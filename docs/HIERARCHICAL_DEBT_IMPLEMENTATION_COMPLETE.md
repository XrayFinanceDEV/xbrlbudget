# Hierarchical Debt and Depreciation Implementation - COMPLETE

## ✅ Implementation Summary

We've successfully updated the XBRL import system to extract detailed debt breakdowns and depreciation splits, solving the cashflow double-counting issue.

## Changes Made

### 1. Database Model Updates (`database/models.py`)

**Balance Sheet (both BalanceSheet and ForecastBalanceSheet):**
- Added 14 new detailed debt fields:
  - `sp16a_debiti_banche_breve` / `sp17a_debiti_banche_lungo` - Bank loans
  - `sp16b_debiti_altri_finanz_breve` / `sp17b_debiti_altri_finanz_lungo` - Other financial debts
  - `sp16c_debiti_obbligazioni_breve` / `sp17c_debiti_obbligazioni_lungo` - Bonds
  - `sp16d_debiti_fornitori_breve` / `sp17d_debiti_fornitori_lungo` - Trade payables
  - `sp16e_debiti_tributari_breve` / `sp17e_debiti_tributari_lungo` - Tax debts
  - `sp16f_debiti_previdenza_breve` / `sp17f_debiti_previdenza_lungo` - Social security debts
  - `sp16g_altri_debiti_breve` / `sp17g_altri_debiti_lungo` - Other debts

- Added computed properties:
  - `financial_debt_short` / `financial_debt_long` / `financial_debt_total` - For financing cashflow
  - `operating_debt_short` / `operating_debt_long` / `operating_debt_total` - For working capital cashflow

**Income Statement (both IncomeStatement and ForecastIncomeStatement):**
- Added 3 new depreciation split fields:
  - `ce09a_ammort_immateriali` - Intangible depreciation
  - `ce09b_ammort_materiali` - Tangible depreciation
  - `ce09c_svalutazioni` - Write-downs

### 2. Taxonomy Mapping Updates (`data/taxonomy_mapping.json`)

**Debt Mapping:**
- Split debt mappings into financial vs operating categories
- Banks, bonds, other financiers → Financial debt fields (for financing cashflow)
- Suppliers, taxes, social security, others → Operating debt fields (for working capital)
- Kept aggregate mappings for backward compatibility

**Depreciation Mapping:**
- Added mappings for split depreciation by asset type
- Added mappings for provisions (accantonamenti)
- Supports multiple taxonomy versions

### 3. XBRL Parser Updates (`importers/xbrl_parser.py`)

**New Methods:**
- `_calculate_aggregates_from_details()` - Calculates sp16/sp17 totals from detail fields
- `_calculate_income_aggregates()` - Calculates ce09 total from split fields
- `_estimate_depreciation_split()` - Estimates depreciation split based on asset proportions when details are missing

**Logic:**
1. Extracts all detailed debt items from XBRL
2. Sums details into aggregate fields (sp16, sp17)
3. If no details exist (old XBRL), puts all in "altri debiti" (operating)
4. Estimates depreciation split based on balance sheet asset proportions if XBRL doesn't provide split

### 4. Database Migration (`migrate_hierarchical_debts.py`)

- Created migration script that adds all new fields to existing tables
- Supports both `balance_sheets` and `forecast_balance_sheets`
- Supports both `income_statements` and `forecast_income_statements`
- Migration completed successfully on both databases

## Migration Status

✅ Migrations completed on:
- `/home/peter/DEV/budget/financial_data.db`
- `/home/peter/DEV/budget/backend/financial_analysis.db`

All new fields have been added successfully.

## Next Steps

### CRITICAL: Update Cashflow Calculator

Now that the detailed debt fields exist, we need to update `backend/app/calculations/cashflow_detailed.py` to use them:

1. **Working Capital Section** - Use operating debts only:
   ```python
   # OLD (WRONG - double counts):
   delta_payables = D(bs_current.sp16_debiti_breve) - D(bs_previous.sp16_debiti_breve)

   # NEW (CORRECT - operating only):
   delta_payables = D(bs_current.operating_debt_short) - D(bs_previous.operating_debt_short)
   ```

2. **Financing Section** - Use financial debts only:
   ```python
   # OLD (WRONG - includes operating debts):
   current_debt = D(bs_current.sp16_debiti_breve) + D(bs_current.sp17_debiti_lungo)

   # NEW (CORRECT - financial only):
   current_debt = D(bs_current.financial_debt_total)
   ```

3. **Depreciation Split** - Use actual split values:
   ```python
   # OLD (estimates based on asset proportions):
   depreciation_tangible = depreciation_amortization * tangible_ratio

   # NEW (uses actual XBRL data):
   depreciation_tangible = D(inc_current.ce09b_ammort_materiali)
   depreciation_intangible = D(inc_current.ce09a_ammort_immateriali)

   # Fallback to estimate if not provided:
   if depreciation_tangible == 0 and depreciation_intangible == 0:
       # Use ratio-based estimation
   ```

### Testing Requirements

Before deploying, verify:

1. **Re-import XBRL** - The ISTANZA file needs to be re-imported to populate the new fields
2. **Verify Aggregates** - Check that sum of details = aggregate (sp16, sp17, ce09)
3. **Test Cashflow** - Run cashflow calculation with new fields and verify it matches the correct Excel output:
   - Operating cashflow: 6.590.447 € ✓
   - Investing cashflow: -6.787.084 € ✓
   - Financing cashflow: -421.157 € ✓
   - Total cashflow: -617.794 € ✓

### Files to Update

1. ✅ `database/models.py` - DONE
2. ✅ `data/taxonomy_mapping.json` - DONE
3. ✅ `importers/xbrl_parser.py` - DONE
4. ✅ `migrate_hierarchical_debts.py` - DONE
5. ⏳ `backend/app/calculations/cashflow_detailed.py` - NEEDS UPDATE
6. ⏳ Re-import XBRL data - NEEDS TO BE DONE
7. ⏳ Test complete cashflow calculation - NEEDS TO BE DONE

## Technical Notes

### Why This Fixes the Double-Counting Issue

**Before (WRONG):**
```
Working Capital:
  Delta payables = sp16_breve(2024) - sp16_breve(2023)
                 = ALL debts change (financial + operating)

Financing:
  Delta debt = (sp16 + sp17)(2024) - (sp16 + sp17)(2023)
             = ALL debts change (financial + operating)

Result: SHORT-TERM DEBT COUNTED TWICE!
```

**After (CORRECT):**
```
Working Capital:
  Delta operating payables = operating_debt_short(2024) - operating_debt_short(2023)
                           = ONLY suppliers, taxes, social security

Financing:
  Delta financial debt = financial_debt_total(2024) - financial_debt_total(2023)
                       = ONLY banks, bonds, financial loans

Result: EACH DEBT TYPE COUNTED ONCE IN CORRECT SECTION ✓
```

### Backward Compatibility

- Original aggregate fields (sp16, sp17, ce09) are still populated
- Old code that uses aggregates will continue to work
- New cashflow code should use detailed fields for accurate breakdown

### Fallback Logic

If XBRL file doesn't provide detailed breakdown:
- **Debts**: All placed in `sp16g_altri_debiti_breve` (operating)
- **Depreciation**: Split estimated based on asset proportions from balance sheet

This ensures the system works with both detailed and simplified XBRL files.

## Impact on Correct Cashflow Values

With these changes, the cashflow should correctly show:

| Item | Current (Wrong) | After Fix (Correct) |
|------|----------------|---------------------|
| Operating debt change (WC) | Mixed with financial | 628.975 € (payables only) |
| Financial debt change (Financing) | Mixed with operating | -411.301 € (banks only) |
| Operating Cashflow | 6.674.706 € | 6.590.447 € ✓ |
| Financing Cashflow | 236.732 € | -421.157 € ✓ |
| Total Cashflow | 129.354 € | -617.794 € ✓ |

## Commands for Next Steps

```bash
# 1. Re-import XBRL (from backend directory)
cd /home/peter/DEV/budget/backend
.venv/bin/python -c "
from importers.xbrl_parser import import_xbrl_file
result = import_xbrl_file('../ISTANZA02353550391.xbrl')
print(f'Imported: {result}')
"

# 2. Verify the detailed fields were populated
.venv/bin/python -c "
from database.db import SessionLocal
from database.models import Company, BalanceSheet

db = SessionLocal()
company = db.query(Company).filter(Company.name.like('%PUCCI%')).first()
bs = company.financial_years[0].balance_sheet

print(f'Financial debt short: {bs.financial_debt_short}')
print(f'Operating debt short: {bs.operating_debt_short}')
print(f'Total sp16: {bs.sp16_debiti_breve}')
print(f'Match: {bs.financial_debt_short + bs.operating_debt_short == bs.sp16_debiti_breve}')
"

# 3. After updating cashflow_detailed.py, test the calculation
cd /home/peter/DEV/budget
.venv/bin/python debug_cashflow_detailed.py
```

## Documentation

All changes are documented in:
- `CASHFLOW_ISSUES_ANALYSIS.md` - Detailed problem analysis
- This file - Implementation summary
- Code comments in modified files

## Status: READY FOR CASHFLOW CALCULATOR UPDATE

The database schema and XBRL import are complete. Next step is to update the cashflow calculator to use the new fields.
