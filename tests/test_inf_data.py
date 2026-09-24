"""from_intermedio sui bilanci veri: AMBIENTA (575/17) stampa le cifre del committente."""
import shutil, tempfile
from decimal import Decimal as D
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SRC = Path("/home/peter/DEV/budget/financial_analysis.db")


@pytest.fixture(scope="module")
def db():
    if not SRC.is_file():
        pytest.skip("DB locale assente")
    tmp = Path(tempfile.mkdtemp()) / "db.sqlite"
    shutil.copyfile(SRC, tmp)
    s = sessionmaker(bind=create_engine(f"sqlite:///{tmp}"))()
    yield s
    s.close()


def _data(db, scenario_id):
    from database.models import BudgetScenario
    from app.services.intermedio_report_service import assemble_intermedio
    from app.renderers.infrannuale.data import from_intermedio
    return from_intermedio(assemble_intermedio(db, db.get(BudgetScenario, scenario_id)))


def test_ambienta_coincide_col_riferimento(db):
    d = _data(db, 17)
    assert [c.label for c in d.ce_cols] == ["2025 C", "6M 2026", "Ann. 2026", "2026 F"]
    assert [c.label for c in d.sp_cols] == ["2025 C", "6M 2026", "2026 F"]
    assert round(d.v("ricavi", "proiezione")) == 4109510
    assert round(d.v("oneri_finanziari", "storico")) == -40744
    assert round(d.v("cc_comm", "storico")) == 371906 and round(d.v("cc_comm", "proiezione")) == 852261
    assert round(d.v("crediti_clienti", "infrannuale")) == 1198959
    assert round(d.v("dscr", "storico"), 3) == D("3.026")
    assert round(d.var("ricavi", "proiezione"), 2) == D("9.26")
    assert d.crisi["infrannuale"].codice == "C2" and d.crisi["proiezione"].oltre == 8
    assert d.period_end == "30.06.2026"
    assert d.legend.startswith("C = consuntivo · 6M = infrannuale al 30.06.2026")


def test_senza_proiezione(db):
    d = _data(db, 3)  # AIC, nessun ForecastYear
    assert not d.has_forecast and [c.kind for c in d.sp_cols] == ["C", "6M"]
    assert "F = forecast" not in d.legend


def test_json_del_banco(db, tmp_path):
    from app.renderers.infrannuale.data import dump_json, load_json
    import json
    d = _data(db, 17)
    p = tmp_path / "b.json"
    p.write_text(json.dumps(dump_json(d)))
    assert load_json(p).values == d.values


def test_periodo_di_tre_mesi_senza_annualizzato():
    from app.renderers.infrannuale.data import Col, InfrannualeData, _period_end
    d = InfrannualeData("X", 3, 2025, 2026, _period_end(2026, 3),
                        (Col("storico", "2025 C", "C"), Col("infrannuale", "3M 2026", "6M")),
                        (Col("storico", "2025 C", "C"), Col("infrannuale", "3M 2026", "6M")), {})
    assert d.period_end == "31.03.2026"
    assert d.legend == "C = consuntivo · 3M = infrannuale al 31.03.2026"
    assert d.header_title == "Report infrannuale 3M 2026"
    assert d.var("ricavi", "infrannuale") is None


def test_rapporto_senza_denominatore_non_e_un_numero():
    """Rilievo 1 della revisione finale: `_div` del motore dà 0 su denominatore nullo, e 0 oneri finanziari è
    copertura infinita, non DSCR 0,000× «attenzione». Senza denominatore positivo il valore è n.d.; l'esito cade
    quando il motore dà il NEUTRO del «non lo so», resta quando dà un verdetto (PFN positiva senza EBITDA)."""
    from app.renderers.infrannuale.data import senza_denominatore
    ind = {"dscr": D("0"), "_oneri_finanziari_raw": D("0"), "pfn_ebitda": D("-1.12"), "_ebitda_raw": D("-5"),
           "roe": D("12"), "_equity_raw": D("-3"), "ros": D("0"), "_revenue_raw": D("0"),
           "roi": D("4"), "_total_assets_raw": D("100"), "ms": D("7")}
    pun = {"dscr": D("0.5"), "pfn_ebitda": D("0"), "roe": D("0.5"), "ros": D("0.5"), "roi": D("0.8"),
           "ms": D("1")}
    i2, p2 = senza_denominatore(ind, pun)
    assert i2["dscr"] is None and p2["dscr"] is None
    assert i2["pfn_ebitda"] is None and p2["pfn_ebitda"] == D("0")
    assert i2["roe"] is None and i2["ros"] is None
    assert i2["roi"] == D("4") and i2["ms"] == D("7") and p2["roi"] == D("0.8")


def test_d2m_pfn_ebitda_non_stampato(db):
    d = _data(db, 23)
    for col in d.crisi:
        if d.crisi[col].indicatori.get("_ebitda_raw") is not None and d.crisi[col].indicatori["_ebitda_raw"] <= 0:
            assert d.v("pfn_ebitda", col) is None, col
