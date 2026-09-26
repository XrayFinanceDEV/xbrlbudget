"""Sezione 9 (punto di partenza, per workflow) e sezione 10 (ipotesi del piano)."""
from __future__ import annotations

from decimal import Decimal

from reportlab.lib.colors import HexColor
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from . import fmt, layout, narrative, theme
from .data import BusinessPlanData
from .theme import CW

C = HexColor


def partenza(data: BusinessPlanData, pages: dict) -> list:
    sp = data.starting_point
    if sp is None:
        return layout.section_head("SEZIONE 9", "Punto di partenza", "Dati di partenza non disponibili.")
    s = layout.section_head("SEZIONE 9", sp.title, sp.intro)
    s += [layout.tiles(list(sp.tiles)), Spacer(0, 12)]
    for block in sp.tables:
        s += layout.h2(block.title, after=6)
        s += [layout.fin_table(list(block.headers), [(label, [fmt.eur(v) for v in vals], style)
                                                     for label, vals, style in block.rows])]
        if block.note:
            s += [Spacer(0, 4), layout.note(block.note)]
        s += [Spacer(0, 10)]
    if sp.indicators:
        # indivisibile, come a p. 12 del riferimento: titolo e tabella stanno insieme
        block = layout.h2("Indicatori di partenza", after=4)
        if sp.note:
            block += [layout.note(sp.note), Spacer(0, 4)]
        block += [layout.fin_table(list(sp.indicator_headers),
                                   [(r.label, [fmt.value(v, r.unit) for v in r.values], "") for r in sp.indicators],
                                   first="Indicatore")]
        s += [KeepTogether(block), Spacer(0, 10)]
    block = layout.h2("Fonti e controlli di quadratura" if sp.sources else "Controlli di quadratura", after=4)
    if sp.sources:
        block += [_grid(("Fonte", "Periodo", "Stato"), sp.sources, (180, 150, CW - 330), bold_first=False),
                  Spacer(0, 6)]
    block += [_grid(("Controllo", "Esito"), sp.checks, (180, CW - 180), bold_first=True)]
    return s + [KeepTogether(block)]


def _grid(headers, rows, widths, *, bold_first: bool) -> Table:
    first = layout.ST["cellb"] if bold_first else layout.ST["cell"]
    data = [[Paragraph(h, layout.ST["cellh"]) for h in headers]] + \
        [[Paragraph(r[0], first)] + [Paragraph(x, layout.ST["cell"]) for x in r[1:]] for r in rows]
    t = Table(data, colWidths=list(widths))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, C(theme.RULE)),
                           ("TOPPADDING", (0, 0), (-1, -1), 4.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.6)]))
    return t


_AREE = (("Scenario", "Inflazione e ipotesi di scenario generale."),
         ("Fatturato", "Crescita dei ricavi delle vendite e degli altri ricavi."),
         ("Costi", "Incidenza dei costi operativi e ripartizione fissi/variabili."),
         ("Capitale circolante", "Giorni di incasso, giacenza e pagamento del circolante."),
         ("Patrimoniale pregresso", "Debito pregresso, fidi e piano di rimborso già in essere."),
         ("Patrimoniale piano", "Investimenti, nuovo finanziamento, ammortamenti e cassa."),
         ("Imposte", "Aliquota fiscale e acconti."))


def _uniform(vals) -> bool:
    return bool(vals) and all(v is not None and v == vals[0] for v in vals)


def ipotesi(data: BusinessPlanData, pages: dict) -> list:
    years = data.plan_years
    s = layout.section_head("SEZIONE 10", "Assunzioni del piano", "Driver dichiarati per ciascun anno di piano.")
    g = data.growth
    rev = narrative.growth_list(data, "revenue_growth_pct")
    forzati = rev is None and data.growth.get("revenue_growth_pct") is not None
    pers = g.get("personnel_growth_pct")
    inv = [sum((x or Decimal(0)) for x in pair) for pair in
           zip(g.get("tangible_investments", (None,) * len(years)), g.get("intangible_investments", (None,) * len(years)))]
    inv_years = [str(y) for y, v in zip(years, inv) if v]
    tax = g.get("tax_rate")
    s += [layout.tiles([
        (rev or ("da CE" if forzati else fmt.ND), "Crescita ricavi",
         "ricavi forzati nel CE previsionale" if forzati else " / ".join(str(y) for y in years)),
        (fmt.pct_short(pers[0]) if pers and _uniform(pers) else (narrative.growth_list(data, "personnel_growth_pct") or fmt.ND),
         "Crescita costo del personale", "tutti gli anni di piano" if pers and _uniform(pers) else "per anno"),
        (fmt.compact_eur(sum(inv, Decimal(0))), "Investimenti",
         f"nel {' e '.join(inv_years)}" if inv_years else "nessun investimento"),
        (fmt.pct(tax[0]) if tax and _uniform(tax) else fmt.ND, "Aliquota fiscale",
         "tutti gli anni di piano" if tax and _uniform(tax) else "per anno")]), Spacer(0, 12)]
    s += layout.h2("Driver economici e finanziari", after=6)
    s += [layout.fin_table([f"{y} P" for y in years],
                           [(r.label, [fmt.value(v, r.unit) for v in r.values], "") for r in data.assumptions],
                           first="Driver"), Spacer(0, 10)]
    head = layout.h2("Aree del piano", after=6)
    rows = [[Paragraph("Area", layout.ST["cellh"]), Paragraph("Contenuto delle ipotesi", layout.ST["cellh"])]] + \
        [[Paragraph(a, layout.ST["cellb"]), Paragraph(b, layout.ST["cell"])] for a, b in _AREE]
    t = Table(rows, colWidths=[150, CW - 150])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, C(theme.RULE)),
                           ("TOPPADDING", (0, 0), (-1, -1), 4.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 4.6)]))
    # indivisibile: sul piano a 5 anni la tabella si spezzava lasciando la sola riga «Imposte» su una pagina
    return s + [KeepTogether(head + [t])]
