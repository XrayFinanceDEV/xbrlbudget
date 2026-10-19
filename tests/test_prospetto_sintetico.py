"""Prospetto CEE sintetico a voci appiattite (budget_1405, Metaldecor, weekend 10/2026).

Due pagine, una colonna, "B) Immobilizzazioni materiali", "C.II) Crediti", "B.7) Servizi", costi fra
parentesi, totali di gruppo stampati. Prima si leggeva col modello e importava squadrato (scarto
570.933,62, utile CE -346.949,45 contro 4.437,33 stampato). Ora si legge a regole: i totali stampati
decidono, e il totale di ogni voce senza dettaglio va nel sotto-campo "altri" della sua famiglia
(le materiali in impianti e macchinari, scelta del proprietario).
"""
import os
from decimal import Decimal as D

import fitz
import pytest

_RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PDF_REALE = os.path.join(_RADICE, "Test", "weekend-10-2026",
                          "budget_1405_Metaldecor_Bilancio_CEE_Semplificato_2025.pdf")

_SP_ATTIVO = [("B) Immobilizzazioni immateriali", "1.000,00"), ("B) Immobilizzazioni materiali", "2.000,00"),
              ("B) Immobilizzazioni finanziarie", "100,00"), ("Totale B) Immobilizzazioni", "3.100,00"),
              ("C.I) Rimanenze", "500,00"), ("C.II) Crediti", "1.500,00"),
              ("C.IV) Disponibilità liquide", "400,00"), ("Totale C) Attivo circolante", "2.400,00"),
              ("D) Ratei e risconti", "50,00"), ("TOTALE ATTIVO", "5.550,00")]
_SP_PASSIVO = [("A) Patrimonio netto", "1.200,00"), ("B) Fondi per rischi e oneri", "100,00"),
               ("C) Trattamento di fine rapporto", "150,00"), ("D) Debiti entro esercizio successivo", "3.000,00"),
               ("D) Debiti oltre esercizio successivo", "800,00"), ("Totale D) Debiti", "3.800,00"),
               ("E) Ratei e risconti", "300,00"), ("TOTALE PASSIVO", "5.550,00")]
_CE = [("A.1) Ricavi delle vendite e delle prestazioni", "10.000,00"), ("A.5) Altri ricavi e proventi", "500,00"),
       ("Totale A) Valore della produzione", "10.500,00"),
       ("B.6) Materie prime, sussidiarie, consumo e merci", "(6.000,00)"), ("B.7) Servizi", "(2.000,00)"),
       ("B.9) Personale", "(1.500,00)"), ("B.11) Variazione rimanenze", "200,00"),
       ("Totale B) Costi della produzione", "(9.300,00)"), ("Differenza A - B", "1.200,00"),
       ("C.17) Interessi e altri oneri finanziari", "(100,00)"), ("Totale C) Proventi e oneri finanziari", "(100,00)"),
       ("RISULTATO PRIMA DELLE IMPOSTE", "1.100,00"), ("20) Imposte sul reddito", "(300,00)"),
       ("UTILE DELL'ESERCIZIO", "800,00")]


def _pdf(tmp_path, ritocca=None):
    righe = [("STATO PATRIMONIALE - ATTIVO", None), *_SP_ATTIVO, ("STATO PATRIMONIALE - PASSIVO", None),
             *_SP_PASSIVO, ("CONTO ECONOMICO", None), *_CE]
    if ritocca:
        righe = [(e, ritocca.get(e, v)) for e, v in righe]
    doc = fitz.open()
    pagina, y = doc.new_page(), 60
    for etichetta, importo in righe:
        if y > 780:
            pagina, y = doc.new_page(), 60
        pagina.insert_text((40, y), etichetta, fontsize=9)
        if importo:
            pagina.insert_text((470, y), importo, fontsize=9)
        y += 14
    percorso = str(tmp_path / "sintetico.pdf")
    doc.save(percorso)
    return percorso


def test_si_legge_e_ogni_totale_stampato_torna(tmp_path):
    from importers.prospetto_sintetico import estrai
    letto = estrai(_pdf(tmp_path))
    assert "rifiuto" not in letto
    bs, ce = letto["bs"], letto["ce"]
    assert bs["sp13"] == D("800.00") and bs["sp12"] == D("400.00")           # PN 1.200 - utile 800
    assert ce["ce10"] == D("-200.00")                                        # +200 stampato = meno costo
    assert ce["ce05"] == D("6000.00") and ce["ce20"] == D("300.00")
    assert letto["stampati"] == {"totale_attivo": D("5550.00"), "totale_passivo": D("5550.00")}


def test_le_materiali_vanno_in_impianti_e_le_altre_nel_secchio_della_famiglia(tmp_path):
    from importers.prospetto_sintetico import estrai
    bs = estrai(_pdf(tmp_path))["bs"]
    assert bs["sp03"] == bs["sp03b"] == D("2000.00")
    assert bs["sp02"] == bs["sp02g"] == D("1000.00")
    assert bs["sp12"] == bs["sp12e"] == D("400.00")
    assert bs["sp16"] == bs["sp16g"] == D("3000.00") and bs["sp17"] == bs["sp17g"] == D("800.00")
    assert bs["sp05"] == bs["sp05a"] and bs["sp06"] == bs["sp06a"] == D("1500.00")


def test_un_totale_che_non_torna_rifiuta_senza_correggere(tmp_path):
    from importers.prospetto_sintetico import estrai
    letto = estrai(_pdf(tmp_path, {"Totale C) Attivo circolante": "2.399,00"}))
    assert letto["rifiuto"]["controllo"] == "totale_non_torna" and letto["rifiuto"]["totale"] == "SPA.C"
    assert "bs" not in letto


def test_una_riga_che_non_si_sa_collocare_rifiuta(tmp_path):
    from importers.prospetto_sintetico import estrai
    righe = {"D) Ratei e risconti": "50,00"}
    pdf = _pdf(tmp_path, righe)
    doc = fitz.open(pdf)
    doc[0].insert_text((40, 800), "Z) Voce inventata", fontsize=9)
    doc[0].insert_text((470, 800), "10,00", fontsize=9)
    doc.saveIncr()
    letto = estrai(pdf)
    assert letto["rifiuto"]["controllo"] == "riga_non_riconosciuta"


def test_un_bilancio_di_legge_non_e_un_prospetto_sintetico():
    from importers.prospetto_sintetico import riconosci
    for nome in ("COLOMBO.pdf",):
        pdf = os.path.join(_RADICE, "Test", nome)
        if os.path.exists(pdf):
            assert riconosci(pdf) is False


@pytest.mark.skipif(not os.path.exists(_PDF_REALE), reason="budget_1405 non presente in Test/")
def test_1405_si_adotta_a_regole_e_quadra():
    from importers.import_snello.deterministico import tentativo
    esito = tentativo(_PDF_REALE)
    assert esito["adottato"] is True and esito["parser"] == "prospetto_sintetico"
    assert esito["esito"] == "ok" and esito["misura"]["scarto_sp"] == 0 and esito["misura"]["scarto_ce"] == 0
    assert esito["misura"]["scarto_stampati"] == 0
    bs, ce = esito["bs"], esito["ce"]
    assert bs["sp03_immob_materiali"] == bs["sp03b_impianti_macchinari"] == D("318107.85")
    assert bs["sp13_utile_perdita"] == D("4437.33") and ce["ce10_var_rimanenze_mat_prime"] == D("-183504.94")
    assert ce["ce20_imposte"] == D("61778.00")


@pytest.mark.skipif(not os.path.exists(_PDF_REALE), reason="budget_1405 non presente in Test/")
def test_1405_import_completo_senza_modello_con_avviso(monkeypatch):
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
        file_path=_PDF_REALE, fiscal_year=2025, company_name="SINTETICO", create_company=True,
        sector=1, user_id="sintetico")
    assert result["success"] is True
    with sessions() as db:
        fy = db.query(FinancialYear).filter(FinancialYear.company_id == result["company_id"]).one()
        bs = fy.balance_sheet
        assert bs.sp03b_impianti_macchinari == D("318107.85") and bs.sp13_utile_perdita == D("4437.33")
        import json
        assert json.loads(fy.validation_report)["arithmetic_balanced"] is True
    assert any(w.startswith("PROSPETTO SINTETICO") for w in result["warnings"])
