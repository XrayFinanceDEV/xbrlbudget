# Routing import bilanci per tipologia — analisi e tassonomia

> ⚠️ **Conteggi e sintesi superati (verificato il 2026-07-16).** Il corpus è ora a **214 file
> fisici / 137 contenuti unici**. Inoltre: la sintesi del blocco B (§4) attribuisce la soglia
> `coge_codes>=5` a tutto il blocco mentre nel codice la richiede **solo B2**; i segnali
> `sit_contabile` e `dare_avere` sono elencati fra i discriminanti ma sono **inerti** (calcolati
> e mai letti); le sottocategorie A4/Cerved, A5/riepiloghi AI, B4, C1b e C5 sono dichiarate ma
> **il router non le produce mai**. Per le regole di routing effettive vedi
> [REGOLE-IMPORT-01-ROUTING.md](REGOLE-IMPORT-01-ROUTING.md). Questo documento resta valido come
> **analisi del corpus e razionale del progetto**.

> Documento generato dall'analisi automatica di **tutti i casi** in `Test/`
> (124 file totali, **77 documenti unici** dopo dedup per hash di contenuto).
> Obiettivo: sostituire le patch caso-per-caso con un **router per macro-area** che,
> dato un file in ingresso, ne riconosca la tipologia e lo instradi all'estrattore
> giusto. Nuovi formati ricadono nella macro-area corretta (e al peggio nel suo
> fallback) senza rompere gli altri rami.
>
> **STATO: implementato.** Il router descritto in §4 è realtà nel modulo
> [`importers/bilancio_classifier.py`](../importers/bilancio_classifier.py) e gira
> per primo in `pdf_importer.import_pdf_balance_sheet`. Questo documento copre il
> **routing** (quale estrattore prende il file); i due documenti complementari coprono:
> - [`IMPORT-BALANCING-SCHEME.md`](IMPORT-BALANCING-SCHEME.md) — lo **schema di quadratura L0→L5** applicato a valle di ogni rotta.
> - [`IMPORT-QUADRATURA-ENGINE.md`](IMPORT-QUADRATURA-ENGINE.md) — il **motore IV-CEE condiviso** (`iv_cee_hierarchy`) + anti-masking.
>
> La descrizione granulare di ogni singolo parser/fix sta nel `CLAUDE.md`, sezione *PDF Import*.

## 1. Sintesi

| Macro-area | # file | % | Parsing deterministico (yes / maybe / no) |
|---|--:|--:|---|
| **A** sintetico IV CEE | 34 | 44% | 22 / 12 / 0 |
| **B** dettagliato macrovoci IV CEE | 21 | 27% | 10 / 11 / 0 |
| **C** verifica a sezioni contrapposte | 19 | 24% | 9 / 8 / 2 |
| **OTHER** fuori perimetro | 3 | 3% | 1 / 0 / 2 |

Le tre macro-aree richieste **coprono il 96%** dei casi reali. Il restante 4%
(OTHER) sono file che NON sono prospetti importabili (un `.xbrl` nativo che va al
parser XBRL e non al ramo PDF, un thread email, un riepilogo AI troppo aggregato):
il router deve riconoscerli e **fallire onestamente** con un messaggio chiaro,
mai con un plug silenzioso.

## 2. Le tre macro-aree

### Come si distinguono (in una riga)

- **A** = solo **voci di legge** (lettere A/B/C/D, numeri romani, voci numerate), **nessun codice di conto** di contabilità generale.
- **B** = **stesso scheletro IV CEE di A**, ma ogni macrovoce è **esplosa nei sottoconti** di mastro (codici conto presenti) — il totale di voce è comunque leggibile.
- **C** = **elenco di conti** di contabilità generale (mastro/conto/sottoconto) con **Dare/Avere o Saldo**, **senza** lo schema di legge: è il bilancio di verifica / situazione contabile, da **riclassificare per descrizione**.

### Segnali di riconoscimento (per il router)

| Segnale | A | B | C |
|---|:--:|:--:|:--:|
| Scheletro di legge (lettere/romani, "Totale immobilizzazioni", "Valore della produzione") | ✅ | ✅ | ❌ |
| Codici conto CoGe (XX/YY/ZZZ, 6-8 cifre, NNN.NNNNN, dotted) | ❌ | ✅ | ✅ |
| Codici-PATH CEE puntati (`B.II.1.a`, `C.II.5 bis`) come prefisso riga | ❌ | ✅ (spesso) | ❌ |
| "TOTALE A PAREGGIO" / "BILANCIO DI VERIFICA" / "SITUAZIONE CONTABILE" | ❌ | raro | ✅ (forte) |
| "Conforme alla tassonomia itcc-ci-…" / "Generato automaticamente" | ✅ (forte) | ❌ | ❌ |
| Colonne "Dare/Avere" o singola "Saldo" su elenco conti | ❌ | ❌ | ✅ |

## 3. Sottocategorie proposte

Le sottocategorie servono al **sub-router** interno a ciascuna macro-area: dentro la
stessa area l'estrazione cambia in base al *layout fisico* e alla *codifica del
gestionale*, non al singolo file.

### Macro-area A — sintetico IV CEE  (34 file)
- **A1 · Facsimile di deposito XBRL→PDF** — marker `Conforme alla tassonomia itcc-ci-2018-11-04`, `Generato automaticamente`. Il caso più frequente e affidabile; spesso il PDF contiene anche la Nota Integrativa (da ignorare). Dual-year.
- **A2 · Civilistico abbreviato / micro da gestionale** — `forma abbreviata art. 2435-bis`, `Stato patrimoniale micro` (art. 2435-ter). Solo voci di legge; mono-colonna (provvisori) o dual-year.
- **A3 · CEE sintetico riclassificato con scostamenti** — layout gestionale (TeamSystem/Sistemi) con colonne `anno / anno / Differenza / Scost.%`, solo aggregati di voce.
- **A4 · Bilancio ottico Cerved** — pagine di indicatori Cerved + prospetto IV CEE micro incorporato.
- **A5 · Riepiloghi ultra-aggregati / output AI** *(borderline OTHER)* — "schema IV Direttiva CEE", solo macro-totali, spesso non quadrano: bassa confidenza, da validare con cura.

### Macro-area B — dettaglio macrovoci IV CEE  (21 file)
- **B1 · "Situazione contabile riclassificata dettagliata" con codici-PATH CEE** — i sottoconti portano il **codice CEE come prefisso** (`B.II.1.a)`): aggregabili **deterministicamente per prefisso** fermandosi al livello di legge. Famiglia molto coerente (file 147/152/176/182/209/282/283/319/320…).
- **B2 · "con dettaglio sottoconti / conti"** — la voce di legge mostra il **totale**, seguito dai sottoconti CoGe a 6-7 cifre: si legge il **totale di voce** e si ignorano i sottoconti (305/324/340/313/314 + export **Genya**).
- **B3 · Bilancio XBRL esteso AGO Infinity (Zucchetti)** — `BILANCIO SCHEMA XBRL`, header `AGO - 10.x`, codici `6-digit+3`, con `Totale …` di legge espliciti. Già coperto dal parser AGO 8-digit (207/297/331).
- **B4 · Abbreviato con dettaglio conti per descrizione / flag A·P·R·C** — senza codici CEE puntati: mapping più euristico (171/289).

### Macro-area C — verifica a sezioni contrapposte  (19 file)
Due assi indipendenti: **layout fisico** (cosa vede il parser) × **codifica gestionale**.

*Per layout:*
- **C1 · Sezioni contrapposte fisiche** — due colonne affiancate Attività│Passività e Costi│Ricavi (Dare/Avere). Richiede **split per coordinate x** (188 FastReport `.frx`, 249 SAMAC, 338 Pandoro, 281 DEPI, 330 8-digit, 210/213/215 BILAGRA).
- **C1b · Sezioni contrapposte PER SEGNO del saldo** *(nuovo, vedi §6)* — variante di C1 in cui i conti sono in colonna in base al **segno** e **lo stesso conto compare su entrambi i lati** (cassa attiva vs scoperto, crediti vs debiti erariali, risultati). Parser dedicato `parse_bilancio_verifica_segno` che classifica per **natura** e netta i due lati (LIO ENERGY `6 - BILANCIO 31.03.2026`).
- **C2 · Colonna unica "Saldo"** — SP poi CE in sequenza, un solo importo per conto (229/238/243 MBS·CARP 6-digit, 169 e BILANCIO-TEST DEPI a saldo).

*Per codifica gestionale (sotto-asse):* DEPI `XX/YY/ZZZ` (Sistemi) · TeamSystem `XX/YYYY/ZZZZ` · 8-digit · dotted `10.05.001` · BILAGRA `NNN.NNNNN` · single-column 6-digit. **Tutte già mappate** nei parser esistenti (`situazione_contabile_parser.py`), con un fallback generico best-effort che riclassifica i mastri a IV CEE per descrizione.

*Casi speciali C:*
- **C4 · Solo Conto Economico (manca lo Stato Patrimoniale)** — `PROSPETTO ECONOMICO per competenza` (196/335). **Non ricostruibile** un bilancio completo → il router deve segnalarlo, non plug-gare.
- **C5 · Ditta individuale / professionista** — DEPI a saldi senza patrimonio netto societario (131/132 Oprandi): attenzione alla mappatura del PN.

### OTHER  (3 file)
- File **XBRL nativo** (`.xbrl`/`.xml`) → instradare al **parser XBRL**, non al ramo PDF.
- Documenti **non-bilancio** (email, verbali soli) o **riepiloghi troppo aggregati** → errore esplicito.

## 4. Il router implementato — `importers/bilancio_classifier.py`

Un unico modulo **classificatore** gira PRIMA di scegliere l'estrattore. Sostituisce il
vecchio check binario `is_trial_balance`. La scelta dell'estrattore dipende SOLO dalla
`route` ritornata; dentro l'area il sub-router (dentro `situazione_contabile_parser`)
sceglie per layout/codifica.

### 4.1 API e costanti

```python
classify_bilancio(file_path: Optional[str] = None,
                  text: Optional[str] = None) -> Classification

class Classification(NamedTuple):
    macro_area: str        # MACRO_A="A" | MACRO_B="B" | MACRO_C="C" | MACRO_OTHER="OTHER"
    subcategory: str       # es. "A1 facsimile itcc", "B2 dettaglio sottoconti", "C verifica"
    route: str             # ROUTE_IVCEE | ROUTE_TRIAL | ROUTE_XBRL | ROUTE_UNSUPPORTED
    gestionale: str        # DEPI / TeamSystem / AGO / Genya / … (best-effort)
    confidence: str        # "high" | "med" | "low"
    signals: Dict[str, object]
    reason: str            # stringa diagnostica loggata
```

Costanti **rotta** (l'unica cosa che `pdf_importer` guarda per scegliere l'estrattore):

| Costante | Valore | Estrattore a valle |
|---|---|---|
| `ROUTE_IVCEE` | `"IVCEE"` | A/B → LLM IV-CEE (`extract_pdf_with_llm` / `extract_pdf_both_years_with_llm`) |
| `ROUTE_TRIAL` | `"TRIAL_BALANCE"` | C → CoGe-LLM (`extract_trial_balance_with_llm`) → deterministico (fallback) |
| `ROUTE_XBRL` | `"XBRL_NATIVE"` | OTHER `.xbrl/.xml` → `xbrl_parser_enhanced` |
| `ROUTE_UNSUPPORTED` | `"UNSUPPORTED"` | errore onesto, mai un plug silenzioso |

In `pdf_importer`: `is_trial_balance = (classification.route == ROUTE_TRIAL)`. Il dict
risultato porta `macro_area` + `macro_subcategory` (loggati e ritornati), così un nuovo
formato emerge come **area**, non come crash.

### 4.2 I segnali — `compute_signals(text, file_path)`

Tutti robusti agli header lettera-spaziati (variante senza spazi). I principali:

- **Marker testuali (bool):** `itcc` (`itcc-ci-`, "conforme alla tassonomia", "generato automaticamente"), `pareggio` ("totale a pareggio"), `verifica` ("bilancio di verifica"), `sit_contabile` ("situazione contabile"), `riclassificata`, `ago_xbrl` ("bilancio schema xbrl" o regex `\bago\s*-\s*\d`), `dettaglio`, `prospetto_economico`, `valore_produzione`, `immobilizzazioni`, `stato_patrimoniale`, `conto_economico`, `totale_attivo`, `dare_avere`.
- **Derivati (bool):** `legal_skeleton` = `valore_produzione AND immobilizzazioni`; `sp_present` / `ce_present` (presenza dei due prospetti).
- **Densità codici (conteggi regex):** `cee_path` (`B.II.1.a)`), `depi` (`XX/YY/ZZZ`), `depi2` (`XX/YYYY`), `teamsystem` (`XX/YYYY/YYYY`), `eight` (8-cifre), `dotted` (`10.05.001`), `mastro_sub` (BILAGRA `NNN.NNNNN`), `sixdigit_line` (single-column 6-cifre), `totale_voce` (numero di "Totale immobilizzazioni/attivo/…"). `coge_codes` = somma dei conteggi codice.
- **Layout fisico:** `contrapposte` = `is_contrapposte_file(file_path)` (detector per coordinate), `is_sc` = `is_situazione_contabile(text)`.

### 4.3 Regole ordinate (dal segnale più forte al fallback)

```
0.  ext ∈ {.xbrl,.xml}                                   → ROUTE_XBRL / OTHER
1.  ce_present AND NOT sp_present                         → ROUTE_UNSUPPORTED  (solo CE: errore onesto)
2.  itcc AND coge_codes<5 AND NOT pareggio AND NOT verifica
                                                          → ROUTE_IVCEE / A    (facsimile deposito XBRL→PDF)
3.  legal_skeleton AND coge_codes>=5  (B batte C):       → ROUTE_IVCEE / B
      ago_xbrl            → "B3 XBRL esteso AGO"
      riclassificata      → "B1 sit. riclassificata dettagliata"
      cee_path>=5         → "B1 codici-PATH CEE"
      dettaglio           → "B2 dettaglio sottoconti"
4.  legal_skeleton AND totale_voce>=2 AND NOT pareggio
      AND NOT verifica AND NOT contrapposte               → ROUTE_IVCEE / B    (IV-CEE con sottoconti, conf=med)
5.  pareggio OR verifica OR is_sc OR contrapposte        → ROUTE_TRIAL / C    (conf high se pareggio/verifica)
6.  legal_skeleton OR itcc OR (stato_patrimoniale AND totale_attivo)
                                                          → ROUTE_IVCEE / A
7.  fallback                                             → ROUTE_UNSUPPORTED / OTHER
```

> **"B batte C":** un file con lo scheletro di legge che porta *anche* codici conto
> (es. budget_313/314) va in **B** (IV-CEE), NON nel parser trial-balance vuoto — purché
> manchino i marker C forti (pareggio/verifica/contrapposte).

**Principi anti-regressione** (rispondono a "non sistemare per singolo caso"):
1. **Classifica, poi estrai.** Il singolo file non tocca la logica globale: cambia solo *quale* rotta lo prende.
2. **Ogni rotta ha un fallback interno** che degrada con dignità:
   - C → CoGe-LLM → deterministico → (se vuoto) IV-CEE LLM; best-effort reclassify-by-description + flag `BILANCIO NON QUADRATO`.
   - B → se i sottoconti non si aggregano, usa i totali di voce di legge.
   - A → LLM IV-CEE; reconcile al `TOTALE ATTIVO` dichiarato.
3. **Mai mascherare.** `pdf_mapper.validate_balance` fallisce su estrazioni vuote/plug-gate; `_is_aggregated_summary` emette "Formato non supportato" su riepiloghi non-2424/2425.
4. **Confidence + tracciamento.** Il classificatore logga `macro_area/sottocategoria/segnali` (`upload_tracker`): i nuovi formati si vedono e si assegnano a un'area.

### 4.4 Mappatura sui moduli (stato attuale)
- **A/B** → `importers/pdf_extractor_llm.py` (LLM IV-CEE + reconciler deterministici delle sotto-righe, §6).
- **C** → `importers/pdf_extractor_llm.extract_trial_balance_with_llm` (CoGe-LLM, **primario**) con `importers/situazione_contabile_parser.py` come fallback deterministico (DEPI, TeamSystem, 8-digit, single-column, contrapposte best-effort, verifica-per-segno, rescue dotted-hierarchical).
- **OTHER/XBRL** → `importers/xbrl_parser_enhanced.py`.
- **Stadio condiviso a valle** (tutte le rotte) → `importers/iv_cee_hierarchy.py` (`check_quadratura`, `enforce_ce_sp_identity`, `reconcile_ivcee_balance`).

## 5. Mappatura completa dei file

### Macro-area A — Bilancio sintetico in IV CEE  (34)

| File | Sottocategoria | Gestionale | Colonne | Codici | Parsing det. | Conf. |
|---|---|---|---|---|:--:|:--:|
| `budget_133_Bilancio_LUGS_2025_IV_Direttiva.pdf` | sintetico IV CEE ultra-aggregato (solo macrovoci) | sconosciuto/AI | single | nessuno | maybe | high |
| `budget_135_Bilancio_LUGS_2025_COMPLETO.pdf` | sintetico riclassificato, macrovoci aggregate | sconosciuto/AI | single | nessuno | maybe | med |
| `budget_138_Bilancio_LUGS_2025_FULL_DETTAGLIATO.pdf` | IV CEE per voci aggregate (riepilogo) | sconosciuto/AI | single | etichette CEE | maybe | med |
| `budget_143_BILCC58E.pdf` | facsimile deposito abbreviato art.2435-bis | deposito XBRL | dual-year | nessuno | yes | high |
| `budget_144_Elle_erre_-_bilancio_2025.pdf` | civilistico ordinario (facsimile deposito) | sconosciuto | dual-year | nessuno | maybe | high |
| `budget_150_Bilancio_FINALE_CEE_SRL_2025.pdf` | abbreviato art.2435-bis | sconosciuto/AI | single | nessuno | maybe | med |
| `budget_161_BILANCIO_CONA.pdf` | CEE sintetico riclassificato con scostamenti | TeamSystem | dual-year | nessuno | yes | high |
| `budget_162_bilxbrl-0002952.pdf` | facsimile XBRL micro/abbreviato | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_164_bilcervi.pdf` | facsimile deposito XBRL abbreviato/ordinario | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_173_BILANCIO_CEE_AL_31.12.2025.pdf` | facsimile deposito XBRL abbreviato | itcc-ci-2018-11-04 | dual-year | nessuno | maybe | high |
| `budget_201_New_Smile_Bil_Xbrl_2025.pdf` | facsimile deposito XBRL abbreviato | deposito CCIAA | dual-year | nessuno | yes | high |
| `budget_202_New_Smile_Bil_Xbrl_2024.pdf` | facsimile deposito XBRL micro/abbreviato | deposito CCIAA | dual-year | nessuno | maybe | high |
| `budget_221_9af1ba15-4a73-4508-afad-58580b962d35.pdf` | facsimile deposito XBRL | itcc-ci-2018-11-04 | dual-year | nessuno | maybe | high |
| `budget_227_Bilancio_cee_2025_NI_verbale.pdf` | micro art.2435-ter da NI XBRL | deposito XBRL | dual-year | nessuno | yes | high |
| `budget_241_02_2024_01_Bilancio.pdf` | facsimile deposito XBRL ordinario + NI | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_247_BILANCIO_2025.pdf` | facsimile deposito XBRL ordinario completo | itcc-ci-2018-11-04 | dual-year | nessuno | maybe | high |
| `budget_253_mbs_2025_parziale.pdf` | bilancio riclassificato abbreviato (voci di legge) | ERP (modulo riclass.) | dual-year | nessuno | yes | high |
| `budget_254_bilancio___NI.pdf` | facsimile deposito XBRL (IV CEE) + NI | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_255_04.02.2026_BILANCIO___NI_DEF.xbrl.pdf` | facsimile deposito XBRL ordinario (voci di legge) + NI | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_256_Bilancio_XBRL-PDF_GHEDA_TM_SRL_es._2025_al_31-12-2025_Civilistico.PDF` | facsimile deposito XBRL abbreviato + NI | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_257_bilancio_31.12.2025_forma_abbreviata.pdf` | IV CEE forma abbreviata art.2435-bis | sconosciuto | dual-year | nessuno | maybe | high |
| `budget_265_P2195690000400007.pdf` | facsimile deposito abbreviato art.2435-bis | deposito XBRL | dual-year | nessuno | yes | high |
| `budget_269_BIL_NOTA25.pdf` | facsimile XBRL ordinario + NI | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_272_BILANCIO_OTTICO_2024.pdf` | bilancio ottico Cerved + prospetto IV CEE micro | Cerved + itcc | dual-year | nessuno | yes | high |
| `budget_275_PHOENIX_SRL_-_Bilancio_al_31.12.2025.pdf` | facsimile deposito XBRL micro | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_287_BILANCIO_XBRL_AL_31.12.2025.pdf` | facsimile deposito XBRL ordinario + NI | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_288_teberesponse.pdf` | facsimile deposito XBRL ordinario + NI | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_290_Bilancio_di_esercizio_2024.pdf` | facsimile deposito XBRL | itcc-ci-2018-11-04 | dual-year | nessuno | maybe | high |
| `budget_298_notaintegrativaabbreviata__2025_.pdf` | facsimile (SP+CE voci di legge) + NI abbreviata | deposito XBRL | dual-year | nessuno | yes | high |
| `budget_315_BERTELLI_BilancioCEE_PROVV_2025.pdf` | provvisorio IV CEE ordinario completo (mono-colonna) | sconosciuto | single | nessuno | maybe | high |
| `budget_328_2025-_ELLE_ERRE_BIL.pdf` | IV CEE ordinario civilistico (voci di legge) | sconosciuto | dual-year | nessuno | yes | high |
| `budget_329_BILANCIO_XBRL_2025.pdf` | facsimile deposito XBRL ordinario + NI | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_336_00a2fc11-15fa-4623-9200-fbcea15b618c.pdf` | facsimile deposito XBRL ordinario + NI | itcc-ci-2018-11-04 | dual-year | nessuno | yes | high |
| `budget_341_Bilancio_cee_per_previsionale.pdf` | CEE sintetico riclassificato con scostamenti | sconosciuto (TS/Sistemi?) | dual-year | nessuno | yes | high |
| `5a - NI Bil. 31 12 2025 - LIOENERGY.pdf` | civilistico abbreviato + NI (dettaglio sotto-righe PN/personale via reconciler §6) | sconosciuto | dual-year | nessuno | yes | high |

### Macro-area B — Bilancio dettagliato con macrovoci in IV CEE  (21)

| File | Sottocategoria | Gestionale | Colonne | Codici | Parsing det. | Conf. |
|---|---|---|---|---|:--:|:--:|
| `budget_147_BILAQ-31.12.2025.pdf` | sit. contabile riclass. IV CEE con dettaglio sottoconti | sconosciuto/ERP | dual-year | B.I.1.a (path CEE) | yes | high |
| `budget_152_BILAQ-001.pdf` | CEE riclassificato dettaglio sottoconti (codici CEE puntati) | sconosciuto | dual-year | B.II.3.a.6 | maybe | high |
| `budget_171_T03_Bilancio_al_31122025.pdf` | abbreviato con dettaglio conti per descrizione | sconosciuto/ERP | dual-year | descr (no codici) | maybe | high |
| `budget_176_2R_IMMOBILIARE.pdf` | sit. contabile riclass. dettagliata (path CEE) | sconosciuto/ERP | dual-year | B.II.1.a (path CEE) | maybe | high |
| `budget_182_2R_IMMOBILIARE1.pdf` | sit. contabile riclass. dettagliata (path CEE) | sconosciuto/ERP | dual-year | B.II.1.a (path CEE) | yes | high |
| `budget_207_GCGROUP_XBRL_30_09.PDF` | bilancio XBRL esteso con sottoconti (infrannuale 9M) | AGO Infinity (Zucchetti) | dual-year | 6-digit+3 | yes | high |
| `budget_209_nicee.pdf` | sit. contabile riclass. dettagliata + CoGe grezzi | sconosciuto/ERP | dual-year | CEE+7-digit | yes | high |
| `budget_280_NICEE.pdf` | CEE riclassificato dettaglio con CoGe 7-cifre | sconosciuto | dual-year | CEE+7-digit | maybe | high |
| `budget_282_MSIT-31_3_2026.pdf` | sit. contabile riclass. dettagliata (infrannuale 31/03) | sconosciuto/ERP | dual-year | path CEE | maybe | high |
| `budget_283_detail_riclass_-_2026-05-21T101520.941.pdf` | sit. contabile riclass. dettagliata (path CEE) | sconosciuto/ERP | dual-year | path CEE | yes | high |
| `budget_289_Bilancio_provvisorio_2025.pdf` | abbreviato con dettaglio conti (flag A/P/R/C) | sconosciuto | single | 9-11 digit+flag | maybe | high |
| `budget_297_bilancio_cce_provvisorio_alma_srl.pdf` | bilancio XBRL esteso con sottoconti (provvisorio) | AGO Infinity (Zucchetti) | dual-year | 6-digit+3 | yes | high |
| `budget_305_Bilancio_CEE_al_31.12.2025_con_dettaglio_sottoconti.pdf` | CEE con dettaglio sottoconti 7-cifre | sconosciuto/ERP | dual-year | CEE+7-digit | yes | high |
| `budget_313_INQCEED-001.pdf` | IV CEE con dettaglio sottoconti DEPI | Sistemi/DEPI | dual-year | XX/YY/ZZZ | maybe | high |
| `budget_314_2024.pdf` | CEE dettagliato biennale (anno corr. azzerato) | Sistemi/DEPI | dual-year | XX/YY/ZZZ | maybe | high |
| `budget_319_detail_riclass_-_2026-05-27T125618.533.pdf` | sit. contabile riclass. dettagliata (infrannuale 31/03) | sconosciuto/ERP | dual-year | path CEE | maybe | high |
| `budget_320_nicee.pdf` | sit. contabile riclass. dettagliata + CoGe grezzi | sconosciuto/ERP | dual-year | CEE+7-digit | yes | high |
| `budget_324_nicee.pdf` | CEE con dettaglio sottoconti 7-cifre | sconosciuto/ERP | dual-year | CEE+7-digit | yes | high |
| `budget_331_bilancio_kg_con_dettagliopdf.pdf` | bilancio XBRL esteso con sottoconti (holding) | AGO Infinity (Zucchetti) | dual-year | 6-digit+3 | yes | high |
| `budget_340_Bilancio_CEE_al_31.12.2025_con_dettaglio_sottoconti.pdf` | CEE con dettaglio sottoconti 7-cifre | sconosciuto | dual-year | CEE+7-digit | maybe | high |
| `sangae6_bil_ue_con_dettaglio_conti_da_genya_2025.pdf` | bilancio UE/CEE abbreviato con dettaglio conti | Genya (Wolters Kluwer) | dual-year | 6-digit | maybe | high |

### Macro-area C — Bilancio di verifica a sezioni contrapposte  (19)

| File | Sottocategoria | Gestionale | Colonne | Codici | Parsing det. | Conf. |
|---|---|---|---|---|:--:|:--:|
| `BILANCIO-TEST.pdf` | sit. patrim./econ. contrapposte (mastri DEPI) | Sistemi/DEPI | saldo | XX/YY/ZZZ | yes | high |
| `budget_131_Oprandi_Fabrizio_-_30.04.2026__provvisoria_.pdf` | sit. patrim./econ. a saldi (ditta indiv.) DEPI | Sistemi/DEPI | saldo | XX/YYYY | yes | high |
| `budget_132_Oprandi_Fabrizio_-_30.04.2026.pdf` | sit. patrim./econ. a saldi (ditta indiv.) DEPI | Sistemi/DEPI | dual-year | XX/YYYY | yes | high |
| `budget_159_BILAcona.pdf` | verifica contrapposte TeamSystem | TeamSystem | saldo | XX/YYYY/ZZZZ | yes | high |
| `budget_169_spectra.pdf` | sit. patrim./econ. contrapposte (mastri DEPI) | Sistemi/DEPI | saldo | XX/YY/ZZZ | yes | high |
| `budget_188_Sezioni_Contrapposte_Bilanci__7GP0QRV4I.frx_2025.pdf` | verifica contrapposte (FastReport .frx) | sconosciuto (FastReport) | dare-avere | 10.05.001 dotted | maybe | high |
| `budget_196_teic_provvisorio__2_.pdf` | SOLO conto economico per competenza (no SP) | ERP fiscale IIDD | dare-avere | 6-digit | no | high |
| `budget_210_Bilancio_2025--26-05-13.pdf` | verifica contrapposte (Attivita/Passivita) | BILAGRA | dare-avere | XXX.NNNNN | maybe | high |
| `budget_213_Gustopronto_srl_bilancio_di_verifica_dettaglio_conti.pdf` | verifica contrapposte con dettaglio sottoconti | BILAGRA | dare-avere | NNN.NNNNN | maybe | high |
| `budget_215_BILANCIO_GUSTOPRONTO_31-12-2024.pdf` | verifica contrapposte (Attivita/Passivita) | Sistemi/BILAGRA | dare-avere | NNN.NNNNN | maybe | high |
| `budget_229_MBS_2025.pdf` | sit. contabile colonna unica Saldo | sconosciuto | saldo | 6-digit | yes | high |
| `budget_238_CARP_2025.pdf` | sit. contabile colonna unica Saldo | sconosciuto | saldo | 6-digit | maybe | high |
| `budget_243_MBS_2025.pdf` | sit. contabile colonna unica Saldo | sconosciuto | saldo | 6-digit | yes | high |
| `budget_249_SAMAC_APPALTI_SRL_-_BILANCIO_AL_31.12.2025.pdf` | contrapposte fisiche (mastri+sottoconti) | sconosciuto | dare-avere | 6-digit+N.NN | maybe | high |
| `budget_281_MSIT-31_3_2026.pdf` | sit. patrimoniale contrapposte Dare/Avere (DEPI) | Sistemi/DEPI | dare-avere | XX/YY/ZZZ | yes | high |
| `budget_330_KG_Project_Srl_situazione_contabile_al_31-12-2025.pdf` | sit. contabile contrapposte 8-digit | sconosciuto | dare-avere | 8-digit | yes | high |
| `budget_335_TEIC_ECONOMICO_31.03.26.pdf` | SOLO prospetto economico contrapposte (no SP) | ERP fiscale | dare-avere | 6-digit | maybe | med |
| `budget_337_2023.pdf` | SP+CE contrapposte (OCR rumoroso) | sconosciuto | dare-avere | 6-digit+N.NN | no | high |
| `budget_338_Pandoro_srl_Bilancino_2025.pdf` | bilancino contrapposte fisiche affiancate | sconosciuto | dare-avere | gerarchico / | maybe | high |
| `6 - LIO - BILANCIO 31.03.2026.PDF` | **C1b** verifica contrapposte PER SEGNO (stesso conto sui 2 lati) — parser dedicato §6 | Zucchetti/DEPI | per-segno | XX.YY | yes | high |

### OTHER — non importabile / fuori perimetro  (3)

| File | Sottocategoria | Gestionale | Colonne | Codici | Parsing det. | Conf. |
|---|---|---|---|---|:--:|:--:|
| `04171640248-20251231.xbrl` | file XBRL nativo (.xbrl) | Genya | dual-year | tag XBRL | yes | high |
| `Anomalie-budget.pdf` | email di segnalazione bug (no prospetto) | - | altro | nessuno | no | high |
| `budget_137_Bilancio_LUGS_2025_DEFINITIVO.pdf` | riassunto macro non IV CEE (troppo aggregato) | sconosciuto/AI | single | nessuno | no | med |

## 6. Regole di estrazione consolidate per route (aggiornamento 2026-06-25)

Oltre al *routing* (quale macro-area prende il file), ogni route applica **regole di
estrazione GENERALI** — valide per l'intera famiglia, non per il singolo bilancio. Sono
la risposta diretta a "non sistemare per singolo caso": un nuovo file che cade nella
route ne eredita automaticamente le regole.

> **Principio cardine — "quadra" ≠ "corretto".** Il software forza sempre il pareggio
> (attivo = passivo): quando una voce è mal classificata, lo scarto viene *tappato* in un
> plug (di norma liquidità o debiti) e il bilancio quadra lo stesso, nascondendo l'errore.
> Quindi **ogni route deve classificare per NATURA e validare contro un totale di
> controllo stampato**, non limitarsi a far tornare attivo=passivo.

### Route A / B — IV CEE: reconciler deterministico delle sotto-righe
**Problema risolto** (LIO 2025): l'estrattore LLM cattura bene gli AGGREGATI ma perde le
sotto-righe di legge stampate verbatim. In particolare può **perdere una riga di RISERVA
NEGATIVA** ("A.VIII – Utili (perdite) portati a nuovo (44.217)"): il patrimonio netto
risulta troppo alto e il ribilancio lo **maschera gonfiando la liquidità** (es. 106.156 →
150.156). Inoltre lo **split del personale** (salari/oneri) non veniva estratto (li fondeva:
214.698 + 60.346 = 275.044 in salari, oneri 0).

**Regola** (`importers/pdf_extractor_llm.py`, post-LLM, solo text-path):
- `_reconcile_pn_detail` legge le righe romane **A.II–A.X → sp12a…sp12h** e ricalcola
  `sp12_riserve` come somma **ALGEBRICA** (i negativi inclusi). Applicata SOLO se
  `sp11 + Σsp12* + sp13` riconcilia al "Totale patrimonio netto" stampato → **anti-masking**.
- `_reconcile_personale_detail` legge **B.9 a/b/c/e → ce08b** salari / **ce08c** oneri /
  **ce08a** TFR / **ce08d** altri, gated su "Totale costi per il personale". Gotcha: la riga
  CE "c) trattamento di fine rapporto" va distinta dalla riga SP "C) Trattamento di fine
  rapporto di lavoro subordinato" (fondo TFR) via lookahead `(?!\s+di\s+lavoro)`.
- Agganciata su **single-year** (colonna corrente) e **dual-year** (corrente + precedente →
  corregge anche la tab **Confronti**). `pdf_importer._create_income_statement` ora salva
  ce08b/c/d (colonne DB che esistevano ma non venivano scritte).
- **No-op** sui layout senza le righe legali esplicite o se il gate non riconcilia → zero
  regressione (verificato: 115/394 invariati, sangae6 popola le riserve mantenendo il pareggio).

### Route C — sotto-famiglia "verifica a sezioni contrapposte PER SEGNO del saldo"
**Problema risolto** (LIO 2026): i conti sono messi in colonna Attività/Passività in base al
**SEGNO del saldo**, e **LO STESSO conto compare su ENTRAMBI i lati** (es. "19 Disponibilità
liquide" = banche attive in attivo *e* scoperto in passivo; idem conti erariali, risultati).
I parser generici classificavano **per COLONNA** → ammucchiavano l'intero attivo in un unico
bucket crediti (2.419.824, clienti non riconosciuti), **raddoppiavano la cassa** (302.583 vs
138.447), perdevano il dettaglio debiti (fornitori dentro "altri debiti").

**Regola** (`importers/situazione_contabile_parser.py`):
- `is_bilancio_verifica_segno(text)` — marker "BILANCIO DI VERIFICA" + "STATO PATRIMONIALE" +
  ("ECCEDENZA" / "TOTALE A QUADRATURA" / "PAREGGIO").
- `parse_bilancio_verifica_segno(file_path)` — split colonne **per COORDINATA** (gutter = x del
  2° header "Conto"/"Codice"); classifica i **MASTRI per NATURA** (descrizione, side-aware, MAI
  per colonna); **netta i fondi ammortamento** off sp02/sp03 (attenzione: descrizioni TRONCATE
  dal PDF → usare substring corti, es. `IMMATER`, `FORNITOR`, `ERARI`); separa **scoperto-banche
  (sp16a)** dalla **cassa (sp09)**; spacca i debiti (fornitori/banche/erariali/previdenza/altri);
  porta il conto risultati in PN (portati a nuovo sp12g / risultato prior sp12e); **deriva sp13
  dal CE** (ricavi − costi). **Auto-valida** attivo==passivo: se non quadra solleva `ValueError` e
  lascia agire il fallback esistente → zero regressione (0 match sul corpus storico `Test/`).
  Emette aggregati a chiavi corte + sotto-voci a **nomi-DB-pieni** (sp06a, sp16a/d/e/f/g) che
  sopravvivono a `_map_sc_keys`.
- Marca il risultato `_skip_declared_reconcile=True`: `pdf_importer` fa `pop` del flag e **salta
  il reconcile al risultato dichiarato** per le estrazioni già esatte e bilanciate (plug 0) —
  altrimenti `_declared_control_totals` scambierebbe un conto "RISULTATO D'ESERCIZIO" di anni
  precedenti per il risultato di periodo e rigonfierebbe la cassa.

> Il C1 esistente ("sezioni contrapposte fisiche") resta valido per i layout Dare/Avere classici;
> la variante **PER SEGNO** (stesso conto sui due lati) è quella nuova qui sopra.

### Route C — estrattore CoGe-LLM primario (`extract_trial_balance_with_llm`)
La rotta C prova PRIMA un pass LLM dedicato alle liste di conti CoGe (non lo schema di legge):
manda il **testo completo** (`_extract_full_text`, niente windowing SP/CE — le verifiche non hanno
header IV-CEE su cui ancorare) e usa due prompt CoGe specifici:
- `TRIAL_BALANCE_SP_SYSTEM_PROMPT` — convenzione Dare/Avere (Dare = saldo attivo/costo, Avere =
  passivo/PN/ricavo), **netting** dei conti di rettifica (fondo ammortamento / svalutazione crediti
  sottratti dal lordo, mai a passivo), mapping descrizione→sp01–18, e che il **risultato è implicito**
  (= gap Attivo vs Passivo).
- `TRIAL_BALANCE_CE_SYSTEM_PROMPT` — classifica i conti economici in ce01–20, costi tutti positivi.

Completezza (le liste lunghe fanno droppare conti al LLM in modo non deterministico): il pass SP è
ritentato fino a `_COGE_SP_MAX_ATTEMPTS = 3`, tenendo la pescata col `_plug_residual` minore e
fermandosi quando il residuo < `_COGE_SP_CLEAN_PCT = 2%` del totale. Chiude con
`_balance_trial_via_result` (sp13 = Attivo − (Passivo + PN escluso il risultato)). PDF scansionati →
`_extract_with_llm_vision` con gli stessi prompt. Solo single-year. Fallback → deterministico
(`extract_situazione_contabile`) → se vuoto, IV-CEE LLM (`force_llm=True`).

### Route A / B — fix di estrazione aggiuntivi (2026-06-25)
Stessa classe anti-masking del reconciler PN (sopra), estesa ai formati gestionali:
- **Copertura formati gestionali del reconciler PN** (`_PN_DETAIL_SPECS`/`_PN_TOTAL_SPECS`): accettano
  prefisso legale `A.` opzionale e separatore `)`/`-` **o solo spazio** (`IV   Riserva legale` senza
  separatore — budget_315); recupera la riserva NEGATIVA `A.VIII` su FLUIVER (340/341), Zucchetti
  holding (331), BERTELLI provvisorio (315) — stessa classe di LIO 2025.
- **Monocolonna non blocca più il dual-year**: `extract_pdf_both_years_with_llm` non esce più presto su
  PDF monocolonna; svuota il precedente ma lascia girare i validatori + `_reconcile_pn_detail` sulla
  colonna corrente (budget_315).
- **Colonna corrente azzerata** (Step 4c): se la corrente ha `totale_attivo ~ 0` e la precedente è
  valorizzata, la precedente viene promossa a corrente (budget_314).
- **Scoping crediti (anti doppio-conteggio):** sp06/sp07 ristretti a **C.II** circolante, esclusi i
  **B.III.2** crediti immobilizzati (sp04) — contarli due volte sbilanciava (budget_315).

## 7. Riproducibilità

- `Test/_classify_dump.py` — dedup per hash, estrae il testo di ogni PDF/XBRL unico in `Test/_analysis/dumps/`, calcola i segnali strutturali e i verdetti dei parser esistenti → `Test/_analysis/index.json`.
- `Test/_analysis/consolidate.py` — consolida le classificazioni (6 batch) → `Test/_analysis/classifications.json` + statistiche.
- `Test/_analysis/gen_doc.py` — genera questo documento da `classifications.json`.

La classificazione di ciascun file è stata fatta leggendo il testo estratto delle
prime pagine; ogni record ha `confidence` ed evidenze testuali (nei log dei batch).
I file con `confidence: med` o `deterministic: maybe/no` sono i candidati naturali
per i primi test del nuovo router.
