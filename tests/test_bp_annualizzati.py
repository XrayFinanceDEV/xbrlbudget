"""#62 S22: PFN/EBITDA e ROI del periodo infrannuale compaiono anche annualizzati nel Business plan."""
from decimal import Decimal as D

from app.renderers.business_plan.data import IndicatorRow, _annualizza


def _rows(roi, pfn):
    return (IndicatorRow("ROE", "percent", (D("1"), D("2"))),
            IndicatorRow("ROI", "percent", roi),
            IndicatorRow("PFN / EBITDA", "ratio", pfn))


KEYS = ("roe", "roi", "pfn_ebitda")


def test_sei_mesi_righe_annualizzate():
    out = _annualizza(_rows((D("4"), D("5")), (D("10.76"), D("3"))), KEYS, 6, 0)
    assert [r.label for r in out] == ["ROE", "ROI", "ROI (annualizzato)", "PFN / EBITDA",
                                      "PFN / EBITDA (annualizzato)"]
    assert out[2].values == (D("8"), D("5"))          # colonna a 12 mesi ripete il valore
    assert out[4].values == (D("5.38"), D("3"))
    assert out[2].unit == "percent" and out[4].unit == "ratio"


def test_valore_assente_resta_assente():
    out = _annualizza(_rows((None, D("5")), (D("1"), None)), KEYS, 6, 0)
    assert out[2].values == (None, D("5")) and out[4].values == (D("0.5"), None)


def test_dodici_mesi_o_senza_colonna_non_cambia():
    rows = _rows((D("4"), D("5")), (D("1"), D("3")))
    assert _annualizza(rows, KEYS, 12, 0) == rows
    assert _annualizza(rows, KEYS, None, 0) == rows
    assert _annualizza(rows, KEYS, 6, None) == rows
