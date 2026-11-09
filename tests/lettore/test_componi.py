"""Composizione quadrata (Task 4)."""
from decimal import Decimal as D

from importers.lettore.classifica import Classe
from importers.lettore.componi import componi
from importers.lettore.foglie import Ancora, Foglia


def F(id, importo, lato="L", sezione="SP", verso=None, etichetta="Voce", percorso=None, antenati=()):
    return Foglia(id, etichetta, "", lato, sezione, D(importo), percorso, antenati, verso, None)


def C(macro, dettaglio=None):
    return Classe(macro, dettaglio, "modello")


def base():
    foglie = [F("a", 1000), F("p", 900, "R"), F("r", 100, "L", "CE", "ricavo")]
    classi = {"a": C("sp06"), "p": C("sp16"), "r": C("ce01")}
    return foglie, classi


def test_contrapposte_quadra_per_costruzione():
    foglie, classi = base()
    c = componi(foglie, classi, [])
    assert c.bs["sp06_crediti_breve"] == D("1000") and c.bs["sp16_debiti_breve"] == D("900")
    assert c.sbilancio == 0 and c.blocchi == [] and c.chiusure == []
    assert c.bs["sp13_utile_perdita"] == D("100")


def test_dettaglio_non_sbilancia():
    foglie, classi = base()
    k1 = componi(foglie, {**classi, "p": C("sp16", "sp16a")}, [])
    k2 = componi(foglie, {**classi, "p": C("sp16", "sp16b")}, [])
    assert k1.bs["sp16_debiti_breve"] == k2.bs["sp16_debiti_breve"] == D("900")
    assert k1.sbilancio == k2.sbilancio == 0


def test_senza_classe_nel_secchio_del_lato():
    c = componi([F("a", 500)], {}, [])
    assert c.bs["sp06g_crediti_altri_breve"] == D("500")
    assert c.senza_classe == D("500")


def test_arrotondamento_chiuso():
    foglie, classi = base()
    foglie[1] = F("p", "899.20", "R")
    c = componi(foglie, classi, [])
    assert len(c.chiusure) == 1 and c.chiusure[0]["motivo"] == "arrotondamento"
    assert c.chiusure[0]["importo"] == D("0.80") and c.sbilancio == 0


def test_oltre_un_euro_dichiarato():
    foglie, classi = base()
    foglie[1] = F("p", "898.50", "R")
    c = componi(foglie, classi, [])
    assert c.chiusure == [] and c.sbilancio == D("1.50")


def test_ancora_che_non_torna_e_un_blocco():
    c = componi([F("a", 400)], {"a": C("sp06")}, [Ancora("sp06", D(500), "Crediti", ("a",))])
    assert "sp06" in c.blocchi and c.scarti["sp06"] == 100


def test_rimanenze_per_natura():
    foglie = [F("x", 30, "L", "CE", "ricavo", "Rimanenze finali prodotti finiti"),
              F("y", 20, "L", "CE", "costo", "Rimanenze materie prime")]
    c = componi(foglie, {"x": C("ce04"), "y": C("ce06")}, [])
    assert c.ce["ce02_variazioni_rimanenze"] == 30 and c.ce["ce10_var_rimanenze_mat_prime"] == 20


def test_risultato_cifra_di_chiusura():
    foglie, classi = base()
    foglie.append(F("u", 100, "R", etichetta="Utile d'esercizio"))
    classi["u"] = C("sp13")
    c = componi(foglie, classi, [])
    assert c.bs["sp13_utile_perdita"] == D("100") and c.sbilancio == 0


def test_solo_sp_sp13_stampato():
    foglie = [F("a", 1000), F("p", 900, "R")]
    classi = {"a": C("sp06"), "p": C("sp16")}
    c = componi(foglie, classi, [Ancora("utile", D(100), "Utile", ())])
    assert c.sp13_da == "stampato" and c.bs["sp13_utile_perdita"] == 100 and c.sbilancio == 0


def test_senza_lato_ne_verso_fuori_dai_lati():
    f = Foglia("z", "Boh", "", "U", "SP", D(70), None, (), None, None)
    g = Foglia("w", "Boh ce", "", "U", "CE", D(30), None, (), None, None)
    c = componi([f, g], {}, [])
    assert c.senza_classe == 100 and not any(v for v in c.bs.values()) and not any(v for v in c.ce.values())


def test_ce17_con_e_senza_verso():
    c = componi([F("a", 50, "L", "CE", "ricavo")], {"a": C("ce17")}, [])
    assert c.ce["ce17a_rivalutazioni"] == 50 and c.bs["sp13_utile_perdita"] == 50
    c = componi([F("b", 50, "L", "CE", None)], {"b": C("ce17")}, [])
    assert c.bs["sp13_utile_perdita"] == -50 and c.scelte


def test_perdita_e_riga_risultato_non_foglia():
    foglie = [F("c", 100, "L", "CE", "costo"), F("a", 100), F("p", 300, "R"),
              F("u", 100, "R", etichetta="Perdita d'esercizio")]
    c = componi(foglie, {"c": C("ce06"), "a": C("sp06"), "p": C("sp16")}, [])
    assert c.bs["sp13_utile_perdita"] == -100 and c.sbilancio == -100 and "pareggio" in c.blocchi


def test_fondo_positivo_negato():
    f = F("f", 40, percorso="SPA.B.II.1.F")
    c = componi([F("a", 100), f], {"a": C("sp03", "sp03a"), "f": C("sp03", "sp03a")}, [])
    assert c.bs["sp03_immob_materiali"] == 60


def test_rimanenze_segno_invertito():
    c = componi([F("x", 30, "L", "CE", "costo", "Rimanenze iniziali prodotti finiti")], {"x": C("ce12")}, [])
    assert c.ce["ce02_variazioni_rimanenze"] == -30


def test_solo_sp_utile_stampato_non_e_un_falso_blocco():
    foglie = [F("a", 1000), F("p", 900, "R")]
    c = componi(foglie, {"a": C("sp06"), "p": C("sp16")}, [Ancora("utile", D(100), "Utile", ())])
    assert c.sp13_da == "stampato" and c.scarti["utile"] == 0 and c.blocchi == []


# --- Task 9: la riga del risultato che non e' il risultato di questo periodo ----------------------------------

def test_risultato_di_un_altro_esercizio_nelle_riserve():
    # «Utile d'esercizio» 1.500 nel passivo, ma il CE del periodo da' 1.000: e' l'utile dell'esercizio prima, non
    # destinato, un conto del patrimonio netto (riserva), non la cifra di chiusura
    foglie = [F("a", 11500), F("p", 9000, "R"), F("u", 1500, "R", etichetta="Utile d'esercizio"),
              F("r", 1000, "L", "CE", "ricavo")]
    c = componi(foglie, {"a": C("sp06"), "p": C("sp16"), "u": C("sp13"), "r": C("ce01")}, [])
    assert c.bs["sp13_utile_perdita"] == 1000 and c.bs["sp12g_utili_perdite_portati"] == 1500 and c.sbilancio == 0
    assert any("u" in s for s in c.scelte)


def test_riga_utile_nuda_e_il_risultato():
    # «Utile» fra i costi, a pareggio: e' il risultato, non un costo
    foglie = [F("a", 140), F("p", 100, "R"), F("r", 100, "R", "CE", "ricavo"), F("c", 60, "L", "CE", "costo"),
              F("u", 40, "L", "CE", "costo", "Utile")]
    c = componi(foglie, {"a": C("sp06"), "p": C("sp16"), "r": C("ce01"), "c": C("ce06")}, [])
    assert c.bs["sp13_utile_perdita"] == 40 and c.sbilancio == 0 and c.senza_classe == 0


def R(macro, percorso, dettaglio=None):
    return Classe(macro, dettaglio, "modello", rettifica=percorso)


def test_fondo_sul_passivo_si_netta_sul_cespite_e_il_foglio_quadra():
    # stampato lordo: attivo 1.600 = passivo 1.600 (il fondo sta nella colonna del passivo)
    foglie = [F("i", 1000, etichetta="Impianti"), F("c", 600, etichetta="Cassa"),
              F("f", 400, "R", etichetta="Fondo amm. impianti"), F("d", 1200, "R", etichetta="Debiti")]
    classi = {"i": C("sp03"), "c": C("sp09"), "f": R("sp03", "SPA.B.II.F"), "d": C("sp16")}
    ancore = [Ancora("attivo", D(1600), "r1", ("i", "c")), Ancora("passivo", D(1600), "r2", ("f", "d"))]
    k = componi(foglie, classi, ancore)
    assert k.bs["sp03_immob_materiali"] == D(600)
    assert k.sbilancio == 0 and k.blocchi == [] and k.chiusure == []
    assert k.rettifiche == D(400)          # attivo e passivo scendono entrambi di 400
    assert k.scarti["attivo"] == 0 and k.scarti["passivo"] == 0
    assert k.senza_classe == 0


def test_perdite_portate_a_nuovo_nell_attivo_in_diminuzione_del_netto():
    foglie = [F("c", 900, etichetta="Crediti"), F("p", 100, etichetta="Perdite a nuovo"),
              F("k", 300, "R", etichetta="Capitale"), F("d", 700, "R", etichetta="Debiti")]
    classi = {"c": C("sp06"), "p": R("sp12", "SPP.A.VIII", "sp12g"), "k": C("sp11"), "d": C("sp16")}
    k = componi(foglie, classi, [Ancora("attivo", D(1000), "r1", ("c", "p"))])
    assert k.bs["sp12g_utili_perdite_portati"] == D(-100)
    assert k.sbilancio == 0 and k.rettifiche == D(100) and k.scarti["attivo"] == 0


def test_fondo_nel_dettaglio_del_bene():
    foglie = [F("i", 1000, etichetta="Impianti"), F("f", 400, "R", etichetta="Fondo amm. impianti"),
              F("d", 600, "R", etichetta="Debiti")]
    classi = {"i": C("sp03", "sp03b"), "f": R("sp03", "SPA.B.II.F", "sp03b"), "d": C("sp16")}
    k = componi(foglie, classi, [])
    assert k.bs["sp03b_impianti_macchinari"] == D(600) and k.sbilancio == 0


def test_fondo_oltre_il_cespite_azzerato_e_dichiarato_come_conti():
    # stessa regola del percorso snello: dettaglio negativo all'aggregato, aggregato negativo a zero, dichiarato
    foglie = [F("i", 300, etichetta="Impianti"), F("c", 700, etichetta="Cassa"),
              F("f", 500, "R", etichetta="Fondo amm. impianti"), F("d", 500, "R", etichetta="Debiti")]
    classi = {"i": C("sp03", "sp03b"), "c": C("sp09"), "f": R("sp03", "SPA.B.II.F", "sp03b"), "d": C("sp16")}
    k = componi(foglie, classi, [])
    assert k.bs["sp03_immob_materiali"] == 0 and "sp03b_impianti_macchinari" not in k.bs
    assert k.tagliate == [["sp03_immob_materiali", "200.00"]]
    assert k.sbilancio == D(200)       # l'eccedenza tagliata resta sbilancio dichiarato, mai spostata
    assert "pareggio" in k.blocchi


def test_dettaglio_non_kpi_tenuto():
    foglie = [F("a", 300, etichetta="Erario c/IVA"), F("b", 700, etichetta="Clienti"), F("p", 1000, "R")]
    k = componi(foglie, {"a": C("sp06", "sp06e"), "b": C("sp06", "sp06a"), "p": C("sp16")}, [])
    assert k.bs["sp06e_crediti_tributari_breve"] == D(300) and k.bs["sp06_crediti_breve"] == D(1000)
    assert k.sbilancio == 0
