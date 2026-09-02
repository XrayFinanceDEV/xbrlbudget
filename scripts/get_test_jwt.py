#!/usr/bin/env python3
"""Ottiene un JWT vero facendo login sul backend FastAPI, per provare l'auth a mano.

Il login e' `POST /api/v1/users/token` di `api_server_it` (form OAuth2), che
inoltra a `supabase.auth.sign_in_with_password` e restituisce lo stesso
`access_token` che l'iframe riceve per postMessage: HS256, `aud:
"authenticated"`, `sub` = uuid dell'utente. Passare dal backend, e non da
Supabase, evita di dover tenere in giro la chiave anon del progetto.

Nessuna credenziale sta qui dentro: si leggono dall'ambiente, e il posto dove
tenerle e' un file `.env*.local`, che `.gitignore` copre a qualunque profondita'.

    source .env.test.local && python scripts/get_test_jwt.py

Variabili: TEST_USER_EMAIL e TEST_USER_PASSWORD (richieste), API_BASE_URL
(facoltativa, default il backend di produzione).

Il token vale un'ora e si usa cosi':

    TOKEN=$(source .env.test.local && python scripts/get_test_jwt.py)
    curl -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/companies

Perche' il backend budget lo accetti serve `SUPABASE_JWT_SECRET` dello stesso
progetto Supabase (sta in `.env.staging`). Senza quel segreto il backend non puo'
verificare nulla e risponde 401 anche a un token perfettamente valido — vedi
`docs/deployment/IFRAME_INTEGRATION.md`, sezione «Testing auth with a real token».
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API_BASE_URL = "https://api.kpsfinanciallab.it"
LOGIN_PATH = "/api/v1/users/token"


def main() -> int:
    email = os.environ.get("TEST_USER_EMAIL")
    password = os.environ.get("TEST_USER_PASSWORD")
    if not email or not password:
        print(
            "Mancano TEST_USER_EMAIL e/o TEST_USER_PASSWORD.\n"
            "Crea un file .env*.local (gitignorato) e fanne il source; il modello e'\n"
            "nel docstring di questo script.",
            file=sys.stderr,
        )
        return 2

    base = os.environ.get("API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
    # OAuth2PasswordRequestForm: i campi si chiamano username/password, non email.
    body = urllib.parse.urlencode({"username": email, "password": password}).encode()
    req = urllib.request.Request(
        base + LOGIN_PATH,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        # Il corpo dice quale delle due cose e' sbagliata; la password non vi
        # compare mai, quindi si puo' stampare.
        print(
            f"{base}{LOGIN_PATH} ha risposto {e.code}: {e.read().decode(errors='replace')[:400]}",
            file=sys.stderr,
        )
        return 1
    except urllib.error.URLError as e:
        print(f"{base} irraggiungibile: {e.reason}", file=sys.stderr)
        return 1

    token = payload.get("access_token")
    if not token:
        print(f"Nessun access_token nella risposta: {json.dumps(payload)[:400]}", file=sys.stderr)
        return 1

    user = payload.get("user") or {}
    print(f"sub={user.get('id')} email={user.get('email')} role={user.get('role')}", file=sys.stderr)
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
