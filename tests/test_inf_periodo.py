"""Rilievo 2 della revisione finale: il documento non dà per scontato un semestre. Varianti del banco AMBIENTA a 3 e
12 mesi, con e senza forecast: nessun «semestre», intestazioni «NM / C», niente annualizzato dove non c'è."""
import dataclasses
from pathlib import Path

import fitz
import pytest

from app.renderers.infrannuale.data import ANNUALIZZATO, PROIEZIONE, load_json
from app.renderers.infrannuale.document import render_infrannuale

BANCO = Path(__file__).parent / "fixtures" / "infrannuale" / "banco_ambienta.json"


def _senza(d, *tolte):
    """Toglie colonne da CE/SP e dalle righe d'allegato, che sono allineate alle colonne."""
    def cut(cols, rows):
        keep = [i for i, c in enumerate(cols) if c.key not in tolte]
        return (tuple(cols[i] for i in keep),
                tuple(dataclasses.replace(r, values=tuple(r.values[i] for i in keep)) for r in rows))
    ce, ace = cut(d.ce_cols, d.annex_ce)
    sp, asp = cut(d.sp_cols, d.annex_sp)
    return dataclasses.replace(d, ce_cols=ce, sp_cols=sp, annex_ce=ace, annex_sp=asp,
                               crisi={k: v for k, v in d.crisi.items() if k not in tolte})


def _testo(d):
    pdf = fitz.open(stream=render_infrannuale(d), filetype="pdf")
    return [" ".join(p.get_text().split()) for p in pdf]


@pytest.fixture(scope="module")
def base():
    return load_json(BANCO)


@pytest.mark.parametrize("mesi,tolte", [(3, ()), (3, (PROIEZIONE,)), (9, ()), (12, (ANNUALIZZATO, PROIEZIONE))])
def test_nessun_semestre_fuori_dai_sei_mesi(base, mesi, tolte):
    d = _senza(dataclasses.replace(base, period_months=mesi), *tolte)
    pagine = _testo(d)
    tutto = " ".join(pagine)
    assert "semestre" not in tutto
    assert "6M / C" not in tutto and "nel nel" not in tutto
    if PROIEZIONE in tolte:
        assert f"{mesi}M / C" in tutto
        assert "e del forecast" not in tutto
    if ANNUALIZZATO in tolte:
        assert "annualizzat" not in tutto
        allegato_a = next(p for p in pagine if "ALLEGATO A" in p)
        assert "F / C" not in allegato_a and "Ann. / C" not in allegato_a


def test_sei_mesi_resta_semestre(base):
    assert "semestre" in " ".join(_testo(base))
