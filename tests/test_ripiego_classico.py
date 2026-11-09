"""Interruttore del ripiego classico (Fase 4) e motivo sempre dichiarato.

Impianto di tests/test_snello_innesto.py: DB in memoria, PDF sintetico di route C, snello finto.
"""
import pytest

from importers import import_snello, pdf_importer
from importers.import_snello import SnelloNonRiuscito
from tests.test_coge_provider import RIGHE_PAREGGIO, _pdf
from tests.test_snello_innesto import _db_in_memoria, _risultato_quadrato, _vieta_estrattori_di_oggi


def _importa(tmp_path, nome, utente):
    return pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path, RIGHE_PAREGGIO), fiscal_year=2025, company_name=nome,
        create_company=True, sector=1, user_id=utente, period_months=12)


def test_ripiego_dichiarato_anche_quando_non_usato(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _vieta_estrattori_di_oggi(monkeypatch)
    monkeypatch.setattr(import_snello, "importa", lambda *a, **k: _risultato_quadrato())
    _db_in_memoria(monkeypatch)
    result = _importa(tmp_path, "Ripiego non usato", "rc-1")
    assert result["validation_report"]["import_snello"]["ripiego_classico"] == {
        "usato": False, "motivo": None}


def test_classico_spento_errore_chiaro(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.setenv("IMPORT_RIPIEGO_CLASSICO", "0")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def finta(*a, **k):
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": "verifica"})
    monkeypatch.setattr(import_snello, "importa", finta)
    session_factory = _db_in_memoria(monkeypatch)
    with pytest.raises(pdf_importer.PDFImportError, match="percorso classico spento"):
        _importa(tmp_path, "Classico spento", "rc-2")
    from database.models import FinancialYear
    with session_factory() as db:
        assert db.query(FinancialYear).count() == 0


def test_classico_acceso_identico(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPORT_MOTORE", "snello")
    monkeypatch.delenv("IMPORT_RIPIEGO_CLASSICO", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def finta(*a, **k):
        raise SnelloNonRiuscito({"esito": "ripiego", "fase": "verifica"})
    monkeypatch.setattr(import_snello, "importa", finta)
    _db_in_memoria(monkeypatch)
    result = _importa(tmp_path, "Classico acceso", "rc-3")
    assert result["success"] is True
    assert result["extraction_method"] != "import_snello"
    snello = result["validation_report"]["import_snello"]
    assert snello["ripiego_classico"] == {"usato": True, "motivo": "ripiego"}
    assert snello["esito"] == "ripiego"


def test_motivi_dichiarati():
    f = pdf_importer._motivo_ripiego_classico
    assert f(None) == "motore_classico"
    assert f({"esito": "non_applicabile", "motivo": "ocr"}) == "non_applicabile"
    assert f({"esito": "ripiego", "fase": "eccezione"}) == "eccezione"
    assert f({"esito": "ripiego", "fonte_testo": "tabelle_mineru"}) == "scansione_non_quadra"
    assert f({"esito": "ripiego", "fase": "verifica"}) == "ripiego"


@pytest.mark.parametrize("valore,acceso", [("0", False), ("off", False), ("No", False),
                                           ("1", True), ("", True)])
def test_interruttore_valori(monkeypatch, valore, acceso):
    monkeypatch.setenv("IMPORT_RIPIEGO_CLASSICO", valore)
    assert pdf_importer._ripiego_classico_acceso() is acceso
