"""Impaginazione: intestazione, piè di pagina, tabella a sei colonne e indice calcolato su due passate."""
from decimal import Decimal as D

import fitz

from app.renderers.business_plan import document, layout, theme
from app.renderers.business_plan.data import BusinessPlanData, Column


def _data(n_plan=3, draft=False):
    cols = (Column("closing:2026", 2026, "2026 F", True),) + tuple(
        Column(f"forecast:{y}", y, f"{y} P", False) for y in range(2027, 2027 + n_plan))
    return BusinessPlanData(company_name="AZIENDA PROVA", workflow="infrannuale", columns=cols,
                            base_description="Base: prova", values={}, draft=draft)


def _two_sections(monkeypatch):
    def a(data, pages):
        return layout.section_head("SEZIONE 1", "Prima", "sotto") + [layout.note("x")]

    def b(data, pages):
        return layout.section_head("SEZIONE 2", "Seconda", "sotto") + [layout.note(f"pagina prima: {pages.get('a')}")]
    monkeypatch.setattr(document, "SECTIONS", [document.SectionSpec("a", "Prima", a),
                                               document.SectionSpec("b", "Seconda", b)])


def test_intestazione_e_piede(monkeypatch):
    _two_sections(monkeypatch)
    pdf = fitz.open(stream=document.render_business_plan(_data()), filetype="pdf")
    assert pdf.page_count == 2
    p = pdf[0]
    band = [d for d in p.get_drawings() if d.get("fill") and abs(d["rect"].height - theme.HEADER_H) < 0.5]
    assert band and band[0]["rect"].y0 < 0.5
    text = p.get_text()
    assert "AZIENDA PROVA" in text and "Piano economico-finanziario 2027 – 2029" in text
    assert "F = forecast · P = previsione di piano" in text
    assert "pagina prima: 1" in pdf[1].get_text()  # seconda passata: la pagina è nota


def test_bozza_nell_intestazione(monkeypatch):
    _two_sections(monkeypatch)
    pdf = fitz.open(stream=document.render_business_plan(_data(draft=True)), filetype="pdf")
    assert "BOZZA" in pdf[0].get_text()


def test_tabella_sei_colonne_sta_in_pagina():
    headers = ["2025 C"] + [f"{y} P" for y in range(2026, 2031)]
    table = layout.fin_table(headers, [("Ricavi delle vendite e delle prestazioni", ["4.109.510"] * 6, "")])
    w, _ = table.wrap(theme.CW, 800)
    assert w <= theme.CW + 0.5
