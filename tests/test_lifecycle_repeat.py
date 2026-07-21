"""Repeated-lifecycle behaviours: re-import, regenerate, override->clear,
rettifica->reset, promote->budget chain, re-promote.

The existing Codex matrix (tests/test_standard_ivcee_parser.py) walks each step
of the import -> rettifiche -> assumptions -> promote pipeline exactly ONCE.
Real users repeat steps: re-import the same company/year, save assumptions
again after setting a CE override, reset a rettifica back to the original
snapshot, and re-promote an infrannuale projection after changing its
hypotheses. This module exercises those REPEATED paths.
"""
from decimal import Decimal

from backend.app.api.v1 import budget_scenarios, financial_years
from backend.app.schemas.adjustments import AdjustmentsUpdate, RettificaEntry
from backend.app.schemas.budget import BudgetScenarioCreate
from backend.app.services.promote_service import promote_projection_to_financial_year
from tests.e2e_kit import memory_sessions, read_forecast_maps, seed_base_year
from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf

USER = "lifecycle"

# Fixed by _write_compact_infrannual_pdf's hardcoded amounts (independent of
# period_months, which only changes the CE page label) -- used as the ground
# truth for the re-import assertion instead of a field the importer's result
# dict does not actually carry (see reconciliation note on test 1 below).
_FIXTURE_TOTAL_ASSETS = Decimal("2417588.25")


def _import_pdf(sessions, monkeypatch, tmp_path, name, period_months=6, company_id=None):
    from importers import pdf_importer

    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    pdf = tmp_path / f"{name}-{period_months}-{company_id}.pdf"
    _write_compact_infrannual_pdf(pdf, period_months=period_months)
    return pdf_importer.import_pdf_balance_sheet(
        file_path=str(pdf), fiscal_year=2026, company_name=name,
        company_id=company_id, create_company=(company_id is None),
        sector=1, period_months=period_months, user_id=USER,
    )


def test_reimport_same_year_replaces_not_duplicates(tmp_path, monkeypatch):
    """Re-importing the SAME company+year+period replaces the FinancialYear
    and BalanceSheet in place instead of creating a duplicate.

    Reconciliation vs the brief: pdf_importer.import_pdf_balance_sheet has NO
    company-matching-by-name path -- when company_id is None and
    create_company=True it unconditionally creates a brand-new Company row
    (importers/pdf_importer.py ~line 1055), regardless of whether a company
    with the same name already exists for the user. That is the real,
    intentional contract (the UI always re-imports against an
    already-selected company_id, never by re-typing a name), so the second
    import in this test passes company_id=first["company_id"] explicitly --
    exactly how the app's "re-import for this company" flow works. Passing
    company_id is what exercises the FinancialYear replace-not-duplicate path
    (importers/pdf_importer.py Step 4, ~line 1068): same company_id + year +
    period_months type (both partial, both not 12) matches the existing
    record, deletes its BalanceSheet/IncomeStatement/FinancialYear, and
    inserts a fresh set -- so re-import always yields exactly one row per
    (company, year, period-type).

    Also cleaned up the brief's placeholder final assert (which referenced a
    "total_assets" key the result dict never contains) into a real assertion
    against the fixture's known total.
    """
    from database.models import BalanceSheet, FinancialYear

    engine, sessions = memory_sessions()
    try:
        first = _import_pdf(sessions, monkeypatch, tmp_path, "REIMPORT SRL")
        assert first["success"] is True

        second = _import_pdf(
            sessions, monkeypatch, tmp_path, "REIMPORT SRL",
            company_id=first["company_id"],
        )
        assert second["success"] is True
        assert second["company_id"] == first["company_id"]

        with sessions() as db:
            years = db.query(FinancialYear).all()
            assert len(years) == 1
            assert years[0].company_id == first["company_id"]
            assert db.query(BalanceSheet).count() == 1
            ta_after = years[0].balance_sheet.total_assets
        assert ta_after == _FIXTURE_TOTAL_ASSETS
    finally:
        engine.dispose()


def test_override_survives_save_and_clears_on_request(monkeypatch):
    """ce-override -> bulk save preserves it (when hydrated) -> explicit
    generate?clear_overrides=true wipes it back to baseline.

    Reconciliation vs the brief: bulk_upsert_assumptions (backend/app/services
    /assumptions_service.py) DELETES every BudgetAssumptions row for the
    scenario and re-INSERTS one row per dict in the request, reading each
    ce*_override field with `.get(field, None)` (lines ~169-200). It does NOT
    merge onto the existing row -- so a bulk-save request that omits
    ce01_override would silently NULL it out, and the brief's literal
    `assumptions` list (no ce01_override key) would fail the "bulk save
    preserves the override" assertion for the WRONG reason (naive payload,
    not a real bug).  CLAUDE.md documents the actual contract: "'Salva e
    Calcola' ... sends full hydrated rows, so overrides made on
    /forecast/income survive the save" -- confirmed in
    frontend/app/budget/page.tsx (~line 907), which rebuilds the assumptions
    payload from `a.ce01_override` (the CURRENT persisted value) before every
    bulk PUT. This test reproduces that hydration explicitly: the second
    bulk_upsert_assumptions call re-sends ce01_override=900000, mirroring
    what the real frontend does. That is the real, intentional behaviour
    (preservation is a caller responsibility, not a service-layer merge), so
    the test -- not the app -- was adjusted.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company_id, _ = seed_base_year(db, user_id=USER)
            scenario = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="ovr",
                                     base_year=2026, scenario_type="budget"),
                user_id=USER, db=db,
            )
            assumptions = [{"forecast_year": 2027, "revenue_growth_pct": 5,
                            "tax_rate": 24}]
            budget_scenarios.bulk_upsert_assumptions(
                company_id, scenario.id,
                request={"assumptions": assumptions, "auto_generate": True},
                user_id=USER, db=db,
            )
            (_, _, ce_baseline), = read_forecast_maps(db, scenario.id)
            baseline_revenue = ce_baseline["ce01_ricavi_vendite"]

            budget_scenarios.patch_ce_override(
                company_id, scenario.id,
                request={"overrides": [{"forecast_year": 2027,
                                        "field": "ce01_override",
                                        "value": 900000}]},
                user_id=USER, db=db,
            )
            (_, bs_o, ce_o), = read_forecast_maps(db, scenario.id)
            assert ce_o["ce01_ricavi_vendite"] == Decimal("900000.00")
            assert bs_o["_total_assets"] == bs_o["_total_liabilities"]

            # A hydrated bulk-save (re-sends the current override, as the
            # frontend does) must NOT drop it.
            assumptions_hydrated = [{"forecast_year": 2027, "revenue_growth_pct": 5,
                                     "tax_rate": 24, "ce01_override": 900000}]
            budget_scenarios.bulk_upsert_assumptions(
                company_id, scenario.id,
                request={"assumptions": assumptions_hydrated, "auto_generate": True},
                user_id=USER, db=db,
            )
            (_, _, ce_saved), = read_forecast_maps(db, scenario.id)
            assert ce_saved["ce01_ricavi_vendite"] == Decimal("900000.00")

            # clear esplicito: si torna ESATTAMENTE alla baseline
            budget_scenarios.generate_forecasts(
                company_id, scenario.id, clear_overrides=True, user_id=USER, db=db
            )
            (_, _, ce_cleared), = read_forecast_maps(db, scenario.id)
            assert ce_cleared["ce01_ricavi_vendite"] == baseline_revenue
    finally:
        engine.dispose()


def test_rettifica_then_reset_restores_the_original_snapshot(tmp_path, monkeypatch):
    engine, sessions = memory_sessions()
    try:
        imported = _import_pdf(sessions, monkeypatch, tmp_path, "RESET SRL")
        company_id = imported["company_id"]
        with sessions() as db:
            editable = financial_years.get_adjustable_financial_year(
                company_id, 2026, period_months=6, user_id=USER, db=db
            )
            original_bs = dict(editable.balance_sheet)
            original_is = dict(editable.income_statement)
            cash = Decimal(str(original_bs["sp09_disponibilita_liquide"]))

            financial_years.save_adjustments(
                company_id, 2026,
                AdjustmentsUpdate(
                    balance_sheet={
                        "sp09_disponibilita_liquide": cash + Decimal("700"),
                        "sp16_debiti_breve": Decimal(str(original_bs["sp16_debiti_breve"])) + 700,
                        "sp16a_debiti_banche_breve": Decimal(str(original_bs["sp16a_debiti_banche_breve"])) + 700,
                    },
                    income_statement={},
                    rettifiche_log=[RettificaEntry(
                        id="r1", edited_field="sp09_disponibilita_liquide",
                        edited_label="Cassa", edit_delta=700,
                        counterpart_field="sp16a_debiti_banche_breve",
                        counterpart_label="Banche", counterpart_delta=700,
                        explanation="temporanea", created_at="2026-07-21T10:00:00Z",
                    )],
                ),
                period_months=6, user_id=USER, db=db,
            )
            # reset: rimando lo snapshot originale con log vuoto
            after_reset = financial_years.save_adjustments(
                company_id, 2026,
                AdjustmentsUpdate(balance_sheet=original_bs,
                                  income_statement=original_is,
                                  rettifiche_log=[]),
                period_months=6, user_id=USER, db=db,
            )
            assert after_reset.rettifiche_log == []
            assert Decimal(str(after_reset.balance_sheet["sp09_disponibilita_liquide"])) == cash
            # lo snapshot immutabile e' sopravvissuto a entrambe le PUT
            assert Decimal(str(after_reset.original_balance_sheet["sp09_disponibilita_liquide"])) == cash
    finally:
        engine.dispose()


def test_promote_then_budget_chain_stays_quadrato(tmp_path, monkeypatch):
    """La catena che i clienti percorrono davvero: infrannuale 2026 -> promote ->
    budget 2027-2029 basato sull'anno promosso, poi ri-promozione con ipotesi
    diverse."""
    from database.models import FinancialYear

    engine, sessions = memory_sessions()
    try:
        imported = _import_pdf(sessions, monkeypatch, tmp_path, "CATENA SRL")
        company_id = imported["company_id"]
        with sessions() as db:
            infra = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="infra",
                                     base_year=2025, scenario_type="infrannuale",
                                     period_months=6),
                user_id=USER, db=db,
            )
            budget_scenarios.bulk_upsert_assumptions(
                company_id, infra.id,
                request={"assumptions": [{"forecast_year": 2026,
                                          "revenue_growth_pct": 3,
                                          "tax_rate": 24}],
                         "auto_generate": True},
                user_id=USER, db=db,
            )
            promoted = promote_projection_to_financial_year(db, infra.id)
            assert promoted["verification"]["exact_match"] is True

            budget = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(company_id=company_id, name="budget-su-promosso",
                                     base_year=2026, scenario_type="budget"),
                user_id=USER, db=db,
            )
            result = budget_scenarios.bulk_upsert_assumptions(
                company_id, budget.id,
                request={"assumptions": [
                    {"forecast_year": y, "revenue_growth_pct": 4, "tax_rate": 24}
                    for y in (2027, 2028, 2029)
                ], "auto_generate": True},
                user_id=USER, db=db,
            )
            assert result["forecast_generated"] is True, result["message"]
            for _, bs, _ in read_forecast_maps(db, budget.id):
                assert bs["_total_assets"] == bs["_total_liabilities"]

            # ri-promozione con ipotesi diverse: sostituisce, non duplica
            budget_scenarios.bulk_upsert_assumptions(
                company_id, infra.id,
                request={"assumptions": [{"forecast_year": 2026,
                                          "revenue_growth_pct": 8,
                                          "tax_rate": 24}],
                         "auto_generate": True},
                user_id=USER, db=db,
            )
            promote_projection_to_financial_year(db, infra.id)
            full_years = (
                db.query(FinancialYear)
                .filter(FinancialYear.company_id == company_id,
                        FinancialYear.year == 2026,
                        (FinancialYear.period_months == None)  # noqa: E711
                        | (FinancialYear.period_months == 12))
                .all()
            )
            assert len(full_years) == 1
    finally:
        engine.dispose()
