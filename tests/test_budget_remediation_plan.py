from decimal import Decimal
from types import SimpleNamespace

from backend.app.schemas.budget import BudgetAssumptionsCreate
from calculations.forecast_engine import ForecastEngine
from calculations.intra_year_engine import apply_ce_overrides
from calculations.intra_year_engine import IntraYearEngine
from calculations.projection_common import (
    base_bank_debt,
    financial_repayment_instalment,
    new_financing_schedule,
    tax_closing_position,
    deferred_tax_position,
)


D = Decimal


def test_infrannuale_applies_every_absolute_override_and_keeps_tax_exact():
    result = {
        "ce01_ricavi_vendite": D("100"),
        "ce17_rettifiche_attivita_fin": D("0"),
        "ce17a_rivalutazioni": D("0"),
        "ce17b_svalutazioni": D("0"),
        "ce20_imposte": D("10"),
    }
    assumption = SimpleNamespace(
        ce01_override=D("125"),
        ce17_override=None,
        ce17a_override=D("7"),
        ce17b_override=D("2"),
        ce20_override=D("19"),
    )

    actual = apply_ce_overrides(result, assumption)

    assert actual["ce01_ricavi_vendite"] == D("125")
    assert actual["ce17_rettifiche_attivita_fin"] == D("5")
    assert actual["ce20_imposte"] == D("19")


def test_tax_settlement_reclassifies_overpayment_without_negative_balances():
    assert tax_closing_position(D("100"), D("0"), D("30"), D("0")) == (
        D("70"), D("0")
    )
    assert tax_closing_position(D("0"), D("50"), D("30"), D("100")) == (
        D("20"), D("0")
    )
    assert tax_closing_position(D("0"), D("50"), D("30"), D("10")) == (
        D("0"), D("70")
    )


def test_existing_repayment_uses_total_bank_debt_and_excludes_bonds():
    values = {
        "sp16_debiti_breve": D("110"),
        "sp16a_debiti_banche_breve": D("100"),
        "sp16d_debiti_fornitori_breve": D("10"),
        "sp17_debiti_lungo": D("800"),
        "sp17a_debiti_banche_lungo": D("300"),
        "sp17c_debiti_obbligazioni_lungo": D("500"),
    }
    getter = lambda field: values.get(field, D("0"))

    assert base_bank_debt(getter) == D("400")
    assert financial_repayment_instalment(getter, 5) == D("80")


def test_infrannuale_repayment_reduces_short_bank_debt_before_long_bank_debt():
    base = SimpleNamespace(
        sp16_debiti_breve=D("100"),
        sp16a_debiti_banche_breve=D("100"),
        sp17_debiti_lungo=D("300"),
        sp17a_debiti_banche_lungo=D("300"),
        sp17b_debiti_altri_finanz_lungo=D("0"),
    )
    assumption = SimpleNamespace(
        existing_debt_repayment_years=D("4"),
        altri_finanz_repayment_years=None,
    )

    short_bank, long_bank, other_lender = IntraYearEngine(None)._apply_debt_repayment(
        base, D("100"), D("300"), D("0"), assumption
    )

    assert short_bank == D("0")
    assert long_bank == D("300")
    assert other_lender == D("0")


def test_abbreviated_debt_gap_is_assigned_to_banks():
    values = {"sp16_debiti_breve": D("200"), "sp17_debiti_lungo": D("300")}
    getter = lambda field: values.get(field, D("0"))

    assert base_bank_debt(getter) == D("500")


def test_absolute_sp_detail_overrides_rebuild_parent_and_cash():
    result = {
        "sp01_crediti_soci": D("0"),
        "sp02_immob_immateriali": D("0"),
        "sp03_immob_materiali": D("0"),
        "sp04_immob_finanziarie": D("0"),
        "sp05_rimanenze": D("0"),
        "sp06_crediti_breve": D("100"),
        "sp06a_crediti_clienti_breve": D("100"),
        "sp06b_crediti_controllate_breve": D("0"),
        "sp06c_crediti_collegate_breve": D("0"),
        "sp06d_crediti_controllanti_breve": D("0"),
        "sp06e_crediti_tributari_breve": D("0"),
        "sp06f_imposte_anticipate_breve": D("0"),
        "sp06g_crediti_altri_breve": D("0"),
        "sp07_crediti_lungo": D("0"),
        "sp08_attivita_finanziarie": D("0"),
        "sp09_disponibilita_liquide": D("200"),
        "sp10_ratei_risconti_attivi": D("0"),
        "sp11_capitale": D("300"),
        "sp12_riserve": D("0"),
        "sp13_utile_perdita": D("0"),
        "sp14_fondi_rischi": D("0"),
        "sp15_tfr": D("0"),
        "sp16_debiti_breve": D("0"),
        "sp17_debiti_lungo": D("0"),
        "sp18_ratei_risconti_passivi": D("0"),
    }
    assumption = SimpleNamespace(
        sp_overrides={
            "sp06e_crediti_tributari_breve": 50,
            "sp06g_crediti_altri_breve": 20,
        }
    )

    actual = ForecastEngine._apply_sp_overrides(result, assumption)

    assert actual["sp06_crediti_breve"] == D("170")
    assert actual["sp09_disponibilita_liquide"] == D("130")


def test_multiple_financing_lines_keep_independent_schedules():
    loans = [
        {"year": 2027, "amount": D("100"), "duration": D("2"), "rate": D("0.10")},
        {"year": 2027, "amount": D("60"), "duration": D("3"), "rate": D("0.05")},
    ]

    raised, repayment, interest = new_financing_schedule(loans, 2027)

    assert raised == D("160")
    assert repayment == D("70")
    assert interest == D("13")


def test_assumptions_schema_accepts_additional_financing_lines():
    assumption = BudgetAssumptionsCreate(
        scenario_id=1,
        forecast_year=2027,
        financing_loans=[
            {"name": "Mutuo capex", "amount": 100_000, "duration_years": 5, "interest_rate": 4.2}
        ],
    )

    assert assumption.financing_loans is not None
    assert assumption.financing_loans[0].amount == D("100000")


def test_deferred_tax_rollforward_splits_assets_liabilities_and_ce_effect():
    actual = deferred_tax_position([
        {
            "kind": "deductible", "maturity": "short",
            "opening_amount": 100, "additions": 50, "reversals": 20,
            "tax_rate": 25,
        },
        {
            "kind": "taxable", "maturity": "long",
            "opening_amount": 200, "additions": 100, "reversals": 0,
            "tax_rate": 25,
        },
    ], D("24"))

    assert actual["short_asset"] == D("32.5")
    assert actual["long_asset"] == D("0")
    assert actual["liability"] == D("75")
    assert actual["deferred_expense"] == D("17.5")


def test_advanced_financing_supports_grace_and_balloon():
    loan = [{
        "year": 2027,
        "amount": 100,
        "duration": 4,
        "rate": D("0.10"),
        "grace_years": 1,
        "balloon_pct": 20,
    }]

    assert new_financing_schedule(loan, 2027) == (D("100"), D("0"), D("10"))
    _, second_repayment, second_interest = new_financing_schedule(loan, 2028)
    _, final_repayment, final_interest = new_financing_schedule(loan, 2030)
    assert second_repayment == D("80") / D("3")
    assert second_interest == D("10")
    assert abs(final_repayment - D("140") / D("3")) < D("0.0000001")
    assert abs(final_interest - D("14") / D("3")) < D("0.0000001")


def test_tax_components_keep_current_tax_out_of_deferred_settlement():
    projected = {"ce01_ricavi_vendite": D("100"), "ce20_imposte": D("0")}
    base = SimpleNamespace(ce20_imposte=D("0"))
    assumption = SimpleNamespace(
        tax_rate=D("25"),
        ce20_override=None,
        tax_temporary_differences=[{
            "kind": "deductible", "maturity": "short",
            "opening_amount": 0, "additions": 40, "reversals": 0,
            "tax_rate": 25,
        }],
    )

    current, deferred, total = ForecastEngine._tax_components(
        base, projected, assumption
    )

    assert current == D("25")
    assert deferred["deferred_expense"] == D("-10")
    assert total == D("15")
