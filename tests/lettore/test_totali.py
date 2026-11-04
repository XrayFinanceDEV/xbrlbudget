"""Task 6: righe di totale e parentela, colonna per colonna. Decide la somma stampata, mai il codice."""
from importers.lettore import Documento, leggi_pdf
from tests.lettore.pdf_sintetico import scrivi_pdf

_X_ETICHETTA = 50
_COLONNE = (400, 480)


def _leggi(tmp_path, voci, nome="t.pdf") -> Documento:
    p = tmp_path / nome
    scrivi_pdf(p, [voci])
    return leggi_pdf(str(p))


def _righe(y0, righe, passo=14, colonne=_COLONNE):
    """`righe`: (etichetta, importo per colonna...) oppure (x, etichetta, importi...) per una riga rientrata."""
    voci = []
    for k, riga in enumerate(righe):
        y = y0 + k * passo
        x = _X_ETICHETTA
        if isinstance(riga[0], (int, float)):
            x, riga = riga[0], riga[1:]
        etichetta, importi = riga[0], riga[1:]
        if etichetta:
            voci.append((x, y, etichetta))
        for colonna, importo in zip(colonne, importi):
            if importo:
                voci.append((colonna, y, importo))
    return voci


def _riga(doc, etichetta):
    trovate = [r for r in doc.righe if r.etichetta == etichetta]
    assert len(trovate) == 1, [r.etichetta for r in doc.righe]
    return trovate[0]


def test_totale_e_figli_su_una_colonna(tmp_path):
    doc = _leggi(tmp_path, _righe(140, [("Conto uno", "100,00"), ("Conto due", "250,00"), ("Conto tre", "470,00"),
                                        ("Totale", "820,00")]))
    totale = _riga(doc, "Totale")
    assert totale.totale
    assert totale.figli[0] == tuple(_riga(doc, e).id for e in ("Conto uno", "Conto due", "Conto tre"))
    assert not any(_riga(doc, e).totale for e in ("Conto uno", "Conto due", "Conto tre"))


def test_totale_che_precede_i_figli(tmp_path):
    # schema con dettaglio: la voce stampa l'importo, poi i conti che la compongono
    doc = _leggi(tmp_path, _righe(140, [("Crediti verso clienti", "820,00"), ("Clienti Italia", "100,00"),
                                        ("Clienti estero", "250,00"), ("Ricevute bancarie", "470,00")]))
    voce = _riga(doc, "Crediti verso clienti")
    assert voce.totale
    assert set(voce.figli[0]) == {_riga(doc, e).id for e in ("Clienti Italia", "Clienti estero", "Ricevute bancarie")}
    assert _riga(doc, "Clienti estero").padre == voce.id


def test_colonna_precedente_che_non_torna(tmp_path):
    # budget_1445: il TFR torna sulla corrente (161.654,36 + 97.660,80 + 128.192,34) e non sulla precedente
    # (401.361,79 stampato, 333.227,76 dai conti): la corrente resta, la precedente si dichiara
    doc = _leggi(tmp_path, _righe(140, [
        ("C) TRATTAMENTO DI FINE RAPPORTO", "387.507,50", "401.361,79"),
        ("Fondo TFR impiegati", "161.654,36", "150.000,00"),
        ("Fondo TFR operai", "97.660,80", "90.000,00"),
        ("Fondo TFR dirigenti", "128.192,34", "93.227,76")]))
    tfr = _riga(doc, "C) TRATTAMENTO DI FINE RAPPORTO")
    assert tfr.totale
    assert len(tfr.figli[0]) == 3
    assert not tfr.figli.get(1)
    avvisi = [a for a in doc.avvisi if "68.134,03" in a]
    assert len(avvisi) == 1
    assert "TRATTAMENTO DI FINE RAPPORTO" in avvisi[0]


def test_mastro_e_foglie_non_si_sommano_due_volte(tmp_path):
    doc = _leggi(tmp_path, _righe(140, [("FORNITORI", "100,00"), ("Fornitore Alfa", "60,00"),
                                        ("Fornitore Beta", "40,00"), ("Totale", "100,00")]))
    mastro, totale = _riga(doc, "FORNITORI"), _riga(doc, "Totale")
    assert mastro.figli[0] == (_riga(doc, "Fornitore Alfa").id, _riga(doc, "Fornitore Beta").id)
    assert totale.figli[0] == (mastro.id,)
    assert _riga(doc, "Fornitore Alfa").padre == mastro.id
    assert mastro.padre == totale.id


def test_prefisso_del_codice_non_decide(tmp_path):
    # AGO: mastri a 8 cifre, conti a 9, nessuno prefisso del proprio mastro; «100000021» comincia perfino col codice
    # dell'altro mastro (10000002), ma la somma lo mette sotto il primo
    righe = [("10000001", "IMMOBILIZZAZIONI", "900,00"), ("100000102", "Terreni", "200,00"),
             ("100000021", "Fabbricati", "700,00"), ("10000002", "CREDITI", "430,00"),
             ("100000201", "Clienti", "180,00"), ("100000202", "Erario", "250,00")]
    voci = []
    for k, (codice, etichetta, importo) in enumerate(righe):
        y = 140 + k * 14
        voci += [(40, y, codice), (110, y, etichetta), (480, y, importo)]
    doc = _leggi(tmp_path, voci)
    immob, crediti = _riga(doc, "IMMOBILIZZAZIONI"), _riga(doc, "CREDITI")
    assert immob.codice == "10000001" and _riga(doc, "Fabbricati").codice == "100000021"
    assert _riga(doc, "Fabbricati").padre == immob.id and _riga(doc, "Fabbricati").padre_verificato
    assert _riga(doc, "Terreni").padre == immob.id
    assert {_riga(doc, e).padre for e in ("Clienti", "Erario")} == {crediti.id}


def test_stampa_all_unita_tollera_un_euro(tmp_path):
    righe = [("Voce uno", "1.200"), ("Voce due", "2.300"), ("Voce tre", "3.700"), ("Totale", "7.201"),
             ("Altra uno", "4.100"), ("Altra due", "5.200"), ("Totale altre", "9.300")]
    doc = _leggi(tmp_path, _righe(140, righe))
    assert doc.profilo.decimali.get(0) is False
    assert _riga(doc, "Totale").totale
    assert len(_riga(doc, "Totale").figli[0]) == 3


def test_al_centesimo_un_euro_non_basta(tmp_path):
    righe = [("Voce uno", "1.200,00"), ("Voce due", "2.300,00"), ("Voce tre", "3.700,00"), ("Totale", "7.201,00"),
             ("Altra uno", "4.100,00"), ("Altra due", "5.200,00"), ("Totale altre", "9.300,00")]
    doc = _leggi(tmp_path, _righe(140, righe))
    assert _riga(doc, "Totale altre").totale
    assert not _riga(doc, "Totale").totale


def test_stessa_descrizione_in_due_mastri(tmp_path):
    doc = _leggi(tmp_path, _righe(140, [("FORNITORI", "400,00"), ("Fornitori Italia", "300,00"), ("Altri", "100,00"),
                                        ("CLIENTI", "250,00"), ("Clienti Italia", "200,00"), ("Altri", "50,00")]))
    altri = [r for r in doc.righe if r.etichetta == "Altri"]
    assert len(altri) == 2
    assert [a.percorso[-1] for a in altri] == ["FORNITORI", "CLIENTI"]
    assert all(a.padre_verificato for a in altri)
    assert [a.padre for a in altri] == [_riga(doc, "FORNITORI").id, _riga(doc, "CLIENTI").id]


def test_mastro_solo_intestazione(tmp_path):
    voci = [(40, 126, "10"), (80, 126, "IMMOBILIZZAZIONI")]
    voci += _righe(140, [("Terreni", "100,00"), ("Fabbricati", "250,00"), ("Impianti", "470,00"),
                         ("Automezzi", "1.010,00")])
    doc = _leggi(tmp_path, voci)
    titolo = next(r for r in doc.righe if "IMMOBILIZZAZIONI" in r.etichetta)
    assert titolo.intestazione
    for e in ("Terreni", "Fabbricati", "Impianti", "Automezzi"):
        conto = _riga(doc, e)
        assert conto.padre == titolo.id
        assert not conto.padre_verificato
        assert "IMMOBILIZZAZIONI" in conto.percorso[-1]
    assert not any(r.totale for r in doc.righe)


def test_percorso_fino_alla_sezione(tmp_path):
    voci = [(50, 112, "STATO PATRIMONIALE")]
    voci += _righe(140, [("DEBITI", "1.000,00"), ("FORNITORI", "700,00"), ("c/anticipi", "300,00"),
                         ("Anticipo Alfa", "100,00"), ("Anticipo Beta", "200,00"), ("Fornitori Italia", "400,00"),
                         ("ALTRI DEBITI", "300,00"), ("Erario", "120,00"), ("Istituti previdenziali", "180,00")])
    doc = _leggi(tmp_path, voci)
    assert _riga(doc, "Anticipo Alfa").percorso == ("SP", "DEBITI", "FORNITORI", "c/anticipi")
    assert _riga(doc, "Anticipo Alfa").padre_verificato
    assert _riga(doc, "c/anticipi").percorso == ("SP", "DEBITI", "FORNITORI")
    assert _riga(doc, "Erario").percorso == ("SP", "DEBITI", "ALTRI DEBITI")


def test_totale_vince_sull_intestazione(tmp_path):
    voci = [(50, 126, "CREDITI")]
    voci += _righe(140, [("Conto Alfa", "100,00"), ("Conto Beta", "50,00"), ("DEBITI DIVERSI", "150,00"),
                         ("Banca", "1.010,00")])
    doc = _leggi(tmp_path, voci)
    debiti = _riga(doc, "DEBITI DIVERSI")
    assert _riga(doc, "CREDITI").intestazione
    for e in ("Conto Alfa", "Conto Beta"):
        assert _riga(doc, e).padre == debiti.id
        assert _riga(doc, e).padre_verificato
        assert _riga(doc, e).percorso[-1] == "DEBITI DIVERSI"
    avvisi = [a for a in doc.avvisi if "CREDITI" in a and "DEBITI DIVERSI" in a]
    assert len(avvisi) == 1
