"""Il router non deve rifiutare un bilancio perche' e' scritto con gli accenti.

`compute_signals.has()` normalizzava con `lower()` + variante senza spazi, ma NON
toglieva gli accenti — mentre due dei marker cercati sono scritti senza:
`has("passivita")` e `has("disponibilita liquide")`. Su testo accentato non
matchano MAI. Se nessun altro marker patrimoniale regge, `sp_present` resta False
e il documento finisce in ROUTE_UNSUPPORTED: import RIFIUTATO con il messaggio
"documento solo Conto Economico" su un bilancio che ha lo Stato Patrimoniale.
"""
from importers.bilancio_classifier import compute_signals


def test_marker_patrimoniali_accentati():
    testo = ("Prospetto\n"
             "Totale passività 1.000,00\n"
             "Disponibilità liquide 500,00\n")
    assert compute_signals(testo)["sp_present"] is True


def test_marker_patrimoniali_senza_accento_continuano_a_funzionare():
    testo = "Totale passivita 1.000,00\nDisponibilita liquide 500,00\n"
    assert compute_signals(testo)["sp_present"] is True


def test_marker_accentati_lettera_spaziata():
    testo = "T O T A L E   P A S S I V I T À   1.000,00\n"
    assert compute_signals(testo)["sp_present"] is True


def test_un_documento_solo_economico_resta_tale():
    """Il fix amplia il riconoscimento, non deve trasformare un CE-only in un
    bilancio completo (196/335 devono restare rifiutati onestamente)."""
    testo = ("Conto economico\n"
             "Valore della produzione 100.000,00\n"
             "Costi della produzione 90.000,00\n"
             "Totale ricavi 100.000,00\n")
    s = compute_signals(testo)
    assert s["ce_present"] is True
    assert s["sp_present"] is False
