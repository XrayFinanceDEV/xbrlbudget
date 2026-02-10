"""
Analysis API endpoints - Comprehensive financial analysis

Provides simplified API with one endpoint that returns everything:
- Historical financial data (2 years)
- Forecast financial data (3-5 years)
- All calculations (Altman, FGPMI, ratios, cashflow)

This replaces ~15 individual endpoints with one comprehensive endpoint.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.schemas import analysis as analysis_schemas
from app.services import analysis_service

router = APIRouter()


@router.get(
    "/companies/{company_id}/scenarios/{scenario_id}/analysis",
    summary="Get complete financial analysis (historical + forecast + calculations)",
    description="""
    Get comprehensive financial analysis for a scenario in ONE call.

    **Returns:**
    - Historical years (base_year - 1 and base_year): Balance Sheet + Income Statement
    - Forecast years (3 or 5 years): Balance Sheet + Income Statement + Assumptions
    - All calculations for each year:
      - Altman Z-Score (bankruptcy prediction)
      - FGPMI Rating (Italian SME credit rating)
      - Financial Ratios (liquidity, solvency, profitability, activity)
    - Multi-year Cash Flow Statement (indirect method)

    **This ONE endpoint replaces:**
    - `/scenarios/{id}/reclassified`
    - `/scenarios/{id}/detailed-cashflow`
    - `/scenarios/{id}/ratios`
    - `/years/{year}/calculations/altman`
    - `/years/{year}/calculations/fgpmi`
    - `/years/{year}/calculations/ratios`
    - `/forecasts/{year}/balance-sheet`
    - `/forecasts/{year}/income-statement`

    **Typical usage:**
    ```
    GET /api/v1/companies/123/scenarios/456/analysis
    ```

    Frontend can then display all pages (Budget, Forecast, Analysis, Cashflow)
    from this single response.
    """
)
def get_complete_analysis(
    company_id: int,
    scenario_id: int,
    include_historical: bool = Query(
        default=True,
        description="Include historical years (base_year - 1 and base_year)"
    ),
    include_forecast: bool = Query(
        default=True,
        description="Include forecast years"
    ),
    include_calculations: bool = Query(
        default=True,
        description="Include all calculations (Altman, FGPMI, ratios, cashflow)"
    ),
    db: Session = Depends(get_db)
):
    """
    Get complete financial analysis for a scenario.

    Args:
        company_id: Company ID
        scenario_id: Budget scenario ID
        include_historical: Include historical years (default: True)
        include_forecast: Include forecast years (default: True)
        include_calculations: Include calculations (default: True)
        db: Database session

    Returns:
        CompleteAnalysisResponse with all data

    Raises:
        HTTPException 404: If scenario not found
        HTTPException 400: If data incomplete or invalid
        HTTPException 500: If calculation errors occur
    """
    try:
        result = analysis_service.get_complete_analysis(
            db=db,
            company_id=company_id,
            scenario_id=scenario_id,
            include_historical=include_historical,
            include_forecast=include_forecast,
            include_calculations=include_calculations
        )
        return result

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


# Health check endpoint for this router
@router.get(
    "/analysis/health",
    summary="Health check for analysis endpoints",
    tags=["health"]
)
def analysis_health_check():
    """Health check for analysis service"""
    return {
        "status": "ok",
        "service": "analysis",
        "version": "1.0",
        "description": "Comprehensive financial analysis API"
    }
