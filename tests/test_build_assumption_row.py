from decimal import Decimal

from backend.app.services.assumptions_service import build_assumption_row
from database import models


def test_row_is_transient_and_carries_every_column_default():
    row = build_assumption_row(7, {"forecast_year": 2027, "revenue_growth_pct": 5})
    assert isinstance(row, models.BudgetAssumptions)
    assert row.scenario_id == 7 and row.forecast_year == 2027
    assert row.revenue_growth_pct == 5
    # default del bulk, non dello schema: 27.9, 40, 20
    assert row.tax_rate == 27.9
    assert row.fixed_materials_percentage == 40.0
    assert row.depreciation_rate == 20.0
    assert row.financing_amount == 0.0            # null -> 0
    assert row.cash_sweep_enabled is False
    assert row.ce05_override is None
    # nessuna colonna e' rimasta None fra quelle NOT NULL del modello
    for col in models.BudgetAssumptions.__table__.columns:
        if not col.nullable and col.name not in ("id", "created_at", "updated_at"):
            assert getattr(row, col.name) is not None, col.name


def test_json_fields_are_encoded_like_the_bulk():
    row = build_assumption_row(7, {
        "forecast_year": 2027,
        "financing_loans": [{"amount": Decimal("1000"), "duration_years": 5}],
        "sp_overrides": {"sp09_disponibilita_liquide": Decimal("12.5")},
    })
    assert row.financing_loans == [{"amount": 1000.0, "duration_years": 5}]
    assert row.sp_overrides == {"sp09_disponibilita_liquide": 12.5}
