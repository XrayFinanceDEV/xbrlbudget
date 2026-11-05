"""Parser unico degli importi: un token stampato diventa un Decimal con la sua forma."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

# migliaia a gruppi di 3 (o nessun separatore se ci sono i decimali), virgola e 1-3 decimali
_FORMA = re.compile(r"^(?P<int>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<dec>\d{1,3}))?$")
_MARCATORE = re.compile(r"\s+([DA])$")
_RIMANDO = re.compile(r"\s*\(\d{1,2}\)$")


@dataclass(frozen=True)
class Importo:
    valore: Decimal
    forma: str  # "importo" | "percentuale" | "zero" (cella "-")
    testo: str  # il token come stampato
    marcatore: str | None = None   # "D" | "A" stampato con l'importo: il segno lo da' il lato (`segno_del_lato`)


# R23: il segno di un marcatore D/A dipende dal lato, perche' la colonna e' la verita' sul lato (CLAUDE.md). Sul lato
# sinistro delle contrapposte (attivo, costi) e su una sezione unica vale il saldo in dare: D positivo, A negativo; sul
# lato destro (passivo, ricavi) A positivo, D negativo.
MARCATORE_NEGATIVO = {"U": "A", "L": "A", "R": "D"}


def segno_del_lato(imp: Importo, lato: str) -> Importo:
    """L'importo col segno del suo marcatore sul lato della riga; senza marcatore, l'importo com'e'."""
    if imp.marcatore is None or imp.marcatore != MARCATORE_NEGATIVO.get(lato, "A"):
        return imp
    return Importo(-imp.valore, imp.forma, imp.testo, imp.marcatore)


def leggi_importo(token: str) -> Importo | None:
    t = token.replace("_", "").replace("€", "").strip().rstrip("*").strip()
    if t == "-":
        return Importo(Decimal("0"), "zero", token)
    t = _RIMANDO.sub("", t)
    negativo = False
    marcatore = None
    m = _MARCATORE.search(t)
    if m:
        # neutro: il segno del marcatore lo decide il lato della riga (R23, `segno_del_lato`)
        marcatore = m.group(1)
        t = t[: m.start()]
    # la parentesi e' un segno solo se si chiude: "(5.367,37" e' una nota (budget_1450)
    if t.startswith("(") and t.endswith(")"):
        negativo, t = True, t[1:-1]
    elif t.startswith("("):
        t = t[1:]
    if t.startswith("-"):
        negativo, t = True, t[1:]
    elif t.endswith("-"):
        negativo, t = True, t[:-1]
    m = _FORMA.match(t)
    if not m:
        return None
    intero, dec = m.group("int"), m.group("dec")
    # senza separatori un intero e' un anno, un codice, un conteggio: non un importo
    if dec is None and "." not in intero:
        return None
    v = Decimal(intero.replace(".", "") + ("." + dec if dec else ""))
    forma = "percentuale" if dec and len(dec) == 3 else "importo"
    return Importo(-v if negativo else v, forma, token, marcatore)
