"""Testi del Business plan, a regole deterministiche (spec D3): ogni frase nasce da una soglia in SOGLIE.

Un dato assente toglie la frase, non la inventa. Nessun LLM: stessa pratica, stesso testo.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from . import fmt
from .data import BusinessPlanData

D = Decimal
SOGLIE = {
    "margine_variazione_pp": D("1"),     # punti di EBITDA margin per dire «in espansione» o «in contrazione»
    "margine_stabile_pp": D("0.5"),
    "dscr_coperto": D("1.25"),
    "dscr_limite": D("1"),
    "dscr_ampio": D("2"),
    "pfn_ebitda_alto": D("3"),
    "dso_variazione_gg": D("5"),
    "indipendenza_bassa": D("15"),
    "personale_alto": D("50"),
    "banche_breve_quota": D("40"),
    "cassa_minima_ricavi_pct": D("1"),
    "dso_da_accelerare": D("90"),
}


@dataclass(frozen=True)
class Finding:
    id: str
    title: str
    text: str


def _v(data: BusinessPlanData, key: str) -> list:
    return list(data.v(key))


def _ends(data: BusinessPlanData, key: str) -> tuple:
    vals = _v(data, key)
    return (vals[0], vals[-1]) if vals else (None, None)


def _plan(data: BusinessPlanData, key: str) -> list:
    return [(data.columns[i], data.v(key)[i]) for i in data.plan_idx]


def _plan_values(data: BusinessPlanData, key: str) -> list:
    return [v for _, v in _plan(data, key)]


def _all(*xs) -> bool:
    return all(x is not None for x in xs)


def _join(items: list) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " e " + items[-1]


#: scarto massimo, in punti percentuali, fra la crescita dei ricavi dichiarata e quella che i ricavi mostrano
SCARTO_CRESCITA_PP = Decimal("2")


def revenue_growth_coherent(data: BusinessPlanData) -> bool:
    """La crescita dichiarata è quella che muove i ricavi? No quando un override del CE (o l'input a importi della
    startup) li forza: allora stampare «crescita dello 0%» accanto a ricavi che raddoppiano contraddice il report."""
    if data.revenue_overridden:
        return False
    vals, ricavi = data.growth.get("revenue_growth_pct"), data.v("ricavi")
    for g, i in zip(vals or (), data.plan_idx):
        prev, cur = (ricavi[i - 1] if i > 0 else None), ricavi[i]
        if g is None or prev is None or cur is None or prev <= 0:
            continue
        if abs((cur / prev - 1) * 100 - g) > SCARTO_CRESCITA_PP:
            return False
    return True


def growth_list(data: BusinessPlanData, field: str) -> Optional[str]:
    vals = data.growth.get(field)
    if not vals or any(v is None for v in vals):
        return None
    if field == "revenue_growth_pct" and not revenue_growth_coherent(data):
        return None
    return " / ".join(fmt.pct_short(v) for v in vals)


def _growth_phrase(data: BusinessPlanData) -> Optional[str]:
    vals = data.growth.get("revenue_growth_pct")
    if not vals or any(v is None for v in vals) or not revenue_growth_coherent(data):
        return None
    parts = [f"{fmt.prep('del', fmt.pct_short(v))} nel {y}" for v, y in zip(vals, data.plan_years)]
    return _join(parts)


def _span(data: BusinessPlanData) -> str:
    y = data.plan_years
    return f"{y[0]}–{y[-1]}" if len(y) > 1 else str(y[0])


# ---------------------------------------------------------------- punti chiave (sezione 1)
def key_points(data: BusinessPlanData) -> list:
    out = []
    c0, cn = data.first.label, data.last.label
    r0, rn = _ends(data, "ricavi")
    if _all(r0, rn):
        lead = "Crescita dei ricavi." if rn > r0 else ("Ricavi stabili." if rn == r0 else "Ricavi in calo.")
        text = f"I ricavi delle vendite passano da € {fmt.eur(r0)} ({c0}) a € {fmt.eur(rn)} ({cn})"
        g = _growth_phrase(data)
        out.append((lead, text + (f", con ipotesi di crescita {g}." if g else ".")))
    m0, mn = _ends(data, "ebitda_margin")
    e0, en = _ends(data, "ebitda")
    if _all(m0, mn, e0, en):
        delta = mn - m0
        lead = ("Redditività in miglioramento." if delta > SOGLIE["margine_stabile_pp"] else
                "Redditività in calo." if delta < -SOGLIE["margine_stabile_pp"] else "Redditività stabile.")
        text = (f"L'EBITDA passa da € {fmt.eur(e0)} a € {fmt.eur(en)} e l'EBITDA margin "
                f"{fmt.prep('dal', fmt.pct(m0))} {fmt.prep('al', fmt.pct(mn))}.")
        p0, pn = _ends(data, "inc_personale")
        if _all(p0, pn):
            text += (f" L'incidenza del costo del personale sui ricavi passa "
                     f"{fmt.prep('dal', fmt.pct(p0))} {fmt.prep('al', fmt.pct(pn))}.")
        out.append((lead, text))
    dscr = [(c, v) for c, v in _plan(data, "dscr") if v is not None]
    of = [(c, v) for c, v in _plan(data, "of_mol") if v is not None]
    if dscr:
        mn_d = min(v for _, v in dscr)
        lead = ("Servizio del debito coperto." if mn_d >= SOGLIE["dscr_coperto"] else
                "Servizio del debito al limite." if mn_d >= SOGLIE["dscr_limite"] else
                "Servizio del debito non coperto.")
        (c1, d1), (cl, dl) = dscr[0], dscr[-1]
        text = f"Il DSCR (proxy) è pari a {fmt.ratio(d1)} nel {c1.year} e a {fmt.ratio(dl)} nel {cl.year}"
        if len(of) >= 2:
            text += (f"; gli oneri finanziari passano {fmt.prep('dal', fmt.pct(of[0][1]))} "
                     f"{fmt.prep('al', fmt.pct(of[-1][1]))} del MOL")
        out.append((lead, text + "."))
    op = _plan_values(data, "cf_operativo")
    inv = _plan_values(data, "cf_investimenti")
    rimb = _plan_values(data, "cf_rimborsi")
    f0, fn = _ends(data, "pfn")
    pe0, pen = _ends(data, "pfn_ebitda")
    if op and _all(*op, *inv, *rimb, f0, fn, pe0, pen):
        s_op, s_inv, s_r = sum(op, D(0)), sum(inv, D(0)), sum(rimb, D(0))
        lead = ("Generazione di cassa e deleveraging." if s_op > 0 and fn < f0 else
                "Generazione di cassa." if s_op > 0 else "Assorbimento di cassa.")
        out.append((lead, f"I flussi operativi cumulati {_span(data)} sono pari a {fmt.compact_eur(s_op)}, a fronte "
                          f"di investimenti per {fmt.compact_eur(abs(s_inv))} e rimborsi per {fmt.compact_eur(s_r)}. "
                          f"La PFN passa da € {fmt.eur(f0)} a € {fmt.eur(fn)} e il rapporto PFN/EBITDA da "
                          f"{fmt.ratio(pe0)} a {fmt.ratio(pen)}."))
    ms0, msn = _ends(data, "margine_sicurezza")
    if _all(ms0, msn):
        lead = "Sopra il break even point." if msn >= 0 else "Sotto il break even point."
        turn = next(((c, v) for c, v in _plan(data, "margine_sicurezza") if v is not None and v >= 0), None)
        if ms0 < 0 <= msn and turn:
            text = (f"Il margine di sicurezza, negativo nel {c0} ({fmt.pct(ms0)}), diventa positivo dal "
                    f"{turn[0].year} ({fmt.pct(turn[1])}) e raggiunge il {fmt.pct(msn)} nel {data.last.year}.")
        else:
            text = (f"Il margine di sicurezza passa {fmt.prep('dal', fmt.pct(ms0))} ({c0}) "
                    f"{fmt.prep('al', fmt.pct(msn))} ({cn}).")
        out.append((lead, text))
    d0, dn = _ends(data, "dso")
    k0, kn = _ends(data, "ciclo")
    if _all(d0, dn, k0, kn):
        lead = ("Circolante più efficiente." if kn < k0 else
                "Circolante stabile." if kn == k0 else "Circolante in assorbimento.")
        out.append((lead, f"I giorni di incasso (DSO) passano da {fmt.eur(d0)} a {fmt.eur(dn)}, il ciclo di "
                          f"conversione del denaro da {fmt.eur(k0)} a {fmt.eur(kn)} giorni."))
    return out


# ---------------------------------------------------------------- forza e debolezza (sezione 1 · segue)
def strengths_weaknesses(data: BusinessPlanData) -> tuple:
    forza, debolezza = [], []
    c0 = data.first.label
    m0, mn = _ends(data, "ebitda_margin")
    if _all(m0, mn):
        if mn - m0 >= SOGLIE["margine_variazione_pp"]:
            forza.append(Finding("margini", "Margini in espansione",
                                 f"EBITDA margin {fmt.prep('dal', fmt.pct(m0))} ({c0}) {fmt.prep('al', fmt.pct(mn))} "
                                 f"({data.last.label})."))
        elif m0 - mn >= SOGLIE["margine_variazione_pp"]:
            debolezza.append(Finding("margini_calo", "Margini in contrazione",
                                     f"EBITDA margin {fmt.prep('dal', fmt.pct(m0))} {fmt.prep('al', fmt.pct(mn))}."))
    op = _plan(data, "cf_operativo")
    if op and all(v is not None for _, v in op):
        neg = [str(c.year) for c, v in op if v < 0]
        if not neg:
            forza.append(Finding("cassa", "Generazione di cassa",
                                 f"Flussi operativi positivi in ogni anno di piano, "
                                 f"{fmt.compact_eur(sum((v for _, v in op), D(0)))} cumulati; liquidità a fine "
                                 f"{data.last.year} pari a € {fmt.eur(data.v('cassa_fine')[-1])}."))
        else:
            debolezza.append(Finding("flussi_negativi", f"Flussi operativi negativi nel {_join(neg)}",
                                     "La gestione operativa assorbe cassa in almeno un anno di piano."))
    f0, fn = _ends(data, "pfn")
    pe0, pen = _ends(data, "pfn_ebitda")
    dscr_plan = [v for v in _plan_values(data, "dscr") if v is not None]
    if _all(f0, fn, pe0, pen):
        if fn < f0 and pen < pe0:
            txt = f"PFN da € {fmt.eur(f0)} a € {fmt.eur(fn)} e PFN/EBITDA da {fmt.ratio(pe0)} a {fmt.ratio(pen)}."
            if dscr_plan:
                txt += f" DSCR (proxy) mai inferiore a {fmt.floor_ratio(min(dscr_plan), 1)}."
            forza.append(Finding("deleveraging", "Rapido deleveraging", txt))
        if pen > SOGLIE["pfn_ebitda_alto"]:
            debolezza.append(Finding("indebitamento", "Indebitamento elevato",
                                     f"PFN/EBITDA pari a {fmt.ratio(pen)} nel {data.last.year}."))
    if dscr_plan and min(dscr_plan) < SOGLIE["dscr_limite"]:
        debolezza.append(Finding("dscr_basso", "Servizio del debito non coperto",
                                 f"DSCR (proxy) minimo pari a {fmt.ratio(min(dscr_plan))}."))
    d0, dn = _ends(data, "dso")
    k0, kn = _ends(data, "ciclo")
    if _all(d0, dn):
        if d0 - dn >= SOGLIE["dso_variazione_gg"]:
            txt = f"DSO da {fmt.eur(d0)} a {fmt.eur(dn)} giorni"
            if _all(k0, kn):
                txt += f"; ciclo di conversione del denaro da {fmt.eur(k0)} a {fmt.eur(kn)} giorni"
            forza.append(Finding("incassi", "Incassi più rapidi", txt + "."))
        elif dn - d0 >= SOGLIE["dso_variazione_gg"]:
            debolezza.append(Finding("incassi_lenti", "Incassi più lenti",
                                     f"DSO da {fmt.eur(d0)} a {fmt.eur(dn)} giorni."))
    p0, pn = _ends(data, "patrimonio_netto")
    msn = data.v("margine_struttura")[-1]
    if _all(p0, pn, msn) and pn > p0 and msn > 0:
        forza.append(Finding("patrimonio", "Rafforzamento patrimoniale",
                             f"Patrimonio netto da € {fmt.eur(p0)} a € {fmt.eur(pn)}; margine di struttura positivo "
                             f"nel {data.last.year} (€ {fmt.eur(msn)})."))
    ms0 = data.v("margine_sicurezza")[0]
    base = data.columns[0].is_base
    if base and ms0 is not None and ms0 < 0:
        debolezza.append(Finding("sotto_bep", "Punto di partenza sotto il break even point",
                                 f"Nel {c0} il margine di sicurezza è {fmt.pct(ms0)}."))
    pers0 = data.v("inc_personale")[0]
    fissi0, r0 = data.v("costi_fissi")[0], data.v("ricavi")[0]
    if pers0 is not None and pers0 > SOGLIE["personale_alto"]:
        txt = f"Il personale assorbe il {fmt.pct(pers0)} dei ricavi"
        if _all(fissi0):
            txt = f"Costi fissi pari a {fmt.compact_eur(fissi0)} nel {c0}; " + txt[0].lower() + txt[1:]
        debolezza.append(Finding("costi_rigidi", "Struttura dei costi rigida",
                                 txt + ". Una crescita dei ricavi inferiore al piano incide direttamente sul margine."))
    cassa0, op0 = data.v("cassa_fine")[0], data.v("cf_operativo")[0]
    if base and _all(cassa0, r0) and r0 > 0 and (
            cassa0 / r0 * 100 < SOGLIE["cassa_minima_ricavi_pct"] or (op0 is not None and op0 < 0)):
        debolezza.append(Finding("tensione_liquidita", f"Tensione di liquidità nel {data.first.year}",
                                 f"Flusso operativo {c0} pari a € {fmt.eur(op0)} e disponibilità liquide a fine "
                                 f"{data.first.year} pari a € {fmt.eur(cassa0)}."))
    ind0 = data.v("indipendenza")[0]
    if ind0 is not None and ind0 < SOGLIE["indipendenza_bassa"]:
        debolezza.append(Finding("sottocapitalizzazione", "Sottocapitalizzazione iniziale",
                                 f"Indipendenza finanziaria al {fmt.pct(ind0)} nel {c0}."))
    b0, bb0 = data.v("banche")[0], data.v("banche_breve")[0]
    if _all(b0, bb0) and b0 > 0 and bb0 / b0 * 100 > SOGLIE["banche_breve_quota"]:
        debolezza.append(Finding("debito_breve", "Debito bancario a breve",
                                 f"Debiti verso banche entro 12 mesi pari a € {fmt.eur(bb0)} nel {c0}, "
                                 f"il {fmt.pct(bb0 / b0 * 100, 0)} dell'esposizione bancaria."))
    return forza[:5], debolezza[:5]


# ---------------------------------------------------------------- azioni prioritarie
_AZIONI = {
    "sotto_bep": ("Superare stabilmente il break even point", None, "Margine di sicurezza, ricavi vs break even point"),
    "costi_rigidi": ("Presidiare i costi fissi", None, "Incidenza personale e costi fissi sui ricavi"),
    "margini_calo": ("Recuperare marginalità", "Verificare prezzi, mix e costi variabili che riducono l'EBITDA margin.",
                     "EBITDA margin"),
    "flussi_negativi": ("Coprire il fabbisogno operativo",
                        "Pianificare le fonti che coprono gli anni con flusso operativo negativo.",
                        "Flusso operativo, cassa"),
    "dscr_basso": ("Rinegoziare il servizio del debito",
                   "Allineare il piano di rimborso ai flussi che la gestione genera.", "DSCR"),
    "tensione_liquidita": ("Presidiare la liquidità", None, "Saldo di cassa, flusso operativo"),
}
_STRUTTURA = {"sottocapitalizzazione", "debito_breve", "indebitamento"}


def actions(data: BusinessPlanData, weaknesses: list) -> list:
    out = []
    if data.workflow == "infrannuale" and data.residual_revenue is not None:
        out.append((f"Consolidare il forecast {data.first.year}",
                    f"Verificare con i dati contabili più recenti il raggiungimento dei ricavi stimati per il periodo "
                    f"residuo (€ {fmt.eur(data.residual_revenue)}) e presidiare la liquidità di fine anno.",
                    "Ricavi e EBITDA mensili, saldo di cassa"))
    ids = [w.id for w in weaknesses]
    for wid in ids:
        if wid not in _AZIONI:
            continue
        if wid == "tensione_liquidita" and data.workflow == "infrannuale":
            continue  # già coperta da «Consolidare il forecast», che chiede di presidiare la liquidità di fine anno
        title, text, kpi = _AZIONI[wid]
        if wid == "sotto_bep":
            g = growth_list(data, "revenue_growth_pct")
            text = ("Sostenere la crescita dei ricavi" + (f" ({g})" if g else "") +
                    " con portafoglio ordini, contratti in essere e capacità operativa.")
        elif wid == "costi_rigidi":
            text = (f"Mantenere il costo del personale sul livello di piano (€ {fmt.eur(data.v('personale')[-1])}) "
                    "e monitorare servizi e godimento beni di terzi.")
        elif wid == "tensione_liquidita":
            text = f"Pianificare incassi e pagamenti del {data.first.year} per evitare tensioni di cassa."
        out.append((title, text, kpi))
    dso0 = data.v("dso")[0]
    target = growth_list(data, "dso_days")
    if target and dso0 is not None and dso0 > SOGLIE["dso_da_accelerare"]:
        out.append(("Accelerare gli incassi",
                    f"Portare i tempi di incasso ai giorni ipotizzati ({target.replace('%', '')}) con azioni su "
                    "scaduto e condizioni commerciali.", "DSO, scaduto clienti, ciclo monetario"))
    if _STRUTTURA & set(ids):
        out.append(("Riequilibrare la struttura finanziaria",
                    "Allineare la quota di debito a breve ai flussi del piano e mantenere gli utili a riserva per "
                    "rafforzare il patrimonio netto.", "PFN/EBITDA, DSCR, indipendenza finanziaria"))
    if not out:
        out.append(("Monitorare il piano", "Confrontare trimestralmente consuntivo e piano su ricavi, EBITDA e cassa.",
                    "Ricavi, EBITDA, cassa"))
    return out[:5]


# ---------------------------------------------------------------- letture e sottotitoli
_VOCI = (("inc_materie", "le materie prime"), ("inc_servizi", "i servizi"), ("inc_godimento", "il godimento di beni di terzi"),
         ("inc_personale", "il personale"), ("inc_oneri_diversi", "gli oneri diversi di gestione"))


def lettura_costi(data: BusinessPlanData) -> list:
    out = []
    p0, pn = _ends(data, "inc_personale")
    m0, mn = _ends(data, "ebitda_margin")
    pers_growth = data.growth.get("personnel_growth_pct")
    if _all(p0, pn, m0, mn) and pers_growth and all(v == 0 for v in pers_growth) and mn > m0 and pn < p0:
        out.append("Il miglioramento del margine deriva principalmente dalla stabilità del costo del personale "
                   "(crescita ipotizzata 0%) a fronte della crescita dei ricavi: l'incidenza del personale scende di "
                   f"{fmt.pct(p0 - pn, 1).replace('%', '')} punti.")
    else:
        o0, on = _ends(data, "inc_costi_operativi")
        if _all(o0, on):
            out.append(f"L'incidenza dei costi operativi sui ricavi passa {fmt.prep('dal', fmt.pct(o0))} "
                       f"{fmt.prep('al', fmt.pct(on))}.")
    last = [(label, data.v(k)[-1]) for k, label in _VOCI if data.v(k)[-1] is not None]
    if last:
        label, v = max(last, key=lambda x: x[1])
        out.append(f"Nel {data.last.year} la voce di costo con l'incidenza maggiore è {label} ({fmt.pct(v)} dei ricavi).")
    return out


def lettura_circolante(data: BusinessPlanData) -> list:
    out = []
    c0, cn = _ends(data, "cc_comm")
    r0, rn = _ends(data, "ricavi")
    d0, dn = _ends(data, "dso")
    p0, pn = _ends(data, "dpo")
    if _all(c0, cn, r0, rn) and c0 and r0:
        gc, gr = (cn / c0 - 1) * 100, (rn / r0 - 1) * 100
        verso = "meno" if gc < gr else "più"
        txt = (f"Il circolante commerciale cresce {verso} che proporzionalmente ai ricavi ({fmt.pct(gc, 1)} contro "
               f"{fmt.pct(gr, 1)})")
        if _all(d0, dn, p0, pn):
            txt += (f"; i giorni di incasso passano da {fmt.eur(d0)} a {fmt.eur(dn)} e quelli di pagamento da "
                    f"{fmt.eur(p0)} a {fmt.eur(pn)}")
        out.append(txt + ".")
    k0, kn = _ends(data, "ciclo")
    if _all(k0, kn):
        out.append(f"Il ciclo di conversione del denaro passa da {fmt.eur(k0)} giorni ({data.first.label}) a "
                   f"{fmt.eur(kn)} giorni ({data.last.label}).")
    return out


def subtitle_flussi(data: BusinessPlanData) -> str:
    base = "Rendiconto finanziario di sintesi (metodo indiretto)."
    plan = _plan(data, "cf_variazione")
    if not plan or any(v is None for _, v in plan):
        return base
    neg = [str(c.year) for c, v in plan if v < 0]
    if not neg:
        return base + " Il piano genera cassa in ogni anno, sufficiente a finanziare investimenti e rimborsi."
    return base + f" La cassa diminuisce nel {_join(neg)}."
