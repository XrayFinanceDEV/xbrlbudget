# Reserves Accumulation Fix - COMPLETE ✅

## Problem

After implementing Phase 1 priority-based mapping, the **Patrimonio Netto (Equity)** section showed incorrect values:

**Wrong (before fix):**
```
Capitale: €1,100,000 ✓
Riserve: €19,365 ✗ (only legal reserve)
Utile: €10,746 ✓
TOTAL: €1,130,111 ✗ (missing €3.14M!)
```

**Expected (from XBRL):**
```
Capitale: €1,100,000
Riserve: €3,161,378 (all reserve types)
Utile: €10,746
TOTAL: €4,272,124
```

## Root Cause

Two issues were found:

### Issue 1: Priority-Based Matching Stopped at First Match

The `sp12_riserve` mapping had:
```json
"sp12_riserve": {
  "priority_1": "itcc-ci:PatrimonioNettoRiservaLegale",  // First match wins!
  "priority_2": "itcc-ci:PatrimonioNettoAltreRiserve...",
  ...
}
```

This meant only the **first matching reserve** (legal reserve = €19,365) was captured, and other reserves were ignored.

**Solution:** Changed to `accumulate_all: true` with `detail_tags`:
```json
"sp12_riserve": {
  "accumulate_all": true,
  "detail_tags": [
    "itcc-ci:PatrimonioNettoRiservaLegale",
    "itcc-ci:PatrimonioNettoRiservaSoprapprezzoAzioni",
    "itcc-ci:PatrimonioNettoAltreRiserveDistintamente...",
    "itcc-ci:PatrimonioNettoUtiliPerditePortatiNuovo",
    ...
  ]
}
```

### Issue 2: V1 Fallback Interfered with V2

Even after v2 successfully accumulated reserves, v1 fallback was trying to re-map individual reserve tags to `sp12_riserve`, overwriting the v2 value.

**Solution:** Added tracking of v2-mapped fields:
```python
v2_mapped_fields_bs = set()
# Track which fields were successfully mapped by v2
if value is not None:
    bs_data[field] = value
    v2_mapped_fields_bs.add(field)

# Later in v1 fallback:
if field in v2_mapped_fields_bs:
    continue  # Skip - already mapped by v2
```

### Issue 3: Missing Tag Variation

XBRL file contained `PatrimonioNettoRiservaSoprapprezzoAzioni` (with "Azioni"), but mapping only had `PatrimonioNettoRiservaSoprapprezzo` (without "Azioni"). This caused the share premium reserve (€3,180,324) to be missed.

**Solution:** Added correct tag to detail_tags.

## Implementation

### 1. Updated taxonomy_mapping_v2.json

```json
"sp12_riserve": {
  "comment": "Accumulates ALL reserve types",
  "accumulate_all": true,
  "detail_tags": [
    "itcc-ci:PatrimonioNettoRiservaLegale",
    "itcc-ci:PatrimonioNettoRiservaSoprapprezzo",
    "itcc-ci:PatrimonioNettoRiservaSoprapprezzoAzioni",  // ADDED
    "itcc-ci:PatrimonioNettoRiservaRivalutazione",
    "itcc-ci:PatrimonioNettoRiserveStatutarie",
    "itcc-ci:PatrimonioNettoAltreRiserve",
    "itcc-ci:PatrimonioNettoAltreRiserveDistintamenteIndicateTotaleAltreRiserve",
    "itcc-ci:PatrimonioNettoRiservaOperazioniCoperturaFlussiFinanziariAttesi",
    "itcc-ci:PatrimonioNettoUtiliPerditePortatiNuovo"
  ]
}
```

### 2. Updated xbrl_parser_enhanced.py

**Added `accumulate_all` logic:**
```python
def _extract_value_by_priority(self, facts, field_config):
    # If accumulate_all=true, try detail_tags FIRST
    if field_config.get('accumulate_all', False) and 'detail_tags' in field_config:
        accumulated = Decimal('0')
        found_any = False

        for detail_tag in field_config['detail_tags']:
            # Match and accumulate ALL matching tags
            ...
            accumulated += value
            found_any = True

        if found_any:
            return accumulated, 'detail_tags_accumulated (N items)'

    # Then try priority matching...
```

**Added v2 field tracking:**
```python
v2_mapped_fields_bs = set()

# Track successfully mapped fields
if value is not None:
    bs_data[field] = value
    v2_mapped_fields_bs.add(field)

# V1 fallback skips v2-mapped fields
if field in v2_mapped_fields_bs:
    continue
```

## Test Results

### Test 1: Reserves Accumulation (Mock Data)
```
✅ PASS: All reserves accumulated correctly!
Value: €3,161,378.00
Matched: detail_tags_accumulated (4 items)
```

### Test 2: Full XBRL Import (Real File)
```
✅ PASS: Full XBRL Import Test

Patrimonio Netto (Equity):
  sp11_capitale: €1,100,000.00 ✓
  sp12_riserve: €3,161,378.00 ✓ (accumulated 6 reserve types)
  sp13_utile_perdita: €10,746.00 ✓
  TOTAL: €4,272,124.00 ✓
```

### Reserve Types Accumulated
1. **Riserva Legale** (Legal reserve): €19,365
2. **Riserva Soprapprezzo Azioni** (Share premium): €3,180,324
3. **Altre Riserve** (Other reserves): €30,222
4. **Riserve Statutarie** (Statutory): €0
5. **Utili/Perdite Portati a Nuovo** (Retained earnings): -€68,533
6. **Riserva Operazioni Copertura** (Hedge reserve): €0

**Total: €3,161,378** ✓

## Files Modified

1. **data/taxonomy_mapping_v2.json**:
   - Changed `sp12_riserve` to `accumulate_all: true`
   - Added all reserve tag variations to `detail_tags`
   - Added `PatrimonioNettoRiservaSoprapprezzoAzioni` (missing tag)

2. **importers/xbrl_parser_enhanced.py**:
   - Updated `_extract_value_by_priority()` to handle `accumulate_all` flag
   - Added `v2_mapped_fields_bs` and `v2_mapped_fields_inc` tracking
   - Modified v1 fallback to skip v2-mapped fields

3. **backend/** (synchronized):
   - `backend/data/taxonomy_mapping_v2.json`
   - `backend/importers/xbrl_parser_enhanced.py`

## Expected Balance Sheet Output

After fix, the balance sheet should show:

```
PASSIVO E PATRIMONIO NETTO
A) PATRIMONIO NETTO
I - Capitale                        €1,100,000
IV-VII - Riserve                    €3,161,378  ← FIXED!
IX - Utile (perdita) dell'esercizio   €10,746
Totale Patrimonio Netto             €4,272,124  ← CORRECT!
```

**Before fix:** €1,130,111 (€3.14M missing)
**After fix:** €4,272,124 ✓

## How It Works Now

For `sp12_riserve` with `accumulate_all: true`:

1. **Try detail_tags FIRST** (accumulate all matches)
   - PatrimonioNettoRiservaLegale → €19,365
   - PatrimonioNettoRiservaSoprapprezzoAzioni → €3,180,324
   - PatrimonioNettoAltreRiserve... → €30,222
   - PatrimonioNettoUtiliPerditePortatiNuovo → -€68,533
   - **Sum = €3,161,378** ✓

2. **If detail_tags found values → DONE**
   - Mark field as mapped by v2
   - V1 fallback will skip this field

3. **Only if detail_tags find nothing → try priorities**
   - priority_1, priority_2, etc.

## Benefits

1. ✅ **Complete data capture**: All reserve types accumulated
2. ✅ **Correct totals**: Patrimonio Netto = €4,272,124
3. ✅ **No v1 interference**: v2-mapped fields protected
4. ✅ **Tag variation handling**: Multiple tag names supported
5. ✅ **Backward compatible**: Non-accumulate fields still work

## Testing

Run the test suite:

```bash
source .venv/bin/activate

# Test reserves accumulation fix
python test_reserves_fix.py

# Debug reserves extraction
python debug_reserves.py

# Full priority mapping tests
python test_priority_mapping.py
```

All tests should pass:
```
✅ PASS: Reserves Accumulation Test
✅ PASS: Full XBRL Import Test

🎉 All tests passed! Reserves fix working correctly.
```

## Conclusion

The reserves accumulation issue is **completely fixed**:

- ✅ All reserve types are accumulated (not just first match)
- ✅ V1 fallback doesn't interfere with v2 mappings
- ✅ Tag variations handled correctly
- ✅ Patrimonio Netto totals match XBRL exactly
- ✅ No breaking changes to other fields

**Balance sheet equity section now imports correctly!**
