"""Bilancio di verifica per segno (OCR RapidOCR).

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import os
import re
from collections import defaultdict
from decimal import Decimal
from functools import lru_cache
from typing import Dict, List, Optional, Tuple
from importers.rimanenze_ce import e_conto_rimanenze
from importers.situazione_contabile.regole import (
    _CE_SUBFIELD_PARENT, _ce09_dal_dettaglio, _classify_ce_costi, _classify_ce_ricavi, _figli_puntati,
    _natura_unanime, _rimanenze_dal_dettaglio,
)
from importers.situazione_contabile.best_effort import (
    _be_cluster_physical_rows,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.situazione_contabile_parser")


# ===========================================================================
# Dedicated parser: "Bilancio di verifica a sezioni contrapposte PER SEGNO"
# ===========================================================================
# A specific, recognisable trial-balance layout (Zucchetti/DEPI "Bilancio di
# verifica") where accounts are placed in the Attività / Passività columns by the
# SIGN of their balance, NOT by their accounting nature — so the SAME account can
# appear on BOTH sides (e.g. "19 DISPONIBILITA' LIQUIDE" sits in Attività as the
# positive bank balance AND in Passività as the overdraft). The generic best-effort
# and the CoGe-LLM extractors both mis-handle this: they lump the asset column into a
# single crediti bucket, double-count cash, and miss the debt breakdown. This parser
# reads the two columns by COORDINATE, classifies each 2-digit MASTRO by description
# (side-aware), nets fondi ammortamento off the gross immobilizzazioni, splits the
# result account (portati a nuovo vs prior result) into PN, and derives the current
# result from the CE — yielding a fully-balanced IV-CEE statement (plug 0).
# Markers: "BILANCIO DI VERIFICA" + "STATO PATRIMONIALE" + "Eccedenza (Perdita)" /
# "Totale a quadratura", two physical Attività/Passività columns.

_VSEG_CODE_RE = re.compile(r'^\d{2}(?:\.\d{2})?$')

@lru_cache(maxsize=4)
def _vseg_rapidocr_pages_cached(
    file_path: str, size: int, mtime_ns: int
) -> Optional[Tuple[dict, ...]]:
    """Return 300-DPI OCR words while preserving their source coordinates.

    ``size`` and ``mtime_ns`` are cache-key provenance only: a replaced scan at
    the same path is never served stale OCR.  RapidOCR is deliberately optional;
    deployments without it keep the existing Anthropic scan fallback.
    """
    del size, mtime_ns
    try:
        from rapidocr_onnxruntime import RapidOCR
    except (ImportError, ModuleNotFoundError):
        return None

    engine = RapidOCR()
    pages: List[dict] = []
    try:
        with fitz.open(file_path) as doc:
            for page_number, page in enumerate(doc, 1):
                pix = page.get_pixmap(dpi=300, colorspace=fitz.csGRAY, alpha=False)
                result, _elapsed = engine(pix.tobytes("png"))
                words = []
                texts = []
                for word_number, item in enumerate(result or []):
                    if len(item) < 3:
                        continue
                    polygon, text, confidence = item
                    text = str(text or "").strip()
                    if not text or float(confidence) < 0.45:
                        continue
                    x0 = min(float(point[0]) for point in polygon)
                    y0 = min(float(point[1]) for point in polygon)
                    x1 = max(float(point[0]) for point in polygon)
                    y1 = max(float(point[1]) for point in polygon)
                    # PyMuPDF-compatible projection: all coordinate parsers use
                    # only x0/y0/x1/y1/text; the trailing indexes retain order.
                    words.append((x0, y0, x1, y1, text, 0, word_number, 0))
                    texts.append(text)
                pages.append({
                    "page": page_number,
                    "width": float(pix.width),
                    "height": float(pix.height),
                    "words": tuple(words),
                    "text": "\n".join(texts),
                })
    except Exception as exc:
        logger.warning(
            "RapidOCR verifica-segno failed (%s: %s)", type(exc).__name__, exc
        )
        return None
    return tuple(pages)

def _vseg_rapidocr_pages(file_path: str) -> Optional[Tuple[dict, ...]]:
    """Cached coordinate OCR for image-only verifica-segno statements."""
    try:
        stat = os.stat(file_path)
    except OSError:
        return None
    return _vseg_rapidocr_pages_cached(
        os.path.abspath(file_path), stat.st_size, stat.st_mtime_ns
    )

def ocr_bilancio_verifica_segno_sample_text(file_path: str) -> str:
    """Return local OCR routing text only for the supported by-sign layout.

    The same cached OCR pages are later consumed by the deterministic parser, so
    the scan is rendered once and no temporary files are needed.
    """
    pages = _vseg_rapidocr_pages(file_path)
    if not pages:
        return ""
    text = "\n".join(page["text"] for page in pages)
    return text if is_bilancio_verifica_segno(text) else ""

def _vseg_num(tok: str) -> Optional[Decimal]:
    """Parse one Italian amount token; parentheses or trailing '-' = negative."""
    tok = tok.strip()
    if not tok:
        return None
    neg = False
    if tok.startswith('(') and tok.endswith(')'):
        neg = True
        tok = tok[1:-1].strip()
    if tok.endswith('-'):
        neg = True
        tok = tok[:-1].strip()
    if tok.startswith('-'):
        neg = True
        tok = tok[1:].strip()
    t = tok.replace('.', '').replace(',', '.')
    if not re.fullmatch(r'\d+(?:\.\d+)?', t):
        return None
    v = Decimal(t)
    return -v if neg else v

def _vseg_up(s: str) -> str:
    return s.upper().replace("'", " ").replace("`", " ")

def is_bilancio_verifica_segno(text: str) -> bool:
    """Detect the 'Bilancio di verifica a sezioni contrapposte per segno' layout."""
    nos = re.sub(r"\s+", "", text).upper()
    if "STATOPATRIMONIALE" not in nos:
        return False
    if "BILANCIODIVERIFICA" not in nos and "BILANCINODIVERIFICA" not in nos:
        return False
    # the by-sign layout always prints a balancing residual line + a quadratura total
    return ("ECCEDENZA" in nos or "TOTALEAQUADRATURA" in nos
            or "TOTALEAPAREGGIO" in nos)

def _vseg_split_rows(page, details: Optional[list] = None) -> Tuple[list, list]:
    """Split a 2-column page into (left_rows, right_rows). Each row is
    (code, desc_upper, amount). Columns split at the gutter between the two
    'Conto'/'Codice' header words (fallback: 290pt). With ``details`` the level-3
    rows (_VSEG_DETAIL_CODE_RE) are appended there as (side, code, desc, amount),
    the same channel as _vseg_split_ocr_rows."""
    words = page.get_text('words')  # (x0,y0,x1,y1,word,block,line,wordno)
    headers = sorted([w for w in words if w[4] in ('Conto', 'Codice')],
                     key=lambda w: w[0])
    gutter = headers[1][0] - 10 if len(headers) >= 2 else page.rect.width * 0.49
    lines: Dict[int, list] = defaultdict(list)
    for w in words:
        lines[round(w[1])].append(w)
    left, right = [], []
    for y in sorted(lines):
        row = lines[y]
        for side_words, out in (
            (sorted([w for w in row if w[0] < gutter], key=lambda w: w[0]), left),
            (sorted([w for w in row if w[0] >= gutter], key=lambda w: w[0]), right),
        ):
            if len(side_words) < 2:
                continue
            code = side_words[0][4]
            dettaglio = (details is not None and not _VSEG_CODE_RE.match(code)
                         and _VSEG_DETAIL_CODE_RE.match(code))
            if not (_VSEG_CODE_RE.match(code) or dettaglio):
                continue
            amt = _vseg_num(side_words[-1][4])
            if amt is None:
                continue
            desc = ' '.join(w[4] for w in side_words[1:-1])
            if dettaglio:
                if desc and not _VSEG_PARTITARIO_RE.match(desc):
                    details.append(('left' if out is left else 'right', code,
                                    _vseg_up(desc), amt))
                continue
            out.append((code, _vseg_up(desc), amt))
    return left, right

def _vseg_ocr_sections(page: dict) -> List[Tuple[str, float, float]]:
    """Find SP/CE y-regions on one coordinate-OCR page.

    A physical page may contain the tail of Stato Patrimoniale and the beginning
    of Conto Economico.  Page-level routing would classify both tables twice;
    section-header coordinates keep the two regions disjoint.
    """
    words = page["words"]
    height = page["height"]

    def _compact(word) -> str:
        return re.sub(r"\W+", "", _vseg_up(word[4]))

    sp_headers = [
        (word[1] + word[3]) / 2
        for word in words
        if "STATOPATRIMONIALE" in _compact(word)
    ]
    ce_headers = [
        (word[1] + word[3]) / 2
        for word in words
        if "CONTOECONOMICO" in _compact(word)
    ]
    # OCR occasionally fuses or drops a section title; the paired column
    # captions still identify the table without using any accounting amount.
    if not sp_headers:
        att = [(word[1] + word[3]) / 2 for word in words
               if _compact(word).startswith("ATTIVIT")]
        pas = [(word[1] + word[3]) / 2 for word in words
               if _compact(word).startswith("PASSIVIT")]
        if att and pas:
            sp_headers = [min(min(att), min(pas))]
    if not ce_headers:
        costs = [(word[1] + word[3]) / 2 for word in words
                 if _compact(word) == "COSTI"]
        revenues = [(word[1] + word[3]) / 2 for word in words
                    if _compact(word) == "RICAVI"]
        if costs and revenues:
            ce_headers = [min(min(costs), min(revenues))]

    starts = [(min(sp_headers), "sp") for _ in [0] if sp_headers]
    starts += [(min(ce_headers), "ce") for _ in [0] if ce_headers]
    starts.sort()
    return [
        (section, start, starts[index + 1][0] if index + 1 < len(starts) else height)
        for index, (start, section) in enumerate(starts)
    ]

# Level-3+ account codes (31.03.01). They are DETAIL under a level-2 sub-account and
# must never reach _vseg_classify_sp, which sums mastri: booking them too would double
# count (the fondi ammortamento tree 41 > 41.01 > 41.01.25 is the obvious victim). They
# are captured on a separate channel, used only where the mastro alone cannot answer.
_VSEG_DETAIL_CODE_RE = re.compile(r'^\d{2}(?:\.\d{2,3}){2,}$')

# A "partitario" row repeats its parent's code and re-lists part of its amount under a
# counterparty ("1 BANCO BPM SPA"). Summing it with the parent double counts.
_VSEG_PARTITARIO_RE = re.compile(r'^\d+\s')

def _vseg_financing_split(details: list, total: Decimal) -> Optional[Dict[str, Decimal]]:
    """Split a financing mastro into entro/oltre from its level-3 detail rows.

    A bilancio di verifica prints no "esigibili entro/oltre" column, so the house rule
    is "no marker -> all short". On this layout the maturity IS printed, one level
    below the mastro ("Banca c/anticipazioni" vs "Finanz. a medio/lungo termine"), so
    reading it is reading the document, not inventing a split.

    RapidOCR drops the decimal comma on some rows (243.073,49 arrives as 24307349).
    Italian amounts always carry two decimals, so an integer-valued row is a repair
    candidate — but the repair is accepted ONLY when the rows then sum to the printed
    mastro total, i.e. when the source confirms itself. Returns None on any doubt (no
    details, an unrecognised caption, no reconciliation): the caller then keeps the
    aggregate exactly as classified, which is the current behaviour.
    """
    if not details:
        return None
    typed = []
    for _code, description, amount in details:
        field = _vseg_debt_field(description)
        if field is None:
            return None  # partial knowledge must not produce a partial split
        typed.append((field, amount))

    for repair in (False, True):
        out: Dict[str, Decimal] = defaultdict(Decimal)
        running = Decimal('0')
        for field, amount in typed:
            value = amount
            if repair and value == value.to_integral_value():
                value = value / 100
            out[field] += value
            running += value
        if abs(running - total) <= Decimal('0.02'):
            return dict(out)
    return None

def _vseg_is_financing(u: str) -> bool:
    """A mastro holding bank financing / mortgages ("FINANZIAMENTI DI TERZI")."""
    return 'FINANZIAMENT' in u or 'MUTU' in u

def _vseg_ha_prova_lungo(u: str) -> bool:
    return ('MEDIO/LUNGO' in u or 'MEDIO LUNGO' in u or 'M/L' in u
            or 'LUNGO TERMINE' in u or 'OLTRE' in u)

def _vseg_debt_field(u: str) -> Optional[str]:
    """IV-CEE field for a financing DETAIL caption, or None when unrecognised.

    Deliberately narrow: an unknown caption must fail the whole split rather than be
    guessed into a bucket."""
    if 'SOCIO' in u or 'SOCI ' in u or u.startswith('SOCI'):
        # A shareholder account inside the financing mastro is a soci loan: D.5, not a
        # bank. Keyed on SOCIO alone and NOT on 'FINANZ', which the OCR mangles
        # ("C/FINANZIAMEN" -> "C/FINANANZIAMEN"); the caller has already scoped these
        # rows to the financing mastro, so the word carries the meaning on its own.
        # Senza scadenza stampata e' breve (owner, 2026-11-09): sp17b solo con una prova.
        if _vseg_ha_prova_lungo(u):
            return 'sp17b_debiti_altri_finanz_lungo'
        return 'sp16b_debiti_altri_finanz_breve'
    if 'ANTICIPAZ' in u:
        return 'sp16a_debiti_banche_breve'          # advances revolve within the year
    if _vseg_ha_prova_lungo(u):
        return 'sp17a_debiti_banche_lungo'
    if 'MUTU' in u:
        # La parola MUTUO da sola non e' una scadenza (owner, 2026-11-09): senza
        # MEDIO/LUNGO, M/L o OLTRE stampati il debito va a breve.
        return 'sp16a_debiti_banche_breve'
    return None

def _vseg_split_ocr_rows(
    page: dict, y0: float, y1: float
) -> Tuple[list, list, list, list]:
    """Split coordinate OCR into left/right account rows, source controls and the
    level-3 detail rows (see _VSEG_DETAIL_CODE_RE)."""
    words = [
        word for word in page["words"]
        if y0 <= (word[1] + word[3]) / 2 < y1
    ]
    # The scan is a symmetric two-half table.  The right ``Conto`` header begins
    # *after* its narrow code column, while the first right-side account code can
    # straddle the exact centre.  Reusing the text-PDF ``header.x - 10`` heuristic
    # therefore puts that code on the left and merges two physical rows.  The
    # rendered page midpoint is the actual printed gutter and is rotation-safe.
    gutter = page["width"] / 2
    left: list = []
    right: list = []
    controls: list = []
    details: list = []

    for side, lo, hi, out in (
        ("left", -1e9, gutter, left),
        ("right", gutter, 1e9, right),
    ):
        for physical_row in _be_cluster_physical_rows(words, lo, hi):
            row = sorted(physical_row, key=lambda word: word[0])
            tokens = [word[4].strip() for word in row if word[4].strip()]
            if len(tokens) < 2:
                continue
            amount_index = None
            amount = None
            amount_prefix = ""

            # RapidOCR commonly returns ``caption 1.234,56`` as one detection
            # box.  Prefer a trailing cents-formatted amount embedded in a token
            # before considering bare integer tokens: a narrow code belonging to
            # the opposite half can otherwise be mistaken for this row's amount.
            fused_amount_re = re.compile(
                r"(?P<amount>\(?-?\d{1,3}(?:\.\d{3})*,\d{2}\)?-?)\s*$"
            )
            for index in range(len(tokens) - 1, 0, -1):
                match = fused_amount_re.search(tokens[index])
                if not match:
                    continue
                parsed = _vseg_num(match.group("amount"))
                if parsed is None:
                    continue
                amount_index = index
                amount = parsed
                amount_prefix = tokens[index][:match.start()].strip()
                break

            # Text PDFs and some OCR rows keep the amount in its own token.
            for index in range(len(tokens) - 1, 0, -1):
                if amount_index is not None:
                    break
                amount = _vseg_num(tokens[index])
                if amount is not None:
                    amount_index = index
                    break
            if amount_index is None or amount is None:
                continue

            caption_tokens = tokens[:amount_index]
            if amount_prefix:
                caption_tokens.append(amount_prefix)
            raw_code = caption_tokens[0].replace(",", ".")
            if _VSEG_CODE_RE.match(raw_code):
                description = " ".join(caption_tokens[1:]).strip()
                if description:
                    out.append((raw_code, _vseg_up(description), amount))
                continue

            # Level-3 detail: kept OUT of `out` (mastri only) on its own channel.
            if _VSEG_DETAIL_CODE_RE.match(raw_code):
                description = " ".join(caption_tokens[1:]).strip()
                if description and not _VSEG_PARTITARIO_RE.match(description):
                    details.append((side, raw_code, _vseg_up(description), amount))
                continue

            # Codeless printed controls never become ledger rows.  They are kept
            # with their physical side and used only for explicit source-backed
            # facts such as the prior-year excess.
            description = _vseg_up(" ".join(caption_tokens).strip())
            if description and any(key in description for key in (
                "TOTALE", "ECCEDENZA", "UTILE", "PERDITA", "QUADRATURA"
            )):
                controls.append((side, description, amount))

    return left, right, controls, details

def _vseg_classify_sp(bs: Dict[str, Decimal], rows: list, side: int) -> None:
    """Accumulate a column's MASTRO rows into bs (short keys + full sub-field names).
    side: 0 = Attività, 1 = Passività. Fondi ammortamento (sub-rows) and the result
    account (25) are handled by the caller via the returned helpers."""
    for code, u, amt in rows:
        mastro = '.' not in code
        if side == 1 and 'FOND' in u and 'SVALUT' in u:
            # The generic mastro 43 and its specific category 43.09 carry the
            # same printed amount.  Ignore the generic parent and net the one
            # category explicitly identified as CREDITI exactly once.
            if 'CREDIT' in u:
                bs['sp06'] -= amt
                bs['sp06a_crediti_clienti_breve'] = (
                    bs.get('sp06a_crediti_clienti_breve', Decimal('0')) - amt
                )
            continue
        if 'FOND' in u and 'AMMORT' in u:        # fondi ammortamento -> netting
            if not mastro:                        # use sub-rows for immat/mat split
                if (code == '41.01' or 'IMMATER' in u
                        or ('IMMOBILIZZ' in u and u.rstrip('.').endswith('IMM'))):
                    # Some OCR engines preserve only the source code 41.01 and
                    # the truncated caption ``IMMOBILIZZAZ.IMM``.
                    bs['sp02'] -= amt
                else:
                    bs['sp03'] -= amt
            continue
        shareholder_current_account = bool(re.search(r'\bC\s*/\s*TO\s+UTILE\b', u))
        if (not shareholder_current_account
                and ('RISULTAT' in u or 'UTILE' in u
                     or 'PERDITE PORTAT' in u or 'PORTATI A NUOVO' in u)):
            # result/retained accounts -> patrimonio netto (sub-rows split the parts)
            if not mastro:
                sign = amt if side == 1 else -amt
                if 'PORTAT' in u:
                    bs['sp12g_utili_perdite_portati'] = bs.get('sp12g_utili_perdite_portati', Decimal('0')) + sign
                else:
                    bs['sp12e_altre_riserve'] = bs.get('sp12e_altre_riserve', Decimal('0')) + sign
                bs['sp12'] += sign
            continue
        if not mastro:
            continue
        if side == 0:  # ATTIVO
            if 'IMMOBILIZZAZIONI IMMATERIAL' in u or ('IMMATERIAL' in u and 'IMMOBIL' in u):
                bs['sp02'] += amt
            elif 'IMMOBILIZZAZIONI MATERIAL' in u or ('MATERIAL' in u and 'IMMOBIL' in u):
                bs['sp03'] += amt
            elif 'IMMOBILIZZAZIONI FINANZIAR' in u:
                bs['sp04'] += amt
            elif 'RIMANENZ' in u or 'MAGAZZIN' in u:
                bs['sp05'] += amt
            elif 'CREDITI COMMERCIAL' in u or 'CLIENT' in u:
                bs['sp06'] += amt
                bs['sp06a_crediti_clienti_breve'] = bs.get('sp06a_crediti_clienti_breve', Decimal('0')) + amt
            elif 'ERARI' in u or 'TRIBUTAR' in u or 'IMPOST' in u:
                bs['sp06'] += amt
                bs['sp06e_crediti_tributari_breve'] = bs.get('sp06e_crediti_tributari_breve', Decimal('0')) + amt
            elif 'DISPONIBILITA' in u or 'LIQUID' in u or 'BANCH' in u or 'CASSA' in u or 'POSTA' in u:
                bs['sp09'] += amt
            elif 'RATEI' in u or 'RISCONT' in u:
                bs['sp10'] += amt
            else:  # crediti vari, enti previdenziali (attivo), altri -> crediti v/altri
                bs['sp06'] += amt
                bs['sp06g_crediti_altri_breve'] = bs.get('sp06g_crediti_altri_breve', Decimal('0')) + amt
        else:  # PASSIVO
            if 'DISPONIBILITA' in u or 'BANCH' in u or 'POSTA' in u:   # overdraft
                bs['sp16'] += amt
                bs['sp16a_debiti_banche_breve'] = bs.get('sp16a_debiti_banche_breve', Decimal('0')) + amt
            elif _vseg_is_financing(u):
                # Bank financing / mortgages. Without this rule the whole mass fell to
                # the `else` and was booked as generic 'altri debiti' with sp17 = 0 —
                # which zeroes the forecast repayment instalment, since that reads
                # sp17a/sp17c (Bilancino 31-5-26 in the corpus). Maturity is printed
                # only on the level-3 rows, so default to short here — the house rule
                # for a verifica with no entro/oltre column — and let the caller refine
                # it from the details when they reconcile to this total.
                bs['sp16'] += amt
                bs['sp16a_debiti_banche_breve'] = bs.get('sp16a_debiti_banche_breve', Decimal('0')) + amt
                bs['_vseg_financing'] = bs.get('_vseg_financing', Decimal('0')) + amt
            elif 'CAPITALE' in u:
                bs['sp11'] += amt
            elif 'FOND' in u and ('RISCHI' in u or 'ONERI' in u):
                bs['sp14'] += amt
            elif 'TFR' in u or 'FINE RAPPORTO' in u:
                bs['sp15'] += amt
            elif 'DEBITI COMMERCIAL' in u or 'FORNITOR' in u:
                bs['sp16'] += amt
                bs['sp16d_debiti_fornitori_breve'] = bs.get('sp16d_debiti_fornitori_breve', Decimal('0')) + amt
            elif 'ERARI' in u or 'TRIBUTAR' in u:
                bs['sp16'] += amt
                bs['sp16e_debiti_tributari_breve'] = bs.get('sp16e_debiti_tributari_breve', Decimal('0')) + amt
            elif 'PREVIDENZ' in u or 'INPS' in u or 'INAIL' in u:
                bs['sp16'] += amt
                bs['sp16f_debiti_previdenza_breve'] = bs.get('sp16f_debiti_previdenza_breve', Decimal('0')) + amt
            elif 'RATEI' in u or 'RISCONT' in u:
                bs['sp18'] += amt
            elif 'RISERV' in u:
                bs['sp12'] += amt
                bs['sp12e_altre_riserve'] = bs.get('sp12e_altre_riserve', Decimal('0')) + amt
            else:  # altri debiti, acconti, ...
                bs['sp16'] += amt
                bs['sp16g_altri_debiti_breve'] = bs.get('sp16g_altri_debiti_breve', Decimal('0')) + amt

# Ordered by specificity; FIRST match wins. ce14 keyed on FINANZIAR only (NOT generic
# PROVENTI, which also occurs in "ALTRI RICAVI E PROVENTI" → ce04).
_VSEG_CE_RICAVI = [
    (['VENDIT'], 'ce01'), (['RICAVI DELLE'], 'ce01'), (['RICAVI DA PREST'], 'ce01'),
    (['INCREMENTI'], 'ce03a'),
    (['FINANZIAR'], 'ce14'),
]

# "ACQUISTI DI SERVIZI" contains both ACQUIST and SERVIZ → ce05 must require BENI/PRODUZ
# so it stays goods-only and SERVIZ wins for services.
_VSEG_CE_COSTI = [
    (['MATERIE'], 'ce05'), (['MERCI'], 'ce05'),
    (['ACQUIST', 'BENI'], 'ce05'), (['ACQUIST', 'PRODUZ'], 'ce05'),
    (['GODIMENTO'], 'ce07'), (['LEASING'], 'ce07'), (['AFFITT'], 'ce07'),
    (['PERSONALE'], 'ce08'), (['SALAR'], 'ce08'), (['STIPEND'], 'ce08'),
    (['AMMORTAMENT'], 'ce09'), (['SVALUTAZ'], 'ce09'),
    (['ACCANTONAMENT'], 'ce11'),
    (['ONERI FINANZIAR'], 'ce15'), (['INTERESS'], 'ce15'),
    (['IMPOST'], 'ce20'),
    (['SERVIZ'], 'ce06'), (['PRESTAZION'], 'ce06'), (['SPESE'], 'ce06'),
    (['GESTIONE', 'VEICOLI'], 'ce06'),
    (['ONERI'], 'ce12'),
]

def _vseg_classify_ce(ce: Dict[str, Decimal], rows: list, side: int,
                      details: list = (), opposite: list = ()) -> None:
    """side: 0 = Costi, 1 = Ricavi. MASTRO rows only; the level-2/3 rows (``details``,
    as (side, code, desc, amount)) are read only to split an inventory mastro."""
    table = _VSEG_CE_RICAVI if side == 1 else _VSEG_CE_COSTI
    default = 'ce04' if side == 1 else 'ce12'
    lato = 'right' if side == 1 else 'left'
    figli = _figli_puntati(list(rows) + [(c, d, a) for sd, c, d, a in details if sd == lato])
    ripiego = _natura_unanime([d for _c, d, _a in opposite]
                              + [d for sd, _c, d, _a in details if sd != lato])
    for code, u, amt in rows:
        if '.' in code:
            continue
        if e_conto_rimanenze(u):
            # Rimanenze iniziali fra i costi, finali fra i ricavi: mai il secchio di
            # ripiego (oneri diversi / altri ricavi), che quadra e gonfia valore e costi
            # della produzione. La natura la dicono i conti sotto il mastro.
            classify = _classify_ce_ricavi if side == 1 else _classify_ce_costi
            tag = 'ce10_close' if side == 1 else 'ce10'
            for t, a in _rimanenze_dal_dettaglio(tag, code, u, amt, figli, classify, ripiego):
                if t == 'ce10_close':
                    t, a = 'ce10', -a
                elif t == 'ce02_open':
                    t, a = 'ce02', -a
                ce[t] = ce.get(t, Decimal('0')) + a
            continue
        field = default
        for kws, f in table:
            if all(kw in u for kw in kws):
                field = f
                break
        if field == 'ce09':
            for t, a in _ce09_dal_dettaglio(code, u, amt, figli):
                ce['ce09'] = ce.get('ce09', Decimal('0')) + a
                if t != 'ce09':
                    detail = _CE_SUBFIELD_PARENT[t][0]
                    ce[detail] = ce.get(detail, Decimal('0')) + a
            continue
        ce[field] = ce.get(field, Decimal('0')) + amt

_VSEG_RICAVI_KEYS = ('ce01', 'ce02', 'ce03', 'ce03a', 'ce04', 'ce13', 'ce14', 'ce18')

_VSEG_COSTI_KEYS = ('ce05', 'ce06', 'ce07', 'ce08', 'ce09', 'ce10', 'ce11', 'ce12', 'ce15', 'ce19', 'ce20')

def parse_bilancio_verifica_segno(
    file_path: str, ocr_pages: Optional[Tuple[dict, ...]] = None
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Parse the by-sign contrapposte bilancio di verifica. Returns (bs, ce) with
    short aggregate keys (sp02..sp18, ce01..ce20) plus full-name sub-fields, and
    `_plug_residual` = |attivo - passivo|. Raises ValueError if the layout does not
    yield a balanced sheet (so the caller can fall back)."""
    bs: Dict[str, Decimal] = defaultdict(Decimal)
    ce: Dict[str, Decimal] = defaultdict(Decimal)
    controls: list = []
    sp_details: list = []
    sp_fin_codes: set = set()
    found_sp = False

    if ocr_pages:
        for page in ocr_pages:
            for section, y0, y1 in _vseg_ocr_sections(page):
                left, right, region_controls, region_details = _vseg_split_ocr_rows(
                    page, y0, y1)
                controls.extend(
                    (section, side, description, amount)
                    for side, description, amount in region_controls
                )
                if section == 'sp':
                    found_sp = True
                    _vseg_classify_sp(bs, left, 0)
                    _vseg_classify_sp(bs, right, 1)
                    sp_fin_codes.update(
                        code for code, description, _amount in right
                        if '.' not in code and _vseg_is_financing(description)
                    )
                    sp_details.extend(
                        (code, description, amount)
                        for side, code, description, amount in region_details
                        if side == 'right'
                    )
                elif section == 'ce':
                    _vseg_classify_ce(ce, left, 0, region_details, right)
                    _vseg_classify_ce(ce, right, 1, region_details, left)
    else:
        doc = fitz.open(file_path)
        try:
            sp_pages, ce_pages = [], []
            for i in range(doc.page_count):
                up = doc[i].get_text().upper()
                if 'STATO PATRIMONIALE' in up:
                    sp_pages.append(i)
                if 'CONTO ECONOMICO' in up:
                    ce_pages.append(i)
            found_sp = bool(sp_pages)
            for page_number in sp_pages:
                left, right = _vseg_split_rows(doc[page_number])
                _vseg_classify_sp(bs, left, 0)
                _vseg_classify_sp(bs, right, 1)
            for page_number in ce_pages:
                ce_details: list = []
                left, right = _vseg_split_rows(doc[page_number], ce_details)
                _vseg_classify_ce(ce, left, 0, ce_details, right)
                _vseg_classify_ce(ce, right, 1, ce_details, left)
        finally:
            doc.close()

    if not found_sp:
        raise ValueError("verifica-segno: no Stato Patrimoniale page")

    # This codeless source row sits outside the account hierarchy and is included
    # in printed passività.  It is prior-year retained profit, not the current
    # result (which is independently derived from CE below).
    prior_excesses = [
        (-amount if 'PERDIT' in description else amount)
        for section, side, description, amount in controls
        if section == 'sp' and side == 'right'
        and 'ECCEDENZA' in description and 'PRECEDENT' in description
    ]
    if prior_excesses:
        prior_excess = prior_excesses[-1]
        bs['sp12'] += prior_excess
        bs['sp12g_utili_perdite_portati'] += prior_excess

    # Refine the financing mastro's entro/oltre from its level-3 rows. _vseg_classify_sp
    # booked the whole mass short (sp16/sp16a); move only what the detail rows prove is
    # long. Balance-invariant: sp16 loses exactly what sp17 gains. A source that does
    # not reconcile to its own printed mastro leaves the short default untouched.
    financing = bs.pop('_vseg_financing', Decimal('0'))
    if financing > 0 and sp_fin_codes:
        # Select the details by CODE PREFIX, never by caption: filtering on "captions we
        # recognise" would silently drop the unrecognised ones and defeat both the
        # reconciliation gate and the refusal on an unknown account.
        split = _vseg_financing_split(
            [row for row in sp_details
             if row[0].split('.')[0] in sp_fin_codes],
            financing,
        )
        if split:
            for field, amount in split.items():
                if field.startswith('sp17'):
                    bs['sp16'] -= amount
                    bs['sp16a_debiti_banche_breve'] -= amount
                    bs['sp17'] += amount
                    bs[field] += amount
                elif field != 'sp16a_debiti_banche_breve':
                    # breve ma non banca (soci senza scadenza): sp16 non cambia
                    bs['sp16a_debiti_banche_breve'] -= amount
                    bs[field] = bs.get(field, Decimal('0')) + amount

    ricavi = sum(ce.get(k, Decimal('0')) for k in _VSEG_RICAVI_KEYS)
    costi = sum(ce.get(k, Decimal('0')) for k in _VSEG_COSTI_KEYS)
    bs['sp13'] = ricavi - costi  # current-period result (= Eccedenza/Perdita)

    att = sum(bs.get(k, Decimal('0')) for k in ('sp01', 'sp02', 'sp03', 'sp04', 'sp05', 'sp06', 'sp07', 'sp08', 'sp09', 'sp10'))
    pas = sum(bs.get(k, Decimal('0')) for k in ('sp11', 'sp12', 'sp13', 'sp14', 'sp15', 'sp16', 'sp17', 'sp18'))
    plug = abs(att - pas)
    tol = max(Decimal('1'), att.copy_abs() * Decimal('0.005'))
    if att <= 0 or plug > tol:
        raise ValueError(
            f"verifica-segno: did not balance (attivo={att}, passivo={pas}, diff={plug})")

    bs['totale_attivo'] = att
    bs['totale_passivo'] = att
    bs['_plug_residual'] = plug
    # This sheet is deterministic, exact and already balanced (plug 0) with sp13 derived
    # from the CE. Signal pdf_importer to SKIP the LLM-oriented declared-result reconcile:
    # this layout books the PRIOR year's result in an equity account ("RISULTATO
    # D'ESERCIZIO"), which _declared_control_totals would mistake for the period result
    # and use to overwrite sp13 and inflate cash.
    bs['_skip_declared_reconcile'] = True
    logger.info(
        f"verifica-segno parsed ({'RapidOCR' if ocr_pages else 'text'}): "
        f"attivo={att}, passivo={pas}, sp13={bs['sp13']}, "
        f"clienti={bs.get('sp06a_crediti_clienti_breve')}, liquidità={bs.get('sp09')}, "
        f"debiti={bs.get('sp16')}")
    return dict(bs), dict(ce)
