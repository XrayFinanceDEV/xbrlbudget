"""Ogni rifiuto noto dell'import PDF porta un suggerimento: che cosa caricare al suo posto."""
from importers.bilancio_classifier import classify_bilancio
from importers.rifiuti_import import suggerimento_rifiuto


def _categoria(msg):
    s = suggerimento_rifiuto(msg)
    return s and s["categoria"]


def test_i_messaggi_dei_rifiuti_hanno_la_loro_categoria():
    assert _categoria("Il file è un'istanza XBRL nativa: usa l'import XBRL, non l'import PDF.") == "xbrl"
    assert _categoria("Formato non supportato: il documento è un riepilogo aggregato per macro-voci, non uno "
                      "schema di bilancio IV-CEE") == "riepilogo"
    assert _categoria("Il documento è una scansione contabile, ma l'OCR non ha ricostruito in modo affidabile "
                      "colonne, gerarchie e totali.") == "scansione"
    assert _categoria("Failed to import PDF: PDF e' un'immagine: la vision richiede ANTHROPIC_API_KEY") == "scansione"
    assert _categoria("Nessun dato estratto dal documento: lo Stato Patrimoniale risulta vuoto (Totale Attivo "
                      "pari a zero).") == "non_bilancio"
    assert _categoria("Lettura del passivo mancante: il modello ha restituito l'attivo") == "lettura_incompleta"
    assert suggerimento_rifiuto("un errore che nessuno conosce") is None


def test_i_rifiuti_del_classificatore_hanno_la_loro_categoria():
    # il motivo del classificatore arriva all'utente come «Documento non importabile come bilancio completo: …»
    def motivo(testo):
        return f"Documento non importabile come bilancio completo: {classify_bilancio(text=testo).reason}."
    assert _categoria(motivo("Conto economico\nValore della produzione 1.000\nCosti per servizi 400")) \
        == "solo_conto_economico"
    assert _categoria(motivo("SITUAZIONE CONTABILE\nRIEPILOGO DEI RICAVI\nRIEPILOGO DEI COSTI\nUTILE FISCALE")) \
        == "contabilita_semplificata"
    assert _categoria(motivo("Lettera al cliente\nGentile signore, in allegato")) == "non_bilancio"


def test_il_422_di_un_pdf_rifiutato_porta_il_suggerimento():
    import os
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from app.api.v1.imports import _dettaglio_rifiuto
    from importers.pdf_importer import PDFImportError

    d = _dettaglio_rifiuto(PDFImportError("Formato non supportato: il documento è un riepilogo aggregato per "
                                          "macro-voci"))
    assert d["error_type"] == "PDFImportError" and d["categoria"] == "riepilogo"
    assert d["suggerimento"] and d["details"] == d["suggerimento"]
    ignoto = _dettaglio_rifiuto(PDFImportError("qualcos'altro"))
    assert ignoto["suggerimento"] is None and ignoto["details"] == "Il file non è stato importato."
