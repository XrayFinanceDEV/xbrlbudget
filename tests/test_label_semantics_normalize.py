"""Forma canonica unica delle etichette di bilancio.

Oggi nel codice convivono SEI normalizzazioni incompatibili (iv_cee_hierarchy,
standard_ivcee_parser, _normalize_for_search, _declared_control_totals inline,
bilancio_classifier.has, situazione_contabile_parser con solo .upper()). Da cui
difetti reali: bilancio_classifier cerca "passivita"/"disponibilita liquide" con
una funzione che NON deaccenta, quindi su testo accentato non matcha mai.
"""
from importers.label_semantics import normalize_label as N, parse_label


def test_toglie_numerazione_di_voce_e_separatori():
    assert N("I - Immobilizzazioni immateriali") == "immobilizzazioni immateriali"
    assert N("B.I) Immob. immateriali") == "immobilizzazioni immateriali"
    assert N("C.II.5 quater) Verso altri") == "verso altri"
    # `fondi` e `f.di` e `f.do` collassano tutti su `fondo`: e' lemmatizzazione,
    # non invenzione, ed e' cio' che rende uguali "F.di ammor.to" e "F.do amm.to".
    assert N("B.II.1.a.1) (Fondi di ammortamento)") == "fondo di ammortamento"
    assert N("A.VIII Utili (perdite) portati a nuovo") == "utili perdite portati a nuovo"


def test_normalizzazione_non_inventa_parole():
    # 'I. immateriali' resta 'immateriali': l'espansione e' compito del DIZIONARIO,
    # non della normalizzazione (che non deve mai aggiungere significato).
    assert N("I. immateriali") == "immateriali"


def test_non_mangia_parole_che_iniziano_come_un_numerale():
    # 'IVA', 'Immobili', 'Cassa' NON sono numerazioni di voce
    assert N("IVA su acquisti") == "iva su acquisti"
    assert N("Immobili civili") == "immobili civili"
    assert N("Vari") == "vari"
    assert N("Debiti v/istituti previdenziali") == "debiti verso istituti previdenziali"


def test_espande_abbreviazioni_comuni():
    assert N("Crediti v/clienti") == "crediti verso clienti"
    assert N("F.do amm.to fabbricati") == "fondo ammortamento fabbricati"
    assert N("F.di ammor.to automezzi") == "fondo ammortamento automezzi"
    assert N("Fdo amm impianti") == "fondo ammortamento impianti"
    assert N("Erario c/IVA") == "erario conto iva"
    assert N("Sval. crediti") == "svalutazione crediti"


def test_toglie_accenti_e_collassa_spazi():
    assert N("Totale   attività ") == "totale attivita"
    assert N("Disponibilità liquide") == "disponibilita liquide"
    assert N("TOTALE STATO PATRIMONIALE - PASSIVO") == "totale stato patrimoniale passivo"


def test_de_spacing_lettera_per_lettera():
    # grafia reale di budget_281 e di 6 documenti del corpus
    assert N("A T T I V I T A'") == "attivita"
    assert N("TOTALE A T T I V I T A") == "totale attivita"
    assert N("P A S S I V I T A`") == "passivita"


def test_non_confonde_voci_diverse():
    assert N("immateriali") != N("materiali")
    assert N("Debiti verso fornitori") != N("Crediti verso clienti")


def test_e_idempotente():
    for s in ["I - Immobilizzazioni immateriali", "F.do amm.to fabbricati",
              "TOTALE A T T I V I T A", "Erario c/IVA", "C.II.5 quater) Verso altri"]:
        assert N(N(s)) == N(s), s


def test_parse_label_estrae_il_path_invece_di_buttarlo():
    """Il path civilistico non e' rumore: serve a disambiguare e a validare la
    gerarchia. La normalizzazione lo toglie dalla stringa, parse_label lo conserva."""
    p = parse_label("C.II.5 quater) Verso altri")
    assert p.canonical == "verso altri"
    assert p.path_hint == "C.II.5-quater"

    p2 = parse_label("B.II.1.a.1) (Fondi di ammortamento)")
    assert p2.canonical == "fondo di ammortamento"
    assert p2.path_hint == "B.II.1.a.1"

    p3 = parse_label("Cassa")
    assert p3.canonical == "cassa" and p3.path_hint is None


def test_parse_label_riconosce_le_righe_di_totale():
    assert parse_label("Totale immobilizzazioni").is_total is True
    assert parse_label("T O T A L E   P A S S I V O").is_total is True
    assert parse_label("Tot. crediti").is_total is True
    assert parse_label("Crediti verso clienti").is_total is False
