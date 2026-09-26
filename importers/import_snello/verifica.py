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


def misura(bs: dict, ce: dict, stampati: dict | None = None) -> dict:
    att = sum((Decimal(bs.get(k, 0)) for k in _ATTIVO_FIELDS), Decimal(0))
    pas = sum((Decimal(bs.get(k, 0)) for k in _PASSIVO_FIELDS), Decimal(0))
    sp13 = Decimal(bs.get("sp13_utile_perdita", 0))
    utile = calculate_ce_result(ce).net_profit
    bilancio = (att - pas, utile - sp13)                     # sp13 e' il risultato corrente
    verifica = (att - pas - utile, Decimal(0))               # sp13 e' l'anno prima (resta nel netto); il corrente e' l'utile CE
    forma, (s_sp, s_ce) = min((("bilancio", bilancio), ("verifica", verifica)),
                              key=lambda x: abs(x[1][0]) + abs(x[1][1]))
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
    if abs(m["scarto_sp"]) > s or abs(m["scarto_ce"]) > s or m["scarto_stampati"] > s:
        return bs, ce, None, "oltre_soglia"
    if m["scarto_sp"] == 0 and m["scarto_ce"] == 0:
        return bs, ce, None, "ok"
    bs, ce, tappo = dict(bs), dict(ce), {"soglia": str(s)}
    if m["scarto_sp"] > 0:        # attivo in piu': manca passivo
        _aggiungi(bs, "sp16g_altri_debiti_breve", "sp16_debiti_breve", m["scarto_sp"])
        tappo.update(campo="sp16g_altri_debiti_breve", importo=str(m["scarto_sp"]))
    elif m["scarto_sp"] < 0:      # manca attivo
        _aggiungi(bs, "sp06g_crediti_altri_breve", "sp06_crediti_breve", -m["scarto_sp"])
        tappo.update(campo="sp06g_crediti_altri_breve", importo=str(-m["scarto_sp"]))
    if m["scarto_ce"] != 0:       # utile CE diverso da sp13: i servizi assorbono la differenza
        ce["ce06_servizi"] = (Decimal(ce.get("ce06_servizi", 0)) + m["scarto_ce"]).quantize(_C)
        tappo["ce"] = {"campo": "ce06_servizi", "importo": str(m["scarto_ce"])}
    return bs, ce, tappo, "tappo"
