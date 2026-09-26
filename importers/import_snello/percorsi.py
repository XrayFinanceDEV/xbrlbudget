"""Percorsi di legge (artt. 2424-2425 c.c.) -> campi del budget.

Il modello nomina la voce di legge ('SPP.D.4.E'); questa tabella fissa la traduce nel campo.
Mai far scegliere al modello un codice da un elenco lungo: senza thinking lo scorre in ordine.
"""
from __future__ import annotations

import os
from decimal import Decimal

LEGENDA = open(os.path.join(os.path.dirname(__file__), "legenda.txt"), encoding="utf-8").read()


def _nomi() -> dict[str, str]:
    from database.models import BalanceSheet, IncomeStatement
    out = {}
    for modello in (BalanceSheet, IncomeStatement):
        for colonna in modello.__table__.columns:
            if colonna.name[:2] in ("sp", "ce"):
                out[colonna.name.split("_")[0]] = colonna.name
    return out


NOMI = _nomi()
_CR = {"1": "a", "2": "b", "3": "c", "4": "d", "5-bis": "e", "5-ter": "f", "5-quater": "g"}
_DEB = {"1": "c", "2": "c", "3": "b", "4": "a", "5": "b", "6": "g", "7": "d", "8": "d", "9": "g",
        "10": "g", "11": "g", "11-bis": "g", "12": "e", "13": "f", "14": "g"}
_PN = {"I": "sp11", "II": "sp12a", "III": "sp12b", "IV": "sp12c", "V": "sp12d", "VI": "sp12e",
       "VII": "sp12f", "VIII": "sp12g", "IX": "sp13", "X": "sp12h"}
_CE = {"1": "ce01", "2": "ce02", "3": "ce02", "4": "ce03", "5": "ce04", "6": "ce05", "7": "ce06",
       "8": "ce07", "11": "ce10", "12": "ce11", "13": "ce11b", "14": "ce12", "15": "ce13", "16": "ce14",
       "17": "ce15", "17-bis": "ce16", "18": "ce17a", "19": "ce17b", "20": "ce20"}
RICAVI = {"ce01", "ce02", "ce03", "ce03a", "ce04", "ce13", "ce14", "ce16", "ce17a", "ce18"}
ATTIVO = ("sp01", "sp02", "sp03", "sp04", "sp05", "sp06", "sp07", "sp08", "sp09", "sp10")

CONTROPARTE = {
    "SPA.C.IV": "SPP.D.4", "SPA.C.II.5-bis": "SPP.D.12", "SPA.C.II.1": "SPP.D.6", "SPA.C.II.5-quater": "SPP.D.14",
    "SPA.C.II.2": "SPP.D.9", "SPA.C.II.3": "SPP.D.10", "SPA.C.II.4": "SPP.D.11",
    "SPP.D.4": "SPA.C.IV.1", "SPP.D.12": "SPA.C.II.5-bis", "SPP.D.13": "SPA.C.II.5-quater",
    "SPP.D.7": "SPA.C.II.5-quater", "SPP.D.14": "SPA.C.II.5-quater", "SPP.D.5": "SPA.C.II.5-quater",
    "SPP.D.6": "SPA.C.II.1", "SPP.D.3": "SPA.C.II.5-quater",
}


def e_fondo(p: str) -> bool:
    return p.endswith(".F")


def e_risultato(p: str) -> bool:
    return p in ("CE.21", "CE.D.21")


def lato_di(p: str) -> str | None:
    return {"SPA": "att", "SPP": "pas", "CE": "ce"}.get(p.split(".")[0])


def campo_da_percorso(p: str) -> str | None:
    if not p or p in ("X", "R") or e_risultato(p):
        return None
    t = [x for x in p.split(".") if x != "F"]
    scad = t[-1] if len(t) > 2 and t[-1] in ("E", "O") else None
    if scad:
        t = t[:-1]
    try:
        if t[0] == "SPA" and len(t) >= 2:
            if t[1] == "A":
                return "sp01"
            if t[1] == "B":
                if len(t) == 2:
                    return None
                if len(t) == 3:
                    return {"I": "sp02", "II": "sp03", "III": "sp04"}.get(t[2])
                n = int(t[3])
                if t[2] == "I" and 1 <= n <= 7:
                    return "sp02" + "abcdefg"[n - 1]
                if t[2] == "II" and 1 <= n <= 5:
                    return "sp03" + "abcde"[n - 1]
                if t[2] == "III":
                    return {1: "sp04a", 2: "sp04c" if scad == "O" else "sp04b", 3: "sp04d", 4: "sp04e"}.get(n)
            if t[1] == "C" and len(t) >= 3:
                if t[2] == "I":
                    return "sp05" + "abcde"[int(t[3]) - 1] if len(t) > 3 else "sp05"
                if t[2] == "II":
                    base = "sp07" if scad == "O" else "sp06"
                    return base + _CR[t[3]] if len(t) > 3 else base
                if t[2] == "III":
                    return "sp08"
                if t[2] == "IV":
                    return "sp09"
            if t[1] == "D":
                return "sp10"
        if t[0] == "SPP" and len(t) >= 2:
            if t[1] == "A" and len(t) >= 3:
                return _PN.get(t[2])
            if t[1] == "B" and len(t) >= 3:
                return "sp14" + "abcd"[int(t[2]) - 1]
            if t[1] == "C":
                return "sp15"
            if t[1] == "D":
                base = "sp17" if scad == "O" else "sp16"
                return base + _DEB[t[2]] if len(t) > 2 else (base if scad else None)
            if t[1] == "E":
                return "sp18"
        if t[0] == "CE":
            n = [x for x in t[1:] if x not in ("A", "B", "C", "D", "E")]
            if not n:
                return None
            voce, sub = n[0], (n[1] if len(n) > 1 else None)
            if voce == "9":
                return {"a": "ce08b", "b": "ce08c", "c": "ce08a", "d": "ce08d", "e": "ce08d"}.get(sub, "ce08") if sub else "ce08"
            if voce == "10":
                return {"a": "ce09a", "b": "ce09b", "c": "ce09c", "d": "ce09d"}.get(sub, "ce09") if sub else "ce09"
            return _CE.get(voce)
    except (ValueError, KeyError, IndexError):
        return None
    return None


def famiglia(codice: str) -> str:
    if codice.startswith("sp"):
        return "att" if codice[:4] in ATTIVO else "pas"
    return "ric" if codice in RICAVI else "cos"


def completa(importi: dict[str, Decimal]) -> tuple[dict, dict]:
    """Codici brevi -> (bs, ce) con nomi completi; ogni aggregato = valore diretto + sotto-campi."""
    from importers.iv_cee_hierarchy import aggregates_with_details, detail_fields
    cent = Decimal("0.01")
    pieni = {NOMI[c]: Decimal(v) for c, v in importi.items() if c in NOMI}
    for aggregato in aggregates_with_details():
        dettagli = [d for d in detail_fields(aggregato) if d in pieni]
        if dettagli:
            pieni[aggregato] = pieni.get(aggregato, Decimal(0)) + sum((pieni[d] for d in dettagli), Decimal(0))
    bs = {k: v.quantize(cent) for k, v in pieni.items() if k.startswith("sp")}
    ce = {k: v.quantize(cent) for k, v in pieni.items() if k.startswith("ce")}
    return bs, ce
