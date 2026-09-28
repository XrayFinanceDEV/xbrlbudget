from decimal import Decimal as D

import fitz
import pytest

from importers.import_snello.verifica import misura, normalizza_forma, soglia, tappa, totali_stampati


def _bs(**kw):
    base = {"sp03_immob_materiali": D("1000"), "sp09_disponibilita_liquide": D("500"),
            "sp11_capitale": D("800"), "sp13_utile_perdita": D("100"), "sp16_debiti_breve": D("600"),
            "sp16d_debiti_fornitori_breve": D("600")}
    base.update({k: D(v) for k, v in kw.items()})
    return base


CE = {"ce01_ricavi_vendite": D("400"), "ce06_servizi": D("300")}    # utile 100


def test_soglia_relativa_con_minimo():
    assert soglia(D("50000")) == D("100.00")
    assert soglia(D("2000000")) == D("2000.00")


def test_bilancio_che_quadra():
    m = misura(_bs(), CE)
    assert m["forma"] == "bilancio" and m["scarto_sp"] == 0 and m["scarto_ce"] == 0
    bs, ce, tappo, esito = tappa(_bs(), CE, m, D("100"))
    assert esito == "ok" and tappo is None


def test_forma_verifica_sposta_il_risultato_dell_anno_prima():
    bs = _bs(sp13_utile_perdita="-40", sp09_disponibilita_liquide="460")   # nel netto la perdita dell'anno prima; attivo = netto + debiti + utile corrente
    m = misura(bs, CE)
    assert m["forma"] == "verifica" and m["scarto_sp"] == 0
    nuovo = normalizza_forma(bs, CE, m)
    assert nuovo["sp12g_utili_perdite_portati"] == D("-40") and nuovo["sp13_utile_perdita"] == D("100")
    assert nuovo["sp12_riserve"] == D("-40")


def test_tappo_entro_soglia_su_altri_debiti_e_crediti():
    bs = _bs(sp09_disponibilita_liquide="550")                   # attivo in piu' di 50
    bs2, ce2, tappo, esito = tappa(bs, CE, misura(bs, CE), D("100"))
    assert esito == "tappo" and tappo["campo"] == "sp16g_altri_debiti_breve" and tappo["importo"] == "50.00"
    assert bs2["sp16g_altri_debiti_breve"] == D("50.00") and bs2["sp16_debiti_breve"] == D("650.00")
    bs = _bs(sp09_disponibilita_liquide="470")                   # attivo in meno di 30
    bs3, _, tappo, _ = tappa(bs, CE, misura(bs, CE), D("100"))
    assert tappo["campo"] == "sp06g_crediti_altri_breve" and bs3["sp06_crediti_breve"] == D("30.00")


def test_tappo_ce_su_servizi():
    ce = {"ce01_ricavi_vendite": D("400"), "ce06_servizi": D("290")}   # utile CE 110 contro sp13 100
    bs2, ce2, tappo, esito = tappa(_bs(), ce, misura(_bs(), ce), D("100"))
    assert esito == "tappo" and ce2["ce06_servizi"] == D("300.00") and tappo["ce"]["campo"] == "ce06_servizi"


def test_oltre_soglia_non_tocca_nulla():
    bs = _bs(sp09_disponibilita_liquide="900")
    bs2, ce2, tappo, esito = tappa(bs, CE, misura(bs, CE), D("100"))
    assert esito == "oltre_soglia" and tappo is None and bs2 == bs


def test_estrazione_vuota_non_e_ok():
    bs, ce = {}, {}
    m = misura(bs, ce)
    bs2, ce2, tappo, esito = tappa(bs, ce, m, D("100"))
    assert esito == "vuoto" and tappo is None and bs2 == bs and ce2 == ce


def test_forma_esplicita_non_maschera_lo_scarto_reale():
    # sp13 = 0 e utile CE = 100 con una vera eccedenza di attivo di 100 (sp13 azzerato,
    # non 100 come nella fixture base): con forma="bilancio" lo scarto si vede;
    # con forma=None l'euristica (somma degli scarti assoluti piu' piccola: 0 contro 200)
    # preferisce "verifica" e lo maschera. E' l'ambiguita' nota fra le due forme quando
    # utile CE e l'eccedenza di attivo coincidono: documentata qui, non risolta.
    bs = _bs(sp13_utile_perdita="0")
    m_bilancio = misura(bs, CE, forma="bilancio")
    assert m_bilancio["forma"] == "bilancio" and m_bilancio["scarto_sp"] == D("100.00")
    m_auto = misura(bs, CE)
    assert m_auto["forma"] == "verifica" and m_auto["scarto_sp"] == D("0.00")


def test_tappo_ce_negativo_si_rifiuta():
    ce = {"ce01_ricavi_vendite": D("50"), "ce06_servizi": D("5")}   # utile CE 45 contro sp13 100 (scarto -55)
    m = misura(_bs(), ce, forma="bilancio")
    bs2, ce2, tappo, esito = tappa(_bs(), ce, m, D("100"))
    assert esito == "oltre_soglia" and tappo is None and ce2["ce06_servizi"] == D("5")


def test_forma_invalida_solleva():
    with pytest.raises(ValueError):
        misura(_bs(), CE, forma="xyz")


# --- Task 15 (2026-09-27): i totali che il documento stampa da solo, ancora deterministica ---
# --- indipendente dall'estrattore (nessuna chiamata modello) --------------------------------


def test_totali_stampati_legge_i_totali_dichiarati_dal_documento(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Totale Attivo 5.000,00")
    page.insert_text((50, 70), "Totale Passivo 5.000,00")
    pdf = str(tmp_path / "c.pdf")
    doc.save(pdf)
    assert totali_stampati(pdf) == {"totale_attivo": D("5000"), "totale_passivo": D("5000")}


def test_totali_stampati_assenti_sono_none(tmp_path):
    doc = fitz.open()
    doc.new_page()
    pdf = str(tmp_path / "c.pdf")
    doc.save(pdf)
    assert totali_stampati(pdf) == {"totale_attivo": None, "totale_passivo": None}


def test_stampati_passivo_netto_del_risultato_si_corregge_come_il_vecchio_importatore():
    """Un 'Totale Passivo' stampato NETTO del risultato d'esercizio (comune nelle situazioni
    contabili a sezioni contrapposte, dove il risultato sta su una riga a parte accanto al
    pareggio) non deve apparire come uno scarto quanto l'utile: misura() lo corregge con la
    stessa regola del vecchio importatore (_reconcile_utile_in_passivo), prima di calcolare
    scarto_stampati."""
    bs = _bs()  # att=1500, pas=1500 (sp13=100 gia' incluso)
    stampati = {"totale_attivo": D("1500"), "totale_passivo": D("1400")}   # netto dell'utile 100
    m = misura(bs, CE, stampati, forma="bilancio")
    assert m["scarto_stampati"] == D("0.00")


def test_stampati_gap_non_coincidente_col_risultato_non_si_corregge():
    """Un gap che NON coincide col risultato (una vera sotto-estrazione, non una convenzione
    di stampa) non si tocca: la correzione e' condizionata, non un pareggio forzato."""
    bs = _bs()
    stampati = {"totale_attivo": D("1500"), "totale_passivo": D("1000")}  # gap 500, non 100
    m = misura(bs, CE, stampati, forma="bilancio")
    assert m["scarto_stampati"] == D("500.00")


# --- Task 21 (2026-09-27): il totale stampato si confronta sulla massa grezza per lato ------
# --- (prima di applica_lato/netting), mai contro att/pas netti - diagnosi TM 589/590 --------


def test_misura_senza_grezzo_si_comporta_come_prima():
    """Comportamento di sempre (nessun ``grezzo``): scarto_stampati confronta lo stampato
    contro att/pas NETTI - invariato dal Task 21 per ogni chiamante che non passa grezzo."""
    bs = _bs()  # att=1500, pas=1500 (sp13=100 incluso)
    stampati = {"totale_attivo": D("1500"), "totale_passivo": D("1400")}  # netto dell'utile 100
    m = misura(bs, CE, stampati, forma="bilancio")
    assert m["scarto_stampati"] == D("0.00")


def test_misura_con_grezzo_confronta_la_massa_grezza_non_i_netti():
    """Un fondo stampato nel lato passivo ma nettato contro l'attivo (sp03) nella
    classificazione fa divergere att/pas netti dalla massa grezza per lato che il documento
    stampa davvero: senza ``grezzo`` lo scarto_stampati vedrebbe un falso sbilancio (netto
    1100/1100 contro lo stampato grezzo 1400/1400); con ``grezzo`` fornito lo scarto e' zero,
    perche' la base di confronto e' la massa grezza, non il netto."""
    bs = _bs(sp03_immob_materiali="900", sp09_disponibilita_liquide="200", sp11_capitale="900",
             sp16_debiti_breve="200", sp16d_debiti_fornitori_breve="200", sp13_utile_perdita="0")
    ce = {}  # utile CE 0, cosi' att(1100)=pas(1100) nel netto
    stampati = {"totale_attivo": D("1400"), "totale_passivo": D("1400")}  # grezzo per lato, come stampato
    grezzo = {"attivo": D("1400"), "passivo": D("1400")}
    m_senza = misura(bs, ce, stampati, forma="bilancio")
    assert m_senza["attivo"] == D("1100.00") and m_senza["passivo"] == D("1100.00")
    assert m_senza["scarto_stampati"] == D("300.00")   # falso sbilancio: netto (1100) vs grezzo stampato (1400)
    m_con = misura(bs, ce, stampati, forma="bilancio", grezzo=grezzo)
    assert m_con["attivo"] == D("1100.00") and m_con["passivo"] == D("1100.00")  # att/pas netti invariati
    assert m_con["scarto_stampati"] == D("0.00")


def test_misura_con_grezzo_rileva_ancora_un_vero_scarto():
    """``grezzo`` non spegne il contraddittorio: se la massa grezza per lato non coincide col
    totale stampato (una riga davvero mancante), lo scarto resta e si vede."""
    bs = _bs(sp03_immob_materiali="900", sp09_disponibilita_liquide="200", sp11_capitale="900",
             sp16_debiti_breve="200", sp16d_debiti_fornitori_breve="200", sp13_utile_perdita="0")
    ce = {}
    stampati = {"totale_attivo": D("1650"), "totale_passivo": D("1400")}  # il documento dichiara 1650, non 1400
    grezzo = {"attivo": D("1400"), "passivo": D("1400")}
    m = misura(bs, ce, stampati, forma="bilancio", grezzo=grezzo)
    assert m["scarto_stampati"] == D("250.00")


def test_totali_stampati_con_regola_legge_la_colonna_saldo_finale(tmp_path):
    """Task 21: con ``regola`` (struttura a 3 colonne, saldo_finale ultima) si legge la
    colonna giusta anche quando il rigo di controllo stampa piu' importi per lato - non piu'
    il primo numero dopo il marcatore ('Saldo non rettificato', il difetto TM 589/590)."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Totale Attivita' 1.000,00 400,00 1.400,00")
    page.insert_text((50, 70), "Totale Passivita' 1.400,00 1.400,00")
    pdf = str(tmp_path / "c.pdf")
    doc.save(pdf)
    regola = {"n": 3, "k": 2}
    assert totali_stampati(pdf, regola=regola) == {"totale_attivo": D("1400.00"), "totale_passivo": D("1400.00")}
    # senza regola (comportamento di sempre): il primo numero, sbagliato su questo layout.
    assert totali_stampati(pdf) == {"totale_attivo": D("1000.00"), "totale_passivo": D("1400.00")}


def test_totali_stampati_numero_scritto_prima_della_propria_etichetta(tmp_path):
    """Task 22, G3, fix round 1 (diagnosi budget_297): il content-stream a volte scrive
    l'importo di un totale PRIMA della propria etichetta ("3.680.418,00\\nTOTALE ATTIVO", non
    "TOTALE ATTIVO\\n3.680.418,00") - un rigo solo fuori ordine, non un intero documento
    scomposto. Senza correzione l'ancora resta sul subtotale che la precede
    ("Totale attivo circolante (C)", correttamente ordinato) invece del vero totale."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 90), "Totale attivo circolante (C)")
    page.insert_text((300, 90), "1.041.258,00")
    page.insert_text((300, 110), "3.680.418,00")     # il numero, PRIMA della sua etichetta
    page.insert_text((50, 110), "TOTALE ATTIVO")     # ...nel content-stream
    pdf = str(tmp_path / "c.pdf")
    doc.save(pdf)
    assert totali_stampati(pdf)["totale_attivo"] == D("3680418.00")


def test_totali_stampati_non_disturba_etichette_riga_a_riga(tmp_path):
    """Non regressione: un altro meccanismo di _declared_control_totals
    (_section_heading_total) legge un'etichetta SU UNA RIGA e il proprio importo sulla riga
    IMMEDIATAMENTE seguente ("Stato patrimoniale attivo\\n1.603.874,24", il formato reale di
    budget_280/320/379) - l'aggiunta del testo ordinato per posizione (solo per attivo/
    passivo, "il maggiore vince") non deve rompere questo meccanismo, che legge il testo
    normale, invariato."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 90), "Stato patrimoniale attivo")
    page.insert_text((50, 110), "1.603.874,24")
    pdf = str(tmp_path / "c.pdf")
    doc.save(pdf)
    assert totali_stampati(pdf)["totale_attivo"] == D("1603874.24")
