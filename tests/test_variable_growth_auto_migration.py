from sqlalchemy import create_engine, inspect, text

from database.db import ensure_variable_growth_columns
from backend.app.schemas.budget import BudgetAssumptionsCreate
from backend.app.services.assumptions_service import build_assumption_row


def test_existing_budget_assumptions_gain_nullable_auto_markers(tmp_path):
    bind = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with bind.begin() as connection:
        connection.execute(text("CREATE TABLE budget_assumptions (id INTEGER PRIMARY KEY, revenue_growth_pct NUMERIC)"))
        connection.execute(text("INSERT INTO budget_assumptions (id, revenue_growth_pct) VALUES (1, 5)"))

    ensure_variable_growth_columns(bind)
    ensure_variable_growth_columns(bind)

    columns = {column["name"] for column in inspect(bind).get_columns("budget_assumptions")}
    assert {"variable_materials_growth_auto", "variable_services_growth_auto"} <= columns
    with bind.connect() as connection:
        row = connection.execute(text(
            "SELECT revenue_growth_pct, variable_materials_growth_auto, variable_services_growth_auto "
            "FROM budget_assumptions WHERE id = 1"
        )).one()
    assert row == (5, None, None)
    bind.dispose()


def test_explicit_zero_growth_keeps_its_manual_marker():
    data = BudgetAssumptionsCreate(
        scenario_id=1, forecast_year=2027, revenue_growth_pct=5,
        variable_services_growth_pct=0, variable_services_growth_auto=False,
        variable_materials_growth_pct=5, variable_materials_growth_auto=True,
    ).model_dump()
    row = build_assumption_row(1, data)
    assert row.variable_services_growth_pct == 0
    assert row.variable_services_growth_auto is False
    assert row.variable_materials_growth_auto is True
