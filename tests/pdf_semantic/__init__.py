"""M2-04: independent, non-visual verification of a compiled dossier PDF.

Deliberately does not import PyMuPDF (`fitz`): the renderer's own
`app.renderers.typst.runtime.validate_pdf` already checks the PDF with it, so a
bug shared between the renderer and its own validator would fool a second
check built on the same library. This module reads the artefact with the
poppler-utils CLI (`pdftotext`, `pdffonts`, `pdfinfo`) instead — a distinct
oracle, and the layout-neutral one the brief asks for: it reads the text a
human (or a screen reader) would get out of the PDF, not the Typst layout
metadata the renderer measures internally.

Every ``assert_*`` function raises a plain ``AssertionError`` with a message
naming what was expected and what was found, and never touches pytest
internals: `tests/test_pdf_semantic_dossier.py` calls them both to build the
green-path checks and, with deliberately wrong expectations, to prove the
checks are sensitive (the mutation test the brief requires).
"""
from __future__ import annotations

import re
import subprocess
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

#: Technical identifiers that must never leak into rendered text (M2-02B, still
#: present in the M2-02 template this harness supersedes as an oracle — see the
#: `xfail(strict=True)` in the test module).
FORBIDDEN_TECHNICAL_STRINGS = ("historical:", "forecast:", "practice.", "synthetic_", "Unità: ratio")

#: Poppler's watermark text marker (draft-only); read with `-raw` (see `raw_page_texts`).
DRAFT_WATERMARK = "BOZZA"


class PopplerToolMissing(RuntimeError):
    """A required poppler-utils binary (pdftotext/pdffonts/pdfinfo) is not on PATH."""


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(args, capture_output=True, timeout=60)
    except FileNotFoundError as error:
        raise PopplerToolMissing(args[0]) from error
    if result.returncode != 0:
        raise RuntimeError(f"{args[0]} failed (exit {result.returncode}): {result.stderr.decode('utf-8', 'replace')}")
    return result.stdout.decode("utf-8", "replace")


def poppler_available() -> bool:
    """True only if pdftotext, pdffonts and pdfinfo are all on PATH."""
    import shutil
    return all(shutil.which(tool) for tool in ("pdftotext", "pdffonts", "pdfinfo"))


# --------------------------------------------------------------------------
# poppler-utils wrappers
# --------------------------------------------------------------------------

def pdf_info(pdf_path: Path) -> dict[str, str]:
    """Parse `pdfinfo` key/value output (Title, Pages, Encrypted, ...)."""
    text = _run(["pdfinfo", str(pdf_path)])
    info: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            info[key.strip()] = value.strip()
    return info


def pdf_fonts(pdf_path: Path) -> list[dict[str, str]]:
    """Parse `pdffonts` columnar output into one dict per embedded font."""
    text = _run(["pdffonts", str(pdf_path)])
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return []
    header, separator, *rows = lines
    spans = [match.span() for match in re.finditer(r"-+", separator)]
    names = [header[start:end].strip() for start, end in spans]
    fonts = []
    for row in rows:
        values = []
        for index, (start, end) in enumerate(spans):
            stop = len(row) if index == len(spans) - 1 else end
            values.append(row[start:stop].strip())
        fonts.append(dict(zip(names, values)))
    return fonts


def _paginate(text: str, *, expected_pages: int | None = None) -> list[str]:
    """Split `pdftotext`'s per-page form-feed (0x0C) output into one string per page."""
    parts = text.split("\x0c")
    if parts and parts[-1] == "":
        parts = parts[:-1]
    if expected_pages is not None and len(parts) != expected_pages:
        raise AssertionError(f"pdftotext produced {len(parts)} page(s), expected {expected_pages}")
    return parts


def layout_page_texts(pdf_path: Path, *, expected_pages: int | None = None) -> list[str]:
    """`pdftotext -layout` for the whole document, one entry per physical page.

    Column-aware layout mode: use this for anything read as a table (Allegati
    rows) or as plain body text (cover, notes via the whole-document form).
    """
    return _paginate(_run(["pdftotext", "-layout", str(pdf_path), "-"]), expected_pages=expected_pages)


def raw_page_texts(pdf_path: Path, *, expected_pages: int | None = None) -> list[str]:
    """`pdftotext -raw` for the whole document, one entry per physical page.

    Content-stream order rather than reading order: `-layout` silently drops
    the rotated draft watermark (measured: 0 of 48 hits with `-layout` on a
    known-draft PDF, 48 of 48 with `-raw`), so watermark detection always
    goes through this function, never `layout_page_texts`.
    """
    return _paginate(_run(["pdftotext", "-raw", str(pdf_path), "-"]), expected_pages=expected_pages)


def page_text_range(pdf_path: Path, first_page: int, last_page: int, *, mode: str = "raw") -> str:
    """`pdftotext -f N -l N` (the brief's own tool) for a physical page range.

    Default mode is `-raw` (content-stream order), not `-layout`: measured on
    a wrapped Allegati label ("2) Variazioni delle rim. ... semilav. e
    finiti"), `-layout` reflows the second line of a wrapped cell to *after*
    the row's numeric columns, splitting the label; `-raw` keeps Typst's own
    draw order, label-then-note-then-values, so a wrapped label stays one
    contiguous run of text.
    """
    flag = {"raw": "-raw", "layout": "-layout"}[mode]
    return _run(["pdftotext", flag, "-f", str(first_page), "-l", str(last_page), str(pdf_path), "-"])


#: The template inserts zero-width breakpoints after `_`, `+`, `/`, `.` in any
#: cell with no declared unit (`editorial.typ`'s `cell()`, so a long source id
#: or a label can wrap) — invisible on screen, but they land inside
#: `pdftotext`'s output (e.g. "rim.​ di prodotti"), splitting an otherwise
#: exact label in two. A human reading the PDF does not see them; neither
#: should an exact-substring check.
_INVISIBLE_CHARS = ("​", "‌", "‍", "﻿")

#: The same four characters `cell()` inserts a zero-width breakpoint after.
#: A visual line wrap exactly at one of those points (measured: "plus/​"
#: then a bare newline before "minusvalenze", no real space either side) makes
#: `pdftotext` emit no space there at all, which `.split()`/`.join(" ")` would
#: otherwise turn into a *spurious* space once the newline is collapsed. Both
#: sides of a comparison go through this, so the fix (drop any space right
#: after one of these characters) is safe: text that never wrapped there keeps
#: matching, because a real ". " in ordinary prose collapses to "." on BOTH
#: the label and the extracted page text identically.
_BREAK_HINT_CHARS = ("_", "+", "/", ".")


def normalize(text: str) -> str:
    for char in _INVISIBLE_CHARS:
        text = text.replace(char, "")
    collapsed = " ".join(text.split())
    for char in _BREAK_HINT_CHARS:
        collapsed = collapsed.replace(char + " ", char)
    return collapsed


# --------------------------------------------------------------------------
# euro-integer formatting: must match `chart-format.typ`'s
# `display-value(value, "eur", places: 0)`, which every editorial table cell
# uses (`editorial.typ`'s `cell()`, `places: if unit == "eur" { 0 } else { none }`).
# --------------------------------------------------------------------------

def format_euro_integer(value: Decimal) -> str:
    """Round to the nearest euro (half rounds away from zero) and group by thousands.

    `-0,3 -> 0`, never `-0`: the template's `sign` is empty whenever every
    rounded digit is zero, and this mirrors it via `abs(int(...))`.
    """
    quantized = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    digits = str(abs(int(quantized)))
    groups: list[str] = []
    remaining = digits
    while len(remaining) > 3:
        groups.insert(0, remaining[-3:])
        remaining = remaining[:-3]
    groups.insert(0, remaining)
    sign = "−" if quantized < 0 else ""
    return sign + ".".join(groups)


# --------------------------------------------------------------------------
# assertions: primitive, model-agnostic, each raising plain AssertionError.
# The domain wiring (which row goes on which page, which text is expected)
# lives in the test module, not here — this module never imports the report
# schema so it stays a genuinely independent check.
# --------------------------------------------------------------------------

def assert_pdf_signature(data: bytes) -> None:
    if not data.startswith(b"%PDF-"):
        raise AssertionError("artifact does not start with the %PDF- signature")


def assert_not_encrypted(info: dict[str, str]) -> None:
    if info.get("Encrypted", "").lower() != "no":
        raise AssertionError(f"PDF reports Encrypted={info.get('Encrypted')!r}, expected 'no'")


def assert_metadata_title(info: dict[str, str], expected_title: str) -> None:
    if info.get("Title") != expected_title:
        raise AssertionError(f"pdfinfo Title {info.get('Title')!r} does not match {expected_title!r}")


def assert_page_count(info: dict[str, str], expected_pages: int) -> None:
    actual = info.get("Pages")
    if actual is None or int(actual) != expected_pages:
        raise AssertionError(f"pdfinfo Pages={actual!r} does not match the editorial plan's {expected_pages} page(s)")


def assert_all_fonts_embedded(fonts: list[dict[str, str]]) -> None:
    if not fonts:
        raise AssertionError("pdffonts reported no fonts at all")
    missing = [font.get("name") for font in fonts if font.get("emb") != "yes"]
    if missing:
        raise AssertionError(f"fonts not embedded: {missing}")


def assert_text_present(haystack: str, needle: str, *, context: str) -> None:
    # Both sides go through `normalize`: a catalog label's leading two spaces
    # (behavioural for the frontend's indentation, not for PDF text extraction
    # — Typst renders the indent as layout, not as literal leading characters)
    # would otherwise make an untouched needle uncheckable.
    if normalize(needle) not in normalize(haystack):
        raise AssertionError(f"{context}: {needle!r} not found")


def assert_text_absent(haystack: str, needle: str, *, context: str) -> None:
    if normalize(needle) in normalize(haystack):
        raise AssertionError(f"{context}: {needle!r} unexpectedly found")


def assert_no_forbidden_technical_strings(full_text: str) -> None:
    found = [token for token in FORBIDDEN_TECHNICAL_STRINGS if token in full_text]
    if found:
        raise AssertionError(f"forbidden technical tokens leaked into the dossier text: {found}")


#: `key.style` / `key_style` tokens legitimately printed verbatim: a column
#: literally called "Codice" (diagnostics, source revisions) or
#: "Identificativo" (source engine) shows a technical code on purpose, for
#: traceability — a motivated, finite exception, not a pattern weakening.
#: `n.d` is `pdftotext`'s reading of the report's own "n.d." (non disponibile)
#: marker, printed on nearly every table with a missing value.
_KEY_STYLE_LABEL_EXCEPTIONS = frozenset({
    "n.d",
    "analysis_service",
    "adjustments_details_realigned", "adjustments_profit_realigned",
    "adjustments_unposted_mass", "legacy_assumption_provenance",
    "forecast_stale", "opening_balance_missing",
})

#: A manual CE/SP override or SP indexing driver in Allegato E («dettagli
#: ipotesi») is labelled with the raw `BudgetAssumptions` field the user
#: overrode («Override CE ce02_override», «Indicizzazione SP sp16g»): unlike
#: the codes this harness guards elsewhere, that field is user-chosen from 32
#: CE columns and an open SP set, so no finite allowlist could cover it —
#: a known, separate, smaller gap (not this lotto's fix), excluded here by
#: the fixed prefix that always precedes it, not by guessing every value.
_OVERRIDE_LABEL_PREFIX = re.compile(r"(Override CE|Override SP|Indicizzazione SP) [a-z][a-z0-9_.]*")

_KEY_STYLE_LABEL_PATTERN = re.compile(r"\b[a-z][a-z0-9]*(?:[_.][a-z0-9]+)+\b")


def assert_no_field_code_style_labels(full_text: str) -> None:
    """No row prints a raw field/model code as its label — `sp06c_crediti_collegate_breve`,
    `cashflow.operating.start.net_profit`, `ce01_ricavi_vendite` all leaked as
    the "Voce" of a row on real (AMBIENTA) data before `editorial_inventory.py`
    started resolving every forecast/closing-value line through
    `detailed_statements` first and `_FORECAST_LABEL_OVERRIDES` second,
    raising instead of falling back to the code (M2-02B integrazione, rilievo
    del coordinatore). A curated fixture never exercised this: its forecast
    lines already carry a real label, so this check is the harness's own
    defense, independent of that mechanism."""
    scrubbed = _OVERRIDE_LABEL_PREFIX.sub("", full_text)
    found = sorted(set(_KEY_STYLE_LABEL_PATTERN.findall(scrubbed)) - _KEY_STYLE_LABEL_EXCEPTIONS)
    if found:
        raise AssertionError(f"field/model codes leaked as row labels: {found}")


def assert_draft_watermark(raw_text: str, *, draft: bool) -> None:
    present = DRAFT_WATERMARK in raw_text
    if draft and not present:
        raise AssertionError("draft watermark missing from a draft page")
    if not draft and present:
        raise AssertionError("draft watermark present on a final page")


def assert_appendix_row_count_matches_plan(statement_id: str, row_ids: list[str], row_pages: dict[str, int]) -> None:
    """The model's row list for `statement_id` must have exactly one plan marker each.

    Catches a row silently dropped from (or duplicated into) the rendered
    Allegati even when nothing else in this module happens to look at it.
    """
    prefix = f"row:{statement_id}:"
    plan_count = sum(1 for content_id in row_pages if content_id.startswith(prefix))
    if len(row_ids) != plan_count:
        raise AssertionError(f"{statement_id}: model declares {len(row_ids)} appendix row(s), "
                              f"the editorial plan carries {plan_count}")
