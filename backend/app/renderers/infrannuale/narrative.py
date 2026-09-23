"""Testi a regole del report infrannuale: stesso input, stesso testo; ogni frase nasce da una soglia dichiarata.

Nessuna frase si scrive su un dato assente: la regola che non ha i suoi numeri tace.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.renderers.business_plan import fmt, theme

from .data import INFRANNUALE, PROIEZIONE, STORICO, InfrannualeData

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
