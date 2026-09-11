"""Il residuo di quadratura dello SP va solo su campi neutri; se nessuno e' libero si posa sul default e si dichiara (lotto 3A, Task 12)."""
import json
import sys
from decimal import ROUND_HALF_UP, Decimal as D

from backend.app.api.v1 import budget_scenarios
from backend.app.schemas.budget import BudgetScenarioCreate
from calculations.forecast_engine import ForecastEngine
from database.models import BalanceSheet, FinancialYear
from tests.e2e_kit import memory_sessions, seed_base_year

NEUTRI = {
    "sp01_crediti_soci": ("sp01b_parte_da_richiamare", "sp01a_parte_richiamata"),
    "sp02_immob_immateriali": ("sp02g_altre_immob_imm", "sp02a_costi_impianto", "sp02b_costi_sviluppo",
                               "sp02c_brevetti", "sp02d_concessioni", "sp02e_avviamento", "sp02f_immob_in_corso"),
    "sp03_immob_materiali": ("sp03d_altri_beni", "sp03a_terreni_fabbricati", "sp03b_impianti_macchinari",
                             "sp03c_attrezzature", "sp03e_immob_in_corso"),
    "sp04_immob_finanziarie": ("sp04d_altri_titoli", "sp04a_partecipazioni", "sp04c_crediti_immob_lungo"),
    "sp05_rimanenze": ("sp05e_acconti", "sp05a_materie_prime", "sp05b_prodotti_in_corso",
                       "sp05c_lavori_in_corso", "sp05d_prodotti_finiti"),
    "sp06_crediti_breve": ("sp06g_crediti_altri_breve", "sp06d_crediti_controllanti_breve",
                           "sp06c_crediti_collegate_breve", "sp06b_crediti_controllate_breve", "sp06a_crediti_clienti_breve"),
    "sp07_crediti_lungo": ("sp07g_crediti_altri_lungo", "sp07d_crediti_controllanti_lungo",
                           "sp07c_crediti_collegate_lungo", "sp07b_crediti_controllate_lungo", "sp07a_crediti_clienti_lungo"),
    "sp12_riserve": ("sp12g_utili_perdite_portati", "sp12e_altre_riserve", "sp12a_riserva_sovrapprezzo",
                     "sp12b_riserve_rivalutazione", "sp12c_riserva_legale", "sp12d_riserve_statutarie",
                     "sp12f_riserva_copertura_flussi"),
    "sp14_fondi_rischi": ("sp14d_altri_fondi", "sp14a_fondi_trattamento_quiescenza"),
    "sp16_debiti_breve": ("sp16g_altri_debiti_breve", "sp16f_debiti_previdenza_breve",
                          "sp16e_debiti_tributari_breve", "sp16d_debiti_fornitori_breve"),
    "sp17_debiti_lungo": ("sp17g_altri_debiti_lungo", "sp17f_debiti_previdenza_lungo",
                          "sp17e_debiti_tributari_lungo", "sp17d_debiti_fornitori_lungo"),
}
FINANZIARI = ("sp16a_debiti_banche_breve", "sp16b_debiti_altri_finanz_breve", "sp16c_debiti_obbligazioni_breve",
              "sp17a_debiti_banche_lungo", "sp17b_debiti_altri_finanz_lungo", "sp17c_debiti_obbligazioni_lungo")


def _q(x):
    return D(str(x)).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def test_la_tabella_dei_campi_neutri_sta_nel_codice():
    assert getattr(ForecastEngine, "_CAMPI_NEUTRI_RESIDUO", None) == NEUTRI


def _griglia_in_processo(tmp_path):
    """Il driver del banco eseguito in questo processo (seme 20260910, 4 anni): una spia sul motore lo vede."""
    from scripts import parita_motore as banco
    ingresso, uscita = tmp_path / "in.json", tmp_path / "out.json"
    ingresso.write_text(json.dumps({"scenari": banco.costruisci_griglia(20260910, 4)}), encoding="utf-8")
    spazio = {"__name__": "driver_banco"}
    exec(compile(banco.DRIVER, "driver_banco", "exec"), spazio)
    argv = sys.argv
    sys.argv = ["driver_banco", str(banco.REPO_ROOT), str(ingresso), str(uscita)]
    try:
        assert spazio["main"]() == 0
    finally:
        sys.argv = argv
    return json.loads(uscita.read_text(encoding="utf-8"))


def test_sulla_griglia_ogni_residuo_sta_su_un_campo_neutro_e_i_debiti_finanziari_non_si_muovono(tmp_path, monkeypatch):
    originale = ForecastEngine.__dict__["_normalize_balance_sheet_cents"].__func__
    violazioni, chiamate = [], []

    def spia(cls, values, **kw):
        risultato = originale(cls, values, **kw)
        scoperto = kw.get("overdraft")
        if scoperto is not None:
            sweep = kw.get("sweep")
            rimborsato = (sweep.rimborso_breve + sweep.rimborso_lungo) if sweep is not None else D("0")
            prima = sum((_q(values[f]) for f in FINANZIARI), D("0"))
            dopo = sum((risultato[f] for f in FINANZIARI), D("0"))
            chiamate.append(1)
            if dopo != prima + scoperto.outstanding - rimborsato:
                violazioni.append(f"debiti finanziari: prima {prima}, dopo {dopo}, scoperto {scoperto.outstanding}, sweep {rimborsato}")
        return risultato

    monkeypatch.setattr(ForecastEngine, "_normalize_balance_sheet_cents", classmethod(spia))
    esiti = _griglia_in_processo(tmp_path)
    neutri = {campo for campi in NEUTRI.values() for campo in campi}
    for sid, esito in sorted(esiti.items()):
        for anno in esito["anni"]:
            for posa in anno["details"].get("residuo_quadratura", []):
                dove = f"[{sid} · {anno['anno']}] {posa}"
                if not isinstance(posa.get("campo_dichiarato"), bool):
                    violazioni.append(f"{dove}: campo_dichiarato assente")
                if posa["campo"] not in neutri:
                    violazioni.append(f"{dove}: campo non neutro")
    assert len(chiamate) >= 380, len(chiamate)
    assert not violazioni, f"{len(violazioni)} violazioni:\n" + "\n".join(violazioni[:40])


PIANI_TUTTI = {
    "debiti_fornitori": {"opening": 100000, "amounts": [33333.335, 33333.335, 33333.33]},
    "debiti_tributari": {"opening": 10000, "saldo": 6000, "rateizzato": 4000, "amounts": [1333.335, 1333.335, 1333.33]},
    "debiti_previdenziali": {"opening": 25000, "amounts": [8333.335, 8333.335, 8333.33]},
    "altri_debiti": {"opening": 55000, "amounts": [18333.335, 18333.335, 18333.33]},
}
INVESTIMENTI = {"intangible_investments": 0.02, "tangible_investments": 0.02, "depreciation_rate": 20, "depreciation_rate_intangible": 20}
CRESCITE = (1.11, 3.33, 7.77, 0.37, 2.5, 4.44, 6.66, 9.99)


def _base_ricca(db, user):
    """La base di `tests/test_forecast_dichiarato_vs_persistito.py`: massa su ogni debito operativo, a breve e oltre."""
    company_id, _ = seed_base_year(db, user_id=user)
    fy = db.query(FinancialYear).filter(FinancialYear.company_id == company_id).one()
    b = db.query(BalanceSheet).filter(BalanceSheet.financial_year_id == fy.id).one()
    for campo, valore in {
        "sp16_debiti_breve": "145000", "sp16b_debiti_altri_finanz_breve": "5000", "sp16d_debiti_fornitori_breve": "80000",
        "sp16e_debiti_tributari_breve": "10000", "sp16f_debiti_previdenza_breve": "15000", "sp16g_altri_debiti_breve": "35000",
        "sp17a_debiti_banche_lungo": "0", "sp17d_debiti_fornitori_lungo": "20000", "sp17f_debiti_previdenza_lungo": "10000",
        "sp17g_altri_debiti_lungo": "20000", "sp03_immob_materiali": "140000", "sp04_immob_finanziarie": "20000",
        "sp04a_partecipazioni": "20000", "sp01_crediti_soci": "3000", "sp01b_parte_da_richiamare": "3000",
        "sp08_attivita_finanziarie": "4000", "sp10_ratei_risconti_attivi": "5000", "sp14_fondi_rischi": "6000",
        "sp14d_altri_fondi": "6000", "sp18_ratei_risconti_passivi": "2000", "sp09_disponibilita_liquide": "31000",
    }.items():
        setattr(b, campo, D(valore))
    db.commit()
    return company_id


def test_con_tutti_i_debiti_operativi_pianificati_il_residuo_resta_sul_default_e_si_dichiara(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    posature = []
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            for crescita in CRESCITE:
                user = f"residuo-{crescita}"
                company_id = _base_ricca(db, user)
                righe = [dict(forecast_year=anno, revenue_growth_pct=crescita, **INVESTIMENTI) for anno in (2027, 2028, 2029)]
                righe[0]["pregresso"] = PIANI_TUTTI
                sc = budget_scenarios.create_budget_scenario(
                    company_id, BudgetScenarioCreate(company_id=company_id, name="residuo", base_year=2026, scenario_type="budget"),
                    user_id=user, db=db)
                esito = budget_scenarios.bulk_upsert_assumptions(
                    company_id, sc.id, request={"assumptions": [dict(r) for r in righe], "auto_generate": True}, user_id=user, db=db)
                assert esito["forecast_generated"] is True, esito["message"]
                anteprima = budget_scenarios.preview_forecast_route(
                    company_id, sc.id, request={"assumptions": [dict(r) for r in righe]}, user_id=user, db=db)
                for anno in anteprima["forecast_years"]:
                    posature += [(crescita, anno["year"], p) for p in anno["details"]["residuo_quadratura"]
                                 if p["campo"].startswith(("sp16", "sp17"))]
    finally:
        engine.dispose()
    assert posature, "nessun residuo su sp16/sp17 in questi scenari: vedi lo Step 3"
    fuori = [p for p in posature
             if p[2]["campo"] not in ("sp16g_altri_debiti_breve", "sp17g_altri_debiti_lungo") or p[2].get("campo_dichiarato") is not True]
    assert not fuori, "\n".join(str(p) for p in fuori)
