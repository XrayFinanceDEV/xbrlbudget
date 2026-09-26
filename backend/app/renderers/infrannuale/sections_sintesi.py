"""Copertina con i numeri chiave e l'indice, sezione 1 (sintesi, forza/debolezza, azioni)."""
from __future__ import annotations

from reportlab.lib.colors import HexColor, white
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.renderers.business_plan import fmt, layout, theme
from app.renderers.business_plan.sections_sintesi import _card, _chip_tiles, _cover_name
from app.renderers.business_plan.theme import BOLD, CW, LM, PAGE_H, PAGE_W, REGULAR

from . import narrative
from . import sections as sec
from .data import INFRANNUALE, PROIEZIONE, STORICO, InfrannualeData
from .sections import VALUE, signed_pct

C = HexColor

INDEX = [  # (numero, titolo dell'indice, chiave di sezione)
    ("1", "Sintesi · punti di forza, di debolezza e azioni prioritarie", "sintesi"),
    ("2", "Conto economico: infrannuale, annualizzato e forecast", "economia"),
    ("3", "EBITDA margin e struttura dei costi", "costi"),
    ("4", "Stato patrimoniale", "patrimonio"),
    ("5", "Capitale circolante commerciale e liquidità", "circolante"),
    ("6", "Indebitamento e sostenibilità del debito", "debito"),
    ("7", "Indicatori della crisi d'impresa", "crisi"),
    ("8", "Segnali extracontabili", "segnali"),
    ("", "Allegati A–B · prospetti completi", "allegato_a"),
]


def _last(d: InfrannualeData) -> str:
    return PROIEZIONE if d.has_forecast else INFRANNUALE


def cover_lines(d: InfrannualeData) -> layout.CoverLines:
    """I testi della fascia di copertina: gli stessi nel PDF e nel Word."""
    forecast = f"forecast {d.partial_year}" if d.has_forecast else "forecast non ancora generato"
    return layout.CoverLines(f"REPORT INFRANNUALE {d.partial_label}", d.company_name,
                      f"Situazione al {d.period_end}" + (" e forecast a fine anno" if d.has_forecast else ""),
                      (f"Bilancio infrannuale di {d.period_months} mesi · confronto con il consuntivo "
                       f"{d.reference_year} · {forecast}",
                       "Andamento economico, struttura patrimoniale, circolante, debito e indicatori della crisi d'impresa"))


def draw_cover_band(canvas, d: InfrannualeData) -> None:
    """Fascia navy della copertina (0–283,5 pt dall'alto) con filetto teal: la stessa del Business plan."""
    theme.register_fonts()
    canvas.saveState()
    canvas.setFillColor(C(theme.NAVY))
    canvas.rect(0, PAGE_H - 283.5, PAGE_W, 283.5, stroke=0, fill=1)
    canvas.setFillColor(C(theme.TEAL))
    canvas.rect(0, PAGE_H - 289.1, PAGE_W, 5.6, stroke=0, fill=1)
    canvas.setFillColor(white)
    canvas.setFont(BOLD, 10)
    cl = cover_lines(d)
    canvas.drawString(LM, PAGE_H - 64, cl.eyebrow)
    size, lines = _cover_name(cl.name)
    canvas.setFont(BOLD, size)
    if len(lines) == 1:
        canvas.drawString(LM, PAGE_H - 122, lines[0])
    else:
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


def _cover_kpis(d: InfrannualeData) -> list:
    v, last, rif = d.v, _last(d), d.reference_year
    ll, cl = d.label_of(last), d.reference_label
    fc = "forecast" if d.has_forecast else "del periodo"
    esito = lambda k: narrative.esito(d.crisi[last].punteggi.get(k)) if last in d.crisi else None  # noqa: E731
    span = f"{cl} → {ll}"
    semestre = "del semestre" if d.period_months == 6 else f"dei {d.period_months} mesi"
    items = [
        (d.partial_label, fmt.compact_eur(v("ricavi", INFRANNUALE)), f"Ricavi delle vendite {semestre}",
         f"EBITDA {fmt.compact_eur(v('ebitda', INFRANNUALE))} · margin {fmt.pct(v('ebitda_margin', INFRANNUALE))}"),
    ]
    if d.has_forecast:
        items += [
            (f"{ll} vs {cl}", fmt.compact_eur(v("ricavi", last)), "Ricavi delle vendite forecast",
             f"{signed_pct(d.var('ricavi', last))} sul consuntivo {rif} ({fmt.compact_eur(v('ricavi', STORICO))})"),
            (ll, fmt.compact_eur(v("ebitda", last)), "EBITDA forecast",
             f"EBITDA margin {fmt.pct(v('ebitda_margin', last))} · {signed_pct(d.var('ebitda', last))} sul {rif}"),
            (ll, fmt.compact_eur(v("risultato_netto", last)), "Utile netto forecast",
             f"{fmt.compact_eur(v('risultato_netto', STORICO))} nel consuntivo {rif}"),
        ]
    else:
        items += [
            (cl, fmt.compact_eur(v("ricavi", STORICO)), "Ricavi delle vendite consuntivo", f"esercizio {rif}"),
            (d.partial_label, fmt.compact_eur(v("ebitda", INFRANNUALE)), f"EBITDA {fc}",
             f"{fmt.compact_eur(v('ebitda', STORICO))} nel consuntivo {rif}"),
            (d.partial_label, fmt.compact_eur(v("risultato_netto", INFRANNUALE)), f"Risultato netto {fc}",
             f"{fmt.compact_eur(v('risultato_netto', STORICO))} nel consuntivo {rif}"),
        ]
    r2 = lambda k: f"{fmt.ratio(v(k, STORICO), 2)} → {fmt.ratio(v(k, last), 2)}"  # noqa: E731
    items += [
        (span, fmt.compact_range(v("pfn", STORICO), v("pfn", last)), "Posizione finanziaria netta",
         "debiti finanziari − liquidità"),
        (span, r2("pfn_ebitda"), "PFN / EBITDA", f"indicatore {esito('pfn_ebitda') or 'n.d.'}"),
        (span, r2("dscr"), "DSCR", f"indicatore {esito('dscr') or 'n.d.'}"),
    ]
    attivi = sum(1 for s in d.segnali if s[2])
    if last in d.crisi:
        sub = f"{attivi} su {len(d.segnali)} segnali extracontabili"
        if d.has_forecast and INFRANNUALE in d.crisi:
            sub = f"{d.crisi[INFRANNUALE].classe} nel {d.partial_label} · " + sub
        items.append((ll, d.crisi[last].classe, "Classe di rischio", sub))
    else:
        items.append((ll, fmt.ND, "Classe di rischio", f"{attivi} su {len(d.segnali)} segnali extracontabili"))
    return items


def _index_table(d: InfrannualeData, pages: dict) -> Table:
    num = layout._ps("in", BOLD, 9.8, 12, theme.TEAL)
    tit = layout._ps("it", REGULAR, 9.8, 12, theme.INK)
    pg = layout._ps("ip", REGULAR, 9.8, 12, theme.MUTED, alignment=2)
    rows = [[Paragraph(n, num), Paragraph(sec.titolo_economia(d) if key == "economia" else title, tit), Paragraph(str(pages.get(key, "")), pg)]
            for n, title, key in INDEX]
    t = Table(rows, colWidths=[22, CW - 22 - 40, 40], rowHeights=19.2)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, C(theme.RULE)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    return t


def copertina(d: InfrannualeData, pages: dict) -> list:
    return layout.h2("I numeri chiave", after=6) + [_chip_tiles(_cover_kpis(d)), Spacer(0, 14)] + \
        layout.h2("Indice", after=4) + [_index_table(d, pages)]


def _cruscotto(d: InfrannualeData) -> Table:
    cs = [c for c in (STORICO, INFRANNUALE, PROIEZIONE) if c in {x.key for x in d.sp_cols}]
    g = lambda label: (label, [], "group")  # noqa: E731

    def r(label, key, style="", unit="eur"):
        f = {"eur": fmt.eur, "pct": fmt.pct, "ratio": lambda x: fmt.ratio(x, 3)}[unit]
        return (label, [f(d.v(key, c)) for c in cs], style)

    tot = sum(1 for x in d.definizioni if x[3]) or 14
    classe = ("Classe di rischio", [d.crisi[c].classe if c in d.crisi else fmt.ND for c in cs], "hl")
    oltre = ("Indicatori oltre soglia", [f"{d.crisi[c].oltre} su {tot}" if c in d.crisi else fmt.ND for c in cs], "")
    rows = [g("Conto economico"), r("Ricavi delle vendite", "ricavi"), r("EBITDA", "ebitda"),
            r("EBITDA margin", "ebitda_margin", "hl", "pct"), r("Risultato netto", "risultato_netto"),
            g("Patrimonio e debito"), r("Totale attivo", "totale_attivo"), r("Patrimonio netto", "patrimonio_netto"),
            r("Posizione finanziaria netta (PFN)", "pfn"), r("PFN / EBITDA ¹", "pfn_ebitda", unit="ratio"),
            r("DSCR", "dscr", "hl", "ratio"),
            g("Circolante e liquidità"), r("Capitale circolante commerciale ²", "cc_comm"),
            r("Disponibilità liquide", "liquidita"), r("Liquidità corrente", "current_ratio", unit="ratio"),
            g("Crisi d'impresa"), classe, oltre]
    return layout.fin_table([d.label_of(c) for c in cs], rows, first="Voce", value_size=VALUE, value_width=98)


def sintesi(d: InfrannualeData, pages: dict) -> list:
    m = d.period_months
    periodo = "semestre" if m == 6 else f"periodo di {m} mesi"
    testa = f"Il {periodo} al {d.period_end}, il forecast a fine anno " if d.has_forecast else \
        f"Il {periodo} al {d.period_end} "
    sub = testa + (
           f"e il consuntivo {d.reference_year} sono tenuti distinti in tutto il documento. Ricavi e risultati del "
           f"{m}M si riferiscono a {'sei' if m == 6 else m} mesi; lo stato patrimoniale è puntuale alla data.")
    s = layout.section_head("SEZIONE 1", "Sintesi", sub)
    kp = narrative.key_points(d)
    if kp:
        s += [layout.panel("Punti chiave", [(a, b) for a, b in kp]), Spacer(0, 12)]
    s += layout.h2("Cruscotto", after=6) + [_cruscotto(d), Spacer(0, 5),
          layout.note((f"¹ Per il {d.partial_label} gli indicatori reddituali sono calcolati su base annualizzata. "
                       if d.has_annualized else f"¹ Indicatori reddituali calcolati sui {m} mesi del periodo. ") +
                      "² Crediti verso clienti + rimanenze − debiti verso fornitori, calcolato sui saldi dello stato "
                      "patrimoniale (Sezione 5).")]
    return s


def forza(d: InfrannualeData, pages: dict) -> list:
    m = d.period_months
    periodo = "sul semestre" if m == 6 else f"sul periodo di {m} mesi"
    sub = (f"Valutazione di sintesi basata sul consuntivo {d.reference_year}, {periodo} al {d.period_end}" +
           (f" e sul forecast {d.partial_year}." if d.has_forecast else "."))
    s = layout.section_head("SEZIONE 1 · SEGUE", "Punti di forza, di debolezza e azioni prioritarie", sub)
    strengths, weaknesses = narrative.strengths_weaknesses(d)
    w = (CW - 11.4) / 2
    pair = Table([[_card("Punti di forza", theme.TEAL, theme.HL, strengths, w),
                   _card("Punti di debolezza", theme.RED, theme.WEAK, weaknesses, w)]], colWidths=[w, w])
    # le due colonne alte uguali, come nel riferimento: il fondo si allunga alla più alta
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                              ("BACKGROUND", (0, 0), (0, 0), C(theme.HL)), ("BACKGROUND", (1, 0), (1, 0), C(theme.WEAK))]))
    pair.hAlign = "CENTER"
    s += [pair]
    azioni = narrative.actions(d, weaknesses)
    if not azioni:
        return s
    s += [Spacer(0, 12)] + layout.h2("Azioni prioritarie", after=6)
    num = layout._ps("an", BOLD, 11, 13, theme.TEAL)
    rows = [[Paragraph("#", layout.ST["cellh"]), Paragraph("Azione", layout.ST["cellh"]),
             Paragraph("Contenuto", layout.ST["cellh"]), Paragraph("Indicatori da monitorare", layout.ST["cellh"])]]
    for i, (title, text, kpi) in enumerate(azioni, start=1):
        rows.append([Paragraph(str(i), num), Paragraph(title, layout.ST["cellb"]), Paragraph(text, layout.ST["cell"]),
                     Paragraph(kpi, layout.ST["ks"])])
    t = Table(rows, colWidths=[24, 110, CW - 24 - 110 - 120, 120], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C("#ffffff"), C(theme.PANEL)]),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return s + [t]
