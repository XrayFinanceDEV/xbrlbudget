"""`_is_fondo_amm` governa l'intero netting dei fondi, quindi il pareggio di route C.

E' una congiunzione di sottostringhe su testo solo-maiuscolo: riconosce `F.DO AMM`
ma non `F.di ammor.to` ne' `Fdo amm`. Un fondo non riconosciuto non viene nettato
dal cespite -> l'attivo resta LORDO e il passivo gonfio della stessa massa -> i due
lati non tornano -> la differenza diventa residuo non classificato -> se supera
l'1% scatta QUADRATURA MASCHERATA e l'import viene RIFIUTATO.

Allargarlo e' additivo per costruzione: si riconoscono piu' fondi, mai meno.
"""
import pytest

from importers.situazione_contabile_parser import _is_fondo_amm

# grafie gia' coperte: non devono regredire
GIA_COPERTE = [
    "F.DO AMM.TO FABBRICATI",
    "FONDO AMMORTAMENTO IMPIANTI",
    "FONDI AMMORTAMENTO IMMOBILIZ",
    "F/AMM. AUTOMEZZI",
    "F.DO AMM.NTO MACCHINARI",
]

# grafie reali che oggi SFUGGONO
NUOVE = [
    "F.DI AMMOR.TO FABBRICATI",
    "FDO AMM IMPIANTI",
    "F.DI AMMORTAMENTO AUTOMEZZI",
    "FONDO AMM. ATTREZZATURE",
]

# NON sono fondi ammortamento: il netting non deve toccarli
NON_FONDI = [
    "FORNITORI",
    "AMMORTAMENTO IMMOBILIZZAZIONI IMMATERIALI",   # COSTO del CE, non un fondo dello SP
    "QUOTA AMMORTAMENTO ESERCIZIO",                # idem
    "FONDO TFR",
    "FONDO RISCHI E ONERI",
    "FONDO SVALUTAZIONE CREDITI",                  # contra dei CREDITI, non delle immobilizz.
]


@pytest.mark.parametrize("desc", GIA_COPERTE)
def test_non_regredisce_le_grafie_gia_coperte(desc):
    assert _is_fondo_amm(desc) is True


@pytest.mark.parametrize("desc", NUOVE)
def test_riconosce_le_grafie_che_oggi_sfuggono(desc):
    assert _is_fondo_amm(desc) is True


@pytest.mark.parametrize("desc", NON_FONDI)
def test_non_allarga_a_cio_che_non_e_un_fondo_ammortamento(desc):
    assert _is_fondo_amm(desc) is False
