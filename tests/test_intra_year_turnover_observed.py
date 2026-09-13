"""Guardia fra stock proiettato e stock già osservato nel parziale (#59)."""
from decimal import Decimal as D
from types import SimpleNamespace

from calculations.intra_year_engine import IntraYearEngine


def _scala(*, observed, projected_base=100, months=5):
    engine = IntraYearEngine(None)
    partial = SimpleNamespace(sp06_crediti_breve=D(str(observed)))
    value = engine._scaled_or_carried(
        "sp06_crediti_breve",
        ref_stock=D("20"),
        ref_base=D("100"),
        projected_base=D(str(projected_base)),
        partial_bs=partial,
        period_months=months,
    )
    return value, engine._diagnostics


def test_una_proiezione_sotto_meta_dello_stock_osservato_viene_riportata():
    value, diagnostics = _scala(observed=100, projected_base=100, months=5)
    assert value == D("100")
    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic["code"] == "turnover_projection_below_observed"
    assert diagnostic["severity"] == "warning"
    assert diagnostic["projected_amount"] == "20.0"
    assert diagnostic["amount"] == "100"
    assert diagnostic["minimum_ratio"] == "0.50"
    assert diagnostic["period_months"] == 5


def test_meta_esatta_non_e_una_contraddizione():
    value, diagnostics = _scala(observed=40, projected_base=100, months=5)
    assert value == D("20.0")
    assert diagnostics == []


def test_un_periodo_troppo_corto_resta_non_valutabile():
    value, diagnostics = _scala(observed=100, projected_base=100, months=2)
    assert value == D("20.0")
    assert diagnostics == []


def test_un_consuntivo_di_dodici_mesi_non_e_un_parziale_da_controllare():
    value, diagnostics = _scala(observed=100, projected_base=100, months=12)
    assert value == D("20.0")
    assert diagnostics == []


def test_senza_stock_osservato_non_esiste_contraddizione():
    value, diagnostics = _scala(observed=0, projected_base=100, months=5)
    assert value == D("20.0")
    assert diagnostics == []
