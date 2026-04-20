"""
Upload tracker service — saves every imported file to disk and records
the outcome in the uploaded_files table.

Goal: when a user reports wrong/missing numbers or a failed import, the
developer can SSH into the VPS, query the table, and retrieve the exact
original file that produced the problem.

Storage: data/uploads/{user_id}/{YYYY-MM}/{timestamp}_{uuid}.{ext}
Retention: 90 days (see scripts/cleanup_uploads.py)
"""
import os
import uuid
import logging
import traceback as tb_module
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from database.models import UploadedFile

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
UPLOAD_ROOT = os.environ.get("UPLOAD_ROOT", str(_PROJECT_ROOT / "data" / "uploads"))


def _safe_user_dir(user_id: Optional[str]) -> str:
    if not user_id:
        return "_anonymous"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)[:64]


def save_upload(
    db: Session,
    user_id: Optional[str],
    filename: str,
    file_type: str,
    content: bytes,
    company_id: Optional[int] = None,
    user_email: Optional[str] = None,
) -> UploadedFile:
    """
    Persist the uploaded bytes to disk and create a pending UploadedFile row.

    Called BEFORE the parser runs so hard failures (parser crash, import
    exception before any DB write) still produce a trackable record.

    Errors in this function are swallowed — tracking must never break the
    import flow. Returns None if persistence fails.
    """
    try:
        now = datetime.utcnow()
        month_dir = now.strftime("%Y-%m")
        user_dir = _safe_user_dir(user_id)

        target_dir = Path(UPLOAD_ROOT) / user_dir / month_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        stored_name = f"{now.strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"
        storage_path = target_dir / stored_name

        storage_path.write_bytes(content)

        record = UploadedFile(
            user_id=user_id,
            user_email=(user_email[:255] if user_email else None),
            company_id=company_id,
            filename=filename[:255],
            file_type=file_type,
            file_size=len(content),
            storage_path=str(storage_path),
            status="pending",
            uploaded_at=now,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info(f"[UPLOAD_TRACKER] Saved id={record.id} path={storage_path}")
        return record
    except Exception as e:
        logger.error(f"[UPLOAD_TRACKER] save_upload failed: {e}\n{tb_module.format_exc()}")
        try:
            db.rollback()
        except Exception:
            pass
        return None


def mark_success(db: Session, record: Optional[UploadedFile], company_id: Optional[int] = None) -> None:
    if record is None:
        return
    try:
        record.status = "success"
        if company_id and not record.company_id:
            record.company_id = company_id
        db.commit()
    except Exception as e:
        logger.error(f"[UPLOAD_TRACKER] mark_success failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass


def mark_error(db: Session, record: Optional[UploadedFile], exc: BaseException) -> None:
    if record is None:
        return
    try:
        record.status = "error"
        record.error_message = f"{type(exc).__name__}: {exc}"[:2000]
        record.error_traceback = tb_module.format_exc()[:10000]
        db.commit()
    except Exception as e:
        logger.error(f"[UPLOAD_TRACKER] mark_error failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
