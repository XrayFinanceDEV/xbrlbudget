"""Task 2 (Fase 3): foglie contate una volta e ancore stampate."""
from decimal import Decimal

from importers.lettore import leggi_pdf
from importers.lettore.foglie import ancore, colonne_utili, foglie_contabili
from tests.lettore.pdf_sintetico import scrivi_pdf
from tests.lettore.test_righe import _INTERI, _riempi
from tests.lettore.test_totali import _righe


def _prospetto_e_nota(tabella):
    prospetto = [(50, 100, "STATO PATRIMONIALE")] + _riempi(140, n=8)
    nota = [(50, 100, "NOTA INTEGRATIVA"), (50, 124, "Patrimonio netto"),
            (268, 140, "Importo"), (304, 140, "Possibilita' di utilizzazione")] + tabella
    return [prospetto, nota]


def _doc(tmp_path, voci, nome="f.pdf", pagine=None):
    p = tmp_path / nome
    scrivi_pdf(p, pagine or [voci])
    return leggi_pdf(str(p))


def _per_etichetta(foglie):
    return {f.etichetta: f for f in foglie}


def test_mastro_e_figli_contano_una_volta(tmp_path):
    doc = _doc(tmp_path, _righe(140, [("Crediti v/clienti", "300,00"), ("Cliente Rossi", "100,00"),
                                      ("Cliente Bianchi", "200,00"), ("Banca", "500,00"), ("Cassa", "50,00"),
                                      ("Totale", "850,00")]))
    foglie = foglie_contabili(doc, 0)
    assert [f.etichetta for f in foglie] == ["Cliente Rossi", "Cliente Bianchi", "Banca", "Cassa"]
    assert sum(f.importo for f in foglie) == Decimal("850.00")


def test_foglia_senza_figli_verificati_resta_foglia(tmp_path):
    # il titolo ha un importo ma i figli non sommano: nessun totale, quindi nessun doppio conteggio da evitare
    doc = _doc(tmp_path, _righe(140, [("Crediti diversi", "999,00"), ("Conto uno", "100,00"), ("Conto due", "250,00"),
                                      ("Banca", "500,00"), ("Cassa", "50,00"), ("Magazzino", "70,00")]))
    nomi = {f.etichetta for f in foglie_contabili(doc, 0)}
    assert "Conto uno" in nomi and "Conto due" in nomi


def test_percorso_legale_dall_antenato(tmp_path):
    voci = [(50, 112, "STATO PATRIMONIALE ATTIVO")]
    voci += _righe(140, [("C) ATTIVO CIRCOLANTE",), ("II - Crediti",), ("1) verso clienti esigibili entro", "300,00"),
                         ("Cliente Rossi", "100,00"), ("Cliente Bianchi", "200,00"), ("Totale crediti", "300,00")])
    doc = _doc(tmp_path, voci)
    f = _per_etichetta(foglie_contabili(doc, 0))["Cliente Rossi"]
    assert f.percorso_legale == "SPA.C.II.1.E"
    assert f.lato_sp == "A"
    assert "1) verso clienti esigibili entro" in f.antenati


def test_ancora_di_macro_voce(tmp_path):
    voci = [(50, 112, "STATO PATRIMONIALE ATTIVO")]
    voci += _righe(140, [("C) ATTIVO CIRCOLANTE",), ("II - Crediti",), ("1) verso clienti esigibili entro", "300,00"),
                         ("Cliente Rossi", "100,00"), ("Cliente Bianchi", "200,00"), ("Totale crediti", "300,00")])
    doc = _doc(tmp_path, voci)
    trovate = {a.chiave: a for a in ancore(doc, 0)}
    assert trovate["sp06"].importo == Decimal("300.00")
    ids = {f.id for f in foglie_contabili(doc, 0)}
    assert set(trovate["sp06"].foglie) == ids


def test_crediti_senza_scadenza_con_foglie_miste_non_ancorano(tmp_path):
    voci = [(50, 112, "STATO PATRIMONIALE ATTIVO")]
    voci += _righe(140, [("C) ATTIVO CIRCOLANTE",), ("II - Crediti",), ("1) verso clienti esigibili entro", "300,00"),
                         ("Cliente Rossi", "300,00"), ("1) verso clienti esigibili oltre", "100,00"),
                         ("Cliente Verdi", "100,00"), ("Totale crediti", "400,00")])
    doc = _doc(tmp_path, voci)
    assert not [a for a in ancore(doc, 0) if a.chiave in ("sp06", "sp07")]


def _contrapposte_sp():
    sx = [("Banca c/c", "110,00"), ("Clienti Rossi", "210,00"), ("Clienti Bianchi", "330,00"),
          ("Magazzino merci", "450,00"), ("Cassa", "500,00"), ("Impianti", "500,00"), ("Totale attivita", "2.100,00")]
    dx = [("Capitale sociale", "250,00"), ("Fornitori Alfa", "310,00"), ("Fornitori Beta", "420,00"),
          ("Mutuo banca", "520,00"), ("Debiti tributari", "500,00"), ("Utile d'esercizio", "100,00"),
          ("Totale passivita", "2.100,00")]
    voci = [(40, 100, "STATO PATRIMONIALE"), (40, 120, "Attivo"), (310, 120, "Passivo")]
    for k, ((a, ia), (b, ib)) in enumerate(zip(sx, dx)):
        y = 140 + 14 * k
        voci += [(40, y, a), (280, y, ia), (310, y, b), (560, y, ib)]
    return voci


def test_ancore_attivo_passivo_utile(tmp_path):
    doc = _doc(tmp_path, _contrapposte_sp())
    corrente, _ = colonne_utili(doc)
    trovate = {a.chiave: a for a in ancore(doc, corrente)}
    assert trovate["attivo"].importo == Decimal("2100.00")
    assert trovate["passivo"].importo == Decimal("2100.00")
    assert trovate["utile"].importo == Decimal("100.00")
    f = _per_etichetta(foglie_contabili(doc, corrente))
    assert f["Banca c/c"].lato_sp == "A" and f["Fornitori Alfa"].lato_sp == "P"
    assert sum(f[e].importo for e in f if f[e].lato_sp == "A") == Decimal("2100.00")
    assert set(trovate["attivo"].foglie) == {x.id for x in f.values() if x.lato_sp == "A"}


def test_righe_della_nota_escluse(tmp_path):
    tabella = []
    for k in range(4):
        y = 156 + k * 16
        tabella += [(45, y, f"Riserva {k + 1}"), (294.6, y, _INTERI[k]), (420, y, _INTERI[k + 1])]
    doc = _doc(tmp_path, None, pagine=_prospetto_e_nota(tabella))
    nomi = {f.etichetta for f in foglie_contabili(doc, 0)}
    assert nomi and all(n.startswith("Voce") for n in nomi)
    assert not any(n.startswith("Riserva") for n in nomi)


def _con_date(voci_dx=(), prima=True):
    return [(50, 100, "STATO PATRIMONIALE"), (480, 118, "31/12/2025"), (560, 118, "31/12/2024")]


def test_colonne_utili(tmp_path):
    doc = _doc(tmp_path, _con_date() + _riempi(140, n=8))
    assert colonne_utili(doc) == (0, 1)
    solo = _doc(tmp_path, [(50, 100, "STATO PATRIMONIALE"), (560, 118, "31/12/2025")]
                + _riempi(140, n=8, colonne=(560,)), "s.pdf")
    assert colonne_utili(solo) == (0, None)


def test_differenza_e_percentuale_mai_scelte(tmp_path):
    voci = [(50, 100, "STATO PATRIMONIALE"), (400, 118, "31/12/2025"), (480, 118, "31/12/2024"),
            (560, 118, "Differenza")] + _riempi(140, n=8, colonne=(400, 480, 560))
    doc = _doc(tmp_path, voci)
    corrente, precedente = colonne_utili(doc)
    assert doc.colonne[corrente].ruolo == "esercizio" and doc.colonne[precedente].ruolo == "esercizio"


def test_fondo_negativo_e_conto_positivo(tmp_path):
    voci = _righe(140, [("Immobilizzazioni materiali", "700,00"), ("Macchinari", "1.000,00"),
                        ("(Fondo ammortamento)", "300,00"), ("Banca", "510,00"), ("Cassa", "20,00"),
                        ("Magazzino", "33,00")])
    doc = _doc(tmp_path, voci)
    f = _per_etichetta(foglie_contabili(doc, 0))
    assert f["Macchinari"].importo == Decimal("1000.00")
    assert f["(Fondo ammortamento)"].importo == Decimal("-300.00")


def test_colonna_unica_con_marcatore_il_passivo_resta_positivo(tmp_path):
    voci = [(50, 100, "STATO PATRIMONIALE PASSIVO"), (560, 118, "31/12/2025")]
    importi = (137, 251, 389, 412, 566, 631, 704, 853, 917, 1021, 1109, 1237)
    for k in range(12):
        voci += [(50, 140 + 14 * k, f"Fornitore {k + 1}"), (540, 140 + 14 * k, f"{importi[k]},00"), (548, 140 + 14 * k, "A")]
    doc = _doc(tmp_path, voci)
    assert doc.profilo.marcatori
    f = _per_etichetta(foglie_contabili(doc, 0))
    assert f["Fornitore 3"].lato_sp == "P" and f["Fornitore 3"].importo == Decimal("389.00")


def test_conversione_degli_enumeratori_in_percorso():
    from importers.lettore.foglie import _gettoni
    assert _gettoni("C) ATTIVO CIRCOLANTE") == ("C",)
    assert _gettoni("II - Crediti") == ("II",)
    assert _gettoni("5-bis) crediti tributari") == ("5-bis",)
    assert _gettoni("c) trattamento di fine rapporto") == ("c",)
    assert _gettoni("C.II.1) Crediti verso clienti") == ("C", "II", "1")
    assert _gettoni("Conto", "B.I.2") == ("B", "I", "2")
    assert _gettoni("I.V.A. a credito") == ()
    assert _gettoni("A. Rossi s.r.l.") == ()


def test_verso_dal_lato_sul_conto_economico_contrapposto(tmp_path):
    sx = [("Acquisti merci", "110,00"), ("Servizi", "210,00"), ("Salari", "330,00"), ("Ammortamenti", "450,00"),
          ("Interessi passivi", "500,00"), ("Utile d'esercizio", "100,00"), ("Totale a pareggio", "1.700,00")]
    dx = [("Vendite", "900,00"), ("Prestazioni", "400,00"), ("Altri ricavi", "250,00"), ("Interessi attivi", "150,00"),
          ("", ""), ("", ""), ("Totale a pareggio", "1.700,00")]
    voci = [(40, 100, "CONTO ECONOMICO"), (40, 120, "Costi"), (310, 120, "Ricavi")]
    for k, ((a, ia), (b, ib)) in enumerate(zip(sx, dx)):
        y = 140 + 14 * k
        voci += [(40, y, a), (280, y, ia)]
        if b:
            voci += [(310, y, b), (560, y, ib)]
    doc = _doc(tmp_path, voci)
    corrente, _ = colonne_utili(doc)
    f = _per_etichetta(foglie_contabili(doc, corrente))
    assert f["Salari"].verso_ce == "costo" and f["Vendite"].verso_ce == "ricavo"
    assert "Utile d'esercizio" not in f
    assert f["Vendite"].importo == Decimal("900.00")
