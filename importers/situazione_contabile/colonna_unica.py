"""Parser della situazione contabile a colonna unica (codici a 6 cifre).

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import re
from decimal import Decimal
from typing import List
from importers.situazione_contabile.comune import (
    Entry, _parse_amount,
)


# ---------------------------------------------------------------------------
# Single-column "Situazione contabile" parser (6-digit codes, TeamSystem-like)
# ---------------------------------------------------------------------------

# Standalone 6-digit code on its own line, or 8-digit sub-account inline with
# its description (e.g. "25060501 Carburante c/anticipi").
_SC1_STANDALONE_CODE_RE = re.compile(r'^\s*(\d{6})\s*$')

_SC1_INLINE_CODE_RE = re.compile(r'^\s*(\d{8})\s+(.+\S)\s*$')

_SC1_AMOUNT_RE = re.compile(r'^\s*(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*-?\s*$')
# Long-term financing code prefixes → route to sp17 (debiti oltre l'esercizio).
# 430 = finanziamenti soci, 440/442 = mutui e finanziamenti bancari.
_SC1_LONGTERM_DEBT_PREFIXES = ('430', '440', '442')

def parse_entries_single_column(text: str) -> List[Entry]:
    """Parse a single-column "Situazione contabile" trial balance.

    Sections are delimited by STATO PATRIMONIALE / CONTO ECONOMICO context and
    ATTIVO / PASSIVO / COSTI / RICAVI header rows. Each account is a code line
    (6-digit standalone, or 8-digit inline with description) followed by a
    (possibly multi-line) description and then a single amount line.

    Emits level-1 Entry objects so they flow through build_iv_cee's
    keyword-based _process_category path, plus a synthetic level-4 utile derived
    from the declared UTILE/TOTALE A PAREGGIO footer (falls back to A-P).
    """
    lines = [ln.rstrip() for ln in text.split('\n')]
    entries: List[Entry] = []

    context = ''   # 'sp' or 'ce'
    section = ''    # attivo / passivo / costi / ricavi
    declared_attivo = Decimal('0')
    declared_passivo = Decimal('0')
    declared_utile_sp = None  # signed: + = utile, set from "UTILE STATO PATRIMONIALE"
    declared_perdita = False

    def _flush(code: str, desc: str, amount: Decimal) -> None:
        if not desc:
            return
        d = desc.strip()
        # Long-term financing: tag description so existing OE routing → sp17.
        if section == 'passivo' and code[:3] in _SC1_LONGTERM_DEBT_PREFIXES:
            if 'OLTRE' not in d.upper() and '(OE)' not in d.upper():
                d = d + ' (OE)'
        entries.append(Entry(code=code, description=d, amount=amount,
                             level=1, section=section))

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i].strip()
        if not raw:
            i += 1
            continue
        upper = raw.upper()

        # Context switches
        if upper == 'STATO PATRIMONIALE':
            context = 'sp'
            i += 1
            continue
        if upper == 'CONTO ECONOMICO':
            context = 'ce'
            i += 1
            continue

        # Section headers (often followed by a total amount line we must skip)
        header = upper.rstrip(' .')
        if header in ('ATTIVO', 'ATTIVITA', "ATTIVITA'", 'ATTIVITA`'):
            section = 'attivo'
            i += 1
            if i < n and _SC1_AMOUNT_RE.match(lines[i].strip()):
                i += 1
            continue
        if header in ('PASSIVO', 'PASSIVITA', "PASSIVITA'", 'PASSIVITA`'):
            section = 'passivo'
            i += 1
            if i < n and _SC1_AMOUNT_RE.match(lines[i].strip()):
                i += 1
            continue
        if header == 'COSTI':
            section = 'costi'
            i += 1
            if i < n and _SC1_AMOUNT_RE.match(lines[i].strip()):
                i += 1
            continue
        if header == 'RICAVI':
            section = 'ricavi'
            i += 1
            if i < n and _SC1_AMOUNT_RE.match(lines[i].strip()):
                i += 1
            continue
        if upper == 'SALDO':
            i += 1
            continue

        # Footer / totals
        if upper.startswith('TOTALE ATTIVO'):
            i += 1
            if i < n and _SC1_AMOUNT_RE.match(lines[i].strip()):
                declared_attivo = _parse_amount(_SC1_AMOUNT_RE.match(lines[i].strip()).group(1).rstrip('-'))
                i += 1
            continue
        if upper.startswith('TOTALE PASSIVO'):
            i += 1
            if i < n and _SC1_AMOUNT_RE.match(lines[i].strip()):
                declared_passivo = _parse_amount(_SC1_AMOUNT_RE.match(lines[i].strip()).group(1).rstrip('-'))
                i += 1
            continue
        if upper.startswith('UTILE STATO PATRIMONIALE') or upper.startswith('UTILE CONTO ECONOMICO'):
            i += 1
            if i < n and _SC1_AMOUNT_RE.match(lines[i].strip()):
                declared_utile_sp = _parse_amount(_SC1_AMOUNT_RE.match(lines[i].strip()).group(1).rstrip('-'))
                i += 1
            continue
        if upper.startswith('PERDITA STATO PATRIMONIALE') or upper.startswith('PERDITA CONTO ECONOMICO'):
            i += 1
            if i < n and _SC1_AMOUNT_RE.match(lines[i].strip()):
                declared_utile_sp = _parse_amount(_SC1_AMOUNT_RE.match(lines[i].strip()).group(1).rstrip('-'))
                declared_perdita = True
                i += 1
            continue
        if (upper.startswith('TOTALE A PAREGGIO') or upper.startswith('TOTALE COSTI')
                or upper.startswith('TOTALE RICAVI')):
            i += 1
            # skip following amount line(s)
            while i < n and _SC1_AMOUNT_RE.match(lines[i].strip()):
                i += 1
            continue

        # Account code (standalone 6-digit)
        m = _SC1_STANDALONE_CODE_RE.match(raw)
        if m and section:
            code = m.group(1)
            # gather description lines until amount
            j = i + 1
            desc_parts: List[str] = []
            amount = None
            while j < n:
                cand = lines[j].strip()
                if not cand:
                    j += 1
                    continue
                am = _SC1_AMOUNT_RE.match(cand)
                if am:
                    amount = _parse_amount(am.group(1).rstrip('-'))
                    j += 1
                    break
                # stop if we hit another code or a structural marker
                if (_SC1_STANDALONE_CODE_RE.match(cand)
                        or _SC1_INLINE_CODE_RE.match(cand)
                        or cand.upper() in ('SALDO', 'ATTIVO', 'PASSIVO', 'COSTI', 'RICAVI')):
                    break
                desc_parts.append(cand)
                j += 1
            if amount is not None:
                _flush(code, ' '.join(desc_parts), amount)
                i = j
                continue
            i += 1
            continue

        # Account code (inline 8-digit + description on same line)
        mi = _SC1_INLINE_CODE_RE.match(raw)
        if mi and section:
            code = mi.group(1)
            desc_parts = [mi.group(2).strip()]
            j = i + 1
            amount = None
            while j < n:
                cand = lines[j].strip()
                if not cand:
                    j += 1
                    continue
                am = _SC1_AMOUNT_RE.match(cand)
                if am:
                    amount = _parse_amount(am.group(1).rstrip('-'))
                    j += 1
                    break
                if (_SC1_STANDALONE_CODE_RE.match(cand)
                        or _SC1_INLINE_CODE_RE.match(cand)
                        or cand.upper() in ('SALDO', 'ATTIVO', 'PASSIVO', 'COSTI', 'RICAVI')):
                    break
                desc_parts.append(cand)
                j += 1
            if amount is not None:
                _flush(code, ' '.join(desc_parts), amount)
                i = j
                continue
            i += 1
            continue

        i += 1

    # Synthetic utile (level 4). Prefer the declared SP utile/perdita footer.
    if declared_utile_sp is not None:
        if declared_perdita:
            entries.append(Entry(code='****', description="PERDITA D'ESERCIZIO",
                                 amount=declared_utile_sp, level=4, section='attivo'))
        else:
            entries.append(Entry(code='****', description="UTILE D'ESERCIZIO",
                                 amount=declared_utile_sp, level=4, section='passivo'))
    elif declared_attivo and declared_passivo:
        diff = declared_attivo - declared_passivo
        if diff >= 0:
            entries.append(Entry(code='****', description="UTILE D'ESERCIZIO",
                                 amount=diff, level=4, section='passivo'))
        else:
            entries.append(Entry(code='****', description="PERDITA D'ESERCIZIO",
                                 amount=-diff, level=4, section='attivo'))

    return entries
