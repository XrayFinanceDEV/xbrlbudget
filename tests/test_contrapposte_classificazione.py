"""Classificazione dei conti di un bilancio di verifica a sezioni contrapposte.

Contesto (2026-10-19, Napolitano Solution, verifica al 30/09/2026): il lettore
deterministico scartava il documento e il modello lo importava squadrato. Quattro difetti,
qui fissati sulle regole (le cifre del file reale stanno nel corpus locale ``Test/``):

- "PATRIMONIO NETTO" era una voce specifica (riserve): il capitale sociale sotto il mastro
  finiva nelle riserve, sp11 = 0; "Utili in attesa di destinaz." era un debito;
- "DEBITI VARI DI FINANZIAMENTO" andava per intero in banca (sotto: debiti v/dipendenti);
- "Fondi ammort.costi imp.e ampl." si nettava dalle immobilizzazioni materiali;
- "AMM/TO ATTREZZ.COMMERCIALI" finiva nei servizi per COMMERCIAL, oltre il confine
  dell'EBITDA (lo stesso su budget_188/229/238 del corpus: 55.000, 26.870, 134.277).

Run: python -m pytest tests/test_contrapposte_classificazione.py -v
"""
import os
import sys
from decimal import Decimal as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.situazione_contabile_parser import (  # noqa: E402
    _be_reclassify, classify_costi, classify_passivo)


def _tags(out):
    tot = {}
    for t, a in out:
        tot[t] = tot.get(t, D(0)) + a
    return tot


def test_patrimonio_netto_si_legge_dai_conti():
    passivo = [
        ("10", "PATRIMONIO NETTO", D("34841.08")),
        ("10029", "CAPITALE SOCIALE QUOTE", D("10000.00")),
        ("10710", "UTILI IN ATTESA DI DESTINAZ.", D("24841.08")),
    ]
    assert _tags(_be_reclassify(passivo, classify_passivo)) == {
        "sp11": D("10000.00"), "sp12": D("24841.08")}


def test_debiti_vari_di_finanziamento_non_sono_banca():
    passivo = [
        ("14", "DEBITI VARI DI FINANZIAMENTO", D("4285.00")),
        ("14123", "DEBITI V/DIPENDENTI", D("4285.00")),
    ]
    tot = _tags(_be_reclassify(passivo, classify_passivo))
    assert "sp16a" not in tot and tot == {"sp16g": D("4285.00")}


def test_fondo_costi_di_impianto_e_ampliamento_e_immateriale():
    assert classify_passivo("FONDI AMMORT.COSTI IMP.E AMPL.") == ("depr_sp02", True)
    assert classify_passivo("FONDO AMM/TO MACCHINARI")[0] == "depr_sp03"


def test_ammortamento_prima_di_ogni_altra_parola():
    assert classify_costi("AMM/TO ATTREZZ.COMMERCIALI") == ("ce09b", True)
    assert classify_costi("AMM.TO ORDINARIO ATTREZZATURE INDUSTRIALI E COMMERCIALI") == ("ce09b", True)
    assert classify_costi("AMMORTAMENTO SPESE DI COSTITUZIONE") == ("ce09a", True)
    # amministrazione, non ammortamento
    assert classify_costi("AMM.NE CONDOMINIO")[0] != "ce09b"


def test_servizi_abbreviati():
    assert classify_costi("COMP.PROF.CONSUL.AMM.VA/FISC.")[0] == "ce06"
    assert classify_costi("VIAGGI/TRASP./PARCHEG.DIV.")[0] == "ce06"
    assert classify_costi("SPESE RISTORANTI/PERNOTT. 75%")[0] == "ce06"
