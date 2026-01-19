"""
Pydantic schemas for data import operations
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class XBRLImportResponse(BaseModel):
    """Response schema for successful XBRL import"""
    success: bool = Field(..., description="Whether import was successful")
    taxonomy_version: str = Field(..., description="XBRL taxonomy version detected")
    years: List[int] = Field(..., description="Fiscal years imported")
    company_id: int = Field(..., description="Company ID")
    company_name: str = Field(..., description="Company name")
    tax_id: Optional[str] = Field(None, description="Company tax ID (P.IVA)")
    financial_year_ids: List[int] = Field(..., description="Financial year record IDs created")
    contexts_found: int = Field(..., description="Number of contexts found in XBRL")
    years_imported: int = Field(..., description="Number of years successfully imported")
    company_created: bool = Field(..., description="Whether a new company was created")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "taxonomy_version": "2018-11-04",
                "years": [2022, 2023],
                "company_id": 1,
                "company_name": "Azienda Esempio S.r.l.",
                "tax_id": "12345678901",
                "financial_year_ids": [1, 2],
                "contexts_found": 2,
                "years_imported": 2,
                "company_created": True
            }
        }


class CSVImportResponse(BaseModel):
    """Response schema for successful CSV import"""
    success: bool = Field(..., description="Whether import was successful")
    balance_sheet_type: str = Field(..., description="Balance sheet schema type detected")
    years: List[int] = Field(..., description="Fiscal years imported")
    rows_processed: int = Field(..., description="Number of CSV rows processed")
    balance_sheet_fields_imported: int = Field(..., description="Number of balance sheet fields imported")
    income_statement_fields_imported: int = Field(..., description="Number of income statement fields imported")
    financial_year_ids: List[int] = Field(..., description="Financial year record IDs created")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "balance_sheet_type": "ORDINARIO",
                "years": [2022, 2023],
                "rows_processed": 45,
                "balance_sheet_fields_imported": 18,
                "income_statement_fields_imported": 20,
                "financial_year_ids": [1, 2]
            }
        }


class ImportError(BaseModel):
    """Error response for failed imports"""
    success: bool = Field(False, description="Always False for errors")
    error: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Error type/category")
    details: Optional[str] = Field(None, description="Additional error details")

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "Failed to parse XBRL file",
                "error_type": "XBRLParseError",
                "details": "Unsupported taxonomy version: 2010-01-01"
            }
        }
