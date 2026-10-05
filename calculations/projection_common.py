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


def eur_it(amount: Decimal) -> str:
    """1234567.891 -> '1.234.567,89' (ROUND_HALF_UP, come la quantizzazione del motore)."""
    q = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def scarto_it(mancante: Decimal) -> str:
    """«mancano 0,42» / «ce ne sono 0,42 di troppo»: lo scarto detto, non da dedurre.

    I messaggi dei cancelli sul debito pregresso nominavano tre importi e lasciavano la
    sottrazione a chi legge. Su uno scarto di 42 centesimi contro un debito di 960.937,42 la
    somma «torna» a occhio — il proprietario l'ha segnalato esattamente così («a me la somma
    torna corretta», 2026-09-16) — e la schermata non dava altro modo di scoprire che cosa
    correggere.
    """
    if mancante > ZERO:
        return f"mancano {eur_it(mancante)}"
    return f"ce ne sono {eur_it(-mancante)} di troppo"


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


# ── Ammortamento per masse separate (spec B02, E05 — 2026-09-26) ──
def ammortamento_categoria(
    stato_apertura: Optional[Dict[str, Any]],
    netto_apertura: Decimal,
    quota_base: Decimal,
    investimento: Decimal,
    aliquota: Decimal,
    anno: int,
    override: Optional[Decimal],
    dismissione: Decimal = ZERO,
) -> Tuple[Decimal, Dict[str, Any]]:
    """Quota di ammortamento dell'anno per UNA categoria (immateriali o materiali),
    tenendo separate la massa esistente all'apertura del piano e i cespiti che il
    piano stesso genera — invece di sommarli in un'unica quota che non si ferma mai
    al residuo netto (B02).

    Regole:
    - Primo anno (`stato_apertura is None`): la massa esistente parte dal netto di
      bilancio dell'anno base (`netto_apertura`, sp02/sp03 dell'anno prima), senza
      cespiti nuovi. Dal secondo anno in poi la massa esistente e i cespiti nuovi
      vengono dallo stato dell'anno precedente (`esistente_residuo`, `cespiti_nuovi`
      — le sole due chiavi lette da `stato_apertura`, cosi' un chiamante puo' passare
      uno stato parziale).
    - Un investimento dell'anno (`investimento > 0`) apre un cespite nuovo
      `{'anno', 'importo', 'aliquota', 'residuo': importo}`; l'aliquota e' quella
      dell'anno d'ingresso e resta la sua per tutta la vita del cespite.
    - Riallineamento al netto persistito (I1, revisione finale lotto 1, 2026-09-26): dal
      secondo anno in poi, PRIMA di aprire il cespite dell'investimento dell'anno, il pool
      (`esistente_apertura` + residui dei cespiti) si riporta a `netto_apertura` — un
      `sp_overrides` scritto direttamente su sp02/sp03 lo puo' aver spostato senza che il
      pool, che viene da `prev_details`, lo sappia. Se il pool eccede, la differenza si
      toglie come una dismissione (prima l'esistente, poi i nuovi in ordine d'ingresso, mai
      sotto zero); se manca, si aggiunge al pool esistente. Dichiarato sempre in
      `riallineato_al_netto` (positivo = aggiunto, negativo = tolto, zero quando non serve
      o al primo anno di piano).
    - La quota sull'esistente e' `min(quota_base, esistente_apertura)`: si ferma al
      residuo, non continua alla quota piena di sempre (B02). `quota_base` e'
      `ce09a`/`ce09b` dell'ANNO BASE, costante per tutto il piano.
    - Ogni cespite nuovo ammortizza alla propria aliquota piena, ECCETTO nell'anno
      in cui entra: li' la quota e' meta' aliquota (E05, decisione del proprietario
      2026-09-26), sempre limitata al proprio residuo.
    - Guardia: `netto_apertura + investimento - dismissione` e' il massimo ammortizzabile
      (un `sp_overrides` sullo SP puo' averlo abbassato sotto la quota che le formule
      produrrebbero, e la dismissione dell'anno riduce cio' che resta da ammortizzare).
      Se la somma calcolata lo supera, la quota si LIMITA a quel massimo e si alloca come
      un override (`limitato_al_netto = True`).
    - Un override esplicito (o la guardia sopra) toglie l'importo prima dalla massa
      esistente fino al suo residuo, poi dai cespiti nuovi in ordine d'ingresso;
      `override = True` solo per l'override vero, mai per la guardia. Il CHIAMANTE deve
      rifiutare un override oltre il massimo ammortizzabile (M3, stessa revisione): questa
      funzione non lo fa, quindi da sola onorerebbe un override che il netto non regge.
    - Una dismissione (`dismissione`, solo materiali) si toglie DOPO le quote, nello
      stesso ordine (esistente poi nuovi), mai sotto zero: non e' una quota, e' una
      radiazione del residuo.

    Ritorna `(quota_dell_anno, stato_chiusura)`. Gli importi restano `Decimal`
    grezzi, non quantizzati: la quantizzazione del CE persistito e' a valle.
    """
    netto_apertura = Decimal(str(netto_apertura or 0))
    quota_base = Decimal(str(quota_base or 0))
    investimento = Decimal(str(investimento or 0))
    aliquota = Decimal(str(aliquota or 0))
    dismissione = Decimal(str(dismissione or 0))

    if stato_apertura is None:
        esistente_apertura = netto_apertura
        cespiti_nuovi: List[Dict[str, Any]] = []
        riallineato_al_netto = ZERO
    else:
        esistente_apertura = Decimal(str(stato_apertura.get('esistente_residuo') or 0))
        cespiti_nuovi = [dict(c) for c in (stato_apertura.get('cespiti_nuovi') or [])]
        # Riallineamento al netto persistito (I1, revisione finale lotto 1, 2026-09-26): i pool
        # (`esistente_residuo` + residui dei cespiti) vengono da `prev_details`, che non sa nulla di
        # un `sp_overrides` scritto direttamente su sp02/sp03. Senza questo passo il pool "esistente"
        # resta un fantasma che continua a caricare `quota_base` sul netto degli investimenti nuovi
        # (o, verso l'alto, non si ammortizza mai oltre il pool originale). Si riporta il pool al
        # netto persistito ad ogni inizio d'anno dopo il primo: se eccede, si riduce come una
        # dismissione (prima l'esistente, poi i nuovi in ordine d'ingresso, mai sotto zero); se
        # manca, la differenza si aggiunge al pool esistente. Sempre dichiarato, anche a zero.
        pool_totale = esistente_apertura + sum((c['residuo'] for c in cespiti_nuovi), ZERO)
        riallineato_al_netto = netto_apertura - pool_totale
        if riallineato_al_netto > ZERO:
            esistente_apertura += riallineato_al_netto
        elif riallineato_al_netto < ZERO:
            eccesso = -riallineato_al_netto
            preso = min(eccesso, esistente_apertura)
            esistente_apertura -= preso
            eccesso -= preso
            for cespite in cespiti_nuovi:
                if eccesso <= ZERO:
                    break
                preso = min(eccesso, cespite['residuo'])
                cespite['residuo'] = cespite['residuo'] - preso
                eccesso -= preso

    if investimento > ZERO:
        cespiti_nuovi = cespiti_nuovi + [
            {'anno': anno, 'importo': investimento, 'aliquota': aliquota, 'residuo': investimento}
        ]

    quota_esistente = min(quota_base, esistente_apertura)

    quote_nuovi = []
    for cespite in cespiti_nuovi:
        piena = cespite['importo'] * cespite['aliquota']
        if cespite['anno'] == anno:
            piena = piena / Decimal('2')
        quote_nuovi.append(min(piena, cespite['residuo']))
    quota_nuovi_totale = sum(quote_nuovi, ZERO)

    quota_calcolata = quota_esistente + quota_nuovi_totale
    # La dismissione dell'anno riduce cio' che si puo' davvero ammortizzare (I1): senza,
    # il tetto ignorava una radiazione della stessa annata e la quota poteva restare
    # sopra cio' che il netto, gia' ridotto dalla dismissione, puo' sostenere.
    max_disponibile = netto_apertura + investimento - dismissione

    is_override = override is not None
    limitato_al_netto = (not is_override) and quota_calcolata > max_disponibile

    if is_override or limitato_al_netto:
        importo = Decimal(str(override)) if is_override else max_disponibile
        preso_esistente = min(importo, esistente_apertura)
        esistente_residuo = esistente_apertura - preso_esistente
        restante = importo - preso_esistente
        for cespite in cespiti_nuovi:
            preso = min(restante, cespite['residuo'])
            cespite['residuo'] = cespite['residuo'] - preso
            restante -= preso
        quota = importo
        quota_esistente_dichiarata = preso_esistente
        quota_nuovi_dichiarata = importo - preso_esistente
    else:
        esistente_residuo = esistente_apertura - quota_esistente
        for cespite, quota_c in zip(cespiti_nuovi, quote_nuovi):
            cespite['residuo'] = cespite['residuo'] - quota_c
        quota = quota_calcolata
        quota_esistente_dichiarata = quota_esistente
        quota_nuovi_dichiarata = quota_nuovi_totale

    if dismissione > ZERO:
        preso = min(dismissione, esistente_residuo)
        esistente_residuo -= preso
        restante = dismissione - preso
        for cespite in cespiti_nuovi:
            if restante <= ZERO:
                break
            preso = min(restante, cespite['residuo'])
            cespite['residuo'] = cespite['residuo'] - preso
            restante -= preso

    return quota, {
        'esistente_apertura': esistente_apertura,
        'quota_esistente': quota_esistente_dichiarata,
        'esistente_residuo': esistente_residuo,
        'quota_nuovi': quota_nuovi_dichiarata,
        'cespiti_nuovi': cespiti_nuovi,
        'override': is_override,
        'limitato_al_netto': limitato_al_netto,
        'riallineato_al_netto': riallineato_al_netto,
    }


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
    final instalment. Returns ``(0, 0, 0)`` for an empty list (no-op).

    A loan may also carry ``repayments`` — the capital repaid in each plan year
    (index 0 = first plan year), the hand-scheduled way of describing a PRE-
    EXISTING contract (spec 2026-09-15 §5.1): beyond the list nothing is repaid
    and the residual stays open on the balance sheet, a year's quota is never
    capped below the opening residual, and interest stays rate × opening
    residual, exactly as for a duration-driven contract."""
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
        repayments = loan.get('repayments')
        if repayments is not None:
            # Contratto pregresso scadenziato a mano (spec 2026-09-15 §5.1): il capitale
            # dell'anno e' la voce della lista (zero oltre la lista: il residuo resta
            # aperto), mai oltre il residuo di apertura; interessi sul residuo di apertura.
            if principal <= ZERO:
                continue
            elapsed = target_year - raise_year
            if elapsed < 0:
                continue
            piano = [Decimal(str(r or 0)) for r in repayments]
            opening = max(ZERO, principal - sum(piano[:elapsed], ZERO))
            quota = piano[elapsed] if elapsed < len(piano) else ZERO
            repayment += min(opening, quota)
            interest += opening * rate
            continue
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


# ── Pregresso del circolante: le sette masse di apertura ──
# I sette saldi che l'utente puo' scadenziare. La massa di
# apertura e' letta dal bilancio dell'anno base: e' l'importo che ESISTE GIA', da
# tenere distinto da quello che il piano genera. Il lato breve e il lato lungo si
# sommano, perche' e' il piano — non la classificazione dell'anno base — a dire
# quando quel saldo si chiude.
PREGRESSO_KEYS = (
    "crediti_commerciali",
    "crediti_tributari_breve",
    "crediti_tributari_lungo",
    "debiti_fornitori",
    "debiti_tributari",
    "debiti_previdenziali",
    "altri_debiti",
)
PREGRESSO_LABELS = {
    "crediti_commerciali": "crediti commerciali",
    "crediti_tributari_breve": "crediti tributari entro 12 mesi",
    "crediti_tributari_lungo": "crediti tributari oltre 12 mesi",
    "debiti_fornitori": "debiti verso fornitori",
    "debiti_tributari": "debiti tributari",
    "debiti_previdenziali": "debiti previdenziali",
    "altri_debiti": "altri debiti",
}


def pregresso_opening_masses(getter: Callable[[str], Decimal], acconti_tributari=ZERO):
    """Le sette masse di apertura del pregresso, dall'anno base.

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
        "crediti_tributari_breve": g('sp06e_crediti_tributari_breve') - Decimal(str(acconti_tributari)),
        "crediti_tributari_lungo": g('sp07e_crediti_tributari_lungo'),
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
ALIQUOTA_RIPIEGO = Decimal('27.9')   # IRES + IRAP


def aliquota_effettiva(inc) -> Optional[Decimal]:
    """L'aliquota effettiva di un conto economico, in percentuale assoluta (27,9 = 27,9%).

    `ce20 / risultato ante imposte`; `None` quando non e' derivabile (imposte o
    risultato non positivi) o supera il 60%, dove smette di descrivere un'aliquota.
    E' la regola che il motore applicava da solo fino al 2026-09-18: ora serve a
    PROPORRE l'aliquota (e alla migrazione), mai a sostituirla a quella scritta.
    """
    from calculations.ce_result import calculate_ce_result
    tax = Decimal(str(getattr(inc, 'ce20_imposte', None) or 0))
    pbt = calculate_ce_result(inc).profit_before_tax
    if tax <= ZERO or pbt <= ZERO:
        return None
    rate = tax / pbt * Decimal('100')
    return rate if rate <= Decimal('60') else None


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

    Al 31/12 resta solo il saldo dell'anno in corso: imposta dell'anno meno acconti versati nell'anno. Il DEBITO
    aperto al mese del parziale esce di cassa entro fine anno, e il budget che nasce dal promote scadenzia quel
    saldo.

    ATTENZIONE: dal 2026-09-16 il CREDITO d'apertura NON si incassa piu' — il chiamante
    (`intra_year_engine`) lo somma al credito di chiusura e lo tiene in bilancio — ma `cash_out` qui sotto
    continua a sottrarlo: `posizione netta di apertura + imposta dei mesi restanti − posizione netta di fine
    anno`. Quel campo non ha lettori in produzione (solo due test) e non misura piu' l'uscita di cassa per
    imposte: va corretto o rimosso, non usato.
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
    # Per gli acconti gia' nel bilancio base, l'eccedenza non compensabile
    # resta disponibile negli anni seguenti.
    opening_credit_left: Decimal
    cash_out: Decimal
    credito_compensato: Decimal = ZERO
    # #62 S14/S18: la parte del credito tributario del consuntivo compensata (F24) con cio' che resta da versare.
    credito_storico_compensato: Decimal = ZERO


def tax_settlement_saldo_acconto(*, opening_credit, saldo_due, rate_due, current_tax,
                                 previous_tax, acconto_pct, explicit_advances,
                                 carry_excess_credit=False, credito_storico_compensabile=ZERO) -> TaxYear:
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
    # Il credito generato dal piano segue la regola esistente di compensazione
    # integrale. Gli acconti storici, se distinti dall'utente, si compensano
    # fino ai pagamenti dell'anno; l'eccedenza resta credito.
    saldo_paid = saldo_due
    net = current_tax - acconti
    # This is not diagnostic precision: year N+1 pays ``generated_debt`` as
    # its opening ``saldo_due``.  Keep that state at the same cent precision
    # as the balance-sheet cell it represents, otherwise a fractional tail
    # (for example 5760.04707000 behind a 5760.05 cell) changes next year's
    # cash while remaining invisible in the persisted accounts (#51).
    generated_debt = max(ZERO, net).quantize(CENT, rounding=ROUND_HALF_UP)
    payable = max(ZERO, saldo_paid + acconti + rate_due)
    compensated = min(opening_credit, payable) if carry_excess_credit else opening_credit
    # #62 S14/S18 (decisione del proprietario 2026-10-05): il credito tributario del consuntivo che il piano non
    # incassa si compensa, se l'utente lo sceglie, con cio' che resta da versare dopo il credito da acconti.
    # Il debito generato non cambia: si riduce solo cio' che esce.
    capienza = max(ZERO, payable - compensated)
    storico = min(max(ZERO, d(credito_storico_compensabile)), capienza)
    return TaxYear(
        saldo_paid=saldo_paid, acconti_paid=acconti, rate_paid=rate_due,
        generated_debt=generated_debt, generated_credit=max(ZERO, -net),
        opening_credit_left=opening_credit - compensated,
        cash_out=saldo_paid + acconti + rate_due - compensated - storico,
        credito_compensato=compensated, credito_storico_compensato=storico,
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


# ── Rimanenze di materie prime (sp05a) dal CONSUMO, non dai ricavi (spec B01, 2026-09-26) ──
# Un'azienda compra e consuma materie prime, non le vende: scalare sp05a sul fatturato (come le
# altre rimanenze, che seguono i ricavi) non ha alcun senso fisico. Il DIO delle materie misura
# la giacenza sul CONSUMO dell'anno (`ce05 + apertura - chiusura`), e la relazione e' circolare —
# la chiusura entra nella formula del consumo che la determina. La forma chiusa la risolve:
#     chiusura = (acquisti + apertura) x giorni / (360 + giorni)
# perche' consumo = acquisti + apertura - chiusura e chiusura = consumo x giorni / 360 implicano
# chiusura x 360 = (acquisti + apertura - chiusura) x giorni, cioe' chiusura x (360 + giorni) =
# (acquisti + apertura) x giorni.
def rimanenze_materie(apertura: Decimal, acquisti: Decimal, giorni: Decimal) -> Tuple[Decimal, Decimal]:
    """Rimanenze di materie prime di fine anno e variazione di CE (`ce10`), dal consumo.

    `ce10` segue la convenzione OIC B11 (voce di CE "variazione delle rimanenze di materie
    prime"): un aumento delle rimanenze RIDUCE il costo, quindi `ce10 = apertura - chiusura`.

    La chiusura non scende mai sotto zero (un consumo che supererebbe l'apertura piu' gli
    acquisti non svuota le rimanenze sotto zero). Resta a precisione piena: la quantizzazione al
    centesimo, e la derivazione di `ce10` dalla chiusura gia' quantizzata, sono del chiamante
    (il motore), non di questa funzione pura.
    """
    apertura = Decimal(str(apertura or 0))
    acquisti = Decimal(str(acquisti or 0))
    giorni = Decimal(str(giorni or 0))
    chiusura = max(ZERO, (acquisti + apertura) * giorni / (Decimal('360') + giorni))
    ce10 = apertura - chiusura
    return chiusura, ce10


def rimanenze_gruppo_materie(apertura_a, apertura_b, acquisti, giorni) -> Tuple[Decimal, Decimal]:
    """Materie prime (sp05a) e semilavorati (sp05b) come un solo magazzino di produzione, giorni sul consumo di
    materie (#62 nota S04, decisione del proprietario 2026-10-05). La quota materie del gruppo resta quella
    d'apertura; la chiusura delle materie si risolve in forma chiusa come `rimanenze_materie` (con q = 1 coincide).
    Ritorna (chiusura_a, chiusura_b) a precisione piena: quantizzare e' del chiamante."""
    a, b = Decimal(str(apertura_a or 0)), Decimal(str(apertura_b or 0))
    acq, g = Decimal(str(acquisti or 0)), Decimal(str(giorni or 0))
    q = Decimal('1') if a + b == 0 else a / (a + b)
    chiusura_a = max(ZERO, q * (acq + a) * g / (Decimal('360') + q * g))
    gruppo = max(ZERO, (acq + a - chiusura_a) * g / Decimal('360'))
    return chiusura_a, max(ZERO, gruppo - chiusura_a)


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
    repayments = loan.get('repayments')
    if repayments is None and durata <= ZERO:
        return []
    condizioni = {
        'year': anno,
        'duration': durata,
        'rate': Decimal(str(loan.get('interest_rate') or 0)) / Decimal('100'),
        'grace_years': Decimal(str(loan.get('grace_years') or 0)),
        'balloon_pct': Decimal(str(loan.get('balloon_pct') or 0)),
    }
    condizioni['name'] = loan.get('name')
    if repayments is not None:
        condizioni['repayments'] = [Decimal(str(r or 0)) for r in repayments]
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


def rata_anno_dopo(loan: Mapping[str, Any], anno: int,
                    ultimo_anno_piano: Optional[int] = None) -> Tuple[Decimal, bool]:
    """(capitale dovuto in `anno + 1`, ripetuta) per UN contratto (spec B05).

    Il caso normale e' `new_financing_schedule([loan], anno + 1)[1]`: la rata che il
    calendario del contratto scadenzia per l'anno dopo, zero oltre la lista `repayments`
    o oltre la durata di un contratto a rata fissa.

    Nell'ULTIMO anno di piano (`anno == ultimo_anno_piano`) un contratto scadenziato a
    mano (`repayments`) la cui lista non arriva a coprire l'anno dopo
    (`anno + 1 - loan['year'] >= len(repayments)`) lascerebbe a lungo termine un residuo
    che nessun anno del piano vedra' mai scadere: il calendario del contratto non sa dove
    finisce l'orizzonte, quindi qui — e solo qui — si RIPETE l'ultima rata positiva della
    lista, fino al residuo di fine `anno` se questo e' piu' piccolo. Un residuo di fine
    anno gia' a zero (contratto estinto) non ripete nulla. Una lista che copre l'anno
    dopo, anche con un valore a zero, vince sempre: uno zero scadenziato e' una scelta del
    piano, non un buco da tappare.

    Il residuo di fine `anno` si calcola come lo calcola `new_financing_schedule`
    all'apertura dell'anno dopo: `principal - Σ repayments[:anno + 1 - year]`, mai sotto
    zero — e' esattamente l'`opening` che quella funzione calcolerebbe chiamata con
    `target_year = anno + 1`, quindi non e' un secondo kernel del residuo, solo lo stesso
    conto letto qui per decidere la ripetizione.
    """
    zero = Decimal('0')
    _, rata, _ = new_financing_schedule([loan], anno + 1)
    repayments = loan.get('repayments')
    if anno == ultimo_anno_piano and repayments is not None:
        amount = Decimal(str(loan.get('amount') or 0))
        opening_residual = Decimal(str(loan.get('opening_residual') or 0))
        principal = amount + opening_residual
        if principal > zero:
            piano = [Decimal(str(r or 0)) for r in repayments]
            elapsed_dopo = anno + 1 - int(loan['year'])
            if elapsed_dopo >= len(piano):
                residuo_fine_anno = max(zero, principal - sum(piano[:elapsed_dopo], zero))
                if residuo_fine_anno > zero:
                    ultima_rata_positiva = next((r for r in reversed(piano) if r > zero), zero)
                    return min(residuo_fine_anno, ultima_rata_positiva), True
    return rata, False


def quota_breve_prestiti_nuovi(loans, anno: int, lungo: Decimal,
                                ultimo_anno_piano: Optional[int] = None) -> Decimal:
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

    `ultimo_anno_piano` (spec B05, lotto 1 fix rilievi 2026-09-26): quando `anno` e'
    l'ultimo anno del piano, la rata di ciascun prestito si legge da
    `rata_anno_dopo(loan, anno, ultimo_anno_piano)`, che ripete l'ultima rata positiva
    di un contratto scadenziato a mano la cui lista non arriva a coprire l'anno dopo —
    altrimenti il residuo che nessun anno vedra' mai scadere finirebbe intero a lungo
    termine, oltre l'orizzonte del piano. Fuori dall'ultimo anno (o senza
    `ultimo_anno_piano`) e' lo stesso conto di sempre.

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
    rimborso = sum((rata_anno_dopo(loan, anno, ultimo_anno_piano)[0] for loan in erogati), zero)
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


PAREGGIO_CAMPI = (
    'costi_variabili', 'costi_fissi', 'costi_fissi_operativi',
    'margine_contribuzione_pct', 'fatturato_pareggio',
    'margine_sicurezza', 'margine_sicurezza_pct',
)


def punto_di_pareggio(*, ce01: Decimal, ce02: Optional[Decimal], ce03: Optional[Decimal],
                      ce03a: Optional[Decimal], ce04: Decimal,
                      ce05_fixed: Optional[Decimal], ce05_variable: Optional[Decimal],
                      ce06_fixed: Optional[Decimal], ce06_variable: Optional[Decimal],
                      ce07: Decimal, ce08: Decimal, ce10: Optional[Decimal],
                      ce11: Optional[Decimal], ce11b: Optional[Decimal],
                      ce12: Decimal) -> Dict[str, Optional[Decimal]]:
    """Il blocco pareggio SUL MOL (spec 2026-09-15 §4.3, §5.5; F5, decisione del proprietario
    2026-09-26): UNA sola implementazione, usata sia da ogni anno di piano del motore budget
    (`calculations/forecast_engine.py`) sia dalla colonna base/storica del report finale
    (`backend/app/services/final_report_dossier.py`), cosi' le due colonne sono confrontabili per
    costruzione — mai una seconda copia della formula che puo' divergere.

    Costi variabili = quota variabile di ce05 (materie) + ce06 (servizi). Costi fissi = quota
    fissa di ce05/ce06 + ce07 (godimento beni) + ce08 (personale) + ce12 (oneri diversi).
    `costi_fissi_operativi` porta dentro TUTTO cio' che separa ricavi, variabili e fissi dal MOL
    canonico: meno altri ricavi (ce04, gia' comprensivo dell'eventuale plusvalenza da
    dismissione), variazioni di rimanenze di prodotti (ce02) e lavori interni (ce03, ce03a), piu'
    variazioni di rimanenze di materie (ce10) e accantonamenti (ce11, ce11b). Per costruzione
    (ce01 - fatturato_pareggio) x margine = MOL.

    `None` su ogni chiave quando la quota fisso/variabile di ce05 o ce06 manca (riga sotto
    override: la scomposizione non esiste piu'). Margine di contribuzione e margine di sicurezza
    restano `None` con ricavi o margine di contribuzione non positivi, mai zero — variabili/fissi
    restano dichiarati anche in quel caso.

    Ogni parametro resta a precisione piena (nessun arrotondamento qui): il chiamante quantizza
    come gli serve (il motore al centesimo per `engine_meta`, il report allo stesso modo per
    restare confrontabile con gli anni di piano).
    """
    risultato: Dict[str, Optional[Decimal]] = {campo: None for campo in PAREGGIO_CAMPI}
    if ce05_fixed is None or ce05_variable is None or ce06_fixed is None or ce06_variable is None:
        return risultato
    zero = Decimal('0')
    _z = lambda v: v if v is not None else zero
    costi_variabili = ce05_variable + ce06_variable
    costi_fissi = ce05_fixed + ce06_fixed + ce07 + ce08 + ce12
    costi_fissi_operativi = (costi_fissi + _z(ce10) + _z(ce11) + _z(ce11b)
                             - ce04 - _z(ce02) - _z(ce03) - _z(ce03a))
    risultato.update({
        'costi_variabili': costi_variabili,
        'costi_fissi': costi_fissi,
        'costi_fissi_operativi': costi_fissi_operativi,
    })
    if ce01 > zero and ce01 - costi_variabili > zero:
        margine_pct = (ce01 - costi_variabili) / ce01
        fatturato_pareggio = costi_fissi_operativi / margine_pct
        risultato.update({
            'margine_contribuzione_pct': margine_pct * Decimal('100'),
            'fatturato_pareggio': fatturato_pareggio,
            'margine_sicurezza': ce01 - fatturato_pareggio,
            'margine_sicurezza_pct': (ce01 - fatturato_pareggio) / ce01 * Decimal('100'),
        })
    return risultato
