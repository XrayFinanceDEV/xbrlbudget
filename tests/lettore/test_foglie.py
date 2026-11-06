"""Task 2 (Fase 3): foglie contate una volta e ancore stampate."""
from decimal import Decimal

from importers.lettore import leggi_pdf
from importers.lettore.foglie import (_fine_finestra, _livelli_eco, _scorri, ancore, colonne_utili,
                                       foglie_contabili)
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
    # probe 2 (F3-10): «a) Rossi» sotto «1) verso clienti» (gia' sp06a) e' un conto: tiene il percorso della voce
    voci = _crediti_attivo(("1) verso clienti", "300,00"), ("a) Rossi srl", "100,00"), ("b) Bianchi spa", "200,00"),
                           ("Banca c/c", "517,00"), ("Cassa", "23,00"), ("Magazzino", "71,00"))
    f = _per_etichetta(foglie_contabili(_doc(tmp_path, voci), 0))
    assert f["a) Rossi srl"].percorso_legale == "SPA.C.II.1" and f["b) Bianchi spa"].percorso_legale == "SPA.C.II.1"


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


def test_lettera_che_non_divide_la_voce_si_toglie_e_la_base_deve_valere(tmp_path):
    from importers.lettore.foglie import _Posizione, _percorso
    r = _riga_finta("x", "a) altri")
    r.sezione = "CE"
    assert _percorso(r, _Posizione(None, ("B", "7", "a"), None))[0] == "CE.B.7"          # lettera senza significato
    assert _percorso(r, _Posizione(None, ("C", "16", "b"), None))[0] == "CE.C.16"
    assert _percorso(r, _Posizione(None, ("B", "9", "a"), None))[0] == "CE.B.9.a"        # lettera che divide: resta
    assert _percorso(r, _Posizione(None, ("A", "1", "a"), None))[0] == "CE.A.1"
    r2 = _riga_finta("y", "a) x")
    assert _percorso(r2, _Posizione("A", ("C", "1", "a"), None)) == (None, None)         # la base non vale: None


# --- Task 2b (Fase 3): lato dal saldo, costi stampati col meno, due tabelle affiancate -----------------------------

def test_saldo_con_segno_decide_il_lato_senza_titoli(tmp_path):
    # 1566: colonna «Saldo», nessun titolo di lato: il dare (positivo) e' attivo, l'avere (negativo) passivo
    voci = [(50, 100, "STATO PATRIMONIALE al 30/09/2026"), (500 - 28, 120, "Saldo")]
    dati = [("Banca", "1.000,00"), ("Cassa", "50,00"), ("Fornitori", "700,00-"), ("Capitale", "350,00-"),
            ("Clienti", "200,00"), ("Riserve", "200,00-")]
    for k, (e, v) in enumerate(dati):
        voci += [(50, 140 + k * 14, e), (500, 140 + k * 14, v)]
    doc = _doc(tmp_path, voci)
    assert [c.ruolo for c in doc.colonne] == ["saldo"]
    foglie = _per_etichetta(foglie_contabili(doc, colonne_utili(doc)[0]))
    assert {foglie[e].lato_sp for e in ("Banca", "Cassa", "Clienti")} == {"A"}
    assert {foglie[e].lato_sp for e in ("Fornitori", "Capitale", "Riserve")} == {"P"}
    assert foglie["Fornitori"].importo == Decimal("700.00")


def test_saldo_senza_negativi_non_dice_il_lato(tmp_path):
    # 1561: importi assoluti (la lettera D/A e' nell'etichetta): tutto positivo non vuol dire «tutto attivo»
    voci = [(50, 100, "STATO PATRIMONIALE"), (500 - 28, 120, "Saldo")]
    for k, e in enumerate(("Banca", "Cassa", "Fornitori", "Capitale")):
        voci += [(50, 140 + k * 14, e), (500, 140 + k * 14, "1.000,00")]
    doc = _doc(tmp_path, voci)
    assert {f.lato_sp for f in foglie_contabili(doc, colonne_utili(doc)[0])} == {None}


def test_lettera_dare_avere_dopo_il_saldo_decide_il_lato(tmp_path):
    # 1561: importi assoluti, ma ogni saldo e' seguito dalla sua lettera in una colonna propria (10 pt dopo): D e'
    # attivo, A passivo, e l'importo arriva positivo sul suo lato
    voci = [(50, 100, "STATO PATRIMONIALE"), (500 - 28, 120, "Saldo")]
    dati = [("Banca", "1.000,00", "D"), ("Cassa", "50,00", "D"), ("Clienti", "200,00", "D"), ("Magazzino", "33,00", "D"),
            ("Erario", "20,00", "D"), ("Ratei", "10,00", "D"), ("Brevetti", "90,00", "D"), ("Impianti", "300,00", "D"),
            ("Fornitori", "700,00", "A"), ("Capitale", "350,00", "A"), ("Riserve", "200,00", "A"),
            ("Debiti tributari", "155,00", "A")]
    for k, (e, v, m) in enumerate(dati):
        voci += [(50, 140 + k * 14, e), (500, 140 + k * 14, v), (510, 140 + k * 14, m)]
    doc = _doc(tmp_path, voci)
    assert doc.profilo.marcatori == frozenset({0})
    foglie = _per_etichetta(foglie_contabili(doc, colonne_utili(doc)[0]))
    assert {foglie[e].lato_sp for e, _, m in dati if m == "D"} == {"A"}
    assert {foglie[e].lato_sp for e, _, m in dati if m == "A"} == {"P"}
    assert foglie["Fornitori"].importo == Decimal("700.00") and foglie["Banca"].importo == Decimal("1000.00")


def test_costi_stampati_col_meno_arrivano_positivi(tmp_path):
    # 1470: tutto il conto economico stampa i costi tra parentesi: e' la convenzione del documento (F3-1: segno normale)
    voci = [(50, 100, "CONTO ECONOMICO")]
    righe = [("A) Valore della produzione", None), ("1) Ricavi delle vendite e delle prestazioni", "9.000,00")]
    righe += [("B) Costi della produzione", None)] + [(f"7) Per servizi {k}", f"({(k + 1) * 100},00)".replace(
        "(100,00)", "(1.100,00)")) for k in range(6)]
    for k, (e, v) in enumerate(righe):
        voci.append((50, 140 + k * 14, e))
        if v:
            voci.append((480, 140 + k * 14, v))
            voci.append((560, 140 + k * 14, v))
    doc = _doc(tmp_path, voci)
    costi = [f for f in foglie_contabili(doc, colonne_utili(doc)[0]) if f.etichetta.startswith("7) Per servizi")]
    assert costi and all(f.importo > 0 for f in costi)


def test_due_tabelle_affiancate_non_hanno_l_attivo_a_sinistra(tmp_path):
    # 1426: a sinistra uno stato patrimoniale con attivo e passivo uno sotto l'altro, a destra il conto economico:
    # L non e' l'attivo e R non e' il passivo; il lato viene dai titoli come su una colonna unica
    sinistra = [("STATO PATRIMONIALE ATTIVO", "800,00"), ("B) Immobilizzazioni", "300,00"),
                ("I - Immobilizzazioni immateriali", "300,00"), ("C) Attivo circolante", "500,00"),
                ("I - Rimanenze", "500,00"), ("STATO PATRIMONIALE PASSIVO", "800,00"),
                ("A) Patrimonio netto", "600,00"), ("I - Capitale", "600,00"), ("D) Debiti", "200,00"),
                ("7) Debiti verso fornitori", "200,00")]
    destra = [("A) Valore della produzione", "900,00"), ("1) Ricavi delle vendite", "900,00"),
              ("B) Costi della produzione", "80,00"), ("6) Per materie prime", "50,00"), ("7) Per servizi", "30,00"),
              ("9) Per il personale", "10,00"), ("Differenza A - B", "820,00"), ("17) Interessi", "5,00"),
              ("20) Imposte", "3,00"), ("21) Utile dell'esercizio", "812,00")]
    voci = [(40, 100, "STATO PATRIMONIALE - Schema"), (320, 100, "CE - Schema Ridotto")]
    for k, ((a, va), (b, vb)) in enumerate(zip(sinistra, destra)):
        y = 140 + k * 14
        voci += [(40, y, a), (270, y, va), (320, y, b), (560, y, vb)]
    doc = _doc(tmp_path, voci)
    assert doc.profilo.confine is not None and not doc.contrapposto
    foglie = _per_etichetta(foglie_contabili(doc, 0))
    assert foglie["I - Immobilizzazioni immateriali"].lato_sp == "A" and foglie["I - Rimanenze"].lato_sp == "A"
    assert foglie["I - Capitale"].lato_sp == "P" and foglie["7) Debiti verso fornitori"].lato_sp == "P"
    assert foglie["6) Per materie prime"].sezione == "CE" and foglie["6) Per materie prime"].lato_sp is None


# --- Task 2b, fix round 1 ------------------------------------------------------------------------------------------

def _ce_con_costi(valori_costi, totale):
    voci = [(50, 100, "CONTO ECONOMICO"), (50, 124, "B) Costi della produzione")]
    righe = [(f"7) Per servizi {k}", v) for k, v in enumerate(valori_costi)]
    righe.append(("Totale 7) Per servizi", totale))
    for k, (e, v) in enumerate(righe):
        voci += [(50, 140 + k * 14, e), (480, 140 + k * 14, v), (560, 140 + k * 14, v)]
    return voci


def test_ancora_dei_costi_ha_il_segno_delle_sue_foglie(tmp_path):
    # 1470: costi tra parentesi; la foglia arriva positiva e l'ancora della macro-voce con lei (non -1.065.113 contro +)
    doc = _doc(tmp_path, _ce_con_costi([f"({v},00)" for v in (130, 270, 410, 570, 690, 850)], "(2.920,00)"))
    col = colonne_utili(doc)[0]
    foglie = [f for f in foglie_contabili(doc, col) if f.etichetta.startswith("7) Per servizi")]
    ancora = next(a for a in ancore(doc, col) if a.chiave.startswith("ce"))
    assert sum(f.importo for f in foglie) == ancora.importo == Decimal("2920.00")


def test_un_costo_negativo_fra_i_positivi_resta_negativo(tmp_path):
    # sotto soglia (1 su 6) non c'e' convenzione: e' uno storno e resta com'e'
    doc = _doc(tmp_path, _ce_con_costi(["130,00", "270,00", "410,00", "(50,00)", "690,00", "850,00"], "2.300,00"))
    costi = {f.etichetta: f.importo for f in foglie_contabili(doc, colonne_utili(doc)[0])
             if f.etichetta.startswith("7) Per servizi")}
    assert costi["7) Per servizi 3"] == Decimal("-50.00") and costi["7) Per servizi 0"] == Decimal("130.00")


def test_contrapposte_tipata_male_con_titoli_di_lato_tiene_i_lati(tmp_path):
    # L titolata ATTIVO, R titolata PASSIVO, profilo non contrapposto: i lati restano quelli fisici
    sinistra = [("ATTIVO", "800,00"), ("B) Immobilizzazioni", "300,00"), ("I - Immobilizzazioni immateriali", "300,00"),
                ("C) Attivo circolante", "500,00"), ("I - Rimanenze", "500,00"), ("II - Crediti", "500,00")]
    destra = [("PASSIVO", "800,00"), ("A) Patrimonio netto", "600,00"), ("I - Capitale", "600,00"),
              ("D) Debiti", "200,00"), ("7) Debiti verso fornitori", "200,00"), ("E) Ratei", "100,00")]
    voci = [(40, 100, "STATO PATRIMONIALE")]
    for k, ((a, va), (b, vb)) in enumerate(zip(sinistra, destra)):
        y = 140 + k * 14
        voci += [(40, y, a), (270, y, va), (320, y, b), (560, y, vb)]
    doc = _doc(tmp_path, voci)
    assert not doc.contrapposto       # il profilo la tipa come schema: e' il caso da proteggere
    foglie = _per_etichetta(foglie_contabili(doc, colonne_utili(doc)[0]))
    assert foglie["I - Immobilizzazioni immateriali"].lato_sp == "A"
    assert foglie["I - Rimanenze"].lato_sp == "A"
    assert foglie["I - Capitale"].lato_sp == "P"
    assert foglie["7) Debiti verso fornitori"].lato_sp == "P"


def test_lato_dal_saldo_si_dichiara_con_un_avviso(tmp_path):
    voci = [(50, 100, "STATO PATRIMONIALE al 30/09/2026"), (500 - 28, 120, "Saldo")]
    for k, (e, v) in enumerate([("Banca", "1.000,00"), ("Cassa", "50,00"), ("Fornitori", "700,00-"),
                                ("Capitale", "350,00-")]):
        voci += [(50, 140 + k * 14, e), (500, 140 + k * 14, v)]
    doc = _doc(tmp_path, voci)
    foglie_contabili(doc, colonne_utili(doc)[0])
    assert any("dal segno del saldo" in a and a.startswith("4 righe") for a in doc.tutti_gli_avvisi())


# --- Task 2c (Fase 3): voci che ripetono i propri conti, titolo di lato col suo totale ---------------------------

def _attivo_con_catena():
    """1440 in piccolo: «I.» vale 875 come il suo unico sottogruppo con importo («7) Altre», che non stampa il proprio:
    i conti stanno sotto «Costo storico»/«Fondo»), e l'altro sottogruppo somma zero: nessun totale chiude «I.»."""
    return _righe(140, [("STATO PATRIMONIALE ATTIVO", "5.000,00"), ("B) Immobilizzazioni", "875,00"),
                        ("I. Immobilizzazioni immateriali", "875,00"), ("1) Costi di impianto", ""),
                        (60, "Costo storico", "1.283,80"), (70, "Costi di impianto", "1.283,80"),
                        (60, "Fondo ammortamento", "-1.283,80"), (70, "F.amm. costi di impianto", "-1.283,80"),
                        ("7) Altre", ""), (60, "Costo storico", "3.500,00"), (70, "Migliorie su beni di terzi", "3.500,00"),
                        (60, "Fondo ammortamento", "-2.625,00"), (70, "F.amm. migliorie", "-2.625,00"),
                        ("C) Attivo circolante", "4.125,00"), (70, "Banca", "3.000,00"), (70, "Cassa", "1.125,00")])


def test_voce_di_pari_importo_sopra_i_suoi_conti_non_e_una_foglia(tmp_path):
    # 1440: senza questa regola «I.» e il titolo del lato restano foglie accanto ai conti, e l'attivo esce doppio
    doc = _doc(tmp_path, _attivo_con_catena())
    foglie = foglie_contabili(doc, 0)
    assert sorted(f.etichetta for f in foglie) == sorted(["Costi di impianto", "F.amm. costi di impianto",
                                                          "Migliorie su beni di terzi", "F.amm. migliorie", "Banca",
                                                          "Cassa"])
    assert sum(f.importo for f in foglie) == Decimal("5000.00")


def test_voce_il_cui_importo_non_e_la_somma_dei_conti_resta_foglia(tmp_path):
    # i conti sotto «I.» sommano 875, ma la voce dice 900: non e' il loro riepilogo, nessuna massa si toglie
    voci = [(x, y, "900,00" if t == "875,00" and k < 10 else t) for k, (x, y, t) in enumerate(_attivo_con_catena())]
    nomi = {f.etichetta for f in foglie_contabili(_doc(tmp_path, voci), 0)}
    assert "I. Immobilizzazioni immateriali" in nomi


def test_voci_sorelle_di_pari_importo_restano_due_foglie(tmp_path):
    # due voci dello stesso livello con lo stesso importo non sono una catena: la seconda chiude la prima
    voci = _righe(140, [("STATO PATRIMONIALE ATTIVO", ""), ("B) Immobilizzazioni", "500,00"),
                        ("C) Attivo circolante", "500,00"), ("D) Ratei e risconti", "70,00"),
                        ("E) Altre voci", "31,00"), ("F) Altre voci due", "13,00"), ("G) Altre voci tre", "7,00")])
    nomi = {f.etichetta for f in foglie_contabili(_doc(tmp_path, voci), 0)}
    assert {"B) Immobilizzazioni", "C) Attivo circolante"} <= nomi


def _due_titoli(passivo):
    return _righe(140, [("STATO PATRIMONIALE ATTIVO", "1.500,00"), ("Banca", "1.000,00"), ("Cassa", "500,00"),
                        ("STATO PATRIMONIALE PASSIVO", passivo), ("Capitale", "1.000,00"), ("Fornitori", "500,00")])


def test_titolo_di_lato_con_importo_uguale_all_altro_e_un_totale(tmp_path):
    # 1440: «STATO PATRIMONIALE ATTIVO 217.368,86» e «... PASSIVO 217.368,86» senza righe «Totale»: attivo = passivo
    doc = _doc(tmp_path, _due_titoli("1.500,00"))
    col = colonne_utili(doc)[0]
    an = {a.chiave: a.importo for a in ancore(doc, col)}
    assert an["attivo"] == Decimal("1500.00") and an["passivo"] == Decimal("1500.00")


def test_titolo_di_lato_con_importo_diverso_dall_altro_non_e_un_totale(tmp_path):
    doc = _doc(tmp_path, _due_titoli("1.200,00"))
    assert not {a.chiave for a in ancore(doc, colonne_utili(doc)[0])} & {"attivo", "passivo"}


# --- Task 2c, fix round 1 ---------------------------------------------------------------------------------------

def test_un_totale_chiuso_fra_la_voce_e_i_conti_chiude_la_finestra(tmp_path):
    # «B) Crediti vari» e' seguita da «Totale altri» (chiuso) e poi da conti di un'altra voce: la finestra dei suoi
    # conti finisce al totale
    voci = _righe(140, [("B) Crediti vari", "300,00"), ("Conto a", "120,00"), ("Conto b", "180,00"),
                        ("Totale crediti", "300,00"), ("Conto c", "100,00"), ("Conto d", "200,00")])
    doc = _doc(tmp_path, voci)
    righe = doc.righe_del_prospetto()
    pos = _scorri(righe, doc.contrapposto)
    livello = _livelli_eco(righe)
    k = next(i for i, r in enumerate(righe) if r.etichetta == "B) Crediti vari")
    t = next(i for i, r in enumerate(righe) if r.etichetta == "Totale crediti")
    assert righe[t].totale
    assert _fine_finestra(righe, pos, livello, k) == t


def test_nome_con_iniziale_romana_non_e_un_livello_di_legge(tmp_path):
    # «V. ROSSI» fra i conti di una voce arabica non e' il livello V; «I.» sotto «B)» e «II.» dopo «I.» si'
    voci = _righe(140, [("B) Immobilizzazioni", "700,00"), ("I. Immateriali", "400,00"), ("4) Crediti diversi", "350,00"),
                        ("Cliente alfa", "100,00"), ("V. ROSSI", "200,00"), ("Cliente beta", "50,00"),
                        ("II. Materiali", "300,00"), ("Impianti", "300,00")])
    doc = _doc(tmp_path, voci)
    righe = doc.righe_del_prospetto()
    livello = _livelli_eco(righe)
    per = {righe[k].etichetta: v for k, v in livello.items()}
    assert "V. ROSSI" not in per
    assert per["I. Immateriali"] == 1 and per["II. Materiali"] == 1


def test_titolo_ancora_non_e_anche_foglia(tmp_path):
    # sonda 2900 su 1500: il titolo (1500) non e' il riepilogo dei suoi conti (900 + 500) ma e' l'ancora (= passivo)
    voci = _righe(140, [("STATO PATRIMONIALE ATTIVO", "1.500,00"), ("Banca", "900,00"), ("Cassa", "500,00"),
                        ("STATO PATRIMONIALE PASSIVO", "1.500,00"), ("Capitale", "1.000,00"), ("Fornitori", "500,00")])
    doc = _doc(tmp_path, voci)
    col = colonne_utili(doc)[0]
    foglie = foglie_contabili(doc, col)
    assert "STATO PATRIMONIALE ATTIVO" not in {f.etichetta for f in foglie}
    assert sum(f.importo for f in foglie if f.lato_sp == "A") == Decimal("1400.00")
    assert {a.chiave: a.importo for a in ancore(doc, col)}["attivo"] == Decimal("1500.00")


def test_titolo_a_zero_non_e_un_ancora(tmp_path):
    voci = _righe(140, [("STATO PATRIMONIALE ATTIVO", "0,00"), ("Banca", "900,00"), ("Cassa", "500,00"),
                        ("STATO PATRIMONIALE PASSIVO", "0,00"), ("Capitale", "1.000,00"), ("Fornitori", "400,00")])
    doc = _doc(tmp_path, voci)
    assert not {a.chiave for a in ancore(doc, colonne_utili(doc)[0])} & {"attivo", "passivo"}


def test_con_un_totale_attivo_il_titolo_non_fa_da_ancora(tmp_path):
    voci = _righe(140, [("STATO PATRIMONIALE ATTIVO", "1.400,00"), ("Banca", "900,00"), ("Cassa", "500,00"),
                        ("Totale attivo", "1.400,00"), ("STATO PATRIMONIALE PASSIVO", "1.400,00"),
                        ("Capitale", "1.000,00"), ("Fornitori", "400,00"), ("Totale passivo", "1.400,00")])
    doc = _doc(tmp_path, voci)
    col = colonne_utili(doc)[0]
    ancora_attivo = [a for a in ancore(doc, col) if a.chiave == "attivo"]
    assert len(ancora_attivo) == 1
    r = next(r for r in doc.righe if r.id == ancora_attivo[0].riga)
    assert r.etichetta == "Totale attivo"
