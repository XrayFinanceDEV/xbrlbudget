"""Lati delle sezioni contrapposte: un solo rilevatore del confine fra sinistra (attivo/costi) e destra.

Principio di `situazione_contabile_parser._be_split`/`_be_split_codeless`: il confine e' un varco verticale
fra due gruppi di colonne, ciascuno con le proprie descrizioni, su piu' righe; vince il taglio piu'
equilibrato, a parita' il piu' vicino al centro. Le parole ATTIVITA'/PASSIVITA', COSTI/RICAVI sulla stessa
riga, una per lato, lo confermano (bastano meno righe descritte), non lo decidono (C11). Il profilo del
documento accetta il confine solo con i due lati simmetrici (`confine_ammesso`).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
import unicodedata

from importers.lettore.colonne import Colonna, _corrente, colonna_di
from importers.lettore.geometria import Parola, RigaFisica
from importers.lettore.importi import leggi_importo

# Righe con descrizione e importo che ogni lato deve avere; con l'intestazione che conferma, meno.
_MIN_RIGHE_LATO = 3
_MIN_RIGHE_CONFERMATO = 2
# Un varco piu' stretto di cosi' fra due parole e' lo spazio fra due parole, non fra due colonne.
_VARCO_MIN = 0.5
_X0_MINIMO = 150.0      # come `colonne._in_colonna`
_COPPIE_TESTATA = ((("attivit", "attivo"), ("passivit", "passivo")), (("costi",), ("ricavi",)))
# «D»/«A» dopo un importo ne sono il segno (dare/avere), non la descrizione di un lato (budget_682, 1533, 1540).
_MARCATORI = {"D", "A"}
# Ruoli che si confrontano fra i lati: i valori di periodo insieme, gli altri ciascuno per se'.
_GRUPPO_RUOLO = {"esercizio": "valori", "saldo": "valori", "mastro": "valori", "dare": "dare", "avere": "avere",
                 "differenza": "differenza", "percentuale": "percentuale"}
# Su una pagina una colonna conta in un lato se ha celle su almeno questa quota delle righe con importi di quel lato
# della pagina; si confrontano le pagine con almeno tante righe per lato. Una colonna che copre solo un pezzo di
# pagina (una tabella in coda, i mastri di poche righe) non vi conta.
_QUOTA_RIGHE_PAGINA = 0.25
_MIN_RIGHE_PAGINA = 3


def confine_dei_lati(righe: list[RigaFisica], colonne: list[Colonna]) -> float | None:
    """x del confine fra lato sinistro e destro; None = una sola sezione."""
    ordinate = sorted(colonne, key=lambda c: c.x_destra)
    if len(ordinate) < 2:
        return None
    dati = [(r, _celle(r, colonne)) for r in righe]
    dati = [(r, celle) for r, celle in dati if celle]
    tutte = [p for r in righe for p in r.parole if p.testo.strip()]
    centro = _centro(tutte)
    inizi: dict[int, list[float]] = {}
    for _, celle in dati:
        for p in celle:
            inizi.setdefault(colonna_di(p.x1, colonne).indice, []).append(p.x0)
    migliori = []
    for a, b in zip(ordinate, ordinate[1:]):
        x = _varco(dati, a, b)
        if x is None:
            continue
        # Dal bordo sinistro tipico degli importi di sinistra fino al varco ci sono solo importi: una parola
        # di testo li' e' una descrizione che sfora, e la riga non descrive nessuno dei due lati.
        zona = min(statistics.median(inizi[c.indice]) for c in ordinate if c.x_destra < x)
        pulite = [(r, celle) for r, celle in dati if not _sfora(r, zona, x)]
        sx = sum(1 for r, celle in pulite if _descritta(r, celle, -1e9, x))
        dx = sum(1 for r, celle in pulite if _descritta(r, celle, x, 1e9))
        minimo = _MIN_RIGHE_CONFERMATO if _confermato(righe, colonne, x) else _MIN_RIGHE_LATO
        if sx >= minimo and dx >= minimo:
            migliori.append((min(sx, dx), -abs(x - centro), x))
    return max(migliori)[2] if migliori else None


def confine_ammesso(righe: list[RigaFisica], colonne: list[Colonna]) -> float | None:
    """Il confine fisico del profilo: il varco di `confine_dei_lati`, se i due lati sono simmetrici
    (`lati_simmetrici`). Dice che la pagina e' fatta di due tabelle affiancate, non che siano sezioni contrapposte:
    quel verdetto lo da' il profilo (`Profilo.contrapposto`)."""
    x = confine_dei_lati(righe, colonne)
    return x if x is not None and lati_simmetrici(righe, colonne, x) else None


@dataclass(frozen=True)
class ConfiniPerPagina:
    confini: dict[int, float]       # pagina -> x del confine
    lati: dict[int, str]            # indice di colonna -> "L" | "R"
    gemelle: dict[int, int]         # indice di colonna -> indice della colonna di cui e' la gemella


# Due confini di pagina piu' vicini di cosi' sono lo stesso confine: il documento ne avrebbe uno solo.
_SCARTO_CONFINI = 5.0


def confini_per_pagina(righe: list[RigaFisica], colonne: list[Colonna]) -> ConfiniPerPagina | None:
    """Le sezioni contrapposte il cui confine si sposta da una pagina all'altra: un export da foglio di calcolo
    stampato in PDF (1714) mette l'importo di sinistra a una x sulle pagine dello stato patrimoniale e a un'altra su
    quelle del conto economico, e i codici di destra cominciano subito dopo. Nessun varco vale per tutto il
    documento, ma ogni pagina ha il suo.

    Su ogni pagina il confine si cerca fra le sole colonne con celle li' (`confine_dei_lati`, lati simmetrici). Si
    accetta solo se: ogni pagina con celle in due colonne ha il suo confine; i confini non sono tutti lo stesso (allora
    il documento ne avrebbe uno solo, e se non l'ha trovato non e' per la pagina); ogni colonna cade sempre sullo
    stesso lato. Una pagina con le celle di una colonna sola (i ricavi finiti, a destra solo «0») prende il confine
    della pagina piu' vicina, prima o dopo, che lascia ogni sua cella sul lato della sua colonna.

    Due colonne di valori dello stesso lato, con lo stesso ruolo e lo stesso periodo, che non hanno mai celle sulla
    stessa pagina sono una colonna sola stampata a due x: la seconda e' la gemella della prima, e le sue celle si
    leggono nella prima (altrimenti una sembrerebbe l'esercizio precedente dell'altra)."""
    per_pagina: dict[int, list[RigaFisica]] = {}
    for r in righe:
        per_pagina.setdefault(r.pagina, []).append(r)
    celle_pagina: dict[int, dict[int, int]] = {}
    for n, rr in per_pagina.items():
        conti: dict[int, int] = {}
        for r in rr:
            for p in _celle(r, colonne):
                if leggi_importo(p.testo).forma != "zero":
                    i = colonna_di(p.x1, colonne).indice
                    conti[i] = conti.get(i, 0) + 1
        celle_pagina[n] = {i: k for i, k in conti.items() if k >= _MIN_RIGHE_PAGINA}
    per_indice = {c.indice: c for c in colonne}

    confini: dict[int, float] = {}
    for n, usate in celle_pagina.items():
        if len(usate) < 2:
            continue
        sue = [per_indice[i] for i in sorted(usate)]
        x = confine_dei_lati(per_pagina[n], sue)
        if x is None or not lati_simmetrici(per_pagina[n], sue, x):
            return None
        confini[n] = x
    if len(confini) < 2 or max(confini.values()) - min(confini.values()) <= _SCARTO_CONFINI:
        return None
    lati: dict[int, str] = {}
    for n, x in confini.items():
        for i in celle_pagina[n]:
            lato = "L" if per_indice[i].x_destra < x else "R"
            if lati.setdefault(i, lato) != lato:
                return None
    for n, usate in celle_pagina.items():
        if n in confini or not usate:
            continue
        vicine = sorted(confini, key=lambda m: (abs(m - n), m > n))
        x = next((confini[m] for m in vicine if all(
            i in lati and ("L" if per_indice[i].x_destra < confini[m] else "R") == lati[i] for i in usate)), None)
        if x is None:
            return None
        confini[n] = x
    if any(n not in confini for n, usate in celle_pagina.items() if usate):
        return None
    return ConfiniPerPagina(confini, lati, _gemelle(colonne, lati, celle_pagina))


def _gemelle(colonne: list[Colonna], lati: dict[int, str], celle_pagina: dict[int, dict[int, int]]
             ) -> dict[int, int]:
    """Gemella -> colonna (vedi `confini_per_pagina`): a ogni lato la colonna di valori con piu' celle tiene il
    proprio indice, e ogni altra dello stesso ruolo e periodo, mai sulla stessa pagina di una gia' tenuta, ne diventa
    la gemella."""
    pagine: dict[int, set[int]] = {}
    for n, usate in celle_pagina.items():
        for i in usate:
            pagine.setdefault(i, set()).add(n)
    totali = {i: sum(u.get(i, 0) for u in celle_pagina.values()) for i in pagine}
    out: dict[int, int] = {}
    for lato in ("L", "R"):
        valori = sorted((c for c in colonne if lati.get(c.indice) == lato and c.indice in pagine
                         and c.ruolo in _GRUPPO_RUOLO and _GRUPPO_RUOLO[c.ruolo] == "valori"),
                        key=lambda c: (-totali[c.indice], c.x_destra))
        tenute: list[tuple[Colonna, set[int]]] = []
        for c in valori:
            gemella_di = next((t for t, viste in tenute if t.ruolo == c.ruolo and (t.fine, t.mesi) == (c.fine, c.mesi)
                               and not viste & pagine[c.indice]), None)
            if gemella_di is None:
                tenute.append((c, set(pagine[c.indice])))
                continue
            out[c.indice] = gemella_di.indice
            next(v for t, v in tenute if t is gemella_di).update(pagine[c.indice])
    return out


def lati_simmetrici(righe: list[RigaFisica], colonne: list[Colonna], confine: float) -> bool:
    """Le sezioni contrapposte ripetono la stessa tabella sui due lati: tante colonne di valori a sinistra quante
    a destra, e dare/avere, differenza o percentuale su entrambi o su nessuno. Un lato con colonne che l'altro
    non ha e' una tabella unica, con le descrizioni corte di una colonna in mezzo (budget_594, 680, 1566).

    Si confronta pagina per pagina, sulle colonne che coprono la pagina (`_QUOTA_RIGHE_PAGINA`), e i lati sono
    simmetrici se le pagine simmetriche sono piu' di quelle che non lo sono: una colonna minore su una pagina (la
    colonna dei mastri sotto i ricavi di budget_588 p. 4, una tabella in coda) non rompe la simmetria."""
    per_pagina: dict[int, list] = {}
    for r in righe:
        usate = {c.indice: c for p in r.parole
                 if p.x0 > _X0_MINIMO and (i := leggi_importo(p.testo)) is not None and i.forma != "zero"
                 and (c := colonna_di(p.x1, colonne)) is not None}
        pagina = per_pagina.setdefault(r.pagina, [[0, {}], [0, {}]])
        for k, sinistra in enumerate((True, False)):
            lato = [c for c in usate.values() if (c.x_destra < confine) == sinistra]
            if lato:
                pagina[k][0] += 1
                for c in lato:
                    pagina[k][1][c.indice] = pagina[k][1].get(c.indice, 0) + 1
    simmetriche = asimmetriche = 0
    per_indice = {c.indice: c for c in colonne}
    for lati in per_pagina.values():
        if min(n for n, _ in lati) < _MIN_RIGHE_PAGINA:
            continue
        gruppi = []
        for n, conteggi in lati:
            g: dict[str, int] = {}
            for i, k in conteggi.items():
                if k >= _QUOTA_RIGHE_PAGINA * n and (ruolo := _GRUPPO_RUOLO.get(per_indice[i].ruolo)) is not None:
                    g[ruolo] = g.get(ruolo, 0) + 1
            gruppi.append(g)
        if gruppi[0].get("valori") and gruppi[0] == gruppi[1]:
            simmetriche += 1
        else:
            asimmetriche += 1
    return simmetriche > asimmetriche


def assegna_lati(colonne: list[Colonna], confine: float | None,
                 lati: dict[int, str] | None = None) -> list[Colonna]:
    """Lato "L" a sinistra del confine, "R" a destra; tutte "U" senza confine. Modifica le colonne e
    restituisce la stessa lista. `lati` (indice -> lato) vale al posto del confine dove il confine cambia da una
    pagina all'altra (`confini_per_pagina`).

    Con un confine la colonna corrente si sceglie per lato, con la regola di `colonne._corrente`: sulle
    contrapposte la stessa data sta sopra entrambi i lati, e scelta sul documento non ne vincerebbe nessuna.
    Senza confine resta quella del documento."""
    for c in colonne:
        c.lato = "U" if confine is None else (
            (lati or {}).get(c.indice) or ("L" if c.x_destra < confine else "R"))
    if confine is not None:
        for c in colonne:
            c.corrente = False
        for lato in ("L", "R"):
            _corrente([c for c in colonne if c.lato == lato])
    return colonne


def _celle(r: RigaFisica, colonne: list[Colonna]) -> list[Parola]:
    """Le parole della riga che sono importi in una colonna. Una riga le cui sole «celle» sono trattini non e' una
    riga con importi: il trattino di un'intestazione di pagina («N10010 - RAGIONE SOCIALE», budget_1645) caduto
    sotto una colonna faceva contare l'intestazione fra le righe con importi, e le sue parole, larghe quanto la
    pagina, chiudevano il varco fra i lati."""
    celle = [p for p in r.parole
             if p.x0 > _X0_MINIMO and leggi_importo(p.testo) is not None
             and colonna_di(p.x1, colonne) is not None]
    return celle if any(leggi_importo(p.testo).forma != "zero" for p in celle) else []


def _centro(parole: list[Parola]) -> float:
    """Centro del contenuto, robusto a intestazioni e piedi lontani (5°/95° percentile)."""
    xs = sorted((p.x0 + p.x1) / 2 for p in parole)
    if not xs:
        return 0.0
    return (xs[int(0.05 * len(xs))] + xs[min(len(xs) - 1, int(0.95 * len(xs)))]) / 2


_STACCO_MARCATORE = 12.0      # come `profilo._STACCO_MARCATORE`


def _varco(dati: list[tuple[RigaFisica, list[Parola]]], a: Colonna, b: Colonna) -> float | None:
    """Il primo varco a destra della colonna `a` che nessuna parola di una riga con importi attraversa,
    prima che finisca la colonna `b`; il centro del varco, o None."""
    # il marcatore D/A staccato subito dopo un importo della colonna `a` ne fa parte: non chiude il varco (R23)
    coperti = sorted((p.x0, p.x1) for r, _ in dati for p in r.parole
                     if p.testo.strip() and p.x1 > a.x_destra and p.x0 < b.x_destra
                     and not (p.testo in _MARCATORI and p.x0 - a.x_destra <= _STACCO_MARCATORE))
    cursore = a.x_destra
    for x0, x1 in coperti:
        if x0 > cursore + _VARCO_MIN:
            return (cursore + x0) / 2
        cursore = max(cursore, x1)
    return None


def _sfora(r: RigaFisica, zona: float, x: float) -> bool:
    """Una parola che non e' un importo occupa la zona degli importi di sinistra, fra `zona` e il varco."""
    return any(p.x1 > zona and p.x0 < x and leggi_importo(p.testo) is None and p.testo.strip()
               and p.testo not in _MARCATORI for p in r.parole)


def _descritta(r: RigaFisica, celle: list[Parola], lo: float, hi: float) -> bool:
    """La riga ha, fra lo e hi, un importo in colonna e una descrizione (una parola con lettere, non il marcatore
    D/A di un importo) alla sua sinistra."""
    importi = [p for p in celle if lo < p.x0 and p.x1 < hi]
    if not importi:
        return False
    primo = min(p.x0 for p in importi)
    return any(lo < p.x0 and p.x1 <= primo and any(ch.isalpha() for ch in p.testo)
               and leggi_importo(p.testo) is None and p.testo not in _MARCATORI for p in r.parole)


def _piega(testo: str) -> str:
    senza = unicodedata.normalize("NFKD", testo.casefold())
    return "".join(ch for ch in senza if ch.isalpha())


def _confermato(righe: list[RigaFisica], colonne: list[Colonna], x: float) -> bool:
    """Una riga senza importi in colonna porta la parola del lato sinistro prima di x e quella del destro dopo, in
    qualunque maiuscolo e con o senza accento («Conto attivo … Conto passivo» su una riga di conti non
    e' un'intestazione), e sta sopra righe con importi della sua stessa pagina: l'intestazione dei lati che
    descrive."""
    con_importi: dict[int, float] = {}
    for r in righe:
        if _celle(r, colonne):
            con_importi[r.pagina] = max(con_importi.get(r.pagina, r.y), r.y)
    for r in righe:
        if _celle(r, colonne) or con_importi.get(r.pagina, -1.0) <= r.y:
            continue
        parole = [(p, _piega(p.testo)) for p in r.parole]
        for sinistre, destre in _COPPIE_TESTATA:
            if any(p.x1 < x and n.startswith(sinistre) for p, n in parole) and \
                    any(p.x0 > x and n.startswith(destre) for p, n in parole):
                return True
    return False
