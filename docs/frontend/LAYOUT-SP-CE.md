# Layout SP/CE — il catalogo IV-CEE e le viste che lo rendono

> Le regole che, violate, corrompono un dato **senza che nessun controllo se ne accorga** stanno
> in `CLAUDE.md` § «Invarianti e trappole». Qui c'è come funziona.

Stato patrimoniale e conto economico compaiono in sette punti dell'app, e devono restare
confrontabili: la stessa voce, con lo stesso nome, nello stesso posto dello schema di legge
(art. 2424 / 2425). Questa pagina spiega da dove vengono quelle righe, che cosa succede quando se
ne aggiunge una, e quali differenze fra le viste sono deliberate.

## 1. Quattro elenchi di righe, sette superfici

Non c'è **un** elenco condiviso: ce ne sono quattro, e ciascuno serve una famiglia di viste.

| Elenco | Dove vive | Chi lo rende | Righe |
|---|---|---|---|
| `RETTIFICHE_RENDER_ORDER` | `lib/pratica-rettifiche-rules.ts` | Rettifiche (le due sotto-tab) | 92 codici |
| `buildBalanceItemsWithTotals` + `buildIncomeItemsWithEbitda` | `lib/pratica-statement-rows.ts` | Confronto · Proiezione · Stampa | 76 + 44 righe, di cui 87 codici di voce |
| `BALANCE_STATEMENT_ROWS` | `lib/ivcee-catalog.ts` | `/forecast/balance` · `report-appendices` | 86 righe |
| `INCOME_STATEMENT_ROWS` | `lib/ivcee-catalog.ts` | `/forecast/income` | 47 righe |

I due prospetti insieme portano **108** righe con un campo, di cui 97 citano una voce del
catalogo; le altre 11 sono aggregati calcolati dal backend (`fixed_assets`, `ebitda`, `net_profit`,
…), che non sono voci di legge.

Gli elenchi **non coincidono**, ed è voluto. Il catalogo ha 100 voci; Rettifiche ne rende 92 — le
otto che mancano sono i tre aggregati che la scheda ricalcola da sé (`sp12_riserve`,
`sp16_debiti_breve`, `sp17_debiti_lungo`), le quattro sotto-voci dei fondi rischi (`sp14a..d`) e
`ce03a_incrementi_immobilizzazioni`, che invece i prospetti rendono. Il Confronto rende 87 voci più
33 righe sintetiche di intestazione e totale (20 nello SP, 13 nel CE). Quello che è condiviso è la
**tassonomia** — il nome, il padre, la sezione, l'ordine — non l'elenco.

Ogni elenco è pinnato riga per riga in `lib/ivcee-catalog-parity.test.ts` (§6).

## 2. Il catalogo IV-CEE

`frontend/lib/ivcee-catalog.ts` è la fonte del **nome** e della **posizione** di una voce. Ogni
`Voce` porta `code`, `parent` (null se di primo livello), `section`
(`attivo | passivo | patrimonio | ce`), `order` fra pari, e **due etichette**:

- **autonoma** (`label`) — auto-esplicativa, funziona da sola: `Debiti vs fornitori (entro)`.
  La usano il giornale delle rettifiche, il selettore di contropartita, i dialoghi e ogni riga
  della scheda Rettifiche.
- **contestuale** (`shortLabel`) — breve, funziona solo sotto l'intestazione del proprio
  aggregato: `entro 12 mesi`. La usano le righe di tabella del Confronto, della Proiezione e
  della Stampa.

`labelOf(code, role)` con `role = "contestuale"` **cade sull'autonoma** quando la breve non c'è;
`labelOf` di un codice sconosciuto restituisce il codice stesso invece di lanciare, per non
spegnere l'applicazione al caricamento del modulo — la degradazione è intercettata in CI dal test
«nessuna etichetta è il codice stesso». Delle 100 voci, 33 hanno una forma contestuale distinta.

Le **tre grafie** da cui le etichette sono derivate — `GRAFIA_RETTIFICHE`, `GRAFIA_SELETTORE`,
`CONFRONTO_RELABEL` — sono **private al modulo** dal 2026-08-11. Erano due export di
`pratica-rettifiche-rules.ts` (`RETTIFICHE_LABELS`, `COUNTERPART_PICKER_LABELS`) e una mappa
interna a `pratica-statement-rows.ts` (`relabel`): tre posti da cui si poteva ribattezzare una
voce senza passare dal catalogo. Oggi non esistono più come identificatori.

**La direzione delle dipendenze è fissa:** `ivcee-catalog.ts` importa da
`pratica-rettifiche-rules.ts` e da `pratica-codes.ts`, mai il contrario. `COUNTERPART_OPTIONS` è
passato al catalogo proprio per questo — era l'ultimo consumatore delle due mappe di grafie, e
lasciarlo nelle rules avrebbe chiuso un ciclo di import.

### Che cosa il catalogo espone e nessuno usa

`labelOf`, `isDettaglio`, `COUNTERPART_OPTIONS`, `BALANCE_STATEMENT_ROWS` e
`INCOME_STATEMENT_ROWS` hanno consumatori veri. Gli accessori che **camminano l'albero** —
`sectionRows`, `childrenOf`, `subtree`, `voce`, `aggregate`, `depthOf` — no: fuori dal catalogo
li chiamano soltanto i test. `childrenOf` serve al catalogo stesso, per costruire il blocco debiti
di `BALANCE_STATEMENT_ROWS`; `BALANCE_HIERARCHY_GROUPS` idem. `balanceRowValue` è esportato e non
ha **alcun** consumatore, nemmeno un test.

`aggregate()` compare in un solo punto del codice applicativo: il commento di
`components/report/report-composition.tsx` che ne **vieta** l'uso. Quella funzione somma le
**foglie**, e il `BalanceSheet` che arriva da `/analysis` è già aggregato dal backend (sotto-voci
a zero), quindi su `sp04`, `sp06` e `sp07` restituirebbe 0 — immobilizzazioni e crediti azzerati
in silenzio nel grafico stampato. La rinuncia è misurata nel `describe("report-composition")` del
test di parità.

## 3. Aggiungere una sotto-voce tocca QUATTRO file, non uno

Fino al 2026-08-11 `CLAUDE.md` (e il messaggio del commit `d044e06`) dicevano che bastava toccare
`ivcee-catalog.ts`: «le sei viste la ricevono per costruzione». **Era falso**, ed è esattamente il
genere di documentazione contro cui mette in guardia l'apertura di `CLAUDE.md`: descriveva un'API
che il codice non offre. Chi ci avesse creduto avrebbe prodotto una voce che non compare da
nessuna parte, senza un solo errore.

Per aggiungere, poniamo, `sp05f_nuova`:

| File | Che cosa, e cosa succede se lo salti |
|---|---|
| `lib/pratica-rettifiche-rules.ts` | il codice in `RETTIFICHE_BS_*` / `DEBT_GROUPS` / `CE_*`. Sono gli elenchi da cui `ALL_CODES` costruisce il catalogo **e** l'ordine di resa di Rettifiche: fuori di lì la voce non è editabile e non entra in `VOCI` — a meno di inserirla **a mano** in `ALL_CODES` (`ivcee-catalog.ts`), che è la via seguita per `sp14a..d` e `ce03a`. |
| `lib/pratica-codes.ts` | il padre in `DETAIL_PARENTS` (per una sotto-voce) oppure il codice in `ATTIVO_CODES` / `PASSIVO_CODES` (per una voce SP di primo livello). Se manca, `order` vale `-1` e il test «nessuna voce resta senza ordine» diventa rosso. Per una voce di primo livello del CE non serve nulla: l'ordine si deriva da `ALL_CODES`. |
| `lib/ivcee-catalog.ts` | l'etichetta (in una delle tre grafie, o in `EXTRA_LABELS`), più la riga in `BALANCE_STATEMENT_ROWS` o `INCOME_STATEMENT_ROWS` se deve comparire nei prospetti. Senza etichetta la voce si chiama come il proprio codice e il test strutturale diventa rosso. |
| `lib/pratica-statement-rows.ts` | la riga del Confronto: è ancora una sequenza scritta a mano di chiamate `labeled("…")`, nessuno la deriva dal catalogo. |

**Due file in più, che la vecchia tabella non nominava:**

- **`lib/pratica-reconcile.ts`**, se la voce entra in un aggregato riconciliato (`sp04`, `sp05`,
  `sp06`, `sp07`, `sp12`, `sp16`, `sp17`, `ce08`, `ce09`). `reconcileSubfields` porta la lista dei
  dettagli di ciascun aggregato scritta a mano: una sotto-voce che non ci sia non entra nella
  somma, il divario aggregato−dettagli la conta una seconda volta, e il secchio «altri» riceve un
  importo fantasma. **Misurato:** con `sp05_rimanenze = 1000`, `sp05a = 600` e una `sp05f = 400`
  non registrata, `sp05e_acconti` riceve 400 e la somma dei dettagli diventa 1400 contro un
  aggregato di 1000. Nessun errore: gli aggregati continuano a quadrare e il foglio pareggia — a
  sbagliare sono solo le righe di dettaglio, cioè quelle che l'utente legge.
- **`lib/ivcee-catalog-parity.test.ts`**, i cui elenchi congelati diventano rossi. È l'unico caso
  in cui aggiornarli è legittimo, e va fatto nello stesso commit (§6).

**Bilancio onesto del consolidamento.** Prima erano cinque file e una decina di punti di modifica,
e **tre** di quei punti erano tre mappe di etichette diverse. Oggi le **etichette** hanno una
fonte sola (più i letterali dei prospetti, §5); gli **elenchi di codici** sono ancora sparsi su
tre file; le **proiezioni dell'albero** sono costruite ma nessuna vista le consuma. Il
consolidamento c'è stato: non è arrivato dove il messaggio di commit diceva.

## 4. Rientro, filtro degli zeri, blocchi di dettaglio

Le regole di **resa** — filtro degli zeri, editabilità, totali — restano di ciascuna vista. Il
**rientro** lo dichiara il catalogo, ma **solo per Rettifiche**: le altre viste lo calcolano
ciascuna a modo proprio. Quattro regole diverse, e conviene saperlo prima di toccare
un'etichetta:

| Vista | Rientro | Riga di dettaglio nascosta quando |
|---|---|---|
| Rettifiche | `isDettaglio(code)` dal catalogo | mai: le sotto-righe restano editabili anche a zero |
| Confronto · Proiezione | `code in DETAIL_PARENTS` (`pl-6`) | `partial`, `reference` e `prior` sono tutti a zero **e** il codice non è in `ALWAYS_SHOW_CODES` |
| Stampa | **nessuno** — le righe di dettaglio non rientrano | `partial` e `reference` sono a zero **e** il codice non è in `ALWAYS_SHOW_CODES` (`prior` non è guardato) |
| `/forecast/balance` · `report-appendices` | `row.label.startsWith("  ")` (`pl-12`) | nessun anno storico valorizza quel campo (≥ 0,5 €) |
| `/forecast/income` | il flag `row.indent` | nessun anno storico valorizza quel campo (≥ 0,5 €) |

⚠️ **I due spazi iniziali di un'etichetta di prospetto sono comportamento, non estetica.** Su
`/forecast/balance` e nelle appendici del report decidono sia il rientro sia se la riga viene
**nascosta**. Le etichette del catalogo sono `trim()`ate — il catalogo legge i due spazi una volta
sola, per dedurne `Voce.dettaglio`, e poi li toglie. Un'armonizzazione dei prospetti a `labelOf`
(§5) farebbe quindi sparire quelle righe, senza alcun errore.

### I blocchi di dettaglio, condivisi da tutte le viste

- **Immobilizzazioni finanziarie (`sp04`):** `sp04a_partecipazioni`,
  `sp04b`/`sp04c_crediti_immob_breve`/`_lungo`, `sp04d_altri_titoli`,
  `sp04e_strumenti_derivati_attivi`. L'aggregato `sp04_immob_finanziarie` è **calcolato** dai
  sotto-campi.
- **Crediti (`sp06` entro / `sp07` oltre):** da `a` a `g` per ciascuno — clienti, controllate,
  collegate, controllanti, tributari, imposte anticipate, altri.
- **Patrimonio netto (`sp12`):** da `sp12a` (sovrapprezzo) a `sp12h` (riserva negativa azioni
  proprie), con `sp12g` (utili portati a nuovo) **prima** di `sp13` e `sp12h` **dopo**.
  `sp12_riserve` è calcolato.
- **Debiti (`sp16` entro / `sp17` oltre):** sette gruppi per tipo di creditore — banche, altri
  finanziatori, obbligazioni, fornitori, tributari, previdenza, altri. Nel Confronto ciascuno è
  una riga-totale sintetica (`_debt_banche`, …) seguita dalle due sotto-righe entro/oltre; le
  sette righe-totale sono pinnate in `ALWAYS_SHOW_CODES`, così la struttura art. 2424 si vede
  anche quando un gruppo è a zero. Nei prospetti lo stesso blocco è ricostruito da `childrenOf`,
  con una riga `computed` (entro + oltre) al posto del totale sintetico: la **didascalia di
  gruppo** non ha fonte nel catalogo e viene letta da `BALANCE_HIERARCHY_GROUPS`, per codice —
  è un quarto ruolo di etichetta che manca, dichiarato nel codice e non ancora risolto.
- **Conto economico:** `ce08a–d` (personale: TFR, salari, oneri sociali, altri), `ce09a–d`
  (ammortamenti e svalutazioni), `ce17a/b` (rivalutazioni / svalutazioni). Le righe EBITDA ed EBIT
  compaiono in tutte le viste di CE, ma sono calcolate **tre volte** in tre punti diversi:
  `buildIncomeItemsWithEbitda` per Confronto/Proiezione/Stampa, campi del backend
  (`ebitda`, `ebit`) nel prospetto di `/forecast/income`, e a mano dentro `RettificheTab`.

### La riconciliazione per anno del Confronto

Un bilancio abbreviato valorizza spesso solo gli aggregati (`sp16_debiti_breve`) e lascia i
sotto-campi a zero. `buildBalanceItemsWithTotals` applica `reconcileSubfields` a **ogni colonna
d'anno separatamente** (partial / reference / prior), così il divario finisce nel secchio «altri»
(`sp04a`, `sp05e`, `sp06g`, `sp07g`, `sp12e`, `sp16g`, `sp17g`) **prima** che le righe siano
costruite, e il filtro degli zeri non nasconde il dettaglio. È lo stesso meccanismo che le
Rettifiche applicano al caricamento (→ `RETTIFICHE.md` §4).

⚠️ `annualized_value` **non** viene riconciliato: la tab Proiezione ci scrive dentro i valori di
SP proiettati. Sovrascriverlo qui li cancellerebbe.

### Due difetti noti, lasciati dov'erano di proposito

Trovati il 2026-08-10 mentre si scomponeva `app/pratica/page.tsx`, e non corretti in quello
spostamento:

1. `buildBalanceItemsWithTotals` itera sui `rawItems` del **chiamante**: un plug calcolato per un
   codice che il chiamante non ha inviato esiste nella mappa riconciliata interna ma non ha una
   riga da rendere, quindi sparisce. Chi chiama deve includere le righe di dettaglio (anche a
   zero) perché un plug si veda.
2. Il parametro `periodMonths` di `buildIncomeItemsWithEbitda` è **morto**:
   `const factor = 12 / periodMonths` (`lib/pratica-statement-rows.ts:202`) è calcolato e mai
   letto, quindi l'output non varia con esso — l'annualizzazione delle righe di CE arriva tutta
   dall'`annualized_value` fornito dal chiamante. Stessa sorte per `partialRevenue` e `refRevenue`
   (`:282-283`).

## 5. I due elenchi di prospetto, e la terza superficie di naming

`ivcee-catalog.ts` non è solo la tassonomia: porta anche i **due elenchi di righe già impaginate**,
`BALANCE_STATEMENT_ROWS` (letto da `/forecast/balance` e da `report-appendices`) e
`INCOME_STATEMENT_ROWS` (letto da `/forecast/income`).

Quelle righe portano un testo **proprio**, distinto sia dalla grafia autonoma sia dalla
contestuale: **66 delle 97** righe che citano una voce non coincidono con nessuna delle due.
`sp04b_crediti_immob_breve` ha tre nomi —

| dove | testo |
|---|---|
| prospetto | `2) Crediti entro 12 mesi` |
| catalogo, autonoma | `Crediti immobilizzati (entro)` |
| catalogo, contestuale | `2) Crediti (entro es. successivo)` |

— e `ce20_imposte` è numerata `22)` nel prospetto e `20)` nel catalogo.

Nulla di ciò è una regressione: i testi sono arrivati **verbatim** dalle viste. Ma sono stati
spostati *dentro* il file che dichiara di essere l'unica fonte del nome di una voce, senza essere
armonizzati. Dal 2026-08-11 sono almeno **congelati** (`ATTESI_PROSPETTO_LABELS`, 108 coppie):
prima nessun test li leggeva, perché `rowKey` usa `r.field ?? "computed:" + r.label` e quindi
sulle righe che portano un campo fissava il codice, non il testo. Un futuro «armonizziamo tutto a
`labelOf`» ora si vede — e va fatto sapendo che i due spazi iniziali sono comportamento (§4).

## 6. Il test di parità, e come va letto quando diventa rosso

`frontend/lib/ivcee-catalog-parity.test.ts` (18 casi) fissa due cose di natura diversa.

**Gli elenchi di codici resi e il loro ordine**, uno per vista: `ATTESI_BALANCE` (86),
`ATTESI_INCOME` (47), `ATTESI_RETTIFICHE` (92), `ATTESI_CONFRONTO_BS` (76),
`ATTESI_CONFRONTO_CE` (44). Se uno di questi cambia, **una vista ha perso o riordinato una riga**:
quegli elenchi non vanno aggiornati per far passare il test. L'unica eccezione è una riga aggiunta
di proposito (§3).

**Il testo di ogni etichetta**: `ATTESI_CONFRONTO_LABELS` (87 grafie contestuali),
`ATTESI_LABELS_AUTONOME` (tutte e 100 le autonome), `ATTESI_PROSPETTO_LABELS` (le 108 righe di
prospetto che portano un campo). Qui un cambiamento deliberato è legittimo e si aggiorna la riga
nello stesso commit che cambia il testo. Quello che non è legittimo è aggiornarla per far tornare
verde la suite **senza sapere perché il testo si è mosso**.

Il test copre anche il rientro di Rettifiche: `isDettaglio` seleziona 32 delle 78 righe passate a
`renderSection`, dove `depthOf(code) > 0` ne selezionerebbe 42 — le 10 di scarto sono `sp12a..h` e
`ce17a/b`, che hanno un padre nel catalogo ma portano già la propria lettera di schema (`A.II)`,
`18)`) e restano a filo (→ `RETTIFICHE.md` §6).

**L'ordine di resa di Rettifiche è dichiarato una volta sola** (2026-08-11):
`RETTIFICHE_RENDER_SECTIONS` (gli elenchi passati a `renderSection`, in ordine, 78 righe) e
`RETTIFICHE_RENDER_ORDER` (ogni codice reso, debiti compresi, 92). Li consumano il componente
**e** i due test. Prima ognuno dei tre lo riscriveva a mano, e il rifacimento del test di parità
aveva **perso** `sp18_ratei_risconti_passivi`: pinnava 91 codici dove la vista ne rende 92, quindi
non si sarebbe accorto della sparizione di sp18. **Limite noto:** questo fissa quali elenchi e in
che ordine, non che il JSX li renda in quell'ordine — il componente interfoglia intestazioni,
totali e il blocco debiti fra le chiamate. Una riga persa o aggiunta non può più sfuggire; una
sezione spostata nel JSX sì.

## 7. File chiave

| File | Che cosa contiene |
|---|---|
| `frontend/lib/ivcee-catalog.ts` | il catalogo (`VOCI`, `labelOf`, `isDettaglio`, `COUNTERPART_OPTIONS`), le tre grafie private, i due elenchi di prospetto |
| `frontend/lib/pratica-rettifiche-rules.ts` | gli elenchi di codici da cui il catalogo si costruisce, e l'ordine di resa di Rettifiche |
| `frontend/lib/pratica-codes.ts` | `DETAIL_PARENTS`, `ATTIVO_CODES`, `PASSIVO_CODES`, `ALWAYS_SHOW_CODES`, `VP_CODES` |
| `frontend/lib/pratica-statement-rows.ts` | le righe del Confronto/Proiezione/Stampa (`buildBalanceItemsWithTotals`, `buildIncomeItemsWithEbitda`) |
| `frontend/lib/pratica-reconcile.ts` | `reconcileSubfields` — nove riconciliazioni aggregato→dettaglio più il plug di pareggio ≤ 5 € |
| `frontend/lib/ivcee-catalog-parity.test.ts` | gli elenchi congelati, per vista e per etichetta |
| `frontend/components/pratica/RettificheTab.tsx` | la scheda editabile |
| `frontend/components/pratica/ComparisonTable.tsx`, `ProjectionTable.tsx`, `StampaContent.tsx` | le tre viste che consumano i builder |
| `frontend/app/forecast/balance/page.tsx`, `app/forecast/income/page.tsx` | i due prospetti previsionali |
| `frontend/components/report/report-appendices.tsx` | le appendici del report, che rendono `BALANCE_STATEMENT_ROWS` |
