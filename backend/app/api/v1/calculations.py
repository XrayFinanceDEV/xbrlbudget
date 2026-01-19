"""
Calculations API endpoints - Financial ratios, Altman Z-Score, FGPMI Rating
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.database import get_db
from app.schemas import calculations as calc_schemas
from app.services import calculation_service

router = APIRouter()


@router.get(
    "/companies/{company_id}/years/{year}/calculations/ratios",
    response_model=calc_schemas.AllRatios,
    summary="Calculate all financial ratios"
)
def get_financial_ratios(
    company_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """
    Calculate all financial ratios for a specific company and year.

    Returns:
    - Working capital metrics (CCLN, CCN, MS, MT)
    - Liquidity ratios (Current, Quick, Acid Test)
    - Solvency ratios (Autonomy, Leverage, D/E, D/VP)
    - Profitability ratios (ROE, ROI, ROS, ROD, margins)
    - Activity ratios (Turnover, Days metrics, Cash cycle)
    """
    try:
        return calculation_service.calculate_all_ratios(db, company_id, year)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating ratios: {str(e)}"
        )


@router.get(
    "/companies/{company_id}/years/{year}/calculations/summary",
    response_model=calc_schemas.SummaryMetrics,
    summary="Get summary financial metrics"
)
def get_summary_metrics(
    company_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """
    Get summary financial metrics for dashboard display.

    Returns key metrics:
    - Revenue, EBITDA, EBIT, Net Profit
    - Total Assets, Equity, Debt
    - Working Capital, Current Ratio
    - ROE, ROI, D/E, EBITDA Margin
    """
    try:
        return calculation_service.calculate_summary_metrics(db, company_id, year)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating summary: {str(e)}"
        )


@router.get(
    "/companies/{company_id}/years/{year}/calculations/altman",
    response_model=calc_schemas.AltmanResult,
    summary="Calculate Altman Z-Score"
)
def get_altman_zscore(
    company_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """
    Calculate Altman Z-Score for bankruptcy prediction.

    Uses sector-specific models:
    - Manufacturing (Sector 1): 5-component model
    - Services/Other (Sectors 2-6): 4-component model

    Returns:
    - Z-Score value
    - Individual components (A, B, C, D, E)
    - Classification (safe, gray_zone, distress)
    - Italian interpretation text
    """
    try:
        return calculation_service.calculate_altman_zscore(db, company_id, year)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating Altman Z-Score: {str(e)}"
        )


@router.get(
    "/companies/{company_id}/years/{year}/calculations/fgpmi",
    response_model=calc_schemas.FGPMIResult,
    summary="Calculate FGPMI credit rating"
)
def get_fgpmi_rating(
    company_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """
    Calculate FGPMI (Fondo di Garanzia PMI) credit rating.

    Multi-indicator scoring model with sector-specific thresholds.
    Used for Italian SME access to government-backed loan guarantees.

    Returns:
    - Total score and max score
    - Rating class (1-13) and code (AAA to B-)
    - Rating description and risk level
    - Revenue bonus (+2 if >500K)
    - Individual indicator scores (V1-V7)
    """
    try:
        return calculation_service.calculate_fgpmi_rating(db, company_id, year)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating FGPMI rating: {str(e)}"
        )


@router.get(
    "/companies/{company_id}/years/{year}/calculations/complete",
    response_model=calc_schemas.FinancialAnalysis,
    summary="Complete financial analysis"
)
def get_complete_analysis(
    company_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """
    Get complete financial analysis including:
    - All financial ratios
    - Altman Z-Score
    - FGPMI credit rating
    - Summary metrics

    This is a comprehensive endpoint that returns all calculations in one response.
    """
    try:
        return calculation_service.calculate_complete_analysis(db, company_id, year)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculating complete analysis: {str(e)}"
        )


# Convenience endpoints for individual ratio categories

@router.get(
    "/companies/{company_id}/years/{year}/calculations/ratios/liquidity",
    response_model=calc_schemas.LiquidityRatios,
    summary="Get liquidity ratios only"
)
def get_liquidity_ratios(
    company_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """Get only liquidity ratios (Current, Quick, Acid Test)"""
    try:
        all_ratios = calculation_service.calculate_all_ratios(db, company_id, year)
        return all_ratios.liquidity
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/companies/{company_id}/years/{year}/calculations/ratios/profitability",
    response_model=calc_schemas.ProfitabilityRatios,
    summary="Get profitability ratios only"
)
def get_profitability_ratios(
    company_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """Get only profitability ratios (ROE, ROI, ROS, margins)"""
    try:
        all_ratios = calculation_service.calculate_all_ratios(db, company_id, year)
        return all_ratios.profitability
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get(
    "/companies/{company_id}/years/{year}/calculations/ratios/solvency",
    response_model=calc_schemas.SolvencyRatios,
    summary="Get solvency ratios only"
)
def get_solvency_ratios(
    company_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """Get only solvency/leverage ratios"""
    try:
        all_ratios = calculation_service.calculate_all_ratios(db, company_id, year)
        return all_ratios.solvency
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
