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
    sample = text[:10000]
    # DEPI format: XX/YY/ZZZ codes
    depi_codes = re.findall(r'\b\d{2}/\d{2}/\d{3}\b', sample)
    if len(depi_codes) >= 10:
        return True
    # AGO/ERP format: 8-digit codes + "SITUAZIONE PATRIMONIALE" or "BILANCIO DI VERIFICA"
    ago_codes = re.findall(r'\b\d{8}\b', sample)
    if len(ago_codes) >= 5 and re.search(r'SITUAZIONE\s+PATRIMONIALE|BILANCIO\s+DI\s+VERIFICA', sample, re.IGNORECASE):
        return True
    return False


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
                if entry.level in (1, 2):
                    # Parent-level (EE)/(OE) routing: AGO suffix convention
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

    if is_ago_format(full_text):
        logger.info("AGO/ERP format detected, using block-based parser")
        entries, totali = parse_entries_ago(file_path)
        logger.info(f"AGO parser: {len(entries)} parent entries, totali={totali}")
    else:
        logger.info("DEPI format detected, using text-based parser")
        entries = parse_entries(full_text)
        logger.info(f"DEPI parser: {len(entries)} entries")

    bs, ce = build_iv_cee(entries)

    logger.info(f"SC parser: sp02={bs.get('sp02')}, sp03={bs.get('sp03')}, sp09={bs.get('sp09')}")
    logger.info(f"SC parser: sp11={bs.get('sp11')}, sp12={bs.get('sp12')}, sp13={bs.get('sp13')}")
    logger.info(f"SC parser: sp16={bs.get('sp16')}, sp17={bs.get('sp17')}")
    logger.info(f"SC parser: ce01={ce.get('ce01')}, ce05={ce.get('ce05')}, ce08={ce.get('ce08')}")
    logger.info(f"SC parser: totale_attivo={bs.get('totale_attivo')}, totale_passivo={bs.get('totale_passivo')}")

    return bs, ce
