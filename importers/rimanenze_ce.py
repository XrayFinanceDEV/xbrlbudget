"""Rimanenze a conto economico: in quale voce di legge va un conto di rimanenze
letto in un elenco di conti (bilancio di verifica, situazione contabile).

Art. 2425 c.c. e OIC 12 tengono separate due variazioni:

- **A.2** (``ce02``) - prodotti in corso di lavorazione, semilavorati e finiti (A.3,
  lavori in corso su ordinazione, confluisce qui): finali meno iniziali, fra i RICAVI;
- **B.11** (``ce10``) - materie prime, sussidiarie, di consumo e merci: iniziali meno
  finali, fra i COSTI.

Un elenco di conti stampa le iniziali fra i costi e le finali fra i ricavi, in lordo.
Lasciarle a un secchio qualunque (B.14 oneri diversi, A.5 altri ricavi) chiude l'utile
al centesimo e gonfia valore e costi della produzione dello stesso importo: un difetto
che quadra, e nessun controllo lo vede (Unicarton 2025: 193.691,65 di rimanenze finali
dentro ``ce04``, 218.314,13 di iniziali dentro ``ce12``). Metterle tutte in ``ce10``
sbaglia invece il consumo di materie, cioe' il DIO e il motore del previsionale.

La natura si legge dalla descrizione del conto, poi da quella dei padri; quando il
testo non la dice, o le dice entrambe ("prodotti finiti e merci"), resta ``None`` e il
chiamante tiene la voce di sempre (``ce10``).
"""
from __future__ import annotations

import re
from typing import Optional

# Un conto di movimento del magazzino: rimanenze/esistenze iniziali o finali, o la
# variazione. "RIM." e "RIMAN." solo davanti a INIZ/FIN: da soli sono anche rimborsi.
_CONTO_RE = re.compile(
    r"RIMANENZ|ESISTENZ|\bRIM(?:AN)?\.\s*(?:INIZ|FIN)|\bVAR\.?\s*RIM")

_PRODOTTI_RE = re.compile(
    r"PRODOTT|\bPROD\.|SEMILAV|\bSEMIL\.|\bIN\s*CORSO|\bFINIT|\bLAV(?:ORI|\.)|ORDINAZ|COMMESS")
_MATERIE_RE = re.compile(
    r"MATERI|\bMAT\.|SUSSID|CONSUM|\bMERC[EI.]|IMBALL|COMMERCIALIZZ")

_MERCI_RE = re.compile(r"\bPROD(?:OTT\w*|\.)\s*(?:COMMERCIALIZZ|(?:DEST\w*\.?\s*)?(?:ALLA\s*)?RIVENDIT)\w*\.?")


def e_conto_rimanenze(testo: str) -> bool:
    """La descrizione e' quella di un conto di rimanenze iniziali/finali o di variazione."""
    return bool(_CONTO_RE.search((testo or "").upper()))


def natura_rimanenze(*testi: str) -> Optional[str]:
    """``'ce02'`` (prodotti, A.2) o ``'ce10'`` (materie e merci, B.11) per la prima
    descrizione che lo dice senza ambiguita', nell'ordine dato (il conto, poi i padri).
    Una descrizione che nomina entrambe le nature chiude la ricerca con ``None``: un
    padre non puo' decidere per un conto misto."""
    for testo in testi:
        # "prodotti commercializzati / destinati alla rivendita" sono merci (B.11)
        t = _MERCI_RE.sub("MERCI", (testo or "").upper())
        prodotti = bool(_PRODOTTI_RE.search(t))
        materie = bool(_MATERIE_RE.search(t))
        if prodotti and materie:
            return None
        if prodotti:
            return "ce02"
        if materie:
            return "ce10"
    return None


# W4 del proprietario (2026-11-04): la variazione dei lavori in corso su ordinazione (commesse) va in A.3, la sua voce
# di legge (``ce03``), non in A.2. ``natura_rimanenze`` resta com'e' per i lettori di oggi; chi vuole la voce di legge
# usa ``voce_rimanenze``.
_ORDINAZIONE_RE = re.compile(r"ORDINAZ|COMMESS")


def voce_rimanenze(*testi: str) -> Optional[str]:
    """La voce di legge di un conto di rimanenze: ``'ce03'`` (A.3) per i lavori in corso su ordinazione, altrimenti
    quella di ``natura_rimanenze``. Decide la prima descrizione che dice la natura, come per ``natura_rimanenze``."""
    natura = natura_rimanenze(*testi)
    if natura != "ce02":
        return natura
    for testo in testi:
        t = _MERCI_RE.sub("MERCI", (testo or "").upper())
        if _PRODOTTI_RE.search(t):
            return "ce03" if _ORDINAZIONE_RE.search(t) else "ce02"
    return natura
