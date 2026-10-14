"""Bilancio di verifica AGO a sezioni contrapposte con l'intestazione "BILANCIO DI
VERIFICA" scritta come testo (budget_618/619 2023-2024): mastri a 8 cifre, sottoconti
"NNNNNN NNN" sotto ciascun mastro, due colonne affiancate. Il parser a blocchi AGO
leggeva un mastro solo e sbilanciava di 1,5 milioni; la firma 8-digit e' piu'
specifica e deve vincere. PDF sintetico, mai il file reale."""
from decimal import Decimal as D

import fitz

from importers.import_snello.deterministico import tentativo
from importers.situazione_contabile_parser import (
    extract_situazione_contabile, is_ago_format, is_contrapposte_8digit,
)


def _conto(page, y, x, mastro, desc_mastro, figlio, desc_figlio, importo, disegnato=False):
    page.insert_text((x, y), f"{mastro} - {desc_mastro}", fontsize=7)
    page.insert_text((x + 10, y + 15), f"{figlio} - {desc_figlio}", fontsize=7)
    if disegnato:
        return              # l'importo e' grafica: nel testo non c'e'
    page.insert_text((x + 350, y), importo, fontsize=7)
    page.insert_text((x + 345, y + 15), importo, fontsize=7)


def _intestazione(page, n):
    page.insert_text((12, 20), "BILANCIO DI VERIFICA", fontsize=10)
    page.insert_text((12, 32), "Esercizio 2024 / 1 Dal 01-01-2024 Al 31-12-2024", fontsize=7)
    page.insert_text((14, 570), f"AGO - 06.06.00 Pag. {n} di 2", fontsize=7)


def _documento(path, salari_disegnati=False):
    doc = fitz.open()
    sp = doc.new_page(width=842, height=595)
    _intestazione(sp, 1)
    sp.insert_text((150, 70), "ATTIVITA'", fontsize=8)
    sp.insert_text((330, 70), "SITUAZIONE PATRIMONIALE", fontsize=8)
    sp.insert_text((570, 70), "PASSIVITA'", fontsize=8)
    attivo = [
        ("13120000", "Altri beni materiali ammortizzabili", "101445 000", "altri beni materiali", "500.000,00"),
        ("15040000", "Crediti v/clienti (EE)", "102280 000", "clienti ordinari (EE)", "300.000,00"),
        ("15150000", "Depositi bancari e postali", "103435 000", "banche c/c", "200.000,00"),
    ]
    passivo = [
        ("13120005", "F.do amm. altri beni materiali ammortiz.", "201460 000", "f.do amm. altri beni materiali", "100.000,00"),
        ("31000000", "Capitale", "203780 000", "capitale sociale", "50.000,00"),
        ("31030000", "Riserve facoltative", "204050 000", "riserva straordinaria", "250.000,00"),
        ("35000000", "Trattamento fine rapporto di lavoro sub.", "204500 000", "trattamento fine rapporto", "40.000,00"),
        ("37030000", "Debiti verso fornitori (EE)", "204845 000", "fornitori ordinari (EE)", "460.000,00"),
    ]
    y = 100
    for i in range(max(len(attivo), len(passivo))):
        if i < len(attivo):
            _conto(sp, y, 17, *attivo[i])
        if i < len(passivo):
            _conto(sp, y, 417, *passivo[i])
        y += 30
    sp.insert_text((12, y + 10), "TOTALE A PAREGGIO", fontsize=7)
    sp.insert_text((417, y + 10), "UTILE D'ESERCIZIO", fontsize=7)

    ce = doc.new_page(width=842, height=595)
    _intestazione(ce, 2)
    _conto(ce, 100, 17, "73000000", "Costi mat.prime, sussid , consumo, merci",
           "703020 000", "acquisto di merci e prodotti", "300.000,00")
    _conto(ce, 130, 17, "73005000", "Costi per servizi",
           "704170 000", "prestazioni professionali", "40.000,00")
    if salari_disegnati:
        # come gli interessi di budget_618: mastro e un sottoconto disegnati come grafica,
        # nel testo resta l'importo dell'altro sottoconto (25.000 su 60.000)
        ce.insert_text((17, 160), "73015000 - Salari e stipendi", fontsize=7)
        ce.insert_text((27, 175), "705900 000 - salari e stipendi", fontsize=7)
        ce.insert_text((27, 190), "705900 001 - salari e stipendi", fontsize=7)
        ce.insert_text((362, 190), "25.000,00", fontsize=7)
    else:
        _conto(ce, 160, 17, "73015000", "Salari e stipendi",
               "705900 000", "salari e stipendi", "60.000,00")
    _conto(ce, 100, 417, "71000000", "Ricavi delle vendite e delle prestazioni",
           "500005 000", "vendita prodotti finiti e merci ITALIA", "500.000,00")
    ce.insert_text((12, 220), "TOTALE COSTI", fontsize=7)
    ce.insert_text((300, 220), "400.000,00", fontsize=7)
    ce.insert_text((417, 220), "TOTALE RICAVI", fontsize=7)
    ce.insert_text((760, 220), "500.000,00", fontsize=7)
    ce.insert_text((12, 235), "UTILE D'ESERCIZIO", fontsize=7)
    ce.insert_text((300, 235), "100.000,00", fontsize=7)
    ce.insert_text((12, 250), "TOTALE A PAREGGIO", fontsize=7)
    ce.insert_text((300, 250), "500.000,00", fontsize=7)
    doc.save(path)
    doc.close()


def test_la_firma_8digit_vince_su_quella_ago(tmp_path):
    path = tmp_path / "ago.pdf"
    _documento(str(path))
    testo = "".join(p.get_text() for p in fitz.open(str(path)))
    assert is_ago_format(testo) and is_contrapposte_8digit(testo)

    bs, ce = extract_situazione_contabile(str(path))
    assert bs["sp03"] == D("400000.00")          # 500.000 lordo - fondo 100.000
    assert bs["sp06"] == D("300000.00")
    assert bs["sp09"] == D("200000.00")
    assert bs["sp15"] == D("40000.00")
    assert bs["sp13"] == D("100000.00")
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("900000.00")
    assert ce["ce01"] == D("500000.00")


def test_costo_disegnato_come_grafica_sp13_dal_risultato_stampato(tmp_path):
    path = tmp_path / "ago.pdf"
    _documento(str(path), salari_disegnati=True)
    bs, ce = extract_situazione_contabile(str(path))
    # lo SP chiude con l'utile stampato; al CE mancano 35.000 di salari, dichiarati
    assert bs["sp13"] == D("100000.00")
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("900000.00")
    assert bs["_ce_massa_non_letta"] == D("35000.00")
    assert bs["_totale_costi_stampato"] == D("400000.00")
    assert ce["ce08"] == D("25000.00")

    # lo snello non la adotta (CE/SP oltre i 10 euro) ma la tiene in gara col modello
    r = tentativo(str(path))
    assert not r["adottato"] and r["esito"] == "oltre_soglia"
    assert r["lettura"]["misura"]["scarto_sp"] == D("0.00")
    assert r["lettura"]["misura"]["scarto_ce"] == D("35000.00")


def test_senza_i_totali_stampati_del_ce_non_si_tocca_nulla(tmp_path):
    path = tmp_path / "ago.pdf"
    _documento(str(path), salari_disegnati=True)
    doc = fitz.open(str(path))
    for r in doc[1].search_for("TOTALE COSTI"):
        doc[1].add_redact_annot(r)
    doc[1].apply_redactions()
    path2 = tmp_path / "ago2.pdf"
    doc.save(str(path2))
    bs, _ce = extract_situazione_contabile(str(path2))
    assert "_ce_massa_non_letta" not in bs
    assert bs["sp13"] == D("135000.00")


def test_l_avviso_cita_il_totale_costi_stampato_e_il_risultato():
    from importers.pdf_importer import _snello_squadrato_reason
    testo = _snello_squadrato_reason({
        "causa": "ce_non_letto",
        "ce_non_letto": {"massa": "11343.64", "risultato": "40951.18",
                         "totale_costi": "4103725.80", "costi_letti": "4092382.16"},
        "misura": {"corrente": {"scarto_sp": "0.00", "scarto_ce": "11343.64",
                                "scarto_stampati": "0.00"}}})
    assert testo.startswith("BILANCIO SBILANCIATO")
    assert "11.343,64" in testo and "4.103.725,80" in testo and "40.951,18" in testo
