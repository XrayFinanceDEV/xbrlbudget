"""
FastAPI Application - XBRL Budget API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from decimal import Decimal
import sys
import os

# Add backend directory to Python path
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.config import settings
from app.core.decimal_encoder import decimal_to_float

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom JSON response that handles Decimals
class DecimalJSONResponse(JSONResponse):
    """JSON response that properly serializes Decimal values"""

    def render(self, content) -> bytes:
        if content is not None:
            content = decimal_to_float(content)
        return super().render(content)


# Override default response class
app.default_response_class = DecimalJSONResponse


@app.get("/")
def read_root():
    """Root endpoint"""
    return {
        "message": "XBRL Budget API",
        "version": settings.VERSION,
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


# Import and include API routes
from app.api.v1 import companies, financial_years, calculations, imports, budget_scenarios
app.include_router(companies.router, prefix=settings.API_V1_PREFIX, tags=["companies"])
app.include_router(financial_years.router, prefix=settings.API_V1_PREFIX, tags=["financial_years"])
app.include_router(calculations.router, prefix=settings.API_V1_PREFIX, tags=["calculations"])
app.include_router(imports.router, prefix=settings.API_V1_PREFIX, tags=["imports"])
app.include_router(budget_scenarios.router, prefix=settings.API_V1_PREFIX, tags=["budget_scenarios"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
