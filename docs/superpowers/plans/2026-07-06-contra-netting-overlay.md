# Contra-Netting Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministic, extractor-agnostic post-extraction netting of fondi ammortamento (and conservative IVA offset) on route-C trial balances, so accumulated depreciation never lands in "Altri debiti" and corrupts the rating.

**Architecture:** A pure scan+apply stage `net_contra_accounts` in `importers/situazione_contabile_parser.py`, wired into `pdf_importer.import_pdf_balance_sheet`'s route-C block after `overlay_debt_typing` and before the declared-result reconcile, whose declared anchor is reduced by the netted mass. Self-validation gates make every uncertain case a no-op.

**Spec:** `docs/superpowers/specs/2026-07-06-contra-netting-overlay-design.md` (read it before starting any task).

**Tech Stack:** Python 3, PyMuPDF (`fitz`), Decimal, pytest (in `backend/venv`).

## Global Constraints

- All monetary math uses `Decimal` — never float (project convention, `CLAUDE.md`).
- Run tests with the backend venv interpreter: `/home/peter/DEV/budget/backend/venv/bin/python -m pytest` (pytest 8.3.4 is installed there; system python has no pytest).
- All new code must be **no-op-safe**: on any exception or failed gate, return inputs unchanged. This stage may NEVER make an import fail that succeeded before.
- No new dependencies. No LLM calls in the new code.
- Log messages in Italian where user-facing, matching module style (e.g. "contra-netting: scan non riconcilia col totale dichiarato — no-op").
- Commit directly to `main` (user preference; no feature branches). Note: pushing triggers the Jenkins "Budget" job — commit locally as you go; push only at the end or when the user says so.
- The two evidence PDFs `docs/examples/612_2025 Costruzione di edifici residenziali e non residenziali.pdf` and `613_2024 ….pdf` exist in the working tree but are untracked. Tests must `pytest.mark.skipif` on their absence. Task 6 commits them (repo already tracks similar client PDFs in `docs/examples/`).
- Field names in route-C `winner_bs` dicts are **full DB names** (post `_map_sc_keys`): `sp02_immob_immateriali`, `sp03_immob_materiali`, `sp06_crediti_breve`, `sp16_debiti_breve`, `sp16e_debiti_tributari_breve`, `sp16g_altri_debiti_breve`, `sp17_debiti_lungo`, `sp17g_altri_debiti_lungo`, `totale_attivo`, `totale_passivo`, `sp13_utile_perdita`.

## Design decisions locked in (deviations from the spec text, approved rationale)

1. **Balance-invariant debt reduction instead of blind "subtract netted from sp16".** After overwriting sp02/sp03 with net scanned values, remove from the debt buckets exactly `min(totale_passivo − totale_attivo, fondi_total)` (floored at 0). On a fully-gross extraction this equals the fondi mass (spec behavior); on an **already-netted** extraction the excess is 0 and no real debt is touched. This implements the spec's "can never regress" requirement strictly better than the floor-0 rule alone.
   **IVA is delta-based (not idempotent like the sp02/sp03 overwrite), so it gets its own gross-evidence gate:** the IVA offset is applied only when the winner's pre-apply `totale_attivo` still sits at the declared GROSS magnitude (within 0.5%) — proof the extractor collapsed nothing. An already-net or partially-net sheet skips the IVA delta entirely (fondi netting still applies via the idempotent overwrite + excess rule). Without this gate, re-running the stage on a net sheet would subtract the IVA twice.
2. **`_contra_netted` is a return value, not a dict marker.** `net_contra_accounts` returns `(bs, netted)`; `pdf_importer` holds `netted` in a local. Same data flow as the spec's pop-the-marker wiring, one less magic key.
3. **The scan's gate-2 sum is the FULL attivo-side scan total** (fondi excluded), not just `gross_sp02+gross_sp03+current_assets`: `_classify_sp_attivo` defaults unknown attivo lines to `sp06`, so the full-side sum is the faithful gross-attivo reconstruction (per the spec's 2026-07-06 amendment).
4. **Parent/child dedup applies to ALL scanned rows**, not only fondi — AGO trial balances repeat mastro subtotals above their detail accounts on both sides; without dedup the attivo scan sum doubles and gate 2 would (wrongly) no-op every file.

---

### Task 1: Scan classification primitives (`_contra_classify`, `_dedup_parent_child`, `_is_iva_line`)

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (append after `_is_fondo_amm`, currently at `:2449-2454`)
- Create: `tests/test_contra_netting.py`

**Interfaces:**
- Consumes: existing `_is_fondo_amm(desc_upper) -> bool`, `_classify_sp_attivo(desc_upper) -> str` (returns tags `'gross_sp02'|'gross_sp03'|'gross_sp04'` or field names, default `'sp06'`), `_classify_sp_passivo(desc_upper) -> str` (returns `'depr_sp02'|'depr_sp03'|...`, default `'sp16'`).
- Produces (used by Tasks 2–3):
  - `ContraScan` NamedTuple: fields `gross_sp02, gross_sp03, attivo_total, fondi_immat, fondi_mat, iva_credito, iva_debito` (all `Decimal`).
  - `_contra_classify(attivo_rows, passivo_rows) -> ContraScan` where each row is `(code: str, desc_upper: str, amount: Decimal)`.
  - `_dedup_parent_child(rows) -> list[tuple]`.
  - `_is_iva_line(desc_upper) -> bool`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_contra_netting.py`:

```python
"""Tests for the route-C contra-netting overlay (fondi ammortamento + IVA).

Spec: docs/superpowers/specs/2026-07-06-contra-netting-overlay-design.md
Run:  /home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.situazione_contabile_parser import (  # noqa: E402
    ContraScan,
    _contra_classify,
    _dedup_parent_child,
    _is_iva_line,
)

D = Decimal


# ---------------------------------------------------------------- dedup

def test_dedup_drops_parent_when_children_sum_to_it():
    # 613_2024 real case: mastro "F.do amm fabbricati" 1.779.795,83 already equals
    # its two sub-accounts — counting both double-counts the fund.
    rows = [
        ("0402", "F.DO AMM FABBRICATI", D("1779795.83")),
        ("040201", "F.DO AMM FABBRICATI INDUSTRIALI", D("1416504.33")),
        ("040202", "F.DO AMM COSTRUZIONI LEGGERE", D("363291.50")),
    ]
    out = _dedup_parent_child(rows)
    assert [c for c, _, _ in out] == ["040201", "040202"]


def test_dedup_keeps_parent_without_children():
    rows = [("0402", "F.DO AMM FABBRICATI", D("100"))]
    assert _dedup_parent_child(rows) == rows


def test_dedup_keeps_parent_when_children_do_not_sum():
    rows = [
        ("0402", "F.DO AMM FABBRICATI", D("1000")),
        ("040201", "F.DO AMM FABBRICATI INDUSTRIALI", D("300")),
    ]
    # children present but sum (300) != parent (1000) -> parent is a real
    # independent balance, keep everything
    assert _dedup_parent_child(rows) == rows


def test_dedup_ignores_codeless_rows():
    rows = [("", "CASSA", D("10")), ("", "CASSA CONTANTI", D("10"))]
    assert _dedup_parent_child(rows) == rows


# ---------------------------------------------------------------- IVA detection

def test_is_iva_line_matches_erario_and_iva_accounts():
    assert _is_iva_line("ERARIO C/IVA")
    assert _is_iva_line("IVA C/ACQUISTI")
    assert _is_iva_line("IVA C/VENDITE")
    assert _is_iva_line("IVA A DEBITO")


def test_is_iva_line_rejects_riserva_and_plain_words():
    # 'RISERVA' contains the substring IVA — the \bIVA\b boundary must reject it
    assert not _is_iva_line("RISERVA LEGALE")
    assert not _is_iva_line("RISERVA STRAORDINARIA")
    assert not _is_iva_line("FORNITORI")


# ---------------------------------------------------------------- classification

ATTIVO_ROWS = [
    ("0101", "SOFTWARE DI PROPRIETA", D("20000")),
    ("0201", "FABBRICATI INDUSTRIALI", D("3000000")),
    ("0202", "IMPIANTI E MACCHINARI", D("500000")),
    ("0601", "CREDITI V/CLIENTI", D("100000")),
    ("0602", "ERARIO C/IVA", D("15000")),
    ("0901", "BANCA C/C", D("50000")),
]
PASSIVO_ROWS = [
    ("0401", "F.DO AMM.TO FABBRICATI", D("1800000")),
    ("0402", "F.DO AMM.TO IMPIANTI", D("53799.20")),
    ("0403", "F.DO AMM.TO SOFTWARE", D("5000")),
    ("1601", "FORNITORI", D("180000")),
    ("1602", "ERARIO C/IVA VENDITE", D("10000")),
    ("1101", "CAPITALE SOCIALE", D("1000000")),
]


def test_contra_classify_gross_trial_balance():
    scan = _contra_classify(ATTIVO_ROWS, PASSIVO_ROWS)
    assert scan.gross_sp02 == D("20000")
    assert scan.gross_sp03 == D("3500000")
    # full attivo side, fondi excluded: 20k+3M+500k+100k+15k+50k
    assert scan.attivo_total == D("3685000")
    assert scan.fondi_immat == D("5000")
    assert scan.fondi_mat == D("1853799.20")
    assert scan.iva_credito == D("15000")
    assert scan.iva_debito == D("10000")


def test_contra_classify_fondi_on_asset_side():
    # rare gross-on-asset presentation: fondi listed as attivo-side rows —
    # still summed as fondi, excluded from the gross asset totals
    attivo = ATTIVO_ROWS + [("0301", "F.DO AMM.TO IMPIANTI", D("53799.20"))]
    scan = _contra_classify(attivo, [])
    assert scan.fondi_mat == D("53799.20")
    assert scan.attivo_total == D("3685000")


def test_contra_classify_fondo_svalutazione_left_gross():
    # fondo svalutazione crediti is OUT of scope (spec §goal 3): not a fondo amm
    scan = _contra_classify([], [("0405", "F.DO SVALUTAZIONE CREDITI", D("9000"))])
    assert scan.fondi_immat == D("0")
    assert scan.fondi_mat == D("0")


def test_contra_classify_dedups_before_summing():
    passivo = [
        ("0402", "F.DO AMM FABBRICATI", D("1779795.83")),
        ("040201", "F.DO AMM FABBRICATI INDUSTRIALI", D("1416504.33")),
        ("040202", "F.DO AMM COSTRUZIONI LEGGERE", D("363291.50")),
    ]
    scan = _contra_classify([], passivo)
    assert scan.fondi_mat == D("1779795.83")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v`
Expected: FAIL at import time with `ImportError: cannot import name 'ContraScan'`.

- [ ] **Step 3: Implement the primitives**

In `importers/situazione_contabile_parser.py`, append immediately after `_is_fondo_amm` (after current line 2454). First change line 25 from `from typing import Dict, List, Optional, Tuple` to `from typing import Dict, List, NamedTuple, Optional, Tuple`. The module already has `re`, `Decimal`, and `logger = logging.getLogger(__name__)` at line 29 — reuse them.

```python
# ---------------------------------------------------------------------------
# Contra-netting overlay (spec docs/superpowers/specs/2026-07-06-contra-netting-
# overlay-design.md): deterministic post-extraction netting of fondi ammortamento
# (+ conservative IVA offset) on the CHOSEN route-C candidate, whatever extractor
# produced it. Pure, no LLM; no-op unless the scan self-validates against the
# document's own declared gross total.
# ---------------------------------------------------------------------------

class ContraScan(NamedTuple):
    gross_sp02: Decimal      # attivo-side immobilizzazioni immateriali (gross)
    gross_sp03: Decimal      # attivo-side immobilizzazioni materiali (gross)
    attivo_total: Decimal    # FULL attivo-side sum, fondi excluded (gate anchor)
    fondi_immat: Decimal     # fondi ammortamento immateriali (either side)
    fondi_mat: Decimal       # fondi ammortamento materiali (either side)
    iva_credito: Decimal     # IVA lines on the attivo side
    iva_debito: Decimal      # IVA lines on the passivo side


_IVA_LINE_RE = re.compile(r'\bIVA\b')


def _is_iva_line(desc_upper: str) -> bool:
    """IVA account line ('ERARIO C/IVA', 'IVA C/ACQUISTI', ...). Word-boundary so
    'RISERVA' (which contains the substring IVA) never matches."""
    return bool(_IVA_LINE_RE.search(desc_upper))


def _dedup_parent_child(rows):
    """Sum mastri OR leaves, never both. A parent row is dropped when child rows
    (codes strictly extending its code) are present and sum to its amount within
    max(2 EUR, 1%) — AGO layouts print the mastro subtotal above its detail
    accounts on both sides. Code-less rows are always kept."""
    out = []
    for code, desc, amount in rows:
        if code:
            kids = [a for c, _d, a in rows if c != code and c.startswith(code)]
            if kids:
                tol = max(Decimal('2'), abs(amount) * Decimal('0.01'))
                if abs(sum(kids) - amount) <= tol:
                    continue  # parent duplicated by its children
        out.append((code, desc, amount))
    return out


def _contra_classify(attivo_rows, passivo_rows) -> ContraScan:
    """Classify + sum deduplicated scan rows into the contra-netting aggregates.
    Rows are (code, desc_upper, amount); the SIDE each row came from is ground
    truth for attivo_total/IVA, while fondi ammortamento count from EITHER side."""
    Z = Decimal('0')
    g02 = g03 = att_total = f_im = f_mat = iva_c = iva_d = Z

    def _fondo_bucket(desc):
        # immat/mat split via the existing passivo rules (depr_sp02/depr_sp03);
        # unmatched fondi fall to materiali, mirroring the F.DO AMM fallback rule.
        return 'im' if _classify_sp_passivo(desc) == 'depr_sp02' else 'mat'

    for _c, d, a in _dedup_parent_child(list(attivo_rows)):
        if _is_fondo_amm(d):
            if _fondo_bucket(d) == 'im':
                f_im += abs(a)
            else:
                f_mat += abs(a)
            continue
        att_total += a
        if _is_iva_line(d):
            iva_c += a
            continue
        f = _classify_sp_attivo(d)
        if f == 'gross_sp02':
            g02 += a
        elif f == 'gross_sp03':
            g03 += a
    for _c, d, a in _dedup_parent_child(list(passivo_rows)):
        if _is_fondo_amm(d):
            if _fondo_bucket(d) == 'im':
                f_im += abs(a)
            else:
                f_mat += abs(a)
            continue
        if _is_iva_line(d):
            iva_d += a
    return ContraScan(g02, g03, att_total, f_im, f_mat, iva_c, iva_d)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v`
Expected: all 10 tests PASS.

Sanity check against the classification rules if a test fails: `'F.DO AMM.TO FABBRICATI'` must hit `_is_fondo_amm` (has `AMM.TO` + `F.DO`) and `_classify_sp_passivo` rule `(['F.DO','AMM','FABBRICAT'], 'depr_sp03')`; `'FABBRICATI INDUSTRIALI'` must hit `(['FABBRICAT'], 'gross_sp03')`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_contra_netting.py importers/situazione_contabile_parser.py
git commit -m "Contra-netting 1/6: primitivi di scansione (ContraScan, dedup mastro/dettaglio, riconoscimento IVA)"
```

---

### Task 2: Row acquisition — `_contra_rows` (coordinate + OCR-text modes)

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (append after `_contra_classify`)
- Test: `tests/test_contra_netting.py` (append)

**Interfaces:**
- Consumes: `_be_split(words) -> Optional[float]` (`:2069`), `_be_collect_side(words, lo, hi) -> List[(code, desc_upper, amount)]` (`:2125`) — both existing.
- Produces: `_contra_rows(file_path: str, text: Optional[str] = None) -> Optional[tuple[list, list]]` returning `(attivo_rows, passivo_rows)` or `None`. Used by Task 3's `net_contra_accounts`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_contra_netting.py`:

```python
import pytest  # add to the top-of-file imports

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "docs", "examples")
PDF_613 = os.path.join(
    EXAMPLES, "613_2024 Costruzione di edifici residenziali e non residenziali.pdf")


@pytest.mark.skipif(not os.path.exists(PDF_613), reason="evidence PDF not present")
def test_contra_rows_on_613_finds_the_fondi_mass():
    from importers.situazione_contabile_parser import _contra_rows, _contra_classify

    rows = _contra_rows(PDF_613)
    assert rows is not None
    attivo_rows, passivo_rows = rows
    scan = _contra_classify(attivo_rows, passivo_rows)
    # Spec reproduced evidence: fondi ammortamento 1.853.799,20 on this file
    assert abs(scan.fondi_immat + scan.fondi_mat - Decimal("1853799.20")) \
        <= Decimal("1853799.20") * Decimal("0.01")
    # gross attivo scan must land near the file's gross total (~4.99M order of
    # magnitude: net 3.13M + fondi 1.85M). Loose 2% band — the exact declared
    # total is asserted in the end-to-end test via _declared_control_totals.
    assert scan.attivo_total > Decimal("4000000")


def test_contra_rows_text_mode_classifies_fondi_by_nature():
    from importers.situazione_contabile_parser import _contra_rows, _contra_classify

    ocr = (
        "SITUAZIONE PATRIMONIALE\n"
        "0201 FABBRICATI INDUSTRIALI 3.000.000,00\n"
        "0401 F.DO AMM.TO FABBRICATI 1.800.000,00\n"
        "1601 FORNITORI 180.000,00\n"
        "CONTO ECONOMICO\n"
        "3101 RICAVI DELLE VENDITE 900.000,00\n"
    )
    rows = _contra_rows("/nonexistent.pdf", text=ocr)
    assert rows is not None
    scan = _contra_classify(*rows)
    assert scan.fondi_mat == Decimal("1800000.00")
    assert scan.gross_sp03 == Decimal("3000000.00")
    # the CE line must NOT leak into the attivo total (window cut at CONTO ECONOMICO)
    assert scan.attivo_total == Decimal("3000000.00")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v -k contra_rows`
Expected: FAIL with `ImportError: cannot import name '_contra_rows'`.

- [ ] **Step 3: Implement `_contra_rows`**

Append to `importers/situazione_contabile_parser.py` after `_contra_classify`:

```python
_CONTRA_TXT_ROW_RE = re.compile(
    r'^\s*(?P<code>[\d./*]+)?\s*(?P<desc>[A-ZÀ-Ù][^\d\n]*?)\s+'
    r'(?P<amt>-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$', re.MULTILINE)


def _contra_rows(file_path: str, text: Optional[str] = None):
    """Acquire (attivo_rows, passivo_rows) for the contra-netting scan.

    Generated PDFs: coordinate mode — the SP pages' two physical columns are
    split with the same helpers the best-effort parser uses (`_be_split` +
    `_be_collect_side`), so each row carries its true side. Scanned PDFs (no
    word layer): line-parse the OCR `text`; the side is unknown, so rows are
    assigned by NATURE (fondi → passivo bucket, attivo-rule matches → attivo)
    — lower fidelity, which the caller's self-validation gate absorbs (a
    misread scan fails reconciliation → no-op, never corruption).
    Returns None when neither mode yields rows.
    """
    # --- coordinate mode -----------------------------------------------------
    try:
        import fitz
        doc = fitz.open(file_path)
        att, pas = [], []
        for page in doc:
            up = page.get_text().upper()
            flat = re.sub(r'\s+', '', up)
            # fiscal-reconciliation appendix pages are not the SP
            if 'RIDETERMINAZIONE' in flat or 'REDDITOIMPONIBILE' in flat:
                continue
            is_sp = ('PATRIMONIAL' in flat) or (
                'ATTIVIT' in up and 'PASSIVIT' in up and 'CONTOECONOMICO' not in flat)
            is_ce = ('CONTOECONOMICO' in flat) or ('COSTI' in up and 'RICAVI' in up)
            if not is_sp or is_ce:
                continue
            words = page.get_text('words')
            if not words:
                continue
            split = _be_split(words)
            if split is None:
                split = page.rect.width / 2
            att += _be_collect_side(words, -1e9, split)
            pas += _be_collect_side(words, split, 1e9)
        doc.close()
        if att or pas:
            return att, pas
    except Exception:
        pass

    # --- OCR-text fallback (scanned PDFs) ------------------------------------
    if not text:
        return None
    up = text.upper()
    # keep only the SP region: cut at the CE section header
    m = re.search(r'CONTO\s+ECONOMICO', up)
    if m:
        up = up[:m.start()]
    att, pas = [], []
    for row in _CONTRA_TXT_ROW_RE.finditer(up):
        desc = row.group('desc').strip()
        if len(desc) < 3 or 'TOTALE' in desc or 'PAREGGIO' in desc:
            continue
        try:
            amount = _parse_amount(row.group('amt'))
        except Exception:
            continue
        code = (row.group('code') or '').strip().strip('./*')
        entry = (re.sub(r'\D', '', code), desc, abs(amount))
        if _is_fondo_amm(desc):
            pas.append(entry)          # side irrelevant for fondi (contra either way)
        elif _is_iva_line(desc) and ('VENDIT' in desc or 'DEBITO' in desc):
            pas.append(entry)
        else:
            f = _classify_sp_attivo(desc)
            # text mode has no column ground truth: count ONLY explicit
            # attivo-rule matches (never the sp06 default, which would suck
            # passivo/CE lines into the attivo total and defeat the gate)
            if f != 'sp06' or _is_iva_line(desc):
                att.append(entry)
    if att or pas:
        return att, pas
    return None
```

Note on the text-mode side test above: `'FORNITORI'` matches no attivo rule (`_classify_sp_attivo` default `'sp06'`) and is not a fondo/IVA-debit line, so it is **dropped** in text mode — which is why `attivo_total == 3000000` in the test (the gate, not the scan, is the safety mechanism in text mode).

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v`
Expected: all tests PASS (the 613 test exercises the real PDF; if it fails on the fondi sum, debug with a quick REPL: `_contra_rows(PDF_613)` and inspect which fondi lines were missed or double-counted — adjust nothing in the rules tables without checking the spec's dedup rule first).

- [ ] **Step 5: Commit**

```bash
git add tests/test_contra_netting.py importers/situazione_contabile_parser.py
git commit -m "Contra-netting 2/6: acquisizione righe scan (coordinate + fallback testo OCR)"
```

---

### Task 3: `net_contra_accounts` — apply + self-validation gates

**Files:**
- Modify: `importers/situazione_contabile_parser.py` (append after `_contra_rows`)
- Test: `tests/test_contra_netting.py` (append)

**Interfaces:**
- Consumes: `_contra_rows`, `_contra_classify` (Tasks 1–2).
- Produces: `net_contra_accounts(winner_bs: dict, file_path: str, text: Optional[str] = None, declared: Optional[dict] = None) -> tuple[dict, Decimal]` — returns the (mutated) sheet and the netted contra mass (`Decimal('0')` on no-op). `declared` is the `_declared_control_totals` dict (`attivo/passivo/pareggio/utile/perdita`). Used by Task 4's wiring.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_contra_netting.py`:

```python
# ---------------------------------------------------------------- net_contra_accounts

import importers.situazione_contabile_parser as scp


def _gross_winner_bs():
    """Reproduces the observed CoGe-LLM failure shape on a gross trial balance:
    assets left GROSS, the whole fondi mass (1.858.799,20) dumped into debts."""
    return {
        "sp02_immob_immateriali": D("20000"),
        "sp03_immob_materiali": D("3500000"),
        "sp06_crediti_breve": D("115000"),          # incl. 15.000 IVA credit
        "sp09_disponibilita_liquide": D("50000"),
        "sp11_capitale": D("1000000"),
        "sp13_utile_perdita": D("636200.80"),
        "sp16_debiti_breve": D("2048799.20"),       # 190.000 real + 1.858.799,20 fondi
        "sp16g_altri_debiti_breve": D("1873799.20"),
        "totale_attivo": D("3685000"),
        "totale_passivo": D("3685000"),
    }


DECLARED = {"attivo": D("3685000"), "passivo": D("3685000"),
            "pareggio": D("3685000"), "utile": None, "perdita": None}


def _patch_scan(monkeypatch, attivo, passivo):
    monkeypatch.setattr(scp, "_contra_rows", lambda fp, text=None: (attivo, passivo))


def test_netting_applied_on_gross_extraction(monkeypatch):
    _patch_scan(monkeypatch, ATTIVO_ROWS, PASSIVO_ROWS)
    bs = _gross_winner_bs()
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    # netted = fondi 1.858.799,20 + IVA offset min(15000, 10000)
    assert netted == D("1868799.20")
    assert bs["sp02_immob_immateriali"] == D("15000")       # 20.000 - 5.000
    assert bs["sp03_immob_materiali"] == D("1646200.80")    # 3.500.000 - 1.853.799,20
    assert bs["sp06_crediti_breve"] == D("105000")          # IVA credit collapsed
    assert bs["totale_attivo"] == D("1816200.80")
    assert bs["totale_passivo"] == bs["totale_attivo"]      # pareggio preserved
    assert bs["sp16_debiti_breve"] == D("180000")           # only real debts left
    assert bs["sp13_utile_perdita"] == D("636200.80")       # result untouched


def test_noop_when_extractor_already_netted(monkeypatch):
    """Deterministic authority must be idempotent: a correct (net) sheet passes
    through with only the anchor-reduction value returned — no field changes."""
    _patch_scan(monkeypatch, ATTIVO_ROWS, PASSIVO_ROWS)
    bs = {
        "sp02_immob_immateriali": D("15000"),
        "sp03_immob_materiali": D("1646200.80"),
        "sp06_crediti_breve": D("105000"),
        "sp09_disponibilita_liquide": D("50000"),
        "sp11_capitale": D("1000000"),
        "sp13_utile_perdita": D("636200.80"),
        "sp16_debiti_breve": D("180000"),
        "totale_attivo": D("1816200.80"),
        "totale_passivo": D("1816200.80"),
    }
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("1868799.20")   # still returned: the DECLARED anchor is gross
    # sp02/sp03 overwritten with the SAME net values; the IVA gross-evidence gate
    # skips the (non-idempotent) IVA delta because totale_attivo is already at the
    # NET magnitude; balance-invariant debt reduction sees excess 0 -> no real
    # debt touched. Net effect: the sheet passes through byte-identical.
    assert bs == before


def test_noop_without_fondi(monkeypatch):
    _patch_scan(monkeypatch, [("0601", "CREDITI V/CLIENTI", D("3685000"))], [])
    bs = _gross_winner_bs()
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("0")
    assert bs == before


def test_noop_when_scan_does_not_reconcile(monkeypatch):
    # scan reads only half the attivo -> gate 2 fails -> untouched sheet
    _patch_scan(monkeypatch, ATTIVO_ROWS[:2], PASSIVO_ROWS)
    bs = _gross_winner_bs()
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("0")
    assert bs == before


def test_noop_without_declared_totals(monkeypatch):
    _patch_scan(monkeypatch, ATTIVO_ROWS, PASSIVO_ROWS)
    bs = _gross_winner_bs()
    before = dict(bs)
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=None)
    assert netted == D("0")
    assert bs == before


def test_iva_one_sided_left_gross(monkeypatch):
    # only an IVA credit exists -> offset 0 -> crediti untouched, fondi still netted
    passivo_no_iva = [r for r in PASSIVO_ROWS if "IVA" not in r[1]]
    # keep the attivo scan total equal to declared by replacing the IVA row
    attivo = [r if "IVA" not in r[1] else (r[0], "CREDITI DIVERSI", r[2])
              for r in ATTIVO_ROWS]
    _patch_scan(monkeypatch, attivo, passivo_no_iva)
    bs = _gross_winner_bs()
    bs, netted = scp.net_contra_accounts(bs, "x.pdf", declared=DECLARED)
    assert netted == D("1858799.20")                 # fondi only, no IVA offset
    assert bs["sp06_crediti_breve"] == D("115000")   # untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v -k "netting or noop or iva_one"`
Expected: FAIL with `AttributeError: ... has no attribute 'net_contra_accounts'`.

- [ ] **Step 3: Implement `net_contra_accounts`**

Append to `importers/situazione_contabile_parser.py`:

```python
def _reduce_debts(bs: Dict[str, Decimal], amount: Decimal) -> Decimal:
    """Remove `amount` from the debt buckets: sp16g (altri, where misclassified
    fondi land) first — mirrored on the sp16 aggregate to keep sub-field
    consistency — then the sp16 aggregate residual, then the sp17 side. Floors
    at 0 everywhere; returns the mass actually removed."""
    Z = Decimal('0')
    removed = Z
    for sub, agg in (('sp16g_altri_debiti_breve', 'sp16_debiti_breve'),
                     ('sp16e_debiti_tributari_breve', 'sp16_debiti_breve'),
                     ('sp17g_altri_debiti_lungo', 'sp17_debiti_lungo')):
        if removed >= amount:
            break
        take = min(amount - removed, bs.get(sub, Z))
        if take > Z:
            bs[sub] = bs.get(sub, Z) - take
            bs[agg] = max(Z, bs.get(agg, Z) - take)
            removed += take
    for agg in ('sp16_debiti_breve', 'sp17_debiti_lungo'):
        if removed >= amount:
            break
        take = min(amount - removed, bs.get(agg, Z))
        if take > Z:
            bs[agg] = bs.get(agg, Z) - take
            removed += take
    return removed


def net_contra_accounts(winner_bs: Dict[str, Decimal], file_path: str,
                        text: Optional[str] = None,
                        declared: Optional[dict] = None):
    """Deterministic contra-netting overlay for route-C trial balances.

    Re-reads the source document, sums fondi ammortamento (parent/child
    deduplicated) and the offsettable IVA position, then — deterministic
    authority — OVERWRITES sp02/sp03 with the scanned net values and removes
    from the debt buckets exactly the passivo excess over the new attivo
    (capped at the fondi mass), so an already-net extraction is passed through
    untouched (idempotent) and a gross one comes out net and balanced.

    Self-validation gates (either fails -> no-op, sheet returned unchanged):
      1. netted contra > 1% of the declared total (there is real contra mass);
      2. the scan's gross attivo reconciles to the declared TOTALE ATTIVO /
         pareggio within 0.5% (proves we read the right magnitudes).

    Returns (winner_bs, netted_contra). netted_contra > 0 also when the sheet
    needed no field change (already net): the caller must still reduce the
    DECLARED anchor by it, because the document's printed totals are GROSS.
    """
    Z = Decimal('0')
    try:
        decl_total = None
        if declared:
            decl_total = (declared.get('pareggio') or declared.get('attivo')
                          or declared.get('passivo'))
        if not decl_total or decl_total <= 0:
            return winner_bs, Z
        rows = _contra_rows(file_path, text=text)
        if not rows:
            return winner_bs, Z
        scan = _contra_classify(*rows)
        iva_offset = min(scan.iva_credito, scan.iva_debito)
        fondi_total = scan.fondi_immat + scan.fondi_mat
        netted = fondi_total + iva_offset
        if netted <= decl_total * Decimal('0.01'):
            return winner_bs, Z                              # gate 1
        if abs(scan.attivo_total - decl_total) > decl_total * Decimal('0.005'):
            logger.info(
                "contra-netting: scan attivo %s non riconcilia col totale "
                "dichiarato %s — no-op", scan.attivo_total, decl_total)
            return winner_bs, Z                              # gate 2
    except Exception as exc:
        logger.warning("contra-netting: scan fallito (%s) — no-op", exc)
        return winner_bs, Z

    # ---- apply (deterministic authority) ------------------------------------
    # IVA gross-evidence gate: the IVA collapse is a DELTA (not idempotent like
    # the sp02/sp03 overwrite), so it applies only when the winner's pre-apply
    # total still sits at the declared GROSS magnitude — proof nothing was
    # collapsed yet. An already-net / partially-net sheet skips the IVA delta.
    pre_total = winner_bs.get('totale_attivo', Z)
    apply_iva = (iva_offset > Z
                 and abs(pre_total - decl_total) <= decl_total * Decimal('0.005'))

    old_02 = winner_bs.get('sp02_immob_immateriali', Z)
    old_03 = winner_bs.get('sp03_immob_materiali', Z)
    new_02 = max(Z, scan.gross_sp02 - scan.fondi_immat)
    new_03 = max(Z, scan.gross_sp03 - scan.fondi_mat)
    winner_bs['sp02_immob_immateriali'] = new_02
    winner_bs['sp03_immob_materiali'] = new_03
    att_delta = (new_02 + new_03) - (old_02 + old_03)
    winner_bs['totale_attivo'] = winner_bs.get('totale_attivo', Z) + att_delta

    if apply_iva:
        # collapse the offsettable IVA: net erario position stays on the larger
        # side, the smaller side is dropped from crediti and debiti tributari.
        cred = winner_bs.get('sp06_crediti_breve', Z)
        take = min(iva_offset, cred)
        winner_bs['sp06_crediti_breve'] = cred - take
        winner_bs['totale_attivo'] -= take
        winner_bs['totale_passivo'] = (winner_bs.get('totale_passivo', Z)
                                       - _reduce_debts(winner_bs, take))

    # balance-invariant fondi removal from the debt buckets: exactly the passivo
    # excess over the (new, net) attivo, capped at the fondi mass — 0 when the
    # extractor had already netted, the full fondi mass when it was gross.
    excess = winner_bs.get('totale_passivo', Z) - winner_bs['totale_attivo']
    to_remove = min(max(Z, excess), fondi_total)
    if to_remove > Z:
        winner_bs['totale_passivo'] = (winner_bs.get('totale_passivo', Z)
                                       - _reduce_debts(winner_bs, to_remove))
    logger.info(
        "contra-netting: nettati %s (fondi immat %s + mat %s + IVA %s); "
        "sp02 %s→%s, sp03 %s→%s", netted, scan.fondi_immat, scan.fondi_mat,
        iva_offset, old_02, new_02, old_03, new_03)
    return winner_bs, netted
```

- [ ] **Step 4: Run the full test module**

Run: `/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v`
Expected: all tests PASS. Gross-case arithmetic to walk if one fails (order matters — `apply_iva` is decided on the PRE-apply total, the fondi overwrite runs next, the IVA delta after that, the excess-based debt removal last):
- pre_total = 3.685.000 ≈ declared → `apply_iva` True
- fondi overwrite: att_delta = −1.858.799,20 → totale_attivo 1.826.200,80
- IVA delta: sp06 115.000→105.000, totale_attivo 1.816.200,80; debts −10.000 (sp16g 1.873.799,20→1.863.799,20, sp16 2.048.799,20→2.038.799,20), totale_passivo 3.675.000
- excess = 3.675.000 − 1.816.200,80 = 1.858.799,20 = fondi_total → removed in full: sp16g→5.000, sp16→180.000, totale_passivo 1.816.200,80
- final invariant: `totale_attivo == totale_passivo == 1.816.200,80`, `sp16 == 180.000`, sp13 untouched.

- [ ] **Step 5: Commit**

```bash
git add tests/test_contra_netting.py importers/situazione_contabile_parser.py
git commit -m "Contra-netting 3/6: net_contra_accounts (autorita deterministica + gate anti-regressione)"
```

---

### Task 4: Wire into `pdf_importer` route C + reduce the declared anchor + fix the `:535` OCR-text bug

**Files:**
- Modify: `importers/pdf_importer.py` (route-C block `:426-477` and the `enforce_ce_sp_identity` block `:532-543`)
- Test: `tests/test_contra_netting.py` (append end-to-end test)

**Interfaces:**
- Consumes: `net_contra_accounts` (Task 3), existing `_declared_control_totals`, `_reconcile_trial_to_declared` (`pdf_extractor_llm.py:2160/:2235`).
- Produces: the production route-C path applies netting between `overlay_debt_typing` and the declared-result reconcile; the reconcile receives declared totals reduced by the netted mass.

- [ ] **Step 1: Write the failing end-to-end test**

Append to `tests/test_contra_netting.py`:

```python
# ---------------------------------------------------------------- end-to-end (production path)

@pytest.mark.skipif(not os.path.exists(PDF_613), reason="evidence PDF not present")
def test_613_production_path_with_stubbed_gross_llm():
    """Full route-C post-selection pipeline on the real 613_2024 PDF, with the
    winning candidate stubbed to the observed LLM failure (gross assets, fondi
    in debts). No API key needed. Asserts the spec's acceptance numbers."""
    from importers.pdf_extractor_llm import (
        _declared_control_totals, _reconcile_trial_to_declared,
    )
    from importers.situazione_contabile_parser import net_contra_accounts
    from importers.iv_cee_hierarchy import enforce_ce_sp_identity
    from importers.pdf_mapper import IVCEEMapper

    declared = _declared_control_totals(PDF_613)
    assert declared.get("pareggio") or declared.get("attivo"), \
        "613 must print its own control totals"

    # stubbed winner reproducing the observed failure: real scan drives the fix
    bs, netted = net_contra_accounts(_gross_winner_bs_613(), PDF_613,
                                     declared=declared)
    assert netted > D("1800000")

    decl = dict(declared)
    for k in ("attivo", "passivo", "pareggio"):
        if decl.get(k):
            decl[k] = decl[k] - netted
    bs = _reconcile_trial_to_declared(bs, decl, "test-613")

    # Spec acceptance: sp03 ~ 3,08M net; debts ~ real (~182k, fondi removed);
    # totale_attivo ~ 3,13M net; attivo == passivo
    assert abs(bs["sp03_immob_materiali"] - D("3080000")) < D("100000")
    debts = bs.get("sp16_debiti_breve", D("0")) + bs.get("sp17_debiti_lungo", D("0"))
    assert debts < D("400000")
    assert abs(bs["totale_attivo"] - D("3130000")) < D("100000")
    assert abs(bs["totale_attivo"] - bs["totale_passivo"]) <= D("1")
    # no false plug: the netted mass must NOT resurface as _plug_residual
    assert bs.get("_plug_residual", D("0")) < bs["totale_attivo"] * D("0.01")


def _gross_winner_bs_613():
    """Observed-failure shape for 613_2024, built from the spec's evidence:
    equity 2,93M, real debts ~182k, fondi 1.853.799,20 booked as altri debiti,
    assets gross. Numbers approximate the real file; the scan overwrites the
    asset side from the document itself, so only the SHAPE matters here."""
    return {
        "sp02_immob_immateriali": D("0"),
        "sp03_immob_materiali": D("4930000"),
        "sp06_crediti_breve": D("30000"),
        "sp09_disponibilita_liquide": D("25000"),
        "sp11_capitale": D("2930000"),
        "sp13_utile_perdita": D("19590.98"),
        "sp16_debiti_breve": D("2035409.02"),
        "sp16g_altri_debiti_breve": D("2035409.02"),
        "totale_attivo": D("4985000"),
        "totale_passivo": D("4985000"),
    }
```

**Important:** the exact figures for `_gross_winner_bs_613` must be calibrated against the actual scan in Step 2 — the assertions that matter are the spec's acceptance bands (sp03 ≈ 3,08M ± 100k, debts < 400k, attivo ≈ 3,13M ± 100k, pareggio). If the first run shows the scan produces slightly different gross/fondi values, adjust the stub's `totale_*`/`sp16*` so it is internally balanced and gross (assets ≈ scan gross total), NOT the acceptance bands.

- [ ] **Step 2: Run the test to verify it fails**

Run: `/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v -k production`
Expected: FAIL — either at the acceptance assertions (netting not yet wired is irrelevant here since the test calls the stages directly, so this test may already pass after Task 3; if it passes, treat Step 2 as calibration of the stub numbers and move on).

- [ ] **Step 3: Wire the stage into `pdf_importer.py`**

Three edits inside `import_pdf_balance_sheet`:

**(a)** Make `_dc0` always defined. At the declared-totals fetch (`:426-433`), change:

```python
                _decl_tot = None
                try:
                    from importers.pdf_extractor_llm import _declared_control_totals
                    _dc0 = _declared_control_totals(file_path, text=ocr_text)
                    _decl_tot = (_dc0.get('pareggio') or _dc0.get('passivo')
                                 or _dc0.get('attivo'))
                except Exception:
                    _decl_tot = None
```

to:

```python
                _decl_tot = None
                _dc0 = {}
                try:
                    from importers.pdf_extractor_llm import _declared_control_totals
                    _dc0 = _declared_control_totals(file_path, text=ocr_text)
                    _decl_tot = (_dc0.get('pareggio') or _dc0.get('passivo')
                                 or _dc0.get('attivo'))
                except Exception:
                    _decl_tot = None
```

**(b)** Insert the netting stage after the `overlay_debt_typing` block (`:453-457`) and before the `_authoritative` pop (`:466`):

```python
                # Contra-netting overlay (spec 2026-07-06): deterministic post-
                # extraction netting of fondi ammortamento (+ conservative IVA
                # offset) on the CHOSEN candidate, whatever extractor produced it.
                # No-op unless the scan self-validates against the declared gross
                # total; _contra also reduces the declared anchor below, because
                # the document's printed totals are GROSS on these files.
                _contra = Decimal('0')
                try:
                    from importers.situazione_contabile_parser import net_contra_accounts
                    balance_sheet_data, _contra = net_contra_accounts(
                        balance_sheet_data, file_path, text=ocr_text, declared=_dc0)
                    if _contra > 0:
                        logger.info(f"Route C: contra-netting applicato "
                                    f"({_contra:,.0f} fondi ammortamento/IVA)")
                except Exception as _cn_err:
                    logger.warning(f"Route C: contra-netting saltato: {_cn_err}")
```

**(c)** In the declared-result reconcile block (`:467-477`), reuse `_dc0` (dropping the duplicate `_declared_control_totals` fetch at `:472`) and reduce the totals by `_contra`:

```python
                _authoritative = balance_sheet_data.pop('_skip_declared_reconcile', False)
                if not _authoritative:
                    try:
                        from importers.pdf_extractor_llm import _reconcile_trial_to_declared
                        _decl = dict(_dc0)
                        if _contra > 0:
                            # the printed totals are GROSS on gross-presentation
                            # files: anchor the reconcile to the NET total so it
                            # does not re-inflate the netted mass as a false plug
                            for _k in ('attivo', 'passivo', 'pareggio'):
                                if _decl.get(_k):
                                    _decl[_k] = _decl[_k] - _contra
                        balance_sheet_data = _reconcile_trial_to_declared(
                            balance_sheet_data, _decl, source)
                        residual = balance_sheet_data.get('_plug_residual', residual)
                    except Exception as _rc_err:
                        logger.warning(f"Route C: declared-result reconcile skipped: {_rc_err}")
```

(`utile`/`perdita` keys are left untouched — the result is invariant under symmetric netting.)

**(d)** Fix the adjacent pre-existing bug at `:535`: change

```python
            _decl_ce = _declared_control_totals(file_path)
```

to

```python
            _decl_ce = _declared_control_totals(file_path, text=ocr_text)
```

First verify `ocr_text` is in scope and defined on ALL routes at that point (it is set by the OCR routing pass near `:273-292`; confirm with `grep -n "ocr_text" importers/pdf_importer.py` that it is initialized before the route split, e.g. `ocr_text = None` — if it is only assigned inside a conditional, initialize it to `None` right before the classification step).

- [ ] **Step 4: Run the whole module + a smoke import**

```bash
/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v
```
Expected: all PASS.

Smoke-check that the production entry point still works end-to-end on a *non*-trial-balance file (route A/B unaffected) and on 613 without an API key (deterministic candidate + netting):

```bash
cd /home/peter/DEV/budget && backend/venv/bin/python - <<'EOF'
import logging; logging.basicConfig(level=logging.INFO)
from importers.bilancio_classifier import classify_bilancio
print(classify_bilancio("docs/examples/613_2024 Costruzione di edifici residenziali e non residenziali.pdf", None))
EOF
```
Expected: route `ROUTE_TRIAL` (macro-area C) — confirms the file exercises the new block.

- [ ] **Step 5: Commit**

```bash
git add importers/pdf_importer.py tests/test_contra_netting.py
git commit -m "Contra-netting 4/6: wiring route-C (overlay dopo debt-typing, ancora dichiarata ridotta, fix ocr_text su enforce_ce_sp_identity)"
```

---

### Task 5: Regression corpus runner + before/after record

**Files:**
- Create: `tests/run_contra_regression.py`
- Modify: none

**Interfaces:**
- Consumes: `extract_situazione_contabile`, `_map_sc_keys` (via `importers.pdf_importer`), `net_contra_accounts`, `_declared_control_totals`, `_reconcile_trial_to_declared`, `enforce_ce_sp_identity`, `IVCEEMapper.validate_balance`, `check_quadratura`.
- Produces: a manual CLI tool printing a per-file table (quadra / masked / empty, plug residual, with vs without netting). No pytest dependency — plain script, mirrors the repo's ad-hoc test style.

- [ ] **Step 1: Write the runner**

Create `tests/run_contra_regression.py`:

```python
"""Deterministic route-C regression runner for the contra-netting overlay.

Runs every PDF in tests/debug/ + the two docs/examples evidence files through
the DETERMINISTIC production path (no LLM, no API key), once WITHOUT and once
WITH net_contra_accounts, and prints quadratura verdicts side by side.

A file counts as REGRESSED when it was quadrato without netting and is not
with netting. The expected outcome is zero regressions and 612/613 improving.

Usage:  backend/venv/bin/python tests/run_contra_regression.py
"""
import glob
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.iv_cee_hierarchy import check_quadratura, enforce_ce_sp_identity
from importers.pdf_extractor_llm import (
    _declared_control_totals, _reconcile_trial_to_declared,
)
from importers.pdf_importer import _map_sc_keys
from importers.pdf_mapper import IVCEEMapper
from importers.situazione_contabile_parser import (
    extract_situazione_contabile, net_contra_accounts,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = sorted(
    glob.glob(os.path.join(ROOT, "tests", "debug", "*.pdf"))
    + glob.glob(os.path.join(ROOT, "tests", "debug", "*.PDF"))
    + glob.glob(os.path.join(ROOT, "docs", "examples", "61[23]_*.pdf"))
)


def run_one(path, with_netting):
    bs, ce = extract_situazione_contabile(path)
    bs, ce = _map_sc_keys(bs), _map_sc_keys(ce)
    declared = _declared_control_totals(path)
    contra = Decimal("0")
    if with_netting:
        bs, contra = net_contra_accounts(bs, path, declared=declared)
    if not bs.pop("_skip_declared_reconcile", False):
        decl = dict(declared)
        if contra > 0:
            for k in ("attivo", "passivo", "pareggio"):
                if decl.get(k):
                    decl[k] = decl[k] - contra
        bs = _reconcile_trial_to_declared(bs, decl, os.path.basename(path))
    ce = enforce_ce_sp_identity(bs, ce, "regression", prefer="sp13",
                                declared=declared)
    valid = IVCEEMapper().validate_balance(bs)
    q = check_quadratura(bs, ce)
    return {
        "valid": valid, "quadra": q.quadra, "masked": q.masked,
        "empty": q.is_empty, "plug": q.plug_residual,
        "attivo": bs.get("totale_attivo", Decimal("0")), "contra": contra,
    }


def main():
    if not CORPUS:
        print("no corpus PDFs found (tests/debug/ empty?) — nothing to check")
        return
    regressions = 0
    print(f"{'file':50s} {'senza netting':>22s} {'con netting':>22s}  contra")
    for path in CORPUS:
        name = os.path.basename(path)[:48]
        try:
            base = run_one(path, with_netting=False)
        except Exception as exc:
            base = {"quadra": False, "masked": False, "empty": True,
                    "plug": Decimal("0"), "err": str(exc)[:40]}
        try:
            net = run_one(path, with_netting=True)
        except Exception as exc:
            net = {"quadra": False, "masked": False, "empty": True,
                   "plug": Decimal("0"), "err": str(exc)[:40], "contra": "?"}

        def verdict(r):
            if r.get("err"):
                return f"ERR {r['err'][:14]}"
            if r["empty"]:
                return "VUOTO"
            tag = "SI" if r["quadra"] else ("MASCHERATO" if r["masked"] else "NO")
            return f"{tag} plug={r['plug']:,.0f}"

        if base.get("quadra") and not net.get("quadra"):
            regressions += 1
            flag = "  << REGRESSIONE"
        else:
            flag = ""
        print(f"{name:50s} {verdict(base):>22s} {verdict(net):>22s}  "
              f"{net.get('contra', 0)}{flag}")
    print(f"\nregressioni: {regressions}")
    sys.exit(1 if regressions else 0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it and record the result**

Run: `/home/peter/DEV/budget/backend/venv/bin/python tests/run_contra_regression.py`
Expected: exit code 0, **regressioni: 0**. `613_2024` should move toward quadra/lower plug with netting (the deterministic candidate on 613 under-nets and doesn't balance — the netting stage should visibly shrink its gap even if the deterministic extraction alone still fails elsewhere). Files where the gate no-ops must show identical verdicts in both columns.

Copy the printed table into the commit message body (it is the spec's "record before/after quadratura counts" artifact).

- [ ] **Step 3: Commit**

```bash
git add tests/run_contra_regression.py
git commit -m "Contra-netting 5/6: runner di regressione corpus deterministico (before/after)

<paste the table here>"
```

---

### Task 6: Docs, fixtures, spec status

**Files:**
- Modify: `CLAUDE.md` (route-C section), `docs/superpowers/specs/2026-07-06-contra-netting-overlay-design.md` (status line)
- Add: `docs/examples/612_2025 Costruzione di edifici residenziali e non residenziali.pdf`, `docs/examples/613_2024 Costruzione di edifici residenziali e non residenziali.pdf`

- [ ] **Step 1: Update CLAUDE.md**

In the CLAUDE.md section "IV-CEE leveling + quadratura engine" area (route-C documentation), add a bullet after the "Route-C extractor selection by completeness" bullet:

```markdown
- **Contra-netting overlay (2026-07-06)** (`situazione_contabile_parser.net_contra_accounts`,
  called in `pdf_importer` route C after `overlay_debt_typing`): deterministic post-extraction
  netting of fondi ammortamento (+ offsettable IVA, both-sides-only) on the CHOSEN candidate.
  Re-scans the SP pages (coordinate mode; OCR-text fallback), dedupes mastro/dettaglio, then
  OVERWRITES sp02/sp03 with net values and removes from the debt buckets exactly the passivo
  excess over the new attivo (capped at the fondi mass) — idempotent on an already-net sheet.
  Two gates or no-op: netted > 1% of declared total AND scan gross attivo ≈ declared total
  (0.5%). The declared anchor passed to `_reconcile_trial_to_declared` is reduced by the netted
  mass (printed totals are GROSS on these files) so the reconcile cannot re-inflate it as a
  false plug. Tests: `tests/test_contra_netting.py`; corpus check: `tests/run_contra_regression.py`.
```

- [ ] **Step 2: Update the spec status + commit fixtures**

In the spec header change `**Status:** Design approved (pending written-spec review)` to `**Status:** Implemented (see docs/superpowers/plans/2026-07-06-contra-netting-overlay.md)`.

```bash
git add CLAUDE.md docs/superpowers/specs/2026-07-06-contra-netting-overlay-design.md \
  "docs/examples/612_2025 Costruzione di edifici residenziali e non residenziali.pdf" \
  "docs/examples/613_2024 Costruzione di edifici residenziali e non residenziali.pdf"
git commit -m "Contra-netting 6/6: docs (CLAUDE.md, stato spec) + fixture PDF di evidenza"
```

- [ ] **Step 3: Final verification (whole suite + production smoke)**

```bash
/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_contra_netting.py -v
/home/peter/DEV/budget/backend/venv/bin/python tests/run_contra_regression.py
/home/peter/DEV/budget/backend/venv/bin/python -m pytest tests/test_debt_type.py tests/test_overlay_debt_typing.py -v
```
Expected: everything passes, zero regressions. The last command guards the two existing route-C test modules against accidental breakage.
