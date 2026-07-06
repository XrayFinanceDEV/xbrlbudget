# Contra-netting overlay for route-C trial balances

**Date:** 2026-07-06
**Status:** Design approved (pending written-spec review)
**Area:** `importers/` — PDF route-C (situazione contabile / bilancio di verifica, "sezioni contrapposte")

## Problem

Gross-presentation trial balances ("bilancio di verifica" / "sezioni contrapposte") list
`fondo ammortamento` (accumulated depreciation) as **separate accounts on the PASSIVITÀ side**.
Under OIC these are contra-assets: they must be **netted against the gross immobilizzazioni**
(`sp02`/`sp03`), never booked as liabilities.

On the route-C path the winning extractor is often the **CoGe LLM** (`extract_trial_balance_with_llm`),
which has **no Python-side netting** — it relies entirely on Haiku following the prompt. When Haiku
fails to net (observed, stochastic), the whole fondi mass lands in `Altri debiti` and the asset side
stays near-gross. The deterministic parsers *do* have netting rules but are unreliable on these AGO
8-digit layouts (they under-capture / don't balance), so they lose candidate selection and cannot save
the result.

### Reproduced evidence (the two example files)

Source: `docs/examples/613_2024 …pdf` (Bilancio di Verifica, AGO 8-digit) and
`docs/examples/612_2025 …pdf` (Situazione Contabile). Generated report: `docs/examples/Edile-rating-basso.pdf`.

- Report 2024 `Altri debiti = 2.035.409 €` reconciles **to the cent** as
  `fondi ammortamento 1.853.799,20 + real debts 181.609,82`. So ~91% of the "debt" is accumulated
  depreciation, not debt.
- Consequences: `Current ratio 0,03`, `CCN −1.983.907`, `Margine di struttura −1.993.998`,
  `Copertura immob. 59,5%` → an artificial **D / C2 "Rischio grave"** rating on a company whose real
  profile is sound (equity €2,93M, real debt ~€182k, mostly a long-term mutuo + a postergato soci loan).
- Deterministic reproduction (`extract_situazione_contabile`, no LLM): 2024 nets only ~313k of the
  1,84M tangible fondi and **does not balance** (attivo 4.699.290 ≠ passivo 2.888.526); 2025 falls to
  best-effort and produces garbage (passivo 10,06M ≈ double). Both lose to the LLM candidate.

Secondary observation: the CE (`ce09` ammortamento cost) is unaffected by this bug — accumulated
depreciation (the fund) and the period depreciation cost are different figures.

## Goal

A single, deterministic, extractor-agnostic **post-extraction netting stage** that runs on the chosen
route-C candidate (LLM, deterministic, or best-effort; generated **or** scanned PDF) and:

1. nets `fondo ammortamento` off `sp02`/`sp03` (**primary, high value, unambiguous**);
2. nets offsettable IVA (secondary, conservative — only when both credit and debit sides exist);
3. leaves every other contra item gross (out of scope);
4. can **never regress** a file that was already correct (self-validation gate + no-op fallback).

Non-goal (separate follow-up): fixing the deterministic AGO/`build_iv_cee` balance bug. This design
corrects the report without depending on it.

## Approach (chosen: A — unified overlay)

Add the stage next to the existing `overlay_debt_typing` precedent in `pdf_importer`'s route-C block.
Deterministic authority: re-read the source text and **overwrite** `sp02`/`sp03` with net values, rather
than trying to detect whether an extractor already netted (fragile, and double-subtraction risk).

Rejected alternatives:
- **B — fix each extractor**: larger surface; the LLM half stays non-deterministic (a prompt tweak does
  not *guarantee* netting), so we'd want A as a safety net anyway.
- **C — post-LLM pass only**: covers only the LLM route; best-effort and future extractors stay exposed.

## Component design

### New function

`net_contra_accounts(winner_bs, file_path, text, declared_totals) -> (bs, netted_contra)`
in `importers/situazione_contabile_parser.py` (co-located with `_is_fondo_amm`,
`_classify_sp_attivo`/`_classify_sp_passivo`, `overlay_debt_typing`, and the debt/contra helpers it
reuses). Pure, deterministic, no LLM. Mutates and returns `winner_bs`; conservative — **no-op unless
clearly beneficial**, mirroring `overlay_debt_typing`. On any validation failure returns
`(winner_bs_unchanged, Decimal('0'))`.

### 1. Deterministic contra-scan (core primitive)

A robust scan of the SITUAZIONE PATRIMONIALE region that must be **more robust than `parse_entries_ago`**
(which drops most passivo blocks on these files). It sums only specific keyworded lines — a far lower bar
than a full, balanced parse.

Two input modes so both generated and scanned PDFs are covered:
- **Generated PDF** (`page.get_text("words")` non-empty): coordinate-aware — reconstruct rows by
  y-coordinate, split the two columns at the x-gutter (same coordinate approach `is_contrapposte_file`
  already uses), pair each description with the amount on its own row.
- **Scanned PDF** (no word coords): parse the OCR string (`text` / `ocr_text`) line by line. Lower
  fidelity, but the self-validation gate (below) rejects a misread scan rather than corrupting the sheet.

Both modes feed the same classification + summation:
- `gross_sp02` / `gross_sp03` — asset-side immobilizzazioni lines via `_classify_sp_attivo`,
  **excluding** anything matching `_is_fondo_amm`.
- `fondi_immat` / `fondi_mat` — every line matching the **broad** `_is_fondo_amm` guard, split
  immat/mat, **parent-vs-detail deduplicated**: sum mastri OR leaves, never both. (In `613_2024` the
  mastro `F.do amm fabbricati 1.779.795,83` already equals its two sub-accounts `1.416.504,33 +
  363.291,50` — counting both double-counts.) Dedup rule: a mastro is excluded when its own detail
  children (whose codes extend the mastro code) are present and sum to it within tolerance; otherwise
  the mastro is kept and its (absent) children ignored.
- `iva_credito` / `iva_debito` — IVA lines (`ERARIO C/IVA`, `IVA C/ACQUISTI`, `IVA C/VENDITE`, …),
  captured per side. Only used when **both** sides exist.

### 2. Apply (deterministic authority)

```
iva_offset  := min(iva_credito, iva_debito)          # 0 if only one side present
netted_contra := fondi_immat + fondi_mat + iva_offset

sp02 := gross_sp02 − fondi_immat                      # overwrite extractor
sp03 := gross_sp03 − fondi_mat                        # overwrite extractor
# IVA: collapse to the net erario position on the larger side; drop the smaller.
# remove netted_contra from the debt buckets: sp16 'altri' (sp16g) first, then sp16, floor 0
winner_bs['_contra_netted'] := netted_contra          # consumed by pdf_importer (see wiring)
```

Removing the contra mass from the debt bucket + reducing the declared anchor by the same amount keeps
the sheet balanced (gross-presentation ties gross-attivo == passivo-incl-fondi; subtracting the same
fondi from both sides preserves `attivo == passivo`).

### 3. Self-validation gate (never regress)

Apply only when **both** hold:
- `netted_contra > 1%` of the declared total (there is real contra to net), **and**
- `gross_sp02 + gross_sp03 (scanned) + current_assets(from winner_bs) ≈ declared TOTALE ATTIVO`
  within **0.5%** (the scan reconciles to the document's own gross total — proves we read the right
  magnitudes).

If either fails → **no-op**, `log()` the reason, return the extractor's sheet untouched. This is what
makes the stage safe for already-net IV-CEE-style trial balances (no fondi found → `netted_contra ≈ 0`
→ gate fails → no-op) and for OCR misreads (reconciliation fails → no-op).

## Data flow / wiring in `pdf_importer.import_pdf_balance_sheet`

Route-C block, after the winning candidate is chosen (`pdf_importer.py:445`) and after
`overlay_debt_typing` (`:453-457`):

1. Choose winner (existing).
2. `overlay_debt_typing` when the LLM won (existing).
3. **NEW:** `balance_sheet_data, _contra = net_contra_accounts(balance_sheet_data, file_path, ocr_text, _dc0)`
   — `_dc0` is the declared control totals already fetched at `pdf_importer.py:429` for the completeness
   gap; reuse it (or fetch via `_declared_control_totals` if unavailable) for the self-validation gate.
4. `_authoritative = balance_sheet_data.pop('_skip_declared_reconcile', False)` (existing).
5. Declared-result reconcile (existing `:467-477`), **modified**: pop `_contra_netted` and **reduce the
   declared totals by it** before `_reconcile_trial_to_declared`, so the reconcile plugs to the **net**
   total instead of re-inflating back to gross. (This reuses the existing "reduce anchor by netted
   contra" pattern — cf. best-effort `iv_total = tb_total − netted_contra`.)
6. `enforce_ce_sp_identity` (existing `:533+`) unaffected — `sp13` (result) is untouched by symmetric
   asset/debt netting; the CE is not modified by this stage.
7. `validate_balance` (existing) — balance preserved; if netting somehow left a residual, the existing
   `BILANCIO NON QUADRATO` flag surfaces it for Rettifiche.

`_contra_netted` is popped before the DB write so it never leaks into a model field. When the stage
no-ops, `_contra_netted` is 0 / absent and every downstream step behaves exactly as today.

## Edge cases

- **No fondi in the document** (already-net sheet) → gate fails → no-op.
- **Fondi already netted by the extractor** → deterministic authority overwrites with the same net value;
  debt-bucket subtraction floors at 0 so it cannot go negative; anchor reduction still consistent.
- **Fondi only on the asset side** (rare gross-on-asset presentation) → `_classify_sp_attivo` excludes
  them from gross, `_is_fondo_amm` still sums them; netting subtracts from the correct asset class.
- **Mastro + detail both present** → dedup rule prevents double counting.
- **IVA one-sided** → left gross (conservative).
- **Scanned PDF with poor OCR** → reconciliation gate fails → no-op (honest, no corruption).

## Testing

New test module `tests/test_contra_netting.py`:

1. **End-to-end, both example files** (`613_2024`, `612_2025`) through the full route-C production path
   (extract → `net_contra_accounts` → declared reconcile → `validate_balance`). Assert for 2024:
   `sp03 ≈ 3,08M` (net), debts ≈ real (`~182k`, fondi removed from `Altri debiti`), `totale_attivo ≈
   3,13M` (net), `attivo == passivo`. Run with a stub/mock extractor input reproducing the observed LLM
   failure (gross assets + fondi in `sp16`) so the test does **not** require a live API key.
2. **Unit — `net_contra_accounts` on a synthetic gross TB**: fondi in `sp16` + gross assets → net
   assets, fondi removed, `_contra_netted` correct.
3. **Unit — parent/detail dedup**: mastro = Σ subs → counted once.
4. **Unit — no-op guards**: (a) no fondi present; (b) scan does not reconcile to declared total;
   (c) IVA one-sided.
5. **Regression**: run the existing deterministic route-C corpus (`tests/debug/*.pdf`) through the path
   and confirm no already-balanced file changes (self-validation gate must hold them at no-op). Record
   before/after quadratura counts.

## Files touched

- `importers/situazione_contabile_parser.py` — new `net_contra_accounts` + the coordinate/OCR contra-scan
  helper(s); reuses `_is_fondo_amm`, `_classify_sp_attivo`/`_classify_sp_passivo`, column-split helpers.
- `importers/pdf_importer.py` — call the stage in the route-C block; reduce the declared anchor by
  `_contra_netted` in the reconcile step.
- `tests/test_contra_netting.py` — new.
- `CLAUDE.md` — document the new stage under the route-C / netting section.

## Out of scope (follow-ups)

- Deterministic AGO/`build_iv_cee` under-capture + balance bug (so it becomes a reliable fallback).
- Aggressive/full IVA consolidation beyond the conservative both-sides rule.
- Netting of other contra accounts (fondo svalutazione beyond crediti, etc.).
