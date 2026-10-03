from decimal import Decimal as D

import fitz
import pytest

from importers.import_snello.verifica import misura, normalizza_forma, soglia, soglia_tappo, tappa, totali_stampati


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
    bs = _bs(sp09_disponibilita_liquide="508")                   # attivo in piu' di 8
    bs2, ce2, tappo, esito = tappa(bs, CE, misura(bs, CE), D("100"))
    assert esito == "tappo" and tappo["campo"] == "sp16g_altri_debiti_breve" and tappo["importo"] == "8.00"
    assert bs2["sp16g_altri_debiti_breve"] == D("8.00") and bs2["sp16_debiti_breve"] == D("608.00")
    bs = _bs(sp09_disponibilita_liquide="495")                   # attivo in meno di 5
    bs3, _, tappo, _ = tappa(bs, CE, misura(bs, CE), D("100"))
    assert tappo["campo"] == "sp06g_crediti_altri_breve" and bs3["sp06_crediti_breve"] == D("5.00")


def test_tappo_massimo_dieci_euro_decisione_proprietario_2026_10_03():
    """Il tappo chiude al massimo 10,00 euro per controllo (SP e CE ciascuno), qualunque sia
    la soglia relativa: 10,00 si tampona, 10,01 no (oltre soglia: rilettura, poi squadrato)."""
    assert soglia_tappo() == D("10.00")
    bs = _bs(sp09_disponibilita_liquide="510")
    assert tappa(bs, CE, misura(bs, CE), D("100"))[3] == "tappo"
    bs = _bs(sp09_disponibilita_liquide="510.01")
    bs2, _, tappo, esito = tappa(bs, CE, misura(bs, CE), D("100"))
    assert esito == "oltre_soglia" and tappo is None and bs2 == bs
    bs = _bs(sp09_disponibilita_liquide="490")
    assert tappa(bs, CE, misura(bs, CE), D("100"))[3] == "tappo"
    bs = _bs(sp09_disponibilita_liquide="489.99")
    assert tappa(bs, CE, misura(bs, CE), D("100"))[3] == "oltre_soglia"
    ce = {"ce01_ricavi_vendite": D("400"), "ce06_servizi": D("289.99")}   # utile CE 110,01: scarto 10,01
    assert tappa(_bs(), ce, misura(_bs(), ce), D("100"))[3] == "oltre_soglia"
    ce = {"ce01_ricavi_vendite": D("400"), "ce06_servizi": D("290")}      # scarto 10,00
    assert tappa(_bs(), ce, misura(_bs(), ce), D("100"))[3] == "tappo"


def test_scarto_sui_totali_stampati_al_massimo_dieci_euro_decisione_proprietario_2026_10_03():
    """Decisione del proprietario (2026-10-03): anche il confronto con il totale che il documento
    stampa tollera al massimo 10 euro, come il tappo. Prima restava sulla soglia relativa (almeno
    100 euro): 50 euro di attivo stampato non letti passavano come "ok". Oltre i 10 euro si
    rilegge e, se non torna, si salva squadrato con avviso: l'utente corregge in Rettifiche."""
    bs = _bs()
    m = misura(bs, CE, {"totale_attivo": D("1550")})
    assert m["scarto_stampati"] == D("50.00")
    assert tappa(bs, CE, m, D("100"))[3] == "oltre_soglia"
    m = misura(bs, CE, {"totale_attivo": D("1510")})
    assert tappa(bs, CE, m, D("100"))[3] == "ok"
    m = misura(bs, CE, {"totale_attivo": D("1511")})
    assert tappa(bs, CE, m, D("100"))[3] == "oltre_soglia"
    # mai oltre la soglia relativa quando questa e' piu' bassa (mai il caso reale: minimo 100)
    m = misura(bs, CE, {"totale_attivo": D("1508")})
    assert tappa(bs, CE, m, D("5"))[3] == "oltre_soglia"


def test_tappo_ce_su_servizi():
    ce = {"ce01_ricavi_vendite": D("400"), "ce06_servizi": D("295")}   # utile CE 105 contro sp13 100
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
    ce = {"ce01_ricavi_vendite": D("97"), "ce06_servizi": D("2")}   # utile CE 95 contro sp13 100 (scarto -5)
    m = misura(_bs(), ce, forma="bilancio")
    bs2, ce2, tappo, esito = tappa(_bs(), ce, m, D("100"))
    assert esito == "oltre_soglia" and tappo is None and ce2["ce06_servizi"] == D("2")


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
    """Task 22, G3, fix round 2 (diagnosi budget_297): il content-stream a volte scrive
    l'importo di un totale PRIMA della propria etichetta ("3.680.418,00\\nTOTALE ATTIVO", non
    "TOTALE ATTIVO\\n3.680.418,00") - un rigo solo fuori ordine, non un intero documento
    scomposto. La lettura primaria (testo di sempre) ancora sul subtotale che precede
    ("Totale attivo circolante (C)") ed e' INCOERENTE con il passivo (stesso difetto, ancora
    su un altro subtotale): solo allora si prova il testo ordinato per posizione, che legge
    sia attivo sia passivo correttamente (coerenti fra loro) - fix round 2, mai una fusione
    delle due fonti (round 1, scartato: rompeva altri file)."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 90), "Totale attivo circolante (C)")
    page.insert_text((300, 90), "1.041.258,00")
    page.insert_text((300, 110), "3.680.418,00")     # il numero, PRIMA della sua etichetta
    page.insert_text((50, 110), "TOTALE ATTIVO")     # ...nel content-stream
    page.insert_text((50, 140), "Totale debiti")
    page.insert_text((300, 140), "999.000,00")       # un altro subtotale, diverso dal vero passivo
    page.insert_text((300, 160), "3.680.418,00")     # il vero totale passivo, stesso difetto
    page.insert_text((50, 160), "TOTALE PASSIVO")
    pdf = str(tmp_path / "c.pdf")
    doc.save(pdf)
    assert totali_stampati(pdf) == {"totale_attivo": D("3680418.00"), "totale_passivo": D("3680418.00")}


def test_totali_stampati_non_disturba_etichette_riga_a_riga(tmp_path):
    """Non regressione: un altro meccanismo di _declared_control_totals
    (_section_heading_total) legge un'etichetta SU UNA RIGA e il proprio importo sulla riga
    IMMEDIATAMENTE seguente ("Stato patrimoniale attivo\\n1.603.874,24", il formato reale di
    budget_280/320/379) - solo attivo qui (nessun passivo dichiarato, quindi la lettura resta
    "non coerente" per definizione), ma il fix round 2 non tenta nemmeno l'ordinamento per
    posizione perche' l'ordinato non aggiunge nulla di coerente in piu' (nessun passivo li'
    nemmeno): resta la lettura primaria, che _section_heading_total legge correttamente."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 90), "Stato patrimoniale attivo")
    page.insert_text((50, 110), "1.603.874,24")
    pdf = str(tmp_path / "c.pdf")
    doc.save(pdf)
    assert totali_stampati(pdf)["totale_attivo"] == D("1603874.24")


def test_totali_stampati_non_prova_l_ordinamento_se_gia_coerente(tmp_path, monkeypatch):
    """Fix round 2: quando la lettura primaria e' gia' coerente (attivo=passivo entro
    soglia), il testo ordinato per posizione non si costruisce nemmeno - un costo evitato, e
    la garanzia che nessun file gia' corretto (TM 589/590 nel banco reale) possa mai leggere
    un numero diverso da quello di sempre."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Totale Attivo 5.000,00")
    page.insert_text((50, 70), "Totale Passivo 5.000,00")
    pdf = str(tmp_path / "c.pdf")
    doc.save(pdf)

    def _esplode(*a, **k):
        raise AssertionError("_extract_full_text(forza_ordinamento=True) non doveva essere chiamata")

    import importers.pdf_extractor_llm as pdf_llm
    originale = pdf_llm._extract_full_text

    def _sorvegliata(file_path, max_pages=60, forza_ordinamento=False):
        if forza_ordinamento:
            _esplode()
        return originale(file_path, max_pages=max_pages, forza_ordinamento=forza_ordinamento)

    monkeypatch.setattr(pdf_llm, "_extract_full_text", _sorvegliata)
    assert totali_stampati(pdf) == {"totale_attivo": D("5000"), "totale_passivo": D("5000")}


def test_misura_con_grezzo_aggiunge_l_utile_al_passivo_grezzo():
    """TM 589 (2026-09-28): il grezzo per lato non contiene il risultato corrente (da_foglie
    non lo fa mai entrare dalle righe: sp13 = utile CE), mentre lo stampato passivo, netto
    del risultato, viene ripiegato con l'utile da _fold_utile_in_passivo. Il confronto deve
    quindi usare passivo grezzo + utile: altrimenti lo scarto e' sempre pari all'utile."""
    bs = {"sp09_disponibilita_liquide": D("1302133.80"), "sp11_capitale": D("1273134.72"),
          "sp13_utile_perdita": D("28999.08")}
    ce = {"ce01_ricavi_vendite": D("28999.08")}
    stampati = {"totale_attivo": D("1302133.80"), "totale_passivo": D("1273134.72")}
    grezzo = {"attivo": D("1302133.80"), "passivo": D("1273134.72")}
    m = misura(bs, ce, stampati, forma="bilancio", grezzo=grezzo)
    assert m["utile_ce"] == D("28999.08")
    assert m["scarto_stampati"] == D("0.00")
    # una riga passiva davvero mancante resta visibile
    m2 = misura(bs, ce, stampati, forma="bilancio",
                grezzo={"attivo": D("1302133.80"), "passivo": D("1263134.72")})
    assert m2["scarto_stampati"] == D("10000.00")


def test_misura_con_grezzo_perdita_stampata_nel_lato_attivo():
    """D2M (passata4, 2026-09-28): a sezioni contrapposte la perdita si stampa nel lato
    attivo per arrivare al pareggio. Il totale letto sulla colonna di saldo e' il pareggio
    (attivo grezzo + perdita = passivo grezzo): lo stesso risultato puo' stare su un lato o
    sull'altro, e nessuna delle due convenzioni e' uno sbilancio."""
    bs = {"sp09_disponibilita_liquide": D("300168.27"), "sp11_capitale": D("341299.18"),
          "sp13_utile_perdita": D("-41130.91")}
    ce = {"ce06_servizi": D("41130.91")}
    stampati = {"totale_attivo": D("341299.18"), "totale_passivo": D("341299.18")}
    grezzo = {"attivo": D("300168.27"), "passivo": D("341299.18")}
    m = misura(bs, ce, stampati, forma="bilancio", grezzo=grezzo)
    assert m["utile_ce"] == D("-41130.91")
    assert m["scarto_stampati"] == D("0.00")
    # una riga attiva davvero mancante resta visibile
    m2 = misura(bs, ce, stampati, forma="bilancio",
                grezzo={"attivo": D("290168.27"), "passivo": D("341299.18")})
    assert m2["scarto_stampati"] == D("10000.00")
