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


@pytest.mark.parametrize("token, marcatore", [("1.234,56 A", "A"), ("1.234,56 D", "D")])
def test_marcatore_attaccato_e_neutro(token, marcatore):
    # R23: il marcatore resta accanto all'importo, senza segno; il segno lo da' il lato (`segno_del_lato`)
    assert leggi_importo(token) == Importo(Decimal("1234.56"), "importo", token, marcatore)


@pytest.mark.parametrize("lato, d, a", [("U", "1234.56", "-1234.56"), ("L", "1234.56", "-1234.56"),
                                        ("R", "-1234.56", "1234.56")])
def test_segno_del_marcatore_dipende_dal_lato(lato, d, a):
    from importers.lettore.importi import segno_del_lato
    assert segno_del_lato(leggi_importo("1.234,56 D"), lato).valore == Decimal(d)
    assert segno_del_lato(leggi_importo("1.234,56 A"), lato).valore == Decimal(a)
