# XBRL Taxonomy Mapping Refactoring Plan

## Current Problem
We're overfitting to specific XBRL file tag structures. Our mappings work for the current file but may break with other companies/years.

## VBA Aggregate Approach
The VBA project uses:
1. **Aggregate totals first** (TotaleValoreProduzione, TotaleCostiProduzione, etc.)
2. **Detail items as fallback** only if aggregates don't exist
3. **Reconciliation logic** to verify detail sums match aggregates

## Proposed Solution

### Phase 1: Add Priority-Based Mapping (Quick Fix)
Keep current mappings but organize by priority:

```json
{
  "ce02_variazioni_rimanenze": {
    "priority_1": "itcc-ci:ValoreProduzioneVariazioniRimanenze",
    "priority_2": "itcc-ci:VariazioniRimanenze", 
    "priority_3": "itcc-ci:ValoreProduzioneVariazioniRimanenzeProdottiCorsoLavorazioneSemilavoratiFiniti"
  }
}
```

Parser tries priority_1 first, then priority_2, etc.

### Phase 2: Use Aggregate Totals with Reconciliation
Map aggregate totals for income statement:

```python
AGGREGATE_TAGS_INCOME = {
    'TotaleValoreProduzione': 'total_production_value',
    'TotaleCostiProduzione': 'total_production_costs',
    'DifferenzaValoreCostiProduzione': 'ebit_calculated',
    'TotaleProventiOneriFinanziari': 'total_financial_result',
    'RisultatoPrimaImposte': 'profit_before_tax_calculated',
    'UtilePerditaEsercizio': 'net_profit_calculated'
}
```

Then reconcile:
- If ce01 + ce02 + ce03 + ce04 ≠ TotaleValoreProduzione → adjust or warn
- If ce05 + ce06 + ... ≠ TotaleCostiProduzione → adjust or warn

### Phase 3: Test with Multiple XBRL Files
Test with:
1. Different companies
2. Different years (2011-2024 taxonomies)
3. Different schema types (Ordinario/Abbreviato/Micro)

## Immediate Action
For now, document which mappings are:
- ✅ **Generic** (work across all XBRL files)
- ⚠️ **Specific** (may only work with certain file structures)
- 🔄 **Should use aggregate fallback**

## Files to Check
Test our mappings with these XBRL taxonomy versions:
- 2011-01-04
- 2014-11-17
- 2015-12-14
- 2016-11-14
- 2017-07-06
- 2018-11-04

Each version may have different tag hierarchies.
