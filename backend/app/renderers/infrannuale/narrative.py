"""Testi a regole del report infrannuale: stesso input, stesso testo; ogni frase nasce da una soglia dichiarata.

Nessuna frase si scrive su un dato assente: la regola che non ha i suoi numeri tace.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.renderers.business_plan import fmt, theme

from .data import ANNUALIZZATO, INFRANNUALE, PROIEZIONE, STORICO, InfrannualeData

#: soglie dell'esito sul punteggio 0–1 del motore della crisi (spec §5)
SOGLIA_OLTRE = Decimal("0.33")   # = calculations.crisi_impresa.SOGLIA_OLTRE
SOGLIA_ATTENZIONE = Decimal("0.66")  # ricavata dal riferimento: 0,557 «attenzione», 0,691 «in soglia»
ATTENZIONE = "#b7791f"
ESITO_COLORE = {"oltre soglia": theme.RED, "attenzione": ATTENZIONE, "in soglia": theme.TEAL}


def esito(punteggio) -> Optional[str]:
    if punteggio is None:
        return None
    p = Decimal(str(punteggio))
    if p < SOGLIA_OLTRE:
        return "oltre soglia"
    return "attenzione" if p < SOGLIA_ATTENZIONE else "in soglia"


def _all(*xs) -> bool:
    return all(x is not None for x in xs)


def _last(d: InfrannualeData) -> str:
    """La colonna di arrivo: il forecast se c'è, altrimenti il semestre."""
    return PROIEZIONE if d.has_forecast else INFRANNUALE


def _pct_int(v: Decimal) -> str:
    return f"{abs(v).quantize(Decimal(1))}%"


_VOCI_ATTIVO = (("crediti_clienti", "i crediti verso clienti"), ("rimanenze", "le rimanenze"),
                ("liquidita", "le disponibilità liquide"), ("immobilizzazioni", "le immobilizzazioni"),
                ("ratei_attivi", "i ratei e risconti attivi"))


def lettura_patrimonio(d: InfrannualeData) -> list:
    out = []
    v = d.v
    rif = str(d.reference_year)
    a0, a6 = v("totale_attivo", STORICO), v("totale_attivo", INFRANNUALE)
    if _all(a0, a6) and a6 != a0:
        deltas = [(v(k, INFRANNUALE) - v(k, STORICO), txt) for k, txt in _VOCI_ATTIVO
                  if _all(v(k, INFRANNUALE), v(k, STORICO))]
        verbo = "cresce" if a6 > a0 else "scende"
        s = f"L'attivo {verbo} nel semestre"
        if deltas:
            top = max(deltas, key=lambda x: x[0]) if a6 > a0 else min(deltas, key=lambda x: x[0])
            s += f" soprattutto per {top[1]}"
        c0, c6, cf = v("crediti_clienti", STORICO), v("crediti_clienti", INFRANNUALE), v("crediti_clienti", PROIEZIONE)
        if _all(c0, c6, cf) and cf < c6:
            s += (f"; nel forecast i crediti si riducono ma restano superiori al {rif}" if cf > c0
                  else f"; nel forecast i crediti tornano sotto il livello del {rif}")
        out.append(s + ".")
    last = _last(d)
    i0, i1 = v("immobilizzazioni", STORICO), v("immobilizzazioni", last)
    if _all(i0, i1) and i1 < i0:
        s = "Le immobilizzazioni scendono per effetto degli ammortamenti"
        f0, f1 = v("immob_finanziarie", STORICO), v("immob_finanziarie", last)
        if _all(f0, f1) and f1 < f0:
            s += (f" e della riduzione delle immobilizzazioni finanziarie (da € {fmt.eur(f0)} a "
                  f"€ {fmt.eur(f1)})")
        out.append(s + ".")
    elif _all(i0, i1) and i1 > i0:
        out.append(f"Le immobilizzazioni crescono da € {fmt.eur(i0)} a € {fmt.eur(i1)}.")
    p0, p1, u1 = v("patrimonio_netto", STORICO), v("patrimonio_netto", last), v("risultato_netto", last)
    dvar = d.var("debiti_finanziari", last)
    if _all(p0, p1):
        s = "Il patrimonio netto " + ("cresce con l'utile" if p1 > p0 and (u1 or 0) > 0
                                      else "cresce" if p1 > p0 else "diminuisce")
        if dvar is not None and dvar != 0:
            s += (f", mentre i debiti finanziari {'aumentano' if dvar > 0 else 'diminuiscono'} "
                  f"{fmt.prep('del', _pct_int(dvar))}")
        ind = v("indipendenza", last)
        if ind is not None and ind < 20:
            s += ": la struttura resta sbilanciata sul capitale di terzi"
        out.append(s + ".")
    return out


# ================================================================== sezione 1
@dataclass(frozen=True)
class Finding:
    id: str
    title: str
    text: str


SOGLIE = {
    "margine_contenuto": Decimal("10"),      # EBITDA margin sotto il 10%: «contenuta»
    "margine_stabile_pp": Decimal("0.1"),    # variazione del margine sotto 0,1 punti: «stabile»
    "circolante_pct": Decimal("20"),         # crescita dei crediti verso clienti oltre il 20%: debolezza
    "previdenziali_pct": Decimal("20"),      # crescita dei debiti previdenziali oltre il 20%: debolezza
    "cassa_su_ricavi_pct": Decimal("1"),     # liquidità sotto l'1% dei ricavi: tesoreria da presidiare
    "costi_spostamento_pp": Decimal("5"),    # incidenza di una voce di costo mossa di oltre 5 punti
    "indipendenza_pct": Decimal("20"),       # sotto il 20% la struttura è «sbilanciata sul capitale di terzi»
}
_NOMI_PERIODO = {STORICO: "nel consuntivo {rif}", INFRANNUALE: "nel semestre", PROIEZIONE: "nel forecast {anno}"}


def _periodo(d: InfrannualeData, col: str) -> str:
    if col == INFRANNUALE and d.period_months != 6:
        return f"nei {d.period_months} mesi"
    return _NOMI_PERIODO[col].format(rif=d.reference_year, anno=d.partial_year)


def _signed_pct(v: Optional[Decimal]) -> str:
    if v is None:
        return fmt.ND
    return ("+" if v > 0 else "") + fmt.pct(v)


def _signed_eur(v: Decimal) -> str:
    return (fmt.MINUS if v < 0 else "+") + "€ " + fmt.eur(abs(v))


def _r2(v) -> str:
    return fmt.ratio(v, 2)


def _floor1(v: Decimal) -> str:
    """Arrotondato per difetto: «intorno a 2,9–3,0×» non promette più del minimo."""
    return fmt.floor_ratio(v, 1).rstrip("×")


def _esito(d: InfrannualeData, key: str, col: str) -> Optional[str]:
    c = d.crisi.get(col)
    return esito(c.punteggi.get(key)) if c else None


def _semestre(d: InfrannualeData) -> str:
    return "Il semestre" if d.period_months == 6 else f"Il periodo di {d.period_months} mesi"


def key_points(d: InfrannualeData) -> list:
    out = []
    v, last = d.v, _last(d)
    rif, anno = d.reference_year, d.partial_year
    r0, r6, rf = v("ricavi", STORICO), v("ricavi", INFRANNUALE), v("ricavi", last)
    if _all(r0, r6) and d.has_forecast and rf is not None:
        lead = "Ricavi in crescita." if rf > r0 else ("Ricavi stabili." if rf == r0 else "Ricavi in calo.")
        out.append((lead, f"{_semestre(d)} chiude con ricavi delle vendite per € {fmt.eur(r6)}; il forecast {anno} è "
                          f"di € {fmt.eur(rf)}, {_signed_pct(d.var('ricavi', last))} rispetto al consuntivo {rif} "
                          f"(€ {fmt.eur(r0)})."))
    elif _all(r0, r6):
        out.append(("Ricavi del periodo.", f"{_semestre(d)} chiude con ricavi delle vendite per € {fmt.eur(r6)}, "
                                           f"contro € {fmt.eur(r0)} dell'intero {rif}."))
    m0, m6, mf, e0, ef = (v("ebitda_margin", STORICO), v("ebitda_margin", INFRANNUALE), v("ebitda_margin", last),
                          v("ebitda", STORICO), v("ebitda", last))
    if _all(m0, m6, mf, e0, ef) and d.has_forecast:
        delta = mf - m0
        stato = ("stabile" if abs(delta) < SOGLIE["margine_stabile_pp"] else
                 "in miglioramento" if delta > 0 else "in calo")
        lead = f"Marginalità {stato}" + (" ma contenuta." if mf < SOGLIE["margine_contenuto"] and stato != "in calo" else ".")
        conf = ("invariato rispetto al" if round(mf, 2) == round(m0, 2) else
                f"{'in aumento' if delta > 0 else 'in calo'} {fmt.prep('dal', fmt.pct(m0))} del")
        out.append((lead, f"L'EBITDA forecast è di € {fmt.eur(ef)} ({_signed_pct(d.var('ebitda', last))}), con un "
                          f"EBITDA margin {fmt.prep('del', fmt.pct(mf))}, {conf} {rif}; "
                          f"{_periodo(d, INFRANNUALE)} il margine è {fmt.prep('del', fmt.pct(m6))}."))
    u0, u6, uf = v("risultato_netto", STORICO), v("risultato_netto", INFRANNUALE), v("risultato_netto", last)
    if _all(u0, u6, uf) and d.has_forecast:
        lead = "Risultato in perdita." if uf < 0 else ("Utile in aumento." if uf > u0 else "Utile in calo.")
        parola = "l'utile" if u6 >= 0 else "la perdita"
        out.append((lead, f"Il risultato netto forecast è di € {fmt.eur(uf)} contro € {fmt.eur(u0)} del {rif}; "
                          f"{_periodo(d, INFRANNUALE)} {parola} è di € {fmt.eur(abs(u6))}."))
    p0, pf, q0, qf = v("pfn", STORICO), v("pfn", last), v("pfn_ebitda", STORICO), v("pfn_ebitda", last)
    if _all(p0, pf, q0, qf) and pf != p0:
        su = pf > p0
        dscr = [x for x in (v("dscr", c) for c in (STORICO, INFRANNUALE, last)) if x is not None]
        txt = (f"La PFN {'sale' if su else 'scende'} da € {fmt.eur(p0)} ({d.reference_label}) a € {fmt.eur(pf)} "
               f"({d.label_of(last)}) e il rapporto PFN/EBITDA da {_r2(q0)} a {_r2(qf)}")
        if dscr:
            lo, hi = _floor1(min(dscr)), _floor1(max(dscr))
            txt += f"; il DSCR resta intorno a {lo if lo == hi else f'{lo}–{hi}'}×"
        out.append((f"Indebitamento {'in crescita' if su else 'in calo'}.", txt + "."))
    c0, cf = v("crediti_clienti_breve", STORICO), v("crediti_clienti_breve", last)
    k0, kf, lf = v("cc_comm", STORICO), v("cc_comm", last), v("liquidita", last)
    if _all(c0, cf, k0, kf, lf) and d.has_forecast:
        lead = "Circolante assorbe liquidità." if kf > k0 else "Circolante in riduzione."
        out.append((lead, f"I crediti verso clienti entro 12 mesi passano da € {fmt.eur(c0)} a € {fmt.eur(cf)} "
                          f"({_signed_pct(d.var('crediti_clienti_breve', last))}); le disponibilità liquide forecast "
                          f"sono pari a € {fmt.eur(lf)}."))
    if d.crisi:
        gruppi: dict = {}
        for col in (STORICO, PROIEZIONE, INFRANNUALE):
            if col in d.crisi:
                c = d.crisi[col]
                gruppi.setdefault((c.codice, c.etichetta), []).append(_periodo(d, col))
        parti = [f"{cod} ({et}) " + " e ".join(p) for (cod, et), p in gruppi.items()]
        attivi = sum(1 for s in d.segnali if s[2])
        seg = (f"nessuno dei {len(d.segnali)} segnali extracontabili è attivo" if attivi == 0 else
               f"{attivi} dei {len(d.segnali)} segnali extracontabili {'è attivo' if attivi == 1 else 'sono attivi'}")
        out.append(("Classe di rischio.", "Classe " + ", ".join(parti) + (f"; {seg}." if d.segnali else ".")))
    return out


def strengths_weaknesses(d: InfrannualeData) -> tuple:
    forza, debolezza = [], []
    v, last, rif = d.v, _last(d), d.reference_year
    if not d.has_forecast:
        last = INFRANNUALE
    fl = "forecast" if d.has_forecast else _periodo(d, INFRANNUALE)
    # ---- forza
    vr = d.var("ricavi", last) if d.has_forecast else d.var("ricavi", ANNUALIZZATO)
    if vr is not None and vr > 0:
        base = v("ricavi", PROIEZIONE if d.has_forecast else ANNUALIZZATO)
        txt = f"Ricavi delle vendite {'forecast' if d.has_forecast else 'annualizzati'} € {fmt.eur(base)}, " \
              f"{_signed_pct(vr)} sul {rif}"
        va = d.var("ricavi", ANNUALIZZATO)
        if d.has_forecast and va is not None and va > 0:
            txt += f"; il semestre (€ {fmt.eur(v('ricavi', INFRANNUALE))}) è coerente con il percorso di crescita"
        forza.append(Finding("ricavi", "Crescita dei ricavi", txt + "."))
    ve, vb = d.var("ebitda", last), d.var("ebit", last)
    if d.has_forecast and _all(ve, vb) and ve > 0 and vb > 0:
        forza.append(Finding("risultati", "Risultati in miglioramento",
                             f"EBITDA forecast {_signed_pct(ve)} (€ {fmt.eur(v('ebitda', last))}), EBIT "
                             f"{_signed_pct(vb)} (€ {fmt.eur(v('ebit', last))}), utile netto da "
                             f"€ {fmt.eur(v('risultato_netto', STORICO))} a € {fmt.eur(v('risultato_netto', last))}."))
    cols_crisi = [c for c in (STORICO, INFRANNUALE, PROIEZIONE) if c in d.crisi]
    dscr_esiti = [_esito(d, "dscr", c) for c in cols_crisi]
    if cols_crisi and all(e == "in soglia" for e in dscr_esiti) and all(v("dscr", c) is not None for c in cols_crisi):
        nomi = {STORICO: f"nel {rif}", INFRANNUALE: "nel semestre" if d.period_months == 6 else
                f"nei {d.period_months} mesi", PROIEZIONE: "nel forecast"}
        parti = [f"{_r2(v('dscr', c))} {nomi[c]}" for c in cols_crisi]
        testo = ", ".join(parti[:-1]) + " e " + parti[-1] if len(parti) > 1 else parti[0]
        forza.append(Finding("dscr", "Servizio del debito coperto",
                             f"DSCR pari a {testo}: indicatore in soglia."))
    l0, l1 = v("current_ratio", STORICO), v("current_ratio", last)
    if _all(l0, l1) and l1 > l0:
        txt = f"Da {fmt.ratio(l0, 3)} a {fmt.ratio(l1, 3)}"
        extra = []
        t0, t1 = v("mt", STORICO), v("mt", last)
        if _all(t0, t1) and t1 > t0:
            extra.append(f"il margine di tesoreria passa da {_signed_eur(t0)} a {_signed_eur(t1)}")
        k0, k1 = v("copertura_immob", STORICO), v("copertura_immob", last)
        if _all(k0, k1) and k1 > k0:
            extra.append(f"la copertura delle immobilizzazioni {fmt.prep('dal', fmt.pct(k0))} "
                         f"{fmt.prep('al', fmt.pct(k1))}")
        forza.append(Finding("liquidita", "Liquidità corrente in miglioramento",
                             txt + ("; " + " e ".join(extra) if extra else "") + "."))
    if d.segnali and not any(s[2] for s in d.segnali):
        forza.append(Finding("segnali", "Nessun segnale extracontabile",
                             f"0 su {len(d.segnali)}: nessun ritardo rilevante verso dipendenti, fornitori, banche, "
                             "INPS, INAIL, Agente della Riscossione e Agenzia delle Entrate."))
    # ---- debolezza
    if last in d.crisi and d.crisi[last].codice[:1] in ("C", "D"):
        c = d.crisi[last]
        altri = [f"{d.crisi[k].oltre} {nome}" for k, nome in
                 ((INFRANNUALE, "nel semestre" if d.period_months == 6 else f"nei {d.period_months} mesi"),
                  (STORICO, f"nel {rif}")) if k in d.crisi and k != last]
        tot = sum(1 for x in d.definizioni if x[3]) or 14
        dove = f"Nel forecast {d.partial_year}" if d.has_forecast else _periodo(d, INFRANNUALE).capitalize()
        debolezza.append(Finding("classe", f"Classe di rischio {c.classe}",
                                 f"{dove} {c.oltre} indicatori su {tot} sono oltre soglia"
                                 + (f" ({', '.join(altri)})" if altri else "") + "."))
    if _esito(d, "pfn_ebitda", last) == "oltre soglia":
        txt = (f"PFN da € {fmt.eur(v('pfn', STORICO))} a € {fmt.eur(v('pfn', last))} e PFN/EBITDA a "
               f"{_r2(v('pfn_ebitda', last))}")
        om = v("of_mol", last)
        if om is not None:
            txt += f"; gli oneri finanziari assorbono il {fmt.pct(om)} del MOL"
        debolezza.append(Finding("leva", "Leva finanziaria elevata", txt + "."))
    red = [(n, k) for n, k in (("EBITDA margin", "ebitda_margin"), ("ROS", "ros"), ("ROI", "roi"))
           if _esito(d, k, last) == "oltre soglia" and v(k, last) is not None]
    if red:
        parti = [f"{n} {fmt.pct(v(k, last))}" for n, k in red]
        elenco = ", ".join(parti[:-1]) + " e " + parti[-1] if len(parti) > 1 else parti[0]
        debolezza.append(Finding("redditivita", "Redditività contenuta",
                                 elenco + (", tutti oltre soglia." if len(parti) > 1 else ", oltre soglia.")))
    ind, ms = v("indipendenza", last), v("ms", last)
    if _esito(d, "indipendenza", last) == "oltre soglia" and ind is not None:
        txt = f"Indipendenza finanziaria {fmt.prep('al', fmt.pct(ind))}"
        if ms is not None and ms < 0:
            txt += f" e margine di struttura negativo ({fmt.MINUS}€ {fmt.eur(abs(ms))})"
        debolezza.append(Finding("patrimonio", "Sottocapitalizzazione", txt + f" nel {fl}."))
    vc = d.var("crediti_clienti_breve", last)
    k0, kf, lf, rf = v("cc_comm", STORICO), v("cc_comm", last), v("liquidita", last), v("ricavi", last)
    if vc is not None and vc > SOGLIE["circolante_pct"] and _all(k0, kf):
        txt = (f"Crediti verso clienti {_signed_pct(vc)} sul {rif}; circolante commerciale da € {fmt.eur(k0)} a "
               f"€ {fmt.eur(kf)}")
        if lf is not None and d.has_forecast:
            txt += f"; disponibilità liquide forecast pari a € {fmt.eur(lf)}"
        debolezza.append(Finding("circolante", "Circolante e cassa", txt + "."))
    vp = d.var("debiti_previdenziali", last)
    if vp is not None and vp > SOGLIE["previdenziali_pct"]:
        p0, p6, pf = (v("debiti_previdenziali", c) for c in (STORICO, INFRANNUALE, PROIEZIONE))
        txt = f"Da € {fmt.eur(p0)} ({d.reference_label}) a € {fmt.eur(p6)} nel semestre"
        if d.has_forecast:
            txt += f" e € {fmt.eur(pf)} nel forecast"
        debolezza.append(Finding("previdenziali", "Debiti previdenziali in aumento", txt + f" ({_signed_pct(vp)})."))
    return forza, debolezza


_VOCI_COSTO = (("servizi", "servizi"), ("personale", "personale"), ("materie", "materie prime"),
               ("godimento", "godimento di beni di terzi"), ("oneri_diversi", "oneri diversi di gestione"))


def actions(d: InfrannualeData, debolezze: list) -> list:
    out = []
    ids = {w.id for w in debolezze}
    v = d.v
    if d.has_forecast and d.has_annualized:
        scarti = [(abs(v(k, PROIEZIONE) - v(k, ANNUALIZZATO)), k, nome) for k, nome in _VOCI_COSTO
                  if _all(v(k, PROIEZIONE), v(k, ANNUALIZZATO)) and v(k, PROIEZIONE) != v(k, ANNUALIZZATO)]
        top = sorted(scarti, reverse=True)[:2]
        top = [x for x in _VOCI_COSTO if x[0] in {t[1] for t in top}]  # nell'ordine del catalogo
        if top:
            parti = [f"{nome} per € {fmt.eur(v(k, PROIEZIONE))} contro € {fmt.eur(v(k, ANNUALIZZATO))} annualizzati"
                     for k, nome in top]
            resto = "del secondo semestre" if d.period_months == 6 else "dei mesi restanti"
            out.append((f"Verificare il forecast {resto}",
                        f"Il forecast ipotizza {' e '.join(parti)}: confrontare le stime con i dati contabili più "
                        "recenti.", f"Costi per {' e '.join(n for _, n in top)} mensili, EBITDA"))
    if "circolante" in ids:
        cf = v("crediti_clienti_breve", _last(d))
        out.append(("Accelerare gli incassi",
                    f"Ridurre l'esposizione verso clienti (€ {fmt.eur(cf)} entro 12 mesi"
                    f"{' nel forecast' if d.has_forecast else ''}) con azioni su scaduto e condizioni commerciali.",
                    "Crediti vs clienti, circolante commerciale"))
    lf, rf, bb = v("liquidita", _last(d)), v("ricavi", _last(d)), v("banche_breve", _last(d))
    if d.has_forecast and _all(lf, rf) and rf > 0 and lf / rf * 100 < SOGLIE["cassa_su_ricavi_pct"]:
        txt = f"Con disponibilità liquide forecast pari a € {fmt.eur(lf)}"
        if bb:
            txt += f" e debiti bancari a breve per € {fmt.eur(bb)}"
        out.append(("Presidiare la tesoreria di fine anno",
                    txt + ", pianificare incassi, pagamenti e utilizzo degli affidamenti.",
                    "Saldo di cassa, utilizzo fidi"))
    if "leva" in ids:
        out.append(("Ridurre la leva e riequilibrare le scadenze",
                    "Riportare PFN/EBITDA verso livelli sostenibili e spostare quota di debito dal breve al "
                    "medio-lungo termine.", "PFN/EBITDA, oneri finanziari/MOL"))
    if "patrimonio" in ids:
        out.append(("Rafforzare il patrimonio",
                    "Destinare gli utili a riserva e valutare interventi sul capitale per migliorare indipendenza "
                    "finanziaria e margine di struttura.", "Indipendenza finanziaria, margine di struttura"))
    if "previdenziali" in ids:
        out.append(("Monitorare i debiti previdenziali e tributari",
                    "Mantenere i versamenti regolari per evitare l'attivazione dei segnali extracontabili.",
                    "Debiti previdenziali, segnali extracontabili"))
    if "redditivita" in ids:
        out.append(("Recuperare marginalità",
                    "Rivedere prezzi e costi variabili per riportare EBITDA margin e ROS sopra le soglie.",
                    "EBITDA margin, ROS"))
    return out[:6]


def _incidenza(d: InfrannualeData, key: str, col: str) -> Optional[Decimal]:
    x, r = d.v(key, col), d.v("ricavi", col)
    return None if x is None or not r else x / r * 100


def lettura_costi(d: InfrannualeData) -> list:
    out = []
    rif = d.reference_year
    mosse = [(abs(_incidenza(d, k, INFRANNUALE) - _incidenza(d, k, STORICO)), k, nome) for k, nome in _VOCI_COSTO
             if _all(_incidenza(d, k, INFRANNUALE), _incidenza(d, k, STORICO))]
    if len(mosse) < 2:
        return out
    top = sorted(mosse, reverse=True)[:2]
    top = [x for x in _VOCI_COSTO if x[0] in {t[1] for t in top}]
    parti = []
    for n, (k, nome) in enumerate(top):
        i6, i0 = _incidenza(d, k, INFRANNUALE), _incidenza(d, k, STORICO)
        parti.append(f"{'i ' if nome == 'servizi' else 'il ' if nome == 'personale' else ''}{nome} "
                     f"{'pesano' if n == 0 else ''}".strip() + f" il {fmt.pct(i6)}" +
                     (" dei ricavi" if n == 0 else "") + f" ({fmt.pct(i0)} nel {rif})")
    cambiata = max(m[0] for m in mosse) > SOGLIE["costi_spostamento_pp"]
    out.append(f"Nel {'semestre' if d.period_months == 6 else 'periodo'} {parti[0]} e {parti[1]}: la composizione "
               f"dei costi {'è cambiata' if cambiata else 'è rimasta simile'} rispetto al consuntivo.")
    if d.has_forecast:
        f = [(nome, _incidenza(d, k, PROIEZIONE), _incidenza(d, k, INFRANNUALE), _incidenza(d, k, STORICO))
             for k, nome in top]
        if all(_all(a, b, c) for _, a, b, c in f):
            mezzo = all(min(b, c) <= a <= max(b, c) for _, a, b, c in f)
            livello = "su livelli intermedi" if mezzo else "su livelli diversi da semestre e consuntivo"
            resto = "sul secondo semestre" if d.period_months == 6 else "sui mesi restanti"
            out.append(f"Il forecast riporta l'incidenza di {f[0][0]} ({fmt.pct(f[0][1])}) e {f[1][0]} "
                       f"({fmt.pct(f[1][1])}) {livello}: questa ipotesi {resto} è il principale fattore che "
                       "determina l'EBITDA di fine anno.")
    return out


def lettura_circolante(d: InfrannualeData) -> list:
    out = []
    last, rif = _last(d), d.reference_year
    k0, kf = d.v("cc_comm", STORICO), d.v("cc_comm", last)
    if not _all(k0, kf) or k0 <= 0:
        return out
    r = kf / k0
    verbo = ("più che raddoppia" if r >= 2 else f"cresce del {_pct_int((r - 1) * 100)}" if r > 1 else
             f"si riduce del {_pct_int((1 - r) * 100)}")
    s = f"Il circolante commerciale {verbo} rispetto al {rif}"
    vc = d.var("crediti_clienti_breve", last)
    lung0, lungf = d.v("crediti_clienti_lungo", STORICO), d.v("crediti_clienti_lungo", last)
    if r > 1 and vc is not None and vc > 0:
        s += f", trainato dai crediti verso clienti ({_signed_pct(vc)} entro 12 mesi"
        if _all(lung0, lungf) and lungf > lung0:
            s += f" e € {fmt.eur(lungf)} oltre 12 mesi"
        s += ")"
    out.append(s + ".")
    p0, pf = d.v("pfn", STORICO), d.v("pfn", last)
    lf, rf = d.v("liquidita", last), d.v("ricavi", last)
    if r > 1 and _all(p0, pf) and pf > p0:
        s = "La crescita del circolante spiega l'aumento dell'indebitamento"
        if d.has_forecast and _all(lf, rf) and rf > 0 and lf / rf * 100 < SOGLIE["cassa_su_ricavi_pct"]:
            s += " e la cassa quasi nulla attesa a fine anno"
        c0, cf = d.v("current_ratio", STORICO), d.v("current_ratio", last)
        if _all(c0, cf) and cf > c0:
            s += ", pur in presenza di indici di liquidità corrente in miglioramento"
        out.append(s + ".")
    return out
