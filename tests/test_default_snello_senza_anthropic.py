"""Default di produzione (decisione del proprietario, 2026-10-16): percorso snello per tutti,
nessun servizio Anthropic se non chiesto esplicitamente con ANTHROPIC_CONSENTITO=1."""
import pytest

from importers import llm_provider, pdf_importer


@pytest.fixture
def default_produzione(monkeypatch):
    for nome in ("ANTHROPIC_CONSENTITO", "IMPORT_MOTORE", "PDF_LLM_PROVIDER_COGE",
                 "PDF_LLM_PROVIDER_IVCEE", "PDF_LLM_PROVIDER_DETTAGLI"):
        monkeypatch.delenv(nome, raising=False)


def test_senza_variabili_il_motore_e_snello(default_produzione):
    assert pdf_importer._motore_snello() is True


def test_classico_si_chiede_esplicitamente(default_produzione, monkeypatch):
    monkeypatch.setenv("IMPORT_MOTORE", "classico")
    assert pdf_importer._motore_snello() is False


def test_senza_consenso_ogni_fase_va_su_gx10(default_produzione, monkeypatch):
    assert llm_provider.anthropic_consentito() is False
    assert llm_provider.provider_coge() == "gx10"
    assert llm_provider.provider_ivcee() == "gx10"
    assert llm_provider.provider_dettagli() == "gx10"
    # nemmeno un valore esplicito "anthropic" la riaccende senza consenso
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "anthropic")
    assert llm_provider.provider_coge() == "gx10"


def test_senza_gx10_il_lettore_dettagli_non_ripiega_su_anthropic(default_produzione, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "una-chiave")
    monkeypatch.setenv("GX10_API_KEY", "")
    assert llm_provider.lettore_dettagli_disponibile() is False


def test_con_consenso_il_comportamento_di_prima(default_produzione, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_CONSENTITO", "1")
    assert llm_provider.provider_coge() == "anthropic"
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    assert llm_provider.provider_coge() == "gx10"


def test_la_mappa_della_struttura_va_su_gx10_senza_consenso(default_produzione, monkeypatch, tmp_path):
    import fitz
    from importers.struttura_documento import mappa

    chiamate = []

    def finta_gx10(system, messaggi, schema, *, max_tokens, timeout=900.0, transport=None):
        parti = messaggi[0]["content"]
        assert any(p.get("type") == "image_url" for p in parti)
        chiamate.append(1)
        return {"tipo_pagina": "prospetto_sp", "disposizione": "colonna_unica",
                "schema": "iv_cee_di_legge", "sezioni": [], "continuazione": False,
                "codici_conto": False, "totali_stampati": True, "anno_precedente": False,
                "negativi": "segno_meno", "fondi_ammortamento": "assenti", "note": ""}

    def vietato(*a, **k):
        raise AssertionError("client Anthropic creato senza consenso")

    monkeypatch.setattr(llm_provider, "chiama_gx10_json", finta_gx10)
    monkeypatch.setattr(mappa, "_client", vietato)
    pdf = tmp_path / "p.pdf"
    doc = fitz.open()
    pagina = doc.new_page()
    y = 72
    pagina.insert_text((72, y), "STATO PATRIMONIALE")
    for i in range(8):
        y += 14
        pagina.insert_text((72, y), f"Voce {i}")
        pagina.insert_text((400, y), f"{i + 1}.{i}50,00")
    doc.save(pdf)
    mappe = mappa.mappa_documento(str(pdf))
    assert chiamate and mappe[0]["tipo_pagina"] == "prospetto_sp"


def test_senza_consenso_la_chiave_anthropic_risulta_vuota(default_produzione, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "una-chiave")
    assert llm_provider.chiave_anthropic() == ""
    monkeypatch.setenv("ANTHROPIC_CONSENTITO", "1")
    assert llm_provider.chiave_anthropic() == "una-chiave"


def test_senza_consenso_creare_un_client_anthropic_solleva(default_produzione):
    with pytest.raises(llm_provider.AnthropicVietato, match="fase saltata"):
        llm_provider.vieta_anthropic("prova")
