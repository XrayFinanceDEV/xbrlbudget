"""Kit del banco di triage AMBIENTA: base vera in memoria, generazione e report dal percorso di produzione."""
import json
from dataclasses import dataclass
from decimal import Decimal as D
from pathlib import Path

import pytest

from database.models import (
    BalanceSheet, BudgetScenario, Company, FinancialYear, ForecastYear, IncomeStatement,
)
from backend.app.services import assumptions_service, forecast_preview_service
from tests.e2e_kit import memory_sessions, read_forecast_maps

_RAW = json.loads((Path(__file__).parent / "fixtures" / "ambienta_2026.json").read_text())
BASE_BS = {k: D(v) for k, v in _RAW["bs"].items()}
BASE_CE = {k: D(v) for k, v in _RAW["ce"].items()}
ANNI = (2027, 2028, 2029)


def righe(**comuni) -> list:
    """Tre righe di piano a crescita zero. Lo scoperto è concesso: la cassa di base è 54,82 € e ogni test
    deve isolare il proprio meccanismo, non inciampare nel fabbisogno."""
    out = []
    for y in ANNI:
        r = {"forecast_year": y, "revenue_growth_pct": 0, "tax_rate": 27.9, "overdraft_allowed": True}
        r.update(comuni)
        out.append(r)
    return out


def per_anno(rows: list, campo: str, valori) -> list:
    """Imposta `campo` anno per anno (valori nell'ordine 2027, 2028, 2029)."""
    for r, v in zip(rows, valori):
        r[campo] = v
    return rows


@dataclass
class Esito:
    res: dict
    anni: dict
    det: dict
    data: object
    rep: object
    meta: dict


def genera(rows, *, bs=None, ce=None, report=False, prima=None, ritocca=None) -> Esito:
    """Semina la base (con eventuali ritocchi `bs`/`ce`), salva le righe col bulk di produzione
    (`auto_generate=True`) e rilegge ciò che è persistito. `prima`: righe salvate e generate PRIMA di
    `rows`, per i test che vogliono un previsionale vecchio sotto un salvataggio respinto. `ritocca`:
    `callable(db, scenario_id)` eseguito dopo la generazione e prima del report, per i test che
    scrivono a mano un campo persistito (es. `ForecastYear.engine_meta`) che nessuna API espone."""
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company = Company(name="AMBIENTA", tax_id="AMBIENTA2026", sector=1, user_id="rilievi")
            db.add(company); db.flush()
            fy = FinancialYear(company_id=company.id, year=2026, period_months=None,
                               validation_status="verified", forecastable=True)
            db.add(fy); db.flush()
            db.add(BalanceSheet(financial_year_id=fy.id, **{**BASE_BS, **(bs or {})}))
            db.add(IncomeStatement(financial_year_id=fy.id, **{**BASE_CE, **(ce or {})}))
            db.commit()
            sc = BudgetScenario(company_id=company.id, name="rilievi", base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            if prima is not None:
                r0 = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in prima],
                                                                 auto_generate=True)
                if r0["forecast_generated"] is not True:
                    pytest.fail(f"precondizione: il previsionale di partenza non si genera: {r0['message']}")
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in rows],
                                                              auto_generate=True)
            if ritocca is not None:
                ritocca(db, sc.id)
                db.flush()
            anni = {y: (sp, c) for y, sp, c in read_forecast_maps(db, sc.id)}
            meta = {fy.year: fy.engine_meta for fy in
                    db.query(ForecastYear).filter(ForecastYear.scenario_id == sc.id)}
            prev = forecast_preview_service.preview_forecast(db, sc.id, [dict(r) for r in rows])
            det = {y["year"]: y["details"] for y in prev.get("forecast_years") or []}
            data = rep = None
            if report and anni:
                from backend.app.services.final_report_service import assemble_final_report
                from backend.app.renderers.business_plan.data import from_report
                rep = assemble_final_report(db, company.id, sc.id, schema_version=2)
                data = from_report(rep, draft=True)
            return Esito(res, anni, det, data, rep, meta)
    finally:
        engine.dispose()


def generato(e: Esito) -> Esito:
    """Precondizione: il previsionale si è generato. `pytest.fail`, non `assert`: un test marcato
    xfail(raises=AssertionError) non deve inghiottire una precondizione caduta come se fosse il rilievo."""
    if e.res["forecast_generated"] is not True:
        pytest.fail(f"precondizione: previsionale non generato: {e.res['message']}")
    return e


def piano(data, key: str) -> list:
    """Valori di piano (2027..2029) di una chiave di BusinessPlanData, colonna base esclusa."""
    return [data.v(key)[i] for i in data.plan_idx]


def base(data, key: str):
    return data.v(key)[0]
