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
from dataclasses import dataclass, replace
from decimal import Decimal

from importers.lettore import tavola
from importers.lettore._ereditati import _CONNETTIVI, _scadenza as _scadenza_inizio, _scadenza_in_coda
from importers.lettore.righe import Documento, Riga
from importers.lettore.totali import (DICE_ATTIVO, DICE_PASSIVO, DICE_TOTALE, _CONTROLLO, _RISULTATO_DI_LEGGE,
                                      _RISULTATO, _RISULTATO_ESERCIZIO, _controllo_sotto, _costo_del_risultato, _norm, _risultato,
                                      _su_schema, _valore_di_somma, valore_nel_totale)
from importers.schema_etichette_parser import percorso as _percorso_etichetta

_ZERO = Decimal(0)
_RUOLI_VALORE = ("esercizio", "saldo")

# Un'etichetta fatta delle sole parole del risultato («Utile», «Perdita», «Utile (perdita)», «Risultato netto») e' il
# risultato anche senza «esercizio»: fra i costi a pareggio di un conto economico contrapposto non e' un costo
_RISULTATO_NUDO = re.compile(r"^\W*(?:utile|perdita|risultato)(?:\W+(?:utile|perdita|netto|netta|del|di|periodo))*\W*$")


def e_riga_del_risultato(etichetta: str) -> bool:
    """La riga del risultato d'esercizio: «Utile (perdita) dell'esercizio», o un'etichetta di sole parole del
    risultato («Utile»)."""
    n = _norm(etichetta)
    return bool(_RISULTATO_ESERCIZIO.search(n) or _RISULTATO_NUDO.match(n))

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
    mastri: tuple[str, ...] = ()  # i titoli sopra il conto, verificati o no (`Riga.percorso`, dalla sezione al
                                  # padre): il mastro di una catena di un solo conto non e' un antenato verificato ma
                                  # ne dice la natura. Solo contesto per il modello e per le regole di testo, mai importi

    @property
    def contesto(self) -> tuple[str, ...]:
        """I titoli sopra il conto per chi legge la natura: i mastri, o gli antenati verificati se mancano."""
        return self.mastri if len(self.mastri) >= len(self.antenati) else self.antenati


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

_ENUM_INIZIALE = re.compile(r"^(?:[a-e]|p)\)\s*")


def _nome(r: Riga) -> str:
    """L'etichetta normalizzata, senza l'enumeratore di sezione in testa («A) TOTALE STATO PATRIMONIALE - ATTIVO»)."""
    return _ENUM_INIZIALE.sub("", _norm(r.etichetta))


# Le parole che un totale generale puo' avere oltre a «totale» e al lato: se ne resta una, e' la voce di una macro
# («Totale attivo circolante»). Le parole che lo dicono totale e i lati stanno nel lessico C12 di totali.py.
_PAROLE_DEL_GENERALE = {"totale", "totali", "generale", "stato", "patrimoniale", "patrimoniali", "dell", "del", "e",
                        "patrimonio", "netto", "a", "pareggio"}


def _totale_generale(r: Riga) -> str | None:
    """«attivo» | «passivo» se la riga e' il totale generale di un lato dello stato patrimoniale (anche «A pareggio» di
    un lato fisico), altrimenti None."""
    n = _nome(r)
    if r.sezione != "SP" or not DICE_TOTALE.search(n):
        return None
    parole = re.findall(r"[a-z]+", n)
    attivo, passivo = bool(DICE_ATTIVO.search(n)), bool(DICE_PASSIVO.search(n))
    resto = [w for w in parole if w not in _PAROLE_DEL_GENERALE and not DICE_ATTIVO.search(w)
             and not DICE_PASSIVO.search(w)]
    if resto or (attivo and passivo and "netto" not in parole):
        return None
    if attivo and not passivo:
        return "attivo"
    if passivo:
        return "passivo"
    if "pareggio" in parole and r.lato in ("L", "R"):
        return "attivo" if r.lato == "L" else "passivo"
    return None


def _lato_del_titolo(r: Riga, gettoni: tuple[str, ...]) -> str | None:
    """«A» | «P» se la riga e' il titolo di un lato («STATO PATRIMONIALE ATTIVO», «Passivo»): breve, senza numerazione
    di legge e senza essere un totale."""
    n = _nome(r)
    if gettoni or len(n.split()) > 5 or DICE_TOTALE.search(n):
        return None
    attivo, passivo = bool(DICE_ATTIVO.search(n)), bool(DICE_PASSIVO.search(n))
    return "A" if attivo and not passivo else "P" if passivo and not attivo else None


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


# Art. 2425 c.c.: i numeri arabi di ogni lettera del conto economico. Un arabo fuori dalla sua lettera («5) da altri»
# sotto «C) 16) a)», la numerazione dei debitori nel prospetto reso da XBRL) non e' una voce di legge: e' un elenco
# dentro la voce, e prenderlo come livello manderebbe un provento finanziario fra gli altri ricavi (C.5 -> A.5).
_ARABI_DEL_CE = {"A": (1, 5), "B": (6, 14), "C": (15, 17), "D": (18, 19)}


def arabo_fuori_lettera(lettera: str | None, arabo: str) -> bool:
    """L'arabo non appartiene alla lettera del conto economico sopra di lui (A 1-5, B 6-14, C 15-17-bis, D 18-19).
    Imposte (20) e risultato (21) seguono le lettere senza una propria: valgono sotto qualunque lettera."""
    limiti = _ARABI_DEL_CE.get(lettera or "")
    m = re.match(r"\d+", arabo)
    return bool(limiti and m and int(m.group()) < 20 and not limiti[0] <= int(m.group()) <= limiti[1])


def _arabo_all_indietro(sezione: str, lettera: str | None, gettoni: tuple[str, ...]) -> bool:
    """Il solo arabo della riga sta prima dei numeri della sua lettera del CE («5) da altri» sotto C): e' un elenco
    dentro la voce e non entra nell'outline. Un arabo in avanti («6)» sotto A, quando l'intestazione «B)» manca)
    entra, e il percorso che ne viene, fuori dalla lettera, non si risolve (`percorso_valido`): decide il modello,
    mai la voce sbagliata dell'outline di prima (che manderebbe un costo fra i ricavi)."""
    if sezione != "CE" or len(gettoni) != 1 or _tipo(gettoni[0]) != 2:
        return False
    limiti = _ARABI_DEL_CE.get(lettera or "")
    m = re.match(r"\d+", gettoni[0])
    return bool(limiti and m and int(m.group()) < limiti[0])


def _titoli_di_lato_sui_due_lati(righe: list[Riga]) -> bool:
    """Due tabelle affiancate dello stato patrimoniale con un titolo «attivo» a sinistra e uno «passivo» a destra:
    sono le sezioni contrapposte che il profilo ha tipato male, non due tabelle diverse. Il flusso sequenziale non puo'
    decidere i lati quando i titoli li dicono gia'."""
    titoli = {(r.lato, _lato_del_titolo(r, gettoni_di_legge(r.etichetta, r.codice)))
              for r in righe if r.sezione == "SP" and r.lato in ("L", "R")}
    return ("L", "A") in titoli and ("R", "P") in titoli


def _romano_in_sequenza(r: Riga, livelli: list[str | None], prefisso: str | None) -> tuple[str, ...]:
    """«II. Crediti»: il romano col punto e' un livello dell'outline solo se e' un totale sotto una voce con lettera,
    fa salire il romano aperto (I, II, poi IV se III manca) e divide davvero quella voce nello schema di legge del
    lato («SPA.C.IV» si', «SPA.C.V» no); «V. ROSSI» fra i conti no."""
    m = _ROMANO_COL_PUNTO.match(r.etichetta)
    if not m or not r.totale or not livelli[0] or not prefisso or m["n"] not in _VALORE_ROMANO:
        return ()
    if _VALORE_ROMANO[m["n"]] <= _VALORE_ROMANO.get(livelli[1] or "", 0):
        return ()
    voce = f"{prefisso}.{livelli[0]}"
    figlio = _campo(f"{voce}.{m['n']}")
    return (m["n"],) if figlio is not None and figlio != _campo(voce) else ()


def _scorri(righe: list[Riga], contrapposto: bool = True) -> dict[str, _Posizione]:
    """Per ogni riga: il lato dello stato patrimoniale (L/R dal lato fisico; su una colonna unica dal titolo
    «attivo»/«passivo», dal totale dell'attivo, o dalla lettera maiuscola che riparte da A dopo la B), l'outline di
    legge corrente (l'ultimo enumeratore visto a ogni livello, per lato e sezione) e la scadenza dichiarata. Le righe
    prima della prima prova sono dell'attivo solo se la prova e' un passaggio al passivo; altrimenti restano senza
    lato. Due tabelle affiancate che non sono contrapposte (1426) non hanno L = attivo e R = passivo: ogni tabella e'
    una colonna unica. L'outline vale da solo: il percorso degli antenati del lettore non sempre porta il livello piu' alto."""
    if not contrapposto and _titoli_di_lato_sui_due_lati(righe):
        contrapposto = True     # il profilo non l'ha vista, ma i titoli dicono L = attivo e R = passivo
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

    for k_riga, r in enumerate(righe):
        n = _nome(r)
        chiave = (r.sezione, r.lato)
        livelli = outline.setdefault(chiave, [None] * 4)
        unico = r.lato == "U" or not contrapposto
        lato_qui = ({"L": "A", "R": "P"}.get(r.lato) if contrapposto and not unico else stato) \
            if r.sezione == "SP" else None
        gettoni = gettoni_di_legge(r.etichetta, r.codice) or _romano_in_sequenza(
            r, livelli, {"A": "SPA", "P": "SPP"}.get(lato_qui or ""))
        if r.sezione == "SP" and unico:
            titolo = _lato_del_titolo(r, gettoni)
            if titolo == "A" and stato != "A":
                stato = "A"
                prima_della_prova.clear()
                azzera()
            elif titolo == "P" and stato != "P":
                prima_della_prova.clear()
                stato = "P"
                azzera()
            elif gettoni and gettoni[0] == "A" and stato != "P" and livelli[0] in ("B", "C", "D"):
                passa_al_passivo()          # la lettera A che riparte dopo la B: comincia il passivo
                azzera()
        if _arabo_all_indietro(r.sezione, livelli[0], gettoni):
            gettoni = ()
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
            lato_sp = {"L": "A", "R": "P"}.get(r.lato, stato) if contrapposto else stato
        out[r.id] = _Posizione(lato_sp, tuple(g for g in livelli if g), scadenze.get(chiave))
        if r.totale and not gettoni and not _totale_generale(r) and not s_riga:
            # (una ripartizione «- entro esercizio successivo» divide la voce per scadenza, non la chiude)
            # un totale chiuso senza numerazione («Totale crediti») chiude la voce che porta il suo nome: sotto di lui
            # i livelli tornano a quelli del titolo, meno quello chiuso
            titolo = _titolo_del_totale(r, righe[:k_riga])
            base = list(out[titolo.id].livelli) if titolo is not None and titolo.id in out else [g for g in livelli if g]
            livelli[:] = [None] * 4
            for g in base[:-1]:
                livelli[_tipo(g)] = g
            scadenze[chiave] = None
        if r.sezione == "SP" and unico:
            if stato is None:
                prima_della_prova.append(r.id)
            if _totale_generale(r) == "attivo":
                if stato is None:
                    prima_della_prova.pop()
                    out[r.id] = _Posizione("A", out[r.id].livelli, out[r.id].scad)
                    passa_al_passivo()
                else:
                    stato = "P"
                azzera()
    return out


def _campo(p: str) -> str | None:
    return tavola.campo_da_percorso_legale(p)


def _lettera_significativa(base: str, lettera: str) -> bool:
    """La lettera divide davvero la voce `base` in sotto-voci: il resolver della legge la manda su un campo diverso
    da quello della voce (CE.B.9.a-e, CE.B.10.a-d). Sotto «1) verso clienti» (gia' sp06a) «a)» e' un conto."""
    figlio = _campo(f"{base}.{lettera}")
    return figlio is not None and figlio != _campo(base)


def _scadenza_significativa(base: str) -> bool:
    """La voce ha una ripartizione entro/oltre: E e O cadono su campi diversi (crediti, debiti, B.III.2)."""
    e, o = _campo(f"{base}.E"), _campo(f"{base}.O")
    return e is not None and o is not None and e != o


def percorso_valido(p: str) -> bool:
    """F3-9: un percorso di legge si assegna solo se e' ben formato nello schema che il codice conosce
    (`percorsi.campo_da_percorso`): livelli in ordine (capitale, romano, arabo, lettera) senza ripetizioni, voce che il
    resolver sa tradurre (cosi' un arabo senza il romano sopra, «SPA.C.1», cade), lettera solo dove divide la voce,
    scadenza solo dove la voce ha entro/oltre."""
    parti = p.split(".")
    if len(parti) < 2 or parti[0] not in ("SPA", "SPP", "CE"):
        return False
    livelli = parti[1:]
    scad = livelli[-1] if len(livelli) > 1 and livelli[-1] in ("E", "O") else None
    if scad:
        livelli = livelli[:-1]
    if not livelli or _campo(p) is None:
        return False
    tipi = [_tipo(g) for g in livelli]
    if any(b <= a for a, b in zip(tipi, tipi[1:])):
        return False
    if parti[0] == "CE" and tipi[0] == 0 and any(arabo_fuori_lettera(livelli[0], g) for g, t in zip(livelli, tipi) if t == 2):
        return False
    base = ".".join((parti[0], *livelli))
    if tipi[-1] == 3 and not _lettera_significativa(".".join((parti[0], *livelli[:-1])), livelli[-1]):
        return False
    return scad is None or _scadenza_significativa(base)


def _percorso(r: Riga, pos: _Posizione) -> tuple[str | None, str | None]:
    """(percorso di legge, campo) dall'outline della riga; (None, None) se il lato manca o il percorso non e' ben
    formato (F3-9: un percorso mancante costa una chiamata al modello, uno sbagliato una macro sbagliata). Una lettera
    che non divide la voce (F3-10: la ripartizione entro/oltre «a) … esigibili entro», un conto «a) Rossi» sotto
    «1) verso clienti») non e' un livello: si toglie e la foglia tiene il percorso della voce, che deve valere da solo."""
    prefisso = _prefisso(r, pos.lato_sp)
    if prefisso is None or not pos.livelli:
        return None, None
    livelli = list(pos.livelli)
    if len(livelli) > 1 and _tipo(livelli[-1]) == 3 \
            and not _lettera_significativa(".".join((prefisso, *livelli[:-1])), livelli[-1]):
        livelli.pop()
    p = ".".join((prefisso, *livelli, *((pos.scad,) if pos.scad else ())))
    if not percorso_valido(p):
        return None, None
    return p, _campo(p)


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
        if _risultato(padre, _su_schema(doc)) and _costo_del_risultato(r):
            v = -v        # il meno e' della somma: il costo e' positivo comunque sia stampato
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

def gettoni_di_legge(r_etichetta: str, codice: str = "") -> tuple[str, ...]:
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


# «- entro esercizio successivo», «- oltre l'esercizio successivo»: la ripartizione senza «esigibili» (Passepartout)
_SCADENZA_A_TRATTINO = re.compile(r"^\W*(entro|oltre)\s+(?:l\W?\s*)?esercizio\s+successivo\b", re.I)


def _scadenza(etichette: list[str]) -> str | None:
    for e in etichette:
        s = _scadenza_in_coda(e) or _scadenza_inizio(e)
        if s:
            return "E" if "entro" in s else "O"
        m = _SCADENZA_A_TRATTINO.match(e)
        if m:
            return "E" if m.group(1).lower() == "entro" else "O"
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


def _e_saldo(doc: Documento, r: Riga, colonna: int) -> bool:
    """La cella sta in una colonna di saldi (dare - avere, il testo della testata) di una tabella a lato unico, e il
    segno e' stampato: il documento ha dei saldi negativi, oppure la colonna porta la lettera D/A (1561: il saldo
    e' assoluto, la lettera D/A e' il segno). Un saldo che non e' mai negativo e senza lettera non dice il lato
    dal segno."""
    return (r.lato == "U" and any(c.indice == colonna and c.ruolo == "saldo" for c in doc.colonne)
            and (bool(doc.profilo.negativi & {"meno", "parentesi", "meno-finale", "meno-staccato", "meno-colonna"})
                 or colonna in doc.profilo.marcatori))


def _lato_dal_saldo(r: Riga, lato_sp: str | None, verso: str | None, v: Decimal) -> tuple[str | None, str | None, Decimal]:
    """In una colonna di saldi il segno e' la colonna: il dare (positivo) e' attivo o costo, l'avere (negativo)
    passivo o ricavo. Un lato o un verso gia' decisi dal documento (titolo, percorso di legge) restano; l'importo
    arriva col segno normale del suo lato. Senza lato ne' verso lo decide il segno (1566)."""
    if r.sezione == "SP":
        lato_sp = lato_sp or ("A" if v > 0 else "P")
        return lato_sp, verso, v if lato_sp == "A" else -v
    if r.sezione == "CE":
        verso = verso or ("costo" if v > 0 else "ricavo")
        return lato_sp, verso, v if verso == "costo" else -v
    return lato_sp, verso, v


def _generali_stampati(doc: Documento, colonna: int, righe: list[Riga]) -> dict[str, list[Riga]]:
    """Le righe che si dichiarano totale generale di un lato e hanno una cella su questa colonna."""
    gen: dict[str, list[Riga]] = {"attivo": [], "passivo": []}
    for r in righe:
        lato_gen = _totale_generale(r)
        c = _colonna_della_riga(doc, colonna, r) if lato_gen else None
        if lato_gen and c is not None and _cella(doc, r, c) is not None:
            gen[lato_gen].append(r)
    return gen


def _titoli_come_totali(doc: Documento, colonna: int, righe: list[Riga], per_id: dict[str, Riga],
                        gen: dict[str, list[Riga]]) -> dict[str, list[Riga]]:
    """Il titolo di un lato che porta il suo totale («STATO PATRIMONIALE ATTIVO» seguito dall'importo) vale come totale
    solo dove nessuna riga «Totale attivo» lo dice, il suo importo non e' zero e coincide con quello dell'altro lato,
    titolo o totale (attivo = passivo e' la prova stampata che e' un totale: senza, un titolo con un numero e' un
    titolo, 1426, 680; due zeri non provano nulla). Una riga che e' l'ancora non e' una foglia
    (`_senza_titoli_ancora`): ogni importo si conta una volta."""
    def valore(r: Riga, lato: str) -> Decimal | None:
        c = _colonna_della_riga(doc, colonna, r)
        if c is None or _cella(doc, r, c) is None:
            return None
        return _importo(doc, r, colonna, per_id, lato, None)

    cand_lato: dict[str, set[Decimal]] = {"attivo": set(), "passivo": set()}
    for chiave_lato, lato in (("attivo", "A"), ("passivo", "P")):
        for r in gen[chiave_lato]:
            v = valore(r, lato)
            if v is not None:
                cand_lato[chiave_lato].add(v)
    titoli: dict[str, list[tuple[Riga, Decimal]]] = {}
    for r in righe:
        lato_titolo = _lato_del_titolo(r, gettoni_di_legge(r.etichetta, r.codice)) if r.sezione == "SP" else None
        chiave = {"A": "attivo", "P": "passivo"}.get(lato_titolo or "")
        if chiave and not gen[chiave]:
            v = valore(r, lato_titolo)
            if v is not None and v != _ZERO:
                titoli.setdefault(chiave, []).append((r, v))
    out: dict[str, list[Riga]] = {}
    for chiave, voci in titoli.items():
        altro = "passivo" if chiave == "attivo" else "attivo"
        valori_altro = cand_lato[altro] | {v for _, v in titoli.get(altro, [])}
        out[chiave] = [r for r, v in voci if v in valori_altro]
    return out


def _senza_titoli_ancora(doc: Documento, colonna: int, foglie: list[Foglia]) -> list[Foglia]:
    """Un titolo di lato usato come ancora e' un totale stampato, non una foglia: contarlo accanto ai suoi conti
    mostrerebbe come doppio conteggio il divario fra l'ancora e la loro somma."""
    righe = doc.righe_del_prospetto()
    per_id = {r.id: r for r in righe}
    gen = _generali_stampati(doc, colonna, righe)
    usati = {r.id for rr in _titoli_come_totali(doc, colonna, righe, per_id, gen).values() for r in rr}
    return [f for f in foglie if f.id not in usati] if usati else foglie


def foglie_contabili(doc: Documento, colonna: int) -> list[Foglia]:
    return _costi_col_segno_normale(_senza_echi(doc, _senza_titoli_ancora(doc, colonna, _foglie_grezze(doc, colonna))))


_TOLLERANZA_ECO = Decimal("0.01")
# «I. Immobilizzazioni immateriali»: il romano col punto (e non la parentesi) e' un livello di legge per questo
# solo scopo; `gettoni_di_legge` non lo legge, e cambiarlo sposterebbe i percorsi di tutti i lettori
_ROMANO_COL_PUNTO = re.compile(r"^\s*(?P<n>[IVX]{1,4})\.\s+\S")
_VALORE_ROMANO = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10}


def _livello_aperto(livello: dict[int, int]) -> int | None:
    """Il livello dell'ultima riga di legge vista (None se nessuna)."""
    return livello[max(livello)] if livello else None


def _livelli_eco(righe: list[Riga]) -> dict[int, int]:
    """Indice di riga -> livello di legge (0-3), -1 il titolo di un lato."""
    livello: dict[int, int] = {}
    romano = 0                        # l'ultimo romano col punto accettato nella sequenza aperta
    for k, r in enumerate(righe):
        g = gettoni_di_legge(r.etichetta, r.codice)
        m = _ROMANO_COL_PUNTO.match(r.etichetta) if not g else None
        if g:
            livello[k] = _tipo(g[-1])
            if _tipo(g[-1]) == 0:
                romano = 0
        elif m and m["n"] in _VALORE_ROMANO and (
                _VALORE_ROMANO[m["n"]] == romano + 1 or (_VALORE_ROMANO[m["n"]] == 1 and _livello_aperto(livello) == 0)):
            # «V. ROSSI» fra i conti non e' un livello di legge: conta solo il romano che continua la sequenza
            # aperta (I, II, III...) o che comincia subito sotto una voce con lettera (B), C))
            livello[k] = 1
            romano = _VALORE_ROMANO[m["n"]]
        elif _lato_del_titolo(r, g) is not None:
            livello[k] = -1
    return livello


def _fine_finestra(righe: list[Riga], pos: dict[str, "_Posizione"], livello: dict[int, int], k: int) -> int:
    """L'indice dove finiscono i conti di una voce: la prossima voce di livello pari o piu' alto, un totale chiuso
    «Totale ...» o il cambio di lato o di sezione."""
    r = righe[k]
    for j in range(k + 1, len(righe)):
        q = righe[j]
        if q.sezione != r.sezione or q.lato != r.lato or pos[q.id].lato_sp != pos[r.id].lato_sp \
                or (q.totale and DICE_TOTALE.search(_nome(q))) \
                or (j in livello and 0 <= livello[j] <= livello[k]):
            return j
    return len(righe)


def _senza_echi(doc: Documento, foglie: list[Foglia]) -> list[Foglia]:
    """Toglie le voci che ripetono i propri conti. Una voce di legge (o il titolo di un lato) con un importo che nessun
    totale ha chiuso sembra una foglia, ma se i conti stampati sotto di lei (fino alla prossima voce dello stesso
    livello o piu' alto, a un totale chiuso «Totale ...» o al cambio di lato o di sezione; i totali chiusi delle sotto-voci,
    «Costo storico», stanno dentro la finestra: sono i conti stessi) sommano esattamente il suo importo, e' il loro riepilogo:
    contarla accanto a loro raddoppia la massa (1440: «I. Immobilizzazioni immateriali» sopra «7) Altre» di pari
    importo, e «B) Immobilizzazioni» sopra entrambe; 1426). Il caso piu' semplice e' la catena k=1 di uguale importo
    (R14): resta un'ipotesi, nessuna parentela nuova si registra, cambia solo che non si conta due volte. Si procede
    dalle voci piu' profonde: l'eco di un livello basso non entra nella somma di quello sopra. La somma si chiude al
    centesimo (come il reintegro dal testo): una tolleranza trasformerebbe il riepilogo in un conto qualunque."""
    if len(foglie) < 2:
        return foglie
    righe = doc.righe_del_prospetto()
    pos = _scorri(righe, doc.contrapposto)
    indice = {r.id: k for k, r in enumerate(righe)}
    livello = _livelli_eco(righe)
    aperte = [(indice[f.id], f) for f in foglie if indice.get(f.id) in livello]
    eco: set[str] = set()
    for k, f in sorted(aperte, key=lambda kf: (-livello[kf[0]], -kf[0])):
        r = righe[k]
        fine = _fine_finestra(righe, pos, livello, k)
        sotto = [g for g in foglie if k < indice.get(g.id, -1) < fine and g.id not in eco]
        if sotto and abs(sum((g.importo for g in sotto), _ZERO) - f.importo) <= _TOLLERANZA_ECO:
            eco.add(f.id)
    return [f for f in foglie if f.id not in eco]


def _chiude_su(doc: Documento, r: Riga, col: int, per_id: dict[str, Riga], ordine: dict[str, int]) -> bool:
    """La riga chiude dei conti sulla colonna `col`, quindi non e' una foglia: ha un gruppo su `col` (o sulla sua
    colonna dei parziali) che non contiene una riga di controllo stampata sotto di lei (`totali._controllo_sotto`:
    «B.I.3» che «somma» il «Totale B.I» stampato sotto, «C.16.d» = C.17 + «TOTALE C)» per caso). Un totale senza
    gruppo su `col` chiude se un suo gruppo di un'altra colonna ha figli con un importo su `col`; un gruppo il cui
    totale vale zero su quella colonna non prova niente (+x e -x sommano a zero dovunque: il conto «Imm. in corso» a
    zero nel precedente, «sopra» due conti di un'altra voce). Altrimenti la massa della riga non la conterebbe nessuno."""
    coppie = getattr(doc.profilo, "coppie", {})
    gruppi = [r.figli[k] for k in (col, coppie.get(col)) if k is not None and r.figli.get(k)]
    if gruppi:
        # un risultato del conto economico non e' mai un conto, anche quando la sua somma non prova nulla
        return any(not _controllo_sotto(r, [per_id[f] for f in g if f in per_id], ordine) for g in gruppi) \
            or (r.sezione == "CE" and bool(_RISULTATO.search(_norm(r.etichetta))))
    if not r.totale:
        return False
    if not r.figli:
        return True     # un totale senza figli in nessuna colonna resta com'era: non una foglia
    totale_di = {v: k for k, v in coppie.items()}     # colonna dei parziali -> la sua colonna dei totali
    for k, g in r.figli.items():
        proprio = r.celle.get(k) or r.celle.get(totale_di.get(k, -1))
        if proprio is None or not proprio.valore:
            continue
        for f in g:
            if f not in per_id:
                continue
            c = _colonna_della_riga(doc, col, per_id[f])
            cella = _cella(doc, per_id[f], c) if c is not None else None
            if cella is not None and cella.valore:
                return True
    return False


def _foglie_grezze(doc: Documento, colonna: int) -> list[Foglia]:
    dal_saldo = 0
    righe = doc.righe_del_prospetto()
    per_id = {r.id: r for r in righe}
    ordine = {r.id: k for k, r in enumerate(doc.righe)}
    pos = _scorri(righe, doc.contrapposto)
    perc = _Percorsi(righe, pos)
    out: list[Foglia] = []
    for r in righe:
        col = _colonna_della_riga(doc, colonna, r)
        if r.intestazione or col is None or _cella(doc, r, col) is None or _chiude_su(doc, r, col, per_id, ordine) \
                or _e_controllo(r):
            continue
        lato_sp = pos[r.id].lato_sp
        p, campo = _percorso(r, perc.posizione(r))
        verso = _verso_ce(r, campo)
        if verso is None and r.sezione == "CE" and r.lato == "U":
            cella = _cella(doc, r, col)
            verso = {"D": "costo", "A": "ricavo"}.get(cella.marcatore or "")
        v = _importo(doc, r, colonna, per_id, lato_sp, verso)
        if v is None or v == _ZERO:
            continue
        # in una colonna a marcatore D/A il lato o il verso gia' decisi (titolo, percorso, lettera di un conto del CE)
        # hanno gia' il segno di `_importo`: girarlo di nuovo lo rovescerebbe. Solo cio' che e' ancora ignoto si
        # decide dal segno
        decisa = verso if r.sezione == "CE" else lato_sp
        if _e_saldo(doc, r, col) and not (col in doc.profilo.marcatori and decisa):
            prima = (lato_sp, verso)
            lato_sp, verso, v = _lato_dal_saldo(r, lato_sp, verso, v)
            dal_saldo += (lato_sp, verso) != prima
        out.append(Foglia(r.id, r.etichetta, r.codice, r.lato, r.sezione, v, p, _antenati_verificati(r, per_id),
                          verso, lato_sp, tuple(r.percorso)))
    if dal_saldo:
        avviso = (f"{dal_saldo} righe hanno avuto il lato (attivo/passivo) o il verso (costo/ricavo) dal segno del "
                  f"saldo: titoli e percorso di legge non lo dicevano")
        if avviso not in doc.avvisi:
            doc.avvisi.append(avviso)
    return out


_MIN_COSTI_NEGATIVI = 5
_QUOTA_COSTI_NEGATIVI = 0.7


def _costi_stampati_negativi(foglie: list[Foglia]) -> bool:
    """Un conto economico che stampa i costi col meno (importi fra parentesi sul totale dei servizi) segue una convenzione
    del documento intero, non storna ogni conto. La prova e' la maggioranza: almeno cinque costi e almeno il 70% di
    loro negativo (i cinque documenti misurati sono tutti sopra il 95%; una percentuale piu' bassa e' un documento
    con storni, che resta com'e'). Un costo positivo dentro un documento sopra soglia e' lo storno."""
    costi = [f for f in foglie if f.sezione == "CE" and f.verso_ce == "costo"]
    negativi = sum(1 for f in costi if f.importo < _ZERO)
    return len(costi) >= _MIN_COSTI_NEGATIVI and negativi >= _QUOTA_COSTI_NEGATIVI * len(costi)


def _costi_col_segno_normale(foglie: list[Foglia]) -> list[Foglia]:
    """Se il documento stampa i costi col meno, i costi arrivano col segno normale positivo (F3-1); la cella resta lo
    stampato. Le ancore dei costi seguono la stessa regola (`ancore`), cosi' foglie e ancore concordano."""
    if not _costi_stampati_negativi(foglie):
        return foglie
    return [replace(f, importo=-f.importo) if f.sezione == "CE" and f.verso_ce == "costo" else f for f in foglie]


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


def _titolo_del_totale(t: Riga, sopra: list[Riga]) -> Riga | None:
    """La voce con enumeratore, sopra il totale (`sopra`: le righe che lo precedono), che ha il suo nome
    («Totale crediti» -> «II - Crediti»): prima quella con le stesse parole, poi quella che ne contiene o ne e'
    contenuta; la piu' vicina."""
    nome = _parole_nome(t)
    if not nome:
        return None
    sopra = [r for r in reversed(sopra) if r.lato == t.lato and r.sezione == t.sezione
             and gettoni_di_legge(r.etichetta, r.codice)]
    for ammesso in (lambda p: p == nome, lambda p: p and (p <= nome or nome <= p)):
        for r in sopra:
            if ammesso(_parole_nome(r)):
                return r
    return None


class _Percorsi:
    """Il percorso di legge di una riga. Prima la catena degli antenati VERIFICATI: eredita il percorso del padre
    verificato e lo affina col proprio enumeratore solo se la riga e' una voce di legge piu' profonda di lui (un
    «1) Rossi» sotto un padre che ha gia' un livello arabo e' un conto, non un livello). Solo la riga senza padre
    verificato ripiega sull'outline posizionale di `_scorri`."""

    def __init__(self, righe: list[Riga], pos: dict[str, _Posizione]):
        self.per_id = {r.id: r for r in righe}
        self.pos = pos
        self._memo: dict[str, tuple[tuple[str, ...], str | None, bool]] = {}

    def _livelli(self, r: Riga) -> tuple[tuple[str, ...], str | None, bool]:
        """(livelli, scadenza, ancorato): `ancorato` dice che la catena porta almeno un enumeratore di legge; un
        padre verificato senza alcun enumerator («Totale», una riga di soli importi) non e' un'autorita'."""
        if r.id in self._memo:
            return self._memo[r.id]
        self._memo[r.id] = ((), None, False)         # contro un ciclo
        if _totale_generale(r):
            # «A) TOTALE STATO PATRIMONIALE - ATTIVO»: la lettera numera il lato, non la voce A di legge; un totale
            # di sezione verificato sotto di lui («C) TOTALE ATTIVO CIRCOLANTE») non deve ereditarla
            return (), None, False
        posizionale = (self.pos[r.id].livelli, self.pos[r.id].scad)
        propri = gettoni_di_legge(r.etichetta, r.codice)
        padre = self.per_id.get(r.padre) if r.padre and r.padre_verificato else None
        base, scad, ancorato = self._livelli(padre) if padre is not None else ((), None, False)
        romano = _ROMANO_COL_PUNTO.match(r.etichetta) if not propri else None
        if romano and r.totale and ancorato and base and _tipo(base[-1]) == 0 and romano["n"] in _VALORE_ROMANO:
            # «II. Crediti» sotto «C) Attivo circolante», verificato dai suoi conti: il romano col punto e' un livello
            # quando e' un totale subito sotto una voce con lettera («V. ROSSI» fra i conti resta un conto)
            propri = (romano["n"],)
        slots: list[str | None] = [None] * 4
        for g in base if ancorato else ():
            slots[_tipo(g)] = g
        presenti = [i for i, g in enumerate(slots) if g]
        if _arabo_all_indietro(r.sezione, slots[0], propri):
            propri = ()         # un elenco dentro la voce, non un livello
        accettati = bool(propri) and (len(propri) > 1 or not presenti or _tipo(propri[0]) > max(presenti))
        if accettati and ancorato:
            if len(propri) > 1:
                slots = [None] * 4
            for g in propri:
                t = _tipo(g)
                slots[t] = g
                for j in range(t + 1, 4):
                    slots[j] = None
            propria = _scadenza([r.etichetta])
            res = (tuple(g for g in slots if g), propria, True)
        elif accettati:
            res = (*posizionale, True)               # la riga e' una voce di legge e nessun antenato lo e'
        elif ancorato:
            propria = _scadenza([r.etichetta])
            res = (base, propria or scad, True)      # un conto: eredita dall'antenato che ha un enumeratore
        else:
            res = (*posizionale, False)
        self._memo[r.id] = res
        return res

    def posizione(self, r: Riga) -> _Posizione:
        livelli, scad, _ = self._livelli(r)
        return _Posizione(self.pos[r.id].lato_sp, livelli, scad)


def _macro_del_totale(t: Riga, righe: list[Riga], perc: _Percorsi) -> tuple[str | None, bool]:
    """(macro-voce del totale, ambigua sulla scadenza). Dal proprio enumeratore; se il totale non ha un nome di
    legge («Totale crediti»), da quello della voce sopra che ne porta il nome."""
    candidati = [t] if gettoni_di_legge(t.etichetta, t.codice) else []
    titolo = _titolo_del_totale(t, righe[:righe.index(t)])
    if titolo is not None:
        candidati.append(titolo)
    for c in candidati:
        p = perc.posizione(c)
        _, campo = _percorso(t, _Posizione(perc.pos[t.id].lato_sp or p.lato_sp, p.livelli, p.scad))
        if campo:
            macro = tavola.macro_di(campo)
            if macro != campo:
                return None, False       # un dettaglio, non la macro-voce: l'importo non e' della macro
            return macro, macro in ("sp06", "sp07", "sp16", "sp17") and p.scad is None
    return None, False


def ancore(doc: Documento, colonna: int) -> list[Ancora]:
    righe = doc.righe_del_prospetto()
    per_id = {r.id: r for r in righe}
    ordine = {r.id: k for k, r in enumerate(doc.righe)}
    pos = _scorri(righe, doc.contrapposto)
    perc = _Percorsi(righe, pos)
    coppie = getattr(doc.profilo, "coppie", {})
    grezze = _senza_echi(doc, _senza_titoli_ancora(doc, colonna, _foglie_grezze(doc, colonna)))
    costi_negativi = _costi_stampati_negativi(grezze)
    tutte = _costi_col_segno_normale(grezze)
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
        if not (t.figli.get(c) or t.figli.get(coppie.get(c, -1))) or not _chiude_su(doc, t, c, per_id, ordine):
            continue
        macro, ambigua = _macro_del_totale(t, righe, perc)
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
            if costi_negativi and macro in _MACRO_COSTI and macro not in _MACRO_RICAVI:
                v = -v          # come le sue foglie (`_costi_col_segno_normale`)
            aggiungi(macro, v, t.id, sotto)

    # totali generali stampati: il totale chiuso se c'e', altrimenti l'ultima riga che si dichiara tale
    gen = _generali_stampati(doc, colonna, righe)
    for chiave_titolo, rr in _titoli_come_totali(doc, colonna, righe, per_id, gen).items():
        gen[chiave_titolo].extend(rr)
    for chiave, lista in gen.items():
        if not lista:
            continue
        r = ([x for x in lista if x.totale] or lista)[-1]
        lato = "A" if chiave == "attivo" else "P"
        v = _importo(doc, r, colonna, per_id, lato, None)
        if v is not None:
            aggiungi(chiave, v, r.id, tuple(f.id for f in tutte if f.lato_sp == lato))

    # risultato d'esercizio: il totale chiuso del conto economico, poi una sua riga, poi quello dello stato
    # patrimoniale (che e' una foglia del passivo); legato alle foglie che lo compongono se e' un totale
    cand = [r for r in righe if cella(r) is not None and r.sezione in ("CE", "SP")
            and e_riga_del_risultato(r.etichetta) and not _totale_generale(r)]
    cand.sort(key=lambda r: (r.sezione != "CE", not r.totale))
    if cand:
        r = cand[0]
        v = _importo(doc, r, colonna, per_id, "P" if r.sezione == "SP" else None,
                     "ricavo" if r.sezione == "CE" else None)
        if v is not None:
            n = _norm(r.etichetta)
            if "perdit" in n and "utile" not in n and v > 0:
                v = -v
            c = col(r)
            aggiungi("utile", v, r.id, _sotto(r, per_id, ids, c, coppie) if r.totale and c is not None else ())
    return out


def senza_colonna(doc: Documento, colonna: int) -> tuple[str, ...]:
    """Gli id delle righe con importi che non hanno una colonna equivalente a `colonna` (contrapposte: l'altro lato
    non stampa quella colonna). Non sono foglie ne' ancore: si dichiarano, mai si perdono in silenzio."""
    return tuple(r.id for r in doc.righe_del_prospetto()
                 if r.celle and _colonna_della_riga(doc, colonna, r) is None)
