"""I messaggi del previsionale nascono in italiano, importi all'europea, codici diagnostici invariati (lotto 3A, Task 8).

Task 8 e' diviso in due parti dal coordinatore (i motori sono toccati da altri agenti in parallelo,
Task 2/4/5 di questo stesso lotto): la parte A copre i servizi e le rotte del previsionale
(`backend/app/services/assumptions_service.py`, `forecast_preview_service.py`, `promote_service.py`,
`backend/app/api/v1/budget_scenarios.py`); la parte B, non ancora fatta, copre `calculations/forecast_engine.py`
e `calculations/intra_year_engine.py`. I tre test che leggono un messaggio dei motori sono marcati `xfail`
finche' la parte B non e' integrata: diventeranno verdi da soli, senza bisogno di essere riscritti.
"""
from decimal import Decimal as D
from pathlib import Path

import pytest

from backend.app.services import assumptions_service
from calculations.forecast_engine import _Overdraft
from calculations.intra_year_engine import IntraYearEngine
from database.models import BudgetScenario
from tests.e2e_kit import memory_sessions, seed_base_year
from tests.test_intra_year_semantics import _assumption, _zero_projection

REPO = Path(__file__).resolve().parents[1]

# Frammenti dei testi inglesi di oggi, solo per i file della parte A (servizi e rotte). I motori
# (`calculations/forecast_engine.py`, `calculations/intra_year_engine.py`) sono la parte B: restano
# in inglese fino a quel lotto, e non vanno controllati qui.
FRASI_INGLESI = {
    "backend/app/services/assumptions_service.py": [
        'Scenario {scenario_id} not found"', "Assumptions saved", "forecast generated successfully",
        "overrides list is required", "needs forecast_year and field", "Invalid override field", "No assumptions found for year"],
    "backend/app/services/forecast_preview_service.py": ['Budget scenario {scenario_id} not found"'],
    "backend/app/services/promote_service.py": [
        'Scenario {scenario_id} not found"', "Only infrannuale scenarios", "No projection found", "Projection is incomplete",
        "Promotion aborted", "promoted to full-year"],
    "backend/app/api/v1/budget_scenarios.py": [
        "Comparison is only available", "Only infrannuale scenarios", "must be greater than base year",
        "already exist in scenario", "Forecast generation failed", "Internal error during forecast",
        "Error saving assumptions:", "regeneration failed, no override", "Cannot generate forecast"],
}


def test_nessun_testo_inglese_del_perimetro_resta_nei_sorgenti():
    fuori = []
    for percorso, frasi in FRASI_INGLESI.items():
        testo = (REPO / percorso).read_text(encoding="utf-8")
        fuori += [f"{percorso}: «{frase}»" for frase in frasi if frase in testo]
    assert not fuori, "testi inglesi rimasti:\n" + "\n".join(fuori)


@pytest.mark.xfail(reason="parte B del Task 8 (lotto 3A): _Overdraft.copri parla ancora inglese", strict=False)
def test_il_fabbisogno_scoperto_si_dice_in_italiano_con_l_importo_all_europea():
    with pytest.raises(ValueError) as e:
        _Overdraft(allowed=False).copri(D("-1100700.90"))
    assert str(e.value).startswith("Fabbisogno finanziario scoperto di 1.100.700,90: "), str(e.value)


@pytest.mark.xfail(reason="parte B del Task 8 (lotto 3A): il messaggio del motore budget e' ancora inglese", strict=False)
def test_il_bulk_che_non_genera_lo_dice_in_italiano(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id="messaggi")
            sc = BudgetScenario(company_id=company_id, name="messaggi", base_year=2026, scenario_type="budget")
            db.add(sc)
            db.commit()
            righe = [{"forecast_year": 2027, "revenue_growth_pct": 3, "tax_rate": 27.9, "tangible_investments": 5000000}]
            esito = assumptions_service.bulk_upsert_assumptions(db, sc.id, righe, auto_generate=True)
        assert esito["forecast_generated"] is False
        assert esito["message"].startswith(
            "Ipotesi salvate, ma il previsionale non è stato calcolato: Fabbisogno finanziario scoperto di "), esito["message"]
    finally:
        engine.dispose()


@pytest.mark.xfail(reason="parte B del Task 8 (lotto 3A): il diagnostico dell'infrannuale e' ancora inglese", strict=False)
def test_il_diagnostico_dell_infrannuale_e_italiano_e_il_codice_resta():
    from types import SimpleNamespace
    motore = IntraYearEngine(None)
    motore._project_balance_sheet_annualized(
        SimpleNamespace(sp02_immob_immateriali=D("1000"), sp16_debiti_breve=D("0")),
        SimpleNamespace(), _zero_projection(), _assumption(), 9)
    diagnostico = next(d for d in motore._diagnostics if d["code"] == "unfunded_financing_requirement")
    assert diagnostico["message"] == (
        "L'attivo proiettato supera le fonti di finanziamento esplicite: aggiungi un'ipotesi di finanziamento "
        "esplicita; nessun debito è stato creato automaticamente.")
