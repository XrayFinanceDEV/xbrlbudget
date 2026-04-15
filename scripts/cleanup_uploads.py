"""
Delete uploaded files + DB rows older than the retention window.

Retention: 90 days (override with UPLOAD_RETENTION_DAYS env var).

Run daily via cron on the VPS:
    0 3 * * *  cd /app && python scripts/cleanup_uploads.py >> /var/log/upload_cleanup.log 2>&1
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Make shared modules importable
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from database.db import SessionLocal
from database.models import UploadedFile

RETENTION_DAYS = int(os.environ.get("UPLOAD_RETENTION_DAYS", "90"))


def main() -> None:
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    print(f"[cleanup_uploads] cutoff={cutoff.isoformat()} (retention={RETENTION_DAYS}d)")

    db = SessionLocal()
    files_deleted = 0
    rows_deleted = 0
    missing = 0
    try:
        stale = db.query(UploadedFile).filter(UploadedFile.uploaded_at < cutoff).all()
        print(f"[cleanup_uploads] {len(stale)} rows to purge")

        for row in stale:
            if row.storage_path:
                try:
                    p = Path(row.storage_path)
                    if p.exists():
                        p.unlink()
                        files_deleted += 1
                    else:
                        missing += 1
                except Exception as e:
                    print(f"[cleanup_uploads] could not remove {row.storage_path}: {e}")
            db.delete(row)
            rows_deleted += 1

        db.commit()
    finally:
        db.close()

    print(f"[cleanup_uploads] done — rows={rows_deleted} files={files_deleted} already_missing={missing}")


if __name__ == "__main__":
    main()
