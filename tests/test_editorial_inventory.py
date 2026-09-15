"""Lossless editorial inventory checks across the three canonical workflows."""
from decimal import Decimal

import pytest

from app.renderers.typst.editorial_inventory import (
    SECTION_IDS,
    build_inventory,
    expected_content_inventory,
)
from tests.test_final_report_v2 import fixture_report


def _items(inventory):
    return [item for section in inventory for item in section["items"]]


def _rows(inventory):
    return [row for item in _items(inventory) if item["kind"] == "table" for row in item["rows"]]


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
    assert {item["chart_id"] for item in items if item["kind"] == "chart"} == {chart.id for chart in report.chart_series}
    assert len([item for item in items if item["kind"] == "chart"]) == 16
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
    assert scalar["cells"][-2:] == ["no", None]

    # The fixture supplies all six nested structures.  Stable row IDs make the
    # full source data visible to the template and prevent silent omission.
    required_prefixes = {
        "assumption:pregresso-nuovo:financing_loans:loan:0",
        "assumption:pregresso-nuovo:pregresso:crediti_commerciali:opening",
        "assumption:imposte:tax_temporary_differences:temporary_difference:0",
        "assumption:altre-voci-ce:ce_overrides:ce_override:0",
        "assumption:circolante:sp_indexing:sp_indexing:0",
        "assumption:circolante:sp_overrides:sp_override:0",
    }
    assert all(any(row_id.startswith(prefix + ":field:") for row_id in rows) for prefix in required_prefixes)
    flattened = "\n".join(cell for row in rows.values() for cell in row["cells"] if cell is not None)
    for exact in ("100000.00", "120", "200", "120.00", "sp16g", "50.00"):
        assert exact in flattened


def test_expected_markers_cover_every_chart_indicator_and_appendix_source_row_once():
    report = fixture_report("infrannuale")
    inventory = build_inventory(report)
    expected = expected_content_inventory(report)

    assert list(expected)[0] == "cover"
    assert expected["appendix-index"] == "appendices_methodology"
    assert len(expected) == len(set(expected))
    for chart in report.chart_series:
        assert list(expected).count(f"chart:{chart.id}") == 1
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
