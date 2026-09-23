"""Sezioni 2–8 del report infrannuale. Misure della pagina prese dal riferimento (spike: 0,2 pt)."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from app.renderers.business_plan import fmt, layout, theme
from app.renderers.business_plan.layout import ST, _ps
from app.renderers.business_plan.theme import CW

from . import charts, narrative
from .data import ANNUALIZZATO, INFRANNUALE, PROIEZIONE, STORICO, InfrannualeData

C = HexColor
CHART_W = 459.0      # grafici a tutta pagina, centrati (1584 px a ~248 dpi)
CHART_W_CRISI = 439.1
PAD, HEAD_PAD, VALUE, LABEL = 3.55, 4.0, 9.8, 8.0


# ------------------------------------------------------------------ primitive della pagina
def table(headers: list, rows: list, first: str = "Voce (euro)") -> Table:
    t = layout.fin_table(headers, rows, first=first, pad=PAD, value_size=VALUE, label_size=LABEL)
    t.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, 0), HEAD_PAD), ("BOTTOMPADDING", (0, 0), (-1, 0), HEAD_PAD)]))
    return t


def chart(png: bytes, key: str, width: float = CHART_W):
    return layout.chart(png, charts.HEIGHTS[key], width)


def signed_pct(v: Optional[Decimal]) -> str:
    """«+11,92%» / «−14,19%»: variazione con il segno esplicito, per i riquadri."""
    if v is None:
        return fmt.ND
    return ("+" if v > 0 else "") + fmt.pct(v)


def cols(d: InfrannualeData, keys) -> list:
    """Le colonne richieste che esistono davvero in questa pratica (CE o SP)."""
    have = {c.key for c in d.ce_cols + d.sp_cols}
    return [k for k in keys if k in have]


def _row(d, label, key, cs, style="", unit="eur", var_cols=()) -> tuple:
    f = {"eur": fmt.eur, "pct": fmt.pct, "ratio": lambda x: fmt.ratio(x, 3)}[unit]
    cells = [f(d.v(key, c)) for c in cs]
    cells += [("" if unit != "eur" else fmt.pct(d.var(key, c))) for c in var_cols]
    return (label, cells, style)


# ------------------------------------------------------------------ sezione 2
def economia(d: InfrannualeData, pages: dict) -> list:
    m, anno, rif = d.period_months, d.partial_year, d.reference_label
    ce = cols(d, (STORICO, INFRANNUALE, ANNUALIZZATO, PROIEZIONE))
    var = cols(d, (ANNUALIZZATO, PROIEZIONE))
    parts = []
    if d.has_annualized:
        parts.append(f"L'annualizzato riporta i {m} mesi a dodici (× 12/{m})")
    if d.has_forecast:
        rest = "sul secondo semestre" if m == 6 else f"sui {12 - m} mesi restanti"
        parts.append(f"il forecast è la stima a fine anno costruita con le ipotesi {rest}, non "
                     "l'annualizzazione aritmetica")
    sub = ("; ".join(parts) + ".") if parts else f"Conto economico dei {m} mesi a confronto con il consuntivo {d.reference_year}."
    sub = sub[0].upper() + sub[1:]
    s = layout.section_head("SEZIONE 2", "Conto economico: infrannuale, annualizzato e forecast", sub)

    t = [(d.partial_label, fmt.compact_eur(d.v("ricavi", INFRANNUALE)), "Ricavi del semestre" if m == 6 else "Ricavi del periodo",
          f"EBITDA {fmt.compact_eur(d.v('ebitda', INFRANNUALE))}")]
    if d.has_annualized:
        t.append((d.label_of(ANNUALIZZATO), fmt.compact_eur(d.v("ricavi", ANNUALIZZATO)), "Ricavi annualizzati",
                  f"{signed_pct(d.var('ricavi', ANNUALIZZATO))} sul {rif}"))
    if d.has_forecast:
        t.append((d.forecast_label, fmt.compact_eur(d.v("ricavi", PROIEZIONE)), "Ricavi forecast",
                  f"{signed_pct(d.var('ricavi', PROIEZIONE))} sul {rif}"))
        t.append((d.forecast_label, fmt.compact_eur(d.v("risultato_netto", PROIEZIONE)), "Utile netto forecast",
                  f"{signed_pct(d.var('risultato_netto', PROIEZIONE))} sul {rif}"))
    else:
        t.append((d.partial_label, fmt.compact_eur(d.v("risultato_netto", INFRANNUALE)), "Utile netto del periodo",
                  f"{fmt.compact_eur(d.v('risultato_netto', STORICO))} nel {rif}"))
    s += [layout.tiles_chip(t[:4]), Spacer(0, 5)]

    kinds = {STORICO: "C", INFRANNUALE: "6M", ANNUALIZZATO: "Ann", PROIEZIONE: "F"}
    s += [chart(charts.ricavi_periodi([d.label_of(c) for c in ce], [d.v("ricavi", c) for c in ce],
                                      [d.v("ebitda_margin", c) for c in ce], [kinds[c] for c in ce]),
                "ricavi_periodi")]
    rows = [
        _row(d, "Ricavi delle vendite", "ricavi", ce, var_cols=var),
        _row(d, "Valore della produzione", "valore_produzione", ce, var_cols=var),
        _row(d, "Costi operativi (esclusi ammortamenti)", "costi_operativi", ce, var_cols=var),
        _row(d, "EBITDA (MOL)", "ebitda", ce, "bold", var_cols=var),
        _row(d, "EBITDA margin", "ebitda_margin", ce, "hl", unit="pct", var_cols=var),
        _row(d, "Ammortamenti e svalutazioni", "ammortamenti", ce, var_cols=var),
        _row(d, "EBIT", "ebit", ce, "bold", var_cols=var),
        _row(d, "Altri proventi finanziari", "altri_proventi_fin", ce, var_cols=var),
        _row(d, "Oneri finanziari", "oneri_finanziari", ce, var_cols=var),
        _row(d, "Risultato ante imposte", "risultato_ante_imposte", ce, "bold", var_cols=var),
        _row(d, "Imposte", "imposte", ce, var_cols=var),
        _row(d, "Risultato netto", "risultato_netto", ce, "hl", var_cols=var),
    ]
    heads = [d.label_of(c) for c in ce] + [f"{'Ann.' if c == ANNUALIZZATO else 'F'} / C" for c in var]
    s += [table(heads, rows), Spacer(0, 5),
          layout.note(f"Variazioni calcolate rispetto al consuntivo {d.reference_year} (C). Il {d.period_months}M non "
                      "è confrontabile direttamente con un esercizio completo. Dettaglio nell'Allegato A.")]
    return s


# ------------------------------------------------------------------ sezione 4
def patrimonio(d: InfrannualeData, pages: dict) -> list:
    sp = cols(d, (STORICO, INFRANNUALE, PROIEZIONE))
    var = cols(d, (INFRANNUALE, PROIEZIONE))
    rif = d.reference_label
    sub = (f"Lo stato patrimoniale è puntuale: i valori al {d.period_end} non si annualizzano e si confrontano con il "
           f"consuntivo {d.reference_year}")
    sub += (f"; il forecast rappresenta i saldi attesi al 31.12.{d.partial_year}." if d.has_forecast else ".")
    s = layout.section_head("SEZIONE 4", "Stato patrimoniale", sub)
    last = PROIEZIONE if d.has_forecast else INFRANNUALE
    ll = d.label_of(last)
    t = [(d.partial_label, fmt.compact_eur(d.v("totale_attivo", INFRANNUALE)), "Totale attivo",
          f"{signed_pct(d.var('totale_attivo', INFRANNUALE))} sul {rif}")]
    if d.has_forecast:
        t.append((ll, fmt.compact_eur(d.v("totale_attivo", last)), "Totale attivo",
                  f"{signed_pct(d.var('totale_attivo', last))} sul {rif}"))
    t += [(ll, fmt.compact_eur(d.v("patrimonio_netto", last)), "Patrimonio netto",
           f"{signed_pct(d.var('patrimonio_netto', last))} sul {rif}"),
          (ll, fmt.compact_eur(d.v("debiti_finanziari", last)), "Debiti finanziari",
           f"{signed_pct(d.var('debiti_finanziari', last))} sul {rif}")]
    s += [layout.tiles_chip(t[:4]), Spacer(0, 5)]
    s += [chart(charts.stato_patrimoniale([d.label_of(c) for c in sp],
                                          *[[d.v(k, c) for c in sp] for k in ("totale_attivo", "debiti_finanziari",
                                                                              "debiti_operativi", "patrimonio_netto")]),
                "stato_patrimoniale")]
    rows = [
        _row(d, "Immobilizzazioni", "immobilizzazioni", sp, var_cols=var),
        _row(d, "Attivo circolante", "attivo_circolante", sp, var_cols=var),
        _row(d, "Totale attivo", "totale_attivo", sp, "bold", var_cols=var),
        _row(d, "Patrimonio netto", "patrimonio_netto", sp, "hl", var_cols=var),
        _row(d, "Debiti finanziari", "debiti_finanziari", sp, var_cols=var),
        _row(d, "Debiti operativi", "debiti_operativi", sp, var_cols=var),
        _row(d, "Disponibilità liquide", "liquidita", sp, var_cols=var),
        _row(d, "Capitale circolante netto", "ccn_sp", sp, var_cols=var),
    ]
    heads = [d.label_of(c) for c in sp] + [f"{'6M' if c == INFRANNUALE else 'F'} / C" for c in var]
    r0, r6, rf = (d.v("ratei_attivi", c) for c in (STORICO, INFRANNUALE, PROIEZIONE))
    ratei = f"€ {fmt.eur(r0)} nel {rif}"
    if d.has_forecast and r6 == rf:
        ratei += f", € {fmt.eur(r6)} nel {d.period_months}M e nel forecast"
    else:
        ratei += f", € {fmt.eur(r6)} nel {d.period_months}M" + (f" e € {fmt.eur(rf)} nel forecast" if d.has_forecast else "")
    s += [table(heads, rows), Spacer(0, 5),
          layout.note(f"Il totale attivo comprende i ratei e risconti attivi ({ratei}). Debiti finanziari = debiti "
                      "verso banche + altri finanziatori. Dettaglio nell'Allegato B.")]
    lettura = narrative.lettura_patrimonio(d)
    if lettura:
        s += [Spacer(0, 4.6), layout.panel("Lettura", [("", x) for x in lettura])]
    return s


# ------------------------------------------------------------------ sezione 7
CRISI_LABEL = {"dscr": "DSCR", "ebitda_margin": "EBITDA %", "mt": "Margine di tesoreria", "ccn": "CCN",
               "current_ratio": "Liquidità corrente", "ms": "Margine di struttura",
               "copertura_immob": "Copertura immobilizzazioni", "indipendenza": "Indipendenza finanziaria",
               "pfn": "PFN", "pfn_ebitda": "PFN / EBITDA", "roi": "ROI", "roe": "ROE", "ros": "ROS",
               "of_mol": "Oneri finanziari / MOL", "of_revenue": "Oneri finanziari / fatturato"}


def crisi_value(v, formato: str) -> str:
    if formato == "euro":
        return fmt.eur(v)
    if formato == "pct":
        return fmt.pct(v)
    return fmt.ratio(v, 3)


def crisi_table(d: InfrannualeData) -> Table:
    cc = [k for k in (STORICO, INFRANNUALE, PROIEZIONE) if k in d.crisi]
    last = cc[-1] if cc else None
    vs = _ps("iv", theme.REGULAR, VALUE, VALUE * 1.15, alignment=TA_RIGHT)
    lab = _ps("il", theme.REGULAR, LABEL, LABEL * 1.15)
    heads = [d.label_of(c) for c in cc] + ([f"Esito {d.label_of(last)}"] if last else [])
    data = [[Paragraph("Indicatore", ST["cellh"])] + [Paragraph(h, ST["valueh"]) for h in heads]]
    for chiave, _, formato, nel in d.definizioni:
        label = CRISI_LABEL.get(chiave, chiave) + ("" if nel else " ¹")
        row = [Paragraph(label, lab)] + [Paragraph(crisi_value(d.v(chiave, c), formato), vs) for c in cc]
        if last:
            e = narrative.esito(d.crisi[last].punteggi.get(chiave))
            row.append(Paragraph(e or fmt.ND, _ps("ie", theme.BOLD, VALUE, VALUE * 1.15,
                                                  narrative.ESITO_COLORE.get(e, theme.MUTED), alignment=TA_RIGHT)))
        data.append(row)
    n = len(heads)
    t = Table(data, colWidths=[CW - n * 82] + [82] * n)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                           ("TOPPADDING", (0, 0), (-1, -1), PAD), ("BOTTOMPADDING", (0, 0), (-1, -1), PAD),
                           ("TOPPADDING", (0, 0), (-1, 0), HEAD_PAD), ("BOTTOMPADDING", (0, 0), (-1, 0), HEAD_PAD),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, C(theme.RULE))]))
    return t


def crisi(d: InfrannualeData, pages: dict) -> list:
    s = layout.section_head(
        "SEZIONE 7", "Indicatori della crisi d'impresa",
        "Quattordici indicatori con punteggio da 0 a 1 e sette segnali extracontabili compongono la classe di rischio, "
        "da A3 (nessun rischio) a D (crisi). «Oltre soglia» indica un punteggio inferiore a 0,33.")
    cc = [k for k in (STORICO, INFRANNUALE, PROIEZIONE) if k in d.crisi]
    tot = sum(1 for x in d.definizioni if x[3]) or 14
    tiles = [(d.label_of(c), d.crisi[c].classe, "Classe di rischio", f"{d.crisi[c].oltre} su {tot} oltre soglia")
             for c in cc]
    attivi = sum(1 for x in d.segnali if x[2])
    span = f"{d.label_of(cc[0])} – {d.label_of(cc[-1])}" if cc else d.partial_label
    tiles.append((span, f"{attivi} su {len(d.segnali)}", "Segnali extracontabili attivi", "in tutti i periodi"))
    s += [layout.tiles_chip(tiles[:4], value_style="kv13"), Spacer(0, 5)]
    if cc:
        s += [chart(charts.crisi([d.label_of(c) for c in cc], [d.crisi[c].oltre for c in cc], tot,
                                 [d.crisi[c].classe for c in cc]), "crisi", CHART_W_CRISI)]
    s += [crisi_table(d), Spacer(0, 5),
          layout.note(f"¹ Riportato per completezza: non entra nella determinazione della classe di rischio. Per il "
                      f"{d.partial_label} gli indicatori reddituali sono su base annualizzata.")]
    return s


# ------------------------------------------------------------------ sezione 3
CHART_W_RISULTATI = 329.3  # nel riferimento il grafico dei risultati sta a 329 pt, centrato


def _incidenza_row(d, label, key, cs, style="") -> tuple:
    cells = []
    for c in cs:
        x, r = d.v(key, c), d.v("ricavi", c)
        cells.append(fmt.pct(abs(x) / r * 100) if x is not None and r else fmt.ND)
    return (label, cells, style)


def costi(d: InfrannualeData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 3", "EBITDA margin e struttura dei costi",
                            "Costi della produzione per natura e loro incidenza sui ricavi delle vendite.")
    ce = cols(d, (STORICO, INFRANNUALE, ANNUALIZZATO, PROIEZIONE))
    graf = cols(d, (STORICO, ANNUALIZZATO, PROIEZIONE)) if d.has_annualized else cols(d, (STORICO, INFRANNUALE))
    s += layout.h2("EBITDA, EBIT e utile netto (€ migliaia)", after=0)
    s += [chart(charts.risultati([d.label_of(c) for c in graf], *[[d.v(k, c) for c in graf]
                                                                   for k in ("ebitda", "ebit", "risultato_netto")]),
                "risultati", CHART_W_RISULTATI)]
    rows = [_row(d, "Materie prime, sussidiarie, di consumo e merci", "materie", ce),
            _row(d, "Servizi", "servizi", ce), _row(d, "Godimento di beni di terzi", "godimento", ce),
            _row(d, "Personale", "personale", ce), _row(d, "Variazione rimanenze materie prime", "var_rim_materie", ce),
            _row(d, "Oneri diversi di gestione", "oneri_diversi", ce),
            _row(d, "Costi operativi (esclusi ammortamenti)", "costi_operativi", ce, "bold"),
            _row(d, "Ammortamenti e svalutazioni", "ammortamenti", ce),
            _row(d, "Totale costi della produzione", "totale_costi_produzione", ce, "bold"),
            _row(d, "EBITDA margin", "ebitda_margin", ce, "hl", unit="pct")]
    s += [table([d.label_of(c) for c in ce], rows), Spacer(0, 10)]
    inc = cols(d, (STORICO, INFRANNUALE, PROIEZIONE))
    s += layout.h2("Incidenza dei costi sui ricavi delle vendite", after=6)
    irows = [_incidenza_row(d, "Materie prime", "materie", inc), _incidenza_row(d, "Servizi", "servizi", inc),
             _incidenza_row(d, "Godimento di beni di terzi", "godimento", inc),
             _incidenza_row(d, "Personale", "personale", inc),
             _incidenza_row(d, "Oneri diversi di gestione", "oneri_diversi", inc),
             _incidenza_row(d, "Costi operativi (esclusi ammortamenti)", "costi_operativi", inc, "bold"),
             _incidenza_row(d, "Oneri finanziari", "oneri_finanziari", inc)]
    note = f"Per il {'semestre' if d.period_months == 6 else 'periodo'} l'incidenza coincide con quella dell'annualizzato."
    over = [c for c in inc if d.v("costi_operativi", c) is not None and d.v("ricavi", c)
            and d.v("costi_operativi", c) > d.v("ricavi", c)]
    if over:
        note += (" Costi operativi oltre il 100% dei ricavi delle vendite: il margine è sostenuto da variazione dei "
                 "lavori in corso e altri ricavi, inclusi nel valore della produzione.")
    s += [table([d.label_of(c) for c in inc], irows, first="Incidenza su ricavi delle vendite"), Spacer(0, 5),
          layout.note(note)]
    lettura = narrative.lettura_costi(d)
    if lettura:
        s += [Spacer(0, 4.6), layout.panel("Lettura", [("", x) for x in lettura])]
    return s


# ------------------------------------------------------------------ sezione 5
def circolante(d: InfrannualeData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 5", "Capitale circolante commerciale e liquidità",
                            "Crediti verso clienti, rimanenze e debiti verso fornitori ai saldi di fine periodo; "
                            "margini ed equilibrio di breve termine.")
    sp = cols(d, (STORICO, INFRANNUALE, PROIEZIONE))
    last = PROIEZIONE if d.has_forecast else INFRANNUALE
    rif = d.reference_label
    k0, kl = d.v("cc_comm", STORICO), d.v("cc_comm", last)
    delta = None if k0 is None or kl is None else kl - k0
    delta_txt = fmt.ND if delta is None else ("+" if delta > 0 else "") + fmt.compact_eur(delta)
    t = [(rif, fmt.compact_eur(k0), "Circolante commerciale", "consuntivo"),
         (d.partial_label, fmt.compact_eur(d.v("cc_comm", INFRANNUALE)), "Circolante commerciale",
          f"al {d.period_end}")]
    if d.has_forecast:
        t.append((d.forecast_label, fmt.compact_eur(kl), "Circolante commerciale", f"{delta_txt} sul {rif}"))
    t.append((d.label_of(last), fmt.compact_eur(d.v("liquidita", last)), "Disponibilità liquide",
              f"da € {fmt.eur(d.v('liquidita', STORICO))} nel {rif}"))
    s += [layout.tiles_chip(t[:4]), Spacer(0, 5)]
    forn = [d.v("fornitori", c) for c in sp]
    s += [chart(charts.circolante([d.label_of(c) for c in sp], [d.v("crediti_clienti", c) for c in sp],
                                  [d.v("rimanenze", c) for c in sp], [None if x is None else -x for x in forn],
                                  [d.v("cc_comm", c) for c in sp]), "circolante")]
    neg = ("Debiti verso fornitori", [fmt.eur(None if x is None else -x) for x in forn], "")
    rows = [_row(d, "Crediti verso clienti (entro e oltre 12 mesi)", "crediti_clienti", sp),
            _row(d, "Rimanenze", "rimanenze", sp), neg,
            _row(d, "Capitale circolante commerciale", "cc_comm", sp, "hl"),
            _row(d, "Disponibilità liquide", "liquidita", sp), _row(d, "Margine di tesoreria", "mt", sp),
            _row(d, "Capitale circolante netto (indicatore)", "ccn", sp),
            _row(d, "Liquidità corrente", "current_ratio", sp, unit="ratio")]
    s += [table([d.label_of(c) for c in sp], rows), Spacer(0, 5),
          layout.note("Il capitale circolante netto è riportato secondo la definizione usata negli indicatori della "
                      "crisi d'impresa (Sezione 7); nello stato patrimoniale sintetico (Sezione 4) è calcolato con una "
                      "diversa aggregazione.")]
    lettura = narrative.lettura_circolante(d)
    if lettura:
        s += [Spacer(0, 4.6), layout.panel("Lettura", [("", x) for x in lettura])]
    return s


# ------------------------------------------------------------------ sezione 6
def _scadenza(d: InfrannualeData, key: str, cs) -> str:
    """« (oltre 12 mesi)» quando il debito sta tutto da una parte in ogni periodo, come nel riferimento."""
    b = [d.v(f"{key}_breve", c) for c in cs]
    lo = [d.v(f"{key}_lungo", c) for c in cs]
    if any(x is None for x in b + lo):
        return ""
    if all(x == 0 for x in b) and any(x for x in lo):
        return " (oltre 12 mesi)"
    if all(x == 0 for x in lo) and any(x for x in b):
        return " (entro 12 mesi)"
    return ""


def debito(d: InfrannualeData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 6", "Indebitamento e sostenibilità del debito",
                            f"PFN = debiti finanziari meno disponibilità liquide. Per il {d.partial_label} PFN/EBITDA è "
                            "calcolato sull'EBITDA annualizzato.")
    cs = cols(d, (STORICO, INFRANNUALE, PROIEZIONE))
    last = PROIEZIONE if d.has_forecast else INFRANNUALE
    ll, rif = d.label_of(last), d.reference_label
    r2 = lambda k, c: fmt.ratio(d.v(k, c), 2)  # noqa: E731
    storia = lambda k: f"{rif} {r2(k, STORICO)}" + (  # noqa: E731
        f" · {d.period_months}M {r2(k, INFRANNUALE)}" if d.has_forecast else "")
    t = [(ll, fmt.compact_eur(d.v("pfn", last)), "PFN", f"da {fmt.compact_eur(d.v('pfn', STORICO))} nel {rif}"),
         (ll, r2("pfn_ebitda", last), "PFN / EBITDA", storia("pfn_ebitda")),
         (ll, r2("dscr", last), "DSCR", storia("dscr")),
         (ll, fmt.pct(d.v("of_mol", last)), "Oneri finanziari / MOL", f"{fmt.pct(d.v('of_mol', STORICO))} nel {rif}")]
    s += [layout.tiles_chip(t), Spacer(0, 5)]
    s += [chart(charts.debito([d.label_of(c) for c in cs], [d.v("dscr", c) for c in cs],
                              [d.v("pfn_ebitda", c) for c in cs]), "debito", CHART_W_CRISI)]
    breve_altri = [d.v("altri_finanziatori", c) for c in cs]
    rows = [_row(d, "Debiti verso banche", "banche", cs), _row(d, "di cui entro 12 mesi", "banche_breve", cs),
            _row(d, "di cui oltre 12 mesi", "banche_lungo", cs),
            _row(d, "Debiti verso altri finanziatori" + _scadenza(d, "altri_finanziatori", cs), "altri_finanziatori", cs),
            _row(d, "Disponibilità liquide", "liquidita", cs),
            _row(d, "Posizione finanziaria netta (PFN)", "pfn", cs, "bold"),
            _row(d, "PFN / EBITDA", "pfn_ebitda", cs, "hl", unit="ratio"),
            _row(d, "DSCR", "dscr", cs, "hl", unit="ratio"),
            _row(d, "Oneri finanziari / MOL", "of_mol", cs, unit="pct"),
            _row(d, "Oneri finanziari / fatturato", "of_revenue", cs, unit="pct"),
            _row(d, "Indipendenza finanziaria", "indipendenza", cs, unit="pct"),
            _row(d, "Margine di struttura", "ms", cs),
            _row(d, "Copertura immobilizzazioni", "copertura_immob", cs, unit="pct")]
    s += [table([d.label_of(c) for c in cs], rows, first="Indicatore")]
    if any(x for x in breve_altri):
        s += [Spacer(0, 5), layout.note("La PFN è calcolata sui debiti verso banche; i debiti verso altri finanziatori "
                                        "sono esposti separatamente.")]
    return s


# ------------------------------------------------------------------ sezione 8
AREE = {"retribuzioni": "Retribuzioni", "fornitori": "Fornitori", "banche": "Banche", "inps": "INPS",
        "inail": "INAIL", "riscossione": "Agente della Riscossione", "iva": "Agenzia delle Entrate"}


def _definizione(etichetta: str) -> str:
    """«INPS: ritardo di …» → «Ritardo di …», con lo spazio fra € e l'importo."""
    import re
    testo = etichetta.split(": ", 1)[1] if ": " in etichetta[:40] else etichetta
    testo = re.sub(r"€\s?(\d)", r"€ \1", testo)
    return testo[0].upper() + testo[1:]


def segnali(d: InfrannualeData, pages: dict) -> list:
    attivi = [s for s in d.segnali if s[2]]
    n = len(d.segnali)
    stato = (f"Nessuno dei {'sette' if n == 7 else n} segnali risulta attivo." if not attivi else
             f"{len(attivi)} {'segnale risulta attivo' if len(attivi) == 1 else 'segnali risultano attivi'} su {n}.")
    s = layout.section_head("SEZIONE 8", "Segnali extracontabili",
                            "Ogni segnale attivo peggiora la classe di rischio del semestre e del forecast. " + stato)
    num = _ps("sn", theme.BOLD, 9.8, 11.5, theme.TEAL)
    area = _ps("sa", theme.BOLD, 9.0, 11)
    txt = _ps("st", theme.REGULAR, 8.8, 11)
    rows = [[Paragraph(h, ST["cellh"]) for h in ("#", "Area", "Segnale", "Stato")]]
    for i, (chiave, etichetta, attivo) in enumerate(d.segnali, start=1):
        st = _ps("ss", theme.BOLD, 9.0, 11, theme.RED if attivo else theme.TEAL)
        rows.append([Paragraph(str(i), num), Paragraph(AREE.get(chiave, chiave), area),
                     Paragraph(_definizione(etichetta), txt), Paragraph("attivo" if attivo else "non attivo", st)])
    t = Table(rows, colWidths=[26, 86, CW - 26 - 86 - 70, 70], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), C(theme.NAVY)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C("#ffffff"), C(theme.PANEL)]),
                           ("TOPPADDING", (0, 0), (-1, -1), 5.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5)]))
    return s + [t]
