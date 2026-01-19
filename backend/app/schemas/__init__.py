"""
Pydantic schemas for API request/response models
"""
from .company import (
    Company,
    CompanyCreate,
    CompanyUpdate,
    CompanyInDB
)
from .financial_year import (
    FinancialYear,
    FinancialYearCreate,
    FinancialYearUpdate,
    FinancialYearInDB
)
from .balance_sheet import (
    BalanceSheet,
    BalanceSheetCreate,
    BalanceSheetUpdate,
    BalanceSheetInDB
)
from .income_statement import (
    IncomeStatement,
    IncomeStatementCreate,
    IncomeStatementUpdate,
    IncomeStatementInDB
)
from .budget import (
    BudgetScenario,
    BudgetScenarioCreate,
    BudgetScenarioUpdate,
    BudgetScenarioInDB,
    BudgetAssumptions,
    BudgetAssumptionsCreate,
    BudgetAssumptionsUpdate,
    BudgetAssumptionsInDB,
    ForecastYear,
    ForecastYearCreate,
    ForecastYearInDB
)
from .calculations import (
    WorkingCapitalMetrics,
    LiquidityRatios,
    SolvencyRatios,
    ProfitabilityRatios,
    ActivityRatios,
    AllRatios,
    SummaryMetrics,
    AltmanComponents,
    AltmanResult,
    IndicatorScore,
    FGPMIResult,
    FinancialAnalysis
)

__all__ = [
    # Company
    "Company",
    "CompanyCreate",
    "CompanyUpdate",
    "CompanyInDB",
    # FinancialYear
    "FinancialYear",
    "FinancialYearCreate",
    "FinancialYearUpdate",
    "FinancialYearInDB",
    # BalanceSheet
    "BalanceSheet",
    "BalanceSheetCreate",
    "BalanceSheetUpdate",
    "BalanceSheetInDB",
    # IncomeStatement
    "IncomeStatement",
    "IncomeStatementCreate",
    "IncomeStatementUpdate",
    "IncomeStatementInDB",
    # Budget & Forecast
    "BudgetScenario",
    "BudgetScenarioCreate",
    "BudgetScenarioUpdate",
    "BudgetScenarioInDB",
    "BudgetAssumptions",
    "BudgetAssumptionsCreate",
    "BudgetAssumptionsUpdate",
    "BudgetAssumptionsInDB",
    "ForecastYear",
    "ForecastYearCreate",
    "ForecastYearInDB",
]
