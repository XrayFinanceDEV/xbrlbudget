"""Il Documento dalle tabelle di MinerU: il secondo ingresso, per le scansioni senza text layer (Task 7).

MinerU consegna ogni riga gia' divisa in celle (`mineru_adapter._parse_table_html`, con colspan espansi). Le colonne
vengono dall'intestazione della tabella (date e anni come il passo 3, parole di ruolo come «Differenza», «%»): la
colonna di ogni importo e' la posizione della sua cella, mai «gli ultimi due» (C4, `_row_label_and_values`).
Un'intestazione vale solo con importi sotto le sue colonne; senza date vale solo in un documento che non ne stampa
(un bilancio di verifica: «Conto | Descrizione | Importo»). Una tabella senza intestazione eredita quella prima (il
prospetto che continua sulla pagina dopo), allineata se MinerU ha aggiunto o tolto una cella; una tabella che apre
con un'intestazione non di colonne di valori e' della nota, e con lei il suo seguito (`schema_legge_generico.
_grezze_mineru`): non da' righe, si dichiara in `profilo.tabelle_nota`. Le sezioni contrapposte (un'intestazione
con due lati) danno righe L e R, con colonne per lato.

Non c'e' geometria: le regole del profilo (forme dei codici, negativi, decimali, colonne a interi, sezioni, tipo) si
applicano a righe fisiche sintetiche, una per riga di tabella e lato, con la descrizione a sinistra di x=150 e ogni
importo sul bordo destro della sua colonna. `Riga.x` e' 0 per ogni riga con testo: l'HTML non stampa rientri, e la
parentela la decidono le somme (Task 6) e le intestazioni sopra.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from decimal import Decimal

from importers.lettore.colonne import (
    _ANALISI, _PAROLE_RIGA_TESTATA, _RUOLI_TESTATA, Colonna, _corrente, _data, _mastri, _mesi, _norm as _norm_testata,
    _ruoli)
from importers.lettore.geometria import Parola, RigaFisica
from importers.lettore.importi import Importo, leggi_importo
from importers.lettore.profilo import (
    _MACRO_ATTESA, _QUOTA_CODICI, _RUOLI_VERIFICA, Profilo, TabellaNota, _candidati, _decimali, _forme, _indizio,
    _INTERO, _VOCE_NUMERATA, _negativi, _norm, _parole_del_tipo, _sezioni, _sezioni_pagina, _voce_di_legge)
from importers.lettore.righe import Documento, Riga, _codice, _normalizza
from importers.lettore.totali import _TESTATA, _TESTATA_ANCHE, assegna_padri, marca_totali
from importers.mineru_adapter import _parse_table_html

# Geometria sintetica: la descrizione sta a sinistra di `profilo._X0_MINIMO` (150), le colonne a destra.
_X_TESTO = 10.0
_X_TESTO_MAX = 140.0
_LARGHEZZA_CARATTERE = 4.0
_X_COLONNA = 300.0
_PASSO_COLONNA = 120.0
_LARGHEZZA_IMPORTO = 50.0
_INTERLINEA = 12.0
_Y_PRIMA = 50.0
_MAX_COLSPAN = 20
_RIGHE_TITOLO = 2          # righe di titolo che possono stare sopra l'intestazione della tabella
_ORDINE_LATI = {"U": 0, "L": 1, "R": 2}
# Le parole di testata di una colonna di valori (le altre parole di testata sono della descrizione)
_VALORE_TESTATA = {"importo", "importi", "saldo", "saldi", "dare", "avere", "esercizio", "esercizi", "corrente",
                   "precedente", "consuntivo", "comparato", "valori", "progr", "progressivo", "progressivi",
                   "differenza", "diff", "scost", "scostamento", "variazione", "var", "%", "periodo", "bilancio",
                   "anno", "totali", "parziali", "rettificato", "finale", "euro", "\u20ac"}
# Le parole di testata della descrizione che le liste del passo 3 e del passo 6 non hanno
_DESCRIZIONE_TESTATA = {"partitario", "sottoconto", "sottoconti", "mastri", "denominazione", "nr", "n"}
# Il titolo di un lato delle sezioni contrapposte, da solo nella sua cella
_LATI_TESTATA = {"attivita", "passivita", "attivo", "passivo", "costi", "ricavi", "attivita e passivita"}
# Una tabella senza intestazione si allinea a quella che eredita solo se MinerU ha aggiunto o tolto una cella
_SPOSTAMENTO_MAX = 1

_SPAZI = re.compile(r"[\u00a0\u202f\u2009\s]+")
_LETTERA = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
_COLSPAN = re.compile(r"<(t[dh])\b([^>]*?)\scolspan\s*=\s*[\"']?(\d+)[\"']?([^>]*)>(.*?)</\1\s*>", re.I | re.S)
_ROWSPAN = re.compile(r"\browspan\s*=\s*[\"']?([2-9]|\d{2,})", re.I)
_A_CAPO_HTML = re.compile(r"<br\s*/?>", re.I)
# «94.086.46»: l'OCR ha letto la virgola dei decimali come un punto
_PUNTO_DECIMALE = re.compile(r"(\(?[-\u2212\u2013]?)(\d{1,3}(?:\.\d{3})*)\.(\d{2})(\)?-?(?: [DA])?)")


# --------------------------------------------------------------------------------------
# Importi: le grafie dell'OCR
# --------------------------------------------------------------------------------------

def _grafia_ocr(t: str) -> str:
    """Le grafie dell'OCR riportate a quelle di `leggi_importo`: virgola staccata («1.234 ,56»), migliaia a spazi
    («11 396,02»), segno staccato («- 1.000,00»), punto al posto della virgola dei decimali («94.086.46»)."""
    t = re.sub(r"(?<=\d)\s*,\s*(?=\d)", ",", t)
    t = re.sub(r"(?<=\d) (?=\d{3}(?!\d))", ".", t)
    t = re.sub(r"^(\(?[-\u2212\u2013])\s+(?=\d)", r"\1", t)
    m = _PUNTO_DECIMALE.fullmatch(t)
    if m:
        t = f"{m.group(1)}{m.group(2)},{m.group(3)}{m.group(4)}"
    return t


def _importo_cella(cella: str) -> tuple[Importo, str] | None:
    """(importo, token normalizzato) di una cella di colonna, o None. La normalizzazione dei token del text layer
    (`righe._normalizza`: meno Unicode, spazi non separabili, marcatore D/A attaccato) vale anche qui; le grafie
    dell'OCR solo se la cella cosi' com'e' non e' un importo. `Importo.testo` resta la cella come stampata."""
    t = _SPAZI.sub(" ", cella).strip()
    if not t:
        return None
    for candidato in (t, _grafia_ocr(t)):
        token = _normalizza(candidato)
        imp = leggi_importo(token)
        if imp is not None:
            return dataclasses.replace(imp, testo=cella.strip()), token
    return None


# --------------------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------------------

def _espandi(html: str) -> str:
    """Una cella con colspan=n diventa n celle (la prima col testo): la posizione delle celle dopo resta quella
    della colonna. «<br>» e' uno spazio, non una parola incollata alla successiva."""
    html = _A_CAPO_HTML.sub(" ", html or "")

    def una(m: re.Match) -> str:
        n = min(max(int(m.group(3)), 1), _MAX_COLSPAN)
        tag = m.group(1)
        return f"<{tag}{m.group(2)}{m.group(4)}>{m.group(5)}</{tag}>" + f"<{tag}></{tag}>" * (n - 1)

    return _COLSPAN.sub(una, html)


def _celle_tabella(html: str, pagina: int, k: int) -> list[list[str]]:
    return [[_SPAZI.sub(" ", c.text or "").strip() for c in r.cells]
            for r in _parse_table_html(_espandi(html), pagina, f"t{k}")]


# --------------------------------------------------------------------------------------
# Intestazione
# --------------------------------------------------------------------------------------

def _periodo(cella: str) -> tuple | None:
    """(fine, inizio, mesi) di una cella d'intestazione: una data (o un anno), o «dal ... al ...», con intorno solo
    parole di testata («Esercizio 2024», «Saldo al 31/12/2024»)."""
    parole = cella.split()
    date = [(k, d) for k, p in enumerate(parole) if (d := _data(p)) is not None]
    if not date or not all(_norm_testata(p) in _PAROLE_RIGA_TESTATA for k, p in enumerate(parole)
                           if k not in {i for i, _ in date}):
        return None
    if len(date) == 1:
        fine, intera = date[0][1]
        return fine, None, _mesi(None, fine, intera)
    if len(date) == 2 and date[0][0] > 0 and _norm_testata(parole[date[0][0] - 1]) == "dal" \
            and date[0][1][1] and date[1][1][1]:
        inizio, (fine, _) = date[0][1][0], date[1][1]
        return fine, inizio, _mesi(inizio, fine, True)
    return None


def _parole_testata(cella: str) -> list[str]:
    return [p for p in (_norm(t).strip(".:") for t in cella.split()) if p]


def _tipo_cella(cella: str) -> str:
    """«vuota», «data», «colonna» (solo parole di testata, almeno una di una colonna di valori: «Importo», «Saldo»,
    «Differenza», «Scost. %»), «descrizione» (solo parole di testata della descrizione: «Cod.», «Conto»,
    «Descrizione»), «testo»."""
    if not cella:
        return "vuota"
    if _periodo(cella) is not None:
        return "data"
    parole = _parole_testata(cella)
    if " ".join(p.strip("'\u2019") for p in parole) in _LATI_TESTATA:
        return "lato"
    if parole and all(p in _PAROLE_RIGA_TESTATA or p in _TESTATA or p in _TESTATA_ANCHE or p in _DESCRIZIONE_TESTATA
                      for p in parole):
        return "colonna" if any(p in _VALORE_TESTATA for p in parole) else "descrizione"
    return "testo"


def _ruolo(cella: str) -> set[str]:
    """Le parole di ruolo di una cella d'intestazione («Differenza», «Scost. %», «Saldo»)."""
    return {_norm_testata(p) for p in cella.split()} & (_ANALISI | set(_RUOLI_TESTATA))


def _solo_testata(testo: str) -> bool:
    """La descrizione di una testata fatta solo di parole di testata («Cod. Descrizione», «Conto»): non e' un
    titolo."""
    return _tipo_cella(testo) in ("colonna", "descrizione")


@dataclass
class _Segmento:
    lato: str
    etichetta: list[int]               # posizioni delle celle della descrizione
    colonne: dict[int, tuple]          # posizione -> chiave della colonna del documento


@dataclass
class _Testata:
    segmenti: list[_Segmento]
    larghezza: int
    periodi: dict[tuple, tuple] = field(default_factory=dict)    # chiave -> (fine, inizio, mesi)
    parole: dict[tuple, set[str]] = field(default_factory=dict)  # chiave -> parole di ruolo


def _testata(celle: list[str], senza_date: bool = False) -> _Testata | None:
    """L'intestazione delle colonne, o None. E' tale una riga senza importi che dalla seconda cella in poi ha
    almeno una data o una parola di colonna, e per il resto solo parole di testata o celle vuote. Una cella di
    descrizione o di testo dopo una colonna apre il secondo lato delle sezioni contrapposte («Attivita' | 2024 |
    Passivita' | 2024», «Conto | Descrizione | Importo | Conto | Descrizione | Importo»); una cella di testo dentro
    la descrizione (un'anagrafica: «Unicarton Srl | Via ... | Data | 11/09/2026») non e' un'intestazione. Una data
    nella prima cella vuol dire che MinerU ha omesso la cella vuota sopra le descrizioni. Senza `senza_date` ci vuole
    almeno una data: «Descrizione | Esercizio precedente | Esercizio corrente» e' una tabella della nota."""
    if any(_importo_cella(c) for c in celle):
        return None
    if not senza_date and not any(_tipo_cella(c) == "data" for c in celle):
        return None
    if celle and _tipo_cella(celle[0]) == "data":
        celle = [""] + celle
    tipi = [_tipo_cella(c) for c in celle]
    if senza_date and tipi.count("lato") == 2 and tipi[0] == "lato" and set(tipi) == {"lato", "vuota"}:
        # solo i titoli dei due lati («ATTIVITA' | | PASSIVITA' |»): sotto ciascuno, le colonne senza intestazione
        k = tipi.index("lato", 1)
        if k >= 2 and len(tipi) - k >= 2:
            testata = _Testata([], len(celle))
            for lato, (a, b) in (("L", (0, k)), ("R", (k, len(celle)))):
                testata.segmenti.append(_Segmento(lato, [a], {i: (lato, "vuota", i - a, 0) for i in range(a + 1, b)}))
            return testata
        return None
    tipi = ["descrizione" if t == "lato" else t for t in tipi]
    inizi, colonna = [0], False
    for i in range(1, len(tipi)):
        if tipi[i] in ("data", "colonna"):
            colonna = True
        elif tipi[i] in ("descrizione", "testo"):
            if colonna:
                inizi.append(i)
                colonna = False
            elif tipi[i] == "testo":
                return None
    if not colonna:
        return None          # un lato senza colonne, o nessuna colonna
    testata = _Testata([], len(celle))
    lati = ["U"] if len(inizi) == 1 else ["L", "R"] if len(inizi) == 2 else ["?"] * len(inizi)
    for s, (a, lato) in enumerate(zip(inizi, lati)):
        b = inizi[s + 1] if s + 1 < len(inizi) else len(celle)
        prima = next(i for i in range(a + 1, b) if tipi[i] in ("data", "colonna"))
        seg = _Segmento(lato, list(range(a, prima)), {})
        visti: dict[tuple, int] = {}
        for i in range(prima, b):
            if tipi[i] == "data":
                periodo = _periodo(celle[i])
                base = (lato, "data", periodo)
                testata.periodi.setdefault(base + (visti.get(base, 0),), periodo)
            elif tipi[i] == "colonna":
                base = (lato, "testata", " ".join(_parole_testata(celle[i])))
            else:
                base = (lato, "vuota", i - a)
            chiave = base + (visti.get(base, 0),)
            visti[base] = visti.get(base, 0) + 1
            seg.colonne[i] = chiave
            ruolo = _ruolo(celle[i])
            if ruolo:
                testata.parole.setdefault(chiave, set()).update(ruolo)
        testata.segmenti.append(seg)
    return testata


def _spostata(testata: _Testata, d: int) -> _Testata | None:
    """La stessa intestazione con le colonne `d` celle piu' in la' (la descrizione si allarga o si stringe)."""
    segmenti = []
    for s, seg in enumerate(testata.segmenti):
        inizio = 0 if s == 0 else min(seg.etichetta) + d
        prima = min(seg.colonne, default=testata.larghezza) + d
        if inizio < 0 or prima <= inizio:
            return None
        segmenti.append(_Segmento(seg.lato, list(range(inizio, prima)), {p + d: c for p, c in seg.colonne.items()}))
    return _Testata(segmenti, testata.larghezza + d, testata.periodi, testata.parole)


def _allinea(testata: _Testata, righe: list[list[str]], pagina: int, avvisi: list[str]) -> _Testata | None:
    """Una tabella senza intestazione larga diversamente da quella che eredita (MinerU aggiunge o toglie una cella
    vuota fra descrizione e importi): fra gli spostamenti possibili vale quello che mette piu' importi in una
    colonna, meno quelli che lascia fuori. La colonna resta la posizione della cella, nella tabella allineata. Piu'
    di una cella di differenza: None, la tabella non e' il seguito del prospetto."""
    larghezza = _larghezza(righe)
    differenza = larghezza - testata.larghezza
    if differenza == 0:
        return testata
    if abs(differenza) > _SPOSTAMENTO_MAX:
        return None

    def punti(t: _Testata) -> int:
        colonne = {p for seg in t.segmenti for p in seg.colonne}
        return sum((1 if i in colonne else -1) for r in righe for i, c in enumerate(r)
                   if i > 0 and c and _importo_cella(c) is not None)

    candidati = [(punti(t), -abs(d), d, t) for d in range(min(0, differenza), max(0, differenza) + 1)
                 if (t := _spostata(testata, d)) is not None]
    candidati.sort(key=lambda c: c[:3], reverse=True)
    migliore = candidati[0]
    if len(candidati) > 1 and candidati[1][0] == migliore[0]:
        avvisi.append(f"pagina {pagina}: tabella senza intestazione larga {larghezza} celle, l'intestazione "
                      f"{testata.larghezza}: allineamento incerto, colonne spostate di {migliore[2]}")
    elif migliore[2]:
        avvisi.append(f"pagina {pagina}: tabella senza intestazione larga {larghezza} celle, l'intestazione "
                      f"{testata.larghezza}: colonne spostate di {migliore[2]}")
    return migliore[3]


def _per_posizione(larghezza: int) -> _Testata:
    """Senza nessuna intestazione nel documento: la prima cella e' la descrizione, ogni altra una colonna senza
    periodo."""
    return _Testata([_Segmento("U", [0], {i: ("U", "vuota", i, 0) for i in range(1, larghezza)})], larghezza)


def _nota(celle: list[str]) -> bool:
    """La prima riga di una tabella che e' un'intestazione ma non di date: la tabella e' della nota
    («Valore di inizio esercizio | Incrementi | ...», «Entro 12 mesi | Oltre 12 mesi»)."""
    piene = [c for c in celle[1:] if c]
    return len(piene) >= 2 and not any(_importo_cella(c) for c in celle)


def _testo_sopra_colonne(celle: list[str], testata: _Testata) -> bool:
    """La prima riga di una tabella senza intestazione porta del testo sopra le colonne che erediterebbe, e nessun
    importo: e' l'intestazione di una tabella della nota («| Variazioni nell'esercizio», «| Importo»)."""
    if any(_importo_cella(c) for c in celle):
        return False
    colonne = {p for seg in testata.segmenti for p in seg.colonne}
    return any(i in colonne and _LETTERA.search(c) for i, c in enumerate(celle) if c)


# --------------------------------------------------------------------------------------
# Righe
# --------------------------------------------------------------------------------------

@dataclass
class _Grezza:
    pagina: int
    lato: str
    testi: list[str]
    celle: dict[tuple, tuple[Importo, str]]   # chiave della colonna -> (importo, token normalizzato)
    y: float = 0.0
    interi: dict[tuple, tuple[Importo, str]] = field(default_factory=dict)   # interi nudi, in attesa del profilo


def _segmento_di_riga(celle: list[str], seg: _Segmento, fine: int | None, pagina: int,
                      avvisi: list[str]) -> _Grezza:
    """La parte della riga che cade nel segmento: le celle-colonna danno gli importi; il resto, e il testo nelle
    colonne, va nella descrizione. Un importo fuori da ogni colonna resta testo, e si dichiara."""
    testi: list[str] = []
    valori: dict[tuple, tuple[Importo, str]] = {}
    interi: dict[tuple, tuple[Importo, str]] = {}
    ultima = len(celle) if fine is None else min(fine, len(celle))
    inizio = min(seg.etichetta) if seg.etichetta else min(seg.colonne, default=0)
    for i in range(inizio, ultima):
        c = celle[i]
        if not c:
            continue
        chiave = seg.colonne.get(i)
        trovato = _importo_cella(c) if chiave is not None else None
        if trovato is not None:
            valori[chiave] = trovato
            continue
        if chiave is not None and _INTERO.match(c) and len(c.strip("()-")) <= 3:
            # un intero nudo («0», «673») e' un importo solo in una colonna a interi (decisione R6): lo decide il
            # profilo, sulle colonne
            v = Decimal(c.strip("()"))
            v = -v if c.startswith("(") else v
            interi[chiave] = (Importo(v, "zero" if v == 0 else "importo", c), c)
            continue
        if chiave is None and i not in seg.etichetta and _importo_cella(c) is not None:
            avvisi.append(f"pagina {pagina}: importo «{c}» in una cella senza colonna d'intestazione, resta testo")
        testi.append(c)
    descrizione = " ".join(testi)
    if not valori and not interi and re.search(r"\d", descrizione) and any(
            leggi_importo(_normalizza(t)) is not None for t in descrizione.split()[-2:]) \
            and _LETTERA.search(descrizione):
        avvisi.append(f"pagina {pagina}: importi nella cella della descrizione «{descrizione}»: la riga non si "
                      f"legge in colonna")
    return _Grezza(pagina, seg.lato, testi, valori, interi=interi)


def _voci_di_legge(righe: list[list[str]]) -> bool:
    """Qualche riga apre con una voce dello schema di legge («B) Immobilizzazioni», «II - Crediti», «4) ...»)."""
    return any(_voce_di_legge(c) or _VOCE_NUMERATA.match(c) for r in righe for c in r[:2] if c)


def _larghezza(righe: list[list[str]]) -> int:
    larghezze = [len(r) for r in righe]
    return max(set(larghezze), key=larghezze.count) if larghezze else 0


def _testate(tabelle: list[list[list[str]]]) -> dict[tuple[int, int], _Testata]:
    """Le intestazioni vere, per (tabella, riga). Un'intestazione vale solo con un importo sotto una delle sue colonne,
    nella tabella o, se e' la sua ultima riga, nella tabella dopo (`colonne._intestazioni`: «Dal | al 31/08/2026»
    sopra una tabella di conti non e' un'intestazione). Un'intestazione senza date vale solo in un documento senza
    intestazioni con le date (un bilancio di verifica: «Conto | Descrizione | Importo»): accanto a un prospetto
    datato, «Esercizio precedente | Esercizio corrente» e' della nota."""
    def vere(senza_date: bool) -> dict[tuple[int, int], _Testata]:
        out = {}
        for k, righe in enumerate(tabelle):
            for j, celle in enumerate(righe):
                t = _testata(celle, senza_date)
                if t is None:
                    continue
                sotto = righe[j + 1:] or (tabelle[k + 1] if k + 1 < len(tabelle) else [])
                posizioni = {p for seg in t.segmenti for p in seg.colonne}
                if any(i in posizioni and _importo_cella(c) is not None for r in sotto for i, c in enumerate(r)):
                    out[(k, j)] = t
        return out

    datate = vere(False)
    return datate if datate else vere(True)


def _grezze(tabelle: list[str], pagine: list[int], avvisi_doc: list[str], avvisi: list[str]
            ) -> tuple[list[_Grezza], dict[tuple, tuple], dict[tuple, set[str]], list[TabellaNota], bool]:
    grezze: list[_Grezza] = []
    periodi: dict[tuple, tuple] = {}
    parole: dict[tuple, set[str]] = {}
    note: list[TabellaNota] = []
    testata: _Testata | None = None
    senza_testata = False
    tutte = [[r for r in _celle_tabella(html, pagina, k) if any(r)] for k, (html, pagina) in enumerate(zip(tabelle,
                                                                                                          pagine))]
    vere = _testate(tutte)
    nota_larghezza: int | None = None       # la larghezza dell'ultima tabella, se era della nota
    for k, (html, pagina, piene) in enumerate(zip(tabelle, pagine, tutte)):
        if _ROWSPAN.search(html or ""):
            avvisi.append(f"pagina {pagina}: tabella con celle su piu' righe (rowspan), non espanse")
        if not piene:
            continue
        titolo = " | ".join(c for c in piene[0] if c)
        larghezza = _larghezza(piene)
        # l'intestazione della tabella puo' stare sotto i titoli dei lati («Attivita' | | | Passivita' | | |»)
        propria = next((vere[(k, j)] for j in range(min(len(piene), _RIGHE_TITOLO + 1)) if (k, j) in vere), None)
        dentro = True
        if propria is not None:
            nota_larghezza = None
        elif _nota(piene[0]):
            dentro = False
            note.append(TabellaNota(pagina, 0.0, 0.0, titolo, ()))
            avvisi_doc.append(f"pagina {pagina}: tabella con un'intestazione non di colonne di valori («{titolo}»): "
                              f"della nota, non si legge")
        elif nota_larghezza is not None and (testata is None or abs(larghezza - nota_larghezza)
                                             < abs(larghezza - testata.larghezza) or (
                abs(larghezza - nota_larghezza) == abs(larghezza - testata.larghezza) and not _voci_di_legge(piene))):
            # senza intestazione, larga come la tabella della nota prima e non meno: ne e' il seguito, salvo che a
            # parita' di larghezza porti le voci dello schema (il prospetto che riprende dopo una nota in mezzo,
            # «Varie altre riserve», `schema_legge_generico._grezze_mineru`)
            dentro = False
            note.append(TabellaNota(pagina, 0.0, 0.0, titolo, ()))
            avvisi_doc.append(f"pagina {pagina}: tabella senza intestazione («{titolo}») dopo una tabella della nota "
                              f"larga come lei: il suo seguito, non si legge")
        elif testata is None and vere:
            # prima della prima intestazione del documento (un'anagrafica, il periodo): non e' il prospetto
            dentro = False
            avvisi.append(f"pagina {pagina}: tabella senza intestazione («{titolo}») prima di ogni intestazione di "
                          f"colonne: non si legge")
        elif testata is not None:
            allineata = _allinea(testata, piene, pagina, avvisi)
            if allineata is not None and _testo_sopra_colonne(piene[0], allineata):
                dentro = False
                note.append(TabellaNota(pagina, 0.0, 0.0, titolo, ()))
                avvisi_doc.append(f"pagina {pagina}: tabella con un'intestazione non di colonne di valori sopra le "
                                  f"colonne del prospetto («{titolo}»): della nota, non si legge")
            elif allineata is None:
                dentro = False
                avvisi.append(f"pagina {pagina}: tabella senza intestazione («{titolo}») larga diversamente dal "
                              f"prospetto: non si legge")
            else:
                testata = allineata
        nota_larghezza = larghezza if not dentro else None
        for j, celle in enumerate(piene):
            nuova = vere.get((k, j))
            riga_testata = nuova is not None
            if nuova is not None:
                if _tipo_cella(celle[0]) == "data":
                    celle = [""] + celle
                if len(nuova.segmenti) > 2:
                    avvisi.append(f"pagina {pagina}: intestazione con {len(nuova.segmenti)} lati, la tabella non "
                                  f"si legge")
                    dentro, testata = False, None
                    continue
                testata, dentro = nuova, True
                periodi.update(nuova.periodi)
                for chiave, p in nuova.parole.items():
                    parole.setdefault(chiave, set()).update(p)
            elif propria is not None and len(propria.segmenti) <= 2 and dentro and celle is piene[0]:
                testata = propria      # i titoli dei lati sopra l'intestazione si leggono con le sue colonne
            if not dentro:
                continue
            if testata is None:
                if not senza_testata:
                    avvisi_doc.append("nessuna intestazione delle colonne: colonne per posizione, senza "
                                      "periodo")
                    senza_testata = True
                testata = _per_posizione(larghezza)
            segmenti = testata.segmenti
            for s, seg in enumerate(segmenti):
                if riga_testata:
                    # della testata resta solo la descrizione che non e' una parola di testata («STATO
                    # PATRIMONIALE», «Attivita'»): un titolo, che apre la sezione
                    testo = " ".join(celle[i] for i in seg.etichetta if i < len(celle) and celle[i])
                    if not _LETTERA.search(testo) or _solo_testata(testo):
                        continue
                    g = _Grezza(pagina, seg.lato, [testo], {})
                else:
                    fine = min(segmenti[s + 1].etichetta) if s + 1 < len(segmenti) else None
                    g = _segmento_di_riga(celle, seg, fine, pagina, avvisi)
                if g.testi or g.celle or g.interi:
                    grezze.append(g)
    return grezze, periodi, parole, note, senza_testata


# --------------------------------------------------------------------------------------
# Righe fisiche sintetiche (per le regole del profilo)
# --------------------------------------------------------------------------------------

def _parole_testo(testi: list[str], y: float) -> list[Parola]:
    out: list[Parola] = []
    x = _X_TESTO
    for t in " ".join(testi).split():
        x0 = min(x, _X_TESTO_MAX)
        out.append(Parola(x0, y - 4, min(x0 + len(t) * _LARGHEZZA_CARATTERE, 149.0), y + 4, t))
        x += len(t) * _LARGHEZZA_CARATTERE + 3
    return out


def _fisica(g: _Grezza, indici: dict[tuple, int], colonne: list[Colonna]) -> RigaFisica:
    parole = _parole_testo(g.testi, g.y)
    for chiave, (_, token) in g.celle.items():
        x = colonne[indici[chiave]].x_destra
        parole.append(Parola(x - _LARGHEZZA_IMPORTO, g.y - 4, x, g.y + 4, token))
    return RigaFisica(g.pagina, g.y, parole)


# --------------------------------------------------------------------------------------
# Documento
# --------------------------------------------------------------------------------------

def leggi_celle(tabelle: list[str], pagine: list[int]) -> Documento:
    """Il Documento dalle tabelle HTML di MinerU (`tabelle[k]` sta a pagina `pagine[k]`, 1-based), consumabile come
    quello di `leggi_pdf`: righe del prospetto, colonne, sezioni, totali e padri. Le tabelle della nota non danno
    righe: si dichiarano in `profilo.tabelle_nota`."""
    avvisi: list[str] = []
    avvisi_doc: list[str] = []
    if len(tabelle) != len(pagine) or any(p < 1 for p in pagine):
        raise ValueError("leggi_celle: una pagina per tabella, contata da 1")
    grezze, periodi, parole, note, _ = _grezze(tabelle, pagine, avvisi_doc, avvisi)
    if not grezze:
        profilo = Profilo("ignoto", "nessuna tabella", [], None, frozenset(), {}, [], {}, frozenset(),
                          avvisi_doc + ["tipo non determinato: nessuna riga di prospetto nelle tabelle OCR"],
                          tabelle_nota=note, parti={t.pagina: "nota" for t in note})
        return Documento([], [], False, avvisi + ["nessuna riga di prospetto nelle tabelle OCR"], profilo)

    # le colonne del documento, nell'ordine in cui compaiono: prima un lato, poi l'altro
    chiavi: list[tuple] = []
    for g in grezze:
        for chiave in g.celle:
            if chiave not in chiavi:
                chiavi.append(chiave)
    chiavi.sort(key=lambda c: _ORDINE_LATI.get(c[0], 0))
    indici = {c: i for i, c in enumerate(chiavi)}
    colonne = [Colonna(i, _X_COLONNA + i * _PASSO_COLONNA, c[0], "ignoto", *periodi.get(c, (None, None, None)), False)
               for i, c in enumerate(chiavi)]

    # y: in ordine dentro la pagina, i due lati di una stessa riga di tabella alla stessa altezza
    righe_per_pagina: dict[int, int] = {}
    precedente: _Grezza | None = None
    for g in grezze:
        if precedente is not None and precedente.pagina == g.pagina and (precedente.lato, g.lato) == ("L", "R"):
            g.y = precedente.y
        else:
            n = righe_per_pagina.get(g.pagina, 0)
            righe_per_pagina[g.pagina] = n + 1
            g.y = _Y_PRIMA + n * _INTERLINEA
        precedente = g
    fisiche = [_fisica(g, indici, colonne) for g in grezze]
    decimali = _decimali(fisiche, colonne)
    intere = frozenset(i for i, d in decimali.items() if d is False)
    for g in grezze:
        for chiave, intero in g.interi.items():
            if chiave in indici and indici[chiave] in intere:
                g.celle[chiave] = intero
            else:
                g.testi.append(intero[0].testo)
    fisiche = [_fisica(g, indici, colonne) for g in grezze]

    valori = []
    for g in grezze:
        riga: list = [None] * len(colonne)
        forme: list = [None] * len(colonne)
        for chiave, (imp, _) in g.celle.items():
            riga[indici[chiave]], forme[indici[chiave]] = imp.valore, imp.forma
        valori.append([g.pagina, g.y, riga, forme])
    _ruoli(colonne, valori, {indici[c]: p for c, p in parole.items() if c in indici},
           {indici[c]: p for c, p in periodi.items() if c in indici})
    lati = sorted({c.lato for c in colonne}, key=_ORDINE_LATI.get)
    for lato in lati:
        del_lato = [c for c in colonne if c.lato == lato]
        _mastri(del_lato, valori)
        _corrente(del_lato)
    contrapposto = {"L", "R"} <= set(lati)

    # il profilo, con le regole di `profilo_documento` sulle righe sintetiche
    n_pagine = max(g.pagina for g in grezze)
    per_pagina: list[list[RigaFisica]] = [[] for _ in range(n_pagine)]
    for f in fisiche:
        per_pagina[f.pagina - 1].append(f)
    forme_codice = _forme(_candidati(fisiche, colonne, None))
    tipo_parole, _, quota, perche_parole = _parole_del_tipo(fisiche, colonne)
    ruoli = {c.ruolo for c in colonne}
    if tipo_parole is not None:
        tipo, perche = tipo_parole, "parole"
    elif contrapposto:
        tipo, perche = "contrapposte", "intestazione delle tabelle divisa in due lati"
    elif ruoli & _RUOLI_VERIFICA:
        tipo, perche = "verifica", "colonne " + "/".join(sorted(ruoli & _RUOLI_VERIFICA))
    elif quota >= _QUOTA_CODICI:
        tipo, perche = "verifica", "codici conto senza voci di legge"
    else:
        tipo, perche = "ignoto", "nessuna regola decide"
    indizio = _indizio(fisiche)
    if tipo == "ignoto":
        avvisi_doc.append(f"tipo non determinato ({perche_parole}; {indizio})")
    elif indizio.split()[1] not in _MACRO_ATTESA[tipo]:
        avvisi_doc.append(f"tipo {tipo}, ma il {indizio} (solo un indizio)")
    avvisi_doc.append("lettura dalle tabelle OCR: nessun rientro, la parentela la decidono le somme e le "
                      "intestazioni sopra")
    per_riga = _sezioni(per_pagina, colonne, avvisi_doc)
    sezione_di = {id(f): s for ff, ss in zip(per_pagina, per_riga) for f, s in zip(ff, ss)}
    parti = {n: "nota" for n in {t.pagina for t in note}}
    parti.update({g.pagina: "prospetto" for g in grezze})
    profilo = Profilo(
        tipo, f"{perche}; {perche_parole}; {indizio}", colonne, None, _negativi(fisiche, colonne, intere), decimali,
        forme_codice, _sezioni_pagina(per_pagina, per_riga), frozenset(), avvisi_doc, contrapposto, parti, [], note,
        frozenset(), {(f.pagina, f.y): sezione_di[id(f)] for f in fisiche},
        {(f.pagina, f.y): "prospetto" for f in fisiche})

    righe_doc: list[Riga] = []
    contatori: dict[tuple[int, str], int] = {}
    for g, f in sorted(zip(grezze, fisiche), key=lambda gf: (gf[0].pagina, _ORDINE_LATI[gf[0].lato], gf[0].y)):
        testo = [p for p in f.parole if p.x0 < _X_COLONNA - _LARGHEZZA_IMPORTO]
        cod = _codice(testo, forme_codice)
        n = contatori.get((g.pagina, g.lato), 0) + 1
        contatori[(g.pagina, g.lato)] = n
        celle = {indici[c]: imp for c, (imp, _) in g.celle.items()}
        etichetta = " ".join(cod.etichetta)
        righe_doc.append(Riga(id=f"p{g.pagina}r{n}{g.lato}", pagina=g.pagina, y=g.y, lato=g.lato,
                              sezione=sezione_di[id(f)], codice=cod.codice, etichetta=etichetta,
                              celle=dict(sorted(celle.items())), intestazione=not celle and bool(etichetta),
                              x=0.0 if testo else None, x_etichetta=0.0 if cod.codice else None))
    doc = Documento(righe_doc, colonne, contrapposto, avvisi, profilo)
    marca_totali(doc)
    assegna_padri(doc)
    return doc
