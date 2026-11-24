"""Parser AGO/ERP: codici a 8 cifre, impaginazione a due colonne.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import re
from decimal import Decimal
from typing import Dict, List, Tuple
from importers.situazione_contabile.comune import (
    Entry, _parse_amount,
)
from importers.situazione_contabile.regole import (
    _CE_COSTI_RULES, _CE_RICAVI_RULES, _SP_ATTIVO_RULES, _SP_PASSIVO_RULES, _kw_match,
)


# ---------------------------------------------------------------------------
# AGO / ERP parser — 8-digit codes, 2-column block layout
# ---------------------------------------------------------------------------

_AGO_PARENT_CODE_RE = re.compile(r'^(\d{8})\s*-\s*(.+?)\s*$')

_AGO_DETAIL_CODE_RE = re.compile(r'^(\d{6})\s+(\d{3})\b')  # e.g. "100605 000"

_AGO_AMOUNT_RE = re.compile(r'^\s*(-?[\d]+(?:\.[\d]{3})*,[\d]{2})\s*-?\s*$')
_AGO_SKIP_MARKERS = [
    "TOTALE A PAREGGIO",
    "SITUAZIONE PATRIMONIALE",
    "CONTO ECONOMICO",
    "BILANCIO DI VERIFIC",
    "DATI CONTABILI",
    "PARTITA IVA",
    "CODICE FISCALE",
    "ESERCIZIO",
    "DISSTE",
]

def _extract_amounts_in_order(lines: List[str]) -> List[Decimal]:
    """Return amounts (in textual order) from a list of block lines."""
    out: List[Decimal] = []
    for ln in lines:
        m = _AGO_AMOUNT_RE.match(ln)
        if m:
            out.append(_parse_amount(m.group(1)))
    return out

def _classify_ago_section(desc: str, col1_section: str, col2_section: str) -> str:
    """Classify a description into a column section by Italian-accounting keywords.

    Returns 'attivo'/'passivo'/'costi'/'ricavi' or '' if ambiguous. Passivo
    markers take precedence so descriptions like "F.do sval. crediti" resolve
    correctly despite containing CREDITI.
    """
    u = desc.upper()
    if col1_section == 'attivo':
        # Strong passivo markers (checked before attivo)
        if any(k in u for k in ('F.DO', 'F/AMM', 'DEBITI', 'FONDO', 'FONDI',
                                'CAPITALE', 'RISERVA', 'RISERVE', 'PATRIMONIO',
                                'SOVRAPPREZZO', 'OBBLIGAZION', 'MUTUI',
                                'ACCONTI', 'TFR')):
            return 'passivo'
        if ('TRATTAMENTO' in u and 'FINE' in u):
            return 'passivo'
        if 'UTILI' in u and any(w in u for w in ('PORTATI', 'NUOVO', 'PRECEDENT')):
            return 'passivo'
        if 'RATEI' in u and 'PASSIV' in u:
            return 'passivo'
        if 'RISCONTI' in u and 'PASSIV' in u:
            return 'passivo'
        # Attivo markers
        if any(k in u for k in ('CREDITI', 'DEPOSIT', 'DENARO', 'CASSA',
                                'RIMANENZE', 'MAGAZZIN', 'IMMOB',
                                'ATTREZZ', 'MACCHINE', 'MACCHINAR', 'IMPIANT',
                                'AUTOVEIC', 'AUTOVETTUR', 'AUTOMEZZ',
                                'MEZZI TRASP', 'MOBILI', 'ARREDAMENT',
                                'PARTECIPAZ', 'TERREN', 'FABBRICAT',
                                'SOFTWARE', 'BREVETT', 'MARCHI', 'AVVIAMENTO',
                                'LICENZ', 'PLURIENN')):
            return 'attivo'
        if 'AUTO' in u or 'MOTO' in u or 'CICLO' in u:
            return 'attivo'
        if 'RATEI' in u and 'ATTIV' in u:
            return 'attivo'
        if 'RISCONTI' in u and 'ATTIV' in u:
            return 'attivo'
        return ''
    # CE
    if any(k in u for k in ('RICAVI', 'PROVENTI', 'PLUSVALENZ', 'RIMBORSI', 'CONTRIBUT')):
        return 'ricavi'
    if 'SOPRAVVEN' in u and 'ATTIV' in u:
        return 'ricavi'
    if 'INTERESSI' in u and 'ATTIV' in u:
        return 'ricavi'
    if any(k in u for k in ('COSTI', 'ONERI', 'SALARI', 'STIPENDI', 'AMM', 'SPESE',
                            'INTERESSI', 'IMPOSTE', 'SVALUTAZ', 'IRAP', 'IRES',
                            'ACCANTON', 'GODIMENTO', 'MATERIE', 'MERCI', 'QUOTE',
                            'PERSONALE')):
        return 'costi'
    return ''

def _guess_ago_column(desc: str, col1_section: str, col2_section: str) -> str:
    """Pick a column for an orphan single-code block. Falls back to col2 (passivo/ricavi)."""
    sec = _classify_ago_section(desc, col1_section, col2_section)
    return sec or col2_section

def _any_rule_matches(desc_upper: str, rules: list) -> bool:
    """True if any (keywords, field) rule matches the description."""
    for keywords, _ in rules:
        if _kw_match(desc_upper, keywords):
            return True
    return False

def _semantic_section_from_desc(desc_upper: str, is_sp: bool) -> str:
    """Classify a description by keywords into its semantic IV CEE section.

    Returns 'attivo'/'passivo' for SP, 'costi'/'ricavi' for CE, or '' when
    ambiguous (no rule matches, or both rule-sets match). Passivo/ricavi
    priority handles "F.do sval. crediti" (passivo wins) and "Ricavi delle
    vendite" (ricavi wins over the costi-side RICAVI returns rule).
    """
    if is_sp:
        p_match = _any_rule_matches(desc_upper, _SP_PASSIVO_RULES)
        a_match = _any_rule_matches(desc_upper, _SP_ATTIVO_RULES)
        if p_match and not a_match:
            return 'passivo'
        if a_match and not p_match:
            return 'attivo'
        if p_match and a_match:
            # Both matched — prefer passivo (F.do sval. crediti case)
            return 'passivo'
        return ''
    # CE: check ricavi FIRST since "RICAVI" keyword also appears in the costi
    # rules (as "returns in cost section"). Genuine Ricavi items win.
    r_match = _any_rule_matches(desc_upper, _CE_RICAVI_RULES)
    c_match = _any_rule_matches(desc_upper, _CE_COSTI_RULES)
    if r_match:
        return 'ricavi'
    if c_match:
        return 'costi'
    return ''

def parse_entries_ago(file_path: str) -> Tuple[List[Entry], Dict[str, Decimal]]:
    """Parse AGO/ERP trial balance using block-based 2-column layout.

    Each block is a logical row with 1–2 parent codes. Column (left/right) is
    assigned primarily from description keywords (semantic section). Positional
    order within the block is used only as a tie-breaker when keywords are
    ambiguous. Amounts are then summed per IV CEE field during build_iv_cee.

    Returns:
        (entries, totali) — level-1 parent entries + synthetic level-4 utile;
        totali has declared 'attivo','passivo','costi','ricavi' totals.
    """
    doc = fitz.open(file_path)
    entries: List[Entry] = []
    totali: Dict[str, Decimal] = {}

    for page in doc:
        page_text_upper = page.get_text().upper()
        is_sp = 'SITUAZIONE PATRIMONIALE' in page_text_upper
        is_ce = 'CONTO ECONOMICO' in page_text_upper
        if not (is_sp or is_ce):
            continue

        col1_section = 'attivo' if is_sp else 'costi'
        col2_section = 'passivo' if is_sp else 'ricavi'

        blocks = page.get_text('blocks', sort=True)
        for b in blocks:
            text = b[4]
            lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
            if not lines:
                continue
            upper = text.upper()

            # Capture declared totali labels
            if "TOTALE ATTIVITA" in upper and "TOTALE PASSIVITA" in upper:
                amts = _extract_amounts_in_order(lines)
                if len(amts) >= 2:
                    totali['attivo'] = amts[0]
                    totali['passivo'] = amts[1]
                continue
            if "TOTALE COSTI" in upper and "TOTALE RICAVI" in upper:
                amts = _extract_amounts_in_order(lines)
                if len(amts) >= 2:
                    totali['costi'] = amts[0]
                    totali['ricavi'] = amts[1]
                continue

            # Skip structural/metadata blocks
            if any(m in upper for m in _AGO_SKIP_MARKERS):
                continue
            if ("UTILE D" in upper or "PERDITA D" in upper) and not any(
                _AGO_PARENT_CODE_RE.match(ln) for ln in lines
            ):
                continue
            if all(ln.upper().strip(" '") in ("ATTIVITA", "PASSIVITA", "COSTI", "RICAVI")
                   for ln in lines):
                continue

            # Parse lines in order: pair each parent code with the first
            # following amount not already claimed. Handles both parent-first
            # blocks ([code1, code2, amt1, amt2]) and mixed blocks with
            # interleaved detail lines ([detail_code, det_amt, parent_code,
            # parent_amt]).
            parent_positions = []  # (line_idx, code, desc)
            amount_positions = []  # (line_idx, amount)
            for idx, ln in enumerate(lines):
                pm = _AGO_PARENT_CODE_RE.match(ln)
                if pm:
                    parent_positions.append((idx, pm.group(1), pm.group(2).strip()))
                    continue
                am = _AGO_AMOUNT_RE.match(ln)
                if am:
                    amount_positions.append((idx, _parse_amount(am.group(1))))

            if not parent_positions:
                continue

            # Pair: for each parent, take first amount at line_idx >= parent's,
            # skipping amounts already claimed.
            pairs: List[Tuple[str, str, Decimal]] = []
            claimed: set = set()
            for p_idx, code, desc in parent_positions:
                chosen_amt = None
                for a_idx, amt in amount_positions:
                    if a_idx in claimed:
                        continue
                    if a_idx >= p_idx:
                        chosen_amt = amt
                        claimed.add(a_idx)
                        break
                if chosen_amt is None:
                    continue
                pairs.append((code, desc, chosen_amt))

            # Assign section: keyword-first, positional fallback for ambiguity
            for i, (code, desc, amt) in enumerate(pairs):
                desc_upper = desc.upper()
                sec = _semantic_section_from_desc(desc_upper, is_sp)
                if not sec:
                    sec = col1_section if i == 0 else col2_section
                entries.append(Entry(
                    code=code, description=desc,
                    amount=amt, level=1, section=sec,
                ))
    doc.close()

    # Compute utile from our semantically-classified CE entries — more
    # reliable than the PDF's declared TOTALE labels, whose column-to-label
    # pairing can be ambiguous in rotated layouts.
    ricavi_sum = sum((e.amount for e in entries if e.section == 'ricavi'), Decimal('0'))
    costi_sum = sum((e.amount for e in entries if e.section == 'costi'), Decimal('0'))
    utile_signed = ricavi_sum - costi_sum

    if utile_signed >= 0:
        entries.append(Entry(
            code='****', description="UTILE D'ESERCIZIO",
            amount=abs(utile_signed), level=4, section='passivo',
        ))
    else:
        entries.append(Entry(
            code='****', description="PERDITA D'ESERCIZIO",
            amount=abs(utile_signed), level=4, section='attivo',
        ))

    return entries, totali
