"""Righe di un elenco di conti: saldo, segno, totali esclusi perche' somma di righe vicine.

La struttura fisica delle righe viene dal lettore del repo (collect_source_rows: rotazione,
righe fisiche, sezioni contrapposte, colonne SAP). Qui si sceglie il saldo e si tolgono i
totali: il totale stampato decide, mai il prefisso del codice di conto.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal

_AMT = re.compile(r"^\(?-?(\d{1,3}(\.\d{3})+|\d+),\d{2}\)?-?$")
_MIGLIAIA = re.compile(r"^\(?-?\d{1,3}(\.\d{3})+\)?-?$")
_AMT_TESTO = re.compile(r"\s+\(?-?[\d.]+,\d{2}\)?-?(\s+[DA](?=\s|$))?")


@dataclass
class Riga:
    id: str
    pagina: int
    lato: str
    testo: str
    valore: Decimal | None
    sezione: str = ""
    mastro: str | None = None
    totale: bool = False
    percorso: str | None = None


def _dec(t: str) -> Decimal:
    negativo = t.startswith("-") or t.endswith("-") or t.startswith("(")
    v = Decimal(t.strip("()-").replace(".", "").replace(",", "."))
    return -v if negativo else v


def importi(testo: str) -> list[tuple[Decimal, str]]:
    toks = testo.replace("_", "").split()
    out = []
    for i, t in enumerate(toks):
        if _AMT.match(t) or _MIGLIAIA.match(t):
            dopo = toks[i + 1] if i + 1 < len(toks) else ""
            out.append((_dec(t), dopo if dopo in ("D", "A") else ""))
    return out


def etichetta(testo: str) -> str:
    return re.sub(r"\s+", " ", _AMT_TESTO.sub("", " " + testo.replace("_", ""))).strip()


def regola_colonna(ruoli: list[str]) -> dict:
    for ruolo in ("saldo_corrente", "saldo_finale"):
        if ruolo in ruoli:
            return {"n": len(ruoli), "k": ruoli.index(ruolo)}
    return {}


def saldo(riga, regola: dict) -> Decimal | None:
    vs = importi(riga.text)
    if not vs:
        return None
    if not regola:
        v, m = vs[-1]
    elif len(vs) == regola["n"]:
        v, m = vs[regola["k"]]
    elif regola["k"] == regola["n"] - 1:
        v, m = vs[-1]
    elif regola["k"] == 0:
        v, m = vs[0]
    else:
        return None
    v = -abs(v) if m == "A" else v
    return v.quantize(Decimal("0.01"))


def _per_lato(righe: list[Riga]) -> dict[str, list[Riga]]:
    per_lato: dict[str, list[Riga]] = defaultdict(list)
    for r in righe:
        r.totale, r.mastro = False, None
        if r.valore is not None:
            per_lato[r.lato].append(r)
    return per_lato


def _passata(per_lato: dict[str, list[Riga]], direzione: int, kmin: int) -> int:
    """Marca, in una sola direzione, i totali di almeno kmin figli. Ritorna quanti ne marca."""
    marcati = 0
    for seq in per_lato.values():
        cambiato = True
        while cambiato:
            cambiato = False
            vive = [r for r in seq if not r.totale]
            for i, r in enumerate(vive):
                if not r.valore:
                    continue
                s, j, membri = Decimal(0), i + direzione, []
                while 0 <= j < len(vive) and len(membri) < 80:
                    s += vive[j].valore
                    membri.append(vive[j])
                    if len(membri) >= kmin and s == r.valore:
                        r.totale = cambiato = True
                        marcati += 1
                        for m in membri:
                            m.mastro = m.mastro or r.testo
                        break
                    j += direzione
                if cambiato:
                    break
            if cambiato:
                continue
    return marcati


def _conta_forzata(righe: list[Riga], direzione: int) -> int:
    """Su una copia usa e getta: quante righe marcherebbe questa sola direzione, gruppi (k>=2)
    e catene (k=1) insieme. Serve solo a confrontare le due direzioni, mai a marcare davvero:
    una catena a due cifre uguali puo' comparire in entrambe le direzioni per coincidenza, ma
    conta comunque quanto un gruppo vero ai fini del confronto."""
    per_lato = _per_lato(deepcopy(righe))
    return _passata(per_lato, direzione, 2) + _passata(per_lato, direzione, 1)


def _voti_apprendimento(righe: list[Riga]) -> Counter:
    """Vota la direzione dai soli gruppi (k>=2), provando entrambe le direzioni riga per
    riga: usato solo per spareggiare quando le due passate forzate per intero marcano lo
    stesso numero di righe. Da solo puo' votare la direzione sbagliata quando un gruppo
    confina con l'altro (le prime righe del gruppo vicino sommano per caso al totale di
    questo) - per questo non decide mai da solo, se non a parita'."""
    per_lato = _per_lato(deepcopy(righe))
    voti: Counter = Counter()
    for seq in per_lato.values():
        cambiato = True
        while cambiato:
            cambiato = False
            vive = [r for r in seq if not r.totale]
            for i, r in enumerate(vive):
                if not r.valore:
                    continue
                for d in (1, -1):
                    s, j, membri = Decimal(0), i + d, []
                    while 0 <= j < len(vive) and len(membri) < 80:
                        s += vive[j].valore
                        membri.append(vive[j])
                        if len(membri) >= 2 and s == r.valore:
                            r.totale = cambiato = True
                            voti[d] += 1
                            for m in membri:
                                m.mastro = m.mastro or r.testo
                            break
                        j += d
                    if r.totale:
                        break
                if cambiato:
                    break
            if cambiato:
                continue
    return voti


def marca_totali(righe: list[Riga]) -> Counter:
    """Sceglie la direzione provando le due passate forzate per intero (gruppi e catene) e
    tenendo quella che marca piu' righe: l'apprendimento a coppie da solo vota anche la
    direzione sbagliata quando un gruppo confina con l'altro (le prime righe del gruppo
    vicino sommano per caso al totale di questo - senza un confine di gruppo il voto a coppie
    non lo vede). A parita' decide l'apprendimento a coppie; se anche quello e' muto, -1
    (totale dopo i figli). Le catene di un solo figlio (k=1) contano solo se la direzione
    scelta ha trovato almeno un totale vero (k>=2) nel documento: senza un gruppo reale, due
    importi uguali in fila sono spesso una coincidenza, non un mastro (80,80 non e' il totale
    di 50)."""
    piu, meno = _conta_forzata(righe, 1), _conta_forzata(righe, -1)
    if piu != meno:
        direzione = 1 if piu > meno else -1
    else:
        voti = _voti_apprendimento(righe)
        direzione = voti.most_common(1)[0][0] if voti else -1

    per_lato = _per_lato(righe)
    trovati = _passata(per_lato, direzione, 2)
    if trovati:
        _passata(per_lato, direzione, 1)
    return Counter({direzione: trovati}) if trovati else Counter()


def righe_da_pdf(file_path: str, pagine: set[int] | None, ruoli: list[str],
                 ocr_text: str | None = None) -> list[Riga]:
    from importers.detail_enrichment import collect_source_rows
    regola = regola_colonna(ruoli)
    out = []
    for r in collect_source_rows(file_path, ocr_text=ocr_text):
        if pagine and r.page not in pagine:
            continue
        out.append(Riga(id=r.id, pagina=r.page, lato=r.side, testo=etichetta(r.text),
                        valore=saldo(r, regola), sezione=r.statement))
    marca_totali(out)
    return out


def foglie(righe: list[Riga]) -> list[Riga]:
    return [r for r in righe if r.valore is not None and not r.totale and r.testo]
