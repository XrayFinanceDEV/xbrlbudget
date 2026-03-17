"""
Deterministic parser for "Situazione Contabile" (trial balance) PDFs.

These PDFs use XX/YY/ZZZ account codes with a *** subtotal hierarchy,
unlike IV CEE formatted PDFs. This parser maps trial balance accounts
to IV CEE sp01-sp18 and ce01-ce20 fields without using an LLM.

Classification is keyword-based (account descriptions), NOT prefix-based,
so it works across different Italian accounting software numbering systems.

Account hierarchy (DEPI format):
  XX/YY/ZZZ  = detail line
  XX/YY/***  = 3rd-level subtotal
  XX/**/***  = 2nd-level subtotal (maps to IV CEE categories)
  ***        = section total (TOTALE ATTIVITA`, TOTALE PASSIVITA`, etc.)
  ****       = UTILE DI ESERCIZIO
  *****      = TOTALE A PAREGGIO
"""

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class Entry:
    """A single parsed line from the trial balance."""
    code: str          # e.g. "03/05/005", "03/**/***", "***"
    description: str
    amount: Decimal    # single amount (section determines dare/avere)
    level: int = 0     # 0=detail, 1=sub3, 2=sub2, 3=section total, 4=utile, 5=pareggio
    section: str = ""  # 'attivo', 'passivo', 'costi', 'ricavi'

    @property
    def prefix2(self) -> str:
        """First two digits of account code, e.g. '03'."""
        return self.code[:2] if len(self.code) >= 2 and self.code[:2].isdigit() else ""


def is_situazione_contabile(text: str) -> bool:
    """Detect if text is from a Situazione Contabile / trial balance PDF.

    Supports two code formats:
    - DEPI: XX/YY/ZZZ (e.g. 03/05/005)
    - AGO/ERP: 8-digit codes with keywords (e.g. 13065000, 37015000)
    """
    sample = text[:5000]
    # DEPI format: XX/YY/ZZZ codes
    depi_codes = re.findall(r'\b\d{2}/\d{2}/\d{3}\b', sample)
    if len(depi_codes) >= 10:
        return True
    # AGO/ERP format: 8-digit codes + "SITUAZIONE PATRIMONIALE" or "BILANCIO DI VERIFICA"
    ago_codes = re.findall(r'\b\d{8}\b', sample)
    if len(ago_codes) >= 5 and re.search(r'SITUAZIONE\s+PATRIMONIALE|BILANCIO\s+DI\s+VERIFICA', sample, re.IGNORECASE):
        return True
    return False


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


# Patterns for line parsing
_CODE_RE = re.compile(r'^\s*(\d{2}/(?:\d{2}|\*\*)/(?:\d{3}|\*{3})|\*{3,5})\s*$')
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
    if re.match(r'^\d{2}/\d{2}/\*{3}$', code):
        return 1  # XX/YY/***
    return 0  # XX/YY/ZZZ detail


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

            # Next line(s) should be amount(s)
            amount = Decimal('0')
            if i + 1 < len(lines):
                amt_match = _AMOUNT_RE.match(lines[i + 1].strip())
                if amt_match:
                    amount = _parse_amount(amt_match.group(1))
                    i += 1
                    # Skip second amount for pareggio lines
                    if level == 5 and i + 1 < len(lines):
                        if _AMOUNT_RE.match(lines[i + 1].strip()):
                            i += 1

            entries.append(Entry(
                code=code,
                description=desc,
                amount=amount,
                level=level,
                section=section,
            ))

        i += 1

    return entries


# ---------------------------------------------------------------------------
# Keyword-based classification rules
# ---------------------------------------------------------------------------
# Each rule is (keywords_to_match, iv_cee_field_or_action)
# Keywords are matched against uppercased description text.
# Rules are tried in order; first match wins.

def _kw_match(desc_upper: str, keywords: List[str]) -> bool:
    """Check if ALL keywords appear in the description."""
    return all(kw in desc_upper for kw in keywords)


def _kw_any(desc_upper: str, keywords: List[str]) -> bool:
    """Check if ANY keyword appears in the description."""
    return any(kw in desc_upper for kw in keywords)


# SP ATTIVO keyword rules: (keywords, field)
# Matched against sub2/sub3 descriptions in the ATTIVO section
_SP_ATTIVO_RULES = [
    # Fixed assets (gross — will be netted against depreciation)
    (['IMMOBILIZZAZIONI IMMATERIALI'], 'gross_sp02'),
    (['IMMOBILIZZAZIONI MATERIALI'], 'gross_sp03'),
    (['IMMOBILIZZAZIONI FINANZIARIE'], 'gross_sp04'),
    # Current assets
    (['RIMANENZE'], 'sp05'),
    (['RATEI', 'RISCONTI', 'ATTIV'], 'sp10'),
    (['RATEI', 'ATTIV'], 'sp10'),
    (['RISCONTI', 'ATTIV'], 'sp10'),
    (['DISPONIBILIT'], 'sp09'),  # Disponibilità liquide (banks + cash)
    # Everything else in attivo = crediti (sp06)
]

# SP PASSIVO keyword rules
_SP_PASSIVO_RULES = [
    # Depreciation funds (will be netted against gross assets)
    (['F/AMM', 'IMMAT'], 'depr_sp02'),
    (['F/AMM', 'MATER'], 'depr_sp03'),
    (['AMMORTAM', 'IMMAT'], 'depr_sp02'),
    (['AMMORTAM', 'MATER'], 'depr_sp03'),
    # Crediti deduction
    (['RISCHI', 'CREDITI'], 'deduct_crediti'),
    (['SVALUT', 'CREDITI'], 'deduct_crediti'),
    # Banks avere = overdrafts
    (['DISPONIBILIT'], 'bank_avere'),
    # Equity (sub2 total and sub3 components)
    (['PATRIMONIO NETTO'], 'equity_total'),
    (['CAPITALE'], 'equity_total'),
    (['RISERVA'], 'equity_total'),
    (['RISERVE'], 'equity_total'),
    (['UTILE', 'ESERCIZ'], 'equity_total'),
    (['PERDITA', 'ESERCIZ'], 'equity_total'),
    (['UTILI', 'PORTATI'], 'equity_total'),
    # Fondi
    (['FONDI', 'RISCHI'], 'sp14'),
    (['FONDI', 'ONERI'], 'sp14'),
    # TFR
    (['TFR'], 'sp15'),
    (['TRATTAMENTO', 'FINE', 'RAPPORTO'], 'sp15'),
    # Debiti v/banche (need entro/oltre split from details)
    (['DEBITI', 'BANCH'], 'debt_bank'),
    (['DEBITI', 'FINANZIAT'], 'debt_bank'),
    # Ratei e risconti passivi
    (['RATEI', 'RISCONTI', 'PASSIV'], 'sp18'),
    (['RATEI', 'PASSIV'], 'sp18'),
    (['RISCONTI', 'PASSIV'], 'sp18'),
    # Debiti tributari
    (['DEBITI', 'TRIBUTAR'], 'sp16'),
    (['DEBITI', 'TRIBUTARI'], 'sp16'),
    # Debiti previdenziali
    (['DEBITI', 'PREV'], 'sp16'),
    (['DEBITI', 'SICUR'], 'sp16'),
    (['DEBITI', 'INPS'], 'sp16'),
    # Specific debt categories → sp16 (breve by default)
    (['DEBITI', 'FORNITOR'], 'sp16'),
    (['ACCONTI'], 'sp16'),
    (['ALTRI DEBITI'], 'sp16'),
    # SBF / crediti ceduti in passivo → sp16
    (['CREDITI', 'CLIENT'], 'sp16'),
]

# CE keyword rules for COSTI section
_CE_COSTI_RULES = [
    (['RICAVI'], 'ce01_return'),  # Returns/discounts in cost section
    # Variazioni rimanenze MUST be before materie prime (descriptions often contain "MERCI")
    (['VARIAZ', 'RIMANENZ'], 'ce10'),
    (['VAR.RIM'], 'ce10'),
    # Materie prime / merci
    (['MATERIE PRIME'], 'ce05'),
    (['MATERIE', 'CONSUMO'], 'ce05'),
    (['COSTI', 'MAT'], 'ce05'),  # "COSTI P/MAT.PRI,SUSS.,CON.E MER."
    (['MERCI'], 'ce05'),
    (['MAT.PRI'], 'ce05'),
    (['SERVIZI'], 'ce06'),
    (['GODIMENTO', 'BENI'], 'ce07'),
    (['PERSONALE'], 'ce08'),
    (['AMMORTAM', 'IMMAT'], 'ce09a'),  # Ammort. immateriali
    (['AMM.T', 'IMM. IMMAT'], 'ce09a'),
    (['AMM.TI', 'IMMAT'], 'ce09a'),
    (['AMMORTAM', 'MATER'], 'ce09b'),  # Ammort. materiali
    (['AMM.T', 'IMM. MAT'], 'ce09b'),
    (['AMM.TO', 'MAT'], 'ce09b'),
    (['SVALUT'], 'ce09d'),  # Svalutazioni
    (['ACCANTONAM', 'RISCHI'], 'ce11'),
    (['ALTRI ACCANTONAM'], 'ce11b'),
    (['ONERI DIVERSI'], 'ce12'),
    (['INTERESSI', 'ONERI'], 'ce15'),
    (['INT. PASS'], 'ce15'),
    (['ONERI FINANZ'], 'ce15'),
    (['IMPOSTE', 'REDDITO'], 'ce20'),
    (['IMPOSTE', 'ESERC'], 'ce20'),
    # Proventi/oneri straordinari in costs
    (['ONERI STRAORD'], 'ce19'),
    (['PROVENTI', 'PARTECIP'], 'ce13_cost'),
]

# CE keyword rules for RICAVI section
_CE_RICAVI_RULES = [
    # More specific rules first
    (['VARIAZ', 'RIMANENZ'], 'ce10_close'),
    (['VAR.RIM'], 'ce10_close'),
    (['ALTRI RICAVI'], 'ce04'),
    (['ALTRI', 'PROVENTI'], 'ce04'),
    (['PROVENTI', 'PARTECIP'], 'ce13'),
    (['PROVENTI', 'FINANZ'], 'ce14'),
    (['PROVENTI STRAORD'], 'ce18'),
    # Generic ricavi last (catches "RICAVI DELLE VENDITE" etc.)
    (['RICAVI'], 'ce01'),
]

# Equity sub3 keyword rules
_EQUITY_RULES = [
    (['CAPITALE'], 'capitale'),
    # Everything else in equity = riserve (includes utile esercizio precedente)
]


def _classify_sp_attivo(desc_upper: str) -> str:
    """Classify an attivo entry by description keywords. Returns field or 'sp06' default."""
    for keywords, field in _SP_ATTIVO_RULES:
        if _kw_match(desc_upper, keywords):
            return field
    return 'sp06'  # default: crediti


def _classify_sp_passivo(desc_upper: str) -> str:
    """Classify a passivo entry by description keywords. Returns field or 'sp16' default."""
    for keywords, field in _SP_PASSIVO_RULES:
        if _kw_match(desc_upper, keywords):
            return field
    return 'sp16'  # default: debiti breve


def _classify_ce_costi(desc_upper: str) -> Optional[str]:
    """Classify a CE cost entry by description keywords."""
    for keywords, field in _CE_COSTI_RULES:
        if _kw_match(desc_upper, keywords):
            return field
    return None


def _classify_ce_ricavi(desc_upper: str) -> Optional[str]:
    """Classify a CE ricavi entry by description keywords."""
    for keywords, field in _CE_RICAVI_RULES:
        if _kw_match(desc_upper, keywords):
            return field
    return None


def build_iv_cee(entries: List[Entry]) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Map trial balance entries to IV CEE sp01-sp18 and ce01-ce20 fields."""
    bs: Dict[str, Decimal] = {}
    ce: Dict[str, Decimal] = {}

    # Accumulators
    gross_sp02 = Decimal('0')  # Immob. immateriali (gross)
    gross_sp03 = Decimal('0')  # Immob. materiali (gross)
    depr_sp02 = Decimal('0')   # F/amm immateriali
    depr_sp03 = Decimal('0')   # F/amm materiali
    bank_dare = Decimal('0')
    bank_avere = Decimal('0')
    crediti_deduction = Decimal('0')
    capitale = Decimal('0')
    riserve = Decimal('0')
    utile_esercizio = Decimal('0')

    # Debt entro/oltre from detail lines
    debt_bank_entro = Decimal('0')
    debt_bank_oltre = Decimal('0')
    debt_bank_total = Decimal('0')

    # CE sub-items
    ce_tfr_accrual = Decimal('0')
    ce09a = Decimal('0')  # ammort. immateriali
    ce09b = Decimal('0')  # ammort. materiali
    ce09d = Decimal('0')  # svalutazioni
    ce10_opening = Decimal('0')
    ce10_closing = Decimal('0')
    ce01_total = Decimal('0')
    ce01_returns = Decimal('0')

    # Track which prefixes have sub2 entries
    has_sub2: set = set()
    for entry in entries:
        if entry.level == 2:
            has_sub2.add((entry.prefix2, entry.section))

    def _process_category(entry: Entry) -> None:
        """Process a sub2 or standalone sub3 entry through keyword classification."""
        nonlocal gross_sp02, gross_sp03, depr_sp02, depr_sp03
        nonlocal bank_dare, bank_avere, crediti_deduction, capitale, riserve
        nonlocal debt_bank_total
        nonlocal ce09a, ce09b, ce09d
        nonlocal ce10_opening, ce10_closing, ce01_total, ce01_returns

        desc_upper = entry.description.upper()

        # =================================================================
        # STATO PATRIMONIALE — ATTIVO
        # =================================================================
        if entry.section == 'attivo':
            field = _classify_sp_attivo(desc_upper)
            if field == 'gross_sp02':
                gross_sp02 += entry.amount
            elif field == 'gross_sp03':
                gross_sp03 += entry.amount
            elif field == 'gross_sp04':
                bs['sp04'] = bs.get('sp04', Decimal('0')) + entry.amount
            elif field == 'sp09':
                bank_dare += entry.amount
            else:
                bs[field] = bs.get(field, Decimal('0')) + entry.amount
            return

        # =================================================================
        # STATO PATRIMONIALE — PASSIVO
        # =================================================================
        if entry.section == 'passivo':
            field = _classify_sp_passivo(desc_upper)
            if field == 'depr_sp02':
                depr_sp02 += entry.amount
            elif field == 'depr_sp03':
                depr_sp03 += entry.amount
            elif field == 'deduct_crediti':
                crediti_deduction += entry.amount
            elif field == 'bank_avere':
                bank_avere += entry.amount
            elif field == 'equity_total':
                if entry.level == 2:
                    return  # skip sub2 total, use sub3 components
                # sub3: classify
                if _kw_match(desc_upper, ['CAPITALE']):
                    capitale += entry.amount
                else:
                    riserve += entry.amount
            elif field == 'debt_bank':
                if entry.level in (1, 2):
                    debt_bank_total += entry.amount
            else:
                bs[field] = bs.get(field, Decimal('0')) + entry.amount
            return

        # =================================================================
        # CONTO ECONOMICO — COSTI
        # =================================================================
        if entry.section == 'costi':
            field = _classify_ce_costi(desc_upper)
            if field == 'ce01_return':
                ce01_returns += entry.amount
            elif field == 'ce09a':
                ce09a += entry.amount
            elif field == 'ce09b':
                ce09b += entry.amount
            elif field == 'ce09d':
                ce09d += entry.amount
            elif field == 'ce10':
                ce10_opening += entry.amount
            elif field == 'ce13_cost':
                ce['ce13'] = ce.get('ce13', Decimal('0')) - entry.amount
            elif field:
                ce[field] = ce.get(field, Decimal('0')) + entry.amount
            return

        # =================================================================
        # CONTO ECONOMICO — RICAVI
        # =================================================================
        if entry.section == 'ricavi':
            field = _classify_ce_ricavi(desc_upper)
            if field == 'ce01':
                ce01_total += entry.amount
            elif field == 'ce10_close':
                ce10_closing += entry.amount
            elif field:
                ce[field] = ce.get(field, Decimal('0')) + entry.amount
            return

    # Main processing loop
    for entry in entries:
        desc_upper = entry.description.upper()

        # Section totals
        if entry.level == 3:
            continue  # ignore trial balance section totals

        if entry.level == 4:
            # UTILE DI ESERCIZIO
            if entry.section in ('passivo', 'ricavi'):
                utile_esercizio = entry.amount
            elif entry.section in ('attivo', 'costi'):
                utile_esercizio = -entry.amount
            else:
                utile_esercizio = entry.amount
            continue

        if entry.level >= 5:
            continue

        if not entry.prefix2:
            continue

        # Sub2 entries: always process
        if entry.level == 2:
            _process_category(entry)
            continue

        # Sub3 entries: process only if no sub2 exists for this prefix+section
        if entry.level == 1:
            if (entry.prefix2, entry.section) not in has_sub2:
                _process_category(entry)
                continue
            # Even with sub2 parent, extract equity sub-items and CE TFR
            if entry.section == 'passivo':
                passivo_field = _classify_sp_passivo(desc_upper)
                if passivo_field == 'equity_total':
                    if _kw_match(desc_upper, ['CAPITALE']):
                        capitale += entry.amount
                    else:
                        riserve += entry.amount
                    continue
            if entry.section == 'costi' and ('TFR' in desc_upper or
                    _kw_match(desc_upper, ['TRATTAMENTO', 'FINE', 'RAPPORTO'])):
                ce_tfr_accrual += entry.amount
                continue

        # Detail level: debt entro/oltre classification
        if entry.level == 0 and entry.section == 'passivo':
            # Check if parent is a bank debt category
            if 'ENTRO' in desc_upper:
                debt_bank_entro += entry.amount
            elif 'OLTRE' in desc_upper:
                debt_bank_oltre += entry.amount

    # =====================================================================
    # Build final BS
    # =====================================================================

    # Net gross assets against depreciation
    bs['sp02'] = bs.get('sp02', Decimal('0')) + (gross_sp02 - depr_sp02)
    bs['sp03'] = bs.get('sp03', Decimal('0')) + (gross_sp03 - depr_sp03)

    # Banks
    bs['sp09'] = bs.get('sp09', Decimal('0')) + bank_dare

    # Crediti deduction
    if crediti_deduction > 0:
        bs['sp06'] = bs.get('sp06', Decimal('0')) - crediti_deduction

    # Equity
    bs['sp11'] = capitale
    bs['sp12'] = riserve
    bs['sp13'] = utile_esercizio

    # Debiti v/banche: entro/oltre split
    bs.setdefault('sp16', Decimal('0'))
    bs.setdefault('sp17', Decimal('0'))

    if debt_bank_entro + debt_bank_oltre > 0:
        bs['sp16'] += debt_bank_entro
        bs['sp17'] += debt_bank_oltre
        remainder = debt_bank_total - debt_bank_entro - debt_bank_oltre
        if remainder > 0:
            bs['sp16'] += remainder
    else:
        # No entro/oltre markers → all breve
        bs['sp16'] += debt_bank_total

    # Bank overdrafts → sp16
    bs['sp16'] += bank_avere

    # Defaults
    for i in range(1, 19):
        bs.setdefault(f'sp{i:02d}', Decimal('0'))

    # Recalculate totals from IV CEE values
    bs['totale_attivo'] = sum(bs[f'sp{i:02d}'] for i in range(1, 11))
    bs['totale_passivo'] = sum(bs[f'sp{i:02d}'] for i in range(11, 19))

    # =====================================================================
    # Build final CE
    # =====================================================================

    ce['ce01'] = ce01_total - ce01_returns
    ce['ce10'] = ce10_opening - ce10_closing
    ce['ce08a_tfr_accrual'] = ce_tfr_accrual

    total_amm = ce09a + ce09b + ce09d
    ce['ce09'] = total_amm
    ce['ce09a_ammort_immateriali'] = ce09a
    ce['ce09b_ammort_materiali'] = ce09b
    ce['ce09c_svalutazioni'] = Decimal('0')
    ce['ce09d_svalutazione_crediti'] = ce09d

    # Defaults
    for i in range(1, 21):
        ce.setdefault(f'ce{i:02d}', Decimal('0'))
    for extra in ['ce08a_tfr_accrual', 'ce09a_ammort_immateriali', 'ce09b_ammort_materiali',
                  'ce09c_svalutazioni', 'ce09d_svalutazione_crediti', 'ce11b',
                  'ce13', 'ce14', 'ce16', 'ce17', 'ce18', 'ce19']:
        ce.setdefault(extra, Decimal('0'))

    return bs, ce


def extract_situazione_contabile(file_path: str) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """
    Extract IV CEE data from a Situazione Contabile PDF.

    Returns:
        (balance_sheet_data, income_data) dicts with Decimal values
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise ValueError(f"Cannot open PDF: {e}")

    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    doc.close()

    logger.info("Situazione contabile format detected, using deterministic parser")

    entries = parse_entries(full_text)
    logger.info(f"Parsed {len(entries)} entries from trial balance")

    bs, ce = build_iv_cee(entries)

    logger.info(f"SC parser: sp02={bs.get('sp02')}, sp03={bs.get('sp03')}, sp09={bs.get('sp09')}")
    logger.info(f"SC parser: sp11={bs.get('sp11')}, sp12={bs.get('sp12')}, sp13={bs.get('sp13')}")
    logger.info(f"SC parser: sp16={bs.get('sp16')}, sp17={bs.get('sp17')}")
    logger.info(f"SC parser: ce01={ce.get('ce01')}, ce05={ce.get('ce05')}, ce08={ce.get('ce08')}")
    logger.info(f"SC parser: totale_attivo={bs.get('totale_attivo')}, totale_passivo={bs.get('totale_passivo')}")

    return bs, ce
