# Import PDF snello: struttura, macroconti, verifica, dettagli

Spec del 2026-09-26. Sostituisce, per l'obiettivo, il piano
`docs/superpowers/plans/2026-09-23-import-struttura-vision.md` (stesso branch), che metteva una fase di
struttura davanti all'importatore di oggi senza toccarne le chiamate e i vincoli: di quel piano si
riusano i Task 1-2 (mappa della struttura portata dal branch `feat/import-mappa-classificazione`).

## 1. Obiettivo

Un bilancio in PDF deve arrivare nei campi `sp`/`ce` del sistema budget **con un errore piccolo e
dichiarato, in poche chiamate**, su Qwen locale (gx10) per la lettura e Sonnet per la sola struttura.
Non si importa al centesimo: si importa il bilancio, e la parte che non torna si dichiara e si
corregge in Rettifiche.

Decisioni del proprietario (2026-09-26):

- «bisogna ingegnerizzare bene la lettura ed interpretazione di questi pdf. Sono sempre bilanci e non
  devono essere importati al centesimo, il sistema attuale usa troppe chiamate ed impone troppi limiti
  al modello, bisogna snellire e lasciare estrarre al modello i numeri tenendo chiara la riclassifica
  finale che abbiamo nel sistema budget»;
- «soglia relativa (con altri debiti altri crediti costi per servizi come tappo)»;
- «vision con Sonnet» per la struttura;
- «tieni l'attuale come ripiego»;
- «non dimentichiamoci del lavoro già fatto sulle 3 route e compensazioni immobilizzazioni - fondi e
  altre attivo passivo di voci minori»;
- capacità di gx10: 500k token di contesto condivisi; fino a 4 richieste parallele se ciascuna sta
  sotto 100k di contesto, oltre rallenta il prefill.

## 2. Perché (misurato il 2026-09-26)

- Sistema attuale con i tre fornitori su gx10: `budget_948` (route C, contrapposte) **708 s**;
  `budget_949` **185 s**; il bilancio di verifica AMBIENTA 30.06.2026 **456 s e sbagliato**
  (sbilancio 330.223,99 = patrimonio netto + TFR non letti).
- Profilo per fase del sistema attuale su `budget_948` (555 s): `extract_source_candidates` →
  `ledger_evidence.read_accounts` **483 s** in 5 chiamate, una delle quali ha scritto il tetto intero di
  14.000 token e da sola è durata 368 s; il pass CoGe 37 s in 4 chiamate, **3 delle quali identiche**
  (stesso prompt da 11.545 token, stessa risposta); i dettagli 34 s. Qwen ha scritto 28.609 token.
- Prototipo usa-e-getta (righe dal text layer, Qwen assegna il percorso di legge, il codice somma):
  stesso `budget_948` in pareggio in **26 s**; AMBIENTA verifica e depositato in pareggio al
  centesimo in **18-31 s**; 22 file di route C in 540 s complessivi. Il prototipo pareggiava solo 9
  file su 22 contro 17 del sistema attuale: gli errori erano tutti di ricostruzione delle righe
  (righe fisiche spezzate, sottolineature fra le cifre, importi nell'etichetta), cioè esattamente ciò
  che il parser di route C sa già fare. Da qui la regola di questa spec: **la struttura delle righe
  si riusa, non si riscrive** (la stessa lezione è nel registro del motore mappa, 2026-09-23).
- Qwen su gx10 (`qwen3.8-flash-next`): ~60 token/s in uscita per richiesta, ~150 token/s aggregati a
  4 richieste; il prefisso comune va in cache (20k token: 8 s → 3,7 s). **Il costo è l'output.**
- Qwen legge anche immagini: le pagine SP e CE del depositato AMBIENTA (testo vettoriale, nessun
  text layer) trascritte a 120 dpi in 3 strisce per pagina, 57/57 righe con importi esatte, 20,8 s.
- Trappola misurata: uno schema con `enum` di ~110 codici campo, thinking spento, fa scorrere
  l'elenco in ordine (Avviamento → `sp02c`, ratei passivi → `sp17`). Il percorso di legge
  (`SPP.D.4.E`) invece è stato corretto su 107/107 righe.

## 3. Principi

1. **Il modello estrae; il codice verifica e applica le regole contabili.** Il modello può restituire
   importi. Il codice non inventa massa oltre la soglia, e ogni correzione è dichiarata.
2. **Poche chiamate, risposte corte.** Nessun giro di riparazione per default, nessuna estrazione
   ripetuta «per vedere se torna»: una sola rilettura mirata quando la verifica fallisce oltre soglia.
3. **Mai scegliere da un elenco lungo.** Il modello nomina voci di legge (percorso o nome del campo
   come chiave di un oggetto), non sceglie un codice da un `enum` di decine di valori.
4. **La struttura delle righe e le regole contabili si riusano** dall'importatore a tre route
   (`collect_source_rows`, `situazione_contabile_parser`, `iv_cee_hierarchy`, netting, compensazioni):
   il nuovo percorso sostituisce le chiamate LLM e i loro vincoli, non il sapere sui layout.
5. **L'importatore attuale resta come ripiego**, intero e invariato.

## 4. Architettura

Interruttore `IMPORT_MOTORE=snello` (assente → comportamento di oggi). Con l'interruttore acceso:

```
PDF ──► xbrl di legge? ──sì──► mappa dai titoli (0 chiamate)
          │no
          ▼
     F1 Struttura (Sonnet vision, 1-2 chiamate)
          ▼
     F2 Macroconti (gx10: SP e CE in parallelo)
          ▼
     F3 Verifica + tappo (codice) ──oltre soglia──► 1 rilettura mirata ──ancora oltre──► ripiego: importatore attuale
          ▼ entro soglia
     F4 Dettagli per il budget (gx10, solo dove servono)
          ▼
     regole contabili (codice) ──► salvataggio + validation_report["import_snello"]
```

### F1 — Struttura

Riuso della mappa del branch mappa (`importers/mappa_classificazione/mappa.py` →
`importers/struttura_documento/mappa.py`, Task 1-2 del piano del 23/09): blocchi dal text layer, una
chiamata Sonnet per blocco a 110 dpi, tool forzato; per gli xbrl di legge (piè di pagina della
tassonomia) mappa deterministica dai titoli, zero chiamate.

Uscita, per documento: pagine SP, pagine CE, pagine di dettaglio (sottoconti, tabelle di nota
integrativa su crediti, debiti, rimanenze); per ogni pagina di prospetto `disposizione`
(colonna unica / sezioni contrapposte), `schema` (di legge / riclassificato con codici / piano dei
conti), colonne con ruolo (saldo corrente, saldo precedente, dare, avere, scostamento, percentuale) e
intestazione stampata, `totali_stampati`, `continuazione`; unità (euro / migliaia); presenza del text
layer.

Sui PDF senza text layer (scansioni, testo vettoriale come il depositato AMBIENTA) la struttura gira
lo stesso: Sonnet vede le immagini.

La chiave della cache delle mappe include la versione della regola dei blocchi (trappola del registro
mappa: una cache per file nascondeva i cambi di regola).

### F2 — Macroconti

Due modi, scelti dallo `schema` della struttura.

**F2-L, schema di legge** (IV-CEE, abbreviato, micro, riclassificato): una chiamata per sezione (SP,
CE), le due in parallelo, con il testo delle sole pagine di quella sezione (o le immagini a strisce se
manca il text layer). Il modello restituisce, per ciascun esercizio presente nelle colonne della
struttura, un oggetto `{campo: importo}` con **solo i campi presenti** nel documento, nei campi del
budget (`sp01`…`sp18`, `ce01`…`ce20` e le sotto-voci di legge). Lo schema JSON ha le chiavi dei campi
come proprietà opzionali numeriche, con la descrizione di legge accanto a ciascuna; nessun `enum`.

**F2-C, elenco di conti** (bilancio di verifica, situazione contabile, contrapposte, piano dei conti):
- righe da `collect_source_rows` (rotazione, righe fisiche, contrapposte, colonne SAP già gestite) sulle
  sole pagine SP/CE della struttura, più la pulizia degli importi con sottolineature fra le cifre
  (difetto misurato su `budget_614`, oggi perso anche dal lettore);
- colonna del saldo dalla struttura (ruolo `saldo_corrente`), segno D/A dal marcatore stampato;
- totali e mastri esclusi perché uguali alla somma di righe adiacenti (il totale stampato decide), con
  la direzione dei totali imparata dai gruppi di almeno due righe e applicata alle catene;
- il modello assegna a ogni conto foglia il **percorso di legge** (`SPA.C.II.1.E`, `SPP.D.4`,
  `CE.B.7`, `SPA.B.II.2.F` per un fondo, `R` per la riga di quadratura, `X` per ciò che non è un
  saldo), a blocchi di ~60 righe con il nome del mastro come contesto; la legenda dei percorsi sta nel
  prompt di sistema, identica per ogni blocco (prefisso in cache);
- il codice traduce percorso → campo con una tabella fissa e somma.

Le somme di centinaia di conti non si chiedono al modello: lente e inaffidabili.

### F3 — Verifica e tappo

Controlli, tutti nel codice:
- attivo = passivo (con il risultato nel netto);
- risultato CE = `sp13` (nel bilancio di verifica il risultato del conto di netto è l'anno prima, e il
  corrente è la riga di quadratura: si accetta la forma che torna, dichiarandola);
- totali stampati dalla struttura (totale attivo, passivo, valore e costi della produzione), se presenti.

**Soglia** = `max(100 €, 0,1% del totale attivo)`, per esercizio. Entrambi i numeri in `config.py`.

- **Entro soglia:** lo scarto si chiude con un **tappo dichiarato**: sullo SP su `sp06g` (altri
  crediti) se manca attivo, su `sp16g` (altri debiti) se manca passivo; fra CE e SP su `ce06`
  (servizi). `validation_report["import_snello"]["tappo"]` = importo, campo, motivo, per esercizio.
- **Oltre soglia:** una rilettura mirata della sola sezione che non torna, con lo scarto misurato
  nel messaggio. Se torna entro soglia si procede come sopra.
- **Ancora oltre:** ripiego sull'importatore attuale (decisione del proprietario). Dei due risultati
  si tiene quello con lo scarto minore; se entrambi sono oltre soglia si importa squadrato, dichiarato,
  come oggi (le Rettifiche esistono per questo).

Il tappo è un plug entro soglia per decisione del proprietario: CLAUDE.md va aggiornato (§8).

### F4 — Dettagli per il budget

Solo le ripartizioni che il motore del previsionale usa:
- debiti: banche, altri finanziatori, fornitori, tributari, previdenziali, altri; entro/oltre;
- crediti: clienti, tributari, altri; entro/oltre;
- rimanenze di materie (`sp05a`);
- personale e ammortamenti (CE).

In F2-C i dettagli escono già dalle foglie: F4 non gira. In F2-L legge le pagine di dettaglio della
struttura (sottoconti, tabelle di nota integrativa), una chiamata per famiglia in parallelo (tetto
4), e restituisce `{campo: importo}` dentro la famiglia. Il codice chiude sulla macro-voce già
verificata in F3 (`reconcile_source_detail`) e il residuo va nel secchio «altri» della famiglia
(`residual_bucket`), mai su un campo `TIER0`. Senza pagine di dettaglio F4 non gira e le macro-voci
restano sui secchi di oggi.

### Regole contabili applicate dal codice

Invariate, applicate all'uscita di F2/F4, riusando il codice esistente:
- la colonna è la verità sul lato: un conto il cui percorso contraddice la colonna passa alla voce
  corrispondente dell'altro lato (c/c in passivo → `sp16a`, erario in dare → `sp06e`, fornitori in
  dare → `sp06g`…), mai il contrario; i fondi rettificativi restano;
- netting cespite/fondo per sottoconto, all'aggregato se manca il dettaglio;
- compensazioni dei saldi di segno opposto sulle voci minori di attivo e passivo, come oggi;
- debito senza scadenza dichiarata → a breve;
- una riga «Sbilancio»/«Squadratura» stampata dal gestionale non entra in nessun campo e si dichiara;
- i campi `TIER0` non sono mai destinazione di un ripiego o di un tappo;
- le chiavi diagnostiche (`_plug_residual`, `_unclassified_mass`, `_ce_sp_difference`) si dichiarano
  sempre, anche a zero.

## 5. gx10: contesto e concorrenza

- Un solo semaforo di processo per gx10, **4 richieste** (`GX10_CONCORRENZA`, default 4).
- Ogni chiamata dichiara il proprio tetto: token del prompt stimati + `max_tokens` ≤ **100k**
  (`GX10_CONTESTO_MAX`); un blocco che lo supererebbe si divide prima dell'invio.
- `temperature: 0`, thinking spento, `structured_outputs` dove serve uno schema, `max_tokens`
  proporzionato alla risposta attesa (non 12.000 fissi).
- Prompt di sistema e legenda identici fra le chiamate dello stesso documento, per la cache del
  prefisso.

## 6. Report e osservabilità

`validation_report["import_snello"]`: esito (`ok` / `tappo` / `squadrato` / `ripiego`), fasi con
secondi, chiamate e token (in/out) per fornitore, struttura (fonte, pagine, schema, disposizione),
scarti per esercizio prima e dopo il tappo, tappo, righe `X`/`R` con importo, ragione del ripiego.
La sonda `tests/_import_probe.py` lo registra.

## 7. Misura di riuscita (banco, solo gx10 + Sonnet per la struttura)

Banchi: i 22 file di route C, i 26 di route A/B (elenchi nel registro del motore mappa), i due
AMBIENTA.

- file entro soglia (senza ripiego) ≥ file in pareggio del sistema attuale sullo stesso banco;
- con il ripiego, nessun file peggiora rispetto al sistema attuale;
- tempo mediano per file ≤ 60 s, massimo ≤ 180 s (oggi 185-708 s);
- chiamate gx10 per file ≤ 12 (esclusa la struttura);
- banche (`sp16a`/`sp17a`) valorizzate dove il documento le stampa;
- due passate per file: stessi esiti di quadratura (la classificazione fine può oscillare).

## 8. Documentazione da cambiare nello stesso lavoro

- CLAUDE.md, «Invarianti e trappole › Contabilità / Estrazione»: il divieto di plug diventa
  «nessuna massa inventata oltre la soglia; entro la soglia un tappo dichiarato su `sp06g`, `sp16g`,
  `ce06`»; il contratto «il modello restituisce riferimenti riga/cella, non importi» vale per
  l'importatore attuale, non per il percorso snello.
- `docs/import/REGOLE-IMPORT-00…06`: il percorso snello, l'interruttore, la soglia, il ripiego.
- `docs/deployment/PRODUCTION_CONFIG.md`: `IMPORT_MOTORE`, `STRUTTURA_MODEL`, `GX10_CONCORRENZA`,
  `GX10_CONTESTO_MAX`, soglia.

## 9. Fuori ambito

- Togliere l'importatore attuale (resta ripiego).
- MinerU / `pdf-ocr`.
- Il frontend: il report di validazione è già letto dalle Rettifiche; il tappo compare come avviso.
- La scelta di un modello diverso da Qwen per la lettura.

## 10. Rischi

- **Sonnet non deterministico sulla struttura** (registro mappa: su `budget_624` una mappa rigenerata
  ha cambiato il CE). Mitigazione: la struttura sceglie pagine e colonne, i numeri li controlla F3;
  una mappa sbagliata produce uno scarto oltre soglia e quindi il ripiego, non un bilancio sbagliato
  e silenzioso.
- **Un difetto che quadra** (classificazione sbagliata dentro lo stesso lato: servizi contro godimento
  beni, clienti contro altri crediti). F3 non lo vede. Mitigazione: la legenda dei percorsi con le
  voci tipiche; il banco confronta gli aggregati con il sistema attuale e le differenze si giudicano
  a mano, su due passate.
- **Tappo che nasconde un errore di lettura** entro soglia. Mitigazione: sempre dichiarato, con la
  soglia relativa piccola (0,1%).
