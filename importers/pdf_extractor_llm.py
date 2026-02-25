"""
PDF Balance Sheet Extractor using PyMuPDF + Claude Haiku 4.5.

Fast alternative to Docling: PyMuPDF extracts text from relevant pages (~100ms),
then Claude Haiku parses IV CEE fields via structured output (~3-5s).
Total: ~5s at ~$0.01/PDF vs Docling's ~133s.
"""

import json
import os
import logging
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
CE_FALLBACK_KEYWORDS = ["totale valore della produzione", "differenza tra valore e costi"]


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

    # Scan all pages and cache lowercased text
    page_texts = []
    for page_num in range(total_pages):
        page_texts.append(doc[page_num].get_text().lower())
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
    # CE start: search after SP start to avoid re-matching the SP header page
    ce_after = (sp_start + 1) if sp_start is not None else 0
    ce_start = _find_start(CE_START_KEYWORDS, after_page=ce_after)
    # If CE start not found after SP, try from the beginning (SP may not exist)
    if ce_start is None and ce_after > 0:
        ce_start = _find_start(CE_START_KEYWORDS)

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
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF (e.g., losses, negative reserves)
- Crediti "esigibili entro l'esercizio successivo" go to sp06_crediti_breve
- Crediti "esigibili oltre l'esercizio successivo" go to sp07_crediti_lungo
- If crediti are not split by maturity, put the total in sp06_crediti_breve
- Debiti "esigibili entro l'esercizio successivo" go to sp16_debiti_breve
- Debiti "esigibili oltre l'esercizio successivo" go to sp17_debiti_lungo
- If debiti are not split by maturity, put the total in sp16_debiti_breve
- sp11_capitale is ONLY "I - Capitale" (share capital). Do NOT include it in sp12_riserve
- sp12_riserve = sum of ONLY items II through VIII: sovrapprezzo azioni (II), riserve di rivalutazione (III), riserva legale (IV), riserve statutarie (V), altre riserve (VI), riserva per operazioni di copertura (VII), utili (perdite) portati a nuovo (VIII), riserva negativa azioni proprie
- IMPORTANT: Verify that sp11_capitale + sp12_riserve + sp13_utile_perdita = "Totale patrimonio netto"
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
- Dash or empty = 0
- Return plain numbers without any formatting (no dots, no commas)
- All values in full euros (not thousands)

EXTRACTION RULES:
- Extract values EXACTLY as they appear: parentheses = negative, plain numbers = positive
- Do NOT flip signs - preserve the original sign from the PDF (e.g., losses, negative reserves)
- Crediti "esigibili entro l'esercizio successivo" go to sp06_crediti_breve
- Crediti "esigibili oltre l'esercizio successivo" go to sp07_crediti_lungo
- If crediti are not split by maturity, put the total in sp06_crediti_breve
- Debiti "esigibili entro l'esercizio successivo" go to sp16_debiti_breve
- Debiti "esigibili oltre l'esercizio successivo" go to sp17_debiti_lungo
- If debiti are not split by maturity, put the total in sp16_debiti_breve
- sp11_capitale is ONLY "I - Capitale" (share capital). Do NOT include it in sp12_riserve
- sp12_riserve = sum of ONLY items II through VIII: sovrapprezzo azioni (II), riserve di rivalutazione (III), riserva legale (IV), riserve statutarie (V), altre riserve (VI), riserva per operazioni di copertura (VII), utili (perdite) portati a nuovo (VIII), riserva negativa azioni proprie
- IMPORTANT: Verify that sp11_capitale + sp12_riserve + sp13_utile_perdita = "Totale patrimonio netto"
- Extract totale_attivo and totale_passivo for validation
- totale_passivo = Totale patrimonio netto + fondi rischi + TFR + debiti + ratei passivi

Extract BOTH columns: current_year (left column) and prior_year (right column)."""

CE_SYSTEM_PROMPT = """You are an expert Italian accountant specializing in Bilancio IV CEE (Schema di Conto Economico art. 2425 Codice Civile).

Extract the Conto Economico (income statement) values from the text below.

NUMBER RULES:
- Italian format: dots are thousand separators, commas are decimal separators (1.234.567 = 1234567)
- Parentheses mean negative: (347.117) = -347117
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

    # Step 4: Convert to Decimal dicts
    balance_sheet_data = _model_to_decimal_dict(sp_result)
    income_data = _model_to_decimal_dict(ce_result)

    # Log key values for verification
    logger.info(f"SP totale_attivo = {balance_sheet_data.get('totale_attivo')}")
    logger.info(f"SP totale_passivo = {balance_sheet_data.get('totale_passivo')}")
    logger.info(f"CE ce01_ricavi_vendite = {income_data.get('ce01_ricavi_vendite')}")

    # Step 5: Validate equity consistency
    # sp11 + sp12 + sp13 should approximately equal totale_passivo - (sp14+sp15+sp16+sp17+sp18)
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
            f"Equity mismatch: sp11+sp12+sp13={computed_equity} but "
            f"totale_passivo-liabilities={expected_equity} (diff={equity_diff}). "
            f"Correcting sp12_riserve from {sp12} to {sp12 - equity_diff}"
        )
        # Auto-correct: adjust sp12_riserve to make equity match
        balance_sheet_data['sp12_riserve'] = expected_equity - sp11 - sp13

    return balance_sheet_data, income_data


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

    # Step 4: Convert to Decimal dicts
    current_bs = _model_to_decimal_dict(sp_result.current_year)
    prior_bs = _model_to_decimal_dict(sp_result.prior_year)
    current_ce = _model_to_decimal_dict(ce_result.current_year)
    prior_ce = _model_to_decimal_dict(ce_result.prior_year)

    # Log key values
    logger.info(f"[current] SP totale_attivo={current_bs.get('totale_attivo')}, CE ricavi={current_ce.get('ce01_ricavi_vendite')}")
    logger.info(f"[prior]   SP totale_attivo={prior_bs.get('totale_attivo')}, CE ricavi={prior_ce.get('ce01_ricavi_vendite')}")

    # Step 5: Validate equity consistency for both years
    current_bs = _validate_equity(current_bs, "current")
    prior_bs = _validate_equity(prior_bs, "prior")

    return current_bs, current_ce, prior_bs, prior_ce
