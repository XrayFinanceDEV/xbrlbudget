"""Rilievi AMBIENTA #61/#62: regole del motore, una sezione per rilievo."""
from decimal import Decimal as D
from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, righe


def _q(x): return D(str(x)).quantize(D("0.01"))


def test_M3_cinque_per_cento_dell_utile_a_riserva_legale():
    e = generato(genera(righe()))
    utile_base = BASE_BS["sp13_utile_perdita"]
    sp = e.anni[2027][0]
    attesa = min(utile_base * D("0.05"), D("0.20") * BASE_BS["sp11_capitale"] - BASE_BS["sp12c_riserva_legale"])
    assert _q(sp["sp12c_riserva_legale"]) == _q(BASE_BS["sp12c_riserva_legale"] + max(D(0), attesa))
    det = e.det[2027]["riserva_legale"]
    assert _q(det["quota"]) == _q(max(D(0), attesa))
    # il totale delle riserve non cambia: la quota esce da sp12g
    assert _q(sp["sp12_riserve"]) == _q(BASE_BS["sp12_riserve"] + utile_base)


def test_M3_tetto_al_venti_per_cento_del_capitale():
    e = generato(genera(righe(), bs={
        "sp12c_riserva_legale": D("21990.00"),
        # base coerente: l'aumento di sp12c esce da sp12e, l'aggregato sp12 non cambia
        "sp12e_altre_riserve": BASE_BS["sp12e_altre_riserve"] - D("18483.60"),
    }))
    sp = e.anni[2027][0]
    assert _q(sp["sp12c_riserva_legale"]) <= D("22000.00")
    assert e.det[2027]["riserva_legale"]["raggiunto"] is True


def test_M3_perdita_non_accantona():
    e = generato(genera(righe(), 
        bs={"sp13_utile_perdita": D("-5000.00"),
            # base coerente: la perdita (-29.131,11 sull'utile) e' compensata dalle riserve, il CE la rispecchia
            "sp12_riserve": BASE_BS["sp12_riserve"] + D("29131.11"),
            "sp12e_altre_riserve": BASE_BS["sp12e_altre_riserve"] + D("29131.11")},
        ce={"ce20_imposte": BASE_CE["ce20_imposte"] + D("29131.11")}))
    sp = e.anni[2027][0]
    assert _q(sp["sp12c_riserva_legale"]) == _q(BASE_BS["sp12c_riserva_legale"])
    assert _q(e.det[2027]["riserva_legale"]["quota"]) == D("0.00")


def test_M2_ce08d_cresce_col_personale_e_il_totale_e_la_somma():
    rows = righe(personnel_growth_pct=4)
    e = generato(genera(rows))
    ce_base = BASE_CE
    for i, y in enumerate((2027, 2028, 2029), start=1):
        ce = e.anni[y][1]
        atteso_d = ce_base["ce08d_altri_costi_personale"] * D("1.04") ** i
        assert abs(ce["ce08d_altri_costi_personale"] - atteso_d) <= D("0.05")
        somma = sum(ce[k] for k in ("ce08a_tfr_accrual", "ce08b_salari_stipendi",
                                    "ce08c_oneri_sociali", "ce08d_altri_costi_personale"))
        assert _q(ce["ce08_costi_personale"]) == _q(somma)
        assert _q(ce["ce08a_tfr_accrual"]) == _q(ce["ce08b_salari_stipendi"] / D("13.5"))
    assert e.det[2027]["personale"]["modo"] == "componenti"
    assert e.det[2027]["personale_ricomposto"] is None


def test_M2_senza_dettaglio_resta_la_regola_aggregata():
    zero = {k: D("0") for k in ("ce08a_tfr_accrual", "ce08b_salari_stipendi",
                                 "ce08c_oneri_sociali", "ce08d_altri_costi_personale")}
    e = generato(genera(righe(personnel_growth_pct=4), ce=zero))
    assert e.det[2027]["personale"]["modo"] == "aggregato"
    assert _q(e.anni[2027][1]["ce08_costi_personale"]) >= _q(BASE_CE["ce08_costi_personale"] * D("1.04"))
