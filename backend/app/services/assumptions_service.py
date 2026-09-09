"""
Assumptions Service - Bulk operations for budget assumptions

Handles bulk insert/update of forecast assumptions with automatic forecast generation.
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from decimal import Decimal
from sqlalchemy import Numeric
from datetime import datetime
from fastapi.encoders import jsonable_encoder
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from database import models
from calculations.forecast_engine import ForecastEngine, prune_out_of_plan_forecast_years


_NUMERIC_COLUMNS = {
    c.name: c for c in models.BudgetAssumptions.__table__.columns if isinstance(c.type, Numeric)
}
_NUMERIC_FIELDS = tuple(_NUMERIC_COLUMNS)
_COLUMN_SCALE = {name: col.type.scale for name, col in _NUMERIC_COLUMNS.items()}
_COLUMN_DEFAULT = {
    name: col.default.arg for name, col in _NUMERIC_COLUMNS.items() if col.default is not None
}


def _normalize_numeric_fields(row: models.BudgetAssumptions) -> models.BudgetAssumptions:
    """Le tre cose che il giro DB fa sul percorso persistito (INSERT poi SELECT
    fresca), replicate qui perche' una riga transitoria (l'anteprima) non tocca
    mai il DB:

    1. coalescenza dei null sul DEFAULT DI COLONNA -- non un default inventato:
       verificato empiricamente che SQLAlchemy applica il default Python-side
       anche quando l'attributo e' stato assegnato esplicitamente a None (non
       solo quando resta NO_VALUE). E' cosi' che un `tax_rate: null` dal client
       fa girare il 24 dello schema, non il 27,9 che ogni chiamante reale manda
       (CLAUDE.md, "Tax rate"): la coalescenza deve RIPRODURRE questo
       comportamento, non correggerlo.
    2. quantizzazione alla scala della colonna, con la stessa formattazione del
       bind SQLite -- non `.quantize()`, che arrotonda diversamente: su
       1234.565 la formattazione da' 1234.57, `.quantize()` da' 1234.56.
    3. tipo Decimal (il motore lavora in Decimal, mai float).
    """
    for field in _NUMERIC_FIELDS:
        value = getattr(row, field, None)
        if value is None:
            default = _COLUMN_DEFAULT.get(field)
            if default is None:
                continue  # colonna nullable: None resta un valore legittimo
            value = default
        scale = _COLUMN_SCALE[field]
        setattr(row, field, Decimal(f"%.{scale}f" % float(value)))
    return row


def validate_assumptions_list(assumptions_list: List[Dict[str, Any]], base_year: int) -> List[int]:
    """Stesso controllo per bulk e anteprima, chiamato PRIMA di qualunque lettura
    che dipenda dall'anno base: un corpo malformato e' un errore del chiamante e
    non dipende da cosa dice il database sull'anno base, quindi deve dare lo
    stesso messaggio ovunque arrivi.

    Restituisce gli anni GIA' COERCIATI a int, nello stesso ordine di
    assumptions_list. E' l'UNICO punto che fa la conversione: chi costruisce le
    righe (build_assumption_row) o la lista degli anni del piano deve usare
    questo valore, mai `assumption["forecast_year"]` grezzo. Coercire solo la
    variabile locale del confronto qui sotto non basta -- un `forecast_year`
    stringa che supera questa validazione arriverebbe comunque grezzo al motore
    o a un `sorted()` a valle, con lo stesso TypeError che la validazione doveva
    prevenire (N1: sul percorso bulk, con le righe gia' committate).
    """
    if not assumptions_list:
        raise ValueError("At least one assumption record is required")
    years: List[int] = []
    for assumption in assumptions_list:
        if "forecast_year" not in assumption:
            raise ValueError("Each assumption must have a forecast_year")
        raw_year = assumption["forecast_year"]
        try:
            forecast_year = int(raw_year)
        except (TypeError, ValueError):
            raise ValueError(f"forecast_year non valido: {raw_year!r}")
        if forecast_year <= base_year:
            raise ValueError(
                f"Forecast year {forecast_year} must be greater than base year {base_year}"
            )
        years.append(forecast_year)
    if len(years) != len(set(years)):
        raise ValueError("Duplicate forecast years found in assumptions list")
    return years


def build_assumption_row(
    scenario_id: int, data: Dict[str, Any], forecast_year: int = None
) -> models.BudgetAssumptions:
    """Una riga di ipotesi dal dict del client, con i default del bulk.

    L'istanza è TRANSITORIA: chi la vuole persistere la aggiunge alla sessione
    (bulk); l'anteprima la passa al motore e basta. Bulk e anteprima passano
    di qui, così un campo aggiunto a uno non può mancare all'altro.
    """
    row = models.BudgetAssumptions(
        scenario_id=scenario_id,
        # `forecast_year`, se dato, e' il valore GIA' COERCIATO da
        # validate_assumptions_list (bulk e anteprima lo passano sempre): una
        # stringa numerica dal client non deve mai finire grezza sulla colonna.
        # Il fallback sul dict resta solo per un uso diretto/di test.
        forecast_year=forecast_year if forecast_year is not None else data.get("forecast_year"),
        revenue_growth_pct=data.get("revenue_growth_pct", 0.0),
        other_revenue_growth_pct=data.get("other_revenue_growth_pct", 0.0),
        variable_materials_growth_pct=data.get("variable_materials_growth_pct", 0.0),
        fixed_materials_growth_pct=data.get("fixed_materials_growth_pct", 0.0),
        variable_services_growth_pct=data.get("variable_services_growth_pct", 0.0),
        fixed_services_growth_pct=data.get("fixed_services_growth_pct", 0.0),
        rent_growth_pct=data.get("rent_growth_pct", 0.0),
        personnel_growth_pct=data.get("personnel_growth_pct", 0.0),
        other_costs_growth_pct=data.get("other_costs_growth_pct", 0.0),
        investments=data.get("investments", 0.0),
        intangible_investments=data.get("intangible_investments", 0.0),
        tangible_investments=data.get("tangible_investments", 0.0),
        asset_disposal_nbv=data.get("asset_disposal_nbv", None),
        asset_disposal_proceeds=data.get("asset_disposal_proceeds", None),
        receivables_short_growth_pct=data.get("receivables_short_growth_pct", 0.0),
        receivables_long_growth_pct=data.get("receivables_long_growth_pct", 0.0),
        payables_short_growth_pct=data.get("payables_short_growth_pct", 0.0),
        dso_days=data.get("dso_days", None),
        dio_days=data.get("dio_days", None),
        dpo_days=data.get("dpo_days", None),
        existing_debt_repayment_years=data.get("existing_debt_repayment_years", None),
        altri_finanz_repayment_years=data.get("altri_finanz_repayment_years", None),
        cash_sweep_enabled=data.get("cash_sweep_enabled", False) or False,
        cash_sweep_min_cash=data.get("cash_sweep_min_cash", None),
        tfr_accrual_suspended=data.get("tfr_accrual_suspended", False) or False,
        previdenza_scales_with_personnel=data.get("previdenza_scales_with_personnel", False) or False,
        interest_rate_receivables=data.get("interest_rate_receivables", 0.0),
        interest_rate_payables=data.get("interest_rate_payables", 0.0),
        tax_rate=data.get("tax_rate", 27.9),
        tax_advances_paid=data.get("tax_advances_paid", 0.0) or 0.0,
        tax_temporary_differences=jsonable_encoder(
            data.get("tax_temporary_differences", None)
        ),
        fixed_materials_percentage=data.get("fixed_materials_percentage", 40.0),
        fixed_services_percentage=data.get("fixed_services_percentage", 40.0),
        depreciation_rate=data.get("depreciation_rate", 20.0),
        depreciation_rate_intangible=data.get("depreciation_rate_intangible", 20.0),
        # Coalesce null -> 0: the UI now allows clearing these fields (sends null),
        # but the columns are NOT NULL. 0 == "no financing", the existing default
        # semantics. (.get(key, 0.0) only defaults on a MISSING key, not an explicit null.)
        financing_amount=data.get("financing_amount") or 0.0,
        financing_duration_years=data.get("financing_duration_years") or 0.0,
        financing_interest_rate=data.get("financing_interest_rate") or 0.0,
        financing_loans=jsonable_encoder(data.get("financing_loans", None)),
        sp01_growth_pct=data.get("sp01_growth_pct", None),
        sp04_growth_pct=data.get("sp04_growth_pct", None),
        sp06e_growth_pct=data.get("sp06e_growth_pct", None),
        sp06f_growth_pct=data.get("sp06f_growth_pct", None),
        sp08_growth_pct=data.get("sp08_growth_pct", None),
        sp10_growth_pct=data.get("sp10_growth_pct", None),
        sp14_growth_pct=data.get("sp14_growth_pct", None),
        sp16e_growth_pct=data.get("sp16e_growth_pct", None),
        sp16f_growth_pct=data.get("sp16f_growth_pct", None),
        sp16g_growth_pct=data.get("sp16g_growth_pct", None),
        sp17d_growth_pct=data.get("sp17d_growth_pct", None),
        sp17e_growth_pct=data.get("sp17e_growth_pct", None),
        sp17f_growth_pct=data.get("sp17f_growth_pct", None),
        sp17g_growth_pct=data.get("sp17g_growth_pct", None),
        sp18_growth_pct=data.get("sp18_growth_pct", None),
        sp_overrides=jsonable_encoder(data.get("sp_overrides", None)),
        ce02_override=data.get("ce02_override", None),
        ce03_override=data.get("ce03_override", None),
        ce03a_override=data.get("ce03a_override", None),
        ce10_override=data.get("ce10_override", None),
        ce11_override=data.get("ce11_override", None),
        ce13_override=data.get("ce13_override", None),
        ce14_override=data.get("ce14_override", None),
        ce15_override=data.get("ce15_override", None),
        ce16_override=data.get("ce16_override", None),
        ce17_override=data.get("ce17_override", None),
        ce18_override=data.get("ce18_override", None),
        ce19_override=data.get("ce19_override", None),
        ce01_override=data.get("ce01_override", None),
        ce04_override=data.get("ce04_override", None),
        ce05_override=data.get("ce05_override", None),
        ce06_override=data.get("ce06_override", None),
        ce07_override=data.get("ce07_override", None),
        ce08_override=data.get("ce08_override", None),
        ce08a_override=data.get("ce08a_override", None),
        ce08b_override=data.get("ce08b_override", None),
        ce08c_override=data.get("ce08c_override", None),
        ce08d_override=data.get("ce08d_override", None),
        ce09_override=data.get("ce09_override", None),
        ce09a_override=data.get("ce09a_override", None),
        ce09b_override=data.get("ce09b_override", None),
        ce09c_override=data.get("ce09c_override", None),
        ce09d_override=data.get("ce09d_override", None),
        ce11b_override=data.get("ce11b_override", None),
        ce12_override=data.get("ce12_override", None),
        ce17a_override=data.get("ce17a_override", None),
        ce17b_override=data.get("ce17b_override", None),
        ce20_override=data.get("ce20_override", None),
    )
    return _normalize_numeric_fields(row)


def bulk_upsert_assumptions(
    db: Session,
    scenario_id: int,
    assumptions_list: List[Dict[str, Any]],
    auto_generate: bool = True
) -> Dict[str, Any]:
    """
    Bulk insert or update budget assumptions for a scenario.

    This replaces all existing assumptions with the new ones provided.
    Optionally triggers automatic forecast generation.

    Args:
        db: Database session
        scenario_id: Budget scenario ID
        assumptions_list: List of assumption dicts with fields:
            - forecast_year: int (required)
            - revenue_growth_pct: float
            - material_cost_growth_pct: float
            - service_cost_growth_pct: float
            - personnel_cost_growth_pct: float
            - other_revenue_growth_pct: float
            - depreciation_rate_tangible_pct: float
            - depreciation_rate_intangible_pct: float
            - capex_tangible: Decimal
            - capex_intangible: Decimal
            - new_debt: Decimal
            - debt_repayment: Decimal
            - interest_rate_pct: float
            - tax_rate_pct: float
            - dividend_payout_pct: float
        auto_generate: If True, automatically generate forecasts after saving

    Returns:
        Dictionary with operation results:
            - success: bool
            - scenario_id: int
            - assumptions_saved: int
            - forecast_generated: bool
            - forecast_years: List[int]
            - message: str

    Raises:
        ValueError: If scenario not found or validation fails
    """
    # 1. Validate scenario exists
    scenario = db.query(models.BudgetScenario).filter(
        models.BudgetScenario.id == scenario_id
    ).first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found")

    # 2-4. Validazione condivisa col percorso di anteprima (Task 9): stesso
    # corpo malformato -> stesso messaggio, ovunque arrivi. Valida PRIMA di
    # qualunque lettura che dipenda dall'anno base, e restituisce gli anni GIA'
    # COERCIATI: il loop sotto e forecast_years_list usano quelli, mai il valore
    # grezzo del dict (N1).
    coerced_years = validate_assumptions_list(assumptions_list, scenario.base_year)

    # 5. Delete existing assumptions for this scenario
    db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).delete()

    # 6. Insert new assumptions
    assumptions_saved = 0
    forecast_years_list = []

    for assumption_data, forecast_year in zip(assumptions_list, coerced_years):
        db_assumption = build_assumption_row(scenario_id, assumption_data, forecast_year=forecast_year)
        db.add(db_assumption)
        assumptions_saved += 1
        forecast_years_list.append(forecast_year)

    # 7. Gli anni fuori piano si potano QUI, non solo dentro il motore: le
    # ipotesi vengono committate qui sotto, mentre il motore puo' non girare
    # affatto (`auto_generate=false`) o fallire — e in quel caso la sua
    # transazione, potatura compresa, viene annullata mentre le ipotesi salvate
    # restano. In entrambi i casi /analysis conterebbe ancora gli anni in piu'
    # coi numeri del salvataggio precedente, sotto un avviso che parla solo di
    # generazione.
    #
    # Sta PRIMA del commit, non dopo: cosi' e' atomica col salvataggio delle
    # ipotesi (una DELETE che fallisce annulla tutto e l'errore e' onesto),
    # mentre dopo il commit avrebbe potuto restituire 500 «errore nel
    # salvataggio» su ipotesi gia' persistite e previsionale non rigenerato.
    # L'infrannuale e' escluso: la sua proiezione e' un anno solo e non segue
    # gli anni delle ipotesi.
    if scenario.scenario_type != "infrannuale":
        prune_out_of_plan_forecast_years(db, scenario_id, forecast_years_list)

    # 7-bis. Commit assumptions
    db.commit()

    # 8. Generate forecasts if requested
    forecast_generated = False
    if auto_generate:
        try:
            if scenario.scenario_type == "infrannuale":
                from calculations.intra_year_engine import IntraYearEngine
                engine = IntraYearEngine(db)
                engine.generate_projection(scenario_id)
            else:
                engine = ForecastEngine(db)
                engine.generate_forecast(scenario_id)
            forecast_generated = True
        except Exception as e:
            # If forecast generation fails, return success for assumptions but note failure
            return {
                "success": True,
                "scenario_id": scenario_id,
                "assumptions_saved": assumptions_saved,
                "forecast_generated": False,
                "forecast_years": forecast_years_list,
                "message": f"Assumptions saved successfully, but forecast generation failed: {str(e)}"
            }

    return {
        "success": True,
        "scenario_id": scenario_id,
        "assumptions_saved": assumptions_saved,
        "forecast_generated": forecast_generated,
        "forecast_years": sorted(forecast_years_list),
        "message": "Assumptions saved and forecast generated successfully" if forecast_generated
                   else "Assumptions saved successfully"
    }


def get_assumptions_for_scenario(
    db: Session,
    scenario_id: int
) -> List[models.BudgetAssumptions]:
    """
    Get all assumptions for a scenario, ordered by year.

    Args:
        db: Database session
        scenario_id: Budget scenario ID

    Returns:
        List of BudgetAssumptions ordered by forecast_year

    Raises:
        ValueError: If scenario not found
    """
    # Validate scenario exists
    scenario = db.query(models.BudgetScenario).filter(
        models.BudgetScenario.id == scenario_id
    ).first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found")

    # Get assumptions ordered by year
    assumptions = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).order_by(models.BudgetAssumptions.forecast_year).all()

    return assumptions


def delete_assumptions_for_scenario(
    db: Session,
    scenario_id: int
) -> int:
    """
    Delete all assumptions for a scenario.

    Args:
        db: Database session
        scenario_id: Budget scenario ID

    Returns:
        Number of assumptions deleted

    Raises:
        ValueError: If scenario not found
    """
    # Validate scenario exists
    scenario = db.query(models.BudgetScenario).filter(
        models.BudgetScenario.id == scenario_id
    ).first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found")

    # Delete assumptions
    count = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).delete()

    db.commit()

    return count
