"""
PDF Balance Sheet Extractor using PyMuPDF + Claude Haiku 4.5.

Fast alternative to Docling: PyMuPDF extracts text from relevant pages (~100ms),
then Claude Haiku parses IV CEE fields via structured output (~3-5s).
Total: ~5s at ~$0.01/PDF vs Docling's ~133s.
"""

import base64
import json
import os
import logging
import re
import tempfile
import time
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

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

def _coerce_number(v):
    """Coerce an LLM-returned amount to float, tolerating Italian/mangled formats.

    Claude sometimes serialises a numeric field as a STRING using Italian
    thousands/decimal separators ("8.144.680,93") or a mangled hybrid where the
    decimal comma was already turned into a dot but the thousands dots were left
    in ("8.144.680.93"). Plain pydantic float-parsing rejects both, which made a
    whole BalanceSheetExtraction fail validation and the extractor return nothing
    (budget_405). Normalise here so one oddly-formatted field never sinks the
    whole extraction.

    Rules (no comma vs comma):
      - comma present  -> Italian: drop '.', then ',' -> '.'   ("1.234,56" -> 1234.56)
      - >1 dot, no comma -> last 2-digit group is the decimal, others thousands
                            ("8.144.680.93" -> 8144680.93; "1.234.567" -> 1234567)
      - <=1 dot         -> leave as-is (normal float / int)
    Trailing '-' and parentheses denote negatives.
    """
    if v is None or isinstance(v, (int, float, dict, list)):
        return v
    s = str(v).strip()
    if not s:
        return 0
    neg = s.endswith('-') or (s.startswith('(') and s.endswith(')'))
    s = s.strip('()').rstrip('-').strip().replace(' ', '').replace(' ', '')
    if not s:
        return 0
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif s.count('.') > 1:
        head, _, tail = s.rpartition('.')
        s = (head.replace('.', '') + '.' + tail) if len(tail) == 2 else s.replace('.', '')
    try:
        f = float(s)
    except ValueError:
        return 0
    return -f if neg else f


class _ItalianNumberModel(pydantic.BaseModel):
    """Base model whose float fields tolerate Italian/mangled numeric strings."""

    @pydantic.field_validator('*', mode='before')
    @classmethod
    def _coerce_italian_numbers(cls, v):
        return _coerce_number(v)


class BalanceSheetExtraction(_ItalianNumberModel):
    """IV CEE Stato Patrimoniale fields (single year)."""
    sp01_crediti_soci: float = pydantic.Field(0, description="A) Crediti verso soci per versamenti ancora dovuti")
    sp02_immob_immateriali: float = pydantic.Field(0, description="B.I) Immobilizzazioni immateriali")
    sp03_immob_materiali: float = pydantic.Field(0, description="B.II) Immobilizzazioni materiali")
    sp04_immob_finanziarie: float = pydantic.Field(0, description="B.III) Immobilizzazioni finanziarie")
    sp05_rimanenze: float = pydantic.Field(0, description="C.I) Rimanenze")
    sp06_crediti_breve: float = pydantic.Field(0, description="C.II) Crediti esigibili entro l'esercizio successivo")
    sp07_crediti_lungo: float = pydantic.Field(0, description="C.II) Crediti esigibili oltre l'esercizio successivo")
    # Debtor-type breakdown for C.II Crediti per OIC art. 2424 (entro/oltre per group).
    # Must sum to sp06_crediti_breve and sp07_crediti_lungo respectively.
    sp06a_crediti_clienti_breve: float = pydantic.Field(0, description="C.II.1) Crediti verso clienti — entro l'esercizio")
    sp07a_crediti_clienti_lungo: float = pydantic.Field(0, description="C.II.1) Crediti verso clienti — oltre l'esercizio")
    sp06b_crediti_controllate_breve: float = pydantic.Field(0, description="C.II.2) Crediti verso imprese controllate — entro l'esercizio")
    sp07b_crediti_controllate_lungo: float = pydantic.Field(0, description="C.II.2) Crediti verso imprese controllate — oltre l'esercizio")
    sp06c_crediti_collegate_breve: float = pydantic.Field(0, description="C.II.3) Crediti verso imprese collegate — entro l'esercizio")
    sp07c_crediti_collegate_lungo: float = pydantic.Field(0, description="C.II.3) Crediti verso imprese collegate — oltre l'esercizio")
    sp06d_crediti_controllanti_breve: float = pydantic.Field(0, description="C.II.4) Crediti verso controllanti — entro l'esercizio")
    sp07d_crediti_controllanti_lungo: float = pydantic.Field(0, description="C.II.4) Crediti verso controllanti — oltre l'esercizio")
    sp06e_crediti_tributari_breve: float = pydantic.Field(0, description="C.II.5-bis) Crediti tributari — entro l'esercizio")
    sp07e_crediti_tributari_lungo: float = pydantic.Field(0, description="C.II.5-bis) Crediti tributari — oltre l'esercizio")
    sp06f_imposte_anticipate_breve: float = pydantic.Field(0, description="C.II.5-ter) Imposte anticipate — entro l'esercizio")
    sp07f_imposte_anticipate_lungo: float = pydantic.Field(0, description="C.II.5-ter) Imposte anticipate — oltre l'esercizio")
    sp06g_crediti_altri_breve: float = pydantic.Field(0, description="C.II.5-quater) Crediti verso altri — entro l'esercizio")
    sp07g_crediti_altri_lungo: float = pydantic.Field(0, description="C.II.5-quater) Crediti verso altri — oltre l'esercizio")
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
    # Creditor-type breakdown per OIC art. 2424 (entro/oltre per group).
    # Must sum to sp16_debiti_breve and sp17_debiti_lungo respectively.
    sp16a_debiti_banche_breve: float = pydantic.Field(0, description="D.4) Debiti verso banche — entro l'esercizio")
    sp17a_debiti_banche_lungo: float = pydantic.Field(0, description="D.4) Debiti verso banche — oltre l'esercizio")
    sp16b_debiti_altri_finanz_breve: float = pydantic.Field(0, description="D.3)+D.5) Debiti verso soci per finanziamenti + verso altri finanziatori — entro l'esercizio")
    sp17b_debiti_altri_finanz_lungo: float = pydantic.Field(0, description="D.3)+D.5) Debiti verso soci per finanziamenti + verso altri finanziatori — oltre l'esercizio")
    sp16c_debiti_obbligazioni_breve: float = pydantic.Field(0, description="D.1)+D.2)+D.8) Obbligazioni + obbligazioni convertibili + debiti rappresentati da titoli di credito — entro l'esercizio")
    sp17c_debiti_obbligazioni_lungo: float = pydantic.Field(0, description="D.1)+D.2)+D.8) Obbligazioni + obbligazioni convertibili + debiti rappresentati da titoli di credito — oltre l'esercizio")
    sp16d_debiti_fornitori_breve: float = pydantic.Field(0, description="D.7) Debiti verso fornitori — entro l'esercizio")
    sp17d_debiti_fornitori_lungo: float = pydantic.Field(0, description="D.7) Debiti verso fornitori — oltre l'esercizio")
    sp16e_debiti_tributari_breve: float = pydantic.Field(0, description="D.12) Debiti tributari — entro l'esercizio")
    sp17e_debiti_tributari_lungo: float = pydantic.Field(0, description="D.12) Debiti tributari — oltre l'esercizio")
    sp16f_debiti_previdenza_breve: float = pydantic.Field(0, description="D.13) Debiti verso istituti di previdenza e di sicurezza sociale — entro l'esercizio")
    sp17f_debiti_previdenza_lungo: float = pydantic.Field(0, description="D.13) Debiti verso istituti di previdenza e di sicurezza sociale — oltre l'esercizio")
    sp16g_altri_debiti_breve: float = pydantic.Field(0, description="D.6)+D.9-11bis)+D.14) Acconti + verso controllate/collegate/controllanti + altri debiti — entro l'esercizio")
    sp17g_altri_debiti_lungo: float = pydantic.Field(0, description="D.6)+D.9-11bis)+D.14) Acconti + verso controllate/collegate/controllanti + altri debiti — oltre l'esercizio")
    sp18_ratei_risconti_passivi: float = pydantic.Field(0, description="E) Ratei e risconti passivi")
    totale_attivo: float = pydantic.Field(0, description="Totale attivo (total assets)")
    totale_passivo: float = pydantic.Field(0, description="Totale passivo (total equity + liabilities)")
    totale_debiti: float = pydantic.Field(0, description="Totale debiti (D) — the explicit 'Totale debiti' line from the PDF, sum of all debt categories (both entro and oltre). Used for validation.")
    totale_crediti: float = pydantic.Field(0, description="Totale crediti (C.II) — the explicit 'Totale crediti' line from the PDF, sum of all C.II debtor categories (both entro and oltre). Used for validation.")


class IncomeStatementExtraction(_ItalianNumberModel):
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
# SP end: the closing "Totale ... passivo/passività" line. Gestionali word it many ways
# ("Totale passivo", "Totale passività", "Totale STATO PATRIMONIALE passivo",
# "Totale passivo e patrimonio netto", ...). A plain "totale passivo" substring misses
# the variants with words in between (e.g. budget_352 "TOTALE STATO PATRIMONIALE PASSIVO"),
# which truncated the SP window before the passivo pages and broke the balance. Keep this
# list broad; _find_end scans from sp_start forward so the first SP-closing total wins.
SP_END_KEYWORDS = [
    "totale passivo",
    "totale passività",
    "totale stato patrimoniale passivo",
    "totale dello stato patrimoniale passivo",
    "totale passivo e patrimonio netto",
    "totale passivo e netto",
    "totale passività e patrimonio netto",
    "totale passività e netto",
]

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
SP_FALLBACK_KEYWORDS = [
    "totale attivo", "totale passivo",
    "attivo circolante",      # always present on BS asset pages
    "patrimonio netto",       # always present on BS liability pages
]
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
    # Relaxed SP start (sezioni contrapposte / "dettaglio voci"): some layouts have a
    # "Stato patrimoniale" header but no plain "Attivo" token (they use ATTIVITA' /
    # column headers), so the strict two-keyword match fails and the SP section text
    # never reaches the LLM (empty BS — budget_249/188). Fall back to the
    # "stato patrimoniale" header alone, on the FIRST page that has it and is not a CE
    # page (avoid matching a running "...Conto Economico a Sezioni Contrapposte" header).
    # "situazione patrimoniale" is the SP header used by some trial-balance / "bilancio
    # di verifica" printouts that have no "Stato patrimoniale"/"Attivo" tokens at all.
    _SP_HEADER_VARIANTS = ('stato patrimoniale', 'situazione patrimoniale')
    if sp_start is None:
        for i in range(total_pages):
            t = page_texts[i]
            if any(h in t for h in _SP_HEADER_VARIANTS) and 'conto economico' not in t:
                sp_start = i
                break
        # If every page carries a combined SP+CE running header, accept the first
        # SP-header page regardless (better than the first-6-pages last resort).
        if sp_start is None:
            for i in range(total_pages):
                if any(h in page_texts[i] for h in _SP_HEADER_VARIANTS):
                    sp_start = i
                    break
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

    # Relaxed (sezioni contrapposte / "dettaglio voci" CE): some layouts have NO
    # "valore della produzione" line at all — the CE is presented as two columns
    # (RICAVI / COSTI) under a "Conto economico" header. Detect the CE section by the
    # ricavi+costi column markers on a page after the SP section, so the CE text
    # actually reaches the LLM (otherwise CE comes back all zeros — budget_188/338/135).
    def _has_ce_columns(page_text: str) -> bool:
        has_rev = ('ricavi' in page_text or 'ricavo' in page_text)
        has_cost = ('costi' in page_text or 'costo' in page_text)
        # require a CE section header on the page to avoid matching SP pages that
        # merely mention "costi"/"ricavi" in a line description
        has_ce_header = 'conto economico' in page_text
        return has_rev and has_cost and has_ce_header

    if ce_start is None:
        search_from = (sp_end + 1) if sp_end is not None else (
            (sp_start + 1) if sp_start is not None else 0
        )
        for i in range(search_from, total_pages):
            if _has_ce_columns(page_texts[i]):
                ce_start = i
                break
        # If nothing after SP end, retry across the whole document (CE may share a page
        # with the SP tail in very compact statements)
        if ce_start is None:
            for i in range(total_pages):
                if _has_ce_columns(page_texts[i]):
                    ce_start = i
                    break

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

    # Zeroed-leading-section guard (draft "provvisorio" PDFs — budget_355/356):
    # some exports render the IV-CEE schema (labels + SP/CE headers) with every amount
    # at "0,00" up front, then put the REAL figures on later pages with no section
    # header. The header-based detection locks onto the zero copy and the LLM only ever
    # sees zeros (→ empty BS, "does not balance"). This is SAFE to correct because it
    # only fires when the selected SP pages carry a negligible amount mass compared with
    # the largest data page in the document (a normal IV-CEE statement never satisfies
    # that — its SP pages hold real totals): we slide the SP/CE windows forward, by the
    # same offset, onto the first later page that begins a substantial data block.
    def _page_amount_mass(text: str) -> float:
        s = 0.0
        for tok in re.findall(r'-?\d[\d.]*,\d{2}', text):
            try:
                s += abs(float(tok.replace('.', '').replace(',', '.')))
            except ValueError:
                continue
        return s

    page_mass = [_page_amount_mass(t) for t in page_texts]
    doc_max_mass = max(page_mass) if page_mass else 0.0
    sp_mass = sum(page_mass[p] for p in sp_pages)
    if sp_pages and doc_max_mass > 0 and sp_mass < 0.02 * doc_max_mass:
        # Only relocate to a GENUINE second copy of the statement that re-states the SP
        # header AND carries real amounts. We deliberately do NOT relocate to a headerless
        # number-only data block (e.g. a coordinate-split account dump like budget_355):
        # the IV-CEE LLM cannot map those columns, so masking them as a "result" would be
        # worse than failing honestly. Such files must fall through to the honest
        # "does not balance" error / a dedicated deterministic parser.
        second_start = next(
            (i for i in range(max(sp_pages) + 1, total_pages)
             if all(kw in page_texts[i] for kw in SP_START_KEYWORDS)
             and page_mass[i] >= 0.20 * doc_max_mass),
            None,
        )
        if second_start is not None:
            delta = second_start - min(sp_pages)
            shifted_sp = {min(p + delta, total_pages - 1) for p in sp_pages}
            shifted_ce = {min(p + delta, total_pages - 1) for p in ce_pages}
            logger.warning(
                f"Zeroed leading section detected (sp_mass={sp_mass:.0f} vs "
                f"doc_max={doc_max_mass:.0f}); a real second copy starts at page "
                f"{second_start}; shifting SP/CE windows by {delta} pages "
                f"(SP {sorted(sp_pages)}->{sorted(shifted_sp)})"
            )
            sp_pages = shifted_sp
            ce_pages = shifted_ce or ce_pages

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
    sp_text = _preprocess_stampa_dettaglio(sp_text)
    ce_text = _preprocess_stampa_dettaglio(ce_text)
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
  PLUS "imposte anticipate" (deferred tax assets) if shown as a separate line within crediti
- sp07_crediti_lungo = SUM of ALL "esigibili oltre l'esercizio successivo" amounts across ALL crediti categories
- CRITICAL: sp06 + sp07 MUST equal "Totale crediti". If they don't, add the difference to sp06.
  Common cause: "imposte anticipate" is a separate line within crediti that must be included in sp06.
- If crediti are not split by maturity, put the TOTAL Crediti in sp06_crediti_breve and sp07=0

CREDITI — DEBTOR-TYPE BREAKDOWN (split each group into entro + oltre):
- For each C.II) Crediti sub-item, separate "entro l'esercizio successivo" (sp06*) from "oltre l'esercizio successivo" (sp07*).
- Map each OIC item to its bucket:
  * C.II.1 Crediti verso clienti             -> sp06a / sp07a
  * C.II.2 Crediti verso imprese controllate -> sp06b / sp07b
  * C.II.3 Crediti verso imprese collegate   -> sp06c / sp07c
  * C.II.4 Crediti verso controllanti + C.II.5 Crediti verso imprese sottoposte al controllo delle controllanti -> sp06d / sp07d
  * C.II.5-bis Crediti tributari             -> sp06e / sp07e
  * C.II.5-ter Imposte anticipate            -> sp06f / sp07f
  * C.II.5-quater Crediti verso altri        -> sp06g / sp07g
- CRITICAL: sp06a+sp06b+sp06c+sp06d+sp06e+sp06f+sp06g MUST equal sp06_crediti_breve.
- CRITICAL: sp07a+sp07b+sp07c+sp07d+sp07e+sp07f+sp07g MUST equal sp07_crediti_lungo.
- If a group is missing in the PDF, leave it at 0.
- If the PDF shows only "Totale crediti" without a breakdown, put everything in sp06g_crediti_altri_breve (or sp07g_crediti_altri_lungo for long-term) to match the aggregate — do NOT invent sub-totals.
- IMPORTANT: Do NOT confuse C.II Crediti (operating receivables in "Attivo circolante") with B.III.2 Crediti (immobilized financial receivables). Only extract C.II values here.

DEBITI (in PASSIVO section, AFTER "Totale attivo"):
- IMPORTANT: "entro/oltre" in the PASSIVO section refers to DEBTS, not credits
- First find TOTALE Debiti (D) — the sum of all debt categories. Put this exact line's value into `totale_debiti`.
- sp17_debiti_lungo: look for ALL "di cui esigibili oltre l'esercizio successivo" sub-lines
  under individual debt items (e.g., under "Debiti verso fornitori", under "Altri debiti", etc.)
  and SUM them. These "di cui" lines are indented sub-totals showing the long-term portion.
- sp16_debiti_breve = TOTALE Debiti (D) minus sp17_debiti_lungo
- CRITICAL: sp16 + sp17 MUST equal TOTALE Debiti (D). If they don't, recalculate sp16 as the difference.
- If debiti are not split by maturity at all, put TOTALE Debiti in sp16_debiti_breve and sp17=0

DEBITI — CREDITOR-TYPE BREAKDOWN (split each group into entro + oltre):
- For each debt item, separate "entro l'esercizio successivo" (sp16*) from "oltre l'esercizio successivo" (sp17*).
- Map each OIC item to its bucket:
  * D.4 Debiti verso banche                                    -> sp16a / sp17a
  * D.3 verso soci per finanziamenti + D.5 verso altri finanziatori -> sp16b / sp17b
  * D.1 Obbligazioni + D.2 Obbligazioni convertibili + D.8 rappresentati da titoli -> sp16c / sp17c
  * D.7 Debiti verso fornitori                                 -> sp16d / sp17d
  * D.12 Debiti tributari                                      -> sp16e / sp17e
  * D.13 Debiti verso istituti di previdenza/sicurezza sociale -> sp16f / sp17f
  * D.6 Acconti + D.9/10/11/11bis verso controllate/collegate/controllanti + D.14 Altri debiti -> sp16g / sp17g
- CRITICAL: sp16a+sp16b+sp16c+sp16d+sp16e+sp16f+sp16g MUST equal sp16_debiti_breve.
- CRITICAL: sp17a+sp17b+sp17c+sp17d+sp17e+sp17f+sp17g MUST equal sp17_debiti_lungo.
- If a group is missing in the PDF, leave it at 0.
- If the PDF shows only the "Totale debiti" without a breakdown, put everything in sp16g_altri_debiti_breve (or sp17g_altri_debiti_lungo for long-term) to match the aggregate — do NOT invent sub-totals.

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
  PLUS "imposte anticipate" (deferred tax assets) if shown as a separate line within crediti
- sp07_crediti_lungo = SUM of ALL "esigibili oltre l'esercizio successivo" amounts across ALL crediti categories
- CRITICAL: sp06 + sp07 MUST equal "Totale crediti". If they don't, add the difference to sp06.
  Common cause: "imposte anticipate" is a separate line within crediti that must be included in sp06.
- If crediti are not split by maturity, put the TOTAL Crediti in sp06_crediti_breve and sp07=0

CREDITI — DEBTOR-TYPE BREAKDOWN (split each group into entro + oltre):
- For each C.II) Crediti sub-item, separate "entro l'esercizio successivo" (sp06*) from "oltre l'esercizio successivo" (sp07*).
- Map each OIC item to its bucket:
  * C.II.1 Crediti verso clienti             -> sp06a / sp07a
  * C.II.2 Crediti verso imprese controllate -> sp06b / sp07b
  * C.II.3 Crediti verso imprese collegate   -> sp06c / sp07c
  * C.II.4 Crediti verso controllanti + C.II.5 Crediti verso imprese sottoposte al controllo delle controllanti -> sp06d / sp07d
  * C.II.5-bis Crediti tributari             -> sp06e / sp07e
  * C.II.5-ter Imposte anticipate            -> sp06f / sp07f
  * C.II.5-quater Crediti verso altri        -> sp06g / sp07g
- CRITICAL: sp06a+sp06b+sp06c+sp06d+sp06e+sp06f+sp06g MUST equal sp06_crediti_breve.
- CRITICAL: sp07a+sp07b+sp07c+sp07d+sp07e+sp07f+sp07g MUST equal sp07_crediti_lungo.
- If a group is missing in the PDF, leave it at 0.
- If the PDF shows only "Totale crediti" without a breakdown, put everything in sp06g_crediti_altri_breve (or sp07g_crediti_altri_lungo for long-term) to match the aggregate — do NOT invent sub-totals.
- IMPORTANT: Do NOT confuse C.II Crediti (operating receivables in "Attivo circolante") with B.III.2 Crediti (immobilized financial receivables). Only extract C.II values here.

DEBITI (in PASSIVO section, AFTER "Totale attivo"):
- IMPORTANT: "entro/oltre" in the PASSIVO section refers to DEBTS, not credits
- First find TOTALE Debiti (D) — the sum of all debt categories. Put this exact line's value into `totale_debiti`.
- sp17_debiti_lungo: look for ALL "di cui esigibili oltre l'esercizio successivo" sub-lines
  under individual debt items (e.g., under "Debiti verso fornitori", under "Altri debiti", etc.)
  and SUM them. These "di cui" lines are indented sub-totals showing the long-term portion.
- sp16_debiti_breve = TOTALE Debiti (D) minus sp17_debiti_lungo
- CRITICAL: sp16 + sp17 MUST equal TOTALE Debiti (D). If they don't, recalculate sp16 as the difference.
- If debiti are not split by maturity at all, put TOTALE Debiti in sp16_debiti_breve and sp17=0

DEBITI — CREDITOR-TYPE BREAKDOWN (split each group into entro + oltre):
- For each debt item, separate "entro l'esercizio successivo" (sp16*) from "oltre l'esercizio successivo" (sp17*).
- Map each OIC item to its bucket:
  * D.4 Debiti verso banche                                    -> sp16a / sp17a
  * D.3 verso soci per finanziamenti + D.5 verso altri finanziatori -> sp16b / sp17b
  * D.1 Obbligazioni + D.2 Obbligazioni convertibili + D.8 rappresentati da titoli -> sp16c / sp17c
  * D.7 Debiti verso fornitori                                 -> sp16d / sp17d
  * D.12 Debiti tributari                                      -> sp16e / sp17e
  * D.13 Debiti verso istituti di previdenza/sicurezza sociale -> sp16f / sp17f
  * D.6 Acconti + D.9/10/11/11bis verso controllate/collegate/controllanti + D.14 Altri debiti -> sp16g / sp17g
- CRITICAL: sp16a+sp16b+sp16c+sp16d+sp16e+sp16f+sp16g MUST equal sp16_debiti_breve.
- CRITICAL: sp17a+sp17b+sp17c+sp17d+sp17e+sp17f+sp17g MUST equal sp17_debiti_lungo.
- If a group is missing in the PDF, leave it at 0.
- If the PDF shows only the "Totale debiti" without a breakdown, put everything in sp16g_altri_debiti_breve (or sp17g_altri_debiti_lungo for long-term) to match the aggregate — do NOT invent sub-totals.

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
- ce08_costi_personale = Total personnel costs. Use "Totale costi per il personale" if present, otherwise "9) per il personale". If the "9)" line shows a dash but sub-items (a/b/c/d/e) and a "Totale" line exist, use the Totale value.
- ce08a_tfr_accrual = sub-item "c) trattamento di fine rapporto" under personnel costs (item 9c)
- ce09_ammortamenti = Total depreciation/amortization. Use "Totale ammortamenti e svalutazioni" if present, otherwise "10) ammortamenti e svalutazioni". If the "10)" line shows a dash but sub-items and a "Totale" line exist, use the Totale value.
- Extract sub-items ce09a (10a), ce09b (10b), ce09c (10c), ce09d (10d) if available
- IMPORTANT: ce02_variazioni_rimanenze (item 2) and ce10_var_rimanenze_mat_prime (item 11) are DIFFERENT items. Do NOT confuse them:
  - ce02 = item 2) "Variazioni delle rimanenze di PRODOTTI in corso di lavorazione, semilavorati e finiti" (under A) Valore della produzione)
  - ce10 = item 11) "Variazioni delle rimanenze di MATERIE PRIME, sussidiarie, di consumo e merci" (under B) Costi della produzione)
  - If only one "variazioni rimanenze" item exists and it's under B) Costi, it's ce10. Set ce02 to 0.
- ce04_altri_ricavi = item 5) "Altri ricavi e proventi" — use the TOTAL including sub-items (contributi in conto esercizio + altri). Use "Totale altri ricavi e proventi" if present.
- ce10_var_rimanenze_mat_prime = item 11) variazioni delle rimanenze di materie prime (under B costs, NOT item 2)
- ce11_accantonamenti = item 12) accantonamenti per rischi
- ce11b_altri_accantonamenti = item 13) altri accantonamenti
- ce15_oneri_finanziari = item 17) interessi e altri oneri finanziari (total)
- Items 2) and 3) may be merged; if so put the combined value in ce02_variazioni_rimanenze

SEZIONI CONTRAPPOSTE / "DETTAGLIO VOCI" LAYOUTS (CRITICAL — do NOT return zeros):
- Some statements do NOT have a classic single-column Conto Economico. Instead they
  present the income statement as TWO SIDE-BY-SIDE SECTIONS: "RICAVI" (revenues, one side)
  and "COSTI" (costs, the other side), often under a "Conto Economico" header, with
  account-level detail lines (e.g. "06.01.01.01.001 Vendita beni ..." or "07.01.01.01.004 Merci").
- You MUST still extract the CE values from these layouts. Treat the RICAVI side as the
  revenue items (A) and the COSTI side as the cost items (B):
  * Sum all "Vendita / Ricavi delle vendite e prestazioni" account lines into ce01_ricavi_vendite.
  * Sum "Altri ricavi e proventi / contributi / sopravvenienze attive" into ce04_altri_ricavi.
  * Map purchases of goods/raw materials ("Acquisti", "Merci", "Materie prime") to ce05_materie_prime.
  * Map "per servizi" costs to ce06_servizi; "godimento beni di terzi"/affitti to ce07_godimento_beni.
  * Map personnel ("Salari", "Stipendi", "Oneri sociali", "TFR") to ce08_costi_personale.
  * Map "Ammortamenti"/"Svalutazioni" to ce09_ammortamenti.
  * Map "Oneri diversi di gestione"/"sopravvenienze passive" to ce12_oneri_diversi.
  * Map "Interessi"/"oneri finanziari" to ce15_oneri_finanziari; financial income to ce14.
  * Map "Imposte sul reddito"/"IRES"/"IRAP" to ce20_imposte.
- If only account-level lines are present (no IV CEE subtotals), AGGREGATE the relevant
  detail lines yourself into the matching ce* field. NEVER leave the whole CE at zero when
  revenue and cost lines are clearly present in the text.

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
- ce08_costi_personale = Total personnel costs. Use "Totale costi per il personale" if present, otherwise "9) per il personale". If the "9)" line shows a dash but sub-items (a/b/c/d/e) and a "Totale" line exist, use the Totale value.
- ce08a_tfr_accrual = sub-item "c) trattamento di fine rapporto" under personnel costs (item 9c)
- ce09_ammortamenti = Total depreciation/amortization. Use "Totale ammortamenti e svalutazioni" if present, otherwise "10) ammortamenti e svalutazioni". If the "10)" line shows a dash but sub-items and a "Totale" line exist, use the Totale value.
- Extract sub-items ce09a (10a), ce09b (10b), ce09c (10c), ce09d (10d) if available
- IMPORTANT: ce02_variazioni_rimanenze (item 2) and ce10_var_rimanenze_mat_prime (item 11) are DIFFERENT items. Do NOT confuse them:
  - ce02 = item 2) "Variazioni delle rimanenze di PRODOTTI in corso di lavorazione, semilavorati e finiti" (under A) Valore della produzione)
  - ce10 = item 11) "Variazioni delle rimanenze di MATERIE PRIME, sussidiarie, di consumo e merci" (under B) Costi della produzione)
  - If only one "variazioni rimanenze" item exists and it's under B) Costi, it's ce10. Set ce02 to 0.
- ce04_altri_ricavi = item 5) "Altri ricavi e proventi" — use the TOTAL including sub-items (contributi in conto esercizio + altri). Use "Totale altri ricavi e proventi" if present.
- ce10_var_rimanenze_mat_prime = item 11) variazioni delle rimanenze di materie prime (under B costs, NOT item 2)
- ce11_accantonamenti = item 12) accantonamenti per rischi
- ce11b_altri_accantonamenti = item 13) altri accantonamenti
- ce15_oneri_finanziari = item 17) interessi e altri oneri finanziari (total)
- Items 2) and 3) may be merged; if so put the combined value in ce02_variazioni_rimanenze

SEZIONI CONTRAPPOSTE / "DETTAGLIO VOCI" LAYOUTS (CRITICAL — do NOT return zeros):
- Some statements do NOT have a classic single-column Conto Economico. Instead they
  present the income statement as TWO SIDE-BY-SIDE SECTIONS: "RICAVI" (revenues, one side)
  and "COSTI" (costs, the other side), often under a "Conto Economico" header, with
  account-level detail lines (e.g. "06.01.01.01.001 Vendita beni ..." or "07.01.01.01.004 Merci").
- You MUST still extract the CE values from these layouts. Treat the RICAVI side as the
  revenue items (A) and the COSTI side as the cost items (B):
  * Sum all "Vendita / Ricavi delle vendite e prestazioni" account lines into ce01_ricavi_vendite.
  * Sum "Altri ricavi e proventi / contributi / sopravvenienze attive" into ce04_altri_ricavi.
  * Map purchases of goods/raw materials ("Acquisti", "Merci", "Materie prime") to ce05_materie_prime.
  * Map "per servizi" costs to ce06_servizi; "godimento beni di terzi"/affitti to ce07_godimento_beni.
  * Map personnel ("Salari", "Stipendi", "Oneri sociali", "TFR") to ce08_costi_personale.
  * Map "Ammortamenti"/"Svalutazioni" to ce09_ammortamenti.
  * Map "Oneri diversi di gestione"/"sopravvenienze passive" to ce12_oneri_diversi.
  * Map "Interessi"/"oneri finanziari" to ce15_oneri_finanziari; financial income to ce14.
  * Map "Imposte sul reddito"/"IRES"/"IRAP" to ce20_imposte.
- If only account-level lines are present (no IV CEE subtotals), AGGREGATE the relevant
  detail lines yourself into the matching ce* field. NEVER leave the whole CE at zero when
  revenue and cost lines are clearly present in the text. This applies to BOTH year columns
  when two columns are present; if there is only ONE value column, fill current_year only
  and leave prior_year at 0.

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
# Vision-based extraction (fallback for image-only PDFs)
# ---------------------------------------------------------------------------

def _render_pdf_pages_as_images(file_path: str, pages: Optional[Set[int]] = None, dpi: int = 200) -> List[str]:
    """Render PDF pages as base64-encoded PNG images using PyMuPDF.

    Args:
        file_path: Path to the PDF
        pages: Set of zero-based page indices (None = all pages)
        dpi: Resolution for rendering

    Returns:
        List of base64-encoded PNG strings
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")

    if pages is None:
        pages = set(range(len(doc)))

    images = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    for p in sorted(pages):
        if p < len(doc):
            pix = doc[p].get_pixmap(matrix=matrix)
            images.append(base64.standard_b64encode(pix.tobytes("png")).decode("ascii"))

    doc.close()
    logger.info(f"Rendered {len(images)} PDF pages as images ({dpi} dpi)")
    return images


def _extract_with_llm_vision(
    client: anthropic.Anthropic,
    images: List[str],
    system_prompt: str,
    output_model: type[pydantic.BaseModel],
    section_name: str,
    tool_name: str,
    max_retries: int = 2,
) -> pydantic.BaseModel:
    """Call Claude with vision (page images) for structured extraction."""
    logger.info(f"Calling Claude (vision) for {section_name} extraction ({len(images)} images)...")

    tool = _build_tool_schema(output_model, tool_name)

    # Build content blocks: images + text instruction
    content: List[dict] = []
    for img_b64 in images:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
        })
    content.append({
        "type": "text",
        "text": (
            f"Extract the {section_name} values from these Italian balance sheet pages. "
            f"Use the {tool_name} tool to record your results."
        ),
    })

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            response = client.messages.create(
                model=PDF_LLM_MODEL,
                max_tokens=PDF_LLM_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": content}],
                tools=[tool],
                tool_choice={"type": "tool", "name": tool_name},
            )

            for block in response.content:
                if block.type == "tool_use":
                    result = output_model.model_validate(block.input)
                    logger.info(f"{section_name} vision extraction complete")
                    return result

            raise PDFImportError(f"No tool_use block in {section_name} vision response")

        except anthropic.InternalServerError as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(f"API 500 error, retrying in {wait}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
            else:
                raise

    raise last_error  # unreachable but satisfies type checker


def _is_image_pdf(file_path: str) -> bool:
    """Check if a PDF contains no extractable text (image-only)."""
    try:
        doc = fitz.open(file_path)
        total_chars = sum(len(doc[p].get_text().strip()) for p in range(len(doc)))
        doc.close()
        return total_chars < 50  # threshold: fewer than 50 chars = image-based
    except Exception:
        return False


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

# Ambiguous fields handled explicitly in _normalize_ce_signs Pass 2 when the PDF uses
# the "all costs as negative" convention:
#   ce10_var_rimanenze_mat_prime — a variation that can be a cost OR a credit; it must
#     be NEGATED (not abs'd) so an inventory-increase credit shown as +X becomes -X.
#   ce20_imposte — effectively always an expense; flipped to positive only when negative.


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
    # convention — handle the ambiguous fields.
    if len(flipped) >= 3:
        # ce10 (variazioni rimanenze materie prime) is NOT a pure cost: an inventory
        # INCREASE is a credit that REDUCES COPRO and is printed with the opposite
        # sign of the surrounding cost block (i.e. a plain positive number, while the
        # real costs are in parentheses). The correct transform is therefore to NEGATE
        # it — the very same flip applied to every cost line — so a +X credit becomes
        # -X in the positive-cost model and a real cost shown as -X becomes +X. Using
        # abs() (the old behaviour) left a +X credit untouched and inflated COPRO by 2X,
        # breaking the CE cross-foot (e.g. ALMA item 11 = +7.831 → CE off by 15.662).
        ce10 = income_data.get('ce10_var_rimanenze_mat_prime', Decimal('0'))
        if ce10 != 0:
            income_data['ce10_var_rimanenze_mat_prime'] = -ce10
            flipped.append('ce10_var_rimanenze_mat_prime')
        # ce20 (imposte) is effectively always an expense in these layouts; flip the
        # parenthesised (negative) presentation to positive, leave an already-positive
        # value alone (its own cross-check in _validate_ce_imposte guards edge cases).
        ce20 = income_data.get('ce20_imposte', Decimal('0'))
        if ce20 < 0:
            income_data['ce20_imposte'] = abs(ce20)
            flipped.append('ce20_imposte')

    if flipped:
        logger.info(f"CE sign normalization: flipped {len(flipped)} fields to positive: {flipped}")
    return income_data


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def extract_pdf_with_llm(
    file_path: str, force_llm: bool = False
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """
    Extract balance sheet and income statement from PDF using PyMuPDF + Claude Haiku 4.5.

    For "Situazione Contabile" (trial balance) PDFs with XX/YY/ZZZ account codes,
    uses a deterministic parser instead of the LLM — UNLESS force_llm=True, which skips
    the trial-balance re-routing. The caller in pdf_importer uses this when the
    deterministic parser already ran and yielded an empty extraction (a mis-detected
    bilancio, e.g. budget_313/314): without force_llm the LLM path would re-detect the
    trial-balance format and bounce straight back to the same empty deterministic parser,
    defeating the fallback.

    Requires ANTHROPIC_API_KEY environment variable (unless situazione contabile).

    Args:
        file_path: Path to the PDF file

    Returns:
        (balance_sheet_data, income_data) - dictionaries with Decimal values

    Raises:
        PDFImportError: If extraction fails
    """
    # Check for Situazione Contabile format (trial balance with XX/YY/ZZZ codes)
    # Route to deterministic parser — bypasses LLM entirely
    try:
        doc = fitz.open(file_path)
        sample_text = ""
        for page in doc:
            sample_text += page.get_text()
            if len(sample_text) > 5000:
                break
        doc.close()
    except Exception:
        sample_text = ""

    from importers.situazione_contabile_parser import is_situazione_contabile, extract_situazione_contabile
    if not force_llm and is_situazione_contabile(sample_text):
        logger.info("Situazione contabile (trial balance) format detected, using deterministic parser")
        balance_sheet_data, income_data = extract_situazione_contabile(file_path)
        # Skip LLM validators (_validate_crediti/_validate_debiti/_validate_equity)
        # as they rely on full column names and are designed to fix LLM errors.
        # The deterministic parser produces correct values directly.
        return balance_sheet_data, income_data

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

    # Step 1: Check if PDF is image-based (no extractable text)
    use_vision = _is_image_pdf(file_path)

    if use_vision:
        logger.info("Image-based PDF detected, using vision extraction")
        all_images = _render_pdf_pages_as_images(file_path)

        # Step 2v: Extract balance sheet via vision
        try:
            sp_result = _extract_with_llm_vision(
                client, all_images, SP_SYSTEM_PROMPT,
                BalanceSheetExtraction, "Stato Patrimoniale",
                tool_name="balance_sheet",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during SP vision extraction: {e}")

        # Step 3v: Extract income statement via vision
        try:
            ce_result = _extract_with_llm_vision(
                client, all_images, CE_SYSTEM_PROMPT,
                IncomeStatementExtraction, "Conto Economico",
                tool_name="income_statement",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during CE vision extraction: {e}")
    else:
        # Step 1b: Extract relevant page text with PyMuPDF
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

    # Step 5: Fold the result into totale_passivo when the layout reports it net of
    # the year's result (sezioni contrapposte / dettaglio voci); then validate crediti;
    # then debiti (using explicit totale_debiti when present); then equity (which uses
    # the corrected debt aggregate to derive expected equity).
    balance_sheet_data = _reconcile_utile_in_passivo(balance_sheet_data, "single")
    balance_sheet_data = _validate_crediti(balance_sheet_data, "single")
    balance_sheet_data = _validate_debiti(balance_sheet_data, "single")
    balance_sheet_data = _validate_equity(balance_sheet_data, "single")

    # Step 6: Reconcile ce10 sign on the BS utile anchor, then cross-check ce20_imposte
    income_data = _validate_ce10_against_bs(income_data, balance_sheet_data, "single")
    income_data = _validate_ce_imposte(income_data, balance_sheet_data, "single")

    return balance_sheet_data, income_data


# ---------------------------------------------------------------------------
# Trial-balance (situazione contabile / sezioni contrapposte) CoGe extraction
# ---------------------------------------------------------------------------
# Macro-area C documents are NOT legal IV-CEE statements: they are flat lists of
# general-ledger accounts (conti di contabilita' generale, "CoGe") with Dare/Avere
# or Saldo balances and NO art.2424/2425 schema. The IV-CEE prompts above read the
# legal schema and misfire on these. These dedicated prompts teach the model the
# trial-balance sign convention (Dare=asset/cost, Avere=liability/equity/revenue),
# contra-account netting (fondi ammortamento / svalutazione), and that the year's
# result is the Attivo-vs-Passivo gap — so the LLM actually reads the CoGe list.

TRIAL_BALANCE_SP_SYSTEM_PROMPT = """You are an expert Italian accountant reading a TRIAL BALANCE (bilancio di verifica / situazione contabile / saldi di contabilita' generale).

This is NOT a legal IV-CEE statement. It is a flat list of general-ledger accounts (conti CoGe), each with a code and one or two amount columns. Your job: classify the PATRIMONIAL accounts (assets, liabilities, equity) into the IV-CEE Stato Patrimoniale fields (sp01-sp18). IGNORE economic accounts (costi/ricavi) here — they belong to the income statement.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimals (1.234.567,89 = 1234567.89)
- Parentheses or a trailing minus mean negative
- Return plain numbers without formatting (no dots, no commas), in full euros

TRIAL-BALANCE LAYOUTS (handle all):
- Two columns "Dare" (debit) and "Avere" (credit): each account has a balance on ONE side; use that side's amount.
- A single "Saldo" column, sometimes with a D/A flag or a sign: the flag/sign tells the side.
- The COLUMN is ground truth for the side. Do NOT move an account to the other side based on its name.

SIGN / SIDE CONVENTION:
- ATTIVO (assets) accounts normally carry a DARE (debit) balance: cassa, banche c/c attive, crediti verso clienti, immobilizzazioni (immateriali/materiali/finanziarie), rimanenze/magazzino, ratei e risconti attivi, crediti tributari/erario c/, crediti v/altri.
- PASSIVO + PATRIMONIO NETTO accounts normally carry an AVERE (credit) balance: debiti verso fornitori, banche c/c passive (scoperti), capitale sociale, riserve, fondo rischi, fondo TFR, debiti tributari, debiti v/istituti previdenziali, ratei e risconti passivi.
- Report every sp* field as a POSITIVE magnitude on its natural side.

CONTRA ACCOUNTS — NET THEM, never put in passivo:
- "Fondo ammortamento ..." (any: immobilizzazioni immateriali/materiali) is an AVERE account that REDUCES the related asset. Subtract it from the gross asset so sp02/sp03 are reported NET of their fondi ammortamento.
- "Fondo svalutazione crediti" reduces crediti: report sp06/sp07 NET of it.
- Do NOT classify these fondi as fondi rischi (sp14) or debiti.

MAPPING (description -> field), report NET magnitudes:
- sp01_crediti_soci: crediti verso soci per versamenti dovuti
- sp02_immob_immateriali: immobilizzazioni immateriali (avviamento, software, costi pluriennali) NET of fondo amm.to immateriali
- sp03_immob_materiali: immobilizzazioni materiali (terreni, fabbricati, impianti, macchinari, attrezzature, automezzi, mobili) NET of fondo amm.to materiali
- sp04_immob_finanziarie: partecipazioni, crediti immobilizzati, titoli immobilizzati
- sp05_rimanenze: rimanenze / magazzino (materie prime, prodotti, merci, lavori in corso)
- sp06_crediti_breve: crediti dell'attivo circolante esigibili ENTRO l'esercizio (clienti, tributari, v/altri) NET of fondo svalutazione
- sp07_crediti_lungo: crediti dell'attivo circolante esigibili OLTRE l'esercizio
- sp08_attivita_finanziarie: attivita' finanziarie non immobilizzate (titoli, partecipazioni non durevoli)
- sp09_disponibilita_liquide: cassa, denaro, banche e poste c/c ATTIVI (saldo Dare)
- sp10_ratei_risconti_attivi: ratei e risconti attivi
- sp11_capitale: capitale sociale
- sp12_riserve: TUTTE le riserve (sovrapprezzo, rivalutazione, legale, statutarie, straordinaria, altre) + utili/(perdite) portati a nuovo. Do NOT include the current-year result here.
- sp13_utile_perdita: the CURRENT YEAR result — see RESULT rule below
- sp14_fondi_rischi: fondi per rischi e oneri (NOT fondi ammortamento)
- sp15_tfr: fondo trattamento di fine rapporto (TFR)
- sp16_debiti_breve: debiti esigibili ENTRO l'esercizio (fornitori, banche c/c passive, tributari, previdenziali, v/altri)
- sp17_debiti_lungo: debiti esigibili OLTRE l'esercizio (mutui, finanziamenti a lungo)
- sp18_ratei_risconti_passivi: ratei e risconti passivi

CREDITOR / DEBTOR BREAKDOWN — PRESERVE THE SOURCE'S DETAIL DEPTH:
- A trial balance names each account by type (es. "DEBITI V/FORNITORI", "ERARIO C/IVA",
  "INPS C/CONTRIBUTI", "MUTUO BANCA..."). When the type is determinable from the
  description, you MUST fill the matching typed sub-field — do NOT collapse everything
  into the aggregate. The sub-fields must sum to the aggregate:
  * crediti: sp06a/sp07a clienti, sp06e/sp07e tributari (erario, IVA, ritenute),
    sp06f imposte anticipate, sp06g/sp07g altri
  * debiti: sp16a/sp17a banche (mutui, c/c passivi), sp16b/sp17b altri finanziatori,
    sp16c/sp17c obbligazioni, sp16d/sp17d fornitori, sp16e/sp17e tributari (erario, IVA),
    sp16f/sp17f previdenza (INPS, INAIL), sp16g/sp17g altri (acconti, c/terzi, ...)
- Only leave a sub-field at 0 when no account of that type exists. Put a debt/credit
  whose type you genuinely cannot tell into the 'altri' bucket (sp16g / sp06g), never
  silently into the bare aggregate.

RESULT OF THE YEAR (sp13) — THE BALANCING RULE:
- A trial balance usually has NO "utile d'esercizio" account: the profit/loss is implicit.
- Compute sp13 so that the sheet balances: sp13 = totale_attivo - (sp11 + sp12 + sp14 + sp15 + sp16 + sp17 + sp18).
- A POSITIVE sp13 = utile; a NEGATIVE sp13 = perdita. Keep the sign.
- Only if the trial balance EXPLICITLY shows a separate "Utile/Perdita d'esercizio" account, use that value and verify it equals the gap.

COMPLETENESS — THE MOST IMPORTANT RULE (do not drop accounts):
- EVERY patrimonial account line in the trial balance must be classified into exactly one sp field. Do not skip lines, do not stop early on long lists, scan ALL pages.
- The trial balance prints its OWN control total ("TOTALE A PAREGGIO", "TOTALE ATTIVITA'", "TOTALE PASSIVITA'"). Your sum of the asset accounts MUST reconcile to the declared "TOTALE ATTIVITA'" (GROSS, i.e. before you net the fondi). If your running asset total is materially below the printed total, you have MISSED accounts — go back and find them before answering. The single most common error is dropping a whole block of debiti (fornitori, banche, tributari, previdenziali) or a large immobilizzazioni mastro.
- MASTRO + DOTTED CHILDREN layout: some trial balances print each voce as a level-1 "mastro" WITH its subtotal (e.g. "102 IMMOBILIZZAZIONI IMMATERIALI 2.429.051"), immediately followed by indented dotted children ("102.00002 Software 12.000"). Book the MASTRO SUBTOTAL ONCE. Do NOT also add its children (double-count) and do NOT add only the children while skipping the mastro (drops the rounding/other lines). One amount per voce.

TOTALS:
- totale_attivo = sum of sp01..sp10 (all NET of contra accounts)
- totale_passivo = sp11 + sp12 + sp13 + sp14 + sp15 + sp16 + sp17 + sp18
- totale_attivo MUST equal totale_passivo (sp13 absorbs the difference). Set both fields.
- Leave totale_debiti and totale_crediti at 0 unless the trial balance prints an explicit "Totale debiti"/"Totale crediti" line."""

TRIAL_BALANCE_CE_SYSTEM_PROMPT = """You are an expert Italian accountant reading a TRIAL BALANCE (bilancio di verifica / situazione contabile / saldi di contabilita' generale).

This is NOT a legal IV-CEE statement. It is a flat list of general-ledger accounts (conti CoGe). Your job: classify the ECONOMIC accounts (costi e ricavi) into the IV-CEE Conto Economico fields (ce01-ce20). IGNORE patrimonial accounts (assets, liabilities, equity) here.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimals (1.234.567,89 = 1234567.89)
- Parentheses or a trailing minus mean negative
- Return plain numbers without formatting, in full euros
- Report ALL COSTS as POSITIVE magnitudes (the model subtracts them). Report revenues as positive.

TRIAL-BALANCE SIGN CONVENTION:
- RICAVI / PROVENTI (revenue) accounts carry an AVERE (credit) balance.
- COSTI / ONERI (cost) accounts carry a DARE (debit) balance.
- Use the account's balance magnitude; the side identifies whether it is a revenue or a cost.

MAPPING (description -> field):
RICAVI (A — valore della produzione):
- ce01_ricavi_vendite: ricavi delle vendite e delle prestazioni (vendite merci/prodotti/servizi)
- ce02_variazioni_rimanenze: variazioni rimanenze di prodotti/semilavorati/lavori in corso
- ce03_lavori_interni: incrementi di immobilizzazioni per lavori interni
- ce04_altri_ricavi: altri ricavi e proventi, contributi in conto esercizio, sopravvenienze attive, rimborsi
COSTI (B — costi della produzione), all positive:
- ce05_materie_prime: acquisti di materie prime, sussidiarie, di consumo e merci
- ce06_servizi: costi per servizi (consulenze, utenze, trasporti, provvigioni, manutenzioni, compensi)
- ce07_godimento_beni: godimento beni di terzi (affitti, leasing, noleggi, royalties)
- ce08_costi_personale: TOTALE costi del personale (salari, stipendi, oneri sociali, TFR, altri)
- ce08a_tfr_accrual: quota TFR dell'esercizio (sub-item of ce08)
- ce09_ammortamenti: ammortamenti e svalutazioni (amm.to immateriali + materiali + svalutazioni crediti)
- ce10_var_rimanenze_mat_prime: variazioni rimanenze di materie prime/merci (segno: incremento rimanenze RIDUCE i costi)
- ce11_accantonamenti: accantonamenti per rischi
- ce11b_altri_accantonamenti: altri accantonamenti
- ce12_oneri_diversi: oneri diversi di gestione (imposte indirette, IMU, bolli, sopravvenienze passive, perdite su crediti)
AREA FINANZIARIA (C):
- ce13_proventi_partecipazioni: proventi da partecipazioni
- ce14_altri_proventi_finanziari: interessi attivi e altri proventi finanziari
- ce15_oneri_finanziari: interessi passivi e altri oneri finanziari (positive)
- ce16_utili_perdite_cambi: utili/perdite su cambi
RETTIFICHE (D) / STRAORDINARI (E) / IMPOSTE:
- ce17_rettifiche_attivita_fin: rivalutazioni/svalutazioni di attivita' finanziarie (net)
- ce18_proventi_straordinari: proventi straordinari
- ce19_oneri_straordinari: oneri straordinari (positive)
- ce20_imposte: imposte sul reddito dell'esercizio (IRES + IRAP) (positive)

RULES:
- AGGREGATE all account lines that map to the same ce* field (a trial balance has many detail accounts per IV-CEE item).
- NEVER leave the whole CE at zero when revenue and cost accounts are clearly present.
- Leave a field at 0 if no matching account exists.
- Extract the CURRENT YEAR values only."""


def _extract_full_text(file_path: str, max_pages: int = 60) -> str:
    """Return the concatenated text of (up to max_pages) PDF pages.

    Trial balances have no IV-CEE section headers to anchor on, so the whole
    account list is sent to the LLM rather than a detected SP/CE window.
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")
    parts = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        parts.append(page.get_text())
    doc.close()
    return "\n".join(parts)


# Completeness retry for the CoGe SP pass: the LLM stochastically drops accounts on
# long trial-balance lists. Re-run up to N times and keep the lowest-residual draw; stop
# early once a draw's estimated residual is under _COGE_SP_CLEAN_PCT of total assets.
_COGE_SP_MAX_ATTEMPTS = 3
_COGE_SP_CLEAN_PCT = Decimal("0.02")  # 2% of totale_attivo = "clean enough", stop retrying


def extract_trial_balance_with_llm(
    file_path: str,
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Extract a macro-area C trial balance (situazione contabile / CoGe accounts)
    with a dedicated LLM pass that understands Dare/Avere account balances.

    Unlike extract_pdf_with_llm (which reads the legal IV-CEE schema), this sends
    the FULL trial-balance text and uses CoGe-specific prompts to classify
    general-ledger accounts into sp01-sp18 / ce01-ce20, netting contra accounts
    and deriving the year's result as the Attivo-vs-Passivo gap.

    Returns:
        (balance_sheet_data, income_data) - dicts with full DB field names + Decimal values.

    Raises:
        PDFImportError: if the API key is missing or extraction fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")

    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

    is_image = _is_image_pdf(file_path)
    images = _render_pdf_pages_as_images(file_path) if is_image else None
    full_text = None
    if not is_image:
        full_text = _extract_full_text(file_path)
        if not full_text.strip():
            raise PDFImportError("No text extracted from trial-balance PDF")

    # Declared control totals (TOTALE A PAREGGIO / ATTIVO / explicit Utile-Perdita) read
    # deterministically from the printed footer — used BOTH as a hint to the LLM AND as
    # the post-pass reconciliation anchor.
    try:
        declared = _declared_control_totals(file_path)
    except Exception:
        declared = {}
    # Inject the declared totals as a completeness anchor in the SP system prompt.
    sp_prompt = TRIAL_BALANCE_SP_SYSTEM_PROMPT
    _anchor = declared.get("attivo") or declared.get("pareggio") if declared else None
    if _anchor:
        sp_prompt = (TRIAL_BALANCE_SP_SYSTEM_PROMPT
                     + f"\n\nDOCUMENT CONTROL TOTAL: the printed TOTALE ATTIVITA' / A PAREGGIO of "
                       f"THIS document is approximately {_anchor:,.0f} euro (gross). Your classified "
                       f"asset accounts (before netting fondi) must reconcile to this figure — if your "
                       f"sum is materially lower, you have dropped accounts: re-scan all pages.")

    def _extract_ce():
        if is_image:
            return _extract_with_llm_vision(
                client, images, TRIAL_BALANCE_CE_SYSTEM_PROMPT,
                IncomeStatementExtraction, "Situazione Contabile (CE)", tool_name="income_statement")
        return _extract_with_llm(
            client, full_text, TRIAL_BALANCE_CE_SYSTEM_PROMPT,
            IncomeStatementExtraction, "Situazione Contabile (CE)", tool_name="income_statement")

    def _extract_sp_once():
        if is_image:
            res = _extract_with_llm_vision(
                client, images, sp_prompt,
                BalanceSheetExtraction, "Situazione Contabile (SP)", tool_name="balance_sheet")
        else:
            res = _extract_with_llm(
                client, full_text, sp_prompt,
                BalanceSheetExtraction, "Situazione Contabile (SP)", tool_name="balance_sheet")
        bs = _model_to_decimal_dict(res)
        bs = _validate_crediti(bs, "coge")
        bs = _validate_debiti(bs, "coge")
        bs = _balance_trial_via_result(bs, "coge")
        try:
            bs = _reconcile_trial_to_declared(bs, declared, "coge")
        except Exception as _rec_err:
            logger.warning(f"[coge] declared-total reconciliation skipped: {_rec_err}")
        return bs

    # COMPLETENESS RETRY: the LLM stochastically drops accounts on long lists (proven by
    # byte-identical files extracting one complete / one short). Run the SP pass up to
    # _COGE_SP_MAX_ATTEMPTS times and keep the draw with the SMALLEST post-reconcile
    # _plug_residual (least estimated mass). Stop early once a draw is materially clean.
    best_bs = None
    best_resid = None
    for attempt in range(_COGE_SP_MAX_ATTEMPTS):
        bs = _extract_sp_once()
        resid = bs.get("_plug_residual", Decimal("0"))
        att = bs.get("totale_attivo", Decimal("0")) or Decimal("1")
        if best_bs is None or resid < best_resid:
            best_bs, best_resid = bs, resid
        logger.info(f"[CoGe] SP attempt {attempt + 1}/{_COGE_SP_MAX_ATTEMPTS}: "
                    f"totale_attivo={bs.get('totale_attivo')} plug_residual={resid}")
        if resid <= max(Decimal("1"), att * _COGE_SP_CLEAN_PCT):
            break  # clean enough, no need to retry

    balance_sheet_data = best_bs
    income_data = _normalize_ce_signs(_model_to_decimal_dict(_extract_ce()))

    logger.info(f"[CoGe] SP totale_attivo = {balance_sheet_data.get('totale_attivo')} "
                f"(plug_residual={best_resid})")

    income_data = _validate_ce10_against_bs(income_data, balance_sheet_data, "coge")
    income_data = _validate_ce_imposte(income_data, balance_sheet_data, "coge")

    return balance_sheet_data, income_data


# Asset-side sp fields used to recompute totale_attivo for the trial-balance identity.
_TB_ASSET_KEYS = [
    'sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
    'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve',
    'sp07_crediti_lungo', 'sp08_attivita_finanziarie',
    'sp09_disponibilita_liquide', 'sp10_ratei_risconti_attivi',
]
# Passivo/PN fields EXCLUDING sp13 (the result, which absorbs the balancing gap).
_TB_PASSIVO_KEYS_NO_RESULT = [
    'sp11_capitale', 'sp12_riserve', 'sp14_fondi_rischi', 'sp15_tfr',
    'sp16_debiti_breve', 'sp17_debiti_lungo', 'sp18_ratei_risconti_passivi',
]


def _balance_trial_via_result(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Force the trial-balance identity Attivo == Passivo by deriving sp13 as the gap.

    A CoGe trial balance has no legal totals to anchor on and (almost) never an
    explicit result account: the year's profit/loss is precisely the amount that
    makes the two sides tie. We recompute totale_attivo from the asset fields and
    set sp13 = totale_attivo - (passivo + PN excluding the result). Keeps the sign
    (positive = utile, negative = perdita). This mirrors the deterministic parser's
    pareggio logic, so route C stays balanced regardless of which extractor ran.
    """
    att = sum(balance_sheet_data.get(k, Decimal('0')) for k in _TB_ASSET_KEYS)
    pas_no_result = sum(balance_sheet_data.get(k, Decimal('0')) for k in _TB_PASSIVO_KEYS_NO_RESULT)
    sp13 = att - pas_no_result
    balance_sheet_data['sp13_utile_perdita'] = sp13
    balance_sheet_data['totale_attivo'] = att
    balance_sheet_data['totale_passivo'] = att  # by construction pas_no_result + sp13 == att
    logger.info(
        f"[{label}] trial-balance pareggio: attivo={att}, passivo(no result)={pas_no_result}, "
        f"sp13 (result)={sp13}"
    )
    return balance_sheet_data


# Italian-number token: 1.234.567,89 | 1234,89 | 1234567,89
_DECL_NUM_RE = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+,\d{2}")


def _declared_control_totals(file_path: str) -> Dict[str, Optional[Decimal]]:
    """Read a trial balance's OWN declared control totals from the printed footer.

    GENERAL anti-masking anchor (level L2): every situazione contabile / bilancio di
    verifica prints its own control totals — "TOTALE A PAREGGIO", "TOTALE ATTIVO/
    ATTIVITA'", "TOTALE PASSIVO/PASSIVITA'", and (usually) an explicit
    "UTILE/PERDITA D'ESERCIZIO" (also "del periodo" / "in corso di formazione").
    These are GROUND TRUTH for the magnitude of the sheet. Returned so the extractor
    can reconcile its classified sums to them instead of silently forcing balance.

    Robust to letter-spaced headers ("T O T A L E   A T T I V O") via a no-spaces
    variant of the text, and to Italian number formatting. Returns the LARGEST amount
    found per label (detail lines repeat small partials; the control total is the max).
    All keys may be None when the document does not print that line.
    """
    out: Dict[str, Optional[Decimal]] = {
        "attivo": None, "passivo": None, "pareggio": None, "utile": None, "perdita": None,
    }
    try:
        text = _extract_full_text(file_path)
    except Exception:
        return out
    low = text.lower()
    nos = re.sub(r"[ \t]+", "", low)  # collapse intra-line spacing (keep newlines)

    def _largest_after(markers) -> Optional[Decimal]:
        """Largest Italian-number amount occurring within ~80 chars after any marker,
        searched in BOTH the normal and the no-spaces text."""
        best: Optional[Decimal] = None
        for hay in (low, nos):
            for mk in markers:
                m = mk if " " not in mk else mk
                for hit in re.finditer(re.escape(mk.replace(" ", "")) if hay is nos else re.escape(mk), hay):
                    window = hay[hit.end(): hit.end() + 80]
                    for nm in _DECL_NUM_RE.finditer(window):
                        try:
                            v = Decimal(nm.group(0).replace(".", "").replace(",", "."))
                        except Exception:
                            continue
                        av = abs(v)
                        if av > 0 and (best is None or av > best):
                            best = av
                        break  # first number after the marker is the total
        return best

    out["pareggio"] = _largest_after(["totale a pareggio"])
    out["attivo"] = _largest_after([
        "totale attivo", "totale attivita", "totale dell'attivo",
        "totale stato patrimoniale attivo",
    ])
    out["passivo"] = _largest_after([
        "totale passivo", "totale passivita", "totale a pareggio passivo",
        "totale passivo e patrimonio netto", "totale passivita e netto",
    ])
    out["utile"] = _largest_after([
        "utile d'esercizio", "utile dell'esercizio", "utile di esercizio",
        "utile del periodo", "utile in corso di formazione", "utile (perdita) dell'esercizio",
        "risultato d'esercizio", "risultato dell'esercizio",
    ])
    out["perdita"] = _largest_after([
        "perdita d'esercizio", "perdita dell'esercizio", "perdita di esercizio",
        "perdita del periodo", "perdita in corso di formazione",
    ])
    return out


def _reconcile_trial_to_declared(balance_sheet_data: Dict[str, Decimal],
                                 declared: Dict[str, Optional[Decimal]],
                                 label: str) -> Dict[str, Decimal]:
    """Reconcile a forced-balanced trial-balance extraction against the document's OWN
    declared control totals (anti-masking, level L2).

    `_balance_trial_via_result` always ties the sheet by making sp13 absorb the gap,
    so a sheet "balances" even when the LLM dropped accounts on one side — the dropped
    mass becomes a FAKE profit/loss. This step compares the derived result/total against
    the printed control totals and, when they disagree materially:

      1. RESULT-ANCHORED (preferred): the document prints an explicit Utile/Perdita.
         residual = derived_sp13 - declared_result.  residual>0 ⇒ the PASSIVO side was
         short by `residual` (sp13 was inflated): book it into sp16 (debiti) and set
         sp13 to the declared value.  residual<0 ⇒ the ATTIVO side was short: book it
         into sp09 (liquidità) and lift both totals.  Either way the pareggio is
         preserved AND sp13 becomes the document's true result.
      2. TOTAL-COVERAGE (fallback, flag-only): no usable result anchor but the extracted
         totale_attivo falls short of the declared TOTALE ATTIVO/PAREGGIO — we cannot
         know which side, so we only expose the shortfall (no mass moved).

    In both cases the moved/short mass is exposed as `_plug_residual`, which
    `iv_cee_hierarchy.check_quadratura` reads to raise the QUADRATURA MASCHERATA flag
    (>1% of total) so the user sees an estimated composition and refines it in Rettifiche,
    instead of importing a silently-wrong sheet. Purely additive on a correct extraction
    (residual ≈ 0 ⇒ no-op), so it cannot regress files that already extract cleanly.
    """
    att = balance_sheet_data.get('totale_attivo', Decimal('0'))
    if att <= 0:
        return balance_sheet_data
    tol = max(Decimal('50'), abs(att) * Decimal('0.005'))

    # signed declared result: + utile, - perdita (utile wins when both are mis-detected)
    decl_result: Optional[Decimal] = None
    if declared.get('utile') is not None:
        decl_result = declared['utile']
    elif declared.get('perdita') is not None:
        decl_result = -declared['perdita']

    sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))

    # 1) result-anchored reconciliation
    if decl_result is not None and abs(sp13 - decl_result) > tol:
        residual = sp13 - decl_result
        if residual > 0:
            # passivo undercounted by `residual` (sp13 was inflated by the drop)
            balance_sheet_data['sp16_debiti_breve'] = (
                balance_sheet_data.get('sp16_debiti_breve', Decimal('0')) + residual)
        else:
            # attivo undercounted: lift assets and both totals
            add = -residual
            balance_sheet_data['sp09_disponibilita_liquide'] = (
                balance_sheet_data.get('sp09_disponibilita_liquide', Decimal('0')) + add)
            balance_sheet_data['totale_attivo'] = att + add
            balance_sheet_data['totale_passivo'] = att + add
        balance_sheet_data['sp13_utile_perdita'] = decl_result
        # ACCUMULATE (never clobber) — the deterministic parser may already expose its own
        # _plug_residual; this result-anchoring residual adds to it.
        balance_sheet_data['_plug_residual'] = (
            balance_sheet_data.get('_plug_residual', Decimal('0')) + abs(residual))
        _flag_unbalanced(
            label,
            f"sp13 derivato {sp13} != risultato dichiarato {decl_result}: ~{abs(residual)} "
            f"di massa non classificata (lato {'passivo' if residual > 0 else 'attivo'}) "
            f"stimata in sp16/sp09 — correggere in Rettifiche",
            residual,
        )
        return balance_sheet_data

    # 2) total-coverage fallback (flag only — side unknown, no mass moved)
    control = declared.get('attivo') or declared.get('passivo')
    if control and att + tol < control:
        gap = control - att
        balance_sheet_data['_plug_residual'] = max(
            balance_sheet_data.get('_plug_residual', Decimal('0')), gap)
        _flag_unbalanced(
            label,
            f"attivo estratto {att} < totale dichiarato {control}: ~{gap} di conti non "
            f"classificati (estrazione incompleta) — verificare in Rettifiche",
            gap,
        )
    return balance_sheet_data


# Anti-masking guard: a plug correction is rejected (and surfaced as a warning)
# when it would drive a field negative, or when its magnitude exceeds this fraction
# of total assets (a correction that large is almost certainly a structural
# extraction error, not a roundable discrepancy — better to flag than to hide).
_PLUG_CAP_FRACTION = Decimal('0.05')


def _plug_cap(balance_sheet_data: Dict[str, Decimal]) -> Decimal:
    """Absolute cap on a single plug correction = 5% of totale_attivo (fallback to
    totale_passivo, then a flat floor) so the cap is meaningful even when one total
    is missing."""
    base = abs(balance_sheet_data.get('totale_attivo', Decimal('0')))
    if base == 0:
        base = abs(balance_sheet_data.get('totale_passivo', Decimal('0')))
    cap = base * _PLUG_CAP_FRACTION
    # never below a flat floor so tiny statements still get a sane allowance
    return max(cap, Decimal('5000'))


def _flag_unbalanced(label: str, reason: str, diff: Decimal) -> None:
    """Emit an explicit, visible imbalance warning so a rejected/insufficient plug
    surfaces as an error instead of being silently masked.

    Kept log-only (does not mutate the data dict) so the Dict[str, Decimal] contract
    consumed by the mapper / harness stays intact."""
    logger.warning(f"BILANCIO NON QUADRATO [{label}]: {reason} (diff={diff})")


def _reconcile_utile_in_passivo(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Add the result of the year (sp13) into totale_passivo when the layout reports
    'Totale Passivo' NET of the result.

    In "sezioni contrapposte" / "dettaglio voci" layouts the bottom of the liabilities
    column shows a 'Totale Passivo' that excludes the 'Utile/Perdita d'esercizio' line
    (the result sits on its own line, often next to 'Totale a pareggio'). The tell-tale
    sign is that the balance gap equals exactly the result:

        totale_attivo - totale_passivo == sp13_utile_perdita   (within tolerance)

    When detected, fold sp13 into totale_passivo so the downstream debt/equity
    validators derive the correct aggregates instead of cannibalising the reserves
    (budget_188 diff 133.744=utile; budget_249 diff 56.999=utile; budget_338 diff
    80.228≈utile; budget_213 perdita 90.819).
    """
    tot_attivo = balance_sheet_data.get('totale_attivo', Decimal('0'))
    tot_passivo = balance_sheet_data.get('totale_passivo', Decimal('0'))
    sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))

    if tot_attivo == 0 or tot_passivo == 0 or sp13 == 0:
        return balance_sheet_data

    gap = tot_attivo - tot_passivo
    # gap must match the result (same sign and magnitude) within a small tolerance.
    # Use a relative tolerance too, to absorb rounding on large statements.
    tol = max(Decimal('1'), abs(tot_attivo) * Decimal('0.0005'))
    if abs(gap - sp13) <= tol and abs(gap) > Decimal('1'):
        new_passivo = tot_passivo + sp13
        logger.warning(
            f"[{label}] Totale Passivo appears NET of result: "
            f"totale_attivo={tot_attivo}, totale_passivo={tot_passivo}, "
            f"gap={gap} ≈ utile(sp13)={sp13}. Folding result into totale_passivo "
            f"({tot_passivo} -> {new_passivo})."
        )
        balance_sheet_data['totale_passivo'] = new_passivo

    return balance_sheet_data


def _fit_breakdown_to_aggregate(balance_sheet_data: Dict[str, Decimal], aggregate: str,
                                groups: list, altri_key: str, label: str) -> None:
    """Reconcile a balance-relevant aggregate (sp06/sp07/sp16/sp17) DOWN to its typed
    sub-items when those sub-items overshoot it.

    The aggregate is anchored to the declared totals (totale_attivo / totale_debiti) and
    is what feeds the balance check, so it must NOT be inflated to a double-counted
    breakdown sum (that masks an asset/liability over-count and breaks the balance — see
    budget_208). Instead keep the aggregate fixed, zero the "altri" plug, and scale the
    remaining typed sub-items proportionally so they sum back to the aggregate. The detail
    is only a Rettifiche starting point; the aggregate stays correct.
    """
    total = balance_sheet_data.get(aggregate, Decimal('0'))
    others = [g for g in groups if g != altri_key]
    others_sum = sum(balance_sheet_data.get(g, Decimal('0')) for g in others)
    balance_sheet_data[altri_key] = Decimal('0')
    if others_sum > 0 and total > 0:
        scale = total / others_sum
        for g in others:
            balance_sheet_data[g] = balance_sheet_data.get(g, Decimal('0')) * scale
    elif total <= 0:
        for g in others:
            balance_sheet_data[g] = Decimal('0')
    _flag_unbalanced(
        label,
        f"breakdown {aggregate}: typed sub-items ({others_sum}) overshoot aggregate "
        f"({total}); kept aggregate and scaled sub-items down (no asset/liability inflation)",
        others_sum - total,
    )


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
    cap = _plug_cap(balance_sheet_data)

    def _apply_sp06(new_sp06: Decimal, kind: str) -> None:
        """Apply the sp06 plug only if it passes the anti-masking guards
        (non-negative result + magnitude under cap); otherwise flag the imbalance."""
        change = abs(new_sp06 - sp06)
        if new_sp06 < 0:
            _flag_unbalanced(label, f"crediti {kind}: refusing sp06 plug -> {new_sp06} (negative)", diff)
            return
        if change > cap:
            _flag_unbalanced(
                label,
                f"crediti {kind}: sp06 plug {sp06} -> {new_sp06} exceeds cap {cap}; not applied",
                diff,
            )
            return
        logger.warning(
            f"[{label}] Crediti {kind}: sp06+sp07={actual_crediti} but expected={expected_crediti} "
            f"(diff={diff}). Correcting sp06 from {sp06} to {new_sp06}"
        )
        balance_sheet_data['sp06_crediti_breve'] = new_sp06

    if diff > Decimal('1') and sp07 > 0 and abs(diff - sp07) <= Decimal('1'):
        # Classic double-count: LLM put total crediti in sp06, then also added sp07
        _apply_sp06(expected_crediti - sp07, "double-count")
    elif diff > Decimal('1'):
        # General overshoot — correct sp06
        _apply_sp06(expected_crediti - sp07, "overshoot")
    elif diff < Decimal('-1'):
        # Undershoot — LLM likely missed "imposte anticipate" or other crediti items
        _apply_sp06(expected_crediti - sp07, "undershoot (likely imposte anticipate)")

    # Reconcile debtor-type breakdown against the aggregates.
    # Residual (aggregate − sum of a..g) plugs into the "altri" bucket (g), so
    # sum of detail always matches sp06_crediti_breve / sp07_crediti_lungo and
    # the Rettifiche journal has a meaningful starting point.
    _CREDIT_BREVE_GROUPS = ['sp06a_crediti_clienti_breve', 'sp06b_crediti_controllate_breve',
                            'sp06c_crediti_collegate_breve', 'sp06d_crediti_controllanti_breve',
                            'sp06e_crediti_tributari_breve', 'sp06f_imposte_anticipate_breve',
                            'sp06g_crediti_altri_breve']
    _CREDIT_LUNGO_GROUPS = ['sp07a_crediti_clienti_lungo', 'sp07b_crediti_controllate_lungo',
                            'sp07c_crediti_collegate_lungo', 'sp07d_crediti_controllanti_lungo',
                            'sp07e_crediti_tributari_lungo', 'sp07f_imposte_anticipate_lungo',
                            'sp07g_crediti_altri_lungo']
    for aggregate, groups, altri_key in (
        ('sp06_crediti_breve', _CREDIT_BREVE_GROUPS, 'sp06g_crediti_altri_breve'),
        ('sp07_crediti_lungo', _CREDIT_LUNGO_GROUPS, 'sp07g_crediti_altri_lungo'),
    ):
        total = balance_sheet_data.get(aggregate, Decimal('0'))
        breakdown_sum = sum(balance_sheet_data.get(g, Decimal('0')) for g in groups)
        residual = total - breakdown_sum
        if abs(residual) > Decimal('1'):
            current_altri = balance_sheet_data.get(altri_key, Decimal('0'))
            new_altri = current_altri + residual
            # Anti-masking guard: never let the "altri" bucket go negative. A negative
            # residual means the typed sub-totals exceed the aggregate; lift the
            # aggregate to the breakdown sum instead of fabricating a negative credit.
            if new_altri < 0:
                # Sub-items overshoot the aggregate: keep the (declared-total-anchored)
                # aggregate and scale the breakdown down — never inflate assets.
                _fit_breakdown_to_aggregate(balance_sheet_data, aggregate, groups, altri_key, label)
            else:
                logger.info(
                    f"[{label}] Credit breakdown residual for {aggregate}: "
                    f"aggregate={total}, breakdown_sum={breakdown_sum}, plugging {residual} into {altri_key}"
                )
                balance_sheet_data[altri_key] = new_altri

    return balance_sheet_data


def _validate_debiti(balance_sheet_data: Dict[str, Decimal], label: str) -> Dict[str, Decimal]:
    """Validate and auto-correct debt split: sp16 + sp17 must equal total debiti.

    Uses the explicit `totale_debiti` field from the PDF when present (most reliable).
    Falls back to inference from totale_passivo - (patrimonio_netto + fondi + tfr + ratei)
    when the explicit value is missing.
    """
    sp16 = balance_sheet_data.get('sp16_debiti_breve', Decimal('0'))
    sp17 = balance_sheet_data.get('sp17_debiti_lungo', Decimal('0'))
    explicit_total = balance_sheet_data.get('totale_debiti', Decimal('0'))

    if explicit_total > 0:
        total_debiti = explicit_total
        source = "explicit"
    else:
        tot_passivo = balance_sheet_data.get('totale_passivo', Decimal('0'))
        if tot_passivo == 0:
            return balance_sheet_data
        sp11 = balance_sheet_data.get('sp11_capitale', Decimal('0'))
        sp12 = balance_sheet_data.get('sp12_riserve', Decimal('0'))
        sp13 = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
        sp14 = balance_sheet_data.get('sp14_fondi_rischi', Decimal('0'))
        sp15 = balance_sheet_data.get('sp15_tfr', Decimal('0'))
        sp18 = balance_sheet_data.get('sp18_ratei_risconti_passivi', Decimal('0'))
        total_debiti = tot_passivo - (sp11 + sp12 + sp13) - sp14 - sp15 - sp18
        source = "inferred"

    debt_sum = sp16 + sp17
    diff = abs(debt_sum - total_debiti)
    cap = _plug_cap(balance_sheet_data)

    if diff > Decimal('1') and total_debiti > 0:
        new_sp16 = total_debiti - sp17
        if new_sp16 >= 0:
            # Cap guard: a sp16 plug larger than 5% of total assets is almost
            # certainly a structural error (e.g. inferred total_debiti was wrong
            # because totale_passivo was net of the result). Flag instead of mask.
            if source == "inferred" and abs(new_sp16 - sp16) > cap:
                _flag_unbalanced(
                    label,
                    f"debiti (inferred): sp16 plug {sp16} -> {new_sp16} exceeds cap {cap}; not applied",
                    diff,
                )
            else:
                logger.warning(
                    f"[{label}] Debt mismatch ({source}): sp16+sp17={debt_sum} but total debiti={total_debiti} "
                    f"(diff={diff}). Correcting sp16 from {sp16} to {new_sp16}"
                )
                balance_sheet_data['sp16_debiti_breve'] = new_sp16
        else:
            # sp17 exceeds total debiti — correct sp17 instead
            logger.warning(
                f"[{label}] Debt mismatch ({source}): sp17={sp17} > total debiti={total_debiti}. "
                f"Correcting sp17 to {total_debiti} and sp16 to 0"
            )
            balance_sheet_data['sp17_debiti_lungo'] = total_debiti
            balance_sheet_data['sp16_debiti_breve'] = Decimal('0')

    # Reconcile creditor-type breakdown against the aggregates.
    # Any residual (aggregate − sum of a..g) is plugged into the "altri" bucket (g)
    # so the Rettifiche journal always has a meaningful starting point and sums
    # back to sp16_debiti_breve / sp17_debiti_lungo.
    _DEBT_BREVE_GROUPS = ['sp16a_debiti_banche_breve', 'sp16b_debiti_altri_finanz_breve',
                          'sp16c_debiti_obbligazioni_breve', 'sp16d_debiti_fornitori_breve',
                          'sp16e_debiti_tributari_breve', 'sp16f_debiti_previdenza_breve',
                          'sp16g_altri_debiti_breve']
    _DEBT_LUNGO_GROUPS = ['sp17a_debiti_banche_lungo', 'sp17b_debiti_altri_finanz_lungo',
                          'sp17c_debiti_obbligazioni_lungo', 'sp17d_debiti_fornitori_lungo',
                          'sp17e_debiti_tributari_lungo', 'sp17f_debiti_previdenza_lungo',
                          'sp17g_altri_debiti_lungo']
    for aggregate, groups, altri_key in (
        ('sp16_debiti_breve', _DEBT_BREVE_GROUPS, 'sp16g_altri_debiti_breve'),
        ('sp17_debiti_lungo', _DEBT_LUNGO_GROUPS, 'sp17g_altri_debiti_lungo'),
    ):
        total = balance_sheet_data.get(aggregate, Decimal('0'))
        breakdown_sum = sum(balance_sheet_data.get(g, Decimal('0')) for g in groups)
        residual = total - breakdown_sum
        if abs(residual) > Decimal('1'):
            current_altri = balance_sheet_data.get(altri_key, Decimal('0'))
            new_altri = current_altri + residual
            # Anti-masking guard: never let the "altri" bucket go negative. A negative
            # residual means the LLM's typed sub-totals already EXCEED the aggregate
            # (the breakdown, not the bucket, is wrong) — plugging it would produce an
            # impossible negative debt (budget_213/249 sp16g/sp17g went negative).
            # In that case lift the aggregate to the breakdown sum instead and flag.
            if new_altri < 0:
                # Sub-items overshoot the aggregate: keep the (declared-total-anchored)
                # aggregate and scale the breakdown down — never inflate liabilities.
                _fit_breakdown_to_aggregate(balance_sheet_data, aggregate, groups, altri_key, label)
            else:
                logger.info(
                    f"[{label}] Debt breakdown residual for {aggregate}: "
                    f"aggregate={total}, breakdown_sum={breakdown_sum}, plugging {residual} into {altri_key}"
                )
                balance_sheet_data[altri_key] = new_altri

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
        new_sp12 = expected_equity - sp11 - sp13
        change = abs(new_sp12 - sp12)
        # Anti-masking guards on the reserves tap:
        #  * never let reserves go negative (impossible total reserves);
        #  * never absorb an EGREGIOUS discrepancy into reserves — that signals the
        #    imbalance is structural (wrong debiti, totale_passivo net of the result,
        #    missing liabilities) and must surface rather than hide in sp12
        #    (budget_158/238 inflated reserves by >1 mln).
        # The equity cap is intentionally LOOSER than the crediti/debiti cap: moderate
        # reserve corrections on small companies are legitimate (a €40k plug on a €350k
        # statement is normal rounding/sub-item absorption — budget_275). We only reject
        # plugs that are BOTH a large fraction of assets AND large in absolute terms.
        equity_cap = max(_plug_cap(balance_sheet_data) * Decimal('3'), Decimal('150000'))

        # Balance-validated override: when BOTH declared totals are present and equal AND the
        # asset side already reconstructs totale_attivo, the imbalance lives ENTIRELY in the
        # equity composition — the LLM mis-extracted reserves (common with NEGATIVE equity:
        # budget_297 prior 2024 had PN −75.414, riserve extracted as 1.152.513 vs the 152.023
        # that makes both sides reconcile). The corrected sp12 then makes the whole statement
        # tie out to the declared totals, so it is a legitimate fix, not masking — apply it even
        # past the cap. Structural imbalances (asset side NOT reconstructing the total, or the
        # two declared totals disagreeing) do not qualify and still surface.
        tot_attivo = balance_sheet_data.get('totale_attivo', Decimal('0'))
        _ATT_KEYS = ['sp01_crediti_soci', 'sp02_immob_immateriali', 'sp03_immob_materiali',
                     'sp04_immob_finanziarie', 'sp05_rimanenze', 'sp06_crediti_breve',
                     'sp07_crediti_lungo', 'sp08_attivita_finanziarie',
                     'sp09_disponibilita_liquide', 'sp10_ratei_risconti_attivi']
        att_sum = sum(balance_sheet_data.get(k, Decimal('0')) for k in _ATT_KEYS)
        balance_validated = (
            tot_passivo > 0 and tot_attivo > 0
            and abs(tot_attivo - tot_passivo) <= Decimal('1')
            and abs(att_sum - tot_attivo) <= Decimal('1')
            and new_sp12 >= 0
        )

        if new_sp12 < 0:
            _flag_unbalanced(
                label,
                f"equity: refusing sp12 plug {sp12} -> {new_sp12} (negative reserves)",
                equity_diff,
            )
        elif change > equity_cap and not balance_validated:
            _flag_unbalanced(
                label,
                f"equity: sp12 plug {sp12} -> {new_sp12} exceeds cap {equity_cap}; not applied "
                f"(structural imbalance, not a reserve error)",
                equity_diff,
            )
        else:
            extra = " [balance-validated: asset side ties to declared total]" if (
                change > equity_cap and balance_validated) else ""
            logger.warning(
                f"[{label}] Equity mismatch: sp11+sp12+sp13={computed_equity} but "
                f"totale_passivo-liabilities={expected_equity} (diff={equity_diff}). "
                f"Correcting sp12_riserve from {sp12} to {new_sp12}{extra}"
            )
            balance_sheet_data['sp12_riserve'] = new_sp12
    return balance_sheet_data


def _ce_risultato_ante(ce_data: Dict[str, Decimal]) -> Decimal:
    """Reconstruct 'Risultato prima delle imposte' from the CE fields.

    Mirrors the model convention: costs (incl. ce10) are stored positive and the
    whole COPRO block is subtracted from the Valore della Produzione.
    """
    vp = (
        ce_data.get('ce01_ricavi_vendite', Decimal('0'))
        + ce_data.get('ce02_variazioni_rimanenze', Decimal('0'))
        + ce_data.get('ce03_lavori_interni', Decimal('0'))
        + ce_data.get('ce04_altri_ricavi', Decimal('0'))
    )
    copro = (
        ce_data.get('ce05_materie_prime', Decimal('0'))
        + ce_data.get('ce06_servizi', Decimal('0'))
        + ce_data.get('ce07_godimento_beni', Decimal('0'))
        + ce_data.get('ce08_costi_personale', Decimal('0'))
        + ce_data.get('ce09_ammortamenti', Decimal('0'))
        + ce_data.get('ce10_var_rimanenze_mat_prime', Decimal('0'))
        + ce_data.get('ce11_accantonamenti', Decimal('0'))
        + ce_data.get('ce11b_altri_accantonamenti', Decimal('0'))
        + ce_data.get('ce12_oneri_diversi', Decimal('0'))
    )
    financial = (
        ce_data.get('ce13_proventi_partecipazioni', Decimal('0'))
        + ce_data.get('ce14_altri_proventi_finanziari', Decimal('0'))
        - ce_data.get('ce15_oneri_finanziari', Decimal('0'))
        + ce_data.get('ce16_utili_perdite_cambi', Decimal('0'))
        - ce_data.get('ce17_rettifiche_attivita_fin', Decimal('0'))
    )
    return vp - copro + financial


def _validate_ce10_against_bs(
    ce_data: Dict[str, Decimal],
    bs_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Reconcile ce10 (variazioni rimanenze materie prime) against the BS utile anchor.

    item 11 is a VARIATION, not a pure cost: a cost when inventory falls (positive in
    the model), a CREDIT when inventory rises (negative). The LLM mis-handles it in two
    recurring ways that throw the whole CE off while the balance-sheet utile (sp13) —
    independently pinned by a balancing BS — stays correct:

      * WRONG SIGN (convention): the residual gap equals -2*ce10 → flip the sign.
        (e.g. ALMA budget_271: +7.831 credit stored as a cost → CE off by 2*7.831.)
      * SPURIOUS VALUE (mis-attributed prior-year/blank column): the residual gap
        equals -ce10 → the current-year item 11 is really 0 and the LLM grabbed an
        adjacent column. (e.g. ELLE ERRE budget_144/328: item 11 prints "(300.567)"
        in the prior column; the PDF's own "Totale costi"/"A-B" totals imply ce10=0,
        and the booked utile only reconciles at ce10=0.)

    Both are exact-coincidence detectors (tol €2), so an unrelated extraction error
    never triggers a spurious correction, and they are mutually exclusive for ce10≠0.
    Gated on a BALANCING BS so sp13 is a trustworthy anchor.
    """
    ce10 = ce_data.get('ce10_var_rimanenze_mat_prime', Decimal('0'))
    sp13 = bs_data.get('sp13_utile_perdita', Decimal('0'))
    if ce10 == 0 or sp13 == 0:
        return ce_data

    # sp13 is only a reliable anchor when the BS actually balances.
    tot_att = bs_data.get('totale_attivo', Decimal('0'))
    tot_pas = bs_data.get('totale_passivo', Decimal('0'))
    if tot_att == 0 or abs(tot_att - tot_pas) > Decimal('2'):
        return ce_data

    utile_ce = _ce_risultato_ante(ce_data) - ce_data.get('ce20_imposte', Decimal('0'))
    gap = utile_ce - sp13
    tol = Decimal('2')  # whole-euro reports; allow minor rounding
    if abs(gap) <= tol:
        return ce_data

    # Flipping ce10 shifts COPRO by -2*ce10 (utile_ce by +2*ce10); zeroing it shifts
    # COPRO by +ce10 (utile_ce by -ce10).
    if abs(gap + 2 * ce10) <= tol:
        ce_data['ce10_var_rimanenze_mat_prime'] = -ce10
        logger.warning(
            f"[{label}] ce10 sign correction: {ce10} -> {-ce10} reconciles CE utile "
            f"({utile_ce}) with BS sp13 ({sp13}); residual gap was {gap}."
        )
    elif abs(gap + ce10) <= tol:
        ce_data['ce10_var_rimanenze_mat_prime'] = Decimal('0')
        logger.warning(
            f"[{label}] ce10 spurious-value correction: {ce10} -> 0 reconciles CE utile "
            f"({utile_ce}) with BS sp13 ({sp13}); residual gap was {gap} "
            f"(likely a mis-attributed prior-year column)."
        )
    return ce_data


def _validate_ce_imposte(
    ce_data: Dict[str, Decimal],
    bs_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Cross-check ce20_imposte against BS utile and CE risultato ante imposte.

    In multi-column PDFs (e.g. "Stampa dettaglio voci"), when a year has zero
    imposte the LLM may pick up the other year's value.  Fix by computing:
      expected_imposte = risultato_ante_imposte - utile_from_BS
    """
    sp13 = bs_data.get('sp13_utile_perdita', Decimal('0'))
    # Compute risultato ante imposte from CE fields
    risultato_ante = _ce_risultato_ante(ce_data)
    expected_imposte = risultato_ante - sp13

    ce20 = ce_data.get('ce20_imposte', Decimal('0'))
    diff = abs(ce20 - expected_imposte)

    # Only overwrite the extracted imposte when we are confident the LLM picked up
    # the WRONG value (typically the other year's column on multi-year layouts).
    # Guards against the failure mode where a miscomputed VdP (e.g. ce03 lavori
    # interni excluded) produces a bogus expected_imposte that clobbers a correctly
    # extracted ce20 (budget_256 GHEDA: real 117.892 was being forced to 28.421).
    #
    # Preconditions for a correction:
    #   - sp13 must be a real BS anchor (non-zero); without it expected_imposte is
    #     meaningless and we must not touch the extracted value.
    #   - expected_imposte must be non-negative (negative => our CE reconstruction
    #     is off, not the imposte) and smaller in magnitude than the extracted ce20
    #     (the classic "wrong column was larger" case).
    #   - the extracted ce20 must NOT already reconcile the BS utile: if
    #     |risultato_ante - ce20 - sp13| <= 1 then PBT - imposte == utile_BS already,
    #     so the extracted imposte is internally consistent and must be kept.
    reconciles_bs = abs(risultato_ante - ce20 - sp13) <= Decimal('1')

    # Case 0 — imposte line entirely MISSING. The LLM sometimes drops the
    # "20) Imposte sul reddito" value (returns ce20≈0) on layouts where the line is
    # present but visually detached from its amount. The BS utile anchor then implies
    # a real positive tax (PBT > utile_BS). Fill it in so the CE bottom line reconciles
    # to sp13. Tightly guarded so a correctly-extracted imposte is never touched:
    #   - ce20 must be ~0 (nothing to clobber — distinct from the GHEDA "wrong column"
    #     case where ce20 is a real non-zero value handled below);
    #   - PBT (risultato_ante) must be positive and the implied tax a plausible
    #     fraction of it (0 < imposte < PBT), i.e. not a tax credit nor larger than
    #     the pre-tax profit (which would mean the gap is some other CE error, e.g.
    #     a fabricated cost like budget_328's ce10 — left untouched on purpose).
    if (
        diff > Decimal('1')
        and sp13 != 0
        and abs(ce20) <= Decimal('1')
        and risultato_ante > 0
        and Decimal('0') < expected_imposte < risultato_ante
        and not reconciles_bs
    ):
        logger.warning(
            f"[{label}] ce20_imposte missing (extracted={ce20}); filling from BS anchor: "
            f"risultato_ante {risultato_ante} - utile_BS {sp13} = {expected_imposte}."
        )
        ce_data['ce20_imposte'] = expected_imposte
        return ce_data

    if (
        diff > Decimal('1')
        and sp13 != 0
        and expected_imposte >= 0
        and abs(expected_imposte) < abs(ce20) + Decimal('1')
        and not reconciles_bs
    ):
        logger.warning(
            f"[{label}] ce20_imposte cross-check: extracted={ce20}, "
            f"expected (risultato_ante {risultato_ante} - utile_BS {sp13})={expected_imposte}. "
            f"Correcting."
        )
        ce_data['ce20_imposte'] = max(expected_imposte, Decimal('0'))
    elif diff > Decimal('1'):
        logger.info(
            f"[{label}] ce20_imposte cross-check skipped (extracted={ce20}, "
            f"expected={expected_imposte}, sp13={sp13}, reconciles_bs={reconciles_bs}): "
            f"keeping extracted value."
        )

    return ce_data


def _prior_column_is_absent(
    current_bs: Dict[str, Decimal],
    current_ce: Dict[str, Decimal],
    prior_bs: Dict[str, Decimal],
    prior_ce: Dict[str, Decimal],
) -> bool:
    """Detect a MONOCOLUMN (single-year) PDF where the LLM fabricated a prior year.

    On a one-column statement there is no prior column to read, so the model tends to
    either (a) clone the current values into prior, or (b) leave prior almost empty
    apart from an orphan figure it carried over. Both produce a bogus prior year that
    the downstream "prior all zeros" guard in pdf_importer does NOT catch (because the
    clone isn't zero). We detect the physical absence here and let the caller drop it.

    Heuristics (any one is sufficient):
      * Prior balance-sheet aggregates are a near-exact clone of current (same totale
        attivo + same key items) AND prior CE has no revenue — i.e. the BS was copied
        but there was never a second CE column. Clone of a real two-year statement
        would have *different* totals, so equality is the tell.
      * Prior has no meaningful activity at all (no totale_attivo and no CE revenue)
        beyond a stray orphan value.
    """
    def _g(d: Dict[str, Decimal], k: str) -> Decimal:
        return d.get(k, Decimal('0'))

    cur_attivo = _g(current_bs, 'totale_attivo')
    pri_attivo = _g(prior_bs, 'totale_attivo')
    cur_ricavi = _g(current_ce, 'ce01_ricavi_vendite')
    pri_ricavi = _g(prior_ce, 'ce01_ricavi_vendite')

    # Key BS items to compare for clone detection
    _KEY_BS = ['totale_attivo', 'totale_passivo', 'sp03_immob_materiali',
               'sp06_crediti_breve', 'sp09_disponibilita_liquide',
               'sp11_capitale', 'sp16_debiti_breve']

    def _near(a: Decimal, b: Decimal) -> bool:
        if a == 0 and b == 0:
            return True
        scale = max(abs(a), abs(b), Decimal('1'))
        return abs(a - b) <= scale * Decimal('0.001')

    bs_is_clone = (
        cur_attivo != 0
        and all(_near(_g(current_bs, k), _g(prior_bs, k)) for k in _KEY_BS)
    )

    # Prior CE essentially empty (no revenue) while current has revenue
    prior_ce_empty = (pri_ricavi == 0 and cur_ricavi != 0)

    if bs_is_clone and prior_ce_empty:
        return True

    # Prior has no real substance at all (everything zero apart from possible orphan)
    prior_no_activity = (pri_attivo == 0 and pri_ricavi == 0)
    current_has_activity = (cur_attivo != 0 or cur_ricavi != 0)
    if prior_no_activity and current_has_activity:
        return True

    return False


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

    # Step 1: Check if PDF is image-based (no extractable text)
    use_vision = _is_image_pdf(file_path)

    if use_vision:
        logger.info("Image-based PDF detected, using vision extraction (both years)")
        all_images = _render_pdf_pages_as_images(file_path)

        # Step 2v: Extract balance sheet (both years) via vision
        try:
            sp_result = _extract_with_llm_vision(
                client, all_images, SP_BOTH_YEARS_SYSTEM_PROMPT,
                TwoYearBalanceSheetExtraction, "Stato Patrimoniale (both years)",
                tool_name="balance_sheet_both_years",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during SP vision extraction: {e}")

        # Step 3v: Extract income statement (both years) via vision
        try:
            ce_result = _extract_with_llm_vision(
                client, all_images, CE_BOTH_YEARS_SYSTEM_PROMPT,
                TwoYearIncomeStatementExtraction, "Conto Economico (both years)",
                tool_name="income_statement_both_years",
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during CE vision extraction: {e}")
    else:
        # Step 1b: Extract relevant page text with PyMuPDF
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

    # Step 4b: Drop a fabricated prior year on MONOCOLUMN PDFs. When the source has a
    # single value column, the LLM clones current into prior (or leaves an orphan), and
    # the downstream "prior all zeros" guard can't catch a non-zero clone. Returning
    # empty prior dicts here signals the importer to skip the prior year entirely
    # (budget_315 BERTELLI provvisorio: prior was a clone of 2025 with CE all-zero and
    # an orphan sp13).
    if _prior_column_is_absent(current_bs, current_ce, prior_bs, prior_ce):
        logger.warning(
            "Prior-year column appears ABSENT (monocolumn PDF / fabricated prior): "
            "discarding prior_bs and prior_ce."
        )
        return current_bs, current_ce, {}, {}

    # Step 5: Fold the result into totale_passivo when the layout reports it net of
    # the year's result (sezioni contrapposte / dettaglio voci); then validate crediti;
    # then debiti (using explicit totale_debiti when present); then equity (which uses
    # the corrected debt aggregate to derive expected equity).
    current_bs = _reconcile_utile_in_passivo(current_bs, "current")
    prior_bs = _reconcile_utile_in_passivo(prior_bs, "prior")
    current_bs = _validate_crediti(current_bs, "current")
    prior_bs = _validate_crediti(prior_bs, "prior")
    current_bs = _validate_debiti(current_bs, "current")
    prior_bs = _validate_debiti(prior_bs, "prior")
    current_bs = _validate_equity(current_bs, "current")
    prior_bs = _validate_equity(prior_bs, "prior")

    # Step 6: Reconcile ce10 sign on the BS utile anchor, then cross-check ce20_imposte
    current_ce = _validate_ce10_against_bs(current_ce, current_bs, "current")
    prior_ce = _validate_ce10_against_bs(prior_ce, prior_bs, "prior")
    current_ce = _validate_ce_imposte(current_ce, current_bs, "current")
    prior_ce = _validate_ce_imposte(prior_ce, prior_bs, "prior")

    return current_bs, current_ce, prior_bs, prior_ce
