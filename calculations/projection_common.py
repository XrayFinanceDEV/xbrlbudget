"""
Shared projection rules — the "kernel" called by BOTH forecasting engines.

`forecast_engine` (budget: N years concatenated) and `intra_year_engine`
(infrannuale: one partial period annualised) are two ORCHESTRATORS. They
legitimately differ in HOW they reach the year to project — that difference
stays in each engine. But the per-line CALCULATION RULES must be identical in
both: they are facts about the world (a fixed debt instalment does not change
whether you look at the company over 3 months or 5 years).

Keeping a single implementation of each rule here means a fix lands once and is
correct by construction in both engines. This module was created to end the
duplication that let the debt-repayment amortisation (P2) be correct in the
budget engine while silently staying flat in the intra-year engine.

Each function takes a ``getter(field_name) -> Decimal`` accessor so each engine
can pass its own base-year reader (``_base`` / ``_get_field``) without this
module depending on the ORM object shape.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

ZERO = Decimal('0')
CENT = Decimal('0.01')

# Existing-debt repayment is a BANK plan and therefore uses the total bank
# exposure (entro + oltre 12 mesi). Bonds and other lenders have distinct legal
# maturities and must never be silently amortised as bank debt.
_BANK_FIELDS = ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo')
_NON_BANK_SHORT_FIELDS = (
    'sp16b_debiti_altri_finanz_breve',
    'sp16c_debiti_obbligazioni_breve',
    'sp16d_debiti_fornitori_breve',
    'sp16e_debiti_tributari_breve',
    'sp16f_debiti_previdenza_breve',
    'sp16g_altri_debiti_breve',
)
_NON_BANK_LONG_FIELDS = (
    'sp17b_debiti_altri_finanz_lungo',
    'sp17c_debiti_obbligazioni_lungo',
    'sp17d_debiti_fornitori_lungo',
    'sp17e_debiti_tributari_lungo',
    'sp17f_debiti_previdenza_lungo',
    'sp17g_altri_debiti_lungo',
)


def base_bank_debt(getter: Callable[[str], Decimal]) -> Decimal:
    """Base-year bank debt across both maturity buckets.

    Positive aggregate/detail gaps from abbreviated statements are assigned to
    banks, matching the import/forecast convention used elsewhere in the app.
    """
    explicit_banks = sum((getter(f) for f in _BANK_FIELDS), ZERO)
    short_gap = getter('sp16_debiti_breve') - (
        getter('sp16a_debiti_banche_breve')
        + sum((getter(f) for f in _NON_BANK_SHORT_FIELDS), ZERO)
    )
    long_gap = getter('sp17_debiti_lungo') - (
        getter('sp17a_debiti_banche_lungo')
        + sum((getter(f) for f in _NON_BANK_LONG_FIELDS), ZERO)
    )
    return explicit_banks + max(ZERO, short_gap) + max(ZERO, long_gap)


def base_financial_long_term_debt(getter: Callable[[str], Decimal]) -> Decimal:
    """Backward-compatible alias for the bank-debt repayment base."""
    return base_bank_debt(getter)


def financial_repayment_instalment(getter: Callable[[str], Decimal], repay_years) -> Decimal:
    """Fixed annual instalment on the base-year financial long-term debt, so e.g.
    a 100k loan on a 5-year plan drops by 20k/year and fully amortises to zero
    after ``repay_years``. Returns ZERO when the plan is unset / non-positive or
    there is no financial debt to repay (no-op — zero regression)."""
    if repay_years is None:
        return ZERO
    years = Decimal(str(repay_years))
    if years <= ZERO:
        return ZERO
    bank_debt = base_bank_debt(getter)
    return bank_debt / years if bank_debt > ZERO else ZERO


def altri_finanz_repayment_instalment(getter: Callable[[str], Decimal], altri_years) -> Decimal:
    """Fixed annual instalment on the base-year 'altri finanziatori' debt (sp17b)
    — e.g. an intra-group loan — repaid on its own plan, independent of the bank
    debt. Returns ZERO when the plan is unset / non-positive."""
    if altri_years is None:
        return ZERO
    years = Decimal(str(altri_years))
    if years <= ZERO:
        return ZERO
    return getter('sp17b_debiti_altri_finanz_lungo') / years


# ── TFR (trattamento di fine rapporto) accrual ──
# The yearly TFR accrual is the statutory quota "retribuzione / 13,5". We use the
# projected "salari e stipendi" (ce08b) as the retribuzione base. When an import
# only carries the aggregate personnel cost (no B.9 sub-split), ce08b is 0 and we
# estimate the salary base as 70% of the total personnel cost (oneri sociali /
# TFR / altri make up the remaining ~30%). This drives BOTH the P&L accrual line
# (ce08a) and the TFR fund growth (sp15 = prev + ce08a) in both engines, so the
# fund no longer stays flat when the base year lacks the TFR sub-line.
TFR_DIVISOR = Decimal('13.5')
TFR_SALARY_FALLBACK_PCT = Decimal('0.70')


def tfr_accrual_quota(salari, personale_totale) -> Decimal:
    """Annual TFR accrual = salari e stipendi / 13,5. Falls back to 70% of the
    total personnel cost as the salary base when salari are not broken out.
    Returns ZERO when there is no usable base (no-op)."""
    salari = salari or ZERO
    personale_totale = personale_totale or ZERO
    base = salari if salari > ZERO else personale_totale * TFR_SALARY_FALLBACK_PCT
    return base / TFR_DIVISOR if base > ZERO else ZERO


def deferred_tax_position(lines, default_tax_rate):
    """Calculate deferred-tax assets/liabilities from temporary differences.

    Every line contains a tax base roll-forward (opening + additions - reversals),
    a kind (``deductible`` or ``taxable``), a maturity (``short``/``long``) and
    an optional percentage tax rate.  Returns closing DTA split by maturity, the
    closing deferred-tax liability and the P&L deferred-tax expense (negative for
    a benefit).  Empty input is a strict no-op.
    """
    short_asset = ZERO
    long_asset = ZERO
    liability = ZERO
    deferred_expense = ZERO
    default_rate = Decimal(str(default_tax_rate or ZERO)) / Decimal('100')

    for line in lines or ():
        opening_base = max(ZERO, Decimal(str(line.get('opening_amount') or ZERO)))
        additions = max(ZERO, Decimal(str(line.get('additions') or ZERO)))
        reversals = max(ZERO, Decimal(str(line.get('reversals') or ZERO)))
        closing_base = max(ZERO, opening_base + additions - reversals)
        raw_rate = line.get('tax_rate')
        rate = (
            Decimal(str(raw_rate)) / Decimal('100')
            if raw_rate is not None else default_rate
        )
        opening_tax = opening_base * rate
        closing_tax = closing_base * rate

        if line.get('kind', 'deductible') == 'taxable':
            liability += closing_tax
            deferred_expense += closing_tax - opening_tax
        else:
            if line.get('maturity', 'short') == 'long':
                long_asset += closing_tax
            else:
                short_asset += closing_tax
            deferred_expense -= closing_tax - opening_tax

    return {
        'short_asset': short_asset,
        'long_asset': long_asset,
        'liability': liability,
        'deferred_expense': deferred_expense,
    }


# ── NEW financing raised DURING the plan ──
# Each forecast year's `financing_amount` assumption is a NEW loan raised that
# year (IMPORTO FINANZIAMENTO), linearly amortised (rata = amount / durata) over
# its `financing_duration_years` (DURATA MEDIA), with interest (% TASSO INTERESSE
# PASSIVO) accruing on the year-OPENING outstanding balance.
#
# This is DIFFERENT from `financial_repayment_instalment`, which amortises the
# BASE-year debt on a single plan: here the loans are born DURING the plan, in
# possibly several different years, so the schedule must be assembled across all
# forecast years — a single per-year `assumption` can't see it. The engine builds
# the loan list once (from every assumption) and asks this kernel, per target
# year, for the three figures it needs to keep the balance sheet and the P&L in
# sync: what was raised, what is repaid, and the interest on the residual.
def new_financing_schedule(loans, target_year):
    """For the NEW loans raised during the plan, return the
    ``(raised, repayment, interest)`` totals for ``target_year``:

    - ``raised``     — new financing raised IN ``target_year`` (added to sp17a).
    - ``repayment``  — straight-line instalment due in ``target_year`` across all
      loans still inside their amortisation window (subtracted from sp17a).
    - ``interest``   — interest for ``target_year`` = rate × the loan's OPENING
      outstanding; this is what the P&L (ce15) charges.

    In addition to the legacy keys, a loan may contain ``opening_residual``
    (already present in the base-year bank debt), ``grace_years`` and
    ``balloon_pct``. Grace years are interest-only; the balloon is paid with the
    final instalment. Returns ``(0, 0, 0)`` for an empty list (no-op)."""
    raised = ZERO
    repayment = ZERO
    interest = ZERO
    for loan in loans or ():
        raise_year = loan['year']
        amount = Decimal(str(loan.get('amount') or ZERO))
        opening_residual = Decimal(str(loan.get('opening_residual') or ZERO))
        principal = amount + opening_residual
        duration = int(Decimal(str(loan.get('duration') or ZERO)))
        rate = Decimal(str(loan.get('rate') or ZERO))
        grace_years = int(Decimal(str(loan.get('grace_years') or ZERO)))
        balloon_pct = Decimal(str(loan.get('balloon_pct') or ZERO)) / Decimal('100')
        if principal <= ZERO or duration <= 0 or grace_years >= duration:
            continue
        if target_year == raise_year:
            raised += amount
        elapsed = target_year - raise_year           # whole years since raised
        if 0 <= elapsed < duration:
            balloon = principal * max(ZERO, min(Decimal('1'), balloon_pct))
            amort_years = duration - grace_years
            annual_principal = (principal - balloon) / Decimal(amort_years)
            previous_amort_years = max(0, elapsed - grace_years)
            opening = max(
                ZERO,
                principal - annual_principal * Decimal(previous_amort_years),
            )
            current_repayment = ZERO
            if elapsed >= grace_years:
                current_repayment = annual_principal
                if elapsed == duration - 1:
                    current_repayment += balloon
            repayment += min(opening, current_repayment)
            interest += opening * rate
    return raised, repayment, interest


# ── Pregresso del circolante: le cinque masse di apertura ──
# I cinque saldi che l'utente puo' scadenziare (spec lotto 2 §3.1). La massa di
# apertura e' letta dal bilancio dell'anno base: e' l'importo che ESISTE GIA', da
# tenere distinto da quello che il piano genera. Il lato breve e il lato lungo si
# sommano, perche' e' il piano — non la classificazione dell'anno base — a dire
# quando quel saldo si chiude.
PREGRESSO_KEYS = (
    "crediti_commerciali",
    "debiti_fornitori",
    "debiti_tributari",
    "debiti_previdenziali",
    "altri_debiti",
)
PREGRESSO_LABELS = {
    "crediti_commerciali": "crediti commerciali",
    "debiti_fornitori": "debiti verso fornitori",
    "debiti_tributari": "debiti tributari",
    "debiti_previdenziali": "debiti previdenziali",
    "altri_debiti": "altri debiti",
}


def pregresso_opening_masses(getter: Callable[[str], Decimal]):
    """Le cinque masse di apertura del pregresso, dall'anno base.

    I crediti commerciali sono i soli crediti COMMERCIALI: crediti tributari e
    imposte anticipate (`sp06e/f`, `sp07e/f`) dipendono dalla posizione fiscale,
    non dalla rotazione, e restano fuori — esattamente come restano fuori dal DSO.
    """
    g = lambda field: getter(field) or ZERO
    return {
        "crediti_commerciali": (
            g('sp06_crediti_breve') - g('sp06e_crediti_tributari_breve') - g('sp06f_imposte_anticipate_breve')
            + g('sp07_crediti_lungo') - g('sp07e_crediti_tributari_lungo') - g('sp07f_imposte_anticipate_lungo')
        ),
        "debiti_fornitori": g('sp16d_debiti_fornitori_breve') + g('sp17d_debiti_fornitori_lungo'),
        "debiti_tributari": g('sp16e_debiti_tributari_breve') + g('sp17e_debiti_tributari_lungo'),
        "debiti_previdenziali": g('sp16f_debiti_previdenza_breve') + g('sp17f_debiti_previdenza_lungo'),
        "altri_debiti": g('sp16g_altri_debiti_breve') + g('sp17g_altri_debiti_lungo'),
    }


# ── Runoff schedule: opening balance parcelled into year-by-year collections ──
@dataclass(frozen=True)
class RunoffYear:
    opening: Decimal
    closed: Decimal
    writeoff: Decimal
    residual: Decimal
    residual_short: Decimal
    residual_long: Decimal


def _dec_list(values):
    return [Decimal(str(v or 0)) for v in (values or [])]


def validate_runoff(opening, amounts, writeoff, horizon, label):
    """Errori in italiano, per l'utente: negativo, oltre l'orizzonte, oltre la massa."""
    amounts, writeoff = _dec_list(amounts), _dec_list(writeoff)
    if any(a < ZERO for a in amounts) or any(w < ZERO for w in writeoff):
        raise ValueError(f"Scadenziamento di {label}: un importo è negativo")
    if len(amounts) > horizon or len(writeoff) > horizon:
        raise ValueError(f"Scadenziamento di {label}: il piano va oltre l'orizzonte di {horizon} anni")
    total = sum(amounts, ZERO) + sum(writeoff, ZERO)
    if total - Decimal(str(opening)) > CENT:
        raise ValueError(
            f"Scadenziamento di {label}: la somma supera il saldo di apertura ({total:.2f} > {Decimal(str(opening)):.2f})")


def runoff_schedule(opening, amounts, writeoff, year_index, horizon) -> RunoffYear:
    """Residuo del pregresso dopo l'anno `year_index` e la sua scadenza.

    `residual_short` e' l'importo dovuto nell'anno dopo (spec §3.3); tutto il
    resto e' oltre 12 mesi. Non valida: chiamare validate_runoff prima del ciclo.
    """
    opening = Decimal(str(opening))
    amounts, writeoff = _dec_list(amounts), _dec_list(writeoff)
    at = lambda lst, i: lst[i] if 0 <= i < len(lst) else ZERO
    closed = at(amounts, year_index)
    wo = at(writeoff, year_index)
    residual = opening - sum(amounts[:year_index + 1], ZERO) - sum(writeoff[:year_index + 1], ZERO)
    residual = max(ZERO, residual)
    due_next = at(amounts, year_index + 1) if year_index + 1 < horizon else ZERO
    residual_short = min(residual, due_next)
    return RunoffYear(opening=opening, closed=closed, writeoff=wo, residual=residual,
                      residual_short=residual_short, residual_long=residual - residual_short)


# ── Tax settlement: saldo + acconto kernel ──
def acconti_dovuti(explicit_advances, reference_tax, acconto_pct=Decimal('100')) -> Decimal:
    """Gli acconti dell'anno: l'importo esplicito se maggiore di zero, altrimenti la percentuale dell'imposta di riferimento.

    Zero (il default di colonna di `tax_advances_paid`) e un negativo valgono «non dichiarato». Regola unica dei due
    motori: il budget la chiama con l'imposta dell'anno prima, l'infrannuale con l'imposta dell'anno di riferimento.
    """
    d = lambda v: Decimal(str(v or 0))
    if d(explicit_advances) > ZERO:
        return d(explicit_advances)
    return max(ZERO, d(reference_tax) * d(acconto_pct) / Decimal('100'))


@dataclass(frozen=True)
class PosizioneTributariaFineAnno:
    closing_credit: Decimal
    closing_debt: Decimal
    acconti: Decimal
    cash_out: Decimal


def posizione_tributaria_fine_anno(*, opening_credit, opening_debt, remaining_current_tax, current_tax,
                                   reference_tax, explicit_advances) -> PosizioneTributariaFineAnno:
    """La posizione tributaria al 31/12 dell'infrannuale (spec lotto 3A §4.3, decisione 4 del proprietario).

    Al 31/12 resta solo il saldo dell'anno in corso: imposta dell'anno meno acconti versati nell'anno. Quanto era
    aperto al mese del parziale esce di cassa entro fine anno: `cash_out` = posizione netta di apertura + imposta
    che matura nei mesi restanti − posizione netta di fine anno. Il budget che nasce dal promote scadenzia quel saldo.
    """
    d = lambda v: Decimal(str(v or 0))
    acconti = acconti_dovuti(explicit_advances, reference_tax)
    netto_fine = d(current_tax) - acconti
    netto_apertura = d(opening_debt) - d(opening_credit)
    return PosizioneTributariaFineAnno(
        closing_credit=max(ZERO, -netto_fine),
        closing_debt=max(ZERO, netto_fine),
        acconti=acconti,
        cash_out=netto_apertura + d(remaining_current_tax) - netto_fine,
    )


@dataclass(frozen=True)
class TaxYear:
    saldo_paid: Decimal
    acconti_paid: Decimal
    rate_paid: Decimal
    generated_debt: Decimal
    generated_credit: Decimal
    opening_credit_left: Decimal
    cash_out: Decimal


def tax_settlement_saldo_acconto(*, opening_credit, saldo_due, rate_due, current_tax,
                                 previous_tax, acconto_pct, explicit_advances) -> TaxYear:
    """Imposte a saldo + acconto (spec lotto 2 §3.2). La regola degli acconti e' `acconti_dovuti`, condivisa con
    `posizione_tributaria_fine_anno` dell'infrannuale.

    L'importo esplicito di acconti (`explicit_advances`) vale come override SOLO se > ZERO.
    Lo zero (il valore di default in DB: Column(Numeric(15,2), default=0, nullable=False))
    significa «non dichiarato», e in quel caso ricade sulla percentuale dell'anno precedente
    (`acconto_pct` sulla `previous_tax`). Chi vuole ZERO acconti assoluti (nessun acconto)
    deve impostare `acconto_pct = 0`.
    """
    d = lambda v: Decimal(str(v or 0))
    opening_credit, saldo_due, rate_due = d(opening_credit), d(saldo_due), d(rate_due)
    current_tax, previous_tax = d(current_tax), d(previous_tax)
    acconti = acconti_dovuti(explicit_advances, previous_tax, acconto_pct)
    used = min(opening_credit, saldo_due)
    saldo_paid = saldo_due - used
    net = current_tax - acconti
    return TaxYear(
        saldo_paid=saldo_paid, acconti_paid=acconti, rate_paid=rate_due,
        generated_debt=max(ZERO, net), generated_credit=max(ZERO, -net),
        opening_credit_left=opening_credit - used,
        cash_out=saldo_paid + acconti + rate_due,
    )


# ── Giorni di magazzino dedotti: la soglia per settore (lotto 3A, Task 10) ──
# Oltre un anno di giacenza un DIO dedotto smette di descrivere l'azienda — tranne dove un magazzino lungo e'
# il mestiere: Immobiliare (5, immobili in rimanenza) ed Edilizia (6, lavori in corso). Un solo punto per la
# tabella, usato dal motore budget e dall'infrannuale. `None` = nessuna soglia.
GIORNI_MAGAZZINO_MAX_DEFAULT = Decimal('365')
GIORNI_MAGAZZINO_MAX_PER_SETTORE: Dict[int, Optional[Decimal]] = {5: None, 6: None}


def soglia_giorni_magazzino(settore) -> Optional[Decimal]:
    """La soglia oltre cui un DIO dedotto e' degenere nel settore dato, o `None` se non ce n'e'. Settore assente o
    non intero: la soglia di sempre."""
    try:
        chiave = int(settore) if settore is not None else None
    except (TypeError, ValueError):
        chiave = None
    return GIORNI_MAGAZZINO_MAX_PER_SETTORE.get(chiave, GIORNI_MAGAZZINO_MAX_DEFAULT)


# ── Debito bancario: le regole condivise dai due motori (lotto 3A, Task 3) ──

def e_contratto_pregresso(loan) -> bool:
    """Un contratto con `opening_residual` > 0 descrive debito bancario GIA' in bilancio (pregresso).

    Dopo `contratti_da_riga_finanziamento` nessun contratto porta insieme `amount` e `opening_residual`,
    quindi il predicato basta da solo.
    """
    return Decimal(str(loan.get('opening_residual') or 0)) > ZERO


def contratti_da_riga_finanziamento(loan: Mapping[str, Any], anno: int) -> List[Dict[str, Any]]:
    """Una riga di `financing_loans` → 0, 1 o 2 contratti del kernel (Ruling 45).

    Un contratto MISTO (`amount` e `opening_residual` insieme) diventa due contratti con le stesse
    condizioni: uno col solo importo nuovo, uno col solo residuo pregresso. Un calendario di
    ammortamento e' lineare nel capitale, quindi la somma dei due equivale al contratto unico. Durata
    nulla o negativa: nessun contratto (il kernel lo salterebbe comunque).
    """
    importo = Decimal(str(loan.get('amount') or 0))
    residuo = Decimal(str(loan.get('opening_residual') or 0))
    durata = Decimal(str(loan.get('duration_years') or 0))
    if durata <= ZERO:
        return []
    condizioni = {
        'year': anno,
        'duration': durata,
        'rate': Decimal(str(loan.get('interest_rate') or 0)) / Decimal('100'),
        'grace_years': Decimal(str(loan.get('grace_years') or 0)),
        'balloon_pct': Decimal(str(loan.get('balloon_pct') or 0)),
    }
    contratti = []
    if importo > ZERO:
        contratti.append({**condizioni, 'amount': importo, 'opening_residual': ZERO})
    if residuo > ZERO:
        contratti.append({**condizioni, 'amount': ZERO, 'opening_residual': residuo})
    return contratti


def residuo_prestiti_nuovi(loans, fino_al_anno: int) -> Decimal:
    """Il residuo dei soli prestiti NUOVI a fine `fino_al_anno`, come il motore lo persiste.

    La catena e' quella che il previsionale ha sempre scritto per un prestito da
    solo: residuo dell'anno prima al centesimo, piu' l'erogato, meno la rata del
    kernel, al centesimo. Quantizzare anno per anno non e' un vezzo: un residuo
    calcolato sul calendario grezzo differisce di un centesimo da quello
    persistito (100.000,38 in 4 anni: 25.000,095 grezzo contro 25.000,11
    persistito il terzo anno), e quel centesimo, tolto a `sp17a`, finirebbe
    attribuito al debito bancario pregresso.
    """
    zero, cent = Decimal('0'), Decimal('0.01')
    anni = [int(loan['year']) for loan in (loans or ())]
    if not anni:
        return zero
    residuo = zero
    for anno in range(min(anni), fino_al_anno + 1):
        raised, repayment, _ = new_financing_schedule(loans, anno)
        residuo = max(zero, residuo + raised - repayment).quantize(cent, rounding=ROUND_HALF_UP)
    return residuo


def quota_breve_prestiti_nuovi(loans, anno: int, lungo: Decimal) -> Decimal:
    """Quanto del residuo dei prestiti NUOVI dentro `lungo` (`sp17a` grezzo a fine `anno`) scade l'anno dopo.

    Il residuo nuovo e' quello che l'anno dopo trovera' all'apertura,
    `min(sp17a, catena)`: se lo sweep ha eroso il prestito (prima il pregresso, poi
    il nuovo), la quota si calcola su cio' che ne resta.

    Il limite finale, mai oltre `lungo` arrotondato per difetto, tiene `lungo -
    quota` non negativo. E' la condizione perche' la riclassifica sia esatta al
    centesimo: su valori non negativi ROUND_HALF_UP e' invariante per traslazione
    di centesimi interi, quindi `Q(lungo - quota) + quota = Q(lungo)`. Senza, un
    lungo grezzo di 5.000,005 tutto in scadenza l'anno dopo darebbe quota 5.000,01
    e un `sp17a` persistito di -0,01.

    E' la stessa regola del pregresso scadenziato (`runoff_schedule`:
    `residual_short = min(residuo, dovuto l'anno dopo)`), ma letta sul calendario
    del kernel dei prestiti invece che su un elenco di importi: la quota a breve e'
    il capitale che la catena persistita toglie al residuo nell'anno dopo. Da qui
    discendono le tre regole del Task 17 senza un ramo per ciascuna:
    - durante il preammortamento la rata dell'anno dopo e' zero, e la quota a breve
      anche;
    - nell'anno prima della maxirata la rata dell'anno dopo la contiene, e la
      maxirata sta a breve;
    - l'ultimo anno di orizzonte non si azzera: il calendario del contratto non sa
      dove finisce il piano. (E' qui che la regola si separa da `runoff_schedule`,
      che oltre l'orizzonte non ha importi e restituisce zero.)

    Contano solo i prestiti gia' erogati a fine `anno`: un prestito che nasce
    l'anno dopo non e' debito di quest'anno, ne' a breve ne' oltre.

    Perche' la differenza fra due residui al centesimo e non la rata arrotondata:
    100.000,38 in 4 anni ha rata 25.000,095, ma la catena passa da 75.000,29 a
    50.000,20 e toglie 25.000,09. Con 25.000,10 a breve il lungo di fine anno
    (50.000,19) risulterebbe inferiore al residuo che l'anno dopo non scade
    (50.000,20): un centesimo di debito oltre l'esercizio che nascerebbe dal nulla.
    """
    zero, cent = Decimal('0'), Decimal('0.01')
    residuo = min(lungo.quantize(cent, rounding=ROUND_HALF_UP), residuo_prestiti_nuovi(loans, anno))
    if residuo <= zero:
        return zero
    erogati = [loan for loan in (loans or ()) if int(loan['year']) <= anno]
    _, rimborso, _ = new_financing_schedule(erogati, anno + 1)
    dopo = max(zero, residuo - rimborso).quantize(cent, rounding=ROUND_HALF_UP)
    return min(residuo - dopo, lungo.quantize(cent, rounding=ROUND_DOWN))


def separa_prestiti_nuovi(sp17a_apertura: Decimal, prestiti_nuovi, anno: int) -> Tuple[Decimal, Decimal]:
    """(pregresso, residuo nuovo di apertura) dal debito bancario a lungo di apertura dell'anno `anno`.

    Il residuo nuovo di apertura e' la catena dei prestiti nuovi a fine `anno - 1`, mai oltre
    `sp17a_apertura`: un cash sweep o un `sp_overrides` che l'anno prima ha abbassato `sp17a` sotto la
    catena lo ha abbassato prima sul pregresso e poi sul nuovo. Va fatto PRIMA di ogni piano di rimborso:
    ogni debito si riduce solo col proprio rimborso (I1 esteso, Task 16 del lotto 2).
    """
    nuovo = min(sp17a_apertura, residuo_prestiti_nuovi(prestiti_nuovi, anno - 1))
    return sp17a_apertura - nuovo, nuovo
