"""
PDF Balance Sheet Importer for Italian IV CEE format.

Uses PyMuPDF + Claude Haiku 4.5 (~5s). Requires ANTHROPIC_API_KEY.
"""

import os
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from database.db import SessionLocal
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from importers.pdf_mapper import IVCEEMapper
from config import Sector

logger = logging.getLogger(__name__)


class PDFImportError(Exception):
    """Exception raised when PDF import fails."""
    pass


def _create_balance_sheet(db, financial_year_id: int, data: Dict[str, Decimal]) -> 'BalanceSheet':
    """Create a BalanceSheet record from a dict of sp01-sp18 values."""
    bs = BalanceSheet(
        financial_year_id=financial_year_id,
        sp01_crediti_soci=data.get('sp01_crediti_soci', Decimal('0')),
        sp02_immob_immateriali=data.get('sp02_immob_immateriali', Decimal('0')),
        sp03_immob_materiali=data.get('sp03_immob_materiali', Decimal('0')),
        sp04_immob_finanziarie=data.get('sp04_immob_finanziarie', Decimal('0')),
        sp05_rimanenze=data.get('sp05_rimanenze', Decimal('0')),
        sp06_crediti_breve=data.get('sp06_crediti_breve', Decimal('0')),
        sp07_crediti_lungo=data.get('sp07_crediti_lungo', Decimal('0')),
        sp08_attivita_finanziarie=data.get('sp08_attivita_finanziarie', Decimal('0')),
        sp09_disponibilita_liquide=data.get('sp09_disponibilita_liquide', Decimal('0')),
        sp10_ratei_risconti_attivi=data.get('sp10_ratei_risconti_attivi', Decimal('0')),
        sp11_capitale=data.get('sp11_capitale', Decimal('0')),
        sp12_riserve=data.get('sp12_riserve', Decimal('0')),
        sp13_utile_perdita=data.get('sp13_utile_perdita', Decimal('0')),
        sp14_fondi_rischi=data.get('sp14_fondi_rischi', Decimal('0')),
        sp15_tfr=data.get('sp15_tfr', Decimal('0')),
        sp16_debiti_breve=data.get('sp16_debiti_breve', Decimal('0')),
        sp17_debiti_lungo=data.get('sp17_debiti_lungo', Decimal('0')),
        sp18_ratei_risconti_passivi=data.get('sp18_ratei_risconti_passivi', Decimal('0')),
        sp04a_partecipazioni=Decimal('0'),
        sp04b_crediti_immob_breve=Decimal('0'),
        sp04c_crediti_immob_lungo=Decimal('0'),
        sp04d_altri_titoli=Decimal('0'),
        sp04e_strumenti_derivati_attivi=Decimal('0'),
        sp12a_riserva_sovrapprezzo=Decimal('0'),
        sp12b_riserve_rivalutazione=Decimal('0'),
        sp12c_riserva_legale=Decimal('0'),
        sp12d_riserve_statutarie=Decimal('0'),
        sp12e_altre_riserve=Decimal('0'),
        sp12f_riserva_copertura_flussi=Decimal('0'),
        sp12g_utili_perdite_portati=Decimal('0'),
        sp12h_riserva_neg_azioni_proprie=Decimal('0'),
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
    db.add(bs)
    db.flush()
    return bs


def _create_income_statement(db, financial_year_id: int, data: Dict[str, Decimal]) -> 'IncomeStatement':
    """Create an IncomeStatement record from a dict of ce01-ce20 values."""
    def _ce(field: str) -> Decimal:
        return data.get(field, Decimal('0'))

    inc = IncomeStatement(
        financial_year_id=financial_year_id,
        ce01_ricavi_vendite=_ce('ce01_ricavi_vendite'),
        ce02_variazioni_rimanenze=_ce('ce02_variazioni_rimanenze'),
        ce03_lavori_interni=_ce('ce03_lavori_interni'),
        ce04_altri_ricavi=_ce('ce04_altri_ricavi'),
        ce05_materie_prime=_ce('ce05_materie_prime'),
        ce06_servizi=_ce('ce06_servizi'),
        ce07_godimento_beni=_ce('ce07_godimento_beni'),
        ce08_costi_personale=_ce('ce08_costi_personale'),
        ce08a_tfr_accrual=_ce('ce08a_tfr_accrual'),
        ce09_ammortamenti=_ce('ce09_ammortamenti'),
        ce09a_ammort_immateriali=_ce('ce09a_ammort_immateriali'),
        ce09b_ammort_materiali=_ce('ce09b_ammort_materiali'),
        ce09c_svalutazioni=_ce('ce09c_svalutazioni'),
        ce09d_svalutazione_crediti=_ce('ce09d_svalutazione_crediti'),
        ce10_var_rimanenze_mat_prime=_ce('ce10_var_rimanenze_mat_prime'),
        ce11_accantonamenti=_ce('ce11_accantonamenti'),
        ce11b_altri_accantonamenti=_ce('ce11b_altri_accantonamenti'),
        ce12_oneri_diversi=_ce('ce12_oneri_diversi'),
        ce13_proventi_partecipazioni=_ce('ce13_proventi_partecipazioni'),
        ce14_altri_proventi_finanziari=_ce('ce14_altri_proventi_finanziari'),
        ce15_oneri_finanziari=_ce('ce15_oneri_finanziari'),
        ce16_utili_perdite_cambi=_ce('ce16_utili_perdite_cambi'),
        ce17_rettifiche_attivita_fin=_ce('ce17_rettifiche_attivita_fin'),
        ce18_proventi_straordinari=_ce('ce18_proventi_straordinari'),
        ce19_oneri_straordinari=_ce('ce19_oneri_straordinari'),
        ce20_imposte=_ce('ce20_imposte'),
    )
    db.add(inc)
    db.flush()
    return inc


def import_pdf_balance_sheet(
    file_path: str,
    company_id: Optional[int] = None,
    fiscal_year: Optional[int] = None,
    company_name: Optional[str] = None,
    create_company: bool = True,
    sector: Optional[int] = None,
    period_months: Optional[int] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Import balance sheet from PDF file.

    Uses PyMuPDF + Claude Haiku 4.5. Requires ANTHROPIC_API_KEY.

    Args:
        file_path: Path to PDF file
        company_id: Optional company ID (will be created if None and create_company=True)
        fiscal_year: Fiscal year for the balance sheet
        company_name: Company name (for new company creation)
        create_company: Whether to create company if not exists
        sector: Company sector code (1-6)

    Returns:
        Dictionary with import results

    Raises:
        PDFImportError: If extraction or validation fails
    """

    db = SessionLocal()
    extraction_start = datetime.utcnow()

    try:
        logger.info(f"Starting PDF import from {file_path}")

        mapper = IVCEEMapper()
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')

        # Step 1: Extract PDF data via LLM (requires ANTHROPIC_API_KEY)
        prior_bs_data = None
        prior_ce_data = None
        if not api_key:
            raise PDFImportError("ANTHROPIC_API_KEY is required for PDF import")

        logger.info("Using LLM extraction (ANTHROPIC_API_KEY found)")
        if period_months:
            # Dual-year extraction for infrannuale: get both columns
            from importers.pdf_extractor_llm import extract_pdf_both_years_with_llm
            logger.info(f"Dual-year extraction (period_months={period_months})")
            balance_sheet_data, income_data, prior_bs_data, prior_ce_data = extract_pdf_both_years_with_llm(file_path)
        else:
            # Single-year extraction for budget
            from importers.pdf_extractor_llm import extract_pdf_with_llm
            balance_sheet_data, income_data = extract_pdf_with_llm(file_path)

        # Step 2: Validate balance sheet (both paths)
        logger.info("Validating balance sheet...")
        if not mapper.validate_balance(balance_sheet_data):
            raise PDFImportError("Balance sheet does not balance (Assets != Liabilities + Equity)")

        warnings = mapper.validate_hierarchy(balance_sheet_data)
        if warnings:
            logger.warning(f"Balance sheet hierarchy warnings: {warnings}")

        # Step 3: Handle company
        company = None
        if company_id:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise PDFImportError(f"Company with ID {company_id} not found")
            if user_id and company.user_id != user_id:
                raise PDFImportError(f"Company with ID {company_id} not found")
        elif create_company and company_name:
            company = Company(
                name=company_name,
                tax_id=None,
                sector=sector or Sector.SERVIZI.value,
                user_id=user_id,
            )
            db.add(company)
            db.flush()
            logger.info(f"Created new company: {company.name} (ID: {company.id})")
        else:
            raise PDFImportError("Either company_id or (create_company=True and company_name) must be provided")

        # Step 4: Check if fiscal year already exists (match same type: partial or full)
        if fiscal_year:
            if period_months:
                # Partial import: only delete existing partial record
                existing_year = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == fiscal_year,
                    FinancialYear.period_months.isnot(None),
                ).first()
            else:
                # Full-year import: only delete existing full-year record
                existing_year = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == fiscal_year,
                    FinancialYear.period_months.is_(None),
                ).first()

            if existing_year:
                logger.warning(f"Financial year {fiscal_year} (period_months={existing_year.period_months}) already exists for company {company.id}, will update")
                if existing_year.balance_sheet:
                    db.delete(existing_year.balance_sheet)
                if existing_year.income_statement:
                    db.delete(existing_year.income_statement)
                db.delete(existing_year)
                db.flush()

        # Step 5: Create current-year financial year
        current_year_val = fiscal_year or datetime.now().year
        financial_year_obj = FinancialYear(
            company_id=company.id,
            year=current_year_val,
            period_months=period_months  # None for full year, 1-11 for partial
        )
        db.add(financial_year_obj)
        db.flush()

        # Step 6: Create balance sheet and income statement (current year)
        balance_sheet = _create_balance_sheet(db, financial_year_obj.id, balance_sheet_data)
        logger.info(f"Balance sheet created (ID: {balance_sheet.id})")

        income_statement = _create_income_statement(db, financial_year_obj.id, income_data)
        logger.info(f"Income statement created (ID: {income_statement.id})")

        # Step 7: Save prior year if dual-year extraction was used
        prior_year_imported = False
        prior_fiscal_year = fiscal_year - 1 if fiscal_year else None
        if prior_bs_data and prior_ce_data and fiscal_year:
            # Check if prior year data is meaningful (not all zeros from single-column PDF)
            prior_sp_fields = [v for k, v in prior_bs_data.items()
                               if k.startswith('sp') and k != 'totale_attivo' and k != 'totale_passivo']
            prior_has_data = any(v != Decimal('0') for v in prior_sp_fields)

            if not prior_has_data:
                logger.info("Prior year data is all zeros (single-column PDF), skipping")
            else:
                # Only import prior year if a full-year record doesn't already exist
                existing_prior = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == prior_fiscal_year,
                    FinancialYear.period_months.is_(None),
                ).first()

                if existing_prior:
                    logger.info(f"Prior year {prior_fiscal_year} already exists for company {company.id}, skipping")
                    prior_year_imported = True  # already present
                else:
                    # Validate prior year balance sheet
                    if mapper.validate_balance(prior_bs_data):
                        prior_fy = FinancialYear(
                            company_id=company.id,
                            year=prior_fiscal_year,
                            period_months=None  # Full 12-month year
                        )
                        db.add(prior_fy)
                        db.flush()

                        prior_bs = _create_balance_sheet(db, prior_fy.id, prior_bs_data)
                        prior_ce = _create_income_statement(db, prior_fy.id, prior_ce_data)
                        prior_year_imported = True
                        logger.info(
                            f"Prior year {prior_fiscal_year} imported (BS ID: {prior_bs.id}, CE ID: {prior_ce.id})"
                        )
                    else:
                        logger.warning(f"Prior year {prior_fiscal_year} balance sheet does not balance, skipping")

        # Step 8: Commit transaction
        db.commit()

        extraction_time = (datetime.utcnow() - extraction_start).total_seconds()
        extraction_method = "llm"

        logger.info(
            f"PDF import successful: company={company.name}, "
            f"year={financial_year_obj.year}, "
            f"method={extraction_method}, "
            f"time={extraction_time:.2f}s"
        )

        result = {
            "success": True,
            "company_id": company.id,
            "company_name": company.name,
            "fiscal_year": financial_year_obj.year,
            "balance_sheet_id": balance_sheet.id,
            "income_statement_id": income_statement.id,
            "format": "micro",  # TODO: Detect format from PDF
            "confidence_score": 0.95,
            "extraction_method": extraction_method,
            "extraction_time_seconds": round(extraction_time, 2),
            "message": f"Successfully imported balance sheet for {company.name} ({financial_year_obj.year})",
            "warnings": warnings
        }

        result["prior_year_imported"] = prior_year_imported
        result["prior_fiscal_year"] = prior_fiscal_year

        return result

    except PDFImportError:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error during PDF import: {e}")
        raise PDFImportError(f"Failed to import PDF: {str(e)}")

    finally:
        db.close()
