"""Colonne di un prospetto IV-CEE comparato intestato a PAROLE, non a date.

Il "bilancio riclassificato UE" stampa ``Importo corrente | Importo comparato |
Scostamento | %`` e allinea i quattro importi a destra. Tre difetti nascevano da
qui (issue #18, verdetto in #4), tutti su una fonte che quadra da sola al
centesimo:

* una riga con la cella dell'anno corrente VUOTA stampa tre numeri invece di
  quattro, e la lettura lineare prende il primo — cioe' il comparato;
* la sezione patrimoniale veniva chiusa due pagine dopo il proprio inizio (il
  documento non stampa alcun "Totale passivo"), e la coda del passivo — con i
  ratei e risconti — non arrivava mai all'estrattore;
* `_unclassified_mass` valeva 0 mentre 178.663,25 di massa stampata non erano
  arrivati in nessun campo.

Le prove qui sotto girano sulla geometria, senza alcuna chiamata all'LLM: sono
il diaframma deterministico dove i tre difetti vivono davvero. In coda ci sono
le prove sul file reale, saltate quando il PDF non e' in locale.
"""
import os
from decimal import Decimal

import fitz
import pytest

from importers.iv_cee_hierarchy import declare_unclassified_mass, reconcile_ivcee_balance
from importers.pdf_extractor_llm import (
    _column_of,
    _labelled_column_anchors,
    _page_column_anchors,
    _reconcile_blank_current_ce_cells,
    _reconcile_blank_current_sp_cells,
    _recover_printed_sp_rows,
    find_section_pages,
)


D = Decimal

# Bordi destri delle quattro colonne, come li stampa il gestionale.
CURRENT_X, PRIOR_X, DEVIATION_X, PERCENT_X = 424.0, 489.0, 543.0, 575.0
FONT, SIZE = "helv", 9


def _right(page, x_right, y, text):
    """Scrive `text` allineato a DESTRA su x_right (le colonne lo sono)."""
    width = fitz.get_text_length(text, fontname=FONT, fontsize=SIZE)
    page.insert_text((x_right - width, y), text, fontname=FONT, fontsize=SIZE)


def _header(page):
    _right(page, CURRENT_X, 100, "corrente")
    _right(page, PRIOR_X, 100, "comparato")
    _right(page, DEVIATION_X, 100, "Scostamento")
    _right(page, PERCENT_X, 100, "%")


def _row(page, y, label, current=None, prior=None, deviation=None, percent=None):
    page.insert_text((20, y), label, fontname=FONT, fontsize=SIZE)
    for value, x in (
        (current, CURRENT_X), (prior, PRIOR_X),
        (deviation, DEVIATION_X), (percent, PERCENT_X),
    ):
        if value is not None:
            _right(page, x, y, value)


# ---------------------------------------------------------------------------
# A. la cella dell'anno corrente vuota vale zero, non il comparato
# ---------------------------------------------------------------------------

def _comparative_ce_pdf(path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((90, 60), "BILANCIO RICLASSIFICATO UE dal 01/01/2026 al 30/06/2026")
    page.insert_text((20, 80), "Descrizione")
    _header(page)
    _row(page, 140, "CONTO ECONOMICO")
    _row(page, 160, "1) Ricavi delle vendite e delle prestazioni",
         "2.104.755,45", "3.761.087,73", "-1.656.332,28", "-44,03")
    # corrente VUOTO: restano tre numeri, il primo dei quali e' il comparato
    _row(page, 180, "4) Incrementi di immobilizzazioni per lavori interni",
         None, "90.603,75", "-90.603,75", "-100,00")
    _row(page, 200, "d) svalutazioni dei crediti compresi nell'attivo circolante",
         None, "2.452,23", "-2.452,23", "-100,00")
    _row(page, 220, "20) Imposte sul reddito dell'esercizio",
         None, "28.773,00", "-28.773,00", "-100,00")
    doc.save(path)
    doc.close()


def test_una_cella_corrente_vuota_estrae_zero_non_il_comparato(tmp_path):
    pdf_path = tmp_path / "comparato.pdf"
    _comparative_ce_pdf(str(pdf_path))

    current, prior = _reconcile_blank_current_ce_cells(
        str(pdf_path),
        {
            "ce01_ricavi_vendite": D("2104755.45"),
            "ce03_lavori_interni": D("90603.75"),
            "ce09d_svalutazione_crediti": D("2452.23"),
            "ce20_imposte": D("28773.00"),
        },
        {"ce03_lavori_interni": D("0"), "ce20_imposte": D("0")},
    )

    assert current["ce03_lavori_interni"] == D("0")
    assert current["ce09d_svalutazione_crediti"] == D("0")
    assert current["ce20_imposte"] == D("0")
    # la riga con QUATTRO numeri ha una cella corrente piena: non si tocca
    assert current["ce01_ricavi_vendite"] == D("2104755.45")
    # il valore letto non sparisce: e' dell'anno precedente e li' finisce
    assert prior["ce03_lavori_interni"] == D("90603.75")


def test_le_colonne_di_analisi_non_passano_per_anno_precedente(tmp_path):
    """Scostamento e % sono le uniche altre celle piene di una riga a corrente vuoto.

    Senza un'ancora per ciascuna delle quattro colonne, il confronto "la piu'
    vicina fra due" le attribuisce entrambe al comparato: i tre valori non
    concordano, la guardia sull'unanimita' scatta, e la riga resta sbagliata.
    """
    pdf_path = tmp_path / "quattro-colonne.pdf"
    _comparative_ce_pdf(str(pdf_path))

    with fitz.open(pdf_path) as document:
        words = document[0].get_text("words", sort=True)
        anchors = _page_column_anchors(words)
        assert anchors is not None and anchors.right_edge
        assert len(anchors.others) == 2
        deviation = next(
            word for word in words if str(word[4]).strip() == "-90.603,75"
        )
        assert _column_of(deviation, anchors) == "other"
        comparato = next(
            word for word in words if str(word[4]).strip() == "90.603,75"
        )
        assert _column_of(comparato, anchors) == "prior"


def test_le_date_del_periodo_non_sono_una_coppia_di_colonne(tmp_path):
    """``dal 01/01/2026 al 30/06/2026`` sta su una riga sola e non intesta nulla.

    Il riconoscimento per data la scambiava per due colonne affiancate a meta'
    pagina; le intestazioni a parole vanno provate per prime.
    """
    pdf_path = tmp_path / "periodo.pdf"
    _comparative_ce_pdf(str(pdf_path))

    with fitz.open(pdf_path) as document:
        words = document[0].get_text("words", sort=True)
        labelled = _labelled_column_anchors(words)
        assert labelled is not None
        assert labelled.current == pytest.approx(CURRENT_X, abs=1.0)
        assert labelled.prior == pytest.approx(PRIOR_X, abs=1.0)
        assert _page_column_anchors(words) == labelled


# ---------------------------------------------------------------------------
# B. la sezione patrimoniale finisce dove comincia quella economica
# ---------------------------------------------------------------------------

def _long_statement_pdf(path):
    """Quattro pagine di SP senza alcun "Totale passivo" stampato, poi il CE."""
    doc = fitz.open()
    for index in range(5):
        page = doc.new_page()
        page.insert_text((20, 80), "Descrizione")
        _header(page)
        if index == 0:
            _row(page, 140, "STATO PATRIMONIALE ATTIVO",
                 "2.352.461,64", "2.170.417,20", "182.044,44", "8,38")
            _row(page, 160, "D) Ratei e risconti",
                 "216.226,30", "208.869,12", "7.357,18", "3,52")
        elif index == 1:
            _row(page, 140, "STATO PATRIMONIALE PASSIVO",
                 "2.352.461,64", "2.170.417,20", "182.044,44", "8,38")
            _row(page, 160, "D) Debiti",
                 "1.843.574,40", "1.791.522,27", "52.052,13", "2,90")
        elif index == 2:
            _row(page, 140, "D4A 202.01002 BANCO BPM C/C 14208",
                 "38.749,72", "89.030,08", "-50.280,36", "-56,47")
        elif index == 3:
            # coda del passivo E capo del conto economico sulla stessa pagina
            _row(page, 140, "E) Ratei e risconti",
                 "178.663,25", "20.812,17", "157.851,08", "758,45")
            _row(page, 170, "CONTO ECONOMICO")
            _row(page, 190, "A) Valore della produzione",
                 "2.112.107,99", "4.006.984,18", "-1.894.876,19", "-47,28")
        else:
            _row(page, 140, "21) Utile (perdita) dell'esercizio",
                 "27.887,32", "7.422,36", "20.464,96", "275,72")
        doc.save(path) if index == 4 else None
    doc.save(path, incremental=False)
    doc.close()


def test_lo_stato_patrimoniale_arriva_fino_alla_pagina_che_apre_il_ce(tmp_path):
    pdf_path = tmp_path / "prospetto-lungo.pdf"
    _long_statement_pdf(str(pdf_path))

    sp_pages, ce_pages = find_section_pages(str(pdf_path))

    # la pagina 4 (indice 3) porta la coda del passivo E l'apertura del CE:
    # sta in entrambe le sezioni. Il vecchio default (inizio + 2) la escludeva.
    assert 3 in sp_pages, "la coda del passivo deve raggiungere il prompt SP"
    assert 3 in ce_pages
    assert sp_pages == {0, 1, 2, 3}


def _long_note_pdf(path, note_pages=12):
    """SP senza «Totale passivo», poi una Nota Integrativa lunga, poi il CE.

    E' il deposito ordinario: l'SP chiude senza totale di sezione, seguono le
    note, e l'intestazione del conto economico arriva solo dopo. Le note portano
    il prospetto delle immobilizzazioni e la tabella dei debiti per scadenza —
    con numeri LORDI e in colonne diverse — cioe' proprio le tabelle che gli
    scanner geometrici che girano su ``sp_pages`` sono liberi di leggere.
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((20, 80), "Descrizione")
    _header(page)
    _row(page, 140, "STATO PATRIMONIALE ATTIVO",
         "2.352.461,64", "2.170.417,20", "182.044,44", "8,38")
    _row(page, 160, "D) Ratei e risconti",
         "216.226,30", "208.869,12", "7.357,18", "3,52")

    page = doc.new_page()
    _header(page)
    _row(page, 140, "STATO PATRIMONIALE PASSIVO",
         "2.352.461,64", "2.170.417,20", "182.044,44", "8,38")
    _row(page, 160, "D) Debiti",
         "1.843.574,40", "1.791.522,27", "52.052,13", "2,90")

    page = doc.new_page()
    _header(page)
    _row(page, 140, "E) Ratei e risconti",
         "178.663,25", "20.812,17", "157.851,08", "758,45")

    for index in range(note_pages):
        page = doc.new_page()
        _header(page)
        _row(page, 140, "NOTA INTEGRATIVA - Movimenti delle immobilizzazioni")
        _row(page, 160, "Costo storico immobilizzazioni materiali",
             "1.204.883,10", "1.150.112,44", "54.770,66", "4,76")
        _row(page, 180, "Fondo ammortamento",
             "1.114.066,51", "1.061.208,03", "52.858,48", "4,98")

    page = doc.new_page()
    _header(page)
    _row(page, 140, "CONTO ECONOMICO")
    _row(page, 160, "A) Valore della produzione",
         "2.112.107,99", "4.006.984,18", "-1.894.876,19", "-47,28")
    page = doc.new_page()
    _header(page)
    _row(page, 140, "21) Utile (perdita) dell'esercizio",
         "27.887,32", "7.422,36", "20.464,96", "275,72")
    doc.save(path)
    doc.close()


def test_la_nota_integrativa_non_finisce_nella_sezione_patrimoniale(tmp_path):
    """«L'SP finisce dove comincia il CE» regge solo se il CE comincia SUBITO dopo.

    Senza un tetto, `_find_start` scandisce fino in fondo al documento e
    `sp_pages` si mangia tutta la Nota Integrativa: il prompt SP si gonfia, e
    ogni scanner geometrico che gira su `sp_pages` puo' leggere il prospetto
    delle immobilizzazioni o la tabella dei debiti per scadenza stampati nelle
    note — numeri LORDI, in colonne diverse. Un dettaglio letto dalle note al
    posto del prospetto attraversa un aggregato, e il foglio quadra lo stesso.
    """
    pdf_path = tmp_path / "nota-lunga.pdf"
    _long_note_pdf(str(pdf_path))

    sp_pages, ce_pages = find_section_pages(str(pdf_path))

    assert 15 in ce_pages, "il CE comincia dove il documento lo intesta"
    assert max(sp_pages) <= 5, (
        "la sezione SP deve fermarsi al tetto, non alla pagina che apre il CE"
    )
    assert {0, 1, 2} <= sp_pages, "il passivo stampato deve restare dentro"


def test_i_ratei_passivi_stampati_si_rileggono_dalla_riga(tmp_path):
    pdf_path = tmp_path / "prospetto-lungo.pdf"
    _long_statement_pdf(str(pdf_path))

    recovered = _recover_printed_sp_rows(
        str(pdf_path),
        {"sp10_ratei_risconti_attivi": D("216226.30"),
         "sp18_ratei_risconti_passivi": D("0")},
    )

    assert recovered["sp18_ratei_risconti_passivi"] == D("178663.25")
    assert recovered["sp10_ratei_risconti_attivi"] == D("216226.30")


def test_la_congiunzione_di_ratei_E_risconti_non_e_il_codice_di_voce(tmp_path):
    """In "D) Ratei **e** risconti" la ``e`` supera un ``^E[.)]?$`` senza maiuscole.

    Senza questa distinzione la voce dell'ATTIVO si spaccia per la ``E)`` del
    passivo e sp18 riceve i ratei attivi: quadrerebbe pure, ed e' falso.
    """
    pdf_path = tmp_path / "solo-attivo.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((20, 80), "Descrizione")
    _header(page)
    _row(page, 140, "STATO PATRIMONIALE ATTIVO", "2.352.461,64", "2.170.417,20")
    _row(page, 160, "D) Ratei e risconti", "216.226,30", "208.869,12")
    doc.save(pdf_path)
    doc.close()

    recovered = _recover_printed_sp_rows(
        str(pdf_path), {"sp18_ratei_risconti_passivi": D("0")}
    )

    assert recovered["sp18_ratei_risconti_passivi"] == D("0")


def test_un_valore_gia_estratto_non_viene_sovrascritto(tmp_path):
    pdf_path = tmp_path / "prospetto-lungo.pdf"
    _long_statement_pdf(str(pdf_path))

    recovered = _recover_printed_sp_rows(
        str(pdf_path), {"sp18_ratei_risconti_passivi": D("12345.67")}
    )

    assert recovered["sp18_ratei_risconti_passivi"] == D("12345.67")


# ---------------------------------------------------------------------------
# D. la massa stampata e non classificata si dichiara
# ---------------------------------------------------------------------------

def _classified(**overrides):
    balance = {
        "sp01_crediti_soci": D("0"), "sp02_immob_immateriali": D("346304.85"),
        "sp03_immob_materiali": D("90816.59"), "sp04_immob_finanziarie": D("52550.00"),
        "sp05_rimanenze": D("0"), "sp06_crediti_breve": D("1646563.90"),
        "sp07_crediti_lungo": D("0"), "sp08_attivita_finanziarie": D("0"),
        "sp09_disponibilita_liquide": D("0"),
        "sp10_ratei_risconti_attivi": D("216226.30"),
        "sp11_capitale": D("110000"), "sp12_riserve": D("69484.43"),
        "sp13_utile_perdita": D("27887.32"), "sp14_fondi_rischi": D("0"),
        "sp15_tfr": D("122852.24"), "sp16_debiti_breve": D("1339542.14"),
        "sp17_debiti_lungo": D("504032.26"),
        "sp18_ratei_risconti_passivi": D("178663.25"),
    }
    balance.update(overrides)
    return balance


DECLARED = {"attivo": D("2352461.64"), "passivo": D("2352461.64")}


def test_la_massa_stampata_persa_e_dichiarata_non_zero():
    lost = _classified(sp18_ratei_risconti_passivi=D("0"))

    declared = declare_unclassified_mass(lost, DECLARED, "test")

    assert declared["_unclassified_mass"] == D("178663.25")
    assert declared["_unclassified_mass_measured"] == D("1")


def test_uno_scarto_di_debiti_non_classificato_finisce_nella_stessa_misura():
    """I 164,00 fra ``sp16+sp17`` e il ``D) Debiti`` stampato sono massa mancante."""
    short = _classified(sp16_debiti_breve=D("1339378.14"))

    declared = declare_unclassified_mass(short, DECLARED, "test")

    assert declared["_unclassified_mass"] == D("164.00")


def test_la_chiave_si_dichiara_anche_quando_vale_zero():
    declared = declare_unclassified_mass(_classified(), DECLARED, "test")

    assert declared["_unclassified_mass"] == D("0")
    assert declared["_unclassified_mass_measured"] == D("1")


def test_senza_totale_stampato_lo_zero_dice_non_lo_so_non_pulito():
    declared = declare_unclassified_mass(_classified(), None, "test")

    assert declared["_unclassified_mass"] == D("0")
    assert declared["_unclassified_mass_measured"] == D("0")


def test_uneccedenza_non_e_massa_mancante():
    """Classificare PIU' del totale stampato e' un doppio conteggio, non un buco."""
    doubled = _classified(sp18_ratei_risconti_passivi=D("357326.50"))

    declared = declare_unclassified_mass(doubled, DECLARED, "test")

    assert declared["_unclassified_mass"] == D("0")


def test_reconcile_ivcee_balance_dichiara_sempre_la_chiave():
    reconciled = reconcile_ivcee_balance(
        _classified(sp18_ratei_risconti_passivi=D("0")), DECLARED, "test"
    )

    assert reconciled["_unclassified_mass"] == D("178663.25")
    assert reconciled["_declared_liabilities_difference"] == D("-178663.25")
    # nessun valore contabile e' stato toccato
    assert reconciled["sp18_ratei_risconti_passivi"] == D("0")


# ---------------------------------------------------------------------------
# Il file reale (saltato quando non e' in locale)
# ---------------------------------------------------------------------------

AMB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "inbox", "Bilancio di verifica al 30.06.2026.pdf",
)
amb_only = pytest.mark.skipif(
    not os.path.exists(AMB), reason="PDF di prova (AMB AMBIENTA) non presente in locale"
)


@amb_only
def test_amb_le_tre_righe_a_corrente_vuoto_valgono_zero():
    current, _ = _reconcile_blank_current_ce_cells(
        AMB,
        {
            "ce01_ricavi_vendite": D("2104755.45"),
            "ce03_lavori_interni": D("90603.75"),
            "ce09d_svalutazione_crediti": D("2452.23"),
            "ce20_imposte": D("28773.00"),
        },
        {},
    )

    assert current["ce03_lavori_interni"] == D("0")
    assert current["ce09d_svalutazione_crediti"] == D("0")
    assert current["ce20_imposte"] == D("0")
    assert current["ce01_ricavi_vendite"] == D("2104755.45")


@amb_only
def test_amb_la_sezione_sp_raggiunge_i_ratei_passivi():
    sp_pages, ce_pages = find_section_pages(AMB)

    assert sorted(sp_pages) == [0, 1, 2, 3]
    assert 3 in ce_pages


@amb_only
def test_amb_i_ratei_passivi_arrivano_in_sp18():
    recovered = _recover_printed_sp_rows(
        AMB, {"sp18_ratei_risconti_passivi": D("0"),
              "sp10_ratei_risconti_attivi": D("216226.30")}
    )

    assert recovered["sp18_ratei_risconti_passivi"] == D("178663.25")
    assert recovered["sp10_ratei_risconti_attivi"] == D("216226.30")


def test_un_importo_troncato_ai_centesimi_e_ancora_lo_stesso_importo(tmp_path):
    """L'estrazione LLM non e' deterministica: a volte restituisce 90603 per 90.603,75.

    Il controllo di identita' fra il valore estratto e la cella del comparato non
    puo' essere al centesimo, o la riga resta sbagliata proprio nell'esecuzione in
    cui l'LLM ha perso i decimali (osservato sul file di prova, esecuzione 3 di 4).
    """
    pdf_path = tmp_path / "troncato.pdf"
    _comparative_ce_pdf(str(pdf_path))

    current, _ = _reconcile_blank_current_ce_cells(
        str(pdf_path),
        {"ce03_lavori_interni": D("90603"), "ce09d_svalutazione_crediti": D("2452")},
        {},
    )

    assert current["ce03_lavori_interni"] == D("0")
    assert current["ce09d_svalutazione_crediti"] == D("0")


def test_un_importo_diverso_non_viene_azzerato(tmp_path):
    """Il cinturino regge: un campo che non ha preso il comparato resta intatto."""
    pdf_path = tmp_path / "diverso.pdf"
    _comparative_ce_pdf(str(pdf_path))

    current, _ = _reconcile_blank_current_ce_cells(
        str(pdf_path), {"ce03_lavori_interni": D("12345.67")}, {},
    )

    assert current["ce03_lavori_interni"] == D("12345.67")


# ---------------------------------------------------------------------------
# E. il ripiego aggiunge massa MANCANTE, non massa mal classificata
# ---------------------------------------------------------------------------

def test_un_importo_gia_presente_altrove_nel_passivo_non_si_ripesca(tmp_path):
    """Se l'LLM l'ha letto e archiviato altrove, riscriverlo lo conta due volte.

    I 178.663,25 stampati alla ``E) Ratei e risconti`` del passivo possono essere
    finiti sotto `sp16g_altri_debiti_breve`: la massa e' gia' dentro
    l'estrazione. La guardia sul solo campo di destinazione non lo vede — sp18
    e' zero in entrambi i casi — e il passivo eccede l'attivo di quell'importo,
    senza che nessuna chiave nomini il doppio conteggio.
    """
    pdf_path = tmp_path / "prospetto-lungo.pdf"
    _long_statement_pdf(str(pdf_path))

    prima = {
        "sp16_debiti_breve": D("1843574.40"),
        "sp16g_altri_debiti_breve": D("178663.25"),
        "sp18_ratei_risconti_passivi": D("0"),
    }
    recovered = _recover_printed_sp_rows(str(pdf_path), prima)

    assert recovered["sp18_ratei_risconti_passivi"] == D("0")
    assert recovered == prima


def test_un_importo_presente_solo_nell_attivo_non_blocca_il_ripesco(tmp_path):
    """La guardia guarda il proprio LATO, non l'intero prospetto.

    Ratei attivi e ratei passivi di pari importo sono una coincidenza possibile,
    e non dicono nulla sulla classificazione del passivo: il ripiego — che e' il
    caso per cui la funzione esiste — deve scrivere lo stesso.
    """
    pdf_path = tmp_path / "prospetto-lungo.pdf"
    _long_statement_pdf(str(pdf_path))

    recovered = _recover_printed_sp_rows(
        str(pdf_path),
        {"sp10_ratei_risconti_attivi": D("178663.25"),
         "sp18_ratei_risconti_passivi": D("0")},
    )

    assert recovered["sp18_ratei_risconti_passivi"] == D("178663.25")


# ---------------------------------------------------------------------------
# F. il valore spostato nell'anno precedente porta la convenzione dei fratelli
# ---------------------------------------------------------------------------

def _comparative_ce_pdf_costi_fra_parentesi(path):
    """Lo stesso prospetto, ma con la convenzione «i costi sono negativi»."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((90, 60), "BILANCIO RICLASSIFICATO UE dal 01/01/2026 al 30/06/2026")
    page.insert_text((20, 80), "Descrizione")
    _header(page)
    _row(page, 140, "CONTO ECONOMICO")
    _row(page, 160, "1) Ricavi delle vendite e delle prestazioni",
         "2.104.755,45", "3.761.087,73", "-1.656.332,28", "-44,03")
    # corrente VUOTO, e il comparato stampa il costo fra parentesi
    _row(page, 180, "17) Interessi e altri oneri finanziari",
         None, "(12.500,00)", "12.500,00", "-100,00")
    _row(page, 200, "20) Imposte sul reddito dell'esercizio",
         None, "(28.773,00)", "28.773,00", "-100,00")
    doc.save(path)
    doc.close()


def test_il_valore_spostato_nel_precedente_porta_il_segno_dei_fratelli(tmp_path):
    """`_normalize_ce_signs` gira PRIMA, e questo valore non ci passa mai.

    Il token grezzo di un costo stampato fra parentesi vale -12.500: scritto
    tale e quale in `prior_ce`, si trova accanto a fratelli che la
    normalizzazione ha portato tutti a positivo, e il risultato dell'anno
    precedente si sposta di 2x l'importo senza che nulla lo segnali.

    Il valore giusto e' quello che il campo ha GIA' nell'anno corrente — dove
    l'estrattore l'aveva messo per sbaglio, e dove la normalizzazione l'ha
    trattato come i suoi fratelli — con la precisione della cella stampata.
    """
    pdf_path = tmp_path / "parentesi.pdf"
    _comparative_ce_pdf_costi_fra_parentesi(str(pdf_path))

    # Come arrivano qui: gia' normalizzati, cioe' con i costi a positivo.
    current, prior = _reconcile_blank_current_ce_cells(
        str(pdf_path),
        {"ce01_ricavi_vendite": D("2104755.45"),
         "ce15_oneri_finanziari": D("12500.00"),
         "ce20_imposte": D("28773.00")},
        {"ce01_ricavi_vendite": D("3761087.73"),
         "ce15_oneri_finanziari": D("0"),
         "ce20_imposte": D("0")},
    )

    assert current["ce15_oneri_finanziari"] == D("0")
    assert current["ce20_imposte"] == D("0")
    assert prior["ce15_oneri_finanziari"] == D("12500.00")
    assert prior["ce20_imposte"] == D("28773.00")


def test_un_campo_a_convenzione_positiva_non_cambia(tmp_path):
    """Su un PDF che non usa le parentesi nulla si muove."""
    pdf_path = tmp_path / "positivo.pdf"
    _comparative_ce_pdf(str(pdf_path))

    _, prior = _reconcile_blank_current_ce_cells(
        str(pdf_path),
        {"ce03_lavori_interni": D("90603.75"), "ce20_imposte": D("28773.00")},
        {"ce03_lavori_interni": D("0"), "ce20_imposte": D("0")},
    )

    assert prior["ce03_lavori_interni"] == D("90603.75")
    assert prior["ce20_imposte"] == D("28773.00")


def test_anche_lo_sp_scrive_nel_precedente_il_segno_che_ha_nel_corrente(tmp_path):
    """Il terzo punto di scrittura e' quello dello SP, e segue la stessa regola.

    La cella comparata stampata fra parentesi non e' un'autorita' sul segno piu'
    di quanto lo sia nel CE: la grandezza e' la stessa che l'estrattore ha gia'
    attribuito all'anno corrente (e' la condizione che il ripesco verifica prima
    di agire), quindi il segno da usare e' quello. Scriverne uno diverso nella
    stessa voce, fra le due colonne, e' incoerente comunque la si giri — e su
    ``B) Fondi per rischi e oneri`` un valore negativo non esiste nell'art. 2424.
    """
    pdf_path = tmp_path / "sp-parentesi.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((20, 80), "Descrizione")
    _header(page)
    _row(page, 140, "STATO PATRIMONIALE PASSIVO", "2.352.461,64", "2.170.417,20")
    _row(page, 160, "B) Fondi per rischi e oneri",
         None, "(45.000,00)", "45.000,00", "-100,00")
    doc.save(pdf_path)
    doc.close()

    current, prior = _reconcile_blank_current_sp_cells(
        str(pdf_path),
        {"sp14_fondi_rischi": D("45000.00")},
        {"sp14_fondi_rischi": D("0")},
    )

    assert current["sp14_fondi_rischi"] == D("0")
    assert prior["sp14_fondi_rischi"] == D("45000.00")
