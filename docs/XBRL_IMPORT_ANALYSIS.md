# XBRL Import Analysis - Balance Sheet Discrepancies

## Problem Statement

Balance sheet showing 59 € discrepancy:
- Total Assets (2024): 205,627 €
- Total Liabilities (2024): 205,686 €
- **Difference: 59 €**

## Root Cause Analysis

### Finding 1: Italian XBRL Structure

Italian GAAP XBRL files (ITCC taxonomy) contain **TWO types of data**:

1. **Detail Items** - Individual line items (e.g., `CreditiEsigibiliEntroEsercizioSuccessivo`)
2. **Aggregate Totals** - Pre-calculated sums (e.g., `TotaleCrediti`, `TotaleAttivo`)

### Finding 2: Current Import Behavior

Our XBRL parser currently:
- ✅ Imports 20 detail items correctly
- ❌ **IGNORES 26 aggregate total tags**

Critical unmapped totals from BKPS.XBRL:
```
TotaleAttivo                = 205,686 €  (Total Assets)
TotalePassivo               = 205,686 €  (Total Liabilities)
TotalePatrimonioNetto       = 32,086 €   (Total Equity)
TotaleDebiti                = 173,578 €  (Total Debt)
TotaleCrediti               = 82,472 €   (Total Credits)
TotaleImmobilizzazioni      = 72,437 €   (Total Fixed Assets)
TotaleAttivoCircolante      = 126,404 €  (Total Current Assets)
```

Note: **TotaleAttivo = TotalePassivo** in the XBRL (balanced!)

### Finding 3: The 59 € Discrepancy Explained

Comparing imported vs. XBRL totals:

**Credits (Receivables):**
- XBRL Total (`TotaleCrediti`): 82,472 €
- Imported detail (`CreditiEsigibiliEntroEsercizioSuccessivo`): 82,413 €
- **Missing: 59 €**

This 59 € likely comes from:
- `CreditiImposteAnticipateTotaleImposteAnticipate` (59 €) - Deferred tax assets
- Or other credit sub-items not captured by our mapping

### Finding 4: Why Detail Items Don't Always Sum Correctly

Italian XBRL files may have:
1. **Sub-items not explicitly listed** - The taxonomy allows detail breakdowns that aren't always present
2. **Rounding at source** - Companies round individual items, then provide exact totals
3. **Tax-related items** - Deferred taxes, prepaid expenses that have separate tags
4. **Schema variations** - Abbreviated vs. Ordinary vs. Micro schemas have different detail levels

## Current Database Model Behavior

Our `BalanceSheet` model calculates totals as:

```python
@property
def total_assets(self) -> Decimal:
    return (
        sp01_crediti_soci +
        sp02_immob_immateriali +
        sp03_immob_materiali +
        ...  # sum of all detail items
    )
```

**Problem**: If detail items have missing sub-components, our calculated total ≠ XBRL official total.

## Impact Assessment

### Current State
- ✅ Major line items imported correctly
- ✅ Ratios and calculations work
- ❌ Balance sheet may not balance perfectly
- ❌ Totals may differ by 0.01-0.05% from official XBRL
- ❌ No visibility into which version (detail vs. total) is authoritative

### Affected Data
- Any XBRL import where detail items are incomplete
- Files using Abbreviated (Abbreviato) or Micro schemas
- Companies with complex tax structures

## Solutions

### Option 1: Import Totals as Fallback (Recommended)
**Approach**: Use detail items when available, fallback to totals when missing

Pros:
- Most accurate representation of official data
- Handles all schema types
- Minimal code change

Cons:
- Need to modify parser logic
- Potential for confusion (which source was used?)

### Option 2: Import Both Details and Totals
**Approach**: Store both in separate fields, flag discrepancies

Pros:
- Complete audit trail
- Can reconcile differences
- User can choose which to display

Cons:
- Database schema changes required
- More complex UI
- Higher storage requirements

### Option 3: Accept Current Behavior + Warn User
**Approach**: Keep current import, add warnings for unbalanced sheets

Pros:
- No code changes needed
- Already implemented (BalanceCheckWarning component)
- Transparent to user

Cons:
- Doesn't fix the root issue
- May confuse accountants
- Less accurate than official XBRL

### Option 4: Intelligent Hybrid Mapping
**Approach**: Map aggregate totals with priority rules

1. If detail items sum correctly → use details
2. If detail items missing/incomplete → use aggregates
3. If mismatch > threshold → warn user

Pros:
- Best of both worlds
- Most accurate
- Handles edge cases

Cons:
- Complex implementation
- May still have edge cases

## Recommended Action Plan

1. **Immediate** (Completed ✅):
   - Add `BalanceCheckWarning` component to UI
   - Show discrepancy amount to users
   - Explain possible causes

2. **Short-term** (Recommended):
   - Add aggregate total tags to `taxonomy_mapping.json`
   - Modify parser to preferentially use totals when details incomplete
   - Add `import_source` field to track which tags were used

3. **Long-term** (Optional):
   - Store both detail and aggregate values
   - Add reconciliation report
   - Allow user to choose preferred source

## Files to Modify (Short-term Solution)

1. **data/taxonomy_mapping.json**
   - Add mappings for `TotaleCrediti`, `TotaleDebiti`, etc.
   - Map to corresponding field with special handling

2. **importers/xbrl_parser.py**
   - Add priority logic: prefer details, fallback to totals
   - Track which source was used per field

3. **database/models.py** (Optional)
   - Add `import_source` JSON field to track data provenance

## Testing Required

1. Test with BKPS.XBRL (real data)
2. Test with sample_data.xbrl (synthetic)
3. Test with Abbreviated/Micro schemas
4. Verify balance sheet balances after import
5. Check that ratios still calculate correctly

## References

- Italian GAAP Taxonomy: https://www.xbrl.org/taxonomy/it/itcc-ci/
- OIC (Organismo Italiano di Contabilità) Standards
- Art. 2424 c.c. (Balance Sheet structure)
- Art. 2425 c.c. (Income Statement structure)
