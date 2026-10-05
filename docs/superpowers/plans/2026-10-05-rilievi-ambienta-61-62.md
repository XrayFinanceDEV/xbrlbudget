# Rilievi AMBIENTA #61 #62 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chiudere le issue #61 e #62. Si correggono il motore budget (DSO, personale, riserva legale, rimanenze in
due gruppi, compensazione dei crediti tributari, avvisi), gli indici (ROD medio, leva, annualizzati
dell'infrannuale), il rendiconto (imposte pagate), il Business plan e il wizard.

**Architecture:** le regole numeriche stanno nel motore Python (`calculations/forecast_engine.py`,
`calculations/projection_common.py`) e ognuna si dichiara in `details`. Gli avvisi del motore viaggiano in un solo canale,
`details['avvisi']` (lista di frasi italiane), che `engine_meta` persiste: così li leggono sia il wizard (anteprima) sia
il Business plan. Il frontend non calcola nulla: legge `details` e `engine_meta`.

**Tech Stack:** Python 3 / SQLAlchemy / FastAPI / pytest (backend, `tests/`), Next.js 15 + TypeScript + Vitest (frontend).

**Spec:** `docs/superpowers/specs/2026-10-05-rilievi-ambienta-61-62-design.md` — leggerla prima di ogni task.

**Branch:** `fix/rilievi-ambienta-61-62`, da `main`. Prima di creare un worktree verificare lo SHA di partenza (memoria
«worktree-agenti-partono-da-main»).

**Comandi:**
- Backend, un file: `cd /home/peter/DEV/budget && PYTHONPATH=.:backend backend/venv/bin/python -m pytest tests/<file>.py -q -p no:cacheprovider`
- Backend, suite intera: `cd /home/peter/DEV/budget && PYTHONPATH=.:backend backend/venv/bin/python -m pytest tests -q -p no:cacheprovider -p no:warnings`
- Frontend: `cd /home/peter/DEV/budget/frontend && npx vitest run <file>`; suite `npm test`; prima del push `npx next build`
- Banco di parità: `backend/venv/bin/python scripts/parita_motore.py main HEAD --json <scratch>/parita.json`

## Global Constraints

- Money is `Decimal`, never `float`. Percentuali assolute (25,5 = 25,5%).
- Testi in italiano, nessuna emoji, icone lucide-react. Si usa il «tu».
- `ENGINE_VERSION` sale a `"3"` (Task 1), una volta sola per tutto il lotto.
- Ogni nuova regola del motore si dichiara in `details`, e la chiave c'è sempre, anche a `None`/zero: una chiave assente vale «tutto regolare», e quindi mente.
- Gli avvisi non toccano i numeri. Vanno in `details['avvisi']`, una lista di stringhe, e da lì in `engine_meta['avvisi']`.
- Una colonna nuova di `BudgetAssumptions` tocca sempre gli stessi punti: `database/models.py`, `migrate_db.py`,
  `backend/app/schemas/budget.py` (Base e Update), `assumptions_service.build_assumption_row`,
  `contracts/final_report_assumption_sections.json` (oppure `DEAD_FIELDS`), `final_report_assumptions.FIELD_LABELS`,
  `frontend/types/api.ts` (due interfacce), `frontend/lib/budget-field-rules.ts`, `frontend/lib/budget-horizon.ts`
  (tipo, copia, default), `frontend/lib/budget-wizard-steps.ts`, `frontend/app/budget/page.tsx` (default),
  `scripts/parita_motore.py` se il banco deve variarla. I test di parità del contratto
  (`tests/test_m1_05b_assumption_sections.py`, `tests/test_final_report_contract.py`,
  `frontend/lib/final-report-contract.test.ts`, `frontend/lib/budget-horizon.test.ts`) dicono se ne manca uno.
- Il DB locale si migra a mano dopo ogni colonna nuova: `backend/venv/bin/python migrate_db.py financial_analysis.db`.
- Gli elenchi congelati di `ivcee-catalog-parity.test.ts` non si toccano.
- Commit piccoli, uno per task, con le righe di attribuzione richieste dalla sessione.

## Review Focus

1. **Uno scenario senza dettaglio dei crediti** (`sp06a` = 0 e `sp06` commerciale > 0, il 98% degli import abbreviati): il DSO sui soli clienti non deve azzerare i crediti né trasformarli in «altri». Si ripiega sull'aggregato, come fa `_alloc` con `primary_idx=0`. Il test sta nel Task 4.
2. **Rimanenze senza dettaglio** (`sp05` > 0 e sotto-voci a zero): i due gruppi non devono perdere né raddoppiare la massa. Il ripiego va sul gruppo 1, come il `_materie_base` di oggi. Il test sta nel Task 5.
3. **Casella «Compensa» accesa senza credito storico, o con imposte a zero**: nessuna compensazione, nessun negativo, e cassa e debito identici a casella spenta. Il test sta nel Task 8.
4. **Prima colonna del ROD** (nessun bilancio precedente): resta sul saldo di fine anno, senza `None` e senza errore. Il test sta nel Task 11.
5. **Perdita nell'anno prima**: la riserva legale non si muove e `sp12g` assorbe la perdita come oggi. Il test sta nel Task 2.

---

### Task 1: `ENGINE_VERSION` 3, canale degli avvisi, `engine_meta` NULL = da rigenerare

**Files:**
- Modify: `calculations/forecast_engine.py:29` (versione), `:97-104` (`engine_meta`), e `compute_forecast`, dove si scrivono `cassa_sotto_minimo`/`avviso_fidi` (~2748-2808)
- Modify: `backend/app/services/final_report_service.py:60-75` (`_engine_version_stale`)
- Modify: `frontend/types/api.ts` (`ForecastYearDetails`: `avvisi?: string[]`)
- Modify: `CLAUDE.md` (bullet «`ForecastYear.engine_meta` è `NULL`…», A01-bis, e la sezione «Forecasting Engine», dove dice `"2"`)
- Test: `tests/test_engine_meta.py`, `tests/test_fix_rilievi_report.py:96-130`

**Interfaces:**
- Produce: `details['avvisi']: list[str]`, sempre presente (anche vuota) in ogni anno; `engine_meta(details)['avvisi']`, una lista; `ENGINE_VERSION == "3"`. I Task 5, 7, 9 vi aggiungono le loro frasi con `details.setdefault('avvisi', []).append(frase)`, oppure scrivono nella lista già inizializzata.

- [ ] **Step 1: test che falliscono**

In `tests/test_engine_meta.py`:
```python
def test_engine_meta_porta_gli_avvisi_e_la_versione_3():
    from calculations.forecast_engine import ENGINE_VERSION, engine_meta
    assert ENGINE_VERSION == "3"
    meta = engine_meta({'avvisi': ['uno', 'due']})
    assert meta['avvisi'] == ['uno', 'due']
    assert engine_meta({})['avvisi'] == []
```
Aggiorna `assert meta["engine_version"] == ENGINE_VERSION == "2"` (riga 76) a `"3"`, e nello stesso file aggiungi un test
end-to-end: ogni anno generato (`tests.rilievi_kit.genera(righe())`) ha `e.det[y]['avvisi'] == []` e `e.meta[y]['avvisi'] == []`.

In `tests/test_fix_rilievi_report.py` sostituisci `test_d_engine_meta_none_nessuna_diagnostica` con:
```python
def test_d_engine_meta_none_su_budget_e_da_rigenerare():
    from backend.app.services.final_report_service import _engine_version_stale
    class FY:  # riga senza firma, come i previsionali generati prima del 2026-09-26
        engine_meta = None
    assert _engine_version_stale("bilancio", [FY()]) is True
    assert _engine_version_stale("infrannuale", [FY()]) is False
    class FY2:
        engine_meta = {"pareggio": None}  # senza engine_version
    assert _engine_version_stale("bilancio", [FY2()]) is True
```
Controlla gli altri test di quel file che leggono `_engine_version_stale` con righe dict (riga 130): devono continuare a passare.

- [ ] **Step 2: verifica che falliscano**

Run: `PYTHONPATH=.:backend backend/venv/bin/python -m pytest tests/test_engine_meta.py tests/test_fix_rilievi_report.py -q -p no:cacheprovider`
Expected: FAIL (`ENGINE_VERSION == "2"`, `KeyError 'avvisi'`, `stale is False`).

- [ ] **Step 3: implementazione**

`forecast_engine.py:29`: `ENGINE_VERSION = "3"`. In `engine_meta`, aggiungi alla dict restituita:
```python
'avvisi': [str(a) for a in (details.get('avvisi') or [])],
```
In `compute_forecast`, all'inizio del giro di ogni anno, dove si crea il `details` dell'anno (cerca dove si inizializza
`details = {}` per l'anno), aggiungi `details['avvisi'] = []`: tutti i task successivi vi aggiungono le loro frasi.
In `final_report_service._engine_version_stale`:
```python
    for row in forecast_years:
        meta = row.get("engine_meta") if isinstance(row, dict) else getattr(row, "engine_meta", None)
        version = (meta or {}).get("engine_version")
        if version is None:
            # Decisione del proprietario 2026-10-05 (#61): i dati vecchi non contano. Un previsionale budget senza
            # firma e' di sicuro anteriore al 2026-09-26, quindi va rigenerato.
            return True
        try:
            if int(version) < int(ENGINE_VERSION):
                return True
        except (TypeError, ValueError):
            continue
    return False
```
Prima di cambiare, verifica come il test della riga 130 passa le righe, se `dict` o oggetto, e mantieni il supporto a
entrambe. In `frontend/types/api.ts`, `ForecastYearDetails`, aggiungi `avvisi?: string[];`.
CLAUDE.md: riscrivi il bullet «`ForecastYear.engine_meta` è `NULL`…» così: su uno scenario budget NULL vale «da
rigenerare», per decisione del proprietario del 2026-10-05, perché i dati vecchi non contano; sull'infrannuale non c'è
alcun avviso. Riscrivi in modo coerente anche A01-bis («`engine_meta` `NULL` o senza `engine_version` = nessun
avviso»), e porta a `"3"` la frase su `ENGINE_VERSION` nella sezione Forecasting Engine.

- [ ] **Step 4: verifica che passino**, con lo stesso comando dello Step 2. Expected: PASS.

- [ ] **Step 5: commit** — `feat(motore): versione 3, canale details['avvisi'], engine_meta NULL da rigenerare (#61)`

---

### Task 2: M3 — riserva legale (art. 2430 c.c.)

**Files:**
- Modify: `calculations/forecast_engine.py:3998-4013` (blocco PN in `_calculate_balance_sheet`), più il punto in cui si scrive `details`
- Test: `tests/test_rilievi_61_62_motore.py` (nuovo)

**Interfaces:**
- Produce: `details['riserva_legale'] = {'utile': D, 'quota': D, 'tetto': D, 'raggiunto': bool}`, sempre presente.

- [ ] **Step 1: test che falliscono**, in `tests/test_rilievi_61_62_motore.py`:
```python
from decimal import Decimal as D
from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, righe

def _q(x): return D(str(x)).quantize(D("0.01"))

def test_M3_cinque_per_cento_dell_utile_a_riserva_legale():
    e = generato(genera(righe()))
    utile_base = BASE_BS["sp13_utile_perdita"]
    sp = e.anni[2027][0]
    attesa = min(utile_base * D("0.05"), D("0.20") * BASE_BS["sp11_capitale"] - BASE_BS["sp12c_riserva_legale"])
    assert _q(sp["sp12c_riserva_legale"]) == _q(BASE_BS["sp12c_riserva_legale"] + max(D(0), attesa))
    det = e.det[2027]["riserva_legale"]
    assert _q(det["quota"]) == _q(max(D(0), attesa))
    # il totale delle riserve non cambia: la quota esce da sp12g
    assert _q(sp["sp12_riserve"]) == _q(BASE_BS["sp12_riserve"] + utile_base)

def test_M3_tetto_al_venti_per_cento_del_capitale():
    e = generato(genera(righe(), bs={"sp12c_riserva_legale": D("21990.00")}))
    sp = e.anni[2027][0]
    assert _q(sp["sp12c_riserva_legale"]) <= D("22000.00")
    assert e.det[2027]["riserva_legale"]["raggiunto"] is True

def test_M3_perdita_non_accantona():
    e = generato(genera(righe(), bs={"sp13_utile_perdita": D("-5000.00")}))
    sp = e.anni[2027][0]
    assert _q(sp["sp12c_riserva_legale"]) == _q(BASE_BS["sp12c_riserva_legale"])
    assert _q(e.det[2027]["riserva_legale"]["quota"]) == D("0.00")
```
Se l'override `bs` su `sp13`/`sp12c` sbilancia la base, compensa sulla stessa colonna di PN, per esempio
`sp12g_utili_perdite_portati`, perché `genera` semina la base così com'è. Controlla prima che `genera` accetti una base
squilibrata: se la rifiuta, aggiusta `sp12_riserve`/`sp12g` di conseguenza.

- [ ] **Step 2: verifica che falliscano.** Expected: FAIL (`sp12c` costante, `KeyError 'riserva_legale'`).

- [ ] **Step 3: implementazione**, che sostituisce le righe 4006 e 4012:
```python
        # Riserva legale (art. 2430 c.c., decisione del proprietario 2026-10-05, #62 S29): il 5% dell'utile
        # dell'anno prima va a riserva legale finche' questa non raggiunge il 20% del capitale. Il movimento
        # resta dentro il PN (sp12c contro sp12g): totale e cassa non cambiano. Una perdita non accantona.
        sp12c_prev = _prev('sp12c_riserva_legale')
        tetto_legale = sp11 * D('0.20')
        quota_legale = ZERO
        if previous_profit > ZERO:
            quota_legale = min(previous_profit * D('0.05'), max(ZERO, tetto_legale - sp12c_prev))
        sp12c = sp12c_prev + quota_legale
        ...
        sp12g = _prev('sp12g_utili_perdite_portati') + previous_profit - quota_legale
        if details is not None:
            details['riserva_legale'] = {
                'utile': previous_profit, 'quota': quota_legale, 'tetto': tetto_legale,
                'raggiunto': sp12c >= tetto_legale,
            }
```
Al primo anno `_prev` legge `previous_bs`, che è la base: verificalo nel codice (`_prev` alla riga 3657). Controlla
anche che nessun override di `sp12c` passi da `_apply_sp_overrides` senza `_realign`: se `sp12c` è in `sp_overrides`,
l'override vince come ogni altra riga, e non serve altro.

- [ ] **Step 4: verifica che passino** il nuovo file e `tests/test_forecast_residuo_neutro.py` e `tests/test_engine_accounting_invariants.py`.

- [ ] **Step 5: commit** — `feat(motore): riserva legale al 5% fino al 20% del capitale (#62 S29)`

---

### Task 3: M2 — gli altri costi del personale crescono col personale

**Files:**
- Modify: `calculations/forecast_engine.py:3130-3177`
- Modify: `tests/test_fix_rilievi_motore.py:25-50` (i tre test B03 descrivono la regola vecchia)
- Test: `tests/test_rilievi_61_62_motore.py`

**Interfaces:**
- Produce: `details['personale'] = {'modo': 'componenti'|'aggregato'|'override', 'ce08_ipotesi': D, 'ce08': D, 'differenza': D, 'tfr_limitato': bool}`, sempre presente. `details['personale_ricomposto']` resta per il solo ramo `aggregato` (ricomposizione) e per il ramo `override`, con il significato di oggi; nel ramo `componenti` vale `None`.

- [ ] **Step 1: test che falliscono**
```python
def test_M2_ce08d_cresce_col_personale_e_il_totale_e_la_somma():
    rows = righe(personnel_growth_pct=4)
    e = generato(genera(rows))
    ce_base = BASE_CE
    for i, y in enumerate((2027, 2028, 2029), start=1):
        ce = e.anni[y][1]
        atteso_d = ce_base["ce08d_altri_costi_personale"] * D("1.04") ** i
        assert abs(ce["ce08d_altri_costi_personale"] - atteso_d) <= D("0.05")
        somma = sum(ce[k] for k in ("ce08a_tfr_accrual", "ce08b_salari_stipendi",
                                    "ce08c_oneri_sociali", "ce08d_altri_costi_personale"))
        assert _q(ce["ce08_costi_personale"]) == _q(somma)
        assert _q(ce["ce08a_tfr_accrual"]) == _q(ce["ce08b_salari_stipendi"] / D("13.5"))
    assert e.det[2027]["personale"]["modo"] == "componenti"

def test_M2_senza_dettaglio_resta_la_regola_aggregata():
    zero = {k: D("0") for k in ("ce08a_tfr_accrual", "ce08b_salari_stipendi",
                                 "ce08c_oneri_sociali", "ce08d_altri_costi_personale")}
    e = generato(genera(righe(personnel_growth_pct=4), ce=zero))
    assert e.det[2027]["personale"]["modo"] == "aggregato"
    assert _q(e.anni[2027][1]["ce08_costi_personale"]) >= _q(BASE_CE["ce08_costi_personale"] * D("1.04"))
```
Prima di scrivere il test controlla in `tests/fixtures/ambienta_2026.json` che `ce08d_altri_costi_personale` della base
sia positivo. Se è zero, semina un valore con `ce={...}` e ricalcola `ce08` come somma, perché la base deve restare
coerente. Riscrivi i tre test B03 di `test_fix_rilievi_motore.py` sulla regola nuova: il primo diventa «`ce08d` non va a
zero e `ce08` = somma», il secondo, con `ce08_override`, resta uguale, il terzo legge `details['personale']['modo']`.

- [ ] **Step 2: verifica che falliscano.**

- [ ] **Step 3: implementazione.** Nel blocco Personnel:
```python
        prev_ce08 = _pinc('ce08_costi_personale')
        prev_b, prev_c, prev_d = (_pinc('ce08b_salari_stipendi'), _pinc('ce08c_oneri_sociali'),
                                  _pinc('ce08d_altri_costi_personale'))
        crescita_pers = Decimal('1') + assumption.personnel_growth_pct / Decimal('100')
        personale_ricomposto = None
        if assumption.ce08_override is None and (prev_b + prev_c + prev_d) > 0:
            # #61 S06 (decisione del proprietario 2026-10-05): ogni componente monetaria cresce col personale,
            # il TFR e' quello di legge (B03) e il totale e' la loro somma. Il totale non e' piu'
            # «anno prima × crescita»: si dichiara di quanto se ne scosta.
            ce08b = assumption.ce08b_override if assumption.ce08b_override is not None else prev_b * crescita_pers
            ce08c = assumption.ce08c_override if assumption.ce08c_override is not None else prev_c * crescita_pers
            ce08d = assumption.ce08d_override if assumption.ce08d_override is not None else prev_d * crescita_pers
            ce08a = assumption.ce08a_override if assumption.ce08a_override is not None else tfr_accrual_quota(ce08b, prev_ce08 * crescita_pers)
            ce08_ipotesi = prev_ce08 * crescita_pers
            ce08 = ce08a + ce08b + ce08c + ce08d
            personale = {'modo': 'componenti', 'ce08_ipotesi': ce08_ipotesi, 'ce08': ce08,
                         'differenza': ce08 - ce08_ipotesi, 'tfr_limitato': False}
        else:
            # ramo di oggi, invariato (aggregato o ce08_override): righe 3131-3175
            ...
            personale = {'modo': 'override' if assumption.ce08_override is not None else 'aggregato',
                         'ce08_ipotesi': (personale_ricomposto or {}).get('ce08_ipotesi', ce08), 'ce08': ce08,
                         'differenza': ce08 - (personale_ricomposto or {}).get('ce08_ipotesi', ce08),
                         'tfr_limitato': bool((personale_ricomposto or {}).get('tfr_limitato'))}
        if details is not None:
            details['personale_ricomposto'] = personale_ricomposto
            details['personale'] = personale
```
Il calcolo di `ce08` alle righe 3131-3134 resta solo nel ramo `else`. Controlla che `ce08` non sia letto prima di
questo blocco: cerca `ce08` fra le righe 3000 e 3130.

- [ ] **Step 4: verifica che passino** il nuovo file e `tests/test_fix_rilievi_motore.py`.

- [ ] **Step 5: commit** — `feat(motore): altri costi del personale crescono col personale, ce08 = somma (#61 S06)`

---

### Task 4: M1 — il DSO governa i soli crediti verso clienti

**Files:**
- Modify: `calculations/forecast_engine.py:3860-3879` (DSO), `:3959-3985` (piano `crediti_commerciali`), `:4800-4853` (riparto `sp06`/`sp07`)
- Test: `tests/test_rilievi_61_62_motore.py`

**Interfaces:**
- Produce: `details['dso_clienti'] = {'target': D, 'sp07a': D, 'sp06a': D, 'scarto': D}`, sempre presente; `details['dso_applied']` diventa il DSO sui clienti.

Regole, dalla spec M1:
- Senza piano `crediti_commerciali`, `target = DSO × ricavi / 360`. `sp07a` è il lato oltre che il motore già calcola (riparto di `sp07` a crescita `receivables_long_growth_pct`), e `sp06a = max(0, target − sp07a)`, con `scarto = max(0, sp07a − target)`.
- `sp06b/c/d/g` = valore dell'anno prima (costanti: non esiste una `*_growth_pct` per queste righe).
- DSO derivato: `(base sp06a + base sp07a) / base ricavi × 360`. **Ripiego (Review Focus 1):** se la base non ha alcun dettaglio commerciale (`sp06a+b+c+d+g == 0` mentre `sp06 − sp06e − sp06f > 0`), la massa commerciale intera vale da «clienti», come fa oggi `_alloc` con `primary_idx=0`. In quel caso `sp06b/c/d/g` restano a zero.
- Con il piano `crediti_commerciali`, la massa d'apertura del piano comprende tutto il commerciale. `sp06a` = generato (`target − sp07a` generato, cioè zero lato oltre: col piano il lato oltre è tutto pregresso) + la quota clienti di `residual_short` secondo il mix base di `a/b/c/d/g`. `sp06b/c/d/g` ricevono la loro sola quota di `residual_short`, perché col piano non generano nulla di nuovo. Il report misura in questo caso anche il pregresso, quindi l'accettazione «DSO del report = input» vale **solo senza piano**: dichiaralo in un commento.
- `sp06_trade` resta la somma `a+b+c+d+g`, usata a valle da `sp06 = sp06_trade + sp06e + sp06f` e da `generated['crediti_commerciali']`.

- [ ] **Step 1: test che falliscono**
```python
def test_M1_dso_del_report_uguale_all_input_senza_piano():
    rows = righe(dso_days=90)
    e = generato(genera(rows, report=True))
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        dso = (sp["sp06a_crediti_clienti_breve"] + sp["sp07a_crediti_clienti_lungo"]) / ce["ce01_ricavi_vendite"] * 360
        assert abs(dso - D("90")) < D("0.05")

def test_M1_altri_crediti_restano_costanti():
    e = generato(genera(righe(dso_days=90, revenue_growth_pct=10)))
    assert _q(e.anni[2027][0]["sp06g_crediti_altri_breve"]) == _q(BASE_BS["sp06g_crediti_altri_breve"])
    assert _q(e.anni[2029][0]["sp06g_crediti_altri_breve"]) == _q(BASE_BS["sp06g_crediti_altri_breve"])

def test_M1_dso_derivato_a_crescita_zero_non_muove_i_clienti():
    e = generato(genera(righe()))
    sp = e.anni[2027][0]
    assert abs(sp["sp06a_crediti_clienti_breve"] + sp["sp07a_crediti_clienti_lungo"]
               - BASE_BS["sp06a_crediti_clienti_breve"] - BASE_BS["sp07a_crediti_clienti_lungo"]) < D("1")

def test_M1_base_senza_dettaglio_ripiega_sull_aggregato():
    piatto = {k: D("0") for k in ("sp06a_crediti_clienti_breve", "sp06g_crediti_altri_breve",
                                    "sp07a_crediti_clienti_lungo")}
    commerciale = BASE_BS["sp06a_crediti_clienti_breve"] + BASE_BS["sp06g_crediti_altri_breve"]
    # sp06 resta lo stesso aggregato: la massa commerciale e' tutta senza dettaglio
    e = generato(genera(righe(), bs=piatto))
    sp = e.anni[2027][0]
    assert sp["sp06a_crediti_clienti_breve"] > D("0")
    assert abs(sp["sp06a_crediti_clienti_breve"] - commerciale) < D("1")
    assert sp["sp06g_crediti_altri_breve"] == D("0")
```
Scrivi anche un test col piano `crediti_commerciali`. Prendi un piano valido da `tests/test_budget_pregresso.py`, che ha
un helper per costruirlo, e verifica che `sp06a+b+c+d+g` = `sp06_trade` dichiarato e che il foglio pareggi. Aggiorna
le aspettative dei test esistenti che falliscono **solo** perché `sp06b/c/d/g` ora restano costanti (`tests/test_forecast_*`,
`tests/test_budget_pregresso.py`): ogni aspettativa cambiata va motivata nel messaggio di commit.

- [ ] **Step 2: verifica che falliscano.**

- [ ] **Step 3: implementazione.** Lo schema è questo: calcola il riparto di `sp07` lato commerciale (oggi a 4809-4853)
**prima** del DSO, o almeno fai calcolare `sp07a` prima, poi applica il target sui clienti e costruisci
`sp06a..g`. Le righe 4800-4807 (`_alloc` di `sp06_trade`) diventano l'assegnazione esplicita:
```python
        # #61 S03 (decisione del proprietario 2026-10-05): il DSO governa i soli clienti, sp06a + sp07a =
        # DSO × ricavi / 360. Le altre voci commerciali restano quelle dell'anno prima, come dichiara il passo 6.
```
Mantieni le firme di `_alloc` e di `_consuma_in_ordine`. Non toccare `sp06e`/`sp06f`. Se lo spostamento dell'ordine
diventa troppo invasivo, calcola `sp07a` in anticipo con la stessa formula che userà il blocco `sp07` e verifica con
un `assert`, nel test, che le due coincidano.

- [ ] **Step 4: verifica che passino** il nuovo file e `tests/test_forecast_*.py tests/test_budget_pregresso.py tests/test_engine_accounting_invariants.py tests/test_forecast_dichiarato_vs_persistito.py`.

- [ ] **Step 5: commit** — `feat(motore): il DSO governa i soli crediti verso clienti (#61 S03, S27)`

---

### Task 5: M7 motore — giorni di magazzino in due gruppi, `ce02`/`ce03` dallo SP, avviso

**Files:**
- Modify: `database/models.py` (`BudgetAssumptions.dio_pf_days = Column(Numeric(10, 2), nullable=True)` accanto a `dio_days`, riga 628), `migrate_db.py:104` (`("dio_pf_days", "NUMERIC(10,2)")`), `backend/app/schemas/budget.py:323` e `:482`, `backend/app/services/assumptions_service.py:237`, `contracts/final_report_assumption_sections.json:5` (aggiungi `"dio_pf_days"` ai campi del circolante), `backend/app/services/final_report_assumptions.py:145` (label `"dio_pf_days": "Giorni prodotti finiti e merci (sui ricavi)"`, e `"dio_days"` → `"Giorni materie prime e semilavorati (sul consumo)"`), `backend/app/renderers/business_plan/data.py:290` (stesse label, più la riga `dio_pf_days`), `backend/app/renderers/typst/dossier_catalog/allegati.py:119`, `scripts/parita_motore.py:307` (`"dio_pf_days": _giorni(rng, 5, 90)` nel profilo `giorni_manuali`)
- Modify: `calculations/projection_common.py:675` (nuova funzione `rimanenze_gruppo_materie`), `calculations/forecast_engine.py:3302-3420` (blocco CE delle rimanenze), `:3295-3296` (`ce02`/`ce03`), `:3884-3908` e `:4856-4862` (SP), `:1861` (`_CAMPI_NEUTRI_RESIDUO['sp05_rimanenze']`)
- Test: `tests/test_rilievi_61_62_magazzino.py` (nuovo); da aggiornare `tests/test_forecast_magazzino_settore.py`, `tests/test_fix_rilievi_motore.py:193,237`

**Interfaces:**
- Consuma: `details['avvisi']` (Task 1).
- Produce: la colonna `dio_pf_days`. `details['rimanenze'] = {'materie_semilavorati': {...}, 'prodotti_finiti': {...}, 'lavori_in_corso': {...}}`, ciascuno con `apertura, chiusura, giorni, base_giorni, degenere, override, contropartita` (`'ce10+ce02'`, `'ce02'`, `'ce03'`). `details['rimanenze_materie']` resta con le chiavi di oggi, perché lo leggono SP e test, e descrive la sola `sp05a`. `details['dio_applied']` = giorni del gruppo 1. Nuova `details['dio_pf_applied']`. `details['avviso_rimanenze']`: lista di dict `{gruppo, apertura, chiusura, variazione, giorni}`, sempre presente. Funzione pura `rimanenze_gruppo_materie(apertura_a, apertura_b, acquisti, giorni) -> (chiusura_a, chiusura_b)`.

Regole, dalla spec M7:
- **Gruppo 1** (`sp05a + sp05b`), giorni sul consumo di materie. Quota materie `q = apertura_a / (apertura_a + apertura_b)` (se entrambe sono zero, `q = 1`; con materie a zero e semilavorati positivi, `q = 0`). In forma chiusa, `chiusura_a = q × (acquisti + apertura_a) × g / (360 + q × g)`, perché il consumo = acquisti + apertura_a − chiusura_a e il gruppo = consumo × g / 360. Poi `chiusura_gruppo = (acquisti + apertura_a − chiusura_a) × g / 360` e `chiusura_b = chiusura_gruppo − chiusura_a`. Tutto è `max(0, ·)`, quantizzato al centesimo dal chiamante. Con `q = 1` coincide con `rimanenze_materie` di oggi: c'è un test che lo prova.
- Il DIO derivato del gruppo 1 è `(base sp05a + base sp05b) / (base ce05 + base ce10) × 360`, con la soglia `soglia_giorni_magazzino(settore)` e il ripiego `_materie_base` per le basi senza dettaglio (Review Focus 2).
- **Gruppo 2** (`sp05d`): `dio_pf_days` esplicito, oppure derivato `base sp05d / base ricavi × 360` con la stessa soglia; chiusura = ricavi × giorni / 360; degenere ⇒ si riporta il saldo.
- **`sp05c`/`sp05e`**: come oggi (`_derived_days` sui ricavi della loro somma), ma riparto fra loro due soltanto.
- **CE**: `ce10 = apertura_a − chiusura_a` (come oggi). `ce02 = (chiusura_b + chiusura_d) − (apertura_b + apertura_d)`, `ce03 = chiusura_c − apertura_c`. Un override vince e lo SP lo segue: `ce02_override` sposta la chiusura del gruppo 2, oppure, se `sp05d` è zero, di `sp05b`; `ce03_override` sposta `sp05c`. Un override che porterebbe una chiusura sotto zero si rifiuta con `ValueError` in italiano, sul modello della riga 3371.
- Poiché `ce02`/`ce03` dipendono dai ricavi dell'anno (gruppo 2, `sp05c`), il calcolo sta nel CE come per `ce10`, e lo SP **legge** `details['rimanenze']`, senza ricalcolare.
- `_CAMPI_NEUTRI_RESIDUO['sp05_rimanenze']`: restano neutri solo `sp05e_acconti`. Le altre voci ora hanno una contropartita di CE, e un centesimo su di loro attraverserebbe il confine CE↔SP: aggiorna il commento e `tests/test_forecast_residuo_neutro.py`.
- **Avviso** (per gruppo, solo se i giorni sono **espliciti**): `|variazione| > 50% apertura` oppure `|variazione| > flusso annuo` (consumo per il gruppo 1, ricavi per il gruppo 2). La frase va in `details['avvisi']`: «Nel {anno} i giorni inseriti per {gruppo} ({g} gg sul consumo) portano il magazzino da {apertura} a {chiusura}: {variazione} € di {costo|ricavo} a conto economico.», con gli importi resi da `_importo_it`.

- [ ] **Step 1: test che falliscono**, in `tests/test_rilievi_61_62_magazzino.py`:
```python
from decimal import Decimal as D
from calculations.projection_common import rimanenze_gruppo_materie, rimanenze_materie
from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, righe

def test_gruppo_senza_semilavorati_coincide_con_b01():
    ca, cb = rimanenze_gruppo_materie(D("287312"), D("0"), D("135773.40"), D("25"))
    atteso, _ = rimanenze_materie(D("287312"), D("135773.40"), D("25"))
    assert abs(ca - atteso) < D("0.000001") and cb == D("0")

def test_gruppo_rispetta_i_giorni_sul_consumo():
    ca, cb = rimanenze_gruppo_materie(D("100000"), D("50000"), D("400000"), D("60"))
    consumo = D("400000") + D("100000") - ca
    assert abs((ca + cb) - consumo * D("60") / D("360")) < D("0.01")
    assert abs(ca / (ca + cb) - D("100000") / D("150000")) < D("0.0001")

def test_ambienta_25_giorni_avvisa():
    e = generato(genera(righe(dio_days=25)))
    assert any("287.312" in a for a in e.det[2027]["avvisi"])

def test_prodotti_finiti_seguono_i_ricavi_e_passano_da_ce02():
    bs = {"sp05a_materie_prime": D("187312"), "sp05d_prodotti_finiti": D("100000")}
    e = generato(genera(righe(dio_pf_days=10), bs=bs))
    sp, ce = e.anni[2027]
    assert abs(sp["sp05d_prodotti_finiti"] - ce["ce01_ricavi_vendite"] * 10 / 360) < D("0.01")
    assert abs(ce["ce02_variazioni_rimanenze"] - (sp["sp05d_prodotti_finiti"] - D("100000")
               + sp["sp05b_prodotti_in_corso"] - D("0"))) < D("0.01")

def test_lavori_in_corso_passano_da_ce03():
    bs = {"sp05a_materie_prime": D("187312"), "sp05c_lavori_in_corso": D("100000")}
    e = generato(genera(righe(revenue_growth_pct=10), bs=bs))
    sp, ce = e.anni[2027]
    assert abs(ce["ce03_lavori_interni"] - (sp["sp05c_lavori_in_corso"] - D("100000"))) < D("0.01")

def test_base_senza_dettaglio_non_perde_massa():
    piatto = {"sp05a_materie_prime": D("0")}  # sp05_rimanenze resta 287312
    e = generato(genera(righe(), bs=piatto))
    assert abs(e.anni[2027][0]["sp05_rimanenze"] - BASE_BS["sp05_rimanenze"]) < D("1")

def test_override_ce02_vince_e_lo_sp_lo_segue():
    bs = {"sp05a_materie_prime": D("187312"), "sp05d_prodotti_finiti": D("100000")}
    e = generato(genera(righe(ce02_override=-20000), bs=bs))
    sp, ce = e.anni[2027]
    assert ce["ce02_variazioni_rimanenze"] == D("-20000")
    assert abs(sp["sp05d_prodotti_finiti"] - D("80000")) < D("0.01")
```
Nei test con `bs={...}` che spostano massa fra le sotto-voci, il totale `sp05_rimanenze` resta 287.312: verificalo
nella fixture. Altrimenti il seed sbilancia la base.

- [ ] **Step 2: verifica che falliscano.**

- [ ] **Step 3: implementazione.** Aggiungi la colonna in tutti i punti elencati in Files. Esegui
`backend/venv/bin/python migrate_db.py financial_analysis.db`. Poi scrivi la funzione pura in `projection_common.py`:
```python
def rimanenze_gruppo_materie(apertura_a, apertura_b, acquisti, giorni) -> Tuple[Decimal, Decimal]:
    """Materie prime (sp05a) e semilavorati (sp05b) come un solo magazzino di produzione, giorni sul consumo di
    materie (#62 nota S04, decisione del proprietario 2026-10-05). La quota materie del gruppo resta quella
    d'apertura; la chiusura delle materie si risolve in forma chiusa come `rimanenze_materie` (con q = 1 coincide)."""
    a, b = Decimal(str(apertura_a or 0)), Decimal(str(apertura_b or 0))
    acq, g = Decimal(str(acquisti or 0)), Decimal(str(giorni or 0))
    q = Decimal('1') if a + b == 0 else a / (a + b)
    chiusura_a = max(ZERO, q * (acq + a) * g / (Decimal('360') + q * g))
    gruppo = max(ZERO, (acq + a - chiusura_a) * g / Decimal('360'))
    return chiusura_a, max(ZERO, gruppo - chiusura_a)
```
Nel blocco CE (3302-3420) estendi il calcolo al gruppo 1, con `apertura_b` dalla base o dall'anno prima, come
`apertura_materie`, e aggiungi i calcoli del gruppo 2 e di `sp05c`, che leggono `forecast_revenue` = `ce01` dell'anno
già calcolato in questa funzione. Poi sostituisci le righe 3295-3296 di `ce02`/`ce03` con i valori derivati. Se `ce01` è
calcolato **dopo** la riga 3295, sposta l'assegnazione di `ce02`/`ce03` dopo il blocco rimanenze: entrano solo nel
valore della produzione, che si somma più in basso. Verificalo leggendo il punto in cui `ce02` compare nella somma.
Nello SP (3884-3908 e 4856-4862) leggi le chiusure da `details['rimanenze']`.

- [ ] **Step 4: verifica che passino** il nuovo file, `tests/test_forecast_magazzino_settore.py`, `tests/test_fix_rilievi_motore.py`, `tests/test_forecast_residuo_neutro.py`, `tests/test_m1_05b_assumption_sections.py`, `tests/test_final_report_contract.py`, `tests/test_parita_motore_profili.py`, e infine la suite intera. Le aspettative cambiate vanno motivate.

- [ ] **Step 5: commit** — `feat(motore): rimanenze in due gruppi, ce02/ce03 dallo SP, avviso sul magazzino (#62 nota S04)`

---

### Task 6: M7 frontend — due caselle di giorni, DIO storico, avvisi del motore nel passo 4

**Files:**
- Modify: `frontend/types/api.ts:542,653` (`dio_pf_days`), `:1237` (`dio_pf_applied?`, `rimanenze?`, `avviso_rimanenze?`)
- Modify: `frontend/lib/budget-field-rules.ts:68`, `frontend/lib/budget-horizon.ts:134,292` (e il tipo a 48), `frontend/app/budget/page.tsx:569`, `frontend/lib/budget-wizard-steps.ts:40`, `frontend/components/budget/assumption-rows.ts:92`
- Modify: `frontend/lib/budget-turnover.ts:33-68` (`computeAutoDays`: `"dio"` diventa gruppo 1, cioè `sp05a+sp05b` sul consumo con il ripiego aggregato; nuovo `"dio_pf"` = `sp05d / ricavi × 360`). **Niente** più `null` quando è degenere: restituisce il numero, e il chiamante decide.
- Modify: `frontend/lib/budget-circolante-step.ts:40-112` (`GiorniMedi`, `GIORNI_LABELS`, `giorniMediRows`), `frontend/components/budget/wizard/steps/StepCircolante.tsx:49-78`
- Test: `frontend/lib/budget-turnover.test.ts`, `frontend/lib/budget-circolante-step.test.ts`, `frontend/lib/budget-horizon.test.ts`

**Interfaces:**
- Consuma: `details.avvisi` (Task 1) e `dio_pf_days` (Task 5).
- Produce: `GIORNI_LABELS.dio = "Giorni materie prime e semilavorati (sul consumo)"`, `GIORNI_LABELS.dio_pf = "Giorni prodotti finiti e merci (sui ricavi)"`. La riga `dio_days` ha `sub` = «Storico {anno}: {n} gg sul consumo», e se supera 365 aggiunge «— oltre la soglia: senza un valore il motore riporta il saldo». Una funzione pura `avvisiMotore(years: PreviewYear[]): string[]` in `lib/budget-preview-rows.ts` (accanto a `scopertoAvvisi`) raccoglie `details.avvisi` di tutti gli anni senza duplicati. La riusano i Task 7 e 9.

- [ ] **Step 1: test che falliscono.** In `budget-turnover.test.ts`, nel describe B01 (riga 78): «dio somma materie e
semilavorati sul consumo», «dio_pf = sp05d / ricavi × 360», «dio oltre 365 restituisce il numero (807), non null». Il
caso AMBIENTA: sp05a 287312, ce05 129308, ce10 −1217 ⇒ 807. In `budget-circolante-step.test.ts`: `giorniMediRows`
restituisce 4 righe nell'ordine dso, dio, dio_pf, dpo; la riga dio ha `sub` che contiene «807» e «oltre la soglia».
`avvisiMotore` deduplica. In `budget-horizon.test.ts` aggiorna l'elenco congelato dei campi con `dio_pf_days`: è una
riga aggiunta di proposito.

- [ ] **Step 2: verifica che falliscano** — `cd frontend && npx vitest run lib/budget-turnover.test.ts lib/budget-circolante-step.test.ts lib/budget-horizon.test.ts lib/budget-preview-rows.test.ts`

- [ ] **Step 3: implementazione.** Aggiungi il campo in tutti i punti elencati. In `StepCircolante.tsx`, sotto la Card
«Giorni medi», metti un box ambra per ogni frase di `avvisiMotore(previewYears)` che contiene «magazzino», con lo
stesso markup di `StepPatrimonialePiano.tsx:525-539` (icona `AlertTriangle`). Gli avvisi di imposte e debiti
appartengono ad altri passi: per non filtrare sul testo, `avvisiMotore` accetta un secondo argomento
`chiave?: "magazzino" | "acconti" | "altri_debiti"` e legge gli elenchi strutturati (`avviso_rimanenze`, ecc.) quando
serve. Scelta consigliata: Task 5, 7 e 9 scrivono **anche** l'elenco strutturato, e il passo usa quello. Il Task 5 lo
fa già (`avviso_rimanenze`).

- [ ] **Step 4: verifica che passino** gli stessi file, poi `npm test`.

- [ ] **Step 5: commit** — `feat(wizard): giorni di magazzino in due gruppi e DIO storico accanto alla casella (#62 nota S04)`

---

### Task 7: M5 — avviso sugli acconti sotto il minimo

**Files:**
- Modify: `calculations/forecast_engine.py`, il blocco imposte vicino al `tax_settlement_saldo_acconto` (~4351-4368), e `details['imposte']` (4919-4943)
- Modify: `frontend/types/api.ts:505-518` (`ImposteDetail.avviso_acconti?`), `frontend/components/budget/wizard/steps/StepImposte.tsx` (box ambra sotto la tabella degli acconti)
- Test: `tests/test_rilievi_61_62_motore.py`, `frontend/lib/budget-imposte-step.test.ts`

**Interfaces:**
- Produce: `details['imposte']['avviso_acconti']` = `None` oppure `{'acconti': D, 'minimo_storico': D, 'minimo_previsionale': D}`, presente in entrambi i modi (`None` in `manual`), più la frase in `details['avvisi']`. Una funzione pura `avvisoAcconti(details): string | null` in `lib/budget-imposte-step.ts`.

- [ ] **Step 1: test che falliscono**
```python
def test_M5_acconti_sotto_entrambi_i_minimi_avvisano():
    rows = righe(tax_advances_paid=1)  # 1 € esplicito: sotto qualunque imposta positiva
    e = generato(genera(rows))
    av = e.det[2028]["imposte"]["avviso_acconti"]
    assert av is not None and av["acconti"] == D("1")
    assert any("acconti" in a.lower() for a in e.det[2028]["avvisi"])

def test_M5_acconti_non_dichiarati_non_avvisano():
    e = generato(genera(righe()))
    assert all(e.det[y]["imposte"]["avviso_acconti"] is None for y in (2027, 2028, 2029))
```
Prima di scrivere il primo test verifica che le imposte di AMBIENTA siano positive negli anni del test. Se non lo sono,
sostituisci `tax_advances_paid=1` con un valore inferiore all'imposta dichiarata.

- [ ] **Step 2: verifica che falliscano.**

- [ ] **Step 3: implementazione.** Dopo la chiamata al kernel:
```python
            esplicito = Decimal(str(getattr(assumption, 'tax_advances_paid', None) or 0))
            avviso_acconti = None
            if esplicito > ZERO and esplicito < previous_tax and esplicito < current_tax:
                # #62 S28: l'importo inserito vince (puo' essere voluto), ma sotto sia al metodo storico sia al
                # previsionale espone a sanzioni: si dichiara, non si corregge.
                avviso_acconti = {'acconti': esplicito, 'minimo_storico': previous_tax,
                                  'minimo_previsionale': current_tax}
                details_avvisi.append(
                    f"Nel {assumption.forecast_year} gli acconti inseriti ({_importo_it(esplicito)}) sono sotto sia "
                    f"all'imposta dell'anno prima ({_importo_it(previous_tax)}) sia a quella dell'anno "
                    f"({_importo_it(current_tax)}): sotto il minimo di legge si pagano sanzioni e interessi.")
```
`details_avvisi` è la lista di `details['avvisi']`. Se `details` è `None` in quel punto, accumula in una variabile locale
e scrivila insieme a `details['imposte']`. Aggiungi `'avviso_acconti': avviso_acconti` a entrambi i rami di
`details['imposte']`. In `StepImposte.tsx` mostra il box ambra per gli anni con `avviso_acconti`.

- [ ] **Step 4: verifica che passino.**

- [ ] **Step 5: commit** — `feat(motore): avviso sugli acconti sotto il minimo (#62 S28)`

---

### Task 8: M4 — compensazione del credito tributario del consuntivo, a scelta dell'utente

**Files:**
- Modify: `database/models.py:652` (accanto a `overdraft_allowed`: `compensa_crediti_tributari = Column(Boolean, default=False, nullable=False)`), `migrate_db.py:116` (`("compensa_crediti_tributari", "BOOLEAN DEFAULT 0 NOT NULL")`), `backend/app/schemas/budget.py:336,488`, `backend/app/services/assumptions_service.py:243`, `backend/app/schemas/final_report.py:89`, `backend/app/services/final_report_assumptions.py:178` (label «Compensazione del credito tributario residuo con le imposte»), `contracts/final_report_assumption_sections.json` (sezione dei pregressi/imposte; verifica quale contiene `tax_advances_paid`), `frontend/types/api.ts:550,659`, `frontend/types/final-report.ts:66`, `frontend/lib/budget-field-rules.ts:103`, `frontend/lib/budget-wizard-steps.ts` (passo pregresso), `frontend/lib/budget-horizon.ts:48,140,298`, `scripts/parita_motore.py:670`
- Modify: `calculations/projection_common.py:596-645` (kernel), `calculations/forecast_engine.py:2513-2526` (regola della sola prima riga, anche per questa colonna), `:4251-4368` (blocco imposte), `:4919-4943` (`details`)
- Modify: `frontend/components/budget/wizard/steps/StepPatrimonialePregresso.tsx` (casella accanto alla riga `crediti_tributari_breve`, sul modello di `StepPatrimonialePiano.tsx:223,456`, `boolAssumption` + `updateAll` sulla sola prima riga)
- Test: `tests/test_tax_kernel_compensazione.py`, `tests/test_rilievi_61_62_motore.py`

**Interfaces:**
- Produce: `tax_settlement_saldo_acconto(..., credito_storico_compensabile=ZERO)` → `TaxYear.credito_storico_compensato: Decimal = ZERO`; `details['imposte']['credito_storico_compensato']` (presente in entrambi i modi) e `details['imposte']['compensazione_ignorata']: bool`.

Regole, dalla spec M4: la casella si legge sulla prima riga, e l'utente la tiene uguale su tutte.
`capienza = max(0, saldo + acconti + rate − credito_compensato)`; `credito_storico_compensato = min(credito_storico_compensabile, capienza)`; `cash_out −= credito_storico_compensato`. Nel motore,
`crediti_consuntivo −= credito_storico_compensato` dopo l'incasso del piano: il credito scende e la cassa, che è il plug,
sale dello stesso importo. Il debito generato non cambia. Via manuale: `compensazione_ignorata = True` se la casella è
accesa, e nessun effetto.

- [ ] **Step 1: test che falliscono**

In `tests/test_tax_kernel_compensazione.py`, dove si usa l'helper `_k(**kw)`:
```python
def test_credito_storico_compensa_dopo_il_credito_da_acconti():
    t = _k(opening_credit=D("1000"), saldo_due=D("3000"), rate_due=D("0"), current_tax=D("5000"),
           previous_tax=D("4000"), acconto_pct=D("100"), explicit_advances=None,
           credito_storico_compensabile=D("10000"))
    assert t.credito_compensato == D("1000")
    assert t.credito_storico_compensato == D("3000") + D("4000") - D("1000")
    assert t.generated_debt == D("1000")  # 5000 - 4000 acconti: il debito non cambia
    assert t.cash_out == D("0")

def test_senza_credito_storico_nulla_cambia():
    a = _k(opening_credit=D("0"), saldo_due=D("3000"), rate_due=D("0"), current_tax=D("5000"),
           previous_tax=D("4000"), acconto_pct=D("100"), explicit_advances=None)
    b = _k(opening_credit=D("0"), saldo_due=D("3000"), rate_due=D("0"), current_tax=D("5000"),
           previous_tax=D("4000"), acconto_pct=D("100"), explicit_advances=None, credito_storico_compensabile=D("0"))
    assert a == b and b.credito_storico_compensato == D("0")
```
Adatta i nomi dei parametri a ciò che `_k` accetta davvero, leggendo il file. In `tests/test_rilievi_61_62_motore.py`:
```python
def test_M4_casella_spenta_identica_a_prima():
    a = generato(genera(righe()))
    b = generato(genera(per_anno(righe(), "compensa_crediti_tributari", [False, False, False])))
    assert a.anni == b.anni

def test_M4_casella_accesa_consuma_il_credito_e_libera_cassa():
    a = generato(genera(righe()))
    b = generato(genera(per_anno(righe(), "compensa_crediti_tributari", [True, True, True])))
    comp = b.det[2027]["imposte"]["credito_storico_compensato"]
    assert comp > D("0")
    assert _q(a.anni[2027][0]["sp06e_crediti_tributari_breve"] - b.anni[2027][0]["sp06e_crediti_tributari_breve"]) == _q(comp)
    assert _q(b.anni[2027][0]["sp09_disponibilita_liquide"] - a.anni[2027][0]["sp09_disponibilita_liquide"]) >= _q(comp) - D("0.01")
    assert _q(a.anni[2027][0]["sp16e_debiti_tributari_breve"]) == _q(b.anni[2027][0]["sp16e_debiti_tributari_breve"])

def test_M4_via_manuale_la_dichiara_ignorata():
    rows = per_anno(righe(sp16e_growth_pct=0), "compensa_crediti_tributari", [True, True, True])
    e = generato(genera(rows))
    assert e.det[2027]["imposte"]["compensazione_ignorata"] is True
    assert e.det[2027]["imposte"]["credito_storico_compensato"] == D("0")
```
Lo scoperto è concesso nel kit: se la cassa di partenza è negativa, confronta `sp09 − scoperto` invece di `sp09`.
Leggi `details['scoperto_residuo']` o `sp16a`.
Va deciso anche il comportamento quando la casella è diversa fra le righe. Il motore legge **la prima riga**: aggiungi
un test che lo fissi, prima riga True e altre False ⇒ compensa in tutti gli anni. Non sollevare errori: l'interfaccia
scrive sempre tutte le righe.

- [ ] **Step 2: verifica che falliscano.**

- [ ] **Step 3: implementazione.** Nel kernel:
```python
                                 carry_excess_credit=False, credito_storico_compensabile=ZERO) -> TaxYear:
    ...
    compensated = min(opening_credit, payable) if carry_excess_credit else opening_credit
    # #62 S14/S18 (decisione del proprietario 2026-10-05): il credito tributario del consuntivo che il piano non
    # incassa si compensa, se l'utente lo sceglie, con cio' che resta da versare dopo il credito da acconti.
    capienza = max(ZERO, payable - compensated)
    storico = min(max(ZERO, d(credito_storico_compensabile)), capienza)
    return TaxYear(..., cash_out=saldo_paid + acconti + rate_due - compensated - storico,
                   credito_compensato=compensated, credito_storico_compensato=storico)
```
Nel motore leggi `compensa = bool(getattr(assumptions[0], 'compensa_crediti_tributari', False))` in `compute_forecast`
e passalo a `_calculate_balance_sheet` sul modello di `pregresso`: verifica come `pregresso` arriva alla funzione e
segui lo stesso percorso. Nel ramo `saldo_acconto` passa `credito_storico_compensabile=crediti_consuntivo if compensa
else ZERO` e poi `crediti_consuntivo -= tax_year.credito_storico_compensato`, **prima** di
`sp06e = crediti_consuntivo + ...`. `details['imposte']['crediti_tributari_consuntivo']` dichiara così il residuo già
compensato, e l'anno dopo riparte da lì (riga 4252). Col piano `crediti_tributari_breve`, la riga 4262 riassegna
`crediti_consuntivo` dal residuo del runoff a ogni anno, quindi la compensazione dell'anno prima andrebbe persa. Va
quindi accumulata: tieni in `details['imposte']['credito_storico_compensato_cumulato']` la somma degli anni e sottraila
dal residuo del runoff. Un test col piano attivo lo fissa: prendi un piano da `tests/test_budget_pregresso.py:150`.
Verifica infine `_realign_sp_declarations` (1569-1580): un override di `sp06e` riempie prima la quota del consuntivo,
e questo non cambia.

- [ ] **Step 4: verifica che passino** il kernel, il nuovo file, `tests/test_budget_pregresso.py`, `tests/test_imposte_commercialista.py`, `tests/test_forecast_override_tributario.py`, `tests/test_forecast_dichiarato_vs_persistito.py`, `tests/test_bulk_tipizzato.py`, i test di contratto e `npm test`.

- [ ] **Step 5: commit** — `feat(motore): compensazione del credito tributario residuo con le imposte, a scelta (#62 S14 S18)`

---

### Task 9: M6 — avviso sugli altri debiti passati da oltre a entro 12 mesi

**Files:**
- Modify: `calculations/forecast_engine.py:203-207` (`ForecastSource`: aggiungi `prev_base_bs: Optional[Any] = None`), `:709-744` (`load_forecast_source`: `get_fy_prefer_full(db, scenario.company_id, scenario.base_year - 1)`, poi il suo `balance_sheet` o `None`), e il primo anno di `_calculate_balance_sheet`, dove si calcolano `sp16g`/`sp17g` (4372-4448)
- Modify: `frontend/components/budget/wizard/steps/StepPatrimonialePiano.tsx:525-539` (box ambra)
- Modify: `tests/rilievi_kit.py` (`genera(..., anno_prima_bs=None)` semina un `FinancialYear` 2025 annuale con un BS dato, oppure con la base + il ritocco)
- Test: `tests/test_rilievi_61_62_motore.py`

**Interfaces:**
- Produce: `details['avviso_altri_debiti_breve']` = `None` oppure `{'oltre_prima': D, 'oltre_base': D, 'entro_base': D, 'anno_prima': int}`, presente in ogni anno ma valorizzato solo nel primo, più la frase in `details['avvisi']`.

Regola: nel primo anno di piano, se `prev_base_bs` esiste, `prev sp17g > base sp17g` e il piano `altri_debiti` è
assente ⇒ avviso: «Gli altri debiti oltre 12 mesi sono scesi da {oltre_prima} ({anno_prima}) a {oltre_base}
({base_year}) e quelli entro 12 mesi ora crescono con i ricavi: se sono debiti che si pagheranno a rate, scadenziali
al passo 5 «Patrimoniale pregresso».» Senza `prev_base_bs` ⇒ `None` («non lo so»).

- [ ] **Step 1: test che falliscono**
```python
def test_M6_avviso_quando_l_oltre_si_e_spostato_entro():
    prima = {**BASE_BS, "sp17g_altri_debiti_lungo": D("201851.00"),
             "sp16g_altri_debiti_breve": BASE_BS["sp16g_altri_debiti_breve"] - D("201851.00")}
    e = generato(genera(righe(), anno_prima_bs=prima))
    av = e.det[2027]["avviso_altri_debiti_breve"]
    assert av is not None and av["oltre_prima"] == D("201851.00")
    assert any("altri debiti" in a.lower() for a in e.det[2027]["avvisi"])

def test_M6_senza_anno_prima_nessun_avviso():
    e = generato(genera(righe()))
    assert e.det[2027]["avviso_altri_debiti_breve"] is None
```
Il BS dell'anno prima non deve pareggiare per il motore, che ne legge un solo campo. Verifica comunque che il seed
non passi da un validatore: `genera` scrive direttamente le righe ORM.

- [ ] **Step 2: verifica che falliscano.**

- [ ] **Step 3: implementazione**, nel kit, in `ForecastSource`/`load_forecast_source` e nel motore. La preview usa la
stessa `load_forecast_source` (`forecast_preview_service.py:39`), quindi anteprima e generazione restano allineate. Gli
anni non zero scrivono `details['avviso_altri_debiti_breve'] = None`. In `StepPatrimonialePiano.tsx` mostra il box
quando un anno ha `avviso_altri_debiti_breve`.

- [ ] **Step 4: verifica che passino** il nuovo file, `tests/test_budget_pregresso.py` e `tests/test_forecast_*.py`.

- [ ] **Step 5: commit** — `feat(motore): avviso sugli altri debiti passati da oltre a entro 12 mesi (#62 S18)`

---

### Task 10: R1 — «Imposte pagate» = versamenti effettivi

**Files:**
- Modify: `calculations/forecast_engine.py:97-104` (`engine_meta`: `'imposte_versate'`)
- Modify: `backend/app/calculations/cashflow_detailed.py:58-65` (firma: `imposte_versate: Optional[Decimal] = None`), `:200-203`, `:249`, `:271`
- Modify: `backend/app/services/analysis_service.py:236-249,367-392`, `backend/app/services/calculation_service.py:438-448`
- Test: `tests/test_cashflow_tributi.py`

**Interfaces:**
- Consuma: `details['imposte']` (Task 8: `credito_storico_compensato`).
- Produce: `engine_meta['imposte_versate']`, una stringa al centesimo oppure `None` (in `manual` o senza kernel):
`saldo_paid + acconti_paid + rate_paid − credito_compensato − credito_storico_compensato`.

- [ ] **Step 1: test che falliscono**, in `tests/test_cashflow_tributi.py` (segui il pattern del file, cioè bulk e poi `DetailedCashFlowCalculator.calculate`):
```python
def test_R1_imposte_pagate_sono_i_versamenti_e_la_cassa_non_cambia(...):
    # stesso anno calcolato due volte: senza imposte_versate (com'era) e con
    vecchio = DetailedCashFlowCalculator.calculate(bs_cur, bs_prev, inc_cur, 2028, erogazioni=None)
    nuovo = DetailedCashFlowCalculator.calculate(bs_cur, bs_prev, inc_cur, 2028, erogazioni=None,
                                                 imposte_versate=versate)
    assert nuovo.<percorso taxes_paid> == -versate
    assert nuovo.<percorso totale variazione cassa> == vecchio.<percorso totale variazione cassa>
    assert nuovo.<percorso delta_tax> == vecchio.<percorso delta_tax> - (vecchio.<taxes_paid> - nuovo.<taxes_paid>)
```
Sostituisci i `<percorso …>` con gli attributi veri del dataclass `DetailedCashFlowStatement`, leggendo il file. Prendi
`versate` da `engine_meta['imposte_versate']` dell'anno, generato con `tests.rilievi_kit.genera`. Aggiungi un test
end-to-end, in `analysis_service` e in `calculate_detailed_cashflow_historical_and_forecast`, che verifichi lo stesso
`taxes_paid` sulle due pagine: è la regola F3.

- [ ] **Step 2: verifica che falliscano.**

- [ ] **Step 3: implementazione**:
```python
        taxes_paid = -income_taxes if imposte_versate is None else -imposte_versate
        # #62 S13: con i versamenti del motore la riga «imposte pagate» e' quella vera; la variazione della
        # posizione tributaria nel circolante assorbe la differenza, e la cassa resta la stessa.
        if imposte_versate is not None:
            delta_tax = delta_tax + (imposte_versate - income_taxes)
```
Calcolalo **prima** di `wc_total` (riga 249). Verifica il segno su un caso numerico nel test, perché
`delta_tax` positivo è una fonte di cassa. Passa `imposte_versate` dalle due call site, letto da `engine_meta` come
`erogazioni`.

- [ ] **Step 4: verifica che passino** il file, `tests/test_fix_rilievi_rendiconto.py`, `tests/test_cashflow_*.py` e `tests/test_engine_meta.py`.

- [ ] **Step 5: commit** — `fix(rendiconto): imposte pagate = versamenti del motore, cassa invariata (#62 S13)`

---

### Task 11: I1 — ROD sul debito finanziario medio

**Files:**
- Modify: `calculations/ratios.py:104-113` (`__init__(self, balance_sheet, income_statement, previous_balance_sheet=None)`), `:265-273`
- Modify: `backend/app/services/calculation_service.py:517-540` (passa il BS dell'iterazione precedente; per il primo storico prova `get_fy_prefer_full(db, company_id, year - 1)`), `backend/app/services/analysis_service.py:212-227,304-360` (`_calculate_year_metrics(bs, inc, sector, prev_bs=None)`)
- Modify: `calculations/report_indicators.py:275` (formula «Oneri finanziari / debito finanziario medio (inizio e fine anno; senza inizio, fine anno)»)
- Modify: `CLAUDE.md` (bullet «ROD e PFN su un solo perimetro»)
- Test: `tests/test_fix_rilievi_report.py`

**Interfaces:**
- Produce: `FinancialRatiosCalculator(bs, inc, previous_balance_sheet=None)`. Senza `previous_balance_sheet` il comportamento di oggi resta invariato (Review Focus 4).

- [ ] **Step 1: test che falliscono**
```python
def test_I1_rod_sulla_media_fra_inizio_e_fine():
    bs_prev, _ = _statements({"sp16a_debiti_banche_breve": D("100000")}, {})
    bs, inc = _statements({"sp16a_debiti_banche_breve": D("300000")}, {"ce15_oneri_finanziari": D("10000")})
    calc = FinancialRatiosCalculator(bs, inc, previous_balance_sheet=bs_prev)
    rod = calc.calculate_all_ratios().profitability.rod
    media = (bs_prev.financial_debt_total + bs.financial_debt_total) / 2
    assert rod == FinancialRatiosCalculator.round_decimal(D("10000") / media, 4)

def test_I1_senza_inizio_resta_la_fine_anno():
    bs, inc = _statements({}, {"ce15_oneri_finanziari": D("10000")})
    assert (FinancialRatiosCalculator(bs, inc).calculate_all_ratios().profitability.rod
            == FinancialRatiosCalculator(bs, inc, previous_balance_sheet=None).calculate_all_ratios().profitability.rod)
```
Adatta `_statements` (righe 184-204) se restituisce oggetti legati a sessioni diverse. Verifica anche come si accede a
`round_decimal` (statico o d'istanza) e a `profitability`. Aggiungi un test sul servizio `/ratios`
(`tests/test_multi_year_ratios_years.py`): la seconda colonna usa la media.

- [ ] **Step 2: verifica che falliscano.**

- [ ] **Step 3: implementazione**:
```python
        # #61 S11 (decisione del proprietario 2026-10-05): ROD sul debito finanziario medio dell'anno, stesso
        # perimetro della PFN. Senza un bilancio d'inizio (prima colonna) resta la fine anno.
        debito_fine = self.bs.financial_debt_total
        if self.prev_bs is not None:
            financial_debt = (self.prev_bs.financial_debt_total + debito_fine) / 2
        else:
            financial_debt = debito_fine
        rod = self.safe_divide(self.inc.ce15_oneri_finanziari, financial_debt) if financial_debt > 0 else None
```
Il ROD analitico del report legge i `calculations` di `analysis_service`: passando `prev_bs` in `_calculate_year_metrics`
anche il report usa la media, senza codice in più. La F1 di `report_indicators` (dettaglio mancante) resta com'è.

- [ ] **Step 4: verifica che passino** il file, `tests/test_rilievi_ambienta.py` (aggiorna l'oracolo `test_C03_rod_sui_debiti_finanziari` motivandolo), `tests/test_multi_year_ratios_years.py` e `tests/test_fix_rilievi_liquidita.py`.

- [ ] **Step 5: commit** — `feat(indici): ROD sul debito finanziario medio (#61 S11)`

---

### Task 12: I2 — leva finanziaria = totale attivo / patrimonio netto

**Files:**
- Modify: `calculations/ratios.py:75,512-517`, `backend/app/schemas/calculations.py:90` (commento), `calculations/report_indicators.py:259,286` (denominatore: resta `equity`; formula «Totale attivo / patrimonio netto»)
- Modify: `frontend/app/analysis/page.tsx:1064-1068` (`formula="TA/CN"`, formato **rapporto** come nel report, non percentuale: usa il formatter dei rapporti che la pagina usa per `leverage_ratio` alle righe 655-663)
- Modify: `tests/test_dossier_catalog_allegati_dg.py:187-200` se legge il valore, e le fixture `tests/fixtures/final_report/v2/*.json` **solo** se un test le confronta col calcolo dal vivo (verifica prima)
- Test: `tests/test_fix_rilievi_report.py`

- [ ] **Step 1: test che fallisce**
```python
def test_I2_leva_e_totale_attivo_su_pn_e_non_duplica_l_indebitamento():
    bs, inc = _statements({}, {})
    r = FinancialRatiosCalculator(bs, inc).calculate_all_ratios()
    assert r.extended_profitability.financial_leverage_effect == FinancialRatiosCalculator.round_decimal(
        bs.total_assets / bs.total_equity, 4)
    assert r.extended_profitability.financial_leverage_effect != r.solvency.leverage_ratio
```
Usa i nomi veri delle proprietà, `total_assets`/`total_equity`, del `BalanceSheet` ORM: verificali in `database/models.py`.

- [ ] **Step 2: verifica che fallisca.**

- [ ] **Step 3: implementazione**:
```python
        # Leva finanziaria = Totale attivo / Patrimonio netto (#62 S20): prima era (PC+PF)/CN, cioe' debiti/PN,
        # numericamente identica all'Indice di indebitamento accanto.
        financial_leverage_effect = self.safe_divide(self.bs.total_assets, self.bs.total_equity)
```
Poi esegui `node tools/final_report/export_catalog.cjs --check` e verifica se il catalogo contiene la formula. Se
cambia, rigeneralo senza `--check` e committalo.

- [ ] **Step 4: verifica che passino** il file, `tests/test_dossier_catalog_allegati_dg.py`, `tests/test_calculations.py` e `npm test`.

- [ ] **Step 5: commit** — `fix(indici): leva finanziaria = totale attivo / PN (#62 S20)`

---

### Task 13: I3 — indicatori del periodo infrannuale anche annualizzati, nel Business plan

**Files:**
- Modify: `backend/app/renderers/business_plan/data.py:355-381,455-470,560-590` (le righe `_START_IND` e Allegato D con la colonna `adj`)
- Test: `tests/test_bp_data.py` oppure un nuovo `tests/test_bp_annualizzati.py`, con `BusinessPlanData` costruito a mano come in `tests/test_bp_narrative.py:11-15`

Regola, dalla spec I3: per il periodo `adj` (period_months = m < 12), accanto a PFN/EBITDA e ROI «del periodo» compaiono
due righe: «PFN/EBITDA annualizzato» = `pfn_ebitda × m / 12` (la PFN è uno stock, l'EBITDA × 12/m) e «ROI
annualizzato» = `roi × 12 / m`. Le colonne di 12 mesi (chiusura, piano) ripetono il valore. Il report infrannuale
ReportLab annualizza già (`crisi_service`): non si tocca. Nemmeno il dossier Typst si tocca, perché è staccato
dall'interfaccia.

- [ ] **Step 1: test che fallisce.** Partendo da un `adj` con `period_months=6`, `pfn_ebitda=10.76` e `roi=4`, le righe
annualizzate valgono 5,38 e 8. Leggi in `data.py:455-470` come si costruiscono le righe di `_START_IND`, poi scrivi il
test sul risultato (`AssumptionRow`/riga di tabella) con la stessa struttura.

- [ ] **Step 2: verifica che fallisca.**

- [ ] **Step 3: implementazione.** Aggiungi le due righe dopo le originali, solo quando `adj` esiste e
`adj.period_months < 12`. Etichette: «PFN / EBITDA (annualizzato)» e «ROI (annualizzato)». Le righe originali diventano
«… (periodo)» solo nella colonna `adj`, se l'intestazione lo consente; altrimenti aggiorna la nota a 465-466: «Per il
periodo di {m} mesi gli indicatori reddituali compaiono sia sul periodo sia annualizzati (× 12/{m}).»

- [ ] **Step 4: verifica che passino** il nuovo test e `tests/test_bp_*.py`.

- [ ] **Step 5: commit** — `feat(report): PFN/EBITDA e ROI del periodo anche annualizzati (#62 S22)`

---

### Task 14: R2 + R4 + avvisi — sezione 10 completa, nota IVA, avvisi del motore

**Files:**
- Modify: `backend/app/renderers/business_plan/data.py:281-298` (`_ASSUMPTIONS`), `:319-332` (`_assumptions`), `:551-557` (riga «Rimborso debito»)
- Modify: `backend/app/renderers/business_plan/sections_partenza.py:70-100`
- Modify: `backend/app/services/final_report_assumptions.py` solo se serve una label nuova
- Test: `tests/test_bp_data.py` (DB reale, salta senza), oppure un test con `rilievi_kit.genera(..., report=True)` che dà `e.data`

Regole, dalla spec R2:
1. **Inventario.** Elenca nel commit e nel report del task i campi dei passi 1-7 (`frontend/lib/budget-wizard-steps.ts`, la mappa dei campi per passo) e, per ognuno, se arriva in sezione 10. Ogni campo non vuoto deve comparire: o come riga di `_ASSUMPTIONS`, o in una tabella «Finanziamenti» (`financing_loans`: nome, importo/residuo, **tasso** `interest_rate`, durata), o come riga calcolata.
2. **Proventi finanziari**: riga calcolata «Proventi finanziari» = `ce13 + ce14` per anno di piano (`"proventi_fin"` in `data.py:156`).
3. **Tasso del finanziamento esistente**: dalla tabella Finanziamenti (punto 1), una riga per contratto con `opening_residual > 0`.
4. **Righe tutte a zero**: una riga calcolata («Rimborso debito», ecc.) che vale zero in **ogni** anno non esce. Una riga d'input a zero resta, se l'utente l'ha scritta: si distingue con `provenance` di `AssumptionValue`, che vale `"automatic"` quando tutto è `None`. Verifica.
5. **Nota IVA (R4)**, sotto la tabella dei driver: «I giorni si applicano a ricavi e acquisti al netto dell'IVA; i saldi di crediti e debiti del bilancio sono al lordo. Un DSO/DPO misurato sui saldi storici risulta quindi più alto di quello effettivo.»
6. **Avvisi del motore**: sotto, un riquadro «Avvisi del motore» con le frasi di `engine_meta['avvisi']` di tutti gli anni di piano, deduplicate, se ce ne sono. Verifica come il report riceve `engine_meta` (`final_report_service.py:606-609`) e portalo in `BusinessPlanData`, per esempio con un campo `avvisi: tuple[str, ...]`.

- [ ] **Step 1: test che falliscono**, con `genera(rows, report=True)`:
```python
def test_R2_sezione_10_completa_e_senza_righe_a_zero():
    rows = righe(financing_loans=[{"name": "Fin. A", "opening_residual": 100000, "duration_years": 5,
                                   "interest_rate": 4}])
    e = generato(genera(rows, report=True))
    etichette = [r.label for r in e.data.assumptions]
    assert "Proventi finanziari" in etichette
    assert not any(r.label == "Rimborso debito" and all((v or 0) == 0 for v in r.values) for r in e.data.assumptions)
    assert any("4" in str(c) for c in e.data.finanziamenti_tabella)  # nome del campo da fissare nell'implementazione

def test_R2_avvisi_del_motore_arrivano_al_report():
    e = generato(genera(righe(dio_days=25), report=True))
    assert any("magazzino" in a for a in e.data.avvisi)
```
Se `financing_loans` richiede altri campi, il bulk risponde 422 con `detail.errori`: leggili e completa la riga.
`finanziamenti_tabella` è il nome scelto qui per il campo nuovo di `BusinessPlanData`. Se trovi una struttura già
esistente per i finanziamenti, riusala e aggiorna il test.

- [ ] **Step 2: verifica che falliscano.**

- [ ] **Step 3: implementazione** dei punti 1-6. Aggiorna `tests/test_bp_data.py:68` e
`tests/test_dossier_catalog_piano.py:107`, che si aspetta «Rimborso debito», **solo** se il fallimento è dovuto alla
regola 4 (righe tutte a zero).

- [ ] **Step 4: verifica che passino** `tests/test_bp_*.py`, `tests/test_dossier_catalog_piano.py`, `tests/test_m1_05b_assumption_sections.py`. Genera un PDF da uno scenario di prova e guardalo: la regola di CLAUDE.md è che un layout di stampa si controlla generando il PDF.

- [ ] **Step 5: commit** — `feat(report): sezione 10 completa, nota IVA e avvisi del motore (#61 S15, #62 S24)`

---

### Task 15: R3 — testi automatici del Business plan

**Files:**
- Modify: `backend/app/renderers/business_plan/narrative.py:153-168,214-222,381-389`
- Test: `tests/test_bp_narrative.py` (fixture `AMBIENTA` alle righe 20-34, `make(values, growth)`)

Regole, dalla spec R3, sulle chiavi già disponibili per colonna (`debiti_finanziari` = debito lordo, `cf_nuovo_debito`,
`cf_operativo`, `cf_investimenti`, `cf_rimborsi`, `cf_variazione`):
- «deleveraging» (lead a 160, titolo «Rapido deleveraging» a 222) solo se `debiti_finanziari` ultimo < primo. Se scende la sola PFN: lead «Generazione di cassa e riduzione della PFN per accumulo di liquidità.» e titolo «Riduzione della PFN per accumulo di liquidità».
- `subtitle_flussi`: «genera cassa in ogni anno, sufficiente a finanziare investimenti e rimborsi» solo se per ogni anno di piano `cf_operativo ≥ |cf_investimenti| + cf_rimborsi`. Se la variazione è ≥ 0 grazie a nuovo debito: «La cassa non scende in nessun anno, sostenuta da nuovi finanziamenti per {_eur_per_anno(cf_nuovo_debito)}.» Negli altri casi resta il testo di oggi.

- [ ] **Step 1: test che falliscono**
```python
def test_R3_niente_deleveraging_se_il_debito_lordo_non_scende():
    vals = {**AMBIENTA, "debiti_finanziari": [D(500), D(500), D(500), D(500)], "pfn": [D(400), D(300), D(200), D(100)]}
    testo = " ".join(narrative.key_points(make(vals, GROWTH)))  # adatta a ciò che key_points restituisce
    assert "deleveraging" not in testo.lower()
    assert "accumulo di liquidità" in testo

def test_R3_cassa_sostenuta_dal_nuovo_finanziamento_lo_dice():
    vals = {**AMBIENTA, "cf_variazione": [None, D(10), D(10), D(10)], "cf_operativo": [None, D(5), D(5), D(5)],
            "cf_investimenti": [None, D(-50), D(-50), D(-50)], "cf_rimborsi": [None, D(0), D(0), D(0)],
            "cf_nuovo_debito": [None, D(55), D(55), D(55)]}
    s = narrative.subtitle_flussi(make(vals, GROWTH))
    assert "sufficiente a finanziare" not in s and "nuovi finanziamenti" in s
```
Leggi `tests/test_bp_narrative.py:1-40` per la forma esatta di `AMBIENTA`, `make` e `GROWTH`, e adegua i nomi.

- [ ] **Step 2: verifica che falliscano.** **Step 3: implementazione.** **Step 4: verifica che passino** `tests/test_bp_narrative.py`, `tests/test_fix_rilievi_narrativa.py`.

- [ ] **Step 5: commit** — `fix(report): deleveraging solo sul debito lordo, cassa e nuovi finanziamenti (#61 S17)`

---

### Task 16: R4 + R5 nel wizard — nota IVA nel passo 4, etichetta della cassa dal circolante

**Files:**
- Modify: `frontend/components/budget/wizard/steps/StepCircolante.tsx:61-65` (aggiungi la frase IVA al `<p>`)
- Modify: `frontend/lib/budget-preview-rows.ts:302` (etichetta «cassa liberata (+) / assorbita (−) dal circolante»)
- Verifica: `frontend/lib/budget-circolante-step.ts:249` e `frontend/lib/budget-piano-step.ts:323` dicono «Costante» per `sp06g`, e dopo il Task 4 è vero. Nessuna modifica, ma un test che lo fissi.
- Test: `frontend/lib/budget-preview-rows.test.ts:236-258`

- [ ] **Step 1: test che fallisce.** In `rowsCircolante`, la riga `cassa` ha label `"cassa liberata (+) / assorbita (−) dal circolante"` e lo stesso valore di oggi (−40 nel caso esistente).
- [ ] **Step 2: verifica che fallisca.** **Step 3: implementazione.** **Step 4:** `npm test`, poi `npx next build`.
- [ ] **Step 5: commit** — `fix(wizard): etichetta della cassa dal circolante e nota IVA sui giorni (#61 S27, #62 S24)`

---

### Task 17: documentazione, banco di parità, suite, build

**Files:**
- Modify: `CLAUDE.md`. Bullet da aggiornare: «Un solo DSO» (il motore ora governa `sp06a+sp07a`), «DIO sul consumo di materie» e B01 in «Forecasting Engine» (due gruppi, `ce02`/`ce03` dallo SP, `dio_pf_days`), «Indice di indebitamento» (la leva ora è TA/PN), ROD (media), B03/TFR (`ce08` = somma delle componenti), imposte a saldo + acconto (compensazione del credito storico a scelta), riserva legale (bullet nuovo in Previsionale), «Il rendiconto ha una riga propria per la posizione tributaria» (imposte pagate = versamenti), avvisi del motore (`details['avvisi']`, `engine_meta['avvisi']`).
- Modify: `docs/budget/FORECASTING_GUIDE.md`, `docs/budget/API-PREVISIONALE.md` (le colonne `dio_pf_days` e `compensa_crediti_tributari`)
- Modify: `docs/superpowers/specs/2026-10-05-rilievi-ambienta-61-62-design.md`. I1: niente reason `rod_saldo_fine_anno`, la prima colonna lo dichiara nella formula. I3: annualizzati nel Business plan, perché il report infrannuale già annualizza. Avvisi: canale unico `details['avvisi']`. M4: «cash_out» è descrittivo, la cassa resta il plug.

- [ ] **Step 1:** `PYTHONPATH=.:backend backend/venv/bin/python -m pytest tests -q -p no:cacheprovider -p no:warnings`. Expected: tutto verde. I fallimenti noti e preesistenti si confrontano con `main`, eseguendo la stessa suite in un worktree di `main`.
- [ ] **Step 2:** `backend/venv/bin/python scripts/parita_motore.py main HEAD --json <scratch>/parita.json --log <scratch>/parita.log`. Ogni scenario che si muove deve muoversi per una delle regole M1–M7, e il report del task lo motiva per famiglia.
- [ ] **Step 3:** `cd frontend && npm test && npx next build`.
- [ ] **Step 4:** migrazione del DB locale e rigenerazione dello scenario AMBIENTA 18 dal backend: le accettazioni della spec misurate dal vivo (DSO 90,0 con 90 in input; `ce08d` 2027; riserva legale 2027; leva 2026; avviso sul magazzino). I numeri vanno nel report.
- [ ] **Step 5: commit** — `docs: CLAUDE.md e guide allineate ai rilievi #61 #62`

---

## Dopo i task

1. Revisione finale dell'intero branch con un subagente **opus** (memoria «scelta-modello-subagenti»).
2. Merge su `main` secondo `superpowers:finishing-a-development-branch`. Prima del push serve `next build`.
3. Commento di chiusura su #61 e #62: punto per punto che cosa è cambiato, dove ci si discosta dai tester (S11 perimetro, S14 compensazione orizzontale degli acconti, S18 compensazione invece della riclassifica) e la nota per chi ritesta («Salva e Calcola Previsionale»; il DIO va reinserito in due gruppi). Il testo si mostra al proprietario prima di pubblicarlo.
4. Un'issue nuova per l'import che mette tutte le rimanenze su `sp05a` senza dettaglio (fuori perimetro).

---

**Superato dall'esecuzione (2026-10-05).** Il codice del Task 3 Step 3 è stato ristretto da
`33f3bc0` (fix finale 4, pinato da `fac439c`): il ramo «componenti» scatta solo con `prev_b > 0`
(salari), non `(prev_b + prev_c + prev_d) > 0` — senza salari il TFR cadrebbe sul ripiego del 70%
sopra oneri e altri costi. Stato attuale: blocco Personnel di `calculations/forecast_engine.py`
e CLAUDE.md §«Lotto 1 fix rilievi».
