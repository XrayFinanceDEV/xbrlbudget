"""Rilievi AMBIENTA #61/#62: regole del motore, una sezione per rilievo."""
from decimal import Decimal as D
from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, per_anno, righe


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


def test_M1_dso_del_report_uguale_all_input_senza_piano():
    rows = righe(dso_days=90)
    e = generato(genera(rows, report=True))
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        dso = (sp["sp06a_crediti_clienti_breve"] + sp["sp07a_crediti_clienti_lungo"]) / ce["ce01_ricavi_vendite"] * 360
        assert abs(dso - D("90")) < D("0.05")


def test_M1_altri_crediti_restano_costanti():
    e = generato(genera(righe(dso_days=90, revenue_growth_pct=10)))
    # tolleranza di un centesimo: sp06g e' il primo campo neutro del centesimo di quadratura
    for y in (2027, 2029):
        for k in ("sp06b_crediti_controllate_breve", "sp06c_crediti_collegate_breve",
                  "sp06d_crediti_controllanti_breve", "sp06g_crediti_altri_breve"):
            assert abs(e.anni[y][0].get(k, D(0)) - BASE_BS.get(k, D(0))) <= D("0.01")


def test_M1_dso_derivato_a_crescita_zero_non_muove_i_clienti():
    e = generato(genera(righe()))
    sp = e.anni[2027][0]
    assert abs(sp["sp06a_crediti_clienti_breve"] + sp["sp07a_crediti_clienti_lungo"]
               - BASE_BS["sp06a_crediti_clienti_breve"] - BASE_BS["sp07a_crediti_clienti_lungo"]) < D("1")


def test_M1_base_senza_dettaglio_ripiega_sull_aggregato():
    # tutti i dettagli di sp06/sp07 a zero, gli aggregati restano: la base non ha dettaglio commerciale
    piatto = {k: D("0") for k in ("sp06a_crediti_clienti_breve", "sp06e_crediti_tributari_breve",
                                    "sp06g_crediti_altri_breve", "sp07a_crediti_clienti_lungo",
                                    "sp07e_crediti_tributari_lungo")}
    commerciale = BASE_BS["sp06_crediti_breve"]
    e = generato(genera(righe(), bs=piatto))
    sp = e.anni[2027][0]
    assert sp["sp06a_crediti_clienti_breve"] > D("0")
    assert abs(sp["sp06a_crediti_clienti_breve"] - commerciale) < D("1")
    assert sp["sp06g_crediti_altri_breve"] == D("0")


def test_M1_dso_clienti_dichiarato_e_sp07a_allineato():
    e = generato(genera(righe(dso_days=90, revenue_growth_pct=10)))
    for y in (2027, 2028, 2029):
        d = e.det[y]["dso_clienti"]
        sp = e.anni[y][0]
        assert abs(d["sp07a"] - sp["sp07a_crediti_clienti_lungo"]) <= D("0.01")
        assert abs(d["sp06a"] - sp["sp06a_crediti_clienti_breve"]) <= D("0.01")


def test_M1_con_piano_crediti_commerciali_il_foglio_pareggia_e_il_trade_e_dichiarato():
    massa = (BASE_BS["sp06a_crediti_clienti_breve"] + BASE_BS["sp06g_crediti_altri_breve"]
             + BASE_BS["sp07a_crediti_clienti_lungo"])
    rows = righe()
    meta = massa / 2
    rows[0]["pregresso"] = {"crediti_commerciali": {
        "opening": float(massa), "amounts": [float(meta), float(massa - meta)], "writeoff": [0, 0]}}
    e = generato(genera(rows))
    for y in (2027, 2028):
        sp = e.anni[y][0]
        trade = sum(sp.get(k, D(0)) for k in (
            "sp06a_crediti_clienti_breve", "sp06b_crediti_controllate_breve",
            "sp06c_crediti_collegate_breve", "sp06d_crediti_controllanti_breve",
            "sp06g_crediti_altri_breve"))
        resto = sp["sp06e_crediti_tributari_breve"] + sp.get("sp06f_imposte_anticipate_breve", D(0))
        assert abs(sp["sp06_crediti_breve"] - trade - resto) <= D("0.01")
        att = sum(v for k, v in sp.items() if k in ("sp01_crediti_soci",) or k.startswith(("sp02_", "sp03_", "sp04_", "sp05_", "sp06_", "sp07_", "sp08_", "sp09_", "sp10_")))
        pas = sum(v for k, v in sp.items() if k.startswith(("sp11_", "sp12_", "sp13_", "sp14_", "sp15_", "sp16_", "sp17_", "sp18_")))
        assert abs(att - pas) <= D("0.02")


def test_M5_acconti_sotto_entrambi_i_minimi_avvisano():
    rows = righe(tax_advances_paid=1)  # 1 € esplicito: sotto qualunque imposta positiva
    e = generato(genera(rows))
    av = e.det[2028]["imposte"]["avviso_acconti"]
    assert av is not None and av["acconti"] == D("1")
    assert any("acconti" in a.lower() for a in e.det[2028]["avvisi"])


def test_M5_acconti_non_dichiarati_non_avvisano():
    e = generato(genera(righe()))
    assert all(e.det[y]["imposte"]["avviso_acconti"] is None for y in (2027, 2028, 2029))


# ── M4 (#62 S14/S18): compensazione del credito tributario del consuntivo, a scelta ──
def _netto_scoperto(sp):
    return sp["sp09_disponibilita_liquide"] - sp["sp16a_debiti_banche_breve"]


def test_M4_casella_spenta_identica_a_prima():
    a = generato(genera(righe()))
    b = generato(genera(per_anno(righe(), "compensa_crediti_tributari", [False, False, False])))
    assert a.anni == b.anni


def test_M4_casella_accesa_consuma_il_credito_e_libera_cassa():
    a = generato(genera(righe()))
    b = generato(genera(per_anno(righe(), "compensa_crediti_tributari", [True, True, True])))
    comp = b.det[2027]["imposte"]["credito_storico_compensato"]
    assert comp > D("0")
    assert _q(a.anni[2027][0]["sp06e_crediti_tributari_breve"] - b.anni[2027][0]["sp06e_crediti_tributari_breve"]) == _q(comp)
    assert _q(_netto_scoperto(b.anni[2027][0]) - _netto_scoperto(a.anni[2027][0])) >= _q(comp) - D("0.01")
    assert _q(a.anni[2027][0]["sp16e_debiti_tributari_breve"]) == _q(b.anni[2027][0]["sp16e_debiti_tributari_breve"])
    # l'anno dopo riparte dal residuo gia' compensato
    c2 = b.det[2028]["imposte"]
    assert c2["credito_storico_compensato_cumulato"] == comp + c2["credito_storico_compensato"]


def test_M4_via_manuale_la_dichiara_ignorata():
    rows = per_anno(righe(sp16e_growth_pct=0), "compensa_crediti_tributari", [True, True, True])
    e = generato(genera(rows))
    assert e.det[2027]["imposte"]["compensazione_ignorata"] is True
    assert e.det[2027]["imposte"]["credito_storico_compensato"] == D("0")


def test_M4_si_legge_sulla_prima_riga():
    uno = generato(genera(per_anno(righe(), "compensa_crediti_tributari", [True, True, True])))
    misto = generato(genera(per_anno(righe(), "compensa_crediti_tributari", [True, False, False])))
    assert uno.anni == misto.anni


def test_M4_col_piano_dei_crediti_la_compensazione_non_si_perde():
    rows = righe()
    rows[0]["pregresso"] = {"crediti_tributari_breve": {"opening": D("184140.58"), "amounts": [D("10000"), D("0"), D("0")]}}
    rows = per_anno(rows, "compensa_crediti_tributari", [True, True, True])
    e = generato(genera(rows))
    cum = [e.det[y]["imposte"]["credito_storico_compensato_cumulato"] for y in (2027, 2028, 2029)]
    assert cum[0] > D("0") and cum == sorted(cum)
    # il residuo non e' piu' quello del solo piano: la compensazione dell'anno prima non si perde
    assert e.det[2027]["imposte"]["crediti_tributari_consuntivo"] == (
        D("184140.58") - D("10000") - cum[0])
    for y in (2027, 2028, 2029):
        assert e.det[y]["imposte"]["crediti_tributari_consuntivo"] >= D("0")
