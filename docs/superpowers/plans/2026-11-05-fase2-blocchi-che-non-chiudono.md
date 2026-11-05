# Fase 2 — Il lettore nell'import: blocchi che non chiudono — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ogni import di un PDF passa anche dal lettore di righe della Fase 1, che **non cambia nessun numero** ma
dice per nome, colonna e righe quali totali stampati non chiudono; quando il bilancio importato non quadra,
l'utente vede quei blocchi nell'avviso invece del solo «SP sbilanciato di N €».

**Architecture:** Tre passi. (1) Il pacchetto `importers/lettore/` si stacca dai nomi privati dei moduli vecchi
(R24 della Fase 1), così una correzione al percorso attuale non lo cambia in silenzio. (2) Un modulo nuovo,
`importers/lettore/blocchi.py`, trasforma un `Documento` in un elenco di blocchi aperti (voce stampata, colonna,
periodo, importo stampato, somma dei figli, scarto, righe dalla prima all'ultima), solo dalle righe di prospetto.
(3) `pdf_importer.import_pdf_balance_sheet` chiama il lettore **dopo** l'estrazione, in un `try` che non può far
fallire l'import, e scrive il risultato in `validation_report["lettore"]`; gli avvisi per l'utente si aggiungono
solo quando l'import stesso dichiara uno sbilancio. La classificazione dei conti resta all'importatore di oggi
(è la Fase 3).

**Tech Stack:** Python 3.12, PyMuPDF, `decimal.Decimal`, pytest; nessuna dipendenza nuova, nessuna chiamata a
modelli in più.

**Spec:** la review «Generic Importer Gap Review» (https://claude.ai/artifact/ByQZE4SXdTd4TbeVVX6Yxy), «Phase 2 —
The row tree and per-block checks»; il §11 «Lettore di righe unico (Fase 1)» di
`docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md`, paragrafo «Per chi integra»; il ledger della Fase 1
`.superpowers/sdd/2026-11-04-fase1-lettore-righe/progress.md` (decisioni R1-R24, limiti noti). Leggere i tre.

## Global Constraints

- **Nessun numero importato cambia.** SP, CE, anno precedente, esito (importato / rifiutato), metodo e periodo
  restano quelli del percorso di oggi; il lettore aggiunge solo chiavi di diagnostica e avvisi. Verificato col
  punteggio (Task 5): stessi valori dei giri deterministici della base `base-fase2-e3455d6`.
- **Il lettore non fa mai fallire un import.** Qualunque eccezione, o un tempo oltre `LETTORE_TETTO_SECONDI`
  (default 20 s), si dichiara in `validation_report["lettore"] = {"esito": "errore"|"tempo", "motivo": ...}` e
  l'import prosegue identico.
- **Diagnose, never fabricate** (CLAUDE.md): un blocco aperto si misura e si dichiara, non si tappa; nessuna
  correzione automatica degli importi.
- **Un estrattore dichiara sempre le proprie chiavi, anche a zero** (CLAUDE.md): `validation_report["lettore"]`
  c'è a ogni import di un PDF, anche con `blocchi_aperti: []`; un import senza lettore (XBRL, CSV) non ha la chiave.
- **Solo righe di prospetto** (`Documento.righe_del_prospetto()`), avvisi da `Documento.tutti_gli_avvisi()`,
  risomme con `valore_nel_totale`: le tre trappole del §11 «Per chi integra».
- **Parentela solo dalle somme stampate**, mai dal codice (CLAUDE.md); un blocco «aperto» è un totale stampato i
  cui figli non tornano, mai un'ipotesi del lettore non verificata.
- Interruttore `LETTORE_DIAGNOSI` (default acceso; `0`/`off` lo spegne del tutto, nessuna chiave scritta).
- Lavoro sul branch `feat/fase2-blocchi`; merge e push su richiesta del proprietario.
- I test non toccano `Test/`, usano PDF sintetici in `tmp_path` e il DB su una copia (`DATABASE_PATH`).
- Avvisi in italiano, nello stile degli avvisi esistenti di `pdf_importer.py` (prefisso in maiuscolo, frase che
  dice che cosa verificare in Rettifiche).

## Review Focus

1. **Un import già sbilanciato da un difetto di un altro lettore**: il blocco nominato deve essere uno dei
   totali stampati che il lettore vede aperti, non un'ipotesi; se il lettore non trova blocchi aperti, l'avviso
   di oggi resta da solo, senza frasi inventate. Test in Task 4.
2. **Un documento lungo** (oltre 80 pagine, nota integrativa compresa): il tetto di tempo scatta e l'import
   prosegue. Test in Task 4.
3. **Una scansione** (MinerU): il lettore gira su `leggi_celle` con le tabelle del contesto, non sul PDF senza
   testo; senza tabelle si dichiara `non_applicabile`. Test in Task 4.
4. **Colonne con un ruolo sbagliato** (differenza, percentuale lette come esercizio, limite noto della Fase 1):
   un blocco aperto su una colonna che non è `corrente` né l'anno precedente salvato non va nell'avviso
   all'utente. Test in Task 3.
5. **Il percorso di oggi cambia una correzione nei moduli vecchi**: il lettore non deve cambiare. Test in Task 1.

---

## File Structure

| File | Responsabilità |
|---|---|
| `importers/lettore/_ereditati.py` | Le copie dei 14 nomi privati presi dai moduli vecchi, con la provenienza |
| `tests/lettore/test_ereditati.py` | Test di deriva: copia e originale danno lo stesso risultato su casi fissi |
| `importers/lettore/blocchi.py` | `Blocco`, `blocchi_aperti(doc)`, `frase_blocco(b)` |
| `tests/lettore/test_blocchi.py` | Test dei blocchi su PDF sintetici |
| `importers/lettore/diagnosi.py` | `diagnosi_pdf(file_path, contesto_mineru, anni)` → dict JSON per `validation_report["lettore"]` |
| `importers/pdf_importer.py` | Chiamata a `diagnosi_pdf` e avvisi per l'utente |
| `tests/test_lettore_nell_import.py` | L'import con e senza lettore: stessi numeri, chiave dichiarata, avvisi |
| `tests/corpus/punteggio.py` (branch `feat/punteggio-fase0`) | Misura dei blocchi nominati e controllo «numeri invariati» |
| `docs/import/REGOLE-IMPORT-04-QUADRATURE.md` | Sezione «Blocchi che non chiudono (Fase 2)» |

---

### Task 1: Il lettore si stacca dai nomi privati dei moduli vecchi

**Files:**
- Create: `importers/lettore/_ereditati.py`, `tests/lettore/test_ereditati.py`
- Modify: `importers/lettore/righe.py`, `colonne.py`, `celle.py`, `totali.py`, `profilo.py` (solo gli import)

**Interfaces:**
- Consumes: i nomi oggi importati da `importers.schema_legge_generico` (`_forma_strutturale`, `_intestazione`,
  `_PAROLE_TESTATA`, `_e_differenza`, `_PIEDE`), `importers.xbrl_reso_parser` (`_frase_aperta`,
  `_FASCIA_MARGINE`, `_chiave_ripetuta`), `importers.standard_ivcee_parser` (`_AMOUNT_LIKE`, `_DATE_RE`),
  `importers.detail_enrichment` (`_chiude_sezione`, `_sezione_della_chiusura`), `importers.import_snello.righe`
  (`_lista_concatenata`), `importers.mineru_adapter` (`_TableHTMLParser`). `classify_bilancio` è pubblico e resta.
- Produces: `importers/lettore/_ereditati.py` con gli stessi nomi senza trattino iniziale
  (`forma_strutturale`, `intestazione`, `PAROLE_TESTATA`, …, `TableHTMLParser`); nessun modulo di
  `importers/lettore/` importa più un nome che comincia con `_` da fuori dal pacchetto.

Ogni copia porta un commento d'una riga con modulo e funzione d'origine e il commit di `main` da cui è presa
(e3455d6). Dove la copia dipende a sua volta da altri privati del modulo d'origine, si copia anche quello, mai
di più di quanto serve.

- [ ] **Step 1: Scrivi i test** in `tests/lettore/test_ereditati.py`:
  - `test_nessun_privato_da_fuori` — legge con `ast` ogni file di `importers/lettore/` e fallisce se un
    `from importers.X import _Y` ha `X` fuori da `lettore`;
  - `test_deriva_<nome>` uno per nome (14), che confronta copia e originale su 5-10 input fissi scelti fra i casi
    dei test della Fase 1 (stringhe di etichette, token di importo, righe HTML); per le costanti, uguaglianza del
    valore. Il test fallisce quando il modulo vecchio cambia: è il segnale che si vuole, e il messaggio dice di
    decidere se portare la correzione nel lettore.
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_ereditati.py -q`. Expected: FAIL
  su `test_nessun_privato_da_fuori` e ImportError su `_ereditati`.
- [ ] **Step 3: Crea `_ereditati.py` e cambia gli import** dei cinque moduli.
- [ ] **Step 4: Lancia** tutta `tests/lettore` (Expected: PASS, 308 + i nuovi) e il dump dei 245 PDF prima/dopo
  (script `dump.py`/`diff.py` del ledger della Fase 1, da rifare in `.superpowers/sdd/<piano>/` se lo scratchpad
  è stato svuotato). Expected: diff vuoto.
- [ ] **Step 5: Commit** `git commit -m "refactor(lettore): copie dei nomi privati dei moduli vecchi, con test di deriva"`

### Task 2: I blocchi che non chiudono

**Files:**
- Create: `importers/lettore/blocchi.py`, `tests/lettore/test_blocchi.py`
- Modify: `importers/lettore/__init__.py` (esporta `Blocco`, `blocchi_aperti`, `frase_blocco`)

**Interfaces:**
- Consumes: `leggi_pdf`, `Documento.righe_del_prospetto()`, `Riga.totale`, `Riga.figli`, `Riga.celle`,
  `Colonna.ruolo/fine/mesi/corrente`, `valore_nel_totale`, `Profilo.coppie`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Blocco:
      voce: str                 # etichetta stampata del totale («B) II - Crediti», «Totale costi»)
      codice: str               # "" se il totale non ha codice
      sezione: str              # "SP" | "CE" | ""
      lato: str                 # "U" | "L" | "R"
      colonna: int              # indice in Documento.colonne
      fine: date | None         # periodo della colonna
      mesi: int | None
      corrente: bool
      stampato: Decimal         # importo del totale sulla sua colonna
      somma: Decimal            # somma dei figli candidati con valore_nel_totale
      scarto: Decimal           # stampato - somma
      pagina: int
      righe: tuple[str, str]    # id della prima e dell'ultima riga candidata («p3r12U», «p3r27U»)
      etichette: tuple[str, ...]  # le etichette dei figli candidati, al massimo 12
  def blocchi_aperti(doc: Documento) -> list[Blocco]   # in ordine di |scarto| decrescente
  def frase_blocco(b: Blocco) -> str   # «B) II - Crediti (2025, p. 3, righe 12-27): stampato 1.234,56, i conti sommano 1.200,00, scarto 34,56»
  ```

Un **blocco aperto** è una riga di prospetto con importo su una colonna esercizio o saldo che è un totale
stampato (riga di controllo C12, o voce che `marca_totali` ha provato a chiudere: `Riga.totale` vero su un'altra
colonna, oppure una voce con figli dichiarati per intestazione) e i cui **figli candidati** non sommano entro la
tolleranza C6 su quella colonna. I figli candidati sono le righe dello stesso lato e sezione fra il totale
precedente chiuso e questo (o, per un totale stampato prima dei figli, fino al totale successivo), con la stessa
regola di lettura di `totali.py` (si importa da lì; nessuna seconda implementazione della ricerca). Un totale che
chiude su una colonna e non sull'altra è aperto **solo** sulla colonna che non torna (C6, budget_1445).
`blocchi_aperti` legge, non modifica: dopo la chiamata `doc` è identico.

- [ ] **Step 1: Scrivi i test** in `tests/lettore/test_blocchi.py` (PDF sintetici con `tests/lettore/pdf_sintetico.py`):
  - `test_documento_che_chiude_non_ha_blocchi` (schema a due colonne con tre voci e totali esatti → `[]`);
  - `test_voce_che_non_chiude_e_un_blocco` (tre conti 100, 200, 300 e «Totale» 610 → un `Blocco` con
    `stampato == 610`, `somma == 600`, `scarto == 10`, `righe` dal primo conto al totale);
  - `test_colonna_precedente_che_non_torna` (forma di budget_1445: TFR 387.507,50 chiude sulla corrente,
    401.361,79 contro 333.227,76 sulla precedente → un solo blocco, colonna precedente, scarto 68.134,03);
  - `test_colonna_differenza_non_e_un_blocco` (colonna «DIFFERENZA» che non somma → nessun blocco);
  - `test_righe_della_nota_non_fanno_blocchi` (pagina «NOTA INTEGRATIVA» con una tabella che non somma → `[]`);
  - `test_frase_blocco` (la frase esatta dell'esempio sopra, importi in formato italiano);
  - `test_blocchi_non_modificano_il_documento` (`copy.deepcopy(doc)` prima, uguaglianza dopo);
  - `test_ordine_per_scarto` (due blocchi aperti, il più grande per primo).
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_blocchi.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implementa** `blocchi.py`.
- [ ] **Step 4: Lancia** tutta `tests/lettore`. Expected: PASS. Poi, sul corpus, uno script nello scratchpad che
  stampa per i 78 documenti del campione il numero di blocchi aperti sulla colonna corrente e i 3 maggiori
  (fuori da git: cifre di clienti); riportalo nel rapporto.
- [ ] **Step 5: Commit** `git commit -m "feat(lettore): blocchi che non chiudono, per voce, colonna e righe"`

### Task 3: La diagnosi del lettore per un import

**Files:**
- Create: `importers/lettore/diagnosi.py`, `tests/lettore/test_diagnosi.py`

**Interfaces:**
- Consumes: `leggi_pdf`, `leggi_celle`, `blocchi_aperti`, `frase_blocco`, `Documento.tutti_gli_avvisi()`;
  `importers.mineru_adapter.MinerUExtractionContext` (campi `tables`, ciascuna con `html`, `page`, `caption`).
- Produces:
  ```python
  TETTO_SECONDI_DEFAULT = 20
  def diagnosi_pdf(file_path: str, contesto_mineru=None, *, anno_corrente: int | None = None,
                   anno_precedente: int | None = None, tetto_secondi: float | None = None) -> dict
  def frasi_per_utente(diagnosi: dict, sezioni: set[str]) -> list[str]
  ```

`diagnosi_pdf` non solleva mai e restituisce un dict JSON (stringhe per i Decimal e le date):
`{"esito": "ok"|"errore"|"tempo"|"non_applicabile", "motivo": str|None, "ingresso": "pdf"|"mineru",
"secondi": float, "tipo": str, "contrapposto": bool, "colonne": [{"indice", "ruolo", "fine", "mesi",
"corrente"}], "blocchi_aperti": [<Blocco come dict>], "avvisi": [str]}`.
Ingresso: `contesto_mineru` con tabelle → `leggi_celle([t.html …], [t.page …], titoli=[t.caption …])`;
altrimenti `leggi_pdf(file_path)`; un PDF senza testo e senza tabelle → `non_applicabile`. Il tetto di tempo si fa
con un `concurrent.futures.ThreadPoolExecutor(max_workers=1)` e `result(timeout=…)`; scaduto il tetto il
risultato si scarta (il thread finisce da solo) e l'esito è `"tempo"`. Tetto da `LETTORE_TETTO_SECONDI` o dal
parametro. Nei `blocchi_aperti` del dict restano solo i blocchi su colonne con ruolo esercizio o saldo il cui
periodo ha anno `anno_corrente` o `anno_precedente` (quando dati), al massimo 20.

`frasi_per_utente` produce le frasi d'avviso, al massimo 5, solo per i blocchi della colonna corrente (o
dell'anno precedente, se il chiamante lo chiede) delle sezioni date: prima riga
«BLOCCHI CHE NON CHIUDONO NEL PDF: i totali stampati qui sotto non sono la somma delle righe che li precedono;
verificarli in Rettifiche.», poi una `frase_blocco` per blocco. Nessun blocco → lista vuota.

- [ ] **Step 1: Scrivi i test** in `tests/lettore/test_diagnosi.py`:
  - `test_diagnosi_documento_che_chiude` (`esito == "ok"`, `blocchi_aperti == []`, la chiave c'è);
  - `test_diagnosi_blocco_aperto` (il PDF del Task 2 con «Totale» 610 → un blocco, `scarto == "10.00"`);
  - `test_diagnosi_non_solleva` (file inesistente → `esito == "errore"`, `motivo` non vuoto);
  - `test_diagnosi_tetto_di_tempo` (`leggi_pdf` sostituito con una funzione che dorme 2 s, tetto 0,5 → `"tempo"`
    in meno di 1,5 s);
  - `test_diagnosi_mineru` (contesto finto con due tabelle HTML di schema → `ingresso == "mineru"`);
  - `test_diagnosi_scansione_senza_tabelle` (PDF di sola immagine, nessun contesto → `"non_applicabile"`);
  - `test_frasi_solo_colonna_corrente` (un blocco sulla precedente e uno sulla corrente → una frase di blocco);
  - `test_frasi_vuote_senza_blocchi`;
  - `test_json_serializzabile` (`json.dumps(diagnosi)` non solleva).
- [ ] **Step 2: Lancia** `backend/venv/bin/python -m pytest tests/lettore/test_diagnosi.py -q`. Expected: FAIL.
- [ ] **Step 3: Implementa** `diagnosi.py`.
- [ ] **Step 4: Lancia** tutta `tests/lettore`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(lettore): diagnosi di un import, con tetto di tempo e senza eccezioni"`

### Task 4: Il lettore nell'import

**Files:**
- Modify: `importers/pdf_importer.py` (dentro `import_pdf_balance_sheet`: la chiamata dopo l'estrazione, prima
  di `warnings = mapper.validate_hierarchy(...)` ~riga 2428; la chiave in `_validation_payload` ~riga 2549)
- Create: `tests/test_lettore_nell_import.py`

**Interfaces:**
- Consumes: `diagnosi_pdf`, `frasi_per_utente`; nel file: `file_path`, `extraction_context` (MinerU),
  `_ocr_source`, `unbalanced_reason`, `_snello_report`, `_qd` (`check_quadratura`: `sbilancio`, `utile_match`),
  `warnings`, `_validation_payload`, l'anno corrente e precedente già decisi dall'import.
- Produces: `validation_report["lettore"]` (il dict di `diagnosi_pdf`) a ogni import di un PDF col lettore acceso;
  le frasi di `frasi_per_utente` in testa al blocco degli avvisi di quadratura quando l'import dichiara uno
  sbilancio.

**Quando le frasi vanno all'utente:** solo se l'import stesso dichiara che qualcosa non torna — `unbalanced_reason`
non vuoto, oppure `abs(_qd.sbilancio) > 0,01`, oppure `_snello_report["esito"]` in `("squadrato", "tappo")`, oppure
`_qd.utile_match` falso. Sezioni: `{"SP"}` per uno sbilancio di stato patrimoniale, `{"CE"}` per un utile che non
torna, entrambe se non si sa. Negli altri casi la diagnosi va solo in `validation_report` (un blocco aperto su un
documento che quadra è spesso un limite del lettore, non del documento: non si allarma l'utente).

- [ ] **Step 1: Scrivi i test** in `tests/test_lettore_nell_import.py`, con l'LLM sostituito come in
  `tests/test_durata_comparato.py` (nessuna chiamata di rete; `anthropic.Anthropic` che solleva) e il DB su copia:
  - `test_numeri_identici_con_e_senza_lettore` (stesso PDF sintetico importato con `LETTORE_DIAGNOSI=0` e `=1`:
    `balance_sheet`, `income_statement`, esito e anni uguali campo per campo);
  - `test_chiave_lettore_dichiarata` (acceso → `validation_report["lettore"]["esito"] == "ok"`; spento → chiave assente);
  - `test_lettore_che_solleva_non_ferma_l_import` (`diagnosi_pdf` sostituita da una che solleva — non deve
    accadere, ma l'import la avvolge comunque — → import riuscito, `esito == "errore"`);
  - `test_sbilancio_nomina_il_blocco` (PDF sintetico il cui SP stampato non quadra per un totale che non chiude:
    l'avviso contiene «BLOCCHI CHE NON CHIUDONO» e la voce);
  - `test_documento_che_quadra_nessun_avviso_del_lettore` (blocco aperto su un documento importato in quadratura →
    nessuna frase negli avvisi, il blocco c'è in `validation_report`);
  - `test_sbilancio_senza_blocchi_non_inventa` (sbilancio dichiarato ma nessun blocco aperto → nessuna frase nuova);
  - `test_tetto_di_tempo_nell_import` (`LETTORE_TETTO_SECONDI=0.1` e lettore lento → import riuscito, `"tempo"`).
- [ ] **Step 2: Lancia** `DATABASE_PATH=<copia> backend/venv/bin/python -m pytest tests/test_lettore_nell_import.py -q`.
  Expected: FAIL.
- [ ] **Step 3: Implementa** la chiamata in `pdf_importer.py` (un blocco di 20-30 righe, in un `try` proprio, con
  un commento che rimanda al §11 e a questo piano) e l'interruttore `LETTORE_DIAGNOSI`.
- [ ] **Step 4: Lancia** il test nuovo, `tests/lettore`, e le suite dell'import
  `tests/test_standard_ivcee_parser.py tests/test_durata_comparato.py tests/test_snello_*.py` su DB copia.
  Expected: PASS; la suite completa con gli stessi falliti di `main` (i 9 noti + il manifest del corpus).
- [ ] **Step 5: Commit** `git commit -m "feat(import): il lettore di righe nomina i blocchi che non chiudono"`

### Task 5: Misura e documentazione

**Files:**
- Modify: `tests/corpus/punteggio.py` sul branch `feat/punteggio-fase0` (worktree `../budget-punteggio`, dopo un
  merge di `feat/fase2-blocchi`)
- Modify: `docs/import/REGOLE-IMPORT-04-QUADRATURE.md` (sezione nuova), `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md`
  §11 (una riga: il lettore è collegato in diagnosi)

**Interfaces:**
- Consumes: `validation_report["lettore"]` dagli esiti dell'import; la base
  `Test/_analisi-campione/punteggio/base-fase2-e3455d6/` (nel worktree `budget-punteggio`).
- Produces: nel rapporto del punteggio una sezione «Lettore» con, per i documenti importati: esito del lettore
  (ok/errore/tempo/non_applicabile), secondi (media e massimo), documenti sbilanciati con almeno un blocco
  nominato sulla sezione giusta, documenti sbilanciati senza blocchi; e un controllo «numeri invariati» che
  confronta campo per campo i valori salvati con la base sui documenti stabili fra i giri della base.

- [ ] **Step 1: Estendi `punteggio.py`** (l'esito di `probe` già porta il `validation_report`: verificarlo in
  `tests/_import_probe.py`, aggiungere il campo se manca) e scrivi i test della sezione «Lettore» in
  `tests/test_punteggio_corpus.py` con esiti finti.
- [ ] **Step 2: Lancia il punteggio** dal worktree, come la base: 78 documenti × 3, `--paralleli 2`, etichetta
  `fase2-<sha>`, lanciato con `setsid nohup` (le misure lunghe sopravvivono alla sessione) e lo script
  `Test/_analisi-campione/lancia_base_fase2.sh` adattato. Le chiavi solo nell'ambiente del processo.
- [ ] **Step 3: Confronta** con `base-fase2-e3455d6`: macro, KPI, dettagli, esito e anno precedente entro la
  variabilità della base (i 14 documenti instabili si guardano a parte); «numeri invariati» al 100% sui documenti
  stabili. Ogni documento che cambia è un difetto da spiegare prima di chiudere.
- [ ] **Step 4: Documenta** in `REGOLE-IMPORT-04-QUADRATURE.md` una sezione «Blocchi che non chiudono (Fase 2)»:
  che cosa vede l'utente e quando, la chiave `validation_report["lettore"]`, l'interruttore, il tetto, che i numeri
  non cambiano, i limiti noti ereditati dalla Fase 1.
- [ ] **Step 5: Commit** dei due branch (`punteggio.py` sul suo, docs su `feat/fase2-blocchi`).

## Quando la Fase 2 è fatta

- `validation_report["lettore"]` c'è su ogni PDF importato del campione, con esito `ok` su almeno il 95% dei
  documenti con testo e nessun import fallito per colpa del lettore.
- **Numeri invariati:** 100% dei campi uguali alla base sui documenti stabili fra i giri.
- Sui documenti che l'import salva sbilanciati, almeno uno su due ha un blocco nominato sulla sezione giusta;
  ogni documento sbilanciato senza blocco è elencato con il motivo (di solito un limite noto della Fase 1).
- Il lettore costa al massimo 2 s di mediana e 20 s di massimo per documento.
- Il lettore non importa nessun nome privato da fuori dal pacchetto, e i test di deriva passano.

## Fuori da questa fase

La classificazione dei conti col lettore (Fase 3), il voto sui blocchi aperti e la rilettura del solo blocco
(Fase 3), tenere la colonna che chiude quando l'altra no al posto di rifiutare il file (budget_1445: cambia i
numeri, quindi Fase 3), i limiti noti della Fase 1 (confine per pagina, colonne col ruolo sbagliato, OCR), il
frontend (gli avvisi arrivano già come lista nell'import).
