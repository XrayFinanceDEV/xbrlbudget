"""La griglia del banco ha un'azienda di Edilizia con magazzino lungo, e il driver usa il settore (lotto 3A, Task 9)."""
from decimal import Decimal as D

from scripts import parita_motore as banco


def test_la_griglia_ha_i_due_fixture_col_magazzino_lungo_e_il_loro_settore():
    griglia = banco.costruisci_griglia(20260910, 4)
    settori = {s["id"].split("__")[0]: s.get("settore") for s in griglia}
    assert len(griglia) == 135, len(griglia)
    assert settori.get("edilizia_magazzino") == 6
    assert settori.get("industria_magazzino") == 1
    assert settori.get("base") == 1
    edilizia = next(s for s in griglia if s["id"] == "edilizia_magazzino__neutro")
    # Moltiplicare prima di dividere (invece di dividere poi moltiplicare, come nel brief)
    # evita un artefatto di precisione Decimal: 1.000.000/600.000 e' un decimale periodico
    # e a 28 cifre significative (il default) il prodotto per 360 non torna esattamente
    # 600 (misurato: 600,0000000000000000000000001). La divisione 360.000.000/600.000 e'
    # invece esatta.
    giorni = D(edilizia["bs"]["sp05_rimanenze"]) * 360 / D(edilizia["ce"]["ce01_ricavi_vendite"])
    assert giorni == D("600")
    assert 'scenario_def.get("settore", 1)' in banco.DRIVER
