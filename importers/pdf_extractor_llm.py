"""
PDF Balance Sheet Extractor using PyMuPDF + Claude Haiku 4.5.

Fast alternative to Docling: PyMuPDF extracts text from relevant pages (~100ms),
then Claude Haiku parses IV CEE fields via structured output (~3-5s).
Total: ~5s at ~$0.01/PDF vs Docling's ~133s.
"""

import json
import os
import logging
import re
import tempfile
import time
from decimal import Decimal
from typing import Dict, Optional, Set, Tuple

import fitz  # PyMuPDF
import pydantic
import anthropic

from config import PDF_LLM_MODEL, PDF_LLM_MAX_TOKENS

logger = logging.getLogger(__name__)


class PDFImportError(Exception):
    """Exception raised when PDF import fails."""
    pass


# ---------------------------------------------------------------------------
# Pydantic models for structured extraction
# ---------------------------------------------------------------------------

class BalanceSheetExtraction(pydantic.BaseModel):
    """IV CEE Stato Patrimoniale fields (single year)."""
    sp01_crediti_soci: float = pydantic.Field(0, description="A) Crediti verso soci per versamenti ancora dovuti")
    sp02_immob_immateriali: float = pydantic.Field(0, description="B.I) Immobilizzazioni immateriali")
    sp03_immob_materiali: float = pydantic.Field(0, description="B.II) Immobilizzazioni materiali")
    sp04_immob_finanziarie: float = pydantic.Field(0, description="B.III) Immobilizzazioni finanziarie")
    sp05_rimanenze: float = pydantic.Field(0, description="C.I) Rimanenze")
    sp06_crediti_breve: float = pydantic.Field(0, description="C.II) Crediti esigibili entro l'esercizio successivo")
    sp07_crediti_lungo: float = pydantic.Field(0, description="C.II) Crediti esigibili oltre l'esercizio successivo")
    sp08_attivita_finanziarie: float = pydantic.Field(0, description="C.III) Attivita finanziarie che non costituiscono immobilizzazioni")
    sp09_disponibilita_liquide: float = pydantic.Field(0, description="C.IV) Disponibilita liquide")
    sp10_ratei_risconti_attivi: float = pydantic.Field(0, description="D) Ratei e risconti attivi")
    sp11_capitale: float = pydantic.Field(0, description="A.I) Capitale sociale")
    sp12_riserve: float = pydantic.Field(0, description="Sum of all reserves (II-VIII): sovrapprezzo, rivalutazione, legale, statutarie, altre, copertura flussi, utili portati, azioni proprie")
    sp13_utile_perdita: float = pydantic.Field(0, description="A.IX) Utile (perdita) dell'esercizio")
    sp14_fondi_rischi: float = pydantic.Field(0, description="B) Fondi per rischi e oneri")
    sp15_tfr: float = pydantic.Field(0, description="C) Trattamento di fine rapporto di lavoro subordinato")
    sp16_debiti_breve: float = pydantic.Field(0, description="D) Debiti esigibili entro l'esercizio successivo")
    sp17_debiti_lungo: float = pydantic.Field(0, description="D) Debiti esigibili oltre l'esercizio successivo")
    sp18_ratei_risconti_passivi: float = pydantic.Field(0, description="E) Ratei e risconti passivi")
    totale_attivo: float = pydantic.Field(0, description="Totale attivo (total assets)")
    totale_passivo: float = pydantic.Field(0, description="Totale passivo (total equity + liabilities)")


class IncomeStatementExtraction(pydantic.BaseModel):
    """IV CEE Conto Economico fields."""
    ce01_ricavi_vendite: float = pydantic.Field(0, description="A.1) Ricavi delle vendite e delle prestazioni")
    ce02_variazioni_rimanenze: float = pydantic.Field(0, description="A.2) Variazioni delle rimanenze di prodotti in corso di lavorazione, semilavorati e finiti")
    ce03_lavori_interni: float = pydantic.Field(0, description="A.4) Incrementi di immobilizzazioni per lavori interni")
    ce04_altri_ricavi: float = pydantic.Field(0, description="A.5) Altri ricavi e proventi")
    ce05_materie_prime: float = pydantic.Field(0, description="B.6) Per materie prime, sussidiarie, di consumo e di merci")
    ce06_servizi: float = pydantic.Field(0, description="B.7) Per servizi")
    ce07_godimento_beni: float = pydantic.Field(0, description="B.8) Per godimento di beni di terzi")
    ce08_costi_personale: float = pydantic.Field(0, description="B.9) Totale costi per il personale")
    ce08a_tfr_accrual: float = pydantic.Field(0, description="B.9c) Trattamento di fine rapporto (sub-item of personnel costs)")
    ce09_ammortamenti: float = pydantic.Field(0, description="B.10) Totale ammortamenti e svalutazioni")
    ce09a_ammort_immateriali: float = pydantic.Field(0, description="B.10a) Ammortamento delle immobilizzazioni immateriali")
    ce09b_ammort_materiali: float = pydantic.Field(0, description="B.10b) Ammortamento delle immobilizzazioni materiali")
    ce09c_svalutazioni: float = pydantic.Field(0, description="B.10c) Altre svalutazioni delle immobilizzazioni")
    ce09d_svalutazione_crediti: float = pydantic.Field(0, description="B.10d) Svalutazioni dei crediti compresi nell'attivo circolante")
    ce10_var_rimanenze_mat_prime: float = pydantic.Field(0, description="B.11) Variazioni delle rimanenze di materie prime, sussidiarie, di consumo e merci")
    ce11_accantonamenti: float = pydantic.Field(0, description="B.12) Accantonamenti per rischi")
    ce11b_altri_accantonamenti: float = pydantic.Field(0, description="B.13) Altri accantonamenti")
    ce12_oneri_diversi: float = pydantic.Field(0, description="B.14) Oneri diversi di gestione")
    ce13_proventi_partecipazioni: float = pydantic.Field(0, description="C.15) Proventi da partecipazioni")
    ce14_altri_proventi_finanziari: float = pydantic.Field(0, description="C.16) Altri proventi finanziari")
    ce15_oneri_finanziari: float = pydantic.Field(0, description="C.17) Interessi e altri oneri finanziari")
    ce16_utili_perdite_cambi: float = pydantic.Field(0, description="C.17-bis) Utili e perdite su cambi")
    ce17_rettifiche_attivita_fin: float = pydantic.Field(0, description="D) Totale delle rettifiche di valore di attivita e passivita finanziarie")
    ce18_proventi_straordinari: float = pydantic.Field(0, description="E.20) Proventi straordinari")
    ce19_oneri_straordinari: float = pydantic.Field(0, description="E.21) Oneri straordinari")
    ce20_imposte: float = pydantic.Field(0, description="22) Imposte sul reddito dell'esercizio")


class TwoYearBalanceSheetExtraction(pydantic.BaseModel):
    """IV CEE Stato Patrimoniale — both columns (current year + prior year)."""
    current_year: BalanceSheetExtraction = pydantic.Field(description="Current year values (leftmost/first column)")
    prior_year: BalanceSheetExtraction = pydantic.Field(description="Prior year values (rightmost/second column)")


class TwoYearIncomeStatementExtraction(pydantic.BaseModel):
    """IV CEE Conto Economico — both columns (current year + prior year)."""
    current_year: IncomeStatementExtraction = pydantic.Field(description="Current year values (leftmost/first column)")
    prior_year: IncomeStatementExtraction = pydantic.Field(description="Prior year values (rightmost/second column)")


# ---------------------------------------------------------------------------
# PyMuPDF page detection — range-based IV CEE section finding
# ---------------------------------------------------------------------------

# SP (Stato Patrimoniale) anchors
SP_START_KEYWORDS = ["stato patrimoniale", "attivo"]  # both must appear on start page
SP_END_KEYWORDS = ["totale passivo"]                  # first match after sp_start

# CE (Conto Economico) anchors
CE_START_KEYWORDS = ["conto economico", "valore della produzione"]  # both must appear
# CE end: "21) Utile (perdita) dell'esercizio" or nearby.
# NOTE: "utile (perdita) dell'esercizio" also appears in SP equity (item IX),
# so we search from ce_start+1 to skip the SP overlap page.
# We use two tiers: first look for the definitive item 21 line,
# then fall back to "totale delle imposte" which is 1 line before item 21.
CE_END_KEYWORDS_PRIMARY = [
    "21) utile (perdita) dell'esercizio",       # item 21 with number prefix
    "21) utile(perdita) dell'esercizio",        # variant without space
]
CE_END_KEYWORDS_FALLBACK = [
    "totale delle imposte sul reddito",         # item 20 total — last line before result
    "utile (perdita) dell'esercizio",           # without prefix (searched from ce_start+1)
    "risultato dell'esercizio",
]

# Fallback: single-keyword detection if range-based fails
SP_FALLBACK_KEYWORDS = ["totale attivo", "totale passivo"]
CE_FALLBACK_KEYWORDS = ["totale valore della produzione", "differenza tra valore e costi", "differ. tra valore e costi"]


def find_section_pages(file_path: str) -> Tuple[Set[int], Set[int]]:
    """
    Scan PDF pages with PyMuPDF to find SP and CE sections using
    range-based detection (start anchor → end anchor).

    IV CEE structure:
      SP starts: "Stato patrimoniale" + "Attivo" on same page
      SP ends:   "Totale passivo"
      CE starts: "Conto economico" + "Valore della produzione" on same page
      CE ends:   "Totale delle imposte sul reddito" or "21) Utile (perdita)"

    Returns:
        (sp_pages, ce_pages) - sets of zero-based page indices
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")

    total_pages = len(doc)
    logger.info(f"PDF has {total_pages} pages")

    # Scan all pages and cache lowercased text.
    # Collapse spaced-out text (e.g. "S T A T O" → "STATO") for keyword matching
    # (Dylog format uses spaced headers).
    def _normalize_for_search(text: str) -> str:
        lowered = text.lower()
        lowered = re.sub(r'\b(\w) (?=\w\b)', r'\1', lowered)  # "s t a t o" → "stato"
        lowered = re.sub(r' {2,}', ' ', lowered)               # collapse multi-spaces
        return lowered

    page_texts = []
    for page_num in range(total_pages):
        page_texts.append(_normalize_for_search(doc[page_num].get_text()))
    doc.close()

    def _find_start(start_kws, after_page=0):
        """Find first page where ALL start keywords are present."""
        for i in range(after_page, total_pages):
            if all(kw in page_texts[i] for kw in start_kws):
                return i
        return None

    def _find_end(end_kws, from_page):
        """Find first page (from from_page onward) where ANY end keyword is present."""
        for i in range(from_page, total_pages):
            if any(kw in page_texts[i] for kw in end_kws):
                return i
        return None

    # --- SP range ---
    sp_start = _find_start(SP_START_KEYWORDS)
    sp_end = None
    if sp_start is not None:
        sp_end = _find_end(SP_END_KEYWORDS, sp_start)
        if sp_end is None:
            sp_end = min(sp_start + 2, total_pages - 1)

    # --- CE range ---
    # CE start: search after SP start to avoid re-matching the SP header page.
    # Strategy: try strict match first (both "conto economico" + "valore della produzione"),
    # then try "valore della produzione" alone after SP end (Dylog format puts VP on last
    # SP page without a "conto economico" header until a later page).
    ce_after = (sp_start + 1) if sp_start is not None else 0
    ce_start = _find_start(CE_START_KEYWORDS, after_page=ce_after)
    # If CE start not found after SP, try from the beginning (SP may not exist)
    if ce_start is None and ce_after > 0:
        ce_start = _find_start(CE_START_KEYWORDS)
    # Relaxed: try "valore della produzione" alone after SP end (Dylog)
    if ce_start is None and sp_end is not None:
        ce_start = _find_start(["valore della produzione"], after_page=sp_end)

    ce_end = None
    if ce_start is not None:
        # Search from ce_start+1 to skip "utile (perdita)" in SP equity on the same page.
        # Try primary (item 21 with prefix) first, then fall back to imposte/generic.
        ce_end = _find_end(CE_END_KEYWORDS_PRIMARY, ce_start + 1)
        if ce_end is None:
            ce_end = _find_end(CE_END_KEYWORDS_FALLBACK, ce_start + 1)
        if ce_end is None:
            ce_end = min(ce_start + 3, total_pages - 1)

    # Build page sets from ranges
    def _range_to_set(start, end):
        if start is None or end is None:
            return set()
        return set(range(start, end + 1))

    sp_pages = _range_to_set(sp_start, sp_end)
    ce_pages = _range_to_set(ce_start, ce_end)

    # Fallback: if range-based detection fails, try single-keyword matching + ±1 expansion
    if not sp_pages or not ce_pages:
        logger.warning("Range-based detection incomplete, falling back to keyword matching")

        def _find_by_keywords(keywords):
            pages = set()
            for i, text in enumerate(page_texts):
                if any(kw in text for kw in keywords):
                    pages.add(i)
            return pages

        def _expand(pages):
            expanded = set()
            for p in pages:
                if p - 1 >= 0:
                    expanded.add(p - 1)
                expanded.add(p)
                if p + 1 < total_pages:
                    expanded.add(p + 1)
            return expanded

        if not sp_pages:
            sp_pages = _expand(_find_by_keywords(SP_FALLBACK_KEYWORDS))
        if not ce_pages:
            ce_pages = _expand(_find_by_keywords(CE_FALLBACK_KEYWORDS))

    # Last resort: first 6 pages
    if not sp_pages and not ce_pages:
        logger.warning("No SP/CE sections found, using first 6 pages as fallback")
        fallback = set(range(min(6, total_pages)))
        sp_pages = fallback
        ce_pages = fallback

    if not sp_pages:
        sp_pages = ce_pages
    if not ce_pages:
        ce_pages = sp_pages

    logger.info(f"SP pages: {sorted(sp_pages)}, CE pages: {sorted(ce_pages)}")
    return sp_pages, ce_pages


# ---------------------------------------------------------------------------
# Zucchetti IV Direttiva pre-filter
# ---------------------------------------------------------------------------

# Zucchetti account detail line: "100220 000 - description"
_ZUCCHETTI_ACCOUNT_RE = re.compile(r'^\s*\d{6}\s+\d{3}\s+-\s+')

# Bare numeric value: "(1.234)", "1.234.567", "0", "(0)" — with optional parens
_BARE_NUMBER_RE = re.compile(
    r'^\s*\(?\d[\d.]*\)?\s*$'
)

# Footer block lines (multi-line footer split across lines)
_ZUCCHETTI_FOOTER_WORDS = re.compile(
    r'^\s*(administrator|Data:|Ora:|Utente:|Pag\.|AGO\s*-|di\s*$|\d{2}-\d{2}-\d{4}$|\d{2}:\d{2}$|\d{2}\.\d{2}\.\d{2}$)',
    re.IGNORECASE
)

# Repeated page headers / metadata (appear at top of every page)
_ZUCCHETTI_PAGE_HEADER_RE = re.compile(
    r'^\s*(BILANCIO SCHEMA XBRL|Esercizio$|Dal$|Al$|'
    r'\d{4}/\d|Registrazioni fino al|'
    r'Schema$|Esteso$|Versione tassonomia|\d{8}$|'
    r'Regime Contabile|Tipo Reddito|Partita IVA|Codice Fiscale|'
    r'Impresa$|Ordinario$|Abbreviato$|'
    r'\d{2}-\d{2}-\d{4}$|\d{11}$|'  # dates and P.IVA/CF numbers
    r'Differenza arrotondamento unit)',
    re.IGNORECASE
)


def _is_zucchetti_format(text: str) -> bool:
    """Detect Zucchetti format by presence of account detail lines."""
    matches = sum(1 for line in text.splitlines()
                  if _ZUCCHETTI_ACCOUNT_RE.match(line))
    return matches >= 5


def _preprocess_zucchetti(text: str) -> str:
    """Strip Zucchetti detail account lines and their preceding values.

    Zucchetti layout puts the value on the line BEFORE the account detail:
        82.818                          ← value (to remove)
        100815 000 - impianti specifici ← account detail (to remove)
        ...
        Totale 2) impianti e macchinario  ← structural (to keep)
        146.992                            ← total value (to keep)

    Pass 1: mark indices of account lines and their preceding value lines.
    Pass 2: remove marked lines + footer/header noise.
    """
    if not _is_zucchetti_format(text):
        return text

    lines = text.splitlines()

    # Pass 1: find lines to remove (account details + their preceding values)
    remove = set()
    for i, line in enumerate(lines):
        if _ZUCCHETTI_ACCOUNT_RE.match(line):
            remove.add(i)
            # Also remove preceding bare-number line(s)
            j = i - 1
            while j >= 0 and _BARE_NUMBER_RE.match(lines[j]):
                remove.add(j)
                j -= 1

    # Pass 2: also mark footer block lines for removal.
    # Footer pattern spans multiple lines; mark the full block by scanning for
    # known trigger words and eating surrounding bare-number lines (page numbers).
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _ZUCCHETTI_FOOTER_WORDS.match(stripped):
            remove.add(i)
            # Eat adjacent bare single/double-digit lines (page num, total pages)
            for j in (i - 1, i + 1):
                if 0 <= j < len(lines) and re.match(r'^\s*\d{1,2}\s*$', lines[j]):
                    remove.add(j)

    # Pass 3: filter remaining lines, dropping repeated page headers
    # Track company name to allow first occurrence but skip repeats
    company_name = None
    seen_section_header = False
    section_header_count = 0
    filtered = []
    for i, line in enumerate(lines):
        if i in remove:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if _ZUCCHETTI_PAGE_HEADER_RE.match(stripped):
            continue
        # Track section headers (STATO PATRIMONIALE / CONTO ECONOMICO)
        is_section = stripped.startswith('STATO PATRIMONIALE') or stripped.startswith('CONTO ECONOMICO')
        if is_section:
            section_header_count += 1
            if not seen_section_header:
                seen_section_header = True
            elif section_header_count > 1:
                continue  # skip repeated section headers from later pages
        # Keep company name only on first occurrence
        if company_name is None and not seen_section_header:
            if not _BARE_NUMBER_RE.match(stripped):
                company_name = stripped
                filtered.append(line)
                continue
        elif stripped == company_name:
            continue  # skip repeated company name
        filtered.append(line)

    result = '\n'.join(filtered)
    logger.info(f"Zucchetti pre-filter: {len(text)} -> {len(result)} chars")
    return result


# ---------------------------------------------------------------------------
# Datev Koinos IV Direttiva pre-filter
# ---------------------------------------------------------------------------

# Datev Koinos account detail: standalone 5-11 digit code on its own line
_DATEV_ACCOUNT_CODE_STANDALONE_RE = re.compile(r'^\s*\d{5,11}\s*$')

# Datev Koinos account detail: code + description on same line (longer codes)
# e.g. "06015101010 Impianti generici" or "10030100910 IVA in compensazione..."
_DATEV_ACCOUNT_CODE_INLINE_RE = re.compile(r'^\s*\d{7,11}\s+\S')

# Standalone A/P/C/R flag (single letter on its own line)
_DATEV_FLAG_RE = re.compile(r'^\s*[APCR]\s*$')

# Footer: "Bilancio micro-imprese" or "Pagina X di Y"
_DATEV_FOOTER_RE = re.compile(
    r'^\s*(Bilancio micro-imprese|Pagina \d+ di \d+)',
    re.IGNORECASE
)

# Bare Italian-format number: "554,68", "24.383,23", "-13.541,08", "(1.234,56)", "0,00", "0"
_DATEV_BARE_NUMBER_RE = re.compile(
    r'^\s*[-\(]?\d[\d.]*(?:,\d{2})?\)?\s*$'
)

# Bare date on its own line (DD/MM/YYYY or DD.MM.YYYY)
_DATEV_BARE_DATE_RE = re.compile(r'^\s*\d{2}[/\.]\d{2}[/\.]\d{4}\s*$')


def _is_datev_koinos_format(text: str) -> bool:
    """Detect Datev Koinos format by account codes + A/P/C/R flag lines."""
    lines = text.splitlines()
    standalone = sum(1 for l in lines if _DATEV_ACCOUNT_CODE_STANDALONE_RE.match(l))
    inline = sum(1 for l in lines if _DATEV_ACCOUNT_CODE_INLINE_RE.match(l))
    flag_count = sum(1 for l in lines if _DATEV_FLAG_RE.match(l))
    # Need account codes (either type) AND standalone flags
    return (standalone + inline) >= 5 and flag_count >= 5


def _preprocess_datev_koinos(text: str) -> str:
    """Strip Datev Koinos account detail noise.

    Datev Koinos layout (after PyMuPDF extraction) has two variants:

    Variant A — short codes (5-7 digits) are standalone:
        54.164,31             ← subtotal value (KEEP)
        050101010             ← account code (remove)
        Spese di costituzione ← account description (remove)
        A                     ← flag (remove)
        67.705,39             ← detail value (remove)

    Variant B — long codes (7-11 digits) are inline with description:
        06015101010 Impianti generici  ← code+description (remove)
        A                              ← flag (remove)
        37.793,41                      ← detail value (remove)

    Both variants: after removing detail blocks, keep structural labels
    and subtotal values.
    """
    if not _is_datev_koinos_format(text):
        return text

    lines = text.splitlines()
    remove = set()

    for i, line in enumerate(lines):
        # Variant B: inline code+description (e.g. "06015101010 Impianti generici")
        if _DATEV_ACCOUNT_CODE_INLINE_RE.match(line):
            remove.add(i)
            # Next lines: flag (A/P/C/R), then value
            j = i + 1
            while j < len(lines) and j <= i + 2:
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                if _DATEV_FLAG_RE.match(lines[j]):
                    remove.add(j)
                    if j + 1 < len(lines) and _DATEV_BARE_NUMBER_RE.match(lines[j + 1]):
                        remove.add(j + 1)
                    break
                j += 1
            continue

        # Variant A: standalone code (e.g. "050101010")
        if _DATEV_ACCOUNT_CODE_STANDALONE_RE.match(line):
            remove.add(i)
            # Remove following lines: description, flag, value
            j = i + 1
            while j < len(lines) and j <= i + 3:
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                if _DATEV_FLAG_RE.match(lines[j]):
                    remove.add(j)
                    if j + 1 < len(lines) and _DATEV_BARE_NUMBER_RE.match(lines[j + 1]):
                        remove.add(j + 1)
                    break
                # Description line between code and flag — remove it
                # But don't eat structural lines (IV CEE labels)
                if re.match(r'^\s*\d+\)', s) or re.match(r'^\s*[A-E]\)', s) or 'Totale' in s:
                    break
                remove.add(j)
                j += 1

    # Also remove footers and bare dates
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _DATEV_FOOTER_RE.match(stripped):
            remove.add(i)
        if _DATEV_BARE_DATE_RE.match(stripped):
            remove.add(i)

    filtered = [line for i, line in enumerate(lines) if i not in remove and line.strip()]
    result = '\n'.join(filtered)
    logger.info(f"Datev Koinos pre-filter: {len(text)} -> {len(result)} chars")
    return result


def _strip_separator_noise(text: str) -> str:
    """Remove separator lines (-----, =====) and repeated page headers.

    Applies to Dylog and similar ERP printouts that insert ASCII separators
    and repeated header/footer lines on every page.
    """
    lines = text.splitlines()
    # Detect: if fewer than 5 separator lines, skip (probably not noisy)
    sep_count = sum(1 for l in lines if re.match(r'^\s*[-=]{5,}\s*$', l.strip()))
    if sep_count < 5:
        return text

    # Dylog repeated page header pattern
    _dylog_header_re = re.compile(
        r'^\s*(DATA\s*:|PAGINA Nr|Stampato con tecnologia|FISCOLASER|'
        r'DESCRIZIONE VOCE|ESER\.\s+\d)',
        re.IGNORECASE
    )

    filtered = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Remove separator lines
        if re.match(r'^[-=]{5,}$', stripped):
            continue
        # Remove repeated page headers
        if _dylog_header_re.match(stripped):
            continue
        # Remove bare page numbers (single digit on a line)
        if re.match(r'^\d{1,2}$', stripped):
            continue
        # Remove bare dates like 01/12/2025 on their own line
        if re.match(r'^\d{2}/\d{2}/\d{4}$', stripped):
            continue
        filtered.append(line)

    result = '\n'.join(filtered)
    logger.info(f"Separator noise filter: {len(text)} -> {len(result)} chars ({sep_count} separators removed)")
    return result


def extract_relevant_pages(file_path: str) -> Tuple[str, str]:
    """
    Open PDF with PyMuPDF, detect SP and CE pages by keywords,
    and return extracted text for each section.

    Returns:
        (sp_text, ce_text) - text from balance sheet and income statement pages
    """
    sp_pages, ce_pages = find_section_pages(file_path)

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")

    sp_text = "\n".join(doc[p].get_text() for p in sorted(sp_pages))
    ce_text = "\n".join(doc[p].get_text() for p in sorted(ce_pages))
    doc.close()

    # Pre-filter ERP account detail lines (no-op for standard PDFs)
    sp_text = _preprocess_zucchetti(sp_text)
    ce_text = _preprocess_zucchetti(ce_text)
    sp_text = _preprocess_datev_koinos(sp_text)
    ce_text = _preprocess_datev_koinos(ce_text)

    # Strip separator lines and repeated headers (Dylog, etc.)
    sp_text = _strip_separator_noise(sp_text)
    ce_text = _strip_separator_noise(ce_text)

    logger.info(
        f"SP text: {len(sp_text)} chars, CE text: {len(ce_text)} chars"
    )
    return sp_text, ce_text


def build_subpdf(file_path: str, pages: Set[int]) -> str:
    """
    Build a smaller PDF containing only the specified pages using PyMuPDF.

    Args:
        file_path: Path to the original PDF
        pages: Set of zero-based page indices to include

    Returns:
        Path to the temporary sub-PDF file (caller must clean up)
    """
    try:
        src = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")

    dst = fitz.open()  # new empty PDF
    sorted_pages = sorted(pages)
    for p in sorted_pages:
        if p < len(src):
            dst.insert_pdf(src, from_page=p, to_page=p)

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    dst.save(tmp.name)
    dst.close()
    src.close()

    logger.info(
        f"Built sub-PDF: {len(sorted_pages)} pages ({sorted_pages}) -> {tmp.name}"
    )
    return tmp.name


# ---------------------------------------------------------------------------
# Claude Haiku structured extraction
# ---------------------------------------------------------------------------

SP_SYSTEM_PROMPT = """You are an expert Italian accountant specializing in Bilancio IV CEE (Schema di Bilancio art. 2424 Codice Civile).

Extract the Stato Patrimoniale (balance sheet) values from the text below.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimal separators (1.234.567 = 1234567)
- Parentheses mean negative: (347.117) = -347117
- Trailing minus means negative: 347.117- = -347117
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF (e.g., losses, negative reserves)

CREDITI (in ATTIVO section, BEFORE "Totale attivo"):
- sp06_crediti_breve = SUM of ALL "esigibili entro l'esercizio successivo" amounts across ALL crediti categories (verso clienti, tributari, verso altri, etc.)
- sp07_crediti_lungo = SUM of ALL "esigibili oltre l'esercizio successivo" amounts across ALL crediti categories
- CRITICAL: sp06 + sp07 MUST equal "Totale crediti". Do NOT use "Totale crediti" directly as sp06.
- If crediti are not split by maturity, put the TOTAL Crediti in sp06_crediti_breve and sp07=0

DEBITI (in PASSIVO section, AFTER "Totale attivo"):
- IMPORTANT: "entro/oltre" in the PASSIVO section refers to DEBTS, not credits
- First find TOTALE Debiti (D) — the sum of all debt categories
- sp17_debiti_lungo: look for ALL "di cui esigibili oltre l'esercizio successivo" sub-lines
  under individual debt items (e.g., under "Debiti verso fornitori", under "Altri debiti", etc.)
  and SUM them. These "di cui" lines are indented sub-totals showing the long-term portion.
- sp16_debiti_breve = TOTALE Debiti (D) minus sp17_debiti_lungo
- CRITICAL: sp16 + sp17 MUST equal TOTALE Debiti (D). If they don't, recalculate sp16 as the difference.
- If debiti are not split by maturity at all, put TOTALE Debiti in sp16_debiti_breve and sp17=0

PATRIMONIO NETTO:
- sp11_capitale is ONLY "I - Capitale" (share capital). Do NOT include it in sp12_riserve
- sp12_riserve = sum of ONLY items II through VIII: sovrapprezzo azioni (II), riserve di rivalutazione (III), riserva legale (IV), riserve statutarie (V), altre riserve (VI), riserva per operazioni di copertura (VII), utili (perdite) portati a nuovo (VIII), riserva negativa azioni proprie
- IMPORTANT: Verify that sp11_capitale + sp12_riserve + sp13_utile_perdita = "Totale patrimonio netto"

TOTALS:
- Extract totale_attivo and totale_passivo for validation
- totale_passivo = Totale patrimonio netto + fondi rischi + TFR + debiti + ratei passivi

Extract the CURRENT YEAR values (the first/leftmost value column, not the prior year)."""

SP_BOTH_YEARS_SYSTEM_PROMPT = """You are an expert Italian accountant specializing in Bilancio IV CEE (Schema di Bilancio art. 2424 Codice Civile).

Extract the Stato Patrimoniale (balance sheet) values from the text below.
The document has TWO value columns: current year (left) and prior year (right).
Extract BOTH columns into current_year and prior_year.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimal separators (1.234.567 = 1234567)
- Parentheses mean negative: (347.117) = -347117
- Trailing minus means negative: 347.117- = -347117
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF (e.g., losses, negative reserves)

CREDITI (in ATTIVO section, BEFORE "Totale attivo"):
- sp06_crediti_breve = SUM of ALL "esigibili entro l'esercizio successivo" amounts across ALL crediti categories (verso clienti, tributari, verso altri, etc.)
- sp07_crediti_lungo = SUM of ALL "esigibili oltre l'esercizio successivo" amounts across ALL crediti categories
- CRITICAL: sp06 + sp07 MUST equal "Totale crediti". Do NOT use "Totale crediti" directly as sp06.
- If crediti are not split by maturity, put the TOTAL Crediti in sp06_crediti_breve and sp07=0

DEBITI (in PASSIVO section, AFTER "Totale attivo"):
- IMPORTANT: "entro/oltre" in the PASSIVO section refers to DEBTS, not credits
- First find TOTALE Debiti (D) — the sum of all debt categories
- sp17_debiti_lungo: look for ALL "di cui esigibili oltre l'esercizio successivo" sub-lines
  under individual debt items (e.g., under "Debiti verso fornitori", under "Altri debiti", etc.)
  and SUM them. These "di cui" lines are indented sub-totals showing the long-term portion.
- sp16_debiti_breve = TOTALE Debiti (D) minus sp17_debiti_lungo
- CRITICAL: sp16 + sp17 MUST equal TOTALE Debiti (D). If they don't, recalculate sp16 as the difference.
- If debiti are not split by maturity at all, put TOTALE Debiti in sp16_debiti_breve and sp17=0

PATRIMONIO NETTO:
- sp11_capitale is ONLY "I - Capitale" (share capital). Do NOT include it in sp12_riserve
- sp12_riserve = sum of ONLY items II through VIII: sovrapprezzo azioni (II), riserve di rivalutazione (III), riserva legale (IV), riserve statutarie (V), altre riserve (VI), riserva per operazioni di copertura (VII), utili (perdite) portati a nuovo (VIII), riserva negativa azioni proprie
- IMPORTANT: Verify that sp11_capitale + sp12_riserve + sp13_utile_perdita = "Totale patrimonio netto"

TOTALS:
- Extract totale_attivo and totale_passivo for validation
- totale_passivo = Totale patrimonio netto + fondi rischi + TFR + debiti + ratei passivi

Extract BOTH columns: current_year (left column) and prior_year (right column)."""

CE_SYSTEM_PROMPT = """You are an expert Italian accountant specializing in Bilancio IV CEE (Schema di Conto Economico art. 2425 Codice Civile).

Extract the Conto Economico (income statement) values from the text below.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimal separators (1.234.567 = 1234567)
- Parentheses mean negative: (347.117) = -347117
- Trailing minus means negative: 347.117- = -347117
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF
- ce08_costi_personale = Total "9) per il personale" (the sum, not sub-items)
- ce08a_tfr_accrual = sub-item "c) trattamento di fine rapporto" under personnel costs (item 9c)
- ce09_ammortamenti = Total "10) ammortamenti e svalutazioni" (the sum of 10a+10b+10c+10d)
- Extract sub-items ce09a (10a), ce09b (10b), ce09c (10c), ce09d (10d) if available
- ce10_var_rimanenze_mat_prime = item 11) variazioni delle rimanenze di materie prime
- ce11_accantonamenti = item 12) accantonamenti per rischi
- ce11b_altri_accantonamenti = item 13) altri accantonamenti
- ce15_oneri_finanziari = item 17) interessi e altri oneri finanziari (total)
- Items 2) and 3) may be merged; if so put the combined value in ce02_variazioni_rimanenze

Extract the CURRENT YEAR values (the first/leftmost value column, not the prior year)."""

CE_BOTH_YEARS_SYSTEM_PROMPT = """You are an expert Italian accountant specializing in Bilancio IV CEE (Schema di Conto Economico art. 2425 Codice Civile).

Extract the Conto Economico (income statement) values from the text below.
The document has TWO value columns: current year (left) and prior year (right).
Extract BOTH columns into current_year and prior_year.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimal separators (1.234.567 = 1234567)
- Parentheses mean negative: (347.117) = -347117
- Trailing minus means negative: 347.117- = -347117
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF
- ce08_costi_personale = Total "9) per il personale" (the sum, not sub-items)
- ce08a_tfr_accrual = sub-item "c) trattamento di fine rapporto" under personnel costs (item 9c)
- ce09_ammortamenti = Total "10) ammortamenti e svalutazioni" (the sum of 10a+10b+10c+10d)
- Extract sub-items ce09a (10a), ce09b (10b), ce09c (10c), ce09d (10d) if available
- ce10_var_rimanenze_mat_prime = item 11) variazioni delle rimanenze di materie prime
- ce11_accantonamenti = item 12) accantonamenti per rischi
- ce11b_altri_accantonamenti = item 13) altri accantonamenti
- ce15_oneri_finanziari = item 17) interessi e altri oneri finanziari (total)
- Items 2) and 3) may be merged; if so put the combined value in ce02_variazioni_rimanenze

Extract BOTH columns: current_year (left column) and prior_year (right column)."""


def _build_tool_schema(model: type[pydantic.BaseModel], tool_name: str) -> dict:
    """Build an Anthropic tool definition from a Pydantic model."""
    schema = model.model_json_schema()
    # Remove title/description that Pydantic adds at the top level
    schema.pop("title", None)
    schema.pop("description", None)
    return {
        "name": tool_name,
        "description": f"Record the extracted {tool_name} values",
        "input_schema": schema,
    }


def _extract_with_llm(
    client: anthropic.Anthropic,
    text: str,
    system_prompt: str,
    output_model: type[pydantic.BaseModel],
    section_name: str,
    tool_name: str,
    max_retries: int = 2,
) -> pydantic.BaseModel:
    """Call Claude Haiku with tool-use for structured extraction."""
    logger.info(f"Calling Claude Haiku for {section_name} extraction ({len(text)} chars)...")

    tool = _build_tool_schema(output_model, tool_name)

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=PDF_LLM_MODEL,
                max_tokens=PDF_LLM_MAX_TOKENS,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Extract the {section_name} values from this Italian balance sheet text. "
                        f"Use the {tool_name} tool to record your results.\n\n{text}"
                    ),
                }],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
            )

            # Find the tool_use block
            for block in response.content:
                if block.type == "tool_use":
                    result = output_model.model_validate(block.input)
                    logger.info(f"{section_name} extraction complete")
                    return result

            raise PDFImportError(f"No tool_use block in {section_name} response")

        except anthropic.InternalServerError as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(f"API 500 error, retrying in {wait}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise

    raise last_error  # unreachable but satisfies type checker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_to_decimal_dict(model: pydantic.BaseModel) -> Dict[str, Decimal]:
    """Convert a Pydantic model with float fields to Dict[str, Decimal]."""
    result = {}
    for field_name, value in model:
        result[field_name] = Decimal(str(value))
    return result


# Core cost fields that must always be positive (the model subtracts them).
# Some PDFs (e.g. Zucchetti, "bilancio riclassificato") show costs as negative.
_POSITIVE_COST_FIELDS = {
    'ce05_materie_prime', 'ce06_servizi', 'ce07_godimento_beni',
    'ce08_costi_personale', 'ce08a_tfr_accrual',
    'ce09_ammortamenti', 'ce09a_ammort_immateriali', 'ce09b_ammort_materiali',
    'ce09c_svalutazioni', 'ce09d_svalutazione_crediti',
    'ce11_accantonamenti', 'ce11b_altri_accantonamenti',
    'ce12_oneri_diversi',
    'ce15_oneri_finanziari',
    'ce19_oneri_straordinari',
}

# Ambiguous fields: only flip if the PDF uses "all costs as negative" convention.
# ce10_var_rimanenze_mat_prime — can be legitimately negative (inventory reduction)
# ce20_imposte — can be negative (net tax credit)
# If many core cost fields were negative, the PDF uses a negative convention
# and these should be flipped too.
_CONDITIONAL_COST_FIELDS = {
    'ce10_var_rimanenze_mat_prime',
    'ce20_imposte',
}


def _normalize_ce_signs(income_data: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Ensure cost fields are stored as positive values.

    The model formulas explicitly subtract costs (e.g. EBIT = VP - COPRO),
    so ce05-ce12, ce15, ce19, ce20 must be positive.  Some PDFs show costs
    in parentheses and the LLM correctly extracts them as negative — this
    function flips those to positive.

    When the PDF uses "all costs as negative" convention (detected by ≥3
    core cost fields being negative), also flip ce10 and ce20.
    """
    # Pass 1: flip core cost fields and count how many were negative
    flipped = []
    for field in _POSITIVE_COST_FIELDS:
        val = income_data.get(field, Decimal('0'))
        if val < 0:
            income_data[field] = abs(val)
            flipped.append(field)

    # Pass 2: if many core fields were negative, the PDF uses "costs as negative"
    # convention — also flip the ambiguous fields
    if len(flipped) >= 3:
        for field in _CONDITIONAL_COST_FIELDS:
            val = income_data.get(field, Decimal('0'))
            if val < 0:
                income_data[field] = abs(val)
                flipped.append(field)

    if flipped:
        logger.info(f"CE sign normalization: flipped {len(flipped)} fields to positive: {flipped}")
    return income_data


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def extract_pdf_with_llm(file_path: str) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """
    Extract balance sheet and income statement from PDF using PyMuPDF + Claude Haiku 4.5.

    Requires ANTHROPIC_API_KEY environment variable.

    Args:
        file_path: Path to the PDF file

    Returns:
        (balance_sheet_data, income_data) - dictionaries with Decimal values

    Raises:
        PDFImportError: If extraction fails
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

    # Step 1: Extract relevant page text with PyMuPDF
    sp_text, ce_text = extract_relevant_pages(file_path)

    if not sp_text.strip():
        raise PDFImportError("No text extracted from balance sheet pages")

    # Step 2: Extract balance sheet via Claude Haiku
    try:
        sp_result = _extract_with_llm(
            client, sp_text, SP_SYSTEM_PROMPT,
            BalanceSheetExtraction, "Stato Patrimoniale",
            tool_name="balance_sheet",
        )
    except anthropic.APIError as e:
        raise PDFImportError(f"Anthropic API error during SP extraction: {e}")

    # Step 3: Extract income statement via Claude Haiku
    try:
        ce_result = _extract_with_llm(
            client, ce_text, CE_SYSTEM_PROMPT,
            IncomeStatementExtraction, "Conto Economico",
            tool_name="income_statement",
        )
    except anthropic.APIError as e:
        raise PDFImportError(f"Anthropic API error during CE extraction: {e}")

    # Step 4: Convert to Decimal dicts and normalize signs
    balance_sheet_data = _model_to_decimal_dict(sp_result)
    income_data = _normalize_ce_signs(_model_to_decimal_dict(ce_result))

    # Log key values for verification
    logger.info(f"SP totale_attivo = {balance_sheet_data.get('totale_attivo')}")
    logger.info(f"SP totale_passivo = {balance_sheet_data.get('totale_passivo')}")
    logger.info(f"CE ce01_ricavi_vendite = {income_data.get('ce01_ricavi_vendite')}")

    # Step 5: Validate crediti, debt split, then equity consistency
    balance_sheet_data = _validate_crediti(balance_sheet_data, "single")
    balance_sheet_data = _validate_debiti(balance_sheet_data, "single")
    balance_sheet_data = _validate_equity(balance_sheet_data, "single")

    return balance_sheet_data, income_data


def _validate_crediti(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Validate crediti: sp06 + sp07 must not exceed the crediti implied by totale_attivo.

    If totale_attivo is available, crediti = totale_attivo - (sp01..sp05 + sp08 + sp09 + sp10).
    If sp06 + sp07 overshoots, the LLM likely put total crediti in sp06 instead of just entro.
    Fix: sp06 = total_crediti - sp07.
    """
    tot_attivo = balance_sheet_data.get('totale_attivo', Decimal('0'))
    if tot_attivo == 0:
        return balance_sheet_data

    sp01 = balance_sheet_data.get('sp01_crediti_soci', Decimal('0'))
    sp02 = balance_sheet_data.get('sp02_immob_immateriali', Decimal('0'))
    sp03 = balance_sheet_data.get('sp03_immob_materiali', Decimal('0'))
    sp04 = balance_sheet_data.get('sp04_immob_finanziarie', Decimal('0'))
    sp05 = balance_sheet_data.get('sp05_rimanenze', Decimal('0'))
    sp06 = balance_sheet_data.get('sp06_crediti_breve', Decimal('0'))
    sp07 = balance_sheet_data.get('sp07_crediti_lungo', Decimal('0'))
    sp08 = balance_sheet_data.get('sp08_attivita_finanziarie', Decimal('0'))
    sp09 = balance_sheet_data.get('sp09_disponibilita_liquide', Decimal('0'))
    sp10 = balance_sheet_data.get('sp10_ratei_risconti_attivi', Decimal('0'))

    non_crediti = sp01 + sp02 + sp03 + sp04 + sp05 + sp08 + sp09 + sp10
    expected_crediti = tot_attivo - non_crediti
    actual_crediti = sp06 + sp07

    diff = actual_crediti - expected_crediti
    if diff > Decimal('1') and sp07 > 0 and abs(diff - sp07) <= Decimal('1'):
        # Classic double-count: LLM put total crediti in sp06, then also added sp07
        new_sp06 = expected_crediti - sp07
        logger.warning(
            f"[{label}] Crediti double-count detected: sp06+sp07={actual_crediti} but "
            f"expected={expected_crediti} (diff={diff} ≈ sp07={sp07}). "
            f"Correcting sp06 from {sp06} to {new_sp06}"
        )
        balance_sheet_data['sp06_crediti_breve'] = new_sp06
    elif diff > Decimal('1'):
        # General overshoot — correct sp06
        new_sp06 = expected_crediti - sp07
        if new_sp06 >= 0:
            logger.warning(
                f"[{label}] Crediti mismatch: sp06+sp07={actual_crediti} but "
                f"expected={expected_crediti} (diff={diff}). Correcting sp06 to {new_sp06}"
            )
            balance_sheet_data['sp06_crediti_breve'] = new_sp06

    return balance_sheet_data


def _validate_debiti(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Validate and auto-correct debt split: sp16 + sp17 must equal total debiti.

    The total debiti can be inferred from totale_passivo - (patrimonio_netto + fondi + tfr + ratei).
    If sp16 + sp17 overshoots total debiti, recalculate sp16 = total_debiti - sp17.
    """
    tot_passivo = balance_sheet_data.get('totale_passivo', Decimal('0'))
    if tot_passivo == 0:
        return balance_sheet_data

    sp11 = balance_sheet_data.get('sp11_capitale', Decimal('0'))
    sp12 = balance_sheet_data.get('sp12_riserve', Decimal('0'))
    sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    sp14 = balance_sheet_data.get('sp14_fondi_rischi', Decimal('0'))
    sp15 = balance_sheet_data.get('sp15_tfr', Decimal('0'))
    sp16 = balance_sheet_data.get('sp16_debiti_breve', Decimal('0'))
    sp17 = balance_sheet_data.get('sp17_debiti_lungo', Decimal('0'))
    sp18 = balance_sheet_data.get('sp18_ratei_risconti_passivi', Decimal('0'))

    patrimonio_netto = sp11 + sp12 + sp13
    total_debiti = tot_passivo - patrimonio_netto - sp14 - sp15 - sp18
    debt_sum = sp16 + sp17
    diff = abs(debt_sum - total_debiti)

    if diff > Decimal('1') and total_debiti > 0:
        new_sp16 = total_debiti - sp17
        if new_sp16 >= 0:
            logger.warning(
                f"[{label}] Debt mismatch: sp16+sp17={debt_sum} but total debiti={total_debiti} "
                f"(diff={diff}). Correcting sp16 from {sp16} to {new_sp16}"
            )
            balance_sheet_data['sp16_debiti_breve'] = new_sp16
        else:
            # sp17 exceeds total debiti — correct sp17 instead
            logger.warning(
                f"[{label}] Debt mismatch: sp17={sp17} > total debiti={total_debiti}. "
                f"Correcting sp17 to {total_debiti} and sp16 to 0"
            )
            balance_sheet_data['sp17_debiti_lungo'] = total_debiti
            balance_sheet_data['sp16_debiti_breve'] = Decimal('0')

    return balance_sheet_data


def _validate_equity(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Validate and auto-correct equity consistency for a single year."""
    sp11 = balance_sheet_data.get('sp11_capitale', Decimal('0'))
    sp12 = balance_sheet_data.get('sp12_riserve', Decimal('0'))
    sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    computed_equity = sp11 + sp12 + sp13
    tot_passivo = balance_sheet_data.get('totale_passivo', Decimal('0'))
    liabilities = (
        balance_sheet_data.get('sp14_fondi_rischi', Decimal('0')) +
        balance_sheet_data.get('sp15_tfr', Decimal('0')) +
        balance_sheet_data.get('sp16_debiti_breve', Decimal('0')) +
        balance_sheet_data.get('sp17_debiti_lungo', Decimal('0')) +
        balance_sheet_data.get('sp18_ratei_risconti_passivi', Decimal('0'))
    )
    expected_equity = tot_passivo - liabilities
    equity_diff = abs(computed_equity - expected_equity)
    if equity_diff > Decimal('1'):
        logger.warning(
            f"[{label}] Equity mismatch: sp11+sp12+sp13={computed_equity} but "
            f"totale_passivo-liabilities={expected_equity} (diff={equity_diff}). "
            f"Correcting sp12_riserve from {sp12} to {sp12 - equity_diff}"
        )
        balance_sheet_data['sp12_riserve'] = expected_equity - sp11 - sp13
    return balance_sheet_data


def extract_pdf_both_years_with_llm(
    file_path: str,
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal], Dict[str, Decimal], Dict[str, Decimal]]:
    """
    Extract balance sheet and income statement for BOTH years from a PDF.

    Same 2 API calls as single-year extraction, but with richer output models
    that capture both the current-year and prior-year columns.

    Args:
        file_path: Path to the PDF file

    Returns:
        (current_bs, current_ce, prior_bs, prior_ce) — all Dict[str, Decimal]

    Raises:
        PDFImportError: If extraction fails
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

    # Step 1: Extract relevant page text with PyMuPDF
    sp_text, ce_text = extract_relevant_pages(file_path)

    if not sp_text.strip():
        raise PDFImportError("No text extracted from balance sheet pages")

    # Step 2: Extract balance sheet (both years) via Claude Haiku
    try:
        sp_result = _extract_with_llm(
            client, sp_text, SP_BOTH_YEARS_SYSTEM_PROMPT,
            TwoYearBalanceSheetExtraction, "Stato Patrimoniale (both years)",
            tool_name="balance_sheet_both_years",
        )
    except anthropic.APIError as e:
        raise PDFImportError(f"Anthropic API error during SP extraction: {e}")

    # Step 3: Extract income statement (both years) via Claude Haiku
    try:
        ce_result = _extract_with_llm(
            client, ce_text, CE_BOTH_YEARS_SYSTEM_PROMPT,
            TwoYearIncomeStatementExtraction, "Conto Economico (both years)",
            tool_name="income_statement_both_years",
        )
    except anthropic.APIError as e:
        raise PDFImportError(f"Anthropic API error during CE extraction: {e}")

    # Step 4: Convert to Decimal dicts and normalize signs
    current_bs = _model_to_decimal_dict(sp_result.current_year)
    prior_bs = _model_to_decimal_dict(sp_result.prior_year)
    current_ce = _normalize_ce_signs(_model_to_decimal_dict(ce_result.current_year))
    prior_ce = _normalize_ce_signs(_model_to_decimal_dict(ce_result.prior_year))

    # Log key values
    logger.info(f"[current] SP totale_attivo={current_bs.get('totale_attivo')}, CE ricavi={current_ce.get('ce01_ricavi_vendite')}")
    logger.info(f"[prior]   SP totale_attivo={prior_bs.get('totale_attivo')}, CE ricavi={prior_ce.get('ce01_ricavi_vendite')}")

    # Step 5: Validate crediti, debt split, then equity consistency for both years
    current_bs = _validate_crediti(current_bs, "current")
    prior_bs = _validate_crediti(prior_bs, "prior")
    current_bs = _validate_debiti(current_bs, "current")
    prior_bs = _validate_debiti(prior_bs, "prior")
    current_bs = _validate_equity(current_bs, "current")
    prior_bs = _validate_equity(prior_bs, "prior")

    return current_bs, current_ce, prior_bs, prior_ce
