"""Bilancio di verifica con la sezione in colonna (COLOMBO 2026): "Mastro | Descrizione | Conto |
Descrizione | Importo | SEZBIL", un solo importo positivo per conto e la lettera della sezione
(A attivita', P passivita', C costi, R ricavi), "Totale <MASTRO>" sotto i conti e un RIEPILOGO
con TOTALE ATTIVITA'/PASSIVITA'/COSTI/RICAVI e la DIFFERENZA, che e' il risultato.

Prima il classificatore lo rifiutava ("nessuno scheletro di legge ne' elenco conti
riconoscibile"): nessun "bilancio di verifica", nessun "TOTALE A PAREGGIO".
"""
from decimal import Decimal as D

import fitz
import pytest

from importers import situazione_contabile_parser as scp

# (mastro, descrizione mastro, [(conto, descrizione, importo)], sezione)
MASTRI = [
    ("025", "DIRITTI BREV.IND.E OP. INGEGNO", [("11804", "software di proprieta'", "1000")], "A"),
    ("150", "RIM.PRODOTTI FINITI E MERCI", [("17405", "Merci / Imballi", "500")], "A"),
    ("162", "CREDITI ESIGIBILI ENTRO 12MESI", [("29001", "clienti italia", "800"),
                                               ("29002", "fatture da emettere", "200,5")], "A"),
    ("200", "BANCHE E POSTA", [("32001", "banca intesa c/c", "300")], "A"),
    ("300", "CAPITALE SOCIALE", [("33001", "capitale sociale", "1000")], "P"),
    ("315", "UTILE E PERDITA DELL'ESERCIZIO", [("33651", "utile d'esercizio", "100")], "P"),
    ("340", "TFR LAV. SUBORDINATO", [("34301", "f.do tratt.fine rapp.lav.sub.", "200")], "P"),
    ("420", "FORNITORI", [("40001", "fornitori italia", "900")], "P"),
    ("605", "ESIST.INIZ.PROD.FINITI E SEMIL", [("56001", "RIMANENZE INIZIALI", "100")], "C"),
    ("600", "ACQUISTI MERCI", [("60001", "acquisti merci", "2000")], "C"),
    ("610", "SERVIZI", [("61001", "consulenze", "500")], "C"),
    ("620", "SALARI E STIPENDI", [("62001", "salari e stipendi", "400")], "C"),
    ("495", "RICAVI VENDITE", [("51601", "vendite Italia", "3000"),
                               ("5160EQ", "VENDITE GDO", "300")], "R"),
    ("601", "RIM.FIN.MAT.PRIME,SUSSID,MERCI", [("56805", "Prodotti finiti rimanenze finali", "300,5")], "R"),
]
RIEPILOGO = {"ATTIVITA'": "2800,5", "PASSIVITA'": "2200", "COSTI": "3000", "RICAVI": "3600,5"}
DIFFERENZA = "600,5"


def _pdf(tmp_path, mastri=MASTRI, riepilogo=RIEPILOGO, differenza=DIFFERENZA, stampato=None):
    doc = fitz.open()
    font = fitz.Font("helv")
    pagina = doc.new_page(width=842, height=595)
    y = [74.0]

    def a_destra(x_fine, testo):
        pagina.insert_text((x_fine - font.text_length(testo, fontsize=8), y[0]), testo, fontsize=8)

    def riga():
        y[0] += 12.5
        nonlocal pagina
        if y[0] > 560:
            pagina = doc.new_page(width=842, height=595)
            y[0] = 74.0
            intestazione()
            y[0] += 12.5

    def intestazione():
        for x, t in ((53, "Mastro"), (142, "Descrizione"), (342, "Conto"), (397, "Descrizione"),
                     (630, "Importo"), (690, "SEZBIL")):
            pagina.insert_text((x, y[0]), t, fontsize=8)

    intestazione()
    riga()
    for codice, desc, conti, sez in mastri:
        for i, (conto, cdesc, importo) in enumerate(conti):
            if i == 0:
                pagina.insert_text((53, y[0]), codice, fontsize=8)
                pagina.insert_text((142, y[0]), desc, fontsize=8)
            pagina.insert_text((342, y[0]), conto, fontsize=8)
            pagina.insert_text((397, y[0]), cdesc, fontsize=8)
            a_destra(686, importo)
            pagina.insert_text((690, y[0]), sez, fontsize=8)
            riga()
            if conto == "5160EQ":
                pagina.insert_text((690, y[0]), "X", fontsize=8)
                riga()
        tot = sum((D(c[2].replace(",", ".")) for c in conti), D(0))
        pagina.insert_text((142, y[0]), f"Totale {desc}", fontsize=8)
        testo_tot = f"{tot:f}".replace(".", ",")
        if "," in testo_tot:
            testo_tot = testo_tot.rstrip("0").rstrip(",")
        a_destra(686, (stampato or {}).get(codice, testo_tot))
        pagina.insert_text((690, y[0]), sez, fontsize=8)
        riga()
    pagina.insert_text((53, y[0]), "RIEPILOGO", fontsize=8)
    riga()
    for sinistra, destra in (("ATTIVITA'", "COSTI"), ("PASSIVITA'", "RICAVI")):
        pagina.insert_text((53, y[0]), f"TOTALE {sinistra}", fontsize=8)
        a_destra(338, riepilogo[sinistra])
        pagina.insert_text((397, y[0]), f"TOTALE {destra}", fontsize=8)
        a_destra(686, riepilogo[destra])
        riga()
    pagina.insert_text((53, y[0]), "DIFFERENZA", fontsize=8)
    a_destra(338, differenza)
    pagina.insert_text((397, y[0]), "DIFFERENZA", fontsize=8)
    a_destra(686, differenza)
    percorso = tmp_path / "verifica_sezbil.pdf"
    doc.save(percorso)
    doc.close()
    return str(percorso)


def _testo(path):
    with fitz.open(path) as d:
        return "\n".join(p.get_text() for p in d)


def test_riconosciuta_come_situazione_contabile(tmp_path):
    from importers.bilancio_classifier import ROUTE_TRIAL, classify_bilancio
    path = _pdf(tmp_path)
    assert scp.is_verifica_sezbil(_testo(path))
    assert classify_bilancio(file_path=path, text=_testo(path)).route == ROUTE_TRIAL


def test_conti_letti_con_la_sezione_della_colonna(tmp_path):
    entries = scp.parse_entries_verifica_sezbil(_pdf(tmp_path))
    assert entries
    per_codice = {e.code: e for e in entries if e.code}
    assert per_codice["5160EQ"].section == "ricavi" and per_codice["5160EQ"].amount == D("300")
    assert per_codice["29002"].amount == D("200.5")          # un solo decimale stampato
    assert per_codice["40001"].section == "passivo"
    utile = next(e for e in entries if e.description == "UTILE D'ESERCIZIO" and e.level == 4)
    assert utile.amount == D("600.5")


def test_un_mastro_che_non_torna_scarta_la_lettura(tmp_path):
    # il mastro SERVIZI stampa 499 sotto un conto da 500
    assert scp.parse_entries_verifica_sezbil(_pdf(tmp_path, stampato={"610": "499"})) == []


def test_differenza_che_non_pareggia_scarta_la_lettura(tmp_path):
    assert scp.parse_entries_verifica_sezbil(_pdf(tmp_path, differenza="700")) == []


def test_import_completo_senza_modello(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.db import Base
    from database.models import FinancialYear
    from importers import pdf_importer

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    for chiave in ("ANTHROPIC_API_KEY", "GX10_API_KEY", "IMPORT_MOTORE"):
        monkeypatch.delenv(chiave, raising=False)
    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path), fiscal_year=2026, company_name="VERIFICA SEZBIL",
        create_company=True, sector=2, user_id="sezbil", period_months=6)
    assert result["success"] is True
    with sessions() as db:
        fy = db.query(FinancialYear).filter(FinancialYear.company_id == result["company_id"]).one()
        bs, ce = fy.balance_sheet, fy.income_statement
        assert fy.period_months == 6
        assert bs.sp13_utile_perdita == D("600.50")
        assert ce.ce01_ricavi_vendite == D("3300.00")
        assert bs.sp09_disponibilita_liquide == D("300.00")
        import json
        report = json.loads(fy.validation_report)
        assert report["arithmetic_balanced"] is True
        # il conto "utile d'esercizio" da 100 e' l'utile dell'anno prima non destinato
        assert bs.sp12g_utili_perdite_portati == D("100.00")
    assert any(w.startswith("RISULTATO DELL'ANNO PRIMA NON DESTINATO") for w in result["warnings"])
