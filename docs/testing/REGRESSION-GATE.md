# Gate di regressione ripetibile (`scripts/verify_report_gate.sh`)

Task M1-00 del piano
[2026-09-13-report-finale-e-pdf-typst.md](../superpowers/plans/2026-09-13-report-finale-e-pdf-typst.md).
Codifica in un solo script i quattro comandi del gate di integrazione M1-10
(§7 del piano), preservandone gli exit code e fermandosi al primo fallimento
(fail-fast). Lo script **non installa nulla** e **non legge il database di
produzione**: `DATABASE_PATH` punta a un file temporaneo eliminato all'uscita e
`ANTHROPIC_API_KEY` viene rimosso dall'ambiente del backend, esattamente come
nel comando documentato.

## Modalità

```bash
scripts/verify_report_gate.sh                  # FULL: suite backend, Vitest, tsc, build
scripts/verify_report_gate.sh full             # identico
scripts/verify_report_gate.sh backend [PATH…]  # mirata: pytest (PATH sostituisce "tests")
scripts/verify_report_gate.sh vitest  [ARG…]   # mirata: vitest run
scripts/verify_report_gate.sh types            # mirata: tsc --noEmit
scripts/verify_report_gate.sh build            # mirata: next build di produzione
```

La modalità `full` è quella dei gate di integrazione; le modalità mirate sono
per i task piccoli. I gate frontend girano **sempre** su `<root>/frontend`:
non esiste un override della sorgente, e i binari invocati sono quelli locali
in `frontend/node_modules/.bin` (mai `npx`, che potrebbe scaricare). Il riuso
dei `node_modules` da un altro checkout è una scelta di setup esterna
(es. symlink), non una opzione dello script.

### Isolamento segreti / test live

Il gate backend esporta `REPORT_GATE_NO_DOTENV=1` e rimuove con `env -u`
le variabili note di opt-in verso sistemi esterni o corpus locale:
`ANTHROPIC_API_KEY`, `SUPABASE_JWT_SECRET`, `ADMIN_API_KEY`, `TEST_USER_EMAIL`,
`TEST_USER_PASSWORD`, `PROBE_SAMPLE_PDF`, `IMPORT_CORPUS_ROOT`. Su questi
percorsi verificati l'effetto è: `tests/_import_probe._load_env()` esce prima
di aprire `backend/.env` o la `.env` di root — né l'import del modulo né una
chiamata successiva può ripopolare i segreti da lì — e i consumer noti delle
variabili rimosse (tutti `skipif`/monkeypatch) risultano deterministicamente
saltati, mai falliti. Non viene affermata l'assenza di altre letture di env o
di accessi di rete da parte di diverso codice, né per i gate frontend. È una
protezione in più rispetto al solo `env -u ANTHROPIC_API_KEY` del comando
documentato M1-10; fuori dal marker `_load_env()` si comporta come prima.

I conteggi dei test li stampano i runner stessi: il criterio è **zero nuovi
fallimenti**, mai una cifra storica fissata (la suite salta i test condizionali
ai file corpus/debug non presenti nel checkout, quindi i numeri di `skipped`
variano fra worktree).

## Override di ambiente

| Variabile | Default | Uso |
|---|---|---|
| `GATE_PYTHON` | `backend/venv/bin/python` → `backend/venv/Scripts/python.exe` → `python3` da PATH | interprete con le dipendenze backend (es. worktree senza venv proprio). Viene validato con un sentinel `import pytest`: un binario inerte (es. `/bin/true`) esce con errore 2 prima di qualsiasi esecuzione |

Esempio (worktree senza venv):

```bash
GATE_PYTHON=/path/al/budget/backend/venv/bin/python scripts/verify_report_gate.sh full
```

## Exit code

`0` tutto verde; il codice del primo subcomando fallito (pytest/Vitest/tsc/build)
in caso di gate rosso; `2` per uso errato o prerequisiti mancanti (interprete
non valido, binari frontend locali assenti — il messaggio dice quale `npm
install`/venv manca).

## Perché il Jenkinsfile non esegue il gate (decisione M1-00)

Nessuna stage `Test` è stata aggiunta. Fatti misurati nel repo, non ipotesi
sull'ambiente:

1. **Il `Jenkinsfile` non definisce alcuna stage di provisioning dipendenze
   né di test.** Le sue stage sono `Checkout`, `Generate env`, `Build`,
   `Deploy`, `Health check`, `Cleanup`: nessuna di esse crea o aggiorna un
   venv Python o i `node_modules` del frontend, e lo script del gate richiede
   entrambi già presenti (non installa nulla).
2. **Nessuna immagine del repo contiene i test.** `Dockerfile.backend` copia
   solo codice di produzione (`config.py`, `database/`, `calculations/`,
   `importers/`, `pdf_service/`, `backend/`, `migrate_db.py`); `tests/` e i
   file corpus non entrano nell'immagine, quindi il gate non può girare
   nemmeno come container one-shot a partire dagli artefatti esistenti.
   Copiare `tests/` o aggiungere una variante `dev` significherebbe modificare
   i Dockerfile, fuori dallo scope di M1-00.
3. La pipeline ha un `timeout(time: 15, unit: 'MINUTES')` e una stage `Build`
   con `docker compose build --no-cache --parallel`: il tempo residuo
   disponibile per eventuali step di test sull'agente, alle condizioni reali
   di quella macchina, **non è stato misurato** e non viene affermato nulla
   al riguardo.

La decisione registrata è quindi: il gate resta eseguito fuori dalla pipeline
(a mano o da una CI dedicata) fino a quando chi possiede il deploy sceglie
dove farlo girare — un'immagine con `tests/` e dipendenze, oppure una fase di
setup sull'agente. Entrambe le vie sono modifiche ad altri file, non allo
script, che è già pronto per essere invocato da una stage `Test` con una riga:
`sh 'scripts/verify_report_gate.sh full'` prima di `Deploy`.
