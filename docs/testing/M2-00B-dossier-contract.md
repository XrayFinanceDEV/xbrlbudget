# M2-00B — Contratto e assembler del dossier

## Delivered behavior

`GET /api/v1/companies/{company_id}/scenarios/{scenario_id}/final-report`
continues to return v1. Add `?schema_version=2` for the dossier. Unsupported
versions return 422; a v2 request with no declared budget horizon returns 409.
Authentication and ownership checks remain shared with v1, including tenant-safe
404 responses for foreign scenarios and transitive source pointers.

The dossier adds a neutral document title, complete ordered CE/SP/cashflow,
explicit row hierarchies, periods and unavailable reasons, the practice and
analytical indicator catalogs and additional homogeneous-unit graph series.
Presentation amounts are in thousands of euros by default, while every monetary
model value remains an exact euro decimal string. Analytical percentage fractions
are converted to percentage points on the server.

Practice and analytical conventions remain distinct. Practice DSCR is explicitly
a proxy; analytical ROS uses net profit, whereas practice ROS uses EBIT. Practice
current assets exclude long receivables and include active accruals; analytical
current assets follow the existing model. Both use canonical CE results. Backend
practice calculation replaces the older frontend-only formula for v2, including
canonical detail-first financial value adjustments. No ratings or thresholds are
invented. Flows keep their declared duration and are not silently annualized.

Unallocated aggregate families use the legal hierarchy to mark zero default
details as unavailable. Nonzero details remain visible; fully reconciled zero
families remain zero. This is an availability rule based on reconciliation, not a
claim that legacy imports store per-field provenance. Infrannual observed,
adjusted and closing periods remain distinct, including missing pre-adjustment
snapshots. Closing values use the persisted source projection when available;
metrics computed for a different promoted annual record are not attached to it.

The planner and page-note contracts are defined, with economic and editorial
hashes separated. Assembly returns `editorial_plan: null`, no page notes and
`editorial_readiness.status: pending`. M2-02A/M2-00C implement pagination,
text metrics and page comments. This stage does not produce the final PDF or
claim that the Typst spike's independent technical gate has passed.

## Validation

Validated on 2026-09-15: **116 backend tests passed**, **24 frontend tests
passed**, TypeScript `--noEmit` passed and catalog synchronization passed.
The frontend run also includes API getter, report action and adapter regressions.
Bounded contract/catalog review was performed by Terra; identified hierarchy,
unavailability and getter gaps were resolved before integration.

Python uses the existing backend virtual environment. Run from the repository:

```bash
PYTHONPATH=.:backend python -m pytest tests/test_final_report_v2.py tests/test_analysis_exact_decimals.py tests/test_final_report_contract.py tests/test_final_report_endpoint.py tests/test_final_report_narrative.py tests/test_m1_05a_final_report_domain.py -q
cd frontend
npm test -- lib/final-report-v2-contract.test.ts lib/final-report-contract.test.ts
npx tsc --noEmit --incremental false
```

The new tests cover the three workflows at one, three and five years, exact
Decimal serialization including positive exponents, null/zero/negative values,
canonical CE netting, complete catalog row occurrences, cashflow parity, source
closing provenance, version negotiation, tenant safety, auth and read-only hash
stability. Exact analysis mode is additionally tested for exception reset and
concurrent request isolation; legacy analysis output remains compatible.

The catalog is exported from the existing frontend catalogs, with financial
parentage made explicit in the exporter. Regenerate after a catalog change:

```bash
node tools/final_report/export_catalog.cjs
node tools/final_report/export_catalog.cjs --check
```

Requires the project's declared frontend TypeScript dependency to be installed.
The frontend contract suite runs the synchronization check. V1 fixtures are not
regenerated as v2; dedicated synthetic v2 fixtures live alongside them.
