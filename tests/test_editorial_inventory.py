"""Lossless editorial inventory checks across the three canonical workflows."""
from decimal import Decimal

import pytest

from app.renderers.typst.editorial_inventory import (
    SECTION_IDS,
    build_inventory,
    chart_view,
    expected_content_inventory,
)
from app.schemas.final_report import AssumptionValue, OtherLender
from tests.test_final_report_v2 import fixture_report


def _items(inventory):
    return [item for section in inventory for item in section["items"]]


def _rows(inventory):
    return [row for item in _items(inventory) if item["kind"] == "table" for row in item["rows"]]


def _charts_with_values(report):
    # M2-02B: un grafico senza alcun valore nel timeline non occupa una pagina
    # «n.d.»; resta in pagina solo come «pagina orfana», cioè quando la sezione
    # non avrebbe altrimenti alcun marcatore.
    return {chart.id for chart in report.chart_series
            if any(value is not None for series in chart_view(report, chart.id)["series"] for value in series["values"])}


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_workflows_have_the_complete_ordered_and_marked_inventory(workflow):
    report = fixture_report(workflow, [2027])
    inventory = build_inventory(report)
    items = _items(inventory)
    rows = _rows(inventory)

    expected_sections = [identifier for identifier in SECTION_IDS if workflow == "infrannuale" or identifier != "infrannual_closing"]
    assert [section["id"] for section in inventory] == expected_sections
    assert all(section["items"] for section in inventory)
    assert all(len(row["cells"]) == len(item["columns"]) == len(row["units"])
               for item in items if item["kind"] == "table" for row in item["rows"])
    rendered = {item["chart_id"] for item in items if item["kind"] == "chart"}
    with_values = _charts_with_values(report)
    assert with_values <= rendered
    # Ogni grafico senza valori che resta in pagina è una pagina orfana: la sua
    # sezione non contiene cioè altri maricatori.
    for chart_id in rendered - with_values:
        section = next(section for section in inventory
                       if any(item.get("chart_id") == chart_id for item in section["items"]))
        assert all(item["kind"] == "chart" for item in section["items"])
    assert ("infrannual-closing-values" in {item["id"] for item in items}) == (workflow == "infrannuale")
    # The one-year fixture intentionally retains source assumptions over three
    # periods.  The renderer must expose the exact extras, never discard them.
    assumptions = next(item for item in items if item["id"] == "assumptions:fatturato")
    if workflow == "infrannuale":
        assert assumptions["columns"][1:4] == ["2027", "Periodo non associato 1", "Periodo non associato 2"]
    assert len({row["id"] for row in rows}) == len(rows)


def test_nested_assumptions_and_large_exact_decimals_are_not_lost():
    report = fixture_report("infrannuale")
    report.forecast.years[0].income_statement[0].value = Decimal("9007199254740993.123456789012345678")
    # Inactive assumptions remain reportable with their declared provenance.
    report.assumption_sections[1].assumptions[0].active = False
    inventory = build_inventory(report)
    rows = {row["id"]: row for row in _rows(inventory)}

    forecast = rows["forecast:income_statement:revenue"]
    assert "9007199254740993.123456789012345678" in forecast["cells"]
    scalar = rows["assumption:fatturato:revenue_growth_pct:value"]
    # M2-02B rilievo 6: la colonna «Indisponibilità» è sparita dalla tabella
    # base; l'ultima cella è ora «Attiva».
    assert scalar["cells"][-1] == "no"

    # The fixture supplies all six nested structures.  Stable row IDs make the
    # full source data visible to the template and prevent silent omission.
    required_prefixes = {
        "assumption:patrimoniale-pregresso:financing_loans:loan:0",
        "assumption:patrimoniale-pregresso:pregresso:crediti_commerciali:opening",
        "assumption:imposte:tax_temporary_differences:temporary_difference:0",
        "assumption:costi:ce_overrides:ce_override:0",
        "assumption:patrimoniale-piano:sp_indexing:sp_indexing:0",
        "assumption:patrimoniale-piano:sp_overrides:sp_override:0",
    }
    assert all(any(row_id.startswith(prefix + ":field:") for row_id in rows) for prefix in required_prefixes)
    flattened = "\n".join(cell for row in rows.values() for cell in row["cells"] if cell is not None)
    for exact in ("100000.00", "120", "200", "120.00", "sp16g", "50.00"):
        assert exact in flattened


def test_main_branch_financing_details_are_preserved_in_the_inventory():
    report = fixture_report("infrannuale")
    section = next(section for section in report.assumption_sections if section.key == "patrimoniale-pregresso")
    loans = next(item for item in section.assumptions if item.field == "financing_loans")
    loans.financing_loans[0].repayments = [Decimal("25.50")]
    pregresso = next(item for item in section.assumptions if item.field == "pregresso")
    pregresso.pregresso.crediti_commerciali.non_incassato = True
    section.assumptions.append(AssumptionValue(
        field="other_lenders", label="Altri finanziatori", values=[None],
        provenance="user", active=True,
        other_lenders=[OtherLender(name="Socio", opening_residual=Decimal("90.125"),
                                   interest_rate=Decimal("0.03"), repayments=[Decimal("30.25")])],
    ))
    rows = {row["id"]: row for row in _rows(build_inventory(report))}

    assert rows["assumption:patrimoniale-pregresso:financing_loans:loan:0:repayment:0:field:1"]["cells"][1] == "25.50"
    assert rows["assumption:patrimoniale-pregresso:pregresso:crediti_commerciali:non_incassato:field:1"]["cells"][1] == "sì"
    lender = "assumption:patrimoniale-pregresso:other_lenders:other_lender:0"
    assert rows[f"{lender}:field:1"]["cells"][1] == "90.125"
    assert rows[f"{lender}:field:2"]["cells"][1] == "0.03"
    assert rows[f"{lender}:repayment:0:field:1"]["cells"][1] == "30.25"


def test_expected_markers_cover_every_chart_indicator_and_appendix_source_row_once():
    report = fixture_report("infrannuale")
    inventory = build_inventory(report)
    expected = expected_content_inventory(report)

    assert list(expected)[0] == "cover"
    assert expected["appendix-index"] == "appendices_methodology"
    assert len(expected) == len(set(expected))
    rendered = {item["chart_id"] for item in _items(inventory) if item["kind"] == "chart"}
    for chart in report.chart_series:
        assert list(expected).count(f"chart:{chart.id}") == (1 if chart.id in rendered else 0)
    for indicator in report.indicator_catalog:
        assert list(expected).count(f"indicator:{indicator.id}") == 1

    appendix_ids = [row["id"] for item in _items(inventory) if item["id"].startswith("appendix:")
                    for row in item["rows"]]
    source_ids = [f"row:{statement.id}:{row.id}" for statement in report.detailed_statements for row in statement.rows]
    assert appendix_ids == source_ids
    assert all(expected[row_id] == "appendices_methodology" for row_id in source_ids)
    assert {"heading:" + item["id"] for item in _items(inventory) if item["kind"] == "table"} <= set(expected)


def test_ambiguous_canonical_periods_or_forecast_lines_are_rejected():
    report = fixture_report("bilancio")
    report.forecast.years[0].income_statement.append(report.forecast.years[0].income_statement[0].model_copy())
    with pytest.raises(ValueError, match="duplicate canonical forecast line"):
        build_inventory(report)

    report = fixture_report("bilancio")
    report.indicator_catalog[1].periods[0] = report.indicator_catalog[1].periods[0].model_copy(update={"label": "Periodo incompatibile"})
    with pytest.raises(ValueError, match="conflicting indicator period"):
        build_inventory(report)


@pytest.mark.parametrize("workflow", ("bilancio", "infrannuale", "startup"))
def test_il_dossier_non_riversa_i_calcoli_grezzi(workflow):
    """«Calcoli previsionali canonici» portava nel documento gli output interni dei calcolatori:
    il codice tecnico come etichetta, nessuna unità, 73.33333333333333333333333333. Gli stessi
    indicatori stanno nel catalogo con etichetta, unità e metodologia (decisione del
    proprietario, 2026-09-17: toglierla)."""
    inventory = build_inventory(fixture_report(workflow, [2027]))
    assert "forecast-calculations" not in {item["id"] for item in _items(inventory)}
    assert not [row for row in _rows(inventory) if row["id"].startswith("forecast:calculations:")]
