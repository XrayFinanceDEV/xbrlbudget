"""Un conto stampato SOTTO un mastro con un codice che non ne porta il prefisso (budget_1478,
2026-10-27: «1201036 Carta prepagata» 112,49 sotto il mastro «360 Debiti verso banche»
5.128,88 = 5.016,39 + 112,49). La parentela dal prefisso lo lasciava radice orfana: il mastro
(descrizione specifica) si prendeva tutta la massa e l'orfano si contava una seconda volta.
Decide il totale stampato: il mastro e' la somma dei figli diretti PIU' l'orfano, al centesimo."""
from decimal import Decimal as D

from importers.situazione_contabile_parser import _be_reclassify


def _classify(desc):
    if "BANCHE" in desc:
        return "sp16a", True
    return "sp16g", False


def test_orfano_stampato_sotto_il_mastro_che_lo_spiega_al_centesimo_e_suo_figlio():
    items = [("360", "DEBITI VERSO BANCHE", D("5128.88")),
             ("3601025", "BANCA POPOLARE C/C", D("5016.39")),
             ("1201036", "CARTA PREPAGATA", D("112.49")),
             ("380", "ALTRI DEBITI", D("100.00"))]
    righe = _be_reclassify(items, _classify)
    assert sum(a for f, a in righe if f == "sp16a") == D("5128.88")
    assert sum(a for f, a in righe if f == "sp16g") == D("100.00")


def test_orfano_che_non_chiude_il_mastro_resta_radice():
    items = [("360", "DEBITI VERSO BANCHE", D("5128.88")),
             ("3601025", "BANCA POPOLARE C/C", D("5016.39")),
             ("1201036", "CARTA PREPAGATA", D("50.00"))]
    righe = _be_reclassify(items, _classify)
    assert sum(a for f, a in righe if f == "sp16g") == D("50.00")


def test_mastro_che_i_figli_gia_spiegano_non_adotta_nulla():
    items = [("360", "DEBITI VERSO BANCHE", D("5016.39")),
             ("3601025", "BANCA POPOLARE C/C", D("5016.39")),
             ("1201036", "CARTA PREPAGATA", D("112.49"))]
    righe = _be_reclassify(items, _classify)
    assert sum(a for f, a in righe if f == "sp16g") == D("112.49")
