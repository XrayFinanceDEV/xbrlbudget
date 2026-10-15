"""Bilancio di verifica a colonna unica con marcatori di riga IE/E (budget_680, FTC Srl):
sezione a 2 cifre, mastro a 4 cifre a sinistra, conto a 5 cifre rientrato, cinque colonne
numeriche con il saldo finale e il suo segno D/A a destra. PDF sintetico, mai il file reale.
"""
from decimal import Decimal as D

import fitz

from importers.import_snello.deterministico import tentativo
from importers.situazione_contabile_parser import extract_situazione_contabile, is_verifica_ie


def _riga(page, y, codice, descrizione, saldo, segno, marcatore):
    x = 3 if len(codice) <= 4 else 51
    page.insert_text((x, y), codice, fontsize=7)
    page.insert_text((79, y), descrizione, fontsize=7)
    if saldo:
        page.insert_text((776 - 4.2 * len(saldo), y), saldo, fontsize=7)
        page.insert_text((780, y), segno, fontsize=7)
    page.insert_text((788, y - 6), marcatore, fontsize=7)   # riga propria, come nel PDF vero


def _pagina(doc, titolo):
    p = doc.new_page(width=820, height=572)
    p.insert_text((0, 20), "BILANCIO DI VERIFICA AL 31/05/2026", fontsize=9)
    p.insert_text((280, 38), titolo, fontsize=9)
    p.insert_text((426, 58), "Saldo al", fontsize=7)
    p.insert_text((648, 58), "Saldo Periodo", fontsize=7)
    p.insert_text((741, 58), "Saldo al", fontsize=7)
    return p


def _documento(path, *, patrimonio="1.200,00"):
    doc = fitz.open()
    sp = _pagina(doc, "STATO PATRIMONIALE")
    righe_sp = [
        ("01", "ATTIVITA'   ATTIVITA'", "4.050,00", "D", "IE"),
        ("0102", "BANCHE", "500,00", "D", "IE"),
        ("10206", "BANCA DI ASTI C/C000001001576", "700,00", "D", "E"),
        ("10207", "CREDEM C/C 010000001673", "200,00", "A", "E"),
        ("0107", "GIACENZA", "800,00", "D", "IE"),
        ("10701", "COLORANTI/GIACENZE", "800,00", "D", "E"),
        ("0113", "CLIENTI", "2.750,00", "D", "IE"),
        ("11301", "LORO PIANA SPA", "2.750,00", "D", "E"),
        ("02", "PASSIVITA'   PASSIVITA'", "3.850,00", "A", "IE"),
        ("0208", "FONDI DI ACCANTONAMENTO", "600,00", "A", "IE"),
        ("20801", "F.DO INDENNITA'ANZIANITA'DIPEND", "600,00", "A", "E"),
        ("0210", "CAPITALE NETTO", patrimonio, "A", "IE"),
        ("21005", "CAPITALE SOCIALE", patrimonio, "A", "E"),
        ("0225", "FORNITORI", "2.050,00", "A", "IE"),
        ("22501", "ARTEX S.R.L.", "2.050,00", "A", "E"),
    ]
    y = 85
    for r in righe_sp:
        _riga(sp, y, *r)
        y += 13
    ce = _pagina(doc, "CONTO ECONOMICO")
    righe_ce = [
        ("03", "COSTI   COSTI", "1.800,00", "D", "IE"),
        ("0301", "ACQUISTO MATERIE PRIME", "1.500,00", "D", "IE"),
        ("30101", "COLORANTI", "1.500,00", "D", "E"),
        ("0304", "ONERI FINANZIARI", "300,00", "D", "IE"),
        ("30401", "ASSICURAZIONI VARIE", "250,00", "D", "E"),
        ("30452", "INT.PASSIVI FIN.CREDEM N.617/7663219", "50,00", "D", "E"),
        ("04", "RICAVI   RICAVI", "2.000,00", "A", "IE"),
        ("0401", "RICAVI LAVORAZIONI C/TERZI", "2.000,00", "A", "IE"),
        ("40101", "RICAVI LAVORAZIONI C/TERZI", "2.000,00", "A", "E"),
    ]
    y = 85
    for r in righe_ce:
        _riga(ce, y, *r)
        y += 13
    ce.insert_text((300, y + 10), "UTILE ESERCIZIO:", fontsize=7)
    ce.insert_text((400, y + 10), "200,00", fontsize=7)
    doc.save(path)
    doc.close()


def test_verifica_ie_si_legge_e_si_verifica_sui_totali(tmp_path):
    path = tmp_path / "ie.pdf"
    _documento(str(path))
    assert is_verifica_ie("".join(p.get_text() for p in fitz.open(str(path))))
    bs, ce = extract_situazione_contabile(str(path))
    assert bs["sp09"] == D("700.00")             # la banca a saldo dare e' liquidita'
    assert bs["sp05"] == D("800.00")
    assert bs["sp06"] == D("2750.00")            # il cliente col solo nome: dal mastro
    assert bs["sp15"] == D("600.00")             # il TFR col nome di prima del 1982
    assert bs["sp13"] == D("200.00")
    assert bs["sp16"] == D("2250.00")            # fornitore + la banca a saldo avere
    assert bs["totale_attivo"] == bs["totale_passivo"] == D("4250.00")
    assert ce["ce05"] == D("1500.00")
    assert ce["ce15"] == D("50.00")              # gli interessi si', le assicurazioni no
    assert ce["ce12"] == D("250.00")

    r = tentativo(str(path))
    assert r["adottato"] and r["esito"] == "ok"


def test_verifica_che_non_pareggia_si_importa_squadrata_con_i_totali(tmp_path):
    # il capitale stampato e' piu' basso di 150: dare 5.850, avere 5.700 nei totali
    # stampati; le sezioni ricostruiscono comunque i loro totali
    path = tmp_path / "ie.pdf"
    _documento(str(path), patrimonio="1.050,00")
    doc = fitz.open(str(path))
    p = doc[0]
    for r in p.search_for("3.850,00"):
        p.add_redact_annot(r)
    p.apply_redactions()
    p.insert_text((776 - 4.2 * 8, 85 + 13 * 8), "3.700,00", fontsize=7)
    path2 = tmp_path / "ie2.pdf"
    doc.save(str(path2))
    bs, _ce = extract_situazione_contabile(str(path2))
    assert bs["totale_attivo"] - bs["totale_passivo"] == D("150.00")
    assert bs["_verifica_dare"] - bs["_verifica_avere"] == D("150.00")

    r = tentativo(str(path2))
    assert r["adottato"] and r["esito"] == "squadrato"
    assert r["causa"] == "documento_sbilanciato"
    assert r["contraddizioni"][0]["tipo"] == "verifica"


def test_sezione_che_non_torna_col_suo_totale_non_si_legge(tmp_path):
    path = tmp_path / "ie.pdf"
    _documento(str(path))
    doc = fitz.open(str(path))
    p = doc[0]
    for r in p.search_for("3.850,00"):
        p.add_redact_annot(r)
    p.apply_redactions()
    p.insert_text((776 - 4.2 * 8, 85 + 13 * 8), "3.900,00", fontsize=7)
    path2 = tmp_path / "ie2.pdf"
    doc.save(str(path2))
    bs, _ce = extract_situazione_contabile(str(path2))
    assert not bs.get("totale_attivo")           # mai una lettura non verificata


def test_sigle_dei_cespiti_e_conti_sotto_un_mastro_di_controparti():
    """budget_680: sigle che nessuna regola riconosceva, e un cliente con LICENZE nel nome."""
    from importers.situazione_contabile_parser import _classify_sp_attivo, _sp03_detail_field
    assert _sp03_detail_field("F.DO AMM.MACC.AMBIENTE CORROS.") == "sp03b_impianti_macchinari"
    assert _sp03_detail_field("F.DO AMM.IMP.DEPURAZIONE ACQUE") == "sp03b_impianti_macchinari"
    assert _sp03_detail_field("F.DO AMM.ATTREZ./REPARTO OFFIC") == "sp03c_attrezzature"
    assert _sp03_detail_field("F.DO AMM.MACCHINE UFF.ELETTRON. PC") == "sp03d_altri_beni"
    assert _sp03_detail_field("IMMOBILIZZI TECNICI") is None     # MOBIL non dentro IMMOBIL
    assert _classify_sp_attivo("MATERIALE HARDWARE") == "gross_sp03"
    assert _classify_sp_attivo("CERTIFICAZIONI_IMM") == "gross_sp02"


def _con_apertura(path, path_out, apertura_attivo, apertura_passivo):
    """Il documento che non pareggia di 150, con la colonna d'apertura stampata sulle sezioni."""
    _documento(str(path), patrimonio="1.050,00")
    doc = fitz.open(str(path))
    p = doc[0]
    for r in p.search_for("3.850,00"):
        p.add_redact_annot(r)
    p.apply_redactions()
    p.insert_text((776 - 4.2 * 8, 85 + 13 * 8), "3.700,00", fontsize=7)
    for y, importo, segno in ((85, apertura_attivo, "D"), (85 + 13 * 8, apertura_passivo, "A")):
        p.insert_text((459 - 4.2 * len(importo), y), importo, fontsize=7)
        p.insert_text((463, y), segno, fontsize=7)
    doc.save(str(path_out))


def test_risultato_dell_anno_prima_non_riaperto_nella_colonna_d_apertura(tmp_path):
    """budget_680: saldo al 31/12 dell'anno prima sbilanciato della stessa cifra del saldo
    finale -> e' il risultato dell'anno prima non riaperto, negli utili portati a nuovo."""
    path = tmp_path / "ie2.pdf"
    _con_apertura(tmp_path / "ie.pdf", path, "4.050,00", "3.900,00")
    bs, _ce = extract_situazione_contabile(str(path))
    assert bs["sp12g_utili_perdite_portati"] == D("150.00")
    assert bs["totale_attivo"] == bs["totale_passivo"]
    assert bs["_risultato_anno_prima_apertura"] == D("150.00")
    r = tentativo(str(path))
    assert r["adottato"] and r["esito"] == "ok"


def test_apertura_che_non_spiega_lo_sbilancio_non_tocca_nulla(tmp_path):
    path = tmp_path / "ie2.pdf"
    _con_apertura(tmp_path / "ie.pdf", path, "4.050,00", "3.950,00")     # apertura: 100, non 150
    bs, _ce = extract_situazione_contabile(str(path))
    assert "_risultato_anno_prima_apertura" not in bs
    assert bs["totale_attivo"] - bs["totale_passivo"] == D("150.00")
