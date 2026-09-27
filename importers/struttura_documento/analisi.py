"""Struttura del documento per fase: quali pagine leggono i macroconti, quali i dettagli, e
quale route, decisa DOPO aver visto il documento (decisione del proprietario, 2026-09-23).

La struttura seleziona pagine e route; non decide importi, colonne o lati. Un insieme di
pagine vuoto non restringe nulla: meglio leggere tutto il documento che zero righe."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from importers.bilancio_classifier import ROUTE_IVCEE, ROUTE_TRIAL
from importers.struttura_documento.mappa import (MAX_PAGINE_CONTINUAZIONE, MIN_IMPORTI, NOTA_INTEGRATIVA,
                                                 _apre_sezione_nuova, _importi_pagina, _testo_di_testa,
                                                 e_xbrl_di_legge, mappa_documento, mappa_xbrl)

SCHEMI_CONTI = {"piano_dei_conti_gerarchico", "elenco_piatto"}
SCHEMI_LEGGE = {"iv_cee_di_legge", "riclassificato_con_codici_ivcee"}
TIPI_SP = {"prospetto_sp", "prospetto_sp_e_ce"}
TIPI_CE = {"prospetto_ce", "prospetto_sp_e_ce"}

# Schemi che il "modo" tratta come un elenco di conti da leggere in modo "conti": un documento
# "riclassificato con codici IVCEE" e' un elenco analitico per mastro (centinaia di righe per
# pagina), non uno schema di legge sintetico — leggerlo come "legge" sotto-conta gli aggregati
# quando manca anche un solo figlio di un totale (8 file del banco 26/09, Task lotto-b, fix 9).
SCHEMI_CONTI_MODO = {"piano_dei_conti_gerarchico", "elenco_piatto", "riclassificato_con_codici_ivcee"}

# Un voto vicino alla parita' (al massimo questo scarto di pagine fra "conti" e "legge") con
# l'indizio del classificatore (route TRIAL_BALANCE) sceglie "conti": budget_313 aveva un voto in
# parita' e nessun indizio, ed e' caduto sul lato sbagliato.
MARGINE_PAREGGIO_MODO = 1

# Titoli fissi delle tabelle di nota integrativa (schema OIC / tassonomia itcc) che portano
# natura e scadenza di crediti e debiti e la composizione delle rimanenze.
TITOLI_TABELLE_NOTA = re.compile(
    r"variazioni e (?:della )?scadenza dei (?:crediti|debiti)"
    r"|crediti iscritti nell'?\s*attivo circolante"
    r"|suddivisione dei (?:crediti|debiti) per area geografica"
    r"|debiti assistiti da garanzie reali"
    r"|finanziamenti effettuati da soci"
    r"|analisi delle variazioni delle rimanenze", re.I)


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


def _porta_captions_legali_con_totali(pdf: str | None) -> bool:
    """Vero solo quando il chiamante passa un file E quel file porta le colonne comparative
    dello schema di legge coi TOTALI stampati (``has_comparative_ivcee_columns``): il segnale
    deterministico, indipendente dalla vision, che i totali di livello superiore si leggono
    DIRETTAMENTE dalla riga stampata invece di doversi ricostruire sommando le foglie (Task 18,
    ruling c; diagnosi AMBIENTA §6b/§7-8). Senza ``pdf`` non si tenta nemmeno l'apertura: ogni
    chiamante che non lo passa (i test unitari di questo modulo, o un ramo futuro senza il
    percorso a portata di mano) resta sul voto di sempre."""
    if not pdf:
        return False
    from importers.standard_ivcee_parser import has_comparative_ivcee_columns
    return has_comparative_ivcee_columns(pdf)


def modo_da_mappe(mappe: list[dict], *, route_hint: str | None = None, pdf: str | None = None) -> str:
    """"conti" quando lo schema prevalente e' un elenco di conti (compreso il "riclassificato
    con codici IVCEE": un elenco analitico per mastro, non uno schema di legge sintetico), o
    quando il voto e' CONTESO (almeno una pagina per lato) e vicino alla parita' (scarto <=
    MARGINE_PAREGGIO_MODO pagine) e il classificatore ha gia' segnalato una situazione contabile
    (`route_hint == ROUTE_TRIAL`) — l'indizio pesa solo su un voto conteso, mai su un voto
    unanime (compreso un documento a pagina singola, `n == 1`, che non oppone alcun voto
    "conti") e mai contro una maggioranza netta per lo schema di legge.

    Eccezione (Task 18, ruling c, owner dopo la diagnosi AMBIENTA): un "riclassificato con
    codici IVCEE" che e' ANCHE uno schema di legge puro — captions B)/C)/D), I/II/III con
    TOTALI stampati, non un piano dei conti piatto — smette di votare "conti" quando il
    documento porta le colonne comparative dello schema di legge
    (``_porta_captions_legali_con_totali``, richiede ``pdf``): leggerlo come "legge" lascia che
    i totali di livello superiore si leggano DIRETTAMENTE dalla riga stampata invece di doversi
    ricostruire sommando le foglie, dove una gerarchia a piu' di due livelli (B = I+II+III,
    Totale attivo = B+C+...) puo' restare irrisolta (diagnosi AMBIENTA, causa radice #2). Gli
    8 file del banco 26/09 che hanno motivato "riclassificato -> conti" (fix round 1, Task
    lotto-b) NON portano quelle colonne comparative con totali: restano "conti" come prima,
    l'eccezione non li tocca. Senza ``pdf`` (il default) il comportamento e' quello di sempre."""
    prospetti = [m for m in mappe if m.get("tipo_pagina") in TIPI_SP | TIPI_CE]
    if not prospetti:
        return "legge"
    n = len(prospetti)
    schemi_conti_modo = SCHEMI_CONTI_MODO
    if (any(m.get("schema") == "riclassificato_con_codici_ivcee" for m in prospetti)
            and _porta_captions_legali_con_totali(pdf)):
        schemi_conti_modo = SCHEMI_CONTI_MODO - {"riclassificato_con_codici_ivcee"}
    conti = sum(1 for m in prospetti if m.get("schema") in schemi_conti_modo)
    if conti * 2 > n:
        return "conti"
    margine = n - conti * 2
    conteso = 0 < conti < n
    if route_hint == ROUTE_TRIAL and n >= 2 and conteso and margine <= MARGINE_PAREGGIO_MODO:
        return "conti"
    return "legge"


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


def _assorbi_continuazioni_perse(mappe: list[dict], pdf: str) -> list[dict]:
    """Una pagina che la vision ha lasciato "nota_o_testo" (mai vista perche' filtrata per pochi
    importi, o vista e classificata cosi') e' la continuazione del prospetto aperto se ha importi
    veri, segue subito una o piu' pagine dello stesso prospetto (SP o CE) e il suo testo non apre
    una sezione diversa — stesso meccanismo di `mappa_xbrl` per il ramo xbrl (Task lotto-b, fix 6b,
    diagnosi budget_972/614/158: pagine di continuazione del CE con importi veri, mai incluse).
    Al massimo MAX_PAGINE_CONTINUAZIONE pagine di fila."""
    import fitz
    out = list(mappe)
    with fitz.open(pdf) as doc:
        pagine = list(doc)
        n = len(out)
        i = 0
        while i < n:
            if out[i].get("tipo_pagina") in TIPI_SP | TIPI_CE:
                tipo = out[i]["tipo_pagina"]
                schema = out[i].get("schema")
                j, assorbite = i + 1, 0
                while (j < n and assorbite < MAX_PAGINE_CONTINUAZIONE and j < len(pagine)
                       and out[j].get("tipo_pagina") == "nota_o_testo"
                       and _importi_pagina(pagine[j]) >= MIN_IMPORTI
                       and not _apre_sezione_nuova(pagine[j])):
                    # Lo schema della pagina assorbita e' quello del blocco, non quello stantio
                    # che portava da "nota_o_testo" (il default di una pagina mai vista dalla
                    # vision, o una classificazione ormai superata): altrimenti voterebbe ancora
                    # in modo_da_mappe come se fosse una pagina indipendente (fix round 1, gap 2;
                    # stesso comportamento gia' in mappa_xbrl per il ramo xbrl).
                    out[j] = {**out[j], "tipo_pagina": tipo, "continuazione": True,
                              "sezioni": out[i].get("sezioni", []), "schema": schema}
                    assorbite += 1
                    j += 1
                i = j if assorbite else i + 1
            else:
                i += 1
    return out


def analizza_struttura(pdf: str, *, mappa_pagina_fn=None, route_hint: str | None = None) -> Struttura:
    inizio = time.monotonic()
    if e_xbrl_di_legge(pdf):
        mappe, fonte, chiamate = mappa_xbrl(pdf), "xbrl_titoli", 0
    else:
        mappe = mappa_documento(pdf, mappa_pagina_fn=mappa_pagina_fn)
        fonte, chiamate = "vision", int(mappe[0].get("_chiamate", 0)) if mappe else 0
        mappe = _assorbi_continuazioni_perse(mappe, pdf)
    route = ROUTE_IVCEE if fonte == "xbrl_titoli" else route_da_mappe(mappe)
    pagine_sp = [m["pagina"] for m in mappe if m.get("tipo_pagina") in TIPI_SP]
    pagine_ce = [m["pagina"] for m in mappe if m.get("tipo_pagina") in TIPI_CE]
    prospetti = set(pagine_sp) | set(pagine_ce)
    dettaglio = {m["pagina"] for m in mappe if m.get("tipo_pagina") == "dettaglio_conti"}
    dettaglio |= set(pagine_tabelle_nota(pdf))
    modo = modo_da_mappe(mappe, route_hint=route_hint, pdf=pdf)
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
