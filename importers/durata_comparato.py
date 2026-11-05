"""Quanti mesi copre la colonna dell'anno precedente di un bilancio infrannuale.

Un infrannuale si confronta con lo stesso periodo dell'anno prima (budget_1470 settembre su
settembre, budget_1540 e budget_1445 giugno su giugno) oppure con l'anno prima intero
(budget_638, budget_1524). Lo dice solo la data di chiusura stampata per quella colonna:
salvare il semestre come anno intero ne fa un anno base falso, e sostituisce in silenzio
l'anno intero gia' importato (le macro-voci quadrano, nessun controllo lo vede).

Si cercano nel testo di testa le date di fine mese dell'anno precedente (``30/06/2025``,
``31-12-2025``): una sola data di chiusura decide, due chiusure diverse o nessuna lasciano la
durata ignota. Le date d'inizio (``01/01/2025``) e quelle che non chiudono un mese (una
delibera, una stampa) non contano.
"""
from __future__ import annotations

import calendar
import re
from typing import Optional

_DATA = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](20\d{2})(?!\d)")
PAGINE_DI_TESTA = 3


def mesi_del_comparato(testo: str, fiscal_year: int) -> Optional[int]:
    """12 se la colonna precedente chiude il 31/12, i mesi da gennaio se chiude prima, None se
    il testo non stampa una sola data di chiusura dell'anno precedente."""
    anno = fiscal_year - 1
    chiusure = set()
    for g, m, a in _DATA.findall(testo or ""):
        g, m, a = int(g), int(m), int(a)
        if a != anno or not 1 <= m <= 12:
            continue
        if g == calendar.monthrange(a, m)[1]:
            chiusure.add(m)
    return chiusure.pop() if len(chiusure) == 1 else None


def testo_di_testa(file_path: str, pagine: int = PAGINE_DI_TESTA) -> str:
    """Il text layer delle prime pagine; vuoto su una scansione o un file illeggibile."""
    try:
        import fitz

        with fitz.open(file_path) as documento:
            return "\n".join(documento[i].get_text() for i in range(min(pagine, documento.page_count)))
    except Exception:
        return ""
