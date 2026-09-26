# Fix rilievi AMBIENTA · Lotto 1 (motore) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** chiudere nel motore del previsionale i rilievi B01, B02, B03, B05, A04, E05 e persistere firma del motore e `pareggio` sul `ForecastYear`.

**Architecture:** ogni rilievo ha già il suo oracolo in `tests/test_rilievi_ambienta.py` (marcato `xfail(strict=True)`): il fix lo fa passare e toglie il marcatore. Le regole nuove vivono in funzioni pure (in `calculations/projection_common.py` o a livello di modulo in `calculations/forecast_engine.py`) con test unitari propri; il motore le chiama e dichiara in `details` ciò che ha fatto.

**Tech Stack:** Python 3 + SQLAlchemy (SQLite), `Decimal`, pytest; un ritocco Next.js/TypeScript (Vitest) nei Task 5 e 7.

**Spec:** `docs/superpowers/specs/2026-09-26-fix-rilievi-ambienta-design.md` (§3 Lotto 1, §4 Verifica).

## Global Constraints

- Worktree `/home/peter/DEV/budget-fix-rilievi`, branch `fix/rilievi-ambienta`. Mai toccare `/home/peter/DEV/budget` (albero principale). Niente push.
- Python: `../budget/backend/venv/bin/python -m pytest …` lanciato dalla radice del worktree. Frontend: `cd frontend && npx vitest run <file>` e `npx tsc --noEmit`; `npm run build` se si tocca un `.tsx`.
- Test solo in memoria (`tests/e2e_kit.memory_sessions`, `tests/rilievi_kit.genera`) o su una **copia** del DB. Mai `financial_analysis.db` vivo.
- Niente bilanci inventati: la base è `tests/fixtures/ambienta_2026.json` (regola del proprietario, `tests/test_bp_data.py`).
- Soldi in `Decimal`, mai `float`. Una chiave diagnostica si dichiara **sempre**, anche a zero/`None`.
- File con fine riga misti: solo modifiche additive/locali; `git diff --stat` prima di ogni commit (un diff gonfiato = line endings rovinati → ripristina e rifai).
- Un test esistente che fissa il comportamento **vecchio** che la spec cambia si aggiorna nello stesso commit, con un commento `# lotto 1 fix rilievi (2026-09-26): <regola>`; l'elenco dei test aggiornati va nel messaggio di commit. Un test che cambia per altre ragioni è un difetto: fermati e segnalalo.
- Togliere il marcatore `xfail` di un rilievo quando il fix lo fa passare (lo `strict` lo impone).
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Testi in italiano; commenti nello stile del file (italiano, spiegano il perché).

## Review Focus

- Override di CE sulle righe toccate (`ce08_override`, `ce08a_override`, `ce09a/b_override`, `ce10_override`, `ce18/19_override`): l'override vince e lo SP resta coerente (niente differenza assorbita in silenzio dalla cassa). Test nei Task 2, 3, 4, 5.
- Base abbreviata senza sotto-voci (solo `sp05`, solo `sp03`, solo `ce08`): nessuna divisione per zero, nessuna massa persa. Test nei Task 3 e 5.
- `sp_overrides` su `sp03`/`sp05a` in un anno: l'anno dopo riparte dal persistito, gli ammortamenti non superano il netto disponibile. Test nel Task 3.
- Contratto scadenziato a mano che copre esplicitamente l'anno dopo con 0: lo zero vince, nessuna rata ripetuta. Test nel Task 6.
- Piano crediti oltre 12 mesi con massa che **cresce** (nessun incasso): riparto proporzionale di sempre. Test nel Task 7.

---

### Task 1: firma del motore e `pareggio` persistiti

**Files:**
- Modify: `database/models.py` (classe `ForecastYear`, ~782-801)
- Modify: `migrate_db.py` (`MIGRATIONS`)
- Modify: `calculations/forecast_engine.py` (costante in testa al modulo; `generate_forecast` ~2720-2810)
- Modify: `tests/rilievi_kit.py` (`Esito.meta`)
- Test: `tests/test_engine_meta.py` (nuovo)

**Interfaces:**
- Produces: `forecast_engine.ENGINE_VERSION: str = "2"`; `forecast_engine.engine_meta(details: dict) -> dict` che restituisce `{"engine_version": ENGINE_VERSION, "pareggio": {chiave: str(Decimal quantizzato a 0.01) | None}}`; colonna `ForecastYear.engine_meta` (JSON, nullable); `Esito.meta: dict[int, dict | None]` (anno → `engine_meta` persistito). Il lotto 2 legge `engine_meta["pareggio"]` e confronta `int(engine_meta["engine_version"])` con `int(ENGINE_VERSION)`.

- [ ] **Step 1: test che falliscono.** Crea `tests/test_engine_meta.py`:

```python
"""Firma del motore e pareggio persistiti sul ForecastYear (spec fix rilievi 2026-09-26 §3, lotto 1)."""
from decimal import Decimal as D

from calculations.forecast_engine import ENGINE_VERSION, engine_meta
from tests.rilievi_kit import genera, generato, righe


def test_engine_meta_serializza_il_pareggio_in_stringhe():
    meta = engine_meta({"pareggio": {"costi_variabili": D("10.005"), "fatturato_pareggio": None}})
    assert meta == {"engine_version": ENGINE_VERSION,
                    "pareggio": {"costi_variabili": "10.01", "fatturato_pareggio": None}}


def test_engine_meta_senza_pareggio_dichiara_none():
    assert engine_meta({}) == {"engine_version": ENGINE_VERSION, "pareggio": None}


def test_ogni_anno_generato_porta_firma_e_pareggio_del_motore():
    e = generato(genera(righe()))
    assert set(e.meta) == {2027, 2028, 2029}
    for anno, meta in e.meta.items():
        assert meta["engine_version"] == ENGINE_VERSION == "2"
        atteso = {k: (None if v is None else str(D(str(v)).quantize(D("0.01"))))
                  for k, v in e.det[anno]["pareggio"].items()}
        assert meta["pareggio"] == atteso, anno
```

- [ ] **Step 2:** `../budget/backend/venv/bin/python -m pytest tests/test_engine_meta.py -q` → FAIL (ImportError su `ENGINE_VERSION`).

- [ ] **Step 3: implementazione.**
  - `database/models.py`, in `ForecastYear` dopo `updated_at`:
    ```python
    # Firma della generazione (spec fix rilievi 2026-09-26): versione del motore che ha prodotto
    # questi numeri e il punto di pareggio dichiarato. NULL = generato prima della firma, cioè
    # «non lo so» — mai un verdetto negativo.
    engine_meta = Column(JSON, nullable=True)
    ```
  - `migrate_db.py`, in `MIGRATIONS`: `"forecast_years": [("engine_meta", "JSON")],` (se la chiave `forecast_years` esiste già, aggiungi la tupla alla sua lista).
  - `calculations/forecast_engine.py`, dopo gli import:
    ```python
    # Si incrementa a ogni cambiamento dei numeri che il motore produce a parità di ipotesi: un
    # ForecastYear con una versione più vecchia è un previsionale da rigenerare (lotto 2, A01-bis).
    ENGINE_VERSION = "2"


    def engine_meta(details: Dict[str, Any]) -> Dict[str, Any]:
        """La firma persistita su `ForecastYear.engine_meta`: JSON puro, importi come stringhe al centesimo."""
        pareggio = details.get('pareggio')
        if pareggio is not None:
            pareggio = {k: (None if v is None else str(Decimal(str(v)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)))
                        for k, v in pareggio.items()}
        return {'engine_version': ENGINE_VERSION, 'pareggio': pareggio}
    ```
  - In `generate_forecast`, subito dopo il blocco `if not fy: … else: fy.updated_at = …`: `fy.engine_meta = engine_meta(result.details)`.
  - `tests/rilievi_kit.py`: aggiungi `meta: dict` in fondo a `Esito`; in `genera`, dopo `anni = …`, leggi `meta = {fy.year: fy.engine_meta for fy in db.query(ForecastYear).filter(ForecastYear.scenario_id == sc.id)}` (import `ForecastYear` da `database.models`) e passalo a `Esito(res, anni, det, data, rep, meta)`.

- [ ] **Step 4:** stesso comando → PASS (3 test). Poi `../budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py -q` → 19 passed, 16 xfailed (invariato).

- [ ] **Step 5: migrazione su una copia.** `cp /home/peter/DEV/budget/financial_analysis.db /tmp/claude-1000/-home-peter-DEV-budget/c84cb587-b7a2-4376-a794-7618627d4d71/scratchpad/copia.db && ../budget/backend/venv/bin/python migrate_db.py /tmp/claude-1000/-home-peter-DEV-budget/c84cb587-b7a2-4376-a794-7618627d4d71/scratchpad/copia.db` → Expected: una riga `ADD   forecast_years.engine_meta`; seconda esecuzione → nessun `ADD` per quella colonna. (Se `migrate_db.py` legge il percorso diversamente, leggilo in testa al file e adegua il comando; mai sul DB vivo.)

- [ ] **Step 6: commit** `feat(motore): firma del motore e pareggio persistiti sul ForecastYear`.

---

### Task 2: B03 — TFR = retribuzioni / 13,5

**Files:**
- Modify: `calculations/forecast_engine.py` (`_calculate_income_statement`, righe ~3001-3006)
- Test: `tests/test_rilievi_ambienta.py` (togli marcatore B03), `tests/test_fix_rilievi_motore.py` (nuovo, condiviso dai task 2-7)

**Interfaces:**
- Produces: `details['personale_ricomposto']`, sempre dichiarato: `None` quando i quattro sotto-conti stanno nel totale; altrimenti `{'ce08_ipotesi': Decimal, 'ce08': Decimal, 'eccedenza': Decimal, 'tfr_limitato': bool}`.

Regola (spec §3 B03): `ce08a = tfr_accrual_quota(ce08b, ce08)` (salvo `ce08a_override`); `ce08d = ce08 − ce08a − ce08b − ce08c` (salvo `ce08d_override`). Se il resto è negativo:
- **senza** `ce08_override`: `ce08d = 0` e `ce08 = ce08a + ce08b + ce08c`; dichiara `{'ce08_ipotesi': ce08 di prima, 'ce08': nuovo, 'eccedenza': −resto, 'tfr_limitato': False}`;
- **con** `ce08_override` (il totale forzato vince): `ce08a = max(0, ce08 − ce08b − ce08c)` (come oggi), `ce08d = 0`, dichiara `{'ce08_ipotesi': ce08, 'ce08': ce08, 'eccedenza': −resto, 'tfr_limitato': True}`.
Il blocco `details` è `if details is not None:`.

- [ ] **Step 1: test.** Crea `tests/test_fix_rilievi_motore.py`:

```python
"""Test unitari e di regola dei fix del lotto 1 (spec fix rilievi AMBIENTA 2026-09-26 §3)."""
from decimal import Decimal as D

from tests.rilievi_kit import BASE_CE, genera, generato, per_anno, righe


def test_B03_personale_ricomposto_quando_il_tfr_sfonda_il_totale():
    # Sulla base AMBIENTA salari/13,5 + salari + oneri supera il totale del personale:
    # il totale si ricompone come somma e lo si dichiara.
    e = generato(genera(righe()))
    ce, det = e.anni[2027][1], e.det[2027]["personale_ricomposto"]
    somma = ce["ce08a_tfr_accrual"] + ce["ce08b_salari_stipendi"] + ce["ce08c_oneri_sociali"]
    assert ce["ce08d_altri_costi_personale"] == D("0.00")
    assert ce["ce08_costi_personale"] == somma
    assert det["tfr_limitato"] is False and D(str(det["eccedenza"])) > 0


def test_B03_override_del_totale_vince_e_limita_il_tfr():
    rows = righe(ce08_override=2344742)
    e = generato(genera(rows))
    ce, det = e.anni[2027][1], e.det[2027]["personale_ricomposto"]
    assert ce["ce08_costi_personale"] == D("2344742.00")
    assert ce["ce08a_tfr_accrual"] + ce["ce08b_salari_stipendi"] + ce["ce08c_oneri_sociali"] \
        + ce["ce08d_altri_costi_personale"] == D("2344742.00")
    assert det["tfr_limitato"] is True


def test_B03_nessuna_ricomposizione_dichiarata_quando_il_totale_regge():
    # Oneri sociali azzerati: salari/13,5 + salari sta sotto il totale.
    e = generato(genera(righe(), ce={"ce08c_oneri_sociali": D("0"),
                                     "ce08d_altri_costi_personale": D("491380.40")}))
    assert e.det[2027]["personale_ricomposto"] is None
    ce = e.anni[2027][1]
    assert abs(ce["ce08a_tfr_accrual"] - ce["ce08b_salari_stipendi"] / D("13.5")) < D("0.01")
```

(Il terzo test sposta nella base 453.027,54 da `ce08c` a `ce08d` lasciando invariato `ce08`: il totale della base resta quello del bilancio, nessun bilancio inventato.)

- [ ] **Step 2:** togli il marcatore `xfail` di `test_B03_tfr_uguale_retribuzioni_diviso_13_5`. Esegui `../budget/backend/venv/bin/python -m pytest tests/test_fix_rilievi_motore.py tests/test_rilievi_ambienta.py -k B03 -q` → FAIL (B03 del triage e i nuovi).

- [ ] **Step 3:** implementa la regola sopra al posto delle righe 3005-3006 (il commento sopra le righe va riscritto: niente più «cap at the remainder»).

- [ ] **Step 4:** stesso comando → PASS. Poi la suite intera (`-q -p no:warnings > $SCRATCH/t2.txt`, leggi la coda): ogni test rotto va classificato (Global Constraints). Expected: rotture solo su test che fissano il vecchio `ce08a` capato/`ce08d` di resto.

- [ ] **Step 5: commit** `fix(motore): B03 TFR = retribuzioni / 13,5, personale ricomposto e dichiarato`.

---

### Task 3: B02 + E05 — ammortamenti per masse separate, metà aliquota nel primo anno

**Files:**
- Modify: `calculations/projection_common.py` (funzione pura nuova)
- Modify: `calculations/forecast_engine.py` (`_calculate_income_statement`, blocco ~3008-3064)
- Test: `tests/test_fix_rilievi_motore.py`, `tests/test_rilievi_ambienta.py` (togli marcatore B02; riscrivi `test_E05_caratterizzazione_ammortamento_primo_anno_e_straordinari`)

**Interfaces:**
- Produces: `projection_common.ammortamento_categoria(stato_apertura: dict | None, netto_apertura: Decimal, quota_base: Decimal, investimento: Decimal, aliquota: Decimal, anno: int, override: Decimal | None, dismissione: Decimal = ZERO) -> tuple[Decimal, dict]` → `(quota_dell_anno, stato_chiusura)`; `stato` = `{'esistente_apertura', 'quota_esistente', 'esistente_residuo', 'quota_nuovi', 'cespiti_nuovi': [{'anno', 'importo', 'aliquota', 'residuo'}], 'override': bool, 'limitato_al_netto': bool}` (Decimal grezzi). `details['ammortamenti'] = {'immateriali': stato, 'materiali': stato}`, sempre dichiarato.

Regole (spec §3 B02, E05):
- Anno 1 (`stato_apertura is None`): `esistente_apertura = netto_apertura` (sp02/sp03 dell'anno prima), nessun cespite nuovo. Anni dopo: `esistente_apertura = stato_apertura['esistente_residuo']`, cespiti nuovi dallo stato.
- Se l'anno ha `investimento > 0`, entra un cespite `{'anno': anno, 'importo': investimento, 'aliquota': aliquota, 'residuo': investimento}`.
- `quota_esistente = min(quota_base, esistente_apertura)` (`quota_base` = `ce09a`/`ce09b` dell'**anno base**).
- Per cespite nuovo: `piena = importo × aliquota` (aliquota del suo anno d'ingresso, frazione); nell'anno d'ingresso `piena / 2`; `quota = min(quella, residuo)`.
- `quota = quota_esistente + Σ quote nuovi`, poi guardia: `netto_apertura + investimento` è il massimo (un `sp_overrides` sullo SP può averlo abbassato); se la somma lo supera, `limitato_al_netto = True` e si procede come con un override di quell'importo.
- Override (o guardia): l'importo si toglie prima dall'esistente fino al suo residuo, poi dai cespiti nuovi in ordine d'ingresso; `override = True` solo per l'override vero.
- Dismissione (`asset_disposal_nbv`, solo materiali): dopo le quote, si toglie dal residuo esistente e poi dai nuovi in ordine, mai sotto zero.
- `ce09a`/`ce09b` = la quota; lo SP resta `prev + investimento − quota` (invariato).

- [ ] **Step 1: test** (in `tests/test_fix_rilievi_motore.py`):

```python
from calculations.projection_common import ammortamento_categoria


def test_ammortamento_esistente_si_ferma_al_residuo():
    q, s = ammortamento_categoria(None, D("100"), D("60"), D("0"), D("0.1"), 2027, None)
    assert q == D("60") and s["esistente_residuo"] == D("40")
    q, s = ammortamento_categoria(s, D("40"), D("60"), D("0"), D("0.1"), 2028, None)
    assert q == D("40") and s["esistente_residuo"] == D("0")


def test_nuovo_cespite_a_meta_aliquota_nell_anno_d_ingresso():
    q, s = ammortamento_categoria(None, D("0"), D("0"), D("1000"), D("0.1"), 2027, None)
    assert q == D("50")
    q, s = ammortamento_categoria(s, D("950"), D("0"), D("0"), D("0.2"), 2028, None)
    assert q == D("100")  # aliquota del suo anno d'ingresso (10%), piena


def test_override_consuma_prima_l_esistente():
    q, s = ammortamento_categoria(None, D("100"), D("60"), D("1000"), D("0.1"), 2027, D("130"))
    assert q == D("130") and s["override"] is True
    assert s["esistente_residuo"] == D("0") and s["cespiti_nuovi"][0]["residuo"] == D("970")


def test_quota_limitata_al_netto_disponibile():
    stato = {"esistente_residuo": D("100"), "cespiti_nuovi": []}
    q, s = ammortamento_categoria(stato, D("30"), D("60"), D("0"), D("0.1"), 2028, None)
    assert q == D("30") and s["limitato_al_netto"] is True


def test_E05_metà_aliquota_e_B02_sul_motore():
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 100000
    e = generato(genera(rows))
    assert e.anni[2027][1]["ce09b_ammort_materiali"] == D("36040.00") + D("5000.00")
    assert e.det[2027]["ammortamenti"]["materiali"]["quota_nuovi"] == D("5000")


def test_base_senza_quote_dettagliate_non_ammortizza_l_esistente():
    # Base abbreviata: ammortamenti solo nell'aggregato ce09. Nessuna quota esistente da portare
    # (come oggi), nessuna divisione per zero.
    e = generato(genera(righe(), ce={"ce09a_ammort_immateriali": D("0"), "ce09b_ammort_materiali": D("0"),
                                     "ce09d_svalutazione_crediti": D("75264.00")}))
    assert e.anni[2027][1]["ce09b_ammort_materiali"] == D("0.00")


def test_override_sp03_l_anno_prima_limita_la_quota():
    rows = righe(depreciation_rate=10)
    rows[0]["sp_overrides"] = {"sp03_immob_materiali": 1000}
    e = generato(genera(rows))
    assert e.anni[2028][1]["ce09b_ammort_materiali"] <= D("1000.00")
```

Riscrivi in `tests/test_rilievi_ambienta.py` il test E05 dell'ammortamento come oracolo (non più caratterizzazione):

```python
def test_E05_ammortamento_a_meta_aliquota_nel_primo_anno():
    """E05 · decisione del proprietario (2026-09-26): un investimento si ammortizza a metà aliquota
    nell'anno in cui entra. Investimento 2027 di 100.000 al 10%: quota 2027 del nuovo = 5.000."""
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 100000
    e = generato(genera(rows))
    quota_nuovo = e.anni[2027][1]["ce09b_ammort_materiali"] - BASE_CE["ce09b_ammort_materiali"]
    assert quota_nuovo == D("5000.00")
```

e togli il marcatore di `test_B02_ammortamento_dei_cespiti_esistenti_si_ferma_al_residuo` (l'oracolo 25.716,59 non cambia con la metà aliquota: nel 2029 il nuovo è a quota piena).

- [ ] **Step 2:** `pytest tests/test_fix_rilievi_motore.py tests/test_rilievi_ambienta.py -k "ammort or B02 or E05" -q` → FAIL.

- [ ] **Step 3:** implementa `ammortamento_categoria` in `projection_common.py` (docstring: la regola sopra). In `_calculate_income_statement` sostituisci il calcolo `ce09a`/`ce09b` (da `prev_ce09a = …` fino agli `if assumption.ce09b_override …`) con due chiamate: stato d'apertura da `(prev_details or {}).get('ammortamenti', {}).get('immateriali'|'materiali')`, `netto_apertura = _prev_bs_val('sp02…'|'sp03…')`, `quota_base = base_ce09a|base_ce09b`, investimenti da `_get_split_investments`, aliquote `depreciation_rate_intangible|depreciation_rate` / 100, `override = assumption.ce09a_override|ce09b_override`, `dismissione = asset_disposal_nbv` solo per i materiali. Dichiara `details['ammortamenti']` se `details is not None`. Verifica che `prev_details` arrivi a questa funzione anche dal percorso di preview (`compute_forecast`).

- [ ] **Step 4:** stesso comando → PASS; suite intera, classifica le rotture (attese: test che fissano quota piena nel primo anno o la vecchia catena `prev_ce09 + nuovo`).

- [ ] **Step 5: commit** `fix(motore): B02 ammortamenti per masse separate, E05 metà aliquota nel primo anno`.

---

### Task 4: E05 — proventi e oneri straordinari a zero nel piano

**Files:**
- Modify: `calculations/forecast_engine.py` (~3151-3152)
- Test: `tests/test_rilievi_ambienta.py` (riscrivi `test_E05_caratterizzazione_straordinari_ripetuti_ogni_anno`), `tests/test_fix_rilievi_motore.py`

- [ ] **Step 1: test.** In `tests/test_rilievi_ambienta.py` sostituisci il test degli straordinari con:

```python
def test_E05_straordinari_a_zero_nel_piano():
    """E05 · decisione del proprietario (2026-09-26): proventi e oneri straordinari della base non si
    proiettano; valgono zero in ogni anno di piano, salvo override."""
    straord = {"ce18_proventi_straordinari": D("1234.00"), "ce19_oneri_straordinari": D("1234.00")}
    e = generato(genera(righe(), ce=straord))
    for y in (2027, 2028, 2029):
        ce = e.anni[y][1]
        assert (ce["ce18_proventi_straordinari"], ce["ce19_oneri_straordinari"]) == (D("0.00"), D("0.00")), y
```

e in `tests/test_fix_rilievi_motore.py`:

```python
def test_E05_override_degli_straordinari_vince():
    e = generato(genera(righe(ce18_override=500, ce19_override=200)))
    ce = e.anni[2027][1]
    assert (ce["ce18_proventi_straordinari"], ce["ce19_oneri_straordinari"]) == (D("500.00"), D("200.00"))
```

- [ ] **Step 2:** `pytest … -k "E05" -q` → FAIL sul primo.
- [ ] **Step 3:** `ce18 = assumption.ce18_override if … is not None else Decimal('0')`, idem `ce19`, con un commento che cita la decisione.
- [ ] **Step 4:** PASS; suite intera, classifica.
- [ ] **Step 5: commit** `fix(motore): E05 straordinari a zero negli anni di piano`.

---

### Task 5: B01 — variazione rimanenze di materie dal patrimoniale, DIO sul consumo

**Files:**
- Modify: `calculations/projection_common.py` (funzione pura nuova)
- Modify: `calculations/forecast_engine.py` (`_calculate_income_statement`: ce10 ~3094, nuovi parametri `base_bs`, `settore`; chiamante in `compute_forecast`; `_calculate_balance_sheet`: blocco DIO ~3574-3591 e riparto `sp05*` ~4493-4495)
- Modify: `frontend/lib/budget-turnover.ts` (`computeAutoDays("dio")`) e il suo test (`frontend/lib/budget-turnover.test.ts` se esiste, altrimenti nuovo)
- Test: `tests/test_fix_rilievi_motore.py`, `tests/test_rilievi_ambienta.py` (togli marcatore B01)

**Interfaces:**
- Produces: `projection_common.rimanenze_materie(apertura: Decimal, acquisti: Decimal, giorni: Decimal) -> tuple[Decimal, Decimal]` → `(chiusura, ce10)`; `details['rimanenze_materie'] = {'apertura', 'chiusura', 'giorni', 'consumo', 'derivati': bool, 'degenere': bool, 'override': bool}` sempre dichiarato; `details['dio_applied']` = i giorni delle materie.

Regole (spec §3 B01):
- Materie = `sp05a`. Se la base non ha **alcuna** sotto-voce di `sp05` (tutte zero, aggregato positivo), l'aggregato meno `sp05e` conta come materie (è lo stesso ripiego di `_alloc`, `primary_idx=0`).
- DIO sul consumo: `chiusura = consumo × giorni / 360` con `consumo = acquisti (ce05) + apertura − chiusura`, in forma chiusa `chiusura = max(0, (acquisti + apertura) × giorni / (360 + giorni))`; `ce10 = apertura − chiusura` (convenzione OIC B11: un aumento riduce il costo).
- Giorni: `dio_days` esplicito se c'è; altrimenti dedotti dalla base, `sp05a_base / (ce05_base + ce10_base) × 360`, con la stessa guardia di `_derived_days` (denominatore ≤ 0 o giorni oltre `soglia_giorni_magazzino(settore)` ⇒ degenere): degenere ⇒ `chiusura = apertura`, `ce10 = 0`, `'dio'` aggiunto a `details['degenerate_turnover_ratio']`.
- `ce10_override` vince: `ce10 = override`, `chiusura = max(0, apertura − override)` — lo SP segue il CE, niente scarto in cassa.
- Il calcolo sta nel CE (serve `ce10` prima delle imposte); lo SP legge `details['rimanenze_materie']['chiusura']` per `sp05a`. Le altre rimanenze (`sp05b`–`sp05e`) seguono i ricavi con i giorni dedotti dalla base su di loro (`(Σ base b..e) / ricavi_base × 360`, stessa guardia, nome `'dio_altre'`), ripartite fra b..e sulle proporzioni della base; `dio_days` esplicito non le tocca più. `sp05 = sp05a + Σ b..e`.
- Apertura: anno 1 = materie della base; anni dopo = `sp05a` persistito dell'anno prima (`previous_bs`).
- Nel motore la chiusura si quantizza al centesimo (`ROUND_HALF_UP`) **prima** di derivarne `ce10 = apertura − chiusura`: così `ce10` persistito = Δ `sp05a` persistito al centesimo. La funzione pura resta a precisione piena.

- [ ] **Step 1: test.**

```python
from calculations.projection_common import rimanenze_materie


def test_rimanenze_materie_forma_chiusa():
    chiusura, ce10 = rimanenze_materie(D("100"), D("260"), D("36"))
    assert chiusura == D("360") * D("36") / D("396")
    consumo = D("260") + D("100") - chiusura
    assert abs(chiusura - consumo * D("36") / D("360")) < D("0.0000001")
    assert ce10 == D("100") - chiusura


def test_rimanenze_materie_mai_negative():
    assert rimanenze_materie(D("0"), D("-10"), D("30")) == (D("0"), D("0"))


def test_B01_dio_esplicito_sul_consumo_e_ce10_coerente():
    e = generato(genera(righe(dio_days=22)))
    sp, ce = e.anni[2027]
    r = e.det[2027]["rimanenze_materie"]
    assert r["derivati"] is False and D(str(r["giorni"])) == D("22")
    assert ce["ce10_var_rimanenze_mat_prime"] == D("287312.00") - sp["sp05a_materie_prime"]


def test_B01_giorni_degeneri_riportano_lo_stock():
    # AMBIENTA: 287.312 di materie su un consumo di 128.090,89 = oltre 800 giorni ⇒ degenere.
    e = generato(genera(righe()))
    assert e.anni[2027][0]["sp05a_materie_prime"] == D("287312.00")
    assert e.anni[2027][1]["ce10_var_rimanenze_mat_prime"] == D("0.00")
    assert e.det[2027]["rimanenze_materie"]["degenere"] is True


def test_B01_override_ce10_muove_lo_sp():
    e = generato(genera(righe(ce10_override=12312)))
    assert e.anni[2027][0]["sp05a_materie_prime"] == D("275000.00")


def test_B01_base_senza_sotto_voci_usa_l_aggregato_come_materie():
    e = generato(genera(righe(dio_days=22), bs={"sp05a_materie_prime": D("0")}))
    sp, ce = e.anni[2027]
    assert ce["ce10_var_rimanenze_mat_prime"] == D("287312.00") - sp["sp05_rimanenze"]
```

Togli il marcatore di `test_B01_variazione_rimanenze_del_ce_segue_lo_sp`. Vitest (in `frontend/lib/budget-turnover.test.ts`): `computeAutoDays("dio", {ce05_materie_prime: 260, ce10_var_rimanenze_mat_prime: 0, ce01_ricavi_vendite: 1000, …}, {sp05_rimanenze: 36, sp05a_materie_prime: 36, …})` → `Math.round(36/260*360)` = 50; consumo ≤ 0 → `null`; base senza `sp05a` → usa `sp05_rimanenze − sp05e_acconti`.

- [ ] **Step 2:** `pytest tests/test_fix_rilievi_motore.py tests/test_rilievi_ambienta.py -k "rimanenze or B01" -q` e `cd frontend && npx vitest run lib/budget-turnover.test.ts` → FAIL.

- [ ] **Step 3:** implementa. `rimanenze_materie` in `projection_common.py`; nel CE un blocco commentato che sostituisce la riga di `ce10` e dichiara `details['rimanenze_materie']`; `_calculate_income_statement` riceve `base_bs=None, settore=None` dal chiamante (lo stesso `settore` già passato al BS). Nello SP sostituisci il blocco DIO e il riparto `sp05*` secondo la regola. Nel frontend, `computeAutoDays("dio")`: numeratore materie (`sp05a`, o `sp05 − sp05e` senza sotto-voci), denominatore `ce05 + ce10`.

- [ ] **Step 4:** PASS su entrambi; suite Python intera e `npx vitest run`, `npx tsc --noEmit`; classifica le rotture (attese: test che fissano `ce10` della base o `sp05` sui ricavi).

- [ ] **Step 5: commit** `fix(motore): B01 variazione rimanenze materie dallo SP, DIO sul consumo`.

---

### Task 6: B05 — nell'ultimo anno, la rata non scadenziata oltre l'orizzonte sta a breve

**Files:**
- Modify: `calculations/projection_common.py` (funzione pura nuova; `quota_breve_prestiti_nuovi` ~569)
- Modify: `calculations/forecast_engine.py` (ogni lettura della rata dell'anno dopo: `new_financing_schedule([c], anno + 1)` ~4218, ~4269, e le chiamate a `_quota_breve_prestiti_nuovi` / `quota_breve_prestiti_nuovi`; `_contratti_dell_anno` per la dichiarazione)
- Test: `tests/test_fix_rilievi_motore.py`, `tests/test_rilievi_ambienta.py` (togli marcatore B05)

**Interfaces:**
- Produces: `projection_common.rata_anno_dopo(loan: Mapping, anno: int, ultimo_anno_piano: int | None = None) -> tuple[Decimal, bool]` → `(capitale dovuto in anno+1, ripetuta)`; ogni riga di `details['debito_bancario']['contratti']` guadagna `'rata_ripetuta': bool`.

Regola (spec §3 B05): `rata = new_financing_schedule([loan], anno + 1)[1]`. Se `anno == ultimo_anno_piano`, il contratto ha `repayments`, la lista **non** copre `anno + 1` (`anno + 1 − loan['year'] >= len(repayments)`) e il residuo di fine `anno` è positivo: `rata = min(residuo, ultima rata positiva della lista)`, `ripetuta = True`. Una lista che copre `anno + 1`, anche con 0, vince sempre.

- [ ] **Step 1: test.**

```python
from calculations.projection_common import rata_anno_dopo

MUTUO = {"year": 2027, "opening_residual": D("1000"), "rate": D("0"), "repayments": [D("100"), D("100"), D("100")]}


def test_rata_anno_dopo_ripete_l_ultima_solo_nell_ultimo_anno():
    assert rata_anno_dopo(MUTUO, 2029, ultimo_anno_piano=2029) == (D("100"), True)
    assert rata_anno_dopo(MUTUO, 2028, ultimo_anno_piano=2029) == (D("100"), False)
    assert rata_anno_dopo(MUTUO, 2029) == (D("0"), False)


def test_rata_anno_dopo_zero_scadenziato_vince():
    m = {**MUTUO, "repayments": [D("100"), D("100"), D("100"), D("0")]}
    assert rata_anno_dopo(m, 2029, ultimo_anno_piano=2029) == (D("0"), False)


def test_rata_anno_dopo_mai_oltre_il_residuo():
    m = {**MUTUO, "opening_residual": D("350")}
    assert rata_anno_dopo(m, 2029, ultimo_anno_piano=2029) == (D("50"), True)
```

e un test di motore che, sullo scenario di `test_B05_rata_oltre_orizzonte_non_scadenziata_sta_a_breve`, controlla che il contratto del 2029 dichiari `rata_ripetuta is True` e breve 53.409 (usa `e.det[2029]["debito_bancario"]["contratti"]`). Togli il marcatore B05.

- [ ] **Step 2:** `pytest … -k "rata_anno_dopo or B05" -q` → FAIL.
- [ ] **Step 3:** implementa `rata_anno_dopo` (il residuo di fine `anno` si calcola come in `new_financing_schedule`: `principal − Σ repayments[:anno + 1 − year]`, mai sotto zero); instrada ogni lettura della rata dell'anno dopo del motore attraverso di essa, con `ultimo_anno_piano` = l'anno dell'ultima ipotesi (in `_calculate_balance_sheet`: `year_index == horizon − 1`); `quota_breve_prestiti_nuovi` riceve `ultimo_anno_piano=None` di default e lo inoltra. Dichiara `rata_ripetuta` per contratto. Verifica che la riconciliazione di `_dichiara_debito_bancario` (Σ breve + scoperto = `sp16a`) resti esatta.
- [ ] **Step 4:** PASS (incluso `test_B05_bis…`, che deve restare verde); suite intera, classifica.
- [ ] **Step 5: commit** `fix(motore): B05 rata dell'ultimo anno oltre l'orizzonte a breve`.

---

### Task 7: A04 — l'incasso dei crediti oltre 12 mesi consuma prima i clienti

**Files:**
- Modify: `calculations/forecast_engine.py` (funzione di modulo nuova; riparto `sp07*` ~4468-4491 nel ramo col piano `crediti_commerciali`)
- Modify: `frontend/components/budget/wizard/steps/StepPatrimonialePregresso.tsx` (nota della riga crediti commerciali oltre 12 mesi)
- Test: `tests/test_fix_rilievi_motore.py`, `tests/test_rilievi_ambienta.py` (riscrivi il test parametrizzato A04)

**Interfaces:**
- Produces: `forecast_engine._consuma_in_ordine(totale: Decimal, valori_base: list[Decimal]) -> list[Decimal]`.

Regola (spec §3 A04): col piano `crediti_commerciali`, il lato oltre commerciale (`sp07a/b/c/d/g`, esclusi `sp07e` tributari e `sp07f` anticipate, che restano come oggi) = `_consuma_in_ordine(residuo_lungo, basi)`: se `totale < Σ basi`, la riduzione `Σ basi − totale` si toglie prima dalla prima voce (`sp07a`), poi dalle successive in ordine, mai sotto zero; se `totale ≥ Σ basi` (o `Σ basi = 0`), riparto proporzionale come `_alloc` (tutto su `sp07a` senza dettaglio). Senza piano, invariato.

- [ ] **Step 1: test.**

```python
from calculations.forecast_engine import _consuma_in_ordine


def test_consuma_in_ordine_toglie_prima_dalla_prima_voce():
    assert _consuma_in_ordine(D("44"), [D("35"), D("0"), D("0"), D("0"), D("10")]) == \
        [D("34"), D("0"), D("0"), D("0"), D("10")]
    assert _consuma_in_ordine(D("5"), [D("35"), D("0"), D("0"), D("0"), D("10")]) == \
        [D("0"), D("0"), D("0"), D("0"), D("5")]


def test_consuma_in_ordine_crescita_proporzionale():
    assert _consuma_in_ordine(D("90"), [D("30"), D("0"), D("0"), D("0"), D("15")]) == \
        [D("60"), D("0"), D("0"), D("0"), D("30")]
    assert _consuma_in_ordine(D("7"), [D("0")] * 5) == [D("7"), D("0"), D("0"), D("0"), D("0")]
```

In `tests/test_rilievi_ambienta.py` riscrivi il parametrizzato (via marcatore, nuovo oracolo, docstring che cita la decisione):

```python
@pytest.mark.parametrize("sp07a, sp07g, atteso_a, atteso_g", [
    pytest.param(0, 45000, 0, 44000, id="tutto_su_sp07g"),
    pytest.param(35231, 9769, 34231, 9769, id="mix_del_consulente"),
])
def test_A04_incasso_scadenziato_consuma_prima_i_clienti(sp07a, sp07g, atteso_a, atteso_g):
    """A04 · decisione del proprietario (2026-09-26): l'incasso della massa «oltre 12 mesi» dei crediti
    commerciali consuma prima i clienti (sp07a), poi le altre sotto-voci. Supera l'oracolo del consulente
    («scende la voce altri crediti»): sul mix scende sp07a, sp07g resta 9.769."""
    rows = righe()
    rows[0]["pregresso"] = PREGRESSO_A04
    e = generato(genera(rows, bs=_a04_base(sp07a, sp07g)))
    sp = e.anni[2027][0]
    assert (sp["sp07a_crediti_clienti_lungo"], sp["sp07g_crediti_altri_lungo"]) == (D(str(atteso_a)), D(str(atteso_g))), sp
```

- [ ] **Step 2:** `pytest … -k "consuma or A04" -q` → FAIL.
- [ ] **Step 3:** implementa `_consuma_in_ordine` e usala nel ramo col piano crediti commerciali (entrambi i sotto-rami, con e senza piano `crediti_tributari_lungo`: `sp07e` si calcola a parte come oggi, il resto commerciale passa da `_consuma_in_ordine`). Nel `.tsx`, sotto la riga dei crediti commerciali oltre 12 mesi, una nota nello stile delle altre: «L'incasso si toglie prima dai crediti verso clienti oltre 12 mesi, poi dalle altre voci.»
- [ ] **Step 4:** PASS; suite Python intera; `cd frontend && npx tsc --noEmit && npm run build` (next build vede il lint che tsc non vede).
- [ ] **Step 5: commit** `fix(motore): A04 incasso dei crediti oltre 12 mesi prima sui clienti`.

---

### Task 8: documentazione, verdetto del triage, chiusura del lotto

**Files:**
- Modify: `CLAUDE.md` (sezione «Forecasting Engine (Budget)» e «Invarianti e trappole › Previsionale»)
- Modify: `docs/budget/FORECASTING_GUIDE.md`
- Modify: `tools/triage_rilievi.py` (`LETTURE`), `docs/superpowers/allineamento/2026-09-25-triage-rilievi-ambienta.md` (una sezione «Lotto 1, 2026-09-26»)

- [ ] **Step 1:** in CLAUDE.md, un bullet per regola, ognuno con che cosa cambia sugli scenari esistenti: TFR = retribuzioni/13,5 con personale ricomposto (`details['personale_ricomposto']`); ammortamenti per masse separate e metà aliquota nel primo anno (`details['ammortamenti']`); `ce10` dallo SP e DIO sulle materie sul consumo (`details['rimanenze_materie']`, `dio_days` ora vale per le sole materie); straordinari a zero; rata ripetuta nell'ultimo anno (`rata_ripetuta`); incasso oltre 12 mesi prima sui clienti; `ForecastYear.engine_meta` + `ENGINE_VERSION` (si incrementa a ogni cambiamento dei numeri; NULL = «non lo so»; `migrate_db.py` sul DB locale). Stesse regole in `FORECASTING_GUIDE.md`.
- [ ] **Step 2:** in `tools/triage_rilievi.py` aggiorna `LETTURE` per B01, B02, B03, B05, A04, E05 («Risolto nel lotto 1 fix, 2026-09-26», A04 ed E05 «su decisione del proprietario»). Aggiungi la sezione al rapporto di triage con lo stato del banco.
- [ ] **Step 3:** suite completa: `../budget/backend/venv/bin/python -m pytest tests -q -p no:warnings`, `cd frontend && npx vitest run && npx tsc --noEmit`. Expected: nessun fallimento nuovo rispetto alla linea di base del ledger; `tests/test_rilievi_ambienta.py` con i soli xfail del lotto 2 (A01-bis, A02, C01–C09).
- [ ] **Step 4: commit** `docs(rilievi): lotto 1 del motore — regole nuove, numeri che cambiano, verdetto`.
