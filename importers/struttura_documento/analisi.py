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
                                                 _apre_sezione_nuova, _importi_pagina, _testo_di_testa, pagina_continua_prospetto,
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
    # Task 18, ruling (c) addendum: vero solo per un "riclassificato con codici IVCEE" che e'
    # ANCHE schema di legge coi totali stampati (owner, dopo la diagnosi AMBIENTA §7-8) - le
    # sue macro-voci possono stare INTERAMENTE su una pagina classificata "dettaglio_conti"
    # per il solo cambio pagina fisico. Default False: ogni "legge" precedente a questo
    # ruling ha pagine_dettaglio che sono tabelle di nota integrativa vere, non macro-voci, e
    # non deve vederle nel prompt macro di import_snello.
    macro_include_dettaglio: bool = False

    def pagine_macro(self) -> set[int] | None:
        pagine = set(self.pagine_sp) | set(self.pagine_ce)
        return pagine or None

    def pagine_dettagli(self) -> set[int] | None:
        pagine = set(self.pagine_sp) | set(self.pagine_dettaglio)
        return pagine or None

    def report(self) -> dict:
        if self.fonte == "deterministico":
            # Nessuna fase di struttura e' girata (Task 24): la lettura deterministica ha deciso
            # senza vision. Le pagine, quando ci sono, le ha derivate il testo, mai un modello.
            return {"stato": "non_richiesta", "fonte": "deterministico", "chiamate_vision": 0,
                    "modo": self.modo, "pagine_sp": self.pagine_sp, "pagine_ce": self.pagine_ce,
                    "pagine_dettaglio": self.pagine_dettaglio, "colonne_sp": self.colonne_sp,
                    "colonne_ce": self.colonne_ce}
        # Il voto della vision pagina per pagina, a parte dal modo scelto: il banco misura quante
        # volte la classificazione della vision concorda col modo deciso (Task 24).
        schemi: dict[str, int] = {}
        tipi: dict[str, int] = {}
        for m in self.mappe:
            tipi[m.get("tipo_pagina", "?")] = tipi.get(m.get("tipo_pagina", "?"), 0) + 1
            if m.get("tipo_pagina") in TIPI_SP | TIPI_CE:
                schemi[m.get("schema") or "?"] = schemi.get(m.get("schema") or "?", 0) + 1
        return {"stato": "ok", "fonte": self.fonte, "route_struttura": self.route,
                "schemi": schemi, "tipi_pagina": tipi,
                "pagine_sp": self.pagine_sp, "pagine_ce": self.pagine_ce,
                "pagine_dettaglio": self.pagine_dettaglio,
                "chiamate_vision": self.chiamate_vision, "secondi": round(self.secondi, 1),
                "modo": self.modo, "colonne_sp": self.colonne_sp, "colonne_ce": self.colonne_ce,
                "intestazioni_sp": self.intestazioni_sp, "intestazioni_ce": self.intestazioni_ce,
                "pagine_senza_testo": self.pagine_senza_testo}


# Importo con decimali, oppure intero con separatore delle migliaia ("2.216.822"): i bilanci in
# euro interi (budget_297, 247, 253) non stampano decimali. Un anno ("2025") o un numero di
# pagina non hanno separatori e non contano.
_IMPORTO = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}|\d{1,3}(?:\.\d{3})+(?![\d,])")
_MIN_IMPORTI_PAGINA = 3
_TITOLO_CE = re.compile(r"^\s*conto economico\s*$", re.I | re.M)


def pagine_dettagli_da_testo(pdf: str) -> list[int]:
    """Le pagine che portano lo SP e il suo dettaglio, dal solo testo (nessuna chiamata a un
    modello): dalla prima pagina con "STATO PATRIMONIALE" fino alla pagina dove comincia il
    titolo "CONTO ECONOMICO" (compresa: lo SP puo' finire a meta' pagina), piu' le tabelle di
    nota integrativa. Serve a ``enrich_pdf_details`` quando la struttura non e' girata: stesso
    ruolo di ``Struttura.pagine_dettagli`` senza la vision. Vuoto = nessuna restrizione."""
    import fitz
    with fitz.open(pdf) as doc:
        testi = [p.get_text() for p in doc]
    # Una pagina di indice o di copertina che nomina i titoli non e' il prospetto: l'inizio e' la
    # prima pagina con "stato patrimoniale" che porta importi veri.
    inizio = next((i for i, t in enumerate(testi)
                   if "stato patrimoniale" in t.casefold() and len(_IMPORTO.findall(t)) >= _MIN_IMPORTI_PAGINA),
                  None)
    if inizio is None:
        return []
    fine, include_fine = len(testi) - 1, True
    for i in range(inizio, len(testi)):
        m = _TITOLO_CE.search(testi[i])
        if m:
            fine = i
            # La pagina dove comincia il CE appartiene allo SP solo se SOPRA il titolo ci sono
            # importi (lo SP finisce a meta' pagina: budget_313, budget_352); se il titolo e' in
            # testa, la pagina e' tutta CE (AMBIENTA verifica, pagina 4: falso positivo prima).
            include_fine = len(_IMPORTO.findall(testi[i][:m.start()])) >= _MIN_IMPORTI_PAGINA
            break
    ultima = fine if include_fine else fine - 1
    return sorted(set(range(inizio + 1, ultima + 2)) | set(pagine_tabelle_nota(pdf)))


def struttura_deterministica(pdf: str, *, modo: str) -> Struttura:
    """Il segnaposto di una lettura deterministica adottata prima di ogni vision (Task 24):
    nessuna mappa di pagina, ``pagine_dettaglio`` dal testo, chiamate_vision a zero."""
    return Struttura(fonte="deterministico", route=None, pagine_sp=[], pagine_ce=[],
                     pagine_dettaglio=pagine_dettagli_da_testo(pdf), chiamate_vision=0,
                     secondi=0.0, mappe=[], modo=modo)


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


def _riclassificato_con_captions_legali(prospetti: list[dict], pdf: str | None) -> bool:
    """Vero quando almeno un prospetto e' schema "riclassificato_con_codici_ivcee" E il
    documento porta le colonne comparative dello schema di legge coi totali stampati: il
    segnale unico che decide sia il modo (Task 18, ruling c) sia se le pagine_dettaglio
    entrano anche nel prompt macro di import_snello invece che nel solo recupero dettaglio a
    valle (``Struttura.macro_include_dettaglio``, owner dopo la diagnosi AMBIENTA §7-8: "9)
    per il personale" e "8) per godimento di beni di terzi" stanno INTERAMENTE su una pagina
    dettaglio_conti, non un piano dei conti piatto)."""
    if not any(m.get("schema") == "riclassificato_con_codici_ivcee" for m in prospetti):
        return False
    return _porta_captions_legali_con_totali(pdf)


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
    if _riclassificato_con_captions_legali(prospetti, pdf):
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
            ruoli = [c.get("ruolo", "altro") for c in col]
            intestazioni = [c.get("intestazione", "") for c in col]
            return _ruoli_dalle_intestazioni(ruoli, intestazioni), intestazioni
    return [], []


_DIDASCALIA_DI_RIGA = re.compile(
    r"^\s*(?:[A-E]|[IVX]+|\d{1,2}(?:-(?:bis|ter|quater))?|[a-e])\s*[\).]\s+\S|^\s*(?:totale|differenza|risultato)\b",
    re.I)


def _sono_didascalie(intestazioni: list[str]) -> bool:
    """Le «intestazioni» sono in maggioranza didascalie di riga (voci di legge), non colonne."""
    righe = [i for i in intestazioni if _DIDASCALIA_DI_RIGA.match(i or "")]
    return len(intestazioni) >= 3 and len(righe) * 2 > len(intestazioni)


def _colonne_vere(proprie: tuple[list[str], list[str]],
                  altre: tuple[list[str], list[str]]) -> tuple[list[str], list[str]]:
    """Le colonne di una sezione, salvo che la vision abbia dichiarato come colonne le didascalie
    di riga (budget_1433: «5) Altri ricavi e proventi», «B) Costi della produzione»... come
    colonne del CE, e il modello saltava i ricavi). Allora valgono quelle dell'altra sezione dello
    stesso documento, se sono vere; altrimenti nessuna."""
    if not _sono_didascalie(proprie[1]):
        return proprie
    return altre if altre[1] and not _sono_didascalie(altre[1]) else ([], [])


_DATA_O_ANNO = re.compile(r"(?:(\d{1,2})[/.\-](\d{1,2})[/.\-])?(20\d{2})")


def _ruoli_dalle_intestazioni(ruoli: list[str], intestazioni: list[str]) -> list[str]:
    """L'intestazione stampata decide il ruolo della colonna, la vision propone soltanto: quando
    la vision non da' nessuna colonna di saldo e le intestazioni non parlano di dare/avere, i ruoli
    si leggono da loro (budget_1445: [dare, avere, dare, avere] su «Periodo fino al 30/06/2026 |
    ... al 30/06/2025 | Diff. % | Diff. Valore»). «Diff», «variaz», «scostam» sono variazioni,
    «%» una percentuale; fra le colonne datate la piu' recente e' il saldo corrente, le altre il
    precedente. Senza alcuna colonna datata, nessun verdetto: restano i ruoli della vision."""
    if (any(r in ("saldo_corrente", "saldo_finale") for r in ruoli)
            or len(intestazioni) != len(ruoli)
            or any(re.search(r"\b(dare|avere)\b", i, re.I) for i in intestazioni)):
        return ruoli
    nuovi: list[str | None] = []
    date: dict[int, tuple[int, int, int]] = {}
    for k, i in enumerate(intestazioni):
        testo = i.casefold()
        if re.search(r"\bdiff|variaz|scostam", testo):
            nuovi.append("percentuale" if "%" in testo else "variazione")
            continue
        if "%" in testo:
            nuovi.append("percentuale")
            continue
        m = _DATA_O_ANNO.search(i)
        if m:
            date[k] = (int(m.group(3)), int(m.group(2) or 0), int(m.group(1) or 0))
        nuovi.append(None)
    if not date:
        return ruoli
    corrente = max(date, key=date.get)
    return [("saldo_corrente" if k == corrente else "saldo_precedente") if k in date
            else (r if r is not None else ruoli[k]) for k, r in enumerate(nuovi)]


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
                       and pagina_continua_prospetto(pagine[j], tipo)
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


_TITOLO_SEZIONE_SP = re.compile(r"^\s*stato\s+patrimoniale\b", re.I | re.M)
_TITOLO_SEZIONE_CE = re.compile(r"^\s*conto\s+economico\s*$", re.I | re.M)
_FINE_PROSPETTI = re.compile(r"(?i)nota\s+integrativa|rendiconto\s+finanziario")


def _pagine_dai_titoli(pagine_sp: list[int], pagine_ce: list[int],
                       testi: dict[int, str]) -> tuple[list[int], list[int]]:
    """I titoli di sezione stampati decidono le pagine quando la vision li contraddice: una
    pagina del CE prima del titolo «Conto economico», o una dello SP dopo (budget_1445, 14
    pagine: SP [3, 5] e CE [1, 6, 9, 12, 13, 14] dalla vision, titoli a p.1, p.6 e p.9). Lo SP
    va dal primo titolo dello SP fino al titolo del CE (compresa quella pagina se il titolo non
    sta in testa), il CE dal suo titolo fino all'ultima pagina con importi prima della nota
    integrativa. Senza contraddizione, o senza titoli con importi, decide la vision."""
    def importi(n):
        return len(_IMPORTO.findall(testi.get(n, "")))

    con_titolo = lambda rx: [n for n in sorted(testi) if rx.search(testi[n])
                             and importi(n) >= _MIN_IMPORTI_PAGINA]
    titoli_sp, titoli_ce = con_titolo(_TITOLO_SEZIONE_SP), con_titolo(_TITOLO_SEZIONE_CE)
    if not titoli_sp or not titoli_ce or min(titoli_ce) <= min(titoli_sp):
        return pagine_sp, pagine_ce
    a, c = min(titoli_sp), min(titoli_ce)
    if not (any(p < c for p in pagine_ce) or any(p > c for p in pagine_sp)):
        return pagine_sp, pagine_ce
    sp = [n for n in range(a, c) if importi(n) >= _MIN_IMPORTI_PAGINA]
    righe_c = [r for r in testi[c].splitlines() if r.strip()]
    if next(i for i, r in enumerate(righe_c) if _TITOLO_SEZIONE_CE.match(r)) > 3:
        sp.append(c)            # il CE si apre a meta' pagina: sopra c'e' la coda dello SP
    ce = []
    for n in range(c, max(testi) + 1):
        if importi(n) < _MIN_IMPORTI_PAGINA or (n > c and _FINE_PROSPETTI.search(testi[n])):
            break
        ce.append(n)
    return sp, ce


_DATA_INTESTAZIONE = re.compile(r"\d{1,2}[/.\-]\d{1,2}[/.\-]20\d{2}")


def _ordina_colonne(ruoli: list[str], intestazioni: list[str],
                    parole: list) -> tuple[list[str], list[str]]:
    """Le colonne nell'ordine in cui la pagina stampa le loro intestazioni (budget_1445: la
    vision elencava [Diff. %, Diff. Valore, 2025, 2026] e il saldo corrente finiva sull'ultimo
    importo della riga, la Diff. Valore). Ogni intestazione si ritrova nella fascia della
    testata: dalla sua data, se ne ha una, altrimenti dall'ultima parola. Una sola non trovata:
    resta l'ordine della vision."""
    if len(ruoli) != len(intestazioni) or len(ruoli) < 2:
        return ruoli, intestazioni
    date = [w for w in parole if _DATA_INTESTAZIONE.fullmatch(str(w[4]).strip())]
    if not date:
        return ruoli, intestazioni
    alto, basso = min(w[1] for w in date) - 25, max(w[1] for w in date) + 25
    fascia = [w for w in parole if alto <= w[1] <= basso]
    usate, posizioni = set(), []
    for i in intestazioni:
        m = _DATA_INTESTAZIONE.search(i)
        chiave = m.group(0) if m else (i.split() or [""])[-1]
        trovate = [k for k, w in enumerate(fascia) if k not in usate
                   and str(w[4]).strip().casefold() == chiave.casefold()]
        if not chiave or not trovate:
            return ruoli, intestazioni
        k = min(trovate, key=lambda k: fascia[k][0])
        usate.add(k)
        posizioni.append(fascia[k][0])
    ordine = sorted(range(len(ruoli)), key=lambda k: posizioni[k])
    return [ruoli[k] for k in ordine], [intestazioni[k] for k in ordine]


_TITOLO_SP = re.compile(r"^\s*stato\s+patrimoniale\s*(?:[-–]?\s*attivo)?\s*$", re.I | re.M)


def _pagine_di_apertura(pagine_sp: list[int], pagine_ce: list[int],
                        testi: dict[int, str]) -> tuple[list[int], list[int]]:
    """La pagina subito prima della prima pagina di una sezione, assegnata all'altra, che porta su
    una riga sua il titolo della sezione, e' anche una pagina di quella sezione: la sezione si
    apre li' (budget_1433/1434: «Conto economico», valore della produzione e ricavi in fondo alla
    pagina dello SP; la vision dava la pagina solo allo SP e i ricavi non li leggeva nessuno).
    Ciascuna lettura vede allora la pagina, e ``_per_sezione`` prende ogni lato dalla sua."""
    sp, ce = list(pagine_sp), list(pagine_ce)
    prima_ce, prima_sp = (min(ce) - 1, min(sp) - 1) if sp and ce else (None, None)
    if prima_ce in sp and prima_ce not in ce and _TITOLO_CE.search(testi.get(prima_ce, "")):
        ce = sorted(ce + [prima_ce])
    if prima_sp in ce and prima_sp not in sp and _TITOLO_SP.search(testi.get(prima_sp, "")):
        sp = sorted(sp + [prima_sp])
    return sp, ce


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
    if pagine_sp and pagine_ce:
        import fitz
        with fitz.open(pdf) as doc:
            testi = {n: doc[n - 1].get_text() for n in range(1, doc.page_count + 1)}
        pagine_sp, pagine_ce = _pagine_dai_titoli(pagine_sp, pagine_ce, testi)
        pagine_sp, pagine_ce = _pagine_di_apertura(pagine_sp, pagine_ce, testi)
    prospetti = set(pagine_sp) | set(pagine_ce)
    dettaglio = {m["pagina"] for m in mappe if m.get("tipo_pagina") == "dettaglio_conti"}
    dettaglio |= set(pagine_tabelle_nota(pdf))
    modo = modo_da_mappe(mappe, route_hint=route_hint, pdf=pdf)
    # Task 24: il modo "legge_con_dettaglio" si decide dal TESTO (didascalie di legge con importo e
    # righe-conto sotto), mai dal voto della vision, che qui resta un'indicazione: 4 schemi della
    # vision si collassavano in due modi e il "riclassificato con codici IVCEE" copriva due
    # documenti diversi.
    from importers.standard_ivcee_parser import riconosci_schema_con_dettaglio
    con_dettaglio = riconosci_schema_con_dettaglio(pdf) is not None
    if con_dettaglio:
        modo = "legge_con_dettaglio"
    # Stesso segnale che ha scelto "legge" sopra (Task 18, ruling c addendum): un
    # "riclassificato con codici IVCEE" che e' anche schema di legge coi totali stampati non
    # e' un piano dei conti piatto, e le sue pagine_dettaglio possono portare macro-voci
    # intere (owner, dopo la diagnosi AMBIENTA §7-8) - import_snello le include allora anche
    # nel prompt macro, non solo nel recupero dettaglio a valle.
    prospetti_mappe = [m for m in mappe if m.get("tipo_pagina") in TIPI_SP | TIPI_CE]
    macro_include_dettaglio = con_dettaglio or _riclassificato_con_captions_legali(prospetti_mappe, pdf)
    sp_col, ce_col = _colonne_di(mappe, TIPI_SP), _colonne_di(mappe, TIPI_CE)
    colonne_sp, intestazioni_sp = _colonne_vere(sp_col, ce_col)
    colonne_ce, intestazioni_ce = _colonne_vere(ce_col, sp_col)
    import fitz
    with fitz.open(pdf) as doc:
        def _parole(pagine):
            return doc[min(pagine) - 1].get_text("words") if pagine else []
        colonne_sp, intestazioni_sp = _ordina_colonne(colonne_sp, intestazioni_sp,
                                                      _parole(pagine_sp))
        colonne_ce, intestazioni_ce = _ordina_colonne(colonne_ce, intestazioni_ce,
                                                      _parole(pagine_ce))
    import fitz
    with fitz.open(pdf) as doc:
        pagine_senza_testo = [i + 1 for i, p in enumerate(doc) if not p.get_text().strip()]
    return Struttura(fonte=fonte, route=route, pagine_sp=pagine_sp, pagine_ce=pagine_ce,
                     pagine_dettaglio=sorted(dettaglio - prospetti), chiamate_vision=chiamate,
                     secondi=time.monotonic() - inizio, mappe=mappe, modo=modo,
                     colonne_sp=colonne_sp, colonne_ce=colonne_ce,
                     intestazioni_sp=intestazioni_sp, intestazioni_ce=intestazioni_ce,
                     pagine_senza_testo=pagine_senza_testo,
                     macro_include_dettaglio=macro_include_dettaglio)
