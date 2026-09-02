"""Che stato risponde `get_current_user` per ogni forma di credenziale (issue #36).

Il punto della suite è **lo stato HTTP**, non il payload: il frontend ri-chiede il
token al parent dell'iframe solo sul **401** (`frontend/lib/api.ts`), quindi un token
rifiutato che esce come 500 lascia l'utente su un errore generico invece di
ri-autenticarlo.

Un 500 resta legittimo in un caso solo: il server di produzione senza
`SUPABASE_JWT_SECRET`. Lì il difetto è del deployment, non del client, e un 401
manderebbe l'iframe a ri-chiedere all'infinito un token che nessuno potrà mai
verificare.
"""
import datetime

import jwt
import pytest
from fastapi.testclient import TestClient

SECRET = "auth-endpoint-test-secret"
DEV_ID = "dev-user-001"


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _signed(claims, secret=SECRET):
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture()
def client(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.app.main import app
    from app.core import database as core_db
    from app.core.config import settings
    from database.db import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    def override_get_db():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[core_db.get_db] = override_get_db
    # Ogni test dichiara la propria configurazione: si parte da produzione nuda.
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", None)
    monkeypatch.setattr(settings, "DEV_USER_ID", None)

    with TestClient(app, raise_server_exceptions=False) as c:
        try:
            yield c, settings, monkeypatch
        finally:
            app.dependency_overrides.clear()


# --- Sviluppo: DEV_USER_ID impostato, nessun segreto ------------------------

def test_senza_header_il_fallback_di_sviluppo_lascia_passare(client):
    c, settings, mp = client
    mp.setattr(settings, "DEV_USER_ID", DEV_ID)

    assert c.get("/api/v1/companies").status_code == 200


def test_token_malformato_in_sviluppo_risponde_401_non_500(client):
    """Il caso dell'issue #36: `Bearer dev` contro un backend senza segreto.

    Un token che non si può verificare non vale più di nessun token: 401. Il
    fallback `DEV_USER_ID` non lo riscatta — altrimenti in sviluppo qualunque
    stringa passerebbe, e un token davvero rotto non si vedrebbe mai.
    """
    c, settings, mp = client
    mp.setattr(settings, "DEV_USER_ID", DEV_ID)

    r = c.get("/api/v1/companies", headers=_bearer("dev"))

    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_token_valido_in_sviluppo_risponde_401_se_manca_il_segreto(client):
    """Nemmeno un JWT ben formato passa: senza segreto la firma non si controlla."""
    c, settings, mp = client
    mp.setattr(settings, "DEV_USER_ID", DEV_ID)

    r = c.get("/api/v1/companies", headers=_bearer(_signed({"sub": "utente-vero"})))

    assert r.status_code == 401


# --- Produzione: segreto configurato ----------------------------------------

def test_token_firmato_bene_passa(client):
    c, settings, mp = client
    mp.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)

    r = c.get("/api/v1/companies", headers=_bearer(_signed({"sub": "utente-vero"})))

    assert r.status_code == 200


@pytest.mark.parametrize(
    "nome,token",
    [
        ("troncato", "dev"),
        ("tre-segmenti-ma-spazzatura", "aaa.bbb.ccc"),
        ("vuoto-dopo-Bearer", ""),
        ("firmato-con-un-altro-segreto", _signed({"sub": "x"}, secret="segreto-sbagliato")),
        ("senza-claim-sub", _signed({"email": "x@example.com"})),
        (
            "scaduto",
            _signed(
                {
                    "sub": "x",
                    "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1),
                }
            ),
        ),
    ],
)
def test_ogni_token_rifiutato_esce_401(client, nome, token):
    c, settings, mp = client
    mp.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)

    r = c.get("/api/v1/companies", headers=_bearer(token))

    # `Bearer ` con token vuoto non è una credenziale: HTTPBearer(auto_error=False)
    # la scarta e si finisce sul ramo «nessuna autenticazione», che è comunque 401.
    assert r.status_code == 401, f"{nome} -> {r.status_code} {r.text}"
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_senza_header_e_senza_dev_user_id_esce_401(client):
    c, settings, mp = client
    mp.setattr(settings, "SUPABASE_JWT_SECRET", SECRET)

    r = c.get("/api/v1/companies")

    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


# --- Il 500 che resta -------------------------------------------------------

def test_segreto_mancante_in_produzione_resta_500(client):
    """Nessun segreto e nessun `DEV_USER_ID`: è il server a essere configurato male.

    Un 401 qui manderebbe l'iframe a ri-chiedere un token che questo server non
    potrà mai accettare; il 500 dice la verità, cioè che il difetto è a monte.
    """
    c, settings, mp = client

    r = c.get("/api/v1/companies", headers=_bearer(_signed({"sub": "x"})))

    assert r.status_code == 500
    assert "SUPABASE_JWT_SECRET" in r.json()["detail"]
