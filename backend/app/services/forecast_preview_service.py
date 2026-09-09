"""Anteprima del previsionale: stesse righe del bulk, stesso motore, nessuna scrittura."""
from decimal import Decimal
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.services.assumptions_service import build_assumption_row, validate_assumptions_list
from calculations.forecast_engine import ForecastEngine, load_forecast_source
from database import models


def _floats(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in d.items()}


def preview_forecast(db: Session, scenario_id: int, assumptions_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Lettura minima per validare il corpo PRIMA di `load_forecast_source`: un
    # corpo malformato e' un errore del chiamante, indipendente da cosa dice il
    # database sull'anno base, e deve dare lo stesso messaggio del bulk sullo
    # stesso corpo (validate_assumptions_list e' condivisa con quel percorso).
    scenario = db.query(models.BudgetScenario).filter(models.BudgetScenario.id == scenario_id).first()
    if not scenario:
        raise ValueError(f"Budget scenario {scenario_id} not found")
    # Il wizard e' budget-only: l'infrannuale ha il proprio motore
    # (IntraYearEngine) e le proprie tab (Confronto, Proiezione). Farlo
    # calcolare a questo endpoint con ForecastEngine produrrebbe due bilanci
    # diversi della stessa azienda dallo stesso corpo — l'esatto contrario
    # dell'invariante "un solo motore di proiezione" (CLAUDE.md).
    if scenario.scenario_type == "infrannuale":
        raise ValueError(
            "L'anteprima del previsionale copre solo scenari budget: "
            "l'infrannuale ha il proprio percorso (Confronto, Proiezione)."
        )
    # validate_assumptions_list restituisce gli anni GIA' COERCIATI a int (N1):
    # build_assumption_row li riceve espliciti, cosi' un forecast_year stringa
    # nel corpo non arriva grezzo al sorted() qui sotto ne' al motore.
    coerced_years = validate_assumptions_list(assumptions_list, scenario.base_year)

    source = load_forecast_source(db, scenario_id)          # ValueError -> 400 nella route
    rows = sorted(
        (build_assumption_row(scenario_id, a, forecast_year=y)
         for a, y in zip(assumptions_list, coerced_years)),
        key=lambda r: r.forecast_year,
    )
    # Le righe sono transitorie: MAI db.add. Il motore le legge con getattr.
    # build_assumption_row le consegna gia' normalizzate (null sul default di
    # colonna, quantizzate, Decimal): stessi numeri del percorso persistito,
    # senza toccare il DB.
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
