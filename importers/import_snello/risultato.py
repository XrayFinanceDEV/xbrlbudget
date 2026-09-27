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
logica a sottostringhe (mai una riscrittura semantica).

Fix round 1 (review, 2026-09-26): ``control_caption`` e' un test SULLA DIDASCALIA, cieco al
percorso - va invocato solo su una foglia gia' non classificata come conto vero (percorso "R"
o "SPP.A.IX": l'unico punto dove ``conti.py`` lo chiama), mai su un percorso che si e' gia'
risolto su un campo normale. "Differenza cambi attivi" (CE.C.17-bis, un conto vero) e "Totale
rimanenze iniziali" contengono le stesse sottostringhe di un rigo di pareggio, ma hanno un
percorso classificato: la didascalia non li deve mai escludere. Le frasi sono anche state
ristrette a quelle che il vecchio parser usa davvero: mai il 'TOTALE' nudo (che matcherebbe
"Totale rimanenze iniziali"), 'DIFFERENZA' solo insieme ad ATTIVO/PASSIVO/DARE/AVERE, e
'SBILANCIO' solo quando la riga e' essenzialmente quella sola parola."""
from __future__ import annotations

import re
from decimal import Decimal

from importers.situazione_contabile_parser import _is_prior_result_caption

_C = Decimal("0.01")
_DIFFERENZA_LATI = ('ATTIV', 'PASSIV', 'DARE', 'AVERE')
_SBILANCIO_RIEMPITIVI = {'SBILANCIO', 'DI', 'DA', 'CONTABILE'}


def prior_caption(desc: str) -> bool:
    """Vero per una didascalia di risultato di ESERCIZI PRECEDENTI ("Utile esercizio
    precedente", "Perdite portate a nuovo"), mai per il risultato corrente. Wrapper diretto
    di ``situazione_contabile_parser._is_prior_result_caption``, che si aspetta la stringa
    gia' maiuscola."""
    return _is_prior_result_caption((desc or "").upper())


def control_caption(desc: str) -> bool:
    """Riga di pareggio/controllo o di risultato CORRENTE, mai un conto vero - ma questo lo
    dice il PERCORSO, non la didascalia: va chiamata solo su una foglia non classificata come
    conto vero (percorso "R" o "SPP.A.IX"), mai su un percorso gia' risolto su un campo normale
    (vedi il modulo). Stessa regola del vecchio parser, ristretta (fix round 1, 2026-09-26) a
    cio' che testa davvero: l'``is_control`` di ``_be_collect_side_facts`` (~L3120: 'PAREGGIO',
    o 'ESERCIZ' insieme a UTILE/PERDITA/RISULTATO - MAI il 'TOTALE' nudo, che matcherebbe
    anche "Totale rimanenze iniziali") e lo ``_strip_result`` di
    ``extract_contrapposte_best_effort`` (~L4896: la stessa coppia ESERCIZ+UTILE/PERDITA/
    RISULTATO). Nessuna delle due e' una funzione esportata: quella pipeline lavora su
    colonne fisiche gia' separate (words di PyMuPDF), non sulle Riga di questo pacchetto, e
    tenerla come adattatore qui evita di duplicarne l'albero delle chiamate. 'DIFFERENZA' conta
    solo insieme ad ATTIVO/PASSIVO/DARE/AVERE (mai da sola: "Differenza cambi attivi" e' un
    conto vero), e 'SBILANCIO' solo quando la riga e' essenzialmente quella sola parola (al
    piu' con 'DI'/'DA'/'CONTABILE': "Sbilancio import/export" non e' una riga di pareggio).

    Va chiamata SOLO dopo aver escluso ``prior_caption``: una "PERDITA PORTATA A NUOVO"
    contiene sia RISULTATO/PERDITA sia ESERCIZ(I), ma e' un saldo pregresso, non corrente."""
    d = (desc or "").upper()
    if 'PAREGGIO' in d:
        return True
    if 'ESERCIZ' in d and any(k in d for k in ('UTILE', 'PERDIT', 'RISULTAT')):
        return True
    if 'DIFFERENZA' in d and any(k in d for k in _DIFFERENZA_LATI):
        return True
    if 'SBILANCIO' in d:
        parole = re.findall(r'[A-Z]+', d)
        if parole and all(p in _SBILANCIO_RIEMPITIVI for p in parole):
            return True
    return False


def sign_by_caption(desc: str, amount: Decimal) -> Decimal:
    """Segno dato dalla didascalia, come ``situazione_contabile_parser._hier_prior_result``:
    valore assoluto, negativo se la didascalia contiene 'PERDIT' - mai il segno di colonna,
    che su queste righe non e' affidabile (un pregresso puo' essere stampato lordo, senza
    parentesi ne' meno, sul lato Dare o Avere a seconda del gestionale)."""
    v = abs(amount)
    return -v if 'PERDIT' in (desc or "").upper() else v
