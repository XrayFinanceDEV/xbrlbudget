"""R07 (#63, decisione del proprietario 2026-10-09): la crescita delle materie si applica al CONSUMO
(ce05 + ce10), non agli acquisti. Acquisti = consumo + RF - RI, mai sotto zero; B11 = RI - RF."""
from decimal import Decimal as D

from tests.rilievi_kit import BASE_CE, genera, generato, per_anno, righe

Q = D("0.01")
# Caso del tester: consumo 2026 = 129.309 - 1.432 = 127.877; materie +7%.
# I servizi compensano la differenza di consumo, cosi' l'utile del CE resta quello di sp13 (base valida).
CE_T = {"ce05_materie_prime": D("129309"), "ce10_var_rimanenze_mat_prime": D("-1432"),
        "ce06_servizi": BASE_CE["ce06_servizi"] + (D("128090.89") - D("127877"))}


def _consumo(e, y):
    ce = e.anni[y][1]
    return ce["ce05_materie_prime"] + ce["ce10_var_rimanenze_mat_prime"]


def _righe(**kw):
    kw.setdefault("fixed_materials_percentage", 0)
    kw.setdefault("variable_materials_growth_pct", 7)
    return righe(**kw)


def test_accettazione_tester_consumo_cresce_del_7_per_cento_qualunque_i_giorni():
    atteso = (D("127877") * D("1.07")).quantize(Q)
    assert atteso == D("136828.39")
    for giorni in (None, 60, 360, 809):
        kw = {} if giorni is None else {"dio_days": giorni}
        e = generato(genera(_righe(**kw), ce=CE_T))
        ce = e.anni[2027][1]
        assert _consumo(e, 2027).quantize(Q) == atteso, giorni
        # B11 = RI - RF: la variazione di rimanenze del CE e' quella dello SP.
        sp = e.anni[2027][0]
        assert abs(ce["ce10_var_rimanenze_mat_prime"] - (D("287312") - sp["sp05a_materie_prime"])) < Q


def test_quota_fissa_con_la_sua_crescita_sul_consumo():
    e = generato(genera(righe(fixed_materials_percentage=40, variable_materials_growth_pct=10,
                              fixed_materials_growth_pct=0), ce=CE_T))
    atteso = D("127877") * D("0.4") + D("127877") * D("0.6") * D("1.10")
    assert abs(_consumo(e, 2027) - atteso) < Q
    d = e.det[2027]
    assert abs(D(str(d["ce05_fixed"])) + D(str(d["ce05_variable"])) - atteso) < Q


def test_clamp_acquisti_a_zero_con_avviso_e_diagnostica():
    # 25 giorni: RF = ~9.000 su un'apertura di 287.312 e un consumo di 127.877: servirebbero acquisti negativi.
    e = generato(genera(_righe(dio_days=25), ce=CE_T))
    rm = e.det[2027]["rimanenze_materie"]
    assert rm["acquisti_azzerati"] is True and rm["acquisti"] == 0
    assert e.anni[2027][1]["ce05_materie_prime"] == 0
    assert any("azzerati" in a for a in e.det[2027]["avvisi"])
    # RF = RI - consumo
    assert abs(e.anni[2027][0]["sp05a_materie_prime"] - (D("287312") - _consumo(e, 2027))) < Q


def test_ce05_override_vince_e_gli_acquisti_restano_fissati():
    e = generato(genera(_righe(dio_days=60, ce05_override=150000), ce=CE_T))
    ce = e.anni[2027][1]
    assert ce["ce05_materie_prime"] == D("150000")
    assert e.det[2027]["pareggio"]["costi_variabili"] is None


def test_ce10_override_sotto_la_giacenza_vince_e_il_consumo_resta_quello_dell_ipotesi():
    e = generato(genera(_righe(ce10_override=10000), ce=CE_T))
    ce, sp = e.anni[2027][1], e.anni[2027][0]
    assert ce["ce10_var_rimanenze_mat_prime"] == D("10000")
    assert sp["sp05a_materie_prime"] == D("277312")
    assert abs(_consumo(e, 2027) - D("127877") * D("1.07")) < Q


def test_pareggio_porta_b11_nei_costi_variabili_con_il_consumo():
    e = generato(genera(_righe(dio_days=2000), ce=CE_T))
    d = e.det[2027]
    # costi variabili = consumo variabile (B6 + B11) + servizi variabili: B11 non finisce nei fissi.
    assert abs(D(str(d["ce05_variable"])) + D(str(d["ce05_fixed"])) - _consumo(e, 2027)) < Q
    assert D(str(d["pareggio"]["costi_variabili"])) == (D(str(d["ce05_variable"])) + D(str(d["ce06_variable"]))).quantize(Q)


def test_il_consumo_prosegue_anno_su_anno():
    e = generato(genera(_righe(dio_days=2000), ce=CE_T))
    assert abs(_consumo(e, 2028) - D("127877") * D("1.07") ** 2) < Q
