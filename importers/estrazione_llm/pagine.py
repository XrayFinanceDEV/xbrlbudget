"""Le pagine di SP e CE dentro il PDF e il loro testo.

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from typing import Set, Tuple
from importers.estrazione_llm.modelli import (
    PDFImportError,
)
from importers.estrazione_llm.colonne import (
    _detached_value_page_texts, _filter_difference_columns, reading_order_text,
)
from importers.estrazione_llm.formati import (
    _preprocess_datev_koinos, _preprocess_stampa_dettaglio, _preprocess_zucchetti, _strip_separator_noise,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


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

# Quante pagine, al massimo, puo' occupare la sezione patrimoniale quando il
# documento non stampa alcun totale di chiusura del passivo. Non e' un'ancora,
# e' una TAGLIA: serve solo a impedire che «l'SP finisce dove comincia il CE»
# si mangi tutto cio' che sta in mezzo quando in mezzo c'e' una Nota
# Integrativa. Sei pagine sono il doppio del vecchio default (sp_start + 2) e
# lasciano due pagine di margine sul caso piu' lungo osservato nel corpus — il
# riclassificato UE di AMB AMBIENTA, che di pagine patrimoniali ne usa quattro.
_SP_SECTION_MAX_PAGES = 6

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
        # Collapse a spaced dash used as a label separator so section-total
        # keywords match regardless of it: "totale stato patrimoniale - passivo"
        # → "totale stato patrimoniale passivo" (some gestionali print the
        # closing total with a " - PASSIVO" suffix; without this the SP_END
        # anchor is missed and the CE bleeds into the SP page range). Only the
        # spaced form is touched, so account codes like "d-bis" are preserved.
        lowered = re.sub(r' [-–—] ', ' ', lowered)
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
            # Nessun "Totale passivo" stampato. Il default storico (sp_start + 2)
            # e' una TAGLIA, non un'ancora: su un prospetto piu' lungo di tre
            # pagine chiude la sezione patrimoniale a meta' del passivo e la coda
            # non arriva mai al prompt. Sul bilancio riclassificato UE di AMB
            # AMBIENTA (che i totali di sezione li stampa nell'intestazione, non
            # in coda) "E) Ratei e risconti" 178.663,25 sta a pagina 4 e spariva:
            # sp18 restava 0 mentre il "D) Ratei e risconti" dell'attivo, a
            # pagina 2, arrivava regolarmente in sp10.
            # L'ancora onesta e' il documento stesso: la sezione patrimoniale
            # finisce dove comincia quella economica. La pagina che apre il CE e'
            # INCLUSA perche' su questi layout porta ancora le ultime righe del
            # passivo (ed e' la stessa condivisione che il ramo `ce_start`
            # qui sotto gia' ammette nel verso opposto).
            # Il tetto resta comunque: fra l'SP e il CE puo' esserci una Nota
            # Integrativa lunga, e li' il prospetto delle immobilizzazioni e la
            # tabella dei debiti per scadenza ci sono quasi sempre — con numeri
            # LORDI e in colonne diverse. Sono le stesse tabelle che gli scanner
            # geometrici in giro su `sp_pages` leggerebbero volentieri al posto
            # del prospetto, e un dettaglio preso dalle note attraversa un
            # aggregato senza che il pareggio se ne accorga.
            ce_header_page = _find_start(CE_START_KEYWORDS, after_page=sp_start + 1)
            cap = min(sp_start + _SP_SECTION_MAX_PAGES - 1, total_pages - 1)
            if ce_header_page is not None and ce_header_page > sp_start:
                sp_end = min(ce_header_page, cap)
                logger.warning(
                    "Nessun totale di chiusura del passivo stampato: la sezione SP "
                    "si chiude a pagina %s (%s). Apertura del CE a pagina %s, tetto "
                    "di sezione a pagina %s.",
                    sp_end + 1,
                    "apertura del CE" if sp_end == ce_header_page else "tetto di sezione",
                    ce_header_page + 1, cap + 1,
                )
            else:
                sp_end = min(sp_start + 2, total_pages - 1)

    # --- CE range ---
    # CE start: search after SP start to avoid re-matching the SP header page.
    # Strategy: try strict match first (both "conto economico" + "valore della produzione"),
    # then try "valore della produzione" alone after SP end (Dylog format puts VP on last
    # SP page without a "conto economico" header until a later page).
    ce_after = (sp_start + 1) if sp_start is not None else 0
    # Compact filings can start the CE on the very page that closes the SP.  Prefer
    # that source page before searching later pages; otherwise a second statement
    # quoted inside the Nota Integrativa can be selected (budget_336).
    ce_start = (
        sp_end
        if sp_end is not None
        and all(keyword in page_texts[sp_end] for keyword in CE_START_KEYWORDS)
        else _find_start(CE_START_KEYWORDS, after_page=ce_after)
    )
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
        # Cerved statements often print rounded totals as Italian integers
        # (``469.102``), with no decimal comma.  Ignoring those values made a real
        # SP page look empty and could relocate the section into the notes
        # (budget_272).  The boundaries deliberately exclude dates and fractions.
        amount_re = re.compile(
            r'(?<![\d/])(?:-?\d[\d.]*,\d{2}|-?\d{1,3}(?:\.\d{3})+)(?![\d/])'
        )
        for tok in amount_re.findall(text):
            try:
                s += abs(float(tok.replace('.', '').replace(',', '.')))
            except ValueError:
                continue
        return s

    page_mass = [_page_amount_mass(t) for t in page_texts]
    doc_max_mass = max(page_mass) if page_mass else 0.0
    sp_mass = sum(page_mass[p] for p in sp_pages)
    selected_sp_text = ' '.join(page_texts[p] for p in sorted(sp_pages))
    selected_sp_has_controls = (
        'totale attivo' in selected_sp_text
        and 'totale passivo' in selected_sp_text
    )
    if (
        sp_pages
        and not selected_sp_has_controls
        and doc_max_mass > 0
        and sp_mass < 0.02 * doc_max_mass
    ):
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

    detached_texts = _detached_value_page_texts(doc)
    def _page_text(page_index: int) -> str:
        if page_index in detached_texts:
            return detached_texts[page_index]
        page = doc[page_index]
        return _filter_difference_columns(page) or reading_order_text(page)

    sp_text = "\n".join(
        _page_text(p) for p in sorted(sp_pages)
    )
    ce_text = "\n".join(
        _page_text(p) for p in sorted(ce_pages)
    )
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

def _extract_full_text(file_path: str, max_pages: int = 60, forza_ordinamento: bool = False) -> str:
    """Return the concatenated text of (up to max_pages) PDF pages.

    Trial balances have no IV-CEE section headers to anchor on, so the whole
    account list is sent to the LLM rather than a detected SP/CE window.

    ``forza_ordinamento`` (fix round 1, Task 22 G3): passato a ``reading_order_text`` -
    solo il chiamante che lo richiede esplicitamente lo forza; il default resta invariato.
    """
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise PDFImportError(f"Cannot open PDF file: {e}")
    detached_texts = _detached_value_page_texts(doc)
    effective_pages = (len(doc) // 2) if detached_texts else len(doc)
    parts = []
    for i, page in enumerate(doc):
        if i >= effective_pages:
            break
        if i >= max_pages:
            break
        parts.append(
            detached_texts.get(i)
            or _filter_difference_columns(page)
            or reading_order_text(page, forza_ordinamento=forza_ordinamento)
        )
    doc.close()
    return "\n".join(parts)
