"""Anteprima del previsionale: stesse righe del bulk, stesso motore, nessuna scrittura."""
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy import Numeric
from sqlalchemy.orm import Session

from app.services.assumptions_service import build_assumption_row
from calculations.forecast_engine import ForecastEngine, load_forecast_source
from database import models

# Colonne Numeric di BudgetAssumptions: sul percorso persistito SQLAlchemy le
# consegna al motore gia' Decimal (INSERT poi SELECT fresca); la riga
# dell'anteprima non tocca mai il DB, quindi resta con qualunque tipo Python
# le sia arrivato — il default float di `build_assumption_row`, o un int/float
# dal corpo della richiesta — e il motore lavora in Decimal: `float / Decimal`
# alza TypeError.
_NUMERIC_FIELDS = tuple(
    c.name for c in models.BudgetAssumptions.__table__.columns if isinstance(c.type, Numeric)
)


def _as_decimal_row(row: models.BudgetAssumptions) -> models.BudgetAssumptions:
    """Converte in Decimal i campi Numeric della riga transitoria, sul posto."""
    for field in _NUMERIC_FIELDS:
        value = getattr(row, field, None)
        if value is not None and not isinstance(value, Decimal):
            setattr(row, field, Decimal(str(value)))
    return row


def _validate(assumptions_list: List[Dict[str, Any]], base_year: int) -> None:
    if not assumptions_list:
        raise ValueError("At least one assumption record is required")
    years = []
    for a in assumptions_list:
        if "forecast_year" not in a:
            raise ValueError("Each assumption must have a forecast_year")
        if a["forecast_year"] <= base_year:
            raise ValueError(f"Forecast year {a['forecast_year']} must be greater than base year {base_year}")
        years.append(a["forecast_year"])
    if len(years) != len(set(years)):
        raise ValueError("Duplicate forecast years found in assumptions list")


def _floats(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in d.items()}


def preview_forecast(db: Session, scenario_id: int, assumptions_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    source = load_forecast_source(db, scenario_id)          # ValueError -> 400 nella route
    _validate(assumptions_list, source.scenario.base_year)
    rows = sorted(
        (_as_decimal_row(build_assumption_row(scenario_id, a)) for a in assumptions_list),
        key=lambda r: r.forecast_year,
    )
    # Le righe sono transitorie: MAI db.add. Il motore le legge con getattr.
    computation = ForecastEngine(db).compute_forecast(source, rows, stop_on_error=False)
    return {
        "scenario_id": scenario_id,
        "base_year": source.scenario.base_year,
        "forecast_years": [
            {"year": y.year, "income_statement": _floats(y.income_statement),
             "balance_sheet": _floats(y.balance_sheet), "details": _floats(y.details)}
            for y in computation.years
        ],
        "error": None if computation.error is None
                 else {"year": computation.error.year, "message": computation.error.message},
    }
