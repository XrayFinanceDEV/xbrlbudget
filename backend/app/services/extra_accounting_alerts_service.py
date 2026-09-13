"""Persistence boundary for the seven infrannuale extra-accounting flags."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.budget import ExtraAccountingAlerts, ExtraAccountingAlertsUpdate


EXTRA_ACCOUNTING_ALERT_KEYS = (
    "retribuzioni", "fornitori", "banche", "inps", "inail", "riscossione", "iva",
)


def normalize_extra_accounting_alerts(raw: Any) -> ExtraAccountingAlerts:
    """Turn legacy null/sparse/untrusted JSON into the complete safe map."""
    source = raw if isinstance(raw, dict) else {}
    return ExtraAccountingAlerts.model_validate({
        key: source[key] if isinstance(source.get(key), bool) else False
        for key in EXTRA_ACCOUNTING_ALERT_KEYS
    })


def save_extra_accounting_alerts(
    db: Session,
    scenario: Any,
    alerts: ExtraAccountingAlertsUpdate,
) -> datetime:
    """Persist map and a database-compatible naïve UTC clock atomically."""
    updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    scenario.extra_accounting_alerts = alerts.model_dump()
    scenario.extra_accounting_alerts_updated_at = updated_at
    db.commit()
    return utc_aware(updated_at)


def utc_aware(value: datetime | None) -> datetime | None:
    """Expose old naïve DB UTC values as explicit UTC in API responses."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
