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
    voci = _riempi(140) + [(40, 240, "102355"), (80, 240, "151"), (100, 240, "-"),
                           (110, 240, "banche c/ricevute all'incasso"), (560, 240, "(113.340,54)")]
    doc = _leggi(tmp_path, [voci])
    riga = _riga(doc, "banche")
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
    from importers.lettore import leggi_importo
    letto = leggi_importo(_normalizza(token))
    assert (letto.valore if letto else None) == valore


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
    assert [a for a in doc.avvisi if "pagina 2" in a and "sezione" in a]


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
