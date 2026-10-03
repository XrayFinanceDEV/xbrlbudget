"""Task 26, fix 1: la famiglia «situazione contabile riclassificata dettagliata» (budget_320, 379,
324, 402, 340, 371, 372 del corpus locale): didascalie di legge con importo NETTO stampato, un
``Cod.`` numerico davanti, righe-conto a 7 cifre sotto. PDF sintetici (niente dati reali).

Tre varianti di stampa, ciascuna dietro il flag ``varianti`` (i punti d'ingresso storici non le
leggono mai):
  a. «imposte anticipate» scritta a parte, fuori dal blocco «esigibili entro» (somma ai crediti);
  b. didascalia che va a capo con l'importo su una riga-codice poco piu' in basso (si unisce);
  c. «III - Immobilizzazioni finanziarie» non stampata quando e' zero.
"""
from __future__ import annotations

from decimal import Decimal as D

import fitz

from importers.import_snello import deterministico as DET
from importers.standard_ivcee_parser import (
    _LEGAL_CAPTION,
    extract_ivcee_didascalie,
    extract_standard_ivcee_balances,
    extract_standard_ivcee_income,
    riconosci_schema_con_dettaglio,
)

FONT = "helv"


def _dest(page, x_right, y, testo, fontsize=8):
    larghezza = fitz.get_text_length(testo, fontname=FONT, fontsize=fontsize)
    page.insert_text((x_right - larghezza, y), testo, fontname=FONT, fontsize=fontsize)


def _sx(page, x, y, testo, fontsize=8):
    page.insert_text((x, y), testo, fontname=FONT, fontsize=fontsize)


def _conti(prefisso, n=3):
    return [(f"{prefisso}{i:03d} conto di dettaglio {i}", "1,00") for i in range(n)]


def _righe_sp(*, imposte_a_parte=False, con_iii=True):
    entro = "450,00" if imposte_a_parte else "500,00"
    righe = [
        ("2 stato patrimoniale attivo", "1.000,00"),
        ("44 b) immobilizzazioni", "100,00"),
        ("276 b.ii) immobilizzazioni materiali", "100,00"),
        ("322 b.ii.2) impianti e macchinario", "100,00"),
    ] + _conti("1000")
    if con_iii:
        righe += [("534 b.iii) immobilizzazioni finanziarie", "0,00")]
    righe += [
        ("956 c) attivo circolante", "900,00"),
        ("1104 c.ii) crediti", "500,00"),
        ("1110 esigibili entro l'esercizio successivo", entro),
    ]
    if imposte_a_parte:
        righe += [("1114 imposte anticipate", "50,00")]
    righe += [
        ("1120 c.ii.1) verso clienti", "450,00"),
        ("1634 c.iv) disponibilita liquide", "400,00"),
    ] + _conti("2000") + [
        ("1718 d) ratei e risconti", "0,00"),
        ("1834 stato patrimoniale passivo", "1.000,00"),
        ("1850 a) patrimonio netto", "300,00"),
        ("1870 a.i) capitale", "100,00"),
        ("2012 a.vi) altre riserve", "150,00"),
        ("2086 a.ix) utile (perdita) dell'esercizio", "50,00"),
        ("2244 c) trattamento di fine rapporto di lavoro subordinato", "100,00"),
        ("2264 d) debiti", "600,00"),
        ("2270 esigibili entro l'esercizio successivo", "400,00"),
        ("2272 esigibili oltre l'esercizio successivo", "200,00"),
        ("2384 d.7) debiti verso fornitori", "600,00"),
    ] + _conti("3000") + [
        ("3200 e) ratei e risconti", "0,00"),
    ]
    return righe


def _righe_ce(*, a5_a_capo=False):
    ricavi, altri = ("900,00", "100,00") if a5_a_capo else ("1.000,00", "0,00")
    return [
        ("3330 conto economico", None),
        ("3380 a) valore della produzione", "1.000,00"),
        ("3400 a.1) ricavi delle vendite e delle prestazioni", ricavi),
        ("A5", altri),
        ("3700 b) costi della produzione", "900,00"),
        ("3710 b.6) per materie prime, sussidiarie, di consumo e di merci", "100,00"),
        ("3720 b.7) per servizi", "300,00"),
        ("3730 b.8) per godimento di beni di terzi", "0,00"),
        ("3740 b.9) per il personale", "200,00"),
        ("3750 b.10) ammortamenti e svalutazioni", "100,00"),
        ("3760 b.14) oneri diversi di gestione", "200,00"),
        ("3800 differenza tra valore e costi della produzione (a-b)", "100,00"),
        ("3900 c) totale proventi e oneri finanziari", "-10,00"),
        ("3910 c.17) interessi e altri oneri finanziari", "10,00"),
        ("4900 risultato prima delle imposte", "90,00"),
        ("4918 20) imposte sul reddito dell'esercizio", "40,00"),
        ("4934 21) utile (perdita) dell'esercizio", "50,00"),
    ]


def _pdf(path, *, imposte_a_parte=False, con_iii=True, a5_a_capo=False) -> str:
    doc = fitz.open()
    for righe in (_righe_sp(imposte_a_parte=imposte_a_parte, con_iii=con_iii),
                  _righe_ce(a5_a_capo=a5_a_capo)):
        page = doc.new_page(width=595, height=842)
        _sx(page, 40, 60, "Cod.")
        _sx(page, 70, 60, "Descrizione")
        _dest(page, 420, 60, "31/12/2025")
        _dest(page, 500, 60, "31/12/2024")
        y = 80
        for label, valore in righe:
            if label == "A5":
                # la didascalia va a capo: l'importo e il codice stanno su una riga poco piu' sotto
                _sx(page, 70, y, "a.5) altri ricavi e proventi, con separata indicazione dei contributi in")
                _sx(page, 40, y + 3.5, "3590")
                _dest(page, 420, y + 3.5, valore)
                _dest(page, 500, y + 3.5, valore)
                _sx(page, 70, y + 7, "conto esercizio")
                y += 14
                continue
            _sx(page, 40 if label[0].isdigit() and len(label.split()[0]) < 5 else 40, y, label)
            if valore:
                _dest(page, 420, y, valore)
                _dest(page, 500, y, valore)
            y += 11
    doc.save(str(path))
    return str(path)


def test_il_documento_di_base_si_adotta_come_schema_con_dettaglio(tmp_path):
    f = _pdf(tmp_path / "base.pdf")
    esito = DET.tentativo(f)
    assert esito["adottato"] is True
    assert esito["parser"] == "schema_legge_con_dettaglio"


def test_a_imposte_anticipate_a_parte_entrano_nei_crediti_a_breve(tmp_path):
    f = _pdf(tmp_path / "a.pdf", imposte_a_parte=True)
    bs, ce, conti = extract_ivcee_didascalie(f)
    assert bs is not None, "i crediti non chiudono: la riga a parte non e' sommata"
    assert bs["sp06_crediti_breve"] == D("500.00")
    assert bs["sp07_crediti_lungo"] == D("0")
    esito = DET.tentativo(f)
    assert esito["adottato"] is True


def test_a_senza_flag_le_imposte_a_parte_restano_fuori(tmp_path):
    # i punti d'ingresso storici non leggono la variante
    f = _pdf(tmp_path / "a2.pdf", imposte_a_parte=True)
    bs, _ = extract_standard_ivcee_balances(f)
    assert bs is None


def test_b_la_didascalia_a_capo_con_importo_su_riga_codice_si_unisce(tmp_path):
    f = _pdf(tmp_path / "b.pdf", a5_a_capo=True)
    bs, ce, conti = extract_ivcee_didascalie(f)
    assert ce is not None
    assert ce["ce04_altri_ricavi"] == D("100.00")
    assert ce["ce01_ricavi_vendite"] == D("900.00")
    assert DET.tentativo(f)["adottato"] is True


def test_b_i_punti_d_ingresso_storici_non_uniscono_le_righe(tmp_path):
    f = _pdf(tmp_path / "b2.pdf", a5_a_capo=True)
    ce, _ = extract_standard_ivcee_income(f)
    assert ce is None


def test_c_le_immobilizzazioni_finanziarie_a_zero_possono_mancare(tmp_path):
    f = _pdf(tmp_path / "c.pdf", con_iii=False)
    bs, ce, conti = extract_ivcee_didascalie(f)
    assert bs is not None
    assert bs["sp04_immob_finanziarie"] == D("0")
    assert bs["sp03_immob_materiali"] == D("100.00")
    assert DET.tentativo(f)["adottato"] is True


def test_c_senza_flag_le_immobilizzazioni_finanziarie_restano_obbligatorie(tmp_path):
    f = _pdf(tmp_path / "c2.pdf", con_iii=False)
    bs, _ = extract_standard_ivcee_balances(f)
    assert bs is None


def test_le_didascalie_con_cod_e_numerazione_a_punti_si_riconoscono(tmp_path):
    # «276 b.ii) ...», «c.ii.5 bis) ...», «d.4.1) ...»: prima ne vedeva una sola su 12 richieste
    for etichetta in ("276 b.ii) immobilizzazioni materiali", "1363 c.ii.5 bis.1) esigibili entro",
                      "2386 d.3.1) esigibili entro l'esercizio", "c) totale proventi e oneri finanziari",
                      "1104 c.ii) crediti", "3400 a.1) ricavi delle vendite"):
        assert _LEGAL_CAPTION.match(etichetta), etichetta
    for etichetta in ("1234567 impianto", "totale", "conto di dettaglio 3", "gas&plus 2.0 srl"):
        assert not _LEGAL_CAPTION.match(etichetta) or etichetta == "totale", etichetta
    f = _pdf(tmp_path / "r.pdf")
    r = riconosci_schema_con_dettaglio(f)
    assert r is not None and r["didascalie"] >= 12
