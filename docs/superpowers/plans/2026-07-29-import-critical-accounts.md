# Import Critical Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the import correct on the three accounts that decide every KPI (immobilizzazioni nette, patrimonio netto, debiti verso banche), approximate where it does not matter, and honest about which of the two happened.

**Architecture:** Four additive changes plus one gate. (1) The contra-netting scan stops guessing parent/child from code prefixes and instead picks the row partition that reconciles to the document's own printed TOTALE ATTIVO. (2) Route-C classification falls back to the shared IV-CEE tree before hitting a catch-all. (3) A single `fallback_bucket()` encodes the materiality policy and refuses to write critical fields. (4) A new pure module `importers/reliability.py` turns evidence the pipeline already computes into a per-account verdict, which gates `forecastable` — never the save.

**Tech Stack:** Python 3.12, SQLAlchemy, PyMuPDF (`fitz`), Decimal arithmetic, pytest. Virtualenv at `backend/venv`. Run everything from the project root `/home/peter/DEV/budget`.

## Global Constraints

- **Never use `float` for money.** Every monetary value is `decimal.Decimal`. Import as `from decimal import Decimal`.
- **Never classify by account-code prefix.** Code *depth* may be used as a hierarchy hint only, and must always be overruled by reconciliation to a printed total.
- **Materiality threshold:** `M = max(Decimal('1000'), Decimal('0.001') * totale_attivo)`.
- **Tier-0 (critical) fields — a fallback may NEVER write these:** `sp02`, `sp03`, `sp04`, `sp11`, `sp12`, `sp13`, `sp16a`, `sp17a` (and their full-name equivalents).
- **Generic fallback fields:** `ce06` (costi per servizi), `ce12` (oneri diversi), `sp16g` (altri debiti), `sp06g` (altri crediti). Always an explicit sub-field, never left as an aggregate residual.
- **Additive only.** Every change must trigger only on the currently-failing sub-case, so files that already extract are provably untouched.
- **No DB migration.** `validation_report` is an existing JSON TEXT column.
- **`quadra` and the save/reject decision are never modified.** An unreliable file must still save so Rettifiche can reach it.
- Run tests with: `backend/venv/bin/python -m pytest <path> -q -p no:randomly`
- Commit messages end with: `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `importers/reliability.py` | **create** | Pure verdict engine: `AccountStatus`, `ReliabilityReport`, `assess()`. No I/O, no PDF, no DB. |
| `tests/test_reliability.py` | **create** | Unit tests for `assess()` across all three accounts. |
| `tests/test_fallback_bucket.py` | **create** | Unit tests for the materiality/tier policy. |
| `tests/test_dedup_partition.py` | **create** | Unit tests for prefix-free partition selection. |
| `tests/test_classification_fallback.py` | **create** | `_resolve_field` + budget_342 CE end-to-end. |
| `importers/situazione_contabile_parser.py` | modify | Add `_code_depth`, `_dedup_candidates`, `_select_dedup`, `_resolve_field`, `fallback_bucket`; parameterise `_contra_classify`; record contra metadata in `net_contra_accounts`. |
| `importers/pdf_importer.py` | modify | Call `assess()`, fold into `forecastable`/`validation_status`, embed in `validation_report`. |
| `tests/test_contra_netting.py` | modify | Fix the stale 2-vs-3 unpack (Task 1). |
| `tests/test_csv_schema_detection.py` | modify | Add `skipif` guards (Task 0). |

---

## Task 0: Green the suite

Two CSV tests fail because a corpus file is absent and they lack the `skipif` guard every other corpus-dependent test has. They keep the suite red and would mask a real regression introduced by later tasks.

**Files:**
- Modify: `tests/test_csv_schema_detection.py`

**Interfaces:**
- Consumes: nothing
- Produces: a suite whose only failures are the two known netting failures (Task 1 fixes those)

- [ ] **Step 1: Confirm the current failure and its cause**

Run: `backend/venv/bin/python -m pytest tests/test_csv_schema_detection.py -q -p no:randomly 2>&1 | tail -6`

Expected: 2 failed, with `CSVImportError: File not found: .../Test/june_sample/errori/budget_370_BILAQ-001.csv`

- [ ] **Step 2: Find the two test functions and the path constant**

Run: `grep -n "budget_370_BILAQ-001\|^def test_\|^BILAQ\|^CSV_" tests/test_csv_schema_detection.py`

Note the module-level constant holding the CSV path (if the path is inline in each test, hoist it to a module-level constant named `BILAQ_CSV` first).

- [ ] **Step 3: Add the skipif guard to both tests**

Add near the top of the file, after the imports:

```python
import os
import pytest

BILAQ_CSV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Test", "june_sample", "errori", "budget_370_BILAQ-001.csv",
)
```

Then decorate **both** failing tests (`test_bilaq_header_and_windows_encoding_are_detected` and `test_real_bilaq_is_mapped_by_headers_and_iv_cee_sections`):

```python
@pytest.mark.skipif(not os.path.exists(BILAQ_CSV),
                    reason="local corpus CSV budget_370 is not available")
```

and make each test use `BILAQ_CSV` instead of its inline path.

- [ ] **Step 4: Verify both now skip and nothing else changed**

Run: `backend/venv/bin/python -m pytest tests/test_csv_schema_detection.py -q -p no:randomly -rs`

Expected: `2 skipped` (or `2 passed` if you do have the corpus file), 0 failed.

- [ ] **Step 5: Record the whole-suite baseline**

Run: `backend/venv/bin/python -m pytest tests/ -q -p no:randomly 2>&1 | tail -5`

Expected: exactly 2 failures remain, both in `tests/test_contra_netting.py`. Write the exact pass/fail/skip counts into the commit message — later tasks compare against it.

- [ ] **Step 6: Commit**

```bash
git add tests/test_csv_schema_detection.py
git commit -m "test: skip BILAQ CSV tests when the local corpus file is absent

Every other corpus-dependent test guards with skipif; these two raised
CSVImportError instead, keeping the suite red and masking regressions.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 1: Prefix-free partition selection for the contra scan

`_dedup_parent_child` decides parentage with `c.startswith(code)`. AGO prints mastri as 8-digit codes (`13095000`) and their details as 9-digit codes (`101080000`), which are not prefixes of each other, so nothing dedups and both levels are summed. On `613_2024` this over-reads attivo by 41.613,46 (0,836%) and fondi by 393.916,50 — the netting gate then fails and `netted = 0`, leaving 2,25 M of fondi ammortamento booked as debts.

The fix does not invent a better parentage rule. It generates several candidate partitions and keeps the one that reconciles to the document's own printed TOTALE ATTIVO.

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (add `_code_depth`, `_dedup_candidates`, `_select_dedup`; add `dedup` parameter to `_contra_classify`; use selection + record metadata in `net_contra_accounts`)
- Modify: `tests/test_contra_netting.py` (fix stale unpack)
- Test: `tests/test_dedup_partition.py` (create)

**Interfaces:**
- Consumes: `_contra_rows(file_path, text=None) -> (attivo_rows, passivo_rows, from_ocr)` where each row is `(code: str, desc_upper: str, amount: Decimal)`; `ContraScan` NamedTuple; `_dedup_parent_child(rows) -> rows`
- Produces:
  - `_code_depth(code: str) -> int`
  - `_dedup_candidates(rows) -> Iterator[tuple[str, list]]` yielding `(label, deduped_rows)`
  - `_select_dedup(attivo_rows, declared_total: Optional[Decimal]) -> tuple[str, Callable, bool]` returning `(label, dedup_fn, reconciled)`
  - `_contra_classify(attivo_rows, passivo_rows, dedup=None) -> ContraScan` — `dedup=None` keeps today's `_dedup_parent_child`
  - `net_contra_accounts` writes `_contra_detected`, `_contra_applied`, `_contra_reason` into the returned `bs`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dedup_partition.py`:

```python
"""Prefix-free partition selection for the contra-netting scan.

AGO prints mastri as 8-digit codes and their sub-accounts as 9-digit codes.
Neither is a prefix of the other, so the historical startswith() dedup summed
both levels: on 613_2024 that over-read attivo by 41.613,46 and fondi by
393.916,50, which made net_contra_accounts no-op and left 2,25M of fondi
ammortamento booked as debts.
"""
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.situazione_contabile_parser import (  # noqa: E402
    _code_depth,
    _select_dedup,
)

D = Decimal

PDF_613 = os.path.join(
    ROOT, "docs", "examples",
    "613_2024 Costruzione di edifici residenziali e non residenziali.pdf",
)


def test_code_depth_uses_segments_for_dotted_codes():
    assert _code_depth("03") == 1
    assert _code_depth("03.01") == 2
    assert _code_depth("03.01.07") == 3


def test_code_depth_uses_length_for_flat_codes():
    assert _code_depth("13095000") == 8
    assert _code_depth("101080000") == 9


def test_code_depth_of_empty_code_is_zero():
    assert _code_depth("") == 0


def test_selection_prefers_the_partition_matching_the_declared_total():
    # mastri (8-digit) sum to 1000 == declared; details (9-digit) duplicate 300 of it
    rows = [
        ("13095000", "ATTREZZATURE", D("300")),
        ("101080000", "ATTREZZATURA VARIA", D("300")),
        ("13085000", "FABBRICATI", D("700")),
    ]
    label, dedup_fn, reconciled = _select_dedup(rows, D("1000"))
    assert reconciled is True
    kept = dedup_fn(rows)
    assert sum(a for _c, _d, a in kept) == D("1000")


def test_selection_reports_not_reconciled_when_nothing_matches():
    rows = [("13095000", "ATTREZZATURE", D("300"))]
    label, dedup_fn, reconciled = _select_dedup(rows, D("999999"))
    assert reconciled is False


def test_selection_without_a_declared_total_keeps_legacy_behaviour():
    rows = [("13095000", "ATTREZZATURE", D("300"))]
    label, dedup_fn, reconciled = _select_dedup(rows, None)
    assert label == "existing"
    assert reconciled is False


@pytest.mark.skipif(not os.path.exists(PDF_613), reason="evidence PDF not present")
def test_613_partition_reproduces_the_declared_total_exactly():
    from importers.situazione_contabile_parser import _contra_rows
    attivo_rows, _passivo_rows, _from_ocr = _contra_rows(PDF_613)
    label, dedup_fn, reconciled = _select_dedup(attivo_rows, D("4979885.27"))
    assert reconciled is True
    kept = dedup_fn(attivo_rows)
    assert sum(a for _c, _d, a in kept) == D("4979885.27")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest tests/test_dedup_partition.py -q -p no:randomly`

Expected: FAIL at collection — `ImportError: cannot import name '_code_depth' from 'importers.situazione_contabile_parser'`

- [ ] **Step 3: Implement the helpers**

In `importers/situazione_contabile_parser.py`, immediately **after** the existing `_dedup_parent_child` function (which ends with `return out`), add:

```python
def _code_depth(code: str) -> int:
    """Hierarchy level of an account code.

    Dotted/slashed codes carry their depth explicitly ('03.01.07' -> 3). Flat
    numeric codes encode it in their LENGTH: AGO prints mastri as 8 digits
    ('13095000') and their sub-accounts as 9 ('101080000'). Depth is only a
    HINT — the caller must corroborate the chosen partition against a printed
    total before trusting it (see _select_dedup).
    """
    c = (code or '').strip()
    if not c:
        return 0
    canon = _hier_canon(c)
    if '.' in canon:
        return len(canon.split('.'))
    return len(canon)


def _dedup_candidates(rows):
    """Yield (label, rows) candidate partitions of a scan side.

    No candidate is trusted on its own; _select_dedup scores them against the
    document's printed total. Includes the historical prefix-based dedup so a
    file that works today can still win.
    """
    yield 'all', list(rows)
    yield 'existing', _dedup_parent_child(rows)
    depths = sorted({_code_depth(c) for c, _d, _a in rows if c})
    for depth in depths:
        yield (f'depth<={depth}',
               [r for r in rows if not r[0] or _code_depth(r[0]) <= depth])


def _select_dedup(attivo_rows, declared_total: Optional[Decimal]):
    """Pick the partition whose attivo sum reconciles to the declared total.

    Returns (label, dedup_fn, reconciled). ``dedup_fn`` is applied to BOTH
    sides so the two are partitioned consistently. When no declared total is
    available, or none of the candidates reconciles, the historical behaviour
    is returned with reconciled=False — the caller then records the scan as
    unreliable instead of silently trusting it.
    """
    legacy = ('existing', _dedup_parent_child, False)
    if not declared_total or declared_total <= 0:
        return legacy
    tol = max(Decimal('50'), declared_total * Decimal('0.005'))
    best = None
    for label, kept in _dedup_candidates(attivo_rows):
        total = sum((a for _c, _d, a in kept), Decimal('0'))
        gap = abs(total - declared_total)
        if gap > tol:
            continue
        # tie-break: drop as few rows as possible
        key = (gap, -len(kept))
        if best is None or key < best[0]:
            best = (key, label)
    if best is None:
        return legacy
    label = best[1]

    def _fn(rows, _label=label):
        for candidate_label, kept in _dedup_candidates(rows):
            if candidate_label == _label:
                return kept
        return _dedup_parent_child(rows)

    return label, _fn, True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m pytest tests/test_dedup_partition.py -q -p no:randomly`

Expected: PASS (7 passed, or 6 passed + 1 skipped without the 613 PDF)

- [ ] **Step 5: Commit the helpers**

```bash
git add importers/situazione_contabile_parser.py tests/test_dedup_partition.py
git commit -m "feat(netting): prefix-free partition selection anchored on the declared total

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Wire the selection into `_contra_classify`**

Change the signature of `_contra_classify` (currently `def _contra_classify(attivo_rows, passivo_rows) -> ContraScan:`) to:

```python
def _contra_classify(attivo_rows, passivo_rows, dedup=None) -> ContraScan:
```

Add as the first line of its body:

```python
    dedup = dedup or _dedup_parent_child
```

Then inside it replace **every** call `_dedup_parent_child(list(attivo_rows))`, `_dedup_parent_child(list(passivo_rows))` and `_dedup_parent_child(list(raw_rows))` with `dedup(list(...))` — keeping the same argument in each case. Find them with:

Run: `grep -n "_dedup_parent_child(list(" importers/situazione_contabile_parser.py`

Expected: 3 call sites, all inside `_contra_classify`.

- [ ] **Step 7: Verify the default path is unchanged**

Run: `backend/venv/bin/python -m pytest tests/test_contra_netting.py -q -p no:randomly 2>&1 | tail -4`

Expected: still exactly 2 failures (the same two as the Task 0 baseline) — the `dedup=None` default must not have changed any behaviour yet.

- [ ] **Step 8: Use the selection inside `net_contra_accounts` and record metadata**

In `net_contra_accounts`, replace this line:

```python
        scan = _contra_classify(att_rows, pas_rows)
```

with:

```python
        dedup_label, dedup_fn, dedup_reconciled = _select_dedup(att_rows, decl_total)
        scan = _contra_classify(att_rows, pas_rows, dedup=dedup_fn)
        logger.info("contra-netting: partizione '%s' (riconcilia=%s)",
                    dedup_label, dedup_reconciled)
```

Then record the outcome so `reliability.assess()` can read it.

> **Why this is safe to put in the `bs` dict.** `_map_sc_keys` passes through any key containing
> an underscore, so `_contra_*` survives into the full-name dict — and
> `_create_balance_sheet`/`_create_income_statement` build their values from
> `BalanceSheet.__table__.columns`, pulling only real ORM columns out of `data`. Unknown keys are
> ignored, never written. This is the same mechanism `_plug_residual` and `_netted_contra`
> already rely on.

Immediately **before** each of the three `return winner_bs, Z` statements inside the `try:` block (gate 1, gate 2, and the `rows` guard), and before the final successful return, set the metadata. The simplest correct way is a tiny helper defined at the top of `net_contra_accounts`:

```python
    def _mark(bs, detected, applied, reason):
        bs['_contra_detected'] = detected
        bs['_contra_applied'] = applied
        bs['_contra_reason'] = reason
        return bs
```

Apply it:

| Return site | Call |
|---|---|
| `if not decl_total or decl_total <= 0:` | `return _mark(winner_bs, Z, Z, 'nessun totale dichiarato'), Z` |
| `if not rows:` | `return _mark(winner_bs, Z, Z, 'scan non disponibile'), Z` |
| gate 1 (`netted <= decl_total * 0.01`) | `return _mark(winner_bs, netted, Z, 'massa contro sotto soglia'), Z` |
| gate 2 (the `else:` that logs "no-op") | `return _mark(winner_bs, netted, Z, 'contro rilevati ma non applicati: scan non riconcilia'), Z` |
| `except Exception` | `return _mark(winner_bs, Z, Z, f'scan fallito: {exc}'), Z` |
| end of function (successful apply) | `_mark(winner_bs, netted, netted, f'applicato ({dedup_label})')` before the existing `return winner_bs, netted` |

- [ ] **Step 9: Fix the stale unpack in the existing netting test**

In `tests/test_contra_netting.py`, find:

```python
    rows = _contra_rows(PDF_613)
    assert rows is not None
    attivo_rows, passivo_rows = rows
```

Replace the last line with:

```python
    attivo_rows, passivo_rows, _from_ocr = rows
```

- [ ] **Step 10: Run the two 613 tests — these are the acceptance criteria**

Run: `backend/venv/bin/python -m pytest tests/test_contra_netting.py -q -p no:randomly`

Expected: **all pass**, specifically
- `test_contra_rows_on_613_finds_the_fondi_mass`: fondi within 1% of `1853799.20`, `scan.attivo_total > 4000000`
- `test_613_production_path_with_stubbed_gross_llm`: `netted > 1800000`, `sp03 ≈ 3080000`, debts `< 400000`, `totale_attivo ≈ 3130000`

If `test_contra_rows_on_613_finds_the_fondi_mass` still fails, `_contra_classify` is not receiving the selected `dedup` — that test calls `_contra_classify(attivo_rows, passivo_rows)` directly with the default. Update that test to pass the selected partition:

```python
    from importers.situazione_contabile_parser import _select_dedup
    from importers.pdf_extractor_llm import _declared_control_totals
    declared = _declared_control_totals(PDF_613)
    _label, dedup_fn, _ok = _select_dedup(
        attivo_rows, declared.get("attivo") or declared.get("pareggio"))
    scan = _contra_classify(attivo_rows, passivo_rows, dedup=dedup_fn)
```

- [ ] **Step 11: Run the route-C corpus regression**

```bash
backend/venv/bin/python tests/_prod_route_c_runner.py tests/debug 2>/dev/null | grep -v "^WARNING" > /tmp/after.txt
git stash push importers/situazione_contabile_parser.py -q
backend/venv/bin/python tests/_prod_route_c_runner.py tests/debug 2>/dev/null | grep -v "^WARNING" > /tmp/before.txt
git stash pop -q
diff /tmp/before.txt /tmp/after.txt
```

Expected: no line regresses. `budget_615` and `budget_342` must both still show `SI`. A file improving from `MASK` to `SI` is a win; a file going the other way is a blocker — stop and investigate.

- [ ] **Step 12: Run the whole suite**

Run: `backend/venv/bin/python -m pytest tests/ -q -p no:randomly 2>&1 | tail -5`

Expected: 0 failures (the two Task 0 baseline failures are now fixed).

- [ ] **Step 13: Commit**

```bash
git add importers/situazione_contabile_parser.py tests/test_contra_netting.py
git commit -m "fix(netting): select the scan partition by reconciliation, not code prefixes

_dedup_parent_child matched parents with c.startswith(code). AGO uses two
disjoint code families (8-digit mastri, 9-digit sub-accounts), so nothing
deduped and both levels were summed: on 613_2024 attivo over-read by
41.613,46 (0,836%) and fondi by 393.916,50, so the netting gate failed and
2,25M of fondi ammortamento stayed booked as debts with the assets gross.

Candidate partitions are now scored against the document's printed TOTALE
ATTIVO; the winner reproduces it exactly (4.979.885,27) and the fondi mass
(1.853.799,20). When nothing reconciles the scan is recorded as unreliable
instead of silently trusted.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Classification fallback to the shared IV-CEE tree

Two independent classifiers exist and each knows what the other misses: `resolve()` maps `AMMORTAMENTI -> ce09` but not `COSTI PERSONALE DIPENDENTE`; `_classify_ce_costi` the reverse. `_hier_reconstruct` uses only the second, so on `budget_342` it drops 36.500,17 of depreciation into the `ce12` catch-all and EBITDA is wrong while every gate still passes.

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (add `_resolve_field`; use it at the two catch-all sites)
- Test: `tests/test_classification_fallback.py` (create)

**Interfaces:**
- Consumes: `iv_cee_hierarchy.resolve(desc, side=None, statement=None) -> Optional[Node]`; `Node.db_field: str`, `Node.statement: str` (`'bs'`/`'ce'`)
- Produces: `_resolve_field(desc: str, side: Optional[str] = None, statement: Optional[str] = None) -> Optional[str]` returning a SHORT key (`'ce09'`, `'sp16'`) or `None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_classification_fallback.py`:

```python
"""Route C falls back to the shared IV-CEE tree before the catch-all.

_classify_ce_costi and iv_cee_hierarchy.resolve() are independent classifiers
that each miss what the other knows. _hier_reconstruct used only the former,
so a bare 'AMMORTAMENTI' mastro fell into the ce12 catch-all: totals and sp13
stayed correct (no gate fired) but EBITDA was wrong, because EBITDA = EBIT + ce09.
"""
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.situazione_contabile_parser import _resolve_field  # noqa: E402

D = Decimal


def test_resolve_field_returns_the_short_key():
    assert _resolve_field("AMMORTAMENTI", "costi") == "ce09"


def test_resolve_field_handles_a_known_financial_cost():
    assert _resolve_field("ONERI FINANZIARI", "costi") == "ce15"


def test_resolve_field_returns_none_when_unknown():
    assert _resolve_field("ACQUISTI DI BENI", "costi") is None


def test_resolve_field_rejects_a_node_from_the_wrong_statement():
    # a balance-sheet caption must not be returned when we asked for the CE
    assert _resolve_field("DISPONIBILITA' LIQUIDE", "costi", statement="ce") is None


def _budget_342_pdf():
    for folder in ("Test/july_budget", "tests/debug"):
        matches = sorted(
            __import__("pathlib").Path(ROOT, folder).glob("budget_342_*.pdf"))
        if matches:
            return str(matches[0])
    return None


def test_budget_342_ammortamenti_are_not_swallowed_by_oneri_diversi():
    pdf = _budget_342_pdf()
    if pdf is None:
        pytest.skip("local regression PDF budget_342 is not available")
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from _prod_route_c_runner import run_prod_route_c

    result = run_prod_route_c(pdf)
    ce = result["ce"]
    # declared in the PDF: Totale ammortamenti mastro 80 = 36.500,17
    assert abs(Decimal(ce.get("ce09_ammortamenti", 0)) - D("36500.17")) <= D("1")
    # ce12 must fall back to the real 'ONERI DIVERSI DI GESTIONE' mastro
    assert Decimal(ce.get("ce12_oneri_diversi", 0)) < D("60000")
    # the result is unchanged by re-labelling costs
    assert abs(Decimal(result["sp13"]) - D("100046.26")) <= D("1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest tests/test_classification_fallback.py -q -p no:randomly`

Expected: FAIL at collection — `ImportError: cannot import name '_resolve_field'`

- [ ] **Step 3: Implement `_resolve_field`**

In `importers/situazione_contabile_parser.py`, add immediately **after** `_classify_ce_ricavi` (which ends with `return None`):

```python
def _resolve_field(desc: str, side: Optional[str] = None,
                   statement: Optional[str] = None) -> Optional[str]:
    """Shared-tree classification, returned as a SHORT route-C key.

    `iv_cee_hierarchy.resolve` reasons in DB column names ('ce09_ammortamenti')
    while the route-C parsers work in short keys ('ce09') until _map_sc_keys.
    The short key is the db_field prefix up to the first underscore, which is
    exact for every node ('sp16a_debiti_banche_breve' -> 'sp16a').

    Returns None when the tree does not know the description, or when it
    resolves to the OTHER statement — a balance-sheet caption must never be
    booked as a cost.
    """
    try:
        from importers.iv_cee_hierarchy import resolve as _tree_resolve
        node = _tree_resolve(desc, side, statement)
    except Exception:
        return None
    if node is None or not node.db_field:
        return None
    if statement and node.statement and node.statement != statement:
        return None
    return node.db_field.split('_', 1)[0]
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run: `backend/venv/bin/python -m pytest tests/test_classification_fallback.py -q -p no:randomly -k "resolve_field"`

Expected: 4 passed

- [ ] **Step 5: Use the fallback at the two catch-all sites**

Run: `grep -n "or 'ce12'\|or 'ce04'" importers/situazione_contabile_parser.py`

Expected: 2 hits inside `_hier_reconstruct`. Change:

```python
        f = _classify_ce_costi(d) or 'ce12'
```

to

```python
        f = _classify_ce_costi(d) or _resolve_field(d, 'costi', statement='ce') or 'ce12'
```

and

```python
        f = _classify_ce_ricavi(d) or 'ce04'
```

to

```python
        f = _classify_ce_ricavi(d) or _resolve_field(d, 'ricavi', statement='ce') or 'ce04'
```

- [ ] **Step 6: Run the budget_342 end-to-end test**

Run: `backend/venv/bin/python -m pytest tests/test_classification_fallback.py -q -p no:randomly`

Expected: 5 passed (or 4 passed + 1 skipped without the PDF)

- [ ] **Step 7: Corpus regression + full suite**

```bash
backend/venv/bin/python tests/_prod_route_c_runner.py tests/debug 2>/dev/null | grep -v "^WARNING"
backend/venv/bin/python -m pytest tests/ -q -p no:randomly 2>&1 | tail -5
```

Expected: every file still `SI` that was `SI`; 0 test failures.

- [ ] **Step 8: Commit**

```bash
git add importers/situazione_contabile_parser.py tests/test_classification_fallback.py
git commit -m "fix(classification): fall back to the shared IV-CEE tree before the catch-all

resolve() knows AMMORTAMENTI -> ce09; _classify_ce_costi does not.
_hier_reconstruct used only the latter, so budget_342 buried 36.500,17 of
depreciation in ce12: totals and sp13 stayed right so no gate fired, but
EBITDA = EBIT + ce09 was wrong. Additive - fires only where the keyword
table returns None today.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `fallback_bucket()` — one place for the materiality policy

Today the fallback is scattered (`or 'ce12'`, `or 'ce04'`, `addb('sp16', a)`) and implicit. This centralises it so the tier-0 prohibition is codified rather than remembered, and so mass assigned by guesswork above the materiality threshold becomes visible.

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (add `TIER0_FIELDS`, `FALLBACK_FIELDS`, `materiality_threshold`, `fallback_bucket`)
- Test: `tests/test_fallback_bucket.py` (create)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `materiality_threshold(total: Decimal) -> Decimal`
  - `fallback_bucket(desc: str, statement: str, amount: Decimal, total: Decimal, target: Optional[str] = None) -> tuple[str, str]` returning `(short_field, severity)` where severity is `'silent'` or `'recorded'`; raises `ValueError` if `target` is a tier-0 field
  - `TIER0_FIELDS: frozenset[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_fallback_bucket.py`:

```python
"""Materiality + criticality policy for unclassified mass.

A plug INVENTS mass to make a sheet balance and is forbidden. A fallback
LABELS mass that was actually read and is allowed - but never onto a tier-0
account, because those decide every KPI (a fondo ammortamento landing in
'altri debiti' inflates assets and debts together and breaks PFN, ROI,
indipendenza finanziaria and both rating models at once).
"""
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.situazione_contabile_parser import (  # noqa: E402
    TIER0_FIELDS,
    fallback_bucket,
    materiality_threshold,
)

D = Decimal


def test_threshold_has_an_absolute_floor_of_1000():
    assert materiality_threshold(D("100000")) == D("1000")


def test_threshold_scales_with_total_assets():
    assert materiality_threshold(D("10000000")) == D("10000")


def test_threshold_of_zero_total_is_the_floor():
    assert materiality_threshold(D("0")) == D("1000")


def test_small_cost_goes_silently_to_servizi():
    field, severity = fallback_bucket("QUALCOSA", "ce", D("500"), D("1000000"))
    assert field == "ce06"
    assert severity == "silent"


def test_material_cost_is_recorded():
    field, severity = fallback_bucket("QUALCOSA", "ce", D("50000"), D("1000000"))
    assert field == "ce06"
    assert severity == "recorded"


def test_balance_sheet_fallback_is_altri_debiti():
    field, _severity = fallback_bucket("QUALCOSA", "bs", D("500"), D("1000000"))
    assert field == "sp16g"


def test_fallback_field_is_usable_before_the_total_is_known():
    """A classification loop knows the amount long before the sheet total, so it
    needs the destination without a materiality verdict."""
    from importers.situazione_contabile_parser import fallback_field
    assert fallback_field("ce") == "ce06"
    assert fallback_field("bs") == "sp16g"


@pytest.mark.parametrize("target", ["sp02", "sp03", "sp12", "sp16a", "ce09"])
def test_tier0_targets_are_refused(target):
    with pytest.raises(ValueError):
        fallback_bucket("F.DO AMM. FABBRICATI", "bs", D("500"), D("1000000"),
                        target=target)


def test_tier0_set_covers_the_critical_accounts():
    for f in ("sp02", "sp03", "sp04", "sp11", "sp12", "sp13", "sp16a", "sp17a"):
        assert f in TIER0_FIELDS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest tests/test_fallback_bucket.py -q -p no:randomly`

Expected: FAIL at collection — `ImportError: cannot import name 'TIER0_FIELDS'`

- [ ] **Step 3: Implement the policy**

In `importers/situazione_contabile_parser.py`, add immediately **after** `_resolve_field`:

```python
# Accounts that decide every KPI. A fallback may NEVER write these: an error
# here changes a TOTAL (a fondo ammortamento booked as a debt inflates assets
# and debts together), which breaks PFN, ROI, indipendenza finanziaria and
# both rating models at once. ce09 is included because EBITDA = EBIT + ce09.
TIER0_FIELDS = frozenset({
    'sp02', 'sp03', 'sp04',      # immobilizzazioni nette
    'sp11', 'sp12', 'sp13',      # patrimonio netto
    'sp16a', 'sp17a',            # debiti verso banche
    'ce09',                      # ammortamenti (EBITDA boundary)
})

# KPI-neutral destinations: moving mass between these changes neither EBIT nor
# EBITDA (they are all inside 'costi della produzione'), nor any debt/credit
# total. Always an explicit SUB-field: projection_common.base_bank_debt treats
# an aggregate/detail gap as BANK debt, so a residual left on an aggregate
# would silently become phantom bank debt - a tier-0 corruption.
FALLBACK_FIELDS = {'ce': 'ce06', 'bs': 'sp16g'}


def materiality_threshold(total: Decimal) -> Decimal:
    """M = max(1.000 EUR; 0,1% del totale attivo)."""
    total = abs(total or Decimal('0'))
    return max(Decimal('1000'), total * Decimal('0.001'))


def fallback_field(statement: str) -> str:
    """KPI-neutral destination for unrecognised mass in `statement`.

    Separate from fallback_bucket because a classification loop knows the
    amount long before the sheet total exists: it needs the destination now
    and the materiality verdict later.
    """
    return FALLBACK_FIELDS.get(statement, 'ce06')


def fallback_bucket(desc: str, statement: str, amount: Decimal,
                    total: Decimal, target: Optional[str] = None):
    """Destination for mass that was READ but not recognised.

    Returns (short_field, severity). severity is 'silent' below the
    materiality threshold and 'recorded' above it, so the caller can surface
    material guesswork instead of hiding it.

    Raises ValueError when `target` names a tier-0 field: uncertainty about a
    critical account must become an UNRELIABLE verdict, never a guess.
    """
    if target and target in TIER0_FIELDS:
        raise ValueError(
            f"fallback vietato verso un conto critico ({target}): "
            f"'{desc}' deve essere segnalato, non indovinato")
    severity = ('recorded'
                if abs(amount or Decimal('0')) > materiality_threshold(total)
                else 'silent')
    return fallback_field(statement), severity
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m pytest tests/test_fallback_bucket.py -q -p no:randomly`

Expected: 13 passed

- [ ] **Step 5: Wire the policy into the two catch-all sites**

Creating the function without using it would leave the policy decorative. In `_hier_reconstruct`, record what the catch-all swallowed so the mass becomes measurable.

Add near the top of `_hier_reconstruct`, next to the existing `prior_pn = Z`:

```python
    unclassified = []          # (desc, amount, assigned_field)
```

Change the cost line written in Task 2:

```python
        f = _classify_ce_costi(d) or _resolve_field(d, 'costi', statement='ce') or 'ce12'
```

to:

```python
        f = _classify_ce_costi(d) or _resolve_field(d, 'costi', statement='ce')
        if f is None:
            f = fallback_field('ce')
            unclassified.append((d, a, 'ce'))
```

and the revenue line the same way, keeping `ce04` as its destination (a revenue
that reaches the catch-all is still revenue — only the sub-line is unknown):

```python
        f = _classify_ce_ricavi(d) or _resolve_field(d, 'ricavi', statement='ce')
        if f is None:
            f = 'ce04'
            unclassified.append((d, a, 'ce'))
```

The materiality verdict cannot be reached inside the loop — the sheet total does not
exist yet. Resolve it once, immediately **after** `att_sum` is computed (the line
`att_sum = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)`):

```python
    # Mass assigned by fallback rather than recognised. Only the MATERIAL part is
    # reported: below the threshold a generic bucket is a legitimate label; above
    # it the composition is guesswork and must be visible. fallback_bucket is the
    # single policy entry point, called here where the total is finally known.
    material = Z
    for _desc, _amt, _stmt in unclassified:
        _field, _severity = fallback_bucket(_desc, _stmt, _amt, att_sum)
        if _severity == 'recorded':
            material += abs(_amt)
    bs['_unclassified_mass'] = material
```

- [ ] **Step 6: Verify the wiring on budget_342**

Run: `backend/venv/bin/python -m pytest tests/test_classification_fallback.py tests/test_fallback_bucket.py -q -p no:randomly`

Expected: all pass. The budget_342 assertions from Task 2 must still hold — `ce09 = 36.500,17` is now produced by `_resolve_field`, so nothing should reach the fallback for that mastro.

- [ ] **Step 7: Corpus regression**

Run: `backend/venv/bin/python tests/_prod_route_c_runner.py tests/debug 2>/dev/null | grep -v "^WARNING"`

Expected: no file regresses; `budget_615` and `budget_342` still `SI`.

- [ ] **Step 8: Commit**

```bash
git add importers/situazione_contabile_parser.py tests/test_fallback_bucket.py
git commit -m "feat(import): centralise the fallback/materiality policy

Labelling mass that was read is allowed; inventing mass is not, and neither
is guessing a tier-0 account. One function so the prohibition is codified
rather than remembered, plus _unclassified_mass so material guesswork is
measurable instead of silent.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `reliability.assess()` — the verdict engine

A pure module that turns evidence the pipeline already produces into a per-account verdict. No I/O, no PDF, no DB — so it is trivially testable and reusable by the XBRL/CSV importers later.

**Files:**
- Create: `importers/reliability.py`
- Test: `tests/test_reliability.py` (create)

**Interfaces:**
- Consumes: the balance-sheet dict with full DB field names, plus the `_contra_detected` / `_contra_applied` / `_contra_reason` metadata written by Task 1
- Produces:
  - `AccountStatus` (Enum: `VERIFIED`, `DERIVED`, `UNRELIABLE`)
  - `ReliabilityReport` (frozen dataclass) with `.immobilizzazioni`, `.patrimonio_netto`, `.debiti_banche`, matching `*_reason: str`, `.unclassified_mass: Decimal`, `.all_critical_ok: bool`, `.to_dict()`
  - `assess(bs: dict, ce: dict, declared: Optional[dict] = None) -> ReliabilityReport`

- [ ] **Step 1: Write the failing test**

Create `tests/test_reliability.py`:

```python
"""Per-account reliability verdicts.

UNRELIABLE requires POSITIVE evidence of contradiction, never the mere absence
of a control - otherwise every route A/B file (which runs no contra scan) and
every abbreviated statement would be blocked.
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.reliability import (  # noqa: E402
    AccountStatus,
    ReliabilityReport,
    assess,
)

D = Decimal


def _bs(**over):
    base = {
        "sp02_immob_immateriali": D("6000"),
        "sp03_immob_materiali": D("1500000"),
        "sp11_capitale": D("10000"),
        "sp12_riserve": D("800000"),
        "sp13_utile_perdita": D("100000"),
        "sp16_debiti_breve": D("220000"),
        "sp16a_debiti_banche_breve": D("7000"),
        "sp16d_debiti_fornitori_breve": D("213000"),
        "sp17_debiti_lungo": D("0"),
        "totale_attivo": D("2000000"),
        "totale_passivo": D("2000000"),
    }
    base.update(over)
    return base


# ---------------------------------------------------------- immobilizzazioni

def test_contra_detected_but_not_applied_is_unreliable():
    """The 613 shape: the scan found 2,25M of fondi and then discarded them."""
    bs = _bs(_contra_detected=D("2247715.70"), _contra_applied=D("0"),
             _contra_reason="contro rilevati ma non applicati")
    r = assess(bs, {})
    assert r.immobilizzazioni is AccountStatus.UNRELIABLE
    assert r.all_critical_ok is False


def test_contra_applied_is_verified():
    bs = _bs(_contra_detected=D("2247715.70"), _contra_applied=D("2247715.70"),
             _contra_reason="applicato")
    r = assess(bs, {})
    assert r.immobilizzazioni is AccountStatus.VERIFIED


def test_no_contra_mass_found_is_derived_not_unreliable():
    bs = _bs(_contra_detected=D("0"), _contra_applied=D("0"),
             _contra_reason="nessuna massa contro")
    r = assess(bs, {})
    assert r.immobilizzazioni is AccountStatus.DERIVED


def test_route_ab_without_any_contra_metadata_is_derived():
    """Route A/B never runs a contra scan; absence of metadata must not block."""
    r = assess(_bs(), {})
    assert r.immobilizzazioni is AccountStatus.DERIVED
    assert r.all_critical_ok is True


# ---------------------------------------------------------- patrimonio netto

def test_pn_matching_the_printed_control_is_verified():
    r = assess(_bs(), {}, declared={"patrimonio_netto": D("910000")})
    assert r.patrimonio_netto is AccountStatus.VERIFIED


def test_pn_contradicting_the_printed_control_is_unreliable():
    r = assess(_bs(), {}, declared={"patrimonio_netto": D("500000")})
    assert r.patrimonio_netto is AccountStatus.UNRELIABLE
    assert r.all_critical_ok is False


def test_pn_without_a_printed_control_is_derived():
    r = assess(_bs(), {}, declared={})
    assert r.patrimonio_netto is AccountStatus.DERIVED


# ------------------------------------------------------------ debiti banche

def test_explicit_bank_subfields_are_verified():
    r = assess(_bs(), {})
    assert r.debiti_banche is AccountStatus.VERIFIED


def test_material_aggregate_gap_is_unreliable():
    """base_bank_debt assigns any aggregate/detail gap to BANKS, so a material
    gap means the bank figure is invented rather than read."""
    bs = _bs(sp16_debiti_breve=D("500000"))   # 280k unexplained
    r = assess(bs, {})
    assert r.debiti_banche is AccountStatus.UNRELIABLE


def test_immaterial_aggregate_gap_is_tolerated():
    bs = _bs(sp16_debiti_breve=D("220500"))   # 500 gap, below M=2000
    r = assess(bs, {})
    assert r.debiti_banche is not AccountStatus.UNRELIABLE


def test_no_bank_debt_and_no_gap_is_derived():
    bs = _bs(sp16a_debiti_banche_breve=D("0"),
             sp16d_debiti_fornitori_breve=D("220000"))
    r = assess(bs, {})
    assert r.debiti_banche is AccountStatus.DERIVED


# ------------------------------------------------------------------ payload

def test_to_dict_is_json_safe_and_carries_reasons():
    import json
    r = assess(_bs(), {})
    payload = r.to_dict()
    json.dumps(payload)          # must not raise
    assert set(payload) >= {"immobilizzazioni", "patrimonio_netto",
                            "debiti_banche", "all_critical_ok"}
    assert payload["immobilizzazioni"]["status"] == "derived"
    assert isinstance(payload["immobilizzazioni"]["reason"], str)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest tests/test_reliability.py -q -p no:randomly`

Expected: FAIL at collection — `ModuleNotFoundError: No module named 'importers.reliability'`

- [ ] **Step 3: Implement the module**

Create `importers/reliability.py`:

```python
"""Per-account reliability verdicts for an imported balance sheet.

An import can BALANCE AND BE FALSE. The reference case is 613_2024: 2,25M of
fondi ammortamento stay booked as debts, the assets stay gross (4,98M instead
of 3,13M), every gate passes and the file is saved as `verified`.

This module turns evidence the pipeline already computes into a verdict on the
three accounts that decide every KPI. It is a PURE function: dicts in, verdict
out, no I/O.

Design rule: UNRELIABLE requires POSITIVE evidence of contradiction, never the
mere absence of a control. A route A/B file runs no contra scan at all; an
abbreviated statement prints no patrimonio-netto subtotal. Treating those as
unreliable would block most of the corpus.
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

Z = Decimal('0')


class AccountStatus(Enum):
    VERIFIED = 'verified'      # corroborated by independent source evidence
    DERIVED = 'derived'        # inferred but internally consistent
    UNRELIABLE = 'unreliable'  # evidence says the figure is probably wrong


_BANK_FIELDS = ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo')
_NON_BANK_SHORT = (
    'sp16b_debiti_altri_finanz_breve', 'sp16c_debiti_obbligazioni_breve',
    'sp16d_debiti_fornitori_breve', 'sp16e_debiti_tributari_breve',
    'sp16f_debiti_previdenza_breve', 'sp16g_altri_debiti_breve',
)
_NON_BANK_LONG = (
    'sp17b_debiti_altri_finanz_lungo', 'sp17c_debiti_obbligazioni_lungo',
    'sp17d_debiti_fornitori_lungo', 'sp17e_debiti_tributari_lungo',
    'sp17f_debiti_previdenza_lungo', 'sp17g_altri_debiti_lungo',
)


def _d(bs: dict, key: str) -> Decimal:
    value = bs.get(key)
    if value is None:
        return Z
    return value if isinstance(value, Decimal) else Decimal(str(value))


def materiality_threshold(total: Decimal) -> Decimal:
    """M = max(1.000 EUR; 0,1% del totale attivo).

    Canonical definition for the whole import pipeline. This module is pure and
    dependency-free, so every other module imports it from here rather than
    re-deriving it (Task 3 defined a temporary copy in
    situazione_contabile_parser; Step 5 below replaces it with a re-export).
    """
    return max(Decimal('1000'), abs(total or Z) * Decimal('0.001'))


_threshold = materiality_threshold   # internal alias


@dataclass(frozen=True)
class ReliabilityReport:
    immobilizzazioni: AccountStatus
    immobilizzazioni_reason: str
    patrimonio_netto: AccountStatus
    patrimonio_netto_reason: str
    debiti_banche: AccountStatus
    debiti_banche_reason: str
    unclassified_mass: Decimal = Z

    @property
    def all_critical_ok(self) -> bool:
        return AccountStatus.UNRELIABLE not in (
            self.immobilizzazioni, self.patrimonio_netto, self.debiti_banche)

    def to_dict(self) -> dict:
        return {
            'immobilizzazioni': {'status': self.immobilizzazioni.value,
                                 'reason': self.immobilizzazioni_reason},
            'patrimonio_netto': {'status': self.patrimonio_netto.value,
                                 'reason': self.patrimonio_netto_reason},
            'debiti_banche': {'status': self.debiti_banche.value,
                              'reason': self.debiti_banche_reason},
            'unclassified_mass': str(self.unclassified_mass),
            'all_critical_ok': self.all_critical_ok,
        }


def _assess_immobilizzazioni(bs: dict):
    if '_contra_detected' not in bs:
        return (AccountStatus.DERIVED,
                'nessuno scan contro-conti per questa rotta (schema di legge)')
    detected = _d(bs, '_contra_detected')
    applied = _d(bs, '_contra_applied')
    reason = bs.get('_contra_reason') or ''
    if detected <= Z:
        return (AccountStatus.DERIVED,
                'nessuna massa contro rilevata: il documento e gia netto')
    if applied > Z:
        return (AccountStatus.VERIFIED,
                f'contro-conti riconciliati e applicati ({applied:,.2f})')
    return (AccountStatus.UNRELIABLE,
            f'rilevati {detected:,.2f} di contro-conti NON applicati '
            f'({reason}): immobilizzazioni lorde e fondi fra i debiti')


def _assess_patrimonio_netto(bs: dict, declared: Optional[dict]):
    computed = (_d(bs, 'sp11_capitale') + _d(bs, 'sp12_riserve')
                + _d(bs, 'sp13_utile_perdita'))
    printed = (declared or {}).get('patrimonio_netto')
    if printed is None:
        return (AccountStatus.DERIVED,
                'nessun totale patrimonio netto stampato da confrontare')
    printed = printed if isinstance(printed, Decimal) else Decimal(str(printed))
    gap = abs(computed - printed)
    if gap <= _threshold(_d(bs, 'totale_attivo')):
        return (AccountStatus.VERIFIED,
                f'riconcilia col totale stampato ({printed:,.2f})')
    return (AccountStatus.UNRELIABLE,
            f'ricostruito {computed:,.2f} contro {printed:,.2f} stampato '
            f'(scarto {gap:,.2f})')


def _assess_debiti_banche(bs: dict):
    explicit = sum((_d(bs, f) for f in _BANK_FIELDS), Z)
    short_gap = _d(bs, 'sp16_debiti_breve') - (
        _d(bs, 'sp16a_debiti_banche_breve')
        + sum((_d(bs, f) for f in _NON_BANK_SHORT), Z))
    long_gap = _d(bs, 'sp17_debiti_lungo') - (
        _d(bs, 'sp17a_debiti_banche_lungo')
        + sum((_d(bs, f) for f in _NON_BANK_LONG), Z))
    gap = max(Z, short_gap) + max(Z, long_gap)
    if gap > _threshold(_d(bs, 'totale_attivo')):
        return (AccountStatus.UNRELIABLE,
                f'{gap:,.2f} di debiti non tipizzati: base_bank_debt li '
                f'attribuirebbe alle banche, gonfiando la PFN')
    if explicit > Z:
        return (AccountStatus.VERIFIED,
                f'letti da sotto-campi espliciti ({explicit:,.2f})')
    return (AccountStatus.DERIVED,
            'nessuna esposizione bancaria e nessuno scarto da attribuire')


def assess(bs: dict, ce: dict,
           declared: Optional[dict] = None) -> ReliabilityReport:
    """Verdict on the three accounts that decide every KPI.

    `bs` uses full DB field names and may carry the `_contra_*` metadata written
    by net_contra_accounts. `declared` may carry a 'patrimonio_netto' control
    total read from the document. `ce` is accepted for symmetry and future use.
    """
    immo_status, immo_reason = _assess_immobilizzazioni(bs)
    pn_status, pn_reason = _assess_patrimonio_netto(bs, declared)
    bank_status, bank_reason = _assess_debiti_banche(bs)
    return ReliabilityReport(
        immobilizzazioni=immo_status, immobilizzazioni_reason=immo_reason,
        patrimonio_netto=pn_status, patrimonio_netto_reason=pn_reason,
        debiti_banche=bank_status, debiti_banche_reason=bank_reason,
        unclassified_mass=_d(bs, '_unclassified_mass'),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m pytest tests/test_reliability.py -q -p no:randomly`

Expected: 13 passed

- [ ] **Step 5: Remove the duplicated threshold formula**

Task 3 defined `materiality_threshold` inside `situazione_contabile_parser`. The canonical
definition now lives in the pure `reliability` module, so replace the parser's copy with a
re-export. In `importers/situazione_contabile_parser.py`, delete the whole
`def materiality_threshold(total: Decimal) -> Decimal:` function (including its docstring and
`return`) and put in its place:

```python
# Canonical definition lives in the dependency-free reliability module so the
# import pipeline has exactly one materiality rule.
from importers.reliability import materiality_threshold  # noqa: E402,F401
```

- [ ] **Step 6: Verify both test files still pass against the single definition**

Run: `backend/venv/bin/python -m pytest tests/test_reliability.py tests/test_fallback_bucket.py -q -p no:randomly`

Expected: 26 passed. `tests/test_fallback_bucket.py::test_threshold_*` now exercise the
re-exported function, proving the two modules share one rule.

- [ ] **Step 7: Commit**

```bash
git add importers/reliability.py importers/situazione_contabile_parser.py tests/test_reliability.py
git commit -m "feat(import): per-account reliability verdicts

Pure module: turns evidence the pipeline already computes into a verdict on
immobilizzazioni nette, patrimonio netto and debiti verso banche. UNRELIABLE
requires positive contradiction, never a missing control, so route A/B and
abbreviated statements are unaffected.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Gate `forecastable` on the verdict

`forecastable` currently depends only on `semantic_valid`, which knows nothing about discarded contra-accounts. This wires the verdict in — gating the *forecast*, never the *save*, so Rettifiche can still reach the record.

**Files:**
- Modify: `importers/pdf_importer.py` (`_validation_report_payload` at `:26`, the current-year `FinancialYear` at `:1102-1111`, the prior-year one at `:1190-1200`)
- Test: `tests/test_reliability_gating.py` (create)

**Interfaces:**
- Consumes: `reliability.assess(bs, ce, declared) -> ReliabilityReport`; `_validation_report_payload(q) -> dict`
- Produces: `validation_report["critical_accounts"]` in the persisted JSON; `forecastable = semantic_valid and all_critical_ok`

- [ ] **Step 1: Write the failing test**

Create `tests/test_reliability_gating.py`:

```python
"""The reliability verdict gates the FORECAST, never the SAVE.

An unreliable file must still be persisted: Rettifiche operates on a saved
FinancialYear, so refusing to save would make the file uncorrectable.
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.pdf_importer import _validation_report_payload  # noqa: E402
from importers.reliability import AccountStatus, assess        # noqa: E402

D = Decimal


class _FakeQ:
    """Minimal stand-in for the check_quadratura result."""
    sbilancio = D("0")
    utile_match = True
    hierarchy_consistent = True
    semantic_valid = True
    masked = False
    is_empty = False
    totale_attivo = D("2000000")
    totale_passivo = D("2000000")
    utile_ce = D("100000")
    sp13 = D("100000")
    plug_residual = D("0")
    hierarchy_differences: dict = {}
    warnings: list = []


def test_payload_carries_critical_accounts_when_a_report_is_given():
    bs = {"_contra_detected": D("2247715.70"), "_contra_applied": D("0"),
          "_contra_reason": "non applicati", "totale_attivo": D("2000000")}
    report = assess(bs, {})
    payload = _validation_report_payload(_FakeQ(), reliability=report)
    assert payload["critical_accounts"]["immobilizzazioni"]["status"] == "unreliable"
    assert payload["critical_accounts"]["all_critical_ok"] is False


def test_payload_omits_critical_accounts_when_no_report_is_given():
    payload = _validation_report_payload(_FakeQ())
    assert "critical_accounts" not in payload


def test_unreliable_immobilizzazioni_blocks_forecastable():
    bs = {"_contra_detected": D("2247715.70"), "_contra_applied": D("0"),
          "_contra_reason": "non applicati", "totale_attivo": D("2000000")}
    report = assess(bs, {})
    forecastable = _FakeQ.semantic_valid and report.all_critical_ok
    assert forecastable is False


def test_clean_sheet_stays_forecastable():
    bs = {"_contra_detected": D("1000"), "_contra_applied": D("1000"),
          "totale_attivo": D("2000000")}
    report = assess(bs, {})
    assert report.all_critical_ok is True
    assert (_FakeQ.semantic_valid and report.all_critical_ok) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m pytest tests/test_reliability_gating.py -q -p no:randomly`

Expected: FAIL — `TypeError: _validation_report_payload() got an unexpected keyword argument 'reliability'`

- [ ] **Step 3: Extend the payload builder**

In `importers/pdf_importer.py`, change the signature at line 26:

```python
def _validation_report_payload(q, reliability=None) -> Dict[str, Any]:
```

and, immediately before its `return`, build the dict into a local so the key can be added conditionally. Replace `return {` with `payload = {`, then after the closing `}` of that dict add:

```python
    if reliability is not None:
        payload["critical_accounts"] = reliability.to_dict()
    return payload
```

- [ ] **Step 4: Run the payload tests**

Run: `backend/venv/bin/python -m pytest tests/test_reliability_gating.py -q -p no:randomly`

Expected: 4 passed

- [ ] **Step 5: Compute the verdict in the import path**

`_dc0` (the declared control totals) is computed only on the route-C branch, so it is not
in scope for route A/B. Capture it explicitly instead of probing the namespace.

First, immediately **after** the line `mapper = IVCEEMapper()` near the top of
`import_pdf_balance_sheet`, add:

```python
        # Declared control totals, when the route computed any. Initialised here so
        # the reliability step below is in scope for EVERY route, not just route C.
        _declared_for_reliability = None
```

Then, on the route-C branch, immediately **after** the line that assigns `_dc0` (find it with
`grep -n "_dc0 = " importers/pdf_importer.py`), add:

```python
                _declared_for_reliability = _dc0
```

Finally, immediately **before** the line `_validation_payload = _validation_report_payload(_qd)`
(~line 1101), insert:

```python
        # Reliability of the accounts that decide every KPI. Never allowed to
        # turn a working import into a failure: any error means "unknown".
        _reliability = None
        try:
            from importers.reliability import assess as _assess_reliability
            _reliability = _assess_reliability(
                balance_sheet_data, income_data,
                declared=_declared_for_reliability)
        except Exception as _rel_err:
            logger.warning(f"Reliability non calcolata: {_rel_err}")
```

- [ ] **Step 6: Fold the verdict into the persisted record**

Replace:

```python
        _validation_payload = _validation_report_payload(_qd)
```

with:

```python
        _validation_payload = _validation_report_payload(_qd, reliability=_reliability)
        _critical_ok = _reliability is None or _reliability.all_critical_ok
        _forecastable = _qd.semantic_valid and _critical_ok
```

Then in the `FinancialYear(...)` constructor change these two lines:

```python
            validation_status=("verified" if _qd.semantic_valid else "review_required"),
            ...
            forecastable=_qd.semantic_valid,
```

to:

```python
            validation_status=("verified" if _forecastable else "review_required"),
            ...
            forecastable=_forecastable,
```

Leave the **prior-year** block (~`:1190-1200`) unchanged: the prior year already has a stricter admission standard and carries no contra metadata of its own.

- [ ] **Step 7: Verify 613 is now blocked and 615/342 are not**

```bash
SCRATCH=$(mktemp -d)
for f in "tests/debug/budget_615_2024 Lavori di meccanica generale.pdf" \
         "tests/debug/budget_342_BILANCIO PROVVISORIO AL 30-04-2026.pdf"; do
  rm -f "$SCRATCH/t.db"
  DATABASE_PATH="$SCRATCH/t.db" \
  ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' .env.docker | cut -d= -f2- | tr -d '\r\n') \
  backend/venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from database.db import init_db; init_db()
from importers.pdf_importer import import_pdf_balance_sheet
r = import_pdf_balance_sheet(file_path='''$f''', fiscal_year=2024,
      company_name='GATE TEST', create_company=True, sector=1, user_id='t')
print('$f'.split('/')[-1][:40], '->', r['validation_status'], 'forecastable=', r['forecastable'])
print('  critical:', r['validation_report'].get('critical_accounts', {}).get('all_critical_ok'))
"
done
rm -rf "$SCRATCH"
```

Expected: both files report `all_critical_ok: True` and keep the `forecastable` value they had before this task. If either flips to `False`, the verdict is over-firing — investigate before continuing.

- [ ] **Step 8: Quantify the corpus impact**

Run the route-C runner over every available PDF and count how many files would now lose `forecastable`:

```bash
backend/venv/bin/python tests/_prod_route_c_runner.py tests/debug 2>/dev/null | grep -v "^WARNING"
```

Record the count in the commit message. A material drop is expected and intended (613-class files), but it must be *known*, not discovered later in production.

- [ ] **Step 9: Full suite**

Run: `backend/venv/bin/python -m pytest tests/ -q -p no:randomly 2>&1 | tail -5`

Expected: 0 failures.

- [ ] **Step 10: Commit**

```bash
git add importers/pdf_importer.py tests/test_reliability_gating.py
git commit -m "feat(import): gate forecastable on the critical-account verdict

forecastable depended only on semantic_valid, which knows nothing about
discarded contra-accounts: 613 was saved as verified with gross assets and
2,25M of fondi among the debts. The verdict now gates the FORECAST, never the
SAVE - an unreliable file must stay persisted so Rettifiche can reach it.
Existing records are not re-evaluated; the rule applies on import only.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Final end-to-end verification

**Files:**
- Modify: none (verification only)

**Interfaces:**
- Consumes: everything above
- Produces: a recorded before/after statement for the handover

- [ ] **Step 1: Full suite, clean**

Run: `backend/venv/bin/python -m pytest tests/ -q -p no:randomly 2>&1 | tail -5`

Expected: 0 failed. Note the pass/skip counts against the Task 0 baseline.

- [ ] **Step 2: Route-C corpus, no regressions**

Run: `backend/venv/bin/python tests/_prod_route_c_runner.py tests/debug 2>/dev/null | grep -v "^WARNING"`

Expected: `budget_615`, `budget_342`, `AITEC`, `6 - LIO` all still `SI` with `plug 0.00`.

- [ ] **Step 3: Confirm the spec-2 fixture is still honestly rejected**

`tests/debug/Bilancio_Riclassificato DEF.pdf` fails for route-B reasons (swapped years, section C read as D, aggregates and sub-fields from different columns) that are **out of scope here**. It must still be rejected, and for the *same* reason as before — not a new one.

```bash
SCRATCH=$(mktemp -d) && DATABASE_PATH="$SCRATCH/t.db" \
ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' .env.docker | cut -d= -f2- | tr -d '\r\n') \
backend/venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from database.db import init_db; init_db()
from importers.pdf_importer import import_pdf_balance_sheet, PDFImportError
try:
    r = import_pdf_balance_sheet(
        file_path='tests/debug/Bilancio_Riclassificato DEF.pdf', fiscal_year=2025,
        company_name='RICLASS', create_company=True, sector=1, user_id='t')
    print('IMPORTED:', r['validation_status'], r['forecastable'])
except PDFImportError as e:
    print('REJECTED:', e)
"; rm -rf "$SCRATCH"
```

Expected: `REJECTED: ... Utile CE 45.082 != sp13 17.305 (diff 27.777)` — the same message as the 2026-07-29 baseline in the spec §9. A *different* rejection message means one of these tasks changed route-B behaviour, which it must not.

Ground truth for spec 2 (from the document's text layer, both years verified to the cent):

| | 2025 (current) | 2024 (prior) |
|---|---|---|
| TOTALE ATTIVO = PASSIVO | 1.758.609 | 1.836.998 |
| Totale patrimonio netto | 160.307 | 288.301 |
| Utile (perdita) | −127.995 | 17.305 |
| EBIT / EBITDA | −81.422 / −48.438 | 61.025 / 98.875 |

- [ ] **Step 4: Update the audit document status**

In `docs/piano-import-2026-07/14-AUDIT-CLASSIFICAZIONE-E-NETTING-2026-07-27.md` §0, change the **Stato** column for N1, N2, N3, C1 from `confermato` to `RISOLTO 2026-07-29 (piano import-critical-accounts)`. Leave C2, D1 and T1 as they are — C2 (silent catch-all diagnostics) and D1 (CLAUDE.md staleness) are not addressed by this plan.

- [ ] **Step 5: Commit**

```bash
git add docs/piano-import-2026-07/14-AUDIT-CLASSIFICAZIONE-E-NETTING-2026-07-27.md
git commit -m "docs: mark netting/classification findings resolved

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Known follow-ups (NOT in this plan)

| # | Item | Where it goes |
|---|---|---|
| C2 | `_unclassified` diagnostic mass + wiring `fallback_bucket` into the remaining catch-all sites | next backend spec |
| D1 | `CLAUDE.md` still documents plug/realignment behaviour the code no longer has | doc-only cleanup |
| — | Frontend: KPI/rating panels reading `critical_accounts`, pre-filled Rettifiche suggestions | frontend spec |
| — | Route-B dual-year column assignment + section C vs D | **spec 2**, fixture `Bilancio_Riclassificato DEF.pdf` |
| — | Corpus "decency" metric (rettifiche-to-green per file) | harness spec |
