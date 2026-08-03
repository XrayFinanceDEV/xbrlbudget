"""Regression tests for semantic Route-C classification (budget_615 class).

The rules intentionally use descriptions rather than ERP account numbers.  The
same accounting captions must therefore map identically when another gestionale
uses completely different codes.
"""

import os
from decimal import Decimal

import pytest

from importers.situazione_contabile_parser import (
    Entry,
    _classify_sp_attivo,
    _classify_sp_passivo,
    build_iv_cee,
    extract_situazione_contabile,
)


D = Decimal
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_615 = os.path.join(
    ROOT, "Test", "july_budget", "budget_615_2024 Lavori di meccanica generale.pdf"
)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("ALTRI BENI MATERIALI AMMORTIZZABILI", "gross_sp03"),
        ("RIM. MAT. PRIME, SUSSID. E CONSUMO", "sp05"),
        ("CREDITI V/ALTRI (EE-IMMOB.)", "gross_sp04"),
        ("CREDITI V/ALTRI (OE-IMMOB.)", "gross_sp04"),
    ],
)
def test_asset_semantics_do_not_depend_on_account_codes(description, expected):
    assert _classify_sp_attivo(description) == expected


def test_fine_mandato_amministratori_is_not_depreciation():
    description = "F.DO INDENNITA FINE MANDATO AMMINISTRATORI"
    assert _classify_sp_passivo(description) == "sp14"


def _semantic_fixture(code_seed: int):
    rows = [
        ("ALTRI BENI MATERIALI AMMORTIZZABILI", D("2000"), "attivo"),
        ("CREDITI V/ALTRI (EE-IMMOB.)", D("300"), "attivo"),
        ("CREDITI V/ALTRI (OE-IMMOB.)", D("700"), "attivo"),
        ("RIM. MAT. PRIME, SUSSID. E CONSUMO", D("1000"), "attivo"),
        ("F.DO AMM. ALTRI BENI MATERIALI", D("500"), "passivo"),
        ("F.DO INDENNITA FINE MANDATO AMMINISTRATORI", D("20000"), "passivo"),
    ]
    return [
        Entry(
            code=f"{code_seed + index:08d}",
            description=description,
            amount=amount,
            level=1,
            section=section,
        )
        for index, (description, amount, section) in enumerate(rows)
    ]


def test_semantic_mapping_is_stable_across_different_erp_codes():
    first_bs, _ = build_iv_cee(_semantic_fixture(11000000))
    second_bs, _ = build_iv_cee(_semantic_fixture(87000000))

    fields = (
        "sp03",
        "sp03d_altri_beni",
        "sp04",
        "sp04b_crediti_immob_breve",
        "sp04c_crediti_immob_lungo",
        "sp05",
        "sp05a_materie_prime",
        "sp14",
        "sp14a_fondi_trattamento_quiescenza",
        "_netted_contra",
    )
    assert {field: first_bs.get(field, D("0")) for field in fields} == {
        field: second_bs.get(field, D("0")) for field in fields
    }
    assert first_bs["sp03"] == D("1500")
    assert first_bs["sp03d_altri_beni"] == D("1500")
    assert first_bs["sp04"] == D("1000")
    assert first_bs["sp04b_crediti_immob_breve"] == D("300")
    assert first_bs["sp04c_crediti_immob_lungo"] == D("700")
    assert first_bs["sp05"] == first_bs["sp05a_materie_prime"] == D("1000")
    assert first_bs["sp14"] == D("20000")
    assert first_bs["sp14a_fondi_trattamento_quiescenza"] == D("20000")
    assert first_bs["_netted_contra"] == D("500")


@pytest.mark.skipif(not os.path.exists(PDF_615), reason="budget_615 corpus PDF not present")
def test_budget_615_assets_funds_and_debts_match_the_source():
    bs, ce = extract_situazione_contabile(PDF_615)

    assert bs["sp02"] == D("6114.33")
    assert bs["sp03"] == D("1586087.17")
    assert bs["sp03a_terreni_fabbricati"] == D("1426458.63")
    assert bs["sp03b_impianti_macchinari"] == D("61474.81")
    assert bs["sp03c_attrezzature"] == D("3321.54")
    assert bs["sp03d_altri_beni"] == D("86912.19")
    assert bs["sp03e_immob_in_corso"] == D("7920.00")
    assert bs["sp04"] == D("31065.62")
    assert bs["sp05"] == D("133204.54")
    assert bs["sp06"] == D("315175.67")
    assert bs["sp14"] == D("20000.00")
    assert bs["sp14a_fondi_trattamento_quiescenza"] == D("20000.00")
    # `_netted_contra` = massa contra COMPLESSIVA tolta dall'attivo, di cui il
    # totale dichiarato dal documento e' lordo. Sono i 698.555,96 di fondi
    # ammortamento PIU' i 13.168,43 del "F.do sval. crediti v/clienti": anche
    # quest'ultimo e' stampato fra le passivita' e nettato dai crediti, quindi
    # deve abbassare l'ancora esattamente come i fondi ammortamento — altrimenti
    # riemerge come plug falso di pari importo (era il caso di budget_281).
    assert bs["_netted_contra"] == D("698555.96") + D("13168.43")

    assert bs["sp16"] == D("220222.57")
    assert bs["sp17"] == D("839488.96")
    assert bs["sp16a_debiti_banche_breve"] == D("7602.77")
    assert bs["sp17a_debiti_banche_lungo"] == D("837488.96")
    assert bs["sp16d_debiti_fornitori_breve"] == D("131658.89")
    assert bs["sp16e_debiti_tributari_breve"] == D("25625.69")
    assert bs["sp16f_debiti_previdenza_breve"] == D("17397.52")
    assert bs["sp16g_altri_debiti_breve"] == D("37937.70")
    assert bs["sp17g_altri_debiti_lungo"] == D("2000.00")
    assert bs["sp18"] == D("53536.60")

    assert bs["sp13"] == D("133705.26")
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("2116501.91")
    assert ce["ce09a_ammort_immateriali"] == D("2036.79")
    assert ce["ce09b_ammort_materiali"] == D("71225.44")


@pytest.mark.skipif(not os.path.exists(PDF_615), reason="budget_615 corpus PDF not present")
def test_budget_615_full_import_is_verified_and_forecastable(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base
    from database.models import BalanceSheet, FinancialYear
    from importers import pdf_importer

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", session_factory)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=PDF_615,
        fiscal_year=2024,
        company_name="Budget 615 regression",
        create_company=True,
        sector=1,
        user_id="test-budget-615",
        period_months=12,
    )

    assert result["validation_status"] == "verified"
    assert result["forecastable"] is True
    assert result["validation_report"]["hierarchy_consistent"] is True
    assert result["validation_report"]["semantic_valid"] is True
    assert result["warnings"] == []

    with session_factory() as db:
        year = db.query(FinancialYear).filter_by(company_id=result["company_id"]).one()
        balance = db.query(BalanceSheet).filter_by(financial_year_id=year.id).one()
        assert year.period_months is None  # 12M is a full-year record
        assert balance.sp03_immob_materiali == D("1586087.17")
        assert balance.sp14_fondi_rischi == D("20000.00")
        assert balance.total_assets == balance.total_liabilities == D("2116501.91")

    engine.dispose()
