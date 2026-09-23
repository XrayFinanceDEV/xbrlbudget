"""Il pass CoGe di route C sceglie il fornitore da PDF_LLM_PROVIDER_COGE.

Nessuna rete: la chiamata a gx10 si sostituisce con monkeypatch.
"""
from decimal import Decimal

import fitz
import pytest

from importers import llm_provider, pdf_extractor_llm as P
from importers.llm_provider import LLMProviderError

# ATTENZIONE: PDFImportError e' definita DUE volte, in pdf_extractor_llm.py:29 e in
# pdf_importer.py:51, e sono classi diverse. extract_trial_balance_with_llm solleva quella
# dell'estrattore: e' quella che i test devono aspettarsi.
PDFImportError = P.PDFImportError


def _pdf(tmp_path, righe):
    doc = fitz.open()
    pagina = doc.new_page()
    for i, riga in enumerate(righe):
        pagina.insert_text((40, 60 + 14 * i), riga, fontsize=9)
    percorso = tmp_path / "situazione.pdf"
    doc.save(str(percorso))
    return str(percorso)


RIGHE = ["SITUAZIONE PATRIMONIALE AL 31/12/2025",
         "ATTIVITA'                                   PASSIVITA'",
         "Cassa contanti      1.000,00        Fornitori      1.000,00",
         "TOTALE ATTIVITA'    1.000,00        TOTALE PASSIVITA'  1.000,00"]


def _finto_gx10(chiamate):
    def finto(system_prompt, testo_utente, output_model, *, max_tokens, **_):
        chiamate.append((output_model.__name__, testo_utente))
        if output_model is P.BalanceSheetExtraction:
            return P.BalanceSheetExtraction(sp09_disponibilita_liquide=Decimal("1000"),
                                            sp16d_debiti_fornitori_breve=Decimal("1000"),
                                            totale_attivo=Decimal("1000"),
                                            totale_passivo=Decimal("1000"))
        return P.IncomeStatementExtraction()
    return finto


def test_con_gx10_non_serve_la_chiave_anthropic_e_anthropic_non_si_chiama(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    chiamate = []
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato", _finto_gx10(chiamate))
    monkeypatch.setattr(P.anthropic, "Anthropic",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Anthropic chiamato")))
    bs, ce = P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))
    assert bs["sp09_disponibilita_liquide"] == Decimal("1000")
    nomi = [c[0] for c in chiamate]
    assert "BalanceSheetExtraction" in nomi and "IncomeStatementExtraction" in nomi
    assert "Cassa contanti" in chiamate[0][1]          # il testo del documento arriva a gx10


def test_default_resta_anthropic_e_senza_chiave_solleva_come_oggi(tmp_path, monkeypatch):
    monkeypatch.delenv("PDF_LLM_PROVIDER_COGE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("gx10 chiamato")))
    with pytest.raises(PDFImportError, match="ANTHROPIC_API_KEY"):
        P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))


def test_pdf_immagine_con_gx10_e_senza_chiave_anthropic_errore_dichiarato(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(P, "_is_image_pdf", lambda *_: True)
    with pytest.raises(PDFImportError, match="vision"):
        P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))


def test_errore_di_gx10_esce_come_eccezione_non_come_foglio_vuoto(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")

    def giu(*a, **k):
        raise LLMProviderError("gx10 ha risposto 400")
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato", giu)
    with pytest.raises(LLMProviderError):
        P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))


def test_il_retry_di_completezza_tiene_il_draw_col_tappo_piu_piccolo(tmp_path, monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    draw = iter([Decimal("300"), Decimal("5"), Decimal("80")])
    residui = []

    def finto(system_prompt, testo_utente, output_model, *, max_tokens, **_):
        if output_model is P.BalanceSheetExtraction:
            return P.BalanceSheetExtraction(totale_attivo=Decimal("1000"),
                                            totale_passivo=Decimal("1000"))
        return P.IncomeStatementExtraction()
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato", finto)
    originale = P._reconcile_trial_to_declared

    def con_residuo(bs, declared, source, **kw):
        bs = dict(bs)
        bs["_plug_residual"] = next(draw)
        residui.append(bs["_plug_residual"])
        return bs
    monkeypatch.setattr(P, "_reconcile_trial_to_declared", con_residuo)
    bs, _ = P.extract_trial_balance_with_llm(_pdf(tmp_path, RIGHE))
    assert bs["_plug_residual"] == min(residui)


from importers import pdf_importer


def test_coge_attivo_anthropic_segue_la_chiave(monkeypatch):
    monkeypatch.delenv("PDF_LLM_PROVIDER_COGE", raising=False)
    assert pdf_importer._coge_attivo("sk-qualcosa") is True
    assert pdf_importer._coge_attivo("") is False


def test_coge_attivo_gx10_segue_la_chiave_gx10_non_quella_anthropic(monkeypatch):
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    assert pdf_importer._coge_attivo("") is True
    monkeypatch.setenv("GX10_API_KEY", "")
    assert pdf_importer._coge_attivo("sk-qualcosa") is False


# ATTENZIONE: "TOTALE A PAREGGIO" e' il marker che bilancio_classifier.classify_bilancio
# usa per instradare alla route C (s["pareggio"]); RIGHE (sopra) non lo porta e da sola
# classifica UNSUPPORTED, quindi i due test end-to-end sotto usano questa variante.
RIGHE_PAREGGIO = RIGHE + ["TOTALE A PAREGGIO   1.000,00"]


def _db_in_memoria(monkeypatch):
    """Sessione SQLite in RAM, agganciata a pdf_importer.SessionLocal come negli altri
    test end-to-end (vedi tests/test_reliability_gating.py)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", session_factory)
    return session_factory


def _coge_provider_persistito(session_factory, company_id, fiscal_year):
    """Rilegge il validation_report DALLA RIGA PERSISTITA (non dal dict del risultato):
    prova che la dichiarazione sopravvive al commit, non solo alla risposta dell'import."""
    import json as _json

    from database.models import FinancialYear

    with session_factory() as db:
        fy = db.query(FinancialYear).filter_by(
            company_id=company_id, year=fiscal_year).one()
        return _json.loads(fy.validation_report)["coge_provider"]


def test_route_c_senza_chiave_anthropic_con_gx10_dichiara_il_fornitore(tmp_path, monkeypatch):
    """Prova che validation_report["coge_provider"] arriva sia nel risultato SIA nella riga
    persistita (rileggibile da un GET successivo, senza rieseguire l'import): l'intera route C
    (classificazione + pass CoGe + persistenza) gira SENZA ANTHROPIC_API_KEY quando il
    fornitore e' gx10, e dichiara "gx10" — non solo quando gx10 vince il confronto col
    candidato deterministico, ma su ogni import di route C."""
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm_provider, "chiama_gx10_strutturato", _finto_gx10([]))
    session_factory = _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Route C gx10", create_company=True, sector=1,
        user_id="route-c-gx10", period_months=12,
    )
    assert result["validation_report"]["coge_provider"] == "gx10"
    # Non solo il risultato dell'import: anche la riga scritta sul DB, cioe' quella che
    # legge un GET fatto DOPO, a chiamata dell'import ormai finita.
    assert _coge_provider_persistito(session_factory, result["company_id"], 2025) == "gx10"
    # Questa fixture e' a colonna singola (nessuna colonna anno precedente nel testo): non
    # produce un anno precedente, quindi non c'e' una seconda riga da verificare qui.
    assert result["prior_year_imported"] is False


def test_route_c_default_anthropic_senza_chiave_dichiara_anthropic_e_non_chiama_il_pass_coge(
        tmp_path, monkeypatch):
    """Col fornitore di default, senza chiave Anthropic il pass CoGe non parte affatto
    (_coge_attivo lo blocca) — ma la chiave dichiarata resta "anthropic", sia nel risultato
    sia nella riga persistita: e' il fornitore CONFIGURATO, non la prova che il pass abbia
    girato."""
    monkeypatch.delenv("PDF_LLM_PROVIDER_COGE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        P, "extract_trial_balance_with_llm",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("pass CoGe chiamato senza chiave")))
    session_factory = _db_in_memoria(monkeypatch)

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Route C anthropic default", create_company=True, sector=1,
        user_id="route-c-anthropic", period_months=12,
    )
    assert result["validation_report"]["coge_provider"] == "anthropic"
    assert _coge_provider_persistito(session_factory, result["company_id"], 2025) == "anthropic"
    assert result["prior_year_imported"] is False
