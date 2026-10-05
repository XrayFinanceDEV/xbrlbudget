"""#62 nota S04 (M7): giorni di magazzino in due gruppi, ce02/ce03 dallo SP, avviso sui giorni espliciti."""
import pytest
from decimal import Decimal as D

from calculations.projection_common import rimanenze_gruppo_materie, rimanenze_materie
from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, righe

# Il totale sp05_rimanenze resta 287.312: la massa si sposta fra le sotto-voci, il seed resta in pareggio.
BS_PF = {"sp05a_materie_prime": D("187312"), "sp05d_prodotti_finiti": D("100000")}
BS_LC = {"sp05a_materie_prime": D("187312"), "sp05c_lavori_in_corso": D("100000")}
BS_SL = {"sp05a_materie_prime": D("187312"), "sp05b_prodotti_in_corso": D("100000")}


def test_gruppo_senza_semilavorati_coincide_con_b01():
    ca, cb = rimanenze_gruppo_materie(D("287312"), D("0"), D("135773.40"), D("25"))
    atteso, _ = rimanenze_materie(D("287312"), D("135773.40"), D("25"))
    assert abs(ca - atteso) < D("0.000001") and cb == D("0")


def test_gruppo_rispetta_i_giorni_sul_consumo():
    ca, cb = rimanenze_gruppo_materie(D("100000"), D("50000"), D("400000"), D("60"))
    consumo = D("400000") + D("100000") - ca
    assert abs((ca + cb) - consumo * D("60") / D("360")) < D("0.01")
    assert abs(ca / (ca + cb) - D("100000") / D("150000")) < D("0.0001")


def test_gruppo_senza_materie_e_tutto_semilavorati():
    ca, cb = rimanenze_gruppo_materie(D("0"), D("50000"), D("400000"), D("60"))
    assert ca == D("0") and cb > 0


def test_ambienta_25_giorni_avvisa():
    e = generato(genera(righe(dio_days=25)))
    assert any("287.312" in a for a in e.det[2027]["avvisi"])
    av = e.det[2027]["avviso_rimanenze"]
    assert av and av[0]["gruppo"] == "materie_semilavorati"


def test_senza_giorni_espliciti_nessun_avviso_e_chiave_presente():
    e = generato(genera(righe()))
    assert e.det[2027]["avviso_rimanenze"] == []
    assert "rimanenze" in e.det[2027]


def test_apertura_zero_non_fa_scattare_il_test_del_50_percento():
    # Fix finale 5: ap_d == 0 (AMBIENTA non ha prodotti finiti) e 1 giorno sui ricavi: una chiusura piccola
    # non e' «oltre il 50% dell'apertura», e il flusso (ricavi) e' lontano.
    e = generato(genera(righe(dio_pf_days=1)))
    assert e.anni[2027][0]["sp05d_prodotti_finiti"] > 0
    assert e.det[2027]["avviso_rimanenze"] == []


def test_prodotti_finiti_seguono_i_ricavi_e_passano_da_ce02():
    e = generato(genera(righe(dio_pf_days=10), bs=BS_PF))
    sp, ce = e.anni[2027]
    assert abs(sp["sp05d_prodotti_finiti"] - ce["ce01_ricavi_vendite"] * 10 / 360) < D("0.01")
    assert abs(ce["ce02_variazioni_rimanenze"] - (sp["sp05d_prodotti_finiti"] - D("100000")
               + sp["sp05b_prodotti_in_corso"])) < D("0.01")


def test_semilavorati_seguono_il_gruppo_materie_e_passano_da_ce02():
    e = generato(genera(righe(dio_days=60), bs=BS_SL))
    sp, ce = e.anni[2027]
    assert abs(ce["ce02_variazioni_rimanenze"] - (sp["sp05b_prodotti_in_corso"] - D("100000"))) < D("0.01")
    assert abs(ce["ce10_var_rimanenze_mat_prime"] - (D("187312") - sp["sp05a_materie_prime"])) < D("0.01")


def test_lavori_in_corso_non_passano_dal_ce():
    # ce03 e' ambiguo negli import (A.4 finisce spesso li'): resta quello della base, sp05c muove solo la cassa.
    e = generato(genera(righe(revenue_growth_pct=10), bs=BS_LC))
    sp, ce = e.anni[2027]
    assert sp["sp05c_lavori_in_corso"] > D("100000")
    assert ce["ce03_lavori_interni"] == BASE_CE["ce03_lavori_interni"]
    assert e.det[2027]["rimanenze"]["lavori_in_corso"]["contropartita"] == "nessuna"


def test_ce03_della_base_ambienta_si_riporta():
    e = generato(genera(righe()))
    assert BASE_CE["ce03_lavori_interni"] == D("93000.00")
    assert e.anni[2027][1]["ce03_lavori_interni"] == D("93000.00")


def test_base_senza_dettaglio_non_perde_massa():
    e = generato(genera(righe(), bs={"sp05a_materie_prime": D("0")}))
    assert abs(e.anni[2027][0]["sp05_rimanenze"] - BASE_BS["sp05_rimanenze"]) < D("1")


def test_override_ce02_vince_e_lo_sp_lo_segue():
    e = generato(genera(righe(ce02_override=-20000), bs=BS_PF))
    sp, ce = e.anni[2027]
    assert ce["ce02_variazioni_rimanenze"] == D("-20000")
    assert abs(sp["sp05d_prodotti_finiti"] - D("80000")) < D("0.01")


def test_override_ce02_sotto_zero_si_rifiuta():
    e = genera(righe(ce02_override=-150000), bs=BS_PF)
    assert e.res["forecast_generated"] is not True
    assert "ce02" in e.res["message"]
