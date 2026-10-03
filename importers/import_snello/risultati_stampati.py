"""Il risultato d'esercizio che il documento stampa due volte (Task 27, decisione 3, 2026-10-03):
nello Stato Patrimoniale («IX - Utile (perdita) dell'esercizio») e nel Conto Economico
(«21)/23) Utile (perdita) dell'esercizio»). Lettura deterministica dalle righe fisiche del
documento, mai un importo riportato dal modello: serve a dichiarare un documento che si
contraddice da solo (budget_161, 672), non a correggerlo."""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

# «utile (perdita) dell'esercizio», «utile (perdite) d'esercizio», «utile/perdita del periodo».
# Solo la forma con entrambi i termini: «perdita d'esercizio» da sola non dice il segno
# dell'importo stampato, e un importo di segno incerto non ancora nulla.
_ETICHETTA = re.compile(
    r"utile\s*(?:\(\s*perdit[ae]\s*\)|/\s*perdit[ae])\s*(?:del(?:l)?\s*['’`]?\s*)?(?:esercizio|periodo)\b")
_NON_RISULTATO = re.compile(r"\b(?:prima|ante)\b|\bimposte\b|\bportat[io]\b|\bprecedent")


def _norm(testo: str) -> str:
    t = unicodedata.normalize("NFKD", testo.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


_NUMERO = re.compile(r"\(?-?\d{1,3}(?:\.\d{3})+(?:,\d+)?\)?|\(?-?\d+(?:,\d+)?\)?")


def _numeri_dopo(testo: str, fine_etichetta: int) -> list[Decimal]:
    """I soli importi che seguono l'etichetta: un codice stampato PRIMA (``2086 A.IX) Utile...``,
    ``AB010100``) non e' mai una colonna."""
    out = []
    for tok in _NUMERO.findall(testo[fine_etichetta:]):
        neg = tok.startswith("(") or tok.startswith("-") or tok.startswith("(-")
        n = Decimal(tok.strip("()-").replace(".", "").replace(",", "."))
        out.append(-n if neg else n)
    return out


def _valore_corrente(righe, statement: str) -> Decimal | None:
    """L'importo della colonna corrente della riga di risultato del prospetto ``statement``.
    La colonna corrente e' la prima, ed e' certa solo se la riga ne stampa almeno due (corrente e
    comparativo): su una riga con un importo solo non si sa quale anno sia. Piu' righe di
    risultato nello stesso prospetto devono concordare, altrimenti nulla."""
    valori = []
    for r in righe:
        if getattr(r, "statement", "") != statement:
            continue
        t = _norm(r.text)
        e = _ETICHETTA.search(t)
        if not e or _NON_RISULTATO.search(t):
            continue
        numeri = _numeri_dopo(t, e.end())
        if len(numeri) < 2:
            return None
        valori.append(numeri[0])
    if not valori or any(v != valori[0] for v in valori):
        return None
    return valori[0]


def risultati_stampati(righe) -> dict | None:
    """``{"sp": Decimal, "ce": Decimal}`` quando il documento stampa il risultato in ENTRAMBI i
    prospetti e la riga e' leggibile con certezza; altrimenti None («non lo so», mai un verdetto)."""
    sp = _valore_corrente(righe, "bs")
    ce = _valore_corrente(righe, "ce")
    if sp is None or ce is None:
        return None
    return {"sp": sp, "ce": ce}
