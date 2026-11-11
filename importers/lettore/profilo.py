"""Profilo del documento: come e' fatto il bilancio, calcolato sulle righe fisiche prima di leggerne le righe.

Tipo (schema, schema con dettaglio, sezioni contrapposte, verifica), colonne e lati, forma dei negativi,
decimali per colonna, forme dei codici del piano dei conti, sezione di ogni pagina, righe di margine: fatti del
documento intero, che una riga da sola non vede (decisione del proprietario, 2026-11-04). Qui stanno anche le
regole di livello documento che il passo 5 aveva scritto in `righe.py`; `righe.py` le legge dal profilo.

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

from importers.bilancio_classifier import classify_bilancio
from importers.lettore._ereditati import (
    _TOTALE_DI_CHIUSURA, AMOUNT_LIKE, DATE_RE, FASCIA_MARGINE, PIEDE, chiave_ripetuta, chiude_sezione, intestazione,
    sezione_della_chiusura,
)
from importers.lettore.colonne import Colonna, _e_riga_testata, colonna_di, colonne_documento, completa_periodi
from importers.lettore.geometria import Parola, RigaFisica
from importers.lettore.importi import Importo, leggi_importo
from importers.lettore.lati import assegna_lati, confine_ammesso

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

# Un codice e' allineato a una forma del profilo se il suo x0, o quello dell'etichetta che lo segue (un mastro
# stampato piu' a sinistra dei conti), e' entro tanto dalla mediana della forma.
_TOL_X_CODICE = 4.0

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
# Anche con la lettera in coda come segmento a se' («3.B.10.a», budget_1540).
_PERCORSO_LEGGE = re.compile(r"^(?:\d{1,2}\.)?[A-E](?:\.(?:[IVX]{1,4}|\d{1,2}[a-z]?))+(?:\.[a-z])?\)?$")
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
    negativi: frozenset[str]    # "meno" (-123), "parentesi" ((123)), "meno-finale" (123-), "meno-staccato" (- 123), "meno-colonna" (trattini allineati), "marcatore" (123 D/A), "colonne-dare-avere"
    decimali: dict[int, bool | None]   # per colonna: True = stampa i centesimi, False = interi, None = non visto
    codici: list[FormaCodice]          # le forme di codice del piano dei conti, piu' frequenti prima
    sezioni: dict[int, str]            # pagina -> "SP" | "CE" | "SP+CE" | "" (sconosciuta)
    margini: frozenset[str]            # testi normalizzati delle righe ripetute in testa o in piede
    avvisi: list[str] = field(default_factory=list)
    contrapposto: bool = False         # il verdetto: a sinistra attivo/costi, a destra passivo/ricavi
    parti: dict[int, str] = field(default_factory=dict)   # pagina -> "prospetto" | "nota" | "altro", la prevalente
    bande: list[tuple[int, float, str]] = field(default_factory=list)   # (pagina, y da cui comincia, parte), in ordine
    tabelle_nota: list["TabellaNota"] = field(default_factory=list)
    # Per riga fisica, con chiave (pagina, y del centro): le decisioni che il lettore di righe consuma senza rifarle.
    scartate: frozenset[tuple[int, float]] = frozenset()             # margini, piedi, testate di colonna
    sezioni_righe: dict[tuple[int, float], str] = field(default_factory=dict)   # righe non scartate -> sezione
    parti_righe: dict[tuple[int, float], str] = field(default_factory=dict)     # ogni riga -> parte
    # Q2 (proprietario, 2026-11-05): le colonne in cui la maggioranza delle celle porta il marcatore D/A staccato
    # dopo l'importo («11.429.777,38 D»): solo li' il marcatore e' il segno della cella e lascia l'etichetta
    marcatori: frozenset[int] = frozenset()
    # Q1 (proprietario, 2026-11-05): colonna dei totali -> colonna dei parziali accanto, sullo stesso lato: i conti
    # stanno nei parziali (al centesimo), la voce che li somma nei totali (all'unita'), mai sulla stessa riga
    coppie: dict[int, int] = field(default_factory=dict)
    # Due tabelle affiancate (confine fisico senza sezioni contrapposte, 1426: lo stato patrimoniale a sinistra, il
    # conto economico a destra): la sezione di ogni lato ha i suoi titoli, chiave (pagina, y, "L"|"R")
    sezioni_lati: dict[tuple[int, float, str], str] = field(default_factory=dict)
    # (pagina, x destra) dei trattini che fanno da colonna dei segni meno (1426), vedi `meno_staccato`
    segni_colonna: frozenset[tuple[int, float]] = frozenset()
    # le colonne dove un intero nudo («623», «82») e' un importo nella lettura delle celle
    # (`_colonne_intere_di_fatto`); None = quelle che `decimali` dice tutte senza centesimi. Negativi, coppie
    # parziali/totali e marcatori D/A restano sulle intere strette: contano forme e posizioni su tutte le righe, e un
    # intero nudo letto come importo in una colonna che stampa anche i centesimi sposterebbe quei conteggi su ogni
    # documento; a 1540 bastano le celle (le coppie le trova gia').
    intere: frozenset[int] | None = None


@dataclass(frozen=True)
class TabellaNota:
    """Una tabella della nota integrativa (o del rendiconto, di una movimentazione): riconosciuta e dichiarata, mai
    letta come prospetto."""
    pagina: int
    y0: float               # centro della prima riga con importi
    y1: float               # centro dell'ultima
    titolo: str             # la riga di testo che la precede, o l'ultimo titolo della nota
    colonne: tuple[float, ...]   # bordi destri delle sue colonne


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


_RIMANDO = re.compile(r"^\([1-9]\d?\)$")      # «(0)» e' uno zero, i rimandi cominciano da 1
_STACCO_RIMANDO = 6.0


def _rimando_di_nota(parole: list[Parola], i: int) -> bool:
    """«(1)» attaccato a un importo e' il rimando a una nota («VI - Altre riserve 46.078 (1) 37.407», budget_385),
    non un intero nudo negativo."""
    return (bool(_RIMANDO.match(parole[i].testo)) and i > 0 and leggi_importo(parole[i - 1].testo) is not None
            and parole[i].x0 - parole[i - 1].x1 <= _STACCO_RIMANDO)


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


# Una colonna dei totali all'unita' puo' stampare i centesimi su una riga o due (il risultato d'esercizio, 1540: 2
# importi su 81): non per questo i suoi interi nudi («623», «82») diventano testo. Bastano tanti importi da fare una
# prova, e i centesimi devono essere l'eccezione, non una delle due forme della colonna (208, 682: un terzo e oltre).
_MIN_IMPORTI_INTERI = 20
_QUOTA_CENTESIMI_AMMESSA = 0.05


def _colonne_intere_di_fatto(righe: list[RigaFisica], colonne: list[Colonna]) -> frozenset[int]:
    """Le colonne i cui importi sono senza centesimi, salvo al piu' il 5% su almeno 20 importi letti."""
    conti: dict[int, list[int]] = {c.indice: [0, 0] for c in colonne}
    for r in righe:
        for p in r.parole:
            trovato = _in_colonna(p, colonne)
            if trovato is not None and trovato[0].forma != "zero":
                conti[trovato[1].indice]["," in p.testo] += 1
    return frozenset(i for i, (senza, con) in conti.items() if intera_di_fatto(senza, con))


def intera_di_fatto(senza: int, con: int) -> bool:
    """`senza` importi senza centesimi e `con` coi centesimi: la colonna e' a interi se non ne ha coi centesimi, o
    se ne ha al piu' il 5% su almeno 20 importi (1 su 20 si', 1 su 19 no)."""
    totale = senza + con
    return senza > 0 and (con == 0 or (totale >= _MIN_IMPORTI_INTERI and con <= _QUOTA_CENTESIMI_AMMESSA * totale))


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
# Margini, piedi, sezioni
# --------------------------------------------------------------------------------------

def _testo(r: RigaFisica) -> str:
    return " ".join(p.testo for p in r.parole)


def _nel_margine(r: RigaFisica, altezza: float) -> bool:
    y0, y1 = min(p.y0 for p in r.parole), max(p.y1 for p in r.parole)
    return y1 <= FASCIA_MARGINE * altezza or y0 >= (1 - FASCIA_MARGINE) * altezza


def _ripetute(pagine: list[list[RigaFisica]], altezze: list[float], colonne: list[Colonna]) -> set[str]:
    """Le righe di margine senza importi che si ripetono su piu' pagine (`xbrl_reso_parser._ripetute`): «Pag.
    2» e «Pag. 3» sono la stessa, a meno delle cifre."""
    pagine_per_chiave: dict[str, set[int]] = {}
    for n, righe in enumerate(pagine):
        for r in righe:
            if _nel_margine(r, altezze[n]) and not _ha_celle(r, colonne):
                pagine_per_chiave.setdefault(chiave_ripetuta(_testo(r)), set()).add(n)
    return {k for k, p in pagine_per_chiave.items() if len(p) >= 2}


def _scartata(r: RigaFisica, altezza: float, colonne: list[Colonna], ripetute: set[str]) -> bool:
    """Righe che non sono del prospetto: margini ripetuti, piedi «Pagina N di M», «Pag. N», «Utente:», il
    numero di pagina nudo, le intestazioni di colonna («ESERCIZIO 2025 ESERCIZIO 2024»)."""
    testo = _testo(r)
    if _GENERATO.search(_norm(testo)):
        return True     # «Generato automaticamente - Conforme alla tassonomia»: il trattino cade in colonna
    if _ha_celle(r, colonne):
        return False
    if _nel_margine(r, altezza) and chiave_ripetuta(testo) in ripetute and not intestazione(testo) \
            and not _PERDITE_E_PROFITTI.match(testo.strip()):
        return True
    return bool(PIEDE.search(_norm(testo)) or re.fullmatch(r"\d{1,3}", testo.strip())
                or _e_riga_testata(r))


_CODICE_IN_TESTA = re.compile(r"^[\d.]+$")


def _titolo_con_importi(r: RigaFisica, colonne: list[Colonna]) -> str | None:
    """Un titolo di sezione che stampa i totali sulla stessa riga («STATO PATRIMONIALE ATTIVO» con il totale accanto,
    «Conto economico 0,00»): le parole fuori colonna cominciano col titolo, dopo l'eventuale numero d'ordine, e
    sono poche. «UTILE DA CONTO ECONOMICO 5.000,00» nel passivo comincia altrimenti e non apre il CE."""
    parole = [p.testo for p in r.parole if _in_colonna(p, colonne) is None]
    while parole and _CODICE_IN_TESTA.fullmatch(parole[0]):
        parole = parole[1:]
    compatto = re.sub(r"\s+", "", " ".join(parole).upper())
    if len(compatto) > 40:
        return None
    if compatto.startswith(("STATOPATRIMONIALE", "SITUAZIONEPATRIMONIALE")):
        return "SP"
    if compatto.startswith(("CONTOECONOMICO", "SITUAZIONEECONOMICA")):
        return "CE"
    return None


def _titolo_debole(r: RigaFisica, colonne: list[Colonna]) -> str | None:
    """«1 ATTIVO», «2 PASSIVO» con i totali accanto (1540): titolo dello stato patrimoniale solo finche' il
    documento non ha aperto nessuna sezione. Piu' avanti «ATTIVO» con un totale e' un riepilogo in coda alle
    contrapposte, non un titolo."""
    parole = [p.testo for p in r.parole if _in_colonna(p, colonne) is None]
    while parole and _CODICE_IN_TESTA.fullmatch(parole[0]):
        parole = parole[1:]
    if _ha_celle(r, colonne) and intestazione(" ".join(parole)) in (["Attivo"], ["Passivo"]):
        return "SP"
    return None


# Il titolo del conto economico di certi gestionali, ripetuto in testa a ogni pagina come un'intestazione di sezione:
# non e' un margine da scartare (1566)
_PERDITE_E_PROFITTI = re.compile(r"perdite\s+e\s+profitti\b", re.I)
# Le due meta' del conto economico a sezioni contrapposte, nel titolo classico: «COSTI, SPESE E PERDITE»,
# «RICAVI E PROFITTI» (1531: la pagina dopo uno stato patrimoniale chiuso a pareggio)
_COSTI_E_RICAVI = re.compile(r"(?:costi\W+spese\s+e\s+perdite|ricavi\W+(?:rendite\s+e\s+)?profitti)\b", re.I)


# Le parole di una testata di colonna che una stampa mette in coda al titolo del lato («ATTIVITA' CORRENTE
# PRECEDENTE», 1533): tolte quelle, resta il titolo. Solo le parole dei periodi: «SALDO PASSIVO» non e' un titolo.
_TESTATA_SUL_TITOLO = {"corrente", "precedente", "esercizio", "periodo", "anno"}


def _titolo_di_lato(r: RigaFisica, colonne: list[Colonna]) -> bool:
    """«ATTIVITA'», «PASSIVITA' E PATRIMONIO NETTO» seguiti dalle parole della testata delle colonne, su una riga
    senza importi."""
    if _ha_celle(r, colonne):
        return False
    parole = _testo(r).split()
    n = len(parole)
    while parole and _norm(parole[-1]).strip("'’.:") in _TESTATA_SUL_TITOLO:
        parole.pop()
    return 0 < len(parole) < n and intestazione(" ".join(parole)) in (["Attivo"], ["Passivo"])


def _titolo_sezione(r: RigaFisica, colonne: list[Colonna]) -> str | None:
    """La sezione che una riga-titolo apre (`detail_enrichment.collect_source_rows`); solo una riga senza
    importi: «UTILE DA CONTO ECONOMICO 5.000,00» nel passivo non apre il CE."""
    if _ha_celle(r, colonne):
        return _titolo_con_importi(r, colonne)
    compatto = re.sub(r"\s+", "", _testo(r).upper())
    if "STATOPATRIMONIALE" in compatto or "SITUAZIONEPATRIMONIALE" in compatto:
        return "SP"
    if "CONTOECONOMICO" in compatto or "SITUAZIONEECONOMICA" in compatto or _PERDITE_E_PROFITTI.match(_testo(r)) \
            or _COSTI_E_RICAVI.match(_testo(r)):
        return "CE"     # «PERDITE E PROFITTI al 30/09/2026»: il conto economico di certi gestionali (1566)
    if compatto.startswith(("CE-", "SP-")) and len(compatto) < 40:
        return compatto[:2]     # «CE - Schema Ridotto» in testa a una delle due tabelle affiancate (1426)
    if "CONTINONASSEGNATI" in compatto or compatto.startswith("NOTAINTEGRATIVA"):
        return ""
    return None


def _tuple(righe: list[RigaFisica]) -> list[list[tuple]]:
    return [[(p.x0, p.y0, p.x1, p.y1, p.testo) for p in r.parole] for r in righe]


# Il risultato d'esercizio come riga di chiusura: la stessa frase di `_ereditati._TOTALE_DI_CHIUSURA`
# (test di parita'), qui separata dai totali.
_RISULTATO_DI_CHIUSURA = re.compile(r"(?:UTILE|PERDITA)\S*\s+(?:D\W?\s*)?ESERCIZIO")


_SUBTOTALE_DI_LEGGE = re.compile(r"TOTALE\s+(?:COSTI|VALORE|RICAVI)\b.*PRODUZIONE")


def _chiude(grezze: list[list[tuple]]) -> bool:
    """La pagina chiude la sua sezione (`chiude_sezione`), con due eccezioni. «Totale Costi della produzione (B)»
    e' un sottototale dello schema di legge, non la fine del conto economico (1553: il CE continua nella pagina
    dopo). Il risultato d'esercizio da solo chiude soltanto se e' fra le ultime due righe con importi: in uno
    stato patrimoniale «Utile (Perdita) dell'esercizio» sta dentro il patrimonio netto e la pagina prosegue
    con TFR e debiti (381). Un totale o un pareggio chiudono dove stanno."""
    if not chiude_sezione(grezze):
        return False

    def testo(line):
        return " ".join(str(w[4]) for w in line).upper()
    righe = [line for line in grezze if not _SUBTOTALE_DI_LEGGE.search(testo(line))]
    senza = [line for line in righe if not _RISULTATO_DI_CHIUSURA.search(testo(line))]
    if chiude_sezione(senza):
        return True
    con_importi = [line for line in righe if any(leggi_importo(str(w[4])) is not None for w in line)]
    return chiude_sezione(con_importi[-2:])


_TOTALE_CONTI = re.compile(r"TOTALE\s+(?:DEI\s+)?CONTI\s+(PATRIMONIAL|ECONOMIC)")


def _sezioni_dai_totali_di_conti(pagine: list[list[RigaFisica]], per_pagina: list[list[str]]) -> None:
    """Un bilancio di verifica senza titoli di sezione ma con «TOTALE CONTI PATRIMONIALI» e «TOTALE CONTI
    ECONOMICI» (1561, ordine «Conti Patrimoniali / Economici»): ogni riga ancora senza sezione e' della sezione
    del primo di quei totali che la segue, anche a meta' pagina. Sono righe di chiusura, come i totali di
    attivita'/passivita' che decidono la pagina in `sezione_della_chiusura`; senza un totale dopo, resta vuota."""
    da_assegnare = []
    for n, righe in enumerate(pagine):
        for k, r in enumerate(righe):
            if per_pagina[n][k] == "":
                da_assegnare.append((n, k))
            m = _TOTALE_CONTI.search(re.sub(r"\s+", " ", _testo(r).upper()))
            if m:
                sezione = "SP" if m.group(1) == "PATRIMONIAL" else "CE"
                for i, j in da_assegnare:
                    per_pagina[i][j] = sezione
                da_assegnare = []


_CHIUSURA_SP = re.compile(r"TOTALE\s*(?:ATTIVIT|PASSIVIT|ATTIVO\b(?!\s*CIRCOLANTE)|PASSIVO\b)")
_CHIUSURA_CE = re.compile(r"TOTALE\s*(?:COSTI|RICAVI)")


def _sezioni_dalle_chiusure(pagine: list[list[RigaFisica]], colonne: list[Colonna], per_pagina: list[list[str]]) -> None:
    """All'indietro (Fase 5, F1a: 395, 1325, 1401, 281, 610): ogni riga ancora senza sezione prende quella del primo
    totale di chiusura con importi che la segue — attivita'/passivita' lo SP, costi/ricavi il CE —, anche nelle
    pagine prima, come fa `_sezioni_dai_totali_di_conti` coi totali dei conti. Una verifica che dichiara la sezione
    solo coi totali in fondo. Un titolo ferma la propagazione (le righe sopra «CONTO ECONOMICO» non sono del CE
    perche' il CE chiude coi costi), e le righe sotto un titolo che dichiara «nessuna sezione» (conti non
    assegnati, nota) restano senza."""
    da_assegnare: list[tuple[int, int]] = []
    fuori = False
    for n, righe in enumerate(pagine):
        for k, r in enumerate(righe):
            titolo = _titolo_sezione(r, colonne)
            if titolo is not None:
                da_assegnare, fuori = [], titolo == ""
            if per_pagina[n][k] == "" and not fuori:
                da_assegnare.append((n, k))
            if not da_assegnare or not _ha_celle(r, colonne):
                continue
            testo = re.sub(r"\s+", " ", _testo(r).upper())
            sezione = "SP" if _CHIUSURA_SP.search(testo) else "CE" if _CHIUSURA_CE.search(testo) else None
            if sezione:
                for i, j in da_assegnare:
                    per_pagina[i][j] = sezione
                da_assegnare = []


def _sezioni_dei_lati(pagine: list[list[RigaFisica]], colonne: list[Colonna],
                      confine: float) -> dict[tuple[int, float, str], str]:
    """Due tabelle affiancate (1426: lo stato patrimoniale a sinistra, «CE - Schema Ridotto» a destra): in una
    pagina dove ogni meta' stampa il suo titolo, ciascuna ha la sua sezione. Con un titolo in una meta' sola il
    titolo vale per tutta la riga, come per un documento a una tabella (1430: i costi a sinistra e i ricavi a
    destra del conto economico)."""
    def meta(r: RigaFisica, lato: str) -> RigaFisica:
        return RigaFisica(r.pagina, r.y, [p for p in r.parole if ((p.x0 + p.x1) / 2 < confine) == (lato == "L")])

    per_lato = {lato: _sezioni([[meta(r, lato) for r in rr] for rr in pagine], colonne, []) for lato in ("L", "R")}
    out: dict[tuple[int, float, str], str] = {}
    for n, rr in enumerate(pagine):
        if all(any(_titolo_sezione(meta(r, lato), colonne) is not None for r in rr) for lato in ("L", "R")):
            for lato in ("L", "R"):
                out.update({(r.pagina, r.y, lato): s for r, s in zip(rr, per_lato[lato][n])})
    return out


def _senza_riepilogo(grezze: list[list[tuple]], titolo: int | None) -> list[list[tuple]]:
    """La pagina senza le righe di chiusura stampate subito sotto il suo ultimo titolo di sezione: «Totale Costi: /
    Perdita d'Esercizio:» sotto «Conto Economico» e' il riepilogo che apre la sezione, non la chiusura (1432: il CE
    comincia in fondo a pagina 2 e prosegue nelle pagine dopo, che senza titolo restavano senza sezione)."""
    if titolo is None:
        return grezze
    fine = titolo + 1
    while fine < len(grezze) and _TOTALE_DI_CHIUSURA.search(" ".join(str(w[4]) for w in grezze[fine]).upper()):
        fine += 1
    return grezze[:titolo + 1] + grezze[fine:]


def _sezioni(pagine: list[list[RigaFisica]], colonne: list[Colonna], avvisi: list[str]) -> list[list[str]]:
    """Per pagina e riga, la sezione: l'ultimo titolo sopra la riga; sopra il primo titolo, la sezione della
    pagina prima finche' quella non si e' chiusa col suo totale; una pagina senza titoli che chiude con un
    totale dell'altra sezione decide da se' (`collect_source_rows` 255-267, `sezione_della_chiusura`)."""
    ultima, chiusa = "", False
    out = []
    for righe in pagine:
        titoli = []
        ultimo_titolo = None
        for k, r in enumerate(righe):
            s = _titolo_sezione(r, colonne)
            if s is None and not ultima:
                s = _titolo_debole(r, colonne)
            if s is None and not titoli and (not ultima or chiusa) and _titolo_di_lato(r, colonne):
                s = "SP"        # solo dove nessuna sezione e' aperta: a meta' di un CE «PASSIVO ...» resta un conto
            if s is not None:
                titoli.append((r.y, s))
                ultimo_titolo = k
        grezze = _tuple(righe)
        chiusura = _SEZIONI.get(sezione_della_chiusura(grezze) or "")
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
        # la chiusura conta solo dopo l'ultimo titolo della pagina: «TOTALE PASSIVO» sopra «Conto economico»
        # chiude lo SP, non il CE che comincia sotto (Fase 5, F1b: 1434, 1433, 1405)
        chiusa = _chiude(_senza_riepilogo(grezze, ultimo_titolo) if ultimo_titolo is None
                         else _senza_riepilogo(grezze[ultimo_titolo:], 0))
    _sezioni_dai_totali_di_conti(pagine, out)
    _sezioni_dalle_chiusure(pagine, colonne, out)
    return out


# --------------------------------------------------------------------------------------
# Parti del documento: prospetto, nota, altro
# --------------------------------------------------------------------------------------

# Titoli che aprono una parte. Un titolo e' una riga corta senza importi che COMINCIA cosi': la prosa della nota
# nomina il conto economico a meta' frase, il titolo lo stampa in testa. La rideterminazione del reddito ai fini
# fiscali in coda a una situazione contabile e' un prospetto fiscale, non di bilancio (budget_395, 700).
_TITOLO_NOTA = re.compile(
    r"^(?:nota integrativa|relazione (?:sulla gestione|del collegio|della societa di revisione|del revisore|unitaria)"
    r"|rendiconto finanziario|(?:prospetto (?:di |della )?)?movimentazion|variazioni nell|informativa\b"
    r"|informazioni (?:sull|sui\b|sul\b|sugli|relative|in calce|ex art|ai sensi)|analisi delle variazioni"
    r"|rideterminazione (?:del )?risultato"
    # i titoli delle tabelle della nota che le tabelle OCR stampano, e la stampa a se' dei ratei (R21: budget_210)
    r"|(?:composizione|dettaglio|movimenti|indicatori|indici|flussi finanziari)\b)")
# «Informazioni …» senza le parole della nota («Informazioni generali sull'impresa» dei micro XBRL) e' un titolo
# debole: apre la nota solo se sotto non ci sono le prove di un prospetto (R12).
_TITOLO_NOTA_DEBOLE = re.compile(r"^informazioni\b")
_TITOLO_NOTA_OVUNQUE = ("possibilita di utilizzazione",)
# Il titolo di un prospetto e' tutto il rigo: il nome, e al piu' parti e date («STATO PATRIMONIALE - ATTIVO»,
# «SITUAZIONE PATRIMONIALE dal 01/01/2026 al 30/09/2026»). «Conto economico i canoni corrisposti…» e' prosa.
_TITOLO_PROSPETTO = re.compile(
    r"^(?:[a-e]\s?\)\s*)?(?:stato patrimoniale|conto economico|situazione (?:patrimoniale|economica|contabile)"
    r"|bilancio di verifica)"
    r"(?:\s*[-\u2013:]?\s*(?:attivo|passivo|attivita|passivita|e|ed|patrimonio netto|netto|costi|ricavi|al|dal|del"
    r"|periodo|esercizio|ordinario|abbreviato|\(?micro\)?|in forma abbreviata|riclassificato|in unita di euro"
    r"|\d[\d/.\-]*))*$")
_TITOLO_MAX = 90
# Una pagina del prospetto senza titolo proprio, con almeno tanti importi di cui meno della meta' nelle colonne dei
# prospetti, e' una tabella con colonne sue: nota (la rideterminazione del reddito fiscale, budget_395 p. 6-7).
_MIN_IMPORTI_GEOMETRIA = 4
_QUOTA_COLONNE_PROSPETTO = 0.5
# Prove di un prospetto su una riga con importi (R12: una prova vince su un titolo della nota). Un totale dei
# prospetti basta; le voci con la numerazione di legge («A)», «B) II», «C.II.2», «21) Utile») contano da tre in su,
# perche' anche la nota numera i suoi elenchi («1) Totale dell'attivo dello stato patrimoniale: 220.000 euro»).
_TOTALE_PROSPETTO = re.compile(
    r"^(?:totale (?:attivo|passivo|patrimonio netto|valore della produzione|costi della produzione)\b"
    r"|differenza tra valore e costi|risultato prima delle imposte"
    r"|(?:\d{1,2}\s?\)\s*|[ivx]+\s?[-.)]\s*)?utile\s*[(/]?\s*perdit\w*\)?\s*(?:dell|d)\W*esercizio)")
_VOCE_NUMERATA = re.compile(r"^(?:\d{1,2}\s?\)|[a-e]\s?\))\s")
_MIN_VOCI_PROVA = 3


def _importi_grezzi(r: RigaFisica) -> list[Parola]:
    """Gli importi della riga prima di conoscere le colonne (`colonne._in_colonna` + `_e_importo`)."""
    return [p for p in r.parole if p.x0 > _X0_MINIMO and (i := leggi_importo(p.testo)) is not None
            and i.forma != "zero"]


def _titolo_parte(r: RigaFisica) -> str | None:
    if _importi_grezzi(r):
        return None
    n = _norm(_testo(r)).replace("'", "").replace("`", "")
    if len(n) > _TITOLO_MAX:
        return None
    if _TITOLO_NOTA.match(n) or any(t in n for t in _TITOLO_NOTA_OVUNQUE):
        return "nota"
    if _TITOLO_NOTA_DEBOLE.match(n):
        return "nota-debole"
    if _TITOLO_PROSPETTO.match(n):
        return "prospetto"
    return None


def _etichetta_grezza(r: RigaFisica) -> list[Parola]:
    importi = set(map(id, _importi_grezzi(r)))
    return [p for p in r.parole if id(p) not in importi]


def _numeri(r: RigaFisica) -> int:
    """Quanti numeri ha la riga nella zona degli importi: importi, interi nudi e trattini."""
    return sum(1 for p in r.parole if p.x0 > _X0_MINIMO and (leggi_importo(p.testo) is not None
                                                              or _INTERO.match(p.testo)))


def _prova(r: RigaFisica, larghezza: int | None = None) -> str | None:
    """«totale» se la riga e' un totale dei prospetti, «voce» se e' una voce con la numerazione di legge; solo su
    una riga con importi e, se `larghezza` e' data, con non piu' numeri delle colonne dei prospetti: la tabella
    della nota sulle variazioni del patrimonio netto ha una riga «Totale patrimonio netto» con un numero per ogni
    riserva, e non e' un prospetto."""
    if not _importi_grezzi(r) or (larghezza is not None and _numeri(r) > larghezza):
        return None
    testo = _etichetta_grezza(r)
    trovato = _codice_in_testa(testo)
    if testo and _PERCORSO_LEGGE.match(testo[0].testo):
        return "voce"
    etichetta = " ".join(p.testo for p in testo[trovato[1] if trovato else 0:]).strip()
    n = _norm(etichetta).replace("'", " ")
    if _TOTALE_PROSPETTO.match(n):
        return "totale"
    if _VOCE_LEGGE.match(etichetta) or _VOCE_NUMERATA.match(n):
        return "voce"
    return None


@dataclass
class _Banda:
    pagina: int             # 0-based
    parte: str | None
    righe: list[RigaFisica]
    titolo: str | None = None   # la parte del titolo che apre la banda, None se continua

    def prove(self, larghezza: int | None = None) -> bool:
        tipi = [t for r in self.righe if (t := _prova(r, larghezza)) is not None]
        return "totale" in tipi or len(tipi) >= _MIN_VOCI_PROVA


def _bande_del_documento(pagine: list[list[RigaFisica]], altezze: list[float], margini: set[str]) -> list[_Banda]:
    """Le bande di righe: una nuova a ogni titolo e a ogni pagina, con la parte che il titolo apre o che continua
    dalla banda prima. Le righe di margine ripetute non sono titoli («Nota integrativa XBRL al … Pag. N»)."""
    bande: list[_Banda] = []
    stato: str | None = None
    for n, righe in enumerate(pagine):
        corrente: _Banda | None = None
        for r in righe:
            t = None if (_nel_margine(r, altezze[n]) and chiave_ripetuta(_testo(r)) in margini) else _titolo_parte(r)
            if t is not None:
                stato, corrente = t, None
            if corrente is None:
                corrente = _Banda(n, stato, [], t)
                bande.append(corrente)
            corrente.righe.append(r)
    return bande


def _parti(pagine: list[list[RigaFisica]], altezze: list[float], margini: set[str]) -> dict[int, str]:
    """id(riga) -> parte, per bande (`_bande_del_documento`). Prima di ogni titolo una banda e' prospetto se ha
    importi, altro se no. Una banda con le prove di un prospetto (`_prova`) e' prospetto qualunque titolo l'abbia
    aperta: perdere un prospetto in silenzio e' il danno peggiore (R12). Poi la geometria, solo sulle bande del
    prospetto senza prove: e' nota una banda con gli importi per lo piu' fuori dalle colonne dei prospetti, o che
    continua con colonne proprie la tabella della nota della banda prima."""
    bande = _bande_del_documento(pagine, altezze, margini)
    for b in bande:
        if b.parte is None:
            b.parte = "prospetto" if any(_importi_grezzi(r) for r in b.righe) else "altro"

    # Le colonne dei prospetti: quelle delle bande prima della nota aperte da un titolo di prospetto o con le prove
    # di un prospetto (o di tutto il prospetto, se non ce ne sono), presenti su almeno meta' delle loro pagine o su
    # almeno due. Una tabella che sta su una pagina sola non e' una colonna dei prospetti.
    prima_nota = next((i for i, b in enumerate(bande) if b.parte in ("nota", "nota-debole")), len(bande))
    fonte = ([b for b in bande[:prima_nota] if b.parte == "prospetto" and (b.titolo == "prospetto" or b.prove())]
             or [b for b in bande if b.parte == "prospetto"])
    candidate = colonne_documento([r for b in fonte for r in b.righe])
    pagine_fonte = {b.pagina for b in fonte}
    per_pagina: dict[int, Counter] = {}
    for b in fonte:
        conta = per_pagina.setdefault(b.pagina, Counter())
        conta.update(c.indice for r in b.righe for p in _importi_grezzi(r)
                     if (c := colonna_di(p.x1, candidate)) is not None)
    presenze = Counter(i for conta in per_pagina.values() for i, k in conta.items() if k >= 2)
    # ...o su almeno due pagine: la colonna di destra delle contrapposte ha importi solo sulle pagine del passivo e
    # dei ricavi (budget_375: 3 pagine su 7)
    principali = [c for c in candidate if presenze[c.indice] * 2 >= len(pagine_fonte) or presenze[c.indice] >= 2]

    # Le prove: una banda del prospetto che le ha non si declassa; una banda «altro», o aperta da un titolo debole
    # («Informazioni generali sull'impresa»), che le ha e' prospetto. Un titolo forte della nota resta nota anche
    # sopra le stesse voci: il rendiconto finanziario comincia dall'utile, il riepilogo del bilancio della
    # controllante e la riconciliazione delle imposte le ripetono.
    larghezza = max(len(principali), 2)
    provate = set()
    for i, b in enumerate(bande):
        if b.parte != "nota" and b.prove(larghezza):
            b.parte = "prospetto"
            provate.add(i)
        elif b.parte == "nota-debole":
            b.parte = "nota"
    proprie_prima: list[float] = []
    for i, b in enumerate(bande):
        importi = [p for r in b.righe for p in _importi_grezzi(r)]
        fuori = [p.x1 for p in importi if colonna_di(p.x1, principali) is None]
        if b.parte == "prospetto" and i not in provate and len(importi) >= _MIN_IMPORTI_GEOMETRIA and (
                len(fuori) > (1 - _QUOTA_COLONNE_PROSPETTO) * len(importi)
                or any(abs(x - y) <= _TOL_X_CODICE * 2 for x in _bordi(fuori, minimo=3) for y in proprie_prima)):
            b.parte = "nota"
        if b.parte == "nota":
            proprie_prima = _bordi(fuori, minimo=3)
        elif importi:
            proprie_prima = []
    return {id(r): b.parte for b in bande for r in b.righe}


def _bordi(xs: list[float], minimo: int = 2) -> list[float]:
    """I bordi destri mediani dei gruppi di `xs` a non piu' di 14 pt l'uno dall'altro (`colonne._colonne_dai_bordi`),
    con almeno `minimo` elementi."""
    gruppi: list[list[float]] = []
    for x in sorted(xs):
        if gruppi and x - gruppi[-1][-1] <= 14.0:
            gruppi[-1].append(x)
        else:
            gruppi.append([x])
    return [statistics.median(g) for g in gruppi if len(g) >= minimo]


def _parti_pagina(pagine: list[list[RigaFisica]], parti: dict[int, str]) -> tuple[dict[int, str], list]:
    """(pagina -> parte prevalente, bande). Prevale la parte con piu' righe con importi, poi con piu' righe."""
    per_pagina: dict[int, str] = {}
    bande: list[tuple[int, float, str]] = []
    for n, righe in enumerate(pagine, start=1):
        if not righe:
            continue
        conta = Counter()
        for r in righe:
            parte = parti[id(r)]
            conta[parte] += 1 + 1000 * bool(_importi_grezzi(r))
            if not bande or bande[-1][2] != parte:
                bande.append((n, r.y, parte))
        per_pagina[n] = conta.most_common(1)[0][0]
    return per_pagina, bande


# Un trattino seguito a meno di tanto da una parola e' un separatore, non uno zero (come `righe._STACCO_CELLA_TESTO`).
_STACCO_SEPARATORE = 8.0


def _zeri(r: RigaFisica) -> list[Parola]:
    """Gli zeri della zona degli importi («0», «-»): una colonna della tabella che stampa solo zeri accanto a un importo
    e' comunque una colonna («Totali 191.633 0 0», budget_1437 p17)."""
    out = []
    for i, p in enumerate(r.parole):
        if p.x0 <= _X0_MINIMO or p.testo not in ("0", "-", "\u2013"):
            continue
        dopo = r.parole[i + 1] if i + 1 < len(r.parole) else None
        if p.testo != "0" and dopo is not None and any(ch.isalpha() for ch in dopo.testo) \
                and dopo.x0 - p.x1 <= _STACCO_SEPARATORE:
            continue    # il trattino di un elenco o di una descrizione («- canoni di leasing»), non uno zero
        out.append(p)
    return out


def _riga_di_tabella(r: RigaFisica) -> bool:
    """Una riga con importi, o con un trattino nella zona degli importi: la riserva a zero «Riserve statutarie -
    A,B,C,D» (budget_1315 p17) e' una riga della tabella, e una serie di righe cosi' non la spezza in due."""
    return bool(_importi_grezzi(r)) or any(p.x0 > _X0_MINIMO and p.testo in ("-", "\u2013") for p in r.parole)


def _tabelle_nota(pagine: list[list[RigaFisica]], parti: dict[int, str]) -> list[TabellaNota]:
    """Le tabelle della nota: per pagina, i blocchi di righe della tabella (`_riga_di_tabella`) separati da almeno
    due righe di testo; titolo la riga di testo appena sopra, o l'ultimo titolo della nota. Le colonne sono i bordi
    destri dei suoi importi e dei suoi zeri."""
    out = []
    titolo_nota = ""
    for righe in pagine:
        blocco: list[RigaFisica] = []
        testo_fra = 0
        sopra = ""

        def chiudi():
            if blocco:
                out.append(TabellaNota(blocco[0].pagina, blocco[0].y, blocco[-1].y, sopra or titolo_nota,
                                       tuple(_bordi([p.x1 for r in blocco for p in _importi_grezzi(r) + _zeri(r)]))))

        for r in righe:
            if parti[id(r)] != "nota":
                chiudi()
                blocco, testo_fra, sopra = [], 0, ""
                continue
            if _titolo_parte(r) == "nota":
                titolo_nota = _testo(r)
            if _riga_di_tabella(r):
                if testo_fra >= 2:
                    chiudi()
                    blocco = []
                blocco.append(r)
                testo_fra = 0
            else:
                testo_fra += 1
                if testo_fra >= 2 or not blocco:
                    if testo_fra >= 2:
                        chiudi()
                        blocco = []
                    sopra = _testo(r)
        chiudi()
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


def _codice_in_testa(parole: list[Parola], cifre_min: int = _CIFRE_MIN_CODICE) -> tuple[str, int] | None:
    """(sagoma, token di codice) del codice che apre `parole`, o None. Il codice e' il primo token con
    una cifra e quelli di sole cifre che lo seguono («707245 000», «CII1A 208.00121»), o un codice spaziato
    («4 / 5 / 1»); un codice seguito da «bis)», «ter)» e' una voce («5 bis)»). Con meno di `cifre_min` cifre non e'
    un codice («1.1 roe»): le forme del profilo ne vogliono tre; il lettore di righe ne accetta meno solo per la
    famiglia di una forma, allineata (il mastro «48»)."""
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
    if sum(ch.isdigit() for t in testi[:n] for ch in t) < cifre_min:
        return None
    return " ".join(_sagoma(t) for t in testi[:n]), n


def _e_token_forma(t: str, primo: bool) -> bool:
    rx = _TOKEN_FORMA if primo else _TOKEN_SEGUITO_FORMA
    return bool(rx.fullmatch(t) and leggi_importo(t) is None and not AMOUNT_LIKE.match(t)
                and not DATE_RE.fullmatch(t))


_FILETTO = re.compile(r"^[|\u00a6]+$")


def senza_filetti(parole: list[Parola]) -> list[Parola]:
    """Le parole senza i filetti verticali in testa e in coda («| 303.01000 RISERVE |», budget_375): non sono testo
    della riga, e in testa nascondono il codice. Lo stesso per il segno dell'euro in testa, che e' la valuta della
    cella dell'altro lato («59.743,13 €» | «04.03 Costi…», budget_1456)."""
    i, j = 0, len(parole)
    while i < j and (_FILETTO.match(parole[i].testo) or parole[i].testo.strip() == "€"):
        i += 1
    while j > i and _FILETTO.match(parole[j - 1].testo):
        j -= 1
    return parole[i:j]


def _candidati(righe: list[RigaFisica], colonne: list[Colonna], confine: float | None) -> list[_Candidato]:
    out = []
    for r in righe:
        for lato, parole in _gruppi(r, confine).items():
            celle = [p for p in parole if (t := _in_colonna(p, colonne)) is not None
                     and (confine is None or t[1].lato == lato)]
            testo = senza_filetti([p for p in parole if p not in celle])
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


_TRATTINI = ("-", "\u2013")
# Il segno meno staccato dal suo numero di un solo spazio: misurato 2,2-2,5 pt contro i 33 pt e oltre di un
# separatore di descrizione in colonna (1426).
_STACCO_SEGNO = 3.0


_TOL_COLONNA_SEGNI = 1.5


def in_colonna_di_segni(pagina: int, x1: float, segni_colonna: frozenset[tuple[int, float]]) -> bool:
    """Il trattino con bordo destro `x1` sta su una colonna di segni della pagina (centro del gruppo entro ±1,5 pt:
    le x reali oscillano di un punto, 284,0-285,2)."""
    return any(p == pagina and abs(x - x1) <= _TOL_COLONNA_SEGNI for p, x in segni_colonna)


def meno_staccato(parole: list[Parola], i: int, trovati: list, pagina: int = 0,
                  segni_colonna: frozenset[tuple[int, float]] = frozenset()) -> bool:
    """La parola `i` e' un trattino che fa da segno meno all'importo che la segue, e che sta in una colonna mentre il
    trattino no. Due forme: a un soffio dall'importo («Utile (Perdita) dell'esercizio - 1.000»; due trattini
    di fila, «merci - - 300», sono una convenzione che non si legge dal solo segno), oppure in una colonna di
    segni, trattini allineati sulla stessa x in tre o piu' righe della pagina («Passivo B) IMMOBILIZZAZIONI - FONDI
    -   1.000»: a 33 pt dall'importo, ma sempre alla stessa x)."""
    if i + 1 >= len(parole) or parole[i].testo not in _TRATTINI or trovati[i] is not None or trovati[i + 1] is None:
        return False
    imp = leggi_importo(parole[i + 1].testo)
    if imp is None or imp.forma == "zero" or imp.valore <= 0:
        return False
    if in_colonna_di_segni(pagina, parole[i].x1, segni_colonna):
        return True
    if parole[i + 1].x0 - parole[i].x1 > _STACCO_SEGNO:
        return False
    return not (i > 0 and parole[i - 1].testo in _TRATTINI)


def _segni_in_colonna(righe: list[RigaFisica], colonne: list[Colonna],
                      intere: frozenset[int]) -> frozenset[tuple[int, float]]:
    """(pagina, x media) dei gruppi di trattini che fanno una colonna di segni: tre o piu' trattini fuori colonna,
    ciascuno subito prima di un importo in colonna ma a piu' di un soffio da lui, con il bordo destro entro ±1,5 pt
    gli uni dagli altri."""
    per_pagina: dict[int, list[float]] = {}
    for r in righe:
        trovati = [_in_colonna(p, colonne, intere) for p in r.parole]
        for i, p in enumerate(r.parole[:-1]):
            if p.testo in _TRATTINI and trovati[i] is None and trovati[i + 1] is not None \
                    and r.parole[i + 1].x0 - p.x1 > _STACCO_SEGNO:
                imp = leggi_importo(r.parole[i + 1].testo)
                if imp is not None and imp.forma != "zero" and imp.valore > 0:
                    per_pagina.setdefault(r.pagina, []).append(p.x1)
    out = set()
    for pagina, xs in per_pagina.items():
        gruppo: list[float] = []
        for x in sorted(xs) + [float("inf")]:
            if gruppo and x - gruppo[-1] > _TOL_COLONNA_SEGNI:
                if len(gruppo) >= 3:
                    out.add((pagina, sum(gruppo) / len(gruppo)))
                gruppo = []
            gruppo.append(x)
    return frozenset(out)


def _negativi(righe: list[RigaFisica], colonne: list[Colonna], intere: frozenset[int],
              segni_colonna: frozenset[tuple[int, float]] = frozenset()) -> frozenset[str]:
    """Le forme del negativo viste almeno due volte sulle celle; le colonne di differenza e di percentuale
    non contano (un negativo li' e' una variazione)."""
    viste: Counter[str] = Counter()
    for r in righe:
        trovati = [_in_colonna(p, colonne, intere) for p in r.parole]
        for k, p in enumerate(r.parole):
            if meno_staccato(r.parole, k, trovati, r.pagina, segni_colonna) and \
                    trovati[k + 1][1].ruolo not in _RUOLI_ANALISI:
                viste["meno-colonna" if in_colonna_di_segni(r.pagina, r.parole[k].x1, segni_colonna) else "meno-staccato"] += 1
            trovato = _in_colonna(p, colonne, intere)
            if trovato is None or trovato[1].ruolo in _RUOLI_ANALISI or _rimando_di_nota(r.parole, k):
                continue
            testo = p.testo.replace("€", "").strip()
            if re.search(r"\s[DA]$", testo) or marcatore_dopo(r.parole, k) is not None:
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
    if forme - {"meno-staccato", "meno-colonna", "marcatore"}:
        # un documento che stampa gia' i negativi con una forma sua («-2.000» attaccato) non ne ha una seconda: il
        # trattino a un soffio di un importo li' non e' un segno (darebbe un positivo nella somma che chiude)
        forme.discard("meno-staccato")
    ruoli = {c.ruolo for c in colonne}
    if {"dare", "avere"} <= ruoli:
        forme.add("colonne-dare-avere")
    return frozenset(forme)


_MARCATORI = ("D", "A")
# La lettera D/A sta in una colonna propria subito dopo l'importo. Misurato sul corpus: 4-9 pt in dieci documenti,
# 10 pt in 1561 (lettera in una colonna fissa, a destra dell'importo allineato a destra); 12 le tiene tutte e resta
# sotto la larghezza di tre caratteri e mezzo, oltre la quale una lettera sola e' una parola dell'etichetta o della
# colonna dopo. A difendere da un «A» qualunque restano la soglia per colonna (`_colonne_a_marcatore`, 60% e 10 celle).
_STACCO_MARCATORE = 12.0
_MIN_MARCATORI = 10
_QUOTA_MARCATORI = 0.6


def _posto_marcatore(parole: list[Parola], i: int) -> int | None:
    """L'indice del marcatore D/A che segue la parola `i`, o None. Fra importo e lettera possono stare solo i
    filetti di sottolineatura dell'importo («300,00 _________ D__», token fatti di soli «_» che
    cominciano sotto l'importo); la lettera puo' portare la sua sottolineatura attaccata («D__»)."""
    j = i + 1
    while j < len(parole) and set(parole[j].testo) == {"_"} and parole[j].x0 < parole[i].x1:
        j += 1
    if j >= len(parole) or parole[j].testo.rstrip("_") not in _MARCATORI:
        return None
    return j if parole[j].x0 - parole[i].x1 <= _STACCO_MARCATORE else None


def marcatore_dopo(parole: list[Parola], i: int) -> str | None:
    """Il marcatore D/A staccato subito dopo la parola `i` («11.429.777,38 D»), o None."""
    j = _posto_marcatore(parole, i)
    return None if j is None else parole[j].testo.rstrip("_")


def _colonne_a_marcatore(righe: list[RigaFisica], colonne: list[Colonna], intere: frozenset[int]) -> frozenset[int]:
    """Q2: una colonna e' «a marcatore» quando almeno il 60% delle sue celle, e almeno 10, sono seguite da un D/A
    staccato. Si decide per colonna, non per token: due «A» sparsi in una contrapposta (365, 367) o il marcatore dei
    soli mastri (1562) non fanno una colonna a marcatore. Le colonne di differenza e di percentuale non contano."""
    celle: Counter[int] = Counter()
    marcate: Counter[int] = Counter()
    for r in righe:
        for k, p in enumerate(r.parole):
            trovato = _in_colonna(p, colonne, intere)
            if trovato is None or trovato[1].ruolo in _RUOLI_ANALISI or _rimando_di_nota(r.parole, k):
                continue
            celle[trovato[1].indice] += 1
            marcate[trovato[1].indice] += marcatore_dopo(r.parole, k) is not None
    return frozenset(c for c, n in celle.items() if marcate[c] >= _MIN_MARCATORI and marcate[c] >= _QUOTA_MARCATORI * n)


_MIN_RIGHE_COPPIA = 4
_QUOTA_CENTESIMI_PARZIALI = 0.5
_QUOTA_INTERI_TOTALI = 0.95


def _coppie(righe: list[RigaFisica], colonne: list[Colonna], intere: frozenset[int]) -> dict[int, int]:
    """Q1: le coppie (parziali, totali) del documento, come {totali: parziali}. Due colonne di valori adiacenti sullo
    stesso lato, che non stampano mai sulla stessa riga, con almeno 4 righe ciascuna; i parziali stampano i centesimi
    (almeno meta' degli importi non nulli con centesimi diversi da zero), i totali le unita' (almeno il 95% degli
    importi non nulli interi). Due colonne affiancate a centesimi o a interi (corrente e precedente di uno schema
    reso da XBRL) non sono una coppia."""
    per_colonna: dict[int, list[tuple[int, Decimal]]] = {}
    for k, r in enumerate(righe):
        for p in r.parole:
            trovato = _in_colonna(p, colonne, intere)
            if trovato is not None:
                per_colonna.setdefault(trovato[1].indice, []).append((k, trovato[0].valore))
    valori = sorted((c for c in colonne if c.ruolo in ("esercizio", "saldo")), key=lambda c: (c.lato, c.x_destra))
    out: dict[int, int] = {}
    for a, b in zip(valori, valori[1:]):
        if a.lato != b.lato or a.indice in out or a.indice in out.values():
            continue
        ra, rb = per_colonna.get(a.indice, []), per_colonna.get(b.indice, [])
        if len({k for k, _ in ra}) < _MIN_RIGHE_COPPIA or len({k for k, _ in rb}) < _MIN_RIGHE_COPPIA \
                or {k for k, _ in ra} & {k for k, _ in rb}:
            continue
        va, vb = [v for _, v in ra if v], [v for _, v in rb if v]
        if not va or not vb:
            continue
        centesimi = sum(v != v.to_integral_value() for v in va) / len(va)
        interi = sum(v == v.to_integral_value() for v in vb) / len(vb)
        if centesimi >= _QUOTA_CENTESIMI_PARZIALI and interi >= _QUOTA_INTERI_TOTALI:
            out[b.indice] = a.indice
    return out


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

    # I margini come prima, sulle colonne di tutte le righe; poi le parti, e le colonne solo sul prospetto.
    margini = _ripetute(pagine, altezze_l, colonne_documento([r for p in pagine for r in p]))
    parti = _parti(pagine, altezze_l, margini)
    colonne = colonne_documento([r for p in pagine for r in p if parti[id(r)] == "prospetto"])
    parti_pagina, bande = _parti_pagina(pagine, parti)
    tabelle = _tabelle_nota(pagine, parti)
    parti_righe = {(r.pagina, r.y): parti[id(r)] for rr in pagine for r in rr}
    scartate = frozenset((r.pagina, r.y) for n, rr in enumerate(pagine) for r in rr
                         if _scartata(r, altezze_l[n], colonne, margini))
    pagine_tutte = pagine
    pagine = [[r for r in rr if (r.pagina, r.y) not in scartate] for rr in pagine]
    tutte = [r for rr in pagine for r in rr]
    prospetto = [r for r in tutte if parti[id(r)] == "prospetto"]
    decimali = _decimali(prospetto, colonne)
    intere = frozenset(i for i, d in decimali.items() if d is False)

    tipo_parole, voci, quota, perche_parole = _parole_del_tipo(prospetto, colonne)
    confine = confine_ammesso(prospetto, colonne)
    assegna_lati(colonne, confine)
    # i titoli del documento stanno anche fuori dal prospetto e nei margini ripetuti; mai nella nota
    completa_periodi(colonne, [r for rr in pagine_tutte for r in rr if parti[id(r)] == "prospetto"],
                     [r for rr in pagine_tutte for r in rr if parti[id(r)] != "nota"], avvisi)
    ruoli = {c.ruolo for c in colonne}
    if tipo_parole is not None:
        tipo, perche = tipo_parole, "parole"
    elif confine is not None:
        tipo, perche = "contrapposte", f"geometria: due lati simmetrici, confine a x={confine:.1f}"
    elif ruoli & _RUOLI_VERIFICA:
        tipo, perche = "verifica", "colonne " + "/".join(sorted(ruoli & _RUOLI_VERIFICA))
    elif quota >= _QUOTA_CODICI:
        tipo, perche = "verifica", "codici conto senza voci di legge"
    else:
        tipo, perche = "ignoto", "nessuna regola decide"
    contrapposto = confine is not None and tipo in ("contrapposte", "verifica")
    if confine is not None and not contrapposto:
        avvisi.append(f"due tabelle affiancate: lati fisici, non sezioni contrapposte (confine a x={confine:.1f}, "
                      f"tipo {tipo})")
    indizio = _indizio(prospetto)
    tipo_perche = f"{perche}; {perche_parole}; {indizio}"
    if tipo == "ignoto":
        avvisi.append(f"tipo non determinato ({perche_parole}; {indizio})")
    elif indizio.split()[1] not in _MACRO_ATTESA[tipo]:
        avvisi.append(f"tipo {tipo}, ma il {indizio} (solo un indizio)")

    per_riga = _sezioni(pagine, colonne, avvisi)
    sezioni_righe = {(r.pagina, r.y): s for rr, ss in zip(pagine, per_riga) for r, s in zip(rr, ss)}
    sezioni_lati = _sezioni_dei_lati(pagine, colonne, confine) if confine is not None and not contrapposto else {}
    segni_colonna = _segni_in_colonna(prospetto, colonne, intere)
    return Profilo(tipo, tipo_perche, colonne, confine, _negativi(prospetto, colonne, intere, segni_colonna), decimali,
                   _forme(_candidati(prospetto, colonne, confine)), _sezioni_pagina(pagine, per_riga),
                   frozenset(margini), avvisi, contrapposto, parti_pagina, bande, tabelle, scartate, sezioni_righe,
                   parti_righe, _colonne_a_marcatore(prospetto, colonne, intere), _coppie(prospetto, colonne, intere),
                   sezioni_lati, segni_colonna, _colonne_intere_di_fatto(prospetto, colonne))
