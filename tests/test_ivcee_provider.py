"""L'estrattore testuale di route A/B (IV-CEE) sceglie il fornitore da
PDF_LLM_PROVIDER_IVCEE, sia per extract_pdf_with_llm sia per
extract_pdf_both_years_with_llm. La vision resta su Anthropic in ogni caso.

Nessuna rete: _extract_with_llm/_extract_with_llm_vision sono sostituite con finte.
"""
from decimal import Decimal

import fitz
import pytest

from importers import pdf_extractor_llm as P

PDFImportError = P.PDFImportError


def _pdf(tmp_path, nome="bilancio.pdf"):
    """PDF minimo, non-situazione-contabile: nessun codice XX/YY/ZZZ o AGO, quindi
    is_situazione_contabile lo lascia passare alla route A/B come da instradamento
    corrente (non modificato in questo task)."""
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((40, 60), "STATO PATRIMONIALE", fontsize=9)
    pagina.insert_text((40, 80), "Nessun dato rilevante", fontsize=9)
    percorso = tmp_path / nome
    doc.save(str(percorso))
    doc.close()
    return str(percorso)


def _finto_extract_with_llm(chiamate):
    def finto(client, text, system_prompt, output_model, section_name, tool_name,
              max_retries=2, provider="anthropic"):
        chiamate.append((output_model, provider))
        if output_model is P.BalanceSheetExtraction:
            return P.BalanceSheetExtraction()
        if output_model is P.IncomeStatementExtraction:
            return P.IncomeStatementExtraction()
        if output_model is P.TwoYearBalanceSheetExtraction:
            return P.TwoYearBalanceSheetExtraction(
                current_year=P.BalanceSheetExtraction(),
                prior_year=P.BalanceSheetExtraction(),
            )
        if output_model is P.TwoYearIncomeStatementExtraction:
            return P.TwoYearIncomeStatementExtraction(
                current_year=P.IncomeStatementExtraction(),
                prior_year=P.IncomeStatementExtraction(),
            )
        raise AssertionError(f"output_model inatteso: {output_model}")
    return finto


def _monkeypatch_testo(monkeypatch, tmp_path, chiamate):
    """Instrada al ramo testuale: PDF non-immagine, testo SP/CE finto, chiamata LLM finta."""
    monkeypatch.setattr(P, "_is_image_pdf", lambda *_: False)
    monkeypatch.setattr(P, "extract_relevant_pages", lambda *_: ("SP testo", "CE testo"))
    monkeypatch.setattr(P, "_extract_with_llm", _finto_extract_with_llm(chiamate))
    monkeypatch.setattr(
        P, "_extract_with_llm_vision",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("vision chiamata sul ramo testuale")))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


class TestExtractPdfWithLlm:
    def test_senza_variabile_provider_e_anthropic(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PDF_LLM_PROVIDER_IVCEE", raising=False)
        chiamate = []
        _monkeypatch_testo(monkeypatch, tmp_path, chiamate)
        P.extract_pdf_with_llm(_pdf(tmp_path))
        assert len(chiamate) == 2
        assert all(provider == "anthropic" for _, provider in chiamate)

    def test_con_provider_gx10_entrambe_le_chiamate_usano_gx10(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
        chiamate = []
        _monkeypatch_testo(monkeypatch, tmp_path, chiamate)
        P.extract_pdf_with_llm(_pdf(tmp_path))
        assert len(chiamate) == 2
        assert all(provider == "gx10" for _, provider in chiamate)
        nomi = [m.__name__ for m, _ in chiamate]
        assert "BalanceSheetExtraction" in nomi and "IncomeStatementExtraction" in nomi

    def test_pdf_immagine_con_gx10_la_vision_resta_su_anthropic(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        chiamate_testo = []
        chiamate_vision = []
        monkeypatch.setattr(P, "_is_image_pdf", lambda *_: True)
        monkeypatch.setattr(P, "_render_pdf_pages_as_images", lambda *_: ["img"])
        monkeypatch.setattr(P, "_extract_with_llm", _finto_extract_with_llm(chiamate_testo))

        def finta_vision(client, images, system_prompt, output_model, section_name,
                          tool_name, max_retries=2):
            chiamate_vision.append(output_model)
            if output_model is P.BalanceSheetExtraction:
                return P.BalanceSheetExtraction()
            return P.IncomeStatementExtraction()
        monkeypatch.setattr(P, "_extract_with_llm_vision", finta_vision)

        P.extract_pdf_with_llm(_pdf(tmp_path))

        assert chiamate_testo == []  # _extract_with_llm mai chiamata sul ramo vision
        assert len(chiamate_vision) == 2


class TestExtractPdfBothYearsWithLlm:
    def test_senza_variabile_provider_e_anthropic(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PDF_LLM_PROVIDER_IVCEE", raising=False)
        chiamate = []
        _monkeypatch_testo(monkeypatch, tmp_path, chiamate)
        P.extract_pdf_both_years_with_llm(_pdf(tmp_path))
        assert len(chiamate) == 2
        assert all(provider == "anthropic" for _, provider in chiamate)

    def test_con_provider_gx10_entrambe_le_chiamate_usano_gx10(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
        chiamate = []
        _monkeypatch_testo(monkeypatch, tmp_path, chiamate)
        P.extract_pdf_both_years_with_llm(_pdf(tmp_path))
        assert len(chiamate) == 2
        assert all(provider == "gx10" for _, provider in chiamate)
        nomi = [m.__name__ for m, _ in chiamate]
        assert "TwoYearBalanceSheetExtraction" in nomi and "TwoYearIncomeStatementExtraction" in nomi

    def test_pdf_immagine_con_gx10_la_vision_resta_su_anthropic(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        chiamate_testo = []
        chiamate_vision = []
        monkeypatch.setattr(P, "_is_image_pdf", lambda *_: True)
        monkeypatch.setattr(P, "_render_pdf_pages_as_images", lambda *_: ["img"])
        monkeypatch.setattr(P, "_extract_with_llm", _finto_extract_with_llm(chiamate_testo))

        def finta_vision(client, images, system_prompt, output_model, section_name,
                          tool_name, max_retries=2):
            chiamate_vision.append(output_model)
            if output_model is P.TwoYearBalanceSheetExtraction:
                return P.TwoYearBalanceSheetExtraction(
                    current_year=P.BalanceSheetExtraction(),
                    prior_year=P.BalanceSheetExtraction(),
                )
            return P.TwoYearIncomeStatementExtraction(
                current_year=P.IncomeStatementExtraction(),
                prior_year=P.IncomeStatementExtraction(),
            )
        monkeypatch.setattr(P, "_extract_with_llm_vision", finta_vision)

        P.extract_pdf_both_years_with_llm(_pdf(tmp_path))

        assert chiamate_testo == []
        assert len(chiamate_vision) == 2
