"""Assembla il modello del report intermedio di uno scenario infrannuale.

Solo letture, e nessuna formula nuova: il CE riclassificato viene da
`calculate_ce_result` (anche per l'annualizzato, su una mappa `× 12 / mesi`),
lo SP dalle proprieta' dei modelli ORM, gli indicatori della crisi da
`crisi_service`. La scelta dei due bilanci e' quella del motore infrannuale
(`IntraYearEngine._load_financial_years`), cosi' il report legge esattamente
i record che il confronto e la proiezione hanno usato.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.renderers.typst.intermedio_catalog import documento_titolo
from app.renderers.typst.intermedio_renderer import IntermedioPdf, IntermedioRenderer
from app.schemas.final_report_v2 import StatementPeriod
from app.schemas.intermedio_report import (
    CeAggregati, ColonnaCe, ColonnaSp, IntermediateReportModel, Segnale, SpAggregati,
)
from app.services.ai_comments_service import get_infrannuale_comments
from app.services.crisi_service import crisi_infrannuale
from app.services.extra_accounting_alerts_service import (
    EXTRA_ACCOUNTING_ALERT_KEYS, EXTRA_ACCOUNTING_ALERT_LABELS, normalize_extra_accounting_alerts,
)
from app.services.final_report_dossier import DossierSource, build_detailed_statements
from calculations.ce_result import calculate_ce_result
from calculations.intra_year_engine import IntraYearEngine

CHIAVI_COMMENTI = ("overall", "ce_confronto", "sp_confronto", "ce_proiezione", "sp_proiezione", "indicatori")


def _dec(value: Any) -> Decimal:
    return Decimal("0") if value is None else Decimal(str(value))


def _ce(source: Any) -> CeAggregati:
    r = calculate_ce_result(source)
    get = source.get if isinstance(source, dict) else (lambda k: getattr(source, k, None))
    return CeAggregati(
        ricavi=_dec(get("ce01_ricavi_vendite")),
        valore_produzione=r.production_value,
        # I costi operativi sono cio' che separa il valore della produzione
        # dall'EBITDA: si leggono dal risultato canonico, non si risommano.
        costi_operativi=r.production_value - r.ebitda,
        ebitda=r.ebitda,
        ammortamenti=_dec(get("ce09_ammortamenti")),
        ebit=r.ebit,
        oneri_finanziari=_dec(get("ce15_oneri_finanziari")),
        risultato_ante_imposte=r.profit_before_tax,
        imposte=_dec(get("ce20_imposte")),
        risultato_netto=r.net_profit,
    )


def _sp(bs: Any) -> SpAggregati:
    return SpAggregati(
        immobilizzazioni=_dec(bs.fixed_assets),
        attivo_circolante=_dec(bs.current_assets),
        totale_attivo=_dec(bs.total_assets),
        patrimonio_netto=_dec(bs.total_equity),
        debiti_finanziari=_dec(bs.financial_debt_total),
        debiti_operativi=_dec(bs.operating_debt_total),
        cassa=_dec(bs.sp09_disponibilita_liquide),
        ccn=_dec(bs.working_capital_net),
    )


def _colonne_orm(obj: Any, prefix: str = "ce") -> dict[str, Any]:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key.startswith(prefix)}


def _mappa(obj: Any, prefix: str) -> dict[str, Decimal]:
    return {k: _dec(v) for k, v in _colonne_orm(obj, prefix).items()}


def _periodo(pid: str, anno: int, label: str, basis: str, mesi: int | None) -> StatementPeriod:
    return StatementPeriod(id=pid, year=anno, label=label, basis=basis, period_months=mesi,
                           source="intermedio_report_service")


def _prospetti(ref_fy: Any, partial_fy: Any, mesi: int, anno_rif: int, anno: int,
               annualizzato: dict[str, Decimal] | None, forecast: Any) -> tuple[Any, Any]:
    """CE e SP completi con le righe del report finale. L'annualizzato esiste
    solo per il CE: lo stato patrimoniale e' puntuale e non si annualizza."""
    storico = DossierSource(_periodo("storico", anno_rif, f"Storico {anno_rif}", "historical", None),
                            _mappa(ref_fy.balance_sheet, "sp"), _mappa(ref_fy.income_statement, "ce"))
    parziale = DossierSource(_periodo("infrannuale", anno, f"Infrannuale {mesi}M", "observed", mesi),
                             _mappa(partial_fy.balance_sheet, "sp"), _mappa(partial_fy.income_statement, "ce"))
    fonti_ce, fonti_sp = [storico, parziale], [storico, parziale]
    if annualizzato is not None:
        fonti_ce.append(DossierSource(_periodo("annualizzato", anno, f"Annualizzato {anno}", "observed", 12),
                                      None, annualizzato))
    if forecast is not None:
        proiezione = DossierSource(_periodo("proiezione", anno, f"Proiezione {anno}", "forecast", 12),
                                   _mappa(forecast.balance_sheet, "sp"), _mappa(forecast.income_statement, "ce"))
        fonti_ce.append(proiezione)
        fonti_sp.append(proiezione)
    ce = next(s for s in build_detailed_statements(fonti_ce) if s.id == "income_statement")
    sp = next(s for s in build_detailed_statements(fonti_sp) if s.id == "balance_sheet")
    return ce, sp


def assemble_intermedio(db: Session, scenario: Any) -> IntermediateReportModel:
    """Solleva `ValueError` se i bilanci del periodo non ci sono."""
    engine = IntraYearEngine(db)
    partial_fy, ref_fy = engine._load_financial_years(scenario)
    if ref_fy is None:
        raise ValueError("Il report intermedio richiede il bilancio dell'anno di riferimento.")
    mesi = engine._period_months_from_record(partial_fy)
    anno_rif, anno = scenario.base_year, scenario.base_year + 1
    fattore = Decimal(12) / Decimal(mesi)
    parziale_ce = _colonne_orm(partial_fy.income_statement)
    annualizzato = {k: _dec(v) * fattore for k, v in parziale_ce.items()}

    ce = [
        ColonnaCe(chiave="storico", etichetta=f"Storico {anno_rif}", ce=_ce(ref_fy.income_statement)),
        ColonnaCe(chiave="infrannuale", etichetta=f"Infrannuale {mesi}M", ce=_ce(partial_fy.income_statement)),
    ]
    sp = [
        ColonnaSp(chiave="storico", etichetta=f"Storico {anno_rif}", sp=_sp(ref_fy.balance_sheet)),
        ColonnaSp(chiave="infrannuale", etichetta=f"Infrannuale {mesi}M", sp=_sp(partial_fy.balance_sheet)),
    ]
    if mesi != 12:
        ce.append(ColonnaCe(chiave="annualizzato", etichetta=f"Annualizzato {anno}", ce=_ce(annualizzato)))
    ordinati = sorted(scenario.forecast_years or [], key=lambda fy: fy.year)
    forecast = (ordinati[0] if mesi != 12 and ordinati and ordinati[0].income_statement
                and ordinati[0].balance_sheet else None)
    if forecast is not None:
        ce.append(ColonnaCe(chiave="proiezione", etichetta=f"Proiezione {anno}",
                            ce=_ce(forecast.income_statement)))
        sp.append(ColonnaSp(chiave="proiezione", etichetta=f"Proiezione {anno}",
                            sp=_sp(forecast.balance_sheet)))
    prospetto_ce, prospetto_sp = _prospetti(ref_fy, partial_fy, mesi, anno_rif, anno,
                                            annualizzato if mesi != 12 else None, forecast)

    stored = get_infrannuale_comments(db, scenario.id)
    commenti = stored.get("comments") or {}
    alerts = normalize_extra_accounting_alerts(scenario.extra_accounting_alerts).model_dump()

    return IntermediateReportModel(
        generated_at=datetime.now(timezone.utc),
        company_name=scenario.company.name,
        reference_year=anno_rif,
        partial_year=anno,
        period_months=mesi,
        ce=ce,
        sp=sp,
        crisi=crisi_infrannuale(db, scenario),
        prospetto_ce=prospetto_ce,
        prospetto_sp=prospetto_sp,
        commenti={k: str(commenti.get(k) or "").strip() for k in CHIAVI_COMMENTI},
        commenti_stantii=bool(stored.get("comments_stale")),
        segnali=[Segnale(chiave=k, etichetta=EXTRA_ACCOUNTING_ALERT_LABELS[k], attivo=bool(alerts[k]))
                 for k in EXTRA_ACCOUNTING_ALERT_KEYS],
    )


# ── PDF ───────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).resolve().parents[3]
_RENDERER: IntermedioRenderer | None = None
_RENDERER_LOCK = threading.RLock()
#: Caratteri vietati o ambigui in un nome file (come `final_report_pdf_service`).
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def get_intermedio_renderer() -> IntermedioRenderer:
    """Un renderer per processo: il semaforo interno limita le compilazioni."""
    global _RENDERER
    with _RENDERER_LOCK:
        if _RENDERER is None:
            _RENDERER = IntermedioRenderer.from_project(_ROOT)
    return _RENDERER


def nomi_file(model: IntermediateReportModel) -> tuple[str, str]:
    """(UTF-8 per `filename*`, ASCII per `filename=`), come il report finale."""
    raw = f"{documento_titolo(model)} - {model.company_name}"
    base = re.sub(r"\s+", " ", _UNSAFE.sub(" ", raw)).strip().strip(".").rstrip()[:160].rstrip(" .-")
    base = base or "Report infrannuale"
    ascii_base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    ascii_base = re.sub(r"\s+", " ", ascii_base).strip().strip(".").rstrip(" -") or "Report infrannuale"
    return base + ".pdf", ascii_base + ".pdf"


def render_intermedio_pdf(db: Session, scenario: Any, *,
                          avviso_commenti: bool = True) -> tuple[IntermediateReportModel, IntermedioPdf]:
    """Assemble → render. Solo letture: niente AI, niente proiezione, niente scritture.

    `avviso_commenti=False` e' la scelta dell'utente di chiudere, nella Stampa,
    l'avviso sui commenti scritti prima dell'ultima proiezione: chiuso a
    schermo, sparisce anche dal PDF (decisione del proprietario, 2026-09-16).
    """
    model = assemble_intermedio(db, scenario)
    if not avviso_commenti:
        model = model.model_copy(update={"commenti_stantii": False})
    # Il report si consegna: niente filigrana BOZZA, come la stampa del browser.
    return model, get_intermedio_renderer().render_intermedio(model, document_state="final")
