"""C01 (lotto 2 fix rilievi, 2026-09-26): il DSCR del report include la quota capitale rimborsata
nell'anno, letta dal rendiconto finanziario dettagliato (`financing.third_party_funds.decreases`,
Task 5/C08) — mai più (EBITDA - imposte) / oneri finanziari, la vecchia formula che il report
chiamava esplicitamente "proxy" in tabelle, grafici e testi (PDF, Word, dossier Typst).

L'oracolo end-to-end (con rimborsi reali del motore) vive in
`tests/test_rilievi_ambienta.py::test_C01_il_dscr_del_report_comprende_la_quota_capitale`. Qui:
i motivi di indisponibilità dichiarati da `calculations/report_indicators.py::_dscr_capital_quota`
sui casi unitari, e la sparizione della parola "proxy" dal PDF e dal Word del Business plan sullo
stesso scenario dell'oracolo.
"""
from decimal import Decimal as D

import pytest

from calculations.ce_result import calculate_ce_result
from calculations.report_indicators import indicator_results
from tests.rilievi_kit import BASE_BS, BASE_CE, genera, generato, piano
from tests.test_rilievi_ambienta import _con_rimborsi

BS = dict(BASE_BS)
CE = dict(BASE_CE)


def _bp():
    pytest.importorskip("backend.app.renderers.business_plan.data")


# ===========================================================================
# _dscr_capital_quota / indicator_results: i motivi di indisponibilità
# ===========================================================================

def test_senza_rendiconto_il_dscr_e_indefinito_non_zero_denominator():
    """Senza un rendiconto per l'anno (colonna storica del dossier, o i periodi infrannuali
    `observed`/`adjusted`, che non ne calcolano uno proprio) il DSCR non ha una quota capitale:
    `cashflow_unavailable`, mai un fallback silenzioso alla vecchia formula né uno
    `zero_denominator` sui soli oneri finanziari nulli."""
    res = indicator_results(dict(BS), dict(CE))
    assert res["practice.dscr"].value is None
    assert res["practice.dscr"].reason == "cashflow_unavailable"
    assert "proxy" not in res["practice.dscr"].methodology.lower()


def test_erogazioni_incoerenti_rende_il_dscr_non_determinabile():
    """Task 5/C08: quando le erogazioni note dell'anno non bastano a spiegare l'aumento del
    debito rilevato, il rendiconto torna al netto storico su `third_party_funds` e lo dichiara con
    `erogazioni_incoerenti`. Il DSCR non usa comunque quel numero come quota capitale — è
    dichiaratamente non determinabile, mai un rimborso inventato."""
    cashflow = {"financing": {"erogazioni_incoerenti": True,
                              "third_party_funds": {"decreases": D("999999")}}}
    res = indicator_results(dict(BS), dict(CE), cashflow=cashflow)
    assert res["practice.dscr"].value is None
    assert res["practice.dscr"].reason == "rimborsi_non_determinabili"


def test_senza_erogazioni_note_decreases_e_comunque_la_quota_capitale():
    """Colonna storica/base, o un anno di piano il cui `engine_meta` non dichiara erogazioni: il
    rendiconto calcola comunque `decreases` come diminuzione netta del debito finanziario
    dell'anno, e il DSCR la usa come quota capitale — dichiarato nella formula dell'indicatore,
    non un secondo proxy silenzioso."""
    ce = dict(CE)
    ce["ce15_oneri_finanziari"] = D("10000")
    cashflow = {"financing": {"third_party_funds": {"decreases": D("5000")}}}
    res = indicator_results(dict(BS), ce, cashflow=cashflow)
    ce_result = calculate_ce_result(ce)
    atteso = (ce_result.ebitda - ce_result.taxes) / D("15000")
    assert res["practice.dscr"].value == atteso
    assert res["practice.dscr"].reason is None


def test_denominatore_nullo_resta_zero_denominator_con_rendiconto():
    """Un rendiconto presente ma con oneri finanziari e quota capitale entrambi nulli resta un
    vero `zero_denominator`, non `cashflow_unavailable`: il rendiconto c'è, dice solo che non
    c'era nulla da rimborsare né oneri da pagare."""
    ce = dict(CE)
    ce["ce15_oneri_finanziari"] = D("0")
    cashflow = {"financing": {"third_party_funds": {"decreases": D("0")}}}
    res = indicator_results(dict(BS), ce, cashflow=cashflow)
    assert res["practice.dscr"].value is None
    assert res["practice.dscr"].reason == "zero_denominator"


def test_erogazioni_incoerenti_falso_di_default_non_serve_dichiararlo():
    """`erogazioni_incoerenti` assente dal dizionario (mai scritto) si comporta come `False` — un
    rendiconto storico/senza motore non lo dichiara affatto, e il DSCR non deve inciampare su una
    chiave mancante."""
    cashflow = {"financing": {"third_party_funds": {"decreases": D("0")}}}
    res = indicator_results(dict(BS), dict(CE), cashflow=cashflow)
    assert res["practice.dscr"].reason != "rimborsi_non_determinabili"


# ===========================================================================
# End-to-end: PDF e Word del Business plan non citano più "proxy"
# ===========================================================================

def test_pdf_e_word_del_business_plan_non_citano_piu_il_proxy():
    """Stesso scenario dell'oracolo C01 (rimborsi 53.409 nel 2027, sez. 1/6/Allegato D erano le tre
    superfici che citavano esplicitamente "proxy"): né il PDF né il Word del Business plan devono
    più contenere la parola, in nessuna sezione."""
    _bp()
    import fitz
    from app.renderers.docx_export import docx_text
    from backend.app.renderers.business_plan.document import render_business_plan, render_business_plan_docx
    e = generato(genera(_con_rimborsi(), report=True))
    pdf = render_business_plan(e.data)
    testo_pdf = "".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf")).lower()
    assert "proxy" not in testo_pdf
    docx = render_business_plan_docx(e.data)
    testo_docx = "\n".join(docx_text(docx)).lower()
    assert "proxy" not in testo_docx


def test_dscr_del_report_usa_la_stessa_riga_di_rimborsi_del_rendiconto():
    """Il DSCR di piano legge esattamente `financing.third_party_funds.decreases` dell'anno — la
    stessa riga che l'Allegato del rendiconto (`cf_rimborsi`) mostra — non un secondo calcolo
    indipendente che potrebbe divergere."""
    _bp()
    e = generato(genera(_con_rimborsi(), report=True))
    ce = e.anni[2027][1]
    mol = e.data.v("ebitda")[e.data.plan_idx[0]]
    rimborsi = piano(e.data, "cf_rimborsi")[0]
    atteso = (D(str(mol)) - ce["ce20_imposte"]) / (ce["ce15_oneri_finanziari"] + D(str(rimborsi)))
    assert abs(D(str(piano(e.data, "dscr")[0])) - atteso) < D("0.01")
