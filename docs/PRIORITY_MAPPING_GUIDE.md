# Priority-Based XBRL Mapping - User Guide

## Overview

The XBRL import system now uses a **priority-based mapping approach** that automatically tries multiple tag variations before falling back to aggregates. This makes imports more robust across different XBRL file types.

## Why Priority-Based Mapping?

### The Problem

Italian XBRL files vary significantly:

**Same field, different tags:**
```
Company A (2018 taxonomy, detailed):
  itcc-ci:TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteEntroEsercizio

Company B (2014 taxonomy, generic):
  itcc-ci:CreditiEsigibiliEntroEsercizioSuccessivo

Company C (2011 taxonomy, versioned):
  itcc-ci-2011-01-04:CreditiEsigibiliEntroEsSucc
```

**Old approach:** Map only one tag → fails for other files

**New approach:** Try all variations in priority order → works for all files

## How It Works

### Priority System

For each database field (e.g., `sp06_crediti_breve`), the system tries tags in this order:

```
1. priority_1 → Most specific/preferred tag
   ↓ (if not found)
2. priority_2 → Generic aggregate tag
   ↓ (if not found)
3. priority_3 → Versioned specific tag
   ↓ (if not found)
4. priority_4/5 → Additional variations
   ↓ (if not found)
5. detail_tags → Sum all detail items
   ↓ (if not found)
6. V1 fallback → Old mapping system
   ↓ (if not found)
7. Reconciliation → Use TotaleCrediti/TotaleDebiti aggregate
```

**First match wins!** Once a value is found, lower priorities are ignored.

### Example: Importing Credits

**XBRL File A** (detailed split):
```xml
<itcc-ci:TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteEntroEsercizio>
  2688056
</itcc-ci:TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteEntroEsercizio>
```
✅ **Matches priority_1** → Uses €2,688,056

---

**XBRL File B** (generic aggregate):
```xml
<itcc-ci:CreditiEsigibiliEntroEsercizioSuccessivo>
  3500000
</itcc-ci:CreditiEsigibiliEntroEsercizioSuccessivo>
```
❌ priority_1 not found
✅ **Matches priority_2** → Uses €3,500,000

---

**XBRL File C** (detail items only):
```xml
<itcc-ci:CreditiVersoClientiEsigibiliEntroEsercizioSuccessivo>2000000</...>
<itcc-ci:CreditiCreditiTributariEsigibiliEntroEsercizioSuccessivo>500000</...>
<itcc-ci:CreditiVersoAltriEsigibiliEntroEsercizioSuccessivo>800000</...>
```
❌ priority_1 not found
❌ priority_2 not found
❌ priority_3 not found
✅ **Matches detail_tags** → Sums €2M + €0.5M + €0.8M = €3.3M

---

**XBRL File D** (only total aggregate):
```xml
<itcc-ci:TotaleCrediti>4450986</itcc-ci:TotaleCrediti>
```
❌ priority_1 not found
❌ priority_2 not found
❌ priority_3 not found
❌ detail_tags not found
✅ **Reconciliation adds difference** → Uses €4,450,986 (all goes to short-term)

## Priority Mapping Structure

### Balance Sheet Example

```json
{
  "sp06_crediti_breve": {
    "comment": "Short-term credits - prefer detailed split tags",
    "priority_1": "itcc-ci:TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteEntroEsercizio",
    "priority_2": "itcc-ci:CreditiEsigibiliEntroEsercizioSuccessivo",
    "priority_3": "itcc-ci-2018-11-04:CreditiEsigibiliEntroEsSucc",
    "priority_4": "itcc-ci:CreditiImposteAnticipateTotaleImposteAnticipate",
    "detail_tags": [
      "itcc-ci:CreditiVersoClientiEsigibiliEntroEsercizioSuccessivo",
      "itcc-ci:CreditiCreditiTributariEsigibiliEntroEsercizioSuccessivo",
      "itcc-ci:CreditiVersoAltriEsigibiliEntroEsercizioSuccessivo"
    ]
  }
}
```

### Income Statement Example

```json
{
  "ce02_variazioni_rimanenze": {
    "comment": "Multiple variations exist across taxonomies",
    "priority_1": "itcc-ci:ValoreProduzioneVariazioniRimanenze",
    "priority_2": "itcc-ci-2018-11-04:VariazioniRimanenze",
    "priority_3": "itcc-ci:VariazioniRimanenze",
    "priority_4": "itcc-ci:ValoreProduzioneVariazioniRimanenzeProdottiCorsoLavorazioneSemilavoratiFiniti"
  }
}
```

## Import Results

When you import an XBRL file, the result includes `priority_matches`:

```python
result = import_xbrl_file_enhanced("company.xbrl")

# See which tags were used
for field, tag in result['reconciliation_info'][2024]['priority_matches'].items():
    print(f"{field} → {tag}")
```

**Example output:**
```
sp06_crediti_breve → itcc-ci:TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteEntroEsercizio
sp07_crediti_lungo → itcc-ci:TotaleCreditiIscrittiAttivoCircolanteQuotaScadenteOltreEsercizio
sp05_rimanenze → itcc-ci:TotaleRimanenze
sp09_disponibilita_liquide → itcc-ci:TotaleDisponibilitaLiquide
...
```

This tells you exactly which priority level was matched for each field.

## Adding New Priority Mappings

If you encounter a new XBRL tag that isn't being imported, you can add it to the priority list:

### Step 1: Find the XBRL tag

Look in the XBRL file for tags that aren't being imported:

```xml
<itcc-ci:NewTagName>12345</itcc-ci:NewTagName>
```

### Step 2: Determine which field it maps to

Check which balance sheet or income statement field this should go to (sp01-sp18 or ce01-ce20).

### Step 3: Add to taxonomy_mapping_v2.json

Edit `/data/taxonomy_mapping_v2.json`:

```json
{
  "sp06_crediti_breve": {
    "priority_1": "...",
    "priority_2": "...",
    "priority_3": "...",
    "priority_4": "...",
    "priority_5": "itcc-ci:NewTagName"  // ADD HERE
  }
}
```

### Step 4: Sync to backend

```bash
cp data/taxonomy_mapping_v2.json backend/data/taxonomy_mapping_v2.json
```

### Step 5: Test

```bash
python test_priority_mapping.py
```

## Backward Compatibility

**Don't worry about breaking existing imports!**

The system maintains full backward compatibility:

1. **V2 mappings tried first** (priority-based)
2. **V1 mappings used as fallback** (old simple mappings)
3. **Reconciliation ensures completeness** (aggregate totals)

If a tag was working before, it will still work now.

## Best Practices

### Priority Order Guidelines

When adding new priorities, follow this order:

1. **priority_1**: Most specific aggregate (with maturity split, with type breakdown)
2. **priority_2**: Generic aggregate (TotaleXXX without details)
3. **priority_3**: Latest versioned tag (2018-11-04)
4. **priority_4**: Older versioned tags (2017, 2016, 2015, etc.)
5. **priority_5**: Edge cases or rare variations
6. **detail_tags**: Individual line items to sum

### When to Use detail_tags

Use `detail_tags` when:
- The field is a sum of multiple sub-items
- Some files have aggregates, others only have details
- You want to accumulate all matching items

**Example:**
```json
{
  "sp06_crediti_breve": {
    "priority_1": "itcc-ci:TotaleCreditiEntroEsercizio",  // Preferred
    "detail_tags": [  // Fallback if no aggregate
      "itcc-ci:CreditiVersoClientiEntro...",
      "itcc-ci:CreditiTributariEntro...",
      "itcc-ci:CreditiVersoAltriEntro..."
    ]
  }
}
```

## Troubleshooting

### Problem: Field showing €0 after import

**Diagnosis:**
```python
result = import_xbrl_file_enhanced("problem.xbrl")
print(result['reconciliation_info'][2024]['priority_matches'])
```

If the field is missing from `priority_matches`, none of the priority tags were found.

**Solution:**
1. Open the XBRL file in a text editor
2. Search for the field value (e.g., search for "2688056" to find credits)
3. Find the tag name used in this file
4. Add it to the appropriate priority level in `taxonomy_mapping_v2.json`

### Problem: Value seems doubled

**Diagnosis:** Both an aggregate and detail tags were matched, causing double-counting.

**Solution:** The parser should skip aggregate tags (in `AGGREGATE_TAGS`). If doubling occurs:
1. Check if the aggregate tag is in `AGGREGATE_TAGS` constant
2. Add it if missing
3. Or adjust priorities to prefer aggregates over details

### Problem: Import failed with error

**Check these:**
1. Is `/data/taxonomy_mapping_v2.json` present?
2. Is the JSON valid? (no syntax errors)
3. Are all priority keys named correctly? (priority_1, priority_2, not priority1)

## Testing

Run comprehensive tests:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run priority mapping tests
python test_priority_mapping.py

# Expected output:
# ✓ PASS: Structure Test
# ✓ PASS: Priority Extraction Test
# ✓ PASS: XBRL Import Test
# ✓ PASS: V1 Fallback Test
# Total: 4/4 tests passed
```

## Summary

✅ **Automatic**: Tries multiple tag variations without manual intervention
✅ **Robust**: Works across taxonomy versions (2011-2018) and schema types
✅ **Compatible**: Backward compatible with old mappings
✅ **Transparent**: Shows which tags were matched via `priority_matches`
✅ **Complete**: Still uses aggregate reconciliation to ensure 100% data capture

**Result:** XBRL imports "just work" regardless of source, year, or schema type!
