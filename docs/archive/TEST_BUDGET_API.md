# Budget Scenarios API - Testing Guide

## API Documentation
Access Swagger UI at: http://127.0.0.1:8000/docs#/

All budget scenario endpoints are under the **budget_scenarios** tag.

## Available Endpoints

### Budget Scenario Management

1. **GET /api/v1/companies/{company_id}/scenarios**
   - List all budget scenarios for a company
   - Optional query params: `skip`, `limit`, `is_active`

2. **GET /api/v1/companies/{company_id}/scenarios/{scenario_id}**
   - Get single scenario
   - Optional query param: `include_details=true` (includes nested assumptions and forecast years)

3. **POST /api/v1/companies/{company_id}/scenarios**
   - Create new budget scenario
   - Required fields: `company_id`, `name`, `base_year`
   - Optional: `description`, `is_active` (default: 1)

4. **PUT /api/v1/companies/{company_id}/scenarios/{scenario_id}**
   - Update scenario metadata
   - All fields optional

5. **DELETE /api/v1/companies/{company_id}/scenarios/{scenario_id}**
   - Delete scenario and cascade delete all related data

### Budget Assumptions Management

6. **GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions**
   - List all assumptions for a scenario

7. **POST /api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions**
   - Create assumptions for a forecast year
   - Required: `scenario_id`, `forecast_year`
   - All growth rates default to 0
   - Cannot duplicate (scenario_id, forecast_year)

8. **PUT /api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions/{year}**
   - Update assumptions for specific year
   - All fields optional

9. **DELETE /api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions/{year}**
   - Delete assumptions for specific year

### Forecast Generation

10. **POST /api/v1/companies/{company_id}/scenarios/{scenario_id}/generate**
    - Generate forecasts for all years with assumptions
    - Returns summary with statistics per year

### Forecast Data Access

11. **GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/forecasts**
    - List all forecast years

12. **GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/forecasts/{year}/balance-sheet**
    - Get forecasted balance sheet for specific year

13. **GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/forecasts/{year}/income-statement**
    - Get forecasted income statement for specific year

## Testing Flow (via Swagger UI)

### Step 1: Check Available Companies
```
GET /api/v1/companies
```
Note a company ID (e.g., company_id=1)

### Step 2: Check Available Years
```
GET /api/v1/companies/{company_id}/years
```
Note a year to use as base_year (e.g., 2023)

### Step 3: Create Budget Scenario
```
POST /api/v1/companies/{company_id}/scenarios

Request Body:
{
  "company_id": 1,
  "name": "Conservative Growth Scenario",
  "base_year": 2023,
  "description": "3-year forecast with 5% annual revenue growth",
  "is_active": 1
}
```
Note the returned scenario_id

### Step 4: Create Assumptions for Year 1
```
POST /api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions

Request Body:
{
  "scenario_id": 1,
  "forecast_year": 2024,
  "revenue_growth_pct": 5.0,
  "other_revenue_growth_pct": 3.0,
  "variable_materials_growth_pct": 5.0,
  "fixed_materials_growth_pct": 2.0,
  "variable_services_growth_pct": 5.0,
  "fixed_services_growth_pct": 2.0,
  "rent_growth_pct": 1.0,
  "personnel_growth_pct": 3.0,
  "other_costs_growth_pct": 2.0,
  "investments": 50000.0,
  "receivables_short_growth_pct": 5.0,
  "receivables_long_growth_pct": 0.0,
  "payables_short_growth_pct": 5.0,
  "interest_rate_receivables": 0.5,
  "interest_rate_payables": 4.5,
  "tax_rate": 24.0,
  "fixed_materials_percentage": 40.0,
  "fixed_services_percentage": 40.0,
  "depreciation_rate": 20.0,
  "financing_amount": 0.0,
  "financing_duration_years": 0.0,
  "financing_interest_rate": 0.0
}
```

### Step 5: Create Assumptions for Years 2 & 3
Repeat Step 4 with `forecast_year: 2025` and `forecast_year: 2026`
Adjust growth rates as needed for each year

### Step 6: Generate Forecasts
```
POST /api/v1/companies/{company_id}/scenarios/{scenario_id}/generate
```
This will return a summary with statistics for each forecast year:
- total_assets
- total_equity
- total_debt
- working_capital_net
- revenue
- ebitda
- ebit
- net_profit

### Step 7: Retrieve Forecast Data
```
GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/forecasts

GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/forecasts/2024/balance-sheet

GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/forecasts/2024/income-statement
```

### Step 8: Update Assumptions and Regenerate
```
PUT /api/v1/companies/{company_id}/scenarios/{scenario_id}/assumptions/2024

Request Body:
{
  "revenue_growth_pct": 7.5
}

Then regenerate:
POST /api/v1/companies/{company_id}/scenarios/{scenario_id}/generate
```

## Example cURL Commands

### Create Scenario
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/companies/1/scenarios" \
  -H "Content-Type: application/json" \
  -d '{
    "company_id": 1,
    "name": "Test Scenario",
    "base_year": 2023,
    "is_active": 1
  }'
```

### Create Assumptions
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/companies/1/scenarios/1/assumptions" \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_id": 1,
    "forecast_year": 2024,
    "revenue_growth_pct": 5.0,
    "tax_rate": 24.0
  }'
```

### Generate Forecast
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/companies/1/scenarios/1/generate"
```

### Get Forecast Balance Sheet
```bash
curl "http://127.0.0.1:8000/api/v1/companies/1/scenarios/1/forecasts/2024/balance-sheet"
```

## Error Handling

The API returns appropriate HTTP status codes:
- **200 OK**: Successful GET/PUT
- **201 Created**: Successful POST (creation)
- **204 No Content**: Successful DELETE
- **400 Bad Request**: Validation errors (missing data, duplicate records, etc.)
- **404 Not Found**: Resource not found
- **500 Internal Server Error**: Calculation errors

## Validation Rules

1. **Scenario Creation**:
   - Company must exist
   - Base year must have complete financial data (BalanceSheet + IncomeStatement)
   - Name cannot be empty

2. **Assumptions Creation**:
   - Forecast year must be > base_year
   - Cannot create duplicate assumptions for same (scenario_id, forecast_year)

3. **Forecast Generation**:
   - At least one assumption must exist
   - Base year must have complete data
   - ForecastEngine will calculate balance sheet with cash as plug
   - If cash goes negative, short-term debt increases

## Integration with Streamlit UI

The API runs independently of the Streamlit UI. Both access the same SQLite database at `/home/peter/DEV/budget/xbrl_budget.db`, so:
- Scenarios created via API are visible in Streamlit
- Scenarios created in Streamlit are accessible via API
- Both use the same ForecastEngine calculation logic

## Next Steps

1. Open Swagger UI: http://127.0.0.1:8000/docs#/
2. Locate the **budget_scenarios** section
3. Follow the testing flow above
4. Verify forecast calculations are correct
5. Test error handling (try invalid inputs)
