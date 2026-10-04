"""#60: il comparato del prospetto «corrente | comparato | Scostamento | %» si legge.

La #27 non lo leggeva mai: senza confine, la seconda colonna riceveva lo
scostamento, che e' lineare e passa ogni controllo incrociato. Qui il
comparato vale il doppio del corrente, quindi lo scostamento e' il corrente
cambiato di segno: un precedente letto dallo scostamento sarebbe negativo, e
i test lo vedrebbero.
"""
from decimal import Decimal
from pathlib import Path

import fitz

from importers.standard_ivcee_parser import (
    extract_standard_ivcee_balances,
    extract_standard_ivcee_income,
)

_FONT, _SIZE = "helv", 9
_COLONNE = (424.0, 489.0, 543.0, 575.0)

_SP = [
    ("Stato patrimoniale attivo", "1.050,00"),
    ("B) Immobilizzazioni", "300,00"),
    ("I. Immobilizzazioni Immateriali", "100,00"),
    ("II. Immobilizzazioni Materiali", "150,00"),
    ("III. Immobilizzazioni Finanziarie", "50,00"),
    ("C) Attivo circolante", "700,00"),
    ("I. Rimanenze", "200,00"),
    ("II. Crediti", "400,00"),
    ("1) verso clienti", "400,00"),
    ("- entro esercizio successivo", "400,00"),
    ("IV. Disponibilita' liquide", "100,00"),
    ("D) Ratei e risconti", "50,00"),
    ("Stato patrimoniale passivo", "1.050,00"),
    ("A) Patrimonio netto", "400,00"),
    ("I) Capitale", "300,00"),
    ("IX. Utile (perdita) dell'esercizio", "100,00"),
    ("C) Trattamento di fine rapporto di lavoro subordinato", "50,00"),
    ("D) Debiti", "550,00"),
    ("4) Debiti verso banche", "550,00"),
    ("- entro l'esercizio successivo", "550,00"),
    ("E) Ratei e risconti", "50,00"),
]
_CE = [
    ("Conto economico", None),
    ("A) Valore della produzione", "500,00"),
    ("1) Ricavi delle vendite e delle prestazioni", "450,00"),
    ("5) Altri ricavi e proventi:", "50,00"),
    ("B) Costi della produzione", "300,00"),
    ("6) per materie prime, sussidiarie, di consumo e di merci", "100,00"),
    ("7) per servizi", "50,00"),
    ("8) per godimento di beni di terzi", "20,00"),
    ("9) per il personale", "80,00"),
    ("10) Ammortamenti e svalutazioni", "30,00"),
    ("11) Variazioni delle rimanenze di materie prime, sussidiarie, di consumo e m", "20,00"),
    ("14) Oneri diversi di gestione", "0,00"),
    ("Differenza tra Valore e Costo della Produzione", "200,00"),
    ("C) Proventi e oneri finanziari", "-20,00"),
    ("16) Altri proventi finanziari", "5,00"),
    ("17) Interessi e altri oneri finanziari", "25,00"),
    ("Risultato prima delle imposte", "180,00"),
    ("20) Imposte sul reddito dell'esercizio", "80,00"),
    ("21) Utile (Perdita) dell'esercizio", "100,00"),
]


def _euro(value: Decimal) -> str:
    testo = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if value < 0 else "") + testo


def _celle(corrente: str, *, analisi: bool):
    cur = Decimal(corrente.replace(".", "").replace(",", "."))
    prec = cur * 2
    celle = [corrente, _euro(prec)]
    if analisi:
        celle += [_euro(cur - prec), "-50,00" if cur else "0,00"]
    return celle


def _scrivi(path: Path, *, intestazioni) -> None:
    analisi = len(intestazioni) == 4

    def destra(page, x, y, text):
        larghezza = fitz.get_text_length(text, fontname=_FONT, fontsize=_SIZE)
        page.insert_text((x - larghezza, y), text, fontname=_FONT, fontsize=_SIZE)

    document = fitz.open()
    for righe, titolo in ((_SP, "BILANCIO RICLASSIFICATO UE dal 01/01/2026 al 30/06/2026"), (_CE, None)):
        page = document.new_page()
        if titolo:
            page.insert_text((30, 40), titolo, fontsize=11)
        page.insert_text((20, 60), "Descrizione", fontsize=_SIZE)
        for x, testo in zip(_COLONNE, intestazioni):
            destra(page, x, 75, testo)
        y = 100
        for etichetta, corrente in righe:
            page.insert_text((20, y), etichetta, fontname=_FONT, fontsize=_SIZE)
            if corrente is not None:
                for x, cella in zip(_COLONNE, _celle(corrente, analisi=analisi)):
                    destra(page, x, y, cella)
            y += 20
    document.save(str(path))
    document.close()


def test_il_comparato_si_legge_e_non_e_lo_scostamento(tmp_path):
    pdf = tmp_path / "quattro-colonne.pdf"
    _scrivi(pdf, intestazioni=("corrente", "comparato", "Scostamento", "%"))

    current, prior = extract_standard_ivcee_balances(str(pdf))
    current_ce, prior_ce = extract_standard_ivcee_income(str(pdf))

    assert current["totale_attivo"] == Decimal("1050.00")
    assert current["sp13_utile_perdita"] == Decimal("100.00")
    assert prior is not None and prior_ce is not None
    assert prior["totale_attivo"] == Decimal("2100.00")
    assert prior["totale_passivo"] == Decimal("2100.00")
    assert prior["sp05_rimanenze"] == Decimal("400.00")
    assert prior["sp13_utile_perdita"] == Decimal("200.00")
    assert current_ce["ce01_ricavi_vendite"] == Decimal("450.00")
    assert prior_ce["ce01_ricavi_vendite"] == Decimal("900.00")
    assert prior_ce["ce20_imposte"] == Decimal("160.00")


def test_due_sole_colonne_intestate_leggono_il_comparato(tmp_path):
    pdf = tmp_path / "due-colonne.pdf"
    _scrivi(pdf, intestazioni=("corrente", "comparato"))

    _, prior = extract_standard_ivcee_balances(str(pdf))
    _, prior_ce = extract_standard_ivcee_income(str(pdf))

    assert prior is not None and prior["totale_attivo"] == Decimal("2100.00")
    assert prior_ce is not None and prior_ce["ce01_ricavi_vendite"] == Decimal("900.00")


def test_una_terza_colonna_senza_intestazione_di_analisi_lascia_il_comparato_non_letto(tmp_path):
    """Mai indovinare: importi stabili oltre il comparato che nessuna intestazione
    identifica come scostamento lasciano l'anno precedente non letto, come prima."""
    pdf = tmp_path / "terza-anonima.pdf"
    _scrivi(pdf, intestazioni=("corrente", "comparato", "Colonna", "Altro"))

    current, prior = extract_standard_ivcee_balances(str(pdf))
    current_ce, prior_ce = extract_standard_ivcee_income(str(pdf))

    assert current is not None and current["totale_attivo"] == Decimal("1050.00")
    assert current_ce is not None
    assert prior is None and prior_ce is None


def test_il_percorso_snello_porta_il_comparato_letto(tmp_path):
    from importers.import_snello.deterministico import tentativo

    pdf = tmp_path / "quattro-colonne.pdf"
    _scrivi(pdf, intestazioni=("corrente", "comparato", "Scostamento", "%"))

    esito = tentativo(str(pdf))

    assert esito["adottato"] and esito["parser"] == "standard_ivcee_parser"
    assert esito["prior_stato"] == "letto"
    assert esito["prior_bs"]["sp05_rimanenze"] == Decimal("400.00")
    assert esito["prior_ce"]["ce01_ricavi_vendite"] == Decimal("900.00")


def test_il_percorso_snello_dichiara_il_comparato_assente(tmp_path):
    from importers.import_snello.deterministico import tentativo

    pdf = tmp_path / "terza-anonima.pdf"
    _scrivi(pdf, intestazioni=("corrente", "comparato", "Colonna", "Altro"))

    esito = tentativo(str(pdf))

    assert esito["adottato"]
    assert esito["prior_stato"] == "assente"
    assert "prior_bs" not in esito


def test_un_precedente_che_non_chiude_da_solo_si_scarta_col_motivo():
    from importers.import_snello.deterministico import _con_precedente

    esito = {"adottato": True}
    _con_precedente(esito, {"sp01_crediti_soci": Decimal("1")}, {})

    assert esito["prior_stato"] == "scartato"
    assert esito["prior_rifiuto"]["controllo"] == "vuoto"
    assert "prior_bs" not in esito
