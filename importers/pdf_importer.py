"""
PDF Balance Sheet Importer for Italian IV CEE format.

Uses PyMuPDF + Claude Haiku 4.5 (~5s). Requires ANTHROPIC_API_KEY.
"""

import os
import re
import json
import hashlib
import logging
from typing import Dict, Any, List, NamedTuple, Optional, Tuple
from decimal import Decimal
from datetime import datetime

from database.db import SessionLocal
from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
from importers.pdf_mapper import IVCEEMapper
from config import Sector

logger = logging.getLogger(__name__)

_PDF_PARSER_VERSION = "semantic-v3-2026-07-20"


def _validation_report_payload(q, reliability=None) -> Dict[str, Any]:
    """JSON-safe persisted form of the immutable accounting validation."""
    payload = {
        "arithmetic_balanced": abs(q.sbilancio) <= Decimal("0.01"),
        "income_result_consistent": q.utile_match,
        "hierarchy_consistent": q.hierarchy_consistent,
        "semantic_valid": q.semantic_valid,
        "masked": q.masked,
        "is_empty": q.is_empty,
        "totale_attivo": str(q.totale_attivo),
        "totale_passivo": str(q.totale_passivo),
        "sbilancio": str(q.sbilancio),
        "utile_ce": None if q.utile_ce is None else str(q.utile_ce),
        "sp13": str(q.sp13),
        "plug_residual": str(q.plug_residual),
        "hierarchy_differences": {
            key: str(value) for key, value in q.hierarchy_differences.items()
        },
        "warnings": list(q.warnings),
    }
    if reliability is not None:
        payload["critical_accounts"] = reliability.to_dict()
    return payload


class PDFImportError(Exception):
    """Exception raised when PDF import fails."""
    pass


_UNBALANCED_WARNING_PREFIX = "BILANCIO SBILANCIATO"
_UNBALANCED_WARNING_SUFFIX = (
    "Il bilancio è stato importato così com'è: correggilo in Rettifiche "
    "prima di calcolare la proiezione."
)


class BalanceFailureVerdict(NamedTuple):
    """Esito della diagnosi su un bilancio che non supera ``validate_balance``.

    Esattamente uno dei due campi e' valorizzato. ``hard_error`` significa che
    non c'e' nulla che l'utente possa correggere in Rettifiche (estrazione
    vuota, documento che non e' uno schema IV-CEE, totali letti dall'OCR e
    quindi inaffidabili di per se'). ``warning`` significa che il bilancio e'
    leggibile ma non quadra: si importa e si corregge a mano.
    """
    hard_error: Optional[str]
    warning: Optional[str]


def _it_amount(value: Decimal) -> str:
    """Formattazione italiana: 1.234.567,89."""
    return f"{value:,.2f}".replace(',', '#').replace('.', ',').replace('#', '.')


def _classify_balance_failure(
    balance_sheet_data: Dict[str, Decimal],
    *,
    is_scanned: bool,
    ocr_source: bool,
    is_trial_balance: bool,
    sample_text: str,
    file_path: str,
    ocr_text: Optional[str],
) -> BalanceFailureVerdict:
    """Decide se un fallimento di ``validate_balance`` blocca o solo avvisa.

    L'ordine conta: le diagnosi irrecuperabili girano per prime, cosi' un
    documento che non e' importabile non viene salvato come "sbilanciato".
    """
    # 1. Testo OCR: i totali stessi possono essere letti male, quindi non si puo'
    #    dichiarare sbilanciato il documento sorgente.
    if is_scanned or ocr_source:
        return BalanceFailureVerdict(
            "Il documento è una scansione contabile, ma l'OCR non ha "
            "ricostruito in modo affidabile colonne, gerarchie e totali. "
            "Il file sorgente non viene dichiarato sbilanciato: serve una "
            "lettura OCR strutturata oppure un PDF con testo selezionabile.",
            None,
        )

    # 2. Estrazione vuota: non c'e' niente da rettificare.
    if balance_sheet_data.get('totale_attivo', Decimal('0')) == Decimal('0'):
        return BalanceFailureVerdict(
            "Nessun dato estratto dal documento: lo Stato Patrimoniale "
            "risulta vuoto (Totale Attivo pari a zero). Verificare che il "
            "file contenga un prospetto leggibile.",
            None,
        )

    # 3. Riepilogo aggregato: manca lo schema IV-CEE, non la quadratura.
    if not is_trial_balance and _is_aggregated_summary(sample_text):
        contradiction = _summary_internal_contradiction(sample_text)
        if contradiction:
            return BalanceFailureVerdict(contradiction, None)
        return BalanceFailureVerdict(
            "Formato non supportato: il documento è un riepilogo aggregato per "
            "macro-voci, non uno schema di bilancio IV-CEE (art. 2424/2425) "
            "importabile. Carica il prospetto di Stato Patrimoniale e Conto "
            "Economico completo.",
            None,
        )

    # 4. Tutto il resto e' uno sbilancio correggibile. Il messaggio d'errore
    #    che prima bloccava e' la migliore diagnosi disponibile: diventa il
    #    testo dell'avviso, cosi' l'utente sa cosa cercare in Rettifiche.
    try:
        from importers.pdf_extractor_llm import _declared_control_totals
        controls = _declared_control_totals(file_path, text=ocr_text)
        source_attivo = controls.get('attivo')
        source_passivo = controls.get('passivo')
    except Exception:
        source_attivo = source_passivo = None

    if source_attivo is not None and source_passivo is not None:
        difference = abs(source_attivo - source_passivo)
        if difference > Decimal('2'):
            detail = (
                "il bilancio sorgente non quadra già nel documento: Totale "
                f"Attivo €{_it_amount(source_attivo)} != Totale Passivo "
                f"€{_it_amount(source_passivo)} (scarto €{_it_amount(difference)})"
            )
        else:
            detail = (
                "i totali Attivo e Passivo stampati coincidono, ma le "
                "componenti patrimoniali estratte non li ricostruiscono"
            )
    else:
        detail = (
            "il bilancio non quadra oppure il documento non contiene "
            "dettaglio sufficiente per ricostruire Attivo, Passivo e "
            "Patrimonio netto"
        )

    return BalanceFailureVerdict(
        None,
        f"{_UNBALANCED_WARNING_PREFIX}: {detail}. {_UNBALANCED_WARNING_SUFFIX}",
    )


def _resolve_validation_status(warning_free: bool, forecastable: bool) -> str:
    """Stato di validazione a tre vie.

    Invariante: lo stato e' ``unbalanced`` esattamente quando all'utente e'
    stato mostrato un avviso "BILANCIO SBILANCIATO" (``warning_free=False``,
    cioe' ``unbalanced_reason`` non era ``None``) — stato e avviso non
    possono mai essere in disaccordo. Deliberatamente NON e' derivato dalla
    tolleranza rigorosa di ``arithmetic_balanced`` (0,01 €): i gate che
    generano l'avviso (``validate_balance``, ``check_quadratura(tol=2)``)
    usano tolleranze piu' larghe, quindi uno sbilancio nella fascia
    (0,01 €; 2,00 €] — rumore che i gate considerano accettabile (vedi
    budget_305, scarto 1,82 €) — non deve produrre uno stato "unbalanced"
    senza alcun avviso a spiegarlo.
    """
    if not warning_free:
        return "unbalanced"
    return "verified" if forecastable else "review_required"


def _should_import_prior(
    fresh_balances: bool, is_empty: bool, *, has_existing: bool
) -> bool:
    """Se salvare l'anno di raffronto appena estratto.

    Un anno vuoto non si importa mai: non c'e' nulla da rettificare. Un anno
    sbilanciato si importa SOLO se non ne esiste gia' uno: meglio uno storico
    da correggere che nessuno storico (senza anno di raffronto il wizard
    infrannuale non parte), ma mai al prezzo di degradare un record buono.
    """
    if is_empty:
        return False
    if fresh_balances:
        return True
    return not has_existing


def _is_aggregated_summary(text: str) -> bool:
    """True when the document carries NO legal IV-CEE substructure — only top-level
    macro-voci (e.g. "Immobilizzazioni: 2.406.946", "B) Patrimonio netto: ..."), with
    no roman-numeral sub-items, no "esigibili entro/oltre l'esercizio", and no account
    codes. These are over-aggregated riepiloghi (often AI-generated, e.g. the LUGS /
    FINALE_CEE test fixtures) that are NOT an importable art. 2424/2425 schema — so the
    import should say "formato non supportato" rather than the cryptic "does not balance".

    Used ONLY at the validate_balance failure point (a file that already balances never
    reaches it), so this can never reclassify a correctly-imported bilancio. Gestionali
    with a real (even abbreviated) schema always carry roman numerals / "esigibili" /
    account codes, so they keep the "BILANCIO NON QUADRATO" honest-fail path.
    """
    if not text:
        return False
    # Roman-numeral legal items II..X, optionally prefixed by the section letter (A.II, B) II).
    romans = re.findall(
        r'(?im)^\s*(?:[A-D][.\)]\s*)?(?:II|III|IV|VIII|VII|VI|IX|V|X)\b', text)
    has_esigibili = bool(re.search(r'esigibili\s+(?:entro|oltre)', text, re.I))
    has_codes = bool(re.search(r'(?m)^\s*\d{4,}\b', text))
    return len(romans) < 3 and not has_esigibili and not has_codes


# Italian-formatted amount: 1.234.567,89 / -58.481,84 / 258,31
_IT_AMOUNT_RE = re.compile(r'-?\d{1,3}(?:\.\d{3})*,\d{2}\b')


def _euro_it(value: Decimal) -> str:
    return f"{value:,.2f}".replace(',', '#').replace('.', ',').replace('#', '.')


def _label_amount_pairs(text: str) -> list:
    """(label, amount) for every printed amount, tolerating the two layouts these
    summaries use: "Immobilizzazioni: 2.406.946,04" and a label whose amount sits on
    the following line (PyMuPDF splits two-column tables that way)."""
    pairs = []
    pending_label = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _IT_AMOUNT_RE.search(line)
        if not match:
            pending_label = line
            continue
        label = line[:match.start()].strip(' :.\t-–') or (pending_label or '')
        pairs.append((label, Decimal(
            match.group().replace('.', '').replace(',', '.'))))
        pending_label = None
    return pairs


def _section(text: str, start_pattern: str, end_pattern: str) -> Optional[str]:
    start = re.search(start_pattern, text, re.I | re.M)
    if not start:
        return None
    rest = text[start.end():]
    end = re.search(end_pattern, rest, re.I | re.M)
    return rest[:end.start()] if end else rest


def _summary_internal_contradiction(text: str) -> Optional[str]:
    """Diagnosis for an over-aggregated summary that contradicts its OWN printed
    figures — the components it lists do not rebuild the totals it prints.

    budget_137 is the motivating case: it carries the budget_133/135 macro figures with
    Debiti inflated (2.688.470,08 -> 3.995.536,14) so the two sides tie, which lets it
    slip past the "Totale Attivo != Totale Passivo" source check. The tie is cosmetic:
    the Attivo components sum 89.354,38 above the printed total, and the CE components
    land 61.350,89 away from the printed result. Saying "riepilogo aggregato" there
    hides a document that is arithmetically self-contradictory.

    Reads only amounts the document prints, and reports the gaps. It never infers a
    corrected figure and never touches an accounting value. Returns None when the
    printed figures are consistent or too sparse to judge — silence is the safe answer,
    the caller still rejects the file for its own reasons.
    """
    if not text:
        return None
    faults = []

    # --- CE: does "Differenza A-B" + "Gestione finanziaria" reach the printed result?
    ce_text = _section(text, r'^.*CONTO\s+ECONOMICO.*$', r'^\s*NOT[AE]\b')
    if ce_text and not re.search(r'\b(IRES|IRAP|imposte)\b', ce_text, re.I):
        # Imposte would sit between the two, so only judge a CE that prints none.
        ce_pairs = _label_amount_pairs(ce_text)

        def _find(pattern):
            for label, amount in ce_pairs:
                if re.search(pattern, label, re.I):
                    return amount
            return None

        differenza = _find(r'^differenza\b')
        finanziaria = _find(r'gestione\s+finanziaria')
        risultato = _find(r"^(risultato\s+netto|utile\s+netto|"
                          r"perdita\s+(?:d')?esercizio)")
        if differenza is not None and finanziaria is not None and risultato is not None:
            gap = abs(differenza + finanziaria - risultato)
            if gap > Decimal('2'):
                faults.append(
                    "le componenti del Conto Economico non ricostruiscono il "
                    f"risultato netto dichiarato (scarto €{_euro_it(gap)})"
                )

    # --- Attivo: do the listed components add up to the printed total?
    attivo_text = _section(
        text,
        r'^.*STATO\s+PATRIMONIALE\s*[-–]?\s*ATTIVO.*$',
        r'^.*(?:STATO\s+PATRIMONIALE\s*[-–]?\s*)?PASSIVO.*$',
    )
    if attivo_text:
        declared = None
        components = Decimal('0')
        for label, amount in _label_amount_pairs(attivo_text):
            if re.match(r'^totale\s+attivo\b', label, re.I):
                declared = amount
            elif not re.match(r'^totale\b', label, re.I):
                # Subtotals ("Totale immobilizzazioni") would double-count the leaves.
                components += amount
        if declared is not None and declared != 0:
            gap = abs(components - declared)
            if gap > Decimal('2'):
                faults.append(
                    "le componenti dell'Attivo non coincidono con il totale "
                    f"stampato (scarto €{_euro_it(gap)})"
                )

    if not faults:
        return None
    return (
        "Il documento sorgente è internamente incoerente: "
        + " e ".join(faults)
        + ". Correggere il documento contabile originale."
    )


# Soglia oltre cui un plug residuo del parser best-effort rende il bilancio inaffidabile
# (composizione per lo più fabbricata): sopra questa frazione del totale si rifiuta
# l'estrazione deterministica e si tenta l'LLM. Sotto, si importa con flag "BILANCIO NON
# QUADRATO" per correzione in Rettifiche (workflow esistente). Vedi iv_cee_hierarchy.
SC_PLUG_REJECT_PCT = Decimal("0.20")


# Map short keys from situazione_contabile_parser to full DB field names
_SC_KEY_MAP = {
    'sp01': 'sp01_crediti_soci', 'sp02': 'sp02_immob_immateriali', 'sp03': 'sp03_immob_materiali',
    'sp04': 'sp04_immob_finanziarie', 'sp04a': 'sp04a_partecipazioni', 'sp05': 'sp05_rimanenze',
    'sp06': 'sp06_crediti_breve', 'sp06g': 'sp06g_crediti_altri_breve',
    'sp07': 'sp07_crediti_lungo',
    'sp08': 'sp08_attivita_finanziarie', 'sp09': 'sp09_disponibilita_liquide',
    'sp10': 'sp10_ratei_risconti_attivi', 'sp11': 'sp11_capitale', 'sp12': 'sp12_riserve',
    'sp13': 'sp13_utile_perdita', 'sp14': 'sp14_fondi_rischi', 'sp15': 'sp15_tfr',
    # sp06g / sp16g are the KPI-neutral catch-all destinations named by
    # situazione_contabile_parser.FALLBACK_FIELDS. _map_sc_keys SILENTLY DROPS a
    # short key it does not know, so an unmapped fallback bucket would make read
    # mass disappear with no gate firing (the sp04a incident).
    'sp16': 'sp16_debiti_breve', 'sp16g': 'sp16g_altri_debiti_breve',
    'sp17': 'sp17_debiti_lungo',
    'sp18': 'sp18_ratei_risconti_passivi',
    'ce01': 'ce01_ricavi_vendite', 'ce02': 'ce02_variazioni_rimanenze',
    'ce03': 'ce03_lavori_interni',
    'ce03a': 'ce03a_incrementi_immobilizzazioni',
    'ce04': 'ce04_altri_ricavi',
    'ce05': 'ce05_materie_prime', 'ce06': 'ce06_servizi', 'ce07': 'ce07_godimento_beni',
    'ce08': 'ce08_costi_personale', 'ce09': 'ce09_ammortamenti',
    'ce10': 'ce10_var_rimanenze_mat_prime', 'ce11': 'ce11_accantonamenti',
    'ce11b': 'ce11b_altri_accantonamenti', 'ce12': 'ce12_oneri_diversi',
    'ce13': 'ce13_proventi_partecipazioni', 'ce14': 'ce14_altri_proventi_finanziari',
    'ce15': 'ce15_oneri_finanziari', 'ce16': 'ce16_utili_perdite_cambi',
    'ce17': 'ce17_rettifiche_attivita_fin',
    'ce17a': 'ce17a_rivalutazioni', 'ce17b': 'ce17b_svalutazioni',
    'ce18': 'ce18_proventi_straordinari',
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


def _apply_vision_rescue(file_path: str,
                         balance_sheet_data: Dict[str, Decimal],
                         income_data: Dict[str, Decimal],
                         declared: Dict[str, Optional[Decimal]],
                         donor_bs: Optional[Dict[str, Decimal]],
                         ocr_text: Optional[str],
                         reader=None) -> Tuple[Dict[str, Decimal], Dict[str, Decimal], List[str]]:
    """Riscatto vision per sezione, in coda alla catena route C.

    Innesco: check_quadratura sul foglio FINITO. La posizione e' deliberata — innescare
    prima del netting farebbe scattare il riscatto su un attivo ancora lordo, un divario
    che il netting dei fondi chiude da solo. Le due sezioni si innescano in modo
    indipendente: un file puo' riscattare il CE e lasciare l'SP com'e'.

    Ogni errore e' NON fatale: si logga e si tiene il candidato precedente. Se il
    riscatto non riesce, il foglio resta esattamente com'e' oggi.
    """
    from importers import vision_rescue as vr
    from importers.iv_cee_hierarchy import check_quadratura
    from importers import situazione_contabile_parser as scp

    read = reader or vr.read_section
    rescued: List[str] = []
    try:
        before = check_quadratura(balance_sheet_data, income_data)
    except Exception as err:
        logger.warning(f"Riscatto vision: quadratura iniziale non calcolabile ({err})")
        return balance_sheet_data, income_data, rescued

    sp_broken = before.is_empty or abs(before.sbilancio) > Decimal("0.01") or before.masked
    ce_broken = not before.utile_match
    if not sp_broken and not ce_broken:
        return balance_sheet_data, income_data, rescued

    try:
        pages = scp.section_pages(file_path)
    except Exception as err:
        logger.warning(f"Riscatto vision: pagine per sezione non determinabili ({err})")
        return balance_sheet_data, income_data, rescued

    # --- Conto economico ---------------------------------------------------
    if ce_broken:
        try:
            sec = read(file_path, pages.get("ce", []), "ce")
            if sec is not None and sec.rows:
                new_ce = _map_sc_keys(scp.build_ce_from_vision(
                    [(r.code, r.description, r.amount, r.column) for r in sec.rows]))
                rebuilt = sum((r.amount for r in sec.rows if r.column == "left"),
                              Decimal("0"))
                # Il CE non tocca il bilancio: lo si passa immutato su entrambi i lati
                # del confronto. Con ce=None `utile_match` varrebbe True per difetto e
                # il ramo `fixed_identity` del cancello scatterebbe a vuoto.
                after = check_quadratura(balance_sheet_data, new_ce)
                ok, why = vr.accept_rescue("ce", rebuilt, sec, declared, before, after)
                logger.info(f"Riscatto vision CE: {'accettato' if ok else 'scartato'} — {why}")
                if ok:
                    income_data = new_ce
                    before = after
                    rescued.append("ce")
        except Exception as err:
            logger.warning(f"Riscatto vision CE fallito ({type(err).__name__}: {err})")

    # --- Stato patrimoniale ------------------------------------------------
    if sp_broken:
        try:
            sec = read(file_path, pages.get("sp", []), "sp")
            if sec is not None and sec.rows:
                # Il segno del risultato lo decide l'identita' che ha VALIDATO i totali
                # letti, non l'ordine delle chiavi: un documento stampa spesso sia un
                # "utile" sia una "perdita" e preferire il primo ribalta il risultato
                # quando e' il ramo della perdita a tornare.
                utile = vr.vision_result(sec)
                if utile is None:
                    logger.info("Riscatto vision SP: totali letti non coerenti — non tentato")
                else:
                    new_bs = _map_sc_keys(scp.build_sp_from_vision(
                        [(r.code, r.description, r.amount, r.column) for r in sec.rows],
                        utile=utile))
                    # Letto PRIMA della catena: dopo net_contra_accounts questa chiave
                    # non descrive piu' la stessa massa.
                    netted = new_bs.get('_netted_contra', Decimal('0'))
                    # Il totale stampato e' LORDO quando i fondi stanno sul passivo: si
                    # misura il lordo contro il lordo (stesso cancello di _hier_reconstruct).
                    rebuilt = new_bs.get('totale_attivo', Decimal('0')) + netted

                    # Stessa post-elaborazione degli altri candidati.
                    if donor_bs is not None:
                        new_bs = scp.overlay_debt_typing(new_bs, donor_bs)
                    new_bs, _contra = scp.net_contra_accounts(
                        new_bs, file_path, text=ocr_text, declared=declared)
                    from importers.pdf_extractor_llm import _reconcile_trial_to_declared
                    _decl = dict(declared or {})
                    _cut = _contra if _contra > 0 else netted
                    if _cut > 0:
                        for _k in ('attivo', 'passivo', 'pareggio'):
                            if _decl.get(_k):
                                _decl[_k] = _decl[_k] - _cut
                    # Indispensabile: build_sp_from_vision ASSERISCE _plug_residual = 0,
                    # non lo misura. E' questa chiamata a sostituirlo con il divario
                    # misurato contro il totale dichiarato — senza, ogni riscatto SP
                    # entrerebbe nel cancello con un miglioramento regalato.
                    new_bs = _reconcile_trial_to_declared(new_bs, _decl, "vision")

                    after = check_quadratura(new_bs, income_data)
                    ok, why = vr.accept_rescue("sp", rebuilt, sec, declared, before, after)
                    logger.info(f"Riscatto vision SP: {'accettato' if ok else 'scartato'} — {why}")
                    if ok:
                        balance_sheet_data = new_bs
                        rescued.append("sp")
        except Exception as err:
            logger.warning(f"Riscatto vision SP fallito ({type(err).__name__}: {err})")

    return balance_sheet_data, income_data, rescued


def _create_balance_sheet(db, financial_year_id: int, data: Dict[str, Decimal]) -> 'BalanceSheet':
    """Create a lossless BalanceSheet record from every ORM ``sp*`` column.

    The previous hand-written constructor silently dropped entire detail families
    (sp01, sp02, sp03, sp05 and sp14).  Deriving the field registry from the model
    makes a newly supported IV-CEE field persist automatically and keeps all import
    routes aligned with the database schema.
    """
    fields = (c.name for c in BalanceSheet.__table__.columns if c.name.startswith('sp'))
    values = {field: data.get(field, Decimal('0')) for field in fields}
    bs = BalanceSheet(financial_year_id=financial_year_id, **values)
    db.add(bs)
    db.flush()
    return bs


def _create_income_statement(db, financial_year_id: int, data: Dict[str, Decimal]) -> 'IncomeStatement':
    """Create a lossless IncomeStatement record from every ORM ``ce*`` column."""
    fields = (c.name for c in IncomeStatement.__table__.columns if c.name.startswith('ce'))
    values = {field: data.get(field, Decimal('0')) for field in fields}
    inc = IncomeStatement(financial_year_id=financial_year_id, **values)
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
    extraction_context: Any = None,
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

    # Normalize: 12 (or more) months is a full year — store as NULL per the
    # FinancialYear convention (NULL = full year, 1-11 = partial). Only 1-11
    # marks a genuine partial-year (infrannuale) record.
    if period_months is not None and period_months >= 12:
        period_months = None

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
        api_key = os.environ.get('ANTHROPIC_API_KEY', '')

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
                    raise PDFImportError(
                        "Il PDF è una scansione (nessun testo selezionabile): questo "
                        "schema non è supportato dall'OCR locale e l'import richiede "
                        "ANTHROPIC_API_KEY."
                    )
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

        # Reject an explicitly contradictory legal statement before choosing an
        # extractor.  Previously this check ran only *after* extraction failed:
        # on a clean text PDF without an API key, a printed Attivo/Passivo mismatch
        # therefore surfaced as the unrelated "ANTHROPIC_API_KEY is required"
        # error.  These are immutable source controls, so no extractor or plug is
        # allowed to hide the contradiction.
        if classification.route == ROUTE_IVCEE and not is_scanned and not _ocr_source:
            try:
                from importers.pdf_extractor_llm import _declared_control_totals

                source_controls = _declared_control_totals(
                    file_path, text=sample_text
                )
                source_attivo = source_controls.get("attivo")
                source_passivo = source_controls.get("passivo")
                if source_attivo is not None and source_passivo is not None:
                    source_difference = abs(source_attivo - source_passivo)
                    if source_difference > Decimal("2"):
                        raise PDFImportError(
                            "Il bilancio sorgente non quadra prima dell'importazione: "
                            f"Totale Attivo €{_euro_it(source_attivo)} != Totale "
                            f"Passivo €{_euro_it(source_passivo)} (scarto "
                            f"€{_euro_it(source_difference)}). "
                            "Correggere il documento contabile originale."
                        )
            except PDFImportError:
                raise
            except Exception as source_control_error:
                # Control discovery is best effort.  If totals are not legible,
                # continue with the existing extraction and semantic gates.
                logger.info(
                    "IV-CEE source preflight unavailable (%s: %s)",
                    type(source_control_error).__name__,
                    source_control_error,
                )

        def _llm_extract():
            """IV CEE extraction via LLM. Returns (bs, ce, prior_bs, prior_ce)."""
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

            if not api_key:
                raise PDFImportError("ANTHROPIC_API_KEY is required for PDF import")
            logger.info("Using LLM extraction (ANTHROPIC_API_KEY found)")
            from importers.pdf_extractor_llm import (
                extract_pdf_with_llm, extract_pdf_both_years_with_llm,
            )
            if period_months:
                # A prior year is optional. Use the dual prompt only when the source
                # physically proves two date columns; a monocolumn partial statement
                # must use the single-year extractor and return no fabricated prior.
                from importers.standard_ivcee_parser import has_comparative_ivcee_columns

                if has_comparative_ivcee_columns(file_path):
                    logger.info(f"Dual-year extraction (period_months={period_months})")
                    return extract_pdf_both_years_with_llm(file_path)
                logger.info(
                    f"Single-year infrannual extraction (period_months={period_months}; "
                    "no prior column detected)"
                )
                bs, ce = extract_pdf_with_llm(file_path, force_llm=True)
                return bs, ce, None, None

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
            from importers.iv_cee_hierarchy import rollup_debiti_aggregates

            def _balances(d):
                return bool(d) and mapper.validate_balance(rollup_debiti_aggregates(d))

            def _attempt():
                """One extraction pass: single-year current + dual pass for the prior,
                falling back to the dual-pass current when the single-year one does not
                balance (dense 4-column layouts trip the single-year prompt)."""
                bs, ce = extract_pdf_with_llm(file_path, force_llm=True)
                prior_bs = prior_ce = None
                try:
                    dual_bs, dual_ce, prior_bs, prior_ce = extract_pdf_both_years_with_llm(file_path)
                    if not _balances(bs) and _balances(dual_bs):
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
        # Sezioni riscattate in vision (route C). Inizializzata QUI, fuori da ogni
        # ramo: il blocco del parser_version la legge su OGNI route, mentre
        # l'assegnazione vive dentro `if candidates:` — una route A/B solleverebbe
        # NameError.
        _rescued_sections = []
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

            # A locally recognised verifica-segno has already been parsed from
            # source coordinates and self-validates against independent SP/CE
            # controls.  Do not let the presence of an API key add a stochastic
            # plain-text OCR candidate that has lost the two-column geometry.
            if api_key and not local_coordinate_ocr:
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
                        _dc0 = _declared_control_totals(file_path, text=ocr_text)
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
                            file_path, text=ocr_text, declared=_dc0)
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
                        balance_sheet_data, file_path, text=ocr_text, declared=_dc0)
                    if _contra > 0:
                        logger.info(f"Route C: contra-netting applicato "
                                    f"({_contra:,.0f} fondi ammortamento/IVA)")
                        # Never clear a pre-existing unexplained difference here.
                        # Netting can correct documented contra-assets, but it cannot
                        # prove that every other unclassified row has been recovered.
                except Exception as _cn_err:
                    logger.warning(f"Route C: contra-netting saltato: {_cn_err}")
                # Anchor sp13 to the document's DECLARED result for the CHOSEN candidate,
                # whatever extractor produced it (the deterministic parser may leave sp13=0
                # or unanchored — budget_342/367). Idempotent on the CoGe result (already
                # reconciled inside the extractor). This makes sp13 = declared before the
                # CE↔SP identity step aligns the CE to it.
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
                try:
                    _donor = next((c[1] for c in candidates if c[3] == "deterministico"), None)
                    balance_sheet_data, income_data, _rescued_sections = _apply_vision_rescue(
                        file_path, balance_sheet_data, income_data,
                        declared=_dc0, donor_bs=_donor, ocr_text=ocr_text)
                    if _rescued_sections:
                        residual = balance_sheet_data.get('_plug_residual', residual)
                        source = f"{source}+vision({'+'.join(_rescued_sections)})"
                except Exception as _vr_err:
                    logger.warning(f"Route C: riscatto vision saltato: {_vr_err}")
                others = ", ".join(f"{s}={r:,.0f}" for r, _b, _c, s in candidates)
                logger.info(f"Route C: scelto estrattore '{source}' (residuo minore "
                            f"{residual:,.0f}); candidati: {others}")
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
                        f"BILANCIO NON QUADRATO ({_sev}): residuo {residual:,.0f} "
                        f"({_pct:.0f}% del totale) non classificato in alcuna voce — "
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
            # Garbled text layer -> the declared Utile/Perdita is unreliable: do not
            # let it arbitrate (a misread CE-section total flips the result sign).
            _decl_ce = (None if _text_garbled
                        else _declared_control_totals(file_path, text=ocr_text))
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
        unbalanced_reason: Optional[str] = None
        if not mapper.validate_balance(balance_sheet_data):
            _verdict = _classify_balance_failure(
                balance_sheet_data,
                is_scanned=is_scanned,
                ocr_source=bool(_ocr_source),
                is_trial_balance=is_trial_balance,
                sample_text=sample_text,
                file_path=file_path,
                ocr_text=ocr_text,
            )
            if _verdict.hard_error:
                raise PDFImportError(_verdict.hard_error)
            # Sbilancio: si importa e si corregge in Rettifiche. forecastable
            # restera' False da solo (semantic_valid include la quadratura),
            # e _validate_forecast_source blocca comunque la proiezione.
            unbalanced_reason = _verdict.warning
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
                balance_sheet_data, income_data, tol=Decimal('2')
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

        warnings = mapper.validate_hierarchy(balance_sheet_data)
        if balance_sheet_data.get("_source_maturity_unspecified"):
            warnings.append(
                "SCADENZA DEBITI NON DISTINTA NEL PDF: il totale Debiti e le sue "
                "sottovoci sono stati conservati nel breve termine; verificare la "
                "quota oltre 12 mesi in Rettifiche se disponibile."
            )
        # Surface the deterministic trial-balance plug flag to the user (Rettifiche cue),
        # so an imperfect-but-imported situazione contabile is visible rather than silent.
        warnings.extend(sc_quadratura_warnings)
        if unbalanced_reason:
            warnings.insert(0, unbalanced_reason)
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
        with open(file_path, "rb") as _source_file:
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
        _critical_ok = _reliability is None or _reliability.all_critical_ok
        _forecastable = _qd.semantic_valid and _critical_ok

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
                    "situazione_contabile_llm" if _coge_ok else "situazione_contabile"
                )
            elif balance_sheet_data.get("_source_mineru_ivcee"):
                _ocr_accounting_method = "ivcee_deterministic"
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
        # dal solo text layer.
        if _rescued_sections:
            _stored_parser_version = (
                f"{_stored_parser_version}+vision-{'-'.join(_rescued_sections)}"
            )[:50]
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
                existing_prior = db.query(FinancialYear).filter(
                    FinancialYear.company_id == company.id,
                    FinancialYear.year == prior_fiscal_year,
                    (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),
                ).first()

                _prior_ok = _should_import_prior(
                    fresh_prior_balances, _prior_q.is_empty,
                    has_existing=existing_prior is not None,
                )
                if not _prior_ok:
                    logger.info(
                        f"Prior year {prior_fiscal_year} extraction is not accounting-valid — "
                        f"{'keeping existing record' if existing_prior else 'not importing it'}"
                    )
                    prior_year_imported = existing_prior is not None
                    warnings.append(
                        f"ANNO PRECEDENTE NON IMPORTATO [{prior_fiscal_year}]: "
                        + "; ".join(_prior_q.warnings)
                    )
                else:
                    if not fresh_prior_balances:
                        warnings.append(
                            f"{_UNBALANCED_WARNING_PREFIX} [ANNO PRECEDENTE "
                            f"{prior_fiscal_year}]: " + "; ".join(_prior_q.warnings)
                            + f". {_UNBALANCED_WARNING_SUFFIX}"
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
                        period_months=None,  # Full 12-month year
                        validation_status=_resolve_validation_status(
                            bool(fresh_prior_balances),
                            _prior_q.semantic_valid,
                        ),
                        validation_report=json.dumps(_prior_validation, ensure_ascii=False),
                        source_sha256=_source_sha256,
                        parser_version=_stored_parser_version,
                        forecastable=_prior_q.semantic_valid,
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
        elif balance_sheet_data.get("_source_mineru_ivcee"):
            extraction_method = "ivcee_deterministic"
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
