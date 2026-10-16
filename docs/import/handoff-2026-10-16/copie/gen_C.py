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
# Subtotali calcolati, comunque abbreviati: alla didascalia che il cuore del lettore riconosce.
_CALCOLATI = (
    (re.compile(r"^(?:totale\s+)?diff(?:erenza|\.)?\s+(?:tra\s+)?(?:i\s+)?valor[ei]\s*(?:e|-)\s*costi"),
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
        sp = r"^totale (?:stato patrimoniale\s*[-–]?\s*)?"
        if re.match(sp + r"(?:attivo|attivita)\b(?! circolante| finanziar)", n) and len(n) < 45:
            return "Totale attivo"
        if re.match(sp + r"(?:passivo|passivita)\b", n):
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
    # il titolo con la sua lettera ("A) STATO PATRIMONIALE - ATTIVO", "E) CONTO ECONOMICO")
    n = re.sub(r"^[a-z]\s*\)\s*(?=stato patrimoniale|conto economico)", "", n)
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
    pagine = [_righe_pagina(p) for p in documento]
    # Le colonne del documento: un gestionale stampa ogni pagina sulla stessa griglia, e una
    # colonna che su una pagina porta pochi importi (la colonna interna delle sotto-voci) e' una
    # colonna lo stesso se il documento intero ne porta abbastanza.
    # Le righe nella fascia d'intestazione e di piede (partita IVA, numero di pagina, ripetuti su
    # ogni pagina) non fanno colonne.
    def _corpo(righe, pagina):
        h = float(pagina.rect.height)
        return [r for r in righe if min(w[1] for w in r) > _FASCIA_MARGINE * h
                and max(w[3] for w in r) < (1 - _FASCIA_MARGINE) * h]
    colonne_doc = _colonne_pagina([r for p, righe in zip(documento, pagine) for r in _corpo(righe, p)])
    for numero, pagina in enumerate(documento):
        righe = pagine[numero]
        colonne = _colonne_pagina(righe)
        bordi_pag = [float(w[2]) for r in _corpo(righe, pagina) for w in r[_coda_importi(r):]
                     if _importo(str(w[4])) is not None and float(w[0]) > 150]
        colonne = sorted(colonne + [
            c for c in colonne_doc
            if all(abs(c - x) > _TOL_COLONNA for x in colonne)
            and any(abs(c - x) <= _TOL_COLONNA for x in bordi_pag)])
        altezza = float(pagina.rect.height)
        lette = []
        centri = [(min(w[1] for w in r) + max(w[3] for w in r)) / 2 for r in righe]
        salti = sorted(b - a for a, b in zip(centri, centri[1:]) if b - a > 0.5)
        passo = salti[len(salti) // 2] if salti else 0.0
        centri_lette: list[float] = []
        for r, centro in zip(righe, centri):
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
                y0, y1 = min(w[1] for w in r), max(w[3] for w in r)
                nel_margine = y1 <= _FASCIA_MARGINE * altezza or y0 >= (1 - _FASCIA_MARGINE) * altezza
                if nel_margine and not _intestazione(didascalia) \
                        and reso._chiave_ripetuta(didascalia) in ripetute:
                    continue
                if _PIEDE.search(_norm(didascalia)) or re.fullmatch(r"\d{1,3}", didascalia.strip()):
                    continue
                # una riga senza importi stretta sotto la precedente, piu' vicina dell'interlinea
                # della pagina, e' la didascalia di quella andata a capo ("A-B) TOTALE DIFFERENZA
                # TRA VALORI E COSTI" / "DELLA PRODUZIONE"), qualunque sia la maiuscola
                # Se la riga sopra porta solo gli importi, centrati fra le due righe di una
                # didascalia spezzata ("C) TRATTAMENTO DI FINE RAPPORTO DI LAVORO" / importi /
                # "SUBORDINATO"), le tre righe sono una voce sola.
                if (lette and passo and centro - centri_lette[-1] < 0.7 * passo
                        and not _forma_strutturale(didascalia) and not _intestazione(didascalia)):
                    p_did, p_pc = lette[-1]
                    if (not p_did.strip() and len(lette) >= 2
                            and not any(v is not None for v in lette[-2][1])
                            and centri_lette[-1] - centri_lette[-2] < 0.7 * passo):
                        lette[-2] = (lette[-2][0] + " " + didascalia, p_pc)
                        del lette[-1], centri_lette[-1]
                    else:
                        lette[-1] = (p_did + " " + didascalia, p_pc)
                    continue
            celle = _celle(parole)
            if con_importi and len(celle) == 2 and reso._enumeratore(_forma(celle[0]) or "") \
                    and not _forma_strutturale(celle[1]):
                # voce e sotto-voce in due celle della stessa riga ("15) proventi da
                # partecipazioni ... da imprese controllate"): due righe, l'importo e' della seconda
                lette.append((celle[0], [None] * len(colonne)))
                lette.append((celle[1], per_col))
                centri_lette += [centro, centro]
                continue
            lette.append((didascalia, per_col))
            centri_lette.append(centro)
        if not colonne:
            for didascalia, _ in lette:
                grezze.append((numero, didascalia, []))
            continue
        # ruoli delle colonne della pagina: percentuale, differenza, esercizio
        valori = [pc for _, pc in lette if any(v is not None for v in pc)]
        ruoli: list[int] = []
        anni_pag = _anni_intestazione(righe, colonne)
        for i in range(len(colonne)):
            col = [r[i] for r in valori if r[i] is not None]
            if not col:
                continue
            if col and sum(1 for v in col if v.as_tuple().exponent == -3) >= max(1, len(col) // 2):
                continue
            if len(ruoli) >= 2 and _e_differenza(valori, i, ruoli[0], ruoli[1]):
                continue
            ruoli.append(i)
        # Due colonne vicine che non portano MAI un importo sulla stessa riga, e la cui testata
        # non dice due anni diversi, sono lo stesso esercizio: la sinistra e' la colonna interna
        # delle sotto-voci (il gestionale le rientra e stampa il loro totale nella colonna di
        # destra, su una riga senza didascalia). Due esercizi veri condividono quasi ogni riga.
        k = 0
        while k + 1 < len(ruoli):
            a, b = ruoli[k], ruoli[k + 1]
            if (anni_pag.get(a, anni_pag.get(b)) == anni_pag.get(b)
                    and not any(pc[a] is not None and pc[b] is not None for _, pc in lette)):
                for _, pc in lette:
                    if pc[a] is not None:
                        pc[b], pc[a] = pc[a], None
                del ruoli[k]
                continue
            k += 1
        ruoli = ruoli[:2]
        n_col = max(n_col, len(ruoli))
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
        forma = didascalia if parole and _CODICE_CONTO.match(parole[0]) else _forma(didascalia)
        if not parole and ha_importi:
            # importi senza didascalia sotto le sotto-voci, seguiti dalla voce successiva dello
            # schema: il totale stampato del gruppo che si chiude, verificato come ogni altro
            # totale. Se ripetono gli importi della riga sopra sono la stessa voce stampata due
            # volte; se il gruppo continua ("Meno: fondo svalutazione") sono un subtotale
            # intermedio: in entrambi i casi restano fuori, come prima.
            pieni_qui = ([v if v is not None else _ZERO for v in valori] + [_ZERO] * n_col)[:n_col]
            dopo = next((d for _, d, _ in grezze[indice + 1:] if d.strip()), "")
            if (not (righe_out and righe_out[-1].valori == pieni_qui)
                    and (not dopo or _forma_strutturale(dopo) or _intestazione(dopo))):
                forma = "Totale"
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


def _togli_dettaglio_conti(righe: list[reso._Riga]) -> list[reso._Riga]:
    """Sotto una voce con importo, le righe senza enumeratore che sommano esattamente a
    quell'importo sono i conti che la compongono: la voce li ha gia' contati."""
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
        somme = [sum((f.valori[c] for f in righe[i:j]), _ZERO) for c in range(len(r.valori))]
        if somme == list(r.valori):
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
