"""Schema di legge con il percorso come codice di riga (budget_1331, "Stampa dettaglio voci"):
"1.B.2", "2.D", "3.B.9.a", conti del gestionale sotto, colonne Parziali / Totali per due
anni. PDF sintetico."""
from decimal import Decimal as D

import fitz

from importers.import_snello.deterministico import tentativo
from importers.schema_codici_parser import percorso

FONT = fitz.Font("helv")
TOT, TOT_PREC = 421, 568


def _documento(path, attivo="1.000"):
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    for x, t in ((304, "Parziali"), (383, "Totali"), (447, "Parziali"), (529, "Totali")):
        p.insert_text((x, 60), t, fontsize=7)
    righe = [
        ("1", "ATTIVO", attivo, "900"), ("1.B", "IMMOBILIZZAZIONI", "300", "300"),
        ("1.B.2", "IMMOBILIZZAZIONI MATERIALI", "300", "300"),
        ("05.03.09", "Impianti specifici", None, None),
        ("1.C", "ATTIVO CIRCOLANTE", "700", "600"), ("1.C.2", "CREDITI", "500", "400"),
        ("1.C.4", "DISPONIBILITA' LIQUIDE", "200", "200"),
        ("2", "PASSIVO", "1.000", "900"), ("2.A", "PATRIMONIO NETTO", "400", "300"),
        ("2.A.1", "Capitale", "300", "300"), ("2.A.6", "Altre riserve", "1-", "1-"),
        ("2.A.9", "Utile (perdita) dell'esercizio", "101", "1"), ("2.D", "DEBITI", "600", "600"),
        ("3", "CONTO ECONOMICO", None, None), ("3.A", "VALORE DELLA PRODUZIONE", "2.000", "1.000"),
        ("3.A.1", "Ricavi delle vendite e delle prestazioni", "2.000", "1.000"),
        ("3.B", "COSTI DELLA PRODUZIONE", "1.899", "999"),
        ("3.B.6", "Costi per materie prime", "1.000", "500"),
        ("3.B.9", "Costi per il personale", "800", "450"),
        ("3.B.9.a", "Salari e stipendi", "700", "400"),
        ("3.B.9.cde", "Trattamento di fine rapporto, quiescenza", "100", "50"),
        ("3.B.9.cde.c", "Trattamento di fine rapporto", "100", "50"),
        ("3.B.10", "Ammortamenti e svalutazioni", "99", "49"),
        ("3.B.10.abc", "Ammortamento e svalutazione delle immobilizzazioni", "99", "49"),
        ("3.B.10.abc.b", "Ammortamento delle immobilizzazioni materiali", "99", "49"),
        ("3.21", "Utile (perdita) dell'esercizio", "101", "1"),
    ]
    y = 80
    for codice, desc, cor, prec in righe:
        p.insert_text((25, y), codice, fontsize=7)
        p.insert_text((95, y), desc, fontsize=7)
        for v, x in ((cor, TOT), (prec, TOT_PREC)):
            if v:
                p.insert_text((x - FONT.text_length(v, fontsize=7), y), v, fontsize=7)
        y += 14
    doc.save(path)


def test_percorso_dal_codice():
    assert percorso("1.B.2") == "SPA.B.II"
    assert percorso("1.C.4") == "SPA.C.IV"
    assert percorso("2.A.9") == "SPP.A.IX"
    assert percorso("2.D") == "SPP.D"
    assert percorso("3.B.9.cde.c") == "CE.B.9.c"
    assert percorso("3.B.10.abc") is None            # raggruppamento, non voce
    assert percorso("3.20") == "CE.20"


def test_schema_codici_si_adotta_e_legge_il_precedente(tmp_path):
    path = str(tmp_path / "codici.pdf")
    _documento(path)
    r = tentativo(path)
    assert r["adottato"] and r["esito"] == "ok" and r["parser"] == "schema_codici"
    bs, ce = r["bs"], r["ce"]
    assert bs["sp03_immob_materiali"] == D("300.00")
    assert bs["sp16_debiti_breve"] == D("600.00")
    assert bs["sp12_riserve"] == D("-1.00")
    assert ce["ce08_costi_personale"] == D("800.00")        # salari + TFR, una volta sola
    assert ce["ce08a_tfr_accrual"] == D("100.00")
    assert ce["ce09_ammortamenti"] == D("99.00")
    assert r["prior_stato"] == "letto"
    assert r["prior_bs"]["sp06_crediti_breve"] == D("400.00")


def test_attivo_stampato_diverso_non_si_adotta(tmp_path):
    path = str(tmp_path / "codici.pdf")
    _documento(path, attivo="1.100")
    r = tentativo(path)
    assert not (r["adottato"] and r.get("parser") == "schema_codici" and r["esito"] == "ok")
