"""
API endpoints for data import (XBRL and CSV)
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
import tempfile
import os

from app.core.database import get_db
from app.schemas.imports import XBRLImportResponse, CSVImportResponse, ImportError
from importers.xbrl_parser_enhanced import import_xbrl_file_enhanced, XBRLParseError
from importers.csv_importer import import_csv_file

router = APIRouter()


@router.post(
    "/import/xbrl",
    response_model=XBRLImportResponse,
    summary="Import XBRL Financial Data",
    description="""
    Upload and import an Italian GAAP XBRL file.

    Supports taxonomies: 2011-01-04, 2014-11-17, 2015-12-14, 2016-11-14, 2017-07-06, 2018-11-04

    The file will be parsed and financial data (Balance Sheet and Income Statement) will be
    imported into the database. If no company_id is provided and create_company is True,
    a new company will be created from the XBRL entity information.
    """
)
async def upload_xbrl(
    file: UploadFile = File(..., description="XBRL file to import (.xbrl or .xml)"),
    company_id: Optional[int] = Query(None, description="Existing company ID (optional)"),
    create_company: bool = Query(True, description="Create company if not exists"),
    db: Session = Depends(get_db)
):
    """
    Import XBRL file and extract financial data.

    Args:
        file: Uploaded XBRL file
        company_id: Optional company ID to associate data with
        create_company: Whether to create a new company if not found
        db: Database session

    Returns:
        XBRLImportResponse with import results

    Raises:
        HTTPException: If file validation fails or parsing errors occur
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    file_ext = file.filename.lower().split('.')[-1]
    if file_ext not in ['xbrl', 'xml']:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: .{file_ext}. Only .xbrl and .xml files are supported."
        )

    # Validate file size (max 50MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB in bytes

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is 50MB, received {len(content) / 1024 / 1024:.1f}MB"
        )

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Save to temporary file
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xbrl') as tmp:
            tmp.write(content)
            tmp_file = tmp.name

        # Import XBRL file using enhanced parser with reconciliation
        result = import_xbrl_file_enhanced(
            file_path=tmp_file,
            company_id=company_id,
            create_company=create_company
        )

        return XBRLImportResponse(**result)

    except XBRLParseError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "XBRLParseError",
                "details": "Failed to parse XBRL file. Check taxonomy version and file structure."
            }
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "ValueError",
                "details": "Invalid data in XBRL file"
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "details": "Unexpected error during import"
            }
        )
    finally:
        # Clean up temporary file
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass  # Ignore cleanup errors


@router.post(
    "/import/csv",
    response_model=CSVImportResponse,
    summary="Import CSV Financial Data (TEBE Format)",
    description="""
    Upload and import a CSV file in TEBE format (semicolon-delimited).

    The CSV must contain financial data for a specific company and up to 2 years.
    Company ID must be provided (CSV files don't contain entity information).
    """
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file to import (.csv)"),
    company_id: int = Query(..., description="Company ID to import data for"),
    year1: Optional[int] = Query(None, description="First year (most recent, auto-detect if None)"),
    year2: Optional[int] = Query(None, description="Second year (previous, auto-detect if None)"),
    db: Session = Depends(get_db)
):
    """
    Import CSV file (TEBE format) and extract financial data.

    Args:
        file: Uploaded CSV file
        company_id: Company ID to associate data with
        year1: First fiscal year (optional, auto-detected from CSV)
        year2: Second fiscal year (optional, auto-detected from CSV)
        db: Database session

    Returns:
        CSVImportResponse with import results

    Raises:
        HTTPException: If file validation fails or parsing errors occur
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    file_ext = file.filename.lower().split('.')[-1]
    if file_ext != 'csv':
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: .{file_ext}. Only .csv files are supported."
        )

    # Validate company exists
    from database.models import Company
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail=f"Company with ID {company_id} not found")

    # Read file content
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")

    if len(content) == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    # Save to temporary file
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='wb') as tmp:
            tmp.write(content)
            tmp_file = tmp.name

        # Import CSV file using existing importer
        result = import_csv_file(
            file_path=tmp_file,
            company_id=company_id,
            year1=year1,
            year2=year2
        )

        return CSVImportResponse(**result)

    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "error": str(e),
                "error_type": "ValueError",
                "details": "Failed to parse CSV file. Check format and data."
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "details": "Unexpected error during import"
            }
        )
    finally:
        # Clean up temporary file
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.unlink(tmp_file)
            except Exception:
                pass  # Ignore cleanup errors
