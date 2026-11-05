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


def test_l_esercizio_salvato_si_abbina_per_anno_non_per_posizione():
    assert P.anno_del_periodo("2025-12") == 2025
    assert P.anno_del_periodo(None) is None
    vero = {"id": "Z", "giudizio_atteso": "importabile",
            "periodi": [{"fine": "2025-12", "periodo": None, "campi": _vero(sp09=10.0)},
                        {"fine": "2024-12", "periodo": None, "campi": _vero(sp09=8.0)}]}
    giro = {"importato": True, "esercizi": [{"anno": 2026, "mesi": None, "campi": {"sp09": 10.0}}]}
    d = P.punteggio_documento(vero, [giro])
    assert [p["salvato"] for p in d["giri"][0]["periodi"]] == [False, False]   # l'anno sbagliato non conta


def test_un_confronto_infrannuale_salvato_come_anno_intero_si_segnala():
    vero = {"id": "W", "giudizio_atteso": "importabile",
            "periodi": [{"fine": "2026-09", "periodo": "2026-01-01..2026-09-30", "campi": _vero(sp09=10.0)},
                        {"fine": "2025-09", "periodo": "2025-01-01..2025-09-30", "campi": _vero(sp09=8.0)}]}
    giro = {"importato": True, "esercizi": [{"anno": 2026, "mesi": 9, "campi": {"sp09": 10.0}},
                                            {"anno": 2025, "mesi": None, "campi": {"sp09": 8.0}}]}
    d = P.punteggio_documento(vero, [giro])
    assert [p["periodo_giusto"] for p in d["giri"][0]["periodi"]] == [True, False]
    assert P.sintesi([d], {"W": {"tipologia": "x"}})["periodo_sbagliato"] == ["W 2025-09"]


# --- lettore di righe (Fase 2) e numeri invariati ----------------------------------------------------

def _giro(giro=1, *, quadra=True, sbil=0.0, utile_ce=None, sp13=None, lettore="assente", campi=None, importato=True):
    g = {"id": "D", "giro": giro, "importato": importato, "quadra": quadra, "sbilancio": sbil,
         "utile_ce": utile_ce, "sp13": sp13, "esercizi": [{"anno": 2025, "mesi": None, "campi": campi or {"sp09": 10.0}}]}
    if lettore != "assente":
        g["lettore"] = lettore
    return g


def _blocco(scarto, voce="B.7 Debiti", sezione="passivo"):
    return {"voce": voce, "sezione": sezione, "scarto": scarto, "cercato": "debiti verso fornitori"}


def test_lettore_assente_negli_esiti_vecchi_non_solleva():
    a = P.analisi_lettore({"D": [_giro(), _giro(2)]})
    assert a["importati"] == 2 and a["assenti"] == 2
    assert P.righe_lettore(a)[-1].startswith("Lettore assente")


def test_sbilanciato_con_blocco_che_spiega_lo_sbilancio():
    let = {"esito": "ok", "secondi": 1.5, "blocchi_aperti": [_blocco("12.00"), _blocco(-500.0)]}
    g = _giro(quadra=False, sbil=-500.4, lettore=let)
    a = P.analisi_lettore({"D": [g]})
    assert (a["sbilanciati_giri"], a["sbilanciati_con_blocchi"], a["sbilanciati_spiegati"]) == (1, 1, 1)
    assert a["sbilanciati"][0]["spiega"] is True
    assert a["esiti"] == {"ok": 1} and a["secondi_max"] == 1.5
    md = "\n".join(P.righe_lettore(a))
    assert "| D |" in md and "sì" in md


def test_blocco_con_scarto_diverso_non_spiega_e_la_differenza_utile_conta():
    let = {"esito": "ok", "secondi": 1.0, "blocchi_aperti": [_blocco(300.0)]}
    no = P.analisi_lettore({"D": [_giro(quadra=False, sbil=-500.0, lettore=let)]})
    assert no["sbilanciati_con_blocchi"] == 1 and no["sbilanciati_spiegati"] == 0
    si = P.analisi_lettore({"D": [_giro(quadra=False, sbil=-500.0, utile_ce=1000.0, sp13=700.5, lettore=let)]})
    assert si["sbilanciati_spiegati"] == 1                       # 1000 - 700,5 = 299,5: entro 1 € da 300


def test_sbilanciato_senza_blocchi_e_bilanciato_con_blocchi():
    let_vuoto = {"esito": "ok", "secondi": 0.5, "blocchi_aperti": []}
    let_blocchi = {"esito": "ok", "secondi": 0.5, "blocchi_aperti": [_blocco(9.0), _blocco(7.0)]}
    a = P.analisi_lettore({"A": [_giro(quadra=False, sbil=40.0, lettore=let_vuoto)],
                           "B": [_giro(quadra=True, lettore=let_blocchi)]})
    assert a["sbilanciati_giri"] == 1 and a["sbilanciati_con_blocchi"] == 0
    assert a["sbilanciati"][0]["blocchi"] == []
    assert a["bilanciati_con_blocchi_documenti"] == ["B"] and a["bilanciati_blocchi"] == 2


def test_un_rifiutato_non_conta_nel_lettore():
    a = P.analisi_lettore({"D": [_giro(importato=False, quadra=None)]})
    assert a["importati"] == 0
    assert "Nessun documento importato" in P.righe_lettore(a)[-1]


def test_numeri_invariati_solo_sui_documenti_stabili():
    base = {"S": [_giro(1), _giro(2)],
            "I": [_giro(1, campi={"sp09": 1.0}), _giro(2, campi={"sp09": 2.0})],
            "C": [_giro(1), _giro(2)]}
    nuovi = {"S": [_giro(1), _giro(2)],
             "I": [_giro(1, campi={"sp09": 9.0})],
             "C": [_giro(1), _giro(2, campi={"sp09": 10.0, "ce01": 5.0})]}
    r = P.numeri_invariati(base, nuovi)
    assert r["stabili"] == 2 and r["invarianti"] == 1 and r["quota"] == 0.5
    assert r["instabili_nella_base"] == ["I"]
    assert r["cambiati"][0]["id"] == "C" and r["cambiati"][0]["giri"] == [2]
    assert [d["campo"] for d in r["cambiati"][0]["differenze"]] == ["2025/None ce01"]
    md = "\n".join(P.righe_invarianti(r, "base-x"))
    assert "50.0%" in md and "| C |" in md


def test_l_esito_diverso_dalla_base_e_una_differenza():
    r = P.numeri_invariati({"D": [_giro(1)]}, {"D": [_giro(1, importato=False)]})
    assert r["invarianti"] == 0 and r["cambiati"][0]["differenze"][0]["campo"] == "importato"
