"""Banco di prova: le sezioni 2, 4 e 5 rese con i numeri del committente contro le pagine 4, 6 e 7 del suo PDF.

Si confrontano i riquadri pieni (per colore), le immagini dei grafici e la fascia d'intestazione. Tolleranze della
spec §6: 8 pt su y0, 3 pt sull'altezza, 2 pt su x0/x1. Il PDF del committente non è in git: senza, il test si salta.
"""
import os
from pathlib import Path

import fitz
import pytest

from app.renderers.business_plan.data import load_json
from app.renderers.business_plan.document import render_business_plan

ROOT = Path(__file__).resolve().parents[1]
REF = Path(os.environ.get("BP_RIFERIMENTO_PDF", ROOT / "tests/.banco-business-plan/riferimento.pdf"))
FIXTURE = ROOT / "tests/fixtures/business_plan/banco_ambienta.json"
PAGINE = {"economia": 4, "pareggio": 6, "flussi": 7}


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(x * 255 + 0.5) for x in c)


def boxes(page) -> list:
    out = [(f"fill{_hex(d['fill'])}", d["rect"]) for d in page.get_drawings()
           if d.get("fill") and d["rect"].height > 3]
    out += [("img", fitz.Rect(i["bbox"])) for i in page.get_image_info()]
    return out


def confronta(ref_page, new_page) -> list:
    """Restituisce le discrepanze; lista vuota = pagina conforme."""
    a, b = boxes(ref_page), boxes(new_page)
    errors = []
    if sorted(k for k, _ in a) != sorted(k for k, _ in b):
        errors.append(f"riquadri diversi: riferimento {sorted(k for k, _ in a)} contro {sorted(k for k, _ in b)}")
        return errors
    used = set()
    for kind, r in a:
        cands = [(j, rr) for j, (kk, rr) in enumerate(b) if kk == kind and j not in used]
        j, best = min(cands, key=lambda c: abs(c[1].y0 - r.y0) + abs(c[1].x0 - r.x0))
        used.add(j)
        dy, dh = best.y0 - r.y0, best.height - r.height
        dx0, dx1 = best.x0 - r.x0, best.x1 - r.x1
        if abs(dy) > 8 or abs(dh) > 3 or abs(dx0) > 2 or abs(dx1) > 2:
            errors.append(f"{kind} a y={r.y0:.1f}: dy={dy:.1f} dh={dh:.1f} dx0={dx0:.1f} dx1={dx1:.1f}")
    return errors


@pytest.mark.skipif(not REF.is_file(), reason="PDF del committente assente: il banco gira solo in locale")
def test_banco_strutturale_pagine_4_6_7():
    pdf = render_business_plan(load_json(FIXTURE), only=tuple(PAGINE))
    new = fitz.open(stream=pdf, filetype="pdf")
    ref = fitz.open(REF)
    assert new.page_count == 3
    problemi = {sec: confronta(ref[p - 1], new[i]) for i, (sec, p) in enumerate(PAGINE.items())}
    assert not any(problemi.values()), problemi


@pytest.mark.skipif(not REF.is_file(), reason="PDF del committente assente")
def test_banco_testi_chiave():
    new = fitz.open(stream=render_business_plan(load_json(FIXTURE), only=tuple(PAGINE)), filetype="pdf")
    t4, t6, t7 = (new[i].get_text() for i in range(3))
    for s in ("SEZIONE 2", "Evoluzione economica dell'impresa", "€ 4,67 mln", "Conto economico di sintesi",
              "4.109.510", "−45.192", "EBITDA (MOL)"):
        assert s in t4, s
    for s in ("SEZIONE 4", "€ 1,83 mln", "14,39%", "Margine di contribuzione", "4.286.693"):
        assert s in t6, s
    for s in ("SEZIONE 5", "€ 1,07 mln", "−€ 150 mila", "−€ 210 mila", "€ 804,3 mila", "Flusso di cassa operativo (A)"):
        assert s in t7, s
