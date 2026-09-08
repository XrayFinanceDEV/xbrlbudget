"""La guardia contro le ancore di colonna sbagliate (`_page_has_current_column_values`).

Nata da un difetto misurato sul corpus: su `budget_609` — un IV-CEE da tassonomia
XBRL, file del tutto ordinario — la pagina del conto economico non ripete le
intestazioni di data. Le ancore ricadono su quelle di DOCUMENTO, prese da un'altra
pagina, e cadono a sinistra di ENTRAMBE le colonne reali (allineate a destra a
x1=488 e x1=546). Tutti e 70 gli importi finiscono classificati «comparato» e il
meccanismo vede 36 celle correnti vuote su 36 righe.

La guardia di IDENTITA' non puo' vederlo: il campo contiene davvero il numero che la
geometria chiama comparato, perche' quel numero e' il valore corrente. Serve un
controllo a livello di PAGINA — e vuole una contraddizione, non un'assenza: una
pagina intera senza un solo valore corrente non e' un esercizio vuoto.

Discriminatore misurato: 0 valori correnti su 70 (`budget_609`, ancore sbagliate)
contro 18 su 23 (`budget_391`) e 34 su 35 (`budget_397`), dove le celle vuote sono
vere e l'azzeramento va fatto.

Run:  python -m pytest tests/test_ancore_colonna_sbagliate.py -v
Nessuna chiamata di rete e nessun PDF: la geometria delle righe e' sintetica.
"""
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.pdf_extractor_llm import (  # noqa: E402
    _BLANK_CURRENT_CE_ROWS,
    _ColumnAnchors,
    _clear_blank_current_rows,
    _page_has_current_column_values,
)

D = Decimal

# Colonne intestate a parole: allineate al bordo destro (right_edge=True).
ANCHORS = _ColumnAnchors(current=450.0, prior=560.0, others=(), right_edge=True)


def _w(x0, y, text, x1=None):
    """Una parola nel formato PyMuPDF: (x0, y0, x1, y1, testo, ...)."""
    return (x0, y, x1 if x1 is not None else x0 + 40, y + 9, text, 0, 0, 0)


def _row(y, code, label, current=None, prior=None):
    """Una riga di prospetto: codice a sinistra, etichetta, e le celle numeriche."""
    words = [_w(60, y, code)]
    x = 140
    for token in label.split():
        words.append(_w(x, y, token)); x += 20
    # Oltre x=350 una parola e' letta come NUMERO, non come etichetta: senza questa
    # asserzione una label lunga si troncherebbe in silenzio e il test passerebbe
    # (o fallirebbe) per la ragione sbagliata.
    assert x < 350, f"etichetta troppo lunga per il fixture: {label!r}"
    if current is not None:
        words.append(_w(410, y, current, x1=450))
    if prior is not None:
        words.append(_w(520, y, prior, x1=560))
    return words


def _healthy_row(y=60):
    """Una riga con ENTRAMBE le celle piene: e' cio' che dimostra che le ancore della
    pagina sono giuste. Una pagina reale ne ha sempre almeno una."""
    return _row(y, "1)", "Ricavi delle vendite", current="900.000,00", prior="800.000,00")


def _target_row(y=100):
    """`ce09d`: cella corrente vuota, importo solo nel comparato."""
    return _row(y, "d)", "Svalutazioni dei crediti", prior="12.500,00")


# --------------------------------------------------------- la guardia blocca

def test_una_pagina_senza_alcun_valore_corrente_e_unancora_sbagliata():
    """Il caso `budget_609`: nessuna riga della pagina porta un valore corrente.
    Non e' un esercizio vuoto, sono le ancore a essere sbagliate — e li' l'azzeramento
    costava il valore reale -5.103 su `ce16`."""
    words = _target_row() + _row(120, "7)", "Servizi", prior="9.000,00")
    current = {'ce09d_svalutazione_crediti': D("12500")}
    prior = {'ce09d_svalutazione_crediti': D("0")}

    assert _page_has_current_column_values(words, ANCHORS) is False
    assert _clear_blank_current_rows(words, ANCHORS, _BLANK_CURRENT_CE_ROWS, current, prior) == []
    assert current['ce09d_svalutazione_crediti'] == D("12500")


# ------------------------------------------------------ la guardia non blocca

def test_una_pagina_sana_continua_ad_azzerare():
    """Il caso `budget_391`/`budget_397`: la pagina ha valori correnti, quindi la cella
    vuota e' vera. La guardia deve distinguere i due casi, non spegnere il meccanismo."""
    words = _healthy_row() + _target_row()
    current = {'ce09d_svalutazione_crediti': D("12500")}
    prior = {'ce09d_svalutazione_crediti': D("0")}

    assert _page_has_current_column_values(words, ANCHORS) is True
    cleared = _clear_blank_current_rows(words, ANCHORS, _BLANK_CURRENT_CE_ROWS, current, prior)
    assert [f for f, _ in cleared] == ['ce09d_svalutazione_crediti']
    assert current['ce09d_svalutazione_crediti'] == D("0")
    assert prior['ce09d_svalutazione_crediti'] == D("12500")


def test_una_riga_con_entrambe_le_celle_piene_basta_a_sbloccare_la_pagina():
    """La guardia guarda la PAGINA, non la riga: una sola riga sana e' la prova che le
    ancore sono giuste, e le altre righe tornano lavorabili."""
    assert _page_has_current_column_values(_healthy_row(), ANCHORS) is True
    assert _page_has_current_column_values(_target_row(), ANCHORS) is False


# ------------------------------------- le guardie preesistenti restano intatte

def test_una_cella_corrente_piena_non_si_tocca():
    words = _healthy_row() + _row(100, "d)", "Svalutazioni dei crediti",
                                  current="9.000,00", prior="12.500,00")
    current = {'ce09d_svalutazione_crediti': D("9000")}

    assert _clear_blank_current_rows(words, ANCHORS, _BLANK_CURRENT_CE_ROWS, current, {}) == []
    assert current['ce09d_svalutazione_crediti'] == D("9000")


def test_non_si_azzera_un_campo_diverso_da_quello_che_ha_preso_il_comparato():
    """La guardia di identita': l'importo estratto deve essere QUELLO stampato nella
    cella del comparato. Se non coincide, la riga non e' la sua e non si tocca."""
    words = _healthy_row() + _target_row()
    current = {'ce09d_svalutazione_crediti': D("777")}

    assert _clear_blank_current_rows(words, ANCHORS, _BLANK_CURRENT_CE_ROWS, current, {}) == []
    assert current['ce09d_svalutazione_crediti'] == D("777")
