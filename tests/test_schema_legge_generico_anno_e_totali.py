"""Schema di legge generico: l'anno stampato sul titolo di sezione e il «Totale» che ripete la
voce dopo il suo dettaglio.

Contesto (2026-10-27, lotto week-43, Napolitano 1417/1421/1423/1425, CEE ordinario a colonna
unica):
- A. la riga ``CONTO ECONOMICO  2025`` porta l'anno nella colonna degli importi. Il titolo con
  un importo non apriva la sezione, il «21) Utile (perdita)» restava nel patrimonio netto come
  voce IX e il documento era rifiutato (``didascalia_non_collocabile``).
- B. «VI - Altre riserve 1», i conti a zero che la compongono, poi «Totale altre riserve 1»: i
  conti si toglievano, il totale restava e chiudeva la voce del patrimonio netto; la voce VII
  finiva sotto ``SPP`` invece che sotto ``SPP.A`` e il documento era rifiutato.

Run: python -m pytest tests/test_schema_legge_generico_anno_e_totali.py -v
"""
import os
import sys
from decimal import Decimal as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers import schema_legge_generico as G  # noqa: E402
from importers import xbrl_reso_parser as reso  # noqa: E402

_SP = [
    (0, "STATO PATRIMONIALE ATTIVO", [None]),
    (0, "B) Immobilizzazioni", [None]),
    (0, "I - Immateriali", [D(10)]),
    (0, "Totale attivo", [D(10)]),
    (0, "STATO PATRIMONIALE PASSIVO", [None]),
    (0, "A) Patrimonio netto", [None]),
    (0, "I - Capitale", [D(5)]),
    (0, "IX - Utile (perdita) dell'esercizio", [D(5)]),
    (0, "Totale patrimonio netto", [D(10)]),
    (0, "Totale passivo", [D(10)]),
]


def _didascalie(righe):
    return [(r.didascalia, list(r.valori)) for r in righe]


def test_l_anno_stampato_sul_titolo_del_conto_economico_non_e_un_importo():
    grezze = _SP + [
        (1, "CONTO ECONOMICO", [D(2025)]),
        (1, "A) Valore della produzione", [None]),
        (1, "1) ricavi delle vendite e delle prestazioni", [D(5)]),
        (1, "21) Utile (perdita) dell'esercizio", [D(5)]),
    ]
    righe, _, _ = G._righe_da_grezze(grezze, 1, {0: 2025})
    didascalie = [r.didascalia for r in righe]
    assert "Conto economico" in didascalie
    ce = didascalie[didascalie.index("Conto economico"):]
    assert ce[-1] == "Utile (perdita) dell'esercizio"     # non "IX - ...", voce del netto


def test_un_importo_sul_titolo_che_non_e_l_anno_resta_un_importo():
    """Solo l'anno delle colonne si toglie: un altro numero sul titolo resta letto."""
    grezze = _SP + [(1, "CONTO ECONOMICO", [D(1234)])]
    righe, _, _ = G._righe_da_grezze(grezze, 1, {0: 2025})
    assert ("CONTO ECONOMICO", [D(1234)]) in _didascalie(righe)


def _r(didascalia, *valori):
    return reso._Riga(didascalia, [D(v) for v in valori], 0)


def test_il_totale_che_ripete_la_voce_dopo_i_suoi_conti_si_toglie_con_loro():
    righe = [
        _r("VI - Altre riserve", 1),
        _r("Riserva straordinaria", 0),
        _r("Varie altre riserve", 1),
        _r("Totale altre riserve", 1),
        _r("VII - Riserva per operazioni di copertura dei flussi finanziari attesi", 0),
    ]
    out = G._togli_dettaglio_conti(righe)
    assert [r.didascalia for r in out] == [
        "VI - Altre riserve",
        "VII - Riserva per operazioni di copertura dei flussi finanziari attesi",
    ]


def test_un_totale_con_un_altro_nome_o_un_altro_importo_resta():
    """Il totale si toglie solo se ripete la voce: stesso importo e stesso nome."""
    altro_nome = [
        _r("VI - Altre riserve", 1),
        _r("Riserva straordinaria", 0),
        _r("Varie altre riserve", 1),
        _r("Totale patrimonio netto", 1),
    ]
    assert [r.didascalia for r in G._togli_dettaglio_conti(altro_nome)][-1] == \
        "Totale patrimonio netto"
    altro_importo = [
        _r("VI - Altre riserve", 1),
        _r("Riserva straordinaria", 0),
        _r("Varie altre riserve", 1),
        _r("Totale altre riserve", 2),
    ]
    assert [r.didascalia for r in G._togli_dettaglio_conti(altro_importo)][-1] == \
        "Totale altre riserve"


def test_senza_dettaglio_tolto_il_totale_resta():
    righe = [_r("VI - Altre riserve", 1), _r("Totale altre riserve", 1)]
    assert [r.didascalia for r in G._togli_dettaglio_conti(righe)] == [
        "VI - Altre riserve", "Totale altre riserve"]
