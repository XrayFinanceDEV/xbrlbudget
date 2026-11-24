"""Geometria delle colonne comparative: anno corrente, anno precedente, colonne di analisi; ordine di lettura.

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from decimal import Decimal
from typing import Dict, List, NamedTuple, Optional, Tuple
from importers.estrazione_llm.modelli import (
    _parse_it_number,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


_DETACHED_AMOUNT_RE = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$|^-?\d+,\d{2}$")

def _detached_value_page_texts(doc: fitz.Document) -> Dict[int, str]:
    """Rejoin labels and amounts split across two physical page layers.

    A few accounting exports print ``N`` normal pages whose amount cells are all
    ``0,00``, followed by ``N`` headerless pages containing the real amount column.
    Each value keeps the exact vertical coordinate of its placeholder.  Plain text
    extraction therefore sends only zeroes to the LLM even though the visible PDF is
    complete (budget_355/356).

    Return synthetic text for the first half only when the geometry proves this
    layout: an even page count, amount-only second half, at least 30 matches, >=95%
    one-to-one Y coverage, and materially non-zero values.  No accounting value is
    inferred; every replacement comes from one uniquely aligned source cell.
    """
    page_count = len(doc)
    if page_count < 4 or page_count % 2:
        return {}
    half = page_count // 2
    page_words = [page.get_text("words", sort=True) for page in doc]

    value_word_count = sum(len(words) for words in page_words[half:])
    alpha_value_words = sum(
        1
        for words in page_words[half:]
        for word in words
        if re.search(r"[A-Za-zÀ-ÿ]", str(word[4]))
    )
    if value_word_count == 0 or alpha_value_words > max(5, int(value_word_count * 0.02)):
        return {}

    replacements_by_page: Dict[int, Dict[int, str]] = {}
    matched = 0
    placeholder_count = 0
    value_count = 0
    source_mass = Decimal("0")

    for page_index in range(half):
        labels = page_words[page_index]
        values = page_words[page_index + half]
        placeholders = [
            (idx, word)
            for idx, word in enumerate(labels)
            if _DETACHED_AMOUNT_RE.fullmatch(str(word[4]).strip())
        ]
        source_values = [
            word for word in values
            if _DETACHED_AMOUNT_RE.fullmatch(str(word[4]).strip())
        ]
        if not placeholders or not source_values:
            return {}

        placeholder_count += len(placeholders)
        value_count += len(source_values)
        available = set(range(len(placeholders)))
        page_replacements: Dict[int, str] = {}
        for value in source_values:
            candidates = [
                pos for pos in available
                if abs(float(placeholders[pos][1][1]) - float(value[1])) <= 1.0
            ]
            if not candidates:
                continue
            best = min(
                candidates,
                key=lambda pos: abs(float(placeholders[pos][1][1]) - float(value[1])),
            )
            available.remove(best)
            word_index = placeholders[best][0]
            token = str(value[4]).strip()
            page_replacements[word_index] = token
            matched += 1
            parsed = _parse_it_number(token)
            if parsed is not None:
                source_mass += abs(parsed)
        replacements_by_page[page_index] = page_replacements

    coverage = Decimal(matched) / Decimal(max(placeholder_count, value_count, 1))
    if matched < 30 or coverage < Decimal("0.95") or source_mass < Decimal("1000"):
        return {}

    def _render_page(words, replacements: Dict[int, str]) -> str:
        positioned = []
        for idx, word in enumerate(words):
            positioned.append((float(word[1]), float(word[0]), replacements.get(idx, str(word[4]))))
        positioned.sort(key=lambda item: (item[0], item[1]))
        lines: List[str] = []
        current: List[Tuple[float, str]] = []
        line_y: Optional[float] = None
        for y, x, token in positioned:
            if line_y is None or abs(y - line_y) <= 1.0:
                current.append((x, token))
                if line_y is None:
                    line_y = y
                continue
            lines.append(" ".join(text for _, text in sorted(current)))
            current = [(x, token)]
            line_y = y
        if current:
            lines.append(" ".join(text for _, text in sorted(current)))
        return "\n".join(lines)

    logger.warning(
        "Detached amount pages detected: %s/%s cells matched (%.1f%%); "
        "rejoining %s page pairs from source coordinates",
        matched, max(placeholder_count, value_count), float(coverage * 100), half,
    )
    return {
        page_index: _render_page(page_words[page_index], replacements_by_page[page_index])
        for page_index in range(half)
    }

_GEOMETRIC_NUMBER_RE = re.compile(
    r"^\(?-?\d{1,3}(?:\.\d{3})*(?:,\d{2})?\)?-?$"
)

def _comparative_column_words(words) -> List[Tuple]:
    """Return the left-to-right current/prior header words for a table page."""
    for pattern in (r"\d{2}/\d{2}/20\d{2}", r"20\d{2}"):
        candidates = sorted(
            (
                word for word in words
                if re.fullmatch(pattern, str(word[4]).strip())
            ),
            key=lambda word: (float(word[1]), float(word[0])),
        )
        pairs = []
        for first in candidates:
            same_line = sorted(
                (
                    other for other in candidates
                    if other is not first
                    and abs(float(other[1]) - float(first[1])) <= 1
                    and float(other[0]) > float(first[0]) + 25
                ),
                key=lambda word: float(word[0]),
            )
            if same_line:
                pairs.append((first, same_line[0]))
        if pairs:
            # Prefer the financial-statement table on the right over small note
            # tables whose date columns begin near the left margin.
            return list(max(pairs, key=lambda pair: float(pair[0][0])))
    return []

# Intestazioni di colonna scritte a PAROLE, non a date. Il "bilancio riclassificato
# UE" non data le colonne: l'unica data stampata e' il periodo ("dal 01/01/2026 al
# 30/06/2026"), che il riconoscimento per data scambia per una coppia di colonne
# affiancate a meta' pagina. Le vere colonne sono intestate
# ``Importo corrente | Importo comparato | Scostamento | %`` e sono allineate a
# DESTRA sul bordo della propria intestazione: l'ancora e' quindi il bordo destro
# (``word[2]``), non il centro.
_CURRENT_COLUMN_HEADERS = ('corrente',)

_PRIOR_COLUMN_HEADERS = ('comparato', 'precedente', 'confronto')

# Colonne di ANALISI, non contabili: vanno riconosciute per non essere scambiate
# per la colonna del comparato (su una riga a corrente vuoto lo scostamento e la
# percentuale sono gli unici altri numeri stampati, e senza queste ancore il
# confronto "piu' vicino fra due" li attribuirebbe all'anno precedente).
_ANALYSIS_COLUMN_HEADERS = ('scostamento', 'scost.', 'differenza', 'variazione', '%')

class _ColumnAnchors(NamedTuple):
    """Ancore orizzontali delle colonne numeriche di un prospetto comparato.

    ``right_edge`` distingue le due grafie: le colonne intestate a parole sono
    allineate al bordo destro dell'intestazione, quelle intestate a date si
    riconoscono dal centro (comportamento storico, lasciato invariato).
    """

    current: float
    prior: float
    others: Tuple[float, ...]
    right_edge: bool

def _text_line_groups(words) -> List[List[Tuple]]:
    """Raggruppa le parole per riga fisica (stessa baseline entro 1pt)."""
    groups: List[List[Tuple]] = []
    for word in sorted(words, key=lambda item: (float(item[1]), float(item[0]))):
        if not groups or abs(float(word[1]) - float(groups[-1][0][1])) > 1.0:
            groups.append([word])
        else:
            groups[-1].append(word)
    return groups

# Quanto puo' discostarsi il valore ESTRATTO dall'importo stampato nella cella del
# comparato perche' i due si riconoscano come lo stesso numero. Non e' una
# tolleranza contabile: e' un controllo di IDENTITA', il cinturino di sicurezza che
# impedisce di azzerare un campo diverso da quello che ha preso il comparato. Chi
# decide che il valore corrente e' zero e' la geometria (la cella e' vuota), non
# questa soglia. Un euro perche' l'estrazione LLM non e' deterministica e a volte
# restituisce l'importo troncato ai centesimi (90.603,75 -> 90603): a cento
# centesimi di distanza si parla ancora dello stesso importo, a un euro di distanza
# non esiste un'altra voce di bilancio con cui confonderlo.
_PRIOR_CELL_MATCH_TOL = Decimal('1')

def _row_code_words(labels) -> List[str]:
    """Il codice di voce di una riga di prospetto: la PRIMA parola dell'etichetta.

    Prendere tutte le parole del margine sinistro sembra piu' generoso ed e'
    invece una trappola: nell'etichetta "D) Ratei e risconti" la congiunzione
    ``e`` supera un confronto ``^E[.)]?$`` insensibile alle maiuscole, e la voce
    dell'ATTIVO si spaccia per la ``E)`` del passivo. Il codice, quando c'e', sta
    sempre in testa alla riga.
    """
    ordered = sorted(labels, key=lambda word: float(word[0]))
    if not ordered or float(ordered[0][0]) >= 130:
        return []
    return [str(ordered[0][4]).strip()]

def _labelled_column_anchors(words) -> Optional[_ColumnAnchors]:
    """Ancore lette da un'intestazione ``corrente | comparato | ...`` stampata."""
    for line in _text_line_groups(words):
        current_word = prior_word = None
        for word in sorted(line, key=lambda item: float(item[0])):
            if float(word[0]) < 250:
                continue  # colonne numeriche: mai a ridosso del margine sinistro
            token = str(word[4]).strip().casefold().strip(':')
            if current_word is None:
                if token in _CURRENT_COLUMN_HEADERS:
                    current_word = word
            elif prior_word is None and token in _PRIOR_COLUMN_HEADERS:
                prior_word = word
        if current_word is None or prior_word is None:
            continue
        current_x = float(current_word[2])
        prior_x = float(prior_word[2])
        if prior_x - current_x < 25:
            continue
        others = tuple(
            float(word[2]) for word in line
            if float(word[0]) > prior_x
            and str(word[4]).strip().casefold() in _ANALYSIS_COLUMN_HEADERS
        )
        return _ColumnAnchors(current_x, prior_x, others, True)
    return None

def _page_column_anchors(
    words, document_centers: Optional[Tuple[float, float]] = None
) -> Optional[_ColumnAnchors]:
    """Ancore di colonna della pagina: prima le intestazioni a parole, poi le date."""
    labelled = _labelled_column_anchors(words)
    if labelled is not None:
        return labelled
    date_words = _comparative_column_words(words)
    if len(date_words) >= 2:
        current_x = (float(date_words[0][0]) + float(date_words[0][2])) / 2
        prior_x = (float(date_words[1][0]) + float(date_words[1][2])) / 2
    elif document_centers is not None:
        current_x, prior_x = document_centers
    else:
        return None
    if prior_x - current_x < 25:
        return None
    return _ColumnAnchors(current_x, prior_x, (), False)

def _column_of(word, anchors: _ColumnAnchors) -> str:
    """``'current'`` / ``'prior'`` / ``'other'``: colonna piu' vicina all'importo."""
    x = float(word[2]) if anchors.right_edge else (float(word[0]) + float(word[2])) / 2
    best_name = 'current'
    best_distance = abs(x - anchors.current)
    candidates = [('prior', anchors.prior)]
    candidates.extend(('other', anchor) for anchor in anchors.others)
    for name, anchor in candidates:
        distance = abs(x - anchor)
        if distance < best_distance:
            best_name, best_distance = name, distance
    return best_name

def _split_current_prior(numbers, anchors: _ColumnAnchors) -> Tuple[List, List]:
    current_numbers, prior_numbers = [], []
    for word in numbers:
        column = _column_of(word, anchors)
        if column == 'current':
            current_numbers.append(word)
        elif column == 'prior':
            prior_numbers.append(word)
    return current_numbers, prior_numbers

def _document_comparative_centers(doc: fitz.Document) -> Optional[Tuple[float, float]]:
    pairs = []
    for page in doc:
        headers = _comparative_column_words(page.get_text('words', sort=True))
        if len(headers) < 2:
            continue
        centers = tuple((float(word[0]) + float(word[2])) / 2 for word in headers)
        if centers[0] > 350 and centers[1] - centers[0] >= 25:
            pairs.append(centers)
    return max(pairs, key=lambda pair: pair[0]) if pairs else None

def _filter_difference_columns(page: fitz.Page) -> Optional[str]:
    """Return row-wise text without DIFFERENZA/SCOST. analysis columns.

    Some ERP exports have four numeric columns (current year, prior year,
    difference, percentage).  The two-year prompt otherwise interprets the
    repeated difference as another accounting value (budget_314).  Geometry is
    unambiguous: retain both ``ESERCIZIO`` columns and drop only words at or to the
    right of the printed ``DIFFERENZA`` header.
    """
    words = page.get_text('words', sort=True)
    # le colonne-anno: "2025" o una data "30/06/2026" (budget_1445, Crystal Reports)
    year_words = [
        word for word in words
        if re.fullmatch(r"(?:\d{2}[/.\-]\d{2}[/.\-])?20\d{2}", str(word[4]).strip())
    ]
    years = {str(word[4]).strip()[-4:] + str(word[4]).strip() for word in year_words}
    if len(years) < 2:
        return None
    first_year_x = min(float(word[0]) for word in year_words)
    # un'intestazione di differenza sta a destra delle colonne-anno: "Differenza tra valore e
    # costi" e' una didascalia del CE, a sinistra, e non taglia la pagina
    difference_headers = [
        word for word in words
        if float(word[0]) > first_year_x
        and (str(word[4]).strip().casefold().startswith('differenza')
             or str(word[4]).strip().casefold() in ('diff.', 'diff'))
    ]
    has_deviation = any(
        str(word[4]).strip().casefold().startswith('scost') or str(word[4]).strip() == '%'
        for word in words
    )
    if not difference_headers or not has_deviation:
        return None
    cutoff_x = min(float(word[0]) for word in difference_headers) - 2
    kept = [word for word in words if float(word[0]) < cutoff_x]
    positioned = sorted(kept, key=lambda word: (float(word[1]), float(word[0])))
    lines: List[str] = []
    current: List[Tuple[float, str]] = []
    line_y: Optional[float] = None
    for word in positioned:
        y, x, token = float(word[1]), float(word[0]), str(word[4])
        if line_y is None or abs(y - line_y) <= 1.0:
            current.append((x, token))
            if line_y is None:
                line_y = y
            continue
        lines.append(' '.join(text for _, text in sorted(current)))
        current = [(x, token)]
        line_y = y
    if current:
        lines.append(' '.join(text for _, text in sorted(current)))
    logger.warning(
        "Filtered DIFFERENZA/SCOST. columns at x>=%.1f from source page %s",
        cutoff_x, page.number + 1,
    )
    return '\n'.join(lines)

# Ordine di lettura: minimo di blocchi sotto il quale la statistica non e'
# significativa, e quota di inversioni verticali oltre la quale lo stream e'
# considerato fuori ordine (un salto all'indietro isolato e' normale: colonne
# affiancate, note a pie' di pagina, intestazioni ripetute).
_SCRAMBLED_MIN_BLOCKS = 6

_SCRAMBLED_INVERSION_PCT = 0.25

_SCRAMBLED_LINE_TOL = 1.0

def _stream_order_is_scrambled(page: fitz.Page) -> bool:
    """True quando il content-stream emette il testo fuori dall'ordine di lettura.

    ``page.get_text()`` segue l'ordine in cui il generatore ha SCRITTO il testo,
    non quello in cui il documento si LEGGE. Alcuni export disegnano il prospetto
    dal basso verso l'alto, o disegnano la seconda colonna importi come blocco
    staccato: le etichette si legano allora agli importi della colonna sbagliata
    e l'anno precedente viene importato come anno corrente (il "Bilancio
    riclassificato / Fascicolo" leggeva la colonna 2024 come 2025, e attribuiva
    gli oneri finanziari «altri» alla voce D.18 Rivalutazioni che li precede
    nello stream, gonfiando l'utile CE).

    Il criterio e' geometrico e deterministico: si contano i salti verticali
    all'indietro fra blocchi consecutivi nell'ordine di stream.
    """
    try:
        blocks = [b for b in page.get_text("blocks") if str(b[4]).strip()]
    except Exception:  # pagina illeggibile: nessuna diagnosi, nessun cambiamento
        return False
    if len(blocks) < _SCRAMBLED_MIN_BLOCKS:
        return False
    tops = [float(b[1]) for b in blocks]
    inversions = sum(
        1 for previous, current in zip(tops, tops[1:])
        if current < previous - _SCRAMBLED_LINE_TOL
    )
    return inversions > len(tops) * _SCRAMBLED_INVERSION_PCT

def reading_order_text(page: fitz.Page, forza_ordinamento: bool = False) -> str:
    """Testo della pagina nell'ordine in cui e' STAMPATA.

    Restituisce il testo grezzo (byte-identico a ``page.get_text()``) quando lo
    stream e' gia' in ordine — cosi' i PDF ben formati, su cui i prompt sono
    tarati, non cambiano di un carattere — e passa all'ordinamento per
    coordinate solo sulle pagine dimostrabilmente scomposte.

    ``forza_ordinamento`` (fix round 1, Task 22 G3, ruling del proprietario 2026-09-28,
    diagnosi budget_297): ``_stream_order_is_scrambled`` e' un criterio a livello di PAGINA
    (conta le inversioni fra blocchi); un singolo rigo fuori ordine ("3.680.418\\n2.428.464\\n
    TOTALE ATTIVO", il numero scritto PRIMA della propria etichetta - una riga sola, non un
    blocco) non lo supera, e la pagina resta "non scomposta" anche se quella riga sola lo e'.
    Passando ``forza_ordinamento=True`` si tenta SEMPRE l'ordinamento per coordinate, con la
    stessa guardia di sicurezza sotto (mai se cambia le parole): usato solo dal chiamante che
    lo richiede esplicitamente (``totali_stampati``, l'importatore) - ogni altro
    chiamante (default ``False``) resta sul comportamento di sempre, byte-identico."""
    raw = page.get_text()
    if not forza_ordinamento and not _stream_order_is_scrambled(page):
        return raw
    ordered = page.get_text(sort=True)
    # Riordinare e' SPOSTARE, non riscrivere: se le parole in uscita non sono
    # piu' quelle della pagina, l'ordinamento ha fatto danni e vale meno dello
    # stream grezzo. Succede sulle stampe che disegnano la sottolineatura come
    # glifi `_` su una baseline di pochi punti piu' in basso (situazioni
    # contabili AGO): l'ordinamento salda la riga di underscore all'importo che
    # la precede — `1.468.999,24______________` — e quell'importo smette di
    # essere un numero per chiunque lo legga, LLM compreso.
    if sorted(ordered.split()) != sorted(raw.split()):
        logger.warning(
            "Riordino per coordinate scartato a pagina %s: cambierebbe le parole "
            "della pagina (importi saldati alla sottolineatura); si tiene il "
            "content-stream grezzo", page.number + 1,
        )
        return raw
    logger.warning(
        "Content-stream fuori ordine di lettura a pagina %s: testo riordinato "
        "per coordinate (altrimenti etichette e importi si legano alla colonna "
        "sbagliata)", page.number + 1,
    )
    return ordered
