"""A06 · la casella dei previdenziali diventa la tendina (spec fix rilievi 2026-09-26 §3, lotto 3)."""
from decimal import Decimal as D

from database.models import BudgetAssumptions
from scripts.migra_previdenza_tendina import migra
from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, per_anno, righe
from tests.e2e_kit import memory_sessions


def test_il_motore_ignora_la_casella():
    rows = per_anno(righe(previdenza_scales_with_personnel=True), "personnel_growth_pct", (3, 4, 4))
    per_anno(rows, "revenue_growth_pct", (5, 6, 7))
    e = generato(genera(rows))
    assert e.anni[2027][0]["sp16f_debiti_previdenza_breve"] == BASE_BS["sp16f_debiti_previdenza_breve"]


def test_tendina_personale_da_gli_stessi_numeri_della_casella_di_prima():
    rows = per_anno(righe(sp_indexing={"sp16f": "personale", "sp17f": "personale"}), "personnel_growth_pct", (3, 4, 4))
    e = generato(genera(rows))
    b16, b08 = BASE_BS["sp16f_debiti_previdenza_breve"], BASE_CE["ce08_costi_personale"]
    for y in (2027, 2028, 2029):
        sp, ce = e.anni[y]
        assert abs(sp["sp16f_debiti_previdenza_breve"] - b16 * ce["ce08_costi_personale"] / b08) < D("1"), y


# ── La migrazione una tantum ──

def _seed_row(db, *, flag, sp_indexing=None, forecast_year=2027):
    """Semina azienda, anno base, scenario budget e una riga di ipotesi, col minimo
    richiesto dal modello. Riusa `build_assumption_row` per non dover elencare a mano
    ogni colonna NOT NULL di `BudgetAssumptions` (stesso motivo del bulk di produzione)."""
    from backend.app.services.assumptions_service import build_assumption_row
    from database.models import BalanceSheet, BudgetScenario, Company, FinancialYear, IncomeStatement

    company = Company(name="MIGRA", tax_id="MIGRA2026", sector=1, user_id="migra")
    db.add(company)
    db.flush()
    fy = FinancialYear(company_id=company.id, year=2026, period_months=None,
                        validation_status="verified", forecastable=True)
    db.add(fy)
    db.flush()
    db.add(BalanceSheet(financial_year_id=fy.id, **BASE_BS))
    db.add(IncomeStatement(financial_year_id=fy.id, **BASE_CE))
    db.commit()
    sc = BudgetScenario(company_id=company.id, name="migra", base_year=2026, scenario_type="budget")
    db.add(sc)
    db.commit()
    row = build_assumption_row(sc.id, {
        "forecast_year": forecast_year,
        "previdenza_scales_with_personnel": flag,
        "sp_indexing": sp_indexing,
    })
    db.add(row)
    db.commit()
    return sc, row


def test_pianifica_una_riga_col_flag_acceso():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            sc, row = _seed_row(db, flag=True, sp_indexing={"sp16f": "ricavi", "sp10": "ricavi"})
            modifiche = migra(db, apply=False)
            assert len(modifiche) == 1
            m = modifiche[0]
            assert m.scenario_id == sc.id
            assert m.indicizzazione_prima == {"sp16f": "ricavi", "sp10": "ricavi"}
            assert m.indicizzazione_dopo == {"sp16f": "personale", "sp17f": "personale", "sp10": "ricavi"}
            # prova: non scrive nulla
            db.refresh(row)
            assert row.previdenza_scales_with_personnel is True
            assert row.sp_indexing == {"sp16f": "ricavi", "sp10": "ricavi"}
    finally:
        engine.dispose()


def test_applica_scrive_e_azzera_il_flag():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            sc, row = _seed_row(db, flag=True, sp_indexing={"sp16f": "ricavi", "sp10": "ricavi"})
            migra(db, apply=True)
            db.refresh(row)
            assert row.previdenza_scales_with_personnel is False
            assert row.sp_indexing == {"sp16f": "personale", "sp17f": "personale", "sp10": "ricavi"}

            row_id = row.id
            # idempotente: una seconda esecuzione non trova piu' nulla da cambiare
            modifiche2 = migra(db, apply=True)
            assert modifiche2 == []
            db.refresh(row)
            assert row.id == row_id
            assert row.previdenza_scales_with_personnel is False
            assert row.sp_indexing == {"sp16f": "personale", "sp17f": "personale", "sp10": "ricavi"}
    finally:
        engine.dispose()


def test_senza_flag_niente_da_migrare():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            _seed_row(db, flag=False, sp_indexing={"sp16f": "ricavi"})
            assert migra(db, apply=False) == []
    finally:
        engine.dispose()


def test_prova_non_scrive_nulla():
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            sc, row = _seed_row(db, flag=True, sp_indexing=None)
            modifiche = migra(db, apply=False)
            assert len(modifiche) == 1
            assert modifiche[0].indicizzazione_prima is None
            assert modifiche[0].indicizzazione_dopo == {"sp16f": "personale", "sp17f": "personale"}
            db.refresh(row)
            assert row.previdenza_scales_with_personnel is True
            assert row.sp_indexing is None
    finally:
        engine.dispose()
