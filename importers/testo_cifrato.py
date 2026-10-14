"""Testo di un PDF cifrato da un font senza mappa Unicode.

Una scansione con OCR ripassata da Ghostscript (PDF24 Creator, tipicamente) può
perdere la ``ToUnicode`` del font Type0/Identity-H: il testo resta selezionabile,
ma ogni carattere esce come indice di glifo, cioè spostato di una costante
(29 su Times/Arial TrueType, dove lo spazio è il glifo 3). «Unicarton Srl» diventa
«8QLFDUWRQ 6UO», il classificatore non riconosce nulla e l'import esce con
«nessuno scheletro di legge né elenco conti riconoscibile» (upload 1269-1279,
ottobre 2026).

Lo spostamento si misura, non si suppone: si sceglie quello che fa comparire le
parole di un bilancio dove prima non ce n'era nessuna. Riconosciuto, si scrive
una copia del PDF con lo stesso testo decodificato, invisibile, carattere per
carattere nella posizione originale — immagini e grafica intatte — e tutto
l'import legge la copia. Nessun importo nasce qui: è lo stesso testo, letto con
la mappa giusta, e l'import lo dichiara.
"""
from __future__ import annotations

import logging
import os
import re
import tempfile
from typing import NamedTuple, Optional

logger = logging.getLogger(__name__)

_PAROLE = (
    "bilancio", "totale", "attivo", "passivo", "attivit", "passivit", "debiti",
    "crediti", "capitale", "riserva", "fondo", "ricavi", "costi", "conto",
    "patrimoniale", "economico", "descrizione", "importo", "banca", "fornitori",
)
_PAROLA_RE = re.compile("|".join(_PAROLE))
_SPOSTAMENTI = range(1, 64)
_MIN_PAROLE = 5


class TestoCifrato(NamedTuple):
    spostamento: int
    parole_prima: int
    parole_dopo: int


def _decodifica(testo: str, spostamento: int) -> str:
    # Spazio e a capo non sono cifrati (lo spazio ha la sua mappa, l'a capo lo mette
    # PyMuPDF). Ogni altro carattere si sposta solo se ricade nell'ASCII stampabile:
    # i glifi accentati non sono contigui all'alfabeto, e restano come sono.
    # Attenzione: str.isspace() vale anche per \x1c-\x1f, che qui sono le cifre 9..<.
    return "".join(
        c if c in " \n" or not 0x20 < ord(c) + spostamento < 0x7F else chr(ord(c) + spostamento)
        for c in testo
    )


def _conta_parole(testo: str) -> int:
    return len(_PAROLA_RE.findall(testo.lower()))


def rileva(testo: str) -> Optional[TestoCifrato]:
    """Lo spostamento che rende leggibile ``testo``, o None se è già leggibile."""
    prima = _conta_parole(testo)
    if prima >= _MIN_PAROLE:
        return None
    migliore = None
    for k in _SPOSTAMENTI:
        dopo = _conta_parole(_decodifica(testo, k))
        if dopo >= _MIN_PAROLE and dopo > 3 * max(prima, 1) and (
            migliore is None or dopo > migliore.parole_dopo
        ):
            migliore = TestoCifrato(k, prima, dopo)
    return migliore


def ripara(file_path: str, max_pagine: int = 14) -> Optional[tuple[str, TestoCifrato]]:
    """Una copia di ``file_path`` col testo decodificato, o None se non serve.

    Il chiamante cancella la copia quando ha finito.
    """
    import fitz

    with fitz.open(file_path) as doc:
        campione = "".join(p.get_text() for p in doc[:max_pagine])
        esito = rileva(campione)
        if esito is None:
            return None
        k = esito.spostamento
        font = fitz.Font("helv")
        for page in doc:
            raw = page.get_text("rawdict")
            caratteri = []
            for blocco in raw.get("blocks", ()):
                for riga in blocco.get("lines", ()):
                    for span in riga.get("spans", ()):
                        for ch in span.get("chars", ()):
                            c = ch["c"]
                            # Gli spazi non si copiano: parte li ha inventati MuPDF
                            # dalle larghezze dei glifi cifrati, e nella copia li
                            # ricava di nuovo dalle posizioni vere.
                            if c == " ":
                                continue
                            caratteri.append((ch["origin"], _decodifica(c, k), span["size"]))
            # Toglie il solo testo: immagini e grafica restano come sono.
            page.add_redact_annot(page.rect)
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            if not caratteri:
                continue
            tw = fitz.TextWriter(page.rect)
            for origine, c, size in caratteri:
                tw.append(origine, c, font=font, fontsize=size)
            tw.write_text(page, render_mode=3)
        fd, copia = tempfile.mkstemp(suffix=".pdf", prefix="testo-decodificato-")
        os.close(fd)
        doc.save(copia, garbage=3, deflate=True)
    logger.info(
        "Testo PDF cifrato (spostamento %d, parole riconosciute %d -> %d): letta una copia decodificata",
        k, esito.parole_prima, esito.parole_dopo,
    )
    return copia, esito


def avviso(esito: TestoCifrato) -> str:
    return (
        "Il testo del PDF era illeggibile: il font non portava la mappa dei caratteri "
        "(capita ai PDF ripassati da PDF24 o Ghostscript), e ogni lettera era spostata "
        f"di {esito.spostamento} posizioni. L'import ha letto il testo decodificato: "
        "controlla gli importi in Rettifiche."
    )
