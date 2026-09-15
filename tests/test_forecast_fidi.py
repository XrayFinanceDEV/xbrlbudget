"""Fidi e anticipi separati dai mutui (spec 2026-09-15 §5.2, decisioni 5 e 9).

Base: sp16a 172.500 (fidi 90.000 + rata 2027 del mutuo 82.500), sp17a 247.500. Un mutuo da
330.000 al 3,8% con rimborsi [82.500, 82.500, 82.500]. Oracolo a mano, senza sweep:
- 2027: mutuo 247.500 → a breve la rata 2028 (82.500), a lungo 165.000; fidi 90.000 costanti;
  sp16a = 172.500, sp17a = 165.000; oneri = 12.540 (mutuo) + 4.500 (fidi al 5%) = 17.040.
- 2028: mutuo 165.000 → breve 82.500, lungo 82.500; sp16a = 172.500; oneri 9.405 + 4.500.
Con regola «ricavi» e ricavi +10% i fidi 2027 valgono 99.000.
Con sweep (cassa minima 0) i fidi scendono della cassa in eccesso, il mutuo no.
"""
from decimal import Decimal as D

import pytest

from backend.app.services import assumptions_service, forecast_preview_service
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP09, SP16A, SP17A, CE15 = "sp09_disponibilita_liquide", "sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo", "ce15_oneri_finanziari"
MUTUO = {"name": "Mutuo", "opening_residual": 330000, "interest_rate": 3.8, "repayments": [82500, 82500, 82500]}


def _genera(user, rows, breve=D("172500"), lungo=D("247500")):
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=user)
            fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
            b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
            delta_lungo = lungo - b.sp17a_debiti_banche_lungo
            b.sp16a_debiti_banche_breve = breve; b.sp16_debiti_breve += breve
            b.sp17a_debiti_banche_lungo = lungo; b.sp17_debiti_lungo += delta_lungo
            b.sp09_disponibilita_liquide += breve + delta_lungo
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


def _rows(**primo):
    base = {"tax_rate": 27.9, "revenue_growth_pct": 0}
    r1 = {"forecast_year": 2027, "financing_loans": [MUTUO], "bank_lines_amount": 90000,
          "bank_lines_rule": "costante", "bank_lines_rate": 5, **base}
    r1.update(primo)
    return [r1, {"forecast_year": 2028, **base}, {"forecast_year": 2029, **base}]


def test_fidi_costanti_e_rata_dell_anno_dopo_a_breve():
    res, anni, det, err = _genera("fidi-costanti", _rows())
    assert res["forecast_generated"] is True, res["message"]
    assert (anni[2027][0][SP16A], anni[2027][0][SP17A]) == (D("172500.00"), D("165000.00"))
    assert (anni[2028][0][SP16A], anni[2028][0][SP17A]) == (D("172500.00"), D("82500.00"))
    assert anni[2027][1][CE15] == D("17040.00") and anni[2028][1][CE15] == D("13905.00")
    fidi = det[2027]["debito_bancario"]["fidi"]
    assert {k: (v if k == "regola" else D(str(v))) for k, v in fidi.items()} == {
        "apertura": D("90000.00"), "variazione_ricavi": D("0.00"), "rimborso_sweep": D("0.00"),
        "tiraggio": D("0.00"), "affidamento": D("90000.00"), "oltre_affidamento": D("0.00"),
        "residuo": D("90000.00"), "regola": "costante"}
    assert det[2027]["oneri_fidi"] == 4500.0 and det[2027]["regime_debito_bancario"] == "esplicito"
    assert D(str(det[2027]["debito_bancario"]["contratti"][0]["breve"])) == D("82500.00")


def test_fidi_seguono_i_ricavi():
    res, anni, det, _ = _genera("fidi-ricavi", _rows(bank_lines_rule="ricavi", revenue_growth_pct=10))
    assert res["forecast_generated"] is True, res["message"]
    assert D(str(det[2027]["debito_bancario"]["fidi"]["residuo"])) == D("99000.00")
    assert D(str(det[2027]["debito_bancario"]["fidi"]["variazione_ricavi"])) == D("9000.00")


def test_lo_sweep_riduce_solo_i_fidi():
    senza = _genera("sweep-no", _rows())
    con = _genera("sweep-si", _rows(cash_sweep_enabled=True, cash_sweep_min_cash=0))
    assert con[0]["forecast_generated"] is True, con[0]["message"]
    fidi = con[2][2027]["debito_bancario"]["fidi"]
    assert D("0") < D(str(fidi["rimborso_sweep"])) <= D("90000.00")
    # il mutuo e' identico con e senza sweep: lo sweep non lo tocca
    assert con[2][2027]["debito_bancario"]["contratti"][0] == senza[2][2027]["debito_bancario"]["contratti"][0]
    assert con[1][2027][0][SP16A] == senza[1][2027][0][SP16A] - D(str(fidi["rimborso_sweep"]))
    assert con[1][2027][0][SP09] == senza[1][2027][0][SP09] - D(str(fidi["rimborso_sweep"]))


def test_rifiuti_in_italiano():
    res, *_ = _genera("fidi-troppi", _rows(bank_lines_amount=200000))
    assert res["forecast_generated"] is False and "superano i debiti verso banche a breve" in res["message"]
    res, *_ = _genera("fidi-non-quadra", _rows(bank_lines_amount=80000))
    assert res["forecast_generated"] is False and "devono coincidere con il debito bancario" in res["message"]


def test_senza_fidi_nulla_cambia():
    # `bank_lines_amount` assente: il contratto a durata di sempre, stessi numeri del Task 2.
    rows = [{"forecast_year": 2027, "tax_rate": 27.9, "financing_loans": [{"opening_residual": 330000, "interest_rate": 3.8, "duration_years": 4}]},
            {"forecast_year": 2028, "tax_rate": 27.9}]
    res, anni, det, _ = _genera("fidi-assenti", rows, breve=D("82500"), lungo=D("247500"))
    assert res["forecast_generated"] is True, res["message"]
    assert det[2027]["debito_bancario"]["fidi"] is None and det[2027]["oneri_fidi"] == 0.0
    assert det[2027]["regime_debito_bancario"] == "contratti"
