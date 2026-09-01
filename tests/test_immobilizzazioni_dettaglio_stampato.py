"""I sotto-campi di immobilizzazioni e rimanenze si leggono dove sono stampati.

Sul layout «BILANCIO RICLASSIFICATO UE» l'estrattore LLM di route B restituiva
gli aggregati `sp02`, `sp03`, `sp04`, `sp05` e lasciava a ZERO tutti i loro
sotto-campi. Il documento invece li stampa, con il proprio tag IV-CEE su ogni
conto e con il netting gia' calcolato riga per riga.

Non e' un di piu': `_forecastable` richiede `semantic_valid`, che richiede
`hierarchy_consistent` — la somma dei sotto-campi deve corrispondere al proprio
aggregato. Con i sotto-campi a zero il controllo falliva anche nelle esecuzioni
PULITE (sbilancio 0,00, `utile_ce == sp13`), e `forecastable: false`
sopravviveva.

La riga di voce di legge e' gia' NETTA: `4) Concessioni…` vale 48.618,07, cioe'
61.605,00 di costo storico meno 12.986,93 di fondo. Si leggono quelle righe, e
NON i conti sottostanti: si sommano i mastri oppure le foglie, mai entrambi.
"""
import os
from decimal import Decimal

import fitz
import pytest

from importers.pdf_extractor_llm import _recover_printed_fixed_asset_details


D = Decimal

CURRENT_X, PRIOR_X, DEVIATION_X, PERCENT_X = 424.0, 489.0, 543.0, 575.0
FONT, SIZE = "helv", 9


def _right(page, x_right, y, text):
    width = fitz.get_text_length(text, fontname=FONT, fontsize=SIZE)
    page.insert_text((x_right - width, y), text, fontname=FONT, fontsize=SIZE)


def _row(page, y, label, current=None, prior=None):
    page.insert_text((20, y), label, fontname=FONT, fontsize=SIZE)
    for value, x in ((current, CURRENT_X), (prior, PRIOR_X)):
        if value is not None:
            _right(page, x, y, value)


def _attivo_pdf(path, righe):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((90, 60), "BILANCIO RICLASSIFICATO UE dal 01/01/2026 al 30/06/2026")
    page.insert_text((20, 80), "Descrizione")
    _right(page, CURRENT_X, 100, "corrente")
    _right(page, PRIOR_X, 100, "comparato")
    _right(page, DEVIATION_X, 100, "Scostamento")
    _right(page, PERCENT_X, 100, "%")
    _row(page, 120, "STATO PATRIMONIALE ATTIVO", "1.500,00", "1.500,00")
    y = 140
    for label, current in righe:
        _row(page, y, label, current, current)
        y += 18
    doc.save(path)
    doc.close()


def _zero_bs():
    """Lo SP come lo restituisce l'LLM di route B: aggregati sì, dettagli a zero."""
    return {
        "sp02_immob_immateriali": D("1000.00"),
        "sp03_immob_materiali": D("500.00"),
        "sp02a_costi_impianto": D("0"),
        "sp02d_concessioni": D("0"),
        "sp03b_impianti_macchinari": D("0"),
    }


def test_le_righe_di_voce_di_legge_popolano_i_sotto_campi(tmp_path):
    pdf = tmp_path / "immob.pdf"
    _attivo_pdf(str(pdf), [
        ("B) Immobilizzazioni", "1.500,00"),
        ("I. Immobilizzazioni Immateriali", "1.000,00"),
        ("1) Costi di impianto e di ampliamento", "600,00"),
        ("Costo storico", "800,00"),
        ("BI1 106.01000 COSTI MIGLIORIE BENI TERZI", "800,00"),
        ("Fondo ammortamento", "-200,00"),
        ("BI1A 112.01000 F.AMM. MIGLIORIE BENI TERZI", "-200,00"),
        ("4) Concessioni, licenze, marchi e diritti simili", "400,00"),
        ("II. Immobilizzazioni Materiali", "500,00"),
        ("2) Impianti e macchinario", "500,00"),
        ("C) Attivo circolante", "0,00"),
    ])

    bs = _recover_printed_fixed_asset_details(str(pdf), _zero_bs())

    assert bs["sp02a_costi_impianto"] == D("600.00")
    assert bs["sp02d_concessioni"] == D("400.00")
    assert bs["sp03b_impianti_macchinari"] == D("500.00")
    # Il valore preso e' quello NETTO della riga di voce, senza doppi conteggi:
    # «Costo storico» 800 e il conto BI1 800 sono la stessa massa vista due
    # volte, e nessuno dei due entra.
    assert bs["sp02_immob_immateriali"] == D("1000.00")
    assert (
        bs["sp02a_costi_impianto"] + bs["sp02d_concessioni"]
        == bs["sp02_immob_immateriali"]
    )


def test_senza_cross_foot_col_totale_di_voce_non_si_tocca_nulla(tmp_path):
    """Il totale stampato della voce e' l'unico controllo di questa lettura.

    Se i sotto-campi letti non sommano al totale che il documento stampa per
    quella voce, qualcosa non e' stato letto: scrivere lo stesso significherebbe
    ridistribuire un aggregato, e sp02/sp03/sp04 sono `TIER0_FIELDS` — mai una
    destinazione di ripiego.
    """
    pdf = tmp_path / "monco.pdf"
    _attivo_pdf(str(pdf), [
        ("I. Immobilizzazioni Immateriali", "1.000,00"),
        ("1) Costi di impianto e di ampliamento", "600,00"),
        # manca la 4): 600 != 1.000
        ("II. Immobilizzazioni Materiali", "500,00"),
    ])

    prima = _zero_bs()
    assert _recover_printed_fixed_asset_details(str(pdf), prima) == prima


def test_un_dettaglio_gia_estratto_non_viene_sovrascritto(tmp_path):
    """Si tocca solo cio' che l'estrazione dichiara a zero.

    Un importo gia' estratto, anche diverso, resta com'e': il divario lo
    dichiara `_unclassified_mass`, non lo corregge questa funzione.
    """
    pdf = tmp_path / "gia_estratto.pdf"
    _attivo_pdf(str(pdf), [
        ("I. Immobilizzazioni Immateriali", "1.000,00"),
        ("1) Costi di impianto e di ampliamento", "600,00"),
        ("4) Concessioni, licenze, marchi e diritti simili", "400,00"),
    ])

    prima = _zero_bs()
    prima["sp02a_costi_impianto"] = D("123.45")
    bs = _recover_printed_fixed_asset_details(str(pdf), prima)

    assert bs["sp02a_costi_impianto"] == D("123.45")
    assert bs["sp02d_concessioni"] == D("0")


def test_le_rimanenze_non_si_confondono_con_le_immateriali(tmp_path):
    """«I. Rimanenze» e «I. Immobilizzazioni Immateriali» portano lo STESSO codice.

    A distinguerle e' l'etichetta, mai il solo numero romano — e «materiali» e'
    una sottostringa di «immateriali», quindi nemmeno la sola parola basta.
    """
    pdf = tmp_path / "rimanenze.pdf"
    _attivo_pdf(str(pdf), [
        ("I. Immobilizzazioni Immateriali", "1.000,00"),
        ("1) Costi di impianto e di ampliamento", "1.000,00"),
        ("C) Attivo circolante", "300,00"),
        ("I. Rimanenze", "300,00"),
        ("1) Materie prime, sussidiarie e di consumo", "300,00"),
    ])

    bs = _recover_printed_fixed_asset_details(
        str(pdf), {**_zero_bs(), "sp05_rimanenze": D("300.00"), "sp05a_materie_prime": D("0")}
    )

    assert bs["sp02a_costi_impianto"] == D("1000.00")
    assert bs["sp05a_materie_prime"] == D("300.00")


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
def test_amb_i_sotto_campi_sono_quelli_stampati_e_sommano_al_proprio_aggregato():
    bs = _recover_printed_fixed_asset_details(AMB, {
        "sp02_immob_immateriali": D("346304.85"),
        "sp03_immob_materiali": D("90816.59"),
        "sp04_immob_finanziarie": D("52550.00"),
        "sp05_rimanenze": D("287526.55"),
    })

    # B.I — le quattro voci stampate, gia' nette del proprio fondo
    assert bs["sp02a_costi_impianto"] == D("118720.39")
    assert bs["sp02d_concessioni"] == D("48618.07")
    assert bs["sp02e_avviamento"] == D("88362.64")
    assert bs["sp02f_immob_in_corso"] == D("90603.75")
    # B.II
    assert bs["sp03b_impianti_macchinari"] == D("30133.06")
    assert bs["sp03c_attrezzature"] == D("38323.68")
    assert bs["sp03d_altri_beni"] == D("22359.85")
    # B.III e C.I
    assert bs["sp04d_altri_titoli"] == D("52550.00")
    assert bs["sp05a_materie_prime"] == D("287526.55")

    # `hierarchy_consistent`: ogni aggregato e' la somma dei propri dettagli.
    for aggregato, dettagli in (
        ("sp02_immob_immateriali", ("sp02a_costi_impianto", "sp02b_costi_sviluppo",
                                    "sp02c_brevetti", "sp02d_concessioni",
                                    "sp02e_avviamento", "sp02f_immob_in_corso",
                                    "sp02g_altre_immob_imm")),
        ("sp03_immob_materiali", ("sp03a_terreni_fabbricati", "sp03b_impianti_macchinari",
                                  "sp03c_attrezzature", "sp03d_altri_beni",
                                  "sp03e_immob_in_corso")),
        ("sp05_rimanenze", ("sp05a_materie_prime", "sp05b_prodotti_in_corso",
                            "sp05c_lavori_in_corso", "sp05d_prodotti_finiti",
                            "sp05e_acconti")),
    ):
        somma = sum((bs.get(f, D("0")) for f in dettagli), D("0"))
        assert somma == bs[aggregato], aggregato


def test_un_fratello_gia_estratto_e_non_stampato_blocca_la_sezione(tmp_path):
    """La guardia deve vedere TUTTI i fratelli dell'aggregato, non i soli stampati.

    Se l'estrazione ha gia' messo un importo in un sotto-campo che il documento
    non stampa, scrivere le voci stampate e poi fissare l'aggregato al totale di
    voce lascia i dettagli a sommare piu' dell'aggregato: `hierarchy_consistent`
    fallisce — cioe' esattamente la condizione che questa funzione ripara — e
    `reconcileSubfields` lato client conta due volte quella massa dentro il
    secchio «altri».
    """
    pdf = tmp_path / "fratello.pdf"
    _attivo_pdf(str(pdf), [
        ("I. Immobilizzazioni Immateriali", "1.000,00"),
        ("1) Costi di impianto e di ampliamento", "600,00"),
        ("4) Concessioni, licenze, marchi e diritti simili", "400,00"),
    ])

    prima = _zero_bs()
    # `sp02g` non compare fra le righe stampate, ma l'estrazione ce l'ha messo.
    prima["sp02g_altre_immob_imm"] = D("5000.00")
    assert _recover_printed_fixed_asset_details(str(pdf), prima) == prima


def test_un_credito_immobilizzato_gia_estratto_blocca_la_sezione(tmp_path):
    """`sp04b_crediti_immob_breve` esiste ed e' un fratello di sp04.

    La voce di legge B.III.2 «Crediti» si spacchetta in entro/oltre, e questa
    lettura porta l'importo all'oltre; ma il campo ENTRO resta un fratello
    dell'aggregato, e la guardia deve guardarlo.
    """
    pdf = tmp_path / "sp04.pdf"
    _attivo_pdf(str(pdf), [
        ("III. Immobilizzazioni Finanziarie", "1.000,00"),
        ("1) Partecipazioni", "400,00"),
        ("3) Altri titoli", "600,00"),
    ])

    prima = {"sp04_immob_finanziarie": D("1000.00"),
             "sp04b_crediti_immob_breve": D("5000.00")}
    assert _recover_printed_fixed_asset_details(str(pdf), prima) == prima
