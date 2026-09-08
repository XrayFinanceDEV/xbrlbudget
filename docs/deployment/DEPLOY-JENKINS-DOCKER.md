# Deploy reale: Jenkins + Docker + nginx

Questa è la procedura che gira davvero. Le altre pagine di questa cartella descrivono il
percorso **Netlify + backend su host dedicato**, dismesso: sono marcate `NON CORRENTE` e
non vanno seguite.

Ogni affermazione qui sotto è verificabile nel repository: `Jenkinsfile`,
`docker-compose.yml`, `Dockerfile.frontend`, `Dockerfile.backend`, `Dockerfile.nginx`,
`nginx/default.conf`. Quando il codice cambia, cambia anche questa pagina —
`tests/test_deployment_docs.py` tiene ancorate le tre affermazioni portanti.

## In una riga

Un push fa partire Jenkins, che genera `.env.docker` dalle credenziali, esegue
`docker compose build` + `up -d` e pubblica l'nginx del compose su `127.0.0.1:9090`;
l'nginx di **host** (fuori da questo repository) espone quella porta come sito HTTPS.

## Perché non esiste un URL di backend da configurare

`NEXT_PUBLIC_API_URL` in produzione è **vuota di proposito**. È il fatto che spiega perché
niente si è rotto quando l'host del vecchio backend è sparito.

- `Dockerfile.frontend` costruisce l'immagine con `ENV NEXT_PUBLIC_API_URL=""`, quindi il
  valore in `frontend/.env.production` non arriva mai al bundle.
- `frontend/lib/api.ts` con la variabile vuota cade sul ramo **relativo** `/api/v1` (lato
  browser; lato server, in assenza di variabile, usa `http://localhost:8000/api/v1`).
- `nginx/default.conf` sta davanti a entrambi: `location /api/` va a `backend:8000`,
  `location /` va a `frontend:3000`. Stessa origine, nessun CORS da configurare per l'app.

Corollario: non esiste una variabile d'ambiente con dentro l'host pubblico. Cambiare il
dominio non richiede un rebuild del frontend per via dell'API — richiede semmai di
aggiornare le origini del **genitore** (sotto).

## Le tre immagini

| Servizio | Dockerfile | Che cosa fa |
|---|---|---|
| `backend` | `Dockerfile.backend` | FastAPI su `:8000` nella rete compose. `env_file: .env.docker`, `DATABASE_PATH=/app/data/financial_analysis.db` sul volume `db-data`, healthcheck su `/health` |
| `frontend` | `Dockerfile.frontend` | Next.js standalone su `:3000`. Build arg `NEXT_PUBLIC_PARENT_ORIGIN` da `${PARENT_ORIGIN}`; `NEXT_PUBLIC_API_URL` forzata a stringa vuota |
| `nginx` | `Dockerfile.nginx` | Unico ingresso. Pubblicato su `127.0.0.1:${PORT:-8080}` (Jenkins passa `PORT=9090`) |

Il quarto servizio, `mineru`, sta dietro il compose profile `mineru` ed è **escluso da ogni
comando compose**, `build` compreso: la sua immagine è `FROM vllm/vllm-openai` e sul VPS non
ci deve andare. `MINERU_OCR_ENABLED` nel compose è `false` di default.

## La pipeline, stadio per stadio (`Jenkinsfile`)

1. **Trigger** — `githubPush()`, con `disableConcurrentBuilds()` e timeout di 15 minuti.
2. **Checkout** — `checkout scm`.
3. **Generate env** — scrive `.env.docker` con `SUPABASE_JWT_SECRET`, `ANTHROPIC_API_KEY`,
   `ADMIN_API_KEY` (credenziali Jenkins), più `PARENT_ORIGIN`, `ALLOWED_ORIGINS`,
   `MAX_COMPANIES_PER_USER=50`, `PORT=9090`. Non esiste un file di env versionato.
4. **Build** — `docker compose build --no-cache --parallel`.
5. **Deploy** — `docker compose down --timeout 10` poi `up -d --remove-orphans`.
6. **Health check** — dieci tentativi a 5 secondi su
   `docker inspect --format="{{.State.Health.Status}}" budget-backend-1`.
7. **Cleanup** — `docker image prune -f`; in caso di fallimento la pipeline ritenta un
   `up -d` di rollback.

⚠️ `PARENT_ORIGIN` deve stare nel blocco `environment{}` del `Jenkinsfile`, non solo in
`.env.docker`: `docker compose build` risolve `${PARENT_ORIGIN}` dall'ambiente di shell,
mentre `.env.docker` è soltanto l'`env_file` del backend.

## Origini, iframe e JWT

L'app vive dentro l'iframe di Formula Finance, e due controlli indipendenti devono
concordare sulle origini del genitore:

- `nginx/default.conf` manda `Content-Security-Policy: frame-ancestors …` con
  `https://app.formulafinance.it` e `https://app.kpsfinanciallab.it`. È **cotta
  nell'immagine**: cambiarla vuol dire ricostruire.
- `NEXT_PUBLIC_PARENT_ORIGIN` (build arg, da `PARENT_ORIGIN` nel `Jenkinsfile`) è il
  controllo lato client in `AuthContext`; vuota = permissiva.

`ALLOWED_ORIGINS` in `.env.docker` aggiunge origini CORS a quelle di
`backend/app/core/config.py`. Dettagli del protocollo: [IFRAME_INTEGRATION.md](IFRAME_INTEGRATION.md).

## Dove sta, in concreto

Il nome pubblico non è deciso in questo repository: l'nginx di host del VPS mappa il
dominio sulla porta di loopback pubblicata dal compose. Sullo staging l'app risponde su
`https://budget.kpsfinanciallab.it`; la produzione sta su un server separato. Il
`Jenkinsfile` pinna invece esplicitamente le origini del **genitore**
(`app.formulafinance.it`, `app.kpsfinanciallab.it`), ed è lì che si vede a quale ambiente
appartiene un deploy.

Timeout: l'import PDF con LLM (e MinerU in locale) supera abbondantemente il minuto.
`nginx/default.conf` tiene `proxy_read_timeout`/`proxy_send_timeout` a 1200s; se davanti c'è
un altro nginx, anche lì serve un timeout generoso o l'import esce in 504.

## Netlify

`netlify.toml` è ancora nel repository ma **nessuna fase della pipeline lo usa**: il
frontend viene costruito da `Dockerfile.frontend`. Se il percorso Netlify è definitivamente
abbandonato, quel file e le tre guide dedicate vanno tolti da qui; finché la decisione non è
presa, restano marcati come non correnti.
