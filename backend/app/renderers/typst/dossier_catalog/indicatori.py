"""Gruppo INDICATORI (v4 pagine 11-18): indicatori del piano, liquidità e
margini strutturali, redditività e costo del debito, solidità e copertura del
debito, circolante e ciclo monetario, composizione economica e patrimoniale,
break-even e margine di sicurezza, diagnostica e punti da verificare.

Una pagina fisica per voce di catalogo (vedi `docs/testing/M2-02D-catalogo.md`).
Ogni voce di questo gruppo resta a **un solo grafico** (mai due, anche quando
la v4 ne affianca due con `panel_grid`): un secondo `chart-block` reale (grafico
+ tabella valori) supera da solo il budget verticale di una pagina fisica
(misurato: ~130mm a blocco contro ~205mm disponibili sotto l'intestazione), e
`pagine/comuni.typ` (`render-item`, dispatcher unico di TUTTO il catalogo) è
fuori dal perimetro di questo gruppo — le regole della fase vietano di
aggiungergli un nuovo `kind` "panel" solo per queste pagine. Dove le due serie
condividono l'unità si uniscono in un grafico solo (ROI/ROE/OF; DSO/DIO/DPO/
ciclo monetario — il tetto di 4 serie del layout lo permette esattamente);
dove le unità sono incompatibili (eur vs ratio, eur vs percent) si tiene il
grafico più legato ai KPI di testa e il resto resta comunque leggibile in
tabella o come KPI. Ogni omissione è dichiarata nel commento della funzione di
pagina, mai silenziosa.

Stesso vincolo per il "dumbbell" (confronto fra due soli periodi, v4 pagine 6/
11/16): nessun componente dumbbell esiste ancora fuori da questo file, e non
serve costruirne uno — il grafico a linea già esistente (`charts.typ`, kind
diverso da "bar"), applicato a soli DUE periodi (`_first_last_periods`),
produce esattamente lo stesso disegno (due punti, una linea, valore iniziale e
finale), sugli stessi dati, senza toccare `pagine/comuni.typ`.

Nota per chi tocca «composizione» e «break-even»: i dati sono già nel modello
v2 (`report.structure_series`, quattro `ReportSeriesGroup` fissi —
`composition_uses`, `composition_sources`, `cost_incidence`, `break_even`,
aggiunti da M2-02C), con serie canoniche in ordine fisso
(`STRUCTURE_GROUP_SERIES` in `app.schemas.final_report_v2`). Nessun calcolo:
solo lettura e formattazione — tranne il «circolante operativo» di pagina 15
(`_kpi_circolante_operativo`), una somma di righe di prospetto già canoniche
(rimanenze + crediti commerciali − fornitori), non un indicatore del
catalogo: la mappatura della fase la definisce esplicitamente "derivabile" e
ne descrive la stessa somma.
"""
from __future__ import annotations

from typing import Any

from app.schemas.final_report_v2 import FinalReportModelV2

from . import shared as s

GROUP = "indicatori"
# v4: le pagine 7-18 condividono la stessa fascia "PIANO E RISULTATI"
# nell'occhiello di pagina (verificato con `pdftotext -f 11 -l 18 -layout` sul
# PDF di riferimento) — stessa stringa di `piano.py`, non una svista.
FAMILY = "Piano e risultati"


# ── Helpers locali: fonti multiple sulla stessa pagina ──────────────────────
# `shared.py` copre un'unica fonte per grafico/tabella (indicator_catalog O
# statement O structure_series); alcune pagine di questo gruppo compongono più
# fonti sullo stesso asse di periodi (es. pagina 11: debito da
# `structure_series`, cassa da uno statement, PFN da un indicatore) — questi
# helper restano qui perché nessun'altra pagina del catalogo ne ha bisogno.


def _periods(report: FinalReportModelV2) -> list[Any]:
    statement = s.statement_by_id(report, "balance_sheet")
    return s.select_periods(statement.periods)


def _structure_group(report: FinalReportModelV2, group_id: str) -> Any:
    for group in report.structure_series:
        if group.id == group_id:
            return group
    raise ValueError(f"no structure series group {group_id!r}")


def _structure_series(group: Any, series_id: str) -> Any:
    for series in group.series:
        if series.id == series_id:
            return series
    raise ValueError(f"no series {series_id!r} on structure group {group.id!r}")


def _values_by_period(values: list[Any], value_periods: list[Any], periods: list[Any]) -> list[Any]:
    by_id = {period.id: value for period, value in zip(value_periods, values)}
    return [by_id.get(period.id) for period in periods]


def _indicator_values(report: FinalReportModelV2, identifier: str, periods: list[Any]) -> list[Any] | None:
    indicator = s.indicator_by_id(report, identifier)
    if indicator is None:
        return None
    return _values_by_period(indicator.values, indicator.periods, periods)


def _structure_values(report: FinalReportModelV2, group_id: str, series_id: str, periods: list[Any]) -> list[Any]:
    group = _structure_group(report, group_id)
    series = _structure_series(group, series_id)
    return _values_by_period(series.values, group.periods, periods)


def _statement_values(report: FinalReportModelV2, statement_id: str, code: str, periods: list[Any]) -> list[Any]:
    statement = s.statement_by_id(report, statement_id)
    row_obj = s.statement_row(statement, code)
    return s.values_for_periods(row_obj, statement, periods)


def _chart(chart_id: str, title: str, unit: str, periods: list[Any],
          entries: list[tuple[str, list[Any] | None]]) -> dict[str, Any] | None:
    """Grafico composto da fonti eterogenee — vedi il commento del modulo."""
    axis = [str(period.year) for period in periods]
    series: list[dict[str, Any]] = []
    for display_label, values in entries:
        if values is None or not any(value is not None for value in values):
            continue
        series.append({"label": display_label, "values": [s.exact(value) for value in values]})
    if not series:
        return None
    return {"id": chart_id, "title": title, "unit": unit, "categories": axis,
            "series": series, "indicator_ids": [], "thresholds": []}


def _kpi_delta(report: FinalReportModelV2, identifier: str, desc: str, unit: str,
               periods: list[Any]) -> dict[str, Any] | None:
    values = _indicator_values(report, identifier, periods)
    if values is None:
        return None
    available = [(period, value) for period, value in zip(periods, values) if value is not None]
    if len(available) < 2:
        return None
    (first_period, first), (last_period, last) = available[0], available[-1]
    return s.kpi(f"{desc} · {first_period.year}-{last_period.year}", last - first, unit)


def _indicator_table(table_id: str, title: str, report: FinalReportModelV2, periods: list[Any],
                     rows_spec: list[tuple[str, str | None]]) -> dict[str, Any] | None:
    """Una riga per indicatore del catalogo; un identificatore assente si
    omette (mai «n.d.»). `display_label=None` tiene l'etichetta del catalogo
    così com'è — necessario per `practice.dscr`, che porta il suffisso
    "— proxy della pratica" (v. `build_indicator_catalog`), non riscrivibile a
    mano senza perdere quell'avvertenza."""
    columns = ["Indicatore", *[s.period_label(period) for period in periods]]
    rows = []
    for identifier, display_label in rows_spec:
        indicator = s.indicator_by_id(report, identifier)
        if indicator is None:
            continue
        values = _values_by_period(indicator.values, indicator.periods, periods)
        if not any(value is not None for value in values):
            continue
        label = indicator.label if display_label is None else display_label
        rows.append(s.row(f"{table_id}:{identifier}", [label, *values], [None, *([indicator.unit] * len(values))]))
    if not rows:
        return None
    return s.table(table_id, title, columns, rows)


# ── Pagina 11 · Indicatori e rischi ──────────────────────────────────────────


def _indicatori(report: FinalReportModelV2) -> dict[str, Any]:
    periods = _periods(report)
    kpis = [kpi for kpi in (
        s.kpi_indicator(report, "practice.pfn", "PFN", mode="first_last"),
        s.kpi_indicator(report, "practice.pfn_ebitda", "PFN / EBITDA", mode="first_last"),
        s.kpi_indicator(report, "practice.ccn", "circolante operativo (CCN)"),
        _kpi_delta(report, "practice.ccn", "assorbimento circolante", "eur", periods),
    ) if kpi is not None]
    chart = _chart("indicatori-debito-cassa-pfn", "Debito, cassa e PFN", "eur", periods, [
        ("Debiti finanziari", _structure_values(report, "composition_sources", "financial_debt", periods)),
        ("Cassa", _statement_values(report, "balance_sheet", "sp09_disponibilita_liquide", periods)),
        ("PFN", _indicator_values(report, "practice.pfn", periods)),
    ])
    items: list[dict[str, Any]] = []
    block = s.chart_block("indicatori-debito-cassa-pfn", "Debito, cassa e PFN", chart, kpis, kind="line")
    if block is not None:
        items.append(block)
    table = _indicator_table("indicatori-tabella", "Indicatori del piano", report, periods, [
        ("practice.pfn", "PFN"),
        ("practice.pfn_ebitda", "PFN / EBITDA"),
        ("practice.ebitda_margin", "EBITDA margin"),
        ("practice.ccn", "Circolante operativo (CCN)"),
    ])
    if table is not None:
        items.append(table)
    return {"form": "rail+main", "id": "indicatori", "title": "Indicatori e rischi", "family": FAMILY,
            "subtitle": "PFN = debiti finanziari meno disponibilità liquide. Gli indicatori descrivono la "
                        "pratica, non costituiscono un rating.",
            "kpis": [] if block is not None else kpis, "items": items}


# ── Pagina 12 · Liquidità e margini strutturali ─────────────────────────────


def _liquidita(report: FinalReportModelV2) -> dict[str, Any]:
    periods = _periods(report)
    kpis = [kpi for kpi in (
        s.kpi_indicator(report, "practice.current_ratio", "liquidità corrente"),
        s.kpi_indicator(report, "practice.mt", "margine di tesoreria"),
        s.kpi_indicator(report, "practice.ms", "margine di struttura"),
    ) if kpi is not None]
    # Id di grafico riusato apposta: è lo stesso "structural_balance" già
    # dichiarato fra i grafici a barre di `chart-layout.json` (e nel catalogo
    # legacy `DOSSIER_CHARTS` di `final_report_dossier.py`, stessi tre
    # indicatori) — nessuna voce nuova da aggiungere lì.
    chart = s.indicator_chart(report, "structural_balance", "Margini strutturali", "eur", periods,
        ["practice.ccn", "practice.mt", "practice.ms"])
    items: list[dict[str, Any]] = []
    block = s.chart_block("structural_balance", "Margini strutturali", chart, kpis, kind="bar")
    if block is not None:
        items.append(block)
    # Il secondo grafico della v4 ("Liquidità corrente e immediata", current
    # ratio + quick ratio) non ha una pagina fisica propria in questo gruppo
    # (v. commento di modulo): entrambi gli indicatori restano leggibili in
    # tabella, e la liquidità corrente anche come KPI qui sopra.
    table = _indicator_table("liquidita-tabella", "Quadro dei margini e della liquidità", report, periods, [
        ("practice.ccn", "Capitale circolante netto"),
        ("practice.mt", "Margine di tesoreria"),
        ("practice.ms", "Margine di struttura"),
        ("practice.current_ratio", "Liquidità corrente"),
        ("practice.quick_ratio", "Liquidità immediata"),
    ])
    if table is not None:
        items.append(table)
    return {"form": "rail+main", "id": "liquidita", "title": "Liquidità e margini strutturali", "family": FAMILY,
            "subtitle": "CCN, margine di tesoreria e margine di struttura sono distinti dal circolante operativo.",
            "kpis": [] if block is not None else kpis, "items": items}


# ── Pagina 13 · Redditività e costo del debito ──────────────────────────────


def _redditivita(report: FinalReportModelV2) -> dict[str, Any]:
    periods = _periods(report)
    # La v4 affianca due grafici (ROI/ROE; OF/ricavi e OF/MOL): qui restano
    # uniti in un solo grafico a 4 serie, tutte in percentuale e su scala
    # comparabile (v. commento di modulo) — il tetto di `chart-layout.json`
    # (`max_series: 4`) lo permette esattamente, senza perdere alcuna serie.
    chart = s.indicator_chart(report, "redditivita-quattro-serie", "Redditività e costo del debito", "percent",
        periods, ["practice.roi", "practice.roe", "practice.of_revenue", "practice.of_mol"])
    items: list[dict[str, Any]] = []
    block = s.chart_block("redditivita-quattro-serie", "Redditività e costo del debito", chart, [], kind="line")
    if block is not None:
        items.append(block)
    table = _indicator_table("redditivita-tabella", "Confronto della redditività", report, periods, [
        ("practice.roi", "ROI"),
        ("practice.roe", "ROE"),
        ("practice.ros", "ROS"),
        ("practice.ebitda_margin", "EBITDA margin"),
        ("practice.of_mol", "Oneri finanziari / MOL"),
        ("practice.of_revenue", "Oneri finanziari / ricavi"),
    ])
    if table is not None:
        items.append(table)
    return {"id": "redditivita", "title": "Redditività e costo del debito", "family": FAMILY,
            "subtitle": "Redditività e costo del debito in un unico grafico percentuale; la tabella riporta "
                        "ogni indicatore per esteso.",
            "kpis": [], "items": items}


# ── Pagina 14 · Solidità e copertura del debito ─────────────────────────────


def _solidita(report: FinalReportModelV2) -> dict[str, Any]:
    periods = _periods(report)
    kpis = [kpi for kpi in (
        s.kpi_indicator(report, "practice.indipendenza", "indipendenza finanziaria"),
        s.kpi_indicator(report, "practice.copertura_immob", "copertura immobilizzazioni"),
        s.kpi_indicator(report, "practice.pfn_ebitda", "PFN / EBITDA"),
    ) if kpi is not None]
    # Id riusato dal catalogo legacy `DOSSIER_CHARTS` (stessa coppia di
    # indicatori: indipendenza + copertura immobilizzazioni).
    chart = s.indicator_chart(report, "practice_asset_coverage", "Autonomia e copertura", "percent", periods,
        ["practice.indipendenza", "practice.copertura_immob"])
    items: list[dict[str, Any]] = []
    block = s.chart_block("practice_asset_coverage", "Autonomia e copertura", chart, kpis, kind="line")
    if block is not None:
        items.append(block)
    # Il secondo grafico della v4 (PFN/EBITDA, unità "volte", incompatibile
    # con il percent del primo) resta fuori dal grafico; il valore è comunque
    # KPI qui sopra e riga di tabella qui sotto.
    table = _indicator_table("solidita-tabella", "Autonomia, copertura e servizio del debito", report, periods, [
        ("practice.indipendenza", "Indipendenza finanziaria"),
        ("practice.copertura_immob", "Copertura immobilizzazioni"),
        ("practice.pfn_ebitda", "PFN / EBITDA"),
        ("practice.dscr", None),
    ])
    if table is not None:
        items.append(table)
    return {"form": "rail+main", "id": "solidita", "title": "Solidità e copertura del debito", "family": FAMILY,
            "subtitle": "Il DSCR segue la convenzione della pratica: non è un calcolo completo sul servizio "
                        "del debito.",
            "kpis": [] if block is not None else kpis, "items": items}


# ── Pagina 15 · Circolante e ciclo monetario ────────────────────────────────


def _kpi_circolante_operativo(report: FinalReportModelV2, periods: list[Any]) -> dict[str, Any] | None:
    """Rimanenze + crediti commerciali (breve+lungo) − fornitori, sull'ultimo
    periodo con tutt'e quattro le righe valorizzate. Somma di righe di
    prospetto già canoniche (`sp05_rimanenze`, `sp06a`/`sp07a` crediti
    clienti, la riga aggregata "Fornitori" già presente nel catalogo SP) — non
    un calcolo finanziario nuovo, la stessa somma che la mappatura della fase
    dichiara "derivabile" per questo KPI (nessun indicatore unico lo copre)."""
    statement = s.statement_by_id(report, "balance_sheet")
    codes = ("sp05_rimanenze", "sp06a_crediti_clienti_breve", "sp07a_crediti_clienti_lungo",
             "sp16d_debiti_fornitori_breve+sp17d_debiti_fornitori_lungo")
    values = {code: s.values_for_periods(s.statement_row(statement, code), statement, periods) for code in codes}
    for index in range(len(periods) - 1, -1, -1):
        parts = [values[code][index] for code in codes]
        if any(part is None for part in parts):
            continue
        rimanenze, crediti_breve, crediti_lungo, fornitori = parts
        return s.kpi(f"circolante operativo · {periods[index].year}",
                     rimanenze + crediti_breve + crediti_lungo - fornitori, "eur")
    return None


def _circolante(report: FinalReportModelV2) -> dict[str, Any]:
    periods = _periods(report)
    kpis = [kpi for kpi in (
        s.kpi_indicator(report, "analytical.activity.receivables_turnover_days", "giorni di credito (DSO)"),
        s.kpi_indicator(report, "analytical.activity.inventory_turnover_days", "giorni di magazzino (DIO)"),
        s.kpi_indicator(report, "analytical.activity.payables_turnover_days", "giorni di debito (DPO)"),
        _kpi_circolante_operativo(report, periods),
    ) if kpi is not None]
    # I due grafici della v4 (giorni DSO/DIO/DPO; ciclo di conversione) sono
    # entrambi in giorni: qui restano in un solo grafico a 4 serie (tetto
    # `max_series: 4` rispettato esattamente).
    chart = s.indicator_chart(report, "circolante-giorni", "Giorni del capitale circolante e ciclo monetario",
        "days", periods, ["analytical.activity.receivables_turnover_days",
        "analytical.activity.inventory_turnover_days", "analytical.activity.payables_turnover_days",
        "analytical.activity.cash_conversion_cycle"])
    items: list[dict[str, Any]] = []
    block = s.chart_block("circolante-giorni", "Giorni del capitale circolante e ciclo monetario", chart, kpis, kind="line")
    if block is not None:
        items.append(block)
    table = _indicator_table("circolante-tabella", "Circolante e ciclo monetario", report, periods, [
        ("analytical.activity.receivables_turnover_days", "Giorni di credito · DSO"),
        ("analytical.activity.inventory_turnover_days", "Giorni di magazzino · DIO"),
        ("analytical.activity.payables_turnover_days", "Giorni di debito · DPO"),
        ("analytical.activity.cash_conversion_cycle", "Ciclo di conversione del denaro"),
    ])
    if table is not None:
        items.append(table)
    return {"form": "rail+main", "id": "circolante", "title": "Circolante e ciclo monetario", "family": FAMILY,
            "subtitle": "Giorni su base 365; il ciclo monetario è calcolato prima degli arrotondamenti "
                        "individuali di DSO, DIO e DPO.",
            "kpis": [] if block is not None else kpis, "items": items}


# ── Pagina 16 · Composizione economica e patrimoniale ───────────────────────


def _first_last_periods(periods: list[Any]) -> list[Any]:
    if len(periods) <= 2:
        return periods
    return [periods[0], periods[-1]]


def _structure_table(table_id: str, title: str, report: FinalReportModelV2, group_id: str, periods: list[Any],
                     rows_spec: list[tuple[str, str, str]]) -> dict[str, Any] | None:
    group = _structure_group(report, group_id)
    columns = ["Voce", *[s.period_label(period) for period in periods]]
    rows = []
    for series_id, display_label, unit in rows_spec:
        series = _structure_series(group, series_id)
        values = _values_by_period(series.values, group.periods, periods)
        if not any(value is not None for value in values):
            continue
        rows.append(s.row(f"{table_id}:{series_id}", [display_label, *values], [None, *([unit] * len(values))]))
    if not rows:
        return None
    return s.table(table_id, title, columns, rows)


def _composizione(report: FinalReportModelV2) -> dict[str, Any]:
    periods = _periods(report)
    two_point = _first_last_periods(periods)
    # Sostituisce il dumbbell della v4 (confronto chiusura -> fine piano) con
    # un grafico a linea su due soli periodi — stesso disegno, nessun
    # componente nuovo (v. commento di modulo).
    chart = _chart("composizione-incidenza-costi", "Incidenza dei costi sul fatturato", "percent", two_point, [
        ("Materie prime", _structure_values(report, "cost_incidence", "materials", two_point)),
        ("Servizi", _structure_values(report, "cost_incidence", "services", two_point)),
        ("Personale", _structure_values(report, "cost_incidence", "personnel", two_point)),
        ("Oneri finanziari", _structure_values(report, "cost_incidence", "financial_charges", two_point)),
    ])
    items: list[dict[str, Any]] = []
    # Il contratto nomina questo confronto un `dumbbell` (due periodi, due
    # estremi congiunti). Qui restano le serie per voce di costo disegnate a
    # linea: passare al dumbbell vuol dire trasporre serie e categorie, cioè
    # contenuto della fase 3, non una forma da dichiarare qui. `kind` è
    # comunque esplicito, perché il template non deve più indovinarlo.
    block = s.chart_block("composizione-incidenza-costi",
        "Incidenza dei costi sul fatturato · confronto fra primo e ultimo periodo", chart, [], kind="line")
    if block is not None:
        items.append(block)
    # Le barre al 100% della v4 (composizione impieghi/fonti) diventano UNA
    # tabella di quota percentuale (impieghi + fonti insieme, non due tabelle
    # separate: due titoli+intestazioni in più non ci stanno sulla stessa
    # pagina fisica insieme al grafico — misurato su AMBIENTA, la seconda
    # tabella separata spillava su una pagina fisica senza intestazione).
    # Stessa fonte (`structure_series`), nessuna perdita di dato, senza un
    # componente "barre 100%" che comuni.typ non ha.
    composition_rows = [
        ("composition_uses", "fixed_assets_share", "Immobilizzazioni nette (impieghi)"),
        ("composition_uses", "current_other_share", "Circolante e altro (impieghi)"),
        ("composition_uses", "cash_share", "Disponibilità liquide (impieghi)"),
        ("composition_sources", "equity_share", "Patrimonio netto (fonti)"),
        ("composition_sources", "financial_debt_share", "Debiti finanziari (fonti)"),
        ("composition_sources", "other_liabilities_share", "Altre passività (fonti)"),
    ]
    columns = ["Voce", *[s.period_label(period) for period in periods]]
    rows = []
    for group_id, series_id, display_label in composition_rows:
        values = _structure_values(report, group_id, series_id, periods)
        if not any(value is not None for value in values):
            continue
        rows.append(s.row(f"composizione-quote:{group_id}:{series_id}", [display_label, *values],
                          [None, *(["percent"] * len(values))]))
    if rows:
        items.append(s.table("composizione-quote", "Composizione di impieghi e fonti · quote %", columns, rows))
    return {"id": "composizione", "title": "Composizione economica e patrimoniale", "family": FAMILY,
            "subtitle": "Quote percentuali sullo stesso totale; il dettaglio in euro è negli Allegati.",
            "kpis": [], "items": items}


# ── Pagina 17 · Break-even e margine di sicurezza ───────────────────────────


def _structure_table(table_id: str, title: str, report: FinalReportModelV2, group_id: str, periods: list[Any],
                     rows_spec: list[tuple[str, str, str]]) -> dict[str, Any] | None:
    group = _structure_group(report, group_id)
    columns = ["Voce", *[s.period_label(period) for period in periods]]
    rows = []
    for series_id, display_label, unit in rows_spec:
        series = _structure_series(group, series_id)
        values = _values_by_period(series.values, group.periods, periods)
        if not any(value is not None for value in values):
            continue
        rows.append(s.row(f"{table_id}:{series_id}", [display_label, *values], [None, *([unit] * len(values))]))
    if not rows:
        return None
    return s.table(table_id, title, columns, rows)


def _structure_kpi(report: FinalReportModelV2, group_id: str, series_id: str, desc: str, unit: str,
                   periods: list[Any]) -> dict[str, Any] | None:
    values = _structure_values(report, group_id, series_id, periods)
    pairs = [(period, value) for period, value in zip(periods, values) if value is not None]
    if not pairs:
        return None
    period, value = pairs[-1]
    return s.kpi(f"{desc} · {period.year}", value, unit)


def _break_even(report: FinalReportModelV2) -> dict[str, Any]:
    periods = _periods(report)
    kpis = [kpi for kpi in (
        _structure_kpi(report, "break_even", "break_even_revenue", "ricavi di pareggio", "eur", periods),
        _structure_kpi(report, "break_even", "safety_margin_pct", "margine di sicurezza", "percent", periods),
    ) if kpi is not None]
    chart = _chart("break-even-ricavi-pareggio", "Ricavi e break-even", "eur", periods, [
        ("Ricavi", _statement_values(report, "income_statement", "ce01_ricavi_vendite", periods)),
        ("Pareggio", _structure_values(report, "break_even", "break_even_revenue", periods)),
    ])
    items: list[dict[str, Any]] = []
    block = s.chart_block("break-even-ricavi-pareggio", "Ricavi e break-even", chart, kpis, kind="bar")
    if block is not None:
        items.append(block)
    # Il secondo grafico della v4 (solo margine di sicurezza, %) resta fuori
    # dal grafico principale (unità incompatibile con l'eur di ricavi/
    # pareggio): il valore è comunque KPI e riga di tabella. Il margine può
    # essere negativo (ricavi sotto il pareggio): righe e barre lo mostrano
    # senza clamp, nessuna formula nel template.
    table = _structure_table("break-even-tabella", "Costi fissi, variabili e ricavi di pareggio", report, "break_even",
        periods, [
            ("fixed_costs", "Costi fissi", "eur"),
            ("variable_costs", "Costi variabili", "eur"),
            ("contribution_margin", "Margine di contribuzione", "eur"),
            ("break_even_revenue", "Ricavi di pareggio", "eur"),
            ("safety_margin_pct", "Margine di sicurezza", "percent"),
        ])
    if table is not None:
        items.append(table)
    return {"form": "rail+main", "id": "break-even", "title": "Break-even e margine di sicurezza", "family": FAMILY,
            "subtitle": "Il margine di sicurezza può risultare negativo quando i ricavi restano sotto il "
                        "pareggio operativo.",
            "kpis": [] if block is not None else kpis, "items": items}


# ── Pagina 18 · Diagnostica e punti da verificare ───────────────────────────
# Le "4 spunte verdi" del campione dimostrativo non sono tutte verificabili
# sul modello reale (v. mappatura della fase, pagina 18): "9M rettificati +
# Q4 = chiusura" non ha un controllo indipendente (nessuna stima Q4 separata
# dalla chiusura promossa) e si omette, invece di riprodurre un controllo che
# non esiste. Le altre tre si leggono dal modello, mai da un testo fisso.

_READINESS_LABELS = {"ready": "pronto", "draft": "bozza", "blocked": "bloccato"}


def _esito_rettifiche(report: FinalReportModelV2) -> str:
    codes = {"adjustments_reconciliation_unavailable", "adjustments_unconfirmed"}
    hits = [diagnostic.message for diagnostic in report.diagnostics if diagnostic.code in codes]
    if hits:
        return "; ".join(hits)
    if report.adjustments.confirmed:
        return "Verificato: le rettifiche confermate sono riconciliate con il progressivo."
    return "Le rettifiche non risultano confermate."


def _esito_quadratura_sp(report: FinalReportModelV2, periods: list[Any]) -> str:
    statement = s.statement_by_id(report, "balance_sheet")
    code = ("total_assets+sp11_capitale+sp12_riserve+sp13_utile_perdita+sp16_debiti_breve"
            "+sp17_debiti_lungo+sp14_fondi_rischi+sp15_tfr+sp18_ratei_risconti_passivi")
    values = s.values_for_periods(s.statement_row(statement, code), statement, periods)
    checked = [(period, value) for period, value in zip(periods, values) if value is not None]
    if not checked:
        return "n.d.: nessun periodo verificabile"
    scarti = [(period, value) for period, value in checked if value != 0]
    if not scarti:
        return f"Quadra su {len(checked)} periodi rappresentati."
    dettaglio = "; ".join(f"{period.year}: {s.exact(value)}" for period, value in scarti)
    return f"Scostamento residuo su {len(scarti)} periodi — {dettaglio}"


def _esito_cassa(report: FinalReportModelV2, periods: list[Any]) -> str:
    statement = s.statement_by_id(report, "cashflow")
    beginning = s.values_for_periods(s.statement_row(statement, "cash_reconciliation.cash_beginning"),
        statement, periods)
    flow = s.values_for_periods(s.statement_row(statement, "cash_reconciliation.total_cashflow"),
        statement, periods)
    ending = s.values_for_periods(s.statement_row(statement, "cash_reconciliation.cash_ending"),
        statement, periods)
    checked = 0
    scarti = []
    for period, begin, flow_value, end in zip(periods, beginning, flow, ending):
        if begin is None or flow_value is None or end is None:
            continue
        checked += 1
        if begin + flow_value != end:
            scarti.append((period, end - (begin + flow_value)))
    if checked == 0:
        return "n.d.: nessun periodo verificabile"
    if not scarti:
        return f"Verificato su {checked} periodi: cassa iniziale + flusso totale = cassa finale."
    dettaglio = "; ".join(f"{period.year}: {s.exact(delta)}" for period, delta in scarti)
    return f"Scostamento residuo su {len(scarti)} periodi — {dettaglio}"


def _diagnostica(report: FinalReportModelV2) -> dict[str, Any]:
    periods = _periods(report)
    kpis = [kpi for kpi in (
        s.kpi("stato di preparazione", s.label(_READINESS_LABELS, report.readiness.status)),
        s.kpi("segnalazioni diagnostiche", len(report.diagnostics)),
    ) if kpi is not None]
    items: list[dict[str, Any]] = [s.text("diagnostica-priorita", "Priorità di verifica",
        "Prima di presentare il piano, verificare: la chiusura dell'esercizio in corso rispetto ai dati più "
        "recenti disponibili; la tenuta delle ipotesi di crescita e di costo rispetto all'operatività; i "
        "tempi di incasso e di pagamento rispetto al piano del circolante.")]
    rows = [
        s.row("diagnostica:rettifiche", ["Prima + rettifiche = dopo", _esito_rettifiche(report)]),
        s.row("diagnostica:quadratura", ["Attivo = passivo e patrimonio netto", _esito_quadratura_sp(report, periods)]),
        s.row("diagnostica:cassa", ["Cassa iniziale + flussi = cassa finale", _esito_cassa(report, periods)]),
    ]
    items.append(s.table("diagnostica-controlli", "Controlli di quadratura", ["Controllo", "Esito"], rows))
    return {"form": "rail+main", "id": "diagnostica", "title": "Diagnostica e punti da verificare", "family": FAMILY,
            "subtitle": "Il controllo «9M rettificati + Q4 = chiusura» non è verificabile sul modello: non "
                        "esiste una stima Q4 indipendente dalla chiusura promossa, e si omette invece di "
                        "riprodurlo come spunta vuota.",
            "kpis": kpis, "items": items}


def build(report: FinalReportModelV2) -> list[dict[str, Any]]:
    # "Niente pagine vuote" (m2-02d.md): su una fonte degenere (es. il
    # fixture sintetico "startup", dove ricavi/margini sono tutti a zero) sia
    # il grafico sia la tabella di una pagina possono restare entrambi vuoti
    # — quella pagina si toglie dal catalogo qui, non entra come riquadro
    # bianco e non compare nell'indice.
    pages = [_indicatori(report), _liquidita(report), _redditivita(report), _solidita(report),
             _circolante(report), _composizione(report), _break_even(report), _diagnostica(report)]
    return [page for page in pages if page["items"]]
