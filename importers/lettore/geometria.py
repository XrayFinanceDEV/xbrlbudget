"""Parole di una pagina PDF e righe fisiche, nel riferimento visualizzato (dopo l'eventuale rotazione)."""
from dataclasses import dataclass, field

import fitz

# Stessa regola di `situazione_contabile_parser._be_cluster_physical_rows`: i frammenti di una riga stampata
# hanno 1-3 pt di jitter di linea di base, le righe contabili distano almeno ~9 pt.
_TOLLERANZA_CENTRI = 3.6
_SOVRAPPOSIZIONE_MIN = 0.55
_RIGHE_CANDIDATE = 4


@dataclass(frozen=True)
class Parola:
    x0: float
    y0: float
    x1: float
    y1: float
    testo: str


@dataclass
class RigaFisica:
    pagina: int  # 1-based
    y: float  # centro verticale
    parole: list[Parola] = field(default_factory=list)  # ordinate per x0


def _righe_non_orizzontali(pagina: "fitz.Page") -> list["fitz.Rect"]:
    """I riquadri delle righe di testo che a schermo non sono orizzontali: timbri e note scritti in verticale sul
    margine. Le loro parole sono alte quanto piu' righe contabili e le unirebbero in una sola (1531)."""
    out = []
    for b in pagina.get_text("dict")["blocks"]:
        for linea in b.get("lines", ()):
            dx, dy = linea["dir"]
            if pagina.rotation:
                v = fitz.Point(dx, dy) * pagina.rotation_matrix - fitz.Point(0, 0) * pagina.rotation_matrix
                dx, dy = v.x, v.y
            if abs(dy) > abs(dx):
                out.append(fitz.Rect(linea["bbox"]))
    return out


def parole_pagina(pagina: "fitz.Page") -> list[Parola]:
    """Parole della pagina; con la pagina ruotata le coordinate sono portate nel riferimento visualizzato. Le parole
    scritte in verticale a schermo (timbri, note a margine) non sono parole del prospetto e si tolgono."""
    risultato = []
    verticali = _righe_non_orizzontali(pagina)
    for w in pagina.get_text("words", sort=True):
        rett = fitz.Rect(w[:4])
        centro = fitz.Point((rett.x0 + rett.x1) / 2, (rett.y0 + rett.y1) / 2)
        if any(centro in v for v in verticali):
            continue
        if pagina.rotation:
            rett = rett * pagina.rotation_matrix
        risultato.append(Parola(rett.x0, rett.y0, rett.x1, rett.y1, w[4]))
    return risultato


def righe_fisiche(parole: list[Parola], pagina: int) -> list[RigaFisica]:
    """Raggruppa le parole in righe: centri entro 3,6 pt oppure sovrapposizione verticale >= 55% dell'altezza minore."""
    scelte = sorted((p for p in parole if p.testo.strip()), key=lambda p: ((p.y0 + p.y1) / 2, p.x0))
    righe: list[dict] = []
    for p in scelte:
        cy = (p.y0 + p.y1) / 2
        candidate = []
        for idx in range(max(0, len(righe) - _RIGHE_CANDIDATE), len(righe)):
            r = righe[idx]
            sovrapp = max(0.0, min(p.y1, r["y1"]) - max(p.y0, r["y0"]))
            minima = min(p.y1 - p.y0, r["y1"] - r["y0"])
            distanza = abs(cy - r["cy"])
            if distanza <= _TOLLERANZA_CENTRI or (minima > 0 and sovrapp >= _SOVRAPPOSIZIONE_MIN * minima):
                candidate.append((distanza, idx))
        if candidate:
            r = righe[min(candidate)[1]]
            r["parole"].append(p)
            r["y0"] = min(r["y0"], p.y0)
            r["y1"] = max(r["y1"], p.y1)
            r["cy"] = sum((w.y0 + w.y1) / 2 for w in r["parole"]) / len(r["parole"])
        else:
            righe.append({"parole": [p], "y0": p.y0, "y1": p.y1, "cy": cy})
    return [RigaFisica(pagina, r["cy"], sorted(r["parole"], key=lambda w: w.x0)) for r in righe]
