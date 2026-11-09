"""Percorsi di legge (artt. 2424-2425 c.c.) -> campi del budget.

Il modello nomina la voce di legge ('SPP.D.4.E'); questa tabella fissa come tradurla nel campo.
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


def e_netto(p: str) -> bool:
    """Capitale, riserve, risultati (SPP.A.*): cambiano lato col segno per natura (un utile
    e una perdita hanno naturalmente lato invertito), e non esiste una contropartita per
    ribaltarli. La colonna non decide il loro segno: lo decide il valore letto."""
    t = p.split(".")
    return len(t) >= 2 and t[0] == "SPP" and t[1] == "A"


def e_risultato(p: str) -> bool:
    return p in ("CE.21", "CE.D.21")


def lato_di(p: str) -> str | None:
    return {"SPA": "att", "SPP": "pas", "CE": "ce"}.get(p.split(".")[0])


def campo_da_percorso(p: str) -> str | None:
    """Percorso di legge -> campo. La tavola sta in `importers.lettore.tavola.campo_di_legge` (una sola)."""
    from importers.lettore.tavola import campo_di_legge   # import tardivo: la tavola importa questo modulo
    return campo_di_legge(p)


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
