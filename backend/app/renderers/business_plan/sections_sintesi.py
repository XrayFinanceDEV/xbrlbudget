"""Copertina e sezione 1: numeri chiave, indice, sintesi, forza/debolezza e azioni."""
from __future__ import annotations

from decimal import Decimal

from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from . import fmt, layout, narrative, theme
from .data import BusinessPlanData
from .sections_economia import _plan_span, _sum_plan, headers, row
from .theme import BOLD, CW, LM, PAGE_H, PAGE_W, REGULAR

C = HexColor

INDEX = [  # (numero, titolo dell'indice, chiave di sezione)
    ("1", "Sintesi del piano · punti di forza, di debolezza e azioni prioritarie", "sintesi"),
    ("2", "Evoluzione economica dell'impresa", "economia"),
    ("3", "EBITDA margin e struttura dei costi", "costi"),
    ("4", "Costi fissi e variabili · break even point", "pareggio"),
    ("5", "Flussi di cassa", "flussi"),
    ("6", "Sostenibilità del debito · DSCR e PFN", "debito"),
    ("7", "Capitale circolante commerciale", "circolante"),
    ("8", "Solidità patrimoniale, liquidità e redditività", "solidita"),
    ("9", None, "partenza"),  # titolo dal punto di partenza del workflow
    ("10", "Assunzioni del piano", "ipotesi"),
    ("", "Allegati A–E · prospetti completi e indicatori", "allegato_a"),
]


def _years(data: BusinessPlanData) -> str:
    y = data.plan_years
    return f"{y[0]} – {y[-1]}" if len(y) > 1 else str(y[0])


def _cover_name(name: str) -> tuple:
    """Una riga da 40 a 20 pt; sotto i 20 pt il nome va su due righe (fino a 16 pt), poi si tronca con «…»."""
    w = pdfmetrics.stringWidth(name, BOLD, 40)
    if w * 20 / 40 <= CW:
        return (min(40.0, 40 * CW / w), [name])
    for size in range(24, 15, -1):
        lines = simpleSplit(name, BOLD, size, CW)
        if len(lines) <= 2:
            return (float(size), lines)
    lines = simpleSplit(name, BOLD, 16, CW)
    return (16.0, [lines[0], layout.fit(" ".join(lines[1:]), BOLD, 16, CW)])


def cover_lines(data: BusinessPlanData) -> layout.CoverLines:
    """I testi della fascia di copertina: gli stessi nel PDF e nel Word."""
    return layout.CoverLines(f"REPORT DI BUDGET {_years(data)}" + (" · BOZZA" if data.draft else ""), data.company_name,
                      f"Piano economico-finanziario {_years(data)}",
                      (data.base_description, "Andamento economico, flussi di cassa, sostenibilità del debito e circolante"))


def draw_cover_band(canvas, data: BusinessPlanData) -> None:
    """Fascia navy della copertina (0–283,5 pt dall'alto) con filetto teal, come nel riferimento."""
    theme.register_fonts()
    canvas.saveState()
    canvas.setFillColor(C(theme.NAVY))
    canvas.rect(0, PAGE_H - 283.5, PAGE_W, 283.5, stroke=0, fill=1)
    canvas.setFillColor(C(theme.TEAL))
    canvas.rect(0, PAGE_H - 289.1, PAGE_W, 5.6, stroke=0, fill=1)
    canvas.setFillColor(white)
    canvas.setFont(BOLD, 10)
    cl = cover_lines(data)
    canvas.drawString(LM, PAGE_H - 64, cl.eyebrow)
    size, lines = _cover_name(cl.name)
    canvas.setFont(BOLD, size)
    if len(lines) == 1:
        canvas.drawString(LM, PAGE_H - 122, lines[0])
    else:  # due righe nella stessa fascia: l'altezza della copertina non cambia, l'indice resta stabile
        for n, line in enumerate(lines):
            canvas.drawString(LM, PAGE_H - 106 - n * size * 1.12, line)
    canvas.setFont(REGULAR, 21)
    canvas.drawString(LM, PAGE_H - 160, cl.title)
    canvas.setFillColor(C(theme.COVER_SUB))
    canvas.setFont(REGULAR, 11)
    canvas.drawString(LM, PAGE_H - 200, cl.lines[0])
    canvas.drawString(LM, PAGE_H - 220, cl.lines[1])
    canvas.setFillColor(C(theme.MUTED))
    canvas.setFont(REGULAR, 7.8)
    canvas.drawString(LM, PAGE_H - 820, "Riservato e confidenziale")
    canvas.restoreState()


def _chip_tiles(items: list) -> Table:
    """Riquadri di copertina: chip teal con il periodo, valore, etichetta, nota."""
    gap = 8.5
    w = (CW - 3 * gap) / 4
    chip = layout._ps("chip", BOLD, 8.6, 10, "#ffffff")
    val = layout._ps("cv", BOLD, 12.5, 15, theme.NAVY)
    cells = []
    for period, value, label, sub in items:
        c = Table([[Paragraph(period, chip)]], colWidths=[w - 11])
        c.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(theme.TEAL)), ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8)]))
        cells.append([c, Spacer(0, 3), Paragraph(value, val), Paragraph(label, layout.ST["kl"]), Spacer(0, 1),
                      Paragraph(sub, layout.ST["ks"])])
    rows = [cells[:4], cells[4:8]]
    data = [[r[0], "", r[1], "", r[2], "", r[3]] for r in rows]
    t = Table(data, colWidths=[w, gap, w, gap, w, gap, w])
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5.5),
             ("RIGHTPADDING", (0, 0), (-1, -1), 5.5), ("TOPPADDING", (0, 0), (-1, -1), 6),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
    for r in range(2):
        for c in (0, 2, 4, 6):
            style += [("BACKGROUND", (c, r), (c, r), C(theme.TILE)), ("LINEABOVE", (c, r), (c, r), 2.2, C(theme.NAVY))]
    t.setStyle(TableStyle(style))
    return t


def _cover_kpis(data: BusinessPlanData) -> list:
    span = f"{data.first.label} → {data.last.label}"
    g = narrative.growth_list(data, "revenue_growth_pct")
    dscr_plan = [v for v in (data.v("dscr")[i] for i in data.plan_idx) if v is not None]
    op = _sum_plan(data, "cf_operativo")
    n = len(data.plan_idx)
    periodo = {2: "sul biennio", 3: "sul triennio"}.get(n, "negli anni")
    e0, en = data.v("ebitda")[0], data.v("ebitda")[-1]
    last = data.last.label
    return [
        (span, fmt.compact_range(data.v("ricavi")[0], data.v("ricavi")[-1]), "Ricavi delle vendite",
         f"crescita {g} nel piano" if g else ("ricavi forzati nel CE previsionale"
                                                     if data.growth.get("revenue_growth_pct") else "crescita da ipotesi di piano")),
        (span, f"{fmt.pct(data.v('ebitda_margin')[0])} → {fmt.pct(data.v('ebitda_margin')[-1])}", "EBITDA margin",
         f"EBITDA {fmt.compact_eur(e0)} → {fmt.compact_eur(en)}"),
        (span, f"{fmt.ratio(data.v('dscr')[0])} → {fmt.ratio(data.v('dscr')[-1])}", "DSCR (proxy)",
         f"mai inferiore a {fmt.floor_ratio(min(dscr_plan), 1)}" if dscr_plan else "n.d."),
        (f"{data.plan_columns[0].label} – {last}", fmt.compact_eur(op), "Flussi di cassa operativi",
         f"cumulati {periodo} di piano"),
        (span, fmt.compact_range(data.v("pfn")[0], data.v("pfn")[-1]), "Posizione finanziaria netta",
         "debiti finanziari − liquidità"),
        (span, f"{fmt.ratio(data.v('pfn_ebitda')[0])} → {fmt.ratio(data.v('pfn_ebitda')[-1])}", "PFN / EBITDA",
         "rapporto di indebitamento"),
        (last, fmt.compact_eur(data.v("bep")[-1]), "Break even point",
         f"margine di sicurezza {fmt.pct(data.v('margine_sicurezza')[-1])}"),
        (last, fmt.compact_eur(data.v("cc_comm")[-1]), "Capitale circolante commerciale",
         f"DSO {fmt.eur(data.v('dso')[-1])} gg · DIO {fmt.eur(data.v('dio')[-1])} gg · "
         f"DPO {fmt.eur(data.v('dpo')[-1])} gg"),
    ]


def _index_table(data: BusinessPlanData, pages: dict) -> Table:
    num = layout._ps("in", BOLD, 9.8, 12, theme.TEAL)
    tit = layout._ps("it", REGULAR, 9.8, 12, theme.INK)
    pg = layout._ps("ip", REGULAR, 9.8, 12, theme.MUTED, alignment=2)
    rows = []
    for n, title, key in INDEX:
        if key == "partenza":
            title = data.starting_point.title if data.starting_point else "Punto di partenza"
        rows.append([Paragraph(n, num), Paragraph(title, tit), Paragraph(str(pages.get(key, "")), pg)])
    t = Table(rows, colWidths=[22, CW - 22 - 40, 40], rowHeights=19.2)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, C(theme.RULE)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    return t


def copertina(data: BusinessPlanData, pages: dict) -> list:
    return layout.h2("I numeri chiave del piano", after=6) + [_chip_tiles(_cover_kpis(data)), Spacer(0, 14)] + \
        layout.h2("Indice", after=4) + [_index_table(data, pages)]


def _cruscotto(data: BusinessPlanData) -> Table:
    g = lambda label: (label, [], "group")  # noqa: E731
    rows = [g("Conto economico"), row(data, "Ricavi delle vendite", "ricavi"),
            row(data, "Valore della produzione", "valore_produzione"), row(data, "EBITDA", "ebitda"),
            row(data, "EBITDA margin", "ebitda_margin", "hl", "percent"), row(data, "Risultato netto", "utile"),
            g("Cassa e debito"), row(data, "Flusso di cassa operativo", "cf_operativo"),
            row(data, "Disponibilità liquide a fine anno", "cassa_fine"),
            row(data, "Posizione finanziaria netta (PFN)", "pfn"),
            row(data, "PFN / EBITDA", "pfn_ebitda", unit="ratio"), row(data, "DSCR — proxy", "dscr", "hl", "ratio"),
            g("Break-even e circolante"), row(data, "Break even point", "bep"),
            row(data, "Margine di sicurezza", "margine_sicurezza", "hl", "percent"),
            row(data, "Capitale circolante commerciale ¹", "cc_comm", "hl"),
            row(data, "Ciclo di conversione del denaro (gg)", "ciclo", unit="days"),
            g("Patrimonio"), row(data, "Patrimonio netto", "patrimonio_netto"),
            row(data, "Indipendenza finanziaria", "indipendenza", unit="percent")]
    return layout.fin_table(headers(data), rows, first="Indicatore")


def sintesi(data: BusinessPlanData, pages: dict) -> list:
    base = data.first.label
    s = layout.section_head("SEZIONE 1", "Sintesi del piano",
                            f"Il quadro economico, finanziario e patrimoniale del piano in una pagina. "
                            f"{data.base_description}.")
    s += [layout.panel("Punti chiave del piano", narrative.key_points(data)), Spacer(0, 12)]
    s += layout.h2("Cruscotto degli indicatori", after=6) + [_cruscotto(data), Spacer(0, 5),
          layout.note(f"¹ Crediti commerciali + rimanenze − debiti commerciali, calcolato sui saldi dello stato "
                      f"patrimoniale (Sezione 7). Colonna {base}: {data.base_description.lower()}.")]
    return s


def _card(title: str, color: str, fill: str, items: list, width: float) -> Table:
    head = layout._ps("ch", BOLD, 11, 14, color)
    content = [Paragraph(title, head), Spacer(0, 5)]
    if not items:
        content.append(Paragraph("Nessun elemento supera le soglie di valutazione.", layout.ST["cell"]))
    for f in items:
        content += [Paragraph(f.title, layout.ST["cardhead"]), Paragraph(f.text, layout.ST["cell"]), Spacer(0, 5)]
    t = Table([[content]], colWidths=[width])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(fill)), ("LINEABOVE", (0, 0), (-1, 0), 2.5, C(color)),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def forza(data: BusinessPlanData, pages: dict) -> list:
    plan = data.plan_years
    s = layout.section_head("SEZIONE 1 · SEGUE", "Punti di forza, di debolezza e azioni prioritarie",
                            f"Valutazione di sintesi basata sui dati di {data.first.label} e degli anni di piano "
                            f"{plan[0]}–{plan[-1]}.")
    strengths, weaknesses = narrative.strengths_weaknesses(data)
    w = (CW - 11.4) / 2
    pair = Table([[_card("Punti di forza", theme.TEAL, theme.HL, strengths, w),
                   _card("Punti di debolezza", theme.RED, theme.WEAK, weaknesses, w)]], colWidths=[w, w])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    pair.hAlign = "CENTER"
    s += [pair, Spacer(0, 12)] + layout.h2("Azioni prioritarie", after=6)
    num = layout._ps("an", BOLD, 11, 13, theme.TEAL)
    rows = [[Paragraph("#", layout.ST["cellh"]), Paragraph("Azione", layout.ST["cellh"]),
             Paragraph("Contenuto", layout.ST["cellh"]), Paragraph("Indicatori da monitorare", layout.ST["cellh"])]]
    for i, (title, text, kpi) in enumerate(narrative.actions(data, weaknesses), start=1):
        rows.append([Paragraph(str(i), num), Paragraph(title, layout.ST["cellb"]), Paragraph(text, layout.ST["cell"]),
                     Paragraph(kpi, layout.ST["cell"])])
    t = Table(rows, colWidths=[24, 110, CW - 24 - 110 - 120, 120], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C("#ffffff"), C(theme.PANEL)]),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return s + [t]
