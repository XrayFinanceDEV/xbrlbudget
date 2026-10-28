"""Le parti pure dello script di punteggio della Fase 0 (`tests/corpus/punteggio.py`), su dati inventati.

Il giro vero fa girare l'importatore sui PDF dei clienti, fuori da git; qui si prova solo che il
confronto con la verità conti giusto: tolleranza, campi assenti a zero, dubbi esclusi, rifiuti attesi,
stabilità fra i giri.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("punteggio", Path(__file__).parent / "corpus" / "punteggio.py")
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


def _vero(**campi):
    return {k: {"valore": v, "stato": "concorde"} for k, v in campi.items()}


def test_tolleranza_di_un_euro_e_campo_assente_vale_zero():
    vero = _vero(sp09=1000.00, sp06a=500.00, ce09a=0.0)
    letto = {"sp09": 1000.90, "sp06a": 498.00}           # ce09a assente: zero, come nel DB
    r = P.confronta_periodo(vero, letto)
    assert r["macro"] == {"giusti": 1, "totali": 1}
    assert r["kpi"] == {"giusti": 1, "totali": 2}
    assert [e["campo"] for e in r["errori"]] == ["sp06a"]
    assert r["errori"][0]["scarto"] == -2.0


def test_i_dubbi_non_pesano_sul_punteggio():
    vero = _vero(sp16=100.0)
    vero["sp16d"] = {"valore": 80.0, "stato": "dubbio"}
    r = P.confronta_periodo(vero, {"sp16": 100.0, "sp16d": 0.0})
    assert r["macro"] == {"giusti": 1, "totali": 1}
    assert r["kpi"] == {"giusti": 0, "totali": 0}
    assert r["dubbi"] == {"giusti": 0, "totali": 1}
    assert r["errori"] == []


def test_rifiuto_atteso_conta_come_esito_giusto():
    assert P.esito_atteso_rispettato("da rifiutare", importato=False)
    assert not P.esito_atteso_rispettato("da rifiutare", importato=True)
    assert P.esito_atteso_rispettato("importabile con avviso", importato=True)
    assert not P.esito_atteso_rispettato("importabile", importato=False)


def test_mesi_del_periodo_solo_per_gli_infrannuali():
    assert P.mesi_del_periodo("2026-01-01..2026-09-30") == 9
    assert P.mesi_del_periodo("2025-09-01..2026-08-31") is None      # esercizio intero non solare
    assert P.mesi_del_periodo("2025-01-01..2025-12-31") is None
    assert P.mesi_del_periodo(None) is None


def test_punteggio_e_sintesi_con_due_giri_diversi():
    vero = {"id": "X", "giudizio_atteso": "importabile",
            "periodi": [{"fine": "2025-12", "periodo": "2025-01-01..2025-12-31", "campi": _vero(sp09=10.0, ce01=50.0)},
                        {"fine": "2024-12", "periodo": "2024-01-01..2024-12-31", "campi": _vero(sp09=8.0)}]}
    giri = [
        {"importato": True, "quadra": True, "secondi": 1,
         "esercizi": [{"anno": 2025, "mesi": None, "campi": {"sp09": 10.0, "ce01": 50.0}},
                      {"anno": 2024, "mesi": None, "campi": {"sp09": 8.0}}]},
        {"importato": True, "quadra": True, "secondi": 1,
         "esercizi": [{"anno": 2025, "mesi": None, "campi": {"sp09": 10.0, "ce01": 40.0}}]},
    ]
    d = P.punteggio_documento(vero, giri)
    assert d["giri"][0]["periodi"][0]["macro"] == {"giusti": 2, "totali": 2}
    assert d["giri"][1]["periodi"][0]["macro"] == {"giusti": 1, "totali": 2}
    assert d["giri"][1]["periodi"][1]["salvato"] is False              # anno precedente non salvato
    assert d["stabilita"]["campi_instabili"] == ["ce01"]
    s = P.sintesi([d], {"X": {"tipologia": "ivcee/2-anni"}})
    assert s["esito_giusto"] == 1.0
    assert s["documenti_macro_tutti_esatti"] == 0.5
    assert s["macro_esatti"] == 0.75
    assert s["precedente_macro_esatti"] == 0.5
    assert s["documenti_instabili"] == 1


def test_un_documento_da_rifiutare_non_ha_confronto_dei_campi():
    vero = {"id": "Y", "giudizio_atteso": "da rifiutare", "periodi": [{"fine": "2025-12", "periodo": None, "campi": _vero(ce01=5.0)}]}
    d = P.punteggio_documento(vero, [{"importato": False, "errore": "PDFImportError: solo CE", "esercizi": []}])
    assert d["giri"][0]["esito_giusto"] is True
    assert d["giri"][0]["periodi"] == []
