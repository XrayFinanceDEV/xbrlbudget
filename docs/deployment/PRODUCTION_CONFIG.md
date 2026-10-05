# Production Configuration — NON CORRENTE

> **NON CORRENTE.** Questa pagina diceva che il backend di produzione sta su un host e una
> porta propri, e che il frontend va puntato lì con `NEXT_PUBLIC_API_URL`. Non è più vero
> in nessuna delle due metà: quell'host non risponde, e in produzione la variabile è
> **vuota di proposito** — frontend e backend stanno dietro lo stesso nginx e l'app usa
> l'URL relativo `/api/v1`.
>
> La configurazione di produzione reale è descritta in
> → **[DEPLOY-JENKINS-DOCKER.md](DEPLOY-JENKINS-DOCKER.md)**.

Il testo originale è stato rimosso invece che corretto perché la sua premessa — un backend
raggiungibile a un indirizzo pubblico diverso da quello del frontend, con CORS da aprire
verso il dominio Netlify — non descrive più nulla di esistente. La versione integrale resta
in git.

Le variabili che oggi contano davvero (`SUPABASE_JWT_SECRET`, `ANTHROPIC_API_KEY`,
`ADMIN_API_KEY`, `PARENT_ORIGIN`, `ALLOWED_ORIGINS`, `MAX_COMPANIES_PER_USER`, `PORT`) sono
generate da Jenkins in `.env.docker`: vedi la guida corrente e
[IFRAME_INTEGRATION.md](IFRAME_INTEGRATION.md).

## Variabili del fornitore LLM per l'import PDF (Qwen locale)

`PDF_LLM_PROVIDER_COGE` — `anthropic` (default: il pass CoGe di route C gira su Claude
Haiku, come oggi) oppure `gx10` (Qwen locale; solo il valore esatto `gx10` cambia il
fornitore).

`PDF_LLM_PROVIDER_IVCEE` — stesso schema, per l'estrattore testuale di route A/B (schema di
legge IV-CEE) e per la lettura delle macro-voci (`read_macros`): `anthropic` di default,
`gx10` per farli girare su Qwen locale.

`PDF_LLM_PROVIDER_DETTAGLI` — stesso schema, per la seconda lettura (`read_details`,
`read_accounts`: celle di dettaglio della nota integrativa e classificazione dei sottoconti):
`anthropic` di default, `gx10` per Qwen locale.

La vision resta su Anthropic in ogni caso, per tutti e tre i fornitori: un PDF senza text
layer letto con `gx10` e senza `ANTHROPIC_API_KEY` solleva un errore dichiarato invece di
chiamare gx10 sull'immagine (gx10 qui legge solo testo).

- `GX10_API_KEY` — chiave per gx10, letta solo dall'ambiente, inviata solo come header
  `Authorization: Bearer`, mai loggata; obbligatoria quando il provider è `gx10`,
  altrimenti route C gira senza il pass CoGe e tiene il candidato deterministico.
- `GX10_BASE_URL` — default `http://100.65.63.12:18300` (indirizzo Tailscale:
  raggiungibile solo dalle macchine sulla tailnet; la porta 18300 non è mai aperta sul
  router).
- `GX10_MODEL` — default `qwen3.8-flash-next`.

Nota operativa: la chiamata a gx10 ha un timeout di 900 s e il pass CoGe ritenta la
lettura dello stato patrimoniale fino a 3 volte, quindi un gx10 bloccato può tenere
impegnato un import di route C a lungo prima di ripiegare sul candidato deterministico
(misurato dal vivo: una chiamata normale impiega 15-26 s).

## Percorso snello per l'import PDF (`IMPORT_MOTORE=snello`)

`IMPORT_MOTORE` — `snello` accende il motore alternativo di import PDF (struttura Sonnet vision +
lettura macroconti su gx10 + verifica con tappo dichiarato); qualunque altro valore, o l'assenza
della variabile (default), lascia l'importatore attuale invariato. Vedi
[REGOLE-IMPORT-02-ESTRAZIONE.md §10](../import/REGOLE-IMPORT-02-ESTRAZIONE.md) e
[REGOLE-IMPORT-04-QUADRATURE.md §12](../import/REGOLE-IMPORT-04-QUADRATURE.md).

`STRUTTURA_MODEL` — modello Anthropic per la fase di struttura (F1): quali pagine sono SP/CE/di
dettaglio, schema (di legge / riclassificato / piano dei conti) e disposizione. Default
`claude-sonnet-5-5` (dal 2026-10-02; la mappa si chiede con l'uscita strutturata, non con uno strumento forzato). **Le pagine intere del documento vanno ad Anthropic per questa fase**,
indipendentemente da `PDF_LLM_PROVIDER_*`: la struttura non gira mai su gx10.

`GX10_CONCORRENZA` — richieste gx10 in parallelo per processo (un solo semaforo, condiviso da
tutte le chiamate a gx10, non solo dal percorso snello). Default **6** (decisione del
proprietario, 2026-09-26; prima 4). gx10 ha 500k token di contesto condivisi: sotto questo numero
di richieste il prefill non rallenta, purché ciascuna resti sotto `GX10_CONTESTO_MAX`.

`GX10_CONTESTO_MAX` — tetto di token stimati (prompt + `max_tokens`) per una singola chiamata
gx10. Default **100000**. Una chiamata che lo supererebbe solleva `ContestoEccessivo` prima
dell'invio, invece di partire e farsi troncare.

`IMPORT_SNELLO_TAPPO_MAX` — limite, in euro, del tappo della verifica F3 del percorso snello:
lo scarto massimo che si chiude su un campo dichiarato, per controllo (SP, CE, confronto con i
totali stampati), e la tolleranza contro i totali stampati dal documento. Oltre, si salva
`"squadrato"` con avviso. Default **10** (decisione del proprietario, 2026-10-03).

`IMPORT_SNELLO_SOGLIA_MIN` — soglia minima assoluta, in euro, della tolleranza relativa del
percorso snello (`soglia()`). Non decide il tappo: serve al cancello sulla massa non
classificata, alla lettura di riserva e alla coerenza dei totali stampati letti (REGOLE-IMPORT-04
§12). Default **100**.

`IMPORT_SNELLO_SOGLIA_PCT` — soglia relativa, in percento del totale attivo, della stessa
tolleranza. Default **0.1** (0,1%). La soglia effettiva per esercizio è
`max(IMPORT_SNELLO_SOGLIA_MIN, IMPORT_SNELLO_SOGLIA_PCT% × totale attivo)`.

Nota operativa sul percorso snello: le sue chiamate gx10 (`importers/import_snello/lettura.py`)
usano un timeout di **120 s**, più stretto del timeout generico di 900 s del pass CoGe di route C
descritto sopra — un gx10 impantanato sul percorso snello non deve tenere impegnato l'import per
minuti prima di ripiegare.

### Accendere il percorso snello su un server (Jenkins)

Il `Jenkinsfile` è lo stesso per staging e produzione. Le variabili proprie di un server stanno in
una credenziale *Secret file* **`budget-env-staging`** (*Manage Jenkins › Credentials › System ›
Global*): righe `CHIAVE=valore`, che lo stage *Generate env* accoda a `.env.docker` (togliendo gli
`\r` di un file salvato da Windows) e di cui il log della build stampa i soli **nomi**. Il Jenkins
che non ha la credenziale scrive il `.env.docker` di sempre e importa con l'importatore attuale.

Per accendere il percorso snello, il file contiene:

```ini
IMPORT_MOTORE=snello
PDF_LLM_PROVIDER_COGE=gx10
PDF_LLM_PROVIDER_IVCEE=gx10
PDF_LLM_PROVIDER_DETTAGLI=gx10
GX10_BASE_URL=https://kpsfinanciallab.w3pro.it:18443
GX10_API_KEY=<la chiave Bearer di vLLM su gx10>
GX10_CONCORRENZA=3
```

`GX10_BASE_URL` senza `/v1` (lo aggiunge il codice) e senza barra finale. La chiave sta solo in
quel file, mai nel repo né nei log. `ANTHROPIC_API_KEY` resta necessaria: la struttura (F1) e la
vision girano su Anthropic, e l'importatore attuale la usa quando il percorso snello ripiega.

- **Concorrenza.** Il semaforo di `GX10_CONCORRENZA` è **per processo**, e il backend gira con
  `--workers 2` (`backend/entrypoint.sh`): il default di Jenkins è quindi `3`, cioè al massimo 6
  richieste in contemporanea su gx10. Il default del codice (6) vale per un processo solo.
- **Trasporto.** Una `GX10_BASE_URL` in `http://` su rete pubblica fa viaggiare in chiaro sia la
  chiave Bearer sia il testo dei bilanci: va servita in `https://` (o dentro una VPN), e la porta
  aperta su gx10 va ristretta all'IP del server.
- **Timeout.** Un import snello somma struttura (fino a 120 s), letture gx10 (120 s ciascuna) e
  passata di dettaglio: il `proxy_read_timeout` del vhost nginx **dell'host** va portato allo
  stesso valore del container (1200 s, `nginx/default.conf`), o l'utente riceve un 504 mentre
  l'import prosegue.

### Verificare che gx10 sia pronto per un server fuori dalla tailnet

`<IP_PUBBLICO>` e `<PORTA_ESTERNA>` sono l'indirizzo e la porta con cui quel server raggiunge gx10
(lo stesso valore di `GX10_BASE_URL`). La chiave si passa sempre da stdin, mai sulla riga di comando.

**1. Su gx10 — il servizio ascolta sull'interfaccia giusta e chiede la chiave.**

```bash
sudo ss -ltnp | grep 18300
```

Un indirizzo `100.65.63.12:18300` (solo Tailscale) o `127.0.0.1:18300` non riceve mai
connessioni da fuori: deve risultare `0.0.0.0:18300`, o l'IP di rete locale verso cui il router
inoltra la porta.

```bash
read -rs GX10_API_KEY; export GX10_API_KEY
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18300/v1/models                  # atteso: 401
curl -s -H @- http://127.0.0.1:18300/v1/models <<< "Authorization: Bearer $GX10_API_KEY"   # atteso: JSON col modello
```

Un 200 **senza** chiave vuol dire che il server accetta chiunque: da sistemare prima di esporlo.

**2. Firewall di gx10 e router — la porta è aperta solo al server.**

```bash
sudo ufw status numbered
sudo ufw allow from 194.163.175.249 to any port 18300 proto tcp   # staging; se manca
```

Una regola `18300 ALLOW Anywhere` è troppo larga e va sostituita. Sul router: inoltro TCP
`<PORTA_ESTERNA>` → IP locale di gx10 `:18300`, limitato all'IP sorgente del server se il router
lo consente.

**3. Dal server — gx10 raggiungibile, anche dal container.**

```bash
nc -zv -w 5 <IP_PUBBLICO> <PORTA_ESTERNA>                                                  # atteso: open
curl -s -o /dev/null -w "%{http_code}\n" http://<IP_PUBBLICO>:<PORTA_ESTERNA>/v1/models   # atteso: 401
```

L'import parte dal container del backend, la cui rete non sempre esce come l'host:

```bash
docker exec -i budget-backend-1 python - <<'EOF'
import urllib.request, urllib.error
try:
    urllib.request.urlopen("http://<IP_PUBBLICO>:<PORTA_ESTERNA>/v1/models", timeout=10)
except urllib.error.HTTPError as e:
    print("raggiungibile, HTTP", e.code)   # atteso: 401
except Exception as e:
    print("NON raggiungibile:", type(e).__name__, e)
EOF
```

Dopo aver acceso il percorso snello e rilanciato la build, una chiamata vera con la chiave che il
container ha ricevuto da Jenkins:

```bash
docker exec -i budget-backend-1 python - <<'EOF'
import sys; sys.path.insert(0, "/app")
from importers.llm_provider import chiama_gx10_testo
print(chiama_gx10_testo("Rispondi con una parola.", [{"role": "user", "content": "ping"}],
                        max_tokens=20, timeout=30))
EOF
```

Atteso: una parola in pochi secondi. «gx10 non raggiungibile» = rete o porta; «gx10 ha risposto
401» = chiave sbagliata nella credenziale `budget-gx10-api-key`; «GX10_API_KEY non impostata» = la
build non è passata dal ramo snello (variabile globale `IMPORT_MOTORE` mancante).

**4. Da un'altra rete — gx10 non è aperto a tutti.**

```bash
nc -zv -w 5 <IP_PUBBLICO> <PORTA_ESTERNA>       # atteso: timeout o refused
```

Se si collega, la chiave è l'unica protezione, e su `http://` viaggia in chiaro.

gx10 è pronto quando il punto 1 dà 401 senza chiave e il modello con la chiave, il punto 3 dà 401
dal server e dal container, e il punto 4 non si collega.
