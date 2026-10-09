"""ce09c (svalutazione immobilizzazioni) e' non monetaria; ce09d non si conta due volte."""

from decimal import Decimal as D

from backend.app.calculations.cashflow_detailed import DetailedCashFlowCalculator
from database.models import BalanceSheet, IncomeStatement


def _zeroed(model, **kw):
    # oggetti non persistiti: le colonne senza valore sono None, non 0
    cols = {c.name: D(0) for c in model.__table__.columns
            if c.name.startswith(("sp", "ce"))}
    cols.update({k: D(v) for k, v in kw.items()})
    return model(**cols)


def _bs(sp04, cash):
    return _zeroed(BalanceSheet, sp04_immob_finanziarie=sp04,
                   sp09_disponibilita_liquide=cash)


def _ce(**kw):
    return _zeroed(IncomeStatement, **kw)


def _calc(prev, cur, inc):
    return DetailedCashFlowCalculator.calculate(
        bs_current=cur, bs_previous=prev, inc_current=inc, year=2027,
    )


def _op_plus_inv(cf):
    return (cf.operating_activities.total_operating_cashflow
            + cf.investing_activities.total_investing_cashflow)


def test_ce09c_riaggiunta_e_non_e_disinvestimento():
    # sp04 scende di 10.000 per la sola svalutazione ce09c
    prev, cur = _bs(100000, 50000), _bs(90000, 50000)
    cf = _calc(prev, cur, _ce(ce09c_svalutazioni=10000))
    assert cf.operating_activities.non_cash_adjustments.write_downs == D("10000.00")
    fin = cf.investing_activities.financial_assets
    assert fin.disinvestments == D("0.00")
    assert fin.investments == D("0.00")
    assert cf.investing_activities.total_investing_cashflow == D("0.00")
    # la ripartizione cambia, la cassa no: il costo riaggiunto nell'operativo
    # e' esattamente quello che non e' piu' contato come disinvestimento
    assert cf.operating_activities.non_cash_adjustments.total == D("10000.00")
    # operativo + investimenti = 10.000 come quando la svalutazione era letta
    # come disinvestimento: cambia la riga, non la cassa
    assert _op_plus_inv(cf) == D("10000.00")


def test_ripiego_ammortamenti_non_conta_ce09d_due_volte():
    prev, cur = _bs(0, 0), _bs(0, 0)
    cf = _calc(prev, cur, _ce(ce09_ammortamenti=30000, ce09d_svalutazione_crediti=5000))
    nc = cf.operating_activities.non_cash_adjustments
    assert nc.depreciation_amortization == D("25000.00")
    assert nc.write_downs == D("5000.00")
    assert nc.total == D("30000.00")
