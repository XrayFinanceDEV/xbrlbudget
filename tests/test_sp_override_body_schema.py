"""PATCH /sp-override valida il CORPO: un `value` non numerico risponde 422, non 500.

Rilievo Minor M2 della revisione finale del lotto 2
(`.superpowers/sdd/2026-09-08-scadenziamento-pregresso/final-review.md`): la
rotta riceveva `request: Any = Body(...)` e passava il `value` cosi' com'e' al
servizio, che lo scrive nel sacco `sp_overrides`; il motore lo rilegge con
`Decimal(str(raw_value))` (`calculations/forecast_engine.py`,
`_apply_sp_overrides`). Un `"abc"` solleva `decimal.InvalidOperation`, che e'
un `ArithmeticError` e NON un `ValueError`: la rotta cade nel ramo generico
`except Exception` e risponde **500** «Forecast regeneration failed». Il
rollback e' corretto -- nulla resta scritto -- ma il codice dice "errore del
server" a una schermata che ha mandato un corpo non valido.

La correzione e' un modello Pydantic del corpo
(`backend/app/schemas/budget.py`, `SpOverrideRequest`/`SpOverrideEntry`): NaN e
infiniti sono rifiutati (`allow_inf_nan=False`), `null` continua a voler dire
"cancella quella chiave". Un corpo valido deve comportarsi ESATTAMENTE come
prima, anche nella forma del JSON salvato: `model_dump(mode="json")` di
Pydantic 2 girerebbe i `Decimal` in STRINGHE e `jsonable_encoder` li girerebbe
in float anche dove il corpo ne portava uno intero (`1000` -> `1000.0`), quindi
la rotta ricompone un numero Python dalla forma del Decimal (integrale ->
`int`, altrimenti -> `float`), che e' il tipo che `json.loads` del corpo
produceva prima.

Stile del fixture: client HTTP su DB in-memory come
`tests/test_http_full_cycle.py` (con lo stesso avvertimento sul doppio
`app.*` / `backend.app.*`), azienda/anno/scenario/ipotesi come
`tests/test_sp_override_multi_year_batch.py` (`tests.e2e_kit`).
"""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient

from tests.e2e_kit import memory_sessions, seed_base_year

USER = "sp-override-schema-user"
BASE_YEAR = 2026
FIELD = "sp16a_debiti_banche_breve"


@pytest.fixture()
def client(monkeypatch):
    """Client HTTP + scenario budget gia' ipotecato su un kit forecastable.

    `backend.app.main` va importato PRIMA di `app.*`: il suo modulo mette
    `backend/` su sys.path, e le rotte fanno `from app.core.database import
    get_db` -- sono le copie `app.*` gli oggetti da superare in
    `dependency_overrides` (vedi il commento in
    `tests/test_http_full_cycle.py`).
    """
    from backend.app.main import app

    from app.core import database as core_db
    from app.core.config import settings
    from database.models import BudgetScenario

    engine, sessions = memory_sessions()

    def override_get_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[core_db.get_db] = override_get_db
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(settings, "DEV_USER_ID", USER)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with sessions() as db:
        company_id, _ = seed_base_year(db, user_id=USER, year=BASE_YEAR)
        scenario = BudgetScenario(
            company_id=company_id, name="kit-override", base_year=BASE_YEAR,
            scenario_type="budget",
        )
        db.add(scenario)
        db.commit()
        rows = [
            {"forecast_year": y, "revenue_growth_pct": 3.0, "tax_rate": 27.9}
            for y in (BASE_YEAR + 1, BASE_YEAR + 2)
        ]
        from backend.app.services import assumptions_service

        saved = assumptions_service.bulk_upsert_assumptions(
            db, scenario.id, rows, auto_generate=False
        )
        assert saved["success"] is True, saved
        ids = (company_id, scenario.id)

    with TestClient(app) as client:
        client.kit = {"sessions": sessions, "company_id": ids[0], "scenario_id": ids[1]}
        yield client

    app.dependency_overrides.pop(core_db.get_db, None)
    engine.dispose()


def _patch(client, overrides):
    return client.patch(
        f"/api/v1/companies/{client.kit['company_id']}/scenarios"
        f"/{client.kit['scenario_id']}/sp-override",
        json={"overrides": overrides},
    )


def _bag(client, year):
    from database.models import BudgetAssumptions

    with client.kit["sessions"]() as db:
        row = (
            db.query(BudgetAssumptions)
            .filter(
                BudgetAssumptions.scenario_id == client.kit["scenario_id"],
                BudgetAssumptions.forecast_year == year,
            )
            .first()
        )
        return None if row is None else row.sp_overrides


def test_value_non_numerico_risponde_422_e_non_lascia_nulla(client):
    """`"abc"` era un 500: `Decimal(str("abc"))` nel motore solleva
    `InvalidOperation` (ArithmeticError), che la rotta non sa nominare."""
    response = _patch(client, [{"forecast_year": BASE_YEAR + 1, "field": FIELD, "value": "abc"}])

    assert response.status_code == 422, response.text
    assert _bag(client, BASE_YEAR + 1) is None, "un corpo rifiutato non deve scrivere nulla"


def test_forecast_year_mancante_risponde_422(client):
    """Manca un campo obbligatorio del corpo: e' la validazione Pydantic a
    dirlo, non il `ValueError` del servizio (che resta come difesa a valle)."""
    response = _patch(client, [{"field": FIELD, "value": 1000.0}])

    assert response.status_code == 422, response.text
    assert _bag(client, BASE_YEAR + 1) is None
    assert _bag(client, BASE_YEAR + 2) is None


def test_overrides_non_lista_risponde_422(client):
    """`overrides` non e' una lista: prima si iterava un oggetto qualunque e
    si finiva in un AttributeError da 500."""
    response = _patch(client, {"not": "a list"})

    assert response.status_code == 422, response.text


def test_corpo_valido_salva_un_numero_non_una_stringa(client):
    """Un corpo valido risponde 200 come oggi e il sacco `sp_overrides` porta
    il valore come numero JSON: `model_dump(mode="json")` di un Decimal lo
    avrebbe girato in stringa, e qui si sarebbe salvato `\"400000.55\"`."""
    response = _patch(client, [{"forecast_year": BASE_YEAR + 1, "field": FIELD, "value": 400000.55}])

    assert response.status_code == 200, response.text
    assert response.json()["success"] is True
    bag = _bag(client, BASE_YEAR + 1)
    assert isinstance(bag.get(FIELD), (int, float)) and not isinstance(bag.get(FIELD), str), bag
    assert D(str(bag[FIELD])) == D("400000.55"), bag
    # Il valore deve davvero finire nel previsionale rigenerato.
    from database.models import ForecastYear

    with client.kit["sessions"]() as db:
        fy = (
            db.query(ForecastYear)
            .filter(
                ForecastYear.scenario_id == client.kit["scenario_id"],
                ForecastYear.year == BASE_YEAR + 1,
            )
            .first()
        )
        assert D(str(fy.balance_sheet.sp16a_debiti_banche_breve)) == D("400000.55")


def test_un_intero_resta_intero_nel_sacco(client):
    """Un intero JSON resta un intero: `jsonable_encoder` di un Decimal lo
    avrebbe allargato a `1000.0`, cioe' un'altra forma nel DB rispetto a oggi."""
    response = _patch(client, [{"forecast_year": BASE_YEAR + 1, "field": FIELD, "value": 1000}])

    assert response.status_code == 200, response.text
    assert _bag(client, BASE_YEAR + 1) == {FIELD: 1000}


def test_nan_e_infinito_rispondono_422(client):
    """`allow_inf_nan=False`: un NaN nel sacco si moltiplicherebbe in ogni
    riga del previsionale senza che nessun controllo di quadratura lo veda."""
    for bad in ("NaN", "Infinity", "-Infinity"):
        response = _patch(client, [{"forecast_year": BASE_YEAR + 1, "field": FIELD, "value": bad}])
        assert response.status_code == 422, (bad, response.text)
    assert _bag(client, BASE_YEAR + 1) is None


def test_value_null_cancella_la_chiave(client):
    """`null` continua a voler dire "torna al calcolo del motore"."""
    ok = _patch(client, [{"forecast_year": BASE_YEAR + 1, "field": FIELD, "value": 400000.55}])
    assert ok.status_code == 200, ok.text
    assert _bag(client, BASE_YEAR + 1) == {FIELD: 400000.55}

    cleared = _patch(client, [{"forecast_year": BASE_YEAR + 1, "field": FIELD, "value": None}])
    assert cleared.status_code == 200, cleared.text
    assert _bag(client, BASE_YEAR + 1) is None, "sacca vuoto => colonna NULL, come oggi"
