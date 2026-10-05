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
