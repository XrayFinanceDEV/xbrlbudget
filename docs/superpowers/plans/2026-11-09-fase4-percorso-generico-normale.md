# Fase 4 — il percorso generico diventa quello normale — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fare del percorso del lettore la strada normale dopo i lettori deterministici: il lettore adotta anche gli
schemi di legge e i documenti che oggi rifiutiamo a torto. Si misura che cosa aggiunge ancora il percorso classico,
il modello smette di scrivere importi dove il lettore può leggerli, e i parser di layout vecchi si congelano.

**Architecture:** la catena resta *lettori deterministici → percorso del lettore → modello snello → classico*. Questa
fase lavora sui due anelli dopo il lettore. Il modello snello in modo `legge` (Qwen restituisce `[percorso, importo]`,
`lettura.voci_di_legge`) e il ripiego classico (`pdf_importer`, esito snello `ripiego`/`non_applicabile`) si
restringono, ognuno con un interruttore e una misura. Si spengono di default solo per decisione del proprietario
presa sui numeri.

**Tech Stack:** Python 3, PyMuPDF, `importers/lettore/*`, `importers/import_snello/*`, `importers/pdf_importer.py`,
Qwen su gx10 (`llm_provider.chiama_gx10_json`), pytest, `tests/corpus/punteggio.py` (worktree `budget-punteggio`).

**Spec:** la sezione «Phase 4 — Make the generic path the default, freeze the rest» della revisione
https://claude.ai/artifact/ByQZE4SXdTd4TbeVVX6Yxy (aggiornata il 2026-11-09). Decisioni del proprietario in memoria:
`prima-quadrato-poi-dettagli`, `debiti-senza-scadenza-a-breve`, `regole-classificazione-2026-10-28`. La Fase 3
(`docs/superpowers/plans/2026-11-06-fase3-lettore-decide-gli-importi.md`, ledger e `final-review.md` nella sua
cartella SDD) è il punto di partenza.

**Stato di partenza misurato** (giro `fase3-4de18b6`, 78 documenti × 3, main 5817f8b):

| Strada che ha salvato | Documenti |
|---|---|
| lettori deterministici | 54 |
| percorso del lettore | 11 (1432, 1440, 1450, 1523, 1528, 1531, 1552, 1555, 1561, 1566, 1567) |
| modello snello, modo `legge` (Qwen scrive gli importi) | 6: 161, 1407, 1426, 1445, 1533, 1553 (tutti sbilanciati tranne 1407) |
| classico | 1540 (3 giri), 1426 (1 giro); scansioni via MinerU fuori dallo snello: 1319, 1322, 1419 |
| rifiutati ma attesi importabili | 1562, 1565 (conti/colonne, «nessuno scheletro di legge né elenco conti») |

**Fuori da questa fase, apposta:**
- **La cache delle risposte prevista dalla revisione c'è già dentro il documento.** `classifica_macro` e
  `classifica_dettagli` chiedono una volta sola la stessa (etichetta, lato, sezione). Una cache fra un import e
  l'altro non si fa: renderebbe uguali i 3 giri del punteggio e nasconderebbe la variabilità che il punteggio deve
  misurare.
- **Spegnere il classico e il modo `legge` di default** è una decisione del proprietario dopo i Task 2 e 7, non un
  task.

## Global Constraints

- Valgono tutti i vincoli della Fase 3: `.superpowers/sdd/2026-11-06-fase3-lettore-decide-gli-importi/vincoli-globali.md`,
  con l'aggiornamento del 2026-11-09 (dettagli massimi, contro-conti nettati con la logica esistente).
- **Gli importi vengono solo dal testo** (o dalle celle MinerU) tramite il lettore. Ogni modifica di questa fase che
  sposta un documento dal modo `legge` al lettore toglie a Qwen un importo, non gliene dà uno nuovo.
- **Debito senza scadenza stampata → a breve**, mutui e finanziamenti compresi (CLAUDE.md, 2026-11-09).
- **Un interruttore per ogni cosa che si spegne**, letto come `IMPORT_LETTORE`: `0`/`false`/`no`/`off` spengono.
  Il default cambia solo con un sì del proprietario dopo la misura. Con l'interruttore al valore di oggi, il percorso
  di oggi resta identico (test).
- **I lettori deterministici restano davanti e i loro numeri non cambiano** (punteggio: «Numeri invariati»).
- **Nessuna regola legata a un id di documento**; ogni regola nuova ha un test sintetico che fallisce prima; una
  soglia ha la sua ragione nel codice.
- **Dati dei clienti mai in git**: cifre ed etichette reali solo nei rapporti della cartella SDD; nei test PDF
  sintetici e nomi inventati (lezione I2 della revisione finale della Fase 3).
- Codice, test e commenti in italiano; importi `Decimal`; DB su copia (`DATABASE_PATH`, `BUDGET_REAL_DB`); mai
  `pytest tests` intero; mai `ANTHROPIC_CONSENTITO`; gx10 solo con `strumenti/con_gx10.sh` (chiavi mai su riga di
  comando né stampate); niente git stash né `git add -A`.
- Branch `feat/fase4-generico` da `main` 5817f8b; merge e push solo su richiesta del proprietario.

## Review Focus

1. **Uno schema di legge in cui il lettore legge le didascalie ma non gli importi di una colonna** (per esempio il
   precedente in un'altra pagina): il lettore adotta solo se la colonna corrente quadra; il precedente senza importi
   letti resta assente o passa per il cancello come oggi, mai preso dal modello. Test nel Task 3.
2. **Un documento che oggi salva il classico e che, a classico spento, non ha altra strada**: deve uscire con un
   errore chiaro (`PDFImportError` che dice perché), mai con un foglio vuoto salvato. Test nel Task 1.
3. **Uno schema di legge abbreviato** (voci aggregate tipo «C.II Crediti» senza sotto-voci): le classi restano a
   livello di macro e il dettaglio va in «altri», senza inventarne uno. Test nel Task 3.
4. **Una didascalia di legge che il modello classifica contro il percorso stampato** («B.II.2 Impianti» nominato
   sp02): vince il percorso legale stampato (`classifica._da_percorso`), il modello non viene chiesto. Test nel Task 3.
5. **Un'etichetta che le parole chiave mandano in una voce e il modello in un'altra**: l'indizio entra nella domanda,
   ma decide il modello dentro le classi ammesse; un indizio che contraddice il lato della colonna non entra mai.
   Test nel Task 4.

---

### Task 1: interruttore del ripiego classico e motivo dichiarato

**Files:**
- Modify: `importers/pdf_importer.py` (blocco «Import snello», righe ~1421-1530, e il percorso MinerU che salta lo
  snello con esito `non_applicabile`)
- Test: `tests/test_ripiego_classico.py` (nuovo)

**Interfaces:**
- Produces: `pdf_importer._ripiego_classico_acceso() -> bool` (env `IMPORT_RIPIEGO_CLASSICO`, default acceso).
- Produces: `validation_report["import_snello"]["ripiego_classico"]`: dict sempre presente, anche quando il classico
  non gira, con `{"usato": bool, "motivo": str | None}`. Il motivo è uno di `"ripiego"`, `"non_applicabile"`,
  `"eccezione"`, `"scansione_non_quadra"`, `"motore_classico"`.

- [ ] **Step 1: inventario.** Elenca nel rapporto ogni punto in cui l'import passa dallo snello al classico, compreso
  il ramo MinerU/scansioni che dà `mineru+xbrl_reso`, `mineru+schema_etichette` e `mineru+situazione_contabile_llm`.
  Per ciascuno: condizione, file:riga, documenti del campione che ci passano (dagli `esiti.jsonl` di
  `fase3-4de18b6`).
- [ ] **Step 2: test che falliscono:**
  - `test_ripiego_dichiarato_anche_quando_non_usato`: un PDF sintetico adottato dallo snello porta
    `ripiego_classico == {"usato": False, "motivo": None}`;
  - `test_classico_spento_errore_chiaro`: con `IMPORT_RIPIEGO_CLASSICO=0` e snello in `ripiego` (monkeypatch),
    `import_pdf_balance_sheet` solleva `PDFImportError`, il messaggio contiene «percorso classico spento» e nessun
    `FinancialYear` viene salvato;
  - `test_classico_acceso_identico`: con l'interruttore assente, il percorso di oggi chiama il classico come prima.
- [ ] **Step 3:** implementa interruttore e chiave nel punto unico in cui lo snello cede al classico (uno per ramo
  dell'inventario).
- [ ] **Step 4:** fai girare `tests/test_ripiego_classico.py`, `tests/test_snello_*`, `tests/test_pdf_ocr_endpoint.py`
  e `tests/test_unbalanced_import.py` su DB copia: tutto PASS.
- [ ] **Step 5:** commit `feat(import): interruttore del ripiego classico, motivo sempre dichiarato`.

### Task 2: misura senza il classico (coordinatore)

**Files:**
- Modify (worktree `budget-punteggio`, branch `feat/punteggio-fase0`): `tests/corpus/punteggio.py`, che aggiunge alla
  sezione «Percorso del lettore» la riga «Ripiego classico usato: giri / documenti / motivi».
- Create: `Test/_analisi-campione/lancia_fase4-senza-classico.sh` (fuori da git, copia di `lancia_fase3c.sh` con
  `IMPORT_RIPIEGO_CLASSICO=0`).

- [ ] **Step 1:** fai il merge di `feat/fase4-generico` in `feat/punteggio-fase0` e aggiungi la riga del rapporto,
  con un test in `tests/corpus/test_punteggio*.py`.
- [ ] **Step 2:** lancia il giro 78×3 con etichetta `fase4-senza-classico-<sha>`, `--confronta fase3-4de18b6`
  (`setsid nohup`).
- [ ] **Step 3:** scrivi nel ledger, per ogni documento che a classico spento cambia esito o punteggio, il prima e il
  dopo.
- [ ] **Step 4 (decisione del proprietario):** presenta la tabella. Il default di `IMPORT_RIPIEGO_CLASSICO` resta
  acceso finché il proprietario non decide; i Task 3-4 servono anche a ridurre i documenti che dipendono dal classico.

### Task 3: gli schemi di legge sul lettore (diagnosi e correzione, opus)

**Files:**
- Modify: i moduli del lettore dove sta la causa (`importers/lettore/foglie.py`, `classifica.py`, `componi.py`,
  `percorso.py`, `profilo.py`, `totali.py`), da scegliere dalla diagnosi
- Modify: `importers/import_snello/__init__.py` (`importa`), solo se un documento rifiutato prima dello snello
  (1562, 1565) deve arrivare al lettore
- Test: `tests/lettore/test_*.py` del modulo toccato

**Interfaces:**
- Consumes: `percorso.importa_col_lettore`, `deterministico.esito`, `classifica._da_percorso` (Fase 3).
- Produces: nessuna interfaccia nuova; `lettore_percorso.motivo` resta l'elenco di oggi più eventuali motivi nuovi,
  documentati in REGOLE-IMPORT-02 §11.

- [ ] **Step 1: diagnosi** su 161, 1407, 1426, 1445, 1533, 1553 (modo `legge`), 1540 (classico), 1562 e 1565
  (rifiutati), con `strumenti/` della Fase 3 e `con_gx10.sh`. Le cifre vanno solo nel rapporto. Per ognuno scrivi
  perché il percorso del lettore non adotta:
  - foglie non in pari;
  - massa non classificata;
  - un'ancora che non torna, e quale;
  - colonna sbagliata;
  - documento rifiutato prima.
  Indica anche la causa generale.
- [ ] **Step 2: test sintetici che falliscono**, uno per causa generale trovata, più i tre del Review Focus (1, 3, 4):
  - `test_legge_precedente_senza_importi_non_dal_modello`;
  - `test_legge_abbreviato_dettaglio_in_altri`;
  - `test_legge_percorso_stampato_vince_sul_modello`.
- [ ] **Step 3: correzioni generali**, una per commit. Non si tocca il cancello `deterministico.esito`.
- [ ] **Step 4: misura prima/dopo**, un import di produzione per ciascuno dei 9 documenti più gli 11 già adottati:
  - adottato sì/no;
  - salvato quadrato sì/no;
  - macro, KPI e dettagli contro la verità;
  - chiamate e secondi.
  Nessuno degli 11 deve perdere l'adozione o la quadratura.
- [ ] **Step 5:** fai girare `tests/lettore`, `tests/test_snello_*` e `tests/test_schema_legge_mineru.py` su DB copia:
  tutto PASS.
- [ ] **Step 6:** commit (uno per correzione) e `task-3-report.md`.

### Task 4: le parole chiave come indizio nella domanda al modello

**Files:**
- Modify: `importers/lettore/classifica.py` (`_contesto`, `_richiesta`)
- Modify: `importers/lettore/_ereditati.py` (accesso ai classificatori a parole chiave, con test di deriva)
- Test: `tests/lettore/test_classifica.py`

**Interfaces:**
- Produces: `classifica.indizio(f: Foglia) -> str | None`, cioè la macro-voce che i classificatori a parole chiave di
  oggi danno all'etichetta: `situazione_contabile_parser._resolve_ce_field(desc, direction)` per il CE e le regole SP
  di route C per lo SP, filtrata con `_ammesse(f)`. `None` se le parole chiave non decidono o se l'esito non è
  ammesso per il lato della colonna.

- [ ] **Step 1: test che falliscono:**
  - `test_indizio_entra_nella_domanda`: per un'etichetta «carburanti» sul lato costi, la richiesta contiene
    l'indizio `ce05`;
  - `test_indizio_contro_il_lato_scartato`: un indizio di un campo del passivo su una foglia dell'attivo dà `None`;
  - `test_decide_il_modello`: con indizio `ce05` e risposta del modello `ce06`, la classe è `ce06`.
- [ ] **Step 2:** implementa `indizio` e l'aggiunta nel contesto della richiesta. È una riga «indizio dalle parole
  chiave: <campo>» per id, mai un vincolo dell'enum.
- [ ] **Step 3: misura prima/dopo**, un import ciascuno, sugli 11 adottati e sui documenti adottati nel Task 3.
  Riporta macro e KPI, con attenzione a ce05/ce06 (1561) e A.1/A.5 (1567). Se il totale macro+KPI scende, l'indizio
  non resta: revert e rapporto.
- [ ] **Step 4:** fai girare `tests/lettore` e `tests/test_lettore_ereditati*` su DB copia: tutto PASS.
- [ ] **Step 5:** commit `feat(lettore): le parole chiave di oggi come indizio nella domanda, decide il modello`.

### Task 5: una tavola di destinazione sola

**Files:**
- Modify: `importers/lettore/tavola.py`, `importers/import_snello/percorsi.py`; `data/iv_cee_tree.json` solo per
  correggere un campo di destinazione, **mai per aggiungere alias** (CLAUDE.md: raddoppia gli importi delle route A/B)
- Test: `tests/test_tavola_unica.py` (nuovo)

**Interfaces:**
- Produces: `tavola.campo_di_legge(percorso: str) -> str | None`, la sola funzione percorso di legge → campo usata
  dal lettore, da `conti.py` e da `schema_etichette_parser`; `percorsi.campo_da_percorso` la richiama.

- [ ] **Step 1: test che fallisce** `test_albero_e_percorsi_concordano`: per ogni nodo di livello legale di
  `iv_cee_tree.json` che ha un campo, `campo_di_legge(percorso del nodo)` restituisce lo stesso campo. Elenca nel
  rapporto le discordanze trovate, incluso il conflitto A.3/A.4 annotato in `tavola.py`.
- [ ] **Step 2:** risolvi ogni discordanza secondo le colonne del DB (`database/models.py`: `ce03` = A.3,
  `ce03a` = A.4), una per commit, dicendo nel commit quale lettore cambia numeri.
- [ ] **Step 3:** fai passare i chiamanti da `campo_di_legge`; togli la nota «iv_cee_tree.json resta com'e' (Fase 4)»
  da `tavola.py`.
- [ ] **Step 4:** fai girare `tests/test_tavola_unica.py`, `tests/lettore`, `tests/test_snello_*`,
  `tests/test_schema_etichette*` e `tests/test_iv_cee_hierarchy*` su DB copia: tutto PASS.
- [ ] **Step 5:** commit.

### Task 6: congelare i parser di layout

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (intestazione del modulo)
- Modify: `CLAUDE.md` (invariante in «Estrazione e classificazione»), `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md`
- Test: `tests/test_parser_layout_congelati.py` (nuovo)

**Interfaces:**
- Produces: `situazione_contabile_parser.PARSER_DI_LAYOUT: tuple[str, ...]`, l'elenco congelato dei nomi delle
  funzioni di layout (AGO, DEPI, TeamSystem, SEZBIL e le altre, enumerate dall'implementatore).

- [ ] **Step 1: test che fallisce** `test_nessun_parser_di_layout_nuovo`: le funzioni del modulo riconosciute come
  parser di layout (criterio scritto nel test, per esempio i dispatch del riconoscimento del formato) sono esattamente
  `PARSER_DI_LAYOUT`. Un parser nuovo fa fallire il test, che dice di andare nel percorso generico.
- [ ] **Step 2:** aggiungi `PARSER_DI_LAYOUT` e l'intestazione «congelato dal 2026-11: solo correzioni di errori; un
  layout nuovo va nel lettore (`importers/lettore`)».
- [ ] **Step 3:** aggiungi a CLAUDE.md, in «Estrazione e classificazione», una voce che dica la regola e che cosa si
  rompe a violarla. Aggiorna il §11 di REGOLE-IMPORT-02.
- [ ] **Step 4:** il test passa.
- [ ] **Step 5:** commit `chore(import): i parser di layout di route C sono congelati`.

### Task 7: misura finale e chiusura (coordinatore)

- [ ] **Step 1:** fai il merge in `feat/punteggio-fase0` e lancia il giro 78×3 `fase4-<sha>` `--confronta fase3-4de18b6`
  con gli interruttori al default.
- [ ] **Step 2: criteri:**
  - nessun documento oggi adottato da un lettore deterministico cambia numeri;
  - documenti salvati dal modo `legge` da 6 ad al massimo 3;
  - macro e KPI non scendono sotto 80,6% / 80,3%;
  - documenti salvati sbilanciati ≤ 7;
  - nessun bersaglio della Fase 3 perde la quadratura.
  Un criterio mancato si spiega nel ledger.
- [ ] **Step 3:** scrivi la misura in REGOLE-IMPORT-02 §11 e REGOLE-IMPORT-04 §14, e aggiorna la pagina di revisione.
- [ ] **Step 4:** revisione finale di tutto il branch su opus, una tornata di correzioni, poi merge e push solo su
  richiesta del proprietario.
