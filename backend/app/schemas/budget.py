"""
Pydantic schemas for Budget and Forecast models
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List
from decimal import Decimal


# BudgetScenario Schemas
class BudgetScenarioBase(BaseModel):
    """Base BudgetScenario schema"""
    company_id: int
    name: str = Field(..., min_length=1, max_length=255)
    base_year: int = Field(..., ge=2000, le=2100)
    scenario_type: str = Field(default="budget")  # "budget" | "infrannuale"
    period_months: Optional[int] = Field(default=None, ge=1, le=12)
    description: Optional[str] = None
    is_active: int = Field(default=1, ge=0, le=1)


class BudgetScenarioCreate(BudgetScenarioBase):
    """Schema for creating a new BudgetScenario"""
    pass


class BudgetScenarioUpdate(BaseModel):
    """Schema for updating a BudgetScenario"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    base_year: Optional[int] = Field(None, ge=2000, le=2100)
    scenario_type: Optional[str] = None
    period_months: Optional[int] = Field(None, ge=1, le=12)
    description: Optional[str] = None
    is_active: Optional[int] = Field(None, ge=0, le=1)


class BudgetScenarioInDB(BudgetScenarioBase):
    """BudgetScenario schema with database fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class BudgetScenario(BudgetScenarioInDB):
    """Full BudgetScenario schema for API responses"""
    pass


# BudgetAssumptions Schemas
class BudgetAssumptionsBase(BaseModel):
    """Base BudgetAssumptions schema"""
    scenario_id: int
    forecast_year: int = Field(..., ge=2000, le=2100)

    # Revenue assumptions
    revenue_growth_pct: Decimal = Field(default=Decimal("0"))
    other_revenue_growth_pct: Decimal = Field(default=Decimal("0"))

    # Cost assumptions
    variable_materials_growth_pct: Decimal = Field(default=Decimal("0"))
    fixed_materials_growth_pct: Decimal = Field(default=Decimal("0"))
    variable_services_growth_pct: Decimal = Field(default=Decimal("0"))
    fixed_services_growth_pct: Decimal = Field(default=Decimal("0"))
    rent_growth_pct: Decimal = Field(default=Decimal("0"))
    personnel_growth_pct: Decimal = Field(default=Decimal("0"))
    other_costs_growth_pct: Decimal = Field(default=Decimal("0"))

    # Investment and working capital
    investments: Decimal = Field(default=Decimal("0"))
    receivables_short_growth_pct: Decimal = Field(default=Decimal("0"))
    receivables_long_growth_pct: Decimal = Field(default=Decimal("0"))
    payables_short_growth_pct: Decimal = Field(default=Decimal("0"))

    # Financial parameters
    interest_rate_receivables: Decimal = Field(default=Decimal("0"))
    interest_rate_payables: Decimal = Field(default=Decimal("0"))

    # Tax and other parameters
    tax_rate: Decimal = Field(default=Decimal("24"))
    fixed_materials_percentage: Decimal = Field(default=Decimal("40"))
    fixed_services_percentage: Decimal = Field(default=Decimal("40"))
    depreciation_rate: Decimal = Field(default=Decimal("20"))

    # Financing parameters
    financing_amount: Decimal = Field(default=Decimal("0"))
    financing_duration_years: Decimal = Field(default=Decimal("0"))
    financing_interest_rate: Decimal = Field(default=Decimal("0"))

    # CE line item overrides (absolute EUR values, None = use base year value)
    ce02_override: Optional[Decimal] = None
    ce03_override: Optional[Decimal] = None
    ce10_override: Optional[Decimal] = None
    ce11_override: Optional[Decimal] = None
    ce13_override: Optional[Decimal] = None
    ce14_override: Optional[Decimal] = None
    ce15_override: Optional[Decimal] = None
    ce16_override: Optional[Decimal] = None
    ce17_override: Optional[Decimal] = None
    ce18_override: Optional[Decimal] = None
    ce19_override: Optional[Decimal] = None


class BudgetAssumptionsCreate(BudgetAssumptionsBase):
    """Schema for creating new BudgetAssumptions"""
    pass


class BudgetAssumptionsUpdate(BaseModel):
    """Schema for updating BudgetAssumptions"""
    forecast_year: Optional[int] = Field(None, ge=2000, le=2100)
    revenue_growth_pct: Optional[Decimal] = None
    other_revenue_growth_pct: Optional[Decimal] = None
    variable_materials_growth_pct: Optional[Decimal] = None
    fixed_materials_growth_pct: Optional[Decimal] = None
    variable_services_growth_pct: Optional[Decimal] = None
    fixed_services_growth_pct: Optional[Decimal] = None
    rent_growth_pct: Optional[Decimal] = None
    personnel_growth_pct: Optional[Decimal] = None
    other_costs_growth_pct: Optional[Decimal] = None
    investments: Optional[Decimal] = None
    receivables_short_growth_pct: Optional[Decimal] = None
    receivables_long_growth_pct: Optional[Decimal] = None
    payables_short_growth_pct: Optional[Decimal] = None
    interest_rate_receivables: Optional[Decimal] = None
    interest_rate_payables: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    fixed_materials_percentage: Optional[Decimal] = None
    fixed_services_percentage: Optional[Decimal] = None
    depreciation_rate: Optional[Decimal] = None
    financing_amount: Optional[Decimal] = None
    financing_duration_years: Optional[Decimal] = None
    financing_interest_rate: Optional[Decimal] = None

    # CE line item overrides
    ce02_override: Optional[Decimal] = None
    ce03_override: Optional[Decimal] = None
    ce10_override: Optional[Decimal] = None
    ce11_override: Optional[Decimal] = None
    ce13_override: Optional[Decimal] = None
    ce14_override: Optional[Decimal] = None
    ce15_override: Optional[Decimal] = None
    ce16_override: Optional[Decimal] = None
    ce17_override: Optional[Decimal] = None
    ce18_override: Optional[Decimal] = None
    ce19_override: Optional[Decimal] = None


class BudgetAssumptionsInDB(BudgetAssumptionsBase):
    """BudgetAssumptions schema with database fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class BudgetAssumptions(BudgetAssumptionsInDB):
    """Full BudgetAssumptions schema for API responses"""
    pass


# ForecastYear Schemas
class ForecastYearBase(BaseModel):
    """Base ForecastYear schema"""
    scenario_id: int
    year: int = Field(..., ge=2000, le=2100)


class ForecastYearCreate(ForecastYearBase):
    """Schema for creating a new ForecastYear"""
    pass


class ForecastYearInDB(ForecastYearBase):
    """ForecastYear schema with database fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ForecastYear(ForecastYearInDB):
    """Full ForecastYear schema for API responses"""
    pass


# Intra-Year Comparison Schemas
class IntraYearComparisonItem(BaseModel):
    """Single line item comparison between partial year and reference"""
    code: str
    label: str
    partial_value: float
    reference_value: float
    pct_of_reference: float
    annualized_value: float


class IntraYearComparison(BaseModel):
    """Complete comparison between partial year and reference full year"""
    partial_year: int
    reference_year: int
    period_months: int
    income_items: List[IntraYearComparisonItem]
    balance_items: List[IntraYearComparisonItem]
