"""Parser TeamSystem «Stato patrimoniale / Conto economico».

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import re
from typing import List
from importers.situazione_contabile.comune import (
    Entry, _parse_amount,
)
from importers.situazione_contabile.regole import (
    _kw_match,
)


# ---------------------------------------------------------------------------
# TeamSystem "Stato patrimoniale / Conto economico" parser
# Codes: XX/YYYY/YYYY (e.g. 04/0005/0010). Accounts are grouped under
# Attivit�/Passivit� (SP) and Ricavi/Costi (CE) header rows that determine the
# balance section by sign. Section comes from the header, NOT from keywords.
# ---------------------------------------------------------------------------

_TS_CODE_RE = re.compile(r'^\s*(\d{2}/\d{4,8}(?:/\d{4})?)\s*$')

_TS_AMOUNT_RE = re.compile(r'^\s*(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*-?\s*$')

def is_teamsystem_sc(text: str) -> bool:
    """Detect TeamSystem trial-balance exports (Stato patrimoniale / Conto economico)."""
    upper = text.upper()
    if 'TEAMSYSTEM' not in upper:
        return False
    if not re.search(r'STATO\s+PATRIMONIALE', upper):
        return False
    codes = re.findall(r'\b\d{2}/\d{4}/\d{4}\b', text)
    return len(codes) >= 10

def parse_entries_teamsystem(text: str) -> List[Entry]:
    """Parse a TeamSystem SP/CE trial balance into level-1 entries + utile."""
    lines = [ln.rstrip() for ln in text.split('\n')]
    entries: List[Entry] = []

    context = ''   # 'sp' or 'ce'
    section = ''
    declared_utile = None
    declared_perdita = False

    def _level_from_code(code: str) -> int:
        """Hierarchy encoded by TeamSystem zero-filled account components."""
        parts = code.split('/')
        if len(parts) == 3:
            if parts[1] == '0000' and parts[2] == '0000':
                return 2
            if parts[2] == '0000':
                return 1
            return 0
        if len(parts) == 2 and set(parts[1]) == {'0'}:
            return 2
        return 0

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i].strip()
        if not raw:
            i += 1
            continue
        upper = raw.upper()

        if upper == 'STATO PATRIMONIALE':
            context = 'sp'
            i += 1
            continue
        if upper == 'CONTO ECONOMICO':
            context = 'ce'
            i += 1
            continue

        # Header rows set the active section (by sign placement)
        h = upper.rstrip(' .').replace('À', 'A').replace('�', '')
        if h in ('ATTIVITA', "ATTIVITA'", 'ATTIVITA`', 'ATTIVO'):
            section = 'attivo'
            i += 1
            continue
        if h in ('PASSIVITA', "PASSIVITA'", 'PASSIVITA`', 'PASSIVO'):
            section = 'passivo'
            i += 1
            continue
        if h == 'RICAVI':
            section = 'ricavi'
            i += 1
            continue
        if h == 'COSTI':
            section = 'costi'
            i += 1
            continue
        if upper in ('CONTO', 'DESCRIZIONE'):
            i += 1
            continue

        # Footer totals
        if upper.startswith('TOTALE ATTIVO') or upper.startswith('TOTALE PASSIVO') \
                or upper.startswith('TOTALE COSTI') or upper.startswith('TOTALE RICAVI'):
            i += 1
            while i < n and _TS_AMOUNT_RE.match(lines[i].strip()):
                i += 1
            continue
        if upper.startswith('UTILE DI ESERCIZIO') and context and (
                i + 1 < n and _TS_AMOUNT_RE.match(lines[i + 1].strip())):
            # This is the footer plug only when it is a standalone total row;
            # the equity account "UTILE DI ESERCIZIO" is preceded by a code and
            # handled below. Footer rows have no preceding code on this line.
            declared_utile = _parse_amount(_TS_AMOUNT_RE.match(lines[i + 1].strip()).group(1).rstrip('-'))
            i += 2
            continue
        if upper.startswith('PERDITA DI ESERCIZIO') and context and (
                i + 1 < n and _TS_AMOUNT_RE.match(lines[i + 1].strip())):
            declared_utile = _parse_amount(_TS_AMOUNT_RE.match(lines[i + 1].strip()).group(1).rstrip('-'))
            declared_perdita = True
            i += 2
            continue

        m = _TS_CODE_RE.match(raw)
        if m and section:
            code = m.group(1)
            j = i + 1
            desc_parts: List[str] = []
            amount = None
            while j < n:
                cand = lines[j].strip()
                if not cand:
                    j += 1
                    continue
                am = _TS_AMOUNT_RE.match(cand)
                if am:
                    amount = _parse_amount(am.group(1).rstrip('-'))
                    j += 1
                    break
                if _TS_CODE_RE.match(cand) or cand.upper() in (
                        'CONTO', 'DESCRIZIONE', 'ATTIVIT�', 'PASSIVIT�',
                        'RICAVI', 'COSTI'):
                    break
                desc_parts.append(cand)
                j += 1
            if amount is not None:
                desc = ' '.join(desc_parts)
                du = desc.upper()
                # An equity account "UTILE/PERDITA DI ESERCIZIO" is a booked
                # result that is part of the declared Totale Passivo. The
                # current-year result is the footer "Utile di esercizio" plug,
                # so retain this account as a reserve (tag it so the equity
                # skip in _process_category treats it as prior/retained).
                if section == 'passivo' and (
                        _kw_match(du, ['UTILE', 'ESERCIZ'])
                        or _kw_match(du, ['PERDITA', 'ESERCIZ'])
                        or _kw_match(du, ['RISULTATO', 'ESERCIZ'])):
                    desc = desc + ' (PRECEDENTE)'
                entries.append(Entry(code=code, description=desc,
                                     amount=amount, level=_level_from_code(code),
                                     section=section))
                i = j
                continue
            i += 1
            continue

        i += 1

    if declared_utile is not None:
        if declared_perdita:
            entries.append(Entry(code='****', description="PERDITA D'ESERCIZIO",
                                 amount=declared_utile, level=4, section='attivo'))
        else:
            entries.append(Entry(code='****', description="UTILE D'ESERCIZIO",
                                 amount=declared_utile, level=4, section='passivo'))

    return entries
