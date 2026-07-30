from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.db import Base
from database.models import Company, FinancialYear
from importers.csv_importer import CSVImporter, CSVImportError


ROOT = Path(__file__).resolve().parents[1]
BILAQ = ROOT / "Test" / "june_sample" / "errori" / "budget_370_BILAQ-001.csv"
TEBE = ROOT / "legacy" / "sample_data" / "sample_data.csv"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _company(db, name="CSV Test"):
    company = Company(name=name, tax_id=name.replace(" ", "")[:11], sector=1)
    db.add(company)
    db.flush()
    return company


@pytest.mark.skipif(not BILAQ.exists(),
                    reason="local corpus CSV budget_370 is not available")
def test_bilaq_header_and_windows_encoding_are_detected():
    parser = CSVImporter(db_session=_session())
    _, rows = parser.read_csv_file(str(BILAQ))
    assert parser.csv_metadata["schema"] == "BILAQ"
    assert parser.csv_metadata["encoding"] == "cp1252"
    assert parser.csv_metadata["detected_years"] == [2025]
    assert any(row["description"] == "Disponibilità liquide" for row in rows)
    assert len(rows) < 250  # exact duplicate export rows are discarded


@pytest.mark.skipif(not BILAQ.exists(),
                    reason="local corpus CSV budget_370 is not available")
def test_real_bilaq_is_mapped_by_headers_and_iv_cee_sections():
    db = _session()
    company = _company(db)
    parser = CSVImporter(db_session=db)
    result = parser.import_to_database(str(BILAQ), company.id)

    fy = db.query(FinancialYear).filter_by(company_id=company.id, year=2025).one()
    assert result["csv_schema"] == "BILAQ"
    assert result["years"] == [2025]
    assert fy.balance_sheet.sp03_immob_materiali == Decimal("244364.61")
    assert fy.balance_sheet.sp06_crediti_breve == Decimal("312248.43")
    assert fy.balance_sheet.sp16_debiti_breve == Decimal("247088.46")
    assert fy.balance_sheet.sp17_debiti_lungo == Decimal("175935.90")
    assert fy.balance_sheet.sp13_utile_perdita == Decimal("38607.28")
    assert fy.income_statement.ce01_ricavi_vendite == Decimal("1139883.63")
    assert fy.validation_status == "verified"
    assert fy.forecastable is True


def test_unbalanced_tebe_is_rejected_atomically():
    db = _session()
    company = _company(db, "TEBE Test")
    parser = CSVImporter(db_session=db)
    with pytest.raises(CSVImportError, match="non valido"):
        parser.import_to_database(str(TEBE), company.id)
    assert db.query(FinancialYear).filter_by(company_id=company.id).count() == 0
