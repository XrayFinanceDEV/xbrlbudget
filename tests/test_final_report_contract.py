"""Contract boundary tests for the JSON shared by API, React and Typst."""
import copy
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

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
    changed = copy.deepcopy(report.model_dump(mode="python"))
    changed["forecast"]["years"][0]["income_statement"][0]["value"] = Decimal("1261.5001")
    assert model_hash(changed) != original_hash
    assert source_hash(changed) != source_hash(report)
    assert '"5.125"' in canonical_json(report)
    assert '"120.00"' in report.model_dump_json()


def test_assumption_catalog_is_exactly_the_current_wizard_without_dead_fields():
    catalog_keys = [item["key"] for item in ASSUMPTION_SECTION_CATALOG]
    assert catalog_keys == ["scenario", "fatturato", "costi", "altre-voci-ce", "circolante", "pregresso-nuovo", "imposte"]
    fields = [field for item in ASSUMPTION_SECTION_CATALOG for field in item["fields"]]
    assert len(fields) == len(set(fields))

    wizard = (ROOT / "frontend" / "lib" / "budget-wizard-steps.ts").read_text(encoding="utf-8")
    step_body = wizard.split("export const STEP_FIELDS:", 1)[1].split("/**", 1)[0]
    wizard_fields = re.findall(r'"([a-z0-9_]+)"', step_body)
    dead_body = wizard.split("export const DEAD_FIELDS", 1)[1].split("] as const", 1)[0]
    dead_fields = set(re.findall(r'"([a-z0-9_]+)"', dead_body))
    assert set(fields) == set(wizard_fields)
    assert not dead_fields.intersection(fields)
