"""Gruppo DATI (v4 pagine 3-6, solo workflow infrannuale): bilancio infrannuale
e fonti, rettifiche apportate, dall'infrannuale alla chiusura, indicatori
dell'infrannuale. Il gruppo esiste solo quando `report.practice.workflow_type
== "infrannuale"`: nel bilancio/startup queste quattro pagine non hanno una
fonte nel modello (niente `observed:{anno}`/`adjusted:{anno}`/`closing:{anno}`
né `infrannual_closing`), quindi `build()` ritorna una lista vuota — niente
pagine vuote, niente voce d'indice.

Vincolo del proprietario da rispettare (`m2-02d.md`, 2026-09-17 sera): la
pagina «rettifiche» resta al minimo — 4 KPI + grafico prima/dopo + UNA
tabella di 9 righe sugli aggregati (Ricavi, Costi operativi, EBITDA,
Ammortamenti, EBIT, Oneri finanziari, Risultato ante imposte, Imposte,
Risultato netto) con colonne Prima · Rettifiche · Dopo — niente
contropartite, niente saldi prima/dopo per voce di dettaglio, niente periodi
di confronto. Le stesse 9 righe aggregate ricorrono, con basi diverse, sulle
pagine «fonti» (solo osservato) e «chiusura» (rettificato/stimato/chiusura).

Nota per chi tocca questo file: il grafico «prima/dopo» (pag. 4), quello del
«passaggio alla chiusura» (pag. 5) e il confronto rettificato→chiusura degli
indicatori (pag. 6) sono tutti resi come grafici a barre raggruppate — un
`kind: "chart"` standard che `comuni.typ` già dispatcha, con l'id registrato
in `chart-layout.json`'s `bars` — non un vero dumbbell con due punti connessi
per indicatore: quella forma non esiste ancora nell'infrastruttura Typst
condivisa (vedi `pagine/dati.typ`) e costruirla avrebbe richiesto toccare
`pagine/comuni.typ`/`editorial.typ`, file di dispatch comuni a tutti i gruppi
(anche `indicatori.py`, che ha lo stesso bisogno alle pagine 12-17). La barra
raggruppata comunica lo stesso confronto a due punti per categoria; un vero
dumbbell resta un miglioramento visivo per chi arriva dopo, non un buco.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2
from app.services.final_report_dossier import CATALOG

from . import shared as s

GROUP = "dati"

FAMILY = "Dati di partenza"

# Le nove righe aggregate condivise dalle pagine «fonti», «rettifiche» e
# «chiusura» (vincolo del proprietario). `codes` è `None` per «Costi
# operativi»: non è una riga del prospetto, è la somma delle voci canoniche
# di B) esclusi gli ammortamenti (`_operating_costs`, sotto) — la stessa
# somma che il prospetto stampato chiama «Totale Costi della Produzione»
# meno «Totale ammortamenti e svalutazioni».
_AGGREGATE_ROWS: tuple[tuple[str, str, tuple[str, ...] | None], ...] = (
    ("ricavi", "Ricavi", ("ce01_ricavi_vendite",)),
    ("costi-operativi", "Costi operativi", None),
    ("ebitda", "EBITDA", ("ebitda",)),
    ("ammortamenti", "Ammortamenti", ("ce09_ammortamenti",)),
    ("ebit", "EBIT", ("ebit",)),
    ("oneri-finanziari", "Oneri finanziari", ("ce15_oneri_finanziari",)),
    ("risultato-ante-imposte", "Risultato ante imposte", ("profit_before_tax",)),
    ("imposte", "Imposte", ("ce20_imposte",)),
    ("risultato-netto", "Risultato netto", ("net_profit",)),
)

_OPERATING_COST_CODES = (
    "ce05_materie_prime", "ce06_servizi", "ce07_godimento_beni", "ce08_costi_personale",
    "ce10_var_rimanenze_mat_prime", "ce11_accantonamenti", "ce11b_altri_accantonamenti",
    "ce12_oneri_diversi",
)

_PRIMA_DOPO_ROWS = (("ce01_ricavi_vendite", "Ricavi"), ("ebitda", "EBITDA"), ("net_profit", "Utile netto"))

_INDICATOR_TABLE_IDS = (
    "practice.mt", "practice.ccn", "practice.current_ratio", "practice.ms",
    "practice.copertura_immob", "practice.indipendenza", "practice.pfn", "practice.pfn_ebitda",
)

_DUMBBELL_IDS = ("practice.ebitda_margin", "practice.ros", "practice.roi", "practice.roe")


# ── Basis-period helpers (observed/adjusted/closing), local a questo gruppo ─
# Non condivisi in `shared.py`: solo queste quattro pagine leggono la stessa
# statement su tre basi distinte per lo stesso anno.


def _period(statement: Any, basis: str) -> Any:
    for period in statement.periods:
        if period.basis == basis:
            return period
    return None


def _row_value(statement: Any, code: str, period: Any) -> Any:
    if period is None:
        return None
    row_obj = s.statement_row(statement, code)
    return s.values_for_periods(row_obj, statement, [period])[0]


def _operating_costs(statement: Any, period: Any) -> Any:
    if period is None:
        return None
    values = [_row_value(statement, code, period) for code in _OPERATING_COST_CODES]
    if all(value is None for value in values):
        return None
    return sum((value for value in values if value is not None), Decimal("0"))


def _aggregate_value(statement: Any, codes: tuple[str, ...] | None, period: Any) -> Any:
    if codes is None:
        return _operating_costs(statement, period)
    return _row_value(statement, codes[0], period)


def _delta(before: Any, after: Any) -> Any:
    return (after - before) if before is not None and after is not None else None


def _column_label(period: Any) -> str:
    if period is None:
        return ""
    if period.period_months is not None and period.period_months < 12:
        return f"{period.period_months}M {period.year}"
    return str(period.year)


def _bar_chart(chart_id: str, title: str, unit: str, categories: list[str],
              series: list[tuple[str, list[Any]]]) -> dict[str, Any] | None:
    built = [{"label": label, "values": [s.exact(v) for v in values]}
             for label, values in series if any(v is not None for v in values)]
    if not built:
        return None
    return {"id": chart_id, "title": title, "unit": unit, "categories": categories,
            "series": built, "indicator_ids": [], "thresholds": [], "kind": "bar"}


# ── Pagina 3 — Bilancio infrannuale e fonti ─────────────────────────────────


def _fonti(report: FinalReportModelV2) -> dict[str, Any] | None:
    statement = s.statement_by_id(report, "income_statement")
    observed = _period(statement, "observed")
    closing_info = report.infrannual_closing
    months = observed.period_months if observed is not None else None
    kpis = [kpi for kpi in (
        s.kpi("data del bilancio infrannuale", closing_info.period_end.strftime("%d.%m.%Y"))
            if closing_info is not None else None,
        s.kpi("periodo osservato", f"{months} mesi") if months is not None else None,
        s.kpi("ricavi prima delle rettifiche", _row_value(statement, "ce01_ricavi_vendite", observed), "eur"),
        s.kpi("EBITDA prima delle rettifiche", _row_value(statement, "ebitda", observed), "eur"),
    ) if kpi is not None]
    items: list[dict[str, Any]] = []
    if observed is not None:
        items.append(_fonti_table(statement, observed))
    items.append(_perimetro_table(report, statement, observed))
    if not items:
        return None
    return {"id": "fonti", "title": "Bilancio infrannuale e fonti", "family": FAMILY, "form": "rail+main",
            "subtitle": "Il conto economico di verifica precede le rettifiche; il progressivo non è "
                        "direttamente comparabile con un esercizio completo.",
            "kpis": kpis, "items": items}


def _fonti_table(statement: Any, observed: Any) -> dict[str, Any]:
    columns = ["Voce", _column_label(observed)]
    rows = []
    for key, display_label, codes in _AGGREGATE_ROWS:
        value = _aggregate_value(statement, codes, observed)
        rows.append(s.row(f"fonti-ce:{key}", [display_label, value], [None, "eur"]))
    return s.table("fonti-ce", "Conto economico di partenza", columns, rows)


def _perimetro_table(report: FinalReportModelV2, statement: Any, observed: Any) -> dict[str, Any]:
    closing = _period(statement, "closing")
    forecast_years = report.practice.periods.forecast_years
    forecast_period = "n.d." if not forecast_years else (
        str(forecast_years[0]) if len(forecast_years) == 1
        else f"{forecast_years[0]}–{forecast_years[-1]}")
    n_entries = len(report.adjustments.entries)
    rows = [
        s.row("fonti-perimetro:verifica", ["Bilancio di verifica",
            _column_label(observed) if observed is not None else "n.d.",
            "disponibile" if observed is not None else "non disponibile"]),
        s.row("fonti-perimetro:rettifiche", ["Registro rettifiche",
            f"{n_entries} evento" if n_entries == 1 else f"{n_entries} eventi",
            "confermato" if report.adjustments.confirmed else "non confermato"]),
        s.row("fonti-perimetro:chiusura", ["Chiusura attesa",
            closing.period_end.strftime("%d.%m.%Y") if closing is not None and closing.period_end is not None
            else "n.d.", "stimata"]),
        s.row("fonti-perimetro:piano", ["Ipotesi del piano", forecast_period,
            "disponibile" if report.forecast.years else "non disponibile"]),
    ]
    return s.table("fonti-perimetro", "Perimetro delle fonti", ["Fonte", "Periodo", "Stato"], rows)


# ── Pagina 4 — Rettifiche apportate ─────────────────────────────────────────


def _rettifiche(report: FinalReportModelV2) -> dict[str, Any] | None:
    statement = s.statement_by_id(report, "income_statement")
    observed = _period(statement, "observed")
    adjusted = _period(statement, "adjusted")
    months = observed.period_months if observed is not None else None
    ebitda_obs = _row_value(statement, "ebitda", observed)
    ebitda_adj = _row_value(statement, "ebitda", adjusted)
    net_obs = _row_value(statement, "net_profit", observed)
    net_adj = _row_value(statement, "net_profit", adjusted)
    utile_label = f"utile {months}M rettificato" if months is not None else "utile rettificato"
    kpis = [kpi for kpi in (
        s.kpi("rettifiche economiche", len(report.adjustments.entries)),
        s.kpi("effetto sull'EBITDA", _delta(ebitda_obs, ebitda_adj), "eur"),
        s.kpi("effetto sul risultato netto", _delta(net_obs, net_adj), "eur"),
        s.kpi(utile_label, net_adj, "eur"),
    ) if kpi is not None]
    categories = [label for _, label in _PRIMA_DOPO_ROWS]
    prima = [_row_value(statement, code, observed) for code, _ in _PRIMA_DOPO_ROWS]
    dopo = [_row_value(statement, code, adjusted) for code, _ in _PRIMA_DOPO_ROWS]
    chart = _bar_chart("rettifiche-prima-dopo", "Prima e dopo le rettifiche", "eur", categories,
                       [("Prima", prima), ("Dopo", dopo)])
    items: list[dict[str, Any]] = []
    block = s.chart_block("rettifiche-prima-dopo", "Prima e dopo le rettifiche", chart, kpis)
    if block is not None:
        items.append(block)
    items.append(_riconciliazione_table(statement, observed, adjusted))
    # Il rimando all'Allegato D sta nel sottotitolo, non in un blocco «note» a
    # parte: quattro KPI + grafico con colonna KPI e tabella valori + una
    # tabella a 9 righe già riempiono la pagina fino al bordo su dati reali
    # (misurato su AMBIENTA) — un blocco in più trabocca su una seconda
    # pagina fisica orfana, senza intestazione, che viola l'invariante «una
    # pagina fisica per voce di catalogo».
    return {"id": "rettifiche", "title": "Rettifiche apportate", "family": FAMILY, "form": "rail+main",
            "subtitle": "Il confronto rende visibile l'effetto delle rettifiche confermate sui valori di "
                        "partenza, senza contropartite; il dettaglio di ciascuna è nell'Allegato D.",
            "kpis": [] if block is not None else kpis, "items": items}


def _riconciliazione_table(statement: Any, observed: Any, adjusted: Any) -> dict[str, Any]:
    columns = ["Voce", "Prima", "Rettifiche", "Dopo"]
    rows = []
    for key, display_label, codes in _AGGREGATE_ROWS:
        prima = _aggregate_value(statement, codes, observed)
        dopo = _aggregate_value(statement, codes, adjusted)
        delta = _delta(prima, dopo)
        rows.append(s.row(f"rettifiche-riconciliazione:{key}", [display_label, prima, delta, dopo],
                          [None, "eur", "eur", "eur"]))
    return s.table("rettifiche-riconciliazione", "Riconciliazione del progressivo", columns, rows)


# ── Pagina 5 — Dall'infrannuale alla chiusura ───────────────────────────────


def _chiusura(report: FinalReportModelV2) -> dict[str, Any] | None:
    statement = s.statement_by_id(report, "income_statement")
    adjusted = _period(statement, "adjusted")
    closing = _period(statement, "closing")
    ricavi_adj = _row_value(statement, "ce01_ricavi_vendite", adjusted)
    ricavi_close = _row_value(statement, "ce01_ricavi_vendite", closing)
    ebitda_adj = _row_value(statement, "ebitda", adjusted)
    ebitda_close = _row_value(statement, "ebitda", closing)
    ricavi_residuo = _delta(ricavi_adj, ricavi_close)
    ebitda_residuo = _delta(ebitda_adj, ebitda_close)
    kpis = [kpi for kpi in (
        s.kpi("ricavi osservati rettificati", ricavi_adj, "eur"),
        s.kpi("ricavi stimati · periodo residuo", ricavi_residuo, "eur"),
        s.kpi("ricavi di chiusura", ricavi_close, "eur"),
        s.kpi("EBITDA di chiusura", ebitda_close, "eur"),
    ) if kpi is not None]
    categories = ["Rettificato", "Stimato residuo", "Chiusura"]
    chart = _bar_chart("chiusura-passaggio", "Il passaggio alla chiusura", "eur", categories,
                       [("Ricavi", [ricavi_adj, ricavi_residuo, ricavi_close]),
                        ("EBITDA", [ebitda_adj, ebitda_residuo, ebitda_close])])
    items: list[dict[str, Any]] = []
    block = s.chart_block("chiusura-passaggio", "Il passaggio alla chiusura", chart, kpis)
    if block is not None:
        items.append(block)
    items.append(_chiusura_table(statement, adjusted, closing))
    return {"id": "chiusura", "title": "Dall'infrannuale alla chiusura", "family": FAMILY, "form": "rail+main",
            "subtitle": "Il progressivo rettificato più la stima del periodo residuo compone la "
                        "chiusura attesa, base del piano.",
            "kpis": [] if block is not None else kpis, "items": items}


def _chiusura_table(statement: Any, adjusted: Any, closing: Any) -> dict[str, Any]:
    columns = ["Voce", "Rettificato", "Stimato residuo", "Chiusura"]
    rows = []
    for key, display_label, codes in _AGGREGATE_ROWS:
        rettificato = _aggregate_value(statement, codes, adjusted)
        chiusura = _aggregate_value(statement, codes, closing)
        residuo = _delta(rettificato, chiusura)
        rows.append(s.row(f"chiusura-passaggio-tabella:{key}", [display_label, rettificato, residuo, chiusura],
                          [None, "eur", "eur", "eur"]))
    return s.table("chiusura-passaggio-tabella", "Dal progressivo alla base del piano", columns, rows)


# ── Pagina 6 — Indicatori dell'infrannuale ──────────────────────────────────


def _indicatori_infrannuali(report: FinalReportModelV2) -> dict[str, Any] | None:
    statement = s.statement_by_id(report, "income_statement")
    adjusted = _period(statement, "adjusted")
    closing = _period(statement, "closing")
    n_indicators = len(CATALOG["practice_indicators"])
    kpis = [kpi for kpi in (
        s.kpi("indicatori della pratica", n_indicators),
        _kpi_indicator_at(report, "practice.ebitda_margin", adjusted, "EBITDA margin · rettificato"),
        _kpi_indicator_at(report, "practice.ebitda_margin", closing, "EBITDA margin · chiusura"),
        s.kpi("periodi di durata diversa", f"{adjusted.period_months} mesi", to=f"{closing.period_months} mesi")
            if adjusted is not None and closing is not None else None,
    ) if kpi is not None]
    chart = _confronto_chart(report, adjusted, closing)
    items: list[dict[str, Any]] = []
    block = s.chart_block("indicatori-infrannuali-confronto", "Dal progressivo alla chiusura", chart, kpis)
    if block is not None:
        items.append(block)
    table_rows = [row for row in (
        _indicator_row(report, identifier, adjusted, closing) for identifier in _INDICATOR_TABLE_IDS
    ) if row is not None]
    items.append(s.table("indicatori-infrannuali-tabella",
        "Indicatori finanziari e strutturali · progressivo e chiusura",
        ["Indicatore", "Rettificato", "Chiusura"], table_rows))
    # Rimando all'Allegato F nel sottotitolo, non in un blocco a parte — vedi
    # la nota nella pagina «rettifiche» sullo stesso trabocco su dati reali.
    return {"id": "indicatori-infrannuali", "title": "Indicatori dell'infrannuale", "family": FAMILY,
            "subtitle": "Il progressivo rettificato e la chiusura attesa sono confrontati sugli stessi "
                        "indicatori, con durate diverse; il dettaglio è nell'Allegato F.",
            "kpis": [] if block is not None else kpis, "items": items}


def _kpi_indicator_at(report: FinalReportModelV2, identifier: str, period: Any, desc: str) -> dict[str, Any] | None:
    if period is None:
        return None
    indicator = s.indicator_by_id(report, identifier)
    if indicator is None:
        return None
    for candidate, value in zip(indicator.periods, indicator.values):
        if candidate.id == period.id and value is not None:
            return s.kpi(desc, value, indicator.unit)
    return None


def _indicator_row(report: FinalReportModelV2, identifier: str, adjusted: Any, closing: Any) -> dict[str, Any] | None:
    indicator = s.indicator_by_id(report, identifier)
    if indicator is None:
        return None
    by_id = {period.id: value for period, value in zip(indicator.periods, indicator.values)}
    adj_value = by_id.get(adjusted.id) if adjusted is not None else None
    close_value = by_id.get(closing.id) if closing is not None else None
    if adj_value is None and close_value is None:
        return None
    return s.row(f"indicatori-infrannuali-tabella:{identifier}", [indicator.label, adj_value, close_value],
                [None, indicator.unit, indicator.unit])


def _confronto_chart(report: FinalReportModelV2, adjusted: Any, closing: Any) -> dict[str, Any] | None:
    categories: list[str] = []
    adj_values: list[Any] = []
    close_values: list[Any] = []
    unit = "percent"
    for identifier in _DUMBBELL_IDS:
        indicator = s.indicator_by_id(report, identifier)
        if indicator is None:
            continue
        by_id = {period.id: value for period, value in zip(indicator.periods, indicator.values)}
        adj_value = by_id.get(adjusted.id) if adjusted is not None else None
        close_value = by_id.get(closing.id) if closing is not None else None
        if adj_value is None and close_value is None:
            continue
        categories.append(indicator.label)
        adj_values.append(adj_value)
        close_values.append(close_value)
        unit = indicator.unit
    if not categories:
        return None
    return _bar_chart("indicatori-infrannuali-confronto", "Dal progressivo alla chiusura", unit, categories,
                      [("Rettificato", adj_values), ("Chiusura", close_values)])


def build(report: FinalReportModelV2) -> list[dict[str, Any]]:
    if report.practice.workflow_type != "infrannuale":
        return []
    pages = [_fonti(report), _rettifiche(report), _chiusura(report), _indicatori_infrannuali(report)]
    return [page for page in pages if page is not None]
