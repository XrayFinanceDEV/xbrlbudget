"""Sezioni contrapposte generiche: ricostruzione delle righe e riclassificazione dei mastri.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple
from importers.situazione_contabile.comune import (
    _parse_amount,
)
from importers.situazione_contabile.regole import (
    _CE09_SOTTO, _albero_da_dettagliare, _ce09_dal_dettaglio, _rimanenze_dal_dettaglio,
)


# ---------------------------------------------------------------------------
# Generic best-effort "sezioni contrapposte" parser
# Handles 2-physical-column ERP dumps (Attivo|Passivo, Costi|Ricavi) with
# heterogeneous account-code schemes (02.01.01.02.902, 101 / 101.00001,
# 101001 + 1.01, "3 / 5 / 1", XX/YY/ZZZ). Splits columns at the right-code
# cluster start, sums LEAF accounts only (a code that is the prefix of a more
# detailed code on the same side is a subtotal and is skipped), classifies by
# description, and reconciles the residual to the declared totals into sp09 with
# an explicit "NON QUADRATO" warning so the user can refine via Rettifiche.
# ---------------------------------------------------------------------------

_BE_AMT_RE = re.compile(r'^-?\d{1,3}(?:\.\d{3})*,\d{2}-?$')
# A monetary value in a damaged ToUnicode layer is often split into several PDF
# words (``3.239`` / ``,`` / ``12``) and some separator / zero glyphs are exposed
# as letters (``42.100,DO``).  Keep this deliberately narrow: it is used only for
# the right-aligned numeric suffix of a physical row, never for free text.
_BE_NUMERIC_FRAGMENT_RE = re.compile(r'^[\d.,+\-#rRlLoOdDqQbB()]+$')

def _be_is_numeric_fragment(token: str) -> bool:
    """True for a monetary suffix fragment, excluding words such as ``BOLLO``."""
    if not _BE_NUMERIC_FRAGMENT_RE.fullmatch(token):
        return False
    letters = ''.join(ch for ch in token if ch.isalpha())
    return len(letters) <= 2

@dataclass(frozen=True)
class ReconstructedRow:
    """One physical trial-balance row reconstructed from PDF coordinates.

    ``raw_*`` and geometry are retained so a repaired amount never loses its
    provenance.  The legacy best-effort pipeline still consumes the public
    ``(code, description, amount)`` projection, while tests / diagnostics can
    inspect these facts through :func:`reconstruct_contrapposte_rows`.
    """

    code: str
    description: str
    amount: Decimal
    raw_code: str
    raw_description: str
    raw_amount: str
    normalized_amount: str
    page: int
    y: float
    bbox: Tuple[float, float, float, float]
    confidence: str = "exact"
    control: bool = False

    def legacy(self) -> Tuple[str, str, Decimal]:
        return self.code, self.description, self.amount

_ZERO_PADDED_CODE = re.compile(r'^\d+(?:\.\d+){2,}$')

def _be_trim_zero_segments(code: str) -> str:
    """Un piano dei conti a segmenti di larghezza fissa scrive il mastro e il conto
    riempiendo di zeri i segmenti che non hanno ("102.00.00000" mastro, "102.01.00000"
    conto, "102.01.00004" sottoconto: M.C.T. 30/06/2026). Ridotti alle sole cifre i tre
    livelli non sono uno il prefisso dell'altro e si sommano tutti: tolti i segmenti di
    zeri in coda lo diventano ("102", "10201", "1020100004"), e il riclassificatore
    sceglie un livello solo. Solo codici di almeno tre segmenti con l'ultimo di almeno
    quattro cifre: i "NN.NN.NN" dei quattro sezioni restano come sono."""
    code = code.strip()
    if not _ZERO_PADDED_CODE.match(code) or len(code.rsplit('.', 1)[1]) < 4:
        return code
    parts = code.split('.')
    while len(parts) > 1 and not parts[-1].strip('0'):
        parts.pop()
    return '.'.join(parts)

def _be_norm(code: str) -> str:
    """Normalise a (possibly multi-token) account code to a digit string."""
    return re.sub(r'\D', '', _be_trim_zero_segments(code))

def _be_split(words) -> Optional[float]:
    """Find the column gutter separating two physical (code, amount) columns.

    Account codes form two x clusters; the gutter is the gap between them. But
    repeating page headers/footers (protocol numbers, dates) add spurious code-like
    tokens on the far right that can create a WIDER gap than the real one — picking
    the widest code-gap blindly then bisects the right column between its codes and
    its amounts, merging the two data columns (booking costs as negative revenue).

    So we don't trust the widest gap: we VALIDATE each candidate gutter operationally
    by running the same row reconstruction (`_be_collect_side`) on both sides and
    keeping only gutters that yield real (code+amount) rows on BOTH sides — then take
    the widest of those. Single-column / costs-only pages yield rows on one side only,
    so no candidate validates and we return None (caller falls back to a centre split).
    """
    xs = sorted((w[0] + w[2]) / 2 for w in words
                if re.match(r'^\d', w[4]) and not _BE_AMT_RE.match(w[4]))
    if len(xs) < 6:
        return None
    # Page-content centre, robust to far-right header/footer outliers (5°/95° percentile).
    allx = sorted((w[0] + w[2]) / 2 for w in words if w[4].strip())
    if allx:
        lo_p = allx[max(0, int(0.05 * len(allx)))]
        hi_p = allx[min(len(allx) - 1, int(0.95 * len(allx)))]
        centre = (lo_p + hi_p) / 2
    else:
        centre = None
    # Candidate gutters: gaps between adjacent code-x centres with a real cluster on
    # each side.
    candidates = []
    for i in range(len(xs) - 1):
        gap = xs[i + 1] - xs[i]
        if gap >= 25 and (i + 1) >= 3 and (len(xs) - i - 1) >= 3:
            candidates.append(xs[i + 1] - 1.0)
    # Score each VALIDATED candidate. The correct gutter splits into two genuine data
    # columns with DESCRIPTION-bearing rows on BOTH sides; the header/footer-polluted (or
    # code-vs-amount) gutter is wider but leaves one side with orphan amounts and no
    # descriptions. So we DON'T pick the widest: we pick the candidate that maximises the
    # balance of description-bearing rows across the two sides, breaking ties by proximity
    # to the page centre (the real Attivo|Passivo gutter sits near the middle).
    scored = []
    for split in candidates:
        left = _be_collect_side(words, -1e9, split)
        right = _be_collect_side(words, split, 1e9)
        ld = sum(1 for _c, d, _a in left if d.strip())
        rd = sum(1 for _c, d, _a in right if d.strip())
        if len(left) >= 2 and len(right) >= 2 and ld >= 2 and rd >= 2:
            balance = min(ld, rd)
            dist = abs(split - centre) if centre is not None else 0.0
            scored.append((balance, -dist, split))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][2]

def _be_cluster_physical_rows(words, lo: float, hi: float) -> List[list]:
    """Cluster words into physical rows using vertical overlap / baseline distance.

    The old ``round(y / 2)`` bucket split a single printed row whenever the PDF
    producer emitted code, caption, comma and cents with 1--3 pt baseline jitter.
    Adjacent accounting rows in the local corpus are at least ~9 pt apart, so a
    3.6 pt tolerance plus an overlap check joins fragments without joining rows.
    """
    selected = [w for w in words if lo <= (w[0] + w[2]) / 2 < hi and w[4].strip()]
    selected.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    rows: List[dict] = []
    for word in selected:
        cy = (word[1] + word[3]) / 2
        candidates = []
        # Only the most recent rows can overlap a y-sorted word.
        start = max(0, len(rows) - 4)
        for idx in range(start, len(rows)):
            row = rows[idx]
            overlap = max(0.0, min(word[3], row['y1']) - max(word[1], row['y0']))
            min_height = min(word[3] - word[1], row['y1'] - row['y0'])
            distance = abs(cy - row['cy'])
            if distance <= 3.6 or (min_height > 0 and overlap >= 0.55 * min_height):
                candidates.append((distance, idx))
        if candidates:
            _distance, idx = min(candidates)
            row = rows[idx]
            row['words'].append(word)
            row['y0'] = min(row['y0'], word[1])
            row['y1'] = max(row['y1'], word[3])
            row['cy'] = sum((w[1] + w[3]) / 2 for w in row['words']) / len(row['words'])
        else:
            rows.append({'words': [word], 'y0': word[1], 'y1': word[3], 'cy': cy})
    return [sorted(row['words'], key=lambda w: w[0]) for row in rows]

def _be_parse_amount_fragments(parts: List[str]) -> Optional[Tuple[Decimal, str, str]]:
    """Parse a right-aligned monetary suffix, returning value/text/confidence.

    Italian amounts always carry two decimal digits.  After proving that every
    suffix token is numeric-context text, punctuation can therefore be rebuilt
    from the digit stream.  Letter-to-digit repairs are restricted to common
    damaged-font zero/eight glyphs and never run on descriptions.
    """
    if not parts:
        return None
    original_parts = [p.strip() for p in parts if p.strip()]
    if not original_parts:
        return None

    compact = ''.join(original_parts)
    canonical = compact.replace(' ', '')
    exact = re.fullmatch(r'-?\d{1,3}(?:\.\d{3})*,\d{2}-?', canonical)
    if exact:
        value = _parse_amount(canonical.rstrip('-'))
        if canonical.endswith('-'):
            value = -value
        return value, canonical, 'exact'

    repaired_parts = list(original_parts)
    # A broken thousands separator can itself be exposed as a one-digit word
    # (``100 | 1 | 680 | r | 34``).  It is safe to discard only in this precise
    # 3+separator+3+separator+2 grouping.
    if (len(repaired_parts) >= 5
            and len(re.sub(r'\D', '', repaired_parts[-5])) in (1, 2, 3)
            and repaired_parts[-4].isdigit() and len(repaired_parts[-4]) == 1
            and repaired_parts[-3].isdigit() and len(repaired_parts[-3]) == 3
            and not re.search(r'\d', repaired_parts[-2])
            and len(re.sub(r'\D', '', repaired_parts[-1])) == 2):
        del repaired_parts[-4]

    numeric = ''.join(repaired_parts).upper().translate(str.maketrans({
        'D': '0', 'O': '0', 'Q': '0', 'B': '8',
    }))
    negative = numeric.startswith('-') or numeric.endswith('-')
    digits = ''.join(ch for ch in numeric if ch.isdigit())
    if len(digits) < 3:
        return None
    normalized = ('-' if negative else '') + digits[:-2] + ',' + digits[-2:]
    try:
        value = Decimal(digits[:-2] + '.' + digits[-2:])
    except InvalidOperation:
        return None
    return (-value if negative else value), normalized, 'repaired'

def _be_normalize_description(description: str) -> str:
    """Conservative caption repairs supported by the numeric/asset context.

    These variants are recurring damaged-font spellings, not document names or
    account codes.  Repairs only make an already recognisable depreciation-fund
    caption canonical; unrelated prose is untouched.
    """
    d = re.sub(r'\s+', ' ', description.upper()).strip()
    if any(k in d for k in ('AMM', 'ANFM', 'AWORT')):
        d = re.sub(r'\b(?:RONDO|FONDA)\b', 'FONDO', d)
        d = re.sub(r'\bRANDI\b', 'FONDI', d)
        d = d.replace('AWORTAMENTO', 'AMMORTAMENTO').replace('ANFM', 'AMM')
        d = re.sub(r'AMM\s*\.\s*TO', 'AMM.TO', d)
    return d

def _be_code_prefix(tokens: List[str]) -> Tuple[List[str], int]:
    """Read a possibly garbled account code from the beginning of a row."""
    code_tokens: List[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if code_tokens and len(_be_normalize_code(''.join(code_tokens))) >= 3:
            break
        if not code_tokens:
            code_like = bool(token and token[0].isdigit())
        else:
            # Separator glyphs may be exposed as one/two letters (``1 nD 2``).
            code_like = len(token) <= 2 or bool(re.fullmatch(r'[\d./*+,#]+', token))
        if not code_like:
            break
        code_tokens.append(token)
        i += 1
    return code_tokens, i

def _be_normalize_code(raw_code: str) -> str:
    raw_code = _be_trim_zero_segments(raw_code)
    mapped = raw_code.upper().translate(str.maketrans({
        'D': '0', 'O': '0', 'Q': '0', 'L': '1', 'A': '0',
    }))
    return re.sub(r'\D', '', mapped)

def _be_repair_parent_codes(facts: List[ReconstructedRow]) -> List[ReconstructedRow]:
    """Recover subtotal hierarchy from adjacent children and printed order.

    A damaged separator can turn ``8.33`` into ``8933``.  We only rewrite it
    when preceding detail rows share a 3-digit prefix and either their exact sum
    equals the subtotal or the subtotal amount itself required glyph repair.  In
    the latter case the bottom-up child sum wins and the raw printed value remains
    available in ``raw_amount`` / ``confidence``.
    """
    out = list(facts)
    for idx, fact in enumerate(out):
        if fact.control or len(fact.code) >= 6 or idx == 0:
            continue
        candidate = None
        for start in range(max(0, idx - 20), idx):
            previous = out[start:idx]
            codes = [r.code for r in previous if len(r.code) >= 3 and not r.control]
            if not codes:
                continue
            common = codes[0]
            for code in codes[1:]:
                while common and not code.startswith(common):
                    common = common[:-1]
            if len(common) < 3:
                continue
            prefix = common[:3]
            # The printed short code must corroborate the group (first section
            # digit + final two digits); this prevents unrelated equal amounts
            # from becoming a hierarchy by coincidence.
            short = fact.code
            if not (short == prefix
                    or (len(short) == 4 and short[0] == prefix[0]
                        and short[-2:] == prefix[-2:])):
                continue
            children = [r for r in previous if r.code.startswith(prefix)]
            child_sum = sum((r.amount for r in children), Decimal('0'))
            if not children:
                continue
            tolerance = max(Decimal('0.02'), abs(fact.amount) * Decimal('0.001'))
            if abs(child_sum - fact.amount) <= tolerance:
                candidate = replace(fact, code=prefix)
            elif fact.confidence in ('repaired', 'derived_from_children'):
                candidate = replace(
                    fact, code=prefix, amount=child_sum,
                    normalized_amount=str(child_sum), confidence='derived_from_children')
            if candidate is not None:
                break
        if candidate is not None:
            out[idx] = candidate
    return out

def _be_collect_side_facts(words, lo: float, hi: float, codeless: bool = False,
                           page: int = 0, include_controls: bool = False
                           ) -> List[ReconstructedRow]:
    """Coordinate reconstruction retaining raw text, geometry and confidence."""
    facts: List[ReconstructedRow] = []
    for row_words in _be_cluster_physical_rows(words, lo, hi):
        token_words = [w for w in row_words if w[4].strip()]
        tokens = [w[4].strip() for w in token_words]
        if not tokens:
            continue
        amount_start = len(tokens)
        while amount_start > 0 and _be_is_numeric_fragment(tokens[amount_start - 1]):
            if amount_start < len(tokens):
                gap = token_words[amount_start][0] - token_words[amount_start - 1][2]
                # A detached page/column marker before a footer amount is not part
                # of that amount (e.g. ``Totale Attivita  1    315.121,19``).
                if gap > 16.0:
                    break
            amount_start -= 1
        if amount_start == len(tokens):
            continue
        parsed = _be_parse_amount_fragments(tokens[amount_start:])
        if parsed is None:
            continue
        amount, normalized_amount, confidence = parsed
        prefix = tokens[:amount_start]
        code_tokens, description_start = _be_code_prefix(prefix)
        raw_code = ' '.join(code_tokens)
        code = _be_normalize_code(raw_code)
        if not code:
            if not codeless:
                continue
            description_start = 0
        raw_description = ' '.join(prefix[description_start:]).strip()
        description = _be_normalize_description(raw_description)
        if len(description) < 3:
            continue
        if (
            re.match(r'^(?:VIA|VIALE|V\.LE|PIAZZA|P\.ZZA|CORSO)\b', description)
            or 'CODICE FISCALE' in description
            or 'PARTITA IVA' in description
            or re.match(r'^(?:C\.F\.|P\.IVA|REA)\b', description)
        ):
            continue
        if any(k in description for k in ('A RIPORT', 'RIPORTO', 'RIPORTARE',
                                          'SEGUE', 'IMPORTI', 'PROGRESSIV')):
            continue
        is_control = ('TOTALE' in description or 'PAREGGIO' in description
                      or re.match(r'^TOTALI\b', description) is not None
                      or ('ESERCIZ' in description
                          and any(k in description for k in ('UTILE', 'PERDIT', 'RISULTAT'))))
        if is_control and not include_controls:
            if codeless and not code:
                break
            continue
        if not code and not codeless:
            continue
        bbox = (min(w[0] for w in row_words), min(w[1] for w in row_words),
                max(w[2] for w in row_words), max(w[3] for w in row_words))
        facts.append(ReconstructedRow(
            code=code, description=description, amount=amount,
            raw_code=raw_code, raw_description=raw_description,
            raw_amount=' '.join(tokens[amount_start:]),
            normalized_amount=normalized_amount, page=page,
            y=sum((w[1] + w[3]) / 2 for w in row_words) / len(row_words),
            bbox=bbox, confidence=confidence, control=is_control,
        ))
    return facts

def _be_page_needs_coordinate_repair(words) -> bool:
    """Detect a damaged/split amount layer without depending on a filename."""
    isolated = sum(1 for w in words if w[4].strip() in {',', '+', '#', 'r'})
    return isolated >= 3

def _be_collect_side_legacy(words, lo: float, hi: float,
                            codeless: bool = False) -> List[Tuple[str, str, Decimal]]:
    """Original strict collector retained for healthy PDF text layers."""
    rows: Dict[int, list] = defaultdict(list)
    for word in words:
        cx = (word[0] + word[2]) / 2
        if lo <= cx < hi:
            rows[round(word[1] / 2.0)].append(word)
    out = []
    for y in sorted(rows):
        toks = [w[4] for w in sorted(rows[y], key=lambda w: w[0])]
        i, code_toks = 0, []
        while (i < len(toks) and re.match(r'^[\d./*]+$', toks[i])
               and not _BE_AMT_RE.match(toks[i])):
            code_toks.append(toks[i])
            i += 1
        if not code_toks:
            if not codeless:
                continue
            code = ''
            rest = toks
        else:
            code = _be_norm(''.join(code_toks))
            if not code:
                continue
            rest = toks[i:]
        amts = [_parse_amount(t) for t in rest if _BE_AMT_RE.match(t)]
        if not amts:
            continue
        desc = ' '.join(t for t in rest if not _BE_AMT_RE.match(t)).upper().strip()
        if (
            re.match(r'^(?:VIA|VIALE|V\.LE|PIAZZA|P\.ZZA|CORSO)\b', desc)
            or 'CODICE FISCALE' in desc
            or 'PARTITA IVA' in desc
            or re.match(r'^(?:C\.F\.|P\.IVA|REA)\b', desc)
        ):
            continue
        if codeless and not code:
            if len(desc) < 3:
                continue
            if any(k in desc for k in ('A RIPORT', 'RIPORTO', 'RIPORTARE',
                                       'SEGUE', 'IMPORTI', 'PROGRESSIV')):
                continue
            if 'TOTALE' in desc or 'PAREGGIO' in desc:
                break
        out.append((code, desc, amts[-1]))
    return out

def _be_collect_side(words, lo: float, hi: float,
                     codeless: bool = False, page: int = 0
                     ) -> List[Tuple[str, str, Decimal]]:
    """Legacy projection of the provenance-preserving coordinate facts."""
    if not _be_page_needs_coordinate_repair(words):
        return _be_collect_side_legacy(words, lo, hi, codeless=codeless)
    facts = _be_repair_parent_codes(_be_collect_side_facts(
        words, lo, hi, codeless=codeless, page=page))
    return [fact.legacy() for fact in facts]

def reconstruct_contrapposte_rows(file_path: str) -> List[ReconstructedRow]:
    """Return all reconstructed row facts for local diagnostics / audit tooling."""
    facts: List[ReconstructedRow] = []
    doc = fitz.open(file_path)
    try:
        for page_number, pdf_page in enumerate(doc, 1):
            words = pdf_page.get_text('words')
            if not words:
                continue
            split = _be_split(words) or pdf_page.rect.width / 2
            facts.extend(_be_collect_side_facts(
                words, -1e9, split, codeless=True, page=page_number,
                include_controls=True))
            facts.extend(_be_collect_side_facts(
                words, split, 1e9, codeless=True, page=page_number,
                include_controls=True))
    finally:
        doc.close()
    return facts

def _be_split_codeless(words) -> Optional[float]:
    """Column gutter for CODE-LESS two-column layouts (description+amount rows).

    With no account codes the gutter is not a code-cluster gap; it sits between the
    LEFT column's amounts and the RIGHT column's descriptions. We scan candidate
    gutters across the central half of the page and keep the one that yields the most
    BALANCED set of well-formed (description+amount) rows on both sides — a wrong split
    leaves one side with descriptions but no amounts (or vice-versa) and scores low.
    """
    xs = [(w[0] + w[2]) / 2 for w in words if w[4].strip()]
    if len(xs) < 6:
        return None
    allx = sorted(xs)
    centre = (allx[int(0.05 * len(allx))] + allx[min(len(allx) - 1, int(0.95 * len(allx)))]) / 2
    lo_x, hi_x = allx[0], allx[-1]
    span = hi_x - lo_x
    if span <= 0:
        return None

    def _score(x):
        left = _be_collect_side(words, -1e9, x, codeless=True)
        right = _be_collect_side(words, x, 1e9, codeless=True)
        ld = sum(1 for _c, d, _a in left if d.strip())
        rd = sum(1 for _c, d, _a in right if d.strip())
        return (min(ld, rd), -abs(x - centre)) if ld >= 2 and rd >= 2 else None

    # Prima i varchi veri: un taglio che non attraversa nessuna parola delle righe con un
    # importo (i titoli centrati, "Dal 01/01/2025 al 31/12/2025", non contano). Fra le
    # colonne di budget_435 il varco e' largo un punto (importo fino a 296, descrizione da
    # 297) e la griglia qui sotto non ci cade mai: con 50 costi contro 3 ricavi vinceva un
    # taglio in mezzo agli importi dei costi, o in mezzo a "Totale" della colonna di destra.
    # Non su una pagina con gli importi a frammenti ("2.280" "," "30"): li' fra un
    # frammento e l'altro c'e' un varco che non e' fra le colonne.
    per_riga: Dict[int, list] = {}
    for w in words:
        if w[4].strip():
            per_riga.setdefault(round(w[3]), []).append(w)
    dati = [w for ws in per_riga.values()
            if any(re.fullmatch(r'\d{1,3}(?:\.\d{3})*,\d{2}-?|\d+,\d{2}-?', x[4]) for x in ws)
            for w in ws]
    lo_g, hi_g = lo_x + 0.25 * span, lo_x + 0.75 * span
    coperti = sorted((w[0], w[2]) for w in dati if w[2] > lo_g and w[0] < hi_g)
    varchi, cursore = [], lo_g
    for a, b in coperti:
        if a > cursore + 0.5:
            varchi.append((cursore + a) / 2)
        cursore = max(cursore, b)
    if hi_g > cursore + 0.5:
        varchi.append((cursore + hi_g) / 2)
    if _be_page_needs_coordinate_repair(words):
        varchi = []
    migliori = [(sc, x) for x in varchi if (sc := _score(x)) is not None]
    if migliori:
        return max(migliori)[1]

    best = None
    step = max(2.0, span / 80.0)
    x = lo_x + 0.25 * span
    end = lo_x + 0.75 * span
    while x <= end:
        left = _be_collect_side(words, -1e9, x, codeless=True)
        right = _be_collect_side(words, x, 1e9, codeless=True)
        ld = sum(1 for _c, d, _a in left if d.strip())
        rd = sum(1 for _c, d, _a in right if d.strip())
        if ld >= 2 and rd >= 2:
            score = (min(ld, rd), -abs(x - centre))
            if best is None or score > best[0]:
                best = (score, x)
        x += step
    return best[1] if best else None

def _be_adotta_orfani(rows: List[Tuple[str, str, Decimal]]) -> List[Tuple[str, str, Decimal]]:
    """Un conto orfano (ne' padre ne' figlio di nessun codice) stampato SOTTO un mastro che i
    suoi figli diretti non spiegano, mentre figli + orfano lo spiegano al centesimo, e' figlio
    di quel mastro (budget_1478: «1201036 Carta prepagata» 112,49 sotto «360 Debiti verso
    banche» 5.128,88 = 5.016,39 + 112,49). Il prefisso del codice non decide la parentela:
    decide il totale stampato. Il codice dell'orfano si riscrive sotto quello del mastro, cosi'
    la gerarchia per prefisso di _be_reclassify lo vede figlio e non lo conta due volte."""
    codici = [c for c, _, _ in rows]

    def discende(o, c):
        return o != c and len(o) > len(c) and o.startswith(c)

    out = list(rows)
    for i, (c, d, a) in enumerate(rows):
        if any(discende(c, o) or discende(o, c) for o in codici):
            continue
        for j in range(i - 1, -1, -1):
            r, _rd, ra = rows[j]
            if any(discende(r, o) for o in codici):
                continue                      # non e' una radice: si risale
            figli = [x for x in rows[j + 1:i] if discende(x[0], r)]
            if not figli:
                break
            diretti = [x for x in figli if not any(discende(x[0], y[0]) for y in figli)]
            somma = sum((x[2] for x in diretti), Decimal(0))
            if abs(somma - ra) > Decimal("0.005") and abs(somma + a - ra) <= Decimal("0.005"):
                out[i] = (r + "~" + c, d, a)
            break
    return out

def _be_reclassify(items: List[Tuple[str, str, Decimal]], classify,
                   ripiego_rimanenze: Optional[str] = None) -> List[Tuple[str, Decimal]]:
    """Reconcile mastri/subtotali to the IV-CEE reclassification.

    Walk the account-code hierarchy (parent = prefix) and emit ONE line at the
    COARSEST level whose DESCRIPTION maps to a specific IV-CEE field; descend
    into children only when a node's description is generic. This uses the named
    subtotals/mastri (IMMOBILIZZAZIONI IMMATERIALI, DEBITI V/FORNITORI, ...) — no
    per-gestionale code mapping — and never double-counts (a classified parent
    stands in for the sum of its children). classify(desc) -> (field, specific).
    Returns [(field, amount)].
    """
    rows, seen = [], set()
    for c, d, a in items:
        if 'TOTALE' in d or 'PAREGGIO' in d:
            continue
        key = (c, d, a)
        if key in seen:
            continue
        seen.add(key)
        rows.append((c, d, a))
    rows = _be_adotta_orfani(rows)

    info = {}
    for c, d, a in rows:
        if c in info:
            # Two DISTINCT accounts whose codes normalise to the same digit string
            # (e.g. both collapse to "5") would otherwise overwrite each other and
            # silently DROP the earlier amount — unbalancing the sheet and inflating the
            # sp09/sp16 plug (budget_343/348/342). Aggregate the amount instead so no mass
            # is lost; keep the first description for classification (same normalised code
            # → same gestionale family → same IV-CEE field). Exact (c,d,a) duplicates were
            # already removed by the `seen` set above, so this only sums genuine distinct rows.
            pd, pa = info[c]
            info[c] = (pd, pa + a)
        else:
            info[c] = (d, a)
    uniq = list(info.keys())

    def direct_children(c):
        desc = [o for o in uniq if o != c and len(o) > len(c) and o.startswith(c)]
        return [x for x in desc
                if not any(y != x and len(y) < len(x) and x.startswith(y) for y in desc)]

    roots = [c for c in uniq
             if not any(o != c and len(c) > len(o) and c.startswith(o) for o in uniq)]

    out: List[Tuple[str, Decimal]] = []

    def figli(c):
        return [(x,) + info[x] for x in direct_children(c)]

    def proprio(d):
        f, spec = classify(d)
        return f if spec else None

    def rec(c):
        d, a = info[c]
        field, specific = classify(d)
        if field in _CE09_SOTTO or (field == 'ce09' and specific):
            # "AMMORTAMENTI E SVALUTAZIONI" non e' svalutazione crediti: le sotto-voci
            # di B.10 le dicono i conti sotto (Pandoro, 138.838,83 tutti in ce09d)
            out.extend(_ce09_dal_dettaglio(c, d, a, figli))
            return a
        if field == 'ce08':
            # Personale senza sotto-voce: le parole chiave non bastano a ripartirlo, lo
            # fa il modello sui conti sotto il mastro (importers/dettaglio_dal_modello.py)
            out.append(('ce08', a))
            out.append(('_ce_da_dettagliare', _albero_da_dettagliare('ce08', c, d, a, figli)))
            return a
        if specific:
            # un mastro di rimanenze senza natura si legge dai conti (prodotti/materie)
            out.extend(_rimanenze_dal_dettaglio(field, c, d, a, figli, proprio,
                                                ripiego_rimanenze))
            return a
        ch = direct_children(c)
        if not ch:
            out.append((field, a))
            return a
        acc = Decimal('0')
        for x in ch:
            acc += rec(x)
        # The collected children may be incomplete (some detail rows not parsed):
        # preserve the mastro's declared subtotal by booking the shortfall under the
        # parent's own (generic) field. No-op when children reconcile to the parent.
        resid = a - acc
        if abs(resid) > Decimal('0.01'):
            out.append((field, resid))
        return a

    for r in roots:
        rec(r)
    return out

def _be_amount(up: str) -> Optional[Decimal]:
    m = re.search(r'(-?\d{1,3}(?:\.\d{3})*,\d{2})', up)
    return _parse_amount(m.group(1)) if m else None

def is_contrapposte_file(file_path: str) -> bool:
    """Coordinate-based detector for 2-physical-column 'sezioni contrapposte'
    trial-balance dumps. Distinguishes them from standard single-column IV-CEE
    statements (which also mention Attivo/Passivo) by requiring account codes to
    cluster into TWO horizontal bands on the same page.
    """
    try:
        doc = fitz.open(file_path)
    except Exception:
        return False
    try:
        head = "".join(p.get_text() for p in doc[:3]).upper()
        # Strong textual markers are unique to trial-balance / contrapposte dumps
        # and never appear in standard IV-CEE statements.
        if ('SEZIONI CONTRAPPOSTE' in head or 'BILANCIO DI VERIFICA' in head
                or 'TOTALE A PAREGGIO' in head):
            return True
        # Otherwise require, ON THE SAME PAGE: (a) account codes clustered in two
        # horizontal bands AND (b) ATTIVITA'/PASSIVITA' column headers side by
        # side near the top. This excludes IV-CEE nota-integrativa pages where the
        # words merely co-occur in prose.
        for page in doc:
            words = page.get_text('words')
            split = _be_split(words)
            if split is None:
                continue
            xs = [(w[0] + w[2]) / 2 for w in words
                  if re.match(r'^\d', w[4]) and not _BE_AMT_RE.match(w[4])]
            left = sum(1 for x in xs if x < split)
            right = len(xs) - left
            if left < 4 or right < 4:
                continue
            top = page.rect.height * 0.35
            # Case-sensitive: genuine column headers are upper-case ("ATTIVITA'"),
            # whereas nota-integrativa prose uses lower-case ("attività").
            atts = [w for w in words if w[4].startswith('ATTIV') and w[1] < top]
            pasv = [w for w in words if w[4].startswith('PASSIV') and w[1] < top]
            if any(abs(a[1] - p[1]) < 15 and abs(a[0] - p[0]) > 40 for a in atts for p in pasv):
                return True
        return False
    finally:
        doc.close()

def looks_contrapposte(text: str) -> bool:
    """Text-based detector for the 2-column 'sezioni contrapposte' ERP dumps."""
    up = text.upper()
    has_cols = (
        'SEZIONI CONTRAPPOSTE' in up
        or 'BILANCIO DI VERIFICA' in up
        or ('ATTIVITA' in up.replace("'", '') and 'PASSIVITA' in up.replace("'", ''))
        or ('ATTIVO' in up and 'PASSIVO' in up)
    )
    if not has_cols:
        return False
    # Trial-balance account-code density (IV-CEE prose statements lack these).
    codes = re.findall(
        r'\b\d{2}\.\d{2}\.\d{2}\b|\b\d{6}\b|\b\d{3}\.\d{4,5}\b|\d+\s*/\s*\d+\s*/\s*\d+',
        up)
    return len(codes) >= 8
