"""Profilo del documento: come e' fatto il bilancio, calcolato sulle righe fisiche prima di leggerne le righe.

Tipo (schema, schema con dettaglio, sezioni contrapposte, verifica), colonne e lati, forma dei negativi,
decimali per colonna, forme dei codici del piano dei conti, sezione di ogni pagina, righe di margine: fatti del
documento intero, che una riga da sola non vede (decisione del proprietario, 2026-11-04). Qui stanno anche le
regole di livello documento che il passo 5 aveva scritto in `righe.py`; `righe.py` le importa da qui.

Le forme dei codici dicono che cos'e' un codice, mai chi e' figlio di chi: la parentela la decide il totale
stampato (Task 6).
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from importers.bilancio_classifier import classify_bilancio
from importers.detail_enrichment import _chiude_sezione, _sezione_della_chiusura
from importers.lettore.colonne import Colonna, _e_riga_testata, colonna_di, colonne_documento
from importers.lettore.geometria import Parola, RigaFisica
from importers.lettore.importi import Importo, leggi_importo
from importers.lettore.lati import assegna_lati, confine_ammesso
from importers.schema_legge_generico import _PIEDE, _intestazione
from importers.standard_ivcee_parser import _AMOUNT_LIKE, _DATE_RE
from importers.xbrl_reso_parser import _FASCIA_MARGINE, _chiave_ripetuta

if TYPE_CHECKING:       # solo per le annotazioni: `righe` importa da qui
    from importers.lettore.righe import _Pezzo

_X0_MINIMO = 150.0          # come `colonne._in_colonna`
_ALTEZZA_PAGINA = 842.0     # A4 verticale, se chi chiama non da' l'altezza della pagina
_VALUTA = {"euro", "eur", "€"}
_SEZIONI = {"bs": "SP", "ce": "CE"}

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
_GENERATO = re.compile(r"\bgenerato automaticamente\b")
_SEGUITO_CODICE = re.compile(r"^(?:bis|ter|quater|quinquies)\)?$", re.I)
_SEPARATORE = re.compile(r"^[-–:.]+$")
_SEPARATORE_CODICE = re.compile(r"^[/.\-]$")

# Un codice senza importi si riconosce dalla forma dei codici gia' separati sulle righe con importi:
# stessa famiglia (le cifre e gli asterischi come gruppi, i separatori come sono), stesso lato, x0 entro
# qualche punto (o, per un mastro stampato piu' a sinistra, l'etichetta allineata a quella dei conti), e
# almeno due esempi.
_TOKEN_CODICE = re.compile(r"[\d*]+(?:[/.\-][\d*]+)*")
_TOL_X_CODICE = 4.0
_MIN_ESEMPI_CODICE = 2

# Forme di codice del profilo: un token con almeno una cifra, lettere e asterischi ammessi («CII1A», «03/05/***»).
_TOKEN_FORMA = re.compile(r"[A-Za-z\d*]*\d[A-Za-z\d*]*(?:[/.\-][A-Za-z\d*]+)*")
_TOKEN_SEGUITO_FORMA = re.compile(r"[\d*]+(?:[/.\-][\d*]+)*")
_CIFRE_MIN_CODICE = 3          # «5 bis)», «1.1 roe» non sono codici
_TOL_ALLINEATI = 3.0           # una sagoma con separatori conta se si ripete allineata entro tanto
_MIN_RIGHE_FORMA = 3           # righe con importi perche' una forma entri fra i codici
_QUOTA_CODICI = 1 / 3          # righe con importi che portano un codice, perche' il documento sia «a conti»
_MIN_VOCI_LEGGE = 3
_MIN_NEGATIVI = 2

# Voci dello schema di legge (art. 2424-2425): l'enumeratore della voce, con la parentesi o il trattino («A)», «B) II
# -», «II -», «I.»), o nudo davanti al nome in minuscolo («A Crediti verso soci», «II Immobilizzazioni materiali»).
# Il nome di un aggregato da solo non basta: le situazioni contabili chiamano i mastri allo stesso modo («60 COSTI
# DELLA PRODUZIONE», budget_1450).
_VOCE_LEGGE = re.compile(
    r"^(?:[A-E]\s?\)|[A-E]\s?[.\-]\s|(?:[A-E]\s?\)?\s?)?(?:I|II|III|IV|V|VI|VII|VIII|IX)\s?[).\-](?:\s|$)"
    r"|(?:[A-E]|I|II|III|IV|V|VI|VII|VIII|IX)\s[A-Z][a-z\u00e0-\u00f9])")
# Il percorso della voce stampato come codice («1.B.2.1», «B.II.1.a)»): e' lo schema di legge, non un piano dei conti.
_PERCORSO_LEGGE = re.compile(r"^(?:\d{1,2}\.)?[A-E](?:\.(?:[IVX]{1,4}|\d{1,2}[a-z]?))+\)?$")
_RUOLI_ANALISI = ("differenza", "percentuale")
_RUOLI_VERIFICA = frozenset({"dare", "avere", "saldo"})


@dataclass(frozen=True)
class FormaCodice:
    forma: str              # la sagoma: cifre -> "9", lettere -> "A", separatori tali e quali ("999999 999", "9999", "99/99/***")
    x0: float               # x0 mediano del codice
    x_etichetta: float      # x0 mediano della descrizione che lo segue
    con_importi: int        # righe di questa forma con almeno una cella
    senza_importi: int      # righe di questa forma senza celle (titoli o conti a zero)


@dataclass
class Profilo:
    tipo: str               # "schema" | "schema-dettaglio" | "contrapposte" | "verifica" | "ignoto"
    tipo_perche: str        # che cosa l'ha deciso (geometria, parole, indizio del classificatore)
    colonne: list[Colonna]  # da colonne_documento, con lato assegnato
    confine: float | None   # x del confine fra i lati; None = una sezione
    negativi: frozenset[str]    # "meno" (-123), "parentesi" ((123)), "meno-finale" (123-), "marcatore" (123 D/A), "colonne-dare-avere"
    decimali: dict[int, bool | None]   # per colonna: True = stampa i centesimi, False = interi, None = non visto
    codici: list[FormaCodice]          # le forme di codice del piano dei conti, piu' frequenti prima
    sezioni: dict[int, str]            # pagina -> "SP" | "CE" | "SP+CE" | "" (sconosciuta)
    margini: frozenset[str]            # testi normalizzati delle righe ripetute in testa o in piede
    avvisi: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------
# Celle (regole del passo 5, condivise con `righe`)
# --------------------------------------------------------------------------------------

def _norm(testo: str) -> str:
    testo = "".join(c for c in unicodedata.normalize("NFKD", testo) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", testo).strip().casefold()


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


def _ha_celle(r: RigaFisica, colonne: list[Colonna]) -> bool:
    return any(_in_colonna(p, colonne) for p in r.parole)


def _valuta_davanti(parole: list[Parola], i: int) -> bool:
    """La parola `i` segue una valuta, o la «E» del capitale sociale («CAP. SOC. E 22.000.000,00»)."""
    prima = parole[i - 1].testo.lower().strip(".:") if i >= 1 else ""
    if prima in _VALUTA:
        return True
    return prima == "e" and i >= 2 and parole[i - 2].testo.lower().startswith("soc")


def _decimali(righe: list[RigaFisica], colonne: list[Colonna]) -> dict[int, bool | None]:
    """Per colonna, se i suoi importi (quelli che `leggi_importo` legge, cioe' a gruppi o coi decimali) stampano
    i centesimi; None se la colonna non ne ha."""
    out: dict[int, bool | None] = {c.indice: None for c in colonne}
    for r in righe:
        for p in r.parole:
            trovato = _in_colonna(p, colonne)
            if trovato is not None and trovato[0].forma != "zero":
                i = trovato[1].indice
                out[i] = bool(out[i]) or "," in p.testo
    return out


def _colonne_intere(righe: list[RigaFisica], colonne: list[Colonna]) -> frozenset[int]:
    """Le colonne i cui importi sono tutti senza decimali, come nei prospetti resi da XBRL («10.000»): solo li'
    un intero nudo e' un importo."""
    return frozenset(i for i, dec in _decimali(righe, colonne).items() if dec is False)


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


# --------------------------------------------------------------------------------------
# Codici senza importi (regola del passo 5 sulle righe di `righe`)
# --------------------------------------------------------------------------------------

def _famiglia(codice: str) -> str:
    """«707245 000» -> «9 9», «03/05/***» -> «9/9/9»: la forma senza le lunghezze."""
    return re.sub(r"[\d*]+", "9", codice)


def _forma_codice(codice: str) -> str:
    """«707245 000» -> «999999 999»: la forma con le lunghezze."""
    return re.sub(r"\d", "9", codice)


def _token_codice(t: str) -> bool:
    return bool(_TOKEN_CODICE.fullmatch(t) and re.search(r"\d", t)
                and not _AMOUNT_LIKE.match(t) and not _DATE_RE.fullmatch(t))


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


def _codici_senza_importi(sequenze: list[list["_Pezzo"]]) -> None:
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
# Profilo
# --------------------------------------------------------------------------------------

@dataclass
class _Candidato:
    """Il codice in testa a un lato di una riga fisica."""
    lato: str
    forma: str
    x0: float
    x_etichetta: float | None
    con_importi: bool


def _sagoma(token: str) -> str:
    return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", token))


def _gruppi(r: RigaFisica, confine: float | None) -> dict[str, list[Parola]]:
    """Le parole della riga per lato, come le divide `righe._pezzi_della_riga`."""
    if confine is None:
        return {"U": list(r.parole)}
    return {"L": [p for p in r.parole if (p.x0 + p.x1) / 2 < confine],
            "R": [p for p in r.parole if (p.x0 + p.x1) / 2 >= confine]}


def _codice_in_testa(parole: list[Parola]) -> tuple[str, int] | None:
    """(sagoma, token di codice) del codice che apre `parole`, o None. Il codice e' il primo token con
    una cifra e quelli di sole cifre che lo seguono («707245 000», «CII1A 208.00121»), o un codice spaziato
    («4 / 5 / 1»); un codice seguito da «bis)», «ter)» e' una voce («5 bis)»)."""
    testi = [p.testo for p in parole]
    if not testi or not _e_token_forma(testi[0], primo=True):
        return None
    n = 1
    while n < len(testi):
        if (n + 1 < len(testi) and _SEPARATORE_CODICE.match(testi[n])
                and _e_token_forma(testi[n + 1], primo=False)):
            n += 2
        elif _e_token_forma(testi[n], primo=False):
            n += 1
        else:
            break
    if n < len(testi) and _SEGUITO_CODICE.match(testi[n]):
        return None
    if sum(ch.isdigit() for t in testi[:n] for ch in t) < _CIFRE_MIN_CODICE:
        return None
    return " ".join(_sagoma(t) for t in testi[:n]), n


def _e_token_forma(t: str, primo: bool) -> bool:
    rx = _TOKEN_FORMA if primo else _TOKEN_SEGUITO_FORMA
    return bool(rx.fullmatch(t) and leggi_importo(t) is None and not _AMOUNT_LIKE.match(t)
                and not _DATE_RE.fullmatch(t))


def _candidati(righe: list[RigaFisica], colonne: list[Colonna], confine: float | None) -> list[_Candidato]:
    out = []
    for r in righe:
        for lato, parole in _gruppi(r, confine).items():
            celle = [p for p in parole if (t := _in_colonna(p, colonne)) is not None
                     and (confine is None or t[1].lato == lato)]
            testo = [p for p in parole if p not in celle]
            trovato = _codice_in_testa(testo)
            if trovato is None:
                continue
            forma, n = trovato
            k = n
            while k < len(testo) and _SEPARATORE.match(testo[k].testo):
                k += 1
            out.append(_Candidato(lato, forma, testo[0].x0, testo[k].x0 if k < len(testo) else None, bool(celle)))
    return out


def _forme(candidati: list[_Candidato]) -> list[FormaCodice]:
    """Le forme di codice del documento. Per lato e sagoma, i candidati allineati (x0 entro 3 pt) fanno un
    gruppo; una sagoma con separatori conta solo ripetuta allineata. Entra un gruppo con almeno tre righe con
    importi; poi un gruppo senza abbastanza importi (i titoli dei mastri, «7072») se e' allineato a uno gia'
    entrato, sul codice o sull'etichetta."""
    gruppi: list[list[_Candidato]] = []
    per_chiave: dict[tuple[str, str], list[_Candidato]] = {}
    for c in candidati:
        per_chiave.setdefault((c.lato, c.forma), []).append(c)
    for (_, forma), cs in per_chiave.items():
        cs = sorted(cs, key=lambda c: c.x0)
        correnti: list[_Candidato] = []
        for c in cs:
            if correnti and c.x0 - correnti[-1].x0 > _TOL_ALLINEATI:
                gruppi.append(correnti)
                correnti = []
            correnti.append(c)
        gruppi.append(correnti)
    separati = [g for g in gruppi if not re.search(r"[/.\-]", g[0].forma) or len(g) >= 2]

    def forma_di(g: list[_Candidato]) -> tuple[str, FormaCodice]:
        etichette = [c.x_etichetta for c in g if c.x_etichetta is not None]
        con = sum(c.con_importi for c in g)
        return g[0].lato, FormaCodice(g[0].forma, statistics.median(c.x0 for c in g),
                                      statistics.median(etichette) if etichette else statistics.median(c.x0 for c in g),
                                      con, len(g) - con)

    tutte = [forma_di(g) for g in separati]
    entrate = [(lato, f) for lato, f in tutte if f.con_importi >= _MIN_RIGHE_FORMA]
    for lato, f in tutte:
        if f.con_importi >= _MIN_RIGHE_FORMA:
            continue
        if any(lato == l2 and (abs(f.x0 - e.x0) <= _TOL_X_CODICE or abs(f.x_etichetta - e.x_etichetta) <= _TOL_X_CODICE)
               for l2, e in entrate if e.con_importi >= _MIN_RIGHE_FORMA):
            entrate.append((lato, f))
    return sorted((f for _, f in entrate), key=lambda f: (-(f.con_importi + f.senza_importi), -f.con_importi, f.x0))


def _voce_di_legge(testo: str) -> bool:
    return bool(_VOCE_LEGGE.match(testo.strip()))


def _parole_del_tipo(righe: list[RigaFisica], colonne: list[Colonna]) -> tuple[str | None, int, float, str]:
    """(tipo che dicono le parole, voci di legge, quota di righe con importi che aprono con un codice, perche').
    Le parole bastano solo a dire «schema» o «schema con dettaglio»; il resto lo dice la geometria."""
    con_codice = sum(f.con_importi for f in _forme(_candidati(righe, colonne, None)))
    con_importi = sum(1 for r in righe if _ha_celle(r, colonne))
    quota = con_codice / con_importi if con_importi else 0.0
    voci = 0
    for r in righe:
        testo = [p for p in r.parole if _in_colonna(p, colonne) is None]
        trovato = _codice_in_testa(testo)
        k = trovato[1] if trovato else 0
        if (testo and _PERCORSO_LEGGE.match(testo[0].testo)) or _voce_di_legge(" ".join(p.testo for p in testo[k:])):
            voci += 1
    perche = f"{voci} voci di legge, {con_codice}/{con_importi} righe con importi aperte da un codice"
    if voci >= _MIN_VOCI_LEGGE:
        return ("schema-dettaglio" if quota >= _QUOTA_CODICI else "schema"), voci, quota, perche
    return None, voci, quota, perche


def _negativi(righe: list[RigaFisica], colonne: list[Colonna], intere: frozenset[int]) -> frozenset[str]:
    """Le forme del negativo viste almeno due volte sulle celle; le colonne di differenza e di percentuale
    non contano (un negativo li' e' una variazione)."""
    viste: Counter[str] = Counter()
    for r in righe:
        for k, p in enumerate(r.parole):
            trovato = _in_colonna(p, colonne, intere)
            if trovato is None or trovato[1].ruolo in _RUOLI_ANALISI:
                continue
            testo = p.testo.replace("€", "").strip()
            dopo = r.parole[k + 1] if k + 1 < len(r.parole) else None
            if re.search(r"\s[DA]$", testo) or (
                    dopo is not None and dopo.testo in ("D", "A") and dopo.x0 - p.x1 <= 8):
                viste["marcatore"] += 1
            if trovato[0].valore >= 0:
                continue
            if testo.startswith("(") and testo.endswith(")"):
                viste["parentesi"] += 1
            elif testo.startswith("-"):
                viste["meno"] += 1
            elif testo.rstrip(")").endswith("-"):
                viste["meno-finale"] += 1
    forme = {f for f, n in viste.items() if n >= _MIN_NEGATIVI}
    ruoli = {c.ruolo for c in colonne}
    if {"dare", "avere"} <= ruoli:
        forme.add("colonne-dare-avere")
    return frozenset(forme)


def _sezioni_pagina(pagine: list[list[RigaFisica]], sezioni: list[list[str]]) -> dict[int, str]:
    out = {}
    for n, (righe, per_riga) in enumerate(zip(pagine, sezioni), start=1):
        if not righe:
            continue
        viste = {s for s in per_riga if s}
        out[n] = "SP+CE" if viste == {"SP", "CE"} else (viste.pop() if viste else "")
    return out


def _indizio(righe: list[RigaFisica]) -> str:
    """Il classificatore di rotta sul testo delle righe (nessuna lettura di file): solo un indizio."""
    c = classify_bilancio(text="\n".join(_testo(r) for r in righe))
    return f"classificatore: {c.macro_area} {c.subcategory}"


_MACRO_ATTESA = {"schema": {"A"}, "schema-dettaglio": {"B"}, "contrapposte": {"C"}, "verifica": {"C"}}


def profilo_documento(righe: list[RigaFisica], *, altezze: dict[int, float] | None = None) -> Profilo:
    """Il profilo del documento dalle righe fisiche di tutte le pagine. `altezze` (pagina -> altezza in punti)
    serve alle righe di margine; senza, la pagina e' un A4 verticale o, se il testo scende piu' in basso,
    alta fino all'ultima parola."""
    avvisi: list[str] = []
    n_pagine = max((r.pagina for r in righe), default=0)
    pagine: list[list[RigaFisica]] = [[] for _ in range(n_pagine)]
    for r in righe:
        pagine[r.pagina - 1].append(r)
    altezze_l = [(altezze or {}).get(n) or max([_ALTEZZA_PAGINA] + [p.y1 for r in pagine[n - 1] for p in r.parole])
                 for n in range(1, n_pagine + 1)]
    if not any(pagine):
        return Profilo("ignoto", "nessun testo", [], None, frozenset(), {}, [], {}, frozenset(),
                       ["tipo non determinato: nessun testo, serve l'OCR"])

    colonne = colonne_documento([r for p in pagine for r in p])
    margini = _ripetute(pagine, altezze_l, colonne)
    pagine = [[r for r in rr if not _scartata(r, altezze_l[n], colonne, margini)] for n, rr in enumerate(pagine)]
    tutte = [r for rr in pagine for r in rr]
    decimali = _decimali(tutte, colonne)
    intere = frozenset(i for i, d in decimali.items() if d is False)

    tipo_parole, voci, quota, perche_parole = _parole_del_tipo(tutte, colonne)
    confine = confine_ammesso(tutte, colonne, tipo_parole)
    assegna_lati(colonne, confine)
    ruoli = {c.ruolo for c in colonne}
    if confine is not None:
        tipo, perche = "contrapposte", f"geometria: due lati simmetrici, confine a x={confine:.1f}"
    elif ruoli & _RUOLI_VERIFICA:
        tipo, perche = "verifica", "colonne " + "/".join(sorted(ruoli & _RUOLI_VERIFICA))
    elif tipo_parole is not None:
        tipo, perche = tipo_parole, "parole"
    elif quota >= _QUOTA_CODICI:
        tipo, perche = "verifica", "codici conto senza voci di legge"
    else:
        tipo, perche = "ignoto", "nessuna regola decide"
    indizio = _indizio(tutte)
    tipo_perche = f"{perche}; {perche_parole}; {indizio}"
    if tipo == "ignoto":
        avvisi.append(f"tipo non determinato ({perche_parole}; {indizio})")
    elif indizio.split()[1] not in _MACRO_ATTESA[tipo]:
        avvisi.append(f"tipo {tipo}, ma il {indizio} (solo un indizio)")

    sezioni = _sezioni_pagina(pagine, _sezioni(pagine, colonne, avvisi))
    return Profilo(tipo, tipo_perche, colonne, confine, _negativi(tutte, colonne, intere), decimali,
                   _forme(_candidati(tutte, colonne, confine)), sezioni, frozenset(margini), avvisi)
