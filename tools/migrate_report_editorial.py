"""Add only editorial tables; existing accounting tables and rows are untouched."""
from pathlib import Path
import sqlite3
import sys


DDL = (
    """CREATE TABLE IF NOT EXISTS report_editorial_states (
        scenario_id INTEGER PRIMARY KEY REFERENCES budget_scenarios(id) ON DELETE CASCADE,
        revision INTEGER NOT NULL DEFAULT 0, plan JSON,
        source_hash VARCHAR(64) NOT NULL, body_hash VARCHAR(64) NOT NULL,
        render_signature VARCHAR(64) NOT NULL, updated_at DATETIME NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS report_editorial_notes (
        id INTEGER PRIMARY KEY,
        scenario_id INTEGER NOT NULL REFERENCES report_editorial_states(scenario_id) ON DELETE CASCADE,
        note_id VARCHAR(128) NOT NULL, plan_hash VARCHAR(64) NOT NULL,
        source_hash VARCHAR(64) NOT NULL, content_ids JSON NOT NULL,
        text TEXT NOT NULL, provenance VARCHAR(20) NOT NULL,
        revision INTEGER NOT NULL, updated_at DATETIME NOT NULL,
        CONSTRAINT uq_report_editorial_note_plan UNIQUE(scenario_id, note_id, plan_hash)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_report_editorial_notes_scenario_id ON report_editorial_notes(scenario_id)",
    """CREATE TRIGGER IF NOT EXISTS delete_scenario_editorial_history
       AFTER DELETE ON budget_scenarios BEGIN
         DELETE FROM report_editorial_notes WHERE scenario_id = OLD.id;
         DELETE FROM report_editorial_states WHERE scenario_id = OLD.id;
       END""",
    """CREATE TRIGGER IF NOT EXISTS delete_editorial_state_history
       AFTER DELETE ON report_editorial_states BEGIN
         DELETE FROM report_editorial_notes WHERE scenario_id = OLD.scenario_id;
       END""",
)


def migrate(database: Path):
    # mode=rw prevents accidentally creating an empty accounting database.
    with sqlite3.connect(database.resolve().as_uri() + "?mode=rw", uri=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='budget_scenarios'").fetchone():
            raise ValueError("Il database deve contenere budget_scenarios.")
        for statement in DDL:
            connection.execute(statement)


if __name__ == "__main__":
    migrate(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "financial_analysis.db")
    print("Tabelle editoriali disponibili; dati di bilancio invariati.")
