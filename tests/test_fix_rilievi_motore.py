"""Test unitari e di regola dei fix del lotto 1 (spec fix rilievi AMBIENTA 2026-09-26 §3)."""
from decimal import Decimal as D

from calculations.projection_common import ammortamento_categoria
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


def test_ammortamento_esistente_si_ferma_al_residuo():
    q, s = ammortamento_categoria(None, D("100"), D("60"), D("0"), D("0.1"), 2027, None)
    assert q == D("60") and s["esistente_residuo"] == D("40")
    q, s = ammortamento_categoria(s, D("40"), D("60"), D("0"), D("0.1"), 2028, None)
    assert q == D("40") and s["esistente_residuo"] == D("0")


def test_nuovo_cespite_a_meta_aliquota_nell_anno_d_ingresso():
    q, s = ammortamento_categoria(None, D("0"), D("0"), D("1000"), D("0.1"), 2027, None)
    assert q == D("50")
    q, s = ammortamento_categoria(s, D("950"), D("0"), D("0"), D("0.2"), 2028, None)
    assert q == D("100")  # aliquota del suo anno d'ingresso (10%), piena


def test_override_consuma_prima_l_esistente():
    q, s = ammortamento_categoria(None, D("100"), D("60"), D("1000"), D("0.1"), 2027, D("130"))
    assert q == D("130") and s["override"] is True
    assert s["esistente_residuo"] == D("0") and s["cespiti_nuovi"][0]["residuo"] == D("970")


def test_quota_limitata_al_netto_disponibile():
    stato = {"esistente_residuo": D("100"), "cespiti_nuovi": []}
    q, s = ammortamento_categoria(stato, D("30"), D("60"), D("0"), D("0.1"), 2028, None)
    assert q == D("30") and s["limitato_al_netto"] is True


def test_dismissione_consuma_prima_l_esistente_poi_i_nuovi_in_ordine_mai_sotto_zero():
    # Due cespiti nuovi gia' aperti, aliquota zero cosi' la quota dell'anno resta a zero e la
    # dismissione e' l'unica cosa che tocca i residui: piu' facile isolarne l'ordine.
    stato = {
        "esistente_residuo": D("50"),
        "cespiti_nuovi": [
            {"anno": 2020, "importo": D("1000"), "aliquota": D("0"), "residuo": D("80")},
            {"anno": 2021, "importo": D("1000"), "aliquota": D("0"), "residuo": D("80")},
        ],
    }
    # 100 di dismissione: i primi 50 svuotano l'esistente, i 50 restanti vanno sul PRIMO
    # cespite nuovo (ordine d'ingresso); il secondo cespite resta intatto.
    q, s = ammortamento_categoria(stato, D("300"), D("0"), D("0"), D("0.1"), 2028, None,
                                   dismissione=D("100"))
    assert q == D("0")
    assert s["esistente_residuo"] == D("0")
    assert s["cespiti_nuovi"][0]["residuo"] == D("30")
    assert s["cespiti_nuovi"][1]["residuo"] == D("80")


def test_dismissione_oltre_il_disponibile_si_ferma_a_zero_mai_sotto():
    stato = {
        "esistente_residuo": D("50"),
        "cespiti_nuovi": [
            {"anno": 2020, "importo": D("1000"), "aliquota": D("0"), "residuo": D("80")},
            {"anno": 2021, "importo": D("1000"), "aliquota": D("0"), "residuo": D("80")},
        ],
    }
    # Una dismissione ben oltre il totale disponibile (50 + 80 + 80 = 210) azzera tutto, senza
    # mai andare sotto zero.
    q, s = ammortamento_categoria(stato, D("300"), D("0"), D("0"), D("0.1"), 2028, None,
                                   dismissione=D("1000000"))
    assert s["esistente_residuo"] == D("0")
    assert s["cespiti_nuovi"][0]["residuo"] == D("0")
    assert s["cespiti_nuovi"][1]["residuo"] == D("0")


def test_E05_metà_aliquota_e_B02_sul_motore():
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 100000
    e = generato(genera(rows))
    assert e.anni[2027][1]["ce09b_ammort_materiali"] == D("36040.00") + D("5000.00")
    assert e.det[2027]["ammortamenti"]["materiali"]["quota_nuovi"] == D("5000")


def test_base_senza_quote_dettagliate_non_ammortizza_l_esistente():
    # Base abbreviata: ammortamenti solo nell'aggregato ce09. Nessuna quota esistente da portare
    # (come oggi), nessuna divisione per zero.
    e = generato(genera(righe(), ce={"ce09a_ammort_immateriali": D("0"), "ce09b_ammort_materiali": D("0"),
                                     "ce09d_svalutazione_crediti": D("75264.00")}))
    assert e.anni[2027][1]["ce09b_ammort_materiali"] == D("0.00")


def test_override_sp03_l_anno_prima_limita_la_quota():
    rows = righe(depreciation_rate=10)
    rows[0]["sp_overrides"] = {"sp03_immob_materiali": 1000}
    e = generato(genera(rows))
    assert e.anni[2028][1]["ce09b_ammort_materiali"] <= D("1000.00")


def test_asset_disposal_nbv_tocca_solo_i_residui_materiali():
    # Investimento sia materiale che immateriale nel 2027, con una dismissione (asset_disposal_nbv,
    # SOLO materiali) di 50.000: sopra il residuo esistente materiali post-quota (36.756,59), quindi
    # trabocca sul nuovo cespite materiale nell'ordine (esistente prima, poi il nuovo). La quota
    # dell'anno (ce09b) NON cambia: la dismissione tocca lo stato, non il conto economico. Il
    # secchio immateriali resta del tutto intatto: nessuna dismissione lo riguarda.
    rows = righe(depreciation_rate=10)
    rows[0]["tangible_investments"] = 100000
    rows[0]["intangible_investments"] = 50000
    rows[0]["asset_disposal_nbv"] = 50000
    e = generato(genera(rows))
    assert e.anni[2027][1]["ce09b_ammort_materiali"] == D("41040.00")  # invariata dalla dismissione
    materiali = e.det[2027]["ammortamenti"]["materiali"]
    assert materiali["esistente_residuo"] == D("0.00")
    assert materiali["cespiti_nuovi"][0]["residuo"] == D("81756.59")
    immateriali = e.det[2027]["ammortamenti"]["immateriali"]
    assert immateriali["esistente_residuo"] == D("302468.85")
    assert immateriali["cespiti_nuovi"][0]["residuo"] == D("45000")
