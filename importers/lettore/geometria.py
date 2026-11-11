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
    return [RigaFisica(pagina, r["cy"], _ricompatta_lettere(sorted(r["parole"], key=lambda w: w.x0))) for r in righe]


_MIN_LETTERE_SPAZIATE = 3
_PASSO_MASSIMO = 2.5      # fra due lettere della stessa scritta spaziata: al piu' due caratteri e mezzo di vuoto
_STACCO_PAROLA = 1.5      # fra due parole: uno stacco di almeno una volta e mezza il passo fra le lettere


def _lettera(p: Parola) -> bool:
    return len(p.testo) == 1 and p.testo.isalpha() and p.testo.isupper()


def _ricompatta_lettere(parole: list[Parola]) -> list[Parola]:
    """Le scritte a lettere spaziate («T O T A L E   A T T I V O», «S T A T O   P A T R I M O N I A L E») tornano
    parole (Fase 5): una lettera maiuscola per token, almeno tre di fila a passo regolare. Lo stacco piu' largo del
    passo fra le lettere separa le parole («TOTALE», «ATTIVO»), come lo legge chi guarda la pagina. Senza, titoli e
    totali di sezione non si riconoscono: lato e ancore restano ignoti."""
    out: list[Parola] = []
    i, n = 0, len(parole)
    while i < n:
        if not _lettera(parole[i]):
            out.append(parole[i])
            i += 1
            continue
        j = i
        while j + 1 < n and _lettera(parole[j + 1]) and \
                parole[j + 1].x0 - parole[j].x1 <= _PASSO_MASSIMO * max(parole[j].x1 - parole[j].x0, 1.0):
            j += 1
        gruppo = parole[i:j + 1]
        if len(gruppo) < _MIN_LETTERE_SPAZIATE:
            out.extend(gruppo)
            i = j + 1
            continue
        stacchi = [b.x0 - a.x1 for a, b in zip(gruppo, gruppo[1:])]
        passo = min(stacchi)
        pezzo = [gruppo[0]]
        for stacco, p in zip(stacchi, gruppo[1:]):
            if stacco > _STACCO_PAROLA * max(passo, 0.5):
                out.append(_unisci(pezzo))
                pezzo = []
            pezzo.append(p)
        out.append(_unisci(pezzo))
        i = j + 1
    return out


def _unisci(pezzo: list[Parola]) -> Parola:
    return Parola(pezzo[0].x0, min(p.y0 for p in pezzo), pezzo[-1].x1, max(p.y1 for p in pezzo),
                  "".join(p.testo for p in pezzo))
