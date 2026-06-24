# Routing import bilanci per tipologia — analisi e tassonomia

> Documento generato dall'analisi automatica di **tutti i casi** in `Test/`
> (124 file totali, **77 documenti unici** dopo dedup per hash di contenuto).
> Obiettivo: sostituire le patch caso-per-caso con un **router per macro-area** che,
> dato un file in ingresso, ne riconosca la tipologia e lo instradi all'estrattore
> giusto. Nuovi formati ricadono nella macro-area corretta (e al peggio nel suo
> fallback) senza rompere gli altri rami.

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

## 4. Architettura del router proposta

Un unico modulo **classificatore** che gira PRIMA di scegliere l'estrattore e
ritorna `(macro_area, sottocategoria, gestionale, layout, confidence, signals)`.
La scelta dell'estrattore dipende SOLO dalla macro-area; dentro l'area il
sub-router sceglie per layout/codifica. Ordine di decisione (dal segnale più
forte al fallback):

```
0.  ext ∈ {.xbrl,.xml}                          → OTHER/XBRL  → parser XBRL nativo
1.  testo estratto < soglia (PDF scansionato)    → OCR/LLM fallback (o errore se vuoto)
2.  marker forte C:
      "TOTALE A PAREGGIO" | "BILANCIO DI VERIFICA" | "SITUAZIONE CONTABILE"
      | (alta densità codici conto CoGe AND assenza scheletro di legge)
                                                  → C  → sub-router layout+codifica
                                                         (riuso situazione_contabile_parser)
3.  scheletro di legge presente AND codici conto/CoGe presenti
      (codici-PATH CEE puntati | "dettaglio sottoconti" | header AGO XBRL)
                                                  → B  → leggi i TOTALI di voce /
                                                         aggrega sottoconti per prefisso CEE
4.  scheletro di legge presente AND nessun codice conto
      (bonus marker: "Conforme alla tassonomia itcc-…", "art. 2435-bis/ter")
                                                  → A  → estrattore IV CEE (template A1 / LLM)
5.  nessuno scheletro di legge AND nessun set conti, oppure solo CE
                                                  → OTHER → errore onesto, messaggio chiaro
```

**Principi anti-regressione** (rispondono alla richiesta "non sistemare per singolo caso"):
1. **Classifica, poi estrai.** Il singolo file non tocca mai più la logica globale: cambia solo *quale* macro-area lo prende.
2. **Ogni macro-area ha un fallback interno** che degrada con dignità invece di rompersi:
   - C → reclassify-by-description best-effort + flag `BILANCIO NON QUADRATO`.
   - B → se i sottoconti non si aggregano, usa i totali di voce di legge.
   - A → se il template facsimile non combacia, LLM.
3. **Mai mascherare.** Quando l'estrazione non quadra, errore esplicito (già la direzione presa dal balance-hardening in `pdf_mapper.validate_balance`), non plug silenzioso.
4. **Confidence + tracciamento.** Il classificatore logga `macro_area/sottocategoria/segnali` (riusa `upload_tracker`) così i nuovi formati si vedono e si assegnano a un'area, non si scoprono da un crash.

### Mappatura sui moduli esistenti
- **C** è già in gran parte coperto da `importers/situazione_contabile_parser.py` (DEPI, TeamSystem, 8-digit, single-column, contrapposte best-effort). Serve solo spostare la **detection** dentro al classificatore unico.
- **A** è il ramo `importers/pdf_extractor_llm.py` (oggi LLM). Per A1 (facsimile itcc) si può aggiungere un estrattore a template deterministico.
- **B** è il **punto più debole** oggi: va consolidato un estrattore "IV CEE + dettaglio" che (a) legge i totali di voce quando presenti, (b) aggrega per prefisso CEE per la famiglia B1. È l'area con più `maybe` (11/21).

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

## 6. Regole di estrazione consolidate per route (aggiornamento 2026-06-24)

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

## 7. Riproducibilità

- `Test/_classify_dump.py` — dedup per hash, estrae il testo di ogni PDF/XBRL unico in `Test/_analysis/dumps/`, calcola i segnali strutturali e i verdetti dei parser esistenti → `Test/_analysis/index.json`.
- `Test/_analysis/consolidate.py` — consolida le classificazioni (6 batch) → `Test/_analysis/classifications.json` + statistiche.
- `Test/_analysis/gen_doc.py` — genera questo documento da `classifications.json`.

La classificazione di ciascun file è stata fatta leggendo il testo estratto delle
prime pagine; ogni record ha `confidence` ed evidenze testuali (nei log dei batch).
I file con `confidence: med` o `deterministic: maybe/no` sono i candidati naturali
per i primi test del nuovo router.
