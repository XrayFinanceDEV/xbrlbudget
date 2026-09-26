"""Righe di un elenco di conti: saldo, segno, totali esclusi perche' somma di righe vicine.

La struttura fisica delle righe viene dal lettore del repo (collect_source_rows: rotazione,
righe fisiche, sezioni contrapposte, colonne SAP). Qui si sceglie il saldo e si tolgono i
totali: il totale stampato decide, mai il prefisso del codice di conto.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
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


def _marca(righe: list[Riga], forzata: int | None) -> Counter:
    per_lato = defaultdict(list)
    for r in righe:
        r.totale, r.mastro = False, None
        if r.valore is not None:
            per_lato[r.lato].append(r)
    direzioni: Counter = Counter()
    for kmin in (2, 1):
        if forzata is not None:
            consentite = (forzata,)
        elif kmin == 2 or not direzioni:
            consentite = (1, -1)
        else:
            consentite = (direzioni.most_common(1)[0][0],)
        cambiato = True
        while cambiato:
            cambiato = False
            for seq in per_lato.values():
                vive = [r for r in seq if not r.totale]
                for i, r in enumerate(vive):
                    if not r.valore:
                        continue
                    for d in consentite:
                        s, j, membri = Decimal(0), i + d, []
                        while 0 <= j < len(vive) and len(membri) < 80:
                            s += vive[j].valore
                            membri.append(vive[j])
                            if len(membri) >= kmin and s == r.valore:
                                r.totale = cambiato = True
                                if kmin == 2 and forzata is None:
                                    direzioni[d] += 1
                                for m in membri:
                                    m.mastro = m.mastro or r.testo
                                break
                            j += d
                        if r.totale:
                            break
                    if cambiato:
                        break
                if cambiato:
                    break
    return direzioni


def marca_totali(righe: list[Riga]) -> Counter:
    """Prima impara la direzione dei totali (prima o dopo i figli) dai gruppi di almeno due
    righe, poi ricalcola tutto con quella sola direzione: una sequenza all'indietro che
    somma per caso (un bene e il suo fondo si annullano) non marca piu' un conto vero."""
    direzioni = _marca(righe, None)
    if direzioni:
        _marca(righe, direzioni.most_common(1)[0][0])
    return direzioni


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
