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


# ---------------------------------------------------------------------------
# `_is_fondo_amm` NON governa la route DEPI/`build_iv_cee`: li' il netting lo
# decide `_classify_sp_passivo` sulla tabella `_SP_PASSIVO_RULES`, che e' un
# RICONOSCITORE DIVERSO. I due possono divergere — ed e' esattamente cio' che
# succede su budget_281 (GI.AL TRASPORTI, situazione patrimoniale al 31/03/2026):
# `_is_fondo_amm` riconosce tutti e 6 i fondi, la tabella ne riconosce UNO SOLO
# (`F.DO AMM.TO TELEFONO CELLULARE`, 42,61 su 124.936,25) perche' la grafia con
# SLASH e' coperta solo in coppia con IMMAT/MATER — parole che compaiono nei
# mastri aggregati, mai nei conti di dettaglio per categoria.
#
# I 5 fondi non riconosciuti cadono nel default `sp16` (debiti a breve): l'attivo
# resta LORDO, i debiti si gonfiano della stessa massa, i due lati continuano a
# pareggiare e NESSUN gate protesta. E' un errore SILENTE — la classe peggiore.
CLASSIFY_PASSIVO_FONDI = [
    # (descrizione, campo atteso) — grafie reali dal corpus
    ("F/AMM.MACCHINARI", 'depr_sp03'),
    ("F/AMM.ATTREZ. IND.LI E COMM.LI", 'depr_sp03'),
    ("F/AMM.MACCH. ELETTROM. D'UFF.", 'depr_sp03'),
    ("F/AMM. AUTOCARRI/AUTOVETTURE", 'depr_sp03'),
    ("F.DO AMM.TO TELEFONO CELLULARE", 'depr_sp03'),   # gia' coperta: non deve regredire
    # grafia senza punti ne' slash: anch'essa oggi cade nel default sp16
    ("FONDO AMMORTAMENTO IMPIANTI", 'depr_sp03'),
    ("FONDI AMMORTAMENTO IMMOBILIZZAZIONI IMMATERIALI", 'depr_sp02'),
    ("F/AMM. SOFTWARE GESTIONALE", 'depr_sp02'),
]

# Conti del PASSIVO che NON sono fondi ammortamento: la canonicalizzazione della
# grafia non deve trascinarli nel netting. "AMMINISTRATORI" contiene "AMM".
CLASSIFY_PASSIVO_NON_FONDI = [
    "AMMINISTRATORI C/COMPENSI",
    "FATTURE DA RICEVERE",
    "F.DO RIS.P/CONTROV.LEGALIinCORSO",
    "DEBITI V/FORNITORI",
    "FONDO TFR",
]


@pytest.mark.parametrize("desc,atteso", CLASSIFY_PASSIVO_FONDI)
def test_la_tabella_del_passivo_netta_ogni_grafia_del_fondo(desc, atteso):
    from importers.situazione_contabile_parser import _classify_sp_passivo
    assert _classify_sp_passivo(desc.upper()) == atteso


@pytest.mark.parametrize("desc", CLASSIFY_PASSIVO_NON_FONDI)
def test_la_canonicalizzazione_non_trascina_i_non_fondi_nel_netting(desc):
    from importers.situazione_contabile_parser import _classify_sp_passivo
    assert _classify_sp_passivo(desc.upper()) not in ('depr_sp02', 'depr_sp03')


def test_i_due_riconoscitori_di_fondo_non_divergono():
    """Ogni grafia che `_is_fondo_amm` chiama fondo, la tabella del passivo deve
    nettarla. La divergenza fra i due riconoscitori E' il bug di budget_281."""
    from importers.situazione_contabile_parser import _classify_sp_passivo
    for desc in GIA_COPERTE + NUOVE + [d for d, _ in CLASSIFY_PASSIVO_FONDI]:
        up = desc.upper()
        assert _is_fondo_amm(up) is True, desc
        assert _classify_sp_passivo(up) in ('depr_sp02', 'depr_sp03'), desc
