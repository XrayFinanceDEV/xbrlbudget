"""Editorial history is additive, isolated, and deleted with its scenario."""
from datetime import datetime
from pathlib import Path
import sqlite3

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.db import Base
from database.models import BudgetScenario, Company
from database.report_editorial import ReportEditorialNote, ReportEditorialState
from tools.migrate_report_editorial import migrate
from app.schemas.editorial_notes import GenerateEditorialNotesRequest, SaveEditorialNotesRequest


def test_additive_migration_is_idempotent_preserves_accounting_and_manual_prose(tmp_path):
    database = tmp_path / "data.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE budget_scenarios(id INTEGER PRIMARY KEY, narrative_blocks TEXT)")
        db.execute("INSERT INTO budget_scenarios VALUES (1, ?)", ('{"summary":"Testo originale"}',))
        db.execute("CREATE TABLE income_statements(id INTEGER PRIMARY KEY, revenue TEXT)")
        db.execute("INSERT INTO income_statements VALUES(1,'9007199254740993.12')")
    migrate(database)
    migrate(database)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT * FROM budget_scenarios").fetchall() == [(1, '{"summary":"Testo originale"}')]
        assert db.execute("SELECT * FROM income_statements").fetchall() == [(1, '9007199254740993.12')]
        assert db.execute("SELECT count(*) FROM report_editorial_notes").fetchone() == (0,)
        assert db.execute("PRAGMA table_info(budget_scenarios)").fetchall()[1][1] == "narrative_blocks"


def test_migration_does_not_create_missing_database(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        migrate(missing)
    assert not missing.exists()


@pytest.mark.parametrize("parent", ["budget_scenarios", "report_editorial_states"])
def test_direct_sql_delete_cleans_editorial_history_with_legacy_fk_settings(tmp_path, parent):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE budget_scenarios(id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO budget_scenarios VALUES(1)")
    migrate(database)
    with sqlite3.connect(database) as db:
        assert db.execute("PRAGMA foreign_keys").fetchone() == (0,)
        db.execute("INSERT INTO report_editorial_states VALUES(1,1,NULL,?,?,?,?)", ("a" * 64, "b" * 64, "c" * 64, "2026-09-15"))
        db.execute("INSERT INTO report_editorial_notes VALUES(1,1,'note:x',?,?,?,?,'user',1,?)", ("d" * 64, "a" * 64, '["cover"]', "Manuale", "2026-09-15"))
        db.execute(f"DELETE FROM {parent}")
        assert db.execute("SELECT count(*) FROM report_editorial_states").fetchone() == (0,)
        assert db.execute("SELECT count(*) FROM report_editorial_notes").fetchone() == (0,)


def test_orm_company_deletion_removes_all_editorial_history():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(name="Test", sector=1, user_id="owner")
        scenario = BudgetScenario(name="Budget", base_year=2026)
        company.budget_scenarios.append(scenario)
        state = ReportEditorialState(source_hash="a" * 64, body_hash="b" * 64, render_signature="c" * 64)
        scenario.editorial_state = state
        state.notes.append(ReportEditorialNote(note_id="note:x", plan_hash="d" * 64, source_hash="a" * 64,
            content_ids=["cover"], text="Commento manuale", provenance="user", revision=1, updated_at=datetime.utcnow()))
        db.add(company)
        db.commit()
        assert db.query(ReportEditorialNote).count() == 1
        db.delete(company)
        db.commit()
        assert db.query(ReportEditorialState).count() == 0
        assert db.query(ReportEditorialNote).count() == 0
    engine.dispose()


@pytest.mark.parametrize("model", [SaveEditorialNotesRequest, GenerateEditorialNotesRequest])
def test_revision_contract_rejects_coercion_and_duplicate_page_ids(model):
    note = {"id": "note:x", "revision": 0}
    if model is SaveEditorialNotesRequest:
        note["text"] = "Nota"
    payload = dict(source_hash="a" * 64, plan_hash="b" * 64, expected_revision=0, notes=[note])
    model.model_validate(payload)
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "expected_revision": "0"})
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "notes": [note, note]})
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "client_context": "untrusted facts"})
