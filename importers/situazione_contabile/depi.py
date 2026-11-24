"""Parser DEPI: codici XX/YY/ZZZ con i subtotali ***.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import re
from decimal import Decimal
from typing import List
from importers.situazione_contabile.comune import (
    Entry, _parse_amount,
)


# Patterns for line parsing
# DEPI XX/YY/ZZZ + subtotals, plus the 2-part XX/YYYY (detail) and XX/**** variant.
_CODE_RE = re.compile(
    r'^\s*('
    r'\d{2}/(?:\d{2}|\*\*)/(?:\d{3}|\*{3})'  # XX/YY/ZZZ, XX/YY/***, XX/**/***
    r'|\d{2}/(?:\d{4}|\*{4})'                 # XX/YYYY detail, XX/**** subtotal
    r'|\*{3,5}'                               # ***, ****, *****
    r')\s*$'
)

_AMOUNT_RE = re.compile(r'^\s*([\d]+(?:\.[\d]{3})*,[\d]{2})\s*$')

def _classify_code(code: str) -> int:
    """Return level for an account code."""
    if code == '*****':
        return 5
    if code == '****':
        return 4
    if code == '***':
        return 3
    if re.match(r'^\d{2}/\*\*/\*{3}$', code):
        return 2  # XX/**/***
    if re.match(r'^\d{2}/\*{4}$', code):
        return 2  # XX/**** (2-part subtotal — maps to IV CEE categories)
    if re.match(r'^\d{2}/\d{2}/\*{3}$', code):
        return 1  # XX/YY/***
    return 0  # XX/YY/ZZZ or XX/YYYY detail

def parse_entries(text: str) -> List[Entry]:
    """
    Parse trial balance text into Entry objects.

    Handles multi-line format from PyMuPDF:
      code line -> description line -> amount line(s)
    """
    lines = text.split('\n')
    entries = []
    section = ''

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # Detect section headers: ** followed by section name
        if line == '**' and i + 1 < len(lines):
            next_line = lines[i + 1].strip().upper()
            if 'A T T I V I T' in next_line or next_line.startswith('ATTIVIT'):
                section = 'attivo'
                i += 2
                continue
            elif 'P A S S I V I T' in next_line or next_line.startswith('PASSIVIT'):
                section = 'passivo'
                i += 2
                continue
            elif 'COSTI' in next_line:
                section = 'costi'
                i += 2
                continue
            elif 'RICAVI' in next_line:
                section = 'ricavi'
                i += 2
                continue
            i += 1
            continue

        # Try to match account code
        code_match = _CODE_RE.match(line)
        if code_match:
            code = code_match.group(1).strip()
            level = _classify_code(code)

            # Next line should be description
            desc = ''
            if i + 1 < len(lines):
                desc = lines[i + 1].strip()
                if _CODE_RE.match(desc) or _AMOUNT_RE.match(desc):
                    desc = ''
                else:
                    i += 1

            # Next line(s) should be amount(s).
            #   Mono-column layout:  amt1 = saldo
            #   Dual-year layout:    amt1 = saldo corrente, amt2 = saldo precedente,
            #                        amt3 = differenza (left as an orphan line, skipped
            #                        by the main loop), then a % (not an _AMOUNT_RE match).
            # We capture the SECOND consecutive amount as the prior-year saldo so a
            # dual-year trial balance (e.g. budget_132) yields both years. Single-column
            # files have no second consecutive amount → amount_prior stays 0.
            amount = Decimal('0')
            amount_prior = Decimal('0')
            if i + 1 < len(lines):
                amt_match = _AMOUNT_RE.match(lines[i + 1].strip())
                if amt_match:
                    amount = _parse_amount(amt_match.group(1))
                    i += 1
                    # Second consecutive amount = prior-year column (dual-year files).
                    if i + 1 < len(lines):
                        amt2_match = _AMOUNT_RE.match(lines[i + 1].strip())
                        if amt2_match:
                            amount_prior = _parse_amount(amt2_match.group(1))
                            i += 1

            entries.append(Entry(
                code=code,
                description=desc,
                amount=amount,
                level=level,
                section=section,
                amount_prior=amount_prior,
            ))

        i += 1

    return entries
