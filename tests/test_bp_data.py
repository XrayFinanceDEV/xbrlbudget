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


def test_R15_altri_ricavi_chiude_ricavi_costi_ebitda():
    from app.renderers.business_plan import data as bp
    vals = {"valore_produzione": D("2112108"), "ricavi": D("2104755"), "costi_operativi": D("2037866")}
    altri = bp._DERIVED["altri_ricavi_var"](vals.__getitem__)
    assert altri == D("7353")
    assert vals["ricavi"] + altri - vals["costi_operativi"] == D("74242")
    assert "altri_ricavi_var" in VALUE_KEYS
    labels = [label for label, _, _ in bp._CE_LINES]
    assert labels[:3] == ["Ricavi", "Altri ricavi e variazioni", "Costi operativi"]
    assert bp._DERIVED["altri_ricavi_var"](lambda k: None) is None


def test_R15_rettifiche_registrate_con_etichette_non_codici():
    from types import SimpleNamespace as NS
    from app.renderers.business_plan import data as bp
    e = NS(edited_label="Crediti verso clienti", edit_delta=D("-12500.4"),
           counterpart_label="Utile (perdita) d'esercizio", counterpart_delta=D("12500.4"),
           explanation=" Fattura stornata ")
    n = NS(edited_label="Ratei e risconti attivi", edit_delta=D("300"), counterpart_label="Cassa",
           counterpart_delta=D("-300"), explanation=None)
    rows = bp.rettifiche_registrate([e, n])
    assert rows[0] == ("Crediti verso clienti", "−12.500", "Utile (perdita) d'esercizio (12.500)", "Fattura stornata")
    assert rows[1][3] == "—"
    assert bp.rettifiche_registrate([]) == ()


# ------------------------------------------------------------------ R16: sezione 10, assunzioni del piano
def _ns(**kw):
    from types import SimpleNamespace
    return SimpleNamespace(**kw)


def _ass(field, values, *, active=True, provenance="user", **extra):
    base = dict(field=field, values=list(values), active=active, provenance=provenance, financing_loans=None,
                other_lenders=None, pregresso=None, sp_indexing=None, sp_overrides=None, ce_overrides=None)
    base.update(extra)
    return _ns(**base)


def _report(assumptions, rows=()):
    stm = _ns(rows=[_ns(code=c, label=label) for c, label in rows])
    return _ns(assumption_sections=[_ns(assumptions=list(assumptions))], detailed_statements=[stm])


def test_R16_tasso_e_durata_legacy_non_si_stampano_senza_finanziamento_legacy():
    from app.renderers.business_plan import data as bp
    base = [_ass("financing_amount", [0, 0, 0]), _ass("financing_interest_rate", [5, 5, 5]),
            _ass("financing_duration_years", [3, 3, 3])]
    labels = [r.label for r in bp._assumptions(_report(base), 3)[1]]
    assert not any("asso" in label or "urata" in label for label in labels)
    # importo legacy positivo e nessun contratto: restano
    vivo = [_ass("financing_amount", [100000, 0, 0]), _ass("financing_interest_rate", [5, 5, 5])]
    assert any(r.unit == "percent" for r in bp._assumptions(_report(vivo), 3)[1])
    # con financing_loans il tasso vero sta nella tabella Finanziamenti
    loans = vivo + [_ass("financing_loans", [None] * 3, financing_loans=[_ns()])]
    assert bp._assumptions(_report(loans), 3)[1] == []


def test_R16_fidi_valore_unico_per_tutto_il_piano():
    from app.renderers.business_plan import data as bp
    rows = bp._assumptions(_report([_ass("bank_lines_amount", [50000, None, None])]), 3)[1]
    assert rows[0].values == (D("50000"),) * 3


def test_R16_durata_solo_dichiarata_e_altro_finanziatore_senza_rimborsi():
    from app.renderers.business_plan import data as bp
    ln = _ns(name="Mutuo", amount=D("0"), opening_residual=D("90000"), interest_rate=D("4"), duration_years=None,
             repayments=[D("0"), D("30000"), D("30000"), D("30000")])
    ol = _ns(name="Socio", opening_residual=D("10000"), interest_rate=D("2"), repayments=[D("0"), D("0"), D("0")])
    rep = _report([_ass("financing_loans", [None], financing_loans=[ln]),
                   _ass("other_lenders", [None], other_lenders=[ol])])
    pre, altro = bp._finanziamenti(rep)
    # #61 S15: il calendario non e' la durata del mutuo, resta «n.d.»
    assert pre.durata_anni is None
    assert altro.durata_anni == 0


def test_R16_voci_indicizzate_e_forzate_senza_codici_ne_ripetizioni():
    from app.renderers.business_plan import data as bp
    idx = [_ns(field="sp16f", driver="personale")] * 3 + [_ns(field="sp18", driver="ricavi")] * 3
    ovr = [_ns(field="sp10_ratei_risconti_attivi", value=D("1000")), _ns(field="sp10_ratei_risconti_attivi", value=D("1000")),
           _ns(field="sp99_boh_altro", value=D("5"))]
    ce = [_ns(field="ce06_override", value=D("2000"))]
    rep = _report([_ass("sp_indexing", [None], sp_indexing=idx), _ass("sp_overrides", [None], sp_overrides=ovr),
                   _ass("ce_overrides", [None], ce_overrides=ce)],
                  rows=[("sp16f_debiti_previdenziali_altri", "Debiti verso istituti di previdenza"),
                        ("sp18_ratei_risconti_passivi", "E) Ratei e risconti passivi"),
                        ("sp10_ratei_risconti_attivi", "D) Ratei e risconti attivi"),
                        ("ce06_servizi", "7) Per servizi")])
    out = dict(bp._puntuali(rep))
    assert out["Voci indicizzate"] == "Debiti verso istituti di previdenza → personale, Ratei e risconti passivi → ricavi"
    assert out["Valori forzati SP previsionale"] == "Ratei e risconti attivi: 1.000, Boh altro: 5"
    assert out["Valori forzati CE previsionale"] == "Per servizi: 2.000"
