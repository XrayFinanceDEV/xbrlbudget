"""Struttura del documento per fase: quali pagine leggono i macroconti, quali i dettagli, e
quale route, decisa DOPO aver visto il documento (decisione del proprietario, 2026-09-23).

La struttura seleziona pagine e route; non decide importi, colonne o lati. Un insieme di
pagine vuoto non restringe nulla: meglio leggere tutto il documento che zero righe."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from importers.bilancio_classifier import ROUTE_IVCEE, ROUTE_TRIAL
from importers.struttura_documento.mappa import (MIN_IMPORTI, NOTA_INTEGRATIVA, _importi_pagina,
                                                 _testo_di_testa, e_xbrl_di_legge, mappa_documento,
                                                 mappa_xbrl)

SCHEMI_CONTI = {"piano_dei_conti_gerarchico", "elenco_piatto"}
SCHEMI_LEGGE = {"iv_cee_di_legge", "riclassificato_con_codici_ivcee"}
TIPI_SP = {"prospetto_sp", "prospetto_sp_e_ce"}
TIPI_CE = {"prospetto_ce", "prospetto_sp_e_ce"}

# Titoli fissi delle tabelle di nota integrativa (schema OIC / tassonomia itcc) che portano
# natura e scadenza di crediti e debiti e la composizione delle rimanenze.
TITOLI_TABELLE_NOTA = re.compile(
    r"variazioni e (?:della )?scadenza dei (?:crediti|debiti)"
    r"|crediti iscritti nell'?\s*attivo circolante"
    r"|suddivisione dei (?:crediti|debiti) per area geografica"
    r"|debiti assistiti da garanzie reali"
    r"|finanziamenti effettuati da soci"
    r"|analisi delle variazioni delle rimanenze", re.I)

SCHEMI_CONTI_MODO = {"piano_dei_conti_gerarchico", "elenco_piatto"}


@dataclass
class Struttura:
    fonte: str                      # "xbrl_titoli" | "vision"
    route: str | None
    pagine_sp: list[int]
    pagine_ce: list[int]
    pagine_dettaglio: list[int]
    chiamate_vision: int
    secondi: float
    mappe: list[dict] = field(default_factory=list)
    modo: str = "legge"             # "conti" | "legge"
    colonne_sp: list[str] = field(default_factory=list)
    colonne_ce: list[str] = field(default_factory=list)
    intestazioni_sp: list[str] = field(default_factory=list)
    intestazioni_ce: list[str] = field(default_factory=list)
    pagine_senza_testo: list[int] = field(default_factory=list)

    def pagine_macro(self) -> set[int] | None:
        pagine = set(self.pagine_sp) | set(self.pagine_ce)
        return pagine or None

    def pagine_dettagli(self) -> set[int] | None:
        pagine = set(self.pagine_sp) | set(self.pagine_dettaglio)
        return pagine or None

    def report(self) -> dict:
        return {"stato": "ok", "fonte": self.fonte, "route_struttura": self.route,
                "pagine_sp": self.pagine_sp, "pagine_ce": self.pagine_ce,
                "pagine_dettaglio": self.pagine_dettaglio,
                "chiamate_vision": self.chiamate_vision, "secondi": round(self.secondi, 1),
                "modo": self.modo, "colonne_sp": self.colonne_sp, "colonne_ce": self.colonne_ce,
                "intestazioni_sp": self.intestazioni_sp, "intestazioni_ce": self.intestazioni_ce,
                "pagine_senza_testo": self.pagine_senza_testo}


def modo_da_mappe(mappe: list[dict]) -> str:
    prospetti = [m for m in mappe if m.get("tipo_pagina") in TIPI_SP | TIPI_CE]
    conti = sum(1 for m in prospetti if m.get("schema") in SCHEMI_CONTI_MODO)
    return "conti" if prospetti and conti * 2 > len(prospetti) else "legge"


def _colonne_di(mappe: list[dict], tipi: set[str]) -> tuple[list[str], list[str]]:
    for m in mappe:
        if m.get("tipo_pagina") in tipi and m.get("sezioni"):
            col = m["sezioni"][0].get("colonne") or []
            return [c.get("ruolo", "altro") for c in col], [c.get("intestazione", "") for c in col]
    return [], []


def route_da_mappe(mappe: list[dict]) -> str | None:
    prospetti = [m for m in mappe if m.get("tipo_pagina") in TIPI_SP | TIPI_CE]
    conti = sum(1 for m in prospetti if m.get("schema") in SCHEMI_CONTI)
    legge = sum(1 for m in prospetti if m.get("schema") in SCHEMI_LEGGE)
    if conti > legge:
        return ROUTE_TRIAL
    if legge > conti:
        return ROUTE_IVCEE
    return None


def pagine_tabelle_nota(pdf: str) -> list[int]:
    """Pagine dopo «Nota integrativa» con un titolo di tabella di dettaglio e almeno
    MIN_IMPORTI importi, piu' la pagina seguente se ha importi (le tabelle continuano)."""
    import fitz
    out: set[int] = set()
    with fitz.open(pdf) as doc:
        pagine = list(doc)
        inizio = next((i for i, p in enumerate(pagine) if NOTA_INTEGRATIVA.search(_testo_di_testa(p))), None)
        if inizio is None:
            return []
        for i in range(inizio, len(pagine)):
            testo = " ".join(pagine[i].get_text().split())
            if TITOLI_TABELLE_NOTA.search(testo) and _importi_pagina(pagine[i]) >= MIN_IMPORTI:
                out.add(i + 1)
                if i + 1 < len(pagine) and _importi_pagina(pagine[i + 1]) >= MIN_IMPORTI:
                    out.add(i + 2)
    return sorted(out)


def analizza_struttura(pdf: str, *, mappa_pagina_fn=None) -> Struttura:
    inizio = time.monotonic()
    if e_xbrl_di_legge(pdf):
        mappe, fonte, chiamate = mappa_xbrl(pdf), "xbrl_titoli", 0
    else:
        mappe = mappa_documento(pdf, mappa_pagina_fn=mappa_pagina_fn)
        fonte, chiamate = "vision", int(mappe[0].get("_chiamate", 0)) if mappe else 0
    route = ROUTE_IVCEE if fonte == "xbrl_titoli" else route_da_mappe(mappe)
    pagine_sp = [m["pagina"] for m in mappe if m.get("tipo_pagina") in TIPI_SP]
    pagine_ce = [m["pagina"] for m in mappe if m.get("tipo_pagina") in TIPI_CE]
    prospetti = set(pagine_sp) | set(pagine_ce)
    dettaglio = {m["pagina"] for m in mappe if m.get("tipo_pagina") == "dettaglio_conti"}
    dettaglio |= set(pagine_tabelle_nota(pdf))
    modo = modo_da_mappe(mappe)
    colonne_sp, intestazioni_sp = _colonne_di(mappe, TIPI_SP)
    colonne_ce, intestazioni_ce = _colonne_di(mappe, TIPI_CE)
    import fitz
    with fitz.open(pdf) as doc:
        pagine_senza_testo = [i + 1 for i, p in enumerate(doc) if not p.get_text().strip()]
    return Struttura(fonte=fonte, route=route, pagine_sp=pagine_sp, pagine_ce=pagine_ce,
                     pagine_dettaglio=sorted(dettaglio - prospetti), chiamate_vision=chiamate,
                     secondi=time.monotonic() - inizio, mappe=mappe, modo=modo,
                     colonne_sp=colonne_sp, colonne_ce=colonne_ce,
                     intestazioni_sp=intestazioni_sp, intestazioni_ce=intestazioni_ce,
                     pagine_senza_testo=pagine_senza_testo)
