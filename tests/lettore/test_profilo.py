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


def test_due_prospetti_di_legge_affiancati_hanno_lati_fisici_non_contrapposti(tmp_path):
    # Lo stato patrimoniale con il conto economico accanto (budget_1426), o una situazione riclassificata
    # (budget_1430): due tabelle affiancate. Il confine e' fisico, le parole dicono schema, e il verdetto
    # «contrapposto» (lato sinistro = attivo/costi) non c'e'; il profilo lo dichiara.
    for testata in ([], [(40, 120, "ATTIVITA'"), (310, 120, "PASSIVITA'")]):
        prof = _profilo(tmp_path, _due_lati_di_legge(testata))
        assert prof.tipo == "schema"
        assert prof.confine is not None and 280 < prof.confine < 310
        assert [c.lato for c in prof.colonne] == ["L", "R"]
        assert prof.contrapposto is False
        assert any("due tabelle affiancate" in a for a in prof.avvisi)


def test_contrapposte_hanno_il_verdetto(tmp_path):
    prof = _profilo(tmp_path, _contrapposte())
    assert prof.contrapposto is True
    assert not any("due tabelle affiancate" in a for a in prof.avvisi)


def test_titolo_centrato_attivo_e_passivo_non_fa_contrapposte(tmp_path):
    # «STATO PATRIMONIALE ATTIVO E PASSIVO» centrato sopra uno schema a sezione unica.
    voci = [(200, 120, "STATO PATRIMONIALE ATTIVO E PASSIVO")] + _tabella(_SCHEMA, colonne=(300, 560))
    prof = _profilo(tmp_path, voci)
    assert prof.tipo == "schema"
    assert prof.confine is None
    assert prof.contrapposto is False


def _movimentazione(y0=200):
    """Una tabella della nota con quattro colonne proprie."""
    voci = [(50, y0 - 20, "Valore di inizio esercizio Incrementi Decrementi Valore di fine esercizio")]
    for k in range(5):
        y = y0 + k * 14
        voci += [(50, y, f"Categoria {k}"), (250, y, _VALORI[k]), (330, y, _VALORI[k + 1]), (410, y, _VALORI[k + 2]),
                 (490, y, _VALORI[k + 3])]
    return voci


def test_tabella_della_nota_non_fa_colonne(tmp_path):
    pagina1 = [(50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA)
    pagina2 = [(50, 120, "NOTA INTEGRATIVA"), (50, 140, "Movimentazione delle immobilizzazioni")] + _movimentazione()
    prof = profilo_documento(_righe(tmp_path, [pagina1, pagina2]))
    assert [round(c.x_destra) for c in prof.colonne] == [480, 560]
    assert prof.parti == {1: "prospetto", 2: "nota"}
    assert len(prof.tabelle_nota) == 1
    tab = prof.tabelle_nota[0]
    assert tab.pagina == 2 and len(tab.colonne) == 4
    assert "Movimentazione" in tab.titolo or "Valore di inizio" in tab.titolo


def test_pagina_di_nota_senza_titolo_continua_la_nota(tmp_path):
    pagina1 = [(50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA)
    pagina2 = [(50, 120, "NOTA INTEGRATIVA")] + _movimentazione()
    # una tabella della nota sulle stesse colonne dei prospetti: la geometria non la distingue, la continuazione si'
    pagina3 = _tabella(["Saldo iniziale", "Incrementi", "Decrementi", "Saldo finale"])
    prof = profilo_documento(_righe(tmp_path, [pagina1, pagina2, pagina3]))
    assert prof.parti == {1: "prospetto", 2: "nota", 3: "nota"}
    assert [round(c.x_destra) for c in prof.colonne] == [480, 560]


def test_titolo_di_prospetto_dopo_la_nota_torna_prospetto(tmp_path):
    pagina1 = [(50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA)
    pagina2 = [(50, 120, "Nota integrativa, parte iniziale")] + _movimentazione()
    pagina3 = [(50, 120, "CONTO ECONOMICO")] + _tabella(["A) Valore della produzione", "1) Ricavi",
                                                         "B) Costi della produzione", "6) Materie", "7) Servizi"])
    prof = profilo_documento(_righe(tmp_path, [pagina1, pagina2, pagina3]))
    assert prof.parti == {1: "prospetto", 2: "nota", 3: "prospetto"}
    assert [round(c.x_destra) for c in prof.colonne] == [480, 560]
    assert [b[2] for b in prof.bande] == ["prospetto", "nota", "prospetto"]


def test_pagina_con_colonne_proprie_dopo_il_prospetto_e_nota(tmp_path):
    # Senza titolo, ma con colonne che non sono quelle dei prospetti (la rideterminazione del reddito fiscale in
    # coda a una situazione contabile, budget_395 p. 6-7).
    pagina1 = [(50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA)
    prof = profilo_documento(_righe(tmp_path, [pagina1, _movimentazione(140)]))
    assert prof.parti == {1: "prospetto", 2: "nota"}
    assert [round(c.x_destra) for c in prof.colonne] == [480, 560]


def test_frontespizio_e_altro(tmp_path):
    copertina = [(200, 300, "ALFA SRL"), (200, 320, "Bilancio al 31/12/2025")]
    pagina2 = [(50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA)
    prof = profilo_documento(_righe(tmp_path, [copertina, pagina2]))
    assert prof.parti == {1: "altro", 2: "prospetto"}


def _pagina_contrapposta(n_sinistra, n_destra, minore=(), y0=140):
    """Una pagina a sezioni contrapposte: `n_sinistra` conti a sinistra (colonna a 280), `n_destra` a destra (560);
    sulle righe di `minore` una seconda colonna a sinistra (200), come i mastri dei costi."""
    voci = []
    for k in range(max(n_sinistra, n_destra)):
        y = y0 + k * 14
        if k < n_sinistra:
            voci += [(40, y, f"0{k % 9 + 1}.0{k // 9 + 1}"), (80, y, f"Costo {k}"), (280, y, _VALORI[k % 8])]
            if k in minore:
                voci.append((200, y, _VALORI[(k + 3) % 8]))
        if k < n_destra:
            voci += [(310, y, f"2{k % 9 + 1}.0{k // 9 + 1}"), (350, y, f"Ricavo {k}"), (560, y, _VALORI[(k + 1) % 8])]
    return voci


def test_colonna_minore_su_parte_del_documento_non_rompe_la_simmetria(tmp_path):
    # La colonna a 200 ha il 45% degli importi della colonna principale di sinistra, ma solo sulla pagina dei costi,
    # dove a destra non c'e' niente da confrontare. Contata per quota degli importi (regola di prima, 40%) faceva
    # due colonne a sinistra contro una a destra.
    pagine = [_pagina_contrapposta(8, 8), _pagina_contrapposta(8, 8), _pagina_contrapposta(40, 0, minore=range(25))]
    righe = _righe(tmp_path, pagine)
    prof = profilo_documento(righe)
    principale = sum(1 for r in righe for p in r.parole if abs(p.x1 - 280) < 3)
    minore = sum(1 for r in righe for p in r.parole if abs(p.x1 - 200) < 3)
    assert 0.4 < minore / principale < 0.5
    assert prof.contrapposto is True and prof.tipo == "contrapposte"
    assert [c.lato for c in prof.colonne] == ["L", "L", "R"]


def test_colonna_minore_su_una_pagina_su_tre_non_rompe_la_simmetria(tmp_path):
    pagine = [_pagina_contrapposta(8, 8), _pagina_contrapposta(8, 8), _pagina_contrapposta(8, 8, minore=range(4))]
    prof = profilo_documento(_righe(tmp_path, pagine))
    assert prof.contrapposto is True


def test_lati_asimmetrici_su_ogni_pagina_sono_una_tabella(tmp_path):
    pagine = [_pagina_contrapposta(8, 8, minore=range(8)) for _ in range(3)]
    prof = profilo_documento(_righe(tmp_path, pagine))
    assert prof.confine is None and prof.contrapposto is False


def test_negativi_col_meno(tmp_path):
    voci = _tabella([f"Voce {k}" for k in range(6)])
    voci += [(50, 240, "Perdite"), (480, 240, "-1.234,56"), (560, 240, "-45,00")]
    prof = _profilo(tmp_path, voci)
    assert prof.negativi == frozenset({"meno"})


def test_negativi_col_marcatore(tmp_path):
    # Il marcatore staccato («1.234,56 D») e quello attaccato («45,00A», ricucito da `righe._ricuci` come in
    # `leggi_pdf`): il profilo del PDF vede l'uno e l'altro.
    from importers.lettore.righe import profilo_pdf
    for forma in ("staccato", "attaccato"):
        voci = []
        for k in range(6):
            y = 140 + k * 14
            voci += [(50, y, f"Conto {k}"), (560, y, _VALORI[k + 1])]
            voci += [(480, y, _VALORI[k]), (486, y, "D")] if forma == "staccato" else [(480, y, _VALORI[k] + "A")]
        p = tmp_path / f"m-{forma}.pdf"
        scrivi_pdf(p, [voci])
        prof = profilo_pdf(str(p))
        assert len(prof.colonne) == 2, forma
        assert "marcatore" in prof.negativi, forma


def test_negativi_in_percentuale_non_contano(tmp_path):
    percentuali = ("-12,345", "-3,500", "10,000", "-1,250", "4,000", "-2,000")
    voci = _tabella([f"Voce {k}" for k in range(6)], colonne=(480,))
    voci += [(560, 140 + k * 14, v) for k, v in enumerate(percentuali)]
    prof = _profilo(tmp_path, voci)
    assert [c.ruolo for c in prof.colonne] == ["esercizio", "percentuale"]
    assert prof.negativi == frozenset()


_SP_MICRO = ["B) Immobilizzazioni", "I - Immobilizzazioni immateriali", "II - Immobilizzazioni materiali",
             "C) Attivo circolante", "Totale attivo", "A) Patrimonio netto", "Totale patrimonio netto", "Totale passivo"]
_CE_MICRO = ["A) Valore della produzione", "1) ricavi delle vendite", "Totale valore della produzione",
             "B) Costi della produzione", "7) per servizi", "Totale costi della produzione",
             "Differenza tra valore e costi della produzione (A - B)", "21) Utile (perdita) dell'esercizio"]


def test_bilancio_micro_xbrl(tmp_path):
    # I titoli dei micro XBRL: «Informazioni generali sull'impresa» in testa, «Stato Patrimoniale Micro»,
    # «Informazioni in calce allo stato patrimoniale (micro)» fra SP e CE, «Conto economico micro».
    pagina1 = ([(50, 80, "Informazioni generali sull'impresa"), (50, 100, "Denominazione: ALFA SRL"),
                (50, 300, "Stato Patrimoniale Micro")] + _tabella(_SP_MICRO, y0=320))
    pagina2 = ([(50, 80, "Informazioni in calce allo stato patrimoniale (micro)"),
                (50, 100, "La societa' non ha impegni non risultanti dallo stato patrimoniale."),
                (50, 300, "Conto economico micro")] + _tabella(_CE_MICRO, y0=320))
    prof = profilo_documento(_righe(tmp_path, [pagina1, pagina2]))
    parti = [(p, parte) for p, _, parte in prof.bande]
    assert parti == [(1, "nota"), (1, "prospetto"), (2, "nota"), (2, "prospetto")]
    assert prof.parti == {1: "prospetto", 2: "prospetto"}
    assert [round(c.x_destra) for c in prof.colonne] == [480, 560]


def test_informazioni_generali_con_le_prove_di_un_prospetto_sono_prospetto(tmp_path):
    # Un titolo debole («Informazioni …» senza le parole della nota) non toglie il prospetto che lo segue.
    voci = [(50, 120, "Informazioni generali sull'impresa")] + _tabella(_SP_MICRO)
    prof = profilo_documento(_righe(tmp_path, [voci]))
    assert prof.parti == {1: "prospetto"}
    assert len(prof.colonne) == 2


def test_coda_del_conto_economico_e_rendiconto_sulla_stessa_pagina(tmp_path):
    pagina1 = [(50, 120, "Conto economico")] + _tabella(_CE_MICRO[:6])
    coda = _tabella(["20) Imposte sul reddito dell'esercizio", "21) Utile (perdita) dell'esercizio"], y0=80)
    rendiconto = [(50, 140, "Rendiconto finanziario, metodo indiretto")] + _tabella(
        ["Utile (perdita) dell'esercizio", "Imposte sul reddito", "Interessi passivi", "Ammortamenti",
         "Variazione dei crediti"], y0=160)
    prof = profilo_documento(_righe(tmp_path, [pagina1, coda + rendiconto]))
    # `bande` elenca i punti in cui la parte cambia: la coda resta prospetto, la nota comincia col rendiconto
    assert [(p, parte) for p, _, parte in prof.bande] == [(1, "prospetto"), (2, "nota")]
    assert 94 < prof.bande[1][1] < 140


def test_tabella_della_nota_con_totali_non_di_prospetto_resta_nota(tmp_path):
    pagina1 = [(50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA)
    nota = [(50, 120, "Movimentazione delle immobilizzazioni")] + _tabella(
        ["Costo", "Ammortamenti", "Totale variazioni", "Totale valore di bilancio", "Totale"], colonne=(250, 330))
    prof = profilo_documento(_righe(tmp_path, [pagina1, nota]))
    assert prof.parti == {1: "prospetto", 2: "nota"}
    assert [round(c.x_destra) for c in prof.colonne] == [480, 560]


def test_totale_con_piu_numeri_delle_colonne_non_e_una_prova(tmp_path):
    # La tabella delle variazioni del patrimonio netto ha «Totale patrimonio netto» con un numero per riserva: piu'
    # numeri delle colonne dei prospetti, quindi non prova un prospetto, nemmeno sotto un titolo debole.
    pagina1 = [(50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA)
    tabella = [(50, 120, "Informazioni generali sul patrimonio")]
    for k, etichetta in enumerate(["Capitale", "Riserva legale", "Altre riserve", "Totale patrimonio netto"]):
        y = 140 + k * 14
        tabella += [(50, y, etichetta)] + [(x, y, _VALORI[(k + j) % 8]) for j, x in enumerate((250, 330, 410, 490))]
    prof = profilo_documento(_righe(tmp_path, [pagina1, tabella]))
    assert prof.parti == {1: "prospetto", 2: "nota"}
    assert [round(c.x_destra) for c in prof.colonne] == [480, 560]


def test_fine_di_una_frase_sul_prospetto_non_e_un_titolo(tmp_path):
    # «… dello stato patrimoniale.» a capo in una pagina della nota non riapre il prospetto (budget_201 p16).
    pagina1 = [(50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA)
    nota = [(50, 120, "NOTA INTEGRATIVA"), (50, 140, "stato patrimoniale.")] + _tabella(
        ["Saldo iniziale", "Incrementi", "Decrementi", "Saldo finale"], y0=200)
    prof = profilo_documento(_righe(tmp_path, [pagina1, nota]))
    assert prof.parti == {1: "prospetto", 2: "nota"}


def test_decisioni_per_riga_nel_profilo(tmp_path):
    # Task 5-ter: il lettore di righe consuma margini, sezioni e parti senza rifarle; la chiave e' (pagina, y)
    pagina1 = [(50, 120, "STATO PATRIMONIALE")] + _tabella(_SCHEMA) + [(50, 800, "Pagina 1 di 2")]
    pagina2 = [(50, 120, "NOTA INTEGRATIVA")] + _movimentazione() + [(50, 800, "Pagina 2 di 2")]
    righe = _righe(tmp_path, [pagina1, pagina2])
    prof = profilo_documento(righe)
    piedi = {(r.pagina, r.y) for r in righe if "Pagina" in " ".join(p.testo for p in r.parole)}
    assert piedi and piedi <= prof.scartate
    assert set(prof.parti_righe) == {(r.pagina, r.y) for r in righe}
    assert set(prof.sezioni_righe) == {(r.pagina, r.y) for r in righe} - prof.scartate
    voce = next(r for r in righe if r.pagina == 1 and r.parole[0].testo == "A)")
    assert prof.sezioni_righe[(1, voce.y)] == "SP" and prof.parti_righe[(1, voce.y)] == "prospetto"
    assert {prof.parti_righe[(r.pagina, r.y)] for r in righe if r.pagina == 2} == {"nota"}


def test_colonna_destra_delle_contrapposte_su_poche_pagine_resta_del_prospetto(tmp_path):
    # budget_375: la colonna di destra ha importi solo su 3 pagine su 7; la pagina col solo passivo non e' nota
    def lato(prefisso, x_codice, x_etichetta, x_importo, y0=140, n=8):
        return [v for k in range(n) for v in ((x_codice, y0 + k * 14, f"{prefisso}{k + 1}.01"),
                                              (x_etichetta, y0 + k * 14, f"Conto {prefisso}{k + 1}"),
                                              (x_importo, y0 + k * 14, _VALORI[k % len(_VALORI)]))]
    pagina1 = [(50, 100, "SITUAZIONE PATRIMONIALE")] + lato("1", 40, 80, 280) + lato("2", 310, 350, 560)
    pagina2 = [(50, 100, "SITUAZIONE PATRIMONIALE")] + lato("3", 310, 350, 560)
    economico = [[(50, 100, "CONTO ECONOMICO")] + lato(str(4 + k), 40, 80, 280) for k in range(3)]
    prof = profilo_documento(_righe(tmp_path, [pagina1, pagina2] + economico))
    assert prof.parti[2] == "prospetto"
    assert all(prof.parti_righe[k] == "prospetto" for k in prof.parti_righe if k[0] == 2)


def test_titoli_della_nota_delle_tabelle():
    """R21: «Dettaglio ratei, risconti e competenze» (budget_210 pp. 6-7, una stampa a se'), «Indici di struttura»,
    «Composizione dei ricavi» aprono la nota."""
    from importers.lettore.geometria import Parola, RigaFisica
    from importers.lettore.profilo import _titolo_parte
    for titolo in ("Dettaglio ratei, risconti e competenze (valuta di gestione)", "Indici di struttura",
                   "Composizione dei ricavi", "Movimenti delle immobilizzazioni"):
        assert _titolo_parte(RigaFisica(1, 10.0, [Parola(10, 6, 200, 14, titolo)])) == "nota", titolo
