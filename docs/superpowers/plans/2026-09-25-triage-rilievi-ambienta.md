# Banco di triage dei rilievi AMBIENTA — piano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un test per rilievo software del foglio AMBIENTA, eseguito su 62bfed1 e su 92c7270, che classifica ogni rilievo in Confermato / Risolto / Non riprodotto / Regressione e scrive il verdetto in una copia del foglio.

**Architecture:** pytest in memoria sul percorso di produzione (bulk assumptions → `ForecastYear` → `assemble_final_report` → `from_report` → PDF), Vitest sulle funzioni pure del wizard, base = AMBIENTA 2026 vero congelato in JSON. Uno script porta i file del banco in un worktree staccato di 62bfed1, esegue le due suite su entrambi i commit con report JUnit e compila il foglio.

**Tech Stack:** pytest, SQLAlchemy in memoria (`StaticPool`), Vitest 3 (`environment: node`), openpyxl.

**Spec:** `docs/superpowers/specs/2026-09-25-triage-rilievi-ambienta-design.md`

## Global Constraints

- Worktree `/home/peter/DEV/budget-rilievi`, branch `test/rilievi-ambienta`. Python: `/home/peter/DEV/budget/backend/venv/bin/python` (il worktree non ha venv). Frontend: `frontend/node_modules` è un symlink a `/home/peter/DEV/budget/frontend/node_modules` (crearlo se manca, non committarlo: è già in `.gitignore`).
- Nessun test tocca `financial_analysis.db`: tutto in memoria.
- Niente bilanci inventati: la base è `tests/fixtures/ambienta_2026.json` (anno 493 del DB locale, valori sotto, copiati al centesimo).
- Oracolo = comportamento che il consulente si aspetta. Un test rosso è un verdetto, non un guasto del banco: **non si corregge il codice di produzione in questo piano**.
- Ogni test porta l'ID nel nome (`test_A01_…`, `it("A01 …")`) e la riga del foglio nel docstring/commento: lo script di verdetto riconosce il rilievo dal prefisso `test_<ID>_` o `<ID> `.
- Un test che su un commit non può girare perché l'API non esiste ancora si **salta** (`pytest.importorskip`, `ctx.skip()`), non fallisce: per quel commit il verdetto è «n/a».
- File con fine riga miste: solo modifiche additive (memoria del proprietario). I file nuovi sono LF.
- Italiano nei messaggi e nei docstring; commit che finiscono con la riga `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

- **Un test verde per la ragione sbagliata.** Un test che non arriva all'asserzione (generazione respinta, periodo mancante) deve fallire con messaggio, mai passare: ogni test asserisce `forecast_generated is True` prima dell'oracolo, salvo i test che vogliono proprio il rifiuto.
- **Colonne sbagliate.** `data.columns[0]` è la base 2026; i valori di piano sono `data.plan_idx`. Un indice spostato di uno confronta 2026 con 2027 e dà un verdetto falso.
- **Import che su 62bfed1 non esistono** (`app.renderers.business_plan`, funzioni del wizard nuove): devono dare «skip», non «error», altrimenti lo script conta rosso e dichiara «Risolto» un rilievo di codice che non c'era.
- **Arrotondamenti.** Gli oracoli monetari si confrontano al centesimo (`Decimal`); gli indici con tolleranza esplicita (`abs(a-b) < 0.01`).
- **Il foglio originale** in `inbox/` non si sovrascrive: lo script scrive `inbox/Verifica_piano_Ambienta_triage.xlsx`.

---

### Task 1: Base AMBIENTA e kit del banco

**Files:**
- Create: `tests/fixtures/ambienta_2026.json`
- Create: `tests/rilievi_kit.py`
- Create: `tests/test_rilievi_ambienta.py` (solo il test del kit per ora)

**Interfaces:**
- Produces: `rilievi_kit.BASE_BS`, `BASE_CE` (dict str→Decimal); `rilievi_kit.righe(**comuni) -> list[dict]` (tre righe 2027-2029, `tax_rate` 27.9, `overdraft_allowed` True, crescite 0, più `comuni`); `rilievi_kit.genera(rows, *, bs=None, ce=None, report=False) -> Esito` con `Esito(res, anni, det, data, rep, db)` dove `anni[year] = (sp: dict, ce: dict)` letti da `ForecastYear`, `det[year]` = `details` del motore (preview sulle stesse righe), `data` = `BusinessPlanData` (solo se `report=True` e la generazione è riuscita), `rep` = modello v2 del report; `db` resta aperta dentro il context manager `sessione()`.

- [ ] **Step 1: la fixture**

`tests/fixtures/ambienta_2026.json`:

```json
{
  "_fonte": "financial_analysis.db locale, financial_years.id=493 (AMBIENTA, company 575, settore 1), congelato il 2026-09-25",
  "bs": {
    "sp02_immob_immateriali": "331692.85", "sp02a_costi_impianto": "113711.10", "sp02d_concessioni": "46566.68",
    "sp02e_avviamento": "84634.26", "sp02f_immob_in_corso": "86780.81",
    "sp03_immob_materiali": "72796.59", "sp03b_impianti_macchinari": "24154.00", "sp03c_attrezzature": "30719.42",
    "sp03d_altri_beni": "17923.17",
    "sp04_immob_finanziarie": "52550.00", "sp04a_partecipazioni": "52550.00",
    "sp05_rimanenze": "287312.00", "sp05a_materie_prime": "287312.00",
    "sp06_crediti_breve": "1294367.10", "sp06a_crediti_clienti_breve": "1068527.42",
    "sp06e_crediti_tributari_breve": "184140.58", "sp06g_crediti_altri_breve": "41699.10",
    "sp07_crediti_lungo": "62356.48", "sp07a_crediti_clienti_lungo": "45000.00", "sp07e_crediti_tributari_lungo": "17356.48",
    "sp09_disponibilita_liquide": "54.82", "sp10_ratei_risconti_attivi": "216226.30",
    "sp11_capitale": "110000.00", "sp12_riserve": "69484.43", "sp12c_riserva_legale": "3506.40",
    "sp12e_altre_riserve": "65978.03", "sp13_utile_perdita": "24131.11", "sp15_tfr": "170193.73",
    "sp16_debiti_breve": "1400851.61", "sp16a_debiti_banche_breve": "493408.90",
    "sp16d_debiti_fornitori_breve": "548578.07", "sp16e_debiti_tributari_breve": "4227.00",
    "sp16f_debiti_previdenza_breve": "163536.55", "sp16g_altri_debiti_breve": "191101.09",
    "sp17_debiti_lungo": "504032.26", "sp17a_debiti_banche_lungo": "467528.52",
    "sp17b_debiti_altri_finanz_lungo": "36503.74", "sp18_ratei_risconti_passivi": "38663.00"
  },
  "ce": {
    "ce01_ricavi_vendite": "4109510.00", "ce03_lavori_interni": "93000.00", "ce04_altri_ricavi": "140706.00",
    "ce05_materie_prime": "129308.00", "ce06_servizi": "1432482.00", "ce07_godimento_beni": "234534.00",
    "ce08_costi_personale": "2344742.00", "ce08a_tfr_accrual": "81014.85", "ce08b_salari_stipendi": "1772346.75",
    "ce08c_oneri_sociali": "453027.54", "ce08d_altri_costi_personale": "38352.86",
    "ce09_ammortamenti": "75264.00", "ce09a_ammort_immateriali": "29224.00", "ce09b_ammort_materiali": "36040.00",
    "ce09d_svalutazione_crediti": "10000.00", "ce10_var_rimanenze_mat_prime": "-1217.11",
    "ce12_oneri_diversi": "37530.00", "ce14_altri_proventi_finanziari": "11750.00",
    "ce15_oneri_finanziari": "45192.00", "ce20_imposte": "33000.00"
  }
}
```

- [ ] **Step 2: il test del kit (rosso: il kit non esiste)**

`tests/test_rilievi_ambienta.py`:

```python
"""Banco di triage dei rilievi AMBIENTA (inbox/Verifica_piano_Ambienta_problemi.xlsx).

Spec: docs/superpowers/specs/2026-09-25-triage-rilievi-ambienta-design.md. Un test per rilievo software;
l'oracolo è il comportamento che il consulente si aspetta, quindi un test ROSSO vuol dire che il difetto
c'è. Nessun fix in questo file: il verdetto lo scrive tools/triage_rilievi.py.
"""
from decimal import Decimal as D

import pytest

from tests.rilievi_kit import BASE_BS, BASE_CE, genera, righe

SP = "sp"  # solo per leggibilità dei commenti


def test_kit_la_base_ambienta_genera_un_piano_a_crescita_zero():
    e = genera(righe())
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert sorted(e.anni) == [2027, 2028, 2029]
    assert e.anni[2027][1]["ce01_ricavi_vendite"] == BASE_CE["ce01_ricavi_vendite"]
    assert e.anni[2027][0]["_total_assets"] == e.anni[2027][0]["_total_liabilities"]
```

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py -q -p no:warnings`
Expected: FAIL — `ModuleNotFoundError: No module named 'tests.rilievi_kit'`

- [ ] **Step 3: il kit**

`tests/rilievi_kit.py`:

```python
"""Kit del banco di triage AMBIENTA: base vera in memoria, generazione e report dal percorso di produzione."""
import json
from dataclasses import dataclass
from decimal import Decimal as D
from pathlib import Path

from database.models import BalanceSheet, BudgetScenario, Company, FinancialYear, IncomeStatement
from backend.app.services import assumptions_service, forecast_preview_service
from tests.e2e_kit import memory_sessions, read_forecast_maps

_RAW = json.loads((Path(__file__).parent / "fixtures" / "ambienta_2026.json").read_text())
BASE_BS = {k: D(v) for k, v in _RAW["bs"].items()}
BASE_CE = {k: D(v) for k, v in _RAW["ce"].items()}
ANNI = (2027, 2028, 2029)


def righe(**comuni) -> list:
    """Tre righe di piano a crescita zero. Lo scoperto è concesso: la cassa di base è 54,82 € e ogni test
    deve isolare il proprio meccanismo, non inciampare nel fabbisogno."""
    out = []
    for y in ANNI:
        r = {"forecast_year": y, "revenue_growth_pct": 0, "tax_rate": 27.9, "overdraft_allowed": True}
        r.update(comuni)
        out.append(r)
    return out


def per_anno(rows: list, campo: str, valori) -> list:
    """Imposta `campo` anno per anno (valori nell'ordine 2027, 2028, 2029)."""
    for r, v in zip(rows, valori):
        r[campo] = v
    return rows


@dataclass
class Esito:
    res: dict
    anni: dict
    det: dict
    data: object
    rep: object


def genera(rows, *, bs=None, ce=None, report=False, prima=None) -> Esito:
    """Semina la base (con eventuali ritocchi `bs`/`ce`), salva le righe col bulk di produzione
    (`auto_generate=True`) e rilegge ciò che è persistito. `prima`: righe salvate e generate PRIMA di
    `rows`, per i test che vogliono un previsionale vecchio sotto un salvataggio respinto."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company = Company(name="AMBIENTA", tax_id="AMBIENTA2026", sector=1, user_id="rilievi")
            db.add(company); db.flush()
            fy = FinancialYear(company_id=company.id, year=2026, period_months=None,
                               validation_status="verified", forecastable=True)
            db.add(fy); db.flush()
            db.add(BalanceSheet(financial_year_id=fy.id, **{**BASE_BS, **(bs or {})}))
            db.add(IncomeStatement(financial_year_id=fy.id, **{**BASE_CE, **(ce or {})}))
            db.commit()
            sc = BudgetScenario(company_id=company.id, name="rilievi", base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            if prima is not None:
                r0 = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in prima],
                                                                 auto_generate=True)
                assert r0["forecast_generated"] is True, r0["message"]
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows],
                                                              auto_generate=True)
            anni = {y: (sp, c) for y, sp, c in read_forecast_maps(db, sc.id)}
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            det = {y["year"]: y["details"] for y in prev.get("forecast_years") or []}
            data = rep = None
            if report and anni:
                from backend.app.services.final_report_service import assemble_final_report
                from backend.app.renderers.business_plan.data import from_report
                rep = assemble_final_report(db, company.id, sc.id, schema_version=2)
                data = from_report(rep, draft=True)
            return Esito(res, anni, det, data, rep)
    finally:
        engine.dispose()


def piano(data, key: str) -> list:
    """Valori di piano (2027..2029) di una chiave di BusinessPlanData, colonna base esclusa."""
    return [data.v(key)[i] for i in data.plan_idx]


def base(data, key: str):
    return data.v(key)[0]
```

- [ ] **Step 4: verde**

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py -q -p no:warnings`
Expected: `1 passed`

- [ ] **Step 5: commit**

```bash
cd /home/peter/DEV/budget-rilievi && git add tests/fixtures/ambienta_2026.json tests/rilievi_kit.py tests/test_rilievi_ambienta.py && git commit -m "test(rilievi): base AMBIENTA 2026 vera e kit del banco di triage

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: rilievi del motore (A01, A03, A04, A06, B01, B02, B03, B04, B05, E05)

**Files:**
- Modify: `tests/test_rilievi_ambienta.py` (append)

**Interfaces:**
- Consumes: `genera`, `righe`, `per_anno`, `BASE_BS`, `BASE_CE` (Task 1).

In questo task **i test si scrivono per restare rossi quando il difetto c'è**: lo step «rosso» del TDD qui è il verdetto stesso. Si esegue ogni test, si legge l'esito, si annota nel ledger `Task 2: <ID> rosso|verde — <messaggio breve>`. Non si tocca il codice di produzione.

- [ ] **Step 1: A01, A03, A04**

Append:

```python
Q = D("0.01")


def _q(x) -> D:
    return D(str(x)).quantize(Q)


def test_A01_scostamento_materie_applicato_dal_motore():
    """A01 · Passo 3 Costi: scostamento −5 punti sulle materie dalla crescita ricavi (5/6/7 → 0/1/2).
    Il consulente: materie 2027 = 129.308 (base × 1,00), il report dava 135.773."""
    rows = per_anno(righe(fixed_materials_percentage=0, variable_materials_growth_auto=False),
                    "revenue_growth_pct", (5, 6, 7))
    per_anno(rows, "variable_materials_growth_pct", (0, 1, 2))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    base = BASE_CE["ce05_materie_prime"]
    attese = [_q(base), _q(base * D("1.01")), _q(base * D("1.01") * D("1.02"))]
    assert [e.anni[y][1]["ce05_materie_prime"] for y in (2027, 2028, 2029)] == attese


def test_A03_acconto_manuale_maggiore_di_zero_vince_sulla_percentuale():
    """A03 · Passo 7 Imposte: acconti 50.000 / 10.000 / 20.000 ignorati, applicato il 100% dell'imposta
    dell'anno prima. Oracolo: l'acconto versato di ogni anno è l'importo digitato."""
    rows = per_anno(righe(), "tax_advances_paid", (50000, 10000, 20000))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    versati = [_q(e.det[y]["imposte"]["acconti_paid"]) for y in (2027, 2028, 2029)]
    assert versati == [D("50000.00"), D("10000.00"), D("20000.00")]


# Il piano che il wizard scrive per «incasso 1.000 nel 2027 sui crediti oltre 12 mesi»: prodotto da
# withOltreAmount(baseBs, {}, [2027, 2028, 2029], "crediti_commerciali", 0, 1000) sulla stessa base
# (breve 1.110.226,52 + oltre 45.000 = apertura 1.155.226,52; incasso 2027 = breve + 1.000).
PREGRESSO_A04 = {
    "crediti_commerciali": {"opening": 1155226.52, "amounts": [1111226.52, 0, 0], "writeoff": None,
                            "non_incassato": False},
    "crediti_tributari_breve": {"opening": 184140.58, "amounts": [184140.58, 0, 0], "writeoff": None},
    "crediti_tributari_lungo": {"opening": 17356.48, "amounts": [0, 0, 0], "writeoff": None},
    "debiti_fornitori": {"opening": 548578.07, "amounts": [548578.07, 0, 0], "writeoff": None},
}


def test_A04_incasso_scadenziato_sui_crediti_oltre_12_mesi_arriva_allo_sp():
    """A04 · Passo 5: incasso di 1.000 nel 2027 sui crediti oltre 12 mesi; l'interfaccia dice «resta 8.769»,
    lo SP tiene il saldo intero. Qui: oltre 45.000 → 44.000 nel 2027, e la generazione non è respinta."""
    rows = righe()
    rows[0]["pregresso"] = PREGRESSO_A04
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert e.anni[2027][0]["sp07a_crediti_clienti_lungo"] == D("44000.00")
```

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py -q -p no:warnings -k "A01 or A03 or A04" -rA 2>&1 | tail -25`
Expected: ogni test PASS o FAIL con messaggio di asserzione (mai `ERROR` di collezione o `KeyError` del banco). Se un test fallisce per un errore del banco (chiave inesistente, periodo mancante), correggi il test — è un difetto del banco, non un verdetto — e ledgera la correzione come `Ruling:`.

- [ ] **Step 2: A06, B01, B02, B03**

Append:

```python
def test_A06_previdenziali_seguono_il_personale_se_la_tendina_lo_dice():
    """A06 · Passo 6: tendina «cresce con il costo del personale», casella non spuntata; l'output cresce coi
    ricavi. Oracolo: sp16f cresce come ce08 (personale +3/4/4, ricavi +5/6/7)."""
    rows = per_anno(righe(sp_indexing={"sp16f": "personale"}, previdenza_scales_with_personnel=False),
                    "revenue_growth_pct", (5, 6, 7))
    per_anno(rows, "personnel_growth_pct", (3, 4, 4))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    b16, b08 = BASE_BS["sp16f_debiti_previdenza_breve"], BASE_CE["ce08_costi_personale"]
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        atteso = b16 * ce["ce08_costi_personale"] / b08
        assert abs(sp["sp16f_debiti_previdenza_breve"] - atteso) < D("1"), (y, sp["sp16f_debiti_previdenza_breve"], atteso)


def test_B01_variazione_rimanenze_del_ce_segue_lo_sp():
    """B01 · Passo 4 / CE B11: nello SP le rimanenze seguono il DIO, nel CE la variazione resta al valore
    2026. Oracolo: ce10 di ogni anno = rimanenze di fine anno − rimanenze d'inizio (convenzione del CE:
    un aumento delle rimanenze di materie riduce il costo)."""
    rows = per_anno(righe(dio_days=22), "revenue_growth_pct", (5, 6, 7))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    prec = BASE_BS["sp05_rimanenze"]
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        delta = sp["sp05_rimanenze"] - prec
        assert abs(abs(ce["ce10_var_rimanenze_mat_prime"]) - abs(delta)) < D("1"), (y, ce["ce10_var_rimanenze_mat_prime"], delta)
        prec = sp["sp05_rimanenze"]


def test_B02_ammortamento_dei_cespiti_esistenti_si_ferma_al_residuo():
    """B02 · Passo 6: materiali esistenti 72.797 netti ammortizzati 36.040/anno anche oltre il residuo.
    Con un investimento di 250.000 nel 2027 al 10%: 2027 = 36.040 + 25.000, 2028 = 36.040 + 25.000,
    2029 = residuo esistente (72.796,59 − 72.080 = 716,59) + 25.000."""
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 250000
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert e.anni[2029][1]["ce09b_ammort_materiali"] == D("25716.59")


def test_B03_tfr_uguale_retribuzioni_diviso_13_5():
    """B03 · Passo 3/6: l'accantonamento è il residuo personale − salari − oneri, non retribuzioni/13,5
    come dice l'interfaccia. Oracolo: ce08a = ce08b / 13,5 in ogni anno."""
    e = genera(per_anno(righe(), "personnel_growth_pct", (3, 4, 4)))
    assert e.res["forecast_generated"] is True, e.res["message"]
    for y in (2027, 2028, 2029):
        ce = e.anni[y][1]
        assert abs(ce["ce08a_tfr_accrual"] - ce["ce08b_salari_stipendi"] / D("13.5")) < D("1"), (y, ce["ce08a_tfr_accrual"])
```

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py -q -p no:warnings -k "A06 or B01 or B02 or B03" -rA 2>&1 | tail -25`
Expected: come Step 1 — PASS o FAIL di asserzione, mai errori del banco. Per B01 leggi il segno che il motore usa per `ce10` sulla base (−1.217,11 con rimanenze in aumento o in calo?) e, se la convenzione è l'opposta, il test confronta i valori assoluti: già fatto; ledgera la convenzione osservata.

- [ ] **Step 3: B04, B05, E05**

Append:

```python
MUTUO_A = {"name": "Finanziamento A", "amount": 0, "opening_residual": 467528.52, "interest_rate": 4,
           "grace_years": 0, "balloon_pct": 0, "duration_years": None,
           "repayments": [53409, 53409, 53409, 53409]}


def _banche(fidi: float, residuo: float) -> dict:
    return {"financing_loans": [{**MUTUO_A, "opening_residual": residuo}], "bank_lines_amount": fidi,
            "bank_lines_rule": "costante", "bank_lines_rate": 6}


def test_B04_fidi_e_residui_che_non_quadrano_col_bilancio_si_rifiutano():
    """B04 · Passo 5: fidi 311.000 + residuo ≠ debito bancario di bilancio (scarto 11.000), avviso rosso ma
    il motore calcola coi fidi ridotti in silenzio. Oracolo: generazione respinta e scarto nel messaggio."""
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]  # 960.937,42
    residuo = float(banche - D("300000"))  # il residuo quadra coi fidi a 300.000: lo scarto sono i fidi a 311.000
    rows = righe()
    rows[0].update(_banche(311000, residuo))
    e = genera(rows)
    assert e.res["forecast_generated"] is False
    assert "11.000" in e.res["message"], e.res["message"]


def test_B05_ultimo_anno_la_rata_successiva_sta_a_breve():
    """B05 · Passo 5 → SP 2029: oltre l'orizzonte la rata 2030 del Finanziamento A non è classificata
    entro 12 mesi. Oracolo: banche a breve 2029 = fidi + rata 2030 scadenziata (53.409)."""
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert e.anni[2029][0]["sp16a_debiti_banche_breve"] == D("353409.00")


def test_B05_bis_rata_oltre_orizzonte_non_scadenziata():
    """B05 · variante del foglio: il piano scadenzia solo 2027-2029 e a fine 2029 resta un residuo.
    Oracolo del consulente: a breve almeno la rata dell'ultimo anno (53.409)."""
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    rows[0]["financing_loans"][0]["repayments"] = [53409, 53409, 53409]
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    assert e.anni[2029][0]["sp16a_debiti_banche_breve"] >= D("353409.00")


def test_E05_caratterizzazione_ammortamento_primo_anno_e_straordinari():
    """E05 · caratterizzazione, non verdetto (spec §4): registra lo stato. Investimento 2027 di 100.000 al 10%:
    quota 2027 del nuovo = 10.000 (aliquota piena). Oneri diversi 2026 ripetuti ogni anno."""
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 100000
    e = genera(rows)
    assert e.res["forecast_generated"] is True, e.res["message"]
    quota_nuovo = e.anni[2027][1]["ce09b_ammort_materiali"] - BASE_CE["ce09b_ammort_materiali"]
    assert quota_nuovo == D("10000.00")  # aliquota piena nel primo anno: stato di oggi
```

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py -q -p no:warnings -k "B04 or B05 or E05" -rA 2>&1 | tail -25`
Expected: PASS o FAIL di asserzione. Per B04 leggi il messaggio del motore e, se nomina lo scarto in un altro formato (es. «11.000,00»), l'asserzione `"11.000" in` lo copre già; se il motore genera (`True`) il test è rosso: è il verdetto.

- [ ] **Step 4: commit**

```bash
cd /home/peter/DEV/budget-rilievi && git add tests/test_rilievi_ambienta.py && git commit -m "test(rilievi): triage dei rilievi del motore (A01, A03, A04, A06, B01-B05, E05)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: rilievi del report (A01-bis, A02, C01-C09)

**Files:**
- Modify: `tests/test_rilievi_ambienta.py` (append)

**Interfaces:**
- Consumes: `genera(..., report=True)`, `piano`, `base` (Task 1). Accessori del report: `data.v(key)` con le chiavi di `business_plan.data` (`dscr`, `pfn`, `dso`, `rod`, `liquidita_corrente`, `copertura_immob`, `of_mol`, `cf_nuovo_debito`, `cf_rimborsi`, `costi_variabili`, `costi_fissi`, `bep`); `data.indicators_analytical` = tuple di `IndicatorRow(label, unit, values)` allineate a `data.columns`; `e.rep.readiness.status`; `narrative.key_points(data) -> list[(lead, text)]`.

Tutti i test di questo task iniziano con `pytest.importorskip("app.renderers.business_plan.data")` **e** `pytest.importorskip("backend.app.renderers.business_plan.data")`: su 62bfed1 il Business plan non esiste, e il verdetto per quel commit è «n/a».

- [ ] **Step 1: A01-bis e A02**

Append:

```python
def _bp():
    pytest.importorskip("backend.app.renderers.business_plan.data")


def test_A01_bis_salvataggio_respinto_non_stampa_il_previsionale_vecchio_come_buono():
    """A01/A04/B04 · ipotesi della verifica sul codice: un salvataggio respinto risponde 200, a schermo resta il
    previsionale vecchio e il report lo stampa. Oracolo: il report è bloccato E il PDF in bozza dice che il
    previsionale non corrisponde alle ipotesi salvate."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan
    buone = righe()
    respinte = righe()
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    respinte[0].update(_banche(311000, float(banche - D("300000"))))
    e = genera(respinte, prima=buone, report=True)
    assert e.res["forecast_generated"] is False
    assert e.rep is not None, "il report non si costruisce sul previsionale vecchio"
    assert e.rep.readiness.status == "blocked", e.rep.readiness
    import fitz
    pdf = render_business_plan(e.data)
    testo = "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf")).lower()
    assert "non aggiornat" in testo or "ipotesi salvate" in testo, "il PDF in bozza tace sul previsionale vecchio"


def test_A02_bep_del_report_usa_la_ripartizione_del_motore():
    """A02 · Report sez. 4: il BEP del report non usa la ripartizione fissi/variabili degli slider (60/40 di
    default). Oracolo: costi variabili e fatturato di pareggio del report = details['pareggio'] del motore."""
    _bp()
    rows = righe(fixed_materials_percentage=0, fixed_services_percentage=50)
    e = genera(rows, report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    for i, y in enumerate((2027, 2028, 2029)):
        par = e.det[y]["pareggio"]
        assert abs(D(str(piano(e.data, "costi_variabili")[i])) - par["costi_variabili"]) < D("1"), y
        assert abs(D(str(piano(e.data, "bep")[i])) - par["fatturato_pareggio"]) < D("1"), y
```

Prima di eseguire, verifica il nome della funzione che rende il PDF: `grep -n "^def render" backend/app/renderers/business_plan/document.py`. Se non è `render_business_plan(data) -> bytes`, usa quella che c'è e ledgera la `Ruling:`.

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py -q -p no:warnings -k "A01_bis or A02" -rA 2>&1 | tail -25`
Expected: PASS o FAIL di asserzione; `SKIPPED` non è atteso su questo commit.

- [ ] **Step 2: C01-C05**

Append:

```python
def _con_rimborsi():
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    return rows


def test_C01_il_dscr_del_report_comprende_la_quota_capitale():
    """C01 · Report sez. 1, 6, All. D: «DSCR proxy» = (EBITDA − imposte) / oneri, senza quota capitale.
    Oracolo: DSCR = (MOL − imposte) / (oneri + quota capitale); con rimborsi 53.409 è molto sotto il proxy."""
    _bp()
    e = genera(_con_rimborsi(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    ce = e.anni[2027][1]
    mol = e.data.v("ebitda")[e.data.plan_idx[0]]
    atteso = (D(str(mol)) - ce["ce20_imposte"]) / (ce["ce15_oneri_finanziari"] + D("53409"))
    assert abs(D(str(piano(e.data, "dscr")[0])) - atteso) < D("0.01"), (piano(e.data, "dscr")[0], atteso)


def test_C02_dso_sui_soli_crediti_commerciali():
    """C02 · Report sez. 1, 7, All. E: «DSO» su tutti i crediti (tributari e oltre 12 mesi compresi).
    Oracolo: DSO 2026 = clienti (sp06a + sp07a) / ricavi × 360."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    atteso = (BASE_BS["sp06a_crediti_clienti_breve"] + BASE_BS["sp07a_crediti_clienti_lungo"]) \
        / BASE_CE["ce01_ricavi_vendite"] * 360
    assert abs(D(str(base(e.data, "dso"))) - atteso) < D("1"), (base(e.data, "dso"), atteso)


def test_C03_rod_sui_debiti_finanziari():
    """C03 · ROD = oneri finanziari / totale debiti (fornitori compresi). Oracolo: oneri / debiti finanziari
    (banche + altri finanziatori), in percentuale."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    fin = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"] \
        + BASE_BS["sp17b_debiti_altri_finanz_lungo"]
    atteso = BASE_CE["ce15_oneri_finanziari"] / fin * 100
    assert abs(D(str(base(e.data, "rod"))) - atteso) < D("0.05"), (base(e.data, "rod"), atteso)


def test_C04_pfn_del_report_comprende_gli_altri_finanziatori():
    """C04 · PFN del report esclude gli altri finanziatori, l'interfaccia (budget-piano-step.ts, finDebt)
    li include. Oracolo: PFN 2026 = banche + altri finanziatori + obbligazioni − cassa."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    atteso = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"] \
        + BASE_BS["sp17b_debiti_altri_finanz_lungo"] - BASE_BS["sp09_disponibilita_liquide"]
    assert abs(D(str(base(e.data, "pfn"))) - atteso) < D("1"), (base(e.data, "pfn"), atteso)


def _analitico(data, etichetta: str):
    for r in data.indicators_analytical:
        if r.label.strip().lower() == etichetta.lower():
            return r
    raise AssertionError(f"indicatore «{etichetta}» assente dall'Allegato E: "
                         f"{[r.label for r in data.indicators_analytical]}")


def test_C05_un_solo_current_ratio_nel_documento():
    """C05 · Liquidità corrente sez. 8 = 1,43×, Current Ratio All. E = 1,29×. Oracolo: stesso valore."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    sez8 = D(str(base(e.data, "liquidita_corrente")))
    all_e = D(str(_analitico(e.data, "Current Ratio").values[0]))
    assert abs(sez8 - all_e) < D("0.01"), (sez8, all_e)
```

Prima di eseguire, conferma l'etichetta esatta nell'Allegato E: `grep -rn "Current Ratio\|Indice di Indebitamento\|Copertura" contracts/final_report_dossier_catalog.json | head`. Se l'etichetta è diversa, correggi la stringa nel test e ledgera la `Ruling:`.

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py -q -p no:warnings -k "C01 or C02 or C03 or C04 or C05" -rA 2>&1 | tail -25`
Expected: PASS o FAIL di asserzione.

- [ ] **Step 3: C06-C09**

Append:

```python
def test_C06_indice_di_indebitamento_e_debiti_su_patrimonio():
    """C06 · All. E: «Indice di indebitamento» = immobilizzazioni / PN. Oracolo: debiti totali / PN."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    pn = BASE_BS["sp11_capitale"] + BASE_BS["sp12_riserve"] + BASE_BS["sp13_utile_perdita"]
    atteso = (BASE_BS["sp16_debiti_breve"] + BASE_BS["sp17_debiti_lungo"]) / pn
    val = D(str(_analitico(e.data, "Indice di Indebitamento").values[0]))
    assert abs(val - atteso) < D("0.01"), (val, atteso)


def test_C07_copertura_immobilizzazioni_con_il_tfr():
    """C07 · Sez. 8, All. D: il TFR non è fra le fonti consolidate. Oracolo (in %):
    (PN + debiti a lungo + TFR) / immobilizzazioni × 100."""
    _bp()
    e = genera(righe(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    pn = BASE_BS["sp11_capitale"] + BASE_BS["sp12_riserve"] + BASE_BS["sp13_utile_perdita"]
    immob = BASE_BS["sp02_immob_immateriali"] + BASE_BS["sp03_immob_materiali"] + BASE_BS["sp04_immob_finanziarie"]
    atteso = (pn + BASE_BS["sp17_debiti_lungo"] + BASE_BS["sp15_tfr"]) / immob * 100
    assert abs(D(str(base(e.data, "copertura_immob"))) - atteso) < D("0.1"), (base(e.data, "copertura_immob"), atteso)


def test_C08_erogazioni_e_rimborsi_su_righe_separate():
    """C08 · Sez. 1, 5, All. C: nel 2027 erogazione 280.000 e rimborsi 88.409 compensati (191.591).
    Oracolo: il rendiconto 2027 porta nuovo debito = 280.000 e rimborsi ≥ 53.409, non il netto."""
    _bp()
    rows = _con_rimborsi()
    rows[0]["financing_loans"].append({"name": "Nuovo", "amount": 280000, "opening_residual": 0,
                                       "duration_years": 8, "interest_rate": 4.5, "grace_years": 0,
                                       "balloon_pct": 0})
    e = genera(rows, report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    nuovo, rimb = piano(e.data, "cf_nuovo_debito")[0], piano(e.data, "cf_rimborsi")[0]
    assert abs(D(str(nuovo)) - D("280000")) < D("1"), (nuovo, rimb)
    assert D(str(rimb)) >= D("53409"), (nuovo, rimb)


def test_C09_oneri_su_mol_parte_dalla_colonna_base():
    """C09 · Sez. 1: «dal 24,54% al 10,71%» ma il 2026 F è 30,73%. Oracolo: il testo cita il valore della
    colonna base."""
    _bp()
    from backend.app.renderers.business_plan import fmt
    from backend.app.renderers.business_plan.narrative import key_points
    e = genera(_con_rimborsi(), report=True)
    assert e.res["forecast_generated"] is True, e.res["message"]
    testo = " ".join(t for _, t in key_points(e.data))
    assert fmt.pct(base(e.data, "of_mol")) in testo, (fmt.pct(base(e.data, "of_mol")), testo)
```

Prima di eseguire: `grep -n "^from\|^import" backend/app/renderers/business_plan/narrative.py | head` per il modulo `fmt` (se è `app.renderers.fmt` o simile, correggi l'import e ledgera). Su C07, se `copertura_immob` è un rapporto e non una percentuale, confronta con `atteso / 100` e ledgera.

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py -q -p no:warnings -k "C06 or C07 or C08 or C09" -rA 2>&1 | tail -25`
Expected: PASS o FAIL di asserzione.

- [ ] **Step 4: commit**

```bash
cd /home/peter/DEV/budget-rilievi && git add tests/test_rilievi_ambienta.py && git commit -m "test(rilievi): triage dei rilievi del report (A01-bis, A02, C01-C09)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: rilievi del wizard (Vitest: A01, A03, A05, A06)

**Files:**
- Create: `frontend/lib/rilievi-ambienta.test.ts`

**Interfaces:**
- Consumes (verificate il 2026-09-25 su 92c7270): `lib/budget-costi-step.ts` → `variableGrowthChange(deviation: number | null, revenue: number): number`, `variableGrowthDeviation(growth, revenue): string`, `variableAutoYearsOf(map, years, field)`; `lib/budget-imposte-step.ts` → `accontiRow(preview, accontoPct)` con `.field`; `lib/budget-sp-manuale.ts` → `withSpRule(assumptions, years, code, field, growthField, driver, projected)`; `lib/budget-circolante-step.ts` → `minorFieldsRows(baseBs, indexing, previdenzaSuPersonale, years)`.

Ogni test importa il modulo con `await import(...)` dentro il test e fa `ctx.skip()` se la funzione non esiste: su 62bfed1 alcune non c'erano.

- [ ] **Step 1: i test**

```ts
// Banco di triage dei rilievi AMBIENTA — lato wizard. Spec: docs/superpowers/specs/2026-09-25-triage-rilievi-ambienta-design.md.
// Oracolo = comportamento che il consulente si aspetta: un test rosso vuol dire che il difetto c'è.
import { describe, expect, it } from "vitest";

async function fn<T = any>(mod: string, name: string): Promise<T | null> {
  try {
    const m: any = await import(/* @vite-ignore */ mod);
    return (m?.[name] as T) ?? null;
  } catch {
    return null;
  }
}

describe("rilievi AMBIENTA · wizard", () => {
  it("A01 lo scostamento digitato resta lo scostamento dopo un cambio dei ricavi", async (ctx) => {
    const change = await fn<(d: number | null, r: number) => number>("@/lib/budget-costi-step", "variableGrowthChange");
    const dev = await fn<(g: number | null, r: number) => string>("@/lib/budget-costi-step", "variableGrowthDeviation");
    if (!change || !dev) return ctx.skip();
    const salvato = change(-5, 5); // ricavi +5, scostamento −5 → materie 0
    expect(salvato).toBe(0);
    // I ricavi passano a +7 dopo: il consulente si aspetta che lo scostamento resti −5 (materie +2).
    expect(dev(salvato, 7)).toBe("-5");
  });

  it("A03 il passo Imposte ha un campo per anno collegato a tax_advances_paid", async (ctx) => {
    const row = await fn<(p: unknown, pct: number) => { field: string }>("@/lib/budget-imposte-step", "accontiRow");
    if (!row) return ctx.skip();
    expect(row({ forecast_years: [] }, 100).field).toBe("tax_advances_paid");
  });

  it("A05 passare a Manuale non congela i valori della regola precedente", async (ctx) => {
    const withSpRule = await fn<any>("@/lib/budget-sp-manuale", "withSpRule");
    if (!withSpRule) return ctx.skip();
    const prima = { 2027: { sp_indexing: { sp04: "ricavi" } } };
    const dopo = withSpRule(prima, [2027], "sp04", "sp04_immob_finanziarie", "sp04_growth_pct", null, { 2027: 55178 });
    // Oracolo del consulente: con i campi manuali vuoti la voce non segue i ricavi → nessun override scritto.
    expect(dopo[2027]?.sp_overrides?.sp04_immob_finanziarie ?? null).toBeNull();
  });

  it("A06 un solo comando governa i debiti previdenziali", async (ctx) => {
    const rows = await fn<any>("@/lib/budget-circolante-step", "minorFieldsRows");
    if (!rows) return ctx.skip();
    const out: any[] = rows({ sp16f_debiti_previdenza_breve: 163536.55 }, { sp16f: "ricavi" }, false, [2027]);
    const riga = out.find((r) => r.code === "sp16f" || r.balanceField === "sp16f_debiti_previdenza_breve");
    expect(riga).toBeDefined();
    // Oracolo: la riga di sp16f non offre una tendina indipendente dalla casella «scalano col personale».
    expect(riga.driver ?? null).toBeNull();
  });
});
```

- [ ] **Step 2: eseguire e leggere i verdetti**

Run: `cd /home/peter/DEV/budget-rilievi/frontend && ls node_modules >/dev/null 2>&1 || ln -s /home/peter/DEV/budget/frontend/node_modules node_modules; npx vitest run lib/rilievi-ambienta.test.ts 2>&1 | tail -30`
Expected: ogni test PASS o FAIL di asserzione, nessuno SKIP su questo commit. Se `accontiRow` o `minorFieldsRows` lanciano per un argomento del banco (forma di `preview`, `baseBs`), leggi la firma nel sorgente, adatta l'argomento e ledgera la `Ruling:` — è il banco, non il verdetto.

- [ ] **Step 3: commit**

```bash
cd /home/peter/DEV/budget-rilievi && git add frontend/lib/rilievi-ambienta.test.ts && git commit -m "test(rilievi): triage dei rilievi del wizard (A01, A03, A05, A06)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: lo script del verdetto

**Files:**
- Create: `tools/triage_rilievi.py`
- Create: `tests/test_triage_rilievi_tool.py`

**Interfaces:**
- Produces: `verdetto(vecchio: str | None, nuovo: str | None) -> str` con esiti `"pass" | "fail" | "skip" | None`; `esiti_junit(path) -> dict[str, str]` (ID rilievo → esito peggiore fra i suoi test); `main()` che crea il worktree di 62bfed1, esegue le suite, scrive `inbox/Verifica_piano_Ambienta_triage.xlsx`.

- [ ] **Step 1: test della logica pura (rosso)**

`tests/test_triage_rilievi_tool.py`:

```python
from tools.triage_rilievi import esiti_junit, verdetto


def test_tabella_del_verdetto():
    assert verdetto("fail", "fail") == "Confermato"
    assert verdetto("fail", "pass") == "Risolto (2026-09-24)"
    assert verdetto("pass", "pass") == "Non riprodotto"
    assert verdetto("pass", "fail") == "Regressione"
    assert verdetto("skip", "fail") == "Confermato (n/a su 62bfed1)"
    assert verdetto("skip", "pass") == "Non riprodotto (n/a su 62bfed1)"
    assert verdetto(None, None) == "Senza test"


def test_esiti_junit_prende_il_peggiore_per_rilievo(tmp_path):
    x = tmp_path / "r.xml"
    x.write_text(
        '<testsuites><testsuite>'
        '<testcase name="test_A01_scostamento"/>'
        '<testcase name="test_A01_bis_salvataggio"><failure message="x"/></testcase>'
        '<testcase name="test_C02_dso"><skipped/></testcase>'
        '<testcase name="A06 un solo comando"/>'
        '<testcase name="test_kit_la_base"/>'
        '</testsuite></testsuites>')
    assert esiti_junit(x) == {"A01": "fail", "C02": "skip", "A06": "pass"}
```

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_triage_rilievi_tool.py -q -p no:warnings`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.triage_rilievi'` (se `tools/` non è un package, crea anche `tools/__init__.py` solo se manca e ledgera).

- [ ] **Step 2: lo script**

`tools/triage_rilievi.py`:

```python
"""Verdetto del banco di triage AMBIENTA: stesse suite su 62bfed1 e su HEAD, esito per rilievo nel foglio.

Uso: python tools/triage_rilievi.py   (dal worktree del banco; scrive inbox/Verifica_piano_Ambienta_triage.xlsx)
"""
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

VECCHIO = "62bfed1"
PY = "/home/peter/DEV/budget/backend/venv/bin/python"
NODE_MODULES = "/home/peter/DEV/budget/frontend/node_modules"
BANCO = ["tests/rilievi_kit.py", "tests/test_rilievi_ambienta.py", "tests/fixtures/ambienta_2026.json",
         "frontend/lib/rilievi-ambienta.test.ts"]
_ID = re.compile(r"^(?:test_)?([A-E]\d{2})[_ ]")
_PESO = {"fail": 3, "pass": 2, "skip": 1}


def verdetto(vecchio, nuovo) -> str:
    if nuovo is None:
        return "Senza test"
    if vecchio == "skip" or vecchio is None:
        base = "Confermato" if nuovo == "fail" else "Non riprodotto"
        return f"{base} (n/a su {VECCHIO})"
    return {("fail", "fail"): "Confermato", ("fail", "pass"): "Risolto (2026-09-24)",
            ("pass", "pass"): "Non riprodotto", ("pass", "fail"): "Regressione"}.get((vecchio, nuovo), f"{vecchio}/{nuovo}")


def esiti_junit(path) -> dict:
    out = {}
    for tc in ET.parse(path).iter("testcase"):
        m = _ID.match(tc.get("name", ""))
        if not m:
            continue
        esito = ("fail" if tc.find("failure") is not None or tc.find("error") is not None
                 else "skip" if tc.find("skipped") is not None else "pass")
        rid = m.group(1)
        if _PESO[esito] > _PESO.get(out.get(rid), 0):
            out[rid] = esito
    return out


def _suite(root: Path, tag: str, out: Path) -> dict:
    py_xml, js_xml = out / f"{tag}-pytest.xml", out / f"{tag}-vitest.xml"
    subprocess.run([PY, "-m", "pytest", "tests/test_rilievi_ambienta.py", "-q", "-p", "no:warnings",
                    f"--junitxml={py_xml}"], cwd=root)
    nm = root / "frontend" / "node_modules"
    if not nm.exists():
        nm.symlink_to(NODE_MODULES)
    subprocess.run(["npx", "vitest", "run", "lib/rilievi-ambienta.test.ts", "--reporter=junit",
                    f"--outputFile={js_xml}"], cwd=root / "frontend")
    esiti = {}
    for x in (py_xml, js_xml):
        if x.exists():
            for rid, e in esiti_junit(x).items():
                if _PESO[e] > _PESO.get(esiti.get(rid), 0):
                    esiti[rid] = e
    return esiti


def main() -> int:
    qui = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    out = qui / ".superpowers" / "triage"
    out.mkdir(parents=True, exist_ok=True)
    vecchio = out / f"wt-{VECCHIO}"
    if not vecchio.exists():
        subprocess.run(["git", "worktree", "add", "--detach", str(vecchio), VECCHIO], cwd=qui, check=True)
    for f in BANCO:
        (vecchio / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(qui / f, vecchio / f)
    e_old, e_new = _suite(vecchio, "vecchio", out), _suite(qui, "nuovo", out)

    import openpyxl
    src = qui / "inbox" / "Verifica_piano_Ambienta_problemi.xlsx"
    wb = openpyxl.load_workbook(src)
    ws = wb["Elenco problemi"]
    for r in range(5, ws.max_row + 1):
        rid = ws.cell(r, 1).value
        if not rid or ws.cell(r, 10).value != "Softwarista":
            continue
        v = verdetto(e_old.get(rid), e_new.get(rid))
        ws.cell(r, 11).value = v
        ws.cell(r, 12).value = f"banco: {VECCHIO}={e_old.get(rid, '-')}, HEAD={e_new.get(rid, '-')}"
        print(f"{rid:4} {v}")
    dst = qui / "inbox" / "Verifica_piano_Ambienta_triage.xlsx"
    wb.save(dst)
    print(f"scritto {dst}")
    subprocess.run(["git", "worktree", "remove", "--force", str(vecchio)], cwd=qui)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: verde**

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_triage_rilievi_tool.py -q -p no:warnings`
Expected: `2 passed`

- [ ] **Step 4: commit**

```bash
cd /home/peter/DEV/budget-rilievi && git add tools/triage_rilievi.py tests/test_triage_rilievi_tool.py && git commit -m "test(rilievi): script del verdetto su 62bfed1 e HEAD, esito nel foglio

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: esecuzione del triage e suite verde

**Files:**
- Modify: `tests/test_rilievi_ambienta.py`, `frontend/lib/rilievi-ambienta.test.ts` (solo marcatori)
- Create: `docs/superpowers/allineamento/2026-09-25-triage-rilievi-ambienta.md`

- [ ] **Step 1: il verdetto**

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python tools/triage_rilievi.py 2>&1 | tail -40`
Expected: una riga per ogni rilievo «Softwarista» (A01-A06, B01-B05, C01-C09, E04, E05) con il verdetto, e `scritto …/inbox/Verifica_piano_Ambienta_triage.xlsx`. E04 esce «Senza test» (fuori perimetro, spec §6). E05 esce dal test di caratterizzazione: nel rapporto va scritto «caratterizzazione, non verdetto».

- [ ] **Step 2: rapporto**

Scrivi `docs/superpowers/allineamento/2026-09-25-triage-rilievi-ambienta.md`: tabella ID | verdetto | test | una riga sul meccanismo, copiata dall'output dello Step 1 e dai messaggi di asserzione dei rossi (`.superpowers/triage/nuovo-pytest.xml`). In testa: commit confrontati, data, e il fatto che la base è AMBIENTA 2026 locale e non quella del consulente.

- [ ] **Step 3: suite verde senza nascondere nulla**

Per ogni test ROSSO su HEAD aggiungi `@pytest.mark.xfail(strict=True, reason="<ID> confermato dal triage 2026-09-25: <meccanismo>")` (pytest) o sostituisci `it(` con `it.fails(` e aggiungi il commento `// <ID> confermato dal triage 2026-09-25` (Vitest). Solo dopo lo Step 1: il verdetto va letto sui test nudi.

Run: `cd /home/peter/DEV/budget-rilievi && /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_rilievi_ambienta.py tests/test_triage_rilievi_tool.py -q -p no:warnings 2>&1 | tail -3 && cd frontend && npx vitest run lib/rilievi-ambienta.test.ts 2>&1 | tail -4`
Expected: pytest `N passed, M xfailed`, nessun `failed`; Vitest tutto verde (i `fails` contano come passati).

- [ ] **Step 4: commit**

```bash
cd /home/peter/DEV/budget-rilievi && git add tests/test_rilievi_ambienta.py frontend/lib/rilievi-ambienta.test.ts docs/superpowers/allineamento/2026-09-25-triage-rilievi-ambienta.md && git commit -m "test(rilievi): verdetto del triage AMBIENTA e rilievi confermati marcati xfail strict

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
