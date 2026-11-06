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
