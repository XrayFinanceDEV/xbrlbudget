# M2-06B — packaging offline del renderer Typst

Collaudo locale del 2026-09-17, worktree `worktree-agent-ab95760a5d0f5bd41` a partire da
`fix/quadratura-rettifiche` @ `0e1e7f5`. Nessun accesso Docker su questa macchina (WSL,
Docker Desktop di Windows non integrato): tutto ciò che segue è verificato offline, senza
container.

## Che cosa è cambiato

- `Dockerfile.backend`: `bubblewrap`, `xz-utils`, `ca-certificates` nel layer apt; un nuovo
  layer che copia `tools/typst/{manifest.json,install.sh,verify.sh,healthcheck.py,
  healthcheck-fixture.json}` e installa+verifica il compilatore pinnato **prima** della
  `COPY backend/ backend/` (cache indipendente dal codice applicativo). **Nessun
  `HEALTHCHECK` del Dockerfile**: un primo giro di questo lotto ne aveva aggiunto uno che
  eseguiva anche la compilazione Typst, ma il coordinatore lo ha fatto revertire (vedi
  sotto, «Correzione del coordinatore»).
- `docker-compose.yml`: **invariato rispetto a `0e1e7f5`** — l'healthcheck del servizio
  `backend` resta solo `curl -f http://localhost:8000/health`, esattamente come prima.
- `tools/typst/healthcheck.py` (nuovo): compilazione smoke reale, nel sandbox reale, del
  bundle `runtime-smoke` (`TypstRenderer.from_project`) su un `FinalReportModelV2`
  sintetico costruito con solo moduli di produzione — niente `tests/`, niente rete. Non è
  più agganciato a nessun health check automatico: è un passo di collaudo **manuale**
  post-deploy (`docker compose exec backend python /app/tools/typst/healthcheck.py`),
  documentato in `docs/deployment/TYPST-RENDERER.md`.
- `tools/typst/healthcheck-fixture.json` (nuovo, 5.798 byte): copia di
  `tests/fixtures/final_report/bilancio.json`, l'unico dato che lo script porta con sé.
- `docs/deployment/TYPST-RENDERER.md` (nuova pagina): meccanismo di build, perché la salute
  del container **non** dipende da Typst (e perché una prima versione di questo lotto lo
  faceva, e perché è stato tolto), il collaudo manuale post-deploy, il rischio noto del
  sandbox userns dentro Docker con le opzioni e i loro costi, e il percorso da seguire
  quando arriva l'evidenza reale.
- `docs/deployment/README_DEPLOYMENT.md`: un rimando alla pagina nuova, nel blocco «NON
  CORRENTE» in cima (quello che si legge davvero).

Codice applicativo (`backend/app/**`, `calculations/`, ecc.) non toccato. `tools/typst/`
resta com'era per `install.sh`/`verify.sh`/`manifest.json`.

## Correzione del coordinatore (secondo commit)

Il primo commit di questo lotto (`fed4537`) legava la salute dell'intero container
`backend` anche al renderer Typst: `HEALTHCHECK` nel `Dockerfile.backend` eseguiva
`curl -f .../health && python /app/tools/typst/healthcheck.py`, e `docker-compose.yml`
non definiva più un proprio `healthcheck:` per lasciare vincere quello dell'immagine. Il
coordinatore ha chiesto di ripristinare la sola liveness API, perché il job Jenkins builda
e deploya da `main` a ogni push: se sullo staging `bwrap --unshare-user` fosse bloccato dal
profilo Docker (rischio non ancora misurato, la cui soluzione — es. `cap_add: SYS_ADMIN` —
è una decisione del proprietario non ancora presa), quell'HEALTHCHECK avrebbe reso
`unhealthy` tutto il backend e fatto scattare il rollback anche per correzioni che non
c'entrano nulla con il PDF.

Fatto in questo secondo commit:
- `Dockerfile.backend` ricostruito **byte per byte** da `git show 0e1e7f5:Dockerfile.backend`
  (il file è CRLF tranne quattro righe `COPY` storicamente LF —
  `pdf_service/`, `contracts/`, `backend/`, `migrate_db.py` — che il primo commit aveva
  normalizzato a CRLF per errore dell'Edit tool): rimosso interamente il blocco
  `HEALTHCHECK`, riapplicate solo le due modifiche che restano volute (apt packages, layer
  di installazione Typst), preservando il terminatore di riga originale ovunque, comprese
  le quattro righe LF.
- `docker-compose.yml` riportato **identico** a `0e1e7f5` (`git diff 0e1e7f5 --
  docker-compose.yml` vuoto).
- `docs/deployment/TYPST-RENDERER.md` e questa ricevuta aggiornate di conseguenza: il
  collaudo del renderer nel container reale resta possibile ma come comando esplicito
  post-deploy, non come gate automatico.

Verifica: `git diff 0e1e7f5..HEAD -- Dockerfile.backend docker-compose.yml` non contiene
nessuna coppia di righe `-`/`+` identiche (controllato programmaticamente, vedi sotto).

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
  attesa.
- **Il rischio vero e proprio**: se `bwrap --unshare-user` funziona dentro il container
  `backend` reale sullo staging (seccomp/AppArmor/capability del motore Docker in uso
  lì). Impossibile da misurare da qui per costruzione. Con la correzione del
  coordinatore questo non è più un gate automatico del deploy: si misura con il comando
  manuale `docker compose exec backend python /app/tools/typst/healthcheck.py` dopo il
  primo deploy reale. Vedi
  [docs/deployment/TYPST-RENDERER.md](../deployment/TYPST-RENDERER.md) per le opzioni e i
  passi da seguire in base a quello che mostrerà.
- **`docker compose config`** per confermare che la sintassi YAML del `docker-compose.yml`
  (comunque tornato identico a `0e1e7f5`) sia valida: non verificato con il validatore
  nativo di Docker Compose (nessun binario `docker compose` funzionante qui — il `docker`
  visto da `which` punta a Docker Desktop di Windows via `/mnt/c`, fuori dal WSL di
  questa sessione) — solo con `yaml.safe_load` (PyYAML), che conferma la sintassi YAML
  generica ma non lo schema Compose.
- **`docker compose exec backend python /app/tools/typst/healthcheck.py`** in un
  container reale: lo script è stato eseguito solo direttamente con l'interprete Python
  della venv di sviluppo, mai dentro un container (nessun Docker qui).

## Raccomandazione sulla sandbox bwrap in Docker

Non attivare nulla in questo lotto (`docker-compose.yml` non ha `security_opt`/`cap_add`
per `backend`): fare arrivare l'evidenza reale dal collaudo manuale post-deploy
(`docker compose exec backend python /app/tools/typst/healthcheck.py`, mai un gate
automatico che blocchi l'intero deploy), poi decidere. Le opzioni, in ordine di
tentativo, con il costo di ciascuna, sono documentate in dettaglio in
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

- Il collaudo del renderer nel container reale resta **manuale**: nessun automatismo lo
  esegue al deploy, quindi può restare non fatto per un po' se nessuno lo lancia. È il
  compromesso scelto dal coordinatore per non legare la salute dell'intero backend al
  renderer PDF — vedi «Correzione del coordinatore» sopra e
  `docs/deployment/TYPST-RENDERER.md`.
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
