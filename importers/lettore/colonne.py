"""Colonne di importi del documento: bordi destri allineati, ruolo e periodo di ciascuna.

Le colonne vengono dai bordi destri degli importi (`schema_legge_generico._bordi`/`_colonne_pagina`); il
ruolo lo decidono i numeri (3 decimali = percentuale, a - b = differenza, la somma dei conti = mastro) e le
intestazioni lo confermano; il periodo viene dalle date stampate sopra la colonna (`_anni_intestazione`).
"""
from __future__ import annotations

import calendar
import re
import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from importers.lettore.geometria import Parola, RigaFisica
from importers.lettore.importi import leggi_importo
from importers.schema_legge_generico import _PAROLE_TESTATA, _e_differenza

# Due bordi destri nella stessa colonna distano al piu' cosi' (punti); una colonna ne porta almeno tanti.
_TOL_COLONNA = 14.0
_MIN_IMPORTI_COLONNA = 4
# A sinistra di qui c'e' la didascalia, non una colonna di importi.
_X0_MINIMO = 150.0
# Un'intestazione sta sopra una colonna se il suo bordo destro o il suo centro distano al piu' cosi'.
_TOL_INTESTAZIONE = 70.0
_TOL_SOMMA = Decimal("0.01")

# Anno nudo, gg/mm/aaaa, gg/mm/aa, con "/", "." o "-".
_DATA = re.compile(r"^(?:(\d{2})[-/.](\d{2})[-/.])?(20\d{2})$|^(\d{2})[-/.](\d{2})[-/.](\d{2})$")
# Una lista sola per le colonne di analisi (C10).
_ANALISI = {"differenza", "diff.", "scostamento", "scost.", "variazione", "%"}
_ANALISI_DIFFERENZA = {"differenza", "diff.", "variazione"}
_RUOLI_TESTATA = {"dare": "dare", "avere": "avere", "saldo": "saldo"}
_PAROLE_RIGA_TESTATA = _PAROLE_TESTATA | _ANALISI | set(_RUOLI_TESTATA) | {"dal", "fino", "infrannuale"}
# Lessico di testata per le intestazioni gia' divise in celle (le tabelle OCR, `celle.py`): quali parole di testata
# sono di una colonna di valori («Importo», «Esercizio precedente», «Scost. %») e quali della descrizione («Cod.»,
# «Partitario»); le altre parole di testata stanno in `_PAROLE_RIGA_TESTATA` e in `totali._TESTATA`.
_PAROLE_VALORE = {"importo", "importi", "saldo", "saldi", "dare", "avere", "esercizio", "esercizi", "corrente",
                  "precedente", "consuntivo", "comparato", "valori", "progr", "progressivo", "progressivi",
                  "differenza", "diff", "scost", "scostamento", "variazione", "var", "%", "periodo", "bilancio",
                  "anno", "totali", "parziali", "rettificato", "finale", "euro", "\u20ac", "eserc"}
_PAROLE_DESCRIZIONE = {"partitario", "sottoconto", "sottoconti", "mastri", "denominazione", "nr", "n"}


def _parola_testata(token: str) -> str:
    """Una parola d'intestazione nella forma del lessico: minuscola, senza parentesi, punti e due punti attorno
    («(€)» -> «€», «Scost.» -> «scost», «2025:» -> «2025»)."""
    return token.strip().casefold().strip("().:;[]")


@dataclass
class Colonna:
    indice: int                  # 0.. nell'ordine x
    x_destra: float              # bordo destro mediano
    lato: str                    # "U" (unico) | "L" | "R" (Task 4 lo raffina)
    ruolo: str                   # "esercizio" | "mastro" | "differenza" | "percentuale" | "dare" | "avere" | "saldo" | "ignoto"
    fine: date | None            # data di chiusura stampata sopra la colonna
    inizio: date | None
    mesi: int | None             # da inizio..fine, o da gennaio se l'inizio non e' stampato
    corrente: bool               # la colonna-esercizio piu' recente


def colonna_di(x_destra: float, colonne: list[Colonna]) -> Colonna | None:
    """La colonna il cui bordo destro dista al piu' 14 pt; None = fuori colonna."""
    vicine = [c for c in colonne if abs(c.x_destra - x_destra) <= _TOL_COLONNA]
    return min(vicine, key=lambda c: abs(c.x_destra - x_destra)) if vicine else None


def colonne_documento(righe: list[RigaFisica]) -> list[Colonna]:
    colonne = _colonne_dai_bordi(righe)
    if not colonne:
        return []
    valori = _valori(righe, colonne)
    periodi, parole = _intestazioni(righe, colonne)
    for c in colonne:
        c.fine, c.inizio, c.mesi = periodi.get(c.indice, (None, None, None))
    _ruoli(colonne, valori, parole, periodi)
    _mastri(colonne, valori)
    _corrente(colonne)
    return colonne


def _colonne_dai_bordi(righe: list[RigaFisica]) -> list[Colonna]:
    bordi = sorted(p.x1 for r in righe for p in r.parole
                   if _in_colonna(p) and _e_importo(p.testo))
    gruppi: list[list[float]] = []
    for x in bordi:
        if gruppi and x - gruppi[-1][-1] <= _TOL_COLONNA:
            gruppi[-1].append(x)
        else:
            gruppi.append([x])
    tenuti = [g for g in gruppi if len(g) >= _MIN_IMPORTI_COLONNA]
    return [Colonna(i, statistics.median(g), "U", "ignoto", None, None, None, False)
            for i, g in enumerate(tenuti)]


def _e_importo(testo: str) -> bool:
    imp = leggi_importo(testo)
    return imp is not None and imp.forma != "zero"


def _in_colonna(p: Parola) -> bool:
    """Un importo che comincia nella zona della didascalia non fa colonna e non vi conta."""
    return p.x0 > _X0_MINIMO


def _valori(righe: list[RigaFisica], colonne: list[Colonna]) -> list[list]:
    """Per ogni riga con importi, nell'ordine del documento: [pagina, y, valori per colonna, forme]."""
    out = []
    for r in sorted(righe, key=lambda r: (r.pagina, r.y)):
        valori: list[Decimal | None] = [None] * len(colonne)
        forme: list[str | None] = [None] * len(colonne)
        doppie: set[int] = set()
        for p in r.parole:
            imp = leggi_importo(p.testo) if _in_colonna(p) else None
            c = colonna_di(p.x1, colonne) if imp is not None else None
            if c is None:
                continue
            if valori[c.indice] is not None:
                doppie.add(c.indice)
            valori[c.indice], forme[c.indice] = imp.valore, imp.forma
        for i in doppie:        # due importi nella stessa colonna: la cella non si sa leggere
            valori[i] = forme[i] = None
        if any(v is not None for v in valori):
            out.append([r.pagina, r.y, valori, forme])
    return out


# --------------------------------------------------------------------------------------
# Intestazioni: date e parole sopra le colonne
# --------------------------------------------------------------------------------------

def _data(testo: str) -> tuple[date, bool] | None:
    """(data, stampata per intero); un anno nudo vale il 31/12 di quell'anno."""
    m = _DATA.match(testo.strip())
    if not m:
        return None
    try:
        if m.group(3):
            if m.group(1) is None:
                return date(int(m.group(3)), 12, 31), False
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), True
        return date(2000 + int(m.group(6)), int(m.group(5)), int(m.group(4))), True
    except ValueError:
        return None


def _sopra(parola: Parola, colonne: list[Colonna]) -> Colonna | None:
    centro = (parola.x0 + parola.x1) / 2
    c = min(colonne, key=lambda c: abs(parola.x1 - c.x_destra))
    if abs(parola.x1 - c.x_destra) <= _TOL_INTESTAZIONE or abs(centro - c.x_destra) <= _TOL_INTESTAZIONE:
        return c
    return None


def _norm(testo: str) -> str:
    return testo.strip().casefold().rstrip(":")


def _e_riga_testata(r: RigaFisica) -> bool:
    """Solo parole di testata, date e anni: «ESERCIZIO ESERCIZIO DIFFERENZA SCOST.», «DARE AVERE SALDO»."""
    return all(_norm(p.testo) in _PAROLE_RIGA_TESTATA or re.fullmatch(r"[\d\-./]+", p.testo.strip())
               for p in r.parole)


def _mesi(inizio: date | None, fine: date, intera: bool) -> int | None:
    """Mesi da inizio a fine (da gennaio se l'inizio manca); None se gli estremi non sono di mese intero
    o se la data e' un anno nudo."""
    if not intera or fine.day != calendar.monthrange(fine.year, fine.month)[1]:
        return None
    if inizio is None:
        return fine.month
    if inizio.day != 1 or inizio > fine:
        return None
    return (fine.year - inizio.year) * 12 + fine.month - inizio.month + 1


def _periodi_riga(r: RigaFisica, colonne: list[Colonna]) -> dict[int, tuple] | None:
    """Colonna -> (fine, inizio, mesi) dalle date della riga; None se la riga e' una frase (una data
    lontana dalle colonne, o due periodi sopra la stessa colonna)."""
    parole = r.parole
    trovati: dict[int, list[tuple]] = {}
    k = 0
    while k < len(parole):
        d = _data(parole[k].testo)
        if d is None:
            k += 1
            continue
        inizio = None
        prima = _norm(parole[k - 1].testo) if k else ""
        # «dal 01/01/2026 al 31/05/2026»: l'inizio e la fine sono un periodo solo, sopra la fine
        if (prima == "dal" and d[1] and k + 2 < len(parole) and _norm(parole[k + 1].testo) == "al"
                and (f := _data(parole[k + 2].testo)) is not None and f[1]):
            inizio, d, k = d[0], f, k + 2
        c = _sopra(parole[k], colonne)
        if c is None:
            return None
        trovati.setdefault(c.indice, []).append((d[0], inizio, _mesi(inizio, d[0], d[1])))
        k += 1
    if any(len(v) > 1 for v in trovati.values()):
        return None
    return {i: v[0] for i, v in trovati.items()}


def _intestazioni(righe: list[RigaFisica], colonne: list[Colonna]):
    """(colonna -> periodo, colonna -> parole di ruolo) dalle righe di testata sopra le colonne.

    Un'intestazione vera ha importi sotto di se' (`standard_ivcee_parser._anchors_carry_amounts`): vale
    solo per una colonna che porta un importo piu' in basso sulla stessa pagina. Il periodo si legge solo
    da una riga di testata («Data stampa 15/03/2026» non lo e'), e fra piu' testate vince la piu' vicina
    sopra gli importi della colonna, sulla prima pagina che ne ha una."""
    importi: dict[tuple[int, int], list[float]] = {}
    for r in righe:
        for p in r.parole:
            if _in_colonna(p) and _e_importo(p.testo) and (c := colonna_di(p.x1, colonne)) is not None:
                importi.setdefault((r.pagina, c.indice), []).append(r.y)

    def distanza(r: RigaFisica, i: int) -> float | None:
        sotto = [y for y in importi.get((r.pagina, i), []) if y > r.y]
        return min(sotto) - r.y if sotto else None

    candidati: dict[int, tuple] = {}     # colonna -> ((pagina, distanza), periodo)
    parole: dict[int, set[str]] = {}
    for r in sorted(righe, key=lambda r: (r.pagina, r.y)):
        if any(_e_importo(p.testo) for p in r.parole) or not _e_riga_testata(r):
            continue
        for i, periodo in (_periodi_riga(r, colonne) or {}).items():
            if (d := distanza(r, i)) is not None and (i not in candidati or (r.pagina, d) < candidati[i][0]):
                candidati[i] = ((r.pagina, d), periodo)
        for p in r.parole:
            n = _norm(p.testo)
            if (n in _ANALISI or n in _RUOLI_TESTATA) and (c := _sopra(p, colonne)) is not None \
                    and distanza(r, c.indice) is not None:
                parole.setdefault(c.indice, set()).add(n)
    return {i: v[1] for i, v in candidati.items()}, parole


# --------------------------------------------------------------------------------------
# Ruoli
# --------------------------------------------------------------------------------------

def _ruoli(colonne: list[Colonna], valori: list[list], parole: dict[int, set[str]],
           periodi: dict[int, tuple]) -> None:
    matrice = [riga[2] for riga in valori]
    esercizi: list[int] = []
    for c in colonne:
        nomi = parole.get(c.indice, set())
        testata = {_RUOLI_TESTATA[n] for n in nomi if n in _RUOLI_TESTATA}
        if len(testata) == 1:           # dare/avere/saldo: l'intestazione decide (saldo = dare - avere)
            c.ruolo = testata.pop()
            continue
        if testata:
            c.ruolo = "ignoto"
            continue
        forme = [riga[3][c.indice] for riga in valori if riga[3][c.indice] not in (None, "zero")]
        if forme and sum(1 for f in forme if f == "percentuale") >= max(1, len(forme) // 2):
            c.ruolo = "percentuale"
            continue
        if c.indice not in periodi and any(
                _e_differenza(matrice, c.indice, a, b) for a in esercizi for b in esercizi if a < b):
            c.ruolo = "differenza"
            continue
        analisi = nomi & _ANALISI
        if analisi:     # i numeri non lo dicono, l'intestazione dice che non e' un esercizio
            c.ruolo = "percentuale" if "%" in analisi else (
                "differenza" if analisi & _ANALISI_DIFFERENZA else "ignoto")
            continue
        c.ruolo = "esercizio"
        esercizi.append(c.indice)


def _e_mastro(valori: list[list], m: int, f: int) -> bool:
    """Ogni importo della colonna m e' la somma degli importi della colonna f che lo seguono, fino al
    prossimo importo di m; le due colonne non sono mai piene sulla stessa riga."""
    gruppi: list[list] = []
    for riga in valori:
        vm, vf = riga[2][m], riga[2][f]
        if vm is not None and vf is not None:
            return False
        if vm is not None:
            gruppi.append([vm, Decimal("0"), 0])
        elif vf is not None and gruppi:
            gruppi[-1][1] += vf
            gruppi[-1][2] += 1
    return len(gruppi) >= 2 and all(n > 0 and abs(tot - somma) <= _TOL_SOMMA for tot, somma, n in gruppi)


def _mastri(colonne: list[Colonna], valori: list[list]) -> None:
    """Due colonne-esercizio vicine dello stesso periodo: quella che somma i conti dell'altra e' dei mastri,
    e il periodo stampato sopra una vale per entrambe."""
    esercizi = [c for c in colonne if c.ruolo == "esercizio"]
    for a, b in zip(esercizi, esercizi[1:]):
        if a.fine is not None and b.fine is not None and (a.fine, a.mesi) != (b.fine, b.mesi):
            continue
        for m, f in ((a, b), (b, a)):
            if m.ruolo == "esercizio" and f.ruolo == "esercizio" and _e_mastro(valori, m.indice, f.indice):
                m.ruolo = "mastro"
                fonte = m if m.fine is not None else f
                for c in (m, f):
                    c.fine, c.inizio, c.mesi = fonte.fine, fonte.inizio, fonte.mesi
                break


def _corrente(colonne: list[Colonna]) -> None:
    """La colonna di valori piu' recente, ovunque stia (C4). Valori = esercizio e saldo: in un bilancio di
    verifica dare e avere sono movimenti, il saldo e' il valore di chiusura del periodo. Una sola colonna di
    valori e' la corrente anche senza data; piu' colonne senza date, o la data piu' recente su due colonne,
    nessuna."""
    esercizi = [c for c in colonne if c.ruolo in ("esercizio", "saldo")]
    if len(esercizi) == 1:
        esercizi[0].corrente = True
        return
    datate = [c for c in esercizi if c.fine is not None]
    if not datate:
        return
    recente = max(c.fine for c in datate)
    scelte = [c for c in datate if c.fine == recente]
    if len(scelte) == 1:
        scelte[0].corrente = True
