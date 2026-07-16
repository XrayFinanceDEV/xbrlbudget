# 04 — Integrazione con apiServerIt (Formula Finance, piattaforma padre)

Analisi dello staging `https://api.kpsfinanciallab.it/apiServerIt` (OpenAPI: **95 endpoint**, 88 autenticati OAuth2 password-flow, 7 pubblici) e del repo privato `AndreiPy13/api_server_it` (FastAPI + PostgreSQL + Alembic; aree: users, licenses, reports, report-sessions-v2, executive-v2, modules, hooks Supabase, user_relationships, training, onboarding, user_files).

**Fatto chiave: xbrlbudget non chiama NESSUN endpoint di apiServerIt.** L'accoppiamento è solo implicito: stesso progetto Supabase → stesso claim `sub` → stesso `user_id`. Il padre non ha alcun riferimento a "budget" nel codice: l'iframe vive nel frontend Formula Finance (repo separato). Quindi nessuna incongruenza di endpoint è possibile — ma nemmeno esiste un contratto formale tra le piattaforme. Interventi in ordine di priorità:

---

## B1 — Nessun enforcement licenze (gap di prodotto)

apiServerIt ha un sistema completo licenses/modules (`GET/PUT/DELETE /api/v1/licenses/*`, CRUD moduli), ma xbrlbudget accetta **qualsiasi JWT Supabase valido** del progetto condiviso: un utente Formula Finance senza licenza "budget" può usare l'app (fino a 50 aziende).

**Fix (se il modello commerciale lo richiede — decisione di business, da confermare con il titolare).**
- Opzione leggera: claim custom nel JWT (il padre aggiunge `app_metadata.modules` ai token Supabase) → `backend/app/core/auth.py` verifica la presenza del modulo budget. Zero chiamate di rete, si aggiorna al refresh del token.
- Opzione robusta: `auth.py` chiama `GET /api/v1/licenses/user/{user_id}` di apiServerIt (con caching TTL ~5 min) e nega l'accesso senza licenza. Richiede un token di servizio.

## B2 — Flow 401 senza retry (bug UX reale)

`frontend/lib/api.ts:40-48`: su 401 il frontend rilancia `REQUEST_AUTH_TOKEN` al parent ma **non riaccoda la richiesta fallita** → l'utente vede l'errore finché non riprova a mano. Il token Supabase dura ~1h: capita ogni sessione lunga.

**Fix.** Interceptor con coda: su 401, sospendere le richieste, chiedere il token, e al ricevimento di `AUTH_TOKEN` (AuthContext) ritentare la richiesta originale una volta. Pattern standard axios (refresh-queue). Inoltre: gestione proattiva della scadenza leggendo `exp` dal JWT e richiedendo il token ~5 min prima.

## B3 — Origin-check disattivabile silenziosamente

`frontend/contexts/AuthContext.tsx:54`: se `NEXT_PUBLIC_PARENT_ORIGIN` manca al build (è un build-arg Docker), il listener postMessage accetta token da **qualsiasi** origin. Difesa residua: solo il CSP `frame-ancestors` di nginx (`nginx/default.conf:18`).

**Fix.** Fail-safe invece di fail-open: se l'env var manca, accettare SOLO le due origin note hardcoded (`app.formulafinance.it`, `app.kpsfinanciallab.it`) e loggare un errore in console — mai il wildcard. Inoltre `lib/api.ts:44` invia `REQUEST_AUTH_TOKEN` con target `'*'`: usare l'origin configurata.

## B4 — JWT HS256 legacy shared-secret

`backend/app/core/auth.py:43-48`: solo HS256 col legacy JWT secret Supabase (condiviso tra più sistemi via Jenkins), `verify_aud` disattivato. Supabase sta deprecando il legacy secret in favore di chiavi asimmetriche (JWKS/ES256): la migrazione del progetto Supabase **romperebbe il login di xbrlbudget**.

**Fix.** Supportare entrambi: prima tentare validazione JWKS (endpoint `.well-known/jwks.json` del progetto Supabase, cache delle chiavi), fallback HS256 finché il legacy secret esiste. Riattivare `verify_aud` (`aud=authenticated`). Coordinare col padre la data di switch.

## B5 — Config e doc stale (footgun documentale)

`frontend/.env.production`, `.env.example:7`, `runtime.txt:3`, `backend/start_https.bat` e 4 doc di deployment (NETLIFY_CHECKLIST, PRODUCTION_CONFIG, …) puntano al **vecchio deploy** `kpsfinanciallab.w3pro.it:8001` (era Netlify). Il deploy reale (Jenkins+Docker+nginx) usa URL relativi. Non rompe nulla oggi (il Dockerfile neutralizza con `NEXT_PUBLIC_API_URL=""`), ma chi segue quelle guide punta a un backend morto.

**Fix.** Ripulire: aggiornare `.env.example` ai soli valori correnti, rimuovere/archiviare le doc Netlify in `docs/deployment/archive/`, cancellare `.env.production` dal repo (i valori veri li mette Jenkins).

## B6 — `DEV_USER_ID` senza guard-rail

`backend/app/core/auth.py:74-75`: se `DEV_USER_ID` finisse settato in produzione, ogni richiesta senza header diventerebbe un utente fisso. Oggi non è nel `.env.docker` di Jenkins (ok) ma nulla lo vieta.

**Fix.** In `auth.py`: rifiutare `DEV_USER_ID` quando `SUPABASE_JWT_SECRET` è configurato (o quando `DEBUG=false`), con log di startup esplicito.
