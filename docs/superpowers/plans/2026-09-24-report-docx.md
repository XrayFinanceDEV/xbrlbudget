# Export Word dei report ReportLab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** «Scarica Word» accanto a «Scarica PDF» per il Business plan (/report) e il report infrannuale (Stampa), con testi e tabelle modificabili.

**Architecture:** un traduttore unico `backend/app/renderers/docx_export.py` converte in `python-docx` gli stessi flowable ReportLab che le sezioni già producono; copertina e intestazioni escono da funzioni di testo condivise col PDF. Due rotte `/docx` gemelle delle `/pdf`, due funzioni api e un hook generico nel frontend.

**Tech Stack:** python-docx 1.2.0, ReportLab 4.2.5, FastAPI, Next.js 15 / Vitest.

**Spec:** `docs/superpowers/specs/2026-09-24-report-docx-design.md`

## Global Constraints

- Lavoro nel worktree `/home/peter/DEV/budget-report-docx` (branch `feat/report-docx`); mai nell'albero principale.
- Python: `PY=/home/peter/DEV/budget/backend/venv/bin/python`, test da `backend/`.
- I test leggono solo una **copia** di `/home/peter/DEV/budget/financial_analysis.db`; senza DB si saltano.
- Il PDF non cambia: `test_bp_*` e `test_inf_*` (banchi compresi) restano verdi a ogni task.
- `lib/api.ts` ha fine riga misti, `StampaContent.tsx` è CRLF: solo modifiche additive che preservano i fine riga; `git diff --stat` prima di ogni commit.
- Un flowable sconosciuto fa fallire la traduzione (`TypeError`), mai un salto silenzioso.
- Nessuna AI e nessuna scrittura sul DB nelle rotte nuove.
- UI in italiano, «Scarica Word».

## Review Focus

1. **Paragrafo col markup** (`<b>`, `<font color>`, `&nbsp;`, `&amp;`, `<br/>`): il testo in Word è identico a quello del PDF, nessuna entità letterale. → test unità Task 1.
2. **Tabelle annidate e liste in cella** (riquadri KPI, pannelli «Lettura», schede): nessun testo perso. → test di completezza Task 2.
3. **Scenari fuori dal banco** (D2M negativo, AIC 9M/12M, infrannuale senza forecast): il Word esce e contiene tutto. → Task 2 parametrizzato su 3, 5, 23.
4. **Rotta su scenario altrui / non infrannuale / campo in più**: 404/400/422 come la PDF. → Task 3.
5. **Il dossier Typst** non mostra «Scarica Word» su /report. → Task 4 (`wordAvailable`).

---

### Task 1: Il traduttore dei flowable

**Files:**
- Create: `backend/app/renderers/docx_export.py`
- Modify: `backend/app/renderers/business_plan/layout.py` (`chart` conserva il PNG)
- Modify: `backend/requirements.txt` (`python-docx==1.2.0`)
- Test: `tests/test_docx_export.py`

**Interfaces:**
- Produces: `docx_export.translate(container, flowables: list) -> None`; `docx_export.docx_text(data: bytes) -> list[str]` (testi di tutti i paragrafi, celle comprese, normalizzati negli spazi); `docx_export.CoverLines(eyebrow, name, title, lines)`; `docx_export.build(sections: list[list], *, cover: CoverLines, header_left, header_right, footer, title) -> bytes`.
- `layout.chart(...)` restituisce un `Image` con attributo `png: bytes`.

- [ ] **Step 1: test che falliscono**

```python
"""Traduttore ReportLab → Word: markup, tabelle, immagini, sconosciuti (spec 2026-09-24 §2.1)."""
import io
import pytest
from docx import Document
from reportlab.platypus import Flowable, Image, PageBreak, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.colors import HexColor

from app.renderers import docx_export as dx
from app.renderers.business_plan import layout, theme


def _doc(flowables):
    theme.register_fonts()
    d = Document()
    dx.translate(d, flowables)
    buf = io.BytesIO(); d.save(buf)
    return buf.getvalue()


def test_markup_del_paragrafo():
    p = Paragraph("<font color='#2a9d8f'>•</font>&nbsp;&nbsp;<b>Ricavi.</b> testo &amp; altro<br/>riga due",
                  layout.ST["body"])
    doc = Document(io.BytesIO(_doc([p])))
    par = doc.paragraphs[-1]
    assert par.text == "•\xa0\xa0Ricavi. testo & altro\nriga due"
    bold = [r.text for r in par.runs if r.bold]
    assert bold == ["Ricavi."]
    assert str(par.runs[0].font.color.rgb) == "2A9D8F"


def test_tabella_sfondi_intestazione_e_annidata():
    t = layout.fin_table(["2025", "2026"], [("Ricavi", ["1.000", "2.000"], ""), ("EBITDA", ["10", "20"], "hl")])
    tiles = layout.tiles([("€ 1 mln", "Ricavi", "+5%"), ("€ 2 mln", "EBITDA", "+1%")])
    doc = Document(io.BytesIO(_doc([t, tiles])))
    ft = doc.tables[0]
    assert [c.text for c in ft.rows[0].cells] == ["Voce (euro)", "2025", "2026"]
    assert ft.rows[0]._tr.trPr is not None and ft.rows[0]._tr.trPr.find(dx.qn("w:tblHeader")) is not None
    shd = ft.rows[2].cells[0]._tc.tcPr.find(dx.qn("w:shd"))
    assert shd.get(dx.qn("w:fill")).lower() == theme.HL[1:]
    testi = dx.docx_text(_doc([tiles]))
    assert "€ 1 mln" in testi and "EBITDA" in testi and "+1%" in testi


def test_immagine_e_interruzioni():
    from app.renderers.infrannuale import charts
    img = layout.chart(charts.crisi(["a"], [3], 14, ["D · Crisi"]), 2.4)
    assert img.png.startswith(b"\x89PNG")
    doc = Document(io.BytesIO(_doc([img, Spacer(0, 5), PageBreak(), Paragraph("dopo", layout.ST["body"])])))
    assert len(doc.inline_shapes) == 1
    assert abs(doc.inline_shapes[0].width.pt - img.drawWidth) < 1


def test_flowable_sconosciuto_non_passa_in_silenzio():
    class Strano(Flowable):
        def wrap(self, *a): return 0, 0
    with pytest.raises(TypeError, match="Strano"):
        _doc([Strano()])
```

- [ ] **Step 2: eseguire — FAIL** `cd backend && $PY -m pytest ../tests/test_docx_export.py -q` → `ModuleNotFoundError: app.renderers.docx_export`.

- [ ] **Step 3: implementazione**

`layout.chart`: dopo `img.hAlign = "CENTER"` aggiungere `img.png = png  # il Word riusa il PNG del grafico, non l'immagine già decodificata`.

`requirements.txt`: riga `python-docx==1.2.0` accanto a `reportlab==4.2.5`.

`docx_export.py`:

```python
"""Word (.docx) dei report ReportLab: traduce i flowable delle sezioni, non ne riscrive il contenuto.

Spec 2026-09-24 §2. Le sezioni restano l'unica fonte dei testi: un testo corretto nel codice cambia PDF e Word
insieme. Un flowable che il traduttore non conosce fa fallire la traduzione: una sezione che perde un pezzo nel Word
senza dirlo è il difetto da non avere.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from reportlab.platypus import CondPageBreak, Image, KeepTogether, NextPageTemplate, PageBreak, Paragraph, Spacer, Table

from app.renderers.business_plan import theme

FONT = "Lato"
_ALIGN = {0: WD_ALIGN_PARAGRAPH.LEFT, 1: WD_ALIGN_PARAGRAPH.CENTER, 2: WD_ALIGN_PARAGRAPH.RIGHT,
          4: WD_ALIGN_PARAGRAPH.JUSTIFY, "LEFT": WD_ALIGN_PARAGRAPH.LEFT, "CENTER": WD_ALIGN_PARAGRAPH.CENTER,
          "CENTRE": WD_ALIGN_PARAGRAPH.CENTER, "RIGHT": WD_ALIGN_PARAGRAPH.RIGHT}
_IGNORATI = (NextPageTemplate, CondPageBreak)


@dataclass(frozen=True)
class CoverLines:
    """I testi della fascia di copertina, gli stessi che `draw_cover_band` disegna nel PDF."""
    eyebrow: str
    name: str
    title: str
    lines: tuple


def _hex(color) -> str | None:
    if color is None or getattr(color, "alpha", 1) == 0:
        return None
    return color.hexval()[2:].upper().rjust(6, "0")


def _font(run, name: str, size: float, color, bold: bool) -> None:
    run.font.name = FONT
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.bold = bold or "Bold" in (name or "")
    hx = _hex(color)
    if hx:
        run.font.color.rgb = RGBColor.from_string(hx)


def _new_paragraph(container, state):
    p = container.add_paragraph()
    pf = p.paragraph_format
    pf.space_before, pf.space_after = Pt(0), Pt(0)
    state["last"] = p
    return p


def _paragraph(container, para: Paragraph, state) -> None:
    p = _new_paragraph(container, state)
    st = para.style
    p.alignment = _ALIGN.get(st.alignment, WD_ALIGN_PARAGRAPH.LEFT)
    if st.leftIndent:
        p.paragraph_format.left_indent = Pt(st.leftIndent)
    for fr in para.frags:
        if getattr(fr, "lineBreak", False):
            p.add_run().add_break()
            continue
        if fr.text:
            _font(p.add_run(fr.text), fr.fontName, fr.fontSize, fr.textColor, False)


def _norm(i: int, n: int) -> int:
    return i + n if i < 0 else i


def _cells(cmd, nrows, ncols):
    (c0, r0), (c1, r1) = cmd[1], cmd[2]
    c0, c1, r0, r1 = _norm(c0, ncols), _norm(c1, ncols), _norm(r0, nrows), _norm(r1, nrows)
    return [(r, c) for r in range(r0, min(r1, nrows - 1) + 1) for c in range(c0, min(c1, ncols - 1) + 1)]


def _shade(cell, hx: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"), shd.set(qn("w:color"), "auto"), shd.set(qn("w:fill"), hx)
    cell._tc.get_or_add_tcPr().append(shd)


def _border(cell, side: str, width: float, hx: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcPr.append(borders)
    b = OxmlElement(f"w:{side}")
    b.set(qn("w:val"), "single"), b.set(qn("w:sz"), str(max(2, round(width * 8)))), b.set(qn("w:color"), hx)
    borders.append(b)


_LATI = {"LINEABOVE": "top", "LINEBELOW": "bottom", "LINEBEFORE": "left", "LINEAFTER": "right"}


def _table(container, t: Table, state) -> None:
    nrows, ncols = t._nrows, t._ncols
    wt = container.add_table(rows=nrows, cols=ncols)
    wt.alignment = WD_TABLE_ALIGNMENT.CENTER
    wt.autofit = False
    widths = [w if isinstance(w, (int, float)) else None for w in t._colWidths]
    free = [i for i, w in enumerate(widths) if w is None]
    if free:
        rest = max(theme.CW - sum(w for w in widths if w), 20)
        for i in free:
            widths[i] = rest / len(free)
    for r in range(nrows):
        for c in range(ncols):
            wt.cell(r, c).width = Pt(widths[c])
    for cmd in t._bkgrndcmds:
        if cmd[0] == "BACKGROUND" and _hex(cmd[3]):
            for r, c in _cells(cmd, nrows, ncols):
                _shade(wt.cell(r, c), _hex(cmd[3]))
    for cmd in t._linecmds:
        side = _LATI.get(cmd[0])
        if side and _hex(cmd[4]):
            for r, c in _cells(cmd, nrows, ncols):
                _border(wt.cell(r, c), side, cmd[3], _hex(cmd[4]))
    for r in range(min(t.repeatRows or 0, nrows)):
        trPr = wt.rows[r]._tr.get_or_add_trPr()
        trPr.append(OxmlElement("w:tblHeader"))
    anchors = {}
    for cmd in t._spanCmds:
        cells = _cells(cmd, nrows, ncols)
        if len(cells) > 1:
            (r0, c0), (r1, c1) = cells[0], cells[-1]
            wt.cell(r0, c0).merge(wt.cell(r1, c1))
            anchors.update({rc: rc == (r0, c0) for rc in cells})
    for r, row in enumerate(t._cellvalues):
        for c, value in enumerate(row):
            if anchors.get((r, c)) is False:
                continue
            cell = wt.cell(r, c)
            _cell(cell, value, t._cellStyles[r][c], state)
    state["last"] = None


def _cell(cell, value, cs, state) -> None:
    first = cell.paragraphs[0]
    inner = {"last": None}
    items = value if isinstance(value, (list, tuple)) else [value]
    for v in items:
        if isinstance(v, str):
            if v:
                p = _new_paragraph(cell, inner)
                p.alignment = _ALIGN.get(cs.alignment, WD_ALIGN_PARAGRAPH.LEFT)
                _font(p.add_run(v), cs.fontname, cs.fontsize, cs.color, False)
        elif v is not None:
            translate(cell, [v], inner)
    if len(cell.paragraphs) > 1 and not first.text and not first.runs:
        first._element.getparent().remove(first._element)  # la cella nasce con un paragrafo vuoto


def _image(container, img: Image, state) -> None:
    png = getattr(img, "png", None)
    if png is None:
        raise TypeError("immagine senza PNG: i grafici passano da layout.chart")
    p = _new_paragraph(container, state)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(io.BytesIO(png), width=Pt(img.drawWidth))


def translate(container, flowables, state: dict | None = None) -> None:
    """Scrive i flowable in `container` (il documento o una cella)."""
    state = state if state is not None else {"last": None}
    for f in flowables:
        if isinstance(f, Paragraph):
            _paragraph(container, f, state)
        elif isinstance(f, Table):
            _table(container, f, state)
        elif isinstance(f, Image):
            _image(container, f, state)
        elif isinstance(f, Spacer):
            if state.get("last") is not None:
                pf = state["last"].paragraph_format
                pf.space_after = Pt((pf.space_after.pt if pf.space_after else 0) + f.height)
        elif isinstance(f, PageBreak):
            _new_paragraph(container, state).add_run().add_break(WD_BREAK.PAGE)
            state["last"] = None
        elif isinstance(f, KeepTogether):
            translate(container, f._content, state)
        elif callable(getattr(f, "make", None)):  # tabella che nel PDF si stringe per stare in pagina
            translate(container, [f.make(1.0)], state)
        elif isinstance(f, _IGNORATI) or type(f).__name__ == "SectionStart":
            continue
        else:
            raise TypeError(f"flowable non tradotto in Word: {type(f).__name__}")


def docx_text(data: bytes) -> list:
    """I testi di tutti i paragrafi del corpo, celle annidate comprese, con gli spazi normalizzati."""
    doc = Document(io.BytesIO(data))
    out = []
    for p in doc.element.body.iter(qn("w:p")):
        txt = "".join(t.text or "" for t in p.iter(qn("w:t")))
        txt = re.sub(r"\s+", " ", txt.replace("\xa0", " ")).strip()
        if txt:
            out.append(txt)
    return out
```

(`build` arriva nel Task 2.)

- [ ] **Step 4: eseguire — PASS** `cd backend && $PY -m pytest ../tests/test_docx_export.py -q` → 4 passed. Poi `$PY -m pytest ../tests/test_bp_*.py ../tests/test_inf_*.py -q` → verdi (il PDF non cambia).

- [ ] **Step 5: commit** `feat(report-docx): traduttore dei flowable ReportLab in Word`.

---

### Task 2: Documento Word dei due report (copertina, intestazione, completezza)

**Files:**
- Modify: `backend/app/renderers/docx_export.py` (`build`)
- Modify: `backend/app/renderers/business_plan/sections_sintesi.py` (`cover_lines`, `draw_cover_band` la usa)
- Modify: `backend/app/renderers/business_plan/document.py` (`page_texts`, `render_business_plan_docx`)
- Modify: `backend/app/renderers/infrannuale/sections_sintesi.py`, `backend/app/renderers/infrannuale/document.py` (idem, `render_infrannuale_docx`)
- Test: `tests/test_docx_report.py`

**Interfaces:**
- Consumes: `translate`, `docx_text`, `CoverLines` (Task 1).
- Produces: `render_business_plan_docx(data: BusinessPlanData) -> bytes`, `render_infrannuale_docx(data: InfrannualeData) -> bytes`; `page_texts(data) -> tuple[str, str, str]` (sinistra, destra, piè) in entrambi i `document.py`.

- [ ] **Step 1: test che falliscono**

```python
"""Il Word contiene tutto il PDF: ogni riga di testo del PDF, tolte intestazioni, piè e numeri di pagina, si trova
nel .docx; i grafici ci sono tutti (spec 2026-09-24 §5)."""
import io
import re

import fitz
import pytest
from docx import Document

from app.renderers.docx_export import docx_text
from tests.test_inf_data import _data, db  # noqa: F401  (fixture condivisa)


def _norm(s):
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def _manca(pdf: bytes, docx: bytes, salta: set) -> list:
    corpus = "\n".join(docx_text(docx))
    mancanti = []
    for n, page in enumerate(fitz.open(stream=pdf, filetype="pdf"), start=1):
        for line in page.get_text().splitlines():
            t = _norm(line)
            if not t or t.isdigit() or t in salta or t.endswith("…"):
                continue
            if t not in corpus:
                mancanti.append((n, t))
    return mancanti


def _controlla(pdf, docx, page_texts, n_grafici):
    left, right, foot = page_texts
    salta = {_norm(left), _norm(right), _norm(foot), "Riservato e confidenziale"}
    assert _manca(pdf, docx, salta) == []
    doc = Document(io.BytesIO(docx))
    assert len(doc.inline_shapes) == n_grafici
    assert doc.sections[0].different_first_page_header_footer
    assert _norm(right) in _norm(doc.sections[0].header.paragraphs[0].text)


@pytest.mark.parametrize("scenario", (17, 23, 3, 5))
def test_infrannuale_word_completo(db, scenario):  # noqa: F811
    from app.renderers.infrannuale.document import page_texts, render_infrannuale, render_infrannuale_docx
    try:
        d = _data(db, scenario)
    except ValueError as e:
        pytest.skip(f"scenario {scenario} incompleto nel DB locale: {e}")
    pdf = render_infrannuale(d)
    n = sum(len(p.get_images()) for p in fitz.open(stream=pdf, filetype="pdf"))
    _controlla(pdf, render_infrannuale_docx(d), page_texts(d), n)


def test_business_plan_word_completo(db):  # noqa: F811
    from database.models import BudgetScenario
    from app.renderers.business_plan import from_report, render_business_plan
    from app.renderers.business_plan.document import page_texts, render_business_plan_docx
    from app.services.final_report_service import assemble_final_report
    sc = db.query(BudgetScenario).filter(BudgetScenario.company_id == 575,
                                         BudgetScenario.scenario_type != "infrannuale").first()
    if sc is None:
        pytest.skip("nessuno scenario budget per AMBIENTA")
    d = from_report(assemble_final_report(db, 575, sc.id, schema_version=2), draft=True)
    pdf = render_business_plan(d)
    n = sum(len(p.get_images()) for p in fitz.open(stream=pdf, filetype="pdf"))
    docx = render_business_plan_docx(d)
    _controlla(pdf, docx, page_texts(d), n)
    assert "BOZZA" in Document(io.BytesIO(docx)).sections[0].header.paragraphs[0].text


def test_indice_senza_numeri_di_pagina(db):  # noqa: F811
    from app.renderers.infrannuale.document import render_infrannuale_docx
    doc = Document(io.BytesIO(render_infrannuale_docx(_data(db, 17))))
    indice = next(t for t in doc.tables if any("Segnali extracontabili" in c.text for c in t.columns[1].cells))
    assert all(not c.text.strip() for c in indice.columns[2].cells)
```

- [ ] **Step 2: eseguire — FAIL** (`ImportError: page_texts`).

- [ ] **Step 3: implementazione**

In `docx_export.py`, `build`:

```python
def _page_field(p) -> None:
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        r = p.add_run()
        if kind:
            el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), kind)
        else:
            el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = text
        r._element.append(el)
        _font(r, "", 7.8, None, False)


def _two_sided(p, left: str, right: str, size: float, color: str, bold_left: bool, page: bool = False) -> None:
    p.paragraph_format.tab_stops.add_tab_stop(Pt(theme.CW), WD_TAB_ALIGNMENT.RIGHT)
    c = RGBColor.from_string(color[1:])
    r = p.add_run(left); _font(r, "", size, None, bold_left); r.font.color.rgb = c
    r = p.add_run("\t" + right); _font(r, "", size, None, False); r.font.color.rgb = c
    if page:
        _page_field(p)


def _cover(doc, cover: CoverLines) -> None:
    band = doc.add_table(rows=1, cols=1)
    cell = band.cell(0, 0)
    cell.width = Pt(theme.CW)
    _shade(cell, theme.NAVY[1:])
    _border(cell, "bottom", 5.6, theme.TEAL[1:])
    white = RGBColor(0xFF, 0xFF, 0xFF)
    first = True
    for text, size, bold, color, after in ((cover.eyebrow, 10, True, white, 18), (cover.name, 30, True, white, 6),
                                          (cover.title, 21, False, white, 14)) + tuple(
            (line, 11, False, RGBColor.from_string(theme.COVER_SUB[1:]), 4) for line in cover.lines):
        p = cell.paragraphs[0] if first else cell.add_paragraph()
        first = False
        p.paragraph_format.space_after = Pt(after)
        r = p.add_run(text); _font(r, "", size, None, bold); r.font.color.rgb = color
    doc.add_paragraph().paragraph_format.space_after = Pt(12)


def build(sections: list, *, cover: CoverLines, header_left: str, header_right: str, footer: str,
          title: str) -> bytes:
    """Documento A4 coi margini del PDF: fascia di copertina, poi una sezione per pagina."""
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = FONT, Pt(9.3)
    normal.paragraph_format.space_after = Pt(0)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Pt(theme.PAGE_W), Pt(theme.PAGE_H)
    sec.left_margin = sec.right_margin = Pt(theme.LM)
    sec.top_margin, sec.bottom_margin = Pt(55), Pt(40)
    sec.header_distance, sec.footer_distance = Pt(14), Pt(16)
    sec.different_first_page_header_footer = True
    _two_sided(sec.header.paragraphs[0], header_left, header_right, 9, theme.NAVY, True)
    _two_sided(sec.footer.paragraphs[0], footer, "", 7.8, theme.MUTED, False, page=True)
    _two_sided(sec.first_page_footer.paragraphs[0], "Riservato e confidenziale", "", 7.8, theme.MUTED, False)
    doc._body._body.remove(doc.paragraphs[0]._element)  # il documento vuoto nasce con un paragrafo
    _cover(doc, cover)
    for n, flowables in enumerate(sections):
        if n > 0:
            doc.add_page_break()
        translate(doc, flowables)
    doc.core_properties.title, doc.core_properties.author = title, ""
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

In `business_plan/sections_sintesi.py`: nuova `cover_lines(data) -> CoverLines` con eyebrow `f"REPORT DI BUDGET {_years(data)}" + (" · BOZZA" if data.draft else "")`, name `data.company_name`, title `f"Piano economico-finanziario {_years(data)}"`, lines `(data.base_description, "Andamento economico, flussi di cassa, sostenibilità del debito e circolante")`; `draw_cover_band` legge quei quattro campi invece delle stringhe (stesse coordinate).

In `business_plan/document.py`:

```python
def page_texts(data: BusinessPlanData) -> tuple:
    """Intestazione sinistra, destra e piè di pagina: gli stessi nel PDF e nel Word."""
    return (data.company_name, header_title(data) + (" · BOZZA" if data.draft else ""),
            f"Riservato e confidenziale · {legend(data)}")


def render_business_plan_docx(data: BusinessPlanData) -> bytes:
    """Lo stesso Business plan in Word (spec 2026-09-24): stesse sezioni, indice senza numeri di pagina."""
    from app.renderers import docx_export
    from .sections_sintesi import cover_lines
    theme.register_fonts()
    left, right, foot = page_texts(data)
    return docx_export.build([s.build(data, {}) for s in SECTIONS], cover=cover_lines(data), header_left=left,
                             header_right=right, footer=foot, title=f"{data.company_name} – {header_title(data)}")
```

e `_body_page` usa `right`, `foot` da `page_texts(data)` (stesso testo di oggi).

Infrannuale: stessa forma — `cover_lines(d)` con eyebrow `f"REPORT INFRANNUALE {d.partial_label}"`, title `f"Situazione al {d.period_end}" + (" e forecast a fine anno" if d.has_forecast else "")`, le due righe della fascia; `page_texts(d) = (d.company_name, d.header_title, f"Riservato e confidenziale · {d.legend}")`; `render_infrannuale_docx(d)` come sopra con title `f"{d.company_name} – {d.header_title}"`.

- [ ] **Step 4: eseguire — PASS** `$PY -m pytest ../tests/test_docx_report.py ../tests/test_docx_export.py -q` → verdi (scenari assenti saltati). Poi banchi: `$PY -m pytest ../tests/test_bp_*.py ../tests/test_inf_*.py -q` → verdi.

- [ ] **Step 5: commit** `feat(report-docx): Word di Business plan e infrannuale con copertina e intestazioni`.

---

### Task 3: Servizi e rotte `/docx`

**Files:**
- Modify: `backend/app/services/business_plan_pdf_service.py`, `backend/app/services/infrannuale_pdf_service.py` (`render_docx`, nomi con estensione)
- Modify: `backend/app/api/v1/reports.py`, `backend/app/api/v1/intermedio_report.py`
- Test: `tests/test_docx_endpoint.py`

**Interfaces:**
- Consumes: `render_business_plan_docx`, `render_infrannuale_docx` (Task 2).
- Produces: `POST /companies/{c}/scenarios/{s}/business-plan/docx` (body `BusinessPlanPdfRequest`), `POST /companies/{c}/scenarios/{s}/infrannuale/docx` (body `InfrannualePdfRequest`); media type `DOCX_MEDIA_TYPE`.

- [ ] **Step 1: test che falliscono** — stesso impianto di `tests/test_inf_endpoint.py` (copia del DB, override di `get_db` e `get_current_user_id`):

```python
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

def test_infrannuale_docx(client):
    r = client.post("/api/v1/companies/575/scenarios/17/infrannuale/docx", json={})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == DOCX and r.content.startswith(b"PK")
    assert 'filename="Report infrannuale AMBIENTA 6M 2026.docx"' in r.headers["content-disposition"]
    Document(io.BytesIO(r.content))

def test_business_plan_docx(client):
    r = client.post(f"/api/v1/companies/575/scenarios/{client.ids['budget']}/business-plan/docx",
                    json={"document_state": "draft"})
    assert r.status_code == 200 and r.headers["content-type"] == DOCX
    assert ".docx" in r.headers["content-disposition"]

def test_altrui_404(client): ...            # entrambe le rotte con utente diverso → 404
def test_infrannuale_su_budget_400(client): # /infrannuale/docx su scenario budget → 400
def test_campo_in_piu_422(client):          # {"avviso_commenti": False} → 422 su /infrannuale/docx
def test_nessuna_ai(client, monkeypatch):   # anthropic.Anthropic.__init__ → pytest.fail, entrambe 200
```

- [ ] **Step 2: eseguire — FAIL** (404 sulle rotte che non esistono).

- [ ] **Step 3: implementazione**
  - Servizi: `filenames(..., ext="pdf")` compone `.{ext}`; `render_docx(...)` identico a `render` ma chiama il renderer Word e passa `ext="docx"`; stesso dataclass risultato.
  - Rotte: gemelle delle `/pdf` (stessi `validate_*`, stessi errori, stessi header), `media_type=DOCX_MEDIA_TYPE` (costante nel servizio infrannuale, importata da `reports.py`), `summary` in italiano.

- [ ] **Step 4: eseguire — PASS** `$PY -m pytest ../tests/test_docx_endpoint.py ../tests/test_inf_endpoint.py ../tests/test_bp_endpoint.py -q`.

- [ ] **Step 5: commit** `feat(report-docx): rotte Word di Business plan e infrannuale`.

---

### Task 4: Frontend — «Scarica Word»

**Files:**
- Modify: `frontend/lib/api.ts` (`downloadReportDocx`), `frontend/lib/final-report-download.ts` (`wordAvailable`)
- Create: `frontend/hooks/use-file-download.ts` (hook generico: guardia, toast, «Riprova»)
- Modify: `frontend/hooks/use-infrannuale-download.ts` (costruito sul generico), `frontend/components/pratica/StampaContent.tsx`, `frontend/app/report/page.tsx`
- Test: `frontend/lib/api.test.ts`, `frontend/lib/final-report-download.test.ts`

**Interfaces:**
- Produces: `downloadReportDocx(companyId, scenarioId, kind: "business-plan" | "infrannuale", documentState?: FinalReportDocumentState): Promise<DownloadFinalReportPdfResult>`; `wordAvailable(model: ReportModel): boolean`; `useFileDownload(): { download(fetcher: () => Promise<{blob, filename}>, errorFallback: string): Promise<void>, downloading: boolean }`.

- [ ] **Step 1: test che falliscono**

```ts
describe("downloadReportDocx", () => {
  it("chiama la rotta Word giusta col corpo della PDF", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Blob(["PK"]), {
      status: 200, headers: { "Content-Disposition": 'attachment; filename="Report.docx"' } }));
    vi.stubGlobal("fetch", fetchMock);
    const r = await downloadReportDocx(1, 2, "infrannuale");
    expect(fetchMock.mock.calls[0][0]).toContain("/companies/1/scenarios/2/infrannuale/docx");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({});
    expect(r.filename).toBe("Report.docx");
    await downloadReportDocx(1, 3, "business-plan", "final");
    expect(fetchMock.mock.calls[1][0]).toContain("/business-plan/docx");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ document_state: "final" });
  });
});
// final-report-download.test.ts
it("il Word esiste solo per il Business plan", () => {
  expect(wordAvailable("business_plan")).toBe(true);
  expect(wordAvailable("dossier")).toBe(false);
});
```

- [ ] **Step 2: eseguire — FAIL** `cd frontend && npx vitest run lib/api.test.ts lib/final-report-download.test.ts`.

- [ ] **Step 3: implementazione**
  - `downloadReportDocx`: come `downloadInfrannualePdf`, URL `${kind}/docx`, corpo `{}` per l'infrannuale e `{ document_state }` per il Business plan; stessa gestione d'errore. Aggiunta in coda al blocco delle download, preservando i fine riga del file.
  - `wordAvailable = (model) => model === "business_plan"`.
  - `useFileDownload`: il corpo di `useInfrannualeDownload` con il fetcher come parametro; `useInfrannualeDownload` diventa `download(c, s) => file.download(() => downloadInfrannualePdf(c, s), ...)`.
  - Stampa: pulsante «Scarica Word» (icona `FileText`) accanto a «Scarica PDF», disabilitato mentre uno dei due scarica.
  - /report: pulsante «Scarica Word» dopo «Scarica bozza/finale», solo se `wordAvailable(reportModel)`, con lo stesso `documentState` del PDF.

- [ ] **Step 4: eseguire — PASS** `npx vitest run && npx tsc --noEmit`.

- [ ] **Step 5: commit** `feat(report-docx): «Scarica Word» nella Stampa e su /report`.

---

### Task 5: Documentazione

**Files:** `docs/budget/BUSINESS-PLAN-PDF.md`, `docs/budget/REPORT-INFRANNUALE-PDF.md`, `CLAUDE.md` (paragrafo Stampa e riga `/report`).

- [ ] **Step 1:** in entrambe le pagine una sezione «Il Word» (traduttore unico, flowable sconosciuto = errore, indice senza pagine, commenti corretti restano nel file, `python-docx` in requirements); in `CLAUDE.md` una frase nel paragrafo della Stampa e nella riga di `/report`.
- [ ] **Step 2:** suite completa: `cd backend && $PY -m pytest ../tests/test_docx_*.py ../tests/test_inf_*.py ../tests/test_bp_*.py ../tests/test_final_report_pdf_endpoint.py -q` e `cd frontend && npx vitest run && npx tsc --noEmit`.
- [ ] **Step 3: commit** `docs(report-docx): export Word nella documentazione dei due report`.
