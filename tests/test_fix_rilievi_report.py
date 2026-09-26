"""A01-bis (lotto 2 fix rilievi, 2026-09-26): avviso di previsionale vecchio nel PDF, nel Word e su
/report — sia per ipotesi salvate dopo l'ultima generazione (`forecast_stale`), sia per un
previsionale generato da una versione precedente del motore (`engine_version_stale`)."""
from decimal import Decimal as D

import pytest

from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, righe

FRASE_FORECAST_STALE = "Previsionale precedente alle ipotesi salvate: da rigenerare"
FRASE_ENGINE_STALE = "Previsionale generato da una versione precedente del motore: da rigenerare"


_MUTUO_A = {"name": "Finanziamento A", "amount": 0, "opening_residual": 467528.52, "interest_rate": 4,
            "grace_years": 0, "balloon_pct": 0, "duration_years": None,
            "repayments": [53409, 53409, 53409, 53409]}


def _banche(fidi: float, residuo: float) -> dict:
    """Copiato da `test_rilievi_ambienta.py::_banche`: fidi + residuo del mutuo A che non quadrano col
    bilancio (scarto 11.000) — il salvataggio bulk lo respinge."""
    return {"financing_loans": [{**_MUTUO_A, "opening_residual": residuo}], "bank_lines_amount": fidi,
            "bank_lines_rule": "costante", "bank_lines_rate": 6}


def _bp():
    pytest.importorskip("backend.app.renderers.business_plan.data")


def _pdf_text(pdf: bytes) -> str:
    import fitz
    return "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))


def _docx_text(data: bytes) -> str:
    from backend.app.renderers.docx_export import docx_text
    return "\n".join(docx_text(data))


def _con_previsionale_vecchio():
    """Un salvataggio respinto: a schermo resta il previsionale precedente, salvato con `prima`."""
    buone = righe()
    respinte = righe()
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    respinte[0].update(_banche(311000, float(banche - D("300000"))))
    e = genera(respinte, prima=buone, report=True)
    if e.res["forecast_generated"] is not False:
        pytest.fail("precondizione: il salvataggio doveva essere respinto")
    if e.rep is None:
        pytest.fail("precondizione: il report non si costruisce sul previsionale vecchio")
    return e


def test_a_triage_forecast_stale_senza_marcatore():
    """(a) Il test del triage: report bloccato, diagnostica `forecast_stale`, frase nel PDF in bozza."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan
    e = _con_previsionale_vecchio()
    assert e.rep.readiness.status == "blocked", e.rep.readiness
    assert any(d.code == "forecast_stale" for d in e.rep.diagnostics)
    assert e.data.avvisi and e.data.avvisi[0] == FRASE_FORECAST_STALE
    testo = _pdf_text(render_business_plan(e.data)).lower()
    assert FRASE_FORECAST_STALE.lower() in testo


def test_b_la_frase_e_nel_docx():
    """(b) Lo stesso avviso è nel .docx, sullo stesso `BusinessPlanData`."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan_docx
    e = _con_previsionale_vecchio()
    testo = _docx_text(render_business_plan_docx(e.data))
    assert FRASE_FORECAST_STALE in testo


def test_c_engine_version_stale_diagnostica_e_frase():
    """(c) Un previsionale generato e poi ritoccato a mano con `engine_meta` di una versione precedente
    del motore: diagnostica `engine_version_stale` e frase nel PDF."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan

    def ritocca(db, scenario_id):
        from database.models import ForecastYear
        rows = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario_id).all()
        assert rows, "precondizione: nessun ForecastYear da ritoccare"
        rows[0].engine_meta = {"engine_version": "1", "pareggio": None}

    e = generato(genera(righe(), report=True, ritocca=ritocca))
    assert any(d.code == "engine_version_stale" for d in e.rep.diagnostics), e.rep.diagnostics
    assert e.rep.readiness.status == "blocked", e.rep.readiness
    assert FRASE_ENGINE_STALE in e.data.avvisi
    testo = _pdf_text(render_business_plan(e.data)).lower()
    assert FRASE_ENGINE_STALE.lower() in testo


def test_d_engine_meta_none_nessuna_diagnostica():
    """(d) `engine_meta = None` non è un "prima": nessuna diagnostica `engine_version_stale`."""
    _bp()

    def ritocca(db, scenario_id):
        from database.models import ForecastYear
        rows = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario_id).all()
        assert rows, "precondizione: nessun ForecastYear da ritoccare"
        for row in rows:
            row.engine_meta = None

    e = generato(genera(righe(), report=True, ritocca=ritocca))
    assert not any(d.code == "engine_version_stale" for d in e.rep.diagnostics), e.rep.diagnostics
    assert FRASE_ENGINE_STALE not in e.data.avvisi


def test_e_report_pulito_nessun_avviso():
    """(e) Un report senza diagnostiche di previsionale vecchio: `avvisi == ()` e il PDF non contiene
    «da rigenerare»."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan
    e = generato(genera(righe(), report=True))
    assert e.data.avvisi == ()
    testo = _pdf_text(render_business_plan(e.data)).lower()
    assert "da rigenerare" not in testo


class _RigaFinta:
    """Un `ForecastYear` finto: solo l'attributo che `_engine_version_stale` legge."""

    def __init__(self, engine_meta):
        self.engine_meta = engine_meta


def test_helper_infrannuale_non_e_mai_candidato():
    """`_engine_version_stale` esclude `workflow == "infrannuale"` a monte, anche con una riga
    palesemente vecchia: costruire uno scenario infrannuale intero solo per questo sarebbe un
    bilancio inventato in più (vietato dai vincoli del lotto) per provare un `if` di una riga."""
    from backend.app.services.final_report_service import _engine_version_stale
    righe_vecchie = [_RigaFinta({"engine_version": "1", "pareggio": None})]
    assert _engine_version_stale("infrannuale", righe_vecchie) is False
    assert _engine_version_stale("bilancio", righe_vecchie) is True
    assert _engine_version_stale("startup", righe_vecchie) is True


def test_helper_engine_meta_assente_o_senza_versione_non_e_stale():
    from backend.app.services.final_report_service import _engine_version_stale
    from calculations.forecast_engine import ENGINE_VERSION
    assert _engine_version_stale("bilancio", [_RigaFinta(None)]) is False
    assert _engine_version_stale("bilancio", [_RigaFinta({"pareggio": None})]) is False
    assert _engine_version_stale("bilancio", [_RigaFinta({"engine_version": ENGINE_VERSION})]) is False


# ===========================================================================
# Task 3 (lotto 2 fix rilievi, 2026-09-26): C02, C03, C04, C06, C07 — formule
# degli indici alla fonte, una definizione per indice. Gli oracoli del triage
# vivono in test_rilievi_ambienta.py (marcatori xfail rimossi in questo lotto);
# qui i test unitari sulle regole di formula stesse.
# ===========================================================================

from calculations.report_indicators import financial_debt_total, indicator_results
from calculations.ratios import FinancialRatiosCalculator


def _getter(**valori):
    return lambda field: valori.get(field, D("0"))


def test_financial_debt_total_e_somma_incondizionata_anche_con_banche_positive():
    """C03/C04: niente più ramo «banche>0 else fallback» — banche, altri finanziatori e
    obbligazioni si sommano sempre, anche quando le banche da sole sono già positive."""
    v = _getter(
        sp16a_debiti_banche_breve=D("493408.90"), sp17a_debiti_banche_lungo=D("467528.52"),
        sp17b_debiti_altri_finanz_lungo=D("36503.74"),
        sp16d_debiti_fornitori_breve=D("548578.07"), sp16e_debiti_tributari_breve=D("184140.58"),
    )
    atteso = D("493408.90") + D("467528.52") + D("36503.74")
    assert financial_debt_total(v) == atteso


def test_financial_debt_total_esclude_fornitori_tributari_e_previdenziali():
    """Fornitori, tributari e previdenziali non sono debito finanziario, in nessun caso —
    con o senza debito bancario."""
    v = _getter(sp16d_debiti_fornitori_breve=D("1000000"), sp16e_debiti_tributari_breve=D("50000"),
                sp16f_debiti_previdenza_breve=D("20000"))
    assert financial_debt_total(v) == D("0")


def _statements(bs_over=None, ce_over=None):
    """`BalanceSheet`/`IncomeStatement` con i default di colonna applicati da un commit reale su un
    DB in memoria, base AMBIENTA (`tests/rilievi_kit.BASE_BS`/`BASE_CE`) più eventuali ritocchi —
    niente bilanci inventati."""
    from tests.e2e_kit import memory_sessions
    from database.models import BalanceSheet, Company, FinancialYear, IncomeStatement
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company = Company(name="UNIT", tax_id="UNIT-C02-C07", sector=1, user_id="unit")
            db.add(company); db.flush()
            fy = FinancialYear(company_id=company.id, year=2026, period_months=None)
            db.add(fy); db.flush()
            bs = BalanceSheet(financial_year_id=fy.id, **{**BASE_BS, **(bs_over or {})})
            inc = IncomeStatement(financial_year_id=fy.id, **{**BASE_CE, **(ce_over or {})})
            db.add(bs); db.add(inc); db.commit()
            db.refresh(bs); db.refresh(inc)
            db.expunge(bs); db.expunge(inc)
            return bs, inc
    finally:
        engine.dispose()


def test_C02_dio_sul_consumo_di_materie_prime():
    """C02 · DIO = rimanenze / (materie prime + variazione rimanenze materie prime) × 360,
    coerente con `calculations/forecast_engine.py::consumo_base_materie`."""
    bs, inc = _statements()
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    consumo = BASE_CE["ce05_materie_prime"] + BASE_CE["ce10_var_rimanenze_mat_prime"]
    atteso = (D("360") * BASE_BS["sp05_rimanenze"] / consumo).quantize(D("1"))
    assert activity.inventory_turnover_days == atteso


def test_C02_dso_sui_soli_crediti_commerciali_in_ratios_py():
    """C02 · DSO = (sp06a + sp07a) / ricavi × 360 — non l'aggregato sp06 + sp07, che comprende
    crediti tributari e diversi."""
    bs, inc = _statements()
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    atteso = (D("360") * (BASE_BS["sp06a_crediti_clienti_breve"] + BASE_BS["sp07a_crediti_clienti_lungo"])
              / BASE_CE["ce01_ricavi_vendite"]).quantize(D("1"))
    assert activity.receivables_turnover_days == atteso


def test_dio_indefinito_con_consumo_zero_e_dichiarato_nel_report():
    """Un consumo di materie a zero rende il DIO indefinito, non zero: il report lo dichiara
    `zero_denominator` e non pubblica un valore — «diagnose, never fabricate»."""
    bs_dict = dict(BASE_BS)
    ce_dict = {**BASE_CE, "ce05_materie_prime": D("0"), "ce10_var_rimanenze_mat_prime": D("0")}
    analytical = {"activity": {"inventory_turnover_days": D("0")}}
    res = indicator_results(bs_dict, ce_dict, analytical)
    r = res["analytical.activity.inventory_turnover_days"]
    assert r.value is None and r.reason == "zero_denominator", r


def test_dio_indefinito_con_consumo_negativo_e_dichiarato_nel_report():
    """Un consumo negativo (variazione rimanenze che eccede gli acquisti) non è zero ma resta
    indefinito: reason `non_positive_denominator`, mai un DIO negativo pubblicato."""
    bs_dict = dict(BASE_BS)
    ce_dict = {**BASE_CE, "ce05_materie_prime": D("100"), "ce10_var_rimanenze_mat_prime": D("-500")}
    analytical = {"activity": {"inventory_turnover_days": D("-129.6")}}
    res = indicator_results(bs_dict, ce_dict, analytical)
    r = res["analytical.activity.inventory_turnover_days"]
    assert r.value is None and r.reason == "non_positive_denominator", r


def test_C03_rod_divide_per_il_debito_finanziario_in_ratios_py():
    """C03 · ROD = oneri finanziari / debito finanziario (banche, altri finanziatori,
    obbligazioni) — non / debiti totali, che includono i fornitori."""
    bs, inc = _statements()
    profitability = FinancialRatiosCalculator(bs, inc).calculate_profitability_ratios()
    fin = (BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
           + BASE_BS["sp17b_debiti_altri_finanz_lungo"])
    atteso = (BASE_CE["ce15_oneri_finanziari"] / fin).quantize(D("0.0001"))
    assert profitability.rod == atteso


def test_C06_leverage_ratio_e_debiti_totali_su_patrimonio_netto():
    """C06 · «Indice di Indebitamento» (All. E, `solvency.leverage_ratio`) = debiti totali /
    patrimonio netto — non immobilizzazioni / PN, che è una leva sugli investimenti, non
    sull'indebitamento. Stessa definizione di `debt_to_equity`: un solo calcolo."""
    bs, inc = _statements()
    solvency = FinancialRatiosCalculator(bs, inc).calculate_solvency_ratios()
    assert solvency.leverage_ratio == solvency.debt_to_equity


def test_C06_indice_di_indebitamento_none_con_patrimonio_netto_zero():
    """Patrimonio netto a zero: l'indice non può essere zero (nessuna leva è "nessuna leva"),
    è indefinito — dichiarato `zero_denominator`, mai pubblicato come 0."""
    bs_dict = {**BASE_BS, "sp11_capitale": D("0"), "sp12_riserve": D("0"), "sp13_utile_perdita": D("0")}
    analytical = {"solvency": {"leverage_ratio": D("0")}}
    res = indicator_results(bs_dict, dict(BASE_CE), analytical)
    r = res["analytical.solvency.leverage_ratio"]
    assert r.value is None and r.reason == "zero_denominator", r


def test_C07_copertura_immob_include_il_tfr_in_ratios_py():
    """C07 · Copertura immobilizzazioni analitica = (PN + debiti oltre 12 mesi + TFR) /
    immobilizzazioni — il TFR è una fonte consolidata, non solo i debiti a lungo."""
    bs, inc = _statements()
    coverage = FinancialRatiosCalculator(bs, inc).calculate_coverage_ratios()
    pn = BASE_BS["sp11_capitale"] + BASE_BS["sp12_riserve"] + BASE_BS["sp13_utile_perdita"]
    fixed = BASE_BS["sp02_immob_immateriali"] + BASE_BS["sp03_immob_materiali"] + BASE_BS["sp04_immob_finanziarie"]
    atteso = ((pn + BASE_BS["sp17_debiti_lungo"] + BASE_BS["sp15_tfr"]) / fixed).quantize(D("0.0001"))
    assert coverage.fixed_assets_coverage_with_equity_and_ltdebt == atteso


def test_C07_copertura_immob_practice_include_il_tfr():
    """C07 · La stessa regola nella convenzione `practice` (Sez. 8, All. D): (PN + debiti oltre 12
    mesi + TFR) / immobilizzazioni × 100."""
    bs_dict = dict(BASE_BS)
    ce_dict = dict(BASE_CE)
    res = indicator_results(bs_dict, ce_dict, {})
    pn = BASE_BS["sp11_capitale"] + BASE_BS["sp12_riserve"] + BASE_BS["sp13_utile_perdita"]
    fixed = BASE_BS["sp02_immob_immateriali"] + BASE_BS["sp03_immob_materiali"] + BASE_BS["sp04_immob_finanziarie"]
    atteso = (pn + BASE_BS["sp17_debiti_lungo"] + BASE_BS["sp15_tfr"]) / fixed * D("100")
    r = res["practice.copertura_immob"]
    assert r.value is not None and abs(r.value - atteso) < D("0.01"), (r.value, atteso)


def test_C07_copertura_immob_practice_none_con_immobilizzazioni_zero():
    """Immobilizzazioni a zero: copertura indefinita, non zero né infinita — `zero_denominator`."""
    bs_dict = {**BASE_BS, "sp02_immob_immateriali": D("0"), "sp03_immob_materiali": D("0"),
               "sp04_immob_finanziarie": D("0")}
    res = indicator_results(bs_dict, dict(BASE_CE), {})
    r = res["practice.copertura_immob"]
    assert r.value is None and r.reason == "zero_denominator", r
