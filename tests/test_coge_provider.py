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
