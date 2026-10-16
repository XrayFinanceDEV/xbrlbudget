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
    (re.compile(r"^(?:totale\s+)?diff(?:erenza|\.)?\s+(?:tra\s+)?(?:i\s+)?valor[ei]\s*(?:e|-)\s*cost[io]"),
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
    """Indice del primo token della coda di importi (euro compresi) della riga."""
    k = len(riga)
    while k > 0:
        t = str(riga[k - 1][4]).strip()
        if _importo(t) is not None or _norm(t) in _EURO:
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
                out.setdefault(i, int(m.group(1)))
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


_SCADENZA_IN_CODA = re.compile(r"\besigibil[ie]\s+(entro|oltre)\b", re.I)


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
            and not re.match(r"^(?:utile|perdita)[^,]*(?:portat|ripianat)", n)):
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
        if resto.startswith(","):
            return t            # "c), d), e) ...": riga di raggruppamento, gia' nella forma giusta
        s = _scadenza(resto) or _scadenza_in_coda(resto)
        if s:
            return s
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


def _in_colonna(w: tuple, colonne: list[float]) -> bool:
    return bool(colonne) and min(abs(float(w[2]) - c) for c in colonne) <= _TOL_COLONNA


def _testate_ripetute(documento: fitz.Document) -> set[tuple[int, int]]:
    """(pagina, indice di riga) delle righe d'intestazione o di piede ripetute: senza importi in
    colonna, sopra la prima o sotto l'ultima riga con importi della pagina (o nella fascia di
    margine), e uguali - a meno delle cifre - su almeno due pagine ("BILANCIO SCHEMA XBRL ALMA
    S.R.L.", "SCD AVVOCATI Codice fiscale 02780840993"). Una riga del prospetto (voce, titolo
    di sezione) non e' mai un'intestazione ripetuta."""
    candidate: list[tuple[int, int, str]] = []
    pagine_per_chiave: dict[str, set[int]] = {}
    for numero, pagina in enumerate(documento):
        righe = _righe_pagina(pagina)
        colonne = _colonne_pagina(righe)
        altezza = float(pagina.rect.height)
        con = [any(_importo(str(w[4])) is not None and _in_colonna(w, colonne)
                   for w in r[_coda_importi(r):]) for r in righe]
        if not any(con):
            continue
        prima, ultima = con.index(True), len(con) - 1 - con[::-1].index(True)
        for i, r in enumerate(righe):
            if con[i]:
                continue
            y0, y1 = min(w[1] for w in r), max(w[3] for w in r)
            nel_margine = y1 <= _FASCIA_MARGINE * altezza or y0 >= (1 - _FASCIA_MARGINE) * altezza
            if not (i < prima or i > ultima or nel_margine):
                continue
            testo = " ".join(str(w[4]) for w in r if _norm(str(w[4])) not in _EURO)
            if not testo.strip() or _intestazione(testo) or _forma_strutturale(testo):
                continue
            chiave = reso._chiave_ripetuta(testo)
            candidate.append((numero, i, chiave))
            pagine_per_chiave.setdefault(chiave, set()).add(numero)
    return {(n, i) for n, i, c in candidate if len(pagine_per_chiave[c]) >= 2}


def _leggi(documento: fitz.Document):
    """(righe, numero di colonne-esercizio, anni) oppure solleva ``reso._Rifiuto``."""
    grezze: list[tuple[int, str, list[Optional[Decimal]]]] = []
    anni_doc: dict[int, int] = {}
    n_col = 0
    ripetute = reso._ripetute(documento)
    testate_ripetute = _testate_ripetute(documento)
    for numero, pagina in enumerate(documento):
        righe = _righe_pagina(pagina)
        colonne = _colonne_pagina(righe)
        altezza = float(pagina.rect.height)
        lette = []
        for indice, r in enumerate(righe):
            if (numero, indice) in testate_ripetute:
                continue
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
    ix_con_importi = False
    for numero, didascalia, valori in grezze:
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
        forma = didascalia if parole and _CODICE_CONTO.match(parole[0]) else _forma(didascalia)
        if forma is None:
            continue
        pieni = ([v if v is not None else _ZERO for v in valori] + [_ZERO] * n_col)[:n_col] \
            if ha_importi else []
        if (reso._calcolato(forma) == "utile" and "Passivo" in radici_viste
                and "Conto economico" not in radici_viste and not ix_con_importi):
            # nel patrimonio netto, senza la sua "IX)", la riga del risultato e' la voce IX
            forma = "IX - " + forma
        if "Passivo" in radici_viste and "Conto economico" not in radici_viste:
            e = reso._enumeratore(forma)
            if e and e[0] == "R":
                ix_con_importi = e[1] == ["IX"] and ha_importi
        righe_out.append(reso._Riga(forma, pieni, numero))
        if ha_importi and reso._calcolato(forma) == "utile" and "Conto economico" in radici_viste:
            finito = True
    righe_out = _numerazione_che_riparte(righe_out)
    righe_out = _ce_a_segno_algebrico(righe_out)
    tol = _tolleranza_dettaglio(righe_out)
    righe_out = _scadenze_con_totale(righe_out, tol)
    righe_out = _togli_scadenze_di_testa(righe_out, tol)
    righe_out = _togli_dettaglio_conti(righe_out, tol)
    righe_out = _titoli_con_totale(righe_out)
    anni = [anni_doc[i] for i in range(n_col) if i in anni_doc]
    if len(anni) != n_col:
        anni = anni[:1] if anni else []
    if (n_col == 2 and len(anni) == 2
            and all(r.valori[0] == 0 for r in righe_out if r.valori)
            and any(r.valori[1] != 0 for r in righe_out if r.valori)):
        # la prima colonna-esercizio e' stampata tutta a zero (l'esercizio non e' ancora stato
        # contabilizzato): non e' un bilancio; il bilancio del documento e' la seconda colonna,
        # col suo anno d'intestazione
        righe_out = [reso._Riga(r.didascalia, r.valori[1:], r.pagina) if r.valori else r
                     for r in righe_out]
        n_col, anni = 1, anni[1:]
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
    salta = False
    for indice, (numero, didascalia, valori) in enumerate(grezze):
        if salta:
            salta = False
            continue
        con = any(v is not None for v in valori)
        if out:
            p_num, p_did, p_val = out[-1]
            senza = not any(v is not None for v in p_val)
            # didascalia su due righe con gli importi centrati fra le due ("C) TRATTAMENTO DI
            # FINE RAPPORTO DI LAVORO" / importi senza testo / "SUBORDINATO"): una riga sola,
            # ma solo se la riga sotto gli importi e' davvero il seguito della didascalia (non
            # una voce, non un conto, senza importi); un importo senza testo seguito da una voce
            # e' il totale di un gruppo, e resta fuori come prima
            seguito = grezze[indice + 1] if indice + 1 < len(grezze) else None
            if (p_num == numero and senza and con and not didascalia.strip() and p_did.strip()
                    and not _intestazione(p_did) and not _e_testata_colonne(p_did)
                    and seguito is not None and seguito[0] == numero
                    and not any(v is not None for v in seguito[2]) and seguito[1].strip()
                    and not _forma_strutturale(seguito[1]) and not _intestazione(seguito[1])
                    and not _e_conto(seguito[1])):
                out[-1] = (numero, p_did + " " + seguito[1], valori)
                salta = True
                continue
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
            if in_lettera and arabo_aperto is not None and numero < arabo_aperto:
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


def _e_conto(didascalia: str) -> bool:
    parole = didascalia.split()
    return bool(parole) and bool(_CODICE_CONTO.match(parole[0]))


def _tolleranza_dettaglio(righe: list[reso._Riga]) -> Decimal:
    """Lo scarto ammesso fra una voce e i conti che la compongono: quello dei totali del
    documento. In un documento che stampa le voci di legge all'euro (anche quando i conti
    portano i centesimi) la voce e' l'arrotondamento della somma dei conti, non la somma degli
    arrotondati; altrimenti zero."""
    voci = [v for r in righe if _strutturale(r.didascalia) for v in r.valori]
    if voci and all(v == v.to_integral_value() for v in voci):
        return _TOLLERANZA_INTERI
    return _ZERO


def _uguali(a, b, tol: Decimal) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _scompone(bersaglio: list[Decimal], valori: list[list[Decimal]], tol: Decimal) -> bool:
    """I valori (nell'ordine di stampa) sono il dettaglio del bersaglio: la loro somma lo
    riproduce, contando ogni riga una volta sola. Un conto seguito dai sottoconti che lo
    compongono esattamente (mastro e foglie) conta una volta: si sommano i mastri OPPURE le
    foglie, mai entrambi, ed e' il totale stampato - non il codice - a dire chi e' il mastro.
    Il dettaglio puo' essere stampato col segno della sezione (dare/avere): la somma vale anche
    cambiata di segno, ma con un segno solo per tutte le colonne."""
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
    return any(_uguali(s, bersaglio, tol) or _uguali(s, [-x for x in bersaglio], tol)
               for s in stati[n])


def _corsa_dettaglio(righe: list[reso._Riga], i: int) -> int:
    """Fine (esclusa) della corsa di righe di dettaglio che comincia in i: righe senza
    enumeratore, con importi; una riga senza importi vi rientra solo se la corsa continua dopo
    di lei (la seconda riga di una didascalia di conto andata a capo)."""
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
            if _scompone(list(r.valori), _valori_corsa(righe[i:taglio]), tol):
                i = taglio
                break
    return out


def _ce_a_segno_algebrico(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Conto economico stampato col segno algebrico (i costi negativi): lo si riconosce dal
    documento stesso - il totale dei costi della produzione e' negativo e la differenza A - B
    stampata e' la SOMMA dei due totali stampati. Allora ogni riga dei costi (B, 17, 19, 20)
    cambia segno, totali compresi, e torna nella convenzione dello schema di legge; i
    risultati intermedi (differenza, C, D, risultato prima delle imposte, utile) sono gia'
    con il segno giusto e restano."""
    try:
        inizio = next(k for k, r in enumerate(righe) if r.didascalia == "Conto economico")
    except StopIteration:
        return righe
    diff = next((k for k in range(inizio, len(righe))
                 if reso._calcolato(righe[k].didascalia) == "differenza" and righe[k].valori), None)
    if diff is None or diff - 1 <= inizio:
        return righe
    tot_b = righe[diff - 1]
    inizio_b = next((k for k in range(inizio, diff) if (reso._enumeratore(righe[k].didascalia) or ("", ))[0] == "L"
                     and reso._enumeratore(righe[k].didascalia)[1] == ["B"]), None)
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
        # le voci dei costi sono positive e solo il totale porta il meno ("Totale (B)
        # -33.155.832"): e' il segno della sottrazione stampato sul totale, non sulle voci
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


def _livello_o_none(r: reso._Riga) -> Optional[int]:
    e = reso._enumeratore(r.didascalia)
    return reso._LIVELLO[e[0]] if e else None


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
        liv = _livello_o_none(r)
        if liv is None or r.valori:
            continue
        j = i
        while j < len(righe) and reso._scadenza(righe[j].didascalia) and righe[j].valori:
            j += 1
        if j == i or j >= len(righe):
            continue
        dopo = _livello_o_none(righe[j])
        if dopo is None or dopo <= liv:
            continue
        somma = [sum((f.valori[c] for f in righe[i:j]), _ZERO) for c in range(len(righe[i].valori))]
        for f in righe[j:]:
            lf = _livello_o_none(f)
            if (lf is not None and lf <= liv) or f.didascalia in ("Attivo", "Passivo", "Conto economico") \
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
            if fine > i + 1 and fine < len(righe):
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
            out.append(reso._Riga("Totale " + titolo.didascalia, titolo._totale, titolo.pagina))

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
