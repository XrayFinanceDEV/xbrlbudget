"""Righe di totale e parentela, colonna per colonna (Task 6).

Un totale e' una riga il cui importo e' la somma di righe adiacenti dello stesso lato e sezione: decide la somma
stampata, mai il codice conto (CLAUDE.md, «Estrazione e classificazione»). L'algoritmo e' quello di
`import_snello/righe.py:marca_totali` (k >= 2, poi k = 1 solo dopo un gruppo vero; direzione scelta con le due
passate forzate; il totale risolto resta addendo del livello sopra; membro a figlio unico risolto prima di essere
consumato; tetto di 80 membri), applicato a una colonna-esercizio o saldo per volta, con la tolleranza unica (C6)
e il lessico unico delle righe di controllo (C12). Poi ogni riga riceve il padre e il percorso dei suoi antenati:
dalla somma (verificato), altrimenti dall'intestazione sopra (non verificato), mai dal codice.

Si lavora solo sulle righe del prospetto: sulle righe della nota le chiavi delle celle sono colonne della tabella.
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Callable

from importers.import_snello.righe import _lista_concatenata
from importers.lettore.profilo import _norm

if TYPE_CHECKING:
    from importers.lettore.colonne import Colonna
    from importers.lettore.righe import Documento, Riga

_RUOLI_VALORE = ("esercizio", "saldo")
_TETTO_MEMBRI = 80
_CENTESIMO = Decimal("0.01")
_UNITA = Decimal("1")
# C12: il lessico unico delle righe di controllo (TOTALE, PAREGGIO, SALDO FINALE/GENERALE, ECCEDENZA, il risultato
# d'esercizio). Una riga di controllo chiude cio' che le sta sopra.
_CONTROLLO = re.compile(r"\btotal[ei]\b|\bpareggio\b|\bsaldo (?:finale|generale)\b|\beccedenza\b"
                        r"|\b(?:utile|perdita|perdite|risultato)\b.*\besercizio\b")
_TOL_RIENTRO = 2.0
_PAROLE_VUOTE = {"di", "del", "dello", "della", "delle", "dei", "degli", "e", "ed", "in", "a", "al", "alla", "per",
                 "su", "con", "da", "verso", "v", "totale", "totali", "voce", "voci"}
_ROMANO = re.compile(r"^[ivxlc]+$")
_SOLO_SEZIONE = {"stato patrimoniale", "conto economico"}
# Le righe di controllo che chiudono un lato o il conto (pareggio, eccedenza, saldo finale, risultato): non sono una
# voce, non hanno un titolo e non ne contraddicono nessuno.
_CHIUSURA = re.compile(r"\bpareggio\b|\bsaldo (?:finale|generale)\b|\beccedenza\b"
                       r"|\b(?:utile|perdita|perdite|risultato)\b.*\besercizio\b")
_PAROLE_SEZIONE = {"stato", "patrimoniale", "conto", "economico", "attivo", "passivo", "attivita", "passivita", "costi",
                   "ricavi", "sezione"}
# Le parole di una testata di colonna rimasta fra le righe («Conto Descrizione Importo», «Voce Importo (€)»): una riga
# con due di queste, o fatta solo di queste e di date, non e' il titolo di niente.
_TESTATA = {"conto", "conti", "conte", "codice", "cod", "descrizione", "importo", "importi", "saldo", "saldi", "dare",
            "avere", "progr", "progressivo", "progressivi", "differenza", "diff", "scost", "variazione", "parziali",
            "voce", "mastro", "rettifiche", "sezione", "sezbil"}
_TESTATA_ANCHE = {"esercizio", "precedente", "corrente", "periodo", "totali", "euro", "valori", "part", "non", "al",
                  "dal", "anno", "finale", "rettificato", "%", "€"}


def _di_controllo(r: Riga) -> bool:
    """Una riga di controllo (C12) o una riga di soli importi: chiude sempre le righe sopra di lei."""
    return (not r.etichetta and not r.codice) or bool(_CONTROLLO.search(_norm(r.etichetta)))


def _tolleranza(doc: Documento, colonna: Colonna) -> Decimal:
    """C6: al centesimo, oppure un euro quando la colonna stampa le voci tutte all'unita'."""
    return _UNITA if doc.profilo.decimali.get(colonna.indice) is False else _CENTESIMO


def _euro(v: Decimal) -> str:
    testo = f"{abs(v):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return ("-" if v < 0 else "") + testo


# --------------------------------------------------------------------------------------
# Somme
# --------------------------------------------------------------------------------------

@dataclass
class _Serie:
    """Le righe di un lato e di una sezione che hanno una cella in una colonna, nell'ordine del documento."""
    colonna: int
    tolleranza: Decimal
    righe: list[Riga]
    valori: list[Decimal]
    controllo: list[bool]
    vivo: list[bool] = field(default_factory=list)
    candidabile: list[bool] = field(default_factory=list)
    figli: dict[int, list[int]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.vivo = [True] * len(self.righe)
        self.candidabile = [True] * len(self.righe)


def _serie(doc: Documento) -> list[_Serie]:
    out = []
    for colonna in doc.colonne:
        if colonna.ruolo not in _RUOLI_VALORE:
            continue
        gruppi: dict[tuple[str, str], list[Riga]] = defaultdict(list)
        for r in doc.righe:
            if r.parte == "prospetto" and colonna.indice in r.celle:
                gruppi[(r.lato, r.sezione)].append(r)
        tolleranza = _tolleranza(doc, colonna)
        for righe in gruppi.values():
            out.append(_Serie(colonna.indice, tolleranza, righe, [r.celle[colonna.indice].valore for r in righe],
                              [_di_controllo(r) for r in righe]))
    return out


def _cerca_membri(valori: list[Decimal], passo: list[int], i: int, kmin: int, tol: Decimal) -> list[int] | None:
    """Come `import_snello/righe.py:_cerca_membri`, con la tolleranza della colonna: i membri vivi da `passo[i]` la
    cui somma torna a `valori[i]` con almeno `kmin` importi diversi da zero (uno zero non fa un gruppo: 100 = 100 +
    0 e' una catena). Una somma che ha gia' toccato il totale con meno membri e poi ci ritorna aggiunge solo righe
    che si annullano: non e' un gruppo, e la catena la trova la passata k = 1."""
    n = len(valori)
    s, j, membri, pieni = Decimal(0), passo[i], [], 0
    while j != -1 and j != n and len(membri) < _TETTO_MEMBRI:
        s += valori[j]
        membri.append(j)
        pieni += valori[j] != 0
        if pieni and abs(s - valori[i]) <= tol:
            return membri if pieni >= kmin else None
        j = passo[j]
    return None


def _marca(serie: _Serie, passo: list[int], i: int, membri: list[int]) -> None:
    """Il totale resta vivo come addendo del livello sopra; i suoi membri escono per sempre."""
    serie.candidabile[i] = False
    serie.figli[i] = membri
    for m in membri:
        serie.vivo[m] = False
    passo[i] = passo[membri[-1]]


def _risolvi(serie: _Serie, ammessi: list[bool], direzione: int, kmin: int) -> int:
    """Una passata nella direzione data (-1: i figli stanno sopra il totale), sui soli candidati `ammessi`: come
    `import_snello/righe.py:_risolvi_totali`, compreso il membro a figlio unico risolto prima di essere consumato."""
    valori, vivo = serie.valori, serie.vivo
    n = len(valori)
    nxt, prv = _lista_concatenata(vivo)
    passo = prv if direzione == -1 else nxt
    ordine = range(n) if direzione == -1 else range(n - 1, -1, -1)
    marcati = 0
    for i in ordine:
        # un totale a zero (a - b = 0) solo su una riga di controllo, e con due importi veri
        if not vivo[i] or not serie.candidabile[i] or not ammessi[i] or (not valori[i] and not serie.controllo[i]):
            continue
        membri = _cerca_membri(valori, passo, i, kmin, serie.tolleranza)
        if membri is None:
            continue
        for m in membri:
            if serie.candidabile[m] and ammessi[m] and valori[m]:
                sotto = _cerca_membri(valori, passo, m, 1, serie.tolleranza)
                if sotto is not None:
                    _marca(serie, passo, m, sotto)
                    marcati += 1
        _marca(serie, passo, i, membri)
        marcati += 1
    return marcati


def _passate(serie: _Serie, direzione: int) -> list[tuple[list[bool], int]]:
    """Le righe di controllo chiudono sempre cio' che sta sopra (-1); le altre seguono la direzione del documento.
    Con la direzione -1 e' una passata sola, come in `import_snello`."""
    if direzione == -1:
        return [([True] * len(serie.righe), -1)]
    return [([not c for c in serie.controllo], 1), (serie.controllo, -1)]


def _forzata(serie: _Serie, direzione: int) -> list[tuple[list[bool], int]]:
    """La passata forzata per scegliere la direzione: le righe di controllo non votano, vanno sempre a -1."""
    return [([not c for c in serie.controllo], direzione)]


def _punto_fisso(tutte: list[_Serie], passate: Callable[[_Serie], list[tuple[list[bool], int]]]) -> tuple[int, int]:
    """Marca fino al punto fisso: per ogni passata k >= 2, poi k = 1 se il documento ha gia' mostrato un gruppo vero
    su quella colonna (una colonna di percentuali «100,00 100,00» fa solo catene). Restituisce (totali marcati,
    gruppi k >= 2)."""
    piano = [(serie, passate(serie)) for serie in tutte]
    marcati = gruppi = 0
    gruppo_visto: set[int] = set()
    cambiato = True
    while cambiato:
        cambiato = False
        for k in range(max((len(p) for _, p in piano), default=0)):
            for kmin in (2, 1):
                for serie, p in piano:
                    if k < len(p) and (kmin == 2 or serie.colonna in gruppo_visto):
                        n = _risolvi(serie, p[k][0], p[k][1], kmin)
                        if n:
                            cambiato = True
                            marcati += n
                            if kmin == 2:
                                gruppo_visto.add(serie.colonna)
                                gruppi += n
    return marcati, gruppi


def _direzione(doc: Documento) -> int:
    """Le due passate forzate per intero, sulle sole righe che non sono di controllo: vince la direzione che marca
    piu' righe; a parita' quella con piu' gruppi veri, poi -1 (il totale dopo i figli). Sostituisce
    `_voti_apprendimento` di `import_snello`, che lavora sulla `Riga` vecchia a un valore solo."""
    esiti = {d: _punto_fisso(_serie(doc), lambda serie, d=d: _forzata(serie, d)) for d in (1, -1)}
    if esiti[1] != esiti[-1]:
        return 1 if esiti[1] > esiti[-1] else -1
    return -1


def marca_totali(doc: Documento) -> None:
    """Imposta `Riga.totale` e `Riga.figli[colonna]` sulle righe del prospetto, colonna per colonna; una voce i cui
    figli tornano su una colonna e non su un'altra resta totale dove torna, e lo scarto dell'altra va in
    `doc.avvisi`."""
    for r in doc.righe:
        if r.parte == "prospetto":
            r.totale, r.figli = False, {}
    direzione = _direzione(doc)
    tutte = _serie(doc)
    _punto_fisso(tutte, lambda serie: _passate(serie, direzione))
    for serie in tutte:
        for i, membri in serie.figli.items():
            totale = serie.righe[i]
            totale.totale = True
            totale.figli[serie.colonna] = tuple(serie.righe[m].id for m in sorted(membri))
    for r in doc.righe:
        if r.totale:
            r.figli = dict(sorted(r.figli.items()))
    _confronta_colonne(doc)


def _priorita(doc: Documento) -> dict[int, int]:
    """Ordine delle colonne per scegliere fra due letture: le correnti prima, poi quelle con piu' gruppi veri (un
    totale con almeno due figli), poi da sinistra."""
    gruppi: dict[int, int] = defaultdict(int)
    for r in doc.righe:
        for c, figli in r.figli.items():
            gruppi[c] += len(figli) >= 2
    valori = [c for c in doc.colonne if c.ruolo in _RUOLI_VALORE]
    ordinate = sorted(valori, key=lambda c: (not c.corrente, -gruppi[c.indice], c.indice))
    return {c.indice: k for k, c in enumerate(ordinate)}


def _nome_colonna(c: Colonna) -> str:
    return f"colonna {c.indice + 1}" + (f" ({c.fine:%d/%m/%Y})" if c.fine else "")


def _confronta_colonne(doc: Documento) -> None:
    """Per ogni totale, le colonne dello stesso lato su cui i suoi figli non sono stati trovati: con gli stessi figli
    la somma torna (e i figli valgono anche li', se nessun altro totale li ha presi) o non torna, e si dichiara."""
    priorita = _priorita(doc)
    per_id = {r.id: r for r in doc.righe}
    colonne = {c.indice: c for c in doc.colonne if c.ruolo in _RUOLI_VALORE}
    presi: dict[int, set[str]] = defaultdict(set)
    for r in doc.righe:
        for c, figli in r.figli.items():
            presi[c].update(figli)
    for t in doc.righe:
        if not t.totale:
            continue
        riferimento = min(t.figli, key=priorita.get)
        figli = [per_id[f] for f in t.figli[riferimento]]
        for c in sorted(t.celle):
            if c in t.figli or c not in colonne:
                continue
            if not any(c in f.celle for f in figli):
                continue        # i figli non stampano quella colonna (parziali e totali, percentuali)
            somma = sum((f.celle[c].valore for f in figli if c in f.celle), Decimal(0))
            scarto = t.celle[c].valore - somma
            if abs(scarto) <= _tolleranza(doc, colonne[c]):
                if not presi[c] & set(t.figli[riferimento]):
                    t.figli[c] = t.figli[riferimento]
                    presi[c].update(t.figli[c])
                continue
            doc.avvisi.append(
                f"«{t.etichetta or t.codice or t.id}» (pagina {t.pagina}): i figli tornano sulla "
                f"{_nome_colonna(colonne[riferimento])} e non sulla {_nome_colonna(colonne[c])}, "
                f"scarto {_euro(scarto)}")
        t.figli = dict(sorted(t.figli.items()))


# --------------------------------------------------------------------------------------
# Padri e percorso
# --------------------------------------------------------------------------------------

def _parole(r: Riga) -> tuple[set[str], set[str]]:
    """Le parole di un'etichetta (radici di 5 lettere) e i suoi enumeratori («B)», «II.», «4)»)."""
    parole, enumeratori = set(), set()
    for t in re.split(r"[^0-9a-z]+", _norm(r.etichetta)):
        if not t or t in _PAROLE_VUOTE:
            continue
        if t.isdigit() or len(t) == 1 or _ROMANO.match(t):
            enumeratori.add(t)
        else:
            parole.add(t[:5])
    return parole, enumeratori


def _stessa_voce(totale: Riga, titolo: Riga) -> bool:
    """Il titolo sopra i figli di un totale nomina la stessa voce: il totale non ha nome proprio («Totale», una riga
    di soli importi), ha lo stesso codice, una parola in comune, o solo l'enumeratore del titolo («Totale I»)."""
    if totale.codice and totale.codice == titolo.codice:
        return True
    p_t, e_t = _parole(totale)
    p_h, e_h = _parole(titolo)
    if p_t:
        return bool(p_t & p_h)
    return not e_t or bool(e_t & e_h)


def _testata(r: Riga) -> bool:
    parole = [t for t in re.split(r"[^0-9a-z%€]+", _norm(f"{r.codice} {r.etichetta}")) if t]
    chiave = sum(t in _TESTATA for t in parole)
    return chiave >= 2 or (chiave >= 1 and all(t in _TESTATA or t in _TESTATA_ANCHE or t.isdigit() for t in parole))


def _di_sezione(r: Riga) -> bool:
    """Un titolo fatto solo di parole di sezione («PATRIMONIALE», «Attività»): nomina il lato, non una voce."""
    parole = [t for t in re.split(r"[^0-9a-z]+", _norm(r.etichetta)) if t]
    return bool(parole) and all(t in _PAROLE_SEZIONE or t in _PAROLE_VUOTE for t in parole)


def _sezione_soltanto(r: Riga) -> bool:
    return _norm(r.etichetta) in _SOLO_SEZIONE


@dataclass
class _Lato:
    """Le righe del prospetto di un lato e di una sezione, con le posizioni e gli intervalli chiusi dei totali."""
    righe: list[Riga]
    pos: dict[str, int]
    inizio: dict[str, int] = field(default_factory=dict)      # id totale -> prima riga del suo gruppo (titoli compresi)
    chiusi: dict[int, int] = field(default_factory=dict)      # ultima riga di un gruppo -> la sua prima


def _lati(doc: Documento) -> list[_Lato]:
    gruppi: dict[tuple[str, str], list[Riga]] = defaultdict(list)
    for r in doc.righe:
        if r.parte == "prospetto":
            gruppi[(r.lato, r.sezione)].append(r)
    return [_Lato(righe, {r.id: k for k, r in enumerate(righe)}) for righe in gruppi.values()]


def _figli_di(r: Riga, priorita: dict[int, int]) -> tuple[str, ...]:
    if not r.figli:
        return ()
    return r.figli[min(r.figli, key=lambda c: priorita.get(c, len(priorita)))]


def assegna_padri(doc: Documento) -> None:
    """Imposta `Riga.padre`, `Riga.padre_verificato` e `Riga.percorso`: dalla somma (il totale i cui figli
    contengono la riga, su almeno una colonna), altrimenti dall'ultima intestazione sopra nello stesso lato e
    sezione, rientrata come la riga o meno; mai dal codice. Un'intestazione sopra i figli di un totale che nomina
    un'altra voce perde: vince il totale, e la differenza va in `doc.avvisi`."""
    priorita = _priorita(doc)
    per_id = {r.id: r for r in doc.righe}
    prospetto = [r for r in doc.righe if r.parte == "prospetto"]
    for r in prospetto:
        r.padre, r.padre_verificato, r.percorso = None, False, ()

    # 1. dalla somma: la colonna con priorita' piu' alta vince su un'altra che indica un altro totale
    scelta: dict[str, tuple[int, str]] = {}
    pretendenti: dict[str, set[str]] = defaultdict(set)
    for t in prospetto:
        for c, figli in t.figli.items():
            for f in figli:
                pretendenti[f].add(t.id)
                voto = (priorita.get(c, len(priorita)), t.id)
                if f not in scelta or voto < scelta[f]:
                    scelta[f] = voto
    for f, (_, t) in scelta.items():
        per_id[f].padre, per_id[f].padre_verificato = t, True
    # Due colonne che danno alla stessa riga due totali diversi, uno dentro l'altro: vince il piu' interno. Una riga a
    # zero sulla corrente («- esigibili oltre 0,00») la prende il totale di sopra, la precedente la mette al suo posto.
    def antenati(t: str | None) -> list[str]:
        catena: list[str] = []
        while t and t not in catena:
            catena.append(t)
            t = per_id[t].padre
        return catena

    for f, alternative in pretendenti.items():
        if len(alternative) < 2:
            continue
        scelto = per_id[f].padre
        dentro = [t for t in alternative
                  if t not in (scelto, f) and scelto in antenati(t)[1:] and f not in antenati(t)]
        if dentro:
            per_id[f].padre = max(dentro, key=lambda t: len(antenati(t)))

    titoli: dict[str, Riga] = {}        # id totale -> la sua intestazione
    di_titolo: dict[str, str] = {}      # id intestazione -> id totale
    lati = _lati(doc)
    for lato in lati:
        _titoli_e_gruppi(doc, lato, priorita, titoli, di_titolo)

    # 2. dall'intestazione, per le righe senza un totale che le contenga
    for lato in lati:
        for k, r in enumerate(lato.righe):
            if r.padre is not None or r.id in di_titolo:
                continue
            da = lato.inizio.get(r.id, k)
            trovato = _intestazione_sopra(lato, da, k, r, stretto=r.intestazione, di_titolo=di_titolo)
            if trovato is not None:
                r.padre = trovato.id
    for h, t in di_titolo.items():
        # il titolo e' il nome del totale: ne prende il padre, ma nessuna somma lo contiene
        per_id[h].padre = per_id[t].padre

    # 3. il percorso: la sezione, poi le etichette degli antenati
    def nome(p: Riga) -> str:
        titolo = titoli.get(p.id)
        if titolo is not None and not _sezione_soltanto(titolo):
            return titolo.etichetta or titolo.codice
        if p.intestazione and _sezione_soltanto(p):
            return ""
        return p.etichetta or p.codice

    fatti: dict[str, tuple[str, ...]] = {}

    def percorso(r: Riga, visti: set[str]) -> tuple[str, ...]:
        if r.id in fatti:
            return fatti[r.id]
        padre = per_id.get(r.padre) if r.padre else None
        if padre is None or padre.id in visti:
            out = (r.sezione,) if r.sezione else ()
        else:
            n = nome(padre)
            out = percorso(padre, visti | {r.id}) + ((n,) if n else ())
        fatti[r.id] = out
        return out

    for r in prospetto:
        r.percorso = percorso(r, set())


def _titoli_e_gruppi(doc: Documento, lato: _Lato, priorita: dict[int, int], titoli: dict[str, Riga],
                     di_titolo: dict[str, str]) -> None:
    """Gli intervalli dei gruppi chiusi e i titoli dei totali che chiudono i figli sopra di se'. Il titolo sta fra
    le intestazioni subito sopra il gruppo, dal totale piu' interno al piu' esterno: per un totale con un nome,
    l'intestazione che nomina la stessa voce; per un totale senza nome («Totale», «Totale I», una riga di soli
    importi), quella col suo enumeratore o la prima rientrata meno dei figli. Un'intestazione con un nome diverso
    subito sopra i figli di un totale col nome contraddice il totale: vince il totale, e si dichiara."""
    righe, pos = lato.righe, lato.pos
    prima: dict[str, int] = {}
    ultima: dict[str, int] = {}

    def estremi(r: Riga, visti: frozenset[str] = frozenset()) -> tuple[int, int]:
        if r.id in prima:
            return prima[r.id], ultima[r.id]
        a = b = pos[r.id]
        for f in _figli_di(r, priorita):
            if f in pos and f not in visti:
                fa, fb = estremi(righe[pos[f]], visti | {r.id})
                a, b = min(a, fa), max(b, fb)
        prima[r.id], ultima[r.id] = a, b
        return a, b

    chiudono = []
    for r in righe:
        if r.totale and _figli_di(r, priorita):
            a, b = estremi(r)
            lato.inizio[r.id] = a
            if b == pos[r.id] and a < b:
                chiudono.append(r)
    chiudono.sort(key=lambda t: (pos[t.id] - prima[t.id], pos[t.id]))

    rientri: dict[str, float | None] = {}

    def rientro(r: Riga, visti: frozenset[str] = frozenset()) -> float | None:
        """Il rientro di una riga: il suo, o quello del suo titolo, o quello dei suoi figli."""
        if r.x is not None:
            return r.x
        if r.id in titoli and titoli[r.id].x is not None:
            return titoli[r.id].x
        return rientro_figli(r, visti)

    def rientro_figli(t: Riga, visti: frozenset[str] = frozenset()) -> float | None:
        if t.id in rientri:
            return rientri[t.id]
        xs = [rientro(righe[pos[f]], visti | {t.id}) for f in _figli_di(t, priorita) if f in pos and f not in visti]
        xs = [x for x in xs if x is not None]
        # la mediana: un figlio stampato fuori rientro («5-quater)» a 61 fra fratelli a 84) non sposta il gruppo
        rientri[t.id] = statistics.median(xs) if xs else None
        return rientri[t.id]

    for t in chiudono:
        if _CHIUSURA.search(_norm(t.etichetta)):
            continue
        sopra = []
        j = prima[t.id] - 1
        while j >= 0 and righe[j].intestazione:
            sopra.append(righe[j])
            j -= 1
        sopra = [h for h in sopra if not _testata(h)]
        liberi = [h for h in sopra if h.id not in di_titolo]
        x_figli = rientro_figli(t)

        def entro(h: Riga, stretto: bool) -> bool:
            if x_figli is None or h.x is None:
                return True
            return h.x < x_figli - _TOL_RIENTRO if stretto else h.x <= x_figli + _TOL_RIENTRO

        parole, enumeratori = _parole(t)
        titolo = None
        if parole or t.codice:
            titolo = next((h for h in liberi if _stessa_voce(t, h)), None)
            vicina = sopra[0] if sopra else None
            if titolo is None and vicina is not None and vicina.id not in di_titolo and entro(vicina, False) \
                    and _parole(vicina)[0] and not _di_sezione(vicina):
                doc.avvisi.append(f"«{vicina.etichetta}» (pagina {vicina.pagina}) sta sopra i figli di "
                                  f"«{t.etichetta}», che li somma: vince il totale")
                lato.inizio[t.id] = pos[vicina.id]
                continue
        else:
            if enumeratori:
                titolo = next((h for h in liberi if enumeratori & _parole(h)[1]), None)
            if titolo is None:
                titolo = next((h for h in liberi if entro(h, True)
                               or (h is sopra[0] and h.codice and entro(h, False))), None)
        if titolo is not None:
            titoli[t.id], di_titolo[titolo.id] = titolo, t.id
            lato.inizio[t.id] = pos[titolo.id]
            rientri.clear()
    for r in righe:
        if r.id in lato.inizio:
            fine = ultima.get(r.id, pos[r.id])
            inizio = lato.inizio[r.id]
            if inizio < fine:
                lato.chiusi[fine] = min(lato.chiusi.get(fine, inizio), inizio)


def _intestazione_sopra(lato: _Lato, da: int, k: int, r: Riga, *, stretto: bool,
                        di_titolo: dict[str, str]) -> Riga | None:
    """L'ultima intestazione sopra la posizione `da`, rientrata come `r` o meno (strettamente meno per
    un'intestazione); un gruppo gia' chiuso sopra si salta intero, e il titolo di un totale ancora aperto vale quel
    totale."""
    righe = lato.righe
    j = da - 1
    while j >= 0:
        if j in lato.chiusi and j < k:
            j = lato.chiusi[j] - 1
            continue
        h = righe[j]
        if h.intestazione and not _testata(h) and (r.x is None or h.x is None
                               or (h.x < r.x - _TOL_RIENTRO if stretto else h.x <= r.x + _TOL_RIENTRO)):
            totale = di_titolo.get(h.id)
            if totale is None:
                return h
            if lato.pos[totale] > k:
                return righe[lato.pos[totale]]
        j -= 1
    return None
