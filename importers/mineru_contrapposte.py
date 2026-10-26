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
_CODICE = re.compile(r"^\d{1,3}(?:[./]\d{1,4})*$|^\d{5,8}(?: \d{3})?$")
# AGO e simili stampano codice e descrizione in una cella sola, che MinerU tiene insieme:
# "13005000 - Costi di impianto e di ampliamento", "100045 000 - costi di impianto" (budget_330)
_CODICE_E_DESCRIZIONE = re.compile(r"^(\d{5,8}(?: \d{3})?)\s+-\s+(\S.*)$")
# un importo spezzato fra due celle o da uno spazio: "1.440.337" + ",23"
_VIRGOLA_STACCATA = re.compile(r"(\d)\s*\|?\s*,(\d{2})(?!\d)")
# Le grafie OCR di un importo viste sulle scansioni (budget_689): il punto al posto della
# virgola ("94.086.46"), gli spazi al posto dei punti ("11 396,02") e la virgola persa
# ("7 467 04"). Solo celle interamente numeriche e con almeno un gruppo di migliaia: un
# codice di conto stampato con lo spazio ("57 90") non diventa un importo.
_OCR_PUNTO_DECIMALE = re.compile(r"(-?\d{1,3}(?:\.\d{3})+)\.(\d{2})")
_OCR_SPAZI = re.compile(r"(-?\d{1,3}(?: \d{3})+)[ ,](\d{2})")


def _importo_ocr(cella: str) -> str:
    """La cella nella forma "1.234,56" quando e' una delle grafie OCR riconosciute,
    altrimenti senza spazi come prima."""
    c = cella.strip()
    m = _OCR_PUNTO_DECIMALE.fullmatch(c)
    if m:
        return f"{m.group(1)},{m.group(2)}"
    m = _OCR_SPAZI.fullmatch(c)
    if m:
        return f"{m.group(1).replace(' ', '.')},{m.group(2)}"
    return c.replace(" ", "")


_PAROLA_TOTALE = re.compile(r"(?i)\b(totale|eccedenza|utile|perdita|risultato|differenza)")

_LARGHEZZA = 595.0
_PASSO = 11.0
_CORPO = 7.0
_LARGO_DESCRIZIONE = 165.0    # dalla descrizione all'inizio della colonna degli importi


def _sezione_del_titolo(titolo: str) -> Optional[str]:
    titolo = titolo.upper()
    if "PATRIMONIAL" in titolo:
        return "sp"
    if "ECONOMIC" in titolo:
        return "ce"
    # l'intestazione dei due lati, quando il titolo sta in un'altra tabella (budget_330)
    if "ATTIVIT" in titolo and "PASSIVIT" in titolo:
        return "sp"
    if re.search(r"\bCOSTI\b", titolo) and re.search(r"\bRICAVI\b", titolo):
        return "ce"
    return None


# Quante righe in testa a una tabella senza didascalia si guardano per il titolo.
_RIGHE_DI_TESTA = 8


def _sezione(table) -> tuple[Optional[str], int]:
    """La sezione della tabella e quante righe d'intestazione saltare.

    Di solito il titolo e' la didascalia di MinerU. Sull'ultima pagina di Unicarton
    31/08/2026 la didascalia e' vuota: l'intestazione della pagina (azienda, anno,
    "CONTO ECONOMICO", "Costi | Ricavi") e' finita dentro la tabella, che veniva scartata
    con le imposte, i totali e l'utile. Allora il titolo si cerca nelle righe di testa,
    prima del primo conto, e le righe fino al titolo (azienda, anno) non si leggono."""
    sezione = _sezione_del_titolo(table.caption or "")
    if sezione or (table.caption or "").strip():
        return sezione, 0
    for i, row in enumerate(table.rows[:_RIGHE_DI_TESTA]):
        celle = [_testo(c) for c in row.cells]
        if any(_CODICE.match(c) for c in celle if c):
            break
        sezione = _sezione_del_titolo(" ".join(celle))
        if sezione:
            return sezione, i + 1
    return None, 0


def _testo(cella) -> str:
    return (cella.text or "").strip()


class _Ricucitore:
    """Ricompone i conti di una sezione dalle celle in ordine di lettura, anche quando
    MinerU spezza una riga della tabella su piu' righe fisiche (Unicarton 31/08/2026,
    scansione da 6,5 MB: il codice di sinistra su una riga, l'importo di destra su quella
    dopo, descrizione e importo di sinistra con codice e descrizione di destra su una
    terza). Su ciascun lato un conto e' codice, descrizione, importo, in quest'ordine:
    l'importo va al lato che ha gia' la descrizione e aspetta l'importo, un codice a
    inizio riga apre un conto a sinistra, piu' avanti nella riga a destra. Su una riga
    intera il risultato e' quello del taglio fisso a tre celle per lato."""

    def __init__(self):
        self.attesa = {"L": None, "R": None}       # [codice, descrizione, importo|None]

    def in_attesa(self) -> bool:
        return any(a is not None and not a[1] for a in self.attesa.values())

    def riga(self, celle: list[str]) -> list:
        """I conti completati da questa riga, come (lato, (codice, descrizione, importo))."""
        usciti, lato, sinistra_toccata = [], "L", False
        codice_appena_letto = None              # lato del codice della cella prima
        for i, c in enumerate(celle):
            if not c:
                continue
            if codice_appena_letto and _CODICE.match(c):
                # La colonna "Partitario" subito dopo il conto ("19.01.01 | 1 | BANCO BPM",
                # budget_689): e' il sottoconto di quel conto, non un conto nuovo. Preso da
                # solo, "1" diventava il padre di 19/1901/190101 e "4" quello dei fondi 41,
                # delle svalutazioni 43 e dei ratei 45, e la banca si portava via la loro massa.
                a = self.attesa[codice_appena_letto]
                a[0] = f"{a[0]}.{c}"
                codice_appena_letto = None
                continue
            codice_appena_letto = None
            importo = _importo_ocr(c)
            if _IMPORTO.fullmatch(importo):
                for s in (lato, "R" if lato == "L" else "L"):
                    a = self.attesa[s]
                    if a is not None and a[1] and a[2] is None:
                        usciti.append((s, (a[0], a[1], importo)))
                        self.attesa[s] = None
                        if s == "L":
                            lato = "R"
                        break
                continue
            if _CODICE.match(c):
                lato = "R" if (sinistra_toccata or i >= 3) else "L"
                self.attesa[lato] = [c, "", None]
                codice_appena_letto = lato
                if lato == "L":
                    sinistra_toccata = True
                continue
            a = self.attesa[lato]
            if a is None:
                self.attesa[lato] = ["", c, None]
            elif not a[1]:
                a[1] = c
            if lato == "L":
                sinistra_toccata = True
        return usciti


def _coppie_di_piede(celle: list[str]) -> list[tuple[str, str]]:
    """Le coppie (didascalia, importo) di una riga di piede, nell'ordine di stampa.
    Un importo senza didascalia ripete quella prima solo se e' lo stesso importo
    ("Totale a quadratura X | X"). Un importo diverso e' un totale di un'altra riga che
    MinerU ha portato qui ("Utile d'esercizio 68.247,80 | 1.440.337,23", Unicarton
    31/08/2026): con la didascalia dell'utile diventava un secondo risultato, e si scarta.
    E' un totale di controllo, non un conto: nessuna massa si perde."""
    testo = " | ".join(c for c in celle if c)
    testo = _VIRGOLA_STACCATA.sub(r"\1,\2", testo)
    coppie, pos = [], 0
    for m in _IMPORTO.finditer(testo):
        didascalia = testo[pos:m.start()].strip(" |:_-")
        pos = m.end()
        if not didascalia:
            if not coppie or coppie[-1][1] != m.group(0):
                logger.info("piede MinerU: importo %s senza didascalia scartato", m.group(0))
                continue
            didascalia = coppie[-1][0]
        coppie.append((didascalia, m.group(0)))
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


def _sei_celle(celle: list[str]) -> list[str]:
    """Una riga a quattro celle con codice e descrizione insieme ("13005000 - Costi di
    impianto | 5.555,24 | 13005005 - F.do amm. | 1.111,05") nella forma a sei celle che il
    ricucitore conosce. Il lato resta quello della colonna d'origine: una riga col solo lato
    destro ("| | 204850 000 - fatture da ricevere | 32,94") resta a destra. Le altre righe
    passano com'erano."""
    if len(celle) != 4 or not any(_CODICE_E_DESCRIZIONE.match(c) for c in celle):
        return celle
    out: list[str] = []
    for c, importo in ((celle[0], celle[1]), (celle[2], celle[3])):
        m = _CODICE_E_DESCRIZIONE.match(c)
        out.extend((*m.groups(), importo) if m else ("", c, importo))
    return out


def _righe(tables) -> dict[str, list]:
    """Per sezione, la lista ordinata di righe da stampare: ("conto", L, R) oppure
    ("piede", lato, didascalia, importo)."""
    out: dict[str, list] = {"sp": [], "ce": []}
    ricuci = {"sp": _Ricucitore(), "ce": _Ricucitore()}
    for table in tables:
        sezione, intestazione = _sezione(table)
        if sezione is None:
            continue
        for row in table.rows[intestazione:]:
            celle = _sei_celle([_testo(c) for c in row.cells])
            if not any(celle):
                continue
            unite = " ".join(celle)
            codici = any(_CODICE.match(c) for c in celle if c)
            if (_PAROLA_TOTALE.search(unite) and not codici
                    and not ricuci[sezione].in_attesa()):
                coppie = _coppie_di_piede(celle)
                for i, (didascalia, importo) in enumerate(coppie):
                    lato = _lato_del_piede(sezione, didascalia, i, len(coppie))
                    out[sezione].append(("piede", lato, didascalia, importo))
                continue
            for lato, conto in ricuci[sezione].riga(celle):
                out[sezione].append(("conto", conto, None) if lato == "L"
                                    else ("conto", None, conto))
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
        # per intero, rimpicciolita se serve: troncata perdeva la coda, dove il gestionale
        # stampa la scadenza ("Debiti verso soci per finanziamenti (OE)", budget_330)
        corpo = min(_CORPO, _CORPO * _LARGO_DESCRIZIONE
                    / max(font.text_length(descrizione, fontsize=_CORPO), 1))
        page.insert_text((x + 42, y), descrizione, fontsize=corpo)
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
    # un conto ha il suo codice: righe "descrizione | importo" senza codice sono un prospetto
    # di legge (budget_1405, "B) Immobilizzazioni immateriali | 707.317,45"), che preso per
    # una situazione contabile mandava il PDF sintetico a Qwen per niente prima del lettore giusto
    conti = {s: sum(1 for r in righe[s] if r[0] == "conto"
                    and any(lato and lato[0] for lato in r[1:])) for s in righe}
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
