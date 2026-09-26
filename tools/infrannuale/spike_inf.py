"""Spike (riferimento di resa, non codice di produzione): pagine 4, 6 e 9 del report infrannuale del committente, ricostruite con il motore del
Business plan (ReportLab + matplotlib) sugli stessi numeri stampati nel riferimento."""
import io
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from matplotlib.patches import Patch  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from reportlab.lib.colors import HexColor, white  # noqa: E402
from reportlab.lib.enums import TA_RIGHT  # noqa: E402
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table,  # noqa: E402
                                TableStyle)

from app.renderers.business_plan import charts as bc, layout, theme  # noqa: E402
from app.renderers.business_plan.charts import (_f, _fig, _finite, _k, _legend, _limits, _png, _text,  # noqa: E402
                                                _thousands, _xticks, _ylabel, FAMILY, LABEL, TICK)
from app.renderers.business_plan.fmt import chart_num  # noqa: E402
from app.renderers.business_plan.layout import ST, _ps  # noqa: E402
from app.renderers.business_plan.theme import BOLD, CW, LM, PAGE_H, PAGE_W, REGULAR  # noqa: E402

C = HexColor
D = lambda *xs: [None if x is None else float(x) for x in xs]  # noqa: E731
CRISI_BG = "#e4e7ec"
ATTENZIONE = "#b7791f"
CHART_W = 459.0  # i grafici del report infrannuale stanno a 459 pt, centrati (1584 px a ~248 dpi)


# ------------------------------------------------------------------------------------------------ grafici
def ricavi_periodi(labels, ricavi, margine, kinds) -> bytes:
    """Barre dei ricavi per periodo (C grigio, 6M azzurro tratteggiato, Ann. azzurro, F navy) + EBITDA margin."""
    bc.HEIGHTS["ricavi_periodi"] = 3.0
    fig, ax = _fig("ricavi_periodi")
    fig.subplots_adjust(left=0.105, right=0.935, top=0.95, bottom=0.12)
    x = list(range(len(labels)))
    k = _k(ricavi)
    style = {"C": (theme.GREY, None, "white"), "6M": (theme.LIGHTBLUE, "//", theme.NAVY),
             "Ann": (theme.LIGHTBLUE, None, theme.NAVY), "F": (theme.NAVY, None, "white")}
    for i, (v, kind) in enumerate(zip(k, kinds)):
        if math.isnan(v):
            continue
        face, hatch, ink = style[kind]
        ax.bar(i, v, 0.55, color=face, hatch=hatch, edgecolor="white" if hatch else face, linewidth=0, zorder=2)
        _text(ax, i, v / 2, chart_num(v), ha="center", va="center", color=ink, fontweight="bold", fontsize=LABEL)
    top = max(_finite(k) + [1.0])
    ax.set_ylim(0, top * 1.57)
    _thousands(ax)
    ax.yaxis.set_major_locator(bc.MaxNLocator(nbins=7, steps=[1, 2, 2.5, 5, 10]))
    _xticks(ax, labels)
    _ylabel(ax, "Ricavi delle vendite (€ k)")
    ax2 = ax.twinx()
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color(theme.GREY)
    ax2.tick_params(colors=theme.GREY, length=4)
    ax2.tick_params(labelcolor=theme.AXIS, labelsize=TICK, labelfontfamily=FAMILY)
    m = _f(margine)
    ax2.plot(x, m, color=theme.ORANGE, linewidth=2.2, marker="o", markersize=6, zorder=3)
    hi = max(_finite(m) + [1.0])
    ax2.set_ylim(0, max(5.0, math.ceil(hi * 1.12)))
    ax2.yaxis.set_major_formatter(bc.FuncFormatter(lambda v, _: f"{v:.0f}%"))
    span = ax2.get_ylim()[1]
    for i, v in enumerate(m):
        if not math.isnan(v):
            _text(ax2, i, v + 0.035 * span, chart_num(v, 2) + "%", ha="center", va="bottom",
                  color=theme.ORANGE_DARK, fontweight="bold", fontsize=LABEL)
    _legend(ax, [Line2D([], [], color=theme.ORANGE, linewidth=2.2, marker="o", markersize=6)], ["EBITDA margin %"],
            loc="upper left", bbox_to_anchor=(0, 1.035))
    return _png(fig)


def stato_patrimoniale(labels, attivo, deb_fin, deb_op, pn) -> bytes:
    bc.HEIGHTS["stato_patrimoniale"] = 2.8
    fig, ax = _fig("stato_patrimoniale")
    fig.subplots_adjust(left=0.10, right=0.985, top=0.95, bottom=0.12)
    series = ((attivo, theme.GREY, "Totale attivo"), (deb_fin, theme.NAVY, "Debiti finanziari"),
              (deb_op, theme.LIGHTBLUE, "Debiti operativi"), (pn, theme.ORANGE, "Patrimonio netto"))
    w = 0.2
    allk = []
    for j, (vals, color, _) in enumerate(series):
        k = _k(vals)
        allk += _finite(k)
        for i, v in enumerate(k):
            if math.isnan(v):
                continue
            xpos = i + (j - 1.5) * w
            ax.bar(xpos, v, w, color=color, zorder=2)
            _text(ax, xpos, v, chart_num(v), ha="center", va="bottom" if v >= 0 else "top", color="black",
                  fontsize=LABEL)
    _limits(ax, allk, top_room=1.16)
    _thousands(ax)
    _xticks(ax, labels)
    _ylabel(ax, "€ migliaia")
    _legend(ax, [Patch(color=c) for _, c, _ in series], [lab for _, _, lab in series], loc="upper left", ncol=4,
            handlelength=2.2, columnspacing=2.2)
    return _png(fig)


CLASSE_COLORE = {"A": theme.TEAL, "B": theme.ORANGE, "C": theme.ORANGE, "D": theme.RED}


def crisi(labels, oltre, totale, classi) -> bytes:
    """Barre orizzontali: indicatori oltre soglia su totale, colore della classe, classe a destra."""
    bc.HEIGHTS["crisi"] = 2.4
    fig, ax = _fig("crisi")
    fig.subplots_adjust(left=0.105, right=0.985, top=0.95, bottom=0.14)
    y = list(range(len(labels)))[::-1]
    for yi, n, cls in zip(y, oltre, classi):
        ax.barh(yi, totale, 0.55, color=CRISI_BG, zorder=1)
        color = CLASSE_COLORE[cls[0]]
        if n is not None:
            ax.barh(yi, n, 0.55, color=color, zorder=2)
            _text(ax, n - 0.15, yi, f"{n} su {totale} oltre soglia", ha="right", va="center", color="white",
                  fontweight="bold", fontsize=TICK)
        _text(ax, totale + 0.2, yi, cls, ha="left", va="center", color=color, fontweight="bold", fontsize=TICK)
    ax.set_yticks(y, labels)
    ax.set_xlim(0, totale * 1.32)
    ax.set_xticks(list(range(0, totale + 1, 2)))
    ax.set_ylim(-0.55, len(labels) - 0.45)
    ax.grid(True, axis="x", color=theme.GRID, linewidth=0.8)
    ax.grid(False, axis="y")
    return _png(fig)


# ------------------------------------------------------------------------------------------------ primitivi
ST["chip"] = _ps("chip", BOLD, 8.6, 10, "#ffffff")
ST["kv13"] = _ps("kv13", BOLD, 13, 15.5, theme.NAVY)


def tiles_chip(items, value_style="kv"):
    """Riquadri KPI dell'infrannuale: bollino teal col periodo, valore, etichetta, confronto."""
    gap = 8.5
    w = (CW - 3 * gap) / 4
    cells = []
    for chip, v, lab, s in items:
        badge = Table([[Paragraph(chip, ST["chip"])]], colWidths=[w - 11], rowHeights=[13.5])
        badge.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(theme.TEAL)),
                                   ("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 1.6),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        cells.append([badge, Spacer(0, 2.5), Paragraph(v, ST[value_style]), Spacer(0, 1.5),
                      Paragraph(lab, ST["kl"]), Spacer(0, 1), Paragraph(s, ST["ks"])])
    t = Table([[cells[0], "", cells[1], "", cells[2], "", cells[3]]], colWidths=[w, gap, w, gap, w, gap, w])
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5.5),
             ("RIGHTPADDING", (0, 0), (-1, -1), 5.5), ("TOPPADDING", (0, 0), (-1, -1), 6),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 4.9)]
    for c in (0, 2, 4, 6):
        style += [("BACKGROUND", (c, 0), (c, 0), C(theme.TILE)), ("LINEABOVE", (c, 0), (c, 0), 2.2, C(theme.NAVY))]
    t.setStyle(TableStyle(style))
    return t


def table(headers, rows):
    t = layout.fin_table(headers, rows, pad=3.55, value_size=9.8, label_size=8.0)
    t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, 0), 4.0), ("BOTTOMPADDING", (0, 0), (-1, 0), 4.0)]))
    return t


ESITO = {"in soglia": theme.TEAL, "oltre soglia": theme.RED, "attenzione": ATTENZIONE}


def crisi_table(rows):
    vs = _ps("v98", REGULAR, 9.8, 11.3, alignment=TA_RIGHT)
    lab = _ps("l8", REGULAR, 8.0, 9.2)
    data = [[Paragraph("Indicatore", ST["cellh"])] +
            [Paragraph(h, ST["valueh"]) for h in ("2025 C", "6M 2026", "2026 F", "Esito 2026 F")]]
    for name, a, b, c, esito in rows:
        es = _ps("es", BOLD, 9.8, 11.3, ESITO[esito], alignment=TA_RIGHT)
        data.append([Paragraph(name, lab), Paragraph(a, vs), Paragraph(b, vs), Paragraph(c, vs), Paragraph(esito, es)])
    t = Table(data, colWidths=[CW - 4 * 82, 82, 82, 82, 82])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), 3.55), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.55),
                           ("TOPPADDING", (0, 0), (-1, 0), 4.0), ("BOTTOMPADDING", (0, 0), (-1, 0), 4.0),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, C(theme.RULE))]))
    return t


# ------------------------------------------------------------------------------------------------ pagine
L3 = ["2025 C", "6M 2026", "2026 F"]


def pagina4():
    s = layout.section_head("SEZIONE 2", "Conto economico: infrannuale, annualizzato e forecast",
                            "L'annualizzato riporta i 6 mesi a dodici (× 12/6); il forecast è la stima a fine anno "
                            "costruita con le ipotesi sul secondo semestre, non l'annualizzazione aritmetica.")
    s += [tiles_chip([("6M 2026", "€ 2,10 mln", "Ricavi del semestre", "EBITDA € 82,2 mila"),
                      ("Ann. 2026", "€ 4,21 mln", "Ricavi annualizzati", "+11,92% sul 2025 C"),
                      ("2026 F", "€ 4,11 mln", "Ricavi forecast", "+9,26% sul 2025 C"),
                      ("2026 F", "€ 24,1 mila", "Utile netto forecast", "+207,98% sul 2025 C")]), Spacer(0, 5)]
    png = ricavi_periodi(["2025 C", "6M 2026", "Ann. 2026", "2026 F"], D(3761088, 2104755, 4209510, 4109510),
                         D(4.04, 3.91, 3.91, 4.04), ["C", "6M", "Ann", "F"])
    s += [layout.chart(png, 3.0, CHART_W)]
    R = [("Ricavi delle vendite", ["3.761.088", "2.104.755", "4.209.510", "4.109.510", "11,92%", "9,26%"], ""),
         ("Valore della produzione", ["4.006.984", "2.220.108", "4.440.216", "4.343.216", "10,81%", "8,39%"], ""),
         ("Costi operativi (esclusi ammortamenti)", ["3.854.915", "2.137.866", "4.275.732", "4.177.379", "10,92%", "8,37%"], ""),
         ("EBITDA (MOL)", ["152.069", "82.242", "164.484", "165.837", "8,16%", "9,05%"], "bold"),
         ("EBITDA margin", ["4,04%", "3,91%", "3,91%", "4,04%", "", ""], "hl"),
         ("Ammortamenti e svalutazioni", ["76.057", "32.632", "65.264", "75.264", "−14,19%", "−1,04%"], ""),
         ("EBIT", ["76.012", "49.610", "99.220", "90.573", "30,53%", "19,16%"], "bold"),
         ("Altri proventi finanziari", ["1.340", "8.875", "17.750", "11.750", "1.224,51%", "776,87%"], ""),
         ("Oneri finanziari", ["−40.744", "−22.596", "−45.192", "−45.192", "10,92%", "10,92%"], ""),
         ("Risultato ante imposte", ["36.608", "35.889", "71.778", "57.131", "96,07%", "56,06%"], "bold"),
         ("Imposte", ["−28.773", "−15.000", "−30.000", "−33.000", "4,26%", "14,69%"], ""),
         ("Risultato netto", ["7.835", "20.889", "41.778", "24.131", "433,19%", "207,98%"], "hl")]
    s += [table(["2025 C", "6M 2026", "Ann. 2026", "2026 F", "Ann. / C", "F / C"], R), Spacer(0, 5),
          layout.note("Variazioni calcolate rispetto al consuntivo 2025 (C). Il 6M non è confrontabile direttamente "
                      "con un esercizio completo. Dettaglio nell'Allegato A.")]
    return s


def pagina6():
    s = layout.section_head("SEZIONE 4", "Stato patrimoniale",
                            "Lo stato patrimoniale è puntuale: i valori al 30.06.2026 non si annualizzano e si "
                            "confrontano con il consuntivo 2025; il forecast rappresenta i saldi attesi al 31.12.2026.")
    s += [tiles_chip([("6M 2026", "€ 2,46 mln", "Totale attivo", "+13,34% sul 2025 C"),
                      ("2026 F", "€ 2,32 mln", "Totale attivo", "+6,75% sul 2025 C"),
                      ("2026 F", "€ 203,6 mila", "Patrimonio netto", "+13,18% sul 2025 C"),
                      ("2026 F", "€ 997,4 mila", "Debiti finanziari", "+17,00% sul 2025 C")]), Spacer(0, 5)]
    png = stato_patrimoniale(L3, D(2170830, 2460463, 2317356), D(852511, 997441, 997441),
                             D(939011, 1101133, 907443), D(179897, 200373, 203616))
    s += [layout.chart(png, 2.8, CHART_W)]
    R = [("Immobilizzazioni", ["584.094", "489.671", "457.039", "−16,17%", "−21,75%"], ""),
         ("Attivo circolante", ["1.377.867", "1.754.565", "1.644.090", "27,34%", "19,32%"], ""),
         ("Totale attivo", ["2.170.830", "2.460.463", "2.317.356", "13,34%", "6,75%"], "bold"),
         ("Patrimonio netto", ["179.897", "200.373", "203.616", "11,38%", "13,18%"], "hl"),
         ("Debiti finanziari", ["852.511", "997.441", "997.441", "17,00%", "17,00%"], ""),
         ("Debiti operativi", ["939.011", "1.101.133", "907.443", "17,27%", "−3,36%"], ""),
         ("Disponibilità liquide", ["29.267", "21.765", "55", "−25,63%", "−99,81%"], ""),
         ("Capitale circolante netto", ["26.780", "160.023", "243.239", "497,55%", "808,30%"], "")]
    s += [table(["2025 C", "6M 2026", "2026 F", "6M / C", "F / C"], R), Spacer(0, 5),
          layout.note("Il totale attivo comprende i ratei e risconti attivi (€ 208.869 nel 2025 C, € 216.226 nel 6M e "
                      "nel forecast). Debiti finanziari = debiti verso banche + altri finanziatori. Dettaglio "
                      "nell'Allegato B."), Spacer(0, 4.6),
          layout.panel("Lettura", [
              ("", "L'attivo cresce nel semestre soprattutto per i crediti verso clienti; nel forecast i crediti si "
                   "riducono ma restano superiori al 2025."),
              ("", "Le immobilizzazioni scendono per effetto degli ammortamenti e della riduzione delle "
                   "immobilizzazioni finanziarie (da € 116.250 a € 52.550)."),
              ("", "Il patrimonio netto cresce con l'utile, mentre i debiti finanziari aumentano del 17%: la "
                   "struttura resta sbilanciata sul capitale di terzi.")])]
    return s


def pagina9():
    s = layout.section_head("SEZIONE 7", "Indicatori della crisi d'impresa",
                            "Quattordici indicatori con punteggio da 0 a 1 e sette segnali extracontabili compongono la "
                            "classe di rischio, da A3 (nessun rischio) a D (crisi). «Oltre soglia» indica un punteggio "
                            "inferiore a 0,33.")
    s += [tiles_chip([("2025 C", "D · Crisi", "Classe di rischio", "9 su 14 oltre soglia"),
                      ("6M 2026", "C2 · Rischio grave", "Classe di rischio", "7 su 14 oltre soglia"),
                      ("2026 F", "D · Crisi", "Classe di rischio", "8 su 14 oltre soglia"),
                      ("2025 C – 2026 F", "0 su 7", "Segnali extracontabili attivi", "in tutti i periodi")],
                     value_style="kv13"), Spacer(0, 5)]
    s += [layout.chart(crisi(L3, [9, 7, 8], 14, ["D · Crisi", "C2 · Rischio grave", "D · Crisi"]), 2.4, 439.1)]
    rows = [("DSCR", "3,026×", "2,976×", "2,939×", "in soglia"), ("EBITDA %", "4,04%", "3,91%", "4,04%", "oltre soglia"),
            ("Margine di tesoreria", "−67.803", "26.581", "109.797", "attenzione"),
            ("CCN", "218.292", "313.893", "397.109", "in soglia"),
            ("Liquidità corrente", "1,162×", "1,197×", "1,283×", "in soglia"),
            ("Margine di struttura", "−404.196", "−289.298", "−253.424", "oltre soglia"),
            ("Copertura immobilizzazioni", "106,20%", "143,85%", "154,83%", "in soglia"),
            ("Indipendenza finanziaria", "8,29%", "8,14%", "8,79%", "oltre soglia"),
            ("PFN", "783.496", "939.173", "960.883", "oltre soglia"),
            ("PFN / EBITDA", "5,152×", "5,710×", "5,794×", "oltre soglia"),
            ("ROI", "3,50%", "4,03%", "3,91%", "oltre soglia"), ("ROE", "4,36%", "20,85%", "11,85%", "in soglia"),
            ("ROS", "2,02%", "2,36%", "2,20%", "oltre soglia"),
            ("Oneri finanziari / MOL", "26,79%", "27,48%", "27,25%", "oltre soglia"),
            ("Oneri finanziari / fatturato ¹", "1,08%", "1,07%", "1,10%", "in soglia")]
    s += [crisi_table(rows), Spacer(0, 5),
          layout.note("¹ Riportato per completezza: non entra nella determinazione della classe di rischio. Per il 6M "
                      "2026 gli indicatori reddituali sono su base annualizzata.")]
    return s


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C(theme.NAVY))
    canvas.rect(0, PAGE_H - theme.HEADER_H, PAGE_W, theme.HEADER_H, stroke=0, fill=1)
    canvas.setFillColor(white)
    canvas.setFont(BOLD, 9)
    canvas.drawString(LM, PAGE_H - 20.5, "AMBIENTA")
    canvas.setFont(REGULAR, 9)
    canvas.drawRightString(PAGE_W - LM, PAGE_H - 20.5, "Report infrannuale 6M 2026 e forecast 2026")
    canvas.setStrokeColor(C(theme.RULE))
    canvas.setLineWidth(0.5)
    canvas.line(LM, PAGE_H - theme.FOOTER_RULE_Y, PAGE_W - LM, PAGE_H - theme.FOOTER_RULE_Y)
    canvas.setFillColor(C(theme.MUTED))
    canvas.setFont(REGULAR, 7.8)
    canvas.drawString(LM, PAGE_H - 820, "Riservato e confidenziale · C = consuntivo · 6M = infrannuale al 30.06.2026 · "
                                        "Ann. = annualizzato · F = forecast")
    canvas.drawRightString(PAGE_W - LM, PAGE_H - 820, str({1: 4, 2: 6, 3: 9}[canvas.getPageNumber()]))
    canvas.restoreState()


def build() -> bytes:
    theme.register_fonts()
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=(PAGE_W, PAGE_H), leftMargin=LM, rightMargin=LM, topMargin=55,
                          bottomMargin=40)
    doc.addPageTemplates([PageTemplate(id="b", frames=[Frame(LM, 40, CW, PAGE_H - 95, leftPadding=0,
                                                             rightPadding=0, topPadding=0, bottomPadding=0)],
                                       onPage=on_page)])
    story = pagina4() + [PageBreak()] + pagina6() + [PageBreak()] + pagina9()
    doc.build(story)
    return buf.getvalue()


if __name__ == "__main__":
    open(sys.argv[1], "wb").write(build())
