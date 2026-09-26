# Fix rilievi AMBIENTA · Lotto 3 (wizard) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chiudere A05 («Manuale» parte dal saldo dell'anno base) e A06 (una sola tendina per i previdenziali, niente casella) nel wizard del previsionale.

**Architecture:** A05 cambia solo il valore che il passaggio a «Manuale» scrive in `sp_overrides` (funzione pura `withSpRule` in `frontend/lib/budget-sp-manuale.ts` + il chiamante in `StepPatrimonialePiano.tsx`). A06 toglie la casella, fa smettere il motore di leggere `previdenza_scales_with_personnel` e porta gli scenari salvati sulla tendina con uno script una tantum.

**Tech Stack:** Next.js 15 + TypeScript (Vitest, `environment: node`), Python 3 + SQLAlchemy, pytest.

**Spec:** `docs/superpowers/specs/2026-09-26-fix-rilievi-ambienta-design.md` (§3 Lotto 3, §4 Verifica).

## Global Constraints

- Worktree `/home/peter/DEV/budget-fix-rilievi-l3`, branch `fix/rilievi-lotto3` (da `fix/rilievi-ambienta`). Mai scrivere in `/home/peter/DEV/budget` né in `/home/peter/DEV/budget-fix-rilievi`. Niente push.
- Python: `../budget/backend/venv/bin/python -m pytest …` dalla radice del worktree. Frontend: `cd frontend && npx vitest run <file>`, `npx tsc --noEmit`, `npm run build` quando si tocca un `.tsx` (se il build crea una directory spuria `frontend/budget/…`, cancellala, mai in stage).
- Suite intera (gate): `S=/tmp/claude-1000/-home-peter-DEV-budget/c84cb587-b7a2-4376-a794-7618627d4d71/scratchpad; cp /home/peter/DEV/budget/financial_analysis.db $S/real_migrated_l3.db && ../budget/backend/venv/bin/python migrate_db.py $S/real_migrated_l3.db >/dev/null && BUDGET_REAL_DB=$S/real_migrated_l3.db ../budget/backend/venv/bin/python -m pytest tests -q -p no:warnings > $S/suite_l3.txt 2>&1; tail -15 $S/suite_l3.txt` — attesi solo i 6 fallimenti preesistenti (test_bp_data::test_from_report_infrannuale_ambienta, test_editorial_notes_service::test_automatic_prose_definition_changes_invalidate_fit_signature_and_require_worker_reload, test_inf_data::test_ambienta_coincide_col_riferimento, test_inf_document::test_ambienta_cifre_del_riferimento, test_inf_rilievi::test_arrotondamenti_come_la_tabella, test_vision_rescue::test_build_ce_non_manda_un_ricavo_sconosciuto_su_una_voce_di_costo).
- Il DB vivo non si scrive mai; lo script di migrazione si prova su una copia.
- `lib/budget-*` è puro: nessun import da `app/` o `components/`.
- Un test esistente che fissa il comportamento che la spec cambia si riscrive sulla decisione nello stesso commit, dicendolo (commento `// lotto 3 fix rilievi (2026-09-26): <regola>` o `#`), ed è elencato nel messaggio di commit. Qualunque altra rottura: fermati e segnala.
- File con fine riga misti: modifiche additive, `git diff --stat` prima di ogni commit.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Testi in italiano, «tu» nei testi a schermo se servono.

## Review Focus

- Voce con saldo di base nullo o assente passata a «Manuale»: scrive 0 (non `null`, non il calcolo), l'anteprima mostra 0. Test nel Task 1.
- Passaggio Manuale → driver → Manuale: il secondo Manuale riparte dal saldo di base, non dai valori di prima. Test nel Task 1.
- Scenario salvato con casella accesa **e** una tendina diversa su `sp16f`: la migrazione fa vincere la casella (era lei a governare), e lo dichiara. Test nel Task 2.
- Scenario con casella accesa e piano pregresso `debiti_previdenziali`: dopo la migrazione il motore ignora l'indicizzazione come prima ignorava la casella? Il test lo misura e fissa i numeri prima/dopo. Test nel Task 2.
- Client vecchio che manda ancora `previdenza_scales_with_personnel: true`: nessun effetto sul motore, nessun errore. Test nel Task 2.

---

### Task 1: A05 — «Manuale» scrive il saldo dell'anno base, costante

**Files:**
- Modify: `frontend/lib/budget-sp-manuale.ts` (`withSpRule`)
- Modify: `frontend/components/budget/wizard/steps/StepPatrimonialePiano.tsx` (~106, chiamata a `p.updateSpRule`)
- Modify: `frontend/hooks/use-scenario-assumptions.ts` (~370, `updateSpRule`), `frontend/components/budget/wizard/types.ts` (~31) se cambia la firma
- Test: `frontend/lib/budget-sp-manuale.test.ts` (riscrivi «scegliere Manuale congela i valori dell'anteprima per anno»), `frontend/lib/rilievi-ambienta.test.ts` (riscrivi il test A05 di caratterizzazione)

**Interfaces:**
- Produces: `withSpRule(assumptions, years, code, field, growthField, driver: SpIndexingDriver | null, baseAmount: number | null): AssumptionsMap` — con `driver === null` scrive `sp_overrides[field] = baseAmount ?? 0` in **ogni** anno; con un driver toglie l'override come oggi. Il parametro `projected` sparisce da `withSpRule` (resta in `withManualSpAmount`, che non cambia). `updateSpRule(code, field, growthField, driver, baseAmount: number | null)`.

- [ ] **Step 1: test.** In `budget-sp-manuale.test.ts` sostituisci l'ultimo test con:

```ts
  // lotto 3 fix rilievi (2026-09-26): «Manuale» parte dal saldo dell'anno base, costante (decisione del proprietario, A05).
  it("scegliere Manuale scrive il saldo dell'anno base in ogni anno", () => {
    const rows: AssumptionsMap = { 2027: { sp_indexing: { sp04: "ricavi" } }, 2028: { sp_indexing: { sp04: "ricavi" } } };
    const next = withSpRule(rows, years, "sp04", field, growth, null, 52550);
    expect(next[2027].sp_indexing).toBeNull();
    expect(next[2027].sp_overrides?.[field]).toBe(52550);
    expect(next[2028].sp_overrides?.[field]).toBe(52550);
  });

  it("Manuale su una voce senza saldo di base scrive zero", () => {
    const next = withSpRule({ 2027: {}, 2028: {} }, years, "sp04", field, growth, null, null);
    expect(next[2027].sp_overrides?.[field]).toBe(0);
    expect(next[2028].sp_overrides?.[field]).toBe(0);
  });

  it("Manuale dopo un driver riparte dal saldo di base, non dai valori di prima", () => {
    const rows: AssumptionsMap = { 2027: { sp_overrides: { [field]: 60000 } }, 2028: { sp_overrides: { [field]: 61000 } } };
    const conDriver = withSpRule(rows, years, "sp04", field, growth, "ricavi", null);
    const next = withSpRule(conDriver, years, "sp04", field, growth, null, 52550);
    expect([next[2027].sp_overrides?.[field], next[2028].sp_overrides?.[field]]).toEqual([52550, 52550]);
  });
```

e aggiorna la chiamata del test «scegliere un driver elimina importi…» (ultimo argomento `null` al posto di `{}`). In `rilievi-ambienta.test.ts` riscrivi il test A05 come oracolo della decisione: da «ricavi» a Manuale, `sp_overrides.sp04_immob_finanziarie` = 52.550 in 2027, 2028, 2029 (saldo 2026 di AMBIENTA), e aggiorna il commento di testa del blocco (non è più una caratterizzazione).

- [ ] **Step 2:** `cd frontend && npx vitest run lib/budget-sp-manuale.test.ts lib/rilievi-ambienta.test.ts` → FAIL.

- [ ] **Step 3:** implementa la firma nuova di `withSpRule`; nel componente passa il saldo di base della riga (`numOrNull((baseBs as unknown as Record<string, unknown>)?.[row.balanceField])`, lo stesso dato che mostra `row.baseLabel`) al posto di `projected`; aggiorna hook e tipo. Docstring di `withSpRule`: Manuale = saldo di base costante, decisione del proprietario 2026-09-26.

- [ ] **Step 4:** stessi test → PASS; `npx vitest run`, `npx tsc --noEmit`, `npm run build`.

- [ ] **Step 5: commit** `fix(wizard): A05 Manuale parte dal saldo dell'anno base`.

---

### Task 2: A06 — una sola tendina per i previdenziali

**Files:**
- Modify: `frontend/components/budget/wizard/steps/StepPatrimonialePiano.tsx` (casella ~80 e ~260)
- Modify: `frontend/lib/budget-circolante-step.ts` (`minorFieldsRows`, parametro `previdenzaSuPersonale`), `frontend/lib/budget-piano-step.ts` (`regoleVociMinori` ~308), `frontend/components/budget/assumption-rows.ts` (~121, riga della vista avanzata)
- Modify: `calculations/forecast_engine.py` (`_resolve_sp_indexing` ~1585-1604, blocco previdenza ~4338-4360)
- Create: `scripts/migra_previdenza_tendina.py`
- Modify: `scripts/sensibilita_ipotesi.py` (~392, ~412) se legge il flag come leva
- Test: `tests/test_migra_previdenza_tendina.py` (nuovo), `tests/test_rilievi_ambienta.py` (A06 resta verde), Vitest dei due lib toccati

**Interfaces:**
- Produces: `scripts.migra_previdenza_tendina.migra(db: Session, apply: bool) -> list[Modifica]` con `Modifica(scenario_id, nome, anno, indicizzazione_prima: dict | None, indicizzazione_dopo: dict)`; uso `python -m scripts.migra_previdenza_tendina [percorso.db] [--apply]` (prova per default), stesso stile di `scripts/migra_imposte_commercialista.py`.

Regole (spec §3 A06):
- Il motore **non legge più** `previdenza_scales_with_personnel`: sparisce il ramo `if getattr(assumption, 'previdenza_scales_with_personnel', False)` nel blocco previdenza (resta il ramo `_sp_scale`/indicizzazione) e il salto «governata dall'interruttore» in `_resolve_sp_indexing`. Il campo resta nel modello e negli schemi (compatibilità): un client vecchio che lo manda a `true` non cambia nulla.
- Migrazione: per ogni riga `BudgetAssumptions` con il flag `true`: `sp_indexing["sp16f"] = sp_indexing["sp17f"] = "personale"` (anche se c'era un altro driver: prima vinceva la casella; la modifica lo dichiara), flag → `false`. Idempotente.
- Frontend: niente casella; `minorFieldsRows` e `regoleVociMinori` non leggono più il flag (il driver di sp16f/sp17f viene dalla sola tendina); la riga della vista avanzata sul flag sparisce.
- Prima di togliere il ramo, **misura** su un test se `sp_indexing personale` dà gli stessi numeri del flag (stesso scenario, anche con piano pregresso `debiti_previdenziali`): se differiscono, fissa i numeri nuovi nel test, scrivilo nel rapporto e nel commit (è un cambiamento di numeri voluto da dichiarare in CLAUDE.md).

- [ ] **Step 1: test (Python).** `tests/test_migra_previdenza_tendina.py`:

```python
"""A06 · la casella dei previdenziali diventa la tendina (spec fix rilievi 2026-09-26 §3, lotto 3)."""
from decimal import Decimal as D

from database.models import BudgetAssumptions
from scripts.migra_previdenza_tendina import migra
from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, per_anno, righe
from tests.e2e_kit import memory_sessions


def test_il_motore_ignora_la_casella():
    rows = per_anno(righe(previdenza_scales_with_personnel=True), "personnel_growth_pct", (3, 4, 4))
    per_anno(rows, "revenue_growth_pct", (5, 6, 7))
    e = generato(genera(rows))
    assert e.anni[2027][0]["sp16f_debiti_previdenza_breve"] == BASE_BS["sp16f_debiti_previdenza_breve"]


def test_tendina_personale_da_gli_stessi_numeri_della_casella_di_prima():
    rows = per_anno(righe(sp_indexing={"sp16f": "personale", "sp17f": "personale"}), "personnel_growth_pct", (3, 4, 4))
    e = generato(genera(rows))
    b16, b08 = BASE_BS["sp16f_debiti_previdenza_breve"], BASE_CE["ce08_costi_personale"]
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        assert abs(sp["sp16f_debiti_previdenza_breve"] - b16 * ce["ce08_costi_personale"] / b08) < D("1"), y
```

più i test della migrazione su un DB in memoria (`memory_sessions`, schema creato dal kit): una riga col flag e `sp_indexing={"sp16f": "ricavi", "sp10": "ricavi"}` → dopo `migra(db, apply=True)` `{"sp16f": "personale", "sp17f": "personale", "sp10": "ricavi"}`, flag `False`, una `Modifica` con `indicizzazione_prima` dichiarata; `apply=False` non scrive nulla; seconda esecuzione → nessuna modifica. (Per creare le righe riusa il modo in cui `tests/rilievi_kit.genera` semina azienda, anno e scenario; `BudgetAssumptions` richiede `scenario_id`, `forecast_year` e i campi obbligatori del modello — leggi `database/models.py`.) Vitest: `minorFieldsRows(baseBs, { sp16f: "personale" })` mostra il driver `personale` su sp16f senza parametro del flag; `regoleVociMinori` con il solo flag a `true` e nessuna indicizzazione non dice più «segue il personale».

- [ ] **Step 2:** i test → FAIL (il primo, i test della migrazione per ImportError, i Vitest).

- [ ] **Step 3:** implementa: motore, script, frontend (casella via, firme dei due lib senza il flag, riga della vista avanzata via), `scripts/sensibilita_ipotesi.py` passa alla tendina se usava il flag come leva. Prova lo script su una copia del DB vivo in scratch (mai il DB vivo): riporta nel rapporto quante righe cambierebbe, in prova.

- [ ] **Step 4:** i test → PASS; il test A06 del triage resta verde; suite gate; `npx vitest run`, `npx tsc --noEmit`, `npm run build`.

- [ ] **Step 5:** CLAUDE.md, «Invarianti e trappole › Previsionale»: un bullet — la casella non esiste più, `previdenza_scales_with_personnel` è ignorato dal motore, gli scenari salvati vanno migrati una volta con `python -m scripts.migra_previdenza_tendina [db] --apply` (senza, uno scenario che aveva la casella accesa perde l'aggancio al personale). `docs/budget/FORECASTING_GUIDE.md` se descrive la casella. `tools/triage_rilievi.py` `LETTURE` per A05 e A06 («Risolto nel lotto 3 fix, 2026-09-26, su decisione del proprietario») e una sezione «Lotto 3» nel rapporto `docs/superpowers/allineamento/2026-09-25-triage-rilievi-ambienta.md`.

- [ ] **Step 6: commit** `fix(wizard): A06 una sola tendina per i previdenziali, migrazione della casella` (e un commit `docs` separato per lo Step 5 se preferisci).
