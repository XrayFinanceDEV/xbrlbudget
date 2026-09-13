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
scripts/verify_report_gate.sh vitest  [ARG…]   # mirata: npx vitest run
scripts/verify_report_gate.sh types            # mirata: npx tsc --noEmit
scripts/verify_report_gate.sh build            # mirata: npm run build
```

La modalità `full` è quella dei gate di integrazione; le modalità mirate sono
per i task piccoli. I conteggi dei test li stampano i runner stessi: il
criterio è **zero nuovi fallimenti**, mai una cifra storica fissata (la suite
salta i test condizionali ai file corpus/debug non presenti nel checkout,
quindi i numeri di skipped variano fra worktree).

## Override di ambiente

| Variabile | Default | Uso |
|---|---|---|
| `GATE_PYTHON` | `backend/venv/bin/python` → `backend/venv/Scripts/python.exe` → `python3` da PATH | interprete con le dipendenze backend (es. worktree senza venv proprio) |
| `GATE_FRONTEND` | `<root>/frontend` | directory frontend con `node_modules` già installato |

Esempio (worktree senza venv né `node_modules`):

```bash
GATE_PYTHON=/path/al/budget/backend/venv/bin/python scripts/verify_report_gate.sh full
```

## Exit code

`0` tutto verde; il codice del primo subcomando fallito (pytest/Vitest/tsc/build)
in caso di gate rosso; `2` per uso errato o dipendenze assenti (il messaggio
dice quale `npm install`/venv manca).

## Perché il Jenkinsfile non esegue il gate (decisione M1-00)

Nessuna stage `Test` è stata aggiunta: nell'ambiente Jenkins attuale il gate
non è eseguibile in modo sano, per tre motivi misurati sul repo:

1. **L'agente Jenkins non ha le dipendenze.** Ogni stage del `Jenkinsfile` è
   solo `docker compose` / `checkout`: non esiste alcun `pip install` né
   `npm ci`, quindi `pytest`, `vitest`, `tsc` e `next build` non hanno un
   interprete/node_modules dove girare. Installarli a ogni build viola la
   regola "lo script non installa dipendenze" e non sta nel `timeout` di
   15 minuti accanto al `docker compose build --no-cache` già esistente.
2. **Il gate non gira nemmeno dentro l'immagine.** `Dockerfile.backend` copia
   solo il codice di produzione (`config.py`, `database/`, `calculations/`,
   `importers/`, `pdf_service/`, `backend/`): `tests/` e i file corpus non
   entrano nell'immagine, e aggiungerli richiederebbe di modificare i
   Dockerfile, fuori dallo scope di M1-00.
3. **La health check non è un gate di regressione** (lo dice esplicitamente il
   piano): continua a non esserlo, e il gate va lanciato a mano (o in CI
   dedicata) prima di spingere su un integration branch.

Appena esisterà un agente con venv e `node_modules` (o un'immagine `dev` con
`tests/` copiata), la stage `Test` che chiama
`scripts/verify_report_gate.sh full` prima di `Deploy` è un'aggiunta di una
decina di righe, senza modifiche allo script.
