"""Il risultato d'esercizio in modo "conti": stesse regole del vecchio parser best-effort
(``situazione_contabile_parser``), riusate qui invece di essere reinventate. Il vecchio
importatore gia' distingue un bilancio di verifica dove la differenza attivo-passivo e'
stampata o no, e dove una riga dice "risultato" ma e' in realta' quella dell'anno prima
mentre il corrente e' la differenza (ruling del proprietario, Task 14, 2026-09-26).

``_is_prior_result_caption`` e' l'unico helper esportato a livello di modulo dal vecchio
parser (situazione_contabile_parser.py:3491) e viene importato cosi' com'e', senza
adattamento. Gli altri due test (riga di risultato CORRENTE/di controllo, segno dalla
didascalia) sono invece chiusi dentro funzioni private del vecchio parser
(``_be_collect_side_facts.is_control`` ~L3120-3122, ``_strip_result`` in
``extract_contrapposte_best_effort`` ~L4896-4901, ``_hier_prior_result`` ~L3509-3533): non
sono importabili, quindi le regole sono riscritte qui come adattatori minimi, con la stessa
logica a sottostringhe (mai una riscrittura semantica)."""
from __future__ import annotations

from decimal import Decimal

from importers.situazione_contabile_parser import _is_prior_result_caption

_C = Decimal("0.01")


def prior_caption(desc: str) -> bool:
    """Vero per una didascalia di risultato di ESERCIZI PRECEDENTI ("Utile esercizio
    precedente", "Perdite portate a nuovo"), mai per il risultato corrente. Wrapper diretto
    di ``situazione_contabile_parser._is_prior_result_caption``, che si aspetta la stringa
    gia' maiuscola."""
    return _is_prior_result_caption((desc or "").upper())


def control_caption(desc: str) -> bool:
    """Riga di pareggio/controllo o di risultato CORRENTE, mai un conto vero. Stessa regola
    del vecchio parser: l'``is_control`` di ``_be_collect_side_facts`` (~L3120: 'TOTALE',
    'PAREGGIO', o 'ESERCIZ' insieme a UTILE/PERDITA/RISULTATO) e lo ``_strip_result`` di
    ``extract_contrapposte_best_effort`` (~L4896: la stessa coppia ESERCIZ+UTILE/PERDITA/
    RISULTATO, li' per togliere il risultato corrente dalle due colonne prima di
    riclassificarle). Nessuna delle due e' una funzione esportata: quella pipeline lavora su
    colonne fisiche gia' separate (words di PyMuPDF), non sulle Riga di questo pacchetto, e
    tenerla come adattatore qui evita di duplicarne l'albero delle chiamate. Estesa a
    'DIFFERENZA'/'SBILANCIO', didascalie di pareggio comuni nei bilanci di verifica che il
    vecchio test non doveva coprire (la sua pipeline non arriva mai a vederle: il gutter
    fisico o l'euristica dei mastri le scartano prima).

    Va chiamata SOLO dopo aver escluso ``prior_caption``: una "PERDITA PORTATA A NUOVO"
    contiene sia RISULTATO/PERDITA sia ESERCIZ(I), ma e' un saldo pregresso, non corrente."""
    d = (desc or "").upper()
    if 'TOTALE' in d or 'PAREGGIO' in d or 'DIFFERENZA' in d or 'SBILANCIO' in d:
        return True
    return 'ESERCIZ' in d and any(k in d for k in ('UTILE', 'PERDIT', 'RISULTAT'))


def sign_by_caption(desc: str, amount: Decimal) -> Decimal:
    """Segno dato dalla didascalia, come ``situazione_contabile_parser._hier_prior_result``:
    valore assoluto, negativo se la didascalia contiene 'PERDIT' - mai il segno di colonna,
    che su queste righe non e' affidabile (un pregresso puo' essere stampato lordo, senza
    parentesi ne' meno, sul lato Dare o Avere a seconda del gestionale)."""
    v = abs(amount)
    return -v if 'PERDIT' in (desc or "").upper() else v
