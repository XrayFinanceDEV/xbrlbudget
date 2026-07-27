"""Motore semantico delle etichette di bilancio — forma canonica e parsing.

Perche' esiste (misurato sul corpus, 72 documenti):

    spazio     righe   irrisolte
    marker       311      100,0%   <- nessun totale di controllo veniva riconosciuto
    account    5.914       63,0%
    legal         69       42,0%

Le voci civilistiche hanno UN significato e N grafie per gestionale
(`I. immateriali`, `I - Immobilizzazioni immateriali`, `B.I IMMOBILIZZAZIONI
IMMATERIALI`). L'LLM che legge il documento intero i sinonimi li capisce; a
rompersi sono i GATE DETERMINISTICI attorno ad esso — ancoraggi di sezione,
totali dichiarati, netting dei fondi, reclassificatore contrapposte — che
decidono se accettarne il risultato. Quando uno non riconosce la grafia,
un'estrazione corretta viene RIFIUTATA.

Questo modulo e' la forma canonica UNICA del sistema. Prima ne convivevano sei,
incompatibili fra loro (`iv_cee_hierarchy.normalize`,
`standard_ivcee_parser._normalise`, `_normalize_for_search`, l'inline di
`_declared_control_totals`, `bilancio_classifier.has`, e il solo `.upper()` di
`situazione_contabile_parser`) — con difetti reali: `bilancio_classifier` cerca
"passivita" e "disponibilita liquide" con una funzione che non deaccenta, quindi
su testo accentato non matcha MAI e il file finisce in ROUTE_UNSUPPORTED.

Regole di progetto:
  * la normalizzazione NON inventa parole: `I. immateriali` -> `immateriali`.
    L'espansione a `immobilizzazioni immateriali` e' compito del dizionario.
  * il path civilistico (`B.II.1.a`) non e' rumore: viene ESTRATTO in `path_hint`,
    non buttato via — serve a disambiguare e a validare la gerarchia.
  * idempotente: `normalize_label(normalize_label(x)) == normalize_label(x)`.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

__all__ = ["normalize_label", "parse_label", "ParsedLabel"]

# --- numerazione di voce ---------------------------------------------------------
# Un romano/lettera/arabo e' una NUMERAZIONE solo se seguito da un separatore
# (. ) - –) oppure se e' un path puntato. Senza questo vincolo si mangerebbero
# parole legittime: "IVA su acquisti", "Immobili civili", "Vari".
# Il lookahead impedisce al romano di matchare la stringa VUOTA (X{0,2} e V?I{0,3}
# sono entrambi opzionali): senza, `_ROMAN + \s+` mangerebbe qualunque spazio.
_ROMAN = r"(?=[IVXivx])(?:X{0,2}(?:IX|IV|V?I{0,3}))"
_ORD_SUFFIX = r"(?:\s*(?:bis|ter|quater|quinquies|sexies))?"

_PATH_RE = re.compile(
    rf"^\s*(?P<path>"
    rf"[A-E]"                                    # lettera di sezione
    rf"(?:\s*[.\-]\s*(?:{_ROMAN}|\d{{1,2}}){_ORD_SUFFIX})*"   # .II .1 .1 bis
    rf"(?:\s*[.\-]\s*[0-9a-z]+)*"                # .a .1
    rf")\s*[.)\-–]\s*",
    re.IGNORECASE,
)
_LEADING_ENUM_RE = re.compile(
    rf"^\s*(?:"
    rf"[A-E]\s*[.)\-–]\s*"                       # A)  B.  C -
    rf"|{_ROMAN}{_ORD_SUFFIX}\s*[.)\-–]\s*"      # I.  II)  V -
    # romano seguito da SOLO spazio: 'A.VIII Utili portati a nuovo' (grafia reale,
    # gia' gestita da _PN_DETAIL_SPECS). Sicuro grazie a \b: 'IVA', 'Immobili',
    # 'Vari' non sono token romani isolati e non vengono toccati.
    rf"|{_ROMAN}{_ORD_SUFFIX}\b\s+"
    rf"|\d{{1,2}}{_ORD_SUFFIX}\s*[.)\-–]\s*"     # 1)  5.  7 bis)
    rf")+",
    re.IGNORECASE,
)

# --- abbreviazioni ---------------------------------------------------------------
# L'ordine conta: 'f.do'/'fdo' prima di 'f/', 'amm.to' prima di 'amm'.
_ABBREV = [
    (r"\bf\s*\.?\s*d[oi]\b", "fondo"),
    (r"\bf\s*/\s*d[oi]\b", "fondo"),
    (r"\bfond[oi]\b", "fondo"),
    # amm.to / ammo.to / ammor.to / ammorto — la 'o' NON e' obbligatoria
    (r"\bamm(?:or?)?\s*\.?\s*t[oi]\b", "ammortamento"),
    (r"\bamm\s*\.?\s*nt[oi]\b", "ammortamento"),
    (r"\bamm\b\.?", "ammortamento"),
    (r"\bf\s*/\s*amm\w*", "fondo ammortamento"),
    (r"\bimmobilizz?\b\.?", "immobilizzazioni"),
    (r"\bimmob\b\.?", "immobilizzazioni"),
    (r"\bsval\w*\b\.?", "svalutazione"),
    (r"\bacc\s*\.?\s*t[oi]\b", "accantonamento"),
    (r"\bv\s*/\s*", "verso "),
    (r"\bc\s*/\s*", "conto "),
    (r"\btot\b\.?", "totale"),
]
_ABBREV = [(re.compile(p, re.IGNORECASE), r) for p, r in _ABBREV]

_TOTAL_RE = re.compile(r"^\s*totale\b", re.IGNORECASE)


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


_DOTTED_ACRONYM_RE = re.compile(r"\b(?:[a-z]\.){2,}", re.IGNORECASE)


def _fuse_dotted_acronyms(s: str) -> str:
    """`I.V.A.` -> `IVA`, `S.R.L.` -> `SRL`.

    Va fatto PRIMA di togliere la numerazione di voce, altrimenti `I.V.A. a debito`
    viene letto come tre numerazioni consecutive (`I.` `V.` `A.`) e resta solo
    "a debito" — una falsa amputazione osservata su etichette reali.
    Non tocca i path civilistici: `B.II.1.a` non e' una sequenza di lettere SINGOLE
    puntate (`II` sono due lettere), quindi non matcha.
    """
    return _DOTTED_ACRONYM_RE.sub(lambda m: m.group(0).replace(".", ""), s)


def _collapse_letter_spacing(s: str) -> str:
    """`A T T I V I T A` -> `attivita`.

    Sei documenti del corpus stampano le intestazioni con una spaziatura
    lettera-per-lettera (`TOTALE A T T I V I T A'`); senza questo passaggio
    nessun marker di sezione o di totale viene mai riconosciuto su quei file.
    Si fondono solo sequenze di >= 3 lettere singole, per non toccare sigle
    legittime come `A B` o le lettere di sezione.
    """
    def _fuse(match: re.Match) -> str:
        return match.group(0).replace(" ", "")

    return re.sub(r"(?:(?<=\s)|^)(?:[a-z]\s){2,}[a-z](?=\s|$)", _fuse, s)


def normalize_label(desc: Optional[str]) -> str:
    """Forma canonica di un'etichetta: minuscolo, senza accenti, senza numerazione
    di voce iniziale, senza spaziatura lettera-per-lettera, abbreviazioni espanse,
    punteggiatura a spazio, spazi collassati.

    NON espande i significati: `I. immateriali` -> `immateriali` (l'associazione a
    `sp02_immob_immateriali` la fa il dizionario, non la normalizzazione).
    """
    if not desc:
        return ""
    s = _strip_accents(str(desc)).lower().strip()
    # apostrofi/accenti tipografici finali (attivita' / attivita`) via subito
    s = re.sub(r"[`'‘’]", " ", s)
    s = _fuse_dotted_acronyms(s)
    s = _collapse_letter_spacing(s)
    s = _LEADING_ENUM_RE.sub("", s)
    for pattern, repl in _ABBREV:
        s = pattern.sub(repl, s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass(frozen=True)
class ParsedLabel:
    """Etichetta scomposta nelle sue tre informazioni utili."""
    canonical: str
    path_hint: Optional[str]
    is_total: bool


def _extract_path(s: str) -> tuple[Optional[str], str]:
    """Separa il path civilistico in testa (`C.II.5 quater)`) dal resto."""
    m = _PATH_RE.match(s)
    if not m:
        return None, s
    raw = m.group("path")
    if not re.search(r"[.\-]", raw):
        return None, s          # una sola lettera: e' una sezione, non un path
    path = re.sub(r"\s*[.\-]\s*", ".", raw.strip())
    path = re.sub(r"\.(bis|ter|quater|quinquies|sexies)", r"-\1", path, flags=re.I)
    path = re.sub(r"\s+(bis|ter|quater|quinquies|sexies)", r"-\1", path, flags=re.I)
    # Case canonica per livello: lettera di sezione e romani MAIUSCOLI, lettere di
    # dettaglio (a/b/c dell'art. 2424) minuscole. Un `.upper()` cieco trasformerebbe
    # B.II.1.a.1 in B.II.1.A.1, perdendo la distinzione fra i livelli.
    def _seg(i_and_s):
        i, seg = i_and_s
        if seg.isdigit() or re.fullmatch(r"(?:bis|ter|quater|quinquies|sexies)", seg, re.I):
            return seg.lower() if seg.isalpha() else seg
        if i == 0 or re.fullmatch(r"[ivx]+", seg, re.I):
            return seg.upper()
        return seg.lower()

    parts = []
    for i, seg in enumerate(path.split(".")):
        head, sep, tail = seg.partition("-")
        parts.append(_seg((i, head)) + sep + tail.lower())
    return ".".join(parts), s[m.end():]


def parse_label(desc: Optional[str]) -> ParsedLabel:
    """Scompone un'etichetta in forma canonica + path civilistico + flag di totale.

    Il `path_hint` NON viene buttato via con la numerazione: `B.II.1.a` dice sotto
    quale voce deve cadere la riga ed e' quindi un vincolo di disambiguazione e di
    validazione della gerarchia.
    """
    if not desc:
        return ParsedLabel("", None, False)
    raw = _strip_accents(str(desc)).strip()
    raw = re.sub(r"[`'‘’]", " ", raw)
    raw = _fuse_dotted_acronyms(raw)
    raw = _collapse_letter_spacing(raw)
    path, rest = _extract_path(raw)
    canonical = normalize_label(rest if path else raw)
    return ParsedLabel(canonical, path, bool(_TOTAL_RE.match(canonical)))
