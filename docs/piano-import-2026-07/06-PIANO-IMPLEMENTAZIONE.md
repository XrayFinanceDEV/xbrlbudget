# 06 — Piano di implementazione

Piano operativo per eseguire i fix del piano (file 01-05), organizzato in **8 PR sequenziali**. Ogni PR: branch, file/funzioni da toccare (con righe attuali), passi di implementazione, test da scrivere PRIMA, comando di verifica, rischi. Le righe citate si riferiscono al working tree al 2026-07-14 (fix netting non committati inclusi) — dopo PR-1 restano valide.

## Prerequisiti ambiente (una volta sola)

```bash
cd C:/DEV/xbrlbudget-main/xbrlbudget
backend/venv/Scripts/activate          # o il venv usato dal progetto
python -m pytest tests/test_contra_netting.py -q     # deve essere verde PRIMA di iniziare
python Test/_quadratura_harness.py                    # baseline deterministica: salvare l'output
```

Regole fisse per tutte le PR:
- **Riavviare il backend** dopo ogni modifica a `importers/` (uvicorn `--reload` non li ricarica) quando si testa dall'app.
- Test LLM/vision (route A/B, CoGe-LLM) solo se `ANTHROPIC_API_KEY` è settata; tutte le PR 1-7 sono testabili in puro deterministico.
- Ogni PR chiude con: suite pytest verde + harness sul corpus senza peggioramenti rispetto alla baseline salvata.

---

## PR-1 (T0) — Commit dei fix netting esistenti

**Branch:** `fix/contra-netting` (da `fix/budget-forecast-tax-credits-and-report-detail` o da main, decidere in base alla strategia di merge corrente).

**Passi.**
1. `python -m pytest tests/test_contra_netting.py tests/test_overlay_debt_typing.py tests/test_debt_type.py -q`
2. `python tests/run_contra_regression.py` (corpus check dedicato al netting)
3. `python Test/_quadratura_harness.py` → confrontare con la baseline nota (19/28 route deterministica; nessun peggioramento)
4. Spostare i 2 PDF untracked `docs/examples/budget_210_*.pdf`, `budget_211_*.pdf` in `Test/sez-contrapposte/` se non già presenti lì (sono corpus di test, non documentazione), oppure committarli dove sono se servono alle doc.
5. Commit unico dei tre file modificati con messaggio che elenca i fix (split prefix-agnostic, `_dedup_parent_child` figli diretti, fondi svalutazione immobilizzazioni, riduzione ancora dichiarata, skip pagine "Dettaglio ratei").

**Rischio:** nessuno (codice già in uso locale). Effort: S.

---

## PR-2 (T1+T2+T3) — Harness `--production`, ground truth, report non-classificati

**Branch:** `test/harness-production`. Nessun cambio di comportamento dell'import: solo refactor + strumenti. **Va fatta PRIMA dei fix** perché è il metro con cui si misurano.

### 2a. Estrarre la pipeline route C riusabile

- In `importers/pdf_importer.py`, il blocco route C (righe ~350-549) contiene la sequenza: scelta candidato → `_map_sc_keys` → `overlay_debt_typing` → `net_contra_accounts` (:492-499) → riduzione ancora (:513-519) → `_reconcile_trial_to_declared` → `enforce_ce_sp_identity` (:579-590) → `validate_balance`.
- Estrarre una funzione pura `run_route_c_postprocess(bs, ce, file_path, text, declared) -> (bs, ce, diagnostics)` che incapsula tutto ciò che avviene DOPO l'estrazione del candidato. `import_pdf_balance_sheet` la chiama al posto del codice inline (refactor a parità di comportamento: nessuna logica nuova).
- `diagnostics` è un dict: `{plug_residual, plug_detail, netted_contra, ce_sp_plug, warnings}`.

### 2b. Flag `--production` nell'harness

- `Test/_quadratura_harness.py`: aggiungere `--production`. Per i file route C: dopo `extract`, chiamare `run_route_c_postprocess` e POI `check_quadratura`. Per route A/B (solo con `--llm`): applicare `reconcile_ivcee_balance` + `enforce_ce_sp_identity` prima del check.
- Output esteso per file: `quadra | masked | empty | plug | sp02 | sp03 | sp13 | totale_attivo` (colonne fisse, parseable).

### 2c. Ground truth

- Nuova dir `Test/_ground_truth/` con un JSON per file, chiave = nome file PDF:
```json
{
  "budget_395 AGRIMIX.pdf": {"totale_attivo": null, "sp02": 39783.68, "sp03": 1862490.15},
  "budget_210 Bilancio 2025.pdf": {"sp02": 169996.00, "sp03": 100363.91, "plug_max": 24},
  "budget_211 Gustopronto.pdf": {"sp02": 182260.00, "sp03": 122967.10, "sp13": -90819.92},
  "budget_405 PROGETTO DI BILANCIO.pdf": {"sp02": 0.61, "sp03": 5756144.64},
  "budget_131 Oprandi.pdf": {"totale_attivo": 355878.76, "sp02": 8069.50, "sp03": 126595.70},
  "budget_343 ver_definitiva.pdf": {"sp13": -41892.29, "plug_max": 0},
  "budget_348 ver_definitiva.pdf": {"sp13": -69804.55, "plug_max": 0}
}
```
  (valori dall'audit 2026-07-14; completare `totale_attivo` di 395 leggendo il PDF al momento della compilazione). L'harness con `--production` confronta e stampa gli scostamenti — **prima dei fix, 395/210/211/131 devono risultare ROSSI**: è la conferma che il metro funziona.

### 2d. Report righe non classificate

- Nuovo `Test/_unclassified_report.py`: itera il corpus route C, raccoglie da `diagnostics.plug_detail` (vedi PR-5) e dai bucket generici (`sp06` default di `_classify_sp_attivo:494`, `sp16` default di `_classify_sp_passivo:502`) le righe (descrizione, importo, file), aggrega per descrizione normalizzata, ordina per massa totale. Finché PR-5 non espone `plug_detail`, la prima versione può instrumentare `extract_contrapposte_best_effort` con un hook di logging.

**Verifica PR-2:** harness `--production` su `Test/sez-contrapposte` riproduce ESATTAMENTE gli esiti dell'audit (tabella in 00-OVERVIEW). Effort: M.

---

## PR-3 (T4) — budget_395: split immat/mat dei fondi

**Branch:** `fix/netting-immat-split-aggregates`. Tutto in `importers/situazione_contabile_parser.py`, funzione `_contra_classify` (:2621) e helper (:2460-2560).

### Test prima (in `tests/test_contra_netting.py`)

1. Test unitario `_contra_classify` con le righe sintetiche di budget_395:
   ```
   attivo:  ("03","IMMOBILIZZAZIONI IMMATERIALI",151380.48), ("06","IMMOBILIZZAZIONI MATERIALI",4611095.08), + foglie
   passivo: ("04","F/AMM IMMOB. IMMAT.",111596.80),
            ("04.xxxx","F/AMM.LIC. D'USO SOF. A TEM. IND",…), ("04.yyyy","F/AMM.ALT. COS. AD UT. PLU. AMM",…),
            ("04.zzzz","F/AMM. LAV. STR. SU BENI DI TERZ",…), ("04.wwww","F/AMM.COSTI IMPIANTO",…),
            ("07","F/AMM IMMOB. MATERIALI",2748604.93), + foglie materiali
   ```
   Atteso: `fondi_immat == 111596.80`, `fondi_mat == 2748604.93`.
2. Test end-to-end sul PDF reale: `net_contra_accounts` su budget_395 → `sp02 == 39783.68`, `sp03 == 1862490.15`.
3. Regression: i casi esistenti del file di test (210, 211, 343, 348, 405) invariati.

### Implementazione

1. **Fondi pre-dedup con aggregati** — il bug primario: in `_contra_classify` i fondi sono raccolti DENTRO il loop post-`_dedup_parent_child` (:2657, :2673), quindi la riga aggregata "04 F/AMM IMMOB. IMMAT. 111.596,80" è già stata eliminata (i figli sommano al padre) prima che `_reduce_fondi`/`_agg_or_sum` (:2697-2707) possano preferirla. Gli anchor lordi (:2641-2647) sono invece già raccolti dai ROW RAW — replicare lo stesso pattern: raccogliere le righe fondo (`_is_fondo_amm`) da `attivo_rows`/`passivo_rows` **prima** del dedup in due liste `fondi_att_raw`/`fondi_pas_raw`, e passare QUELLE a `_reduce_fondi`. `_agg_or_sum` gestisce già l'overlap padre/figli (l'aggregato vince come max) — il dedup sui fondi diventa superfluo. I loop dedup restano per `att_total`/IVA/gross (invariati).
2. **Riconoscere l'aggregato troncato** — `_is_fondo_immat_aggregate` (:2496) richiede `'IMMOBILIZ' in d`: "F/AMM **IMMOB.** IMMAT." non matcha. Rilassare a `'IMMOBILIZ' in d or 'IMMOB.' in d or 'IMMOB ' in d` in ENTRAMBI `_is_fondo_aggregate` (:2478) e `_is_fondo_immat_aggregate`. Attenzione all'interazione con `_FONDO_CATEGORY_KW` (:2470): contiene `'. IMM'` e `'IMMAT'` proprio per marcare il sub-aggregato immat come "specifico" rispetto al grand-total — la modifica non li tocca.
3. **Bucketizzazione per gerarchia di codice (fallback strutturale)** — in `_contra_classify`, dopo aver raccolto i fondi raw: se una riga fondo con codice `C` ha un antenato fondo (codice prefisso di `C`) il cui bucket è determinabile (`_is_fondo_immat_aggregate` → immat; caption con `_FONDO_MAT_KW`/"IMMOB. MAT" → mat), la foglia **eredita il bucket del padre** invece di passare da `_fondo_is_immat` sulla propria caption abbreviata. Implementare come pre-pass che costruisce `{code: bucket}` per gli aggregati e una lookup del prefisso più lungo.
4. **Guardia anti-regressione dello split** — in `net_contra_accounts`, sezione apply (:2983-3006): calcolare quanto lo split è "confermato": se NESSUN aggregato immat è stato trovato E le foglie immat riconosciute pesano < 50% della massa fondi che si sta assegnando a un bucket, e il candidato aveva già `old_02 ≈ base_02 − immat_contra_candidato` coerente (il candidato aveva nettato correttamente), preferire i valori del candidato: `logger.info` e no-op sullo split (solo netting del totale). Questo protegge i layout futuri con abbreviazioni ancora diverse.
5. Solo in coda, e solo se i punti 1-3 non coprono tutto il test: aggiungere token abbreviati a `_FONDO_IMMAT_KW` (:2512): `'SOF'` (con spazio/punto attorno per non matchare parole), `'UT. PLU'`, `'LAV. STR'`.

**Verifica:** pytest + harness `--production` → 395 verde in ground truth; 343/348/405/210/211 invariati. Effort: M. **Rischio principale:** il punto 1 cambia il totale fondi su layout dove il dedup era necessario (padre+figli entrambi presenti E `_agg_or_sum` senza caption aggregata riconosciuta li sommerebbe due volte) — mitigato perché `_agg_or_sum` somma le foglie solo quando NESSUN aggregato matcha, e in quel caso le foglie raw includono il padre non riconosciuto… → coprire con test: layout 343/348 (3 livelli) DEVE dare lo stesso totale di oggi. Se emerge doppio conteggio, applicare `_dedup_parent_child` alle sole liste fondi ma SALVANDO prima gli aggregati riconosciuti (dedup con whitelist).

---

## PR-4 (T5) — budget_211: arbitraggio utile/perdita

**Branch:** `fix/declared-result-arbiter`. File: `importers/pdf_extractor_llm.py`.

### Test prima

1. Unitario su `_reconcile_trial_to_declared`: `declared = {utile: 20581.27, perdita: 90819.92, pareggio: 1713937.42, attivo: 1623117.50}`, `bs.sp13` qualunque → il risultato scelto deve essere **−90819.92** (perché `attivo + perdita == pareggio` entro tolleranza, mentre `attivo + utile` no).
2. Unitario: solo `utile` presente (nessuna perdita) → comportamento invariato.
3. Unitario: `utile` da marker "risultato d'esercizio" + gap che conferma l'utile → utile vince (nessuna regressione sui file dove quel marker è il solo segnale ed è corretto).
4. End-to-end budget_211: `sp13 == −90819.92`, plug < 1%.

### Implementazione

1. **Separare il marker debole** in `_declared_control_totals` (:2223-2227): togliere `"risultato d'esercizio"`/`"risultato dell'esercizio"` dalla lista `utile` e restituirli in una chiave nuova `out["risultato"]` (ambigua: può essere il risultato dell'anno o un conto PN dell'anno prima; il segno non è noto).
2. **Arbitro in `_reconcile_trial_to_declared`** (:2267-2281): costruire la lista dei candidati risultato:
   - `+utile` (marker forte), `−perdita` (marker forte), `±risultato` (marker debole, entrambi i segni),
   - e per ciascuno calcolare la coerenza con gli altri dichiarati: `score = |declared_attivo + max(0, −cand) … |` — concretamente: il candidato vince se `pareggio ≈ attivo + max(0, −cand)` (perdita nel pareggio) oppure `attivo_decl − passivo_decl ≈ cand` (implicito già gestito a :2273-2281).
   - Secondo segnale a parità: risultato dal CE se disponibile al chiamante — passare `ce_result: Optional[Decimal]` come nuovo parametro (il chiamante in `pdf_importer` ce l'ha: `_net_profit_from_ce(ce)`), candidato coerente col CE entro 0,5% vince.
   - Nessun candidato riconciliabile → comportamento attuale (utile > perdita > implicito), così i layout senza pareggio/attivo dichiarati non cambiano.
3. Aggiornare il chiamante in `pdf_importer.py` (route C) per passare `ce_result`.

**Verifica:** pytest; harness `--production`: 211 verde, nessun file route C peggiorato; grep sul corpus dei file con marker "risultato d'esercizio" e ricontrollo mirato. Effort: S/M. **Rischio:** file dove il pareggio dichiarato è a sua volta mal letto → l'arbitro sceglie male; mitigato dal fallback al comportamento attuale quando nessun candidato riconcilia.

---

## PR-5 (T6 + parte di T7) — budget_210: overwrite conservativo + `_plug_detail`

**Branch:** `fix/netting-preserve-extra-mass`. File: `importers/situazione_contabile_parser.py`.

### Test prima

1. Unitario `_classify_sp_attivo`: `"ANTICIPO X CANONI MACCHINARI"` → crediti (non `gross_sp03`); `"IMMOBILIZZAZIONI IN CORSO E ACCONTI"` → resta immobilizzazioni.
2. Unitario `net_contra_accounts`: candidato con `sp03 = base_03 + 39000` (massa estranea parcheggiata) → dopo l'overlay, i 39.000 stanno in `sp06g_altri_crediti_breve`/`sp06_crediti_breve`, non spariti; `totale_attivo` coerente.
3. End-to-end budget_210: plug ≤ 24 €.

### Implementazione

1. **Classificatore**: in `_SP_ATTIVO_RULES` (sopra :489) aggiungere IN TESTA (le regole sono ordinate, più specifiche prima): `(['ANTICIP'], 'sp06')`, `(['ACCONT', 'FORNITOR'], 'sp06')` — MA prima verificare le regole esistenti per "IMMOBILIZZAZIONI IN CORSO E ACCONTI" (legittimo sp03): la regola nuova deve richiedere l'assenza di `IMMOBILIZZ`/`IN CORSO` (`_kw_match` supporta solo AND di keyword → usare una regola con guard esplicito nel codice di `_classify_sp_attivo`, o inserire prima la regola specifica `(['IN CORSO'], 'gross_sp03')`).
2. **Overwrite conservativo** in `net_contra_accounts`, ramo non-anchored (:2992-3006): calcolare `extra = max(0, old_03 − base_03) + max(0, old_02 − base_02)` PRIMA dell'overwrite (con `base_*` = anchor stampato quando presente). Se `extra > max(2€, 0.5% decl_total)`: dopo l'overwrite, ribucare `extra` in `sp06g_altri_crediti_breve` (+ aggiornare `sp06_crediti_breve` e il computo di `att_delta` a :3005 di conseguenza) e loggare `"contra-netting: massa estranea {extra} spostata da immobilizzazioni a crediti"`. NB: farlo solo quando l'anchor stampato esiste — senza anchor, `base = gross keyword-sum` che può sottostimare (il commento a :2993-2998 documenta il caso budget_210 inverso).
3. **`_plug_detail`** (base per T7/PR-6): in `extract_contrapposte_best_effort`, ai punti dove il residuo va in sp09/sp16 (:3456-3490), accumulare le righe non classificate in `bs['_plug_detail'] = [(desc, amount, side), ...]`; farla sopravvivere a `_map_sc_keys` (aggiungerla alla whitelist dei meta-campi come `_plug_residual`) e propagarla in `diagnostics` (PR-2a). Nel warning `BILANCIO NON QUADRATO`, elencare le prime 5 voci per importo.

**Verifica:** pytest; harness: 210 plug ≤ 24; corpus invariato. Effort: S/M.

---

## PR-6 (T7) — budget_405: alias + netting fondo svalutazione crediti

**Branch:** `fix/aliases-risconti-svalcrediti`. File: `situazione_contabile_parser.py`, `data/iv_cee_tree.json`.

### Test prima

1. Unitario classificazione: `"RISCONTI PASSIVI PLURIENNALI"` → sp18 (ratei/risconti passivi); `"F.DO SVAL.CREDITI ENTRO 12 MESI"` → netting su sp06.
2. End-to-end budget_405: plug < 1% (da 870.467).

### Implementazione

1. `_SP_PASSIVO_RULES`: regola `(['RISCONT'], 'sp18')` se non presente / verificare perché "PLURIENNALI" non matcha oggi (probabile regola esistente troppo stretta `['RISCONTI','PASSIV']` che fallisce su righe spezzate — controllare con il PDF).
2. `data/iv_cee_tree.json`: aggiungere alias `"risconti passivi pluriennali"`, `"risconti pluriennali"` al nodo E.risconti passivi.
3. Netting svalutazione crediti: oggi `_SVALUT_NON_IMMOB_KW` (:2542) ESCLUDE i crediti dal netting immobilizzazioni (giusto) ma la massa resta non gestita nel best-effort → aggiungere in `extract_contrapposte_best_effort`/`cl_pas`: una riga passivo `FONDO SVALUTAZIONE CREDITI`/`F.DO SVAL.CREDITI` viene NETTATA su sp06 (qualificatore "ENTRO") o sp07 ("OLTRE"; default sp06), riducendo anche `iv_total` come già avviene per i fondi ammortamento (meccanismo `netted_contra` esistente).
4. Rilanciare harness su 405: se il plug resta > 1%, leggere `_plug_detail` (PR-5) e iterare gli alias mancanti nella stessa PR.

**Verifica:** pytest + harness: 405 sotto soglia masking; 343/348 invariati. Effort: M (iterativo).

---

## PR-7 (T8) — budget_131: parser DEPI multi-colonna

**Branch:** `fix/depi-multicolumn`. File: `situazione_contabile_parser.py`, `parse_entries_contrapposte_depi` (:1643) e/o il sub-parser DEPI `XX/YYYY` effettivamente attivo su questo file (verificare con `Test/_classify_dump.py` quale route/parser prende budget_131 — l'audit indica layout `XX/YYYY` a 3 colonne saldo).

### Test prima

1. End-to-end budget_131: `totale_attivo == 355878.76`, `sp02 == 8069.50`, `sp03 == 126595.70`, plug ~0.
2. Regression: gli altri DEPI del corpus (budget_281 flat-DEPI, i `XX/YYYY` esistenti) invariati.

### Implementazione

1. **Rilevare l'header multi-data**: nella pagina, regex `(\d{2}/\d{2}/\d{2,4})` ripetuta ≥ 2 volte sulla riga di intestazione colonne → lista date con la loro coordinata x (il parser DEPI lavora già sul testo; se serve la coordinata, usare `page.get_text("words")` come fanno `is_contrapposte_file` e i parser coordinate-based esistenti).
2. **Scegliere la colonna target**: data più recente; se `fiscal_year` è disponibile nel contesto di chiamata, preferire la colonna il cui anno combacia (il parametro oggi non arriva fino al parser — passarlo opzionalmente da `extract_situazione_contabile`, default None → più recente).
3. **Estrarre il saldo per coordinata**: per ogni riga conto, prendere il numero la cui x ricade nella banda della colonna target (± metà larghezza colonna), ignorando le colonne % (banda diversa). Non usare la posizione ordinale dei numeri.
4. **prior_bs_data (bonus, solo se a costo zero)**: la colonna precedente può popolare `return_prior`; NON forzarlo in questa PR se complica — la PR è già invasiva.

**Verifica:** pytest + harness `--production`: 131 verde in ground truth. Effort: M. **Rischio:** regressione sui DEPI mono-colonna → il ramo multi-colonna deve attivarsi SOLO quando l'header multi-data è rilevato (guard esplicito, default = comportamento attuale).

---

## PR-8 (T9-T15) — batch successivi (dopo verifica delle PR 3-7 in app)

In ordine, ciascuno col proprio branch e lo stesso schema test-prima:

| PR | Task | Sintesi implementativa |
|---|---|---|
| 8a | T9 ancora validata | in `_reconcile_trial_to_declared` (:2313-2318 ramo total-coverage) e `net_contra_accounts` (:2905-2909): usare il dichiarato solo se 2 su 3 (pareggio/attivo/passivo) concordano entro 0,5% o se lo scarto dalla somma estratta è < 20% |
| 8b | T10 batch alias | da report `_unclassified_report.py`: PR di soli dati (`iv_cee_tree.json` + `_SP_*_RULES`); regola generale funzione>categoria in `_classify_sp_attivo` |
| 8c | T11 debiti | `_reduce_debts` (:2855): rimozione proporzionale ai bucket invece dell'ordine fisso sp16g→sp16e→sp17g; fallback typed `sp16g` a :3381; strip risultato (:3340): escludere `PRECEDENT|PORTAT` |
| 8d | T12 route B cross-check | generalizzare il pattern `_validate_crediti` (:2427) a immobilizzazioni/debiti: somma sottoconti visibili vs totale voce, flag se divergenza > 1% |
| 8e | T13 budget_337 | `TRIAL_BALANCE_SP_SYSTEM_PROMPT`: "i conti AMMORTAMENTO/AMM.TO di CE (82xxxx) NON sono fondi, non nettarli"; cross-check post-LLM con lo scan di `net_contra_accounts` |
| 8f | T14 scala G6 | suite esaustiva su `pdf_mapper.parse_italian_number` PRIMA di toccare qualsiasi cosa; guardia plausibilità 10 mld nel result |
| 8g | T15 | propagare `_ce_sp_plug` nel messaggio di import |

I task backend (T16-T20, file 04) sono un filone separato (`frontend/lib/api.ts`, `AuthContext.tsx`, `backend/app/core/auth.py`) e possono procedere in parallelo con un altro branch; T19 (licenze) resta bloccato sulla decisione di business.

---

## Sequenza e gate di avanzamento

```
PR-1 (commit esistente) ─► PR-2 (metro di misura) ─► PR-3 (395) ─► PR-4 (211) ─► PR-5 (210) ─► PR-6 (405) ─► PR-7 (131) ─► PR-8a..g
```

Gate per passare alla PR successiva: (1) pytest verde, (2) harness `--production` senza peggioramenti sul corpus completo `Test/`, (3) ground truth della PR corrente verde, (4) import verificato dall'app (backend riavviato) sul file target della PR.

Al termine della catena PR-3..7, il criterio di accettazione complessivo è quello di 03-QUADRATURA-E-HARNESS §"Criterio di accettazione": tutti i sez-contrapposte deterministici verdi campo-per-campo, 337/Bilancino dichiarati via LLM/vision.
