"""
Database connection and session management
"""
import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Use absolute path for database to ensure all apps use the same database
# Database is located in project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT.endswith('/database') or PROJECT_ROOT.endswith('\\database'):
    PROJECT_ROOT = os.path.dirname(PROJECT_ROOT)

DATABASE_PATH = os.environ.get('DATABASE_PATH') or os.path.join(PROJECT_ROOT, "financial_analysis.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Create SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False  # Set to True for SQL debugging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


def get_db() -> Session:
    """
    Get database session

    Usage:
        with get_db() as db:
            # perform database operations
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create all tables
    """
    from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement, UploadedFile
    Base.metadata.create_all(bind=engine)
    ensure_variable_growth_columns()


def ensure_variable_growth_columns(bind=engine):
    """Add the two nullable auto/manual markers to existing SQLite databases."""
    inspector = inspect(bind)
    if not inspector.has_table("budget_assumptions"):
        return
    existing = {column["name"] for column in inspector.get_columns("budget_assumptions")}
    with bind.begin() as connection:
        for column in ("variable_materials_growth_auto", "variable_services_growth_auto"):
            if column not in existing:
                connection.execute(text(f"ALTER TABLE budget_assumptions ADD COLUMN {column} BOOLEAN"))


def drop_all():
    """
    Drop all tables - USE WITH CAUTION!
    """
    Base.metadata.drop_all(bind=engine)
