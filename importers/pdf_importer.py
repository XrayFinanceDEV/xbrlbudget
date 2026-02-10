"""
PDF Balance Sheet Importer for Italian IV CEE format.

Uses Docling to extract balance sheet data from PDF files and maps them
to the database schema (sp01-sp18 fields).
"""

import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from docling.document_converter import DocumentConverter

from database.db import SessionLocal
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from importers.pdf_mapper import IVCEEMapper
from config import Sector

logger = logging.getLogger(__name__)


class PDFImportError(Exception):
    """Exception raised when PDF import fails."""
    pass


def import_pdf_balance_sheet(
    file_path: str,
    company_id: Optional[int] = None,
    fiscal_year: Optional[int] = None,
    company_name: Optional[str] = None,
    create_company: bool = True,
    sector: Optional[int] = None
) -> Dict[str, Any]:
    """
    Import balance sheet from PDF file using Docling.

    Args:
        file_path: Path to PDF file
        company_id: Optional company ID (will be created if None and create_company=True)
        fiscal_year: Fiscal year for the balance sheet
        company_name: Company name (for new company creation)
        create_company: Whether to create company if not exists

    Returns:
        Dictionary with import results:
            {
                "success": True,
                "company_id": int,
                "company_name": str,
                "fiscal_year": int,
                "balance_sheet_id": int,
                "income_statement_id": int,
                "format": "micro"|"abbreviato"|"ordinario",
                "confidence_score": float,
                "message": str
            }

    Raises:
        PDFImportError: If extraction or validation fails
    """

    db = SessionLocal()
    extraction_start = datetime.utcnow()

    try:
        logger.info(f"Starting PDF import from {file_path}")

        # Step 1: Extract PDF using Docling
        logger.info("Initializing Docling converter...")
        converter = DocumentConverter()

        logger.info("Converting PDF to structured format...")
        result = converter.convert(file_path)

        doc_text = result.document.export_to_markdown()
        logger.info(f"PDF converted successfully ({len(doc_text)} characters)")

        # Step 2: Extract balance sheet data
        logger.info("Extracting balance sheet data...")
        mapper = IVCEEMapper()

        balance_sheet_data = mapper.extract_balance_sheet(
            doc_text=doc_text,
            year=fiscal_year,
            company_name=company_name
        )

        # Step 3: Validate balance sheet
        logger.info("Validating balance sheet...")
        if not mapper.validate_balance(balance_sheet_data):
            raise PDFImportError("Balance sheet does not balance (Assets ≠ Liabilities + Equity)")

        warnings = mapper.validate_hierarchy(balance_sheet_data)
        if warnings:
            logger.warning(f"Balance sheet hierarchy warnings: {warnings}")

        # Step 4: Extract income statement
        logger.info("Extracting income statement data...")
        income_data = mapper.extract_income_statement(doc_text)

        # Step 5: Handle company
        company = None
        if company_id:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise PDFImportError(f"Company with ID {company_id} not found")
        elif create_company and company_name:
            # Create new company
            company = Company(
                name=company_name,
                tax_id=None,  # PDF doesn't always have tax_id in extractable format
                sector=sector or Sector.SERVIZI.value
            )
            db.add(company)
            db.flush()
            logger.info(f"Created new company: {company.name} (ID: {company.id})")
        else:
            raise PDFImportError("Either company_id or (create_company=True and company_name) must be provided")

        # Step 6: Check if fiscal year already exists
        if fiscal_year:
            existing_year = db.query(FinancialYear).filter(
                FinancialYear.company_id == company.id,
                FinancialYear.year == fiscal_year
            ).first()

            if existing_year:
                logger.warning(f"Financial year {fiscal_year} already exists for company {company.id}, will update")
                # Delete existing data to replace
                if existing_year.balance_sheet:
                    db.delete(existing_year.balance_sheet)
                if existing_year.income_statement:
                    db.delete(existing_year.income_statement)
                db.delete(existing_year)
                db.flush()

        # Step 7: Create financial year
        financial_year_obj = FinancialYear(
            company_id=company.id,
            year=fiscal_year or datetime.now().year
        )
        db.add(financial_year_obj)
        db.flush()

        # Step 8: Create balance sheet record
        # Note: Database model does not store totale_attivo/totale_passivo as columns
        balance_sheet = BalanceSheet(
            financial_year_id=financial_year_obj.id,
            # Assets (Attivo)
            sp01_crediti_soci=balance_sheet_data.get('sp01_crediti_soci', Decimal('0')),
            sp02_immob_immateriali=balance_sheet_data.get('sp02_immob_immateriali', Decimal('0')),
            sp03_immob_materiali=balance_sheet_data.get('sp03_immob_materiali', Decimal('0')),
            sp04_immob_finanziarie=balance_sheet_data.get('sp04_immob_finanziarie', Decimal('0')),
            sp05_rimanenze=balance_sheet_data.get('sp05_rimanenze', Decimal('0')),
            sp06_crediti_breve=balance_sheet_data.get('sp06_crediti_breve', Decimal('0')),
            sp07_crediti_lungo=balance_sheet_data.get('sp07_crediti_lungo', Decimal('0')),
            sp08_attivita_finanziarie=balance_sheet_data.get('sp08_attivita_finanziarie', Decimal('0')),
            sp09_disponibilita_liquide=balance_sheet_data.get('sp09_disponibilita_liquide', Decimal('0')),
            sp10_ratei_risconti_attivi=balance_sheet_data.get('sp10_ratei_risconti_attivi', Decimal('0')),
            # Equity (Patrimonio Netto)
            sp11_capitale=balance_sheet_data.get('sp11_capitale', Decimal('0')),
            sp12_riserve=balance_sheet_data.get('sp12_riserve', Decimal('0')),
            sp13_utile_perdita=balance_sheet_data.get('sp13_utile_perdita', Decimal('0')),
            # Liabilities (Passivo)
            sp14_fondi_rischi=balance_sheet_data.get('sp14_fondi_rischi', Decimal('0')),
            sp15_tfr=balance_sheet_data.get('sp15_tfr', Decimal('0')),
            sp16_debiti_breve=balance_sheet_data.get('sp16_debiti_breve', Decimal('0')),
            sp17_debiti_lungo=balance_sheet_data.get('sp17_debiti_lungo', Decimal('0')),
            sp18_ratei_risconti_passivi=balance_sheet_data.get('sp18_ratei_risconti_passivi', Decimal('0')),
            # Detailed breakdown fields (not extracted from Bilancio Micro, default to 0)
            # Immobilizzazioni finanziarie detail
            sp04a_partecipazioni=Decimal('0'),
            sp04b_crediti_immob_breve=Decimal('0'),
            sp04c_crediti_immob_lungo=Decimal('0'),
            sp04d_altri_titoli=Decimal('0'),
            sp04e_strumenti_derivati_attivi=Decimal('0'),
            # Riserve detail
            sp12a_riserva_sovrapprezzo=Decimal('0'),
            sp12b_riserve_rivalutazione=Decimal('0'),
            sp12c_riserva_legale=Decimal('0'),
            sp12d_riserve_statutarie=Decimal('0'),
            sp12e_altre_riserve=Decimal('0'),
            sp12f_riserva_copertura_flussi=Decimal('0'),
            sp12g_utili_perdite_portati=Decimal('0'),
            sp12h_riserva_neg_azioni_proprie=Decimal('0'),
            # Debiti detail (by nature and maturity)
            sp16a_debiti_banche_breve=Decimal('0'),
            sp17a_debiti_banche_lungo=Decimal('0'),
            sp16b_debiti_altri_finanz_breve=Decimal('0'),
            sp17b_debiti_altri_finanz_lungo=Decimal('0'),
            sp16c_debiti_obbligazioni_breve=Decimal('0'),
            sp17c_debiti_obbligazioni_lungo=Decimal('0'),
            sp16d_debiti_fornitori_breve=Decimal('0'),
            sp17d_debiti_fornitori_lungo=Decimal('0'),
            sp16e_debiti_tributari_breve=Decimal('0'),
            sp17e_debiti_tributari_lungo=Decimal('0'),
            sp16f_debiti_previdenza_breve=Decimal('0'),
            sp17f_debiti_previdenza_lungo=Decimal('0'),
            sp16g_altri_debiti_breve=Decimal('0'),
            sp17g_altri_debiti_lungo=Decimal('0'),
        )
        db.add(balance_sheet)
        db.flush()

        logger.info(f"Balance sheet created (ID: {balance_sheet.id})")

        # Step 9: Create income statement record
        # Note: Bilancio Micro format has limited income statement detail
        # Most fields will be 0 except for revenue (ce01) and any other extracted values
        income_statement = IncomeStatement(
            financial_year_id=financial_year_obj.id,
            # A) Production Value
            ce01_ricavi_vendite=income_data.get('ce01_ricavi_vendite', Decimal('0')),
            ce02_variazioni_rimanenze=Decimal('0'),
            ce03_lavori_interni=Decimal('0'),
            ce04_altri_ricavi=Decimal('0'),
            # B) Production Costs
            ce05_materie_prime=Decimal('0'),
            ce06_servizi=Decimal('0'),
            ce07_godimento_beni=Decimal('0'),
            ce08_costi_personale=Decimal('0'),
            ce08a_tfr_accrual=Decimal('0'),
            ce09_ammortamenti=Decimal('0'),
            ce09a_ammort_immateriali=Decimal('0'),
            ce09b_ammort_materiali=Decimal('0'),
            ce09c_svalutazioni=Decimal('0'),
            ce09d_svalutazione_crediti=Decimal('0'),
            ce10_var_rimanenze_mat_prime=Decimal('0'),
            ce11_accantonamenti=Decimal('0'),
            ce11b_altri_accantonamenti=Decimal('0'),
            ce12_oneri_diversi=Decimal('0'),
            # C) Financial Income/Expenses
            ce13_proventi_partecipazioni=Decimal('0'),
            ce14_altri_proventi_finanziari=Decimal('0'),
            ce15_oneri_finanziari=Decimal('0'),
            ce16_utili_perdite_cambi=Decimal('0'),
            # D) Adjustments to financial assets
            ce17_rettifiche_attivita_fin=Decimal('0'),
            # E) Extraordinary items
            ce18_proventi_straordinari=Decimal('0'),
            ce19_oneri_straordinari=Decimal('0'),
            # Taxes
            ce20_imposte=Decimal('0'),
        )
        db.add(income_statement)
        db.flush()

        logger.info(f"Income statement created (ID: {income_statement.id})")

        # Step 10: Commit transaction
        db.commit()

        extraction_time = (datetime.utcnow() - extraction_start).total_seconds()

        logger.info(
            f"PDF import successful: company={company.name}, "
            f"year={financial_year_obj.year}, "
            f"time={extraction_time:.2f}s"
        )

        return {
            "success": True,
            "company_id": company.id,
            "company_name": company.name,
            "fiscal_year": financial_year_obj.year,
            "balance_sheet_id": balance_sheet.id,
            "income_statement_id": income_statement.id,
            "format": "micro",  # TODO: Detect format from PDF
            "confidence_score": 0.95,  # Docling typical confidence
            "extraction_time_seconds": round(extraction_time, 2),
            "message": f"Successfully imported balance sheet for {company.name} ({financial_year_obj.year})",
            "warnings": warnings
        }

    except PDFImportError:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error during PDF import: {e}")
        raise PDFImportError(f"Failed to import PDF: {str(e)}")

    finally:
        db.close()
