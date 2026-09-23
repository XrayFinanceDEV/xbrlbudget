"""Banco di prova: le sezioni 2, 4 e 7 del report infrannuale contro le pagine 4, 6 e 9 del PDF del committente.

I numeri del riferimento sono quelli del nostro motore (spec, «fatto che cambia il banco»): il fixture è AMBIENTA
(575/17) letta dal DB e serializzata, e il banco confronta sia i riquadri sia le cifre. Tolleranze della spec §7:
8 pt su y0, 3 pt sull'altezza, 2 pt su x0/x1. Il PDF del committente non è in git: senza, il test si salta.
"""
import os
from pathlib import Path

import fitz
import pytest

from app.renderers.infrannuale.data import load_json
from app.renderers.infrannuale.document import render_infrannuale
from tests.test_bp_banco import confronta

ROOT = Path(__file__).resolve().parents[1]
REF = Path(os.environ.get("INF_RIFERIMENTO_PDF", ROOT / "tests/.banco-infrannuale/riferimento.pdf"))
FIXTURE = ROOT / "tests/fixtures/infrannuale/banco_ambienta.json"
PAGINE = {"economia": 4, "patrimonio": 6, "crisi": 9}
senza_riferimento = pytest.mark.skipif(not REF.is_file(), reason="PDF del committente assente: il banco gira in locale")


@senza_riferimento
def test_banco_strutturale_pagine_4_6_9():
    new = fitz.open(stream=render_infrannuale(load_json(FIXTURE), only=tuple(PAGINE)), filetype="pdf")
    ref = fitz.open(REF)
    assert new.page_count == 3
    problemi = {sec: confronta(ref[p - 1], new[i]) for i, (sec, p) in enumerate(PAGINE.items())}
    assert not any(problemi.values()), problemi


def test_cifre_come_il_riferimento():
    new = fitz.open(stream=render_infrannuale(load_json(FIXTURE), only=tuple(PAGINE)), filetype="pdf")
    t4, t6, t9 = (new[i].get_text() for i in range(3))
    for s in ("SEZIONE 2", "€ 2,10 mln", "+11,92% sul 2025 C", "4.209.510", "−22.596", "1.224,51%", "433,19%"):
        assert s in t4, s
    for s in ("SEZIONE 4", "€ 997,4 mila", "+17,00% sul 2025 C", "1.754.565", "808,30%", "€ 208.869 nel 2025 C"):
        assert s in t6, s
    for s in ("3,026×", "−67.803", "20,85%", "attenzione", "C2 · Rischio grave", "8 su 14 oltre soglia", "0 su 7"):
        assert s in t9, s
