"""La ripartizione entro/oltre del D) Debiti si legge dove il documento la stampa.

Dopo #18 il TOTALE dei debiti quadrava — `sp16 + sp17` = 1.843.574,40, cioe' il
`D) Debiti` stampato — ma la RIPARTIZIONE no: l'LLM spostava 230.402,34 dal
breve al lungo. Nessun cancello lo vede, perche' `sp16` e `sp17` stanno
entrambi nel passivo e il pareggio non si muove; lo vedono CCN, current ratio e
il circolante di Altman, e spostare debito dal breve al lungo fa risultare gli
indici di liquidita' MIGLIORI del vero.

Il blocco pero' si auto-valida: le righe `- entro` / `- oltre` che il documento
stampa cross-footano al `D) Debiti` stampato. Una lettura deterministica ha
quindi il proprio totale di controllo e non ha bisogno di fidarsi dell'LLM. E'
un ripiego lecito, non un tappo: la massa e' stampata e leggibile nella propria
riga.
"""
import os
from decimal import Decimal

import fitz
import pytest

from importers.pdf_extractor_llm import _split_printed_debt_maturities


D = Decimal

CURRENT_X, PRIOR_X, DEVIATION_X, PERCENT_X = 424.0, 489.0, 543.0, 575.0
FONT, SIZE = "helv", 9


def _right(page, x_right, y, text):
    width = fitz.get_text_length(text, fontname=FONT, fontsize=SIZE)
    page.insert_text((x_right - width, y), text, fontname=FONT, fontsize=SIZE)


def _row(page, y, label, current=None, prior=None, deviation=None, percent=None):
    page.insert_text((20, y), label, fontname=FONT, fontsize=SIZE)
    for value, x in (
        (current, CURRENT_X), (prior, PRIOR_X),
        (deviation, DEVIATION_X), (percent, PERCENT_X),
    ):
        if value is not None:
            _right(page, x, y, value)


def _passivo_pdf(path, righe):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((90, 60), "BILANCIO RICLASSIFICATO UE dal 01/01/2026 al 30/06/2026")
    page.insert_text((20, 80), "Descrizione")
    _right(page, CURRENT_X, 100, "corrente")
    _right(page, PRIOR_X, 100, "comparato")
    _right(page, DEVIATION_X, 100, "Scostamento")
    _right(page, PERCENT_X, 100, "%")
    _row(page, 120, "STATO PATRIMONIALE PASSIVO", "1.000,00", "1.000,00")
    y = 140
    for label, current in righe:
        _row(page, y, label, current, current)
        y += 20
    _row(page, y, "E) Ratei e risconti", "0,00", "0,00")
    doc.save(path)
    doc.close()


def _bs_sbagliato():
    """Lo SP come lo restituisce l'LLM: totale giusto, ripartizione sbagliata."""
    return {
        "sp16_debiti_breve": D("500.00"),
        "sp16a_debiti_banche_breve": D("500.00"),
        "sp17_debiti_lungo": D("500.00"),
        "sp17a_debiti_banche_lungo": D("500.00"),
    }


def test_la_ripartizione_letta_e_quella_stampata(tmp_path):
    pdf = tmp_path / "debiti.pdf"
    _passivo_pdf(str(pdf), [
        ("D) Debiti", "1.000,00"),
        ("4) Debiti verso banche", "800,00"),
        ("- entro l'esercizio successivo", "600,00"),
        ("- oltre l'esercizio successivo", "200,00"),
        ("7) Debiti verso fornitori", "200,00"),
        ("- entro l'esercizio successivo", "200,00"),
    ])

    bs = _split_printed_debt_maturities(str(pdf), _bs_sbagliato())

    assert bs["sp16_debiti_breve"] == D("800.00")
    assert bs["sp17_debiti_lungo"] == D("200.00")
    # Gli importi finiscono nei sotto-campi TIPIZZATI: un residuo lasciato
    # sull'aggregato diventa debito bancario fantasma
    # (`projection_common.base_bank_debt` assegna alle BANCHE qualunque scarto
    # fra sp16/sp17 e la somma dei loro dettagli, con tanto di piano di
    # rimborso).
    assert bs["sp16a_debiti_banche_breve"] == D("600.00")
    assert bs["sp17a_debiti_banche_lungo"] == D("200.00")
    assert bs["sp16d_debiti_fornitori_breve"] == D("200.00")
    assert bs["sp17d_debiti_fornitori_lungo"] == D("0")
    # e sommano al proprio aggregato
    dettagli_breve = sum(
        (bs[k] for k in bs if k.startswith("sp16") and k != "sp16_debiti_breve"), D("0")
    )
    assert dettagli_breve == bs["sp16_debiti_breve"]


def test_una_voce_non_tipizzata_va_nel_secchio_generico_non_sull_aggregato(tmp_path):
    # 6) Acconti non ha un sotto-campo proprio: la massa non riconosciuta va in
    # `sp16g` / `sp17g`, mai su un aggregato.
    pdf = tmp_path / "acconti.pdf"
    _passivo_pdf(str(pdf), [
        ("D) Debiti", "1.000,00"),
        ("6) Acconti", "1.000,00"),
        ("- entro l'esercizio successivo", "1.000,00"),
    ])

    bs = _split_printed_debt_maturities(str(pdf), _bs_sbagliato())

    assert bs["sp16_debiti_breve"] == D("1000.00")
    assert bs["sp16g_altri_debiti_breve"] == D("1000.00")
    assert bs["sp16a_debiti_banche_breve"] == D("0")


def test_senza_cross_foot_non_si_tocca_nulla(tmp_path):
    """Il totale di controllo e' l'unica ragione per fidarsi di questa lettura.

    Se le righe di scadenza non sommano al `D) Debiti` stampato, qualcosa non e'
    stato letto: sovrascrivere sarebbe inventare una ripartizione, non leggerla.
    """
    pdf = tmp_path / "monco.pdf"
    _passivo_pdf(str(pdf), [
        ("D) Debiti", "1.000,00"),
        ("4) Debiti verso banche", "800,00"),
        ("- entro l'esercizio successivo", "600,00"),
        # manca la riga `- oltre`: 600 != 1.000
        ("7) Debiti verso fornitori", "200,00"),
    ])

    prima = _bs_sbagliato()
    assert _split_printed_debt_maturities(str(pdf), prima) == prima


def test_senza_righe_di_scadenza_il_comportamento_non_cambia(tmp_path):
    """Resta la regola prudenziale: debito senza scadenza dichiarata va a breve.

    Anticipare una scadenza PEGGIORA gli indici di liquidita', non li abbellisce,
    e l'utente lo sposta in Rettifiche.
    """
    pdf = tmp_path / "senza_scadenze.pdf"
    _passivo_pdf(str(pdf), [
        ("D) Debiti", "1.000,00"),
        ("4) Debiti verso banche", "800,00"),
        ("7) Debiti verso fornitori", "200,00"),
    ])

    prima = _bs_sbagliato()
    assert _split_printed_debt_maturities(str(pdf), prima) == prima


def test_le_scadenze_dei_crediti_non_finiscono_nei_debiti(tmp_path):
    """L'attivo circolante stampa le proprie righe `- entro` / `- oltre`.

    La scansione parte dalla riga `D) Debiti` e si chiude sulla lettera di voce
    successiva: le scadenze dei CREDITI stanno prima, e non devono entrare.
    """
    pdf = tmp_path / "crediti_e_debiti.pdf"
    _passivo_pdf(str(pdf), [
        ("II. Crediti", "9.999,00"),
        ("1) verso clienti", "9.999,00"),
        ("- entro esercizio successivo", "9.999,00"),
        ("D) Debiti", "1.000,00"),
        ("4) Debiti verso banche", "1.000,00"),
        ("- entro l'esercizio successivo", "1.000,00"),
    ])

    bs = _split_printed_debt_maturities(str(pdf), _bs_sbagliato())

    assert bs["sp16_debiti_breve"] == D("1000.00")
    assert bs["sp16a_debiti_banche_breve"] == D("1000.00")


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
def test_amb_la_ripartizione_e_quella_stampata_nel_documento():
    bs = _split_printed_debt_maturities(AMB, {
        "sp16_debiti_breve": D("1109139.80"),
        "sp16a_debiti_banche_breve": D("1109139.80"),
        "sp17_debiti_lungo": D("734434.60"),
        "sp17a_debiti_banche_lungo": D("734434.60"),
    })

    assert bs["sp16_debiti_breve"] == D("1339542.14")
    assert bs["sp17_debiti_lungo"] == D("504032.26")
    assert bs["sp16_debiti_breve"] + bs["sp17_debiti_lungo"] == D("1843574.40")


@amb_only
def test_amb_ogni_importo_finisce_nel_proprio_sotto_campo_tipizzato():
    bs = _split_printed_debt_maturities(AMB, {
        "sp16_debiti_breve": D("1109139.80"),
        "sp17_debiti_lungo": D("734434.60"),
    })

    assert bs["sp16a_debiti_banche_breve"] == D("353408.65")
    assert bs["sp17a_debiti_banche_lungo"] == D("467528.52")
    assert bs["sp17b_debiti_altri_finanz_lungo"] == D("36503.74")
    assert bs["sp16d_debiti_fornitori_breve"] == D("652885.44")
    assert bs["sp16e_debiti_tributari_breve"] == D("11179.12")
    assert bs["sp16f_debiti_previdenza_breve"] == D("94631.39")
    # 6) Acconti (1.794,50) e 14) Altri debiti (225.643,04) non hanno un
    # sotto-campo proprio: vanno nel secchio generico, mai sull'aggregato.
    assert bs["sp16g_altri_debiti_breve"] == D("227437.54")
    for aggregato, prefisso in (("sp16_debiti_breve", "sp16"), ("sp17_debiti_lungo", "sp17")):
        dettagli = sum(
            (v for k, v in bs.items() if k.startswith(prefisso) and k != aggregato), D("0")
        )
        assert dettagli == bs[aggregato], aggregato


def test_una_scadenza_indicata_con_una_lettera_non_chiude_la_sezione(tmp_path):
    """Alcuni layout letterano lo spacchettamento: `a) esigibili entro…`.

    La lettera di voce e' il confine della sezione, ma solo quando e' MAIUSCOLA:
    una `a)` minuscola dentro il D) e' una riga di scadenza, non la voce
    successiva. Confonderle interrompeva la scansione alla prima, il cross-foot
    falliva, e la ripartizione stampata — quella che questa funzione esiste per
    leggere — veniva saltata su tutta quella famiglia di documenti.
    """
    pdf = tmp_path / "lettere.pdf"
    _passivo_pdf(str(pdf), [
        ("D) Debiti", "1.000,00"),
        ("4) Debiti verso banche", "1.000,00"),
        ("a) esigibili entro l'esercizio successivo", "600,00"),
        ("b) esigibili oltre l'esercizio successivo", "400,00"),
    ])

    bs = _split_printed_debt_maturities(str(pdf), _bs_sbagliato())

    assert bs["sp16a_debiti_banche_breve"] == D("600.00")
    assert bs["sp17a_debiti_banche_lungo"] == D("400.00")
    assert bs["sp16_debiti_breve"] == D("600.00")
    assert bs["sp17_debiti_lungo"] == D("400.00")
