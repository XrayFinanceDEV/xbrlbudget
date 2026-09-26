"""Sezioni 2–5: evoluzione economica, costi, break even, flussi di cassa."""
from __future__ import annotations

from decimal import Decimal

from reportlab.platypus import Spacer

from . import charts, fmt, layout
from .data import BusinessPlanData
from .theme import CW


def row(data: BusinessPlanData, label: str, key: str, style: str = "", unit: str = "eur", sign: int = 1) -> tuple:
    vals = data.v(key)
    return (label, [fmt.value(None if v is None else v * sign, unit) for v in vals], style)


def headers(data: BusinessPlanData) -> list:
    return [c.label for c in data.columns]


def labels(data: BusinessPlanData) -> list:
    return [c.label for c in data.columns]


def ref_phrase(data: BusinessPlanData) -> str:
    plan = data.plan_years
    span = f"{plan[0]}–{plan[-1]}" if len(plan) > 1 else str(plan[0])
    base = next((c for c in data.columns if c.is_base), None)
    if base is None:
        return f"anni di piano {span} (P)"
    word = "forecast" if data.workflow == "infrannuale" else "consuntivo"
    letter = "F" if data.workflow == "infrannuale" else "C"
    return f"{word} {base.year} ({letter}) e anni di piano {span} (P)"


def tile_from(data: BusinessPlanData, key: str, label: str, fmt_fn) -> tuple:
    vals = data.v(key)
    return (fmt_fn(vals[-1]), f"{label} {data.last.year}", f"da {fmt_fn(vals[0])} nel {data.first.label}")


def _sum_plan(data: BusinessPlanData, key: str) -> Decimal | None:
    vals = [data.v(key)[i] for i in data.plan_idx]
    return None if any(v is None for v in vals) else sum(vals, Decimal(0))


def _plan_span(data: BusinessPlanData) -> str:
    y = data.plan_years
    return f"{y[0]}–{y[-1]}" if len(y) > 1 else str(y[0])


def _years_phrase(years: list) -> str:
    if not years:
        return "nessun anno"
    return years[0] if len(years) == 1 else ", ".join(years[:-1]) + " e " + years[-1]


# ---------------------------------------------------------------- sezione 2
def economia(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 2", "Evoluzione economica dell'impresa",
                            f"Gli anni sono confrontati sulla medesima base annuale: {ref_phrase(data)}.")
    s += [layout.tiles([tile_from(data, "ricavi", "Ricavi delle vendite", fmt.compact_eur),
                        tile_from(data, "ebitda", "EBITDA", fmt.compact_eur),
                        tile_from(data, "ebitda_margin", "EBITDA margin", fmt.pct),
                        tile_from(data, "utile", "Utile netto", fmt.compact_eur)]), Spacer(0, 16)]
    s += layout.h2("Ricavi delle vendite ed EBITDA margin")
    s += [layout.chart(charts.ricavi_margine(labels(data), data.v("ricavi"), data.v("ebitda_margin")),
                       charts.HEIGHTS["ricavi_margine"]), Spacer(0, 8)]
    s += layout.h2("Conto economico di sintesi", after=2)
    rows = [row(data, "Ricavi delle vendite e delle prestazioni", "ricavi"),
            row(data, "Variazioni di rimanenze, lavori in corso e incrementi", "var_produzione"),
            row(data, "Altri ricavi e proventi", "altri_ricavi"),
            row(data, "Valore della produzione", "valore_produzione", "bold"),
            row(data, "Costi della produzione (esclusi ammortamenti e svalutazioni)", "costi_operativi"),
            row(data, "EBITDA (MOL)", "ebitda", "hl"),
            row(data, "EBITDA margin", "ebitda_margin", unit="percent"),
            row(data, "Ammortamenti e svalutazioni", "ammortamenti"),
            row(data, "EBIT (risultato operativo)", "ebit", "bold"),
            row(data, "Altri proventi finanziari", "proventi_fin"),
            row(data, "Interessi e altri oneri finanziari", "oneri_fin", sign=-1)]
    if any(v not in (None, 0) for v in data.v("altre_componenti")):
        rows.append(row(data, "Cambi, rettifiche di valore e componenti straordinarie", "altre_componenti"))
    rows += [row(data, "Risultato prima delle imposte", "ante_imposte", "bold"),
             row(data, "Imposte sul reddito", "imposte", sign=-1),
             row(data, "Utile netto dell'esercizio", "utile", "hl")]
    s += [layout.fin_table(headers(data), rows), Spacer(0, 5),
          layout.note("Dettaglio completo nell'Allegato A. Il valore della produzione include le variazioni di "
                      "rimanenze e lavori in corso e gli altri ricavi.")]
    return s


# ---------------------------------------------------------------- sezione 3
def costi(data: BusinessPlanData, pages: dict) -> list:
    from .narrative import lettura_costi
    s = layout.section_head("SEZIONE 3", "EBITDA margin e struttura dei costi",
                            "Composizione dei costi della produzione per natura e loro incidenza sui ricavi.")
    s += layout.h2("EBITDA, EBIT e utile netto")
    s += [layout.chart(charts.risultati(labels(data), data.v("ebitda"), data.v("ebit"), data.v("utile")),
                       charts.HEIGHTS["risultati"], width_pt=349.3), Spacer(0, 8)]
    s += layout.h2("Costi della produzione per natura", after=6)
    rows = [row(data, "Materie prime, sussidiarie, di consumo e merci", "materie"),
            row(data, "Servizi", "servizi"), row(data, "Godimento di beni di terzi", "godimento"),
            row(data, "Personale", "personale"),
            row(data, "Variazione rimanenze materie prime", "var_rim_materie")]
    if any(v not in (None, 0) for v in data.v("accantonamenti")):
        rows.append(row(data, "Accantonamenti", "accantonamenti"))
    rows += [row(data, "Oneri diversi di gestione", "oneri_diversi"),
             row(data, "Costi operativi (prima di ammortamenti)", "costi_operativi", "bold"),
             row(data, "Ammortamenti e svalutazioni", "ammortamenti"),
             row(data, "Totale costi della produzione", "costi_produzione", "bold"),
             row(data, "EBITDA margin", "ebitda_margin", "hl", unit="percent")]
    s += [layout.fin_table(headers(data), rows), Spacer(0, 10)]
    s += layout.h2("Incidenza dei costi sui ricavi delle vendite", after=6)
    inc = [row(data, "Materie prime", "inc_materie", unit="percent"),
           row(data, "Servizi", "inc_servizi", unit="percent"),
           row(data, "Godimento di beni di terzi", "inc_godimento", unit="percent"),
           row(data, "Personale", "inc_personale", unit="percent"),
           row(data, "Oneri diversi di gestione", "inc_oneri_diversi", unit="percent"),
           row(data, "Costi operativi (prima di ammortamenti)", "inc_costi_operativi", "hl", unit="percent"),
           row(data, "Oneri finanziari", "inc_oneri_fin", unit="percent")]
    s += [layout.fin_table(headers(data), inc, first="Incidenza su ricavi delle vendite"), Spacer(0, 10),
          layout.panel("Lettura", [("", t) for t in lettura_costi(data)])]
    return s


# ---------------------------------------------------------------- sezione 4
def pareggio(data: BusinessPlanData, pages: dict) -> list:
    s = layout.section_head("SEZIONE 4", "Costi fissi e variabili · break even point",
                            "Il margine di sicurezza misura di quanto i ricavi possono ridursi prima di raggiungere "
                            "il break even point; è negativo quando i ricavi sono sotto il break even point.")
    s += [layout.tiles([tile_from(data, "costi_fissi", "Costi fissi", fmt.compact_eur),
                        tile_from(data, "margine_contribuzione", "Margine di contribuzione", fmt.compact_eur),
                        tile_from(data, "bep", "Break even point", fmt.compact_eur),
                        tile_from(data, "margine_sicurezza", "Margine di sicurezza", fmt.pct)]), Spacer(0, 16)]
    s += layout.h2("Costi fissi, costi variabili, ricavi e break even point (€ migliaia)")
    s += [layout.chart(charts.pareggio(labels(data), data.v("ricavi"), data.v("costi_variabili"),
                                       data.v("costi_fissi"), data.v("bep")), charts.HEIGHTS["pareggio"])]
    s += [layout.fin_table(headers(data), [
        row(data, "Ricavi delle vendite", "ricavi"), row(data, "Costi variabili", "costi_variabili"),
        row(data, "Margine di contribuzione", "margine_contribuzione", "bold"),
        row(data, "Costi fissi", "costi_fissi"), row(data, "Break even point", "bep", "hl"),
        row(data, "Margine di sicurezza", "margine_sicurezza", "hl", unit="percent")]), Spacer(0, 4),
        layout.chart(charts.sicurezza(labels(data), data.v("margine_sicurezza")), charts.HEIGHTS["sicurezza"])]
    return s


# ---------------------------------------------------------------- sezione 5
def _financing_note(data: BusinessPlanData) -> str:
    parts = []
    for i, c in enumerate(data.columns):
        new, rep = data.v("cf_nuovo_debito")[i], data.v("cf_rimborsi")[i]
        bits = []
        if new not in (None, 0):
            bits.append(f"nuovi finanziamenti € {fmt.eur(new)}")
        if rep not in (None, 0):
            bits.append(f"rimborsi € {fmt.eur(rep)}")
        if bits:
            parts.append(f"{c.label}: " + ", ".join(bits))
    body = "; ".join(parts) if parts else "nessun nuovo finanziamento né rimborso"
    return f"Flusso di finanziamento — {body}. Dettaglio nell'Allegato C."


def flussi(data: BusinessPlanData, pages: dict) -> list:
    from .narrative import subtitle_flussi
    s = layout.section_head("SEZIONE 5", "Flussi di cassa", subtitle_flussi(data))
    op, inv, rimb = _sum_plan(data, "cf_operativo"), _sum_plan(data, "cf_investimenti"), _sum_plan(data, "cf_rimborsi")
    rimb_years = [str(data.columns[i].year) for i in data.plan_idx if data.v("cf_rimborsi")[i] not in (None, 0)]
    cassa_last = data.v("cassa_fine")[-1]
    first_plan = data.plan_idx[0]
    start = data.v("cassa_inizio")[first_plan]
    delta = None if cassa_last is None or start is None else cassa_last - start
    s += [layout.tiles([
        (fmt.compact_eur(op), "Flussi operativi", f"cumulati {_plan_span(data)}"),
        (fmt.compact_eur(inv), "Investimenti", f"cumulati {_plan_span(data)}"),
        (fmt.compact_eur(None if rimb is None else -rimb), "Rimborsi di debito", _years_phrase(rimb_years)),
        (fmt.compact_eur(cassa_last), f"Cassa a fine {data.last.year}",
         f"variazione {_plan_span(data)}: {fmt.compact_eur(delta)}")]), Spacer(0, 16)]
    s += layout.h2("Composizione dei flussi e cassa di fine anno (€ migliaia)")
    s += [layout.chart(charts.flussi(labels(data), data.v("cf_operativo"), data.v("cf_investimenti"),
                                     data.v("cf_finanziamento"), data.v("cassa_fine")), charts.HEIGHTS["flussi"])]
    s += [layout.fin_table(headers(data), [
        row(data, "Utile prima di imposte, interessi e plusvalenze", "cf_ebit"),
        row(data, "Rettifiche non monetarie (ammortamenti, accantonamenti, svalutazioni)", "cf_non_monetarie"),
        row(data, "Flusso prima delle variazioni del circolante", "cf_ante_ccn", "bold"),
        row(data, "Variazioni del capitale circolante netto", "cf_var_ccn"),
        row(data, "Interessi, imposte pagate e utilizzo fondi", "cf_altre"),
        row(data, "Flusso di cassa operativo (A)", "cf_operativo", "hl"),
        row(data, "Flusso dell'attività di investimento (B)", "cf_investimenti"),
        row(data, "Flusso dell'attività di finanziamento (C)", "cf_finanziamento"),
        row(data, "Variazione delle disponibilità liquide (A+B+C)", "cf_variazione", "bold"),
        row(data, "Disponibilità liquide a inizio esercizio", "cassa_inizio"),
        row(data, "Disponibilità liquide a fine esercizio", "cassa_fine", "hl")]), Spacer(0, 5),
        layout.note(_financing_note(data))]
    return s
