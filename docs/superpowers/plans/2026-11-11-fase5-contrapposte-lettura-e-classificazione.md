# Fase 5 — contrapposte: il lettore legge, il modello classifica — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** alzare l'affidabilità sulle situazioni contabili a sezioni contrapposte e sugli elenchi di conti a colonne
(oggi macro ~65%, KPI ~61%, dettagli ~49%, contro 89-99% sugli schemi di legge) spostando la **classificazione** dalle
parole chiave dei parser al modello, e togliendo i difetti di **lettura** che fanno rinunciare il lettore.

**Decisione del proprietario (2026-11-11):** niente correzioni a parole chiave: limitano la classificazione. La voce
di un conto la sceglie il modello (dentro le classi ammesse, mai un importo); le regole del proprietario che sono un
giudizio sulla natura entrano nelle **istruzioni** al modello; restano deterministici solo lato, segno, scadenza e
importi.

**Architecture:** la catena resta *lettori deterministici → percorso del lettore → modello snello → classico*. Tre
leve, in ordine: (A) il lettore di righe legge più documenti in pari (sezioni, colonne, righe scartate), così il
percorso del lettore li adotta; (B) la classificazione del percorso del lettore (`importers/lettore/classifica.py`)
riceve le regole del proprietario, il contesto del conto e una regola di scadenza completa; (C) sulle situazioni
contabili il lettore prova **prima** del `situazione_contabile_parser`, e dove il lettore non legge il parser
fornisce le righe e il modello le classi («il parser legge, il modello classifica»). I 12 parser di layout restano
congelati: se ne usa la lettura, non le regole.

**Tech Stack:** Python 3, PyMuPDF 1.28.2 (fissato: con 2.x `xbrl_reso_parser` perde le tabelle della nota),
`importers/lettore/*`, `importers/import_snello/*`, Qwen su gx10 (`llm_provider.chiama_gx10_json`), pytest,
`tests/corpus/punteggio.py`.

**Spec / prove:** le due indagini del 2026-11-11, fuori git perché citano cifre ed etichette dei clienti:
`Test/_analisi-campione/indagine-2611/contrapposte.md` (cause di classificazione, conto per conto, sui 18 documenti
salvati dal parser e sugli 8 adottati dal lettore) e `Test/_analisi-campione/indagine-2611/lettore-rinunce.md`
(perché il lettore rinuncia su 29 documenti, con le correzioni simulate offline). Regole del proprietario per la
verità: `Test/_analisi-campione/ISTRUZIONI-CONSOLIDA.md`, `ISTRUZIONI-REGOLE-2.md`, `ISTRUZIONI-WK44.md`,
`ISTRUZIONI-REGOLE-3.md`. Revisione: https://claude.ai/artifact/ByQZE4SXdTd4TbeVVX6Yxy.

**Stato di partenza misurato** (verità aggiornate con le regole R3 del 2026-11-11):

| Giro | Documenti | Esito | Macro | KPI | Altri dettagli |
|---|---|---|---|---|---|
| `fase4-ad2b581-R3` (main di oggi, campione di prima) | 78 | 99,6% | 80,3% | 80,0% | 79,3% |
| `corpus-campione86-R3` (giro sul corpus, 74 + 8 nuovi, nuovi senza mesi) | 82 | 97,6% | 80,2% | 79,6% | 78,6% |
| 18 documenti salvati da `situazione_contabile_parser` (`fase4-ad2b581-sui18-R3`) | 18 | 100% | 56,6% | 41,5% | 35,2% |
| gli stessi con `IMPORT_LETTORE_PRIMA=1` (`esp-lettore-prima-R3`) | 18 | 100% | 61,0% | 53,5% | 50,1% |

Nell'esperimento il lettore è adottato su 8 dei 18 (158, 337, 246, 188, 1478, 373, 1549, 1550), mai peggiore del
parser; sugli altri 10 rinuncia (sezioni, foglie non in pari, massa non classificata). 4 documenti instabili fra i
giri (variabilità del modello). Costo: 2-11 chiamate e 20-140 s per import contro ~1 s del parser.

**Perché il parser è debole (indagine `contrapposte.md`):** `classify_attivo` dà solo aggregati, le sotto-voci le
riempie il secchio di ripiego; `_be_reclassify` fa vincere il mastro sulla natura del conto; `classify_passivo` non
produce mai un debito oltre 12 mesi; alcune parole chiave colpiscono una sottostringa sbagliata. Gli errori spostano
massa dentro lo stesso insieme: il foglio quadra e nessun cancello li vede.

**Perché il lettore rinuncia (indagine `lettore-rinunce.md`):** 22 dei 29 rinunciano per un difetto di lettura
(famiglie F1-F18), 7 a ragione (documenti che si contraddicono, solo SP, colonna a zero).

**Fuori da questa fase, apposta:**
- Correggere le parole chiave di `situazione_contabile_parser.py` o di `import_snello/conti.py` (decisione del
  proprietario; parser congelati).
- F8 (`foglie.py::_scorri`, `_Percorsi._livelli`: percorsi persi quando il mastro è stampato prima dei figli): recupera
  1341 e 1445 ma cambia le foglie di due documenti già adottati (1407, 1440). Va in una fase propria, misurata da sola.
- F13-F15 (tre documenti dello stesso gestionale, 1426, 1429, 1430) e F18 (export SEZBIL, COLOMBO): pacchetti a sé.
- F19: il lettore che dichiara la contraddizione di un documento squadrato all'origine (import «squadrato» con avviso).
- La regola del proprietario «finanziamento soci fuori dalla PFN» (indicatore, non import; il DB non distingue i soci
  dentro `sp16b`): serve un design a parte.
- Cambiare i default degli interruttori: decisione del proprietario sui numeri, dopo il Task 11.

## Global Constraints

- **Il modello non decide mai un importo.** Gli importi vengono dal testo (o dalle celle MinerU) tramite il lettore o
  la lettura del parser; Qwen restituisce una classe per id dentro le classi ammesse. Il cancello
  `deterministico.esito` non si tocca; niente plug; chiusura automatica solo fino alla soglia dichiarata.
- **Deterministico, mai nel prompt:** il lato (lo decide la colonna), il segno e i saldi a lato invertito (D2, D12,
  D15, R3-CARTE, R3-RATEI, R3-NCR, P2/P3), la scadenza (solo da prova stampata: debito senza scadenza a breve, mutui
  compresi), la parentela dei conti (il totale stampato decide, mai il prefisso del codice: il codice e il mastro
  entrano solo come contesto della domanda).
- **Un interruttore per ogni comportamento nuovo**, letto come `IMPORT_LETTORE` (`0`/`false`/`no`/`off` spengono);
  default di oggi = percorso identico (test). Le correzioni di lettura della Fase A non hanno interruttore: sono
  difetti, e il punteggio («Numeri invariati») prova che non toccano i documenti già adottati.
- **I lettori deterministici restano davanti e i loro numeri non cambiano**, salvo dove la Fase C li sostituisce
  dietro interruttore.
- **Nessuna regola legata a un id di documento**; ogni correzione ha un test sintetico che fallisce prima.
- **Dati dei clienti mai in git**: nei test PDF sintetici e nomi inventati; cifre ed etichette reali solo nei
  rapporti fuori git (`Test/_analisi-campione/`).
- Codice, test e commenti in italiano; importi `Decimal`; test su copia del DB (`DATABASE_PATH`, `BUDGET_REAL_DB`);
  mai `pytest tests` intero, mai le suite con PDF reali; mai `ANTHROPIC_CONSENTITO`; gx10 con Bearer, chiavi solo
  nell'ambiente del processo (lanciatori in `Test/_analisi-campione/`), mai stampate; un giro su gx10 alla volta.
  PyMuPDF `VersionBind` < 2 prima di ogni giro. `situazione_contabile_parser.py` è CRLF. Niente `git stash` né
  `git add -A`.
- **Mandare documenti a gx10 è uscita di dati dei clienti:** i giri del Task 0 e del Task 11 si fanno solo con
  l'approvazione del proprietario. Nessuna chiamata a gx10 negli altri task (test con Qwen finto, verifiche offline).
- Branch `feat/fase5-contrapposte` da `main` 616a0c0, con dentro il campione a 86 documenti (`campione-nuovi-2611`)
  e l'interruttore `IMPORT_LETTORE_PRIMA` (`esperimento-lettore-prima`). Merge e push solo su richiesta.

## Review Focus

1. **Una correzione di lettura che cambia le foglie di un documento già adottato** (Fase A): lo strumento del Task 1
   confronta le foglie prima/dopo su tutto il campione; ogni differenza su un adottato va spiegata o la correzione
   ristretta. Test nei Task 2-5.
2. **Una regola nel prompt che contraddice un controllo deterministico** (es. il prompt che sposta a lungo un debito
   senza prova stampata, o cambia il lato): le classi ammesse per riga restano quelle del lato; la scadenza la
   riscrive `scadenza_stampata` dopo la classificazione. Test nel Task 6.
3. **Il parser che legge e il modello che classifica** (Task 10): le foglie costruite dalla lettura del parser non
   possono contare due volte mastro e conti (il totale stampato decide), e l'adozione passa dallo stesso cancello.
   Test nel Task 10.
4. **La variabilità del modello**: un peggioramento si conferma su 3 giri, mai su uno (CLAUDE.md, «L'estrazione LLM
   non è deterministica»).
5. **Un documento che si contraddice da solo** (1410, 289, 138, 152, 161): nessuna correzione deve farlo «quadrare».

---

### Task 0: base di confronto sugli 8 documenti nuovi (gx10, su approvazione)

Il campione ha 86 documenti; gli 8 nuovi (355, 1444, 135, 138, 1430, 1451, 1341, 1452) sono stati importati solo dal
giro sul corpus, senza i mesi della verità.

- [ ] Con l'approvazione del proprietario: `lancia_corpus.sh`-equivalente in modalità campione (lanciatore in
      `Test/_analisi-campione/`, senza `--corpus`), `--solo` gli 8, `--ripetizioni 3 --paralleli 2`, sul codice di
      `main` (interruttori spenti). Etichetta `base5-nuovi8`.
- [ ] Base della fase = `fase4-ad2b581-R3` (78) + `base5-nuovi8` (8), punteggio ricalcolato con `--da-esiti` su una
      cartella che unisce gli esiti: `base5-86`.

### Task 1: strumento offline «foglie in pari» sul campione e sul corpus

Serve a misurare la Fase A senza gx10: il motivo `foglie_non_in_pari`/`senza_foglie_sp` e le foglie stesse si
decidono prima di qualunque chiamata al modello.

**Files:** Create `tests/corpus/foglie_campione.py`; Test `tests/test_foglie_campione.py`.

- [ ] Per ogni documento (campione, o `--corpus` dal manifesto, o `--solo`): `leggi_pdf` → foglie del percorso del
      lettore (le stesse di `importa_col_lettore`, fermandosi prima di `classifica_*`: nessun modello) → esito di
      `percorso._foglie_non_in_pari` e conteggi (foglie, foglie senza sezione, senza lato, senza percorso di legge,
      somma attivo/passivo per lato). Scansioni: fuori (servono le celle MinerU), elencate a parte.
- [ ] `--confronta <etichetta>`: foglie documento per documento contro un giro precedente dello strumento (stesse
      foglie = stessa etichetta, colonna, importo, sezione, lato); stampa i documenti cambiati.
- [ ] Uscita fuori git (`IMPORT_PUNTEGGIO_DIR`), rapporto `.md` + `.json`. Test sintetici: un PDF contrapposto in
      pari, uno con una riga senza sezione.
- [ ] Giro di partenza `foglie-base` sul campione e sul corpus (offline). Atteso: i 22 documenti delle famiglie F1-F17
      fuori pari come nell'indagine.

### Task 2: F1 — sezione (SP/CE) determinata anche all'indietro (10 documenti)

**Files:** Modify `importers/lettore/profilo.py` (`_sezioni`), `importers/lettore/_ereditati.py`
(`_TOTALE_DI_CHIUSURA`); Test `tests/lettore/test_profilo.py`.

- [ ] Test che falliscono (PDF sintetici): (a) righe senza sezione prima di un totale di chiusura dello SP prendono la
      sezione di quel totale; (b) un «TOTALE PASSIVO» stampato prima del titolo «Conto economico» sulla stessa pagina
      non chiude la pagina; (c) «TOTALE ATTIVO CIRCOLANTE» non è un totale di chiusura.
- [ ] Codice: dopo il passaggio in avanti, le righe ancora senza sezione prendono quella del primo totale di chiusura
      che le segue (come già fa `_sezioni_dai_totali_di_conti`); la chiusura di pagina conta solo dopo l'ultimo
      titolo della pagina; `ATTIVO(?!\s+CIRCOLANTE)`.
- [ ] Strumento del Task 1 `--confronta foglie-base`: nessun adottato del campione cambia; 395 in pari.

### Task 3: F3 + F5 — righe con importo non più scartate (405, 1325, 1401)

**Files:** Modify `importers/lettore/righe.py` (`_pezzi_della_riga`, `_ANAGRAFICA`), `importers/lettore/foglie.py`
(`_foglie_grezze`, `_e_controllo`); Test `tests/lettore/test_righe.py`, `tests/lettore/test_foglie.py`.

- [ ] Test: una riga di conto che contiene «PIAZZA …» o «PARTITA IVA …» e ha un importo resta una riga di conto;
      una riga di sola anagrafica (senza celle né codice) resta scartata. Un «Totale MASTRO» senza conti stampati fra
      il titolo del mastro e il totale diventa una foglia (la massa non si perde); con i conti sotto resta un totale.
- [ ] Codice come da test. Strumento del Task 1: in pari 405, 1325, 1401 (con F1); cambiano solo 405 e 1325 fra i
      documenti del campione.

### Task 4: F2 — colonna corrente su un lato con una colonna spuria (229, 1456, 1430)

**Files:** Modify `importers/lettore/colonne.py` (`_corrente`), `importers/lettore/foglie.py` (`colonne_utili`,
`_colonna_della_riga`); Test `tests/lettore/test_colonne.py`.

- [ ] Test: un lato con la colonna degli importi e una colonna di pochi valori (un numero dentro una descrizione, i
      soli totali spostati) sceglie come corrente la colonna degli importi; la colonna dei soli totali non è mai la
      corrente.
- [ ] Codice; strumento del Task 1: 229 e 1456 in pari, nessun adottato cambia.

### Task 5: correzioni puntuali di lettura (F17, F16, F7, F9/F11)

**Files:** `importers/lettore/totali.py` (`_DICE_TOTALE`), `_ereditati.py` (`_TOTALE_DI_CHIUSURA`), `foglie.py`
(«di cui», regola R22), `righe.py`/`foglie.py` (testata CE negativa, riga fusa «C) … 17)»); test nei rispettivi file.

- [ ] F17: «Eccedenza esercizio precedente» è un conto, non un totale (Bilancino).
- [ ] F16: righe «di cui» che partizionano esattamente il totale non si sommano al totale (1427).
- [ ] F7: R22 accetta lo scarto di arrotondamento delle altre riserve fino alla tolleranza già dichiarata, più conti
      sotto la stessa voce, voci stampate all'unità (1533, 1451).
- [ ] F9 + F11: una testata «B) Costi» stampata negativa sopra figli positivi non inverte i figli; la riga fusa
      «C) … 17) Interessi» non è una riga di controllo (1434, 1433, 1464).
- [ ] Ogni punto un commit, ognuno col suo test che fallisce prima; strumento del Task 1 dopo ciascuno. Atteso a fine
      Fase A: ~12-15 dei 22 in pari (stima dell'indagine), nessun adottato cambiato.

### Task 6: la scadenza stampata, completa e anche sui crediti

**Files:** Modify `importers/lettore/classifica.py` (`_PERIODO`, `_OLTRE`, `_ENTRO`, `scadenza_stampata` e chi la
applica); Test `tests/lettore/test_classifica.py`.

- [ ] Test: «MEDIO LUNGO TERMIN…» troncato, «>12 mesi», «oltre l'esercizio successivo», «(OE)» su un credito → oltre;
      «entro», «(EE)» → entro; nessuna indicazione → entro (debiti e crediti); interessi in un mastro «medio/lungo»
      → entro (P3/P4). La scadenza si applica dopo la classe del modello e la riscrive (sp16↔sp17, sp06↔sp07).
- [ ] Codice. Resta deterministico: il modello non sceglie mai entro/oltre.

### Task 7: istruzioni di classificazione con le regole del proprietario

**Files:** Modify `importers/lettore/classifica.py` (`PROMPT_MACRO`, prompt dei dettagli, classi ammesse); Test
`tests/lettore/test_classifica.py` (sul testo del prompt e sulle classi, con Qwen finto).

- [ ] Togliere la frase che manda «un fornitore con saldo dare fra le attività» negli altri crediti: contraddice P6
      (acconti a fornitori nelle rimanenze `sp05e`, o fra le immobilizzazioni in corso `sp03e` se l'acquisto è un
      cespite). Il saldo a lato invertito resta per i conti che non sono acconti.
- [ ] Aggiungere, come istruzioni brevi e generali (nessun nome di cliente), le regole di giudizio sulla natura:
      D3 (somministrato nel personale), D4 (ricavi per natura: A.1 l'attività tipica, A.5 il resto), D5, D8 (natura
      dei costi contro il mastro), D9/R3-D9 (spese bancarie secondo il mastro del documento), D10, D11, D13, D16, P5,
      P6, P7, W4 (lavori in corso su ordinazione in A.3), R3-ACCANT (TFM amministratori e indennità suppletiva in
      B.13), R3-FINSOCI/R3-SOCI-MISTI, R3-RIVALSE/R3-CONAI/R3-ADDEBITI/R3-INDENNIZZI, R3-FTV, R3-ASSOC, R3-ENASARCO,
      R3-CONTROPARTE, imposte di esercizi precedenti in `ce20`. Una riga per regola; il testo vive in un modulo di
      regole (`importers/lettore/regole_proprietario.py`) così che prompt e documentazione leggano la stessa fonte.
- [ ] D6: `ce18`/`ce19` fuori dalle classi ammesse (straordinari per natura in `ce04`/`ce12`/`ce20`); `ce17` resta.
- [ ] Interruttore `IMPORT_REGOLE_NEL_PROMPT` (default acceso? decisione dopo il Task 11; nel branch acceso per la
      misura, spento = prompt di oggi, test).

### Task 8: codice del conto e mastro stampato come contesto della domanda

**Files:** Modify `importers/lettore/classifica.py` (costruzione della domanda per riga); Test idem.

- [ ] Ogni riga chiesta al modello porta, oltre all'etichetta: il codice del conto se stampato, l'etichetta del mastro
      che la contiene secondo il totale stampato (o il titolo di sezione), la sezione. Mai come prova di parentela:
      la foglia e il suo padre li ha già decisi il lettore.
- [ ] La cache per (etichetta, lato, sezione) dentro il documento diventa per (etichetta, codice, mastro, lato,
      sezione): due conti uguali sotto mastri diversi possono avere classi diverse. Test.

### Task 9: il lettore prova prima del parser sulle situazioni contabili

**Files:** `importers/import_snello/__init__.py` (già nel branch: `IMPORT_LETTORE_PRIMA`, `_PARSER_DOPO_IL_LETTORE`).

- [ ] Rivedere il codice dell'esperimento (commit 5f992df) e i suoi test; nessuna modifica attesa salvo il report.
- [ ] Decidere con il proprietario, sui numeri del Task 11, se il default diventa acceso.

### Task 10: «il parser legge, il modello classifica»

Dove il lettore rinuncia ancora ma un parser delle situazioni contabili quadra, la lettura del parser (righe, importi,
lato, gerarchia) diventa l'ingresso della classificazione del lettore; le classi del parser si ignorano.

**Files:** Create `importers/import_snello/lettura_parser.py`; Modify `importers/import_snello/__init__.py`; Test
`tests/test_lettura_parser.py`.

- [ ] Ricognizione (prima del codice, rapporto nel ledger della fase): per ognuno dei parser che salvano le
      contrapposte nel campione (best-effort `extract_contrapposte_best_effort`, mastri, SEZBIL, DEPI, TeamSystem),
      dove si trova la lettura per conto *prima* della classificazione (`_be_collect_side_facts` e simili), con
      lato, importo, mastro, e se i totali stampati decidono la parentela. Nessuna modifica ai parser (congelati):
      si leggono i loro risultati intermedi, e se non sono raggiungibili senza toccarli il task si ferma e lo dice.
- [ ] Adattatore: conti del parser → `Foglia` del lettore (sezione, lato dalla colonna, importo, etichetta, codice,
      mastro come contesto), con il totale stampato che decide mastro **o** foglie, mai entrambi.
- [ ] Le foglie passano per `classifica_macro`/`classifica_dettagli` (Task 6-8), `componi`, e il cancello
      `deterministico.esito`; se non adotta, resta il candidato del parser com'è oggi.
- [ ] Interruttore `IMPORT_PARSER_CLASSIFICA_MODELLO` (spento = oggi). Test con Qwen finto: un elenco di conti
      sintetico dove la parola chiave sbaglia e la classe del modello no; il mastro e i suoi conti non si sommano.

### Task 11: misura sul campione (gx10, su approvazione)

- [ ] Strumento del Task 1 sul campione e sul corpus: foglie in pari prima/dopo.
- [ ] Con l'approvazione del proprietario: giro sul campione di 86 × 3 con `IMPORT_LETTORE_PRIMA=1`,
      `IMPORT_REGOLE_NEL_PROMPT=1`, `IMPORT_PARSER_CLASSIFICA_MODELLO=1`, `--confronta base5-86`. PyMuPDF < 2.
- [ ] Rapporto per tipologia (obiettivo: contrapposte e conti/colonne verso l'80% di macro e KPI), per percorso,
      instabilità, chiamate e secondi; «Numeri invariati» sugli schemi di legge e sui reso XBRL.
- [ ] Se serve isolare una leva: lo stesso giro con un solo interruttore acceso sui soli documenti contrapposte e
      conti/colonne.
- [ ] Decisioni del proprietario sui default; aggiornamento di `docs/import/REGOLE-IMPORT-02-ESTRAZIONE.md` §11,
      `CLAUDE.md` («Percorso snello», «Estrazione e classificazione») e della pagina di revisione.

## Stima del guadagno (dalle indagini, da confermare col Task 11)

| Leva | Documenti | Atteso |
|---|---|---|
| Fase A (lettura) | 22 rinunce per difetto | 12-15 in pari, adottabili dal lettore |
| Task 6-8 (classificazione) | gli 8 adottati nell'esperimento | macro 65% → ~78-80%, KPI 71% → ~80% |
| Task 9-10 (parser legge, modello classifica) | i 10 dove il lettore rinuncia | macro ~58% → ~68-70%, KPI ~45% → ~65-70% |

Costo: tempo di import da ~1 s a 20-80 s sui documenti che oggi salva il parser; variabilità del modello da tenere
sotto controllo con il voto e la rilettura delle righe incerte già presenti nel percorso del lettore.
