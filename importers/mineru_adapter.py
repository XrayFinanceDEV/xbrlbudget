"""
Adapter: MinerU raw ``/file_parse`` result  →  normalized document evidence.

This produces a ``MinerUExtractionContext`` (document evidence), NOT a second balance
sheet. It never decides quadrature, never invents IV-CEE detail and never books amounts
without source text: the downstream importer pipeline (classifier A/B/C + deterministic
parsers + LLM + reconciliation + quadratura gates) owns every accounting decision.

Built against the REAL MinerU 3.2.0 envelope captured in
``tests/fixtures/mineru/file_parse_response.json``:
- ``md_content``: full Markdown of the document (best full text);
- ``content_list``: a JSON-encoded *string* → list of typed blocks
  (``text``/``header``/``footer``/``page_number``/``table``); table blocks carry an
  HTML ``table_body``; every block has ``page_idx`` and ``bbox``;
- ``middle_json``: a JSON-encoded *string* → ``{pdf_info: [per-page...]}``.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Normalized model (document evidence)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MinerUCell:
    text: str
    row: int
    column: int
    page: int


@dataclass(frozen=True)
class MinerURow:
    cells: tuple[MinerUCell, ...]
    page: int
    source_block_id: str


@dataclass(frozen=True)
class MinerUTable:
    html: str
    caption: str
    page: int
    rows: tuple[MinerURow, ...]


@dataclass(frozen=True)
class MinerUExtractionContext:
    full_text: str
    page_texts: tuple[str, ...]
    rows: tuple[MinerURow, ...]
    tables: tuple[MinerUTable, ...]
    headings: tuple[str, ...]
    current_year: Optional[int]
    comparative_year: Optional[int]
    raw_format: str
    mineru_version: Optional[str]

    @property
    def table_count(self) -> int:
        return len(self.tables)

    @property
    def page_count(self) -> int:
        return len(self.page_texts)

    @property
    def deterministic_text(self) -> str:
        """Line-oriented OCR text for existing deterministic CoGe parsers.

        A table row is flattened as one line per cell because the DEPI and
        single-column parsers expect ``code -> description -> amount`` lines.
        Headings/captions retain the section switches (Attivo, Passivo, Costi,
        Ricavi). This is derived evidence, not an accounting mapping.
        """
        lines: list[str] = []
        lines.extend(heading for heading in self.headings if heading)
        for table in self.tables:
            if table.caption:
                lines.append(table.caption)
            for row in table.rows:
                lines.extend(cell.text for cell in row.cells if cell.text)
        return "\n".join(lines) if lines else self.full_text


@dataclass(frozen=True)
class MinerUAccountingCandidate:
    """Conservative IV-CEE candidate derived only from structured MinerU rows.

    The adapter does not make a candidate valid by balancing it.  It merely maps
    source-labelled legal rows and carries the two printed side totals.  The
    importer remains responsible for accepting it through the normal mapper and
    quadratura gates.
    """

    current_bs: dict[str, Decimal]
    current_ce: dict[str, Decimal]
    prior_bs: Optional[dict[str, Decimal]]
    prior_ce: Optional[dict[str, Decimal]]
    source_fields: tuple[str, ...]
    unresolved_rows: tuple[str, ...]

    @property
    def source_detail_fields(self) -> int:
        return len(self.source_fields)

    @property
    def detail_level(self) -> str:
        if self.source_detail_fields >= 20:
            return "detailed"
        if self.source_detail_fields >= 8:
            return "standard"
        return "summary"


# --------------------------------------------------------------------------- #
# Italian number normalization (§6.2) — utility; the accounting extractors own
# the real mapping, but ambiguous tokens stay unresolved instead of guessed.
# --------------------------------------------------------------------------- #
_NUM_RE = re.compile(r"^-?\(?\d{1,3}(?:\.\d{3})*(?:,\d+)?\)?-?$")


def normalize_italian_number(token: str) -> Optional[Decimal]:
    """Parse an Italian-formatted amount to Decimal, or None if ambiguous.

    Handles ``1.234,56``, ``-1.234,56``, ``(1.234,56)`` and trailing-minus
    ``1.234,56-``. Returns None (does NOT guess) when the token is not an
    unambiguous number.
    """
    if token is None:
        return None
    t = token.strip().replace(" ", " ")
    t = re.sub(r"\s+", "", t)
    if not t or not _NUM_RE.match(t):
        return None
    negative = False
    if t.startswith("(") and t.endswith(")"):
        negative = True
        t = t[1:-1]
    if t.endswith("-"):
        negative = True
        t = t[:-1]
    if t.startswith("-"):
        negative = True
        t = t[1:]
    t = t.replace(".", "").replace(",", ".")
    try:
        value = Decimal(t)
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


# --------------------------------------------------------------------------- #
# HTML table parsing
# --------------------------------------------------------------------------- #
class _TableHTMLParser(HTMLParser):
    """Minimal <table> parser → list of rows, each a list of cell strings."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._cur: Optional[list[str]] = None
        self._buf: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._cur = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cur is not None:
            self._cur.append("".join(self._buf).strip())
            self._in_cell = False
            self._buf = []
        elif tag == "tr" and self._cur is not None:
            self.rows.append(self._cur)
            self._cur = None

    def handle_data(self, data):
        if self._in_cell:
            self._buf.append(data)


def _parse_table_html(html: str, page: int, block_id: str) -> tuple[MinerURow, ...]:
    parser = _TableHTMLParser()
    try:
        parser.feed(html or "")
    except Exception:  # noqa: BLE001 - untrusted HTML, never crash the import
        logger.warning("MinerU table HTML unparseable (block=%s)", block_id)
        return ()
    rows: list[MinerURow] = []
    for r_idx, raw_cells in enumerate(parser.rows):
        cells = tuple(
            MinerUCell(text=txt, row=r_idx, column=c_idx, page=page)
            for c_idx, txt in enumerate(raw_cells)
        )
        rows.append(MinerURow(cells=cells, page=page, source_block_id=f"{block_id}#r{r_idx}"))
    return tuple(rows)


_YEAR_RE = re.compile(r"\b(?:31/12/|31\.12\.|al\s+31/12/)?(19|20)\d{2}\b")


def _detect_years(full_text: str, tables: tuple[MinerUTable, ...]) -> tuple[Optional[int], Optional[int]]:
    """Best-effort year detection from table headers; None when unclear."""
    candidates: list[int] = []
    haystacks = [t.html for t in tables[:3]] + [full_text[:2000]]
    for hs in haystacks:
        for m in re.finditer(r"\b(19|20)(\d{2})\b", hs or ""):
            yr = int(m.group(0))
            if 1990 <= yr <= 2100:
                candidates.append(yr)
        if candidates:
            break
    if not candidates:
        return None, None
    uniq: list[int] = []
    for y in candidates:
        if y not in uniq:
            uniq.append(y)
    uniq_sorted = sorted(set(uniq), reverse=True)
    current = uniq_sorted[0] if uniq_sorted else None
    comparative = uniq_sorted[1] if len(uniq_sorted) > 1 else None
    return current, comparative


def build_extraction_context(raw: Any) -> MinerUExtractionContext:
    """Normalize a ``MinerURawResult`` (or a compatible dict) into a context.

    Accepts either the client's ``MinerURawResult`` dataclass or a plain dict with
    ``md_content``/``content_list``/``middle_json``/``version`` (eases testing).
    """
    md_content = getattr(raw, "md_content", None)
    content_list_str = getattr(raw, "content_list", None)
    middle_json_str = getattr(raw, "middle_json", None)
    version = getattr(raw, "version", None)
    if md_content is None and isinstance(raw, dict):
        md_content = raw.get("md_content", "")
        content_list_str = raw.get("content_list", "")
        middle_json_str = raw.get("middle_json", "")
        version = raw.get("version")

    md_content = md_content or ""
    content_list = _load_json_string(content_list_str, "content_list")
    middle_json = _load_json_string(middle_json_str, "middle_json")

    # Group text by page; collect tables, rows and headings.
    page_map: dict[int, list[str]] = {}
    headings: list[str] = []
    tables: list[MinerUTable] = []
    all_rows: list[MinerURow] = []

    if isinstance(content_list, list):
        for idx, block in enumerate(content_list):
            if not isinstance(block, dict):
                continue
            page = int(block.get("page_idx", 0) or 0)
            btype = block.get("type")
            if btype == "table":
                html = block.get("table_body", "") or ""
                caption_list = block.get("table_caption") or []
                caption = " ".join(c for c in caption_list if isinstance(c, str)).strip()
                block_id = f"t{idx}"
                rows = _parse_table_html(html, page, block_id)
                all_rows.extend(rows)
                tables.append(MinerUTable(html=html, caption=caption, page=page, rows=rows))
                if caption:
                    page_map.setdefault(page, []).append(caption)
            elif btype in ("text", "header"):
                text = block.get("text", "") or ""
                if text:
                    page_map.setdefault(page, []).append(text)
                if block.get("text_level") or btype == "header":
                    if text:
                        headings.append(text)
            # footer / page_number blocks are intentionally ignored for full_text

    # page_texts ordered by page index
    if page_map:
        max_page = max(page_map)
        page_texts = tuple("\n".join(page_map.get(p, [])) for p in range(max_page + 1))
    elif isinstance(middle_json, dict) and isinstance(middle_json.get("pdf_info"), list):
        page_texts = tuple("" for _ in middle_json["pdf_info"])
    else:
        page_texts = (md_content,) if md_content else ()

    # full_text: prefer MinerU markdown; fall back to concatenated page texts
    full_text = md_content if md_content.strip() else "\n\n".join(page_texts)

    if isinstance(middle_json, dict):
        version = version or middle_json.get("_version_name")

    tables_t = tuple(tables)
    current_year, comparative_year = _detect_years(full_text, tables_t)

    ctx = MinerUExtractionContext(
        full_text=full_text,
        page_texts=page_texts,
        rows=tuple(all_rows),
        tables=tables_t,
        headings=tuple(headings),
        current_year=current_year,
        comparative_year=comparative_year,
        raw_format="mineru_pipeline_v1",
        mineru_version=version,
    )
    logger.info(
        "MinerU adapter: pages=%d tables=%d rows=%d headings=%d version=%s text_len=%d",
        ctx.page_count, ctx.table_count, len(ctx.rows), len(ctx.headings),
        ctx.mineru_version, len(ctx.full_text),
    )
    return ctx


# --------------------------------------------------------------------------- #
# Structured rows -> conservative IV-CEE candidate
# --------------------------------------------------------------------------- #
_AMOUNT_IN_TEXT_RE = re.compile(
    r"(?<![\w/])(?:\(?-?(?:\d{1,3}(?:[.\s]\d{3})+|\d+)(?:,\d+)?\)?-?)(?![\w/])"
)
_ALPHA_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")


def _row_label_and_values(row: MinerURow) -> tuple[str, tuple[Decimal, ...]]:
    """Read a legal label followed by one/two amounts from one OCR table row.

    MinerU may return one cell per column or collapse the entire row into one
    HTML cell.  Only numeric tokens *after* the last alphabetic character are
    treated as amounts, which avoids interpreting legal prefixes such as
    ``A.1)`` as accounting values.
    """
    label_parts: list[str] = []
    values: list[Decimal] = []
    for cell in row.cells:
        text = re.sub(r"\s+", " ", (cell.text or "").replace("\xa0", " ")).strip()
        if not text:
            continue
        whole = normalize_italian_number(text)
        if whole is not None:
            values.append(whole)
            continue

        alpha_matches = list(_ALPHA_RE.finditer(text))
        last_alpha = alpha_matches[-1].start() if alpha_matches else -1
        amount_matches = [m for m in _AMOUNT_IN_TEXT_RE.finditer(text) if m.start() > last_alpha]
        parsed: list[Decimal] = []
        for match in amount_matches:
            amount = normalize_italian_number(match.group(0))
            if amount is not None:
                parsed.append(amount)
        if parsed:
            label_parts.append(text[: amount_matches[0].start()].strip(" :-–—|"))
            values.extend(parsed)
        else:
            label_parts.append(text)

    label = re.sub(r"\s+", " ", " ".join(part for part in label_parts if part)).strip()
    # A legal table has at most current and comparative columns.  Extra numeric
    # tokens before them are usually OCR artefacts/legal numbering; the final two
    # are the source amounts.
    return label, tuple(values[-2:])


def _section_from_label(label: str, statement: Optional[str], side: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    from importers.iv_cee_hierarchy import normalize

    normalized = normalize(label)
    if "conto economico" in normalized:
        return "ce", None
    if "stato patrimoniale" in normalized and "passivo" in normalized:
        return "bs", "passivo"
    if "stato patrimoniale" in normalized and "attivo" in normalized:
        return "bs", "attivo"
    if normalized in {"passivo", "passivita"} or "totale passivo" in normalized:
        return "bs", "passivo"
    if normalized == "attivo" or "totale attivo" in normalized:
        return "bs", "attivo"
    return statement, side


def _reserve_detail_field(label: str) -> Optional[str]:
    from importers.iv_cee_hierarchy import normalize

    normalized = normalize(label)
    if "sovrapprezzo" in normalized:
        return "sp12a_riserva_sovrapprezzo"
    if "rivalutaz" in normalized:
        return "sp12b_riserve_rivalutazione"
    if "riserva legale" in normalized:
        return "sp12c_riserva_legale"
    if "statutar" in normalized:
        return "sp12d_riserve_statutarie"
    if "copertura" in normalized and "fluss" in normalized:
        return "sp12f_riserva_copertura_flussi"
    if "portat" in normalized and "nuovo" in normalized:
        return "sp12g_utili_perdite_portati"
    if "azioni proprie" in normalized and "negativ" in normalized:
        return "sp12h_riserva_neg_azioni_proprie"
    if "altre riserve" in normalized:
        return "sp12e_altre_riserve"
    return None


def _debt_detail_field(label: str, aggregate: str) -> Optional[str]:
    from importers.iv_cee_hierarchy import normalize

    normalized = normalize(label)
    suffix = "breve" if aggregate == "sp16_debiti_breve" else "lungo"
    prefix = "sp16" if suffix == "breve" else "sp17"
    if any(term in normalized for term in ("banche", "mutui", "finanziamenti bancari")):
        code, name = "a", "debiti_banche"
    elif "obbligaz" in normalized:
        code, name = "c", "debiti_obbligazioni"
    elif "fornitor" in normalized:
        code, name = "d", "debiti_fornitori"
    elif any(term in normalized for term in ("tributar", "erario", "imposte")):
        code, name = "e", "debiti_tributari"
    elif any(term in normalized for term in ("previd", "inps", "inail")):
        code, name = "f", "debiti_previdenza"
    elif any(term in normalized for term in ("finanziator", "soci per finanziamenti")):
        code, name = "b", "debiti_altri_finanz"
    elif "debiti verso altri" in normalized or "altri debiti" in normalized:
        code, name = "g", "altri_debiti"
    else:
        return None
    return f"{prefix}{code}_{name}_{suffix}"


def _put_source_value(
    target: dict[str, Decimal],
    field: str,
    amount: Decimal,
    label: str,
    source_fields: set[str],
) -> None:
    """Store a directly supported value and preserve selected legal detail."""
    target[field] = target.get(field, Decimal("0")) + amount
    source_fields.add(field)

    detail_field: Optional[str] = None
    if field == "sp12_riserve":
        detail_field = _reserve_detail_field(label)
    elif field in {"sp16_debiti_breve", "sp17_debiti_lungo"}:
        detail_field = _debt_detail_field(label, field)
    if detail_field:
        target[detail_field] = target.get(detail_field, Decimal("0")) + amount
        source_fields.add(detail_field)


def extract_ivcee_candidate(
    context: MinerUExtractionContext,
) -> Optional[MinerUAccountingCandidate]:
    """Map structured MinerU table rows into current/prior IV-CEE dictionaries.

    This deliberately declines when both printed ``Totale Attivo`` and ``Totale
    Passivo`` are not present.  Derived totals or balancing plugs would turn OCR
    guesses into accounting facts; candidate acceptance belongs to the importer.
    """
    from importers.iv_cee_hierarchy import normalize, reconcile_source_detail, resolve

    current_bs: dict[str, Decimal] = {}
    current_ce: dict[str, Decimal] = {}
    prior_bs: dict[str, Decimal] = {}
    prior_ce: dict[str, Decimal] = {}
    current_source_fields: set[str] = set()
    prior_source_fields: set[str] = set()
    unresolved: list[str] = []
    statement: Optional[str] = None
    side: Optional[str] = None
    maturity_unspecified_current = False
    maturity_unspecified_prior = False

    # Preserve table order and use captions as section evidence when available.
    for table in context.tables:
        statement, side = _section_from_label(table.caption, statement, side)
        for row in table.rows:
            label, values = _row_label_and_values(row)
            if not label:
                continue
            statement, side = _section_from_label(label, statement, side)
            if not values:
                continue

            current_amount = values[0]
            prior_amount = values[1] if len(values) > 1 else None
            normalized = normalize(label)

            if "totale attivo" in normalized:
                current_bs["totale_attivo"] = current_amount
                current_source_fields.add("totale_attivo")
                if prior_amount is not None:
                    prior_bs["totale_attivo"] = prior_amount
                    prior_source_fields.add("totale_attivo")
                continue
            if "totale passivo" in normalized:
                current_bs["totale_passivo"] = current_amount
                current_source_fields.add("totale_passivo")
                if prior_amount is not None:
                    prior_bs["totale_passivo"] = prior_amount
                    prior_source_fields.add("totale_passivo")
                continue

            node = None
            if statement == "ce":
                node = resolve(label, statement="ce")
            elif statement == "bs":
                node = resolve(label, side=side, statement="bs")
            else:
                # Only accept an unambiguous statement when section headings were
                # lost by OCR.  Result rows are ambiguous between SP and CE.
                bs_node = resolve(label, side=side, statement="bs")
                ce_node = resolve(label, statement="ce")
                if (bs_node is None) != (ce_node is None):
                    node = bs_node or ce_node

            if node is None:
                if current_amount != 0:
                    unresolved.append(label[:160])
                continue
            if node.is_total or node.db_field is None:
                continue

            amount = current_amount
            prior_value = prior_amount
            if node.is_result and "perdita" in normalized and "utile" not in normalized:
                amount = -abs(amount)
                prior_value = -abs(prior_value) if prior_value is not None else None

            current_target = current_bs if node.statement == "bs" else current_ce
            _put_source_value(current_target, node.db_field, amount, label, current_source_fields)
            if prior_value is not None:
                prior_target = prior_bs if node.statement == "bs" else prior_ce
                _put_source_value(prior_target, node.db_field, prior_value, label, prior_source_fields)

            if node.db_field in {"sp16_debiti_breve", "sp17_debiti_lungo"}:
                has_maturity = any(term in normalized for term in ("entro", "oltre", "12 mesi"))
                if not has_maturity:
                    maturity_unspecified_current = True
                    maturity_unspecified_prior = maturity_unspecified_prior or prior_value is not None

    required_totals = {"totale_attivo", "totale_passivo"}
    if not required_totals.issubset(current_bs):
        return None

    if maturity_unspecified_current:
        current_bs["_source_maturity_unspecified"] = Decimal("1")
    if maturity_unspecified_prior:
        prior_bs["_source_maturity_unspecified"] = Decimal("1")

    # Fill only generic "other" detail buckets for source-published aggregates;
    # this preserves an explicitly unknown composition and makes the forecast
    # hierarchy consistent without inventing a typed counterparty.
    reconcile_source_detail(current_bs, current_ce)
    if required_totals.issubset(prior_bs):
        reconcile_source_detail(prior_bs, prior_ce)
        prior_bs_result: Optional[dict[str, Decimal]] = prior_bs
        prior_ce_result: Optional[dict[str, Decimal]] = prior_ce
    else:
        prior_bs_result = None
        prior_ce_result = None

    source_fields = tuple(sorted(current_source_fields))
    current_bs["_source_mineru_ivcee"] = Decimal("1")
    current_bs["_mineru_source_detail_fields"] = Decimal(len(source_fields))
    if prior_bs_result is not None:
        prior_bs_result["_source_mineru_ivcee"] = Decimal("1")
        prior_bs_result["_mineru_source_detail_fields"] = Decimal(len(prior_source_fields))

    return MinerUAccountingCandidate(
        current_bs=current_bs,
        current_ce=current_ce,
        prior_bs=prior_bs_result,
        prior_ce=prior_ce_result,
        source_fields=source_fields,
        unresolved_rows=tuple(unresolved),
    )


def _load_json_string(value: Any, label: str) -> Any:
    """MinerU nests JSON as a *string*; parse defensively, never crash."""
    if value is None or value == "":
        return None
    if isinstance(value, (list, dict)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            logger.warning("MinerU %s not valid JSON", label)
            return None
    return None
