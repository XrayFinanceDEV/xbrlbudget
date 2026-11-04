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
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal

import fitz

from importers.detail_enrichment import _chiude_sezione, _sezione_della_chiusura
from importers.lettore.colonne import Colonna, _e_riga_testata, colonna_di, colonne_documento
from importers.lettore.geometria import Parola, RigaFisica, parole_pagina, righe_fisiche
from importers.lettore.importi import Importo, leggi_importo
from importers.lettore.lati import assegna_lati, confine_dei_lati
from importers.schema_legge_generico import _PIEDE, _forma_strutturale, _intestazione
from importers.standard_ivcee_parser import _AMOUNT_LIKE, _DATE_RE, riga_conto
from importers.xbrl_reso_parser import _FASCIA_MARGINE, _chiave_ripetuta, _frase_aperta

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
_VALUTA = {"euro", "eur", "€"}
_SCADENZA = {"mesi", "mese", "anni", "anno", "m"}
_ORDINE_LATI = {"U": 0, "L": 1, "R": 2}
_SEZIONI = {"bs": "SP", "ce": "CE"}

# Anagrafiche e riporti (`situazione_contabile_parser._be_collect_side_facts`): non sono righe del prospetto.
_ANAGRAFICA = re.compile(r"^(?:VIA|VIALE|V\.LE|PIAZZA|P\.ZZA|CORSO|C\.F\.|P\.\s?IVA|REA)\b|CODICE FISCALE|PARTITA IVA")
# A parola intera: «SEGUENTE» («esercizio seguente») non e' un riporto.
_RIPORTO = re.compile(r"\bA\s+RIPORT\w*|\bRIPORTO\b|\bRIPORTARE\b|\bSEGUE\b|\bPROGRESSIV\w*")
_IMPORTI = re.compile(r"\bIMPORTI\b")
# Il capitale sociale nella ragione sociale o nell'anagrafica («CAP. SOC. E 22.000.000,00», «Capitale sociale:
# Euro 1.500.000,00 di cui versato: Euro 1.500.000,00»): un importo con la valuta davanti e' testo, anche
# quando cade per caso sotto una colonna (budget_1450, budget_1445).
_CAPITALE = re.compile(r"\bCAP(?:ITALE|\.)?\s*SOC(?:IALE|\.)?", re.I)
# ...ma solo in un'anagrafica: la voce di legge «I. Capitale Sociale € 10.000 € 10.000» (budget_413) tiene le celle.
_MARCA_ANAGRAFICA = re.compile(
    r"REGISTRO\s+(?:DELLE\s+)?IMPRESE|\bI\.\s?V\.|\bVERSATO\b|\bC\.\s?F\.|\bP\.\s?IVA\b"
    r"|\bS\.?\s?(?:P\.?\s?A|R\.?\s?L|A\.?\s?S|N\.?\s?C)\b\.?", re.I)
# Un intero nudo senza zeri in testa (uno «0» da solo va bene), col segno o tra parentesi.
_INTERO = re.compile(r"^(?:-?(?:0|[1-9]\d*)|\((?:0|[1-9]\d*)\))$")
# Il token davanti a un numero che lo fa un riferimento, non un importo («art. 2423», «REA n. 1234567»).
_RIFERIMENTO = {"art.", "art", "artt.", "n.", "n", "nr.", "nr", "n°", "num.", "numero", "rea", "p.iva", "piva",
                "p.i.", "iva", "c.f.", "cf", "cap", "cap.", "c.a.p.", "ateco", "codice", "cod.", "tel.", "fax",
                "prot.", "comma", "lett.", "mutuo", "contratto"}
_SEGUITO_CODICE = re.compile(r"^(?:bis|ter|quater|quinquies)\)?$", re.I)
_GENERATO = re.compile(r"\bgenerato automaticamente\b")
_ANNO = re.compile(r"^(?:19|20)\d{2}$")
# Un codice senza importi si riconosce dalla forma dei codici gia' separati sulle righe con importi:
# stessa famiglia (le cifre e gli asterischi come gruppi, i separatori come sono), stesso lato, x0 entro
# qualche punto (o, per un mastro stampato piu' a sinistra, l'etichetta allineata a quella dei conti), e
# almeno due esempi.
_TOKEN_CODICE = re.compile(r"[\d*]+(?:[/.\-][\d*]+)*")
_TOL_X_CODICE = 4.0
_MIN_ESEMPI_CODICE = 2
_CODICE_AGO = (re.compile(r"^\d{6}$"), re.compile(r"^\d{3}$"))
_TAG_IVCEE = re.compile(r"^[a-e](?:[ivx]+\d*[a-z]?|\d+[a-z]?)?$")
_SEPARATORE = re.compile(r"^[-–:.]+$")


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
    figli: dict[int, tuple[str, ...]] = field(default_factory=dict)   # per colonna, id dei figli (Task 6)
    intestazione: bool = False   # riga-titolo senza importi (mastro o gruppo stampato come titolo)
    padre: str | None = None     # id della riga madre (Task 6)
    padre_verificato: bool = False   # True se i figli del padre sommano al suo totale stampato
    percorso: tuple[str, ...] = ()   # etichette degli antenati, dalla sezione al padre (Task 6)


@dataclass
class Documento:
    righe: list[Riga]
    colonne: list[Colonna]
    contrapposto: bool
    avvisi: list[str]


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
    parole: list[str] = field(default_factory=list)   # etichetta in token, codice compreso se non separato
    x0: float = 0.0                                   # bordo sinistro del primo token (codice o etichetta)
    conto: bool = False                               # conto senza importo: non un titolo
    tutti: list[str] = field(default_factory=list)      # i token della riga fisica, codice e separatori compresi
    x_token: list[float] = field(default_factory=list)  # e i loro x0


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


def _norm(testo: str) -> str:
    testo = "".join(c for c in unicodedata.normalize("NFKD", testo) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", testo).strip().casefold()


# --------------------------------------------------------------------------------------
# Celle
# --------------------------------------------------------------------------------------

def _in_colonna(p: Parola, colonne: list[Colonna], intere: frozenset[int] = frozenset()
                ) -> tuple[Importo, Colonna] | None:
    """L'importo e la sua colonna. Un intero nudo («0», «-1», «(646)» dei prospetti resi da XBRL, decisione R6
    rivista) conta solo in una colonna di `intere`; fuori resta testo."""
    if p.x0 <= _X0_MINIMO:
        return None
    imp = leggi_importo(p.testo)
    if imp is not None:
        c = colonna_di(p.x1, colonne)
        return (imp, c) if c is not None else None
    # una colonna che stampa le migliaia col punto non stampa «1904217»: solo fino a tre cifre
    if not intere or not _INTERO.match(p.testo) or len(p.testo.strip("()-")) > 3:
        return None
    c = colonna_di(p.x1, colonne)
    if c is None or c.indice not in intere:
        return None
    v = Decimal(p.testo.strip("()"))
    v = -v if p.testo.startswith("(") else v
    return Importo(v, "zero" if v == 0 else "importo", p.testo), c


def _colonne_intere(righe: list[RigaFisica], colonne: list[Colonna]) -> frozenset[int]:
    """Le colonne i cui importi (quelli che `leggi_importo` legge, cioe' a gruppi o coi decimali) sono tutti
    senza decimali, come nei prospetti resi da XBRL («10.000»): solo li' un intero nudo e' un importo."""
    con_decimali: dict[int, bool] = {}
    for r in righe:
        for p in r.parole:
            trovato = _in_colonna(p, colonne)
            if trovato is not None and trovato[0].forma != "zero":
                i = trovato[1].indice
                con_decimali[i] = con_decimali.get(i, False) or "," in p.testo
    return frozenset(i for i, dec in con_decimali.items() if not dec)


def _riferimento_davanti(parole: list[Parola], i: int) -> bool:
    if i == 0:
        return False
    prima = re.split(r"['\u2019]", parole[i - 1].testo.lower().strip(":"))[-1]
    return prima in _RIFERIMENTO


def _ha_celle(r: RigaFisica, colonne: list[Colonna]) -> bool:
    return any(_in_colonna(p, colonne) for p in r.parole)


def _valuta_davanti(parole: list[Parola], i: int) -> bool:
    """La parola `i` segue una valuta, o la «E» del capitale sociale («CAP. SOC. E 22.000.000,00»)."""
    prima = parole[i - 1].testo.lower().strip(".:") if i >= 1 else ""
    if prima in _VALUTA:
        return True
    return prima == "e" and i >= 2 and parole[i - 2].testo.lower().startswith("soc")


def _celle_del_lato(parole: list[Parola], colonne: list[Colonna], lato: str, pagina: int,
                    avvisi: list[str], stampati: dict[Parola, str],
                    intere: frozenset[int] = frozenset()) -> tuple[dict[int, Importo], list[Parola]]:
    """(celle per colonna, parole dell'etichetta). Un importo e' una cella solo nella sua colonna e sul suo
    lato; fuori colonna, seguito da una durata («12 mesi») o dentro una frase dopo una valuta («euro 516,46
    di valore unitario», o in un'anagrafica col capitale sociale) torna nell'etichetta. Un anno nudo su una
    riga senza altri importi resta testo. Due importi nella stessa colonna: la cella non si legge. La valuta
    davanti a una cella, o in coda all'etichetta, si toglie."""
    trovati = [_in_colonna(p, colonne, intere) for p in parole]
    trovati = [None if t is None or t[1].lato != lato
               or (leggi_importo(p.testo) is None and _riferimento_davanti(parole, i)) else t
               for i, (p, t) in enumerate(zip(parole, trovati))]
    # un trattino seguito da una parola e' un separatore («PRESTAZ. - IMPRESE»), e un intero nudo davanti a quel
    # separatore o a una parola e' un codice («Codice attivita' 255100 - LAVORAZ.»): si legge da destra, perche'
    # il trattino decide per l'intero. Davanti a un importo il trattino resta una cella zero.
    separatori: set[int] = set()
    for i in range(len(parole) - 2, -1, -1):
        dopo = parole[i + 1].testo
        segue_testo = any(ch.isalpha() for ch in dopo) or (i + 1 in separatori and dopo == "-")
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
    for i, (p, trovato) in enumerate(zip(parole, trovati)):
        dopo = parole[i + 1].testo.lower().strip(".,:;") if i + 1 < len(parole) else ""
        if (trovato is None or dopo in _SCADENZA
                or (_valuta_davanti(parole, i)
                    and (capitale or (any(ch.isalpha() for ch in dopo) and dopo not in _VALUTA)))):
            testo.append(i)
            continue
        imp, c = trovato
        sedi.setdefault(c.indice, []).append(p)
        celle[c.indice] = Importo(imp.valore, imp.forma, stampati.get(p, p.testo))
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
    in_cella = set(range(len(parole))) - set(testo)
    etichetta = [parole[i] for i in sorted(testo, key=lambda i: parole[i].x0)
                 if not (_norm(parole[i].testo) in _VALUTA and i + 1 in in_cella)]
    while etichetta and _norm(etichetta[-1].testo) in _VALUTA:
        etichetta.pop()
    return celle, etichetta


def _capitale_in_anagrafica(parole: list[Parola], colonne: list[Colonna]) -> bool:
    """La riga nomina il capitale sociale in un'anagrafica: con un marcatore (registro imprese, i.v.,
    versato, C.F./P.IVA, ragione sociale) o con un importo con la valuta davanti fuori da ogni colonna."""
    testo = " ".join(p.testo for p in parole)
    if not _CAPITALE.search(testo):
        return False
    if _MARCA_ANAGRAFICA.search(testo):
        return True
    return any(_valuta_davanti(parole, i) and leggi_importo(p.testo) is not None and _in_colonna(p, colonne) is None
               for i, p in enumerate(parole))


def _codice(parole: list[str], ha_importo: bool) -> tuple[str, list[str]]:
    """(codice conto, parole dell'etichetta) col predicato unico `standard_ivcee_parser.riga_conto`. Il
    sottoconto a tre cifre dopo un mastro a sei («102355 151») e il conto dopo la voce IV-CEE («CII1A
    208.00121») fanno parte del codice."""
    if not parole or not riga_conto(" ".join(parole), ha_importo):
        return "", parole
    n = 1
    if _TAG_IVCEE.match(parole[0].lower()) and not re.match(r"^[\d/.]+$", parole[0]):
        n = 2
    elif len(parole) > 2 and _CODICE_AGO[0].match(parole[0]) and _CODICE_AGO[1].match(parole[1]):
        n = 2
    resto = parole[n:]
    while resto and _SEPARATORE.match(resto[0]):
        resto = resto[1:]
    return " ".join(parole[:n]), resto


def _famiglia(codice: str) -> str:
    """«707245 000» -> «9 9», «03/05/***» -> «9/9/9»: la forma senza le lunghezze."""
    return re.sub(r"[\d*]+", "9", codice)


def _forma_codice(codice: str) -> str:
    """«707245 000» -> «999999 999»: la forma con le lunghezze."""
    return re.sub(r"\d", "9", codice)


def _token_codice(t: str) -> bool:
    return bool(_TOKEN_CODICE.fullmatch(t) and re.search(r"\d", t)
                and not _AMOUNT_LIKE.match(t) and not _DATE_RE.fullmatch(t))


_SEPARATORE_CODICE = re.compile(r"^[/.\-]$")


def _codice_spaziato(parole: list[str]) -> int:
    """Quanti token fa un codice stampato con gli spazi attorno ai separatori («4 / 5 / 1»); 0 se non lo e'."""
    n = 1
    while (n + 1 < len(parole) and _token_codice(parole[n - 1]) and _SEPARATORE_CODICE.match(parole[n])
           and _token_codice(parole[n + 1])):
        n += 2
    return n if n > 1 else 0


def _x_etichetta(x_token: list[float], parole: list[str], n: int) -> float | None:
    """x0 della prima parola dopo `n` token di codice e i separatori; None se non si sa."""
    k = n
    while k < len(parole) and _SEPARATORE.match(parole[k]):
        k += 1
    return x_token[k] if k < len(parole) and len(x_token) == len(parole) else None


def _codici_senza_importi(sequenze: list[list[_Pezzo]]) -> None:
    """Il codice in testa a una riga che `riga_conto` non separa, dalla forma dei codici del documento: un
    conto a saldo zero o senza importo stampato, il titolo di un mastro, o un mastro con importi che il
    predicato non riconosce («0103 PORTAFOGLIO ...», «03/05/*** COSTI ...»). Stessa forma e lunghezza di un conto vicino
    (il precedente o il successivo con importi) = conto con la cella vuota; forma o lunghezza diverse =
    titolo. Solo i codici: la parentela la decidono le somme."""
    esempi: dict[tuple[str, str, int], list[tuple[float, float | None]]] = {}
    for seq in sequenze:
        for p in seq:
            if p.celle and p.codice:
                n = len(p.codice.split())
                esempi.setdefault((p.lato, _famiglia(p.codice), n), []).append(
                    (p.x0, _x_etichetta(p.x_token, p.tutti, n)))
    for seq in sequenze:
        for k, p in enumerate(seq):
            if p.codice:
                continue
            spaziato = _codice_spaziato(p.parole)
            for n in ((spaziato,) if spaziato else (2, 1)):
                if len(p.parole) <= n or not all(_token_codice(t) or (spaziato and _SEPARATORE_CODICE.match(t))
                                                 for t in p.parole[:n]):
                    continue
                # un codice non si tronca: «5 bis)» e' una voce, «4 / 5 / 1» non e' «4»
                seguito = p.parole[n]
                if _SEGUITO_CODICE.match(seguito) or seguito in ("/", ".") or (
                        seguito == "-" and n + 1 < len(p.parole) and _token_codice(p.parole[n + 1])):
                    continue
                codice = " ".join(p.parole[:n])
                chiave = "".join(p.parole[:n]) if spaziato else codice
                xs = esempi.get((p.lato, _famiglia(chiave), 1 if spaziato else n), [])
                x_et = _x_etichetta(p.x_token, p.tutti, n)
                if len(xs) >= _MIN_ESEMPI_CODICE and any(
                        abs(x - p.x0) <= _TOL_X_CODICE
                        or (x_et is not None and e is not None and abs(e - x_et) <= _TOL_X_CODICE)
                        for x, e in xs):
                    resto = p.parole[n:]
                    while resto and _SEPARATORE.match(resto[0]):
                        resto = resto[1:]
                    p.codice, p.parole, p.etichetta = codice, resto, " ".join(resto)
                    vicini = [next((q for q in reversed(seq[:k]) if q.celle and q.codice), None),
                              next((q for q in seq[k + 1:] if q.celle and q.codice), None)]
                    p.conto = not p.celle and any(q is not None and _forma_codice(q.codice) == _forma_codice(codice)
                                  for q in vicini)
                    break


# --------------------------------------------------------------------------------------
# Margini, piedi, sezioni
# --------------------------------------------------------------------------------------

def _testo(r: RigaFisica) -> str:
    return " ".join(p.testo for p in r.parole)


def _nel_margine(r: RigaFisica, altezza: float) -> bool:
    y0, y1 = min(p.y0 for p in r.parole), max(p.y1 for p in r.parole)
    return y1 <= _FASCIA_MARGINE * altezza or y0 >= (1 - _FASCIA_MARGINE) * altezza


def _ripetute(pagine: list[list[RigaFisica]], altezze: list[float], colonne: list[Colonna]) -> set[str]:
    """Le righe di margine senza importi che si ripetono su piu' pagine (`xbrl_reso_parser._ripetute`): «Pag.
    2» e «Pag. 3» sono la stessa, a meno delle cifre."""
    pagine_per_chiave: dict[str, set[int]] = {}
    for n, righe in enumerate(pagine):
        for r in righe:
            if _nel_margine(r, altezze[n]) and not _ha_celle(r, colonne):
                pagine_per_chiave.setdefault(_chiave_ripetuta(_testo(r)), set()).add(n)
    return {k for k, p in pagine_per_chiave.items() if len(p) >= 2}


def _scartata(r: RigaFisica, altezza: float, colonne: list[Colonna], ripetute: set[str]) -> bool:
    """Righe che non sono del prospetto: margini ripetuti, piedi «Pagina N di M», «Pag. N», «Utente:», il
    numero di pagina nudo, le intestazioni di colonna («ESERCIZIO 2025 ESERCIZIO 2024»)."""
    testo = _testo(r)
    if _GENERATO.search(_norm(testo)):
        return True     # «Generato automaticamente - Conforme alla tassonomia»: il trattino cade in colonna
    if _ha_celle(r, colonne):
        return False
    if _nel_margine(r, altezza) and _chiave_ripetuta(testo) in ripetute and not _intestazione(testo):
        return True
    return bool(_PIEDE.search(_norm(testo)) or re.fullmatch(r"\d{1,3}", testo.strip())
                or _e_riga_testata(r))


def _titolo_sezione(r: RigaFisica, colonne: list[Colonna]) -> str | None:
    """La sezione che una riga-titolo apre (`detail_enrichment.collect_source_rows`); solo una riga senza
    importi: «UTILE DA CONTO ECONOMICO 5.000,00» nel passivo non apre il CE."""
    if _ha_celle(r, colonne):
        return None
    compatto = re.sub(r"\s+", "", _testo(r).upper())
    if "STATOPATRIMONIALE" in compatto or "SITUAZIONEPATRIMONIALE" in compatto:
        return "SP"
    if "CONTOECONOMICO" in compatto or "SITUAZIONEECONOMICA" in compatto:
        return "CE"
    if "CONTINONASSEGNATI" in compatto or compatto.startswith("NOTAINTEGRATIVA"):
        return ""
    return None


def _tuple(righe: list[RigaFisica]) -> list[list[tuple]]:
    return [[(p.x0, p.y0, p.x1, p.y1, p.testo) for p in r.parole] for r in righe]


def _sezioni(pagine: list[list[RigaFisica]], colonne: list[Colonna], avvisi: list[str]) -> list[list[str]]:
    """Per pagina e riga, la sezione: l'ultimo titolo sopra la riga; sopra il primo titolo, la sezione della
    pagina prima finche' quella non si e' chiusa col suo totale; una pagina senza titoli che chiude con un
    totale dell'altra sezione decide da se' (`collect_source_rows` 255-267, `_sezione_della_chiusura`)."""
    ultima, chiusa = "", False
    out = []
    for righe in pagine:
        titoli = [(r.y, s) for r in righe if (s := _titolo_sezione(r, colonne)) is not None]
        grezze = _tuple(righe)
        chiusura = _SEZIONI.get(_sezione_della_chiusura(grezze) or "")
        if ultima and not chiusa and (titoli or chiusura in (None, ultima)):
            pagina = ultima
        elif not titoli and chiusura is not None:
            pagina = chiusura
        else:
            pagina = ultima if not chiusa else ""
        sezioni = []
        for r in righe:
            s = pagina
            for y, sezione in titoli:
                if y <= r.y + 2:
                    s = sezione
            sezioni.append(s)
        if chiusa and not pagina and any(
                not any(y <= r.y + 2 for y, _ in titoli) for r in righe):
            avvisi.append(f"pagina {len(out) + 1}: sezione non determinata (la pagina prima ha chiuso la "
                          f"sua sezione e qui non c'e' un titolo)")
        out.append(sezioni)
        ultima = titoli[-1][1] if titoli else pagina
        chiusa = _chiude_sezione(grezze)
    return out


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
                  sopra.parole + sotto.parole, sopra.x0, sopra.conto or sotto.conto, sopra.tutti, sopra.x_token)


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
        if out:
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

def _pezzi_della_riga(r: RigaFisica, sezione: str, colonne: list[Colonna], confine: float | None,
                      avvisi: list[str], stampati: dict[Parola, str],
                      intere: frozenset[int] = frozenset()) -> list[_Pezzo]:
    """Una riga fisica -> un pezzo per lato (uno solo senza confine)."""
    if confine is None:
        gruppi = {"U": r.parole}
    else:
        gruppi = {"L": [p for p in r.parole if (p.x0 + p.x1) / 2 < confine],
                  "R": [p for p in r.parole if (p.x0 + p.x1) / 2 >= confine]}
    out = []
    for lato, parole in gruppi.items():
        if not parole:
            continue
        celle, testo = _celle_del_lato(parole, colonne, lato, r.pagina, avvisi, stampati, intere)
        codice, etichetta = _codice([p.testo for p in testo], bool(celle))
        etichetta_testo = " ".join(etichetta).strip()
        controllo = (codice + " " + etichetta_testo).upper()
        if _ANAGRAFICA.search(etichetta_testo.upper()) or _RIPORTO.search(controllo) \
                or (not celle and _IMPORTI.search(controllo)):
            continue
        if not celle and not codice and not etichetta_testo:
            continue
        out.append(_Pezzo(r.pagina, lato, r.y, r.y, min(p.y0 for p in parole), max(p.y1 for p in parole),
                          sezione, codice, etichetta_testo, celle, etichetta,
                          testo[0].x0 if testo else parole[0].x0, False, [p.testo for p in testo],
                          [p.x0 for p in testo]))
    return out


def leggi_pdf(file_path: str) -> Documento:
    """Le righe logiche di un PDF dal suo text layer; senza testo, un documento vuoto con l'avviso."""
    avvisi: list[str] = []
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
    if not any(pagine):
        return Documento([], [], False, ["nessun testo: serve l'OCR"])
    colonne = colonne_documento([r for righe in pagine for r in righe])
    if not colonne:
        avvisi.append("nessuna colonna di importi riconosciuta")
    ripetute = _ripetute(pagine, altezze, colonne)
    pagine = [[r for r in righe if not _scartata(r, altezze[n], colonne, ripetute)]
              for n, righe in enumerate(pagine)]
    tutte = [r for righe in pagine for r in righe]
    confine = confine_dei_lati(tutte, colonne)
    assegna_lati(colonne, confine)
    sezioni = _sezioni(pagine, colonne, avvisi)
    intere = _colonne_intere(tutte, colonne)

    sequenze: list[list[_Pezzo]] = []
    for righe, sezioni_pag in zip(pagine, sezioni):
        per_lato: dict[str, list[_Pezzo]] = {}
        for r, sezione in zip(righe, sezioni_pag):
            for pezzo in _pezzi_della_riga(r, sezione, colonne, confine, avvisi, stampati, intere):
                per_lato.setdefault(pezzo.lato, []).append(pezzo)
        sequenze += [per_lato[lato] for lato in sorted(per_lato, key=_ORDINE_LATI.get)]
    _codici_senza_importi(sequenze)

    righe_doc: list[Riga] = []
    for seq in sequenze:
        pezzi = _a_capo(_riattacca_orfani(seq))
        for k, p in enumerate(pezzi, start=1):
            righe_doc.append(Riga(id=f"p{p.pagina}r{k}{p.lato}", pagina=p.pagina, y=p.y, lato=p.lato,
                                  sezione=p.sezione, codice=p.codice, etichetta=p.etichetta,
                                  celle=dict(sorted(p.celle.items())),
                                  intestazione=not p.celle and bool(p.etichetta) and not p.conto))
    return Documento(righe_doc, colonne, confine is not None, avvisi)
