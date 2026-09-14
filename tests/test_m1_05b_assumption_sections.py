"""M1-05B — assumption mapping, provenance and dead-field rules of the report.

Ownership: this file and ``backend/app/services/final_report_assumptions.py``
only.  The rows built here are the same ``BudgetAssumptions`` objects the bulk
assumptions service persists; ``explicitly_supplied_fields`` follows the M1-01
convention (NULL = legacy, ``[]`` = tracked with nothing supplied).
"""
import re
from decimal import Decimal
from pathlib import Path

import pytest

import backend.app.services.final_report_assumptions as fra_module  # noqa: F401 — loads the backend/ path shim
from app.schemas.final_report import (
    ASSUMPTION_SECTION_CATALOG,
    AssumptionSection,
)
from app.services.final_report_assumptions import (
    CATALOG,
    build_assumption_sections,
    dead_assumption_fields,
)
from database.models import BudgetAssumptions


ROOT = Path(__file__).resolve().parents[1]

ALL_CATALOG_FIELDS = [
    field
    for section in ASSUMPTION_SECTION_CATALOG
    for field in [*section["fields"], *section.get("nested_fields", [])]
]


def _row(year: int, supplied=None, **values) -> BudgetAssumptions:
    row = BudgetAssumptions(scenario_id=1, forecast_year=year, **values)
    row.explicitly_supplied_fields = supplied
    return row


def _build(*rows):
    return build_assumption_sections(rows)


def _by_field(read_model):
    return {a.field: a for section in read_model.sections for a in section.assumptions}


def _codes(diagnostics):
    return [d.code for d in diagnostics]


# ---------------------------------------------------------------------------
# Catalog coverage
# ---------------------------------------------------------------------------

def test_module_maps_the_shared_catalog_not_a_private_copy():
    assert [dict(section) for section in CATALOG] == [dict(section) for section in ASSUMPTION_SECTION_CATALOG]


def test_sections_are_the_seven_canonical_groups_in_order():
    read_model = _build(_row(2027, supplied=[]))
    assert [section.key for section in read_model.sections] == [s["key"] for s in ASSUMPTION_SECTION_CATALOG]
    assert [section.title for section in read_model.sections] == [s["title"] for s in ASSUMPTION_SECTION_CATALOG]


def test_every_supported_assumption_maps_exactly_once_with_no_duplicates():
    read_model = _build(_row(2027, supplied=[]))
    emitted = [a.field for section in read_model.sections for a in section.assumptions]
    assert sorted(emitted) == sorted(ALL_CATALOG_FIELDS)
    assert len(emitted) == len(set(emitted)) == len(ALL_CATALOG_FIELDS)


def test_sections_pass_the_contract_section_validators():
    read_model = _build(_row(2027, supplied=[]))
    for section in read_model.sections:
        AssumptionSection.model_validate(section.model_dump())


def test_scenario_section_carries_no_assumption_rows():
    read_model = _build(_row(2027, supplied=[]))
    scenario = next(section for section in read_model.sections if section.key == "scenario")
    assert scenario.assumptions == []


def test_requires_at_least_one_row():
    with pytest.raises(ValueError):
        build_assumption_sections([])


# ---------------------------------------------------------------------------
# DEAD_FIELDS
# ---------------------------------------------------------------------------

def test_derived_dead_field_set_is_exactly_the_wizard_list():
    wizard = (ROOT / "frontend" / "lib" / "budget-wizard-steps.ts").read_text(encoding="utf-8")
    body = wizard.split("export const DEAD_FIELDS", 1)[1].split("] as const", 1)[0]
    frontend_dead = set(re.findall(r'"([a-z0-9_]+)"', body))
    assert frontend_dead  # the parse found the list, it did not silently no-op
    assert set(dead_assumption_fields()) == frontend_dead


def test_dead_fields_never_appear_among_emitted_assumptions():
    read_model = _build(_row(2027, supplied=[], investments=Decimal("5000"),
                             receivables_short_growth_pct=Decimal("3"), payables_short_growth_pct=Decimal("2"),
                             interest_rate_receivables=Decimal("1"), interest_rate_payables=Decimal("1")))
    emitted = {a.field for section in read_model.sections for a in section.assumptions}
    assert emitted.isdisjoint(dead_assumption_fields())
    for assumption in (a for section in read_model.sections for a in section.assumptions):
        assert assumption.active is True


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def test_supplied_values_are_user_not_compared_with_defaults():
    # revenue_growth_pct keeps the schema's own 0.0 default value, yet it was
    # supplied: the classification reads the tracked list, never the amount.
    read_model = _build(_row(2027, supplied=["revenue_growth_pct"], revenue_growth_pct=Decimal("0")))
    assert _by_field(read_model)["revenue_growth_pct"].provenance == "user"


def test_tracked_unsupplied_values_are_default_and_null_series_are_automatic():
    read_model = _build(
        _row(2027, supplied=[], revenue_growth_pct=Decimal("2.5")),
        _row(2028, supplied=[], revenue_growth_pct=Decimal("2.5")),
    )
    values = _by_field(read_model)
    assert values["revenue_growth_pct"].provenance == "default"
    assert values["dso_days"].provenance == "automatic"  # NULL everywhere = the documented rule reads it


def test_override_bags_are_classified_as_override():
    read_model = _build(_row(2027, supplied=[], ce05_override=Decimal("1000"),
                             sp_overrides={"sp09_disponibilita_liquide": "50.00"}))
    values = _by_field(read_model)
    assert values["ce_overrides"].provenance == "override"
    assert values["sp_overrides"].provenance == "override"


def test_tax_rate_is_ignored_when_every_year_forces_ce20():
    read_model = _build(
        _row(2027, supplied=["tax_rate"], tax_rate=Decimal("27.9"), ce20_override=Decimal("250")),
        _row(2028, supplied=[], tax_rate=Decimal("27.9"), ce20_override=Decimal("260")),
    )
    assert _by_field(read_model)["tax_rate"].provenance == "ignored"


def test_tax_rate_still_a_driver_when_only_one_year_forces_ce20():
    read_model = _build(
        _row(2027, supplied=[], tax_rate=Decimal("27.9"), ce20_override=Decimal("250")),
        _row(2028, supplied=[], tax_rate=Decimal("27.9")),
    )
    assert _by_field(read_model)["tax_rate"].provenance == "default"


def test_missing_persisted_provenance_is_legacy_unknown_with_one_diagnostic():
    read_model = _build(_row(2027, supplied=None), _row(2028, supplied=None))
    values = _by_field(read_model)
    assert all(a.provenance == "legacy_unknown" for a in values.values())
    assert _codes(read_model.diagnostics) == ["legacy_assumption_provenance"]
    diagnostic = read_model.diagnostics[0]
    assert diagnostic.severity == "warning"
    assert diagnostic.section == "assumptions"
    assert "2027, 2028" in diagnostic.message


def test_one_legacy_row_makes_the_whole_series_legacy_unknown():
    read_model = _build(_row(2027, supplied=["revenue_growth_pct"]), _row(2028, supplied=None))
    assert _by_field(read_model)["revenue_growth_pct"].provenance == "legacy_unknown"
    assert _codes(read_model.diagnostics) == ["legacy_assumption_provenance"]


def test_empty_tracked_list_is_not_legacy():
    read_model = _build(_row(2027, supplied=[]))
    assert _codes(read_model.diagnostics) == []
    assert all(a.provenance != "legacy_unknown" for a in _by_field(read_model).values())


# ---------------------------------------------------------------------------
# Legacy `investments` — the conditional dead field
# ---------------------------------------------------------------------------

def test_valued_investments_without_splits_raises_a_diagnostic_not_a_driver():
    read_model = _build(_row(2027, supplied=[], investments=Decimal("12000")))
    assert "legacy_investments_without_split" in _codes(read_model.diagnostics)
    emitted = {a.field for section in read_model.sections for a in section.assumptions}
    assert "investments" not in emitted


def test_investments_shadowed_by_splits_is_silent():
    read_model = _build(_row(2027, supplied=[], investments=Decimal("12000"),
                             tangible_investments=Decimal("12000")))
    assert "legacy_investments_without_split" not in _codes(read_model.diagnostics)


def test_zero_investments_is_silent():
    read_model = _build(_row(2027, supplied=[], investments=Decimal("0")))
    assert "legacy_investments_without_split" not in _codes(read_model.diagnostics)


def test_negative_investments_without_split_also_raises_a_diagnostic():
    # `_get_split_investments` rejects the total with `if total:`: any non-zero
    # value stops generation, whatever its sign. A negative legacy total must
    # therefore activate the diagnostic exactly like a positive one.
    read_model = _build(_row(2027, supplied=[], investments=Decimal("-12000")))
    assert "legacy_investments_without_split" in _codes(read_model.diagnostics)
    emitted = {a.field for section in read_model.sections for a in section.assumptions}
    assert "investments" not in emitted


def test_pregoresso_on_a_later_row_is_declared():
    read_model = _build(
        _row(2027, supplied=[]),
        _row(2028, supplied=[], pregresso={"debiti_fornitori": {"opening": "80", "amounts": ["80"]}}),
    )
    assert "pregresso_beyond_first_year" in _codes(read_model.diagnostics)
    plan = _by_field(read_model)["pregresso"].pregresso
    assert plan.debiti_fornitori.opening == Decimal("80")  # still preserved, never dropped


# ---------------------------------------------------------------------------
# Nested structures
# ---------------------------------------------------------------------------

def test_financing_loans_span_years_and_stay_typed_tables():
    read_model = _build(
        _row(2027, supplied=["financing_loans"], financing_loans=[
            {"name": "Mutuo A", "amount": "100000.00", "duration_years": 5, "interest_rate": "3.25"},
        ]),
        _row(2028, supplied=[], financing_loans=[
            {"name": "Mutuo B", "amount": "50000.00", "opening_residual": "45000.00", "duration_years": 3},
        ]),
    )
    loans = _by_field(read_model)["financing_loans"].financing_loans
    assert [loan.name for loan in loans] == ["Mutuo A", "Mutuo B"]
    assert loans[0].amount == Decimal("100000.00") and loans[0].interest_rate == Decimal("3.25")
    assert loans[1].opening_residual == Decimal("45000.00")
    assert _by_field(read_model)["financing_loans"].values == [None, None]


def test_pregoresso_tax_plan_keeps_saldo_rateizzato_and_acconto():
    read_model = _build(_row(2027, supplied=["pregresso"], pregresso={
        "crediti_commerciali": {"opening": "100", "amounts": ["50", "50"], "writeoff": ["5", "5"]},
        "debiti_tributari": {"opening": "120", "amounts": ["50", "40"], "saldo": "30",
                             "rateizzato": "90", "acconto_pct": "100"},
    }))
    plan = _by_field(read_model)["pregresso"].pregresso
    assert plan.crediti_commerciali.writeoff == [Decimal("5"), Decimal("5")]
    assert plan.debiti_tributari.saldo == Decimal("30")
    assert plan.debiti_tributari.rateizzato == Decimal("90")
    assert plan.debiti_tributari.acconto_pct == Decimal("100")


def test_temporary_differences_stay_a_table():
    read_model = _build(_row(2027, supplied=["tax_temporary_differences"], tax_temporary_differences=[
        {"name": "Fondo rischi", "kind": "deductible", "maturity": "short",
         "opening_amount": "200", "additions": "50", "reversals": "25", "tax_rate": "24"},
    ]))
    lines = _by_field(read_model)["tax_temporary_differences"].temporary_differences
    assert lines[0].kind == "deductible" and lines[0].opening_amount == Decimal("200")


def test_sp_indexing_and_overrides_are_flattened_deterministically():
    read_model = _build(
        _row(2027, supplied=[], sp_indexing={"sp16g": "ricavi"}, sp_overrides={"sp09_disponibilita_liquide": "50.00"}),
        _row(2028, supplied=[], sp_indexing={"sp16g": "acquisti"}, sp_overrides={"sp09_disponibilita_liquide": "60.00"}),
    )
    values = _by_field(read_model)
    assert [(e.field, e.driver) for e in values["sp_indexing"].sp_indexing] == [("sp16g", "ricavi"), ("sp16g", "acquisti")]
    assert [e.value for e in values["sp_overrides"].sp_overrides] == [Decimal("50.00"), Decimal("60.00")]


def test_invalid_nested_structure_degrades_to_a_diagnostic_not_a_crash():
    read_model = _build(_row(2027, supplied=["financing_loans"], financing_loans=[
        {"name": "Nope", "amount": "0", "duration_years": 0},
    ]))
    assert "nested_assumption_invalid" in _codes(read_model.diagnostics)
    assert _by_field(read_model)["financing_loans"].financing_loans is None


# ---------------------------------------------------------------------------
# Horizon, nulls, negatives
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("count", [1, 3, 5])
def test_values_align_with_forecast_years_for_any_horizon(count):
    rows = [_row(2027 + i, supplied=(["revenue_growth_pct"] if i == 0 else []),
                 revenue_growth_pct=Decimal("1")) for i in range(count)]
    read_model = _build(*rows)
    values = _by_field(read_model)["revenue_growth_pct"].values
    assert len(values) == count
    assert values[0] == Decimal("1")


def test_null_and_negative_values_survive_untouched():
    read_model = _build(_row(2027, supplied=["revenue_growth_pct", "overdraft_limit"],
                             revenue_growth_pct=Decimal("-3.25"), overdraft_limit=None,
                             asset_disposal_nbv=Decimal("-10")))
    values = _by_field(read_model)
    assert values["revenue_growth_pct"].values == [Decimal("-3.25")]
    assert values["overdraft_limit"].values == [None]
    assert values["asset_disposal_nbv"].values == [Decimal("-10")]


def test_emitted_scalars_are_decimal_or_bool_never_float():
    read_model = _build(_row(2027, supplied=[], revenue_growth_pct=2.5,
                             cash_sweep_enabled=True, overdraft_allowed=False))
    for assumption in _by_field(read_model).values():
        for value in assumption.values:
            assert value is None or isinstance(value, (Decimal, bool)), (assumption.field, value)
    # boolean fields stay booleans for the contract's boolean guard
    assert _by_field(read_model)["cash_sweep_enabled"].values == [True]
    assert _by_field(read_model)["overdraft_allowed"].values == [False]


def test_rows_are_ordered_by_forecast_year_whatever_the_input_order():
    read_model = _build(
        _row(2029, supplied=[], revenue_growth_pct=Decimal("3")),
        _row(2027, supplied=[], revenue_growth_pct=Decimal("1")),
        _row(2028, supplied=[], revenue_growth_pct=Decimal("2")),
    )
    assert _by_field(read_model)["revenue_growth_pct"].values == [Decimal("1"), Decimal("2"), Decimal("3")]


def test_whole_read_model_fits_the_final_report_contract_types():
    # The section list alone must survive a dump/validate round trip under the
    # strict contract (field-in-section, scalar grammar, nested ownership).
    read_model = _build(_row(2027, supplied=["pregresso"],
                             pregresso={"altri_debiti": {"opening": "10", "amounts": ["10"]}},
                             revenue_growth_pct=Decimal("5"), tax_rate=Decimal("27.9")))
    payload = [section.model_dump(mode="json") for section in read_model.sections]
    rebuilt = [AssumptionSection.model_validate(item) for item in payload]
    assert [section.key for section in rebuilt] == [s["key"] for s in ASSUMPTION_SECTION_CATALOG]
