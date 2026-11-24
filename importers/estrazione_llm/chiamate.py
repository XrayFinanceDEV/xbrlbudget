"""Prompt IV-CEE, chiamate al modello (testo e vision), PDF a immagini e testo illeggibile.

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import anthropic
import base64
import fitz
import logging
import pydantic
import re
import time
from config import PDF_LLM_MAX_TOKENS, PDF_LLM_MODEL
from typing import List, Optional, Set
from importers import llm_provider
from importers.estrazione_llm.modelli import (
    PDFImportError,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


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
- ONLY the C.II) Crediti of "Attivo circolante" go here. NEVER include B.III.2 "Crediti" (immobilized
  financial receivables): those belong to sp04_immob_finanziarie. Counting a B.III.2 credito here too
  double-counts it (it is already inside Immobilizzazioni) and unbalances the sheet by that amount.
- sp06_crediti_breve = SUM of ALL "esigibili entro l'esercizio successivo" amounts across the C.II crediti categories (verso clienti, tributari, verso altri, etc.)
  PLUS "imposte anticipate" (deferred tax assets) if shown as a separate line within C.II crediti
- sp07_crediti_lungo = SUM of ALL "esigibili oltre l'esercizio successivo" amounts across the C.II crediti categories (Attivo circolante only)
- CRITICAL: sp06 + sp07 MUST equal "Totale crediti" of C.II (Attivo circolante). If they don't, add the difference to sp06.
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
- If the PDF shows only "Totale crediti" without a breakdown, put everything in sp06a_crediti_clienti_breve (or sp07g_crediti_altri_lungo for long-term) to match the aggregate — do NOT invent sub-totals.
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
- ONLY the C.II) Crediti of "Attivo circolante" go here. NEVER include B.III.2 "Crediti" (immobilized
  financial receivables): those belong to sp04_immob_finanziarie. Counting a B.III.2 credito here too
  double-counts it (it is already inside Immobilizzazioni) and unbalances the sheet by that amount.
- sp06_crediti_breve = SUM of ALL "esigibili entro l'esercizio successivo" amounts across the C.II crediti categories (verso clienti, tributari, verso altri, etc.)
  PLUS "imposte anticipate" (deferred tax assets) if shown as a separate line within C.II crediti
- sp07_crediti_lungo = SUM of ALL "esigibili oltre l'esercizio successivo" amounts across the C.II crediti categories (Attivo circolante only)
- CRITICAL: sp06 + sp07 MUST equal "Totale crediti" of C.II (Attivo circolante). If they don't, add the difference to sp06.
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
- If the PDF shows only "Totale crediti" without a breakdown, put everything in sp06a_crediti_clienti_breve (or sp07g_crediti_altri_lungo for long-term) to match the aggregate — do NOT invent sub-totals.
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
    provider: str = "anthropic",
) -> pydantic.BaseModel:
    """Call Claude Haiku with tool-use for structured extraction.

    provider="gx10": stessa estrazione su Qwen locale (importers/llm_provider.py), con lo
    schema del modello come vincolo di decodifica; `client` e' ignorato. Il messaggio utente
    e' lo stesso del ramo Anthropic, meno il riferimento al tool, che su vLLM non esiste.
    """
    if provider == "gx10":
        logger.info(f"Calling gx10 for {section_name} extraction ({len(text)} chars)...")
        return llm_provider.chiama_gx10_strutturato(
            system_prompt,
            f"Extract the {section_name} values from this Italian balance sheet text.\n\n{text}",
            output_model, max_tokens=PDF_LLM_MAX_TOKENS)
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

def _text_layer_is_garbled(text: str) -> bool:
    """Detect a CORRUPTED (not merely absent) text layer — broken ToUnicode font maps.

    Signature: the printed glyphs are fine but the extracted text splits amounts
    around the decimal comma ("3.239 , 12", "315.121, 19") and garbles letters
    ("roNDO AMM.TO", "IMMOBILIZZAZIONI IIa(ATERIALI" — budget_337). Feeding that
    text to the LLM yields stochastic garbage; the images are clean, so such a file
    must take the VISION path like a scan.

    Calibrated on the full corpus (2026-07-15): budget_337 scores 60.7% broken
    amounts, every other file < 5% — threshold 30% with a >= 10 absolute floor so
    a couple of odd lines on a clean file can never trigger it.
    """
    if not text:
        return False
    broken = len(re.findall(r'\d\s+,\s*\d{2}\b', text))
    if broken < 10:
        return False
    wellformed = len(re.findall(r'\d,\d{2}\b', text))
    total = broken + wellformed
    return total > 0 and (broken / total) > 0.30

def ocr_pdf_sample_text(file_path: str, max_pages: int = 6) -> str:
    """OCR the first pages of a scanned (image-only) PDF into plain text.

    Scanned bilanci carry NO extractable text, so `bilancio_classifier.classify_bilancio`
    (which works on text markers) sees an empty string and routes the file to
    ROUTE_UNSUPPORTED — even though the route-C / IV-CEE extractors are already vision
    capable. This helper renders the first pages and asks Claude to transcribe them to
    plain text, so the SAME text-based router can decide the macro-area/route for a scan.

    It deliberately returns FREE TEXT (no tool schema): we only need routing markers
    ("BILANCIO DI VERIFICA", "STATO PATRIMONIALE", account codes, ...), not structured
    values — the chosen extractor re-reads the images itself for the real figures.

    Requires ANTHROPIC_API_KEY. Returns "" on any failure (caller decides how to surface).
    """
    api_key = llm_provider.chiave_anthropic()
    if not api_key:
        return ""
    try:
        client = anthropic.Anthropic(api_key=api_key)
        pages = set(range(max_pages))
        images = _render_pdf_pages_as_images(file_path, pages=pages, dpi=200)
        if not images:
            return ""
        content: List[dict] = []
        for img_b64 in images:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
            })
        content.append({
            "type": "text",
            "text": (
                "Trascrivi FEDELMENTE tutto il testo visibile in queste pagine di un "
                "documento contabile italiano scansionato. Mantieni intestazioni, nomi "
                "delle voci, codici conto e numeri cosi' come appaiono, riga per riga. "
                "Non interpretare, non riassumere, non aggiungere commenti: solo il testo "
                "grezzo (plain text)."
            ),
        })
        response = client.messages.create(
            model=PDF_LLM_MODEL,
            max_tokens=PDF_LLM_MAX_TOKENS,
            messages=[{"role": "user", "content": content}],
        )
        parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        ocr_text = "\n".join(parts).strip()
        logger.info(f"OCR routing pass: recovered {len(ocr_text)} chars from {len(images)} scanned pages")
        return ocr_text
    except Exception as e:
        logger.warning(f"OCR routing pass failed ({type(e).__name__}: {e})")
        return ""
