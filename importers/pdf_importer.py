"""
PDF Balance Sheet Importer for Italian IV CEE format.

Uses PyMuPDF and a configurable LLM provider for text extraction.
Vision OCR still requires ANTHROPIC_API_KEY.

Dal 2026-11-24 gli aiutanti stanno nel pacchetto importers/import_pdf; qui resta
import_pdf_balance_sheet, che li cerca fra i nomi di questo modulo: un monkeypatch su
importers.pdf_importer continua a valere per le sue chiamate. Il modulo ri-esporta ogni nome del
pacchetto, privati compresi.
"""

from importlib import import_module
import logging
import hashlib
import json
import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from config import Sector
from database.db import SessionLocal
from database.models import Company, FinancialYear
from importers.nome_azienda import nome_azienda_pulito
from importers.pdf_mapper import IVCEEMapper
from importers.import_pdf.verdetti import (
    PDFImportError, _TOL_QUADRATURA, _UNBALANCED_WARNING_PREFIX, _UNBALANCED_WARNING_SUFFIX,
    _avvisi_fondi_snello, _avviso_comparato_non_letto, _avviso_risultato_anno_prima_conti,
    _avviso_risultato_in_apertura, _avviso_risultato_ricostruito, _classify_balance_failure,
    _declared_totals_contradiction, _it_amount, _resolve_validation_status, _rifiuta_lettura_non_riuscita,
    _rifiuta_passivo_non_letto, _should_import_prior, _single_year_read_prior_column,
    _snello_squadrato_reason, _validation_report_payload,
)
from importers.import_pdf.estrattori import (
    SC_PLUG_REJECT_PCT, _coge_attivo, _dettagli_gia_letti, _extract_route_c_last_resort, _ivcee_attivo,
    _map_sc_keys, _modello_non_disponibile, _motivo_ripiego_classico, _motore_snello,
    _prospetto_sintetico_mineru_extract, _ripiego_classico_acceso, _schema_etichette_extract,
    _schema_generico_mineru_extract, _xbrl_reso_extract,
)
from importers.import_pdf.riscatto_vision import (
    _apply_vision_rescue,
)
from importers.import_pdf.persistenza import (
    _create_balance_sheet, _create_income_statement, _lettore_diagnosi_import,
)

logger = logging.getLogger("importers.pdf_importer")

_MODULI = (
    "riassunti",
    "verdetti",
    "estrattori",
    "riscatto_vision",
    "persistenza",
)

for _nome in _MODULI:
    _modulo = import_module(f"importers.import_pdf.{_nome}")
    globals().update({_k: _v for _k, _v in vars(_modulo).items() if not _k.startswith("__")})
del _nome, _modulo


_PDF_PARSER_VERSION = "macro-fallback-v8-2026-09-21"

def import_pdf_balance_sheet(
    file_path: str,
    company_id: Optional[int] = None,
    fiscal_year: Optional[int] = None,
    company_name: Optional[str] = None,
    create_company: bool = True,
    sector: Optional[int] = None,
    period_months: Optional[int] = None,
    user_id: Optional[str] = None,
    extraction_context: Any = None,
) -> Dict[str, Any]:
    """
    Import balance sheet from PDF file.

    Uses PyMuPDF and the configured LLM provider for text extraction.
    Vision OCR requires ANTHROPIC_API_KEY.

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

    # Normalize: 12 (or more) months is a full year — store as NULL per the
    # FinancialYear convention (NULL = full year, 1-11 = partial). Only 1-11
    # marks a genuine partial-year (infrannuale) record.
    if period_months is not None and period_months >= 12:
        period_months = None

    # Un PDF ripassato da PDF24/Ghostscript può avere il testo cifrato (font senza
    # mappa Unicode): l'import legge una copia decodificata e lo dichiara. L'impronta
    # resta quella del file caricato.
    _file_originale = file_path
    _testo_cifrato = None
    # Il PDF sintetico stampato dalle tabelle MinerU (route C): per i controlli
    # dichiarativi a valle E' il documento (stessi totali e stessi fondi, letti dal
    # testo); quello caricato e' una scansione senza testo. Cancellato nel finally.
    _pdf_mineru = None
    try:
        from importers import testo_cifrato as _tc
        _riparato = _tc.ripara(file_path)
    except Exception as _tc_err:
        logger.warning(f"Controllo del testo cifrato non riuscito: {_tc_err}")
        _riparato = None
    if _riparato is not None:
        file_path, _testo_cifrato = _riparato

    db = SessionLocal()
    extraction_start = datetime.utcnow()

    try:
        logger.info(f"Starting PDF import from {file_path}")

        mapper = IVCEEMapper()
        # Declared control totals, when the route computed any. Initialised here so
        # the reliability step below is in scope for EVERY route, not just route C.
        # NOTE: `_declared_control_totals` (the only producer of this dict, set below
        # on route C) never returns a 'patrimonio_netto' key - only attivo/passivo/
        # pareggio/utile/perdita. So `reliability._assess_patrimonio_netto` currently
        # ALWAYS sees `declared.get('patrimonio_netto') is None` on every route and
        # evaluates to DERIVED, never VERIFIED/UNRELIABLE. That is correct behaviour
        # for a missing control (never block on absence), but the PN limb is inert
        # until some route is taught to read a printed "Totale patrimonio netto" and
        # add it to this dict under that key.
        _declared_for_reliability = None
        from importers.llm_provider import chiave_anthropic
        api_key = chiave_anthropic()

        # Step 1: Detect format and extract PDF data
        prior_bs_data = None
        prior_ce_data = None

        # Step 1a: classify the document into a macro-area and pick the extraction
        # route (see importers/bilancio_classifier.py and docs/import/IMPORT-ROUTING-TAXONOMY.md).
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

        # Scanned (image-only) PDF: there is no extractable text, so the text-based
        # classifier would route the file to UNSUPPORTED even though the route-C and
        # IV-CEE extractors are already vision-capable. Recover routing text with a
        # one-off OCR-via-vision pass and feed THAT to the same classifier; the chosen
        # extractor then re-reads the page images for the real figures. Needs an API key.
        ocr_text = None
        local_coordinate_ocr = False
        is_scanned = len(sample_text.strip()) < 50

        # MinerU OCR context (route /import/pdf-ocr): when supplied, MinerU has already
        # produced document text. Use it for BOTH the classifier routing and the
        # route-C CoGe LLM extractor (which accepts ocr_text), instead of a second
        # vision-OCR pass. MinerU is an extractor only — all accounting classification,
        # reconciliation and quadratura gates below are unchanged and still decide the result.
        #
        # _ocr_source marks that sample_text/ocr_text came from OCR (MinerU), NOT a native
        # text layer. OCR text is noisier: a single garbled totals row (e.g. MinerU reading
        # "TOTALE ATTIVITA' 56550ont a 53.06941 2.828.226,30" as attivo=53.069) must NOT
        # trigger the HARD source-contradiction preflight, which is meant for reliable
        # printed totals and aborts with no Rettifiche fallback. This mirrors how the same
        # gate is already skipped for is_scanned. is_scanned itself stays False so the
        # vision-OCR block below is skipped (we already have MinerU text).
        _ocr_source = False
        _mineru_full_text = getattr(extraction_context, "full_text", "") if extraction_context is not None else ""
        if _mineru_full_text and _mineru_full_text.strip():
            sample_text = _mineru_full_text
            ocr_text = _mineru_full_text
            is_scanned = False
            local_coordinate_ocr = False
            _ocr_source = True
            logger.info(
                "MinerU extraction context in use: text_len=%d tables=%d version=%s",
                len(sample_text),
                len(getattr(extraction_context, "tables", ()) or ()),
                getattr(extraction_context, "mineru_version", None),
            )

        if is_scanned:
            logger.info("PDF scansionato (nessun testo estraibile): passaggio OCR per il routing")
            # The by-sign trial-balance parser can consume local OCR bounding boxes
            # exactly.  Try that deterministic route before requiring an external
            # vision service; the helper is optional and returns "" when RapidOCR
            # is not installed or the scan is a different schema.
            from importers.situazione_contabile_parser import (
                ocr_bilancio_verifica_segno_sample_text,
            )
            ocr_text = ocr_bilancio_verifica_segno_sample_text(file_path)
            local_coordinate_ocr = bool(ocr_text)
            if not ocr_text:
                if not api_key:
                    raise PDFImportError(_modello_non_disponibile(
                        "Il PDF è una scansione (nessun testo selezionabile): questo "
                        "schema non è supportato dall'OCR locale e l'import richiede "
                        "ANTHROPIC_API_KEY."
                    ))
                from importers.pdf_extractor_llm import ocr_pdf_sample_text
                # OCR enough pages to cover the whole (usually short) document: the same
                # text drives BOTH routing and the route-C value extraction.
                ocr_text = ocr_pdf_sample_text(file_path, max_pages=20)
            sample_text = ocr_text or ""
            if len(sample_text.strip()) < 50:
                raise PDFImportError(
                    "Il PDF è una scansione ma l'OCR non ha riconosciuto testo "
                    "sufficiente (immagine illeggibile o documento non contabile)."
                )

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

        # Import snello (economia): dietro IMPORT_MOTORE=snello, un unico motore
        # legge la struttura del documento e produce SP/CE gia' quadrati. E'
        # un'economia, non una nuova rotta: se non produce nulla di utilizzabile
        # (o solleva), il codice sotto — is_trial_balance/IV-CEE come oggi — resta
        # il ripiego dichiarato, mai silenzioso (validation_report["import_snello"]
        # lo dice sempre: con il motore classico contiene il solo "ripiego_classico"). Scansioni e testo da
        # OCR (is_scanned/_ocr_source) non hanno mai una struttura testuale
        # affidabile da analizzare: l'importatore non parte nemmeno, e lo
        # dichiara con esito "non_applicabile" invece di un ripiego silenzioso.
        # Un'istanza XBRL nativa non arriva qui: la rotta ROUTE_XBRL solleva sopra.
        _snello = None
        _snello_report = None
        # Scansione letta da MinerU (decisione del proprietario, 2026-10-14): se le sue tabelle
        # hanno la forma di una situazione a sezioni contrapposte se ne stampa un PDF sintetico,
        # un PDF di testo con la geometria pulita. Lo legge l'importatore come qualunque
        # altro PDF di testo (stessi lettori deterministici, stesso tappo, stessa rilettura);
        # la route C sotto lo riusa se lo snello non adotta. Il divieto per le scansioni era
        # nato con l'OCR di prima, che dava solo testo libero.
        if _ocr_source and extraction_context is not None:
            try:
                from importers.mineru_contrapposte import pdf_da_tabelle
                _pdf_mineru = pdf_da_tabelle(extraction_context)
            except Exception as _mc_err:
                logger.warning(f"Tabelle MinerU non lette ({_mc_err})")
                _pdf_mineru = None
        _file_snello = _pdf_mineru or file_path
        if _motore_snello():
            if is_scanned or (_ocr_source and _pdf_mineru is None):
                _snello_report = {
                    "esito": "non_applicabile",
                    "motivo": "scansione" if is_scanned else "ocr",
                }
            else:
                from importers import import_snello
                # Decisione del proprietario, 2026-10-03: un riepilogo a sole macro-voci non e'
                # un bilancio e non si importa - ne' dall'importatore ne' dal ripiego di
                # oggi. Riconosciuto dal testo, PRIMA della struttura (nessuna chiamata modello);
                # stessa uscita degli altri documenti rifiutati (PDFImportError, nulla salvato).
                from importers.import_snello import riepilogo as _riepilogo
                if _riepilogo.riconosci_riepilogo(_file_snello):
                    raise PDFImportError(_riepilogo.MESSAGGIO)
                try:
                    # Tutto in locali fino in fondo: un'eccezione IN QUALUNQUE punto di
                    # questo blocco (compreso il calcolo dei totali sotto) non deve
                    # lasciare _snello/balance_sheet_data/... assegnati a meta': i due
                    # cancelli piu' sotto leggono "_snello is None" per decidere se il
                    # codice di oggi deve girare, e un _snello legato a un risultato mai
                    # adottato per intero li terrebbe chiusi su un bilancio incompleto o
                    # con tipi non validi (bug riprodotto in revisione: un valore non
                    # numerico dentro bs fa fallire proprio il calcolo dei totali qui
                    # sotto, DOPO che _snello era gia' assegnato nella versione precedente).
                    # route_hint: la route che il classificatore ha gia' deciso (ROUTE_TRIAL per una
                    # situazione contabile) aiuta modo_da_mappe a scegliere "conti" su un voto vicino
                    # alla parita' fra schema conti e schema legge (Task lotto-b, fix 9, diagnosi
                    # budget_313: senza l'indizio un pareggio cadeva sul lato sbagliato).
                    _risultato_snello = import_snello.importa(
                        _file_snello, ocr_text=None if _pdf_mineru else ocr_text,
                        route_hint=classification.route)
                    _bs_snello, _ce_snello = _risultato_snello.bs, _risultato_snello.ce
                    _prior_bs_snello = _risultato_snello.prior_bs
                    _prior_ce_snello = _risultato_snello.prior_ce
                    # Il motore snello lavora sulle somme sp01..sp18 (stesse
                    # _ATTIVO_FIELDS/_PASSIVO_FIELDS di mapper.validate_balance,
                    # gia' quadrate da tappa()/misura()), ma non scrive mai
                    # 'totale_attivo'/'totale_passivo' sul dict: ogni altro
                    # estrattore li dichiara da se'. Senza, validate_balance li
                    # legge assenti (= zero) e _classify_balance_failure tratta
                    # un bilancio quadrato come un'estrazione vuota (hard_error).
                    from importers.iv_cee_hierarchy import _ATTIVO_FIELDS, _PASSIVO_FIELDS
                    for _dati_snello in (_bs_snello, _prior_bs_snello):
                        if _dati_snello is not None:
                            _dati_snello["totale_attivo"] = sum(
                                (Decimal(_dati_snello.get(k, 0)) for k in _ATTIVO_FIELDS), Decimal(0))
                            _dati_snello["totale_passivo"] = sum(
                                (Decimal(_dati_snello.get(k, 0)) for k in _PASSIVO_FIELDS), Decimal(0))
                    # Il blocco e' riuscito per intero: solo ora si adotta il risultato.
                    if (_pdf_mineru is not None
                            and _risultato_snello.report.get("esito") not in ("ok", "tappo")
                            and _risultato_snello.report.get("causa") != "documento_sbilanciato"):
                        # Su una scansione lo snello si adotta solo se quadra: una sua lettura
                        # squadrata di un PDF sintetico non e' migliore di quella della route C
                        # (Bilancino, Gerevini 689: piu' lontana, e oltre il 5% la regola delle
                        # scansioni rifiutava il file). Si torna alla route C, come prima.
                        _rep = dict(_risultato_snello.report)
                        raise import_snello.SnelloNonRiuscito(
                            {"esito": "ripiego", "fase": "scansione_non_quadra",
                             "misura": _rep.get("misura"), "fonte_testo": "tabelle_mineru"})
                    _snello = _risultato_snello
                    _snello_report = _snello.report
                    if _pdf_mineru is not None:
                        _snello_report["fonte_testo"] = "tabelle_mineru"
                    balance_sheet_data, income_data = _bs_snello, _ce_snello
                    prior_bs_data, prior_ce_data = _prior_bs_snello, _prior_ce_snello
                except import_snello.SnelloNonRiuscito as exc:
                    _snello = None
                    _snello_report = exc.report
                except Exception as exc:  # l'importatore e' un'economia: senza, l'import di oggi
                    _snello = None
                    logger.warning("Import snello non riuscito (%s): importatore attuale", type(exc).__name__)
                    _snello_report = {"esito": "ripiego", "fase": "eccezione", "errore": type(exc).__name__}

        # Fase 4: lo snello cede qui al classico (o non e' stato tentato). Il motivo si dichiara
        # sempre, anche quando il classico non gira; con IMPORT_RIPIEGO_CLASSICO=0 un documento
        # non adottato dallo snello esce con un errore chiaro, prima di salvare qualunque cosa.
        _ripiego_classico = {"usato": _snello is None, "motivo": None}
        if _snello is None:
            _ripiego_classico["motivo"] = _motivo_ripiego_classico(
                _snello_report if _motore_snello() else None)
            if _motore_snello() and not _ripiego_classico_acceso():
                raise PDFImportError(
                    "Import non riuscito: percorso classico spento (IMPORT_RIPIEGO_CLASSICO=0) "
                    f"e l'importatore non ha adottato il documento ({_ripiego_classico['motivo']}).")
        if _snello_report is not None:
            _snello_report["ripiego_classico"] = _ripiego_classico
        _snello_report_dichiarato = (
            _snello_report if _snello_report is not None else {"ripiego_classico": _ripiego_classico})

        # Detect an explicitly contradictory legal statement before choosing an
        # extractor — but never reject it. Task 17 (decisione del proprietario,
        # 2026-09-27): «se il bilancio non e' quadrato deve essere comunque importato
        # con avviso, l'utente lo correggera' nella tab rettifiche», e questo vale
        # anche per un documento che contraddice i propri stessi totali stampati.
        # Prima di questa decisione un mismatch Attivo/Passivo dichiarato bloccava
        # l'import qui (PDFImportError, prima ancora di scegliere un estrattore); ora
        # il controllo resta (le stesse "immutable source controls" del commento
        # originale: nessun estrattore o plug puo' nascondere la contraddizione), ma
        # produce solo un avviso dichiarato — l'estrazione prosegue con le regole di
        # sempre e, se produce un bilancio importabile, si salva con questo avviso in
        # testa (vedi piu' sotto, dove ``unbalanced_reason`` viene costruito).
        _declared_totals_warning: Optional[str] = None
        if classification.route == ROUTE_IVCEE and not is_scanned and not _ocr_source:
            _declared_totals_warning = _declared_totals_contradiction(file_path, sample_text)
            if _declared_totals_warning:
                logger.warning(_declared_totals_warning)

        _macro_report = {}

        def _llm_extract():
            """IV CEE extraction via LLM. Returns (bs, ce, prior_bs, prior_ce)."""
            nonlocal _macro_report
            # "Situazione contabile riclassificata dettagliata" (BILAQ, detail_riclass,
            # Santini): lo schema di legge col percorso nell'etichetta, letto per percorso e
            # verificato su ogni totale stampato, dalle tabelle MinerU di una scansione o dal
            # testo del PDF. Prima di qualunque modello: su questa famiglia il modello prendeva
            # sotto-righe per totali ("B.6.2) Materie prime" per B.6), contava due volte i
            # crediti oltre 12 mesi e perdeva i debiti verso il gruppo. Si adotta solo se
            # passa gli stessi cancelli degli altri lettori deterministici.
            if extraction_context is None:
                try:
                    adottato = _xbrl_reso_extract(file_path)
                except Exception as reso_err:
                    adottato = None
                    logger.info("PDF reso da XBRL non letto (%s: %s)", type(reso_err).__name__, reso_err)
                if adottato is not None:
                    return adottato
            try:
                adottato = _schema_etichette_extract(file_path, extraction_context)
            except Exception as etichette_err:
                adottato = None
                logger.info("Schema con percorso nell'etichetta non letto (%s: %s)",
                            type(etichette_err).__name__, etichette_err)
            if adottato is not None:
                return adottato
            if extraction_context is not None:
                for lettore in (_schema_generico_mineru_extract, _prospetto_sintetico_mineru_extract):
                    try:
                        adottato = lettore(extraction_context)
                    except Exception as lettore_err:
                        adottato = None
                        logger.info("%s non letto (%s: %s)", lettore.__name__,
                                    type(lettore_err).__name__, lettore_err)
                    if adottato is not None:
                        return adottato
            # /import/pdf-ocr supplies structured MinerU table rows.  Build an
            # evidence-only IV-CEE candidate from those rows before touching the
            # original PDF.  It is accepted only through the same structural and
            # accounting gates as every other extractor; an incomplete or
            # ambiguous OCR mapping simply declines and the established source
            # parser / LLM fallbacks continue.
            if extraction_context is not None:
                try:
                    from importers.iv_cee_hierarchy import check_quadratura
                    from importers.mineru_adapter import extract_ivcee_candidate

                    mineru_candidate = extract_ivcee_candidate(extraction_context)
                    if mineru_candidate is not None:
                        mineru_q = check_quadratura(
                            mineru_candidate.current_bs,
                            mineru_candidate.current_ce,
                            tol=Decimal("2"),
                        )
                        if mapper.validate_balance(mineru_candidate.current_bs) and mineru_q.quadra:
                            prior_ok = False
                            if mineru_candidate.prior_bs and mineru_candidate.prior_ce is not None:
                                prior_q = check_quadratura(
                                    mineru_candidate.prior_bs,
                                    mineru_candidate.prior_ce,
                                    tol=Decimal("2"),
                                )
                                prior_ok = (
                                    mapper.validate_balance(mineru_candidate.prior_bs)
                                    and prior_q.quadra
                                )
                            logger.info(
                                "Using source-validated MinerU IV-CEE tables "
                                "(fields=%d unresolved=%d prior_valid=%s)",
                                mineru_candidate.source_detail_fields,
                                len(mineru_candidate.unresolved_rows),
                                prior_ok,
                            )
                            return (
                                mineru_candidate.current_bs,
                                mineru_candidate.current_ce,
                                mineru_candidate.prior_bs if prior_ok else None,
                                mineru_candidate.prior_ce if prior_ok else None,
                            )
                        logger.info(
                            "Structured MinerU IV-CEE candidate declined by accounting gates: %s",
                            "; ".join(mineru_q.warnings) or "structural balance mismatch",
                        )
                except Exception as mineru_err:
                    logger.info(
                        "Structured MinerU IV-CEE extraction declined (%s: %s)",
                        type(mineru_err).__name__,
                        mineru_err,
                    )

            # A regular comparative legal IV-CEE export has enough independent
            # source controls to be read deterministically: each section exposes
            # its own subtotal and both sides close to printed totals. Prefer that
            # evidence-backed path before requiring an API call. It returns data
            # only when SP, CE and CE↔SP all cross-foot; incomplete/ambiguous
            # layouts decline and continue through the established LLM route.
            # The deterministic source path also supports clean infrannual
            # monocolumn statements. A prior-year column is optional, never required.
            try:
                from importers.iv_cee_hierarchy import check_quadratura
                from importers.standard_ivcee_parser import (
                    extract_standard_ivcee_balances,
                    extract_standard_ivcee_income,
                )

                source_bs, source_prior_bs = extract_standard_ivcee_balances(
                    file_path
                )
                source_ce, source_prior_ce = extract_standard_ivcee_income(
                    file_path
                )
                if source_bs is not None and source_ce is not None:
                    source_q = check_quadratura(
                        source_bs, source_ce, tol=Decimal("2")
                    )
                    if mapper.validate_balance(source_bs) and source_q.quadra:
                        prior_ok = False
                        if source_prior_bs is not None and source_prior_ce is not None:
                            prior_q = check_quadratura(
                                source_prior_bs,
                                source_prior_ce,
                                tol=Decimal("2"),
                            )
                            prior_ok = (
                                mapper.validate_balance(source_prior_bs)
                                and prior_q.quadra
                            )
                        logger.info(
                            "Using deterministic source-validated IV-CEE "
                            "extraction (prior_valid=%s)",
                            prior_ok,
                        )
                        return (
                            source_bs,
                            source_ce,
                            source_prior_bs if prior_ok else None,
                            source_prior_ce if prior_ok else None,
                        )
            except Exception as source_err:
                logger.info(
                    "Deterministic legal IV-CEE extraction declined (%s: %s)",
                    type(source_err).__name__,
                    source_err,
                )

            if not _ivcee_attivo(api_key):
                raise PDFImportError(_modello_non_disponibile(
                    "ANTHROPIC_API_KEY is required for PDF import"))
            if not is_trial_balance and not is_scanned and not _ocr_source:
                # Prefer source-verified macros, but incomplete coverage must not
                # prevent importing. The existing extractor recovers the base;
                # finalization assigns unexplained detail to residual accounts.
                from importers.macro_analysis import analyze_pdf_macros, MacroAnalysisError
                from importers.standard_ivcee_parser import has_comparative_ivcee_columns
                try:
                    bs, ce, prior_bs, prior_ce, _macro_report = analyze_pdf_macros(
                        file_path,
                        include_prior=not period_months and has_comparative_ivcee_columns(file_path),
                    )
                except MacroAnalysisError as exc:
                    warning = (
                        'MACROVOCI DA VERIFICARE: lettura incompleta; importazione '
                        'proseguita con estrazione alternativa e conti residuali. '
                        'Verificare le voci segnalate in Rettifiche.'
                    )
                    _macro_report = {**exc.report, 'fallback_used': True,
                                     'warnings': [*exc.report.get('warnings', []), warning]}
                    sc_quadratura_warnings.append(warning)
                    logger.warning('%s Diagnosi: %s', warning, exc.report.get('errors', []))
                else:
                    return bs, ce, prior_bs, prior_ce
            logger.info("Using LLM extraction (ANTHROPIC_API_KEY found)")
            from importers.pdf_extractor_llm import (
                extract_pdf_with_llm, extract_pdf_both_years_with_llm,
            )
            # A prior year is optional. Use the dual prompt only when the source
            # physically proves two date columns; a monocolumn partial statement
            # must use the single-year extractor and return no fabricated prior.
            from importers.standard_ivcee_parser import has_comparative_ivcee_columns

            if period_months and not has_comparative_ivcee_columns(file_path):
                logger.info(
                    f"Single-year infrannual extraction (period_months={period_months}; "
                    "no prior column detected)"
                )
                bs, ce = extract_pdf_with_llm(file_path, force_llm=True)
                _rifiuta_passivo_non_letto(bs)
                return bs, ce, None, None

            # Da qui in giu' passano SIA il budget annuale SIA l'infrannuale comparato
            # (#50). L'infrannuale comparato tornava direttamente dal prompt a due anni,
            # cioe' senza la mitigazione descritta qui sotto: dopo #27 quei file hanno
            # cominciato ad arrivarci, e una riga di CE persa sull'anno corrente usciva
            # dove prima usciva intera. Un percorso solo, perche' un secondo percorso
            # ri-diverge alla prima modifica del primo.
            #
            # Take the CURRENT year from the proven single-year extractor
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
            from importers.iv_cee_hierarchy import rollup_debiti_aggregates

            def _balances(d):
                return bool(d) and mapper.validate_balance(rollup_debiti_aggregates(d))

            _letture_sp: list = []   # le letture SP dell'ultimo tentativo (un anno, due anni)

            def _attempt():
                """One extraction pass: single-year current + dual pass for the prior,
                falling back to the dual-pass current when the single-year one does not
                balance (dense 4-column layouts trip the single-year prompt) or when it
                turns out to have read the COMPARATIVE column instead of the current one
                (infrannuale: the two columns are not homogeneous, 9 months against 12)."""
                bs, ce = extract_pdf_with_llm(file_path, force_llm=True)
                prior_bs = prior_ce = None
                read_comparative = False
                _letture_sp.clear()
                _letture_sp.append(bs)
                try:
                    dual_bs, dual_ce, prior_bs, prior_ce = extract_pdf_both_years_with_llm(file_path)
                    _letture_sp.append(dual_bs)
                    if _single_year_read_prior_column(bs, dual_bs, prior_bs):
                        # Quadrerebbe lo stesso: e' l'anno sbagliato, non un foglio rotto.
                        read_comparative = True
                        logger.warning(
                            "Single-year current extraction coincides with the "
                            "comparative column: it read the wrong column; using the "
                            "dual-pass current year"
                        )
                        bs, ce = dual_bs, dual_ce
                    elif not _balances(bs) and _balances(dual_bs):
                        logger.info(
                            "Single-year current extraction is unbalanced; using the "
                            "dual-pass current year (it balances)"
                        )
                        bs, ce = dual_bs, dual_ce
                except Exception as prior_err:
                    logger.warning(
                        f"Prior-year dual extraction failed ({type(prior_err).__name__}: "
                        f"{prior_err}); importing current year only"
                    )
                # Dichiarata SEMPRE, anche a zero: a valle una chiave assente vale zero,
                # quindi tacere equivarrebbe a dichiararsi puliti.
                if bs is not None:
                    bs["_single_year_read_comparative"] = (
                        Decimal("1") if read_comparative else Decimal("0")
                    )
                return bs, ce, prior_bs, prior_ce

            # The Haiku extractor is stochastic on this schema: a dense 4-column bilancio
            # (2025/2024/DIFFERENZA/SCOST.%) misreads a debiti line on a minority of runs,
            # unbalancing the year. Retry until BOTH the current and any prior year balance
            # (keeping the best attempt so far), which turns an ~80%/pass success into
            # near-certainty. Bounded and only re-runs while a year still fails; PDF import
            # is infrequent so the extra Haiku calls are acceptable.
            best = None
            for attempt in range(3):
                bs, ce, prior_bs_data, prior_ce_data = _attempt()
                current_ok = _balances(bs)
                prior_ok = _balances(prior_bs_data) or not prior_bs_data
                if best is None or (current_ok and not _balances(best[0])):
                    best = (bs, ce, prior_bs_data, prior_ce_data)
                if current_ok and prior_ok:
                    best = (bs, ce, prior_bs_data, prior_ce_data)
                    break
                # La riprova serve contro una lettura sbilanciata, non contro un prospetto che
                # non c'e': se il tentativo ha letto uno SP vuoto (Attivo = Passivo = 0, sia la
                # lettura a un anno sia quella a due) altri due giri danno lo stesso vuoto, a
                # quattro chiamate l'uno (budget_1667: dieci minuti prima dello stesso rifiuto).
                try:
                    from importers.iv_cee_hierarchy import check_quadratura
                    _sp_vuoto = len(_letture_sp) == 2 and all(
                        (not letto) or check_quadratura(letto).is_empty for letto in _letture_sp)
                except Exception:
                    _sp_vuoto = False
                if _sp_vuoto:
                    logger.info(
                        f"Extraction attempt {attempt + 1}: empty balance sheet; "
                        "not retrying (nothing to re-read)"
                    )
                    break
                logger.info(
                    f"Extraction attempt {attempt + 1}: current_balances={current_ok}, "
                    f"prior_balances={prior_ok}; retrying" if attempt < 2 else
                    f"Extraction attempt {attempt + 1}: current_balances={current_ok}, "
                    f"prior_balances={prior_ok}; keeping best attempt"
                )

            # Clean comparative legal IV-CEE exports expose every aggregate and
            # both side totals at fixed source coordinates.  If all stochastic
            # attempts are still unbalanced, overlay those printed aggregates only
            # when their independent section cross-foots reconcile exactly.  This
            # is a source-backed fallback, not a plug: an incomplete/ambiguous PDF
            # makes the deterministic parser return None and leaves ``best`` alone.
            if best is not None and not _balances(best[0]):
                try:
                    from importers.standard_ivcee_parser import (
                        extract_standard_ivcee_balances,
                        extract_standard_ivcee_income,
                        overlay_standard_ivcee_balance,
                    )

                    source_current, source_prior = extract_standard_ivcee_balances(
                        file_path
                    )
                    source_current_ce, source_prior_ce = extract_standard_ivcee_income(
                        file_path
                    )
                    source_bs = overlay_standard_ivcee_balance(best[0], source_current)
                    source_prior_bs = overlay_standard_ivcee_balance(
                        best[2] or {}, source_prior
                    )
                    if source_current is not None and _balances(source_bs):
                        logger.warning(
                            "LLM IV-CEE current extraction unbalanced; using "
                            "source-validated legal subtotals"
                        )
                        # Keep the independently extracted CE and every typed
                        # detail field; overwrite only the fully cross-footed legal
                        # SP aggregates/totals returned by the source parser.
                        source_ce = dict(best[1])
                        if source_current_ce is not None:
                            source_ce.update(source_current_ce)
                        source_prior_income = dict(best[3] or {})
                        if source_prior_ce is not None:
                            source_prior_income.update(source_prior_ce)
                        best = (
                            source_bs,
                            source_ce,
                            source_prior_bs if source_prior is not None else best[2],
                            source_prior_income if source_prior_ce is not None else best[3],
                        )
                except Exception as source_err:
                    logger.info(
                        "Deterministic legal IV-CEE fallback declined (%s: %s)",
                        type(source_err).__name__, source_err,
                    )
            if best is not None:
                _rifiuta_passivo_non_letto(best[0])
            return best

        sc_quadratura_warnings = []
        # Corrupted (not merely absent) text layer — broken ToUnicode font map
        # (budget_337: "3.239 , 12", "roNDO AMM.TO"): every extractor (text AND
        # vision, both tried) is unreliable on these files. Import proceeds
        # best-effort, but the user MUST know that every value needs review — and,
        # crucially, the DECLARED control totals read from garbled text are garbage
        # too, so they must NOT drive anything (candidate selection, sp13
        # anchoring, CE alignment): a misread "perdita 372.733" (the CE section
        # total) used to flip a profitable company into a huge loss.
        _text_garbled = False
        try:
            from importers.pdf_extractor_llm import _text_layer_is_garbled
            if not is_scanned and _text_layer_is_garbled(sample_text):
                _text_garbled = True
                sc_quadratura_warnings.append(
                    "TESTO PDF CORROTTO (mappa font danneggiata): l'estrazione è "
                    "inaffidabile — verificare TUTTI i valori in Rettifiche"
                )
                logger.warning("Garbled text layer detected — declared totals "
                               "will be IGNORED; flagged for Rettifiche")
        except Exception:
            pass
        _coge_ok = False
        # letta dalle tabelle MinerU (mineru_contrapposte): dalla route C, o dallo snello sul
        # PDF sintetico (allora i dettagli sono gia' celle lette, nessun passaggio dei dettagli)
        _mineru_tabelle = _snello is not None and _pdf_mineru is not None
        # Sezioni riscattate in vision (route C). Inizializzata QUI, fuori da ogni
        # ramo: il blocco del parser_version la legge su OGNI route, mentre
        # l'assegnazione vive dentro `if candidates:` — una route A/B solleverebbe
        # NameError.
        _rescued_sections = []
        # Motivi del cancello per sezione tentata (accettata o no): provenienza
        # persistita nel validation_report. Inizializzata QUI per la stessa ragione
        # di _rescued_sections — il blocco che la legge sta fuori da `if candidates:`.
        _rescue_reasons: Dict[str, str] = {}
        # Independent source proofs precede candidate scoring. A balanced LLM
        # hypothesis is not sufficient when printed families contradict it.
        from importers.source_reconciliation import extract_source_candidates, apply_source_candidate
        _source_candidates = []
        _source_reports = {}
        try:
            # Un risultato snello adottato ha gia' fatto la propria verifica: rileggere
            # le fonti (ledger_evidence su gx10) costava fino a 10 minuti per file.
            if not is_scanned and not _ocr_source and _snello is None:
                _source_candidates = extract_source_candidates(file_path)
        except Exception as source_err:
            logger.warning("Source cross-foot unavailable: %s", source_err)
        _source_complete = bool(_source_candidates and _source_candidates[0][0] is not None
                                and _source_candidates[0][1] is not None)
        if _source_complete and _snello is None:
            # Un risultato snello gia' quadrato non va scavalcato da un candidato
            # indipendente: _snello is None e' l'unico caso in cui questo blocco
            # puo' sovrascrivere balance_sheet_data/income_data.
            balance_sheet_data, income_data = map(dict, _source_candidates[0][:2])
            prior_bs_data = prior_ce_data = None
            if len(_source_candidates) > 1 and all(v is not None for v in _source_candidates[1][:2]):
                prior_bs_data, prior_ce_data = map(dict, _source_candidates[1][:2])
            logger.info("Using independently cross-footed source SP and CE")
        if is_trial_balance and not _source_complete and _snello is None:
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

            # Scansione letta da MinerU (decisione del proprietario, 2026-10-14): se le sue
            # tabelle hanno la forma di una situazione a sezioni contrapposte, il lettore
            # deterministico legge un PDF sintetico stampato da quelle celle e il pass CoGe
            # su Qwen non si chiama (Unicarton 31/08/2026: al centesimo in pochi secondi,
            # contro 8,5 minuti e 315 mila di sbilancio). Qwen resta solo quando le tabelle
            # non hanno quella forma.
            # (il PDF sintetico, se c'e', l'ha gia' stampato il blocco prima dello snello)

            # A locally recognised verifica-segno has already been parsed from
            # source coordinates and self-validates against independent SP/CE
            # controls.  Do not let the presence of an API key add a stochastic
            # plain-text OCR candidate that has lost the two-column geometry.
            if _coge_attivo(api_key) and not local_coordinate_ocr and _pdf_mineru is None:
                try:
                    from importers.pdf_extractor_llm import extract_trial_balance_with_llm
                    # On a scanned PDF, pass the OCR text so the extractor uses the
                    # reliable text path instead of re-doing vision (which misreads
                    # Italian-formatted numbers on noisy scans).
                    coge_bs, coge_ce = extract_trial_balance_with_llm(file_path, ocr_text=ocr_text)
                    r = _residual_of(coge_bs, coge_ce)
                    if r is not None:
                        candidates.append((r, coge_bs, coge_ce, "CoGe-LLM"))
                except Exception as coge_err:
                    logger.warning(
                        f"Route C: CoGe LLM extractor failed "
                        f"({type(coge_err).__name__}: {coge_err})"
                    )

            sc_prior_bs = sc_prior_ce = None
            try:
                # Dual-year trial balances (e.g. budget_131/132 Oprandi) carry the
                # prior-year saldo in a second column. Capture it from the deterministic
                # parser so the prior FinancialYear is created downstream (Step 7) —
                # the CoGe LLM pass is single-year, so the deterministic dual read is
                # the source of the prior column regardless of which current-year
                # candidate wins.
                _mineru_deterministic_text = (
                    getattr(extraction_context, "deterministic_text", None)
                    if extraction_context is not None
                    else None
                )
                if _pdf_mineru is not None:
                    sc_bs, sc_ce, sc_prior_bs, sc_prior_ce = extract_situazione_contabile(
                        _pdf_mineru, return_prior=True)
                else:
                    sc_bs, sc_ce, sc_prior_bs, sc_prior_ce = extract_situazione_contabile(
                        file_path,
                        return_prior=True,
                        text_override=_mineru_deterministic_text,
                    )
                sc_bs_mapped = _map_sc_keys(sc_bs)   # short keys (sp03) -> full DB names
                sc_ce_mapped = _map_sc_keys(sc_ce)
                r = _residual_of(sc_bs_mapped, sc_ce_mapped)
                if r is not None:
                    candidates.append((r, sc_bs_mapped, sc_ce_mapped, "deterministico"))
                    _mineru_tabelle = _pdf_mineru is not None
            except Exception as sc_err:
                logger.warning(
                    f"Route C: deterministic SC parser failed "
                    f"({type(sc_err).__name__}: {sc_err})"
                )

            # Prior-year column (dual-year trial balance) → prior FinancialYear.
            # Mapped to full DB field names; written by the generic Step-7 path.
            if sc_prior_bs and sc_prior_ce:
                prior_bs_data = _map_sc_keys(sc_prior_bs)
                prior_ce_data = _map_sc_keys(sc_prior_ce)

            if candidates:
                # Pick the more COMPLETE extractor. `_plug_residual` alone is BLIND to
                # under-extraction: the CoGe LLM can stochastically DROP a block of accounts
                # and then force-balance via sp13 (residual ~0 → looks clean) while its total
                # falls well short of the printed TOTALE (AITEC PROVVISORIO: CoGe 9.92M vs the
                # declared 12.65M). The deterministic parser anchors to that printed total, so
                # score PRIMARILY by the gap to the declared control total and use the residual
                # only as the tiebreaker.
                _decl_tot = None
                _dc0 = {}
                try:
                    from importers.pdf_extractor_llm import _declared_control_totals
                    if not _text_garbled:   # garbled text -> declared is garbage
                        _dc0 = (_declared_control_totals(_pdf_mineru) if _pdf_mineru
                                else _declared_control_totals(file_path, text=ocr_text))
                    _decl_tot = (_dc0.get('pareggio') or _dc0.get('passivo')
                                 or _dc0.get('attivo'))
                except Exception:
                    _decl_tot = None
                # See the NOTE at the top of the function: _dc0 has no
                # 'patrimonio_netto' key, so this only feeds the immobilizzazioni /
                # debiti_banche limbs of reliability.assess; PN stays DERIVED.
                _declared_for_reliability = _dc0

                # On GROSS-presentation trial balances the declared pareggio includes the
                # fondi ammortamento (contra-assets on both sides) and the perdita parked on
                # the attivo side, so it OVERSTATES the net IV-CEE total. Scoring the net
                # candidates against that gross anchor penalises the candidate that correctly
                # netted the fondi (deterministic parser: net 1.22M vs gross pareggio 2.16M),
                # letting a worse, un-netted LLM candidate win (budget_343/348). Reduce the
                # anchor by the scanned contra mass + declared perdita so the gap targets the
                # NET total. No-op when there is no contra mass (already-net sheets: anchor
                # unchanged, AITEC-style under-extraction guard preserved).
                #
                # contra_scan_mass partitions the scan by RECONCILIATION against
                # the document's own printed total, exactly as net_contra_accounts
                # does, and never by code prefixes: AGO's 8-digit mastri and
                # 9-digit sub-accounts are not prefixes of each other, so the
                # historical prefix dedup summed BOTH levels and over-read the
                # fondi (+393.916,50 on 613_2024). Over-reading here understates
                # the anchor, which is what CHOOSES between the CoGe-LLM and the
                # deterministic candidate — i.e. it can persist different data.
                if _decl_tot and _decl_tot > 0:
                    try:
                        from importers.situazione_contabile_parser import contra_scan_mass
                        _fondi, _iva = contra_scan_mass(
                            _pdf_mineru or file_path,
                            text=None if _pdf_mineru else ocr_text, declared=_dc0)
                        if _fondi > _decl_tot * Decimal('0.01'):
                            _perdita = _dc0.get('perdita') or Decimal('0')
                            _decl_tot = _decl_tot - _fondi - _iva - _perdita
                    except Exception:
                        pass

                def _completeness_gap(bs):
                    """Distance of a candidate's total from the declared control total.
                    0 when the declared total is unknown or the gap is sub-2% noise — so a
                    tiny declared-parse difference never overrides the residual tiebreaker."""
                    if not _decl_tot or _decl_tot <= 0:
                        return Decimal('0')
                    gap = abs(_decl_tot - bs.get('totale_attivo', Decimal('0')))
                    return gap if gap > _decl_tot * Decimal('0.02') else Decimal('0')

                candidates.sort(key=lambda c: (_completeness_gap(c[1]), c[0]))
                residual, balance_sheet_data, income_data, source = candidates[0]
                _coge_ok = True
                # Debt-typing overlay: the LLM is strong on totals but can dump the whole
                # debt mass into 'altri' (sp16g/sp17g). The deterministic parser types each
                # line via _debt_type (banche/fornitori/tributari/...). When the LLM wins but
                # its debt split is degenerate, graft the deterministic candidate's typed
                # proportions onto it — total preserved, only the split is corrected. No-op
                # when the winner is the deterministic parser or already well-typed.
                if source != "deterministico":
                    _det = next((c for c in candidates if c[3] == "deterministico"), None)
                    if _det is not None:
                        from importers.situazione_contabile_parser import overlay_debt_typing
                        balance_sheet_data = overlay_debt_typing(balance_sheet_data, _det[1])
                # Contra-netting overlay (spec 2026-07-06): deterministic post-
                # extraction netting of fondi ammortamento (+ conservative IVA
                # offset) on the CHOSEN candidate, whatever extractor produced it.
                # No-op unless the scan self-validates against the declared gross
                # total; _contra also reduces the declared anchor below, because
                # the document's printed totals are GROSS on these files.
                _contra = Decimal('0')
                try:
                    from importers.situazione_contabile_parser import net_contra_accounts
                    balance_sheet_data, _contra = net_contra_accounts(
                        balance_sheet_data, _pdf_mineru or file_path,
                        text=None if _pdf_mineru else ocr_text, declared=_dc0)
                    if _contra > 0:
                        logger.info(f"Route C: contra-netting applicato "
                                    f"({_contra:,.0f} fondi ammortamento/IVA)")
                        # Never clear a pre-existing unexplained difference here.
                        # Netting can correct documented contra-assets, but it cannot
                        # prove that every other unclassified row has been recovered.
                except Exception as _cn_err:
                    logger.warning(f"Route C: contra-netting saltato: {_cn_err}")
                # Compare the chosen candidate with the declared result. Only an
                # omitted sp13 independently confirmed by the printed result, CE
                # and SP gap can be recovered; CE↔SP remains diagnostic.
                # A parser that already produced an exact, self-balanced sheet (e.g. the
                # by-sign verifica parser) flags itself authoritative: skip the declared
                # reconcile, which would mis-anchor sp13 to a prior-year result account.
                _authoritative = balance_sheet_data.pop('_skip_declared_reconcile', False)
                if not _authoritative:
                    try:
                        from importers.pdf_extractor_llm import _reconcile_trial_to_declared
                        from importers.iv_cee_hierarchy import _net_profit_from_ce
                        _decl = dict(_dc0)
                        # The printed totals are GROSS on gross-presentation files:
                        # anchor the reconcile to the NET total so it does not
                        # re-inflate the netted mass as a false plug. net_contra
                        # (best-effort/CoGe path) exposes the netted mass as _contra;
                        # the DEPI/AGO/single-column build_iv_cee path nets fondi
                        # internally and exposes _netted_contra. Prefer _contra when
                        # net_contra acted (it also overwrote sp02/sp03), else fall
                        # back to build_iv_cee's — never both (same fondi).
                        _anchor_cut = _contra if _contra > 0 else balance_sheet_data.get(
                            '_netted_contra', Decimal('0'))
                        if _anchor_cut > 0:
                            for _k in ('attivo', 'passivo', 'pareggio'):
                                if _decl.get(_k):
                                    _decl[_k] = _decl[_k] - _anchor_cut
                        # CE-derived result: fallback arbiter when a spurious PN
                        # "RISULTATO D'ESERCIZIO" is read as declared utile but the
                        # true result is a perdita (budget_211).
                        try:
                            _ce_res = _net_profit_from_ce(income_data)
                        except Exception:
                            _ce_res = None
                        balance_sheet_data = _reconcile_trial_to_declared(
                            balance_sheet_data, _decl, source, ce_result=_ce_res)
                        residual = balance_sheet_data.get('_plug_residual', residual)
                    except Exception as _rc_err:
                        logger.warning(f"Route C: declared-result reconcile skipped: {_rc_err}")
                # Riscatto vision (spec 2026-08-14): il foglio FINITO non quadra ma il
                # numero giusto e' stampato sulla pagina — e' il text layer a non
                # arrivarci. Rilegge in vision le sole pagine della sezione che non
                # torna. La posizione in coda alla catena e' deliberata: prima del
                # netting il riscatto scatterebbe su un attivo ancora lordo.
                # Senza chiave non si parte nemmeno: render_section_images gira PRIMA di
                # istanziare il client dentro read_section, quindi un'installazione senza
                # chiave renderizzerebbe le pagine a 200 DPI per poi buttarle. Sulle tabelle
                # MinerU niente modello: gli importi sono gia' quelli delle celle.
                if api_key and _pdf_mineru is None:
                    try:
                        _donor = next(
                            (c[1] for c in candidates if c[3] == "deterministico"), None)
                        (balance_sheet_data, income_data, _rescued_sections,
                         _rescue_reasons) = _apply_vision_rescue(
                            file_path, balance_sheet_data, income_data,
                            declared=_dc0, donor_bs=_donor, ocr_text=ocr_text)
                        if _rescued_sections:
                            residual = balance_sheet_data.get('_plug_residual', residual)
                            source = f"{source}+vision({'+'.join(_rescued_sections)})"
                    except Exception as _vr_err:
                        logger.warning(f"Route C: riscatto vision saltato: {_vr_err}")
                others = ", ".join(f"{s}={_it_amount(r)}" for r, _b, _c, s in candidates)
                logger.info(f"Route C: scelto estrattore '{source}' (residuo minore "
                            f"{_it_amount(residual)}); candidati: {others}")
                # Surface the residual as a NON-blocking flag (never reject): a large residual
                # means part of the source mass was not classified into any IV-CEE field, so the
                # composition is partly unexplained — refined in Rettifiche. The statement is
                # left exactly as extracted: nothing is plugged into cash or debt to absorb it.
                _tot = balance_sheet_data.get('totale_attivo', Decimal('0')) or Decimal('1')
                if residual > Decimal('1'):
                    _pct = 100 * residual / _tot
                    _sev = ("prevalentemente stimata"
                            if residual > SC_PLUG_REJECT_PCT * _tot else "parziale")
                    sc_quadratura_warnings.append(
                        f"BILANCIO NON QUADRATO ({_sev}): residuo {_it_amount(residual)} "
                        f"({_pct:.0f}% del totale) non classificato in alcuna voce — "
                        f"correggere in Rettifiche"
                    )
            elif not _ivcee_attivo(api_key):
                raise PDFImportError(_modello_non_disponibile(
                    "Impossibile estrarre la situazione contabile (nessun dato) "
                    "e ANTHROPIC_API_KEY non impostata."
                ))
            else:
                # both extractors empty → IV-CEE LLM as a genuine last resort
                logger.warning("Route C: entrambi gli estrattori vuoti; "
                               "ultimo tentativo con l'estrattore IV-CEE LLM")
                (balance_sheet_data, income_data,
                 prior_bs_data, prior_ce_data) = _extract_route_c_last_resort(
                    _llm_extract
                )
        if not is_trial_balance and not _source_complete and _snello is None:
            # IV CEE format (routes A/B) — use LLM extraction
            balance_sheet_data, income_data, prior_bs_data, prior_ce_data = _llm_extract()
            # Debiti aggregates (sp16/sp17) are schema-derived totals with no source
            # line, so align them to their extracted sub-details before any balancing:
            # the LLM can emit an aggregate that drifts from its own detail lines,
            # unbalancing an otherwise-tying year (budget_585 prior 2024 was dropped
            # for this). Applied to BOTH years so a comparative bilancio imports both.
            from importers.iv_cee_hierarchy import rollup_debiti_aggregates
            balance_sheet_data = rollup_debiti_aggregates(balance_sheet_data)
            if prior_bs_data:
                prior_bs_data = rollup_debiti_aggregates(prior_bs_data)
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

        # Source-proved parents and typed partitions replace stale hypotheses,
        # even if those hypotheses balanced. Do not retain old specific fields
        # or balancing-plug metadata alongside the new source statement.
        _macros_verified = _macro_report.get('status') == 'verified'
        if _source_candidates and not _macros_verified:
            balance_sheet_data, income_data, _source_reports['current'] = apply_source_candidate(
                balance_sheet_data, income_data, _source_candidates[0])
            if _source_candidates[0][0] is not None and not _source_complete:
                sc_quadratura_warnings = []  # diagnostics of the discarded SP candidate
                _declared_for_reliability = None
            if len(_source_candidates) > 1 and prior_bs_data:
                prior_bs_data, prior_ce_data, _source_reports['prior'] = apply_source_candidate(
                    prior_bs_data, prior_ce_data, _source_candidates[1])
        _source_current = _source_reports.get('current', {})
        if _macros_verified:
            # The macro candidate was independently cross-footed. Do not let a
            # declined source-layout reader demote it, or CE sign helpers modify it.
            _source_current = _macro_report
            _source_reports['current'] = _macro_report
            if prior_bs_data:
                _source_reports['prior'] = _macro_report.get('prior', {})
            elif _macro_report.get('prior', {}).get('status') == 'incomplete':
                sc_quadratura_warnings.append(
                    'ANNO PRECEDENTE NON IMPORTATO: macrovoci del comparativo non riconciliate. '
                    + '; '.join(_macro_report['prior'].get('errors', [])))
        _source_review = bool(_source_current.get('requires_review'))
        if _source_current.get('status') == 'verified' and not _source_current.get('income_verified'):
            _source_review = True
            _source_current['requires_review'] = True
        if _source_review:
            sc_quadratura_warnings.append(
                "CONTROLLO DELLA FONTE DA VERIFICARE: " + '; '.join(_source_current.get('errors') or _source_current.get('warnings') or [
                    'SP riconciliato, conto economico non verificato integralmente sul documento'])
            )

        # A balanced extraction can still be analytically empty. Re-read source
        # details AFTER candidate selection/netting, independently of its route.
        # Details preserve each aggregate; the separate ledger maturity policy
        # may move short/long portions but preserves combined credits/debts.
        # Controls, CE and period results cannot be changed by the LLM.
        from importers.detail_enrichment import enrich_pdf_details
        _salta_dettagli = _dettagli_gia_letti(
            _snello.report if _snello is not None else None, _mineru_tabelle,
            extraction_context is not None, balance_sheet_data)
        if _salta_dettagli:
            _detail_report = {"status": "skipped", "reason": _salta_dettagli, "warnings": []}
        else:
            balance_sheet_data, prior_bs_data, _detail_report = enrich_pdf_details(
                file_path, balance_sheet_data, prior_bs_data, fiscal_year=fiscal_year,
                ocr_text=ocr_text,
                pagine=(_snello.struttura.pagine_dettagli()
                        if _snello is not None
                        and _snello.report.get("modo") in ("legge", "legge_con_dettaglio") else None),
                usa_llm=not (_snello is not None and _snello.report.get("modo") == "conti"),
            )
        sc_quadratura_warnings.extend(_detail_report.get('warnings', []))
        _approssimati = (
            sorted({x['campo'] for x in _snello.report['approssimazioni']})
            if _snello is not None and _snello.report.get('approssimazioni')
            else balance_sheet_data.get('_approssimazioni_prospetto'))
        if _approssimati:
            # prospetto sintetico (voci appiattite, nessun dettaglio sotto): il totale di ogni voce sta
            # nel sotto-campo convenzionale della famiglia, massa letta e non un plug - si dichiara
            sc_quadratura_warnings.append(
                'PROSPETTO SINTETICO: il documento stampa le sole voci di legge, senza dettaglio. '
                'I totali sono stati assegnati ai sotto-campi convenzionali ('
                + ', '.join(_approssimati)
                + ') - affinare le riclassifiche in Rettifiche.')
        if _snello is not None:
            sc_quadratura_warnings.extend(_avvisi_fondi_snello(_snello.report.get('diag') or {}))

        # Diagnose the CE/SP result gap for PDF routes. The helper records
        # differences, including comparisons with a declared result when present,
        # without changing accounting fields or creating a balancing entry.
        try:
            from importers.iv_cee_hierarchy import enforce_ce_sp_identity
            from importers.pdf_extractor_llm import _declared_control_totals
            # Garbled text layer -> the declared Utile/Perdita is unreliable: do not
            # let it arbitrate (a misread CE-section total flips the result sign).
            _decl_ce = (None if _text_garbled
                        else _declared_control_totals(_pdf_mineru) if _pdf_mineru
                        else _declared_control_totals(file_path, text=ocr_text))
            if not _source_review and not _source_current.get('income_verified'):
                income_data = enforce_ce_sp_identity(
                    balance_sheet_data, income_data, "import",
                    prefer="sp13", declared=_decl_ce)
            if prior_bs_data and prior_ce_data and not _source_reports.get('prior', {}).get('income_verified'):
                prior_ce_data = enforce_ce_sp_identity(
                    prior_bs_data, prior_ce_data, "import-prior", prefer="sp13")
        except Exception as _ce_sp_err:
            logger.warning(f"CE↔SP identity enforcement skipped: {_ce_sp_err}")

        # Un mastro che il lettore delle contrapposte non sa ripartire sulle sotto-voci di
        # legge (il personale di Unicarton 31/08/2026: retribuzioni e contributi INPS, tutto
        # in ce08d) lo ripartisce il modello sui conti sotto, senza toccare l'aggregato; cio'
        # che non spiega resta alla chiusura dei residui qui sotto, dichiarato come prima.
        from importers.dettaglio_dal_modello import dettaglia
        income_data, _dettaglio_report = dettaglia(income_data)
        _prior_dettaglio_report = None
        if prior_ce_data:
            prior_ce_data, _prior_dettaglio_report = dettaglia(prior_ce_data)

        # Mandatory final closure, independent of analytical reader availability,
        # accepted proposals and extraction route. This changes only residual
        # subfields, never parent totals or either statement's balance/result.
        from importers.residual_finalization import finalize_pdf_residuals
        balance_sheet_data, income_data, _residual_report = finalize_pdf_residuals(
            balance_sheet_data, income_data)
        _prior_residual_report = {}
        if prior_bs_data:
            prior_bs_data, prior_ce_data, _prior_residual_report = finalize_pdf_residuals(
                prior_bs_data, prior_ce_data)
        sc_quadratura_warnings.extend(_residual_report['warnings'])

        # Uno sbilancio che vale esattamente un risultato stampato (utile del periodo
        # mancante, o utile dell'anno prima non destinato fra i conti del patrimonio
        # netto) si chiude con quell'importo, cercato nel documento al centesimo.
        _risultato_report = None
        try:
            from importers import risultato_stampato as _rs
            _righe = _rs.righe_del_pdf(_pdf_mineru or file_path)
            if ocr_text:
                _righe += ocr_text.splitlines()
            balance_sheet_data, _risultato_report = _rs.chiudi_col_risultato_stampato(
                balance_sheet_data, income_data, _righe)
            if _risultato_report:
                logger.info(f"risultato stampato: {_risultato_report}")
        except Exception as _rs_err:
            logger.warning(f"Controllo del risultato stampato saltato: {_rs_err}")

        # Step 2: Validate balance sheet (both paths)
        logger.info("Validating balance sheet...")
        # Un documento che contraddice i propri totali stampati (gate sopra, prima della
        # scelta dell'estrattore) resta dichiarato anche se cio' che si e' riusciti a
        # estrarre poi quadra da solo: e' un difetto della fonte, non dell'estrazione, e
        # nessun estrattore o plug lo deve nascondere (Task 17).
        unbalanced_reason: Optional[str] = _declared_totals_warning
        # Un risultato snello 'squadrato' (Task 17) puo' restare oltre soglia solo sul
        # confronto coi totali STAMPATI dal documento (scarto_stampati), che
        # mapper.validate_balance non vede (guarda solo gli aggregati del foglio, non i
        # totali stampati): l'avviso va dichiarato qui, esplicitamente, prima di quel
        # controllo — non e' un nuovo cancello di quadratura, e' la stessa diagnostica
        # gia' misurata dall'importatore.
        if unbalanced_reason is None and _snello is not None and _snello.report.get("esito") == "squadrato":
            unbalanced_reason = _snello_squadrato_reason(_snello.report)
            logger.warning(unbalanced_reason)
        if not mapper.validate_balance(balance_sheet_data):
            # Cifre lette dalla vision del modello sulle immagini (schema di legge
            # scansionato), non dal testo OCR: ERREGI 30/09/2026 una volta su tre usciva con
            # 1.000 in meno sull'attivo. E' un errore di lettura correggibile, non un OCR
            # che ha perso colonne e totali.
            try:
                from importers.pdf_extractor_llm import _is_image_pdf
                _cifre_da_vision = (
                    not is_trial_balance and _snello is None
                    and not balance_sheet_data.get("_source_mineru_ivcee")
                    and not balance_sheet_data.get("_source_standard_ivcee")
                    and not balance_sheet_data.get("_source_schema_etichette")
                    and not balance_sheet_data.get("_source_xbrl_reso")
                    and not balance_sheet_data.get("_source_prospetto_sintetico")
                    and _is_image_pdf(file_path))
            except Exception:
                _cifre_da_vision = False
            _verdict = _classify_balance_failure(
                balance_sheet_data,
                is_scanned=is_scanned,
                ocr_source=bool(_ocr_source),
                is_trial_balance=is_trial_balance,
                sample_text=sample_text,
                file_path=file_path,
                ocr_text=ocr_text,
                cifre_da_vision=_cifre_da_vision,
            )
            if _verdict.hard_error:
                raise PDFImportError(_verdict.hard_error)
            # Sbilancio: si importa e si corregge in Rettifiche. forecastable
            # restera' False da solo (semantic_valid include la quadratura),
            # e _validate_forecast_source blocca comunque la proiezione.
            if unbalanced_reason is None:
                unbalanced_reason = _verdict.warning
            logger.warning(_verdict.warning)
        elif unbalanced_reason:
            logger.warning(unbalanced_reason)

        # Unified quadratura diagnostic across ALL routes (shared IV-CEE engine):
        # validate_balance above is the hard structural gate; this adds the CE
        # utile==sp13 cross-check (which validate_balance lacks) and any plug-masking,
        # so every route is judged by the same rules. Non-blocking (logged) to avoid
        # rejecting borderline-but-usable A/B imports — but the flags must reach the
        # USER, not just the log: on route A/B a ≤5% plug fabricated by
        # reconcile_ivcee_balance used to pass without any visible warning (the
        # sc_quadratura_warnings below are populated only on route C).
        try:
            from importers.iv_cee_hierarchy import check_quadratura
            # The LLM fields and printed IV-CEE totals can be independently rounded
            # to whole euros.  The mapper already permits one euro per reconstructed
            # side, so the two side sums may differ by at most two euros while both
            # still agree with the same declared total (budget_305: EUR 1.82).
            _qd = check_quadratura(
                balance_sheet_data, income_data, tol=_TOL_QUADRATURA
            )
            for _w in _qd.warnings:
                logger.warning(f"quadratura: {_w}")
                if _w not in sc_quadratura_warnings:
                    sc_quadratura_warnings.append(_w)
            # A CE/SP disagreement or a material plug is surfaced to the user
            # (unbalanced_reason below) and correctable in Rettifiche, rather
            # than blocking the import outright — only a genuinely empty
            # extraction has nothing for the user to act on.
            if not _qd.quadra:
                _blocking_warnings = [
                    warning for warning in _qd.warnings
                    if not warning.startswith("GERARCHIA INCOERENTE:")
                ]
                reason = "; ".join(_blocking_warnings) or (
                    f"attivo {_qd.totale_attivo} / passivo {_qd.totale_passivo}"
                )
                if _qd.is_empty:
                    # Un'estrazione vuota non e' rettificabile: non c'e' alcuna
                    # voce su cui l'utente possa intervenire.
                    raise PDFImportError(
                        "Importazione non salvata: nessun dato contabile "
                        f"estratto dal documento ({reason})"
                    )
                _eccezione = _rifiuta_lettura_non_riuscita(file_path, _qd, income_data)
                if _eccezione and _eccezione not in sc_quadratura_warnings:
                    sc_quadratura_warnings.append(_eccezione)
                # Sbilancio, mismatch CE/SP o plug mascherato: importabile e
                # correggibile in Rettifiche. Allinea finalmente il codice a
                # quanto CLAUDE.md gia' afferma per la rotta C ("Trial-balance
                # import is never hard-blocked"), che oggi non e' vero perche'
                # ``quadra`` richiede ``not masked``.
                if unbalanced_reason is None:
                    unbalanced_reason = (
                        f"{_UNBALANCED_WARNING_PREFIX}: {reason}. "
                        f"{_UNBALANCED_WARNING_SUFFIX}"
                    )
                logger.warning(unbalanced_reason)
        except PDFImportError:
            raise
        except Exception as _qd_err:
            raise PDFImportError(
                f"Impossibile validare contabilmente il bilancio estratto: {_qd_err}"
            ) from _qd_err

        # Lettore di righe (Fase 2, REGOLE-IMPORT-02 §11): solo diagnosi, nessun importo ne dipende. Un try
        # proprio: nulla di cio' che accade qui puo' cambiare SP, CE, esito o anni. Una volta per import.
        _lettore, _lettore_frasi = _lettore_diagnosi_import(
            file_path, extraction_context, fiscal_year, _qd, unbalanced_reason, _snello_report)

        warnings = mapper.validate_hierarchy(balance_sheet_data)
        if _testo_cifrato is not None:
            warnings.insert(0, _tc.avviso(_testo_cifrato))
        if _risultato_report:
            warnings.append(_rs.avviso(_risultato_report))
        if balance_sheet_data.get('_risultato_anno_prima_apertura') is not None:
            warnings.append(_avviso_risultato_in_apertura(balance_sheet_data))
        if balance_sheet_data.get('_risultato_anno_prima_conti') is not None:
            warnings.append(_avviso_risultato_anno_prima_conti(balance_sheet_data))
        _maturity_audit = _detail_report.get('periods', {}).get('current', {}).get('maturity', {}).get('families', {})
        if any(e.get('basis', '').startswith('management_')
               for family in _maturity_audit.values() for e in family.get('evidence', [])) or any(
                   e.get('basis', '').startswith('management_') for e in _source_current.get('maturity', [])):
            warnings.append(
                "SCADENZE STIMATE CON REGOLA GESTIONALE: in assenza di indicazioni "
                "esplicite, crediti/debiti entro 12 mesi e finanziamenti/mutui "
                "(anche soci o altri finanziatori) oltre 12 mesi. "
                "Le scadenze documentate prevalgono; consultare la provenienza dell'importazione."
            )
        # Un messaggio per ciascun caso: la dicitura ORIGINALE (solo debiti) resta byte per byte per
        # ogni rotta che solleva il flag dei debiti; quella che nomina i crediti compare solo quando
        # l'estrattore dello schema con dettaglio ha davvero appiattito i crediti (Task 24, N4).
        _deb_piatti = bool(balance_sheet_data.get("_source_maturity_unspecified")) \
            and 'sp16_debiti_breve' not in _maturity_audit
        _cred_piatti = bool(balance_sheet_data.get("_source_credit_maturity_unspecified"))
        if _deb_piatti and _cred_piatti:
            warnings.append(
                "SCADENZA DEBITI E CREDITI NON DISTINTA NEL PDF: i totali Debiti e Crediti "
                "e le loro sottovoci sono stati conservati nel breve termine; verificare la "
                "quota oltre 12 mesi in Rettifiche se disponibile."
            )
        elif _deb_piatti:
            warnings.append(
                "SCADENZA DEBITI NON DISTINTA NEL PDF: il totale Debiti e le sue "
                "sottovoci sono stati conservati nel breve termine; verificare la "
                "quota oltre 12 mesi in Rettifiche se disponibile."
            )
        elif _cred_piatti:
            warnings.append(
                "SCADENZA CREDITI NON DISTINTA NEL PDF: il totale Crediti e le sue "
                "sottovoci sono stati conservati nel breve termine; verificare la "
                "quota oltre 12 mesi in Rettifiche se disponibile."
            )
        # Surface the deterministic trial-balance plug flag to the user (Rettifiche cue),
        # so an imperfect-but-imported situazione contabile is visible rather than silent.
        warnings.extend(sc_quadratura_warnings)
        if unbalanced_reason:
            warnings.insert(0, unbalanced_reason)
        if _lettore_frasi:
            _pos = 1 if unbalanced_reason else 0
            warnings[_pos:_pos] = _lettore_frasi
        if _snello is not None:
            # Importatore (Task 25 fix round 1): lo stesso avviso arriva da piu' fonti
            # (validate_hierarchy e la quadratura unificata); ogni avviso distinto esce una
            # volta sola. Il percorso di produzione (_snello None) non cambia.
            warnings = list(dict.fromkeys(warnings))
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
                # Mai oltre i 255 caratteri né vuoto: un nome fuori schema fa
                # rispondere 500 a tutta la lista aziende (importers/nome_azienda.py).
                name=nome_azienda_pulito(company_name) or "Azienda importata",
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
                # Partial import (1-11): only delete existing partial record
                # (12 counts as full year, so exclude it)
                existing_year = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == fiscal_year,
                    FinancialYear.period_months.isnot(None),
                    FinancialYear.period_months != 12,
                ).first()
            else:
                # Full-year import: only delete existing full-year record
                # (NULL or legacy 12, so re-import updates in place)
                existing_year = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == fiscal_year,
                    (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),
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
        with open(_file_originale, "rb") as _source_file:
            _source_sha256 = hashlib.sha256(_source_file.read()).hexdigest()
        # Reliability of the accounts that decide every KPI. Never allowed to
        # turn a working import into a failure: any error means "unknown".
        _reliability = None
        try:
            from importers.reliability import assess as _assess_reliability
            _reliability = _assess_reliability(
                balance_sheet_data, income_data,
                declared=_declared_for_reliability)
        except Exception as _rel_err:
            logger.warning(f"Reliability non calcolata: {_rel_err}")

        _validation_payload = _validation_report_payload(_qd, reliability=_reliability)
        if _lettore is not None:
            _validation_payload["lettore"] = _lettore
        _validation_payload["import_snello"] = _snello_report_dichiarato
        if _mineru_tabelle:
            _validation_payload["mineru_contrapposte"] = True
        if _risultato_report:
            _validation_payload["risultato_stampato"] = _risultato_report
        if _testo_cifrato is not None:
            _validation_payload["testo_cifrato"] = {
                "spostamento": _testo_cifrato.spostamento,
                "parole_prima": _testo_cifrato.parole_prima,
                "parole_dopo": _testo_cifrato.parole_dopo,
            }
            _validation_payload.setdefault("warnings", []).append(_tc.avviso(_testo_cifrato))
        if is_trial_balance:
            # Fornitore configurato per il pass CoGe di route C, dichiarato su OGNI import
            # di route C (non solo quando il pass CoGe ha vinto il confronto col candidato
            # deterministico). Scritto QUI, prima che il payload sia serializzato in
            # FinancialYear.validation_report (poco sotto) e la transazione fatta commit:
            # la provenienza si legge a posteriori da un GET, senza rieseguire l'import
            # (docs/import/REGOLE-IMPORT-06-PERSISTENZA.md §2) — lo stesso motivo per cui
            # _rescue_reasons/_rescued_sections sono inizializzati prima che il payload
            # sia costruito, poco piu' sotto in questa funzione.
            from importers.llm_provider import provider_coge
            _validation_payload["coge_provider"] = provider_coge()
        # Fornitore configurato per l'estrattore testuale di route A/B + lettura delle
        # macro-voci (provider_ivcee) e per la seconda lettura dei dettagli (provider_dettagli),
        # dichiarati su OGNI route — non solo su route C come coge_provider sopra, perché
        # questi due girano anche su A/B. Stesso motivo, stesso punto: prima della
        # serializzazione, cosi' un GET successivo li rilegge senza rieseguire l'import.
        from importers.llm_provider import provider_dettagli, provider_ivcee
        _validation_payload["ivcee_provider"] = provider_ivcee()
        _validation_payload["dettagli_provider"] = provider_dettagli()
        _validation_payload['residual_finalization'] = _residual_report
        _validation_payload['dettaglio_dal_modello'] = _dettaglio_report
        _validation_payload['warnings'].extend(_residual_report['warnings'])
        _validation_payload['warnings'].extend(_detail_report.get('warnings', []))
        _validation_payload['source_reconciliation'] = _source_current
        _validation_payload['macro_analysis'] = _macro_report or {
            'status': 'verified' if _source_complete else 'existing_route',
            'method': 'source_crossfoot' if _source_complete else 'existing_extractor',
        }
        _validation_payload['warnings'].extend(_macro_report.get('warnings', []))
        _validation_payload["detail_enrichment"] = {
            **{k: v for k, v in _detail_report.items() if k != "periods"},
            **_detail_report.get("periods", {}).get("current", {}),
        }
        _critical_ok = _reliability is None or _reliability.all_critical_ok
        # Risultato precedente ricostruito dai totali stampati (budget_1410, decisione del
        # proprietario 2026-10-28): importo non letto, quindi da rivedere prima della proiezione.
        _ricostruito = balance_sheet_data.get('_prior_result_ricostruito')
        if _ricostruito:
            _validation_payload['warnings'].append(_avviso_risultato_ricostruito(_ricostruito))
        _forecastable = (_qd.semantic_valid and _critical_ok and not _source_review
                         and not _residual_report['requires_review'] and not _ricostruito)

        _stored_parser_version = _PDF_PARSER_VERSION
        if extraction_context is not None:
            _mineru_version = getattr(extraction_context, "mineru_version", None)
            _source_detail_fields = int(
                balance_sheet_data.get("_mineru_source_detail_fields", 0) or 0
            )
            if _source_detail_fields >= 20:
                _detail_level = "detailed"
            elif _source_detail_fields >= 8:
                _detail_level = "standard"
            else:
                _detail_level = "summary"
            if is_trial_balance:
                _ocr_accounting_method = (
                    ("situazione_contabile_mineru" if _mineru_tabelle
                else "situazione_contabile_llm" if _coge_ok else "situazione_contabile")
                )
            elif balance_sheet_data.get("_source_mineru_ivcee"):
                _ocr_accounting_method = "ivcee_deterministic"
            elif balance_sheet_data.get("_source_schema_etichette"):
                _ocr_accounting_method = "schema_etichette"
            elif balance_sheet_data.get("_source_xbrl_reso"):
                _ocr_accounting_method = "xbrl_reso"
            elif balance_sheet_data.get("_source_prospetto_sintetico"):
                _ocr_accounting_method = "prospetto_sintetico"
            elif balance_sheet_data.get("_source_standard_ivcee"):
                _ocr_accounting_method = "ivcee_source"
            else:
                _ocr_accounting_method = "llm"
            _validation_payload["ocr"] = {
                "engine": "mineru",
                "version": _mineru_version,
                "pages": len(getattr(extraction_context, "page_texts", ()) or ()),
                "tables": len(getattr(extraction_context, "tables", ()) or ()),
                "accounting_method": _ocr_accounting_method,
                "source_detail_fields": _source_detail_fields,
                "detail_level": _detail_level,
            }
            if _mineru_version:
                _stored_parser_version = (
                    f"{_PDF_PARSER_VERSION}+mineru-{_mineru_version}"
                )[:50]
        # Provenienza del riscatto, con la stessa convenzione di '+mineru-<ver>': dopo
        # il fatto si deve poter distinguere un foglio riletto in vision da uno letto
        # dal solo text layer. Il parser_version e' troncato a 50 caratteri e non
        # porta i motivi: la registrazione completa sta nel validation_report, come
        # per l'OCR MinerU qui sopra (spec §5).
        if _rescued_sections:
            _stored_parser_version = (
                f"{_stored_parser_version}+vision-{'-'.join(_rescued_sections)}"
            )[:50]
        if _rescued_sections or _rescue_reasons:
            _validation_payload["vision_rescue"] = {
                "engine": "vision",
                "sections": list(_rescued_sections),
                "attempted": sorted(_rescue_reasons),
                "reasons": dict(_rescue_reasons),
            }
        financial_year_obj = FinancialYear(
            company_id=company.id,
            year=current_year_val,
            period_months=period_months,  # None for full year, 1-11 for partial
            validation_status=_resolve_validation_status(
                unbalanced_reason is None, _forecastable
            ),
            validation_report=json.dumps(_validation_payload, ensure_ascii=False),
            source_sha256=_source_sha256,
            parser_version=_stored_parser_version,
            forecastable=_forecastable,
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
        prior_mesi = None                               # None: anno intero
        if prior_bs_data and prior_ce_data and fiscal_year:
            # Check if prior year data is meaningful (not all zeros from single-column PDF)
            prior_sp_fields = [v for k, v in prior_bs_data.items()
                               if k.startswith('sp') and k != 'totale_attivo' and k != 'totale_passivo']
            prior_has_data = any(v != Decimal('0') for v in prior_sp_fields)

            if not prior_has_data:
                logger.info("Prior year data is all zeros (single-column PDF), skipping")
            else:
                from importers.iv_cee_hierarchy import check_quadratura
                _prior_q = check_quadratura(
                    prior_bs_data, prior_ce_data, tol=Decimal('2')
                )
                fresh_prior_balances = mapper.validate_balance(prior_bs_data) and _prior_q.quadra
                # Di un infrannuale la colonna di confronto puo' essere lo stesso periodo dell'anno
                # prima (budget_1540 giugno su giugno) o l'anno intero (budget_638): lo dice la data
                # di chiusura stampata. Un semestre salvato come anno intero diventa un anno base
                # falso e sostituisce l'anno vero gia' importato.
                durata_ignota = False
                # Fase 3 (F3-14): se il lettore ha adottato il documento e dichiara la durata della colonna di
                # confronto (< 12 mesi), vale anche a periodo pieno: un precedente di 9 mesi non e' un anno intero.
                _mesi_lettore = ((_snello_report or {}).get("lettore_percorso") or {}).get("mesi_precedente") \
                    if (_snello_report or {}).get("fonte") == "deterministico:lettore" else None
                if isinstance(_mesi_lettore, int) and _mesi_lettore < 12:
                    prior_mesi = _mesi_lettore
                elif isinstance(_mesi_lettore, int):
                    pass                                   # il lettore dichiara un anno intero: durata nota
                elif period_months is not None:
                    from importers.durata_comparato import mesi_del_comparato, testo_di_testa
                    _mesi = mesi_del_comparato(testo_di_testa(file_path), fiscal_year)
                    if _mesi is None:
                        durata_ignota = True
                    elif _mesi < 12:
                        prior_mesi = _mesi
                existing_prior = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == prior_fiscal_year,
                    (FinancialYear.period_months == prior_mesi) if prior_mesi is not None
                    else (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),
                ).first()

                _prior_ok = _should_import_prior(
                    fresh_prior_balances and not _prior_residual_report.get('requires_review'), _prior_q.is_empty,
                    has_existing=existing_prior is not None,
                )
                if _prior_ok and durata_ignota and existing_prior is not None:
                    # senza la data non si sa se e' l'anno intero: un anno intero gia' presente non
                    # si sostituisce con una colonna che potrebbe essere un semestre
                    prior_year_imported = True
                    warnings.append(
                        f"ANNO PRECEDENTE NON SOSTITUITO [{prior_fiscal_year}]: il documento non stampa "
                        f"la data di chiusura della colonna di confronto, quindi non si sa se copre l'anno "
                        f"intero o lo stesso periodo dell'anno prima; resta il {prior_fiscal_year} gia' importato."
                    )
                elif not _prior_ok:
                    logger.info(
                        f"Prior year {prior_fiscal_year} extraction is not accounting-valid — "
                        f"{'keeping existing record' if existing_prior else 'not importing it'}"
                    )
                    prior_year_imported = existing_prior is not None
                    warnings.append(
                        f"ANNO PRECEDENTE NON IMPORTATO [{prior_fiscal_year}]: "
                        + "; ".join([*_prior_q.warnings, *_prior_residual_report.get('warnings', [])])
                    )
                else:
                    if not fresh_prior_balances:
                        warnings.append(
                            f"{_UNBALANCED_WARNING_PREFIX} [ANNO PRECEDENTE "
                            f"{prior_fiscal_year}]: " + "; ".join(_prior_q.warnings)
                            + f". {_UNBALANCED_WARNING_SUFFIX}"
                        )
                    if prior_mesi is not None:
                        warnings.append(
                            f"ANNO PRECEDENTE PARZIALE [{prior_fiscal_year}, {prior_mesi} mesi]: la colonna di "
                            f"confronto e' lo stesso periodo dell'anno prima e si salva come periodo di "
                            f"{prior_mesi} mesi, non come anno intero. Come anno di riferimento "
                            f"dell'infrannuale importa il bilancio {prior_fiscal_year} completo."
                        )
                    elif durata_ignota:
                        warnings.append(
                            f"ANNO PRECEDENTE COME ANNO INTERO [{prior_fiscal_year}]: il documento non stampa "
                            f"la data di chiusura della colonna di confronto; e' stata salvata come anno intero. "
                            f"Se copre lo stesso periodo dell'anno prima, importa il bilancio {prior_fiscal_year} "
                            f"completo al suo posto."
                        )
                    # Import (or, on re-import, REPLACE) the prior year. Replacing a stale record with
                    # a freshly extracted one that BALANCES lets a re-import pick up extractor fixes
                    # (budget_297 2024: old import had inflated reserves; re-import now refreshes it).
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

                    _prior_validation = _validation_report_payload(_prior_q)
                    if _snello_report is not None:
                        _prior_validation["import_snello"] = _snello_report
                    if is_trial_balance:
                        # Stesso fornitore dichiarato dell'anno corrente (route C legge
                        # entrambe le colonne con lo stesso pass CoGe): vedi il commento
                        # gemello su _validation_payload, qualche centinaio di righe sopra.
                        from importers.llm_provider import provider_coge
                        _prior_validation["coge_provider"] = provider_coge()
                    # Stessi due campi dell'anno corrente, stesso motivo: vedi il commento
                    # gemello su _validation_payload, qualche centinaio di righe sopra.
                    from importers.llm_provider import provider_dettagli, provider_ivcee
                    _prior_validation["ivcee_provider"] = provider_ivcee()
                    _prior_validation["dettagli_provider"] = provider_dettagli()
                    _prior_validation['residual_finalization'] = _prior_residual_report
                    if _prior_dettaglio_report is not None:
                        _prior_validation['dettaglio_dal_modello'] = _prior_dettaglio_report
                    _prior_validation['warnings'].extend(_prior_residual_report.get('warnings', []))
                    _prior_validation['warnings'].extend(_detail_report.get('warnings', []))
                    _prior_validation['source_reconciliation'] = _source_reports.get('prior', {})
                    if _macros_verified:
                        _prior_validation['macro_analysis'] = _macro_report.get('prior', {})
                    _prior_source_review = bool(_source_reports.get('prior', {}).get('requires_review'))
                    _prior_validation['warnings'].extend(_source_reports.get('prior', {}).get('errors', []))
                    _prior_forecastable = (_prior_q.semantic_valid
                        and not _prior_residual_report.get('requires_review') and not _prior_source_review)
                    _prior_validation["detail_enrichment"] = {
                        **{k: v for k, v in _detail_report.items() if k != "periods"},
                        **_detail_report.get("periods", {}).get("prior", {}),
                    }
                    if extraction_context is not None:
                        _prior_source_detail_fields = int(
                            prior_bs_data.get("_mineru_source_detail_fields", 0) or 0
                        )
                        _prior_validation["ocr"] = {
                            **_validation_payload.get("ocr", {}),
                            "source_detail_fields": _prior_source_detail_fields,
                            "detail_level": (
                                "detailed" if _prior_source_detail_fields >= 20
                                else "standard" if _prior_source_detail_fields >= 8
                                else "summary"
                            ),
                        }
                    prior_fy = FinancialYear(
                        company_id=company.id,
                        year=prior_fiscal_year,
                        period_months=prior_mesi,  # None = anno intero
                        validation_status=_resolve_validation_status(
                            bool(fresh_prior_balances),
                            _prior_forecastable,
                        ),
                        validation_report=json.dumps(_prior_validation, ensure_ascii=False),
                        source_sha256=_source_sha256,
                        parser_version=_stored_parser_version,
                        forecastable=_prior_forecastable,
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

        # #60: un comparato stampato che nessun lettore ha saputo leggere si dichiara.
        if fiscal_year and not prior_year_imported:
            from importers.standard_ivcee_parser import has_comparative_ivcee_columns
            _avviso_comparato = _avviso_comparato_non_letto(
                prior_fiscal_year,
                stampa_comparato=has_comparative_ivcee_columns(file_path),
                prior_imported=prior_year_imported,
                gia_avvisato=any(
                    str(w).startswith("ANNO PRECEDENTE NON IMPORTATO") for w in warnings
                ),
                has_existing=db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == prior_fiscal_year,
                    (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),
                ).first() is not None,
            )
            if _avviso_comparato:
                logger.warning(_avviso_comparato)
                warnings.append(_avviso_comparato)
                # anche nel report persistito dell'anno corrente: il risultato dell'import
                # sparisce al primo ricaricamento, il report no.
                _validation_payload.setdefault("warnings", []).append(_avviso_comparato)
                financial_year_obj.validation_report = json.dumps(
                    _validation_payload, ensure_ascii=False
                )

        # Step 8: Commit transaction
        db.commit()

        extraction_time = (datetime.utcnow() - extraction_start).total_seconds()
        if _snello is not None:
            extraction_method = "import_snello"
        elif is_trial_balance:
            # Route C: distinguish the CoGe LLM pass from the deterministic parser fallback.
            extraction_method = ("situazione_contabile_mineru" if _mineru_tabelle
                else "situazione_contabile_llm" if _coge_ok else "situazione_contabile")
        elif balance_sheet_data.get("_source_mineru_ivcee"):
            extraction_method = "ivcee_deterministic"
        elif balance_sheet_data.get("_source_schema_etichette"):
            extraction_method = "schema_etichette"
        elif balance_sheet_data.get("_source_xbrl_reso"):
            extraction_method = "xbrl_reso"
        elif balance_sheet_data.get("_source_prospetto_sintetico"):
            extraction_method = "prospetto_sintetico"
        elif balance_sheet_data.get("_source_standard_ivcee"):
            extraction_method = "ivcee_source"
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
            "confidence_score": {"high": 0.95, "med": 0.70, "low": 0.40}.get(
                classification.confidence, 0.40
            ),
            "extraction_method": extraction_method,
            "extraction_time_seconds": round(extraction_time, 2),
            "message": f"Successfully imported balance sheet for {company.name} ({financial_year_obj.year})",
            "warnings": warnings,
            "validation_status": financial_year_obj.validation_status,
            "validation_report": _validation_payload,
            "forecastable": financial_year_obj.forecastable,
            "source_sha256": _source_sha256,
            "parser_version": _stored_parser_version,
        }

        result["prior_year_imported"] = prior_year_imported
        result["prior_fiscal_year"] = prior_fiscal_year
        result["prior_period_months"] = prior_mesi if prior_year_imported else None

        # MinerU OCR metadata (only when the /import/pdf-ocr route supplied a context).
        # extraction_method already describes the accounting path actually used
        # (deterministico / CoGe-LLM / IV-CEE LLM); prefix it with the OCR engine so the
        # full provenance "mineru+<engine>" is visible without a DB migration.
        if extraction_context is not None:
            _mineru_version = getattr(extraction_context, "mineru_version", None)
            _pages = len(getattr(extraction_context, "page_texts", ()) or ())
            _tables = len(getattr(extraction_context, "tables", ()) or ())
            _ocr_report = _validation_payload.get("ocr", {})
            result["ocr_engine"] = "mineru"
            result["ocr_version"] = _mineru_version
            result["ocr_pages"] = _pages
            result["ocr_tables"] = _tables
            result["source_detail_fields"] = _ocr_report.get("source_detail_fields", 0)
            result["detail_level"] = _ocr_report.get("detail_level", "summary")
            result["extraction_method"] = f"mineru+{extraction_method}"

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
        if _pdf_mineru is not None:
            try:
                os.remove(_pdf_mineru)
            except OSError:
                pass
        if file_path != _file_originale:
            try:
                os.remove(file_path)
            except OSError:
                pass
