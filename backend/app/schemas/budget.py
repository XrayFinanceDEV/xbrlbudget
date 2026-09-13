"""
Pydantic schemas for Budget and Forecast models
"""
from pydantic import BaseModel, Field, ConfigDict, StrictBool, field_serializer, field_validator, model_validator
from datetime import datetime, timezone
from typing import Optional, List, Dict, Literal
from decimal import Decimal


WorkflowType = Literal["infrannuale", "bilancio", "startup"]
WorkflowIntent = Literal["startup"]
WorkflowOrigin = Literal["imported", "manual", "startup_opening", "promoted_projection"]
ExtraAccountingAlertCode = Literal[
    "retribuzioni", "fornitori", "banche", "inps", "inail", "riscossione", "iva",
]
NarrativeBlockOrigin = Literal["ai", "user", "migrated"]
NarrativeBlockId = Literal[
    "executive_summary",
    "adjustments_and_closing",
    "budget_assumptions",
    "economic_outlook",
    "financial_outlook",
    "risks_and_actions",
]


class ExtraAccountingAlerts(BaseModel):
    """The seven frontend alert flags, persisted as a sparse JSON object."""
    model_config = ConfigDict(extra="forbid")

    retribuzioni: StrictBool = False
    fornitori: StrictBool = False
    banche: StrictBool = False
    inps: StrictBool = False
    inail: StrictBool = False
    riscossione: StrictBool = False
    iva: StrictBool = False


class ExtraAccountingAlertsUpdate(BaseModel):
    """Complete client payload accepted only by the dedicated alerts endpoint."""
    model_config = ConfigDict(extra="forbid")

    retribuzioni: StrictBool
    fornitori: StrictBool
    banche: StrictBool
    inps: StrictBool
    inail: StrictBool
    riscossione: StrictBool
    iva: StrictBool


class ExtraAccountingAlertsResponse(BaseModel):
    """Normalized alert flags plus their server-owned modification time."""
    alerts: ExtraAccountingAlerts
    updated_at: Optional[datetime] = None


class NarrativeBlock(BaseModel):
    """One stable report narrative block and the data revision it describes."""
    id: NarrativeBlockId
    text: str = Field(..., min_length=1)
    origin: NarrativeBlockOrigin
    updated_at: datetime
    source_hash: str = Field(..., min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class NarrativeBlocks(BaseModel):
    """Versioned JSON container persisted on a budget scenario."""
    schema_version: Literal[1] = 1
    blocks: List[NarrativeBlock] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_block_ids(self):
        ids = [block.id for block in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("Narrative block IDs must be unique")
        return self


def _validate_explicitly_supplied_fields(value: Optional[List[str]]) -> Optional[List[str]]:
    """Keep the JSON list unambiguous; NULL remains the legacy-unknown marker."""
    if value is None:
        return value
    if any(not field or field != field.strip() for field in value):
        raise ValueError("Explicitly supplied field names must not be blank or padded")
    if len(value) != len(set(value)):
        raise ValueError("Explicitly supplied field names must be unique")
    allowed_fields = set(BudgetAssumptionsBase.model_fields).difference({
        "scenario_id", "forecast_year", "explicitly_supplied_fields",
    })
    unknown = set(value).difference(allowed_fields)
    if unknown:
        raise ValueError(
            "Explicitly supplied fields must be BudgetAssumptions schema fields: "
            + ", ".join(sorted(unknown))
        )
    return value


# BudgetScenario Schemas
class BudgetScenarioBase(BaseModel):
    """Base BudgetScenario schema"""
    company_id: int
    name: str = Field(..., min_length=1, max_length=255)
    base_year: int = Field(..., ge=2000, le=2100)
    scenario_type: str = Field(default="budget")  # "budget" | "infrannuale"
    period_months: Optional[int] = Field(default=None, ge=1, le=12)
    # Pratica chain / workflow (2026-07-06). Additive, nullable.
    source_scenario_id: Optional[int] = None
    workflow_type: Optional[WorkflowType] = None
    extra_accounting_alerts: Optional[ExtraAccountingAlerts] = None
    extra_accounting_alerts_updated_at: Optional[datetime] = None
    narrative_blocks: Optional[NarrativeBlocks] = None
    narrative_blocks_updated_at: Optional[datetime] = None
    narrative_source_hash: Optional[str] = Field(
        None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
    description: Optional[str] = None
    is_active: int = Field(default=1, ge=0, le=1)

    @field_serializer("extra_accounting_alerts_updated_at")
    def serialize_extra_accounting_alerts_updated_at(
        self, value: Optional[datetime], _info,
    ) -> Optional[datetime]:
        if value is None:
            return None
        return (
            value.replace(tzinfo=timezone.utc)
            if value.tzinfo is None
            else value.astimezone(timezone.utc)
        )

    @model_validator(mode="after")
    def validate_infrannuale_period(self):
        if self.scenario_type == "infrannuale":
            if self.period_months is None or not 1 <= self.period_months <= 12:
                raise ValueError(
                    "An infrannuale scenario requires period_months between 1 and 12"
                )
        return self


class BudgetScenarioCreate(BudgetScenarioBase):
    """Schema for creating a new BudgetScenario"""
    # This is the sole client-provided workflow hint.  `source_scenario_id` and
    # `workflow_type` remain on the shared base model for responses/legacy
    # callers, but the endpoint rejects either if supplied and derives them.
    workflow_intent: Optional[WorkflowIntent] = None
    # Creation is intentionally non-idempotent by default.  Callers that are
    # retrying a known creation may opt into exact active-scenario reuse.
    reuse_existing: bool = False


class BudgetScenarioUpdate(BaseModel):
    """Schema for updating a BudgetScenario"""
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    narrative_blocks: Optional[NarrativeBlocks] = None
    narrative_blocks_updated_at: Optional[datetime] = None
    narrative_source_hash: Optional[str] = Field(
        None, min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )
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
class FinancingLoanInput(BaseModel):
    """Financing contract raised or already outstanding in the parent year."""
    name: Optional[str] = Field(default=None, max_length=100)
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    opening_residual: Decimal = Field(default=Decimal("0"), ge=0)
    duration_years: int = Field(..., gt=0, le=50)
    interest_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    grace_years: int = Field(default=0, ge=0, le=49)
    balloon_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)

    @model_validator(mode="after")
    def validate_contract(self):
        if self.amount == 0 and self.opening_residual == 0:
            raise ValueError("l'importo o il residuo iniziale devono essere maggiori di zero")
        if self.grace_years >= self.duration_years:
            raise ValueError("gli anni di preammortamento devono essere meno della durata")
        return self


class TemporaryDifferenceInput(BaseModel):
    """Tax-base roll-forward used to calculate deferred/anticipated taxes."""
    name: str = Field(..., min_length=1, max_length=100)
    kind: str = Field(default="deductible", pattern="^(deductible|taxable)$")
    maturity: str = Field(default="short", pattern="^(short|long)$")
    opening_amount: Decimal = Field(default=Decimal("0"), ge=0)
    additions: Decimal = Field(default=Decimal("0"), ge=0)
    reversals: Decimal = Field(default=Decimal("0"), ge=0)
    tax_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)


SpIndexingDriver = Literal["ricavi", "acquisti", "personale"]
"""I tre driver di volume, e solo tre (Task 15 §2).

`ricavi` = `ce01` previsto / `ce01` base · `acquisti` = `ce05 + ce06` ·
`personale` = `ce08`. Un quarto nome e' un errore del chiamante e va rifiutato
qui: il motore non inventa un fattore per un driver che non conosce, e un 422
dice al client che cosa ha sbagliato meglio di una chiave silenziosamente
ignorata.
"""


class PregressoPlanInput(BaseModel):
    """Runoff plan for a working capital item (receivables or payables)."""
    opening: Decimal = Field(..., ge=0)
    amounts: List[Decimal] = Field(default_factory=list)
    writeoff: Optional[List[Decimal]] = None  # solo crediti_commerciali


class PregressoTributariInput(PregressoPlanInput):
    """Runoff plan for tax payables with settlement details."""
    saldo: Decimal = Field(default=Decimal("0"), ge=0)
    rateizzato: Decimal = Field(default=Decimal("0"), ge=0)
    acconto_pct: Decimal = Field(default=Decimal("100"), ge=0, le=200)


class PregressoInput(BaseModel):
    """Opening balances and runoff schedules for working capital items and tax payables."""
    crediti_commerciali: Optional[PregressoPlanInput] = None
    debiti_fornitori: Optional[PregressoPlanInput] = None
    debiti_tributari: Optional[PregressoTributariInput] = None
    debiti_previdenziali: Optional[PregressoPlanInput] = None
    altri_debiti: Optional[PregressoPlanInput] = None


class BudgetAssumptionsBase(BaseModel):
    """Base BudgetAssumptions schema"""
    scenario_id: int
    forecast_year: int = Field(..., ge=2000, le=2100)
    explicitly_supplied_fields: Optional[List[str]] = None

    @field_validator("explicitly_supplied_fields")
    @classmethod
    def validate_explicitly_supplied_fields(cls, value):
        return _validate_explicitly_supplied_fields(value)

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
    investments: Decimal = Field(default=Decimal("0"))  # Legacy total (ignored if split fields provided)
    intangible_investments: Decimal = Field(default=Decimal("0"))
    tangible_investments: Decimal = Field(default=Decimal("0"))
    asset_disposal_nbv: Optional[Decimal] = None        # Valore netto contabile cespite ceduto
    asset_disposal_proceeds: Optional[Decimal] = None   # Corrispettivo di vendita
    receivables_short_growth_pct: Decimal = Field(default=Decimal("0"))
    receivables_long_growth_pct: Decimal = Field(default=Decimal("0"))
    payables_short_growth_pct: Decimal = Field(default=Decimal("0"))

    # Working capital turnover days (None = auto-compute from base year)
    dso_days: Optional[Decimal] = None
    dio_days: Optional[Decimal] = None
    dpo_days: Optional[Decimal] = None

    # Existing financial debt repayment (None = keep constant)
    existing_debt_repayment_years: Optional[Decimal] = None  # repays total bank debt (sp16a/sp17a)
    altri_finanz_repayment_years: Optional[Decimal] = None   # repays altri finanziatori (sp17b)

    # Cash sweep (opt-in): excess cash above the floor pays down bank debt
    cash_sweep_enabled: bool = False
    cash_sweep_min_cash: Optional[Decimal] = None

    # Scoperto di c/c (opt-in): un fabbisogno scoperto diventa sp16a generato dal
    # piano invece di far alzare il motore. Spento = comportamento di sempre.
    overdraft_allowed: bool = False
    # None = concesso senza tetto; negativo non ha senso (un fido non e' un credito).
    overdraft_limit: Optional[Decimal] = Field(default=None, ge=0)

    # TFR accrual suspended (TFR paid to INPS, fund stops growing this year)
    tfr_accrual_suspended: bool = False

    # Previdenza scales with personnel cost (opt-in): sp16f/sp17f move with ce08
    previdenza_scales_with_personnel: bool = False

    # Financial parameters
    interest_rate_receivables: Decimal = Field(default=Decimal("0"))
    interest_rate_payables: Decimal = Field(default=Decimal("0"))

    # Tax and other parameters
    tax_rate: Decimal = Field(default=Decimal("24"))
    tax_advances_paid: Decimal = Field(default=Decimal("0"), ge=0)
    tax_temporary_differences: Optional[List[TemporaryDifferenceInput]] = None
    fixed_materials_percentage: Decimal = Field(default=Decimal("40"))
    fixed_services_percentage: Decimal = Field(default=Decimal("40"))
    depreciation_rate: Decimal = Field(default=Decimal("20"))
    depreciation_rate_intangible: Decimal = Field(default=Decimal("20"))

    # Financing parameters
    financing_amount: Decimal = Field(default=Decimal("0"))
    financing_duration_years: Decimal = Field(default=Decimal("0"))
    financing_interest_rate: Decimal = Field(default=Decimal("0"))
    financing_loans: Optional[List[FinancingLoanInput]] = None

    # Scadenziamento del pregresso (runoff schedules for working capital and tax payables)
    pregresso: Optional[PregressoInput] = None

    # Indicizzazione delle voci minori dello SP a un driver di volume (Task 15).
    # Chiave assente = costante, cioe' il comportamento di sempre.
    sp_indexing: Optional[Dict[str, SpIndexingDriver]] = None

    # SP line item growth % overrides (None = 0% / carry forward unchanged)
    sp01_growth_pct: Optional[Decimal] = None
    sp04_growth_pct: Optional[Decimal] = None
    sp06e_growth_pct: Optional[Decimal] = None  # Crediti tributari (breve) — carry-forward + manual %
    sp06f_growth_pct: Optional[Decimal] = None  # Imposte anticipate (breve) — carry-forward + manual %
    sp08_growth_pct: Optional[Decimal] = None
    sp10_growth_pct: Optional[Decimal] = None
    sp14_growth_pct: Optional[Decimal] = None
    sp16e_growth_pct: Optional[Decimal] = None
    sp16f_growth_pct: Optional[Decimal] = None
    sp16g_growth_pct: Optional[Decimal] = None
    sp17d_growth_pct: Optional[Decimal] = None
    sp17e_growth_pct: Optional[Decimal] = None
    sp17f_growth_pct: Optional[Decimal] = None
    sp17g_growth_pct: Optional[Decimal] = None
    sp18_growth_pct: Optional[Decimal] = None
    sp_overrides: Optional[Dict[str, Decimal]] = None

    # CE line item overrides (absolute EUR values, None = use base year value)
    ce02_override: Optional[Decimal] = None
    ce03_override: Optional[Decimal] = None
    ce03a_override: Optional[Decimal] = None
    ce10_override: Optional[Decimal] = None
    ce11_override: Optional[Decimal] = None
    ce13_override: Optional[Decimal] = None
    ce14_override: Optional[Decimal] = None
    ce15_override: Optional[Decimal] = None
    ce16_override: Optional[Decimal] = None
    ce17_override: Optional[Decimal] = None
    ce18_override: Optional[Decimal] = None
    ce19_override: Optional[Decimal] = None

    # CE overrides for direct forecast editing (None = use engine calculation)
    ce01_override: Optional[Decimal] = None
    ce04_override: Optional[Decimal] = None
    ce05_override: Optional[Decimal] = None
    ce06_override: Optional[Decimal] = None
    ce07_override: Optional[Decimal] = None
    ce08_override: Optional[Decimal] = None
    ce08a_override: Optional[Decimal] = None
    ce08b_override: Optional[Decimal] = None
    ce08c_override: Optional[Decimal] = None
    ce08d_override: Optional[Decimal] = None
    ce09_override: Optional[Decimal] = None
    ce09a_override: Optional[Decimal] = None
    ce09b_override: Optional[Decimal] = None
    ce09c_override: Optional[Decimal] = None
    ce09d_override: Optional[Decimal] = None
    ce11b_override: Optional[Decimal] = None
    ce12_override: Optional[Decimal] = None
    ce17a_override: Optional[Decimal] = None
    ce17b_override: Optional[Decimal] = None
    ce20_override: Optional[Decimal] = None


class BudgetAssumptionsCreate(BudgetAssumptionsBase):
    """Schema for creating new BudgetAssumptions"""
    pass


class BudgetAssumptionsBulkRow(BudgetAssumptionsBase):
    """Una riga del bulk `PUT /assumptions`: gli stessi vincoli di `BudgetAssumptionsCreate`, senza `scenario_id` obbligatorio
    (lo scenario e' nel percorso). Serve SOLO a validare: le righe si costruiscono ancora da `build_assumption_row`,
    cosi' un input valido produce esattamente le righe di prima. `extra="forbid"` SOLO qui (non su
    `BudgetAssumptionsBase`/`BudgetAssumptionsCreate`, entrambe usate altrove): un campo sconosciuto
    nel corpo del bulk oggi viene accettato e scartato in silenzio da pydantic (default
    `extra="ignore"`) -- un refuso o un campo rinominato lato frontend non arriva mai a un errore,
    sparisce e basta. `BudgetAssumptionsBulkRow` e' l'unica classe che questo file istanzia da un
    dict di client (`validate_bulk_rows`, unico chiamante); nessun altro schema del bulk cambia."""
    model_config = ConfigDict(extra="forbid")
    scenario_id: Optional[int] = None


class BudgetAssumptionsUpdate(BaseModel):
    """Schema for updating BudgetAssumptions"""
    forecast_year: Optional[int] = Field(None, ge=2000, le=2100)
    explicitly_supplied_fields: Optional[List[str]] = None
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
    intangible_investments: Optional[Decimal] = None
    tangible_investments: Optional[Decimal] = None
    asset_disposal_nbv: Optional[Decimal] = None
    asset_disposal_proceeds: Optional[Decimal] = None
    receivables_short_growth_pct: Optional[Decimal] = None
    receivables_long_growth_pct: Optional[Decimal] = None
    payables_short_growth_pct: Optional[Decimal] = None
    dso_days: Optional[Decimal] = None
    dio_days: Optional[Decimal] = None
    dpo_days: Optional[Decimal] = None
    existing_debt_repayment_years: Optional[Decimal] = None
    altri_finanz_repayment_years: Optional[Decimal] = None
    cash_sweep_enabled: Optional[bool] = None
    cash_sweep_min_cash: Optional[Decimal] = None
    overdraft_allowed: Optional[bool] = None
    overdraft_limit: Optional[Decimal] = Field(None, ge=0)
    tfr_accrual_suspended: Optional[bool] = None
    previdenza_scales_with_personnel: Optional[bool] = None
    interest_rate_receivables: Optional[Decimal] = None
    interest_rate_payables: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    tax_advances_paid: Optional[Decimal] = Field(None, ge=0)
    tax_temporary_differences: Optional[List[TemporaryDifferenceInput]] = None
    fixed_materials_percentage: Optional[Decimal] = None
    fixed_services_percentage: Optional[Decimal] = None
    depreciation_rate: Optional[Decimal] = None
    depreciation_rate_intangible: Optional[Decimal] = None
    financing_amount: Optional[Decimal] = None
    financing_duration_years: Optional[Decimal] = None
    financing_interest_rate: Optional[Decimal] = None
    financing_loans: Optional[List[FinancingLoanInput]] = None

    # Scadenziamento del pregresso
    pregresso: Optional[PregressoInput] = None

    # Indicizzazione delle voci minori dello SP a un driver di volume (Task 15).
    # Chiave assente = costante, cioe' il comportamento di sempre.
    sp_indexing: Optional[Dict[str, SpIndexingDriver]] = None

    # SP line item growth % overrides
    sp01_growth_pct: Optional[Decimal] = None
    sp04_growth_pct: Optional[Decimal] = None
    sp06e_growth_pct: Optional[Decimal] = None
    sp06f_growth_pct: Optional[Decimal] = None
    sp08_growth_pct: Optional[Decimal] = None
    sp10_growth_pct: Optional[Decimal] = None
    sp14_growth_pct: Optional[Decimal] = None
    sp16e_growth_pct: Optional[Decimal] = None
    sp16f_growth_pct: Optional[Decimal] = None
    sp16g_growth_pct: Optional[Decimal] = None
    sp17d_growth_pct: Optional[Decimal] = None
    sp17e_growth_pct: Optional[Decimal] = None
    sp17f_growth_pct: Optional[Decimal] = None
    sp17g_growth_pct: Optional[Decimal] = None
    sp18_growth_pct: Optional[Decimal] = None
    sp_overrides: Optional[Dict[str, Decimal]] = None

    # CE line item overrides
    ce02_override: Optional[Decimal] = None
    ce03_override: Optional[Decimal] = None
    ce03a_override: Optional[Decimal] = None
    ce10_override: Optional[Decimal] = None
    ce11_override: Optional[Decimal] = None
    ce13_override: Optional[Decimal] = None
    ce14_override: Optional[Decimal] = None
    ce15_override: Optional[Decimal] = None
    ce16_override: Optional[Decimal] = None
    ce17_override: Optional[Decimal] = None
    ce18_override: Optional[Decimal] = None
    ce19_override: Optional[Decimal] = None

    # CE overrides for direct forecast editing
    ce01_override: Optional[Decimal] = None
    ce04_override: Optional[Decimal] = None
    ce05_override: Optional[Decimal] = None
    ce06_override: Optional[Decimal] = None
    ce07_override: Optional[Decimal] = None
    ce08_override: Optional[Decimal] = None
    ce08a_override: Optional[Decimal] = None
    ce08b_override: Optional[Decimal] = None
    ce08c_override: Optional[Decimal] = None
    ce08d_override: Optional[Decimal] = None
    ce09_override: Optional[Decimal] = None
    ce09a_override: Optional[Decimal] = None
    ce09b_override: Optional[Decimal] = None
    ce09c_override: Optional[Decimal] = None
    ce09d_override: Optional[Decimal] = None
    ce11b_override: Optional[Decimal] = None
    ce12_override: Optional[Decimal] = None
    ce17a_override: Optional[Decimal] = None
    ce17b_override: Optional[Decimal] = None
    ce20_override: Optional[Decimal] = None

    @field_validator("explicitly_supplied_fields")
    @classmethod
    def validate_explicitly_supplied_fields(cls, value):
        return _validate_explicitly_supplied_fields(value)


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
    prior_value: float = 0.0
    pct_of_reference: float
    annualized_value: float


class IntraYearComparison(BaseModel):
    """Complete comparison between partial year and reference full year"""
    partial_year: int
    reference_year: int
    prior_year: Optional[int] = None
    has_reference: bool = True
    period_months: int
    income_items: List[IntraYearComparisonItem]
    balance_items: List[IntraYearComparisonItem]


# Override Request Schemas
class SpOverrideEntry(BaseModel):
    """One cell edit of SP Prev.: `{forecast_year, field, value}`.

    `value` is a Decimal so that a non-numeric body is refused HERE, by
    Pydantic (422), and never reaches the engine, where
    `Decimal(str(raw_value))` raises `decimal.InvalidOperation` -- an
    `ArithmeticError`, not a `ValueError`, which the route could only report
    as a 500 (final review of the lotto 2, M2). NaN and infinities are
    refused too: either would silently poison every projected line.
    `value: null` means "clear this key", same as before.
    """
    forecast_year: int
    field: str
    value: Optional[Decimal] = Field(default=None, allow_inf_nan=False)


class SpOverrideRequest(BaseModel):
    """Body of `PATCH /companies/{id}/scenarios/{id}/sp-override`."""
    overrides: List[SpOverrideEntry]
