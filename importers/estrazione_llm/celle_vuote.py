"""Celle dell'anno corrente rimaste vuote sul prospetto: si riconciliano con la colonna stampata.

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from importers.estrazione_llm.modelli import (
    _parse_it_number,
)
from importers.estrazione_llm.colonne import (
    _ColumnAnchors, _GEOMETRIC_NUMBER_RE, _PRIOR_CELL_MATCH_TOL, _document_comparative_centers,
    _page_column_anchors, _row_code_words, _split_current_prior, _text_line_groups,
)
from importers.estrazione_llm.pagine import (
    find_section_pages,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


# Voci di CE la cui cella dell'anno corrente puo' restare VUOTA su un prospetto
# comparato: la riga stampa allora tre numeri invece di quattro (comparato,
# scostamento, %) e la lettura lineare prende il primo, cioe' l'anno precedente.
# Ogni voce porta i propri importi sulla stessa baseline dell'etichetta, quindi si
# legge per riga fisica; il codice di voce stampato e le parole obbligatorie
# rendono il riconoscimento inequivocabile.
#   - ce03a: A.4 "Incrementi di immobilizzazioni per lavori interni"
#   - ce09d: B.10.d "Svalutazioni dei crediti compresi nell'attivo circolante"
#   - ce20: 20) "Imposte sul reddito dell'esercizio" (anche quando la voce non ha
#     il dettaglio 20.a/20.b su cui lavora il passo per segmenti piu' sotto)
_BLANK_CURRENT_CE_ROWS = {
    'ce03a_incrementi_immobilizzazioni': (
        re.compile(r"^(?:A\.?)?4\)[,]?$", re.I),
        ('incrementi', 'immobilizzazioni', 'lavori', 'interni'),
    ),
    'ce09d_svalutazione_crediti': (
        re.compile(r"^(?:B\.?)?(?:10\.?)?d\)[,]?$", re.I),
        ('svalutazioni', 'crediti'),
    ),
    'ce20_imposte': (
        re.compile(r"^(?:20|22)\)[,]?$"),
        ('imposte', 'reddito'),
    ),
}

def _prior_cell_with_sibling_sign(printed, extracted):
    """L'importo stampato nella cella comparata, con la convenzione dei fratelli.

    Il ripesco gira DOPO ``_normalize_ce_signs``: scrivere in ``prior`` il token
    grezzo del PDF vi deposita l'unico valore del dizionario che la
    normalizzazione non ha mai visto. Su un prospetto che stampa i costi fra
    parentesi il campo esce negativo accanto a fratelli tutti positivi, e il
    risultato dell'anno precedente si sposta di 2x l'importo senza che nulla lo
    segnali.

    La cella stampata resta l'autorita' sulla GRANDEZZA (il ripesco esiste per
    leggerla dalla fonte); il SEGNO viene dal valore che l'estrattore aveva
    attribuito all'anno corrente, che la normalizzazione ha gia' trattato come i
    suoi fratelli. Le due grandezze sono note uguali a meno di
    ``_PRIOR_CELL_MATCH_TOL``: e' la condizione che il chiamante ha appena
    verificato, ed e' cio' che rende lecito prendere il segno dall'una e il
    valore dall'altra. Su un PDF a convenzione positiva i due segni coincidono
    gia' e nulla cambia.
    """
    magnitude = abs(printed)
    return -magnitude if extracted < 0 else magnitude

def _page_has_current_column_values(words, anchors: _ColumnAnchors) -> bool:
    """Almeno una riga della pagina porta un importo nella colonna dell'anno CORRENTE.

    Serve a distinguere una cella vuota da un'ANCORA SBAGLIATA, che si somigliano
    ma non sono la stessa cosa. Su `budget_609` la pagina del conto economico non
    stampa intestazioni di data: le ancore arrivano dal livello di documento, da
    un'altra pagina, e cadono a sinistra di ENTRAMBE le colonne reali (che sono
    allineate a destra a x1=488 e x1=546). Tutti e 70 gli importi finiscono in
    «comparato» e il meccanismo vede 36 celle correnti vuote su 36 righe.

    La guardia di identita' non basta li': il campo CONTIENE davvero il numero che
    la geometria chiama comparato, perche' quel numero e' il valore corrente. Su
    `17-bis) utili e perdite su cambi` — un importo solo, perche' il 2024 stampa un
    trattino — l'identita' tornava e il valore reale -5.103 veniva azzerato.

    Una pagina INTERA senza un solo valore corrente non e' un esercizio vuoto: e'
    un'ancora sbagliata. Il confronto e' netto e misurato — 0 valori correnti su 70
    (`budget_609`) contro 18 su 23 (`budget_391`, dove la cella vuota e' vera e
    l'azzeramento va fatto).
    """
    for line in _text_line_groups(words):
        numbers = [
            word for word in line
            if float(word[0]) > 350
            and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
        ]
        if not numbers:
            continue
        current_numbers, _prior = _split_current_prior(numbers, anchors)
        if current_numbers:
            return True
    return False

def _clear_blank_current_rows(
    words,
    anchors: _ColumnAnchors,
    specs: Dict[str, Tuple[re.Pattern, Tuple[str, ...]]],
    current: Dict[str, Decimal],
    prior: Dict[str, Decimal],
) -> List[Tuple[str, str]]:
    """Azzera i campi la cui riga stampa un importo SOLO nella colonna comparato.

    Nessun valore viene dedotto: si legge la geometria della riga, e si agisce solo
    quando la cella dell'anno corrente e' dimostrabilmente vuota e quella del
    comparato contiene l'importo che l'estrattore ha attribuito all'anno corrente.
    """
    cleared: List[Tuple[str, str]] = []
    # Ancore sbagliate: senza questo, ogni riga della pagina risulta a cella corrente
    # vuota e la guardia di identita' non se ne accorge. Vedi _page_has_current_column_values.
    if not _page_has_current_column_values(words, anchors):
        return cleared
    for line in _text_line_groups(words):
        labels = [word for word in line if float(word[0]) < 350]
        label_text = ' '.join(str(word[4]).casefold() for word in labels)
        codes = _row_code_words(labels)
        if not codes:
            continue
        numbers = [
            word for word in line
            if float(word[0]) > 350
            and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
        ]
        if not numbers:
            continue
        for field, (code_re, required_words) in specs.items():
            if not all(token in label_text for token in required_words):
                continue
            if not any(code_re.fullmatch(code) for code in codes):
                continue
            current_numbers, prior_numbers = _split_current_prior(numbers, anchors)
            if current_numbers or not prior_numbers:
                continue
            parsed = [_parse_it_number(str(word[4])) for word in prior_numbers]
            parsed = [value for value in parsed if value is not None]
            if not parsed or any(value != parsed[0] for value in parsed[1:]):
                continue
            extracted = current.get(field, Decimal('0'))
            if (
                parsed[0] == 0
                or extracted == 0
                or abs(abs(extracted) - abs(parsed[0])) > _PRIOR_CELL_MATCH_TOL
            ):
                continue
            current[field] = Decimal('0')
            recovered = _prior_cell_with_sibling_sign(parsed[0], extracted)
            if prior:
                prior[field] = recovered
            cleared.append((field, str(recovered)))
    return cleared

def _reconcile_blank_current_ce_cells(
    file_path: str,
    current_ce: Dict[str, Decimal],
    prior_ce: Optional[Dict[str, Decimal]] = None,
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Clear CE values copied from a prior-year-only visual cell.

    PyMuPDF's linear text loses empty table cells.  On comparative statements this
    can make a lone prior-year amount look like the current value (budget_391 A.2,
    budget_328/144 B.11).  Use the printed date-column X coordinates and the legal
    item row bounds to act only when the current cell is geometrically empty and the
    prior cell contains an explicit amount.
    """
    current = dict(current_ce)
    prior = dict(prior_ce or {})
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current, prior

    target_specs = {
        'ce02_variazioni_rimanenze': (
            re.compile(r"^2\)[,]?$"),
            ('variazioni', 'rimanenze', 'prodotti'),
        ),
        'ce10_var_rimanenze_mat_prime': (
            re.compile(r"^11\)[,]?$"),
            ('variazioni', 'rimanenze', 'materie'),
        ),
        'ce11_accantonamenti': (
            re.compile(r"^(?:B\.)?12\)[,]?$", re.I),
            ('accanton', 'rischi'),
        ),
        'ce15_oneri_finanziari': (
            re.compile(r"^17\)[,]?$"),
            ('interessi', 'oneri', 'finanziari'),
        ),
        'ce20_imposte': (
            re.compile(r"^(?:20|22)\)[,]?$"),
            ('imposte', 'reddito'),
        ),
    }
    cleared: List[Tuple[str, str]] = []
    document_centers = _document_comparative_centers(doc)
    try:
        for page in doc:
            words = page.get_text('words', sort=True)
            anchors = _page_column_anchors(words, document_centers)
            if anchors is None:
                continue
            cleared.extend(
                _clear_blank_current_rows(
                    words, anchors, _BLANK_CURRENT_CE_ROWS, current, prior
                )
            )

            item_words = sorted(
                (
                    word for word in words
                    if float(word[0]) < 125
                    and re.fullmatch(
                        r"(?:B\.)?\d+\)[,]?",
                        str(word[4]).strip(),
                        re.I,
                    )
                ),
                key=lambda word: float(word[1]),
            )
            for position, item_word in enumerate(item_words):
                start_y = float(item_word[1]) - 1
                next_item = next(
                    (
                        candidate for candidate in item_words[position + 1:]
                        if float(candidate[1]) > float(item_word[1]) + 2
                    ),
                    None,
                )
                next_y = (
                    float(next_item[1]) - 1
                    if next_item is not None
                    else float(item_word[3]) + 35
                )
                segment = [
                    word for word in words
                    if start_y <= float(word[1]) < next_y
                ]
                segment_text = ' '.join(str(word[4]).lower() for word in segment)
                for field, (code_re, required_words) in target_specs.items():
                    if not code_re.fullmatch(str(item_word[4]).strip()):
                        continue
                    if not all(token in segment_text for token in required_words):
                        continue
                    numbers = [
                        word for word in segment
                        if float(word[0]) > 350
                        and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
                    ]
                    if field == 'ce20_imposte':
                        # Item 20 often has a detailed 20.a/20.b breakdown below it.
                        # The top-level amount on the code baseline is the only value
                        # that proves whether the current aggregate cell is blank.
                        same_row = [
                            word for word in numbers
                            if abs(float(word[1]) - float(item_word[1])) <= 1
                        ]
                        if same_row:
                            numbers = same_row
                    elif field == 'ce15_oneri_finanziari':
                        # The 17) label can be followed by a detail line, its subtotal,
                        # and then the unrelated C total.  Prefer the explicit subtotal
                        # row so values from C cannot be mistaken for this item.
                        line_groups: List[List[Tuple]] = []
                        for word in sorted(
                            segment, key=lambda item: (float(item[1]), float(item[0]))
                        ):
                            if (
                                not line_groups
                                or abs(float(word[1]) - float(line_groups[-1][0][1])) > 1
                            ):
                                line_groups.append([word])
                            else:
                                line_groups[-1].append(word)
                        subtotal_numbers: List[Tuple] = []
                        for line in line_groups:
                            line_text = ' '.join(
                                str(word[4]).casefold() for word in line
                            )
                            if all(
                                token in line_text
                                for token in ('totale', 'interessi', 'oneri', 'finanziari')
                            ):
                                subtotal_numbers = [
                                    word for word in line
                                    if float(word[0]) > 350
                                    and _GEOMETRIC_NUMBER_RE.fullmatch(
                                        str(word[4]).strip()
                                    )
                                ]
                                break
                        if subtotal_numbers:
                            numbers = subtotal_numbers
                    current_numbers, prior_numbers = _split_current_prior(
                        numbers, anchors
                    )
                    if current_numbers or not prior_numbers:
                        continue
                    # Repeated rendering of the same row is harmless; all observed
                    # prior values must agree before the current field is cleared.
                    parsed = [_parse_it_number(str(word[4])) for word in prior_numbers]
                    parsed = [value for value in parsed if value is not None]
                    if not parsed or any(value != parsed[0] for value in parsed[1:]):
                        continue
                    extracted = current.get(field, Decimal('0'))
                    if (
                        parsed[0] == 0
                        or extracted == 0
                        or abs(abs(extracted) - abs(parsed[0])) > _PRIOR_CELL_MATCH_TOL
                    ):
                        continue
                    current[field] = Decimal('0')
                    recovered = _prior_cell_with_sibling_sign(parsed[0], extracted)
                    if prior:
                        prior[field] = recovered
                    cleared.append((field, str(recovered)))
    finally:
        doc.close()

    if cleared:
        logger.warning(
            "CE column geometry: cleared prior-only cells from current year: %s",
            cleared,
        )
    return current, prior

def _reconcile_blank_current_sp_cells(
    file_path: str,
    current_bs: Dict[str, Decimal],
    prior_bs: Optional[Dict[str, Decimal]] = None,
) -> Tuple[Dict[str, Decimal], Dict[str, Decimal]]:
    """Clear selected SP fields proven to exist only in the prior column.

    This is the balance-sheet counterpart of
    :func:`_reconcile_blank_current_ce_cells`.  The target labels are deliberately
    narrow and legally unambiguous; values are never derived from the balance gap.
    """
    current = dict(current_bs)
    prior = dict(prior_bs or {})
    specs = {
        'sp02_immob_immateriali': (('immobilizzazioni', 'immateriali'), re.compile(r"^I[.)]?$", re.I)),
        'sp14_fondi_rischi': (('fondi', 'rischi', 'oneri'), re.compile(r"^B[.)]?$", re.I)),
        'sp18_ratei_risconti_passivi': (('ratei', 'risconti'), re.compile(r"^E[.)]?$", re.I)),
    }
    try:
        doc = fitz.open(file_path)
    except Exception:
        return current, prior
    cleared: List[Tuple[str, str]] = []
    try:
        selected_sp_pages, _ = find_section_pages(file_path)
    except Exception:
        selected_sp_pages = set()
    document_centers = _document_comparative_centers(doc)
    try:
        for page in doc:
            if selected_sp_pages and page.number not in selected_sp_pages:
                continue
            words = page.get_text('words', sort=True)
            # Some statement pages repeat the two numeric columns but not the
            # date header.  Reuse only a document-level pair proven by another
            # page of the same comparative statement (budget_282/336/397).
            anchors = _page_column_anchors(words, document_centers)
            if anchors is None:
                continue

            for line in _text_line_groups(words):
                labels = [word for word in line if float(word[0]) < 350]
                label_text = ' '.join(str(word[4]).casefold() for word in labels)
                codes = _row_code_words(labels)
                for field, (required, code_re) in specs.items():
                    if not all(token in label_text for token in required):
                        continue
                    if not any(code_re.fullmatch(code) for code in codes):
                        continue
                    numbers = [
                        word for word in line
                        if float(word[0]) > 350
                        and _GEOMETRIC_NUMBER_RE.fullmatch(str(word[4]).strip())
                    ]
                    current_numbers, prior_numbers = _split_current_prior(
                        numbers, anchors
                    )
                    if current_numbers or not prior_numbers:
                        continue
                    parsed = [_parse_it_number(str(word[4])) for word in prior_numbers]
                    parsed = [value for value in parsed if value is not None]
                    if not parsed or any(value != parsed[0] for value in parsed[1:]):
                        continue
                    extracted = current.get(field, Decimal('0'))
                    if (
                        parsed[0] == 0
                        or extracted == 0
                        or abs(abs(extracted) - abs(parsed[0])) > _PRIOR_CELL_MATCH_TOL
                    ):
                        continue
                    current[field] = Decimal('0')
                    recovered = _prior_cell_with_sibling_sign(parsed[0], extracted)
                    if prior:
                        prior[field] = recovered
                    cleared.append((field, str(recovered)))
    finally:
        doc.close()
    if cleared:
        logger.warning(
            "SP column geometry: cleared prior-only cells from current year: %s",
            cleared,
        )
    return current, prior
