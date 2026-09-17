# M2-06B — packaging offline del renderer Typst

Collaudo locale del 2026-09-17, worktree `worktree-agent-ab95760a5d0f5bd41` a partire da
`fix/quadratura-rettifiche` @ `0e1e7f5`. Nessun accesso Docker su questa macchina (WSL,
Docker Desktop di Windows non integrato): tutto ciò che segue è verificato offline, senza
container.

## Che cosa è cambiato

- `Dockerfile.backend`: `bubblewrap`, `xz-utils`, `ca-certificates` nel layer apt; un nuovo
  layer che copia `tools/typst/{manifest.json,install.sh,verify.sh,healthcheck.py,
  healthcheck-fixture.json}` e installa+verifica il compilatore pinnato **prima** della
  `COPY backend/ backend/` (cache indipendente dal codice applicativo); un `HEALTHCHECK`
  che esegue `curl -f http://localhost:8000/health && python /app/tools/typst/healthcheck.py`.
- `docker-compose.yml`: rimosso l'override `healthcheck:` del servizio `backend` (usava solo
  `curl`), sostituito da un commento che spiega perché ora vince quello incorporato
  nell'immagine.
- `tools/typst/healthcheck.py` (nuovo): compilazione smoke reale, nel sandbox reale, del
  bundle `runtime-smoke` (`TypstRenderer.from_project`) su un `FinalReportModelV2`
  sintetico costruito con solo moduli di produzione — niente `tests/`, niente rete.
- `tools/typst/healthcheck-fixture.json` (nuovo, 5.798 byte): copia di
  `tests/fixtures/final_report/bilancio.json`, l'unico dato che lo script porta con sé.
- `docs/deployment/TYPST-RENDERER.md` (nuova pagina): meccanismo di build, perché la salute
  del container dipende anche da Typst, il rischio noto del sandbox userns dentro Docker
  con le opzioni e i loro costi, e il percorso da seguire quando arriva l'evidenza reale.
- `docs/deployment/README_DEPLOYMENT.md`: un rimando alla pagina nuova, nel blocco «NON
  CORRENTE» in cima (quello che si legge davvero).

Codice applicativo (`backend/app/**`, `calculations/`, ecc.) non toccato. `tools/typst/`
resta com'era per `install.sh`/`verify.sh`/`manifest.json`.

## Verifiche eseguite qui — tutte offline, esito

1. **`git log --oneline -1`** → `0e1e7f5`, confermato prima di iniziare (il worktree era
   stato creato dal commit sbagliato — `1f09819`, un punto precedente di `main` — e il
   coordinatore lo ha portato a `0e1e7f5` con un fast-forward a metà lavoro; nessuna
   modifica era stata fatta prima di quel momento).
2. **`tools/typst/verify.sh`** sul binario reale (copiato dalla checkout principale, stessa
   `manifest.json`, identica byte a byte — non riscaricato): `verify: ok`, `typst 0.15.1
   (9dfd3a08)`, sha256 binario `29273eaa04f6d00edd0c2bec578f565fc9c65be856bfbffc894567c68ed0b237`.
3. **`tools/typst/verify.sh` su un binario alterato dopo l'installazione** (un byte in coda):
   rifiutato, `binary modified after install`, exit 1.
4. **`tools/typst/install.sh` con un asset locale (`file://…`) e checksum pinnato
   deliberatamente sbagliato**: `checksum mismatch: the artifact is altered or is not the
   pinned release; refusing to extract`, **exit 3**, senza rete — la stessa strada che
   percorrerebbe `docker build` su un asset compromesso o su un mirror alterato.
5. **`tools/typst/install.sh` end-to-end, offline, con un archivio `.tar.xz` reale
   confezionato qui** (stesso binario pinnato, stesso layout `typst-x86_64-unknown-linux-
   musl/{typst,LICENSE,NOTICE}` dell'asset ufficiale, servito via `file://`, checksum
   corretto): fetch → verifica → scansione membri tar → estrazione → gate versione →
   installazione atomica → `install: ok`. Seguito da `verify.sh` sulla stessa root:
   `verify: ok`. Copre l'intero script che il `Dockerfile.backend` esegue a build time,
   compresa l'estrazione reale — cosa che il solo binario preinstallato non collauda.
6. **`tools/typst/healthcheck.py`**, eseguito con l'interprete della venv di backend
   (`/home/peter/DEV/budget/backend/venv/bin/python`), da due working directory diverse
   (dentro il worktree e da `/tmp`, per escludere dipendenze dalla cwd):
   `typst healthcheck: ok pages=1 compiler=0.15.1 elapsed_ms=254..332`. Compila davvero,
   nel sandbox `bwrap` reale di questa macchina (`--unshare-all --unshare-user
   --cap-drop ALL --clearenv`), il bundle `runtime-smoke`.
7. **`tests/test_typst_toolchain.py`**: 27 passed.
8. **`tests/test_typst_runtime.py`**: 42 passed (compilazioni reali nel sandbox, stati
   draft/final, tre workflow, refusal di binario alterato, refusal di sandbox mancante,
   fallimento chiuso su filesystem/rete/diagnostica, timeout, cleanup della directory
   privata).
9. **`tests/test_deployment_docs.py`**: 16 passed — la nuova `TYPST-RENDERER.md` non cita
   l'host dismesso né la porta morta (non li nomina affatto) e non parla di Netlify, quindi
   non ricade nel vincolo «marcata NON CORRENTE» del test.
10. **`git diff --stat`** sui file tracciati modificati: 45+8+4 righe, nessuna riscrittura
    di massa — nessun terminatore di riga convertito.

Comando ripetibile dei due gate Typst mirati:

```bash
PYTHONPATH=backend TYPST_TEST_BINARY=tools/typst/bin/typst \
  /home/peter/DEV/budget/backend/venv/bin/python -m pytest -q -p no:cacheprovider \
  tests/test_typst_toolchain.py tests/test_typst_runtime.py
```

## Che cosa NON è stato collaudato qui (serve un container reale)

- **`docker build`** del `Dockerfile.backend` modificato: nessun Docker su questa macchina.
  Non verificato: che `apt-get install bubblewrap xz-utils ca-certificates` risolva
  davvero su `python:3.12-slim`, che `tools/typst/install.sh` scarichi per davvero
  dall'URL GitHub reale (qui è stato provato solo con `file://` locale — il codice che
  gestisce `https://` non è stato eseguito), che l'ordine dei layer produca la cache
  attesa, che `HEALTHCHECK` sia sintatticamente valido per il parser Docker (nessun
  `hadolint` disponibile né via apt né via `npx` in questo ambiente — verificato solo a
  occhio contro la sintassi Dockerfile).
- **Il rischio vero e proprio**: se `bwrap --unshare-user` funziona dentro il container
  `backend` reale sullo staging (seccomp/AppArmor/capability del motore Docker in uso
  lì). Impossibile da misurare da qui per costruzione — è esattamente il compito che ora
  fa il nuovo `HEALTHCHECK` al primo deploy reale. Vedi
  [docs/deployment/TYPST-RENDERER.md](../deployment/TYPST-RENDERER.md) per le opzioni e i
  passi da seguire in base a quello che l'health check mostrerà.
- **`docker compose config`** per confermare che la sintassi YAML del `docker-compose.yml`
  modificato resti valida: non verificato (nessun binario `docker compose` funzionante qui
  — il `docker` visto da `which` punta a Docker Desktop di Windows via `/mnt/c`, fuori
  dal WSL di questa sessione). Il diff è una rimozione di quattro righe dentro un blocco
  YAML già esistente più un commento: rischio sintattico basso, ma non è una prova.
- **Il comportamento di `HEALTHCHECK` in produzione** (timeout, `start_period`, e se
  `curl -f ... && python ...` in forma shell si comporta come previsto dentro l'immagine
  Debian slim: `/bin/sh` lì è `dash`, che supporta `&&` senza problemi, ma non è stato
  eseguito dentro un container reale).

## Raccomandazione sulla sandbox bwrap in Docker

Non attivare nulla in questo lotto (`docker-compose.yml` non ha `security_opt`/`cap_add`
per `backend`): fare arrivare l'evidenza reale dal nuovo `HEALTHCHECK` al primo deploy,
poi decidere. Le opzioni, in ordine di tentativo, con il costo di ciascuna, sono
documentate in dettaglio in
[docs/deployment/TYPST-RENDERER.md § «Il rischio non ancora chiuso»](../deployment/TYPST-RENDERER.md):

1. `cap_add: [SYS_ADMIN]` sul solo servizio `backend` — primo tentativo consigliato,
   nessun profilo seccomp su misura da scrivere; costo: capability ampia.
2. Profilo seccomp su misura scoped alla sola regola `CLONE_NEWUSER` — **non prodotto
   qui**: andrebbe derivato dal Docker Engine reale in uso sullo staging, non scritto a
   memoria da questa macchina senza poterlo verificare.
3. `security_opt: [apparmor:unconfined]` sul solo `backend`, solo se (1) non basta da
   solo.
4. Sysctl host `kernel.unprivileged_userns_clone=1` — rilevante solo se si sceglie (2)
   invece di (1).

Esplicitamente escluse, per istruzione ricevuta: `--privileged` e qualunque ripiego che
esegua Typst senza sandbox (`runtime.py` non ne prevede uno, e non va introdotto qui).

## Rischi residui

- Il `HEALTHCHECK` ora lega la salute dell'intero container `backend` (e quindi il
  successo del deploy Jenkins, rollback compreso) anche al renderer PDF: un deploy che
  altrimenti sarebbe innocuo può fallire per una regressione isolata di Typst. Scelta
  deliberata e motivata in `TYPST-RENDERER.md`; se risultasse scomoda in pratica, la via
  d'uscita (scorporare i due controlli) non è stata implementata qui per non introdurre
  un secondo endpoint/file di healthcheck non richiesto.
- Il file `tools/typst/healthcheck-fixture.json` è una copia, non un riferimento, di
  `tests/fixtures/final_report/bilancio.json`: se quella fixture cambia forma per
  ragioni di test, questa copia non si aggiorna da sola. Il rischio è basso (lo script
  costruisce il modello con lo stesso percorso di produzione di
  `tests/test_final_report_v2.py::fixture_report`, quindi un cambio di schema che rompe
  l'uno rompe anche l'altro, rendendo la copia disallineata visibile ai gate CI ordinari
  — ma non è un collegamento automatico).
- Non verificata la build reale (vedi sopra): un errore di sintassi Dockerfile o un
  pacchetto apt mancante si scoprirebbe solo al primo `docker compose build` su una
  macchina con Docker.
