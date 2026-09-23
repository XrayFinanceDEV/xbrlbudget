"""ivcee_provider e dettagli_provider si dichiarano nel validation_report persistito
di OGNI route, non solo route C (dove coge_provider gia' esiste). Sono il fornitore
CONFIGURATO da PDF_LLM_PROVIDER_IVCEE/PDF_LLM_PROVIDER_DETTAGLI, come per coge_provider:
la dichiarazione non prova che il pass sia stato invocato.

Nessuna rete: la fixture di route A/B (_write_compact_infrannual_pdf) e' letta dal
parser deterministico standard_ivcee_parser, senza bisogno di ANTHROPIC_API_KEY (vedi
tests/test_http_full_cycle.py, stessa fixture, stessa assenza di chiave). Route C
riusa RIGHE_PAREGGIO/_finto_gx10 di tests/test_coge_provider.py.
"""
import json

from importers import llm_provider, pdf_importer
from tests.test_coge_provider import RIGHE_PAREGGIO, _finto_gx10, _pdf
from tests.test_standard_ivcee_parser import _write_compact_infrannual_pdf


def _db_in_memoria(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", session_factory)
    return session_factory


def _validation_report_persistito(session_factory, company_id, fiscal_year):
    from database.models import FinancialYear

    with session_factory() as db:
        fy = db.query(FinancialYear).filter_by(
            company_id=company_id, year=fiscal_year).one()
        return json.loads(fy.validation_report)


def test_route_ab_dichiara_i_fornitori_di_default_senza_chiave_anthropic(tmp_path, monkeypatch):
    """Route A/B (non trial balance): la fixture compatta non ha bisogno dell'LLM per
    quadrare (parser deterministico), ma i due campi si dichiarano comunque col valore
    di default, sia nel risultato sia nella riga persistita."""
    monkeypatch.delenv("PDF_LLM_PROVIDER_IVCEE", raising=False)
    monkeypatch.delenv("PDF_LLM_PROVIDER_DETTAGLI", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    session_factory = _db_in_memoria(monkeypatch)
    pdf = tmp_path / "compatta.pdf"
    _write_compact_infrannual_pdf(pdf)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=str(pdf), fiscal_year=2026, period_months=6,
        company_name="Route AB default", create_company=True, sector=1,
        user_id="route-ab-default",
    )
    assert result["validation_report"]["ivcee_provider"] == "anthropic"
    assert result["validation_report"]["dettagli_provider"] == "anthropic"
    # coge_provider non esiste affatto fuori da route C.
    assert "coge_provider" not in result["validation_report"]

    persistito = _validation_report_persistito(session_factory, result["company_id"], 2026)
    assert persistito["ivcee_provider"] == "anthropic"
    assert persistito["dettagli_provider"] == "anthropic"


def test_route_ab_dichiara_gx10_quando_configurato(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
    monkeypatch.setenv("PDF_LLM_PROVIDER_DETTAGLI", "gx10")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    session_factory = _db_in_memoria(monkeypatch)
    pdf = tmp_path / "compatta.pdf"
    _write_compact_infrannual_pdf(pdf)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=str(pdf), fiscal_year=2026, period_months=6,
        company_name="Route AB gx10", create_company=True, sector=1,
        user_id="route-ab-gx10",
    )
    assert result["validation_report"]["ivcee_provider"] == "gx10"
    assert result["validation_report"]["dettagli_provider"] == "gx10"
    persistito = _validation_report_persistito(session_factory, result["company_id"], 2026)
    assert persistito["ivcee_provider"] == "gx10"
    assert persistito["dettagli_provider"] == "gx10"


def test_route_c_dichiara_tutti_e_tre_i_fornitori_accanto(tmp_path, monkeypatch):
    """Route C ha gia' coge_provider (test_coge_provider.py): qui si prova che
    ivcee_provider e dettagli_provider compaiono ACCANTO ad esso, non al suo posto."""
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.delenv("PDF_LLM_PROVIDER_IVCEE", raising=False)
    monkeypatch.delenv("PDF_LLM_PROVIDER_DETTAGLI", raising=False)
    monkeypatch.setenv("GX10_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato", _finto_gx10([]))
    session_factory = _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Route C provenienza", create_company=True, sector=1,
        user_id="route-c-provenienza", period_months=12,
    )
    vr = result["validation_report"]
    assert vr["coge_provider"] == "gx10"
    assert vr["ivcee_provider"] == "anthropic"
    assert vr["dettagli_provider"] == "anthropic"
    persistito = _validation_report_persistito(session_factory, result["company_id"], 2025)
    assert persistito["coge_provider"] == "gx10"
    assert persistito["ivcee_provider"] == "anthropic"
    assert persistito["dettagli_provider"] == "anthropic"
