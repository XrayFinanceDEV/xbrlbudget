"""
Database connection and session management for FastAPI
Uses shared database configuration from root database.db module
"""
from typing import Generator
from sqlalchemy.orm import Session

# Import shared database components from root
from database.db import Base, engine, SessionLocal, init_db, drop_all


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

# Note: init_db() and drop_all() are imported from database.db
