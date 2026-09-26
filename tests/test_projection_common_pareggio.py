"""F5 (decisione del proprietario, 2026-09-26): `calculations.projection_common.punto_di_pareggio`
è l'UNICA implementazione del blocco pareggio sul MOL, usata sia da ogni anno di piano del motore
budget (`calculations/forecast_engine.py`) sia dalla colonna base/storica del report finale
(`backend/app/services/final_report_dossier.py`). Questi test coprono la funzione pura,
isolatamente: l'oracolo end-to-end (AMBIENTA, niente finto risanamento) vive in
`tests/test_fix_rilievi_bep.py`.
"""
from decimal import Decimal as D

from calculations.projection_common import PAREGGIO_CAMPI, punto_di_pareggio


def _base(**overrides):
    valori = dict(ce01=D("4000"), ce02=D("0"), ce03=D("0"), ce03a=D("0"), ce04=D("0"),
                  ce05_fixed=D("400"), ce05_variable=D("600"), ce06_fixed=D("200"), ce06_variable=D("300"),
                  ce07=D("100"), ce08=D("200"), ce10=D("0"), ce11=D("0"), ce11b=D("0"), ce12=D("200"))
    valori.update(overrides)
    return valori


def test_costi_variabili_e_fissi_sommano_ce05_ce06_per_quota():
    r = punto_di_pareggio(**_base())
    assert r["costi_variabili"] == D("900")  # 600 + 300
    assert r["costi_fissi"] == D("1100")  # 400 + 200 + 100 + 200 + 200
    assert r["costi_fissi_operativi"] == D("1100")  # nessuna rettifica: tutte a zero


def test_costi_fissi_operativi_include_le_rettifiche_sul_mol():
    """ce04 (altri ricavi), ce02/ce03/ce03a (rimanenze prodotti e lavori interni) si sottraggono;
    ce10/ce11/ce11b (rimanenze materie e accantonamenti) si sommano — mai al plain `costi_fissi`."""
    r = punto_di_pareggio(**_base(ce02=D("10"), ce03=D("20"), ce03a=D("30"), ce04=D("50"),
                                  ce10=D("5"), ce11=D("7"), ce11b=D("3")))
    assert r["costi_fissi"] == D("1100")  # invariato: non entra nelle rettifiche
    # 1100 + 5 + 7 + 3 - 50 - 10 - 20 - 30 = 1005
    assert r["costi_fissi_operativi"] == D("1005")
    assert r["costi_fissi_operativi"] != r["costi_fissi"]


def test_margine_bep_e_sicurezza_dallidentita_del_motore():
    r = punto_di_pareggio(**_base())
    # MdC% = (4000 - 900) / 4000 = 77,5%; bep = 1100 / 0,775 = 1419,354838...
    assert r["margine_contribuzione_pct"] == D("77.5")
    atteso_bep = D("1100") / (D("3100") / D("4000"))
    assert abs(r["fatturato_pareggio"] - atteso_bep) < D("0.0000001")
    assert r["margine_sicurezza"] == D("4000") - r["fatturato_pareggio"]
    # Per costruzione: fatturato_pareggio x margine = costi_fissi_operativi (bep = cf_op / margine).
    assert abs(r["fatturato_pareggio"] * (D("3100") / D("4000")) - r["costi_fissi_operativi"]) < D("0.0000001")


def test_none_su_ogni_chiave_quando_la_quota_fisso_variabile_manca():
    """Una riga sotto override (ce05 o ce06) non ha più una scomposizione fisso/variabile:
    l'intero blocco resta `None`, mai un valore ricalcolato da un default silenzioso."""
    for campo in ("ce05_fixed", "ce05_variable", "ce06_fixed", "ce06_variable"):
        r = punto_di_pareggio(**_base(**{campo: None}))
        assert all(r[k] is None for k in PAREGGIO_CAMPI), (campo, r)


def test_margine_e_bep_restano_none_con_ricavi_o_margine_non_positivi():
    """Costi variabili e fissi restano dichiarati; margine/bep/sicurezza no — mai zero."""
    r = punto_di_pareggio(**_base(ce01=D("0")))
    assert r["costi_variabili"] == D("900") and r["costi_fissi_operativi"] == D("1100")
    assert r["margine_contribuzione_pct"] is None
    assert r["fatturato_pareggio"] is None
    assert r["margine_sicurezza"] is None
    assert r["margine_sicurezza_pct"] is None
    # Margine di contribuzione non positivo: ricavi bassi, costi variabili invariati.
    r2 = punto_di_pareggio(**_base(ce01=D("500")))
    assert r2["fatturato_pareggio"] is None


def test_nessun_arrotondamento_qui_resta_a_carico_del_chiamante():
    """La funzione non quantizza: il motore arrotonda al centesimo per `engine_meta`, il report
    allo stesso modo per restare confrontabile — qui i valori restano a precisione piena."""
    r = punto_di_pareggio(**_base(ce05_variable=D("600.005")))
    assert r["costi_variabili"] == D("900.005")
