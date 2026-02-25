"""
Database connection and session management
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# Use absolute path for database to ensure all apps use the same database
# Database is located in project root directory
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT.endswith('/database'):
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
    from database.models import Company, FinancialYear, BalanceSheet, IncomeStatement
    Base.metadata.create_all(bind=engine)


def drop_all():
    """
    Drop all tables - USE WITH CAUTION!
    """
    Base.metadata.drop_all(bind=engine)
