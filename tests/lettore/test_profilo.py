import fitz

from importers.lettore.geometria import parole_pagina, righe_fisiche
from importers.lettore.lati import confine_dei_lati
from importers.lettore.colonne import colonne_documento
from importers.lettore.profilo import FormaCodice, Profilo, profilo_documento
from tests.lettore.pdf_sintetico import scrivi_pdf

_VALORI = ("1.234,56", "500,00", "98.765,43", "12,30", "4.500,00", "777,77", "80,00", "3,10")


def _righe(tmp_path, pagine, nome="p.pdf"):
    p = tmp_path / nome
    scrivi_pdf(p, pagine)
    with fitz.open(str(p)) as doc:
        righe = []
        for n, pagina in enumerate(doc, start=1):
            righe += righe_fisiche(parole_pagina(pagina), n)
    return righe


def _profilo(tmp_path, voci) -> Profilo:
    return profilo_documento(_righe(tmp_path, [voci]))


def _tabella(etichette, colonne=(480, 560), y0=140, passo=14, valori=None):
    """Una riga per etichetta, un importo per colonna."""
    voci = []
    for k, etichetta in enumerate(etichette):
        y = y0 + k * passo
        voci.append((50, y, etichetta))
        for j, x in enumerate(colonne):
            voci.append((x, y, (valori or _VALORI)[(k + j) % len(valori or _VALORI)]))
    return voci


def test_negativi_tra_parentesi(tmp_path):
    voci = _tabella([f"Voce {k}" for k in range(6)])
    voci += [(50, 240, "Svalutazioni"), (480, 240, "(1.234,56)"), (560, 240, "(12,00)")]
    prof = _profilo(tmp_path, voci)
    assert "parentesi" in prof.negativi
    assert "meno" not in prof.negativi and "meno-finale" not in prof.negativi


def test_negativi_col_meno_finale(tmp_path):
    voci = _tabella([f"Voce {k}" for k in range(6)])
    voci += [(50, 240, "Perdite"), (480, 240, "1.234,56-"), (560, 240, "45,00-")]
    prof = _profilo(tmp_path, voci)
    assert "meno-finale" in prof.negativi
    assert "parentesi" not in prof.negativi


def test_un_negativo_solo_non_fa_la_forma(tmp_path):
    voci = _tabella([f"Voce {k}" for k in range(6)])
    voci += [(50, 240, "Perdite"), (480, 240, "-1.234,56"), (560, 240, "45,00")]
    assert _profilo(tmp_path, voci).negativi == frozenset()


def test_negativi_in_differenza_non_contano(tmp_path):
    correnti = ("1.000,00", "2.000,00", "500,00", "750,00", "300,00", "80,00")
    precedenti = ("1.500,00", "2.600,00", "400,00", "900,00", "350,00", "100,00")
    differenze = ("-500,00", "-600,00", "100,00", "-150,00", "-50,00", "-20,00")
    voci = [(400 - fitz.get_text_length("2025", fontsize=9.0), 120, "2025"),
            (480 - fitz.get_text_length("2024", fontsize=9.0), 120, "2024"),
            (560 - fitz.get_text_length("DIFFERENZA", fontsize=9.0), 120, "DIFFERENZA")]
    for k, (a, b, d) in enumerate(zip(correnti, precedenti, differenze)):
        y = 140 + k * 14
        voci += [(50, y, f"Voce {k}"), (400, y, a), (480, y, b), (560, y, d)]
    righe = _righe(tmp_path, [voci])
    prof = profilo_documento(righe)
    assert [c.ruolo for c in prof.colonne] == ["esercizio", "esercizio", "differenza"]
    assert prof.negativi == frozenset()


def test_tipo_verifica_da_dare_avere_saldo(tmp_path):
    voci = [(400, 120, "DARE"), (480, 120, "AVERE"), (550, 120, "SALDO")]
    dare = ("1.000,00", "2.000,00", "500,00", "750,00", "300,00", "80,00")
    avere = ("400,00", "1.500,00", "100,00", "700,00", "100,00", "30,00")
    saldo = ("600,00", "500,00", "400,00", "50,00", "200,00", "50,00")
    for k, (d, a, s) in enumerate(zip(dare, avere, saldo)):
        y = 140 + k * 14
        voci += [(50, y, f"Conto {k}"), (430, y, d), (510, y, a), (580, y, s)]
    prof = _profilo(tmp_path, voci)
    assert [c.ruolo for c in prof.colonne] == ["dare", "avere", "saldo"]
    assert prof.tipo == "verifica"
    assert prof.confine is None
    assert "colonne-dare-avere" in prof.negativi


_SCHEMA = ["A) Crediti verso soci", "B) Immobilizzazioni", "I - Immobilizzazioni immateriali",
           "II - Immobilizzazioni materiali", "Totale immobilizzazioni", "C) Attivo circolante",
           "I - Rimanenze", "II - Crediti"]


def test_tipo_schema_senza_codici(tmp_path):
    prof = _profilo(tmp_path, _tabella(_SCHEMA))
    assert prof.tipo == "schema"
    assert prof.confine is None
    assert prof.codici == []
    assert [c.lato for c in prof.colonne] == ["U", "U"]


def test_tipo_schema_dettaglio(tmp_path):
    etichette = ["B) Immobilizzazioni", "II - Immobilizzazioni materiali", "102355 151 Fabbricati",
                 "102355 152 Impianti", "102355 153 Macchinari", "Totale immobilizzazioni",
                 "C) Attivo circolante", "II - Crediti", "105010 001 Clienti Italia", "105010 002 Clienti estero"]
    prof = _profilo(tmp_path, _tabella(etichette))
    assert prof.tipo == "schema-dettaglio"
    assert prof.confine is None
    assert prof.codici[0].forma == "999999 999"
    assert prof.codici[0].con_importi == 5


def _contrapposte():
    sinistra = ("1.234,56", "500,00", "98.765,43", "12,30", "4.500,00", "777,77", "80,00", "3,10")
    destra = ("1.000,00", "620,50", "90.000,00", "15,00", "4.100,10", "700,00", "55,55", "9,90")
    voci = []
    for k, (a, b) in enumerate(zip(sinistra, destra)):
        y = 140 + k * 14
        voci += [(40, y, f"0{k + 1}.01"), (80, y, f"Cliente {k + 1}"), (280, y, a),
                 (310, y, f"2{k + 1}.01"), (350, y, f"Fornitore {k + 1}"), (560, y, b)]
    return voci


def test_tipo_contrapposte(tmp_path):
    prof = _profilo(tmp_path, _contrapposte())
    assert prof.tipo == "contrapposte"
    assert prof.confine is not None and 280 < prof.confine < 310
    assert [c.lato for c in prof.colonne] == ["L", "R"]
    # stessa sagoma sui due lati, ciascuno col proprio allineamento
    assert sorted((f.forma, round(f.x0)) for f in prof.codici) == [("99.99", 40), ("99.99", 310)]


def test_lati_asimmetrici_sono_una_tabella(tmp_path):
    # Una tabella sola: la descrizione e il corrente a sinistra; a destra una sigla corta, poi precedente,
    # differenza e percentuale. Il rilevatore geometrico vede un varco e due lati descritti; il profilo no,
    # perche' a destra ci sono colonne che a sinistra mancano.
    correnti = ("1.000,00", "2.000,00", "500,00", "750,00", "300,00", "80,00")
    precedenti = ("1.500,00", "2.600,00", "400,00", "900,00", "350,00", "100,00")
    differenze = ("500,00", "600,00", "100,00", "150,00", "50,00", "20,00")
    percentuali = ("33,333", "23,077", "25,000", "16,667", "14,286", "20,000")
    voci = []
    for k, (a, b, d, p) in enumerate(zip(correnti, precedenti, differenze, percentuali)):
        y = 140 + k * 14
        voci += [(40, y, f"Ricavo {k}"), (280, y, a), (310, y, f"rif {k}"), (420, y, b), (490, y, d),
                 (560, y, p)]
    righe = _righe(tmp_path, [voci])
    assert confine_dei_lati(righe, colonne_documento(righe)) is not None
    prof = profilo_documento(righe)
    assert prof.confine is None
    assert prof.tipo != "contrapposte"
    assert {c.lato for c in prof.colonne} == {"U"}


def test_decimali_per_colonna(tmp_path):
    interi = ("10.000", "0", "-1", "25.000", "3.000", "7.500")
    voci = _tabella([f"Voce {k}" for k in range(6)], colonne=(480,), valori=interi)
    voci += [(560, 140 + k * 14, v) for k, v in enumerate(_VALORI[:6])]
    prof = _profilo(tmp_path, voci)
    assert prof.decimali == {0: False, 1: True}


def test_forme_di_codice(tmp_path):
    etichette = ["7072 RICAVI DELLE VENDITE", "707245 000 Ricavi Italia", "707250 000 Ricavi CEE",
                 "707275 000 Ricavi extra CEE", "Totale ricavi", "Altri ricavi"]
    voci = []
    for k, etichetta in enumerate(etichette):
        y = 140 + k * 14
        voci.append((50, y, etichetta))
        if k:
            voci += [(480, y, _VALORI[k]), (560, y, _VALORI[k + 1])]
    prof = _profilo(tmp_path, voci)
    forme = {f.forma: f for f in prof.codici}
    assert set(forme) == {"999999 999", "9999"}
    assert forme["999999 999"].con_importi == 3 and forme["999999 999"].senza_importi == 0
    assert forme["9999"].con_importi == 0 and forme["9999"].senza_importi == 1
    assert prof.codici[0].forma == "999999 999"
    assert isinstance(prof.codici[0], FormaCodice)
    assert abs(forme["999999 999"].x0 - 50) < 1
    assert forme["999999 999"].x_etichetta > forme["999999 999"].x0


def test_codice_spaziato_e_una_forma(tmp_path):
    etichette = ["4 / 5 / 1 Terreni", "4 / 5 / 2 Fabbricati", "4 / 5 / 3 Impianti", "Totale", "Altro"]
    prof = _profilo(tmp_path, _tabella(etichette))
    assert [f.forma for f in prof.codici] == ["9 / 9 / 9"]
    assert prof.codici[0].con_importi == 3


def test_bis_non_e_un_codice(tmp_path):
    etichette = ["5 bis) Crediti tributari", "5 ter) Imposte anticipate", "5 quater) Verso altri",
                 "1.1 roe", "1.2 roi", "1.3 ros"]
    prof = _profilo(tmp_path, _tabella(etichette))
    assert prof.codici == []


def test_tipo_ignoto_dichiarato(tmp_path):
    voci = [(50, 140, "Relazione del revisore"), (50, 160, "Il sottoscritto dichiara"),
            (50, 180, "Data 15 marzo")]
    prof = _profilo(tmp_path, voci)
    assert prof.tipo == "ignoto"
    assert prof.colonne == []
    assert any("tipo" in a for a in prof.avvisi)


def test_sezioni_e_margini_per_pagina(tmp_path):
    pagina1 = [(50, 30, "ALFA SRL - Bilancio al 31/12/2025"), (50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA)
    pagina2 = [(50, 30, "ALFA SRL - Bilancio al 31/12/2025"), (50, 120, "CONTO ECONOMICO")] + \
        _tabella(["A) Valore della produzione", "1) Ricavi", "B) Costi della produzione", "6) Materie",
                  "7) Servizi", "Totale costi della produzione"])
    prof = profilo_documento(_righe(tmp_path, [pagina1, pagina2]))
    assert prof.sezioni == {1: "SP", 2: "CE"}
    assert any("alfa srl" in m for m in prof.margini)


def _due_lati_di_legge(testata):
    sinistra = ["A) Crediti verso soci", "B) Immobilizzazioni", "I - Immateriali", "II - Materiali",
                "III - Finanziarie", "C) Attivo circolante", "I - Rimanenze", "II - Crediti"]
    destra = ["A) Patrimonio netto", "I - Capitale", "II - Riserve", "B) Fondi rischi", "C) TFR", "D) Debiti",
              "E) Ratei", "IX - Utile"]
    voci = list(testata)
    for k, (a, b) in enumerate(zip(sinistra, destra)):
        y = 140 + k * 14
        voci += [(40, y, a), (280, y, _VALORI[k]), (310, y, b), (560, y, _VALORI[-1 - k])]
    return voci


def test_situazione_riclassificata_a_sezioni_contrapposte(tmp_path):
    # Voci di legge su entrambi i lati, ma l'intestazione dei lati sulla stessa riga: sezioni contrapposte
    # (budget_1429, 1430).
    prof = _profilo(tmp_path, _due_lati_di_legge([(40, 120, "ATTIVITA'"), (310, 120, "PASSIVITA'")]))
    assert prof.tipo == "contrapposte"
    assert prof.confine is not None and 280 < prof.confine < 310


def test_due_prospetti_di_legge_affiancati_senza_intestazione_non_sono_contrapposte(tmp_path):
    # Lo stato patrimoniale con il conto economico accanto (budget_1426): due tabelle di legge, nessuna
    # intestazione dei lati. Le parole dicono schema, e la geometria da sola non basta.
    righe = _righe(tmp_path, [_due_lati_di_legge([])])
    assert confine_dei_lati(righe, colonne_documento(righe)) is not None
    prof = profilo_documento(righe)
    assert prof.tipo == "schema"
    assert prof.confine is None
