from decimal import Decimal

import fitz
import pytest

from importers.lettore import Documento, leggi_pdf
from importers.lettore.righe import _normalizza
from tests.lettore.pdf_sintetico import scrivi_pdf

_CORPO = 9.0
_VALORI = ("1.234,56", "500,00", "98.765,43", "12,30", "4.500,00", "777,77", "80,00", "3,10")


def _riempi(y0, n=6, colonne=(480, 560), passo=14, prefisso="Voce"):
    """Righe di contorno con un importo per colonna: bastano a far riconoscere le colonne."""
    voci = []
    for k in range(n):
        y = y0 + k * passo
        voci.append((50, y, f"{prefisso} {k + 1}"))
        for j, x in enumerate(colonne):
            voci.append((x, y, _VALORI[(k + j) % len(_VALORI)]))
    return voci


def _leggi(tmp_path, pagine, nome="r.pdf") -> Documento:
    p = tmp_path / nome
    scrivi_pdf(p, pagine)
    return leggi_pdf(str(p))


def _riga(doc, testo):
    trovate = [r for r in doc.righe if testo in r.etichetta]
    assert len(trovate) == 1, [r.etichetta for r in doc.righe]
    return trovate[0]


def test_cella_vuota_non_sposta_la_riga(tmp_path):
    voci = _riempi(140, colonne=(400, 480, 560))
    voci += [(50, 240, "Crediti verso clienti"), (400, 240, "1.000,00"), (560, 240, "250,00")]
    doc = _leggi(tmp_path, [voci])
    assert len(doc.colonne) == 3
    riga = _riga(doc, "Crediti verso clienti")
    assert set(riga.celle) == {0, 2}
    assert riga.celle[0].valore == Decimal("1000.00")
    assert riga.celle[2].valore == Decimal("250.00")


def test_capitale_sociale_in_intestazione_resta_etichetta(tmp_path):
    voci = [(50, 100, "ALFA S.P.A. CAP. SOC. E"), (290, 100, "22.000.000,00")] + _riempi(140)
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "CAP. SOC.")
    assert riga.celle == {}
    assert "22.000.000,00" in riga.etichetta
    assert riga.intestazione


def test_capitale_sociale_sotto_la_colonna_resta_etichetta(tmp_path):
    # budget_1445: il secondo importo cade sotto una colonna, ma ha la valuta davanti in un'anagrafica
    voci = [(50, 100, "Capitale sociale: Euro"), (300, 100, "1.500.000,00"), (310, 100, "di cui versato: Euro"),
            (560, 100, "1.500.000,00")] + _riempi(140)
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Capitale sociale")
    assert riga.celle == {}
    assert riga.etichetta.count("1.500.000,00") == 2


def test_scadenza_in_didascalia_non_e_cella(tmp_path):
    voci = _riempi(140) + [(50, 240, "esigibili oltre 12 mesi"), (560, 240, "1.000,00")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "esigibili oltre")
    assert list(riga.celle.values())[0].valore == Decimal("1000.00")
    assert len(riga.celle) == 1
    assert "12 mesi" in riga.etichetta


def test_didascalia_a_capo_diventa_una_riga(tmp_path):
    voci = _riempi(140) + [(50, 226, "C) TRATTAMENTO DI FINE RAPPORTO DI LAVORO"), (560, 226, "387.507,50"),
                           (50, 235, "SUBORDINATO")] + _riempi(254, n=3, prefisso="Altra")
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "TRATTAMENTO")
    assert riga.etichetta == "C) TRATTAMENTO DI FINE RAPPORTO DI LAVORO SUBORDINATO"
    assert [c.valore for c in riga.celle.values()] == [Decimal("387507.50")]
    assert not [r for r in doc.righe if r.etichetta == "SUBORDINATO"]


@pytest.mark.parametrize("distanza", [4, 7])
def test_importo_orfano_si_riattacca(tmp_path, distanza):
    voci = _riempi(140) + [(50, 240, "Totale crediti verso imprese collegate"),
                           (560, 240 + distanza, "321,00")] + _riempi(268, n=3, prefisso="Altra")
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "imprese collegate")
    assert [c.valore for c in riga.celle.values()] == [Decimal("321.00")]
    assert not riga.intestazione
    assert not [r for r in doc.righe if not r.etichetta]


def test_piede_ripetuto_non_e_una_riga(tmp_path):
    pagine = [[(50, 40, "ALFA S.R.L. - Bilancio al 31/12/2025")] + _riempi(140)
              + [(250, 820, f"Pagina {n} di 3")] for n in (1, 2, 3)]
    doc = _leggi(tmp_path, pagine)
    assert not [r for r in doc.righe if "Pagina" in r.etichetta]
    assert not [r for r in doc.righe if "ALFA" in r.etichetta]
    assert len(doc.righe) == 18


def test_sezione_dai_titoli_e_continuazione(tmp_path):
    pagine = [[(50, 100, "STATO PATRIMONIALE")] + _riempi(140),
              _riempi(140, prefisso="Seguito"),
              [(50, 100, "CONTO ECONOMICO")] + _riempi(140, prefisso="Costo")]
    doc = _leggi(tmp_path, pagine)
    sezioni = {p: {r.sezione for r in doc.righe if r.pagina == p} for p in (1, 2, 3)}
    assert sezioni == {1: {"SP"}, 2: {"SP"}, 3: {"CE"}}


def test_codice_conto_separato(tmp_path):
    # il codice ha la forma dei codici del documento (Task 5-ter: le forme vengono dal profilo)
    voci = _riempi(140) + [(40, 240, "102355"), (80, 240, "151"), (100, 240, "-"),
                           (110, 240, "banche c/ricevute all'incasso"), (560, 240, "(113.340,54)")]
    for k, sotto in enumerate(("152", "153", "154")):
        voci += [(40, 254 + k * 14, "102355"), (80, 254 + k * 14, sotto), (100, 254 + k * 14, "-"),
                 (110, 254 + k * 14, f"banca {sotto}"), (560, 254 + k * 14, _VALORI[k])]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "banche c/")
    assert riga.codice == "102355 151"
    assert riga.etichetta == "banche c/ricevute all'incasso"
    assert [c.valore for c in riga.celle.values()] == [Decimal("-113340.54")]


def test_parentesi_staccata_si_ricuce(tmp_path):
    testo = "113.340,54)"
    x0 = 560 - fitz.get_text_length(testo, fontsize=_CORPO)
    voci = _riempi(140) + [(50, 240, "Fondo svalutazione"), (x0 - 6, 240, "("), (x0, 240, testo)]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Fondo svalutazione")
    assert riga.etichetta == "Fondo svalutazione"
    assert [c.valore for c in riga.celle.values()] == [Decimal("-113340.54")]


def test_scansione_senza_testo(tmp_path):
    p = tmp_path / "scansione.pdf"
    doc = fitz.open()
    pagina = doc.new_page(width=595, height=842)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 60), False)
    pix.clear_with(200)
    pagina.insert_image(fitz.Rect(50, 50, 500, 500), pixmap=pix)
    doc.save(str(p))
    doc.close()
    letto = leggi_pdf(str(p))
    assert letto.righe == []
    assert len(letto.avvisi) == 1 and "OCR" in letto.avvisi[0]


def test_contrapposte_una_riga_per_lato(tmp_path):
    voci = []
    for k in range(8):
        y = 140 + k * 14
        voci += [(40, y, f"Cliente {k + 1}"), (280, y, _VALORI[k]),
                 (310, y, f"Fornitore {k + 1}"), (560, y, _VALORI[-k - 1])]
    doc = _leggi(tmp_path, [voci])
    assert doc.contrapposto
    sinistra = [r for r in doc.righe if r.lato == "L"]
    destra = [r for r in doc.righe if r.lato == "R"]
    assert [r.etichetta for r in sinistra] == [f"Cliente {k + 1}" for k in range(8)]
    assert [r.etichetta for r in destra] == [f"Fornitore {k + 1}" for k in range(8)]
    lato_colonna = {c.indice: c.lato for c in doc.colonne}
    assert all(lato_colonna[i] == r.lato for r in doc.righe for i in r.celle)
    assert sinistra[0].id == "p1r1L" and destra[0].id == "p1r1R"


def test_id_stabili_fra_due_letture(tmp_path):
    pagine = [[(50, 100, "STATO PATRIMONIALE")] + _riempi(140), _riempi(140)]
    a = _leggi(tmp_path, pagine, "a.pdf")
    b = leggi_pdf(str(tmp_path / "a.pdf"))
    assert [r.id for r in a.righe] == [r.id for r in b.righe]
    assert len({r.id for r in a.righe}) == len(a.righe)
    assert not a.contrapposto


@pytest.mark.parametrize("token,valore", [
    ("−1.234,56", Decimal("-1234.56")),
    ("1.234,56D", Decimal("1234.56")),
    ("1.234,56A", Decimal("-1234.56")),
    ("1.234,56 A", Decimal("-1234.56")),
])
def test_meno_unicode_e_marcatore_attaccato(token, valore):
    # su una sezione unica (R23: il segno del marcatore lo da' il lato)
    from importers.lettore import leggi_importo
    from importers.lettore.importi import segno_del_lato
    letto = leggi_importo(_normalizza(token))
    assert (segno_del_lato(letto, "U").valore if letto else None) == valore


def test_testo_senza_importo_non_cambia():
    assert _normalizza("ESERCIZIO") == "ESERCIZIO"
    assert _normalizza("–") == "–"


@pytest.mark.parametrize("prima,seconda,unita", [
    ("Crediti verso imprese controllate e", "collegate", "Crediti verso imprese controllate e collegate"),
    ("6) per materie prime, sussidiarie, di con-", "sumo e di merci",
     "6) per materie prime, sussidiarie, di consumo e di merci"),
])
def test_frase_aperta_si_completa_sotto(tmp_path, prima, seconda, unita):
    voci = _riempi(140) + [(50, 226, prima), (50, 240, seconda), (560, 240, "4.321,00")] \
        + _riempi(254, n=3, prefisso="Altra")
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, unita)
    assert riga.etichetta == unita
    assert [c.valore for c in riga.celle.values()] == [Decimal("4321.00")]


# --- Fix round 1 ---------------------------------------------------------------------

def _a_destra(x_destra, y, testo):
    """Un token posato col bordo destro su `x_destra` anche quando non e' un importo per `leggi_importo`."""
    return (x_destra - fitz.get_text_length(testo, fontsize=_CORPO), y, testo)


def test_capitale_sociale_di_uno_schema_resta_in_colonna(tmp_path):
    # budget_413 p2: la voce di legge del capitale, con la valuta davanti a ogni colonna
    # il «€» il font dei PDF sintetici non lo ha: «EUR» e' la stessa valuta per il lettore
    voci = _riempi(140) + [(50, 240, "I. Capitale Sociale"), (430, 240, "EUR"), (480, 240, "10.000"),
                           (510, 240, "EUR"), (560, 240, "10.000")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Capitale Sociale")
    assert {i: c.valore for i, c in riga.celle.items()} == {0: Decimal("10000"), 1: Decimal("10000")}
    assert riga.etichetta == "I. Capitale Sociale"


_INTERI = ("10.000", "2.000", "113.452", "421.290", "1.500", "9.876", "12.345", "7.000")


def _riempi_interi(y0, n=6, colonne=(480, 560), passo=14, prefisso="Voce"):
    """Come `_riempi`, ma con gli importi senza decimali dei prospetti resi da XBRL («10.000»)."""
    voci = []
    for k in range(n):
        y = y0 + k * passo
        voci.append((50, y, f"{prefisso} {k + 1}"))
        for j, x in enumerate(colonne):
            voci.append((x, y, _INTERI[(k + j) % len(_INTERI)]))
    return voci


def test_valuta_davanti_a_una_cella_non_resta_nell_etichetta(tmp_path):
    voci = _riempi_interi(140) + [(50, 240, "IV. Riserva legale"), (440, 240, "Euro"), (520, 240, "Euro"),
                           _a_destra(560, 240, "0")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Riserva legale")
    assert riga.etichetta == "IV. Riserva legale"
    assert {i: (c.valore, c.forma) for i, c in riga.celle.items()} == {1: (Decimal("0"), "zero")}


def test_intero_nudo_in_colonna_e_un_importo(tmp_path):
    voci = _riempi_interi(140) + [(50, 240, "Altri ricavi"), _a_destra(560, 240, "-1"),
                           (50, 254, "Anno di riferimento"), _a_destra(560, 254, "2025")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Altri ricavi")
    assert {i: (c.valore, c.forma, c.testo) for i, c in riga.celle.items()} == {1: (Decimal("-1"), "importo", "-1")}
    anno = _riga(doc, "Anno di riferimento")
    assert anno.celle == {} and anno.etichetta.endswith("2025")


def test_importo_testo_e_il_token_stampato(tmp_path):
    voci = _riempi(140) + [(50, 240, "Banca c/c"), _a_destra(560, 240, "1.234,56D")]
    doc = _leggi(tmp_path, [voci])
    cella = list(_riga(doc, "Banca c/c").celle.values())[0]
    assert cella.testo == "1.234,56D" and cella.valore == Decimal("1234.56")


def _conti(y0, codici, colonna=560):
    voci = []
    for k, codice in enumerate(codici):
        voci += [(40, y0 + k * 14, codice), (110, y0 + k * 14, f"conto {codice}"),
                 (colonna, y0 + k * 14, _VALORI[k % len(_VALORI)])]
    return voci


def test_conto_a_saldo_zero_tiene_il_codice(tmp_path):
    voci = _conti(140, ["10201", "10202", "10203", "10204", "10205"]) + [(40, 210, "10208"),
                                                                          (110, 210, "BANCA SELLA")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "BANCA SELLA")
    assert riga.codice == "10208" and riga.etichetta == "BANCA SELLA"
    assert not riga.intestazione and riga.celle == {}


def test_conto_senza_importo_fra_fratelli_non_e_un_titolo(tmp_path):
    voci = []
    for k, codice in enumerate(["707230", "707240", None, "707250", "707260", "707270"]):
        y = 140 + k * 14
        if codice is None:
            voci += [(40, y, "707245"), (80, y, "000"), (100, y, "-"), (110, y, "imposta di bollo")]
            continue
        voci += [(40, y, codice), (80, y, "000"), (100, y, "-"), (110, y, f"spese {codice}"),
                 (560, y, _VALORI[k])]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "imposta di bollo")
    assert riga.codice == "707245 000" and riga.etichetta == "imposta di bollo"
    assert not riga.intestazione


def test_mastro_a_quattro_cifre_e_un_titolo_col_codice(tmp_path):
    voci = [(40, 126, "0101"), (110, 126, "CASSA E VALORI BOLLATI")] \
        + _conti(140, ["010101", "010102", "010103", "010104", "010105"])
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "CASSA E VALORI")
    assert riga.codice == "0101" and riga.etichetta == "CASSA E VALORI BOLLATI"
    assert riga.intestazione


def test_mastro_con_asterischi_e_prosa_numerata(tmp_path):
    # budget_700: «03/05/*** COSTI DI IMPIANTO» sopra i suoi conti; la prosa numerata non e' un conto
    voci = [(40, 100, "173/2008 di recepimento della direttiva"), (40, 114, "1.1 roe"),
            (40, 126, "03/05/***"), (110, 126, "COSTI DI IMPIANTO")] \
        + _conti(140, ["03/05/001", "03/05/002", "03/05/003", "03/05/004", "03/05/005"])
    doc = _leggi(tmp_path, [voci])
    mastro = _riga(doc, "COSTI DI IMPIANTO")
    assert mastro.codice == "03/05/***" and mastro.intestazione
    assert _riga(doc, "recepimento").codice == "" and _riga(doc, "recepimento").etichetta.startswith("173/2008")
    assert _riga(doc, "roe").codice == ""


def test_pagina_senza_sezione_dopo_la_chiusura_e_dichiarata(tmp_path):
    chiusa = [(50, 100, "STATO PATRIMONIALE")] + _riempi(140) + [(50, 240, "TOTALE PASSIVO"), (560, 240, "1.000,00")]
    doc = _leggi(tmp_path, [chiusa, _riempi(140, prefisso="Seguito")])
    assert {r.sezione for r in doc.righe if r.pagina == 2} == {""}
    # Task 5-ter: le sezioni sono del profilo, e il loro avviso sta con gli avvisi del documento
    assert [a for a in doc.profilo.avvisi if "pagina 2" in a and "sezione" in a]


def test_mastro_con_importo_e_forma_dei_conti_tiene_il_codice(tmp_path):
    # budget_680/700: «0103 PORTAFOGLIO ...» e «03/05/*** ...» col totale del mastro; `riga_conto` non li separa
    voci = _conti(140, ["10311", "10313", "10314", "10315"]) + [(40, 196, "0103"), (110, 196, "PORTAFOGLIO"),
                                                                 (560, 196, "599.842,84")] \
        + _conti(210, ["03/05/001", "03/05/002", "03/05/003"]) + [(40, 252, "03/05/***"),
                                                                   (110, 252, "COSTI DI IMPIANTO"),
                                                                   (560, 252, "3.597,70")]
    doc = _leggi(tmp_path, [voci])
    assert _riga(doc, "PORTAFOGLIO").codice == "0103"
    assert _riga(doc, "COSTI DI IMPIANTO").codice == "03/05/***"


def test_mastro_piu_a_sinistra_con_l_etichetta_allineata(tmp_path):
    # budget_680: il mastro «0103» stampato a x 2,8, i conti a 51,3; le etichette tutte a 79,2
    voci = []
    for k, codice in enumerate(["10311", "10313", "10314", None, "10401", "10402"]):
        y = 140 + k * 14
        if codice is None:
            voci += [(10, y, "0104"), (80, y, "CREDITI VERSO ERARIO"), (560, y, "171.763,01")]
            continue
        voci += [(52, y, codice), (80, y, f"EFFETTI {codice}"), (560, y, _VALORI[k])]
    doc = _leggi(tmp_path, [voci])
    assert _riga(doc, "CREDITI VERSO ERARIO").codice == "0104"


def test_intero_nudo_seguito_da_testo_e_un_codice(tmp_path):
    # budget_700: «Codice attivita' 255100 - LAVORAZ. DI METALLI» con il codice sotto una colonna
    voci = _riempi(140) + [(300, 100, "Codice attivita'"), _a_destra(480, 100, "255100"), (484, 100, "- LAVORAZ.")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "LAVORAZ.")
    assert riga.celle == {} and "255100" in riga.etichetta
    assert not doc.avvisi


# --- Fix round 2 ---------------------------------------------------------------------

def test_numero_del_mutuo_in_un_bilancio_coi_decimali_resta_etichetta(tmp_path):
    # budget_1325: il numero del finanziamento sotto la colonna Dare di un bilancio coi centesimi
    voci = _riempi(140) + [(50, 240, "Mutuo chirografario"), _a_destra(480, 240, "5538870"),
                           (560, 240, "1.000,00")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Mutuo chirografario")
    assert set(riga.celle) == {1} and "5538870" in riga.etichetta
    assert not doc.avvisi


@pytest.mark.parametrize("prima,numero", [("ai sensi dell'art.", "2423"), ("iscritta al REA n.", "1234567"),
                                          ("P.IVA", "9265580960"), ("di cui alla voce", "0123")])
def test_numero_di_riferimento_in_colonna_resta_etichetta(tmp_path, prima, numero):
    # budget_1532 «art. 2423», le anagrafiche delle copertine; uno zero in testa non e' un importo
    voci = _riempi_interi(140) + [(50, 240, f"Bilancio redatto {prima}"), _a_destra(560, 240, numero)]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Bilancio redatto")
    assert riga.celle == {} and riga.etichetta.endswith(numero)


def test_trattino_prima_di_importi_e_una_cella_zero(tmp_path):
    # budget_1438 «Totale variazioni - 14.227 (646)», budget_162 «Diritti vari - 245 245»
    voci = _riempi_interi(140, colonne=(400, 480, 560)) + [
        (50, 240, "Totale variazioni"), (400, 240, "-"), (480, 240, "14.227"), _a_destra(560, 240, "(646)"),
        (50, 254, "Diritti vari"), (400, 254, "-"), _a_destra(480, 254, "245"), _a_destra(560, 254, "245")]
    doc = _leggi(tmp_path, [voci])
    assert {i: c.valore for i, c in _riga(doc, "Totale variazioni").celle.items()} == {
        0: Decimal("0"), 1: Decimal("14227"), 2: Decimal("-646")}
    assert {i: c.valore for i, c in _riga(doc, "Diritti vari").celle.items()} == {
        0: Decimal("0"), 1: Decimal("245"), 2: Decimal("245")}


def test_trattino_fra_due_parole_e_un_separatore(tmp_path):
    voci = _riempi_interi(140) + [(50, 240, "RICAVI DELLE PRESTAZ."), (480, 240, "-"), (484, 240, "IMPRESE"),
                                  (560, 240, "1.500")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "RICAVI DELLE PRESTAZ.")
    assert riga.etichetta == "RICAVI DELLE PRESTAZ. - IMPRESE"
    assert {i: c.valore for i, c in riga.celle.items()} == {1: Decimal("1500")}


def test_piede_generato_automaticamente(tmp_path):
    voci = _riempi(140) + [(50, 400, "Generato automaticamente - Conforme alla tassonomia")]
    doc = _leggi(tmp_path, [voci])
    assert not [r for r in doc.righe if "Generato" in r.etichetta]


def test_codice_spaziato_non_si_tronca(tmp_path):
    # budget_405 «4 / 5 / 1 Terreni»: il codice intero se ha la forma dei codici del documento, mai «4»
    voci = _conti(140, ["4/5/2", "4/5/3", "4/5/4", "4/6/1"]) + _conti(196, ["10201", "10202", "10203"]) + [
        (40, 238, "4"), (50, 238, "/"), (56, 238, "5"), (64, 238, "/"), (70, 238, "1"), (110, 238, "Terreni"),
        (560, 238, "1.234,00"),
        (40, 252, "6"), (50, 252, "/"), (56, 252, "x"), (110, 252, "Varie"), (560, 252, "2,00")]
    doc = _leggi(tmp_path, [voci])
    terreni = _riga(doc, "Terreni")
    assert terreni.codice == "4 / 5 / 1" and terreni.etichetta == "Terreni"
    varie = _riga(doc, "Varie")
    assert varie.codice == "" and varie.etichetta.startswith("6 /")


def test_voce_bis_non_e_un_codice(tmp_path):
    # budget_1445 «5 bis) Crediti tributari»
    voci = _conti(140, ["10201", "10202", "10203", "10204"]) + [(40, 200, "5"), (50, 200, "bis)"), (80, 200, "Crediti tributari"),
                                                 (560, 200, "3,00")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Crediti tributari")
    assert riga.codice == "" and riga.etichetta == "5 bis) Crediti tributari"


def test_intero_nudo_vicino_a_un_importo_nella_stessa_colonna_cede(tmp_path):
    # budget_1438 p9: una tabella della nota con colonne sue; «0» e «302.507» cadono sulla stessa colonna
    voci = _riempi_interi(140) + [(50, 240, "CLIENTI ITALIA"), (470, 240, "302.507"), _a_destra(490, 240, "0"),
                                  (560, 240, "122.138")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "CLIENTI ITALIA")
    assert {i: c.valore for i, c in riga.celle.items()} == {0: Decimal("302507"), 1: Decimal("122138")}
    assert not doc.avvisi


@pytest.mark.parametrize("etichetta,numero", [("Numero Rea MB", "1904217"), ("Sede in VIA Roma 1 (MB)", "20813"),
                                              ("Settore di attivita' prevalente (ATECO)", "619090")])
def test_intero_di_quattro_cifre_senza_separatore_non_e_un_importo(tmp_path, etichetta, numero):
    # le copertine dei prospetti resi da XBRL: la colonna stampa «10.000», un «1904217» non e' suo
    voci = _riempi_interi(140) + [(50, 240, etichetta), _a_destra(560, 240, numero)]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, etichetta.split()[0])
    assert riga.celle == {} and riga.etichetta.endswith(numero)


def test_piede_generato_automaticamente_con_trattino_in_colonna(tmp_path):
    voci = _riempi(140) + [(300, 400, "Generato automaticamente"), (480, 400, "-"), (484, 400, "Conforme")]
    doc = _leggi(tmp_path, [voci])
    assert not [r for r in doc.righe if "Generato" in r.etichetta]


def test_due_interi_nudi_nella_stessa_colonna_restano_testo(tmp_path):
    # budget_173 p16: «0 0» di una tabella della nota sulla stessa colonna del documento
    voci = _riempi_interi(140) + [(50, 240, "Altre partecipazioni"), _a_destra(474, 240, "0"), _a_destra(488, 240, "0"),
                                  (560, 240, "1.500")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Altre partecipazioni")
    assert set(riga.celle) == {1} and not doc.avvisi


def test_rimando_di_nota_dopo_un_importo_non_e_una_cella(tmp_path):
    # budget_385 p2: «VI - Altre riserve 46.078 (1) 37.407». «(1)» e' il rimando a una nota: chiude la colonna al
    # posto dell'importo, che si legge col bordo destro del rimando; «(1)» resta testo, mai -1 nella colonna.
    voci = _riempi_interi(140) + [(50, 240, "VI - Altre riserve"), (462, 240, "46.078"), (465, 240, "(1)"),
                                  (560, 240, "37.407")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Altre riserve")
    assert {i: c.valore for i, c in riga.celle.items()} == {0: Decimal("46078"), 1: Decimal("37407")}
    assert "(1)" in riga.etichetta


def test_zero_tra_parentesi_dopo_un_importo_e_una_cella(tmp_path):
    # budget_207, 271: «IVA conto erario 4.316 (0)», lo zero dell'anno prima stampato tra parentesi
    voci = _riempi_interi(140) + [(50, 240, "IVA conto erario"), (480, 240, "4.316"), _a_destra(560, 240, "(0)")]
    doc = _leggi(tmp_path, [voci])
    assert {i: c.valore for i, c in _riga(doc, "IVA conto erario").celle.items()} == {0: Decimal("4316"),
                                                                                      1: Decimal("0")}


# --- Task 5-ter: le righe si leggono sul profilo -----------------------------------------

def test_intero_nudo_solo_dove_la_colonna_stampa_interi(tmp_path):
    # la colonna 480 stampa «10.000», la 560 «1.234,56»: un «5» e' un importo solo nella prima
    voci = []
    for k in range(6):
        y = 140 + k * 14
        voci += [(50, y, f"Voce {k + 1}"), (480, y, _INTERI[k % len(_INTERI)]), (560, y, _VALORI[k])]
    voci += [(50, 240, "Nella colonna a interi"), _a_destra(480, 240, "5"),
             (50, 254, "Nella colonna coi decimali"), _a_destra(560, 254, "5")]
    doc = _leggi(tmp_path, [voci])
    assert doc.profilo.decimali == {0: False, 1: True}
    assert {i: c.valore for i, c in _riga(doc, "colonna a interi").celle.items()} == {0: Decimal("5")}
    decimali = _riga(doc, "colonna coi decimali")
    assert decimali.celle == {} and decimali.etichetta.endswith("5")


def test_conto_a_zero_non_e_titolo(tmp_path):
    # budget_680 p1: «10501 IVA C/VENDITE» a saldo zero, sotto il mastro col suo totale e ultimo della pagina; la
    # forma «99999» nel documento e' quella delle righe con importi, quindi e' un conto, non un titolo
    voci = _conti(140, ["10201", "10202", "10203", "10204", "10205"]) + [
        (40, 210, "0105"), (110, 210, "CREDITI DIVERSI"), (560, 210, "2.000,00"),
        (40, 224, "10501"), (110, 224, "IVA C/VENDITE")]
    doc = _leggi(tmp_path, [voci])
    forme = {f.forma: f for f in doc.profilo.codici}
    assert forme["99999"].con_importi > forme["99999"].senza_importi
    riga = _riga(doc, "IVA C/VENDITE")
    assert riga.codice == "10501" and riga.etichetta == "IVA C/VENDITE"
    assert riga.celle == {} and not riga.intestazione


def test_codice_fuori_dalle_forme_del_profilo_resta_nell_etichetta(tmp_path):
    # un numero in testa che non ha la forma dei codici del documento non e' un codice
    voci = _conti(140, ["10201", "10202", "10203", "10204"]) + [
        (40, 210, "2023/45"), (110, 210, "rimborso"), (560, 210, "12,00")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "rimborso")
    assert riga.codice == "" and riga.etichetta.startswith("2023/45")
    assert _riga(doc, "conto 10203").codice == "10203"


def test_segno_fuori_profilo_dichiarato(tmp_path):
    # il documento stampa i negativi tra parentesi; un «500,00-» si legge, ma si dichiara
    voci = _riempi(140) + [(50, 240, "Rettifica uno"), (560, 240, "(1.000,00)"),
                           (50, 254, "Rettifica due"), (560, 254, "(2.000,00)"),
                           (50, 268, "Rettifica tre"), (560, 268, "500,00-")]
    doc = _leggi(tmp_path, [voci])
    assert doc.profilo.negativi == frozenset({"parentesi"})
    assert list(_riga(doc, "Rettifica tre").celle.values())[0].valore == Decimal("-500.00")
    fuori = [a for a in doc.avvisi if "500,00-" in a]
    assert len(fuori) == 1 and "parentesi" in fuori[0]
    assert not [a for a in doc.avvisi if "1.000,00" in a]


def _prospetto_e_nota(tabella):
    prospetto = [(50, 100, "STATO PATRIMONIALE")] + _riempi(140, n=8)
    nota = [(50, 100, "NOTA INTEGRATIVA"), (50, 124, "Patrimonio netto"),
            (268, 140, "Importo"), (304, 140, "Possibilita' di utilizzazione")] + tabella
    return [prospetto, nota]


def test_trattino_in_colonna_seguito_da_lettere_e_cella_zero(tmp_path):
    # R9, budget_1315 p17: «Riserve statutarie - A,B,C,D», il trattino allineato a destra con «70.000» della
    # colonna Importo, la lettera nella colonna «Possibilita' di utilizzazione»
    righe = [("Capitale", "70.000", "B"), ("Riserva da soprapprezzo", "43.898", "A,B,C,D"),
             ("Riserve di rivalutazione", "-", "A,B"), ("Riserva legale", "14.000", "A,B"),
             ("Riserve statutarie", "-", "A,B,C,D"), ("Altre riserve", "-", "A,B,C,D"),
             ("Totale", "127.898", None)]
    tabella = []
    for k, (etichetta, importo, uso) in enumerate(righe):
        y = 156 + k * 16
        tabella += [(45, y, etichetta), (294.6, y, importo)] + ([(304.4, y, uso)] if uso else [])
    doc = _leggi(tmp_path, _prospetto_e_nota(tabella))
    statutarie = _riga(doc, "Riserve statutarie")
    assert statutarie.parte == "nota"
    assert {i: (c.valore, c.forma) for i, c in statutarie.celle.items()} == {0: (Decimal("0"), "zero")}
    assert "A,B,C,D" in statutarie.etichetta
    assert {i: c.valore for i, c in _riga(doc, "Riserva legale").celle.items()} == {0: Decimal("14000")}


def test_righe_della_nota_marcate_e_lette_sulle_colonne_della_tabella(tmp_path):
    # R11: una tabella della nota resta fra le righe, marcata, e le sue celle non vanno sulle colonne dei prospetti
    tabella = []
    for k in range(4):
        y = 156 + k * 16
        tabella += [(45, y, f"Riserva {k + 1}"), (294.6, y, _INTERI[k]), (420, y, _INTERI[k + 1])]
    doc = _leggi(tmp_path, _prospetto_e_nota(tabella))
    assert [round(c.x_destra) for c in doc.colonne] == [480, 560]
    prospetto = [r for r in doc.righe if r.pagina == 1 and r.celle]
    assert prospetto and all(r.parte == "prospetto" and r.tabella is None for r in prospetto)
    riserva = _riga(doc, "Riserva 2")
    assert riserva.parte == "nota" and riserva.tabella is not None
    tab = doc.profilo.tabelle_nota[riserva.tabella]
    assert [round(x) for x in tab.colonne] == [295, 420]
    assert {i: c.valore for i, c in riserva.celle.items()} == {0: Decimal(_INTERI[1].replace(".", "")),
                                                               1: Decimal(_INTERI[2].replace(".", ""))}
    assert _riga(doc, "NOTA INTEGRATIVA").parte == "nota"


def test_contrapposto_e_il_verdetto_del_profilo(tmp_path):
    # R10: due prospetti di legge affiancati hanno lati fisici, ma non sono sezioni contrapposte
    sinistra = ["A) Crediti verso soci", "B) Immobilizzazioni", "I - Immateriali", "II - Materiali",
                "III - Finanziarie", "C) Attivo circolante", "I - Rimanenze", "II - Crediti"]
    destra = ["A) Patrimonio netto", "I - Capitale", "II - Riserve", "B) Fondi rischi", "C) TFR", "D) Debiti",
              "E) Ratei", "IX - Utile"]
    voci = []
    for k, (a, b) in enumerate(zip(sinistra, destra)):
        y = 140 + k * 14
        voci += [(40, y, a), (280, y, _VALORI[k]), (310, y, b), (560, y, _VALORI[-1 - k])]
    doc = _leggi(tmp_path, [voci])
    assert doc.profilo.confine is not None
    assert not doc.contrapposto and doc.contrapposto == doc.profilo.contrapposto
    assert {r.lato for r in doc.righe if r.celle} == {"L", "R"}


def test_percorso_di_legge_in_testa_non_e_un_codice(tmp_path):
    # budget_1540: «1.B.2.1 Materie prime» accanto ai conti «101.01.01.01»; il percorso e' la voce, non un conto
    voci = _conti(140, ["101.01.01.01", "101.01.01.02", "101.01.01.03", "101.01.01.04"]) + [
        (40, 210 + k * 14, f"1.B.2.{k + 1}") for k in range(3)] + [
        (110, 210 + k * 14, f"Voce {k + 1} di legge") for k in range(3)] + [
        (560, 210 + k * 14, _VALORI[k]) for k in range(3)]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Voce 2 di legge")
    assert riga.codice == "" and riga.etichetta.startswith("1.B.2.2")
    assert _riga(doc, "conto 101.01.01.02").codice == "101.01.01.02"


def test_percorso_di_legge_con_lettera_finale_non_e_un_codice(tmp_path):
    # budget_1540/1558: «3.B.10.a Salari e stipendi» (tre cifre: il profilo ne fa una forma)
    voci = _conti(140, ["101.01.01.01", "101.01.01.02", "101.01.01.03", "101.01.01.04"]) + [
        v for k, lettera in enumerate("abc") for v in ((40, 210 + k * 14, f"3.B.10.{lettera}"),
                                                       (110, 210 + k * 14, f"Personale {lettera}"),
                                                       (560, 210 + k * 14, _VALORI[k]))]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "Personale b")
    assert riga.codice == "" and riga.etichetta.startswith("3.B.10.b")


# --- Task 5-ter, fix round 1: titolo o conto per posizione e per ruolo della forma ----------------------------------

def _mastro_e_conti(y0, mastro, etichetta, conti, importo_mastro=True, zero=None):
    """Un mastro a x 3 col suo totale (o senza) e i suoi conti a x 52, etichette tutte a 80 (budget_680)."""
    voci = [(3, y0, mastro), (80, y0, etichetta)] + ([(560, y0, "9.636,00")] if importo_mastro else [])
    for k, conto in enumerate(conti):
        y = y0 + (k + 1) * 14
        voci += [(52, y, conto), (80, y, f"conto {conto}")]
        if conto != zero:
            voci.append((560, y, _VALORI[k % len(_VALORI)]))
    return voci


def test_mastro_ripetuto_sulla_pagina_di_continuazione_resta_un_titolo(tmp_path):
    # budget_680: «0105 I.V.A.» col totale a pagina 1, ripetuto senza importi in testa a pagina 2 sopra i suoi conti
    pagina1 = (_mastro_e_conti(100, "0103", "PORTAFOGLIO", ["10301", "10302", "10303"])
               + _mastro_e_conti(170, "0104", "ERARIO", ["10401", "10402", "10403"])
               + _mastro_e_conti(240, "0105", "I.V.A.", ["10501", "10502"]))
    pagina2 = _mastro_e_conti(100, "0105", "I.V.A.", ["10503", "10504", "10505"], importo_mastro=False)
    doc = _leggi(tmp_path, [pagina1, pagina2])
    ripetuto = next(r for r in doc.righe if r.pagina == 2 and r.codice == "0105")
    assert ripetuto.celle == {} and ripetuto.intestazione


def test_mastro_a_codice_corto_senza_saldo_resta_un_titolo(tmp_path):
    # budget_680 p5: «01100 PERDITA D'ESERCIZIO» a x 3, stessa sagoma dei conti a x 51, sopra un conto senza saldo
    voci = (_mastro_e_conti(100, "0103", "PORTAFOGLIO", ["10301", "10302", "10303", "10304"])
            + _mastro_e_conti(184, "0104", "ERARIO", ["10401", "10402", "10403"])
            + [(3, 254, "01100"), (80, 254, "PERDITA D'ESERCIZIO"), (52, 268, "10001"), (80, 268, "PERDITA ESERCIZIO"),
               (3, 282, "01999"), (80, 282, "BILANCIO CHIUSURA"), (52, 296, "99901"), (80, 296, "BILANCIO APERTURA")])
    doc = _leggi(tmp_path, [voci])
    for etichetta in ("PERDITA D'ESERCIZIO", "BILANCIO CHIUSURA"):
        assert _riga(doc, etichetta).intestazione, etichetta
    assert not _riga(doc, "PERDITA ESERCIZIO").intestazione


def test_conto_a_saldo_zero_fra_i_conti_resta_un_conto(tmp_path):
    voci = (_mastro_e_conti(100, "0103", "PORTAFOGLIO", ["10301", "10302", "10303", "10304"], zero="10302")
            + _mastro_e_conti(184, "0104", "ERARIO", ["10401", "10402", "10403"]))
    doc = _leggi(tmp_path, [voci])
    zero = _riga(doc, "conto 10302")
    assert zero.codice == "10302" and zero.celle == {} and not zero.intestazione
    assert not _riga(doc, "PORTAFOGLIO").intestazione


def test_famiglia_piu_lunga_della_forma_non_e_un_codice(tmp_path):
    # la famiglia «9/9» dei codici «10/01» non fa un codice di «12/3456», piu' lungo di ogni codice allineato
    voci = _conti(140, ["10/01", "10/02", "10/03", "10/04"]) + [(40, 210, "12/3456"), (110, 210, "rimborso"),
                                                                 (560, 210, "12,00"), (40, 224, "1/2"),
                                                                 (110, 224, "conto corto"), (560, 224, "3,10")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "rimborso")
    assert riga.codice == "" and riga.etichetta.startswith("12/3456")
    assert _riga(doc, "conto corto").codice == "1/2"


def test_trattino_seguito_da_una_parola_lontana_e_cella_zero(tmp_path):
    # budget_201/202 p16: «Utili portati a nuovo - U», una riga sola: nessuna colonna di testo, ma la «U» e' a 77 pt
    tabella = [(45, 156, "Riserva legale"), (294.6, 156, "4.132"), (45, 172, "Riserva straordinaria"),
               (294.6, 172, "3.705"), (45, 188, "Utili portati a nuovo"), (294.6, 188, "-"), (372, 188, "U"),
               (45, 204, "Totale"), (294.6, 204, "7.837")]
    doc = _leggi(tmp_path, _prospetto_e_nota(tabella))
    utili = _riga(doc, "Utili portati a nuovo")
    assert {i: c.forma for i, c in utili.celle.items()} == {0: "zero"}


def test_variazione_tra_parentesi_in_una_tabella_della_nota_e_una_cella(tmp_path):
    # budget_255 p26: «(311)» in una tabella della nota a interi e' una variazione di -311, non un rimando
    tabella = []
    for k, (etichetta, a, b) in enumerate([("Crediti tributari", "18.315", "16.733"), ("Altri crediti", "1.271", "(311)"),
                                           ("Totale", "19.586", "16.422")]):
        y = 156 + k * 16
        tabella += [(45, y, etichetta), (300, y, a), _a_destra(400, y, b) if b == "(311)" else (400, y, b)]
    doc = _leggi(tmp_path, _prospetto_e_nota(tabella))
    assert {i: c.valore for i, c in _riga(doc, "Altri crediti").celle.items()} == {0: Decimal("1271"),
                                                                                  1: Decimal("-311")}


def test_filetto_verticale_in_testa_al_lato_non_nasconde_il_codice(tmp_path):
    # budget_375: sul lato destro delle contrapposte ogni riga comincia col filetto «|»
    voci = []
    for k in range(6):
        y = 140 + k * 14
        voci += [(20, y, f"205.0001{k}"), (75, y, f"Attivo {k}"), (276, y, _VALORI[k]), (294, y, "|"),
                 (302, y, f"303.0100{k}"), (360, y, f"Passivo {k}"), (561, y, _VALORI[-1 - k])]
    voci += [(294, 230, "|"), (294, 236, "|")]
    doc = _leggi(tmp_path, [voci])
    passivo = _riga(doc, "Passivo 2")
    assert passivo.lato == "R" and passivo.codice == "303.01002" and passivo.etichetta == "Passivo 2"
    assert not [r for r in doc.righe if r.etichetta.strip("| ") == "" and not r.codice and not r.celle]


def test_colonna_della_nota_con_soli_zeri_e_una_colonna(tmp_path):
    # budget_1437 p17: «Totali 191.633 0 0», le ultime due colonne della tabella stampano solo zeri
    tabella = []
    for k, (etichetta, a) in enumerate([("Fondo iniziale", "191.633"), ("Utilizzi", "12.000"), ("Totali", "203.633")]):
        y = 156 + k * 16
        tabella += [(45, y, etichetta), (300, y, a), _a_destra(400, y, "0"), _a_destra(480, y, "0")]
    doc = _leggi(tmp_path, _prospetto_e_nota(tabella))
    totali = _riga(doc, "Totali")
    assert totali.etichetta == "Totali"
    assert {i: c.valore for i, c in totali.celle.items()} == {0: Decimal("203633"), 1: Decimal("0"), 2: Decimal("0")}


def test_valuta_dopo_la_cella_non_apre_l_etichetta_del_lato_destro():
    # 1456: «59.743,13 €» a sinistra e «04.03 Costi di impianto» a destra: il segno dell'euro (che i font di base
    # dei PDF sintetici non stampano, per questo il test lavora sulle parole) non resta davanti al codice del lato
    # destro
    from importers.lettore.geometria import Parola
    from importers.lettore.profilo import senza_filetti
    parole = [Parola(411, 100, 415, 108, "€"), Parola(427, 100, 446, 108, "04.03"), Parola(497, 100, 517, 108, "Costi")]
    assert [p.testo for p in senza_filetti(parole)] == ["04.03", "Costi"]
    # in coda resta: «Capitale sociale €» e' testo dell'etichetta, la valuta in coda la toglie `_celle_del_lato`
    assert [p.testo for p in senza_filetti(parole[1:] + parole[:1])] == ["04.03", "Costi", "€"]



def _verifica_a_marcatore():
    """680: una colonna di saldi col marcatore D/A staccato dopo ogni importo, il mastro col suo saldo."""
    righe = [("0101", "CASSA E VALORI BOLLATI", "1.199,64", "A"), ("10101", "CASSA CONTANTI", "839,66", "D"),
             ("10102", "VALORI BOLLATI", "48,70", "D"), ("10104", "VALORI BOLLATI VIRTUALI", "118,00", "A"),
             ("10105", "CARTA DI CREDITO", "1.970,00", "A"), ("0102", "BANCHE", "390.977,16", "D"),
             ("10202", "INTESA SANPAOLO", "2.882,08", "D"), ("10206", "BANCA DI ASTI", "67.994,40", "D"),
             ("10207", "CREDEM", "320.100,68", "D"), ("0103", "CLIENTI", "12.500,00", "D"),
             ("10301", "CLIENTE ALFA", "10.000,00", "D"), ("10302", "CLIENTE BETA", "2.500,00", "D")]
    voci = []
    for k, (codice, etichetta, importo, marcatore) in enumerate(righe):
        y = 140 + k * 14
        x = 40 if len(codice) == 4 else 60
        voci += [(x, y, codice), (x + 40, y, etichetta), (480, y, importo), (484, y, marcatore)]
    return voci


def test_marcatore_per_colonna_e_il_segno_della_cella(tmp_path):
    # Q2: la colonna porta il D/A dopo ogni importo: il marcatore e' il segno (D positivo, A negativo su una sezione
    # unica) e non resta nell'etichetta; il mastro chiude coi segni
    doc = _leggi(tmp_path, [_verifica_a_marcatore()])
    assert doc.profilo.marcatori == frozenset({0})
    cassa = _riga(doc, "CASSA E VALORI BOLLATI")
    assert cassa.etichetta == "CASSA E VALORI BOLLATI"
    assert cassa.celle[0].valore == Decimal("-1199.64")
    assert _riga(doc, "CARTA DI CREDITO").celle[0].valore == Decimal("-1970.00")
    assert _riga(doc, "CASSA CONTANTI").celle[0].valore == Decimal("839.66")
    assert cassa.totale and len(cassa.figli[0]) == 4
    assert _riga(doc, "CARTA DI CREDITO").padre == cassa.id and _riga(doc, "CARTA DI CREDITO").padre_verificato


def test_due_marcatori_sparsi_in_una_contrapposta_restano_testo(tmp_path):
    # 365, 367: due «A» dopo un importo su novanta celle non fanno una colonna a marcatore: tutto come prima
    sinistra = ("1.234,56", "500,00", "98.765,43", "12,30", "4.500,00", "777,77", "80,00", "3,10")
    destra = ("1.000,00", "620,50", "90.000,00", "15,00", "4.100,10", "700,00", "55,55", "9,90")
    voci = []
    for k, (a, b) in enumerate(zip(sinistra, destra)):
        y = 140 + k * 14
        voci += [(40, y, f"0{k + 1}.01"), (80, y, f"Cliente {k + 1}"), (280, y, a),
                 (310, y, f"2{k + 1}.01"), (350, y, f"Fornitore {k + 1}"), (560, y, b)]
        if k in (2, 5):
            voci.append((284, y, "A"))
    doc = _leggi(tmp_path, [voci])
    assert doc.contrapposto
    assert doc.profilo.marcatori == frozenset()
    assert _riga(doc, "Cliente 3").celle[0].valore == Decimal("98765.43")
    assert sum(r.etichetta.split().count("A") for r in doc.righe) == 2      # i due «A» restano testo


def test_marcatori_sul_lato_destro_delle_contrapposte(tmp_path):
    # R23: a destra (passivo, ricavi) A positivo e D negativo, per la colonna a marcatore come per il marcatore
    # attaccato; a sinistra (attivo, costi) D positivo e A negativo
    voci = []
    for k in range(12):
        y = 140 + k * 14
        voci += [(40, y, f"0{k + 1}.01"), (80, y, f"Cliente {chr(65 + k)}x"), (280, y, f"{k + 1}.000,50"),
                 (284, y, "A" if k == 3 else "D"),
                 (310, y, f"2{k + 1}.01"), (350, y, f"Fornitore {chr(65 + k)}x"), (560, y, f"{k + 2}.100,25"),
                 (564, y, "D" if k == 5 else "A")]
    # il marcatore attaccato («750,00A»): un token solo, col bordo destro sulla colonna
    for y, etichetta, token in ((324, "Debito attaccato", "750,00A"), (338, "Anticipo attaccato", "80,00D")):
        voci += [(310, y, "29.01"), (350, y, etichetta), (567 - fitz.get_text_length(token, fontsize=_CORPO), y, token)]
    doc = _leggi(tmp_path, [voci])
    assert doc.contrapposto
    assert doc.profilo.marcatori == frozenset({0, 1})
    assert _riga(doc, "Cliente Ax").celle[0].valore == Decimal("1000.50")
    assert _riga(doc, "Cliente Dx").celle[0].valore == Decimal("-4000.50")
    assert _riga(doc, "Fornitore Ax").celle[1].valore == Decimal("2100.25")
    assert _riga(doc, "Fornitore Fx").celle[1].valore == Decimal("-7100.25")
    assert _riga(doc, "Debito attaccato").celle[1].valore == Decimal("750.00")
    assert _riga(doc, "Anticipo attaccato").celle[1].valore == Decimal("-80.00")
