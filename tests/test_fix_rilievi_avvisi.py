"""Fix round 1 della review sul Task 1 (lotto 2 fix rilievi, 2026-09-26): l'avviso A01-bis in header
e in copertina non deve rompere l'impaginazione — né troncare il nome azienda nell'intestazione, né
far uscire una riga di copertina dalla larghezza utile della pagina quando entrambe le diagnostiche
sparano insieme. File separato da `test_fix_rilievi_report.py` (in modifica concorrente da un altro
agente su questo stesso giro)."""
from decimal import Decimal as D

import pytest
from reportlab.pdfbase import pdfmetrics

from tests.rilievi_kit import BASE_BS, genera, generato, righe

FRASE_FORECAST_STALE = "Previsionale precedente alle ipotesi salvate: da rigenerare"
FRASE_ENGINE_STALE = "Previsionale generato da una versione precedente del motore: da rigenerare"

_MUTUO_A = {"name": "Finanziamento A", "amount": 0, "opening_residual": 467528.52, "interest_rate": 4,
            "grace_years": 0, "balloon_pct": 0, "duration_years": None,
            "repayments": [53409, 53409, 53409, 53409]}


def _banche(fidi: float, residuo: float) -> dict:
    """Copiato (non importato: vedi nota in testa al file) da `test_rilievi_ambienta.py::_banche`."""
    return {"financing_loans": [{**_MUTUO_A, "opening_residual": residuo}], "bank_lines_amount": fidi,
            "bank_lines_rule": "costante", "bank_lines_rate": 6}


def _bp():
    pytest.importorskip("backend.app.renderers.business_plan.data")


def _con_forecast_stale():
    """Un salvataggio respinto: a schermo resta il previsionale precedente."""
    buone = righe()
    respinte = righe()
    banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
    respinte[0].update(_banche(311000, float(banche - D("300000"))))
    e = genera(respinte, prima=buone, report=True)
    if e.res["forecast_generated"] is not False:
        pytest.fail("precondizione: il salvataggio doveva essere respinto")
    return e


def _ritocca_engine_meta_vecchio(db, scenario_id):
    from database.models import ForecastYear
    rows = db.query(ForecastYear).filter(ForecastYear.scenario_id == scenario_id).all()
    assert rows, "precondizione: nessun ForecastYear da ritoccare"
    rows[0].engine_meta = {"engine_version": "1", "pareggio": None}


def _con_engine_version_stale():
    return generato(genera(righe(), report=True, ritocca=_ritocca_engine_meta_vecchio))


def _con_entrambi_gli_avvisi():
    """forecast_stale (salvataggio respinto) INSIEME a engine_version_stale, per il rilievo 2 (righe
    di copertina che non devono unirsi/overfloware). `rilievi_kit.genera()` non basta: il suo
    `ritocca` gira dopo il salvataggio respinto, e toccare `ForecastYear` in quel momento ne
    aggiorna `updated_at` — il previsionale torna "fresco" e `forecast_stale` non scatta più.
    Serve invece: genera bene → rendi il previsionale vecchio di motore (commit) → POI il
    salvataggio respinto, che salva le nuove ipotesi (bump di `assumptions.updated_at`) ma
    rollback-a la generazione, lasciando intatto l'`engine_meta` appena forzato."""
    from backend.app.services import assumptions_service
    from database.models import BalanceSheet, BudgetScenario, Company, FinancialYear, ForecastYear, IncomeStatement
    from tests.e2e_kit import memory_sessions
    from tests.rilievi_kit import BASE_CE
    engine, sessions = memory_sessions()
    try:
        with sessions() as db:
            company = Company(name="AMBIENTA", tax_id="AMBIENTA2026", sector=1, user_id="rilievi")
            db.add(company); db.flush()
            fy = FinancialYear(company_id=company.id, year=2026, period_months=None,
                               validation_status="verified", forecastable=True)
            db.add(fy); db.flush()
            db.add(BalanceSheet(financial_year_id=fy.id, **BASE_BS))
            db.add(IncomeStatement(financial_year_id=fy.id, **BASE_CE))
            db.commit()
            sc = BudgetScenario(company_id=company.id, name="rilievi", base_year=2026, scenario_type="budget")
            db.add(sc); db.commit()
            r0 = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in righe()],
                                                              auto_generate=True)
            if r0["forecast_generated"] is not True:
                pytest.fail(f"precondizione: il previsionale iniziale non si genera: {r0['message']}")
            rows = db.query(ForecastYear).filter(ForecastYear.scenario_id == sc.id).all()
            assert rows, "precondizione: nessun ForecastYear da ritoccare"
            rows[0].engine_meta = {"engine_version": "1", "pareggio": None}
            db.commit()
            respinte = righe()
            banche = BASE_BS["sp16a_debiti_banche_breve"] + BASE_BS["sp17a_debiti_banche_lungo"]
            respinte[0].update(_banche(311000, float(banche - D("300000"))))
            res = assumptions_service.bulk_upsert_assumptions(db, sc.id, [dict(r) for r in respinte],
                                                               auto_generate=True)
            if res["forecast_generated"] is not False:
                pytest.fail("precondizione: il salvataggio doveva essere respinto")
            from backend.app.renderers.business_plan.data import from_report
            from backend.app.services.final_report_service import assemble_final_report
            rep = assemble_final_report(db, company.id, sc.id, schema_version=2)
            data = from_report(rep, draft=True)
            return rep, data
    finally:
        engine.dispose()


def _header_company_name_fit(data) -> str:
    """La stessa logica di `_body_page.on_page()` (document.py), fuori dal canvas: cosa disegnerebbe
    per il nome azienda nell'intestazione di una pagina interna, dato lo spazio che resta dopo il
    testo di destra."""
    from backend.app.renderers.business_plan import theme
    from backend.app.renderers.business_plan.document import page_texts
    from backend.app.renderers.business_plan.layout import fit
    theme.register_fonts()
    _, right, _ = page_texts(data)
    room = theme.PAGE_W - 2 * theme.LM - pdfmetrics.stringWidth(right, theme.REGULAR, 9) - 16
    return fit(data.company_name, theme.BOLD, 9, room)


# ------------------------------------------------------------- rilievo 1 (critico)
def test_header_non_tronca_il_nome_con_forecast_stale():
    _bp()
    e = _con_forecast_stale()
    assert _header_company_name_fit(e.data) == "AMBIENTA"


def test_header_non_tronca_il_nome_con_engine_version_stale():
    _bp()
    e = _con_engine_version_stale()
    assert _header_company_name_fit(e.data) == "AMBIENTA"


def test_header_usa_la_forma_corta_non_la_frase_intera():
    """L'header porta «BOZZA · da rigenerare», non la frase intera della spec (quella sta solo in
    copertina, rilievo 1)."""
    _bp()
    from backend.app.renderers.business_plan.document import page_texts
    e = _con_forecast_stale()
    _, right, _ = page_texts(e.data)
    assert "BOZZA · da rigenerare" in right
    assert FRASE_FORECAST_STALE not in right
    assert FRASE_ENGINE_STALE not in right


def test_header_forma_corta_anche_nel_docx():
    """Stessa `page_texts()` per PDF e Word: verifico che il Word non erediti la frase intera nella
    riga di destra dell'intestazione (rilievo 1, «Check the Word output too»)."""
    _bp()
    from docx import Document
    import io
    from backend.app.renderers.business_plan.document import render_business_plan_docx
    e = _con_engine_version_stale()
    doc = Document(io.BytesIO(render_business_plan_docx(e.data)))
    header_text = doc.sections[0].header.paragraphs[0].text
    assert "BOZZA · da rigenerare" in header_text
    assert FRASE_ENGINE_STALE not in header_text
    assert "AMBIENTA" in header_text  # invariato: il nome azienda non si tronca mai nel Word


# ------------------------------------------------------------- rilievo 2 (importante)
def test_copertina_pdf_una_riga_per_avviso_entro_la_larghezza():
    _bp()
    from backend.app.renderers.business_plan import theme
    from backend.app.renderers.business_plan.sections_sintesi import cover_lines
    theme.register_fonts()
    _, data = _con_entrambi_gli_avvisi()
    assert set(data.avvisi) == {FRASE_FORECAST_STALE, FRASE_ENGINE_STALE}
    cl = cover_lines(data)
    assert FRASE_FORECAST_STALE in cl.lines
    assert FRASE_ENGINE_STALE in cl.lines
    # mai unite: ogni frase sta sulla propria riga, e nessuna riga della copertina sfora la CW
    for line in cl.lines:
        assert FRASE_FORECAST_STALE + " · " + FRASE_ENGINE_STALE != line
        assert FRASE_ENGINE_STALE + " · " + FRASE_FORECAST_STALE != line
        assert pdfmetrics.stringWidth(line, theme.REGULAR, 11) <= theme.CW, line


def test_copertina_pdf_si_genera_senza_eccezioni_con_entrambi_gli_avvisi():
    """La prova di fuoco: il documento vero si costruisce (nessun overflow di Platypus/coordinate)
    e il testo estratto porta entrambe le frasi."""
    _bp()
    import fitz
    from backend.app.renderers.business_plan.document import render_business_plan
    _, data = _con_entrambi_gli_avvisi()
    pdf = render_business_plan(data)
    testo = "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))
    assert FRASE_FORECAST_STALE in testo
    assert FRASE_ENGINE_STALE in testo


def test_copertina_docx_una_riga_per_avviso():
    """Stessa `cover_lines()` per il Word: `_cover()` in docx_export.py itera `cover.lines` senza
    limite di lunghezza, quindi ogni frase deve arrivare come paragrafo separato."""
    _bp()
    from backend.app.renderers.business_plan.document import render_business_plan_docx
    from backend.app.renderers.docx_export import docx_text
    _, data = _con_entrambi_gli_avvisi()
    paragrafi = docx_text(render_business_plan_docx(data))
    assert FRASE_FORECAST_STALE in paragrafi
    assert FRASE_ENGINE_STALE in paragrafi
    # non unite in un solo paragrafo
    assert not any(FRASE_FORECAST_STALE in p and FRASE_ENGINE_STALE in p for p in paragrafi)


def test_copertina_singolo_avviso_resta_una_riga_sola():
    """Senza sovrapposizione (un solo avviso), il comportamento di prima non cambia: due righe in
    copertina, non tre."""
    _bp()
    from backend.app.renderers.business_plan.sections_sintesi import cover_lines
    e = _con_forecast_stale()
    cl = cover_lines(e.data)
    assert len(cl.lines) == 2
    assert cl.lines[1] == FRASE_FORECAST_STALE


# ------------------------------------------------------------- rilievo 3 (minore)
def test_report_pulito_diagnostics_senza_forecast_stale_ne_engine_version_stale():
    """Caso (e) di `test_fix_rilievi_report.py`, con l'assert aggiuntivo chiesto dalla review: un
    report pulito non porta nessuna delle due diagnostiche di previsionale vecchio in `diagnostics`
    (non solo `avvisi == ()`)."""
    _bp()
    e = generato(genera(righe(), report=True))
    assert e.data.avvisi == ()
    codici = {d.code for d in e.rep.diagnostics}
    assert "forecast_stale" not in codici
    assert "engine_version_stale" not in codici
