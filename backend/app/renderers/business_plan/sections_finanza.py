"""Sezioni 6–8: sostenibilità del debito, circolante commerciale, solidità e redditività."""
from __future__ import annotations

from reportlab.platypus import Spacer

from . import charts, fmt, layout, narrative
from .data import BusinessPlanData
from .sections_economia import headers, labels, row, tile_from


def _others(data: BusinessPlanData, key: str) -> str:
    y = [f"{fmt.ratio(data.v(key)[i])} nel {data.columns[i].year}" for i in data.plan_idx[:-1]]
    return " · ".join(y) if y else ""


def debito(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 6", "Sostenibilità del debito · DSCR e PFN",
                            "PFN = debiti finanziari meno disponibilità liquide. Il DSCR è calcolato come proxy: "
                            "(EBITDA − imposte) / oneri finanziari, senza la quota capitale.")
    last = data.last.year
    s += [layout.tiles([(fmt.ratio(data.v("dscr")[-1]), f"DSCR {last} (proxy)", _others(data, "dscr")),
                        tile_from(data, "pfn_ebitda", "PFN / EBITDA", fmt.ratio),
                        tile_from(data, "pfn", "PFN", fmt.compact_eur),
                        tile_from(data, "of_mol", "Oneri finanziari / MOL", fmt.pct)]), Spacer(0, 2)]
    # ordine e larghezze del riferimento (pagina 8): prima DSCR e PFN/EBITDA a 429 pt, poi il debito a 399 pt
    s += [layout.chart(charts.dscr_pfn(labels(data), data.v("dscr"), data.v("pfn_ebitda")),
                       charts.HEIGHTS["dscr_pfn"], 429.1), Spacer(0, 4)]
    s += layout.h2("Debiti finanziari, liquidità, PFN e patrimonio netto (€ migliaia)")
    s += [layout.chart(charts.debito(labels(data), data.v("debiti_finanziari"), data.v("liquidita"),
                                     data.v("patrimonio_netto"), data.v("pfn")), charts.HEIGHTS["debito"], 399.1),
          Spacer(0, 6)]
    rows = [row(data, "Debiti verso banche", "banche"), row(data, "di cui entro 12 mesi", "banche_breve"),
            row(data, "di cui oltre 12 mesi", "banche_lungo"),
            row(data, "Debiti finanziari (convenzione PFN)", "debiti_finanziari", "bold"),
            row(data, "Disponibilità liquide", "liquidita"), row(data, "Posizione finanziaria netta (PFN)", "pfn", "hl"),
            row(data, "PFN / EBITDA", "pfn_ebitda", unit="ratio"), row(data, "DSCR — proxy", "dscr", "hl", "ratio"),
            row(data, "Oneri finanziari / MOL", "of_mol", unit="percent"),
            row(data, "Oneri finanziari / ricavi", "of_ricavi", unit="percent"),
            row(data, "ROD (costo del denaro)", "rod", unit="percent")]
    notes = []
    if data.partial_label and data.partial_dscr is not None:
        notes.append(f"DSCR proxy nel progressivo rettificato {data.partial_label}: {fmt.ratio(data.partial_dscr)}.")
    other = data.v("altri_finanziatori")
    if any(v not in (None, 0) for v in other):
        notes.append(f"Debiti verso altri finanziatori: € {fmt.eur(other[-1])} nel {last}, fuori dalla PFN per la "
                     "convenzione del motore degli indici.")
    s += [layout.fin_table(headers(data), rows, first="Indicatore", pad=3.8)]
    if notes:
        s += [Spacer(0, 5), layout.note(" ".join(notes))]
    return s


def circolante(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 7", "Capitale circolante commerciale",
                            "Crediti commerciali, rimanenze e debiti commerciali. I giorni vengono dal motore degli "
                            "indici, su base 360 e sull'intero circolante.")
    s += [layout.tiles([tile_from(data, "cc_comm", "Circolante commerciale", fmt.compact_eur),
                        tile_from(data, "dso", "Giorni di credito (DSO)", lambda v: f"{fmt.eur(v)} gg"),
                        tile_from(data, "dio", "Giorni di magazzino (DIO)", lambda v: f"{fmt.eur(v)} gg"),
                        tile_from(data, "dpo", "Giorni di debito (DPO)", lambda v: f"{fmt.eur(v)} gg")]),
          Spacer(0, 6),
          layout.chart(charts.circolante(labels(data), data.v("dso"), data.v("dio"), data.v("dpo"), data.v("cc_comm")),
                       charts.HEIGHTS["circolante"]), Spacer(0, 6)]
    s += [layout.fin_table(headers(data), [
        row(data, "Crediti commerciali (clienti entro e oltre 12 mesi)", "crediti_comm"),
        row(data, "Rimanenze", "rimanenze"), row(data, "Debiti commerciali (fornitori)", "debiti_comm", sign=-1),
        row(data, "Capitale circolante commerciale", "cc_comm", "hl"),
        row(data, "Giorni di credito · DSO", "dso", unit="days"),
        row(data, "Giorni di magazzino · DIO", "dio", unit="days"),
        row(data, "Giorni di debito · DPO", "dpo", unit="days"),
        row(data, "Ciclo di conversione del denaro", "ciclo", "hl", "days")]), Spacer(0, 8)]
    lettura = narrative.lettura_circolante(data)
    if lettura:
        s.append(layout.panel("Lettura", [("", t) for t in lettura]))
    return s


def solidita(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 8", "Solidità patrimoniale, liquidità e redditività",
                            "Saldi di fine esercizio.")
    s += [layout.tiles([tile_from(data, "patrimonio_netto", "Patrimonio netto", fmt.compact_eur),
                        tile_from(data, "indipendenza", "Indipendenza finanziaria", fmt.pct),
                        tile_from(data, "liquidita_corrente", "Liquidità corrente", fmt.ratio),
                        tile_from(data, "margine_struttura", "Margine di struttura", fmt.compact_eur)]), Spacer(0, 10)]
    s += layout.h2("Stato patrimoniale di sintesi", after=4)
    s += [layout.fin_table(headers(data), [
        row(data, "Immobilizzazioni nette", "immobilizzazioni"), row(data, "Rimanenze", "rimanenze"),
        row(data, "Crediti commerciali", "crediti_comm"), row(data, "Disponibilità liquide", "liquidita"),
        row(data, "Altre attività", "altre_attivita"), row(data, "Totale attivo", "totale_attivo", "hl"),
        row(data, "Patrimonio netto", "patrimonio_netto"),
        row(data, "Debiti finanziari (convenzione PFN)", "debiti_finanziari"),
        row(data, "Altre passività", "altre_passivita"), row(data, "di cui debiti commerciali", "debiti_comm"),
        row(data, "Totale passivo e patrimonio netto", "totale_attivo", "hl")], pad=3.8), Spacer(0, 4),
        layout.note("Le altre passività comprendono debiti commerciali, TFR, debiti tributari e previdenziali, altri "
                    "debiti, debiti verso altri finanziatori e ratei e risconti passivi. Dettaglio nell'Allegato B."),
        Spacer(0, 10)]
    s += layout.h2("Margini strutturali e liquidità", after=6)
    s += [layout.fin_table(headers(data), [
        row(data, "Capitale circolante netto (CCN)", "ccn"), row(data, "Margine di tesoreria", "margine_tesoreria"),
        row(data, "Margine di struttura", "margine_struttura"),
        row(data, "Liquidità corrente", "liquidita_corrente", unit="ratio"),
        row(data, "Liquidità immediata", "liquidita_immediata", unit="ratio"),
        row(data, "Indipendenza finanziaria", "indipendenza", unit="percent"),
        row(data, "Copertura immobilizzazioni", "copertura_immob", unit="percent")], first="Indicatore", pad=3.8), Spacer(0, 10)]
    s += layout.h2("Redditività", after=6)
    s += [layout.fin_table(headers(data), [
        row(data, "ROI", "roi", unit="percent"), row(data, "ROE", "roe", unit="percent"),
        row(data, "ROS (EBIT / ricavi)", "ros", unit="percent"),
        row(data, "EBITDA margin", "ebitda_margin", unit="percent"),
        row(data, "Spread (ROI − ROD)", "spread", "hl", "percent")], first="Indicatore", pad=3.8)]
    return s
