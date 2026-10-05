"""Fix finale 3: i percorsi di cassa nuovi dalla generazione alle due pagine del rendiconto.

Compensazione del credito tributario (#62 S14/S18, con e senza piano `crediti_tributari_breve`) e
giorni espliciti dei prodotti finiti (#62 nota S04): /analysis e la pagina Rendiconto mostrano le
stesse «imposte pagate», il rendiconto chiude sulla variazione della cassa dello SP, il foglio quadra.
"""
from decimal import Decimal as D

import pytest

from backend.app.services import analysis_service, calculation_service
from database.models import BudgetScenario, ForecastYear
from tests.rilievi_kit import BASE_BS, genera, generato, per_anno, righe
from tests.test_rilievi_61_62_magazzino import BS_PF

CENT = D("0.01")


def _due_pagine(out):
    """`ritocca`: legge /analysis e la pagina Rendiconto sullo scenario appena generato."""
    def _leggi(db, scenario_id):
        sc = db.query(BudgetScenario).get(scenario_id)
        analisi = analysis_service.get_complete_analysis(db, sc.company_id, scenario_id)
        pagina = calculation_service.calculate_detailed_cashflow_historical_and_forecast(
            db, sc.company_id, scenario_id, sc.base_year)
        out["analisi"] = {c["year"]: c for c in analisi["calculations"]["cashflow"]["years"]}
        out["pagina"] = {cf.year: cf for cf in pagina.cashflows}
        out["versate"] = {fy.year: D(fy.engine_meta["imposte_versate"]) for fy in
                          db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario_id)}
    return _leggi


def _piano_crediti(rows):
    rows[0]["pregresso"] = {"crediti_tributari_breve": {
        "opening": D("184140.58"), "amounts": [D("10000"), D("0"), D("0")]}}
    return rows


@pytest.mark.parametrize("con_piano", [False, True], ids=["senza_piano", "con_piano_crediti_tributari"])
def test_compensazione_imposte_pagate_uguali_sulle_due_pagine_e_rendiconto_chiude(con_piano):
    rows = righe()
    if con_piano:
        rows = _piano_crediti(rows)
    rows = per_anno(rows, "compensa_crediti_tributari", [True, True, True])
    out = {}
    e = generato(genera(rows, ritocca=_due_pagine(out)))
    assert e.det[2027]["imposte"]["credito_storico_compensato"] > D("0"), "la compensazione non e' scattata"
    visti = 0
    for anno in (2027, 2028, 2029):
        versate = out["versate"][anno]
        tp_pagina = out["pagina"][anno].operating_activities.cash_adjustments.taxes_paid
        tp_analisi = D(str(out["analisi"][anno]["operating"]["cash_adjustments"]["taxes_paid"]))
        assert tp_pagina == -versate.quantize(CENT)
        assert tp_analisi == tp_pagina
        # il rendiconto chiude sulla variazione di cassa dello SP
        prec = e.anni[anno - 1][0] if anno - 1 in e.anni else BASE_BS
        rec = out["pagina"][anno].cash_reconciliation
        assert rec.verification_ok is True
        assert rec.total_cashflow == rec.cash_ending - rec.cash_beginning
        assert rec.total_cashflow == (e.anni[anno][0]["sp09_disponibilita_liquide"]
                                      - prec["sp09_disponibilita_liquide"]).quantize(CENT)
        visti += 1
    assert visti == 3


def test_dio_pf_esplicito_ce02_e_la_variazione_di_sp05b_sp05d_e_il_foglio_quadra():
    e = generato(genera(righe(dio_pf_days=10), bs=BS_PF))
    ap_b, ap_d = D("0"), BS_PF["sp05d_prodotti_finiti"]
    for anno in (2027, 2028, 2029):
        sp, ce = e.anni[anno]
        chiusura = sp["sp05b_prodotti_in_corso"] + sp["sp05d_prodotti_finiti"]
        assert abs(ce["ce02_variazioni_rimanenze"] - (chiusura - (ap_b + ap_d))) <= CENT, anno
        assert abs(sp["_total_assets"] - sp["_total_liabilities"]) <= CENT, anno
        ap_b, ap_d = sp["sp05b_prodotti_in_corso"], sp["sp05d_prodotti_finiti"]
