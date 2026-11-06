"""Copie dei nomi privati dei moduli vecchi che il lettore usa (Fase 2, Task 1).

Il lettore non importa piu' un nome con il trattino iniziale da fuori del pacchetto: una correzione
al percorso vecchio non puo' cambiarlo in silenzio. Ogni copia dice da dove viene (modulo, nome, commit
di `main`). `tests/lettore/test_ereditati.py` confronta ogni copia con l'originale: quando l'originale
cambia il test cade, e si decide se portare la correzione qui.

Dove la copia dipende da altri privati del modulo d'origine, si copia anche quello. I privati di
`xbrl_reso_parser` letti da `schema_legge_generico` via `reso.` stanno qui con prefisso `_reso_`/`_RESO_`,
perche' i loro nomi collidono con quelli di `schema_legge_generico`.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Optional


# da importers/schema_legge_generico.py:_PIEDE, main e3455d6
PIEDE = re.compile(r"\bpag(?:ina|\.)?\s*\d*\s*(?:di\s*\d*)?\s*$|^pagina\b|\butente\s*:")

# da importers/schema_legge_generico.py:_PAROLE_TESTATA, main e3455d6
PAROLE_TESTATA = {"al", "anno", "esercizio", "esercizi", "bilancio", "periodo", "differenza",
                   "diff", "diff.", "scost", "scost.", "scostamento", "variazione", "var", "var.",
                   "%", "euro", "importi", "in", "valori", "corrente", "precedente", "consuntivo",
                   "importo", "descrizione", "comparato"}

# da importers/schema_legge_generico.py:_RADICI, main e3455d6
_RADICI = ("Stato patrimoniale", "Attivo", "Passivo", "Conto economico")

# da importers/schema_legge_generico.py:_RE_ROMANO, main e3455d6
_RE_ROMANO = re.compile(r"^(VIII|VII|VI|IV|IX|III|II|V|X|I)(?:\s*[\)\.\-–:]\s*|\s+(?=[A-Za-z]))(.*)$")

# da importers/schema_legge_generico.py:_RE_CAPITALE, main e3455d6
_RE_CAPITALE = re.compile(r"^([A-E])\s*[\)\.]\s*(.*)$")

# da importers/schema_legge_generico.py:_RE_ARABO, main e3455d6
_RE_ARABO = re.compile(r"^(\d{1,2})\s*-?\s*(bis|ter|quater|quinquies)?\s*(?:[\)\.]\s+|\)(?=[A-Za-z]))(.*)$",
                       re.I)

# da importers/schema_legge_generico.py:_RE_LETTERA, main e3455d6
_RE_LETTERA = re.compile(r"^([a-z])\s*-?\s*((?i:bis|ter))?(\d)?\s*\)\s*(.*)$")

# da importers/schema_legge_generico.py:_RE_TOTALE_CON_CODICE, main e3455d6
_RE_TOTALE_CON_CODICE = re.compile(
    r"^(?:[A-Z]|[IVX]+|\d{1,2}(?:-?(?:bis|ter|quater))?|[a-z]\d?(?:-?bis)?"
    r"|[A-E\d][A-E\d+\-±/b ]*[+\-±][A-E\d+\-±/b ]*)\)?\s+(totale\b.*)$", re.I)

# da importers/schema_legge_generico.py:_RE_FORMULA_PRIMA_IMPOSTE, main e3455d6
_RE_FORMULA_PRIMA_IMPOSTE = re.compile(r"^a-b[+\-±]+c[+\-±]+d(?:[+\-±]+e)?\)?$")

# da importers/schema_legge_generico.py:_SCADENZA, main e3455d6
_SCADENZA = re.compile(r"^(?:crediti\s+|debiti\s+|importi\s+)?(?:esigibil[ie]\s+)?(entro|oltre)\b", re.I)

# da importers/schema_legge_generico.py:_SCADENZA_IN_CODA, main e3455d6
_SCADENZA_IN_CODA = re.compile(r"\besigibil[ie]\s+(entro|oltre)\b", re.I)

# da importers/schema_legge_generico.py:_CALCOLATI, main e3455d6
_CALCOLATI = (
    (re.compile(r"^(?:totale\s+)?diff(?:erenza|\.)?\s+(?:tra\s+)?(?:i\s+)?valor[ei]\s*(?:e|-)\s*cost[oi]"),
     "Differenza tra valore e costi della produzione"),
    (re.compile(r"^(?:totale\s+)?ris(?:ultato|\.)?\s+prima\s+delle\s+imposte"),
     "Risultato prima delle imposte"),
    (re.compile(r"^totale\s+(?:diff(?:erenza|\.)?\s+)?(?:tra\s+)?proventi\s+ed?\s+oneri\s+finanziari"),
     "Totale proventi e oneri finanziari"),
    (re.compile(r"^totale\s+(?:delle\s+)?rett(?:ifiche|\.)"),
     "Totale delle rettifiche di valore di attivita' e passivita' finanziarie"),
    (re.compile(r"^totale\s+(?:2[02]\s*\)\s*)?(?:delle\s+)?imposte"),
     "Totale delle imposte sul reddito dell'esercizio"),
)

# da importers/schema_legge_generico.py:_norm, main e3455d6
def _norm(testo: str) -> str:
    testo = "".join(c for c in unicodedata.normalize("NFKD", testo) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", testo).strip().casefold()

# da importers/schema_legge_generico.py:_ricompatta_spaziato, main e3455d6
def _ricompatta_spaziato(testo: str) -> str:
    """ "S T A T O P A T R I M O N I A L E" -> "STATOPATRIMONIALE"."""
    if re.fullmatch(r"(?:\S ){3,}\S", testo):
        return testo.replace(" ", "")
    return testo

# da importers/schema_legge_generico.py:_scadenza, main e3455d6
def _scadenza(testo: str) -> Optional[str]:
    m = _SCADENZA.match(testo)
    if not m:
        return None
    return "esigibili entro l'esercizio successivo" if m.group(1).lower() == "entro" \
        else "esigibili oltre l'esercizio successivo"

# da importers/schema_legge_generico.py:_scadenza_in_coda, main e3455d6
def _scadenza_in_coda(testo: str) -> Optional[str]:
    """ "Debiti verso banche esigibili oltre l'esercizio successivo" sotto la voce 4): la lettera
    e' la ripartizione per scadenza della voce, non una sotto-voce di legge."""
    m = _SCADENZA_IN_CODA.search(testo)
    if not m:
        return None
    return _scadenza(m.group(1) + " " + testo[m.end():])

# da importers/schema_legge_generico.py:_forma, main e3455d6
def _forma(didascalia: str) -> Optional[str]:
    """La didascalia nella forma che il cuore del lettore di legge capisce; None = da saltare."""
    t = _ricompatta_spaziato(didascalia.strip())
    t = re.sub(r"^[\-–•*]+\s*", "", t)
    t = re.sub(r"\)\s*,\s*", "), ", t)          # "b) , c) da titoli" -> "b), c) da titoli"
    if re.match(r"^totali\b", t, re.I):
        t = "Totale" + t[6:]                     # "TOTALI DEBITI ( D )"
    n = _norm(t)
    if not n:
        return None
    if n.startswith("di cui"):
        return None             # memo dentro la voce sopra, gia' compreso nel suo importo
    m = re.match(r"^(.{3,30}?)\s*totale\b", n)
    if m and _RE_FORMULA_PRIMA_IMPOSTE.match(m.group(1).replace(" ", "")):
        return "Risultato prima delle imposte"
    m = _RE_TOTALE_CON_CODICE.match(t)
    if m:
        t, n = m.group(1), _norm(m.group(1))
    for rx, forma in _CALCOLATI:
        if rx.match(n):
            return forma
    if n.startswith("totale"):
        # "Totale attivo", "TOTALE STATO PATRIMONIALE - ATTIVO"; mai "Totale attivo circolante"
        # ne' "Totale attivita' finanziarie"
        m = re.match(r"^totale (?:(?:dello )?stato patrimoniale\W*)?(attivo|attivita|passivo|passivita)\b"
                     r"(?!\s*(?:circolant|finanziar))", n)
        if m and len(n) < 50:
            return "Totale attivo" if m.group(1).startswith("attiv") else "Totale passivo"
        return "Totale" + t[6:]
    if (re.match(r"^(?:2[123]\s*[\)\.]\s*)?(?:utile|perdita|risultato)\b", n) and "esercizio" in n
            and not re.match(r"^(?:utile|perdita)[^,]*(?:portat|ripianat)", n)):
        return "Utile (perdita) dell'esercizio"
    if _RESO_RE_GRUPPO.match(t):
        return t                # "c), d), e) trattamento ...": raggruppamento, gia' in forma
    m = _RE_CAPITALE.match(t)
    if m and m.group(2):
        return f"{m.group(1)}) {m.group(2)}"
    m = _RE_ROMANO.match(t)
    if m and m.group(2):
        return f"{m.group(1)} - {m.group(2)}"
    m = _RE_ARABO.match(t)
    if m:
        suff = f"-{m.group(2).lower()}" if m.group(2) else ""
        resto = m.group(3)
        if _SCADENZA.match(resto):
            return _scadenza(resto)
        numero = m.group(1)
        if numero == "22" and _norm(resto).startswith("imposte"):
            numero = "20"       # numerazione dello schema prima del D.Lgs. 139/2015
        return f"{numero}{suff}) {resto}"
    m = _RE_LETTERA.match(t)
    if m:
        resto = m.group(4)
        s = _scadenza(resto) or _scadenza_in_coda(resto)
        if s:
            return s
        if m.group(3) and not m.group(2):
            return resto        # "d5) da altri": dettaglio numerato della lettera d), non una lettera
        suff = f"-{m.group(2).lower()}" if m.group(2) else ""
        return f"{m.group(1)}{suff}) {resto}"
    if _SCADENZA.match(t):
        return _scadenza(t)
    return t

# da importers/schema_legge_generico.py:_strutturale, main e3455d6
def _strutturale(didascalia: str) -> bool:
    return bool(_reso_enumeratore(didascalia) or _reso_e_totale(didascalia)
                or _reso_scadenza(didascalia) or _reso_calcolato(didascalia)
                or didascalia in _RADICI)

# da importers/schema_legge_generico.py:_forma_strutturale, main e3455d6
def forma_strutturale(didascalia: str) -> bool:
    forma = _forma(didascalia)
    return bool(forma) and _strutturale(forma)

# da importers/schema_legge_generico.py:_intestazione, main e3455d6
def intestazione(didascalia: str) -> list[str]:
    """Le righe di sezione ("STATO PATRIMONIALE - ATTIVO", "Passivo e netto", "CONTO ECONOMICO")
    nella forma del lettore: una lista vuota se non e' un'intestazione."""
    n = _norm(_ricompatta_spaziato(didascalia))
    # il titolo con la sua lettera ("A) STATO PATRIMONIALE - ATTIVO", "E) CONTO ECONOMICO")
    n = re.sub(r"^[a-z]\s*\)\s*(?=stato patrimoniale|conto economico)", "", n)
    # le date e gli anni delle colonne stampati sulla stessa riga del titolo
    n = re.sub(r"\b(?:\d{2}[-/.]\d{2}[-/.])?20\d{2}\b", " ", n)
    n = re.sub(r"\b(?:al|esercizio|bilancio al)\s*$", " ", n.strip())
    # "BILANCIO DI ESERCIZIO AL 31/12/2025 PASSIVO E PATRIMONIO NETTO": il titolo del documento
    # davanti al titolo di sezione
    n = re.sub(r"^bilancio\s+(?:di\s+|d'\s*)?esercizio\s+(?:al\s+)?(?=\S)", "", n.strip())
    n = re.sub(r"[\-–:]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    if n.startswith("totale"):
        return []
    compatto = n.replace(" ", "").replace("'", "")
    if compatto.startswith("contoeconomico") and len(compatto) < 40:
        return ["Conto economico"]
    if re.fullmatch(r"bilancio .*conto economico.*", n) and len(n) < 60:
        return ["Conto economico"]
    for chiave, out in (("statopatrimonialeattiv", ["Stato patrimoniale", "Attivo"]),
                        ("statopatrimonialepassiv", ["Stato patrimoniale", "Passivo"]),
                        ("statopatrimoniale", ["Stato patrimoniale"])):
        if compatto.startswith(chiave) and len(compatto) <= len(chiave) + 14:
            return out
    if compatto in ("attivo", "attivita"):
        return ["Attivo"]
    if compatto in ("passivo", "passivita", "passivoenetto", "passivoepatrimonionetto",
                    "passivitaenetto", "passivitaepatrimonionetto"):
        return ["Passivo"]
    return []

# da importers/schema_legge_generico.py:_e_differenza, main e3455d6
def e_differenza(valori: list[list[Optional[Decimal]]], k: int, a: int, b: int) -> bool:
    """La colonna k e' a - b (o il suo opposto) su ogni riga che le porta tutte e tre."""
    prove = [(r[a], r[b], r[k]) for r in valori if r[a] is not None and r[b] is not None
             and r[k] is not None and (r[a] != 0 or r[b] != 0)]
    if len(prove) < 3:
        return False
    return all(abs(x - y - z) <= Decimal("0.01") or abs(y - x - z) <= Decimal("0.01")
               or abs(abs(x - y) - abs(z)) <= Decimal("0.01") for x, y, z in prove)

# ---- xbrl_reso_parser: i privati che forma_strutturale legge via `reso.` (rinominati _reso_*/_RESO_*) ----

# da importers/xbrl_reso_parser.py:_ENUM_ARABO, main e3455d6
_RESO_ENUM_ARABO = r"\d+(?:-bis|-ter|-quater)?"

# da importers/xbrl_reso_parser.py:_ENUM_LETTERA, main e3455d6
_RESO_ENUM_LETTERA = r"[a-z](?:-bis|-ter)?"

# da importers/xbrl_reso_parser.py:_RE_CAPITALE, main e3455d6
_RESO_RE_CAPITALE = re.compile(r"^([A-E])\)\s")

# da importers/xbrl_reso_parser.py:_RE_ROMANO, main e3455d6
_RESO_RE_ROMANO = re.compile(r"^(I|II|III|IV|V|VI|VII|VIII|IX|X)\s-\s")

# da importers/xbrl_reso_parser.py:_RE_ARABO, main e3455d6
_RESO_RE_ARABO = re.compile(rf"^({_RESO_ENUM_ARABO})\)\s")

# da importers/xbrl_reso_parser.py:_RE_LETTERA, main e3455d6
_RESO_RE_LETTERA = re.compile(rf"^({_RESO_ENUM_LETTERA})\)\s")

# da importers/xbrl_reso_parser.py:_RE_GRUPPO, main e3455d6
_RESO_RE_GRUPPO = re.compile(
    rf"^((?:(?:{_RESO_ENUM_ARABO}|{_RESO_ENUM_LETTERA})\),\s*)+(?:{_RESO_ENUM_ARABO}|{_RESO_ENUM_LETTERA})\))\s")

# da importers/xbrl_reso_parser.py:_RE_CHIAVE, main e3455d6
_RESO_RE_CHIAVE = re.compile(rf"({_RESO_ENUM_ARABO}|{_RESO_ENUM_LETTERA})\)")

# da importers/xbrl_reso_parser.py:_norm, main e3455d6
def _reso_norm(testo: str) -> str:
    return re.sub(r"\s+", " ", testo.replace("\n", " ")).strip().casefold()

# da importers/xbrl_reso_parser.py:_enumeratore, main e3455d6
def _reso_enumeratore(didascalia: str):
    """(tipo, [chiavi]) oppure None. Tipi: L capitale, R romano, N arabo, l lettera minuscola."""
    m = _RESO_RE_GRUPPO.match(didascalia)
    if m:
        chiavi = _RESO_RE_CHIAVE.findall(m.group(1))
        tipo = "N" if _RESO_RE_ARABO.match(chiavi[0] + ") ") else "l"
        return tipo, chiavi
    for tipo, rx in (("L", _RESO_RE_CAPITALE), ("R", _RESO_RE_ROMANO), ("N", _RESO_RE_ARABO), ("l", _RESO_RE_LETTERA)):
        m = rx.match(didascalia)
        if m:
            return tipo, [m.group(1)]
    return None

# da importers/xbrl_reso_parser.py:_e_totale, main e3455d6
def _reso_e_totale(didascalia: str) -> bool:
    return _reso_norm(didascalia).startswith("totale")

# da importers/xbrl_reso_parser.py:_calcolato, main e3455d6
def _reso_calcolato(didascalia: str) -> Optional[str]:
    n = _reso_norm(didascalia)
    if n.startswith("differenza tra valore e costi"):
        return "differenza"
    if n.startswith("risultato prima delle imposte"):
        return "prima_imposte"
    if re.match(r"^21\)\s", n) or n.startswith("utile (perdita) dell'esercizio"):
        return "utile"
    return None

# da importers/xbrl_reso_parser.py:_scadenza, main e3455d6
def _reso_scadenza(didascalia: str) -> Optional[str]:
    n = _reso_norm(didascalia)
    if n.startswith("esigibili entro"):
        return "E"
    if n.startswith("esigibili oltre"):
        return "O"
    return None

# da importers/xbrl_reso_parser.py:_CONNETTIVI, main e3455d6
_CONNETTIVI = {"di", "e", "dei", "delle", "del", "della", "degli", "in", "su", "per", "da", "a",
               "con", "o", "ed", "al", "alle", "nel", "nella", "che"}

# da importers/xbrl_reso_parser.py:_FASCIA_MARGINE, main e3455d6
FASCIA_MARGINE = 0.09

# da importers/xbrl_reso_parser.py:_frase_aperta, main e3455d6
def frase_aperta(didascalia: str) -> bool:
    """La didascalia finisce a meta' frase (virgola o preposizione): la riga sotto la continua,
    anche quando la tabella ha lo stesso passo fra le righe e fra le righe a capo."""
    t = didascalia.rstrip()
    return t.endswith(",") or t.rsplit(" ", 1)[-1].casefold() in _CONNETTIVI

# da importers/xbrl_reso_parser.py:_chiave_ripetuta, main e3455d6
def chiave_ripetuta(testo: str) -> str:
    """Il testo di una riga di margine con i numeri tolti: "Pag. 2" e "Pag. 3" sono la stessa."""
    return re.sub(r"\d+", "#", _reso_norm(testo))

# da importers/standard_ivcee_parser.py:_AMOUNT_LIKE, main e3455d6
AMOUNT_LIKE = re.compile(r"^\d{1,3}(?:\.\d{3})+$")

# da importers/standard_ivcee_parser.py:_DATE_RE, main e3455d6
DATE_RE = re.compile(r"\d{2}[-/]\d{2}[-/]20\d{2}")

# da importers/detail_enrichment.py:_AMOUNT, main e3455d6
_AMOUNT = re.compile(r"^(?:-?\d+(?:\.\d{3})*(?:,\d{1,2})?-?|\(\d+(?:\.\d{3})*(?:,\d{1,2})?\))$")

# da importers/detail_enrichment.py:_amount, main e3455d6
def _amount(token: str) -> Decimal | None:
    if not _AMOUNT.fullmatch(token):
        return None
    negative = token.startswith(("-", "(")) or token.endswith("-")
    try:
        value = Decimal(token.strip("()-").replace(".", "").replace(",", "."))
        return -value if negative else value
    except InvalidOperation:
        return None

# da importers/detail_enrichment.py:_TOTALE_DI_CHIUSURA, main e3455d6
_TOTALE_DI_CHIUSURA = re.compile(
    r"TOTALE\s*(?:A\s*PAREGGIO|A\s*QUADRATURA|ATTIVIT|PASSIVIT|ATTIVO|PASSIVO|COSTI|RICAVI)"
    r"|(?:UTILE|PERDITA)\S*\s+(?:D\W?\s*)?ESERCIZIO|ECCEDENZA")

# da importers/detail_enrichment.py:_RIGHE_DI_CHIUSURA, main e3455d6
_RIGHE_DI_CHIUSURA = 5

# da importers/detail_enrichment.py:_CHIUSURA_PER_SEZIONE, main e3455d6
_CHIUSURA_PER_SEZIONE = (
    ('ce', re.compile(r"TOTALE\s*(?:COSTI|RICAVI)")),
    ('bs', re.compile(r"TOTALE\s*(?:ATTIVIT|PASSIVIT|ATTIVO\b|PASSIVO\b)")),
)

# da importers/detail_enrichment.py:_sezione_della_chiusura, main e3455d6
def sezione_della_chiusura(full_rows) -> str | None:
    """La sezione che la pagina dichiara chiudendo: un totale di costi/ricavi fra le ultime
    righe con importi e' il CE, uno di attivita'/passivita' lo SP; un pareggio non dice nulla."""
    con_importi = [line for line in full_rows
                   if any(_amount(str(w[4])) is not None for w in line)]
    for line in con_importi[-_RIGHE_DI_CHIUSURA:]:
        testo = ' '.join(str(w[4]) for w in line).upper()
        for sezione, rx in _CHIUSURA_PER_SEZIONE:
            if rx.search(testo):
                return sezione
    return None

# da importers/detail_enrichment.py:_chiude_sezione, main e3455d6
def chiude_sezione(full_rows) -> bool:
    """La pagina chiude la sua sezione: fra le ultime righe con importi c'e' un totale di
    chiusura, il risultato d'esercizio o il pareggio senza didascalia (due importi uguali e
    nient'altro: budget_702 «Perdita Esercizio 15.063,40» / «2.329.010,83 2.329.010,83»;
    budget_1450 «Totale a pareggio» in fondo a pagina 2). Un riepilogo in testa alla pagina
    («Totale Attivita': Totale Passivita':» sotto il titolo, budget_1432) non chiude."""
    con_importi = [line for line in full_rows
                   if any(_amount(str(w[4])) is not None for w in line)]
    for line in con_importi[-_RIGHE_DI_CHIUSURA:]:
        testo = [str(w[4]) for w in line]
        if _TOTALE_DI_CHIUSURA.search(' '.join(testo).upper()):
            return True
        importi = [_amount(t) for t in testo]
        if (len(testo) == 2 and None not in importi and importi[0] == importi[1]
                and importi[0] != 0):
            return True
    return False

# da importers/import_snello/righe.py:_lista_concatenata, main e3455d6
def lista_concatenata(vivo: list[bool]) -> tuple[list[int], list[int]]:
    """nxt/prv sulle sole posizioni vive, saltando le altre: n (fuori lista) e -1 come
    sentinelle di fine e inizio."""
    n = len(vivo)
    nxt, prv = [n] * n, [-1] * n
    precedente = -1
    for i in range(n):
        if vivo[i]:
            if precedente != -1:
                nxt[precedente] = i
            prv[i] = precedente
            precedente = i
    return nxt, prv

# da importers/mineru_adapter.py:_TableHTMLParser, main e3455d6
class TableHTMLParser(HTMLParser):
    """Minimal <table> parser → list of rows, each a list of cell strings."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._cur: Optional[list[str]] = None
        self._buf: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._cur = []
        elif tag in ("td", "th"):
            self._in_cell = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cur is not None:
            self._cur.append("".join(self._buf).strip())
            self._in_cell = False
            self._buf = []
        elif tag == "tr" and self._cur is not None:
            self.rows.append(self._cur)
            self._cur = None

    def handle_data(self, data):
        if self._in_cell:
            self._buf.append(data)
