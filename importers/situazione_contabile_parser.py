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
import os
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from functools import lru_cache, partial
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

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
    amount_prior: Decimal = Decimal('0')  # prior-year column (dual-year trial balances)

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
    # Immobilizzazioni in corso e acconti (B.II.5 / B.I.6) — a LEGITIMATE fixed
    # asset. Must precede the ANTICIP rule below so a real immob. acconto is not
    # demoted to a credit.
    (['IMMOBILIZZAZIONI', 'CORSO'], 'gross_sp03'),
    (['IMMOBILIZZAZIONI', 'ACCONT'], 'gross_sp03'),
    # Credits explicitly labelled as immobilised belong to B.III even when the
    # account number is gestionale-specific (AGO: "Crediti v/altri (EE-immob.)").
    (['CREDITI', 'IMMOB'], 'gross_sp04'),
    # An advance on a CANONE / lease ("ANTICIPO X CANONI MACCHINARI") is a credit,
    # not the machine — must precede the MACCHINAR category rule. Narrow to CANON on
    # purpose: a blanket ANTICIP rule would (a) demote a genuine acconto to PURCHASE
    # a cespite ("ANTICIPI SU MACCHINARI" = B.II.5 immobilizzazione) to crediti, and
    # (b) leak into _semantic_section_from_desc, mis-guessing customer advances
    # ("CLIENTI C/ANTICIPI" = a liability) onto the asset side. Generic supplier
    # advances ("ANTICIPI A FORNITORI") already fall to the sp06 default below.
    (['ANTICIP', 'CANON'], 'sp06'),
    # AGO-style single-category descriptions (trial balance parent level)
    (['ONERI', 'PLURIENN'], 'gross_sp02'),
    (['COSTI', 'PLURIENN'], 'gross_sp02'),
    (['COSTI', 'IMPIANTO'], 'gross_sp02'),
    (['COSTI', 'AMPLIAMENT'], 'gross_sp02'),   # B.I.1 e' "costi di impianto E DI AMPLIAMENTO"
    (['SOFTWARE'], 'gross_sp02'),
    (['BREVETT'], 'gross_sp02'),
    (['MARCHI'], 'gross_sp02'),
    (['AVVIAMENTO'], 'gross_sp02'),
    (['LICENZ'], 'gross_sp02'),
    # B.I.7 "costi su beni di terzi" (migliorie/lavori su beni non di proprieta').
    # Il repo lo tratta gia' come IMMATERIALE sul lato fondo (regola F.DO+AMM+MANUT
    # "spese di manut.beni di ter(zi)"); senza la regola simmetrica qui il cespite
    # finiva nei crediti mentre il suo fondo nettava le immobilizzazioni MATERIALI
    # (budget_281: 4.500,00 in sp06 e 2.471,86 sottratti a sp03).
    (['BENI DI TERZ'], 'gross_sp02'),
    (['FABBRICAT'], 'gross_sp03'),
    (['TERREN'], 'gross_sp03'),
    (['MACCHINAR'], 'gross_sp03'),
    (['MACCHINE'], 'gross_sp03'),
    (['IMPIANT'], 'gross_sp03'),
    # 'ATTREZ' e non 'ATTREZZ': "ATTREZ." compare troncato nelle stampe a colonna
    # stretta. Allargamento per PREFISSO, quindi additivo (ogni ATTREZZ contiene ATTREZ).
    (['ATTREZ'], 'gross_sp03'),
    (['ATTR', 'MINUT'], 'gross_sp03'),   # "ATTR.VARIE E MINUTE (<516,46 E.)"
    # Categorie di cespite gia' riconosciute lato FONDO (_FONDO_CATEGORY_KW) ma
    # assenti qui: il fondo nettava sp03 mentre il suo cespite finiva nei crediti.
    (['TELEFON'], 'gross_sp03'),
    (['AUTOMEZZ'], 'gross_sp03'),
    (['AUTOVEICOL'], 'gross_sp03'),
    (['AUTOVETTUR'], 'gross_sp03'),
    (['MEZZI', 'TRASP'], 'gross_sp03'),
    (['AUTO', 'MOTO'], 'gross_sp03'),
    (['ARREDAMENT'], 'gross_sp03'),
    (['MOBILI'], 'gross_sp03'),
    (['ALTRI', 'BENI', 'MATERIAL'], 'gross_sp03'),
    (['PARTECIPAZ'], 'gross_sp04'),
    # Current assets
    (['RIMANENZE'], 'sp05'),
    (['MAGAZZIN'], 'sp05'),
    # Common trial-balance abbreviation: "Rim. mat. prime, sussid. e consumo".
    (['RIM', 'MAT', 'PRIM'], 'sp05'),
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
    # B.1 funds are not depreciation contra-accounts.  Keep these before every
    # AMM rule: "amministratori" contains the substring "AMM" and previously
    # made a fondo fine-mandato look like a tangible depreciation fund.
    (['QUIESCENZA'], 'sp14'),
    (['INDENNIT', 'MANDATO'], 'sp14'),
    # Depreciation funds (will be netted against gross assets)
    # Specific rules first (pluriennali/macchine disambiguate immat vs mat)
    (['F.DO', 'AMM', 'PLURIENN'], 'depr_sp02'),
    (['F.DO', 'AMM', 'IMMAT'], 'depr_sp02'),
    (['F.DO', 'AMM', 'SOFTWARE'], 'depr_sp02'),
    (['F.DO', 'AMM', 'BREVETT'], 'depr_sp02'),
    (['F.DO', 'AMM', 'MARCHI'], 'depr_sp02'),
    (['F.DO', 'AMM', 'AVVIAMENTO'], 'depr_sp02'),
    # Truncated gestionale captions (budget_343/348, Bilancino 31-5-26): the
    # column clips the description, so the canonical keywords above never fire
    # and the fondo fell through to the tangible fallback.
    (['F.DO', 'AMM', 'SW'], 'depr_sp02'),                  # "F.do amm.sw in concessione capitalizz"
    (['F.DO', 'AMM', 'COSTI DI IMPIANTO'], 'depr_sp02'),   # B.I.1, before the IMPIANT→sp03 rule
    (['F.DO', 'AMM', "COSTI D'IMPIANTO"], 'depr_sp02'),
    (['F.DO', 'AMM', 'AMPLIAMENT'], 'depr_sp02'),          # idem B.I.1 (budget_158 CONA)
    (['F.DO', 'AMM', 'MANUT'], 'depr_sp02'),               # "spese di manut.beni di ter(zi)" B.I.7
    (['F.DO', 'AMM', 'BENI DI TERZ'], 'depr_sp02'),        # idem, grafia "lav. str. su beni di terzi"
    (['F.DO', 'AMM', 'LICENZE'], 'depr_sp02'),
    (['FOND', 'AMM', 'IMMOBILIZZAZ. IMM'], 'depr_sp02'),   # mastro "FONDI AMMORT. IMMOBILIZZAZ. IMM"
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
    # "FONDI/FONDO AMM.TO IMMOB. (IM)MATERIALI" — no 'F.DO' token, 'AMM.TO' not 'AMMORTAM'
    # (BILAGRA "BILANCIO DI VERIFICA", e.g. AITEC). IMMAT must precede MATER because
    # "IMMATERIALI" also contains the "MATER" substring.
    (['FOND', 'AMM', 'IMMAT'], 'depr_sp02'),
    (['FOND', 'AMM', 'MATER'], 'depr_sp03'),
    # Safe tangible fallback.  Do not use bare "AMM": it also matches words
    # such as AMMINISTRATORI.  Real depreciation captions use AMM. / AMM.TO or
    # the full AMMORT... stem; asset-specific cases were handled above.
    (['F.DO', 'AMM.'], 'depr_sp03'),
    (['F.DO', 'AMMORT'], 'depr_sp03'),
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


# Testa della dicitura "fondo ammortamento" in TUTTE le grafie reali dei gestionali:
# `F.DO AMM.TO`, `F/AMM.`, `FDO AMM`, `FONDO AMMORTAMENTO`, `F.DI AMMOR.TO`...
# Ancorata a inizio riga perche' i conti di fondo esordiscono sempre con la dicitura.
_FONDO_AMM_HEAD_RE = re.compile(
    r"^\s*(?:F\s*[./]\s*D[OI]|FD[OI]|FOND[OI]|F)\s*[./]?\s*"
    r"AMM(?:ORT\w*|\.?\s*TO|\.?\s*NTO)?\s*[./]?\s*"
)

# Forma canonica contro cui e' scritta l'intera tabella `_SP_PASSIVO_RULES`.
_FONDO_AMM_CANON = 'F.DO AMM. '


def _canon_fondo_amm(desc_upper: str) -> str:
    """Collassa ogni grafia di "fondo ammortamento" sulla forma canonica `F.DO AMM.`.

    `_SP_PASSIVO_RULES` copre la categoria del cespite (MACCHINAR, ATTREZZ, AUTO,
    IMMAT...) SOLO in coppia con il token `F.DO`; la grafia con slash e' coperta
    solo insieme a IMMAT/MATER, parole che compaiono nei mastri aggregati ma MAI
    nei conti di dettaglio per categoria. Cosi' `F/AMM.MACCHINARI` non matcha
    nessuna regola, cade nel default `sp16` e diventa un DEBITO: l'attivo resta
    lordo, il passivo si gonfia della stessa massa, il bilancio pareggia lo stesso
    e nessun gate protesta (budget_281: 5 fondi su 6, 124.893,64 di 124.936,25).

    Normalizzare la TESTA una volta sola, invece di duplicare le 15 regole di
    categoria per ogni grafia, e' cio' che tiene allineati i due riconoscitori di
    fondo (`_is_fondo_amm` e questa tabella) — la loro divergenza E' il bug.

    La riscrittura tocca SOLO le stringhe che `_is_fondo_amm` ha gia' dichiarato
    fondi, quindi e' additiva per costruzione: si nettano piu' fondi, mai meno,
    e "AMMINISTRATORI C/COMPENSI" non e' raggiungibile.
    """
    if not _is_fondo_amm(desc_upper):
        return desc_upper
    canon = _FONDO_AMM_HEAD_RE.sub(_FONDO_AMM_CANON, desc_upper, count=1)
    # Nessuna testa riconosciuta (dicitura non a inizio riga): meglio la stringa
    # originale che una riscrittura a caso.
    return canon if canon != desc_upper else desc_upper


def _classify_sp_passivo(desc_upper: str) -> str:
    """Classify a passivo entry by description keywords. Returns field or 'sp16' default."""
    desc_upper = _canon_fondo_amm(desc_upper)
    for keywords, field in _SP_PASSIVO_RULES:
        if _kw_match(desc_upper, keywords):
            return field
    return 'sp16'  # default: debiti breve


def _sp02_detail_field(desc_upper: str) -> Optional[str]:
    """Return the B.I detail supported by the source description, if explicit."""
    if _kw_any(desc_upper, ['COSTI DI IMPIANTO', "COSTI D'IMPIANTO"]):
        return 'sp02a_costi_impianto'
    if _kw_any(desc_upper, ['SVILUPP', 'RICERCA']):
        return 'sp02b_costi_sviluppo'
    if _kw_any(desc_upper, ['BREVETT', 'SOFTWARE', 'OPERE INGEGNO']):
        return 'sp02c_brevetti'
    if _kw_any(desc_upper, ['CONCESS', 'LICENZ', 'MARCHI']):
        return 'sp02d_concessioni'
    if 'AVVIAMENTO' in desc_upper:
        return 'sp02e_avviamento'
    if _kw_any(desc_upper, ['IN CORSO', 'ACCONT']):
        return 'sp02f_immob_in_corso'
    if _kw_any(desc_upper, ['PLURIENN', 'IMMATERIAL']):
        return 'sp02g_altre_immob_imm'
    return None


def _sp03_detail_field(desc_upper: str) -> Optional[str]:
    """Return the B.II detail from semantics, independently of account codes."""
    if _kw_any(desc_upper, ['IN CORSO', 'ACCONT']):
        return 'sp03e_immob_in_corso'
    if _kw_any(desc_upper, ['TERREN', 'FABBRICAT']):
        return 'sp03a_terreni_fabbricati'
    if 'ATTREZZ' in desc_upper:
        return 'sp03c_attrezzature'
    if _kw_any(desc_upper, [
        "MACCHINE D'UFFICIO", 'MACCHINE UFFICIO', 'MOBIL', 'ARRED',
        'AUTOMEZZ', 'AUTOVEICOL', 'AUTOVETTUR', 'AUTO.', 'AUTO,',
        'MEZZI TRASP', 'ALTRI BENI MATERIAL',
    ]):
        return 'sp03d_altri_beni'
    if _kw_any(desc_upper, ['IMPIANT', 'MACCHINAR']):
        return 'sp03b_impianti_macchinari'
    return None


def _sp04_detail_field(desc_upper: str) -> Optional[str]:
    if 'PARTECIPAZ' in desc_upper:
        return 'sp04a_partecipazioni'
    if 'CREDITI' in desc_upper:
        if _kw_any(desc_upper, ['(OE', 'OLTRE']):
            return 'sp04c_crediti_immob_lungo'
        if _kw_any(desc_upper, ['(EE', 'ENTRO']):
            return 'sp04b_crediti_immob_breve'
    if 'TITOL' in desc_upper:
        return 'sp04d_altri_titoli'
    if 'DERIVAT' in desc_upper:
        return 'sp04e_strumenti_derivati_attivi'
    return None


def _sp05_detail_field(desc_upper: str) -> Optional[str]:
    if _kw_match(desc_upper, ['LAVOR', 'CORSO']):
        return 'sp05c_lavori_in_corso'
    if _kw_any(desc_upper, ['SEMILAVOR', 'PRODOTT IN CORSO']):
        return 'sp05b_prodotti_in_corso'
    if _kw_match(desc_upper, ['MAT', 'PRIM']):
        return 'sp05a_materie_prime'
    if _kw_any(desc_upper, ['PRODOTT FINIT', 'MERCI']):
        return 'sp05d_prodotti_finiti'
    if 'ACCONT' in desc_upper:
        return 'sp05e_acconti'
    return None


def _sp14_detail_field(desc_upper: str) -> Optional[str]:
    if _kw_any(desc_upper, ['QUIESCENZA', 'INDENNIT', 'FINE MANDATO']):
        return 'sp14a_fondi_trattamento_quiescenza'
    if 'IMPOST' in desc_upper:
        return 'sp14b_fondi_imposte'
    if 'DERIVAT' in desc_upper:
        return 'sp14c_strumenti_derivati_passivi'
    if _kw_any(desc_upper, ['FOND', 'RISCHI', 'ONERI']):
        return 'sp14d_altri_fondi'
    return None


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


def _resolve_field(desc: str, side: Optional[str] = None,
                   statement: Optional[str] = None) -> Optional[str]:
    """Shared-tree classification, returned as a SHORT route-C key.

    `iv_cee_hierarchy.resolve` reasons in DB column names ('ce09_ammortamenti')
    while the route-C parsers work in short keys ('ce09') until _map_sc_keys.
    The short key is the db_field prefix up to the first underscore
    ('sp04a_partecipazioni' -> 'sp04a'). That split is a mechanical string
    operation, not a guarantee of routability on its own: every short key the
    tree can actually produce must also be in `pdf_importer._SC_KEY_MAP` (or
    already contain an underscore, in which case `_map_sc_keys` passes it
    through unchanged) — otherwise `_map_sc_keys` silently drops the amount.
    See `tests/test_classification_fallback.py` for the guard that checks
    this holds for every node in `data/iv_cee_tree.json`.

    Returns None when the tree does not know the description, or when it
    resolves to the OTHER statement — a balance-sheet caption must never be
    booked as a cost.
    """
    try:
        from importers.iv_cee_hierarchy import resolve as _tree_resolve
        node = _tree_resolve(desc, side, statement)
    except Exception:
        return None
    if node is None or not node.db_field:
        return None
    if statement and node.statement and node.statement != statement:
        return None
    return node.db_field.split('_', 1)[0]


# The income-statement leaves of data/iv_cee_tree.json, split by the SIGN they
# carry in calculations/ce_result.py: a positive amount in a COST field lowers
# the result (production_cost, ce15 oneri finanziari, ce19 oneri straordinari,
# ce20 imposte), a positive amount in a REVENUE field raises it.
#
# The split has to be written down here because the tree cannot express it:
# Node.side is None for EVERY income-statement node (side is a balance-sheet
# concept), so _resolve_field's 'costi'/'ricavi' argument enforces nothing and
# statement='ce' only bounds the lookup to the income statement. Without the
# allowlists a cost mastro reaches a gain voce -- 'DIFFERENZE CAMBIO PASSIVE'
# -> ce16 -- and since _hier_reconstruct adds every mastro POSITIVELY, the
# amount moves gestione finanziaria (ce13+ce14-ce15+ce16) by TWICE its value.
#
# The genuinely SIGNED (net) voci -- ce02 variazioni rimanenze prodotti, ce16
# utili e perdite su cambi, ce17 rettifiche di valore di attivita finanziarie,
# and their mirror ce10 variazioni rimanenze materie prime -- legitimately
# appear on either side of a trial balance. Each is listed ONLY under the
# direction in which a POSITIVE amount is CORRECT: ce02/ce16/ce17 raise the
# result, so they accept a revenue-column mastro only; ce10 is a cost, so it
# accepts a cost-column mastro only. A wrong-direction mastro is not guessed at
# with a sign flip -- it falls through to the KPI-neutral catch-all, which is
# what it did before the tree fallback existed.
_CE_COST_FIELDS = frozenset({
    'ce05', 'ce06', 'ce07', 'ce08', 'ce09', 'ce10', 'ce11', 'ce11b', 'ce12',
    'ce15',                      # C.17 interessi e altri oneri finanziari
    'ce19',                      # E.21 oneri straordinari
    'ce20',                      # imposte sul reddito
})
_CE_REVENUE_FIELDS = frozenset({
    'ce01', 'ce02', 'ce03', 'ce04',   # A) valore della produzione
    'ce13', 'ce14', 'ce16',           # C) proventi finanziari (ce16 netto)
    'ce17',                           # D) rettifiche di valore (netto)
    'ce18',                           # E.20 proventi straordinari
})


def _resolve_ce_field(desc: str, direction: str) -> Optional[str]:
    """Shared-tree CE classification constrained to `direction`.

    `direction` is 'costi' or 'ricavi'. Returns None when the tree does not
    know the description OR when it resolves to a voce of the OPPOSITE sign, so
    the caller falls through to its catch-all exactly as it did before the tree
    fallback was added. See _CE_COST_FIELDS / _CE_REVENUE_FIELDS for why the
    tree cannot enforce this on its own.
    """
    field = _resolve_field(desc, direction, statement='ce')
    if field is None:
        return None
    allowed = _CE_COST_FIELDS if direction == 'costi' else _CE_REVENUE_FIELDS
    return field if field in allowed else None


# Accounts that decide every KPI. A fallback may NEVER write these: an error
# here changes a TOTAL (a fondo ammortamento booked as a debt inflates assets
# and debts together), which breaks PFN, ROI, indipendenza finanziaria and
# both rating models at once. ce09 is included because EBITDA = EBIT + ce09.
TIER0_FIELDS = frozenset({
    'sp02', 'sp03', 'sp04',      # immobilizzazioni nette
    'sp11', 'sp12', 'sp13',      # patrimonio netto
    'sp16a', 'sp17a',            # debiti verso banche
    'ce09',                      # ammortamenti (EBITDA boundary)
})

# KPI-neutral destinations: moving mass between these changes neither EBIT nor
# EBITDA (they are all inside 'costi della produzione'), nor any debt/credit
# total. Always an explicit SUB-field: projection_common.base_bank_debt treats
# an aggregate/detail gap as BANK debt, so a residual left on an aggregate
# would silently become phantom bank debt - a tier-0 corruption.
FALLBACK_FIELDS = {'ce': 'ce06', 'bs': 'sp16g'}


# Canonical definition lives in the dependency-free reliability module so the
# import pipeline has exactly one materiality rule.
from importers.reliability import materiality_threshold  # noqa: E402,F401


def fallback_field(statement: str) -> str:
    """KPI-neutral destination for unrecognised mass in `statement`.

    Separate from fallback_bucket because a classification loop knows the
    amount long before the sheet total exists: it needs the destination now
    and the materiality verdict later.
    """
    return FALLBACK_FIELDS.get(statement, 'ce06')


def fallback_bucket(desc: str, statement: str, amount: Decimal,
                    total: Decimal, target: Optional[str] = None):
    """Destination for mass that was READ but not recognised.

    Returns (short_field, severity). severity is 'silent' below the
    materiality threshold and 'recorded' above it, so the caller can surface
    material guesswork instead of hiding it.

    Raises ValueError when `target` names a tier-0 field: uncertainty about a
    critical account must become an UNRELIABLE verdict, never a guess.
    """
    if target and target in TIER0_FIELDS:
        raise ValueError(
            f"fallback vietato verso un conto critico ({target}): "
            f"'{desc}' deve essere segnalato, non indovinato")
    severity = ('recorded'
                if abs(amount or Decimal('0')) > materiality_threshold(total)
                else 'silent')
    return fallback_field(statement), severity


# ---------------------------------------------------------------------------
# Typed sub-field classification (depth preservation)
# ---------------------------------------------------------------------------
# When the source distinguishes account TYPES (banche vs fornitori vs tributari,
# clienti vs altri crediti, riserve per natura), preserve that depth into the
# IV-CEE typed sub-fields instead of collapsing everything into the aggregate.
# These return a single OIC sub-letter; the aggregate is computed unchanged, so
# sub-fields are purely additive (no balance/quadratura impact). The DB field
# name maps below translate (letter -> full column) for emission.

# OIC art. 2424 D) Debiti — full DB column names per maturity bucket
_DEBT_FIELD = {
    'breve': {
        'a': 'sp16a_debiti_banche_breve',
        'b': 'sp16b_debiti_altri_finanz_breve',
        'c': 'sp16c_debiti_obbligazioni_breve',
        'd': 'sp16d_debiti_fornitori_breve',
        'e': 'sp16e_debiti_tributari_breve',
        'f': 'sp16f_debiti_previdenza_breve',
        'g': 'sp16g_altri_debiti_breve',
    },
    'lungo': {
        'a': 'sp17a_debiti_banche_lungo',
        'b': 'sp17b_debiti_altri_finanz_lungo',
        'c': 'sp17c_debiti_obbligazioni_lungo',
        'd': 'sp17d_debiti_fornitori_lungo',
        'e': 'sp17e_debiti_tributari_lungo',
        'f': 'sp17f_debiti_previdenza_lungo',
        'g': 'sp17g_altri_debiti_lungo',
    },
}
# OIC art. 2424 C.II) Crediti — full DB column names per maturity bucket
_CREDIT_FIELD = {
    'breve': {
        'a': 'sp06a_crediti_clienti_breve',
        'e': 'sp06e_crediti_tributari_breve',
        'f': 'sp06f_imposte_anticipate_breve',
        'g': 'sp06g_crediti_altri_breve',
    },
    'lungo': {
        'a': 'sp07a_crediti_clienti_lungo',
        'e': 'sp07e_crediti_tributari_lungo',
        'f': 'sp07f_imposte_anticipate_lungo',
        'g': 'sp07g_crediti_altri_lungo',
    },
}
# OIC art. 2424 A) Patrimonio netto — riserve breakdown
_RISERVA_FIELD = {
    'a': 'sp12a_riserva_sovrapprezzo',
    'b': 'sp12b_riserve_rivalutazione',
    'c': 'sp12c_riserva_legale',
    'd': 'sp12d_riserve_statutarie',
    'e': 'sp12e_altre_riserve',
    'g': 'sp12g_utili_perdite_portati',
}


def _debt_type(desc_upper: str) -> str:
    """Typed-debt OIC sub-letter for a passivo debt line (a..g)."""
    if _kw_any(desc_upper, ['OBBLIGAZION']):
        return 'c'
    # Altri finanziatori / soci FIRST, so the generic FINANZ→banche rule below does not
    # steal "FINANZIATORI" or "SOCI C/FINANZIAMENTO" (D.5, not D.4).
    if _kw_any(desc_upper, ['ALTRI FINANZIAT', 'FINANZIAT', 'SOCI C/FINANZ', 'SOCI C/C',
                            'V/SOCI', 'FACTOR']):
        return 'b'
    # Banks (D.4): 'BANC' covers BANCA/BANCO/BANCHE/BANCARIO and bank names ending in
    # -BANCA (EMILBANCA); incl. bank financings ("FINANZIAMENTO <banca>"), salvo-buon-fine
    # (SBF), and bank advances against invoices/credits ("ANTICIPO FATTURE", "ANTICIPI SU
    # CREDITI") which are short-term bank debt even when the bank name carries no 'BANC'.
    if _kw_any(desc_upper, ['BANC', 'MUTU', 'C/C', 'C.C.', 'SCOPERT',
                            'FINANZIAM', 'FINANZ', 'S.B.F', 'SBF',
                            'ANTICIPO FATTUR', 'ANTICIPI SU FATTUR', 'ANTICIPI SU CRED']):
        return 'a'
    # Fornitori (D.7): incl. trade payables ("DEBITI COMMERCIALI") and supplier accruals
    # ("FATTURE DA RICEVERE").
    if _kw_any(desc_upper, ['FORNITOR', 'COMMERCIAL', 'FATTURE DA RICEV']):
        return 'd'
    # Tributari (D.12): 'ERARI' covers ERARIO/ERARIALI/ERARIALE.
    if _kw_any(desc_upper, ['TRIBUTAR', 'ERARI', 'IVA', 'IMPOST', 'F24', 'RITENUT']):
        return 'e'
    if _kw_any(desc_upper, ['PREV', 'INPS', 'INAIL', 'SICUR', 'ENPALS', 'INARCASSA']):
        return 'f'
    return 'g'  # altri debiti (acconti, clienti c/, movimentazioni c/terzi, ...)


# Creditor-type sub-field groups (entro / oltre), aligned to _debt_type letters a..g.
_DEBT_GROUPS_BREVE = ['sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
                      'sp16c_debiti_obbligazioni_breve', 'sp16d_debiti_fornitori_breve',
                      'sp16e_debiti_tributari_breve', 'sp16f_debiti_previdenza_breve',
                      'sp16g_altri_debiti_breve']
_DEBT_GROUPS_LUNGO = ['sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo',
                      'sp17c_debiti_obbligazioni_lungo', 'sp17d_debiti_fornitori_lungo',
                      'sp17e_debiti_tributari_lungo', 'sp17f_debiti_previdenza_lungo',
                      'sp17g_altri_debiti_lungo']


def overlay_debt_typing(winner_bs: dict, donor_bs: dict,
                        degenerate_frac: Decimal = Decimal('0.60'),
                        donor_margin: Decimal = Decimal('0.20')) -> dict:
    """Route-C post-pass: graft the donor's creditor-type breakdown onto the winner.

    Both route-C extractors run (CoGe LLM + deterministic). The LLM is strong on TOTALS
    but can dump the whole debt mass into 'altri' (sp16g/sp17g); the deterministic parser
    types each line via _debt_type (banche/fornitori/tributari/...). When the winning
    candidate's debt is DEGENERATE (mostly 'altri') and the donor has a meaningfully
    richer split, redistribute the winner's debt AGGREGATE across a..g using the donor's
    proportions — the winner's total is preserved, only the split changes.

    Conservative by design (no-op unless clearly beneficial):
      - skip a group whose aggregate is ~0
      - skip when the winner is already well-typed (altri share <= degenerate_frac)
      - skip when the donor is itself degenerate or not at least `donor_margin` better
    Mutates and returns winner_bs.
    """
    for agg, groups, altri_key in (
        ('sp16_debiti_breve', _DEBT_GROUPS_BREVE, 'sp16g_altri_debiti_breve'),
        ('sp17_debiti_lungo', _DEBT_GROUPS_LUNGO, 'sp17g_altri_debiti_lungo'),
    ):
        w_total = Decimal(str(winner_bs.get(agg, 0) or 0))
        if w_total <= Decimal('1'):
            continue
        w_altri = Decimal(str(winner_bs.get(altri_key, 0) or 0))
        w_altri_frac = w_altri / w_total
        if w_altri_frac <= degenerate_frac:
            continue  # winner already meaningfully typed → leave it
        d_total = sum((Decimal(str(donor_bs.get(g, 0) or 0)) for g in groups), Decimal('0'))
        if d_total <= Decimal('1'):
            continue  # donor has no debt typing to offer
        d_altri = Decimal(str(donor_bs.get(altri_key, 0) or 0))
        d_altri_frac = d_altri / d_total
        if d_altri_frac >= w_altri_frac - donor_margin:
            continue  # donor not meaningfully richer than the winner
        # Redistribute the winner's aggregate by the donor's proportions.
        new_vals = {}
        for g in groups:
            share = Decimal(str(donor_bs.get(g, 0) or 0)) / d_total
            new_vals[g] = (w_total * share).quantize(Decimal('0.01'))
        # Absorb rounding drift into 'altri' so the split sums back to the aggregate.
        drift = w_total - sum(new_vals.values(), Decimal('0'))
        new_vals[altri_key] = new_vals.get(altri_key, Decimal('0')) + drift
        winner_bs.update(new_vals)
    return winner_bs


def _credit_type(desc_upper: str) -> str:
    """Typed-credit OIC sub-letter for an attivo credit line (a/e/f/g)."""
    if _kw_any(desc_upper, ['IMPOSTE ANTICIP', 'IMPOSTA ANTICIP']):
        return 'f'
    if _kw_any(desc_upper, ['CLIENT']):
        return 'a'
    if _kw_any(desc_upper, ['TRIBUTAR', 'ERARIO', 'IVA', 'IMPOST', 'RITENUT', "CRED. D'IMPOST",
                            'CREDITO IMPOST', 'F24']):
        return 'e'
    return 'g'  # altri crediti


def _riserva_type(desc_upper: str) -> str:
    """Riserve OIC sub-letter for a PN reserve line (a/b/c/d/e/g)."""
    if _kw_any(desc_upper, ['SOVRAPPREZZO']):
        return 'a'
    if _kw_any(desc_upper, ['RIVALUTAZ']):
        return 'b'
    if _kw_any(desc_upper, ['LEGALE']):
        return 'c'
    if _kw_any(desc_upper, ['STATUTAR']):
        return 'd'
    if _kw_any(desc_upper, ['PORTATI', 'PORTATE', 'NUOVO', 'PRECEDENT', 'ESERCIZI PREC']):
        return 'g'  # utili/(perdite) portati a nuovo
    return 'e'  # altre riserve (straordinaria, riserva utili, ...)


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

    # Typed sub-field accumulators (depth preservation). Mirror the EXACT amounts
    # that feed the aggregates, so they're purely additive: sub-fields are emitted
    # at finalization and reconciled to the aggregate, never altering it. Dicts are
    # mutated in place (no nonlocal needed).
    typed_debt_breve = {k: Decimal('0') for k in 'abcdefg'}
    typed_debt_oltre = {k: Decimal('0') for k in 'abcdefg'}
    typed_credit_breve = {k: Decimal('0') for k in 'aefg'}
    typed_credit_deduction = {k: Decimal('0') for k in 'aefg'}
    typed_riserve = {k: Decimal('0') for k in 'abcdeg'}
    # Gross fixed-asset details and their matching depreciation funds.  These
    # remain description-driven: account numbers vary across ERP products.
    typed_fixed_gross: Dict[str, Decimal] = defaultdict(Decimal)
    typed_fixed_depr: Dict[str, Decimal] = defaultdict(Decimal)
    typed_direct_assets: Dict[str, Decimal] = defaultdict(Decimal)
    typed_fondi_rischi: Dict[str, Decimal] = defaultdict(Decimal)

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
                detail = _sp02_detail_field(desc_upper)
                if detail:
                    typed_fixed_gross[detail] += entry.amount
            elif field == 'gross_sp03':
                gross_sp03 += entry.amount
                detail = _sp03_detail_field(desc_upper)
                if detail:
                    typed_fixed_gross[detail] += entry.amount
            elif field == 'gross_sp04':
                bs['sp04'] = bs.get('sp04', Decimal('0')) + entry.amount
                detail = _sp04_detail_field(desc_upper)
                if detail:
                    typed_direct_assets[detail] += entry.amount
            elif field == 'sp05':
                bs['sp05'] = bs.get('sp05', Decimal('0')) + entry.amount
                detail = _sp05_detail_field(desc_upper)
                if detail:
                    typed_direct_assets[detail] += entry.amount
            elif field == 'sp09':
                bank_dare += entry.amount
            else:
                bs[field] = bs.get(field, Decimal('0')) + entry.amount
                # Typed depth: crediti breve by debtor type (clienti/tributari/altri)
                if field == 'sp06':
                    typed_credit_breve[_credit_type(desc_upper)] += entry.amount
            return

        # =================================================================
        # STATO PATRIMONIALE — PASSIVO
        # =================================================================
        if entry.section == 'passivo':
            field = _classify_sp_passivo(desc_upper)
            if field == 'depr_sp02':
                depr_sp02 += entry.amount
                detail = _sp02_detail_field(desc_upper)
                if detail:
                    typed_fixed_depr[detail] += entry.amount
            elif field == 'depr_sp03':
                depr_sp03 += entry.amount
                detail = _sp03_detail_field(desc_upper)
                if detail:
                    typed_fixed_depr[detail] += entry.amount
            elif field == 'deduct_crediti':
                crediti_deduction += entry.amount
                typed_credit_deduction[_credit_type(desc_upper)] += entry.amount
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
                    typed_riserve[_riserva_type(desc_upper)] += entry.amount
            elif field == 'debt_bank':
                if entry.level in (0, 1, 2):
                    # Parent/detail (EE)/(OE) routing: AGO suffix convention,
                    # plus DEPI flat-balance ENTRO/OLTRE in the description.
                    # Typed depth: banche/altri-finanz/obbligazioni by description.
                    _dt = _debt_type(desc_upper)
                    if '(OE)' in desc_upper or 'OLTRE' in desc_upper:
                        debt_bank_oltre += entry.amount
                        debt_bank_total += entry.amount
                        typed_debt_oltre[_dt] += entry.amount
                    elif '(EE)' in desc_upper or 'ENTRO' in desc_upper:
                        debt_bank_entro += entry.amount
                        debt_bank_total += entry.amount
                        typed_debt_breve[_dt] += entry.amount
                    else:
                        debt_bank_total += entry.amount
                        typed_debt_breve[_dt] += entry.amount
            elif field == 'sp16':
                # Non-bank debts with (OE) suffix → long-term (sp17).
                # Typed depth: fornitori/tributari/previdenza/altri by description.
                _dt = _debt_type(desc_upper)
                if '(OE)' in desc_upper or 'OLTRE' in desc_upper:
                    bs['sp17'] = bs.get('sp17', Decimal('0')) + entry.amount
                    typed_debt_oltre[_dt] += entry.amount
                else:
                    bs['sp16'] = bs.get('sp16', Decimal('0')) + entry.amount
                    typed_debt_breve[_dt] += entry.amount
            elif field == 'sp14':
                bs['sp14'] = bs.get('sp14', Decimal('0')) + entry.amount
                detail = _sp14_detail_field(desc_upper)
                if detail:
                    typed_fondi_rischi[detail] += entry.amount
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

        # Page headers are not ledger accounts.  Some codeless/stacked exports put
        # the company address or fiscal identifier immediately after a numeric
        # token, so the generic row reader interprets them as a code/description/
        # amount triple (BILANCIO-TEST: ``5034 / VIA ROMA 162`` -> EUR 1.62;
        # budget_435/367: P.IVA -> EUR 19,675,904.96).  Exclude only unmistakable
        # registry metadata; never use the balance gap to compensate it later.
        if (
            re.match(r'^(?:VIA|VIALE|V\.LE|PIAZZA|P\.ZZA|CORSO)\b', desc_upper)
            or 'CODICE FISCALE' in desc_upper
            or 'PARTITA IVA' in desc_upper
            or re.match(r'^(?:C\.F\.|P\.IVA|REA)\b', desc_upper)
        ):
            continue

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
                        typed_riserve[_riserva_type(desc_upper)] += entry.amount
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
                    typed_riserve[_riserva_type(desc_upper)] += entry.amount
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
                        typed_riserve[_riserva_type(desc_upper)] += entry.amount
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

    # Net gross assets against depreciation. Clamp at 0: a fondo ammortamento can
    # never exceed its own gross asset, so a negative net immobilizzazione is always
    # a misclassification (fondo booked without/over its asset — budget_330/365/435)
    # and a negative asset is never a valid IV-CEE value.
    bs['sp02'] = bs.get('sp02', Decimal('0')) + max(Decimal('0'), gross_sp02 - depr_sp02)
    bs['sp03'] = bs.get('sp03', Decimal('0')) + max(Decimal('0'), gross_sp03 - depr_sp03)

    # Emit only source-supported IV-CEE details.  Each depreciation fund is
    # subtracted from the same semantic asset family; an unknown caption stays
    # visible as a hierarchy difference instead of being invented as "altri".
    for detail, gross in typed_fixed_gross.items():
        bs[detail] = bs.get(detail, Decimal('0')) + max(
            Decimal('0'), gross - typed_fixed_depr.get(detail, Decimal('0'))
        )
    for detail, amount in typed_direct_assets.items():
        bs[detail] = bs.get(detail, Decimal('0')) + amount
    for detail, amount in typed_fondi_rischi.items():
        bs[detail] = bs.get(detail, Decimal('0')) + amount

    # Immobilizzazioni are presented GROSS on these trial balances (fondi
    # ammortamento are separate passivo lines, netted just above), so the document's
    # DECLARED total / pareggio is GROSS. Expose the netted contra mass so the
    # route-C pipeline can reduce the declared anchor before reconciling — otherwise
    # the netted fondi resurface as a FALSE plug (budget_131 Oprandi: net attivo
    # 230.205,93 vs gross pareggio 355.878,76 → spurious 125.672,83 plug). Survives
    # _map_sc_keys (underscore key). Mirrors net_contra_accounts' returned _contra
    # for the best-effort path. Cap the applied fondi at the gross asset present, so
    # the anchor reduction never exceeds the gross immobilizzazioni (a fondo without
    # a matching asset — the clamp case above — must not shrink the declared anchor).
    _netted = min(depr_sp02, gross_sp02) + min(depr_sp03, gross_sp03)

    # Banks
    bs['sp09'] = bs.get('sp09', Decimal('0')) + bank_dare

    # Crediti deduction. Il fondo svalutazione/rischi su crediti e' un contra dei
    # CREDITI esposto sul passivo esattamente come i fondi ammortamento lo sono
    # delle immobilizzazioni: nettarlo abbassa l'attivo senza abbassare il totale
    # DICHIARATO, che resta lordo. Se non entra anche lui nella massa contra,
    # riemerge come plug FALSO di importo pari al fondo (budget_281: 17.768,10 su
    # 1.708.975,05 = 1,04% -> oltre la soglia dell'1% -> QUADRATURA MASCHERATA su
    # un bilancio che invece e' corretto). Stesso cap dei fondi ammortamento: mai
    # oltre i crediti lordi presenti, cosi' un fondo senza il suo credito non
    # puo' restringere l'ancora.
    if crediti_deduction > 0:
        _gross_crediti = bs.get('sp06', Decimal('0'))
        bs['sp06'] = _gross_crediti - crediti_deduction
        _netted += min(crediti_deduction, max(Decimal('0'), _gross_crediti))

    if _netted > 0:
        bs['_netted_contra'] = bs.get('_netted_contra', Decimal('0')) + _netted

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
    # Overdrafts are bank debt: keep them in the typed depth too.
    typed_debt_breve['a'] += bank_avere

    # -----------------------------------------------------------------
    # Typed sub-field depth (additive): emit the OIC creditor/debtor/riserve
    # breakdown the source distinguished, reconciled so the sub-fields sum
    # EXACTLY to their aggregate. This never changes an aggregate (and thus
    # never the balance) — it only exposes the detail level present in the
    # document instead of one lumped voce. When the source carries no type
    # info, the residual falls into 'altri'/'altre riserve' (same as before).
    # -----------------------------------------------------------------
    def _reconcile_typed(aggregate: Decimal, buckets: Dict[str, Decimal], altri: str) -> None:
        residual = aggregate - sum(buckets.values())
        buckets[altri] = buckets.get(altri, Decimal('0')) + residual
        if buckets[altri] < 0:
            # Contra/deduction exceeded 'altri' (rare) — clamp; the small leftover
            # gap is reconciled downstream (frontend reconcileSubfields).
            buckets[altri] = Decimal('0')

    _reconcile_typed(bs.get('sp16', Decimal('0')), typed_debt_breve, 'g')
    _reconcile_typed(bs.get('sp17', Decimal('0')), typed_debt_oltre, 'g')
    # A fondo svalutazione follows the debtor family it explicitly names.  In
    # particular, "f.do sval. crediti v/clienti" reduces sp06a rather than being
    # forced into the residual sp06g bucket (budget_615).
    for letter, deduction in typed_credit_deduction.items():
        if deduction:
            typed_credit_breve[letter] = max(
                Decimal('0'), typed_credit_breve.get(letter, Decimal('0')) - deduction
            )
    _reconcile_typed(bs.get('sp06', Decimal('0')), typed_credit_breve, 'g')
    _reconcile_typed(bs.get('sp12', Decimal('0')), typed_riserve, 'e')

    for letter, amt in typed_debt_breve.items():
        bs[_DEBT_FIELD['breve'][letter]] = amt
    for letter, amt in typed_debt_oltre.items():
        bs[_DEBT_FIELD['lungo'][letter]] = amt
    for letter, amt in typed_credit_breve.items():
        bs[_CREDIT_FIELD['breve'][letter]] = amt
    for letter, amt in typed_riserve.items():
        bs[_RISERVA_FIELD[letter]] = amt
    # Crediti lungo (sp07): not typed by this parser — expose the aggregate as 'altri'
    # so the sub-row reconciles (clienti/tributari lungo are rare in trial balances).
    if bs.get('sp07', Decimal('0')):
        bs['sp07g_crediti_altri_lungo'] = bs['sp07']

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


def _c8_parse_side(words, lo: float, hi: float, axis: int = 1) -> List[Entry]:
    """Parse one column (words whose split-axis coordinate is in (lo, hi]).

    ``axis`` is the coordinate that SEPARATES the two contrapposte columns:

    * ``axis=1`` (default) — rotated page: columns are stacked along y and a row
      runs along x, read bottom-to-top. This is the original behaviour.
    * ``axis=0`` — unrotated landscape (AGO "Situazione Contabile"): columns sit
      side by side along x and a row runs along y, read left-to-right.

    Tokens are flattened into one reading-order stream and consumed as
    ``code -> description -> amount``, so grouping only fixes ORDER: baseline
    jitter between a code and its amount cannot break the pairing.
    """
    from collections import defaultdict
    rows: Dict[int, list] = defaultdict(list)
    for w in words:
        if lo < w[axis] <= hi:
            rows[round(w[1 - axis])].append(w)
    toks: List[str] = []
    for key in sorted(rows):
        if axis == 1:
            rows[key].sort(key=lambda w: -w[1])  # rotated reading order (top→bottom)
        else:
            rows[key].sort(key=lambda w: w[0])   # left→right within the row
        toks.extend(w[4] for w in rows[key])

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


def _c8_split_columns(words, axis: int, mid: float):
    """Return (left_side, right_side) entries for one page given the document
    split axis + gutter, so the header-driven pass and the header-less second
    pass share EXACTLY the same column geometry.

    'left' is always the ATTIVITA'/COSTI side, 'right' the PASSIVITA'/RICAVI
    side, regardless of axis: on an unrotated page (axis=0) that is lower-x vs
    higher-x; on a rotated page (axis=1) the reading coordinate is inverted so
    the left side is the HIGHER coordinate.
    """
    if axis == 0:
        return (_c8_parse_side(words, -1e9, mid, axis=0),
                _c8_parse_side(words, mid, 1e9, axis=0))
    return (_c8_parse_side(words, mid, 1e9, axis=1),
            _c8_parse_side(words, -1e9, mid, axis=1))


def _c8_refine_gutter_x(words, header_mid: float) -> float:
    """Place the attivo|passivo gutter in the clean vertical gap BEFORE the
    right-hand code column, on an unrotated page.

    Each contrapposte side is ``code | description | amount`` and the LEFT side's
    amount column is right-aligned close to the RIGHT side's code column, so the
    header-word midpoint can fall INSIDE the left amount band and misassign those
    amounts to the passivo reader (budget_615: header_mid=365 slices the attivo
    amounts at x=367-379, losing ~260k). The two 8-digit code columns bracket a
    clean gap; put the gutter at its middle. Returns the header midpoint unchanged
    when it already sits in that gap, so pages the header split reads correctly
    are untouched (additive)."""
    code_xs = sorted(w[0] for w in words if re.fullmatch(r'\d{8}', w[4]))
    if len(code_xs) < 2:
        return header_mid
    gap, gi = max((code_xs[i + 1] - code_xs[i], i) for i in range(len(code_xs) - 1))
    if gap < 100:                      # a single code column: nothing to split
        return header_mid
    right_code_x = code_xs[gi + 1]
    left_max = max((w[0] for w in words if w[0] < right_code_x), default=header_mid)
    if left_max >= right_code_x:
        return header_mid
    if left_max <= header_mid <= right_code_x:
        return header_mid              # header gutter already in the clean gap
    return (left_max + right_code_x) / 2


def parse_entries_contrapposte_8digit(file_path: str) -> List[Entry]:
    """Parse a contrapposte 8-digit trial balance using word coordinates."""
    doc = fitz.open(file_path)
    entries: List[Entry] = []
    declared_utile = None
    declared_perdita = False
    declared_attivo = Decimal('0')
    declared_passivo = Decimal('0')

    # Document-level gutter/axis learned from the page(s) that DO carry live
    # ATTIVITA'/PASSIVITA' header text tokens, reused by the second pass to read
    # the pages whose headers are drawn as vectors (budget_615: only page 1 has
    # live headers, but the SP spills onto page 0 and the CE onto pages 3-7).
    doc_axis: Optional[int] = None
    doc_mid: Optional[float] = None
    read_pages: set = set()

    for pidx, page in enumerate(doc):
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
        # Which coordinate SEPARATES the two columns? A rotated contrapposte page
        # stacks them along y (headers share x); an unrotated landscape export puts
        # them side by side along x (headers share y — AGO budget_615: ATTIVITA'
        # x=156.12 y=90.74, PASSIVITA' x=574.55 y=90.74). Assuming "rotated" on an
        # unrotated page collapsed every word into `left` and left the passivo column
        # EMPTY (totale_passivo=0). Pick the axis on which the headers actually differ.
        if abs(rx - lx) >= abs(ry_ - ly):
            axis, mid = 0, (lx + rx) / 2      # side by side: split by x
            mid = _c8_refine_gutter_x(words, mid)
        else:
            axis, mid = 1, (ly + ry_) / 2     # stacked: split by y (rotated page)
        left, right = _c8_split_columns(words, axis, mid)
        # Remember the SP gutter at document level for the header-less pass.
        if is_sp and doc_mid is None:
            doc_axis, doc_mid = axis, mid
        if not (left or right):
            # The header split yielded nothing — e.g. a CE footer page where the
            # "TOTALE COSTI/RICAVI" summary labels were mistaken for the column
            # headers, giving a gutter that splits a code from its amount. Leave
            # the page for the second pass to read via the document-level gutter.
            continue
        for e in left:
            e.section = left_sec
        for e in right:
            e.section = right_sec
        entries.extend(left)
        entries.extend(right)
        read_pages.add(pidx)

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

    # --- Second pass: pages whose ATTIVITA'/PASSIVITA'/COSTI/RICAVI headers are
    # drawn as VECTORS (no live text token), so the header-driven pass skipped
    # them and most of the document was lost. Reuse the document-level gutter and
    # keep the contrapposte COLUMN as ground truth for the side: the left column
    # is the debit-nature side (attivo / costi), the right the credit-nature side
    # (passivo / ricavi). Whether a page is SP or CE comes from ACCOUNT
    # RECOGNITION, not code prefixes (which differ across gestionali): revenue and
    # cost-of-production accounts resolve to the IV-CEE statement 'ce', SP accounts
    # to 'bs'. The CE section runs contiguously to the end of the document, so the
    # first majority-CE page marks the boundary; past it the ammortamento/TFR/
    # salari lines (which resolve to 'bs' in isolation) are correctly read as CE.
    # Additive: pages with live headers were all read above (read_pages).
    if doc_mid is not None:
        from importers.iv_cee_hierarchy import resolve as _resolve_ivcee
        pending = []          # (pidx, left, right) for each header-less data page
        ce_start = None       # first page index whose accounts are majority CE
        for pidx, page in enumerate(doc):
            if pidx in read_pages:
                continue
            words = page.get_text('words')
            if not any(re.fullmatch(r'\d{8}', w[4]) for w in words):
                continue
            left, right = _c8_split_columns(words, doc_axis, doc_mid)
            pending.append((pidx, left, right))
            if ce_start is None:
                n_ce = sum(1 for e in left + right
                           if _resolve_ivcee(e.description, statement='ce'))
                n_bs = sum(1 for e in left + right
                           if _resolve_ivcee(e.description, statement='bs'))
                if n_ce > n_bs:
                    ce_start = pidx
        for pidx, left, right in pending:
            if ce_start is not None and pidx >= ce_start:
                left_sec, right_sec = 'costi', 'ricavi'
            else:
                # SP gross presentation: attivo on the left, passivo (incl. fondi
                # ammortamento shown gross on the passivo side) on the right.
                left_sec, right_sec = 'attivo', 'passivo'
            for e in left:
                e.section = left_sec
            for e in right:
                e.section = right_sec
            entries.extend(left)
            entries.extend(right)

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

    # When the SP footer TOTALE ATTIVITA'/PASSIVITA' are unreadable (drawn as
    # vectors — budget_615), the current-year result is still fully determined by
    # the CE: utile = ricavi - costi. The CE mastri are in the text layer, so this
    # recovers the result without trusting a corrupt SP footer.
    if declared_utile is None:
        ricavi_sum = sum((e.amount for e in entries
                          if e.section == 'ricavi' and e.amount), Decimal('0'))
        costi_sum = sum((e.amount for e in entries
                         if e.section == 'costi' and e.amount), Decimal('0'))
        if ricavi_sum or costi_sum:
            res = ricavi_sum - costi_sum
            declared_utile = abs(res)
            declared_perdita = res < 0

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


def _c8_dettaglio_rows(words, doc_mid: float, doc_axis: int):
    """Yield ``(code, description, amount)`` for the 6-digit DETTAGLIO lines in
    the PASSIVO (right) column. On these AGO exports the dettaglio amounts carry
    the underline drawn as interlaced '_' glyphs INSIDE the amount token
    (``_2_.00_0_,_0_0_`` = 2.000,00); the digits are all present, so the glyphs
    are stripped before parsing. A token that does not reduce to a clean amount is
    skipped, never guessed — and the caller self-validates the recovered subset
    against the balance gap, so any mis-strip is rejected rather than trusted."""
    from collections import defaultdict
    if doc_axis == 0:
        side = [w for w in words if w[0] > doc_mid]
    else:
        side = [w for w in words if w[1] <= doc_mid]
    rows: Dict[int, list] = defaultdict(list)
    for w in side:
        rows[round(w[1 - doc_axis])].append(w)
    toks: List[str] = []
    for key in sorted(rows):
        rows[key].sort(key=(lambda w: -w[1]) if doc_axis == 1 else (lambda w: w[0]))
        toks.extend(w[4] for w in rows[key])

    out: List[Tuple[str, str, Decimal]] = []
    code: Optional[str] = None
    desc: List[str] = []
    amt: Optional[Decimal] = None

    def flush():
        if code is not None and amt is not None:
            out.append((code, ' '.join(desc), amt))

    for t in toks:
        tc = t.replace('_', '')                # remove interlaced underline glyphs
        if re.fullmatch(r'\d{6}', tc):         # a new dettaglio code (codes are clean)
            flush()
            code, desc, amt = tc, [], None
            continue
        if code is None:
            continue
        if re.fullmatch(r'\d{1,3}(?:\.\d{3})*,\d{2}', tc):  # amount (underline stripped)
            if amt is None:
                amt = _parse_amount(tc)
            continue
        if tc in ('000', '-', '') or tc.isdigit():
            continue
        if amt is None:                        # description precedes the amount;
            desc.append(t)                     # ignore trailing tokens (footer noise)
    flush()
    return out


def _unique_subset_summing_to(cands, target: Decimal, tol: Decimal = Decimal('1')):
    """Return the UNIQUE non-empty subset of ``cands`` (each ``(amount, ...)``)
    whose amounts sum to ``target`` within ``tol``; ``None`` when there is no such
    subset or more than one (ambiguous → refuse rather than guess)."""
    n = len(cands)
    found = None
    for mask in range(1, 1 << n):
        s = Decimal('0')
        for i in range(n):
            if mask & (1 << i):
                s += cands[i][0]
        if abs(s - target) <= tol:
            if found is not None:
                return None                     # ambiguous
            found = mask
    if found is None:
        return None
    return [cands[i] for i in range(n) if found & (1 << i)]


def _c8_recover_orphan_passivo(file_path: str, bs: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Recover passivo mastri whose 8-digit total line is drawn as a VECTOR
    (unreadable) from their CLEAN 6-digit dettagli on a dettaglio-only page.

    Only the mastro totals are trustworthy on these AGO exports (most dettaglio
    amounts are corrupted), EXCEPT where a mastro total is missing entirely
    (vector-drawn): there the happens-to-be-clean dettagli are the sole surviving
    figure. This reads those clean passivo dettagli and adds back ONLY the subset
    that closes the Attivo-vs-Passivo gap EXACTLY, keeping the result only if the
    sheet then balances (self-validation). Dettagli whose parent mastro was
    already captured (e.g. amministratori c/compensi, already inside a read
    Altri-debiti mastro) do not fit the gap and are excluded. Cannot corrupt a
    sheet: worst case it returns ``bs`` unchanged."""
    ta = bs.get('totale_attivo') or Decimal('0')
    tp = bs.get('totale_passivo') or Decimal('0')
    gap = ta - tp
    if gap <= Decimal('1'):
        return bs                              # passivo not short — nothing to do

    from importers.iv_cee_hierarchy import resolve as _resolve_ivcee
    doc = fitz.open(file_path)
    try:
        doc_axis, doc_mid = 0, None
        for page in doc:
            words = page.get_text('words')
            lefts = [w for w in words if w[4].rstrip("'") == "ATTIVITA"]
            rights = [w for w in words if w[4].rstrip("'") == "PASSIVITA"]
            if not lefts or not rights:
                continue
            lx = min(lefts, key=lambda w: w[0])
            rx = min(rights, key=lambda w: w[0])
            if abs(rx[0] - lx[0]) >= abs(rx[1] - lx[1]):
                doc_axis, doc_mid = 0, _c8_refine_gutter_x(words, (lx[0] + rx[0]) / 2)
            else:
                doc_axis, doc_mid = 1, (lx[1] + rx[1]) / 2
            break
        if doc_mid is None:
            return bs
        cands = []                             # (amount, db_field, desc)
        for page in doc:
            words = page.get_text('words')
            if any(re.fullmatch(r'\d{8}', w[4]) for w in words):
                continue                       # not a dettaglio-only page
            for code, desc, amt in _c8_dettaglio_rows(words, doc_mid, doc_axis):
                node = _resolve_ivcee(desc, side='passivo', statement='bs')
                field = node.db_field if (node and node.db_field) else None
                if field == 'sp13_utile_perdita':
                    field = None               # a debt is never the year's result
                cands.append((amt, field, desc))
    finally:
        doc.close()
    if not cands or len(cands) > 18:
        return bs

    subset = _unique_subset_summing_to(cands, gap)
    if subset is None:
        return bs

    def _add(d, key, amt):
        d[key] = (d.get(key) or Decimal('0')) + amt

    new_bs = dict(bs)
    for amt, field, desc in subset:
        if field:                              # resolve() gives a full DB name; the SC
            m = re.match(r'(sp\d+)', field)    # dict aggregates use the SHORT key (sp18)
            _add(new_bs, m.group(1) if m else 'sp16', amt)
        else:                                  # unresolved "altri debiti" → route by
            du = desc.upper()                  # the entro/oltre marker, keeping the
            oltre = ('(OE)' in du or 'OLTRE' in du)  # aggregate == Σ sub-fields so the
            _add(new_bs, 'sp17' if oltre else 'sp16', amt)             # hierarchy check
            _add(new_bs, 'sp17g_altri_debiti_lungo' if oltre          # stays coherent
                 else 'sp16g_altri_debiti_breve', amt)
    new_bs['totale_passivo'] = tp + gap        # subset sums to the gap by construction
    if abs(ta - new_bs['totale_passivo']) <= Decimal('1'):
        logger.info(f"Route C: recuperati {len(subset)} mastri passivo orfani "
                    f"(vettoriali) per {gap:,.2f} — bilancio ora quadrato")
        return new_bs
    return bs


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


def _be_norm(code: str) -> str:
    """Normalise a (possibly multi-token) account code to a digit string."""
    return re.sub(r'\D', '', code)


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

    def rec(c):
        d, a = info[c]
        field, specific = classify(d)
        if specific:
            out.append((field, a))
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


# ---------------------------------------------------------------------------
# Hierarchical-mastri reconstruction (dotted "BILANCIO 4 SEZIONI" family)
# ---------------------------------------------------------------------------
# A whole sub-family of trial balances (Sistemi/DEPI "bilancio 4 sezioni",
# code 03.01.07 / 3 / 15 / 102) lists, for every IV-CEE voce, the LEVEL-1 mastro
# with its already-correct subtotal (e.g. "05 IMMOBILIZZAZIONI MATERIALI
# 1.293.041,01"), then its dotted children. The generic best-effort parser
# normalises the code to digits and the DEEPEST detail rows (printed with a
# truncated single-digit code, e.g. a finance instalment shown as "23") then
# COLLIDE with a mastro number and inflate it → large sp09/sp16 plug ("QUADRATURA
# MASCHERATA"). Anchoring instead on the level-1 mastri (taken in DOCUMENT ORDER,
# so a no-separator code is a mastro only when its own dotted children follow it)
# makes the attivo reconcile to the declared total exactly and the current-year
# result emerge as the attivo/passivo gap (which equals ricavi-costi). This runs
# ONLY as a rescue when the best-effort result is masked, and its output is kept
# ONLY when it reconciles (gross attivo vs declared total AND SP gap vs CE result),
# so it can never regress a file the best-effort already balances.
_DOTTED_HIER_RE = re.compile(r'\b\d{1,3}\.\d{2}\.\d{2,3}\b')


def is_dotted_hierarchical(text: str) -> bool:
    """True when the document is dominated by dotted hierarchical account codes
    (NN.NN.NN), the signature of the 'bilancio 4 sezioni' mastri layout."""
    return len(_DOTTED_HIER_RE.findall(text)) >= 12


def _hier_canon(raw: str) -> str:
    """Canonicalise a hierarchical code to dotted form: '3 / 15 / 102' -> '3.15.102',
    '05.03.05' unchanged. Depth = number of '.'-separated segments."""
    s = raw.replace('/', '.')
    s = re.sub(r'\.+', '.', s).strip('.')
    return s


def _hier_collect(words, lo: float, hi: float) -> List[Tuple[str, str, Decimal]]:
    """Collect (canon_code, desc_upper, amount) rows in x-band [lo, hi), preserving
    the hierarchical code structure and DOCUMENT (top-to-bottom) order."""
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
        while i < len(toks) and re.match(r'^[\d./*]+$', toks[i]) and not _BE_AMT_RE.match(toks[i]):
            code_toks.append(toks[i])
            i += 1
        if not code_toks:
            continue
        cc = _hier_canon(''.join(code_toks))
        if not cc or not cc[0].isdigit():
            continue
        rest = toks[i:]
        amts = [_parse_amount(t) for t in rest if _BE_AMT_RE.match(t)]
        if not amts:
            continue
        desc = ' '.join(t for t in rest if not _BE_AMT_RE.match(t)).upper().strip()
        out.append((cc, desc, amts[-1]))
    return out


def _hier_lvl1(rows: List[Tuple[str, str, Decimal]]) -> List[Tuple[str, str, Decimal]]:
    """Level-1 mastri in document order: a no-'.' code is a mastro only when its OWN
    dotted children (code + '.') follow it before the next no-'.' code. This rejects
    the truncated deep-detail leaves whose code collides with a real mastro number."""
    n = len(rows)
    res = []
    for i, (c, d, a) in enumerate(rows):
        if '.' in c or 'TOTALE' in d or 'PAREGGIO' in d:
            continue
        is_mastro = False
        for j in range(i + 1, n):
            cj = rows[j][0]
            if cj.startswith(c + '.'):
                is_mastro = True
                break
            if '.' not in cj:
                break
        if is_mastro:
            res.append((c, d, a))
    return res


def _is_prior_result_caption(desc_upper: str) -> bool:
    """True for a PRIOR-year result caption ("Utile esercizio precedente", "Utili
    portati a nuovo").

    Trial balances frequently do NOT consolidate the previous year's result into
    the capital/reserve accounts: it is printed as its own row — often CODE-LESS,
    in the SP footer next to the totals — and belongs to patrimonio netto (utili
    portati a nuovo). It must be told apart from the CURRENT period result, which
    is the balancing figure and is derived from the Attivo/Passivo gap.
    """
    d = desc_upper
    if 'TOTALE' in d or 'PAREGGIO' in d:
        return False
    if not any(k in d for k in ('UTILE', 'UTILI', 'PERDITA', 'PERDITE', 'RISULTATO')):
        return False
    return 'PRECEDENT' in d or 'PORTAT' in d


def _hier_prior_result(words, lo: float, hi: float) -> Decimal:
    """Signed prior-year result printed WITHOUT an account code in x-band [lo, hi).

    Only code-less rows are collected: a prior result that carries a code is
    already inside a level-1 mastro (e.g. "23 CAPITALE E RISERVE") and counting
    it again would double it.  The sign follows the caption (perdita -> negative),
    so the caller can add the value to patrimonio netto on either column.
    """
    total = Decimal('0')
    for row_words in _be_cluster_physical_rows(words, lo, hi):
        toks = [w[4].strip() for w in sorted(row_words, key=lambda w: w[0]) if w[4].strip()]
        # a leading account code means the row is already part of a mastro
        if toks and re.match(r'^[\d./*]+$', toks[0]) and not _BE_AMT_RE.match(toks[0]):
            continue
        caption = ' '.join(t for t in toks if not _BE_AMT_RE.fullmatch(t)).upper()
        if not _is_prior_result_caption(caption):
            continue
        amounts = [_parse_amount(t) for t in toks if _BE_AMT_RE.fullmatch(t)]
        if not amounts:
            continue
        amount = abs(amounts[-1])
        if 'PERDIT' in caption:
            amount = -amount
        total += amount
    return total


def _is_fondo_amm(desc_upper: str) -> bool:
    """Recognise depreciation/amortisation funds at any aggregation level, incl. the
    aggregate mastro 'FONDI AMMORTAMENTO IMMOBILIZ' the rule table below misses.

    Questa funzione governa l'INTERO netting dei fondi, quindi il pareggio di
    tutta la route C: un fondo non riconosciuto non viene sottratto dal cespite,
    l'attivo resta lordo e il passivo gonfio della stessa massa, i due lati non
    tornano e la differenza diventa residuo non classificato -> oltre l'1%
    scatta QUADRATURA MASCHERATA e l'import viene rifiutato.

    Il test a sottostringhe qui sotto e' tenuto INVARIATO (non puo' regredire
    nulla) e viene solo AFFIANCATO dalla forma canonica del normalizzatore unico,
    che collassa `F.di ammor.to`, `Fdo amm`, `Fondo amm.` su `fondo ammortamento`
    — grafie reali che il solo test a sottostringhe non vede. L'allargamento e'
    additivo per costruzione: si riconoscono piu' fondi, mai meno.
    """
    d = desc_upper
    if (('AMMORT' in d or 'AMM.TO' in d or 'AMM.NTO' in d or 'F.DO AMM' in d or 'F/AMM' in d)
            and ('FOND' in d or 'F.DO' in d or 'F/' in d)):
        return True
    try:
        from importers.label_semantics import normalize_label
    except Exception:
        return False
    # `fondo ammortamento` CONTIGUO: "Ammortamento immobilizzazioni immateriali" e
    # "Quota ammortamento esercizio" sono COSTI del conto economico, non fondi
    # dello stato patrimoniale, e non devono mai essere nettati.
    return "fondo ammortamento" in normalize_label(d)


# Category qualifiers that make a fondo a SPECIFIC line rather than the grand-total
# aggregate. '. IMM' / 'IMMAT' mark the immateriali SUB-aggregate (also specific).
# NB: no 'MOBIL' — it is a substring of 'IMMOBILIZ' and would exclude the grand
# total itself; 'ARRED' covers "mobili e arredi".
_FONDO_CATEGORY_KW = (
    'FABBRICAT', 'IMPIANT', 'ATTREZZ', 'ARRED', 'AUTO', 'MACCHIN',
    'TERREN', 'MATER', 'SW', 'SOFTWARE', 'BREVETT', 'LICENZ', 'MARCHI',
    'MANUT', 'PLURIENN', 'COSTI', 'SPESE', 'AVVIAMENTO', 'TELEFON', 'BENI',
    '. IMM', 'IMMAT',
)


def _is_fondo_aggregate(desc_upper: str) -> bool:
    """True only for the top-level 'FONDI AMMORTAMENTO IMMOBILIZ(ZAZIONI)' grand
    total — generic immobilizzazioni, no category qualifier. Used to trust the
    printed aggregate over incompletely/mis-coded sub-lines on vision-OCR sheets;
    keyed on description so it never matches a specific leaf/sub-aggregate."""
    d = desc_upper
    return (_is_fondo_amm(d) and 'IMMOBILIZ' in d
            and not any(k in d for k in _FONDO_CATEGORY_KW))


# Specific immateriali sub-categories: their fondo is a LEAF, not the immateriali
# sub-aggregate 'FONDI AMMORT. IMMOBILIZZAZ. IMM(ATERIALI)'.
_FONDO_IMMAT_LEAF_KW = (
    'ALTRE', 'LICENZ', 'BREVETT', 'SW', 'SOFTWARE', 'MARCHI', 'COSTI', 'SPESE',
    'MANUT', 'PLURIENN', 'AVVIAMENTO', 'CONCESS',
)


def _is_fondo_immat_aggregate(desc_upper: str) -> bool:
    """True only for the generic immateriali SUB-aggregate 'FONDI AMMORT.
    IMMOBILIZZAZ. IMM' — the immateriali category header, not a specific
    immateriali leaf (ALTRE IMMOBILIZZ. IMMAT., licenze, software, ...)."""
    d = desc_upper
    return (_is_fondo_amm(d) and 'IMMOBILIZ' in d
            and ('IMMAT' in d or '. IMM' in d or d.rstrip().endswith(' IMM'))
            and not any(k in d for k in _FONDO_IMMAT_LEAF_KW))


# Asset-type markers of an INTANGIBLE (B.I) depreciation fund. The row is already
# known to be a fondo ammortamento, so these key on the ASSET category only and
# are prefix-agnostic (they fire on both 'F.DO AMM.TO ...' and 'FONDO AMM.TO ...',
# which the F.DO-gated _classify_sp_passivo rules missed → immateriali fondi such
# as LICENZE/CONSULENZE/COSTI RICERCA leaked into the materiali bucket, over-
# netting materiali and under-netting immateriali — budget_210).
_FONDO_IMMAT_KW = (
    'IMMAT', '. IMM', 'PLURIENN', 'SOFTWARE', 'BREVETT', 'MARCHI', 'MARCHIO',
    'AVVIAMENT', 'LICENZ', 'CONCESSION', 'RICERCA', 'SVILUPPO', 'PUBBLICIT',
    'WEB', 'PROGETTAZ', 'CONSULENZ', 'DIRITTI', 'INGEGNO', 'KNOW', 'MANUT',
    'AMPLIAMENT', "COSTI D'IMPIANTO", 'COSTI DI IMPIANTO',
)


def _fondo_is_immat(desc_upper: str) -> bool:
    """immateriali (True) vs materiali (False) split for a row already known to be
    a fondo (ammortamento or svalutazione immobilizzazioni). Any intangible
    asset-type marker → immateriali; the tangible captions (impianti/macchinari/
    attrezzature/auto/fabbricati/mobili…) carry none, so they fall to materiali by
    default — mirroring the historical 'F.DO AMM' fallback while no longer
    depending on the 'F.DO' spelling."""
    return any(k in desc_upper for k in _FONDO_IMMAT_KW)


# Asset-type markers of a TANGIBLE (B.II) fixed asset — used only to recognise a
# fondo svalutazione as a contra to immobilizzazioni MATERIALI (the immat side is
# recognised by _fondo_is_immat / 'IMMOBILIZ').
_FONDO_MAT_KW = (
    'FABBRICAT', 'IMPIANT', 'ATTREZZ', 'MACCHIN', 'AUTO', 'ARRED', 'TERREN',
    'AUTOMEZZ', 'AUTOVEIC',
)

# A fondo svalutazione of these items reduces OTHER balance-sheet lines, NOT the
# B.I/B.II immobilizzazioni, so it stays OUT of the immobilizzazioni contra-netting
# (crediti → sp06, rimanenze/magazzino → sp05, titoli/partecipazioni → immob.
# finanziarie sp04).
_SVALUT_NON_IMMOB_KW = ('CREDIT', 'RIMANENZ', 'MAGAZZIN', 'TITOL', 'PARTECIP')


def _is_fondo_svalut_immob(desc_upper: str) -> bool:
    """A write-down fund (fondo svalutazione) of an INTANGIBLE or TANGIBLE fixed
    asset. It is a contra-asset that reduces the B.I/B.II net book value exactly
    like the depreciation fund, so the overlay nets it TOGETHER with the fondo
    ammortamento (spec: user rule 2026-07-14, budget_210/211 'FONDO SVALUTAZIONE
    MARCHI'). Svalutazione of crediti/rimanenze/titoli/partecipazioni is excluded
    (it reduces other items). Requires a positive immobilizzazione reference so a
    bare/other 'fondo svalutazione' is never mis-netted onto immobilizzazioni."""
    d = desc_upper
    if 'SVALUT' not in d:
        return False
    if not ('FOND' in d or 'F.DO' in d or 'F/' in d):
        return False
    if any(k in d for k in _SVALUT_NON_IMMOB_KW):
        return False
    return (_fondo_is_immat(d) or 'IMMOBILIZ' in d
            or any(k in d for k in _FONDO_MAT_KW))


# ---------------------------------------------------------------------------
# Contra-netting overlay (spec docs/superpowers/specs/2026-07-06-contra-netting-
# overlay-design.md): deterministic post-extraction netting of fondi ammortamento
# (+ conservative IVA offset) on the CHOSEN route-C candidate, whatever extractor
# produced it. Pure, no LLM; no-op unless the scan self-validates against the
# document's own declared gross total.
# ---------------------------------------------------------------------------

class ContraScan(NamedTuple):
    gross_sp02: Decimal      # attivo-side immobilizzazioni immateriali (gross)
    gross_sp03: Decimal      # attivo-side immobilizzazioni materiali (gross)
    attivo_total: Decimal    # FULL attivo-side sum, fondi excluded (gate anchor)
    fondi_immat: Decimal     # fondi ammortamento immateriali (either side)
    fondi_mat: Decimal       # fondi ammortamento materiali (either side)
    iva_credito: Decimal     # IVA lines on the attivo side
    iva_debito: Decimal      # IVA lines on the passivo side
    fondi_att: Decimal       # fondi mass found on the ATTIVO side (already-net docs)
    anchor_sp02: Optional[Decimal]  # printed IMMOBILIZZAZIONI IMMATERIALI subtotal
    anchor_sp03: Optional[Decimal]  # printed IMMOBILIZZAZIONI MATERIALI subtotal
    has_aggregate: bool      # a generic grand-total 'FONDI AMMORTAMENTO IMMOBILIZ' was seen
    sval_immat: Decimal = Decimal('0')  # fondo svalutazione immobilizz. immateriali
    sval_mat: Decimal = Decimal('0')    # fondo svalutazione immobilizz. materiali


_IVA_LINE_RE = re.compile(r'\bIVA\b')


def _is_iva_line(desc_upper: str) -> bool:
    """IVA account line ('ERARIO C/IVA', 'IVA C/ACQUISTI', ...). Word-boundary so
    'RISERVA' (which contains the substring IVA) never matches."""
    return bool(_IVA_LINE_RE.search(desc_upper))


def _dedup_parent_child(rows):
    """Sum mastri OR leaves, never both. A parent row is dropped when its DIRECT
    child rows (codes strictly extending its code, with no intermediate ancestor
    among the descendants) are present and sum to its amount within
    max(2 EUR, 1%) — AGO layouts print the mastro subtotal above its detail
    accounts on both sides. Comparing against ALL descendants would double-count
    on 3-level layouts (mastro 41 → 41.01 → 41.01.07: intermediates + leaves sum
    to 2× the mastro, so the root was never dropped — budget_343/348).
    Code-less rows are always kept."""
    out = []
    for code, desc, amount in rows:
        if code:
            desc_codes = [(c, a) for c, _d, a in rows
                          if c != code and c.startswith(code)]
            kids = [a for c, a in desc_codes
                    if not any(o != c and c.startswith(o) for o, _a in desc_codes)]
            if kids:
                tol = max(Decimal('2'), abs(amount) * Decimal('0.01'))
                if abs(sum(kids) - amount) <= tol:
                    continue  # parent duplicated by its children
        out.append((code, desc, amount))
    return out


def _code_depth(code: str) -> int:
    """Hierarchy level of an account code.

    Dotted/slashed codes carry their depth explicitly ('03.01.07' -> 3). Flat
    numeric codes encode it in their LENGTH: AGO prints mastri as 8 digits
    ('13095000') and their sub-accounts as 9 ('101080000'). A 1-2 character
    flat code cannot be such an account — it is a bare level-1 mastro of a
    dotted-family chart ('03'), so it counts as depth 1.

    Depth is only a HINT — the caller must corroborate the chosen partition
    against a printed total before trusting it (see _select_dedup). Only the
    ORDER matters: a mastro must never score deeper than its own children.
    """
    c = (code or '').strip()
    if not c:
        return 0
    canon = _hier_canon(c)
    if '.' in canon:
        return len(canon.split('.'))
    return 1 if len(canon) <= 2 else len(canon)


def _depth_partition(rows, max_depth: int):
    """Keep the rows at or above `max_depth` in the hierarchy; code-less rows
    are always kept. A pure function of the THRESHOLD, so the same rule applies
    identically to any row set (see _dedup_rules)."""
    return [r for r in rows if not r[0] or _code_depth(r[0]) <= max_depth]


def _dedup_rules(rows):
    """Yield (label, rule) candidate partition RULES for a scan side.

    Each ``rule`` is a callable rows -> rows that CARRIES ITS OWN CRITERION, so
    the winner can be handed any other row set (the passivo side, the fondi
    subset) and still apply the very same partition. `rows` only generates the
    hypotheses (which depths exist here); it never parameterises the rules
    beyond the threshold they close over.

    No candidate is trusted on its own; _select_dedup scores them against the
    document's printed total. Includes the historical prefix-based dedup so a
    file that works today can still win.
    """
    yield 'all', list
    yield 'existing', _dedup_parent_child
    depths = sorted({_code_depth(c) for c, _d, _a in rows if c})
    for depth in depths:
        yield f'depth<={depth}', partial(_depth_partition, max_depth=depth)


def _dedup_candidates(rows):
    """Yield (label, rows) candidate partitions of a scan side — the rules of
    _dedup_rules already applied to `rows`."""
    for label, rule in _dedup_rules(rows):
        yield label, rule(rows)


def _select_dedup(attivo_rows, declared_total: Optional[Decimal]):
    """Pick the partition whose attivo sum reconciles to the declared total.

    Returns (label, dedup_fn, reconciled). ``dedup_fn`` is the WINNING RULE
    itself, not a label to be re-derived: it is applied unchanged to BOTH sides
    (and to the fondi subset), so the two are partitioned consistently even when
    a side happens to contain none of the winning depth's codes. When no
    declared total is available, or none of the candidates reconciles, the
    historical behaviour (`_dedup_parent_child`) is returned with
    reconciled=False — the caller then records the scan as unreliable instead of
    silently trusting it.
    """
    legacy = ('existing', _dedup_parent_child, False)
    if not declared_total or declared_total <= 0:
        return legacy
    tol = max(Decimal('50'), declared_total * Decimal('0.005'))
    best = None
    for label, rule in _dedup_rules(attivo_rows):
        kept = rule(attivo_rows)
        total = sum((a for _c, _d, a in kept), Decimal('0'))
        gap = abs(total - declared_total)
        if gap > tol:
            continue
        # tie-break: drop as few rows as possible
        key = (gap, -len(kept))
        if best is None or key < best[0]:
            best = (key, label, rule)
    if best is None:
        return legacy
    return best[1], best[2], True


def contra_declared_total(declared) -> Optional[Decimal]:
    """The printed total the contra scan must reconcile against.

    Contra-assets reconcile to the printed GROSS ATTIVO; ``pareggio`` can also
    include a current loss parked on the asset side, so using it first
    overstates the anchor (budget_330). Written once and shared, so every
    caller partitions the same document the same way.
    """
    if not declared:
        return None
    return (declared.get('attivo') or declared.get('pareggio')
            or declared.get('passivo'))


def contra_scan_mass(file_path: str, text: Optional[str] = None,
                     declared=None):
    """(fondi, iva_offset) that net_contra_accounts would remove from this doc.

    Exposed because pdf_importer has to reduce the declared anchor by exactly
    that mass BEFORE it picks between the CoGe-LLM and the deterministic
    candidate (the printed totals are GROSS on these files). Sharing this
    helper is what keeps the two sites on the SAME reconciliation-anchored
    partition: computing the mass with the historical prefix dedup over-reads
    it on AGO's disjoint code families (8-digit mastri vs 9-digit sub-accounts,
    neither a prefix of the other) and can hand the win to the wrong extractor.

    Returns (0, 0) when the document has no scannable rows.
    """
    Z = Decimal('0')
    rows = _contra_rows(file_path, text=text)
    if not rows:
        return Z, Z
    att_rows, pas_rows, _from_ocr = rows
    _label, dedup_fn, _reconciled = _select_dedup(
        att_rows, contra_declared_total(declared))
    scan = _contra_classify(att_rows, pas_rows, dedup=dedup_fn)
    fondi = (scan.fondi_immat + scan.fondi_mat
             + scan.sval_immat + scan.sval_mat)
    return fondi, min(scan.iva_credito, scan.iva_debito)


def _contra_classify(attivo_rows, passivo_rows, dedup=None) -> ContraScan:
    """Classify + sum deduplicated scan rows into the contra-netting aggregates.
    Rows are (code, desc_upper, amount); the SIDE each row came from is ground
    truth for attivo_total/IVA, while fondi ammortamento count from EITHER side.

    Besides the leaf sums, capture the document's own PRINTED level-1 subtotals
    ("IMMOBILIZZAZIONI IMMATERIALI/MATERIALI", max amount wins so a fondi-section
    header reusing the same caption never shadows the gross) — leaf-level sums
    under-count on layouts with truncated leaf descriptions, the printed anchors
    do not.

    ``dedup`` partitions the rows into the level actually summed; None keeps
    the historical prefix-based _dedup_parent_child (see _select_dedup)."""
    dedup = dedup or _dedup_parent_child
    Z = Decimal('0')
    g02 = g03 = att_total = f_im = f_mat = iva_c = iva_d = f_att = Z
    anch02 = anch03 = None

    # Printed subtotal anchors come from the RAW rows: dedup drops exactly the
    # mastro rows that carry them (their children reconcile). Skip the B-detail
    # captions that merely CONTAIN the subtotal phrase — 'ALTRE ...' and
    # '... IN CORSO' (immobilizzazioni in corso, B.II.5) — so that when the true
    # subtotal line is dropped by a noisy OCR pass we anchor to nothing (→ no-op)
    # rather than to a partial sub-line.
    for _c, d, a in attivo_rows:
        if _is_fondo_amm(d) or d.startswith('ALTRE') or 'IN CORSO' in d:
            continue
        if 'IMMOBILIZZAZIONI IMMATERIALI' in d:
            anch02 = a if anch02 is None else max(anch02, a)
        elif 'IMMOBILIZZAZIONI MATERIALI' in d:
            anch03 = a if anch03 is None else max(anch03, a)

    sval_rows = []                       # fondo svalutazione immobilizz. (either side)
    for _c, d, a in dedup(list(attivo_rows)):
        if _is_fondo_amm(d):
            continue                        # fondi handled from RAW rows below
        if _is_fondo_svalut_immob(d):
            sval_rows.append((abs(a), d))   # contra-asset: exclude from att_total
            continue
        att_total += a
        if _is_iva_line(d):
            iva_c += a
            continue
        f = _classify_sp_attivo(d)
        if f == 'gross_sp02':
            g02 += a
        elif f == 'gross_sp03':
            g03 += a
    for _c, d, a in dedup(list(passivo_rows)):
        if _is_fondo_amm(d):
            continue
        if _is_fondo_svalut_immob(d):
            sval_rows.append((abs(a), d))
            continue
        if _is_iva_line(d):
            iva_d += a

    def _reduce_fondi(raw_rows):
        """(total, immat) for one side's fondi rows [(code, desc, abs_amount)],
        taken PRE-dedup so the printed sub-aggregate captions survive.

        total  = the GRAND aggregate ('FONDI AMMORTAMENTO IMMOBILIZ', no category
                 qualifier) when the document prints one, else the deduplicated leaf
                 sum (parent/child collapsed so nothing double-counts).
        immat  = the IMMATERIALI sub-aggregate ('FONDI AMMORT. IMMOBILIZZAZ. IMM' /
                 'F/AMM IMMOBILIZZAZIONI IMMAT.') when printed, else the immat-
                 classified leaf sum. mat = total - immat.

        Reading the sub-aggregate from the RAW rows is the fix: the generic
        _dedup_parent_child keeps children and DROPS the parent, so post-dedup the
        immat sub-aggregate is gone and the surviving LEAVES are truncated
        ("F/AMM.LIC. D'USO SOF. A TEM. IND") and self-misclassify to materiali →
        the whole immateriali fondo leaks into materiali (budget_395). Anchoring on
        the printed sub-aggregate keeps the split correct without depending on leaf
        captions, while the deduped leaf sum keeps the TOTAL exact where there is a
        3-level tree with a grand total too (budget_343: 41 > 4101 > leaves)."""
        if not raw_rows:
            return Z, Z
        deduped = dedup(list(raw_rows))
        leaf_total = sum(a for _c, _d, a in deduped)
        grand_aggs = [a for _c, d, a in raw_rows if _is_fondo_aggregate(d)]
        total = max(grand_aggs) if grand_aggs else leaf_total
        immat_aggs = [a for _c, d, a in raw_rows if _is_fondo_immat_aggregate(d)]
        if immat_aggs:
            im = min(max(immat_aggs), total)
        else:
            im = sum(a for _c, d, a in deduped if _fondo_is_immat(d))
        return total, min(im, total)

    fondi_att_raw = [(c, d, abs(a)) for c, d, a in attivo_rows if _is_fondo_amm(d)]
    fondi_pas_raw = [(c, d, abs(a)) for c, d, a in passivo_rows if _is_fondo_amm(d)]
    t_att, im_att = _reduce_fondi(fondi_att_raw)
    t_pas, im_pas = _reduce_fondi(fondi_pas_raw)
    f_att = t_att
    f_im = im_att + im_pas
    f_mat = (t_att - im_att) + (t_pas - im_pas)
    has_agg = any(_is_fondo_aggregate(d) for _c, d, _a in fondi_att_raw + fondi_pas_raw)
    # Fondo svalutazione immobilizzazioni: a plain leaf sum split immat/mat — it
    # has its own 'FONDI SVALUTAZIONE ...' captions, kept in a SEPARATE stream so
    # the ammortamento aggregate helpers never shadow a svalutazione leaf.
    sval_im = sum(a for a, d in sval_rows if _fondo_is_immat(d))
    sval_mat = sum(a for a, d in sval_rows if not _fondo_is_immat(d))
    return ContraScan(g02, g03, att_total, f_im, f_mat, iva_c, iva_d,
                      f_att, anch02, anch03, has_agg, sval_im, sval_mat)


_CONTRA_TXT_ROW_RE = re.compile(
    r'^\s*(?P<code>[\d./*]+)?\s*(?P<desc>[A-ZÀ-Ù][^\d\n]*?)\s+'
    r'(?P<amt>-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$', re.MULTILINE)

# Multi-match segment: finds EVERY "code description amount" triple anywhere on a
# line, not just one anchored at EOL. Vision-OCR of a two-column bilancio di
# verifica merges attivo+passivo onto one physical line ("35 CONTI ERARIALI
# 50.794,41  41 FONDI AMMORTAMENTO IMMOBILIZZ 400.473,85"), which the single-row
# EOL-anchored regex above cannot split. Used only as a fallback when that regex
# yields nothing (real scanned PDFs), so text-layer scans are unaffected.
_CONTRA_TXT_SEG_RE = re.compile(
    r'(?P<code>\d[\d./]*)\s+(?P<desc>[A-ZÀ-Ù][^\d\n]*?)\s+'
    r'(?P<amt>-?\d{1,3}(?:\.\d{3})*,\d{2})')


def _contra_rows(file_path: str, text: Optional[str] = None):
    """Acquire (attivo_rows, passivo_rows, from_ocr) for the contra-netting scan.

    Generated PDFs: coordinate mode — the SP pages' two physical columns are
    split with the same helpers the best-effort parser uses (`_be_split` +
    `_be_collect_side`), so each row carries its true side (from_ocr=False,
    complete capture). Scanned PDFs (no word layer): line-parse the OCR `text`;
    the side is unknown and capture is partial, so rows are assigned by NATURE
    (fondi → passivo bucket, attivo-rule matches → attivo) and from_ocr=True —
    lower fidelity, which the caller's self-validation gate absorbs (a misread
    scan fails reconciliation → no-op, never corruption).
    Returns None when neither mode yields rows.
    """
    # --- coordinate mode -----------------------------------------------------
    try:
        import fitz
        doc = fitz.open(file_path)
        att, pas = [], []
        for page in doc:
            up = page.get_text().upper()
            flat = re.sub(r'\s+', '', up)
            # fiscal-reconciliation appendix pages are not the SP
            if 'RIDETERMINAZIONE' in flat or 'REDDITOIMPONIBILE' in flat:
                continue
            # 'Dettaglio ratei, risconti e competenze' breakdown appendices carry
            # the 'Conti Patrimoniali' header, so they pass the PATRIMONIAL test
            # below, yet they only RE-LIST fragments already totalled in the main
            # prospetto — scanning them double-counts (budget_210 reprints the
            # ricerca-sviluppo fondo on two such pages). Match the specific
            # appendix title and never a genuine prospetto ('SITUAZIONE/STATO
            # PATRIMONIALE'), so a real SP page like 'STATO PATRIMONIALE
            # (DETTAGLIO COMPLETO)' is kept.
            if ('SITUAZIONEPATRIMONIAL' not in flat
                    and 'STATOPATRIMONIAL' not in flat
                    and ('DETTAGLIORATEI' in flat or 'DETTAGLIORISCONT' in flat
                         or 'DETTAGLIOCOMPETENZE' in flat)):
                continue
            is_sp = ('PATRIMONIAL' in flat) or (
                'ATTIVIT' in up and 'PASSIVIT' in up and 'CONTOECONOMICO' not in flat)
            is_ce = ('CONTOECONOMICO' in flat) or ('COSTI' in up and 'RICAVI' in up)
            if not is_sp or is_ce:
                continue
            words = page.get_text('words')
            if not words:
                continue
            split = _be_split(words)
            if split is None:
                split = page.rect.width / 2
            att += _be_collect_side(words, -1e9, split)
            pas += _be_collect_side(words, split, 1e9)
        doc.close()
        if att or pas:
            return att, pas, False
    except Exception:
        pass

    # --- OCR-text fallback (scanned PDFs) ------------------------------------
    if not text:
        return None
    up = text.upper()
    # Vision OCR of a two-column sheet emits a markdown-ish table: cells separated
    # by '|' pipes ("41 | | FONDI AMMORTAMENTO IMMOBILIZZ | 400.473,85"). Collapse
    # pipes (and other table glyphs) to spaces so the code/desc/amount segment
    # regex sees a plain "code desc amount" stream on each line.
    up = re.sub(r'[|＋+]+', ' ', up)
    # keep only the SP region: cut at the CE section header
    m = re.search(r'CONTO\s+ECONOMICO', up)
    if m:
        up = up[:m.start()]
    def _assign(code, desc, amount, att, pas):
        desc = desc.strip()
        if len(desc) < 3 or 'TOTALE' in desc or 'PAREGGIO' in desc:
            return
        code = re.sub(r'\D', '', (code or '').strip().strip('./*'))
        entry = (code, desc, abs(amount))
        if _is_fondo_amm(desc):
            pas.append(entry)          # side irrelevant for fondi (contra either way)
        elif _is_iva_line(desc) and ('VENDIT' in desc or 'DEBITO' in desc):
            pas.append(entry)
        else:
            f = _classify_sp_attivo(desc)
            # text mode has no column ground truth: count ONLY explicit
            # attivo-rule matches (never the sp06 default, which would suck
            # passivo/CE lines into the attivo total and defeat the gate)
            if f != 'sp06' or _is_iva_line(desc):
                att.append(entry)

    # Multi-match segment extraction: finds every code/desc/amount triple on each
    # line, so it reads both columns of a two-column vision-OCR sheet AND ordinary
    # single-column rows. It is a strict superset of the EOL-anchored single-row
    # regex, so use it as the primary OCR parser (the single-row one returned early
    # on the first single-column match and never split the merged columns).
    att, pas = [], []
    for seg in _CONTRA_TXT_SEG_RE.finditer(up):
        try:
            amount = _parse_amount(seg.group('amt'))
        except Exception:
            continue
        _assign(seg.group('code'), seg.group('desc'), amount, att, pas)
    if att or pas:
        return att, pas, True

    # Fallback: EOL-anchored single-row (descriptions that start mid-line without a
    # leading code — the segment regex requires a leading digit).
    att, pas = [], []
    for row in _CONTRA_TXT_ROW_RE.finditer(up):
        try:
            amount = _parse_amount(row.group('amt'))
        except Exception:
            continue
        _assign(row.group('code'), row.group('desc'), amount, att, pas)
    if att or pas:
        return att, pas, True
    return None


def _reduce_debts(bs: Dict[str, Decimal], amount: Decimal) -> Decimal:
    """Remove `amount` from the debt buckets: sp16g (altri, where misclassified
    fondi land) first — mirrored on the sp16 aggregate to keep sub-field
    consistency — then the sp16 aggregate residual, then the sp17 side. Floors
    at 0 everywhere; returns the mass actually removed."""
    Z = Decimal('0')
    removed = Z
    for sub, agg in (('sp16g_altri_debiti_breve', 'sp16_debiti_breve'),
                     ('sp16e_debiti_tributari_breve', 'sp16_debiti_breve'),
                     ('sp17g_altri_debiti_lungo', 'sp17_debiti_lungo')):
        if removed >= amount:
            break
        take = min(amount - removed, bs.get(sub, Z))
        if take > Z:
            bs[sub] = bs.get(sub, Z) - take
            bs[agg] = max(Z, bs.get(agg, Z) - take)
            removed += take
    for agg in ('sp16_debiti_breve', 'sp17_debiti_lungo'):
        if removed >= amount:
            break
        take = min(amount - removed, bs.get(agg, Z))
        if take > Z:
            bs[agg] = bs.get(agg, Z) - take
            removed += take
    return removed


def net_contra_accounts(winner_bs: Dict[str, Decimal], file_path: str,
                        text: Optional[str] = None,
                        declared: Optional[dict] = None):
    """Deterministic contra-netting overlay for route-C trial balances.

    Re-reads the source document, sums fondi ammortamento (parent/child
    deduplicated) and the offsettable IVA position, then — deterministic
    authority — OVERWRITES sp02/sp03 with the scanned net values and removes
    from the debt buckets exactly the passivo excess over the new attivo
    (capped at the fondi mass), so an already-net extraction is passed through
    untouched (idempotent) and a gross one comes out net and balanced.

    Self-validation gates (either fails -> no-op, sheet returned unchanged):
      1. netted contra > 1% of the declared total (there is real contra mass);
      2. the scan's gross attivo reconciles to the declared TOTALE ATTIVO /
         pareggio within 0.5% (proves we read the right magnitudes).

    Returns (winner_bs, netted_contra). netted_contra > 0 also when the sheet
    needed no field change (already net): the caller must still reduce the
    DECLARED anchor by it, because the document's printed totals are GROSS.
    """
    Z = Decimal('0')

    def _mark(bs, detected, applied, reason):
        """Record the scan outcome on the sheet so downstream reliability
        reporting can distinguish 'no contra mass' from 'contra mass found but
        NOT applied'. Underscore keys are passed through by _map_sc_keys and
        ignored by _create_balance_sheet (which reads only ORM columns), the
        same mechanism _plug_residual / _netted_contra already rely on."""
        bs['_contra_detected'] = detected
        bs['_contra_applied'] = applied
        bs['_contra_reason'] = reason
        return bs

    dedup_label = 'existing'
    try:
        decl_total = contra_declared_total(declared)
        if not decl_total or decl_total <= 0:
            return _mark(winner_bs, Z, Z, 'nessun totale dichiarato'), Z
        rows = _contra_rows(file_path, text=text)
        if not rows:
            return _mark(winner_bs, Z, Z, 'scan non disponibile'), Z
        att_rows, pas_rows, from_ocr = rows
        # Which hierarchy level to sum is decided by RECONCILIATION against the
        # document's own printed total, never by code prefixes: AGO uses two
        # disjoint code families (8-digit mastri, 9-digit sub-accounts) that are
        # not prefixes of each other, so the historical dedup summed both.
        dedup_label, dedup_fn, dedup_reconciled = _select_dedup(att_rows, decl_total)
        scan = _contra_classify(att_rows, pas_rows, dedup=dedup_fn)
        logger.info("contra-netting: partizione '%s' (riconcilia=%s)",
                    dedup_label, dedup_reconciled)
        iva_offset = min(scan.iva_credito, scan.iva_debito)
        # Contra to immobilizzazioni = fondo ammortamento + fondo svalutazione
        # immobilizzazioni, per side (both reduce B.I/B.II net book value).
        immat_contra = scan.fondi_immat + scan.sval_immat
        mat_contra = scan.fondi_mat + scan.sval_mat
        fondi_total = immat_contra + mat_contra
        netted = fondi_total + iva_offset
        if netted <= decl_total * Decimal('0.01'):
            return _mark(winner_bs, netted, Z,
                         'massa contro sotto soglia'), Z     # gate 1
        anchored = False
        if abs(scan.attivo_total - decl_total) > decl_total * Decimal('0.005'):
            # Gate 2 failed: the FULL attivo sum is polluted (4-sezioni layouts
            # print partitari detail rows whose short codes collide with real
            # mastri after digit-normalisation). Fall back to ANCHORED mode:
            # trust the document's own printed IMMOBILIZZAZIONI subtotals as the
            # gross, provided (a) the fondi sit on the PASSIVO side (an already-
            # net doc lists them on the attivo → anchors would be NET → double
            # netting) and (b) each fondi mass fits under its anchor.
            def _fits(fondi, anchor):
                if fondi <= Z:
                    return True
                return (anchor is not None
                        and fondi <= anchor + max(Decimal('2'),
                                                  anchor * Decimal('0.005')))
            fondi_passivo_only = scan.fondi_att <= fondi_total * Decimal('0.01')
            # Anchored mode trusts a bottom-up fondi total. From a TEXT-LAYER scan
            # (from_ocr=False) capture is complete and reliable, so a single anchor
            # + leaf-summed fondi is enough (budget_405: specific fondi, no
            # grand-total line). From a SCANNED OCR pass capture is PARTIAL and
            # stochastic, so demand strong corroboration or NO-OP (→ user corrects
            # in Rettifiche) — never write a wrong net immobilizzazioni:
            #   • the printed grand-total aggregate line was captured; AND
            #   • BOTH printed immobilizzazioni subtotals (immat + mat) are present
            #     (a missing one means the OCR dropped a subtotal → unreliable); AND
            #   • the immateriali fondo was actually located (fondi_immat > 0) — else
            #     the whole aggregate would wrongly net onto materiali only.
            if from_ocr:
                reliable = (scan.has_aggregate
                            and scan.anchor_sp02 is not None
                            and scan.anchor_sp03 is not None
                            and scan.fondi_immat > Z)
            else:
                reliable = (scan.anchor_sp02 is not None
                            or scan.anchor_sp03 is not None)
            if (fondi_passivo_only and reliable
                    and _fits(immat_contra, scan.anchor_sp02)
                    and _fits(mat_contra, scan.anchor_sp03)):
                anchored = True
            else:
                logger.info(
                    "contra-netting: scan attivo %s non riconcilia col totale "
                    "dichiarato %s e niente anchor affidabili — no-op",
                    scan.attivo_total, decl_total)
                return _mark(
                    winner_bs, netted, Z,
                    'contro rilevati ma non applicati: scan non riconcilia'), Z
    except Exception as exc:
        logger.warning("contra-netting: scan fallito (%s) — no-op", exc)
        return _mark(winner_bs, Z, Z, f'scan fallito: {exc}'), Z

    # ---- apply (deterministic authority) ------------------------------------
    # IVA gross-evidence gate: the IVA collapse is a DELTA (not idempotent like
    # the sp02/sp03 overwrite), so it applies only when the winner's pre-apply
    # total still sits at the declared GROSS magnitude — proof nothing was
    # collapsed yet. An already-net / partially-net sheet skips the IVA delta.
    # Snapshot every field this phase can mutate: a raise mid-apply must never
    # leave winner_bs half-netted with no _contra_* marker on it (silent
    # masking) — roll back to this snapshot on failure so the sheet is
    # byte-identical to its pre-apply state.
    _pre_apply = dict(winner_bs)
    try:
        pre_total = winner_bs.get('totale_attivo', Z)
        apply_iva = (iva_offset > Z
                     and abs(pre_total - decl_total) <= decl_total * Decimal('0.005'))

        old_02 = winner_bs.get('sp02_immob_immateriali', Z)
        old_03 = winner_bs.get('sp03_immob_materiali', Z)
        if anchored:
            # Anchored mode: printed subtotal − (fondo amm + svalutazione). A side
            # without an anchor is left untouched (never zeroed by an absent leaf sum).
            new_02 = (max(Z, scan.anchor_sp02 - immat_contra)
                      if scan.anchor_sp02 is not None else old_02)
            new_03 = (max(Z, scan.anchor_sp03 - mat_contra)
                      if scan.anchor_sp03 is not None else old_03)
        else:
            # Reconciled scan: prefer the document's PRINTED immobilizzazioni subtotal
            # (anchor) over the keyword-summed gross. The keyword sum drops sub-lines
            # the attivo classifier does not recognise (budget_210: SITO WEB,
            # progettazioni, spese pluriennali → gross_sp02 205.600 vs printed
            # 223.901,20), which would under-net the net immobilizzazioni. Fall back to
            # the keyword gross only when the document prints no subtotal.
            base_02 = scan.anchor_sp02 if scan.anchor_sp02 is not None else scan.gross_sp02
            base_03 = scan.anchor_sp03 if scan.anchor_sp03 is not None else scan.gross_sp03
            new_02 = max(Z, base_02 - immat_contra)
            new_03 = max(Z, base_03 - mat_contra)
        winner_bs['sp02_immob_immateriali'] = new_02
        winner_bs['sp03_immob_materiali'] = new_03
        att_delta = (new_02 + new_03) - (old_02 + old_03)
        winner_bs['totale_attivo'] = winner_bs.get('totale_attivo', Z) + att_delta

        if apply_iva:
            # collapse the offsettable IVA: net erario position stays on the larger
            # side, the smaller side is dropped from crediti and debiti tributari.
            cred = winner_bs.get('sp06_crediti_breve', Z)
            take = min(iva_offset, cred)
            winner_bs['sp06_crediti_breve'] = cred - take
            winner_bs['totale_attivo'] -= take
            winner_bs['totale_passivo'] = (winner_bs.get('totale_passivo', Z)
                                           - _reduce_debts(winner_bs, take))

        # balance-invariant fondi removal from the debt buckets: exactly the passivo
        # excess over the (new, net) attivo, capped at the fondi mass — 0 when the
        # extractor had already netted, the full fondi mass when it was gross.
        excess = winner_bs.get('totale_passivo', Z) - winner_bs['totale_attivo']
        to_remove = min(max(Z, excess), fondi_total)
        if to_remove > Z:
            winner_bs['totale_passivo'] = (winner_bs.get('totale_passivo', Z)
                                           - _reduce_debts(winner_bs, to_remove))
        logger.info(
            "contra-netting: nettati %s (fondi immat %s + mat %s + IVA %s); "
            "sp02 %s→%s, sp03 %s→%s", netted, scan.fondi_immat, scan.fondi_mat,
            iva_offset, old_02, new_02, old_03, new_03)
    except Exception as exc:
        # Restore winner_bs to its exact pre-apply state: a partial mutation
        # here would leave sp02/sp03/totale_attivo/debt buckets half-netted
        # with NO _contra_* marker set, which downstream reliability reporting
        # would read as 'no scan ran on this route' (DERIVED) instead of the
        # failed-mid-application UNRELIABLE it actually is.
        winner_bs.clear()
        winner_bs.update(_pre_apply)
        logger.warning(
            "contra-netting: applicazione fallita (%s) — rollback allo stato "
            "pre-apply", exc, exc_info=True)
        return _mark(winner_bs, netted, Z,
                     f'applicazione fallita: {exc}'), Z

    _mark(winner_bs, netted, netted, f'applicato ({dedup_label})')
    return winner_bs, netted


def _hier_reconstruct(pages_data, full: str):
    """Reconstruct a balanced IV-CEE sheet from level-1 mastri. Returns (bs, ce) or
    None when the layout does not reconcile (caller then keeps the best-effort result).
    """
    Z = Decimal('0')
    att, pas, cos, ric = [], [], [], []
    prior_pn = Z
    unclassified = []          # (desc, amount, assigned_field)
    for words, is_sp, is_ce, up, width in pages_data:
        split = _be_split(words)
        if split is None:
            split = width / 2
        left = _hier_collect(words, -1e9, split)
        right = _hier_collect(words, split, 1e9)
        if is_sp and not is_ce:
            att += left
            pas += right
            # A trial balance often does NOT consolidate the previous year's
            # result into the capital/reserve accounts: it is printed as a
            # code-less row in the SP footer ("Utile esercizio precedente").
            # It is patrimonio netto (utili portati a nuovo) — a credit balance
            # on the passivo side, a debit balance on the attivo side.
            prior_pn += _hier_prior_result(words, split, 1e9)
            prior_pn -= _hier_prior_result(words, -1e9, split)
        elif is_ce and not is_sp:
            if ('COSTI' in up[:400] and 'RICAVI' in up[:400]
                    and up[:400].find('RICAVI') < up[:400].find('COSTI')):
                cos += right
                ric += left
            else:
                cos += left
                ric += right

    ma, mp = _hier_lvl1(att), _hier_lvl1(pas)
    mc, mr = _hier_lvl1(cos), _hier_lvl1(ric)
    if len(ma) < 4 or len(mp) < 4:
        return None                       # not a clean two-column mastri layout

    bs: Dict[str, Decimal] = {}
    netted = Z

    def addb(k, v):
        bs[k] = bs.get(k, Z) + v

    def _net_fondo(code, desc, amount, side_rows):
        """Net a fondi-ammortamento mastro SPLITTING immat/mat: the level-1
        caption ("FONDI AMMORTAMENTO IMMOBILIZ") is category-blind, so read the
        split from its DIRECT child rows (level-2 mastri: "FONDI AMMORT.
        IMMOBILIZZAZ. IMM" → sp02) when they reconcile to the mastro amount;
        otherwise fall back to the mastro's own classification. Unattributed
        mass keeps netting sp03 (the historical behaviour)."""
        nonlocal netted
        im = Z
        if code:
            desc_rows = [(c, d2, a2) for c, d2, a2 in side_rows
                         if c != code and c.startswith(code)]
            direct = [(c, d2, a2) for c, d2, a2 in desc_rows
                      if not any(o != c and c.startswith(o)
                                 for o, _d3, _a3 in desc_rows)]
            covered = sum(a2 for _c2, _d2, a2 in direct)
            tol = max(Decimal('2'), abs(amount) * Decimal('0.01'))
            if direct and abs(covered - amount) <= tol:
                im = sum(a2 for _c2, d2, a2 in direct
                         if _classify_sp_passivo(d2) == 'depr_sp02')
        if im == Z and _classify_sp_passivo(desc) == 'depr_sp02':
            im = amount
        addb('sp02', -im)
        addb('sp03', -(amount - im))
        netted += amount

    for _c, d, a in ma:
        if _is_fondo_amm(d):
            _net_fondo(_c, d, a, att)
        else:
            f = _classify_sp_attivo(d)
            addb({'gross_sp02': 'sp02', 'gross_sp03': 'sp03', 'gross_sp04': 'sp04'}.get(f, f), a)
    for _c, d, a in mp:
        if _is_fondo_amm(d):
            _net_fondo(_c, d, a, pas)
            continue
        t = _classify_sp_passivo(d)
        if t == 'equity_total':
            addb('sp11' if (_kw_match(d, ['CAPITALE']) and 'RISERV' not in d) else 'sp12', a)
        elif t in ('depr_sp02', 'depr_sp03', 'depr_sp04'):
            addb(t.replace('depr_', ''), -a)
            netted += a
        elif t == 'deduct_crediti':
            addb('sp06', -a)
            netted += a
        elif t in ('sp14', 'sp15', 'sp18'):
            addb(t, a)
        else:
            addb('sp16', a)

    # Unconsolidated prior-year result -> utili (perdite) portati a nuovo.
    if prior_pn:
        addb('sp12', prior_pn)

    # CE: every cost mastro lands in a cost field and every revenue mastro in a
    # revenue field, so the net (ricavi - costi) is sign-correct regardless of the
    # exact bucket (used both for the import P&L and for the reconciliation check).
    ce: Dict[str, Decimal] = {}

    def adde(k, v):
        ce[k] = ce.get(k, Z) + v

    for _c, d, a in mc:
        f = _classify_ce_costi(d) or _resolve_ce_field(d, 'costi')
        if f is None:
            f = fallback_field('ce')
            unclassified.append((d, a, 'ce'))
        if f == 'ce01_return':
            adde('ce01', -a)
        elif f == 'ce10_close':
            adde('ce10', -a)
        elif f == 'ce13_cost':
            adde('ce15', a)
        elif f in _CE_HIER_SUBPARENT:
            adde(_CE_HIER_SUBPARENT[f], a)
        else:
            adde(f, a)
    for _c, d, a in mr:
        f = _classify_ce_ricavi(d) or _resolve_ce_field(d, 'ricavi')
        if f is None:
            f = 'ce04'
            unclassified.append((d, a, 'ce'))
        if f == 'ce10_close':
            adde('ce10', -a)
        else:
            adde(f, a)

    att_sum = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)

    # Mass assigned by fallback rather than recognised. Only the MATERIAL part is
    # reported: below the threshold a generic bucket is a legitimate label; above
    # it the composition is guesswork and must be visible. fallback_bucket is the
    # single policy entry point, called here where the total is finally known.
    material = Z
    for _desc, _amt, _stmt in unclassified:
        _field, _severity = fallback_bucket(_desc, _stmt, _amt, att_sum)
        if _severity == 'recorded':
            material += abs(_amt)
    bs['_unclassified_mass'] = material

    pas_sum = sum((bs.get(k, Z) for k in ('sp11', 'sp12', 'sp14', 'sp15', 'sp16', 'sp17', 'sp18')), Z)
    sp13 = att_sum - pas_sum               # result as the SP gap → attivo == passivo

    # --- validation: keep ONLY when it genuinely reconciles ---
    up1 = re.sub(r'\s+', ' ', full.upper())
    flat1 = re.sub(r'\s+', '', full.upper())

    def _ft(spaced, flat):
        if spaced in up1:
            return _be_amount(up1.split(spaced, 1)[1][:40])
        if flat in flat1:
            return _be_amount(flat1.split(flat, 1)[1][:40])
        return None

    # Prefer the rightmost coordinate-backed ``TOTALE ATTIVITA`` printed in the
    # SP footer.  On adjusted four-column statements the linear text is laid out
    # as ``saldo non rettificato / rettifiche / saldo finale``: ``_ft`` therefore
    # sees the first (pre-adjustment) value, while every mastro above is read from
    # the last (final) column.  Comparing those different columns rejects an
    # otherwise exact reconstruction (budget_588).  Do not use ``PAREGGIO`` here:
    # on a loss it includes the perdita parked on the attivo side, while the
    # gross asset mastri correctly reconcile to ``TOTALE ATTIVITA`` (343/348).
    final_attivi = []
    for words, is_sp, is_ce, _up, width in pages_data:
        if not is_sp or is_ce:
            continue
        split = _be_split(words) or width / 2
        for lo, hi in ((-1e9, split), (split, 1e9)):
            for row_words in _be_cluster_physical_rows(words, lo, hi):
                tokens = [w[4].strip() for w in row_words if w[4].strip()]
                caption = ' '.join(tokens).upper()
                if 'TOTALE' not in caption or 'ATTIVIT' not in caption:
                    continue
                amounts = [_parse_amount(token) for token in tokens
                           if _BE_AMT_RE.fullmatch(token)]
                if amounts and amounts[-1] > 0:
                    final_attivi.append(amounts[-1])

    tot_att = final_attivi[-1] if final_attivi else _ft(
        'TOTALE ATTIV', 'TOTALEATTIV')
    if not tot_att or tot_att <= 0:
        return None
    tol = max(Decimal('50'), Decimal('0.005') * tot_att)
    # (1) gross attivo (net classified + fondi netted back) matches the declared total
    if abs((att_sum + netted) - tot_att) > tol:
        return None
    # (2) the SP result gap equals the CE result (ricavi - costi); otherwise the
    #     passivo composition is wrong and we must not trust the gap as sp13.
    ce_result = sum(ric_a for _c, _d, ric_a in mr) - sum(cos_a for _c, _d, cos_a in mc)
    if abs(sp13 - ce_result) > tol:
        return None

    bs['sp13'] = sp13
    bs['totale_attivo'] = att_sum
    bs['totale_passivo'] = att_sum
    bs['_plug_residual'] = Z
    # This result is independently corroborated by final-column SP controls and
    # the CE result.  Do not let the later generic declared-total reader replace
    # it with the first (pre-adjustment) column or interpret the adjustment/final
    # columns as a comparative year.
    bs['_skip_declared_reconcile'] = True
    return bs, ce


# CE sub-field → parent aggregate (the EBIT/profit formula reads the parent). Mirrors
# the mapping in extract_contrapposte_best_effort so a personale/ammortamenti detail
# rolls into ce08/ce09 instead of being lost.
_CE_HIER_SUBPARENT = {
    'ce08a_tfr': 'ce08', 'ce08b': 'ce08', 'ce08c': 'ce08', 'ce08d': 'ce08',
    'ce09a': 'ce09', 'ce09b': 'ce09', 'ce09c': 'ce09', 'ce09d': 'ce09',
}


# CE sub-field -> (full DB detail key, parent aggregate). Personale (ce08a-d) and
# ammortamenti (ce09a-d) are detail ("di cui") lines: the EBIT/profit formula reads
# only the aggregates ce08/ce09, so each sub-field is rolled into its parent
# aggregate AND stored under its full DB key (mirrors build_iv_cee). Promoted to
# module level (was a local dict inside extract_contrapposte_best_effort) so
# build_ce_from_vision reads the same single definition.
_CE_SUBFIELD_PARENT = {
    'ce08a_tfr': ('ce08a_tfr_accrual', 'ce08'),
    'ce08b': ('ce08b_salari_stipendi', 'ce08'),
    'ce08c': ('ce08c_oneri_sociali', 'ce08'),
    'ce08d': ('ce08d_altri_costi_personale', 'ce08'),
    'ce09a': ('ce09a_ammort_immateriali', 'ce09'),
    'ce09b': ('ce09b_ammort_materiali', 'ce09'),
    'ce09c': ('ce09c_svalutazioni', 'ce09'),
    'ce09d': ('ce09d_svalutazione_crediti', 'ce09'),
}


def classify_page_section(page_text: str) -> Optional[Tuple[bool, bool]]:
    """(is_sp, is_ce) per una pagina di contrapposte, o None se la pagina va saltata.

    Estratta verbatim dal ciclo pagine di extract_contrapposte_best_effort perché il
    riscatto vision ha bisogno della stessa classificazione senza ri-eseguire l'intera
    estrazione. `None` significa "salta la pagina" (appendice fiscale di
    rideterminazione), che NON e' la stessa cosa di (False, False) — quest'ultima e'
    una pagina reale che non appartiene a nessuna sezione.
    """
    up = page_text.upper()
    flat = up.replace(' ', '')
    # Classify the page by its FIRST section title line — a single page may
    # carry a subtitle naming both ("Stato Patrimoniale e Conto Economico"),
    # so the title line that comes first decides.
    title = ''
    for l in page_text.split('\n'):
        lu = l.strip().upper()
        if 'PATRIMONIAL' in lu or 'ECONOMIC' in lu:
            title = lu
            break
    # Fiscal-reconciliation appendices ("RIDETERMINAZIONE RISULTATO D'ESERCIZIO"
    # for II.DD./IRAP, with VARIAZIONI IN AUMENTO/DIMINUZIONE) re-list cost/revenue
    # accounts but are NOT the income statement — skip them so they don't pollute
    # the CE (they otherwise match the loose COSTI+RICAVI test below).
    if ('RIDETERMINAZIONE' in flat or 'REDDITOIMPONIBILE' in flat
            or ('VARIAZIONIINAUMENTO' in flat and 'VARIAZIONIINDIMINUZIONE' in flat)):
        return None
    if 'PATRIMONIAL' in title and 'ECONOMIC' not in title:
        return True, False
    if 'ECONOMIC' in title and 'PATRIMONIAL' not in title:
        return False, True
    is_sp = ('PATRIMONIALE' in flat) or ('ATTIVIT' in up and 'PASSIVIT' in up and 'CONTOECONOMICO' not in flat)
    is_ce = ('CONTOECONOMICO' in flat) or ('COSTI' in up and 'RICAVI' in up)
    return is_sp, is_ce


def section_pages(file_path: str) -> Dict[str, List[int]]:
    """Indici pagina (0-based) che portano lo Stato Patrimoniale e il Conto Economico.

    Una pagina classificata come entrambe compare in entrambe le liste; una pagina da
    saltare (classify_page_section -> None) in nessuna.
    """
    out: Dict[str, List[int]] = {"sp": [], "ce": []}
    with fitz.open(file_path) as doc:
        for idx, page in enumerate(doc):
            verdict = classify_page_section(page.get_text())
            if verdict is None:
                continue
            is_sp, is_ce = verdict
            if is_sp:
                out["sp"].append(idx)
            if is_ce:
                out["ce"].append(idx)
    return out


# Classifiers map a mastro/subtotal DESCRIPTION to an IV-CEE field; the second
# element flags whether the match is specific enough to stop descending.
# Erano closure dentro extract_contrapposte_best_effort: promosse a funzioni di
# modulo perche' il riscatto vision (vision_rescue.py) classifica le stesse
# descrizioni senza ri-eseguire l'estrazione. Nessun cambiamento di regola.
def classify_attivo(desc_upper: str) -> Tuple[str, bool]:
    d = desc_upper
    # Some TeamSystem/ERP exports append the legal IV-CEE code after a run of
    # underscores (e.g. ``IMMOBILIZZAZIONI IMMATERIALI______BI``).  It is still
    # the explicit parent category, not an unknown generic caption: normalize
    # only these three exact suffixes so the hierarchy does not descend into
    # children and count the same mass again (AITEC 373/374/375).
    normalized = re.sub(r'_+(?:BIII|BII|BI)\s*$', '', d).strip()
    legal_parent = {
        'IMMOBILIZZAZIONI IMMATERIALI': 'sp02',
        'IMMOBILIZZAZIONI MATERIALI': 'sp03',
        'IMMOBILIZZAZIONI FINANZIARIE': 'sp04',
    }.get(normalized)
    if legal_parent:
        return legal_parent, True
    d = normalized
    # A malformed generic "IMMOBILIZZAZIONI ..." caption can accidentally
    # match MOBILI inside IMMOBILIZZAZIONI.  Descend to its specific children
    # (software/oneri pluriennali/etc.) unless the printed category is exact.
    if (d.startswith('IMMOBILIZZAZIONI')
            and d not in ('IMMOBILIZZAZIONI MATERIALI',
                          'IMMOBILIZZAZIONI IMMATERIALI',
                          'IMMOBILIZZAZIONI FINANZIARIE')):
        return 'sp06', False
    # Side is ground truth in a contrapposte layout: BANCHE on ATTIVO is cash,
    # not the generic-credit fallback used by the single-column classifier.
    if 'BANC' in d:
        return 'sp09', True
    if ('SCORTE' in d or 'MATERIE PRIME' in d or d == 'IMBALLAGGI'):
        return 'sp05', True
    f = _classify_sp_attivo(d)
    f = {'gross_sp02': 'sp02', 'gross_sp03': 'sp03', 'gross_sp04': 'sp04'}.get(f, f)
    return f, f != 'sp06'


def classify_passivo(desc_upper: str) -> Tuple[str, bool]:
    d = desc_upper
    if _is_fondo_amm(d):
        field = 'depr_sp02' if _fondo_is_immat(d) else 'depr_sp03'
        # A category-blind aggregate must descend into children; any uncovered
        # residual is retained by _be_reclassify under the material fallback.
        specific = any(k in d for k in _FONDO_CATEGORY_KW)
        return field, specific
    tag = _classify_sp_passivo(d)
    if tag == 'equity_total':
        if _kw_match(d, ['CAPITALE']):
            return 'sp11', True
        return 'sp12', True
    if tag in ('sp16', 'debt_bank', 'bank_avere'):
        # Split debiti by OIC creditor type from the description (banche / fornitori /
        # tributari / previdenza / ...) instead of collapsing everything into the sp16
        # aggregate (which the UI then renders entirely under "altri debiti"). 'debt_bank'
        # /'bank_avere' are already bank lines; otherwise read _debt_type. A recognised
        # type stops the descent; an unknown ('g') keeps descending to find a typed child.
        letter = ('a' if tag in ('debt_bank', 'bank_avere') or 'BANC' in d
                  else _debt_type(d.upper()))
        return 'sp16' + letter, letter != 'g'
    return tag, tag != 'sp16'


def classify_costi(desc_upper: str) -> Tuple[str, bool]:
    d = desc_upper
    f = _classify_ce_costi(d)
    return (f, True) if f else ('ce12', False)


def classify_ricavi(desc_upper: str) -> Tuple[str, bool]:
    d = desc_upper
    f = _classify_ce_ricavi(d)
    return (f, True) if f else ('ce04', False)


def extract_contrapposte_best_effort(file_path: str) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Best-effort extraction of a 2-column contrapposte trial balance.

    Declared totals are controls only.  Any residual from imperfect parsing is
    exposed as diagnostic metadata and the classified sides are left unchanged:
    a missing source row must never become cash or debt just to make the import
    balance.
    """
    doc = fitz.open(file_path)
    full = ""
    # Capture per-page (words, is_sp, is_ce, up, width) so the column collection can
    # be re-run in a code-less second pass without re-opening the PDF.
    pages_data: List[tuple] = []

    for page in doc:
        ptext = page.get_text()
        full += ptext + "\n"
        up = ptext.upper()
        verdict = classify_page_section(ptext)
        if verdict is None:
            continue
        is_sp, is_ce = verdict
        words = page.get_text('words')
        if not words:
            continue
        pages_data.append((words, is_sp, is_ce, up, page.rect.width))

    doc.close()
    use_garbled_reconstruction = any(
        _be_page_needs_coordinate_repair(words)
        for words, _is_sp, _is_ce, _up, _width in pages_data)

    def _collect_all(codeless: bool):
        """Collect attivo/passivo/costi/ricavi rows across all pages. In code-less
        mode each rowless-code row gets a globally-unique, fixed-width synthetic code
        (~NNNNNN) so it is its own non-prefixing root in _be_reclassify."""
        att_facts: List[ReconstructedRow] = []
        pas_facts: List[ReconstructedRow] = []
        cos_facts: List[ReconstructedRow] = []
        ric_facts: List[ReconstructedRow] = []
        ctr = [0]

        def _uniq(side_rows):
            res = []
            for c, d, a in side_rows:
                if c == '':
                    c = f"~{ctr[0]:06d}"
                    ctr[0] += 1
                res.append((c, d, a))
            return res

        def _ce_side_scores(rows):
            return (
                sum(1 for _c, desc, _a in rows if _classify_ce_costi(desc)),
                sum(1 for _c, desc, _a in rows if _classify_ce_ricavi(desc)),
            )

        def _ce_columns_are_swapped(left_rows, right_rows):
            """Choose COSTI/RICAVI from accounting captions, not header text order.

            PyMuPDF's linear text order does not necessarily match physical column
            order (budget_405 prints the words ``RICAVI COSTI`` but costs are on the
            left).  Scoring the already separated row descriptions is stable also on
            continuation pages where one physical column is empty.
            """
            left_cost, left_revenue = _ce_side_scores(left_rows)
            right_cost, right_revenue = _ce_side_scores(right_rows)
            direct = left_cost + right_revenue
            swapped = right_cost + left_revenue
            return swapped > direct

        if not use_garbled_reconstruction:
            att: List[Tuple[str, str, Decimal]] = []
            pas: List[Tuple[str, str, Decimal]] = []
            cos: List[Tuple[str, str, Decimal]] = []
            ric: List[Tuple[str, str, Decimal]] = []
            for page_number, (words, is_sp, is_ce, up, width) in enumerate(pages_data, 1):
                split = _be_split(words)
                if split is None and codeless:
                    split = _be_split_codeless(words)
                if split is None:
                    split = width / 2

                def _best_side(lo, hi):
                    legacy = _be_collect_side_legacy(
                        words, lo, hi, codeless=codeless)
                    coordinate = [
                        fact.legacy() for fact in _be_repair_parent_codes(
                            _be_collect_side_facts(
                                words, lo, hi, codeless=codeless,
                                page=page_number)
                        )
                    ]
                    # Coordinate clustering is a recovery path for baseline jitter;
                    # retain the proven legacy rows unless it recovers more physical
                    # facts from the same side.
                    return coordinate if len(coordinate) > len(legacy) else legacy

                left = _uniq(_best_side(-1e9, split))
                right = _uniq(_best_side(split, 1e9))
                if is_sp and not is_ce:
                    att += left
                    pas += right
                elif is_ce and not is_sp:
                    if _ce_columns_are_swapped(left, right):
                        cos += right
                        ric += left
                    else:
                        cos += left
                        ric += right
            return att, pas, cos, ric

        for page_number, (words, is_sp, is_ce, up, width) in enumerate(pages_data, 1):
            split = _be_split(words)
            if split is None and codeless:
                split = _be_split_codeless(words)
            if split is None:
                split = width / 2
            left = _be_collect_side_facts(
                words, -1e9, split, codeless=codeless, page=page_number)
            right = _be_collect_side_facts(
                words, split, 1e9, codeless=codeless, page=page_number)
            if is_sp and not is_ce:
                att_facts += left
                pas_facts += right
            elif is_ce and not is_sp:
                if _ce_columns_are_swapped(
                        [f.legacy() for f in left], [f.legacy() for f in right]):
                    cos_facts += right
                    ric_facts += left
                else:
                    cos_facts += left
                    ric_facts += right

        # Re-run hierarchy repair after concatenating pages: one account family
        # may start at the foot of page N and print its subtotal on page N+1.
        def _project(facts):
            return _uniq([f.legacy() for f in _be_repair_parent_codes(facts)])

        return (_project(att_facts), _project(pas_facts),
                _project(cos_facts), _project(ric_facts))

    attivo, passivo, costi, ricavi = _collect_all(codeless=False)
    # Code-less second pass: a clean two-column trial balance whose rows carry NO
    # account code (description+amount only, e.g. budget_367) collects zero rows in
    # the code-required pass. Retry code-less ONLY when the normal pass found nothing,
    # so coded files (the entire passing corpus) are never affected.
    if not attivo and not passivo:
        attivo, passivo, costi, ricavi = _collect_all(codeless=True)

    # Control rows are collected separately and never enter account
    # reclassification.  Their side / page coordinates make them safer than a
    # substring search over a corrupted linear text layer.
    controls: List[Tuple[str, str, ReconstructedRow]] = []
    for page_number, (words, is_sp, is_ce, _up, width) in enumerate(pages_data, 1):
        split = _be_split(words) or width / 2
        section = 'sp' if is_sp and not is_ce else ('ce' if is_ce and not is_sp else '')
        if not section:
            continue
        for side, lo, hi in (('left', -1e9, split), ('right', split, 1e9)):
            for fact in _be_collect_side_facts(
                    words, lo, hi, codeless=True, page=page_number,
                    include_controls=True):
                if fact.control:
                    controls.append((section, side, fact))

    # A contrapposte trial balance must have a balance-sheet side. Documents that
    # are economic-only (e.g. "PROSPETTO ECONOMICO per competenza" with just a
    # COSTI/RICAVI + fiscal-reconciliation table and no Stato Patrimoniale, budget_196)
    # collect zero attivo/passivo rows: refuse to fabricate a balance sheet by plugging
    # the pareggio into sp09/sp16 — raise so the caller can fall back to LLM extraction.
    if not attivo and not passivo:
        raise ValueError(
            "contrapposte best-effort: nessuno Stato Patrimoniale rilevato "
            "(documento solo economico?) — impossibile estrarre un bilancio deterministico"
        )

    Z = Decimal('0')
    bs: Dict[str, Decimal] = {}
    ce: Dict[str, Decimal] = {}

    def add(d, k, v):
        d[k] = d.get(k, Z) + v

    cl_att, cl_pas = classify_attivo, classify_passivo
    cl_cos, cl_ric = classify_costi, classify_ricavi

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
    # Track the contra-asset mass netted off the asset side. When fondi ammortamento /
    # svalutazione crediti are listed as separate PASSIVO accounts (GROSS presentation),
    # the declared TOTALE ATTIVO / pareggio is GROSS. Netting them off the assets while
    # anchoring the plug to that gross total opens a hole == the fondi magnitude, swept
    # into sp09/sp16 — the dominant cause of "QUADRATURA MASCHERATA" on gross-presentation
    # trial balances (budget_395/405/343/348/342). We accumulate the netted mass and
    # reduce iv_total by it below so the IV-CEE NET total matches the netted sums (plug ~ 0).
    # No-op when fondi sit on the asset side (e.g. AITEC) → netted_contra stays 0.
    netted_contra = Z
    for tag, amt in _be_reclassify(passivo, cl_pas):
        if tag in ('depr_sp02', 'depr_sp03', 'depr_sp04'):
            add(bs, tag.replace('depr_', ''), -amt)        # net fondi off the asset
            netted_contra += amt
        elif tag == 'deduct_crediti':
            add(bs, 'sp06', -amt)
            netted_contra += amt
        elif tag in ('sp11', 'sp12', 'sp14', 'sp15', 'sp18'):
            add(bs, tag, amt)
        elif len(tag) == 5 and tag.startswith('sp16') and tag[4] in 'abcdefg':
            # Typed debt: keep the aggregate sp16 (pareggio unchanged) AND emit the typed
            # sub-field under its full DB name so it survives _map_sc_keys and shows up split.
            add(bs, 'sp16', amt)
            add(bs, _DEBT_FIELD['breve'][tag[4]], amt)
        else:                                              # any unexpected tag → aggregate
            add(bs, 'sp16', amt)

    # --- CE ---
    # Personale (ce08a-d) and ammortamenti (ce09a-d) are detail ("di cui") lines:
    # the EBIT/profit formula reads only the aggregates ce08/ce09, so each sub-field
    # is rolled into its parent aggregate AND stored under its full DB key (mirrors
    # build_iv_cee). _be_reclassify emits a node at exactly one level (parent OR
    # children, never both), so this never double-counts. _CE_SUBFIELD_PARENT is a
    # module-level constant (defined next to _CE_HIER_SUBPARENT) so build_ce_from_vision
    # reads the same single definition.
    def ce_add(tag, amt):
        if tag == 'ce01_return':
            add(ce, 'ce01', -amt)
        elif tag == 'ce10_close':
            add(ce, 'ce10', -amt)
        elif tag == 'ce13_cost':
            add(ce, 'ce15', amt)
        elif tag in _CE_SUBFIELD_PARENT:
            detail, parent = _CE_SUBFIELD_PARENT[tag]
            add(ce, parent, amt)      # aggregate read by the EBIT/profit formula
            add(ce, detail, amt)      # "di cui" detail (full DB key, survives _map_sc_keys)
        else:
            add(ce, tag, amt)
    for tag, amt in _be_reclassify(costi, cl_cos):
        ce_add(tag, amt)
    for tag, amt in _be_reclassify(ricavi, cl_ric):
        ce_add(tag, amt)

    # --- Declared totals & current-year result ---
    # Some gestionali letter-space the column headers ("TOTALE  A T T I V I T�"),
    # which defeats a contiguous-substring search; fall back to a whitespace-stripped
    # copy so the needle still matches.
    up1 = re.sub(r'\s+', ' ', full.upper())
    flat1 = re.sub(r'\s+', '', full.upper())

    def _find_total(spaced, flat):
        if spaced in up1:
            return _be_amount(up1.split(spaced, 1)[1][:40])
        if flat in flat1:
            return _be_amount(flat1.split(flat, 1)[1][:40])
        return None

    def _control_amount(section, side, *needles):
        matches = [fact.amount for sec, sd, fact in controls
                   if sec == section and (side is None or sd == side)
                   and all(needle in fact.description for needle in needles)]
        return max(matches) if matches else None

    # Coordinate facts first; legacy linear-text lookup remains as a fallback for
    # layouts whose footer is not physically aligned with either data column.
    tot_att = ((_control_amount('sp', 'left', 'TOTALE', 'ATTIV')
                if use_garbled_reconstruction else None)
               or _find_total('TOTALE ATTIV', 'TOTALEATTIV'))
    tot_pas = ((_control_amount('sp', 'right', 'TOTALE', 'PASSIV')
                if use_garbled_reconstruction else None)
               or _find_total('TOTALE PASSIV', 'TOTALEPASSIV'))
    pareggio = ((_control_amount('sp', None, 'TOTALE', 'PAREGGIO')
                 if use_garbled_reconstruction else None)
                or _find_total('TOTALE A PAREGGIO', 'TOTALEAPAREGGIO'))

    explicit_results = []
    for sec, _side, fact in controls:
        if sec != 'sp' or 'ESERCIZ' not in fact.description:
            continue
        if 'UTILE' in fact.description:
            explicit_results.append(fact.amount)
        elif 'PERDIT' in fact.description:
            explicit_results.append(-fact.amount)
    explicit_result = explicit_results[-1] if explicit_results else None
    total_gap = (tot_att - tot_pas
                 if tot_att is not None and tot_pas is not None else None)
    ce_cost_total = _control_amount('ce', 'left', 'TOTALE', 'COST')
    ce_revenue_total = _control_amount('ce', 'right', 'TOTALE', 'RICAV')
    ce_control_result = (ce_revenue_total - ce_cost_total
                         if ce_cost_total is not None and ce_revenue_total is not None
                         else None)

    independent_results = [v for v in (explicit_result, total_gap, ce_control_result)
                           if v is not None]
    result_controls_agree = (len(independent_results) >= 2
                             and max(independent_results) - min(independent_results)
                             <= Decimal('0.05'))
    if use_garbled_reconstruction and result_controls_agree:
        utile = independent_results[0]
    elif total_gap is not None:
        utile = total_gap
    else:
        utile = result[0]                                  # booked account fallback
    bs['sp13'] = utile

    # A fondo ammortamento can never exceed its own gross asset, so a negative net
    # immobilizzazione is always a misclassification (fondo netted off the wrong /
    # a missing gross asset — budget_365/435). Clamp at 0: a negative asset is never
    # a valid IV-CEE value; the residual then surfaces honestly in the plug below.
    for _immk in ('sp02', 'sp03', 'sp04'):
        if bs.get(_immk, Z) < Z:
            bs[_immk] = Z

    # Trial-balance pareggio total; the IV-CEE total removes the perdita that is
    # parked on the attivo side as a balancing item.
    tb_total = pareggio
    if tb_total is None and tot_att is not None and tot_pas is not None:
        tb_total = max(tot_att, tot_pas)
    if tb_total is None:
        tb_total = tot_att or tot_pas

    if tb_total:
        # tb_total (pareggio / TOTALE ATTIVO) is GROSS when contra-asset funds sit on the
        # passivo side; subtract the netted contra mass so the IV-CEE NET total matches the
        # netted asset/passivo sums (plug ~ 0 instead of ~ fondi). No-op when netted_contra=0.
        iv_total = tb_total - (abs(utile) if utile < 0 else Z) - netted_contra
        att_sum = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)
        res_a = iv_total - att_sum
        pas_sum = sum((bs.get(k, Z) for k in _PASSIVO_KEYS), Z)
        res_p = iv_total - pas_sum
        # Keep the statement exactly as classified.  ``iv_total`` is independent
        # evidence from the source, not permission to manufacture the missing side.
        bs['totale_attivo'] = att_sum
        bs['totale_passivo'] = pas_sum
        bs['_declared_net_total'] = iv_total
        bs['_unexplained_asset_difference'] = res_a
        bs['_unexplained_liability_difference'] = res_p
        worst = max(abs(res_a), abs(res_p))
        # Expose the plug magnitude so the shared quadratura engine can tell a real
        # balance from one that only ties because the residual was swept into
        # sp09/sp16. Survives _map_sc_keys (has '_') and is ignored by the BS builder.
        bs['_plug_residual'] = worst
        # A geometrically reconstructed statement is authoritative only when
        # independent source controls agree and both net sides reconcile without
        # a compensating accounting entry.  This flag merely prevents a later
        # declared-total mutator from undoing that source-backed result.
        if (use_garbled_reconstruction and result_controls_agree
                and worst <= Decimal('0.05')):
            bs['_plug_residual'] = Z
            bs['_skip_declared_reconcile'] = True
        if worst > Decimal('1'):
            logger.warning(
                f"BILANCIO NON QUADRATO (contrapposte best-effort): residuo attivo={res_a}, "
                f"passivo={res_p}; nessun plug applicato — verificare in Rettifiche"
            )
    else:
        # No reliable declared total (e.g. code-less footer): retain both classified
        # sides and expose their difference.  Anchoring the shorter side to the larger
        # one used to invent cash/debt and turn incomplete extraction into a false OK.
        att_sum = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)
        pas_sum = sum((bs.get(k, Z) for k in _PASSIVO_KEYS), Z)
        bs['totale_attivo'] = att_sum
        bs['totale_passivo'] = pas_sum
        bs['_plug_residual'] = abs(att_sum - pas_sum)
        if abs(att_sum - pas_sum) > Decimal('1'):
            logger.warning(
                f"BILANCIO NON QUADRATO (contrapposte best-effort): totali dichiarati non "
                f"trovati, differenza non spiegata {abs(att_sum - pas_sum)}; "
                f"nessun plug applicato — verificare in Rettifiche"
            )

    # Rescue: a MASKED result on a dotted hierarchical ('4 sezioni') layout is the
    # truncated-deep-code collision described above. Retry via the level-1 mastri
    # reconstruction and keep it ONLY when it reconciles (self-validated inside
    # _hier_reconstruct) — so a file the best-effort already balances is untouched.
    plug_now = bs.get('_plug_residual', Z)
    total_now = bs.get('totale_attivo', Z) or Z
    if plug_now > max(Decimal('1'), Decimal('0.01') * total_now) and is_dotted_hierarchical(full):
        try:
            rescued = _hier_reconstruct(pages_data, full)
        except Exception as he:
            logger.warning(f"Hierarchical reconstruct failed: {type(he).__name__}: {he}")
            rescued = None
        if rescued is not None:
            logger.info("Hierarchical mastri reconstruction reconciled — using it over the masked best-effort")
            return rescued

    return bs, ce


def build_sp_from_vision(rows, utile: Decimal) -> Dict[str, Decimal]:
    """Monta lo Stato Patrimoniale da righe MASTRO piatte lette in vision.

    `rows` = [(codice, descrizione, importo, colonna)], colonna in {'left','right'}.
    La colonna e' verita' sul lato (FIXING-IMPORT.md §1.3); la descrizione decide la
    voce. `utile` e' il risultato LETTO dal documento, non derivato qui: questa
    funzione non inventa il pareggio.

    Le righe sono gia' al livello mastro, quindi non passano da _be_reclassify (che
    serve a scegliere fra padre e figli in una gerarchia): ogni riga vale per se'.
    Chiavi corte come il best-effort — il chiamante applica _map_sc_keys.
    """
    Z = Decimal('0')
    bs: Dict[str, Decimal] = {}
    netted = Z

    def add(k, v):
        bs[k] = bs.get(k, Z) + v

    for _code, desc, amount, column in rows:
        d = (desc or '').upper()
        if column == 'left':
            field, _specific = classify_attivo(d)
            add({'gross_sp02': 'sp02', 'gross_sp03': 'sp03',
                 'gross_sp04': 'sp04'}.get(field, field), amount)
            continue
        tag, _specific = classify_passivo(d)
        if tag in ('depr_sp02', 'depr_sp03', 'depr_sp04'):
            add(tag.replace('depr_', ''), -amount)     # netta il fondo dall'attivo
            netted += amount
        elif tag == 'deduct_crediti':
            add('sp06', -amount)
            netted += amount
        elif tag in ('sp11', 'sp12', 'sp14', 'sp15', 'sp18'):
            add(tag, amount)
        elif len(tag) == 5 and tag.startswith('sp16') and tag[4] in 'abcdefg':
            add('sp16', amount)                        # aggregato: pareggio invariato
            add(_DEBT_FIELD['breve'][tag[4]], amount)  # tipizzato, nome pieno
        else:
            add('sp16', amount)

    # Un fondo non puo' mai superare il proprio cespite lordo: un'immobilizzazione
    # netta negativa e' sempre una misclassificazione. Il cancello vedra' il divario.
    for k in ('sp02', 'sp03', 'sp04'):
        if bs.get(k, Z) < Z:
            bs[k] = Z

    bs['sp13'] = utile
    bs['_netted_contra'] = netted
    # Il riscatto legge i mastri, non la scadenza: nessun conto dice se un debito e'
    # entro o oltre l'esercizio, quindi finiscono tutti a breve. Non e' un errore da
    # nascondere — sp16 e sp17 stanno entrambi nel passivo, quindi il pareggio non
    # se ne accorge, ma CCN, current ratio e il termine di capitale circolante di
    # Altman si'. Stessa bandiera che alzano standard_ivcee_parser e mineru_adapter.
    bs['_source_maturity_unspecified'] = Decimal('1')
    bs['totale_attivo'] = sum((bs.get(k, Z) for k in _ATTIVO_KEYS), Z)
    bs['totale_passivo'] = sum((bs.get(k, Z) for k in _PASSIVO_KEYS), Z)
    bs['_plug_residual'] = Z
    return bs


def build_ce_from_vision(rows) -> Dict[str, Decimal]:
    """Monta il Conto Economico da righe MASTRO piatte lette in vision.

    La colonna decide la DIREZIONE (sinistra = costi, destra = ricavi) e la direzione
    vincola la risoluzione: _resolve_ce_field rifiuta una voce del segno opposto, cosi'
    un costo non puo' finire su un nodo di ricavo (che sposterebbe il risultato di 2x).
    Ordine: tabella a parole chiave -> albero IV-CEE vincolato -> catch-all neutro.
    """
    Z = Decimal('0')
    ce: Dict[str, Decimal] = {}

    def add(k, v):
        ce[k] = ce.get(k, Z) + v

    for _code, desc, amount, column in rows:
        d = (desc or '').upper()
        direction = 'costi' if column == 'left' else 'ricavi'
        if direction == 'costi':
            tag, specific = classify_costi(d)
        else:
            tag, specific = classify_ricavi(d)
        if not specific:
            # La tabella a parole chiave non conosce questa descrizione: prova
            # l'albero condiviso, VINCOLATO alla direzione. iv_cee_hierarchy.resolve
            # non filtra per segno sui nodi CE — _resolve_ce_field si'.
            resolved = _resolve_ce_field(d, direction)
            # Ultimo ripiego, e va scelto per DIREZIONE. FALLBACK_FIELDS['ce'] e'
            # 'ce06': neutro per i KPI solo DENTRO i costi della produzione. Su una
            # riga della colonna RICAVI e' un COSTO, quindi la massa non riconosciuta
            # sposta il risultato di 2x il proprio importo — lo stesso errore che
            # _resolve_ce_field esiste per impedire. Su budget_624 ci finivano le
            # rimanenze finali e i proventi finanziari letti a destra (1.479.943,47):
            # il conto economico chiudeva a 0,00 invece che agli 8.906,79 stampati.
            # A destra si tiene il default del classificatore ('ce04'), che e' del
            # segno giusto: e' la stessa scelta che fa _be_reclassify con cl_ric sul
            # percorso deterministico, non una regola nuova.
            tag = resolved or (fallback_field('ce') if direction == 'costi' else tag)
        if tag == 'ce01_return':
            add('ce01', -amount)
        elif tag == 'ce10_close':
            add('ce10', -amount)
        elif tag == 'ce13_cost':
            add('ce15', amount)
        elif tag in _CE_SUBFIELD_PARENT:
            detail, parent = _CE_SUBFIELD_PARENT[tag]
            add(parent, amount)
            add(detail, amount)
        else:
            add(tag, amount)
    return ce


_ATTIVO_KEYS = ['sp01', 'sp02', 'sp03', 'sp04', 'sp05', 'sp06', 'sp07', 'sp08', 'sp09', 'sp10']
_PASSIVO_KEYS = ['sp11', 'sp12', 'sp13', 'sp14', 'sp15', 'sp16', 'sp17', 'sp18']


def _attivo_key(k: str) -> bool:
    return k in _ATTIVO_KEYS


def _build_prior_from_entries(entries: List[Entry], default_ce: bool):
    """Build a prior-year (BS, CE) from the second amount column of a dual-year
    trial balance, or (None, None) when there is no usable prior column.

    Dual-year DEPI files carry two saldi per line (corrente, precedente). The
    parser stores the prior saldo in Entry.amount_prior; here we re-run the
    SAME IV-CEE mapping on the prior column and keep it only if it is non-empty
    and balances (Attivo == Passivo within €1) — a single-column file has all
    amount_prior == 0, so this returns (None, None) and nothing changes.
    """
    if not any((e.amount_prior or Decimal('0')) != 0 for e in entries):
        return None, None
    prior_entries = [replace(e, amount=(e.amount_prior or Decimal('0'))) for e in entries]
    prior_bs, prior_ce = build_iv_cee(prior_entries, default_ce=default_ce)
    ta = prior_bs.get('totale_attivo') or Decimal('0')
    tp = prior_bs.get('totale_passivo') or Decimal('0')
    if ta <= 0 or abs(ta - tp) > Decimal('1'):
        logger.info(f"Prior-year column unusable (attivo={ta}, passivo={tp}) — skipping")
        return None, None
    logger.info(f"Prior-year column extracted (totale_attivo={ta})")
    return prior_bs, prior_ce


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


def _vseg_split_rows(page) -> Tuple[list, list]:
    """Split a 2-column page into (left_rows, right_rows). Each row is
    (code, desc_upper, amount). Columns split at the gutter between the two
    'Conto'/'Codice' header words (fallback: 290pt)."""
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
            if not _VSEG_CODE_RE.match(code):
                continue
            amt = _vseg_num(side_words[-1][4])
            if amt is None:
                continue
            desc = ' '.join(w[4] for w in side_words[1:-1])
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


def _vseg_debt_field(u: str) -> Optional[str]:
    """IV-CEE field for a financing DETAIL caption, or None when unrecognised.

    Deliberately narrow: an unknown caption must fail the whole split rather than be
    guessed into a bucket."""
    if 'SOCIO' in u or 'SOCI ' in u or u.startswith('SOCI'):
        # A shareholder account inside the financing mastro is a soci loan: D.5, not a
        # bank. Keyed on SOCIO alone and NOT on 'FINANZ', which the OCR mangles
        # ("C/FINANZIAMEN" -> "C/FINANANZIAMEN"); the caller has already scoped these
        # rows to the financing mastro, so the word carries the meaning on its own.
        return 'sp17b_debiti_altri_finanz_lungo'
    if 'ANTICIPAZ' in u:
        return 'sp16a_debiti_banche_breve'          # advances revolve within the year
    if 'MEDIO/LUNGO' in u or 'MEDIO LUNGO' in u or 'M/L' in u or 'MUTUO' in u:
        return 'sp17a_debiti_banche_lungo'
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
    (['RIMANENZ'], 'ce02'), (['INCREMENTI'], 'ce03'),
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
    (['ONERI'], 'ce12'),
]


def _vseg_classify_ce(ce: Dict[str, Decimal], rows: list, side: int) -> None:
    """side: 0 = Costi, 1 = Ricavi. MASTRO rows only."""
    table = _VSEG_CE_RICAVI if side == 1 else _VSEG_CE_COSTI
    default = 'ce04' if side == 1 else 'ce12'
    for code, u, amt in rows:
        if '.' in code:
            continue
        field = default
        for kws, f in table:
            if all(kw in u for kw in kws):
                field = f
                break
        ce[field] = ce.get(field, Decimal('0')) + amt


_VSEG_RICAVI_KEYS = ('ce01', 'ce02', 'ce03', 'ce04', 'ce13', 'ce14', 'ce18')
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
                    _vseg_classify_ce(ce, left, 0)
                    _vseg_classify_ce(ce, right, 1)
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
                left, right = _vseg_split_rows(doc[page_number])
                _vseg_classify_ce(ce, left, 0)
                _vseg_classify_ce(ce, right, 1)
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


def extract_situazione_contabile(
    file_path: str,
    return_prior: bool = False,
    text_override: Optional[str] = None,
):
    """
    Extract IV CEE data from a Situazione Contabile PDF.

    Routes AGO-style (8-digit codes, 2-column layout) to the AGO parser,
    otherwise falls back to the DEPI parser (XX/YY/ZZZ codes).

    Returns:
        (balance_sheet_data, income_data) dicts with Decimal values.
        When return_prior=True, returns a 4-tuple
        (bs, ce, prior_bs, prior_ce) where prior_* is None unless the file is a
        dual-year trial balance whose prior column balances.
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise ValueError(f"Cannot open PDF: {e}")

    full_text = text_override or ""
    if not full_text:
        for page in doc:
            full_text += page.get_text() + "\n"
    doc.close()

    vseg_ocr_pages = None
    if text_override is None and len(full_text.strip()) < 50:
        candidate_pages = _vseg_rapidocr_pages(file_path)
        if candidate_pages:
            candidate_text = "\n".join(page["text"] for page in candidate_pages)
            if is_bilancio_verifica_segno(candidate_text):
                full_text = candidate_text
                vseg_ocr_pages = candidate_pages
                logger.info(
                    "Image-only verifica-segno detected via local coordinate RapidOCR"
                )

    # Dedicated by-sign contrapposte "bilancio di verifica" (accounts placed by sign of
    # balance, same account on both sides). Tried FIRST because its coordinate parser
    # reads this layout exactly and balances to plug 0, where the generic best-effort /
    # CoGe-LLM lump the asset column and double-count cash. Falls through on a ValueError
    # (not this layout, or it didn't balance) so nothing regresses.
    if is_bilancio_verifica_segno(full_text):
        try:
            logger.info("Bilancio di verifica a sezioni contrapposte PER SEGNO detected")
            vbs, vce = parse_bilancio_verifica_segno(
                file_path, ocr_pages=vseg_ocr_pages
            )
            return (vbs, vce, None, None) if return_prior else (vbs, vce)
        except Exception as vseg_err:
            logger.info(f"verifica-segno parser declined ({type(vseg_err).__name__}: "
                        f"{vseg_err}); falling back to standard routing")

    default_ce = False
    used_c8 = False
    if is_ago_format(full_text):
        logger.info("AGO/ERP format detected, using block-based parser")
        entries, totali = parse_entries_ago(file_path)
        logger.info(f"AGO parser: {len(entries)} parent entries, totali={totali}")
    elif is_contrapposte_8digit(full_text):
        logger.info("Contrapposte 8-digit detected, using coordinate-based parser")
        entries = parse_entries_contrapposte_8digit(file_path)
        default_ce = True
        used_c8 = True
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
        be_bs, be_ce = extract_contrapposte_best_effort(file_path)
        return (be_bs, be_ce, None, None) if return_prior else (be_bs, be_ce)
    else:
        logger.info("DEPI format detected, using text-based parser")
        entries = parse_entries(full_text)
        # Unmatched cost/revenue mastri → ce12/ce01 (aligns DEPI with the other
        # trial-balance parsers); the level-2-vs-level-1 has_sub2 guard in
        # build_iv_cee prevents double-counting parent + detail lines.
        default_ce = True
        logger.info(f"DEPI parser: {len(entries)} entries")

    bs, ce = build_iv_cee(entries, default_ce=default_ce)

    # Recover passivo mastri whose 8-digit total line is drawn as a vector (only
    # the contrapposte-8digit path exposes this) from their clean dettagli, gated
    # on the SP balancing exactly. No-op unless the sheet is short on the passivo
    # side and a clean orphan subset closes the gap.
    if used_c8:
        bs = _c8_recover_orphan_passivo(file_path, bs)

    # Safety net (general, not per-file): a structured/DEPI parser that comes up
    # EMPTY on a file that is physically a 2-column contrapposte (is_contrapposte_file)
    # has misrouted. This happens when is_situazione_contabile() matches a marker
    # (e.g. dotted NNN.NNNNN codes + an 8-digit cluster) and shadows the best-effort
    # route, but no structured sub-parser actually reads the layout — so build_iv_cee
    # yields nothing (e.g. AITEC PROVVISORIO/BILANCINO). The best-effort coordinate
    # parser DOES read these layouts, so retry it and keep its result only when it is
    # genuinely non-empty. Purely additive: triggers only on an otherwise-empty result,
    # so it cannot regress files the structured parsers already extract.
    if (bs.get('totale_attivo') or Decimal('0')) == 0:
        try:
            if is_contrapposte_file(file_path):
                logger.info("Structured parser empty on contrapposte file — retrying best-effort")
                be_bs, be_ce = extract_contrapposte_best_effort(file_path)
                if (be_bs.get('totale_attivo') or Decimal('0')) != 0:
                    logger.info(f"Best-effort retry recovered totale_attivo={be_bs.get('totale_attivo')}")
                    return (be_bs, be_ce, None, None) if return_prior else (be_bs, be_ce)
        except Exception as be_err:
            logger.warning(f"Best-effort retry failed: {type(be_err).__name__}: {be_err}")

    logger.info(f"SC parser: sp02={bs.get('sp02')}, sp03={bs.get('sp03')}, sp09={bs.get('sp09')}")
    logger.info(f"SC parser: sp11={bs.get('sp11')}, sp12={bs.get('sp12')}, sp13={bs.get('sp13')}")
    logger.info(f"SC parser: sp16={bs.get('sp16')}, sp17={bs.get('sp17')}")
    logger.info(f"SC parser: ce01={ce.get('ce01')}, ce05={ce.get('ce05')}, ce08={ce.get('ce08')}")
    logger.info(f"SC parser: totale_attivo={bs.get('totale_attivo')}, totale_passivo={bs.get('totale_passivo')}")

    if return_prior:
        prior_bs, prior_ce = _build_prior_from_entries(entries, default_ce)
        return bs, ce, prior_bs, prior_ce
    return bs, ce
