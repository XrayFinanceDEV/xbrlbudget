"""Regression tests for period-safe and non-inventive intra-year forecasts."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.schemas.budget import BudgetScenarioCreate
from backend.app.schemas.financial_year import FinancialYearCreate
from calculations.intra_year_engine import CE_FIELDS, IntraYearEngine
from database.db import Base
from database.models import BalanceSheet, Company, FinancialYear, IncomeStatement
from database.queries import get_fy_full, get_fy_partial


D = Decimal


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _company(db):
    company = Company(name="Infra Test", tax_id="INFRA-TEST", sector=1)
    db.add(company)
    db.flush()
    return company


def _financial_year(db, company_id, year, period_months, *, profit=D("0")):
    fy = FinancialYear(
        company_id=company_id,
        year=year,
        period_months=period_months,
    )
    db.add(fy)
    db.flush()
    db.add(BalanceSheet(
        financial_year_id=fy.id,
        sp09_disponibilita_liquide=D("100"),
        sp11_capitale=D("100") - profit,
        sp13_utile_perdita=profit,
    ))
    db.add(IncomeStatement(
        financial_year_id=fy.id,
        ce01_ricavi_vendite=profit,
    ))
    db.flush()
    return fy


def _zero_projection(**changes):
    projection = {
        field: D("0")
        for field, _label in CE_FIELDS
    }
    projection.update(changes)
    return projection


def _assumption(**changes):
    values = {
        "investments": D("0"),
        "intangible_investments": D("0"),
        "tangible_investments": D("0"),
        "financing_amount": D("0"),
        "existing_debt_repayment_years": None,
        "altri_finanz_repayment_years": None,
        "ce14_override": None,
        "ce15_override": None,
        "ce17_override": None,
        "ce17a_override": None,
        "ce17b_override": None,
        "tax_rate": D("0"),
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_partial_lookup_requires_exact_months_and_never_returns_full_year(db_session):
    company = _company(db_session)
    fy6 = _financial_year(db_session, company.id, 2025, 6)
    fy9 = _financial_year(db_session, company.id, 2025, 9)
    _financial_year(db_session, company.id, 2025, None)

    assert get_fy_partial(db_session, company.id, 2025, 6).id == fy6.id
    assert get_fy_partial(db_session, company.id, 2025, 9).id == fy9.id
    with pytest.raises(ValueError, match="between 1 and 11"):
        get_fy_partial(db_session, company.id, 2025, 12)


def test_engine_never_falls_back_from_missing_partial_to_full_year(db_session):
    company = _company(db_session)
    _financial_year(db_session, company.id, 2025, None)
    scenario = SimpleNamespace(
        company_id=company.id,
        base_year=2024,
        period_months=6,
    )

    with pytest.raises(ValueError, match=r"2025 \(6 mesi\)"):
        IntraYearEngine(db_session)._load_financial_years(scenario)


def test_strict_full_year_lookup_never_returns_a_partial_record(db_session):
    company = _company(db_session)
    _financial_year(db_session, company.id, 2024, 9)

    assert get_fy_full(db_session, company.id, 2024) is None


def test_infrannuale_schema_requires_a_period():
    with pytest.raises(ValidationError, match="between 1 and 12"):
        BudgetScenarioCreate(
            company_id=1,
            name="Invalid partial",
            base_year=2024,
            scenario_type="infrannuale",
            period_months=None,
        )


@pytest.mark.parametrize("period_months", [1, 6, 11, 12])
def test_infrannuale_schema_accepts_one_to_twelve_months(period_months):
    # 12 months is a full year (identity annualization) and is a valid,
    # supported infrannuale period alongside genuine partials 1-11.
    payload = BudgetScenarioCreate(
        company_id=1,
        name="Valid period",
        base_year=2024,
        scenario_type="infrannuale",
        period_months=period_months,
    )
    assert payload.period_months == period_months


def test_twelve_month_scenario_loads_the_full_year_record(db_session):
    company = _company(db_session)
    # A 12-month import is normalized to a full-year record (period_months NULL).
    full = _financial_year(db_session, company.id, 2025, None)
    scenario = SimpleNamespace(
        company_id=company.id,
        base_year=2024,
        period_months=12,
    )

    engine = IntraYearEngine(db_session)
    partial_fy, ref_fy = engine._load_financial_years(scenario)

    assert partial_fy.id == full.id
    # Full year annualizes with factor 12/12 = 1.
    assert engine._period_months_from_record(partial_fy) == 12


def test_fixed_assets_roll_forward_uses_their_own_depreciation_class():
    engine = IntraYearEngine(None)
    partial_bs = SimpleNamespace(
        sp02_immob_immateriali=D("3000"),
        sp03_immob_materiali=D("5000"),
        sp04_immob_finanziarie=D("2000"),
        sp06_crediti_breve=D("1000"),
    )
    partial_inc = SimpleNamespace(
        ce09a_ammort_immateriali=D("0"),
        ce09b_ammort_materiali=D("300"),
        ce09d_svalutazione_crediti=D("30"),
    )
    projected_inc = _zero_projection(
        ce09_ammortamenti=D("450"),
        ce09a_ammort_immateriali=D("0"),
        ce09b_ammort_materiali=D("400"),
        ce09d_svalutazione_crediti=D("50"),
    )

    result = engine._project_balance_sheet_annualized(
        partial_bs, partial_inc, projected_inc, _assumption(), 9
    )

    assert result["sp02_immob_immateriali"] == D("3000")
    assert result["sp03_immob_materiali"] == D("4900")
    assert result["sp04_immob_finanziarie"] == D("2000")
    assert result["sp06_crediti_breve"] == D("980")


def test_aggregate_investments_are_not_split_fifty_fifty():
    engine = IntraYearEngine(None)

    with pytest.raises(ValueError, match="cannot be allocated automatically"):
        engine._project_balance_sheet_annualized(
            SimpleNamespace(),
            SimpleNamespace(),
            _zero_projection(),
            _assumption(investments=D("1000")),
            9,
        )


def test_projected_income_uses_canonical_ce_formula_and_d_section_details():
    engine = IntraYearEngine(None)
    partial_inc = SimpleNamespace(
        ce01_ricavi_vendite=D("120"),
        ce03a_incrementi_immobilizzazioni=D("12"),
        ce11b_altri_accantonamenti=D("6"),
        ce17a_rivalutazioni=D("3"),
        ce17b_svalutazioni=D("1"),
    )

    result = engine._project_income_statement_annualized(
        partial_inc, _assumption(), 6
    )

    assert result["ce17_rettifiche_attivita_fin"] == D("4")
    assert result["ce17a_rivalutazioni"] == D("6")
    assert result["ce17b_svalutazioni"] == D("2")
    assert engine._net_profit_from_projection(result) == D("256")


def test_uncovered_cash_requirement_is_diagnostic_not_automatic_debt():
    engine = IntraYearEngine(None)
    partial_bs = SimpleNamespace(
        sp02_immob_immateriali=D("1000"),
        sp16_debiti_breve=D("0"),
    )
    projected_inc = _zero_projection()

    result = engine._project_balance_sheet_annualized(
        partial_bs,
        SimpleNamespace(),
        projected_inc,
        _assumption(),
        9,
    )

    assert result["sp09_disponibilita_liquide"] == D("0")
    assert result["sp16_debiti_breve"] == D("0")
    diagnostic = next(
        item for item in engine._diagnostics
        if item["code"] == "unfunded_financing_requirement"
    )
    assert D(diagnostic["amount"]) == D("1000")


def test_missing_debt_breakdown_is_not_invented_as_forty_sixty_split():
    engine = IntraYearEngine(None)

    breakdown = engine._distribute_sp16(SimpleNamespace(), D("1000"))

    assert breakdown == (D("0"),) * 7
    assert engine._diagnostics[0]["code"] == "missing_short_debt_breakdown"


def test_forecast_gate_rejects_ce_sp_mismatch(db_session):
    company = _company(db_session)
    fy = _financial_year(db_session, company.id, 2025, 9, profit=D("10"))
    fy.balance_sheet.sp13_utile_perdita = D("0")
    db_session.flush()

    with pytest.raises(ValueError, match="CE/SP profit mismatch"):
        IntraYearEngine(db_session)._validate_forecast_source(fy, "Partial source")


def test_forecast_gate_rejects_persisted_source_plug(db_session):
    company = _company(db_session)
    fy = _financial_year(db_session, company.id, 2025, 9)
    fy.original_bs_snapshot = '{"_plug_residual": "5"}'
    db_session.flush()

    with pytest.raises(ValueError, match="source plug 5"):
        IntraYearEngine(db_session)._validate_forecast_source(fy, "Partial source")


def test_forecast_gate_rejects_debt_aggregate_without_breakdown(db_session):
    # sp16/sp17 are the exception to the rule below: projection_common.base_bank_debt
    # attributes the whole aggregate/detail gap to BANKS, so an absent breakdown is
    # silently turned into phantom bank debt downstream.  It must keep blocking.
    company = _company(db_session)
    fy = _financial_year(db_session, company.id, 2025, 9)
    fy.balance_sheet.sp11_capitale = D("90")
    fy.balance_sheet.sp16_debiti_breve = D("10")
    db_session.flush()

    with pytest.raises(ValueError, match="sp16_debiti_breve"):
        IntraYearEngine(db_session)._validate_forecast_source(fy, "Partial source")


def test_forecast_gate_allows_an_aggregate_with_no_breakdown_at_all(db_session):
    """A bilancio abbreviato states only the aggregate.  That is not a contradiction:
    the engine's distributors return zeros and carry the aggregate unchanged, so
    nothing is invented and the projection must not be blocked."""
    company = _company(db_session)
    fy = _financial_year(db_session, company.id, 2025, 9)
    fy.balance_sheet.sp05_rimanenze = D("50")      # aggregate only, every sp05x = 0
    fy.balance_sheet.sp04_immob_finanziarie = D("20")
    fy.balance_sheet.sp15_tfr = D("70")            # keep the sheet balanced
    db_session.flush()

    IntraYearEngine(db_session)._validate_forecast_source(fy, "Partial source")


def test_forecast_gate_still_rejects_a_contradictory_breakdown(db_session):
    """Detail that IS declared but does not sum to its aggregate is a positive
    contradiction — one of the two figures is wrong, and the engine would scale it."""
    company = _company(db_session)
    fy = _financial_year(db_session, company.id, 2025, 9)
    fy.balance_sheet.sp05_rimanenze = D("50")
    fy.balance_sheet.sp05a_materie_prime = D("20")  # 20 != 50
    fy.balance_sheet.sp15_tfr = D("50")
    db_session.flush()

    with pytest.raises(ValueError, match="sp05_rimanenze"):
        IntraYearEngine(db_session)._validate_forecast_source(fy, "Partial source")


def test_financial_year_schema_preserves_the_exact_partial_period():
    payload = FinancialYearCreate(company_id=1, year=2026, period_months=9)
    assert payload.period_months == 9


def test_financial_year_schema_rejects_invalid_period_months():
    with pytest.raises(ValidationError):
        FinancialYearCreate(company_id=1, year=2026, period_months=0)
    with pytest.raises(ValidationError):
        FinancialYearCreate(company_id=1, year=2026, period_months=13)
