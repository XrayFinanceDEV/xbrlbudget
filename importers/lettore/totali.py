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

from importers.lettore._ereditati import lista_concatenata
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
_RIGHE_DI_TESTA = 4
# un livello di rientro: piu' dei pochi punti di un codice allineato a destra («3960.01» a 27, «3940» a 32)
_SCALINO = 10.0
# le parole di un titolo che apre una sezione («COSTI, SPESE E PERDITE», «STATO PATRIMONIALE ATTIVO»)
_APRE_SEZIONE = {"patrimoniale", "economico", "attivo", "passivo", "attivita", "passivita", "costi", "ricavi", "spese",
                 "perdite", "profitti", "proventi", "oneri"}
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


_DECIMALI_STAMPATI = re.compile(r",\d")


def _tolleranza_cella(doc: Documento, t: Riga, colonna: int) -> Decimal:
    """C6 per un totale: un euro quando il totale e' stampato all'unita' (la colonna stampa tutto a interi, la cella
    non ha decimali, o sta nella colonna dei totali di una coppia parziali/totali), anche sopra figli al centesimo
    (le voci a interi sopra i conti a centesimi, 1533, 682, 638); altrimenti al centesimo."""
    if doc.profilo.decimali.get(colonna) is False or colonna in getattr(doc.profilo, "coppie", {}):
        return _UNITA
    cella = t.celle.get(colonna)
    if cella is not None and cella.forma == "importo" and not _DECIMALI_STAMPATI.search(cella.testo):
        return _UNITA
    return _CENTESIMO


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
    tolleranze: list[Decimal]                               # per riga, quando la riga e' il totale (C6)
    righe: list[Riga]
    valori: list[Decimal]
    controllo: list[bool]
    bersagli: list[Decimal] = field(default_factory=list)   # l'importo stampato, che i membri devono fare
    risultato: list[bool] = field(default_factory=list)      # un risultato del conto economico (una differenza)
    sottratti: list[Decimal] = field(default_factory=list)   # il valore di un membro dentro un risultato
    marcati: list[bool] = field(default_factory=list)       # la cella ha il segno dal marcatore D/A (Q2)
    vivo: list[bool] = field(default_factory=list)
    candidabile: list[bool] = field(default_factory=list)
    figli: dict[int, list[int]] = field(default_factory=dict)
    versi: dict[int, int] = field(default_factory=dict)      # -1: i membri a marcatore chiudono col segno rovesciato
    verso_cercato: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.vivo = [True] * len(self.righe)
        self.candidabile = [True] * len(self.righe)
        if not self.bersagli:
            self.bersagli = list(self.valori)
        if not self.risultato:
            self.risultato = [False] * len(self.righe)
        if not self.sottratti:
            self.sottratti = list(self.valori)
        if not self.marcati:
            self.marcati = [False] * len(self.righe)


# Una voce fra parentesi dopo la sua numerazione («(Ammortamenti)», «B.I.5.f) (Fondi di ammortamento)», «(Perdita
# d'esercizio)»): nel fac-simile OIC e' una posta rettificativa, stampata positiva e sottratta dalla voce. Solo coi
# nomi di una rettifica: «(IRES)» o «(di cui …)» fra parentesi sono una voce o un sottoinsieme, non una sottrazione.
_NUMERAZIONE_VOCE = re.compile(r"^[^\s()]{1,14}\)\s+(?=\()")
_NOME_RETTIFICA = re.compile(r"ammortament|svalutazion|\bfond[oi]\b|\bperdit[ae]\b|\bsconti\b|\babbuoni\b|\bresi\b"
                             r"|rettific|\brimanenze finali\b")


def _rettificativa(r: Riga) -> bool:
    e = _NUMERAZIONE_VOCE.sub("", r.etichetta.strip(), count=1)
    if not (e.startswith("(") and e.endswith(")")) or not _NOME_RETTIFICA.search(_norm(e)):
        return False
    livello = 0
    for k, ch in enumerate(e):     # la prima parentesi si chiude solo in fondo: «(a) e (b)» non e' una voce fra parentesi
        livello += {"(": 1, ")": -1}.get(ch, 0)
        if livello == 0 and k < len(e) - 1:
            return False
    return True


def _valore_di_somma(r: Riga, colonna: int) -> Decimal:
    """L'importo come entra nelle somme di un totale sopra: lo stampato, col segno meno per una posta rettificativa
    stampata positiva. Come totale dei suoi conti la posta vale lo stampato (i fondi stampati positivi sommano al
    fondo). La cella resta lo stampato."""
    v = r.celle[colonna].valore
    return -v if v > 0 and _rettificativa(r) else v


# I risultati del conto economico di legge sono differenze stampate: «Differenza tra valore e costi della produzione
# (A - B)», «Risultato prima delle imposte», «21) Utile (perdita) dell'esercizio», «Totale proventi e oneri finanziari
# (15 + 16 - 17 + - 17-bis)», «Totale delle rettifiche». Dentro una di queste somme i costi della produzione, gli
# interessi e oneri, le svalutazioni e le imposte, stampati positivi, si sottraggono.
_RISULTATO = re.compile(r"\bdifferenza\b|\brisultato\b|\butile\b|\bperdita\b|\bproventi e oneri\b"
                        r"|\brettifiche di valore\b|\btotale (?:delle )?rettifiche\b")
_COSTO_DEL_RISULTATO = re.compile(r"\bcosti della produzione\b|\binteressi e (?:altri )?oneri\b|\bsvalutazion"
                                  r"|\bimposte (?:sul reddito|correnti|relative|differite)|\btotale (?:delle )?imposte\b")


# Fuori da uno schema di legge (bilancio di verifica, situazione contabile) «Differenza cambi passiva» o «UTILE
# ESERCIZIO:» sono nomi di conto: li' vale solo il lessico di legge per intero.
_RISULTATO_DI_LEGGE = re.compile(r"\bdifferenza tra valore e costi della produzione\b|\brisultato prima delle imposte\b"
                                 r"|\butile \(perdita\) dell.? ?esercizio\b"
                                 r"|\btotale (?:dei )?proventi e oneri finanziari\b|\btotale (?:delle )?rettifiche\b")
# La voce di legge che stampa il suo importo prima dei componenti («C) PROVENTI E ONERI FINANZIARI», «D) RETTIFICHE DI
# VALORE DI ATTIVITA' …», 1464): tiene la regola del segno, ma non e' una riga di controllo che chiude sopra di se'.
_VOCE_DI_RISULTATO = re.compile(r"^[a-e]\s?[).\-]\s*(?:proventi e oneri|rettifiche di valore)\b")
_TIPI_SCHEMA = ("schema", "schema-dettaglio")


_PROFILO_ASSENTE = "documento senza profilo: totali e segni letti come su uno schema di legge"


def _su_schema(doc: Documento) -> bool:
    return getattr(doc.profilo, "tipo", "schema") in _TIPI_SCHEMA


def _risultato(r: Riga, schema: bool = True) -> bool:
    """Solo su una sezione unica: sulle contrapposte costi e ricavi stanno su due lati, e il risultato pareggia. Fuori
    da uno schema di legge, solo col lessico di legge per intero."""
    if r.sezione != "CE" or r.lato != "U":
        return False
    return bool((_RISULTATO if schema else _RISULTATO_DI_LEGGE).search(_norm(r.etichetta)))


def _risultato_di_controllo(r: Riga, schema: bool = True) -> bool:
    """Un risultato chiude cio' che gli sta sopra, come una riga di controllo; non la voce che lo apre."""
    return _risultato(r, schema) and not _VOCE_DI_RISULTATO.match(_norm(r.etichetta))


def _costo_del_risultato(r: Riga) -> bool:
    e = _norm(r.etichetta)
    return r.sezione == "CE" and r.lato == "U" and bool(_COSTO_DEL_RISULTATO.search(e)) and not _RISULTATO.search(e)


def _marcata(r: Riga, colonna: int) -> bool:
    """Una cella col segno dal marcatore D/A: attaccato («1.234,56A») o staccato in una colonna di
    `Profilo.marcatori` (Q2), lo registra `Importo.marcatore`."""
    cella = r.celle.get(colonna)
    return cella is not None and cella.marcatore is not None


def _valore_nel_totale(t: Riga, f: Riga, colonna: int, verso: int = 1, schema: bool = True) -> Decimal:
    """Il valore del membro `f` nella somma del totale `t`, con le regole del segno (posta rettificativa, costo
    dentro un risultato, conto a marcatore D/A dentro una voce dal verso rovesciato: `Riga.verso`)."""
    v = _valore_di_somma(f, colonna)
    if verso == -1 and _marcata(f, colonna):
        v = -v
    return -v if v > 0 and _risultato(t, schema) and _costo_del_risultato(f) else v


def valore_nel_totale(doc: Documento, totale: Riga, figlio: Riga, colonna: int) -> Decimal:
    """Il valore che il figlio porta nella somma del suo totale, sulla colonna `colonna` di `totale.figli`: le
    poste rettificative, un costo dentro un risultato del conto economico, un conto a marcatore D/A dentro una voce
    dal verso rovesciato (`Riga.verso`). Per risommare i figli si usa questo, mai la cella com'e' stampata."""
    return _valore_nel_totale(totale, figlio, colonna, totale.verso.get(colonna, 1), _su_schema(doc))


def _serie(doc: Documento) -> list[_Serie]:
    out = []
    schema = _su_schema(doc)
    for colonna in doc.colonne:
        if colonna.ruolo not in _RUOLI_VALORE:
            continue
        gruppi: dict[tuple[str, str], list[Riga]] = defaultdict(list)
        for r in doc.righe:
            if r.parte == "prospetto" and colonna.indice in r.celle:
                gruppi[(r.lato, r.sezione)].append(r)
        for righe in gruppi.values():
            valori = [_valore_di_somma(r, colonna.indice) for r in righe]
            # un risultato chiude sempre cio' che gli sta sopra, come una riga di controllo
            out.append(_Serie(colonna.indice, [_tolleranza_cella(doc, r, colonna.indice) for r in righe], righe, valori,
                              [_di_controllo(r) or _risultato_di_controllo(r, schema) for r in righe],
                              [r.celle[colonna.indice].valore for r in righe], [_risultato(r, schema) for r in righe],
                              [-v if v > 0 and _costo_del_risultato(r) else v for r, v in zip(righe, valori)],
                              [_marcata(r, colonna.indice) for r in righe]))
    return out


def _cerca_membri(serie: _Serie, passo: list[int], i: int, kmin: int) -> list[int] | None:
    """I membri del totale `i` (`_cerca`). Q2: su una sezione unica i conti a marcatore D/A hanno il saldo in dare
    positivo, ma una voce del passivo o dei ricavi, stampata positiva e senza marcatore, li chiude col segno
    rovesciato: se il verso diritto non chiude, si prova il rovesciato (i soli membri a marcatore cambiano segno; una
    cella senza marcatore, «FORNITORE 2.515.292,93» fra i debiti di 1533, resta com'e' stampata). Il verso trovato
    resta in `verso_cercato[i]`, e `_marca` lo registra."""
    base = serie.sottratti if serie.risultato[i] else serie.valori
    serie.verso_cercato[i] = 1
    membri = _cerca(serie, passo, i, kmin, base)
    if membri is not None or serie.righe[i].lato != "U" or serie.marcati[i] or not any(serie.marcati):
        return membri
    rovesciati = [-v if m else v for v, m in zip(base, serie.marcati)]
    membri = _cerca(serie, passo, i, kmin, rovesciati)
    if membri is None or not any(serie.marcati[m] for m in membri if base[m]):
        return None
    serie.verso_cercato[i] = -1
    return membri


def _cerca(serie: _Serie, passo: list[int], i: int, kmin: int, valori: list[Decimal]) -> list[int] | None:
    """Come `import_snello/righe.py:_cerca_membri`, con la tolleranza della colonna: i membri vivi da `passo[i]` la
    cui somma torna a `valori[i]` con almeno `kmin` importi diversi da zero (uno zero non fa un gruppo: 100 = 100 +
    0 e' una catena). Una somma che ha gia' toccato il totale con meno membri e poi ci ritorna aggiunge solo righe
    che si annullano: non e' un gruppo. Lo stesso per un tratto che si annulla da solo (somme parziali che si
    ripetono): un mastro e la sua foglia, +x e -x, finirebbero contati due volte. Una catena (un solo importo) vale
    solo all'uguaglianza esatta e mai con un figlio meno rientrato del totale (R14). Il tetto di 80 membri non vale
    per una riga di controllo (R15): «Totale costi» chiude anche centocinquanta conti."""
    tol = serie.tolleranze[i]
    bersaglio = serie.bersagli[i]
    n = len(valori)
    tetto = n if serie.controllo[i] else _TETTO_MEMBRI
    s, j, membri, pieni = Decimal(0), passo[i], [], 0
    parziali = {Decimal(0)}
    # R17: una chiusura entro la tolleranza resta in attesa finche' la somma resta nella finestra: se piu' avanti la
    # stessa ricerca chiude esatta (14.445,49 -> 14.445,48 col conto da -0,01, 1478), vince l'esatta
    in_tolleranza: list[int] | None = None
    while j != -1 and j != n and len(membri) < tetto:
        s += valori[j]
        membri.append(j)
        pieni += valori[j] != 0
        if pieni and abs(s - bersaglio) <= tol:
            if pieni < kmin:
                return in_tolleranza
            if pieni == 1 and (s != bersaglio or _meno_rientrato(serie, membri, i) or _controllo_figlio_unico(
                    serie, membri, i)):
                return in_tolleranza
            if _chiusura_piu_esterna(serie, membri, i):
                return in_tolleranza
            if not bersaglio and not serie.controllo[i] and pieni != 2:
                return in_tolleranza     # un totale a zero fuori dal lessico C12: solo la coppia costo/fondo
            if s == bersaglio:
                return membri
            if in_tolleranza is None:
                in_tolleranza = list(membri)
        elif in_tolleranza is not None:
            return in_tolleranza
        if valori[j]:
            if s in parziali:
                return in_tolleranza
            parziali.add(s)
        j = passo[j]
    return in_tolleranza


def _all_unita(r: Riga, colonna: int) -> bool:
    cella = r.celle[colonna]
    return cella.forma == "importo" and not _DECIMALI_STAMPATI.search(cella.testo)


def _catene_all_unita(serie: _Serie, direzione: int) -> None:
    """R22: una voce stampata all'unita' («contributi in conto esercizio 113.946») sopra un solo conto al centesimo
    (113.945,74) non chiude mai come catena esatta (R14), e il totale sopra, in tolleranza, prenderebbe il conto al
    posto della voce (1533, 682, 208: e il conto attraversa il confine entro/oltre). Prima di ogni altra somma la
    voce prende il suo conto adiacente (sopra o sotto), rientrato piu' di lei o col codice, e col verso dei marcatori
    D/A, come catena entro un euro: resta un'ipotesi (un membro solo, mai verificato), ma il conto esce dal cammino e
    il totale sopra somma la voce. Non vale se il conto dopo, sommato, resta nella tolleranza (la voce ha piu'
    conti), ne' per le righe di controllo o i risultati; senza rientri ne' codici (le tabelle OCR) non vale mai."""
    nxt, prv = lista_concatenata(serie.vivo)
    n = len(serie.righe)
    for i in range(n):
        if not serie.vivo[i] or not serie.candidabile[i] or serie.controllo[i] or serie.risultato[i]:
            continue
        t = serie.righe[i]
        if not _all_unita(t, serie.colonna) or t.x is None:
            continue
        # il conto dopo la voce nella direzione del documento, poi quello dall'altra parte
        for passo in ((nxt, prv) if direzione == 1 else (prv, nxt)):
            j = passo[i]
            if not (0 <= j < n) or not serie.vivo[j] or serie.controllo[j] or not serie.valori[j]:
                continue
            f = serie.righe[j]
            # una voce sopra il suo conto: rientrata meno di lui, o senza codice sopra un conto col codice (208: voce e
            # codice allo stesso bordo). Due conti affiancati, uno stampato senza decimali, non sono voce e conto
            if _all_unita(f, serie.colonna) or f.x is None or not (
                    t.x < f.x - _TOL_RIENTRO or (f.codice and not t.codice)):
                continue
            versi = [1] + ([-1] if t.lato == "U" and serie.marcati[j] and not serie.marcati[i] else [])
            verso = next((v for v in versi if abs(serie.bersagli[i] - v * serie.valori[j]) <= _UNITA), None)
            if verso is None:
                continue
            # il conto puo' essere a sua volta il totale dei suoi conti («Depositi bancari 5.300,05» = 3.000,10 +
            # 2.299,95 sotto «4) Disponibilita' liquide 5.300»): si risolve prima lui, poi la voce lo prende
            if serie.candidabile[j]:
                sotto = _cerca_membri(serie, passo, j, 2)
                if sotto is not None and i not in sotto:
                    _marca(serie, passo, j, sotto)
            k = passo[j]
            if 0 <= k < n and serie.valori[k] and not serie.controllo[k] \
                    and abs(serie.bersagli[i] - verso * (serie.valori[j] + serie.valori[k])) <= _UNITA:
                continue
            serie.verso_cercato[i] = verso
            _marca(serie, passo, i, [j])
            break


def _meno_rientrato(serie: _Serie, membri: list[int], i: int) -> bool:
    """R14, per le sole catene: il figlio stampato sotto e a sinistra del suo totale, di almeno un livello, non e'
    suo figlio (un conto a 85 non e' il totale della voce a 34 che lo segue). Vale solo per un totale stampato prima
    del figlio: un mastro che chiude i suoi conti sta spesso piu' a destra di loro («8.02» dopo «802002»), e il
    rientro di una riga di controllo («Totale X:» allineato a destra) non dice nulla. Un gruppo vero non ha questo
    limite: le foglie col prefisso «Passivo» a 72 sono figlie della voce a 117 (1426)."""
    totale = serie.righe[i]
    if totale.x is None or serie.controllo[i] or membri[0] < i:
        return False
    return any(serie.valori[m] and serie.righe[m].x is not None and serie.righe[m].x < totale.x - _SCALINO
               for m in membri)


def _controllo_figlio_unico(serie: _Serie, membri: list[int], i: int) -> bool:
    """Una catena verso il basso non prende per figlio unico il totale di un costo del conto economico stampato
    sotto: «Totale interessi e altri oneri finanziari» sotto «altri», con lo stesso importo, chiude «altri» e resta
    lui il membro che il risultato sottrae (409). Fuori da quel caso la voce stampata sopra resta la voce e il
    totale sotto la sua ripetizione («I - Immobilizzazioni immateriali» e il suo «Totale …», 1421)."""
    return membri[0] > i and not serie.controllo[i] and any(
        serie.valori[m] and serie.controllo[m] and _costo_del_risultato(serie.righe[m]) for m in membri)


def _chiusura_piu_esterna(serie: _Serie, membri: list[int], i: int) -> bool:
    """Un totale stampato prima dei figli non contiene una riga di controllo meno rientrata di lui: «17 TOTALE
    interessi» a 74 o «21) Utile (perdita) dell'esercizio» a 32 chiudono qualcosa di piu' grande di un conto a 87 o
    del «Risultato prima delle imposte» a 65 sopra di loro (313, 302), anche quando l'aritmetica torna."""
    totale = serie.righe[i]
    if totale.x is None or serie.controllo[i] or membri[0] < i:
        return False
    return any(serie.valori[m] and serie.controllo[m] and serie.righe[m].x is not None
               and serie.righe[m].x < totale.x - _SCALINO for m in membri)


def _annidata(serie: _Serie, m: int, sotto: list[int]) -> bool:
    """Una catena che e' un mastro con la sua foglia rientrata di un livello, non due gemelli allo stesso rientro."""
    mastro = serie.righe[m]
    return mastro.x is not None and any(
        serie.valori[f] and serie.righe[f].x is not None and serie.righe[f].x > mastro.x + _SCALINO for f in sotto)


def _marca(serie: _Serie, passo: list[int], i: int, membri: list[int]) -> None:
    """Il totale resta vivo come addendo del livello sopra; i suoi membri escono per sempre."""
    serie.candidabile[i] = False
    serie.figli[i] = membri
    serie.versi[i] = serie.verso_cercato.get(i, 1)
    for m in membri:
        serie.vivo[m] = False
    passo[i] = passo[membri[-1]]


def _risolvi(serie: _Serie, ammessi: list[bool], direzione: int, kmin: int) -> int:
    """Una passata nella direzione data (-1: i figli stanno sopra il totale), sui soli candidati `ammessi`: come
    `import_snello/righe.py:_risolvi_totali`, compreso il membro a figlio unico risolto prima di essere consumato,
    con la somma rifatta dopo (vedi sotto)."""
    valori, vivo = serie.valori, serie.vivo
    n = len(valori)
    nxt, prv = lista_concatenata(vivo)
    passo = prv if direzione == -1 else nxt
    ordine = range(n) if direzione == -1 else range(n - 1, -1, -1)
    marcati = 0
    for i in ordine:
        # un totale a zero (a - b = 0, il costo e il suo fondo) vale con due importi veri, come ogni gruppo
        if not vivo[i] or not serie.candidabile[i] or not ammessi[i] or (not serie.bersagli[i] and kmin < 2):
            continue
        membri = _cerca_membri(serie, passo, i, kmin)
        if membri is None:
            continue
        # Un membro mastro a figlio unico si risolve prima (TM 589/590): i suoi figli escono dal cammino e la somma
        # del totale si rifa'. Se con le catene risolte la somma torna, vale quella lettura; se no le catene si
        # disfano e restano i membri come sono (due gemelli «NOLEGGIO FIAT 600» sono fratelli, non mastro e foglia).
        prima = None
        catene = 0
        annidata = False
        for m in list(membri):
            if serie.vivo[m] and serie.candidabile[m] and ammessi[m] and valori[m]:
                sotto = _cerca_membri(serie, passo, m, 1)
                # solo una catena vera (un importo): un gruppo dentro un membro lo risolve la sua passata, con le sue
                # regole, non questa scorciatoia
                if sotto is not None and i not in sotto and sum(1 for f in sotto if valori[f]) == 1:
                    if prima is None:
                        prima = (serie.vivo[:], serie.candidabile[:], dict(serie.figli), passo[:])
                    _marca(serie, passo, m, sotto)
                    catene += 1
                    annidata = annidata or _annidata(serie, m, sotto)
        if prima is not None:
            nuovi = _cerca_membri(serie, passo, i, kmin)
            if nuovi is not None:
                membri = nuovi
                marcati += catene
            else:
                serie.vivo[:], serie.candidabile[:], passo[:] = prima[0], prima[1], prima[3]
                serie.figli = prima[2]
                if annidata:
                    # la somma torna solo contando un mastro e la sua foglia rientrata (1.260 + 1.260 = 2.520, 1561)
                    continue
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


def _punto_fisso(tutte: list[_Serie], passate: Callable[[_Serie], list[tuple[list[bool], int]]], *,
                 risultati: bool = True) -> tuple[int, int]:
    """Marca fino al punto fisso: per ogni passata k >= 2, poi k = 1 se il documento ha gia' mostrato un gruppo vero
    su quella colonna (una colonna di percentuali «100,00 100,00» fa solo catene). I risultati del conto economico
    (differenze) si cercano dopo, a punto fisso raggiunto: «A - B» prende «Totale valore della produzione» come
    membro, e il totale deve aver gia' trovato i suoi. Restituisce (totali marcati, gruppi k >= 2)."""
    piano = [(serie, passate(serie)) for serie in tutte]
    marcati = gruppi = 0
    gruppo_visto: set[int] = set()
    for fase in ((False, True) if risultati else (False,)):
        cambiato = True
        while cambiato:
            cambiato = False
            for k in range(max((len(p) for _, p in piano), default=0)):
                # fra i risultati prima le catene: «Totale proventi e oneri» = «Totale interessi» si chiude prima che
                # il risultato sotto lo cerchi come membro, e prima che l'utile prenda il risultato
                for kmin in ((1, 2) if fase else (2, 1)):
                    for serie, p in piano:
                        if k < len(p) and (kmin == 2 or serie.colonna in gruppo_visto):
                            ammessi = p[k][0] if fase else [a and not r for a, r in zip(p[k][0], serie.risultato)]
                            n = _risolvi(serie, ammessi, p[k][1], kmin)
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
    esiti = {d: _punto_fisso(_serie(doc), lambda serie, d=d: _forzata(serie, d), risultati=False) for d in (1, -1)}
    if esiti[1] != esiti[-1]:
        return 1 if esiti[1] > esiti[-1] else -1
    return -1


def marca_totali(doc: Documento) -> None:
    """Imposta `Riga.totale` e `Riga.figli[colonna]` sulle righe del prospetto, colonna per colonna; una voce i cui
    figli tornano su una colonna e non su un'altra resta totale dove torna, e lo scarto dell'altra va in
    `doc.avvisi`."""
    if not hasattr(doc.profilo, "tipo") and _PROFILO_ASSENTE not in doc.avvisi:
        doc.avvisi.append(_PROFILO_ASSENTE)      # `_su_schema` legge allora il documento come uno schema di legge
    for r in doc.righe:
        if r.parte == "prospetto":
            r.totale, r.figli, r.verso = False, {}, {}
    direzione = _direzione(doc)
    tutte = _serie(doc)
    for serie in tutte:
        _catene_all_unita(serie, direzione)
    _punto_fisso(tutte, lambda serie: _passate(serie, direzione))
    _coppie_parziali_totali(doc, tutte)
    for serie in tutte:
        for i, membri in serie.figli.items():
            totale = serie.righe[i]
            totale.totale = True
            totale.figli[serie.colonna] = tuple(serie.righe[m].id for m in sorted(membri))
            if serie.versi.get(i, 1) == -1:
                totale.verso[serie.colonna] = -1
    for r in doc.righe:
        if r.totale:
            r.figli = dict(sorted(r.figli.items()))
    _mastro_e_foglia(doc)
    _confronta_colonne(doc)
    _un_totale_per_colonna(doc)
    for r in doc.righe:
        r.verso = {c: v for c, v in r.verso.items() if c in r.figli}


# --------------------------------------------------------------------------------------
# Coppie parziali -> totali (Q1)
# --------------------------------------------------------------------------------------

def _coppie_parziali_totali(doc: Documento, tutte: list[_Serie]) -> None:
    """Q1 (proprietario, 2026-11-05): in una coppia (parziali, totali) del profilo i conti stanno nella colonna dei
    parziali e la voce che li somma in quella dei totali. Una voce della colonna dei totali prende per membri le celle
    dei parziali delle righe fra lei e la riga dei totali successiva (o precedente, se il documento stampa la voce
    dopo i conti: vale la direzione che chiude di piu'). I due livelli restano separati: un conto gia' membro di un
    totale dei parziali non conta (i suoi figli si sommano oppure lui, mai entrambi), e fra righe a rientri diversi
    contano le meno rientrate. Valgono le regole di sempre: tolleranza di un euro per la voce all'unita' (C6), una
    catena solo esatta (R14), un totale a zero solo con due membri (R16), e la voce che ha gia' un gruppo sulla sua
    colonna lo tiene. I figli stanno in `figli[parziali]`: e' la colonna su cui si leggono i loro importi."""
    coppie = getattr(doc.profilo, "coppie", {}) or {}
    if not coppie:
        return
    consumati: dict[int, set[int]] = defaultdict(set)
    for serie in tutte:
        for membri in serie.figli.values():
            consumati[serie.colonna].update(id(serie.righe[m]) for m in membri)
    propri = {(id(serie.righe[i]), serie.colonna) for serie in tutte for i in serie.figli}
    gruppi: dict[tuple[str, str], list[Riga]] = defaultdict(list)
    for r in doc.righe:
        if r.parte == "prospetto":
            gruppi[(r.lato, r.sezione)].append(r)
    # la testata della stampa ripetuta in cima a ogni pagina, o la riga di testata delle colonne, non chiude una voce
    saltate = _testate_di_pagina(doc) | {r.id for r in doc.righe if r.intestazione and (_testata(r) or _parametri(r))}
    for totali, parziali in sorted(coppie.items()):
        esiti = {d: [g for righe in gruppi.values()
                     for g in _gruppi_di_coppia(doc, righe, totali, parziali, d, consumati[parziali], propri, saltate)]
                 for d in (1, -1)}
        conta = {d: sum(len(g[2]) >= 2 for g in v) for d, v in esiti.items()}
        if not max(conta.values()):
            continue
        for t, membri, pieni, verso in esiti[1 if conta[1] > conta[-1] else -1]:
            t.totale = True
            t.figli[parziali] = tuple(m.id for m in membri)
            if verso == -1:
                t.verso[parziali] = -1


def _gruppi_di_coppia(doc: Documento, righe: list[Riga], totali: int, parziali: int, direzione: int,
                      consumati: set[int], propri: set[tuple[int, int]], saltate: set[str]
                      ) -> list[tuple[Riga, list[Riga], list[Riga], int]]:
    """Le voci della colonna `totali` di un lato e di una sezione che i parziali chiudono, nella direzione data (1: i
    conti dopo la voce)."""
    out = []
    for k, t in enumerate(righe):
        if totali not in t.celle or (id(t), totali) in propri:
            continue
        # fino alla riga dei totali dopo (o prima), o al titolo di una voce allo stesso rientro rimasta senza importo
        # («1.B.1.4 Concessioni, licenze …» fra i conti di 1.B.1.3 e quelli suoi, 1540)
        finestra = []
        passo = range(k + 1, len(righe)) if direzione == 1 else range(k - 1, -1, -1)
        for j in passo:
            r = righe[j]
            if totali in r.celle or (parziali not in r.celle and r.intestazione and r.id not in saltate
                                     and r.x is not None and t.x is not None and r.x <= t.x + _TOL_RIENTRO):
                break
            finestra.append(r)
        membri = [r for r in finestra[::direzione] if parziali in r.celle and id(r) not in consumati]
        xs = [r.x for r in membri if r.x is not None]
        if xs and max(xs) - min(xs) > _TOL_RIENTRO:
            membri = [r for r in membri if r.x is None or r.x <= min(xs) + _TOL_RIENTRO]
        pieni = [r for r in membri if r.celle[parziali].valore]
        if not pieni:
            continue
        bersaglio, tol = t.celle[totali].valore, _tolleranza_cella(doc, t, totali)
        versi = [1]
        if t.lato == "U" and not _marcata(t, totali) and any(_marcata(r, parziali) for r in pieni):
            versi.append(-1)
        chiusure = []
        for verso in versi:
            somma = sum((_valore_nel_totale(t, r, parziali, verso, _su_schema(doc)) for r in membri), Decimal(0))
            if abs(somma - bersaglio) <= tol:
                chiusure.append((somma != bersaglio, verso))
        if not chiusure:
            continue
        inesatta, verso = min(chiusure)
        # R22: un conto solo sotto la voce dei totali (all'unita') vale come catena anche in tolleranza: un'ipotesi
        if (len(pieni) == 1 and inesatta and not _all_unita(t, totali)) or (not bersaglio and len(pieni) != 2):
            continue
        out.append((t, membri, pieni, verso))
    return out


def _mastro_e_foglia(doc: Documento) -> None:
    """Un gruppo che conta due righe di cui una e' figlia dell'altra (su qualunque colonna) somma un mastro e la
    sua foglia: torna per coincidenza (2.999 + 2.999 = 5.998), non e' un totale. Le righe a zero su quella colonna
    non contano: non spostano la somma."""
    per_id = {r.id: r for r in doc.righe}
    for t in doc.righe:
        for c in list(t.figli):
            pieni = {f for f in t.figli[c] if c in per_id[f].celle and per_id[f].celle[c].valore}
            if any(set(g) & pieni for f in pieni for g in per_id[f].figli.values()):
                del t.figli[c]
                doc.avvisi.append(f"{_nome(t)}: sulla colonna {c + 1} i figli contano un mastro e la sua foglia, "
                                  f"somma scartata")
        t.totale = bool(t.figli)


def _nome(t: Riga) -> str:
    """Come si chiama una riga in un avviso: la sua etichetta, il codice, o la pagina e l'importo."""
    if t.etichetta or t.codice:
        return f"«{t.etichetta or t.codice}» (pagina {t.pagina})"
    importo = next(iter(t.celle.values())).valore if t.celle else None
    return f"la riga senza descrizione di pagina {t.pagina}" + (f" da {_euro(importo)}" if importo is not None else "")


def _un_totale_per_colonna(doc: Documento) -> None:
    """Invariante: su una colonna una riga e' figlia di un totale solo. Se due la contano, resta nel piu' interno
    (quello che sta dentro l'altro, o il piu' vicino) ed esce dall'altro, e si dichiara."""
    per_id = {r.id: r for r in doc.righe}
    pos = {r.id: k for k, r in enumerate(doc.righe)}
    colonne = {c for r in doc.righe for c in r.figli}
    for c in sorted(colonne):
        padri: dict[str, list[Riga]] = defaultdict(list)
        for t in doc.righe:
            for f in t.figli.get(c, ()):
                padri[f].append(t)
        for f, totali in padri.items():
            if len(totali) < 2:
                continue

            def dentro(a: Riga, b: Riga) -> bool:
                da_vedere, visti = list(b.figli.get(c, ())), set()
                while da_vedere:
                    x = da_vedere.pop()
                    if x == a.id:
                        return True
                    if x not in visti:
                        visti.add(x)
                        da_vedere += per_id[x].figli.get(c, ())
                return False

            interno = min(totali, key=lambda t: (-sum(dentro(t, o) for o in totali if o is not t),
                                                 abs(pos[t.id] - pos[f])))
            for t in totali:
                if t is interno:
                    continue
                t.figli[c] = tuple(x for x in t.figli[c] if x != f)
                if not t.figli[c]:
                    del t.figli[c]
                t.totale = bool(t.figli)
                doc.avvisi.append(f"{_nome(per_id[f])} era figlia di due totali sulla colonna {c + 1}: resta in "
                                  f"{_nome(interno)}, esce da {_nome(t)}")


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


def _colonne_affidabili(doc: Documento) -> set[int]:
    """Le colonne su cui il documento chiude davvero: almeno la meta' dei gruppi veri della colonna che ne ha di piu'.
    Una colonna di percentuali o di rettifiche letta come esercizio ne ha pochi o nessuno."""
    per_id = {r.id: r for r in doc.righe}
    gruppi: dict[int, int] = defaultdict(int)
    for t in doc.righe:
        for c, figli in t.figli.items():
            gruppi[c] += sum(1 for f in figli if c in per_id[f].celle and per_id[f].celle[c].valore) >= 2
    massimo = max(gruppi.values(), default=0)
    return {c for c, n in gruppi.items() if massimo and n * 2 >= massimo}


def _nome_colonna(c: Colonna) -> str:
    return f"colonna {c.indice + 1}" + (f" ({c.fine:%d/%m/%Y})" if c.fine else "")


def _confronta_colonne(doc: Documento) -> None:
    """Per ogni totale, le colonne dello stesso lato su cui i suoi figli non sono stati trovati: con gli stessi figli
    la somma torna (e i figli valgono anche li', se nessun altro totale li ha presi) o non torna, e si dichiara."""
    priorita = _priorita(doc)
    per_id = {r.id: r for r in doc.righe}
    schema = _su_schema(doc)
    colonne = {c.indice: c for c in doc.colonne if c.ruolo in _RUOLI_VALORE}
    presi: dict[int, set[str]] = defaultdict(set)
    non_chiude: dict[int, list[str]] = defaultdict(list)
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
            somma = sum((_valore_nel_totale(t, f, c, t.verso.get(riferimento, 1), schema)
                         for f in figli if c in f.celle), Decimal(0))
            scarto = t.celle[c].valore - somma
            if abs(scarto) <= _tolleranza_cella(doc, t, c):
                if not presi[c] & set(t.figli[riferimento]):
                    t.figli[c] = t.figli[riferimento]
                    if riferimento in t.verso:
                        t.verso[c] = t.verso[riferimento]
                    presi[c].update(t.figli[c])
                continue
            non_chiude[c].append(f"{_nome(t)} scarto {_euro(scarto)}")
        t.figli = dict(sorted(t.figli.items()))
    # un avviso per colonna, non uno per voce: la colonna che non chiude e' un fatto del documento
    for c, voci in sorted(non_chiude.items()):
        doc.avvisi.append(f"la {_nome_colonna(colonne[c])} non chiude in {len(voci)} "
                          f"{'voce' if len(voci) == 1 else 'voci'} i cui figli tornano su un'altra colonna "
                          f"(prime: {'; '.join(voci[:3])})")


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


def _nome_voce(r: Riga) -> set[str]:
    """Le parole del nome di una voce, coi punti delle sigle tolti e senza il lessico dei totali: «Totale I.V.A.:» e
    «I.V.A.» si chiamano entrambe {iva}. Il codice non conta."""
    testo = re.sub(r"(?<=\w)\.(?=\w)|\.(?=\s|$|:)", "", _norm(r.etichetta))
    return {t for t in re.split(r"[^0-9a-z]+", testo) if t and t not in ("totale", "totali")}


# una coppia «Chiave: valore» dei parametri della stampa («Ordine: Conti … Modulo: -BILAUE», «Stato: Confermati»)
_CHIAVE = re.compile(r"(?:^|\s)[^\W\d_]{3,}\s?:(?=\s|$)")


def _parametri(r: Riga) -> bool:
    return len(_CHIAVE.findall(r.etichetta)) >= 2


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
    saltate: set[str] = field(default_factory=set)            # righe-titolo che non sono il titolo di niente
    di_sezione: set[str] = field(default_factory=set)         # titoli che aprono la sezione: valgono a ogni rientro
    rientro: dict[str, float | None] = field(default_factory=dict)   # rientro di un totale: del titolo o dei figli
    sezioni: dict[int, str] = field(default_factory=dict)     # dal profilo: pagina -> "SP" | "CE" | …


def _lati(doc: Documento) -> list[_Lato]:
    gruppi: dict[tuple[str, str], list[Riga]] = defaultdict(list)
    for r in doc.righe:
        if r.parte == "prospetto":
            gruppi[(r.lato, r.sezione)].append(r)
    ripetute = _testate_di_pagina(doc)
    lati = []
    for righe in gruppi.values():
        lato = _Lato(righe, {r.id: k for k, r in enumerate(righe)}, sezioni=getattr(doc.profilo, "sezioni", {}) or {})
        for k, r in enumerate(righe):
            if r.intestazione and (_testata(r) or r.id in ripetute or _CONTROLLO.search(_norm(r.etichetta))
                                   or _parametri(r) or _conto_a_zero(righe, k)):
                lato.saltate.add(r.id)
        for r in righe:
            if r.celle:
                break
            if r.intestazione and r.id not in lato.saltate and not r.codice and r.etichetta.upper() == r.etichetta \
                    and set(re.split(r"[^a-z]+", _norm(r.etichetta))) & _APRE_SEZIONE and not _parole(r)[1]:
                lato.di_sezione.add(r.id)
        lati.append(lato)
    return lati


def _testate_di_pagina(doc: Documento) -> set[str]:
    """Le righe-titolo senza codice che si ripetono in testa a piu' pagine, a meno delle cifre («Ditta ALFA …
    pag. 2», «Compresi i saldi esercizio prec. Stato: Confermati»): sono la testata della stampa, non un mastro."""
    in_testa: dict[tuple[int, str], list[Riga]] = defaultdict(list)
    for r in doc.righe:
        if r.parte == "prospetto":
            in_testa[(r.pagina, r.lato)].append(r)
    pagine: dict[str, set[int]] = defaultdict(set)
    candidate: dict[str, list[Riga]] = defaultdict(list)
    for (pagina, _), righe in in_testa.items():
        for r in righe[:_RIGHE_DI_TESTA]:
            if r.intestazione and not r.codice:
                chiave = re.sub(r"\d+", "#", _norm(r.etichetta))
                pagine[chiave].add(pagina)
                candidate[chiave].append(r)
    return {r.id for chiave, righe in candidate.items() if len(pagine[chiave]) >= 2 for r in righe}


def _forma(codice: str) -> str:
    return re.sub(r"\d", "9", codice)


def _conto_a_zero(righe: list[Riga], k: int) -> bool:
    """Una riga-titolo col codice nella forma dei conti vicini, allo stesso rientro: e' un conto a saldo zero
    («10405 STELLE DI MIRABELLA» fra «10404 …» e «10406 …»), non il titolo dei conti che la seguono."""
    h = righe[k]
    if not h.codice or h.x is None:
        return False
    vicini = [next((r for r in reversed(righe[:k]) if r.celle and r.codice), None),
              next((r for r in righe[k + 1:] if r.celle and r.codice), None)]
    vicini = [v for v in vicini
              if v is not None and not v.totale and v.x is not None and abs(v.x - h.x) <= _TOL_RIENTRO]
    if not vicini:
        return False
    # stessa forma di codice, oppure (codice rovinato dall'OCR, «00126 3») etichetta dove stanno quelle dei conti, o
    # il titolo vero del mastro subito sopra, un livello piu' a sinistra («0225 FORNITORI» a 3, i conti a 51)
    sopra = next((r for r in reversed(righe[:k]) if r.intestazione and r.codice), None)
    return any(_forma(v.codice) == _forma(h.codice)
               or (h.x_etichetta is not None and v.x_etichetta is not None
                   and abs(v.x_etichetta - h.x_etichetta) <= _TOL_RIENTRO) for v in vicini) \
        or (sopra is not None and sopra.x is not None and sopra.x < h.x - _SCALINO)


def _figli_di(r: Riga, priorita: dict[int, int]) -> tuple[str, ...]:
    if not r.figli:
        return ()
    return r.figli[min(r.figli, key=lambda c: priorita.get(c, len(priorita)))]


_RISULTATO_ESERCIZIO = re.compile(r"\b(?:utile|perdita|perdite|risultato)\b.*\besercizio\b")
_DI_RISULTATO = re.compile(r"\b(?:risultato|utile|perdita|perdite|differenza)\b")


def _voce_impossibile(t: Riga, m: Riga, pos: dict[str, int]) -> bool:
    """Una riga di controllo `m` stampata sotto la riga non di controllo `t` non puo' esserne voce: chiude cio' che le
    sta sopra. Se ha un gruppo suo, l'eccezione e' un totale stampato sopra tutte le voci di lei (1540: «2 PASSIVO»
    sopra le voci di «A.14 TOTALE PATRIMONIO NETTO»); senza un gruppo suo, nessuna eccezione (1407: «C.16.d» = C.17 +
    «TOTALE C)» e' un'identita' per caso; 409: «Totale crediti» non e' voce di «esigibili entro»)."""
    if pos[m.id] < pos[t.id] or not (m.etichetta or m.codice) or not _di_controllo(m) or _di_controllo(t):
        return False
    figli = [f for fs in m.figli.values() for f in fs if f in pos]
    return not figli or min(pos[f] for f in figli) <= pos[t.id]


def _controllo_sotto(t: Riga, membri: list[Riga], pos: dict[str, int]) -> bool:
    """Un membro stampato sotto `t` che non puo' esserne figlio: una riga di controllo (`_voce_impossibile`); il
    risultato d'esercizio, sotto una riga del conto economico o di risultato («Risultato prima delle imposte» =
    imposte + utile e' un'identita' del conto). Sullo SP il patrimonio netto stampato prima delle sue voci conta
    l'utile."""
    return any(_membro_impossibile(t, m, pos) for m in membri)


def _membro_impossibile(t: Riga, m: Riga, pos: dict[str, int]) -> bool:
    if pos[m.id] < pos[t.id] or not (m.etichetta or m.codice):
        return False
    if _RISULTATO_ESERCIZIO.search(_norm(m.etichetta)):
        return t.sezione == "CE" or bool(_DI_RISULTATO.search(_norm(t.etichetta)))
    return _voce_impossibile(t, m, pos)


def _gruppi_incoerenti(doc: Documento, colonne_prova: set[int]) -> set[tuple[str, int]]:
    """R18: i gruppi (totale, colonna) che non provano un padre. Un gruppo prova solo se gli stessi membri chiudono il
    totale su ogni altra colonna di valori affidabile dove il totale e i membri stampano un importo: con x = 0 (le
    tabelle OCR) due colonne possono scegliere i membri ciascuna per conto suo («esigibili entro» su una, «Totale
    crediti» sull'altra, uguali di importo). E una riga di controllo o di risultato non e' membro di un totale
    stampato sopra di lei: «Risultato prima delle imposte» = imposte + utile e' un'identita' del conto, non una
    somma di figli. Ogni gruppo scartato si dichiara."""
    per_id = {r.id: r for r in doc.righe}
    pos = {r.id: k for k, r in enumerate(doc.righe)}
    colonne = {c.indice: c for c in doc.colonne if c.ruolo in _RUOLI_VALORE}
    schema = _su_schema(doc)
    out: set[tuple[str, int]] = set()
    for t in doc.righe:
        if t.parte != "prospetto":
            continue
        for c, figli in t.figli.items():
            membri = [per_id[f] for f in figli]
            if _controllo_sotto(t, membri, pos):
                out.add((t.id, c))
                doc.avvisi.append(f"{_nome(t)}: sulla colonna {c + 1} somma una riga di controllo stampata sotto di "
                                  f"lui, padre non verificato")
                continue
            # R18 simmetrica: con ogni altra colonna che ha un gruppo suo per questo totale, gli stessi membri fra le
            # righe con un importo non nullo su entrambe (un conto che c'e' su una colonna sola, «12) Accantonamenti»
            # solo nel corrente, o che vi vale zero non sposta l'altra somma); un disaccordo declassa entrambi
            for c2 in sorted(t.figli):
                if c2 == c:
                    continue

                def comuni(ids: tuple[str, ...]) -> set[str]:
                    return {f for f in ids if c in per_id[f].celle and c2 in per_id[f].celle
                            and per_id[f].celle[c].valore and per_id[f].celle[c2].valore}
                if comuni(figli) != comuni(t.figli[c2]):
                    if (t.id, c) not in out and (t.id, c2) not in out:
                        doc.avvisi.append(f"{_nome(t)}: le colonne {c + 1} e {c2 + 1} chiudono con figli diversi, "
                                          f"padre non verificato (R18)")
                    out.update({(t.id, c), (t.id, c2)})
            if (t.id, c) in out:
                continue
            # con una colonna affidabile senza gruppo suo, i membri ci devono sommare al totale
            for c2 in sorted(colonne_prova & set(colonne)):
                if c2 == c or c2 in t.figli or c2 not in t.celle or not any(c2 in m.celle for m in membri):
                    continue
                somma = sum((_valore_nel_totale(t, m, c2, t.verso.get(c, 1), schema) for m in membri if c2 in m.celle),
                            Decimal(0))
                if abs(somma - t.celle[c2].valore) > _tolleranza_cella(doc, t, c2):
                    out.add((t.id, c))
                    doc.avvisi.append(f"{_nome(t)}: i figli della colonna {c + 1} non chiudono la colonna {c2 + 1} "
                                      f"(scarto {_euro(t.celle[c2].valore - somma)}), padre non verificato (R18)")
                    break
    return out


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

    # 1. dalla somma. Una pretesa e' «vera» quando il gruppo ha almeno due importi diversi da zero su quella colonna:
    # una catena (un solo importo uguale) e' un'ipotesi, non una prova (R14), e da' un padre non verificato. Una
    # colonna che non e' la corrente non sposta un padre se il suo gruppo non e' vero: una colonna di percentuali o
    # di rettifiche letta come esercizio fa catene senza senso.
    correnti = {c.indice for c in doc.colonne if c.corrente}
    affidabili = _colonne_affidabili(doc)
    incoerenti = _gruppi_incoerenti(doc, correnti | affidabili)
    pretese: dict[str, list[tuple[tuple[int, int], str, bool]]] = defaultdict(list)
    pos = {r.id: k for k, r in enumerate(doc.righe)}
    for t in prospetto:
        for c, figli in t.figli.items():
            pieni = {f for f in figli if c in per_id[f].celle and per_id[f].celle[c].valore}
            for f in figli:
                m = per_id[f]
                if not _RISULTATO_ESERCIZIO.search(_norm(m.etichetta)) and _voce_impossibile(t, m, pos):
                    # una riga di controllo non ha per padre una riga stampata sopra di lei (201, 409); il risultato
                    # d'esercizio resta un'ipotesi (non verificata nel CE, `_controllo_sotto`)
                    continue
                # la somma prova solo i figli che la fanno: una riga a zero su quella colonna ci sta per posizione; e
                # solo se gli stessi figli chiudono il totale anche sulle altre colonne (R18)
                vero = len(pieni) >= 2 and f in pieni and (t.id, c) not in incoerenti
                pretese[f].append(((0 if vero else 1, priorita.get(c, len(priorita))), t.id,
                                   vero or c in correnti or c in affidabili))
    for f, lista in pretese.items():
        forti = [p for p in lista if p[2]] or lista
        (rango, _), t, _ = min(forti)
        per_id[f].padre, per_id[f].padre_verificato = t, rango == 0

    # Due colonne che danno alla stessa riga due totali diversi, uno dentro l'altro: vince il piu' interno, se la
    # sua somma e' vera. Una riga a zero sulla corrente («- esigibili oltre 0,00») la prende il totale di sopra, la
    # precedente la mette al suo posto.
    def antenati(t: str | None) -> list[str]:
        catena: list[str] = []
        while t and t not in catena:
            catena.append(t)
            t = per_id[t].padre
        return catena

    for f, lista in pretese.items():
        scelto = per_id[f].padre
        verificato = per_id[f].padre_verificato
        # un padre verificato si cambia solo per un altro verificato; uno non verificato anche per un'ipotesi di una
        # colonna affidabile
        dentro = {t for (rango, _), t, forte in lista
                  if (rango == 0 or (not verificato and forte)) and t not in (scelto, f)
                  and scelto in antenati(t)[1:] and f not in antenati(t)}
        if dentro:
            nuovo = max(dentro, key=lambda t: len(antenati(t)))
            per_id[f].padre = nuovo
            per_id[f].padre_verificato = any(t == nuovo and rango == 0 for (rango, _), t, _ in lista)

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
            # un totale, come un titolo, sta dentro solo a cio' che e' rientrato meno di lui (o del suo titolo): un
            # mastro fratello aperto allo stesso rientro non e' suo padre
            nodo = r.intestazione or bool(r.figli) or r.id in titoli
            trovato = _intestazione_sopra(lato, da, k, r, stretto=nodo, di_titolo=di_titolo)
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

    # «Totale X» con importo ma senza figli stampati (il mastro X non ha conti, o non tornano): chiude comunque il
    # gruppo dell'intestazione X sopra di se', che altrimenti resterebbe aperta su tutti i mastri fratelli seguenti
    for k, r in enumerate(righe):
        etichetta = _norm(r.etichetta)
        nome = _nome_voce(r)
        if not r.celle or r.totale or not _CONTROLLO.search(etichetta) or _CHIUSURA.search(etichetta) or not nome:
            continue
        j = k - 1
        while j >= 0 and not (righe[j].celle and _di_controllo(righe[j])):
            h = righe[j]
            if h.intestazione and h.id not in lato.saltate and h.id not in di_titolo and nome <= _nome_voce(h):
                titoli[r.id], di_titolo[h.id] = h, r.id
                lato.inizio[r.id] = j
                # il suo gruppo comincia dal titolo: un totale che lo contiene cerca il proprio titolo sopra di questo
                prima[r.id], ultima[r.id] = j, k
                break
            j -= 1
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
        while j >= 0 and righe[j].intestazione and (t.blocco is None or righe[j].blocco == t.blocco):
            sopra.append(righe[j])
            j -= 1
        sopra = [h for h in sopra if h.id not in lato.saltate]
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
    # Un totale stampato prima dei figli con subito sotto un'intestazione d'altro nome, rientrata non piu' di lui:
    # quell'intestazione sta dentro la sua somma. Vince il totale, e si dichiara.
    for r in righe:
        if not r.totale or not _figli_di(r, priorita) or not _parole(r)[0]:
            continue
        a, b = estremi(r)
        k = pos[r.id]
        if a == k and b > k + 1:
            h = righe[k + 1]
            if h.intestazione and h.id not in lato.saltate and _parole(h)[0] and not _di_sezione(h) \
                    and not _stessa_voce(r, h) and h.x is not None and r.x is not None \
                    and h.x <= r.x + _TOL_RIENTRO and not (h.codice and r.codice):
                doc.avvisi.append(f"«{h.etichetta}» (pagina {h.pagina}) sta sotto {_nome(r)}, che ne somma i conti: "
                                  f"vince il totale")
    for r in righe:
        if r.id in lato.inizio and (r.x is None or _di_controllo(r) or r.id in titoli):
            lato.rientro[r.id] = titoli[r.id].x if r.id in titoli else (rientro_figli(r) if r.figli else None)
    for r in righe:
        if r.id in lato.inizio:
            fine = ultima.get(r.id, pos[r.id])
            inizio = lato.inizio[r.id]
            if inizio < fine:
                lato.chiusi[fine] = min(lato.chiusi.get(fine, inizio), inizio)


_PAROLE_SP = {"patrimoniale", "attivo", "passivo", "attivita", "passivita"}
_PAROLE_CE = {"economico", "costi", "ricavi", "spese", "perdite", "profitti", "proventi", "oneri"}


def _stessa_sezione(lato: _Lato, h: Riga, r: Riga) -> bool:
    parole = set(re.split(r"[^a-z]+", _norm(h.etichetta)))
    tipo = "SP" if parole & _PAROLE_SP else "CE" if parole & _PAROLE_CE else ""
    di_h = lato.sezioni.get(h.pagina, "")
    for pagina in range(h.pagina, r.pagina + 1):
        s = lato.sezioni.get(pagina, "")
        if s in ("SP", "CE") and ((tipo and s != tipo) or (di_h in ("SP", "CE") and s != di_h)):
            return False
    return True


def _intestazione_sopra(lato: _Lato, da: int, k: int, r: Riga, *, stretto: bool,
                        di_titolo: dict[str, str]) -> Riga | None:
    """L'ultima intestazione sopra la posizione `da`, rientrata come `r` o meno (strettamente meno per
    un'intestazione); un gruppo gia' chiuso sopra si salta intero, e il titolo di un totale ancora aperto vale quel
    totale."""
    righe = lato.righe
    # il rientro di «Totale X:» allineato a destra non dice nulla: vale quello del suo titolo o dei suoi figli
    x = lato.rientro[r.id] if r.id in lato.rientro else r.x
    sezione: Riga | None = None
    j = da - 1
    while j >= 0:
        if j in lato.chiusi and j < k:
            j = lato.chiusi[j] - 1
            continue
        h = righe[j]
        j -= 1
        if r.blocco is not None and h.blocco != r.blocco:
            break           # un'altra tabella OCR, non il seguito di questa: non e' il titolo di nulla qui
        if not h.intestazione or h.id in lato.saltate:
            continue
        if h.id in lato.di_sezione and not stretto:
            # il titolo della sezione vale a ogni rientro per i conti, ma solo se sopra non c'e' niente di meglio, e
            # mai oltre una pagina di un'altra sezione: «ATTIVITA'» non e' il titolo dei costi di pagina 5
            if sezione is None and _stessa_sezione(lato, h, r):
                sezione = h
            continue
        sconosciuto = x is None or h.x is None
        totale = di_titolo.get(h.id)
        if totale is not None:
            # il titolo di un totale ancora aperto vale quel totale, ma solo per le righe rientrate piu' di lui: un
            # mastro fratello allo stesso rientro non ci sta dentro
            if lato.pos[totale] > k and (sconosciuto or h.x < x - _TOL_RIENTRO):
                return righe[lato.pos[totale]]
            continue
        if sconosciuto or (h.x < x - _TOL_RIENTRO if stretto else h.x <= x + _TOL_RIENTRO):
            return h
    return sezione
