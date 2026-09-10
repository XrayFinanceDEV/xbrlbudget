"""
Forecast Calculation Engine
Generates forecasted Income Statements and Balance Sheets based on budget assumptions
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from database.models import (
    Company, FinancialYear, BalanceSheet, IncomeStatement,
    BudgetScenario, BudgetAssumptions, ForecastYear,
    ForecastBalanceSheet, ForecastIncomeStatement
)
from calculations.projection_common import (
    base_bank_debt, financial_repayment_instalment, altri_finanz_repayment_instalment,
    tfr_accrual_quota, deferred_tax_position,
    new_financing_schedule, PREGRESSO_KEYS, PREGRESSO_LABELS,
    pregresso_opening_masses, runoff_schedule, validate_runoff,
    tax_settlement_saldo_acconto,
)
from calculations.ce_result import calculate_ce_result


# ── INDICIZZAZIONE DELLE VOCI MINORI DELLO SP (Task 15) ──
#
# «Le voci minori dei debiti si tengono o costanti o in crescita con il
# fatturato. Aumenta il volume aumenta tutto» (indicazione del proprietario,
# 2026-09-09). Fino a qui il default era «costante» e basta: `_sp_growth`
# restituisce zero quando la percentuale non e' impostata, quindi una voce
# lasciata in pace resta ferma per tutto il piano.
#
# La forma dell'aggancio NON e' nuova: e' quella gia' cablata sui debiti
# previdenziali (`previdenza_scales_with_personnel`), cioe' `stock dell'ANNO
# BASE × fattore del driver`. Indicizzare sulla base non accumula deriva, mentre
# un `prev × (1+%)` composto per cinque anni si'.

# ── GIORNI MEDI DERIVATI: la soglia oltre cui non descrivono piu' l'azienda ──
#
# Un giorno medio DEDOTTO dall'anno base e' un rapporto: giacenza / flusso. Oltre
# un anno di giacenza smette di descrivere l'azienda e descrive il proprio
# denominatore — e moltiplicare il flusso PROIETTATO per quel rapporto non e' una
# stima imprecisa, e' un moltiplicatore arbitrario. Stessa soglia del rilievo G1
# del banco di sensibilita' (`scripts/sensibilita_ipotesi.py`) e stessa nozione
# del motore infrannuale (`intra_year_engine._turnover_ratio`, «piu' di un anno
# di magazzino»). Un giorno ESPLICITO dell'utente non passa di qui: e' una
# scelta, non una derivazione.
MAX_DERIVED_TURNOVER_DAYS: Decimal = Decimal("365")

SP_INDEXING_DRIVERS: Tuple[str, ...] = ("ricavi", "acquisti", "personale")

# Le voci minori agganciabili, e il campo dell'anno base che il fattore
# moltiplica. Sono le voci che oggi seguono una `sp*_growth_pct` annullabile:
# fuori da questo elenco una chiave viene ignorata e dichiarata, mai applicata
# a una voce che il motore governa in un altro modo.
SP_INDEXABLE_FIELDS: Dict[str, str] = {
    "sp01": "sp01_crediti_soci",
    "sp04": "sp04_immob_finanziarie",
    "sp08": "sp08_attivita_finanziarie",
    "sp10": "sp10_ratei_risconti_attivi",
    "sp14": "sp14_fondi_rischi",
    "sp16f": "sp16f_debiti_previdenza_breve",
    "sp16g": "sp16g_altri_debiti_breve",
    "sp17d": "sp17d_debiti_fornitori_lungo",
    "sp17f": "sp17f_debiti_previdenza_lungo",
    "sp17g": "sp17g_altri_debiti_lungo",
    "sp18": "sp18_ratei_risconti_passivi",
}

# La voce e il saldo di pregresso che la scadenzia. Ruling 17: dichiarare un
# piano significa «questo saldo lo sto estinguendo», dichiarare un driver
# significa «questo saldo si rigenera col volume» — due affermazioni
# contraddittorie sulla stessa voce, e il motore non ne inventa una terza. Il
# motivo tecnico e' misurato: `validate_pregresso` impone che la massa dichiarata
# coincida col bilancio base, quindi per una voce con piano il generato e'
# `base − massa` = 0, e un fattore per zero resta zero — cioe' codice morto che
# l'utente crede attivo.
SP_INDEXING_PLAN_KEY: Dict[str, str] = {
    "sp16f": "debiti_previdenziali",
    "sp17f": "debiti_previdenziali",
    "sp16g": "altri_debiti",
    "sp17g": "altri_debiti",
    "sp17d": "debiti_fornitori",
}

# Le voci che un altro meccanismo governa gia': indicizzarle darebbe due padroni
# allo stesso numero. Non e' una dimenticanza, ed e' per questo che la chiave
# viene DICHIARATA ignorata invece di sparire.
SP_INDEXING_GOVERNED: Dict[str, str] = {
    "sp06e": "governata dalla posizione tributaria",
    "sp16e": "governata dalla posizione tributaria",
    "sp17e": "governata dalla posizione tributaria",
    "sp16a": "governata dal piano di rimborso",
    "sp17a": "governata dal piano di rimborso",
    # Le imposte anticipate/differite non ruotano col volume: quando ci sono
    # differenze temporanee le scrive il kernel del deferred, e anche senza il
    # proprietario ha gia' escluso che salgano coi ricavi («crediti tributari /
    # imposte anticipate che salgono coi ricavi — non e' corretto», la ragione
    # per cui sp06e/sp06f sono stati tolti dal DSO).
    "sp06f": "governata dalla posizione fiscale",
    "sp07f": "governata dalla posizione fiscale",
}


@dataclass
class ForecastSource:
    """Le letture che il calcolo richiede: scenario, anno base e i due prospetti."""
    scenario: BudgetScenario
    base_fy: FinancialYear
    base_bs: BalanceSheet
    base_inc: IncomeStatement


@dataclass
class ForecastYearResult:
    """Un anno calcolato: i due prospetti come dict, piu' i `details` dichiarati."""
    year: int
    income_statement: Dict[str, Decimal]
    balance_sheet: Dict[str, Decimal]
    details: Dict[str, Any]


@dataclass
class ForecastError:
    """L'errore del motore, con l'anno su cui si e' fermato (`None` = a monte del ciclo)."""
    year: Optional[int]
    message: str


@dataclass
class ForecastComputation:
    """Esito del calcolo puro: gli anni prodotti, e l'eventuale errore che li ha fermati."""
    years: List[ForecastYearResult]
    error: Optional[ForecastError] = None


def _eur_it(amount: Decimal) -> str:
    """1234567.891 -> '1.234.567,89' (ROUND_HALF_UP, come la quantizzazione del motore)."""
    q = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@dataclass
class _Overdraft:
    """Lo scoperto di conto corrente concesso su UN anno di piano.

    La cassa plugga solo verso l'alto: un plug negativo e' un fabbisogno
    scoperto. Che cosa succede allora dipende da una scelta ESPLICITA
    dell'utente (`overdraft_allowed`, spenta di default), non dal motore —
    ed e' la ragione per cui questo oggetto esiste invece di un `if` sparso
    nei tre punti che possono produrre una cassa negativa.

    `opening` e' lo scoperto in essere all'APERTURA dell'anno, che l'anno
    precedente ha dichiarato in `details['scoperto_residuo']`: e' su quello, e
    mai su quello che l'anno stesso sta generando, che maturano gli oneri —
    altrimenti l'interesse cambierebbe la cassa che determina l'interesse.

    `raised` e `repaid` si accumulano perche' i punti che possono accendere lo
    scoperto sono piu' d'uno (il plug, il ricalcolo dopo un `sp_overrides`, la
    quadratura finale al centesimo): il tetto va misurato sul totale, non su
    ciascuno separatamente.
    """
    allowed: bool = False
    limit: Optional[Decimal] = None      # None = concesso senza tetto
    opening: Decimal = Decimal("0")
    raised: Decimal = Decimal("0")
    repaid: Decimal = Decimal("0")

    @property
    def outstanding(self) -> Decimal:
        """Lo scoperto in essere adesso: apertura, meno rimborsi, piu' acceso."""
        return self.opening - self.repaid + self.raised

    def copri(self, fabbisogno: Decimal) -> None:
        """Accende `fabbisogno` di scoperto, o alza.

        Non concesso: stesso messaggio di sempre (`Unfunded financing
        requirement`), che il frontend riconosce con una sola regex.
        Oltre il tetto: alza dicendo i due importi, quello richiesto e quello
        concesso — un tetto che si limitasse a tagliare produrrebbe di nuovo
        una cassa negativa, cioe' il difetto che questo codice chiude.
        """
        if not self.allowed:
            raise ValueError(
                f"Unfunded financing requirement {fabbisogno:,.2f}: add an explicit "
                "financing assumption; no bank debt was created automatically"
            )
        richiesto = self.outstanding + fabbisogno
        if self.limit is not None and richiesto > self.limit:
            # In italiano e con le migliaia all'europea: il frontend non ha una
            # traduzione per questo messaggio e lo mostra GREZZO
            # (`previewNotice`, `saveNotice`), accanto a importi formattati
            # cosi'. Il riconoscimento del passo sta in `stepForErrorMessage`.
            raise ValueError(
                "Scoperto di conto corrente oltre il tetto concesso: "
                f"servono {_eur_it(richiesto)}, il tetto concesso e' {_eur_it(self.limit)}"
            )
        self.raised += fabbisogno


class _DictView:
    """getattr(view, 'sp09_...') su un dict del motore: previous_* senza ORM.

    Nel percorso persistente `previous_inc`/`previous_bs` sono gli oggetti ORM
    appena scritti e i calcolatori li leggono con `getattr`. Nel calcolo puro
    l'ORM non c'e': questo adattatore lascia i calcolatori invariati. Una chiave
    assente alza `AttributeError`, cosi' `getattr(obj, field, default)` ricade sul
    default esattamente come su una colonna a `None`.
    """
    __slots__ = ("_d",)

    def __init__(self, d):
        self._d = d

    def __getattr__(self, name):
        try:
            return self._d[name]
        except KeyError:
            raise AttributeError(name)


def _split_to_cents(fixed_part: Decimal, line_value: Decimal) -> Tuple[Decimal, Decimal]:
    """(quota fissa, quota variabile) al centesimo, con la somma pari **esatta**
    alla riga di CE che spiegano.

    La riga e' l'arrotondamento della somma, non la somma degli arrotondamenti:
    quantizzare i due addendi separatamente li fa divergere dalla voce di un
    centesimo, cioe' produce un dettaglio che non ricompone il proprio totale.
    La quota fissa si arrotonda, la variabile assorbe il residuo.
    """
    fixed_q = Decimal(str(fixed_part)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return fixed_q, line_value - fixed_q


def load_forecast_source(db: Session, scenario_id: int) -> ForecastSource:
    """Scenario, anno base e i due prospetti, con gli stessi controlli di
    generate_forecast: scenario assente, base assente o incompleto, gate
    semantico dell'infrannuale, ricavi base negativi. Alza ValueError."""
    scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first()
    if not scenario:
        raise ValueError(f"Budget scenario {scenario_id} not found")

    # Get base year data (prefer full-year record)
    from database.queries import get_fy_prefer_full
    base_fy = get_fy_prefer_full(db, scenario.company_id, scenario.base_year)
    if not base_fy or not base_fy.balance_sheet or not base_fy.income_statement:
        raise ValueError(f"Base year {scenario.base_year} data not found or incomplete")

    # Reuse the same semantic gate as the infrannuale engine.  A balanced
    # aggregate with missing debt/credit detail is not safe for DSO/DPO,
    # repayment schedules or cash-flow projection.
    from calculations.intra_year_engine import IntraYearEngine
    IntraYearEngine(db)._validate_forecast_source(base_fy, "Base source")

    base_inc = base_fy.income_statement

    # Guard: a base year with NEGATIVE sales revenue is a broken extraction
    # (ricavi delle vendite, OIC A.1, can never be < 0). Projecting it produces
    # garbage — applying a growth % to a negative base inverts the direction
    # (e.g. +15% makes it MORE negative). Refuse with an honest error pointing to
    # Rettifiche instead of generating a misleading forecast.
    if (base_inc.ce01_ricavi_vendite or Decimal('0')) < 0:
        raise ValueError(
            f"Anno base {scenario.base_year}: ricavi delle vendite negativi "
            f"({base_inc.ce01_ricavi_vendite:.0f} €) — estrazione del bilancio non valida. "
            f"Correggi i ricavi in Rettifiche (o re-importa il bilancio) prima di generare il previsionale."
        )

    return ForecastSource(scenario=scenario, base_fy=base_fy,
                          base_bs=base_fy.balance_sheet, base_inc=base_inc)


def prune_out_of_plan_forecast_years(db: Session, scenario_id: int, planned_years) -> int:
    """Cancella i `ForecastYear` dello scenario che non sono piu' nel piano.

    La generazione fa l'upsert dei soli anni che hanno un'ipotesi, quindi senza
    questa potatura riportare un piano da 5 anni a 3 lascerebbe due anni
    fantasma coi numeri del salvataggio precedente: `/analysis`, il rendiconto e
    il report continuerebbero a mostrarli, e nessun controllo se ne
    accorgerebbe. Il cascade porta via anche SP e CE dell'anno rimosso.

    Un elenco vuoto non cancella nulla: e' assenza di informazione, non un piano
    a zero anni. Non fa commit — la decide il chiamante.
    """
    years = sorted({int(y) for y in planned_years})
    if not years:
        return 0
    stale = db.query(ForecastYear).filter(
        ForecastYear.scenario_id == scenario_id,
        ForecastYear.year.notin_(years)
    ).all()
    for fy in stale:
        db.delete(fy)
    db.flush()
    return len(stale)


def validate_pregresso(pregresso, base_bs, horizon: int) -> Dict[str, Dict[str, Any]]:
    """Normalizza lo scadenziamento del pregresso in Decimal, o alza ValueError.

    Tre controlli, tutti con messaggi in italiano perche' li legge l'utente:
    la massa dichiarata deve coincidere con quella del bilancio base (±0,01 —
    scadenziare un saldo che nel frattempo e' cambiato scadenzia un numero che
    non esiste piu'), il piano non puo' andare oltre l'orizzonte, e la somma
    degli importi non puo' superare la massa: incassare piu' di quanto c'e'
    inventa cassa, quindi e' un errore, mai un troncamento silenzioso.

    `pregresso` assente o vuoto restituisce `{}`: nessun piano, il motore usa
    le formule di oggi intere, lato breve e lato lungo (spec §3.1).
    """
    if not pregresso:
        return {}
    cent = Decimal('0.01')
    masses = pregresso_opening_masses(lambda field: getattr(base_bs, field, None))
    out: Dict[str, Dict[str, Any]] = {}
    for key in PREGRESSO_KEYS:
        plan = pregresso.get(key)
        if not plan:
            continue
        label = PREGRESSO_LABELS[key]
        opening = Decimal(str(plan.get('opening') or 0))
        if abs(opening - masses[key]) > cent:
            raise ValueError(
                f"Il saldo di apertura di {label} è cambiato "
                f"({opening:.2f} → {masses[key]:.2f}): rivedi lo scadenziamento"
            )
        amounts = [Decimal(str(a or 0)) for a in plan.get('amounts') or []]
        # L'inesigibile esiste solo sui crediti: su un debito non significa nulla.
        writeoff = (
            [Decimal(str(w or 0)) for w in plan.get('writeoff') or []]
            if key == "crediti_commerciali" else []
        )
        if key == "debiti_tributari":
            saldo = Decimal(str(plan.get('saldo') or 0))
            rate = Decimal(str(plan.get('rateizzato') or 0))
            if abs(saldo + rate - opening) > cent:
                raise ValueError(
                    f"Debiti tributari: saldo + rateizzato ({saldo + rate:.2f}) deve essere "
                    f"uguale al saldo di apertura ({opening:.2f})"
                )
            # Il piano delle rate scadenzia il solo rateizzato: il saldo dell'anno
            # precedente si paga nel primo anno per definizione (spec §3.2).
            validate_runoff(rate, amounts, [], horizon, label)
            acconto_pct = plan.get('acconto_pct')
            out[key] = {
                "opening": opening, "saldo": saldo, "rateizzato": rate, "amounts": amounts,
                "writeoff": [],
                "acconto_pct": Decimal(str(acconto_pct)) if acconto_pct is not None else Decimal('100'),
            }
        else:
            validate_runoff(opening, amounts, writeoff, horizon, label)
            out[key] = {"opening": opening, "amounts": amounts, "writeoff": writeoff}
    return out


class ForecastEngine:
    """
    Calculates forecasted financial statements based on budget assumptions
    """

    def __init__(self, db_session: Session):
        self.db = db_session

    @staticmethod
    def _read_bs(bs, field: str) -> Decimal:
        """Un campo dello SP precedente, ORM o `_DictView` che sia (assente = 0)."""
        if bs is None:
            return Decimal('0')
        value = getattr(bs, field, None)
        return Decimal(str(value)) if value is not None else Decimal('0')

    @staticmethod
    def _quantize_values(values: Dict) -> Dict:
        """Round projected accounting rows to the database's two-cent scale."""
        cent = Decimal("0.01")
        return {
            field: Decimal(str(value or 0)).quantize(
                cent, rounding=ROUND_HALF_UP
            )
            for field, value in values.items()
        }

    # I due gruppi CE la cui identita' aggregato/dettagli va tenuta esatta al
    # centesimo. L'ordine e' quello di stampa, ed e' anche l'ordine in cui si
    # cerca il dettaglio su cui posare il residuo (dall'ultimo al primo).
    _CE_RESIDUAL_GROUPS: Dict[str, Tuple[str, ...]] = {
        "ce08_costi_personale": (
            "ce08a_tfr_accrual",
            "ce08b_salari_stipendi",
            "ce08c_oneri_sociali",
            "ce08d_altri_costi_personale",
        ),
        "ce09_ammortamenti": (
            "ce09a_ammort_immateriali",
            "ce09b_ammort_materiali",
            "ce09c_svalutazioni",
            "ce09d_svalutazione_crediti",
        ),
    }

    # L'attributo `*_override` di BudgetAssumptions che forza ciascuna riga dei
    # due gruppi sopra, aggregati compresi — solo quelli che partecipano a un
    # gruppo residuo: gli altri override (ce01, ce05, ...) non servono qui.
    _CE_RESIDUAL_OVERRIDE_ATTRS: Dict[str, str] = {
        "ce08_override": "ce08_costi_personale",
        "ce08a_override": "ce08a_tfr_accrual",
        "ce08b_override": "ce08b_salari_stipendi",
        "ce08c_override": "ce08c_oneri_sociali",
        "ce08d_override": "ce08d_altri_costi_personale",
        "ce09_override": "ce09_ammortamenti",
        "ce09a_override": "ce09a_ammort_immateriali",
        "ce09b_override": "ce09b_ammort_materiali",
        "ce09c_override": "ce09c_svalutazioni",
        "ce09d_override": "ce09d_svalutazione_crediti",
    }

    @classmethod
    def _forced_ce_residual_fields(cls, assumption: BudgetAssumptions) -> "frozenset[str]":
        """I nomi di riga dei due gruppi CE che questa ipotesi forza esplicitamente."""
        return frozenset(
            field
            for attr, field in cls._CE_RESIDUAL_OVERRIDE_ATTRS.items()
            if getattr(assumption, attr, None) is not None
        )

    # Gli attributi `*_override` che impediscono al motore di rilevare in CE il
    # costo dell'inesigibile: `ce09d` perche' e' la riga stessa, `ce09` perche' e'
    # l'aggregato che entra nel risultato d'esercizio.
    _WRITEOFF_BLOCKING_OVERRIDES = ("ce09d_override", "ce09_override")

    @classmethod
    def _suppress_unrecordable_writeoffs(cls, pregresso, assumptions) -> None:
        """L'inesigibile esce dallo SP solo se il costo entra nel CE.

        Un `ce09d_override` (la riga) o un `ce09_override` (l'aggregato che fa il
        risultato) vincono sul motore, come ogni override di questo motore — ma
        allora la svalutazione **non e' rilevata**, e scaricare lo stesso il credito
        dallo stato patrimoniale farebbe sparire un attivo senza contropartita:
        il plug di cassa lo rimpiazzerebbe euro per euro, il foglio quadrerebbe al
        centesimo e la ricchezza sarebbe inventata (misurato: 5.000 di credito
        diventavano 5.000 di cassa). Non e' un divario da tappare, e' massa da non
        creare.

        Quindi l'override vince due volte: tiene la sua riga di CE **e** lascia il
        credito a bilancio. La lista `writeoff` del piano viene azzerata in
        quell'anno — e' l'unica che il motore usa da qui in poi, quindi il residuo
        resta piu' alto per tutti gli anni successivi, non solo per questo — e
        l'importo chiesto e' conservato per essere **dichiarato** nei `details`:
        mai taciuto, come `override_conflicts` per il conto economico.
        """
        plan = (pregresso or {}).get("crediti_commerciali")
        if not plan or not plan.get("writeoff"):
            return
        effective: List[Decimal] = []
        ignored: Dict[int, Dict[str, Any]] = {}
        for index, requested in enumerate(plan["writeoff"]):
            assumption = assumptions[index] if index < len(assumptions) else None
            blocking = next(
                (attr for attr in cls._WRITEOFF_BLOCKING_OVERRIDES
                 if assumption is not None and getattr(assumption, attr, None) is not None),
                None,
            )
            if blocking is not None and requested > 0:
                effective.append(Decimal('0'))
                ignored[index] = {"requested": requested, "reason": blocking}
            else:
                effective.append(requested)
        plan["writeoff"] = effective
        plan["writeoff_ignored"] = ignored

    @staticmethod
    def _pregresso_writeoff(pregresso, year_index: int) -> Decimal:
        """L'inesigibile del piano dei crediti per l'anno `year_index` (0 se non c'e')."""
        plan = (pregresso or {}).get("crediti_commerciali")
        if not plan:
            return Decimal('0')
        writeoff = plan.get("writeoff") or []
        return writeoff[year_index] if year_index < len(writeoff) else Decimal('0')

    @classmethod
    def _engine_forced_ce_fields(cls, pregresso, year_index: int) -> "frozenset[str]":
        """Le righe CE che il MOTORE ha scritto di proposito in questo anno.

        Valgono quanto un override dell'utente per `_normalize_income_statement_cents`:
        `ce09d_svalutazione_crediti` e' l'ultimo dettaglio del gruppo `ce09`, quindi
        senza questa dichiarazione il residuo di arrotondamento dell'aggregato ci
        finirebbe sopra e l'inesigibile scadenziato risulterebbe di un centesimo
        diverso da quello chiesto. Un anno senza inesigibile non forza nulla:
        `ce09d` torna a essere il dettaglio di chiusura, come prima del lotto.
        """
        if cls._pregresso_writeoff(pregresso, year_index) > 0:
            return frozenset({"ce09d_svalutazione_crediti"})
        return frozenset()

    @classmethod
    def _normalize_income_statement_cents(
        cls,
        values: Dict,
        *,
        forced_fields: "frozenset[str]" = frozenset(),
        details: Optional[Dict] = None,
    ) -> Dict:
        """Keep CE aggregate/detail identities exact after cent rounding.

        Il residuo (aggregato quantizzato meno somma dei dettagli quantizzati)
        si posa sull'ultimo dettaglio del gruppo che **non** porta un override
        esplicito — mai su uno che l'utente (o il motore, per `ce09d`) ha
        scritto: posarcelo comunque lo cancellerebbe subito dopo che e' stato
        onorato (Task 11, scadenziamento pregresso — misurato: senza questa
        guardia un `ce08d_override=7000` con l'aggregato piu' alto diventa
        113.777,78 sulla riga persistita, e un `ce09d_override` pulito prende
        un centesimo di residuo di arrotondamento che non gli appartiene).

        `forced_fields` sono i nomi di riga (non gli attributi `*_override`)
        che l'ipotesi ha forzato esplicitamente, aggregato compreso. Il
        chiamante infrannuale non lo passa: default vuoto, comportamento
        identico a prima di questo task.

        Se **tutti** i dettagli di un gruppo sono forzati e l'aggregato non lo
        e', l'aggregato viene ricalcolato come loro somma — sono la fonte piu'
        specifica. Se anche l'aggregato e' forzato e diverge dalla somma dei
        dettagli, vince l'aggregato (com'era prima), il residuo va comunque
        sull'ultimo dettaglio libero (o su quello di chiusura se sono forzati
        tutti), e il conflitto e' **dichiarato**, mai taciuto, in
        `details['override_conflicts']` — una lista di `{"aggregate",
        "declared", "details_sum"}`, sempre presente quando `details` e'
        passato, anche vuota: una chiave assente varrebbe zero a valle.
        """
        result = cls._quantize_values(values)
        conflicts: List[Dict[str, Any]] = []
        for aggregate, group_fields in cls._CE_RESIDUAL_GROUPS.items():
            if aggregate not in result or not all(field in result for field in group_fields):
                continue
            details_sum = sum((result[field] for field in group_fields), Decimal("0"))
            aggregate_forced = aggregate in forced_fields
            all_details_forced = all(field in forced_fields for field in group_fields)

            if all_details_forced and not aggregate_forced:
                # I dettagli sono tutti espliciti: l'aggregato li segue, non il contrario.
                result[aggregate] = details_sum
                continue

            residual = result[aggregate] - details_sum
            if aggregate_forced and residual != 0:
                conflicts.append({
                    "aggregate": aggregate,
                    "declared": result[aggregate],
                    "details_sum": details_sum,
                })

            target = next(
                (field for field in reversed(group_fields) if field not in forced_fields),
                group_fields[-1],
            )
            result[target] += residual

        if details is not None:
            details['override_conflicts'] = conflicts

        # D) Rettifiche is a signed net family: aggregate = rivalutazioni -
        # svalutazioni.  Keep the stored rows exact when all three are present.
        if all(
            field in result
            for field in (
                "ce17_rettifiche_attivita_fin",
                "ce17a_rivalutazioni",
                "ce17b_svalutazioni",
            )
        ):
            result["ce17b_svalutazioni"] = (
                result["ce17a_rivalutazioni"]
                - result["ce17_rettifiche_attivita_fin"]
            )
        return result

    # I due campi di SP che ciascun piano di pregresso scrive di proposito (lato
    # breve, lato oltre). Servono a `_normalize_balance_sheet_cents`: sono valori
    # dichiarati nei `details`, e il residuo di quadratura non puo' riscriverli.
    _PREGRESSO_SP_FIELDS: Dict[str, Tuple[str, str]] = {
        "debiti_fornitori": ("sp16d_debiti_fornitori_breve", "sp17d_debiti_fornitori_lungo"),
        "debiti_tributari": ("sp16e_debiti_tributari_breve", "sp17e_debiti_tributari_lungo"),
        "debiti_previdenziali": ("sp16f_debiti_previdenza_breve", "sp17f_debiti_previdenza_lungo"),
        "altri_debiti": ("sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo"),
    }

    @classmethod
    def _declared_sp_fields(cls) -> "frozenset[str]":
        """I campi di SP il cui valore i `details` dichiarano SEMPRE.

        `details['pregresso'][k]` dichiara `generated + residual_short` sul lato
        breve e `residual_long` sul lato oltre di tutti e quattro i debiti, con o
        senza piano; `details['imposte']` dichiara per conto suo il tributario. Un
        centesimo di residuo di quadratura posato li' fa divergere il numero
        persistito da quello dichiarato — ed e' il difetto trovato CINQUE volte in
        questo file: sul conto economico (Task 11), sul patrimoniale (Task 5),
        sulle voci indicizzate e infine sui tributari, sempre da chi lo cercava.

        Il primo bersaglio del residuo resta il secchio di default `sp16g`/`sp17g`,
        e questo elenco entra in gioco **solo** quando quel secchio e' gia'
        forzato — cioe' sui percorsi con piano o con indicizzazione. Sui percorsi
        di sempre e' quindi inerte per costruzione, non per fortuna: e' cosi' che
        la parita' regge senza doverla sperare (misurato: con il secchio libero il
        residuo e' zero in tutte le osservazioni della sonda).
        """
        return frozenset(
            field for fields in cls._PREGRESSO_SP_FIELDS.values() for field in fields
        )

    @classmethod
    def _pregresso_sp_forced_fields(cls, pregresso) -> "frozenset[str]":
        """I campi di SP che un piano di pregresso ha scritto in questo scenario.

        `crediti_commerciali` non c'e': il piano scrive gli AGGREGATI `sp06`/`sp07`
        e i sotto-campi li ripartisce `_alloc` sulle proporzioni dell'anno base,
        quindi il residuo di quadratura non contraddice nulla di dichiarato.
        """
        return frozenset(
            field
            for key, fields in cls._PREGRESSO_SP_FIELDS.items()
            if (pregresso or {}).get(key)
            for field in fields
        )

    # ── INDICIZZAZIONE: i tre fattori, e chi resta fuori ──

    @classmethod
    def _sp_indexing_factors(cls, base_inc, forecast_inc) -> Dict[str, Optional[Decimal]]:
        """I tre driver di volume: previsto / anno base. `None` = degenere.

        Un denominatore a zero NON produce un fattore inventato: produce
        degenerazione, e chi la incontra ricade su «costante» dichiarandolo.
        Per questo i denominatori si rileggono qui invece di riusare
        `base_revenue` / `base_purchases` del calcolatore, che portano un
        `or D('1')` di comodo per la rotazione: quel fallback trasformerebbe
        uno zero in un fattore di 600.000, e nessun controllo lo vedrebbe.
        """
        zero = Decimal("0")

        def _b(field: str) -> Decimal:
            return getattr(base_inc, field, zero) or zero

        def _f(field: str) -> Decimal:
            return forecast_inc.get(field, zero) or zero

        pairs = {
            "ricavi": (_f("ce01_ricavi_vendite"), _b("ce01_ricavi_vendite")),
            "acquisti": (
                _f("ce05_materie_prime") + _f("ce06_servizi"),
                _b("ce05_materie_prime") + _b("ce06_servizi"),
            ),
            "personale": (_f("ce08_costi_personale"), _b("ce08_costi_personale")),
        }
        return {
            name: (num / den if den > zero else None)
            for name, (num, den) in pairs.items()
        }

    @classmethod
    def _resolve_sp_indexing(
        cls, assumption, base_inc, forecast_inc, pregresso,
    ) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, str]]]:
        """Che cosa e' indicizzato in questo anno, e che cosa e' stato ignorato.

        Restituisce `(applicate, ignorate)`. Le prime mappano il codice della
        voce al driver e al fattore applicato; le seconde dicono, voce per voce,
        PERCHE' la chiave non ha avuto effetto. Entrambe finiscono nei `details`
        di ogni anno, anche vuote: a valle una chiave assente vale zero, quindi
        tacere equivarrebbe a dichiararsi puliti.

        Nessuna chiave alza mai un errore: una voce che non si puo' indicizzare
        e' un'ipotesi che non si applica, non un piano che si ferma. Il rifiuto
        secco dei driver inesistenti sta nello schema Pydantic, dove il client
        riceve un 422 che dice quale nome ha sbagliato.
        """
        raw = getattr(assumption, "sp_indexing", None)
        applied: Dict[str, Dict[str, Any]] = {}
        ignored: List[Dict[str, str]] = []
        if not isinstance(raw, dict) or not raw:
            return applied, ignored
        factors = cls._sp_indexing_factors(base_inc, forecast_inc)
        previdenza_switch = bool(getattr(assumption, "previdenza_scales_with_personnel", False))
        # Ordine per codice: i `details` sono una dichiarazione, e una
        # dichiarazione che cambia ordine a ogni esecuzione non e' confrontabile.
        for code in sorted(raw):
            driver = raw[code]

            def _skip(motivo: str) -> None:
                ignored.append({"voce": code, "driver": driver, "motivo": motivo})

            if driver not in SP_INDEXING_DRIVERS:
                _skip("driver sconosciuto")
            elif code in SP_INDEXING_GOVERNED:
                _skip(SP_INDEXING_GOVERNED[code])
            elif code not in SP_INDEXABLE_FIELDS:
                _skip("voce non indicizzabile")
            elif previdenza_switch and code in ("sp16f", "sp17f"):
                # L'interruttore E' gia' l'indicizzazione di queste due voci al
                # costo del personale: vince lui, cosi' gli scenari che lo usano
                # non cambiano di un centesimo.
                _skip("governata dall'interruttore previdenza/personale")
            elif (pregresso or {}).get(SP_INDEXING_PLAN_KEY.get(code, "")):
                _skip("piano di scadenziamento")
            elif factors.get(driver) is None:
                _skip("driver degenere")
            else:
                applied[code] = {
                    "driver": driver,
                    "fattore": factors[driver],
                    # Un driver e una percentuale sulla stessa voce sono due
                    # affermazioni diverse: vince il driver. Dichiararlo evita
                    # una casella che accetta un numero senza alcun effetto.
                    "percentuale_ignorata": (
                        getattr(assumption, f"{code}_growth_pct", None) is not None
                    ),
                }
        return applied, ignored

    @classmethod
    def _indexed_sp_forced_fields(cls, details) -> "frozenset[str]":
        """I campi che l'indicizzazione ha scritto di proposito in questo anno.

        `sp16g`/`sp17g` sono anche i secchi di default in cui
        `_normalize_balance_sheet_cents` posa il residuo di quadratura di
        `sp16`/`sp17`: senza questa dichiarazione il numero persistito
        divergerebbe di un centesimo dal `base × fattore` che i `details`
        dichiarano — lo stesso difetto che il Task 11 ha chiuso sul conto
        economico e il Task 5 sul patrimoniale, qui sulla terza famiglia di
        campi dichiarati. Gli altri codici sono aggregati o dettagli che non
        fanno mai da secchio: elencarli e' inerte, ed e' preferibile a un elenco
        che va tenuto d'accordo a mano con i gruppi della normalizzazione.
        """
        return frozenset(
            SP_INDEXABLE_FIELDS[code]
            for code in ((details or {}).get("indicizzazione") or {})
            if code in SP_INDEXABLE_FIELDS
        )

    @classmethod
    def _normalize_balance_sheet_cents(
        cls, values: Dict, *, recompute_cash: bool = True,
        forced_fields: "frozenset[str]" = frozenset(),
        details: Optional[Dict[str, Any]] = None,
        overdraft: "Optional[_Overdraft]" = None,
    ) -> Dict:
        """Make persisted SP hierarchy and Attivo/Passivo exact to the cent.

        The engine calculates with higher precision while the ORM stores Numeric(15,2).
        Rounding every row independently could leave a one-cent mismatch in later
        forecast years.  Absorb only those rounding residuals in the generic detail
        bucket, then recompute cash from the rounded aggregate rows.

        `recompute_cash=False` keeps the first two steps and drops the third.  It
        exists for the intra-year engine, whose cash plug clamps at zero and
        raises `unfunded_financing_requirement` rather than creating short-term
        debt: recomputing sp09 as Sigma passivo - Sigma attivo would put the
        negative residual straight back and undo that clamp.  Quantization and
        residual absorption have nothing to do with the clamp, so they must keep
        running — a record whose sub-fields do not sum to their own aggregate is
        read downstream (`reconcileSubfields`, the anti-regression guard of
        `PUT /adjustments`) and starts out disadvantaged against a guard that is
        relative, not absolute.

        `forced_fields` sono i campi che il motore ha scritto di proposito e ha
        gia' DICHIARATO altrove (oggi: i lati breve/oltre di un saldo con piano di
        pregresso). Il residuo non si posa su di loro — e' la stessa cura che il
        Task 11 ha applicato al conto economico, qui sul patrimoniale: i secchi di
        default di `sp16`/`sp17` sono `sp16g`/`sp17g`, cioe' **esattamente** i campi
        che il piano `altri_debiti` scrive, e un centesimo di residuo li faceva
        divergere dal numero dichiarato nei `details` (misurato: `sp17g` persistito
        12.048,41 contro 12.048,40 dichiarato). Se sono forzati, il residuo va
        sull'ultimo campo libero del gruppo; se lo sono tutti, resta sul secchio di
        default — un centesimo va pur posato da qualche parte. Il chiamante
        infrannuale non lo passa: default vuoto, stesso comportamento di sempre.
        """
        result = cls._quantize_values(values)
        groups = {
            "sp01_crediti_soci": (
                ("sp01a_parte_richiamata", "sp01b_parte_da_richiamare"),
                "sp01b_parte_da_richiamare",
            ),
            "sp02_immob_immateriali": (
                (
                    "sp02a_costi_impianto", "sp02b_costi_sviluppo",
                    "sp02c_brevetti", "sp02d_concessioni", "sp02e_avviamento",
                    "sp02f_immob_in_corso", "sp02g_altre_immob_imm",
                ),
                "sp02g_altre_immob_imm",
            ),
            "sp03_immob_materiali": (
                (
                    "sp03a_terreni_fabbricati", "sp03b_impianti_macchinari",
                    "sp03c_attrezzature", "sp03d_altri_beni",
                    "sp03e_immob_in_corso",
                ),
                "sp03d_altri_beni",
            ),
            "sp04_immob_finanziarie": (
                (
                    "sp04a_partecipazioni", "sp04b_crediti_immob_breve",
                    "sp04c_crediti_immob_lungo", "sp04d_altri_titoli",
                    "sp04e_strumenti_derivati_attivi",
                ),
                "sp04d_altri_titoli",
            ),
            "sp05_rimanenze": (
                (
                    "sp05a_materie_prime", "sp05b_prodotti_in_corso",
                    "sp05c_lavori_in_corso", "sp05d_prodotti_finiti",
                    "sp05e_acconti",
                ),
                "sp05e_acconti",
            ),
            "sp06_crediti_breve": (
                (
                    "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
                    "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
                    "sp06e_crediti_tributari_breve", "sp06f_imposte_anticipate_breve",
                    "sp06g_crediti_altri_breve",
                ),
                "sp06g_crediti_altri_breve",
            ),
            "sp07_crediti_lungo": (
                (
                    "sp07a_crediti_clienti_lungo", "sp07b_crediti_controllate_lungo",
                    "sp07c_crediti_collegate_lungo", "sp07d_crediti_controllanti_lungo",
                    "sp07e_crediti_tributari_lungo", "sp07f_imposte_anticipate_lungo",
                    "sp07g_crediti_altri_lungo",
                ),
                "sp07g_crediti_altri_lungo",
            ),
            "sp12_riserve": (
                (
                    "sp12a_riserva_sovrapprezzo", "sp12b_riserve_rivalutazione",
                    "sp12c_riserva_legale", "sp12d_riserve_statutarie",
                    "sp12e_altre_riserve", "sp12f_riserva_copertura_flussi",
                    "sp12g_utili_perdite_portati", "sp12h_riserva_neg_azioni_proprie",
                ),
                "sp12g_utili_perdite_portati",
            ),
            "sp14_fondi_rischi": (
                (
                    "sp14a_fondi_trattamento_quiescenza", "sp14b_fondi_imposte",
                    "sp14c_strumenti_derivati_passivi", "sp14d_altri_fondi",
                ),
                "sp14d_altri_fondi",
            ),
            "sp16_debiti_breve": (
                (
                    "sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve",
                    "sp16c_debiti_obbligazioni_breve", "sp16d_debiti_fornitori_breve",
                    "sp16e_debiti_tributari_breve", "sp16f_debiti_previdenza_breve",
                    "sp16g_altri_debiti_breve",
                ),
                "sp16g_altri_debiti_breve",
            ),
            "sp17_debiti_lungo": (
                (
                    "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo",
                    "sp17c_debiti_obbligazioni_lungo", "sp17d_debiti_fornitori_lungo",
                    "sp17e_debiti_tributari_lungo", "sp17f_debiti_previdenza_lungo",
                    "sp17g_altri_debiti_lungo",
                ),
                "sp17g_altri_debiti_lungo",
            ),
        }
        # Dichiarato SEMPRE, anche vuoto: a valle una chiave assente vale zero.
        # Un centesimo che si sposta senza che nessuno lo dica e' esattamente il
        # modo in cui questo difetto e' rimasto invisibile cinque volte.
        posati: List[Dict[str, Any]] = []
        if details is not None:
            details['residuo_quadratura'] = posati
        for aggregate, (group_fields, residual_field) in groups.items():
            if aggregate not in result or not all(field in result for field in group_fields):
                continue
            residual = result[aggregate] - sum(
                (result[field] for field in group_fields), Decimal("0")
            )
            target = residual_field
            if target in forced_fields:
                target = next(
                    (field for field in reversed(group_fields) if field not in forced_fields),
                    residual_field,
                )
            result[target] += residual
            if residual:
                posati.append({'campo': target, 'importo': residual})

        asset_fields_without_cash = (
            "sp01_crediti_soci", "sp02_immob_immateriali",
            "sp03_immob_materiali", "sp04_immob_finanziarie",
            "sp05_rimanenze", "sp06_crediti_breve", "sp07_crediti_lungo",
            "sp08_attivita_finanziarie", "sp10_ratei_risconti_attivi",
        )
        liability_fields = (
            "sp11_capitale", "sp12_riserve", "sp13_utile_perdita",
            "sp14_fondi_rischi", "sp15_tfr", "sp16_debiti_breve",
            "sp17_debiti_lungo", "sp18_ratei_risconti_passivi",
        )
        if recompute_cash and all(
            field in result for field in asset_fields_without_cash + liability_fields
        ):
            cassa = sum(
                (result[field] for field in liability_fields), Decimal("0")
            ) - sum(
                (result[field] for field in asset_fields_without_cash), Decimal("0")
            )
            # E' l'ULTIMA scrittura sulla cassa di tutto il motore, quindi e'
            # l'ultimo punto in cui un numero impossibile puo' passare: prima di
            # questa riga il ricalcolo scavalcava il clamp di `_apply_sp_overrides`
            # e persisteva una cassa negativa sotto un messaggio di successo
            # (spec §11.1). Qui il residuo e' ormai al centesimo — i due cancelli
            # a monte hanno gia' coperto il fabbisogno vero — ma «piccolo» non e'
            # una ragione per lasciarlo passare: o lo copre lo scoperto concesso,
            # o il motore alza. Il chiamante infrannuale non passa di qui
            # (`recompute_cash=False`).
            if cassa < 0 and overdraft is not None:
                fabbisogno = -cassa
                overdraft.copri(fabbisogno)
                result["sp16a_debiti_banche_breve"] = (
                    result.get("sp16a_debiti_banche_breve", Decimal("0")) + fabbisogno
                )
                result["sp16_debiti_breve"] = (
                    result.get("sp16_debiti_breve", Decimal("0")) + fabbisogno
                )
                cassa = Decimal("0")
            result["sp09_disponibilita_liquide"] = cassa
        return result

    @staticmethod
    def _get_total_investments(assumption) -> Decimal:
        """Get total investments from split fields or legacy field."""
        intangible = getattr(assumption, 'intangible_investments', None) or Decimal('0')
        tangible = getattr(assumption, 'tangible_investments', None) or Decimal('0')
        if intangible > 0 or tangible > 0:
            return intangible + tangible
        return assumption.investments if assumption.investments else Decimal('0')

    @staticmethod
    def _get_split_investments(assumption):
        """Return (intangible, tangible) investment amounts."""
        intangible = getattr(assumption, 'intangible_investments', None) or Decimal('0')
        tangible = getattr(assumption, 'tangible_investments', None) or Decimal('0')
        if intangible > 0 or tangible > 0:
            return intangible, tangible
        # A total investment without an asset class cannot be depreciated or rolled
        # forward faithfully.  The former 50/50 fallback invented both classes.
        total = assumption.investments if assumption.investments else Decimal('0')
        if total:
            raise ValueError(
                "Investments must be split into intangible_investments and "
                "tangible_investments; automatic 50/50 allocation is disabled"
            )
        return Decimal('0'), Decimal('0')

    @staticmethod
    def _apply_sp_overrides(result: Dict, assumption, *, overdraft: "Optional[_Overdraft]" = None) -> Dict:
        """Apply absolute balance-sheet overrides and rebuild affected totals.

        Overrides target persisted forecast field names.  Detail edits win over
        their parent aggregate; cash remains the balancing item unless it was
        explicitly overridden by an API client.

        `overdraft` e' la concessione dello scoperto di c/c (`_Overdraft`), e
        governa il ri-plug della cassa: un override che squilibra il foglio non
        puo' chiudersi con un `max(0, ...)` che lascia il foglio sbilanciato —
        e' il difetto della spec §11.1, dove il clamp veniva poi scavalcato dal
        ricalcolo finale e la cassa finiva persistita a -4,8 milioni sotto un
        messaggio di successo. Assente (`None`) il clamp resta quello di sempre:
        e' il chiamante INFRANNUALE (`intra_year_engine`), il cui plug negativo
        va clampato a zero con la propria diagnostica e non alza mai.
        """
        raw_overrides = getattr(assumption, 'sp_overrides', None) or {}
        if not isinstance(raw_overrides, dict):
            return result

        applied = set()
        signed_fields = {'sp13_utile_perdita', 'sp12h_riserva_neg_azioni_proprie'}
        for field, raw_value in raw_overrides.items():
            if field not in result or raw_value is None:
                continue
            value = Decimal(str(raw_value))
            result[field] = value if field in signed_fields else max(Decimal('0'), value)
            applied.add(field)

        detail_groups = {
            'sp04_immob_finanziarie': (
                'sp04a_partecipazioni', 'sp04b_crediti_immob_breve',
                'sp04c_crediti_immob_lungo', 'sp04d_altri_titoli',
                'sp04e_strumenti_derivati_attivi',
            ),
            'sp05_rimanenze': (
                'sp05a_materie_prime', 'sp05b_prodotti_in_corso',
                'sp05c_lavori_in_corso', 'sp05d_prodotti_finiti', 'sp05e_acconti',
            ),
            'sp06_crediti_breve': (
                'sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
                'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
                'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
                'sp06g_crediti_altri_breve',
            ),
            'sp07_crediti_lungo': (
                'sp07a_crediti_clienti_lungo', 'sp07b_crediti_controllate_lungo',
                'sp07c_crediti_collegate_lungo', 'sp07d_crediti_controllanti_lungo',
                'sp07e_crediti_tributari_lungo', 'sp07f_imposte_anticipate_lungo',
                'sp07g_crediti_altri_lungo',
            ),
            'sp12_riserve': (
                'sp12a_riserva_sovrapprezzo', 'sp12b_riserve_rivalutazione',
                'sp12c_riserva_legale', 'sp12d_riserve_statutarie',
                'sp12e_altre_riserve', 'sp12f_riserva_copertura_flussi',
                'sp12g_utili_perdite_portati', 'sp12h_riserva_neg_azioni_proprie',
            ),
            'sp14_fondi_rischi': (
                'sp14a_fondi_trattamento_quiescenza', 'sp14b_fondi_imposte',
                'sp14c_strumenti_derivati_passivi', 'sp14d_altri_fondi',
            ),
            'sp16_debiti_breve': (
                'sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
                'sp16c_debiti_obbligazioni_breve', 'sp16d_debiti_fornitori_breve',
                'sp16e_debiti_tributari_breve', 'sp16f_debiti_previdenza_breve',
                'sp16g_altri_debiti_breve',
            ),
            'sp17_debiti_lungo': (
                'sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo',
                'sp17c_debiti_obbligazioni_lungo', 'sp17d_debiti_fornitori_lungo',
                'sp17e_debiti_tributari_lungo', 'sp17f_debiti_previdenza_lungo',
                'sp17g_altri_debiti_lungo',
            ),
        }
        for parent, details in detail_groups.items():
            if applied.intersection(details):
                result[parent] = sum((result.get(field, Decimal('0')) for field in details), Decimal('0'))

        if applied and 'sp09_disponibilita_liquide' not in applied:
            total_assets_no_cash = sum((
                result.get(field, Decimal('0')) for field in (
                    'sp01_crediti_soci', 'sp02_immob_immateriali',
                    'sp03_immob_materiali', 'sp04_immob_finanziarie',
                    'sp05_rimanenze', 'sp06_crediti_breve', 'sp07_crediti_lungo',
                    'sp08_attivita_finanziarie', 'sp10_ratei_risconti_attivi',
                )
            ), Decimal('0'))
            total_liabilities = sum((
                result.get(field, Decimal('0')) for field in (
                    'sp11_capitale', 'sp12_riserve', 'sp13_utile_perdita',
                    'sp14_fondi_rischi', 'sp15_tfr', 'sp16_debiti_breve',
                    'sp17_debiti_lungo', 'sp18_ratei_risconti_passivi',
                )
            ), Decimal('0'))
            saldo = total_liabilities - total_assets_no_cash
            if saldo < 0 and overdraft is not None:
                fabbisogno = -saldo
                overdraft.copri(fabbisogno)   # alza se non concesso, o oltre il tetto
                result['sp16a_debiti_banche_breve'] = (
                    result.get('sp16a_debiti_banche_breve', Decimal('0')) + fabbisogno
                )
                result['sp16_debiti_breve'] = (
                    result.get('sp16_debiti_breve', Decimal('0')) + fabbisogno
                )
                saldo = Decimal('0')
            result['sp09_disponibilita_liquide'] = max(Decimal('0'), saldo)
        return result

    def assemble_financing(self, assumptions, base_bs) -> Tuple[List[dict], bool]:
        """(financing_loans, use_detailed_existing_schedule) — alza ValueError
        su opening_residual fuori dal primo anno o residui != debito base.

        NEW financing raised during the plan: each assumption's financing_amount
        is a loan taken THAT year, amortised over its durata with interest on the
        residual (shared kernel `new_financing_schedule`). Assembled ONCE from all
        years because a single per-year assumption can't see a loan raised earlier
        that is still being repaid. Keeps the SP debt (sp17a) and the P&L oneri
        finanziari (ce15) in sync — the previous code added the debt but only
        charged interest in the year of erogazione.
        """
        financing_loans = []
        detailed_opening_total = Decimal('0')
        first_forecast_year = assumptions[0].forecast_year
        for a in assumptions:
            amt = a.financing_amount or Decimal('0')
            dur = a.financing_duration_years or Decimal('0')
            rate = (a.financing_interest_rate or Decimal('0')) / Decimal('100')
            if amt > 0 and dur > 0:
                financing_loans.append({
                    'year': a.forecast_year, 'amount': amt, 'duration': dur, 'rate': rate,
                })
            for loan in (getattr(a, 'financing_loans', None) or []):
                loan_amount = Decimal(str(loan.get('amount') or 0))
                opening_residual = Decimal(str(loan.get('opening_residual') or 0))
                loan_duration = Decimal(str(loan.get('duration_years') or 0))
                loan_rate = Decimal(str(loan.get('interest_rate') or 0)) / Decimal('100')
                if opening_residual > 0 and a.forecast_year != first_forecast_year:
                    raise ValueError(
                        "opening_residual is allowed only in the first forecast year"
                    )
                detailed_opening_total += opening_residual
                if (loan_amount > 0 or opening_residual > 0) and loan_duration > 0:
                    financing_loans.append({
                        'year': a.forecast_year,
                        'amount': loan_amount,
                        'opening_residual': opening_residual,
                        'duration': loan_duration,
                        'rate': loan_rate,
                        'grace_years': Decimal(str(loan.get('grace_years') or 0)),
                        'balloon_pct': Decimal(str(loan.get('balloon_pct') or 0)),
                    })

        use_detailed_existing_schedule = detailed_opening_total > 0
        if use_detailed_existing_schedule:
            getter = lambda field_name: getattr(base_bs, field_name, None) or Decimal('0')
            base_bank_total = base_bank_debt(getter)
            if abs(base_bank_total - detailed_opening_total) > Decimal('0.01'):
                raise ValueError(
                    "The sum of financing opening residuals must equal base-year "
                    f"bank debt ({detailed_opening_total} != {base_bank_total})"
                )
        return financing_loans, use_detailed_existing_schedule

    def compute_forecast(
        self,
        source: ForecastSource,
        assumptions: List[BudgetAssumptions],
        *,
        stop_on_error: bool = True,
    ) -> ForecastComputation:
        """Il ciclo di generate_forecast senza persistenza.

        Con `stop_on_error=False` l'errore del motore ferma il ciclo e resta in
        `error`, gli anni gia' calcolati in `years`; con `True` (default) alza
        come oggi, cosi' il percorso persistente non cambia comportamento.

        I sette `details` di ogni anno non stanno tutti alla stessa scala: le
        quattro quote di ce05/ce06 sono importi, e sono quantizzate al centesimo
        della riga che spiegano; `dso_applied`, `dio_applied` e `dpo_applied` sono
        giorni, e restano i `Decimal` grezzi che il motore ha applicato — arrotondarli
        direbbe che la rotazione usata e' un'altra. Chi li rende fianco a fianco
        formatti i giorni per conto proprio.
        """
        if not assumptions:
            raise ValueError(f"No assumptions found for scenario {source.scenario.id}")

        try:
            financing_loans, use_detailed = self.assemble_financing(assumptions, source.base_bs)
            # Lo scadenziamento del pregresso vive SOLO sulla riga del primo anno
            # di piano, come `financing_loans[].opening_residual`: e' una
            # fotografia dell'anno base, non un'ipotesi dell'anno N. Trovarlo
            # altrove significa che il client lo ha duplicato o spostato, e
            # applicarlo lo farebbe valere due volte.
            for extra in assumptions[1:]:
                if getattr(extra, 'pregresso', None):
                    raise ValueError(
                        "pregresso is allowed only in the first forecast year "
                        "(lo scadenziamento vale solo sulla riga del primo anno)"
                    )
            pregresso = validate_pregresso(
                getattr(assumptions[0], 'pregresso', None), source.base_bs, len(assumptions)
            )
            # Va fatto QUI e non nel calcolatore: sopprimere l'inesigibile di un
            # anno alza il residuo di tutti gli anni dopo, e il singolo anno non
            # vede gli override degli altri.
            self._suppress_unrecordable_writeoffs(pregresso, assumptions)
        except ValueError as e:
            if stop_on_error:
                raise
            return ForecastComputation(years=[], error=ForecastError(year=None, message=str(e)))

        results: List[ForecastYearResult] = []
        # Growth rates apply YEAR OVER YEAR: the first forecast year reads the
        # base year, every later one reads the year just computed.
        prev_inc = source.base_inc
        prev_bs = source.base_bs
        # I `details` dell'anno precedente viaggiano con l'anno: la posizione
        # tributaria a saldo + acconto paga in N il debito generato a fine N-1,
        # e quel numero sta li'. `None` sul primo anno di piano.
        prev_details: Optional[Dict[str, Any]] = None
        horizon = len(assumptions)
        for year_index, assumption in enumerate(assumptions):
            details: Dict[str, Any] = {}
            # La concessione dello scoperto vale per ANNO, come ogni altra
            # ipotesi, e porta con se' il saldo in essere all'apertura: e' quello
            # che l'anno precedente ha dichiarato, non una lettura di `sp16a` —
            # dentro `sp16a` c'e' anche il debito bancario PREGRESSO, ed e'
            # esattamente il confine che questo lotto esiste per tracciare.
            limite = getattr(assumption, 'overdraft_limit', None)
            overdraft = _Overdraft(
                allowed=bool(getattr(assumption, 'overdraft_allowed', False)),
                limit=Decimal(str(limite)) if limite is not None else None,
                opening=Decimal(str((prev_details or {}).get('scoperto_residuo') or 0)),
            )
            cassa_apertura = self._read_bs(prev_bs, 'sp09_disponibilita_liquide')
            try:
                forecast_inc = self._calculate_income_statement(
                    base_inc=source.base_inc,
                    assumption=assumption,
                    previous_inc=prev_inc,
                    previous_bs=prev_bs,
                    financing_loans=financing_loans,
                    pregresso=pregresso,
                    year_index=year_index,
                    details=details,
                    prev_details=prev_details,
                )
                forecast_inc = self._normalize_income_statement_cents(
                    forecast_inc,
                    forced_fields=(
                        self._forced_ce_residual_fields(assumption)
                        | self._engine_forced_ce_fields(pregresso, year_index)
                    ),
                    details=details,
                )
                forecast_bs = self._calculate_balance_sheet(
                    base_bs=source.base_bs,
                    base_inc=source.base_inc,
                    forecast_inc=forecast_inc,
                    assumption=assumption,
                    previous_bs=prev_bs,
                    year_offset=assumption.forecast_year - source.scenario.base_year,
                    financing_loans=financing_loans,
                    use_detailed_existing_schedule=use_detailed,
                    pregresso=pregresso,
                    year_index=year_index,
                    horizon=horizon,
                    prev_details=prev_details,
                    details=details,
                    overdraft=overdraft,
                )
                forecast_bs = self._normalize_balance_sheet_cents(
                    forecast_bs,
                    forced_fields=(
                        self._declared_sp_fields()
                        | self._pregresso_sp_forced_fields(pregresso)
                        | self._indexed_sp_forced_fields(details)
                        # `sp16a` e' dichiarato solo quando lo scoperto ci ha
                        # scritto: il residuo di quadratura non deve poterlo
                        # spostare di un centesimo sotto il numero che
                        # `details['scoperto_residuo']` afferma. Fuori da quel
                        # caso l'insieme resta identico a prima, quindi nessuno
                        # scenario di sempre cambia bersaglio.
                        | (frozenset({'sp16a_debiti_banche_breve'})
                           if overdraft.outstanding > Decimal('0') else frozenset())
                    ),
                    details=details,
                    overdraft=overdraft,
                )
            except ValueError as e:
                if stop_on_error:
                    raise
                self._declare_peak(results)
                return ForecastComputation(
                    years=results,
                    error=ForecastError(year=assumption.forecast_year, message=str(e)),
                )

            # I due addendi stanno alla scala del centesimo della riga che
            # riepilogano, e ci ricompongono esatti. Con un override restano
            # `None`: la scomposizione non esiste, e dichiararla direbbe il falso.
            for line, fixed_key, variable_key in (
                ('ce05_materie_prime', 'ce05_fixed', 'ce05_variable'),
                ('ce06_servizi', 'ce06_fixed', 'ce06_variable'),
            ):
                if details.get(fixed_key) is None:
                    continue
                details[fixed_key], details[variable_key] = _split_to_cents(
                    details[fixed_key], forecast_inc[line]
                )

            # ── CASSA E SCOPERTO: DICHIARATI SEMPRE, ANCHE A ZERO ──
            # A valle una chiave assente vale zero, quindi tacere equivale a
            # dichiararsi puliti. `cassa_assorbita` si dichiara anche quando la
            # cassa resta positiva: e' la cosa di cui l'utente va avvertito
            # PRIMA che diventi uno scoperto, non dopo. Si legge qui e non dentro
            # il calcolatore perche' la chiusura e' quella QUANTIZZATA — cioe' il
            # numero che verra' persistito, non uno vicino.
            cassa_chiusura = forecast_bs['sp09_disponibilita_liquide']
            details['cassa_assorbita'] = max(
                Decimal('0'), (cassa_apertura - cassa_chiusura)
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            details['scoperto_generato'] = overdraft.raised.quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            # Il residuo non puo' dichiarare piu' scoperto di quanto `sp16a`
            # ne porti scritto: un piano di rimborso del debito esistente puo'
            # aver eroso la voce, e dichiarare un saldo che il prospetto non
            # mostra e' il difetto «dichiarato != persistito» preso dall'altro
            # capo.
            details['scoperto_residuo'] = min(
                overdraft.outstanding.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                forecast_bs['sp16a_debiti_banche_breve'],
            )

            results.append(ForecastYearResult(
                year=assumption.forecast_year,
                income_statement=forecast_inc,
                balance_sheet=forecast_bs,
                details=details,
            ))
            prev_inc = _DictView(forecast_inc)
            prev_bs = _DictView(forecast_bs)
            prev_details = details

        self._declare_peak(results)
        return ForecastComputation(years=results)

    @staticmethod
    def _declare_peak(results: List[ForecastYearResult]) -> None:
        """Il fabbisogno di PICCO e l'anno in cui cade, scritti su OGNI anno.

        Non e' un numero d'anno, e' un numero di piano: la domanda che si porta
        in banca e' «quanta finanza richiedono queste ipotesi, e quando», e la
        risposta dev'essere leggibile da qualunque anno si stia guardando —
        l'anteprima del wizard mostra un anno alla volta.

        Dichiarato sempre, anche a zero; `fabbisogno_picco_anno` resta `None`
        senza scoperto, perche' uno zero li' sarebbe un anno, cioe' un'affermazione
        falsa invece di un'assenza. Sul percorso interrotto (`stop_on_error=False`)
        il picco copre gli anni CALCOLATI, che sono quelli che l'anteprima rende.
        """
        zero = Decimal('0')
        saldi = [(r, r.details.get('scoperto_residuo') or zero) for r in results]
        picco = max((s for _, s in saldi), default=zero)
        anno = next((r.year for r, s in saldi if s == picco), None) if picco > zero else None
        for result in results:
            result.details['fabbisogno_picco'] = picco
            result.details['fabbisogno_picco_anno'] = anno

    def generate_forecast(self, scenario_id: int) -> Dict:
        """
        Generate complete forecast for a budget scenario

        Args:
            scenario_id: Budget scenario ID

        Returns:
            Dictionary with forecast results and statistics
        """
        source = load_forecast_source(self.db, scenario_id)

        # Get all assumptions for this scenario
        assumptions = self.db.query(BudgetAssumptions).filter(
            BudgetAssumptions.scenario_id == scenario_id
        ).order_by(BudgetAssumptions.forecast_year).all()

        if not assumptions:
            raise ValueError(f"No assumptions found for scenario {scenario_id}")

        # Un orizzonte accorciato non deve lasciare anni fantasma: il ciclo qui
        # sotto fa l'upsert dei soli anni che hanno un'ipotesi.
        prune_out_of_plan_forecast_years(
            self.db, scenario_id, [a.forecast_year for a in assumptions]
        )

        computation = self.compute_forecast(source, assumptions, stop_on_error=True)

        forecast_years = []
        for result in computation.years:
            # Get or create forecast year
            fy = self.db.query(ForecastYear).filter(
                ForecastYear.scenario_id == scenario_id,
                ForecastYear.year == result.year
            ).first()

            if not fy:
                fy = ForecastYear(
                    scenario_id=scenario_id,
                    year=result.year
                )
                self.db.add(fy)
                self.db.flush()
            else:
                # `updated_at` e' la data della generazione, e /analysis la
                # confronta con quella delle ipotesi per dichiarare stantio un
                # previsionale piu' vecchio di cio' che dovrebbe riflettere.
                # Su un anno gia' esistente questo ciclo scrive solo sui FIGLI
                # (BS e IS): la riga `ForecastYear` non cambia, quindi
                # l'`onupdate` della colonna NON scatta. Misurato: senza questa
                # riga `updated_at` resta al microsecondo della PRIMA
                # generazione, e ogni rigenerazione riuscita successiva si
                # dichiarerebbe stantia pur essendo allineata.
                fy.updated_at = datetime.utcnow()

            # Save or update forecast balance sheet
            existing_bs = self.db.query(ForecastBalanceSheet).filter(
                ForecastBalanceSheet.forecast_year_id == fy.id
            ).first()

            if existing_bs:
                # Update existing
                for field_name, value in result.balance_sheet.items():
                    setattr(existing_bs, field_name, value)
            else:
                # Create new
                new_bs = ForecastBalanceSheet(forecast_year_id=fy.id, **result.balance_sheet)
                self.db.add(new_bs)
                self.db.flush()
                existing_bs = new_bs

            # Save or update forecast income statement
            existing_inc = self.db.query(ForecastIncomeStatement).filter(
                ForecastIncomeStatement.forecast_year_id == fy.id
            ).first()

            if existing_inc:
                # Update existing
                for field_name, value in result.income_statement.items():
                    setattr(existing_inc, field_name, value)
            else:
                # Create new
                new_inc = ForecastIncomeStatement(forecast_year_id=fy.id, **result.income_statement)
                self.db.add(new_inc)
                self.db.flush()
                existing_inc = new_inc

            forecast_years.append({
                'year': result.year,
                'forecast_year_obj': fy,
                'balance_sheet': existing_bs,
                'income_statement': existing_inc
            })

        # Commit all changes
        self.db.commit()

        return {
            'success': True,
            'scenario_id': scenario_id,
            'scenario_name': source.scenario.name,
            'base_year': source.scenario.base_year,
            'forecast_years': [fy['year'] for fy in forecast_years],
            'years_generated': len(forecast_years)
        }

    @staticmethod
    def _pbt_from_income(inc) -> Decimal:
        """Pre-tax profit through the canonical CE algebra."""
        return calculate_ce_result(inc).profit_before_tax

    @classmethod
    def _tax_components(cls, base_inc, projected_inc, assumption):
        """Return current tax, deferred-tax position and total P&L tax.

        Current tax is kept separate from deferred tax because only the former
        participates in the tax-credit/tax-debt settlement.  An explicit CE20
        override is interpreted as total tax expense and remains authoritative.
        """
        zero = Decimal('0')
        deferred = deferred_tax_position(
            getattr(assumption, 'tax_temporary_differences', None),
            assumption.tax_rate,
        )
        if assumption.ce20_override is not None:
            total_tax = Decimal(str(assumption.ce20_override))
            current_tax = max(zero, total_tax - deferred['deferred_expense'])
            return current_tax, deferred, total_tax

        profit_before_tax = calculate_ce_result(projected_inc).profit_before_tax
        base_pbt = cls._pbt_from_income(base_inc)
        base_tax = getattr(base_inc, 'ce20_imposte', None) or zero
        effective_rate = None
        if base_tax > 0 and base_pbt > 0:
            effective_rate = base_tax / base_pbt
            if effective_rate <= 0 or effective_rate > Decimal('0.6'):
                effective_rate = None
        rate = (
            effective_rate
            if effective_rate is not None
            else Decimal(str(assumption.tax_rate)) / Decimal('100')
        )
        current_tax = max(zero, profit_before_tax * rate)
        total_tax = max(zero, current_tax + deferred['deferred_expense'])
        return current_tax, deferred, total_tax

    def _calculate_income_statement(
        self,
        base_inc: IncomeStatement,
        assumption: BudgetAssumptions,
        previous_inc,
        previous_bs=None,
        financing_loans=None,
        pregresso=None,
        year_index: int = 0,
        details=None,
        prev_details=None,
    ) -> Dict:
        """
        Calculate forecasted income statement based on assumptions

        `details`, se passato, riceve la scomposizione fisso/variabile di ce05 e
        ce06 (`None` su entrambe le quote quando la riga e' sotto override).

        `pregresso` e' lo scadenziamento gia' normalizzato (validate_pregresso):
        di questo prospetto riguarda solo l'inesigibile dei crediti dell'anno
        `year_index`, che e' una svalutazione crediti (ce09d).

        `prev_details` sono i `details` dell'anno precedente (`None` sul primo):
        di questo prospetto riguarda solo `scoperto_residuo`, il saldo su cui
        maturano gli oneri dello scoperto di c/c.
        """
        # Growth rates apply YEAR OVER YEAR: each forecast year grows from the
        # PREVIOUS year, not from the consuntivo base year. So +5/+5/+5 compounds
        # (100 → 105 → 110,25 → 115,76) instead of being flat vs base (105 each
        # year). For the first forecast year previous_inc IS base_inc, so nothing
        # changes there. Flat carry-forward lines (ce02/03/10/11/13-19) keep
        # reading base_inc — with no growth % the two are identical.
        def _pinc(field):
            v = getattr(previous_inc, field, None) if previous_inc is not None else None
            return v if v is not None else Decimal('0')

        # Apply growth rates to the previous year values (overrides take precedence)
        if assumption.ce01_override is not None:
            ce01 = assumption.ce01_override
        else:
            ce01 = _pinc('ce01_ricavi_vendite') * (Decimal('1') + assumption.revenue_growth_pct / Decimal('100'))
        if assumption.ce04_override is not None:
            ce04 = assumption.ce04_override
        else:
            ce04 = _pinc('ce04_altri_ricavi') * (Decimal('1') + assumption.other_revenue_growth_pct / Decimal('100'))

        # Calculate costs - split between variable and fixed components based on user-defined percentages

        # Materials
        if assumption.ce05_override is not None:
            ce05 = assumption.ce05_override
            # Un override sostituisce la riga intera: la scomposizione fisso/variabile
            # non esiste piu', e dichiararla a zero direbbe il falso.
            ce05_fixed_part = ce05_variable_part = None
        else:
            base_materials = _pinc('ce05_materie_prime')
            fixed_pct_materials = assumption.fixed_materials_percentage / Decimal('100')
            variable_pct_materials = Decimal('1') - fixed_pct_materials
            variable_materials = base_materials * variable_pct_materials
            fixed_materials = base_materials * fixed_pct_materials
            ce05_variable_part = variable_materials * (Decimal('1') + assumption.variable_materials_growth_pct / Decimal('100'))
            ce05_fixed_part = fixed_materials * (Decimal('1') + assumption.fixed_materials_growth_pct / Decimal('100'))
            ce05 = ce05_variable_part + ce05_fixed_part

        # Services
        if assumption.ce06_override is not None:
            ce06 = assumption.ce06_override
            ce06_fixed_part = ce06_variable_part = None
        else:
            base_services = _pinc('ce06_servizi')
            fixed_pct_services = assumption.fixed_services_percentage / Decimal('100')
            variable_pct_services = Decimal('1') - fixed_pct_services
            variable_services = base_services * variable_pct_services
            fixed_services = base_services * fixed_pct_services
            ce06_variable_part = variable_services * (Decimal('1') + assumption.variable_services_growth_pct / Decimal('100'))
            ce06_fixed_part = fixed_services * (Decimal('1') + assumption.fixed_services_growth_pct / Decimal('100'))
            ce06 = ce06_variable_part + ce06_fixed_part

        if details is not None:
            details['ce05_fixed'] = ce05_fixed_part
            details['ce05_variable'] = ce05_variable_part
            details['ce06_fixed'] = ce06_fixed_part
            details['ce06_variable'] = ce06_variable_part

        # Rent/Godimento beni
        if assumption.ce07_override is not None:
            ce07 = assumption.ce07_override
        else:
            ce07 = _pinc('ce07_godimento_beni') * (Decimal('1') + assumption.rent_growth_pct / Decimal('100'))

        # Personnel
        if assumption.ce08_override is not None:
            ce08 = assumption.ce08_override
        else:
            ce08 = _pinc('ce08_costi_personale') * (Decimal('1') + assumption.personnel_growth_pct / Decimal('100'))

        # Personnel sub-items — override or maintain same proportions as the previous year.
        # Salari/oneri scale with the personnel total; TFR (ce08a) is instead the statutory
        # accrual salari/13,5 (so the sp15 fund — which reads ce08a — grows every year even
        # when the base import only carried the aggregate personnel cost); ce08d absorbs the
        # remainder so the four sub-items still sum to the personnel total.
        prev_ce08 = _pinc('ce08_costi_personale')
        if prev_ce08 > 0:
            growth_factor = ce08 / prev_ce08
        else:
            growth_factor = Decimal('1')
        ce08b = assumption.ce08b_override if assumption.ce08b_override is not None else _pinc('ce08b_salari_stipendi') * growth_factor
        ce08c = assumption.ce08c_override if assumption.ce08c_override is not None else _pinc('ce08c_oneri_sociali') * growth_factor
        # Cap the derived TFR quota at the remainder left by salari+oneri so the four
        # sub-items never sum to more than the personnel total (an explicit override is
        # trusted as-is). ce08d then absorbs the exact remainder.
        ce08a = assumption.ce08a_override if assumption.ce08a_override is not None else min(tfr_accrual_quota(ce08b, ce08), max(Decimal('0'), ce08 - ce08b - ce08c))
        ce08d = assumption.ce08d_override if assumption.ce08d_override is not None else max(Decimal('0'), ce08 - ce08a - ce08b - ce08c)

        # Depreciation — override total or calculate from investments
        depreciation_rate_tangible = assumption.depreciation_rate / Decimal('100')
        depreciation_rate_intangible = (getattr(assumption, 'depreciation_rate_intangible', None) or assumption.depreciation_rate) / Decimal('100')
        intangible_inv, tangible_inv = self._get_split_investments(assumption)
        new_depr_intangible = intangible_inv * depreciation_rate_intangible if intangible_inv > 0 else Decimal('0')
        new_depr_tangible = tangible_inv * depreciation_rate_tangible if tangible_inv > 0 else Decimal('0')

        # Depreciation sub-items: override, else carry the PREVIOUS year's charge forward
        # (it already includes prior investments' depreciation) plus this year's new
        # investment depreciation — so a one-off investment keeps being depreciated in
        # later years instead of reverting to the base-year charge (#7). The charge is
        # then capped at the available net book value (previous NBV + this year's
        # investment) so depreciation stops once the asset is fully written down (#5).
        base_ce09a = getattr(base_inc, 'ce09a_ammort_immateriali', None) or Decimal('0')
        base_ce09b = getattr(base_inc, 'ce09b_ammort_materiali', None) or Decimal('0')
        base_ce09c = getattr(base_inc, 'ce09c_svalutazioni', None) or Decimal('0')
        base_ce09d = getattr(base_inc, 'ce09d_svalutazione_crediti', None) or Decimal('0')

        def _prev_inc_val(field, fallback):
            v = getattr(previous_inc, field, None) if previous_inc is not None else None
            return v if v is not None else fallback

        def _prev_bs_val(field):
            if previous_bs is None:
                return Decimal('0')
            if isinstance(previous_bs, dict):
                return previous_bs.get(field, Decimal('0')) or Decimal('0')
            return getattr(previous_bs, field, Decimal('0')) or Decimal('0')

        prev_ce09a = _prev_inc_val('ce09a_ammort_immateriali', base_ce09a)
        prev_ce09b = _prev_inc_val('ce09b_ammort_materiali', base_ce09b)
        avail_intangible = max(Decimal('0'), _prev_bs_val('sp02_immob_immateriali') + intangible_inv)
        avail_tangible = max(Decimal('0'), _prev_bs_val('sp03_immob_materiali') + tangible_inv)

        if assumption.ce09a_override is not None:
            ce09a = assumption.ce09a_override
        else:
            ce09a = min(prev_ce09a + new_depr_intangible, avail_intangible)
        if assumption.ce09b_override is not None:
            ce09b = assumption.ce09b_override
        else:
            ce09b = min(prev_ce09b + new_depr_tangible, avail_tangible)
        ce09c = assumption.ce09c_override if assumption.ce09c_override is not None else base_ce09c
        # L'inesigibile scadenziato e' una svalutazione crediti dell'anno: si somma
        # alla svalutazione dell'anno base, che resta il portato di sempre. Non
        # c'e' fondo svalutazione nel modello (sp14): si resta al netto, e la
        # riduzione del residuo la fa runoff_schedule sullo stato patrimoniale.
        ce09d = (
            assumption.ce09d_override if assumption.ce09d_override is not None
            else base_ce09d + self._pregresso_writeoff(pregresso, year_index)
        )

        # Total depreciation: override or sum of sub-items
        if assumption.ce09_override is not None:
            ce09 = assumption.ce09_override
        else:
            ce09 = ce09a + ce09b + ce09c + ce09d

        # Other costs
        if assumption.ce12_override is not None:
            ce12 = assumption.ce12_override
        else:
            ce12 = _pinc('ce12_oneri_diversi') * (Decimal('1') + assumption.other_costs_growth_pct / Decimal('100'))

        # Asset disposal (dismissione/vendita cespite): proceeds - net book value = gain/loss.
        # Post-2016 OIC: plusvalenza ordinaria → A.5 altri ricavi (ce04); minusvalenza → B.14
        # oneri diversi (ce12). The disposed asset's NBV is removed from sp03 in the balance
        # sheet and the sale proceeds flow in through the cash plug.
        disposal_nbv = getattr(assumption, 'asset_disposal_nbv', None) or Decimal('0')
        disposal_proceeds = getattr(assumption, 'asset_disposal_proceeds', None) or Decimal('0')
        if disposal_nbv > 0 or disposal_proceeds > 0:
            disposal_gain = disposal_proceeds - disposal_nbv
            if disposal_gain >= 0:
                ce04 = ce04 + disposal_gain
            else:
                ce12 = ce12 + (-disposal_gain)

        # CE line items: use override if set, otherwise fall back to base year
        ce02 = assumption.ce02_override if assumption.ce02_override is not None else base_inc.ce02_variazioni_rimanenze
        ce03 = assumption.ce03_override if assumption.ce03_override is not None else base_inc.ce03_lavori_interni
        # A.4 "Incrementi di immobilizzazioni per lavori interni" — carried as its own line.
        # Without this the engine silently dropped it from the production value (the client's
        # "380.423 che sparisce / non si azzera" issue) and it had no override.
        _base_ce03a = getattr(base_inc, 'ce03a_incrementi_immobilizzazioni', None) or Decimal('0')
        ce03a = assumption.ce03a_override if getattr(assumption, 'ce03a_override', None) is not None else _base_ce03a
        ce10 = assumption.ce10_override if assumption.ce10_override is not None else base_inc.ce10_var_rimanenze_mat_prime
        ce11 = assumption.ce11_override if assumption.ce11_override is not None else base_inc.ce11_accantonamenti
        ce11b = assumption.ce11b_override if assumption.ce11b_override is not None else base_inc.ce11b_altri_accantonamenti
        ce13 = assumption.ce13_override if assumption.ce13_override is not None else base_inc.ce13_proventi_partecipazioni
        ce16 = assumption.ce16_override if assumption.ce16_override is not None else base_inc.ce16_utili_perdite_cambi
        ce17a = assumption.ce17a_override if assumption.ce17a_override is not None else (getattr(base_inc, 'ce17a_rivalutazioni', None) or Decimal('0'))
        ce17b = assumption.ce17b_override if assumption.ce17b_override is not None else (getattr(base_inc, 'ce17b_svalutazioni', None) or Decimal('0'))
        ce17 = assumption.ce17_override if assumption.ce17_override is not None else (ce17a - ce17b)
        ce18 = assumption.ce18_override if assumption.ce18_override is not None else base_inc.ce18_proventi_straordinari
        ce19 = assumption.ce19_override if assumption.ce19_override is not None else base_inc.ce19_oneri_straordinari

        # Financial income/costs: use override if set, otherwise carry forward from base year
        ce14 = assumption.ce14_override if assumption.ce14_override is not None else base_inc.ce14_altri_proventi_finanziari
        ce15 = assumption.ce15_override if assumption.ce15_override is not None else base_inc.ce15_oneri_finanziari

        # Add interest on NEW financing raised during the plan. Charged on the
        # OUTSTANDING balance at the start of each year (shared kernel), so a loan
        # raised once keeps generating interest — decreasing as it amortises —
        # across every year it is on the balance sheet, not only in the year of
        # erogazione. Interest is 0 automatically once the loan is fully repaid or
        # when the rate is 0.
        _, _, financing_interest = new_financing_schedule(financing_loans, assumption.forecast_year)
        has_detailed_opening = any(
            Decimal(str(loan.get('opening_residual') or 0)) > 0
            for loan in (financing_loans or [])
        )
        # A detailed opening schedule replaces the historical aggregate interest
        # carry-forward; otherwise it would be charged twice.  CE15 override stays
        # the explicit escape hatch for ancillary bank charges.
        #
        # ── ONERI DELLO SCOPERTO DI C/C, SENZA CIRCOLARITA' ──
        # Maturano al `financing_interest_rate` gia' fra le ipotesi, su un saldo
        # NOTO prima che il CE si chiuda: lo scoperto in APERTURA d'anno, che
        # l'anno scorso ha dichiarato in `details['scoperto_residuo']`. Mai su
        # quello che l'anno stesso sta generando — quello lo produce il plug, che
        # gira dopo, e farvi maturare interessi vorrebbe dire che l'interesse
        # cambia la cassa che determina l'interesse. Il primo anno di piano non
        # ha apertura: zero, e lo si dichiara lo stesso.
        scoperto_apertura = Decimal(str((prev_details or {}).get('scoperto_residuo') or 0))
        tasso_scoperto = Decimal(str(getattr(assumption, 'financing_interest_rate', None) or 0))
        oneri_scoperto = (scoperto_apertura * tasso_scoperto / Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        if assumption.ce15_override is None:
            ce15 = financing_interest if has_detailed_opening else ce15 + financing_interest
            ce15 = ce15 + oneri_scoperto
        else:
            # Un override della riga vince su tutto, oneri dello scoperto
            # compresi: si dichiara quello che e' stato DAVVERO addebitato, cioe'
            # zero, perche' a valle il dichiarato deve coincidere col persistito.
            oneri_scoperto = Decimal('0')
        if details is not None:
            details['oneri_scoperto'] = oneri_scoperto

        # Taxes - use override if set, otherwise use tax rate
        ce_for_tax = {
            'ce01_ricavi_vendite': ce01, 'ce02_variazioni_rimanenze': ce02,
            'ce03_lavori_interni': ce03, 'ce03a_incrementi_immobilizzazioni': ce03a,
            'ce04_altri_ricavi': ce04, 'ce05_materie_prime': ce05,
            'ce06_servizi': ce06, 'ce07_godimento_beni': ce07,
            'ce08_costi_personale': ce08, 'ce09_ammortamenti': ce09,
            'ce10_var_rimanenze_mat_prime': ce10, 'ce11_accantonamenti': ce11,
            'ce11b_altri_accantonamenti': ce11b, 'ce12_oneri_diversi': ce12,
            'ce13_proventi_partecipazioni': ce13,
            'ce14_altri_proventi_finanziari': ce14,
            'ce15_oneri_finanziari': ce15, 'ce16_utili_perdite_cambi': ce16,
            'ce17_rettifiche_attivita_fin': ce17,
            'ce17a_rivalutazioni': ce17a, 'ce17b_svalutazioni': ce17b,
            'ce18_proventi_straordinari': ce18, 'ce19_oneri_straordinari': ce19,
            'ce20_imposte': Decimal('0'),
        }
        _, _, ce20 = self._tax_components(base_inc, ce_for_tax, assumption)

        return {
            'ce01_ricavi_vendite': ce01,
            'ce02_variazioni_rimanenze': ce02,
            'ce03_lavori_interni': ce03,
            'ce03a_incrementi_immobilizzazioni': ce03a,
            'ce04_altri_ricavi': ce04,
            'ce05_materie_prime': ce05,
            'ce06_servizi': ce06,
            'ce07_godimento_beni': ce07,
            'ce08_costi_personale': ce08,
            'ce08a_tfr_accrual': ce08a,
            'ce08b_salari_stipendi': ce08b,
            'ce08c_oneri_sociali': ce08c,
            'ce08d_altri_costi_personale': ce08d,
            'ce09_ammortamenti': ce09,
            'ce09a_ammort_immateriali': ce09a,
            'ce09b_ammort_materiali': ce09b,
            'ce09c_svalutazioni': ce09c,
            'ce09d_svalutazione_crediti': ce09d,
            'ce10_var_rimanenze_mat_prime': ce10,
            'ce11_accantonamenti': ce11,
            'ce11b_altri_accantonamenti': ce11b,
            'ce12_oneri_diversi': ce12,
            'ce13_proventi_partecipazioni': ce13,
            'ce14_altri_proventi_finanziari': ce14,
            'ce15_oneri_finanziari': ce15,
            'ce16_utili_perdite_cambi': ce16,
            'ce17_rettifiche_attivita_fin': ce17,
            'ce17a_rivalutazioni': ce17a,
            'ce17b_svalutazioni': ce17b,
            'ce18_proventi_straordinari': ce18,
            'ce19_oneri_straordinari': ce19,
            'ce20_imposte': ce20
        }

    def _calculate_balance_sheet(
        self,
        base_bs: BalanceSheet,
        base_inc: IncomeStatement,
        forecast_inc: Dict,
        assumption: BudgetAssumptions,
        previous_bs,
        year_offset: int = 1,
        financing_loans=None,
        use_detailed_existing_schedule: bool = False,
        pregresso=None,
        year_index: int = 0,
        horizon: int = 1,
        prev_details=None,
        details=None,
        overdraft: "Optional[_Overdraft]" = None,
    ) -> Dict:
        """
        Calculate forecasted balance sheet based on assumptions and forecast income statement.
        Builds debt detail bottom-up: financial debts from repayment schedule,
        trade payables from DPO, other operating debts carried forward.

        `details`, se passato, riceve i giorni di rotazione effettivamente
        applicati (`dso_applied`, `dio_applied`, `dpo_applied`) — quelli espliciti
        dell'ipotesi o quelli dedotti dall'anno base — l'elenco dei giorni DEDOTTI
        caduti nella guardia (`degenerate_turnover_ratio`, sempre presente, vuoto
        quando non scatta nulla) e lo stato del pregresso saldo per saldo
        (`pregresso`, `pregresso_ignored`, `imposte`).

        `pregresso` e' lo scadenziamento gia' normalizzato (validate_pregresso),
        `year_index` l'anno di piano (0 = il primo) e `horizon` quanti anni ha il
        piano: servono a runoff_schedule per dire quanto del pregresso resta
        aperto e quanto di quel residuo e' dovuto l'anno DOPO (quindi a breve).
        `prev_details` sono i `details` dell'anno precedente (`None` sul primo):
        oggi nessun ramo li legge — li usera' la posizione tributaria a saldo +
        acconto, che nell'anno N paga il debito generato a fine N-1.

        `overdraft` e' la concessione dello scoperto di c/c su questo anno
        (`_Overdraft`). Assente = non concesso, cioe' il comportamento di
        sempre: un plug negativo alza.
        """
        D = Decimal
        ZERO = D('0')
        DAYS = D('360')
        if overdraft is None:
            overdraft = _Overdraft()

        # Helper to read fields from previous_bs (could be ORM object or dict)
        def _prev(field, default=ZERO):
            if isinstance(previous_bs, dict):
                return previous_bs.get(field, default)
            return getattr(previous_bs, field, default) or default

        def _base(field, default=ZERO):
            return getattr(base_bs, field, default) or default

        def _base_inc(field, default=ZERO):
            # Il gemello di `_base` sul conto economico dell'anno base: la
            # posizione tributaria del primo anno di piano commisura l'acconto
            # sull'imposta del consuntivo, che sta li' e non nel patrimoniale.
            return getattr(base_inc, field, default) or default

        # ── ASSETS ──

        # Fixed assets - previous year + investments - depreciation
        ce09a = forecast_inc.get('ce09a_ammort_immateriali', ZERO)
        ce09b = forecast_inc.get('ce09b_ammort_materiali', ZERO)
        ce09c = forecast_inc.get('ce09c_svalutazioni', ZERO)

        intangible_inv, tangible_inv = self._get_split_investments(assumption)

        # Asset disposal: remove the disposed cespite's net book value from sp03 (tangible
        # fixed assets). The proceeds/gain are booked in the P&L; the cash plug brings in
        # the sale cash automatically, keeping the balance sheet balanced.
        disposal_nbv = getattr(assumption, 'asset_disposal_nbv', None) or ZERO
        sp02 = max(ZERO, _prev('sp02_immob_immateriali') + intangible_inv - ce09a)
        sp03 = max(ZERO, _prev('sp03_immob_materiali') + tangible_inv - ce09b - disposal_nbv)

        # Helper for SP growth % fields (nullable → 0% = carry forward)
        def _sp_growth(field_name):
            val = getattr(assumption, field_name, None)
            if val is None:
                return ZERO
            return D(str(val)) / D('100')

        # ── INDICIZZAZIONE DELLE VOCI MINORI A UN DRIVER DI VOLUME ──
        # Dichiarata SEMPRE, anche vuota: a valle una chiave assente vale zero.
        indicizzazione, indicizzazione_ignorata = self._resolve_sp_indexing(
            assumption, base_inc, forecast_inc, pregresso,
        )
        if details is not None:
            details['indicizzazione'] = indicizzazione
            details['indicizzazione_ignorata'] = indicizzazione_ignorata

        def _sp_scale(code, growth_field):
            """(ancora, fattore) di una voce minore.

            Indicizzata: `(_base, fattore del driver)` — lo stock dell'ANNO BASE
            per il fattore dell'anno, la stessa forma di `pers_factor`, che
            indicizza e non compone. Altrimenti `(_prev, 1 + %)`, cioe' la
            formula di sempre lettera per lettera: senza `sp_indexing` ogni
            numero resta identico al centesimo, ed e' la proprieta' su cui
            questo lotto si gioca.
            """
            entry = indicizzazione.get(code)
            if entry is None:
                return _prev, D('1') + _sp_growth(growth_field)
            return _base, entry['fattore']

        def _declare_indexed(code, valore):
            """Il valore che l'indicizzazione ha DAVVERO scritto sulla voce.

            Non e' ridondante con `fattore`: `sp04` sottrae le svalutazioni
            cumulate e `sp14` con differenze temporanee somma la quota del
            kernel del deferred, quindi `base × fattore` non basta a
            ricostruirlo. Dichiarare il valore rende il confronto «persistito ==
            dichiarato» esatto su tutte e undici le voci — ed e' quel confronto,
            non l'occhio di chi legge, che ha trovato il residuo di quadratura
            cinque volte in questo file.
            """
            if code in indicizzazione:
                indicizzazione[code]['valore'] = valore
            return valore

        # ── SVALUTAZIONI CUMULATE: quel che il CE ha gia' rilevato non torna ──
        # `ce09c` non e' una crescita mancata: e' massa che il conto economico ha
        # gia' rilevato e che non rientra. La formula a riporto la sottraeva una
        # volta per anno e il saldo scendeva davvero; un'ancora sull'anno base la
        # cancella ogni anno, perche' riparte sempre dallo stesso stock — misurato:
        # con `ce09c` da 10.000 e fattore 1,00 la serie 30.000 / 20.000 / 10.000
        # diventava 30.000 / 30.000 / 30.000, senza una diagnostica. Indicizzare
        # deve indicizzare la CRESCITA, non annullare una rettifica.
        #
        # Il cumulato viaggia nei `details` come ogni altro stato che attraversa
        # gli anni (la posizione tributaria fa lo stesso con `prev_details`), ed e'
        # dichiarato SEMPRE, anche a zero: cosi' un anno indicizzato in mezzo a
        # anni costanti trova comunque la somma giusta di tutte le svalutazioni
        # rilevate dall'anno base in poi.
        svalutazioni_cumulate = (
            ((prev_details or {}).get('svalutazioni_cumulate') or ZERO) + ce09c
        )
        if details is not None:
            details['svalutazioni_cumulate'] = svalutazioni_cumulate

        sp04_anchor, sp04_factor = _sp_scale('sp04', 'sp04_growth_pct')
        sp04 = _declare_indexed('sp04', max(
            ZERO,
            sp04_anchor('sp04_immob_finanziarie') * sp04_factor
            # A riporto la sottrazione e' gia' dentro `_prev`: togliere il
            # cumulato la conterebbe due volte. Sull'ancora dell'anno base no.
            - (svalutazioni_cumulate if 'sp04' in indicizzazione else ce09c),
        ))

        # Working capital via turnover days
        # When turnover days are not explicitly set, derive them from the base year
        # so that working capital scales proportionally with revenue/purchases.
        forecast_revenue = forecast_inc['ce01_ricavi_vendite']
        forecast_purchases = forecast_inc['ce05_materie_prime'] + forecast_inc['ce06_servizi']
        base_revenue = _base_inc('ce01_ricavi_vendite')
        base_purchases = _base_inc('ce05_materie_prime') + _base_inc('ce06_servizi')

        # ── GUARDIA SUI GIORNI MEDI DEDOTTI (Task 14) ──
        # Il denominatore di ripiego che stava qui (`or D('1')`) non era una
        # guardia: era un denominatore inventato, e su un'azienda che fattura su
        # `ce04` produceva giorni a scala astronomica senza che nulla protestasse.
        degenerate_days: List[str] = []
        if details is not None:
            # Dichiarata SEMPRE, anche vuota: a valle una chiave assente vale zero,
            # quindi tacere equivarrebbe a dichiararsi puliti. E' la lista viva, che
            # i tre blocchi qui sotto riempiono man mano.
            details['degenerate_turnover_ratio'] = degenerate_days

        def _derived_days(stock, flow_base, name):
            """I giorni dedotti dall'anno base, o `None` se DEGENERI.

            Giacenza nulla ⇒ zero giorni, e non c'e' nulla di degenere: qualunque
            denominatore, il saldo riportato e quello scalato valgono entrambi
            zero, e un avviso su una voce che non esiste sarebbe solo rumore.
            """
            if not stock:
                return ZERO
            if flow_base is None or flow_base <= 0:
                degenerate_days.append(name)
                return None
            days = stock / flow_base * DAYS
            if days < 0 or days > MAX_DERIVED_TURNOVER_DAYS:
                degenerate_days.append(name)
                return None
            return days

        def _effective_days(amount, flow):
            """Il giorno DAVVERO applicato quando il motore ha riportato uno stock.

            Nessun giorno e' stato usato come moltiplicatore: quello dichiarato e'
            quello che il saldo scritto vale sul flusso proiettato, cosi' che
            `saldo = flusso × giorni / 360` resti vera (e' l'identita' che i
            rilievi C1-C3 del banco di sensibilita' verificano). Flusso nullo ⇒
            nessun giorno lo descrive: zero, e la lista dice perche'.
            """
            return (amount / flow * DAYS) if flow > 0 else ZERO

        def _carry_unless_planned(stock, key):
            """Lo stock dell'anno base riportato — a meno che un piano lo governi.

            Un giorno degenere fa RIPORTARE uno stock invece di convertire un
            flusso, ed e' proprio la ragione per cui crediti e fornitori restano
            fuori da `_net_of_pregresso` (vedi la sua docstring piu' sotto: ne
            restano fuori *perche'* il loro generato converte un flusso) a venir
            meno. Lo stock riportato E' il pregresso: `validate_pregresso` impone
            che la massa dichiarata sia quella del bilancio base. Sommargli il
            residuo del piano conterebbe due volte la stessa massa, e il saldo
            non calerebbe mai per quanto il piano lo scadenzi.

            La regola e' quella gia' scritta per l'indicizzazione (Ruling 17): il
            piano vince e la voce si estingue con lui. Il generato e' zero, il
            saldo e' il solo residuo — e se il piano non copre tutta la massa il
            residuo resta aperto, quindi nulla sparisce.
            """
            return ZERO if (pregresso or {}).get(key) else stock

        # Crediti tributari (sp06e) and imposte anticipate (sp06f) are NOT commercial
        # receivables and must NOT scale with revenue via DSO (the client's "crediti
        # tributari / imposte anticipate che salgono coi ricavi — non è corretto"): they
        # depend on the fiscal position, not on turnover. Carry them forward from the
        # previous year, with an optional manual % (sp06e_growth_pct / sp06f_growth_pct)
        # — mirroring the tax/other debts on the passivo (sp16e_growth_pct). Default
        # (no %) → constant. Only the TRADE buckets (clienti/controllate/collegate/
        # controllanti/altri) are driven by DSO below.
        tax_difference_lines = getattr(assumption, 'tax_temporary_differences', None) or []
        current_tax, deferred, _ = self._tax_components(base_inc, forecast_inc, assumption)
        sp06e = _prev('sp06e_crediti_tributari_breve') * (D('1') + _sp_growth('sp06e_growth_pct'))
        sp06f = (
            deferred['short_asset']
            if tax_difference_lines
            else _prev('sp06f_imposte_anticipate_breve') * (D('1') + _sp_growth('sp06f_growth_pct'))
        )

        # DSO → sp06 TRADE receivables (short-term). Auto-derive DSO from the base year
        # TRADE receivables only (sp06 aggregate minus tax credits and deferred taxes),
        # so carving those out above does not distort the ratio.
        dso = getattr(assumption, 'dso_days', None)
        if dso is not None:
            dso = D(str(dso))
            sp06_trade = forecast_revenue * dso / DAYS
        else:
            base_sp06_trade = max(
                ZERO,
                _base('sp06_crediti_breve')
                - _base('sp06e_crediti_tributari_breve')
                - _base('sp06f_imposte_anticipate_breve'),
            )
            dso = _derived_days(base_sp06_trade, base_revenue, 'dso')
            if dso is None:
                sp06_trade = _carry_unless_planned(base_sp06_trade, 'crediti_commerciali')
                dso = _effective_days(sp06_trade, forecast_revenue)
            else:
                sp06_trade = forecast_revenue * dso / DAYS
        if details is not None:
            details['dso_applied'] = dso
        sp06 = sp06_trade + sp06e + sp06f

        # DIO → sp05 (inventory)
        dio = getattr(assumption, 'dio_days', None)
        if dio is not None:
            dio = D(str(dio))
            sp05 = forecast_revenue * dio / DAYS
        else:
            # Auto-derive DIO from base year: base_sp05 / base_revenue * 360
            base_sp05 = _base('sp05_rimanenze')
            dio = _derived_days(base_sp05, base_revenue, 'dio')
            if dio is None:
                # Le rimanenze non hanno piano di scadenziamento: nulla da scorporare.
                sp05 = base_sp05
                dio = _effective_days(sp05, forecast_revenue)
            else:
                sp05 = forecast_revenue * dio / DAYS
        if details is not None:
            details['dio_applied'] = dio

        # Long-term receivables, other current assets
        long_growth = D('1') + assumption.receivables_long_growth_pct / D('100')
        if tax_difference_lines:
            sp07_non_deferred = max(
                ZERO,
                _prev('sp07_crediti_lungo') - _prev('sp07f_imposte_anticipate_lungo'),
            ) * long_growth
            sp07f = deferred['long_asset']
            sp07 = sp07_non_deferred + sp07f
        else:
            sp07 = _prev('sp07_crediti_lungo') * long_growth

        # ── PREGRESSO: il circolante e' generato + residuo (spec lotto 2 §3.1) ──
        # `generated` conserva il lato breve PRIMA del residuo: e' il numero che il
        # motore produceva senza piano, ed e' quello che i `details` dichiarano.
        # Senza piano non si entra in nessuno di questi rami e i saldi restano
        # identici al centesimo a quelli di prima del lotto.
        pregresso_runoff: Dict[str, Any] = {}
        generated: Dict[str, Decimal] = {'crediti_commerciali': sp06_trade}
        crediti_plan = (pregresso or {}).get('crediti_commerciali')
        if crediti_plan:
            runoff_crediti = runoff_schedule(
                crediti_plan['opening'], crediti_plan['amounts'], crediti_plan['writeoff'],
                year_index, horizon,
            )
            pregresso_runoff['crediti_commerciali'] = runoff_crediti
            # A breve: il generato dal DSO piu' il pregresso dovuto l'anno DOPO.
            # Oltre: TUTTO pregresso — la % di crescita del lungo commerciale non
            # si applica piu' (`mode: runoff` nei details lo dichiara). Le quote
            # fiscali di sp07 (crediti tributari e imposte anticipate) restano
            # fuori dal piano, esattamente come restano fuori dal DSO.
            sp06_trade = sp06_trade + runoff_crediti.residual_short
            sp06 = sp06_trade + sp06e + sp06f
            sp07e_long = _prev('sp07e_crediti_tributari_lungo') * long_growth
            if tax_difference_lines:
                sp07_non_deferred = runoff_crediti.residual_long + sp07e_long
                sp07 = sp07_non_deferred + sp07f
            else:
                sp07 = (
                    runoff_crediti.residual_long + sp07e_long
                    + _prev('sp07f_imposte_anticipate_lungo') * long_growth
                )

        sp08_anchor, sp08_factor = _sp_scale('sp08', 'sp08_growth_pct')
        sp08 = _declare_indexed('sp08', sp08_anchor('sp08_attivita_finanziarie') * sp08_factor)
        sp10_anchor, sp10_factor = _sp_scale('sp10', 'sp10_growth_pct')
        sp10 = _declare_indexed('sp10', sp10_anchor('sp10_ratei_risconti_attivi') * sp10_factor)
        sp01_anchor, sp01_factor = _sp_scale('sp01', 'sp01_growth_pct')
        sp01 = _declare_indexed('sp01', sp01_anchor('sp01_crediti_soci') * sp01_factor)

        # ── EQUITY ──

        net_profit = calculate_ce_result(forecast_inc).net_profit

        sp11 = _base('sp11_capitale')
        previous_profit = _prev('sp13_utile_perdita')
        sp12 = _prev('sp12_riserve') + previous_profit
        sp13 = net_profit

        # Reserve detail
        sp12a = _base('sp12a_riserva_sovrapprezzo')
        sp12b = _base('sp12b_riserve_rivalutazione')
        sp12c = _base('sp12c_riserva_legale')
        sp12d = _base('sp12d_riserve_statutarie')
        sp12e = _base('sp12e_altre_riserve')
        sp12f = _base('sp12f_riserva_copertura_flussi')
        sp12g = _prev('sp12g_utili_perdite_portati') + previous_profit
        sp12h = _base('sp12h_riserva_neg_azioni_proprie')

        # ── LIABILITIES (bottom-up from components) ──

        # Other liabilities (non-debt)
        sp14_anchor, provision_factor = _sp_scale('sp14', 'sp14_growth_pct')
        if tax_difference_lines:
            sp14a = sp14_anchor('sp14a_fondi_trattamento_quiescenza') * provision_factor
            sp14b = deferred['liability']
            sp14c = sp14_anchor('sp14c_strumenti_derivati_passivi') * provision_factor
            sp14d = sp14_anchor('sp14d_altri_fondi') * provision_factor
            sp14 = _declare_indexed('sp14', sp14a + sp14b + sp14c + sp14d)
        else:
            sp14 = _declare_indexed('sp14', sp14_anchor('sp14_fondi_rischi') * provision_factor)
            # I sotto-campi dell'anno precedente restano la sorgente delle sole
            # PROPORZIONI del riparto: l'importo lo decide `sp14` qui sopra, e
            # cambiarne l'ancora sposterebbe la ripartizione senza che nessuno
            # l'abbia chiesto.
            provision_fields = (
                'sp14a_fondi_trattamento_quiescenza', 'sp14b_fondi_imposte',
                'sp14c_strumenti_derivati_passivi', 'sp14d_altri_fondi',
            )
            provision_values = [_prev(field) for field in provision_fields]
            provision_total = sum(provision_values, ZERO)
            if provision_total > 0:
                sp14a, sp14b, sp14c, sp14d = [
                    sp14 * value / provision_total for value in provision_values
                ]
            else:
                sp14a = sp14b = sp14c = ZERO
                sp14d = sp14
        # TFR fund: previous fund + accrual. When the accrual is suspended (companies
        # with >60 employees pay the maturing TFR to the INPS treasury fund from a given
        # year rather than accruing it internally), the fund stops growing. The ce08a
        # cost stays in the P&L (it is paid out, not retained), so the outflow is reflected
        # through equity/cash — no internal liability is created.
        tfr_suspended = bool(getattr(assumption, 'tfr_accrual_suspended', False))
        if tfr_suspended:
            sp15 = _prev('sp15_tfr')
        else:
            sp15 = _prev('sp15_tfr') + forecast_inc.get('ce08a_tfr_accrual', ZERO)
        sp18_anchor, sp18_factor = _sp_scale('sp18', 'sp18_growth_pct')
        sp18 = _declare_indexed('sp18', sp18_anchor('sp18_ratei_risconti_passivi') * sp18_factor)

        # --- FINANCIAL DEBTS: repayment schedule ---
        existing_repay_years = getattr(assumption, 'existing_debt_repayment_years', None)

        # Carry forward financial sub-fields from previous year
        sp16a = _prev('sp16a_debiti_banche_breve')
        sp16b = _prev('sp16b_debiti_altri_finanz_breve')
        sp16c = _prev('sp16c_debiti_obbligazioni_breve')
        sp17a = _prev('sp17a_debiti_banche_lungo')
        sp17b = _prev('sp17b_debiti_altri_finanz_lungo')
        sp17c = _prev('sp17c_debiti_obbligazioni_lungo')

        # Handle abbreviato gap: if previous year has aggregate but no sub-field
        # detail, allocate the unaccounted portion to banche (bank debt).
        prev_sp16_agg = _prev('sp16_debiti_breve')
        prev_sp17_agg = _prev('sp17_debiti_lungo')

        # --- TRADE PAYABLES: DPO ---
        dpo = getattr(assumption, 'dpo_days', None)
        if dpo is not None:
            dpo = D(str(dpo))
            sp16d = forecast_purchases * dpo / DAYS
        else:
            # Auto-derive DPO from base year: base_sp16d / base_purchases * 360
            base_sp16d = _base('sp16d_debiti_fornitori_breve')
            dpo = _derived_days(base_sp16d, base_purchases, 'dpo')
            if dpo is None:
                sp16d = _carry_unless_planned(base_sp16d, 'debiti_fornitori')
                dpo = _effective_days(sp16d, forecast_purchases)
            else:
                sp16d = forecast_purchases * dpo / DAYS
        if details is not None:
            details['dpo_applied'] = dpo

        # Long-term trade payables
        sp17d_anchor, sp17d_factor = _sp_scale('sp17d', 'sp17d_growth_pct')
        sp17d = _declare_indexed(
            'sp17d', sp17d_anchor('sp17d_debiti_fornitori_lungo') * sp17d_factor)

        # ── SCORPORO: il generato nasce dalla base AL NETTO della massa a pregresso ──
        def _net_of_pregresso(value, key, short_field, *, from_base=False):
            """La sorgente del generato, tolto il pregresso che gia' contiene.

            Un saldo senza driver (previdenziali, altri debiti) si genera come
            `prev × (1+%)`: quel `prev` e' il saldo dell'anno prima, che dopo il
            primo anno di piano CONTIENE il residuo del pregresso. Farlo crescere
            cosi' com'e' rimetterebbe dentro dalla finestra il pregresso appena
            pagato — il saldo resterebbe fermo dopo aver pagato quasi tutto — ed e'
            l'esatto contrario di cio' che il piano dichiara. Il generato quindi
            parte dalla base scorporata della massa dichiarata, e il residuo lo
            tiene il kernel: `saldo = generato + residuo`, senza sovrapposizioni.

            Il pregresso dentro la sorgente e' l'intero campo dell'anno base
            (`validate_pregresso` impone che la massa dichiarata sia quella del
            bilancio base, quindi al primo anno il campo e' pregresso al 100%), o
            il `residual_short` dell'anno precedente per gli anni successivi.
            `from_base=True` per le formule ancorate all'anno base invece che al
            precedente (previdenza agganciata al personale).

            Senza piano restituisce il valore tale e quale: nessun ramo nuovo,
            nessun `max()` in mezzo, quindi gli stessi numeri di sempre.
            """
            plan = (pregresso or {}).get(key)
            if not plan:
                return value
            if from_base or year_index == 0:
                carried = _base(short_field)
            else:
                carried = runoff_schedule(
                    plan['opening'], plan['amounts'], plan['writeoff'],
                    year_index - 1, horizon,
                ).residual_short
            return max(ZERO, value - carried)

        # ── POSIZIONE TRIBUTARIA: saldo dell'anno prima + acconto sull'anno in corso ──
        # Le imposte non si pagano come un saldo qualsiasi (spec lotto 2 §3.2): in
        # ogni anno esce il SALDO maturato a fine anno precedente, l'ACCONTO
        # sull'anno in corso e la RATA del tributario rateizzato. Quel che resta
        # scoperto a fine anno (`generated_debt`) e' il saldo che si paghera'
        # l'anno DOPO — ed e' per questo che il calcolo legge i `details`
        # dell'anno precedente invece del solo saldo di bilancio: un saldo di
        # bilancio non sa dire quanto di se' e' saldo e quanto e' rata.
        # Le percentuali di crescita esplicite restano la via manuale e vincono
        # sull'automatismo; se c'e' anche un piano, i details lo dichiarano
        # ignorato invece di applicarlo a meta'.
        plan_tax = (pregresso or {}).get('debiti_tributari')
        manual_tax_position = (
            getattr(assumption, 'sp06e_growth_pct', None) is not None
            or getattr(assumption, 'sp16e_growth_pct', None) is not None
        )
        tax_year = None
        tax_generated_short = None
        if manual_tax_position:
            sp16e = _prev('sp16e_debiti_tributari_breve') * (D('1') + _sp_growth('sp16e_growth_pct'))
            sp17e = _prev('sp17e_debiti_tributari_lungo') * (D('1') + _sp_growth('sp17e_growth_pct'))
            if plan_tax and details is not None:
                details.setdefault('pregresso_ignored', []).append('debiti_tributari')
        else:
            # Il piano delle rate scadenzia il solo rateizzato: il saldo non entra
            # nel runoff perche' si paga per intero nel primo anno di piano.
            r = runoff_schedule(
                plan_tax['rateizzato'] if plan_tax else ZERO,
                plan_tax['amounts'] if plan_tax else [],
                [], year_index, horizon,
            )
            prev_tax_details = (prev_details or {}).get('imposte') or {}
            # L'imposta su cui si commisura l'acconto e' quella dell'anno prima:
            # la dichiara ogni anno, la via manuale compresa. Al primo anno di
            # piano e' `ce20` del consuntivo, l'unica imposta che il consuntivo porta.
            previous_tax = prev_tax_details.get('current_tax')
            if previous_tax is None:
                previous_tax = _base_inc('ce20_imposte')
            if prev_tax_details.get('mode') == 'saldo_acconto':
                # L'anno prima e' passato di qui: sa dire quanto di se' e' saldo
                # e quanto e' rata, e lo consegna gia' scomposto.
                saldo_due = prev_tax_details['generated_debt']
                opening_credit = (
                    prev_tax_details['generated_credit']
                    + prev_tax_details['opening_credit_left']
                )
            else:
                # Primo anno di piano, OPPURE un anno preceduto dalla VIA MANUALE.
                # In entrambi i casi la scomposizione non esiste da nessuna parte e
                # l'unica fonte vera e' il patrimoniale che quell'anno ha prodotto:
                # tutto il debito tributario e' saldo da versare, tranne il
                # rateizzato ancora aperto (spec §4), e il credito tributario e' il
                # credito di apertura.
                #
                # Portarselo dietro NON e' un dettaglio: ricominciare da zero dopo
                # un anno manuale faceva evaporare debito e credito tributari, e la
                # cassa — che e' il plug — assorbiva la differenza. Il foglio
                # quadrava lo stesso e nessuna diagnostica se ne accorgeva.
                opening_tax_debt = (
                    _prev('sp16e_debiti_tributari_breve')
                    + _prev('sp17e_debiti_tributari_lungo')
                )
                if year_index == 0 and plan_tax:
                    # Il saldo dichiarato dall'utente, esatto al centesimo: la
                    # sottrazione qui sotto lo ricostruirebbe entro la tolleranza
                    # di `validate_pregresso`, non uguale.
                    saldo_due = plan_tax['saldo']
                else:
                    # `r.residual + r.closed` e' il rateizzato ancora aperto
                    # all'INIZIO di quest'anno: non e' saldo, e dichiararlo tale
                    # lo farebbe risultare pagato due volte.
                    saldo_due = max(ZERO, opening_tax_debt - (r.residual + r.closed))
                opening_credit = _prev('sp06e_crediti_tributari_breve')
            # Solo un piano vero mette il saldo in `mode: runoff` (spec §5.3):
            # senza piano non c'e' nulla di scadenziato da dichiarare, e l'unica
            # sede onesta di cio' che e' stato versato resta `details['imposte']`.
            if plan_tax:
                pregresso_runoff['debiti_tributari'] = r
            tax_year = tax_settlement_saldo_acconto(
                opening_credit=opening_credit,
                saldo_due=saldo_due,
                rate_due=r.closed,
                current_tax=current_tax,
                previous_tax=previous_tax,
                acconto_pct=plan_tax['acconto_pct'] if plan_tax else D('100'),
                # Zero = «non dichiarato» (la colonna e' NOT NULL default 0): il
                # kernel ricade allora sulla percentuale. Chi vuole zero acconti
                # mette `acconto_pct = 0`.
                explicit_advances=getattr(assumption, 'tax_advances_paid', None),
            )
            tax_generated_short = tax_year.generated_debt
            sp16e = tax_year.generated_debt + r.residual_short
            sp17e = r.residual_long
            sp06e = tax_year.generated_credit + tax_year.opening_credit_left
            sp06 = sp06_trade + sp06e + sp06f
        # Con un piano l'indicizzazione e' gia' stata scartata (Ruling 17),
        # quindi l'ancora torna a essere `_prev` e lo scorporo resta quello di
        # sempre; senza piano `_net_of_pregresso` e' un passa-avanti.
        sp16g_anchor, sp16g_factor = _sp_scale('sp16g', 'sp16g_growth_pct')
        sp16g = _declare_indexed('sp16g', _net_of_pregresso(
            sp16g_anchor('sp16g_altri_debiti_breve'), 'altri_debiti', 'sp16g_altri_debiti_breve',
        ) * sp16g_factor)
        sp17g_anchor, sp17g_factor = _sp_scale('sp17g', 'sp17g_growth_pct')
        sp17g = _declare_indexed('sp17g', sp17g_anchor('sp17g_altri_debiti_lungo') * sp17g_factor)

        # Previdenza (sp16f/sp17f): opt-in scaling with the personnel cost (P5).
        # When enabled, social-security payables move in proportion to ce08 vs the BASE
        # year (e.g. personnel 100k→200k ⇒ previdenza 20k→40k), anchored on the base-year
        # amount so multi-year chains stay consistent. Default OFF → carry forward with
        # the manual sp16f/sp17f_growth_pct, exactly as before (zero regression).
        if getattr(assumption, 'previdenza_scales_with_personnel', False):
            base_ce08 = (getattr(base_inc, 'ce08_costi_personale', ZERO) or ZERO)
            fc_ce08 = (forecast_inc.get('ce08_costi_personale', ZERO) or ZERO)
            pers_factor = (fc_ce08 / base_ce08) if base_ce08 > 0 else D('1')
            sp16f = _net_of_pregresso(
                _base('sp16f_debiti_previdenza_breve'), 'debiti_previdenziali',
                'sp16f_debiti_previdenza_breve', from_base=True,
            ) * pers_factor
            sp17f = _base('sp17f_debiti_previdenza_lungo') * pers_factor
        else:
            sp16f_anchor, sp16f_factor = _sp_scale('sp16f', 'sp16f_growth_pct')
            sp16f = _declare_indexed('sp16f', _net_of_pregresso(
                sp16f_anchor('sp16f_debiti_previdenza_breve'), 'debiti_previdenziali',
                'sp16f_debiti_previdenza_breve',
            ) * sp16f_factor)
            sp17f_anchor, sp17f_factor = _sp_scale('sp17f', 'sp17f_growth_pct')
            sp17f = _declare_indexed(
                'sp17f', sp17f_anchor('sp17f_debiti_previdenza_lungo') * sp17f_factor)

        # ── PREGRESSO: gli altri tre saldi, stessa regola dei crediti ──
        # Il lato breve e' generato + dovuto l'anno dopo, il lato oltre e' tutto
        # pregresso: `sp17d_growth_pct`, `sp17f_growth_pct` e `sp17g_growth_pct`
        # non si applicano piu' al saldo che ha un piano, e i details lo dicono.
        # I due saldi senza driver (previdenziali, altri debiti) hanno gia' la
        # sorgente scorporata da `_net_of_pregresso`: il loro `generated` qui sotto
        # e' quindi cio' che il piano genera DAVVERO di nuovo, non il vecchio saldo
        # ripresentato. Fornitori e crediti no: il loro generato non e' uno stock
        # riportato ma la conversione di un flusso (acquisti × DPO, ricavi × DSO),
        # e scorporarlo direbbe che l'azienda smette di comprare e di vendere.
        generated['debiti_fornitori'] = sp16d
        # Il generato del tributario e' il solo debito NUOVO dell'anno (il saldo
        # che si paghera' l'anno dopo): il residuo delle rate lo dichiara
        # `residual_short`/`residual_long`, esattamente come per gli altri saldi.
        generated['debiti_tributari'] = (
            tax_generated_short if tax_generated_short is not None else sp16e
        )
        generated['debiti_previdenziali'] = sp16f
        generated['altri_debiti'] = sp16g
        fornitori_plan = (pregresso or {}).get('debiti_fornitori')
        if fornitori_plan:
            runoff_fornitori = runoff_schedule(
                fornitori_plan['opening'], fornitori_plan['amounts'], fornitori_plan['writeoff'],
                year_index, horizon,
            )
            pregresso_runoff['debiti_fornitori'] = runoff_fornitori
            sp16d = sp16d + runoff_fornitori.residual_short
            sp17d = runoff_fornitori.residual_long
        previdenziali_plan = (pregresso or {}).get('debiti_previdenziali')
        if previdenziali_plan:
            runoff_previdenziali = runoff_schedule(
                previdenziali_plan['opening'], previdenziali_plan['amounts'],
                previdenziali_plan['writeoff'], year_index, horizon,
            )
            pregresso_runoff['debiti_previdenziali'] = runoff_previdenziali
            sp16f = sp16f + runoff_previdenziali.residual_short
            sp17f = runoff_previdenziali.residual_long
        altri_debiti_plan = (pregresso or {}).get('altri_debiti')
        if altri_debiti_plan:
            runoff_altri = runoff_schedule(
                altri_debiti_plan['opening'], altri_debiti_plan['amounts'],
                altri_debiti_plan['writeoff'], year_index, horizon,
            )
            pregresso_runoff['altri_debiti'] = runoff_altri
            sp16g = sp16g + runoff_altri.residual_short
            sp17g = runoff_altri.residual_long

        # A missing breakdown is unknown creditor type, not bank debt.  The source
        # gate catches this on the base year; retain a local guard for direct calls
        # and for malformed previous forecast rows.
        # Validate like-for-like PREVIOUS values.  The variables above already
        # contain this forecast year's DPO/tax/growth calculations, so mixing
        # them with the previous aggregate produced a false mismatch whenever
        # revenue, taxes or creditor assumptions changed.
        prev_sp16_detail = sum(
            (
                _prev(field)
                for field in (
                    'sp16a_debiti_banche_breve',
                    'sp16b_debiti_altri_finanz_breve',
                    'sp16c_debiti_obbligazioni_breve',
                    'sp16d_debiti_fornitori_breve',
                    'sp16e_debiti_tributari_breve',
                    'sp16f_debiti_previdenza_breve',
                    'sp16g_altri_debiti_breve',
                )
            ),
            ZERO,
        )
        gap_short = prev_sp16_agg - prev_sp16_detail
        prev_sp17_detail = sum(
            (
                _prev(field)
                for field in (
                    'sp17a_debiti_banche_lungo',
                    'sp17b_debiti_altri_finanz_lungo',
                    'sp17c_debiti_obbligazioni_lungo',
                    'sp17d_debiti_fornitori_lungo',
                    'sp17e_debiti_tributari_lungo',
                    'sp17f_debiti_previdenza_lungo',
                    'sp17g_altri_debiti_lungo',
                )
            ),
            ZERO,
        )
        gap_long = prev_sp17_agg - prev_sp17_detail
        if abs(gap_short) > Decimal('0.01') or abs(gap_long) > Decimal('0.01'):
            raise ValueError(
                "Debt aggregate/detail mismatch: creditor categories are required; "
                "the difference was not allocated to banks"
            )

        # Apply the bank repayment schedule to total bank debt (entro + oltre).
        # The instalment is FIXED on the ORIGINAL base-year bank exposure
        # so the debt fully amortises to zero after `existing_repay_years`. (Recomputing
        # the instalment on the shrinking residual each year — the previous behaviour —
        # is a decreasing instalment that never reaches zero: e.g. over 3 years it leaves
        # 8/27 ≈ 30% outstanding, the "residuo" the user reported.)
        if (
            not use_detailed_existing_schedule
            and existing_repay_years is not None
            and D(str(existing_repay_years)) > 0
        ):
            # Short-term bank debt is repaid first; any residual instalment reduces
            # long-term bank debt. Bonds and other lenders are left untouched.
            annual_repayment = financial_repayment_instalment(_base, existing_repay_years)
            short_repayment = min(sp16a, annual_repayment)
            sp16a = max(ZERO, sp16a - short_repayment)
            long_repayment = annual_repayment - short_repayment
            sp17a = max(ZERO, sp17a - long_repayment)

        # Altri finanziatori (sp17b) — e.g. an intra-group loan — repaid on its OWN fixed
        # schedule, independent of the bank debt (shared kernel: fixed instalment on the
        # base-year amount, amortises fully to zero after `altri_finanz_repayment_years`).
        altri_repay_years = getattr(assumption, 'altri_finanz_repayment_years', None)
        if altri_repay_years is not None and D(str(altri_repay_years)) > 0:
            annual_altri = altri_finanz_repayment_instalment(_base, altri_repay_years)
            sp17b = max(ZERO, sp17b - annual_altri)

        # New financing raised during the plan: add what is raised THIS year to
        # long-term bank debt, then subtract this year's straight-line instalment
        # so the loan amortises over its durata (shared kernel, mirrors the
        # existing-debt plan above). Because sp17a is carried forward via `_prev`,
        # a loan raised once (e.g. 150k in year 1, then 0) stays on the sheet and
        # shrinks by its rata each year instead of persisting flat forever.
        fin_raised, fin_repayment, _ = new_financing_schedule(financing_loans, assumption.forecast_year)
        sp17a = sp17a + fin_raised
        short_fin_repayment = min(sp16a, fin_repayment)
        sp16a = max(ZERO, sp16a - short_fin_repayment)
        sp17a = max(ZERO, sp17a - (fin_repayment - short_fin_repayment))

        # --- AGGREGATE sp16/sp17 from components ---
        sp16 = sp16a + sp16b + sp16c + sp16d + sp16e + sp16f + sp16g
        sp17 = sp17a + sp17b + sp17c + sp17d + sp17e + sp17f + sp17g

        # ── CASH PLUG ──
        total_assets_no_cash = sp01 + sp02 + sp03 + sp04 + sp05 + sp06 + sp07 + sp08 + sp10
        total_liabilities = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18

        sp09 = total_liabilities - total_assets_no_cash

        # A negative implied cash balance is an uncovered funding requirement.
        # Con lo scoperto SPENTO (il default) il motore alza e non produce nulla,
        # come ha sempre fatto; con lo scoperto concesso il fabbisogno diventa
        # `sp16a` generato dal piano — una scelta esplicita dell'utente, non un
        # debito che compare muto (vedi `_Overdraft`).
        if sp09 < 0:
            fabbisogno = -sp09
            overdraft.copri(fabbisogno)
            sp16a += fabbisogno
            sp16 += fabbisogno
            sp09 = ZERO
        elif overdraft.outstanding > ZERO:
            # Lo scoperto non e' eterno: e' cassa negativa, quindi la cassa
            # disponibile lo rimborsa per prima, prima di qualunque altra
            # destinazione. Non passa dal cash sweep, che e' opt-in e serve al
            # debito bancario ORDINARIO. Il minimo con `sp16a` non e' pleonastico:
            # un piano di rimborso del debito esistente puo' aver gia' eroso la
            # voce, e non si rimborsa piu' di quanto sia rimasto scritto.
            rimborso = min(sp09, overdraft.outstanding, sp16a)
            if rimborso > ZERO:
                overdraft.repaid += rimborso
                sp16a -= rimborso
                sp16 -= rimborso
                sp09 -= rimborso
        if bool(getattr(assumption, 'cash_sweep_enabled', False)):
            # ── CASH SWEEP (opt-in) ── Use cash generated above the minimum floor to pay
            # down BANK debt — short-term first (sp16a), then long-term (sp17a) — instead
            # of letting idle cash accumulate while the debt stays flat (the client's
            # "la cassa cresce ma il debito v/banche resta invariato"). Cash and debt are
            # reduced by the same amount, so the balance sheet stays balanced.
            floor = getattr(assumption, 'cash_sweep_min_cash', None)
            floor = D(str(floor)) if floor is not None else ZERO
            excess = sp09 - floor
            if excess > ZERO:
                pay_short = min(excess, sp16a)
                sp16a -= pay_short; sp16 -= pay_short; sp09 -= pay_short; excess -= pay_short
                pay_long = min(excess, sp17a)
                sp17a -= pay_long; sp17 -= pay_long; sp09 -= pay_long; excess -= pay_long

        # ── DETAIL BREAKDOWNS ──

        # Immobilizzazioni finanziarie (sp04 sub-fields)
        total_base_sp04 = (
            _base('sp04a_partecipazioni') + _base('sp04b_crediti_immob_breve') +
            _base('sp04c_crediti_immob_lungo') + _base('sp04d_altri_titoli') +
            _base('sp04e_strumenti_derivati_attivi')
        )
        if total_base_sp04 > 0:
            ratio = sp04 / total_base_sp04
            sp04a = _base('sp04a_partecipazioni') * ratio
            sp04b = _base('sp04b_crediti_immob_breve') * ratio
            sp04c = _base('sp04c_crediti_immob_lungo') * ratio
            sp04d = _base('sp04d_altri_titoli') * ratio
            sp04e = _base('sp04e_strumenti_derivati_attivi') * ratio
        else:
            sp04a = sp04b = sp04c = sp04d = sp04e = ZERO

        # Trade receivables / inventory detail (sp06*, sp05*): the engine drives only the
        # aggregates (sp06 from DSO, sp05 from DIO), but the forecast BS renders the IV-CEE
        # sub-rows (e.g. "1) verso clienti" = sp06a). Without writing them the rows stay
        # blank. Allocate the aggregate proportionally to the base-year detail; when the
        # base has no detail, put it all in the primary bucket (clienti / materie).
        def _alloc(aggregate, base_fields, primary_idx=0):
            base_vals = [_base(f) for f in base_fields]
            tot = sum(base_vals, ZERO)
            if tot > 0:
                return [aggregate * (v / tot) for v in base_vals]
            out = [ZERO] * len(base_fields)
            out[primary_idx] = aggregate
            return out

        # Fixed-asset details must travel with their aggregates.  The assumptions
        # expose aggregate investments/depreciation, not a statutory sub-category,
        # so preserve the source composition proportionally.  If the source is
        # abbreviated and has no detail, keep the amount in the generic bucket.
        sp02_fields = [
            'sp02a_costi_impianto', 'sp02b_costi_sviluppo', 'sp02c_brevetti',
            'sp02d_concessioni', 'sp02e_avviamento', 'sp02f_immob_in_corso',
            'sp02g_altre_immob_imm',
        ]
        sp02a, sp02b, sp02c, sp02d, sp02e, sp02f, sp02g = _alloc(
            sp02, sp02_fields, primary_idx=6
        )
        sp03_fields = [
            'sp03a_terreni_fabbricati', 'sp03b_impianti_macchinari',
            'sp03c_attrezzature', 'sp03d_altri_beni', 'sp03e_immob_in_corso',
        ]
        sp03a, sp03b, sp03c, sp03d, sp03e = _alloc(
            sp03, sp03_fields, primary_idx=3
        )

        # Allocate the DSO-driven TRADE total across the commercial buckets only
        # (a/b/c/d/g). Crediti tributari (sp06e) and imposte anticipate (sp06f) keep the
        # carried-forward values computed in the working-capital section above — they do
        # not scale with revenue.
        sp06_trade_fields = ['sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
                             'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
                             'sp06g_crediti_altri_breve']
        sp06a, sp06b, sp06c, sp06d, sp06g = _alloc(sp06_trade, sp06_trade_fields)

        sp07_non_deferred_fields = [
            'sp07a_crediti_clienti_lungo', 'sp07b_crediti_controllate_lungo',
            'sp07c_crediti_collegate_lungo', 'sp07d_crediti_controllanti_lungo',
            'sp07e_crediti_tributari_lungo', 'sp07g_crediti_altri_lungo',
        ]
        if tax_difference_lines:
            sp07a, sp07b, sp07c, sp07d, sp07e, sp07g = _alloc(
                sp07_non_deferred, sp07_non_deferred_fields
            )
        else:
            sp07_fields = sp07_non_deferred_fields[:5] + [
                'sp07f_imposte_anticipate_lungo', 'sp07g_crediti_altri_lungo'
            ]
            sp07a, sp07b, sp07c, sp07d, sp07e, sp07f, sp07g = _alloc(sp07, sp07_fields)

        sp05_fields = ['sp05a_materie_prime', 'sp05b_prodotti_in_corso', 'sp05c_lavori_in_corso',
                       'sp05d_prodotti_finiti', 'sp05e_acconti']
        sp05a, sp05b, sp05c, sp05d, sp05e = _alloc(sp05, sp05_fields)

        # ── DETAILS DEL PREGRESSO: dichiarati SEMPRE, tutti e cinque i saldi ──
        # Anche senza alcun piano, e anche a zero: a valle una chiave assente vale
        # zero, quindi tacere equivarrebbe a dichiararsi puliti. `mode` distingue
        # il saldo che segue le formule di oggi (`legacy`) da quello scadenziato
        # (`runoff`).
        #
        # `opening` e' la massa che gli ALTRI CAMPI DELLA RIGA descrivono, cosi' che
        # le cinque righe si leggano tutte allo stesso modo e `opening − Σclosed`
        # torni sul residuo. Senza piano e' la massa del bilancio base, cosi'
        # l'interfaccia sa che cosa c'e' da scadenziare prima ancora del primo piano.
        # Con un piano e' la massa scadenziata, che per i quattro saldi non fiscali
        # e' la stessa cosa (`validate_pregresso` impone che coincidano), ma per i
        # tributari NO: li' il piano scadenzia il solo RATEIZZATO, mentre il saldo
        # si versa nel primo anno e vive in `details['imposte']`. Dichiarare li' la
        # massa intera faceva della riga tributaria l'unica delle cinque che non
        # torna: 90.000 di apertura con 60.000 di rate a spiegarla.
        if details is not None:
            masses = pregresso_opening_masses(_base)
            details['pregresso'] = {}
            for key in PREGRESSO_KEYS:
                r = pregresso_runoff.get(key)
                details['pregresso'][key] = {
                    'opening': r.opening if r else masses[key],
                    'closed': r.closed if r else ZERO,
                    'writeoff': r.writeoff if r else ZERO,
                    'residual_short': r.residual_short if r else ZERO,
                    'residual_long': r.residual_long if r else ZERO,
                    'generated': generated.get(key, ZERO),
                    'mode': 'runoff' if r else 'legacy',
                }
            details.setdefault('pregresso_ignored', [])
            # L'inesigibile che un override di CE ha impedito di rilevare, e che
            # quindi NON e' stato scaricato dai crediti: dichiarato sempre, anche
            # vuoto, come `override_conflicts`. Senza questa riga il piano direbbe
            # 5.000 di inesigibile e il bilancio non ne mostrerebbe traccia — ne'
            # in meno sui crediti ne' in piu' sui costi — senza un solo avviso.
            writeoff_ignored = (
                ((pregresso or {}).get('crediti_commerciali') or {}).get('writeoff_ignored') or {}
            ).get(year_index)
            details['pregresso_writeoff_ignored'] = (
                [{
                    'saldo': 'crediti_commerciali',
                    'field': 'ce09d_svalutazione_crediti',
                    'requested': writeoff_ignored['requested'],
                    'reason': writeoff_ignored['reason'],
                }]
                if writeoff_ignored else []
            )
            # La posizione tributaria dell'anno, dichiarata SEMPRE: `saldo_acconto`
            # quando e' il kernel a governarla, `manual` quando l'utente ha imposto
            # una percentuale di crescita su sp06e/sp16e — e allora gli importi
            # pagati non esistono, quindi si dichiarano zero invece di inventarli.
            details['imposte'] = (
                {
                    'current_tax': current_tax,
                    'saldo_paid': tax_year.saldo_paid,
                    'acconti_paid': tax_year.acconti_paid,
                    'rate_paid': tax_year.rate_paid,
                    'generated_debt': tax_year.generated_debt,
                    'generated_credit': tax_year.generated_credit,
                    'opening_credit_left': tax_year.opening_credit_left,
                    'mode': 'saldo_acconto',
                }
                if tax_year is not None else
                {
                    'current_tax': current_tax, 'saldo_paid': ZERO, 'acconti_paid': ZERO,
                    'rate_paid': ZERO, 'generated_debt': ZERO, 'generated_credit': ZERO,
                    'opening_credit_left': ZERO, 'mode': 'manual',
                }
            )

        result = {
            'sp01_crediti_soci': sp01,
            'sp02_immob_immateriali': sp02,
            'sp02a_costi_impianto': sp02a,
            'sp02b_costi_sviluppo': sp02b,
            'sp02c_brevetti': sp02c,
            'sp02d_concessioni': sp02d,
            'sp02e_avviamento': sp02e,
            'sp02f_immob_in_corso': sp02f,
            'sp02g_altre_immob_imm': sp02g,
            'sp03_immob_materiali': sp03,
            'sp03a_terreni_fabbricati': sp03a,
            'sp03b_impianti_macchinari': sp03b,
            'sp03c_attrezzature': sp03c,
            'sp03d_altri_beni': sp03d,
            'sp03e_immob_in_corso': sp03e,
            'sp04_immob_finanziarie': sp04,
            'sp04a_partecipazioni': sp04a,
            'sp04b_crediti_immob_breve': sp04b,
            'sp04c_crediti_immob_lungo': sp04c,
            'sp04d_altri_titoli': sp04d,
            'sp04e_strumenti_derivati_attivi': sp04e,
            'sp05_rimanenze': sp05,
            'sp05a_materie_prime': sp05a,
            'sp05b_prodotti_in_corso': sp05b,
            'sp05c_lavori_in_corso': sp05c,
            'sp05d_prodotti_finiti': sp05d,
            'sp05e_acconti': sp05e,
            'sp06_crediti_breve': sp06,
            'sp06a_crediti_clienti_breve': sp06a,
            'sp06b_crediti_controllate_breve': sp06b,
            'sp06c_crediti_collegate_breve': sp06c,
            'sp06d_crediti_controllanti_breve': sp06d,
            'sp06e_crediti_tributari_breve': sp06e,
            'sp06f_imposte_anticipate_breve': sp06f,
            'sp06g_crediti_altri_breve': sp06g,
            'sp07_crediti_lungo': sp07,
            'sp07a_crediti_clienti_lungo': sp07a,
            'sp07b_crediti_controllate_lungo': sp07b,
            'sp07c_crediti_collegate_lungo': sp07c,
            'sp07d_crediti_controllanti_lungo': sp07d,
            'sp07e_crediti_tributari_lungo': sp07e,
            'sp07f_imposte_anticipate_lungo': sp07f,
            'sp07g_crediti_altri_lungo': sp07g,
            'sp08_attivita_finanziarie': sp08,
            'sp09_disponibilita_liquide': sp09,
            'sp10_ratei_risconti_attivi': sp10,
            'sp11_capitale': sp11,
            'sp12_riserve': sp12,
            'sp12a_riserva_sovrapprezzo': sp12a,
            'sp12b_riserve_rivalutazione': sp12b,
            'sp12c_riserva_legale': sp12c,
            'sp12d_riserve_statutarie': sp12d,
            'sp12e_altre_riserve': sp12e,
            'sp12f_riserva_copertura_flussi': sp12f,
            'sp12g_utili_perdite_portati': sp12g,
            'sp12h_riserva_neg_azioni_proprie': sp12h,
            'sp13_utile_perdita': sp13,
            'sp14_fondi_rischi': sp14,
            'sp14a_fondi_trattamento_quiescenza': sp14a,
            'sp14b_fondi_imposte': sp14b,
            'sp14c_strumenti_derivati_passivi': sp14c,
            'sp14d_altri_fondi': sp14d,
            'sp15_tfr': sp15,
            'sp16_debiti_breve': sp16,
            'sp17_debiti_lungo': sp17,
            'sp16a_debiti_banche_breve': sp16a,
            'sp17a_debiti_banche_lungo': sp17a,
            'sp16b_debiti_altri_finanz_breve': sp16b,
            'sp17b_debiti_altri_finanz_lungo': sp17b,
            'sp16c_debiti_obbligazioni_breve': sp16c,
            'sp17c_debiti_obbligazioni_lungo': sp17c,
            'sp16d_debiti_fornitori_breve': sp16d,
            'sp17d_debiti_fornitori_lungo': sp17d,
            'sp16e_debiti_tributari_breve': sp16e,
            'sp17e_debiti_tributari_lungo': sp17e,
            'sp16f_debiti_previdenza_breve': sp16f,
            'sp17f_debiti_previdenza_lungo': sp17f,
            'sp16g_altri_debiti_breve': sp16g,
            'sp17g_altri_debiti_lungo': sp17g,
            'sp18_ratei_risconti_passivi': sp18
        }
        return self._apply_sp_overrides(result, assumption, overdraft=overdraft)


def generate_forecast_for_scenario(scenario_id: int, db_session: Session) -> Dict:
    """
    Convenience function to generate forecast

    Args:
        scenario_id: Budget scenario ID
        db_session: Database session

    Returns:
        Forecast results
    """
    engine = ForecastEngine(db_session)
    return engine.generate_forecast(scenario_id)
