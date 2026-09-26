"""Test unitari e di regola dei fix del lotto 1 (spec fix rilievi AMBIENTA 2026-09-26 §3)."""
from decimal import Decimal as D

from calculations.forecast_engine import _consuma_in_ordine
from calculations.projection_common import ammortamento_categoria, rata_anno_dopo, rimanenze_materie
from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, righe
from tests.test_forecast_altri_finanziatori import _genera as _genera_altri_finanziatori
from tests.test_forecast_altri_finanziatori import _rows as _rows_altri_finanziatori
from tests.test_rilievi_ambienta import MUTUO_A, _banche


def test_consuma_in_ordine_toglie_prima_dalla_prima_voce():
    assert _consuma_in_ordine(D("44"), [D("35"), D("0"), D("0"), D("0"), D("10")]) == \
        [D("34"), D("0"), D("0"), D("0"), D("10")]
    assert _consuma_in_ordine(D("5"), [D("35"), D("0"), D("0"), D("0"), D("10")]) == \
        [D("0"), D("0"), D("0"), D("0"), D("5")]


def test_consuma_in_ordine_crescita_proporzionale():
    assert _consuma_in_ordine(D("90"), [D("30"), D("0"), D("0"), D("0"), D("15")]) == \
        [D("60"), D("0"), D("0"), D("0"), D("30")]
    assert _consuma_in_ordine(D("7"), [D("0")] * 5) == [D("7"), D("0"), D("0"), D("0"), D("0")]


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
    # lotto 1 fix rilievi (2026-09-26): un pool (100) sopra il netto persistito (30) e' ESATTAMENTE
    # lo scenario che I1 riallinea PRIMA della quota, non piu' quello che il tetto limita dopo — un
    # `sp_overrides` al ribasso su sp02/sp03 non lascia piu' un pool fantasma. Il riallineamento
    # (-70) porta l'esistente a 30, la quota si ferma li' da sola: `limitato_al_netto` resta False
    # perche' non c'e' piu' nulla da limitare. Il tetto sulla stessa annata lo prova invece
    # `test_I1_max_disponibile_include_la_dismissione_dell_anno`, con una dismissione dell'anno.
    stato = {"esistente_residuo": D("100"), "cespiti_nuovi": []}
    q, s = ammortamento_categoria(stato, D("30"), D("60"), D("0"), D("0.1"), 2028, None)
    assert q == D("30") and s["limitato_al_netto"] is False
    assert s["riallineato_al_netto"] == D("-70")


def test_dismissione_consuma_prima_l_esistente_poi_i_nuovi_in_ordine_mai_sotto_zero():
    # Due cespiti nuovi gia' aperti, aliquota zero cosi' la quota dell'anno resta a zero e la
    # dismissione e' l'unica cosa che tocca i residui: piu' facile isolarne l'ordine.
    # lotto 1 fix rilievi (2026-09-26): il netto persistito (210) ora deve combaciare col totale dei
    # pool (50+80+80=210), altrimenti I1 riallinea PRIMA della dismissione e sposta l'esistente —
    # qui si isola il solo comportamento della dismissione, non il riallineamento.
    stato = {
        "esistente_residuo": D("50"),
        "cespiti_nuovi": [
            {"anno": 2020, "importo": D("1000"), "aliquota": D("0"), "residuo": D("80")},
            {"anno": 2021, "importo": D("1000"), "aliquota": D("0"), "residuo": D("80")},
        ],
    }
    # 100 di dismissione: i primi 50 svuotano l'esistente, i 50 restanti vanno sul PRIMO
    # cespite nuovo (ordine d'ingresso); il secondo cespite resta intatto.
    q, s = ammortamento_categoria(stato, D("210"), D("0"), D("0"), D("0.1"), 2028, None,
                                   dismissione=D("100"))
    assert q == D("0")
    assert s["riallineato_al_netto"] == D("0")
    assert s["esistente_residuo"] == D("0")
    assert s["cespiti_nuovi"][0]["residuo"] == D("30")
    assert s["cespiti_nuovi"][1]["residuo"] == D("80")


def test_dismissione_oltre_il_disponibile_si_ferma_a_zero_mai_sotto():
    # lotto 1 fix rilievi (2026-09-26): netto persistito allineato al totale dei pool (210), stesso
    # motivo del test precedente.
    stato = {
        "esistente_residuo": D("50"),
        "cespiti_nuovi": [
            {"anno": 2020, "importo": D("1000"), "aliquota": D("0"), "residuo": D("80")},
            {"anno": 2021, "importo": D("1000"), "aliquota": D("0"), "residuo": D("80")},
        ],
    }
    # Una dismissione ben oltre il totale disponibile (50 + 80 + 80 = 210) azzera tutto, senza
    # mai andare sotto zero.
    q, s = ammortamento_categoria(stato, D("210"), D("0"), D("0"), D("0.1"), 2028, None,
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


def test_E05_override_degli_straordinari_vince():
    e = generato(genera(righe(ce18_override=500, ce19_override=200)))
    ce = e.anni[2027][1]
    assert (ce["ce18_proventi_straordinari"], ce["ce19_oneri_straordinari"]) == (D("500.00"), D("200.00"))


def test_rimanenze_materie_forma_chiusa():
    chiusura, ce10 = rimanenze_materie(D("100"), D("260"), D("36"))
    assert chiusura == D("360") * D("36") / D("396")
    consumo = D("260") + D("100") - chiusura
    assert abs(chiusura - consumo * D("36") / D("360")) < D("0.0000001")
    assert ce10 == D("100") - chiusura


def test_rimanenze_materie_mai_negative():
    assert rimanenze_materie(D("0"), D("-10"), D("30")) == (D("0"), D("0"))


def test_B01_dio_esplicito_sul_consumo_e_ce10_coerente():
    e = generato(genera(righe(dio_days=22)))
    sp, ce = e.anni[2027]
    r = e.det[2027]["rimanenze_materie"]
    assert r["derivati"] is False and D(str(r["giorni"])) == D("22")
    assert ce["ce10_var_rimanenze_mat_prime"] == D("287312.00") - sp["sp05a_materie_prime"]


def test_B01_giorni_degeneri_riportano_lo_stock():
    # AMBIENTA: 287.312 di materie su un consumo di 128.090,89 = oltre 800 giorni ⇒ degenere.
    e = generato(genera(righe()))
    assert e.anni[2027][0]["sp05a_materie_prime"] == D("287312.00")
    assert e.anni[2027][1]["ce10_var_rimanenze_mat_prime"] == D("0.00")
    assert e.det[2027]["rimanenze_materie"]["degenere"] is True


def test_B01_override_ce10_muove_lo_sp():
    e = generato(genera(righe(ce10_override=12312)))
    assert e.anni[2027][0]["sp05a_materie_prime"] == D("275000.00")


def test_B01_override_ce10_maggiore_dell_apertura_si_rifiuta():
    # AMBIENTA: apertura materie 287.312. Un override di 300.000 svuoterebbe le
    # rimanenze sotto zero (CE e SP divergerebbero dell'eccedenza): si rifiuta.
    e = genera(righe(ce10_override=300000))
    assert e.res["forecast_generated"] is False
    assert "300.000,00" in e.res["message"], e.res["message"]
    assert "287.312,00" in e.res["message"], e.res["message"]


def test_B01_override_ce10_uguale_all_apertura_e_accettato():
    # Solo il primo anno: l'anno dopo apre da sp05a = 0 (l'anno prima l'ha svuotata), e lo
    # stesso override varrebbe di nuovo "oltre l'apertura" — non e' il caso di questo test.
    rows = righe()
    rows[0]["ce10_override"] = 287312
    e = generato(genera(rows))
    sp, ce = e.anni[2027]
    assert sp["sp05a_materie_prime"] == D("0.00")
    assert ce["ce10_var_rimanenze_mat_prime"] == D("287312.00")
    # L'override vince: i giorni dedotti non sono mai stati usati, quindi non
    # si dichiara una degenerazione che non ha determinato nulla.
    assert e.det[2027]["rimanenze_materie"]["degenere"] is False


def test_B01_base_senza_sotto_voci_usa_l_aggregato_come_materie():
    e = generato(genera(righe(dio_days=22), bs={"sp05a_materie_prime": D("0")}))
    sp, ce = e.anni[2027]
    assert ce["ce10_var_rimanenze_mat_prime"] == D("287312.00") - sp["sp05_rimanenze"]


MUTUO = {"year": 2027, "opening_residual": D("1000"), "rate": D("0"), "repayments": [D("100"), D("100"), D("100")]}


def test_rata_anno_dopo_ripete_l_ultima_solo_nell_ultimo_anno():
    assert rata_anno_dopo(MUTUO, 2029, ultimo_anno_piano=2029) == (D("100"), True)
    assert rata_anno_dopo(MUTUO, 2028, ultimo_anno_piano=2029) == (D("100"), False)
    assert rata_anno_dopo(MUTUO, 2029) == (D("0"), False)


def test_rata_anno_dopo_zero_scadenziato_vince():
    m = {**MUTUO, "repayments": [D("100"), D("100"), D("100"), D("0")]}
    assert rata_anno_dopo(m, 2029, ultimo_anno_piano=2029) == (D("0"), False)


def test_rata_anno_dopo_mai_oltre_il_residuo():
    m = {**MUTUO, "opening_residual": D("350")}
    assert rata_anno_dopo(m, 2029, ultimo_anno_piano=2029) == (D("50"), True)


def test_B05_motore_rata_ultimo_anno_ripetuta_sta_a_breve():
    # B05 · stesso scenario di test_B05_rata_oltre_orizzonte_non_scadenziata_sta_a_breve
    # (tests/test_rilievi_ambienta.py): il piano del Finanziamento A scadenzia solo
    # 2027-2029 (3 rate), quindi il calendario del contratto non copre il 2030 e a fine
    # 2029 (ultimo anno di piano) resta un residuo. Oracolo: il contratto dichiara la
    # rata dell'ultimo anno ripetuta e la porta a breve (53.409).
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    rows[0]["financing_loans"][0]["repayments"] = [53409, 53409, 53409]
    e = generato(genera(rows))
    contratti = e.det[2029]["debito_bancario"]["contratti"]
    assert len(contratti) == 1, contratti
    assert contratti[0]["rata_ripetuta"] is True
    assert contratti[0]["breve"] == D("53409")


def test_B05_motore_anno_non_ultimo_rata_non_ripetuta():
    # Stesso scenario, ma il 2028 non è l'ultimo anno di piano: la lista di rimborsi
    # copre ancora il 2029 (elapsed 2 < len 3), quindi nessuna ripetizione.
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    rows = righe()
    rows[0].update(_banche(300000, float(banche - D("300000"))))
    rows[0]["financing_loans"][0]["repayments"] = [53409, 53409, 53409]
    e = generato(genera(rows))
    contratti = e.det[2028]["debito_bancario"]["contratti"]
    assert len(contratti) == 1, contratti
    assert contratti[0]["rata_ripetuta"] is False


def test_B05_rata_ripetuta_dichiarata_anche_su_altri_finanziatori():
    # Controller ruling del Task 6: la stessa regola B05 si applica ai contratti
    # `other_lenders`, e la chiave diagnostica va dichiarata anche lì (una chiave
    # diagnostica si dichiara sempre — CLAUDE.md). Scenario di
    # tests/test_forecast_altri_finanziatori.py::test_rimborsi_per_anno_e_quota_a_breve:
    # il contratto soci [0, 50000, 0] non copre il 2030, ultimo anno di piano il 2029.
    _, _, det, _ = _genera_altri_finanziatori("soci-rata-ripetuta", _rows_altri_finanziatori())
    assert det[2027]["altri_finanziatori"]["contratti"][0]["rata_ripetuta"] is False
    assert det[2028]["altri_finanziatori"]["contratti"][0]["rata_ripetuta"] is False
    assert det[2029]["altri_finanziatori"]["contratti"][0]["rata_ripetuta"] is True


# ── I1 (revisione finale, 2026-09-26): i pool degli ammortamenti si riallineano al netto
# persistito a inizio d'anno, cosi' un `sp_overrides` su sp02/sp03 non lascia un pool
# fantasma che ignora la modifica. ──

def test_I1_riallineamento_zero_dichiarato_al_primo_anno():
    q, s = ammortamento_categoria(None, D("100"), D("60"), D("0"), D("0.1"), 2027, None)
    assert s["riallineato_al_netto"] == D("0")


def test_I1_pool_eccedente_si_riduce_come_dismissione_esistente_poi_nuovi():
    # Pool totale 40+80=120 contro un netto persistito di 50 (es. un sp_overrides al
    # ribasso su sp03): l'eccesso 70 si toglie prima dall'esistente (40 -> 0), poi dal
    # cespite nuovo (80 -> 50). Aliquote a zero per isolare il riallineamento dalla quota
    # dell'anno.
    stato = {
        "esistente_residuo": D("40"),
        "cespiti_nuovi": [
            {"anno": 2020, "importo": D("100"), "aliquota": D("0"), "residuo": D("80")},
        ],
    }
    q, s = ammortamento_categoria(stato, D("50"), D("0"), D("0"), D("0.1"), 2028, None)
    assert s["riallineato_al_netto"] == D("-70")
    assert s["esistente_residuo"] == D("0")
    assert s["cespiti_nuovi"][0]["residuo"] == D("50")
    assert q == D("0")


def test_I1_pool_insufficiente_si_aggiunge_all_esistente():
    # Pool 10 contro un netto persistito di 100 (es. un sp_overrides al rialzo su sp03):
    # la differenza 90 si aggiunge al pool esistente, che torna ad ammortizzarsi a quota
    # base invece di restare fermo al proprio residuo originale.
    stato = {"esistente_residuo": D("10"), "cespiti_nuovi": []}
    q, s = ammortamento_categoria(stato, D("100"), D("60"), D("0"), D("0.1"), 2028, None)
    assert s["riallineato_al_netto"] == D("90")
    assert q == D("60")
    assert s["esistente_residuo"] == D("40")


def test_I1_max_disponibile_include_la_dismissione_dell_anno():
    # Pool e netto persistito coincidono (nessun riallineamento): una dismissione di 30
    # dell'anno abbassa il tetto ammortizzabile a 100+0-30=70, sotto la quota_base 90.
    stato = {"esistente_residuo": D("100"), "cespiti_nuovi": []}
    q, s = ammortamento_categoria(stato, D("100"), D("90"), D("0"), D("0.1"), 2028, None,
                                   dismissione=D("30"))
    assert s["riallineato_al_netto"] == D("0")
    assert s["limitato_al_netto"] is True
    assert q == D("70")
    assert s["esistente_residuo"] == D("0")  # 100 - 70(preso) - 30(dismissione) = 0


def test_I1_sonda_ambienta_override_sp03_poi_investimento_riallinea_il_pool():
    # Sonda della revisione finale: override sp03=1.000 in chiusura 2027, poi un
    # investimento di 100.000 al 10% nel 2028. Il pool esistente (fantasma, dal 2027)
    # si riallinea a 1.000 prima di aprire il cespite nuovo: ce09b 2028 = 1.000 (quota
    # sull'esistente, tutto il residuo) + 5.000 (meta' aliquota sul nuovo) = 6.000,00 —
    # non piu' i 41.040 che il pool fantasma prima produceva.
    from backend.app.services import assumptions_service
    from database.models import BalanceSheet, BudgetScenario, Company, FinancialYear, IncomeStatement
    from tests.e2e_kit import memory_sessions, read_forecast_maps

    rows = righe(depreciation_rate=10)
    rows[1]["tangible_investments"] = 100000  # 2028
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company = Company(name="AMBIENTA", tax_id="I1SONDA", sector=1, user_id="rilievi")
            db.add(company); db.flush()
            fy = FinancialYear(company_id=company.id, year=2026, period_months=None,
                               validation_status="verified", forecastable=True)
            db.add(fy); db.flush()
            db.add(BalanceSheet(financial_year_id=fy.id, **BASE_BS))
            db.add(IncomeStatement(financial_year_id=fy.id, **BASE_CE))
            db.commit()
            sc = BudgetScenario(company_id=company.id, name="i1-sonda", base_year=2026,
                                scenario_type="budget")
            db.add(sc); db.commit()
            res = assumptions_service.bulk_upsert_assumptions(
                db, sc.id, [dict(r) for r in rows], auto_generate=True)
            assert res["forecast_generated"] is True, res["message"]
            assumptions_service.apply_sp_overrides(
                db, sc, [{"forecast_year": 2027, "field": "sp03_immob_materiali", "value": 1000}],
            )
            anni = {y: (sp, c) for y, sp, c in read_forecast_maps(db, sc.id)}
            ce2028 = anni[2028][1]
            assert ce2028["ce09b_ammort_materiali"] == D("6000.00")
    finally:
        engine.dispose()


# ── M3 (revisione finale, 2026-09-26): un override di ce09a/ce09b oltre il netto
# disponibile si RIFIUTA con un ValueError italiano — come ce10_override oltre le
# materie d'apertura — invece di essere onorato nel CE mentre lo SP clampa a zero e la
# cassa assorbe la differenza. ──

def test_M3_override_ce09b_oltre_il_netto_disponibile_si_rifiuta():
    rows = righe(ce09b_override=999999999)
    res = genera(rows).res
    assert res["forecast_generated"] is False
    assert "ce09b" in res["message"] and "netto disponibile" in res["message"], res["message"]


def test_M3_override_ce09a_oltre_il_netto_disponibile_si_rifiuta():
    rows = righe(ce09a_override=999999999)
    res = genera(rows).res
    assert res["forecast_generated"] is False
    assert "ce09a" in res["message"] and "netto disponibile" in res["message"], res["message"]


def test_M3_override_ce09b_entro_il_netto_disponibile_e_accettato():
    # Solo il primo anno: applicarlo a tutti e tre (come farebbe un `righe(...)` diretto)
    # svuoterebbe il netto disponibile del 2028, che erediterebbe zero e rifiuterebbe lo
    # stesso override per una ragione diversa — lo stesso accorgimento degli altri test a
    # override singolo di questo file.
    netto = BASE_BS["sp03_immob_materiali"]
    rows = righe()
    rows[0]["ce09b_override"] = float(netto)
    e = generato(genera(rows))
    assert e.anni[2027][1]["ce09b_ammort_materiali"] == netto.quantize(D("0.01"))


# ── M1 (revisione finale, 2026-09-26): fuori dal regime esplicito dei fidi, il breve
# pregresso resta quanto il bilancio gia' porta (`sp16a`), non la rata dell'anno dopo — una
# lista di rimborsi scritta a mano che non copre l'anno dopo non sposta nulla li', e la riga
# non deve dichiarare `rata_ripetuta: True` come se lo facesse. ──

def test_M1_pregresso_fuori_dal_regime_fidi_rata_ripetuta_non_sposta_nulla():
    banche = float(BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"])

    def _scenario(repayments):
        rows = righe()
        rows[0]["financing_loans"] = [{**MUTUO_A, "opening_residual": banche, "repayments": repayments}]
        return generato(genera(rows))

    non_scadenziato = _scenario([53409, 53409, 53409])       # non copre il 2030
    scadenziato = _scenario([53409, 53409, 53409, 53409])    # copre il 2030

    c_non = non_scadenziato.det[2029]["debito_bancario"]["contratti"][0]
    c_si = scadenziato.det[2029]["debito_bancario"]["contratti"][0]

    # Fuori dal regime fidi il breve pregresso e' sempre `breve_pregresso_fine` (cio' che
    # sp16a gia' porta), mai la rata dell'anno dopo: la ripetizione non sposta nulla.
    assert c_non["breve"] == c_si["breve"]
    assert c_non["lungo"] == c_si["lungo"]
    assert c_non["rata_ripetuta"] is False
    assert c_si["rata_ripetuta"] is False
