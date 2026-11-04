"""Lati delle sezioni contrapposte: un solo rilevatore del confine fra sinistra (attivo/costi) e destra.

Principio di `situazione_contabile_parser._be_split`/`_be_split_codeless`: il confine e' un varco verticale
fra due gruppi di colonne, ciascuno con le proprie descrizioni, su piu' righe; vince il taglio piu'
equilibrato, a parita' il piu' vicino al centro. Le parole ATTIVITA'/PASSIVITA', COSTI/RICAVI sulla stessa
riga, una per lato, lo confermano (bastano meno righe descritte), non lo decidono (C11).
"""
from __future__ import annotations

import unicodedata

from importers.lettore.colonne import Colonna, colonna_di
from importers.lettore.geometria import Parola, RigaFisica
from importers.lettore.importi import leggi_importo

# Righe con descrizione e importo che ogni lato deve avere; con l'intestazione che conferma, meno.
_MIN_RIGHE_LATO = 3
_MIN_RIGHE_CONFERMATO = 2
# Un varco piu' stretto di cosi' fra due parole e' lo spazio fra due parole, non fra due colonne.
_VARCO_MIN = 0.5
_X0_MINIMO = 150.0      # come `colonne._in_colonna`
_COPPIE_TESTATA = ((("attivit", "attivo"), ("passivit", "passivo")), (("costi",), ("ricavi",)))


def confine_dei_lati(righe: list[RigaFisica], colonne: list[Colonna]) -> float | None:
    """x del confine fra lato sinistro e destro; None = una sola sezione."""
    ordinate = sorted(colonne, key=lambda c: c.x_destra)
    if len(ordinate) < 2:
        return None
    dati = [(r, _celle(r, colonne)) for r in righe]
    dati = [(r, celle) for r, celle in dati if celle]
    tutte = [p for r in righe for p in r.parole if p.testo.strip()]
    centro = _centro(tutte)
    migliori = []
    for a, b in zip(ordinate, ordinate[1:]):
        x = _varco(dati, a, b)
        if x is None:
            continue
        sx = sum(1 for r, celle in dati if _descritta(r, celle, -1e9, x))
        dx = sum(1 for r, celle in dati if _descritta(r, celle, x, 1e9))
        minimo = _MIN_RIGHE_CONFERMATO if _confermato(righe, colonne, x) else _MIN_RIGHE_LATO
        if sx >= minimo and dx >= minimo:
            migliori.append((min(sx, dx), -abs(x - centro), x))
    return max(migliori)[2] if migliori else None


def assegna_lati(colonne: list[Colonna], confine: float | None) -> list[Colonna]:
    """Lato "L" a sinistra del confine, "R" a destra; tutte "U" senza confine."""
    for c in colonne:
        c.lato = "U" if confine is None else ("L" if c.x_destra < confine else "R")
    return colonne


def _celle(r: RigaFisica, colonne: list[Colonna]) -> list[Parola]:
    """Le parole della riga che sono importi in una colonna."""
    return [p for p in r.parole
            if p.x0 > _X0_MINIMO and leggi_importo(p.testo) is not None
            and colonna_di(p.x1, colonne) is not None]


def _centro(parole: list[Parola]) -> float:
    """Centro del contenuto, robusto a intestazioni e piedi lontani (5°/95° percentile)."""
    xs = sorted((p.x0 + p.x1) / 2 for p in parole)
    if not xs:
        return 0.0
    return (xs[int(0.05 * len(xs))] + xs[min(len(xs) - 1, int(0.95 * len(xs)))]) / 2


def _varco(dati: list[tuple[RigaFisica, list[Parola]]], a: Colonna, b: Colonna) -> float | None:
    """Il primo varco a destra della colonna `a` che nessuna parola di una riga con importi attraversa,
    prima che finisca la colonna `b`; il centro del varco, o None."""
    coperti = sorted((p.x0, p.x1) for r, _ in dati for p in r.parole
                     if p.testo.strip() and p.x1 > a.x_destra and p.x0 < b.x_destra)
    cursore = a.x_destra
    for x0, x1 in coperti:
        if x0 > cursore + _VARCO_MIN:
            return (cursore + x0) / 2
        cursore = max(cursore, x1)
    return None


def _descritta(r: RigaFisica, celle: list[Parola], lo: float, hi: float) -> bool:
    """La riga ha, fra lo e hi, un importo in colonna e una descrizione (una parola con lettere) alla sua
    sinistra."""
    importi = [p for p in celle if lo < p.x0 and p.x1 < hi]
    if not importi:
        return False
    primo = min(p.x0 for p in importi)
    return any(lo < p.x0 and p.x1 <= primo and any(ch.isalpha() for ch in p.testo)
               and leggi_importo(p.testo) is None for p in r.parole)


def _piega(testo: str) -> str:
    senza = unicodedata.normalize("NFKD", testo.casefold())
    return "".join(ch for ch in senza if ch.isalpha())


def _confermato(righe: list[RigaFisica], colonne: list[Colonna], x: float) -> bool:
    """Una riga senza importi in colonna porta la parola del lato sinistro prima di x e quella del destro dopo, in
    qualunque maiuscolo e con o senza accento («Conto attivo … Conto passivo» su una riga di conti non
    e' un'intestazione)."""
    for r in righe:
        if _celle(r, colonne):
            continue
        parole = [(p, _piega(p.testo)) for p in r.parole]
        for sinistre, destre in _COPPIE_TESTATA:
            if any(p.x1 < x and n.startswith(sinistre) for p, n in parole) and \
                    any(p.x0 > x and n.startswith(destre) for p, n in parole):
                return True
    return False
