# Cashflow 2024 Issues Analysis

## Summary of Differences

| Section | Calculated | Correct | Difference | Status |
|---------|-----------|---------|------------|--------|
| Interest expense/income | 1.644.295 € | 1.653.112 € | -8.817 € | ⚠️ Minor |
| Profit before adjustments | 1.756.908 € | 1.765.725 € | -8.817 € | ⚠️ Minor |
| Provisions (accantonamenti) | **0 €** | **189.973 €** | **-189.973 €** | 🔴 **MISSING** |
| Non-cash adjustments total | 3.196.607 € | 3.386.580 € | -189.973 € | 🔴 Error |
| Cashflow before WC | 4.953.515 € | 5.152.305 € | -198.790 € | 🔴 Error |
| Cashflow after WC | 8.420.868 € | 8.619.658 € | -198.790 € | 🔴 Error |
| Use of provisions | **0 €** | **-274.232 €** | **274.232 €** | 🔴 **MISSING** |
| Total other adjustments | -1.746.162 € | -2.029.211 € | 283.049 € | 🔴 Error |
| **Operating Cashflow (A)** | **6.674.706 €** | **6.590.447 €** | **84.259 €** | 🔴 **Wrong** |
| Tangible investments | -2.666.591 € | -1.169.705 € | -1.496.886 € | 🔴 **Wrong split** |
| Intangible investments | -4.117.993 € | -5.614.879 € | 1.496.886 € | 🔴 **Wrong split** |
| **Investing Cashflow (B)** | **-6.782.084 €** | **-6.787.084 €** | **5.000 €** | ⚠️ Small error |
| Debt change | 217.674 € (shown as increment) | -411.301 € (shown as decrement) | 628.975 € | 🔴 **MAJOR ERROR** |
| Equity change | 19.058 € (shown as increment) | -9.856 € (shown as decrement) | 28.914 € | 🔴 **Wrong** |
| **Financing Cashflow (C)** | **236.732 €** | **-421.157 €** | **657.889 €** | 🔴 **CRITICAL ERROR** |
| **Total Cashflow** | **129.354 €** | **-617.794 €** | **747.148 €** | 🔴 **WRONG** |

---

## Issue 1: Missing Provisions (Accantonamenti) ⚠️ CRITICAL

**Location:** `cashflow_detailed.py`, line 131
**Code:**
```python
provisions = D(inc_current.ce11_accantonamenti)
```

**Problem:** The code correctly reads `ce11_accantonamenti` but it's showing as **0 €** in the output, when it should be **189.973 €**.

**Root Cause:** The income statement field `ce11_accantonamenti` is likely not populated during XBRL import.

**Impact:**
- Non-cash adjustments understated by 189.973 €
- Operating cashflow overstated by 189.973 €

**Fix:** Check XBRL import mapping for provisions (`ce11_accantonamenti`). The provision value should come from the income statement XBRL data.

---

## Issue 2: Missing Use of Provisions ⚠️ CRITICAL

**Location:** `cashflow_detailed.py`, line 200-201
**Code:**
```python
use_of_provisions = -(D(bs_previous.sp14_fondi_rischi) + provisions - D(bs_current.sp14_fondi_rischi))
```

**Problem:** Shows as **0 €** but should be **-274.232 €**

**Root Cause:** The formula is correct, but the calculation is likely wrong due to:
1. Missing provisions value (see Issue 1)
2. Incorrect balance sheet reserves values

**Expected calculation:**
```
Use = -(Previous_reserves + New_provisions - Current_reserves)
Use = -(sp14_2023 + 189.973 - sp14_2024)
```

**Impact:**
- Cash adjustments understated by 274.232 €
- Operating cashflow overstated by 274.232 €

**Fix:**
1. Fix provisions import (Issue 1)
2. Verify sp14_fondi_rischi values for 2023 and 2024

---

## Issue 3: Wrong Depreciation Split Between Tangible/Intangible ⚠️ CRITICAL

**Location:** `cashflow_detailed.py`, lines 240-275
**Current Logic:**
```python
# Split based on asset proportions
total_fixed_assets_previous = D(bs_previous.sp02_immob_immateriali) + D(bs_previous.sp03_immob_materiali)
if total_fixed_assets_previous > 0:
    tangible_ratio = D(bs_previous.sp03_immob_materiali) / total_fixed_assets_previous
else:
    tangible_ratio = Decimal("0.8")

depreciation_tangible = depreciation_amortization * tangible_ratio
depreciation_intangible = depreciation_amortization * (Decimal("1") - tangible_ratio)

tangible_investments = -(delta_tangible + depreciation_tangible)
intangible_investments = -(delta_intangible + depreciation_intangible)
```

**Problem:** The depreciation split is based on **beginning balance proportions**, but this doesn't reflect the actual depreciation for each asset type.

**Current Results:**
- Tangible: -2.666.591 € (wrong)
- Intangible: -4.117.993 € (wrong)

**Correct Results:**
- Tangible: -1.169.705 €
- Intangible: -5.614.879 €

**Why This Happens:**
The XBRL file should have separate depreciation values for tangible (`ammortamento immobilizzazioni materiali`) and intangible (`ammortamento immobilizzazioni immateriali`) assets, but the code uses a single `ce09_ammortamenti` field that aggregates both.

**Fix Options:**

### Option A: Split ce09_ammortamenti into two fields during import
- Add `ce09a_ammort_immateriali` and `ce09b_ammort_materiali` fields to IncomeStatement model
- Update XBRL parser to extract these separately
- Update cashflow calculator to use separate values

### Option B: Use a different calculation method
Instead of splitting depreciation, calculate CAPEX directly:
```python
# For tangible assets - use the actual change + average depreciation rate
tangible_capex = calculate_capex_from_balance_sheet_analysis(...)
```

### Option C: Use external data or assumptions
If XBRL doesn't provide split depreciation, make an informed assumption based on:
- Industry standards (e.g., intangibles amortize faster: 20% vs 10%)
- Asset register data if available

**Recommended:** Option A - properly split depreciation during import.

---

## Issue 4: DOUBLE-COUNTING of Short-Term Debt ⚠️ CRITICAL LOGIC ERROR

**Location:** `cashflow_detailed.py`
- Working capital section (line 156): `delta_payables = D(bs_current.sp16_debiti_breve) - D(bs_previous.sp16_debiti_breve)`
- Financing section (line 305-306): `current_debt = D(bs_current.sp16_debiti_breve) + D(bs_current.sp17_debiti_lungo)`

**Problem:** `sp16_debiti_breve` includes BOTH:
1. **Operating payables** (trade payables, tax payables, social security)
2. **Financial short-term debt** (bank loans, bonds due within 12 months)

The code currently:
- Includes ALL sp16 changes in working capital (as payables)
- Includes ALL sp16 in financing activities (as debt)
- This **DOUBLE-COUNTS** the short-term debt portion!

**Impact:**
Let's say sp16 = 5,000,000 € in 2023 and 4,500,000 € in 2024 (decrease of 500,000 €)

Current (WRONG):
- Working capital: +500,000 € (decrease in payables = less cash)
- Financing: -500,000 € (decrease in debt)
- **Net effect: 0** (double-counting cancels out in total but wrong sections)

Correct:
- Working capital: Should only include TRADE PAYABLES change
- Financing: Should only include FINANCIAL DEBT change

**Why This Matters:**
While the total cashflow might be close, the BREAKDOWN is wrong:
- Operating cashflow is UNDERSTATED (because debt repayment is reducing it)
- Financing cashflow is OVERSTATED (because it includes operating payables)

**Evidence from User Data:**
Correct cashflow shows:
- Working capital payables change: +628.975 € (operating payables only)
- Financing debt change: -411.301 € (financial debt only)
- Our calculation shows: changes that include BOTH

**Fix:** Need to separate sp16 into:
1. `sp16a_debiti_commerciali` (trade payables) → working capital
2. `sp16b_debiti_finanziari` (short-term bank loans) → financing

This requires updating:
- Database model to split sp16
- XBRL parser to extract trade payables vs financial debt separately
- Cashflow calculator to use the split values

**Temporary Workaround:**
If we can't split sp16, we could:
1. Assume all sp16 is operating payables (include in WC, exclude from financing)
2. Assume all sp16 is financial debt (exclude from WC, include in financing)

Neither is correct, but option 1 is more common for small companies.

---

## Issue 5: Financing Section - Wrong Increase/Decrease Display ⚠️ PRESENTATION ISSUE

**Location:** `cashflow_detailed.py`, lines 309-331
**Current Logic:**
```python
delta_debt = current_debt - previous_debt

debt_increases = delta_debt if delta_debt > 0 else Decimal("0")
debt_decreases = -delta_debt if delta_debt < 0 else Decimal("0")
debt_net = delta_debt
```

**Problem:** When debt DECREASES (delta_debt < 0), the code shows:
- `debt_increases = 0`
- `debt_decreases = -delta_debt` (becomes POSITIVE)
- `debt_net = delta_debt` (NEGATIVE)

But in the actual cashflow statement output, it's showing:
- "Incremento mezzi di terzi: 217.674 €" (should be 0)
- "(Decremento mezzi di terzi): 0 €" (should be -411.301 €)

**Why This Happens:**
The display logic in the frontend might be:
1. Showing increases as positive line
2. Not showing decreases in parentheses
3. Showing only the NET value

**Correct Display:**
```
Mezzi di terzi                    -411.301 €
  Incremento mezzi di terzi              0 €
  (Decremento mezzi di terzi)     -411.301 €
```

OR (alternative format - show absolute values with sign):
```
Mezzi di terzi                    -411.301 €
  Incremento mezzi di terzi              0 €
  (Decremento mezzi di terzi)      411.301 € (shown in parentheses)
```

**Fix:** Update the frontend template to properly display financing activities with:
- Increases shown as positive
- Decreases shown in parentheses as absolute values
- Net shown with proper sign

---

## Issue 6: Minor Interest Calculation Difference (8.817 €)

**Location:** `cashflow_detailed.py`, lines 96-107

**Difference:** 1.644.295 € vs 1.653.112 € = 8.817 €

**Possible Causes:**
1. Rounding differences in data extraction
2. Missing interest items in ce15_oneri_finanziari
3. Different treatment of "altri proventi finanziari"

**Fix:** Check XBRL extraction for:
- `ce15_oneri_finanziari` (should extract ALL interest expenses)
- `ce14_altri_proventi_finanziari` (should extract ALL financial income)

This is a minor issue but should be investigated to ensure data accuracy.

---

## Fix Priority

### 🔥 Priority 1 (Critical - Wrong Total Cashflow)
1. **Issue 4: DOUBLE-COUNTING** - This is causing the wrong breakdown between sections
2. **Issue 1: Missing Provisions** - Need to fix XBRL import for ce11_accantonamenti
3. **Issue 2: Use of Provisions** - Depends on Issue 1
4. **Issue 3: Depreciation Split** - Major impact on investing activities breakdown

### ⚠️ Priority 2 (Presentation Issues)
5. **Issue 5: Financing Display** - Wrong presentation but calculations might be OK

### ✅ Priority 3 (Minor Issues)
6. **Issue 6: Interest Calculation** - Small difference, low impact

---

## Recommended Action Plan

### Step 1: Fix Database Model
```python
# Add to BalanceSheet model:
sp16a_debiti_commerciali = Column(Numeric(15, 2), default=0)  # Trade payables
sp16b_debiti_finanziari_breve = Column(Numeric(15, 2), default=0)  # Short-term financial debt

# Add to IncomeStatement model:
ce09a_ammort_immateriali = Column(Numeric(15, 2), default=0)
ce09b_ammort_materiali = Column(Numeric(15, 2), default=0)
```

### Step 2: Fix XBRL Parser
Update `importers/xbrl_parser.py` to extract:
- Trade payables separately from financial debt
- Depreciation split between tangible and intangible
- Provisions (ce11_accantonamenti) correctly

### Step 3: Fix Cashflow Calculator
Update `cashflow_detailed.py`:
- Use sp16a for working capital changes
- Use sp16b + sp17 for financing activities
- Use separate depreciation values for tangible vs intangible

### Step 4: Fix Frontend Display
Update cashflow page to properly display financing activities with parentheses for decreases.

---

## Testing Checklist

After fixes, verify:
- [ ] Provisions show 189.973 € in non-cash adjustments
- [ ] Use of provisions shows -274.232 € in cash adjustments
- [ ] Operating cashflow = 6.590.447 € ✓
- [ ] Tangible investments = -1.169.705 € ✓
- [ ] Intangible investments = -5.614.879 € ✓
- [ ] Investing cashflow = -6.787.084 € ✓
- [ ] Debt change = -411.301 € ✓
- [ ] Equity change = -9.856 € ✓
- [ ] Financing cashflow = -421.157 € ✓
- [ ] **Total cashflow = -617.794 € ✓**

---

## Notes

The DOUBLE-COUNTING issue (Issue 4) is the most critical because it affects the fundamental logic of the cashflow calculation. Even if the total cashflow accidentally matches due to offsetting errors, the breakdown between operating, investing, and financing activities will be completely wrong.

This is why Italian GAAP requires detailed balance sheet breakdowns (piano dei conti) that separate:
- D.7) Debiti verso fornitori (trade payables)
- D.4) Debiti verso banche (bank loans)
- D.11) Debiti verso controllate/collegate
- etc.

We need to update our XBRL parser to extract these detail lines instead of just the aggregate sp16_debiti_breve value.
