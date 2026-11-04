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


def leggi_importo(token: str) -> Importo | None:
    t = token.replace("_", "").replace("€", "").strip().rstrip("*").strip()
    if t == "-":
        return Importo(Decimal("0"), "zero", token)
    t = _RIMANDO.sub("", t)
    negativo = False
    m = _MARCATORE.search(t)
    if m:
        negativo = m.group(1) == "A"
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
    return Importo(-v if negativo else v, forma, token)
