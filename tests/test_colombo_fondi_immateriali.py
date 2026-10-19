"""COLOMBO (verifica con la sezione in colonna, SEZBIL): i fondi dei costi immateriali.

Tre conti di fondo senza il nome del cespite ("F.DO AMM. MAN.E RIP.BENI TERZI",
"MIGLIORIE FABBR.TERZ", "PROCEDURE ELABOR.") stanno sotto mastri che dicono IMMATER. / INGEGNO.
Cadevano nel default dei fondi materiali: 88.776,72 passavano da sp02 a sp03, attraversando un
aggregato, e la gerarchia risultava incoerente (previsionale bloccato). Il documento e' nel corpus
locale `Test/`, che non e' nel repository.
"""
import os
from decimal import Decimal

import pytest

_PDF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Test", "2026-10-weekend", "COLOMBO.pdf")

pytestmark = pytest.mark.skipif(not os.path.exists(_PDF), reason="COLOMBO.pdf non presente in Test/")


def _bs():
    from importers.import_snello.deterministico import tentativo
    esito = tentativo(_PDF)
    assert esito["adottato"] is True and esito["parser"] == "situazione_contabile_parser"
    assert esito["misura"]["scarto_sp"] == 0 and esito["misura"]["scarto_ce"] == 0
    return esito["bs"]


def test_i_fondi_immateriali_restano_in_sp02():
    bs = _bs()
    assert bs["sp02_immob_immateriali"] == Decimal("742535.64")
    assert bs["sp03_immob_materiali"] == Decimal("355664.89")


def test_aggregati_e_dettagli_coincidono():
    bs = _bs()
    for agg, prefisso in (("sp02_immob_immateriali", "sp02"), ("sp03_immob_materiali", "sp03")):
        dettagli = sum(v for k, v in bs.items() if k.startswith(prefisso) and k != agg)
        assert dettagli == bs[agg], agg
