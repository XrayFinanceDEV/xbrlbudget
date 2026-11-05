"""Task 2 (Fase 2): i blocchi che non chiudono, per voce, colonna e righe. Si legge e si dichiara, non si corregge."""
import copy
from datetime import date
from decimal import Decimal

from importers.lettore import Blocco, Documento, blocchi_aperti, frase_blocco, leggi_pdf
from tests.lettore.pdf_sintetico import scrivi_pdf

_X_ETICHETTA = 50
_COLONNE = (400, 480)


def _leggi(tmp_path, pagine, nome="t.pdf") -> Documento:
    p = tmp_path / nome
    scrivi_pdf(p, pagine)
    return leggi_pdf(str(p))


def _righe(y0, righe, passo=14, colonne=_COLONNE):
    voci = []
    for k, (etichetta, *importi) in enumerate(righe):
        y = y0 + k * passo
        voci.append((_X_ETICHETTA, y, etichetta))
        for colonna, importo in zip(colonne, importi):
            if importo:
                voci.append((colonna, y, importo))
    return voci


_APERTURA = [("Voce a", "40,00"), ("Voce b", "60,00"), ("Totale apertura", "100,00")]


def _doc(tmp_path, righe, apertura=True):
    """Un gruppo che chiude davanti (serve al profilo per riconoscere la colonna, e fa da confine) e le `righe`."""
    doc = _leggi(tmp_path, [_righe(140, (_APERTURA if apertura else []) + righe)])
    doc.profilo.tipo = "schema"     # il PDF sintetico e' «ignoto»: i blocchi da riga di controllo valgono solo su uno schema
    return doc


def test_documento_che_chiude_non_ha_blocchi(tmp_path):
    doc = _doc(tmp_path, [("Conto uno", "100,00", "90,00"), ("Conto due", "250,00", "80,00"),
                          ("Conto tre", "300,00", "70,00"), ("Totale", "650,00", "240,00")], apertura=False)
    assert blocchi_aperti(doc) == []


def test_voce_che_non_chiude_e_un_blocco(tmp_path):
    # 150 + 200 + 250 e non 100 + 200 + 300: la terna del brief fa chiudere «Conto tre» sui primi due, e allora
    # «Conto tre» e' un totale stampato che chiude (il lettore legge cosi'), non un conto
    doc = _doc(tmp_path, [("Conto uno", "150,00"), ("Conto due", "200,00"), ("Conto tre", "250,00"),
                          ("Totale", "610,00")])
    blocchi = blocchi_aperti(doc)
    assert len(blocchi) == 1
    b = blocchi[0]
    assert isinstance(b, Blocco)
    assert (b.voce, b.stampato, b.somma, b.scarto) == ("Totale", Decimal("610.00"), Decimal("600.00"),
                                                       Decimal("10.00"))
    ids = {r.etichetta: r.id for r in doc.righe}
    assert b.righe == (ids["Conto uno"], ids["Totale"])
    assert b.etichette == ("Conto uno", "Conto due", "Conto tre")
    assert b.colonna == 0 and b.pagina == 1
    assert b.cercato is True        # riga di controllo non chiusa: il tratto e' scelto, non noto


def test_colonna_precedente_che_non_torna(tmp_path):
    # budget_1445: il TFR torna sulla corrente e non sulla precedente: un solo blocco, sulla precedente
    doc = _doc(tmp_path, [
        ("C) TRATTAMENTO DI FINE RAPPORTO", "387.507,50", "401.361,79"),
        ("Fondo TFR impiegati", "161.654,36", "150.000,00"),
        ("Fondo TFR operai", "97.660,80", "90.000,00"),
        ("Fondo TFR dirigenti", "128.192,34", "93.227,76")])
    blocchi = blocchi_aperti(doc)
    assert len(blocchi) == 1
    b = blocchi[0]
    assert b.colonna == 1
    assert b.cercato is False       # voce chiusa sulla corrente: i figli sono noti
    assert (b.stampato, b.somma, b.scarto) == (Decimal("401361.79"), Decimal("333227.76"), Decimal("68134.03"))
    assert b.etichette == ("Fondo TFR impiegati", "Fondo TFR operai", "Fondo TFR dirigenti")


def test_colonna_differenza_non_e_un_blocco(tmp_path):
    bordi = (330, 400, 470)
    voci = [(x, 110, "ESERCIZIO") for x in bordi[:2]] + [(470, 110, "DIFFERENZA")]
    voci += [(330, 122, "2025"), (400, 122, "2024")]
    voci += _righe(140, [("Conto uno", "100,00", "90,00", "3,00"), ("Conto due", "250,00", "80,00", "77,10"),
                         ("Conto tre", "300,00", "70,00", "1,50"), ("Totale", "650,00", "240,00", "900,00")],
                   colonne=bordi)
    doc = _leggi(tmp_path, [voci])
    assert [c.ruolo for c in doc.colonne] == ["esercizio", "esercizio", "differenza"]
    assert blocchi_aperti(doc) == []


def test_righe_della_nota_non_fanno_blocchi(tmp_path):
    prospetto = [(50, 100, "STATO PATRIMONIALE")] + _righe(
        140, _APERTURA + [("Conto uno", "150,00"), ("Conto due", "200,00"), ("Totale", "350,00")])
    nota = [(50, 100, "NOTA INTEGRATIVA"), (50, 124, "Patrimonio netto"),
            (268, 140, "Importo"), (304, 140, "Possibilita' di utilizzazione")]
    for k, (e, v) in enumerate([("Capitale", "70.000"), ("Riserva legale", "14.000"), ("Totale", "99.999")]):
        nota += [(45, 156 + k * 16, e), (294.6, 156 + k * 16, v)]
    doc = _leggi(tmp_path, [prospetto, nota])
    assert [r.parte for r in doc.righe if r.etichetta == "Totale"] == ["prospetto", "nota"]
    assert blocchi_aperti(doc) == []


def test_voce_da_intestazione_non_e_un_blocco(tmp_path):
    # figli dichiarati solo dall'intestazione: nessun totale stampato che chiuda, nessun blocco
    doc = _doc(tmp_path, [("B) II - Crediti", ), ("Clienti", "100,00"), ("Erario", "250,00"), ("Altri", "470,00"),
                          ("C) Disponibilita'", "1.000,00")])
    assert [r.totale for r in doc.righe if r.etichetta.startswith("B) II")] == [False]
    assert blocchi_aperti(doc) == []


def test_frase_blocco(tmp_path):
    b = Blocco(voce="B) II - Crediti", codice="", sezione="SP", lato="U", colonna=0, fine=date(2025, 12, 31),
               mesi=12, corrente=True, stampato=Decimal("1234.56"), somma=Decimal("1200.00"),
               scarto=Decimal("34.56"), pagina=3, righe=("p3r12U", "p3r27U"), etichette=(), cercato=True)
    assert frase_blocco(b) == ("B) II - Crediti (2025, p. 3, righe 12-27): stampato 1.234,56, "
                               "i conti sommano 1.200,00, scarto 34,56")


def test_blocchi_non_modificano_il_documento(tmp_path):
    doc = _doc(tmp_path, [("Conto uno", "150,00"), ("Conto due", "200,00"), ("Totale", "360,00")])
    prima = copy.deepcopy(doc)
    assert blocchi_aperti(doc)
    assert doc == prima


def test_ordine_per_scarto(tmp_path):
    doc = _doc(tmp_path, [("Conto uno", "150,00"), ("Conto due", "200,00"), ("Totale parziale", "355,00"),
                          ("Conto tre", "1.000,00"), ("Conto quattro", "2.000,00"),
                          ("Totale", "3.455,00")], apertura=False)
    blocchi = blocchi_aperti(doc)
    assert [b.voce for b in blocchi] == ["Totale", "Totale parziale"]
    assert [abs(b.scarto) for b in blocchi] == [Decimal("100.00"), Decimal("5.00")]


def test_controllo_su_elenco_di_conti_non_e_un_blocco(tmp_path):
    righe = [("Conto uno", "150,00"), ("Conto due", "200,00"), ("Conto tre", "250,00"), ("Totale", "610,00")]
    doc = _doc(tmp_path, righe)
    assert len(blocchi_aperti(doc)) == 1          # su uno schema: un blocco
    for tipo in ("contrapposte", "verifica", "ignoto"):
        doc.profilo.tipo = tipo
        assert blocchi_aperti(doc) == []


def test_frase_blocco_su_due_pagine():
    b = Blocco(voce="B) II - Crediti", codice="", sezione="SP", lato="U", colonna=0, fine=date(2025, 12, 31),
               mesi=12, corrente=True, stampato=Decimal("1234.56"), somma=Decimal("1200.00"),
               scarto=Decimal("34.56"), pagina=4, righe=("p3r21U", "p4r11U"), etichette=(), cercato=True)
    assert frase_blocco(b) == ("B) II - Crediti (2025, pp. 3-4, righe 21-11): stampato 1.234,56, "
                               "i conti sommano 1.200,00, scarto 34,56")


def test_taglio_del_tratto_a_minimo_scarto(tmp_path):
    ids = lambda doc: {r.etichetta: r.id for r in doc.righe}
    # il totale non chiuso sta dopo un sottototale chiuso e due righe sciolte: 150 + 200 = 350 (scarto 10 su 360)
    # contro 350 + 100 del sottototale = 450 (scarto -90): vince il tratto che si ferma davanti al sottototale
    doc = _doc(tmp_path, [("Conto x", "150,00"), ("Conto y", "200,00"), ("Totale", "360,00")])
    (b,) = blocchi_aperti(doc)
    assert (b.somma, b.scarto, b.cercato) == (Decimal("350.00"), Decimal("10.00"), True)
    assert b.righe == (ids(doc)["Conto x"], ids(doc)["Totale"])
    # stampato 460: ora vince il tratto che include il sottototale chiuso (450, scarto 10) contro 350 (scarto 110)
    doc = _doc(tmp_path, [("Conto x", "150,00"), ("Conto y", "200,00"), ("Totale", "460,00")])
    (b,) = blocchi_aperti(doc)
    assert (b.somma, b.scarto) == (Decimal("450.00"), Decimal("10.00"))
    assert b.righe == (ids(doc)["Totale apertura"], ids(doc)["Totale"])
    assert "Totale apertura" in b.etichette
