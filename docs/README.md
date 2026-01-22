# XBRL Budget - Documentation

This directory contains technical documentation for the XBRL Budget application, with a focus on the hierarchical debt mapping implementation and cashflow calculation fixes.

## 📚 Documentation Index

### Current Implementation (Latest)

1. **[HIERARCHICAL_DEBT_IMPLEMENTATION_COMPLETE.md](./HIERARCHICAL_DEBT_IMPLEMENTATION_COMPLETE.md)** ⭐
   - **Status:** COMPLETE - Ready for cashflow calculator update
   - Complete implementation guide for hierarchical debt and depreciation mapping
   - Database schema changes
   - XBRL parser updates
   - Migration instructions
   - Next steps for cashflow calculator integration

2. **[CASHFLOW_ISSUES_ANALYSIS.md](./CASHFLOW_ISSUES_ANALYSIS.md)** ⭐
   - **Critical Analysis:** Root cause of cashflow calculation errors
   - Detailed breakdown of 6 major issues causing cashflow discrepancies
   - Issue #4: DOUBLE-COUNTING of short-term debt (most critical)
   - Fix priority and action plan
   - Testing checklist

### Implementation History

3. **[XBRL_IMPORT_FIXES_SUMMARY.md](./XBRL_IMPORT_FIXES_SUMMARY.md)**
   - Summary of XBRL import improvements over time
   - Taxonomy mapping enhancements
   - Priority-based extraction logic

4. **[XBRL_IMPORT_ANALYSIS.md](./XBRL_IMPORT_ANALYSIS.md)**
   - Analysis of XBRL structure and extraction challenges
   - Taxonomy version handling
   - Context detection

5. **[XBRL_AGGREGATE_FALLBACK_EXPLANATION.md](./XBRL_AGGREGATE_FALLBACK_EXPLANATION.md)**
   - How the parser handles missing detail fields
   - Fallback to aggregate values
   - Priority system explanation

### Historical Fixes

6. **[CASHFLOW_FIX_COMPLETE.md](./CASHFLOW_FIX_COMPLETE.md)**
   - Earlier cashflow fix attempt (before hierarchical approach)

7. **[CASHFLOW_COMPREHENSIVE_FIX.md](./CASHFLOW_COMPREHENSIVE_FIX.md)**
   - Comprehensive analysis of cashflow methodology

8. **[CASHFLOW_FINAL_FIX.md](./CASHFLOW_FINAL_FIX.md)**
   - Final fix attempt (superseded by hierarchical implementation)

9. **[DOUBLE_COUNTING_FIX_VERIFICATION.md](./DOUBLE_COUNTING_FIX_VERIFICATION.md)**
   - Verification of double-counting issue

10. **[FIX_VERIFICATION_SUCCESS.md](./FIX_VERIFICATION_SUCCESS.md)**
    - Success metrics for previous fixes

11. **[IMPOSTE_FIX_COMPLETE.md](./IMPOSTE_FIX_COMPLETE.md)**
    - Tax (imposte) field extraction fix

12. **[RESERVES_FIX_COMPLETE.md](./RESERVES_FIX_COMPLETE.md)**
    - Reserves field mapping fix

### Technical Guides

13. **[TAXONOMY_REFACTORING_PLAN.md](./TAXONOMY_REFACTORING_PLAN.md)**
    - Plan for refactoring taxonomy mapping system

14. **[PRIORITY_MAPPING_GUIDE.md](./PRIORITY_MAPPING_GUIDE.md)**
    - How priority-based mapping works
    - Detail vs aggregate handling

15. **[VBA_AGGREGATE_APPROACH.md](./VBA_AGGREGATE_APPROACH.md)**
    - Comparison with VBA Excel approach
    - Why aggregates are used in Excel model

16. **[PHASE1_IMPLEMENTATION_COMPLETE.md](./PHASE1_IMPLEMENTATION_COMPLETE.md)**
    - Phase 1 implementation milestone

## 🎯 Quick Start Guide

### Understanding the Cashflow Issue

1. **Start here:** [CASHFLOW_ISSUES_ANALYSIS.md](./CASHFLOW_ISSUES_ANALYSIS.md)
   - Understand the 6 issues causing incorrect cashflow
   - Focus on Issue #4: DOUBLE-COUNTING

2. **Then read:** [HIERARCHICAL_DEBT_IMPLEMENTATION_COMPLETE.md](./HIERARCHICAL_DEBT_IMPLEMENTATION_COMPLETE.md)
   - See how the hierarchical approach solves the problem
   - Implementation details and next steps

### For Developers

**If you need to:**
- **Fix cashflow calculations** → Start with [HIERARCHICAL_DEBT_IMPLEMENTATION_COMPLETE.md](./HIERARCHICAL_DEBT_IMPLEMENTATION_COMPLETE.md)
- **Understand XBRL import** → Read [XBRL_IMPORT_ANALYSIS.md](./XBRL_IMPORT_ANALYSIS.md)
- **Debug taxonomy mapping** → See [PRIORITY_MAPPING_GUIDE.md](./PRIORITY_MAPPING_GUIDE.md)
- **Add new XBRL fields** → Follow [XBRL_IMPORT_FIXES_SUMMARY.md](./XBRL_IMPORT_FIXES_SUMMARY.md)

## 🔧 Implementation Status

### ✅ Completed
- [x] Database schema updated with hierarchical debt fields
- [x] Taxonomy mapping enhanced with detail field mappings
- [x] XBRL parser updated to extract and aggregate detail fields
- [x] Migration scripts created and executed
- [x] Depreciation split implementation (intangible vs tangible)
- [x] Both databases migrated successfully

### ⏳ In Progress
- [ ] Cashflow calculator update to use new hierarchical fields
- [ ] Re-import XBRL data to populate new fields
- [ ] Test complete cashflow calculation
- [ ] Verify against correct Excel output

### 📋 Next Steps
1. Update `backend/app/calculations/cashflow_detailed.py`:
   - Use `operating_debt_short` for working capital
   - Use `financial_debt_total` for financing
   - Use `ce09a/ce09b` for depreciation split
2. Re-import ISTANZA02353550391.xbrl
3. Run `debug_cashflow_detailed.py` to verify
4. Compare results with correct Excel output

## 🎓 Key Concepts

### Hierarchical Debt Mapping

**Problem:**
- Italian GAAP balance sheets aggregate all short-term debts (sp16) into one line
- This includes BOTH financial debts (bank loans) AND operating debts (suppliers, taxes)
- Original cashflow was using sp16 in BOTH working capital AND financing sections
- Result: **DOUBLE-COUNTING** of short-term debt changes

**Solution:**
- Extract detailed debt breakdown from XBRL:
  - **Financial debts:** Banks, bonds, other financial loans
  - **Operating debts:** Suppliers, taxes, social security
- Use financial debts in **Financing Section** only
- Use operating debts in **Working Capital Section** only
- Each debt type counted **once** in correct section ✓

### Depreciation Split

**Problem:**
- Total depreciation (ce09) includes both tangible and intangible
- Investing cashflow needs separate CAPEX for each asset type
- Original calculation estimated split based on asset proportions

**Solution:**
- Extract actual depreciation split from XBRL:
  - `ce09a_ammort_immateriali` - Intangible depreciation
  - `ce09b_ammort_materiali` - Tangible depreciation
- Use actual values when available
- Fallback to estimation if XBRL doesn't provide split

## 📊 Expected Results

After implementing the hierarchical approach, cashflow for 2024 should match:

| Section | Calculated (Wrong) | Expected (Correct) | Status |
|---------|-------------------|-------------------|--------|
| Operating CF | 6.674.706 € | 6.590.447 € | ⏳ Pending update |
| Investing CF | -6.782.084 € | -6.787.084 € | ⏳ Pending update |
| Financing CF | 236.732 € | -421.157 € | ⏳ Pending update |
| **Total CF** | **129.354 €** | **-617.794 €** | ⏳ Pending update |

## 🔗 Related Files

### Code Files
- `database/models.py` - Database schema with hierarchical fields
- `data/taxonomy_mapping.json` - Enhanced taxonomy mappings
- `importers/xbrl_parser.py` - Updated XBRL parser
- `backend/app/calculations/cashflow_detailed.py` - Cashflow calculator (needs update)

### Migration Scripts
- `migrate_hierarchical_debts.py` - Adds new fields to database

### Test Scripts
- `test_hierarchical_import.py` - Tests XBRL import with hierarchical fields
- `debug_cashflow_detailed.py` - Tests cashflow calculation

## 📝 Contributing

When adding new documentation:
1. Use clear, descriptive filenames
2. Add entry to this README
3. Include implementation status (✅ Complete, ⏳ Pending, ❌ Blocked)
4. Link related files and dependencies

## 📧 Support

For questions about the implementation:
- Review [CASHFLOW_ISSUES_ANALYSIS.md](./CASHFLOW_ISSUES_ANALYSIS.md) for problem context
- Review [HIERARCHICAL_DEBT_IMPLEMENTATION_COMPLETE.md](./HIERARCHICAL_DEBT_IMPLEMENTATION_COMPLETE.md) for solution details
- Check code comments in modified files

---

**Last Updated:** 2026-01-21
**Current Phase:** Ready for cashflow calculator integration
