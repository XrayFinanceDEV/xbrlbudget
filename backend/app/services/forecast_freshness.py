"""Single source of truth for persisted forecast freshness."""
from datetime import timezone


def forecast_staleness(scenario) -> tuple[str | None, str | None, bool]:
    """Return assumption timestamp, forecast timestamp and stale verdict.

    Missing assumptions or forecast years mean "unknown", not stale. Database
    timestamps are UTC-naive by construction; API strings make UTC explicit.
    """

    def _latest(rows):
        stamps = [row.updated_at or row.created_at for row in rows or []]
        stamps = [stamp for stamp in stamps if stamp is not None]
        return max(stamps) if stamps else None

    assumptions_at = _latest(scenario.assumptions)
    forecast_at = _latest(scenario.forecast_years)
    stale = bool(assumptions_at and forecast_at and assumptions_at > forecast_at)

    def _iso_utc(stamp):
        if stamp is None:
            return None
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
        return stamp.isoformat() + "Z"

    return _iso_utc(assumptions_at), _iso_utc(forecast_at), stale
