"""A01-bis (lotto 2 fix rilievi, 2026-09-26): avviso di previsionale vecchio nel PDF, nel Word e su
/report — sia per ipotesi salvate dopo l'ultima generazione (`forecast_stale`), sia per un
previsionale generato da una versione precedente del motore (`engine_version_stale`)."""
from decimal import Decimal as D

import pytest

from tests.rilievi_kit import BASE_BS, genera, generato, righe

FRASE_FORECAST_STALE = "Previsionale precedente alle ipotesi salvate: da rigenerare"
FRASE_ENGINE_STALE = "Previsionale generato da una versione precedente del motore: da rigenerare"


_MUTUO_A = {"name": "Finanziamento A", "amount": 0, "opening_residual": 467528.52, "interest_rate": 4,
            "grace_years": 0, "balloon_pct": 0, "duration_years": None,
            "repayments": [53409, 53409, 53409, 53409]}


def _banche(fidi: float, residuo: float) -> dict:
    """Copiato da `test_rilievi_ambienta.py::_banche`: fidi + residuo del mutuo A che non quadrano col
    bilancio (scarto 11.000) — il salvataggio bulk lo respinge."""
    return {"financing_loans": [{**_MUTUO_A, "opening_residual": residuo}], "bank_lines_amount": fidi,
            "bank_lines_rule": "costante", "bank_lines_rate": 6}


def _bp():
    pytest.importorskip("backend.app.renderers.business_plan.data")


def _pdf_text(pdf: bytes) -> str:
    import fitz
    return "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))


def _docx_text(data: bytes) -> str:
    from backend.app.renderers.docx_export import docx_text
    return "\n".join(docx_text(data))


def _con_previsionale_vecchio():
    """Un salvataggio respinto: a schermo resta il previsionale precedente, salvato con `prima`."""
    buone = righe()
    respinte = righe()
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    respinte[0].update(_banche(311000, float(banche - D("300000"))))
    e = genera(respinte, prima=buone, report=True)
    if e.res["forecast_generated"] is not False:
        pytest.fail("precondizione: il salvataggio doveva essere respinto")
    if e.rep is None:
        pytest.fail("precondizione: il report non si costruisce sul previsionale vecchio")
    return e


def test_a_triage_forecast_stale_senza_marcatore():
    """(a) Il test del triage: report bloccato, diagnostica `forecast_stale`, frase nel PDF in bozza."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan
    e = _con_previsionale_vecchio()
    assert e.rep.readiness.status == "blocked", e.rep.readiness
    assert any(d.code == "forecast_stale" for d in e.rep.diagnostics)
    assert e.data.avvisi and e.data.avvisi[0] == FRASE_FORECAST_STALE
    testo = _pdf_text(render_business_plan(e.data)).lower()
    assert FRASE_FORECAST_STALE.lower() in testo


def test_b_la_frase_e_nel_docx():
    """(b) Lo stesso avviso è nel .docx, sullo stesso `BusinessPlanData`."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan_docx
    e = _con_previsionale_vecchio()
    testo = _docx_text(render_business_plan_docx(e.data))
    assert FRASE_FORECAST_STALE in testo


def test_c_engine_version_stale_diagnostica_e_frase():
    """(c) Un previsionale generato e poi ritoccato a mano con `engine_meta` di una versione precedente
    del motore: diagnostica `engine_version_stale` e frase nel PDF."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan

    def ritocca(db, scenario_id):
        from database.models import ForecastYear
        rows = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario_id).all()
        assert rows, "precondizione: nessun ForecastYear da ritoccare"
        rows[0].engine_meta = {"engine_version": "1", "pareggio": None}

    e = generato(genera(righe(), report=True, ritocca=ritocca))
    assert any(d.code == "engine_version_stale" for d in e.rep.diagnostics), e.rep.diagnostics
    assert e.rep.readiness.status == "blocked", e.rep.readiness
    assert FRASE_ENGINE_STALE in e.data.avvisi
    testo = _pdf_text(render_business_plan(e.data)).lower()
    assert FRASE_ENGINE_STALE.lower() in testo


def test_d_engine_meta_none_nessuna_diagnostica():
    """(d) `engine_meta = None` non è un "prima": nessuna diagnostica `engine_version_stale`."""
    _bp()

    def ritocca(db, scenario_id):
        from database.models import ForecastYear
        rows = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario_id).all()
        assert rows, "precondizione: nessun ForecastYear da ritoccare"
        for row in rows:
            row.engine_meta = None

    e = generato(genera(righe(), report=True, ritocca=ritocca))
    assert not any(d.code == "engine_version_stale" for d in e.rep.diagnostics), e.rep.diagnostics
    assert FRASE_ENGINE_STALE not in e.data.avvisi


def test_e_report_pulito_nessun_avviso():
    """(e) Un report senza diagnostiche di previsionale vecchio: `avvisi == ()` e il PDF non contiene
    «da rigenerare»."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan
    e = generato(genera(righe(), report=True))
    assert e.data.avvisi == ()
    testo = _pdf_text(render_business_plan(e.data)).lower()
    assert "da rigenerare" not in testo


class _RigaFinta:
    """Un `ForecastYear` finto: solo l'attributo che `_engine_version_stale` legge."""

    def __init__(self, engine_meta):
        self.engine_meta = engine_meta


def test_helper_infrannuale_non_e_mai_candidato():
    """`_engine_version_stale` esclude `workflow == "infrannuale"` a monte, anche con una riga
    palesemente vecchia: costruire uno scenario infrannuale intero solo per questo sarebbe un
    bilancio inventato in più (vietato dai vincoli del lotto) per provare un `if` di una riga."""
    from backend.app.services.final_report_service import _engine_version_stale
    righe_vecchie = [_RigaFinta({"engine_version": "1", "pareggio": None})]
    assert _engine_version_stale("infrannuale", righe_vecchie) is False
    assert _engine_version_stale("bilancio", righe_vecchie) is True
    assert _engine_version_stale("startup", righe_vecchie) is True


def test_helper_engine_meta_assente_o_senza_versione_non_e_stale():
    from backend.app.services.final_report_service import _engine_version_stale
    from calculations.forecast_engine import ENGINE_VERSION
    assert _engine_version_stale("bilancio", [_RigaFinta(None)]) is False
    assert _engine_version_stale("bilancio", [_RigaFinta({"pareggio": None})]) is False
    assert _engine_version_stale("bilancio", [_RigaFinta({"engine_version": ENGINE_VERSION})]) is False
