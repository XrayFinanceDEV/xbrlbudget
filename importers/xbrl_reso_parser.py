"""Lettore deterministico del PDF reso dal bilancio XBRL depositato (Task 25).

Il documento piu' standard che esista: ogni pagina porta il piede "Generato automaticamente -
Conforme alla tassonomia itcc-ci-AAAA-MM-GG" e i prospetti (art. 2424/2425 c.c.) escono come un
elenco di righe, una per didascalia, con un importo per anno. Nessun modello, nessuna geometria
da indovinare: ogni riga e' un blocco del testo, la didascalia e' la prima riga, gli importi
sono le righe che seguono (uno per colonna-anno, ``-`` e' uno zero nella SUA colonna).

Regole (CLAUDE.md, «Invarianti e trappole»):

* il percorso di legge di una voce viene dagli enumeratori STAMPATI (``B)``, ``II -``, ``4)``,
  ``a)``) e dal contesto del prospetto, mai da un prefisso di codice: qui non esistono codici
  conto. La traduzione percorso -> campo e' quella dell'importatore snello
  (``import_snello.percorsi.campo_da_percorso``), riusata cosi' com'e';
* il TOTALE STAMPATO decide: una riga di raggruppamento (``a), b), c) ammortamento ...``) e i suoi
  componenti non si sommano mai entrambi; ogni ``Totale ...`` chiude l'ultimo gruppo aperto e
  deve ritrovarsi al centesimo nella somma delle righe che gli stanno sotto;
* autoverifica al centesimo, nessuna tolleranza, nessun tappo: se un solo controllo fallisce il
  candidato e' RIFIUTATO e il controllo e' nominato (``rifiuto``); non si inventa nulla che il
  documento non stampi;
* una didascalia non riconosciuta va nel sotto-campo esplicito della propria sezione (``sp06g``,
  ``sp16g``, ``ce04``, ``ce06``) ed e' contata in ``_unclassified_mass``; mai su un aggregato,
  mai su un campo TIER0. Dove non c'e' un secchio neutro il candidato e' rifiutato;
* le chiavi diagnostiche (``_unclassified_mass``, ``_plug_residual``) sono sempre dichiarate,
  anche a zero.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

import fitz

_C = Decimal("0.01")
_ZERO = Decimal(0)

_PIEDE = re.compile(r"Conforme alla tassonomia itcc-ci-\d{4}-\d{2}-\d{2}")
_IMPORTO = re.compile(r"^-?\(?\d{1,3}(?:\.\d{3})*\)?(?:\s+\(\d{1,2}\))?$|^-$")
_RE_NOTA_PIEDE = re.compile(r"^\(\d{1,2}\)$")
_DATA = re.compile(r"^\d{2}-\d{2}-(\d{4})$")
_ENUM_ARABO = r"\d+(?:-bis|-ter|-quater)?"
_ENUM_LETTERA = r"[a-z](?:-bis|-ter)?"
_RE_CAPITALE = re.compile(r"^([A-E])\)\s")
_RE_ROMANO = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)\s-\s")
_RE_ARABO = re.compile(rf"^({_ENUM_ARABO})\)\s")
_RE_LETTERA = re.compile(rf"^({_ENUM_LETTERA})\)\s")
_RE_GRUPPO = re.compile(
    rf"^((?:(?:{_ENUM_ARABO}|{_ENUM_LETTERA})\),\s*)+(?:{_ENUM_ARABO}|{_ENUM_LETTERA})\))\s")
_RE_CHIAVE = re.compile(rf"({_ENUM_ARABO}|{_ENUM_LETTERA})\)")
_LIVELLO = {"L": 1, "R": 2, "N": 3, "l": 4}
_SEGNO_NEGATIVO = ("CE.C.17", "CE.D.19")

# Sezioni in cui una riga SENZA enumeratore eredita la voce del padre (le righe "aperte" della
# tassonomia: ogni riserva, ogni altro ricavo, ogni genere di imposta). Altrove una riga senza
# enumeratore e' una didascalia che non conosciamo.
_PADRI_APERTI = ("SPP.A.VI", "CE.A.5", "CE.C.15", "CE.C.16", "CE.C.17", "CE.D.18", "CE.D.19",
                 "CE.20", "CE.B.14", "CE.B.12", "CE.B.13")

# Voci della tabella "Variazioni e scadenza" -> lettera del sotto-campo (crediti / debiti).
# L'ordine conta: "sottoposte al controllo delle controllanti" contiene "controllanti".
_RIGHE_CREDITI = (
    ("sottoposte al controllo", "g"), ("verso clienti", "a"), ("controllate", "b"),
    ("collegate", "c"), ("controllanti", "d"), ("tributari", "e"), ("imposte anticipate", "f"),
    ("verso altri", "g"),
)
_RIGHE_DEBITI = (
    ("sottoposte al controllo", "g"), ("verso soci per finanziamenti", "b"), ("obbligazioni", "c"),
    ("verso banche", "a"), ("verso altri finanziatori", "b"), ("acconti", "g"),
    ("verso fornitori", "d"), ("titoli di credito", "g"), ("controllate", "g"), ("collegate", "g"),
    ("controllanti", "g"), ("tributari", "e"), ("previdenza", "f"), ("altri debiti", "g"),
)


def _norm(testo: str) -> str:
    return re.sub(r"\s+", " ", testo.replace("\n", " ")).strip().casefold()


# --------------------------------------------------------------------------------------
# Riconoscimento
# --------------------------------------------------------------------------------------

_PAGINE_RICONOSCIMENTO = 8


def riconosci(sorgente: str) -> bool:
    """Vero se il documento e' il PDF reso da un XBRL depositato: il piede di tassonomia compare
    su una pagina che porta il titolo del prospetto (le prime pagine bastano: il prospetto e'
    sempre in testa). Accetta un percorso di file o direttamente il testo. Solo testo, nessun
    modello."""
    if not sorgente:
        return False
    if not os.path.isfile(sorgente):
        return bool(_PIEDE.search(sorgente)) and bool(
            re.search(r"^Stato patrimoniale", sorgente, re.M))
    try:
        with fitz.open(sorgente) as documento:
            for pagina in list(documento)[:_PAGINE_RICONOSCIMENTO]:
                testo = pagina.get_text()
                if _PIEDE.search(testo) and re.search(r"^Stato patrimoniale", testo, re.M):
                    return True
    except Exception:
        return False
    return False


# --------------------------------------------------------------------------------------
# Lettura delle righe
# --------------------------------------------------------------------------------------

def _importo(token: str) -> Decimal:
    token = token.strip()
    if token == "-":
        return _ZERO
    # "46.078 (1)": l'importo seguito dal rimando a una nota a pie di tabella, mai due importi
    token = re.sub(r"\s+\(\d{1,2}\)$", "", token)
    negativo = token.startswith("(") or token.startswith("-")
    valore = Decimal(token.strip("()-").replace(".", ""))
    return -valore if negativo else valore


@dataclass
class _Riga:
    didascalia: str
    valori: list[Decimal]
    pagina: int


def _e_piede(righe: list[str]) -> bool:
    prima = righe[0].strip()
    return bool(re.match(r"^v\.\d+(?:\.\d+)*$", prima)
                or re.match(r"^Pag\. \d+ di \d+$", prima)
                or prima.startswith("Bilancio di esercizio al")
                or prima.startswith("Generato automaticamente"))


def _leggi_righe(documento: fitz.Document) -> tuple[list[_Riga], int, list[int]]:
    """Le righe del prospetto, dal titolo dello Stato patrimoniale alla riga ``21)`` del conto
    economico. Un blocco del testo e' una cella: la didascalia (anche su piu' righe, quando la riga
    che precede termina con uno spazio), poi un importo per colonna. Un blocco puo' contenere piu'
    righe di tabella una dopo l'altra: si scandisce token per token."""
    righe: list[_Riga] = []
    colonne = 0
    anni: list[int] = []
    iniziato = False
    finito = False
    saltare_ragione_sociale = False
    for numero, pagina in enumerate(documento):
        in_nota = False
        for blocco in pagina.get_text("blocks"):
            grezze = blocco[4].split("\n")
            pulite = [r.strip() for r in grezze if r.strip()]
            if not pulite:
                continue
            if _e_piede(pulite):
                # "v.2.14.5" da sola: il blocco dopo e' la ragione sociale del piede, mai una riga
                saltare_ragione_sociale = len(pulite) == 1 and bool(re.match(r"^v\.\d", pulite[0]))
                continue
            if saltare_ragione_sociale:
                saltare_ragione_sociale = False
                if len(pulite) == 1 and not _IMPORTO.match(pulite[0]):
                    continue
            # Nota a pie di tabella ("(1)" da solo in un blocco, poi il suo contenuto): sta in
            # fondo alla pagina, mai nel prospetto.
            if len(pulite) == 1 and _RE_NOTA_PIEDE.match(pulite[0]):
                in_nota = True
            if in_nota:
                continue
            if all(all(_DATA.match(t) for t in r.split()) for r in pulite):
                if not colonne:
                    token = [t for r in pulite for t in r.split()]
                    colonne = len(token)
                    anni = [int(_DATA.match(t).group(1)) for t in token]
                continue
            if finito:
                continue
            corrente: Optional[_Riga] = None
            continua = False
            for riga in grezze:
                testo = riga.strip()
                if not testo:
                    continue
                if _IMPORTO.match(testo):
                    if corrente is None:
                        continue
                    corrente.valori.append(_importo(testo))
                    continua = False
                    continue
                if (corrente is not None and not corrente.valori and continua
                        and not _RE_GRUPPO.match(testo)):
                    corrente.didascalia += " " + testo
                else:
                    if not iniziato:
                        if _norm(testo).startswith("stato patrimoniale"):
                            iniziato = True
                        else:
                            corrente = None
                            continue
                    corrente = _Riga(testo, [], numero)
                    righe.append(corrente)
                continua = riga.endswith(" ")
            if righe and re.match(r"^21\)\s", righe[-1].didascalia) and righe[-1].valori:
                finito = True
    return righe, colonne, anni


# --------------------------------------------------------------------------------------
# Albero del prospetto
# --------------------------------------------------------------------------------------

@dataclass
class _Nodo:
    didascalia: str
    livello: int
    percorso: str
    genitore: Optional["_Nodo"] = None
    figli: list["_Nodo"] = field(default_factory=list)
    valori: Optional[list[Decimal]] = None     # None = intestazione
    scadenza: Optional[str] = None             # "E" / "O"
    enumeratore: Optional[tuple[str, list[str]]] = None
    gruppo: Optional[list["_Nodo"]] = None     # componenti, se riga di raggruppamento
    ereditato: bool = False                    # riga senza enumeratore, voce del padre
    ignoto: bool = False
    componente_di: Optional["_Nodo"] = None
    stampato: Optional[list[Decimal]] = None   # il totale che lo chiude
    sezione: str = "sp"


class _Rifiuto(Exception):
    def __init__(self, controllo: str, **dettaglio):
        super().__init__(controllo)
        self.controllo = controllo
        self.dettaglio = dettaglio


def _enumeratore(didascalia: str):
    """(tipo, [chiavi]) oppure None. Tipi: L capitale, R romano, N arabo, l lettera minuscola."""
    m = _RE_GRUPPO.match(didascalia)
    if m:
        chiavi = _RE_CHIAVE.findall(m.group(1))
        tipo = "N" if _RE_ARABO.match(chiavi[0] + ") ") else "l"
        return tipo, chiavi
    for tipo, rx in (("L", _RE_CAPITALE), ("R", _RE_ROMANO), ("N", _RE_ARABO), ("l", _RE_LETTERA)):
        m = rx.match(didascalia)
        if m:
            return tipo, [m.group(1)]
    return None


def _e_totale(didascalia: str) -> bool:
    return _norm(didascalia).startswith("totale")


def _calcolato(didascalia: str) -> Optional[str]:
    n = _norm(didascalia)
    if n.startswith("differenza tra valore e costi"):
        return "differenza"
    if n.startswith("risultato prima delle imposte"):
        return "prima_imposte"
    if re.match(r"^21\)\s", n) or n.startswith("utile (perdita) dell'esercizio"):
        return "utile"
    return None


def _scadenza(didascalia: str) -> Optional[str]:
    n = _norm(didascalia)
    if n.startswith("esigibili entro"):
        return "E"
    if n.startswith("esigibili oltre"):
        return "O"
    return None


def _somma(nodo: _Nodo, colonne: int) -> list[Decimal]:
    """Valore di un nodo per colonna: la riga stessa se e' una foglia, altrimenti la somma dei
    figli (con il segno della sezione: in C) gli oneri 17) e in D) le svalutazioni 19) si
    sottraggono). Una riga di raggruppamento con componenti non conta: contano loro."""
    if nodo.valori is not None and not nodo.figli:
        return list(nodo.valori)
    tot = [_ZERO] * colonne
    for f in nodo.figli:
        if f.componente_di is not None:
            continue
        v = _somma(f, colonne)
        segno = -1 if (f.percorso in _SEGNO_NEGATIVO and not f.ereditato) else 1
        tot = [t + segno * x for t, x in zip(tot, v)]
    return tot


def _foglie(nodo: _Nodo):
    for f in nodo.figli:
        if f.valori is not None and not f.figli:
            yield f
        yield from _foglie(f)


def _costruisci(righe: list[_Riga], colonne: int):
    """Albero dei prospetti. Ritorna (radici, calcolati, totali, errori): i totali nell'ordine
    di stampa ``(didascalia, valori, nodo_chiuso)``, gli errori come ``(colonna, controllo,
    dettaglio)`` per ogni totale stampato che le righe sotto di lui non riproducono."""
    errori: list[tuple[int, str, dict]] = []
    radici: list[_Nodo] = []
    calcolati: dict[str, list[Decimal]] = {}
    totali: list[tuple[str, list[Decimal], Optional[_Nodo]]] = []
    pila: list[_Nodo] = []
    sezione = "sp"
    gruppo_aperto: Optional[_Nodo] = None
    for r in righe:
        if r.valori and len(r.valori) != colonne:
            raise _Rifiuto("colonne_incoerenti", didascalia=r.didascalia,
                           attese=colonne, lette=len(r.valori))
        n = _norm(r.didascalia)
        if n.startswith("stato patrimoniale"):
            sezione = "sp"
            continue
        if n.startswith("conto economico"):
            sezione = "ce"
            pila = []
            gruppo_aperto = None
            continue
        if sezione == "sp" and n in ("attivo", "passivo"):
            radice = _Nodo(r.didascalia, 0, "SPA" if n == "attivo" else "SPP", sezione="sp")
            radici.append(radice)
            pila = [radice]
            gruppo_aperto = None
            continue
        if sezione == "ce" and not pila:
            radice = _Nodo("Conto economico", 0, "CE", sezione="ce")
            radici.append(radice)
            pila = [radice]
        if not pila:
            raise _Rifiuto("riga_fuori_prospetto", didascalia=r.didascalia)
        calc = _calcolato(r.didascalia)
        if calc and r.valori:
            calcolati[calc] = r.valori
            gruppo_aperto = None
            continue
        if _e_totale(r.didascalia):
            gruppo_aperto = None
            if not r.valori:
                raise _Rifiuto("totale_senza_importi", didascalia=r.didascalia)
            chiuso = None
            for i in range(len(pila) - 1, -1, -1):
                cand = pila[i]
                if (cand.figli or not any(r.valori)) and _somma(cand, colonne)[0] == r.valori[0]:
                    chiuso = i
                    break
            if chiuso is None:
                alto = pila[-1]
                errori.append((0, "totale", {
                    "didascalia": r.didascalia, "stampato": str(r.valori[0]),
                    "letto": str(_somma(alto, colonne)[0]), "sotto": alto.didascalia}))
                chiuso = len(pila) - 1
            nodo = pila[chiuso]
            letti = _somma(nodo, colonne)
            for col in range(1, colonne):
                if letti[col] != r.valori[col]:
                    errori.append((col, "totale", {
                        "didascalia": r.didascalia, "stampato": str(r.valori[col]),
                        "letto": str(letti[col]), "sotto": nodo.didascalia}))
            nodo.stampato = r.valori
            totali.append((r.didascalia, r.valori, nodo))
            pila = pila[:chiuso] if chiuso > 0 else pila[:1]
            continue
        enum = _enumeratore(r.didascalia)
        scad = _scadenza(r.didascalia)
        # Componente di una riga di raggruppamento aperta?
        if (gruppo_aperto is not None and enum and len(enum[1]) == 1
                and enum[0] == gruppo_aperto.enumeratore[0]
                and enum[1][0] in gruppo_aperto.enumeratore[1]):
            padre = gruppo_aperto.genitore
            nodo = _Nodo(r.didascalia, _LIVELLO[enum[0]], f"{padre.percorso}.{enum[1][0]}", padre,
                         valori=r.valori or None, enumeratore=enum, sezione=sezione,
                         componente_di=gruppo_aperto)
            if not r.valori:
                raise _Rifiuto("componente_senza_importi", didascalia=r.didascalia)
            padre.figli.append(nodo)
            gruppo_aperto.gruppo.append(nodo)
            continue
        gruppo_aperto = None
        if enum:
            livello = _LIVELLO[enum[0]]
            while len(pila) > 1 and pila[-1].livello >= livello:
                pila.pop()
            padre = pila[-1]
            chiave = enum[1][0]
            percorso = f"{padre.percorso}.{chiave}" if len(enum[1]) == 1 else padre.percorso
            nodo = _Nodo(r.didascalia, livello, percorso, padre, enumeratore=enum, sezione=sezione)
            if r.valori:
                nodo.valori = r.valori
            padre.figli.append(nodo)
            if len(enum[1]) > 1:
                if not r.valori:
                    raise _Rifiuto("raggruppamento_senza_importi", didascalia=r.didascalia)
                nodo.gruppo = []
                nodo.livello = livello
                gruppo_aperto = nodo
            elif not r.valori:
                pila.append(nodo)
            continue
        if scad:
            padre = pila[-1]
            if not r.valori:
                raise _Rifiuto("scadenza_senza_importi", didascalia=r.didascalia)
            padre.figli.append(_Nodo(r.didascalia, padre.livello + 1, f"{padre.percorso}.{scad}",
                                     padre, valori=r.valori, scadenza=scad, sezione=sezione))
            continue
        # Riga senza enumeratore.
        padre = pila[-1]
        if not r.valori:
            # intestazione senza enumeratore (p.es. un sotto-titolo): contenitore del padre
            nodo = _Nodo(r.didascalia, padre.livello + 1, padre.percorso, padre, sezione=sezione,
                         ereditato=True)
            padre.figli.append(nodo)
            pila.append(nodo)
            continue
        if sezione == "sp" and _norm(r.didascalia) == "perdita ripianata nell'esercizio" \
                and padre.percorso == "SPP.A":
            # voce di patrimonio netto senza enumeratore, sempre a zero nel corpus: sul sotto-campo
            # degli utili/perdite portati; se non e' zero lo si dichiara come massa.
            padre.figli.append(_Nodo(r.didascalia, padre.livello + 1, "SPP.A.VIII", padre,
                                     valori=r.valori, sezione=sezione))
            continue
        if sezione == "sp" and _norm(r.didascalia) == "imposte anticipate" \
                and padre.percorso == "SPA.C.II":
            padre.figli.append(_Nodo(r.didascalia, padre.livello + 1, "SPA.C.II.5-ter", padre,
                                     valori=r.valori, sezione=sezione))
            continue
        aperto = any(padre.percorso == p or padre.percorso.startswith(p + ".")
                     for p in _PADRI_APERTI)
        nodo = _Nodo(r.didascalia, padre.livello + 1, padre.percorso, padre, valori=r.valori,
                     ereditato=aperto, ignoto=not aperto, sezione=sezione)
        padre.figli.append(nodo)
    return radici, calcolati, totali, errori


# --------------------------------------------------------------------------------------
# Foglie -> campi
# --------------------------------------------------------------------------------------

def _campo(percorso: str) -> Optional[str]:
    from importers.import_snello.percorsi import campo_da_percorso
    campo = campo_da_percorso(percorso)
    if campo is None and re.match(r"^SPA\.C\.II\.5(\.[EO])?$", percorso):
        # "5) verso imprese sottoposte al controllo delle controllanti": credito vero senza un
        # sotto-campo proprio nella tabella di legge dell'importatore, va fra gli altri crediti.
        return "sp07g" if percorso.endswith(".O") else "sp06g"
    return campo


def _secchio(nodo: _Nodo) -> Optional[str]:
    """Sotto-campo neutro della sezione per una didascalia sconosciuta, mai un aggregato e mai
    un campo TIER0; ``None`` se la sezione non ne ha uno."""
    p = nodo.percorso
    if p.startswith("SPA.C"):
        return "sp07g" if ".O" in p else "sp06g"
    if p.startswith("SPP.D"):
        return "sp17g" if ".O" in p else "sp16g"
    if p.startswith("CE.A"):
        return "ce04"
    if p.startswith("CE.B"):
        return "ce06"
    return None


@dataclass
class _Colonna:
    importi: dict[str, Decimal] = field(default_factory=dict)
    massa: Decimal = _ZERO
    ignoti: list[tuple[str, str, str]] = field(default_factory=list)
    scadenze_lette: bool = False
    scadenza_assente: bool = False          # debiti
    scadenza_crediti_assente: bool = False


def _aggiungi(importi: dict[str, Decimal], codice: str, v: Decimal) -> None:
    importi[codice] = importi.get(codice, _ZERO) + v


def _importi_colonna(radici: list[_Nodo], colonna: int) -> _Colonna:
    """I campi (codici brevi) di una colonna-anno."""
    out = _Colonna()
    for radice in radici:
        for foglia in _foglie(radice):
            v = foglia.valori[colonna]
            if foglia.gruppo is not None:
                continue
            _piazza(foglia, v, out)
        # righe di raggruppamento: quelle che nessun componente spiega, e il residuo
        for g in _gruppi(radice):
            valore_gruppo = g.valori[colonna]
            if g.gruppo:
                resto = valore_gruppo - sum((c.valori[colonna] for c in g.gruppo), _ZERO)
                if resto == 0:
                    continue
            else:
                resto = valore_gruppo
            if resto != 0:
                _piazza_gruppo(g, resto, out)
    return out


def _gruppi(nodo: _Nodo):
    for f in nodo.figli:
        if f.gruppo is not None:
            yield f
        yield from _gruppi(f)


def _piazza(foglia: _Nodo, v: Decimal, out: _Colonna) -> None:
    if foglia.sezione == "sp":
        if foglia.scadenza:
            out.scadenze_lette = True
        elif (re.match(r"^SPP\.D(\.[\w-]+)*$", foglia.percorso)):
            out.scadenza_assente = True
        elif (re.match(r"^SPA\.C\.II(\.[\w-]+)*$", foglia.percorso)
              and foglia.percorso != "SPA.C.II.5-ter"):
            out.scadenza_crediti_assente = True
    campo = None if foglia.ignoto else _campo(foglia.percorso)
    if campo is None:
        secchio = _secchio(foglia)
        if secchio is None:
            raise _Rifiuto("didascalia_non_collocabile", didascalia=foglia.didascalia,
                           percorso=foglia.percorso)
        _aggiungi(out.importi, secchio, v)
        out.massa += abs(v)
        out.ignoti.append((foglia.didascalia, secchio, str(v)))
        return
    if _norm(foglia.didascalia) == "perdita ripianata nell'esercizio" and v != 0:
        out.massa += abs(v)
        out.ignoti.append((foglia.didascalia, campo, str(v)))
    _aggiungi(out.importi, campo, v)


def _piazza_gruppo(g: _Nodo, v: Decimal, out: _Colonna) -> None:
    """Riga di raggruppamento senza componenti (o con un resto che i componenti non spiegano):
    sull'aggregato diretto della voce quando il padre e' la voce (ce08, ce09, ce14), altrimenti
    sul primo enumeratore e dichiarato come massa non classificata."""
    padre = g.genitore
    if padre is not None and padre.enumeratore and padre.enumeratore[0] == "N":
        campo = _campo(padre.percorso)
        if campo is not None:
            _aggiungi(out.importi, campo, v)
            return
    campo = _campo(f"{padre.percorso}.{g.enumeratore[1][0]}")
    if campo is None:
        raise _Rifiuto("didascalia_non_collocabile", didascalia=g.didascalia, percorso=g.percorso)
    _aggiungi(out.importi, campo, v)
    out.massa += abs(v)
    out.ignoti.append((g.didascalia, campo, str(v)))


# --------------------------------------------------------------------------------------
# Nota integrativa: "Variazioni e scadenza" dei crediti e dei debiti
# --------------------------------------------------------------------------------------

_FAMIGLIE = {"crediti": ("sp06", "sp07", _RIGHE_CREDITI),
             "debiti": ("sp16", "sp17", _RIGHE_DEBITI)}


def _cella(testo) -> Optional[Decimal]:
    """None = cella vuota (la tabella non dichiara la scadenza di quella riga)."""
    t = (testo or "").replace("\n", " ").strip()
    if not t:
        return None
    if not _IMPORTO.match(t):
        raise ValueError(t)
    return _importo(t)


def _tipo_tabella(etichette: list[str]) -> Optional[str]:
    if any("attivo circolante" in e for e in etichette):
        return "crediti"
    if any(e.startswith("debiti") or e == "totale debiti" for e in etichette):
        return "debiti"
    return None


def _leggi_tabelle(documento: fitz.Document, dopo: int) -> dict:
    """Le due tabelle di nota con le scadenze (``Quota scadente entro/oltre l'esercizio``), anche
    quando proseguono sulla pagina dopo (l'intestazione si ripete). Solo la colonna di fine
    esercizio e le due quote: nient'altro della nota integrativa entra."""
    trovate: dict[str, dict] = {}
    aperta: Optional[dict] = None
    for numero in range(dopo, len(documento)):
        pagina = documento[numero]
        testo = pagina.get_text()
        if "Quota scadente" not in testo:
            continue
        try:
            tabelle = pagina.find_tables().tables
        except Exception:
            continue
        for t in tabelle:
            righe = t.extract()
            if not righe:
                continue
            intest = [_norm(c or "") for c in righe[0]]
            i_fine = next((i for i, c in enumerate(intest) if "fine esercizio" in c), None)
            i_entro = next((i for i, c in enumerate(intest) if "quota scadente entro" in c), None)
            i_oltre = next((i for i, c in enumerate(intest) if "quota scadente oltre" in c), None)
            if i_fine is None or i_entro is None:
                continue
            dati = righe[1:]
            etichette = [_norm(r[0] or "") for r in dati]
            tipo = _tipo_tabella(etichette)
            if tipo is None:
                continue
            if tipo in trovate and trovate[tipo]["finita"]:
                continue
            if tipo not in trovate:
                trovate[tipo] = {"righe": [], "totale": None, "finita": False, "pagine": [],
                                 "errore": None}
            raccolta = trovate[tipo]
            raccolta["pagine"].append(numero + 1)
            for r, e in zip(dati, etichette):
                try:
                    cella = {"fine": _cella(r[i_fine]), "entro": _cella(r[i_entro]),
                             "oltre": _cella(r[i_oltre]) if i_oltre is not None else _ZERO}
                except (ValueError, IndexError) as exc:
                    raccolta["errore"] = f"cella_non_numerica:{exc}"
                    continue
                if e.startswith("totale"):
                    raccolta["totale"] = cella
                    raccolta["finita"] = True
                    break
                raccolta["righe"].append((e, cella))
    for raccolta in trovate.values():
        if not raccolta["finita"]:
            raccolta["errore"] = raccolta["errore"] or "tabella_senza_totale"
    return trovate


def _lettera(etichetta: str, tabella_righe) -> Optional[str]:
    for chiave, lettera in tabella_righe:
        if chiave in etichetta:
            return lettera
    return None


def _applica_tabella(importi: dict[str, Decimal], tipo: str, raccolta: dict) -> dict:
    """Tutto o niente (CLAUDE.md: una correzione che tocca piu' campi si applica tutta o niente).
    Si applica solo se le quote entro/oltre della tabella chiudono, al centesimo, sul valore che il
    PROSPETTO stampa per le stesse scadenze; con le voci gia' stampate nel prospetto (ordinario) la
    tabella e' soltanto un controllo incrociato."""
    breve, lungo, righe_map = _FAMIGLIE[tipo]
    rapporto: dict = {"pagine": raccolta["pagine"], "applicata": False}
    if raccolta["errore"]:
        rapporto["motivo"] = raccolta["errore"]
        return rapporto
    righe = raccolta["righe"]
    totale = raccolta["totale"]
    mappate = []
    for etichetta, cella in righe:
        lettera = _lettera(etichetta, righe_map)
        if lettera is None:
            rapporto["motivo"] = f"riga_non_riconosciuta:{etichetta}"
            return rapporto
        mappate.append((etichetta, lettera, cella))
    for etichetta, lettera, c in mappate:
        if c["entro"] is not None and c["fine"] is not None \
                and c["entro"] + (c["oltre"] or _ZERO) != c["fine"]:
            rapporto["motivo"] = f"riga_incoerente:{etichetta}"
            return rapporto
    con_scadenza = [(e, l, c) for e, l, c in mappate if c["entro"] is not None]
    somma_entro = sum((c["entro"] for _, _, c in con_scadenza), _ZERO)
    somma_oltre = sum(((c["oltre"] or _ZERO) for _, _, c in con_scadenza), _ZERO)
    if totale and totale["entro"] is not None and totale["entro"] != somma_entro:
        rapporto["motivo"] = "totale_tabella_entro"
        rapporto["tabella_righe"] = str(somma_entro)
        rapporto["tabella_totale"] = str(totale["entro"])
        return rapporto
    if totale and totale["oltre"] is not None and totale["oltre"] != somma_oltre:
        rapporto["motivo"] = "totale_tabella_oltre"
        rapporto["tabella_righe"] = str(somma_oltre)
        rapporto["tabella_totale"] = str(totale["oltre"])
        return rapporto
    diretto_e = importi.get(breve, _ZERO)
    diretto_o = importi.get(lungo, _ZERO)
    if diretto_e == 0 and diretto_o == 0:
        # il prospetto stampa gia' le voci: vince il prospetto, la tabella controlla soltanto
        discordanze = []
        for lettera in sorted({l for _, l, _ in con_scadenza}):
            t_e = sum((c["entro"] for _, l, c in con_scadenza if l == lettera), _ZERO)
            t_o = sum(((c["oltre"] or _ZERO) for _, l, c in con_scadenza if l == lettera), _ZERO)
            p_e = importi.get(breve + lettera, _ZERO)
            p_o = importi.get(lungo + lettera, _ZERO)
            if (t_e, t_o) != (p_e, p_o):
                discordanze.append({"voce": lettera, "tabella": [str(t_e), str(t_o)],
                                    "prospetto": [str(p_e), str(p_o)]})
        rapporto["motivo"] = "prospetto_con_dettaglio"
        if discordanze:
            rapporto["discordanze"] = discordanze
        return rapporto
    if (diretto_e, diretto_o) != (somma_entro, somma_oltre):
        rapporto["motivo"] = "non_riconcilia_col_prospetto"
        rapporto["tabella"] = [str(somma_entro), str(somma_oltre)]
        rapporto["prospetto"] = [str(diretto_e), str(diretto_o)]
        return rapporto
    for _, lettera, c in con_scadenza:
        _aggiungi(importi, breve + lettera, c["entro"])
        _aggiungi(importi, lungo + lettera, c["oltre"] or _ZERO)
    importi[breve] = _ZERO
    importi[lungo] = _ZERO
    rapporto["applicata"] = True
    rapporto["righe"] = len(con_scadenza)
    return rapporto


# --------------------------------------------------------------------------------------
# Assemblaggio e verifica
# --------------------------------------------------------------------------------------

def _stampati(totali) -> dict[str, list[Decimal]]:
    out: dict[str, list[Decimal]] = {}
    for didascalia, valori, _ in totali:
        n = _norm(didascalia)
        if n == "totale attivo":
            out["attivo"] = valori
        elif n == "totale passivo":
            out["passivo"] = valori
        elif n.startswith("totale valore della produzione"):
            out["valore_produzione"] = valori
        elif n.startswith("totale costi della produzione"):
            out["costi_produzione"] = valori
        elif n.startswith("totale proventi e oneri finanziari"):
            out["finanziari"] = valori
        elif n.startswith("totale delle rettifiche di valore"):
            out["rettifiche"] = valori
        elif n.startswith("totale delle imposte"):
            out["imposte"] = valori
    return out


def _chiudi(importi: dict[str, Decimal]):
    """Gli aggregati con scadenza che il documento non spiega per voce vanno sul sotto-campo
    esplicito (``sp06g``, ``sp07g``, ``sp16g``, ``sp17g``), mai lasciati sull'aggregato."""
    for aggregato in ("sp06", "sp07", "sp16", "sp17"):
        v = importi.pop(aggregato, _ZERO)
        if v:
            _aggiungi(importi, aggregato + "g", v)
    from importers.import_snello.percorsi import completa
    return completa({k: v for k, v in importi.items()})


# Totali intermedi stampati -> campi aggregati che devono riprodurli dopo la traduzione percorso ->
# campo: la quadratura attivo = passivo non vede una massa finita nell'aggregato sbagliato dello
# stesso lato (un credito su una immobilizzazione), questo si'. Chiave: percorso del nodo che il
# totale chiude.
_AGGREGATI_DEL_TOTALE = {
    "SPA.B": ("sp02", "sp03", "sp04"), "SPA.B.I": ("sp02",), "SPA.B.II": ("sp03",),
    "SPA.C": ("sp05", "sp06", "sp07", "sp08", "sp09"), "SPA.C.I": ("sp05",),
    "SPA.C.II": ("sp06", "sp07"), "SPA.C.III": ("sp08",), "SPA.C.IV": ("sp09",),
    "SPP.A": ("sp11", "sp12", "sp13"), "SPP.B": ("sp14",), "SPP.D": ("sp16", "sp17"),
    "CE.B.9": ("ce08",), "CE.B.10": ("ce09",), "CE.A.5": ("ce04",),
    "CE.C.16": ("ce14",), "CE.C.17": ("ce15",),
}


def _verifica(col: int, bs: dict, ce: dict, stampati: dict, calcolati: dict,
              totali: list) -> list:
    """Controlli di campo (dopo la traduzione percorso -> campo): ognuno al centesimo."""
    from calculations.ce_result import calculate_ce_result
    from importers.iv_cee_hierarchy import _ATTIVO_FIELDS, _PASSIVO_FIELDS
    errori: list = []
    att = sum((Decimal(bs.get(k, 0)) for k in _ATTIVO_FIELDS), _ZERO)
    pas = sum((Decimal(bs.get(k, 0)) for k in _PASSIVO_FIELDS), _ZERO)
    if att == 0 and pas == 0:
        return [(col, "estrazione_vuota", {})]

    def conf(nome, letto, stamp):
        if stamp is not None and Decimal(letto) != stamp[col]:
            errori.append((col, nome, {"letto": str(letto), "stampato": str(stamp[col])}))
    conf("attivo_campi", att, stampati.get("attivo"))
    conf("passivo_campi", pas, stampati.get("passivo"))
    if att != pas:
        errori.append((col, "attivo_diverso_da_passivo", {"attivo": str(att), "passivo": str(pas)}))
    from importers.import_snello.percorsi import NOMI
    for didascalia, valori, nodo in totali:
        campi = _AGGREGATI_DEL_TOTALE.get(nodo.percorso)
        if campi is None:
            continue
        sorgente = ce if nodo.percorso.startswith("CE") else bs
        letto = sum((Decimal(sorgente.get(NOMI[c], 0)) for c in campi), _ZERO)
        if letto != valori[col]:
            errori.append((col, "aggregati_del_totale", {
                "didascalia": didascalia, "campi": list(campi), "letto": str(letto),
                "stampato": str(valori[col])}))
    r = calculate_ce_result(ce)
    conf("valore_produzione", r.production_value, stampati.get("valore_produzione"))
    conf("costi_produzione", r.production_cost, stampati.get("costi_produzione"))
    conf("differenza_A_B", r.ebit, calcolati.get("differenza"))
    conf("prima_delle_imposte", r.profit_before_tax, calcolati.get("prima_imposte"))
    conf("utile_ce", r.net_profit, calcolati.get("utile"))
    sp13 = Decimal(bs.get("sp13_utile_perdita", 0))
    if sp13 != r.net_profit:
        errori.append((col, "ce_diverso_da_sp13", {"ce": str(r.net_profit), "sp13": str(sp13)}))
    return errori


def _controlli_documento(col: int, stampati: dict, calcolati: dict) -> list:
    """Coerenza dei totali stampati fra loro: A - B, + C + D, - imposte."""
    errori = []
    a, b = stampati.get("valore_produzione"), stampati.get("costi_produzione")
    d = calcolati.get("differenza")
    if a and b and d and a[col] - b[col] != d[col]:
        errori.append((col, "stampato_differenza_A_B", {
            "A": str(a[col]), "B": str(b[col]), "differenza": str(d[col])}))
    p = calcolati.get("prima_imposte")
    if d and p:
        fin = stampati.get("finanziari", [_ZERO] * (col + 1))[col]
        ret = stampati.get("rettifiche", [_ZERO] * (col + 1))[col]
        if d[col] + fin + ret != p[col]:
            errori.append((col, "stampato_prima_delle_imposte", {
                "differenza": str(d[col]), "finanziari": str(fin), "rettifiche": str(ret),
                "prima": str(p[col])}))
    u = calcolati.get("utile")
    if p and u:
        imp = stampati.get("imposte", [_ZERO] * (col + 1))[col]
        if p[col] - imp != u[col]:
            errori.append((col, "stampato_utile", {
                "prima": str(p[col]), "imposte": str(imp), "utile": str(u[col])}))
    return errori


def _rifiutato(anni, controllo: str, **dettaglio) -> dict:
    return {"adottabile": False, "rifiuto": {"controllo": controllo, **dettaglio}, "anni": anni,
            "bs": {}, "ce": {}, "prior_bs": None, "prior_ce": None, "stampati": {},
            "dettagli": {}}


def _nome_anno(anni, col):
    return anni[col] if col < len(anni) else col


def estrai(file_path: str) -> Optional[dict]:
    """None se il documento non e' un PDF reso da XBRL; altrimenti un candidato: adottabile solo
    quando OGNI controllo chiude al centesimo (totali stampati riprodotti dalle righe, attivo =
    passivo, risultato CE = ``sp13`` = utile stampato). Il candidato rifiutato nomina il controllo
    fallito in ``rifiuto`` e non porta mai dati: il chiamante prosegue come prima."""
    if not riconosci(file_path):
        return None
    try:
        documento = fitz.open(file_path)
    except Exception:
        return None
    with documento:
        righe, colonne, anni = _leggi_righe(documento)
        if not righe or not colonne:
            return _rifiutato(anni, "prospetto_non_letto")
        try:
            radici, calcolati, totali, errori = _costruisci(righe, colonne)
            colonne_dati = [_importi_colonna(radici, c) for c in range(colonne)]
        except _Rifiuto as exc:
            return _rifiutato(anni, exc.controllo, **exc.dettaglio)
        ultima = max(r.pagina for r in righe)
        tabelle = _leggi_tabelle(documento, ultima + 1)

    stampati = _stampati(totali)
    anomalie: dict[int, list] = {c: [] for c in range(colonne)}
    for col, controllo, dettaglio in errori:
        anomalie[col].append((col, controllo, dettaglio))
    for c in range(colonne):
        anomalie[c].extend(_controlli_documento(c, stampati, calcolati))

    dettagli: dict = {}
    risultati = []
    for c, dati in enumerate(colonne_dati):
        importi = dict(dati.importi)
        if c == 0:
            for tipo, raccolta in tabelle.items():
                dettagli[tipo] = _applica_tabella(importi, tipo, raccolta)
        bs, ce = _chiudi(importi)
        anomalie[c].extend(_verifica(c, bs, ce, stampati, calcolati, totali))
        bs["_unclassified_mass"] = dati.massa.quantize(_C)
        bs["_plug_residual"] = Decimal("0.00")
        # un flag per lato (Task 24, fix round 2): debiti e crediti si dichiarano separatamente
        if dati.scadenza_assente:
            bs["_source_maturity_unspecified"] = Decimal("1")
        if dati.scadenza_crediti_assente:
            bs["_source_credit_maturity_unspecified"] = Decimal("1")
        if not (dati.scadenza_assente or dati.scadenza_crediti_assente) and dati.scadenze_lette:
            bs["_source_maturity_read"] = Decimal("1")
        bs["_source_xbrl_reso"] = Decimal("1")
        risultati.append((bs, ce, [list(x) for x in dati.ignoti]))

    def primo(c):
        a = anomalie[c]
        if not a:
            return None
        col, controllo, dettaglio = a[0]
        return {"controllo": controllo, "anno": _nome_anno(anni, col), **dettaglio}

    if anomalie[0]:
        out = _rifiutato(anni, **primo(0))
        out["rifiuto"]["altri"] = [
            {"controllo": a[1], **a[2]} for a in anomalie[0][1:]]
        return out
    prior_bs = prior_ce = None
    prior_stato = "assente"
    if colonne > 1:
        if anomalie[1]:
            prior_stato = "scartato"
            prior_rifiuto = primo(1)
        else:
            (prior_bs, prior_ce, _), prior_stato = risultati[1], "letto"
            prior_rifiuto = None
    else:
        prior_rifiuto = None
    bs, ce, ignoti = risultati[0]
    return {
        "adottabile": True, "rifiuto": None, "anni": anni, "bs": bs, "ce": ce,
        "prior_bs": prior_bs, "prior_ce": prior_ce, "prior_stato": prior_stato,
        "prior_rifiuto": prior_rifiuto,
        "stampati": {"totale_attivo": stampati["attivo"][0] if "attivo" in stampati else None,
                     "totale_passivo": stampati["passivo"][0] if "passivo" in stampati else None},
        "dettagli": dettagli, "ignoti": ignoti,
    }
