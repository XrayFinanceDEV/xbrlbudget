# Simplified API Implementation Plan

**Project:** XBRL Budget - Backend API Simplification
**Date:** 2026-02-03
**Goal:** Reduce API complexity from 25+ endpoints to 7 core endpoints following INPUT → ASSUMPTIONS → OUTPUT workflow

---

## Executive Summary

The current backend has grown organically with many granular endpoints for individual calculations and data retrieval. This complexity makes the frontend harder to maintain and results in multiple API calls for simple workflows.

**The new design consolidates the API into 3 logical phases:**
1. **INPUT**: Upload financial data (XBRL/PDF/CSV)
2. **ASSUMPTIONS**: Create forecast scenario with growth assumptions
3. **OUTPUT**: Get complete analysis (historical + forecast + all calculations)

**Impact:**
- Frontend: Simplified from ~15+ API calls to 3 calls per workflow
- Backend: Consolidate calculation logic into unified service methods
- Performance: Single comprehensive response instead of multiple round trips
- Maintenance: Easier to understand and modify

---

## Current State Analysis

### Existing Endpoints (25+ total)

#### imports.py (3 endpoints) ✓ KEEP AS-IS
```
POST /api/v1/import/xbrl           → Upload XBRL file
POST /api/v1/import/pdf            → Upload PDF balance sheet
POST /api/v1/import/csv            → Upload CSV data (TEBE format)
```

#### budget_scenarios.py (15 endpoints) ❌ SIMPLIFY
```
# Scenario CRUD
GET    /companies/{id}/scenarios                          → List scenarios
GET    /companies/{id}/scenarios/{sid}                    → Get single scenario
POST   /companies/{id}/scenarios                          → Create scenario
PUT    /companies/{id}/scenarios/{sid}                    → Update scenario
DELETE /companies/{id}/scenarios/{sid}                    → Delete scenario

# Assumptions CRUD (per year)
GET    /companies/{id}/scenarios/{sid}/assumptions        → List all assumptions
POST   /companies/{id}/scenarios/{sid}/assumptions        → Create for one year
PUT    /companies/{id}/scenarios/{sid}/assumptions/{year} → Update one year
DELETE /companies/{id}/scenarios/{sid}/assumptions/{year} → Delete one year

# Forecast generation
POST   /companies/{id}/scenarios/{sid}/generate           → Generate forecasts

# Forecast data retrieval
GET    /companies/{id}/scenarios/{sid}/forecasts          → List forecast years
GET    /companies/{id}/scenarios/{sid}/forecasts/{year}/balance-sheet
GET    /companies/{id}/scenarios/{sid}/forecasts/{year}/income-statement
GET    /companies/{id}/scenarios/{sid}/reclassified       → Historical + forecast reclassified
GET    /companies/{id}/scenarios/{sid}/detailed-cashflow  → Cashflow with forecast
GET    /companies/{id}/scenarios/{sid}/ratios             → Ratios with forecast
```

#### calculations.py (10 endpoints) ❌ CONSOLIDATE
```
# Individual calculations (historical only)
GET /companies/{id}/years/{year}/calculations/ratios       → All ratios
GET /companies/{id}/years/{year}/calculations/summary      → Summary metrics
GET /companies/{id}/years/{year}/calculations/altman       → Altman Z-Score
GET /companies/{id}/years/{year}/calculations/fgpmi        → FGPMI rating
GET /companies/{id}/years/{year}/calculations/complete     → All calculations
GET /companies/{id}/years/{year}/calculations/cashflow     → Single year cashflow

# Individual ratio categories
GET /companies/{id}/years/{year}/calculations/ratios/liquidity
GET /companies/{id}/years/{year}/calculations/ratios/profitability
GET /companies/{id}/years/{year}/calculations/ratios/solvency

# Multi-year cashflow
GET /companies/{id}/calculations/cashflow                  → All years
```

#### companies.py + financial_years.py (CRUD) ✓ KEEP MINIMAL
```
GET    /companies                   → List companies
GET    /companies/{id}              → Get company
POST   /companies                   → Create company
PUT    /companies/{id}              → Update company
DELETE /companies/{id}              → Delete company

GET    /companies/{id}/years        → List financial years
GET    /companies/{id}/years/{year} → Get financial year
DELETE /companies/{id}/years/{year} → Delete financial year
```

### Problems with Current Design

1. **Too many round trips**: Frontend needs 10+ API calls to display forecast analysis page
2. **Inconsistent patterns**: Some endpoints return historical, some forecast, some both
3. **Duplicated logic**: Calculations repeated across multiple endpoints
4. **Complex state management**: Frontend must coordinate multiple async calls
5. **Poor performance**: Network latency multiplied by number of calls
6. **Hard to maintain**: Changes require updating multiple endpoints and frontend code

---

## Proposed Simplified API

### Design Principles

1. **Workflow-driven**: API matches user workflow (INPUT → ASSUMPTIONS → OUTPUT)
2. **One call per phase**: Each workflow phase = one API call
3. **Complete responses**: Each endpoint returns ALL data needed for that phase
4. **Backward compatibility**: Keep existing endpoints during transition period
5. **Clear naming**: Endpoint names describe what you get, not implementation details

### New API Structure (7 core endpoints)

#### Phase 1: INPUT (3 endpoints) ✓ NO CHANGES
```
POST /api/v1/import/xbrl
POST /api/v1/import/pdf
POST /api/v1/import/csv
```

**Status:** Already implemented correctly. No changes needed.

---

#### Phase 2: ASSUMPTIONS (2 endpoints) 🔄 SIMPLIFIED

**2.1 Create Scenario**
```
POST /api/v1/companies/{company_id}/scenarios

Request:
{
  "name": "Budget 2025-2027",
  "base_year": 2024,
  "projection_years": 3,  // or 5
  "is_active": 1
}

Response:
{
  "id": 1,
  "company_id": 123,
  "name": "Budget 2025-2027",
  "base_year": 2024,
  "projection_years": 3,
  "is_active": 1,
  "created_at": "2026-02-03T10:00:00Z",
  "updated_at": "2026-02-03T10:00:00Z"
}
```

**2.2 Set Assumptions (Bulk Upsert)**
```
PUT /api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions

Request:
{
  "assumptions": [
    {
      "forecast_year": 2025,
      "revenue_growth_pct": 5.0,
      "material_cost_growth_pct": 3.0,
      "service_cost_growth_pct": 2.5,
      "personnel_cost_growth_pct": 2.0,
      "capex_tangible": 50000.00,
      "capex_intangible": 10000.00,
      "new_debt": 0.00,
      "dividend_payout_pct": 0.0
    },
    {
      "forecast_year": 2026,
      "revenue_growth_pct": 4.0,
      // ... same fields
    },
    {
      "forecast_year": 2027,
      "revenue_growth_pct": 3.5,
      // ... same fields
    }
  ],
  "auto_generate": true  // Automatically generate forecast after saving
}

Response:
{
  "success": true,
  "scenario_id": 1,
  "assumptions_saved": 3,
  "forecast_generated": true,
  "forecast_years": [2025, 2026, 2027],
  "message": "Assumptions saved and forecast generated successfully"
}
```

**Changes from current design:**
- ❌ Remove individual year endpoints (POST/PUT/DELETE per year)
- ✅ Bulk upsert all years at once
- ✅ Automatically trigger forecast generation (no separate call needed)
- ✅ Simpler frontend: one form, one save button, one API call

---

#### Phase 3: OUTPUT (1 endpoint) ⭐ NEW COMPREHENSIVE

**3.1 Complete Analysis**
```
GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/analysis

Query params (optional):
  - include_historical: bool = true   // Include historical years
  - include_forecast: bool = true     // Include forecast years
  - include_calculations: bool = true // Include Altman, FGPMI, ratios, cashflow

Response:
{
  "scenario": {
    "id": 1,
    "name": "Budget 2025-2027",
    "base_year": 2024,
    "projection_years": 3,
    "company": {
      "id": 123,
      "name": "Acme Corporation",
      "tax_id": "IT12345678901",
      "sector": 1
    }
  },

  "historical_years": [
    {
      "year": 2023,
      "balance_sheet": {
        // All sp01-sp18 fields
        "sp01_crediti_soci": 0.00,
        "sp02_immob_immateriali": 15000.00,
        // ... all 18 fields
        "total_assets": 1000000.00,
        "total_equity": 300000.00,
        "total_debt": 700000.00,
        "fixed_assets": 500000.00,
        "current_assets": 500000.00,
        "current_liabilities": 200000.00,
        "working_capital_net": 300000.00
      },
      "income_statement": {
        // All ce01-ce20 fields
        "ce01_ricavi_vendite": 800000.00,
        "ce02_var_rimanenze": 5000.00,
        // ... all 20 fields
        "revenue": 800000.00,
        "production_value": 810000.00,
        "production_cost": 700000.00,
        "ebitda": 110000.00,
        "ebit": 95000.00,
        "net_profit": 45000.00
      }
    },
    {
      "year": 2024,
      // ... same structure
    }
  ],

  "forecast_years": [
    {
      "year": 2025,
      "assumptions": {
        "revenue_growth_pct": 5.0,
        "material_cost_growth_pct": 3.0,
        // ... all assumptions
      },
      "balance_sheet": {
        // Same structure as historical
      },
      "income_statement": {
        // Same structure as historical
      }
    },
    {
      "year": 2026,
      // ... same structure
    },
    {
      "year": 2027,
      // ... same structure
    }
  ],

  "calculations": {
    "by_year": {
      "2023": {
        "altman": {
          "z_score": 2.85,
          "classification": "gray_zone",
          "component_a": 0.35,
          "component_b": 0.45,
          "component_c": 0.95,
          "component_d": 0.60,
          "component_e": 0.50,
          "interpretation": "Zona grigia - monitorare"
        },
        "fgpmi": {
          "total_score": 65,
          "max_score": 100,
          "rating_class": 5,
          "rating_code": "BB+",
          "rating_description": "Buono",
          "risk_level": "Medio",
          "revenue_bonus": 2,
          "indicators": {
            "v1_patrimonio_vendite": { "value": 0.35, "score": 8, "max": 12 },
            // ... v2-v7
          }
        },
        "ratios": {
          "working_capital": {
            "ccln": 300000.00,
            "ccn": 300000.00,
            "margine_struttura": 200000.00,
            "margine_tesoreria": 100000.00
          },
          "liquidity": {
            "current_ratio": 2.5,
            "quick_ratio": 1.8,
            "acid_test_ratio": 1.2
          },
          "solvency": {
            "autonomy_index": 30.0,
            "leverage_ratio": 2.33,
            "debt_to_equity": 2.33,
            "debt_to_prod_value": 0.86
          },
          "profitability": {
            "roe": 15.0,
            "roi": 9.5,
            "ros": 11.9,
            "rod": 5.0,
            "ebitda_margin": 13.8,
            "ebit_margin": 11.9,
            "net_margin": 5.6
          },
          "activity": {
            "asset_turnover": 0.80,
            "receivables_turnover": 8.0,
            "inventory_turnover": 12.0,
            "payables_turnover": 6.0,
            "receivables_days": 45,
            "inventory_days": 30,
            "payables_days": 60,
            "cash_conversion_cycle": 15
          }
        }
      },
      "2024": { /* ... same structure ... */ },
      "2025": { /* ... same structure ... */ },
      "2026": { /* ... same structure ... */ },
      "2027": { /* ... same structure ... */ }
    },

    "cashflow": {
      "years": [
        {
          "year": 2024,
          "base_year": 2023,
          "operating": {
            "net_profit": 50000.00,
            "depreciation": 15000.00,
            "provisions_change": 2000.00,
            "tfr_change": 3000.00,
            "working_capital_change": -20000.00,
            "other_adjustments": 1000.00,
            "total": 51000.00
          },
          "investing": {
            "capex_tangible": -30000.00,
            "capex_intangible": -5000.00,
            "capex_financial": 0.00,
            "divestments": 0.00,
            "total": -35000.00
          },
          "financing": {
            "debt_change": 10000.00,
            "equity_change": 0.00,
            "dividends": -5000.00,
            "total": 5000.00
          },
          "net_cashflow": 21000.00,
          "cash_beginning": 80000.00,
          "cash_ending": 101000.00,
          "verification": {
            "calculated_change": 21000.00,
            "actual_change": 21000.00,
            "difference": 0.00,
            "balanced": true
          },
          "ratios": {
            "ocf_margin": 6.4,
            "free_cashflow": 16000.00,
            "cash_conversion": 102.0,
            "capex_to_revenue": 4.4
          }
        },
        // ... 2025, 2026, 2027 (forecast)
      ]
    }
  }
}
```

**This ONE endpoint replaces:**
- ❌ `/scenarios/{id}/reclassified`
- ❌ `/scenarios/{id}/detailed-cashflow`
- ❌ `/scenarios/{id}/ratios`
- ❌ `/years/{year}/calculations/altman`
- ❌ `/years/{year}/calculations/fgpmi`
- ❌ `/years/{year}/calculations/ratios`
- ❌ `/years/{year}/calculations/complete`
- ❌ `/forecasts/{year}/balance-sheet`
- ❌ `/forecasts/{year}/income-statement`

---

#### Phase 4: MANAGEMENT (2 endpoints) ✓ KEEP MINIMAL

```
GET    /api/v1/companies                              → List all companies
GET    /api/v1/companies/{id}/scenarios               → List scenarios for company
DELETE /api/v1/companies/{id}/scenarios/{scenario_id} → Delete scenario
```

Optional (for future):
```
GET    /api/v1/companies/{id}                         → Get company details
GET    /api/v1/companies/{id}/years                   → List financial years
```

---

## Implementation Plan

### Phase 1: Preparation (No breaking changes)

**1.1 Create new service layer**
- File: `backend/app/services/analysis_service.py`
- Method: `get_complete_analysis(db, company_id, scenario_id, options)`
- Consolidates logic from:
  - `calculation_service.calculate_all_ratios()`
  - `calculation_service.calculate_altman_zscore()`
  - `calculation_service.calculate_fgpmi_rating()`
  - `calculation_service.calculate_detailed_cashflow_*()`
  - Budget scenario data retrieval

**1.2 Create comprehensive response schemas**
- File: `backend/app/schemas/analysis.py`
- Schemas:
  - `CompleteAnalysisResponse` (top-level)
  - `HistoricalYearData` (one historical year)
  - `ForecastYearData` (one forecast year)
  - `YearCalculations` (Altman, FGPMI, ratios for one year)
  - `CashflowAnalysis` (multi-year cashflow)

**1.3 Update assumptions handling**
- File: `backend/app/services/assumptions_service.py`
- Method: `bulk_upsert_assumptions(db, scenario_id, assumptions_list, auto_generate)`
- Logic:
  1. Validate all assumptions
  2. Delete existing assumptions for scenario
  3. Insert new assumptions (bulk)
  4. If `auto_generate=true`, call `ForecastEngine.generate_forecast()`
  5. Return summary

### Phase 2: Add New Endpoints (Parallel to existing)

**2.1 Add new assumption endpoint**
- File: `backend/app/api/v1/budget_scenarios.py`
- Endpoint: `PUT /companies/{id}/scenarios/{sid}/assumptions` (bulk)
- Keep old endpoints for now (backward compatibility)

**2.2 Add comprehensive analysis endpoint**
- File: `backend/app/api/v1/analysis.py` (NEW FILE)
- Endpoint: `GET /companies/{id}/scenarios/{sid}/analysis`
- Router tag: `["analysis"]`

**2.3 Update main.py**
```python
from app.api.v1 import analysis
app.include_router(analysis.router, prefix=settings.API_V1_PREFIX, tags=["analysis"])
```

### Phase 3: Update Frontend

**3.1 Update API client**
- File: `frontend/lib/api.ts`
- Add new methods:
  - `bulkUpsertAssumptions(companyId, scenarioId, assumptions)`
  - `getCompleteAnalysis(companyId, scenarioId, options)`

**3.2 Update TypeScript types**
- File: `frontend/types/api.ts`
- Add interfaces matching new response schemas

**3.3 Update pages to use new endpoints**
- `frontend/app/budget/page.tsx` → Use bulk assumptions endpoint
- `frontend/app/forecast/income/page.tsx` → Use complete analysis endpoint
- `frontend/app/forecast/balance/page.tsx` → Use complete analysis endpoint
- `frontend/app/forecast/reclassified/page.tsx` → Use complete analysis endpoint
- `frontend/app/analysis/page.tsx` → Use complete analysis endpoint
- `frontend/app/cashflow/page.tsx` → Use complete analysis endpoint

**3.4 Simplify state management**
- Context can cache one `completeAnalysis` response
- All pages read from same cached data
- Invalidate cache when assumptions change

### Phase 4: Deprecation and Cleanup

**4.1 Mark old endpoints as deprecated**
- Add `deprecated=True` to router decorators
- Add deprecation notice in docstrings
- Update OpenAPI docs with migration guide

**4.2 Monitor usage**
- Keep old endpoints for 1-2 months
- Log warnings when deprecated endpoints are called
- Track usage metrics

**4.3 Remove deprecated endpoints**
- After frontend fully migrated and tested
- Delete deprecated endpoint functions
- Clean up unused service methods
- Update documentation

---

## File Structure Changes

### New Files
```
backend/app/
├── api/v1/
│   └── analysis.py                 # NEW: Comprehensive analysis endpoint
├── services/
│   ├── analysis_service.py         # NEW: Complete analysis logic
│   └── assumptions_service.py      # NEW: Bulk assumptions handling
└── schemas/
    └── analysis.py                  # NEW: Complete analysis response schemas
```

### Modified Files
```
backend/app/
├── api/v1/
│   ├── budget_scenarios.py         # MODIFY: Add bulk assumptions endpoint
│   ├── calculations.py             # MODIFY: Mark endpoints as deprecated
│   └── __init__.py                 # MODIFY: Export new router
├── services/
│   └── calculation_service.py      # REFACTOR: Extract reusable logic
└── main.py                          # MODIFY: Include new analysis router

frontend/
├── lib/
│   └── api.ts                       # MODIFY: Add new API methods
├── types/
│   └── api.ts                       # MODIFY: Add new interfaces
└── app/
    ├── budget/page.tsx              # MODIFY: Use bulk assumptions
    ├── forecast/income/page.tsx     # MODIFY: Use complete analysis
    ├── forecast/balance/page.tsx    # MODIFY: Use complete analysis
    ├── forecast/reclassified/page.tsx # MODIFY: Use complete analysis
    ├── analysis/page.tsx            # MODIFY: Use complete analysis
    └── cashflow/page.tsx            # MODIFY: Use complete analysis
```

### Files to Delete (Phase 4)
```
backend/app/api/v1/
└── calculations.py                  # DELETE: After migration complete

# Functions to remove from budget_scenarios.py:
- get_forecast_balance_sheet()
- get_forecast_income_statement()
- get_forecast_reclassified_data()
- get_detailed_cashflow_scenario()
- get_ratios_scenario()
- Individual assumptions CRUD (POST/PUT/DELETE per year)
```

---

## Testing Strategy

### Unit Tests

**1. Service Layer Tests**
```python
# tests/services/test_analysis_service.py
def test_get_complete_analysis_historical_only()
def test_get_complete_analysis_with_forecast()
def test_get_complete_analysis_all_calculations()
def test_get_complete_analysis_missing_data()
def test_get_complete_analysis_invalid_scenario()

# tests/services/test_assumptions_service.py
def test_bulk_upsert_assumptions_new()
def test_bulk_upsert_assumptions_update_existing()
def test_bulk_upsert_assumptions_with_auto_generate()
def test_bulk_upsert_assumptions_validation_error()
def test_bulk_upsert_assumptions_invalid_years()
```

**2. API Endpoint Tests**
```python
# tests/api/test_analysis_endpoints.py
def test_get_complete_analysis_success()
def test_get_complete_analysis_with_query_params()
def test_get_complete_analysis_scenario_not_found()
def test_get_complete_analysis_no_forecast_data()
def test_get_complete_analysis_response_schema()

# tests/api/test_assumptions_endpoints.py
def test_bulk_upsert_assumptions_success()
def test_bulk_upsert_assumptions_auto_generate()
def test_bulk_upsert_assumptions_validation_error()
def test_bulk_upsert_assumptions_duplicate_years()
```

### Integration Tests

**1. End-to-End Workflow**
```python
def test_complete_workflow():
    # 1. Upload XBRL
    response = client.post("/api/v1/import/xbrl", files={"file": xbrl_file})
    company_id = response.json()["company_id"]

    # 2. Create scenario
    scenario = client.post(f"/api/v1/companies/{company_id}/scenarios", json={
        "name": "Test Budget",
        "base_year": 2024,
        "projection_years": 3
    })
    scenario_id = scenario.json()["id"]

    # 3. Set assumptions
    assumptions = client.put(
        f"/api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions",
        json={"assumptions": [...], "auto_generate": True}
    )
    assert assumptions.json()["forecast_generated"] == True

    # 4. Get complete analysis
    analysis = client.get(
        f"/api/v1/companies/{company_id}/scenarios/{scenario_id}/analysis"
    )
    assert "historical_years" in analysis.json()
    assert "forecast_years" in analysis.json()
    assert "calculations" in analysis.json()
```

**2. Performance Tests**
```python
def test_complete_analysis_performance():
    # Measure response time for complete analysis
    # Target: < 2 seconds for 2 historical + 5 forecast years
    start = time.time()
    response = client.get(f"/api/v1/companies/{company_id}/scenarios/{scenario_id}/analysis")
    elapsed = time.time() - start
    assert elapsed < 2.0
    assert response.status_code == 200
```

### Manual Testing Checklist

- [ ] Upload XBRL file via POST /import/xbrl
- [ ] Create scenario via POST /companies/{id}/scenarios
- [ ] Set 3-year assumptions via PUT /scenarios/{id}/assumptions with auto_generate=true
- [ ] Verify forecast generated successfully
- [ ] Get complete analysis via GET /scenarios/{id}/analysis
- [ ] Verify response contains all expected data
- [ ] Test with 5-year projection
- [ ] Test update assumptions (modify and re-save)
- [ ] Verify forecast regenerated automatically
- [ ] Test with missing historical data
- [ ] Test with invalid scenario ID
- [ ] Test Swagger UI documentation
- [ ] Test frontend integration (all pages)

---

## Performance Considerations

### Database Optimization

**1. Eager Loading**
```python
# Load all related data in one query
scenario = db.query(BudgetScenario)\
    .options(
        joinedload(BudgetScenario.company),
        joinedload(BudgetScenario.assumptions),
        joinedload(BudgetScenario.forecast_years).joinedload(ForecastYear.balance_sheet),
        joinedload(BudgetScenario.forecast_years).joinedload(ForecastYear.income_statement)
    )\
    .filter(BudgetScenario.id == scenario_id)\
    .first()
```

**2. Query Historical Years Efficiently**
```python
# Get only needed years (base_year and base_year - 1)
historical_years = db.query(FinancialYear)\
    .options(
        joinedload(FinancialYear.balance_sheet),
        joinedload(FinancialYear.income_statement)
    )\
    .filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year >= base_year - 1,
        FinancialYear.year <= base_year
    )\
    .order_by(FinancialYear.year)\
    .all()
```

**3. Batch Calculations**
- Calculate all ratios for all years in one pass
- Reuse calculator instances where possible
- Cache intermediate results (e.g., working capital used in multiple ratios)

### Response Size Optimization

**1. Optional Data Inclusion**
```python
# Allow clients to request only what they need
?include_historical=true
?include_forecast=true
?include_calculations=true
?calculation_types=altman,fgpmi  # Skip ratios/cashflow if not needed
```

**2. Field Selection** (future enhancement)
```python
# Allow clients to request specific fields
?fields=balance_sheet.total_assets,income_statement.revenue
```

### Caching Strategy

**1. Server-side (optional)**
```python
# Cache complete analysis response for 5 minutes
# Invalidate on assumptions update or forecast regeneration
@lru_cache(maxsize=100)
def get_complete_analysis_cached(company_id, scenario_id, options_hash):
    return get_complete_analysis(db, company_id, scenario_id, options)
```

**2. Client-side (frontend)**
```typescript
// Cache in React Context or TanStack Query
const { data, isLoading } = useQuery({
  queryKey: ['analysis', companyId, scenarioId],
  queryFn: () => api.getCompleteAnalysis(companyId, scenarioId),
  staleTime: 5 * 60 * 1000, // 5 minutes
  cacheTime: 30 * 60 * 1000  // 30 minutes
})
```

---

## Migration Guide (for Frontend Developers)

### Before (Old API - Multiple Calls)

```typescript
// Budget page: Get assumptions for each year
const assumptions2025 = await api.getAssumptions(companyId, scenarioId, 2025)
const assumptions2026 = await api.getAssumptions(companyId, scenarioId, 2026)
const assumptions2027 = await api.getAssumptions(companyId, scenarioId, 2027)

// Save each year separately
await api.updateAssumptions(companyId, scenarioId, 2025, data2025)
await api.updateAssumptions(companyId, scenarioId, 2026, data2026)
await api.updateAssumptions(companyId, scenarioId, 2027, data2027)

// Generate forecast
await api.generateForecasts(companyId, scenarioId)

// Analysis page: Get all calculations
const ratios = await api.getRatios(companyId, scenarioId)
const altman = await api.getAltman(companyId, scenarioId)
const fgpmi = await api.getFGPMI(companyId, scenarioId)
const cashflow = await api.getCashflow(companyId, scenarioId)

// Forecast pages: Get financial statements
const forecastCE = await api.getForecastIncomeStatement(companyId, scenarioId, year)
const forecastSP = await api.getForecastBalanceSheet(companyId, scenarioId, year)
const historicalCE = await api.getIncomeStatement(companyId, year)
const historicalSP = await api.getBalanceSheet(companyId, year)
```

**Problems:**
- 15+ API calls for one workflow
- Complex error handling (what if call #7 fails?)
- Loading states hard to manage
- Race conditions possible
- Network latency multiplied

### After (New API - 3 Calls)

```typescript
// Budget page: Save all assumptions at once
await api.bulkUpsertAssumptions(companyId, scenarioId, {
  assumptions: [
    { forecast_year: 2025, revenue_growth_pct: 5.0, /* ... */ },
    { forecast_year: 2026, revenue_growth_pct: 4.0, /* ... */ },
    { forecast_year: 2027, revenue_growth_pct: 3.5, /* ... */ }
  ],
  auto_generate: true  // Forecast generated automatically
})

// All other pages: Get everything in one call
const analysis = await api.getCompleteAnalysis(companyId, scenarioId)

// Everything is available:
analysis.historical_years[0].balance_sheet  // 2023 SP
analysis.historical_years[1].income_statement  // 2024 CE
analysis.forecast_years[0].balance_sheet  // 2025 SP forecast
analysis.forecast_years[0].income_statement  // 2025 CE forecast
analysis.calculations.by_year[2024].altman  // Altman for 2024
analysis.calculations.by_year[2025].fgpmi  // FGPMI for 2025
analysis.calculations.by_year[2026].ratios  // All ratios for 2026
analysis.calculations.cashflow.years[1]  // Cashflow for 2025
```

**Benefits:**
- 3 API calls total (vs 15+)
- One loading state
- One error handler
- All data available together
- Consistent structure
- Cache once, use everywhere

---

## Backward Compatibility Strategy

### Transition Period (1-2 months)

**Keep both old and new endpoints:**
- Old endpoints marked as `deprecated=True`
- Documentation updated with migration guide
- Warning logs when old endpoints called
- Metrics tracking old endpoint usage

### Deprecation Notices

```python
@router.get(
    "/companies/{company_id}/years/{year}/calculations/altman",
    deprecated=True,
    response_model=calc_schemas.AltmanResult,
    summary="[DEPRECATED] Calculate Altman Z-Score"
)
def get_altman_zscore(
    company_id: int,
    year: int,
    db: Session = Depends(get_db)
):
    """
    **⚠️ DEPRECATED**: This endpoint will be removed in v2.0.

    Please use GET /companies/{id}/scenarios/{sid}/analysis instead.

    Migration guide: See /docs/api-migration.md
    """
    logger.warning(f"Deprecated endpoint called: /calculations/altman by {request.client}")
    # ... existing implementation
```

### Frontend Feature Flags

```typescript
// config.ts
export const USE_NEW_API = process.env.NEXT_PUBLIC_USE_NEW_API === 'true'

// api.ts
export const getAnalysisData = USE_NEW_API
  ? getCompleteAnalysis
  : getAnalysisDataOld
```

---

## Success Metrics

### Performance Metrics
- **API calls per workflow**: 15+ → 3 (80% reduction)
- **Response time**: < 2 seconds for complete analysis
- **Data transfer**: Comparable or smaller (one large response vs many small)
- **Frontend render time**: Faster (data available immediately)

### Developer Experience Metrics
- **Lines of code**: Reduce frontend API integration code by ~60%
- **Bug reports**: Fewer state management / loading state bugs
- **Development time**: Faster to add new features (one data source)
- **Onboarding time**: Simpler API = easier for new developers

### Code Quality Metrics
- **Test coverage**: Maintain > 80% coverage
- **Endpoint count**: 25+ → 7 (72% reduction)
- **Duplicated logic**: Eliminate calculation duplication
- **Documentation**: Clearer, more complete API docs

---

## Risk Assessment

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Performance degradation from large responses | High | Low | Add query params for optional data; implement pagination if needed |
| Breaking changes affect production | Critical | Low | Keep old endpoints during transition; feature flags |
| Database N+1 queries | Medium | Medium | Use eager loading; test with real data volume |
| Response serialization slow | Medium | Low | Profile and optimize; consider pagination |
| Cache invalidation bugs | Medium | Low | Clear cache on any data mutation; add timestamps |

### Business Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Frontend migration takes longer than expected | Medium | Medium | Parallel development; old endpoints available |
| Users confused by API changes | Low | Low | No user-facing changes (internal API only) |
| Bugs in consolidated logic | High | Low | Extensive testing; gradual rollout |

### Mitigation Strategy

1. **Phased rollout**: New endpoints alongside old
2. **Feature flags**: Enable new API per-environment
3. **Monitoring**: Track errors, performance, usage
4. **Rollback plan**: Keep old endpoints until 100% migrated
5. **Testing**: Comprehensive unit, integration, and E2E tests

---

## Timeline Estimate

### Week 1: Backend Implementation
- **Days 1-2**: Create service layer (analysis_service.py, assumptions_service.py)
- **Days 3-4**: Create response schemas (analysis.py)
- **Days 4-5**: Create new endpoints (analysis.py router, bulk assumptions)
- **Day 5**: Write unit tests

### Week 2: Frontend Migration
- **Days 1-2**: Update API client (api.ts, types)
- **Days 2-3**: Update Budget page (bulk assumptions)
- **Days 3-4**: Update Analysis, Forecast, Cashflow pages (complete analysis)
- **Day 5**: Integration testing

### Week 3: Testing & Polish
- **Days 1-2**: E2E testing, bug fixes
- **Days 3-4**: Performance optimization
- **Day 5**: Documentation updates

### Week 4: Deprecation & Cleanup
- **Days 1-2**: Mark old endpoints deprecated
- **Days 3-4**: Monitor usage, address issues
- **Day 5**: Final cleanup (optional - can wait 1-2 months)

**Total: 3-4 weeks for complete migration**

---

## Next Steps

1. **Review and approve this plan**
2. **Create feature branch**: `feature/simplified-api`
3. **Start with backend implementation** (Week 1 tasks)
4. **Test thoroughly with existing data**
5. **Migrate frontend page by page** (Week 2 tasks)
6. **Monitor and iterate** (Week 3-4 tasks)

---

## Open Questions

1. **Response size**: Should we add pagination or field selection for very large datasets?
2. **Caching**: Should we implement server-side caching for complete analysis?
3. **Versioning**: Should we version the API (v1, v2) or keep backward compatibility?
4. **Historical years**: Always return 2 years, or allow customization?
5. **Calculation options**: Allow clients to skip expensive calculations (e.g., skip cashflow)?
6. **Error handling**: How to handle partial failures (e.g., Altman fails but FGPMI succeeds)?
7. **Real-time updates**: Should assumptions auto-save, or require explicit save button?

---

## Appendix A: API Comparison Table

| Feature | Old API | New API | Improvement |
|---------|---------|---------|-------------|
| Upload XBRL | POST /import/xbrl | POST /import/xbrl | No change ✓ |
| Create scenario | POST /companies/{id}/scenarios | POST /companies/{id}/scenarios | No change ✓ |
| Set assumptions | 3× POST (per year) | 1× PUT (bulk) | **3 → 1 call** |
| Generate forecast | POST /generate | Automatic | **No extra call** |
| Get forecast CE | GET /forecasts/{year}/income-statement | GET /scenarios/{id}/analysis | **Included** |
| Get forecast SP | GET /forecasts/{year}/balance-sheet | GET /scenarios/{id}/analysis | **Included** |
| Get historical CE | GET /years/{year} | GET /scenarios/{id}/analysis | **Included** |
| Get historical SP | GET /years/{year} | GET /scenarios/{id}/analysis | **Included** |
| Get Altman | GET /calculations/altman | GET /scenarios/{id}/analysis | **Included** |
| Get FGPMI | GET /calculations/fgpmi | GET /scenarios/{id}/analysis | **Included** |
| Get ratios | GET /calculations/ratios | GET /scenarios/{id}/analysis | **Included** |
| Get cashflow | GET /detailed-cashflow | GET /scenarios/{id}/analysis | **Included** |
| **Total calls for full workflow** | **15+** | **3** | **80% reduction** |

---

## Appendix B: Code Examples

### Backend: Analysis Service

```python
# backend/app/services/analysis_service.py

from typing import Dict, List, Optional
from sqlalchemy.orm import Session, joinedload
from database.models import Company, BudgetScenario, FinancialYear, ForecastYear
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from calculations.rating_fgpmi import FGPMICalculator
from app.calculations.cashflow_detailed import DetailedCashFlowCalculator


def get_complete_analysis(
    db: Session,
    company_id: int,
    scenario_id: int,
    include_historical: bool = True,
    include_forecast: bool = True,
    include_calculations: bool = True
) -> Dict:
    """
    Get complete financial analysis for a scenario.

    Returns historical data, forecast data, and all calculations in one response.
    """
    # 1. Load scenario with all related data (eager loading)
    scenario = db.query(BudgetScenario)\
        .options(
            joinedload(BudgetScenario.company),
            joinedload(BudgetScenario.assumptions),
            joinedload(BudgetScenario.forecast_years).joinedload(ForecastYear.balance_sheet),
            joinedload(BudgetScenario.forecast_years).joinedload(ForecastYear.income_statement)
        )\
        .filter(
            BudgetScenario.id == scenario_id,
            BudgetScenario.company_id == company_id
        )\
        .first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found for company {company_id}")

    result = {
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "base_year": scenario.base_year,
            "projection_years": scenario.projection_years,
            "company": {
                "id": scenario.company.id,
                "name": scenario.company.name,
                "tax_id": scenario.company.tax_id,
                "sector": scenario.company.sector
            }
        }
    }

    # 2. Get historical years (base_year and base_year - 1)
    historical_years = []
    if include_historical:
        historical_data = db.query(FinancialYear)\
            .options(
                joinedload(FinancialYear.balance_sheet),
                joinedload(FinancialYear.income_statement)
            )\
            .filter(
                FinancialYear.company_id == company_id,
                FinancialYear.year >= scenario.base_year - 1,
                FinancialYear.year <= scenario.base_year
            )\
            .order_by(FinancialYear.year)\
            .all()

        for fy in historical_data:
            if fy.balance_sheet and fy.income_statement:
                historical_years.append({
                    "year": fy.year,
                    "balance_sheet": serialize_balance_sheet(fy.balance_sheet),
                    "income_statement": serialize_income_statement(fy.income_statement)
                })

    result["historical_years"] = historical_years

    # 3. Get forecast years
    forecast_years = []
    if include_forecast:
        for forecast_year in scenario.forecast_years:
            if forecast_year.balance_sheet and forecast_year.income_statement:
                # Get assumptions for this year
                assumptions = next(
                    (a for a in scenario.assumptions if a.forecast_year == forecast_year.year),
                    None
                )

                forecast_years.append({
                    "year": forecast_year.year,
                    "assumptions": serialize_assumptions(assumptions) if assumptions else None,
                    "balance_sheet": serialize_balance_sheet(forecast_year.balance_sheet),
                    "income_statement": serialize_income_statement(forecast_year.income_statement)
                })

    result["forecast_years"] = forecast_years

    # 4. Calculate all financial metrics for each year
    calculations = {"by_year": {}}
    if include_calculations:
        all_years = []

        # Add historical years
        for fy in historical_data:
            if fy.balance_sheet and fy.income_statement:
                all_years.append({
                    "year": fy.year,
                    "balance_sheet": fy.balance_sheet,
                    "income_statement": fy.income_statement,
                    "sector": scenario.company.sector
                })

        # Add forecast years
        for forecast_year in scenario.forecast_years:
            if forecast_year.balance_sheet and forecast_year.income_statement:
                all_years.append({
                    "year": forecast_year.year,
                    "balance_sheet": forecast_year.balance_sheet,
                    "income_statement": forecast_year.income_statement,
                    "sector": scenario.company.sector
                })

        # Calculate for each year
        for year_data in all_years:
            bs = year_data["balance_sheet"]
            inc = year_data["income_statement"]
            sector = year_data["sector"]

            # Calculate ratios
            ratios_calc = FinancialRatiosCalculator(bs, inc)
            wc = ratios_calc.calculate_working_capital_metrics()
            liquidity = ratios_calc.calculate_liquidity_ratios()
            solvency = ratios_calc.calculate_solvency_ratios()
            profitability = ratios_calc.calculate_profitability_ratios()
            activity = ratios_calc.calculate_activity_ratios()

            # Calculate Altman
            altman_calc = AltmanCalculator(bs, inc, sector)
            altman = altman_calc.calculate()

            # Calculate FGPMI
            fgpmi_calc = FGPMICalculator(bs, inc, sector)
            fgpmi = fgpmi_calc.calculate()

            calculations["by_year"][str(year_data["year"])] = {
                "altman": serialize_altman(altman),
                "fgpmi": serialize_fgpmi(fgpmi),
                "ratios": {
                    "working_capital": serialize_working_capital(wc),
                    "liquidity": serialize_liquidity(liquidity),
                    "solvency": serialize_solvency(solvency),
                    "profitability": serialize_profitability(profitability),
                    "activity": serialize_activity(activity)
                }
            }

        # Calculate cashflow (requires year-over-year comparisons)
        cashflow_years = []
        for i in range(1, len(all_years)):
            base_year_data = all_years[i - 1]
            current_year_data = all_years[i]

            cf_calc = DetailedCashFlowCalculator(
                base_bs=base_year_data["balance_sheet"],
                base_inc=base_year_data["income_statement"],
                current_bs=current_year_data["balance_sheet"],
                current_inc=current_year_data["income_statement"]
            )
            cf_result = cf_calc.calculate()

            cashflow_years.append({
                "year": current_year_data["year"],
                "base_year": base_year_data["year"],
                **serialize_cashflow(cf_result)
            })

        calculations["cashflow"] = {"years": cashflow_years}

    result["calculations"] = calculations

    return result


def serialize_balance_sheet(bs) -> Dict:
    """Serialize balance sheet to dict"""
    return {
        # All sp01-sp18 fields
        "sp01_crediti_soci": float(bs.sp01_crediti_soci or 0),
        "sp02_immob_immateriali": float(bs.sp02_immob_immateriali or 0),
        # ... all fields
        "total_assets": float(bs.total_assets),
        "total_equity": float(bs.total_equity),
        "total_debt": float(bs.total_debt),
        # ... calculated properties
    }

# ... other serialization helpers
```

### Frontend: API Client

```typescript
// frontend/lib/api.ts

export interface BulkAssumptionsRequest {
  assumptions: Array<{
    forecast_year: number
    revenue_growth_pct: number
    material_cost_growth_pct: number
    service_cost_growth_pct: number
    personnel_cost_growth_pct: number
    capex_tangible: number
    capex_intangible: number
    new_debt: number
    dividend_payout_pct: number
  }>
  auto_generate: boolean
}

export interface CompleteAnalysisOptions {
  include_historical?: boolean
  include_forecast?: boolean
  include_calculations?: boolean
}

export const api = {
  // ... existing methods

  bulkUpsertAssumptions: async (
    companyId: number,
    scenarioId: number,
    request: BulkAssumptionsRequest
  ) => {
    const response = await axios.put(
      `/api/v1/companies/${companyId}/scenarios/${scenarioId}/assumptions`,
      request
    )
    return response.data
  },

  getCompleteAnalysis: async (
    companyId: number,
    scenarioId: number,
    options?: CompleteAnalysisOptions
  ) => {
    const response = await axios.get(
      `/api/v1/companies/${companyId}/scenarios/${scenarioId}/analysis`,
      { params: options }
    )
    return response.data as CompleteAnalysis
  }
}
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-03 | Claude Code | Initial version - comprehensive API simplification plan |

