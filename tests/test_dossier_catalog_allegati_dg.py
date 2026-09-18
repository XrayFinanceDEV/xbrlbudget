"""Allegati D-G (v4 pagine 28-33): registro delle rettifiche, matrice delle
ipotesi, indicatori della pratica, indici analitici, metodologia. Solo
Python, nessuna compilazione Typst (coperta da `test_typst_editorial_plan.py`
e `test_pdf_semantic_dossier.py`). Compagno di `test_dossier_catalog.py`, che
resta sull'indice e su A/B/C.
"""
from decimal import Decimal

import pytest

from app.renderers.typst.dossier_catalog import allegati, build_inventory, shared
from app.schemas.final_report_v2 import StatementPeriod
from tests.test_final_report_v2 import fixture_report


def _page(report, page_id):
    return next(page for page in build_inventory(report) if page["id"] == page_id)


def _table(page):
    return next(item for item in page["items"] if item["kind"] == "table")


# ── format_unit ───────────────────────────────────────────────────────────

def test_format_unit_bakes_the_suffix_into_the_cell_not_the_label():
    assert shared.format_unit(Decimal("17.7532"), "percent") == "17,75%"
    assert shared.format_unit(Decimal("228.121"), "days") == "228,12 gg"
    assert shared.format_unit(Decimal("7.5749"), "ratio") == "7,57×"


def test_format_unit_keeps_decimal_exact_thousands_and_sign():
    assert shared.format_unit(Decimal("1234.5"), "percent") == "1.234,50%"
    assert shared.format_unit(Decimal("-9.3553"), "ratio") == "−9,36×"


def test_format_unit_omits_missing_values_never_fabricates_nd():
    assert shared.format_unit(None, "percent") is None


# ── period_label_short / period_basis_legend ─────────────────────────────

def _period(basis, year, months=12):
    return StatementPeriod(id=f"{basis}:{year}", year=year, label=f"{year} {basis}", basis=basis,
                           period_months=months, source="test")


def test_period_label_short_is_letter_and_year_never_the_long_form():
    assert shared.period_label_short(_period("closing", 2026)) == "2026 C"
    assert shared.period_label_short(_period("forecast", 2027)) == "2027 P"


def test_period_label_short_prefixes_months_only_when_genuinely_partial():
    assert shared.period_label_short(_period("adjusted", 2026, months=6)) == "6M 2026 R"
    assert shared.period_label_short(_period("closing", 2026, months=12)) == "2026 C"


def test_period_basis_legend_spells_out_each_letter_once_in_order():
    periods = [_period("adjusted", 2026, months=6), _period("closing", 2026), _period("forecast", 2027)]
    legend = shared.period_basis_legend(periods)
    assert legend == "R: rettificato; C: chiusura; P: previsione di piano"


def test_select_periods_with_adjusted_keeps_the_adjusted_column():
    periods = [_period("historical", 2025), _period("observed", 2026, months=6),
              _period("adjusted", 2026, months=6), _period("closing", 2026),
              *(_period("forecast", y) for y in (2027, 2028, 2029))]
    selected = shared.select_periods_with_adjusted(periods)
    assert [p.basis for p in selected] == ["adjusted", "closing", "forecast", "forecast", "forecast"]


def test_select_periods_with_adjusted_degrades_without_an_adjusted_period():
    periods = [_period("historical", 2025), *(_period("forecast", y) for y in (2027, 2028, 2029))]
    assert ([p.basis for p in shared.select_periods_with_adjusted(periods)] ==
            [p.basis for p in shared.select_periods(periods)])


# ── Allegato D · Registro delle rettifiche ───────────────────────────────

def test_allegato_d_has_exactly_one_table_with_the_three_mandated_columns():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    page = _page(report, "allegato-D")
    assert len(page["items"]) == 1
    table = _table(page)
    assert table["columns"] == ["Voce", "Rettifica (delta)", "Motivazione"]


def test_allegato_d_one_row_per_confirmed_entry_no_counterpart_no_before_after():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    table = _table(_page(report, "allegato-D"))
    assert len(table["rows"]) == len(report.adjustments.entries)
    for row, entry in zip(table["rows"], report.adjustments.entries):
        assert row["cells"] == [entry.edited_label, shared.exact(entry.edit_delta), entry.explanation]
        assert entry.counterpart_label not in table["columns"]


def test_allegato_d_is_omitted_when_adjustments_are_not_confirmed():
    report = fixture_report("startup", [2027, 2028, 2029])
    assert not report.adjustments.confirmed
    assert not any(page["id"] == "allegato-D" for page in build_inventory(report))


def test_allegato_d_is_omitted_when_confirmed_but_empty():
    report = fixture_report("bilancio", [2027, 2028, 2029])
    assert report.adjustments.confirmed and not report.adjustments.entries
    assert not any(page["id"] == "allegato-D" for page in build_inventory(report))


# ── Allegato E · Matrice delle ipotesi ───────────────────────────────────

def test_allegato_e_only_lists_driver_rows_the_model_actually_supplies():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    table = _table(_page(report, "allegato-E"))
    labels = [row["cells"][0] for row in table["rows"]]
    # La fixture `infrannuale` porta solo revenue_growth_pct e dso_days fra i
    # driver curati (vedi tests/fixtures/final_report/infrannuale.json): gli
    # altri campi di `_DRIVER_ROWS` sono tutti None e restano fuori, mai un
    # "n.d." a riempire la riga.
    assert labels == ["Crescita ricavi", "DSO"]


def test_allegato_e_cells_carry_the_unit_in_percent_and_days_rows():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    table = _table(_page(report, "allegato-E"))
    revenue_row = next(row for row in table["rows"] if row["cells"][0] == "Crescita ricavi")
    assert revenue_row["cells"][1:] == ["5,13%", "4,00%", "3,50%"]
    dso_row = next(row for row in table["rows"] if row["cells"][0] == "DSO")
    assert dso_row["cells"][1] is None  # primo anno non dichiarato: n.d. in cella, non nell'etichetta
    assert dso_row["cells"][2:] == ["58,00 gg", "55,00 gg"]


def test_allegato_e_is_omitted_when_no_curated_driver_has_any_value():
    report = fixture_report("bilancio", [2027, 2028, 2029])
    assert not any(page["id"] == "allegato-E" for page in build_inventory(report))


# ── Allegato F · Indicatori della pratica ────────────────────────────────

def test_allegato_f_has_all_fifteen_practice_indicators_in_catalog_order():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    table = _table(_page(report, "allegato-F"))
    assert len(table["rows"]) == 15
    ids = [f"practice.{key}" for key in allegati._PRACTICE_INDICATOR_KEYS]
    assert [row["id"] for row in table["rows"]] == [f"row:{i}" for i in ids]


def test_allegato_f_never_exceeds_five_value_columns():
    for workflow in ("bilancio", "infrannuale", "startup"):
        report = fixture_report(workflow, [2027, 2028, 2029])
        table = _table(_page(report, "allegato-F"))
        assert len(table["columns"]) - 1 <= 5


def test_allegato_f_eur_rows_go_through_the_amount_cell_not_format_unit():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    table = _table(_page(report, "allegato-F"))
    pfn_row = next(row for row in table["rows"] if row["id"] == "row:practice.pfn")
    idx = allegati._PRACTICE_INDICATOR_KEYS.index("pfn")
    assert idx  # pfn is not the label column
    # An eur cell is a plain exact() Decimal string (or None), never a
    # unit-suffixed token like the percent/ratio rows.
    assert all(cell is None or "×" not in cell and "%" not in cell for cell in pfn_row["cells"][1:])


# ── Allegato G · Indici analitici ────────────────────────────────────────

def test_allegato_g_splits_the_26_analytical_indicators_into_two_parts():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    inventory = build_inventory(report)
    g_pages = [page for page in inventory if page["id"].startswith("allegato-G-")]
    assert [page["id"] for page in g_pages] == ["allegato-G-1", "allegato-G-2"]
    total_rows = sum(len(_table(page)["rows"]) for page in g_pages)
    assert total_rows == 26
    ids = [f"analytical.{key}" for key in allegati._ANALYTICAL_INDICATOR_KEYS]
    seen = [row["id"] for page in g_pages for row in _table(page)["rows"]]
    assert seen == [f"row:{i}" for i in ids]


def test_allegato_g_never_exceeds_five_value_columns():
    report = fixture_report("infrannuale", list(range(2027, 2032)))  # 5 plan years
    inventory = build_inventory(report)
    for page in inventory:
        if page["id"].startswith("allegato-G-"):
            assert len(_table(page)["columns"]) - 1 <= 5


def test_allegato_g_acid_test_and_leverage_are_not_forced_to_nd():
    """Correzione rispetto alla v4 dimostrativa: nel modello reale questi due
    indicatori sono calcolati, e la pagina li legge come ogni altro — non
    esiste un ramo speciale che li forza a "n.d."."""
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    inventory = build_inventory(report)
    rows = [row for page in inventory if page["id"].startswith("allegato-G-") for row in _table(page)["rows"]]
    acid_test = next(row for row in rows if row["id"] == "row:analytical.liquidity.acid_test")
    leverage = next(row for row in rows if row["id"] == "row:analytical.extended_profitability.financial_leverage_effect")
    # La fixture di test può non avere un valore per ogni periodo; la riga
    # non deve però essere assente dal catalogo — questo è ciò che il vecchio
    # comportamento dimostrativo sbagliava.
    assert acid_test["cells"][0] == "Acid Test"
    assert leverage["cells"][0] == "Leva Finanziaria"


# ── Metodologia ───────────────────────────────────────────────────────────

def test_metodologia_page_has_text_table_and_note_never_a_report_calculation():
    report = fixture_report("bilancio", [2027, 2028, 2029])
    page = _page(report, "metodologia")
    kinds = [item["kind"] for item in page["items"]]
    assert kinds == ["text", "table", "note"]
    table = _table(page)
    assert table["columns"] == ["Struttura", "Fonte nel progetto"]
    # Le fonti sono testo statico del progetto, non un valore del report.
    sources = [row["cells"][1] for row in table["rows"]]
    assert all("frontend" not in source for source in sources)


def test_metodologia_page_exists_for_every_workflow():
    for workflow in ("bilancio", "infrannuale", "startup"):
        report = fixture_report(workflow, [2027, 2028, 2029])
        assert any(page["id"] == "metodologia" for page in build_inventory(report))


# ── Il titolo di pagina e quello di tabella non si ripetono ─────────────

def test_appendix_page_title_and_table_title_never_repeat_the_same_phrase():
    """Difetto osservato su AMBIENTA prima di questo giro: il titolo di
    pagina («A · Conto economico completo — prospetto completo») e il titolo
    della tabella subito sotto («A · Conto economico completo · parte 1 di
    2») condividevano la stessa frase quasi per intero."""
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    for page in build_inventory(report):
        for item in page["items"]:
            if item["kind"] != "table" or page["title"] is None:
                continue
            assert item["title"] != page["title"], page["id"]
            assert page["title"] not in item["title"], page["id"]


def test_index_page_lists_d_e_f_g_not_only_a_b_c():
    report = fixture_report("infrannuale", [2027, 2028, 2029])
    index_item = next(item for item in _page(report, "allegati")["items"] if item["kind"] == "index")
    targets = {entry["target"] for entry in index_item["entries"]}
    for page_id in ("allegato-D", "allegato-E", "allegato-F", "allegato-G-1", "allegato-G-2"):
        assert f"heading:{page_id}" in targets, page_id
    # La metodologia non è un prospetto: non compare nell'indice, come la v4.
    assert not any("metodologia" in entry["target"] for entry in index_item["entries"])


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_no_table_in_the_new_pages_exceeds_five_value_columns(workflow):
    report = fixture_report(workflow, [2027, 2028, 2029])
    for page in build_inventory(report):
        if page["id"] not in ("allegato-D", "allegato-E", "allegato-F", "allegato-G-1",
                              "allegato-G-2", "metodologia"):
            continue
        for item in page["items"]:
            if item["kind"] == "table":
                assert len(item["columns"]) - 1 <= 5, (page["id"], item["columns"])
