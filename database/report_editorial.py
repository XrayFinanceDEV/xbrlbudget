"""Versioned page commentary, separate from accounting and legacy narratives."""
from datetime import datetime

from sqlalchemy import Column, DateTime, DDL, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import relationship

from database.db import Base


class ReportEditorialState(Base):
    __tablename__ = "report_editorial_states"

    scenario_id = Column(Integer, ForeignKey("budget_scenarios.id", ondelete="CASCADE"), primary_key=True)
    revision = Column(Integer, nullable=False, default=0)
    plan = Column(JSON, nullable=True)
    source_hash = Column(String(64), nullable=False)
    body_hash = Column(String(64), nullable=False)
    render_signature = Column(String(64), nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    scenario = relationship("BudgetScenario", back_populates="editorial_state")
    notes = relationship("ReportEditorialNote", back_populates="state", cascade="all, delete-orphan")


class ReportEditorialNote(Base):
    __tablename__ = "report_editorial_notes"
    __table_args__ = (UniqueConstraint("scenario_id", "note_id", "plan_hash", name="uq_report_editorial_note_plan"),)

    id = Column(Integer, primary_key=True)
    scenario_id = Column(Integer, ForeignKey("report_editorial_states.scenario_id", ondelete="CASCADE"), nullable=False, index=True)
    note_id = Column(String(128), nullable=False)
    plan_hash = Column(String(64), nullable=False)
    source_hash = Column(String(64), nullable=False)
    content_ids = Column(JSON, nullable=False)
    text = Column(Text, nullable=False)
    provenance = Column(String(20), nullable=False)
    revision = Column(Integer, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    state = relationship("ReportEditorialState", back_populates="notes")


# Legacy SQLite connections do not enforce all foreign keys. These scoped
# triggers enforce editorial deletion without changing accounting FK behavior.
EDITORIAL_DELETE_TRIGGERS = (
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
for statement in EDITORIAL_DELETE_TRIGGERS:
    event.listen(ReportEditorialNote.__table__, "after_create", DDL(statement).execute_if(dialect="sqlite"))
