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
_DATA = re.compile(r"^(?:\d{2}[-/.]\d{2}[-/.])?(20\d{2})$|^\d{2}[-/.]\d{2}[-/.](\d{2})$")
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
# "15) Proventi", "15. Proventi" e anche "15)Proventi" (la parentesi attaccata al testo): il punto
# vuole lo spazio dopo, per non leggere "1.234" come un enumeratore.
_RE_ARABO = re.compile(r"^(\d{1,2})\s*-?\s*(bis|ter|quater|quinquies)?\s*(?:[\)\.]\s+|\)(?=[A-Za-z]))(.*)$", re.I)
_RE_LETTERA = re.compile(r"^([a-z])\s*-?\s*((?i:bis|ter))?(\d)?\s*\)\s*(.*)$")
# Un totale con davanti il codice della voce ("II TOTALE ...", "d-bis TOTALE ...") o la formula
# che lo calcola ("A-B TOTALE DIFF. ...", "15+16-17+-17b TOTALE ...").
_RE_TOTALE_CON_CODICE = re.compile(
    r"^(?:[A-E]|[IVX]+|\d{1,2}(?:-?(?:bis|ter|quater))?|[a-z](?:-?bis)?"
    r"|[A-E\d][A-E\d+\-±/b]*[+\-±][A-E\d+\-±/b]*)\s+(totale\b.*)$", re.I)
_SCADENZA = re.compile(r"^(?:crediti\s+|debiti\s+|importi\s+)?(?:esigibil[ie]\s+)?(entro|oltre)\b", re.I)
# Subtotali calcolati, comunque abbreviati: alla didascalia che il cuore del lettore riconosce.
_CALCOLATI = (
    (re.compile(r"^(?:totale\s+)?diff(?:erenza|\.)?\s+(?:tra\s+)?(?:i\s+)?valor[ei]\s*(?:e|-)\s*cost[oi]"),
     "Differenza tra valore e costi della produzione"),
    (re.compile(r"^(?:totale\s+)?ris(?:ultato|\.)?\s+prima\s+delle\s+imposte"),
     "Risultato prima delle imposte"),
    (re.compile(r"^totale\s+(?:diff(?:erenza|\.)?\s+)?(?:tra\s+)?proventi\s+e\s+oneri\s+finanziari"),
     "Totale proventi e oneri finanziari"),
    (re.compile(r"^totale\s+(?:delle\s+)?rett(?:ifiche|\.)"),
     "Totale delle rettifiche di valore di attivita' e passivita' finanziarie"),
    (re.compile(r"^totale\s+(?:delle\s+)?imposte"),
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
    """Indice del primo token della coda di importi (euro compresi) della riga. Una cella di
    soli asterischi ("********", il campo numerico che trabocca, tipico della percentuale) e'
    una cella della coda, non testo: non e' un importo e non ferma la lettura degli altri."""
    k = len(riga)
    while k > 0:
        t = str(riga[k - 1][4]).strip()
        if _importo(t) is not None or _norm(t) in _EURO or re.fullmatch(r"\*{2,}", t):
            k -= 1
            continue
        break
    return k


def _colonne_pagina(righe: list[list[tuple]]) -> list[float]:
    """I bordi destri delle colonne di importi della pagina, da sinistra."""
    bordi = sorted(float(w[2]) for r in righe for w in r[_coda_importi(r):]
                   if _importo(str(w[4])) is not None and float(w[0]) > 150)
    gruppi: list[list[float]] = []
    for x in bordi:
        if gruppi and x - gruppi[-1][-1] <= _TOL_COLONNA:
            gruppi[-1].append(x)
        else:
            gruppi.append([x])
    return [max(g) for g in gruppi if len(g) >= _MIN_IMPORTI_COLONNA]


def _anni_intestazione(righe: list[list[tuple]], colonne: list[float]) -> dict[int, int]:
    """Colonna -> anno, dalle intestazioni ("2025", "31/12/2025", "Esercizio 2025") che stanno
    sopra una colonna di importi."""
    out: dict[int, int] = {}
    for r in righe:
        for w in r:
            m = _DATA.match(str(w[4]).strip())
            if not m or not colonne:
                continue
            centro = (float(w[0]) + float(w[2])) / 2
            i = min(range(len(colonne)), key=lambda i: abs(float(w[2]) - colonne[i]))
            if abs(float(w[2]) - colonne[i]) <= 70 or abs(centro - colonne[i]) <= 70:
                out.setdefault(i, int(m.group(1)) if m.group(1) else 2000 + int(m.group(2)))
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


_TOTALI_SEZIONE_CE = {
    "A": "Totale valore della produzione", "B": "Totale costi della produzione",
    "C": "Totale proventi e oneri finanziari",
    "D": "Totale delle rettifiche di valore di attivita' e passivita' finanziarie",
}


def _forma(didascalia: str) -> Optional[str]:
    """La didascalia nella forma che il cuore del lettore di legge capisce; None = da saltare."""
    t = _ricompatta_spaziato(didascalia.strip())
    t = re.sub(r"^[\-–•*]+\s*", "", t)
    t = re.sub(r"\)\s*,\s*", "), ", t)          # "b) , c) da titoli" -> "b), c) da titoli"
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
        if re.match(r"^totale (attivo|attivita)(?! circolante)", n) and len(n) < 40:
            return "Totale attivo"
        if re.match(r"^totale (passivo|passivita)", n):
            return "Totale passivo"
        return "Totale" + t[6:]
    if (re.match(r"^(?:2[123]\s*[\)\.]\s*)?(?:utile|perdita|risultato)\b", n) and "esercizio" in n
            and not re.match(r"^(?:utile|perdita)[^,]*portat", n)):
        return "Utile (perdita) dell'esercizio"
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
    for numero, pagina in enumerate(documento):
        righe = _righe_pagina(pagina)
        colonne = _colonne_pagina(righe)
        altezza = float(pagina.rect.height)
        lette = []
        for r in righe:
            k = _coda_importi(r)
            importi = [w for w in r[k:] if _importo(str(w[4])) is not None]
            # un importo e' tale solo se sta in una colonna; altrimenti torna nella didascalia
            per_col: list[Optional[Decimal]] = [None] * len(colonne)
            fuori = []
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
                    and re.sub(r"^\S+\)\s*", "", _forma(celle[0])).strip() \
                    and not _forma_strutturale(celle[1]):
                # voce e sotto-voce in due celle della stessa riga ("15) proventi da
                # partecipazioni ... da imprese controllate"): due righe, l'importo e' della seconda
                lette.append((celle[0], [None] * len(colonne)))
                lette.append((celle[1], per_col))
                continue
            lette.append((didascalia, per_col))
        if not colonne:
            for didascalia, _ in lette:
                grezze.append((numero, didascalia, []))
            continue
        # ruoli delle colonne della pagina: percentuale, differenza, esercizio
        valori = [pc for _, pc in lette if any(v is not None for v in pc)]
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
        anni_pag = _anni_intestazione(righe, colonne)
        for pos, i in enumerate(ruoli):
            if i in anni_pag and pos not in anni_doc:
                anni_doc[pos] = anni_pag[i]
        for didascalia, pc in lette:
            grezze.append((numero, didascalia, [pc[i] for i in ruoli]))
    if not n_col:
        raise reso._Rifiuto("colonne_non_trovate")

    grezze = _unisci_a_capo(grezze)
    righe_out: list[reso._Riga] = []
    radici_viste: set[str] = set()
    iniziato = finito = False
    pendente: Optional[reso._Riga] = None     # totale di sezione stampato sul titolo
    for numero, didascalia, valori in grezze:
        if finito:
            break
        ha_importi = any(v is not None for v in valori)
        testate = _intestazione(didascalia)
        if ha_importi and not (testate and testate[-1] in ("Attivo", "Passivo")):
            testate = []
        if testate:
            if pendente is not None:
                righe_out.append(pendente)
                pendente = None
            if ha_importi:
                # "STATO PATRIMONIALE ATTIVO 102.750": la sezione col suo totale sul titolo; il
                # totale chiude la sezione, verificato come quello stampato in fondo
                pendente = reso._Riga("Totale " + testate[-1].lower(), ([
                    v if v is not None else _ZERO for v in valori] + [_ZERO] * n_col)[:n_col],
                    numero)
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
        if not parole and ha_importi:
            # importi senza didascalia: il totale stampato di una voce intestazione (sotto)
            righe_out.append(reso._Riga("", ([v if v is not None else _ZERO for v in valori]
                                             + [_ZERO] * n_col)[:n_col], numero))
            continue
        conto = parole and _CODICE_CONTO.match(parole[0]) and not (
            len(parole) > 1 and _norm(parole[1]) == "totale")   # "18-19 TOTALE RETT. ..."
        forma = didascalia if conto else _forma(didascalia)
        if forma is None:
            continue
        m = re.fullmatch(r"Totale\s*\(?\s*([A-D])\s*\)?", forma, re.I)
        if m and "Conto economico" in radici_viste:
            # "TOTALE (C)": il totale della sezione del conto economico, col suo nome di legge
            forma = _TOTALI_SEZIONE_CE[m.group(1).upper()]
        pieni = ([v if v is not None else _ZERO for v in valori] + [_ZERO] * n_col)[:n_col] \
            if ha_importi else []
        righe_out.append(reso._Riga(forma, pieni, numero))
        if forma in ("Totale attivo", "Totale passivo"):
            pendente = None     # la sezione stampa anche il totale in fondo
        if ha_importi and reso._calcolato(forma) == "utile" and "Conto economico" in radici_viste:
            finito = True
    if pendente is not None:
        righe_out.append(pendente)
    righe_out = _numerazione_che_riparte(righe_out)
    righe_out = _totali_senza_didascalia(righe_out)
    righe_out = _togli_dettaglio_conti(righe_out)
    righe_out = _titoli_con_totale(righe_out)
    righe_out = _imposte_come_totale(righe_out)
    righe_out = _totali_di_sezione_ce(righe_out)
    anni = [anni_doc[i] for i in range(n_col) if i in anni_doc]
    if len(anni) != n_col:
        anni = anni[:1] if anni else []
    return righe_out, n_col, anni


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
            sillaba = re.search(r"[^\W\d_]-$", p_did or "")     # "di con-" / "sumo e di merci"
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
            if in_lettera and arabo_aperto is not None and numero < arabo_aperto:
                testo = re.sub(r"^\S+\)\s*", "", r.didascalia)
                out.append(reso._Riga(testo, r.valori, r.pagina))
                continue
            arabo_aperto, in_lettera = numero, False
        elif e and e[0] == "l":
            if (out and not out[-1].valori and r.valori
                    and reso._enumeratore(out[-1].didascalia) == e):
                # "d) proventi diversi dai precedenti:" / "d) da altri 0,58": la stessa lettera
                # ripetuta subito sotto la voce aperta e' il suo dettaglio, non una voce sorella
                out.append(reso._Riga(re.sub(r"^\S+\)\s*", "", r.didascalia), r.valori, r.pagina))
                continue
            in_lettera = True
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
            testo = re.sub(r"^\S+\)\s*", "", r.didascalia)
            out.append(reso._Riga(r.didascalia, [], r.pagina))
            out.append(reso._Riga(testo, r.valori, r.pagina))
            out.append(reso._Riga(_totale_di(r.didascalia), r.valori, r.pagina))
            continue
        out.append(r)
    return out


def _totale_di(didascalia: str) -> str:
    """Il totale di una voce intestazione, con il nome che il lettore di legge riconosce:
    "C) Proventi e oneri finanziari" -> "Totale proventi e oneri finanziari", "20) Imposte sul
    reddito" -> "Totale delle imposte sul reddito dell'esercizio"."""
    testo = re.sub(r"^\S+?\)\s*|^[IVX]+ - ", "", didascalia)
    return _forma("Totale " + testo) or "Totale " + didascalia


def _totali_senza_didascalia(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Una riga di soli importi, senza didascalia, chiude la voce intestazione aperta piu'
    interna (una voce con enumeratore stampata senza importi: "22) Imposte sul reddito" seguita
    dalle sue lettere, poi gli importi del totale da soli). Diventa "Totale <voce>" e si verifica
    sulle sotto-voci come ogni totale stampato; una riga che non ha una voce aperta da chiudere
    non e' una riga."""
    out: list[reso._Riga] = []
    aperte: list[tuple[int, reso._Riga]] = []
    for r in righe:
        if r.didascalia == "":
            if out and out[-1].valori == r.valori:
                continue        # ripete gli importi della riga sopra: niente di nuovo
            if out and out[-1].didascalia and not out[-1].valori \
                    and (_livello(out[-1].didascalia) is not None
                         or reso._scadenza(out[-1].didascalia)):
                # subito sotto la voce senza importi: sono i suoi, stampati a capo
                if aperte and aperte[-1][1] is out[-1]:
                    aperte.pop()
                out[-1] = reso._Riga(out[-1].didascalia, r.valori, out[-1].pagina)
                continue
            if aperte:
                _, titolo = aperte.pop()
                out.append(reso._Riga(_totale_di(titolo.didascalia), r.valori, r.pagina))
            continue
        if r.didascalia in ("Stato patrimoniale", "Attivo", "Passivo", "Conto economico") \
                or reso._calcolato(r.didascalia) or reso._e_totale(r.didascalia):
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


def _strutturale(didascalia: str) -> bool:
    return bool(reso._enumeratore(didascalia) or reso._e_totale(didascalia)
                or reso._scadenza(didascalia) or reso._calcolato(didascalia)
                or didascalia in ("Stato patrimoniale", "Attivo", "Passivo", "Conto economico"))


def _somma_righe(righe: list[reso._Riga], colonne: int) -> list[Decimal]:
    return [sum((f.valori[c] for f in righe), _ZERO) for c in range(colonne)]


def _radici_dettaglio(righe: list[reso._Riga], colonne: int) -> list[reso._Riga]:
    """Le righe di primo livello di un dettaglio a due piani: una riga seguita da righe
    consecutive che la sommano esattamente in ogni colonna ("Costo storico 1.781" / i due conti
    1.658 + 123) e' il loro subtotale, e le righe che la sommano non sono un'altra volta."""
    radici: list[reso._Riga] = []
    i = 0
    while i < len(righe):
        r = righe[i]
        radici.append(r)
        i += 1
        for m in range(i + 1, len(righe) + 1):
            if _somma_righe(righe[i:m], colonne) == list(r.valori):
                i = m
                break
    return radici


def _togli_dettaglio_conti(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Sotto una voce con importo, le righe senza enumeratore che sommano esattamente a
    quell'importo sono i conti che la compongono: la voce li ha gia' contati. Il dettaglio
    puo' avere due piani (subtotale e i suoi conti, "altri 1.665" / i conti di "altri"): vale
    se le righe di primo livello sommano alla voce, in ogni colonna."""
    out: list[reso._Riga] = []
    i = 0
    while i < len(righe):
        r = righe[i]
        out.append(r)
        i += 1
        if not r.valori or not (reso._enumeratore(r.didascalia) or reso._scadenza(r.didascalia)):
            continue
        j = i
        while j < len(righe) and righe[j].valori and not _strutturale(righe[j].didascalia):
            j += 1
        if j == i:
            continue
        colonne = len(r.valori)
        if _somma_righe(righe[i:j], colonne) == list(r.valori) \
                or _somma_righe(_radici_dettaglio(righe[i:j], colonne), colonne) == list(r.valori):
            i = j
    return out


def _livello(didascalia: str) -> Optional[int]:
    e = reso._enumeratore(didascalia)
    return reso._LIVELLO[e[0]] if e else None


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
            out.append(reso._Riga(_totale_di(titolo.didascalia), titolo._totale, titolo.pagina))

    for k, r in enumerate(righe):
        liv = _livello(r.didascalia)
        if r.didascalia in ("Stato patrimoniale", "Attivo", "Passivo", "Conto economico") \
                or reso._calcolato(r.didascalia) \
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
                r._totale = list(r.valori)
                r.valori = []
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
        primo = reso.estrai_da_righe(documento, righe, colonne, anni, vuote_zero=True,
                                     eredita_dal_padre=True, tolleranza=_tolleranza(righe))
        if primo["adottabile"]:
            return primo
        variante = _segni_come_contributo(righe)
        if variante is None:
            return primo
        secondo = reso.estrai_da_righe(documento, variante, colonne, anni, vuote_zero=True,
                                       eredita_dal_padre=True, tolleranza=_tolleranza(variante))
        return secondo if secondo["adottabile"] else primo


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
