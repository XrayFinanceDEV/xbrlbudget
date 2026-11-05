"""Righe logiche del documento: etichetta, codice conto, una cella per colonna, sezione e lato.

Compone i passi 1-4 (importi, righe fisiche, colonne, lati) e vi applica le regole di lettura che
l'importatore attuale sparge in piu' copie (inventario §1.2, §1.6, §1.8): importo legato alla colonna dal
bordo destro (fuori colonna torna nell'etichetta), parentesi staccata ricucita, importo orfano riattaccato,
didascalia a capo, margini e piedi tolti, riporti e anagrafiche scartati, codice conto separato, sezione SP/CE
dai titoli e dalla continuazione di pagina. Non classifica e non somma: legge e dichiara.
"""
from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

import fitz

from importers.lettore.colonne import Colonna, colonna_di
from importers.lettore.geometria import Parola, RigaFisica, parole_pagina, righe_fisiche
from importers.lettore.importi import Importo, leggi_importo
from importers.lettore.totali import assegna_padri, marca_totali
# Le regole di livello documento stanno nel profilo (Task 5-bis): qui si leggono dal Profilo, calcolato prima.
from importers.lettore.profilo import (
    _PERCORSO_LEGGE, _RUOLI_ANALISI, _SEPARATORE, _STACCO_SEPARATORE, _SEPARATORE_CODICE, _TOL_X_CODICE, _VALUTA, _VOCE_NUMERATA,
    FormaCodice, Profilo, TabellaNota, _capitale_in_anagrafica, _codice_in_testa, _decimali, _in_colonna, _norm,
    _rimando_di_nota, _valuta_davanti, _voce_di_legge, marcatore_dopo, profilo_documento, senza_filetti)
from importers.schema_legge_generico import _forma_strutturale, _intestazione
from importers.xbrl_reso_parser import _frase_aperta

_X0_MINIMO = 150.0          # come `colonne._in_colonna`
# Una riga senza importi piu' vicina di cosi' (frazione dell'interlinea) alla riga sopra ne e' il seguito
# (`schema_legge_generico._A_CAPO`).
_A_CAPO = 0.7
# Un importo senza didascalia a non piu' di tanti punti dalla didascalia senza importi e' il suo
# (`xbrl_reso_parser._DISTANZA_IMPORTO_ORFANO`); oppure i riquadri si sovrappongono per meta' altezza
# (`schema_legge_generico._riattacca_importi`).
_DISTANZA_ORFANO = 8.0
_ADIACENTE = 1.5
_SOVRAPPOSIZIONE_ORFANO = 0.5
_STACCO_PARENTESI = 6.0
_SCADENZA = {"mesi", "mese", "anni", "anno", "m"}
_ORDINE_LATI = {"U": 0, "L": 1, "R": 2}

# Anagrafiche e riporti (`situazione_contabile_parser._be_collect_side_facts`): non sono righe del prospetto.
_ANAGRAFICA = re.compile(r"^(?:VIA|VIALE|V\.LE|PIAZZA|P\.ZZA|CORSO|C\.F\.|P\.\s?IVA|REA)\b|CODICE FISCALE|PARTITA IVA")
# A parola intera: «SEGUENTE» («esercizio seguente») non e' un riporto.
_RIPORTO = re.compile(r"\bA\s+RIPORT\w*|\bRIPORTO\b|\bRIPORTARE\b|\bSEGUE\b|\bPROGRESSIV\w*")
_IMPORTI = re.compile(r"\bIMPORTI\b")
# Il token davanti a un numero che lo fa un riferimento, non un importo («art. 2423», «REA n. 1234567»).
_RIFERIMENTO = {"art.", "art", "artt.", "n.", "n", "nr.", "nr", "n°", "num.", "numero", "rea", "p.iva", "piva",
                "p.i.", "iva", "c.f.", "cf", "cap", "cap.", "c.a.p.", "ateco", "codice", "cod.", "tel.", "fax",
                "prot.", "comma", "lett.", "mutuo", "contratto"}
_ANNO = re.compile(r"^(?:19|20)\d{2}$")
# La voce IV-CEE senza cifre davanti al conto («AI 301.00001», «D 230.00011», budget_1548): fa parte del codice.
_TAG_IVCEE = re.compile(r"^[a-e](?:[ivx]+\d*[a-z]?|\d+[a-z]?)?$")
# Un trattino in colonna seguito da una parola piu' lontana di cosi' e' una cella, e la parola sta nella colonna dopo
# («Utili portati a nuovo - U» a 77 pt, budget_202 p16; «- A,B,C,D» a 9,8 pt, budget_1315 p17); un separatore di
# descrizione e' a uno spazio (fino a 6,5 pt misurati, «lavoro - avvenuta» budget_255).
_STACCO_CELLA_TESTO = _STACCO_SEPARATORE
# Marcatori di una riga di mastro che cambiano fra la riga col totale e la sua ripetizione in testa a pagina
# («0105 I.V.A. A A A IE» e «0105 I I.V.A.», budget_680).
_MARCATORE = re.compile(r"^[A-Z]{1,2}$")
_FORME_SEGNO = {"parentesi": "tra parentesi", "meno": "col meno davanti", "meno-finale": "col meno in coda"}


@dataclass
class Riga:
    id: str                      # "p{pagina}r{n}{lato}", stabile fra due letture dello stesso file
    pagina: int
    y: float
    lato: str                    # "U" | "L" | "R"
    sezione: str                 # "SP" | "CE" | ""
    codice: str                  # "" se assente
    etichetta: str
    celle: dict[int, Importo]    # indice di Colonna -> importo; una colonna assente = cella vuota
    totale: bool = False         # Task 6
    figli: dict[int, tuple[str, ...]] = field(default_factory=dict)   # per colonna, id dei figli (Task 6): la
                                 # colonna su cui si leggono i loro importi; per una voce della colonna dei totali di
                                 # una coppia (`Profilo.coppie`, Q1) e' la colonna dei parziali
    intestazione: bool = False   # riga-titolo senza importi (mastro o gruppo stampato come titolo)
    padre: str | None = None     # id della riga madre (Task 6)
    padre_verificato: bool = False   # True se i figli del padre sommano al suo totale stampato
    verso: dict[int, int] = field(default_factory=dict)   # per colonna dei figli: -1 quando i conti a marcatore D/A
                                 # chiudono la voce col segno rovesciato (passivo o ricavi su una sezione unica, Q2)
    percorso: tuple[str, ...] = ()   # etichette degli antenati, dalla sezione al padre (Task 6)
    parte: str = "prospetto"     # "prospetto" | "nota" | "altro", dal profilo; i Task 6-8 leggono solo il prospetto
    tabella: int | None = None   # per una riga della nota: indice in `profilo.tabelle_nota`, e le chiavi di `celle`
                                 # sono le colonne di quella tabella, non quelle del documento
    x: float | None = None       # bordo sinistro del testo (codice o etichetta), il rientro; None = soli importi
    x_etichetta: float | None = None   # bordo sinistro dell'etichetta dopo il codice; None = senza codice
    blocco: int | None = None    # dalle tabelle OCR: il blocco di tabelle da cui viene la riga (una tabella e i suoi
                                 # seguiti); la ricerca di un'intestazione sopra non lo attraversa. None dal PDF


@dataclass
class Documento:
    righe: list[Riga]
    colonne: list[Colonna]
    contrapposto: bool           # il verdetto del profilo; il lato delle righe resta fisico
    avvisi: list[str]            # della lettura delle righe; quelli del documento stanno in `profilo.avvisi`
    profilo: Profilo


@dataclass
class _Pezzo:
    """Una riga fisica di un lato, prima delle unioni."""
    pagina: int
    lato: str
    y: float                     # centro della prima riga fisica
    y_ultima: float              # centro dell'ultima riga fisica unita
    y0: float
    y1: float
    sezione: str
    codice: str
    etichetta: str
    celle: dict[int, Importo]
    parole: list[str] = field(default_factory=list)   # etichetta in token, senza il codice
    conto: bool = False                               # conto senza importo: non un titolo
    forma: FormaCodice | None = None                  # la forma del profilo del codice, alla sua posizione
    x_codice: float = 0.0
    x_etichetta: float | None = None
    parte: str = "prospetto"
    tabella: int | None = None
    x_testo: float | None = None                      # bordo sinistro del primo token di testo: il rientro della riga


# --------------------------------------------------------------------------------------
# Token
# --------------------------------------------------------------------------------------

def _normalizza(testo: str) -> str:
    """Il token come lo legge `leggi_importo`: meno Unicode e trattino lungo davanti alle cifre, spazi non
    separabili tolti, marcatore D/A attaccato («1.234,56D») staccato. Solo se il risultato e' un importo;
    altrimenti il testo resta com'e' stampato."""
    t = testo
    for spazio in ("\u00a0", "\u202f", "\u2009"):
        t = t.replace(spazio, "")
    t = re.sub("^(\\(?)[\u2212\u2013](?=\\d)", r"\1-", t)
    t = re.sub("(?<=\\d)[\u2212\u2013](\\)?)$", r"-\1", t)
    m = re.fullmatch(r"(.*\d\)?)([DA])", t)
    if m:
        t = f"{m.group(1)} {m.group(2)}"
    return t if t != testo and leggi_importo(t) is not None else testo


def _ricuci(parole: list[Parola], stampati: dict[Parola, str]) -> list[Parola]:
    """Normalizza i token e ricuce la parentesi aperta staccata dall'importo («(» + «1.234,56)»). In
    `stampati` resta il testo come stampato di ogni parola cambiata, per `Importo.testo`."""
    out: list[Parola] = []
    for originale in parole:
        p = Parola(originale.x0, originale.y0, originale.x1, originale.y1, _normalizza(originale.testo))
        if p.testo != originale.testo:
            stampati[p] = originale.testo
        prima = out[-1] if out else None
        if (prima is not None and prima.testo == "(" and p.x0 - prima.x1 <= _STACCO_PARENTESI
                and p.testo[:1].isdigit()):
            unita = Parola(prima.x0, min(prima.y0, p.y0), p.x1, max(prima.y1, p.y1), "(" + p.testo)
            stampati[unita] = "(" + stampati.get(p, p.testo)
            out[-1] = unita
            continue
        out.append(p)
    return out


# --------------------------------------------------------------------------------------
# Celle
# --------------------------------------------------------------------------------------

def _riferimento_davanti(parole: list[Parola], i: int) -> bool:
    if i == 0:
        return False
    prima = re.split(r"['\u2019]", parole[i - 1].testo.lower().strip(":"))[-1]
    return prima in _RIFERIMENTO


# Q2: in una colonna a marcatore (`Profilo.marcatori`) il D/A staccato dopo l'importo e' il segno della cella. La colonna
# e' la verita' sul lato (CLAUDE.md): sul lato sinistro delle contrapposte (attivo, costi) e su una sezione unica vale
# il saldo in dare, D positivo e A negativo (come «1.234,56 A» attaccato, `leggi_importo`); sul lato destro (passivo,
# ricavi) A positivo e D negativo. Su una sezione unica una voce del passivo o dei ricavi chiude i suoi conti col segno
# rovesciato: lo decide la somma (`totali`, `Riga.verso`), non il marcatore.
_MARCATORE_NEGATIVO = {"U": "A", "L": "A", "R": "D"}


def _celle_del_lato(parole: list[Parola], colonne: list[Colonna], lato: str, pagina: int,
                    avvisi: list[str], stampati: dict[Parola, str],
                    intere: frozenset[int] = frozenset(),
                    marcatori: frozenset[int] = frozenset()) -> tuple[dict[int, Importo], list[Parola]]:
    """(celle per colonna, parole dell'etichetta). Un importo e' una cella solo nella sua colonna e sul suo
    lato; fuori colonna, seguito da una durata («12 mesi») o dentro una frase dopo una valuta («euro 516,46
    di valore unitario», o in un'anagrafica col capitale sociale) torna nell'etichetta. Un anno nudo su una
    riga senza altri importi resta testo. Due importi nella stessa colonna: la cella non si legge. La valuta
    davanti a una cella, o in coda all'etichetta, si toglie. In una colonna di `marcatori` il D/A dopo l'importo ne
    e' il segno e lascia l'etichetta."""
    trovati = [_in_colonna(p, colonne, intere) for p in parole]
    for i, p in enumerate(parole[:-1]):
        # l'importo seguito da un rimando di nota («46.078 (1)») sta nella colonna dove il rimando la chiude
        if trovati[i] is None and _rimando_di_nota(parole, i + 1):
            trovati[i] = _in_colonna(Parola(p.x0, p.y0, parole[i + 1].x1, p.y1, p.testo), colonne, intere)
    trovati = [None if t is None or t[1].lato != lato or _rimando_di_nota(parole, i)
               or (leggi_importo(p.testo) is None and _riferimento_davanti(parole, i)) else t
               for i, (p, t) in enumerate(zip(parole, trovati))]
    # un trattino seguito da una parola e' un separatore («PRESTAZ. - IMPRESE»), e un intero nudo davanti a quel
    # separatore o a una parola e' un codice («Codice attivita' 255100 - LAVORAZ.»): si legge da destra, perche'
    # il trattino decide per l'intero. Davanti a un importo, o a una parola lontana, nella colonna dopo («Riserve
    # statutarie - A,B,C,D», R9), il trattino resta una cella zero.
    separatori: set[int] = set()
    for i in range(len(parole) - 2, -1, -1):
        dopo = parole[i + 1].testo
        in_colonna = parole[i].testo == "-" and parole[i + 1].x0 - parole[i].x1 > _STACCO_CELLA_TESTO
        segue_testo = (any(ch.isalpha() for ch in dopo) and not in_colonna) or (i + 1 in separatori and dopo == "-")
        if trovati[i] is not None and segue_testo and (
                parole[i].testo == "-" or leggi_importo(parole[i].testo) is None):
            trovati[i] = None
            separatori.add(i)
    anni = {i for i, (p, t) in enumerate(zip(parole, trovati)) if t is not None and _ANNO.match(p.testo)}
    if anni and all(t is None or i in anni for i, t in enumerate(trovati)):
        trovati = [None if i in anni else t for i, t in enumerate(trovati)]
    capitale = _capitale_in_anagrafica(parole, colonne)
    celle: dict[int, Importo] = {}
    sedi: dict[int, list[Parola]] = {}
    testo: list[int] = []
    segni: set[int] = set()
    for i, (p, trovato) in enumerate(zip(parole, trovati)):
        if i in segni:
            continue
        dopo = parole[i + 1].testo.lower().strip(".,:;") if i + 1 < len(parole) else ""
        if (trovato is None or dopo in _SCADENZA
                or (_valuta_davanti(parole, i)
                    and (capitale or (any(ch.isalpha() for ch in dopo) and dopo not in _VALUTA)))):
            testo.append(i)
            continue
        imp, c = trovato
        sedi.setdefault(c.indice, []).append(p)
        stampato = stampati.get(p, p.testo)
        marcatore = marcatore_dopo(parole, i) if c.indice in marcatori else None
        if marcatore is not None:
            segni.add(i + 1)
            valore = -imp.valore if marcatore == _MARCATORE_NEGATIVO[lato] else imp.valore
            imp, stampato = Importo(valore, imp.forma, f"{stampato} {marcatore}"), f"{stampato} {marcatore}"
        celle[c.indice] = Importo(imp.valore, imp.forma, stampato)
    for indice, ps in sedi.items():
        # davanti a un importo vero, l'intero nudo nella stessa colonna cede (budget_1438, colonne della nota)
        nudi = [p for p in ps if leggi_importo(p.testo) is None]
        if len(ps) > 1 and len(nudi) < len(ps):
            testo.extend(parole.index(p) for p in nudi)
            ps = [p for p in ps if p not in nudi]
            celle[indice] = next(Importo(t[0].valore, t[0].forma, stampati.get(q, q.testo))
                                 for q, t in zip(parole, trovati) if q is ps[-1])
        if len(ps) > 1 and not any(leggi_importo(p.testo) is not None for p in ps):
            # solo interi nudi: le colonne di una tabella della nota, non quelle del documento; restano testo
            del celle[indice]
            testo.extend(parole.index(p) for p in ps)
            continue
        if len(ps) > 1:
            del celle[indice]
            testo.extend(parole.index(p) for p in ps)
            avvisi.append(f"pagina {pagina}: due importi nella colonna {indice} sulla stessa riga "
                          f"({' '.join(p.testo for p in ps)}): cella non letta")
    in_cella = set(range(len(parole))) - set(testo) - segni
    etichetta = [parole[i] for i in sorted(testo, key=lambda i: parole[i].x0)
                 if not (_norm(parole[i].testo) in _VALUTA and i + 1 in in_cella)]
    while etichetta and _norm(etichetta[-1].testo) in _VALUTA:
        etichetta.pop()
    return celle, etichetta


def _compatta(forma: str) -> str:
    """«9 / 9 / 9» -> «9/9/9»: un codice spaziato ha la forma di quello compatto."""
    return re.sub(r"\s*([/.\-])\s*", r"\1", forma)


def _famiglia(forma: str) -> str:
    """«99/99/***» -> «9/9/9»: la forma senza le lunghezze."""
    return re.sub(r"[9*]+", "9", _compatta(forma))


@dataclass
class _Codice:
    codice: str
    etichetta: list[str]
    forma: FormaCodice | None = None     # la forma del profilo con la stessa sagoma, alla posizione del codice
    x_etichetta: float | None = None


def _alla_posizione(forme: list[FormaCodice], x0: float, x_etichetta: float | None) -> list[FormaCodice]:
    """Le forme allineate a un codice: prima sul codice, poi sull'etichetta."""
    sul_codice = [f for f in forme if abs(f.x0 - x0) <= _TOL_X_CODICE]
    sull_etichetta = [f for f in forme if x_etichetta is not None and abs(f.x_etichetta - x_etichetta) <= _TOL_X_CODICE
                      and f not in sul_codice]
    return sul_codice + sull_etichetta


def _codice(testo: list[Parola], forme: list[FormaCodice]) -> _Codice:
    """Il codice conto in testa e le parole dell'etichetta, dalle forme di codice del profilo. Il codice in testa
    (`profilo._codice_in_testa`) e' un codice se ha una forma del documento, o se e' della famiglia di una forma
    allineata a lui (sul codice o sull'etichetta) e non piu' lungo di lei (il mastro «0103», «48», «03/05/***» sopra
    i conti; non «12/3456» accanto ai codici «10/01»). Senza, resta nell'etichetta. Un codice piu'
    lungo di ogni forma si accorcia fino a una che c'e' («70110 1000 FOGLI»), mai dentro un codice («4 / 5 / 1»,
    «6 / x»). La voce IV-CEE senza cifre davanti al conto («AI 301.00001») conta come la voce con le cifre delle forme
    («A9 999.99999»); il percorso di una voce di legge stampato in testa («1.B.2.1») non e' un codice. `forma` e' la
    forma della stessa sagoma alla posizione del codice: e' lei, non la sagoma, a dire se una riga senza importi e' un
    titolo o un conto (`_conti_e_titoli`)."""
    parole = [p.testo for p in testo]
    nessuno = _Codice("", parole)
    if not forme or not testo:
        return nessuno
    voce = 1 if (len(testo) > 1 and _TAG_IVCEE.match(parole[0].lower()) and not re.search(r"\d", parole[0])) else 0
    if _PERCORSO_LEGGE.match(parole[voce]):
        return nessuno        # il percorso della voce di legge («1.B.2.1»), non un conto
    trovato = _codice_in_testa(testo[voce:], cifre_min=1)
    if trovato is None:
        return nessuno
    sagome, n = trovato[0].split(" "), trovato[1] + voce
    for m in range(n, voce, -1):
        if _SEPARATORE_CODICE.match(parole[m - 1]) or (m < len(parole) and parole[m] in ("/", ".")) or (
                m < n and _SEPARATORE_CODICE.match(parole[m])):
            continue
        forma = _compatta(" ".join(sagome[:m - voce]))
        k = m
        while k < len(parole) and _SEPARATORE.match(parole[k]):
            k += 1
        x_etichetta = testo[k].x0 if k < len(testo) else None
        if voce:
            # la forma della voce con le cifre, senza la voce
            stesse = [f for f in forme if " " in f.forma and re.search(r"[A-Za-z]", f.forma.split(" ")[0])
                      and _compatta(f.forma.split(" ", 1)[1]) == forma]
            famiglia = False
        else:
            stesse = [f for f in forme if _compatta(f.forma) == forma]
            famiglia = any(_famiglia(f.forma) == _famiglia(forma) and len(forma) <= len(_compatta(f.forma))
                           for f in _alla_posizione(forme, testo[0].x0, x_etichetta))
        if k >= len(parole):
            return nessuno    # un numero da solo, senza etichetta, non e' un conto
        if stesse or famiglia:
            posizione = _alla_posizione(stesse, testo[0].x0, x_etichetta)
            return _Codice(" ".join(parole[:m]), parole[k:], posizione[0] if posizione else None, x_etichetta)
    return nessuno


def _chiave_mastro(codice: str, etichetta: str) -> tuple[str, str]:
    return codice, " ".join(t for t in etichetta.split() if not _MARCATORE.match(t))


def _ruoli_delle_forme(sequenze: list[list[_Pezzo]]) -> dict[int, str]:
    """Per forma del profilo (alla sua posizione), «foglia» se le sue righe sono per lo piu' seguite da una riga della
    stessa forma, «testa» se per lo piu' da una riga con un codice piu' rientrato (il mastro sopra i suoi conti)."""
    voti: dict[int, Counter] = {}
    for seq in sequenze:
        con_codice = [p for p in seq if p.codice]
        for a, b in zip(con_codice, con_codice[1:]):
            if a.forma is None:
                continue
            conta = voti.setdefault(id(a.forma), Counter())
            if b.forma is a.forma:
                conta["foglia"] += 1
            elif b.x_codice > a.x_codice + _TOL_X_CODICE or (
                    a.x_etichetta is not None and b.x_etichetta is not None
                    and b.x_etichetta > a.x_etichetta + _TOL_X_CODICE):
                conta["testa"] += 1
    return {k: ("foglia" if v["foglia"] > v["testa"] else "testa") for k, v in voti.items() if v["foglia"] != v["testa"]}


def _conti_e_titoli(sequenze: list[list[_Pezzo]]) -> None:
    """Una riga senza importi con un codice e' un conto a saldo zero o un titolo. E' un conto se la sua forma (alla
    sua posizione) e' una foglia (`_ruoli_delle_forme`; senza voti, se la forma porta per lo piu' importi). Resta un
    titolo: in una forma di testa, senza una forma alla sua posizione, la ripetizione di un mastro gia' stampato col
    suo totale (stesso codice e stessa etichetta: budget_680 riusa i codici dei sottoconti fra mastri, il codice da
    solo non basta), la voce di legge col codice del gestionale («AD000000 D) RATEI E RISCONTI», budget_672). Decide
    solo titolo o conto, mai la parentela."""
    ruoli = _ruoli_delle_forme(sequenze)
    gia_stampati: set[tuple[str, str]] = set()
    for seq in sequenze:
        for p in seq:
            if p.celle:
                if p.codice:
                    gia_stampati.add(_chiave_mastro(p.codice, p.etichetta))
                continue
            f = p.forma
            if not p.codice or f is None:
                continue
            ruolo = ruoli.get(id(f)) or ("foglia" if f.con_importi > f.senza_importi else "testa")
            p.conto = (ruolo == "foglia" and _chiave_mastro(p.codice, p.etichetta) not in gia_stampati
                       and not _voce_di_legge(p.etichetta) and not _VOCE_NUMERATA.match(_norm(p.etichetta)))


def _forma_negativo(testo: str) -> str | None:
    """La forma in cui e' stampato un importo negativo (come `profilo._negativi`); None per il marcatore D/A."""
    t = _normalizza(testo).replace("€", "").strip()
    if re.search(r"\s[DA]$", t):
        return None
    if t.startswith("(") and t.endswith(")"):
        return "parentesi"
    if t.startswith("-"):
        return "meno"
    if t.rstrip(")").endswith("-"):
        return "meno-finale"
    return None


def _segni_fuori_profilo(celle: dict[int, Importo], colonne: list[Colonna], negativi: frozenset[str],
                         pagina: int, avvisi: list[str]) -> None:
    """Un negativo stampato in una forma che il documento non usa («123-» dove i negativi sono tra parentesi) si
    legge come negativo, ma si dichiara. Le colonne di differenza e di percentuale non contano."""
    viste = negativi & set(_FORME_SEGNO)
    if not viste:
        return
    ruoli = {c.indice: c.ruolo for c in colonne}
    for indice, imp in celle.items():
        if imp.valore >= 0 or ruoli.get(indice) in _RUOLI_ANALISI:
            continue
        forma = _forma_negativo(imp.testo)
        if forma is not None and forma not in viste:
            avvisi.append(f"pagina {pagina}: negativo «{imp.testo}» stampato {_FORME_SEGNO[forma]}, ma il documento "
                          f"stampa i negativi {' o '.join(_FORME_SEGNO[v] for v in sorted(viste))}: letto come "
                          f"negativo, da verificare")


# --------------------------------------------------------------------------------------
# Unioni: importo orfano, didascalia a capo
# --------------------------------------------------------------------------------------

def _passo(pezzi: list[_Pezzo]) -> float:
    salti = [b.y - a.y for a, b in zip(pezzi, pezzi[1:]) if b.y - a.y > 0.5]
    return statistics.median(salti) if salti else 0.0


def _sovrapposizione(a: _Pezzo, b: _Pezzo) -> float:
    altezza = a.y1 - a.y0
    return max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0)) / altezza if altezza > 0 else 0.0


def _unisci(sopra: _Pezzo, sotto: _Pezzo, *, sillaba: bool = False) -> _Pezzo:
    etichetta = (sopra.etichetta[:-1] + sotto.etichetta if sillaba
                 else " ".join(t for t in (sopra.etichetta, sotto.etichetta) if t))
    return _Pezzo(sopra.pagina, sopra.lato, sopra.y, max(sopra.y_ultima, sotto.y_ultima),
                  min(sopra.y0, sotto.y0), max(sopra.y1, sotto.y1), sopra.sezione,
                  sopra.codice or sotto.codice, etichetta, {**sopra.celle, **sotto.celle},
                  sopra.parole + sotto.parole, sopra.conto or sotto.conto, parte=sopra.parte, tabella=sopra.tabella,
                  forma=sopra.forma or sotto.forma, x_codice=sopra.x_codice if sopra.codice else sotto.x_codice,
                  x_etichetta=sopra.x_etichetta if sopra.codice else sotto.x_etichetta,
                  x_testo=sopra.x_testo if sopra.x_testo is not None else sotto.x_testo)


def _stessa_parte(a: _Pezzo, b: _Pezzo) -> bool:
    """Due pezzi si uniscono solo nella stessa parte e nella stessa tabella: le chiavi delle celle sono colonne di
    tabelle diverse."""
    return a.parte == b.parte and a.tabella == b.tabella


def _solo_importi(p: _Pezzo) -> bool:
    return bool(p.celle) and not p.etichetta and not p.codice


def _didascalia_nuda(p: _Pezzo) -> bool:
    return not p.celle and bool(p.etichetta)


def _riattacca_orfani(pezzi: list[_Pezzo]) -> list[_Pezzo]:
    """Un importo stampato qualche punto sopra o sotto la propria didascalia senza importi le si riattacca
    (a parita', a quella sopra)."""
    out = list(pezzi)
    i = 0
    while i < len(out):
        p = out[i]
        if _solo_importi(p):
            vicine = [j for j in (i - 1, i + 1) if 0 <= j < len(out) and _didascalia_nuda(out[j])
                      and _stessa_parte(p, out[j])
                      and (abs(out[j].y_ultima - p.y) <= _DISTANZA_ORFANO
                           or _sovrapposizione(p, out[j]) >= _SOVRAPPOSIZIONE_ORFANO)]
            if vicine:
                j = min(vicine, key=lambda k: (abs(out[k].y - p.y), k))
                a, b = (out[j], p) if j < i else (p, out[j])
                out[min(i, j)] = _unisci(a, b)
                del out[max(i, j)]
                i = min(i, j)
                continue
        i += 1
    return out


def _strutturale(etichetta: str) -> bool:
    return bool(_forma_strutturale(etichetta) or _intestazione(etichetta))


def _a_capo(pezzi: list[_Pezzo]) -> list[_Pezzo]:
    """Le didascalie andate a capo (`_grezze_pdf` e `_unisci_a_capo`): una riga senza importi ne' codice
    piu' vicina di 0,7 interlinee alla riga sopra ne e' il seguito, qualunque sia la maiuscola; la riga senza
    importi che finisce a meta' frase o a meta' parola si completa con quella sotto; il seguito in minuscolo
    senza importi di una riga che li ha gia' le si aggiunge. Vale anche per le righe-conto."""
    passo = _passo(pezzi)
    out: list[_Pezzo] = []
    for p in pezzi:
        if out and _stessa_parte(out[-1], p):
            sopra = out[-1]
            nuda = not p.celle and not p.codice and p.etichetta and not _strutturale(p.etichetta)
            salto = p.y - sopra.y_ultima
            vicina = passo and salto < _A_CAPO * passo
            # le altre due regole non guardano l'interlinea, ma non scavalcano un vuoto (una riga saltata)
            adiacente = not passo or salto <= _ADIACENTE * passo
            if nuda and vicina:
                out[-1] = _unisci(sopra, p)
                continue
            sillaba = bool(re.search(r"[^\W\d_]-$", sopra.etichetta))
            if (adiacente and not sopra.celle and sopra.etichetta and not p.codice and p.etichetta
                    and not _intestazione(sopra.etichetta) and not _strutturale(p.etichetta)
                    and (_frase_aperta(sopra.etichetta) or sillaba)):
                out[-1] = _unisci(sopra, p, sillaba=sillaba)
                continue
            if adiacente and sopra.celle and nuda and p.etichetta[:1].islower():
                out[-1] = _unisci(sopra, p)
                continue
        out.append(p)
    return out


# --------------------------------------------------------------------------------------
# Lettura
# --------------------------------------------------------------------------------------

@dataclass
class _Lettura:
    """Come si legge una riga fisica: le colonne su cui stanno le sue celle e le regole del profilo che valgono li'."""
    parte: str
    tabella: int | None
    colonne: list[Colonna]
    confine: float | None
    intere: frozenset[int] = frozenset()
    negativi: frozenset[str] = frozenset()
    marcatori: frozenset[int] = frozenset()


def _pezzi_della_riga(r: RigaFisica, sezione: str, lettura: _Lettura, forme: list[FormaCodice],
                      avvisi: list[str], stampati: dict[Parola, str]) -> list[_Pezzo]:
    """Una riga fisica -> un pezzo per lato (uno solo senza confine)."""
    if lettura.confine is None:
        gruppi = {"U": r.parole}
    else:
        gruppi = {"L": [p for p in r.parole if (p.x0 + p.x1) / 2 < lettura.confine],
                  "R": [p for p in r.parole if (p.x0 + p.x1) / 2 >= lettura.confine]}
    out = []
    for lato, parole in gruppi.items():
        if not parole:
            continue
        celle, testo = _celle_del_lato(parole, lettura.colonne, lato, r.pagina, avvisi, stampati, lettura.intere,
                                       lettura.marcatori)
        _segni_fuori_profilo(celle, lettura.colonne, lettura.negativi, r.pagina, avvisi)
        # i filetti verticali in testa e in coda al lato («| 303.01000 RISERVE DI RIVALUTAZIONE |», budget_375) non
        # sono testo della riga: nascondono il codice e, da soli, fanno una riga vuota
        testo = senza_filetti(testo)
        trovato = _codice(testo, forme)
        codice, etichetta = trovato.codice, trovato.etichetta
        etichetta_testo = " ".join(etichetta).strip()
        controllo = (codice + " " + etichetta_testo).upper()
        if _ANAGRAFICA.search(etichetta_testo.upper()) or _RIPORTO.search(controllo) \
                or (not celle and _IMPORTI.search(controllo)):
            continue
        if not celle and not codice and not etichetta_testo:
            continue
        out.append(_Pezzo(r.pagina, lato, r.y, r.y, min(p.y0 for p in parole), max(p.y1 for p in parole),
                          sezione, codice, etichetta_testo, celle, etichetta, parte=lettura.parte,
                          tabella=lettura.tabella, forma=trovato.forma, x_codice=testo[0].x0 if testo else 0.0,
                          x_etichetta=trovato.x_etichetta, x_testo=_rientro(testo)))
    return out


# Le parole che alcuni gestionali stampano davanti a ogni voce per dire il lato («Attivo B.I) Terreni», 1426): non sono
# il rientro della riga.
_PREFISSI_DI_LATO = {"attivo", "passivo", "attivita", "passivita", "costi", "ricavi"}


def _rientro(testo: list[Parola]) -> float | None:
    """Il bordo sinistro della riga, dopo un eventuale prefisso di lato staccato dal resto."""
    if not testo:
        return None
    if len(testo) > 1 and _norm(testo[0].testo).strip("'`") in _PREFISSI_DI_LATO:
        return testo[1].x0
    return testo[0].x0


def _pagine_pdf(file_path: str) -> tuple[list[list[RigaFisica]], list[float], dict[Parola, str]]:
    """Le righe fisiche di ogni pagina coi token ricuciti, le altezze delle pagine e il testo stampato dei token
    cambiati."""
    pagine: list[list[RigaFisica]] = []
    altezze: list[float] = []
    stampati: dict[Parola, str] = {}
    with fitz.open(file_path) as documento:
        for n, pagina in enumerate(documento, start=1):
            righe = righe_fisiche(parole_pagina(pagina), n)
            for r in righe:
                r.parole = _ricuci(r.parole, stampati)
            pagine.append(righe)
            altezze.append(float(pagina.rect.height))
    return pagine, altezze, stampati


def profilo_pdf(file_path: str) -> Profilo:
    """Il profilo del documento di un PDF, sulle stesse righe fisiche che legge `leggi_pdf`."""
    pagine, altezze, _ = _pagine_pdf(file_path)
    return profilo_documento([r for righe in pagine for r in righe],
                             altezze={n: h for n, h in enumerate(altezze, start=1)})


def _tabella_di(r: RigaFisica, tabelle: list[TabellaNota]) -> int | None:
    return next((k for k, t in enumerate(tabelle) if t.pagina == r.pagina and t.y0 <= r.y <= t.y1), None)


def _letture(righe: list[RigaFisica], profilo: Profilo, colonne_tabelle: list[list[Colonna]]) -> list[_Lettura]:
    """Per ogni riga fisica di una pagina, come si legge: una riga del prospetto sulle colonne del documento, coi
    lati, gli interi in colonna e i negativi del profilo; una riga della nota sulle colonne della sua tabella, a
    lato unico, con gli interi delle colonne senza decimali (R11); una riga della nota fuori da ogni tabella, o di
    un'altra parte, senza colonne."""
    chiavi = []
    for r in righe:
        parte = profilo.parti_righe.get((r.pagina, r.y), "prospetto")
        chiavi.append((parte, None if parte == "prospetto" else _tabella_di(r, profilo.tabelle_nota)))
    letture: dict[tuple[str, int | None], _Lettura] = {}
    for chiave in dict.fromkeys(chiavi):
        parte, tabella = chiave
        if parte == "prospetto":
            colonne = profilo.colonne
            lettura = _Lettura(parte, None, colonne, profilo.confine,
                               frozenset(i for i, d in profilo.decimali.items() if d is False), profilo.negativi,
                               profilo.marcatori)
        else:
            colonne = colonne_tabelle[tabella] if tabella is not None else []
            # gli interi in colonna dove gli importi della tabella non hanno decimali («(311)», budget_255 p26), o
            # dove la colonna stampa solo zeri («Totali 191.633 0 0», budget_1437 p17)
            decimali = _decimali([r for r, c in zip(righe, chiavi) if c == chiave], colonne)
            lettura = _Lettura(parte, tabella, colonne, None, frozenset(i for i, d in decimali.items() if d is not True))
        letture[chiave] = lettura
    return [letture[c] for c in chiavi]


def leggi_pdf(file_path: str) -> Documento:
    """Le righe logiche di un PDF dal suo text layer, lette sul profilo del documento (calcolato prima: prima la
    struttura, poi le righe); senza testo, un documento vuoto con l'avviso."""
    pagine, altezze, stampati = _pagine_pdf(file_path)
    profilo = profilo_documento([r for righe in pagine for r in righe],
                                altezze={n: h for n, h in enumerate(altezze, start=1)})
    if not any(pagine):
        return Documento([], [], False, ["nessun testo: serve l'OCR"], profilo)
    avvisi: list[str] = []
    if not profilo.colonne:
        avvisi.append("nessuna colonna di importi riconosciuta")
    colonne_tabelle = [[Colonna(k, x, "U", "ignoto", None, None, None, False) for k, x in enumerate(t.colonne)]
                       for t in profilo.tabelle_nota]

    sequenze: list[list[_Pezzo]] = []
    for righe in pagine:
        tenute = [r for r in righe if (r.pagina, r.y) not in profilo.scartate]
        per_lato: dict[str, list[_Pezzo]] = {}
        for r, lettura in zip(tenute, _letture(tenute, profilo, colonne_tabelle)):
            for pezzo in _pezzi_della_riga(r, profilo.sezioni_righe.get((r.pagina, r.y), ""), lettura,
                                           profilo.codici, avvisi, stampati):
                per_lato.setdefault(pezzo.lato, []).append(pezzo)
        sequenze += [per_lato[lato] for lato in sorted(per_lato, key=_ORDINE_LATI.get)]
    _conti_e_titoli(sequenze)

    righe_doc: list[Riga] = []
    for seq in sequenze:
        pezzi = _a_capo(_riattacca_orfani(seq))
        for k, p in enumerate(pezzi, start=1):
            righe_doc.append(Riga(id=f"p{p.pagina}r{k}{p.lato}", pagina=p.pagina, y=p.y, lato=p.lato,
                                  sezione=p.sezione, codice=p.codice, etichetta=p.etichetta,
                                  celle=dict(sorted(p.celle.items())),
                                  intestazione=not p.celle and bool(p.etichetta) and not p.conto,
                                  parte=p.parte, tabella=p.tabella,
                                  x=p.x_testo, x_etichetta=p.x_etichetta if p.codice else None))
    doc = Documento(righe_doc, profilo.colonne, profilo.contrapposto, avvisi, profilo)
    # la parentela si decide sulle righe finite, dopo ogni passata che le compone (ruling R2)
    marca_totali(doc)
    assegna_padri(doc)
    return doc
