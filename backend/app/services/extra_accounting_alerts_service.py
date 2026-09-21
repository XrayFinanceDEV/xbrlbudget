"""Persistence boundary for the seven infrannuale extra-accounting flags."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.budget import ExtraAccountingAlerts, ExtraAccountingAlertsUpdate


EXTRA_ACCOUNTING_ALERT_KEYS = (
    "retribuzioni", "fornitori", "banche", "inps", "inail", "riscossione", "iva",
)

#: Il testo di ciascun segnale, per il report intermedio in PDF. Lo stesso testo,
#: nello stesso ordine, sta in `frontend/lib/pratica-codes.ts` (`EXTRA_ALERT_DEFS`),
#: che lo mostra a schermo: `tests/test_intermedio_report.py` confronta i due elenchi.
EXTRA_ACCOUNTING_ALERT_LABELS = {
    "retribuzioni": "Debiti per retribuzione scaduti da almeno 30 giorni pari a oltre il 50% dell'ammontare "
                    "complessivo mensile delle retribuzioni",
    "fornitori": "Debiti verso fornitori scaduti da almeno 90 giorni di ammontare superiore ai debiti non "
                 "ancora scaduti",
    "banche": "Esposizioni nei confronti delle banche e altri intermediari finanziari scadute da più di 60 "
              "giorni o che abbiano superato il limite degli affidamenti da più di 60 giorni, purché "
              "rappresentino almeno il 5% del totale delle esposizioni",
    "inps": "INPS: ritardo di oltre 90 giorni nel versamento di contributi previdenziali di ammontare superiore "
            "al 30% di quelli dovuti nell'anno precedente e all'importo di €15.000 (con lavoratori subordinati) "
            "o €5.000 (senza lavoratori subordinati)",
    "inail": "INAIL: ritardo di oltre 90 giorni nel versamento di premi assicurativi di ammontare superiore a €5.000",
    "riscossione": "Agente della Riscossione: crediti affidati per la riscossione, auto dichiarati o "
                   "definitivamente accertati e scaduti da oltre 90 giorni, superiori a €100.000 (imprese "
                   "individuali), €200.000 (società di persone), €500.000 (società di capitali)",
    "iva": "Agenzia delle Entrate: debiti IVA scaduti e non versati superiori a €20.000, o superiori a €5.000 se "
           "di entità pari ad oltre il 10% del volume d'affari dell'anno precedente",
}


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
