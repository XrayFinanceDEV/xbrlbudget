"""Le regole dei testi: stessa pratica, stesso testo; ogni frase nasce da una soglia dichiarata."""
from decimal import Decimal as D

from app.renderers.business_plan import narrative
from app.renderers.business_plan.data import BusinessPlanData, Column

COLS = (Column("closing:2026", 2026, "2026 F", True),) + tuple(
    Column(f"forecast:{y}", y, f"{y} P", False) for y in (2027, 2028, 2029))


def make(values: dict, growth: dict | None = None, workflow="infrannuale", residual=D("2004755")):
    vals = {k: tuple(None if x is None else D(str(x)) for x in v) for k, v in values.items()}
    g = {k: tuple(D(str(x)) for x in v) for k, v in (growth or {}).items()}
    return BusinessPlanData(company_name="X", workflow=workflow, columns=COLS, base_description="",
                            values=vals, growth=g, residual_revenue=residual)


AMBIENTA = {
    "ricavi": [4109510, 4314986, 4573885, 4673885], "ebitda": [165837, 188329, 395033, 402197],
    "ebitda_margin": [4.04, 4.36, 8.64, 8.61], "inc_personale": [57.06, 54.34, 51.26, 50.17],
    "personale": [2344742] * 4, "dscr": [2.939, 3.085, 6.293, 6.912], "of_mol": [27.25, 30.63, 13.09, 11.85],
    "cf_operativo": [-225519, 399355, 262189, 406154], "cf_investimenti": [61790, -150000, 0, 0],
    "cf_rimborsi": [0, 0, 105000, 105000], "pfn": [960883, 721528, 469339, 73185],
    "pfn_ebitda": [5.794, 3.831, 1.188, 0.182], "margine_sicurezza": [-4.31, 5.02, 14.30, 14.39],
    "dso": [119, 101, 99, 93], "dpo": [126, 126, 125, 120], "ciclo": [18, 0, 2, 3],
    "patrimonio_netto": [203616, 230385, 410503, 598707], "margine_struttura": [-253424, -281391, -6008, 277460],
    "indipendenza": [8.79, 8.89, 14.81, 20.15], "cassa_fine": [55, 346000, 503190, 804344],
    "banche": [960937, 1067528, 972528, 877528], "banche_breve": [493409, 495000, 495000, 450000],
    "costi_fissi": [1671438, 1780869, 1802894, 1832755], "cf_variazione": [-29212, 345946, 157189, 301154],
    "cc_comm": [852261, 888269, 979298, 983378], "inc_costi_operativi": [101.65, 97.79, 93.40, 93.38],
    "inc_servizi": [34.86, 34.03, 33.06, 32.52], "inc_materie": [3.15, 3.15, 3.15, 3.51],
    "inc_godimento": [5.71, 5.44, 5.13, 5.86], "inc_oneri_diversi": [0.91, 0.87, 0.82, 1.36],
}
GROWTH = {"revenue_growth_pct": [5, 6, 1], "personnel_growth_pct": [0, 0, 0], "dso_days": [96, 95, 90]}


def test_punti_chiave_ambienta():
    kp = narrative.key_points(make(AMBIENTA, GROWTH))
    leads = [lead for lead, _ in kp]
    assert leads == ["Crescita dei ricavi.", "Redditività in miglioramento.", "Servizio del debito coperto.",
                     "Generazione di cassa e deleveraging.", "Sopra il break even point.",
                     "Circolante più efficiente."]
    assert "del 5% nel 2027, del 6% nel 2028 e dell'1% nel 2029" in kp[0][1]
    assert "dal 4,04% all'8,61%" in kp[1][1]


def test_forza_debolezza_e_azioni_ambienta():
    forza, debolezza = narrative.strengths_weaknesses(make(AMBIENTA, GROWTH))
    assert [f.id for f in forza] == ["margini", "cassa", "deleveraging", "incassi", "patrimonio"]
    assert [f.id for f in debolezza] == ["sotto_bep", "costi_rigidi", "tensione_liquidita", "sottocapitalizzazione",
                                         "debito_breve"]
    azioni = narrative.actions(make(AMBIENTA, GROWTH), debolezza)
    assert [a[0] for a in azioni] == ["Consolidare il forecast 2026", "Superare stabilmente il break even point",
                                      "Presidiare i costi fissi", "Accelerare gli incassi",
                                      "Riequilibrare la struttura finanziaria"]
    assert "€ 2.004.755" in azioni[0][1]


def test_regole_di_segno_opposto():
    peggio = dict(AMBIENTA, ebitda_margin=[8, 7, 6, 5], cf_operativo=[10, -5, -3, 2], margine_sicurezza=[5, 3, 1, -2],
                  ciclo=[10, 20, 30, 40], pfn=[100, 200, 300, 400], pfn_ebitda=[1, 2, 3, 4], dscr=[3, 0.8, 1.1, 1.2])
    kp = dict(narrative.key_points(make(peggio, GROWTH)))
    assert "Redditività in calo." in kp and "Sotto il break even point." in kp
    assert "Servizio del debito non coperto." in kp and "Circolante in assorbimento." in kp
    forza, debolezza = narrative.strengths_weaknesses(make(peggio, GROWTH))
    assert {"margini_calo", "flussi_negativi", "indebitamento"} <= {f.id for f in debolezza}


def test_narrativa_senza_dati():
    vuota = make({})
    assert narrative.key_points(vuota) == []
    forza, debolezza = narrative.strengths_weaknesses(vuota)
    assert forza == [] and debolezza == []
    assert narrative.actions(make({}, workflow="startup"), []) == [
        ("Monitorare il piano", "Confrontare trimestralmente consuntivo e piano su ricavi, EBITDA e cassa.",
         "Ricavi, EBITDA, cassa")]
    assert narrative.lettura_costi(vuota) == []
    assert narrative.subtitle_flussi(vuota).startswith("Rendiconto finanziario di sintesi")


def test_testo_deterministico():
    a = make(AMBIENTA, GROWTH)
    assert narrative.key_points(a) == narrative.key_points(make(AMBIENTA, GROWTH))
