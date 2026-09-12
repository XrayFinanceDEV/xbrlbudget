"""I messaggi del previsionale nascono in italiano, importi all'europea, codici diagnostici invariati (lotto 3A, Task 8).

Task 8 era diviso in due parti dal coordinatore (i motori erano toccati da altri agenti in parallelo,
Task 2/4/5 di questo stesso lotto): la parte A copriva i servizi e le rotte del previsionale
(`backend/app/services/assumptions_service.py`, `forecast_preview_service.py`, `promote_service.py`,
`backend/app/api/v1/budget_scenarios.py`); la parte B, qui completata, copre
`calculations/forecast_engine.py` e `calculations/intra_year_engine.py`.
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

# Frammenti dei testi inglesi di oggi, file per file: nessuno deve restare, commenti compresi.
#
# Ruling 9 (parte B): il brief attribuiva a `intra_year_engine.py · _get_split_investments` il
# testo "Investments must be split into ...", che in questo codice non c'e' mai stato — la stringa
# VERA di quel raise e' "Aggregate investments cannot be allocated automatically; provide
# intangible_investments and/or tangible_investments" (la stessa che il brief attribuiva, per
# errore di snapshot, al motore budget). Il file e simbolo restano quelli del brief; il frammento
# di guardia segue la stringa vera di ciascun file, non il testo "oggi" (sbagliato) del brief:
# `forecast_engine.py` aveva davvero "Investments must be split into ...", `intra_year_engine.py`
# aveva davvero "Aggregate investments cannot be allocated ...".
FRASI_INGLESI = {
    "calculations/forecast_engine.py": [
        "Unfunded financing requirement", "Budget scenario {scenario_id} not found", "data not found or incomplete",
        "the overdraft gate needs", "Investments must be split", "is allowed only in the first forecast year",
        "must equal base-year", "No assumptions found for scenario", "creditor categories are required", '"Base source"'],
    "calculations/intra_year_engine.py": [
        "Aggregate investments cannot be allocated", "is not a valid period", "is not a valid partial period", "diagnostics are unreadable",
        "empty balance sheet", "SP imbalance", "profit mismatch", "source plug", "aggregate/detail mismatch",
        "is not forecastable", "No assumptions found for scenario", 'Scenario {scenario_id} not found"',
        "is not infrannuale type", "requires period_months between 1 and 12", "Projected assets exceed explicit funding",
        "Short-term debt breakdown is unavailable", "must equal source bank", '"Partial source"', '"Reference source"'],
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


def test_il_fabbisogno_scoperto_si_dice_in_italiano_con_l_importo_all_europea():
    with pytest.raises(ValueError) as e:
        _Overdraft(allowed=False).copri(D("-1100700.90"))
    assert str(e.value).startswith("Fabbisogno finanziario scoperto di 1.100.700,90: "), str(e.value)


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


def test_check_quadratura_dice_lo_sbilancio_all_europea():
    """Il 400 di POST /scenarios/{id}/promote (promote_service.py) concatena
    validation.warnings senza riformattarli: se check_quadratura scrive gli importi
    all'americana, il 400 li mostra all'americana (indagine-2, parte B, 2026-09-11:
    '1,470,357.32' invece di '1.470.357,32'). Sbilancio scelto identico a quello del
    collaudo: 5.509,29."""
    from decimal import Decimal as D

    from importers.iv_cee_hierarchy import check_quadratura

    bs = {"sp09_disponibilita_liquide": D("1470357.32"), "sp11_capitale": D("1464848.03")}
    q = check_quadratura(bs, None)
    assert not q.quadra
    messaggio = "; ".join(q.warnings)
    assert "5.509,29" in messaggio, messaggio
    assert "1.470.357,32" in messaggio, messaggio
    assert "1.464.848,03" in messaggio, messaggio
    assert "5,509.29" not in messaggio, messaggio
    assert "1,470,357.32" not in messaggio, messaggio


def test_save_adjustments_worsening_message_is_italian_formatted():
    """PUT /adjustments (save_adjustments, backend/app/api/v1/financial_years.py) rifiuta una
    modifica che peggiora lo sbilancio con un 400 il cui messaggio, prima di questa correzione,
    formattava gli importi all'americana -- stesso difetto di classe di
    importers/iv_cee_hierarchy.py (indagine-2 parte B), perimetro esteso dal coordinatore
    nell'assemblaggio di questo piano. Costruzione ORM diretta (sqlite in memoria), niente
    import PDF: save_adjustments si chiama come funzione semplice, senza passare per FastAPI
    (stesso pattern di tests/test_lifecycle_repeat.py, righe 184/204/248)."""
    from decimal import Decimal as D

    import pytest
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.api.v1 import financial_years
    from backend.app.schemas.adjustments import AdjustmentsUpdate
    from database.db import Base
    from database.models import BalanceSheet, Company, FinancialYear, IncomeStatement

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    azienda = Company(name="IT AMOUNT SRL", tax_id="ITAMOUNT01", sector=1, user_id="msg-it")
    db.add(azienda); db.flush()
    fy = FinancialYear(company_id=azienda.id, year=2026, period_months=None,
                        validation_status="verified", forecastable=True)
    db.add(fy); db.flush()
    db.add(BalanceSheet(financial_year_id=fy.id, sp09_disponibilita_liquide=D("100000"),
                         sp11_capitale=D("100000")))
    db.add(IncomeStatement(financial_year_id=fy.id))
    db.commit()

    with pytest.raises(HTTPException) as esc:
        financial_years.save_adjustments(
            azienda.id, 2026,
            AdjustmentsUpdate(
                balance_sheet={"sp09_disponibilita_liquide": D("1334567.89")},
                income_statement={}, rettifiche_log=[],
            ),
            period_months=None, user_id="msg-it", db=db,
        )
    detail = esc.value.detail
    assert esc.value.status_code == 400
    assert "1.234.567,89" in detail, detail
    assert "1,234,567.89" not in detail, detail


def test_route_c_bilancio_non_quadrato_usa_it_amount():
    """Route C (situazione contabile, importers/pdf_importer.py:1385-1398) formattava il residuo
    non classificato con {:,.0f} -- stesso difetto di classe, propagato parola per parola dal
    frontend (ImportPanel.tsx). L'helper _it_amount e' gia' presente nello stesso file: questo
    test lo esercita direttamente (una prova end-to-end con un documento route-C ambiguo e'
    fuori dal perimetro pratico di questo task -- vedi la nota di onesta' nel rapporto di fine
    task)."""
    from decimal import Decimal as D

    from importers.pdf_importer import _it_amount

    assert _it_amount(D("12345.6")) == "12.345,60"
    assert _it_amount(D("1234567.89")) == "1.234.567,89"


def test_nessun_formato_americano_residuo_nei_tre_moduli_del_perimetro():
    """Grep-based: nessuna delle righe toccate da questo task deve piu' contenere un formato
    americano (`:,.2f` o `:,.0f` su un importo). Non sostituisce le prove sopra (che verificano
    anche il comportamento), ma chiude il perimetro con una rete che non dipende da un fixture.

    La rete e' sulle RIGHE DI MESSAGGIO, non sul file intero nudo: in pdf_importer.py il
    pattern {:,.2f} vive per NECESSITA' anche nell'implementazione dei due helper italiani
    (_it_amount riga 78 e _euro_it riga 287 -- li' il formato americano e' il MEZZO con cui
    nasce l'italiano, non un messaggio), e sopravvive una riga non toccata dal perimetro di
    questo task: il logger.info di route C 'contra-netting applicato ({_contra:,.0f} ...)'
    (riga 1318, solo log, non utente-facing) che il brief non elenca fra le sue occorrenze.
    Quest'ultima e' segnalata nel rapporto del task come residuo noto, per il collaudo."""
    import re
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*:,\.(0|1|2)f\}")
    for percorso in (
        "importers/iv_cee_hierarchy.py",
        "backend/app/api/v1/financial_years.py",
        "importers/pdf_importer.py",
    ):
        for n, riga in enumerate((repo / percorso).read_text(encoding="utf-8").splitlines(), 1):
            if ".replace('#', '.')" in riga:  # implementazione helper italiano: mezzo, non messaggio
                continue
            if "_contra:,.0f" in riga:  # riga 1318 (continuazione del log contra-netting): fuori perimetro, solo log
                continue
            assert not pattern.search(riga), f"{percorso}:{n}: {riga.strip()}"
