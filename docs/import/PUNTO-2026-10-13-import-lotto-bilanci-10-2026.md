# Punto import, 13/10/2026: lotto `bilanci-10-2026`, Unicarton e MinerU

Riepilogo della sessione del 13/10/2026: allineamento a `main`, test di import sul lotto
`bilanci-10-2026` (mappa `bilanci-budget-09-12-2026.xlsx`), correzione di Unicarton e
collegamento di MinerU alle scansioni. In fondo gli errori di import ancora aperti su 1265 e 1311.

Le prove sono state fatte **su copie del database**, salvo dove è indicato «DB locale», cioè il
`financial_analysis.db` su cui l'utente ha importato a mano.

---

## 1. Ambiente

| Cosa | Esito |
|---|---|
| Pull da `main` | fast-forward `854a6a1` → `7a55383` (156 commit), nessun conflitto con i due file Typst locali non committati (`backend/app/renderers/typst/note_fit.py`, `runtime.py`) |
| Backend non partiva | `SyntaxError: f-string: expecting '}'` in `backend/app/renderers/business_plan/sections_finanza.py:12`, introdotto dal commit `e976322` (#63): virgolette doppie dentro una f-string a virgolette doppie, valide solo da Python 3.12 |
| Causa | venv locale su Python **3.11.4**, mentre la produzione usa `python:3.12-slim` (`Dockerfile.backend`) |
| Correzione | installato Python **3.12.10** (per utente, senza toccare il PATH), `backend/.venv` ricostruito da zero su 3.12 da `requirements.txt`. Il file di `main` resta invariato |
| Nota | il venv 3.11 non ha backup: un pacchetto installato a mano fuori da `requirements.txt` va reinstallato |

---

## 2. Lotto `bilanci-10-2026`: primo giro di import (codice di `main`, motore snello)

14 documenti distinti. Gli 8 Unicarton in `errori/` (upload 1269–1279) sono lo **stesso file**
(hash identico).

| ID | Documento | Periodo | Esito | Note |
|---|---|---|---|---|
| 1263 | AITEC XBRL 2023 | 12 m | OK, quadra | avvisi «CONFLITTO AGGREGATO» sul comparativo (solo aggregati): normale |
| 1264 | AITEC XBRL 2024 | 12 m | OK, quadra | idem |
| 1267 | AITEC XBRL 2025 | 12 m | OK, quadra | utile 269.256 |
| 1309 | M.C.T. XBRL 2025 | 12 m | OK, quadra | utile 6.556 |
| 1255 | ERREGI 30/09/2026 | 9 m | OK, quadra | scansione, OCR di sempre |
| 1268 | Verifica 30/06/2026 | 6 m | OK, quadra | snello deterministico |
| 1273 | Nicole provv. 31/07 | 7 m | OK, quadra | avviso sui totali stampati |
| 1276 | BR0013420251231 (2025) | 12 m | OK, quadra | importato anche il 2024 |
| 1302 | Bilancio 2025 definitivo | 12 m | OK, quadra | stessa azienda e stesso utile di 1276 (173.464), ma **totale attivo diverso di 79.957** (3.143.582 contro 3.223.539): da verificare |
| 1308 | BILAQ-001 (1° sem.) | 6 m | OK, quadra | utile 22.113,11 |
| 1265 | AITEC bilancino 30/06/2026 | 6 m | importato, **non quadra** | vedi §6 |
| 1305 | STB verifica 01/01–30/06 | 6 m | importato, **non quadra** | SP giusto (sp13 22.113 = BILAQ 1308), **CE letto male**: utile 208.581 |
| 1311 | M.C.T. bozza 30/06/2026 | 6 m | importato, **non quadra** | vedi §6 |
| 1301 | Unicarton B 31/08/2026 | 8 m | importato, **non quadra** | sbilancio 1.225.833 (23,7%) |
| 1269–79 | Unicarton A 31/08/2026 | 8 m | **rifiutato** | vedi §3 |

Avvertenze sul giro:
- In locale manca `GX10_API_KEY`: il percorso snello si ferma alla lettura (`LLMProviderError`)
  e ripiega sull'importatore precedente. In staging, dove la chiave c'è, i risultati possono essere diversi.
- L'estrazione con LLM non è deterministica: lo stesso file dà sbilanci diversi da un giro
  all'altro (Unicarton A: 364k, 509k, 404k, 1.305k; 1311: 66.803, 332.215, 836.088, 992.936, 934.550).
- Il file Excel segna «OK» anche i bilanci squadrati, perché vengono salvati con un avviso.

---

## 3. Unicarton A: perché veniva rifiutato

- **Il file:** una scansione ripassata da PDF24/Ghostscript, con un **testo corrotto**. Ogni lettera è
  spostata di 29 posizioni («8QLFDUWRQ 6UO» = «Unicarton Srl»): circa 16.000 caratteri e nessuna parola.
  La versione B dello stesso documento (NAPS2) ha invece un testo OCR leggibile.
- **La catena di errori in `importers/pdf_importer.py`:**
  1. la regola `is_scanned = len(sample_text.strip()) < 50` non lo riconosceva come scansione;
  2. il classificatore leggeva il testo corrotto e restituiva `UNSUPPORTED` («nessuno scheletro di
     legge né elenco conti riconoscibile»);
  3. l'import si fermava **prima** del motore snello;
  4. il controllo «TESTO PDF CORROTTO» arriva dopo e riconosce solo i decimali spezzati (budget_337),
     non le lettere spostate.
- **MinerU non partiva mai:** `/import/pdf` non lo chiama; c'è solo la rotta `/import/pdf-ocr`, il cui
  pulsante è nascosto e che sul VPS è spenta.

---

## 4. Modifiche al codice (branch `feat/import-sempre-mineru`, NON committato)

Decisione dell'utente: **MinerU solo per le scansioni, senza limite di caratteri.**

| File | Modifica |
|---|---|
| `importers/pdf_importer.py` | Tolta la regola dei 50 caratteri. `_testo_leggibile()`: almeno 2 parole contabili (totale, crediti, debiti…). Scansione = testo non leggibile, vuoto o corrotto. Misurato su 268 PDF (corpus `Test/` più questo lotto): **cambia il verdetto solo sugli 8 Unicarton A**. Aggiunta `pdf_e_scansione(file_path)`, con lo stesso criterio |
| `importers/pdf_importer.py` (`_classify_balance_failure`) | Scansione letta da **MinerU** che non quadra: si importa **con avviso** («BILANCIO SBILANCIATO (lettura OCR MinerU)…»). Scansione letta dall'**OCR di ripiego**: resta **errore duro**, perché su Unicarton A inventava importi (attivo 445.200 contro circa 5,9 milioni, CE a zero) |
| `backend/app/api/v1/imports.py` | `/import/pdf` chiama MinerU **solo se `pdf_e_scansione`**. Se MinerU è spento, non risponde o restituisce testo vuoto, la scansione prosegue sull'OCR di ripiego e il fatto è dichiarato in `validation_report["mineru"]` e negli avvisi («MINERU NON USATO (…)») |
| `backend/app/core/config.py` | `MINERU_BASE_URL = http://100.65.63.12:18400` (gx10), `MINERU_EXPECTED_VERSION = 3.4.5` (misurato su `/health`) |
| `docker-compose.yml` | Tolte le righe `environment:` di MinerU, che scavalcavano l'`env_file` (`budget-env-staging`): ora lo staging può configurare MinerU |
| `tests/test_pdf_ocr_endpoint.py` | 5 test nuovi: scansione → MinerU; testo → niente MinerU; MinerU giù o spento → dichiarato; Unicarton corrotto riconosciuto come scansione |
| `tests/test_unbalanced_import.py` | `_testo_leggibile`; squadrato MinerU importato con avviso, squadrato dell'OCR di ripiego rifiutato, MinerU vuoto rifiutato |

**Test:** 115 passati nei file di import e MinerU. La suite completa ha 40 fallimenti, **tutti presenti
anche su `main` pulito** (verificato in un worktree): Typst/WSL su Windows, `os.O_NOFOLLOW`,
`test_deployment_docs` (`PRODUCTION_CONFIG.md` cita ancora `w3pro.it`), `test_vision_rescue`,
`test_parita_riepilogo`, `test_triage_rilievi_tool`, `test_m2_00_spike_fixtures`.

**Verifica sull'endpoint HTTP reale con MinerU su gx10:**

| File | MinerU | Esito |
|---|---|---|
| 1269 Unicarton A (scansione) | usato, 60.386 caratteri | **importato** (prima era rifiutato), non quadra: attivo 5.249.256 contro passivo 3.944.071, da correggere in Rettifiche |
| 1311 M.C.T. (testo) | non usato | importato con il percorso normale, non quadra |

**Per lo staging:** il server deve raggiungere MinerU. Va aperta la porta 18400 di gx10 all'IP dello
staging (come per Qwen sulla 18300) e impostato `MINERU_BASE_URL` in `budget-env-staging`. Finché non lo
si fa, sullo staging le scansioni vanno all'OCR di ripiego e il report lo dichiara.

**Da ricordare:** dopo un `pull` di questo branch **riavviare il backend**, perché `--reload` non ricarica
`importers/`. Il record del 1311 nel DB locale con `parser_version …+mineru-3.4.5` viene dalla prima
versione («ogni PDF → MinerU»), poi corretta: va reimportato.

---

## 5. Errore comune agli infrannuali: l'utile 2025 non ancora destinato

Nelle situazioni infrannuali il patrimonio netto contiene ancora il conto «Utile d'esercizio» con il
**risultato dell'anno precedente non destinato** (A.IX), più eventuali utili a nuovo (A.VIII). L'utile
**del periodo** è stampato a parte, sotto i totali. L'import confonde i due valori, e in modo diverso nei
due file:

| | Utile 2025 nel PN | Utile del periodo | sp13 in DB | Effetto |
|---|---|---|---|---|
| 1265 AITEC | 269.255,83 (conto 309, A.IX) | 230.922,13 | 230.922,13 | il 2025 sparisce: sbilancio **269.255,83**, uguale al residuo |
| 1311 M.C.T. | 6.555,78 (201.21.00001, A.IX) | 106.898,36 | 6.555,78 | il 2025 preso come utile del periodo, l'utile vero va perso |

**Correzione da fare:** l'utile dell'anno precedente (con gli utili a nuovo A.VIII) va in
`sp12g_utili_perdite_portati` o tra le riserve; `sp13` deve essere l'utile del periodo.

---

## 6. Errori per documento (DB locale)

### 1265, AITEC (company 46, fy 44), sbilancio 269.255,83

Corretto l'utile 2025, il bilancio quadra. Il totale attivo (12.084.291,97) e le immobilizzazioni
(immateriali 1.278.788,99, materiali 927.991,44) sono giusti. La **composizione** però è sbagliata in
più punti.

Attivo (spostamenti interni, la somma è zero):
- Immobilizzazioni finanziarie: 279.185 in DB contro 153.145 nel PDF.
- Crediti tributari: 550.985 contro 628.350 (655.903 − 27.553). Mancano circa 105k.
- Ratei attivi: 114.930 contro 180.748. Mancano circa 66k.
- Liquidità +33k e clienti +12k rispetto al PDF.

Passivo:
- TFR: 288.289 in DB contro 316.498 nel PDF. I circa 28k di differenza sono finiti in previdenza
  (+12,8k) e in altri debiti (+15,4k).

Conto economico (l'utile torna, le voci no):
- Personale: 1.525.012 in DB contro 1.907.352 (conto 720). Mancano circa 382k.
- Ammortamenti: 17.297 in DB contro 353.358 (conti 725 + 727). Mancano circa 336k.
- Oneri diversi: 786.720 in DB contro circa 10,7k nel PDF (conti B14 735 + 737).
- Materie +98k e servizi −96k: scambiati tra loro.

Il report segnala anche 5.673.612,81 di «massa non classificata» (stato `unreliable`), cioè importi
stampati che non sono finiti in nessuna voce IV-CEE.

### 1311, M.C.T. bozza (company 50, fy 43), sezioni contrapposte

Il PDF **quadra da solo**: attivo lordo 5.421.078,81 = passivo 5.314.180,45 + utile del periodo
**106.898,36**. L'attivo netto in DB (3.906.915) è corretto, il passivo no.

Stato patrimoniale:
1. **Mastro fornitori 481.427,30 mancante.** In `sp16d` c'è solo «fatture da ricevere» (11.207).
2. **Scoperti di c/c persi.** I c/c negativi (UniCredit −129.967, Tonengo ANT. −137.828, Intesa −91.324,
   Credem −4.322, carta −201: in totale circa 358–364k) vengono tolti dalla liquidità, che resta 819, e
   fin qui è corretto. Ma poi non vengono aggiunti a `sp16a` debiti verso banche.
3. **Patrimonio netto sbagliato.** Il PDF stampa capitale 300.000, riserve 271.796,73, A.VIII utili a
   nuovo 139.129,83 e A.IX utile 2025 6.555,78 (totale PN 717.482,34), più l'utile del periodo 106.898,36:
   in tutto 824.380,70. L'utile 2025 è stato preso come utile del periodo (§5), e A.VIII manca in uno
   dei giri.
4. **Debiti diversi incoerenti.** L'aggregato `sp17` (614.595) non torna con i dettagli: la previdenza
   oltre 12 mesi (181.512,49) resta fuori dal totale. «Dipendenti c/INPS» −70.079 è stato ignorato
   (previdenza in DB 232.001 contro 161.921 nel PDF), e gli altri debiti risultano 196.494 contro 67.507.
   In tutto i debiti diversi sono circa 167k in meno rispetto ai 1.740.641,58 stampati.

I punti 1–4 spiegano lo sbilancio di 934.550 a meno di qualche decina di euro di arrotondamento.

Conto economico (utile vero 106.898,36). Due letture diverse, una per giro:
- In un giro **49.077,06**: personale 825.054,74 contro 763.516,83 stampati (715.825,43 + compensi agli
  organi sociali 42.107,39 + altre prestazioni 5.584,01), cioè +61.537,91; altri ricavi 3.926,61
  contro 210, perché gli straordinari 3.736,61 sono contati due volte, cioè +3.716,61. Le due cifre
  spiegano al centesimo i 57.821,30 di differenza.
- In un altro giro **158.326,37**: mancano i compensi agli organi sociali (42.107,39) e le altre
  prestazioni (5.584,01); gli straordinari sono contati due volte (ce04 e ce18); il personale (715.825)
  è tutto in «altri costi», e salari (517.048) e oneri sociali (155.916) non sono stati letti.
- In entrambi i giri le attività finanziarie non immobilizzate (C.III, 158.035) sono collocate male.
- Nel giro con MinerU lo SP era tutto in **euro interi** (6.556, 413.846) mentre il PDF ha i centesimi.

### Altri del lotto
- **1305 STB:** utile CE 208.581 contro 22.113,11 stampato sia nello SP sia nel CE. Debiti a breve:
  dettagli 571.540 contro un totale di 352.022.
- **1301 Unicarton B:** con l'importatore precedente lo sbilancio era 1.225.833 (attivo 707.076 sotto
  il totale stampato). Letto da MinerU scende a 237.571, vicino ai 241.711,59 di scarto che **il
  documento stesso** stampa fra attivo (5.888.998,46) e passivo (5.647.286,87).
- **1276 / 1302:** stesso bilancio 2025, attivi diversi di 79.957 (vedi §2).

---

## 7. Cose aperte

| # | Cosa | Dove |
|---|---|---|
| 1 | Utile dell'anno precedente (A.IX) e utili a nuovo (A.VIII) negli infrannuali: vanno nelle riserve, `sp13` = utile del periodo | tutti gli infrannuali (1265, 1311) |
| 2 | Sezioni contrapposte: mastri fornitori e clienti non letti, scoperti di c/c non portati tra i debiti verso banche, previdenza/tributari oltre 12 mesi fuori dagli aggregati | 1311 |
| 3 | CE: personale contato in eccesso o su «altri costi», straordinari doppi, ammortamenti e oneri diversi scambiati | 1265, 1311, 1305 |
| 4 | Composizione AITEC (fin./tributari/ratei/TFR) da riallineare | 1265 |
| 5 | Commit del branch `feat/import-sempre-mineru` e merge su `main` (merge = deploy in staging) | — |
| 6 | Staging: aprire la porta 18400 di gx10 all'IP dello staging, `MINERU_BASE_URL` in `budget-env-staging` | infrastruttura |
| 7 | Unicarton A: entra con MinerU ma lo sbilancio cambia a ogni giro: numeri da controllare in Rettifiche | 1269 |
| 8 | `GX10_API_KEY` assente in locale: lo snello non si può provare per intero | ambiente |
| 9 | 40 test che falliscono già su `main` (Windows/WSL, Typst, `w3pro.it` in `PRODUCTION_CONFIG.md`) | test |
