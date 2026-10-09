"""Il modello del Business plan: numeri del motore allineati alle colonne del report.

Fonte unica: FinalReportModelV2. Qui si sommano e si sottraggono righe già presenti; nessun indicatore
viene ricalcolato (spec §4). Un valore assente resta None fino alla stampa, dove diventa «n.d.».
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Callable, Literal, Optional

from . import fmt

Num = Optional[Decimal]
Workflow = Literal["infrannuale", "bilancio", "startup"]

DIFF_ROW = ("balance_sheet:total_assets+sp11_capitale+sp12_riserve+sp13_utile_perdita+sp16_debiti_breve"
            "+sp17_debiti_lungo+sp14_fondi_rischi+sp15_tfr+sp18_ratei_risconti_passivi")

# A01-bis: una frase per diagnostica, nell'ordine in cui la spec le elenca. `report.diagnostics`
# non è filtrato per severità: le due diagnostiche sono sempre `error` (final_report_service).
_AVVISI_PER_CODICE = (
    ("forecast_stale", "Previsionale precedente alle ipotesi salvate: da rigenerare"),
    ("engine_version_stale", "Previsionale generato da una versione precedente del motore: da rigenerare"),
)


def _avvisi(report) -> tuple:
    codici = {d.code for d in report.diagnostics}
    return tuple(frase for codice, frase in _AVVISI_PER_CODICE if codice in codici)


@dataclass(frozen=True)
class Column:
    period_id: str
    year: int
    label: str
    is_base: bool


@dataclass(frozen=True)
class AnnexRow:
    label: str
    level: int
    kind: str
    values: tuple


@dataclass(frozen=True)
class IndicatorRow:
    label: str
    unit: str
    values: tuple


@dataclass(frozen=True)
class AssumptionRow:
    label: str
    unit: str
    values: tuple  # uno per anno di piano


@dataclass(frozen=True)
class FinanziamentoRow:
    """Una riga della tabella «Finanziamenti» della sezione 10 (passo 5 del wizard)."""
    nome: str
    tipo: str  # «Pregresso» | «Nuovo» | «Altro finanziatore»
    importo: Num
    tasso: Num
    durata_anni: Optional[int] = None


@dataclass(frozen=True)
class TableBlock:
    title: str
    headers: tuple
    rows: tuple  # (etichetta, valori, stile) con stile in "", "bold", "hl"
    note: str = ""


@dataclass(frozen=True)
class StartingPoint:
    kind: Workflow
    title: str
    intro: str
    tiles: tuple
    tables: tuple
    indicator_headers: tuple
    indicators: tuple
    checks: tuple
    note: str
    sources: tuple = ()  # (fonte, periodo, stato): la tabella «Fonti» della sezione 9
    rettifiche: tuple = ()  # (voce, importo, contropartita, motivazione): le rettifiche registrate (sezione 9)


@dataclass(frozen=True)
class BusinessPlanData:
    company_name: str
    workflow: Workflow
    columns: tuple
    base_description: str
    values: dict
    growth: dict = field(default_factory=dict)
    revenue_overridden: bool = False  # un ce01_override in qualche anno: i ricavi non seguono la crescita
    assumptions: tuple = ()
    partial_label: Optional[str] = None
    partial_dscr: Num = None
    residual_revenue: Num = None
    starting_point: Optional[StartingPoint] = None
    annex: dict = field(default_factory=dict)
    annex_zero_labels: dict = field(default_factory=dict)
    indicators_practice_headers: tuple = ()
    indicators_practice: tuple = ()
    indicators_analytical: tuple = ()
    draft: bool = False
    avvisi: tuple = ()  # A01-bis: frasi «da rigenerare» per forecast_stale/engine_version_stale, nell'ordine
    finanziamenti_tabella: tuple = ()  # FinanziamentoRow: i contratti dei passi 5-6, col tasso (#61 S15)
    ipotesi_puntuali: tuple = ()  # (voce, testo): piani di rientro, indicizzazioni, valori forzati
    avvisi_motore: tuple = ()  # frasi di `engine_meta['avvisi']` di tutti gli anni di piano, deduplicate (#62 S24)

    def v(self, key: str) -> tuple:
        return self.values.get(key) or (None,) * len(self.columns)

    @property
    def plan_idx(self) -> list:
        return [i for i, c in enumerate(self.columns) if not c.is_base]

    @property
    def plan_columns(self) -> list:
        return [self.columns[i] for i in self.plan_idx]

    @property
    def plan_years(self) -> list:
        return [c.year for c in self.plan_columns]

    @property
    def first(self) -> Column:
        return self.columns[0]

    @property
    def last(self) -> Column:
        return self.columns[-1]


def legend(data: BusinessPlanData) -> str:
    return {"infrannuale": "F = forecast · P = previsione di piano",
            "bilancio": "C = consuntivo · P = previsione di piano",
            "startup": "P = previsione di piano"}[data.workflow]


# ------------------------------------------------------------------ mappa chiave → righe del modello
_CE = {
    "ricavi": ("ce01_ricavi_vendite",),
    "var_produzione": ("ce02_variazioni_rimanenze", "ce03_lavori_interni", "ce03a_incrementi_immobilizzazioni"),
    "altri_ricavi": ("ce04_altri_ricavi",),
    "valore_produzione": ("production_value",),
    "materie": ("ce05_materie_prime",),
    "servizi": ("ce06_servizi",),
    "godimento": ("ce07_godimento_beni",),
    "personale": ("ce08_costi_personale",),
    "var_rim_materie": ("ce10_var_rimanenze_mat_prime",),
    "accantonamenti": ("ce11_accantonamenti", "ce11b_altri_accantonamenti"),
    "oneri_diversi": ("ce12_oneri_diversi",),
    "costi_produzione": ("production_cost",),
    "ammortamenti": ("ce09_ammortamenti",),
    "ebitda": ("ebitda",),
    "ebit": ("ebit",),
    "proventi_fin": ("ce13_proventi_partecipazioni", "ce14_altri_proventi_finanziari"),
    "oneri_fin": ("ce15_oneri_finanziari",),
    "altre_componenti": ("ce16_utili_perdite_cambi", "ce17_rettifiche_attivita_fin", "extraordinary_result"),
    "ante_imposte": ("profit_before_tax",),
    "imposte": ("ce20_imposte",),
    "utile": ("net_profit",),
}
_SP = {
    "immobilizzazioni": ("fixed_assets",),
    "rimanenze": ("sp05_rimanenze",),
    "crediti_comm": ("sp06a_crediti_clienti_breve", "sp07a_crediti_clienti_lungo"),
    "liquidita": ("sp09_disponibilita_liquide",),
    "totale_attivo": ("total_assets",),
    "capitale": ("sp11_capitale",),
    "patrimonio_netto": ("sp11_capitale+sp12_riserve+sp13_utile_perdita",),
    "tfr": ("sp15_tfr",),
    "banche": ("sp16a_debiti_banche_breve+sp17a_debiti_banche_lungo",),
    "banche_breve": ("sp16a_debiti_banche_breve",),
    "banche_lungo": ("sp17a_debiti_banche_lungo",),
    "altri_finanziatori": ("sp16b_debiti_altri_finanz_breve+sp17b_debiti_altri_finanz_lungo",),
    "obbligazioni": ("sp16c_debiti_obbligazioni_breve+sp17c_debiti_obbligazioni_lungo",),
    "debiti_comm": ("sp16d_debiti_fornitori_breve+sp17d_debiti_fornitori_lungo",),
}
_CF = {
    "cf_ebit": ("operating.start.profit_before_adjustments",),
    "cf_non_monetarie": ("operating.non_cash_adjustments.total",),
    "cf_ante_ccn": ("operating.cashflow_before_wc",),
    "cf_var_ccn": ("operating.working_capital_changes.total",),
    "cf_altre": ("operating.cash_adjustments.total",),
    "cf_operativo": ("operating.total_operating_cashflow",),
    "cf_investimenti": ("investing.total_investing_cashflow",),
    "cf_finanziamento": ("financing.total_financing_cashflow",),
    "cf_nuovo_debito": ("financing.third_party_funds.increases",),
    "cf_rimborsi": ("financing.third_party_funds.decreases",),
    "cf_variazione": ("cash_reconciliation.total_cashflow",),
    "cassa_inizio": ("cash_reconciliation.cash_beginning",),
    "cassa_fine": ("cash_reconciliation.cash_ending",),
}
_IND = {
    "ebitda_margin": "practice.ebitda_margin", "dscr": "practice.dscr", "pfn": "practice.pfn",
    "pfn_ebitda": "practice.pfn_ebitda", "of_mol": "practice.of_mol", "of_ricavi": "practice.of_revenue",
    "ccn": "practice.ccn", "margine_tesoreria": "practice.mt", "margine_struttura": "practice.ms",
    "liquidita_corrente": "practice.current_ratio", "liquidita_immediata": "practice.quick_ratio",
    "indipendenza": "practice.indipendenza", "copertura_immob": "practice.copertura_immob",
    "roi": "practice.roi", "roe": "practice.roe", "ros": "practice.ros", "opex_ricavi": "practice.opex_revenue",
    "rod": "analytical.profitability.rod", "spread": "analytical.extended_profitability.spread",
    "dso": "analytical.activity.receivables_turnover_days", "dio": "analytical.activity.inventory_turnover_days",
    "dpo": "analytical.activity.payables_turnover_days", "ciclo": "analytical.activity.cash_conversion_cycle",
}
_BE = {"costi_fissi": "fixed_costs", "costi_variabili": "variable_costs",
       "margine_contribuzione": "contribution_margin", "bep": "break_even_revenue",
       "margine_sicurezza": "safety_margin_pct"}


def _add(*xs: Num) -> Num:
    return None if any(x is None for x in xs) else sum(xs, Decimal(0))


def _sub(a: Num, b: Num) -> Num:
    return None if a is None or b is None else a - b


def _share(a: Num, b: Num) -> Num:
    return None if a is None or b is None or b == 0 else a / b * 100


_DERIVED: dict = {
    # R15: valore della produzione − ricavi delle vendite (ce02 + ce03 + ce03a + ce04), cioè la riga che fa
    # tornare Ricavi + Altri ricavi e variazioni − Costi operativi = EBITDA in ogni colonna
    "altri_ricavi_var": lambda g: _sub(g("valore_produzione"), g("ricavi")),
    "costi_operativi": lambda g: _sub(g("costi_produzione"), g("ammortamenti")),
    "debiti_finanziari": lambda g: _add(g("pfn"), g("liquidita")),
    "cc_comm": lambda g: _sub(_add(g("crediti_comm"), g("rimanenze")), g("debiti_comm")),
    "altre_attivita": lambda g: _sub(g("totale_attivo"),
                                     _add(g("immobilizzazioni"), g("rimanenze"), g("crediti_comm"), g("liquidita"))),
    "altre_passivita": lambda g: _sub(g("totale_attivo"), _add(g("patrimonio_netto"), g("debiti_finanziari"))),
    **{f"inc_{k}": (lambda k: lambda g: _share(g(k), g("ricavi")))(k)
       for k in ("materie", "servizi", "godimento", "personale", "oneri_diversi", "costi_operativi", "oneri_fin")},
}

VALUE_KEYS = tuple(_CE) + tuple(_SP) + tuple(_CF) + tuple(_IND) + tuple(_BE) + tuple(_DERIVED)

UNITS = {"ebitda_margin": "percent", "dscr": "dscr", "pfn": "eur", "pfn_ebitda": "ratio", "of_mol": "percent",
         "of_ricavi": "percent", "ccn": "eur", "margine_tesoreria": "eur", "margine_struttura": "eur",
         "liquidita_corrente": "ratio", "liquidita_immediata": "ratio", "indipendenza": "percent",
         "copertura_immob": "percent", "roi": "percent", "roe": "percent", "ros": "percent",
         "opex_ricavi": "percent", "rod": "percent", "spread": "percent", "dso": "days", "dio": "days",
         "dpo": "days", "ciclo": "days", "margine_sicurezza": "percent"}


class _Lookup:
    """Valori del modello v2 per (chiave, periodo)."""

    def __init__(self, report):
        self.rows: dict = {}
        for st in report.detailed_statements:
            pids = [p.id for p in st.periods]
            for r in st.rows:
                self.rows[r.id] = dict(zip(pids, r.values))
        self.ind = {i.id: dict(zip([p.id for p in i.periods], i.values)) for i in report.indicator_catalog}
        self.series: dict = {}
        for g in report.structure_series:
            pids = [p.id for p in g.periods]
            for s in g.series:
                self.series[(g.id, s.id)] = dict(zip(pids, s.values))

    def _rows(self, prefix: str, ids: tuple, pid: str) -> Num:
        vals = [self.rows.get(f"{prefix}:{i}", {}).get(pid) for i in ids]
        return _add(*vals)

    def get(self, key: str, pid: str) -> Num:
        if key in _CE:
            return self._rows("income_statement", _CE[key], pid)
        if key in _SP:
            return self._rows("balance_sheet", _SP[key], pid)
        if key in _CF:
            value = self._rows("cashflow", _CF[key], pid)
            return abs(value) if key == "cf_rimborsi" and value is not None else value
        if key in _IND:
            return self.ind.get(_IND[key], {}).get(pid)
        if key in _BE:
            return self.series.get(("break_even", _BE[key]), {}).get(pid)
        if key in _DERIVED:
            return _DERIVED[key](lambda k: self.get(k, pid))
        raise KeyError(key)


# ------------------------------------------------------------------ ipotesi
_ASSUMPTIONS = (
    ("revenue_growth_pct", "Crescita ricavi", "percent"),
    ("other_revenue_growth_pct", "Crescita altri ricavi", "percent"),
    ("variable_materials_growth_pct", "Crescita materie (variabile)", "percent"),
    ("variable_services_growth_pct", "Crescita servizi (variabile)", "percent"),
    ("personnel_growth_pct", "Crescita personale", "percent"),
    ("rent_growth_pct", "Crescita godimento beni di terzi", "percent"),
    ("other_costs_growth_pct", "Crescita oneri diversi", "percent"),
    ("dso_days", "DSO (giorni incasso)", "days"),
    ("dio_days", "Giorni materie prime e semilavorati (sul consumo)", "days"),
    ("dio_pf_days", "Giorni prodotti finiti e merci (sui ricavi)", "days"),
    ("dpo_days", "DPO (giorni pagamento)", "days"),
    ("tangible_investments", "Investimenti materiali", "eur"),
    ("intangible_investments", "Investimenti immateriali", "eur"),
    ("depreciation_rate", "Aliquota ammortamenti materiali", "percent"),
    ("depreciation_rate_intangible", "Aliquota ammortamenti immateriali", "percent"),
    ("tax_rate", "Aliquota fiscale", "percent"),
    ("inflation_pct", "Inflazione", "percent"),
)


# Campi dei passi 1-7 non ancora nella lista sopra (inventario del task 14). Un campo qui compare solo se
# l'utente l'ha scritto o se vale qualcosa: un default tutto a zero non e' un'ipotesi dichiarata.
_ASSUMPTIONS_EXTRA = (
    ("fixed_materials_percentage", "percent"), ("fixed_services_percentage", "percent"),
    ("fixed_materials_growth_pct", "percent"), ("fixed_services_growth_pct", "percent"),
    ("fixed_materials_growth_auto", "bool"), ("fixed_services_growth_auto", "bool"),
    ("variable_materials_growth_auto", "bool"), ("variable_services_growth_auto", "bool"),
    ("receivables_long_growth_pct", "percent"),
    ("bank_lines_amount", "eur"), ("bank_lines_rate", "percent"),
    ("existing_debt_repayment_years", "years"), ("altri_finanz_repayment_years", "years"),
    ("sp06e_growth_pct", "percent"), ("compensa_crediti_tributari", "bool"),
    ("sp01_growth_pct", "percent"), ("sp04_growth_pct", "percent"), ("sp08_growth_pct", "percent"),
    ("sp10_growth_pct", "percent"), ("sp14_growth_pct", "percent"), ("sp16f_growth_pct", "percent"),
    ("sp16g_growth_pct", "percent"), ("sp17d_growth_pct", "percent"), ("sp17f_growth_pct", "percent"),
    ("sp17g_growth_pct", "percent"), ("sp18_growth_pct", "percent"),
    ("tfr_accrual_suspended", "bool"), ("tfr_payments", "eur"),
    ("financing_amount", "eur"), ("financing_duration_years", "years"), ("financing_interest_rate", "percent"),
    ("asset_disposal_nbv", "eur"), ("asset_disposal_proceeds", "eur"),
    ("cash_sweep_enabled", "bool"), ("cash_sweep_min_cash", "eur"),
    ("overdraft_allowed", "bool"), ("overdraft_limit", "eur"),
    ("tax_advances_paid", "eur"), ("sp16e_growth_pct", "percent"), ("sp17e_growth_pct", "percent"),
)


def _etichetta(fld: str) -> str:
    from app.services.final_report_assumptions import FIELD_LABELS
    return FIELD_LABELS.get(fld, fld).replace(" %", "").strip()


def _numeric(v) -> Num:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    return None


def _ce01_overridden(report) -> bool:
    for s in report.assumption_sections:
        for a in s.assumptions:
            if a.field == "ce_overrides" and a.active:
                return any(o.field == "ce01_override" for year in a.values if year for o in year)
    return False


def _valori_ipotesi(a, plan_n: int) -> tuple:
    out = []
    for x in list(a.values)[:plan_n]:
        out.append(Decimal(int(x)) if isinstance(x, bool) else _numeric(x))
    return tuple(out) + (None,) * (plan_n - len(out))


#: ipotesi che il motore legge solo sulla riga del primo anno: si mostrano come valore unico per tutto il piano
_PRIMO_ANNO = ("bank_lines_amount", "bank_lines_rate")
#: il finanziamento «legacy» a un solo contratto: superato dalla tabella Finanziamenti
_FINANZIAMENTO_LEGACY = ("financing_amount", "financing_duration_years", "financing_interest_rate")


def _legacy_superato(by_field: dict) -> bool:
    """Tasso e durata legacy non si stampano se non c'è un finanziamento legacy (importo 0/assente) o se ci sono
    contratti in `financing_loans`: il tasso vero sta già nella tabella Finanziamenti."""
    loans = by_field.get("financing_loans")
    if loans is not None and loans.active and loans.financing_loans:
        return True
    amount = by_field.get("financing_amount")
    if amount is None or not amount.active:
        return True
    return all(not x for x in amount.values if not isinstance(x, bool))


def _unico_per_il_piano(vals: tuple) -> tuple:
    primo = next((x for x in vals if x is not None), None)
    return tuple(primo for _ in vals) if primo is not None else vals


def _assumptions(report, plan_n: int) -> tuple:
    by_field = {a.field: a for s in report.assumption_sections for a in s.assumptions}
    legacy_superato = _legacy_superato(by_field)
    growth, rows = {}, []
    for fld, label, unit in _ASSUMPTIONS:
        a = by_field.get(fld)
        if a is None or not a.active:
            continue
        vals = _valori_ipotesi(a, plan_n)
        if all(x is None for x in vals):
            continue
        growth[fld] = vals
        rows.append(AssumptionRow(label, unit, vals))
    for fld, unit in _ASSUMPTIONS_EXTRA:
        a = by_field.get(fld)
        if a is None or not a.active:
            continue
        if legacy_superato and fld in _FINANZIAMENTO_LEGACY:
            continue
        vals = _valori_ipotesi(a, plan_n)
        if fld in _PRIMO_ANNO:
            vals = _unico_per_il_piano(vals)
        if all(x is None for x in vals):
            continue
        if all(x == 0 for x in vals if x is not None) and a.provenance not in ("user", "override"):
            continue
        growth[fld] = vals
        rows.append(AssumptionRow(_etichetta(fld), unit, vals))
    return growth, rows


def _rate_positive(repayments) -> int:
    return sum(1 for r in (repayments or []) if r is not None and r > 0)


def _durata_prestito(ln) -> Optional[int]:
    """Durata dichiarata; con un calendario `repayments` e senza durata, il numero di rate positive."""
    if ln.duration_years:
        return ln.duration_years
    return _rate_positive(ln.repayments) or None


def _finanziamenti(report) -> tuple:
    """Tabella «Finanziamenti»: contratti del passo 5 (`financing_loans`, `other_lenders`), col tasso."""
    out = []
    for s in report.assumption_sections:
        for a in s.assumptions:
            if not a.active:
                continue
            for ln in (a.financing_loans or []) if a.field == "financing_loans" else []:
                nuovo = ln.amount is not None and ln.amount > 0
                if not nuovo and not (ln.opening_residual and ln.opening_residual > 0):
                    continue
                out.append(FinanziamentoRow(ln.name or "Finanziamento", "Nuovo" if nuovo else "Pregresso",
                                            ln.amount if nuovo else ln.opening_residual, ln.interest_rate,
                                            _durata_prestito(ln)))
            for ol in (a.other_lenders or []) if a.field == "other_lenders" else []:
                out.append(FinanziamentoRow(ol.name or "Altro finanziatore", "Altro finanziatore",
                                            ol.opening_residual, ol.interest_rate,
                                            _rate_positive(ol.repayments)))
    return tuple(out)


_PREFISSO_ETICHETTA = re.compile(r"^(?:[A-Z]{1,3}|\d+|[ivx]+)\)\s*")
_CODICE_VOCE = re.compile(r"^((?:sp|ce)\d{2}[a-z]?)(?:_(.*))?$")


def _etichette_voci(report) -> dict:
    """Codice breve (sp16f, ce06…) → etichetta di bilancio, dai prospetti dettagliati del report."""
    out = {}
    for st in report.detailed_statements:
        for r in st.rows:
            m = _CODICE_VOCE.match(r.code)
            if m and m.group(1) not in out:
                out[m.group(1)] = _PREFISSO_ETICHETTA.sub("", r.label.strip())
    return out


def _etichetta_voce(code: str, etichette: dict) -> str:
    """L'etichetta di bilancio di un codice interno; senza riga nel prospetto, il nome del codice leggibile."""
    m = _CODICE_VOCE.match(code.removesuffix("_override"))
    if not m:
        return code
    if m.group(1) in etichette:
        return etichette[m.group(1)]
    resto = (m.group(2) or "").replace("_", " ").strip()
    return resto.capitalize() if resto else code


def _raggruppa(coppie, etichette: dict, rende) -> str:
    """Una voce per codice (il contratto la ripete per ogni anno): i valori distinti restano, nell'ordine."""
    per_voce: dict = {}
    for code, val in coppie:
        visti = per_voce.setdefault(code, [])
        if val not in visti:
            visti.append(val)
    return ", ".join(f"{_etichetta_voce(c, etichette)}: " + " / ".join(rende(v) for v in vals)
                     for c, vals in per_voce.items())


def _puntuali(report) -> tuple:
    """Ipotesi nidificate che non hanno una riga per anno: piani di rientro, indicizzazioni, valori forzati."""
    out = []
    etichette = _etichette_voci(report)
    for s in report.assumption_sections:
        for a in s.assumptions:
            if not a.active:
                continue
            if a.field == "pregresso" and a.pregresso is not None:
                for nome, piano in a.pregresso.model_dump(exclude_none=True).items():
                    importi = " / ".join(fmt.eur(_numeric(x)) for x in piano.get("amounts", []))
                    out.append((f"Piano pregresso: {nome.replace('_', ' ')}",
                                f"residuo {fmt.eur(_numeric(piano.get('opening')))} · per anno {importi}"))
            elif a.field == "sp_indexing" and a.sp_indexing:
                voci = ", ".join(dict.fromkeys(f"{_etichetta_voce(i.field, etichette)} → {i.driver}"
                                               for i in a.sp_indexing))
                out.append(("Voci indicizzate", voci))
            elif a.field == "sp_overrides" and a.sp_overrides:
                out.append(("Valori forzati SP previsionale",
                            _raggruppa([(o.field, o.value) for o in a.sp_overrides], etichette, fmt.eur)))
            elif a.field == "ce_overrides" and a.ce_overrides:
                out.append(("Valori forzati CE previsionale",
                            _raggruppa([(o.field, o.value) for o in a.ce_overrides], etichette, fmt.eur)))
    return tuple(out)


def _avvisi_motore(report) -> tuple:
    visti, out = set(), []
    for d in report.diagnostics:
        if d.code == "engine_avviso" and d.message not in visti:
            visti.add(d.message)
            out.append(d.message)
    return tuple(out)


# ------------------------------------------------------------------ allegati e indicatori
_DUPLICATI_E = {"analytical.profitability.roe", "analytical.profitability.roi", "analytical.profitability.ros",
                "analytical.profitability.ebitda_margin"}


def _annex(statement, cols) -> tuple:
    pids = [p.id for p in statement.periods]
    rows, zero = [], []
    for r in statement.rows:
        vals = tuple(r.values[pids.index(c.period_id)] if c.period_id in pids else None for c in cols)
        if r.kind == "detail" and all(v is None or v == 0 for v in vals):
            zero.append(r.label.strip())
            continue
        rows.append(AnnexRow(r.label.strip(), r.level, r.kind, vals))
    return tuple(rows), tuple(zero)


# I 15 indicatori della pratica (contracts/final_report_dossier_catalog.json › practice_indicators), in quell'ordine.
# Il catalogo v2 aggiunge altri `practice.*` (incidenze, aliquota, margine EBIT, liquidità immediata) che l'Allegato D
# del riferimento non stampa.
_PRACTICE_D = tuple("practice." + k for k in ("dscr", "ebitda_margin", "mt", "ccn", "current_ratio", "ms",
                                              "copertura_immob", "indipendenza", "pfn", "pfn_ebitda", "roi", "roe",
                                              "ros", "of_mol", "of_revenue"))


# Indicatori che su un periodo parziale (m < 12 mesi) si mostrano anche annualizzati, con il fattore che si applica
# al valore del periodo: il ROI è un flusso su uno stock (× 12/m), la PFN/EBITDA ha lo stock al numeratore e il
# flusso al denominatore (× m/12). Chiave del catalogo -> (etichetta annualizzata, fattore in funzione di m).
_ANNUALIZZATI = {
    "roi": ("ROI (annualizzato)", lambda m: Decimal(12) / Decimal(m)),
    "pfn_ebitda": ("PFN / EBITDA (annualizzato)", lambda m: Decimal(m) / Decimal(12)),
}


def _annualizza(rows: tuple, keys: tuple, m: int | None, adj_i: int | None) -> tuple:
    """Dopo ogni riga `keys[i]` inserisce la versione annualizzata. La colonna del periodo parziale (`adj_i`) è
    scalata, le colonne di 12 mesi ripetono il valore; un valore assente resta assente (n.d.).
    Senza periodo parziale (m >= 12 o assente, colonna assente) restituisce le righe com'erano."""
    if not m or m >= 12 or adj_i is None:
        return rows
    out = []
    for key, row in zip(keys, rows):
        out.append(row)
        if key in _ANNUALIZZATI:
            label, factor = _ANNUALIZZATI[key]
            vals = tuple(None if v is None else (v * factor(m) if i == adj_i else v)
                         for i, v in enumerate(row.values))
            out.append(IndicatorRow(label, row.unit, vals))
    return tuple(out)


def _indicators(report, ids, pids: list) -> tuple:
    by_id = {ind.id: ind for ind in report.indicator_catalog}
    out = []
    for identifier in ids:
        ind = by_id.get(identifier)
        if ind is None:
            continue
        by = dict(zip([p.id for p in ind.periods], ind.values))
        out.append(IndicatorRow(ind.label, ind.unit, tuple(by.get(pid) for pid in pids)))
    return tuple(out)


# ------------------------------------------------------------------ punto di partenza
_CE_LINES = (("Ricavi", "ricavi", ""), ("Altri ricavi e variazioni", "altri_ricavi_var", ""),
             ("Costi operativi", "costi_operativi", ""), ("EBITDA", "ebitda", "bold"),
             ("Ammortamenti", "ammortamenti", ""), ("EBIT", "ebit", "bold"), ("Oneri finanziari", "oneri_fin", ""),
             ("Risultato ante imposte", "ante_imposte", ""), ("Imposte", "imposte", ""),
             ("Risultato netto", "utile", "hl"))
_START_IND = (("EBITDA margin", "ebitda_margin"), ("ROS", "ros"), ("ROI", "roi"), ("ROE", "roe"),
              ("Margine di tesoreria", "margine_tesoreria"), ("CCN", "ccn"),
              ("Liquidità corrente", "liquidita_corrente"), ("Margine di struttura", "margine_struttura"),
              ("Copertura immobilizzazioni", "copertura_immob"), ("Indipendenza finanziaria", "indipendenza"),
              ("PFN", "pfn"), ("PFN / EBITDA", "pfn_ebitda"))
_PIANO = {1: "annuale", 2: "biennale", 3: "triennale", 4: "quadriennale", 5: "quinquennale"}


def _checks(lk: _Lookup, cols, report) -> tuple:
    out = []
    diffs = [(c.label, lk.rows.get(DIFF_ROW, {}).get(c.period_id)) for c in cols]
    known = [(label, d) for label, d in diffs if d is not None]
    bad = [(label, d) for label, d in known if abs(d) > Decimal("0.01")]
    if not known:
        out.append(("Attivo = passivo e patrimonio netto", "Controllo non disponibile."))
    elif bad:
        worst = max(abs(d) for _, d in bad)
        out.append(("Attivo = passivo e patrimonio netto",
                    f"Non quadra in {', '.join(label for label, _ in bad)}: differenza massima € {fmt.eur(worst)}."))
    else:
        out.append(("Attivo = passivo e patrimonio netto", f"Quadra su {len(known)} periodi rappresentati."))
    cash, cash_bad = [], []
    for c in cols:
        b, t, e = (lk.get(k, c.period_id) for k in ("cassa_inizio", "cf_variazione", "cassa_fine"))
        if None in (b, t, e):
            continue
        cash.append(c.label)
        if abs(b + t - e) > Decimal("0.01"):
            cash_bad.append(c.label)
    if not cash:
        out.append(("Cassa iniziale + flussi = cassa finale", "Rendiconto non disponibile."))
    elif cash_bad:
        out.append(("Cassa iniziale + flussi = cassa finale", f"Non verificato in {', '.join(cash_bad)}."))
    else:
        out.append(("Cassa iniziale + flussi = cassa finale", f"Verificato su {len(cash)} periodi."))
    if report.practice.workflow_type == "infrannuale":
        n = len(report.adjustments.entries)
        out.append(("Rettifiche", f"{n} rettifiche confermate." if report.adjustments.confirmed
                    else f"{n} rettifiche, non confermate."))
    return tuple(out)


def _plan_sources(periods) -> tuple:
    years = [p.year for p in periods if p.basis == "forecast"]
    if not years:
        return ()
    span = f"{years[0]}–{years[-1]}" if len(years) > 1 else str(years[0])
    return (("Assunzioni del piano", span, "disponibile"),)


def rettifiche_registrate(entries) -> tuple:
    """Le rettifiche del giornale come righe di tabella, con le etichette di bilancio e mai i codici interni."""
    return tuple((e.edited_label, fmt.eur(e.edit_delta),
                  e.counterpart_label + (f" ({fmt.eur(e.counterpart_delta)})" if e.counterpart_delta else ""), (e.explanation or "").strip() or "—")
                 for e in entries)


def _starting_infrannuale(report, lk, cols, periods) -> StartingPoint:
    obs = next(p for p in periods if p.basis == "observed")
    adj = next(p for p in periods if p.basis == "adjusted")
    clo = next(p for p in periods if p.basis == "closing")
    m, y = adj.period_months, adj.year
    g = lambda k, p: lk.get(k, p.id)  # noqa: E731
    prima_dopo = tuple((label, (g(k, obs), _sub(g(k, adj), g(k, obs)), g(k, adj)), style)
                       for label, k, style in _CE_LINES)
    ponte = tuple((label, (g(k, adj), _sub(g(k, clo), g(k, adj)), g(k, clo)), style)
                  for label, k, style in _CE_LINES)
    n_rett = len(report.adjustments.entries)
    e_eff = _sub(g("utile", adj), g("utile", obs))
    tiles = (
        (fmt.compact_eur(g("ricavi", adj)), f"Ricavi {m}M {y}", f"periodo osservato: {m} mesi"),
        (fmt.compact_eur(g("ebitda", adj)), f"EBITDA {m}M rettificato",
         f"{fmt.compact_eur(g('ebitda', obs))} prima delle rettifiche"),
        (fmt.compact_eur(g("utile", adj)), f"Utile {m}M rettificato", f"effetto rettifiche: {fmt.compact_eur(e_eff)}"),
        (fmt.compact_eur(g("ebitda", clo)), f"EBITDA forecast {y}",
         f"EBITDA margin {fmt.pct(g('ebitda_margin', clo))}"),
    )
    end = report.infrannual_closing.period_end if report.infrannual_closing else None
    end_txt = end.strftime("%d.%m.%Y") if end else f"{m} mesi"
    return StartingPoint(
        kind="infrannuale",
        title=f"Punto di partenza: infrannuale, rettifiche e forecast {y}",
        intro=(f"La base del piano è il forecast {y}, ottenuto dal bilancio infrannuale al {end_txt} "
               f"({m} mesi) rettificato più la stima del periodo residuo."),
        tiles=tiles,
        tables=(
            TableBlock("Bilancio infrannuale: prima e dopo le rettifiche", ("Prima", "Rettifiche", "Dopo"), prima_dopo,
                       f"{n_rett} rettifiche. Il progressivo di {m} mesi non è direttamente comparabile "
                       "con un esercizio completo."),
            TableBlock(f"Dal progressivo rettificato al forecast {y}",
                       (f"{m}M rettificato", "Stimato residuo", f"Forecast {y}"), ponte),
        ),
        indicator_headers=(f"{m}M {y} rettificato", f"Forecast {y}"),
        indicators=_annualizza(
            tuple(IndicatorRow(label, UNITS.get(k, "eur"), (g(k, adj), g(k, clo))) for label, k in _START_IND),
            tuple(k for _, k in _START_IND), m, 0),
        checks=_checks(lk, cols, report), rettifiche=rettifiche_registrate(report.adjustments.entries),
        note=f"Periodi di durata diversa ({m} mesi e 12 mesi): gli indicatori reddituali vanno letti tenendo conto "
             f"di questa differenza. Per il periodo di {m} mesi ROI e PFN / EBITDA compaiono sia sul periodo sia "
             f"annualizzati (ROI × 12/{m}, PFN / EBITDA × {m}/12).",
        sources=(("Bilancio di verifica", f"{m}M {y}", "disponibile"),
                 ("Registro rettifiche", f"{n_rett} eventi",
                  "confermato" if report.adjustments.confirmed else "da confermare"),
                 (f"Forecast {y}", f"31.12.{y}", "stimato")) + _plan_sources(periods),
    )


def _starting_bilancio(report, lk, cols, periods) -> StartingPoint:
    hist = [p for p in periods if p.basis == "historical"]
    base = hist[-1]
    prev = hist[-2] if len(hist) > 1 else None
    g = lambda k, p: lk.get(k, p.id)  # noqa: E731
    if prev:
        headers = (f"{prev.year} C", f"{base.year} C", "Variazione")
        rows = tuple((label, (g(k, prev), g(k, base), _sub(g(k, base), g(k, prev))), style)
                     for label, k, style in _CE_LINES)
        ind_headers, ind_pids = (f"{prev.year} C", f"{base.year} C"), (prev, base)
    else:
        headers = (f"{base.year} C",)
        rows = tuple((label, (g(k, base),), style) for label, k, style in _CE_LINES)
        ind_headers, ind_pids = (f"{base.year} C",), (base,)
    da = f"da {fmt.compact_eur(g('ricavi', prev))} nel {prev.year}" if prev else "ultimo esercizio depositato"
    tiles = (
        (fmt.compact_eur(g("ricavi", base)), f"Ricavi {base.year}", da),
        (fmt.compact_eur(g("ebitda", base)), f"EBITDA {base.year}", f"EBITDA margin {fmt.pct(g('ebitda_margin', base))}"),
        (fmt.compact_eur(g("utile", base)), f"Utile {base.year}", "risultato d'esercizio"),
        (fmt.compact_eur(g("pfn", base)), f"PFN {base.year}", "debiti finanziari − liquidità"),
    )
    return StartingPoint(
        kind="bilancio", title=f"Punto di partenza: bilancio {base.year}",
        intro=f"La base del piano è il bilancio d'esercizio {base.year}, confrontato con l'esercizio precedente.",
        tiles=tiles,
        tables=(TableBlock(f"Conto economico di partenza", headers, rows),),
        indicator_headers=ind_headers,
        indicators=tuple(IndicatorRow(label, UNITS.get(k, "eur"), tuple(g(k, p) for p in ind_pids))
                         for label, k in _START_IND),
        checks=_checks(lk, cols, report), note="",
        sources=tuple((f"Bilancio {p.year}", f"31.12.{p.year}", "consuntivo") for p in ind_pids)
        + _plan_sources(periods),
    )


def _starting_startup(report, lk, cols, periods) -> StartingPoint:
    hist = [p for p in periods if p.basis == "historical"]
    first = next(p for p in periods if p.basis == "forecast")
    g = lambda k, p: lk.get(k, p.id)  # noqa: E731
    tables = ()
    if hist:
        o = hist[-1]
        tables = (TableBlock(f"Bilancio d'apertura {o.year}", (f"Apertura {o.year}",),
                             (("Capitale sociale", (g("capitale", o),), ""),
                              ("Disponibilità liquide", (g("liquidita", o),), ""),
                              ("Totale attivo", (g("totale_attivo", o),), "hl"))),)
    n = len([p for p in periods if p.basis == "forecast"])
    tiles = (
        (fmt.compact_eur(g("capitale", hist[-1]) if hist else None), "Capitale sociale", "all'apertura"),
        (fmt.compact_eur(g("liquidita", hist[-1]) if hist else None), "Liquidità iniziale", "all'apertura"),
        (fmt.compact_eur(g("ricavi", first)), f"Ricavi {first.year}", "primo anno di piano"),
        (str(n), "Anni di piano", f"dal {first.year}"),
    )
    return StartingPoint(kind="startup", title="Punto di partenza: apertura della startup",
                         intro="La startup parte dal bilancio d'apertura: non esiste un esercizio precedente.",
                         tiles=tiles, tables=tables, indicator_headers=(), indicators=(),
                         checks=_checks(lk, cols, report), note="",
                         sources=((f"Bilancio d'apertura {hist[-1].year}", str(hist[-1].year), "disponibile"),)
                         * bool(hist) + _plan_sources(periods))


# ------------------------------------------------------------------ ingresso
def from_report(report, *, draft: bool) -> BusinessPlanData:
    wf = report.practice.workflow_type
    periods = report.detailed_statements[0].periods
    plan = [p for p in periods if p.basis == "forecast"]
    if wf == "infrannuale":
        base = next((p for p in periods if p.basis == "closing"), None)
    elif wf == "bilancio":
        base = ([p for p in periods if p.basis == "historical"] or [None])[-1]
    else:
        base = None
    cols = ([Column(base.id, base.year, f"{base.year} {'F' if base.basis == 'closing' else 'C'}", True)]
            if base else []) + [Column(p.id, p.year, f"{p.year} P", False) for p in plan]
    cols = tuple(cols)
    lk = _Lookup(report)
    values = {k: tuple(lk.get(k, c.period_id) for c in cols) for k in VALUE_KEYS}
    growth, rows = _assumptions(report, len(plan))
    revenue_overridden = _ce01_overridden(report)
    plan_pids = [p.id for p in plan]
    # Righe calcolate: una riga che vale zero in ogni anno di piano non e' un'ipotesi e non esce
    # («Rimborso debito 2027: 0»); le righe d'input a zero restano, se l'utente le ha scritte.
    for label, unit, key in (("Costi operativi / ricavi", "percent", "opex_ricavi"),
                             ("Proventi finanziari", "eur", "proventi_fin"),
                             ("Ammortamenti", "eur", "ammortamenti"),
                             ("Rimborso debito", "eur", "cf_rimborsi")):
        vals = tuple(lk.get(key, pid) for pid in plan_pids)
        if all((v or 0) == 0 for v in vals):
            continue
        rows.append(AssumptionRow(label, unit, vals))

    n_word = _PIANO.get(len(plan), f"di {len(plan)} anni")
    partial_label = partial_dscr = residual = None
    adj = next((p for p in periods if p.basis == "adjusted"), None)
    if wf == "infrannuale" and adj is not None and base is not None:
        partial_label = f"{adj.period_months}M {adj.year} R"
        partial_dscr = lk.get("dscr", adj.id)
        residual = _sub(lk.get("ricavi", base.id), lk.get("ricavi", adj.id))
        end = report.infrannual_closing.period_end if report.infrannual_closing else None
        end_txt = f"al {end.strftime('%d.%m.%Y')} " if end else ""
        base_description = (f"Base: bilancio infrannuale {end_txt}({adj.period_months} mesi) · forecast {base.year} "
                            f"· piano {n_word}")
        starting = _starting_infrannuale(report, lk, cols, periods)
    elif wf == "bilancio" and base is not None:
        base_description = f"Base: bilancio d'esercizio {base.year} · piano {n_word}"
        starting = _starting_bilancio(report, lk, cols, periods)
    else:
        base_description = f"Startup · piano {n_word} dal {plan[0].year}"
        starting = _starting_startup(report, lk, cols, periods)

    ce, sp, cf = report.detailed_statements
    annex, zero = {}, {}
    for st in (ce, sp, cf):
        annex[st.id], zero[st.id] = _annex(st, cols)
    d_pids = [c.period_id for c in cols]
    d_headers = tuple(c.label for c in cols)
    d_adj = None
    present_ids = {ind.id for ind in report.indicator_catalog}
    if partial_label and len(cols) + 1 <= 6:
        d_pids, d_headers, d_adj = [adj.id] + d_pids, (partial_label,) + d_headers, 0
    return BusinessPlanData(
        company_name=report.company.name, workflow=wf, columns=cols, base_description=base_description,
        values=values, growth=growth, revenue_overridden=revenue_overridden, assumptions=tuple(rows), partial_label=partial_label,
        partial_dscr=partial_dscr, residual_revenue=residual, starting_point=starting,
        annex=annex, annex_zero_labels=zero,
        indicators_practice_headers=d_headers,
        indicators_practice=_annualizza(
            _indicators(report, _PRACTICE_D, d_pids),
            tuple(k.removeprefix("practice.") for k in _PRACTICE_D if k in present_ids),
            adj.period_months if adj is not None else None, d_adj),
        indicators_analytical=_indicators(
            report, [i.id for i in report.indicator_catalog
                     if i.id.startswith("analytical.") and i.id not in _DUPLICATI_E],
            [c.period_id for c in cols]),
        draft=draft,
        avvisi=_avvisi(report), finanziamenti_tabella=_finanziamenti(report),
        ipotesi_puntuali=_puntuali(report), avvisi_motore=_avvisi_motore(report),
    )


# ------------------------------------------------------------------ JSON del banco
def _enc(v):
    return None if v is None else str(v)


def _dec(v):
    return None if v is None else Decimal(v)


def dump_json(data: BusinessPlanData) -> dict:
    """Solo i campi che le sezioni economiche leggono: il banco non serializza allegati e punto di partenza."""
    return {
        "company_name": data.company_name, "workflow": data.workflow,
        "columns": [c.__dict__ for c in data.columns], "base_description": data.base_description,
        "values": {k: [_enc(x) for x in v] for k, v in data.values.items()},
        "growth": {k: [_enc(x) for x in v] for k, v in data.growth.items()},
        "revenue_overridden": data.revenue_overridden,
        "partial_label": data.partial_label, "partial_dscr": _enc(data.partial_dscr),
        "residual_revenue": _enc(data.residual_revenue), "draft": data.draft,
    }


def load_json(path) -> BusinessPlanData:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return BusinessPlanData(
        company_name=raw["company_name"], workflow=raw["workflow"],
        columns=tuple(Column(**c) for c in raw["columns"]), base_description=raw["base_description"],
        values={k: tuple(_dec(x) for x in v) for k, v in raw["values"].items()},
        growth={k: tuple(_dec(x) for x in v) for k, v in raw.get("growth", {}).items()},
        revenue_overridden=raw.get("revenue_overridden", False),
        partial_label=raw.get("partial_label"), partial_dscr=_dec(raw.get("partial_dscr")),
        residual_revenue=_dec(raw.get("residual_revenue")), draft=raw.get("draft", False),
    )
