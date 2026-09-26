"""C08 (lotto 2 fix rilievi, 2026-09-26): erogazioni e rimborsi su righe separate nel rendiconto.

Prima del fix, `financing_activities.third_party_funds` usciva sempre come un NETTO su una riga
sola (`increases`/`decreases` dal solo segno del residuo che fa quadrare la cassa): un anno con
erogazione 280.000 e rimborsi 88.409 mostrava un incremento di 191.591, non le due cifre vere.

Con `ForecastYear.engine_meta['erogazioni']` (scritto dal motore, `calculations.forecast_engine
.engine_meta`) noto, il rendiconto separa: `increases = erogazioni`, `decreases = erogazioni -
Δ` (Δ = il netto di sempre, `third_party_funds.net`, sul perimetro `financial_debt_total` — non
cambia). Senza quella chiave (anno storico, o previsionale generato prima di questo lotto) il
comportamento resta quello di sempre.
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from decimal import Decimal as D

from backend.app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from backend.app.services import assumptions_service
from database.models import BudgetScenario, FinancialYear, ForecastYear
from tests.e2e_kit import memory_sessions, seed_base_year

# Stesso scenario di `test_cashflow_debito_finanziario.test_caso_a_2027_torna_ai_valori_di_5197929`:
# un solo prestito nuovo, erogato nel 2027 (100.000,38/4 anni al 4,35%), nessun'altra erogazione
# negli anni successivi. Il netto dei mezzi di terzi che quello scenario fissa (75.000,29 nel 2027,
# -25.000,09 negli anni dopo) resta l'oracolo di riferimento anche qui.
PRESTITO = {"financing_amount": 100000.38, "financing_duration_years": 4, "financing_interest_rate": 4.35}
ANNI = (2027, 2028, 2029)
DELTA_2027 = D("75000.29")


def _genera(db, user):
    company_id, _ = seed_base_year(db, user_id=user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
    db.add(sc)
    db.commit()
    rows = [{"forecast_year": y, "revenue_growth_pct": 3.33, "tax_rate": 27.9} for y in ANNI]
    rows[0].update(PRESTITO)
    res = assumptions_service.bulk_upsert_assumptions(db, sc.id, rows, auto_generate=True)
    assert res["forecast_generated"] is True, res["message"]
    return fy, sc


def _forecast(db, sc, anno):
    return db.query(ForecastYear).filter(ForecastYear.scenario_id == sc.id, ForecastYear.year == anno).one()


def test_engine_meta_2027_dichiara_l_erogazione_del_prestito_nuovo():
    """`engine_meta['erogazioni']` porta l'importo erogato del contratto (100.000,38 nel 2027) e
    si dichiara comunque a zero nel 2028, dove non c'e' nessuna nuova erogazione."""
    engine, Session_ = memory_sessions()
    db = Session_()
    try:
        _, sc = _genera(db, "erogazioni-meta")
        fy2027 = _forecast(db, sc, 2027)
        fy2028 = _forecast(db, sc, 2028)
        assert fy2027.engine_meta["erogazioni"] == "100000.38"
        assert fy2028.engine_meta["erogazioni"] == "0.00"
    finally:
        db.close()
        engine.dispose()


def test_con_erogazioni_note_il_rendiconto_separa_incrementi_e_decrementi():
    """Con `erogazioni` noto: `increases = erogazioni`, `decreases = erogazioni - Δ`, `net`
    invariato. Senza (comportamento di prima): il netto esce su una riga sola."""
    engine, Session_ = memory_sessions()
    db = Session_()
    try:
        fy_base, sc = _genera(db, "erogazioni-separazione")
        fy2027 = _forecast(db, sc, 2027)
        erogazioni_2027 = D(fy2027.engine_meta["erogazioni"])
        assert erogazioni_2027 == D("100000.38")

        senza = DetailedCashFlowCalculator.calculate(
            bs_current=fy2027.balance_sheet, bs_previous=fy_base.balance_sheet,
            inc_current=fy2027.income_statement, year=2027,
        )
        delta = senza.financing_activities.third_party_funds.net
        assert delta == DELTA_2027
        # comportamento di prima: il netto esce su una riga sola (nessun rimborso separato).
        assert senza.financing_activities.third_party_funds.increases == delta
        assert senza.financing_activities.third_party_funds.decreases == D("0.00")
        assert senza.financing_activities.erogazioni_incoerenti is False

        con = DetailedCashFlowCalculator.calculate(
            bs_current=fy2027.balance_sheet, bs_previous=fy_base.balance_sheet,
            inc_current=fy2027.income_statement, year=2027, erogazioni=erogazioni_2027,
        )
        assert con.financing_activities.third_party_funds.net == delta  # Δ non cambia
        assert con.financing_activities.third_party_funds.increases == erogazioni_2027.quantize(D("0.01"))
        assert con.financing_activities.third_party_funds.decreases == (erogazioni_2027 - delta).quantize(D("0.01"))
        assert con.financing_activities.erogazioni_incoerenti is False
    finally:
        db.close()
        engine.dispose()


def test_senza_nuove_erogazioni_lo_zero_dichiarato_da_lo_stesso_risultato_di_prima():
    """2028: nessuna nuova erogazione, solo il rimborso della rata 2027. `engine_meta['erogazioni']`
    vale "0.00" (zero vero, non assenza): passarlo al calcolatore da' lo stesso risultato di prima."""
    engine, Session_ = memory_sessions()
    db = Session_()
    try:
        _, sc = _genera(db, "senza-erogazioni")
        fy2027 = _forecast(db, sc, 2027)
        fy2028 = _forecast(db, sc, 2028)

        senza = DetailedCashFlowCalculator.calculate(
            bs_current=fy2028.balance_sheet, bs_previous=fy2027.balance_sheet,
            inc_current=fy2028.income_statement, year=2028,
        )
        assert senza.financing_activities.total_financing_cashflow == D("-25000.09")
        assert senza.financing_activities.third_party_funds.increases == D("0.00")
        assert senza.financing_activities.third_party_funds.decreases == D("25000.09")

        con = DetailedCashFlowCalculator.calculate(
            bs_current=fy2028.balance_sheet, bs_previous=fy2027.balance_sheet,
            inc_current=fy2028.income_statement, year=2028,
            erogazioni=D(fy2028.engine_meta["erogazioni"]),
        )
        assert con.financing_activities.third_party_funds.increases == D("0.00")
        assert con.financing_activities.third_party_funds.decreases == D("25000.09")
        assert con.financing_activities.erogazioni_incoerenti is False
    finally:
        db.close()
        engine.dispose()


def test_erogazioni_incoerenti_tornano_al_netto_e_si_dichiarano():
    """Se le erogazioni note non bastano a spiegare l'aumento del debito finanziario (`decreases`
    negativo), non si inventa un rimborso negativo: si torna al netto di sempre e si dichiara."""
    engine, Session_ = memory_sessions()
    db = Session_()
    try:
        fy_base, sc = _genera(db, "erogazioni-incoerenti")
        fy2027 = _forecast(db, sc, 2027)

        cf = DetailedCashFlowCalculator.calculate(
            bs_current=fy2027.balance_sheet, bs_previous=fy_base.balance_sheet,
            inc_current=fy2027.income_statement, year=2027, erogazioni=D("10000.00"),
        )
        assert cf.financing_activities.erogazioni_incoerenti is True
        assert cf.financing_activities.third_party_funds.net == DELTA_2027
        assert cf.financing_activities.third_party_funds.increases == DELTA_2027
        assert cf.financing_activities.third_party_funds.decreases == D("0.00")
    finally:
        db.close()
        engine.dispose()


def test_analysis_service_alimenta_il_rendiconto_con_le_erogazioni_del_motore():
    """Integrazione: `analysis_service._calculate_cashflow` (chiamato dal ciclo su
    `all_years_data` di `calculate_analysis`) legge `engine_meta['erogazioni']` dell'anno di
    piano e lo passa al calcolatore, senza che il chiamante lo debba fare a mano."""
    from backend.app.services.analysis_service import _calculate_cashflow

    engine, Session_ = memory_sessions()
    db = Session_()
    try:
        fy_base, sc = _genera(db, "analysis-service")
        fy2027 = _forecast(db, sc, 2027)
        erogazioni = D(fy2027.engine_meta["erogazioni"])
        risultato = _calculate_cashflow(
            fy_base.balance_sheet, fy_base.income_statement,
            fy2027.balance_sheet, fy2027.income_statement, 2027, erogazioni,
        )
        financing = risultato["financing"]
        assert D(str(financing["third_party_funds"]["increases"])) == erogazioni
        assert D(str(financing["third_party_funds"]["decreases"])) == (erogazioni - DELTA_2027)

        # Un anno storico (nessun `engine_meta`) chiama _calculate_cashflow senza erogazioni,
        # come sempre: il default resta `None` e il comportamento non cambia.
        risultato_storico = _calculate_cashflow(
            fy_base.balance_sheet, fy_base.income_statement,
            fy2027.balance_sheet, fy2027.income_statement, 2027,
        )
        assert risultato_storico["financing"]["third_party_funds"]["net"] == \
            risultato["financing"]["third_party_funds"]["net"]
    finally:
        db.close()
        engine.dispose()


def test_narrativa_cita_i_rimborsi_di_ogni_anno_di_piano():
    """La sintesi (`narrative.key_points`) cita i rimborsi anno per anno, non il cumulato — dal
    lotto 2 erogazioni e rimborsi escono su righe separate nel rendiconto, e la sintesi segue lo
    stesso taglio invece di sommare le tre cifre in una sola."""
    from app.renderers.business_plan import fmt
    from app.renderers.business_plan.data import BusinessPlanData, Column
    from app.renderers.business_plan.narrative import key_points

    cols = (Column("closing:2026", 2026, "2026 F", True),) + tuple(
        Column(f"forecast:{y}", y, f"{y} P", False) for y in ANNI
    )
    valori = {
        "cf_operativo": [0, 100000, 50000, 60000],
        "cf_investimenti": [0, -20000, -10000, -10000],
        "cf_rimborsi": [0, 280000, 53409, 88409],
        "pfn": [960883, 721528, 469339, 73185],
        "pfn_ebitda": [5.794, 3.831, 1.188, 0.182],
    }
    values = {k: tuple(D(str(x)) for x in v) for k, v in valori.items()}
    data = BusinessPlanData(company_name="X", workflow="infrannuale", columns=cols, base_description="",
                            values=values, growth={}, residual_revenue=None)

    testo = " ".join(t for _, t in key_points(data))
    atteso = (f"{fmt.compact_eur(D('280000'))} nel 2027, {fmt.compact_eur(D('53409'))} nel 2028"
              f" e {fmt.compact_eur(D('88409'))} nel 2029")
    assert atteso in testo, testo


# ===========================================================================
# F3 (Importante, revisione finale lotto 2, 2026-09-26): la pagina Rendiconto
# (`GET /scenarios/{id}/detailed-cashflow`, `calculation_service.calculate_detailed_cashflow_
# historical_and_forecast`) chiamava `DetailedCashFlowCalculator.calculate` senza `erogazioni=`,
# quindi restava al netto anche dopo C08 — `analysis_service.py` (usato da `/analysis`) passava
# `engine_meta['erogazioni']`, questo servizio no: le due pagine mostravano numeri diversi per lo
# stesso anno di piano.
# ===========================================================================

def test_pagina_rendiconto_separa_erogazioni_e_rimborsi_come_analysis():
    """`calculate_detailed_cashflow_historical_and_forecast` (pagina Rendiconto) deve dare lo
    stesso incremento/decremento di mezzi di terzi di `analysis_service._calculate_cashflow`
    (pagina Indici/analisi) sullo stesso scenario: un'erogazione nota separa le due cifre in
    entrambe le pagine, non solo in una."""
    from backend.app.services import calculation_service

    engine, Session_ = memory_sessions()
    db = Session_()
    try:
        fy_base, sc = _genera(db, "rendiconto-pagina")
        fy2027 = _forecast(db, sc, 2027)
        erogazioni = D(fy2027.engine_meta["erogazioni"])

        risultato = calculation_service.calculate_detailed_cashflow_historical_and_forecast(
            db, fy_base.company_id, sc.id, sc.base_year
        )
        cf_2027 = next(cf for cf in risultato.cashflows if cf.year == 2027)
        financing = cf_2027.financing_activities.third_party_funds
        assert D(str(financing.increases)) == erogazioni, financing
        assert D(str(financing.decreases)) == (erogazioni - DELTA_2027), financing
    finally:
        db.close()
        engine.dispose()
