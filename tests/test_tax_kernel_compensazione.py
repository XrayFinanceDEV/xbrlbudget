"""Il credito da acconti si compensa per intero l'anno dopo (commercialista, 2026-09-18).

Prima il credito dell'anno N si consumava solo contro il saldo di N+1, che e' zero proprio
quando N chiude a credito: il resto (`opening_credit_left`) si trascinava e si accumulava.
Ora la posizione di apertura si chiude sempre: il debito esce come saldo, il credito si
compensa e riduce le uscite per imposte, anche oltre gli acconti.
"""
from decimal import Decimal as D

from calculations.projection_common import tax_settlement_saldo_acconto


def _k(**kw):
    base = dict(opening_credit=0, saldo_due=0, rate_due=0, current_tax=0, previous_tax=0,
                acconto_pct=D("100"), explicit_advances=None)
    base.update(kw)
    return tax_settlement_saldo_acconto(**base)


def test_debito_puro():
    t = _k(saldo_due=D("1000"), current_tax=D("1200"), previous_tax=D("800"))
    assert t.saldo_paid == D("1000")
    assert t.acconti_paid == D("800")
    assert t.generated_debt == D("400.00")
    assert t.generated_credit == D("0")
    assert t.credito_compensato == D("0")
    assert t.cash_out == D("1800")


def test_credito_compensato_per_intero():
    t = _k(opening_credit=D("500"), current_tax=D("600"), previous_tax=D("800"))
    assert t.credito_compensato == D("500")
    assert t.opening_credit_left == D("0")
    assert t.generated_credit == D("200")
    assert t.cash_out == D("300")  # 0 saldo + 800 acconti − 500 compensati


def test_credito_oltre_gli_acconti_da_cassa_in_entrata():
    t = _k(opening_credit=D("900"), current_tax=D("100"), previous_tax=D("100"))
    assert t.cash_out == D("-800")
    assert t.opening_credit_left == D("0")


def test_apertura_mista_chiude_entrambe():
    t = _k(opening_credit=D("300"), saldo_due=D("1000"), current_tax=D("500"), previous_tax=D("400"))
    assert t.saldo_paid == D("1000")
    assert t.credito_compensato == D("300")
    assert t.cash_out == D("1100")  # 1000 + 400 − 300


def test_acconti_storici_eccedenti_restano_credito_per_l_anno_dopo():
    t = _k(opening_credit=D("900"), previous_tax=D("100"), carry_excess_credit=True)
    assert t.credito_compensato == D("100")
    assert t.opening_credit_left == D("800")
    assert t.cash_out == D("0")
