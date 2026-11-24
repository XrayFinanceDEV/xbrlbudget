"""Pre-filtri dei formati di gestionale (Zucchetti, Datev Koinos, Stampa dettaglio).

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import logging
import re

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


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

# ---------------------------------------------------------------------------
# "Stampa dettaglio voci" pre-filter (accounting software detail report)
# ---------------------------------------------------------------------------

# Account code lines: "67.01.01.01", "84.01.01", "55.01.07" etc.
_STAMPA_DETAIL_ACCOUNT_RE = re.compile(
    r'^\s*\d{2}\.\d{2}\.\d{2}(?:\.\d{2})?\s*$'
)
# Detail value lines ending with D (Dare/debit) or A (Avere/credit)
_STAMPA_DETAIL_VALUE_RE = re.compile(
    r'^\s*[\d.,]+\s+[DA]\s*$'
)
# Page header pattern for this format
_STAMPA_PAGE_HEADER_RE = re.compile(
    r'^\s*(Data di stampa|Pagina|Dati generali|Sede legale:|Codice fiscale:|'
    r'Partita IVA:|Stampa dettaglio voci)\s*$',
    re.IGNORECASE
)
# "% Reddito" column header
_STAMPA_PERCENT_RE = re.compile(r'^\s*\d{1,3}\s{3,}$')

def _is_stampa_dettaglio_format(text: str) -> bool:
    """Detect 'Stampa dettaglio voci' format by account codes + D/A suffixes."""
    lines = text.splitlines()
    account_codes = sum(1 for l in lines if _STAMPA_DETAIL_ACCOUNT_RE.match(l))
    da_values = sum(1 for l in lines if _STAMPA_DETAIL_VALUE_RE.match(l))
    return account_codes >= 5 and da_values >= 5

def _preprocess_stampa_dettaglio(text: str) -> str:
    """Strip account-level detail from 'Stampa dettaglio voci' format.

    This format has IV CEE section headers (3.B.9, 1.C.2, etc.) with
    account-level details underneath. We keep section headers and totals,
    removing individual account lines and their D/A-suffixed values.

    Also removes repeated page headers and metadata.
    """
    if not _is_stampa_dettaglio_format(text):
        return text

    lines = text.splitlines()
    remove = set()

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Remove account code lines (e.g., "67.01.01.01")
        if _STAMPA_DETAIL_ACCOUNT_RE.match(stripped):
            remove.add(i)
            # Also remove following description and value lines
            j = i + 1
            while j < len(lines) and j <= i + 3:
                s = lines[j].strip()
                if not s:
                    j += 1
                    continue
                if _STAMPA_DETAIL_VALUE_RE.match(s):
                    remove.add(j)
                    break
                # Description line between code and value
                if not s[0].isdigit() or '.' not in s[:5]:
                    remove.add(j)
                else:
                    break
                j += 1
            continue

        # Remove D/A value lines that weren't caught above
        if _STAMPA_DETAIL_VALUE_RE.match(stripped):
            remove.add(i)
            continue

        # Remove page headers
        if _STAMPA_PAGE_HEADER_RE.match(stripped):
            remove.add(i)
            continue

        # Remove "% Reddito" percentage values (e.g., "100   ", "80   ", "75   ")
        if _STAMPA_PERCENT_RE.match(stripped):
            remove.add(i)
            continue

    filtered = [line for i, line in enumerate(lines) if i not in remove and line.strip()]
    result = '\n'.join(filtered)
    logger.info(f"Stampa dettaglio pre-filter: {len(text)} -> {len(result)} chars")
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
