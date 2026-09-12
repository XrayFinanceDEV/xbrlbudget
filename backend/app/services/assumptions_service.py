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
from pydantic import ValidationError
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from database import models
from calculations.forecast_engine import ForecastEngine, prune_out_of_plan_forecast_years
from app.schemas.budget import BudgetAssumptionsBulkRow


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


class AssumptionsValidationError(ValueError):
    """Ipotesi che le rotte tipizzate rifiutano (lotto 3A, Task 7a): `errori` e' un elenco di
    `{forecast_year, campo, messaggio}` in italiano. Sottoclasse di `ValueError`, cosi' l'anteprima — che cattura
    `ValueError` e risponde 400 — non cambia; il bulk la cattura prima e risponde 422."""

    def __init__(self, errori):
        self.errori = list(errori)
        super().__init__("Ipotesi non valide: " + "; ".join(
            (f"{e['forecast_year']} · " if e.get("forecast_year") is not None else "") + f"{e['campo']}: {e['messaggio']}"
            for e in self.errori
        ))


def _errore(anno, campo, messaggio):
    return {"forecast_year": anno, "campo": campo, "messaggio": messaggio}


_TIPO_ATTESO = {
    "decimal_parsing": "un numero", "decimal_type": "un numero", "float_parsing": "un numero", "float_type": "un numero",
    "int_parsing": "un numero intero", "int_type": "un numero intero", "int_from_float": "un numero intero",
    "bool_parsing": "vero o falso", "bool_type": "vero o falso",
    "dict_type": "un oggetto", "model_type": "un oggetto", "model_attributes_type": "un oggetto",
    "list_type": "un elenco", "string_type": "un testo",
}


def messaggio_errore_campo(err) -> str:
    """Un errore di Pydantic in italiano, per tipo. Un tipo non mappato dice comunque che il valore non e' valido;
    il valore ricevuto si mostra sempre, tranne per un campo mancante."""
    tipo, ctx = err.get("type"), err.get("ctx") or {}
    if tipo == "missing":
        return "campo obbligatorio mancante"
    if tipo == "greater_than_equal":
        testo = f"deve essere maggiore o uguale a {ctx.get('ge')}"
    elif tipo == "greater_than":
        testo = f"deve essere maggiore di {ctx.get('gt')}"
    elif tipo == "less_than_equal":
        testo = f"deve essere minore o uguale a {ctx.get('le')}"
    elif tipo == "less_than":
        testo = f"deve essere minore di {ctx.get('lt')}"
    elif tipo == "literal_error":
        testo = "valore non ammesso: sono ammessi " + str(ctx.get("expected", "")).replace(" or ", " o ")
    elif tipo == "extra_forbidden":
        testo = "campo sconosciuto, non ammesso"
    elif tipo == "string_pattern_mismatch":
        testo = "valore non ammesso"
    elif tipo == "string_too_short":
        testo = f"testo troppo corto (minimo {ctx.get('min_length')} caratteri)"
    elif tipo == "string_too_long":
        testo = f"testo troppo lungo (massimo {ctx.get('max_length')} caratteri)"
    elif tipo == "value_error":
        testo = str(err.get("msg", "")).removeprefix("Value error, ")
    elif tipo in _TIPO_ATTESO:
        testo = f"tipo sbagliato: serve {_TIPO_ATTESO[tipo]}"
    else:
        testo = "valore non valido"
    return f"{testo} (ricevuto: {err.get('input')!r})"


def _senza_null(riga):
    """`null` dal client vale «campo omesso» (`build_assumption_row` lo coalizza sul default): lo si toglie prima dello schema."""
    pulita = {k: v for k, v in riga.items() if v is not None}
    for chiave in ("financing_loans", "tax_temporary_differences"):
        if isinstance(pulita.get(chiave), list):
            pulita[chiave] = [{k: v for k, v in voce.items() if v is not None} if isinstance(voce, dict) else voce
                              for voce in pulita[chiave]]
    if isinstance(pulita.get("sp_overrides"), dict):
        pulita["sp_overrides"] = {k: v for k, v in pulita["sp_overrides"].items() if v is not None}
    # Come `sp_overrides`: un valore nullo per una voce di `sp_indexing` vale "questa voce non e'
    # indicizzata" (il motore stesso la tratterebbe come "driver sconosciuto", innocuo -- vedi
    # calculations/forecast_engine.py:_resolve_sp_indexing), non un errore di schema. Prima di
    # questa riga un `null` qui dentro alzava 422 sull'INTERO bulk (literal_error sul tipo
    # Literal["ricavi","acquisti","personale"]).
    if isinstance(pulita.get("sp_indexing"), dict):
        pulita["sp_indexing"] = {k: v for k, v in pulita["sp_indexing"].items() if v is not None}
    if isinstance(pulita.get("pregresso"), dict):
        pulita["pregresso"] = {k: ({kk: vv for kk, vv in piano.items() if vv is not None} if isinstance(piano, dict) else piano)
                               for k, piano in pulita["pregresso"].items() if piano is not None}
    return pulita


def validate_bulk_rows(assumptions_list, forecast_years) -> None:
    """Ogni riga del bulk contro `BudgetAssumptionsBulkRow`, tutti gli errori insieme; alza `AssumptionsValidationError`."""
    errori = []
    for riga, anno in zip(assumptions_list, forecast_years):
        try:
            BudgetAssumptionsBulkRow(**_senza_null(riga))
        except ValidationError as exc:
            for err in exc.errors():
                errori.append(_errore(anno, ".".join(str(p) for p in err["loc"]), messaggio_errore_campo(err)))
    if errori:
        raise AssumptionsValidationError(errori)


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
        raise AssumptionsValidationError([_errore(None, "assumptions", "serve almeno una riga di ipotesi")])
    years: List[int] = []
    for assumption in assumptions_list:
        if "forecast_year" not in assumption:
            raise AssumptionsValidationError([_errore(None, "forecast_year", "ogni riga di ipotesi deve avere forecast_year")])
        raw_year = assumption["forecast_year"]
        try:
            forecast_year = int(raw_year)
        except (TypeError, ValueError):
            raise AssumptionsValidationError([_errore(None, "forecast_year", f"forecast_year non valido: {raw_year!r}")])
        years.append(forecast_year)
    errori = [_errore(a, "forecast_year", f"l'anno di previsione {a} deve essere successivo all'anno base {base_year}")
              for a in years if a <= base_year]
    visti = set()
    for a in years:
        if a in visti:
            errori.append(_errore(a, "forecast_year", f"l'anno di previsione {a} e' ripetuto"))
        visti.add(a)
    ordinati = sorted(set(years))
    for prima, dopo in zip(ordinati, ordinati[1:]):
        if dopo != prima + 1:
            errori.append(_errore(dopo, "forecast_year",
                                  f"anni non consecutivi: dopo il {prima} viene il {dopo}, manca il {prima + 1}"))
    if errori:
        raise AssumptionsValidationError(errori)
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
        overdraft_allowed=data.get("overdraft_allowed", False) or False,
        overdraft_limit=data.get("overdraft_limit", None),
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
        pregresso=jsonable_encoder(data.get("pregresso", None)),
        sp_indexing=jsonable_encoder(data.get("sp_indexing", None)),
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
        raise ValueError(f"Scenario {scenario_id} non trovato")

    # 2-4. Validazione condivisa col percorso di anteprima (Task 9): stesso
    # corpo malformato -> stesso messaggio, ovunque arrivi. Valida PRIMA di
    # qualunque lettura che dipenda dall'anno base, e restituisce gli anni GIA'
    # COERCIATI: il loop sotto e forecast_years_list usano quelli, mai il valore
    # grezzo del dict (N1).
    coerced_years = validate_assumptions_list(assumptions_list, scenario.base_year)

    # 4-bis. Ogni riga passa LO SCHEMA TIPIZZATO, qui e prima di qualunque
    # cancellazione (lotto 3A, Task 7a): un tetto di scoperto negativo, un acconto
    # negativo, un driver sconosciuto o un tasso fuori scala non arrivano piu' ne'
    # al motore ne' alle colonne. Un input valido che il motore rifiuta continua a
    # rispondere 200 con `forecast_generated: false` (CLAUDE.md, Previsionale):
    # questo e' un errore del chiamante, non del piano.
    validate_bulk_rows(assumptions_list, coerced_years)

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
                "message": f"Ipotesi salvate, ma il previsionale non è stato calcolato: {str(e)}"
            }

    return {
        "success": True,
        "scenario_id": scenario_id,
        "assumptions_saved": assumptions_saved,
        "forecast_generated": forecast_generated,
        "forecast_years": sorted(forecast_years_list),
        "message": "Ipotesi salvate e previsionale calcolato" if forecast_generated
                   else "Ipotesi salvate"
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
        raise ValueError(f"Scenario {scenario_id} non trovato")

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
        raise ValueError(f"Scenario {scenario_id} non trovato")

    # Delete assumptions
    count = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario_id
    ).delete()

    db.commit()

    return count


def _regenerate_forecast(db: Session, scenario: models.BudgetScenario) -> None:
    """La stessa selezione di motore di `POST /generate` (infrannuale vs
    budget), fattorizzata perche' `update_single_year_assumptions` e
    `apply_ce_overrides` non la duplichino."""
    if scenario.scenario_type == "infrannuale":
        from calculations.intra_year_engine import IntraYearEngine
        IntraYearEngine(db).generate_projection(scenario.id)
    else:
        ForecastEngine(db).generate_forecast(scenario.id)


def update_single_year_assumptions(
    db: Session,
    scenario: models.BudgetScenario,
    forecast_year: int,
    update_data: Dict[str, Any],
) -> models.BudgetAssumptions:
    """
    Aggiorna le ipotesi di UN anno (`PUT /assumptions/{year}`, l'editor di
    cella di SP Prev.) e rigenera il previsionale nella STESSA transazione:
    se la generazione fallisce, l'aggiornamento si annulla — un override di
    cella rifiutato dal motore non resta persistito (CLAUDE.md §
    Previsionale/Frontend, "una correzione che tocca piu' campi si applica
    tutta o niente").

    Diverso dal bulk (`bulk_upsert_assumptions` sopra), che salva SEMPRE
    anche a generazione fallita: e' un comportamento documentato del wizard,
    e questa funzione non lo tocca. Qui non c'e' nulla da "salvare
    comunque" — l'unico esito utile e' l'override applicato E riflesso nel
    previsionale, o nessuno dei due.

    Solleva `LookupError` se le ipotesi dell'anno non esistono (nessuna
    mutazione avvenuta, nulla da annullare); rilancia l'eccezione del
    motore (di norma `ValueError`) dopo un `rollback()` che disfa la
    `setattr` appena fatta.
    """
    db_assumptions = db.query(models.BudgetAssumptions).filter(
        models.BudgetAssumptions.scenario_id == scenario.id,
        models.BudgetAssumptions.forecast_year == forecast_year,
    ).first()
    if not db_assumptions:
        raise LookupError(
            f"Assumptions for year {forecast_year} not found in scenario {scenario.id}"
        )

    for field, value in update_data.items():
        setattr(db_assumptions, field, value)

    try:
        _regenerate_forecast(db, scenario)
    except Exception:
        db.rollback()
        raise

    db.refresh(db_assumptions)
    return db_assumptions


# I campi ce*_override che PATCH /ce-override puo' toccare. Vive qui, non nel
# router, per lo stesso motivo di `bulk_upsert_assumptions`: la mutazione (e
# ora l'atomicita' col motore) e' logica di servizio, non di routing.
CE_OVERRIDE_FIELDS = {
    "ce01_override", "ce02_override", "ce03_override", "ce03a_override", "ce04_override",
    "ce05_override", "ce06_override", "ce07_override", "ce08_override",
    "ce08a_override", "ce08b_override", "ce08c_override", "ce08d_override",
    "ce09_override", "ce09a_override", "ce09b_override", "ce09c_override", "ce09d_override",
    "ce10_override", "ce11_override", "ce11b_override", "ce12_override",
    "ce13_override", "ce14_override", "ce15_override", "ce16_override",
    "ce17_override", "ce17a_override", "ce17b_override",
    "ce18_override", "ce19_override", "ce20_override",
}


def apply_ce_overrides(
    db: Session,
    scenario: models.BudgetScenario,
    overrides: List[Dict[str, Any]],
) -> int:
    """
    Applica un lotto di override `ce*_override` (`PATCH /ce-override`,
    l'editor di cella di CE Prev.), poi rigenera il previsionale UNA sola
    volta — stessa atomicita' di `update_single_year_assumptions`: una
    rigenerazione rifiutata annulla TUTTO il lotto appena applicato, non solo
    l'ultima voce (CLAUDE.md § Previsionale/Frontend, "una correzione che
    tocca piu' campi si applica tutta o niente").

    Solleva `ValueError` per un lotto vuoto o malformato (voce senza
    `forecast_year`/`field`, o un `field` fuori da `CE_OVERRIDE_FIELDS`) e
    `LookupError` per un anno senza ipotesi — in ENTRAMBI i casi con un
    `rollback()` di quanto gia' applicato nel lotto prima dell'errore;
    rilancia l'eccezione del motore dopo lo stesso `rollback()`.

    Restituisce il numero di override applicati.
    """
    if not overrides:
        raise ValueError("Serve l'elenco degli override (overrides)")

    from decimal import Decimal as D

    try:
        assumption_cache: Dict[int, models.BudgetAssumptions] = {}
        applied = 0
        for entry in overrides:
            forecast_year = entry.get("forecast_year")
            field = entry.get("field")
            value = entry.get("value")

            if not forecast_year or not field:
                raise ValueError("Ogni override richiede forecast_year e field")
            if field not in CE_OVERRIDE_FIELDS:
                raise ValueError(f"Campo di override non valido: {field}")

            if forecast_year not in assumption_cache:
                assumption = db.query(models.BudgetAssumptions).filter(
                    models.BudgetAssumptions.scenario_id == scenario.id,
                    models.BudgetAssumptions.forecast_year == forecast_year,
                ).first()
                if not assumption:
                    raise LookupError(f"Nessuna ipotesi per l'anno {forecast_year}")
                assumption_cache[forecast_year] = assumption

            setattr(
                assumption_cache[forecast_year], field,
                D(str(value)) if value is not None else None,
            )
            applied += 1

        _regenerate_forecast(db, scenario)
    except Exception:
        db.rollback()
        raise

    return applied


def apply_sp_overrides(
    db: Session,
    scenario: models.BudgetScenario,
    overrides: List[Dict[str, Any]],
) -> int:
    """
    Applica un lotto di override `sp_overrides` (`PATCH /sp-override`, l'editor
    di cella di SP Prev., PIU' anni in una sola chiamata), poi rigenera il
    previsionale UNA sola volta -- stessa atomicita' di `apply_ce_overrides`:
    una rigenerazione rifiutata annulla TUTTO il lotto appena applicato, su
    TUTTI gli anni coinvolti, non solo l'ultimo (CLAUDE.md § Previsionale/
    Frontend, "una correzione che tocca piu' campi si applica tutta o
    niente").

    Perche' esiste (giro di correzione 3, task 10): prima di questa funzione
    SP Prev. salvava una modifica multi-anno con un `PUT /assumptions/{year}`
    **per ogni anno, in parallelo** (`Promise.all` lato client) -- e dal giro
    2 ciascun PUT rigenera l'INTERO scenario nella propria transazione. Su
    SQLite questo rischia scritture concorrenti (`database is locked`) e un
    anno puo' essere validato senza vedere ancora la modifica dell'altro,
    non ancora committata: un rifiuto spurio anche quando la combinazione
    delle due modifiche sarebbe valida. Qui tutte le modifiche di tutti gli
    anni si applicano PRIMA di una rigenerazione sola, come gia' fa
    `apply_ce_overrides` per CE Prev.

    Ogni entry e' `{forecast_year, field, value}`: `field` e' il NOME del
    campo dentro il sacco JSON `sp_overrides` di quell'anno -- non c'e' un
    `CE_OVERRIDE_FIELDS` da rispettare qui, perche' il motore stesso ignora
    in silenzio una chiave che non esiste nel risultato (CLAUDE.md §
    Previsionale, gia' documentato per `sp_overrides`). `value: None`
    cancella quella chiave dal sacco (torna al calcolo del motore);
    altrimenti la scrive o sovrascrive. Piu' entry sullo stesso anno si
    fondono nello STESSO sacco, replicando il merge che il client faceva
    prima leggendo `current?.sp_overrides` (ora lato server, sulla riga
    fresca di questa transazione, non su una copia letta a parte).

    Solleva `ValueError` per un lotto vuoto o una entry senza
    `forecast_year`/`field`, `LookupError` per un anno senza ipotesi -- in
    ENTRAMBI i casi con `rollback()` di quanto gia' applicato nel lotto
    prima dell'errore; rilancia l'eccezione del motore dopo lo stesso
    `rollback()`.

    Restituisce il numero di ANNI toccati (non il numero di entry: piu'
    entry sullo stesso anno contano una volta sola).
    """
    if not overrides:
        raise ValueError("Serve l'elenco degli override (overrides)")

    try:
        assumption_cache: Dict[int, models.BudgetAssumptions] = {}
        bag_cache: Dict[int, Dict[str, Any]] = {}

        for entry in overrides:
            forecast_year = entry.get("forecast_year")
            field = entry.get("field")
            value = entry.get("value")

            if not forecast_year or not field:
                raise ValueError("Ogni override richiede forecast_year e field")

            if forecast_year not in assumption_cache:
                assumption = db.query(models.BudgetAssumptions).filter(
                    models.BudgetAssumptions.scenario_id == scenario.id,
                    models.BudgetAssumptions.forecast_year == forecast_year,
                ).first()
                if not assumption:
                    raise LookupError(f"Nessuna ipotesi per l'anno {forecast_year}")
                assumption_cache[forecast_year] = assumption
                bag_cache[forecast_year] = dict(assumption.sp_overrides or {})

            bag = bag_cache[forecast_year]
            if value is None:
                bag.pop(field, None)
            else:
                bag[field] = value

        for forecast_year, assumption in assumption_cache.items():
            bag = bag_cache[forecast_year]
            assumption.sp_overrides = jsonable_encoder(bag) if bag else None

        _regenerate_forecast(db, scenario)
    except Exception:
        db.rollback()
        raise

    return len(assumption_cache)
