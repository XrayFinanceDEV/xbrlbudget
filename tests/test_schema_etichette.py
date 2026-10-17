"""Schema di legge con il percorso nell'etichetta ("Situazione contabile riclassificata
dettagliata": "B.I.2) Costi di sviluppo", "C.II.5 bis.1) Esigibili entro...", i conti del
gestionale sotto ogni voce, colonne esercizio / precedente / Differenza / Scost. %).

Le trappole sono quelle viste su Santini 31/12/2025 (scansione letta da MinerU), dove il modello
le ha sbagliate tutte: la sotto-riga "B.6.2) Materie prime" presa per il totale B.6, i crediti
oltre 12 mesi contati due volte, i debiti verso il gruppo persi, la riserva legale e quella di
copertura sparite dentro "altre riserve".
"""
from decimal import Decimal as D
from types import SimpleNamespace

import fitz
import pytest

from importers import schema_etichette_parser as sep

# (codice, etichetta, esercizio, precedente)
RIGHE = [
    ("2", "Stato patrimoniale attivo", "3.600,00", "3.300,00"),
    ("44", "B) Immobilizzazioni", "1.500,00", "1.400,00"),
    ("60", "B.I) Immobilizzazioni immateriali", "600,00", "500,00"),
    ("110", "B.I.2) Costi di sviluppo", "600,00", "500,00"),
    ("133", "B.I.2.a) Spese di sviluppo", "700,00", "550,00"),
    ("", "3020200 COSTI DI RICERCA E SVILUPPO", "700,00", "550,00"),
    ("134", "B.I.2.b) (Fondi di ammortamento)", "100,00", "50,00"),
    ("276", "B.II) Immobilizzazioni materiali", "400,00", "400,00"),
    ("322", "B.II.2) Impianti e macchinario", "400,00", "400,00"),
    ("534", "B.III) Immobilizzazioni finanziarie", "500,00", "500,00"),
    ("550", "B.III.1) Partecipazioni in:", "450,00", "450,00"),
    ("570", "B.III.1.a) Imprese controllate", "450,00", "450,00"),
    ("654", "B.III.2) Crediti", "50,00", "50,00"),
    ("865", "B.III.2.d bis) Verso altri", "50,00", "50,00"),
    ("896", "B.III.2.d bis.2) Esigibili oltre l'esercizio successivo", "50,00", "50,00"),
    ("956", "C) Attivo circolante", "2.000,00", "1.800,00"),
    ("970", "C.I) Rimanenze", "500,00", "400,00"),
    ("990", "C.I.1) Materie prime, sussidiarie e di consumo", "200,00", "150,00"),
    ("1066", "C.I.4) Prodotti finiti e merci", "300,00", "250,00"),
    ("1104", "C.II) Crediti", "1.300,00", "1.200,00"),
    ("1120", "C.II.1) Verso clienti", "800,00", "700,00"),
    ("1140", "C.II.1.1) Esigibili entro l'esercizio successivo", "800,00", "700,00"),
    ("1176", "C.II.1.1.l) (Fondi svalutazione crediti)", "40,00", "30,00"),
    ("1351", "C.II.5) Verso imprese sottoposte al controllo delle controllanti", "100,00", "100,00"),
    ("1352", "C.II.5.1) Esigibili entro l'esercizio successivo", "100,00", "100,00"),
    ("1362", "C.II.5 bis) Per crediti tributari", "400,00", "400,00"),
    ("1363", "C.II.5 bis.1) Esigibili entro l'esercizio successivo", "340,00", "310,00"),
    ("1373", "C.II.5 bis.2) Esigibili oltre l'esercizio successivo", "60,00", "90,00"),
    ("1634", "C.IV) Disponibilità liquide", "200,00", "200,00"),
    ("1718", "D) Ratei e risconti", "100,00", "100,00"),
    ("1834", "Stato patrimoniale passivo", "3.600,00", "3.300,00"),
    ("1850", "A) Patrimonio netto", "1.180,00", "1.100,00"),
    ("1870", "A.I) Capitale", "1.000,00", "1.000,00"),
    ("1950", "A.IV) Riserva legale", "100,00", "100,00"),
    ("2053", "A.VII) Riserva per operazioni di copertura dei flussi finanziari attesi", "-20,00", "-50,00"),
    ("2086", "A.IX) Utile (Perdita) dell'esercizio", "100,00", "50,00"),
    ("2126", "B) Fondi per rischi e oneri", "100,00", "100,00"),
    ("2196", "B.3) Strumenti finanziari derivati passivi", "100,00", "100,00"),
    ("2244", "C) Trattamento di fine rapporto di lavoro subordinato", "120,00", "100,00"),
    ("2264", "D) Debiti", "2.100,00", "1.900,00"),
    ("2398", "D.4) Debiti verso banche", "1.300,00", "1.200,00"),
    ("2400", "D.4.1) Esigibili entro l'esercizio successivo", "800,00", "700,00"),
    ("2436", "D.4.2) Esigibili oltre l'esercizio successivo", "500,00", "500,00"),
    ("2606", "D.7) Debiti verso fornitori", "700,00", "600,00"),
    ("2620", "D.7.1) Esigibili entro l'esercizio successivo", "700,00", "600,00"),
    ("2894", "D.11 bis) Debiti verso imprese sottoposte al controllo delle controllanti", "100,00", "100,00"),
    ("2895", "D.11 bis.1) Esigibili entro l'esercizio successivo", "100,00", "100,00"),
    ("3122", "E) Ratei e risconti", "100,00", "100,00"),
    ("3360", "Conto economico", "0,00", "0,00"),
    ("3380", "A) Valore della produzione", "1.000,00", "900,00"),
    ("3400", "A.1) Ricavi delle vendite e delle prestazioni", "1.000,00", "900,00"),
    ("3420", "A.1.a) Corrispettivi cessioni di beni", "1.020,00", "910,00"),
    ("3450", "A.1.n) Rettifiche di ricavi", "-20,00", "-10,00"),
    ("3664", "B) Costi della produzione", "850,00", "810,00"),
    ("3680", "B.6) Per materie prime, sussidiarie, di consumo e di merci", "300,00", "280,00"),
    ("3702", "B.6.2) Materie prime", "120,00", "100,00"),
    ("3706", "B.6.4) Prodotti finiti", "180,00", "180,00"),
    ("3800", "B.7) Per servizi", "300,00", "300,00"),
    ("4000", "B.9) Per il personale", "200,00", "180,00"),
    ("4010", "B.9.a) Salari e stipendi", "150,00", "130,00"),
    ("4020", "B.9.b) Oneri sociali", "40,00", "40,00"),
    ("4030", "B.9.c) Trattamento di fine rapporto", "10,00", "10,00"),
    ("4100", "B.10) Ammortamenti e svalutazioni", "50,00", "50,00"),
    ("4110", "B.10.a) Ammortamento delle immobilizzazioni immateriali", "30,00", "30,00"),
    ("4120", "B.10.b) Ammortamento delle immobilizzazioni materiali", "20,00", "20,00"),
    ("4308", "C) Proventi e oneri finanziari", "-20,00", "-30,00"),
    ("4366", "C.16) Altri proventi finanziari", "5,00", "0,00"),
    ("4544", "C.17) Interessi e altri oneri finanziari", "25,00", "30,00"),
    ("", "Risultato prima delle imposte (A-B±C±D)", "130,00", "60,00"),
    ("4918", "20) Imposte sul reddito dell'esercizio, correnti, differite e anticipate", "30,00", "10,00"),
    ("4934", "21) Utile (Perdita) dell'esercizio", "100,00", "50,00"),
]


def _v(testo):
    return D(testo.replace(".", "").replace(",", "."))


def _righe(righe=RIGHE):
    return [(etichetta, _v(cor), _v(prec)) for _cod, etichetta, cor, prec in righe]


def test_legge_le_voci_di_legge_e_mai_i_conti_o_le_sotto_righe():
    letto = sep.estrai_da_righe(_righe())
    bs, ce = letto["bs"], letto["ce"]
    # il valore netto della voce, non i figli (lordo 700 + fondo 100 sommati)
    assert bs["sp02b_costi_sviluppo"] == D("600.00")
    assert bs["sp02_immob_immateriali"] == D("600.00")
    assert bs["sp04a_partecipazioni"] == D("450.00")
    assert bs["sp04c_crediti_immob_lungo"] == D("50.00")
    assert bs["sp05a_materie_prime"] == D("200.00")
    assert bs["sp05d_prodotti_finiti"] == D("300.00")
    # crediti: la scadenza la dice la riga "Esigibili entro/oltre", gli oltre non si
    # contano anche fra gli entro
    assert bs["sp06a_crediti_clienti_breve"] == D("800.00")
    assert bs["sp06g_crediti_altri_breve"] == D("100.00")  # C.II.5, sottoposte
    assert bs["sp06e_crediti_tributari_breve"] == D("340.00")
    assert bs["sp07e_crediti_tributari_lungo"] == D("60.00")
    assert bs["sp06_crediti_breve"] == D("1240.00")
    assert bs["sp07_crediti_lungo"] == D("60.00")
    # patrimonio netto voce per voce
    assert bs["sp11_capitale"] == D("1000.00")
    assert bs["sp12c_riserva_legale"] == D("100.00")
    assert bs["sp12f_riserva_copertura_flussi"] == D("-20.00")
    assert bs["sp12_riserve"] == D("80.00")
    assert bs["sp13_utile_perdita"] == D("100.00")
    assert bs["sp14c_strumenti_derivati_passivi"] == D("100.00")
    assert bs["sp15_tfr"] == D("120.00")
    # debiti: banche divise per scadenza, il gruppo negli altri debiti (mai perso)
    assert bs["sp16a_debiti_banche_breve"] == D("800.00")
    assert bs["sp17a_debiti_banche_lungo"] == D("500.00")
    assert bs["sp16d_debiti_fornitori_breve"] == D("700.00")
    assert bs["sp16g_altri_debiti_breve"] == D("100.00")
    assert bs["sp16_debiti_breve"] == D("1600.00")
    assert bs["sp17_debiti_lungo"] == D("500.00")
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("3600.00")
    # conto economico: il totale B.6, non la sotto-riga "B.6.2) Materie prime"
    assert ce["ce01_ricavi_vendite"] == D("1000.00")
    assert ce["ce05_materie_prime"] == D("300.00")
    assert ce["ce06_servizi"] == D("300.00")
    assert ce["ce08b_salari_stipendi"] == D("150.00")
    assert ce["ce08c_oneri_sociali"] == D("40.00")
    assert ce["ce08a_tfr_accrual"] == D("10.00")
    assert ce["ce08_costi_personale"] == D("200.00")
    assert ce["ce09_ammortamenti"] == D("50.00")
    assert ce["ce14_altri_proventi_finanziari"] == D("5.00")
    assert ce["ce15_oneri_finanziari"] == D("25.00")
    assert ce["ce20_imposte"] == D("30.00")
    assert letto["stampati"] == {"totale_attivo": D("3600.00"), "totale_passivo": D("3600.00")}
    assert letto["utile"] == D("100.00")


def test_legge_anche_l_anno_precedente():
    letto = sep.estrai_da_righe(_righe())
    bs, ce = letto["prior_bs"], letto["prior_ce"]
    assert bs["sp07e_crediti_tributari_lungo"] == D("90.00")
    assert bs["sp12f_riserva_copertura_flussi"] == D("-50.00")
    assert bs["sp13_utile_perdita"] == D("50.00")
    assert ce["ce05_materie_prime"] == D("280.00")
    assert letto["prior_stampati"]["totale_attivo"] == D("3300.00")
    assert letto["prior_utile"] == D("50.00")


def test_un_totale_stampato_che_non_torna_ritira_l_anno():
    # B.I stampato 600 ma la sua voce B.I.2 letta 650: il totale stampato decide, e
    # l'anno non si adotta (nessun numero corretto a mano)
    righe = [r if r[1] != "B.I.2) Costi di sviluppo" else (r[0], r[1], "650,00", r[3])
             for r in RIGHE]
    letto = sep.estrai_da_righe(_righe(righe))
    assert letto["bs"] is None and letto["ce"] is None
    assert "B.I" in letto["rifiuto"]
    assert letto["prior_bs"] is not None  # l'anno precedente torna, quello si'


def test_una_cella_vuota_vale_zero_e_il_totale_stampato_la_verifica():
    # il gestionale non stampa lo zero: accanto a un importo, la cella vuota vale zero. Qui
    # pero' B.7 valeva 300 nel precedente, e il totale B) stampato lo dice
    righe = [(et, cor, None if et.startswith("B.7)") else prec) for et, cor, prec in _righe()]
    letto = sep.estrai_da_righe(righe)
    assert letto["bs"] is not None
    assert letto["prior_bs"] is None
    assert letto["prior_rifiuto"].startswith("CE.B ")


def test_non_riconosce_un_documento_senza_percorsi_nell_etichetta():
    righe = [("Stato patrimoniale attivo", D("10"), D("10")),
             ("Immobilizzazioni", D("10"), D("10")),
             ("Stato patrimoniale passivo", D("10"), D("10")),
             ("Conto economico", D("0"), D("0"))]
    assert sep.estrai_da_righe(righe) is None


# --------------------------------------------------------------------------- #
# Tabelle di MinerU (scansione)
# --------------------------------------------------------------------------- #
def _contesto(righe_celle):
    rows = [SimpleNamespace(cells=[SimpleNamespace(text=t) for t in celle]) for celle in righe_celle]
    return SimpleNamespace(tables=[SimpleNamespace(rows=rows, caption="", page=0)])


def _celle(righe=RIGHE):
    out = [["Cod.", "Descrizione", "31/12/2025", "31/12/2024", "Differenza", "Scost. %"]]
    for cod, et, cor, prec in righe:
        diff = _v(cor) - _v(prec)
        d = f"{diff:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        out.append([cod, et, cor, prec, d, ""])
    return out


def test_mineru_tabella_letta_come_il_testo():
    letto = sep.estrai_da_mineru(_contesto(_celle()))
    assert letto["bs"]["sp07e_crediti_tributari_lungo"] == D("60.00")
    assert letto["ce"]["ce05_materie_prime"] == D("300.00")
    assert letto["prior_bs"]["sp13_utile_perdita"] == D("50.00")
    assert letto["anni"] == (2025, 2024)


def test_mineru_cifra_scivolata_nella_cella_dopo():
    # MinerU sposta l'ultima cifra di una cella all'inizio della successiva
    # ("62.871,92 | 0,0 | 0  62.871,9 | 2  100,000"): la Differenza stampata ricompone la riga
    celle = _celle()
    for c in celle:
        if c[1] == "B.I.2) Costi di sviluppo":
            c[2:6] = ["600,00", "500,0", "0         100,0", "0       20,000"]
    letto = sep.estrai_da_mineru(_contesto(celle))
    assert letto["bs"]["sp02b_costi_sviluppo"] == D("600.00")
    assert letto["prior_bs"]["sp02b_costi_sviluppo"] == D("500.00")


def test_mineru_precedente_vuoto_ricavato_dalla_differenza_stampata():
    # "C.16) Altri proventi finanziari | 511,63 | (vuoto) | -30.351,78 | -98,342": il
    # precedente e' esercizio - differenza, confermato dallo scostamento percentuale
    celle = _celle()
    for c in celle:
        if c[1] == "C.17) Interessi e altri oneri finanziari":
            c[2:6] = ["25,00", "", "-5,00", "-16,667"]
    letto = sep.estrai_da_mineru(_contesto(celle))
    assert letto["prior_ce"]["ce15_oneri_finanziari"] == D("30.00")


# --------------------------------------------------------------------------- #
# PDF di testo (stessa stampa, layer di testo nativo)
# --------------------------------------------------------------------------- #
def _pdf(tmp_path, righe=RIGHE, a_capo=("B.III.1) Partecipazioni in:",)):
    doc = fitz.open()
    font = fitz.Font("helv")
    pagina = doc.new_page(width=595, height=842)
    y = 60.0

    def destra(x_fine, y, testo):
        pagina.insert_text((x_fine - font.text_length(testo, fontsize=7), y), testo, fontsize=7)

    pagina.insert_text((150, 40), "Situazione contabile riclassificata dettagliata", fontsize=9)
    pagina.insert_text((31, y), "Cod.", fontsize=7)
    pagina.insert_text((158, y), "Descrizione", fontsize=7)
    destra(360, y, "31/12/2025")
    destra(430, y, "31/12/2024")
    destra(499, y, "Differenza")
    destra(559, y, "Scost. %")
    for cod, et, cor, prec in righe:
        y += 9
        if y > 820:
            pagina = doc.new_page(width=595, height=842)
            y = 40.0
        diff = _v(cor) - _v(prec)
        d = f"{diff:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if et in a_capo:
            # etichetta su due righe, importi a meta' altezza come nella stampa vera
            pagina.insert_text((75, y), et[:12], fontsize=7)
            pagina.insert_text((75, y + 7), et[12:], fontsize=7)
            y += 3.5
        else:
            pagina.insert_text((75, y), et, fontsize=7)
        if cod:
            pagina.insert_text((34, y), cod, fontsize=7)
        destra(373, y, cor)
        destra(443, y, prec)
        destra(513, y, d)
        if et in a_capo:
            y += 3.5
    percorso = tmp_path / "riclassificata.pdf"
    doc.save(percorso)
    doc.close()
    return str(percorso)


def test_pdf_di_testo_letto_dalle_colonne(tmp_path):
    letto = sep.estrai(_pdf(tmp_path))
    assert letto is not None
    assert letto["bs"]["sp04a_partecipazioni"] == D("450.00")   # etichetta a capo
    assert letto["bs"]["sp16g_altri_debiti_breve"] == D("100.00")
    assert letto["ce"]["ce05_materie_prime"] == D("300.00")
    assert letto["prior_ce"]["ce05_materie_prime"] == D("280.00")


def test_pdf_di_altra_famiglia_non_riconosciuto(tmp_path):
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text((50, 50), "STATO PATRIMONIALE", fontsize=9)
    p.insert_text((50, 70), "B) Immobilizzazioni 1.000,00", fontsize=9)
    percorso = tmp_path / "altro.pdf"
    doc.save(percorso)
    assert sep.estrai(str(percorso)) is None


# --------------------------------------------------------------------------- #
# Integrazione: l'importatore vero, senza chiave di nessun modello
# --------------------------------------------------------------------------- #
@pytest.fixture
def sessioni(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database.db import Base
    from importers import pdf_importer

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    for chiave in ("ANTHROPIC_API_KEY", "GX10_API_KEY", "IMPORT_MOTORE"):
        monkeypatch.delenv(chiave, raising=False)
    return sessions


def _anni_salvati(sessions, company_id):
    from database.models import FinancialYear
    with sessions() as db:
        anni = (db.query(FinancialYear).filter(FinancialYear.company_id == company_id)
                .order_by(FinancialYear.year.desc()).all())
        return [(fy.year, fy.validation_status,
                 {c.name: getattr(fy.balance_sheet, c.name) for c in fy.balance_sheet.__table__.columns},
                 {c.name: getattr(fy.income_statement, c.name) for c in fy.income_statement.__table__.columns})
                for fy in anni]


def test_scansione_letta_da_mineru_si_importa_senza_modello(tmp_path, sessioni):
    from importers import pdf_importer

    pdf = tmp_path / "scansione.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf)
    doc.close()
    contesto = _contesto(_celle())
    contesto.full_text = ("Situazione contabile riclassificata dettagliata\n"
                          + "\n".join(" | ".join(c) for c in _celle()))
    contesto.mineru_version = "3.4.5"
    contesto.page_texts = (contesto.full_text,)
    result = pdf_importer.import_pdf_balance_sheet(
        file_path=str(pdf), fiscal_year=2025, company_name="RICLASSIFICATA SCANSIONE",
        create_company=True, sector=1, user_id="etichette", extraction_context=contesto)
    assert result["success"] is True
    assert result["extraction_method"] == "mineru+schema_etichette"
    assert result["prior_year_imported"] is True
    (a1, s1, bs, ce), (a0, s0, bs0, ce0) = _anni_salvati(sessioni, result["company_id"])
    assert (a1, a0) == (2025, 2024)
    assert bs["sp07e_crediti_tributari_lungo"] == D("60.00")
    assert bs["sp12c_riserva_legale"] == D("100.00")
    assert bs["sp16g_altri_debiti_breve"] == D("100.00")
    assert ce["ce05_materie_prime"] == D("300.00")
    assert ce0["ce05_materie_prime"] == D("280.00")


def test_pdf_di_testo_si_importa_senza_modello(tmp_path, sessioni, monkeypatch):
    from importers import pdf_importer

    monkeypatch.setenv("IMPORT_MOTORE", "classico")  # descrive il percorso classico: lo snello è il default

    result = pdf_importer.import_pdf_balance_sheet(
        file_path=_pdf(tmp_path), fiscal_year=2025, company_name="RICLASSIFICATA TESTO",
        create_company=True, sector=1, user_id="etichette")
    assert result["success"] is True
    assert result["extraction_method"] == "schema_etichette"
    (_, _, bs, ce), _prec = _anni_salvati(sessioni, result["company_id"])
    assert bs["sp06_crediti_breve"] == D("1240.00")
    assert bs["sp07_crediti_lungo"] == D("60.00")
    assert ce["ce05_materie_prime"] == D("300.00")


def test_percorso_snello_lo_adotta_a_zero_chiamate(tmp_path):
    from importers.import_snello import deterministico

    esito = deterministico.tentativo(_pdf(tmp_path))
    assert esito["adottato"] is True
    assert esito["parser"] == "schema_etichette"
    assert esito["prior_stato"] == "letto"


def test_crediti_verso_sottoposte_hanno_un_campo():
    from importers.import_snello.percorsi import campo_da_percorso
    assert campo_da_percorso("SPA.C.II.5.E") == "sp06g"
    assert campo_da_percorso("SPA.C.II.5.O") == "sp07g"
