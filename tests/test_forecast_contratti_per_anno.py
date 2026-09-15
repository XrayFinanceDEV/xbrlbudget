"""Capitale rimborsato anno per anno sui contratti pregressi (spec 2026-09-15 §5.1).

Oracolo a mano: residuo 330.000 al 3,8%, rimborsi [82.500, 82.500, 0] su 3 anni. Residuo di fine
anno 247.500 · 165.000 · 165.000 (oltre la lista non si rimborsa: il debito resta aperto, decisione
7). Interessi sul residuo di apertura: 12.540,00 · 9.405,00 · 6.270,00.
"""
from decimal import Decimal as D

import pytest
from pydantic import ValidationError

from backend.app.schemas.budget import FinancingLoanInput
from backend.app.services import assumptions_service, forecast_preview_service
from calculations.projection_common import contratti_da_riga_finanziamento, new_financing_schedule
from database.models import BalanceSheet, BudgetScenario, FinancialYear
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year

SP16A, SP17A = "sp16a_debiti_banche_breve", "sp17a_debiti_banche_lungo"
CE15 = "ce15_oneri_finanziari"


def test_schema_repayments_solo_sul_pregresso_e_mai_oltre_il_residuo():
    ok = FinancingLoanInput(name="Mutuo", opening_residual=330000, interest_rate=3.8, repayments=[82500, 82500])
    assert ok.duration_years is None and ok.repayments == [D("82500"), D("82500")]
    with pytest.raises(ValidationError, match="supera il residuo"):
        FinancingLoanInput(opening_residual=100, repayments=[60, 60])
    with pytest.raises(ValidationError, match="negativo"):
        FinancingLoanInput(opening_residual=100, repayments=[-1])
    with pytest.raises(ValidationError, match="prestito nuovo"):
        FinancingLoanInput(amount=100, repayments=[50])
    with pytest.raises(ValidationError, match="durata"):
        FinancingLoanInput(amount=100)  # senza repayments la durata resta obbligatoria
    classico = FinancingLoanInput(amount=100, duration_years=4)
    assert classico.repayments is None and classico.duration_years == 4


def test_kernel_rimborsa_la_lista_e_poi_lascia_aperto():
    loan = {"year": 2027, "amount": D("0"), "opening_residual": D("330000"), "rate": D("0.038"),
            "repayments": [D("82500"), D("82500"), D("0")]}
    assert new_financing_schedule([loan], 2027) == (D("0"), D("82500"), D("12540.000"))
    assert new_financing_schedule([loan], 2028) == (D("0"), D("82500"), D("9405.000"))
    assert new_financing_schedule([loan], 2029) == (D("0"), D("0"), D("6270.000"))
    assert new_financing_schedule([loan], 2031) == (D("0"), D("0"), D("6270.000"))


def test_kernel_non_rimborsa_oltre_il_residuo():
    loan = {"year": 2027, "amount": D("0"), "opening_residual": D("100"), "rate": D("0"),
            "repayments": [D("60"), D("60")]}
    assert new_financing_schedule([loan], 2028)[1] == D("40")


def test_contratti_da_riga_porta_repayments_senza_durata():
    riga = {"opening_residual": 330000, "interest_rate": 3.8, "repayments": [82500, 82500]}
    (c,) = contratti_da_riga_finanziamento(riga, 2027)
    assert c["repayments"] == [D("82500"), D("82500")] and c["opening_residual"] == D("330000")
    assert c["year"] == 2027


def _genera(user, rows, breve, lungo):
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
            return res, anni, prev
    finally:
        engine.dispose()


def test_il_previsionale_persiste_i_residui_della_lista():
    contratto = {"name": "Mutuo", "opening_residual": 330000, "interest_rate": 3.8, "repayments": [82500, 82500, 0]}
    rows = [{"forecast_year": 2027, "tax_rate": 27.9, "financing_loans": [contratto]},
            {"forecast_year": 2028, "tax_rate": 27.9}, {"forecast_year": 2029, "tax_rate": 27.9}]
    res, anni, prev = _genera("contratti-anno", rows, breve=D("82500"), lungo=D("247500"))
    assert res["forecast_generated"] is True, res["message"]
    assert [anni[a][0][SP16A] + anni[a][0][SP17A] for a in (2027, 2028, 2029)] == [D("247500.00"), D("165000.00"), D("165000.00")]
    assert [anni[a][1][CE15] for a in (2027, 2028, 2029)] == [D("12540.00"), D("9405.00"), D("6270.00")]
    contratti = prev["forecast_years"][0]["details"]["debito_bancario"]["contratti"]
    # Nei details i blocchi annidati restano Decimal (_floats non e' ricorsivo):
    # si confronta in Decimal, mai in float.
    assert D(str(contratti[0]["rimborso"])) == D("82500.00")
    assert D(str(contratti[0]["interessi"])) == D("12540.00")
    assert contratti[0]["nome"] == "Mutuo"
