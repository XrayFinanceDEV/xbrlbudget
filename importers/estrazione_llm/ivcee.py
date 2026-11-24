"""Lo schema di legge letto dal modello, a un anno e a due.

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import anthropic
import fitz
import logging
from decimal import Decimal
from typing import Dict, Tuple
from importers import llm_provider
from importers.estrazione_llm.modelli import (
    BalanceSheetExtraction, IncomeStatementExtraction, PDFImportError, TwoYearBalanceSheetExtraction,
    TwoYearIncomeStatementExtraction,
)
from importers.estrazione_llm.pagine import (
    extract_relevant_pages,
)
from importers.estrazione_llm.celle_vuote import (
    _reconcile_blank_current_ce_cells, _reconcile_blank_current_sp_cells,
)
from importers.estrazione_llm.voci_stampate import (
    _recover_printed_fixed_asset_details, _recover_printed_sp_rows, _split_printed_debt_maturities,
)
from importers.estrazione_llm.chiamate import (
    CE_BOTH_YEARS_SYSTEM_PROMPT, CE_SYSTEM_PROMPT, SP_BOTH_YEARS_SYSTEM_PROMPT, SP_SYSTEM_PROMPT,
    _extract_with_llm, _extract_with_llm_vision, _is_image_pdf, _render_pdf_pages_as_images,
)
from importers.estrazione_llm.riconciliazioni import (
    _model_to_decimal_dict, _normalize_ce_signs, _reconcile_ce09_from_source_details,
    _reconcile_credit_aggregates_from_source, _reconcile_global_ce_thousand_scale,
    _reconcile_isolated_ce_cost_signs, _reconcile_personale_detail, _reconcile_pn_detail,
)
from importers.estrazione_llm.totali_dichiarati import (
    _declared_control_totals, _reconcile_utile_in_passivo,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


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

    # Step 1: Check if PDF is image-based (no extractable text). Vision has no
    # local provider (vincoli: "la vision resta su Anthropic"); the text branch
    # can run entirely on gx10 (PDF_LLM_PROVIDER_IVCEE=gx10) without ANTHROPIC_API_KEY.
    use_vision = _is_image_pdf(file_path)
    api_key = llm_provider.chiave_anthropic()
    client = None
    if use_vision or llm_provider.provider_ivcee() != "gx10":
        if not api_key:
            if use_vision:
                raise PDFImportError(
                    "PDF e' un'immagine: la vision richiede ANTHROPIC_API_KEY (nessun fornitore locale)."
                )
            raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")
        try:
            client = anthropic.Anthropic(api_key=api_key)
        except Exception as e:
            raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

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

        provider = llm_provider.provider_ivcee()

        # Step 2: Extract balance sheet via Claude Haiku (or gx10, see provider_ivcee)
        try:
            sp_result = _extract_with_llm(
                client, sp_text, SP_SYSTEM_PROMPT,
                BalanceSheetExtraction, "Stato Patrimoniale",
                tool_name="balance_sheet",
                provider=provider,
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during SP extraction: {e}")
        except llm_provider.LLMProviderError as e:
            raise PDFImportError(f"Errore gx10 durante l'estrazione SP: {e}")

        # Step 3: Extract income statement via Claude Haiku (or gx10, see provider_ivcee)
        try:
            ce_result = _extract_with_llm(
                client, ce_text, CE_SYSTEM_PROMPT,
                IncomeStatementExtraction, "Conto Economico",
                tool_name="income_statement",
                provider=provider,
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during CE extraction: {e}")
        except llm_provider.LLMProviderError as e:
            raise PDFImportError(f"Errore gx10 durante l'estrazione CE: {e}")

    # Step 4: Convert to Decimal dicts and normalize signs
    balance_sheet_data = _reconcile_credit_aggregates_from_source(
        _model_to_decimal_dict(sp_result), "single"
    )
    balance_sheet_data, _ = _reconcile_blank_current_sp_cells(
        file_path, balance_sheet_data
    )
    balance_sheet_data = _recover_printed_sp_rows(file_path, balance_sheet_data)
    balance_sheet_data = _split_printed_debt_maturities(
        file_path, balance_sheet_data
    )
    balance_sheet_data = _recover_printed_fixed_asset_details(
        file_path, balance_sheet_data
    )
    raw_income_data = _model_to_decimal_dict(ce_result)
    income_data = _normalize_ce_signs(dict(raw_income_data))
    income_data, _ = _reconcile_blank_current_ce_cells(file_path, income_data)

    # Log key values for verification
    logger.info(f"SP totale_attivo = {balance_sheet_data.get('totale_attivo')}")
    logger.info(f"SP totale_passivo = {balance_sheet_data.get('totale_passivo')}")
    logger.info(f"CE ce01_ricavi_vendite = {income_data.get('ce01_ricavi_vendite')}")

    # Step 5: ``totale_passivo`` is control metadata and can legitimately exclude
    # the year's result on this layout.  Do not infer crediti, debiti or reserves
    # from a balance gap: those values must remain tied to source rows.
    balance_sheet_data = _reconcile_utile_in_passivo(balance_sheet_data, "single")

    # Step 6: CE sign/column conflicts are validation errors.  Never flip ce10 or
    # derive taxes from sp13 solely to make the two statements agree.

    # Step 7: Deterministic detail-line fill for clean IV-CEE statements (text path only):
    # PN reserve sub-fields (recovers dropped NEGATIVE reserves → keeps cash correct) +
    # personnel salari/oneri split. No-op on layouts without the explicit legal lines.
    if not use_vision:
        balance_sheet_data = _reconcile_pn_detail(balance_sheet_data, sp_text, "single")
        income_data = _reconcile_personale_detail(income_data, ce_text, "single")
    income_data = _reconcile_global_ce_thousand_scale(
        income_data, balance_sheet_data, "single"
    )
    income_data = _reconcile_isolated_ce_cost_signs(
        income_data, raw_income_data, balance_sheet_data, "single"
    )
    income_data = _reconcile_ce09_from_source_details(
        income_data, balance_sheet_data, "single"
    )

    # Un estrattore dichiara SEMPRE le proprie chiavi diagnostiche, anche a zero:
    # a valle una chiave assente vale zero, quindi tacere equivale a dichiararsi
    # pulito. Le rotte A/B non scrivevano `_unclassified_mass` affatto.
    try:
        from importers.iv_cee_hierarchy import declare_unclassified_mass
        balance_sheet_data.update(
            declare_unclassified_mass(
                balance_sheet_data, _declared_control_totals(file_path), "ivcee-single"
            )
        )
    except Exception as _declare_err:  # pragma: no cover - diagnostica, mai bloccante
        # Anche fallendo si dichiara. Una chiave ASSENTE a valle vale zero, cioe'
        # «pulito»: tacere qui rimetterebbe in piedi proprio il difetto che questa
        # dichiarazione esiste per togliere. Zero con `_measured` a zero significa
        # invece «non lo so», che e' la verita' quando la misura non e' riuscita.
        balance_sheet_data.setdefault('_unclassified_mass', Decimal('0'))
        balance_sheet_data.setdefault('_unclassified_mass_measured', Decimal('0'))
        logger.warning(
            f"Massa non classificata non dichiarata: {_declare_err}"
        )


    return balance_sheet_data, income_data

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
    # Step 1: Check if PDF is image-based (no extractable text). Vision has no
    # local provider (vincoli: "la vision resta su Anthropic"); the text branch
    # can run entirely on gx10 (PDF_LLM_PROVIDER_IVCEE=gx10) without ANTHROPIC_API_KEY.
    use_vision = _is_image_pdf(file_path)
    api_key = llm_provider.chiave_anthropic()
    client = None
    if use_vision or llm_provider.provider_ivcee() != "gx10":
        if not api_key:
            if use_vision:
                raise PDFImportError(
                    "PDF e' un'immagine: la vision richiede ANTHROPIC_API_KEY (nessun fornitore locale)."
                )
            raise PDFImportError("ANTHROPIC_API_KEY environment variable not set")
        try:
            client = anthropic.Anthropic(api_key=api_key)
        except Exception as e:
            raise PDFImportError(f"Failed to initialize Anthropic client: {e}")

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

        provider = llm_provider.provider_ivcee()

        # Step 2: Extract balance sheet (both years) via Claude Haiku (or gx10)
        try:
            sp_result = _extract_with_llm(
                client, sp_text, SP_BOTH_YEARS_SYSTEM_PROMPT,
                TwoYearBalanceSheetExtraction, "Stato Patrimoniale (both years)",
                tool_name="balance_sheet_both_years",
                provider=provider,
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during SP extraction: {e}")
        except llm_provider.LLMProviderError as e:
            raise PDFImportError(f"Errore gx10 durante l'estrazione SP: {e}")

        # Step 3: Extract income statement (both years) via Claude Haiku (or gx10)
        try:
            ce_result = _extract_with_llm(
                client, ce_text, CE_BOTH_YEARS_SYSTEM_PROMPT,
                TwoYearIncomeStatementExtraction, "Conto Economico (both years)",
                tool_name="income_statement_both_years",
                provider=provider,
            )
        except anthropic.APIError as e:
            raise PDFImportError(f"Anthropic API error during CE extraction: {e}")
        except llm_provider.LLMProviderError as e:
            raise PDFImportError(f"Errore gx10 durante l'estrazione CE: {e}")

    # Step 4: Convert to Decimal dicts and normalize signs
    current_bs = _reconcile_credit_aggregates_from_source(
        _model_to_decimal_dict(sp_result.current_year), "current"
    )
    prior_bs = _reconcile_credit_aggregates_from_source(
        _model_to_decimal_dict(sp_result.prior_year), "prior"
    )
    current_bs, prior_bs = _reconcile_blank_current_sp_cells(
        file_path, current_bs, prior_bs
    )
    current_bs = _recover_printed_sp_rows(file_path, current_bs)
    current_bs = _split_printed_debt_maturities(file_path, current_bs)
    current_bs = _recover_printed_fixed_asset_details(file_path, current_bs)
    raw_current_ce = _model_to_decimal_dict(ce_result.current_year)
    raw_prior_ce = _model_to_decimal_dict(ce_result.prior_year)
    current_ce = _normalize_ce_signs(dict(raw_current_ce))
    prior_ce = _normalize_ce_signs(dict(raw_prior_ce))
    current_ce, prior_ce = _reconcile_blank_current_ce_cells(
        file_path, current_ce, prior_ce
    )

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
        # Empty the prior but DO NOT return early: the current column still needs the
        # Step 5-7 validators + detail reconciler (so a monocolumn provvisorio like
        # budget_315 gets its dropped "VIII Utili portati a nuovo" reserve recovered).
        # Steps below no-op on the now-empty prior dicts.
        prior_bs, prior_ce = {}, {}

    # Step 4c: ZEROED CURRENT COLUMN (draft / opening exports). Some "provvisorio" PDFs
    # render the current-year column entirely at 0,00 while the only real figures sit in
    # the prior column (budget_314: "BILANCIO AL 31/12/2025" with the 2025 column all zero
    # and every amount in 2024). The current extraction is then empty (totale_attivo ~ 0)
    # and the file would import as VUOTO. Promote the valued prior column to current and
    # drop the (now redundant) prior, so the real data is imported instead of nothing.
    # Symmetric to Step 4b and mutually exclusive with it (that path requires the current
    # column to HAVE activity), so the two can never both fire.
    _cur_attivo = current_bs.get('totale_attivo', Decimal('0'))
    _cur_ricavi = current_ce.get('ce01_ricavi_vendite', Decimal('0'))
    _pri_attivo = prior_bs.get('totale_attivo', Decimal('0'))
    if (abs(_cur_attivo) < Decimal('1') and abs(_cur_ricavi) < Decimal('1')
            and abs(_pri_attivo) >= Decimal('1')):
        logger.warning(
            f"Current-year column is ZEROED (draft/opening export) while prior is valued "
            f"(attivo {_pri_attivo}): promoting prior column to current."
        )
        current_bs, current_ce = prior_bs, prior_ce
        prior_bs, prior_ce = {}, {}

    # Step 5: control-total normalization only.  Aggregates and accounting fields
    # are not inferred from the balance difference.
    current_bs = _reconcile_utile_in_passivo(current_bs, "current")
    prior_bs = _reconcile_utile_in_passivo(prior_bs, "prior")

    # Step 6: leave ce10 and taxes as extracted.  Cross-statement disagreement is
    # reported, never corrected by replacing a source value.

    # Step 7: Deterministic detail-line fill per column (text path only). The dual layout
    # prints both years side by side ('label\\ncur\\nprior'), so column 0 = current,
    # column 1 = prior — fixing the SAME dropped-negative-reserve / merged-personale bug
    # on BOTH years so the Confronto (comparison) columns line up.
    if not use_vision:
        current_bs = _reconcile_pn_detail(current_bs, sp_text, "current", column=0)
        prior_bs = _reconcile_pn_detail(prior_bs, sp_text, "prior", column=1)
        current_ce = _reconcile_personale_detail(current_ce, ce_text, "current", column=0)
        prior_ce = _reconcile_personale_detail(prior_ce, ce_text, "prior", column=1)
    current_ce = _reconcile_global_ce_thousand_scale(current_ce, current_bs, "current")
    if prior_bs and prior_ce:
        prior_ce = _reconcile_global_ce_thousand_scale(prior_ce, prior_bs, "prior")
    current_ce = _reconcile_isolated_ce_cost_signs(
        current_ce, raw_current_ce, current_bs, "current"
    )
    if prior_bs and prior_ce:
        prior_ce = _reconcile_isolated_ce_cost_signs(
            prior_ce, raw_prior_ce, prior_bs, "prior"
        )
    current_ce = _reconcile_ce09_from_source_details(current_ce, current_bs, "current")
    if prior_bs and prior_ce:
        prior_ce = _reconcile_ce09_from_source_details(prior_ce, prior_bs, "prior")

    # Un estrattore dichiara SEMPRE le proprie chiavi diagnostiche, anche a zero:
    # a valle una chiave assente vale zero, quindi tacere equivale a dichiararsi
    # pulito. Le rotte A/B non scrivevano `_unclassified_mass` affatto.
    try:
        from importers.iv_cee_hierarchy import declare_unclassified_mass
        current_bs.update(
            declare_unclassified_mass(
                current_bs, _declared_control_totals(file_path), "ivcee-current"
            )
        )
    except Exception as _declare_err:  # pragma: no cover - diagnostica, mai bloccante
        # Anche fallendo si dichiara. Una chiave ASSENTE a valle vale zero, cioe'
        # «pulito»: tacere qui rimetterebbe in piedi proprio il difetto che questa
        # dichiarazione esiste per togliere. Zero con `_measured` a zero significa
        # invece «non lo so», che e' la verita' quando la misura non e' riuscita.
        current_bs.setdefault('_unclassified_mass', Decimal('0'))
        current_bs.setdefault('_unclassified_mass_measured', Decimal('0'))
        logger.warning(
            f"Massa non classificata non dichiarata: {_declare_err}"
        )


    return current_bs, current_ce, prior_bs, prior_ce
