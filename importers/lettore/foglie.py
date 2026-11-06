"""Le foglie contate una volta e le ancore stampate, per colonna (Fase 3, Task 2).

Una foglia e' una riga di prospetto che non e' un totale e porta un importo sulla colonna: un mastro coi figli
verificati non e' mai foglia, quindi la somma delle foglie conta ogni importo una volta. Un'ancora e' un importo che
il documento stampa e che le foglie devono rifare: un totale chiuso che si risolve a una macro-voce, oppure il
totale generale dell'attivo/passivo e il risultato d'esercizio.

Il lettore non classifica: qui il percorso di legge viene composto dalle etichette (la voce, poi gli antenati) e
risolto dalla tavola; il lato e il verso dei conti vengono dalla colonna e dalla sezione, mai dalla descrizione.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from importers.lettore import tavola
from importers.lettore._ereditati import _CONNETTIVI, _scadenza as _scadenza_inizio, _scadenza_in_coda
from importers.lettore.righe import Documento, Riga
from importers.lettore.totali import (DICE_TOTALE, _CONTROLLO, _RISULTATO_DI_LEGGE, _costo_del_risultato, _norm, _risultato,
                                      _su_schema, _valore_di_somma, valore_nel_totale)
from importers.schema_etichette_parser import percorso as _percorso_etichetta

_ZERO = Decimal(0)
_RUOLI_VALORE = ("esercizio", "saldo")

# L'enumeratore di una voce di legge stampato come titolo: «C)», «II -», «1)», «5-bis)», «c)». Il maiuscolo A-E
# vuole la parentesi e il romano la parentesi o il trattino, cosi' «A. Rossi s.r.l.» e «I.V.A.» non sono voci.
_ENUMERATORE = re.compile(
    r"^\s*(?:(?P<lettera>[A-E])\)|(?P<romano>[IVX]{1,4})(?:\)|\s+[-–]\s)"
    r"|(?P<arabo>\d{1,2})(?:\s?-\s?(?P<suffisso>(?i:bis|ter|quater)))?\)|(?P<minuscola>[a-z])\))")
# Il percorso di legge intero in testa all'etichetta, senza parentesi: «B.II.3 Attrezzature», «A.1 Ricavi», «B.9.a Salari»
_PERCORSO_NUDO = re.compile(r"^\s*([A-E](?:\.(?:[IVX]{1,4}|\d{1,2}(?:-(?:bis|ter|quater))?|[a-z]))+)(?=\s|$)")
_CODICE_DI_LEGGE = re.compile(r"^[A-E](?:\.(?:[IVX]{1,4}|\d{1,2}(?:-bis|-ter|-quater)?|[a-z]))*$")


@dataclass(frozen=True)
class Foglia:
    id: str
    etichetta: str
    codice: str
    lato: str                    # il lato fisico della riga: "U" | "L" | "R"
    sezione: str                 # "SP" | "CE" | ""
    importo: Decimal             # col segno normale per il suo lato: positivo = saldo naturale (F3-1)
    percorso_legale: str | None  # dal proprio codice/etichetta o dal primo antenato che ne ha uno
    antenati: tuple[str, ...]    # etichette degli antenati verificati, per il prompt
    verso_ce: str | None = None  # "costo" | "ricavo" | None se ignoto (F3-2)
    lato_sp: str | None = None   # "A" | "P" | None se ignoto (F3-7)


@dataclass(frozen=True)
class Ancora:
    chiave: str                  # un campo macro ("sp06", "ce08"), oppure "attivo" | "passivo" | "utile"
    importo: Decimal
    riga: str
    foglie: tuple[str, ...]      # id delle foglie sotto l'ancora


# --------------------------------------------------------------------------------------
# Colonne
# --------------------------------------------------------------------------------------

def colonne_utili(doc: Documento) -> tuple[int | None, int | None]:
    """(corrente, precedente) fra le colonne di esercizio o di saldo; differenze e percentuali mai."""
    valori = [c for c in doc.colonne if c.ruolo in _RUOLI_VALORE]
    if any(c.lato == "L" for c in valori):     # contrapposte: le colonne di riferimento sono quelle di sinistra,
        valori = [c for c in valori if c.lato == "L"]   # quelle di destra si leggono con `_colonna_della_riga`
    if not valori:
        return None, None
    corrente = next((c for c in valori if c.corrente), valori[0])
    altre = [c for c in valori if c is not corrente and c.ruolo == "esercizio"]
    if not altre:
        return corrente.indice, None
    prima = [c for c in altre if c.fine and corrente.fine and c.fine < corrente.fine]
    precedente = max(prima, key=lambda c: c.fine) if prima else altre[0]
    return corrente.indice, precedente.indice


# --------------------------------------------------------------------------------------
# Lato, verso, segno
# --------------------------------------------------------------------------------------

_ATTIVO = re.compile(r"^(?:stato patrimoniale\s*[-:]?\s*)?(?:a\)\s*)?attivo\b|^attivita\b")
_PASSIVO = re.compile(r"^(?:stato patrimoniale\s*[-:]?\s*)?(?:passivo\b|passivita\b|patrimonio netto e passivo)")
_TOTALE_ATTIVO = re.compile(r"^totale\s+(?:generale\s+)?(?:stato patrimoniale\s*[-\u2013]?\s*)?(?:dell\W?\s*)?(?:attivo|attivita\W?)"
                            r"(?:\s+patrimonial[ei])?\s*(?:\([^)]*\))?[\s:.]*$")
_TOTALE_PASSIVO = re.compile(r"^totale\s+(?:generale\s+)?(?:stato patrimoniale\s*[-\u2013]?\s*)?(?:del\s+)?(?:passivo|passivita\W?)"
                             r"(?:\s+(?:e\s+)?(?:patrimonio\s+netto|netto))?\s*(?:\([^)]*\))?[\s:.]*$")
_PAREGGIO = re.compile(r"^(?:totale\s+)?(?:a\s+)?pareggio\b")
_ENUM_INIZIALE = re.compile(r"^(?:[a-e]|p)\)\s*")


def _nome(r: Riga) -> str:
    """L'etichetta normalizzata, senza l'enumeratore di sezione in testa («A) TOTALE STATO PATRIMONIALE - ATTIVO»)."""
    return _ENUM_INIZIALE.sub("", _norm(r.etichetta))


_UTILE = re.compile(r"\b(?:utile|perdit[ae])\b.*\besercizio\b|^risultato (?:d\W?\s*)?esercizio\b|^21\)")


@dataclass(frozen=True)
class _Posizione:
    lato_sp: str | None          # "A" | "P" | None
    livelli: tuple[str, ...]     # l'outline di legge a questa riga: capitale, romano, arabo, lettera
    scad: str | None             # "E" | "O" | None


_TIPO_ROMANO = re.compile(r"^[IVX]{1,4}$")
_TIPO_ARABO = re.compile(r"^\d{1,2}(?:-(?:bis|ter|quater))?$")


def _tipo(gettone: str) -> int:
    """0 capitale A-E, 1 romano, 2 arabo, 3 lettera minuscola: il livello dell'outline di legge."""
    if _TIPO_ARABO.match(gettone):
        return 2
    if _TIPO_ROMANO.match(gettone):
        return 1
    return 0 if gettone.isupper() else 3


def _scorri(righe: list[Riga]) -> dict[str, _Posizione]:
    """Per ogni riga: il lato dello stato patrimoniale (L/R dal lato fisico; su una colonna unica dal titolo
    «attivo»/«passivo», dal totale dell'attivo, o dalla lettera maiuscola che riparte da A dopo la B), l'outline di
    legge corrente (l'ultimo enumeratore visto a ogni livello, per lato e sezione) e la scadenza dichiarata. Le righe
    prima della prima prova sono dell'attivo solo se la prova e' un passaggio al passivo; altrimenti restano senza
    lato. L'outline vale da solo: il percorso degli antenati del lettore non sempre porta il livello piu' alto."""
    out: dict[str, _Posizione] = {}
    stato: str | None = None
    prima_della_prova: list[str] = []
    outline: dict[tuple[str, str], list[str | None]] = {}
    scadenze: dict[tuple[str, str], str | None] = {}

    def azzera() -> None:
        for k in [k for k in outline if k[0] == "SP"]:
            outline[k], scadenze[k] = [None] * 4, None

    def passa_al_passivo() -> None:
        nonlocal stato
        if stato is None:
            for i in prima_della_prova:
                out[i] = _Posizione("A", out[i].livelli, out[i].scad)
        prima_della_prova.clear()
        stato = "P"

    for r in righe:
        n = _nome(r)
        chiave = (r.sezione, r.lato)
        livelli = outline.setdefault(chiave, [None] * 4)
        gettoni = _gettoni(r.etichetta, r.codice)
        if r.sezione == "SP" and r.lato == "U":
            titolo = len(n.split()) <= 6 and not n.startswith("totale")
            if titolo and _ATTIVO.search(n) and stato != "A":
                stato = "A"
                prima_della_prova.clear()
                azzera()
            elif titolo and _PASSIVO.search(n) and stato != "P":
                prima_della_prova.clear()
                stato = "P"
                azzera()
            elif gettoni and gettoni[0] == "A" and stato != "P" and livelli[0] in ("B", "C", "D"):
                passa_al_passivo()          # la lettera A che riparte dopo la B: comincia il passivo
                azzera()
        for g in gettoni:
            t = _tipo(g)
            livelli[t] = g
            for j in range(t + 1, 4):
                livelli[j] = None
        s_riga = _scadenza([r.etichetta])
        if gettoni or s_riga:
            scadenze[chiave] = s_riga
        lato_sp = None
        if r.sezione == "SP":
            lato_sp = {"L": "A", "R": "P"}.get(r.lato, stato)
        out[r.id] = _Posizione(lato_sp, tuple(g for g in livelli if g), scadenze.get(chiave))
        if r.sezione == "SP" and r.lato == "U":
            if stato is None:
                prima_della_prova.append(r.id)
            if _TOTALE_ATTIVO.search(n):
                if stato is None:
                    prima_della_prova.pop()
                    out[r.id] = _Posizione("A", out[r.id].livelli, out[r.id].scad)
                    passa_al_passivo()
                else:
                    stato = "P"
                azzera()
    return out


def _percorso(r: Riga, pos: _Posizione) -> tuple[str | None, str | None]:
    """(percorso di legge, campo) dall'outline della riga; None se il lato o la tavola non lo risolvono."""
    prefisso = _prefisso(r, pos.lato_sp)
    if prefisso is None or not pos.livelli:
        return None, None
    p = ".".join((prefisso, *pos.livelli, *((pos.scad,) if pos.scad else ())))
    return p, tavola.campo_da_percorso_legale(p)


def _colonna_della_riga(doc: Documento, colonna: int, r: Riga) -> int | None:
    """Sulle contrapposte attivo e passivo hanno ciascuno le proprie colonne: la colonna `colonna` di un lato si
    legge, per una riga dell'altro lato, nella colonna che ha lo stesso posto (corrente con corrente, poi in ordine)."""
    base = next((c for c in doc.colonne if c.indice == colonna), None)
    if base is None or r.lato not in ("L", "R") or base.lato not in ("L", "R") or r.lato == base.lato:
        return colonna
    proprie = [c for c in doc.colonne if c.ruolo in _RUOLI_VALORE and c.lato == base.lato]
    altre = [c for c in doc.colonne if c.ruolo in _RUOLI_VALORE and c.lato == r.lato]
    if base.corrente:
        scelta = [c for c in altre if c.corrente]
    else:
        scelta = [c for c in altre if not c.corrente]
        scelta = scelta[[c for c in proprie if not c.corrente].index(base):][:1] if base in proprie else scelta[:1]
    return scelta[0].indice if scelta else None


def _cella(doc: Documento, r: Riga, colonna: int):
    """La cella della riga sulla colonna; per un conto di una coppia parziali/totali, quella dei parziali."""
    c = r.celle.get(colonna)
    if c is None:
        c = r.celle.get(getattr(doc.profilo, "coppie", {}).get(colonna, -1))
    return c


def _chiave_figli(doc: Documento, padre: Riga, r: Riga, colonna: int) -> int | None:
    coppie = getattr(doc.profilo, "coppie", {})
    for k in (colonna, coppie.get(colonna)):
        if k is not None and r.id in padre.figli.get(k, ()):
            return k
    return None


def _importo(doc: Documento, r: Riga, colonna: int, per_id: dict[str, Riga], lato_sp: str | None,
             verso_ce: str | None) -> Decimal | None:
    """Il valore della cella col segno normale per il suo lato (F3-1). Con un padre verificato si usa il valore che
    la riga porta nella somma del padre (poste rettificative, versi rovesciati), tranne il costo dentro un
    risultato, che resta positivo: il segno meno e' della somma, non del conto."""
    colonna = _colonna_della_riga(doc, colonna, r)
    cella = _cella(doc, r, colonna) if colonna is not None else None
    if cella is None or cella.forma == "percentuale":
        return None
    padre = per_id.get(r.padre) if r.padre and r.padre_verificato else None
    chiave = _chiave_figli(doc, padre, r, colonna) if padre is not None else None
    if padre is not None and chiave is not None:
        v = valore_nel_totale(doc, padre, r, chiave)
        if _risultato(padre, _su_schema(doc)) and _costo_del_risultato(r) and _valore_di_somma(r, chiave) > 0:
            v = -v
        rovesciato = padre.verso.get(chiave, 1) == -1
    else:
        v = cella.valore
        rovesciato = False
    # colonna unica con marcatore D/A: il saldo in dare e' positivo, quindi un passivo o un ricavo col marcatore A
    # arriva negativo; il verso rovesciato del padre l'ha gia' girato.
    if r.lato == "U" and cella.marcatore is not None and not rovesciato and (lato_sp == "P" or verso_ce == "ricavo"):
        v = -v
    return v


_MACRO_RICAVI = set(tavola.MACRO_RICAVI)
_MACRO_COSTI = set(tavola.MACRO_COSTI)


def _verso_ce(r: Riga, campo: str | None) -> str | None:
    if r.sezione != "CE":
        return None
    if r.lato == "L":
        return "costo"
    if r.lato == "R":
        return "ricavo"
    if campo:
        m = tavola.macro_di(campo)
        if m in _MACRO_RICAVI and m not in _MACRO_COSTI:
            return "ricavo"
        if m in _MACRO_COSTI and m not in _MACRO_RICAVI:
            return "costo"
    return None


# --------------------------------------------------------------------------------------
# Percorso di legge
# --------------------------------------------------------------------------------------

def _gettoni(r_etichetta: str, codice: str = "") -> tuple[str, ...]:
    """I livelli di legge che una riga stampa nel proprio codice o nella propria etichetta."""
    if codice and _CODICE_DI_LEGGE.match(codice):
        t = _percorso_etichetta(codice + ") x")
        if t:
            return t
    nudo = _PERCORSO_NUDO.match(r_etichetta)
    if nudo:
        return tuple(nudo.group(1).split("."))
    t = _percorso_etichetta(r_etichetta)
    if t and (len(t) > 1 or _ENUMERATORE.match(r_etichetta)):
        return t
    m = _ENUMERATORE.match(r_etichetta)
    if not m:
        return ()
    if m["lettera"]:
        return (m["lettera"].upper(),)
    if m["romano"]:
        return (m["romano"].upper(),)
    if m["arabo"]:
        return (m["arabo"] + (f"-{m['suffisso'].lower()}" if m["suffisso"] else ""),)
    return (m["minuscola"],)


def _scadenza(etichette: list[str]) -> str | None:
    for e in etichette:
        s = _scadenza_in_coda(e) or _scadenza_inizio(e)
        if s:
            return "E" if "entro" in s else "O"
    return None


def _prefisso(r: Riga, lato_sp: str | None) -> str | None:
    if r.sezione == "CE":
        return "CE"
    if r.sezione == "SP":
        return {"A": "SPA", "P": "SPP"}.get(lato_sp or "")
    return None


# --------------------------------------------------------------------------------------
# Foglie
# --------------------------------------------------------------------------------------

def _antenati_verificati(r: Riga, per_id: dict[str, Riga]) -> tuple[str, ...]:
    out: list[str] = []
    corrente = r
    while corrente.padre and corrente.padre_verificato and corrente.padre in per_id:
        corrente = per_id[corrente.padre]
        out.append(corrente.etichetta)
    return tuple(reversed(out))


_DI_CUI = re.compile(r"^[-\u2013\s]*\(?di cui\b")


def _e_controllo(r: Riga) -> bool:
    """Una riga che chiude o pareggia, non una voce: «Totale…», «A pareggio», e nel conto economico il risultato.
    Anche «di cui esigibili oltre…»: e' un sottoinsieme della voce sopra, contarlo sarebbe contarla due volte."""
    n = _norm(r.etichetta)
    if _DI_CUI.search(n) or (not n and not r.codice):     # «di cui…», o un sottototale di soli importi
        return True
    if DICE_TOTALE.search(n):
        return True
    if r.sezione == "":     # sezione non riconosciuta (il conto economico oltre la pagina): solo il lessico di legge
        return bool(_RISULTATO_DI_LEGGE.search(n) or _CONTROLLO.search(n) and "utile" not in n and "perdit" not in n)
    return r.sezione == "CE" and bool(_CONTROLLO.search(n) or _risultato(r))


def foglie_contabili(doc: Documento, colonna: int) -> list[Foglia]:
    righe = doc.righe_del_prospetto()
    per_id = {r.id: r for r in righe}
    pos = _scorri(righe)
    out: list[Foglia] = []
    for r in righe:
        col = _colonna_della_riga(doc, colonna, r)
        if r.totale or r.intestazione or col is None or _cella(doc, r, col) is None or r.figli.get(col) \
                or _e_controllo(r):
            continue
        lato_sp = pos[r.id].lato_sp
        p, campo = _percorso(r, pos[r.id])
        verso = _verso_ce(r, campo)
        if verso is None and r.sezione == "CE" and r.lato == "U":
            cella = _cella(doc, r, col)
            verso = {"D": "costo", "A": "ricavo"}.get(cella.marcatore or "")
        v = _importo(doc, r, colonna, per_id, lato_sp, verso)
        if v is None or v == _ZERO:
            continue
        out.append(Foglia(r.id, r.etichetta, r.codice, r.lato, r.sezione, v, p, _antenati_verificati(r, per_id),
                          verso, lato_sp))
    return out


# --------------------------------------------------------------------------------------
# Ancore
# --------------------------------------------------------------------------------------

def _sotto(r: Riga, per_id: dict[str, Riga], ids: set[str], colonna: int, coppie: dict[int, int]) -> tuple[str, ...]:
    """Gli id delle foglie sotto un totale, scendendo per i figli verificati."""
    out: list[str] = []
    visti: set[str] = set()

    def scendi(t: Riga) -> None:
        for k in (colonna, coppie.get(colonna)):
            for f in t.figli.get(k, ()) if k is not None else ():
                if f in visti or f not in per_id:
                    continue
                visti.add(f)
                if f in ids:
                    out.append(f)
                elif per_id[f].totale:
                    scendi(per_id[f])

    scendi(r)
    return tuple(out)


_STOP = {"totale", "totali"} | _CONNETTIVI


def _parole_nome(r: Riga) -> frozenset[str]:
    """Le parole del nome di una voce, senza enumeratori, connettivi e lessico dei totali."""
    return frozenset(t for t in re.split(r"[^0-9a-z]+", _norm(r.etichetta))
                     if len(t) > 1 and t not in _STOP and not _TIPO_ROMANO.match(t.upper()) and not t.isdigit())


def _titolo_del_totale(t: Riga, righe: list[Riga]) -> Riga | None:
    """La voce con enumeratore, sopra il totale, che ha il suo nome («Totale crediti» -> «II - Crediti»): prima
    quella con le stesse parole, poi quella che ne contiene o ne e' contenuta; la piu' vicina."""
    nome = _parole_nome(t)
    if not nome:
        return None
    sopra = [r for r in reversed(righe[:righe.index(t)]) if r.lato == t.lato and r.sezione == t.sezione
             and _gettoni(r.etichetta, r.codice)]
    for ammesso in (lambda p: p == nome, lambda p: p and (p <= nome or nome <= p)):
        for r in sopra:
            if ammesso(_parole_nome(r)):
                return r
    return None


def _macro_del_totale(t: Riga, righe: list[Riga], pos: dict[str, _Posizione]) -> tuple[str | None, bool]:
    """(macro-voce del totale, ambigua sulla scadenza). Dal proprio enumeratore; se il totale non ha un nome di
    legge («Totale crediti»), da quello della voce sopra che ne porta il nome."""
    candidati = [t] if _gettoni(t.etichetta, t.codice) else []
    titolo = _titolo_del_totale(t, righe)
    if titolo is not None:
        candidati.append(titolo)
    for c in candidati:
        p = pos[c.id]
        _, campo = _percorso(t, _Posizione(pos[t.id].lato_sp or p.lato_sp, p.livelli, p.scad))
        if campo:
            macro = tavola.macro_di(campo)
            if macro != campo:
                return None, False       # un dettaglio, non la macro-voce: l'importo non e' della macro
            return macro, macro in ("sp06", "sp07", "sp16", "sp17") and p.scad is None
    return None, False


def ancore(doc: Documento, colonna: int) -> list[Ancora]:
    righe = doc.righe_del_prospetto()
    per_id = {r.id: r for r in righe}
    pos = _scorri(righe)
    coppie = getattr(doc.profilo, "coppie", {})
    tutte = foglie_contabili(doc, colonna)
    ids = {f.id for f in tutte}
    per_foglia = {f.id: f for f in tutte}
    out: list[Ancora] = []
    visti: set[tuple[str, Decimal]] = set()

    def aggiungi(chiave: str, importo: Decimal, riga: str, foglie: tuple[str, ...]) -> None:
        if (chiave, importo) not in visti:
            visti.add((chiave, importo))
            out.append(Ancora(chiave, importo, riga, foglie))

    def col(r: Riga) -> int | None:
        return _colonna_della_riga(doc, colonna, r)

    def cella(r: Riga):
        c = col(r)
        return None if c is None else _cella(doc, r, c)

    # macro-voci: solo da un totale chiuso su questa colonna
    for t in righe:
        c = col(t)
        if not t.totale or c is None or cella(t) is None or _e_controllo(t) and not _parole_nome(t):
            continue
        if not (t.figli.get(c) or t.figli.get(coppie.get(c, -1))):
            continue
        macro, ambigua = _macro_del_totale(t, righe, pos)
        if macro is None:
            continue
        sotto = _sotto(t, per_id, ids, c, coppie)
        macro_foglie = {tavola.macro_di(m) for f in sotto if per_foglia[f].percorso_legale
                        and (m := tavola.campo_da_percorso_legale(per_foglia[f].percorso_legale))}
        if ambigua:
            if len(macro_foglie) != 1:
                continue
            macro = next(iter(macro_foglie))
        elif macro_foglie - {macro}:
            continue                    # una foglia sotto il totale si risolve altrove: il totale non e' questa macro
        v = _importo(doc, t, colonna, per_id, pos[t.id].lato_sp, _verso_ce(t, macro))
        if v is not None:
            aggiungi(macro, v, t.id, sotto)

    # totali generali stampati
    gen: dict[str, Riga] = {}
    for r in righe:
        if r.sezione != "SP" or cella(r) is None:
            continue
        n = _nome(r)
        if _TOTALE_ATTIVO.search(n):
            gen["attivo"] = r
        elif _TOTALE_PASSIVO.search(n):
            gen["passivo"] = r
        elif _PAREGGIO.search(n) and r.lato in ("L", "R"):
            gen["attivo" if r.lato == "L" else "passivo"] = r
    for chiave, r in gen.items():
        lato = "A" if chiave == "attivo" else "P"
        v = _importo(doc, r, colonna, per_id, lato, None)
        if v is not None:
            aggiungi(chiave, v, r.id, tuple(f.id for f in tutte if f.lato_sp == lato))

    # risultato d'esercizio: quello del conto economico, se manca quello dello stato patrimoniale
    cand = [r for r in righe if cella(r) is not None and r.sezione in ("CE", "SP")
            and _UTILE.search(_norm(r.etichetta)) and not _TOTALE_ATTIVO.search(_norm(r.etichetta))
            and not r.totale]
    cand.sort(key=lambda r: r.sezione != "CE")
    if cand:
        r = cand[0]
        v = cella(r).valore
        n = _norm(r.etichetta)
        if "perdit" in n and "utile" not in n and v > 0:
            v = -v
        aggiungi("utile", v, r.id, ())
    return out
