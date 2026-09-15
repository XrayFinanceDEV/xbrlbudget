"""Altri finanziatori scadenziati per anno (spec 2026-09-15 §5.3).

Base: sp17b 150.000 (finanziamento soci, 0%). Rimborsi [0, 50.000, 0]. Oracolo: 2027 residuo
150.000 con 50.000 a breve (la rata 2028) e 100.000 a lungo; 2028 residuo 100.000, breve 0,
lungo 100.000; 2029 uguale (resta aperto). Al 2% gli interessi 2027 sono 3.000.
"""
from decimal import Decimal as D

from backend.app.services import assumptions_service, forecast_preview_service
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP16B, SP17B, CE15, SP09 = "sp16b_debiti_altri_finanz_breve", "sp17b_debiti_altri_finanz_lungo", "ce15_oneri_finanziari", "sp09_disponibilita_liquide"
SOCI = {"name": "Finanziamento soci", "opening_residual": 150000, "interest_rate": 0, "repayments": [0, 50000, 0]}


def _genera(user, rows, sp17b=D("150000")):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
            b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
            b.sp17b_debiti_altri_finanz_lungo = sp17b; b.sp17_debiti_lungo += sp17b
            b.sp09_disponibilita_liquide += sp17b
            db.commit()
            sc = BudgetScenario(company_id=company_id, name=user, base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows], auto_generate=True)
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            anni = {anno: (sp, ce) for anno, sp, ce in read_forecast_maps(db, sc.id)} if res["forecast_generated"] else {}
            det = {y["year"]: y["details"] for y in prev["forecast_years"]}
            return res, anni, det, prev["error"]
    finally:
        engine.dispose()


def _rows(soci=SOCI, **primo):
    base = {"tax_rate": 27.9}
    # Regime esplicito con soli fidi a zero: il kit non ha banche a breve, e sp17a 50.000 e'
    # coperto da un contratto senza rimborsi.
    r1 = {"forecast_year": 2027, "bank_lines_amount": 0, "bank_lines_rule": "costante", "bank_lines_rate": 0,
          "financing_loans": [{"opening_residual": 50000, "interest_rate": 0, "repayments": []}],
          "other_lenders": [soci], **base}
    r1.update(primo)
    return [r1, {"forecast_year": 2028, **base}, {"forecast_year": 2029, **base}]


def test_rimborsi_per_anno_e_quota_a_breve():
    res, anni, det, _ = _genera("soci", _rows())
    assert res["forecast_generated"] is True, res["message"]
    assert [(anni[a][0][SP16B], anni[a][0][SP17B]) for a in (2027, 2028, 2029)] == [
        (D("50000.00"), D("100000.00")), (D("0.00"), D("100000.00")), (D("0.00"), D("100000.00"))]
    a = det[2027]["altri_finanziatori"]
    assert a["mode"] == "contratti" and [D(str(a[k])) for k in ("apertura", "rimborso", "breve")] == [D("150000.00"), D("0.00"), D("50000.00")]
    b = det[2028]["altri_finanziatori"]
    assert [D(str(b[k])) for k in ("rimborso", "breve", "lungo")] == [D("50000.00"), D("0.00"), D("100000.00")]


def test_interessi_sul_residuo_di_apertura():
    res, anni, det, _ = _genera("soci-2pct", _rows(soci={**SOCI, "interest_rate": 2}))
    assert res["forecast_generated"] is True, res["message"]
    # apertura 2028 ancora 150.000; 2029 100.000
    assert [D(str(det[y]["altri_finanziatori"]["interessi"])) for y in (2027, 2028, 2029)] == [D("3000.00"), D("3000.00"), D("2000.00")]


def test_rifiuti_in_italiano():
    res, *_ = _genera("soci-non-quadra", _rows(soci={**SOCI, "opening_residual": 100000, "repayments": []}))
    assert res["forecast_generated"] is False and "altri finanziatori" in res["message"] and "coincidere" in res["message"]
    rows = _rows(); rows[0].pop("bank_lines_amount")
    res, *_ = _genera("soci-senza-regime", rows)
    assert res["forecast_generated"] is False and "Patrimoniale pregresso" in res["message"]


def test_senza_lista_il_comportamento_di_prima():
    rows = [{"forecast_year": 2027, "tax_rate": 27.9, "altri_finanz_repayment_years": 3}, {"forecast_year": 2028, "tax_rate": 27.9}]
    res, anni, det, _ = _genera("soci-anni", rows)
    assert res["forecast_generated"] is True, res["message"]
    assert anni[2027][0][SP17B] == D("100000.00") and det[2027]["altri_finanziatori"]["mode"] == "anni"
    assert det[2027]["altri_finanziatori"]["contratti"] == []


def test_guardia_su_prev_details_senza_blocco_fidi(monkeypatch):
    """(rilievo del coordinatore) L'apertura dei fidi per gli anni > 0 NON puo'
    ricadere in silenzio su `bank_lines_amount`: se i `details` dell'anno prima
    non dichiarano il blocco `fidi` il motore deve rifiutare, nominando l'anno.

    Il ramo non e' raggiungibile da un ciclo integro — `details['debito_bancario']`
    contiene sempre la riga `fidi` nel regime esplicito — quindi lo si simula
    tappando la dichiarazione, come il kernel fa con ogni altro stato viaggiante.
    """
    from calculations import forecast_engine as fe
    reale = fe._dichiara_debito_bancario

    def senza_fidi(debito, sweep, sp16a, sp17a, scoperto):
        d = reale(debito, sweep, sp16a, sp17a, scoperto)
        d.pop("fidi", None)
        return d

    monkeypatch.setattr(fe, "_dichiara_debito_bancario", senza_fidi)
    res, anni, det, err = _genera("fidi-det-mancanti", _rows())
    assert res["forecast_generated"] is False
    assert "fidi" in res["message"] and "2028" in res["message"]
    # Il percorso d'anteprima (stop_on_error=False) deve dare la STESSA ragione
    # in `error`, non un'eccezione nuda: l'anno 2027 esce calcolato, il piano si
    # ferma all'anno che non sa aprire i fidi.
    assert err is not None and err["year"] == 2028 and "2028" in err["message"]
    assert sorted(det) == [2027]
