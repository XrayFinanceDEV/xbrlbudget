"""Catalogo fisso del dossier v4 (M2-02D) — solo Python, nessuna compilazione
Typst: la resa fisica è coperta da `test_typst_editorial_plan.py` e
`test_pdf_semantic_dossier.py`. Sostituisce `test_editorial_inventory.py`
(inventario generico rimosso): quel file testava un dump completo del
modello — assunzioni annidate, indicatori a blocchi, confronto dei periodi —
che questa fase del catalogo non produce più (`dati.py`/`indicatori.py`
hanno registro vuoto; le loro pagine porteranno di nuovo quei test, quando
esisteranno davvero, non prima).
"""
from decimal import Decimal

import pytest

from app.renderers.typst import dossier_catalog
from app.renderers.typst.dossier_catalog import (
    allegati, apertura, build_inventory, chart_declarations, dati,
    expected_content_inventory, indicatori, piano, shared,
)
from tests.test_final_report_v2 import fixture_report


def _items(inventory):
    return [item for page in inventory for item in page["items"]]


def _rows(inventory):
    return [row for item in _items(inventory) if item["kind"] == "table" for row in item["rows"]]


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_catalog_order_is_the_fixed_v4_page_list(workflow):
    report = fixture_report(workflow, [2027, 2028, 2029])
    inventory = build_inventory(report)
    ids = [page["id"] for page in inventory]
    # Copertina, sintesi, CE previsionale, indice allegati, poi A (2 parti su
    # questa fixture), B (4 parti), C (2 parti) — nessuna pagina di dati.py o
    # indicatori.py, a registro vuoto in questa fase.
    assert ids[:4] == ["cover", "sintesi", "ce", "allegati"]
    assert ids[4:6] == ["allegato-A-1", "allegato-A-2"]
    assert ids[6:10] == ["allegato-B-1", "allegato-B-2", "allegato-B-3", "allegato-B-4"]
    assert ids[10:12] == ["allegato-C-1", "allegato-C-2"]
    # D (registro rettifiche) ed E (matrice ipotesi) esistono solo quando la
    # fixture porta dati per loro — «niente pagine vuote»: la fixture minimale
    # `bilancio`/`startup` non ha rettifiche confermate né alcuno dei driver
    # curati di Allegato E, `infrannuale` ha entrambi (vedi
    # `tests/fixtures/final_report/*.json`). F (indicatori della pratica) e G
    # (indici analitici, 2 parti: 26 indicatori / 13 per parte) leggono sempre
    # dal catalogo indicatori, presente per costruzione su ogni fixture.
    tail = (["allegato-D", "allegato-E"] if workflow == "infrannuale" else []) + [
        "allegato-F", "allegato-G-1", "allegato-G-2", "metodologia"]
    assert ids[12:] == tail
    assert len(ids) == 12 + len(tail)
    assert all(page["items"] for page in inventory), "nessuna pagina vuota nel catalogo"


def test_empty_groups_never_crash_and_contribute_nothing():
    report = fixture_report("bilancio", [2027])
    assert dati.build(report) == []
    assert indicatori.build(report) == []


def test_groups_are_registered_in_the_fixed_v4_family_order():
    assert dossier_catalog.GROUPS == (apertura, dati, piano, indicatori, allegati)


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_appendix_rows_are_lossless_across_the_three_statements(workflow):
    """Ogni riga di CE, SP e rendiconto compare esattamente una volta negli
    Allegati, nello stesso ordine del modello — anche se le COLONNE mostrate
    sono ridotte (chiusura/storico + anni di piano, vincolo del
    proprietario): «rettifiche al minimo» riguarda le colonne, mai le righe."""
    report = fixture_report(workflow, [2027, 2028, 2029])
    inventory = build_inventory(report)
    # Solo A/B/C portano righe `row:<statement>:<row>` (i tre prospetti
    # completi): D/E/F/G sono anch'essi `allegato-*` ma le loro righe seguono
    # una convenzione diversa (rettifica/ipotesi/indicatore), fuori scopo qui.
    appendix_pages = [page for page in inventory
                      if page["id"].split("-")[1:2] in (["A"], ["B"], ["C"])]
    by_statement: dict[str, list[str]] = {"income_statement": [], "balance_sheet": [], "cashflow": []}
    for page in appendix_pages:
        table = page["items"][0]
        for row in table["rows"]:
            _, statement_id, row_id = row["id"].split(":", 2)
            by_statement[statement_id].append(row_id)
    for statement in report.detailed_statements:
        assert by_statement[statement.id] == [row.id for row in statement.rows]


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_no_table_exceeds_five_value_columns(workflow):
    """Vincolo del proprietario (2026-09-17): nessuna tabella del PDF supera 5
    colonne di valore, più la colonna voce."""
    report = fixture_report(workflow, list(range(2027, 2032)))  # 5 anni di piano
    inventory = build_inventory(report)
    for item in _items(inventory):
        if item["kind"] != "table":
            continue
        value_columns = len(item["columns"]) - 1
        assert value_columns <= 5, (item["id"], item["columns"])


def _period(basis, year):
    from app.schemas.final_report_v2 import StatementPeriod
    return StatementPeriod(id=f"{basis}:{year}", year=year, label=f"{year} {basis}", basis=basis,
                           period_months=12, source="test")


def test_select_periods_drops_the_anchor_once_five_plan_years_fill_the_quota():
    periods = [_period("historical", 2025), *(_period("forecast", y) for y in range(2027, 2032))]
    selected = shared.select_periods(periods)
    assert [period.basis for period in selected] == ["forecast"] * 5
    assert [period.year for period in selected] == [2027, 2028, 2029, 2030, 2031]


def test_select_periods_keeps_the_anchor_under_five_plan_years():
    periods = [_period("historical", 2025), *(_period("forecast", y) for y in (2027, 2028, 2029))]
    selected = shared.select_periods(periods)
    assert selected[0].basis == "historical" and selected[0].year == 2025
    assert [period.year for period in selected[1:]] == [2027, 2028, 2029]


def test_select_periods_prefers_closing_over_historical_when_both_exist():
    periods = [_period("historical", 2025), _period("closing", 2026), _period("forecast", 2027)]
    selected = shared.select_periods(periods)
    assert selected[0].basis == "closing" and selected[0].year == 2026


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_ce_summary_table_reads_the_nine_canonical_rows_verbatim(workflow):
    report = fixture_report(workflow, [2027, 2028, 2029])
    inventory = build_inventory(report)
    ce_page = next(page for page in inventory if page["id"] == "ce")
    table = next(item for item in ce_page["items"] if item["kind"] == "table")
    statement = shared.statement_by_id(report, "income_statement")
    periods = shared.forecast_periods(statement)
    assert table["columns"] == ["Voce", *[shared.period_label(period) for period in periods]]
    labels = [row["cells"][0] for row in table["rows"]]
    assert labels == ["Ricavi", "Costi operativi", "EBITDA", "Ammortamenti", "EBIT",
                      "Oneri finanziari", "Risultato ante imposte", "Imposte", "Risultato netto"]
    for (code, _), row in zip(piano._CE_SUMMARY_ROWS, table["rows"]):
        row_obj = shared.statement_row(statement, code)
        expected = [shared.exact(value) for value in shared.values_for_periods(row_obj, statement, periods)]
        assert row["cells"][1:] == expected


def test_large_exact_decimal_survives_into_an_appendix_cell():
    report = fixture_report("bilancio", [2027])
    huge = Decimal("9007199254740993.123456789012345678")
    statement = next(s for s in report.detailed_statements if s.id == "income_statement")
    row_index = next(i for i, row in enumerate(statement.rows) if row.code == "ce01_ricavi_vendite")
    statement.rows[row_index].values[-1] = huge
    statement.rows[row_index].unavailable_reasons[-1] = None
    inventory = build_inventory(report)
    rows = {row["id"]: row for row in _rows(inventory)}
    matching = [row for row_id, row in rows.items() if row_id == "row:income_statement:income_statement:ce01_ricavi_vendite"]
    assert matching, list(rows)[:5]
    assert str(huge) in matching[0]["cells"]


def test_chart_omitted_when_no_series_has_any_value():
    report = fixture_report("startup", [2027, 2028, 2029])  # zeroed synthetic source: no margin data
    inventory = build_inventory(report)
    ce_page = next(page for page in inventory if page["id"] == "ce")
    assert not any(item["kind"] == "chart" for item in ce_page["items"])
    # Senza grafico i KPI restano comunque in cima alla pagina: non si perde
    # per questo la colonna KPI.
    sintesi_page = next(page for page in inventory if page["id"] == "sintesi")
    has_chart = any(item["kind"] == "chart" for item in sintesi_page["items"])
    assert has_chart or sintesi_page["kpis"]


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_expected_content_inventory_is_ordered_unique_and_starts_with_cover(workflow):
    report = fixture_report(workflow, [2027, 2028])
    inventory = build_inventory(report)
    expected = expected_content_inventory(report)
    assert list(expected)[0] == "cover"
    assert len(expected) == len(set(expected))
    flattened = []
    for page in inventory:
        for item in page["items"]:
            if item["kind"] == "cover":
                flattened.append("cover")
            elif item["kind"] in ("chart", "text", "note", "index"):
                flattened.append(item["id"])
            else:
                flattened.append(f"heading:{item['id']}")
                flattened.extend(row["id"] for row in item["rows"])
    assert list(expected) == flattened
    # Ogni content_id mappa alla pagina che lo dichiara — un contenuto della
    # copertina alla copertina, un contenuto di una tabella alla pagina che
    # porta quella tabella. Il resto (nessuna pagina fisica mescola due
    # pagine del catalogo) lo dimostra `build_editorial_plan`, già coperto da
    # `test_typst_editorial_plan.py`.
    for page in inventory:
        for item in page["items"]:
            owned = ["cover"] if item["kind"] == "cover" else (
                [item["id"]] if item["kind"] in ("chart", "text", "note", "index")
                else [f"heading:{item['id']}", *(row["id"] for row in item["rows"])])
            assert all(expected[content_id] == page["id"] for content_id in owned)


def test_duplicate_content_id_across_pages_is_rejected():
    report = fixture_report("bilancio", [2027])

    class _Broken:
        @staticmethod
        def build(report):
            return [{"id": "duplicate-cover", "title": None, "family": None, "subtitle": None,
                     "kpis": [], "items": [{"id": "cover", "kind": "cover", "title": "x"}]}]

    original = dossier_catalog.GROUPS
    try:
        dossier_catalog.GROUPS = (apertura, _Broken)
        with pytest.raises(ValueError, match="duplicate editorial content id"):
            expected_content_inventory(report)
    finally:
        dossier_catalog.GROUPS = original


def test_chart_declarations_key_by_content_id_and_expose_page_scoped_charts():
    """Un grafico di pagina (es. «Evoluzione dei margini» sul CE previsionale)
    non è necessariamente una serie canonica di `report.chart_series`: deve
    comunque essere risolvibile per content_id, non per lookup nel modello."""
    report = fixture_report("bilancio", [2027, 2028, 2029])
    charts = chart_declarations(report)
    assert "chart:sintesi-andamento" in charts
    canonical_ids = {chart.id for chart in report.chart_series}
    assert "sintesi-andamento" not in canonical_ids
    assert charts["chart:sintesi-andamento"]["chart"]["id"] == "sintesi-andamento"


def test_build_inventory_rejects_non_v2_report():
    with pytest.raises(TypeError):
        build_inventory(object())
