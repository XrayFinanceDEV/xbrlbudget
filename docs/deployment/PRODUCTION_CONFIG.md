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
`claude-sonnet-5`. **Le pagine intere del documento vanno ad Anthropic per questa fase**,
indipendentemente da `PDF_LLM_PROVIDER_*`: la struttura non gira mai su gx10.

`GX10_CONCORRENZA` — richieste gx10 in parallelo per processo (un solo semaforo, condiviso da
tutte le chiamate a gx10, non solo dal percorso snello). Default **6** (decisione del
proprietario, 2026-09-26; prima 4). gx10 ha 500k token di contesto condivisi: sotto questo numero
di richieste il prefill non rallenta, purché ciascuna resti sotto `GX10_CONTESTO_MAX`.

`GX10_CONTESTO_MAX` — tetto di token stimati (prompt + `max_tokens`) per una singola chiamata
gx10. Default **100000**. Una chiamata che lo supererebbe solleva `ContestoEccessivo` prima
dell'invio, invece di partire e farsi troncare.

`IMPORT_SNELLO_SOGLIA_MIN` — soglia minima assoluta, in euro, della verifica F3 del percorso
snello. Default **100**.

`IMPORT_SNELLO_SOGLIA_PCT` — soglia relativa, in percento del totale attivo, della stessa
verifica. Default **0.1** (0,1%). La soglia effettiva per esercizio è
`max(IMPORT_SNELLO_SOGLIA_MIN, IMPORT_SNELLO_SOGLIA_PCT% × totale attivo)`.
