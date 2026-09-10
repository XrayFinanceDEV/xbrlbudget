# Lotto 3B — robustezza del client — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un 500 del backend arriva al browser come 500 (mai come blocco CORS), e CE Prev., SP Prev., Report e la tab
Indicatori dell'infrannuale non restano mai su uno spinner senza uscita: mostrano un messaggio leggibile e un modo
di ritentare.

**Architecture:** Una correzione puntuale nella catena delle middleware FastAPI (le intestazioni CORS aggiunte a
mano nella `JSONResponse` del gestore globale d'eccezione, che oggi la scavalca). Sul client, due funzioni pure
nuove in `frontend/lib/` (`forecast-page-status.ts` per le tre pagine del previsionale, `pratica-indicatori-status.ts`
per la tab Indicatori dell'infrannuale, che ha tre stati e non due) e un unico componente di rendering condiviso
(`components/budget/ForecastLoadError.tsx`), sullo stesso schema già in uso per `lib/budget-stale.ts` +
`ForecastStaleBanner.tsx`: la decisione sta nella funzione pura e testabile, il componente rende soltanto.

**Tech Stack:** FastAPI/Starlette (backend), Next.js 15 + TanStack Query v5 + TypeScript (frontend). Test: pytest
(`TestClient`) per il backend, Vitest in `environment: node` per il frontend — `jsdom` **non è installato** in
questo progetto, quindi ogni componente React nuovo resta senza una sua suite diretta; la logica sta nella funzione
pura accanto, che la suite copre.

**Spec:** `docs/superpowers/specs/2026-09-10-lotto3b-robustezza-client-design.md`

**Branch:** `feat/lotto3b-client`, da staccare da `feat/scadenziamento-pregresso` (il branch integrato del lotto 2)
dopo la sua revisione finale.

**Esecuzione (aggiornamento del proprietario, in corso d'opera dopo l'approvazione della spec):** ogni task lo
implementa **pi**, un agente coding locale lanciato via Orca (`orca-ide orchestration worker-start --agent pi`), in
un worktree Orca figlio del branch del lotto. Pi vede **solo il testo del proprio task** — non questo file intero,
non il codice che non gli viene incollato dentro — quindi ogni task qui sotto è scritto per essere autosufficiente:
percorsi assoluti, codice per intero (nuovo o come blocco vecchio/nuovo per una modifica), comandi per esteso, esiti
attesi. La revisione resta a **sonnet**. Il Task 4 (verifica di fine lotto) fa eccezione e non lo esegue pi — vedi la
sua intestazione per il perché.

## Global Constraints

*(Copiati alla lettera da §2 della spec. Dove il testo dice «implementazione e revisione su sonnet», l'aggiornamento
del proprietario sopra sostituisce l'implementazione con pi; la revisione è quella intesa.)*

- `lib/` resta testabile in `environment: node`: la logica che decide uno stato va in funzioni pure in `lib/`, che non
  importano mai da `app/` o `components/` (l'unica dipendenza ammessa verso l'alto è un `import type`).
- Un hook che restituisce un oggetto non entra intero in un array di dipendenze `useEffect`; un effetto non dipende da
  ciò che scrive (regole di `CLAUDE.md` › Frontend).
- UI in italiano, icone lucide-react, niente emoji.
- Test prima rossi (sulle asserzioni) e poi verdi; implementazione e revisione su sonnet.
- File del lotto: `backend/app/main.py`; `frontend/app/forecast/income/page.tsx`, `frontend/app/forecast/balance/page.tsx`,
  `frontend/app/report/page.tsx`; la parte Indicatori di `frontend/app/pratica/page.tsx`;
  `frontend/hooks/use-queries.ts` se serve; moduli nuovi in `frontend/lib/`. Toccare un file del 3A è un conflitto da
  segnalare, non da risolvere in silenzio.

**Deviazione dichiarata dall'elenco file qui sopra.** La spec elenca solo «moduli nuovi in `frontend/lib/`» come
aggiunta ammessa. Il componente di stato d'errore condiviso da §3.2/§3.3 della spec non può vivere in `lib/`: è JSX,
e la prima riga dei vincoli qui sopra vieta a `lib/` di importare da `components/` — il rendering sta per forza
altrove. Il Task 2 crea quindi anche `frontend/components/budget/ForecastLoadError.tsx`, esattamente sullo stesso
schema di `lib/budget-stale.ts` + `components/budget/ForecastStaleBanner.tsx` (il precedente diretto in questo
stesso repo). Non tocca alcun file del lotto 3A (che lavora su `frontend/components/budget/wizard/BudgetWizard.tsx`,
`frontend/app/budget/page.tsx`, `frontend/lib/budget-preview-notice.ts`, i servizi e i motori del previsionale):
non è quindi un conflitto — è un'estensione minima e necessaria dell'elenco, segnalata qui invece che in silenzio.

**Cartella dei rapporti di questo lotto:** `/home/peter/DEV/budget/.superpowers/sdd/2026-09-10-lotto3b-robustezza-client/`
(da creare al primo task — non esiste ancora).

---

## Come si dividono 3.2 e 3.3 (spec §3.2, §3.3, §4)

**Due task in serie (Task 2, poi Task 3), non uno solo e non in parallelo.** Un revisore deve poter accettare il
componente di stato d'errore e le tre pagine del previsionale (Task 2) indipendentemente dalla correzione della tab
Indicatori dell'infrannuale (Task 3), che tocca una porzione delicata di un file molto più grande e condiviso
(`frontend/app/pratica/page.tsx`, oltre 1900 righe) con una macchina a **tre** stati (non due:
«non generato» ed «errore» sono cose diverse, spec §3.3) e un proprio rischio di effetto-che-si-rincorre (vedi
Constraints del Task 3). In parallelo, due worktree Orca scriverebbero entrambi in prossimità di
`frontend/components/budget/ForecastLoadError.tsx`: il Task 2 lo **crea**, il Task 3 lo **importa soltanto** — se
partissero insieme, pi del Task 3 non avrebbe alcuna garanzia che il file esista già quando il proprio import lo
cerca. La sequenza elimina quel rischio senza bisogno di coordinarli a runtime: il Task 3 dichiara nella propria
intestazione che il suo worktree si apre solo dopo che il Task 2 è stato integrato nel branch del lotto.

---

## Task 1: Il 500 arriva al browser con le intestazioni CORS (spec §3.1)

**Esecutore:** pi (Orca) · **Revisore:** sonnet
**Worktree:** figlio di `feat/lotto3b-client`, apribile subito (nessuna dipendenza da altri task di questo lotto).

### Causa (stabilita leggendo il codice, e verificata con una prova rossa reale)

`backend/app/main.py:74-81` (codice di oggi):

```python
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log full traceback for any unhandled exception, then return 500."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
```

`app.add_middleware(CORSMiddleware, ...)` è registrato a `backend/app/main.py:51-57`, **prima** di questo gestore.
In Starlette, `@app.exception_handler(Exception)` diventa l'`error_handler` di `ServerErrorMiddleware` — la
middleware **più esterna** dello stack, sopra `CORSMiddleware`. La `JSONResponse` costruita qui non attraversa più
`CORSMiddleware`: per un'origine consentita (es. `http://localhost:3000`), la risposta 500 esce **senza**
`Access-Control-Allow-Origin`. Il browser la blocca e il client la vede come un errore di rete generico ("blocked by
CORS policy"), mai come il 500 che è davvero (rilievo 2 del collaudo del lotto 2,
`.superpowers/sdd/2026-09-08-scadenziamento-pregresso/task-10-report-parte1.md`, righe 319-350).

Questa causa è stata **verificata**, non solo letta: una rotta di prova che solleva sempre, aggiunta con lo stesso
meccanismo del Task, chiamata con `TestClient(app, raise_server_exceptions=False)` e `Origin: http://localhost:3000`,
oggi risponde 500 **senza** `access-control-allow-origin` in nessuna intestazione:

```
AssertionError: {'content-length': '34', 'content-type': 'application/json'}
assert None == 'http://localhost:3000'
```

(esito di una copia di verifica in scratchpad, sullo stesso commit di partenza di questo lotto — non sull'albero
principale). Il Task riproduce la stessa identica prova come test permanente del repo.

### Target

`unhandled_exception_handler` aggiunge a mano le intestazioni CORS che `CORSMiddleware` non può più iniettare a
questo punto della catena, per ogni origine presente in `cors_origins` (la stessa lista che `CORSMiddleware` già usa,
definita a `backend/app/main.py:47-49`). Il corpo e lo status restano quelli di oggi.

### Change

**File:** Modify `backend/app/main.py`.

Sostituisci il blocco esatto (righe 74-81):

```python
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log full traceback for any unhandled exception, then return 500."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
```

con:

```python
def _cors_headers_for(request: Request) -> dict:
    """Le stesse intestazioni che CORSMiddleware aggiungerebbe a una risposta riuscita,
    per un'origine consentita.

    Servono qui perche' la JSONResponse costruita da unhandled_exception_handler non
    attraversa piu' CORSMiddleware: l'exception_handler registrato su Exception diventa
    l'error_handler di ServerErrorMiddleware, la middleware piu' esterna dello stack di
    Starlette, sopra CORSMiddleware (registrato qui sopra, add_middleware). Senza queste
    intestazioni un 500 imprevisto su qualunque rotta arriva al browser come blocco CORS,
    mai come l'errore reale (CLAUDE.md > Invarianti e trappole > Frontend).
    """
    origin = request.headers.get("origin")
    if origin and origin in cors_origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return {}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Log full traceback for any unhandled exception, then return 500 —
    con le intestazioni CORS che CORSMiddleware non aggiunge piu' a questo punto
    della catena (vedi _cors_headers_for)."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=_cors_headers_for(request),
    )
```

`cors_origins` è la variabile già definita poco sopra in questo stesso file (righe 47-49: `list(settings.BACKEND_CORS_ORIGINS)` più `settings.ALLOWED_ORIGINS`), non una nuova — non ridefinirla.

**File:** Create `tests/test_cors_on_500.py`:

```python
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
```

**File:** Modify `CLAUDE.md`. Nella sezione `## Invarianti e trappole` › `### Frontend`, trova il blocco che finisce
con questo testo esatto (l'ultimo elenco puntato prima di `### Ambiente`):

```
- **Gli elenchi di codici congelati in `ivcee-catalog-parity.test.ts` non si aggiornano per far tornare verde la
  suite.** Se cambiano, una vista ha perso o riordinato una riga: è quello il
  difetto. L'unica eccezione è una riga aggiunta di proposito, che si aggiorna nello stesso commit.
  Gli elenchi di **etichette** sono un'altra cosa: lì un cambiamento deliberato è legittimo, purché
  si sappia perché il testo si è mosso.
```

Aggiungi subito dopo, come nuovo elenco puntato (stessa sezione, prima della riga vuota che precede `### Ambiente`):

```
- **Un 500 non gestito porta le intestazioni CORS**, non solo le risposte previste. `unhandled_exception_handler`
  (`backend/app/main.py`) le aggiunge a mano perché la sua `JSONResponse` non attraversa più `CORSMiddleware` — è
  l'`error_handler` di `ServerErrorMiddleware`, la middleware più esterna, sopra `CORSMiddleware`. Senza, qualunque
  bug imprevisto su qualunque rotta arriva al browser come «CORS policy», mai come l'errore reale: chi guarda la
  console per diagnosticare vede la causa sbagliata (misurato nel collaudo del lotto 2, prima di questa correzione).
  `tests/test_cors_on_500.py` lo tiene fermo.
```

### Constraints

- Vincoli globali (ripetuti qui perché pi vede solo questo task): test prima rosso poi verde; nessun dettaglio
  interno nel corpo del 500 (resta `{"detail": "Internal server error"}`); non toccare nessun altro file.
- Trappole di `CLAUDE.md` › Frontend: **non applicabile** — questo task è solo backend, nessun hook, nessun `useEffect`,
  nessun modulo `lib/`.

### Ownership

- File toccati: `backend/app/main.py`, `tests/test_cors_on_500.py`, `CLAUDE.md`.
- Nessun conflitto di file col lotto 3A su `backend/app/main.py` (non lo tocca). Il 3A tocca invece `CLAUDE.md`, in
  otto dei suoi tredici task — ma su sezioni testualmente disgiunte da questa («Forecasting Engine», «Intra-Year
  Engine», «Invarianti e trappole › Previsionale», contro «Invarianti e trappole › Frontend» qui): **il 3B, più
  piccolo, si integra per primo** nel branch verso cui i due lotti confluiscono, e il 3A — nel suo Task 13, prima
  della propria verifica di fine lotto — unisce quel branch nel proprio e rilegge le sezioni di `CLAUDE.md` toccate
  da entrambi (Global Constraints del piano 3A, «Ordine di integrazione col lotto gemello»).

### Observable acceptance

Dalla radice del worktree:

1. **Prova rossa.**
   ```
   /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_cors_on_500.py -v
   ```
   Atteso: `test_500_porta_le_intestazioni_cors_per_unorigine_consentita` **FAILED**, con
   `assert None == 'http://localhost:3000'` (o equivalente: l'header non c'è);
   `test_500_non_porta_intestazioni_cors_per_unorigine_non_consentita` **PASSED** (già vero oggi, senza CORS non c'è
   nessuna intestazione da nessuna parte).
2. **Implementazione.** Applica la modifica a `backend/app/main.py` descritta sopra in **Change**.
3. **Prova verde.**
   ```
   /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_cors_on_500.py -v
   ```
   Atteso: entrambi i test **PASSED**.
4. **Non regressione.**
   ```
   /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_auth_jwt.py -v
   ```
   Atteso: tutti **PASSED** (questo task non tocca l'autenticazione, ma modifica lo stesso file `main.py`).
5. **Documentazione.** Applica la modifica a `CLAUDE.md` descritta sopra, nello stesso commit.
6. **Chiusura.** Un solo commit:
   ```
   git add backend/app/main.py tests/test_cors_on_500.py CLAUDE.md
   git commit -m "fix(backend): un 500 non gestito porta le intestazioni CORS, non piu' un blocco CORS silenzioso"
   ```
   Scrivi il rapporto in
   `/home/peter/DEV/budget/.superpowers/sdd/2026-09-10-lotto3b-robustezza-client/task-1-report.md` con: il comando e
   l'esito testuale della prova rossa (punto 1), il comando e l'esito della prova verde (punto 3), il comando e
   l'esito del punto 4, e `git diff --stat HEAD~1 HEAD` incollato per intero.

---

## Task 2: CE Prev., SP Prev. e Report — tre stati, mai uno spinner eterno (spec §3.2)

**Esecutore:** pi (Orca) · **Revisore:** sonnet
**Worktree:** figlio di `feat/lotto3b-client`, apribile dopo il Task 1 (non dipende dal suo codice, ma sullo stesso
branch: aprirlo prima farebbe divergere `CLAUDE.md`, toccato da entrambi nello stesso punto).

### Causa: che cosa è certo, e che cosa resta un'ipotesi non verificabile da qui

**Certo, con `file:riga` (letto nel codice di oggi):**

- `frontend/app/forecast/income/page.tsx:148`:
  `const error = analysisError ? "Impossibile caricare i dati previsionali" : null;` — la stringa è **fissa**,
  scarta interamente `analysisError` (che porta `.response.data.detail` quando il backend risponde con un corpo).
  Stesso schema a `frontend/app/forecast/balance/page.tsx:149` (`"Impossibile caricare i dati previsionali"`) e
  `frontend/app/report/page.tsx:58` (`"Errore nel caricamento dell'analisi"`).
- Nessuna delle tre pagine offre un modo di ritentare la lettura se non un refresh completo del browser.
- `frontend/hooks/use-queries.ts:89-98` (`useAnalysis`) non specifica un proprio `retry`/`retryDelay`: eredita il
  default globale di `frontend/components/providers.tsx:10-17` (`retry: 1`, nessun `retryDelay` esplicito — quindi
  quello di default di TanStack Query). Nessun test fissa questo comportamento per questa query: un cambiamento
  futuro del default globale (o della sua assenza di `retryDelay`) allungherebbe la finestra di caricamento apparente
  senza che nessuna suite se ne accorga.

**Non stabilito con certezza dalla sola lettura — dichiarato, non fabbricato.** Con `retry: 1` e il backoff di
default di TanStack Query (~1 secondo prima del secondo tentativo), la lettura *dovrebbe* uscire dallo stato di
caricamento in pochi secondi e mostrare l'Alert generico di cui sopra — non uno spinner davvero senza fine. Questo
non combacia pienamente con quanto descritto nel collaudo del lotto 2 ("resta indefinitamente su Caricamento...",
`.superpowers/sdd/2026-09-08-scadenziamento-pregresso/task-10-report-parte1.md` righe 172-181). Il meccanismo esatto
di quella finestra (il doppio fetch di React StrictMode in sviluppo che si intreccia col retry, un tempo di
osservazione del collaudatore più breve dell'attesa reale, o altro) **non è verificabile da questa sede**: questo
progetto non ha un'infrastruttura per test DOM/hook (`frontend/vitest.config.ts` è `environment: "node"`, limitato a
`lib/**/*.test.ts` — nessun `jsdom`, nessun `@testing-library/react`: è una scelta esplicita del progetto, non una
lacuna da colmare in questo lotto — vedi Global Constraints), e questo task non può chiamare i server di sviluppo in
esecuzione per riprodurre dal vivo. Per questo la prova rossa del task qui sotto non riproduce il sintomo esatto del
browser: pin, con test puri, i tre difetti **certi** sopra (messaggio fisso che scarta il `detail`, nessuna azione di
retry, nessun numero di tentativi dichiarato e testato) — sono la causa comune a qualunque forma prenda il sintomo, e
la correzione (contratto sotto) li chiude tutti indipendentemente dal meccanismo esatto dell'attesa percepita.

### Target

Le tre pagine (`forecast/income`, `forecast/balance`, `report`) derivano lo stato di caricamento dalla stessa
funzione pura e rendono l'errore con lo stesso componente: un messaggio leggibile (il `detail` del backend quando
c'è, un testo italiano fisso per un errore di rete senza corpo) e un pulsante «Riprova» che rilancia la lettura. I
tentativi di `useAnalysis` diventano un numero e un'attesa espliciti, pinnati da un test.

### Change

**File:** Create `frontend/lib/forecast-page-status.ts`:

```ts
/**
 * CE Prev., SP Prev. e Report leggono tutte `useAnalysis` (`hooks/use-queries.ts`) e
 * restavano su "Caricamento..." senza alcun segnale quando `/analysis` falliva: il
 * `detail` del backend veniva scartato in favore di una stringa fissa, e non c'era modo
 * di ritentare se non un refresh completo della pagina (rilievo 3 del collaudo del lotto
 * 2, `.superpowers/sdd/2026-09-08-scadenziamento-pregresso/task-10-report-parte1.md`
 * righe 354-377).
 *
 * Le tre pagine derivano il proprio stato da qui, e rendono l'errore con
 * `components/budget/ForecastLoadError.tsx`: nessuna delle due decide da sola. Come
 * `lib/budget-stale.ts`, questo modulo resta puro e testabile in `environment: node` —
 * jsdom non e' installato in questo progetto, quindi il componente non ha una sua suite,
 * solo questa.
 */
import { getErrorMessage } from "@/lib/utils";

export type ForecastPageStatus = "caricamento" | "errore" | "pronto";

/**
 * Tentativi e attesa espliciti per `useAnalysis`: prima erano solo il default globale
 * di `components/providers.tsx` (mai testato per questa query in particolare), e un
 * cambiamento futuro di quel default avrebbe allungato la finestra di caricamento
 * apparente senza che nessuna suite se ne accorgesse.
 */
export const ANALYSIS_RETRY_COUNT = 1;
export const ANALYSIS_RETRY_DELAY_MS = 1000;

export function forecastPageStatus(loading: boolean, error: unknown): ForecastPageStatus {
  if (loading) return "caricamento";
  if (error) return "errore";
  return "pronto";
}

/**
 * Il messaggio da mostrare per un errore di caricamento previsionale.
 *
 * Un errore Axios con `.response` e' arrivato dal server: il `detail` vince
 * (`getErrorMessage`). Senza `.response` non c'e' stato alcun corpo da leggere — rete
 * giu', timeout, o (prima del Task 1 di questo lotto) un 500 che il browser bloccava
 * come CORS: in quel caso `error.message` sarebbe la stringa inglese di axios ("Network
 * Error"), quindi si usa un testo italiano fisso invece di propagarla.
 */
export function forecastLoadErrorMessage(error: unknown): string {
  const hasResponse =
    typeof error === "object" &&
    error !== null &&
    "response" in error &&
    (error as { response?: unknown }).response != null;
  if (!hasResponse) {
    return "Il server non ha risposto. Controlla la connessione e riprova.";
  }
  return getErrorMessage(error, "Impossibile caricare i dati previsionali.");
}
```

**File:** Create `frontend/lib/forecast-page-status.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import {
  ANALYSIS_RETRY_COUNT,
  ANALYSIS_RETRY_DELAY_MS,
  forecastLoadErrorMessage,
  forecastPageStatus,
} from "./forecast-page-status";

describe("forecastPageStatus", () => {
  it("in caricamento, sempre caricamento", () => {
    expect(forecastPageStatus(true, new Error("x"))).toBe("caricamento");
    expect(forecastPageStatus(true, null)).toBe("caricamento");
  });

  it("non in caricamento, con errore: errore", () => {
    expect(forecastPageStatus(false, new Error("x"))).toBe("errore");
  });

  it("non in caricamento, senza errore: pronto", () => {
    expect(forecastPageStatus(false, null)).toBe("pronto");
    expect(forecastPageStatus(false, undefined)).toBe("pronto");
  });
});

describe("forecastLoadErrorMessage", () => {
  it("usa il detail del backend quando la risposta c'e'", () => {
    const err = { response: { data: { detail: "Scoperto oltre il tetto concesso" } } };
    expect(forecastLoadErrorMessage(err)).toBe("Scoperto oltre il tetto concesso");
  });

  it("un errore di rete senza corpo ha un testo italiano fisso, mai il messaggio inglese di axios", () => {
    const networkError = new Error("Network Error");
    expect(forecastLoadErrorMessage(networkError)).toBe(
      "Il server non ha risposto. Controlla la connessione e riprova.",
    );
  });

  it("una risposta senza detail leggibile ricade sul messaggio generico italiano", () => {
    const err = { response: { data: {} } };
    expect(forecastLoadErrorMessage(err)).toBe("Impossibile caricare i dati previsionali.");
  });
});

describe("i tentativi di useAnalysis restano espliciti e finiti", () => {
  it("pin dei valori: un cambiamento qui e' una scelta, non un incidente", () => {
    expect(ANALYSIS_RETRY_COUNT).toBe(1);
    expect(ANALYSIS_RETRY_DELAY_MS).toBe(1000);
  });
});
```

**File:** Create `frontend/components/budget/ForecastLoadError.tsx`:

```tsx
"use client";

/**
 * Stato d'errore comune a CE Prev., SP Prev., Report e (dal task successivo di questo
 * lotto) alla tab Indicatori dell'infrannuale: un messaggio leggibile — mai lo spinner
 * che resta a schermo per sempre — e un modo di ritentare la stessa lettura, senza un
 * refresh completo della pagina.
 *
 * Come `ForecastStaleBanner`, rende soltanto: la decisione del messaggio sta in
 * `lib/forecast-page-status.ts` (`forecastLoadErrorMessage`), pura e testata in
 * `environment: node` — questo componente non ha una sua suite, jsdom non e' installato
 * in questo progetto.
 */
import { AlertCircle, RefreshCw } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { forecastLoadErrorMessage } from "@/lib/forecast-page-status";

export function ForecastLoadError({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry: () => void;
  className?: string;
}) {
  return (
    <Alert variant="destructive" className={className}>
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Errore</AlertTitle>
      <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <span>{forecastLoadErrorMessage(error)}</span>
        <Button variant="outline" size="sm" onClick={onRetry} className="self-start sm:self-auto">
          <RefreshCw className="h-4 w-4 mr-2" />
          Riprova
        </Button>
      </AlertDescription>
    </Alert>
  );
}
```

**File:** Modify `frontend/hooks/use-queries.ts`.

Aggiungi l'import, subito dopo gli import esistenti in cima al file (dopo `import type { BudgetScenario } from "@/types/api";`):

```ts
import { ANALYSIS_RETRY_COUNT, ANALYSIS_RETRY_DELAY_MS } from "@/lib/forecast-page-status";
```

Sostituisci il blocco esatto:

```ts
// Comprehensive scenario analysis
export function useAnalysis(
  companyId: number | null,
  scenarioId: number | null
) {
  return useQuery({
    queryKey: queryKeys.analysis(companyId!, scenarioId!),
    queryFn: () => getScenarioAnalysis(companyId!, scenarioId!),
    enabled: !!companyId && !!scenarioId,
  });
}
```

con:

```ts
// Comprehensive scenario analysis
export function useAnalysis(
  companyId: number | null,
  scenarioId: number | null
) {
  return useQuery({
    queryKey: queryKeys.analysis(companyId!, scenarioId!),
    queryFn: () => getScenarioAnalysis(companyId!, scenarioId!),
    enabled: !!companyId && !!scenarioId,
    retry: ANALYSIS_RETRY_COUNT,
    retryDelay: ANALYSIS_RETRY_DELAY_MS,
  });
}
```

**File:** Modify `frontend/app/forecast/income/page.tsx`.

Aggiungi due import, subito dopo `import { cn, getErrorMessage } from "@/lib/utils";`:

```tsx
import { forecastPageStatus } from "@/lib/forecast-page-status";
import { ForecastLoadError } from "@/components/budget/ForecastLoadError";
```

Sostituisci il blocco esatto:

```tsx
  const { data: analysisData, isLoading: analysisLoading, error: analysisError } = useAnalysis(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || analysisLoading;
  const error = analysisError ? "Impossibile caricare i dati previsionali" : null;
```

con:

```tsx
  const { data: analysisData, isLoading: analysisLoading, error: analysisError, refetch: refetchAnalysis } = useAnalysis(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || analysisLoading;
  const pageStatus = forecastPageStatus(loading, analysisError);
```

Sostituisci il blocco esatto (il blocco dell'errore, dello spinner e delle due sezioni "vuoto"/"con dati"):

```tsx
      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && (
        <div className="text-center py-12">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
          <p className="mt-4 text-muted-foreground">Caricamento...</p>
        </div>
      )}

      <ForecastStaleBanner analysis={analysisData} className="mb-6" />

      {!loading && analysisData && historicalYears.length === 0 && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Nessun dato storico trovato per l&apos;anno base dello scenario. Verifica di aver
            importato il bilancio dell&apos;anno base (e dell&apos;anno precedente) prima di
            generare il previsionale.
          </AlertDescription>
        </Alert>
      )}

      {!loading && analysisData && historicalYears.length > 0 && (
```

con:

```tsx
      {pageStatus === "errore" && (
        <ForecastLoadError error={analysisError} onRetry={() => refetchAnalysis()} className="mb-6" />
      )}

      {pageStatus === "caricamento" && (
        <div className="text-center py-12">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
          <p className="mt-4 text-muted-foreground">Caricamento...</p>
        </div>
      )}

      <ForecastStaleBanner analysis={analysisData} className="mb-6" />

      {pageStatus === "pronto" && analysisData && historicalYears.length === 0 && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Nessun dato storico trovato per l&apos;anno base dello scenario. Verifica di aver
            importato il bilancio dell&apos;anno base (e dell&apos;anno precedente) prima di
            generare il previsionale.
          </AlertDescription>
        </Alert>
      )}

      {pageStatus === "pronto" && analysisData && historicalYears.length > 0 && (
```

Il resto del file (il contenuto di quel blocco, i grafici, il resto del componente) **non cambia**: solo la
condizione d'apertura di quei due blocchi è cambiata da `!loading && analysisData && ...` a
`pageStatus === "pronto" && analysisData && ...`.

**File:** Modify `frontend/app/forecast/balance/page.tsx`.

Aggiungi due import, subito dopo `import { cn, getErrorMessage } from "@/lib/utils";`:

```tsx
import { forecastPageStatus } from "@/lib/forecast-page-status";
import { ForecastLoadError } from "@/components/budget/ForecastLoadError";
```

Sostituisci il blocco esatto:

```tsx
  const { data: analysisData, isLoading: analysisLoading, error: analysisError } = useAnalysis(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || analysisLoading;
  const error = analysisError ? "Impossibile caricare i dati previsionali" : null;
```

con:

```tsx
  const { data: analysisData, isLoading: analysisLoading, error: analysisError, refetch: refetchAnalysis } = useAnalysis(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || analysisLoading;
  const pageStatus = forecastPageStatus(loading, analysisError);
```

Sostituisci il blocco esatto:

```tsx
      {error && (
        <Alert variant="destructive" className="mb-6">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Errore</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && (
        <div className="text-center py-12">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
          <p className="mt-4 text-muted-foreground">Caricamento...</p>
        </div>
      )}

      <ForecastStaleBanner analysis={analysisData} className="mb-6" />

      {!loading && analysisData && historicalYears.length > 0 && (
```

con:

```tsx
      {pageStatus === "errore" && (
        <ForecastLoadError error={analysisError} onRetry={() => refetchAnalysis()} className="mb-6" />
      )}

      {pageStatus === "caricamento" && (
        <div className="text-center py-12">
          <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto" />
          <p className="mt-4 text-muted-foreground">Caricamento...</p>
        </div>
      )}

      <ForecastStaleBanner analysis={analysisData} className="mb-6" />

      {pageStatus === "pronto" && analysisData && historicalYears.length > 0 && (
```

Il resto del file non cambia.

**File:** Modify `frontend/app/report/page.tsx`.

Aggiungi un import, subito dopo `import { cn } from "@/lib/utils";`:

```tsx
import { forecastPageStatus } from "@/lib/forecast-page-status";
import { ForecastLoadError } from "@/components/budget/ForecastLoadError";
```

Sostituisci il blocco esatto:

```tsx
  const { data: analysisData, isLoading: analysisLoading, error: analysisError } = useAnalysis(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || analysisLoading;
  const error = analysisError ? "Errore nel caricamento dell'analisi" : null;
```

con:

```tsx
  const { data: analysisData, isLoading: analysisLoading, error: analysisError, refetch: refetchAnalysis } = useAnalysis(
    selectedCompanyId,
    selectedScenario?.id ?? null
  );
  const loading = scenariosLoading || analysisLoading;
  const pageStatus = forecastPageStatus(loading, analysisError);
```

Sostituisci il blocco esatto:

```tsx
      {error && (
        <Alert variant="destructive" className="mb-6 print:hidden">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Errore</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && (
        <Card className="mb-6 print:hidden">
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <span className="ml-3 text-muted-foreground">Caricamento analisi...</span>
          </CardContent>
        </Card>
      )}

      {!loading && !analysisData && !error && scenarios.length === 0 && (
```

con:

```tsx
      {pageStatus === "errore" && (
        <ForecastLoadError
          error={analysisError}
          onRetry={() => refetchAnalysis()}
          className="mb-6 print:hidden"
        />
      )}

      {pageStatus === "caricamento" && (
        <Card className="mb-6 print:hidden">
          <CardContent className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <span className="ml-3 text-muted-foreground">Caricamento analisi...</span>
          </CardContent>
        </Card>
      )}

      {pageStatus === "pronto" && !analysisData && scenarios.length === 0 && (
```

Il resto del file (l'Alert "Nessuno Scenario", il banner stantio, il grosso blocco `{analysisData && (...)}`)
**non cambia**.

**File:** Modify `CLAUDE.md`. Nella sezione `## Invarianti e trappole` › `### Frontend`, trova il bullet aggiunto dal
Task 1 (l'ultimo prima di `### Ambiente`, che finisce con `` `tests/test_cors_on_500.py` lo tiene fermo. ``) e
aggiungi subito dopo, come nuovo elenco puntato:

```
- **CE Prev., SP Prev. e Report non restano mai su uno spinner senza uscita quando `/analysis` fallisce.** Le tre
  pagine derivano lo stato da `lib/forecast-page-status.ts` (`caricamento`/`errore`/`pronto`, con
  `ANALYSIS_RETRY_COUNT`/`ANALYSIS_RETRY_DELAY_MS` espliciti su `useAnalysis`) e rendono l'errore con
  `components/budget/ForecastLoadError.tsx` — il `detail` del backend quando c'è, un testo italiano fisso per un
  errore di rete senza corpo, sempre con «Riprova». Una nuova pagina che legge `useAnalysis` riusa gli stessi due
  moduli, non reinventa un `if (loading)` locale: è esattamente il pattern che ha lasciato per mesi le tre pagine su
  «Caricamento...» per sempre, senza alcun segnale (collaudo del lotto 2).
```

### Constraints

- Vincoli globali: `lib/` resta testabile in `environment: node`, e non importa mai da `app/`/`components/` —
  `forecast-page-status.ts` importa solo da `@/lib/utils` (`getErrorMessage`, un altro modulo `lib/`) e da tipi; non
  aggiungere un import da `@/components/*` o `@/app/*` a quel file, per nessun motivo.
- Questo task **non aggiunge alcun `useEffect` nuovo**: la trappola «un hook che restituisce un oggetto letterale non
  va mai messo intero in un array di dipendenze `useEffect`» non si applica direttamente, ma vale comunque la
  cautela — se in fase di implementazione sembrasse necessario un effetto per il retry, non aggiungerlo: il pulsante
  «Riprova» chiama `refetchAnalysis()` **direttamente** nell'`onClick`, non tramite un effetto.
- UI in italiano, icone lucide-react, niente emoji — il componente nuovo rispetta entrambe.

### Ownership

- File toccati: `frontend/lib/forecast-page-status.ts` (nuovo), `frontend/lib/forecast-page-status.test.ts` (nuovo),
  `frontend/components/budget/ForecastLoadError.tsx` (nuovo — vedi la deviazione dichiarata nei Global Constraints),
  `frontend/hooks/use-queries.ts`, `frontend/app/forecast/income/page.tsx`, `frontend/app/forecast/balance/page.tsx`,
  `frontend/app/report/page.tsx`, `CLAUDE.md`.
- Nessun conflitto con il lotto 3A (`frontend/components/budget/wizard/BudgetWizard.tsx`, `frontend/app/budget/page.tsx`,
  `frontend/lib/budget-preview-notice.ts`, servizi e motori del previsionale — nessuno di questi file compare qui).
- `CLAUDE.md` è condiviso col Task 1: questo worktree va aperto **dopo** che il Task 1 è stato integrato nel branch
  del lotto, altrimenti l'anchor di inserimento («il bullet aggiunto dal Task 1») non esiste ancora.

### Observable acceptance

Dalla radice del worktree:

0. **Node modules del frontend** (il worktree non li ha):
   ```
   ln -s /home/peter/DEV/budget/frontend/node_modules frontend/node_modules
   ```
1. **Prova rossa.**
   ```
   cd frontend && npx vitest run lib/forecast-page-status
   ```
   Atteso: **FAIL** — il modulo `./forecast-page-status` non esiste ancora (errore di risoluzione import).
2. **Implementazione.** Crea `forecast-page-status.ts`, poi applica tutte le altre modifiche descritte in **Change**
   (componente, `use-queries.ts`, le tre pagine, `CLAUDE.md`).
3. **Prova verde.**
   ```
   cd frontend && npx vitest run lib/forecast-page-status
   ```
   Atteso: tutti i test **PASS** (10 asserzioni in 4 blocchi `describe`).
4. **Controlli.**
   ```
   cd frontend && npx tsc --noEmit
   cd frontend && npm run lint
   ```
   Atteso: entrambi puliti (nessun errore nuovo attribuibile ai file toccati da questo task).
5. **Chiusura.** Un solo commit:
   ```
   git add frontend/lib/forecast-page-status.ts frontend/lib/forecast-page-status.test.ts \
     frontend/components/budget/ForecastLoadError.tsx frontend/hooks/use-queries.ts \
     frontend/app/forecast/income/page.tsx frontend/app/forecast/balance/page.tsx \
     frontend/app/report/page.tsx CLAUDE.md
   git commit -m "fix(frontend): CE Prev., SP Prev. e Report escono dal caricamento con un errore leggibile e Riprova"
   ```
   Scrivi il rapporto in
   `/home/peter/DEV/budget/.superpowers/sdd/2026-09-10-lotto3b-robustezza-client/task-2-report.md` con: comando ed
   esito della prova rossa, comando ed esito della prova verde, esito di `tsc`/`lint`, e
   `git diff --stat HEAD~1 HEAD` incollato per intero.

---

## Task 3: Indicatori dell'infrannuale — errore e proiezione mancante sono due cose (spec §3.3)

**Esecutore:** pi (Orca) · **Revisore:** sonnet
**Worktree:** figlio di `feat/lotto3b-client`, apribile **solo dopo** che il Task 2 è stato integrato nel branch del
lotto (questo task importa `components/budget/ForecastLoadError.tsx`, creato dal Task 2 — vedi «Come si dividono 3.2
e 3.3» sopra).

### Causa (stabilita leggendo il codice, con certezza — `file:riga`)

`frontend/app/pratica/page.tsx:924-938` (codice di oggi):

```tsx
  // STEP 4: Load Analysis
  const loadAnalysis = useCallback(async () => {
    if (!importResult || !scenario) return;

    setLoadingAnalysis(true);
    try {
      const data = await getScenarioAnalysis(importResult.companyId, scenario.id);
      setAnalysis(data);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel caricamento analisi";
      toast.error(msg);
    } finally {
      setLoadingAnalysis(false);
    }
  }, [importResult, scenario]);
```

Su un fallimento, questo mostra **solo un toast** (che scompare da solo) e lascia `analysis` a `null` — esattamente
come prima della chiamata. Non esiste alcuno stato che distingua «non ho ancora tentato / la proiezione non esiste»
da «ho tentato e la lettura è fallita».

Il render, a `frontend/app/pratica/page.tsx:1877-1954` (STEP 4: INDICATORI), collassa quei due casi sullo stesso
messaggio:

```tsx
        {/* STEP 4: INDICATORI */}
        {activeTab === "results" && <div className="space-y-6">
          {loadingAnalysis ? (
            <Card>...</Card>
          ) : analysis && comparison ? (
            <>...</>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-muted-foreground">
                  Genera prima la proiezione nel passaggio 3.
                </p>
              </CardContent>
            </Card>
          )}
        </div>}
```

`analysis && comparison` è falso sia quando non è mai stata generata una proiezione, sia quando `getScenarioAnalysis`
ha appena sollevato un'eccezione: in entrambi i casi si finisce sull'ultimo ramo. Verificato anche il lato server
(`backend/app/services/analysis_service.py:99`): `GET /analysis` risponde **200** con `forecast_years: []` quando
non esiste ancora alcun `ForecastYear` — non solleva. Quindi la distinzione corretta fra «non generato» ed «errore»
non è «`analysis` è `null`» (che oggi succede in entrambi i casi per motivi diversi), ma la **lunghezza** di
`analysis.forecast_years` **una volta che la lettura è andata a buon fine**: con un `analysisError` che oggi non
esiste, «non generato» diventa `analysis !== null && analysis.forecast_years.length === 0`, ed «errore» diventa
`analysisError !== null` — due condizioni realmente distinte, non la stessa condizione letta due volte. Questo
combacia esattamente col rilievo 4 del collaudo del lotto 2 (righe 380-403 dello stesso report citato sopra): lo
scenario aveva un `ForecastYear` già presente nel database (`forecast_years` con una riga per `scenario_id=5`), ma lo
schermo mostrava comunque «Genera prima la proiezione», perché la vera causa era un fallimento di lettura scambiato
per stato vuoto.

### Target

La tab Indicatori dell'infrannuale (`activeTab === "results"`) distingue tre stati — caricamento, errore di lettura,
proiezione non ancora generata — più lo stato "pronto"; l'errore usa lo stesso componente del Task 2
(`ForecastLoadError`), con «Riprova» che richiama `loadAnalysis`.

### Change

**File:** Create `frontend/lib/pratica-indicatori-status.ts`:

```ts
/**
 * Indicatori dell'infrannuale (tab «Indicatori» del percorso Pratica): tre stati
 * distinti, non due. `app/pratica/page.tsx` collassava "lettura fallita" e "proiezione
 * non ancora generata" sullo stesso messaggio ("Genera prima la proiezione nel
 * passaggio 3."), perche' in entrambi i casi `analysis` restava `null` — un errore di
 * rete veniva riletto come "l'utente non ha ancora fatto il passo 3" (rilievo 4 del
 * collaudo del lotto 2,
 * `.superpowers/sdd/2026-09-08-scadenziamento-pregresso/task-10-report-parte1.md`
 * righe 380-403).
 *
 * `GET /analysis` risponde 200 con `forecast_years: []` quando non e' stata ancora
 * generata alcuna proiezione (non solleva, `backend/app/services/analysis_service.py:99`):
 * la distinzione fra "non generato" e "letto ma vuoto" e' quindi la lunghezza di
 * `forecast_years`, non l'assenza di `analysis`.
 */
import type { IntraYearComparison, ScenarioAnalysis } from "@/types/api";

export type PraticaIndicatoriStatus = "caricamento" | "errore" | "non_generato" | "pronto";

export function praticaIndicatoriStatus(input: {
  loading: boolean;
  error: unknown;
  analysis: ScenarioAnalysis | null;
  comparison: IntraYearComparison | null;
}): PraticaIndicatoriStatus {
  if (input.loading) return "caricamento";
  if (input.error) return "errore";
  if (input.analysis && input.comparison && (input.analysis.forecast_years?.length ?? 0) > 0) {
    return "pronto";
  }
  return "non_generato";
}
```

**File:** Create `frontend/lib/pratica-indicatori-status.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { praticaIndicatoriStatus } from "./pratica-indicatori-status";
import type { IntraYearComparison, ScenarioAnalysis } from "@/types/api";

const COMPARISON = {} as unknown as IntraYearComparison;
const ANALYSIS_VUOTO = { forecast_years: [] } as unknown as ScenarioAnalysis;
const ANALYSIS_PIENO = { forecast_years: [{}] } as unknown as ScenarioAnalysis;

describe("praticaIndicatoriStatus", () => {
  it("in caricamento vince su tutto", () => {
    expect(
      praticaIndicatoriStatus({ loading: true, error: "x", analysis: ANALYSIS_PIENO, comparison: COMPARISON }),
    ).toBe("caricamento");
  });

  it("un errore di lettura e' distinto da nessuna proiezione", () => {
    // L'errore e' quello grezzo (vedi lib/forecast-page-status.ts), non un
    // messaggio gia' risolto: qui basta un valore truthy qualunque.
    expect(
      praticaIndicatoriStatus({
        loading: false,
        error: new Error("Network Error"),
        analysis: null,
        comparison: COMPARISON,
      }),
    ).toBe("errore");
  });

  it("nessun ForecastYear, nessun errore: invita al passo 3", () => {
    expect(
      praticaIndicatoriStatus({ loading: false, error: null, analysis: ANALYSIS_VUOTO, comparison: COMPARISON }),
    ).toBe("non_generato");
    expect(
      praticaIndicatoriStatus({ loading: false, error: null, analysis: null, comparison: COMPARISON }),
    ).toBe("non_generato");
  });

  it("dati e comparison presenti, forecast_years non vuoto: pronto", () => {
    expect(
      praticaIndicatoriStatus({ loading: false, error: null, analysis: ANALYSIS_PIENO, comparison: COMPARISON }),
    ).toBe("pronto");
  });

  it("senza comparison non e' mai pronto, anche con forecast_years pieno", () => {
    expect(
      praticaIndicatoriStatus({ loading: false, error: null, analysis: ANALYSIS_PIENO, comparison: null }),
    ).toBe("non_generato");
  });
});
```

**File:** Modify `frontend/app/pratica/page.tsx`.

Aggiungi due import, vicino agli altri import di libreria (accanto a dove sta già
`import { IndicatoriTable } from "@/components/pratica/IndicatoriTable";`):

```tsx
import { ForecastLoadError } from "@/components/budget/ForecastLoadError";
import { forecastLoadErrorMessage } from "@/lib/forecast-page-status";
import { praticaIndicatoriStatus } from "@/lib/pratica-indicatori-status";
```

Aggiungi uno stato nuovo, subito dopo la riga esatta (vicino a `const [analysis, setAnalysis] = useState<ScenarioAnalysis | null>(null);`):

```tsx
  const [analysis, setAnalysis] = useState<ScenarioAnalysis | null>(null);
```

diventa:

```tsx
  const [analysis, setAnalysis] = useState<ScenarioAnalysis | null>(null);
  const [analysisError, setAnalysisError] = useState<unknown>(null);
```

(`unknown`, non `string | null`: `ForecastLoadError` risolve il messaggio da solo — via `forecastLoadErrorMessage`,
importata sopra — a partire dall'errore **grezzo**. Se qui si salvasse già una stringa risolta, il componente la
farebbe passare una seconda volta per `forecastLoadErrorMessage`, che su una stringa qualunque non riconosce
`.response` e ricadrebbe sempre sul testo fisso di rete, buttando via il `detail` vero già estratto. Lo stesso vale
per `praticaIndicatoriStatus`, che dichiara `error: unknown` per lo stesso motivo — non serve altro che un
controllo di verità, `unknown` gli basta.)

Sostituisci il blocco esatto (`loadAnalysis`):

```tsx
  // STEP 4: Load Analysis
  const loadAnalysis = useCallback(async () => {
    if (!importResult || !scenario) return;

    setLoadingAnalysis(true);
    try {
      const data = await getScenarioAnalysis(importResult.companyId, scenario.id);
      setAnalysis(data);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : "Errore nel caricamento analisi";
      toast.error(msg);
    } finally {
      setLoadingAnalysis(false);
    }
  }, [importResult, scenario]);
```

con:

```tsx
  // STEP 4: Load Analysis
  const loadAnalysis = useCallback(async () => {
    if (!importResult || !scenario) return;

    setLoadingAnalysis(true);
    setAnalysisError(null);
    try {
      const data = await getScenarioAnalysis(importResult.companyId, scenario.id);
      setAnalysis(data);
    } catch (error: unknown) {
      setAnalysisError(error);
      toast.error(forecastLoadErrorMessage(error));
    } finally {
      setLoadingAnalysis(false);
    }
  }, [importResult, scenario]);
```

`analysisError` prende l'errore **grezzo** (`error`, non un messaggio già risolto): `forecastLoadErrorMessage`
serve solo per il testo del toast qui, e `ForecastLoadError` la richiama da sé con lo stesso errore grezzo quando
rende lo stato `"errore"` — vedi la nota sopra sul perché non va salvata una stringa già risolta.

**Non toccare** l'effetto subito sotto (`useEffect(() => { if ((activeTab === "results" || ...`) — le sue dipendenze
restano `[activeTab, analysis, scenario, loadAnalysis]`, invariate. Vedi Constraints qui sotto sul perché.

Sostituisci il blocco esatto (il render della tab Indicatori, «STEP 4: INDICATORI» — dalla riga di apertura del
`div` fino alla sua chiusura):

```tsx
        {/* STEP 4: INDICATORI */}
        {activeTab === "results" && <div className="space-y-6">
          {loadingAnalysis ? (
            <Card>
              <CardContent className="py-12 text-center">
                <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
                <p className="mt-2 text-muted-foreground">Caricamento indicatori...</p>
              </CardContent>
            </Card>
          ) : analysis && comparison ? (
            <>
              <ExtraAccountingAlerts alerts={extraAlerts} onChange={(a) => { setExtraAlerts(a); setRatingVisible(false); }} />

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Indicatori Finanziari</CardTitle>
                  <CardDescription>
                    {periodMonths === 12
                      ? `Confronto: storico ${comparison.reference_year}, infrannuale 12M ${comparison.partial_year}`
                      : `Confronto: storico ${comparison.reference_year}, infrannuale ${comparison.period_months}M ${comparison.partial_year} (annualizzato), proiezione 12M ${comparison.partial_year}`}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <IndicatoriTable
                    comparison={comparison}
                    forecastBs={analysis.forecast_years?.[0]?.balance_sheet || {}}
                    forecastIs={analysis.forecast_years?.[0]?.income_statement || {}}
                    extraAlerts={extraAlerts}
                    showRating={ratingVisible}
                    hideProiezione={periodMonths === 12}
                  />
                </CardContent>
              </Card>

              {!ratingVisible && (
                <div className="flex justify-center">
                  <AlertDialog open={showNoAlertsConfirm} onOpenChange={setShowNoAlertsConfirm}>
                    <AlertDialogTrigger asChild>
                      <Button onClick={() => {
                        const hasAlerts = Object.values(extraAlerts).some(Boolean);
                        if (hasAlerts) {
                          setRatingVisible(true);
                        } else {
                          setShowNoAlertsConfirm(true);
                        }
                      }}>
                        <BarChart3 className="h-4 w-4 mr-2" />
                        Calcola Rating
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Segnali Extracontabili</AlertDialogTitle>
                        <AlertDialogDescription>
                          Conferma che non ci sono segnali extra contabili della crisi
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Annulla</AlertDialogCancel>
                        <AlertDialogAction onClick={() => { setShowNoAlertsConfirm(false); setRatingVisible(true); }}>
                          Conferma
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="py-12 text-center">
                <p className="text-muted-foreground">
                  Genera prima la proiezione nel passaggio 3.
                </p>
              </CardContent>
            </Card>
          )}
        </div>}
```

con:

```tsx
        {/* STEP 4: INDICATORI */}
        {activeTab === "results" && <div className="space-y-6">
          {(() => {
            const indicatoriStatus = praticaIndicatoriStatus({
              loading: loadingAnalysis,
              error: analysisError,
              analysis,
              comparison,
            });

            if (indicatoriStatus === "caricamento") {
              return (
                <Card>
                  <CardContent className="py-12 text-center">
                    <Loader2 className="h-8 w-8 mx-auto animate-spin text-muted-foreground" />
                    <p className="mt-2 text-muted-foreground">Caricamento indicatori...</p>
                  </CardContent>
                </Card>
              );
            }

            if (indicatoriStatus === "errore") {
              return <ForecastLoadError error={analysisError} onRetry={loadAnalysis} />;
            }

            if (indicatoriStatus === "non_generato") {
              return (
                <Card>
                  <CardContent className="py-12 text-center">
                    <p className="text-muted-foreground">
                      Genera prima la proiezione nel passaggio 3.
                    </p>
                  </CardContent>
                </Card>
              );
            }

            return (
              <>
                <ExtraAccountingAlerts alerts={extraAlerts} onChange={(a) => { setExtraAlerts(a); setRatingVisible(false); }} />

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Indicatori Finanziari</CardTitle>
                    <CardDescription>
                      {periodMonths === 12
                        ? `Confronto: storico ${comparison!.reference_year}, infrannuale 12M ${comparison!.partial_year}`
                        : `Confronto: storico ${comparison!.reference_year}, infrannuale ${comparison!.period_months}M ${comparison!.partial_year} (annualizzato), proiezione 12M ${comparison!.partial_year}`}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <IndicatoriTable
                      comparison={comparison!}
                      forecastBs={analysis!.forecast_years?.[0]?.balance_sheet || {}}
                      forecastIs={analysis!.forecast_years?.[0]?.income_statement || {}}
                      extraAlerts={extraAlerts}
                      showRating={ratingVisible}
                      hideProiezione={periodMonths === 12}
                    />
                  </CardContent>
                </Card>

                {!ratingVisible && (
                  <div className="flex justify-center">
                    <AlertDialog open={showNoAlertsConfirm} onOpenChange={setShowNoAlertsConfirm}>
                      <AlertDialogTrigger asChild>
                        <Button onClick={() => {
                          const hasAlerts = Object.values(extraAlerts).some(Boolean);
                          if (hasAlerts) {
                            setRatingVisible(true);
                          } else {
                            setShowNoAlertsConfirm(true);
                          }
                        }}>
                          <BarChart3 className="h-4 w-4 mr-2" />
                          Calcola Rating
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Segnali Extracontabili</AlertDialogTitle>
                          <AlertDialogDescription>
                            Conferma che non ci sono segnali extra contabili della crisi
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Annulla</AlertDialogCancel>
                          <AlertDialogAction onClick={() => { setShowNoAlertsConfirm(false); setRatingVisible(true); }}>
                            Conferma
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                )}
              </>
            );
          })()}
        </div>}
```

(`comparison!`/`analysis!` sono corretti qui: il ramo `"pronto"` della funzione pura garantisce già che entrambi non
siano `null`, esattamente come la condizione `analysis && comparison` di oggi garantiva la stessa cosa al codice che
seguiva.)

**File:** Modify `CLAUDE.md`. Nella sezione `## Invarianti e trappole` › `### Frontend`, trova il bullet aggiunto dal
Task 2 e aggiungi, **alla fine dello stesso paragrafo** (non un nuovo bullet), questa frase:

testo di oggi (fine del bullet aggiunto dal Task 2):
```
  «Caricamento...» per sempre, senza alcun segnale (collaudo del lotto 2).
```

diventa:
```
  «Caricamento...» per sempre, senza alcun segnale (collaudo del lotto 2). La tab Indicatori dell'infrannuale
  (`app/pratica/page.tsx`) riusa lo stesso componente ma la propria funzione pura,
  `lib/pratica-indicatori-status.ts`, perché lì un errore di lettura e una proiezione mai generata sono due cose
  diverse — prima collassavano sullo stesso messaggio («Genera prima la proiezione nel passaggio 3.»), anche quando
  la proiezione esisteva già.
```

### Constraints

- Vincoli globali: `lib/` resta testabile in `environment: node`, e non importa mai da `app/`/`components/` —
  `pratica-indicatori-status.ts` importa solo da `@/types/api` (tipi); non aggiungere un import da `@/components/*`
  o `@/app/*` a quel file.
- **Trappola concreta di questo task — un effetto non dipende da ciò che scrive.** L'effetto esistente a
  `frontend/app/pratica/page.tsx` (subito dopo `loadAnalysis`):
  ```tsx
  useEffect(() => {
    if ((activeTab === "results" || activeTab === "stampa") && !analysis && scenario) {
      loadAnalysis();
    }
  }, [activeTab, analysis, scenario, loadAnalysis]);
  ```
  ha come dipendenze `activeTab`, `analysis`, `scenario`, `loadAnalysis` — **mai** `analysisError`. Questo task
  aggiunge `setAnalysisError(...)` **dentro** `loadAnalysis`, ma `loadAnalysis` resta nelle dipendenze di
  quell'effetto esattamente come oggi (la sua identità di `useCallback` non cambia: le sue dipendenze restano
  `[importResult, scenario]`). Se `analysisError` finisse in quell'array di dipendenze, un fallimento setterebbe
  `analysisError`, l'effetto si ri-innescherebbe (perché una delle sue dipendenze è cambiata), rilancerebbe
  `loadAnalysis()`, che fallirebbe di nuovo, resetterebbe `analysisError` a un valore nuovo (anche uguale per
  contenuto ma comunque una nuova stringa) — non un ciclo garantito ma un rischio concreto e un retry automatico non
  voluto. **Non aggiungere `analysisError` a quell'array.** Il pulsante «Riprova» del componente
  `ForecastLoadError` chiama `loadAnalysis` **direttamente** (`onRetry={loadAnalysis}`), mai attraverso l'effetto.
- Non toccare nessun'altra parte di `frontend/app/pratica/page.tsx` oltre a: l'import nuovo, lo stato
  `analysisError`, il corpo di `loadAnalysis`, e il blocco JSX «STEP 4: INDICATORI» — è un file condiviso da molte
  altre viste (Anagrafiche, Import, Rettifiche, Confronto, Proiezione, Stampa) che questo lotto non deve toccare.

### Ownership

- File toccati: `frontend/lib/pratica-indicatori-status.ts` (nuovo),
  `frontend/lib/pratica-indicatori-status.test.ts` (nuovo), `frontend/app/pratica/page.tsx` (solo le porzioni
  indicate sopra), `CLAUDE.md`.
- Nessun conflitto con il lotto 3A (stesso elenco del Task 2). `frontend/app/pratica/page.tsx` non è nell'elenco
  esplicito di file del lotto in §2 della spec, che dice «la parte Indicatori di
  `frontend/app/pratica/page.tsx`» — questo task rispetta quel confine restando dentro le quattro porzioni elencate
  sopra in Constraints.
- Dipende dal Task 2 (importa `components/budget/ForecastLoadError.tsx` e
  `lib/forecast-page-status.ts::forecastLoadErrorMessage`, entrambi creati lì): apri questo worktree solo dopo che
  il Task 2 è stato integrato nel branch del lotto.

### Observable acceptance

Dalla radice del worktree:

0. **Node modules del frontend:**
   ```
   ln -s /home/peter/DEV/budget/frontend/node_modules frontend/node_modules
   ```
1. **Prova rossa.**
   ```
   cd frontend && npx vitest run lib/pratica-indicatori-status
   ```
   Atteso: **FAIL** — il modulo `./pratica-indicatori-status` non esiste ancora.
2. **Implementazione.** Crea `pratica-indicatori-status.ts`, poi applica le modifiche a `pratica/page.tsx` e
   `CLAUDE.md` descritte in **Change**, esattamente nelle quattro porzioni indicate.
3. **Prova verde.**
   ```
   cd frontend && npx vitest run lib/pratica-indicatori-status
   ```
   Atteso: tutti i test **PASS** (5 casi).
4. **Controlli.**
   ```
   cd frontend && npx tsc --noEmit
   cd frontend && npm run lint
   ```
   Atteso: entrambi puliti — in particolare, nessun errore su `comparison!`/`analysis!` (il narrowing della funzione
   pura non è visibile a `tsc` dentro il ramo `"pronto"`, quindi l'asserzione `!` è necessaria e intenzionale, non un
   errore da correggere).
5. **Chiusura.** Un solo commit:
   ```
   git add frontend/lib/pratica-indicatori-status.ts frontend/lib/pratica-indicatori-status.test.ts \
     frontend/app/pratica/page.tsx CLAUDE.md
   git commit -m "fix(frontend): la tab Indicatori dell'infrannuale distingue un errore di lettura da nessuna proiezione"
   ```
   Scrivi il rapporto in
   `/home/peter/DEV/budget/.superpowers/sdd/2026-09-10-lotto3b-robustezza-client/task-3-report.md` con: comando ed
   esito della prova rossa, comando ed esito della prova verde, esito di `tsc`/`lint`, e
   `git diff --stat HEAD~1 HEAD` incollato per intero.

---

## Task 4: Verifica di fine lotto (spec §5)

**Esecutore:** coordinatore (sonnet) per le suite e `/riallinea`; l'agente `collaudatore` per il collaudo a
schermo — **non pi**. Questo task non produce un commit di codice nuovo (verifica quello che i Task 1-3 hanno già
prodotto e integrato) e ha bisogno dei due server di sviluppo avviati sul branch **integrato** del lotto, non di un
worktree Orca isolato che vede solo un task: la premessa stessa del modello «pi in un worktree figlio, autosufficiente»
non regge per un compito che deve guidare un browser reale contro un ambiente condiviso.
**Revisore:** il proprietario (gate finale del lotto).

**Prerequisito:** i Task 1, 2 e 3 sono integrati in `feat/lotto3b-client`.

### 1. Suite intere

Dalla radice del repository, branch `feat/lotto3b-client` integrato:

```
/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/ -v
```
Atteso: tutti **PASS**, incluso `tests/test_cors_on_500.py` (Task 1).

```
cd frontend && npx vitest run
```
Atteso: tutti **PASS**, inclusi `lib/forecast-page-status.test.ts` e `lib/pratica-indicatori-status.test.ts`.

```
cd frontend && npx tsc --noEmit
cd frontend && npm run lint
```
Atteso: entrambi puliti.

### 2. Collaudo a schermo con un errore del backend provocato di proposito

**Come provocare un 500 vero in sviluppo, senza toccare una riga di codice applicativo.** Ferma il backend di
sviluppo se è in esecuzione, poi riavvialo puntando `DATABASE_PATH` a un file che non esiste:

```
cd backend && source venv/bin/activate
DATABASE_PATH=/tmp/inesistente-collaudo-lotto3b.db DEV_USER_ID=dev-user-001 \
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Qualunque rotta che tocca il database — praticamente tutte, incluso `/analysis` — risponde 500 al primo tentativo
di apertura della connessione: è un guasto reale (il file non esiste), non simulato a mano nel codice, e
completamente reversibile — `Ctrl+C` e riavvia senza `DATABASE_PATH` (o col valore giusto) per tornare alla
normalità.

Con il frontend (`cd frontend && npm run dev`) puntato su questo backend rotto, dispatcha l'agente `collaudatore`
per verificare, su ciascuna delle quattro superfici toccate da questo lotto:

- `/forecast/income` (CE Prev.)
- `/forecast/balance` (SP Prev.)
- `/report` (Report)
- `/pratica` → tab Indicatori, su uno scenario infrannuale con una proiezione già generata in un run precedente (per
  verificare che, con l'ambiente rotto, lo stato sia «errore» e **non** «Genera prima la proiezione», che sarebbe di
  nuovo il messaggio falso del rilievo 4)

Per ciascuna: un messaggio leggibile (non la stringa fissa di prima, non l'inglese di axios), il pulsante «Riprova»
presente. Poi riavvia il backend con `DATABASE_PATH` corretto (o senza), premi «Riprova» su ciascuna pagina senza
ricaricare il browser, e verifica che i dati compaiano — la stessa identica pagina di prima di questo lotto, con
dati sani.

### 3. `/riallinea`

Sul diff completo del lotto (`feat/lotto3b-client` rispetto al suo punto di partenza), lancia la skill `riallinea`
per verificare che `CLAUDE.md` e la memoria non abbiano affermazioni che questo lotto ha reso false, oltre ai due
bullet aggiunti dai Task 1 e 2/3.

### Chiusura del task

Nessun commit di codice da questo task. Scrivi un rapporto in
`/home/peter/DEV/budget/.superpowers/sdd/2026-09-10-lotto3b-robustezza-client/task-4-report.md` con: l'esito delle
tre suite (punto 1), il rapporto del collaudo a schermo del punto 2 (comprese eventuali osservazioni non conformi),
e l'esito di `/riallinea` (punto 3).
