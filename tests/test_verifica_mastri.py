"""Bilancio di verifica "Mastri" (budget_1325/1330, Santini SpA): sezioni ATTIVITÀ /
PASSIVITÀ / COSTI / RICAVI, mastro a 4 cifre, conti a 8 cifre con un solo importo firmato,
"Totale <MASTRO>:" sotto i conti e un RIEPILOGO con la DIFFERENZA. PDF sintetico."""
from decimal import Decimal as D

import fitz

from importers.import_snello.deterministico import tentativo
from importers.situazione_contabile_parser import (
    _classify_ce_costi, _classify_ce_ricavi, _classify_sp_attivo, _sp05_detail_field,
    extract_situazione_contabile, is_verifica_mastri)

FONT = fitz.Font("helv")


def _importo(p, y, testo, destra=557):
    p.insert_text((destra - FONT.text_length(testo, fontsize=7), y), testo, fontsize=7)


def _documento(path, *, totale_banche="-100,00"):
    doc = fitz.open()
    sezioni = [
        ("ATTIVITÀ", [
            ("0102", "BANCHE", [("01020001", "BPER", "400,00"), ("01020004", "BANCA POP. DI SONDRIO", "-500,00")], totale_banche),
            ("0200", "CLIENTI WEB", [], "1.000,00"),
            ("0502", "FINALI", [("05020003", "RIMAN.FINALI PRODOTTI FINITI", "2.000,00")], "2.000,00"),
        ], "TOTALE ATTIVITÀ': 2.900,00"),
        ("PASSIVITÀ", [
            ("1001", "CAPITALE E RISERVE", [("10010001", "CAPITALE SOCIALE", "2.000,00")], "2.000,00"),
            ("1007", "ALTRE RISERVE", [("10070001", "RISERVA OPER COPERTURA FLUSSI", "-50,00")], "-50,00"),
            ("0608", "I.V.A.", [("06080009", "IVA PARTITA IVA FRANCESE", "350,00")], "350,00"),
            ("0801", "DEBITI MEDIO LUNGO TERMINE", [("08010035", "FINANZIAMENTO 07797790 BANCO BPM", "300,00")], "300,00"),
        ], "TOTALE PASSIVITÀ': 2.600,00"),
        ("COSTI", [
            ("2101", "ACQUISTI", [("21010002", "TESSUTO", "1.000,00")], "1.000,00"),
            ("2105", "COSTI COMMERCIALI-AMMINISTR.E", [("21050001", "PROVVIGIONI ITALIA", "200,00")], "200,00"),
            ("2111", "AMMORTAMENTI", [("21110001", "AMM.IMPIANTI E MACCHINARI", "100,00"),
                                       ("21110002", "AMMORTAMENTO SOFTWARE", "50,00")], "150,00"),
        ], "TOTALE COSTI: 1.350,00"),
        ("RICAVI", [
            ("2201", "VENDITE", [("22010001", "VENDITE ESTERO", "1.600,00")], "1.600,00"),
            ("2205", "RICAVI DIVERSI", [("22050001", "PROVENTI DA CONSOLIDATO FISCALE", "50,00")], "50,00"),
        ], "TOTALE RICAVI: 1.650,00"),
    ]
    for titolo, mastri, totale in sezioni:
        p = doc.new_page(width=595, height=842)
        p.insert_text((14, 40), "Bilancio di verifica", fontsize=9)
        p.insert_text((62, 60), "Conto", fontsize=7)
        p.insert_text((173, 60), "Descrizione conto", fontsize=7)
        p.insert_text((16, 60), "Mastri", fontsize=7)
        p.insert_text((14, 80), titolo, fontsize=8)
        y = 100
        for codice, desc, conti, tot in mastri:
            p.insert_text((16, y), codice, fontsize=7)
            p.insert_text((147, y), desc, fontsize=7)
            y += 12
            for c, d, v in conti:
                p.insert_text((62, y), c, fontsize=7)
                p.insert_text((173, y), d, fontsize=7)
                _importo(p, y, v)
                y += 12
            p.insert_text((272, y), f"Totale {desc}:", fontsize=7)
            _importo(p, y, tot)
            y += 14
        p.insert_text((416, y + 10), totale, fontsize=7)
    p = doc.new_page(width=595, height=842)
    p.insert_text((14, 40), "RIEPILOGO", fontsize=8)
    p.insert_text((40, 60), "TOTALE ATTIVITÀ':        2.900,00", fontsize=7)
    p.insert_text((300, 60), "TOTALE COSTI:        1.350,00", fontsize=7)
    p.insert_text((40, 75), "TOTALE PASSIVITÀ':        2.600,00", fontsize=7)
    p.insert_text((300, 75), "TOTALE RICAVI:        1.650,00", fontsize=7)
    p.insert_text((40, 90), "DIFFERENZA            300,00", fontsize=7)
    p.insert_text((300, 90), "DIFFERENZA            300,00", fontsize=7)
    # abbastanza conti da riconoscere il formato
    for i in range(20):
        p.insert_text((62, 200 + i * 10), f"9900{i:04d}", fontsize=6)
    p.insert_text((272, 420), "Totale RIEPILOGO:", fontsize=6)
    for i in range(4):
        p.insert_text((272, 430 + i * 10), f"Totale X{i}:", fontsize=6)
    doc.save(path)


def test_verifica_mastri_si_legge_e_quadra(tmp_path):
    path = str(tmp_path / "mastri.pdf")
    _documento(path)
    assert is_verifica_mastri("\n".join(p.get_text() for p in fitz.open(path)))
    bs, ce = extract_situazione_contabile(path)
    assert bs["sp13"] == D("300.00")
    assert bs["sp09"] == D("400.00")                    # BPER a saldo dare sotto BANCHE
    assert bs["sp16a_debiti_banche_breve"] == D("800.00")   # Sondrio a saldo avere + il finanziamento
    assert bs["sp05"] == D("2000.00")
    assert bs["sp05d_prodotti_finiti"] == D("2000.00")
    assert bs["sp06"] == D("1000.00")                   # il mastro clienti senza conti stampati
    assert bs["sp12"] == D("-50.00")                    # la riserva a saldo dare resta nel PN
    assert bs["sp16"] == D("1150.00")                   # IVA francese compresa: non e' un'intestazione
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("3400.00")
    assert ce["ce05"] == D("1000.00") and ce["ce06"] == D("200.00")
    assert ce["ce09"] == D("150.00") and ce["ce09a_ammort_immateriali"] == D("50.00")
    assert ce["ce20"] == D("-50.00")                    # il provento da consolidato riduce le imposte
    r = tentativo(path)
    assert r["adottato"] and r["esito"] == "ok"


def test_totale_di_mastro_che_non_torna_scarta_la_lettura(tmp_path):
    path = str(tmp_path / "mastri.pdf")
    _documento(path, totale_banche="-90,00")
    bs, _ce = extract_situazione_contabile(path)
    assert not bs.get("totale_attivo")


def test_regole_generali():
    assert _classify_ce_costi("CONSULENZE COMMERCIALI") == "ce06"     # MERCI in COMMERCIALI
    assert _classify_ce_costi("AMMTO TELEFONIA") == "ce09b"
    assert _classify_ce_costi("AMMORTAMENTO MARCHI") == "ce09a"
    assert _classify_ce_costi("AMMINISTRATORI") == "ce06"             # non e' un ammortamento
    assert _classify_ce_costi("DIFF.CAMBIO PASSIVO") == "ce16_cost"
    assert _classify_ce_ricavi("INTERESSI ATTIVI BANCARI") == "ce14"
    assert _classify_sp_attivo("RIMAN.FINALI SEMILAVORATI") == "sp05"
    assert _sp05_detail_field("RIMANENZE FINALI PRODOTTI FINITI") == "sp05d_prodotti_finiti"
