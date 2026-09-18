"""Gruppo ALLEGATI (v4 pagine 19-33): indice dei prospetti, A/B/C (prospetti
completi), D/E/F/G (registro rettifiche, matrice ipotesi, indicatori),
metodologia.

Indice e A/B/C sono stati implementati dalla fondazione M2-02D; questo giro
(fase 2) aggiunge D/E/F/G e la metodologia, e corregge due difetti già
osservati sulle pagine A/B/C (misurati su AMBIENTA, azienda 575 scenario 18):
intestazioni di colonna troppo lunghe (`period_label` andava a capo su più
righe: "2026 chiusura stimata (12 mesi)") e il titolo di pagina ripetuto
quasi identico nell'intestazione della tabella subito sotto. Vedi
`period_label_short`/`period_basis_legend` in `shared.py` per il primo, e la
`table_title` distinta dal `page_title` qui sotto per il secondo.
"""
from __future__ import annotations

from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

from . import shared as s

GROUP = "allegati"
FAMILY = "Allegati"

# Righe per pagina di un allegato lungo: tarato sulla geometria reale del
# dossier (pagina A4, colonna etichetta + fino a 5 colonne di valore, testata
# ripetuta, nessuna colonna KPI) e validato compilando con Typst — vedi
# `docs/testing/M2-02D-catalogo.md`. Non è il numero della v4 dimostrativa
# (che usava un catalogo sintetico diverso), solo una dimensione simile.
APPENDIX_ROWS_PER_PART = 24

# Allegato G (26 indicatori analitici) su 2 pagine v4 (31-32): una divisione
# più stretta dell'appendice A/B/C perché qui non c'è margine per KPI o
# grafico, solo una tabella indicatore x periodo.
ANALYTICAL_ROWS_PER_PART = 13

_LETTERS = {"income_statement": "A", "balance_sheet": "B", "cashflow": "C"}
_STATEMENT_ORDER = ("income_statement", "balance_sheet", "cashflow")


def _allegato_pages(report: FinalReportModelV2, statement_id: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    statement = s.statement_by_id(report, statement_id)
    periods = s.select_periods(statement.periods)
    letter = _LETTERS[statement_id]
    rows = s.appendix_table_rows(statement, periods)
    parts = s.chunk(rows, APPENDIX_ROWS_PER_PART)
    total = len(parts)
    columns = ["Voce", *[s.period_label_short(period) for period in periods]]
    legend = s.period_basis_legend(periods)
    # Titolo neutro di pagina: `statement.title` è già "... completo" (il
    # nome vero del modello) — non gli si appende una seconda volta
    # "prospetto completo": quella frase resta solo nel titolo della
    # tabella qui sotto, che non ripete più il nome dello statement.
    heading = f"{letter} · {statement.title}"
    pages: list[dict[str, Any]] = []
    index_entries: list[dict[str, str]] = []
    for index, part_rows in enumerate(parts, start=1):
        page_id = f"allegato-{letter}-{index}"
        part_suffix = f" · parte {index} di {total}" if total > 1 else ""
        table_title = f"Prospetto completo{part_suffix}"
        table = s.table(page_id, table_title, columns, part_rows)
        subtitle = f"Allegato {letter}{part_suffix} · valori in euro · {legend}."
        pages.append({"id": page_id, "title": heading, "family": FAMILY,
                      "subtitle": subtitle, "kpis": [], "items": [table]})
        index_entries.append({"label": f"{heading}{part_suffix}", "target": f"heading:{page_id}"})
    return pages, index_entries


def _index_page(entries: list[dict[str, str]]) -> dict[str, Any]:
    return {"id": "allegati", "title": "Allegati · indice dei prospetti", "family": FAMILY,
            "subtitle": "Questa sezione raccoglie il dettaglio contabile e finanziario.",
            "kpis": [], "items": [s.index_block("appendix-index", "Indice degli allegati", entries)]}


# ── Allegato D · Registro delle rettifiche (v4 pagina 28) ───────────────────
# Vincolo del proprietario (2026-09-17): UNA tabella, Voce · Rettifica (delta)
# · Motivazione, una riga per rettifica confermata — niente contropartite,
# niente saldi prima/dopo per voce (quelli stanno a pagina 4, `dati.py`),
# niente periodi di confronto. `report.adjustments.confirmed` è un flag
# sull'intero giornale, non per riga: la pagina esiste solo quando è vero e
# ci sono righe, altrimenti si omette (mai una pagina vuota).

def _allegato_d(report: FinalReportModelV2) -> tuple[dict[str, Any], dict[str, str]] | None:
    adjustments = report.adjustments
    if not adjustments.confirmed or not adjustments.entries:
        return None
    columns = ["Voce", "Rettifica (delta)", "Motivazione"]
    rows = [s.row(f"row:rettifica:{entry.id}", [entry.edited_label, entry.edit_delta, entry.explanation],
                  [None, "eur", None])
            for entry in adjustments.entries]
    table = s.table("allegato-D", "Rettifiche confermate", columns, rows)
    title = "D · Registro delle rettifiche"
    page = {"id": "allegato-D", "title": title, "family": FAMILY,
            "subtitle": "Una riga per ogni rettifica confermata del bilancio infrannuale · valori in euro.",
            "kpis": [], "items": [table]}
    return page, {"label": title, "target": "heading:allegato-D"}


# ── Allegato E · Matrice delle ipotesi (v4 pagina 29) ────────────────────────
# La v4 dimostrativa mescola ipotesi vere (percentuali, giorni) e risultati
# del CE (servizi, personale, ammortamenti come importi assoluti) nella
# stessa tabella; nel modello reale i secondi sono output del prospetto, non
# ipotesi (mappatura pagina 29: "derivabile", mai un'ipotesi propria). Questa
# pagina resta sulle sole ipotesi vere lette da `assumption_sections` — un
# driver è incluso solo se il modello dà almeno un valore su un anno di
# piano, mai un "n.d." su tutta la riga. La sezione "Debito e calendario dei
# rimborsi" della v4 (nuovi finanziamenti/rimborsi per contratto) NON esiste
# nel modello v2 esposto al report (`details['debito_bancario']` del motore
# non è serializzato fuori da `ForecastEngine`, mappatura pagina 29) e si
# omette dichiarandolo qui, non fabbricando una scomposizione dal totale.
_DRIVER_ROWS: tuple[tuple[str, str, str], ...] = (
    ("fatturato", "revenue_growth_pct", "percent"),
    ("fatturato", "other_revenue_growth_pct", "percent"),
    ("costi", "variable_materials_growth_pct", "percent"),
    ("costi", "variable_services_growth_pct", "percent"),
    ("costi", "personnel_growth_pct", "percent"),
    ("costi", "rent_growth_pct", "percent"),
    ("circolante", "dso_days", "days"),
    ("circolante", "dio_days", "days"),
    ("circolante", "dpo_days", "days"),
    ("patrimoniale-piano", "tangible_investments", "eur"),
    ("patrimoniale-piano", "depreciation_rate", "percent"),
    ("imposte", "tax_rate", "percent"),
)


def _assumption(report: FinalReportModelV2, section_key: str, field: str) -> Any:
    section = next((candidate for candidate in report.assumption_sections if candidate.key == section_key), None)
    if section is None:
        return None
    return next((assumption for assumption in section.assumptions if assumption.field == field), None)


def _driver_row(assumption: Any, unit: str, n: int) -> dict[str, Any]:
    values = assumption.values[:n]
    if unit == "eur":
        cells = [assumption.label, *values]
        units = [None, *(["eur"] * len(values))]
    else:
        cells = [assumption.label, *[s.format_unit(value, unit) for value in values]]
        units = [None] * (1 + len(values))
    return s.row(f"row:ipotesi:{assumption.field}", cells, units)


def _allegato_e(report: FinalReportModelV2) -> tuple[dict[str, Any], dict[str, str]] | None:
    years = report.practice.periods.forecast_years
    if not years:
        return None
    candidates = []
    for section_key, field, unit in _DRIVER_ROWS:
        assumption = _assumption(report, section_key, field)
        if assumption is None or all(value is None for value in assumption.values):
            continue
        candidates.append((assumption, unit))
    if not candidates:
        return None
    # Le colonne seguono gli anni di piano, ma non oltre quanti valori le
    # ipotesi dichiarano — nel report reale coincidono sempre (le stesse
    # righe `BudgetAssumptions` alimentano sia `practice.periods` sia
    # `assumption_sections`); un disallineamento si tronca al comune, mai si
    # inventa una colonna vuota per farli tornare.
    n = min([len(years), 5, *(len(assumption.values) for assumption, _ in candidates)])
    years = years[:n]
    rows = [_driver_row(assumption, unit, n) for assumption, unit in candidates]
    columns = ["Driver", *[str(year) for year in years]]
    table = s.table("allegato-E", "Driver dichiarati del piano", columns, rows)
    title = "E · Matrice delle ipotesi"
    page = {"id": "allegato-E", "title": title, "family": FAMILY,
            "subtitle": "Le ipotesi dichiarate per gli anni di piano · valori in euro dove non indicata "
                        "un'altra unità.",
            "kpis": [], "items": [table]}
    return page, {"label": title, "target": "heading:allegato-E"}


# ── Allegato F · Indicatori della pratica (v4 pagina 30) ────────────────────
# I quindici indicatori `practice.*` (stessi della stampa infrannuale, mai
# ricalcolati), estesi ai periodi del piano. A differenza di G, qui entra
# anche il progressivo rettificato quando c'è (`select_periods_with_adjusted`)
# — è quello che questa pagina racconta, la stessa ragione per cui la
# mappatura pagina 30 chiede l'etichetta vera del periodo ("6M 2026
# rettificato" su AMBIENTA), mai un "9M" fisso.
_PRACTICE_INDICATOR_KEYS: tuple[str, ...] = (
    "dscr", "ebitda_margin", "mt", "ccn", "current_ratio", "ms", "copertura_immob",
    "indipendenza", "pfn", "pfn_ebitda", "roi", "roe", "ros", "of_mol", "of_revenue",
)

# I ventisei indicatori `analytical.*` (v4 pagine 31-32, Allegato G), nello
# stesso ordine del catalogo (`contracts/final_report_dossier_catalog.json`).
_ANALYTICAL_INDICATOR_KEYS: tuple[str, ...] = (
    "liquidity.current_ratio", "liquidity.quick_ratio", "liquidity.acid_test",
    "solvency.autonomy_index", "solvency.leverage_ratio", "solvency.debt_to_equity",
    "solvency.debt_to_production",
    "profitability.roe", "profitability.roi", "profitability.ros", "profitability.rod",
    "profitability.ebitda_margin",
    "coverage.fixed_assets_coverage_with_equity_and_ltdebt", "coverage.fixed_assets_coverage_with_equity",
    "coverage.independence_from_third_parties",
    "activity.inventory_turnover_days", "activity.receivables_turnover_days",
    "activity.payables_turnover_days", "activity.cash_conversion_cycle", "activity.asset_turnover",
    "extended_profitability.spread", "extended_profitability.financial_leverage_effect",
    "extended_profitability.ebitda_on_sales", "extended_profitability.financial_charges_on_revenue",
    "efficiency.revenue_per_employee_cost", "efficiency.revenue_per_materials_cost",
)


def _indicators_by_keys(report: FinalReportModelV2, prefix: str, keys: tuple[str, ...]) -> list[Any]:
    found = (s.indicator_by_id(report, f"{prefix}.{key}") for key in keys)
    return [indicator for indicator in found if indicator is not None]


def _indicator_row(indicator: Any, periods: list[Any]) -> dict[str, Any]:
    values = s.indicator_object_values_for_periods(indicator, periods)
    if indicator.unit == "eur":
        cells = [indicator.label, *values]
        units = [None, *(["eur"] * len(values))]
    else:
        cells = [indicator.label, *[s.format_unit(value, indicator.unit) for value in values]]
        units = [None] * (1 + len(values))
    return s.row(f"row:{indicator.id}", cells, units)


def _allegato_f(report: FinalReportModelV2) -> tuple[dict[str, Any], dict[str, str]] | None:
    indicators = _indicators_by_keys(report, "practice", _PRACTICE_INDICATOR_KEYS)
    if not indicators:
        return None
    periods = s.select_periods_with_adjusted(indicators[0].periods)
    columns = ["Indicatore", *[s.period_label_short(period) for period in periods]]
    legend = s.period_basis_legend(periods)
    rows = [_indicator_row(indicator, periods) for indicator in indicators]
    table = s.table("allegato-F", "Indicatori × periodo", columns, rows)
    title = "F · Indicatori della pratica"
    page = {"id": "allegato-F", "title": title, "family": FAMILY,
            "subtitle": f"Allegato F · valori in euro dove non indicata un'altra unità · {legend}.",
            "kpis": [], "items": [table]}
    return page, {"label": title, "target": "heading:allegato-F"}


# ── Allegato G · Indici analitici (v4 pagine 31-32) ──────────────────────────
# Solo chiusura/storico + piano (`select_periods`, come A-C), mai il
# progressivo rettificato: qui la pagina racconta il quadro degli indici di
# bilancio, non l'infrannuale in sé. Acid Test e leva finanziaria sono
# valorizzati per davvero nel modello reale (mappatura pagina 31-32
# conferma: la v4 dimostrativa li mostra "n.d." solo perché lo script demo
# non li calcolava) — qui vengono dalla stessa `indicator_catalog` di ogni
# altro indice, nessun trattamento speciale. Altman, FGPMI, EM-Score e le
# loro componenti sono presenti nel modello ma solo nel bagaglio legacy
# `forecast.years[*].calculations` (chiavi puntate, fuori dal catalogo
# canonico `indicator_catalog`) — omessi qui di proposito, non per assenza
# di dato: un'inclusione futura leggerebbe quel percorso diverso, non questo.

def _allegato_g(report: FinalReportModelV2) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    indicators = _indicators_by_keys(report, "analytical", _ANALYTICAL_INDICATOR_KEYS)
    if not indicators:
        return [], []
    periods = s.select_periods(indicators[0].periods)
    columns = ["Indicatore", *[s.period_label_short(period) for period in periods]]
    legend = s.period_basis_legend(periods)
    rows = [_indicator_row(indicator, periods) for indicator in indicators]
    parts = s.chunk(rows, ANALYTICAL_ROWS_PER_PART)
    total = len(parts)
    heading = "G · Indici analitici"
    pages: list[dict[str, Any]] = []
    entries: list[dict[str, str]] = []
    for index, part_rows in enumerate(parts, start=1):
        page_id = f"allegato-G-{index}"
        part_suffix = f" · parte {index} di {total}" if total > 1 else ""
        table_title = f"Quadro completo{part_suffix}"
        table = s.table(page_id, table_title, columns, part_rows)
        subtitle = f"Allegato G{part_suffix} · valori in euro dove non indicata un'altra unità · {legend}."
        pages.append({"id": page_id, "title": heading, "family": FAMILY,
                      "subtitle": subtitle, "kpis": [], "items": [table]})
        entries.append({"label": f"{heading}{part_suffix}", "target": f"heading:{page_id}"})
    return pages, entries


# ── Metodologia e note (v4 pagina 33) ────────────────────────────────────────
# Testo editoriale statico (non deriva da `report`, a parte l'esistenza
# stessa del dossier): spiega i periodi e da dove vengono le strutture. La
# tabella "Fonti delle strutture" della v4 elencava moduli frontend del solo
# script dimostrativo (`build-dossier-preview.py`); qui elenca le fonti vere
# nel backend che compone questo stesso report (mappatura pagina 33).

_FONTI_ROWS: tuple[tuple[str, str], ...] = (
    ("Conto economico, stato patrimoniale e rendiconto completi",
     "contracts/final_report_dossier_catalog.json"),
    ("Indicatori della pratica e indici analitici", "calculations/report_indicators.py"),
    ("Composizioni, break-even e allineamento dei prospetti", "backend/app/services/final_report_dossier.py"),
    ("Ipotesi, rettifiche e piano", "backend/app/schemas/final_report.py · final_report_v2.py"),
)


def _fonti_table() -> dict[str, Any]:
    rows = [s.row(f"row:fonte:{index}", [struttura, fonte], [None, None])
            for index, (struttura, fonte) in enumerate(_FONTI_ROWS)]
    return s.table("fonti-strutture", "Fonti nel progetto", ["Struttura", "Fonte nel progetto"], rows)


def _metodologia(report: FinalReportModelV2) -> dict[str, Any]:
    intro = ("Osservato, progressivo rettificato, chiusura stimata e anni di piano restano distinti per "
             "tutto il dossier, in ogni tabella e ogni legenda. La stampa comprende ogni allegato, anche "
             "quando richiede più pagine.")
    limiti = ("Acid Test e leva finanziaria sono indicatori calcolati e valorizzati nell'Allegato G: non "
              "sono un limite del modello. Lo Z-Score di Altman, il rating FGPMI e l'EM-Score sono "
              "disponibili per ogni anno di piano, ma solo fuori dal catalogo canonico degli indicatori "
              "(nel bagaglio previsionale per anno) — non compaiono in questo allegato per questo motivo "
              "di percorso, non per assenza di dato.")
    items: list[dict[str, Any]] = [
        s.text("metodologia-intro", "Metodologia e lettura", intro),
        _fonti_table(),
        s.note("metodologia-limiti", limiti),
    ]
    return {"id": "metodologia", "title": "Metodologia e note", "family": FAMILY,
            "subtitle": "Come leggere i periodi del dossier, e da dove vengono le sue strutture.",
            "kpis": [], "items": items}


def build(report: FinalReportModelV2) -> list[dict[str, Any]]:
    pages_by_statement: dict[str, list[dict[str, Any]]] = {}
    entries_by_statement: dict[str, list[dict[str, str]]] = {}
    for statement_id in _STATEMENT_ORDER:
        pages, entries = _allegato_pages(report, statement_id)
        pages_by_statement[statement_id] = pages
        entries_by_statement[statement_id] = entries

    extra_pages: list[dict[str, Any]] = []
    extra_entries: list[dict[str, str]] = []
    for single in (_allegato_d(report), _allegato_e(report), _allegato_f(report)):
        if single is not None:
            page, entry = single
            extra_pages.append(page)
            extra_entries.append(entry)
    g_pages, g_entries = _allegato_g(report)
    extra_pages.extend(g_pages)
    extra_entries.extend(g_entries)

    all_entries = [entry for statement_id in _STATEMENT_ORDER for entry in entries_by_statement[statement_id]]
    all_entries.extend(extra_entries)

    ordered: list[dict[str, Any]] = [_index_page(all_entries)]
    for statement_id in _STATEMENT_ORDER:
        ordered.extend(pages_by_statement[statement_id])
    ordered.extend(extra_pages)
    ordered.append(_metodologia(report))
    return ordered
