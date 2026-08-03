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

__all__ = ["normalize_label", "parse_label", "ParsedLabel",
           "classify_label", "LabelHit", "ROLES", "MARKERS"]

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


# Elisioni: l'apostrofo di `d'esercizio` NON e' punteggiatura da buttare, e'
# una contrazione. Sostituirlo con uno spazio lascia una 'd' orfana
# (`utile d esercizio`) che non corrisponde a nessuna grafia reale. Va espansa.
_ELISION = [
    (re.compile(r"\bdell\s*['’‘`]\s*(?=[a-z])", re.I), "dell "),
    (re.compile(r"\bnell\s*['’‘`]\s*(?=[a-z])", re.I), "nell "),
    (re.compile(r"\ball\s*['’‘`]\s*(?=[a-z])", re.I), "all "),
    (re.compile(r"\bsull\s*['’‘`]\s*(?=[a-z])", re.I), "sull "),
    (re.compile(r"\bun\s*['’‘`]\s*(?=[a-z])", re.I), "una "),
    (re.compile(r"\bd\s*['’‘`]\s*(?=[a-z])", re.I), "di "),
    (re.compile(r"\bl\s*['’‘`]\s*(?=[a-z])", re.I), "la "),
]


def _expand_elisions(s: str) -> str:
    for pattern, repl in _ELISION:
        s = pattern.sub(repl, s)
    return s


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
    s = _expand_elisions(s)
    # apostrofi/accenti tipografici FINALI (attivita' / attivita`): ora che le
    # elisioni sono espanse, quelli rimasti sono solo decorativi
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
    raw = _expand_elisions(raw)
    raw = re.sub(r"[`'‘’]", " ", raw)
    raw = _fuse_dotted_acronyms(raw)
    raw = _collapse_letter_spacing(raw)
    path, rest = _extract_path(raw)
    canonical = normalize_label(rest if path else raw)
    return ParsedLabel(canonical, path, bool(_TOTAL_RE.match(canonical)))


# =================================================================================
# Tre spazi di target
# =================================================================================
#
#   voce    -> db_field, SOLO livello legale (albero IV-CEE esistente)
#   marker  -> "__tot_attivo" / "__pareggio" / "__risultato" / ... : non hanno
#              db_field, e sono cio' che pilota preflight, netting e selezione
#              candidati. Il vecchio resolver non li aveva affatto: 100% irrisolti.
#   conto   -> db_field + RUOLO contabile. Solo route C: un conto risolto anche
#              nello spazio 'voce' verrebbe contato due volte in aggregazione flat.

import json
import os

ROLES = ("contra_immat", "contra_mat", "contra_crediti", "fondo_rischi",
         "risultato", "totale")

MARKERS = ("__tot_attivo", "__tot_passivo", "__pareggio", "__utile", "__perdita",
           "__risultato", "__sez_sp_attivo", "__sez_sp_passivo", "__sez_ce",
           "__col_scostamento")

_DICT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "label_dictionary.json")

# Soglia sotto la quale si preferisce NON classificare. Un irrisolto e' misurabile
# (lascia residuo, i gate lo vedono); una classificazione sbagliata no.
_MIN_SCORE = 0.55


@dataclass(frozen=True)
class LabelHit:
    """Esito della classificazione, con abbastanza contesto da poterlo giudicare."""
    target: str
    role: Optional[str] = None
    level: Optional[str] = None
    specificity: float = 1.0
    confidence: str = "alta"
    source: str = "dizionario"
    reason: str = ""


_DICT_CACHE = None


def _dictionary() -> dict:
    global _DICT_CACHE
    if _DICT_CACHE is None:
        try:
            with open(_DICT_PATH, encoding="utf-8") as fh:
                raw = json.load(fh)
        except Exception:
            raw = {}
        # le chiavi sono gia' in forma canonica, ma ri-normalizzarle rende il file
        # tollerante a una svista di battitura
        markers = {normalize_label(k): v for k, v in (raw.get("marker") or {}).items()}
        conti = {}
        for k, v in (raw.get("conto") or {}).items():
            entry = v if isinstance(v, dict) else {"target": v}
            conti[normalize_label(k)] = entry
        _DICT_CACHE = {"marker": markers, "conto": conti}
    return _DICT_CACHE


def _tokens(s: str) -> list:
    return [t for t in s.split() if t]


def _score(label_norm: str, key: str) -> float:
    """Quanta parte dell'etichetta e' spiegata dalla chiave di dizionario.

    E' il termine che salva dalle corrispondenze FALSE, il difetto simmetrico del
    mancato riconoscimento: `cassa` spiega 1 token su 2 di `cassa previdenziale`,
    quindi perde contro una chiave previdenziale e, senza alternative, scende
    sotto soglia -> None (esito onesto, che lascia residuo e che i gate vedono).
    Tokenizzare da solo non basterebbe: `cassa` e `titoli` SONO token interi.
    """
    lt, kt = _tokens(label_norm), _tokens(key)
    if not lt or not kt:
        return 0.0
    if label_norm == key:
        return 1.0
    if not set(kt).issubset(set(lt)):
        return 0.0                      # la chiave non e' contenuta: non e' un match
    coverage = len(kt) / len(lt)        # quanta parte dell'etichetta spiega
    prefix = 0.15 if lt[:len(kt)] == kt else 0.0
    return min(0.99, coverage + prefix)


def _best_dict_hit(label_norm: str, table: dict):
    """Chiave di dizionario col punteggio piu' alto, se supera la soglia."""
    best_key, best_score = None, 0.0
    for key in table:
        sc = _score(label_norm, key)
        if sc > best_score:
            best_key, best_score = key, sc
    if best_key is None or best_score < _MIN_SCORE:
        return None, best_score
    return best_key, best_score


def _classify_marker(parsed):
    table = _dictionary()["marker"]
    lab = parsed.canonical
    # I marker si matchano per UGUAGLIANZA. Un marker riconosciuto per substring
    # produce il bug budget_176: la voce di legge «Differenza tra valore e costi di
    # produzione» scambiata per l'intestazione di colonna «Differenza», con il
    # cutoff a x>=115 e l'intera pagina cancellata. Stessa ragione per cui
    # «Totale attivo circolante» non e' «Totale attivo».
    target = table.get(lab)
    if target is None:
        return None
    return LabelHit(target=target, specificity=1.0, confidence="alta",
                    source="dizionario", reason="marker esatto: " + repr(lab))


def _classify_voce(parsed, side, statement):
    from importers.iv_cee_hierarchy import resolve      # import differito: no cicli
    node = resolve(parsed.canonical, side=side) if side else resolve(parsed.canonical)
    if node is None and side:
        node = resolve(parsed.canonical)
    # Lo spazio `voce` restituisce SOLO foglie legali dell'art. 2424/2425. I nodi
    # di netting (FONDO.AMM) descrivono una rettifica, non una riga di bilancio:
    # farli passare di qui significherebbe che un conto del piano dei conti
    # ("F.do amm.to automezzi") risolve anche come voce, e in aggregazione flat
    # A/B verrebbe contato due volte. Il ruolo contra vive nello spazio `conto`.
    if node is not None and getattr(node, "netting", False):
        node = None
    if node is not None and getattr(node, "db_field", None):
        return LabelHit(
            target=node.db_field,
            level=str(getattr(node, "level", "") or "") or None,
            specificity=1.0, confidence="alta", source="dizionario",
            reason="albero IV-CEE: " + str(getattr(node, "path", "?")))
    return None


_IMMAT_KW = ("immateriale", "immateriali", "impianto", "ampliamento", "sviluppo",
             "avviamento", "software", "licenz", "brevett", "marchi", "concession",
             "pluriennal", "disaggi", "manutenzioni e riparazioni")


def _split_fondo_ammortamento(label_norm: str, target: str, role: str):
    """Un fondo ammortamento netta l'immateriale o il materiale secondo il CESPITE.

    Sbagliarlo non altera il totale ma sposta massa fra sp02 e sp03 — invisibile a
    ogni gate di quadratura (e' il bug budget_395, gia' documentato nel repo).
    """
    if any(kw in label_norm for kw in _IMMAT_KW):
        return "sp02_immob_immateriali", "contra_immat"
    return "sp03_immob_materiali", "contra_mat"


def _classify_conto(parsed, side):
    if parsed.is_total:
        return LabelHit(target="__totale", role="totale", specificity=1.0,
                        confidence="alta", source="dizionario",
                        reason="riga di totale/subtotale: non va sommata")
    table = _dictionary()["conto"]
    key, score = _best_dict_hit(parsed.canonical, table)
    if key is None:
        return None
    entry = table[key]
    # Conti AMBIGUI (erario c/IVA, banche c/c, depositi bancari): la natura la
    # decide la COLONNA in cui il documento li stampa, mai la descrizione. E' una
    # regola gia' consolidata nel repo (dedurre il lato dalla descrizione fu
    # provato e ritirato: regrediva file puliti).
    if "attivo" in entry or "passivo" in entry:
        side_entry = entry.get(side or "")
        if side_entry is None:
            return None                 # ambiguo e senza lato: non si indovina
        entry = side_entry
    role = entry.get("role")
    target = entry["target"]
    if role in ("contra_mat", "contra_immat"):
        target, role = _split_fondo_ammortamento(parsed.canonical, target, role)
    return LabelHit(target=target, role=role, specificity=round(score, 3),
                    confidence="alta" if score >= 0.99 else "media",
                    source="dizionario",
                    reason="conto: chiave " + repr(key) + " (specificita' %.2f)" % score)


def classify_label(label, space="voce", side=None, statement=None,
                   path_hint=None, parent=None, use_llm=False):
    """Classifica un'etichetta in uno dei tre spazi. `None` = non riconosciuta.

    `use_llm` e' il gancio per l'arbitro Haiku (Piano 05B): oggi no-op, cosi'
    l'attivazione futura non richiede di toccare i chiamanti.
    """
    if not label:
        return None
    parsed = parse_label(label)
    if path_hint and not parsed.path_hint:
        parsed = ParsedLabel(parsed.canonical, path_hint, parsed.is_total)
    if not parsed.canonical:
        return None

    if space == "marker":
        return _classify_marker(parsed)
    if space == "voce":
        return _classify_voce(parsed, side, statement)
    if space == "conto":
        return _classify_conto(parsed, side)
    raise ValueError("spazio semantico sconosciuto: " + repr(space))
