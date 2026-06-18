# Archived documentation

These documents are **superseded or historical**. They are kept for provenance
only and are **not maintained** — their claims may no longer match the code.
For current behaviour use the authoritative sources listed in
[`../README.md`](../README.md) (root `CLAUDE.md` and `IMPORT-OVERVIEW.md`).

| Archived document | What it was | Replaced by |
|-------------------|-------------|-------------|
| `IV-CEE-PDF-IMPORT.md` | Early PDF-extraction architecture sketch (Docling, async/Celery patterns — not the stack that shipped). | `IMPORT-OVERVIEW.md` |
| `IV-CEE-PDF-IMPORT2.md` | KPS worked-example walkthrough. | `IMPORT-OVERVIEW.md` |
| `SIMPLIFIED-API.md` | Proposal to collapse 25+ endpoints to ~7. | `CLAUDE.md` § Simplified API Design |
| `TEST_BUDGET_API.md` | Old granular per-year assumption/forecast CRUD endpoints. | `CLAUDE.md` (bulk assumptions workflow) |
| `SCHEMA_ENHANCEMENTS.md` | Planned BS/IS detail fields (several never implemented). | `CLAUDE.md` § Database Schema + `TASSONOMIA.md` |
| `XBRL_PCI_IV_CEE_Mapping.md` | Long-form XBRL PCI → IV-CEE element mapping. | `data/taxonomy_mapping.json` + `xbrl_parser_enhanced.py` + `TASSONOMIA.md` |
| `PRIORITY_MAPPING_GUIDE.md` | XBRL priority-based tag fallback chain. | `IMPORT-OVERVIEW.md` (reconciliation) |
| `VBA_AGGREGATE_APPROACH.md` | Why aggregate XBRL totals are preferred. | `IMPORT-OVERVIEW.md` § IV-CEE engine |
| `XBRL_AGGREGATE_FALLBACK_EXPLANATION.md` | Detailed-split vs aggregate-only XBRL structures. | `IMPORT-OVERVIEW.md` § IV-CEE engine |
| `TAXONOMY_REFACTORING_PLAN.md` | Multi-phase XBRL mapping overhaul plan (now done). | (completed — see `xbrl_parser_enhanced.py`) |
| `REIMPORT_INSTRUCTIONS.md` | One-off test instructions with stale paths. | `CLAUDE.md` § Running |
| `DEPLOYMENT_SUMMARY.md` | Dated deployment checklist (referenced files no longer exist). | `README.md` + `IFRAME_INTEGRATION.md` |
| `PDF-IMPORT-STATUS-2026-06-11.md` | Dated status snapshot of import fixes. | (snapshot — superseded by `IMPORT-OVERVIEW.md`) |
| `CHANGELOG-unreleased.md` | Dated work-in-progress changelog. | (snapshot — superseded by `IMPORT-OVERVIEW.md`) |
