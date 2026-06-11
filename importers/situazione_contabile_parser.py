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


def _is_contrapposte_layout(text: str) -> bool:
    """True if ATTIVITA' and PASSIVITA' headers appear adjacently (two physical
    columns side by side), as opposed to a single-column sequential layout."""
    spaced = re.sub(r'\s+', '', text.upper())
    ai = spaced.find('ATTIVITA')
    pi = spaced.find('PASSIVITA')
    if ai < 0 or pi < 0:
        return False
    return abs(pi - ai) <= 40


def is_situazione_contabile(text: str) -> bool:
    """Detect if text is from a Situazione Contabile / trial balance PDF.

    Supports two code formats:
    - DEPI: XX/YY/ZZZ (e.g. 03/05/005)
    - AGO/ERP: 8-digit codes with keywords (e.g. 13065000, 37015000)
    """
    sample = text[:10000]
    # DEPI format: XX/YY/ZZZ codes
    depi_codes = re.findall(r'\b\d{2}/\d{2}/\d{3}\b', sample)
    if len(depi_codes) >= 10:
        # Contrapposte (2 physical columns) DEPI layouts place ATTIVITA' and
        # PASSIVITA' headers adjacently. Our deterministic parser cannot
        # reconcile their sign-based contra items to balance, so defer those to
        # the LLM rather than emit an unbalanced extraction.
        if not _is_contrapposte_layout(sample):
            return True
    # AGO/ERP format: 8-digit codes + "SITUAZIONE PATRIMONIALE" or "BILANCIO DI VERIFICA"
    ago_codes = re.findall(r'\b\d{8}\b', sample)
    if len(ago_codes) >= 5 and re.search(r'SITUAZIONE\s+PATRIMONIALE|BILANCIO\s+DI\s+VERIFICA', sample, re.IGNORECASE):
        return True
    # DEPI 2-part format: XX/YYYY detail + XX/**** subtotals (e.g. 06/0015, 06/****)
    twopart_detail = re.findall(r'\b\d{2}/\d{4}\b', sample)
    twopart_sub = re.findall(r'\b\d{2}/\*{4}', sample)
    if len(twopart_detail) >= 8 and len(twopart_sub) >= 3:
        return True
    # Single-column "Situazione contabile" with 6-digit codes (TeamSystem-like)
    if is_single_column_sc(text):
        return True
    # TeamSystem XX/YYYY/YYYY codes
    if is_teamsystem_sc(text):
        return True
    return False


def is_single_column_sc(text: str) -> bool:
    """Detect single-column "Situazione contabile" trial balances.

    Layout: STATO PATRIMONIALE / CONTO ECONOMICO sections, each with
    ATTIVO/PASSIVO or COSTI/RICAVI header rows, one "Saldo" column, and a
    "TOTALE A PAREGGIO" footer. Account codes are 6-digit (e.g. 120101) with
    optional 8-digit sub-accounts. Used by Italian ERPs (e.g. TeamSystem GIS).
    """
    upper = text.upper()
    # Required structural markers
    if 'SITUAZIONE CONTABILE' not in upper:
        return False
    if 'TOTALE A PAREGGIO' not in upper:
        return False
    if not re.search(r'STATO\s+PATRIMONIALE', upper):
        return False
    # Must NOT be the DEPI XX/YY/ZZZ or 8-digit AGO format
    if len(re.findall(r'\b\d{2}/\d{2}/\d{3}\b', text)) >= 5:
        return False
    # Needs a healthy number of 6-digit account codes
    six_digit = re.findall(r'(?m)^\s*\d{6}\b', text)
    return len(six_digit) >= 10


def is_ago_format(text: str) -> bool:
    """Detect AGO/ERP 8-digit code trial balance format.

    AGO-style PDFs use 8-digit account codes with no dashes (e.g. 13065000)
    and a two-column layout per page (ATTIVITA'/PASSIVITA' side by side).
    """
    sample = text[:10000]
    has_marker = bool(re.search(r'BILANCIO\s+DI\s+VERIFIC', sample, re.IGNORECASE))
    ago_codes = re.findall(r'\b\d{8}\b', sample)
    depi_codes = re.findall(r'\b\d{2}/\d{2}/\d{3}\b', sample)
    return has_marker and len(ago_codes) >= 10 and len(depi_codes) < 5


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
    # AGO-style single-category descriptions (trial balance parent level)
    (['ONERI', 'PLURIENN'], 'gross_sp02'),
    (['COSTI', 'PLURIENN'], 'gross_sp02'),
    (['SOFTWARE'], 'gross_sp02'),
    (['BREVETT'], 'gross_sp02'),
    (['MARCHI'], 'gross_sp02'),
    (['AVVIAMENTO'], 'gross_sp02'),
    (['LICENZ'], 'gross_sp02'),
    (['FABBRICAT'], 'gross_sp03'),
    (['TERREN'], 'gross_sp03'),
    (['MACCHINAR'], 'gross_sp03'),
    (['MACCHINE'], 'gross_sp03'),
    (['IMPIANT'], 'gross_sp03'),
    (['ATTREZZ'], 'gross_sp03'),
    (['AUTOMEZZ'], 'gross_sp03'),
    (['AUTOVEICOL'], 'gross_sp03'),
    (['AUTOVETTUR'], 'gross_sp03'),
    (['MEZZI', 'TRASP'], 'gross_sp03'),
    (['AUTO', 'MOTO'], 'gross_sp03'),
    (['ARREDAMENT'], 'gross_sp03'),
    (['MOBILI'], 'gross_sp03'),
    (['PARTECIPAZ'], 'gross_sp04'),
    # Current assets
    (['RIMANENZE'], 'sp05'),
    (['MAGAZZIN'], 'sp05'),
    (['RATEI', 'RISCONTI', 'ATTIV'], 'sp10'),
    (['RATEI', 'ATTIV'], 'sp10'),
    (['RISCONTI', 'ATTIV'], 'sp10'),
    (['DISPONIBILIT'], 'sp09'),  # Disponibilità liquide (banks + cash)
    (['DEPOSIT', 'BANCAR'], 'sp09'),
    (['DEPOSIT', 'POSTAL'], 'sp09'),
    (['DENARO'], 'sp09'),
    (['CASSA'], 'sp09'),
    # Everything else in attivo = crediti (sp06)
]

# SP PASSIVO keyword rules
_SP_PASSIVO_RULES = [
    # Depreciation funds (will be netted against gross assets)
    # Specific rules first (pluriennali/macchine disambiguate immat vs mat)
    (['F.DO', 'AMM', 'PLURIENN'], 'depr_sp02'),
    (['F.DO', 'AMM', 'IMMAT'], 'depr_sp02'),
    (['F.DO', 'AMM', 'SOFTWARE'], 'depr_sp02'),
    (['F.DO', 'AMM', 'BREVETT'], 'depr_sp02'),
    (['F.DO', 'AMM', 'MARCHI'], 'depr_sp02'),
    (['F.DO', 'AMM', 'AVVIAMENTO'], 'depr_sp02'),
    (['F.DO', 'AMM', 'MACCHINE'], 'depr_sp03'),
    (['F.DO', 'AMM', 'MACCHINAR'], 'depr_sp03'),
    (['F.DO', 'AMM', 'IMPIANT'], 'depr_sp03'),
    (['F.DO', 'AMM', 'ATTREZZ'], 'depr_sp03'),
    (['F.DO', 'AMM', 'AUTO'], 'depr_sp03'),
    (['F.DO', 'AMM', 'FABBRICAT'], 'depr_sp03'),
    (['F.DO', 'AMM', 'MATER'], 'depr_sp03'),
    (['F/AMM', 'IMMAT'], 'depr_sp02'),
    (['F/AMM', 'MATER'], 'depr_sp03'),
    (['AMMORTAM', 'IMMAT'], 'depr_sp02'),
    (['AMMORTAM', 'MATER'], 'depr_sp03'),
    (['F.DO', 'AMM'], 'depr_sp03'),  # fallback → tangible
    # Crediti deduction
    (['F.DO', 'SVAL', 'CREDITI'], 'deduct_crediti'),
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
    (['UTILI', 'NUOVO'], 'equity_total'),
    (['PERDITE', 'PORTATE'], 'equity_total'),
    (['SOVRAPPREZZO'], 'equity_total'),
    # Fondi
    (['FONDI', 'RISCHI'], 'sp14'),
    (['FONDI', 'ONERI'], 'sp14'),
    (['FONDO', 'RISCHI'], 'sp14'),
    (['FONDO', 'ONERI'], 'sp14'),
    # TFR
    (['TFR'], 'sp15'),
    (['T.F.R'], 'sp15'),
    (['TRATTAMENTO', 'FINE', 'RAPPORTO'], 'sp15'),
    # Debiti v/banche (need entro/oltre split — from details OR from "(EE)"/"(OE)" suffix)
    (['DEBITI', 'BANCH'], 'debt_bank'),
    (['DEBITI', 'FINANZIAT'], 'debt_bank'),
    (['MUTUI'], 'debt_bank'),
    (['OBBLIGAZION'], 'debt_bank'),
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
    (['ISTIT', 'PREV'], 'sp16'),
    # Specific debt categories → sp16 (breve by default)
    (['DEBITI', 'FORNITOR'], 'sp16'),
    (['ACCONTI'], 'sp16'),
    (['ALTRI DEBITI'], 'sp16'),
    (['ALTRI', 'DEBITI'], 'sp16'),
    # SBF / crediti ceduti in passivo → sp16 (only when explicitly labeled as ceded)
    (['CREDITI', 'CEDUT'], 'sp16'),
    (['CREDITI', 'SMOBIL'], 'sp16'),
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
    # Personale sub-fields (more specific than the generic 'PERSONALE' bucket)
    (['QUOTE', 'FINE', 'RAPPORTO'], 'ce08a_tfr'),
    (['QUOTE', 'TRATTAMENTO'], 'ce08a_tfr'),
    (['QUOTE', 'TFR'], 'ce08a_tfr'),
    (['ACCANTON', 'TFR'], 'ce08a_tfr'),
    (['TRATT', 'FINE', 'RAPPORTO'], 'ce08a_tfr'),
    (['SALARI'], 'ce08b'),
    (['STIPENDI'], 'ce08b'),
    (['ONERI', 'SOCIAL'], 'ce08c'),
    (['ONERI', 'PREVIDENZ'], 'ce08c'),
    (['ALTRI', 'COSTI', 'PERSONALE'], 'ce08d'),
    (['PERSONALE'], 'ce08'),
    # Ammortamenti (more specific keywords first)
    (['AMMORTAM', 'IMMAT'], 'ce09a'),
    (['AMM.TO', 'IMMAT'], 'ce09a'),
    (['AMM.T', 'IMM. IMMAT'], 'ce09a'),
    (['AMM.TI', 'IMMAT'], 'ce09a'),
    (['AMMORTAM', 'MATER'], 'ce09b'),
    (['AMM.TO', 'MATER'], 'ce09b'),
    (['AMM.T', 'IMM. MAT'], 'ce09b'),
    (['AMM.TO', 'MAT'], 'ce09b'),
    (['SVALUT'], 'ce09d'),  # Svalutazioni
    (['ACCANTONAM', 'RISCHI'], 'ce11'),
    (['ALTRI ACCANTONAM'], 'ce11b'),
    (['ONERI DIVERSI'], 'ce12'),
    (['ONERI', 'DIVERSI', 'GESTIONE'], 'ce12'),
    (['INTERESSI'], 'ce15'),
    (['ONERI', 'FINANZ'], 'ce15'),
    (['ON.FIN'], 'ce15'),
    (['INT. PASS'], 'ce15'),
    (['IMPOSTE', 'REDDITO'], 'ce20'),
    (['IMPOSTE', 'ESERC'], 'ce20'),
    (['IMPOSTE', 'ANTICIP'], 'ce20'),
    (['IMPOSTE', 'DIFFER'], 'ce20'),
    (['IRES'], 'ce20'),
    (['IRAP'], 'ce20'),
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


def build_iv_cee(entries: List[Entry], default_ce: bool = False) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Map trial balance entries to IV CEE sp01-sp18 and ce01-ce20 fields.

    When default_ce is True (detail-level trial balances where CE lines rarely
    contain category keywords), unmatched ricavi lines default to ce01 and
    unmatched costi lines to ce12, so the P&L is captured rather than dropped.
    """
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

    # Track which prefixes have sub2 (level 2) and sub3 (level 1) entries
    has_sub2: set = set()
    has_sub3: set = set()
    for entry in entries:
        if entry.level == 2:
            has_sub2.add((entry.prefix2, entry.section))
        elif entry.level == 1:
            has_sub3.add((entry.prefix2, entry.section))

    # Track which sections expose any subtotal (level 1 or 2). For "flat" trial
    # balances that contain ONLY level-0 detail lines (no XX/YY/*** or XX/**/***
    # subtotals), we must process the detail lines directly, classifying each by
    # description, otherwise the whole section would be dropped.
    sections_with_subtotals: set = set()
    for entry in entries:
        if entry.level in (1, 2) and entry.section:
            sections_with_subtotals.add(entry.section)

    def _process_category(entry: Entry) -> None:
        """Process a sub2 or standalone sub3 entry through keyword classification."""
        nonlocal gross_sp02, gross_sp03, depr_sp02, depr_sp03
        nonlocal bank_dare, bank_avere, crediti_deduction, capitale, riserve
        nonlocal debt_bank_total, debt_bank_entro, debt_bank_oltre
        nonlocal ce09a, ce09b, ce09d, ce_tfr_accrual
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
                    return  # skip sub2 total (DEPI); AGO emits only level=1
                # Current-year utile/perdita is set from the level-4 pareggio plug;
                # skip parent-level entries to avoid double-counting
                if (_kw_match(desc_upper, ['UTILE', 'ESERCIZ']) or
                        _kw_match(desc_upper, ['PERDITA', 'ESERCIZ'])):
                    if not _kw_any(desc_upper, ['PORTATI', 'PRECEDENT', 'NUOVO']):
                        return
                if _kw_match(desc_upper, ['CAPITALE']):
                    capitale += entry.amount
                else:
                    riserve += entry.amount
            elif field == 'debt_bank':
                if entry.level in (0, 1, 2):
                    # Parent/detail (EE)/(OE) routing: AGO suffix convention,
                    # plus DEPI flat-balance ENTRO/OLTRE in the description.
                    if '(OE)' in desc_upper or 'OLTRE' in desc_upper:
                        debt_bank_oltre += entry.amount
                        debt_bank_total += entry.amount
                    elif '(EE)' in desc_upper or 'ENTRO' in desc_upper:
                        debt_bank_entro += entry.amount
                        debt_bank_total += entry.amount
                    else:
                        debt_bank_total += entry.amount
            elif field == 'sp16':
                # Non-bank debts with (OE) suffix → long-term (sp17)
                if '(OE)' in desc_upper or 'OLTRE' in desc_upper:
                    bs['sp17'] = bs.get('sp17', Decimal('0')) + entry.amount
                else:
                    bs['sp16'] = bs.get('sp16', Decimal('0')) + entry.amount
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
            elif field == 'ce08a_tfr':
                ce_tfr_accrual += entry.amount
                ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
            elif field == 'ce08b':
                ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
                ce['ce08b_salari_stipendi'] = ce.get('ce08b_salari_stipendi', Decimal('0')) + entry.amount
            elif field == 'ce08c':
                ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
                ce['ce08c_oneri_sociali'] = ce.get('ce08c_oneri_sociali', Decimal('0')) + entry.amount
            elif field == 'ce08d':
                ce['ce08'] = ce.get('ce08', Decimal('0')) + entry.amount
                ce['ce08d_altri_costi_personale'] = ce.get('ce08d_altri_costi_personale', Decimal('0')) + entry.amount
            elif field == 'ce13_cost':
                ce['ce13'] = ce.get('ce13', Decimal('0')) - entry.amount
            elif field:
                ce[field] = ce.get(field, Decimal('0')) + entry.amount
            elif default_ce:
                # Detail-level cost line with no keyword match → oneri diversi.
                ce['ce12'] = ce.get('ce12', Decimal('0')) + entry.amount
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
            elif default_ce:
                # Detail-level revenue line with no keyword match → ricavi vendite.
                ce01_total += entry.amount
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

        # Flat trial balance: a section with NO subtotals (only level-0 detail).
        # Classify each detail line by description directly.
        if entry.level == 0 and entry.section and entry.section not in sections_with_subtotals:
            _process_category(entry)
            continue

        # Equity exposed only at detail level (level 0) under a level-2 total
        # (XX/****), which is skipped for equity. Extract here when there is a
        # sub2 parent but no intervening level-1 entry for this prefix+section.
        if (entry.level == 0 and entry.section == 'passivo'
                and (entry.prefix2, entry.section) in has_sub2
                and (entry.prefix2, entry.section) not in has_sub3):
            if _classify_sp_passivo(desc_upper) == 'equity_total':
                if (_kw_match(desc_upper, ['UTILE', 'ESERCIZ']) or
                        _kw_match(desc_upper, ['PERDITA', 'ESERCIZ']) or
                        _kw_match(desc_upper, ['RISULTATO', 'ESERCIZ'])):
                    if not _kw_any(desc_upper, ['PORTATI', 'PRECEDENT', 'NUOVO', 'PORTATE']):
                        continue
                if _kw_match(desc_upper, ['CAPITALE']):
                    capitale += entry.amount
                else:
                    riserve += entry.amount
                continue

        # Orphan detail lines: a level-0 entry whose prefix has NO subtotal
        # (neither XX/YY/*** nor XX/**/*** nor XX/****) in this section. The
        # parent total would otherwise carry it, so process it directly to
        # avoid dropping it. Guarded by has_sub2/has_sub3 to prevent
        # double-counting where a real subtotal exists.
        if (entry.level == 0
                and (entry.prefix2, entry.section) not in has_sub2
                and (entry.prefix2, entry.section) not in has_sub3):
            if entry.section == 'passivo':
                passivo_field = _classify_sp_passivo(desc_upper)
                if passivo_field == 'equity_total':
                    if (_kw_match(desc_upper, ['UTILE', 'ESERCIZ']) or
                            _kw_match(desc_upper, ['PERDITA', 'ESERCIZ']) or
                            _kw_match(desc_upper, ['RISULTATO', 'ESERCIZ'])):
                        if not _kw_any(desc_upper, ['PORTATI', 'PRECEDENT', 'NUOVO', 'PORTATE']):
                            continue
                    if _kw_match(desc_upper, ['CAPITALE']):
                        capitale += entry.amount
                    else:
                        riserve += entry.amount
                    continue
            _process_category(entry)
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


def _c8_parse_side(words, lo: float, hi: float) -> List[Entry]:
    """Parse one column (words whose split-axis coordinate is in (lo, hi])."""
    from collections import defaultdict
    rows: Dict[int, list] = defaultdict(list)
    for w in words:
        if lo < w[1] <= hi:
            rows[round(w[0])].append(w)
    toks: List[str] = []
    for x in sorted(rows):
        rows[x].sort(key=lambda w: -w[1])  # rotated reading order (top→bottom)
        toks.extend(w[4] for w in rows[x])

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


def parse_entries_contrapposte_8digit(file_path: str) -> List[Entry]:
    """Parse a contrapposte 8-digit trial balance using word coordinates."""
    doc = fitz.open(file_path)
    entries: List[Entry] = []
    declared_utile = None
    declared_perdita = False
    declared_attivo = Decimal('0')
    declared_passivo = Decimal('0')

    for page in doc:
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
        mid = (ly + ry_) / 2
        # left column = higher coordinate on the split axis (rotated page)
        left = _c8_parse_side(words, mid, 1e9)
        right = _c8_parse_side(words, -1e9, mid)
        for e in left:
            e.section = left_sec
        for e in right:
            e.section = right_sec
        entries.extend(left)
        entries.extend(right)

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
                                     amount=amount, level=1, section=section))
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


def _be_norm(code: str) -> str:
    """Normalise a (possibly multi-token) account code to a digit string."""
    return re.sub(r'\D', '', code)


def _be_split(words) -> Optional[float]:
    """Find the column gutter = start of the right-hand code cluster.

    Left/right account codes form two well-separated x clusters; left-column
    amounts always fall left of the right column's codes, so the right cluster's
    minimum x is the safe split point for assigning whole rows to a side.
    """
    xs = sorted((w[0] + w[2]) / 2 for w in words
                if re.match(r'^\d', w[4]) and not _BE_AMT_RE.match(w[4]))
    if len(xs) < 6:
        return None
    best_gap, best_i = 0.0, -1
    for i in range(len(xs) - 1):
        gap = xs[i + 1] - xs[i]
        # require a real cluster on each side of the candidate gutter
        if gap > best_gap and (i + 1) >= 3 and (len(xs) - i - 1) >= 3:
            best_gap, best_i = gap, i
    if best_i < 0 or best_gap < 25:
        return None
    return xs[best_i + 1] - 1.0


def _be_collect_side(words, lo: float, hi: float) -> List[Tuple[str, str, Decimal]]:
    """Reconstruct (norm_code, desc_upper, amount) rows in x-band [lo, hi)."""
    from collections import defaultdict
    rows: Dict[int, list] = defaultdict(list)
    for w in words:
        cx = (w[0] + w[2]) / 2
        if lo <= cx < hi:
            rows[round(w[1] / 2.0)].append(w)
    out = []
    for y in sorted(rows):
        toks = [w[4] for w in sorted(rows[y], key=lambda w: w[0])]
        i, code_toks = 0, []
        while i < len(toks) and re.match(r'^[\d./]+$', toks[i]) and not _BE_AMT_RE.match(toks[i]):
            code_toks.append(toks[i])
            i += 1
        if not code_toks:
            continue
        code = _be_norm(''.join(code_toks))
        if not code:
            continue
        rest = toks[i:]
        amts = [_parse_amount(t) for t in rest if _BE_AMT_RE.match(t)]
        if not amts:
            continue
        desc = ' '.join(t for t in rest if not _BE_AMT_RE.match(t)).upper().strip()
        out.append((code, desc, amts[-1]))
    return out


def _be_reclassify(items: List[Tuple[str, str, Decimal]], classify) -> List[Tuple[str, Decimal]]:
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

    info = {}
    for c, d, a in rows:
        info[c] = (d, a)            # last occurrence wins for a repeated code
    uniq = list(info.keys())

    def direct_children(c):
        desc = [o for o in uniq if o != c and len(o) > len(c) and o.startswith(c)]
        return [x for x in desc
                if not any(y != x and len(y) < len(x) and x.startswith(y) for y in desc)]

    roots = [c for c in uniq
             if not any(o != c and len(c) > len(o) and c.startswith(o) for o in uniq)]

    out: List[Tuple[str, Decimal]] = []

    def rec(c):
        d, a = info[c]
        field, specific = classify(d)
        if specific:
            out.append((field, a))
            return
        ch = direct_children(c)
        if ch:
            for x in ch:
                rec(x)
        else:
            out.append((field, a))

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


def extract_contrapposte_best_effort(file_path: str) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Best-effort extraction of a 2-column contrapposte trial balance.

    Balances to the declared totals; any residual from imperfect parsing is
    plugged into sp09 and a 'BILANCIO NON QUADRATO' warning is logged so the
    user can correct it via the Rettifiche journal.
    """
    doc = fitz.open(file_path)
    attivo: List[Tuple[str, str, Decimal]] = []
    passivo: List[Tuple[str, str, Decimal]] = []
    costi: List[Tuple[str, str, Decimal]] = []
    ricavi: List[Tuple[str, str, Decimal]] = []
    full = ""

    for page in doc:
        ptext = page.get_text()
        full += ptext + "\n"
        up = ptext.upper()
        flat = up.replace(' ', '')
        # Classify the page by its FIRST section title line — a single page may
        # carry a subtitle naming both ("Stato Patrimoniale e Conto Economico"),
        # so the title line that comes first decides.
        title = ''
        for l in ptext.split('\n'):
            lu = l.strip().upper()
            if 'PATRIMONIAL' in lu or 'ECONOMIC' in lu:
                title = lu
                break
        if 'PATRIMONIAL' in title and 'ECONOMIC' not in title:
            is_sp, is_ce = True, False
        elif 'ECONOMIC' in title and 'PATRIMONIAL' not in title:
            is_sp, is_ce = False, True
        else:
            is_sp = ('PATRIMONIALE' in flat) or ('ATTIVIT' in up and 'PASSIVIT' in up and 'CONTOECONOMICO' not in flat)
            is_ce = ('CONTOECONOMICO' in flat) or ('COSTI' in up and 'RICAVI' in up)
        words = page.get_text('words')
        if not words:
            continue
        split = _be_split(words)
        if split is None:
            split = page.rect.width / 2
        left = _be_collect_side(words, -1e9, split)
        right = _be_collect_side(words, split, 1e9)
        if is_sp and not is_ce:
            attivo += left
            passivo += right
        elif is_ce and not is_sp:
            # left=costi, right=ricavi (typical); swap if headers say otherwise
            if 'RICAVI' in up[:400] and up[:400].find('RICAVI') < up[:400].find('COSTI') if 'COSTI' in up[:400] else False:
                costi += right
                ricavi += left
            else:
                costi += left
                ricavi += right

    doc.close()

    Z = Decimal('0')
    bs: Dict[str, Decimal] = {}
    ce: Dict[str, Decimal] = {}

    def add(d, k, v):
        d[k] = d.get(k, Z) + v

    # Classifiers map a mastro/subtotal DESCRIPTION to an IV-CEE field; the second
    # element flags whether the match is specific enough to stop descending.
    def cl_att(d):
        f = _classify_sp_attivo(d)
        f = {'gross_sp02': 'sp02', 'gross_sp03': 'sp03', 'gross_sp04': 'sp04'}.get(f, f)
        return f, f != 'sp06'

    def cl_pas(d):
        tag = _classify_sp_passivo(d)
        if tag == 'equity_total':
            if _kw_match(d, ['CAPITALE']):
                return 'sp11', True
            return 'sp12', True
        return tag, tag != 'sp16'

    def cl_cos(d):
        f = _classify_ce_costi(d)
        return (f, True) if f else ('ce12', False)

    def cl_ric(d):
        f = _classify_ce_ricavi(d)
        return (f, True) if f else ('ce04', False)

    # The current-year result is a pareggio item (utile booked on the passivo
    # side, perdita on the attivo side). Strip it from both columns so it is not
    # double-counted as a credit/asset; its signed value becomes sp13.
    result = [Z]

    def _strip_result(side):
        keep = []
        for c, d, a in side:
            if ('ESERCIZ' in d and ('UTILE' in d or 'PERDITA' in d or 'RISULTAT' in d)
                    and not _kw_any(d, ['PORTAT', 'PORTATE', 'NUOVO', 'PRECEDENT'])):
                result[0] += (-a if 'PERDITA' in d else a)
                continue
            keep.append((c, d, a))
        return keep

    attivo = _strip_result(attivo)
    passivo = _strip_result(passivo)

    # --- Attivo (gross assets; fondi netted from passivo side) ---
    for field, amt in _be_reclassify(attivo, cl_att):
        add(bs, field, amt)

    # --- Passivo (equity / debts / contra-asset funds) ---
    for tag, amt in _be_reclassify(passivo, cl_pas):
        if tag in ('depr_sp02', 'depr_sp03', 'depr_sp04'):
            add(bs, tag.replace('depr_', ''), -amt)        # net fondi off the asset
        elif tag == 'deduct_crediti':
            add(bs, 'sp06', -amt)
        elif tag in ('sp11', 'sp12', 'sp14', 'sp15', 'sp18'):
            add(bs, tag, amt)
        else:                                              # bank_avere / debt_bank / sp16 default
            add(bs, 'sp16', amt)

    # --- CE ---
    def ce_add(tag, amt):
        if tag == 'ce01_return':
            add(ce, 'ce01', -amt)
        elif tag == 'ce10_close':
            add(ce, 'ce10', -amt)
        elif tag == 'ce13_cost':
            add(ce, 'ce15', amt)
        else:
            add(ce, tag, amt)
    for tag, amt in _be_reclassify(costi, cl_cos):
        ce_add(tag, amt)
    for tag, amt in _be_reclassify(ricavi, cl_ric):
        ce_add(tag, amt)

    # --- Declared totals & current-year result ---
    up1 = re.sub(r'\s+', ' ', full.upper())
    tot_att = _be_amount(up1.split('TOTALE ATTIV', 1)[1][:40]) if 'TOTALE ATTIV' in up1 else None
    tot_pas = _be_amount(up1.split('TOTALE PASSIV', 1)[1][:40]) if 'TOTALE PASSIV' in up1 else None
    pareggio = _be_amount(up1.split('TOTALE A PAREGGIO', 1)[1][:40]) if 'TOTALE A PAREGGIO' in up1 else None

    if tot_att is not None and tot_pas is not None:
        utile = tot_att - tot_pas                          # +utile / -perdita from section gap
    else:
        utile = result[0]                                  # fallback: booked result line
    bs['sp13'] = utile

    # Trial-balance pareggio total; the IV-CEE total removes the perdita that is
    # parked on the attivo side as a balancing item.
    tb_total = pareggio
    if tb_total is None and tot_att is not None and tot_pas is not None:
        tb_total = max(tot_att, tot_pas)
    if tb_total is None:
        tb_total = tot_att or tot_pas

    if tb_total:
        iv_total = tb_total - (abs(utile) if utile < 0 else Z)
        att_sum = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)
        res_a = iv_total - att_sum
        add(bs, 'sp09', res_a)
        pas_sum = sum((bs.get(k, Z) for k in _PASSIVO_KEYS), Z)
        res_p = iv_total - pas_sum
        add(bs, 'sp16', res_p)
        bs['totale_attivo'] = iv_total
        bs['totale_passivo'] = iv_total
        worst = max(abs(res_a), abs(res_p))
        if worst > Decimal('1'):
            logger.warning(
                f"BILANCIO NON QUADRATO (contrapposte best-effort): residuo attivo={res_a}, "
                f"passivo={res_p} plug in sp09/sp16 — verificare in Rettifiche"
            )
    else:
        # No reliable declared total (e.g. code-less footer): anchor to the larger
        # classified side and plug the other so the import balances (best-effort);
        # the gap is flagged for manual correction in Rettifiche.
        att_sum = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)
        pas_sum = sum((bs.get(k, Z) for k in _PASSIVO_KEYS), Z)
        iv_total = max(att_sum, pas_sum)
        add(bs, 'sp09', iv_total - att_sum)
        add(bs, 'sp16', iv_total - pas_sum)
        bs['totale_attivo'] = iv_total
        bs['totale_passivo'] = iv_total
        if abs(att_sum - pas_sum) > Decimal('1'):
            logger.warning(
                f"BILANCIO NON QUADRATO (contrapposte best-effort): totali dichiarati non "
                f"trovati, ancorato a {iv_total} (plug {abs(att_sum - pas_sum)}) — verificare in Rettifiche"
            )

    return bs, ce


_ATTIVO_KEYS = ['sp01', 'sp02', 'sp03', 'sp04', 'sp05', 'sp06', 'sp07', 'sp08', 'sp09', 'sp10']
_PASSIVO_KEYS = ['sp11', 'sp12', 'sp13', 'sp14', 'sp15', 'sp16', 'sp17', 'sp18']


def _attivo_key(k: str) -> bool:
    return k in _ATTIVO_KEYS


def extract_situazione_contabile(file_path: str) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """
    Extract IV CEE data from a Situazione Contabile PDF.

    Routes AGO-style (8-digit codes, 2-column layout) to the AGO parser,
    otherwise falls back to the DEPI parser (XX/YY/ZZZ codes).

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

    default_ce = False
    if is_ago_format(full_text):
        logger.info("AGO/ERP format detected, using block-based parser")
        entries, totali = parse_entries_ago(file_path)
        logger.info(f"AGO parser: {len(entries)} parent entries, totali={totali}")
    elif is_contrapposte_8digit(full_text):
        logger.info("Contrapposte 8-digit detected, using coordinate-based parser")
        entries = parse_entries_contrapposte_8digit(file_path)
        default_ce = True
        logger.info(f"Contrapposte parser: {len(entries)} entries")
    elif is_teamsystem_sc(full_text):
        logger.info("TeamSystem situazione contabile detected, using TeamSystem parser")
        entries = parse_entries_teamsystem(full_text)
        default_ce = True
        logger.info(f"TeamSystem parser: {len(entries)} entries")
    elif is_single_column_sc(full_text):
        logger.info("Single-column situazione contabile detected, using single-column parser")
        entries = parse_entries_single_column(full_text)
        default_ce = True
        logger.info(f"Single-column parser: {len(entries)} entries")
    elif not is_situazione_contabile(full_text) and is_contrapposte_file(file_path):
        # Last-resort: an unrecognised 2-physical-column dump (the structured
        # DEPI/single-column/TeamSystem parsers above handle the known schemes).
        logger.info("Generic 2-column contrapposte detected, using best-effort parser")
        return extract_contrapposte_best_effort(file_path)
    else:
        logger.info("DEPI format detected, using text-based parser")
        entries = parse_entries(full_text)
        logger.info(f"DEPI parser: {len(entries)} entries")

    bs, ce = build_iv_cee(entries, default_ce=default_ce)

    logger.info(f"SC parser: sp02={bs.get('sp02')}, sp03={bs.get('sp03')}, sp09={bs.get('sp09')}")
    logger.info(f"SC parser: sp11={bs.get('sp11')}, sp12={bs.get('sp12')}, sp13={bs.get('sp13')}")
    logger.info(f"SC parser: sp16={bs.get('sp16')}, sp17={bs.get('sp17')}")
    logger.info(f"SC parser: ce01={ce.get('ce01')}, ce05={ce.get('ce05')}, ce08={ce.get('ce08')}")
    logger.info(f"SC parser: totale_attivo={bs.get('totale_attivo')}, totale_passivo={bs.get('totale_passivo')}")

    return bs, ce
