"""M1-05A — domain rules of the final report: chain, rettifiche, chiusura.

Ownership: this file and ``backend/app/services/final_report_domain.py`` only.
The three workflows (infrannuale, bilancio, startup) are exercised through the
same persisted objects the rest of the app writes.
"""
import json
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import backend.app.main  # noqa: F401  — puts project root and backend/ on sys.path

from app.schemas.adjustments import RettificaEntry
from app.schemas.final_report import (
    AdjustmentEntry,
    Adjustments,
    ClosingValue,
    ExtraAccountingAlerts as ReportAlerts,
)
from app.services.final_report_domain import (
    ChainMatch,
    build_adjustments,
    build_closing_values,
    build_infrannual_closing,
    economic_entries,
    is_confirmed,
    net_effect,
    reconcile_adjustments,
    resolve_source_scenario,
    signed_deltas,
    unposted_mass,
)
from database.db import Base
from database.models import BudgetScenario, Company, FinancialYear


USER = "m1-05a-user"
ALERT_KEYS = ("retribuzioni", "fornitori", "banche", "inps", "inail", "riscossione", "iva")


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    writes = []

    def record(*args, **kwargs):
        writes.append(args[1] if len(args) > 1 else args[0])

    for hook in ("before_flush", "after_commit"):
        event.listen(session, hook, record)
    try:
        session.writes = writes  # type: ignore[attr-defined]
        session.stop_counting = writes.clear  # type: ignore[attr-defined]
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _company(db, name="M1-05A"):
    company = Company(name=name, sector=1, user_id=USER)
    db.add(company)
    db.flush()
    return company


def _scenario(db, company_id, **values):
    scenario = BudgetScenario(
        company_id=company_id,
        name=values.pop("name", "Scenario"),
        base_year=values.pop("base_year", 2026),
        **values,
    )
    db.add(scenario)
    db.flush()
    return scenario


def _annual_year(db, company_id, year, **values):
    financial_year = FinancialYear(company_id=company_id, year=year, period_months=None, **values)
    db.add(financial_year)
    db.flush()
    return financial_year


def _rettifica(idx=1, **overrides) -> RettificaEntry:
    values = dict(
        id=f"r{idx}",
        edited_field="sp09_disponibilita_liquide",
        edited_label="Disponibilità liquide",
        edit_delta=100.0,
        counterpart_field="ce01_ricavi_vendite",
        counterpart_label="Ricavi",
        counterpart_delta=-100.0,
        created_at="2026-09-01T10:00:00",
    )
    values.update(overrides)
    return RettificaEntry(**values)


def _confirm(**overrides) -> RettificaEntry:
    values = dict(
        id="confirm-2026", entry_type="confirm", edited_field="", counterpart_field="",
        edited_label="Rettifiche confermate", counterpart_label="",
        edit_delta=0.0, counterpart_delta=0.0,
    )
    values.update(overrides)
    return _rettifica(**values)


# ---------------------------------------------------------------------------
# 1. Catena: sorgente esplicito e fallback legacy
# ---------------------------------------------------------------------------
def test_explicit_source_is_resolved_without_touching_the_database(db_session):
    company = _company(db_session)
    source = _scenario(db_session, company.id, name="Infrannuale settembre",
                       scenario_type="infrannuale", base_year=2025, period_months=9,
                       workflow_type="infrannuale")
    budget = _scenario(db_session, company.id, name="Budget 2026", scenario_type="budget",
                       base_year=2026, workflow_type="infrannuale", source_scenario_id=source.id)

    db_session.stop_counting()
    resolution = resolve_source_scenario(db_session, budget)

    assert resolution.match is ChainMatch.EXPLICIT
    assert resolution.source_scenario_id == source.id
    assert resolution.finalizable and not resolution.legacy_inferred
    assert resolution.diagnostics == ()
    assert db_session.writes == []


def test_unique_legacy_promotion_marker_is_inferred_and_declared(db_session):
    company = _company(db_session)
    source = _scenario(db_session, company.id, name="Infrannuale", scenario_type="infrannuale",
                       base_year=2025, period_months=9)
    _annual_year(db_session, company.id, 2026, promoted_from_scenario_id=source.id,
                 workflow_origin="promoted_projection")
    budget = _scenario(db_session, company.id, name="Budget legacy", scenario_type="budget",
                       base_year=2026, workflow_type=None, source_scenario_id=None)

    db_session.stop_counting()
    resolution = resolve_source_scenario(db_session, budget)

    assert resolution.match is ChainMatch.UNIQUE_INFERRED and resolution.legacy_inferred
    assert resolution.source_scenario_id == source.id
    assert [d.code for d in resolution.diagnostics] == ["legacy_chain_inferred"]
    assert all(d.severity == "warning" for d in resolution.diagnostics)
    assert budget.source_scenario_id is None  # declared, never repaired
    assert db_session.writes == []


def test_fallback_by_base_year_window_when_no_promotion_marker(db_session):
    company = _company(db_session)
    source = _scenario(db_session, company.id, name="Infrannuale", scenario_type="infrannuale",
                       base_year=2025, period_months=6)
    budget = _scenario(db_session, company.id, name="Budget legacy", base_year=2026,
                       scenario_type="budget", workflow_type=None)

    resolution = resolve_source_scenario(db_session, budget)

    assert resolution.match is ChainMatch.UNIQUE_INFERRED
    assert resolution.source_scenario is source


def test_multiple_compatible_origins_are_refused_not_guessed(db_session):
    company = _company(db_session)
    first = _scenario(db_session, company.id, name="Infrannuale A", scenario_type="infrannuale",
                      base_year=2025, period_months=6)
    second = _scenario(db_session, company.id, name="Infrannuale B", scenario_type="infrannuale",
                       base_year=2025, period_months=9)
    budget = _scenario(db_session, company.id, name="Budget legacy", base_year=2026,
                       scenario_type="budget", workflow_type=None)

    db_session.stop_counting()
    resolution = resolve_source_scenario(db_session, budget)

    assert resolution.match is ChainMatch.AMBIGUOUS
    assert resolution.source_scenario is None and resolution.source_scenario_id is None
    assert set(resolution.candidate_ids) == {first.id, second.id}
    assert not resolution.finalizable
    assert [d.severity for d in resolution.diagnostics] == ["error"]
    assert db_session.writes == []


def test_bilancio_and_startup_have_no_legacy_parent_to_infer(db_session):
    company = _company(db_session)
    _scenario(db_session, company.id, name="Infrannuale", scenario_type="infrannuale",
              base_year=2025, period_months=9)
    bilancio = _scenario(db_session, company.id, name="Budget 2026 da bilancio",
                         base_year=2026, workflow_type="bilancio")
    startup = _scenario(db_session, company.id, name="Piano startup", base_year=2026,
                        workflow_type="startup")
    _annual_year(db_session, company.id, 2026)

    db_session.stop_counting()
    assert resolve_source_scenario(db_session, bilancio).match is ChainMatch.NONE
    assert resolve_source_scenario(db_session, startup).match is ChainMatch.NONE
    assert db_session.writes == []


def test_infrannuale_scenario_is_its_own_practice_head(db_session):
    company = _company(db_session)
    source = _scenario(db_session, company.id, name="Infrannuale", scenario_type="infrannuale",
                       base_year=2025, period_months=9, workflow_type="infrannuale")

    resolution = resolve_source_scenario(db_session, source)

    assert resolution.match is ChainMatch.NONE
    assert resolution.finalizable and not resolution.legacy_inferred
    assert resolution.diagnostics == ()  # a head has nothing to warn about


def test_dangling_explicit_link_is_broken_and_not_finalizable(db_session):
    company = _company(db_session)
    other = _company(db_session, name="Altra")
    foreign = _scenario(db_session, other.id, name="Altrui", scenario_type="infrannuale",
                        base_year=2025, period_months=9)
    mine = _scenario(db_session, company.id, name="Budget", base_year=2026,
                     workflow_type="infrannuale", source_scenario_id=foreign.id)

    resolution = resolve_source_scenario(db_session, mine)

    assert resolution.match is ChainMatch.BROKEN
    assert not resolution.finalizable and resolution.source_scenario_id is None
    assert [d.code for d in resolution.diagnostics] == ["chain_source_missing"]

    missing = _scenario(db_session, company.id, name="Budget monco", base_year=2026,
                        workflow_type="infrannuale", source_scenario_id=999999)
    assert resolve_source_scenario(db_session, missing).match is ChainMatch.BROKEN


def test_explicit_link_rejects_incompatible_workflow_source_year_and_marker(db_session):
    company = _company(db_session)
    compatible = _scenario(
        db_session, company.id, name="Infrannuale 2025", scenario_type="infrannuale",
        base_year=2025, period_months=9, workflow_type="infrannuale",
    )
    incompatible_year = _scenario(
        db_session, company.id, name="Infrannuale 2024", scenario_type="infrannuale",
        base_year=2024, period_months=9, workflow_type="infrannuale",
    )
    incompatible_origin_workflow = _scenario(
        db_session, company.id, name="Infrannuale con workflow errato", scenario_type="infrannuale",
        base_year=2025, period_months=9, workflow_type="bilancio",
    )
    not_an_origin = _scenario(db_session, company.id, name="Budget ordinario", base_year=2025)

    wrong_workflow = _scenario(
        db_session, company.id, name="Workflow bilancio", base_year=2026,
        workflow_type="bilancio", source_scenario_id=compatible.id,
    )
    wrong_year = _scenario(
        db_session, company.id, name="Anno incoerente", base_year=2026,
        workflow_type="infrannuale", source_scenario_id=incompatible_year.id,
    )
    wrong_type = _scenario(
        db_session, company.id, name="Tipo incoerente", base_year=2026,
        workflow_type="infrannuale", source_scenario_id=not_an_origin.id,
    )
    wrong_origin_workflow = _scenario(
        db_session, company.id, name="Workflow sorgente incoerente", base_year=2026,
        workflow_type="infrannuale", source_scenario_id=incompatible_origin_workflow.id,
    )
    marker_origin = _scenario(
        db_session, company.id, name="Infrannuale 2026 A", scenario_type="infrannuale",
        base_year=2026, period_months=9, workflow_type="infrannuale",
    )
    explicit_other_origin = _scenario(
        db_session, company.id, name="Infrannuale 2026 B", scenario_type="infrannuale",
        base_year=2026, period_months=6, workflow_type="infrannuale",
    )
    _annual_year(
        db_session, company.id, 2027, promoted_from_scenario_id=marker_origin.id,
        workflow_origin="promoted_projection",
    )
    wrong_marker = _scenario(
        db_session, company.id, name="Marcatore incoerente", base_year=2027,
        workflow_type="infrannuale", source_scenario_id=explicit_other_origin.id,
    )

    db_session.stop_counting()
    for budget in (wrong_workflow, wrong_year, wrong_type, wrong_origin_workflow, wrong_marker):
        resolution = resolve_source_scenario(db_session, budget)
        assert resolution.match is ChainMatch.BROKEN
        assert not resolution.finalizable
        assert [diagnostic.code for diagnostic in resolution.diagnostics] == ["chain_source_incompatible"]
    assert db_session.writes == []


def test_promotion_marker_pointing_at_a_non_infrannuale_scenario_invents_nothing(db_session):
    company = _company(db_session)
    wrong = _scenario(db_session, company.id, name="Altro budget", base_year=2024)
    _annual_year(db_session, company.id, 2026, promoted_from_scenario_id=wrong.id,
                 workflow_origin="promoted_projection")
    budget = _scenario(db_session, company.id, name="Budget", base_year=2026)

    db_session.stop_counting()
    resolution = resolve_source_scenario(db_session, budget)

    assert resolution.match is ChainMatch.BROKEN
    assert not resolution.finalizable and resolution.source_scenario is None
    assert [diagnostic.code for diagnostic in resolution.diagnostics] == ["chain_source_incompatible"]
    assert [diagnostic.severity for diagnostic in resolution.diagnostics] == ["error"]
    assert budget.source_scenario_id is None
    assert db_session.writes == []


def test_legacy_marker_outside_annualization_window_is_not_replaced_or_written(db_session):
    company = _company(db_session)
    stale_marker = _scenario(
        db_session, company.id, name="Infrannuale 2024", scenario_type="infrannuale",
        base_year=2024, period_months=9,
    )
    _scenario(
        db_session, company.id, name="Compatibile ma non marcato", scenario_type="infrannuale",
        base_year=2025, period_months=9,
    )
    _annual_year(
        db_session, company.id, 2026, promoted_from_scenario_id=stale_marker.id,
        workflow_origin="promoted_projection",
    )
    budget = _scenario(db_session, company.id, name="Budget legacy", base_year=2026)

    db_session.stop_counting()
    resolution = resolve_source_scenario(db_session, budget)

    assert resolution.match is ChainMatch.BROKEN
    assert not resolution.finalizable and resolution.source_scenario is None
    assert [diagnostic.code for diagnostic in resolution.diagnostics] == ["chain_source_incompatible"]
    assert [diagnostic.severity for diagnostic in resolution.diagnostics] == ["error"]
    assert budget.source_scenario_id is None
    assert db_session.writes == []


# ---------------------------------------------------------------------------
# 2. Rettifiche: le conferme non sono movimenti economici
# ---------------------------------------------------------------------------
def test_confirm_entries_leave_the_economic_rows_but_keep_the_state():
    log = [_rettifica(1), _rettifica(2), _confirm()]

    assert [entry.id for entry in economic_entries(log)] == ["r1", "r2"]
    assert is_confirmed(log) is True
    assert is_confirmed([_rettifica(1)]) is False


def test_confirm_marker_never_counts_in_the_net_effect():
    balanced = [_rettifica(1)]
    assert net_effect(balanced) == Decimal("0")
    single_entry = [_rettifica(1, counterpart_field="_correzione_import", counterpart_label="Import",
                               counterpart_delta=0.0)]
    assert net_effect(single_entry) == Decimal("100.0")
    # A marker carrying a stray non-zero delta would move the total for nothing:
    # what keeps it out is the filter, not the fact that its delta is zero.
    polluted = [_rettifica(1), _confirm(edit_delta=999.0, counterpart_delta=-999.0)]
    assert net_effect(polluted) == net_effect([_rettifica(1)])


def test_build_adjustments_produces_the_contract_block():
    block = build_adjustments([_rettifica(1), _confirm()])

    assert isinstance(block, Adjustments)
    assert block.confirmed is True
    assert [entry.id for entry in block.entries] == ["r1"]
    assert all(isinstance(entry, AdjustmentEntry) for entry in block.entries)
    assert block.net_effect == Decimal("0")
    assert isinstance(block.net_effect, Decimal)
    assert block.model_dump(mode="json")["entries"][0]["edit_delta"] == "100.0"


def test_signed_deltas_carry_the_accounting_sign_and_skip_markers():
    deltas = signed_deltas([_rettifica(1), _confirm(), _rettifica(2, edit_delta=-250.5,
                                                                  counterpart_delta=250.5)])
    assert deltas == {
        "sp09_disponibilita_liquide": Decimal("-150.5"),
        "ce01_ricavi_vendite": Decimal("150.5"),
    }
    assert all(isinstance(value, Decimal) for value in deltas.values())


def test_reconciliation_holds_for_negative_movements_and_rejects_mismatches():
    entries = [_rettifica(1, edit_delta=-400.0, counterpart_delta=400.0)]
    before = {"sp09_disponibilita_liquide": Decimal("1000.00"), "ce01_ricavi_vendite": Decimal("50.00")}
    after = {"sp09_disponibilita_liquide": Decimal("600.00"), "ce01_ricavi_vendite": Decimal("450.00")}

    result = reconcile_adjustments(before, after, entries)
    assert result.balanced and result.diagnostics == ()
    assert result.adjustments["sp09_disponibilita_liquide"] == Decimal("-400.0")

    # 100 € e non 1 €: fino a 2 € uno scarto è arrotondamento e si dichiara senza bloccare
    # (vedi test_ambienta_i_riallineamenti_si_dichiarano_e_non_bloccano).
    drifted = dict(after, sp09_disponibilita_liquide=Decimal("700.00"))
    broken = reconcile_adjustments(before, drifted, entries)
    assert not broken.balanced
    assert broken.differences["sp09_disponibilita_liquide"] == Decimal("100.00")
    assert [d.severity for d in broken.diagnostics] == ["error"]
    assert "sp09_disponibilita_liquide" in broken.diagnostics[0].message

    confirm_only = reconcile_adjustments(before, after, [_confirm()])
    assert not confirm_only.balanced  # confirmation is not an economic journal row
    assert confirm_only.adjustments == {}
    assert reconcile_adjustments(before, before, [_confirm()]).balanced is True


def test_reconciliation_covers_snapshot_union_and_aggregates_duplicate_split_rows():
    entries = [
        _rettifica(1, edit_delta=100.0, counterpart_delta=-60.0),
        _rettifica(2, edit_delta=0.0, counterpart_delta=-40.0),  # UI split row
        _rettifica(3, edited_field="sp09_disponibilita_liquide", edit_delta=25.0,
                   counterpart_field="sp16g_altri_debiti_breve", counterpart_delta=-25.0),
    ]
    before = {
        "sp09_disponibilita_liquide": Decimal("0"),
        "ce01_ricavi_vendite": Decimal("0"),
        "sp16g_altri_debiti_breve": Decimal("0"),
        "sp99_only_before": Decimal("20"),
    }
    after = {
        "sp09_disponibilita_liquide": Decimal("125"),
        "ce01_ricavi_vendite": Decimal("-100"),
        "sp16g_altri_debiti_breve": Decimal("-25"),
        "ce99_only_after": Decimal("7"),
    }

    result = reconcile_adjustments(before, after, entries)

    assert result.adjustments == {
        "sp09_disponibilita_liquide": Decimal("125.0"),
        "ce01_ricavi_vendite": Decimal("-100.0"),
        "sp16g_altri_debiti_breve": Decimal("-25.0"),
    }
    assert not result.balanced
    assert result.differences == {
        "ce99_only_after": Decimal("7"),
        "sp99_only_before": Decimal("-20"),
    }
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["adjustments_unreconciled"]


# ---------------------------------------------------------------------------
# 3. Chiusura infrannuale e alert
# ---------------------------------------------------------------------------
def test_closing_keeps_every_notione_distinto():
    [row] = build_closing_values([{
        "code": "ce01_ricavi_vendite", "label": "Ricavi", "observed": Decimal("900.00"),
        "comparable": None, "automatic": Decimal("1200.00"), "override": None,
    }])
    assert isinstance(row, ClosingValue)
    assert (row.observed, row.comparable, row.automatic, row.override) == (
        Decimal("900.00"), None, Decimal("1200.00"), None,
    )
    assert row.closing_used == Decimal("1200.00")


def test_override_wins_and_a_forced_zero_is_not_an_absence():
    [zeroed] = build_closing_values([{
        "code": "ce01_ricavi_vendite", "label": "Ricavi", "observed": Decimal("900.00"),
        "comparable": Decimal("870.00"), "automatic": Decimal("1200.00"), "override": Decimal("0.00"),
    }])
    assert zeroed.closing_used == Decimal("0.00")
    assert zeroed.automatic == Decimal("1200.00")  # the estimate stays visible
    assert zeroed.comparable == Decimal("870.00")  # comparable is never "used"

    [negative] = build_closing_values([{
        "code": "ce12_oneri_diversi", "label": "Oneri diversi", "observed": Decimal("-30.00"),
    }])
    assert negative.closing_used == Decimal("-30.00")
    assert (negative.comparable, negative.automatic, negative.override) == (None, None, None)

    with pytest.raises(ValueError, match="nessun valore"):
        build_closing_values([{"code": "sp09_disponibilita_liquide", "label": "Cassa"}])


def test_infrannual_closing_block_matches_the_contract_fixture():
    block = build_infrannual_closing(
        period_end=date(2026, 9, 30),
        rows=[{"code": "ce01_ricavi_vendite", "label": "Ricavi", "observed": "900.00",
               "automatic": "1200.00"}],
        alerts={"retribuzioni": True, "bogus": "ignored"},
    )
    assert isinstance(block.extra_accounting_alerts, ReportAlerts)
    assert block.model_dump(mode="json")["period_end"] == "2026-09-30"
    assert block.values[0].closing_used == Decimal("1200.00")

    with pytest.raises(ValueError, match="almeno una voce"):
        build_infrannual_closing(period_end="2026-09-30", rows=[])


@pytest.mark.parametrize("raw", [None, {}, {"retribuzioni": None, "inps": True, "sconosciuto": True},
                                 "non-json", {"iva": 1}])
def test_alert_map_is_always_the_seven_contract_booleans(raw):
    alerts = build_infrannual_closing(
        period_end=date(2026, 12, 31),
        rows=[{"code": "ce01_ricavi_vendite", "label": "Ricavi", "observed": "1.00"}],
        alerts=raw,
    ).extra_accounting_alerts
    dumped = alerts.model_dump()
    assert tuple(dumped) == ALERT_KEYS
    assert all(isinstance(value, bool) for value in dumped.values())
    expected = isinstance(raw, dict) and raw.get("inps") is True
    assert dumped["inps"] is expected and dumped["retribuzioni"] is False
    assert dumped["iva"] is False  # a truthy non-bool is not a declared alert


def test_the_persisted_json_log_reads_like_the_model_one():
    """``rettifiche_log`` is a JSON column: the dict shape is the real read path."""
    log = json.loads(json.dumps([_rettifica(1).model_dump(), _confirm().model_dump()]))

    block = build_adjustments(log)
    assert block.confirmed is True and [e.id for e in block.entries] == ["r1"]
    assert block.net_effect == Decimal("0")
    assert signed_deltas(log) == {"sp09_disponibilita_liquide": Decimal("100.0"),
                                 "ce01_ricavi_vendite": Decimal("-100.0")}


def test_resolution_does_not_flush_somebody_else_s_pending_work(db_session):
    """A read-model resolver must never push a dirty session to SQLite."""
    company = _company(db_session)
    budget = _scenario(db_session, company.id, name="Budget", base_year=2026, workflow_type="bilancio")
    budget.description = "modifica ancora in corso"
    db_session.stop_counting()

    resolve_source_scenario(db_session, budget)

    assert db_session.writes == []


def test_a_single_entry_correction_is_declared_not_absorbed():
    """``_correzione_import`` is a label: mass parked there must stay visible."""
    single = [_rettifica(1, counterpart_field="_correzione_import", counterpart_label="Import")]
    assert unposted_mass(single) == Decimal("-100.0")
    assert signed_deltas(single) == {"sp09_disponibilita_liquide": Decimal("100.0")}

    before = {"sp09_disponibilita_liquide": Decimal("10.00")}
    after = {"sp09_disponibilita_liquide": Decimal("110.00")}
    result = reconcile_adjustments(before, after, single)
    assert result.balanced
    assert [d.code for d in result.diagnostics] == ["adjustments_unposted_mass"]
    assert result.unposted == Decimal("-100.0")


def test_real_correggi_import_writer_shape_declares_its_edit_mass():
    """The UI writer stores the one-sided mass in ``edit_delta``, not the sentinel."""
    writer_entry = {
        "id": "ui-correggi-import",
        "edited_field": "sp09_disponibilita_liquide",
        "edited_label": "Disponibilità liquide",
        "edit_delta": 75,
        "counterpart_field": "_correzione_import",
        "counterpart_label": "Correzione importazione",
        "counterpart_delta": 0,
        "explanation": "Correzione dato importato",
        "created_at": "2026-09-01T10:00:00",
    }

    assert signed_deltas([writer_entry]) == {"sp09_disponibilita_liquide": Decimal("75")}
    assert unposted_mass([writer_entry]) == Decimal("75")
    result = reconcile_adjustments(
        {"sp09_disponibilita_liquide": Decimal("10")},
        {"sp09_disponibilita_liquide": Decimal("85")},
        [writer_entry],
    )
    assert result.balanced and result.unposted == Decimal("75")
    assert [diagnostic.code for diagnostic in result.diagnostics] == ["adjustments_unposted_mass"]


# ---------------------------------------------------------------------------
# AMBIENTA, 2026-09-17: «Documento bloccato — La riconciliazione rettifiche non quadra: ce08 100000.22,
# ce08b 0.03000000003, sp05 -214.55, sp06 63000.00, sp06g 41.00, sp07 45000.00, sp07g -3825.00,
# sp13 -6998.54, sp16 255000.24». Nove «differenze», nessuna delle quali era un movimento non spiegato.
# ---------------------------------------------------------------------------
def _ambienta_in_piccolo():
    """La stessa forma del giornale reale del 6M 2026, in scala.

    - una rettifica su un dettaglio (`ce08b`), registrata in virgola mobile dal client;
    - l'import aveva i dettagli di `sp07` incoerenti col totale di 30, e il salvataggio li ha riallineati;
    - l'import aveva `sp13` a 1,68 dall'utile del CE, e il salvataggio lo ha ricalcolato;
    - `ce08b` si è mosso di 3 centesimi più di quanto dice il giornale.
    """
    entries = [_rettifica(1, edited_field="ce08b_salari_stipendi", edit_delta=100.21999999997,
                          counterpart_field="sp16f_debiti_previdenza_breve", counterpart_delta=100.21999999997)]
    before = {
        "ce01_ricavi_vendite": Decimal("2000.00"), "ce08_costi_personale": Decimal("1000.00"),
        "ce08b_salari_stipendi": Decimal("1000.00"),
        "sp16_debiti_breve": Decimal("500.00"), "sp16f_debiti_previdenza_breve": Decimal("500.00"),
        "sp07_crediti_lungo": Decimal("100.00"), "sp07e_crediti_tributari_lungo": Decimal("100.00"),
        "sp07g_crediti_altri_lungo": Decimal("30.00"),
        "sp13_utile_perdita": Decimal("998.32"),
    }
    after = dict(before, **{
        "ce08_costi_personale": Decimal("1100.25"), "ce08b_salari_stipendi": Decimal("1100.25"),
        "sp16_debiti_breve": Decimal("600.22"), "sp16f_debiti_previdenza_breve": Decimal("600.22"),
        "sp07g_crediti_altri_lungo": Decimal("0.00"),
        "sp13_utile_perdita": Decimal("899.75"),
    })
    return entries, before, after


def test_ambienta_i_riallineamenti_si_dichiarano_e_non_bloccano():
    entries, before, after = _ambienta_in_piccolo()
    result = reconcile_adjustments(before, after, entries)

    # Nessun blocco: un totale si ricava dai suoi dettagli, non si confronta con un giornale che
    # per costruzione non lo nomina mai.
    assert result.balanced, result.differences
    codici = [d.code for d in result.diagnostics]
    assert "adjustments_unreconciled" not in codici
    # I riallineamenti e gli arrotondamenti dichiarati appartengono alla storia
    # dell'import: restano nelle Fonti senza tenere il report in «Bozza».
    gravita = {d.code: d.severity for d in result.diagnostics}
    assert gravita["adjustments_details_realigned"] == "info"
    assert gravita["adjustments_profit_realigned"] == "info"
    assert gravita["adjustments_rounding"] == "info"

    per_codice = {d.code: d.message for d in result.diagnostics}
    # I dettagli riallineati al totale: dichiarati, con l'importo in italiano.
    assert "sp07g_crediti_altri_lungo" in per_codice["adjustments_details_realigned"]
    assert "-30,00" in per_codice["adjustments_details_realigned"]
    # L'utile ricalcolato dal CE: lo scarto che l'import portava.
    assert "1,68" in per_codice["adjustments_profit_realigned"]
    # I 3 centesimi: dichiarati come arrotondamento, sul dettaglio e non anche sul suo totale.
    assert "ce08b_salari_stipendi" in per_codice["adjustments_rounding"]
    assert "0,03" in per_codice["adjustments_rounding"]
    assert "ce08_costi_personale" not in per_codice["adjustments_rounding"]


def test_tredici_centesimi_di_cassa_sono_informativi_ma_oltre_soglia_blocca():
    campo = "sp09_disponibilita_liquide"
    before = {campo: Decimal("1000.00")}
    piccolo = reconcile_adjustments(before, {campo: Decimal("999.87")}, [_confirm()])
    assert piccolo.balanced
    assert piccolo.differences == {}
    assert [(d.code, d.severity) for d in piccolo.diagnostics] == [("adjustments_rounding", "info")]
    assert "-0,13" in piccolo.diagnostics[0].message

    grande = reconcile_adjustments(before, {campo: Decimal("997.99")}, [_confirm()])
    assert not grande.balanced
    assert grande.differences[campo] == Decimal("-2.01")
    assert [(d.code, d.severity) for d in grande.diagnostics] == [("adjustments_unreconciled", "error")]


def test_un_totale_che_si_muove_senza_rettifica_blocca_ancora():
    entries, before, after = _ambienta_in_piccolo()
    # 100 € di debiti comparsi su un dettaglio senza alcuna riga di giornale.
    drifted = dict(after, sp16_debiti_breve=Decimal("700.22"), sp16g_altri_debiti_breve=Decimal("100.00"))
    result = reconcile_adjustments(before, drifted, entries)
    assert not result.balanced
    assert [d.severity for d in result.diagnostics if d.code == "adjustments_unreconciled"] == ["error"]
    assert "sp16g_altri_debiti_breve" in result.differences


def test_la_massa_non_registrata_si_legge_in_euro():
    """«-214.77999999998836 movimentati…»: la virgola mobile del client non arriva a schermo."""
    entries = [_rettifica(1, edited_field="sp05a_materie_prime", edit_delta=-215.54999999998836,
                          counterpart_field="_correzione_import", counterpart_delta=0.0)]
    result = reconcile_adjustments({"sp05a_materie_prime": Decimal("500")},
                                   {"sp05a_materie_prime": Decimal("284.45")}, entries)
    messaggio = [d.message for d in result.diagnostics if d.code == "adjustments_unposted_mass"][0]
    assert "-215,55" in messaggio, messaggio
    # La partita singola è il modo previsto per correggere un import (proprietario, 2026-09-17: «la
    # scrittura è senza contropartita ma è così che è stata pensata»): il testo la nomina, non la
    # presenta come un errore di registrazione.
    assert "Correggi Import" in messaggio
    assert "non è stata registrata" not in messaggio
    # «Correggi Import» in partita singola è uno dei tre modi previsti delle Rettifiche: dichiararlo
    # sì, tenere il documento in bozza per averlo usato no.
    assert [d.severity for d in result.diagnostics if d.code == "adjustments_unposted_mass"] == ["info"]
