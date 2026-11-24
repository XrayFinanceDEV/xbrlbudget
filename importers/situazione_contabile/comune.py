"""La riga letta da un bilancio di verifica (Entry) e la lettura di un importo italiano.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass
class Entry:
    """A single parsed line from the trial balance."""
    code: str          # e.g. "03/05/005", "03/**/***", "***"
    description: str
    amount: Decimal    # single amount (section determines dare/avere)
    level: int = 0     # 0=detail, 1=sub3, 2=sub2, 3=section total, 4=utile, 5=pareggio
    section: str = ""  # 'attivo', 'passivo', 'costi', 'ricavi'
    amount_prior: Decimal = Decimal('0')  # prior-year column (dual-year trial balances)

    @property
    def prefix2(self) -> str:
        """First two digits of account code, e.g. '03'."""
        return self.code[:2] if len(self.code) >= 2 and self.code[:2].isdigit() else ""

def _parse_amount(s: str) -> Decimal:
    """Parse Italian-formatted amount: '1.234,56' -> Decimal('1234.56')."""
    s = s.strip()
    if not s:
        return Decimal('0')
    s = s.replace('.', '').replace(',', '.')
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal('0')
