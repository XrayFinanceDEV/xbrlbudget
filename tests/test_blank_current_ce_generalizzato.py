"""#24 — la cella vuota dell'anno corrente si azzera su OGNI voce di legge, non su tre.

Il meccanismo (`_clear_blank_current_rows`) era gia' generale: prende `specs` come
parametro. Corta era la tabella. Qui si verifica che la tabella derivata da
`data/iv_cee_tree.json` copra tutte le foglie legali del CE senza perdere le tre voci
gia' verificate a mano contro un file reale.

Run:  python -m pytest tests/test_blank_current_ce_generalizzato.py -v

Nessuna chiamata di rete e nessun PDF: la geometria delle righe e' sintetica.
"""
import os
import re
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from importers.pdf_extractor_llm import (  # noqa: E402
    _BLANK_CURRENT_CE_ROWS,
    _CE_ROW_SPEC_OVERRIDES,
    _ColumnAnchors,
    _ce_row_specs_from_tree,
    _clear_blank_current_rows,
    _distinctive_label_words,
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


# ----------------------------------------------------- copertura della tabella

def test_copre_tutte_le_foglie_legali_del_ce():
    """Il difetto di #24 era «chiuso su tre voci». Le foglie legali del CE sono 21."""
    derived = _ce_row_specs_from_tree()
    assert len(derived) >= 18, f"derivate solo {len(derived)} voci"
    for field in ("ce01_ricavi_vendite", "ce05_materie_prime", "ce09_ammortamenti",
                  "ce12_oneri_diversi", "ce15_oneri_finanziari"):
        assert field in _BLANK_CURRENT_CE_ROWS, f"{field} non coperto"


def test_le_tre_voci_verificate_a_mano_sopravvivono_intatte():
    """Erano state verificate contro un file reale: la derivazione non le sostituisce.
    Su `ce20` sarebbe piu' STRETTA (il label aggiunge «esercizio»), cioe' una
    regressione silenziosa su una voce che oggi funziona."""
    for field in ("ce03_lavori_interni", "ce09d_svalutazione_crediti", "ce20_imposte"):
        assert _BLANK_CURRENT_CE_ROWS[field] == _CE_ROW_SPEC_OVERRIDES[field]


def test_la_derivazione_riproduce_la_voce_scritta_a_mano():
    """L'oracolo: su ce03 le parole derivate dal label coincidono con quelle che un
    umano aveva scelto guardando il PDF. E' cio' che rende credibile la derivazione
    sulle altre diciotto."""
    assert _distinctive_label_words(
        "Incrementi di immobilizzazioni per lavori interni"
    ) == ('incrementi', 'immobilizzazioni', 'lavori', 'interni')


def test_le_parole_di_servizio_non_entrano_fra_le_obbligatorie():
    assert _distinctive_label_words("Proventi da partecipazioni") == ('proventi', 'partecipazioni')
    assert 'di' not in _distinctive_label_words("Oneri diversi di gestione")


def test_nessuna_voce_resta_senza_parole_obbligatorie():
    """Un insieme vuoto passerebbe `all(...)` su QUALUNQUE riga: il codice da solo
    deciderebbe, e un codice si ripete fra le sezioni."""
    for field, (_code, words) in _BLANK_CURRENT_CE_ROWS.items():
        assert words, f"{field} non ha parole obbligatorie"


def test_due_voci_non_possono_rivendicare_la_stessa_riga():
    """`E.20` (proventi straordinari) e `IMP` (imposte, stampata «20)») condividono il
    codice: a distinguerle devono essere le parole, altrimenti una riga finisce su due
    campi e uno dei due viene azzerato per sbaglio."""
    items = list(_BLANK_CURRENT_CE_ROWS.items())
    probes = [f"{n})" for n in range(1, 23)]
    probes += [f"{L}.{n})" for L in "ABCDE" for n in range(1, 23)]
    probes += ["D)", "D.", "17bis)", "17-bis)", "10.d)", "d)"]
    for i, (fa, (ca, wa)) in enumerate(items):
        for fb, (cb, wb) in items[i + 1:]:
            shared = [p for p in probes if ca.fullmatch(p) and cb.fullmatch(p)]
            if shared:
                assert not (set(wa) <= set(wb) or set(wb) <= set(wa)), (
                    f"{fa} e {fb} rivendicano la stessa riga su {shared[:3]}")


# ----------------------------------------------------- comportamento sulla riga

def test_una_voce_prima_scoperta_ora_si_azzera():
    """Il criterio di #18 era incondizionato. `ce05` non era in lista: la sua cella
    corrente vuota lasciava passare il valore del comparato."""
    words = _row(100, "6)", "Materie prime sussidiarie di consumo e merci", prior="12.500,00")
    current = {'ce05_materie_prime': D("12500")}
    prior = {'ce05_materie_prime': D("0")}

    cleared = _clear_blank_current_rows(words, ANCHORS, _BLANK_CURRENT_CE_ROWS, current, prior)

    assert current['ce05_materie_prime'] == D("0")
    assert prior['ce05_materie_prime'] == D("12500")
    assert [f for f, _ in cleared] == ['ce05_materie_prime']


def test_una_voce_con_accenti_si_riconosce():
    """`data/iv_cee_tree.json` scrive «attivita e passivita», il prospetto stampa
    «attività e passività». Senza normalizzare i due lati `ce17` non matcherebbe mai —
    e un difetto cosi' e' muto: una voce che non matcha e' indistinguibile da una voce
    che non e' in tabella."""
    words = _row(100, "D)", "Rettifiche di valore di attività e passività finanziarie",
                 prior="4.400,00")
    current = {'ce17_rettifiche_attivita_fin': D("4400")}
    prior = {'ce17_rettifiche_attivita_fin': D("0")}

    cleared = _clear_blank_current_rows(words, ANCHORS, _BLANK_CURRENT_CE_ROWS, current, prior)

    assert current['ce17_rettifiche_attivita_fin'] == D("0")
    assert [f for f, _ in cleared] == ['ce17_rettifiche_attivita_fin']


def test_il_bis_non_e_opzionale():
    """`C.17` e' `ce15` (oneri finanziari), `C.17bis` e' `ce16` (utili su cambi). Se il
    suffisso fosse opzionale, `ce16` rivendicherebbe anche la riga di `ce15`."""
    code_16, _ = _BLANK_CURRENT_CE_ROWS['ce16_utili_perdite_cambi']
    assert not code_16.fullmatch("17)")
    assert code_16.fullmatch("17bis)")


def test_altri_e_una_parola_di_contenuto():
    """Distingue B.13 «Altri accantonamenti» da B.12 «Accantonamenti per rischi»."""
    assert 'altri' in _BLANK_CURRENT_CE_ROWS['ce11b_altri_accantonamenti'][1]
    assert 'altri' in _BLANK_CURRENT_CE_ROWS['ce04_altri_ricavi'][1]


def test_una_cella_corrente_piena_non_si_tocca():
    words = _row(100, "6)", "Materie prime sussidiarie di consumo e merci",
                 current="9.000,00", prior="12.500,00")
    current = {'ce05_materie_prime': D("9000")}
    prior = {'ce05_materie_prime': D("0")}

    assert _clear_blank_current_rows(words, ANCHORS, _BLANK_CURRENT_CE_ROWS, current, prior) == []
    assert current['ce05_materie_prime'] == D("9000")


def test_non_si_azzera_un_campo_diverso_da_quello_che_ha_preso_il_comparato():
    """La guardia di identita': l'importo estratto deve essere QUELLO stampato nella
    cella del comparato. Se non coincide, la riga non e' la sua e non si tocca."""
    words = _row(100, "6)", "Materie prime sussidiarie di consumo e merci", prior="12.500,00")
    current = {'ce05_materie_prime': D("777")}

    assert _clear_blank_current_rows(words, ANCHORS, _BLANK_CURRENT_CE_ROWS, current, {}) == []
    assert current['ce05_materie_prime'] == D("777")
