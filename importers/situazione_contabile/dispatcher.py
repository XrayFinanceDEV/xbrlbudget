"""Riconoscimento del formato ed extract_situazione_contabile, che sceglie il parser.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from decimal import Decimal
from typing import Optional
from importers.situazione_contabile.depi import (
    parse_entries,
)
from importers.situazione_contabile.iv_cee import (
    build_iv_cee,
)
from importers.situazione_contabile.ago import (
    parse_entries_ago,
)
from importers.situazione_contabile.colonna_unica import (
    parse_entries_single_column,
)
from importers.situazione_contabile.contrapposte_8cifre import (
    _c8_recover_orphan_passivo, _c8_risultato_stampato, is_contrapposte_8digit,
    parse_entries_contrapposte_8digit,
)
from importers.situazione_contabile.verifica_ie import (
    _ie_risultato_in_apertura, is_verifica_ie, parse_entries_verifica_ie,
)
from importers.situazione_contabile.verifica_mastri import (
    is_verifica_mastri, parse_entries_verifica_mastri,
)
from importers.situazione_contabile.verifica_sub_mastro import (
    is_verifica_sub_mastro, parse_entries_verifica_sub_mastro,
)
from importers.situazione_contabile.verifica_sezbil import (
    is_verifica_sezbil, parse_entries_verifica_sezbil,
)
from importers.situazione_contabile.teamsystem import (
    is_teamsystem_sc, parse_entries_teamsystem,
)
from importers.situazione_contabile.best_effort import (
    is_contrapposte_file,
)
from importers.situazione_contabile.best_effort_estrazione import (
    extract_contrapposte_best_effort,
)
from importers.situazione_contabile.vision import (
    _build_prior_from_entries,
)
from importers.situazione_contabile.verifica_segno import (
    _vseg_rapidocr_pages, is_bilancio_verifica_segno, parse_bilancio_verifica_segno,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.situazione_contabile_parser")


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
    # Verifica con la sezione in colonna (SEZBIL A/P/C/R e RIEPILOGO, COLOMBO 2026)
    if is_verifica_sezbil(text):
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
    used_ie = False
    # La firma a sezioni contrapposte 8-digit (sottoconti "NNNNNN NNN", TOTALE A
    # PAREGGIO, ATTIVITA'/PASSIVITA') e' piu' specifica di quella AGO: quando
    # l'intestazione "BILANCIO DI VERIFICA" e' testo e non un tracciato (budget_618,
    # 619, 620, 610/621, 613) il parser a blocchi AGO leggeva uno o pochi mastri e
    # sbilanciava di milioni, il parser per coordinate li legge tutti.
    if is_verifica_ie(full_text):
        used_ie = True
        logger.info("Bilancio di verifica a colonna unica IE/E detected")
        entries = parse_entries_verifica_ie(file_path)
        default_ce = True
        logger.info(f"Verifica IE/E parser: {len(entries)} entries")
    elif is_verifica_sub_mastro(full_text):
        used_ie = True
        logger.info("Bilancio di verifica 'Totale Sub / Totale Mastro' detected")
        entries = parse_entries_verifica_sub_mastro(file_path)
        default_ce = True
        logger.info(f"Verifica Sub/Mastro parser: {len(entries)} entries")
    elif is_verifica_mastri(full_text):
        used_ie = True
        logger.info("Bilancio di verifica 'Mastri' detected")
        entries = parse_entries_verifica_mastri(file_path)
        default_ce = True
        logger.info(f"Verifica Mastri parser: {len(entries)} entries")
    elif is_verifica_sezbil(full_text):
        used_ie = True
        logger.info("Bilancio di verifica con la sezione in colonna (SEZBIL) detected")
        entries = parse_entries_verifica_sezbil(file_path)
        default_ce = True
        logger.info(f"Verifica SEZBIL parser: {len(entries)} entries")
    elif is_ago_format(full_text) and not is_contrapposte_8digit(full_text):
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
    if used_ie:
        tot = {e.section: e.amount for e in entries if e.level == 3}
        if tot:
            dare, avere = tot['attivo'] + tot['costi'], tot['passivo'] + tot['ricavi']
            # dare != avere nei totali stampati: la verifica non pareggia da sola (budget_680,
            # perdita 2025 non girata). Si dichiara: il foglio lo riprodurra' tale e quale.
            bs['_verifica_dare'], bs['_verifica_avere'] = dare, avere
            bs = _ie_risultato_in_apertura(bs, entries, dare - avere)
    if used_c8:
        bs = _c8_recover_orphan_passivo(file_path, bs)
        bs = _c8_risultato_stampato(full_text, entries, bs)

    # Safety net (general, not per-file): a structured/DEPI parser that comes up
    # EMPTY on a file that is physically a 2-column contrapposte (is_contrapposte_file)
    # has misrouted. This happens when is_situazione_contabile() matches a marker
    # (e.g. dotted NNN.NNNNN codes + an 8-digit cluster) and shadows the best-effort
    # route, but no structured sub-parser actually reads the layout — so build_iv_cee
    # yields nothing (e.g. AITEC PROVVISORIO/BILANCINO). The best-effort coordinate
    # parser DOES read these layouts, so retry it and keep its result only when it is
    # genuinely non-empty. Purely additive: triggers only on an otherwise-empty result,
    # so it cannot regress files the structured parsers already extract.
    if (bs.get('totale_attivo') or Decimal('0')) == 0 and not used_ie:
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
