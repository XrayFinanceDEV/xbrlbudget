"""
FastAPI Configuration using Pydantic Settings
"""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings"""

    # API Settings
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "XBRL Budget API"
    VERSION: str = "1.0.0"

    # Database
    DATABASE_URL: str = "sqlite:///./financial_analysis.db"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # Next.js dev server (default port)
        "http://localhost:3001",  # Next.js dev server (alternative port)
        "http://localhost:3002",  # Next.js dev server (alternative port)
        "http://localhost:8000",  # FastAPI dev server
        "http://localhost:8501",  # Streamlit (legacy)
    ]

    # Application
    DEBUG: bool = True

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
