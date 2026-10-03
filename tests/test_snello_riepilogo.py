"""Task 27, decisione 2: un riepilogo a macro-voci non e' un bilancio e non si importa.
Testo sintetico, mai file di clienti."""
import fitz
import pytest

from importers import import_snello, pdf_importer
from importers.import_snello import riepilogo as RIEP
from tests.test_coge_provider import RIGHE_PAREGGIO, _pdf

RIEPILOGO_A_RIGHE = """BILANCIO 2025 - SCHEMA IV DIRETTIVA CEE
Società: ESEMPIO S.R.L.
STATO PATRIMONIALE - ATTIVO
Immobilizzazioni: 2.406.946,04
Attivo circolante: 1.695.431,51
Ratei e risconti attivi: 66.612,55
Totale attivo: 4.079.635,72
PASSIVO
Patrimonio netto: -58.481,84
Fondi rischi: 14.962,00
TFR: 123.583,51
Debiti: 2.688.470,08
Ratei e risconti passivi: 4.035,91
Totale passivo: 4.346.574,29
CONTO ECONOMICO
Valore produzione: 2.025.192,55
Costi produzione: 2.092.092,63
Differenza: -66.900,08
Gestione finanziaria: -138.687,60
Perdita esercizio: -266.938,57
"""

# Con lettere di sezione (forma abbreviata) e importi senza virgola migliaia, come budget_150
RIEPILOGO_CON_LETTERE = """BILANCIO DI ESERCIZIO - FORMA ABBREVIATA
STATO PATRIMONIALE
ATTIVO
B) Immobilizzazioni: 554.824,39 €
C) Attivo circolante: 967.451,22 €
D) Ratei e risconti: 3.744,82 €
PASSIVO
A) Patrimonio netto (incluso utile): 663197.53 €
C) Trattamento di fine rapporto: 81.864,67 €
D) Debiti (inclusi tributari): 780958.23 €
CONTO ECONOMICO
A) Valore della produzione: 1.559.119,25 €
B) Costi della produzione: 1.472.044,65 €
Differenza A-B: 87.074,60 €
UTILE NETTO DI ESERCIZIO: 22274.49 €
"""

SCHEMA_DI_LEGGE = """STATO PATRIMONIALE
ATTIVO
B) Immobilizzazioni
I - Immobilizzazioni immateriali 1.000 2.000
II - Immobilizzazioni materiali 5.000 6.000
Totale immobilizzazioni 6.000 8.000
C) Attivo circolante
II - Crediti
esigibili entro l'esercizio successivo 3.000 2.500
IV - Disponibilità liquide 1.500 900
Totale attivo 10.500 11.400
PASSIVO
A) Patrimonio netto 4.000 3.000
D) Debiti
esigibili entro l'esercizio successivo 6.500 8.400
Totale passivo 10.500 11.400
CONTO ECONOMICO
1) Ricavi delle vendite 20.000 18.000
7) Per servizi 5.000 4.000
"""


@pytest.mark.parametrize("testo", [RIEPILOGO_A_RIGHE, RIEPILOGO_CON_LETTERE])
def test_riepilogo_a_macro_voci_riconosciuto(testo):
    assert RIEP.riconosci_riepilogo_testo(testo, 1)


def test_schema_di_legge_non_e_un_riepilogo():
    assert not RIEP.riconosci_riepilogo_testo(SCHEMA_DI_LEGGE, 1)


def test_un_riepilogo_con_le_voci_di_dettaglio_non_e_riconosciuto():
    # nomina i crediti: ha le sotto-voci che il modello richiede, prende la strada di sempre
    testo = RIEPILOGO_A_RIGHE.replace("Attivo circolante: 1.695.431,51",
                                      "Attivo circolante: 1.695.431,51\nCrediti: 1.525.764,37")
    assert not RIEP.riconosci_riepilogo_testo(testo, 1)


def test_righe_conto_scadenze_e_numerazione_di_legge_escludono():
    for aggiunta in ("\n1234567 Cassa 100,00", "\nesigibili entro l'esercizio 10,00", "\n7) servizi 10,00",
                     "\nII - Materiali 10,00"):
        assert not RIEP.riconosci_riepilogo_testo(RIEPILOGO_A_RIGHE + aggiunta, 1)


def test_documento_lungo_o_senza_prospetti_non_e_un_riepilogo():
    assert not RIEP.riconosci_riepilogo_testo(RIEPILOGO_A_RIGHE, 3)
    assert not RIEP.riconosci_riepilogo_testo(RIEPILOGO_A_RIGHE.replace("CONTO ECONOMICO", "RISULTATI"), 1)
    assert not RIEP.riconosci_riepilogo_testo("", 1)


def _pdf_testo(tmp_path, testo, nome="r.pdf"):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), testo, fontsize=8)
    p = str(tmp_path / nome)
    doc.save(p)
    return p


def test_riconosci_riepilogo_da_file(tmp_path):
    assert RIEP.riconosci_riepilogo(_pdf_testo(tmp_path, RIEPILOGO_A_RIGHE))
    assert not RIEP.riconosci_riepilogo(_pdf_testo(tmp_path, SCHEMA_DI_LEGGE, "s.pdf"))
    assert not RIEP.riconosci_riepilogo(str(tmp_path / "non_esiste.pdf"))


def test_innesto_rifiuta_con_messaggio_e_non_salva_nulla(tmp_path, monkeypatch):
    from tests.test_snello_innesto import _db_in_memoria

    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chiave-finta")   # nessuna chiamata: serve solo a passare il controllo iniziale

    def _vietata(*a, **k):
        raise AssertionError("il percorso snello non deve partire su un riepilogo")
    monkeypatch.setattr(import_snello, "importa", _vietata)
    session_factory = _db_in_memoria(monkeypatch)

    with pytest.raises(pdf_importer.PDFImportError) as exc:
        pdf_importer.import_pdf_balance_sheet(
            file_path=_pdf_testo(tmp_path, RIEPILOGO_A_RIGHE), fiscal_year=2025,
            company_name="Riepilogo", create_company=True, sector=1,
            user_id="snello-riepilogo", period_months=12)
    assert "riepilogo di sintesi" in str(exc.value) and "bilancio completo" in str(exc.value)

    from database.models import Company, FinancialYear
    with session_factory() as db:
        assert db.query(FinancialYear).count() == 0
        assert db.query(Company).count() == 0


def test_senza_interruttore_il_riconoscitore_non_gira(tmp_path, monkeypatch):
    from tests.test_snello_innesto import _db_in_memoria

    monkeypatch.delenv("IMPORT_MOTORE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def _vietato(*a, **k):
        raise AssertionError("il riconoscitore dei riepiloghi gira solo col percorso snello")
    monkeypatch.setattr(RIEP, "riconosci_riepilogo", _vietato)
    _db_in_memoria(monkeypatch)

    pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025,
        company_name="Produzione", create_company=True, sector=1,
        user_id="prod", period_months=12)
