"""
Database connection and session management for FastAPI
"""
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

# Create SQLAlchemy engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
    echo=settings.DEBUG
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database session in FastAPI routes

    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database - create all tables"""
    # Import all models to ensure they're registered
    import sys
    import os

    # Add backend directory to path
    backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    from database.models import (
        Company, FinancialYear, BalanceSheet, IncomeStatement,
        BudgetScenario, BudgetAssumptions, ForecastYear,
        ForecastBalanceSheet, ForecastIncomeStatement
    )

    Base.metadata.create_all(bind=engine)


def drop_all() -> None:
    """Drop all tables - USE WITH CAUTION!"""
    Base.metadata.drop_all(bind=engine)
