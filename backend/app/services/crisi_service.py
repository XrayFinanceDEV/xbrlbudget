"""Indicatori della crisi d'impresa di uno scenario infrannuale, tre colonne.

- **Storico**: l'anno di riferimento completo, senza segnali extracontabili
  (i segnali sono del periodo in corso, non dell'anno chiuso).
- **Infrannuale**: SP del periodo cosi' com'e' (valori puntuali, mai
  annualizzati), CE annualizzato `× 12 / period_months`.
- **Proiezione**: il `ForecastYear` che il motore infrannuale ha persistito,
  lo stesso che leggono /analysis e il rendiconto. Assente su un periodo di 12
  mesi o finche' la proiezione non e' stata generata.

Il calcolo sta in `calculations/crisi_impresa.py`; qui si leggono solo i dati.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.services.extra_accounting_alerts_service import (
    EXTRA_ACCOUNTING_ALERT_KEYS,
    normalize_extra_accounting_alerts,
)
from calculations.crisi_impresa import (
    CHIAVI_PUNTEGGIO,
    INDICATORI,
    calcola_indicatori,
    indicatori_come_mappa,
    punteggi_crisi,
    punteggio,
    rating_crisi,
)
from calculations.intra_year_engine import IntraYearEngine


def _colonne_orm(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns
            if c.key.startswith(("sp", "ce"))}


def _colonna(chiave: str, anno: int, mesi: int, bs: dict, ce: dict, segnali: int) -> dict[str, Any]:
    ind = calcola_indicatori(bs, ce)
    punteggi = punteggi_crisi(ind)
    return {
        "chiave": chiave,
        "anno": anno,
        "period_months": mesi,
        "indicatori": {k: float(v) for k, v in indicatori_come_mappa(ind).items()},
        "punteggi": {i.chiave: float(punteggio(i.chiave, ind)) for i in INDICATORI},
        "rating": rating_crisi(punteggi, segnali)._asdict(),
        "rating_per_segnali": [rating_crisi(punteggi, n)._asdict()
                               for n in range(len(EXTRA_ACCOUNTING_ALERT_KEYS) + 1)],
    }


def crisi_infrannuale(db: Session, scenario: Any) -> dict[str, Any]:
    """Solleva `ValueError` (dal motore) se il confronto non si puo' costruire."""
    comparison = IntraYearEngine(db).get_comparison(scenario.id)
    mesi = comparison["period_months"]
    fattore = Decimal(12) / Decimal(mesi)
    alerts = normalize_extra_accounting_alerts(scenario.extra_accounting_alerts)
    segnali = sum(1 for v in alerts.model_dump().values() if v)

    bs_items, ce_items = comparison["balance_items"], comparison["income_items"]
    storico = _colonna(
        "storico", comparison["reference_year"], 12,
        {i["code"]: i["reference_value"] for i in bs_items},
        {i["code"]: i["reference_value"] for i in ce_items},
        0,
    )
    infrannuale = _colonna(
        "infrannuale", comparison["partial_year"], mesi,
        {i["code"]: i["partial_value"] for i in bs_items},
        {i["code"]: Decimal(str(i["partial_value"])) * fattore for i in ce_items},
        segnali,
    )

    proiezione = None
    forecast = sorted(scenario.forecast_years, key=lambda fy: fy.year)
    if mesi != 12 and forecast:
        fy = forecast[0]
        proiezione = _colonna("proiezione", fy.year, 12, _colonne_orm(fy.balance_sheet),
                              _colonne_orm(fy.income_statement), segnali)

    return {
        "reference_year": comparison["reference_year"],
        "partial_year": comparison["partial_year"],
        "period_months": mesi,
        "segnali_attivi": segnali,
        "definizioni": [{"chiave": i.chiave, "etichetta": i.etichetta, "formato": i.formato,
                         "nel_punteggio": i.chiave in CHIAVI_PUNTEGGIO} for i in INDICATORI],
        "storico": storico,
        "infrannuale": infrannuale,
        "proiezione": proiezione,
    }
