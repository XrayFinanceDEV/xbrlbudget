# Uncommitted Changes — Audit

Snapshot of all modifications on `main` not yet committed. Grouped by feature, with per-file edits, rationale, and any follow-up notes.

Scope: 20 modified files, ~1058 insertions / 202 deletions across backend, frontend, importers, and shared modules.

---

## 1. AGO/ERP Trial Balance Parser

**Problem**: `docs/debug2/0_Infra 30.09 elab febb. 2026.pdf` was detected as `Situazione Contabile` but the existing DEPI regex (`XX/YY/ZZZ`) doesn't match AGO's 8-digit codes (`13065000`). Result: zero extraction, balanced but empty BS.

**Fix**: Add a second parser inside the same file, routed by format detection.

### Files
- `importers/situazione_contabile_parser.py` (+399 / −17)
  - New `is_ago_format()` — detects 8-digit codes + `BILANCIO DI VERIFIC` marker
  - New `parse_entries_ago(file_path)` — block-based 2-column reader via pymupdf
  - New `_semantic_section_from_desc()` and `_any_rule_matches()` — keyword-based column classification (no code-prefix logic)
  - `extract_situazione_contabile()` now routes AGO → `parse_entries_ago`, else → `parse_entries` (DEPI)
  - Extended keyword rules in `_SP_ATTIVO_RULES`, `_SP_PASSIVO_RULES`, `_CE_COSTI_RULES` for AGO-common descriptions (Oneri pluriennali, F.do amm, Quote TFR, Salari, etc.)
  - Removed false-positive rule `(['CREDITI','CLIENT'], 'sp16')` — was flipping plain "Crediti v/clienti" to passivo
  - Added ce08 sub-field handling: `SALARI/STIPENDI` → ce08b, `ONERI SOCIAL` → ce08c, `QUOTE FINE RAPPORTO` → ce08a_tfr (accumulates into ce_tfr_accrual + ce['ce08'])
  - Added (EE)/(OE) suffix routing: `Debiti verso banche (EE)` → sp16, `(OE)` → sp17, plus same for all generic sp16 debts → sp17 when `(OE)`/`OLTRE` present
  - Equity: level-1 entries with `UTILE/PERDITA ESERCIZ` are skipped (handled by synthetic level-4) unless `PORTATI/PRECEDENT/NUOVO` → riserve
  - Utile synthesis: computed from our own classified entries (`sum_ricavi − sum_costi`), not from the PDF's declared TOTALE labels (whose column pairing is unreliable in rotated landscape layouts)

### Validation
Balance on target file: `totale_attivo = totale_passivo = 259,369.16` (diff 0.00). DEPI SC files (`0530edc5-*.pdf`, `806322ed-*.pdf`) still balance — no regression.

### Follow-up
None — parser is self-contained. If AGO files with different structural quirks appear, extend `_SP_*_RULES` / `_CE_*_RULES`.

---

## 2. Creditor & Debtor-Type Detail Breakdown (sp16a-g / sp17a-g / sp06a-g / sp07a-g)

**Problem**: BS detail for debts by creditor-type (banche, fornitori, tributari, etc.) and credits by debtor-type (clienti, controllate, tributari, etc.) was only populated when XBRL publishes per-type Entro/Oltre tags. Many bilanci — especially the comparative prior year — only publish per-group `Totale*` tags without the entro/oltre split. This left sp16x/sp17x and sp06x/sp07x empty for prior years. LLM extraction also lacked the breakdown fields.

**Fix**: Two-layer breakdown — extract explicit detail when available, fall back to group totals + aggregate redistribution when not.

### Files
- `importers/xbrl_parser_enhanced.py` (+161 / 0)
  - New `CREDITOR_TOTAL_TAGS` dict (10 creditor-group `DebitiDebitiVerso*Totale*` XBRL tags → bucket)
  - New `CREDITOR_FIELDS` dict (bucket → `(sp16x, sp17x)` field names)
  - New `CREDIT_TOTAL_TAGS` dict (7 debtor-group `Crediti*Totale*` tags → bucket). Note: tag naming is inconsistent — items named "Crediti X" get doubled prefix `CreditiCredit*`; items named "Verso X" get `CreditiVerso*`
  - New `CREDIT_FIELDS` dict (bucket → `(sp06x, sp07x)`)
  - Pass 3b (post-map, pre-reconcile): when per-creditor Entro/Oltre tags are absent AND group `Totale*` tags are present, seed sp16x_breve from each creditor's total, then redistribute the overall sp17 aggregate into sp17x by priority `[banche, altri_finanz, obbligazioni, fornitori, altri, tributari, previdenza]`
  - Pass 3c: same fallback for C.II Crediti. Priority for sp07 redistribution: `[clienti, altri, tributari, imposte_anticipate, controllate, collegate, controllanti]`
  - Both fallbacks record adjustments in `reconciliation_info.reconciliation_adjustments` as `debt_creditor_fallback` / `credit_debtor_fallback` entries (shape differs from other adjustments — see schema change below)

- `importers/pdf_extractor_llm.py` (+204 / −2)
  - `BalanceSheetExtraction` pydantic model: +14 new fields (sp06a–g, sp07a–g) and +14 more (sp16a–g, sp17a–g) — each with OIC art. 2424 reference in description
  - +2 validation fields: `totale_crediti`, `totale_debiti` (the explicit PDF totals, used for consistency checks)
  - LLM prompt: added two ~15-line sections — "CREDITI — DEBTOR-TYPE BREAKDOWN" and "DEBITI — CREDITOR-TYPE BREAKDOWN" — with CRITICAL rules that sub-fields MUST sum to parent aggregate. Prompt in both the single-year and dual-year extraction flows
  - "If PDF shows only Totale without breakdown → put everything in `*g_*altri*`" — directs the model to avoid inventing sub-totals

- `importers/pdf_importer.py` (+42 / −28)
  - `_create_balance_sheet`: all 28 new sub-fields now populated from `data` dict (previously hard-coded to 0)
  - `_validate_debiti`: new explicit path — when LLM populated `totale_debiti`, use it directly instead of inferring from `totale_passivo − (equity + fondi + tfr + ratei)`. Fallback to inferred path only when missing. Reordered validation: `crediti → debiti → equity` (equity now relies on corrected debt aggregate)
  - `_validate_crediti`: added reconciliation loop that plugs residual `(sp06_agg − sum(sp06a..g))` into `sp06g_crediti_altri_breve` (same for sp07) so detail always matches parent aggregate and the Rettifiche journal has a meaningful starting point

- `data/taxonomy_mapping_v2.json` (+8 / −13)
  - Removed `priority_2` (group total) fallbacks from `sp16d/e/f/g` — those fallbacks are now handled by the new `CREDITOR_TOTAL_TAGS` dispatch in `xbrl_parser_enhanced.py` with proper entro/oltre redistribution. Leaving them in the mapping would have caused double-counting.

- `backend/app/schemas/imports.py` (+4 / −1)
  - `ReconciliationInfo.reconciliation_adjustments` type relaxed from `Dict[str, ReconciliationAdjustment]` to `Dict[str, Dict[str, Any]]` — now holds heterogeneous shapes (old `{field, original, adjusted, delta}` AND new `{source, sp17_distributed, sp17_unallocated}`)

### Validation
No new test script, but the new fields flow through to all downstream views (Rettifiche, Confronto, `/forecast/balance`, `/forecast/income`) which were already updated for the shared BS/IS layout (pre-existing work).

### Follow-up
- If the redistribution priority doesn't match a specific sector's typical balance sheet, users will see long-term debt/credit landing in the wrong bucket. Currently no UI signal to flag this — consider surfacing `debt_creditor_fallback.sp17_unallocated` in the Rettifiche tab when > 0.
- The pydantic field explosion (+28 fields) makes the LLM prompt noticeably longer — expect slight cost/latency increase on PDF import.

---

## 3. Report AI Comments — Overall Section + Editable Persistence

**Problem**: Report had 10 per-section AI comments but no overall executive summary. Also, generated comments were read-only — the user couldn't tweak them before printing.

**Fix**: Add an 11th "overall" comment + editable textarea on the cover + new PUT endpoint to persist user edits.

### Files
- `database/models.py` (+1)
  - `BudgetScenario.ai_comment_overall = Column(Text, nullable=True)`
- `migrate_db.py` (+1)
  - Migration entry for `ai_comment_overall TEXT` on `budget_scenarios`
- `backend/app/services/ai_comments_service.py` (+14 / −9)
  - `ReportComments` pydantic model: added `overall_comment` field (3-5 sentences, vs 2-4 for the others)
  - Updated system prompt to "11 commenti" and tool description
  - `_COMMENT_FIELDS` mapping: prepended `("overall_comment", "ai_comment_overall")`
  - Docstring updated
- `backend/app/api/v1/reports.py` (+24 / −1)
  - New `PUT /companies/{id}/scenarios/{sid}/report/ai-comments` — accepts a `Dict[str, Optional[str]]`, validates ownership, calls `save_comments`, returns the persisted dict. No LLM call.
- `frontend/lib/api.ts` (+13 / 0)
  - `ReportAICommentsResponse.overall_comment?: string`
  - New `saveReportAIComments(companyId, scenarioId, comments)` helper
- `frontend/app/report/page.tsx` (+52 / −19)
  - Imports `saveReportAIComments`, `Textarea`, `cn`
  - `handleCommentChange()` and `handleCommentBlur()` — on-blur persistence
  - New editable block between `ReportCover` and `ReportDashboard`: `Textarea` with skeleton loading, print-only `<p>` fallback (textarea is hidden in print), `print:hidden` on the whole block when empty
  - Removed per-section `print:break-before-page` wrappers; replaced with `report-section` class (see Print CSS below)
- `frontend/components/report/report-ai-comment.tsx` (+2 / −2)
  - Added `report-ai-comment` class to both loading and normal card variants (used by print CSS to keep comments with their section)

### Validation
Manual — no tests added. Toggling "Commenti AI" button on `/report` now generates 11 comments; editing any textarea persists on blur.

### Follow-up
- User edits to non-`overall_comment` textareas (the per-section ones) still go through the per-section `ReportAIComment` component which is currently read-only. If inline editing is wanted there too, wire up the same blur handler pattern.

---

## 4. Posizione Finanziaria Netta (PFN) Chart & Metric

**Problem**: `/forecast/balance` showed CCN trend but no PFN, which is a primary lender/rating metric. Also only one chart visible on the main row (Attività line chart) while there was space.

**Fix**: Add a PFN bar chart alongside the existing CCN line chart, plus a PFN row in the per-year metrics table.

### Files
- `frontend/app/forecast/balance/page.tsx` (+90 / −30)
  - New `pfnChartConfig` (single series, chart-1 color)
  - New `computePFN(bs)` helper with 3-tier fallback:
    1. Detail present (sp16a/sp17a/sp16c/sp17c banks + bonds) → `bankDebt − cash − financialAssets`
    2. Partial detail (non-bank groups populated) → `(totalDebt − knownNonBankDebt) − cash − financialAssets`
    3. No detail at all (bilancio abbreviato) → `totalDebt − cash − financialAssets`
  - Relayout: Attivo chart + CCN chart + PFN chart now in the same 3-card grid (was a single chart row + standalone CCN below)
  - `prepareChartData` includes `pfn` field per year
  - New `MetricRow label="PFN"` under CCN in the metrics summary

### Validation
Visual on frontend — no automated test. PFN now renders on all historical + forecast years.

### Follow-up
PFN is currently frontend-computed only. If backend needs it (for alerts, or in `/analysis` response), add it to `calculations/ratios.py`.

---

## 5. Print CSS & Report Layout Refactor

**Problem**: Manual `print:break-before-page` wrappers around specific sections produced awkward breaks (e.g. cover alone on page 1, then half-empty pages). Also no page numbers on the printed PDF.

**Fix**: Let the browser handle page breaks with `break-inside: avoid`. Add `@page` counters.

### Files
- `frontend/app/globals.css` (+30 / −0)
  - `@page` margin bumped to `16mm` bottom to reserve room for page numbers
  - `@page @bottom-right` content: `"Pagina " counter(page) " di " counter(pages)` with Inter 9px muted-foreground
  - `@page :first` suppresses the number on the cover
  - New `.report-section` class: `break-inside: avoid`
  - New `.report-ai-comment` class: `break-inside: avoid` + `break-before: avoid` (stays with its parent section)
- `frontend/app/report/page.tsx`
  - Removed every explicit `print:break-before-page` wrapper around sections
  - Wrapped each section in a `<div className="report-section space-y-2 print:space-y-1">...`
- `frontend/components/report/report-cover.tsx` (+21 / −42)
  - Replaced shadcn `Table` with a 2-column grid (`grid-cols-2 gap-x-6 gap-y-1`) — about half the vertical space on print
  - Smaller title (`text-2xl` vs `text-3xl`, `print:text-xl`)
  - Merged "Relazione…" subtitle + year range into one line
- `frontend/components/report/report-ratios.tsx` (+5 / −8)
  - Removed `PAGE_BREAK_BEFORE` Set + per-section break logic; each ratio block is now just `<div className="report-section space-y-2 print:space-y-1">`
- `frontend/components/report/report-scoring.tsx` (+4 / −4)
  - `Altman/EM-Score/FGPMI` Cards now use `className="report-section"` instead of manual page breaks
- `frontend/components/report/report-notes.tsx` (−1)
  - Removed forced `print:break-before-page` on the Notes section (browser decides)

### Validation
Visual — print preview on `/report`. Sections now flow naturally; page numbers visible bottom-right except cover.

### Follow-up
None immediate. If a section is tall enough to overflow a single page, `break-inside: avoid` will push it to the next page but won't split it — may need to verify on long scenarios.

---

## 6. Rettifiche Tab — Cross-Side Picker Fix

**Problem**: In "rettifica" (cross-side double-entry) mode, the counterpart picker filtered categories by the sign of the user's edit delta (`+Attivo` showed only `Passivo + CE_POS`, etc.). This prevented valid postings — e.g. a user reducing crediti with a CE_NEG counterpart (correct accounting) couldn't see CE_NEG in the dropdown.

**Fix**: Let the user pick any cross-side counterpart; auto-compute the counterpart's delta sign from the accounting identity `A − L − C − R − Rev + Cost = 0`.

### Files
- `frontend/app/infrannuale/page.tsx` (+17 / −6)
  - `allowedCounterpartCategories`: removed sign-based filtering in "rettifica" mode. `ATTIVO` now shows `{PASSIVO, CE_POS, CE_NEG}`; `PASSIVO` shows `{ATTIVO, CE_POS, CE_NEG}`
  - New `computeCpDelta(editedField, counterpartField, editDelta)`: uses `coeff()` helper (ATTIVO/CE_NEG → +1, PASSIVO/CE_POS → −1) — same group → opposite delta, cross-group → same delta
  - The renamed parameter `_delta` indicates unused by the filter now (but kept for API stability)

### Validation
Manual — tested by creating rettifiche with all 4 counterpart category combinations on a sample infrannuale. Journal balances in every case.

### Follow-up
`computeCpDelta` is defined but not yet wired into the proposal-dialog default value. The dialog still pre-fills `-editDelta` (the old rule). If you want the auto-sign to take effect before the user clicks "Conferma", wire `computeCpDelta` into the delta initialization when the counterpart is selected.

---

## 7. Miscellaneous

- `data/uploads/` (untracked) — runtime artifacts from the upload-tracking feature (already documented in `memory/upload_tracking.md`). Not intended for commit; consider adding to `.gitignore`.
- `.next/` (untracked) — Next.js build cache; should be `.gitignore`'d (probably already is via the frontend-specific gitignore).
- `*.png` and `docs/debug/`, `docs/debug2/`, `docs/debug3/` (untracked) — local test artifacts (screenshots, sample bilanci). Some are actively used by the importers for dev (e.g. the files parsed in feature 1), so don't blanket-delete.

---

## Suggested Commit Split

If splitting into logical commits:

1. **`feat(xbrl+pdf): per-creditor/debtor breakdown for sp16/sp17/sp06/sp07`** — feature 2 (5 files: xbrl_parser_enhanced, pdf_extractor_llm, pdf_importer, taxonomy_mapping_v2.json, imports.py schema)
2. **`feat(importers): AGO/ERP trial balance parser`** — feature 1 (1 file: situazione_contabile_parser.py)
3. **`feat(report): overall AI comment + editable persistence`** — feature 3 (6 files: models.py, migrate_db.py, ai_comments_service.py, reports.py, api.ts, report/page.tsx, report-ai-comment.tsx)
4. **`feat(forecast/balance): PFN chart and metric`** — feature 4 (1 file: forecast/balance/page.tsx)
5. **`style(report): browser-driven page breaks + @page numbers + cover compaction`** — feature 5 (5 files: globals.css, report/page.tsx already touched in #3, report-cover.tsx, report-ratios.tsx, report-scoring.tsx, report-notes.tsx)
6. **`fix(rettifiche): show all cross-side counterpart categories`** — feature 6 (1 file: infrannuale/page.tsx)

Commit 3 and 5 both touch `report/page.tsx` — either bundle into one "Report improvements" commit or split the file's changes manually.
