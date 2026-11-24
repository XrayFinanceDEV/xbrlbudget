"""Rilievo Critical (revisione finale, 2026-09-23): con PDF_LLM_PROVIDER_IVCEE=gx10 e
GX10_API_KEY impostata ma ANTHROPIC_API_KEY assente, l'import di route A/B (bilancio
IV-CEE che il parser deterministico NON risolve) si fermava PRIMA di arrivare al ramo
gx10, con "ANTHROPIC_API_KEY is required for PDF import" — il cancello in
_llm_extract() (importers/pdf_importer.py) guardava solo ANTHROPIC_API_KEY.

Questo test passa DA import_pdf_balance_sheet() (non attorno): forza la classificazione
a ROUTE_IVCEE, fa fallire i parser deterministici (extract_standard_ivcee_balances e
analyze_pdf_macros) cosi' l'estrazione arriva davvero al ramo LLM testuale di
pdf_extractor_llm.extract_pdf_with_llm, e sostituisce SOLO le chiamate di rete
(_extract_with_llm) — non le funzioni extract_pdf_with_llm/extract_pdf_both_years_with_llm
stesse — cosi' il cancello corretto in pdf_extractor_llm.py e' davvero esercitato.

Nessuna rete: harness in memoria come tests/test_provenienza_llm.py.
"""
from decimal import Decimal

import fitz
import pytest

from importers import bilancio_classifier as classifier
from importers import macro_analysis
from importers import pdf_extractor_llm as P
# le estrazioni cercano queste funzioni nel proprio modulo: si sostituiscono li', non nella facciata
from importers.estrazione_llm import ivcee as IV
from importers import pdf_importer as importer
from importers import standard_ivcee_parser as standard

from tests.test_provenienza_llm import _db_in_memoria, _validation_report_persistito

PDFImportError = importer.PDFImportError


def _pdf(tmp_path):
    """PDF minimo di route A/B: testo reale (non scansione) ma senza una struttura
    IV-CEE che i parser deterministici possano leggere — costringe al ramo LLM."""
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((40, 60), "STATO PATRIMONIALE 2026", fontsize=9)
    pagina.insert_text((40, 80), "bilancio senza struttura leggibile dal parser deterministico", fontsize=9)
    percorso = tmp_path / "route_ab.pdf"
    doc.save(str(percorso))
    doc.close()
    return str(percorso)


def _finto_extract_with_llm(chiamate):
    """Sostituisce pdf_extractor_llm._extract_with_llm: registra il fornitore ricevuto
    e restituisce uno SP/CE che quadra, cosi' il resto della pipeline di import (mapper,
    quadratura, finalizzazione residui, persistenza) puo' girare fino in fondo."""
    def finto(client, text, system_prompt, output_model, section_name, tool_name,
              max_retries=2, provider="anthropic"):
        chiamate.append((output_model.__name__, provider))
        if output_model is P.BalanceSheetExtraction:
            return P.BalanceSheetExtraction(
                sp05_rimanenze=Decimal("100"),
                sp06_crediti_breve=Decimal("200"),
                sp11_capitale=Decimal("300"),
                totale_attivo=Decimal("300"),
                totale_passivo=Decimal("300"),
            )
        if output_model is P.IncomeStatementExtraction:
            return P.IncomeStatementExtraction(
                ce01_ricavi_vendite=Decimal("50"),
                ce08_costi_personale=Decimal("50"),
            )
        raise AssertionError(f"output_model inatteso: {output_model}")
    return finto


@pytest.fixture
def route_ab_non_risolta_dal_deterministico(monkeypatch, tmp_path):
    """Instrada a ROUTE_IVCEE e fa fallire ENTRAMBI i parser deterministici (fonte
    standard e macro-voci), cosi' _llm_extract() arriva davvero a extract_pdf_with_llm.
    Non tocca ANTHROPIC_API_KEY / PDF_LLM_PROVIDER_IVCEE: li imposta il singolo test."""
    monkeypatch.setattr(classifier, "classify_bilancio", lambda **kw: classifier.Classification(
        "A", "synthetic", classifier.ROUTE_IVCEE, "test", "high", {}, "test"))
    monkeypatch.setattr(standard, "extract_standard_ivcee_balances", lambda *a, **k: (None, None))
    monkeypatch.setattr(standard, "extract_standard_ivcee_income", lambda *a, **k: (None, None))
    monkeypatch.setattr(standard, "has_comparative_ivcee_columns", lambda *a, **k: False)

    def _macro_fallisce(*a, **k):
        raise macro_analysis.MacroAnalysisError({"errors": ["nessuna macrovoce riconosciuta"]})
    monkeypatch.setattr(macro_analysis, "analyze_pdf_macros", _macro_fallisce)

    monkeypatch.setattr(IV, "_is_image_pdf", lambda *_: False)
    monkeypatch.setattr(IV, "extract_relevant_pages", lambda *_: ("SP testo", "CE testo"))
    return tmp_path


def test_gx10_senza_chiave_anthropic_raggiunge_il_ramo_gx10(
    route_ab_non_risolta_dal_deterministico, monkeypatch,
):
    """RED prima della correzione: sollevava PDFImportError('ANTHROPIC_API_KEY is
    required for PDF import') prima ancora di provare gx10."""
    tmp_path = route_ab_non_risolta_dal_deterministico
    monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(P.anthropic, "Anthropic",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Anthropic chiamato")))
    chiamate = []
    monkeypatch.setattr(IV, "_extract_with_llm", _finto_extract_with_llm(chiamate))
    session_factory = _db_in_memoria(monkeypatch)

    result = importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path), fiscal_year=2026, period_months=6,
        company_name="Route AB gx10 senza chiave", create_company=True, sector=1,
        user_id="route-ab-gx10-senza-chiave",
    )

    nomi_forniti = [(nome, fornitore) for nome, fornitore in chiamate]
    assert ("BalanceSheetExtraction", "gx10") in nomi_forniti
    assert ("IncomeStatementExtraction", "gx10") in nomi_forniti
    assert result["validation_report"]["ivcee_provider"] == "gx10"
    persistito = _validation_report_persistito(session_factory, result["company_id"], 2026)
    assert persistito["ivcee_provider"] == "gx10"


def test_provider_anthropic_di_default_senza_chiave_solleva_come_oggi(
    route_ab_non_risolta_dal_deterministico, monkeypatch,
):
    """Controllo: senza PDF_LLM_PROVIDER_IVCEE=gx10 il fornitore resta Anthropic, e
    senza chiave l'errore e' esattamente quello di oggi."""
    tmp_path = route_ab_non_risolta_dal_deterministico
    monkeypatch.delenv("PDF_LLM_PROVIDER_IVCEE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(IV, "_extract_with_llm",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM chiamato")))
    _db_in_memoria(monkeypatch)

    with pytest.raises(PDFImportError, match="ANTHROPIC_API_KEY is required for PDF import"):
        importer.import_pdf_balance_sheet(
            file_path=_pdf(tmp_path), fiscal_year=2026, period_months=6,
            company_name="Route AB anthropic senza chiave", create_company=True, sector=1,
            user_id="route-ab-anthropic-senza-chiave",
        )


def test_un_attivo_letto_col_passivo_tutto_a_zero_e_una_lettura_mancante_non_si_salva(
    route_ab_non_risolta_dal_deterministico, monkeypatch,
):
    """Lotto week-43 (1423/1418): vLLM ometteva sp11-sp18, pydantic li riempiva a zero e il
    bilancio si salvava "unbalanced" col passivo a zero. E' una lettura mancante: si rifiuta."""
    tmp_path = route_ab_non_risolta_dal_deterministico
    monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def finto(client, text, system_prompt, output_model, section_name, tool_name,
              max_retries=2, provider="anthropic"):
        if output_model is P.BalanceSheetExtraction:
            return P.BalanceSheetExtraction(sp05_rimanenze=Decimal("100"),
                                            sp06_crediti_breve=Decimal("200"),
                                            totale_attivo=Decimal("300"))
        return P.IncomeStatementExtraction(ce01_ricavi_vendite=Decimal("50"))
    monkeypatch.setattr(IV, "_extract_with_llm", finto)
    _db_in_memoria(monkeypatch)

    with pytest.raises(PDFImportError, match="passivo mancante"):
        importer.import_pdf_balance_sheet(
            file_path=_pdf(tmp_path), fiscal_year=2026, period_months=6,
            company_name="Passivo a zero", create_company=True, sector=1,
            user_id="passivo-a-zero",
        )



def test_uno_stato_patrimoniale_vuoto_non_si_rilegge_altre_due_volte(
    route_ab_non_risolta_dal_deterministico, monkeypatch,
):
    """budget_1667: un prospetto senza SP letto vuoto dalla lettura a un anno E da quella a
    due anni non si rilegge: altri due giri davano lo stesso vuoto, dopo dieci minuti."""
    tmp_path = route_ab_non_risolta_dal_deterministico
    monkeypatch.setenv("PDF_LLM_PROVIDER_IVCEE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "x")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(importer, "has_comparative_ivcee_columns", lambda *_: True, raising=False)
    monkeypatch.setattr(standard, "has_comparative_ivcee_columns", lambda *a, **k: True)
    letture = []

    def un_anno(*a, **k):
        letture.append("un anno")
        return {}, {"ce01_ricavi_vendite": Decimal("50")}

    def due_anni(*a, **k):
        letture.append("due anni")
        return {}, {"ce01_ricavi_vendite": Decimal("50")}, {}, {}

    monkeypatch.setattr(P, "extract_pdf_with_llm", un_anno)
    monkeypatch.setattr(P, "extract_pdf_both_years_with_llm", due_anni)
    _db_in_memoria(monkeypatch)

    with pytest.raises(PDFImportError):
        importer.import_pdf_balance_sheet(
            file_path=_pdf(tmp_path), fiscal_year=2025,
            company_name="SP vuoto", create_company=True, sector=1,
            user_id="sp-vuoto",
        )

    assert letture == ["un anno", "due anni"]
