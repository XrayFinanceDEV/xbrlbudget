"""Situazione contabile a sezioni contrapposte letta dalle tabelle di MinerU, senza modello
(Unicarton 31/08/2026). Tabelle finte con la forma vera di MinerU 3.4.5: sei celle per riga,
righe di piede con celle unite e importi spezzati."""
import os
from decimal import Decimal as D
from types import SimpleNamespace

from importers.mineru_adapter import MinerUCell, MinerURow, MinerUTable
from importers.mineru_contrapposte import _coppie_di_piede, pdf_da_tabelle
from importers.situazione_contabile_parser import extract_situazione_contabile


def _tabella(caption, righe):
    rows = tuple(
        MinerURow(cells=tuple(MinerUCell(text=t, row=i, column=j, page=0)
                              for j, t in enumerate(r)), page=0, source_block_id=f"b{i}")
        for i, r in enumerate(righe))
    return MinerUTable(html="", caption=caption, page=0, rows=rows)


SP = _tabella("STATO PATRIMONIALE", [
    ["Attività", "Passività"],
    ["Conto", "Descrizione", "Importo", "Conto", "Descrizione", "Importo"],
    ["05", "IMMOBILIZZAZIONI MATERIALI", "500.000,00", "23", "CAPITALE SOCIALE", "100.000,00"],
    ["05.01", "Macchinari", "500.000,00", "29", "FONDO TFR", "50.000,00"],
    ["11", "CREDITI COMMERCIALI", "300.000,00", "33", "DEBITI COMMERCIALI", "600.000,00"],
    ["11.01", "Clienti Italia", "300.000,00", "33.01", "Fornitori Italia", "600.000,00"],
    ["19", "DISPONIBILITA' LIQUIDE", "200.000,00", "41", "FONDI AMMORTAMENTO", "100.000,00"],
    ["19.01", "Banca c/c", "200.000,00", "41.01", "F.do ammortamento macchinari", "100.000,00", ""],
    ["", "Totale attività", "1.000.000,00",
     "Totale passività                              850.000,00"],
    ["", "Eccedenza esercizio precedente               90.000,00"],
    ["", "Eccedenza (Utile)                                 60.000,00"],
    ["Totale a quadratura                           1.000.000,00", "1.000.000,00"],
])
CE = _tabella("CONTO ECONOMICO", [
    ["Costi", "Ricavi"],
    ["Codice", "Descrizione", "Importo", "Codice", "Descrizione", "Importo"],
    ["55", "ACQUISTI DI BENI", "240.000,00", "47", "RICAVI DELLE VENDITE", "300.000,00"],
    ["55.01", "Acquisti materie prime", "240.000,00", "47.01", "Vendite prodotti", "300.000,00"],
    ["Totale costi                                  240.000,00", "",
     "Totale ricavi                                   300.000", ",00"],
    ["Utile d'esercizio                                 60.000,00", ""],
])


def test_la_situazione_dalle_tabelle_quadra_al_centesimo():
    contesto = SimpleNamespace(tables=(SP, CE))
    percorso = pdf_da_tabelle(contesto)
    try:
        bs, ce = extract_situazione_contabile(percorso)
    finally:
        os.remove(percorso)
    # fondi nettati dal cespite, eccedenza dell'anno prima nel PN, utile = conto economico
    assert bs["sp03"] == D("400000.00")
    assert bs["sp12g_utili_perdite_portati"] == D("90000.00")
    assert bs["sp13"] == D("60000.00")
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("900000.00")
    assert not bs.get("_plug_residual")
    assert ce["ce01"] == D("300000.00")


# La stessa tabella come la spezza MinerU su una scansione di qualita' diversa
# (Unicarton 31/08/2026, versione da 6,5 MB): codice di sinistra su una riga, importo di
# destra su quella dopo, descrizione e importo di sinistra con codice e descrizione di
# destra su una terza.
CE_SPEZZATO = _tabella("CONTO ECONOMICO", [
    ["Costi", "Ricavi"],
    ["Codice", "Descrizione", "Importo", "Codice", "Descrizione", "Importo"],
    ["55", "ACQUISTI DI BENI", "240.000,00", "47", "RICAVI DELLE VENDITE", "", ""],
    ["55.01", "", "", "", "", "", ""],
    ["", "", "", "", "300.000,00"],
    ["Acquisti materie prime", "240.000,00", "47.01", "Vendite prodotti"],
    ["", "", "", "", "300.000,00"],
    ["Totale costi                                  240.000,00", "",
     "Totale ricavi                                   300.000", ",00"],
    ["Utile d'esercizio                                 60.000,00", ""],
])


def test_le_righe_spezzate_da_mineru_si_ricompongono():
    percorso = pdf_da_tabelle(SimpleNamespace(tables=(SP, CE_SPEZZATO)))
    try:
        bs, ce = extract_situazione_contabile(percorso)
    finally:
        os.remove(percorso)
    # prima: ricavi persi, CE in perdita di 240.000 contro un utile SP di 60.000
    assert ce["ce01"] == D("300000.00")
    assert ce["ce05"] == D("240000.00")
    assert bs["sp13"] == D("60000.00")
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("900000.00")


def test_tabelle_senza_forma_contrapposta_non_producono_nulla():
    elenco = _tabella("BILANCIO", [["Conto", "Descrizione", "Saldo"],
                                   ["101", "Cassa", "1.000,00"]])
    assert pdf_da_tabelle(SimpleNamespace(tables=(elenco,))) is None
    assert pdf_da_tabelle(SimpleNamespace(tables=())) is None


def test_il_piede_ricompone_l_importo_spezzato_e_ripete_la_didascalia():
    assert _coppie_di_piede(["Totale costi   240.000,00", "", "Totale ricavi   300.000", ",00"]) == [
        ("Totale costi", "240.000,00"), ("Totale ricavi", "300.000,00")]
    assert _coppie_di_piede(["Totale a quadratura   1.000.000,00", "1.000.000,00"]) == [
        ("Totale a quadratura", "1.000.000,00"), ("Totale a quadratura", "1.000.000,00")]


def test_l_import_di_una_scansione_legge_le_tabelle_e_non_chiama_il_modello(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import fitz
    from database.db import Base
    from importers import pdf_extractor_llm, pdf_importer
    from importers.mineru_adapter import MinerUExtractionContext

    scansione = tmp_path / "scansione.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(scansione)
    doc.close()

    testo = ("Bilancio di verifica al 31/08/2026\nSTATO PATRIMONIALE\nAttività Passività\n"
             "05 IMMOBILIZZAZIONI MATERIALI 500.000,00 23 CAPITALE SOCIALE 100.000,00\n"
             "Totale attività 1.000.000,00 Totale passività 850.000,00\n"
             "CONTO ECONOMICO\nCosti Ricavi\nTotale costi 240.000,00 Totale ricavi 300.000,00\n")
    contesto = MinerUExtractionContext(
        full_text=testo, page_texts=(testo,), rows=(), tables=(SP, CE), headings=(),
        current_year=2026, comparative_year=None, raw_format="test", mineru_version="3.4.5")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # il pass CoGe sarebbe attivo (gx10): non deve partire
    monkeypatch.setenv("PDF_LLM_PROVIDER_COGE", "gx10")
    monkeypatch.setenv("GX10_API_KEY", "finta")
    monkeypatch.setenv("GX10_BASE_URL", "http://127.0.0.1:9")

    def vietato(*a, **k):
        raise AssertionError("CoGe su Qwen chiamato su tabelle MinerU contrapposte")

    monkeypatch.setattr(pdf_extractor_llm, "extract_trial_balance_with_llm", vietato)
    risultato = pdf_importer.import_pdf_balance_sheet(
        file_path=str(scansione), fiscal_year=2026, period_months=8,
        company_name="SCANSIONE", create_company=True, sector=1,
        user_id="u-mineru", extraction_context=contesto)

    assert risultato["extraction_method"] == "mineru+situazione_contabile_mineru"
    assert risultato["validation_status"] == "verified"
    assert risultato["validation_report"]["mineru_contrapposte"] is True
    assert risultato["validation_report"]["ocr"]["accounting_method"] == "situazione_contabile_mineru"


def test_con_lo_snello_acceso_la_scansione_passa_dal_percorso_snello(tmp_path, monkeypatch):
    """Il PDF sintetico delle tabelle MinerU e' un PDF di testo: lo legge il percorso snello
    come ogni altro (stessi lettori deterministici, nessun modello se quadra), invece di
    ripiegare sempre sull'importatore vecchio come quando l'OCR dava solo testo."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import fitz
    from database.db import Base
    from importers import pdf_extractor_llm, pdf_importer
    from importers.mineru_adapter import MinerUExtractionContext
    from importers.struttura_documento import analisi

    scansione = tmp_path / "scansione.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(scansione)
    doc.close()
    testo = ("Bilancio di verifica al 31/08/2026\nSTATO PATRIMONIALE\nAttività Passività\n"
             "CONTO ECONOMICO\nCosti Ricavi\n")
    contesto = MinerUExtractionContext(
        full_text=testo, page_texts=(testo,), rows=(), tables=(SP, CE_SPEZZATO), headings=(),
        current_year=2026, comparative_year=None, raw_format="test", mineru_version="3.4.5")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("IMPORT_MOTORE", "snello")

    def vietato(*a, **k):
        raise AssertionError("modello chiamato su una lettura deterministica che quadra")

    monkeypatch.setattr(pdf_extractor_llm, "extract_trial_balance_with_llm", vietato)
    monkeypatch.setattr(analisi, "analizza_struttura", vietato)
    risultato = pdf_importer.import_pdf_balance_sheet(
        file_path=str(scansione), fiscal_year=2026, period_months=8,
        company_name="SCANSIONE", create_company=True, sector=1,
        user_id="u-mineru-snello", extraction_context=contesto)

    snello = risultato["validation_report"]["import_snello"]
    assert risultato["extraction_method"] == "mineru+import_snello"
    assert snello["fonte_testo"] == "tabelle_mineru"
    assert snello["fonte"] == "deterministico:situazione_contabile_parser"
    assert risultato["validation_status"] == "verified"
