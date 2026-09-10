# Lotto 3B — robustezza del client

**Data:** 2026-09-10 · **Stato:** design approvato in chat dal proprietario, spec da rileggere
**Branch:** da staccare dal branch integrato del lotto 2 (`feat/scadenziamento-pregresso`) quando si implementa
**Lotto gemello:** [3A — motori e rendiconto](2026-09-10-lotto3a-motori-rendiconto-design.md), in parallelo
**Origine:** rilievi 2, 3 e 4 del collaudo del lotto 2
(`.superpowers/sdd/2026-09-08-scadenziamento-pregresso/task-10-report-parte1.md`, righe 143-222 e 319-406), emersi
quando il DB di sviluppo non migrato faceva rispondere 500 a ogni `/analysis`.

## 1. Perché

Un errore del backend oggi non arriva mai all'utente come errore. Il browser vede un «blocco CORS» invece di un 500;
tre pagine del previsionale restano su «Caricamento...» per sempre; la tab Indicatori dell'infrannuale dice di generare
una proiezione che esiste già. In produzione, dentro l'iframe, l'utente vede uno spinner eterno o un'indicazione falsa,
e nessuno sa che c'è un guasto.

**Fuori da questo lotto:** i messaggi del motore in italiano, la gestione del 422 del bulk, `saveNotice` e il wizard del
budget (tutti nel 3A). Nessun cambiamento ai motori o ai servizi del previsionale.

## 2. Vincoli globali

- `lib/` resta testabile in `environment: node`: la logica che decide uno stato va in funzioni pure in `lib/`, che non
  importano mai da `app/` o `components/` (l'unica dipendenza ammessa verso l'alto è un `import type`).
- Un hook che restituisce un oggetto non entra intero in un array di dipendenze `useEffect`; un effetto non dipende da
  ciò che scrive (regole di `CLAUDE.md` › Frontend).
- UI in italiano, icone lucide-react, niente emoji.
- Test prima rossi (sulle asserzioni) e poi verdi. **Esecutore pi, revisore Claude sonnet** (decisione del
  proprietario, 2026-09-10).
- File del lotto: `backend/app/main.py`; `frontend/app/forecast/income/page.tsx`, `frontend/app/forecast/balance/page.tsx`,
  `frontend/app/report/page.tsx`; la parte Indicatori di `frontend/app/pratica/page.tsx`;
  `frontend/hooks/use-queries.ts` se serve; moduli nuovi in `frontend/lib/`. Toccare un file del 3A è un conflitto da
  segnalare, non da risolvere in silenzio.

## 3. Il design

### 3.1 Un 500 arriva al browser come 500

**Oggi.** `backend/app/main.py` registra `@app.exception_handler(Exception)`. In Starlette quell'handler diventa
l'`error_handler` di `ServerErrorMiddleware`, la middleware più esterna, fuori da `CORSMiddleware`: la risposta 500
esce senza `Access-Control-Allow-Origin`. Il browser la blocca e il client riceve un errore di rete senza corpo.

**Comportamento richiesto.** Un'eccezione non gestita su qualunque rotta produce, per un'origine consentita, una
risposta **500 con le intestazioni CORS** e il corpo `{"detail": "Internal server error"}` (o un testo italiano
equivalente). Il log della traccia resta com'è. Nessun dettaglio interno nel corpo. La forma della soluzione
(middleware dentro la catena CORS, o intestazioni aggiunte nel gestore) la sceglie il piano; il test decide.

**Test (pytest).** Una rotta di prova che solleva, chiamata con `Origin: http://localhost:3000`: status 500,
`Access-Control-Allow-Origin` presente, corpo JSON. Con un'origine non consentita: nessuna intestazione CORS. Rosso
sul codice di oggi.

### 3.2 CE Prev., SP Prev. e Report: tre stati, mai uno spinner eterno

**Oggi.** Le tre pagine leggono `useAnalysis` (`hooks/use-queries.ts`) e derivano `loading` e un `error` generico
(«Impossibile caricare i dati previsionali», «Errore nel caricamento dell'analisi»): il `detail` del backend si perde.
Nel collaudo le pagine non uscivano mai dal caricamento. Il piano stabilisce la causa con una riproduzione: tentativi
ripetuti della query, errore di rete senza corpo, o condizione di render che ignora l'errore.

**Comportamento richiesto.**
- Una funzione pura in `lib/` deriva lo stato della vista da ciò che le query restituiscono: `caricamento` / `errore`
  (con il messaggio da mostrare) / `pronto` / `vuoto` (nessuno scenario o nessun previsionale, se le pagine lo
  distinguono già).
- Il messaggio d'errore è il `detail` del backend quando c'è; per un errore di rete senza corpo, un testo italiano che
  dice che il server non ha risposto.
- Lo stato `errore` mostra il messaggio e un pulsante **«Riprova»**, che rilancia la lettura.
- Una lettura fallita esce dallo stato di caricamento in un tempo limitato. Se la causa sono i tentativi ripetuti,
  il loro numero e la loro durata diventano espliciti e finiti.
- Le tre pagine usano la stessa funzione e lo stesso componente di stato d'errore.

**Test (vitest).** Funzione di stato: errore con `detail` → messaggio del backend; errore di rete → testo italiano;
caricamento → caricamento; dati → pronto. Se si tocca la configurazione dei tentativi, un test sul valore.

### 3.3 Indicatori dell'infrannuale: errore e proiezione mancante sono due cose

**Oggi.** In `app/pratica/page.tsx` `loadAnalysis` su un fallimento mostra solo un toast e lascia `analysis` a `null`;
il render della tab collassa qualunque assenza su «Genera prima la proiezione nel passaggio 3.».

**Comportamento richiesto.** Tre casi distinti: proiezione non generata → l'invito al passo 3 di oggi; lettura fallita
→ stato d'errore con il messaggio e «Riprova» (lo stesso componente di §3.2); dati → la tab. La decisione va in una
funzione pura in `lib/`.

**Test (vitest).** I tre casi, con la distinzione fra «nessun `ForecastYear`» ed «errore di lettura».

## 4. Ordine

3.1 prima: senza, gli stati d'errore di 3.2 e 3.3 in un browser vero vedrebbero solo errori di rete. Poi 3.2 e 3.3,
che condividono il componente di stato d'errore: in serie o nello stesso task.

## 5. Verifica di fine lotto

- pytest, vitest, `tsc`, lint puliti.
- Collaudo a schermo con un errore del backend provocato di proposito, per esempio fermando il backend o facendo
  sollevare una rotta in un ambiente di prova, su CE Prev., SP Prev., Report e Indicatori dell'infrannuale. Per
  ciascuna: un messaggio leggibile, «Riprova» che funziona quando il backend torna, nessuno spinner eterno. Poi la
  stessa pagina con dati sani, identica a prima.
- `/riallinea` sul diff del lotto.
