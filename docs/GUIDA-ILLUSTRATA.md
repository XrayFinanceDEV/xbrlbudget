# Guida illustrata all'applicazione

> Ultima verifica: ottobre 2026, dalle schermate di sviluppo (azienda AMBIENTA). Le schermate
> del previsionale (09–21) sono tutte sullo scenario «Budget 2027–2029» #18, anno base 2026,
> orizzonte 3 anni; quelle dell'analisi infrannuale (05–08) sulla pratica 2026 a 6 mesi. Ogni immagine è una schermata reale
> dell'app; se una schermata cambia, aggiorna `docs/images/guida/` e questo file insieme.

**A chi serve.** Questa è la mappa di *che cosa si vede e dove*: ogni pagina dell'applicazione,
i suoi parametri, e che cosa fa premere quel pulsante. Non è la guida di aritmetica — per le
formule del motore vedi [FORECASTING_GUIDE.md](budget/FORECASTING_GUIDE.md) e per i contratti
delle API [API-PREVISIONALE.md](budget/API-PREVISIONALE.md). Dove una schermata nasconde una
regola che cambia i numeri, la regola è linkata alla sua pagina.

**I due percorsi.** L'app ha un unico ingresso, la **home**, e due workflow:

- **Da bilancio** (`/pratica`) — dall'importato all'analisi: tre fasi *DATI → ANALISI →
  PREVISIONALE*, sette passaggi, con un solo gate: nulla è raggiungibile finché le Rettifiche
  non sono confermate.
- **Startup** (`/budget` in modalità startup) — stesse schermate previsionali, senza bilancio
  importato dietro.

La barra di stato in testa a ogni pagina dice sempre **dove sei del percorso** (`1 DATI`,
`2 ANALISI`, `3 PREVISIONALE`) e l'azienda + anno di pratica a sinistra.

---

## 0. La home — aziende e pratiche

`/`

![Home](images/guida/01-home.png)

L'elenco delle tue aziende (max 50 per utente), a **schede espandibili**: ogni scheda mostra
nome, settore, partita IVA e quante pratiche contiene. Espandendo la scheda compaiono i pulsanti
**«Nuova pratica»** (la scelta fra **Da bilancio** e **Startup**) e **«Riprendi»** sugli anni già
lavorati — «Riprendi» riparte dall'ultimo passaggio raggiunto (la cache è nel browser, ma viene
riverificata sul server: se il server contraddice la cache, prevale il server).

Con **«Nuova azienda»** si apre un dialogo con **Nome\***, **Partita IVA** e **Settore\***
(1 Industria … 6 Edilizia — il settore sceglie il modello Altman e le soglie FGPMI).

---

# FASE 1 · DATI

## 1. Anagrafica

`/pratica` → tab *Anagrafiche*

![Anagrafica](images/guida/02-anagrafiche.png)

La carta d'identità dell'azienda di pratica: **Nome\***, **Partita IVA** e **Settore\*** (a
tendina, 1 Industria … 6 Edilizia), tutti modificabili, con **«Salva e prosegui»**. Il settore
sceglie il modello Altman (1 = 5 componenti, 2–6 = 4) e le soglie FGPMI.

## 2. Import

`/pratica` → tab *Import* (esiste anche una pagina autonoma `/import`, non raggiungibile
dalla navigazione — la via normale è questa tab)

![Import](images/guida/03-import.png)

Si importa il file (XBRL, CSV TEBE, PDF — anche con OCR MinerU dove attivo) e si dichiara il
periodo: **bilancio a 12 mesi** o **parziale con mesi 1–11** (un parziale apre la strada
all'infrannuale). Regole importanti:

- Un file parziale e uno annuale per lo stesso anno **coesistono di proposito**; l'app sceglie
  quale leggere con le sue regole di priorità.
- L'esito mostra **quadratura, avvisi e sbilanci dichiarati** — un bilancio che non quadra si
  importa comunque con avviso, e si corregge in Rettifiche; non viene «aggiustato» in silenzio.
- «Vuoi vedere gli errori e correggerli?» è il ponte verso le Rettifiche.

![Import standalone](images/guida/22-import-standalone.png)

La pagina `/import` completa, con lo storico degli upload. Per la selezione del file:
il menu Import della barra superiore.

## 3. Rettifiche

`/pratica` → tab *Rettifiche* — una tab **per anno** (storico + bilancio di verifica), entrambe
da confermare prima di proseguire

![Rettifiche](images/guida/04-rettifiche.png)

Il giornale in partita doppia sul bilancio importato: massima, dare/avere, descrizione,
contropartita. È l'unico posto dove l'utente **corregge i numeri**; tutto ciò che sta a valle
legge il libro giornale, mai un valore «sistemato» dall'app. Tre gesti:

- **rettifica / riclassifica** in partita doppia (max 20 righe per giornale);
- **«Correggi Import»** in partita semplice;
- **ripristino** allo stato importato.

Una correzione che peggiora sbilancio, identità CE↔utile o coerenza aggregati/dettagli viene
**rifiutata dal server** (relativamente: ciò che è già sbagliato in partenza si può correggere).
Finché la tab non è confermata, lo stepper blocca tutto il resto del percorso.
→ [docs/frontend/RETTIFICHE.md](frontend/RETTIFICHE.md)

---

# FASE 2 · ANALISI (infrannuale)

Raggiungibile solo con un periodo parziale importato e le Rettifiche confermate. Le prime due
tab sono l'«occhiale» sul dato; Proiezione è dove il dato diventa anno pieno.

## 4. Confronto

`/pratica` → tab *Confronto*

![Confronto](images/guida/05-confronto.png)

Riga per riga: il parziale contro l'anno di riferimento pieno, con la variazione. Il CE è
annualizzato (`× 12 / mesi`), lo **stato patrimoniale no** — è un istante, non un flusso: la
distinzione è scritta sotto le tabelle «Valori Istantanei». La pagina è di sola lettura: i
valori si modificano nella tab Proiezione, non qui.

## 5. Proiezione

`/pratica` → tab *Proiezione*

![Proiezione](images/guida/06-proiezione.png)

22 righe di conto economico modificabili a mano; i subtotali si ricapitolano nel client, lo
**stato patrimoniale proiettato lo calcola il server** (`calculations/intra_year_engine.py`) e
appare sotto. Il pulsante «Genera proiezione e indicatori di crisi» salva le ipotesi, fa
rigenerare il motore e rilegge — non c'è (più) un secondo calcolatore in TypeScript. Due scelte
di fondo visibili qui:

- ammortamenti: annualizzati, mai «cresciuti»;
- il debito finanziario è riportato dal parziale così com'è, non ruota coi ricavi; solo il
  residuo operativo ruota sui ratio dell'anno di riferimento.
- **Modo circolante** (`working_capital_mode`): *storico* (i giorni dell'anno di riferimento —
  default), *infrannuale* (i giorni osservati nel periodo), *equilibrio* (cerca i giorni che
  chiudono la cassa a zero). → [REGOLE-IMPORT-05](import/REGOLE-IMPORT-05-INFRANNUALE.md) §5-bis

## 6. Indicatori

`/pratica` → tab *Indicatori*

![Indicatori infrannuale](images/guida/07-indicatori.png)

Le stesse schede di sintesi dell'analisi annuale (sotto § 14) sulla colonna proiettata, più i
**15 segnali di allarme** della crisi d'impresa (14 concorrono al punteggio, `of_revenue` è
informativo): verde/ambra/rosso, misurati **sul server** (`calculations/crisi_impresa.py`); la
classe di rating A3→D si sceglie dal numero di segnali. I due grafici sono un componente solo
anche nella Stampa. → [INDICATORI-E-STAMPA.md](frontend/INDICATORI-E-STAMPA.md)

## 7. Stampa

`/pratica` → tab *Stampa*

![Stampa](images/guida/08-stampa.png)

Il documento infrannuale impaginato: sintesi, CE, SP, circolante, debito, crisi, segnali,
allegati A/B, con i **sei commenti AI** (generati da Haiku su Confronto/Proiezione/Indicatori,
poi editabili — allowlist di sei chiavi, un settimo verrebbe scartato in silenzio). Il pulsante
vero è **«Scarica PDF»**: chiama `POST /scenarios/{id}/infrannuale/pdf`, lo stesso ReportLab
del Business plan; la stampa del browser è solo un'anteprima. «Scarica Word» esporta lo stesso
report in `.docx` dagli stessi flowable. I **commenti AI** sono sei, generati e poi editabili;
un commento *chiuso* sparisce dal PDF, il testo resta modificabile a schermo. →
[REPORT-INFRANNUALE-PDF.md](budget/REPORT-INFRANNUALE-PDF.md)

---

# FASE 3 · PREVISIONALE

Cinque tab: **Budget** (il wizard), **CE Prev.**, **SP Prev.**, **Rendiconto**, **Report**.
Le due pagine **Indici** e **Riclassificato** non sono tab di questo percorso: si aprono dal
menu **«Previsionale»** della barra di navigazione in alto.

## 8. Il wizard in 7 passi

`/budget` — pulsante «Crea un nuovo scenario» o «Modifica» su uno scenario esistente

### Passo 1 · Scenario

![Wizard passo 1](images/guida/09-wizard-scenario.png)

Nome, **anno base** (l'ultimo bilancio annuale che possiedi) e orizzonte: i pulsanti **«3
anni» / «5 anni» più un campo numerico. A destra il riquadro **«Punto di partenza»** con
**«Inflazione attesa»** e la tabella **«Tendenza»** dell'anno base (ricavi, costi, utile).
L'inflazione **non tocca i ricavi**: precompila la crescita della sola **parte fissa** di
materie prime e servizi al passo 3.

### Passo 2 · Fatturato

![Wizard passo 2](images/guida/10-wizard-fatturato.png)

Una riga di crescita dei **ricavi** e una degli **altri ricavi** per ogni anno di piano.
A destra, l'anteprima dal vivo: il conto economico dell'anno base proiettato con queste
ipotesi, riga per riga, con variazione assoluta e crescita cumulata a lato. L'anteprima si
aggiorna mentre digiti e **non salva nulla**: per quello c'è il pulsante finale.

### Passo 3 · Costi

![Wizard passo 3](images/guida/11-wizard-costi.png)

Per materie prime e servizi lo slider **«Quanto è fisso»** separa parte variabile e parte fissa
(la variabile segue i ricavi, la fissa parte dall'**inflazione del passo 1**, precompilata nel
tablo «Come si muovono i costi»). Le **ipotesi manuali** (personale, godimento beni di terzi,
oneri diversi) hanno una crescita % per anno. Note
importanti dalla prova: la quota fissa è una sola e **si applica a tutti gli anni** (il
modello è per anno, l'interfaccia no — se uno scenario ha valori diversi fra anni, la
schermata avvisa e allinea al primo tocco).

### Passo 4 · Capitale circolante

![Wizard passo 4](images/guida/12-wizard-circolante.png)

I giorni medi per anno: **DSO** (incasso clienti), **giorni materie prime e semilavorati (sul
consumo)** e **prodotti finiti e merci (sui ricavi)** — i due gruppi del DIO (#62 S04:
`dio_days` + `dio_pf_days`; il DIO storico di prima vale ora per il solo primo gruppo) —,
**DPO** (pagamento fornitori), crescita dei crediti oltre 12 mesi. «Vuoto significa come
nell'anno base». A destra il circolante proiettato con «cassa liberata/assorbita». Due note
tecniche reali: i giorni sono calcolati sui soli crediti/debiti commerciali e su 360 giorni;
un valore dedotto fuori scala (oltre un anno di rotazione) è **scartato** e il
motore riporta lo stock dell'anno base — l'avviso ambra in figura lo dichiara.

### Passo 5 · Patrimoniale pregresso

![Wizard passo 5](images/guida/13-wizard-pregresso.png)

Che cosa succede ai saldi **già in bilancio** al 31/12 dell'anno base. Il lato breve senza
piano si chiude nel primo anno di piano; «quelle oltre 12 mesi le scandenzi tu, anno per
anno», nelle quattro righe «Altre voci pregresse · scadenzamento manuale» (crediti oltre 12
mesi; altri crediti tributari entro e oltre 12 mesi; altri debiti oltre 12 mesi, con caselle
per anno e «resta aperto»). Sotto «Altri crediti tributari · entro 12 mesi» c'è la casella
**«compensa il credito residuo con le imposte da versare»**. Poi i finanziamenti: **fidi,
anticipi e scoperti** (importo + tasso; è il regime esplicito dei fidi: sotto di esso il
fabbisogno non apre uno scoperto ma tira sui fidi), scadenza dei prestiti bancari pregressi
(anno per anno), altri finanziatori. I due controlli in fondo dicono: *fidi + residui dei
finanziamenti = debiti verso banche a bilancio* («quadra»), *rimborsi del primo anno = quota
mutui entro 12 mesi* («coerente").

Un vincolo che qui fa rumore: **un anno in via manuale non può scaricare meno di quanto il
piano tributario ripartirà l'anno dopo**, o la stessa rata uscirebbe due volte — il motore
rifiuta la combinazione con un errore in italiano che nomina l'anno e le tre vie d'uscita.
→ [API-PREVISIONALE.md](budget/API-PREVISIONALE.md)

### Passo 6 · Patrimoniale piano

![Wizard passo 6](images/guida/14-wizard-piano.png)

Che cosa il piano **genera**: «Altri saldi patrimoniali nel piano» (tendina per voce: *cresce
con i ricavi*, *cresce con il costo del personale*, *manuale* con importi per anno), «Nuovi
investimenti» materiali e immateriali (i nuovi cespiti ammortizzano a **metà aliquota**
nell'anno di entrata), «Fondo TFR» con le liquidazioni anno per anno (oltre il fondo
disponibile: **rifiuto**, non clamp), «Nuovi finanziamenti» (importo, anno di erogazione,
durata, tasso: la quota in scadenza l'anno dopo finisce correttamente a breve) e «Cassa e
scoperto»: sweep («Usa la cassa in eccesso per ridurre fidi, anticipi e scoperti di conto
corrente», pareggia prima lo scoperto anche sotto il minimo di liquidità), e lo
**scoperto di conto corrente** concesso o no — non concesso di default, quindi un fabbisogno
senza rimedio fa fallire la generazione con un errore, non un numero inventato.

### Passo 7 · Imposte

![Wizard passo 7](images/guida/15-wizard-imposte.png)

**Aliquota**: proposta dall'ultimo bilancio annuale depositato (mai da un infrannuale, mai da
una proiezione), 27,9 = IRES+IRAP quando non derivabile; l'aliquota è usata **così com'è**.
**Pagamento dei debiti tributari**: la regola di cassa del commercialista — ogni anno paga il
**saldo** dell'anno prima + gli **acconti** dell'anno (100% dell'imposta dell'anno prima, o
l'importo esplicito «già versato» se maggiore di zero; **zero nella casella non vuol dire
«zero acconti»**, vuol dire «usa la percentuale»). La compensazione del credito residuo si
sceglie al **passo 5**. La cassa non è più gonfiata di
un'imposta all'anno come prima di questa regola, e «Uscita di cassa per imposte» nei righi a
destra è proprio quella pagata.

Il pulsante finale **«Salva e calcola previsionale»** è la porta: legge `forecast_generated`,
**non** il 200 (una generazione rifiutata risponde comunque 200 con la ragione nel `message`).

## 9. CE Previsionale

`/forecast/income`

![CE previsionale](images/guida/17-ce-previsionale.png)

Il conto economico di piano **cella per cella**, anno per anno, in griglia modificabile:
digitare una cella scrive un `ce*_override` che **vince sulla percentuale di crescita e
sopravvive a ogni salvataggio successivo** — l'unica cosa che lo cancella è la casella
«Azzera le modifiche manuali del CE» nel dialogo Ricalcola. I subtotali (MOL, EAV, utile) si
ricapitolano a lato; «Modifiche manuali attive» le elenca tutte. Un override rifiutato dal
motore (perché oltre la giacenza di magazzino, per esempio) non resta persistito: la cella
torna com'era, con l'errore italiano che dice perché.

## 10. SP Previsionale

`/forecast/balance`

![SP previsionale](images/guida/18-sp-previsionale.png)

Lo stato patrimoniale di piano, stessa logica: celle modificabili che scrivono nel sacco
`sp_overrides` (non colonne `*_override`). È qui che si forzano i saldi — con tre limiti che
il motore fa valere: le righe governate da un piano (il lungo dei saldi scadenzati, la parte
commerciale sotto il residuo) si **rifiutano**; le righe a giorni (DSO/DPO) valgono **un anno
solo** e dall'anno dopo tornano alla formula; e un override che squilibra il foglio non si
chiude più con cassa a zero: il fabbisogno si misura dopo l'override, e o solleva o diventa
scoperto se concesso.

## 11. Riclassificato

`/forecast/reclassified` (pagina di sola lettura)

![Riclassificato](images/guida/19-riclassificato.png)

Lo **stato patrimoniale riclassificato** (attivo, passivo, patrimonio netto) con gli **indici**
per anno: solidità patrimoniale, copertura delle immobilizzazioni, indici di liquidità,
composizione delle fonti. Sotto, gli indicatori di performance con
formula e soglia (DSCR, PFN/EBITDA, punto di pareggio e margine di sicurezza) — dove il
denominatore manca, **n.d.**, mai zero.

## 12. Rendiconto

`/cashflow`

![Rendiconto](images/guida/20-rendiconto.png)

Il rendiconto finanziario **metodo indiretto** (OIC), storico contro previsionale: A)
operativo, B) investimento, C) finanziamento, con la verifica in fondo («Tutti i flussi sono
bilanciati correttamente» è un controllo, non una cortesia). Due raffinatezze volute: le
**erogazioni** (finanziamenti nuovi, incluso il tiraggio di fido) stanno in una riga separata
dai **rimborsi**, e il DSCR usa la **quota capitale contrattuale dei piani** — non il rimborso
di uno scoperto o di un fido. Il circolante prende le variazioni `sp16`/`sp17` al netto dei
debiti finanziari, che sono flusso di finanziamento: il confine è ancorato agli aggregati.

## 13. Report — il Business plan

`/report`

![Report](images/guida/21-report.png)

La pagina di consegna: selettore scenario, **«Anteprima PDF»**, «Scarica PDF finale» (finché un
controllo blocca il documento il pulsante diventa «Scarica bozza» con la ragione accanto),
«Scarica Word». Il banner di stato è il verdetto: **«Documento pronto»**, oppure **«Documento
bloccato»** con la motivazione (per esempio «Forecast precedente alle ipotesi salvate.») e
il pulsante **«Rigenera previsionale»**. Il PDF è ReportLab: **20 pagine**, copertina con
indice e dieci sezioni (Sintesi del piano, Evoluzione economica, EBITDA margin e struttura dei
costi, Costi fissi e variabili · break even point, Flussi di cassa, Sostenibilità del debito ·
DSCR e PFN, Capitale circolante commerciale, Solidità patrimoniale liquidità e redditività,
Punto di partenza, Assunzioni del piano) più gli Allegati A–E.
Le sue regole stanno in [BUSINESS-PLAN-PDF.md](budget/BUSINESS-PLAN-PDF.md).

Sotto, **«Vista web del dossier»**: lo stesso documento in HTML, con indice laterale (Perimetro
· Sintesi · Fonti · Rettifiche · Chiusura · Ipotesi · CE · SP · Cassa · Indicatori ·
Diagnostica · Appendici) e le tabelle/grafici per sezione.

![Dossier web](images/guida/21b-report-dossier.png)

La sezione Fonti è la tracciabilità: **ogni fonte del documento con il suo numero di
revisione e la data** («Origine e qualità dei dati»), così un numero del PDF si può sempre
rispedire al file che l'ha prodotto.

## 14. Analisi finanziaria completa (Indici)

`/analysis`

![Indici](images/guida/16-indici.png)

Il cruscotto sugli **indici di bilancio**: le schede di sintesi in alto (Ricavi, EBITDA, PN, ROE), Altman
Z-Score con zona e componenti, **rating FGPMI** (V1–V7 su soglie di settore, classe AAA→BB-),
i grafici radar/bar, e la tabella pluriennale con la **formula di ogni indice** accanto al
valore. Da leggere con le scelte di perimetro in testa: il DSO è sui soli **crediti
commerciali** (`None` se il dettaglio manca, non zero), il DIO sul **consumo di materie**, il
ROD sul **debito medio** e la PFN sul perimetro finanziario completo, il CCN simmetrico sui
ratei. Un valore «n.d.» è una dichiarazione, non un buco. → sezione «Indici e report» in
CLAUDE.md; la tabella pluriennale si può filtrare su uno scenario (`Scenario Budget` in alto
a destra nella tabella).

---

## Che cosa succede quando qualcosa non torna

| Segnale a schermo | Significato | Cosa fare |
|---|---|---|
| Toast verde + colonna Proiezione vuota | il bulk ha risposto 200 ma `forecast_generated: false` | leggi il `message`: il rifiuto dice tutto (di solito un fabbisogno scoperto o un override governato da piano) |
| «BOZZA · da rigenerare» | ipotesi più recenti della generazione, o motore cambiato | «Ricalcola» (dialogo: puoi azzerare gli override del CE) |
| «n.d.» su un indice | denominatore non positivo o dettaglio mai classificato dall'import | integra il dettaglio in Rettifiche, non cercare il bug |
| «Pratica da riaprire» | la cache del browser non torna col server | chiudi e riapri la pratica dalla home |
| Riga con delta **2× l'importo** | un costo letto nella colonna ricavi (o viceversa) | rettifica di direzione, non di importo |

## Dove andare dopo

- Aritmetica del motore budget → [docs/budget/FORECASTING_GUIDE.md](budget/FORECASTING_GUIDE.md)
- Contratti API (corpi, precedenze, che cosa azzera che cosa) → [docs/budget/API-PREVISIONALE.md](budget/API-PREVISIONALE.md)
- Percorso, gate e stepper → [docs/frontend/PRATICA-PERCORSO.md](frontend/PRATICA-PERCORSO.md)
- Giornale delle rettifiche → [docs/frontend/RETTIFICHE.md](frontend/RETTIFICHE.md)
- Import: routing, estrazione, quadrature → [docs/import/REGOLE-IMPORT-00-INDICE.md](import/REGOLE-IMPORT-00-INDICE.md)
- Il documento infrannuale e il Business plan → [docs/budget/REPORT-INFRANNUALE-PDF.md](budget/REPORT-INFRANNUALE-PDF.md), [docs/budget/BUSINESS-PLAN-PDF.md](budget/BUSINESS-PLAN-PDF.md)
