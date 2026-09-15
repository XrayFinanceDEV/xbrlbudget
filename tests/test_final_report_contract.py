"""Contract boundary tests for the JSON shared by API, React and Typst."""
import copy
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.encoders import jsonable_encoder

from backend.app.schemas.final_report import (
    ASSUMPTION_SECTION_CATALOG,
    FinalReportModel,
    canonical_json,
    model_hash,
    source_hash,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "final_report"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["infrannuale.json", "bilancio.json", "startup.json"])
def test_final_report_fixtures_validate(name):
    report = FinalReportModel.model_validate(load_fixture(name))
    assert report.schema_version == 1
    assert report.model_dump(mode="json")["schema_version"] == 1
    assert report.source_hash == report.calculate_source_hash()
    assert report.model_hash == report.calculate_model_hash()
    if name == "infrannuale.json":
        assert report.infrannual_closing.period_end.isoformat() == "2026-09-30"


def test_workflow_specific_closing_is_omitted_and_float_money_is_rejected():
    annual = load_fixture("bilancio.json")
    assert "infrannual_closing" not in annual
    FinalReportModel.model_validate(annual)
    annual["infrannual_closing"] = None
    with pytest.raises(ValueError, match="omitted"):
        FinalReportModel.model_validate(annual)

    infrannual = load_fixture("infrannuale.json")
    infrannual["forecast"]["years"][0]["income_statement"][0]["value"] = 1.25
    with pytest.raises(ValueError, match="exact JSON strings"):
        FinalReportModel.model_validate(infrannual)


def test_annual_wire_serialization_omits_closing_and_round_trips_through_fastapi():
    for name in ("bilancio.json", "startup.json"):
        report = FinalReportModel.model_validate(load_fixture(name))
        assert "infrannual_closing" not in report.model_dump(mode="json")
        assert "infrannual_closing" not in json.loads(report.model_dump_json())
        encoded = jsonable_encoder(report)
        assert "infrannual_closing" not in encoded
        round_trip = FinalReportModel.model_validate(encoded)
        assert round_trip.model_dump(mode="json") == encoded

    infrannual = FinalReportModel.model_validate(load_fixture("infrannuale.json"))
    assert "infrannual_closing" in jsonable_encoder(infrannual)


def test_canonical_hash_ignores_key_order_and_volatile_timestamps():
    report = load_fixture("infrannuale.json")
    reordered = json.loads(json.dumps(report, sort_keys=True))
    reordered["generated_at"] = "2030-01-01T00:00:00Z"
    reordered["narrative"][0]["updated_at"] = "2030-01-01T00:00:00Z"
    assert canonical_json(report) == canonical_json(reordered)
    assert model_hash(report) == model_hash(reordered)
    assert source_hash(report) == source_hash(reordered)


def test_canonical_hash_changes_for_material_value_and_keeps_decimal_precision():
    report = FinalReportModel.model_validate(load_fixture("infrannuale.json"))
    original_hash = model_hash(report)
    changed = report.model_copy(deep=True)
    changed.forecast.years[0].income_statement[0].value = Decimal("1261.5001")
    assert model_hash(changed) != original_hash
    assert source_hash(changed) != source_hash(report)
    assert '"5.125"' in canonical_json(report)
    assert '"120.00"' in report.model_dump_json()


def test_canonical_decimal_normalizes_only_for_hashing_and_rejects_non_finite_values():
    assert canonical_json({"amount": Decimal("1.00")}) == canonical_json({"amount": Decimal("1.0")})
    assert canonical_json({"amount": "1.00"}) != canonical_json({"amount": "1.0"})
    assert canonical_json({"identifier": "001"}) != canonical_json({"identifier": "1"})
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json({"amount": Decimal("NaN")})


def test_legacy_unknown_is_an_explicit_read_model_value_not_a_writer_inference():
    report = FinalReportModel.model_validate(load_fixture("infrannuale.json"))
    # index 3 = "circolante" (Task 8 giro di rilievi: scenario, fatturato,
    # costi, circolante, patrimoniale-pregresso, patrimoniale-piano, imposte
    # — prima "circolante" era in quarta posizione con "altre-voci-ce").
    provenance = report.assumption_sections[3].assumptions[0].provenance
    assert provenance == "legacy_unknown"


def test_hashes_are_verified_over_validated_default_materialized_data_without_circularity():
    report = load_fixture("infrannuale.json")
    equivalent = copy.deepcopy(report)
    equivalent["adjustments"]["entries"][0]["edit_delta"] = "120.0"
    equivalent_model = FinalReportModel.model_validate(equivalent, context={"skip_hash_validation": True})
    assert equivalent_model.calculate_model_hash() == report["model_hash"]

    explicit_defaults = copy.deepcopy(report)
    explicit_defaults["practice"]["budget_scenario"]["period_months"] = None
    explicit_defaults["source_revisions"][0]["available"] = True
    materialized = FinalReportModel.model_validate(explicit_defaults, context={"skip_hash_validation": True})
    assert materialized.calculate_source_hash() == report["source_hash"]
    assert materialized.calculate_model_hash() == report["model_hash"]

    changed = copy.deepcopy(report)
    changed["narrative"][0]["text"] = "Sintesi aggiornata"
    changed_model = FinalReportModel.model_validate(changed, context={"skip_hash_validation": True})
    assert changed_model.calculate_source_hash() == report["source_hash"]
    assert changed_model.calculate_model_hash() != report["model_hash"]

    with pytest.raises(ValueError, match="model_hash"):
        FinalReportModel.model_validate(changed)
    source_changed = copy.deepcopy(report)
    source_changed["forecast"]["years"][0]["income_statement"][0]["value"] = "1261.5001"
    with pytest.raises(ValueError, match="source_hash"):
        FinalReportModel.model_validate(source_changed)
    with pytest.raises(ValueError, match="model_hash"):
        FinalReportModel.model_validate({**report, "model_hash": "0" * 64})


@pytest.mark.parametrize("bad_decimal", [1.5, "1e3", "+1", "01.0", "NaN"])
def test_decimal_wire_grammar_rejects_float_and_non_plain_forms(bad_decimal):
    report = load_fixture("infrannuale.json")
    report["forecast"]["years"][0]["income_statement"][0]["value"] = bad_decimal
    with pytest.raises(ValueError, match="financial decimals"):
        FinalReportModel.model_validate(report)


def test_decimal_python_inputs_are_exact_but_json_wire_inputs_are_plain_strings():
    report = load_fixture("infrannuale.json")
    report["forecast"]["years"][0]["income_statement"][0]["value"] = Decimal("1261.500")
    assert FinalReportModel.model_validate(report).forecast.years[0].income_statement[0].value == Decimal("1261.500")

    wire = load_fixture("infrannuale.json")
    wire["forecast"]["years"][0]["income_statement"][0]["value"] = 1261
    with pytest.raises(ValueError, match="financial decimals"):
        FinalReportModel.model_validate_json(json.dumps(wire))


def test_v1_material_invariants_and_exact_alert_keys_are_enforced():
    report = load_fixture("infrannuale.json")
    report["chart_series"][0]["categories"] = [2028, 2029, 2030]
    with pytest.raises(ValueError, match="chart categories"):
        FinalReportModel.model_validate(report)

    report = load_fixture("bilancio.json")
    report["source_revisions"][0]["available"] = False
    with pytest.raises(ValueError, match="ready reports"):
        FinalReportModel.model_validate(report)

    report = load_fixture("infrannuale.json")
    report["infrannual_closing"]["extra_accounting_alerts"] = {"banche": True}
    with pytest.raises(ValueError):
        FinalReportModel.model_validate(report)


def test_forecast_years_are_unique_and_ready_reports_have_renderable_statements():
    report = load_fixture("infrannuale.json")
    report["practice"]["periods"]["forecast_years"] = [2027, 2027, 2029]
    with pytest.raises(ValueError, match="unique"):
        FinalReportModel.model_validate(report)

    report = load_fixture("bilancio.json")
    report["forecast"]["years"][0]["cashflow"] = []
    with pytest.raises(ValueError, match="non-empty income_statement"):
        FinalReportModel.model_validate(report)


@pytest.mark.parametrize("path", [
    ("company", "id"),
    ("practice", "budget_scenario", "id"),
    ("practice", "budget_scenario", "base_year"),
    ("practice", "periods", "forecast_years", 0),
    ("forecast", "years", 0, "year"),
    ("chart_series", 0, "categories", 0),
])
@pytest.mark.parametrize("invalid", ["2027", True])
def test_integer_contract_fields_do_not_coerce_wire_strings_or_booleans(path, invalid):
    report = load_fixture("infrannuale.json")
    target = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = invalid
    with pytest.raises(ValueError):
        FinalReportModel.model_validate(report)


def test_iso_dates_and_defaulted_nullable_fields_have_explicit_wire_parity():
    report = load_fixture("infrannuale.json")
    report["generated_at"] = "2026-02-30T10:00:00Z"
    with pytest.raises(ValueError, match="ISO datetime"):
        FinalReportModel.model_validate(report)

    report = load_fixture("infrannuale.json")
    report["infrannual_closing"]["period_end"] = "2026-09-31"
    with pytest.raises(ValueError, match="ISO calendar"):
        FinalReportModel.model_validate(report)

    report = load_fixture("bilancio.json")
    report["company"].pop("tax_id")
    report["source_revisions"][0].pop("available")
    report["readiness"].pop("reasons")
    parsed = FinalReportModel.model_validate(report, context={"skip_hash_validation": True})
    assert parsed.company.tax_id is None and parsed.source_revisions[0].available is True and parsed.readiness.reasons == []


def test_assumptions_must_belong_to_their_catalog_section():
    report = load_fixture("infrannuale.json")
    report["assumption_sections"][1]["assumptions"][0]["field"] = "dso_days"
    with pytest.raises(ValueError, match="not valid for fatturato"):
        FinalReportModel.model_validate(report)


def test_fixture_represents_each_catalogued_nested_assumption_structure():
    report = FinalReportModel.model_validate(load_fixture("infrannuale.json"))
    values = [assumption for section in report.assumption_sections for assumption in section.assumptions]
    assert next(value for value in values if value.field == "ce_overrides").ce_overrides[0].field == "ce02_override"
    assert next(value for value in values if value.field == "sp_indexing").sp_indexing[0].driver == "ricavi"
    assert next(value for value in values if value.field == "sp_overrides").sp_overrides[0].value == Decimal("50.00")


def test_fixture_has_non_vacuous_financing_tax_and_boolean_assumptions():
    report = FinalReportModel.model_validate(load_fixture("infrannuale.json"))
    values = {assumption.field: assumption for section in report.assumption_sections for assumption in section.assumptions}
    assert values["financing_loans"].financing_loans[0].amount == Decimal("100000.00")
    assert values["pregresso"].pregresso.debiti_tributari.rateizzato == Decimal("90")
    assert values["tax_temporary_differences"].temporary_differences[0].kind == "deductible"
    for field in ("cash_sweep_enabled", "overdraft_allowed", "previdenza_scales_with_personnel", "tfr_accrual_suspended"):
        assert all(isinstance(value, bool) for value in values[field].values)


@pytest.mark.parametrize("invalid", [{"unexpected": "object"}, ["nested"], "1"])
def test_assumption_scalars_reject_mixed_object_values(invalid):
    report = load_fixture("infrannuale.json")
    report["assumption_sections"][5]["assumptions"][1]["values"][0] = invalid
    with pytest.raises(ValueError):
        FinalReportModel.model_validate(report)


def test_assumption_catalog_is_exactly_the_current_wizard_without_dead_fields():
    catalog_keys = [item["key"] for item in ASSUMPTION_SECTION_CATALOG]
    assert catalog_keys == ["scenario", "fatturato", "costi", "circolante", "patrimoniale-pregresso", "patrimoniale-piano", "imposte"]
    fields = [field for item in ASSUMPTION_SECTION_CATALOG for field in item["fields"]]
    nested_fields = [field for item in ASSUMPTION_SECTION_CATALOG for field in item.get("nested_fields", [])]
    assert len(fields) == len(set(fields))
    assert set(nested_fields) == {"ce_overrides", "sp_indexing", "sp_overrides", "pregresso", "other_lenders"}
    # These are structured component inputs, deliberately represented as nested
    # tables/envelopes instead of pretending they are scalar wizard STEP_FIELDS.
    assert "investments" not in fields + nested_fields

    wizard = (ROOT / "frontend" / "lib" / "budget-wizard-steps.ts").read_text(encoding="utf-8")
    step_body = wizard.split("export const STEP_FIELDS:", 1)[1].split("/**", 1)[0]
    wizard_sections = {}
    for match in re.finditer(r'(?P<key>"[^"]+"|[a-z_]+):\s*\[(?P<fields>.*?)\]', step_body, re.DOTALL):
        key = match.group("key").strip('"')
        wizard_sections[key] = re.findall(r'"([a-z0-9_]+)"', match.group("fields"))
    wizard_fields = [field for section in wizard_sections.values() for field in section]
    dead_body = wizard.split("export const DEAD_FIELDS", 1)[1].split("] as const", 1)[0]
    dead_fields = set(re.findall(r'"([a-z0-9_]+)"', dead_body))
    assert set(catalog_keys) == set(wizard_sections)
    assert len(wizard_fields) == len(set(wizard_fields)), "the current wizard itself has duplicate fields"
    assert [item["fields"] for item in ASSUMPTION_SECTION_CATALOG] == [wizard_sections[key] for key in catalog_keys]
    assert not dead_fields.intersection(fields)
