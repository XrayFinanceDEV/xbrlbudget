"""from_report sui bilanci veri del DB locale (regola del proprietario: niente bilanci inventati).

Il DB viene COPIATO in una cartella temporanea; senza DB i test si saltano, come in test_intermedio_report.
"""
import os
import shutil
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.renderers.business_plan.data import VALUE_KEYS, BusinessPlanData, dump_json, from_report, load_json

ROOT = Path(__file__).resolve().parents[1]
_DB = Path(os.environ.get("BUDGET_REAL_DB", "/home/peter/DEV/budget/financial_analysis.db"))
CASI = {"infrannuale": (575, 18), "bilancio": (21, 16), "startup": (628, 24)}


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    if not _DB.is_file():
        pytest.skip(f"DB locale assente ({_DB})")
    copia = tmp_path_factory.mktemp("bp") / "db.sqlite"
    shutil.copyfile(_DB, copia)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(f"sqlite:///{copia}")
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def _data(db, caso) -> BusinessPlanData:
    from app.services.final_report_service import assemble_final_report
    company, scenario = CASI[caso]
    try:
        report = assemble_final_report(db, company, scenario, schema_version=2)
    except Exception as error:  # scenario assente in questa copia del DB
        pytest.skip(f"{caso}: {error}")
    return from_report(report, draft=True)


def test_from_report_infrannuale_ambienta(db):
    data = _data(db, "infrannuale")
    assert [c.label for c in data.columns] == ["2026 F", "2027 P", "2028 P", "2029 P"]
    assert data.columns[0].is_base and not any(c.is_base for c in data.columns[1:])
    assert data.v("ricavi")[0] == D("4109510")
    # costi operativi = costi della produzione − ammortamenti, ed EBITDA = VP − costi operativi
    for i in range(4):
        assert data.v("valore_produzione")[i] - data.v("costi_operativi")[i] == data.v("ebitda")[i]
    # debiti finanziari coerenti con la PFN per costruzione
    for i in range(4):
        assert data.v("debiti_finanziari")[i] - data.v("liquidita")[i] == data.v("pfn")[i]
    assert all(v >= 0 for v in data.v("cf_rimborsi"))
    assert data.partial_label == "6M 2026 R"
    assert data.starting_point.kind == "infrannuale"
    assert data.starting_point.tables[0].headers == ("Prima", "Rettifiche", "Dopo")
    # la tabella «Fonte / Periodo / Stato» del riferimento, a pagina 12
    assert [f for f, _, _ in data.starting_point.sources] == [
        "Bilancio di verifica", "Registro rettifiche", "Forecast 2026", "Assunzioni del piano"]
    assert data.starting_point.sources[0][1:] == ("6M 2026", "disponibile")
    assert data.starting_point.sources[2][1:] == ("31.12.2026", "stimato")
    assert data.starting_point.sources[3][1:] == ("2027–2029", "disponibile")
    assert data.residual_revenue == data.v("ricavi")[0] - D("2104755")
    assert data.base_description.startswith("Base: bilancio infrannuale al 30.06.2026 (6 mesi)")
    assert set(VALUE_KEYS) <= set(data.values)
    assert [r.label for r in data.assumptions][:1] == ["Crescita ricavi"]
    assert data.growth["revenue_growth_pct"] == (D("5.000000"), D("6.000000"), D("1.000000"))
    assert data.annex["income_statement"] and data.annex["balance_sheet"] and data.annex["cashflow"]
    assert len(data.indicators_practice) == 15
    assert data.indicators_practice_headers[0] == "6M 2026 R"
    assert not {r.label for r in data.indicators_analytical} & {"ROE", "ROI", "ROS", "EBITDA Margin"}


def test_from_report_bilancio(db):
    data = _data(db, "bilancio")
    assert data.workflow == "bilancio"
    assert data.columns[0].label.endswith(" C") and data.columns[0].is_base
    assert data.starting_point.kind == "bilancio"
    assert data.starting_point.sources[0][2] == "consuntivo"
    assert data.partial_label is None


def test_from_report_startup(db):
    data = _data(db, "startup")
    assert data.workflow == "startup"
    assert not any(c.is_base for c in data.columns)
    assert data.starting_point.kind == "startup"
    assert data.starting_point.sources[-1][0] == "Assunzioni del piano"
    assert data.base_description.startswith("Startup")


def test_json_del_banco_andata_e_ritorno(tmp_path, db):
    data = _data(db, "infrannuale")
    path = tmp_path / "banco.json"
    import json
    path.write_text(json.dumps(dump_json(data)), encoding="utf-8")
    back = load_json(path)
    assert back.columns == data.columns
    assert back.v("ebitda") == data.v("ebitda")
    assert back.growth == data.growth
