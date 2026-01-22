"""
FastAPI Configuration using Pydantic Settings
"""
import os
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Optional


def get_database_url() -> str:
    """Get absolute path to project root database"""
    # Get project root (4 levels up from this file: core -> app -> backend -> budget)
    current_file = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
    db_path = os.path.join(project_root, "financial_analysis.db")
    return f"sqlite:///{db_path}"


class Settings(BaseSettings):
    """Application settings"""

    # API Settings
    API_V1_PREFIX: str = "/api/v1"
    PROJECT_NAME: str = "XBRL Budget API"
    VERSION: str = "1.0.0"

    # Database - Use absolute path pointing to root database
    # This ensures backend and legacy app share the same database
    DATABASE_URL: str = get_database_url()

    # CORS - Configure allowed origins for API access
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # Next.js dev server (default port)
        "http://localhost:3001",  # Next.js dev server (alternative port)
        "http://localhost:3002",  # Next.js dev server (alternative port)
        "http://localhost:8000",  # FastAPI dev server
        "http://localhost:8501",  # Streamlit (legacy)
        "https://*.netlify.app",  # Netlify preview/production deployments
        # TODO: Add your custom Netlify domain after deployment
        # "https://your-site-name.netlify.app",
    ]

    # Application
    DEBUG: bool = True

    class Config:
        case_sensitive = True
        env_file = ".env"


settings = Settings()
