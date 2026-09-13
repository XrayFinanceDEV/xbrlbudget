"""Regression coverage for the additive M1-01 persistence foundation."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.schemas.budget import (
    BudgetAssumptionsCreate,
    BudgetScenario,
    BudgetScenarioCreate,
    NarrativeBlocks,
)
from backend.app.schemas.financial_year import FinancialYear, FinancialYearCreate
from database.db import Base
from database.models import BudgetAssumptions, BudgetScenario as BudgetScenarioModel, Company, FinancialYear as FinancialYearModel


ROOT = Path(__file__).resolve().parents[1]
MIGRATE_DB = ROOT / "migrate_db.py"
SOURCE_HASH = "a" * 64


def _create_legacy_database(path: Path) -> None:
    """Create only the pre-migration table shapes needed by migrate_db.py."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE companies (id INTEGER PRIMARY KEY);
        CREATE TABLE forecast_income_statements (id INTEGER PRIMARY KEY);
        CREATE TABLE income_statements (id INTEGER PRIMARY KEY);
        CREATE TABLE balance_sheets (id INTEGER PRIMARY KEY);
        CREATE TABLE financial_years (id INTEGER PRIMARY KEY);
        CREATE TABLE budget_scenarios (id INTEGER PRIMARY KEY);
        CREATE TABLE budget_assumptions (id INTEGER PRIMARY KEY);
        INSERT INTO financial_years (id) VALUES (1);
        INSERT INTO budget_scenarios (id) VALUES (1);
        INSERT INTO budget_assumptions (id) VALUES (1);
        """
    )
    conn.commit()
    conn.close()


def _run_migration(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MIGRATE_DB), str(path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_is_idempotent_and_leaves_legacy_values_unknown(tmp_path):
    database_path = tmp_path / "legacy.db"
    _create_legacy_database(database_path)

    _run_migration(database_path)
    second_run = _run_migration(database_path)
    assert "added 0 columns" in second_run.stdout

    conn = sqlite3.connect(database_path)
    financial_year_columns = {row[1] for row in conn.execute("PRAGMA table_info(financial_years)")}
    scenario_columns = {row[1] for row in conn.execute("PRAGMA table_info(budget_scenarios)")}
    assumption_columns = {row[1] for row in conn.execute("PRAGMA table_info(budget_assumptions)")}
    index_names = {row[1] for row in conn.execute("PRAGMA index_list(financial_years)")}

    assert {"promoted_from_scenario_id", "workflow_origin"} <= financial_year_columns
    assert {
        "extra_accounting_alerts",
        "extra_accounting_alerts_updated_at",
        "narrative_blocks",
        "narrative_blocks_updated_at",
        "narrative_source_hash",
    } <= scenario_columns
    assert "explicitly_supplied_fields" in assumption_columns
    assert "ix_financial_years_promoted_from_scenario_id" in index_names
    assert conn.execute(
        "SELECT promoted_from_scenario_id, workflow_origin FROM financial_years WHERE id = 1"
    ).fetchone() == (None, None)
    assert conn.execute(
        """SELECT extra_accounting_alerts, extra_accounting_alerts_updated_at,
                  narrative_blocks, narrative_blocks_updated_at, narrative_source_hash
           FROM budget_scenarios WHERE id = 1"""
    ).fetchone() == (None, None, None, None, None)
    assert conn.execute(
        "SELECT explicitly_supplied_fields FROM budget_assumptions WHERE id = 1"
    ).fetchone() == (None,)
    conn.close()


def test_orm_and_pydantic_round_trip_json_and_nullable_provenance(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'orm.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    narrative = {
        "schema_version": 1,
        "blocks": [{
            "id": "executive_summary",
            "text": "Sintesi",
            "origin": "user",
            "updated_at": "2026-09-13T12:00:00",
            "source_hash": SOURCE_HASH,
        }],
    }
    company = Company(name="Acme", sector=1)
    scenario = BudgetScenarioModel(
        company=company,
        name="Budget 2027",
        base_year=2026,
        workflow_type="bilancio",
        extra_accounting_alerts=["banche", "iva"],
        narrative_blocks=narrative,
        narrative_source_hash=SOURCE_HASH,
    )
    financial_year = FinancialYearModel(company=company, year=2026)
    assumptions = BudgetAssumptions(
        scenario=scenario,
        forecast_year=2027,
        explicitly_supplied_fields=["revenue_growth_pct", "tax_rate"],
    )
    session.add_all([financial_year, scenario, assumptions])
    session.commit()
    session.expire_all()

    persisted_scenario = session.get(BudgetScenarioModel, scenario.id)
    persisted_year = session.get(FinancialYearModel, financial_year.id)
    persisted_assumptions = session.get(BudgetAssumptions, assumptions.id)
    assert persisted_scenario.extra_accounting_alerts == ["banche", "iva"]
    assert persisted_scenario.narrative_blocks == narrative
    assert persisted_scenario.narrative_source_hash == SOURCE_HASH
    assert persisted_assumptions.explicitly_supplied_fields == ["revenue_growth_pct", "tax_rate"]
    assert persisted_year.promoted_from_scenario_id is None
    assert persisted_year.workflow_origin is None
    assert BudgetScenario.model_validate(persisted_scenario).narrative_blocks.blocks[0].id == "executive_summary"
    validated_year = FinancialYear.model_validate(persisted_year)
    assert validated_year.promoted_from_scenario_id is None
    assert validated_year.workflow_origin is None


def test_controlled_values_and_explicit_field_list_validation():
    scenario = BudgetScenarioCreate(
        company_id=1,
        name="Budget",
        base_year=2026,
        workflow_type="startup",
        extra_accounting_alerts=["retribuzioni", "inps"],
        narrative_blocks={
            "schema_version": 1,
            "blocks": [{
                "id": "risks_and_actions",
                "text": "Verificare le scadenze.",
                "origin": "ai",
                "updated_at": "2026-09-13T12:00:00",
                "source_hash": SOURCE_HASH,
            }],
        },
        narrative_source_hash=SOURCE_HASH,
    )
    assert scenario.extra_accounting_alerts == ["retribuzioni", "inps"]
    assert BudgetAssumptionsCreate(
        scenario_id=1,
        forecast_year=2027,
        explicitly_supplied_fields=["revenue_growth_pct"],
    ).explicitly_supplied_fields == ["revenue_growth_pct"]
    assert FinancialYearCreate(
        company_id=1, year=2026, workflow_origin="promoted_projection"
    ).workflow_origin == "promoted_projection"

    with pytest.raises(ValidationError):
        BudgetScenarioCreate(company_id=1, name="Budget", base_year=2026, workflow_type="unknown")
    with pytest.raises(ValidationError):
        FinancialYearCreate(company_id=1, year=2026, workflow_origin="unknown")
    with pytest.raises(ValidationError):
        BudgetScenarioCreate(
            company_id=1, name="Budget", base_year=2026, extra_accounting_alerts=["unknown"]
        )
    with pytest.raises(ValidationError):
        NarrativeBlocks.model_validate({
            "schema_version": 1,
            "blocks": [{
                "id": "unknown",
                "text": "Test",
                "origin": "unknown",
                "updated_at": "2026-09-13T12:00:00",
                "source_hash": SOURCE_HASH,
            }],
        })
    with pytest.raises(ValidationError):
        BudgetAssumptionsCreate(
            scenario_id=1,
            forecast_year=2027,
            explicitly_supplied_fields=["revenue_growth_pct", "revenue_growth_pct"],
        )
