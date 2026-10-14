"""Situazione contabile a sezioni contrapposte letta dalle tabelle di MinerU, senza modello.

Una scansione non ha geometria di testo: il lettore delle contrapposte
(``situazione_contabile_parser.extract_situazione_contabile``) non vede nulla, e il pass
CoGe su Qwen legge il testo OCR in minuti e sbaglia (Unicarton 31/08/2026: 8,5 minuti,
315 mila di sbilancio). MinerU invece restituisce le tabelle già divise in celle —
conto, descrizione, importo per lato — con gli importi esatti.

Qui quelle celle si stampano su un PDF sintetico con la forma di un bilancio di verifica
(titolo, intestazioni ATTIVITA'/PASSIVITA' o COSTI/RICAVI, due colonne, i totali e le
righe di piede sotto), e lo si fa leggere al lettore di sempre: netting dei fondi,
gerarchie dei conti, totali di controllo, eccedenza dell'anno prima valgono uguali, una
regola sola. Nessun importo nasce qui: ogni cifra è una cella di MinerU, al suo posto.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

_IMPORTO = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}-?")
_CODICE = re.compile(r"^\d{1,3}(?:[./]\d{1,4})*$")
# un importo spezzato fra due celle o da uno spazio: "1.440.337" + ",23"
_VIRGOLA_STACCATA = re.compile(r"(\d)\s*\|?\s*,(\d{2})(?!\d)")
_PAROLA_TOTALE = re.compile(r"(?i)\b(totale|eccedenza|utile|perdita|risultato|differenza)")

_LARGHEZZA = 595.0
_PASSO = 11.0
_CORPO = 7.0


def _sezione(table) -> Optional[str]:
    titolo = (table.caption or "").upper()
    if "PATRIMONIAL" in titolo:
        return "sp"
    if "ECONOMIC" in titolo:
        return "ce"
    return None


def _testo(cella) -> str:
    return (cella.text or "").strip()


def _riga_conti(celle: list[str]):
    """(sinistra, destra) di una riga a sei celle; ciascun lato (codice, descrizione,
    importo) o None. Le righe d'intestazione non hanno importi e tornano (None, None)."""
    celle = celle + [""] * (6 - len(celle))

    def lato(c, d, a):
        if not _IMPORTO.fullmatch(a.replace(" ", "")):
            return None
        if c and not _CODICE.match(c):
            return None
        return c, d, a.replace(" ", "")

    return lato(*celle[0:3]), lato(*celle[3:6])


def _coppie_di_piede(celle: list[str]) -> list[tuple[str, str]]:
    """Le coppie (didascalia, importo) di una riga di piede, nell'ordine di stampa.
    Un importo senza didascalia ripete quella prima ("Totale a quadratura X | X")."""
    testo = " | ".join(c for c in celle if c)
    testo = _VIRGOLA_STACCATA.sub(r"\1,\2", testo)
    coppie, ultima, pos = [], "", 0
    for m in _IMPORTO.finditer(testo):
        didascalia = testo[pos:m.start()].strip(" |:_-")
        if didascalia:
            ultima = didascalia
        coppie.append((didascalia or ultima, m.group(0)))
        pos = m.end()
    return coppie


def _lato_del_piede(sezione: str, didascalia: str, indice: int, quante: int) -> str:
    """Due coppie sulla stessa riga: la prima a sinistra, la seconda a destra. Una sola:
    decide la didascalia — passività, ricavi ed eccedenze (utile) stanno a destra nello
    stato patrimoniale, una perdita a sinistra; nel conto economico il risultato sta dalla
    parte dei costi."""
    if quante >= 2:
        return "L" if indice == 0 else "R"
    d = didascalia.upper()
    if "PASSIV" in d or "RICAV" in d:
        return "R"
    if "ATTIV" in d or "COST" in d:
        return "L"
    if sezione == "sp":
        return "L" if "PERDIT" in d else "R"
    return "L"


def _righe(tables) -> dict[str, list]:
    """Per sezione, la lista ordinata di righe da stampare: ("conto", L, R) oppure
    ("piede", lato, didascalia, importo)."""
    out: dict[str, list] = {"sp": [], "ce": []}
    for table in tables:
        sezione = _sezione(table)
        if sezione is None:
            continue
        for row in table.rows:
            celle = [_testo(c) for c in row.cells]
            if not any(celle):
                continue
            unite = " ".join(celle)
            sinistra, destra = _riga_conti(celle) if len(celle) >= 6 else (None, None)
            if sinistra or destra:
                out[sezione].append(("conto", sinistra, destra))
                continue
            if not _PAROLA_TOTALE.search(unite):
                continue
            coppie = _coppie_di_piede(celle)
            for i, (didascalia, importo) in enumerate(coppie):
                lato = _lato_del_piede(sezione, didascalia, i, len(coppie))
                out[sezione].append(("piede", lato, didascalia, importo))
    return out


def _stampa_pagina(doc, titolo: str, sinistra: str, destra: str, righe: list) -> None:
    import fitz

    altezza = 120 + _PASSO * (len(righe) + 2)
    page = doc.new_page(width=_LARGHEZZA, height=max(842.0, altezza))
    page.insert_text((20, 30), "BILANCIO DI VERIFICA", fontsize=9)
    page.insert_text((230, 50), titolo, fontsize=9)
    page.insert_text((60, 75), sinistra, fontsize=8)
    page.insert_text((360, 75), destra, fontsize=8)
    font = fitz.Font("helv")

    def importo(x_fine, y, testo):
        page.insert_text((x_fine - font.text_length(testo, fontsize=_CORPO), y), testo,
                         fontsize=_CORPO)

    def conto(x, y, lato):
        codice, descrizione, valore = lato
        if codice:
            page.insert_text((x, y), codice, fontsize=_CORPO)
        page.insert_text((x + 42, y), descrizione[:38], fontsize=_CORPO)
        importo(x + 270, y, valore)

    y = 95.0
    for _, sx, dx in righe:      # solo righe "conto": il piede l'ha gia' convertito _accoppia_piede
        if sx:
            conto(20, y, sx)
        if dx:
            conto(305, y, dx)
        y += _PASSO


def _accoppia_piede(righe: list) -> list:
    """Le coppie di piede consecutive L poi R della stessa riga d'origine si stampano
    sulla stessa altezza, come nel documento."""
    out, i = [], 0
    while i < len(righe):
        r = righe[i]
        if (r[0] == "piede" and r[1] == "L" and i + 1 < len(righe)
                and righe[i + 1][0] == "piede" and righe[i + 1][1] == "R"):
            out.append(("conto", ("", r[2], r[3]), ("", righe[i + 1][2], righe[i + 1][3])))
            i += 2
            continue
        if r[0] == "piede":
            lato = ("", r[2], r[3])
            out.append(("conto", lato, None) if r[1] == "L" else ("conto", None, lato))
        else:
            out.append(r)
        i += 1
    return out


def pdf_da_tabelle(context) -> Optional[str]:
    """Il PDF sintetico di una situazione contabile a sezioni contrapposte, o None quando
    le tabelle di MinerU non hanno quella forma (servono stato patrimoniale e conto
    economico, ciascuno con righe di conti su due lati). Il chiamante cancella il file."""
    import fitz

    righe = _righe(getattr(context, "tables", ()) or ())
    conti = {s: sum(1 for r in righe[s] if r[0] == "conto") for s in righe}
    if conti["sp"] < 4 or conti["ce"] < 2:
        return None
    doc = fitz.open()
    _stampa_pagina(doc, "STATO PATRIMONIALE", "ATTIVITA'", "PASSIVITA'",
                   _accoppia_piede(righe["sp"]))
    _stampa_pagina(doc, "CONTO ECONOMICO", "COSTI", "RICAVI", _accoppia_piede(righe["ce"]))
    fd, percorso = tempfile.mkstemp(suffix=".pdf", prefix="mineru-contrapposte-")
    os.close(fd)
    doc.save(percorso)
    doc.close()
    logger.info("MinerU contrapposte: %d righe SP, %d righe CE su PDF sintetico",
                conti["sp"], conti["ce"])
    return percorso
