# CLAUDE.md snellito — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** portare `CLAUDE.md` da 1694 a meno di 500 righe spostando il dettaglio in `/docs`, senza perdere un fatto vero e correggendo quelli falsi che si incontrano.

**Architecture:** un blocco alla volta. Per ciascuno: si classifica ogni affermazione in un **inventario** committato (`RESTA` / `GIÀ IN` / `SPOSTATA IN` / `OBSOLETA`), poi si applica quella classificazione. L'inventario è anche il **portatore** degli invarianti: le righe marcate `RESTA` vengono raccolte lì con il loro testo, e solo alla fine (Task 6) confluiscono nella nuova sezione «Invarianti e trappole». Senza quel passaggio, cancellare la prosa cancellerebbe anche gli invarianti che ci vivono dentro.

**Tech Stack:** solo Markdown. Nessuna modifica a codice, test, DB o comportamento.

**Spec:** `docs/superpowers/specs/2026-08-14-claude-md-snellito-design.md` — leggerla prima di iniziare.

## Global Constraints

- **Nessuna modifica a codice, test o comportamento.** Se un blocco tocca un `.py`, `.ts` o `.tsx`, è fuori perimetro: fermarsi e segnalarlo.
- **`CLAUDE.md` è un file LF.** Gli strumenti di edit normalizzano i fine riga: `git diff --stat` prima di ogni commit, e se il diff esplode `git checkout` e rifare.
- **Il criterio di permanenza** (spec §1): resta ciò che è **invariante** (violarlo corrompe un dato e nessun controllo se ne accorge), **trappola d'ambiente** (fa fallire il lavoro in modi che non si spiegano) o **orientamento** (dove stanno le cose, come si avvia). Va via tutto il resto.
- **In dubbio, RESTA.** Una riga di troppo nella sezione invarianti costa attenzione; una di meno costa un dato corrotto.
- **Mai trasportare un'affermazione senza verificarla.** Se il codice non fa quello che la riga dice, la voce è `OBSOLETA` e si cancella, con la prova nel campo «perché». Tre casi noti già trovati in sessione: la frase sul pulsante OCR «stays visible by design», i 289.788,03 attribuiti a budget_623, la conseguenza su `base_bank_debt` enunciata al contrario.
- **Dove `CLAUDE.md` e `/docs` si contraddicono non vince l'anzianità: vince il codice.** Si legge il codice, si corregge chi sbaglia, si registra `OBSOLETA`.
- **Un commit per blocco**, altrimenti il diff è irrivedibile.
- L'inventario vive in `docs/superpowers/2026-08-14-inventario-claude-md.md` e si committa insieme al blocco che descrive.

---

## Task 1: Blocco import (661 righe) — il più grande, e fissa il modello

**Files:**
- Create: `docs/superpowers/2026-08-14-inventario-claude-md.md`
- Modify: `CLAUDE.md:305-965` (`### PDF Import (Claude LLM)` e le sue 15 sottosezioni)
- Modify: i file di `docs/import/` che risultano incompleti

**Interfaces:**
- Produces: l'inventario con la sua intestazione e il criterio, più le righe del blocco import. I task successivi vi accodano le proprie righe; il Task 6 legge tutte le righe `RESTA`.

- [ ] **Step 1: Creare l'inventario con intestazione e criterio**

Crea `docs/superpowers/2026-08-14-inventario-claude-md.md`:

```markdown
# Inventario dello snellimento di CLAUDE.md

**Data:** 2026-08-14 · **Spec:** [design](specs/2026-08-14-claude-md-snellito-design.md)

Ogni affermazione rimossa da `CLAUDE.md` è registrata qui con la sua destinazione.
Chi rivede controlla questa tabella, non 1.170 righe di diff.

| destinazione | significato |
|---|---|
| `RESTA` | invariante o trappola: confluisce nella sezione «Invarianti e trappole» di `CLAUDE.md` (Task 6) |
| `GIÀ IN <file> §<n>` | il fatto è già scritto in `/docs`: da `CLAUDE.md` si cancella |
| `SPOSTATA IN <file>` | il fatto esiste solo qui: si trascrive nella destinazione |
| `OBSOLETA — <perché>` | il codice non fa quello che la riga dice: si cancella |

Una voce `RESTA` porta il **testo** dell'invariante, non solo il suo titolo: è questo file
a trasportarlo mentre la prosa che lo conteneva viene cancellata.

## Blocco import (`CLAUDE.md:305-965`)

| # | affermazione | destinazione |
|---|---|---|
```

- [ ] **Step 2: Classificare il blocco, senza ancora cancellare nulla**

Leggi `CLAUDE.md:305-965` e, per ogni affermazione, aggiungi una riga alla tabella. Per decidere `GIÀ IN`, cerca il fatto nei 13 file di `docs/import/`:

```bash
grep -rn "<frase chiave>" docs/import/
```

Regole di classificazione, in ordine:
1. È un invariante o una trappola (vedi Global Constraints)? → `RESTA`, e riporta il testo.
2. Il fatto è già in `docs/import/`? → `GIÀ IN <file> §<n>`.
3. Il codice lo smentisce? → `OBSOLETA — <cosa fa davvero il codice>`.
4. Altrimenti → `SPOSTATA IN <file di docs/import/ che lo ospiterà>`.

Verifica il punto 3 leggendo il codice, non per impressione. I moduli in gioco: `importers/pdf_importer.py`, `situazione_contabile_parser.py`, `pdf_extractor_llm.py`, `iv_cee_hierarchy.py`, `vision_rescue.py`, `bilancio_classifier.py`, `reliability.py`, `label_semantics.py`.

- [ ] **Step 3: Integrare in `docs/import/` ciò che è marcato `SPOSTATA IN`**

Scrivi quei fatti nei file di destinazione, nella sezione pertinente, nello stile della serie (regole e comportamenti, non codice Python; i riferimenti `file:riga` servono a ritrovare la regola). Non creare file nuovi in `docs/import/`: la struttura è già decisa.

- [ ] **Step 4: Sostituire il blocco in `CLAUDE.md` con un rimando**

Cancella `CLAUDE.md:305-965` e metti al suo posto una sezione breve (≤ 25 righe) che dica: cosa fa l'import in tre frasi, le tre rotte macro-area (A/B IV-CEE, C situazione contabile, XBRL), e i rimandi **con la domanda a cui rispondono**:

```markdown
### Import PDF (Claude LLM)

Ogni PDF è classificato da `bilancio_classifier.classify_bilancio` PRIMA di scegliere un
estrattore. Tre macro-aree coprono il 96% dei casi reali: **A/B** (schema IV-CEE, estrattore
LLM), **C** (situazione contabile / sezioni contrapposte, CoGe-LLM + parser deterministico),
**XBRL/non supportato**. Gli invarianti che governano tutte e tre stanno in
«Invarianti e trappole»; qui sotto c'è dove andare a leggere il resto.

| Domanda | Pagina |
|---|---|
| Come si decide che cosa è un documento e a quale estrattore va? | [REGOLE-IMPORT-01-ROUTING](docs/import/REGOLE-IMPORT-01-ROUTING.md) |
| ... | ... |
```

Completa la tabella con una riga per ciascuno dei 6 file `REGOLE-IMPORT-0*`, più `IMPORT-ROUTING-TAXONOMY` (la mappatura per file reale) e `FIXING-IMPORT.md` (il playbook per correggere un bug di import).

- [ ] **Step 5: Verificare**

```bash
wc -l CLAUDE.md                      # atteso: ~1050
grep -c "^| " docs/superpowers/2026-08-14-inventario-claude-md.md   # righe classificate
# ogni link relativo di CLAUDE.md risolve:
grep -o "](docs/[^)]*)" CLAUDE.md | tr -d '](' | while read f; do [ -f "$f" ] || echo "ROTTO: $f"; done
```
Nessun `ROTTO`. Poi, a campione su cinque fatti marcati `GIÀ IN` o `SPOSTATA IN`, `git grep` di una frase chiave deve restituire **un solo** posto: se ne restituisce due, la duplicazione non è stata rimossa, è stata creata.

- [ ] **Step 6: Commit**

```bash
git diff --stat
git add CLAUDE.md docs/import/ docs/superpowers/2026-08-14-inventario-claude-md.md
git commit -m "docs(claude): l'import vive in docs/import, CLAUDE.md rimanda"
```

---

## Task 2: Rettifiche (77 righe) → `docs/frontend/RETTIFICHE.md`

> **Fatto il 2026-08-15** (commit `f8b6d56`). Tre scoperte, registrate come righe 136-160
> dell'inventario: il filtro del selettore contropartita **non** guarda il segno (riga 147,
> `OBSOLETA`); i modi di proposta sono **tre** e uno è in partita singola (riga 136); la guardia
> anti-regressione del server è **relativa** e non era documentata (riga 157). Sei righe `RESTA`
> aggiunte a «Invarianti e trappole». Tre paragrafi sono stati spostati qui dai blocchi Pratica
> (righe 158-159) e Layout (riga 160): **i Task 3 e 4 non li troveranno più**.

**Files:**
- Create: `docs/frontend/RETTIFICHE.md`
- Modify: `CLAUDE.md` (`### Rettifiche (BS/IS Adjustments Journal)`), `docs/superpowers/2026-08-14-inventario-claude-md.md`

**Interfaces:**
- Consumes: l'inventario creato dal Task 1; accoda una sezione `## Blocco Rettifiche`.

- [ ] **Step 1: Classificare il blocco nell'inventario**

Stesse quattro destinazioni e stesse regole del Task 1. Qui `GIÀ IN` sarà raro (`docs/frontend/` ha solo due file), quindi la maggioranza sarà `SPOSTATA IN docs/frontend/RETTIFICHE.md`.

Candidati `RESTA` da valutare (non accettarli per fiducia — verificali nel codice):
- mai mettere l'oggetto restituito da `useRettificheYear` in un array di dipendenze `useEffect`
- il hook si azzera al cambio identità `[companyId, year, periodMonths]`, altrimenti si scrive nel `FinancialYear` sbagliato
- `reset()` deve riconciliare lo snapshot prima di inviarlo, o il backend lo rifiuta con 400
- un salvataggio che il server rifiuta non va mai committato localmente
- il tetto di 20 voci è applicato sia lato client sia lato server

- [ ] **Step 2: Scrivere `docs/frontend/RETTIFICHE.md`**

Struttura: cosa sono le rettifiche e a cosa servono · le due sotto-tab (storico / bilancio di verifica) e perché ne servono due · la partita doppia e il selettore contropartita · la persistenza (`original_*_snapshot`, `rettifiche_log`) · il ciclo per-edit · i file chiave. Include i fatti marcati `SPOSTATA IN`.

- [ ] **Step 3: Sostituire in `CLAUDE.md` con un rimando di ≤ 8 righe**

Cosa sono, dove vivono (`components/pratica/RettificheTab.tsx`, `hooks/use-rettifiche-year.ts`), e il rimando con la domanda: «Il giornale delle rettifiche si comporta male? → `docs/frontend/RETTIFICHE.md`».

- [ ] **Step 4: Verificare e commit**

```bash
wc -l CLAUDE.md
grep -o "](docs/[^)]*)" CLAUDE.md | tr -d '](' | while read f; do [ -f "$f" ] || echo "ROTTO: $f"; done
git diff --stat
git add CLAUDE.md docs/frontend/RETTIFICHE.md docs/superpowers/2026-08-14-inventario-claude-md.md
git commit -m "docs(claude): le rettifiche hanno la loro pagina"
```

---

## Task 3: Il percorso Pratica (197 righe) → `docs/frontend/PRATICA-PERCORSO.md`

**Files:**
- Create: `docs/frontend/PRATICA-PERCORSO.md`
- Modify: `CLAUDE.md` (`### Il percorso unico "Pratica" (2026-08-08)`), l'inventario

- [ ] **Step 1: Classificare il blocco nell'inventario**

È il blocco più lungo dei tre frontend e contiene molta **storia** (la nota «Superseded note, kept for history», le review del 2026-08-08, la mutation coverage misurata). La storia va spostata, non cancellata: è la traccia del perché una scelta è stata fatta.

Candidati `RESTA` da verificare nel codice:
- `PraticaProvider` sta SOPRA `AppProvider` in `app/layout.tsx`: è ciò che permette a `AppContext` di chiamare `usePratica()`
- il `localStorage` si legge in un `useEffect`, mai nell'inizializzatore di `useState`, o Next sbaglia l'idratazione
- `lib/pratica-*` non importa mai da `app/` o `components/`
- il gate delle rettifiche legge la cache dello stepper, non il server: **non è un confine di autorizzazione**

- [ ] **Step 2: Scrivere `docs/frontend/PRATICA-PERCORSO.md`**

Struttura: i due workflow · il modello a tre fasi (`lib/pratica-steps.ts`, `phase`, `group`, gate) · lo stepper e la barra azioni · i moduli di `lib/pratica-*` e la regola di dipendenza · la reidratazione dopo un refresh · i limiti noti misurati (mutation coverage al 18%, la nota su `buildIncomeItemsWithEbitda` con parametri morti).

- [ ] **Step 3: Sostituire in `CLAUDE.md` con un rimando di ≤ 12 righe**

I due workflow, le tre fasi in una riga, i file chiave, e il rimando.

- [ ] **Step 4: Verificare e commit**

```bash
wc -l CLAUDE.md
grep -o "](docs/[^)]*)" CLAUDE.md | tr -d '](' | while read f; do [ -f "$f" ] || echo "ROTTO: $f"; done
git diff --stat
git add CLAUDE.md docs/frontend/PRATICA-PERCORSO.md docs/superpowers/2026-08-14-inventario-claude-md.md
git commit -m "docs(claude): il percorso pratica ha la sua pagina"
```

---

## Task 4: Layout SP/CE (110 righe) → `docs/frontend/LAYOUT-SP-CE.md`

> **Fatto il 2026-08-15.** Righe 198-222 dell'inventario. Tre `OBSOLETA`: le viste non rendono
> «lo stesso layout» (quattro elenchi diversi su sette superfici, 92 / 87 / 97 codici); il rientro
> è del catalogo **solo** in Rettifiche, le altre quattro viste usano tre regole proprie; e
> `ALL_CODES` non sta nelle rules né è chiuso a quegli elenchi. La tabella dei quattro file regge,
> ma i file sono **sei**: manca `pratica-reconcile.ts` (una sotto-voce non registrata lì viene
> contata due volte, misurato) e gli elenchi congelati del test di parità. Otto conteggi
> ri-verificati, tutti confermati. Cinque righe `RESTA` aggiunte a «Invarianti e trappole».

**Files:**
- Create: `docs/frontend/LAYOUT-SP-CE.md`
- Modify: `CLAUDE.md` (`### Shared BS/IS Layout ...`), l'inventario

- [ ] **Step 1: Classificare il blocco nell'inventario**

Candidato `RESTA` quasi certo, da verificare: **aggiungere una sotto-voce tocca QUATTRO file**, non uno — `pratica-rettifiche-rules.ts` (`ALL_CODES`), `pratica-codes.ts` (`DETAIL_PARENTS`), `ivcee-catalog.ts` (etichetta + riga di prospetto), `pratica-statement-rows.ts` (elenco del Confronto). È esattamente il tipo di fatto che, se non lo sai, produce una voce che non compare da nessuna parte senza alcun errore.

Attenzione: quel blocco contiene già una **autocorrezione** (una versione precedente diceva che bastava toccare un file solo). Conservala: è la prova che la documentazione può mentire, e questo file la usa come monito.

- [ ] **Step 2: Scrivere `docs/frontend/LAYOUT-SP-CE.md`**

Struttura: il catalogo IV-CEE unico e le due etichette (autonoma/contestuale) · la tabella dei quattro file · le tre superfici di naming ancora non unificate · i blocchi di dettaglio (sp04, sp06/07, sp12, sp16/17, ce08/09/17) · il test di parità e cosa significa quando diventa rosso.

- [ ] **Step 3: Sostituire in `CLAUDE.md` con un rimando di ≤ 10 righe**

Deve contenere **la tabella dei quattro file**, perché è un invariante operativo: chi aggiunge una voce senza saperlo produce un bug silenzioso.

- [ ] **Step 4: Verificare e commit**

```bash
wc -l CLAUDE.md
grep -o "](docs/[^)]*)" CLAUDE.md | tr -d '](' | while read f; do [ -f "$f" ] || echo "ROTTO: $f"; done
git diff --stat
git add CLAUDE.md docs/frontend/LAYOUT-SP-CE.md docs/superpowers/2026-08-14-inventario-claude-md.md
git commit -m "docs(claude): il layout SP/CE ha la sua pagina"
```

---

## Task 5: Tab minori, Upload Tracking, API budget (~125 righe)

**Files:**
- Create: `docs/deployment/UPLOAD-TRACKING.md`
- Modify: `CLAUDE.md` (Projection Tab, Indicatori charts, Infrannuale AI Comments, Upload Tracking, Bulk Assumptions, Promote, Editable Forecast CE Overrides), `docs/frontend/INDICATORI-E-STAMPA.md`, `docs/budget/`, l'inventario

- [ ] **Step 1: Classificare i sette blocchi nell'inventario**

Destinazioni previste (da confermare leggendo i file):
- Projection Tab → `docs/frontend/PRATICA-PERCORSO.md` (Task 3)
- Indicatori charts → `docs/frontend/INDICATORI-E-STAMPA.md`, che esiste già
- Infrannuale AI Comments → `docs/frontend/PRATICA-PERCORSO.md`
- Upload Tracking → `docs/deployment/UPLOAD-TRACKING.md` (nuovo)
- Bulk Assumptions · Promote · CE Overrides → `docs/budget/`, dove esistono già `TEST_BUDGET_API.md` e `FORECASTING_GUIDE.md`

Candidato `RESTA`: chi chiama le assumptions bulk deve leggere **`forecast_generated`**, non l'HTTP 200 — il server risponde 200 con `forecast_generated: false` e la colonna Proiezione resta vuota sotto un toast di successo.

- [ ] **Step 2: Applicare, e ridurre in `CLAUDE.md`**

`CLAUDE.md` conserva **tre righe** su Upload Tracking (`ADMIN_API_KEY`, il percorso di storage, la ritenzione), perché servono a orientarsi e non si trovano da soli.

- [ ] **Step 3: Verificare e commit**

```bash
wc -l CLAUDE.md
grep -o "](docs/[^)]*)" CLAUDE.md | tr -d '](' | while read f; do [ -f "$f" ] || echo "ROTTO: $f"; done
git diff --stat
git add CLAUDE.md docs/ && git commit -m "docs(claude): tab, upload tracking e API budget nelle loro pagine"
```

---

## Task 6: Le due sezioni nuove — «Invarianti e trappole» e «Mappa della documentazione»

> **Eseguito il 2026-08-15 con le sole righe del Task 1, e quindi da RIAPRIRE.** Il vincolo di
> rilascio ha avuto la precedenza sull'ordine: fino a questo task gli invarianti dell'import
> vivevano solo nell'inventario, che non è auto-caricato, e `CLAUDE.md` non era spingibile.
> 21 righe `RESTA` su 24 sono nella nuova sezione; le altre 3 erano già nella sezione «Import
> PDF». **Ogni Task 2-5 produrrà nuove righe `RESTA` e dovrà tornare qui.** Vedi la sezione
> «Task 6 — eseguito in anticipo» in coda all'inventario.

**Files:**
- Modify: `CLAUDE.md`
- Read: `docs/superpowers/2026-08-14-inventario-claude-md.md`

**Interfaces:**
- Consumes: **tutte** le righe marcate `RESTA` nell'inventario dai Task 1-5. È questo il momento in cui il portatore scarica il suo carico.

- [ ] **Step 1: Raccogliere le righe `RESTA`**

```bash
grep -n "RESTA" docs/superpowers/2026-08-14-inventario-claude-md.md
```
Ogni riga trovata deve comparire nella nuova sezione. Se una non ci sta, o non era un invariante (e va riclassificata nell'inventario, con la motivazione) oppure la sezione è incompleta. Non lasciarne cadere nessuna in silenzio.

- [ ] **Step 2: Scrivere «Invarianti e trappole»**

Subito dopo `## Key Conventions`. Ogni voce: la regola, e **cosa si rompe** ignorandola. Una o due righe. Raggruppate per area (contabilità · import · forecast · frontend · ambiente), non per file di provenienza.

Il modello, dalla spec:

```markdown
## Invarianti e trappole

Le regole che, se ignorate, producono un danno **silenzioso**: il dato risulta sbagliato e
nessun controllo se ne accorge. Il resto della documentazione spiega i meccanismi; questa
sezione elenca ciò che non si può non sapere.

### Contabilità
- La **colonna** è la verità sul lato; la **descrizione** decide la voce. Mai il contrario.
- **Diagnose, never fabricate**: un divario si misura e si dichiara, non si tappa.
- Debiti senza scadenza dichiarata → **a breve** (prudenziale). `sp16` e `sp17` stanno
  entrambi nel passivo: il pareggio non vede l'appiattimento, gli indici di liquidità sì.
...
```

- [ ] **Step 3: Scrivere «Mappa della documentazione»**

In coda al file. Una riga per destinazione, ciascuna con **la domanda** a cui quella pagina risponde. Non «vedi docs/import/», ma «un bilancio non quadra e non capisci perché? → …». Deve coprire ogni file creato o toccato nei Task 1-5.

- [ ] **Step 4: Verificare e commit**

Ogni riga `RESTA` dell'inventario compare nella sezione. Ogni link risolve.

```bash
grep -o "](docs/[^)]*)" CLAUDE.md | tr -d '](' | while read f; do [ -f "$f" ] || echo "ROTTO: $f"; done
git diff --stat
git add CLAUDE.md docs/superpowers/2026-08-14-inventario-claude-md.md
git commit -m "docs(claude): gli invarianti in una sezione sola, e una mappa per il resto"
```

---

## Task 7: Compressione delle sezioni superstiti e verifica finale

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Comprimere ciò che è rimasto**

Le sezioni non toccate dai Task 1-5 (`Project Overview`, `Quick Reference`, `Development Commands`, `Architecture`, `Key Conventions`, `Technical Constraints`, `Development Workflow`, `Common Tasks`, `API Migration Notes`) vanno riviste con lo stesso criterio: resta orientamento e invariante, va via la spiegazione.

Casi noti: `Development Workflow` (83 righe) ripete esempi di codice già presenti in `Quick Reference`; `API Migration Notes` elenca endpoint deprecati da anni. FGPMI, Forecasting Engine e Intra-Year Engine **restano** ma compressi: 24% IRES, split variabile/fisso 60/40, cassa come plug sono convenzioni, non dettagli.

- [ ] **Step 2: Verifica finale**

```bash
wc -l CLAUDE.md                     # DEVE essere < 500
# ogni link relativo risolve:
grep -o "](docs/[^)]*)" CLAUDE.md | tr -d '](' | while read f; do [ -f "$f" ] || echo "ROTTO: $f"; done
# ogni file di codice nominato esiste:
grep -oE "\`[a-zA-Z0-9_/.-]+\.(py|ts|tsx|json)\`" CLAUDE.md | tr -d '`' | sort -u | while read f; do [ -e "$f" ] || echo "MANCA: $f"; done
```

`ROTTO` e `MANCA` devono essere vuoti. Un `MANCA` può essere un percorso relativo a `frontend/` — verificare a mano prima di correggere.

Poi la verifica di sostanza: ogni riga `GIÀ IN` / `SPOSTATA IN` dell'inventario trova riscontro nel file di destinazione. A campione su dieci, `git grep` di una frase chiave restituisce **un solo** posto.

- [ ] **Step 3: Commit**

```bash
git diff --stat
git add CLAUDE.md
git commit -m "docs(claude): comprimere le sezioni superstiti, sotto le 500 righe"
```

---

## Note di esecuzione

- **L'ordine dei task non è negoziabile.** Il Task 6 raccoglie le righe `RESTA` prodotte dai Task 1-5: eseguirlo prima significherebbe costruire la sezione invarianti su un inventario incompleto.
- **Il numero di righe non è l'obiettivo.** Se al Task 7 il file è a 520 righe e ogni riga supera il criterio, va bene: si segnala e si spiega. Tagliare un invariante per rientrare in una soglia è il fallimento di questo lavoro, non il suo successo.
- **Quando una voce risulta `OBSOLETA`, la prova va nell'inventario**, non nel messaggio di commit: il commit si perde nel log, l'inventario resta accanto alla spec.
