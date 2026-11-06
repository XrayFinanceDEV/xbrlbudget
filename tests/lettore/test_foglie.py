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
    from importers.lettore.foglie import gettoni_di_legge
    assert gettoni_di_legge("C) ATTIVO CIRCOLANTE") == ("C",)
    assert gettoni_di_legge("II - Crediti") == ("II",)
    assert gettoni_di_legge("5-bis) crediti tributari") == ("5-bis",)
    assert gettoni_di_legge("c) trattamento di fine rapporto") == ("c",)
    assert gettoni_di_legge("C.II.1) Crediti verso clienti") == ("C", "II", "1")
    assert gettoni_di_legge("Conto", "B.I.2") == ("B", "I", "2")
    assert gettoni_di_legge("I.V.A. a credito") == ()
    assert gettoni_di_legge("A. Rossi s.r.l.") == ()


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


# --- Fix round 1 -----------------------------------------------------------------------------------------------

def _crediti_attivo(*righe):
    voci = [(50, 112, "STATO PATRIMONIALE ATTIVO")]
    return voci + _righe(140, [("C) ATTIVO CIRCOLANTE",), ("II - Crediti",), *righe])


def test_elenco_numerato_di_clienti_sono_conti_non_livelli(tmp_path):
    # «1) Rossi» sotto un padre verificato che ha gia' il livello arabo «1)» e' un conto: non sposta la voce
    voci = _crediti_attivo(("1) verso clienti esigibili entro", "613,00"), ("1) Rossi srl", "101,00"),
                           ("2) Bianchi spa", "202,00"), ("3) Verdi snc", "310,00"),
                           ("5-bis) crediti tributari", "47,00"), ("Erario c/iva", "47,00"),
                           ("Totale crediti", "660,00"))
    f = _per_etichetta(foglie_contabili(_doc(tmp_path, voci), 0))
    assert f["1) Rossi srl"].percorso_legale == "SPA.C.II.1.E"
    assert f["2) Bianchi spa"].percorso_legale == "SPA.C.II.1.E"
    assert f["3) Verdi snc"].percorso_legale == "SPA.C.II.1.E"


def test_livelli_si_chiudono_con_il_totale(tmp_path):
    voci = _crediti_attivo(("1) verso clienti esigibili entro", "301,00"), ("Cliente Rossi", "101,00"),
                           ("Cliente Bianchi", "200,00"), ("Totale crediti", "301,00"),
                           ("Banca c/c", "517,00"), ("Cassa", "23,00"), ("Magazzino", "71,00"))
    f = _per_etichetta(foglie_contabili(_doc(tmp_path, voci), 0))
    assert f["Cliente Rossi"].percorso_legale == "SPA.C.II.1.E"
    for nome in ("Banca c/c", "Cassa", "Magazzino"):
        assert f[nome].percorso_legale in (None, "SPA.C")      # mai il C.II.1.E del blocco chiuso


def _riga_finta(id_, etichetta, **kw):
    from importers.lettore.righe import Riga
    return Riga(id=id_, pagina=1, y=float(len(id_)), lato="U", sezione="SP", codice="", etichetta=etichetta,
                celle={}, **kw)


def test_percorso_dall_antenato_verificato_batte_quello_posizionale():
    from importers.lettore.foglie import _Percorsi, _scorri
    righe = [_riga_finta("r1", "STATO PATRIMONIALE ATTIVO", intestazione=True),
             _riga_finta("r2", "C) ATTIVO CIRCOLANTE", intestazione=True),
             _riga_finta("r3", "II - Crediti", intestazione=True),
             _riga_finta("r4", "1) verso clienti esigibili entro", totale=True),
             _riga_finta("r5", "5-bis) crediti tributari", intestazione=True),      # sposta l'outline posizionale
             _riga_finta("r6", "Cliente Rossi", padre="r4", padre_verificato=True)]
    pos = _scorri(righe)
    assert pos["r6"].livelli == ("C", "II", "5-bis")                  # il posizionale sbaglia
    assert _Percorsi(righe, pos).posizione(righe[5]).livelli == ("C", "II", "1")
    assert _Percorsi(righe, pos).posizione(righe[5]).scad == "E"


def test_costo_stampato_negativo_in_un_risultato_resta_positivo(tmp_path):
    righe = [("C) PROVENTI E ONERI FINANZIARI",), ("16) altri proventi finanziari", "300,00"),
             ("17) interessi e altri oneri finanziari", "(120,00)"),
             ("Totale proventi e oneri finanziari", "180,00"),
             ("Ricavi diversi", "710,00"), ("Costi diversi", "430,00"), ("Spese varie", "19,00"),
             ("Ammortamenti", "88,00")]
    voci = [(50, 112, "CONTO ECONOMICO")] + _righe(140, righe)
    f = _per_etichetta(foglie_contabili(_doc(tmp_path, voci), 0))
    assert f["17) interessi e altri oneri finanziari"].importo == Decimal("120.00")
    assert f["16) altri proventi finanziari"].importo == Decimal("300.00")


def _ce_contrapposto(costi, ricavi, nome_costi_totale="Totale a pareggio"):
    voci = [(40, 100, "CONTO ECONOMICO"), (40, 120, "Costi"), (310, 120, "Ricavi")]
    for k in range(max(len(costi), len(ricavi))):
        y = 140 + 14 * k
        if k < len(costi):
            voci += [(40, y, costi[k][0]), (280, y, costi[k][1])]
        if k < len(ricavi):
            voci += [(310, y, ricavi[k][0]), (560, y, ricavi[k][1])]
    return voci


def test_utile_e_perdita_con_il_loro_segno(tmp_path):
    costi = [("Acquisti merci", "310,00"), ("Servizi", "410,00"), ("Salari", "530,00"), ("Ammortamenti", "650,00"),
             ("Interessi passivi", "500,00"), ("Totale a pareggio", "2.400,00")]
    ricavi = [("Vendite", "900,00"), ("Prestazioni", "400,00"), ("Altri ricavi", "250,00"),
              ("Interessi attivi", "150,00"), ("Perdita d'esercizio", "700,00"), ("Totale a pareggio", "2.400,00")]
    doc = _doc(tmp_path, _ce_contrapposto(costi, ricavi))
    corrente, _ = colonne_utili(doc)
    trovate = {a.chiave: a for a in ancore(doc, corrente)}
    assert trovate["utile"].importo == Decimal("-700.00")
    assert not any(f.etichetta.startswith("Perdita") for f in foglie_contabili(doc, corrente))


def test_totale_generale_chiuso_batte_la_riga_ripetuta_dopo(tmp_path):
    voci = _contrapposte_sp() + [(40, 140 + 14 * 7, "Totale attivita"), (280, 140 + 14 * 7, "9.999,00")]
    doc = _doc(tmp_path, voci)
    corrente, _ = colonne_utili(doc)
    assert {a.chiave: a for a in ancore(doc, corrente)}["attivo"].importo == Decimal("2100.00")


def test_ancora_di_macro_senza_scadenza_se_le_foglie_concordano(tmp_path):
    voci = _crediti_attivo(("1) verso clienti", "301,00"), ("Cliente Rossi", "101,00"), ("Cliente Bianchi", "200,00"),
                           ("Totale crediti", "301,00"), ("Banca c/c", "517,00"), ("Cassa", "23,00"))
    doc = _doc(tmp_path, voci)
    assert {a.chiave: a for a in ancore(doc, 0)}["sp06"].importo == Decimal("301.00")


def _contrapposte_con_precedente():
    sx = [("Banca c/c", "110,00", "100,00"), ("Clienti Rossi", "210,00", "200,00"),
          ("Clienti Bianchi", "330,00", "310,00"), ("Magazzino merci", "450,00", "400,00"),
          ("Cassa", "500,00", "450,00"), ("Impianti", "500,00", "430,00")]
    dx = [("Capitale sociale", "250,00", "240,00"), ("Fornitori Alfa", "310,00", "301,00"),
          ("Fornitori Beta", "420,00", "411,00"), ("Mutuo banca", "520,00", "512,00"),
          ("Debiti tributari", "500,00", "493,00"), ("Debiti vari", "100,00", "93,00")]
    voci = [(40, 100, "STATO PATRIMONIALE"), (40, 120, "Attivo"), (310, 120, "Passivo"),
            (200, 118, "31/12/2025"), (280, 118, "31/12/2024"), (480, 118, "31/12/2025"), (560, 118, "31/12/2024")]
    for k, ((a, c, p), (b, ic, ip)) in enumerate(zip(sx, dx)):
        y = 140 + 14 * k
        voci += [(40, y, a), (200, y, c), (280, y, p), (310, y, b), (480, y, ic), (560, y, ip)]
    return voci


def test_colonna_precedente_sulle_contrapposte(tmp_path):
    doc = _doc(tmp_path, _contrapposte_con_precedente())
    corrente, precedente = colonne_utili(doc)
    f = foglie_contabili(doc, precedente)
    assert sum(x.importo for x in f if x.lato_sp == "A") == Decimal("1890.00")
    assert sum(x.importo for x in f if x.lato_sp == "P") == Decimal("2050.00")


def test_righe_senza_la_colonna_dell_altro_lato_si_dichiarano(tmp_path):
    from importers.lettore.foglie import senza_colonna
    doc = _doc(tmp_path, _contrapposte_con_precedente())
    corrente, precedente = colonne_utili(doc)
    assert not senza_colonna(doc, precedente)
    # il lato destro perde la sua colonna precedente: le sue righe non spariscono in silenzio
    doc.colonne = [c for c in doc.colonne if c.indice != 3]
    mancanti = senza_colonna(doc, precedente)
    destre = {f.id for f in foglie_contabili(doc, corrente) if f.lato_sp == "P"}
    assert destre and destre <= set(mancanti)
    assert {f.lato_sp for f in foglie_contabili(doc, precedente)} == {"A"}


def test_conti_di_una_coppia_parziali_totali(tmp_path):
    from tests.lettore.test_totali import _parziali_e_totali
    doc = _doc(tmp_path, _parziali_e_totali())
    corrente, _ = colonne_utili(doc)
    assert doc.profilo.coppie
    nomi = {f.etichetta: f.importo for f in foglie_contabili(doc, corrente)}
    assert nomi["Crediti verso privati"] == Decimal("98180.13")
    assert "1) Crediti verso clienti" not in nomi            # la voce dei totali non e' foglia: i suoi conti si contano


# --- Fix round 2: F3-9, un percorso o e' ben formato o e' None ------------------------------------------------

def test_validatore_accetta_le_famiglie_di_lettere_dello_schema():
    from importers.lettore.foglie import percorso_valido
    for p in ("CE.B.9.a", "CE.B.9.b", "CE.B.9.c", "CE.B.9.e", "CE.B.10.a", "CE.B.10.d", "SPA.C.II.1.E",
              "SPA.B.III.2.O", "SPP.D.4.E", "SPP.A.IV", "SPA.C.II", "CE.B.7", "SPP.E", "SPA.C.II.5-bis.O"):
        assert percorso_valido(p), p


def test_validatore_rifiuta_i_percorsi_mal_formati():
    from importers.lettore.foglie import percorso_valido
    for p in ("SPA.C.1", "SPA.C.II.1.a", "SPA.C.II.1.a.E", "CE.C.16.a", "SPP.E.O", "SPA.C.II.1.2", "SPP.A.4",
              "SPA.B.II.1.E", "XX.A.1", "SPA", "CE.B.9.A"):
        assert not percorso_valido(p), p


def test_mastro_senza_numero_non_perde_il_romano(tmp_path):
    # probe 1: «1) Rossi» sotto un mastro senza enumeratore non e' un livello C.1
    voci = _crediti_attivo(("Crediti v/clienti", "300,00"), ("1) Rossi srl", "100,00"), ("2) Bianchi spa", "200,00"),
                           ("Banca c/c", "517,00"), ("Cassa", "23,00"), ("Magazzino", "71,00"))
    f = _per_etichetta(foglie_contabili(_doc(tmp_path, voci), 0))
    assert f["1) Rossi srl"].percorso_legale is None and f["2) Bianchi spa"].percorso_legale is None


def test_elenco_con_lettere_di_clienti_non_e_un_livello(tmp_path):
    # probe 2: «a) Rossi» sotto «1) verso clienti» (gia' sp06a) e' un conto
    voci = _crediti_attivo(("1) verso clienti", "300,00"), ("a) Rossi srl", "100,00"), ("b) Bianchi spa", "200,00"),
                           ("Banca c/c", "517,00"), ("Cassa", "23,00"), ("Magazzino", "71,00"))
    f = _per_etichetta(foglie_contabili(_doc(tmp_path, voci), 0))
    assert f["a) Rossi srl"].percorso_legale is None and f["b) Bianchi spa"].percorso_legale is None


def test_arabo_posizionale_senza_romano_sopra_e_none(tmp_path):
    # probe 3: nessun padre verificato (nessuna somma stampata) e nessun romano sopra l'arabo
    voci = [(50, 112, "STATO PATRIMONIALE ATTIVO")] + _righe(140, [
        ("C) ATTIVO CIRCOLANTE",), ("1) Rossi srl", "101,00"), ("2) Bianchi spa", "217,00"),
        ("Banca c/c", "519,00"), ("Cassa", "23,00"), ("Magazzino", "71,00"), ("Impianti", "37,00")])
    f = _per_etichetta(foglie_contabili(_doc(tmp_path, voci), 0))
    assert f["1) Rossi srl"].percorso_legale is None


def test_lettera_di_scadenza_non_e_un_livello(tmp_path):
    voci = _crediti_attivo(("5-bis) crediti tributari", "700,00"), ("a) Erario esigibili entro", "300,00"),
                           ("b) Erario esigibili oltre", "400,00"), ("Banca c/c", "517,00"), ("Cassa", "23,00"),
                           ("Magazzino", "71,00"))
    f = _per_etichetta(foglie_contabili(_doc(tmp_path, voci), 0))
    assert f["a) Erario esigibili entro"].percorso_legale == "SPA.C.II.5-bis.E"
    assert f["b) Erario esigibili oltre"].percorso_legale == "SPA.C.II.5-bis.O"
