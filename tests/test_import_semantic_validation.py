"""Regression tests for non-mutating accounting validation and lossless mapping."""

from copy import deepcopy
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from importers.iv_cee_hierarchy import (
    check_quadratura,
    enforce_ce_sp_identity,
    reconcile_ivcee_balance,
)
from importers.pdf_importer import _create_balance_sheet, _create_income_statement


D = Decimal


def _balanced_bs(result=D("0")):
    return {
        "sp09_disponibilita_liquide": D("100"),
        "sp11_capitale": D("100") - result,
        "sp13_utile_perdita": result,
    }


def test_ce_sp_check_is_diagnostic_and_never_changes_statements():
    bs = _balanced_bs(D("10"))
    ce = {"ce01_ricavi_vendite": D("20")}
    before_bs, before_ce = deepcopy(bs), deepcopy(ce)

    diagnosed = enforce_ce_sp_identity(bs, ce, "test")

    assert bs == before_bs
    assert ce == before_ce
    assert diagnosed["ce01_ricavi_vendite"] == D("20")
    assert diagnosed["_ce_sp_difference"] == D("10")
    assert "ce04_altri_ricavi" not in diagnosed
    assert "ce12_oneri_diversi" not in diagnosed


def test_balance_reconcile_does_not_plug_cash_or_debt():
    bs = {
        "sp09_disponibilita_liquide": D("100"),
        "sp11_capitale": D("90"),
        "sp16_debiti_breve": D("0"),
    }
    before = deepcopy(bs)

    diagnosed = reconcile_ivcee_balance(bs, {"attivo": D("100")}, "test")

    assert bs == before
    assert diagnosed["sp09_disponibilita_liquide"] == D("100")
    assert diagnosed["sp16_debiti_breve"] == D("0")
    assert diagnosed["_unexplained_balance_difference"] == D("10")


def test_quadra_requires_ce_sp_identity():
    q = check_quadratura(_balanced_bs(D("10")), {"ce01_ricavi_vendite": D("20")})
    assert not q.quadra
    assert not q.utile_match
    assert not q.semantic_valid


def test_hierarchy_is_a_separate_downstream_gate():
    bs = {
        "sp06_crediti_breve": D("100"),
        "sp11_capitale": D("100"),
        "sp13_utile_perdita": D("0"),
    }
    q = check_quadratura(bs, {})
    assert q.quadra  # arithmetic identity is true
    assert not q.hierarchy_consistent
    assert q.hierarchy_differences["sp06_crediti_breve"] == D("100")
    assert not q.semantic_valid


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)

    def flush(self):
        return None


def test_pdf_mapping_persists_every_supported_detail_family():
    db = _FakeSession()
    bs_data = {
        "sp01a_parte_richiamata": D("1"),
        "sp02a_costi_impianto": D("2"),
        "sp03c_attrezzature": D("3"),
        "sp05e_acconti": D("5"),
        "sp14d_altri_fondi": D("14"),
    }
    ce_data = {
        "ce03a_incrementi_immobilizzazioni": D("30"),
        "ce17a_rivalutazioni": D("17"),
        "ce17b_svalutazioni": D("7"),
    }

    bs = _create_balance_sheet(db, 1, bs_data)
    ce = _create_income_statement(db, 1, ce_data)

    for field, expected in bs_data.items():
        assert getattr(bs, field) == expected
    for field, expected in ce_data.items():
        assert getattr(ce, field) == expected


def test_pdf_mapping_round_trip_through_database_is_lossless():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        company = Company(name="Round trip", sector=1)
        db.add(company)
        db.flush()
        year = FinancialYear(company_id=company.id, year=2025)
        db.add(year)
        db.flush()
        bs_expected = {
            "sp01a_parte_richiamata": D("1.11"),
            "sp02g_altre_immob_imm": D("2.22"),
            "sp03e_immob_in_corso": D("3.33"),
            "sp14c_strumenti_derivati_passivi": D("4.44"),
        }
        ce_expected = {
            "ce03a_incrementi_immobilizzazioni": D("5.55"),
            "ce11b_altri_accantonamenti": D("6.66"),
            "ce17a_rivalutazioni": D("7.77"),
            "ce17b_svalutazioni": D("8.88"),
        }
        _create_balance_sheet(db, year.id, bs_expected)
        _create_income_statement(db, year.id, ce_expected)
        db.commit()
        db.expire_all()

        stored_bs = db.query(BalanceSheet).filter_by(financial_year_id=year.id).one()
        stored_ce = db.query(IncomeStatement).filter_by(financial_year_id=year.id).one()
        assert {key: getattr(stored_bs, key) for key in bs_expected} == bs_expected
        assert {key: getattr(stored_ce, key) for key in ce_expected} == ce_expected
    finally:
        db.close()
        engine.dispose()
