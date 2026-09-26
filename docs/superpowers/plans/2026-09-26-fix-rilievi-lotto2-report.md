# Fix rilievi AMBIENTA · Lotto 2 (report e indici) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chiudere A01-bis, A02, C01–C09: una definizione per indice, uguale in report, Indici e wizard; il PDF in bozza dice quando il previsionale è vecchio.

**Architecture:** gli oracoli sono i test `xfail` di `tests/test_rilievi_ambienta.py` (A01_bis, A02, C01…C09): ogni task toglie i marcatori dei suoi. Le formule degli indici si correggono **alla fonte** (`calculations/ratios.py` per gli analitici/Allegato E e la pagina Indici, `calculations/report_indicators.py` per gli indici della pratica/Sez. 8/Allegato D), con una funzione condivisa dove due implementazioni divergono. Quota capitale (C01) ed erogazioni (C08) nascono dal motore: il lotto 1 persiste `ForecastYear.engine_meta`; questo lotto vi aggiunge `erogazioni` dell'anno, e il rendiconto calcola `rimborsi = erogazioni − Δ debito finanziario` (formula della spec).

**Tech Stack:** Python 3 (ReportLab/python-docx renderer del Business plan, SQLAlchemy), pytest; Next.js (una pagina, `/report`).

**Spec:** `docs/superpowers/specs/2026-09-26-fix-rilievi-ambienta-design.md` (§3 Lotto 2, §4 Verifica).

## Global Constraints

- Worktree `/home/peter/DEV/budget-fix-rilievi-l2`, branch `fix/rilievi-lotto2` (da `fix/rilievi-ambienta`, lotto 1 compreso). Mai scrivere in `/home/peter/DEV/budget`, `/home/peter/DEV/budget-fix-rilievi` o `/home/peter/DEV/budget-fix-rilievi-l3`. Niente push.
- Python `../budget/backend/venv/bin/python -m pytest …` dalla radice del worktree. Frontend `cd frontend && npx vitest run && npx tsc --noEmit && npm run build` quando si tocca un `.ts(x)` (una directory spuria `frontend/budget/…` creata dal build si cancella, mai in stage).
- Suite intera (gate): `S=/tmp/claude-1000/-home-peter-DEV-budget/c84cb587-b7a2-4376-a794-7618627d4d71/scratchpad; cp /home/peter/DEV/budget/financial_analysis.db $S/real_migrated_l2.db && ../budget/backend/venv/bin/python migrate_db.py $S/real_migrated_l2.db >/dev/null && BUDGET_REAL_DB=$S/real_migrated_l2.db ../budget/backend/venv/bin/python -m pytest tests -q -p no:warnings > $S/suite_l2.txt 2>&1; tail -15 $S/suite_l2.txt` — attesi solo i 6 fallimenti preesistenti: test_bp_data::test_from_report_infrannuale_ambienta, test_editorial_notes_service::test_automatic_prose_definition_changes_invalidate_fit_signature_and_require_worker_reload, test_inf_data::test_ambienta_coincide_col_riferimento, test_inf_document::test_ambienta_cifre_del_riferimento, test_inf_rilievi::test_arrotondamenti_come_la_tabella, test_vision_rescue::test_build_ce_non_manda_un_ricavo_sconosciuto_su_una_voce_di_costo. (Alcuni test su DB vero leggono cifre del report infrannuale: se un indice corretto qui li sposta, è un cambiamento voluto da classificare, non da nascondere.)
- Test in memoria (`tests/rilievi_kit.genera(..., report=True)`) o su copia del DB. Niente bilanci inventati: base `tests/fixtures/ambienta_2026.json`.
- Soldi in `Decimal`. Un indice senza dati è `None` con una ragione dichiarata, mai zero.
- **Una definizione per indice**: dove due implementazioni divergono se ne tiene una, e l'altra la chiama. I modelli di rating (Altman, FGPMI, `crisi_impresa.py`) hanno definizioni proprie e **non si toccano** in questo lotto.
- Un test esistente che fissa il comportamento che la spec cambia si riscrive sulla decisione nello stesso commit, con un commento `# lotto 2 fix rilievi (2026-09-26): <regola>`, ed è elencato nel messaggio di commit. Qualunque altra rottura: fermati e segnala.
- Frasi a schermo e nel documento in italiano, con le parole esatte della spec dove la spec le dà.
- File con fine riga misti: modifiche additive, `git diff --stat` prima di ogni commit.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

- Anno di piano senza `engine_meta` (previsionale generato prima del lotto 1, `NULL`): BEP ed erogazioni ricadono su un valore dichiarato (`None` con ragione, o la formula di prima dichiarata), mai su un numero inventato e mai su un errore 500. Test nei Task 2 e 5.
- Colonna base/storica (nessun piano): DSCR, DSO, rendiconto calcolati sui soli dati del bilancio, senza leggere `engine_meta`. Test nei Task 3, 5, 6.
- Divisioni per zero (ricavi 0, PN 0, immobilizzazioni 0, consumo di materie ≤ 0): `None` con ragione. Test nei Task 3 e 4.
- Word e PDF dicono la stessa cosa (avviso, etichette DSCR): i due renderer condividono `page_texts()`/`cover_lines()`; un test sul `.docx` lo fissa. Test nei Task 1 e 6.
- Scenario infrannuale (report infrannuale, `engine_meta` sempre `NULL`): nessun avviso di versione, nessun cambiamento di comportamento oltre alle formule corrette. Test nel Task 1.

---

### Task 1: A01-bis — avviso di previsionale vecchio nel PDF, nel Word e su /report

**Files:**
- Modify: `backend/app/services/final_report_service.py` (~390, accanto alla diagnostica `forecast_stale`)
- Modify: `backend/app/renderers/business_plan/data.py` (`BusinessPlanData`, ~94; `from_report`, ~523)
- Modify: `backend/app/renderers/business_plan/document.py` (`page_texts()`, ~37-39) e `backend/app/renderers/business_plan/sections_sintesi.py` (`cover_lines()`, ~50-52)
- Modify: `frontend/app/report/page.tsx` (~166)
- Test: `tests/test_fix_rilievi_report.py` (nuovo), `tests/test_rilievi_ambienta.py` (togli marcatore A01-bis)

**Interfaces:**
- Produces: diagnostica `engine_version_stale` (severity `error`, sezione `forecast`) emessa quando uno scenario **budget** ha almeno un anno di piano con `engine_meta.engine_version` presente e `int(...) < int(ENGINE_VERSION)` (`calculations.forecast_engine.ENGINE_VERSION`); `engine_meta` `NULL` o senza versione ⇒ nessuna diagnostica («non lo so»); scenari infrannuali mai. `BusinessPlanData.avvisi: tuple[str, ...]` (vuota di default) = le frasi, nell'ordine: «Previsionale precedente alle ipotesi salvate: da rigenerare» (da `forecast_stale`) e «Previsionale generato da una versione precedente del motore: da rigenerare» (da `engine_version_stale`).

- [ ] **Step 1: test.** In `tests/test_fix_rilievi_report.py`: (a) il test A01-bis del triage senza marcatore; (b) sullo stesso scenario, il testo del `.docx` (`render_business_plan_docx`, leggi il file con `python-docx`) contiene «Previsionale precedente alle ipotesi salvate: da rigenerare»; (c) un previsionale generato e poi con `engine_meta = {"engine_version": "1", "pareggio": None}` scritto a mano su un `ForecastYear` (nella sessione in memoria, prima di `assemble_final_report` — estendi `rilievi_kit.genera` con un parametro `ritocca=callable(db, scenario_id)` chiamato dopo la generazione) → diagnostica `engine_version_stale` e frase nel PDF; (d) `engine_meta = None` → nessuna diagnostica `engine_version_stale`; (e) un report senza diagnostiche → `avvisi == ()` e il PDF non contiene «da rigenerare».
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** implementa. L'avviso sta in copertina (una riga sotto il titolo) e nell'intestazione di ogni pagina accanto a «BOZZA», in PDF e Word (condividono le due funzioni). Su `/report`, l'`Alert` esistente per `forecast_stale` riconosce anche `engine_version_stale`, con il testo della spec e lo stesso pulsante «Rigenera previsionale». Lo scarico in bozza non si blocca (lo è già).
- [ ] **Step 4:** PASS; `npx tsc --noEmit`, `npm run build`, `npx vitest run`; suite gate.
- [ ] **Step 5: commit** `fix(report): A01-bis avviso di previsionale vecchio in PDF, Word e /report`.

---

### Task 2: A02 — il BEP degli anni di piano viene dal motore

**Files:**
- Modify: `backend/app/services/final_report_service.py` (`by_forecast_year` ~510, costruzione di `DossierSource` ~552-558), `backend/app/services/final_report_dossier.py` (`build_structure_series`, blocco pareggio ~179-307)
- Test: `tests/test_fix_rilievi_report.py`, `tests/test_final_report_v2.py` (~364-392), `tests/test_rilievi_ambienta.py` (togli marcatore A02)

**Interfaces:**
- Consumes: `ForecastYear.engine_meta["pareggio"]` = `{costi_variabili, costi_fissi, costi_fissi_operativi, margine_contribuzione_pct, fatturato_pareggio, margine_sicurezza, margine_sicurezza_pct}` (stringhe al centesimo o `None`).
- Produces: `DossierSource.pareggio_motore: dict | None` (nuovo campo, `None` di default).

Regole (spec §3 A02): per un anno `basis == 'forecast'` il gruppo `break_even` usa `pareggio_motore`: `variable_costs` ← `costi_variabili`, `fixed_costs` ← `costi_fissi_operativi`, `break_even_revenue` ← `fatturato_pareggio`, margine di contribuzione e di sicurezza dalle chiavi omonime (leggi il mapping `_BE` in `backend/app/renderers/business_plan/data.py:192-196` e le chiavi che la serie espone oggi, e riempi le stesse). Anno di piano **senza** `pareggio_motore` (o con `pareggio` `None`, o valori `None` perché ce05/ce06 sono sotto override): serie `None` con ragione `engine_meta_missing` (niente `pareggio` persistito) o `pareggio_non_definito` (motore ha dichiarato `None`), **mai** la ripartizione 60/40. La colonna base/storica resta come oggi (`calculate_break_even_analysis` con `DEFAULT_FIXED_SHARE`).

- [ ] **Step 1: test.** (a) A02 del triage senza marcatore; (b) anno di piano con `engine_meta` `NULL` (via `ritocca` del Task 1) → `data.v("bep")` di quell'anno `None`, e la serie dichiara `engine_meta_missing`; (c) colonna base invariata rispetto a oggi (fissa il numero misurato prima del cambio). Riscrivi `test_break_even_reuses_the_analyst_formula_with_the_assumption_fixed_splits` e `test_forecast_year_without_assumptions_declares_break_even_as_null_not_zero` (`tests/test_final_report_v2.py`) sulla regola nuova: il primo diventa un test che con `pareggio_motore` la serie riporta i valori del motore; il secondo che senza `pareggio_motore` è `None` con `engine_meta_missing`.
- [ ] **Step 2:** FAIL. **Step 3:** implementa (`final_report_service` passa `fy.engine_meta.get("pareggio")` di ogni anno di piano). **Step 4:** PASS + suite gate. **Step 5: commit** `fix(report): A02 punto di pareggio degli anni di piano dal motore`.

---

### Task 3: C02, C03, C04, C06, C07 — formule degli indici alla fonte

**Files:**
- Modify: `calculations/report_indicators.py` (`financial_debt_total` ~56-71, PFN ~87-88, `copertura_immob` ~106), `calculations/ratios.py` (ROD ~259-263, leverage ~207-211, DSO ~318-322, DIO ~311-315, `calculate_coverage_ratios` ~363-394), `database/models.py` solo se serve riusare `BalanceSheet.financial_debt_total`
- Modify: `frontend/lib/budget-piano-step.ts` (~161-163) solo per importare/allineare la stessa definizione se diverge
- Test: `tests/test_fix_rilievi_report.py`, `tests/test_rilievi_ambienta.py` (togli marcatori C02, C03, C04, C06, C07)

**Interfaces:**
- Produces: una sola funzione del perimetro di debito finanziario, `report_indicators.financial_debt_total(field_value) -> Decimal` = somma **incondizionata** di `sp16a, sp17a, sp16b, sp17b, sp16c, sp17c` (banche + altri finanziatori + obbligazioni, breve e lungo) — la stessa di `BalanceSheet.financial_debt_total` e di `finDebt` in `budget-piano-step.ts`; il ramo «bank>0 else fallback» sparisce. `ratios.py` la usa per il ROD.

Regole (spec §3):
- **C02** DSO = `(sp06a + sp07a) / ricavi × 360`; DIO = `rimanenze / (ce05 + ce10) × 360` (consumo di materie, coerente col motore del lotto 1), `None` con consumo ≤ 0; DPO invariato. La formula testuale in `report_indicators.py` (~170, «360 × crediti entro e oltre 12 mesi / ricavi») si aggiorna.
- **C03** ROD = `ce15 / financial_debt_total × 100`; lo `spread` (`roi − rod`) segue da solo.
- **C04** PFN = `financial_debt_total − sp09 − sp08` (come oggi per cassa e attività finanziarie, perimetro di debito nuovo).
- **C06** «Indice di indebitamento» = `(sp16 + sp17) / PN`.
- **C07** copertura immobilizzazioni = `(PN + sp17 + sp15) / immobilizzazioni × 100`, sia in `report_indicators` (`copertura_immob`, Sez. 8 e Allegato D) sia in `ratios.calculate_coverage_ratios` (analitico).
- Ogni denominatore zero ⇒ `None` (usa `safe_divide`, già così).

- [ ] **Step 1: test.** I cinque oracoli del triage senza marcatore; test unitari su `financial_debt_total` (altri finanziatori dentro anche con banche > 0; nessun fornitore/tributario dentro), su DIO con consumo ≤ 0 → `None`, su C06/C07 con PN o immobilizzazioni 0 → `None`.
- [ ] **Step 2:** FAIL. **Step 3:** implementa; aggiorna i testi di formula che il catalogo mostra (grep delle vecchie frasi in `calculations/`, `backend/app/renderers/`, `contracts/`). **Step 4:** PASS + suite gate; classifica le rotture (attese: test che fissano i vecchi valori di questi indici, anche nel report infrannuale e nella pagina Indici). **Step 5: commit** `fix(indici): C02 C03 C04 C06 C07 una definizione per indice`.

---

### Task 4: C05 — un solo current ratio, quick ratio e CCN simmetrici sui ratei

**Files:**
- Modify: `calculations/report_indicators.py` (~83-86, 101-104), `calculations/ratios.py` (`calculate_liquidity_ratios` ~150-190, CCN di `WorkingCapitalMetrics` ~127)
- Test: `tests/test_fix_rilievi_report.py`, `tests/test_rilievi_ambienta.py` (togli marcatore C05)

**Interfaces:**
- Produces: `report_indicators.attivo_corrente(field_value) -> Decimal` = `sp05 + sp06 + sp08 + sp09 + sp10` (rimanenze + crediti a breve + attività finanziarie a breve + liquidità + ratei attivi; **niente `sp07`**), `report_indicators.passivo_corrente(field_value) -> Decimal` = `sp16 + sp18` (debiti a breve + ratei passivi). Current ratio = attivo/passivo; quick = (attivo − sp05)/passivo; CCN = attivo − passivo. `ratios.py` le chiama per `liquidity.current_ratio`, il quick e il `ccn` di `WorkingCapitalMetrics`. **Non** toccare le proprietà `BalanceSheet.current_assets`/`working_capital_net` (le usano Altman e FGPMI, che restano come sono).

- [ ] **Step 1: test.** Oracolo C05 senza marcatore (Sez. 8 = Allegato E «Current Ratio (ILC)»); test unitario delle due funzioni su un foglio con `sp07`, `sp10`, `sp18` non nulli (sp07 fuori, ratei su entrambi i lati); passivo corrente 0 → `None`.
- [ ] **Step 2:** FAIL. **Step 3:** implementa; testi di formula aggiornati. **Step 4:** PASS + suite gate; classifica (attesi: test su current ratio/CCN del report e della pagina Indici; Altman/FGPMI **non** devono muoversi — se si muovono, fermati). **Step 5: commit** `fix(indici): C05 un solo current ratio, ratei su entrambi i lati`.

---

### Task 5: C08 — erogazioni e rimborsi su righe separate

**Files:**
- Modify: `calculations/forecast_engine.py` (`engine_meta()` ~32-38 e la sua chiamata ~2840; raccolta delle erogazioni da `details`)
- Modify: `backend/app/calculations/cashflow_detailed.py` (~440-448) e il suo chiamante in `backend/app/services/analysis_service.py` (`_calculate_cashflow`, ~353) per passargli le erogazioni dell'anno
- Modify: `backend/app/renderers/business_plan/narrative.py` (la sintesi cita i rimborsi di ogni anno di piano)
- Test: `tests/test_fix_rilievi_report.py`, `tests/test_engine_meta.py`, `tests/test_rilievi_ambienta.py` (togli marcatore C08), riverifica `tests/test_cashflow_debito_finanziario.py`, `tests/test_cashflow_dividendi.py`, `tests/test_cashflow_svalutazione_crediti.py`

**Interfaces:**
- Produces: `engine_meta(details)` aggiunge `"erogazioni": str` (al centesimo) = somma, per l'anno, di: `erogato` dei contratti di `details['debito_bancario']['contratti']`, `erogato` dei contratti degli altri finanziatori (oggi il motore lo scarta — `new_financing_schedule([c], anno)[0]` ~4489-4496: tienilo e dichiaralo come `erogato` per contratto in `details['altri_finanziatori']['contratti']`), tiraggio dei fidi dell'anno (`details['debito_bancario']['fidi']`, leggi la chiave esatta) e scoperto generato nell'anno (`details['scoperto_generato']` o chiave equivalente). `ENGINE_VERSION` resta `"2"` (nessun numero di SP/CE cambia). `DetailedCashFlowCalculator` riceve `erogazioni: Decimal | None` per l'anno.

Regole (spec §3 C08): con `erogazioni` noto, `third_party_funds.increases = erogazioni`, `decreases = erogazioni − Δ debito finanziario` (Δ misurato come oggi, sul perimetro `financial_debt_total`), `net` invariato (= Δ). Se `decreases` risultasse negativo (dato incoerente), non si inventa nulla: `increases = max(Δ, 0)`, `decreases = max(−Δ, 0)` come oggi, e si dichiara (una diagnostica del rendiconto, nome a tua scelta nello stile del file). Senza `erogazioni` (anno storico, o `engine_meta` `NULL`/senza chiave): comportamento di oggi. L'invariante dei test esistenti «residuo dei mezzi di terzi = variazione misurata del debito finanziario» resta vera (il `net` non cambia).

- [ ] **Step 1: test.** Oracolo C08 senza marcatore (280.000 e ≥ 53.409 nel 2027); `engine_meta` dell'anno 2027 dello stesso scenario ha `erogazioni == "280000.00"`; anno con `engine_meta` `NULL` → rendiconto come oggi (netto su una sola riga); la sintesi (`narrative.key_points`) cita i rimborsi 2027 formattati. I tre file di test del rendiconto verdi.
- [ ] **Step 2:** FAIL. **Step 3:** implementa. **Step 4:** PASS + suite gate. **Step 5: commit** `fix(rendiconto): C08 erogazioni e rimborsi su righe separate`.

---

### Task 6: C01 — il DSCR vero, e il proxy sparisce

**Files:**
- Modify: `calculations/report_indicators.py` (~99, `dscr`), `backend/app/services/final_report_dossier.py` (~109 `build_indicator_catalog` passa il rendiconto; ~131 via l'etichetta «DSCR — proxy della pratica»)
- Modify: `backend/app/renderers/business_plan/charts.py` (~284), `sections_finanza.py` (~18, 21, 36, 41-42), `narrative.py` (~127-136, 200-212), `sections_sintesi.py` (~118, 130-131, 174); `backend/app/renderers/typst/dossier_catalog/indicatori.py` (~136, 300-306)
- Test: `tests/test_fix_rilievi_report.py`, `tests/test_dossier_catalog_indicatori.py` (~176-190), `tests/test_rilievi_ambienta.py` (togli marcatore C01)

**Interfaces:**
- Consumes: il rendiconto del Task 5 (`financing.third_party_funds.decreases` dell'anno = quota capitale rimborsata).
- Produces: `practice.dscr` = `(MOL − imposte) / (oneri finanziari + rimborsi dell'anno)`; rimborsi assenti (rendiconto non disponibile) ⇒ `None` con ragione, mai il vecchio proxy.

Regole (spec §3 C01): un solo indicatore, «DSCR». Ogni «(proxy)», «— proxy della pratica», «calcolato come proxy» sparisce da tabelle, grafici, testi (PDF, Word, dossier Typst) e il sottotitolo della Sez. finanza spiega la formula vera in una riga. Le soglie di `narrative.SOGLIE` (1,25 / 1 / 2) restano, i testi della sintesi e dei rilievi si riscrivono sul DSCR vero. `calculations/crisi_impresa.py` (indicatori della crisi) **non si tocca**. `data.partial_dscr` (DSCR del progressivo infrannuale, `sections_finanza.py:41-42`): se non ha una quota capitale, la riga dice «DSCR» senza «proxy» solo se la formula è quella vera; altrimenti la riga sparisce — scegli leggendo come è calcolato e scrivilo nel rapporto.

- [ ] **Step 1: test.** Oracolo C01 senza marcatore; nessuna occorrenza di «proxy» nel testo del PDF e del Word del Business plan dello scenario C01 (`fitz` e `python-docx`); riscrivi `test_solidita_table_row_spec_leaves_the_dscr_label_to_the_catalog` sulla regola (etichetta «DSCR»).
- [ ] **Step 2:** FAIL. **Step 3:** implementa. **Step 4:** PASS + suite gate (`grep -rn "proxy" backend/app/renderers calculations/report_indicators.py backend/app/services/final_report_dossier.py` → nessuna occorrenza riferita al DSCR). **Step 5: commit** `fix(report): C01 DSCR con la quota capitale, via il proxy`.

---

### Task 7: C09 — oneri finanziari/MOL dalla colonna base

**Files:**
- Modify: `backend/app/renderers/business_plan/narrative.py` (`key_points`, ~128-134)
- Test: `tests/test_rilievi_ambienta.py` (togli marcatore C09), `tests/test_fix_rilievi_report.py`

Regola: la frase «gli oneri finanziari passano dal X% al Y% del MOL» parte dal valore della colonna base (`data.v("of_mol")[0]`) e arriva all'ultimo anno di piano; se la base è `None`, parte dal primo anno di piano come oggi (e il test lo fissa).

- [ ] **Step 1: test** (oracolo + base `None`). **Step 2:** FAIL. **Step 3:** implementa. **Step 4:** PASS. **Step 5: commit** `fix(report): C09 oneri su MOL dalla colonna base`.

---

### Task 8: documentazione e verdetto

**Files:** `CLAUDE.md`, `docs/budget/BUSINESS-PLAN-PDF.md`, `tools/triage_rilievi.py` (`LETTURE`), `docs/superpowers/allineamento/2026-09-25-triage-rilievi-ambienta.md` (sezione «Lotto 2»).

- [ ] **Step 1:** un bullet per regola che cambia numeri letti dall'utente (DSO, DIO, ROD, PFN, current/quick/CCN, indebitamento, copertura, DSCR, rendiconto erogazioni/rimborsi, BEP dal motore, avviso di versione), con che cosa cambia sugli scenari esistenti (anche storici: la pagina Indici legge le stesse formule). `engine_meta.erogazioni` e la regola `NULL` = «non lo so».
- [ ] **Step 2:** `LETTURE` A01, A02, C01–C09 «Risolto nel lotto 2 fix, 2026-09-26»; sezione nel rapporto col conteggio del banco (`pytest tests/test_rilievi_ambienta.py -q`: nessun `xfail` rimasto).
- [ ] **Step 3:** suite gate, `npx vitest run`, `npx tsc --noEmit`, `tests/test_triage_rilievi_tool.py`.
- [ ] **Step 4: commit** `docs(rilievi): lotto 2 — indici con una definizione, report aggiornato, verdetto`.
