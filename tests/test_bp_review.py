"""Rilievi della revisione finale del branch: ogni test riproduce un difetto visto su una pratica vera."""
import dataclasses
from decimal import Decimal as D
from pathlib import Path

import fitz

from app.renderers.business_plan import fmt, narrative
from app.renderers.business_plan.data import load_json
from app.renderers.business_plan.document import render_business_plan
from app.renderers.business_plan.theme import LM, PAGE_W

BANCO = Path(__file__).parent / "fixtures/business_plan/banco_ambienta.json"
LUNGO = "SOCIETÀ COOPERATIVA AGRICOLA E ZOOTECNICA DEL MEDIO CAMPIDANO & FIGLI S.R.L. IN LIQUIDAZIONE"


def _banco(**kw):
    return dataclasses.replace(load_json(BANCO), **kw)


def test_nome_lungo_non_esce_dalla_copertina_ne_si_sovrappone_nell_intestazione():
    pdf = fitz.open(stream=render_business_plan(_banco(company_name=LUNGO, draft=True),
                                                only=("copertina", "economia")), filetype="pdf")
    for x0, y0, x1, y1, w, *_ in pdf[0].get_text("words"):
        assert x1 <= PAGE_W - LM + 1, (w, x1)
    head = [wd for wd in pdf[1].get_text("words") if wd[1] < 31]
    nome = [wd for wd in head if wd[0] < PAGE_W / 2 - 60]
    destra = [wd for wd in head if wd[4] in ("Piano", "BOZZA")]
    assert max(wd[2] for wd in nome) < min(wd[0] for wd in destra) - 6


def test_crescita_dichiarata_incoerente_coi_ricavi_non_si_stampa():
    # startup: ricavi forzati da 50.000 a 120.000 con crescita dichiarata 0/0/0
    d = _banco(values={**load_json(BANCO).values, "ricavi": (D("50000"), D("80000"), D("100000"), D("120000"))},
               growth={"revenue_growth_pct": (D(0), D(0), D(0))})
    assert narrative.growth_list(d, "revenue_growth_pct") is None
    assert "ipotesi di crescita" not in narrative.key_points(d)[0][1]


def test_crescita_coerente_resta():
    d = load_json(BANCO)
    assert narrative.growth_list(d, "revenue_growth_pct") == "5% / 6% / 1%"


def test_zero_vuole_lo():
    assert fmt.prep("del", "0%") == "dello 0%"
    assert fmt.prep("dal", "0%") == "dallo 0%"
    assert fmt.prep("al", "0,5%") == "allo 0,5%"


def test_minimo_dscr_mai_arrotondato_per_eccesso():
    assert fmt.floor_ratio(D("1.26"), 1) == "1,2×"
    assert fmt.floor_ratio(D("-0.34"), 1) == "−0,4×"


def test_periodo_del_piano_senza_doppio_piano():
    from app.renderers.business_plan.sections_sintesi import _cover_kpis
    d = load_json(BANCO)
    one = dataclasses.replace(d, columns=d.columns[:2], values={k: v[:2] for k, v in d.values.items()})
    testi = " ".join(str(x) for row in _cover_kpis(one) for x in row)
    assert "piano di piano" not in testi


def test_aree_del_piano_non_lasciano_una_riga_orfana():
    from reportlab.platypus import KeepTogether
    from app.renderers.business_plan.sections_partenza import ipotesi
    flow = ipotesi(load_json(BANCO), {})
    assert isinstance(flow[-1], KeepTogether)


def test_allegato_d_non_nomina_la_colonna_r_se_manca():
    from app.renderers.business_plan.sections_allegati import allegato_d
    d = load_json(BANCO)
    d = dataclasses.replace(d, indicators_practice_headers=tuple(c.label for c in d.columns))
    testo = " ".join(getattr(f, "text", "") for f in allegato_d(d, {}))
    assert "progressivo rettificato" not in testo


def test_override_dei_ricavi_spegne_la_crescita_anche_se_i_numeri_tornano():
    d = _banco(revenue_overridden=True)
    assert narrative.growth_list(d, "revenue_growth_pct") is None
