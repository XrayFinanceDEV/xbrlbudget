# Packaging offline del renderer Typst (M2-06B)

Il compilatore Typst e il suo isolamento (Bubblewrap) vivono dentro l'immagine `backend`,
non nel container in esecuzione: sono scaricati, verificati e installati **a build time**
dal `Dockerfile.backend`, mai da `entrypoint.sh`. Questa pagina spiega il meccanismo, come
si verifica offline (in build e post-deploy), e il rischio noto — non ancora chiuso — del
sandbox userns dentro Docker.

Il codice del renderer stesso (`backend/app/renderers/typst/runtime.py`) non cambia qui:
questa pagina descrive solo il pacchetto attorno ad esso. Vedi anche
[docs/testing/M2-06B-packaging.md](../testing/M2-06B-packaging.md) per la ricevuta di
collaudo di questo lotto.

## Che cosa fa il `Dockerfile.backend`

1. **Toolchain di sistema**: `bubblewrap` (il sandbox — `runtime.py` non ha un ripiego
   senza sandbox, `TypstRenderer.__init__` punta a `/usr/bin/bwrap` di default), `xz-utils`
   (per spacchettare l'asset ufficiale `.tar.xz`), `ca-certificates` (per la fetch HTTPS).
2. **Compilatore Typst pinnato**: `tools/typst/install.sh` scarica l'asset indicato da
   `tools/typst/manifest.json` (versione, URL, checksum SHA-256) e **verifica il checksum
   dell'archivio PRIMA di estrarlo**; un archivio alterato o non corrispondente fa fallire
   la build (`exit 3`), mai un avvio silenzioso con un binario sbagliato. Subito dopo,
   `tools/typst/verify.sh` ricontrolla l'intero record di provenienza (versione, digest
   dell'archivio, sha256 del binario installato) prima di eseguire `--version`. Questo
   layer sta **prima** della `COPY backend/ backend/`, quindi una modifica al codice
   applicativo non lo invalida — solo un cambio di `manifest.json` lo rifà.
3. **Font del bundle**: `backend/app/renderers/typst/templates/dossier-base/fonts/*.ttf`
   sono già committati nel repository (IBM Plex Sans, quattro pesi) e arrivano con la
   normale `COPY backend/ backend/`: nessun fetch dedicato.
4. **Health check del container**: **immutato**, resta solo liveness API
   (`docker-compose.yml`, servizio `backend`: `curl -f http://localhost:8000/health`). Il
   `Dockerfile.backend` non dichiara un proprio `HEALTHCHECK` — vedi sotto il perché e come
   si collauda comunque il renderer.

## Perché la salute del container NON dipende da Typst

Una prima versione di questo lotto legava `docker inspect Health.Status` — ciò che lo
stadio «Health check» del `Jenkinsfile` legge per decidere se il deploy è riuscito — anche
a una compilazione Typst reale nel sandbox. **Reverted su indicazione del proprietario**: il
job Jenkins builda e deploya da `main` a ogni push, e se sullo staging `bwrap
--unshare-user` fosse bloccato dal profilo Docker (il rischio, ancora non misurato, descritto
sotto), quell'HEALTHCHECK avrebbe reso `unhealthy` l'**intero** backend — bloccando con il
rollback anche correzioni che non c'entrano nulla con il PDF, fino a quando qualcuno non
avesse deciso quale delle opzioni sandbox applicare. Un accoppiamento troppo largo per un
rischio non ancora misurato: la salute del container torna a dipendere solo dall'API.

Il collaudo del renderer nel container reale resta possibile, ma **come passo esplicito
dopo il deploy**, non come gate automatico:

```bash
docker compose exec backend python /app/tools/typst/healthcheck.py
```

Compila davvero, nel sandbox `bwrap` reale del container, il bundle `runtime-smoke`
(`TypstRenderer.from_project`) su un `FinalReportModelV2` sintetico costruito con solo
moduli di produzione (`app.schemas.final_report`, `app.services.final_report_dossier`,
`database.models`) più una fixture da 5,8 KB spedita accanto allo script
(`tools/typst/healthcheck-fixture.json`, copia di
`tests/fixtures/final_report/bilancio.json` — mai il pacchetto `tests/`, che non è
nell'immagine). Nessuna rete.

**Esito atteso**: `typst healthcheck: ok pages=1 compiler=0.15.1 elapsed_ms=…`, exit 0.

**Se fallisce**: stampa `typst healthcheck: FAILED category=<categoria>` su stderr ed esce
non-zero. `category=renderer_unavailable` è quella che compare per qualunque fallimento
della prima invocazione di bwrap nel sandbox — sandbox bloccato da seccomp/AppArmor
compreso (vedi la sezione sotto per le opzioni). Le altre categorie di `RendererError`
(`renderer_compile_failed`, `renderer_output_invalid`, …) indicano un problema diverso —
compilatore o bundle, non il sandbox — e vanno diagnosticate separatamente.

## Il rischio non ancora chiuso: `--unshare-user` dentro Docker

`runtime.py` invoca sempre `bwrap --unshare-all --unshare-user --die-with-parent
--disable-userns --cap-drop ALL --clearenv ...` (vedi `_sandbox_command`): non c'è modo di
disattivare `--unshare-user`, ed è corretto che non ci sia — è la riga che tiene la
sandbox isolata dal resto del container.

Il problema è che i namespace utente non privilegiati sono spesso **bloccati di default
dentro un container Docker**, indipendentemente dal fatto che il kernel host li permetta:

- **seccomp**: il profilo di default di Docker (`docker-default`) consente
  `clone`/`unshare`/`setns` con il flag `CLONE_NEWUSER` solo a un processo che possiede
  `CAP_SYS_ADMIN`. Un container senza quella capability — il caso di questa immagine, che
  non la richiede oggi — vede l'`unshare` interno di bwrap fallire con `EPERM`.
- **AppArmor**: il profilo `docker-default` nega `mount` al processo confinato; bwrap fa
  bind mount (`--ro-bind`, `--bind`) dentro il **proprio** namespace di mount appena
  creato, e a seconda della versione di AppArmor/kernel questo può restare negato anche lì.
- **Kernel host**: su kernel Debian/Ubuntu esiste il sysctl
  `kernel.unprivileged_userns_clone`, storicamente `0` di default, che blocca la creazione
  di user namespace ai processi **senza** `CAP_SYS_ADMIN`. Non è rilevante se il container
  gira da root con `CAP_SYS_ADMIN` (il caso sotto), ma va controllato se si sceglie la via
  del profilo seccomp su misura invece della capability.

Su questa macchina di sviluppo (WSL, niente Docker) `bwrap --unshare-user` funziona: sia
`tools/typst/verify.sh` sia `tools/typst/healthcheck.py` sono stati eseguiti con successo
qui, con il vero binario Typst pinnato e il vero `/usr/bin/bwrap` — ma è un host nudo, non
un container Docker, e non dice nulla sul comportamento dentro `docker run`/`docker
compose` sullo staging reale. **Questo è esattamente ciò che misura il collaudo manuale
sopra**, al primo deploy di questo lotto: se `docker compose exec backend python
/app/tools/typst/healthcheck.py` non torna `ok`, l'output mostra
`typst healthcheck: FAILED category=renderer_unavailable` — la stessa categoria che
`runtime.py` usa per qualunque fallimento della prima invocazione di bwrap, sandbox
bloccato compreso.

### Opzioni, con il loro costo — nessuna attivata in questo lotto

Nessuna delle seguenti è nei file di questo lotto: `docker-compose.yml` non ha
`security_opt`/`cap_add` per `backend`. Attivarne una sposta i confini di isolamento del
container e resta una decisione del proprietario, presa **con l'evidenza reale** che il
collaudo manuale produrrà al primo deploy — non una scommessa fatta qui alla cieca, e non
più un gate automatico che blocca l'intero backend nel frattempo.

| Opzione | Come | Costo |
|---|---|---|
| **A — `cap_add: [SYS_ADMIN]` sul solo servizio `backend`** (consigliata come primo tentativo) | Il profilo seccomp di Docker *di serie* già permette `CLONE_NEWUSER` a chi ha `CAP_SYS_ADMIN`: basta aggiungere la capability, nessun profilo seccomp su misura da scrivere né da mantenere nel tempo. | `SYS_ADMIN` è una delle capability Linux più ampie (mount, quote disco, e altro): il container ottiene molto più di quanto bwrap userebbe da solo, anche se bwrap stesso resta confinato dal proprio `--cap-drop ALL` interno. È il compromesso standard di chi fa girare bubblewrap/flatpak-builder dentro Docker. |
| **B — profilo seccomp su misura, scoped alla sola regola `clone`/`unshare`/`setns` su `CLONE_NEWUSER`** | Si prende il profilo di default effettivamente in uso sul motore Docker dello staging (`docker info`, o il file installato con quella versione di Docker Engine) e si allenta solo quella condizione. | Più stretto di A in linea di principio, ma **non è stato preparato in questo lotto**: scriverlo a memoria, senza poter introspezionare il Docker Engine reale dello staging da questa macchina (niente Docker qui), rischia di essere sbagliato nei due sensi — troppo permissivo, o rompere qualcos'altro in silenzio. Va costruito e rivisto sullo staging stesso, non importato da qui. Ha inoltre un costo di manutenzione: un aggiornamento del Docker Engine può cambiare la forma del profilo di default. |
| **C — anche `security_opt: [apparmor:unconfined]`** (solo se A da solo non basta) | Da aggiungere **dopo** aver verificato con il collaudo manuale che il solo `cap_add` non è sufficiente — cioè che è AppArmor, non (solo) seccomp, a bloccare il `mount` interno di bwrap. | Toglie uno strato di confinamento in più per l'intero servizio `backend`, non solo per il renderer. |
| **D — sysctl host `kernel.unprivileged_userns_clone=1`** | `sysctl -w kernel.unprivileged_userns_clone=1` + una entry persistente in `/etc/sysctl.d/`, sul VPS, fuori da questo repository. | Serve solo se si sceglie B invece di A (un container root con `CAP_SYS_ADMIN` non è soggetto a quel sysctl); richiede accesso root al VPS. |

**Esplicitamente escluse, per istruzione del proprietario**: `--privileged` (apre
l'intero container, non solo la creazione di user namespace) e qualunque ripiego che
esegua Typst **senza** il sandbox — `runtime.py` non lo prevede e non va aggiunto qui.

### Cosa fare quando arriva l'evidenza

1. Deploy di questo lotto così com'è (nessuna riga di `security_opt`/`cap_add`, health
   check del container invariato — solo liveness API).
2. Dopo il deploy, lanciare a mano
   `docker compose exec backend python /app/tools/typst/healthcheck.py`.
3. Se torna `ok`: lo staging permette già i namespace utente non privilegiati dentro il
   container. Non c'è nulla da decidere.
4. Se fallisce con `renderer_unavailable`: applicare l'opzione A (`cap_add: [SYS_ADMIN]`
   sul solo `backend` in `docker-compose.yml`), che richiede l'approvazione del
   proprietario essendo un allargamento reale dei privilegi del container, anche se
   scoped a un solo servizio.
5. Se fallisce anche con A: provare C (AppArmor) sullo stesso servizio, stessa necessità
   di approvazione.
6. Se nessuna delle due chiude il problema: tornare a B, costruendo il profilo seccomp
   sullo staging stesso, non a priori.

## Verifiche possibili offline, senza Docker (questa macchina)

`tools/typst/install.sh` e `tools/typst/verify.sh` non richiedono rete per essere provati:
un asset locale (`file://…`) con checksum alterato fa fallire `install.sh` con `exit 3`
esattamente come farebbe la build reale su un asset compromesso; un binario alterato dopo
l'installazione fa fallire `verify.sh`. `tools/typst/healthcheck.py` è stato eseguito con
successo su questo host (compilatore pinnato reale, `bwrap` reale, nessuna rete) — vedi la
ricevuta in [docs/testing/M2-06B-packaging.md](../testing/M2-06B-packaging.md) per l'elenco
esatto delle esecuzioni e per ciò che resta da collaudare sul container reale.
