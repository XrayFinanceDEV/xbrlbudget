"""Test unitari e di regola dei fix del lotto 1 (spec fix rilievi AMBIENTA 2026-09-26 §3)."""
from decimal import Decimal as D

from tests.rilievi_kit import BASE_CE, genera, generato, per_anno, righe


def test_B03_personale_ricomposto_quando_il_tfr_sfonda_il_totale():
    # Sulla base AMBIENTA salari/13,5 + salari + oneri supera il totale del personale:
    # il totale si ricompone come somma e lo si dichiara.
    e = generato(genera(righe()))
    ce, det = e.anni[2027][1], e.det[2027]["personale_ricomposto"]
    somma = ce["ce08a_tfr_accrual"] + ce["ce08b_salari_stipendi"] + ce["ce08c_oneri_sociali"]
    assert ce["ce08d_altri_costi_personale"] == D("0.00")
    assert ce["ce08_costi_personale"] == somma
    assert det["tfr_limitato"] is False and D(str(det["eccedenza"])) > 0


def test_B03_override_del_totale_vince_e_limita_il_tfr():
    rows = righe(ce08_override=2344742)
    e = generato(genera(rows))
    ce, det = e.anni[2027][1], e.det[2027]["personale_ricomposto"]
    assert ce["ce08_costi_personale"] == D("2344742.00")
    assert ce["ce08a_tfr_accrual"] + ce["ce08b_salari_stipendi"] + ce["ce08c_oneri_sociali"] \
        + ce["ce08d_altri_costi_personale"] == D("2344742.00")
    assert det["tfr_limitato"] is True


def test_B03_nessuna_ricomposizione_dichiarata_quando_il_totale_regge():
    # Oneri sociali azzerati: salari/13,5 + salari sta sotto il totale.
    e = generato(genera(righe(), ce={"ce08c_oneri_sociali": D("0"),
                                     "ce08d_altri_costi_personale": D("491380.40")}))
    assert e.det[2027]["personale_ricomposto"] is None
    ce = e.anni[2027][1]
    assert abs(ce["ce08a_tfr_accrual"] - ce["ce08b_salari_stipendi"] / D("13.5")) < D("0.01")
