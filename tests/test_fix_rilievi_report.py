"""A01-bis (lotto 2 fix rilievi, 2026-09-26): avviso di previsionale vecchio nel PDF, nel Word e su
/report — sia per ipotesi salvate dopo l'ultima generazione (`forecast_stale`), sia per un
previsionale generato da una versione precedente del motore (`engine_version_stale`)."""
from decimal import ROUND_HALF_UP
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


def test_d_engine_meta_none_su_budget_e_da_rigenerare():
    from backend.app.services.final_report_service import _engine_version_stale
    class FY:  # riga senza firma, come i previsionali generati prima del 2026-09-26
        engine_meta = None
    assert _engine_version_stale("bilancio", [FY()]) is True
    assert _engine_version_stale("infrannuale", [FY()]) is False
    class FY2:
        engine_meta = {"pareggio": None}  # senza engine_version
    assert _engine_version_stale("bilancio", [FY2()]) is True


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


def test_helper_engine_meta_assente_o_senza_versione_e_stale_sul_budget():
    from backend.app.services.final_report_service import _engine_version_stale
    from calculations.forecast_engine import ENGINE_VERSION
    assert _engine_version_stale("bilancio", [_RigaFinta(None)]) is True
    assert _engine_version_stale("bilancio", [_RigaFinta({"pareggio": None})]) is True
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
    atteso = (D("360") * BASE_BS["sp05_rimanenze"] / consumo).quantize(D("1"), rounding=ROUND_HALF_UP)
    assert activity.inventory_turnover_days == atteso


def test_C02_dso_sui_soli_crediti_commerciali_in_ratios_py():
    """C02 · DSO = (sp06a + sp07a) / ricavi × 360 — non l'aggregato sp06 + sp07, che comprende
    crediti tributari e diversi."""
    bs, inc = _statements()
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    atteso = (D("360") * (BASE_BS["sp06a_crediti_clienti_breve"] + BASE_BS["sp07a_crediti_clienti_lungo"])
              / BASE_CE["ce01_ricavi_vendite"]).quantize(D("1"), rounding=ROUND_HALF_UP)
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
    atteso = (BASE_CE["ce15_oneri_finanziari"] / fin).quantize(D("0.0001"), rounding=ROUND_HALF_UP)
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
    atteso = ((pn + BASE_BS["sp17_debiti_lungo"] + BASE_BS["sp15_tfr"]) / fixed).quantize(D("0.0001"), rounding=ROUND_HALF_UP)
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


# ===========================================================================
# Fix round 1 (review lotto 2, 2026-09-26): ROD e DIO indefiniti sono `None` alla FONTE
# (`calculations/ratios.py`), non solo dichiarati dal report. La pagina Indici legge
# `GET /companies/{id}/scenarios/{scenario_id}/ratios` (`calculation_service.calculate_ratios_
# historical_and_forecast`, `response_model=Any`) che non passa mai da `report_indicators.py`:
# senza il `None` alla fonte un'azienda senza debito finanziario, o senza una riga di materie
# prime distinta (entrambi comuni), mostrava un ROD/DIO di 0 silenzioso invece di «n.d.», e
# `_convert_namedtuple_to_dict` lo avrebbe comunque riscritto a 0.0 anche se non lo fosse stato.
# ===========================================================================

_NESSUN_DEBITO_FINANZIARIO = {
    "sp16a_debiti_banche_breve": D("0"), "sp17a_debiti_banche_lungo": D("0"),
    "sp16b_debiti_altri_finanz_breve": D("0"), "sp17b_debiti_altri_finanz_lungo": D("0"),
    "sp16c_debiti_obbligazioni_breve": D("0"), "sp17c_debiti_obbligazioni_lungo": D("0"),
}


def test_rod_none_senza_debito_finanziario():
    """ROD = None quando l'azienda non ha banche, altri finanziatori o obbligazioni (comune: tutto
    debito verso fornitori) — zero non è un costo del denaro misurato."""
    bs, inc = _statements(bs_over=_NESSUN_DEBITO_FINANZIARIO)
    profitability = FinancialRatiosCalculator(bs, inc).calculate_profitability_ratios()
    assert profitability.rod is None


def test_dio_none_con_consumo_zero_alla_fonte():
    """DIO = None quando il consumo di materie prime è zero (es. un'azienda di servizi senza una
    riga di materie distinta) — alla fonte in `ratios.py`, non solo nel report."""
    bs, inc = _statements(ce_over={"ce05_materie_prime": D("0"), "ce10_var_rimanenze_mat_prime": D("0")})
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    assert activity.inventory_turnover_days is None


def test_dio_none_con_consumo_negativo_alla_fonte():
    """DIO = None quando il consumo è negativo (variazione rimanenze che eccede gli acquisti):
    mai un giorno di magazzino negativo pubblicato."""
    bs, inc = _statements(ce_over={"ce05_materie_prime": D("100"), "ce10_var_rimanenze_mat_prime": D("-500")})
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    assert activity.inventory_turnover_days is None


def test_cash_conversion_cycle_none_quando_il_dio_lo_e():
    """Il ciclo di conversione del denaro non somma un DIO indefinito: None, non un ciclo che
    ignora il magazzino."""
    bs, inc = _statements(ce_over={"ce05_materie_prime": D("0"), "ce10_var_rimanenze_mat_prime": D("0")})
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    assert activity.inventory_turnover_days is None
    assert activity.cash_conversion_cycle is None


def test_spread_none_quando_il_rod_lo_e():
    """Lo spread ROI-ROD non sottrae un ROD indefinito: None, non uno spread che include un costo
    del denaro mai misurato."""
    bs, inc = _statements(bs_over=_NESSUN_DEBITO_FINANZIARIO)
    calc = FinancialRatiosCalculator(bs, inc)
    assert calc.calculate_profitability_ratios().rod is None
    assert calc.calculate_extended_profitability_ratios().spread is None


def test_convert_namedtuple_to_dict_non_riscrive_none_a_zero():
    """`_convert_namedtuple_to_dict` (calculation_service.py) è dietro l'unico endpoint che legge
    la pagina Indici multi-anno (`.../scenarios/{id}/ratios`, `response_model=Any`, nessuna
    validazione Pydantic): un `None` deve arrivare come `None`, non come lo `0.0` che riscriveva
    prima del fix — «diagnose, never fabricate» vale anche in serializzazione."""
    from backend.app.services.calculation_service import _convert_namedtuple_to_dict
    bs, inc = _statements(bs_over=_NESSUN_DEBITO_FINANZIARIO)
    profitability = FinancialRatiosCalculator(bs, inc).calculate_profitability_ratios()
    d = _convert_namedtuple_to_dict(profitability)
    assert d["rod"] is None


def test_schema_ratios_accetta_rod_e_dio_none():
    """Gli schemi Pydantic (`backend/app/schemas/calculations.py`) validano `rod`,
    `inventory_turnover_days`, `cash_conversion_cycle` e `spread` a `None` senza sollevare: erano
    `float` non opzionali, e la validazione avrebbe rotto ogni endpoint tipizzato che li serve
    (`/companies/{id}/years/{year}/calculations/{ratios|complete}`) per un'azienda senza debito
    finanziario o senza una riga di materie prime distinta."""
    from backend.app.schemas import calculations as calc_schemas
    p = calc_schemas.ProfitabilityRatios(roe=0.1, roi=0.05, ros=0.02, rod=None,
                                          ebitda_margin=0.1, ebit_margin=0.05, net_margin=0.02)
    assert p.rod is None
    a = calc_schemas.ActivityRatios(asset_turnover=1.0, inventory_turnover_days=None,
                                     receivables_turnover_days=30, payables_turnover_days=60,
                                     working_capital_days=10, cash_conversion_cycle=None)
    assert a.inventory_turnover_days is None and a.cash_conversion_cycle is None
    e = calc_schemas.ExtendedProfitabilityRatios(spread=None, financial_leverage_effect=1.0,
                                                  ebitda_on_sales=0.1, financial_charges_on_revenue=0.02)
    assert e.spread is None


# ===========================================================================
# F1 (Critico, revisione finale lotto 2, 2026-09-26): DSO e PFN/ROD non diventano
# silenziosamente 0/−cassa quando i sottoconti di dettaglio sono tutti a zero ma
# l'aggregato non lo è (import abbreviati/riconciliati: crediti e debiti finiscono nei
# secchi di ripiego sp06g/sp16g/sp17g, ~98% dei bilanci annuali secondo CLAUDE.md).
# `None` con una ragione dichiarata, mai un dato inventato.
# ===========================================================================

_CREDITI_COMMERCIALI_NON_DETTAGLIATI = {
    "sp06a_crediti_clienti_breve": D("0"), "sp07a_crediti_clienti_lungo": D("0"),
    "sp06g_crediti_altri_breve": BASE_BS["sp06a_crediti_clienti_breve"] + BASE_BS["sp06g_crediti_altri_breve"],
    "sp07g_crediti_altri_lungo": (BASE_BS["sp07a_crediti_clienti_lungo"]
                                  + BASE_BS.get("sp07g_crediti_altri_lungo", D("0"))),
}


def test_dso_none_quando_i_crediti_commerciali_non_sono_dettagliati_alla_fonte():
    """DSO (`receivables_turnover_days`, ratios.py) = None quando sp06a+sp07a = 0 ma l'aggregato
    sp06+sp07 resta positivo: i crediti ci sono, solo non classificati come commerciali — zero
    giorni di credito sarebbe un dato inventato, non uno misurato."""
    bs, inc = _statements(bs_over=_CREDITI_COMMERCIALI_NON_DETTAGLIATI)
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    assert activity.receivables_turnover_days is None


def test_dso_resta_zero_quando_i_crediti_sono_davvero_zero():
    """Zero crediti commerciali E zero aggregato: qui lo zero è reale, non un buco di dettaglio —
    il DSO resta 0, non None."""
    zero_crediti = {"sp06a_crediti_clienti_breve": D("0"), "sp07a_crediti_clienti_lungo": D("0"),
                    "sp06_crediti_breve": D("0"), "sp07_crediti_lungo": D("0"),
                    "sp06e_crediti_tributari_breve": D("0"), "sp06g_crediti_altri_breve": D("0"),
                    "sp07e_crediti_tributari_lungo": D("0"), "sp07g_crediti_altri_lungo": D("0")}
    bs, inc = _statements(bs_over=zero_crediti)
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    assert activity.receivables_turnover_days == D("0")


def test_cash_conversion_cycle_none_quando_il_dso_lo_e():
    """Il ciclo di conversione del denaro non somma un DSO indefinito: None, non un ciclo che
    finge di conoscere i giorni di credito."""
    bs, inc = _statements(bs_over=_CREDITI_COMMERCIALI_NON_DETTAGLIATI)
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    assert activity.cash_conversion_cycle is None


def test_dso_dichiarato_nel_report_con_la_ragione_giusta():
    """Il report (Sez. 1/7, All. E) dichiara `trade_receivables_detail_unavailable`, non un
    generico `source_calculation_unavailable`: la pagina sa DIRE perché non lo sa."""
    bs_dict = {**BASE_BS, **_CREDITI_COMMERCIALI_NON_DETTAGLIATI}
    analytical = {"activity": {"receivables_turnover_days": None}}
    res = indicator_results(bs_dict, dict(BASE_CE), analytical)
    r = res["analytical.activity.receivables_turnover_days"]
    assert r.value is None and r.reason == "trade_receivables_detail_unavailable", r


_DEBITO_FINANZIARIO_NON_DETTAGLIATO = {
    **_NESSUN_DEBITO_FINANZIARIO,
    "sp16g_altri_debiti_breve": BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp16g_altri_debiti_breve"],
    "sp17g_altri_debiti_lungo": (BASE_BS["sp17a_debiti_banche_lungo"] + BASE_BS["sp17b_debiti_altri_finanz_lungo"]
                                  + BASE_BS.get("sp17g_altri_debiti_lungo", D("0"))),
}


def test_pfn_none_quando_il_debito_finanziario_non_e_dettagliato():
    """PFN = None quando le sei sotto-voci finanziarie (sp16a/b/c, sp17a/b/c) sono tutte a zero
    ma sp16+sp17 (l'aggregato) resta positivo: non si può sapere quanto di quel debito è
    finanziario, e «PFN = −cassa» sarebbe falso — non «nessun debito», ma «non lo so»."""
    bs_dict = {**BASE_BS, **_DEBITO_FINANZIARIO_NON_DETTAGLIATO}
    res = indicator_results(bs_dict, dict(BASE_CE), {})
    r = res["practice.pfn"]
    assert r.value is None and r.reason == "financial_debt_detail_unavailable", r


def test_pfn_ebitda_none_quando_il_debito_finanziario_non_e_dettagliato():
    """PFN/EBITDA eredita la stessa indisponibilità della PFN: non può dividere un numeratore
    indefinito, anche se l'EBITDA è misurato."""
    bs_dict = {**BASE_BS, **_DEBITO_FINANZIARIO_NON_DETTAGLIATO}
    res = indicator_results(bs_dict, dict(BASE_CE), {})
    r = res["practice.pfn_ebitda"]
    assert r.value is None and r.reason == "financial_debt_detail_unavailable", r


def test_pfn_resta_calcolata_quando_il_debito_finanziario_e_dettagliato():
    """Con almeno una delle sei sotto-voci finanziarie diversa da zero (il caso normale, base
    AMBIENTA) la PFN resta un importo vero, non None: la nuova guardia non deve azzerare il
    caso comune."""
    res = indicator_results(dict(BASE_BS), dict(BASE_CE), {})
    r = res["practice.pfn"]
    assert r.value is not None and r.reason is None, r


def test_rod_analitico_dichiara_debito_finanziario_non_dettagliato():
    """`analytical.profitability.rod` distingue «nessun debito finanziario» (caso già gestito)
    da «debito finanziario non dettagliato»: qui l'aggregato sp16+sp17 è positivo, quindi la
    ragione dev'essere `financial_debt_detail_unavailable`, non un generico
    `source_calculation_unavailable`."""
    bs_dict = {**BASE_BS, **_DEBITO_FINANZIARIO_NON_DETTAGLIATO}
    analytical = {"profitability": {"rod": None}}
    res = indicator_results(bs_dict, dict(BASE_CE), analytical)
    r = res["analytical.profitability.rod"]
    assert r.value is None and r.reason == "financial_debt_detail_unavailable", r


# ===========================================================================
# F7 (Importante, revisione finale lotto 2, 2026-09-26): definizioni allineate, pagina Indici.
# `receivables_turnover_days` (DSO) usa sp06a+sp07a, ma stava etichettato "360/TdC" con TdC =
# RIC/(sp06+sp07): allineare TdC ai soli crediti commerciali. `working_capital_days` e TdCCN
# usano ancora `bs.working_capital_net` (il vecchio CCN, con sp07 dentro e senza sp10/sp18):
# passare al CCN nuovo di C05 (attivo corrente - passivo corrente).
# ===========================================================================

def test_tdc_turnover_sui_soli_crediti_commerciali():
    """TdC = RIC / (sp06a + sp07a) — non l'aggregato sp06+sp07, che comprende crediti tributari e
    diversi: altrimenti «360/TdC» e il DSO pubblicato (360 × crediti commerciali / ricavi) non sono
    la stessa coppia numeratore/denominatore."""
    bs, inc = _statements()
    turnover = FinancialRatiosCalculator(bs, inc).calculate_turnover_ratios()
    trade_receivables = BASE_BS["sp06a_crediti_clienti_breve"] + BASE_BS["sp07a_crediti_clienti_lungo"]
    atteso = (BASE_CE["ce01_ricavi_vendite"] / trade_receivables).quantize(D("0.0001"), rounding=ROUND_HALF_UP)
    assert turnover.receivables_turnover == atteso


def test_working_capital_days_sul_nuovo_ccn():
    """DCCN = 360 × CCN / ricavi, con il CCN di C05 (attivo corrente - passivo corrente,
    simmetrico sui ratei) — non più `BalanceSheet.working_capital_net` (sp07 dentro l'attivo,
    niente sp10/sp18)."""
    from calculations.report_indicators import attivo_corrente, passivo_corrente
    bs, inc = _statements()
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    field_value = lambda field: getattr(bs, field)
    ccn = attivo_corrente(field_value) - passivo_corrente(field_value)
    atteso = (D("360") * ccn / BASE_CE["ce01_ricavi_vendite"]).quantize(D("1"), rounding=ROUND_HALF_UP)
    assert activity.working_capital_days == atteso


def test_working_capital_days_diverge_dalla_vecchia_formula_su_ambienta():
    """Regressione: la vecchia formula (working_capital_net) dava un DCCN diverso su AMBIENTA."""
    bs, inc = _statements()
    activity = FinancialRatiosCalculator(bs, inc).calculate_activity_ratios()
    vecchio = (D("360") * bs.working_capital_net / BASE_CE["ce01_ricavi_vendite"]).quantize(D("1"), rounding=ROUND_HALF_UP)
    assert activity.working_capital_days != vecchio, (activity.working_capital_days, vecchio)


def test_tdccn_turnover_sul_nuovo_ccn():
    """TdCCN = RIC / CCN, stesso CCN nuovo di `working_capital_days` — un solo CCN in ogni
    formula che lo usa, non il vecchio `working_capital_net` qui e il nuovo altrove."""
    from calculations.report_indicators import attivo_corrente, passivo_corrente
    bs, inc = _statements()
    turnover = FinancialRatiosCalculator(bs, inc).calculate_turnover_ratios()
    field_value = lambda field: getattr(bs, field)
    ccn = attivo_corrente(field_value) - passivo_corrente(field_value)
    atteso = (BASE_CE["ce01_ricavi_vendite"] / ccn).quantize(D("0.0001"), rounding=ROUND_HALF_UP)
    assert turnover.working_capital_turnover == atteso
