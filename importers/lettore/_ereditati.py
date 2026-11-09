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

from importers.rimanenze_ce import natura_rimanenze


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


# da importers/import_snello/conti.py:_IMMOBILIZZAZIONI, main c57e232
IMMOBILIZZAZIONI = ("sp02", "sp03", "sp04")


# da importers/import_snello/conti.py:_netta_fondi_negativi, main c57e232
def netta_fondi_negativi(importi: dict) -> dict:
    """Un fondo puo' essere piu' fine del lordo stampato: se un dettaglio di immobilizzazioni
    (sp02/sp03/sp04) resta negativo dopo la sottrazione del fondo, l'importo si sposta sul
    valore diretto dell'aggregato e il dettaglio sparisce - senza dettaglio si netta
    all'aggregato."""
    from importers.import_snello.percorsi import NOMI
    from importers.iv_cee_hierarchy import detail_fields

    importi = dict(importi)
    for aggregato in IMMOBILIZZAZIONI:
        pieno = NOMI.get(aggregato)
        if not pieno:
            continue
        for dettaglio_pieno in detail_fields(pieno):
            codice = dettaglio_pieno.split("_")[0]
            v = importi.get(codice)
            if v is not None and v < 0:
                importi[aggregato] = importi.get(aggregato, Decimal(0)) + importi.pop(codice)
    return importi


# da importers/import_snello/conti.py:_clamp_immobilizzazioni_negative, main c57e232
def clamp_immobilizzazioni_negative(bs: dict) -> list:
    """Un fondo non puo' mai superare il proprio cespite lordo: un'immobilizzazione netta ancora negativa a
    livello di AGGREGATO (dopo ``netta_fondi_negativi``) si azzera - mai spostata su un altro campo, ne' lasciata
    negativa - e l'eccedenza tagliata si dichiara (resta sbilancio dichiarato)."""
    from importers.import_snello.percorsi import NOMI

    tagliate = []
    for breve in IMMOBILIZZAZIONI:
        pieno = NOMI.get(breve)
        if pieno and bs.get(pieno, Decimal(0)) < 0:
            tagliate.append([pieno, str((-bs[pieno]).quantize(Decimal("0.01")))])
            bs[pieno] = Decimal(0)
    return tagliate


# da importers/situazione_contabile_parser.py:_FONDO_AMM_HEAD_RE, main c57e232
FONDO_AMM_HEAD_RE = re.compile(
    r"^\s*(?:F\s*[./]\s*D[OI]|FD[OI]|FOND[OI]|F)\s*[./]?\s*"
    r"AMM(?:ORT\w*|\.?\s*TO|\.?\s*NTO)?\s*[./]?\s*"
)


# da importers/situazione_contabile_parser.py:_kw_match, main c57e232
def _kw_match(desc_upper: str, keywords) -> bool:
    return all(kw in desc_upper for kw in keywords)


# da importers/situazione_contabile_parser.py:_kw_any, main c57e232
def _kw_any(desc_upper: str, keywords) -> bool:
    return any(kw in desc_upper for kw in keywords)


# da importers/situazione_contabile_parser.py:_sp02_detail_field, main c57e232
def dettaglio_sp02(desc_upper: str) -> Optional[str]:
    """Return the B.I detail supported by the source description, if explicit."""
    if _kw_any(desc_upper, ['COSTI DI IMPIANTO', "COSTI D'IMPIANTO"]):
        return 'sp02a_costi_impianto'
    if _kw_any(desc_upper, ['SVILUPP', 'RICERCA']):
        return 'sp02b_costi_sviluppo'
    if _kw_any(desc_upper, ['BREVETT', 'SOFTWARE', 'OPERE INGEGNO', 'PROCEDURE ELABOR']):
        return 'sp02c_brevetti'
    if _kw_match(desc_upper, ['DIRITTI', 'UTILIZZ']):   # "F.DO AMM.TO DIRITTI UTILIZZO" (1343)
        return 'sp02c_brevetti'
    if _kw_any(desc_upper, ['CONCESS', 'LICENZ', 'MARCHI']):
        return 'sp02d_concessioni'
    if 'AVVIAMENTO' in desc_upper:
        return 'sp02e_avviamento'
    if _kw_any(desc_upper, ['IN CORSO', 'ACCONT']):
        return 'sp02f_immob_in_corso'
    # migliorie su beni di terzi ("MAN. E RIPARAZ. SU BENI DI TERZI"): B.I.7
    if _kw_any(desc_upper, ['PLURIENN', 'IMMATERIAL', 'BENI DI TERZ', 'BENI TERZI', 'MANUT',
                            'RIPARAZ', 'MAN.E RIP', 'MIGLIORIE']):
        return 'sp02g_altre_immob_imm'
    return None


# da importers/situazione_contabile_parser.py:_sp03_detail_field, main c57e232
def dettaglio_sp03(desc_upper: str) -> Optional[str]:
    """Return the B.II detail from semantics, independently of account codes."""
    if _kw_any(desc_upper, ['IN CORSO', 'ACCONT']):
        return 'sp03e_immob_in_corso'
    if (_kw_any(desc_upper, ['TERREN', 'FABBRICAT', 'COSTRUZIONI LEGGER'])
            or _kw_match(desc_upper, ['COSTR', 'LEGGER'])):     # "F.DO AMM.COSTR.LEGGERE"
        return 'sp03a_terreni_fabbricati'
    if 'ATTREZ' in desc_upper:                 # anche "ATTREZ./REPARTO OFFIC" (budget_680)
        return 'sp03c_attrezzature'
    # "MOBIL" ma non dentro IMMOBIL...: "IMMOBILIZZI TECNICI" non e' un mobile
    # "MACCH. ORD. UFFICI", "MACCH. UFF. ELETTRON", "AUTOV. DA TRASPORT" (budget_1343)
    if re.search(r'(?<!IM)MOBIL|MACC\w*\.?\s*(?:ORD|UFF)|\bAUTOV', desc_upper) or _kw_any(desc_upper, [
        "MACCHINE D'UFFICIO", 'MACCHINE UFFICIO', 'MACCHINE UFF', 'ARRED',
        'AUTOMEZZ', 'AUTOVEICOL', 'AUTOVETTUR', 'AUTO.', 'AUTO,', 'AUTOCARR',
        'BENI VALORE', 'BENI DI VALORE', 'HARDWARE', 'CELLULAR', 'CENTRALINO',
        'TELEFON', 'MEZZI TRASP', 'ALTRI BENI MATERIAL',
    ]):
        return 'sp03d_altri_beni'
    # "MACCHIN/IMP", "MACC./IMP.", "IMP.DEPURAZIONE" (budget_680)
    # "F.DO AMMTO IMP AUDIO-VIDEO SORV"
    if (_kw_any(desc_upper, ['IMPIANT', 'MACCHINAR', 'MACCHIN/', 'MACCHIN.', 'MACC.', 'IMP.', 'IMP/'])
            or re.search(r'\bIMP\b', desc_upper)):
        return 'sp03b_impianti_macchinari'
    return None


# da importers/situazione_contabile_parser.py:_SP_ATTIVO_RULES, branch fase4 b224c95
_SP_ATTIVO_RULES = [
    # Fixed assets (gross — will be netted against depreciation)
    (['IMMOBILIZZAZIONI IMMATERIALI'], 'gross_sp02'),
    (['IMMOBILIZZAZIONI MATERIALI'], 'gross_sp03'),
    (['IMMOBILIZZAZIONI FINANZIARIE'], 'gross_sp04'),
    # "IMMOBILIZZI FINANZIARI" (budget_680): senza questa regola vinceva MOBILI, che e'
    # sottostringa di IMMOBILIZZI, e i depositi cauzionali diventavano arredi
    (['IMMOBILIZZI', 'FINANZ'], 'gross_sp04'),
    # Immobilizzazioni in corso e acconti (B.II.5 / B.I.6) — a LEGITIMATE fixed
    # asset. Must precede the ANTICIP rule below so a real immob. acconto is not
    # demoted to a credit.
    (['IMMOBILIZZAZIONI', 'CORSO'], 'gross_sp03'),
    (['IMMOBILIZZAZIONI', 'ACCONT'], 'gross_sp03'),
    # Credits explicitly labelled as immobilised belong to B.III even when the
    # account number is gestionale-specific (AGO: "Crediti v/altri (EE-immob.)").
    # non 'IMMOB' da solo: "Crediti vs. Ad Immobiliare" e' un credito (M.C.T. 30/06/2026)
    (['CREDITI', 'IMMOBILIZZ'], 'gross_sp04'),
    (['CREDITI', 'IMMOB.'], 'gross_sp04'),
    (['CREDITI', 'IMMOBILE'], 'gross_sp04'),          # "Crediti per acquisto immobile" (AITEC)
    # An advance on a CANONE / lease ("ANTICIPO X CANONI MACCHINARI") is a credit,
    # not the machine — must precede the MACCHINAR category rule. Narrow to CANON on
    # purpose: a blanket ANTICIP rule would (a) demote a genuine acconto to PURCHASE
    # a cespite ("ANTICIPI SU MACCHINARI" = B.II.5 immobilizzazione) to crediti, and
    # (b) leak into _semantic_section_from_desc, mis-guessing customer advances
    # ("CLIENTI C/ANTICIPI" = a liability) onto the asset side. Generic supplier
    # advances ("ANTICIPI A FORNITORI") already fall to the sp06 default below.
    (['ANTICIP', 'CANON'], 'sp06'),
    # AGO-style single-category descriptions (trial balance parent level)
    (['ONERI', 'PLURIENN'], 'gross_sp02'),
    (['COSTI', 'PLURIENN'], 'gross_sp02'),
    (['COSTI', 'IMPIANTO'], 'gross_sp02'),
    (['COSTI', 'AMPLIAMENT'], 'gross_sp02'),   # B.I.1 e' "costi di impianto E DI AMPLIAMENTO"
    (['SOFTWARE'], 'gross_sp02'),
    (['BREVETT'], 'gross_sp02'),
    (['MARCHI'], 'gross_sp02'),
    (['AVVIAMENTO'], 'gross_sp02'),
    (['LICENZ'], 'gross_sp02'),
    # B.I.7 "costi su beni di terzi" (migliorie/lavori su beni non di proprieta').
    # Il repo lo tratta gia' come IMMATERIALE sul lato fondo (regola F.DO+AMM+MANUT
    # "spese di manut.beni di ter(zi)"); senza la regola simmetrica qui il cespite
    # finiva nei crediti mentre il suo fondo nettava le immobilizzazioni MATERIALI
    # (budget_281: 4.500,00 in sp06 e 2.471,86 sottratti a sp03).
    (['BENI DI TERZ'], 'gross_sp02'),
    # Oneri pluriennali scritti per esteso (budget_367: "Altre spese ad utilita'
    # pluriennale", "Manutenzioni e riparazioni da ammortizzare", "Disaggi su
    # prestiti" — quest'ultimo gia' immateriale lato fondo, _FONDO_IMMAT_KW):
    # finivano nel default crediti.
    (['SPESE', 'PLURIENN'], 'gross_sp02'),
    (['DA AMMORTIZZ'], 'gross_sp02'),
    (['DISAGG'], 'gross_sp02'),
    (['CONTENITOR'], 'gross_sp03'),
    (['FABBRICAT'], 'gross_sp03'),
    (['TERREN'], 'gross_sp03'),
    (['MACCHINAR'], 'gross_sp03'),
    (['MACCHINE'], 'gross_sp03'),
    (['IMPIANT'], 'gross_sp03'),
    # 'ATTREZ' e non 'ATTREZZ': "ATTREZ." compare troncato nelle stampe a colonna
    # stretta. Allargamento per PREFISSO, quindi additivo (ogni ATTREZZ contiene ATTREZ).
    (['ATTREZ'], 'gross_sp03'),
    (['ATTR', 'MINUT'], 'gross_sp03'),   # "ATTR.VARIE E MINUTE (<516,46 E.)"
    # Categorie di cespite gia' riconosciute lato FONDO (_FONDO_CATEGORY_KW) ma
    # assenti qui: il fondo nettava sp03 mentre il suo cespite finiva nei crediti.
    (['TELEFON'], 'gross_sp03'),
    (['AUTOMEZZ'], 'gross_sp03'),
    (['AUTOVEICOL'], 'gross_sp03'),
    (['AUTOVETTUR'], 'gross_sp03'),
    (['AUTOCARR'], 'gross_sp03'),                 # budget_238: finiva nei crediti
    # budget_680: sigle e categorie che nessuna regola riconosceva
    (['MACCHIN/'], 'gross_sp03'),
    (['MACC.', 'IMP'], 'gross_sp03'),
    (['HARDWARE'], 'gross_sp03'),
    (['CELLULAR'], 'gross_sp03'),
    (['CENTRALINO'], 'gross_sp03'),
    (['COSTRUZIONI', 'LEGGER'], 'gross_sp03'),
    (['CERTIFICAZION'], 'gross_sp02'),
    # beni strumentali sotto 516,46 euro ("BENI DI VALORE UNITARIO INFERIORE")
    (['BENI', 'VALORE', 'INFERIOR'], 'gross_sp03'),
    (['CESPITI'], 'gross_sp03'),                 # "CESPITI INFERIORI A € 516,45" (Santini)
    (['MEZZI', 'TRASP'], 'gross_sp03'),
    (['AUTO', 'MOTO'], 'gross_sp03'),
    (['ARREDAMENT'], 'gross_sp03'),
    (['MOBILI'], 'gross_sp03'),
    (['ALTRI', 'BENI', 'MATERIAL'], 'gross_sp03'),
    (['PARTECIPAZ'], 'gross_sp04'),
    # Current assets
    (['RIMANENZE'], 'sp05'),
    (['MAGAZZIN'], 'sp05'),
    # Common trial-balance abbreviation: "Rim. mat. prime, sussid. e consumo".
    (['RIM', 'MAT', 'PRIM'], 'sp05'),
    (['GIACENZ'], 'sp05'),                       # "COLORANTI/GIACENZE" (budget_680)
    (['RATEI', 'RISCONTI', 'ATTIV'], 'sp10'),
    (['RATEI', 'ATTIV'], 'sp10'),
    (['RISCONTI', 'ATTIV'], 'sp10'),
    (['DISPONIBILIT'], 'sp09'),  # Disponibilità liquide (banks + cash)
    (['DEPOSIT', 'BANCAR'], 'sp09'),
    (['DEPOSIT', 'POSTAL'], 'sp09'),
    (['DENARO'], 'sp09'),
    (['CASSA'], 'sp09'),
    # conto corrente bancario a saldo dare (budget_680: "BANCA DI ASTI C/C...", mastro
    # "BANCHE"); a saldo avere sta nel passivo e lo leggono le regole di debito. Prima i
    # crediti che nominano una banca ("CREDITI V/BANCHE PER RIMBORSO CARTA", AIC) e
    # l'erario ("ritenute su C/C bancari", MBS): restano crediti, come prima.
    (['CREDIT'], 'sp06'),
    (['ERARIO'], 'sp06'),
    (['DEBIT'], 'sp06'),        # "DEBITI V/BANCHE" stampato all'attivo (AIC): come prima
    (['BANCA ', 'C/C'], 'sp09'),
    (['BANCHE'], 'sp09'),
    # Everything else in attivo = crediti (sp06)
]

# da importers/situazione_contabile_parser.py:_SP_PASSIVO_RULES, branch fase4 b224c95
_SP_PASSIVO_RULES = [
    # B.1 funds are not depreciation contra-accounts.  Keep these before every
    # AMM rule: "amministratori" contains the substring "AMM" and previously
    # made a fondo fine-mandato look like a tangible depreciation fund.
    (['QUIESCENZA'], 'sp14'),
    (['INDENNIT', 'MANDATO'], 'sp14'),
    (['FINE', 'MANDATO'], 'sp14'),               # "F.DO TRATT.FINE MANDATO(TFM)"
    (['T.F.M'], 'sp14'),                          # "F.DO T.F.M. AMMINISTRATORE" (Santini)
    # "F.DO INDENNITA' ANZIANITA' DIPEND." e' il TFR col nome di prima del 1982
    (['INDENNIT', 'ANZIANIT'], 'sp15'),
    # Depreciation funds (will be netted against gross assets)
    # Specific rules first (pluriennali/macchine disambiguate immat vs mat)
    (['F.DO', 'AMM', 'PLURIENN'], 'depr_sp02'),
    (['F.DO', 'AMM', 'IMMAT'], 'depr_sp02'),
    (['F.DO', 'AMM', 'SOFTWARE'], 'depr_sp02'),
    (['F.DO', 'AMM', 'BREVETT'], 'depr_sp02'),
    (['F.DO', 'AMM', 'MARCHI'], 'depr_sp02'),
    (['F.DO', 'AMM', 'AVVIAMENTO'], 'depr_sp02'),
    # Truncated gestionale captions (budget_343/348, Bilancino 31-5-26): the
    # column clips the description, so the canonical keywords above never fire
    # and the fondo fell through to the tangible fallback.
    (['F.DO', 'AMM', 'SW'], 'depr_sp02'),                  # "F.do amm.sw in concessione capitalizz"
    (['F.DO', 'AMM', 'COSTI DI IMPIANTO'], 'depr_sp02'),   # B.I.1, before the IMPIANT→sp03 rule
    (['F.DO', 'AMM', "COSTI D'IMPIANTO"], 'depr_sp02'),
    (['F.DO', 'AMM', 'AMPLIAMENT'], 'depr_sp02'),          # idem B.I.1 (budget_158 CONA)
    (['F.DO', 'AMM', 'MANUT'], 'depr_sp02'),               # "spese di manut.beni di ter(zi)" B.I.7
    (['F.DO', 'AMM', 'BENI DI TERZ'], 'depr_sp02'),        # idem, grafia "lav. str. su beni di terzi"
    (['F.DO', 'AMM', 'LICENZE'], 'depr_sp02'),
    (['F.DO', 'AMM', 'OPERE INGE'], 'depr_sp02'),
    (['F.DO', 'AMM', 'CERTIFICAZ'], 'depr_sp02'),           # budget_680, B.I immateriale          # "F.do amm.dir.brev.e utilizz.opere inge"
    (['F.DO', 'AMM', 'DIR.BREV'], 'depr_sp02'),
    (['F.DO', 'AMM', 'RICERCA'], 'depr_sp02'),             # B.I.2 sviluppo (Santini)
    (['F.DO', 'AMM', 'DIRITTI'], 'depr_sp02'),             # "F.DO AMM.TO DIRITTI UTILIZZO" (budget_1343)
    (['F.DO', 'AMM', 'SVILUPPO'], 'depr_sp02'),
    (['FOND', 'AMM', 'IMMOBILIZZAZ. IMM'], 'depr_sp02'),   # mastro "FONDI AMMORT. IMMOBILIZZAZ. IMM"
    (['F.DO', 'AMM', 'MACCHINE'], 'depr_sp03'),
    (['F.DO', 'AMM', 'MACCHINAR'], 'depr_sp03'),
    (['F.DO', 'AMM', 'IMPIANT'], 'depr_sp03'),
    (['F.DO', 'AMM', 'ATTREZZ'], 'depr_sp03'),
    (['F.DO', 'AMM', 'AUTO'], 'depr_sp03'),
    (['F.DO', 'AMM', 'FABBRICAT'], 'depr_sp03'),
    (['F.DO', 'AMM', 'MATER'], 'depr_sp03'),
    (['F/AMM', 'IMMAT'], 'depr_sp02'),
    (['F/AMM', 'MATER'], 'depr_sp03'),
    (['AMMORTAM', 'IMMAT'], 'depr_sp02'),
    (['AMMORTAM', 'MATER'], 'depr_sp03'),
    # "FONDI/FONDO AMM.TO IMMOB. (IM)MATERIALI" — no 'F.DO' token, 'AMM.TO' not 'AMMORTAM'
    # (BILAGRA "BILANCIO DI VERIFICA", e.g. AITEC). IMMAT must precede MATER because
    # "IMMATERIALI" also contains the "MATER" substring.
    (['FOND', 'AMM', 'IMMAT'], 'depr_sp02'),
    (['FOND', 'AMM', 'MATER'], 'depr_sp03'),
    # Safe tangible fallback.  Do not use bare "AMM": it also matches words
    # such as AMMINISTRATORI.  Real depreciation captions use AMM. / AMM.TO or
    # the full AMMORT... stem; asset-specific cases were handled above.
    (['F.DO', 'AMM.'], 'depr_sp03'),
    (['F.DO', 'AMMORT'], 'depr_sp03'),
    # Crediti deduction
    (['F.DO', 'SVAL', 'CREDITI'], 'deduct_crediti'),
    (['RISCHI', 'CREDITI'], 'deduct_crediti'),
    (['SVALUT', 'CREDITI'], 'deduct_crediti'),
    # Banks avere = overdrafts
    (['DISPONIBILIT'], 'bank_avere'),
    # Equity (sub2 total and sub3 components)
    (['PATRIMONIO NETTO'], 'equity_total'),
    (['UTILI', 'DESTINAZ'], 'equity_total'),      # "Utili in attesa di destinaz." (Napolitano)
    (['CAPITALE'], 'equity_total'),
    (['RISERVA'], 'equity_total'),
    (['RISERVE'], 'equity_total'),
    (['UTILE', 'ESERCIZ'], 'equity_total'),
    (['PERDITA', 'ESERCIZ'], 'equity_total'),
    (['UTILI', 'PORTATI'], 'equity_total'),
    (['UTILI', 'NUOVO'], 'equity_total'),
    (['PERDITE', 'PORTATE'], 'equity_total'),
    (['SOVRAPPREZZO'], 'equity_total'),
    (['CAP.', 'SOC'], 'equity_total'),
    # Fondi
    (['FONDI', 'RISCHI'], 'sp14'),
    (['FONDI', 'ONERI'], 'sp14'),
    (['FONDO', 'RISCHI'], 'sp14'),
    (['FONDO', 'ONERI'], 'sp14'),
    # TFR
    (['TFR'], 'sp15'),
    (['T.F.R'], 'sp15'),
    (['TRATTAMENTO', 'FINE', 'RAPPORTO'], 'sp15'),
    (['TRATT', 'FINE', 'RAPPORTO'], 'sp15'),
    # Debiti v/banche (need entro/oltre split — from details OR from "(EE)"/"(OE)" suffix)
    (['DEBITI', 'BANCH'], 'debt_bank'),
    (['DEBITI', 'FINANZIAT'], 'debt_bank'),
    (['DEBITI', 'V/FINANZ'], 'debt_bank'),      # "DEBITI V/FINANZ.ESIG.ENTRO 12M" (budget_1401): anticipi factoring compresi
    (['MUTUI'], 'debt_bank'),
    # Santini: "FINANZIAMENTO 07797790 BANCO BPM", "ANTICIPI ESTERO BPER" sotto
    # "ANTICIPI BANCARI", un conto bancario a saldo avere sotto "BANCHE"
    (['FINANZIAMENT', 'SOCI'], 'sp16'),          # un socio non e' una banca: resta sp16b
    (['FINANZIAMENT', 'TERZI'], 'sp16'),         # "FINANZIAMENTI DI TERZI" (AITEC): idem
    (['FINANZIAMENT'], 'debt_bank'),
    (['ANTICIP', 'BANC'], 'debt_bank'),
    (['BANCHE'], 'debt_bank'),
    (['OBBLIGAZION'], 'debt_bank'),
    # Ratei e risconti passivi
    (['RATEI', 'RISCONTI', 'PASSIV'], 'sp18'),
    (['RATEI', 'PASSIV'], 'sp18'),
    (['RISCONTI', 'PASSIV'], 'sp18'),
    # Debiti tributari
    (['DEBITI', 'TRIBUTAR'], 'sp16'),
    (['DEBITI', 'TRIBUTARI'], 'sp16'),
    # Debiti previdenziali
    (['DEBITI', 'PREV'], 'sp16'),
    (['DEBITI', 'SICUR'], 'sp16'),
    (['DEBITI', 'INPS'], 'sp16'),
    (['ISTIT', 'PREV'], 'sp16'),
    # Specific debt categories → sp16 (breve by default)
    (['DEBITI', 'FORNITOR'], 'sp16'),
    (['ACCONTI'], 'sp16'),
    (['ALTRI DEBITI'], 'sp16'),
    (['ALTRI', 'DEBITI'], 'sp16'),
    # SBF / crediti ceduti in passivo → sp16 (only when explicitly labeled as ceded)
    (['CREDITI', 'CEDUT'], 'sp16'),
    (['CREDITI', 'SMOBIL'], 'sp16'),
]

# da importers/situazione_contabile_parser.py:_FONDO_AMM_CANON, branch fase4 b224c95
_FONDO_AMM_CANON = 'F.DO AMM. '

# da importers/situazione_contabile_parser.py:_canon_fondo_amm, branch fase4 b224c95
def _canon_fondo_amm(desc_upper: str) -> str:
    """Collassa ogni grafia di "fondo ammortamento" sulla forma canonica `F.DO AMM.`.

    `_SP_PASSIVO_RULES` copre la categoria del cespite (MACCHINAR, ATTREZZ, AUTO,
    IMMAT...) SOLO in coppia con il token `F.DO`; la grafia con slash e' coperta
    solo insieme a IMMAT/MATER, parole che compaiono nei mastri aggregati ma MAI
    nei conti di dettaglio per categoria. Cosi' `F/AMM.MACCHINARI` non matcha
    nessuna regola, cade nel default `sp16` e diventa un DEBITO: l'attivo resta
    lordo, il passivo si gonfia della stessa massa, il bilancio pareggia lo stesso
    e nessun gate protesta (budget_281: 5 fondi su 6, 124.893,64 di 124.936,25).

    Normalizzare la TESTA una volta sola, invece di duplicare le 15 regole di
    categoria per ogni grafia, e' cio' che tiene allineati i due riconoscitori di
    fondo (`_is_fondo_amm` e questa tabella) — la loro divergenza E' il bug.

    La riscrittura tocca SOLO le stringhe che `_is_fondo_amm` ha gia' dichiarato
    fondi, quindi e' additiva per costruzione: si nettano piu' fondi, mai meno,
    e "AMMINISTRATORI C/COMPENSI" non e' raggiungibile.
    """
    if not _is_fondo_amm(desc_upper):
        return desc_upper
    canon = FONDO_AMM_HEAD_RE.sub(_FONDO_AMM_CANON, desc_upper, count=1)
    # Nessuna testa riconosciuta (dicitura non a inizio riga): meglio la stringa
    # originale che una riscrittura a caso.
    return canon if canon != desc_upper else desc_upper

# da importers/situazione_contabile_parser.py:_is_fondo_amm, branch fase4 b224c95
def _is_fondo_amm(desc_upper: str) -> bool:
    """Recognise depreciation/amortisation funds at any aggregation level, incl. the
    aggregate mastro 'FONDI AMMORTAMENTO IMMOBILIZ' the rule table below misses.

    Questa funzione governa l'INTERO netting dei fondi, quindi il pareggio di
    tutta la route C: un fondo non riconosciuto non viene sottratto dal cespite,
    l'attivo resta lordo e il passivo gonfio della stessa massa, i due lati non
    tornano e la differenza diventa residuo non classificato -> oltre l'1%
    scatta QUADRATURA MASCHERATA e l'import viene rifiutato.

    Il test a sottostringhe qui sotto e' tenuto INVARIATO (non puo' regredire
    nulla) e viene solo AFFIANCATO dalla forma canonica del normalizzatore unico,
    che collassa `F.di ammor.to`, `Fdo amm`, `Fondo amm.` su `fondo ammortamento`
    — grafie reali che il solo test a sottostringhe non vede. L'allargamento e'
    additivo per costruzione: si riconoscono piu' fondi, mai meno.
    """
    d = desc_upper
    if (('AMMORT' in d or 'AMM.TO' in d or 'AMM.NTO' in d or 'F.DO AMM' in d or 'F/AMM' in d)
            and ('FOND' in d or 'F.DO' in d or 'F/' in d)):
        return True
    try:
        from importers.label_semantics import normalize_label
    except Exception:
        return False
    # `fondo ammortamento` CONTIGUO: "Ammortamento immobilizzazioni immateriali" e
    # "Quota ammortamento esercizio" sono COSTI del conto economico, non fondi
    # dello stato patrimoniale, e non devono mai essere nettati.
    return "fondo ammortamento" in normalize_label(d)

# da importers/situazione_contabile_parser.py:_regola_sp, branch fase4 b224c95
def _regola_sp(desc_upper: str, lato: str) -> Optional[str]:
    """La voce di SP che una descrizione riconosce davvero, o None se nessuna regola la
    nomina (i classificatori ripiegano allora su crediti/debiti generici)."""
    if lato == 'attivo':
        d = re.sub(r'\bRIM\.(?=\s|$|[A-Z])', 'RIMANENZE ', desc_upper)
        regole = _SP_ATTIVO_RULES
    else:
        d = _canon_fondo_amm(desc_upper)
        regole = _SP_PASSIVO_RULES
    for keywords, field in regole:
        if _kw_match(d, keywords):
            return field
    return None

# da importers/situazione_contabile_parser.py:_CE_COST_FIELDS, branch fase4 b224c95
_CE_COST_FIELDS = frozenset({
    'ce05', 'ce06', 'ce07', 'ce08', 'ce09', 'ce10', 'ce11', 'ce11b', 'ce12',
    'ce15',                      # C.17 interessi e altri oneri finanziari
    'ce19',                      # E.21 oneri straordinari
    'ce20',                      # imposte sul reddito
})

# da importers/situazione_contabile_parser.py:_CE_REVENUE_FIELDS, branch fase4 b224c95
_CE_REVENUE_FIELDS = frozenset({
    'ce01', 'ce02', 'ce03', 'ce04',   # A) valore della produzione
    'ce13', 'ce14', 'ce16',           # C) proventi finanziari (ce16 netto)
    'ce17',                           # D) rettifiche di valore (netto)
    'ce18',                           # E.20 proventi straordinari
})

# da importers/situazione_contabile_parser.py:_resolve_field, branch fase4 b224c95
def _resolve_field(desc: str, side: Optional[str] = None,
                   statement: Optional[str] = None) -> Optional[str]:
    """Shared-tree classification, returned as a SHORT route-C key.

    `iv_cee_hierarchy.resolve` reasons in DB column names ('ce09_ammortamenti')
    while the route-C parsers work in short keys ('ce09') until _map_sc_keys.
    The short key is the db_field prefix up to the first underscore
    ('sp04a_partecipazioni' -> 'sp04a'). That split is a mechanical string
    operation, not a guarantee of routability on its own: every short key the
    tree can actually produce must also be in `pdf_importer._SC_KEY_MAP` (or
    already contain an underscore, in which case `_map_sc_keys` passes it
    through unchanged) — otherwise `_map_sc_keys` silently drops the amount.
    See `tests/test_classification_fallback.py` for the guard that checks
    this holds for every node in `data/iv_cee_tree.json`.

    Returns None when the tree does not know the description, or when it
    resolves to the OTHER statement — a balance-sheet caption must never be
    booked as a cost.
    """
    try:
        from importers.iv_cee_hierarchy import resolve as _tree_resolve
        node = _tree_resolve(desc, side, statement)
    except Exception:
        return None
    if node is None or not node.db_field:
        return None
    if statement and node.statement and node.statement != statement:
        return None
    return node.db_field.split('_', 1)[0]

# da importers/situazione_contabile_parser.py:_resolve_ce_field, branch fase4 b224c95
def _resolve_ce_field(desc: str, direction: str) -> Optional[str]:
    """Shared-tree CE classification constrained to `direction`.

    `direction` is 'costi' or 'ricavi'. Returns None when the tree does not
    know the description OR when it resolves to a voce of the OPPOSITE sign, so
    the caller falls through to its catch-all exactly as it did before the tree
    fallback was added. See _CE_COST_FIELDS / _CE_REVENUE_FIELDS for why the
    tree cannot enforce this on its own.
    """
    field = _resolve_field(desc, direction, statement='ce')
    if field is None:
        return None
    allowed = _CE_COST_FIELDS if direction == 'costi' else _CE_REVENUE_FIELDS
    return field if field in allowed else None

# da importers/situazione_contabile_parser.py:_CE_COSTI_RULES, branch fase4 b224c95
_CE_COSTI_RULES = [
    (['RIM.INIZ'], 'ce10'),
    (['RIMAN', 'INIZ'], 'ce10'),                 # "RIMAN. INIZIALI MAT. PRIME/MER" (budget_1343)
    (['ESISTENZE', 'INIZIAL'], 'ce10'),
    (['RIMANENZE', 'INIZIAL'], 'ce10'),
    (['RICAVI'], 'ce01_return'),  # Returns/discounts in cost section
    # Variazioni rimanenze MUST be before materie prime (descriptions often contain "MERCI")
    (['VARIAZ', 'RIMANENZ'], 'ce10'),
    (['VAR.RIM'], 'ce10'),
    # Materie prime / merci
    (['MATERIE PRIME'], 'ce05'),
    (['MATERIE', 'CONSUMO'], 'ce05'),
    (['COSTI', 'MAT'], 'ce05'),  # "COSTI P/MAT.PRI,SUSS.,CON.E MER."
    # "COSTI COMMERCIALI", "CONSULENZE COMMERCIALI": MERCI e' una sottostringa di
    # COMMERCIALI, e provvigioni e trasporti finivano fra le materie (Santini)
    (['COMMERCIAL'], 'ce06'),
    (['MERCI'], 'ce05'),
    (['MAT.PRI'], 'ce05'),
    (['ACQUISTI', 'DI BENI'], 'ce05'),           # B.6 (mastro "55 ACQUISTI DI BENI", Nicole)
    (['SERVIZI'], 'ce06'),
    # compensi e contributi degli amministratori: B.7 servizi, non personale
    (['AMMINISTRATOR'], 'ce06'),
    (['GODIMENTO', 'BENI'], 'ce07'),
    # Personale sub-fields (more specific than the generic 'PERSONALE' bucket)
    (['QUOTE', 'FINE', 'RAPPORTO'], 'ce08a_tfr'),
    (['QUOTE', 'TRATTAMENTO'], 'ce08a_tfr'),
    (['QUOTE', 'TFR'], 'ce08a_tfr'),
    (['QUOTA', 'TFR'], 'ce08a_tfr'),
    (['QUOTA', 'T.F.R'], 'ce08a_tfr'),
    # compensi e contributi del consiglio di amministrazione: B.7 come gli amministratori
    ([' CDA'], 'ce06'),
    (['ACCANTON', 'TFR'], 'ce08a_tfr'),
    (['TRATT', 'FINE', 'RAPPORTO'], 'ce08a_tfr'),
    (['SALARI'], 'ce08b'),
    (['STIPENDI'], 'ce08b'),
    (['ONERI', 'SOCIAL'], 'ce08c'),
    (['ONERI', 'PREVIDENZ'], 'ce08c'),
    (['ALTRI', 'COSTI', 'PERSONALE'], 'ce08d'),
    (['PERSONALE'], 'ce08'),
    # Ammortamenti (more specific keywords first)
    (['AMMORTAM', 'IMMAT'], 'ce09a'),
    (['AMM.TO', 'IMMAT'], 'ce09a'),
    (['AMM.T', 'IMM. IMMAT'], 'ce09a'),
    (['AMM.TI', 'IMMAT'], 'ce09a'),
    (['AMMORTAM', 'MATER'], 'ce09b'),
    (['AMM.TO', 'MATER'], 'ce09b'),
    (['AMM.T', 'IMM. MAT'], 'ce09b'),
    (['AMM.TO', 'MAT'], 'ce09b'),
    (['SVALUT'], 'ce09d'),  # Svalutazioni
    (['ACCANTONAM', 'RISCHI'], 'ce11'),
    (['ALTRI ACCANTONAM'], 'ce11b'),
    (['ONERI DIVERSI'], 'ce12'),
    (['ONERI', 'DIVERSI', 'GESTIONE'], 'ce12'),
    (['INTERESSI'], 'ce15'),
    (['ONERI', 'FINANZ'], 'ce15'),
    (['ON.FIN'], 'ce15'),
    (['INT. PASS'], 'ce15'),
    (['INT.PASS'], 'ce15'),                      # "INT.PASS.FINANZ.CREDEM" (budget_680)
    (['IMPOSTE', 'REDDITO'], 'ce20'),
    (['IMPOSTE', 'ESERC'], 'ce20'),
    (['IMPOSTE', 'ANTICIP'], 'ce20'),
    (['IMPOSTE', 'DIFFER'], 'ce20'),
    (['IRES'], 'ce20'),
    (['IRAP'], 'ce20'),
    # "DIFF.CAMBIO PASSIVO": C.17-bis. Mai CAMBI da solo: e' dentro "SCAMBIO SUL POSTO"
    (['DIFF', 'CAMBI'], 'ce16_cost'),
    (['SU CAMBI'], 'ce16_cost'),
    # Proventi/oneri straordinari in costs
    (['ONERI STRAORD'], 'ce19'),
    (['PROVENTI', 'PARTECIP'], 'ce13_cost'),
    # Ultime, solo se nient'altro riconosce la voce: mastri B.7 di quel gestionale
    # ("PRESTAZIONI DI LAVORO NON DIPEN(DENTE)", "GESTIONE VEICOLI AZIENDALI", "SPESE
    # AMMIN.,COMM. E DI RAPPRES.", Nicole). Prima di ONERI DIVERSI avrebbero preso il
    # mastro AGO "Oneri diversi di gestione" che porta "spese amministrative varie".
    (['LAVORO', 'NON DIPEN'], 'ce06'),
    (['GESTIONE', 'VEICOLI'], 'ce06'),
    (['SPESE', 'AMMIN'], 'ce06'),
    # mastri di Santini: acquisti B.6, lavorazioni di terzi e costi industriali/generali B.7
    (['ACQUISTI'], 'ce05'),
    (['LAV.', 'TERZI'], 'ce06'),
    (['LAVORAZION'], 'ce06'),
    (['COSTI', 'INDUSTRIAL'], 'ce06'),
    (['SPESE', 'GENERALI'], 'ce06'),
]

# da importers/situazione_contabile_parser.py:_CE_RICAVI_RULES, branch fase4 b224c95
_CE_RICAVI_RULES = [
    (['RIM.FIN'], 'ce10_close'),
    (['RIMAN', 'FINAL'], 'ce10_close'),
    (['RIMANENZE', 'FINAL'], 'ce10_close'),
    (['PROV.FIN'], 'ce14'),
    # More specific rules first
    (['VARIAZ', 'RIMANENZ'], 'ce10_close'),
    (['VAR.RIM'], 'ce10_close'),
    (['ALTRI RICAVI'], 'ce04'),
    (['ALTRI', 'PROVENTI'], 'ce04'),
    (['PROVENTI', 'PARTECIP'], 'ce13'),
    (['PROVENTI', 'FINANZ'], 'ce14'),
    (['PROVENTI STRAORD'], 'ce18'),
    # Santini, mastro "RICAVI DIVERSI": interessi, cambi, consolidato fiscale, incrementi
    (['INTERESSI', 'ATTIV'], 'ce14'),
    (['OPERAZIONI', 'FINANZ'], 'ce14'),
    (['DIFF', 'CAMBI'], 'ce16'),
    (['SU CAMBI'], 'ce16'),
    (['CONSOLIDATO', 'FISCALE'], 'ce20_provento'),   # riduce le imposte
    (['INCREM', 'IMMOB'], 'ce03'),
    (['RICAVI', 'DIVERSI'], 'ce04'),
    # Generic ricavi last (catches "RICAVI DELLE VENDITE" etc.)
    (['RICAVI'], 'ce01'),
]

# da importers/situazione_contabile_parser.py:_classify_sp_attivo, branch fase4 b224c95
def _classify_sp_attivo(desc_upper: str) -> str:
    """Classify an attivo entry by description keywords. Returns field or 'sp06' default."""
    # RIM. is a ledger abbreviation, not an unknown asset to put in receivables.
    desc_upper = re.sub(r'\bRIM\.(?=\s|$|[A-Z])', 'RIMANENZE ', desc_upper)
    desc_upper = re.sub(r'\bRIMAN\.', 'RIMANENZE ', desc_upper)     # "RIMAN.FINALI SEMILAVORATI"
    for keywords, field in _SP_ATTIVO_RULES:
        if _kw_match(desc_upper, keywords):
            return field
    return 'sp06'  # default: crediti

# da importers/situazione_contabile_parser.py:_CE_AMMORTAMENTO_RE, branch fase4 b224c95
_CE_AMMORTAMENTO_RE = re.compile(r'^AMM(?:ORTAMENT[OI]|\.?\s?TO\b|/TO\b|\.(?!NE\b))\s*')

# da importers/situazione_contabile_parser.py:_CE_AMMORTAMENTO_PRIMA_RE, branch fase4 b224c95
_CE_AMMORTAMENTO_PRIMA_RE = re.compile(
    r'^AMM(?:ORTAMENT[OI]|\.?\s?TO\b|/TO\b|\.TI\b|\.(?=ORD|CIVIL))\.?\s*')

# da importers/situazione_contabile_parser.py:_CE_COSTI_FOGLIE, branch fase4 b224c95
_CE_COSTI_FOGLIE = [
    (['TFR'], 'ce08a_tfr'),                       # "ACCAN.TFR FORMAZIONE LAVORO" (AITEC)
    (['T.F.R'], 'ce08a_tfr'),
    (['PREMI', 'PRODUZION'], 'ce08b'),            # retribuzione, non un premio assicurativo
    (['CONTRIBUTI', 'SANITAR'], 'ce08c'),         # assistenza sanitaria integrativa
    (['PREMI', 'ELEMENTI'], 'ce08b'),             # "PREMI E ALTRI ELEMENTI SIMILI"
    (['ASSISTENZA'], 'ce06'),                     # "CANONI DI ASSISTENZA TECNICA": servizio
    (['CONSUL'], 'ce06'),                         # "COMP.PROF.CONSUL.AMM.VA/FISC." (Napolitano)
    (['COMP', 'PROF'], 'ce06'),                   # compensi professionali
    (['VIAGG'], 'ce06'),
    (['RISTORANT'], 'ce06'),
    (['PERNOTT'], 'ce06'),
    (['TELEMATIC'], 'ce06'),
    (['CARBURANT'], 'ce05'),
    (['LUBRIFICANT'], 'ce05'),
    (['CANCELLERIA'], 'ce05'),
    (['IMBALLAGG'], 'ce05'),
    (['INDUMENTI'], 'ce05'),
    (['MATERIALI', 'DI '], 'ce05'),               # "MATERIALI DI PULIZIA/OFFICINA"
    (['CANONI'], 'ce07'),                         # locazione, leasing, noleggio
    (['NOLEGG'], 'ce07'),
    (['LOCAZION'], 'ce07'),
    (['AFFITT'], 'ce07'),
    (['LEASING'], 'ce07'),
    (['CONTRIBUTI', 'PREVIDENZ'], 'ce08c'),
    (['INFORTUNI'], 'ce08c'),
    (['INAIL'], 'ce08c'),
    (['MANUTENZ'], 'ce06'),
    (['RIPARAZ'], 'ce06'),
    (['TRASPORT'], 'ce06'),
    (['CONSULENZ'], 'ce06'),
    (['ENERGIA'], 'ce06'),
    (['TELEFON'], 'ce06'),
    (['ASSICURAZ'], 'ce06'),
    (['PREMI'], 'ce06'),                          # "PREMI RCA", "PREMI RCT"
    (['PROVVIGION'], 'ce06'),
    (['PEDAGG'], 'ce06'),
    (['PARCHEGG'], 'ce06'),
    (['COLLAUD'], 'ce06'),
    (['SOCCORSO'], 'ce06'),
    (['FORMAZIONE'], 'ce06'),
    (['VISITE', 'MEDICHE'], 'ce06'),
    (['INDENNIT', 'CHILOMETR'], 'ce06'),
    (['ONERI', 'BANCARI'], 'ce06'),
    (['SPESE', 'BANCARIE'], 'ce06'),
    (['SOFTWARE'], 'ce06'),
    (['SPESE', 'DI '], 'ce06'),                   # "SPESE DI TRASPORTO/INCASSO/VENDITA"
]

# da importers/situazione_contabile_parser.py:_rimanenze_per_natura, branch fase4 b224c95
def _rimanenze_per_natura(tag: str, *testi: str, ripiego: Optional[str] = None) -> str:
    """Le rimanenze di PRODOTTI vanno in A.2 (ce02), non in B.11 (ce10): il tag di
    rimanenze che le tabelle a parole danno sempre come materie ('ce10' fra i costi,
    'ce10_close' fra i ricavi) diventa 'ce02_open' (iniziali: riducono ce02) o 'ce02'
    (finali) quando la descrizione, o quella di un padre, dice prodotti. Natura non
    detta o mista: decide ``ripiego`` (la natura del lato opposto, _natura_unanime),
    poi il tag di sempre. Regola in importers/rimanenze_ce.py."""
    if tag in ('ce10', 'ce10_close') and (natura_rimanenze(*testi) or ripiego) == 'ce02':
        return 'ce02_open' if tag == 'ce10' else 'ce02'
    return tag

# da importers/situazione_contabile_parser.py:_classify_ce_costi, branch fase4 b224c95
def _classify_ce_costi(desc_upper: str) -> Optional[str]:
    """Classify a CE cost entry by description keywords."""
    m = _CE_AMMORTAMENTO_PRIMA_RE.match(desc_upper)
    if m and desc_upper[m.end():].strip() and 'SVAL' not in desc_upper \
            and 'FONDO' not in desc_upper and 'F.DO' not in desc_upper:
        resto = desc_upper[m.end():]
        immat = _classify_sp_attivo(resto) == 'gross_sp02' or _fondo_is_immat(resto)
        return 'ce09a' if immat else 'ce09b'
    for keywords, field in _CE_COSTI_RULES:
        if _kw_match(desc_upper, keywords):
            return _rimanenze_per_natura(field, desc_upper)
    # "AMM.IMPIANTI E MACCHINARI", "AMMORTAMENTO SOFTWARE", "AMMTO TELEFONIA" (Santini): la
    # quota di un cespite nominato. Immateriale se il cespite lo e', altrimenti materiale
    # (ce09a/ce09b stanno entrambi dentro ce09, l'errore resta dentro l'aggregato).
    m = _CE_AMMORTAMENTO_RE.match(desc_upper)
    if m and desc_upper[m.end():].strip():
        resto = desc_upper[m.end():]
        cespite = _classify_sp_attivo(resto)
        # i segni d'immateriale dei fondi: manutenzioni da ammortizzare, spese
        # pluriennali, disaggi (budget_435)
        immat = cespite == 'gross_sp02' or _fondo_is_immat(resto)
        return 'ce09a' if immat else 'ce09b'
    return None

# da importers/situazione_contabile_parser.py:_classify_ce_costi_foglia, branch fase4 b224c95
def _classify_ce_costi_foglia(desc_upper: str) -> Optional[str]:
    """Ultima risorsa per un conto di costo che nessuna regola ne' il suo mastro
    riconoscono: la parola del conto foglia, prima del ripiego."""
    for keywords, field in _CE_COSTI_FOGLIE:
        if _kw_match(desc_upper, keywords):
            return field
    return None

# da importers/situazione_contabile_parser.py:_classify_ce_ricavi_foglia, branch fase4 b224c95
def _classify_ce_ricavi_foglia(desc_upper: str) -> Optional[str]:
    """Conti foglia di ricavo senza la parola RICAVI ("CORRISPETTIVI DA TRASPORTO DI
    MERCI SU STRADA", budget_435): il fatturato, non altri ricavi."""
    if _kw_any(desc_upper, ['CORRISPETTIV', 'PRESTAZIONI DI SERVIZ', 'FATTURATO']):
        return 'ce01'
    return None

# da importers/situazione_contabile_parser.py:_CE_COSTI_SINONIMI, branch fase4 b224c95
_CE_COSTI_SINONIMI = [
    (['LAVORO NON'], 'ce06'),          # "PRESTAZIONI DI LAVORO NON (DIPENDENTE)" troncato
    (['OPERA', 'TERZI'], 'ce06'),      # manodopera di terzi/esterna: un servizio B.7
    (['OPERA', 'ESTERN'], 'ce06'),
    (["MANO D'OPERA"], 'ce08'),        # manodopera: personale B.9
    (['MANO D OPERA'], 'ce08'),
    (['MANODOPERA'], 'ce08'),
    (['COSTI', 'FABBRICA'], 'ce06'),   # come COSTI INDUSTRIALI
    (['PROMOZIONAL'], 'ce06'),         # spese promozionali / pubblicita': B.7
    (['PUBBLICIT'], 'ce06'),
    (['ELABORAZ', 'DATI'], 'ce06'),    # CED / centro elettronico: servizio B.7
    (['CENTRO', 'ELETTRONIC'], 'ce06'),
    (['PERDITE', 'VARIE'], 'ce12'),    # oneri diversi di gestione B.14
    (['ALTRI ONERI'], 'ce12'),         # idem (i finanziari li prende prima ONERI+FINANZ)
]

# da importers/situazione_contabile_parser.py:_CE_RICAVI_SINONIMI, branch fase4 b224c95
_CE_RICAVI_SINONIMI = [
    (['VENDITE'], 'ce01'),             # mastro "VENDITE" (Italia/estero): fatturato A.1
    (['PROFITTI', 'VARI'], 'ce04'),    # altri ricavi e proventi A.5
    (['PROFITTI', 'DIVERS'], 'ce04'),
]

# da importers/situazione_contabile_parser.py:_classify_ce_sinonimo, branch fase4 b224c95
def _classify_ce_sinonimo(desc_upper: str, direction: str) -> Optional[str]:
    """Ultima risorsa prima del secchio generico: il sinonimo di natura del mastro."""
    rules = _CE_COSTI_SINONIMI if direction == 'costi' else _CE_RICAVI_SINONIMI
    for keywords, field in rules:
        if _kw_match(desc_upper, keywords):
            return field
    return None

# da importers/situazione_contabile_parser.py:_classify_ce_ricavi, branch fase4 b224c95
def _classify_ce_ricavi(desc_upper: str) -> Optional[str]:
    """Classify a CE ricavi entry by description keywords."""
    for keywords, field in _CE_RICAVI_RULES:
        if _kw_match(desc_upper, keywords):
            return _rimanenze_per_natura(field, desc_upper)
    return None

# da importers/situazione_contabile_parser.py:_FONDO_IMMAT_KW, branch fase4 b224c95
_FONDO_IMMAT_KW = (
    'IMMAT', '. IMM', 'PLURIENN', 'SOFTWARE', 'BREVETT', 'MARCHI', 'MARCHIO',
    'AVVIAMENT', 'LICENZ', 'CONCESSION', 'RICERCA', 'SVILUPPO', 'PUBBLICIT',
    'WEB', 'PROGETTAZ', 'CONSULENZ', 'DIRITTI', 'INGEGNO', 'KNOW', 'MANUT',
    'AMPLIAMENT', "COSTI D'IMPIANTO", 'COSTI DI IMPIANTO',
    'AMPL.', 'COSTI IMP', 'COSTITUZ',  # "Fondi ammort.costi imp.e ampl.", "spese di costituzione"
    'DISAGG',                       # disaggi su prestiti (budget_435)
)

# da importers/situazione_contabile_parser.py:_fondo_is_immat, branch fase4 b224c95
def _fondo_is_immat(desc_upper: str) -> bool:
    """immateriali (True) vs materiali (False) split for a row already known to be
    a fondo (ammortamento or svalutazione immobilizzazioni). Any intangible
    asset-type marker → immateriali; the tangible captions (impianti/macchinari/
    attrezzature/auto/fabbricati/mobili…) carry none, so they fall to materiali by
    default — mirroring the historical 'F.DO AMM' fallback while no longer
    depending on the 'F.DO' spelling."""
    return any(k in desc_upper for k in _FONDO_IMMAT_KW)


# da importers/situazione_contabile_parser.py:build_iv_cee (catena CE di route C), branch fase4 b224c95
def catena_ce(desc_upper: str, direzione: str) -> Optional[str]:
    """La catena a parole chiave che route C applica a un mastro di CE: regole di mastro, albero di legge, conto foglia,
    sinonimo di natura. `direzione` e' 'costi' o 'ricavi'."""
    if direzione == "costi":
        return (_classify_ce_costi(desc_upper) or _resolve_ce_field(desc_upper, "costi")
                or _classify_ce_costi_foglia(desc_upper) or _classify_ce_sinonimo(desc_upper, "costi"))
    return (_classify_ce_ricavi(desc_upper) or _resolve_ce_field(desc_upper, "ricavi")
            or _classify_ce_ricavi_foglia(desc_upper) or _classify_ce_sinonimo(desc_upper, "ricavi"))
