# Import PDF: mappa della struttura, lettura verificata, classificazione locale

Data: 2026-09-22 · Stato: pilota eseguito, modulo da scrivere · Ramo del codice:
`feat/import-mappa-classificazione` (pilota in `tools/pilota_import/`, commit 613958b e 6e6035e).
Sostituisce, per la parte di architettura, la [spec gx10 del 21/09](2026-09-21-import-llm-gx10-design.md):
di quella restano validi i rilievi sul trasporto (su vLLM il tool forzato non è affidabile, la
decodifica vincolata sì) e la regola della chiave Bearer.

## 1. Obiettivo e vincoli

- Importare un bilancio PDF **nativo** di circa 6 pagine in **meno di 3 minuti**, con una base
  decente: macrovoci giuste, dettagli dove la fonte li stampa, il resto in secchi espliciti che
  l'utente rifinisce in Rettifiche.
- I **numeri restano in locale**: li legge il text layer e li classifica Qwen 3.8 su gx10. Il solo
  modello esterno è Sonnet 5, che vede le pagine intere per dichiararne la struttura (decisione
  del proprietario, 2026-09-22: non serve oscurare le pagine; l'oscuramento resta possibile, il
  pilota lo ha provato con esito identico, e va menzionato nell'informativa).
- Tre famiglie di formato, oggi tre route: IV-CEE di legge con tabelle di dettaglio nelle note;
  piani dei conti gerarchici, con o senza anno precedente, con o senza colonne di rettifica;
  sezioni contrapposte che richiedono il netting cespiti-fondi. Il nuovo disegno non ha route:
  la mappa parametrizza un solo lettore.

## 2. Il principio

**La struttura si ipotizza, il totale stampato decide.** Nessun modello decide un importo, una
colonna o un lato: il text layer dà i numeri, la mappa dice dove guardare, la verifica accetta un
totale solo se le sue righe sommano al centesimo, e il lato lo dà la colonna in cui la riga è
stampata. Un modello che sbaglia produce un'ipotesi che non verifica, e la mancata verifica si
dichiara. È la stessa regola di CLAUDE.md («Diagnose, never fabricate», «la colonna è la verità
sul lato»), applicata anche ai modelli.

## 3. Architettura: cinque stadi

```
PDF nativo ──► 1. Mappa (Sonnet 5, per pagina, in parallelo)
           ──► 2. Lettore geometrico (text layer, guidato dalla mappa)
           ──► 3. Verifica sui totali stampati (Python)
           ──► 4. Classificazione righe → codici (Qwen su gx10, grammatica fissa)
           ──► 5. Riconciliazione e diagnostica (Python) ──► BalanceSheet / IncomeStatement
```

### 3.1 Mappa

Per ogni pagina, dall'immagine a 110 dpi, Sonnet 5 restituisce con tool forzato:

| Campo | Valori |
|---|---|
| `tipo_pagina` | prospetto_sp · prospetto_ce · prospetto_sp_e_ce · dettaglio_conti · nota_o_testo · altro |
| `disposizione` | colonna_unica · sezioni_contrapposte |
| `schema` | iv_cee_di_legge · piano_dei_conti_gerarchico · riclassificato_con_codici_ivcee · elenco_piatto |
| `sezioni[]` | posizione (unica/sinistra/destra), contenuto (attivo/passivo/costi/ricavi/misto), `colonne[]` = ruolo + **intestazione stampata esatta** |
| `continuazione` | la pagina prosegue il prospetto della precedente con le stesse colonne |
| `codici_conto`, `totali_stampati`, `anno_precedente`, `negativi`, `fondi_ammortamento`, `note` | |

Ruoli di colonna: saldo_corrente, saldo_precedente, saldo_non_rettificato, rettifiche,
saldo_finale, dare, avere, variazione, percentuale, altro. L'**intestazione stampata** è il campo
che conta: il lettore la cerca nel text layer e ancora la colonna al suo bordo destro. Le pagine
`nota_o_testo` e `dettaglio_conti` non continuate non si leggono.

Misurato su 4 pagine, una per famiglia: 4 su 4 corrette, comprese le contrapposte a tre colonne
che Qwen 3.8 (vision, con e senza thinking, a 60/110/200 dpi) sbagliava in 2 casi su 5.

**Non tutte le pagine vanno alla vision** (decisione del proprietario, 2026-09-22). Una volta
riconosciuta la struttura, di un bilancio resta da sapere solo dove finisce lo stato
patrimoniale e dove comincia il conto economico: le pagine di uno stesso prospetto sono
strutturalmente uguali. Il pilota mappava ogni pagina (26 chiamate su FORMETAL 701, di cui 20
per dire «nota o testo»); il modulo procede così:

1. **Filtro dal text layer.** Una pagina con meno di 5 importi monetari, o con prosa corrente
   prevalente, è nota o testo: non si manda e non si legge.
2. **Confine SP/CE dal testo.** I titoli di prospetto («STATO PATRIMONIALE», «CONTO
   ECONOMICO», «ATTIVITA'/PASSIVITA'», «COSTI/RICAVI», «A) Valore della produzione») dividono
   il documento in blocchi; ogni blocco è un prospetto.
3. **Una chiamata per blocco.** Sonnet mappa la **prima pagina** di ogni blocco. Le pagine
   seguenti dello stesso blocco riusano la mappa con `continuazione = true` se la riga delle
   intestazioni di colonna, come testo normalizzato, è identica a quella della pagina mappata
   (o manca, come nelle continuazioni senza ristampa delle intestazioni). Una pagina con
   intestazioni diverse dentro il blocco apre una mappa nuova: è il caso delle tabelle di
   dettaglio nelle note di un IV-CEE xbrl, che hanno colonne proprie.

Atteso: 2 chiamate su TM (SP e CE hanno le stesse colonne ma sezioni diverse, attivo/passivo
contro costi/ricavi), 2 su FORMETAL-TEST, 1-2 su AMB. Mappare la sola prima pagina e dedurre
il resto è stato scartato: la pagina del CE ha sezioni diverse dallo SP, e il riuso per
intestazioni uguali dà lo stesso risparmio senza indovinare.

**Xbrl di legge: percorso deterministico, senza vision** (proprietario, 2026-09-22). Un PDF
generato dalla tassonomia («Generato automaticamente - Conforme alla tassonomia itcc-ci-…» nel
piè di pagina, oppure schema di legge riconosciuto dal `bilancio_classifier`) ha titoli
standard: «Stato patrimoniale», «Conto economico», e nella nota integrativa le tabelle di
dettaglio stanno dopo titoli di sezione fissi («Crediti iscritti nell'attivo circolante»,
«Variazioni e scadenza dei crediti…», «Debiti», «Variazioni e scadenza dei debiti»,
«Suddivisione dei debiti per area geografica», «Debiti assistiti da garanzie reali»). Lì:

- le pagine dei prospetti e le tabelle di dettaglio di crediti e debiti si individuano dai
  titoli, dal text layer; le colonne dei prospetti sono le due date d'esercizio, e il repo le
  legge già (`standard_ivcee_parser.has_comparative_ivcee_columns` e il parser dello schema);
- la classificazione delle voci di legge è una **tabella**, non una chiamata: le etichette
  sono quelle dell'art. 2424/2425 e `iv_cee_hierarchy.resolve` le risolve già; Qwen entra solo
  per le righe che la tabella non riconosce (tipicamente nessuna);
- la mappa vision resta come ripiego quando un titolo atteso non si trova, e si dichiara.

Su FORMETAL 701 questo vale 0 chiamate a Sonnet e una a Qwen al più, contro le 26 del pilota.
La verifica sui totali stampati (§3.3) resta identica: «Totale attivo», «Totale passivo» e i
totali di sezione sono stampati, ed è quella che fa da rete, non il riconoscimento dei titoli.

### 3.2 Lettore geometrico

`fitz` → parole → righe di testo (raggruppate sul centro y, tolleranza 0,45 × altezza mediana).

- **Sezioni affiancate**: il taglio sta fra la fine dell'intestazione dell'ultima colonna
  numerica di sinistra e la prima parola che comincia dopo di lei; una parola appartiene alla
  sezione in cui cade il suo **centro**. La ricerca del vuoto verticale per istogramma è stata
  provata e scartata: sceglie la colonna vuota «Part.» della sezione destra.
- **Colonne**: ancora = x1 dell'intestazione stampata, cercata come stringa normalizzata unita
  («31-12-2025», «Saldo non / rettificato» spezzata su due righe, anche non contigue). Un
  numero va alla colonna con l'ancora più vicina entro il 3,5% della larghezza. Senza
  intestazione trovata, ripiego sui cluster dei bordi destri dei numeri, mappati da destra.
  Un'intestazione trovata nel 15% inferiore della pagina è un piè di pagina, non un'intestazione.
- **Colonna del valore**: saldo_finale > saldo_corrente > saldo_non_rettificato > dare−avere.
- **Riga**: id (`p{pagina}{L|R|U}r{n}`), lato, prospetto (sp/ce), fino a due codici in testa
  (piani dei conti, sigle IV CEE `BI4A`, `CII5BISA`, `D14A`), descrizione, importi per ruolo,
  profondità dal codice (segmenti `.`/`/`, i `*` non contano) e rientro = x0 della
  **descrizione**, non del codice.
- **Lato**: dalla sezione dichiarata per le contrapposte; in colonna unica solo dalle
  intestazioni di sezione (attivo/passivo, «Conto economico»), portate da una pagina all'altra.
  Mai dalla descrizione.

### 3.3 Verifica sui totali stampati

Un totale è riconosciuto solo se un insieme **contiguo** di righe non ancora assegnate somma
esattamente al suo importo. Si accetta il **prefisso più corto** che torna al centesimo:

- **mastro prima dei figli** (TM, riclassificati AMB): ricerca in avanti, dal livello più
  profondo verso l'alto; un fratello allo stesso livello o un «Totale …» che segue chiudono
  la ricerca;
- **totale dopo i figli** («Totale …», mastri `***` di AGO/Zucchetti, IV CEE di legge): ricerca
  all'indietro; un totale già verificato conta come un figlio solo.

Il livello viene dalla profondità del codice se il piano ne ha almeno due, altrimenti dal
rientro con tolleranza 1,6 pt: nei PDF il rientro **deriva** (su AMB il blocco «II.» è
spostato di 1,6 pt rispetto a «I.»), e il prefisso più corto rende la profondità un limite
di ricerca, non un criterio. Le **foglie** sono le righe con importo che non sono totali
verificati; un «Totale …» che non torna è dichiarato ed escluso dalle foglie; una riga che
si chiama «Totale» non è mai una foglia.

### 3.4 Classificazione

Qwen 3.8 Flash-Next su gx10, `/v1/chat/completions`, thinking spento, temperatura 0, blocchi
di 110 righe, due chiamate in parallelo. Input: legenda dei 114 codici (dalle colonne del DB,
nome compreso) più `fa02 fa03 fs04 fs05 fs06` per i fondi e `na`; per ogni riga con importo
`id [prospetto:lato] codice descrizione`, preceduta dalle intestazioni senza importo che la
precedono. Output vincolato da una **regex a sequenza fissa**, una riga «id codice» per ogni id
nell'ordine dato: il modello non può ripetere, saltare né inventare un codice, e si ferma da
solo (con una regex `(…)+` il modello senza thinking ripeteva l'ultima riga fino al limite).

Misurato: 40 righe corrette su 40 senza thinking, circa 8 token per riga; il thinking low costa
100 token a riga e non serve. Il modello classifica anche i totali: servono per ereditare la
classe (3.5).

### 3.5 Riconciliazione

Solo le foglie si sommano. Un fondo (`fa*`/`fs*`) va in detrazione dell'aggregato che rettifica,
qualunque sia il segno stampato. Una riga classificata dal lato sbagliato rispetto alla colonna
prende la classe del **totale verificato che la contiene**, se sta dal lato giusto, altrimenti il
secchio del lato (`sp06g`/`sp16g`; in CE `ce04`/`ce06`), con avviso. Una riga `sp13` nel CE è la
riga di pareggio, non un costo. Diagnostica: totali per lato, sbilancio, risultato CE contro
`sp13`, righe `na` con importo, avvisi. Nulla viene inventato.

## 4. Esito del pilota (5 PDF nativi di `inbox/import-test`, 2026-09-22)

| File | Formato | Totali verificati | Foglie = totale stampato | DB (aggregati diversi) | Tempo |
|---|---|---|---|---|---|
| TM 589 (5 p.) | contrapposte, 3 colonne | 117, 0 aperti | attivo = passivo 1.302.133,80; CE = sp13 | 5/19, tutti a favore del pilota | 40 s |
| TM 590 (6 p.) | idem | 131, 0 aperti | 998.456,45 | 10/26 | 47-83 s |
| FORMETAL-TEST (6 p.) | contrapposte `***`, 1 colonna | 116, 0 aperti | 4.408.635,80 | 10/25 | 56-87 s |
| FORMETAL 701 (26 p.) | IV-CEE di legge | 20, 1 aperto | 2.841.452 | **0/29** | 14 s |
| AMB verifica (7 p.) | riclassificato, colonna unica | 90, 0 aperti | 2.352.461,64 | CE uguale al DB su ogni voce | 58 s |

Le differenze dal DB sono per lo più a favore del pilota (capitale e riserve separati, `ce05`
distinto da `ce06`, fondi nettati, scadenze «oltre» rispettate). Discutibili e dichiarate: mutui
«a medio/lungo» senza scadenza esplicita in `sp17a`; risultato dell'esercizio precedente e del
periodo scambiati su FORMETAL-TEST; conti bancari a saldo avere in `sp16g` invece di `sp16a`.

## 5. Costi e tempi

- **Sonnet 5, mappa**: misurati 3.135 token in ingresso e 545 in uscita a pagina (50 pagine).
  Con il listino della classe Sonnet (3 $/M in ingresso, 15 $/M in uscita, da confermare sul
  listino corrente) sono **1,8 centesimi a pagina**. Nel pilota, che mappava ogni pagina: 0,10 $
  per 6 pagine, 0,46 $ per 26. Con una chiamata per blocco (§3.1): **1-2 chiamate a file sui
  piani dei conti e sui riclassificati, 2-4 centesimi e 6-10 s**, indipendenti dal numero di
  pagine; **zero sugli xbrl di legge**, che vanno per titoli standard. Leva ulteriore se
  servisse: 60 dpi riduce i token in ingresso a un terzo (non provato su Sonnet).
- **Qwen, classificazione**: 35 token/s in uscita, 27 ciascuna con due chiamate; 8 token a
  riga; 14-87 s a file. È tutto il tempo dell'import.
- Prefill su gx10: 7.000-30.000 token/s, trascurabile.

## 6. Integrazione nel repo

- Modulo `importers/mappa_classificazione/` (`mappa.py`, `lettore.py`, `verifica.py`,
  `classifica.py`, `riconcilia.py`), promosso dal pilota con test unitari sulle parti pure
  (numeri italiani, taglio delle sezioni, ancore, prefisso più corto, ereditarietà del lato).
- `importers/llm_client.py` per gx10 come da spec del 21/09: Bearer da variabile d'ambiente,
  mai in argv né nei log; `structured_outputs.regex`; nessun ripiego automatico su Haiku per
  i numeri.
- Accensione per configurazione: `IMPORT_ENGINE=mappa` (default: quello attuale), letta in
  `pdf_importer.import_pdf_balance_sheet` prima del ramo LLM; `_PDF_PARSER_VERSION` dedicata.
- Persistenza della diagnostica nel `validation_report`: `metodo`, totali verificati e non,
  somme per lato, avvisi, righe `na` con importo, chiamate e tempi. Un totale non verificato o
  uno sbilancio sono avvisi da Rettifiche, mai un blocco al salvataggio.
- Scansioni e pagine senza text layer: fuori dal tetto dei 3 minuti. OCR locale (MinerU sul
  gx10) produce il text layer, poi lo stesso percorso. Finché non c'è, la route attuale.
- Pagine di dettaglio delle note (IV-CEE xbrl): non lette nel pilota. Nel modulo si
  individuano dai titoli standard di sezione (§3.1) e alimentano i sotto-campi di crediti e
  debiti (scadenze entro/oltre, banche, fornitori, tributari), come oggi fa
  `detail_enrichment` sulle stesse tabelle.

## 7. Rischi noti

- **Rientro che deriva**: la tolleranza di 1,6 pt è tarata su AMB. Un errore produce un totale
  non verificato (dichiarato) o un mastro contato con i figli (visibile nello sbilancio).
- **Somme accidentali**: un prefisso che torna per caso al centesimo. Improbabile; il controllo
  attivo = passivo lo rivelerebbe.
- **Classificazione** senza thinking: errori di voce dentro un aggregato (accettati dalle regole
  del repo) e, più raramente, di lato, che la colonna corregge. Un secondo passaggio con thinking
  sulle sole righe aperte è previsto e non ancora scritto.
- **Mappa** sbagliata: la verifica non torna e lo dice. Nessuna pagina passa senza verifica.
- **Privacy**: le pagine intere vanno ad Anthropic per la mappa. Scelta del proprietario;
  l'oscuramento di importi e anagrafica dal text layer è già scritto (`oscura.py` del pilota)
  e ha dato lo stesso esito.

## 8. Collaudo

1. I 5 PDF nativi di `inbox/import-test`: attivo = passivo al centesimo sui totali stampati,
   CE = `sp13`, nessun plug, ogni scarto dichiarato (fatto, §4).
2. Gli 87 PDF con baseline (`import_baseline.json`, corpus `Test/` non tracciato): tempo per file,
   totali verificati, differenze dal riferimento per aggregato; ogni differenza si giudica sul
   PDF, non sul riferimento, perché il riferimento è a sua volta una lettura LLM.
3. Prima del merge: test unitari verdi, `tsc` e suite invariati, nessun dato cliente nel repo.

## 9. Decisioni aperte

- Sotto-voci al netto dei fondi (`sp02d` netto) o fondi sull'aggregato come nel pilota.
- Dove fermare l'import quando la verifica fallisce su una pagina: dichiarare e salvare (come
  oggi) o passare la pagina a Qwen vision con thinking prima di salvare.
- Tenere o no il ripiego sull'importatore attuale quando Sonnet non risponde.
