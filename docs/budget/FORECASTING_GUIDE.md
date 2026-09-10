# 📊 Budget & Forecasting Module - User Guide

> **Superato dal 2026-09: vedi [`docs/budget/API-PREVISIONALE.md`](API-PREVISIONALE.md).** Questa
> guida precede lo scadenziamento del pregresso, le imposte a saldo + acconto, lo scoperto di
> conto corrente e il percorso a sette passi delle ipotesi: descrive un motore e un'interfaccia
> che non sono più questi. Riscriverla è fuori ambito di questo lotto.

## Overview
The forecasting module allows you to create 3-year financial projections based on percentage growth assumptions. You can create multiple scenarios (optimistic, pessimistic, base case) and compare them with historical data.

## Workflow

### 1. Import XBRL Data ✅
First, import your company's historical financial data:
- Navigate to **"📥 Importazione Dati"**
- Upload XBRL file
- Choose "Crea nuova azienda" or "Aggiorna azienda esistente"
- Click "Importa XBRL"

### 2. Create Budget Scenario 📊
Create a forecast scenario with your assumptions:
- Navigate to **"💼 Budget & Previsionale"**
- Click the **"➕ Nuovo Scenario"** tab
- Fill in scenario details:
  - **Nome Scenario**: e.g., "Budget 2025-2027"
  - **Anno Base**: Select the base year (e.g., 2024)
  - **Descrizione**: Optional description
  - **Scenario Attivo**: Check to mark as active

### 3. Input Forecast Assumptions 📝
For each forecast year (default: 3 years), enter:

#### Revenue Growth:
- **% Ricavi vs Base Year**: Revenue growth percentage
- **% Altri Ricavi vs Base Year**: Other revenue growth percentage

#### Cost Growth:
- **% Costi Var. Materiali**: Variable material costs growth
- **% Costi Fissi Materiali**: Fixed material costs growth
- **% Costi Var. Servizi**: Variable service costs growth
- **% Costi Fissi Servizi**: Fixed service costs growth
- **% Godimento Beni Terzi**: Rent/lease growth
- **% Costi Personale**: Personnel costs growth
- **% Oneri Diversi**: Other costs growth

#### Investments & Working Capital:
- **Investimenti (€)**: New investments amount (absolute value)
- **% Crediti Breve**: Short-term receivables growth
- **% Crediti Lungo**: Long-term receivables growth
- **% Debiti Breve**: Short-term payables growth

### 4. Calculate Forecast 🔄
- Click **"💾 Salva e Calcola Previsionale"**
- The system will:
  - Generate forecasted Income Statements
  - Generate forecasted Balance Sheets
  - Calculate all financial ratios
  - Store results in database

### 5. View Forecast Results 🔮
Navigate to **"🔮 Visualizza Previsionale"** to see:

#### Tab 1: Conto Economico
- Side-by-side comparison of historical and forecasted P&L
- Revenue, costs, EBITDA, EBIT, Net Profit trends
- Line chart visualization

#### Tab 2: Stato Patrimoniale
- Side-by-side comparison of historical and forecasted Balance Sheet
- Assets, equity, debt trends
- Bar chart visualization

#### Tab 3: Indici Finanziari
- Key ratios (ROE, ROA, Current Ratio, Debt/Equity, EBITDA Margin)
- Historical vs forecast comparison
- Trend charts for profitability and financial structure

### 6. Calculate Ratios & Altman Z-Score 📈
The forecast data integrates with existing analysis tools:
- **"📈 Indici Finanziari"**: Works with forecast data
- **"⚖️ Altman Z-Score"**: Can calculate Z-Score for forecast years

## Forecast Calculation Logic

### Income Statement:
- **Revenues**: Base year × (1 + growth %)
- **Costs**: Split between variable (60%) and fixed (40%) components
- **Depreciation**: Base depreciation + 20% of new investments
- **Taxes**: 24% Italian IRES rate

### Balance Sheet:
- **Fixed Assets**: Base + Investments - Depreciation
- **Receivables**: Base × (1 + growth %)
- **Inventory**: Base × (1 + revenue growth %)
- **Equity**: Previous equity + net profit
- **Debt**: Adjusted based on payables growth %
- **Cash**: Balancing item (plug)

## Multiple Scenarios

You can create multiple scenarios for the same company:
- **Base Case**: Most likely scenario
- **Optimistic**: Best case with higher growth
- **Pessimistic**: Worst case with lower growth

Each scenario is independent and can be calculated/viewed separately.

## Editing Scenarios

To modify an existing scenario:
1. Go to **"💼 Budget & Previsionale"**
2. Find the scenario in **"📋 Scenari"** tab
3. Click **"✏️ Modifica"**
4. Update assumptions
5. Click **"💾 Salva e Calcola Previsionale"**

## Tips & Best Practices

1. **Start with Historical Data**: Always import at least 2-3 years of historical data first
2. **Use Conservative Assumptions**: It's better to under-promise and over-deliver
3. **Review Ratios**: Check that forecast ratios remain reasonable (compare with industry benchmarks)
4. **Multiple Scenarios**: Create at least 3 scenarios (optimistic, base, pessimistic)
5. **Regular Updates**: Update scenarios quarterly based on actual performance
6. **Cash Flow**: Pay attention to the cash balance - negative cash will increase short-term debt

## Troubleshooting

### "❌ Dati completi non trovati per l'anno"
- Make sure you've imported complete data for the base year
- Both Balance Sheet and Income Statement must be present

### "❌ Nessun dato previsionale trovato"
- Click **"🔄 Ricalcola"** to regenerate the forecast
- Verify assumptions are saved

### Forecast doesn't balance
- The system automatically balances using cash as a plug
- If cash is negative, short-term debt is increased

## Database Tables

The forecasting module uses these tables:
- `budget_scenarios`: Scenario metadata
- `budget_assumptions`: % growth assumptions per year
- `forecast_years`: Links to forecast financial statements
- `forecast_balance_sheets`: Projected balance sheets
- `forecast_income_statements`: Projected income statements

## API Integration

To programmatically generate forecasts:

```python
from calculations.forecast_engine import generate_forecast_for_scenario
from database.db import SessionLocal

db = SessionLocal()
result = generate_forecast_for_scenario(scenario_id=1, db_session=db)
print(result)
```

---

**Happy Forecasting! 🚀**
