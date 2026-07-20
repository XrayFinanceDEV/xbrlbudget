# Fixing PDF trial-balance import — discoveries & playbook

A practical guide to diagnosing and fixing "does not balance / failed to extract"
errors on **route-C** files (situazione contabile / sezioni contrapposte). Written
from the budget_615 investigation (2026-07) but the principles are general.

See also: `docs/import/IMPORT-ROUTING-TAXONOMY.md` (macro-area router) and the
per-file diagnosis in `docs/piano-import-2026-07/`.

---

## 0. The pipeline, in one breath

```
classify_bilancio (route A/B/C/XBRL)
  └─ route C: extract_situazione_contabile  → build_iv_cee  → bs/ce dicts (SHORT keys)
       └─ pdf_importer: _map_sc_keys (short→full DB names)
            └─ net_contra_accounts → _reconcile_trial_to_declared → enforce_ce_sp_identity
                 └─ validate_balance   ← the HARD gate (import passes/fails here)
```

Two things are easy to confuse:
- **`validate_balance`** is the only hard structural gate. If it passes, the file
  imports (a large residual is a *non-blocking* `BILANCIO NON QUADRATO` flag, not a
  rejection).
- **`check_quadratura` / CE↔SP identity** is a cross-check that adds warnings; it does
  not by itself block import.

**"Does the harness say NO" ≠ "won't import".** The quadratura harness runs
`extract → check_quadratura` but NOT the production `reconcile`/`enforce` stages, so a
harness NO can still import. To answer "does this PDF import?", run the real
`import_pdf_balance_sheet` path (deterministic = no `ANTHROPIC_API_KEY`).

---

## 1. Architectural principles (do these; the rest is mechanics)

1. **Route by statement type → recognize accounts by description → reconcile to IV-CEE.**
   Recognition is by **description** (`iv_cee_hierarchy.resolve(desc, side, statement)`),
   which returns the IV-CEE node incl. `.statement` (`bs`/`ce`) and `.db_field`.

2. **NEVER classify by account-code prefix.** `71 = ricavi`, `73 = costi`, `1x/3x = SP`,
   `7x/8x = CE` etc. are **gestionale-specific** and change between charts of accounts.
   They looked right on one file and were wrong on the next. Use description recognition
   for statement/field; use physical layout for side (below).

3. **The physical COLUMN is ground truth for the side.** In a contrapposte layout the
   left column is the debit-nature side (**attivo / costi**) and the right is the
   credit-nature side (**passivo / ricavi**), regardless of code. Verified exact on
   budget_615 (costi/ricavi split purely by column).

4. **The RISULTATO (utile/perdita) is the balancing figure.** These trial balances are
   not self-balancing on the raw accounts; the period result closes them
   (`utile = attivo − passivo_excl_result = ricavi − costi`). If the SP footer totals are
   unreadable, derive the result from the CE (`ricavi − costi`). If the derived result
   and the SP gap disagree, that gap is **missing account mass**, not a bigger result —
   recover the mass, don't inflate the result.

5. **Self-validate every reconstruction; never plug silently.** Any recovery/plug must be
   gated on the balance identity (`attivo == passivo`, `utile == ricavi − costi`) and, if
   it doesn't tie, fall back unchanged. A recovery that can only *improve* a sheet (or
   no-op) can never regress the corpus — important because the full corpus is often not
   present in a checkout to regression-test against.

6. **Additive-only changes.** When the corpus can't be run locally, make new behavior
   trigger ONLY on the failing sub-case (e.g. header-less pages, empty results, plug > 1%)
   so files that already extract are provably untouched.

---

## 2. Coordinate-geometry gotchas (route-C, coordinate parsers)

These bit us on budget_615 (AGO "Situazione Contabile", landscape, **not rotated**):

- **Split axis.** A rotated contrapposte page stacks the two columns along **y** (headers
  share x); an unrotated landscape export puts them side by side along **x** (headers
  share y). Pick the axis on which the two header words actually differ — assuming
  "rotated" on an unrotated page collapses everything into one column (`totale_passivo=0`).
  See `_c8_split_columns` / `_c8_parse_side(axis=…)`.

- **Derive the gutter from the DATA, not the header words.** Amounts are right-aligned:
  the LEFT side's amount column can sit just left of the RIGHT side's code column
  (budget_615: attivo amounts x≈357–379, passivo codes x=417). The header-word midpoint
  (365) fell *inside* the attivo amount band → those amounts leaked to the passivo reader
  and were lost (~260k). Put the gutter in the clean vertical gap **before the right-hand
  code column** (`_c8_refine_gutter_x`), and only override the header gutter when it falls
  outside that gap (additive).

- **Vector-drawn text is invisible to the text layer.** Bold rows, grey bars, and often
  the section headers (`CONTO ECONOMICO`, `ATTIVITA'`, `TOTALE …`) and footer totals are
  drawn as **vectors**, not text → `page.get_text()` returns nothing for them. Consequences:
  - Pages whose headers are vector get **skipped** by a header-driven pass. Read them in a
    second pass via the document-level gutter, deciding SP-vs-CE by **account recognition**
    (first majority-CE page starts the CE section, contiguous to EOF), not code prefixes.
  - A CE **footer** page may still carry live `COSTI`/`RICAVI` tokens that are the
    "**TOTALE** COSTI/RICAVI" *summary* labels — picking them as column headers yields a
    bogus gutter and an empty split. Only mark a page "read" if its split actually yielded
    entries; otherwise let the second pass handle it.
  - Declared footer totals being vector means `_declared_control_totals` may return the
    **CE** total (`pareggio` = TOTALE RICAVI) with `attivo=None/passivo=None`. Don't let a
    CE section total anchor the SP reconcile.

- **Corrupted amounts (`_`-interlaced glyphs).** The underline on detail rows is drawn as
  `_` glyphs interlaced *inside* the amount token (`_2_.00_0_,_0_0_` = 2.000,00). Mastro
  amounts are usually clean; **detail amounts are usually corrupted**. So:
  - You cannot sum details to substitute a total in general (most are unparseable).
  - Where you *must* read a detail (an orphan whose mastro total is vector), strip `_`
    before parsing — and rely on the **self-validation gate** to reject any mis-strip
    (a wrong number won't reconcile to the known gap).

---

## 3. Orphan-mastro recovery (when a total line is vector-drawn)

Problem shape: the SP balances except for N account totals whose 8-digit **mastro** line
is vector-drawn (unreadable); only their 6-digit **dettagli** survive (on a
dettaglio-only page), and those dettaglio amounts are `_`-corrupted but recoverable.

Approach that works (see `_c8_recover_orphan_passivo`):
1. Only act when the sheet is short on one side (`gap = attivo − passivo > 0`).
2. Read the clean dettagli (strip `_`) on dettaglio-only pages (no 8-digit mastro), on the
   short side, recognizing each by description (`resolve`).
3. Add back **only the subset whose amounts sum EXACTLY to the gap**
   (`_unique_subset_summing_to`; refuse if zero or >1 subset). This automatically excludes
   dettagli whose parent mastro was already captured (they don't fit the gap) — you don't
   need the (unavailable) 6-digit→8-digit chart-of-accounts hierarchy.
4. Route to the SHORT SC keys (`sp16`/`sp17`/`sp18`), keeping aggregate == Σ sub-fields so
   the hierarchy check stays coherent.
5. **Keep the result only if the sheet then balances.** Otherwise return unchanged.

Why not "recognize all accounts and reconcile by control-total"? That's the right model
in general, but on files where detail amounts are corrupted the control-total inputs are
unreliable — so the recovery must be targeted and self-validated instead.

---

## 4. How to work a new failing file

1. **Reproduce on the real path**, deterministically:
   ```python
   import os; os.environ.pop('ANTHROPIC_API_KEY', None)
   from importers.pdf_importer import import_pdf_balance_sheet
   import_pdf_balance_sheet(path, create_company=False, fiscal_year=YYYY)
   ```
   A `PDFImportError` about balance/format = real failure. Reaching the company step
   ("company_id or company_name required") = **validation passed**.

2. **Inspect geometry** with PyMuPDF `page.get_text('words')`: per-page code x/y clusters,
   amount x-bands, which headers exist as live tokens vs vector. Most route-C bugs are a
   wrong gutter, a skipped page, or a mis-signed/mis-sectioned column — all visible here.

3. **TDD with a debug fixture.** Drop the PDF in `tests/debug/` and gate the test on its
   presence (`@pytest.mark.skipif(not os.path.exists(PDF), …)`), mirroring the existing
   evidence-PDF pattern (binaries are not committed; the test skips in CI without them).
   Assert against numbers you verified from the PDF rendering.

4. **Keep it additive + self-validated** (§1.5–1.6). Re-run `tests/test_c8_split_axis.py`
   and, when available, `tests/_quadratura_harness.py` for before/after masking rate.

---

## 5. budget_615 case study (summary)

AGO "Situazione Contabile", landscape non-rotato, testo parzialmente distrutto (export
AGO 06.07.00). Before: read only the 1 page with live headers (attivo ≈ 396k vs declared
2.828k) → HTTP 422. Fixes (all in `importers/situazione_contabile_parser.py`, tests in
`tests/test_c8_split_axis.py`):

| Fix | Effect |
|---|---|
| Split-axis detection (`axis=0` for unrotated) | passivo 0 → read |
| Data-derived gutter (`_c8_refine_gutter_x`) | attivo amounts stop leaking → attivo exact 2.828.226,30 |
| Second pass for vector-header pages + description-based SP→CE boundary | CE pages read; costi 1.323.220,24 / ricavi 1.456.925,50 exact |
| Don't mark a page read if its split is empty | CE footer page's 1.354 no longer dropped |
| Utile from CE when SP footer vector | sp13 = 133.705,26 |
| Targeted self-validated orphan recovery | +55.536,60 (ratei/risconti → sp18, altri debiti OE → sp17) → **attivo == passivo == 2.096.501,91** |

Result: imports cleanly; CE net (full keys) = 133.705,26 = sp13.
