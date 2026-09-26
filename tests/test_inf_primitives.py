"""Primitive condivise nuove: il riquadro KPI col bollino del report infrannuale (misure del riferimento, p. 4)."""
import io

import fitz
from reportlab.platypus import SimpleDocTemplate

from app.renderers.business_plan import layout, theme


def test_tiles_chip_misure_del_riferimento():
    theme.register_fonts()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=(theme.PAGE_W, theme.PAGE_H), leftMargin=theme.LM, rightMargin=theme.LM,
                            topMargin=128, bottomMargin=40)
    doc.build([layout.tiles_chip([("6M 2026", "€ 2,10 mln", "Ricavi del semestre", "EBITDA € 82,2 mila")] * 4)])
    p = fitz.open(stream=buf.getvalue(), filetype="pdf")[0]
    fills = sorted((d["rect"] for d in p.get_drawings() if d.get("fill")), key=lambda r: (r.y0, r.x0))
    tiles = [r for r in fills if abs(r.width - 118.3) < 1]
    chips = [r for r in fills if abs(r.height - 13.5) < 0.3]
    assert len(tiles) == 4 and len(chips) == 4
    assert abs(tiles[0].height - 65.8) < 0.6          # 128,0–193,8 nel riferimento
    assert abs(chips[0].y0 - tiles[0].y0 - 6.0) < 0.5  # bollino a 6 pt dal bordo
