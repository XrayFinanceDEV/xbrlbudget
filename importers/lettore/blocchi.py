"""Blocchi che non chiudono (Fase 2, Task 2): i totali stampati i cui figli non sommano, colonna per colonna.

Un blocco nasce solo da un totale stampato davvero: una riga di controllo (C12) o una voce che `marca_totali` ha
chiuso su un'altra colonna. Una voce con i figli dichiarati solo dall'intestazione (padre non verificato, nessuna
somma stampata che chiuda) non e' un blocco. Si legge e si dichiara, non si corregge: `blocchi_aperti` non modifica
il documento. La ricerca dei figli e le regole di somma (C6, segni, righe di controllo) sono quelle di `totali.py`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from importers.lettore.profilo import _norm
from importers.lettore.righe import Documento, Riga
from importers.lettore.totali import (
    _RUOLI_VALORE, DICE_TOTALE, _Serie, _euro, _priorita, _risultato_di_controllo, _serie, _su_schema,
    _tolleranza_cella, _valore_nel_totale, valore_nel_totale)

_TETTO_ETICHETTE = 12
_NUMERO_RIGA = re.compile(r"r(\d+)")
_PAGINA_RIGA = re.compile(r"p(\d+)r")


@dataclass(frozen=True)
class Blocco:
    voce: str                 # etichetta stampata del totale
    codice: str               # "" se il totale non ha codice
    sezione: str              # "SP" | "CE" | ""
    lato: str                 # "U" | "L" | "R"
    colonna: int              # indice in Documento.colonne
    fine: date | None
    mesi: int | None
    corrente: bool
    stampato: Decimal         # importo del totale sulla sua colonna
    somma: Decimal            # somma dei figli candidati, con `valore_nel_totale`
    scarto: Decimal           # stampato - somma
    pagina: int
    righe: tuple[str, str]    # prima e ultima riga del tratto, totale compreso, in ordine di documento
    etichette: tuple[str, ...]   # le etichette dei figli candidati, al massimo 12
    cercato: bool             # True: riga di controllo non chiusa, tratto scelto per minimo scarto; False: figli noti


def _chiuso(t: Riga, colonna: int, coppie: dict[int, int]) -> bool:
    return colonna in t.figli or coppie.get(colonna, -1) in t.figli


def blocchi_aperti(doc: Documento) -> list[Blocco]:
    """I blocchi aperti del prospetto, dal piu' grande scarto in valore assoluto. Solo colonne esercizio o saldo."""
    coppie = getattr(doc.profilo, "coppie", {}) or {}
    parziali = set(coppie.values())
    colonne = {c.indice: c for c in doc.colonne if c.ruolo in _RUOLI_VALORE and c.indice not in parziali}
    per_id = {r.id: r for r in doc.righe}
    pos = {r.id: k for k, r in enumerate(doc.righe)}
    trovati: list[tuple[Blocco, int, int]] = []
    priorita = _priorita(doc)
    schema = _su_schema(doc)
    for serie in _serie(doc):
        colonna = colonne.get(serie.colonna)
        if colonna is None:
            continue
        # un tratto scelto per minimo scarto vale solo su uno schema di legge: su un elenco di conti inventerebbe divari
        aperti = _candidati(doc, serie, coppie) if _su_schema(doc) else {}
        for i, r in enumerate(serie.righe):
            if _chiuso(r, serie.colonna, coppie):
                continue
            verso = None
            if r.totale:
                figli, verso = _figli_altra_colonna(doc, r, serie.colonna, per_id, priorita)
            else:
                figli = aperti.get(i)
            if not figli or not any(serie.colonna in f.celle and f.celle[serie.colonna].valore for f in figli):
                continue        # nessun figlio con un importo: un totale vuoto o a zero non ha nulla da chiudere
            if verso is None:
                somma = sum((valore_nel_totale(doc, r, f, serie.colonna) for f in figli if serie.colonna in f.celle),
                            Decimal(0))
            else:   # come totali._confronta_colonne: il verso e' quello della colonna che chiude
                somma = sum((_valore_nel_totale(r, f, serie.colonna, verso, schema)
                             for f in figli if serie.colonna in f.celle), Decimal(0))
            stampato = r.celle[serie.colonna].valore
            scarto = stampato - somma
            if abs(scarto) <= _tolleranza_cella(doc, r, serie.colonna):
                continue
            tratto = sorted([*figli, r], key=lambda x: pos[x.id])
            trovati.append((Blocco(
                voce=r.etichetta, codice=r.codice, sezione=r.sezione, lato=r.lato, colonna=serie.colonna,
                fine=colonna.fine, mesi=colonna.mesi, corrente=colonna.corrente, stampato=stampato, somma=somma,
                scarto=scarto, pagina=r.pagina, righe=(tratto[0].id, tratto[-1].id),
                etichette=tuple(f.etichetta for f in sorted(figli, key=lambda x: pos[x.id]))[:_TETTO_ETICHETTE],
                cercato=not r.totale),
                pos[r.id], serie.colonna))
    trovati.sort(key=lambda b: (-abs(b[0].scarto), b[1], b[2]))
    return [b for b, _, _ in trovati]


def _figli_altra_colonna(doc: Documento, t: Riga, colonna: int, per_id: dict[str, Riga],
                         priorita: dict[int, int]) -> tuple[list[Riga], int]:
    """Un totale chiuso su un'altra colonna: gli stessi figli, scelti sulla colonna che chiude, e il verso di quella
    colonna. Come `totali._confronta_colonne`: riferimento con `_priorita` (la corrente prima), somma con il verso
    del riferimento, perche' `valore_nel_totale` su una colonna fuori da `t.figli` darebbe sempre +1."""
    riferimento = min(t.figli, key=priorita.get)
    return [per_id[f] for f in t.figli[riferimento] if colonna in per_id[f].celle], t.verso.get(riferimento, 1)


def _candidati(doc: Documento, serie: _Serie, coppie: dict[int, int]) -> dict[int, list[Riga]]:
    """Per ogni riga di controllo non chiusa della serie, i figli candidati. Si risale dalla riga fra le righe vive
    (un conto gia' figlio di un totale chiuso non lo e' piu'; un totale chiuso o aperto che sta in mezzo e' un
    membro col suo importo stampato, e i suoi figli si saltano). Il tratto finisce davanti a un totale chiuso
    (confine del gruppo) o piu' su, dopo uno o piu' totali chiusi (la riga somma allora i sottototali): fra questi
    pochi tagli si tiene quello che si avvicina di piu' all'importo stampato, a parita' il piu' corto.
    `marca_totali` ha gia' provato ogni tratto e nessuno chiude entro la tolleranza, quindi quello che resta e' la
    misura piu' onesta del divario."""
    colonna = serie.colonna
    schema = _su_schema(doc)
    morti = {f for t in doc.righe for f in t.figli.get(colonna, ())}
    inizio: dict[int, int] = {}
    out: dict[int, list[Riga]] = {}
    for i, r in enumerate(serie.righe):
        if not serie.controllo[i] or _chiuso(r, colonna, coppie) or r.totale:
            continue
        if r.etichetta and not DICE_TOTALE.search(_norm(r.etichetta)):
            continue
        stampato = r.celle[colonna].valore
        membri: list[Riga] = []
        indici: list[int] = []
        migliore: tuple[Decimal, int] | None = None
        somma = Decimal(0)

        def valuta() -> None:
            nonlocal migliore
            if any(m.celle[colonna].valore for m in membri) and (
                    migliore is None or abs(stampato - somma) < migliore[0]):
                migliore = (abs(stampato - somma), len(membri))

        j = i - 1
        while j >= 0:
            m = serie.righe[j]
            if m.id in morti:
                j -= 1
                continue
            if _chiuso(m, colonna, coppie):
                valuta()        # un totale chiuso e' o il confine del gruppo o un addendo di un livello sopra
            membri.append(m)
            indici.append(j)
            somma += valore_nel_totale(doc, r, m, colonna)
            j = inizio[j] - 1 if j in inizio else j - 1
        valuta()
        if migliore is not None and stampato and not _risultato_di_controllo(r, schema):
            out[i] = membri[:migliore[1]][::-1]
            inizio[i] = indici[migliore[1] - 1]
    return out


def frase_blocco(b: Blocco) -> str:
    """«B) II - Crediti (2025, p. 3, righe 12-27): stampato 1.234,56, i conti sommano 1.200,00, scarto 34,56»."""
    periodo = str(b.fine.year) if b.fine else f"colonna {b.colonna + 1}"
    a, z = (_NUMERO_RIGA.search(x) for x in b.righe)
    righe = f"righe {a.group(1)}-{z.group(1)}" if a and z else "righe"
    pa, pz = (_PAGINA_RIGA.match(x) for x in b.righe)
    pagine = f"pp. {pa.group(1)}-{pz.group(1)}" if pa and pz and pa.group(1) != pz.group(1) else f"p. {b.pagina}"
    return (f"{b.voce} ({periodo}, {pagine}, {righe}): stampato {_euro(b.stampato)}, "
            f"i conti sommano {_euro(b.somma)}, scarto {_euro(b.scarto)}")
