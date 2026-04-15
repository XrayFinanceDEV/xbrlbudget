"""
Admin endpoints for inspecting and retrieving uploaded files.

Protected by `X-Admin-Key` header matching ADMIN_API_KEY env var.
Not reachable from the Formula Finance iframe — used by the developer
from curl/browser to diagnose user-reported import problems.
"""
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from database.models import UploadedFile

router = APIRouter()

CONTENT_TYPES = {
    "pdf":  "application/pdf",
    "xbrl": "application/xml",
    "csv":  "text/csv",
}


def require_admin(x_admin_key: Optional[str] = Header(None)) -> None:
    expected = os.environ.get("ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API is not configured (ADMIN_API_KEY unset)")
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing X-Admin-Key")


@router.get("/admin/uploads", dependencies=[Depends(require_admin)])
def list_uploads(
    user_id: Optional[str] = Query(None, description="Filter by Supabase user_id"),
    file_type: Optional[str] = Query(None, description="xbrl | csv | pdf"),
    status: Optional[str] = Query(None, description="pending | success | error"),
    company_id: Optional[int] = Query(None),
    since: Optional[datetime] = Query(None, description="ISO8601 lower bound on uploaded_at"),
    until: Optional[datetime] = Query(None, description="ISO8601 upper bound on uploaded_at"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    List uploaded files with filters. Typical workflow:
      1. User reports "my last budget is wrong"
      2. GET /admin/uploads?user_id=<uid>&file_type=pdf   → newest first
      3. Pick the id matching the complaint
      4. GET /admin/uploads/{id}/download
    """
    q = db.query(UploadedFile)
    if user_id:
        q = q.filter(UploadedFile.user_id == user_id)
    if file_type:
        q = q.filter(UploadedFile.file_type == file_type)
    if status:
        q = q.filter(UploadedFile.status == status)
    if company_id is not None:
        q = q.filter(UploadedFile.company_id == company_id)
    if since:
        q = q.filter(UploadedFile.uploaded_at >= since)
    if until:
        q = q.filter(UploadedFile.uploaded_at <= until)

    rows = q.order_by(UploadedFile.uploaded_at.desc()).limit(limit).all()

    return {
        "count": len(rows),
        "uploads": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "company_id": r.company_id,
                "filename": r.filename,
                "file_type": r.file_type,
                "file_size": r.file_size,
                "status": r.status,
                "error_message": r.error_message,
                "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
            }
            for r in rows
        ],
    }


@router.get("/admin/uploads/{upload_id}", dependencies=[Depends(require_admin)])
def get_upload(upload_id: int, db: Session = Depends(get_db)):
    r = db.query(UploadedFile).filter(UploadedFile.id == upload_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Upload not found")
    return {
        "id": r.id,
        "user_id": r.user_id,
        "company_id": r.company_id,
        "filename": r.filename,
        "file_type": r.file_type,
        "file_size": r.file_size,
        "status": r.status,
        "error_message": r.error_message,
        "error_traceback": r.error_traceback,
        "storage_path": r.storage_path,
        "uploaded_at": r.uploaded_at.isoformat() if r.uploaded_at else None,
    }


@router.get("/admin/uploads/{upload_id}/download", dependencies=[Depends(require_admin)])
def download_upload(upload_id: int, db: Session = Depends(get_db)):
    r = db.query(UploadedFile).filter(UploadedFile.id == upload_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Upload not found")
    if not r.storage_path or not os.path.exists(r.storage_path):
        raise HTTPException(status_code=410, detail="File no longer available on disk (cleaned up or lost)")
    return FileResponse(
        r.storage_path,
        filename=r.filename,
        media_type=CONTENT_TYPES.get(r.file_type, "application/octet-stream"),
    )
