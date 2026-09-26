"""Documento completo sui bilanci veri (DB locale copiato): 13 pagine su AMBIENTA, indice coerente, tutte le pratiche
infrannuali senza eccezioni."""
import fitz
import pytest

from app.renderers.infrannuale.document import render_infrannuale
from tests.test_inf_data import _data, db  # noqa: F401  (fixture condivisa)

SCENARI_INFRANNUALI = (1, 3, 4, 5, 17, 19, 21, 23)


def _index_entries(page):
    """Righe «N  Titolo … pagina» dell'indice in copertina."""
    lines = {}
    for x0, y0, x1, y1, w, *_ in page.get_text("words"):
        if y0 > 500:
            lines.setdefault(round(y0), []).append((x0, w))
    out = []
    for _, ws in sorted(lines.items()):
        ws.sort()
        if len(ws) >= 2 and ws[-1][1].isdigit():
            title = " ".join(w for _, w in ws[1:-1]) if ws[0][1].isdigit() else " ".join(w for _, w in ws[:-1])
            out.append((title, int(ws[-1][1])))
    return out


def test_ambienta_tredici_pagine_e_indice(db):  # noqa: F811
    pdf = fitz.open(stream=render_infrannuale(_data(db, 17)), filetype="pdf")
    assert pdf.page_count == 13
    cover = pdf[0].get_text()
    assert "AMBIENTA" in cover and "I numeri chiave" in cover and "D · Crisi" in cover and "Indice" in cover
    voci = _index_entries(pdf[0])
    assert len(voci) == 9, voci
    for title, page in voci:
        atteso = "ALLEGATO A" if title.startswith("Allegati") else title.split(" · ")[0][:20]
        assert atteso in pdf[page - 1].get_text().replace("\n", " "), (title, page)


def test_ambienta_cifre_del_riferimento(db):  # noqa: F811
    pdf = fitz.open(stream=render_infrannuale(_data(db, 17)), filetype="pdf")
    testo = [p.get_text() for p in pdf]
    for pagina, cifre in ((2, ("4.109.510", "852.261", "5,794×", "C2 · Rischio grave", "9 su 14")),
                          (4, ("4.209.510", "−22.596", "1.224,51%")),
                          (6, ("997.441", "808,30%")),
                          (8, ("493.409", "467.529", "36.504", "27,25%")),
                          (9, ("3,026×", "attenzione"))):
        for c in cifre:
            assert c in testo[pagina - 1], (pagina, c)


@pytest.mark.parametrize("scenario", SCENARI_INFRANNUALI)
def test_tutte_le_pratiche_infrannuali(db, scenario):  # noqa: F811
    try:
        d = _data(db, scenario)
    except ValueError as e:  # bilanci del periodo mancanti: la rotta risponde 400, il renderer non entra
        pytest.skip(f"scenario {scenario} incompleto nel DB locale: {e}")
    pdf = fitz.open(stream=render_infrannuale(d), filetype="pdf")
    assert pdf.page_count >= 11
    if not d.has_forecast:
        assert "forecast non ancora generato" in pdf[0].get_text()
