"""Le otto colonne e le due chiavi JSON del giro di rilievi del 14/09 (spec 2026-09-15 §6).

Tutto additivo: una riga costruita da `build_assumption_row` con un dict di prima ha i default
di colonna (NULL, 0, False), e lo schema del bulk accetta e valida i campi nuovi.
"""
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.schemas.budget import (
    BudgetAssumptionsBulkRow, OtherLenderInput, PregressoPlanInput,
)
from backend.app.services.assumptions_service import build_assumption_row
from database.models import BudgetAssumptions

COLONNE = {
    "inflation_pct": None, "fixed_materials_growth_auto": False, "fixed_services_growth_auto": False,
    "bank_lines_amount": None, "bank_lines_rule": None, "bank_lines_rate": None,
    "other_lenders": None, "tfr_payments": Decimal("0"),
}


def test_le_otto_colonne_esistono_con_i_default_di_prima():
    nomi = {c.name for c in BudgetAssumptions.__table__.columns}
    assert set(COLONNE) <= nomi
    riga = build_assumption_row(1, {"forecast_year": 2027, "revenue_growth_pct": 3})
    for colonna, atteso in COLONNE.items():
        assert getattr(riga, colonna) == atteso, colonna


def test_build_assumption_row_porta_i_campi_nuovi():
    riga = build_assumption_row(1, {
        "forecast_year": 2027, "inflation_pct": 2.5, "fixed_materials_growth_auto": True,
        "bank_lines_amount": 90000, "bank_lines_rule": "ricavi", "bank_lines_rate": 5,
        "other_lenders": [{"name": "Soci", "opening_residual": 150000, "interest_rate": 0, "repayments": [0, 50000]}],
        "tfr_payments": 50000,
    })
    assert riga.inflation_pct == Decimal("2.5")
    assert riga.fixed_materials_growth_auto is True
    assert riga.bank_lines_amount == Decimal("90000")
    assert riga.bank_lines_rule == "costante"
    assert riga.other_lenders[0]["repayments"] == [0, 50000]
    assert riga.tfr_payments == Decimal("50000")


def test_other_lender_e_non_incassato():
    o = OtherLenderInput(name="Finanziamento soci", opening_residual=150000, repayments=[])
    assert o.interest_rate == Decimal("0")
    with pytest.raises(ValidationError, match="supera il residuo"):
        OtherLenderInput(opening_residual=10, repayments=[11])
    p = PregressoPlanInput(opening=30000, amounts=[0, 0], non_incassato=True)
    assert p.non_incassato is True
    riga = BudgetAssumptionsBulkRow(forecast_year=2027, bank_lines_rule="costante", tfr_payments=0)
    assert riga.bank_lines_rule == "costante"
    with pytest.raises(ValidationError):
        BudgetAssumptionsBulkRow(forecast_year=2027, bank_lines_rule="altro")


def test_il_read_model_del_report_riporta_altri_finanziatori_e_non_incassato():
    """Le due chiavi JSON passano dal catalogo; la vecchia regola fidi no."""
    from backend.app.services import final_report_assumptions as fra

    row = BudgetAssumptions(
        scenario_id=1, forecast_year=2027,
        explicitly_supplied_fields=["other_lenders", "pregresso"],
        bank_lines_rule="ricavi",
        other_lenders=[{"name": "Finanziamento soci", "opening_residual": "150000.00",
                        "interest_rate": "0", "repayments": ["0", "50000.00"]}],
        pregresso={"crediti_commerciali": {"opening": "30000", "amounts": ["0", "0"], "non_incassato": True}},
    )
    read_model = fra.build_assumption_sections([row])
    values = {a.field: a for section in read_model.sections for a in section.assumptions}
    lenders = values["other_lenders"].other_lenders
    assert [l.name for l in lenders] == ["Finanziamento soci"]
    assert lenders[0].opening_residual == Decimal("150000.00")
    assert lenders[0].repayments == [Decimal("0"), Decimal("50000.00")]
    assert values["other_lenders"].provenance == "user"
    assert values["pregresso"].pregresso.crediti_commerciali.non_incassato is True
    assert "bank_lines_rule" not in values
    assert read_model.diagnostics == []


def test_il_contratto_ammette_una_stringa_solo_per_bank_lines_rule():
    from backend.app.schemas.final_report import AssumptionValue

    ok = AssumptionValue(field="bank_lines_rule", label="Fidi: regola nel piano",
                         values=["costante"], provenance="user", active=True)
    assert ok.values == ["costante"]
    with pytest.raises(ValidationError, match="decimal strings"):
        AssumptionValue(field="revenue_growth_pct", label="Crescita ricavi",
                        values=["costante"], provenance="user", active=True)
