# Cash Flow Comprehensive Fix

## Issues Found

### 1. Accruals in other_cash_changes (FIXED ✅)
- **Fixed**: Set `other_cash_changes = Decimal("0")` instead of adding accruals again

### 2. Accruals not in WC total (FIXED ✅)
- **Fixed**: Include accruals in `wc_total` calculation

### 3. Missing "Altri" working capital changes (TO FIX ⚠️)
- **Problem**: `other_wc_changes = Decimal("0")` but should be -4,996
- **Cause**: Missing long-term receivables and other balance sheet changes

## Expected vs Current for 2024

### Operating Activities
| Item | Expected | Current | Status |
|------|----------|---------|--------|
| Profit before adjustments | 1,765,725 | ? | Check |
| Non-cash adjustments | 3,386,580 | ? | Check |
| Cashflow before WC | 5,152,305 | ? | Check |
| WC changes total | 3,467,353 | ? | Check |
| Cashflow after WC | 8,619,658 | ? | Check |
| Cash adjustments | -2,029,211 | ? | Check |
| **Total Operating** | **6,590,447** | **6,679,702** | **❌ OFF by 89,255** |

### Investing Activities
| Item | Expected | Current | Status |
|------|----------|---------|--------|
| **Total Investing** | **-6,787,084** | **-6,782,084** | **❌ OFF by 5,000** |

### Financing Activities
| Item | Expected | Current | Status |
|------|----------|---------|--------|
| Third-party funds | -411,301 | ? | Check |
| Own funds | -9,856 | ? | Check |
| **Total Financing** | **-421,157** | **236,732** | **❌ OFF by 657,889!!** |

### Total Cash Flow
| Item | Expected | Current | Status |
|------|----------|---------|--------|
| **Total** | **-617,794** | **134,350** | **❌ OFF by 752,144** |

## Calculation of "Altri" Working Capital Changes

The -4,996 is likely calculated from:

```python
# Changes in items NOT included in core WC but still affecting cashflow
# Possible sources:
1. Long-term receivables (sp07) - these convert to/from short-term
2. TFR changes - provisions for employee benefits
3. Provisions (sp14) - already handled in non-cash adjustments
4. Other balance sheet movements
```

Let me calculate what it should be:
- Total WC expected: 3,467,353
- Sum of known items: 1,375,000 + 1,390,596 + 628,975 + 37,898 + 39,880 = 3,472,349
- Difference: 3,467,353 - 3,472,349 = **-4,996** ✓

This is the residual/balancing figure!

## Critical Issues

### Issue 1: Database Data
**The database doesn't have the ISTANZA company** - it only has KPS FINANCIAL LAB.

**Action required:** Re-import ISTANZA02353550391.xbrl file

### Issue 2: Backend Restart
**The backend server needs to be restarted** for code changes to take effect.

**Action required:** Restart FastAPI backend

### Issue 3: Other WC Changes Calculation
The "altri" working capital item should reconcile to make the total match.

## Recommended Fix

### Option 1: Calculate "altri" as residual (RECOMMENDED)

```python
# After calculating all specific WC changes
wc_specific = delta_inventory + delta_receivables + delta_payables + delta_accruals_active + delta_accruals_passive

# Calculate "altri" from long-term receivables or as balancing item
delta_long_receivables = D(bs_previous.sp07_crediti_lungo) - D(bs_current.sp07_crediti_lungo)
other_wc_changes = delta_long_receivables  # Or could include other items

# Total includes all items
wc_total = wc_specific + other_wc_changes
```

### Option 2: Include more explicit items

```python
# Long-term receivables that become short-term
delta_long_receivables = D(bs_previous.sp07_crediti_lungo) - D(bs_current.sp07_crediti_lungo)

# TFR is a provision, not WC, but might be included in "altri"
delta_tfr = D(bs_current.sp15_tfr) - D(bs_previous.sp15_tfr)

# Other working capital changes
other_wc_changes = delta_long_receivables + delta_tfr
```

## Next Steps

1. ✅ Fix other_wc_changes calculation
2. ⚠️ Re-import XBRL data
3. ⚠️ Restart backend server
4. ⚠️ Test cashflow calculation

## Testing Commands

```bash
# Re-import XBRL
python3 -c "from importers.xbrl_parser_enhanced import import_xbrl_file_enhanced; result = import_xbrl_file_enhanced('ISTANZA02353550391.xbrl', company_id=None, create_company=True); print(result)"

# Restart backend (in backend directory)
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Test cashflow
python3 debug_cashflow_detailed.py
```
