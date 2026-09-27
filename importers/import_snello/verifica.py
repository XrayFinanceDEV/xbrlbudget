"""Verifica del percorso snello: stesse formule dell'app (campi di quadratura, risultato CE canonico),
soglia relativa, tappo dichiarato entro soglia su altri crediti, altri debiti, servizi (decisione del
proprietario, 2026-09-26). Oltre soglia non si tocca nulla: decide il chiamante."""
from __future__ import annotations

from decimal import Decimal

import config
from calculations.ce_result import calculate_ce_result
from importers.iv_cee_hierarchy import _ATTIVO_FIELDS, _PASSIVO_FIELDS

_C = Decimal("0.01")


def soglia(totale_attivo: Decimal) -> Decimal:
    minimo = Decimal(str(config.IMPORT_SNELLO_SOGLIA_MIN))
    pct = Decimal(str(config.IMPORT_SNELLO_SOGLIA_PCT))
    return max(minimo, abs(Decimal(totale_attivo)) * pct / 100).quantize(_C)


def totali_stampati(file_path: str) -> dict:
    """I totali che il documento stampa da solo (regex sul testo grezzo, nessuna chiamata
    modello): ancora indipendente dall'estrattore, riusata dal vecchio importatore
    (``pdf_extractor_llm._declared_control_totals``) per dare a ``misura()``/``tappa()`` un
    contraddittorio reale - oggi assente in modo "conti" (``stampati=None`` sempre) e solo
    apparente in modo "legge" (i "totali stampati" vengono dalla stessa chiamata LLM che
    legge le voci, non da una lettura indipendente)."""
    try:
        from importers.pdf_extractor_llm import _declared_control_totals
        letti = _declared_control_totals(file_path)
    except Exception:
        letti = {}
    return {"totale_attivo": letti.get("attivo"), "totale_passivo": letti.get("passivo")}


def _fold_utile_in_passivo(stampati: dict | None, utile: Decimal) -> dict | None:
    """Il 'Totale Passivo' di una situazione contabile a sezioni contrapposte puo' non
    includere il risultato d'esercizio (stampato a parte, accanto al pareggio): senza
    correggerlo apparirebbe uno scarto quanto l'utile che non e' una sotto-estrazione, e'
    solo una convenzione di stampa. Riusa la regola del vecchio importatore
    (``pdf_extractor_llm._reconcile_utile_in_passivo``): ripiega il risultato dentro il
    totale passivo SOLO quando il gap coincide col risultato entro tolleranza - un gap
    diverso e' massa vera mancante, e resta com'e'."""
    if not stampati:
        return stampati
    ta, tp = stampati.get("totale_attivo"), stampati.get("totale_passivo")
    if ta is None or tp is None:
        return stampati
    from importers.pdf_extractor_llm import _reconcile_utile_in_passivo
    corretto = _reconcile_utile_in_passivo(
        {"totale_attivo": Decimal(ta), "totale_passivo": Decimal(tp), "sp13_utile_perdita": utile},
        "snello")
    nuovo_tp = corretto["totale_passivo"]
    if nuovo_tp == Decimal(tp):
        return stampati
    nuovo = dict(stampati)
    nuovo["totale_passivo"] = nuovo_tp
    return nuovo


def misura(bs: dict, ce: dict, stampati: dict | None = None, forma: str | None = None) -> dict:
    att = sum((Decimal(bs.get(k, 0)) for k in _ATTIVO_FIELDS), Decimal(0))
    pas = sum((Decimal(bs.get(k, 0)) for k in _PASSIVO_FIELDS), Decimal(0))
    sp13 = Decimal(bs.get("sp13_utile_perdita", 0))
    utile = calculate_ce_result(ce).net_profit
    stampati = _fold_utile_in_passivo(stampati, utile)
    bilancio = (att - pas, utile - sp13)                     # sp13 e' il risultato corrente
    verifica = (att - pas - utile, Decimal(0))               # sp13 e' l'anno prima (resta nel netto); il corrente e' l'utile CE
    if forma is None:
        forma, (s_sp, s_ce) = min((("bilancio", bilancio), ("verifica", verifica)),
                                  key=lambda x: abs(x[1][0]) + abs(x[1][1]))
    elif forma == "bilancio":
        s_sp, s_ce = bilancio
    elif forma == "verifica":
        s_sp, s_ce = verifica
    else:
        raise ValueError(f"forma sconosciuta: {forma!r} (attesa 'bilancio', 'verifica' o None)")
    scarto_stampati = Decimal(0)
    for chiave, nostro in (("totale_attivo", att), ("totale_passivo", pas if forma == "bilancio" else pas + utile)):
        v = (stampati or {}).get(chiave)
        if v is not None:
            scarto_stampati = max(scarto_stampati, abs(nostro - Decimal(v)))
    return {"attivo": att, "passivo": pas, "utile_ce": utile, "sp13": sp13, "forma": forma,
            "scarto_sp": s_sp.quantize(_C), "scarto_ce": s_ce.quantize(_C), "scarto_stampati": scarto_stampati.quantize(_C)}


def normalizza_forma(bs: dict, ce: dict, m: dict) -> dict:
    bs = dict(bs)
    if m["forma"] == "verifica":
        precedente = Decimal(bs.get("sp13_utile_perdita", 0))
        bs["sp12g_utili_perdite_portati"] = Decimal(bs.get("sp12g_utili_perdite_portati", 0)) + precedente
        bs["sp12_riserve"] = Decimal(bs.get("sp12_riserve", 0)) + precedente
        bs["sp13_utile_perdita"] = m["utile_ce"].quantize(_C)
    return bs


def _aggiungi(d: dict, campo: str, aggregato: str, v: Decimal) -> None:
    d[campo] = (Decimal(d.get(campo, 0)) + v).quantize(_C)
    d[aggregato] = (Decimal(d.get(aggregato, 0)) + v).quantize(_C)


def tappa(bs: dict, ce: dict, m: dict, s: Decimal):
    if m["attivo"] == 0 and m["passivo"] == 0:   # estrazione vuota: mai "ok"
        return bs, ce, None, "vuoto"
    if abs(m["scarto_sp"]) > s or abs(m["scarto_ce"]) > s or m["scarto_stampati"] > s:
        return bs, ce, None, "oltre_soglia"
    if m["scarto_sp"] == 0 and m["scarto_ce"] == 0:
        return bs, ce, None, "ok"
    nuovo_ce06 = None
    if m["scarto_ce"] != 0:       # utile CE diverso da sp13: i servizi assorbirebbero la differenza
        nuovo_ce06 = (Decimal(ce.get("ce06_servizi", 0)) + m["scarto_ce"]).quantize(_C)
        if nuovo_ce06 < 0:        # ma non sotto zero: il tappo non si applica, nulla si tocca
            return bs, ce, None, "oltre_soglia"
    bs, ce, tappo = dict(bs), dict(ce), {"soglia": str(s)}
    if m["scarto_sp"] > 0:        # attivo in piu': manca passivo
        _aggiungi(bs, "sp16g_altri_debiti_breve", "sp16_debiti_breve", m["scarto_sp"])
        tappo.update(campo="sp16g_altri_debiti_breve", importo=str(m["scarto_sp"]))
    elif m["scarto_sp"] < 0:      # manca attivo
        _aggiungi(bs, "sp06g_crediti_altri_breve", "sp06_crediti_breve", -m["scarto_sp"])
        tappo.update(campo="sp06g_crediti_altri_breve", importo=str(-m["scarto_sp"]))
    if nuovo_ce06 is not None:
        ce["ce06_servizi"] = nuovo_ce06
        tappo["ce"] = {"campo": "ce06_servizi", "importo": str(m["scarto_ce"])}
    return bs, ce, tappo, "tappo"
