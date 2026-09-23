"""Documento completo sui bilanci veri (DB locale copiato): tre workflow, indice coerente, nessuna eccezione."""
import fitz
import pytest

from app.renderers.business_plan.document import render_business_plan
from tests.test_bp_data import _data, db  # noqa: F401  (fixture condivisa)


@pytest.mark.parametrize("caso", ["infrannuale", "bilancio", "startup"])
def test_documento_completo(db, caso):  # noqa: F811
    data = _data(db, caso)
    pdf = fitz.open(stream=render_business_plan(data), filetype="pdf")
    assert pdf.page_count >= 12
    cover = pdf[0].get_text()
    assert data.company_name in cover and "I numeri chiave del piano" in cover and "Indice" in cover
    # l'indice punta alla pagina dove il titolo compare davvero
    for title, page in _index_entries(pdf[0]):
        assert title.split(" · ")[0][:25] in pdf[page - 1].get_text(), (title, page)


def _index_entries(page):
    """Righe «N  Titolo … pagina» dell'indice in copertina."""
    words = page.get_text("words")
    lines = {}
    for x0, y0, x1, y1, w, *_ in words:
        if y0 > 500:
            lines.setdefault(round(y0), []).append((x0, w))
    out = []
    for _, ws in sorted(lines.items()):
        ws.sort()
        if len(ws) >= 3 and ws[-1][1].isdigit() and ws[0][1].isdigit():
            out.append((" ".join(w for _, w in ws[1:-1]), int(ws[-1][1])))
    return out


def test_sezione_uno_ambienta(db):  # noqa: F811
    pdf = fitz.open(stream=render_business_plan(_data(db, "infrannuale")), filetype="pdf")
    testi = [p.get_text() for p in pdf]
    # la sintesi sta in una pagina, come nel riferimento; forza/debolezza/azioni nella successiva
    i = next(n for n, t in enumerate(testi) if "Punti chiave del piano" in t)
    assert "Cruscotto degli indicatori" in testi[i]
    assert all(s in testi[i + 1] for s in ("Punti di forza", "Punti di debolezza", "Azioni prioritarie"))
