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
  cadono in una colonna di importi (bordo destro allineato su molte righe della pagina);
- le colonne-esercizio sono le colonne di importi da sinistra che non sono una differenza
  (valore = prima - seconda su tutte le righe) ne' una percentuale (tre decimali);
- intestazioni e piedi di pagina (righe ripetute nei margini, "Pagina N di M") non sono righe;
- gli enumeratori si portano alla forma "A)", "I - ", "1)", "a)"; i subtotali calcolati
  ("A-B TOTALE DIFF. TRA VALORE E COSTI") alla didascalia di legge;
- le righe che cominciano con un codice conto non sono voci di legge, e le righe senza
  enumeratore sotto una voce con importo che sommano esattamente a quell'importo sono il
  dettaglio dei conti: la voce le ha gia' contate;
- una voce che stampa il proprio totale sulla riga del titolo, seguita dalle sotto-voci, e'
  un'intestazione con il suo totale: il totale si verifica sulle sotto-voci come ogni altro;
- una riga senza enumeratore eredita la voce del padre, se il padre ne ha una.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Optional

import fitz

from importers import xbrl_reso_parser as reso

_ZERO = Decimal("0")

_IMPORTO = re.compile(r"^\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,3})?-?\)?$")
_EURO = {"€", "�", "eur", "euro"}
_DATA = re.compile(r"^(?:\d{2}[-/.]\d{2}[-/.])?(20\d{2})$")
# Una cella numerica troppo stretta per il suo valore: il gestionale stampa asterischi.
_TRABOCCATO = re.compile(r"^\*+$")
_CODICE_CONTO = re.compile(r"^\d{2,3}(?:[./-]\d{1,4}){1,4}$|^\d{5,}$")

# Due token sono nella stessa colonna se i loro bordi destri distano al piu' cosi' (punti).
_TOL_COLONNA = 14.0
# Una colonna di importi e' tale se la pagina ne porta almeno tanti allineati.
_MIN_IMPORTI_COLONNA = 4
_TOL_RIGA = 3.0
# Fascia in testa e in fondo alla pagina (intestazione e piede ripetuti).
_FASCIA_MARGINE = 0.09

_RE_ROMANO = re.compile(r"^(VIII|VII|VI|IV|IX|III|II|V|X|I)(?:\s*[\)\.\-–:]\s*|\s+(?=[A-Za-z]))(.*)$")
_RE_CAPITALE = re.compile(r"^([A-E])\s*[\)\.]\s*(.*)$")
_RE_ARABO = re.compile(r"^(\d{1,2})\s*-?\s*(bis|ter|quater|quinquies)?\s*[\)\.]\s+(.*)$", re.I)
_RE_LETTERA = re.compile(r"^([a-z])\s*-?\s*(bis|ter)?(\d)?\s*\)\s*(.*)$")
# Un totale con davanti il codice della voce ("II TOTALE ...", "d-bis TOTALE ...") o la formula
# che lo calcola ("A-B TOTALE DIFF. ...", "15+16-17+-17b TOTALE ...").
_RE_TOTALE_CON_CODICE = re.compile(
    r"^(?:[A-E]|[IVX]+|\d{1,2}(?:-?(?:bis|ter|quater))?|[a-z](?:-?bis)?"
    r"|[A-E\d][A-E\d+\-±/b]*[+\-±][A-E\d+\-±/b]*)\s+(totale\b.*)$", re.I)
_SCADENZA = re.compile(r"^(?:crediti\s+|debiti\s+|importi\s+)?(?:esigibil[ie]\s+)?(entro|oltre)\b", re.I)
# Subtotali calcolati, comunque abbreviati: alla didascalia che il cuore del lettore riconosce.
_CALCOLATI = (
    (re.compile(r"^(?:totale\s+)?diff(?:erenza|\.)?\s+(?:tra\s+)?(?:i\s+)?valor[ei]\s*(?:e|-)\s*costi"),
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
# Piedi e intestazioni di pagina riconoscibili dal testo: "Pagina 3 di 8", "Pag. 10 di",
# "Stampata il ... Pagina 1 di", "Utente: administrator".
_PIEDE = re.compile(r"\bpag(?:ina|\.)?\s*\d*\s*(?:di\s*\d*)?\s*$|^pagina\b|\butente\s*:")


def _norm(testo: str) -> str:
    testo = "".join(c for c in unicodedata.normalize("NFKD", testo) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", testo).strip().casefold()


def _importo(token: str) -> Optional[Decimal]:
    t = token.strip()
    if not _IMPORTO.match(t):
        return None
    negativo = t.startswith(("(", "-")) or t.endswith("-")
    t = t.strip("()").strip("-").replace(".", "").replace(",", ".")
    try:
        v = Decimal(t)
    except InvalidOperation:
        return None
    return -v if negativo else v


def _ricompatta_spaziato(testo: str) -> str:
    """ "S T A T O P A T R I M O N I A L E" -> "STATOPATRIMONIALE"."""
    if re.fullmatch(r"(?:\S ){3,}\S", testo):
        return testo.replace(" ", "")
    return testo


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
    return [sorted(g, key=lambda w: w[0]) for _, g in gruppi]


def _coda_importi(riga: list[tuple]) -> int:
    """Indice del primo token della coda di importi (euro compresi) della riga."""
    k = len(riga)
    while k > 0:
        t = str(riga[k - 1][4]).strip()
        if _importo(t) is not None or _norm(t) in _EURO or _TRABOCCATO.match(t):
            k -= 1
            continue
        break
    return k


def _colonne_pagina(righe: list[list[tuple]], precedenti: list[float] = ()) -> list[float]:
    """I bordi destri delle colonne di importi della pagina, da sinistra. Una colonna della pagina
    precedente che prosegue qui (stesso bordo destro) resta una colonna anche se la pagina, corta,
    ne porta meno di ``_MIN_IMPORTI_COLONNA``."""
    bordi = sorted(float(w[2]) for r in righe for w in r[_coda_importi(r):]
                   if _importo(str(w[4])) is not None and float(w[0]) > 150)
    gruppi: list[list[float]] = []
    for x in bordi:
        if gruppi and x - gruppi[-1][-1] <= _TOL_COLONNA:
            gruppi[-1].append(x)
        else:
            gruppi.append([x])
    return [max(g) for g in gruppi if len(g) >= _MIN_IMPORTI_COLONNA
            or any(abs(max(g) - c) <= _TOL_COLONNA and abs(min(g) - c) <= _TOL_COLONNA
                   for c in precedenti)]


def _margine_ripetuto(documento: fitz.Document) -> list[set[int]]:
    """Per pagina, gli indici delle righe fisiche d'intestazione o di piede.
    Un'intestazione si ripete identica, numeri compresi, alla stessa altezza su un'altra pagina
    (ragione sociale, codice fiscale, "31 DICEMBRE 2025"): sono tali le righe cosi' ripetute che
    stanno nella fascia di margine, o nel blocco contiguo di righe ripetute che parte dal bordo
    della pagina. Il blocco si ferma alla prima riga di prospetto (intestazione di sezione o voce
    di legge)."""
    pagine = []
    for pagina in documento:      # (testo, centro y, y0, y1, testo originale) per riga
        altezza = float(pagina.rect.height)
        righe = []
        for r in _righe_pagina(pagina):
            y0, y1 = min(w[1] for w in r), max(w[3] for w in r)
            testo = " ".join(str(w[4]) for w in r)
            righe.append((_norm(testo), (y0 + y1) / 2, y0, y1, testo))
        pagine.append((altezza, righe))

    def ripetuta(numero: int, chiave: str, y: float) -> bool:
        return any(n != numero and any(c == chiave and abs(yy - y) <= 2.0 for c, yy, *_ in righe)
                   for n, (_, righe) in enumerate(pagine))

    def prospetto(testo: str) -> bool:
        forma = _forma(testo)
        return bool(_intestazione(testo)) or (bool(forma) and _strutturale(forma))

    out: list[set[int]] = []
    for numero, (altezza, righe) in enumerate(pagine):
        via: set[int] = set()
        for ordine in (range(len(righe)), range(len(righe) - 1, -1, -1)):
            for k in ordine:
                chiave, y, *_ , testo = righe[k]
                if prospetto(testo) or not ripetuta(numero, chiave, y):
                    break
                via.add(k)
        for k, (chiave, y, y0, y1, testo) in enumerate(righe):
            if (y1 <= _FASCIA_MARGINE * altezza or y0 >= (1 - _FASCIA_MARGINE) * altezza) \
                    and not _intestazione(testo) \
                    and any(c == chiave for n, (_, rr) in enumerate(pagine) if n != numero
                            for c, *_ in rr):
                via.add(k)
        out.append(via)
    return out

def _anni_intestazione(righe: list[list[tuple]], colonne: list[float]) -> dict[int, int]:
    """Colonna -> anno, dalle intestazioni ("2025", "31/12/2025", "Esercizio 2025") che stanno
    sopra una colonna di importi."""
    out: dict[int, int] = {}
    for r in righe:
        riga: dict[int, list[int]] = {}
        for w in r:
            m = _DATA.match(str(w[4]).strip())
            if not m or not colonne:
                continue
            centro = (float(w[0]) + float(w[2])) / 2
            i = min(range(len(colonne)), key=lambda i: abs(float(w[2]) - colonne[i]))
            if abs(float(w[2]) - colonne[i]) <= 70 or abs(centro - colonne[i]) <= 70:
                riga.setdefault(i, []).append(int(m.group(1)))
        # due date sopra la stessa colonna: e' una frase ("periodo dal 01/01/2025 al
        # 31/12/2025"), non l'intestazione delle colonne
        if any(len(v) > 1 for v in riga.values()):
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
    m = _RE_TOTALE_CON_CODICE.match(t)
    if m:
        t, n = m.group(1), _norm(m.group(1))
    for rx, forma in _CALCOLATI:
        if rx.match(n):
            return forma
    if n.startswith("totale"):
        # "Totale attivo", "TOTALE STATO PATRIMONIALE - ATTIVO"; mai "Totale attivo circolante"
        m_sp = re.match(r"^totale (?:(?:dello )?stato patrimoniale\W*)?(attivo|attivita|passivo|passivita)\b"
                        r"(?!\s*circolant)", n)
        if m_sp and len(n) < 50:
            return "Totale attivo" if m_sp.group(1).startswith("attiv") else "Totale passivo"
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
        s = _scadenza(resto)
        if s:
            return s
        if m.group(3) and not m.group(2):
            return resto        # "d5) da altri": dettaglio numerato della lettera d), non una lettera
        suff = f"-{m.group(2)}" if m.group(2) else ""
        return f"{m.group(1)}{suff}) {resto}"
    if _SCADENZA.match(t):
        return _scadenza(t)
    return t


_PAROLE_TESTATA = {"al", "anno", "esercizio", "esercizi", "bilancio", "periodo", "differenza",
                   "diff", "diff.", "scost", "scost.", "scostamento", "variazione", "var", "var.",
                   "%", "euro", "importi", "in", "valori", "corrente", "precedente", "consuntivo"}


def _e_testata_colonne(didascalia: str) -> bool:
    """Una riga d'intestazione delle colonne: solo parole di testata, date e anni."""
    parole = [p for p in _norm(didascalia).replace("/", " ").split() if p]
    return bool(parole) and all(p in _PAROLE_TESTATA or re.fullmatch(r"[\d\-./]+", p)
                                for p in parole)


def _intestazione(didascalia: str) -> list[str]:
    """Le righe di sezione ("STATO PATRIMONIALE - ATTIVO", "Passivo e netto", "CONTO ECONOMICO")
    nella forma del lettore: una lista vuota se non e' un'intestazione."""
    n = _norm(_ricompatta_spaziato(didascalia))
    # le date e gli anni delle colonne stampati sulla stessa riga del titolo
    n = re.sub(r"\b(?:\d{2}[-/.]\d{2}[-/.])?20\d{2}\b", " ", n)
    n = re.sub(r"\b(?:al|esercizio|bilancio al)\s*$", " ", n.strip())
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
    grezze: list[tuple[int, str, list[Optional[Decimal]]]] = []
    anni_doc: dict[int, int] = {}
    n_col = 0
    ripetute = reso._ripetute(documento)
    margini = _margine_ripetuto(documento)
    colonne: list[float] = []
    for numero, pagina in enumerate(documento):
        tutte = _righe_pagina(pagina)
        righe = [r for k, r in enumerate(tutte) if k not in margini[numero]]
        colonne = _colonne_pagina(righe, colonne)
        altezza = float(pagina.rect.height)
        lette = []
        for r in righe:
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
                y0, y1 = min(w[1] for w in r), max(w[3] for w in r)
                nel_margine = y1 <= _FASCIA_MARGINE * altezza or y0 >= (1 - _FASCIA_MARGINE) * altezza
                if nel_margine and not _intestazione(didascalia) \
                        and reso._chiave_ripetuta(didascalia) in ripetute:
                    continue
                if _PIEDE.search(_norm(didascalia)) or re.fullmatch(r"\d{1,3}", didascalia.strip()):
                    continue
            celle = _celle(parole)
            if con_importi and len(celle) == 2 and reso._enumeratore(_forma(celle[0]) or "") \
                    and not _forma_strutturale(celle[1]):
                # voce e sotto-voce in due celle della stessa riga ("15) proventi da
                # partecipazioni ... da imprese controllate"): due righe, l'importo e' della seconda
                lette.append((celle[0], [None] * len(colonne), set()))
                lette.append((celle[1], per_col, traboccate))
                continue
            lette.append((didascalia, per_col, traboccate))
        if not colonne:
            for didascalia, _, _ in lette:
                grezze.append((numero, didascalia, []))
            continue
        colonne, lette = _parziali(colonne, lette)
        # ruoli delle colonne della pagina: percentuale, differenza, esercizio
        valori = [pc for _, pc, _ in lette if any(v is not None for v in pc)]
        ruoli: list[int] = []
        for i in range(len(colonne)):
            col = [r[i] for r in valori if r[i] is not None]
            if col and sum(1 for v in col if v.as_tuple().exponent == -3) >= max(1, len(col) // 2):
                continue
            if len(ruoli) >= 2 and _e_differenza(valori, i, ruoli[0], ruoli[1]):
                continue
            ruoli.append(i)
        ruoli = ruoli[:2]
        n_col = max(n_col, len(ruoli))
        anni_pag = _anni_intestazione(tutte, colonne)     # l'anno sta spesso nell'intestazione
        for pos, i in enumerate(ruoli):
            if i in anni_pag and pos not in anni_doc:
                anni_doc[pos] = anni_pag[i]
        for didascalia, pc, traboccate in lette:
            if traboccate & set(ruoli):
                raise reso._Rifiuto("importo_illeggibile", didascalia=didascalia)
            grezze.append((numero, didascalia, [pc[i] for i in ruoli]))
    if not n_col:
        raise reso._Rifiuto("colonne_non_trovate")

    grezze = _unisci_a_capo(grezze)
    righe_out: list[reso._Riga] = []
    radici_viste: set[str] = set()
    iniziato = finito = False
    for indice, (numero, didascalia, valori) in enumerate(grezze):
        if finito:
            break
        ha_importi = any(v is not None for v in valori)
        testate = [] if ha_importi else _intestazione(didascalia)
        if testate:
            for t in testate:
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
        parole = didascalia.split()
        if not parole and ha_importi and righe_out and righe_out[-1].valori \
                and righe_out[-1].pagina == numero:
            # importi senza didascalia sotto righe con importi: il totale, non intitolato, della
            # voce aperta (la piu' vicina voce di legge senza importi); l'albero lo verifica.
            # Uguali alla riga sopra, ne sono la ripetizione (il netto della voce): si saltano.
            # Seguiti da altre righe della stessa voce ("Meno: fondo svalutazione"), sono un
            # subtotale intermedio, non il totale della voce: si saltano anche loro.
            pieni_qui = ([v if v is not None else _ZERO for v in valori] + [_ZERO] * n_col)[:n_col]
            if pieni_qui == list(righe_out[-1].valori):
                continue
            seguente = grezze[indice + 1][1] if indice + 1 < len(grezze) else ""
            if seguente.strip() and not _intestazione(seguente) \
                    and not _forma_strutturale(seguente):
                continue
            titolo = next((r.didascalia for r in reversed(righe_out)
                           if not r.valori and reso._enumeratore(r.didascalia)), None)
            if titolo:
                didascalia = "Totale " + titolo
                parole = didascalia.split()
        # un codice conto in testa non e' una voce di legge; "18-19 TOTALE RETT. ..." si': la
        # formula del totale ha la forma di un codice, ma e' seguita da "totale"
        conto = bool(parole and _CODICE_CONTO.match(parole[0])
                     and not (len(parole) > 1 and _norm(parole[1]) == "totale"))
        forma = didascalia if conto else _forma(didascalia)
        if forma is None:
            continue
        pieni = ([v if v is not None else _ZERO for v in valori] + [_ZERO] * n_col)[:n_col] \
            if ha_importi else []
        righe_out.append(reso._Riga(forma, pieni, numero))
        if ha_importi and reso._calcolato(forma) == "utile" and "Conto economico" in radici_viste:
            finito = True
    righe_out = _numerazione_che_riparte(righe_out)
    righe_out = _togli_dettaglio_conti(righe_out)
    righe_out = _titoli_con_totale(righe_out)
    righe_out = _sezioni_vuote(righe_out)
    anni = [anni_doc[i] for i in range(n_col) if i in anni_doc]
    if len(anni) != n_col:
        anni = anni[:1] if anni else []
    return righe_out, n_col, anni


def _parziali(colonne: list[float], lette: list) -> tuple[list[float], list]:
    """Colonna dei parziali: due colonne adiacenti che non sono mai piene sulla stessa riga sono
    un esercizio solo, stampato su due incolonnamenti (parziali a sinistra, totali a destra). Le
    righe col solo parziale sono il dettaglio della voce ("Costi", "(Ammortamenti)", i conti),
    gia' compreso nel totale della voce: si tolgono. Una voce di legge stampata nella colonna dei
    parziali resta, con l'importo spostato nella colonna dei totali."""
    i = 0
    while i + 1 < len(colonne):
        j = i + 1
        a = sum(1 for _, pc, _ in lette if pc[i] is not None)
        b = sum(1 for _, pc, _ in lette if pc[j] is not None)
        insieme = sum(1 for _, pc, _ in lette if pc[i] is not None and pc[j] is not None)
        if insieme or not a or not b or a + b < _MIN_IMPORTI_COLONNA:
            i += 1
            continue
        nuove = []
        for didascalia, pc, traboccate in lette:
            if pc[i] is not None:
                if not _forma_strutturale(didascalia):
                    continue
                pc = pc[:j] + [pc[i]] + pc[j + 1:]
            nuove.append((didascalia, pc[:i] + pc[i + 1:],
                          {t - 1 if t > i else t for t in traboccate if t != i}))
        lette = nuove
        colonne = colonne[:i] + colonne[i + 1:]
    return colonne, lette


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
    RETTIFICHE DI VALORE DI") e la riga sotto, sulla stessa pagina, che la completa e porta gli
    importi, o che comincia in minuscolo, sono una riga sola."""
    out: list = []
    for numero, didascalia, valori in grezze:
        if out:
            p_num, p_did, p_val = out[-1]
            senza = not any(v is not None for v in p_val)
            continua = didascalia[:1].islower() and not _forma_strutturale(didascalia)
            if (p_num == numero and senza and p_did and not _intestazione(p_did)
                    and not _intestazione(didascalia) and not _e_testata_colonne(p_did)
                    and reso._frase_aperta(p_did)
                    and not _forma_strutturale(didascalia)):
                out[-1] = (numero, p_did + " " + didascalia, valori)
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


def _numerazione_che_riparte(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Dentro una voce a lettera ("a) da crediti iscritti nelle immobilizzazioni"), una
    numerazione araba che riparte sotto il numero della voce aperta ("1) da imprese controllate"
    sotto 16)) e' il dettaglio della lettera, non una nuova voce dello schema: perde il numero
    e resta una riga della lettera. La numerazione dello schema non torna mai indietro."""
    out: list[reso._Riga] = []
    arabo_aperto: Optional[int] = None
    in_lettera = False
    for r in righe:
        e = reso._enumeratore(r.didascalia)
        if r.didascalia in ("Stato patrimoniale", "Attivo", "Passivo", "Conto economico") \
                or (e and e[0] in ("L", "R")):
            arabo_aperto, in_lettera = None, False
        elif e and e[0] == "N":
            numero = int(re.match(r"\d+", e[1][0]).group())
            if arabo_aperto is not None and numero < arabo_aperto:
                testo = re.sub(r"^\S+\)\s*", "", r.didascalia)
                out.append(reso._Riga(testo, r.valori, r.pagina))
                continue
            arabo_aperto, in_lettera = numero, False
        elif e and e[0] == "l":
            in_lettera = True
        out.append(r)
    return out


def _strutturale(didascalia: str) -> bool:
    return bool(reso._enumeratore(didascalia) or reso._e_totale(didascalia)
                or reso._scadenza(didascalia) or reso._calcolato(didascalia)
                or didascalia in ("Stato patrimoniale", "Attivo", "Passivo", "Conto economico"))


def _togli_dettaglio_conti(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Sotto una voce con importo, le righe senza enumeratore che sommano esattamente a
    quell'importo sono i conti che la compongono: la voce li ha gia' contati. Vale anche con le
    componenti di segno opposto stampate positive ("17-bis) utili e perdite su cambi (97)":
    "utili su cambi 29", "perdite su cambi 126"), purche' uno stesso segno per riga chiuda ogni
    colonna e la prima riga sia additiva."""
    out: list[reso._Riga] = []
    i = 0
    while i < len(righe):
        r = righe[i]
        out.append(r)
        i += 1
        if not r.valori or not reso._enumeratore(r.didascalia):
            continue
        j = i
        while j < len(righe) and righe[j].valori and not _strutturale(righe[j].didascalia):
            j += 1
        if j == i:
            continue
        if _compone(righe[i:j], list(r.valori)):
            i = j
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


_MAX_RIGHE_CON_SEGNO = 8


def _compone(righe: list[reso._Riga], voce: list[Decimal]) -> bool:
    colonne = range(len(voce))
    if [sum((f.valori[c] for f in righe), _ZERO) for c in colonne] == voce:
        return True
    n = len(righe)
    if n < 2 or n > _MAX_RIGHE_CON_SEGNO:
        return False
    for maschera in range(1, 1 << (n - 1)):        # la prima riga resta sempre additiva
        segni = [1] + [-1 if maschera >> (k - 1) & 1 else 1 for k in range(1, n)]
        if all(sum((s * f.valori[c] for s, f in zip(segni, righe)), _ZERO) == voce[c]
               for c in colonne):
            return True
    return False


def _livello(didascalia: str) -> Optional[int]:
    e = reso._enumeratore(didascalia)
    return reso._LIVELLO[e[0]] if e else None


def _nome_totale(didascalia: str) -> str:
    """Il totale di una voce col nome di legge, senza il suo enumeratore ("C) Proventi ed oneri
    finanziari" -> "Totale proventi e oneri finanziari"): cosi' lo riconoscono i controlli."""
    testo = re.sub(r"^(?:[A-E]\)|[IVX]+ -|\d+(?:-\w+)?\)|[a-z](?:-\w+)?\))\s*", "", didascalia)
    return _forma("Totale " + testo) or ("Totale " + didascalia)


def _titoli_con_totale(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Una voce che stampa il proprio totale sul titolo ed e' seguita da sotto-voci piu' profonde
    (o da righe di scadenza) e' un'intestazione: il suo importo diventa il totale che chiude il
    gruppo, verificato come ogni altro sulle sotto-voci. Se il gruppo ha gia' il suo totale
    stampato, uguale, il titolo perde solo l'importo."""
    out: list[reso._Riga] = []
    pendenti: list[tuple[int, reso._Riga]] = []      # (livello, titolo) in attesa di chiusura

    def chiudi_fino(livello: Optional[int]):
        while pendenti and (livello is None or pendenti[-1][0] >= livello):
            _, titolo = pendenti.pop()
            out.append(reso._Riga(_nome_totale(titolo.didascalia), titolo._totale, titolo.pagina))

    for k, r in enumerate(righe):
        liv = _livello(r.didascalia)
        if r.didascalia in ("Stato patrimoniale", "Attivo", "Passivo", "Conto economico") \
                or reso._calcolato(r.didascalia):
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
                    # uno zero sul titolo non e' un totale: e' il titolo stampato con la cella
                    # vuota a zero; le sotto-voci le verificano i totali sopra
                    r._totale = totale
                    pendenti.append((liv, r))
    chiudi_fino(None)
    return out


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
        return reso.estrai_da_righe(documento, righe, colonne, anni, vuote_zero=True,
                                    eredita_dal_padre=True, tolleranza=_tolleranza(righe))


# Documento a importi interi: ogni voce e' gia' arrotondata all'euro, e il totale stampato e'
# l'arrotondamento della somma vera, non la somma degli arrotondati. Lo scarto resta sotto il
# tappo dichiarato del percorso snello (10 euro), che poi lo misura e lo dichiara.
_TOLLERANZA_INTERI = Decimal("5")


def _tolleranza(righe: list[reso._Riga]) -> Decimal:
    valori = [v for r in righe for v in r.valori]
    if valori and all(v == v.to_integral_value() for v in valori):
        return _TOLLERANZA_INTERI
    return _ZERO
