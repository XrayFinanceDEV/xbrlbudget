"""Gruppo INDICATORI (M2-02D fase 2, v4 pagine 11-18): test Python puri sul
catalogo — nessuna compilazione Typst (quella è coperta da
`test_typst_editorial_plan.py` e `test_pdf_semantic_dossier.py`, entrambi
esercitati manualmente su questo gruppo a ogni pagina aggiunta).
"""
from decimal import Decimal

import pytest

from app.renderers.typst.dossier_catalog import indicatori
from tests.test_final_report_v2 import fixture_report


def _items(pages):
    return [item for page in pages for item in page["items"]]


def _charts(pages):
    return [item for item in _items(pages) if item["kind"] == "chart"]


def _tables(pages):
    return [item for item in _items(pages) if item["kind"] == "table"]


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_build_returns_the_pages_implemented_so_far(workflow):
    """Fase 2 in corso: il gruppo cresce di pagina in pagina (un commit a
    testa) — qui solo l'ordine v4 di ciò che esiste già, mai un conteggio
    fisso che andrebbe aggiornato a ogni pagina aggiunta."""
    report = fixture_report(workflow, [2027, 2028, 2029])
    pages = indicatori.build(report)
    assert [page["id"] for page in pages] == ["indicatori", "liquidita"]


def test_liquidita_page_reuses_the_structural_balance_chart_id():
    """`structural_balance` è già dichiarato fra i grafici a barre di
    `chart-layout.json` (e nel catalogo legacy `DOSSIER_CHARTS`, stessi tre
    indicatori CCN/MT/MS): riusarlo qui evita una voce duplicata."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = indicatori.build(report)[1]
    assert page["id"] == "liquidita"
    charts = _charts([page])
    assert len(charts) == 1
    assert charts[0]["chart"]["id"] == "structural_balance"
    assert {series["label"] for series in charts[0]["chart"]["series"]} == {"CCN", "Margine di Tesoreria",
                                                                             "Margine di Struttura"}


def test_liquidita_table_omits_current_and_quick_ratio_when_denominator_is_zero():
    """Sulla fixture sintetica (SP tutto a zero) `practice.current_ratio` e
    `practice.quick_ratio` sono `None` per `zero_denominator`: la riga si
    omette, mai un «n.d.» — le altre tre righe restano."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = indicatori.build(report)[1]
    table = _tables([page])[0]
    row_labels = [row["cells"][0] for row in table["rows"]]
    assert row_labels == ["Capitale circolante netto", "Margine di tesoreria", "Margine di struttura"]


def test_indicatori_page_has_chart_and_summary_table():
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = indicatori.build(report)[0]
    assert page["family"] == "Piano e risultati"
    assert page["title"] == "Indicatori e rischi"
    charts = _charts([page])
    assert len(charts) == 1
    chart = charts[0]["chart"]
    assert chart["id"] == "indicatori-debito-cassa-pfn"
    assert chart["unit"] == "eur"
    assert {series["label"] for series in chart["series"]} == {"Debiti finanziari", "Cassa", "PFN"}
    tables = _tables([page])
    assert len(tables) == 1
    row_labels = [row["cells"][0] for row in tables[0]["rows"]]
    assert row_labels == ["PFN", "PFN / EBITDA", "EBITDA margin", "Circolante operativo (CCN)"]


def test_indicatori_kpis_move_into_the_chart_block_not_the_page_strip():
    """Stesso pattern di `piano.py::_ce`: quando la pagina ha un grafico, i
    KPI stanno nella colonna a fianco del grafico (`item["kpis"]`), non nella
    striscia orizzontale di testa (`page["kpis"]`) — altrimenti sarebbero
    duplicati a schermo."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = indicatori.build(report)[0]
    assert page["kpis"] == []
    chart_item = _charts([page])[0]
    assert len(chart_item["kpis"]) >= 1


def test_debt_cash_pfn_chart_mixes_three_independent_sources():
    """Il grafico di pagina 11 combina una serie di `structure_series`
    (debiti finanziari), una riga di prospetto (cassa) e un indicatore (PFN):
    nessuno dei tre costruttori di `shared.py`, che leggono una sola fonte,
    può bastare da solo (`_chart`, helper locale del gruppo)."""
    report = fixture_report("bilancio", [2027])
    page = indicatori.build(report)[0]
    chart = _charts([page])[0]["chart"]
    assert len(chart["categories"]) == 1
    for series in chart["series"]:
        assert len(series["values"]) == 1


def test_kpi_delta_needs_at_least_two_periods():
    report = fixture_report("bilancio", [2027])
    periods = indicatori._periods(report)
    assert indicatori._kpi_delta(report, "practice.ccn", "assorbimento circolante", "eur", periods) is None
    report3 = fixture_report("bilancio", [2027, 2028, 2029])
    periods3 = indicatori._periods(report3)
    delta = indicatori._kpi_delta(report3, "practice.ccn", "assorbimento circolante", "eur", periods3)
    assert delta is not None and delta["label"].startswith("assorbimento circolante · 2027-2029")


def test_indicator_table_omits_missing_identifiers_and_drops_when_all_missing():
    report = fixture_report("bilancio", [2027])
    periods = indicatori._periods(report)
    table = indicatori._indicator_table("t", "Titolo", report, periods,
        [("practice.pfn", "PFN"), ("practice.non_existent", "Fantasma")])
    assert table is not None
    assert [row["cells"][0] for row in table["rows"]] == ["PFN"]
    empty = indicatori._indicator_table("t", "Titolo", report, periods, [("practice.non_existent", "Fantasma")])
    assert empty is None
