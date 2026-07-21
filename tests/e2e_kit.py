"""Shared helpers for the 'generi diversi' end-to-end suites.

Everything runs on an in-memory SQLite DB and without ANTHROPIC_API_KEY.
"""
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.db import Base
from database.models import BalanceSheet, Company, FinancialYear, IncomeStatement

BASE_BS = {
    "sp02_immob_immateriali": Decimal("40000"),
    "sp03_immob_materiali": Decimal("160000"),
    "sp05_rimanenze": Decimal("50000"),
    "sp06_crediti_breve": Decimal("120000"),
    "sp09_disponibilita_liquide": Decimal("30000"),
    "sp11_capitale": Decimal("100000"),
    "sp12_riserve": Decimal("60000"),
    "sp13_utile_perdita": Decimal("20000"),
    "sp15_tfr": Decimal("30000"),
    "sp16_debiti_breve": Decimal("140000"),
    "sp17_debiti_lungo": Decimal("50000"),
    # IV-CEE detail breakdowns for every aggregate the forecast engine's
    # forecastability gate treats as blocking when detail sub-fields don't
    # reconcile to the aggregate (calculations/intra_year_engine.py
    # _validate_forecast_source -> breakdowns_used_by_engine, exercised by
    # calculations/forecast_engine.py generate_forecast for the base year;
    # see also tests/test_intra_year_semantics.py::
    # test_forecast_gate_rejects_debt_aggregate_without_breakdown). A real
    # import always carries this typed breakdown; a hand-seeded base year
    # must too, or every forecast generation raises "not forecastable:
    # aggregate/detail mismatch". One bucket per aggregate is enough to
    # reconcile — the specific bucket is chosen to match what the engine
    # actually drives off of it (sp06a for DSO, sp16d for DPO, sp17a for the
    # bank-debt repayment schedule).
    "sp05a_materie_prime": Decimal("50000"),
    "sp06a_crediti_clienti_breve": Decimal("120000"),
    "sp12e_altre_riserve": Decimal("60000"),
    "sp16d_debiti_fornitori_breve": Decimal("140000"),
    "sp17a_debiti_banche_lungo": Decimal("50000"),
}
BASE_CE = {
    "ce01_ricavi_vendite": Decimal("600000"),
    "ce05_materie_prime": Decimal("200000"),
    "ce06_servizi": Decimal("150000"),
    "ce07_godimento_beni": Decimal("10000"),
    "ce08_costi_personale": Decimal("120000"),
    "ce08a_tfr_accrual": Decimal("8000"),
    "ce09_ammortamenti": Decimal("40000"),
    "ce12_oneri_diversi": Decimal("5000"),
    "ce15_oneri_finanziari": Decimal("5000"),
    "ce20_imposte": Decimal("50000"),
    # Detail breakdown for ce09 (same forecastability gate as above).
    "ce09b_ammort_materiali": Decimal("40000"),
}
HOLDING_BS = {
    "sp04_immob_finanziarie": Decimal("350000"),
    "sp09_disponibilita_liquide": Decimal("50000"),
    "sp11_capitale": Decimal("200000"),
    "sp12_riserve": Decimal("130000"),
    "sp13_utile_perdita": Decimal("20000"),
    "sp16_debiti_breve": Decimal("50000"),
    # Same forecastability-gate fix as BASE_BS above (see comment there):
    # calculations/intra_year_engine.py _validate_forecast_source gates on
    # sp04/sp12/sp16 (among others) needing aggregate == Σdetail. The holding
    # fixture carries nonzero sp04/sp12/sp16 aggregates with no detail
    # sub-field, which raises "not forecastable: aggregate/detail mismatch".
    # One bucket per aggregate reconciles it, matching BASE_BS's convention.
    "sp04a_partecipazioni": Decimal("350000"),
    "sp12e_altre_riserve": Decimal("130000"),
    "sp16d_debiti_fornitori_breve": Decimal("50000"),
}
HOLDING_CE = {
    "ce01_ricavi_vendite": Decimal("0"),
    "ce06_servizi": Decimal("5000"),
    "ce13_proventi_partecipazioni": Decimal("30000"),
    "ce20_imposte": Decimal("5000"),
}


def memory_sessions():
    """In-memory engine shareable across sessions (StaticPool)."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


def seed_base_year(db, *, user_id, year=2026, scale=Decimal("1"), holding=False):
    """Create a verified, forecastable full-year base directly via ORM."""
    bs_values = HOLDING_BS if holding else BASE_BS
    ce_values = HOLDING_CE if holding else BASE_CE
    company = Company(
        name=f"KIT {user_id} {year}", tax_id=f"KIT{year}", sector=1, user_id=user_id
    )
    db.add(company)
    db.flush()
    fy = FinancialYear(
        company_id=company.id,
        year=year,
        period_months=None,
        validation_status="verified",
        forecastable=True,
    )
    db.add(fy)
    db.flush()
    db.add(
        BalanceSheet(
            financial_year_id=fy.id,
            **{k: (v * scale).quantize(Decimal("0.01")) for k, v in bs_values.items()},
        )
    )
    db.add(
        IncomeStatement(
            financial_year_id=fy.id,
            **{k: (v * scale).quantize(Decimal("0.01")) for k, v in ce_values.items()},
        )
    )
    db.commit()
    return company.id, fy.id


def read_forecast_maps(db, scenario_id):
    """Return [(year, {sp*: Decimal}, {ce*: Decimal})] as actually stored."""
    from database.models import ForecastYear

    out = []
    rows = (
        db.query(ForecastYear)
        .filter(ForecastYear.scenario_id == scenario_id)
        .order_by(ForecastYear.year)
        .all()
    )
    for fy in rows:
        bs = {
            c.name: Decimal(str(getattr(fy.balance_sheet, c.name, None) or 0))
            for c in fy.balance_sheet.__table__.columns
            if c.name.startswith("sp")
        }
        ce = {
            c.name: Decimal(str(getattr(fy.income_statement, c.name, None) or 0))
            for c in fy.income_statement.__table__.columns
            if c.name.startswith("ce")
        }
        bs["_total_assets"] = Decimal(str(fy.balance_sheet.total_assets))
        bs["_total_liabilities"] = Decimal(str(fy.balance_sheet.total_liabilities))
        out.append((fy.year, bs, ce))
    return out
