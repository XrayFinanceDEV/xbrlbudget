from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from backend.app.schemas.budget import BudgetAssumptionsCreate, PregressoInput
from backend.app.services.assumptions_service import build_assumption_row


def test_schema_accepts_a_plan_and_rejects_negatives():
    p = PregressoInput(crediti_commerciali={"opening": 1000, "amounts": [800, 200], "writeoff": [0, 0]},
                       debiti_tributari={"opening": 96, "saldo": 61, "rateizzato": 35, "amounts": [12, 12, 11]})
    assert p.debiti_tributari.acconto_pct == D("100")
    with pytest.raises(ValidationError):
        PregressoInput(debiti_fornitori={"opening": -1, "amounts": []})


def test_build_assumption_row_carries_pregresso_as_json():
    row = build_assumption_row(1, {"forecast_year": 2027, "pregresso": {"altri_debiti": {"opening": D("10"), "amounts": [D("10")]}}})
    assert row.pregresso == {"altri_debiti": {"opening": 10.0, "amounts": [10.0]}}
    assert build_assumption_row(1, {"forecast_year": 2027}).pregresso is None
