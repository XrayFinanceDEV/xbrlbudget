"""Un 500 non gestito arriva al browser con le intestazioni CORS, non come un blocco
CORS che ne nasconde il vero codice (rilievo 2 del collaudo del lotto 2,
`.superpowers/sdd/2026-09-08-scadenziamento-pregresso/task-10-report-parte1.md`,
righe 319-350).

`unhandled_exception_handler` (`backend/app/main.py`) e' l'`error_handler` di
`ServerErrorMiddleware`, la middleware piu' esterna: la sua `JSONResponse` non
attraversa piu' `CORSMiddleware` (registrato sotto), quindi un'origine consentita non
vedeva `Access-Control-Allow-Origin` su un 500 imprevisto, e il browser lo bloccava
mostrando "CORS policy" invece del vero errore.

La rotta di prova qui sotto (`/api/v1/__test_raises`) esiste solo per questo test:
solleva sempre, cosi' il test non dipende da nessun bug applicativo vero.
"""
from fastapi.testclient import TestClient

from backend.app.main import app

ALLOWED_ORIGIN = "http://localhost:3000"
DISALLOWED_ORIGIN = "http://evil.example"


@app.get("/api/v1/__test_raises")
def _raises_for_test():
    raise RuntimeError("boom, apposta")


client = TestClient(app, raise_server_exceptions=False)


def test_500_porta_le_intestazioni_cors_per_unorigine_consentita():
    r = client.get("/api/v1/__test_raises", headers={"Origin": ALLOWED_ORIGIN})

    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert r.json() == {"detail": "Internal server error"}


def test_500_non_porta_intestazioni_cors_per_unorigine_non_consentita():
    r = client.get("/api/v1/__test_raises", headers={"Origin": DISALLOWED_ORIGIN})

    assert r.status_code == 500
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers.keys()}
    assert r.json() == {"detail": "Internal server error"}
