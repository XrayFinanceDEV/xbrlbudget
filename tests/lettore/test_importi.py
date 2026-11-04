from decimal import Decimal

import pytest

from importers.lettore.importi import Importo, leggi_importo


@pytest.mark.parametrize("token, valore", [
    ("1.234,56", "1234.56"),
    ("1.234", "1234"),
    ("-1.234,56", "-1234.56"),
    ("1.234,56-", "-1234.56"),
    ("(1.234,56)", "-1234.56"),
    ("(5.367,37", "5367.37"),
    ("1.234,56 A", "-1234.56"),
    ("1.234,56 D", "1234.56"),
    ("1.234,56_", "1234.56"),
    ("46.078 (1)", "46078"),
    ("46.078*", "46078"),
    ("€ 1.234,56", "1234.56"),
])
def test_importo(token, valore):
    r = leggi_importo(token)
    assert r == Importo(Decimal(valore), "importo", token)
    assert isinstance(r.valore, Decimal)


def test_zero_cella_vuota():
    r = leggi_importo("-")
    assert r.valore == Decimal("0") and r.forma == "zero"


@pytest.mark.parametrize("token", ["12,345", "1.712.097,143"])
def test_percentuale(token):
    assert leggi_importo(token).forma == "percentuale"


@pytest.mark.parametrize("token", ["2025", "104", "31/12/2025", "12", "********", ""])
def test_non_importo(token):
    assert leggi_importo(token) is None
