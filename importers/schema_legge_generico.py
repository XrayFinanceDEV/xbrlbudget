"""Schema di legge (art. 2424/2425) stampato da un gestionale qualunque, letto a regole.

Il PDF reso da XBRL (``xbrl_reso_parser``) ha un layout solo; i bilanci CEE dei gestionali ne
hanno decine: romani scritti "I)", "I.", "I" o "I -", importi coi centesimi o interi, il segno
meno in coda, il simbolo dell'euro staccato, colonne "Differenza" e "Scostamento %" accanto ai
due esercizi, i conti stampati sotto la voce. Questo lettore porta ogni variante alla stessa
forma e consegna le righe al cuore del lettore XBRL (``estrai_da_righe``): stesso albero, stessa
traduzione percorso -> campo, stessi controlli al centesimo. Si adotta solo se OGNI totale
stampato torna; una variante non capita non produce un numero sbagliato, produce un rifiuto.

Regole, tutte generali (nessuna e' scritta per un file):
- una riga e' cio' che sta alla stessa altezza; gli importi sono i token in coda alla riga che
  cadono in una colonna di importi (bordo destro allineato su molte righe del documento);
- le colonne-esercizio sono le colonne di importi da sinistra che non sono una differenza
  (valore = prima - seconda su tutte le righe) ne' una percentuale (tre decimali); due colonne
  che non sono mai piene sulla stessa riga sono un esercizio solo (parziali e totali);
- intestazioni e piedi di pagina (righe ripetute nei margini o sopra il prospetto, "Pagina N di
  M") non sono righe;
- gli enumeratori si portano alla forma "A)", "I - ", "1)", "a)"; i subtotali calcolati
  ("A-B TOTALE DIFF. TRA VALORE E COSTI") alla didascalia di legge;
- le righe che cominciano con un codice conto non sono voci di legge, e le righe senza
  enumeratore sotto una riga con importo che la riproducono sono il dettaglio dei conti: la
  riga le ha gia' contate;
- una voce che stampa il proprio totale sulla riga del titolo, seguita dalle sotto-voci, e'
  un'intestazione con il suo totale: il totale si verifica sulle sotto-voci come ogni altro;
- una riga senza enumeratore eredita la voce del padre, se il padre ne ha una.
"""
from __future__ import annotations

import itertools
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Optional

import fitz

from importers import xbrl_reso_parser as reso

_ZERO = Decimal("0")

_IMPORTO = re.compile(r"^\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,3})?-?\)?$")
_EURO = {"€", "�", "eur", "euro"}
# L'anno di una colonna: "2025", "31/12/2025" o "31/12/25".
_DATA = re.compile(r"^(?:\d{2}[-/.]\d{2}[-/.])?(20\d{2})$|^\d{2}[-/.]\d{2}[-/.](\d{2})$")
# Una cella numerica troppo stretta per il suo valore: il gestionale stampa asterischi.
_TRABOCCATO = re.compile(r"^\*+$")
_CODICE_CONTO = re.compile(r"^\d{2,3}(?:[./-]\d{1,4}){1,4}$|^\d{5,}$")

# Due token sono nella stessa colonna se i loro bordi destri distano al piu' cosi' (punti).
_TOL_COLONNA = 14.0
# Una colonna di importi e' tale se il documento ne porta almeno tanti allineati.
_MIN_IMPORTI_COLONNA = 4
_TOL_RIGA = 3.0
# Fascia in testa e in fondo alla pagina (intestazione e piede ripetuti).
_FASCIA_MARGINE = 0.09
# Una riga senza importi piu' vicina di cosi' (frazione dell'interlinea della pagina) alla riga
# sopra e' la didascalia di quella andata a capo.
_A_CAPO = 0.7

_RE_ROMANO = re.compile(r"^(VIII|VII|VI|IV|IX|III|II|V|X|I)(?:\s*[\)\.\-–:]\s*|\s+(?=[A-Za-z]))(.*)$")
_RE_CAPITALE = re.compile(r"^([A-E])\s*[\)\.]\s*(.*)$")
# "15) Proventi", "15. Proventi" e anche "15)Proventi" (la parentesi attaccata al testo): il punto
# vuole lo spazio dopo, per non leggere "1.234" come un enumeratore.
_RE_ARABO = re.compile(r"^(\d{1,2})\s*-?\s*(bis|ter|quater|quinquies)?\s*(?:[\)\.]\s+|\)(?=[A-Za-z]))(.*)$",
                       re.I)
_RE_LETTERA = re.compile(r"^([a-z])\s*-?\s*((?i:bis|ter))?(\d)?\s*\)\s*(.*)$")
# Un totale con davanti il codice della voce ("II TOTALE ...", "d-bis TOTALE ...", "d5 TOTALE",
# "C) TOTALE") o la formula che lo calcola ("A-B TOTALE DIFF. ...", "15+16-17+-17b TOTALE ...").
_RE_TOTALE_CON_CODICE = re.compile(
    r"^(?:[A-Z]|[IVX]+|\d{1,2}(?:-?(?:bis|ter|quater))?|[a-z]\d?(?:-?bis)?"
    r"|[A-E\d][A-E\d+\-±/b ]*[+\-±][A-E\d+\-±/b ]*)\)?\s+(totale\b.*)$", re.I)
# La formula dello schema (art. 2425) del risultato prima delle imposte: "A-B±C±D" (dal D.Lgs.
# 139/2015) o "A-B±C±D±E" (schema precedente, con i proventi straordinari). Qualunque titolo le
# stampi accanto il gestionale ("TOTALE CONTO ECONOMICO"), il subtotale e' quello.
_RE_FORMULA_PRIMA_IMPOSTE = re.compile(r"^a-b[+\-±]+c[+\-±]+d(?:[+\-±]+e)?\)?$")
# Il codice voce di un gestionale stampato in testa alla riga ("AB010000 I) IMMOBILIZZAZIONI",
# "A 000000 A) STATO PATRIMONIALE", "PA090000a a) Utile"): da una a tre lettere e almeno quattro
# cifre, seguito da un enumeratore di legge. Il codice non e' la voce: la voce e' cio' che segue.
_RE_CODICE_VOCE = re.compile(r"^[A-Z]{1,3}\s?\d{4,}[a-z]{0,2}\d?\s+(?=[^\s)]{1,14}\)\s)")
_SCADENZA = re.compile(r"^(?:crediti\s+|debiti\s+|importi\s+)?(?:esigibil[ie]\s+)?(entro|oltre)\b", re.I)
_SCADENZA_IN_CODA = re.compile(r"\besigibil[ie]\s+(entro|oltre)\b", re.I)
# Subtotali calcolati, comunque abbreviati: alla didascalia che il cuore del lettore riconosce.
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
# Il totale di ogni sezione del conto economico, col nome che i controlli A - B, + C + D leggono.
_TOTALI_SEZIONE_CE = {
    "A": "Totale valore della produzione", "B": "Totale costi della produzione",
    "C": "Totale proventi e oneri finanziari",
    "D": "Totale delle rettifiche di valore di attivita' e passivita' finanziarie",
}
# Piedi e intestazioni di pagina riconoscibili dal testo: "Pagina 3 di 8", "Pag. 10 di",
# "Stampata il ... Pagina 1 di", "Utente: administrator".
_PIEDE = re.compile(r"\bpag(?:ina|\.)?\s*\d*\s*(?:di\s*\d*)?\s*$|^pagina\b|\butente\s*:")
_RADICI = ("Stato patrimoniale", "Attivo", "Passivo", "Conto economico")


def _norm(testo: str) -> str:
    testo = "".join(c for c in unicodedata.normalize("NFKD", testo) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", testo).strip().casefold()


def _importo(token: str) -> Optional[Decimal]:
    t = token.strip()
    if t == "-":
        return Decimal(0)       # la cella vuota dei prospetti Infocamere ("Imposte anticipate 59 -")
    if not _IMPORTO.match(t):
        return None
    negativo = t.startswith(("(", "-")) or t.endswith("-")
    t = t.strip("()").strip("-").replace(".", "").replace(",", ".")
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    return -v if negativo else v


def _anno(m: re.Match) -> int:
    return int(m.group(1)) if m.group(1) else 2000 + int(m.group(2))


def _ricompatta_spaziato(testo: str) -> str:
    """ "S T A T O P A T R I M O N I A L E" -> "STATOPATRIMONIALE"."""
    if re.fullmatch(r"(?:\S ){3,}\S", testo):
        return testo.replace(" ", "")
    return testo


def _pieni(valori: list[Optional[Decimal]], n_col: int) -> list[Decimal]:
    return ([v if v is not None else _ZERO for v in valori] + [_ZERO] * n_col)[:n_col]


# --------------------------------------------------------------------------------------
# Righe fisiche e colonne
# --------------------------------------------------------------------------------------

def _righe_pagina(pagina: fitz.Page) -> list[list[tuple]]:
    parole = sorted(pagina.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    gruppi: list[list] = []
    for w in parole:
        c = (w[1] + w[3]) / 2
        if gruppi and abs(c - gruppi[-1][0]) <= _TOL_RIGA:
            gruppi[-1][1].append(w)
        else:
            gruppi.append([c, [w]])
    return [sorted(g, key=lambda w: w[0]) for g in _riattacca_importi([g for _, g in gruppi])]


def _solo_importi(g: list[tuple]) -> bool:
    """Riga fatta solo di importi: mai un enumeratore ("1)" e' anche un importo per _importo)."""
    return _coda_importi(g) == 0 and not any(str(w[4]).strip().endswith(")") for w in g)


def _ha_importi(g: list[tuple]) -> bool:
    return _coda_importi(sorted(g, key=lambda w: w[0])) < len(g)


def _sovrapposizione(a: list[tuple], b: list[tuple]) -> float:
    """Quota dell'altezza di ``a`` coperta verticalmente da ``b``."""
    a0, a1 = min(w[1] for w in a), max(w[3] for w in a)
    b0, b1 = min(w[1] for w in b), max(w[3] for w in b)
    altezza = a1 - a0
    return max(0.0, min(a1, b1) - max(a0, b0)) / altezza if altezza > 0 else 0.0


def _riattacca_importi(gruppi: list[list[tuple]]) -> list[list[tuple]]:
    """Un importo stampato qualche punto sopra o sotto la propria didascalia (wkhtmltopdf,
    Napolitano CEE 2026: "Totale crediti verso imprese collegate" a 750,4 e il suo "0" a 757,0;
    "2) impianti e macchinario" e "-141") diventa una riga orfana: il lettore la prende per un
    totale senza didascalia e l'albero dello schema di legge si sfasa di un livello. Una riga
    di soli importi si riattacca alla riga vicina che non ne ha, quando i due riquadri si
    sovrappongono per almeno meta' dell'altezza dell'importo; altrimenti resta com'e'."""
    out = [list(g) for g in gruppi]
    i = 0
    while i < len(out):
        g = sorted(out[i], key=lambda w: w[0])
        if _solo_importi(g):
            vicine = [j for j in (i - 1, i + 1) if 0 <= j < len(out)
                      and not _ha_importi(out[j])]
            vicine = [j for j in vicine if _sovrapposizione(g, out[j]) >= 0.5]
            if vicine:
                j = max(vicine, key=lambda k: _sovrapposizione(g, out[k]))
                out[j].extend(g)
                del out[i]
                continue
        i += 1
    return out


def _coda_importi(riga: list[tuple]) -> int:
    """Indice del primo token della coda di importi (euro e celle traboccate compresi)."""
    k = len(riga)
    while k > 0:
        t = str(riga[k - 1][4]).strip()
        if t == "-" and k > 1 and re.fullmatch(r"\(\d+", str(riga[k - 2][4]).strip()):
            break       # "(18 -" a capo di "19)": il trattino di un intervallo, non una cella vuota
        if _importo(t) is not None or _norm(t) in _EURO or _TRABOCCATO.match(t):
            k -= 1
            continue
        break
    return k


def _bordi(righe: list[list[tuple]]) -> list[float]:
    return sorted(float(w[2]) for r in righe for w in r[_coda_importi(r):]
                  if _importo(str(w[4])) is not None and float(w[0]) > 150)


def _colonne_pagina(righe: list[list[tuple]]) -> list[float]:
    """I bordi destri delle colonne di importi, da sinistra."""
    gruppi: list[list[float]] = []
    for x in _bordi(righe):
        if gruppi and x - gruppi[-1][-1] <= _TOL_COLONNA:
            gruppi[-1].append(x)
        else:
            gruppi.append([x])
    return [max(g) for g in gruppi if len(g) >= _MIN_IMPORTI_COLONNA]


def _nel_margine(r: list[tuple], altezza: float) -> bool:
    y0, y1 = min(w[1] for w in r), max(w[3] for w in r)
    return y1 <= _FASCIA_MARGINE * altezza or y0 >= (1 - _FASCIA_MARGINE) * altezza


def _testate_ripetute(pagine: list[list[list[tuple]]], altezze: list[float]) -> list[set[int]]:
    """Per pagina, gli indici delle righe d'intestazione o di piede: righe che non sono del
    prospetto (ne' titolo di sezione ne' voce di legge), nella fascia di margine o prima della
    prima / dopo l'ultima voce di legge della pagina, e ripetute su un'altra pagina
    ("BILANCIO SCHEMA XBRL ALMA S.R.L.", "31 DICEMBRE 2025", "Codice fiscale 02780840993").
    Una riga senza importi si confronta a meno delle cifre ("Pag. 2" e "Pag. 3"); una che porta
    numeri deve ripetersi identica, numeri compresi: un'intestazione si ripete uguale, una riga
    del prospetto con i suoi importi no."""
    candidate: list[tuple[int, int, str]] = []
    pagine_per_chiave: dict[str, set[int]] = {}
    for numero, righe in enumerate(pagine):
        testi = [" ".join(str(w[4]) for w in r if _norm(str(w[4])) not in _EURO) for r in righe]
        voci = [_forma_strutturale(t) for t in testi]
        if not any(voci):
            continue
        prima, ultima = voci.index(True), len(voci) - 1 - voci[::-1].index(True)
        for k, (r, testo) in enumerate(zip(righe, testi)):
            if voci[k] or _intestazione(testo) or not testo.strip():
                continue
            if not (k < prima or k > ultima or _nel_margine(r, altezze[numero])):
                continue
            # il numero di pagina in coda ("Bilancio XBRL 2", "Bilancio XBRL 3") non e' un importo
            numeri = any(_importo(str(w[4])) is not None
                         and not re.fullmatch(r"\d{1,3}", str(w[4]).strip()) for w in r)
            chiave = ("=" + _norm(testo)) if numeri else ("#" + reso._chiave_ripetuta(testo))
            candidate.append((numero, k, chiave))
            pagine_per_chiave.setdefault(chiave, set()).add(numero)
    out: list[set[int]] = [set() for _ in pagine]
    for numero, k, chiave in candidate:
        if len(pagine_per_chiave[chiave]) >= 2:
            out[numero].add(k)
    return out


def _anni_intestazione(righe: list[list[tuple]], colonne: list[float]) -> dict[int, int]:
    """Colonna -> anno, dalle intestazioni ("2025", "31/12/2025", "Esercizio 2025") che stanno
    sopra una colonna di importi."""
    out: dict[int, int] = {}
    for r in righe:
        riga: dict[int, list[int]] = {}
        frase = False
        for w in r:
            m = _DATA.match(str(w[4]).strip())
            if not m or not colonne:
                continue
            centro = (float(w[0]) + float(w[2])) / 2
            i = min(range(len(colonne)), key=lambda i: abs(float(w[2]) - colonne[i]))
            if abs(float(w[2]) - colonne[i]) <= 70 or abs(centro - colonne[i]) <= 70:
                riga.setdefault(i, []).append(_anno(m))
            else:
                frase = True
        # una data lontana dalle colonne, o due date sopra la stessa colonna: e' una frase
        # ("periodo dal 01/01/2025 al 31/12/2025", "Bilancio al 31/12/2025 ..."), non
        # l'intestazione delle colonne
        if frase or any(len(v) > 1 for v in riga.values()):
            continue
        for i, v in riga.items():
            out.setdefault(i, v[0])
        if len(out) >= 2:
            break
    return out


# --------------------------------------------------------------------------------------
# Didascalie: dalla variante del gestionale alla forma del lettore di legge
# --------------------------------------------------------------------------------------

def _scadenza(testo: str) -> Optional[str]:
    m = _SCADENZA.match(testo)
    if not m:
        return None
    return "esigibili entro l'esercizio successivo" if m.group(1).lower() == "entro" \
        else "esigibili oltre l'esercizio successivo"


def _scadenza_in_coda(testo: str) -> Optional[str]:
    """ "Debiti verso banche esigibili oltre l'esercizio successivo" sotto la voce 4): la lettera
    e' la ripartizione per scadenza della voce, non una sotto-voce di legge."""
    m = _SCADENZA_IN_CODA.search(testo)
    if not m:
        return None
    return _scadenza(m.group(1) + " " + testo[m.end():])


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
    if reso._RE_GRUPPO.match(t):
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


_PAROLE_TESTATA = {"al", "anno", "esercizio", "esercizi", "bilancio", "periodo", "differenza",
                   "diff", "diff.", "scost", "scost.", "scostamento", "variazione", "var", "var.",
                   "%", "euro", "importi", "in", "valori", "corrente", "precedente", "consuntivo",
                   "importo", "descrizione", "comparato"}


def _e_testata_colonne(didascalia: str) -> bool:
    """Una riga d'intestazione delle colonne: solo parole di testata, date e anni."""
    parole = [p for p in _norm(didascalia).replace("/", " ").split() if p]
    return bool(parole) and all(p in _PAROLE_TESTATA or re.fullmatch(r"[\d\-./]+", p)
                                for p in parole)


def _intestazione(didascalia: str) -> list[str]:
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


def _e_conto(didascalia: str) -> bool:
    """Riga che comincia con un codice conto. "18-19 TOTALE RETT. ..." no: la formula del totale
    ha la forma di un codice, ma e' seguita da "totale"."""
    parole = didascalia.split()
    return bool(parole and _CODICE_CONTO.match(parole[0])
                and not (len(parole) > 1 and _norm(parole[1]) == "totale"))


# --------------------------------------------------------------------------------------
# Lettura
# --------------------------------------------------------------------------------------

def _e_differenza(valori: list[list[Optional[Decimal]]], k: int, a: int, b: int) -> bool:
    """La colonna k e' a - b (o il suo opposto) su ogni riga che le porta tutte e tre."""
    prove = [(r[a], r[b], r[k]) for r in valori if r[a] is not None and r[b] is not None
             and r[k] is not None and (r[a] != 0 or r[b] != 0)]
    if len(prove) < 3:
        return False
    return all(abs(x - y - z) <= Decimal("0.01") or abs(y - x - z) <= Decimal("0.01")
               or abs(abs(x - y) - abs(z)) <= Decimal("0.01") for x, y, z in prove)


def _leggi(documento: fitz.Document):
    """(righe, numero di colonne-esercizio, anni) oppure solleva ``reso._Rifiuto``."""
    return _righe_da_grezze(*_grezze_pdf(documento))


def _grezze_pdf(documento: fitz.Document):
    """La geometria della pagina -> righe grezze ``(pagina, didascalia, importi per colonna
    esercizio)``, numero di colonne-esercizio e ``{colonna: anno}``."""
    grezze: list[tuple[int, str, list[Optional[Decimal]]]] = []
    anni_doc: dict[int, int] = {}
    n_col = 0
    ripetute = reso._ripetute(documento)
    tutte = [_righe_pagina(p) for p in documento]
    altezze = [float(p.rect.height) for p in documento]
    testate = _testate_ripetute(tutte, altezze)
    pagine = [[r for k, r in enumerate(righe) if k not in testate[n]] for n, righe in enumerate(tutte)]
    # Le colonne del documento: un gestionale stampa ogni pagina sulla stessa griglia, e una
    # colonna che su una pagina porta pochi importi (una pagina corta, la colonna interna delle
    # sotto-voci) e' una colonna lo stesso se il documento intero ne porta abbastanza. Le righe
    # nella fascia d'intestazione e di piede non fanno colonne.
    corpo = [[r for r in righe if not _nel_margine(r, altezze[n])] for n, righe in enumerate(pagine)]
    colonne_doc = _colonne_pagina([r for righe in corpo for r in righe])
    voce_con_importo = False        # la voce aperta porta il suo importo (vedi ``_parziali``)
    for numero, righe in enumerate(pagine):
        colonne = _colonne_pagina(righe)
        bordi_pag = _bordi(corpo[numero])
        colonne = sorted(colonne + [
            c for c in colonne_doc
            if all(abs(c - x) > _TOL_COLONNA for x in colonne)
            and any(abs(c - x) <= _TOL_COLONNA for x in bordi_pag)])
        altezza = altezze[numero]
        centri = [(min(w[1] for w in r) + max(w[3] for w in r)) / 2 for r in righe]
        salti = sorted(b - a for a, b in zip(centri, centri[1:]) if b - a > 0.5)
        passo = salti[len(salti) // 2] if salti else 0.0
        # (didascalia, importi per colonna, colonne traboccate, centro verticale)
        lette: list[list] = []
        for r, centro in zip(righe, centri):
            k = _coda_importi(r)
            importi = [w for w in r[k:] if _importo(str(w[4])) is not None]
            # un importo e' tale solo se sta in una colonna; altrimenti torna nella didascalia
            per_col: list[Optional[Decimal]] = [None] * len(colonne)
            fuori = []
            # una cella traboccata ("********") sta in una colonna: se e' una colonna-esercizio
            # l'importo non e' leggibile e il documento si rifiuta; altrove (scostamento %) si ignora
            traboccate = set()
            for w in r[k:]:
                if _TRABOCCATO.match(str(w[4]).strip()) and colonne:
                    i = min(range(len(colonne)), key=lambda i: abs(float(w[2]) - colonne[i]))
                    if abs(float(w[2]) - colonne[i]) <= _TOL_COLONNA:
                        traboccate.add(i)
            for w in importi:
                if not colonne:
                    fuori.append(w)
                    continue
                i = min(range(len(colonne)), key=lambda i: abs(float(w[2]) - colonne[i]))
                if abs(float(w[2]) - colonne[i]) <= _TOL_COLONNA and per_col[i] is None:
                    per_col[i] = _importo(str(w[4]))
                else:
                    fuori.append(w)
            parole = sorted(r[:k] + fuori, key=lambda w: w[0])
            m_cod = _RE_CODICE_VOCE.match(" ".join(str(w[4]) for w in parole))
            if m_cod:
                # il codice voce del gestionale (una o due parole) non fa parte della didascalia
                parole = parole[len(m_cod.group(0).split()):]
            didascalia = " ".join(str(w[4]) for w in parole if _norm(str(w[4])) not in _EURO)
            intera = _norm(" ".join(str(w[4]) for w in r))
            if (re.search(r"\bpag(?:ina|\.)?\s*\d+\s*(?:di|/)\s*\d+\s*$", intera)
                    or re.search(r"\bpag(?:ina|\.)\s*\d+\s*$", intera)):
                continue        # "Pagina 4 di 8": il numero di pagine non e' un importo
            if (importi and all(_DATA.match(str(w[4]).strip()) for w in importi)
                    and (not _norm(didascalia) or _e_testata_colonne(didascalia))):
                continue        # "ANNO 2025 2024": intestazione di colonna, non importi
            con_importi = any(v is not None for v in per_col)
            if not con_importi:
                if _nel_margine(r, altezza) and not _intestazione(didascalia) \
                        and reso._chiave_ripetuta(didascalia) in ripetute:
                    continue
                if _PIEDE.search(_norm(didascalia)) or re.fullmatch(r"\d{1,3}", didascalia.strip()):
                    continue
                # una riga senza importi stretta sotto la precedente, piu' vicina dell'interlinea
                # della pagina, e' la didascalia di quella andata a capo ("A-B) TOTALE DIFFERENZA
                # TRA VALORI E COSTI" / "DELLA PRODUZIONE"), qualunque sia la maiuscola. Se la
                # riga sopra porta solo gli importi, centrati fra le due righe di una didascalia
                # spezzata ("C) TRATTAMENTO DI FINE RAPPORTO DI LAVORO" / importi /
                # "SUBORDINATO"), le tre righe sono una voce sola.
                if (lette and passo and centro - lette[-1][3] < _A_CAPO * passo
                        and not _forma_strutturale(didascalia) and not _intestazione(didascalia)):
                    sopra = lette[-1]
                    if (not sopra[0].strip() and len(lette) >= 2
                            and not any(v is not None for v in lette[-2][1])
                            and sopra[3] - lette[-2][3] < _A_CAPO * passo):
                        lette[-2] = [lette[-2][0] + " " + didascalia, sopra[1], sopra[2], sopra[3]]
                        del lette[-1]
                    else:
                        sopra[0] = sopra[0] + " " + didascalia
                    continue
            celle = _celle(parole)
            prima = _forma(celle[0]) or "" if celle else ""
            if con_importi and len(celle) == 2 and reso._enumeratore(prima) \
                    and re.sub(r"^\S+\)\s*", "", prima).strip() \
                    and not _forma_strutturale(celle[1]):
                # voce e sotto-voce in due celle della stessa riga ("15) proventi da
                # partecipazioni ... da imprese controllate"): due righe, l'importo e' della seconda
                lette.append([celle[0], [None] * len(colonne), set(), centro])
                lette.append([celle[1], per_col, traboccate, centro])
                continue
            lette.append([didascalia, per_col, traboccate, centro])
        if not colonne:
            for riga in lette:
                grezze.append((numero, riga[0], []))
            continue
        # ruoli delle colonne della pagina: percentuale, differenza, esercizio
        valori = [riga[1] for riga in lette if any(v is not None for v in riga[1])]
        anni_pag = _anni_intestazione(tutte[numero], colonne)    # l'anno sta spesso in testata
        ruoli: list[int] = []
        for i in range(len(colonne)):
            col = [r[i] for r in valori if r[i] is not None]
            if not col:
                continue
            if sum(1 for v in col if v.as_tuple().exponent == -3) >= max(1, len(col) // 2):
                continue
            if len(ruoli) >= 2 and _e_differenza(valori, i, ruoli[0], ruoli[1]):
                continue
            ruoli.append(i)
        lette, ruoli, voce_con_importo = _parziali(lette, ruoli, anni_pag, voce_con_importo)
        ruoli = ruoli[:2]
        n_col = max(n_col, len(ruoli))
        for pos, i in enumerate(ruoli):
            if i in anni_pag and pos not in anni_doc:
                anni_doc[pos] = anni_pag[i]
        for didascalia, pc, traboccate, _ in lette:
            if traboccate & set(ruoli):
                raise reso._Rifiuto("importo_illeggibile", didascalia=didascalia)
            grezze.append((numero, didascalia, [pc[i] for i in ruoli]))
    return grezze, n_col, anni_doc


def _righe_da_grezze(grezze: list[tuple[int, str, list[Optional[Decimal]]]], n_col: int,
                     anni_doc: dict[int, int]):
    """Le regole dello schema di legge sulle righe grezze, da qualunque lettura vengano."""
    if not n_col:
        raise reso._Rifiuto("colonne_non_trovate")

    # "CONTO ECONOMICO  2025": l'anno della colonna stampato sul titolo non e' un importo; con un
    # importo il titolo non aprirebbe la sezione e il "21) Utile" resterebbe nel patrimonio netto
    anni_colonne = set(anni_doc.values())
    grezze = [(p, d, [None] * len(v)) if anni_colonne and _intestazione(d)
              and any(x is not None for x in v)
              and all(x is None or (x == x.to_integral() and int(x) in anni_colonne) for x in v)
              else (p, d, v)
              for p, d, v in grezze]
    grezze = _unisci_a_capo(grezze)
    righe_out: list[reso._Riga] = []
    radici_viste: set[str] = set()
    iniziato = finito = False
    pendente: Optional[reso._Riga] = None     # totale di sezione stampato sul titolo
    ix_con_importi = False
    for indice, (numero, didascalia, valori) in enumerate(grezze):
        if finito:
            break
        ha_importi = any(v is not None for v in valori)
        testate_sez = _intestazione(didascalia)
        if ha_importi and not (testate_sez and testate_sez[-1] in ("Attivo", "Passivo")):
            testate_sez = []
        if testate_sez:
            if pendente is not None:
                righe_out.append(pendente)
                pendente = None
            if ha_importi:
                # "STATO PATRIMONIALE ATTIVO 102.750": la sezione col suo totale sul titolo; il
                # totale chiude la sezione, verificato come quello stampato in fondo
                pendente = reso._Riga("Totale " + testate_sez[-1].lower(), _pieni(valori, n_col),
                                      numero)
            for t in testate_sez:
                if t in radici_viste:
                    continue
                if t == "Attivo" and "Stato patrimoniale" not in radici_viste:
                    radici_viste.add("Stato patrimoniale")
                    righe_out.append(reso._Riga("Stato patrimoniale", [], numero))
                radici_viste.add(t)
                righe_out.append(reso._Riga(t, [], numero))
            iniziato = True
            continue
        if not iniziato:
            continue
        if not ha_importi and _e_testata_colonne(didascalia):
            continue
        if not any(r.didascalia in ("Attivo", "Passivo", "Conto economico") for r in righe_out):
            if not ha_importi:
                continue        # intestazioni fra il titolo e la prima sezione
        if not didascalia.split() and ha_importi:
            # importi senza didascalia: il totale stampato di una voce intestazione, che
            # ``_totali_senza_didascalia`` collega alla sua voce. Seguiti da altre righe della
            # stessa voce ("Meno: fondo svalutazione") sono un subtotale intermedio, non il totale
            # della voce: restano fuori.
            seguente = grezze[indice + 1][1] if indice + 1 < len(grezze) else ""
            if seguente.strip() and not _intestazione(seguente) \
                    and not _forma_strutturale(seguente):
                continue
            righe_out.append(reso._Riga("", _pieni(valori, n_col), numero))
            continue
        forma = didascalia if _e_conto(didascalia) else _forma(didascalia)
        if forma is None:
            continue
        m = re.fullmatch(r"Totale\s*\(?\s*([A-D])\s*\)?", forma, re.I)
        if m and "Conto economico" in radici_viste:
            # "TOTALE (C)": il totale della sezione del conto economico, col suo nome di legge
            forma = _TOTALI_SEZIONE_CE[m.group(1).upper()]
        if "Passivo" in radici_viste and "Conto economico" not in radici_viste:
            if reso._calcolato(forma) == "utile" and not ix_con_importi:
                # nel patrimonio netto, senza la sua "IX)", la riga del risultato e' la voce IX
                forma = "IX - " + forma
            e = reso._enumeratore(forma)
            if e and e[0] == "R":
                ix_con_importi = e[1] == ["IX"] and ha_importi
        righe_out.append(reso._Riga(forma, _pieni(valori, n_col) if ha_importi else [], numero))
        if forma in ("Totale attivo", "Totale passivo"):
            pendente = None     # la sezione stampa anche il totale in fondo
        if ha_importi and reso._calcolato(forma) == "utile" and "Conto economico" in radici_viste:
            finito = True
    if pendente is not None:
        righe_out.append(pendente)
    righe_out = _numerazione_che_riparte(righe_out)
    righe_out = _totali_senza_didascalia(righe_out)
    righe_out = _ce_a_segno_algebrico(righe_out)
    tol = _tolleranza_dettaglio(righe_out)
    righe_out = _scadenze_con_totale(righe_out, tol)
    righe_out = _togli_scadenze_di_testa(righe_out, tol)
    righe_out = _togli_dettaglio_conti(righe_out, tol)
    righe_out = _titoli_con_totale(righe_out)
    righe_out = _imposte_come_totale(righe_out)
    righe_out = _totali_di_sezione_ce(righe_out)
    righe_out = _sezioni_vuote(righe_out)
    righe_out = _intestazioni_a_trattino(righe_out)
    righe_out = _raggruppamenti_con_dettaglio(righe_out)
    anni = [anni_doc[i] for i in range(n_col) if i in anni_doc]
    if len(anni) != n_col:
        anni = anni[:1] if anni else []
    return righe_out, n_col, anni


def _intestazioni_a_trattino(righe: list[reso._Riga]) -> list[reso._Riga]:
    """ "17) interessi ed altri oneri finanziari - -" seguita da "altri 438 336" e dal suo totale:
    i trattini della voce sono la cella vuota di un'intestazione (i prospetti Infocamere
    stampano "-" dove non c'e' importo), non zero stampato. Una voce con enumeratore e tutti gli
    importi a zero, seguita da una riga senza enumeratore che porta importi (sua sotto-voce),
    e' un'intestazione: perde i valori, e la sotto-voce si colloca sotto di lei."""
    out = list(righe)
    for k in range(len(out) - 1):
        r, dopo = out[k], out[k + 1]
        if (r.valori and not any(r.valori) and reso._enumeratore(r.didascalia)
                and any(dopo.valori) and not _strutturale(dopo.didascalia)):
            out[k] = reso._Riga(r.didascalia, [], r.pagina)
    return out


_RE_RAGGRUPPAMENTO_SLASH = re.compile(r"^[a-e](?:/[a-e])+\)", re.I)


def _raggruppamenti_con_dettaglio(righe: list[reso._Riga]) -> list[reso._Riga]:
    """ "a/b/c) ammortamento delle immobilizzazioni immateriali e materiali, altre svalutazioni
    22.712" seguita da "a) ... 21.066" e "b) ... 1.646": la riga a barre e' la somma delle
    lettere che la seguono, stampata due volte (una compatta, una per lettera). Si toglie solo se
    le lettere sommano alla riga in ogni colonna: contarle entrambe raddoppierebbe la voce."""
    out: list[reso._Riga] = []
    for k, r in enumerate(righe):
        if r.valori and _RE_RAGGRUPPAMENTO_SLASH.match(r.didascalia.strip()):
            seguenti = []
            for f in righe[k + 1:]:
                if f.valori and re.match(r"^[a-e]\)", f.didascalia.strip()):
                    seguenti.append(f)
                else:
                    break
            if seguenti and _uguali([sum((f.valori[c] for f in seguenti), _ZERO)
                                     for c in range(len(r.valori))], r.valori, _ZERO):
                continue
        out.append(r)
    return out


def _parziali(lette: list[list], ruoli: list[int], anni_pag: dict[int, int],
              voce_con_importo: bool):
    """Colonna dei parziali: due colonne-esercizio vicine che non sono MAI piene sulla stessa
    riga, e la cui testata non dice due anni diversi, sono un esercizio solo stampato su due
    incolonnamenti (parziali a sinistra, totali a destra). Due esercizi veri condividono quasi
    ogni riga. Un parziale sotto una voce che porta gia' il suo importo nella colonna dei totali
    e' il dettaglio della voce ("Costi", "(Ammortamenti)", i conti), gia' compreso: si toglie,
    se non e' a sua volta una voce di legge. Sotto una voce senza importo (il gestionale stampa il
    totale su una riga a parte, senza didascalia) i parziali sono le sue sotto-voci: restano,
    nella colonna dei totali. La voce aperta prosegue da una pagina all'altra."""
    k = 0
    while k + 1 < len(ruoli):
        a, b = ruoli[k], ruoli[k + 1]
        na = sum(1 for riga in lette if riga[1][a] is not None)
        nb = sum(1 for riga in lette if riga[1][b] is not None)
        if ((a in anni_pag and b in anni_pag and anni_pag[a] != anni_pag[b]) or not na or not nb
                or na + nb < _MIN_IMPORTI_COLONNA
                or any(riga[1][a] is not None and riga[1][b] is not None for riga in lette)):
            k += 1
            continue
        nuove = []
        for riga in lette:
            didascalia, pc = riga[0], riga[1]
            strutturale = _forma_strutturale(didascalia)
            if pc[a] is not None:
                if voce_con_importo and not strutturale:
                    continue
                pc[b], pc[a] = pc[a], None
            elif strutturale:
                voce_con_importo = pc[b] is not None
            nuove.append(riga)
        lette = nuove
        if a in anni_pag:
            anni_pag.setdefault(b, anni_pag[a])     # la testata sopra i parziali vale per i totali
        del ruoli[k]
    return lette, ruoli, voce_con_importo


# Due gruppi di parole della stessa riga sono due celle se fra loro c'e' piu' di cosi' (punti).
_STACCO_CELLE = 24.0


def _celle(parole: list[tuple]) -> list[str]:
    """Le celle di testo di una riga: gruppi di parole separati da uno stacco largo."""
    celle: list[list[tuple]] = []
    for w in parole:
        if _norm(str(w[4])) in _EURO:
            continue
        if celle and float(w[0]) - float(celle[-1][-1][2]) <= _STACCO_CELLE:
            celle[-1].append(w)
        else:
            celle.append([w])
    return [" ".join(str(w[4]) for w in c) for c in celle]


def _unisci_a_capo(grezze: list) -> list:
    """Una didascalia andata a capo: la riga senza importi che finisce a meta' frase ("TOTALE
    RETTIFICHE DI VALORE DI") o a meta' parola ("di con-" / "sumo e di merci") e la riga sotto,
    sulla stessa pagina, che la completa e porta gli importi, o che comincia in minuscolo, sono
    una riga sola."""
    out: list = []
    for numero, didascalia, valori in grezze:
        if out:
            p_num, p_did, p_val = out[-1]
            senza = not any(v is not None for v in p_val)
            continua = didascalia[:1].islower() and not _forma_strutturale(didascalia)
            sillaba = re.search(r"[^\W\d_]-$", p_did or "")
            if (p_num == numero and senza and p_did and not _intestazione(p_did)
                    and not _intestazione(didascalia) and not _e_testata_colonne(p_did)
                    and (reso._frase_aperta(p_did) or sillaba)
                    and not _forma_strutturale(didascalia)):
                unione = p_did[:-1] + didascalia if sillaba else p_did + " " + didascalia
                out[-1] = (numero, unione, valori)
                continue
            # il seguito, senza importi e in minuscolo, di una didascalia che li ha gia'
            # ("b) da titoli ... che non costituiscono" / "partecipazioni"); una sotto-voce
            # ("da imprese controllate") porta invece i suoi importi e resta una riga sua
            if (p_num == numero and not senza and not any(v is not None for v in valori)
                    and continua and p_did):
                out[-1] = (numero, p_did + " " + didascalia, p_val)
                continue
        out.append((numero, didascalia, valori))
    return out


def _forma_strutturale(didascalia: str) -> bool:
    forma = _forma(didascalia)
    return bool(forma) and _strutturale(forma)


def _strutturale(didascalia: str) -> bool:
    return bool(reso._enumeratore(didascalia) or reso._e_totale(didascalia)
                or reso._scadenza(didascalia) or reso._calcolato(didascalia)
                or didascalia in _RADICI)


def _livello(didascalia: str) -> Optional[int]:
    e = reso._enumeratore(didascalia)
    return reso._LIVELLO[e[0]] if e else None


def _senza_enumeratore(didascalia: str) -> str:
    return re.sub(r"^\S+\)\s*", "", didascalia)


def _totale_di(didascalia: str) -> str:
    """Il totale di una voce col nome di legge, senza il suo enumeratore: "C) Proventi ed oneri
    finanziari" -> "Totale proventi e oneri finanziari", "20) Imposte sul reddito" -> "Totale
    delle imposte sul reddito dell'esercizio". Cosi' lo riconoscono i controlli."""
    testo = re.sub(r"^\S+?\)\s*|^[IVX]+ - ", "", didascalia)
    return _forma("Totale " + testo) or "Totale " + didascalia


# --------------------------------------------------------------------------------------
# Struttura: dalle righe lette all'albero dello schema
# --------------------------------------------------------------------------------------

def _numerazione_che_riparte(righe: list[reso._Riga]) -> list[reso._Riga]:
    """La numerazione dello schema non torna mai indietro: un numero arabo minore di quello
    della voce aperta ("1) da imprese controllate" sotto 16), "1) Imposte correnti" sotto 20))
    e' il dettaglio della voce, non una nuova voce: perde il numero e resta una sua riga. Allo
    stesso modo la stessa lettera ripetuta subito sotto la voce a lettera aperta ("d) proventi
    diversi dai precedenti:" / "d) da altri 0,58") e' il suo dettaglio, non una voce sorella."""
    out: list[reso._Riga] = []
    arabo_aperto: Optional[int] = None
    for r in righe:
        e = reso._enumeratore(r.didascalia)
        if r.didascalia in _RADICI or (e and e[0] in ("L", "R")):
            arabo_aperto = None
        elif e and e[0] == "N":
            numero = int(re.match(r"\d+", e[1][0]).group())
            if arabo_aperto is not None and numero < arabo_aperto:
                out.append(reso._Riga(_senza_enumeratore(r.didascalia), r.valori, r.pagina))
                continue
            arabo_aperto = numero
        elif e and e[0] == "l" and out and not out[-1].valori and r.valori \
                and reso._enumeratore(out[-1].didascalia) == e:
            out.append(reso._Riga(_senza_enumeratore(r.didascalia), r.valori, r.pagina))
            continue
        out.append(r)
    return out


def _padre_di_cui_e_totale(out: list[reso._Riga], valori: list[Decimal]) -> Optional[reso._Riga]:
    """L'ultima riga di ``out`` e' una voce senza importo e ha sorelle gia' stampate sotto lo
    stesso padre (anch'esso senza importo): se le sorelle con importo sommano agli ``valori``,
    quegli importi sono il totale del padre. None altrimenti."""
    ultima = out[-1]
    liv = _livello(ultima.didascalia)
    if liv is None:
        return None
    somma = [_ZERO] * len(valori)
    trovate = 0
    for r in reversed(out[:-1]):
        lr = _livello(r.didascalia)
        if lr is None:
            if r.didascalia in _RADICI or reso._calcolato(r.didascalia) or reso._e_totale(r.didascalia):
                return None
            continue
        if lr < liv:
            if r.valori or not trovate:
                return None
            return r if _uguali(somma, valori, _ZERO) else None
        if lr == liv and r.valori:
            somma = [a + b for a, b in zip(somma, r.valori)]
            trovate += 1
    return None


def _totali_senza_didascalia(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Una riga di soli importi, senza didascalia, chiude la voce intestazione aperta piu'
    interna (una voce con enumeratore stampata senza importi: "22) Imposte sul reddito" seguita
    dalle sue righe, poi gli importi del totale da soli). Diventa "Totale <voce>" e si verifica
    sulle sotto-voci come ogni totale stampato. Subito sotto la voce senza importi sono i suoi,
    stampati a capo; uguali alla riga sopra ne sono la ripetizione (il netto della voce); senza
    una voce aperta da chiudere non sono una riga."""
    out: list[reso._Riga] = []
    aperte: list[tuple[int, reso._Riga]] = []
    for r in righe:
        if r.didascalia == "":
            if out and out[-1].valori == r.valori:
                continue
            if out and out[-1].didascalia and not out[-1].valori \
                    and (_livello(out[-1].didascalia) is not None
                         or reso._scadenza(out[-1].didascalia)):
                padre = _padre_di_cui_e_totale(out, r.valori)
                if padre is not None:
                    # "a) vari 191" / "b) contributi" (senza importo) / "191": le sorelle gia'
                    # stampate sommano alla riga, che quindi chiude il padre, non e' di "b)"
                    while aperte and aperte[-1][1] is not padre:
                        aperte.pop()
                    if aperte:
                        aperte.pop()
                    out.append(reso._Riga(_totale_di(padre.didascalia), r.valori, r.pagina))
                    continue
                if aperte and aperte[-1][1] is out[-1]:
                    aperte.pop()
                out[-1] = reso._Riga(out[-1].didascalia, r.valori, out[-1].pagina)
                continue
            if aperte:
                _, titolo = aperte.pop()
                out.append(reso._Riga(_totale_di(titolo.didascalia), r.valori, r.pagina))
            continue
        if r.didascalia in _RADICI or reso._calcolato(r.didascalia) or reso._e_totale(r.didascalia):
            if not reso._e_totale(r.didascalia):
                aperte = []
            elif aperte:
                aperte.pop()        # un totale con la sua didascalia chiude la voce piu' interna
        else:
            liv = _livello(r.didascalia)
            if liv is not None:
                while aperte and aperte[-1][0] >= liv:
                    aperte.pop()
                if not r.valori:
                    aperte.append((liv, r))
        out.append(r)
    return out


def _uguali(a, b, tol: Decimal) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _ce_a_segno_algebrico(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Conto economico stampato col segno algebrico (i costi negativi): lo si riconosce dal
    documento stesso - il totale dei costi della produzione e' negativo e la differenza A - B
    stampata e' la SOMMA dei due totali stampati. Allora ogni riga dei costi (B, 17, 19, 20)
    cambia segno, totali compresi, e torna nella convenzione dello schema di legge; i
    risultati intermedi (differenza, C, D, risultato prima delle imposte, utile) sono gia'
    con il segno giusto e restano. Se le voci dei costi sono positive e solo il totale porta il
    meno ("Totale (B) -33.155.832") e' il segno della sottrazione stampato sul totale: cambia
    segno solo il totale."""
    try:
        inizio = next(k for k, r in enumerate(righe) if r.didascalia == "Conto economico")
    except StopIteration:
        return righe
    diff = next((k for k in range(inizio, len(righe))
                 if reso._calcolato(righe[k].didascalia) == "differenza" and righe[k].valori), None)
    if diff is None or diff - 1 <= inizio:
        return righe
    tot_b = righe[diff - 1]
    inizio_b = next((k for k in range(inizio, diff)
                     if reso._enumeratore(righe[k].didascalia) == ("L", ["B"])), None)
    if not reso._e_totale(tot_b.didascalia) or not tot_b.valori or inizio_b is None:
        return righe
    tot_a = next((righe[k] for k in range(inizio_b - 1, inizio, -1)
                  if reso._e_totale(righe[k].didascalia) and righe[k].valori), None)
    if tot_a is None or not tot_b.valori[0] < 0:
        return righe
    if not _uguali([a + b for a, b in zip(tot_a.valori, tot_b.valori)], righe[diff].valori, _ZERO):
        return righe
    voci_b = [r.valori[0] for r in righe[inizio_b:diff]
              if r.valori and r.valori[0] != 0 and not reso._e_totale(r.didascalia)]
    if sum(1 for v in voci_b if v < 0) * 2 <= len(voci_b):
        return [reso._Riga(r.didascalia, [-v for v in r.valori], r.pagina)
                if inizio_b <= k < diff and reso._e_totale(r.didascalia) and r.valori
                and r.valori[0] < 0 else r for k, r in enumerate(righe)]
    out = list(righe[:inizio_b])
    arabo: Optional[str] = None
    for k in range(inizio_b, len(righe)):
        r = righe[k]
        e = reso._enumeratore(r.didascalia)
        if e and e[0] == "L":
            arabo = None
        elif e and e[0] == "N":
            arabo = e[1][0]
        if reso._calcolato(r.didascalia) or r.didascalia in (
                "Totale proventi e oneri finanziari",
                "Totale delle rettifiche di valore di attivita' e passivita' finanziarie"):
            if reso._calcolato(r.didascalia) == "differenza":
                arabo = None
            out.append(r)
            continue
        costo = (k < diff) or arabo in ("17", "19", "20")
        out.append(reso._Riga(r.didascalia, [-v for v in r.valori] if costo else r.valori,
                              r.pagina))
    return out


def _tolleranza_dettaglio(righe: list[reso._Riga]) -> Decimal:
    """Lo scarto ammesso fra una riga e i conti che la compongono: quello dei totali del
    documento. In un documento che stampa le voci di legge all'euro (anche quando i conti
    portano i centesimi) la voce e' l'arrotondamento della somma dei conti, non la somma degli
    arrotondati; altrimenti zero."""
    voci = [v for r in righe if _strutturale(r.didascalia) for v in r.valori]
    if voci and all(v == v.to_integral_value() for v in voci):
        return _TOLLERANZA_INTERI
    return _ZERO


# Oltre questo numero di righe la prova coi segni liberi non e' piu' una prova.
_MAX_RIGHE_CON_SEGNO = 8


def _scompone(bersaglio: list[Decimal], valori: list[list[Decimal]], tol: Decimal) -> bool:
    """I valori (nell'ordine di stampa) sono il dettaglio del bersaglio: la loro somma lo
    riproduce, contando ogni riga una volta sola. Un conto seguito dai sottoconti che lo
    compongono esattamente (mastro e foglie) conta una volta: si sommano i mastri OPPURE le
    foglie, mai entrambi, ed e' il totale stampato - non il codice - a dire chi e' il mastro.
    Il dettaglio puo' essere stampato col segno della sezione (dare/avere): la somma vale anche
    cambiata di segno, ma con un segno solo per tutte le colonne. Infine, per poche righe, le
    componenti di segno opposto stampate positive ("17-bis) utili e perdite su cambi (97)":
    "utili su cambi 29", "perdite su cambi 126"): uno stesso segno per riga deve chiudere ogni
    colonna, e la prima riga resta additiva."""
    n = len(valori)
    if not n:
        return False
    colonne = len(bersaglio)
    prefissi = [[_ZERO] * colonne]
    for v in valori:
        prefissi.append([a + b for a, b in zip(prefissi[-1], v)])
    stati: list[set] = [set() for _ in range(n + 1)]
    stati[0].add(tuple([_ZERO] * colonne))
    for i in range(n):
        if not stati[i]:
            continue
        for s in stati[i]:
            stati[i + 1].add(tuple(a + b for a, b in zip(s, valori[i])))
        # la riga i e' un mastro: le righe i+1..j-1 sono i suoi conti
        for j in range(i + 2, n + 1):
            figli = [prefissi[j][c] - prefissi[i + 1][c] for c in range(colonne)]
            if _uguali(figli, valori[i], tol):
                for s in stati[i]:
                    stati[j].add(tuple(a + b for a, b in zip(s, valori[i])))
        for k in range(i + 1, n + 1):
            if len(stati[k]) > 4096:
                return False        # troppe letture possibili: nessuna e' una prova
    if any(_uguali(s, bersaglio, tol) or _uguali(s, [-x for x in bersaglio], tol)
           for s in stati[n]):
        return True
    if n < 2 or n > _MAX_RIGHE_CON_SEGNO:
        return False
    for maschera in range(1, 1 << (n - 1)):
        segni = [1] + [-1 if maschera >> (k - 1) & 1 else 1 for k in range(1, n)]
        if any(a != b and va == vb and any(va)
               for (a, va), (b, vb) in itertools.combinations(zip(segni, valori), 2)):
            continue        # due righe uguali di segno opposto si annullano: non e' una prova
        somma = [sum((s * v[c] for s, v in zip(segni, valori)), _ZERO) for c in range(colonne)]
        if _uguali(somma, bersaglio, tol):
            return True
    return False


def _corsa_dettaglio(righe: list[reso._Riga], i: int) -> int:
    """Fine (esclusa) della corsa di righe di dettaglio che comincia in i: righe senza
    enumeratore, con importi; una riga senza importi vi rientra solo se la corsa continua dopo
    di lei con un conto (la seconda riga di una didascalia di conto andata a capo)."""
    j = i
    while j < len(righe) and not _strutturale(righe[j].didascalia):
        if not righe[j].valori:
            k = j
            while k < len(righe) and not righe[k].valori and not _strutturale(righe[k].didascalia):
                k += 1
            if k < len(righe) and righe[k].valori and not _strutturale(righe[k].didascalia) \
                    and k > j and _e_conto(righe[k].didascalia):
                j = k
                continue
            break
        j += 1
    return j


def _valori_corsa(righe: list[reso._Riga]) -> list[list[Decimal]]:
    return [list(f.valori) for f in righe if f.valori]


def _togli_dettaglio_conti(righe: list[reso._Riga], tol: Decimal = _ZERO) -> list[reso._Riga]:
    """Sotto una riga con importo (voce di legge, scadenza, o sotto-voce senza enumeratore),
    le righe di dettaglio che la riproducono (vedi ``_scompone``) sono i conti che la
    compongono: la riga li ha gia' contati. Si prova l'intera corsa di dettaglio; se non torna,
    la sola testa di righe che cominciano con un codice conto (la sotto-voce "Riserva
    straordinaria" seguita dal suo conto "23010 Riserva straordinaria", e poi dalla sotto-voce
    successiva). Se nessuna delle due torna, le righe restano: decidera' il totale stampato."""
    out: list[reso._Riga] = []
    i = 0
    while i < len(righe):
        r = righe[i]
        out.append(r)
        i += 1
        if (not r.valori or reso._e_totale(r.didascalia) or reso._calcolato(r.didascalia)
                or _e_conto(r.didascalia)):
            continue        # un conto non e' una voce: i mastri li riconosce ``_scompone``
        fine = _corsa_dettaglio(righe, i)
        if fine == i:
            continue
        tagli = [fine]
        k = i
        while k < fine and (_e_conto(righe[k].didascalia) or not righe[k].valori):
            k += 1
        while k > i and not righe[k - 1].valori:
            k -= 1
        if i < k < fine:
            tagli.append(k)
        for taglio in tagli:
            # una riga a zero toglie solo conti a zero: con i segni liberi lo zero "si compone"
            # con qualunque mastro e i suoi conti ("Contributi 0" prima di "Altri 4.800" + il
            # suo conto), e si perderebbe massa letta
            if not any(r.valori) and any(any(f.valori) for f in righe[i:taglio]):
                continue
            if _scompone(list(r.valori), _valori_corsa(righe[i:taglio]), tol):
                i = taglio
                # "VI - Altre riserve 1", i suoi conti, "Totale altre riserve 1": tolti i conti,
                # il totale che ripete la voce (stessi importi, stesso nome) va via con loro,
                # altrimenti chiude il padre della voce e quella dopo sale di un livello
                if (i < len(righe) and reso._enumeratore(r.didascalia)
                        and reso._e_totale(righe[i].didascalia)
                        and righe[i].valori == r.valori
                        and _stesso_nome(righe[i].didascalia, r.didascalia)):
                    i += 1
                break
    return out


_PAROLE_VUOTE = {"totale", "di", "da", "dei", "delle", "della", "del", "e", "ed", "nelle", "nel",
                 "in", "a", "al", "per", "i", "il", "la", "le", "gli", "lo", "l", "verso", "dell"}


def _parole_nome(didascalia: str) -> set[str]:
    testo = re.sub(r"^\S+?\)\s*|^[ivx]+ - ", "", _norm(didascalia))
    return {w for w in re.findall(r"[a-zà-ù]+", testo) if w not in _PAROLE_VUOTE}


def _stesso_nome(totale: str, voce: str) -> bool:
    """Il nome del totale e quello della voce, senza enumeratore e articoli, stanno l'uno
    nell'altro ("Totale altre riserve" / "VI - Altre riserve")."""
    a, b = _parole_nome(totale), _parole_nome(voce)
    return bool(a and b) and (a <= b or b <= a)


def _togli_scadenze_di_testa(righe: list[reso._Riga], tol: Decimal) -> list[reso._Riga]:
    """ "II - Crediti" seguito da "esigibili entro" / "esigibili oltre" con importo e POI dalle
    sotto-voci 1), 5-bis)...: le righe di scadenza in testa sono la ripartizione del totale della
    voce, stampata prima del dettaglio che la ripete voce per voce. Si tolgono solo se il totale
    stampato della voce e' la loro somma (contarle entrambe raddoppierebbe la voce)."""
    out: list[reso._Riga] = []
    i = 0
    while i < len(righe):
        r = righe[i]
        out.append(r)
        i += 1
        liv = _livello(r.didascalia)
        if liv is None or r.valori:
            continue
        j = i
        while j < len(righe) and reso._scadenza(righe[j].didascalia) and righe[j].valori:
            j += 1
        if j == i or j >= len(righe):
            continue
        dopo = _livello(righe[j].didascalia)
        if dopo is None or dopo <= liv:
            continue
        somma = [sum((f.valori[c] for f in righe[i:j]), _ZERO) for c in range(len(righe[i].valori))]
        for f in righe[j:]:
            lf = _livello(f.didascalia)
            if (lf is not None and lf <= liv) or f.didascalia in _RADICI \
                    or reso._calcolato(f.didascalia):
                break
            if reso._e_totale(f.didascalia) and f.valori and _uguali(f.valori, somma, tol):
                i = j
                break
    return out


def _scadenze_con_totale(righe: list[reso._Riga], tol: Decimal) -> list[reso._Riga]:
    """ "esigibili entro l'esercizio successivo" senza importo, i conti, poi "Totale esigibili
    entro l'esercizio successivo" con l'importo: la scadenza e' la riga, il suo importo e' il
    totale stampato, i conti sono il suo dettaglio. Si fonde solo se i conti sommano al
    totale (``_scompone``); altrimenti le righe restano come sono e il controllo le rifiuta."""
    out: list[reso._Riga] = []
    i = 0
    while i < len(righe):
        r = righe[i]
        scad = reso._scadenza(r.didascalia)
        if scad and not r.valori:
            fine = _corsa_dettaglio(righe, i + 1)
            if i + 1 < fine < len(righe):
                t = righe[fine]
                n = _norm(t.didascalia)
                if (reso._e_totale(t.didascalia) and t.valori and "esigibil" in n
                        and (("entro" in n) == (scad == "E"))
                        and _scompone(list(t.valori), _valori_corsa(righe[i + 1:fine]), tol)):
                    out.append(reso._Riga(r.didascalia, list(t.valori), r.pagina))
                    i = fine + 1
                    continue
        out.append(r)
        i += 1
    return out


def _titoli_con_totale(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Una voce che stampa il proprio totale sul titolo ed e' seguita da sotto-voci piu' profonde
    (o da righe di scadenza) e' un'intestazione: il suo importo diventa il totale che chiude il
    gruppo, verificato come ogni altro sulle sotto-voci. Se il gruppo ha gia' il suo totale
    stampato, uguale, il titolo perde solo l'importo. Uno zero sul titolo non e' un totale: e' il
    titolo stampato con la cella vuota a zero, e le sotto-voci le verificano i totali sopra."""
    out: list[reso._Riga] = []
    pendenti: list[tuple[int, reso._Riga]] = []      # (livello, titolo) in attesa di chiusura

    def chiudi_fino(livello: Optional[int]):
        while pendenti and (livello is None or pendenti[-1][0] >= livello):
            _, titolo = pendenti.pop()
            out.append(reso._Riga(_totale_di(titolo.didascalia), titolo._totale, titolo.pagina))

    for k, r in enumerate(righe):
        liv = _livello(r.didascalia)
        if r.didascalia in _RADICI or reso._calcolato(r.didascalia) \
                or r.didascalia in ("Totale attivo", "Totale passivo"):
            chiudi_fino(None)
        elif liv is not None:
            chiudi_fino(liv)
        elif reso._e_totale(r.didascalia) and pendenti:
            # un totale stampato che chiude il titolo pendente piu' interno con lo stesso importo
            if r.valori == pendenti[-1][1]._totale:
                pendenti.pop()
        out.append(r)
        if liv is not None and r.valori and k + 1 < len(righe):
            dopo = righe[k + 1]
            liv_dopo = _livello(dopo.didascalia)
            if (liv_dopo is not None and liv_dopo > liv) or reso._scadenza(dopo.didascalia):
                totale = list(r.valori)
                r.valori = []
                if any(totale):
                    r._totale = totale
                    pendenti.append((liv, r))
    chiudi_fino(None)
    return out


def _imposte_come_totale(righe: list[reso._Riga]) -> list[reso._Riga]:
    """"20) Imposte sul reddito 458.043" stampata col suo importo e senza un totale sotto: la
    voce e' il totale delle imposte, e lo e' anche per il controllo prima delle imposte - imposte
    = utile, che legge il totale. Diventa la voce, la sua riga e il suo totale."""
    out: list[reso._Riga] = []
    in_ce = False
    for k, r in enumerate(righe):
        in_ce = in_ce or r.didascalia == "Conto economico"
        e = reso._enumeratore(r.didascalia)
        dopo = righe[k + 1] if k + 1 < len(righe) else None
        if (in_ce and r.valori and e and e[0] == "N" and e[1] == ["20"]
                and not (dopo is not None and reso._e_totale(dopo.didascalia))):
            out.append(reso._Riga(r.didascalia, [], r.pagina))
            out.append(reso._Riga(_senza_enumeratore(r.didascalia), r.valori, r.pagina))
            out.append(reso._Riga(_totale_di(r.didascalia), r.valori, r.pagina))
            continue
        out.append(r)
    return out


def _totali_di_sezione_ce(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Nel conto economico un "TOTALE" senza altro, che chiude la sezione (subito dopo viene la
    sezione seguente o un risultato calcolato: "Differenza ...", "Risultato prima delle
    imposte"), e' il totale di quella sezione: prende il suo nome di legge, quello che i
    controlli A - B, + C + D leggono."""
    out = list(righe)
    in_ce = False
    lettera: Optional[str] = None
    for k, r in enumerate(righe):
        in_ce = in_ce or r.didascalia == "Conto economico"
        if not in_ce:
            continue
        e = reso._enumeratore(r.didascalia)
        if e and e[0] == "L":
            lettera = e[1][0].upper()
            continue
        if reso._calcolato(r.didascalia):
            lettera = None
            continue
        if _norm(r.didascalia) != "totale" or not r.valori or lettera not in _TOTALI_SEZIONE_CE:
            continue
        dopo = righe[k + 1] if k + 1 < len(righe) else None
        e_dopo = reso._enumeratore(dopo.didascalia) if dopo is not None else None
        if dopo is not None and ((e_dopo and e_dopo[0] == "L") or reso._calcolato(dopo.didascalia)):
            out[k] = reso._Riga(_TOTALI_SEZIONE_CE[lettera], r.valori, r.pagina)
    return out


def _sezioni_vuote(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Una sezione di primo livello ("D) Rettifiche di valore ...") stampata con importi tutti a
    zero e senza sotto-voci e' vuota: resta il titolo, senza importi. Non c'e' un campo per la
    sezione intera, e uno zero non ha bisogno di casa."""
    for k, r in enumerate(righe):
        e = reso._enumeratore(r.didascalia)
        if not (e and e[0] == "L" and r.valori and not any(r.valori)):
            continue
        dopo = righe[k + 1] if k + 1 < len(righe) else None
        liv_dopo = _livello(dopo.didascalia) if dopo else None
        if dopo is not None and ((liv_dopo is not None and liv_dopo > 1)
                                 or reso._scadenza(dopo.didascalia)):
            continue
        r.valori = []
    return righe


# --------------------------------------------------------------------------------------
# Punto d'ingresso
# --------------------------------------------------------------------------------------

def riconosci(file_path: str) -> bool:
    """Testo con stato patrimoniale, conto economico e le voci di legge di primo livello."""
    try:
        with fitz.open(file_path) as d:
            testo = _norm(" ".join(p.get_text() for p in list(d)[:12]))
    except Exception:
        return False
    testo = testo.replace(" ", "")
    return ("statopatrimoniale" in testo or "attivo" in testo) and "contoeconomico" in testo \
        and "immobilizzazioni" in testo and "valoredellaproduzione" in testo


def estrai(file_path: str) -> Optional[dict]:
    """Stessa forma del candidato di ``xbrl_reso_parser.estrai``: None se il documento non e'
    uno schema di legge; altrimenti adottabile solo quando ogni controllo chiude al centesimo."""
    if not riconosci(file_path):
        return None
    try:
        documento = fitz.open(file_path)
    except Exception:
        return None
    with documento:
        try:
            righe, colonne, anni = _leggi(documento)
        except reso._Rifiuto as exc:
            return reso._rifiutato([], exc.controllo, **exc.dettaglio)
        return _giudica(documento, righe, colonne, anni)


def _giudica(documento: fitz.Document, righe: list[reso._Riga], colonne: int, anni: list[int],
             tabelle_nota: Optional[list[tuple[int, list]]] = None):
    """Il cuore del lettore XBRL sulle righe normalizzate, e la variante coi segni come
    contributo quando la prima lettura non e' adottabile."""
    primo = reso.estrai_da_righe(documento, righe, colonne, anni, vuote_zero=True,
                                 eredita_dal_padre=True, tolleranza=_tolleranza(righe),
                                 tabelle_nota=tabelle_nota)
    if primo["adottabile"]:
        return primo
    variante = _segni_come_contributo(righe)
    if variante is None:
        return primo
    secondo = reso.estrai_da_righe(documento, variante, colonne, anni, vuote_zero=True,
                                   eredita_dal_padre=True, tolleranza=_tolleranza(variante),
                                   tabelle_nota=tabelle_nota)
    return secondo if secondo["adottabile"] else primo


# il richiamo di una nota in coda all'importo: "220.159 (1)", "220.159 (*)", "220.159 *"
_RICHIAMO_NOTA = re.compile(r"\s*(?:\(\s*(?:\d{1,2}|\*+)\s*\)|\*+)$")


def _cella_mineru(cella: str) -> Optional[Decimal]:
    """L'importo di una cella MinerU, senza il richiamo di nota in coda."""
    if not cella:
        return None
    v = _importo(cella)
    if v is None:
        senza = _RICHIAMO_NOTA.sub("", cella)
        if senza != cella and senza:
            v = _importo(senza)
    return v


def _grezze_mineru(tables) -> tuple[list[tuple[int, str, list[Optional[Decimal]]]], int, dict[int, int]]:
    """Le tabelle di MinerU -> le stesse righe grezze che ``_grezze_pdf`` ricava dalla geometria.

    MinerU consegna ogni riga gia' divisa in celle: la didascalia nella prima, poi una cella
    per colonna. Le colonne-esercizio sono quelle che l'intestazione della tabella data
    ("31-12-2025", "31-12-2024"); una tabella senza intestazione eredita quelle della tabella
    prima (il prospetto che continua sulla pagina dopo). Una tabella con un'intestazione che
    non e' di date (la nota "Varie altre riserve" in mezzo al prospetto) non e' il prospetto."""
    grezze: list[tuple[int, str, list[Optional[Decimal]]]] = []
    anni_doc: dict[int, int] = {}
    n_col = 0
    for table in tables:
        dentro = True
        for indice, row in enumerate(table.rows):
            celle = [str(c.text or "").strip() for c in row.cells]
            date = [_DATA.match(c) for c in celle[1:]]
            if len(celle) > 1 and all(date) and not _norm(celle[0]):
                # l'intestazione delle colonne: gli anni, nell'ordine stampato
                n_col = max(n_col, len(date))
                for pos, m in enumerate(date):
                    anni_doc.setdefault(pos, _anno(m))
                dentro = True
                continue
            if indice == 0 and len(celle) > 1 and any(date):
                dentro = False      # una tabella con un'intestazione propria: nota, non prospetto
            if not dentro:
                continue
            valori: list[Optional[Decimal]] = []
            didascalia = celle[0] if celle else ""
            for c in celle[1:]:
                v = _cella_mineru(c)
                if v is None and c and not valori and not re.search(r"\d", c):
                    didascalia = f"{didascalia} {c}".strip()   # didascalia spezzata in due celle
                    continue
                valori.append(v)
            grezze.append((table.page, didascalia, valori))
    if n_col:
        grezze = [(p, d, (v + [None] * n_col)[:n_col]) for p, d, v in grezze]
    return grezze, n_col, anni_doc


def estrai_da_mineru(context) -> Optional[dict]:
    """Lo schema di legge di una scansione, dalle tabelle di MinerU: stesse regole e stessi
    controlli al centesimo di ``estrai``, solo le righe vengono dalle celle e non dalla
    geometria. None se il documento non e' uno schema di legge."""
    testo = _norm(getattr(context, "full_text", "") or "").replace(" ", "")
    if not (("statopatrimoniale" in testo or "attivo" in testo) and "contoeconomico" in testo
            and "immobilizzazioni" in testo and "valoredellaproduzione" in testo):
        return None
    tables = getattr(context, "tables", ()) or ()
    try:
        righe, colonne, anni = _righe_da_grezze(*_grezze_mineru(tables))
    except reso._Rifiuto as exc:
        return reso._rifiutato([], exc.controllo, **exc.dettaglio)
    # le tabelle della nota con le scadenze (crediti e debiti entro/oltre) vengono anch'esse
    # dalle celle di MinerU: il documento vuoto non ha pagine da cui rileggerle
    nota = [(t.page, [[str(c.text or "") for c in r.cells] for r in t.rows]) for t in tables]
    with fitz.open() as vuoto:
        return _giudica(vuoto, righe, colonne, anni, tabelle_nota=nota)


def _negativa(r: reso._Riga) -> bool:
    return bool(r.valori) and all(v <= 0 for v in r.valori) and any(v < 0 for v in r.valori)


def _segni_come_contributo(righe: list[reso._Riga]) -> Optional[list[reso._Riga]]:
    """Una seconda lettura del conto economico per i gestionali che stampano costi e oneri col
    segno del loro effetto sul risultato ("TOTALE (B) -33.155.832", "17) interessi -11.460",
    "22) imposte -458.043"), mentre lo schema di legge li stampa positivi e li sottrae.
    - costi della produzione (B) stampati in maggioranza negativi: tutta la sezione ha il segno
      del contributo, e si gira tutta (anche la variazione delle rimanenze positiva);
      altrimenti si girano solo i totali di B stampati negativi;
    - oneri finanziari (17), svalutazioni (18-19 lato 19) e imposte (20): si girano le righe
      stampate tutte negative, non il totale della sezione C o D che le comprende.
    Si prova solo se la lettura letterale non chiude, e si adotta solo se OGNI controllo chiude:
    un'imposta negativa vera (un provento fiscale) girata non tornerebbe con l'utile stampato.
    None se non c'e' nulla da girare."""

    def scorri():
        """(indice, riga, sezione A..E, voce aperta) per le righe del conto economico."""
        in_ce, lettera, voce = False, None, None
        for k, r in enumerate(righe):
            if r.didascalia == "Conto economico":
                in_ce = True
            if not in_ce:
                continue
            e = reso._enumeratore(r.didascalia)
            if e and e[0] == "L":
                lettera, voce = e[1][0], None
            elif e and e[0] == "N":
                voce = e[1][0]
            elif reso._calcolato(r.didascalia):
                lettera = voce = None
                continue
            yield k, r, lettera, voce

    voci_b = [r for _, r, lettera, _ in scorri() if lettera == "B" and r.valori
              and not reso._e_totale(r.didascalia) and any(v != 0 for v in r.valori)]
    b_tutta_negativa = bool(voci_b) and sum(1 for r in voci_b if _negativa(r)) * 2 > len(voci_b)
    out = list(righe)
    girate = 0
    for k, r, lettera, voce in scorri():
        if not r.valori:
            continue
        totale = reso._e_totale(r.didascalia)
        if lettera == "B":
            da_girare = b_tutta_negativa or (totale and _negativa(r))
        elif voce in ("17", "19", "20") and _negativa(r):
            # il totale della voce si', quello della sezione (C, D) che la comprende no
            da_girare = not (totale and (
                re.search(r"proventi e oneri|rettifiche", _norm(r.didascalia))
                or _norm(r.didascalia) == "totale"))
        else:
            da_girare = False
        if da_girare:
            out[k] = reso._Riga(r.didascalia, [-v for v in r.valori], r.pagina)
            girate += 1
    return out if girate else None


# Documento a importi interi: ogni voce e' gia' arrotondata all'euro, e il totale stampato e'
# l'arrotondamento della somma vera, non la somma degli arrotondati. Lo scarto resta sotto il
# tappo dichiarato del percorso snello (10 euro), che poi lo misura e lo dichiara.
_TOLLERANZA_INTERI = Decimal("5")


def _tolleranza(righe: list[reso._Riga]) -> Decimal:
    valori = [v for r in righe for v in r.valori]
    if valori and all(v == v.to_integral_value() for v in valori):
        return _TOLLERANZA_INTERI
    return _ZERO
