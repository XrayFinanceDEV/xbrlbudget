"""Sezioni contrapposte DEPI e a codici di 8 cifre (lettura per coordinate).

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from collections import defaultdict
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from importers.situazione_contabile.comune import (
    Entry, _parse_amount,
)
from importers.situazione_contabile.depi import (
    _classify_code,
)
from importers.situazione_contabile.regole import (
    _kw_any, _kw_match,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.situazione_contabile_parser")


# ---------------------------------------------------------------------------
# Contrapposte 2-column 8-digit parser (coordinate-based)
# Layout: physical ATTIVITA' (left) / PASSIVITA' (right) columns, 8-digit parent
# codes with 6-digit+3-digit sub-accounts. PyMuPDF interleaves the columns in
# the text flow, so we split by word coordinates instead. Handles pages that
# are rotated 90deg (column = perpendicular axis).
# ---------------------------------------------------------------------------

_C8_PARENT_RE = re.compile(r'^(\d{8})$')

_C8_SUB_RE = re.compile(r'^\d{6}$')

_C8_AMOUNT_RE = re.compile(r'^-?\d{1,3}(?:\.\d{3})*,\d{2}$')

_CONTRA_LINE_RE = re.compile(
    r'^\s*('
    r'\d{2}/(?:\d{2}|\*\*)/(?:\d{3}|\*{3})'
    r'|\*{3,5}'
    r')\s+(.*?)\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$'
)

def is_contrapposte_depi(file_path: str) -> bool:
    """Detect the DEPI 2-physical-column contrapposte layout (e.g. 309 FORMETAL).

    NOTE: currently UNUSED. The companion parser below extracts these files but
    cannot reconcile their sign-based contra items to a perfect balance, so the
    detection in is_situazione_contabile defers contrapposte layouts to the LLM.
    Kept for reference / future hardening.

    Uses word coordinates: DEPI XX/YY/ZZZ codes present, both ATTIVITA' and
    PASSIVITA' headers, and account codes clustered in TWO distinct horizontal
    bands (left/right columns) on the same page.
    """
    try:
        doc = fitz.open(file_path)
    except Exception:
        return False
    try:
        full = "".join(p.get_text() for p in doc)
        spaced = re.sub(r'\s+', '', full.upper())
        if len(re.findall(r'\b\d{2}/\d{2}/\d{3}\b', full)) < 10:
            return False
        if 'ATTIVITA' not in spaced or 'PASSIVITA' not in spaced:
            return False
        code_re = re.compile(r'^\d{2}/(?:\d{2}|\*\*)/(?:\d{3}|\*{3})$')
        for page in doc:
            xs = [(w[0] + w[2]) / 2 for w in page.get_text('words') if code_re.match(w[4])]
            if len(xs) < 6:
                continue
            mid = page.rect.width / 2
            left = sum(1 for x in xs if x < mid)
            right = len(xs) - left
            if left >= 3 and right >= 3:
                return True
        return False
    finally:
        doc.close()

def parse_entries_contrapposte_depi(file_path: str) -> List[Entry]:
    """Parse a DEPI contrapposte (two physical columns) trial balance.

    Splits each page into left/right columns by the x midpoint, reconstructs
    one logical line per row, and parses 'CODE DESC AMOUNT'. Section is taken
    from each column's spaced header (ATTIVITA'/PASSIVITA' or COSTI/RICAVI).
    """
    from collections import defaultdict
    doc = fitz.open(file_path)
    entries: List[Entry] = []
    declared_utile = None
    declared_perdita = False

    def col_lines(ws, lo, hi):
        rows = defaultdict(list)
        for w in ws:
            cx = (w[0] + w[2]) / 2
            if lo <= cx < hi:
                rows[round(w[1])].append(w)
        out = []
        for y in sorted(rows):
            rows[y].sort(key=lambda w: w[0])
            out.append(' '.join(w[4] for w in rows[y]))
        return out

    def col_section(lines, is_sp):
        joined = re.sub(r'\s+', '', ' '.join(lines[:8]).upper())
        if is_sp:
            if 'ATTIVITA' in joined and 'PASSIVITA' not in joined:
                return 'attivo'
            if 'PASSIVITA' in joined:
                return 'passivo'
            return ''
        if 'RICAVI' in joined and 'COSTI' not in joined:
            return 'ricavi'
        if 'COSTI' in joined:
            return 'costi'
        return ''

    for page in doc:
        ptext = page.get_text()
        pu = ptext.upper()
        is_sp = 'PATRIMONIALE' in re.sub(r'\s+', '', pu)
        is_ce = 'CONTOECONOMICO' in re.sub(r'\s+', '', pu)
        if not (is_sp or is_ce):
            continue
        ws = page.get_text('words')
        if not ws:
            continue
        page_mid = page.rect.width / 2
        left_lines = col_lines(ws, 0, page_mid)
        right_lines = col_lines(ws, page_mid, 1e9)
        left_sec = col_section(left_lines, is_sp)
        right_sec = col_section(right_lines, is_sp)
        # Fallbacks if a header was not detected
        if not left_sec:
            left_sec = 'attivo' if is_sp else 'costi'
        if not right_sec:
            right_sec = 'passivo' if is_sp else 'ricavi'

        for lines, sec in ((left_lines, left_sec), (right_lines, right_sec)):
            for ln in lines:
                m = _CONTRA_LINE_RE.match(ln)
                if not m:
                    continue
                code, desc, amt_s = m.group(1), m.group(2).strip(), m.group(3)
                lvl = _classify_code(code)
                amount = _parse_amount(amt_s)
                if lvl == 4:
                    if declared_utile is None:
                        declared_utile = amount
                        declared_perdita = 'PERDITA' in desc.upper()
                    continue
                if lvl >= 3:
                    continue  # section totals / pareggio
                # A booked "UTILE/PERDITA DELL'ESERCIZIO" equity line is part of
                # the declared section total; retain it as a reserve (the footer
                # plug carries the current-year result) by tagging it prior.
                du = desc.upper()
                if sec == 'passivo' and (
                        _kw_match(du, ['UTILE', 'ESERCIZ'])
                        or _kw_match(du, ['PERDITA', 'ESERCIZ'])
                        or _kw_match(du, ['RISULTATO', 'ESERCIZ'])):
                    if not _kw_any(du, ['PORTATI', 'PRECEDENT', 'NUOVO', 'PORTATE']):
                        desc = desc + ' (PRECEDENTE)'
                entries.append(Entry(code=code, description=desc,
                                     amount=amount, level=lvl, section=sec))

    doc.close()

    if declared_utile is not None:
        if declared_perdita:
            entries.append(Entry(code='****', description="PERDITA D'ESERCIZIO",
                                 amount=declared_utile, level=4, section='attivo'))
        else:
            entries.append(Entry(code='****', description="UTILE D'ESERCIZIO",
                                 amount=declared_utile, level=4, section='passivo'))

    return entries

def is_contrapposte_8digit(text: str) -> bool:
    """Detect the contrapposte (two physical columns) 8-digit layout (e.g. 330)."""
    upper = text.upper()
    if 'TOTALE A PAREGGIO' not in upper:
        return False
    if not re.search(r"ATTIVITA'?\s*\n?\s*PASSIVITA'?|ATTIVITA.{0,40}PASSIVITA", upper, re.DOTALL):
        # column headers usually appear close together
        if 'PASSIVITA' not in upper or 'ATTIVITA' not in upper:
            return False
    if len(re.findall(r'\b\d{8}\b', text)) < 5:
        return False
    # Sub-account "NNNNNN NNN" pattern is the contrapposte signature
    return bool(re.search(r'\b\d{6}\s+\d{3}\b', text))

def _c8_parse_side(words, lo: float, hi: float, axis: int = 1) -> List[Entry]:
    """Parse one column (words whose split-axis coordinate is in (lo, hi]).

    ``axis`` is the coordinate that SEPARATES the two contrapposte columns:

    * ``axis=1`` (default) — rotated page: columns are stacked along y and a row
      runs along x, read bottom-to-top. This is the original behaviour.
    * ``axis=0`` — unrotated landscape (AGO "Situazione Contabile"): columns sit
      side by side along x and a row runs along y, read left-to-right.

    Tokens are flattened into one reading-order stream and consumed as
    ``code -> description -> amount``, so grouping only fixes ORDER: baseline
    jitter between a code and its amount cannot break the pairing.
    """
    from collections import defaultdict
    rows: Dict[int, list] = defaultdict(list)
    for w in words:
        if lo < w[axis] <= hi:
            rows[round(w[1 - axis])].append(w)
    toks: List[str] = []
    for key in sorted(rows):
        if axis == 1:
            rows[key].sort(key=lambda w: -w[1])  # rotated reading order (top→bottom)
        else:
            rows[key].sort(key=lambda w: w[0])   # left→right within the row
        toks.extend(w[4] for w in rows[key])

    out: List[Tuple[str, List[str], Optional[Decimal]]] = []
    cur: Optional[Tuple[str, List[str], list]] = None
    results: List[Entry] = []

    code = None
    desc: List[str] = []
    amt: Optional[Decimal] = None

    def flush():
        if code is not None and amt is not None:
            results.append(Entry(code=code, description=' '.join(desc),
                                 amount=amt, level=1, section=''))

    for t in toks:
        if _C8_PARENT_RE.match(t):
            flush()
            code = t
            desc = []
            amt = None
            continue
        if code is None:
            continue
        # Il pie' di pagina ("TOTALE PASSIVITA' / UTILE D'ESERCIZIO / TOTALE A
        # PAREGGIO") chiude l'ultimo conto: non e' descrizione sua. Accodato, faceva
        # leggere "UTILE ... ESERCIZIO" nella descrizione di un debito (budget_612).
        if t.upper() == 'TOTALE':
            flush()
            code = None
            continue
        if _C8_AMOUNT_RE.match(t):
            if amt is None:
                amt = _parse_amount(t)
            continue
        if _C8_SUB_RE.match(t) or t == '-' or t.startswith('_'):
            continue
        if t.isdigit():  # the "000"/"001" sub-account suffix
            continue
        desc.append(t)
    flush()
    return results

def _c8_split_columns(words, axis: int, mid: float):
    """Return (left_side, right_side) entries for one page given the document
    split axis + gutter, so the header-driven pass and the header-less second
    pass share EXACTLY the same column geometry.

    'left' is always the ATTIVITA'/COSTI side, 'right' the PASSIVITA'/RICAVI
    side, regardless of axis: on an unrotated page (axis=0) that is lower-x vs
    higher-x; on a rotated page (axis=1) the reading coordinate is inverted so
    the left side is the HIGHER coordinate.
    """
    if axis == 0:
        return (_c8_parse_side(words, -1e9, mid, axis=0),
                _c8_parse_side(words, mid, 1e9, axis=0))
    return (_c8_parse_side(words, mid, 1e9, axis=1),
            _c8_parse_side(words, -1e9, mid, axis=1))

def _c8_refine_gutter_x(words, header_mid: float) -> float:
    """Place the attivo|passivo gutter in the clean vertical gap BEFORE the
    right-hand code column, on an unrotated page.

    Each contrapposte side is ``code | description | amount`` and the LEFT side's
    amount column is right-aligned close to the RIGHT side's code column, so the
    header-word midpoint can fall INSIDE the left amount band and misassign those
    amounts to the passivo reader (budget_615: header_mid=365 slices the attivo
    amounts at x=367-379, losing ~260k). The two 8-digit code columns bracket a
    clean gap; put the gutter at its middle. Returns the header midpoint unchanged
    when it already sits in that gap, so pages the header split reads correctly
    are untouched (additive)."""
    code_xs = sorted(w[0] for w in words if re.fullmatch(r'\d{8}', w[4]))
    if len(code_xs) < 2:
        return header_mid
    gap, gi = max((code_xs[i + 1] - code_xs[i], i) for i in range(len(code_xs) - 1))
    if gap < 100:                      # a single code column: nothing to split
        return header_mid
    right_code_x = code_xs[gi + 1]
    # Le parole allineate alla colonna codici di destra (entro 2 pt: es. le
    # didascalie "TOTALE PASSIVITA'" a filo dei codici) appartengono a QUELLA
    # colonna, non a sinistra: contarle mette il gutter a 0,001 pt dai codici e
    # sulle pagine dove la colonna slitta di pochi decimi (budget_620: 417,12 ->
    # 416,76) tutti i conti di destra finiscono a sinistra.
    left_max = max((w[0] for w in words if w[0] < right_code_x - 2.0), default=header_mid)
    if left_max >= right_code_x:
        return header_mid
    if left_max <= header_mid <= right_code_x:
        return header_mid              # header gutter already in the clean gap
    return (left_max + right_code_x) / 2

def parse_entries_contrapposte_8digit(file_path: str) -> List[Entry]:
    """Parse a contrapposte 8-digit trial balance using word coordinates."""
    doc = fitz.open(file_path)
    entries: List[Entry] = []
    declared_utile = None
    declared_perdita = False
    declared_attivo = Decimal('0')
    declared_passivo = Decimal('0')

    # Document-level gutter/axis learned from the page(s) that DO carry live
    # ATTIVITA'/PASSIVITA' header text tokens, reused by the second pass to read
    # the pages whose headers are drawn as vectors (budget_615: only page 1 has
    # live headers, but the SP spills onto page 0 and the CE onto pages 3-7).
    doc_axis: Optional[int] = None
    doc_mid: Optional[float] = None
    read_pages: set = set()

    for pidx, page in enumerate(doc):
        words = page.get_text('words')
        upper = page.get_text().upper()
        is_sp = 'SITUAZIONE PATRIMONIALE' in upper or ("ATTIVITA" in upper and "PASSIVITA" in upper)
        is_ce = 'CONTO ECONOMICO' in upper or ("COSTI" in upper and "RICAVI" in upper)
        if not (is_sp or is_ce):
            continue

        # Determine the column-split coordinate from the two header words.
        if is_sp:
            left_lbl, right_lbl = "ATTIVITA'", "PASSIVITA'"
            left_sec, right_sec = 'attivo', 'passivo'
        else:
            left_lbl, right_lbl = 'COSTI', 'RICAVI'
            left_sec, right_sec = 'costi', 'ricavi'

        # Column-split coordinate from the DATA column header pair (the one at
        # the smallest x; later pairs belong to the TOTALE summary section).
        lefts = [(w[0], w[1]) for w in words if w[4].rstrip("'") == left_lbl.rstrip("'")]
        rights = [(w[0], w[1]) for w in words if w[4].rstrip("'") == right_lbl.rstrip("'")]
        if not lefts or not rights:
            continue
        lx, ly = min(lefts, key=lambda p: p[0])
        rx, ry_ = min(rights, key=lambda p: p[0])
        # Which coordinate SEPARATES the two columns? A rotated contrapposte page
        # stacks them along y (headers share x); an unrotated landscape export puts
        # them side by side along x (headers share y — AGO budget_615: ATTIVITA'
        # x=156.12 y=90.74, PASSIVITA' x=574.55 y=90.74). Assuming "rotated" on an
        # unrotated page collapsed every word into `left` and left the passivo column
        # EMPTY (totale_passivo=0). Pick the axis on which the headers actually differ.
        if abs(rx - lx) >= abs(ry_ - ly):
            axis, mid = 0, (lx + rx) / 2      # side by side: split by x
            mid = _c8_refine_gutter_x(words, mid)
        else:
            axis, mid = 1, (ly + ry_) / 2     # stacked: split by y (rotated page)
        left, right = _c8_split_columns(words, axis, mid)
        # Remember the SP gutter at document level for the header-less pass.
        if is_sp and doc_mid is None:
            doc_axis, doc_mid = axis, mid
        if not (left or right):
            # The header split yielded nothing — e.g. a CE footer page where the
            # "TOTALE COSTI/RICAVI" summary labels were mistaken for the column
            # headers, giving a gutter that splits a code from its amount. Leave
            # the page for the second pass to read via the document-level gutter.
            continue
        for e in left:
            e.section = left_sec
        for e in right:
            e.section = right_sec
        entries.extend(left)
        entries.extend(right)
        read_pages.add(pidx)

        # Footer totals. Labels may be stacked ("TOTALE ATTIVITA'\nTOTALE
        # PASSIVITA'\n<attivo>\n<passivo>\n..."), so take the first two amounts
        # that follow the stacked TOTALE ATTIVITA'/PASSIVITA' labels.
        if is_sp:
            ptext = page.get_text()
            m = re.search(
                r"TOTALE\s+ATTIVITA'?\s*\n?\s*TOTALE\s+PASSIVITA'?\s*\n?\s*"
                r"([\d.]+,\d{2})\s*\n?\s*([\d.]+,\d{2})",
                ptext, re.IGNORECASE)
            if m:
                declared_attivo = _parse_amount(m.group(1))
                declared_passivo = _parse_amount(m.group(2))
            else:
                mt = re.search(r"TOTALE ATTIVITA'?\s*\n?\s*([\d.]+,\d{2})", ptext, re.IGNORECASE)
                if mt:
                    declared_attivo = _parse_amount(mt.group(1))
                mp = re.search(r"TOTALE PASSIVITA'?\s*\n?\s*([\d.]+,\d{2})", ptext, re.IGNORECASE)
                if mp:
                    declared_passivo = _parse_amount(mp.group(1))

    # --- Second pass: pages whose ATTIVITA'/PASSIVITA'/COSTI/RICAVI headers are
    # drawn as VECTORS (no live text token), so the header-driven pass skipped
    # them and most of the document was lost. Reuse the document-level gutter and
    # keep the contrapposte COLUMN as ground truth for the side: the left column
    # is the debit-nature side (attivo / costi), the right the credit-nature side
    # (passivo / ricavi). Whether a page is SP or CE comes from ACCOUNT
    # RECOGNITION, not code prefixes (which differ across gestionali): revenue and
    # cost-of-production accounts resolve to the IV-CEE statement 'ce', SP accounts
    # to 'bs'. The CE section runs contiguously to the end of the document, so the
    # first majority-CE page marks the boundary; past it the ammortamento/TFR/
    # salari lines (which resolve to 'bs' in isolation) are correctly read as CE.
    # Additive: pages with live headers were all read above (read_pages).
    if doc_mid is not None:
        from importers.iv_cee_hierarchy import resolve as _resolve_ivcee
        pending = []          # (pidx, left, right) for each header-less data page
        ce_start = None       # first page index whose accounts are majority CE
        for pidx, page in enumerate(doc):
            if pidx in read_pages:
                continue
            words = page.get_text('words')
            if not any(re.fullmatch(r'\d{8}', w[4]) for w in words):
                continue
            left, right = _c8_split_columns(words, doc_axis, doc_mid)
            pending.append((pidx, left, right))
            if ce_start is None:
                n_ce = sum(1 for e in left + right
                           if _resolve_ivcee(e.description, statement='ce'))
                n_bs = sum(1 for e in left + right
                           if _resolve_ivcee(e.description, statement='bs'))
                if n_ce > n_bs:
                    ce_start = pidx
        for pidx, left, right in pending:
            if ce_start is not None and pidx >= ce_start:
                left_sec, right_sec = 'costi', 'ricavi'
            else:
                # SP gross presentation: attivo on the left, passivo (incl. fondi
                # ammortamento shown gross on the passivo side) on the right.
                left_sec, right_sec = 'attivo', 'passivo'
            for e in left:
                e.section = left_sec
            for e in right:
                e.section = right_sec
            entries.extend(left)
            entries.extend(right)

    doc.close()

    # Current-year result = the gap between the declared section totals (the
    # SP-booked utile/perdita account is part of those totals; the plug is the
    # remaining difference up to TOTALE A PAREGGIO).
    if declared_attivo and declared_passivo:
        gap = declared_passivo - declared_attivo
        if gap >= 0:
            declared_utile = gap          # passivo > attivo → perdita on attivo side
            declared_perdita = True
        else:
            declared_utile = -gap         # attivo > passivo → utile on passivo side
            declared_perdita = False

    # When the SP footer TOTALE ATTIVITA'/PASSIVITA' are unreadable (drawn as
    # vectors — budget_615), the current-year result is still fully determined by
    # the CE: utile = ricavi - costi. The CE mastri are in the text layer, so this
    # recovers the result without trusting a corrupt SP footer.
    if declared_utile is None:
        ricavi_sum = sum((e.amount for e in entries
                          if e.section == 'ricavi' and e.amount), Decimal('0'))
        costi_sum = sum((e.amount for e in entries
                         if e.section == 'costi' and e.amount), Decimal('0'))
        if ricavi_sum or costi_sum:
            res = ricavi_sum - costi_sum
            declared_utile = abs(res)
            declared_perdita = res < 0

    # Remove the SP-booked utile/perdita account from equity classification by
    # tagging it as prior (the footer plug carries the current-year result).
    for e in entries:
        du = e.description.upper()
        if e.section in ('attivo', 'passivo') and (
                _kw_match(du, ['UTILE', 'ESERCIZ'])
                or _kw_match(du, ['PERDITA', 'ESERCIZ'])
                or _kw_match(du, ['RISULTATO', 'ESERCIZ'])):
            # Keep it where it sits (so declared totals reconcile) but neutralise
            # the equity skip by relabelling as a generic balance item.
            if e.section == 'attivo':
                e.description = 'ALTRE ATTIVITA ' + e.description
            else:
                e.description = e.description + ' (PRECEDENTE)'

    if declared_utile is not None:
        if declared_perdita:
            entries.append(Entry(code='****', description="PERDITA D'ESERCIZIO",
                                 amount=declared_utile, level=4, section='attivo'))
        else:
            entries.append(Entry(code='****', description="UTILE D'ESERCIZIO",
                                 amount=declared_utile, level=4, section='passivo'))

    return entries

def _c8_dettaglio_rows(words, doc_mid: float, doc_axis: int):
    """Yield ``(code, description, amount)`` for the 6-digit DETTAGLIO lines in
    the PASSIVO (right) column. On these AGO exports the dettaglio amounts carry
    the underline drawn as interlaced '_' glyphs INSIDE the amount token
    (``_2_.00_0_,_0_0_`` = 2.000,00); the digits are all present, so the glyphs
    are stripped before parsing. A token that does not reduce to a clean amount is
    skipped, never guessed — and the caller self-validates the recovered subset
    against the balance gap, so any mis-strip is rejected rather than trusted."""
    from collections import defaultdict
    if doc_axis == 0:
        side = [w for w in words if w[0] > doc_mid]
    else:
        side = [w for w in words if w[1] <= doc_mid]
    rows: Dict[int, list] = defaultdict(list)
    for w in side:
        rows[round(w[1 - doc_axis])].append(w)
    toks: List[str] = []
    for key in sorted(rows):
        rows[key].sort(key=(lambda w: -w[1]) if doc_axis == 1 else (lambda w: w[0]))
        toks.extend(w[4] for w in rows[key])

    out: List[Tuple[str, str, Decimal]] = []
    code: Optional[str] = None
    desc: List[str] = []
    amt: Optional[Decimal] = None

    def flush():
        if code is not None and amt is not None:
            out.append((code, ' '.join(desc), amt))

    for t in toks:
        tc = t.replace('_', '')                # remove interlaced underline glyphs
        if re.fullmatch(r'\d{6}', tc):         # a new dettaglio code (codes are clean)
            flush()
            code, desc, amt = tc, [], None
            continue
        if code is None:
            continue
        if re.fullmatch(r'\d{1,3}(?:\.\d{3})*,\d{2}', tc):  # amount (underline stripped)
            if amt is None:
                amt = _parse_amount(tc)
            continue
        if tc in ('000', '-', '') or tc.isdigit():
            continue
        if amt is None:                        # description precedes the amount;
            desc.append(t)                     # ignore trailing tokens (footer noise)
    flush()
    return out

def _unique_subset_summing_to(cands, target: Decimal, tol: Decimal = Decimal('1')):
    """Return the UNIQUE non-empty subset of ``cands`` (each ``(amount, ...)``)
    whose amounts sum to ``target`` within ``tol``; ``None`` when there is no such
    subset or more than one (ambiguous → refuse rather than guess)."""
    n = len(cands)
    found = None
    for mask in range(1, 1 << n):
        s = Decimal('0')
        for i in range(n):
            if mask & (1 << i):
                s += cands[i][0]
        if abs(s - target) <= tol:
            if found is not None:
                return None                     # ambiguous
            found = mask
    if found is None:
        return None
    return [cands[i] for i in range(n) if found & (1 << i)]

def _c8_recover_orphan_passivo(file_path: str, bs: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Recover passivo mastri whose 8-digit total line is drawn as a VECTOR
    (unreadable) from their CLEAN 6-digit dettagli on a dettaglio-only page.

    Only the mastro totals are trustworthy on these AGO exports (most dettaglio
    amounts are corrupted), EXCEPT where a mastro total is missing entirely
    (vector-drawn): there the happens-to-be-clean dettagli are the sole surviving
    figure. This reads those clean passivo dettagli and adds back ONLY the subset
    that closes the Attivo-vs-Passivo gap EXACTLY, keeping the result only if the
    sheet then balances (self-validation). Dettagli whose parent mastro was
    already captured (e.g. amministratori c/compensi, already inside a read
    Altri-debiti mastro) do not fit the gap and are excluded. Cannot corrupt a
    sheet: worst case it returns ``bs`` unchanged."""
    ta = bs.get('totale_attivo') or Decimal('0')
    tp = bs.get('totale_passivo') or Decimal('0')
    gap = ta - tp
    if gap <= Decimal('1'):
        return bs                              # passivo not short — nothing to do

    from importers.iv_cee_hierarchy import resolve as _resolve_ivcee
    doc = fitz.open(file_path)
    try:
        doc_axis, doc_mid = 0, None
        for page in doc:
            words = page.get_text('words')
            lefts = [w for w in words if w[4].rstrip("'") == "ATTIVITA"]
            rights = [w for w in words if w[4].rstrip("'") == "PASSIVITA"]
            if not lefts or not rights:
                continue
            lx = min(lefts, key=lambda w: w[0])
            rx = min(rights, key=lambda w: w[0])
            if abs(rx[0] - lx[0]) >= abs(rx[1] - lx[1]):
                doc_axis, doc_mid = 0, _c8_refine_gutter_x(words, (lx[0] + rx[0]) / 2)
            else:
                doc_axis, doc_mid = 1, (lx[1] + rx[1]) / 2
            break
        if doc_mid is None:
            return bs
        cands = []                             # (amount, db_field, desc)
        for page in doc:
            words = page.get_text('words')
            if any(re.fullmatch(r'\d{8}', w[4]) for w in words):
                continue                       # not a dettaglio-only page
            for code, desc, amt in _c8_dettaglio_rows(words, doc_mid, doc_axis):
                node = _resolve_ivcee(desc, side='passivo', statement='bs')
                field = node.db_field if (node and node.db_field) else None
                if field == 'sp13_utile_perdita':
                    field = None               # a debt is never the year's result
                cands.append((amt, field, desc))
    finally:
        doc.close()
    if not cands or len(cands) > 18:
        return bs

    subset = _unique_subset_summing_to(cands, gap)
    if subset is None:
        return bs

    def _add(d, key, amt):
        d[key] = (d.get(key) or Decimal('0')) + amt

    new_bs = dict(bs)
    for amt, field, desc in subset:
        if field:                              # resolve() gives a full DB name; the SC
            m = re.match(r'(sp\d+)', field)    # dict aggregates use the SHORT key (sp18)
            _add(new_bs, m.group(1) if m else 'sp16', amt)
        else:                                  # unresolved "altri debiti" → route by
            du = desc.upper()                  # the entro/oltre marker, keeping the
            oltre = ('(OE)' in du or 'OLTRE' in du)  # aggregate == Σ sub-fields so the
            _add(new_bs, 'sp17' if oltre else 'sp16', amt)             # hierarchy check
            _add(new_bs, 'sp17g_altri_debiti_lungo' if oltre          # stays coherent
                 else 'sp16g_altri_debiti_breve', amt)
    new_bs['totale_passivo'] = tp + gap        # subset sums to the gap by construction
    if abs(ta - new_bs['totale_passivo']) <= Decimal('1'):
        logger.info(f"Route C: recuperati {len(subset)} mastri passivo orfani "
                    f"(vettoriali) per {gap:,.2f} — bilancio ora quadrato")
        return new_bs
    return bs

_C8_IMPORTO = r'(-?\d{1,3}(?:\.\d{3})*,\d{2}-?)'

def _c8_stampato(full_text: str, didascalia: str) -> Optional[Decimal]:
    """L'unico importo stampato subito dopo ``didascalia`` (regex), o None se manca o
    se il documento ne stampa piu' d'uno diverso."""
    trovati = {_parse_amount(m.group(1).rstrip('-'))
               for m in re.finditer(didascalia + r'\s*\n?\s*' + _C8_IMPORTO, full_text,
                                    re.IGNORECASE)}
    return trovati.pop() if len(trovati) == 1 else None

def _c8_risultato_stampato(full_text: str, entries: List[Entry],
                           bs: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Un mastro di conto economico il cui importo il PDF disegna come grafica e non come
    testo (budget_618/619, AGO: "Interessi e altri on.fin.v/terzi") manca alla lettura: il
    CE esce con un utile piu' alto, e sp13 = utile CE lascia lo SP sbilanciato della stessa
    massa. Se il risultato stampato ("UTILE/PERDITA D'ESERCIZIO") chiude lo SP al centesimo
    E la differenza fra utile CE e risultato stampato e' esattamente il TOTALE COSTI
    stampato meno i costi letti (coi ricavi letti pari al TOTALE RICAVI stampato), sp13
    diventa il risultato stampato
    (decisione del proprietario, 2026-10-14). Il CE non si tocca: la massa non letta si
    dichiara (``_ce_massa_non_letta``) e l'utente la inserisce in Rettifiche. Due controlli
    stampati indipendenti, nessun importo inventato; altrimenti ``bs`` resta com'e'."""
    tol = Decimal('0.05')
    ta = bs.get('totale_attivo') or Decimal('0')
    tp = bs.get('totale_passivo') or Decimal('0')
    sp13 = bs.get('sp13') or Decimal('0')
    if abs(ta - tp) <= tol:
        return bs
    utile = _c8_stampato(full_text, r"UTILE\s+D[' ]\s*ESERCIZIO")
    perdita = _c8_stampato(full_text, r"PERDITA\s+D[' ]\s*ESERCIZIO")
    if (utile is None) == (perdita is None):
        return bs
    stampato = utile if utile is not None else -perdita
    if abs(ta - (tp - sp13 + stampato)) > tol or abs(sp13 - stampato) <= tol:
        return bs
    tot_costi = _c8_stampato(full_text, r'TOTALE\s+COSTI')
    tot_ricavi = _c8_stampato(full_text, r'TOTALE\s+RICAVI')
    if tot_costi is None or tot_ricavi is None:
        return bs
    costi = sum((e.amount for e in entries if e.section == 'costi'), Decimal('0'))
    ricavi = sum((e.amount for e in entries if e.section == 'ricavi'), Decimal('0'))
    non_letti = tot_costi - costi
    if (abs(tot_ricavi - ricavi) > tol or non_letti <= tol
            or abs((sp13 - stampato) - non_letti) > tol):
        return bs
    new_bs = dict(bs)
    new_bs['sp13'] = stampato
    new_bs['totale_passivo'] = tp - sp13 + stampato
    new_bs['_ce_massa_non_letta'] = sp13 - stampato
    new_bs['_totale_costi_stampato'] = tot_costi
    new_bs['_costi_letti'] = costi
    logger.warning(
        f"Route C: risultato stampato {stampato:,.2f} chiude lo SP; il CE manca di "
        f"{sp13 - stampato:,.2f} di massa non letta (totali stampati costi {tot_costi:,.2f} / "
        f"ricavi {tot_ricavi:,.2f}) — da inserire in Rettifiche")
    return new_bs
