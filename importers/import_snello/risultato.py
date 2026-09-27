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
ristrette a quelle che il vecchio parser usa davvero per un rigo di PAREGGIO/CONTROLLO: mai il
'TOTALE' nudo (che matcherebbe "Totale rimanenze iniziali"), 'DIFFERENZA' solo insieme ad
ATTIVO/PASSIVO/DARE/AVERE, e 'SBILANCIO' solo quando la riga e' essenzialmente quella sola
parola.

Fix round 2 (review, 2026-09-26): la frase del risultato CORRENTE (ESERCIZ+UTILE/PERDIT/
RISULTAT) e' stata tolta da ``control_caption``. Le parole del proprietario: "a volte c'e'
scritto risultato ma in realta' e' il risultato dell'anno precedente, mentre quello di
quest'anno e' la differenza" - "Utile d'esercizio"/"Risultato d'esercizio" su un percorso "R"/
"SPP.A.IX" e' esattamente il caso ambiguo che le due ipotesi di ``conti.da_foglie`` devono
risolvere confrontando quale chiude meglio il foglio, mai un'esclusione diretta decisa a priori
dalla sola didascalia. Solo un rigo di pareggio/differenza/sbilancio DICHIARATO (mai il
risultato, corrente o precedente che sia) si esclude senza passare dall'ipotesi."""
from __future__ import annotations

import re
from decimal import Decimal

from importers.situazione_contabile_parser import _is_prior_result_caption

_C = Decimal("0.01")
_DIFFERENZA_LATI = ('ATTIV', 'PASSIV', 'DARE', 'AVERE')
_SBILANCIO_RIEMPITIVI = {'SBILANCIO', 'DI', 'DA', 'CONTABILE'}
_CODICE_CONTO = re.compile(r'^[\d./*]+$')


def prior_caption(desc: str) -> bool:
    """Vero per una didascalia di risultato di ESERCIZI PRECEDENTI ("Utile esercizio
    precedente", "Perdite portate a nuovo"), mai per il risultato corrente. Wrapper diretto
    di ``situazione_contabile_parser._is_prior_result_caption``, che si aspetta la stringa
    gia' maiuscola."""
    return _is_prior_result_caption((desc or "").upper())


def control_caption(desc: str) -> bool:
    """Riga di pareggio/controllo DICHIARATA, mai un conto vero e mai il risultato (corrente o
    precedente che sia) - ma questo lo dice il PERCORSO, non la didascalia: va chiamata solo su
    una foglia non classificata come conto vero (percorso "R" o "SPP.A.IX"), mai su un percorso
    gia' risolto su un campo normale (vedi il modulo). Stessa regola del vecchio parser
    (l'``is_control`` di ``_be_collect_side_facts``, ~L3120), ristretta due volte:

    - fix round 1 (2026-09-26): mai il 'TOTALE' nudo (che matcherebbe "Totale rimanenze
      iniziali"), 'DIFFERENZA' solo insieme ad ATTIVO/PASSIVO/DARE/AVERE (mai da sola:
      "Differenza cambi attivi" e' un conto vero), 'SBILANCIO' solo quando la riga e'
      essenzialmente quella sola parola (al piu' con 'DI'/'DA'/'CONTABILE': "Sbilancio
      import/export" non e' una riga di pareggio);
    - fix round 2 (2026-09-26): tolta la frase del risultato CORRENTE (ESERCIZ+UTILE/PERDITA/
      RISULTATO, quella di ``_strip_result`` in ``extract_contrapposte_best_effort``
      ~L4896-4901). Le parole del proprietario: "a volte c'e' scritto risultato ma in realta'
      e' il risultato dell'anno precedente, mentre quello di quest'anno e' la differenza" -
      "Utile d'esercizio"/"Risultato d'esercizio" su un percorso "R"/"SPP.A.IX" e' esattamente
      il caso ambiguo che l'ipotesi di ``conti.da_foglie`` deve risolvere, mai un'esclusione
      decisa a priori dalla sola didascalia.

    Va chiamata SOLO dopo aver escluso ``prior_caption``: una "PERDITA PORTATA A NUOVO"
    contiene sia RISULTATO/PERDITA sia ESERCIZ(I), ma e' un saldo pregresso, non corrente."""
    d = (desc or "").upper()
    if 'PAREGGIO' in d:
        return True
    if 'DIFFERENZA' in d and any(k in d for k in _DIFFERENZA_LATI):
        return True
    if 'SBILANCIO' in d:
        parole = re.findall(r'[A-Z]+', d)
        if parole and all(p in _SBILANCIO_RIEMPITIVI for p in parole):
            return True
    return False


def has_account_code(desc: str) -> bool:
    """Vero se la didascalia comincia con un codice di conto (cifre, punti, barre, asterischi -
    stesso riconoscimento di ``situazione_contabile_parser._hier_prior_result``:
    ``re.match(r'^[\\d./*]+$', toks[0])``, li' per scartare una riga gia' dentro un mastro).
    Aggiunta round 2 (banco FORMETAL-TEST, 2026-09-26): un risultato con un codice conto davanti
    ('28/45/090 RISULTATO DI ESERCIZIO') e' un vero conto di patrimonio netto - durante l'anno il
    risultato CORRENTE non e' mai registrato su un conto, solo il pregresso puo' esserlo - quindi
    e' SEMPRE l'anno precedente, deterministico, mai un candidato per l'ipotesi ambigua. Una riga
    senza codice ('UTILE DI ESERCIZIO') e' la riga di quadratura: resta candidata."""
    toks = (desc or "").split()
    return bool(toks) and bool(_CODICE_CONTO.match(toks[0]))


def sign_by_caption(desc: str, amount: Decimal) -> Decimal:
    """Segno dato dalla didascalia, come ``situazione_contabile_parser._hier_prior_result``:
    valore assoluto, negativo se la didascalia contiene 'PERDIT' - mai il segno di colonna,
    che su queste righe non e' affidabile (un pregresso puo' essere stampato lordo, senza
    parentesi ne' meno, sul lato Dare o Avere a seconda del gestionale)."""
    v = abs(amount)
    return -v if 'PERDIT' in (desc or "").upper() else v
