"""
PDF Balance Sheet Importer for Italian IV CEE format.

Uses PyMuPDF + Claude Haiku 4.5 (~5s). Requires ANTHROPIC_API_KEY.
"""

import os
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from database.db import SessionLocal
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from importers.pdf_mapper import IVCEEMapper
from config import Sector

logger = logging.getLogger(__name__)


class PDFImportError(Exception):
    """Exception raised when PDF import fails."""
    pass


# Soglia oltre cui un plug residuo del parser best-effort rende il bilancio inaffidabile
# (composizione per lo più fabbricata): sopra questa frazione del totale si rifiuta
# l'estrazione deterministica e si tenta l'LLM. Sotto, si importa con flag "BILANCIO NON
# QUADRATO" per correzione in Rettifiche (workflow esistente). Vedi iv_cee_hierarchy.
SC_PLUG_REJECT_PCT = Decimal("0.20")


# Map short keys from situazione_contabile_parser to full DB field names
_SC_KEY_MAP = {
    'sp01': 'sp01_crediti_soci', 'sp02': 'sp02_immob_immateriali', 'sp03': 'sp03_immob_materiali',
    'sp04': 'sp04_immob_finanziarie', 'sp05': 'sp05_rimanenze',
    'sp06': 'sp06_crediti_breve', 'sp07': 'sp07_crediti_lungo',
    'sp08': 'sp08_attivita_finanziarie', 'sp09': 'sp09_disponibilita_liquide',
    'sp10': 'sp10_ratei_risconti_attivi', 'sp11': 'sp11_capitale', 'sp12': 'sp12_riserve',
    'sp13': 'sp13_utile_perdita', 'sp14': 'sp14_fondi_rischi', 'sp15': 'sp15_tfr',
    'sp16': 'sp16_debiti_breve', 'sp17': 'sp17_debiti_lungo',
    'sp18': 'sp18_ratei_risconti_passivi',
    'ce01': 'ce01_ricavi_vendite', 'ce02': 'ce02_variazioni_rimanenze',
    'ce03': 'ce03_lavori_interni', 'ce04': 'ce04_altri_ricavi',
    'ce05': 'ce05_materie_prime', 'ce06': 'ce06_servizi', 'ce07': 'ce07_godimento_beni',
    'ce08': 'ce08_costi_personale', 'ce09': 'ce09_ammortamenti',
    'ce10': 'ce10_var_rimanenze_mat_prime', 'ce11': 'ce11_accantonamenti',
    'ce11b': 'ce11b_altri_accantonamenti', 'ce12': 'ce12_oneri_diversi',
    'ce13': 'ce13_proventi_partecipazioni', 'ce14': 'ce14_altri_proventi_finanziari',
    'ce15': 'ce15_oneri_finanziari', 'ce16': 'ce16_utili_perdite_cambi',
    'ce17': 'ce17_rettifiche_attivita_fin', 'ce18': 'ce18_proventi_straordinari',
    'ce19': 'ce19_oneri_straordinari', 'ce20': 'ce20_imposte',
}

def _map_sc_keys(data: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Map short SC parser keys (sp03, ce01) to full DB field names (sp03_immob_materiali)."""
    result = {}
    for k, v in data.items():
        # Already a full key? Pass through.
        if '_' in k:
            result[k] = v
        elif k in _SC_KEY_MAP:
            result[_SC_KEY_MAP[k]] = v
        # else: skip (totale_attivo, totale_passivo, etc.)
    return result


def _create_balance_sheet(db, financial_year_id: int, data: Dict[str, Decimal]) -> 'BalanceSheet':
    """Create a BalanceSheet record from a dict of sp01-sp18 values."""
    bs = BalanceSheet(
        financial_year_id=financial_year_id,
        sp01_crediti_soci=data.get('sp01_crediti_soci', Decimal('0')),
        sp02_immob_immateriali=data.get('sp02_immob_immateriali', Decimal('0')),
        sp03_immob_materiali=data.get('sp03_immob_materiali', Decimal('0')),
        sp04_immob_finanziarie=data.get('sp04_immob_finanziarie', Decimal('0')),
        sp05_rimanenze=data.get('sp05_rimanenze', Decimal('0')),
        sp06_crediti_breve=data.get('sp06_crediti_breve', Decimal('0')),
        sp07_crediti_lungo=data.get('sp07_crediti_lungo', Decimal('0')),
        sp08_attivita_finanziarie=data.get('sp08_attivita_finanziarie', Decimal('0')),
        sp09_disponibilita_liquide=data.get('sp09_disponibilita_liquide', Decimal('0')),
        sp10_ratei_risconti_attivi=data.get('sp10_ratei_risconti_attivi', Decimal('0')),
        sp11_capitale=data.get('sp11_capitale', Decimal('0')),
        sp12_riserve=data.get('sp12_riserve', Decimal('0')),
        sp13_utile_perdita=data.get('sp13_utile_perdita', Decimal('0')),
        sp14_fondi_rischi=data.get('sp14_fondi_rischi', Decimal('0')),
        sp15_tfr=data.get('sp15_tfr', Decimal('0')),
        sp16_debiti_breve=data.get('sp16_debiti_breve', Decimal('0')),
        sp17_debiti_lungo=data.get('sp17_debiti_lungo', Decimal('0')),
        sp18_ratei_risconti_passivi=data.get('sp18_ratei_risconti_passivi', Decimal('0')),
        sp04a_partecipazioni=Decimal('0'),
        sp04b_crediti_immob_breve=Decimal('0'),
        sp04c_crediti_immob_lungo=Decimal('0'),
        sp04d_altri_titoli=Decimal('0'),
        sp04e_strumenti_derivati_attivi=Decimal('0'),
        sp12a_riserva_sovrapprezzo=Decimal('0'),
        sp12b_riserve_rivalutazione=Decimal('0'),
        sp12c_riserva_legale=Decimal('0'),
        sp12d_riserve_statutarie=Decimal('0'),
        sp12e_altre_riserve=Decimal('0'),
        sp12f_riserva_copertura_flussi=Decimal('0'),
        sp12g_utili_perdite_portati=Decimal('0'),
        sp12h_riserva_neg_azioni_proprie=Decimal('0'),
        sp06a_crediti_clienti_breve=data.get('sp06a_crediti_clienti_breve', Decimal('0')),
        sp07a_crediti_clienti_lungo=data.get('sp07a_crediti_clienti_lungo', Decimal('0')),
        sp06b_crediti_controllate_breve=data.get('sp06b_crediti_controllate_breve', Decimal('0')),
        sp07b_crediti_controllate_lungo=data.get('sp07b_crediti_controllate_lungo', Decimal('0')),
        sp06c_crediti_collegate_breve=data.get('sp06c_crediti_collegate_breve', Decimal('0')),
        sp07c_crediti_collegate_lungo=data.get('sp07c_crediti_collegate_lungo', Decimal('0')),
        sp06d_crediti_controllanti_breve=data.get('sp06d_crediti_controllanti_breve', Decimal('0')),
        sp07d_crediti_controllanti_lungo=data.get('sp07d_crediti_controllanti_lungo', Decimal('0')),
        sp06e_crediti_tributari_breve=data.get('sp06e_crediti_tributari_breve', Decimal('0')),
        sp07e_crediti_tributari_lungo=data.get('sp07e_crediti_tributari_lungo', Decimal('0')),
        sp06f_imposte_anticipate_breve=data.get('sp06f_imposte_anticipate_breve', Decimal('0')),
        sp07f_imposte_anticipate_lungo=data.get('sp07f_imposte_anticipate_lungo', Decimal('0')),
        sp06g_crediti_altri_breve=data.get('sp06g_crediti_altri_breve', Decimal('0')),
        sp07g_crediti_altri_lungo=data.get('sp07g_crediti_altri_lungo', Decimal('0')),
        sp16a_debiti_banche_breve=data.get('sp16a_debiti_banche_breve', Decimal('0')),
        sp17a_debiti_banche_lungo=data.get('sp17a_debiti_banche_lungo', Decimal('0')),
        sp16b_debiti_altri_finanz_breve=data.get('sp16b_debiti_altri_finanz_breve', Decimal('0')),
        sp17b_debiti_altri_finanz_lungo=data.get('sp17b_debiti_altri_finanz_lungo', Decimal('0')),
        sp16c_debiti_obbligazioni_breve=data.get('sp16c_debiti_obbligazioni_breve', Decimal('0')),
        sp17c_debiti_obbligazioni_lungo=data.get('sp17c_debiti_obbligazioni_lungo', Decimal('0')),
        sp16d_debiti_fornitori_breve=data.get('sp16d_debiti_fornitori_breve', Decimal('0')),
        sp17d_debiti_fornitori_lungo=data.get('sp17d_debiti_fornitori_lungo', Decimal('0')),
        sp16e_debiti_tributari_breve=data.get('sp16e_debiti_tributari_breve', Decimal('0')),
        sp17e_debiti_tributari_lungo=data.get('sp17e_debiti_tributari_lungo', Decimal('0')),
        sp16f_debiti_previdenza_breve=data.get('sp16f_debiti_previdenza_breve', Decimal('0')),
        sp17f_debiti_previdenza_lungo=data.get('sp17f_debiti_previdenza_lungo', Decimal('0')),
        sp16g_altri_debiti_breve=data.get('sp16g_altri_debiti_breve', Decimal('0')),
        sp17g_altri_debiti_lungo=data.get('sp17g_altri_debiti_lungo', Decimal('0')),
    )
    db.add(bs)
    db.flush()
    return bs


def _create_income_statement(db, financial_year_id: int, data: Dict[str, Decimal]) -> 'IncomeStatement':
    """Create an IncomeStatement record from a dict of ce01-ce20 values."""
    def _ce(field: str) -> Decimal:
        return data.get(field, Decimal('0'))

    inc = IncomeStatement(
        financial_year_id=financial_year_id,
        ce01_ricavi_vendite=_ce('ce01_ricavi_vendite'),
        ce02_variazioni_rimanenze=_ce('ce02_variazioni_rimanenze'),
        ce03_lavori_interni=_ce('ce03_lavori_interni'),
        ce04_altri_ricavi=_ce('ce04_altri_ricavi'),
        ce05_materie_prime=_ce('ce05_materie_prime'),
        ce06_servizi=_ce('ce06_servizi'),
        ce07_godimento_beni=_ce('ce07_godimento_beni'),
        ce08_costi_personale=_ce('ce08_costi_personale'),
        ce08a_tfr_accrual=_ce('ce08a_tfr_accrual'),
        ce09_ammortamenti=_ce('ce09_ammortamenti'),
        ce09a_ammort_immateriali=_ce('ce09a_ammort_immateriali'),
        ce09b_ammort_materiali=_ce('ce09b_ammort_materiali'),
        ce09c_svalutazioni=_ce('ce09c_svalutazioni'),
        ce09d_svalutazione_crediti=_ce('ce09d_svalutazione_crediti'),
        ce10_var_rimanenze_mat_prime=_ce('ce10_var_rimanenze_mat_prime'),
        ce11_accantonamenti=_ce('ce11_accantonamenti'),
        ce11b_altri_accantonamenti=_ce('ce11b_altri_accantonamenti'),
        ce12_oneri_diversi=_ce('ce12_oneri_diversi'),
        ce13_proventi_partecipazioni=_ce('ce13_proventi_partecipazioni'),
        ce14_altri_proventi_finanziari=_ce('ce14_altri_proventi_finanziari'),
        ce15_oneri_finanziari=_ce('ce15_oneri_finanziari'),
        ce16_utili_perdite_cambi=_ce('ce16_utili_perdite_cambi'),
        ce17_rettifiche_attivita_fin=_ce('ce17_rettifiche_attivita_fin'),
        ce18_proventi_straordinari=_ce('ce18_proventi_straordinari'),
        ce19_oneri_straordinari=_ce('ce19_oneri_straordinari'),
        ce20_imposte=_ce('ce20_imposte'),
    )
    db.add(inc)
    db.flush()
    return inc


def import_pdf_balance_sheet(
    file_path: str,
    company_id: Optional[int] = None,
    fiscal_year: Optional[int] = None,
    company_name: Optional[str] = None,
    create_company: bool = True,
    sector: Optional[int] = None,
    period_months: Optional[int] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Import balance sheet from PDF file.

    Uses PyMuPDF + Claude Haiku 4.5. Requires ANTHROPIC_API_KEY.

    Args:
        file_path: Path to PDF file
        company_id: Optional company ID (will be created if None and create_company=True)
        fiscal_year: Fiscal year for the balance sheet
        company_name: Company name (for new company creation)
        create_company: Whether to create company if not exists
        sector: Company sector code (1-6)

    Returns:
        Dictionary with import results

    Raises:
        PDFImportError: If extraction or validation fails
    """

    db = SessionLocal()
    extraction_start = datetime.utcnow()

    try:
        logger.info(f"Starting PDF import from {file_path}")

        mapper = IVCEEMapper()
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')

        # Step 1: Detect format and extract PDF data
        prior_bs_data = None
        prior_ce_data = None

        # Step 1a: classify the document into a macro-area and pick the extraction
        # route (see importers/bilancio_classifier.py and Test/IMPORT-ROUTING-TAXONOMY.md).
        #   C  → ROUTE_TRIAL : deterministic situazione-contabile parser (balance via pareggio)
        #   A/B → ROUTE_IVCEE : IV-CEE extractor anchored on voce totals (keeps Assets=Liab+Equity)
        # This replaces the old binary is_trial_balance check: it routes IV-CEE bilanci
        # that merely *contain* account codes (B: budget_313/314) to the IV-CEE path instead
        # of the empty trial-balance parser, and fails honestly on non-bilancio inputs.
        import fitz
        from importers.situazione_contabile_parser import extract_situazione_contabile
        from importers.bilancio_classifier import (
            classify_bilancio, ROUTE_TRIAL, ROUTE_IVCEE, ROUTE_XBRL, ROUTE_UNSUPPORTED,
        )
        doc = fitz.open(file_path)
        sample_text = "".join(page.get_text() for page in doc[:14])
        doc.close()
        classification = classify_bilancio(file_path=file_path, text=sample_text)
        logger.info(
            f"Classificato: macro-area {classification.macro_area} "
            f"({classification.subcategory}) → rotta {classification.route}; {classification.reason}"
        )

        if classification.route == ROUTE_XBRL:
            raise PDFImportError(
                "Il file è un'istanza XBRL nativa: usa l'import XBRL, non l'import PDF."
            )
        if classification.route == ROUTE_UNSUPPORTED:
            raise PDFImportError(
                f"Documento non importabile come bilancio completo: {classification.reason}."
            )

        is_trial_balance = (classification.route == ROUTE_TRIAL)

        def _llm_extract():
            """IV CEE extraction via LLM. Returns (bs, ce, prior_bs, prior_ce)."""
            if not api_key:
                raise PDFImportError("ANTHROPIC_API_KEY is required for PDF import")
            logger.info("Using LLM extraction (ANTHROPIC_API_KEY found)")
            from importers.pdf_extractor_llm import (
                extract_pdf_with_llm, extract_pdf_both_years_with_llm,
            )
            if period_months:
                # Infrannuale: current = partial year, prior = reference full year — both
                # come from the same dual pass (the comparison engine needs them paired).
                logger.info(f"Dual-year extraction (period_months={period_months})")
                return extract_pdf_both_years_with_llm(file_path)

            # Budget (full year): take the CURRENT year from the proven single-year extractor
            # (the both-years prompt occasionally drops a current-year line — budget_227), then
            # run a dual pass purely to capture the PRIOR (comparative) column. This way a
            # comparative bilancio imports BOTH years and the user is never asked to re-upload a
            # year already in the PDF, WITHOUT degrading current-year quality. The dual pass
            # returns empty prior dicts on monocolumn PDFs (no fabricated prior). The extra
            # Haiku calls are cheap and PDF import is infrequent.
            # force_llm=True: this helper is only reached for IV-CEE PDFs or as the
            # explicit fallback after the deterministic parser returned empty; in the
            # latter case the document was (mis-)detected as a trial balance, so without
            # force_llm the single-year extractor would re-route back to that same empty
            # deterministic parser (budget_313/314).
            bs, ce = extract_pdf_with_llm(file_path, force_llm=True)
            prior_bs_data = prior_ce_data = None
            try:
                _, _, prior_bs_data, prior_ce_data = extract_pdf_both_years_with_llm(file_path)
            except Exception as prior_err:
                logger.warning(
                    f"Prior-year dual extraction failed ({type(prior_err).__name__}: {prior_err}); "
                    f"importing current year only"
                )
            return bs, ce, prior_bs_data, prior_ce_data

        sc_quadratura_warnings = []
        _coge_ok = False
        if is_trial_balance:
            # Route C (trial balance / situazione contabile). GENERAL rule: run BOTH the
            # CoGe LLM extractor and the deterministic best-effort parser, then keep the
            # CLEANER one — the candidate whose unclassified residual (_plug_residual, read
            # by check_quadratura) is smallest. Neither extractor is universally better: the
            # LLM wins on free-form CoGe lists, while the deterministic parser (with its
            # dotted-hierarchical/4-sezioni rescue) wins on structured mastro layouts where
            # the LLM stochastically drops mass. The deterministic pass is free (no LLM), so
            # always running it costs nothing and strictly improves the result. The IV-CEE
            # LLM is the last resort ONLY when BOTH come up empty (no Stato Patrimoniale).
            from importers.iv_cee_hierarchy import check_quadratura

            def _residual_of(bs, ce):
                """Plug residual (unclassified mass) for a candidate, or None if unusable
                (empty extraction). Lower = more complete."""
                try:
                    if bs.get('totale_attivo', Decimal('0')) <= 0:
                        return None
                    q = check_quadratura(bs, ce)
                    return None if q.is_empty else q.plug_residual
                except Exception:
                    return None

            candidates = []  # (residual, bs, ce, source)

            if api_key:
                try:
                    from importers.pdf_extractor_llm import extract_trial_balance_with_llm
                    coge_bs, coge_ce = extract_trial_balance_with_llm(file_path)
                    r = _residual_of(coge_bs, coge_ce)
                    if r is not None:
                        candidates.append((r, coge_bs, coge_ce, "CoGe-LLM"))
                except Exception as coge_err:
                    logger.warning(
                        f"Route C: CoGe LLM extractor failed "
                        f"({type(coge_err).__name__}: {coge_err})"
                    )

            try:
                sc_bs, sc_ce = extract_situazione_contabile(file_path)
                sc_bs_mapped = _map_sc_keys(sc_bs)   # short keys (sp03) -> full DB names
                sc_ce_mapped = _map_sc_keys(sc_ce)
                r = _residual_of(sc_bs_mapped, sc_ce_mapped)
                if r is not None:
                    candidates.append((r, sc_bs_mapped, sc_ce_mapped, "deterministico"))
            except Exception as sc_err:
                logger.warning(
                    f"Route C: deterministic SC parser failed "
                    f"({type(sc_err).__name__}: {sc_err})"
                )

            if candidates:
                # keep the cleaner extractor (smallest unclassified residual)
                candidates.sort(key=lambda c: c[0])
                residual, balance_sheet_data, income_data, source = candidates[0]
                _coge_ok = True
                # Anchor sp13 to the document's DECLARED result for the CHOSEN candidate,
                # whatever extractor produced it (the deterministic parser may leave sp13=0
                # or unanchored — budget_342/367). Idempotent on the CoGe result (already
                # reconciled inside the extractor). This makes sp13 = declared before the
                # CE↔SP identity step aligns the CE to it.
                try:
                    from importers.pdf_extractor_llm import (
                        _declared_control_totals, _reconcile_trial_to_declared,
                    )
                    _decl = _declared_control_totals(file_path)
                    balance_sheet_data = _reconcile_trial_to_declared(
                        balance_sheet_data, _decl, source)
                    residual = balance_sheet_data.get('_plug_residual', residual)
                except Exception as _rc_err:
                    logger.warning(f"Route C: declared-result reconcile skipped: {_rc_err}")
                others = ", ".join(f"{s}={r:,.0f}" for r, _b, _c, s in candidates)
                logger.info(f"Route C: scelto estrattore '{source}' (residuo minore "
                            f"{residual:,.0f}); candidati: {others}")
                # Surface the chosen plug as a NON-blocking flag (never reject): a large
                # residual means the composition is partly estimated — refined in Rettifiche.
                _tot = balance_sheet_data.get('totale_attivo', Decimal('0')) or Decimal('1')
                if residual > Decimal('1'):
                    _pct = 100 * residual / _tot
                    _sev = ("prevalentemente stimata"
                            if residual > SC_PLUG_REJECT_PCT * _tot else "parziale")
                    sc_quadratura_warnings.append(
                        f"BILANCIO NON QUADRATO ({_sev}): residuo {residual:,.0f} "
                        f"({_pct:.0f}% del totale) tamponato in liquidità/debiti — "
                        f"correggere in Rettifiche"
                    )
            elif not api_key:
                raise PDFImportError(
                    "Impossibile estrarre la situazione contabile (nessun dato) "
                    "e ANTHROPIC_API_KEY non impostata."
                )
            else:
                # both extractors empty → IV-CEE LLM as a genuine last resort
                logger.warning("Route C: entrambi gli estrattori vuoti; "
                               "ultimo tentativo con l'estrattore IV-CEE LLM")
                balance_sheet_data, income_data, prior_bs_data, prior_ce_data = _llm_extract()
        if not is_trial_balance:
            # IV CEE format (routes A/B) — use LLM extraction
            balance_sheet_data, income_data, prior_bs_data, prior_ce_data = _llm_extract()
            # GENERAL: make a near-balanced IV-CEE extraction actually balance. The LLM can
            # drop a few thousand euro on one side of a very detailed bilancio (e.g. the
            # dual-year extractor on budget_352), which otherwise hard-fails validate_balance.
            # Anchor to the declared TOTALE ATTIVO and plug the small short side (capped/flagged).
            try:
                from importers.iv_cee_hierarchy import reconcile_ivcee_balance
                from importers.pdf_extractor_llm import _declared_control_totals
                _decl = _declared_control_totals(file_path)
                balance_sheet_data = reconcile_ivcee_balance(balance_sheet_data, _decl, "ivcee")
                if prior_bs_data:
                    prior_bs_data = reconcile_ivcee_balance(prior_bs_data, None, "ivcee-prior")
            except Exception as _iv_err:
                logger.warning(f"IV-CEE balance reconcile skipped: {_iv_err}")

        # GENERAL rule for ALL routes: enforce the accounting identity utile_CE == sp13.
        # The result of the year is one number that must appear identically on the CE
        # (bottom line) and the SP (sp13). SP and CE are extracted independently and drift,
        # so the "Verifica CE ↔ SP" fails on almost every file. sp13 is the authoritative
        # anchor (pinned by the balance identity, and set to the declared result on route C);
        # we align the CE to it by plugging the gap into a CE line. Applied to A/B and C alike.
        # CE↔SP: default to trusting sp13 (balance-anchored, usually correct; = declared
        # result on route C) and aligning the CE to it. The DECLARED current Utile/Perdita is
        # the arbiter: it flips the decision to "trust the CE and fix sp13" (moving the
        # PRIOR-year result into reserves) ONLY when the declared value confirms the CE. This
        # catches the prior-year-utile case WITHOUT corrupting a correct sp13 when the CE is
        # garbage (sign/parse bug) and no declared anchor exists (budget_413).
        try:
            from importers.iv_cee_hierarchy import enforce_ce_sp_identity
            from importers.pdf_extractor_llm import _declared_control_totals
            _decl_ce = _declared_control_totals(file_path)
            income_data = enforce_ce_sp_identity(
                balance_sheet_data, income_data, "import",
                prefer="sp13", declared=_decl_ce)
            if prior_bs_data and prior_ce_data:
                prior_ce_data = enforce_ce_sp_identity(
                    prior_bs_data, prior_ce_data, "import-prior", prefer="sp13")
        except Exception as _ce_sp_err:
            logger.warning(f"CE↔SP identity enforcement skipped: {_ce_sp_err}")

        # Step 2: Validate balance sheet (both paths)
        logger.info("Validating balance sheet...")
        if not mapper.validate_balance(balance_sheet_data):
            raise PDFImportError("Balance sheet does not balance (Assets != Liabilities + Equity)")

        # Unified quadratura diagnostic across ALL routes (shared IV-CEE engine):
        # validate_balance above is the hard structural gate; this adds the CE
        # utile==sp13 cross-check (which validate_balance lacks) and any plug-masking,
        # so every route is judged by the same rules. Non-blocking (logged) to avoid
        # rejecting borderline-but-usable A/B imports.
        try:
            from importers.iv_cee_hierarchy import check_quadratura
            _qd = check_quadratura(balance_sheet_data, income_data)
            for _w in _qd.warnings:
                logger.warning(f"quadratura: {_w}")
        except Exception:
            pass

        warnings = mapper.validate_hierarchy(balance_sheet_data)
        # Surface the deterministic trial-balance plug flag to the user (Rettifiche cue),
        # so an imperfect-but-imported situazione contabile is visible rather than silent.
        warnings.extend(sc_quadratura_warnings)
        if warnings:
            logger.warning(f"Balance sheet hierarchy warnings: {warnings}")

        # Step 3: Handle company
        company = None
        if company_id:
            company = db.query(Company).filter(Company.id == company_id).first()
            if not company:
                raise PDFImportError(f"Company with ID {company_id} not found")
            if user_id and company.user_id != user_id:
                raise PDFImportError(f"Company with ID {company_id} not found")
        elif create_company and company_name:
            company = Company(
                name=company_name,
                tax_id=None,
                sector=sector or Sector.SERVIZI.value,
                user_id=user_id,
            )
            db.add(company)
            db.flush()
            logger.info(f"Created new company: {company.name} (ID: {company.id})")
        else:
            raise PDFImportError("Either company_id or (create_company=True and company_name) must be provided")

        # Step 4: Check if fiscal year already exists (match same type: partial or full)
        if fiscal_year:
            if period_months:
                # Partial import: only delete existing partial record
                existing_year = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == fiscal_year,
                    FinancialYear.period_months.isnot(None),
                ).first()
            else:
                # Full-year import: only delete existing full-year record
                existing_year = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == fiscal_year,
                    FinancialYear.period_months.is_(None),
                ).first()

            if existing_year:
                logger.warning(f"Financial year {fiscal_year} (period_months={existing_year.period_months}) already exists for company {company.id}, will update")
                if existing_year.balance_sheet:
                    db.delete(existing_year.balance_sheet)
                if existing_year.income_statement:
                    db.delete(existing_year.income_statement)
                db.delete(existing_year)
                db.flush()

        # Step 5: Create current-year financial year
        current_year_val = fiscal_year or datetime.now().year
        financial_year_obj = FinancialYear(
            company_id=company.id,
            year=current_year_val,
            period_months=period_months  # None for full year, 1-11 for partial
        )
        db.add(financial_year_obj)
        db.flush()

        # Step 6: Create balance sheet and income statement (current year)
        balance_sheet = _create_balance_sheet(db, financial_year_obj.id, balance_sheet_data)
        logger.info(f"Balance sheet created (ID: {balance_sheet.id})")

        income_statement = _create_income_statement(db, financial_year_obj.id, income_data)
        logger.info(f"Income statement created (ID: {income_statement.id})")

        # Step 6b: Cross-check SP utile vs CE net profit
        sp_utile = balance_sheet.sp13_utile_perdita
        ce_utile = income_statement.net_profit
        profit_diff = abs(sp_utile - ce_utile)
        if profit_diff > Decimal('1'):
            profit_warning = (
                f"Net profit mismatch: SP Utile/Perdita = {sp_utile}, "
                f"CE Net Profit = {ce_utile} (diff: {profit_diff})"
            )
            logger.warning(profit_warning)
            warnings.append(profit_warning)
        else:
            logger.info(f"Net profit cross-check OK: SP={sp_utile}, CE={ce_utile}")

        # Step 7: Save prior year if dual-year extraction was used
        prior_year_imported = False
        prior_fiscal_year = fiscal_year - 1 if fiscal_year else None
        if prior_bs_data and prior_ce_data and fiscal_year:
            # Check if prior year data is meaningful (not all zeros from single-column PDF)
            prior_sp_fields = [v for k, v in prior_bs_data.items()
                               if k.startswith('sp') and k != 'totale_attivo' and k != 'totale_passivo']
            prior_has_data = any(v != Decimal('0') for v in prior_sp_fields)

            if not prior_has_data:
                logger.info("Prior year data is all zeros (single-column PDF), skipping")
            else:
                fresh_prior_balances = mapper.validate_balance(prior_bs_data)
                existing_prior = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == prior_fiscal_year,
                    FinancialYear.period_months.is_(None),
                ).first()

                if existing_prior and not fresh_prior_balances:
                    # A prior year already exists and the freshly extracted one does NOT balance:
                    # keep the existing record. It may be a manually uploaded full-year statement
                    # or an already-corrected prior — don't clobber it with a worse extraction.
                    logger.info(
                        f"Prior year {prior_fiscal_year} already exists and fresh extraction does not "
                        f"balance — keeping existing record"
                    )
                    prior_year_imported = True  # already present
                else:
                    # Import (or, on re-import, REPLACE) the prior year. Replacing a stale record with
                    # a freshly extracted one that BALANCES lets a re-import pick up extractor fixes
                    # (budget_297 2024: old import had inflated reserves; re-import now refreshes it).
                    # A non-balancing prior is still imported on FIRST import (no existing record) with
                    # a BILANCIO NON QUADRATO warning so the user corrects it in Rettifiche rather than
                    # being forced to re-upload it.
                    if existing_prior:
                        logger.info(
                            f"Prior year {prior_fiscal_year} exists; replacing with fresh balancing extraction"
                        )
                        if existing_prior.balance_sheet:
                            db.delete(existing_prior.balance_sheet)
                        if existing_prior.income_statement:
                            db.delete(existing_prior.income_statement)
                        db.delete(existing_prior)
                        db.flush()

                    if not fresh_prior_balances:
                        prior_unbalanced_warning = (
                            f"BILANCIO NON QUADRATO [{prior_fiscal_year}]: anno precedente estratto dal "
                            f"PDF non quadra — importato comunque, correggere in Rettifiche"
                        )
                        logger.warning(prior_unbalanced_warning)
                        warnings.append(prior_unbalanced_warning)

                    prior_fy = FinancialYear(
                        company_id=company.id,
                        year=prior_fiscal_year,
                        period_months=None  # Full 12-month year
                    )
                    db.add(prior_fy)
                    db.flush()

                    prior_bs = _create_balance_sheet(db, prior_fy.id, prior_bs_data)
                    prior_ce = _create_income_statement(db, prior_fy.id, prior_ce_data)
                    prior_year_imported = True
                    logger.info(
                        f"Prior year {prior_fiscal_year} imported (BS ID: {prior_bs.id}, CE ID: {prior_ce.id})"
                    )

                    # Cross-check prior year SP utile vs CE net profit
                    prior_sp_utile = prior_bs.sp13_utile_perdita
                    prior_ce_utile = prior_ce.net_profit
                    prior_profit_diff = abs(prior_sp_utile - prior_ce_utile)
                    if prior_profit_diff > Decimal('1'):
                        prior_profit_warning = (
                            f"Prior year net profit mismatch: SP Utile/Perdita = {prior_sp_utile}, "
                            f"CE Net Profit = {prior_ce_utile} (diff: {prior_profit_diff})"
                        )
                        logger.warning(prior_profit_warning)
                        warnings.append(prior_profit_warning)

        # Step 8: Commit transaction
        db.commit()

        extraction_time = (datetime.utcnow() - extraction_start).total_seconds()
        if is_trial_balance:
            # Route C: distinguish the CoGe LLM pass from the deterministic parser fallback.
            extraction_method = "situazione_contabile_llm" if _coge_ok else "situazione_contabile"
        else:
            extraction_method = "llm"

        logger.info(
            f"PDF import successful: company={company.name}, "
            f"year={financial_year_obj.year}, "
            f"method={extraction_method}, "
            f"time={extraction_time:.2f}s"
        )

        result = {
            "success": True,
            "company_id": company.id,
            "company_name": company.name,
            "fiscal_year": financial_year_obj.year,
            "balance_sheet_id": balance_sheet.id,
            "income_statement_id": income_statement.id,
            "format": "micro",  # TODO: Detect format from PDF
            "macro_area": classification.macro_area,
            "macro_subcategory": classification.subcategory,
            "confidence_score": 0.95,
            "extraction_method": extraction_method,
            "extraction_time_seconds": round(extraction_time, 2),
            "message": f"Successfully imported balance sheet for {company.name} ({financial_year_obj.year})",
            "warnings": warnings
        }

        result["prior_year_imported"] = prior_year_imported
        result["prior_fiscal_year"] = prior_fiscal_year

        return result

    except PDFImportError:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error during PDF import: {e}")
        raise PDFImportError(f"Failed to import PDF: {str(e)}")

    finally:
        db.close()
