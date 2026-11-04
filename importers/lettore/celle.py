"""Il Documento dalle tabelle di MinerU: il secondo ingresso, per le scansioni senza text layer (Task 7).

MinerU consegna ogni riga gia' divisa in celle (il parser di `mineru_adapter`, con colspan e rowspan espansi su una
griglia). Le colonne vengono dall'intestazione della tabella (date e anni come il passo 3, parole di ruolo come
«Differenza», «%»): la colonna di ogni importo e' la posizione della sua cella, mai «gli ultimi due» (C4,
`_row_label_and_values`). Un'intestazione vale solo con importi sotto le sue colonne; senza date vale solo in un
documento che non ne stampa (un bilancio di verifica: «Conto | Descrizione | Importo»). Una tabella senza
intestazione eredita quella prima (il prospetto che continua sulla pagina dopo), allineata se MinerU ha aggiunto o
tolto una cella vuota.

Una tabella della nota non e' mai il prospetto (regola del proprietario): lo dicono il suo titolo (nella didascalia
o nella tabella: rendiconto, nota integrativa, movimentazione, indici, …), un'intestazione che non e' quella del
prospetto (la prima cella e il formato delle date) o il posto (dopo il totale che chiude una sezione, senza titolo
di sezione proprio); con lei il suo seguito. Non da' righe: si dichiara in `profilo.tabelle_nota`. Un'anagrafica
(ditta, sede, codice fiscale, periodo) e' «altro»: non da' righe, e il periodo che stampa vale per le colonne senza
date. Le sezioni contrapposte (un'intestazione con due lati) danno righe L e R, con colonne per lato.

Non c'e' geometria: le regole del profilo (forme dei codici, negativi, decimali, colonne a interi, sezioni, tipo) si
applicano a righe fisiche sintetiche, una per riga di tabella e lato, con la descrizione a sinistra di x=150 e ogni
importo sul bordo destro della sua colonna. `Riga.x` e' 0 per ogni riga con testo: l'HTML non stampa rientri, e la
parentela la decidono le somme (Task 6) e le intestazioni sopra, mai oltre il blocco di tabelle (`Riga.blocco`).
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from importers.lettore.colonne import (
    _ANALISI, _PAROLE_DESCRIZIONE, _PAROLE_RIGA_TESTATA, _PAROLE_VALORE, _RUOLI_TESTATA, Colonna, _corrente, _data,
    _mastri, _mesi, _parola_testata, _ruoli)
from importers.lettore.geometria import Parola, RigaFisica
from importers.lettore.importi import Importo, leggi_importo
from importers.lettore.profilo import (
    _INTERO, _MACRO_ATTESA, _PERCORSO_LEGGE, _QUOTA_CODICI, _RUOLI_VERIFICA, _TOTALE_PROSPETTO, _VOCE_NUMERATA,
    Profilo, TabellaNota, _candidati, _decimali, _forme, _indizio, _negativi, _norm, _parole_del_tipo, _sezioni,
    _sezioni_pagina, _titolo_parte, _titolo_sezione, _voce_di_legge)
from importers.lettore.righe import _ANAGRAFICA, Documento, Riga, _codice, _normalizza
from importers.lettore.totali import _PAROLE_CE, _PAROLE_SP, _PAROLE_VUOTE, _TESTATA, _TESTATA_ANCHE, assegna_padri, \
    marca_totali
from importers.mineru_adapter import _TableHTMLParser

# Geometria sintetica: la descrizione sta a sinistra di `profilo._X0_MINIMO` (150), le colonne a destra.
_X_TESTO = 10.0
_X_TESTO_MAX = 140.0
_LARGHEZZA_CARATTERE = 4.0
_X_COLONNA = 300.0
_PASSO_COLONNA = 120.0
_LARGHEZZA_IMPORTO = 50.0
_INTERLINEA = 12.0
_Y_PRIMA = 50.0
_MAX_SPAN = 20
_RIGHE_TITOLO = 2          # righe di titolo che possono stare sopra l'intestazione della tabella
_ORDINE_LATI = {"U": 0, "L": 1, "R": 2}
_MIN_VOCI_PROSPETTO = 3    # come `profilo._MIN_VOCI_PROVA`
# Una tabella senza intestazione si allinea a quella che eredita solo se MinerU ha aggiunto o tolto una cella
_SPOSTAMENTO_MAX = 1
# Il lessico di testata: quello del passo 3, quello del passo 6 e le parole della descrizione delle tabelle OCR
_LESSICO_TESTATA = _PAROLE_RIGA_TESTATA | _TESTATA | _TESTATA_ANCHE | _PAROLE_DESCRIZIONE
# I titoli della nota che `profilo._TITOLO_NOTA` non elenca perche' nel PDF stanno sopra tabelle gia' riconosciute
# dalla geometria; sulle tabelle OCR sono il solo segnale («Indici di struttura», «Composizione dei ricavi»)
_TITOLO_NOTA_TABELLA = re.compile(r"^(?:composizione|dettaglio|movimenti|indicatori|indici|flussi finanziari)\b")
# Il totale che chiude una sezione: dopo di lui una tabella datata senza titolo proprio non riprende il prospetto
_CHIUSURA_SEZIONE = re.compile(
    r"^(?:totale (?:attivo|passivo|attivita|passivita|generale)\b|totale a pareggio"
    r"|(?:\d{1,2}\s?\)\s*|[ivx]+\s?[-.)]\s*)?(?:utile|perdita)\b.*\besercizio)")
_PERIODO_ANAGRAFICA = re.compile(r"\bdal\s+(\d{1,2}/\d{1,2}/\d{4})\s+al\s+(\d{1,2}/\d{1,2}/\d{4})", re.I)
_ANAGRAFICA_PAROLE = re.compile(r"\bDITTA\b|\bSEDE\b|\bREGIME CONTABILE\b|\bTIPO REDDITO\b|\bDATI ANAGRAFICI\b")

_SPAZI = re.compile(r"[   \s]+")
_LETTERA = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
_A_CAPO_HTML = re.compile(r"<br\s*/?>", re.I)
# «94.086.46»: l'OCR ha letto la virgola dei decimali come un punto
_PUNTO_DECIMALE = re.compile(r"(\(?[-−–]?)(\d{1,3}(?:\.\d{3})*)\.(\d{2})(\)?-?(?: [DA])?)")


# --------------------------------------------------------------------------------------
# Importi: le grafie dell'OCR
# --------------------------------------------------------------------------------------

def _grafia_ocr(t: str) -> str:
    """Le grafie dell'OCR riportate a quelle di `leggi_importo`: virgola staccata («1.234 ,56»), migliaia a spazi
    («11 396,02»), segno staccato («- 1.000,00»), punto al posto della virgola dei decimali («94.086.46»)."""
    t = re.sub(r"(?<=\d)\s*,\s*(?=\d)", ",", t)
    t = re.sub(r"(?<=\d) (?=\d{3}(?!\d))", ".", t)
    t = re.sub(r"^(\(?[-−–])\s+(?=\d)", r"\1", t)
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
# HTML: la griglia delle celle
# --------------------------------------------------------------------------------------

class _ParserGriglia(_TableHTMLParser):
    """Il parser delle tabelle di `mineru_adapter`, che tiene anche colspan e rowspan di ogni cella."""

    def __init__(self) -> None:
        super().__init__()
        self.span: list[list[tuple[int, int]]] = []
        self._span_riga: list[tuple[int, int]] = []
        self._span_cella = (1, 1)

    def handle_starttag(self, tag, attrs):
        super().handle_starttag(tag, attrs)
        if tag == "tr":
            self._span_riga = []
        elif tag in ("td", "th"):
            valori = dict(attrs)

            def numero(nome: str) -> int:
                try:
                    return min(max(int(str(valori.get(nome) or 1).strip("\"' ")), 1), _MAX_SPAN)
                except ValueError:
                    return 1
            self._span_cella = (numero("colspan"), numero("rowspan"))

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cur is not None:
            self._span_riga.append(self._span_cella)
        elif tag == "tr" and self._cur is not None:
            self.span.append(self._span_riga)
        super().handle_endtag(tag)


def _celle_tabella(html: str) -> list[list[str]]:
    """Le righe della tabella sulla griglia: una cella con colspan=n occupa n posizioni, una con rowspan=n anche le
    stesse posizioni delle n-1 righe sotto. Il testo sta nella prima posizione, le altre sono vuote: un importo su
    due righe («TOTALE COSTI 2.505,51» accanto a «TOTALE RICAVI» e a «PERDITA D'ESERCIZIO») si conta una volta, e
    la riga sotto resta al suo lato. «<br>» e' uno spazio, non una parola incollata alla successiva."""
    parser = _ParserGriglia()
    try:
        parser.feed(_A_CAPO_HTML.sub(" ", html or ""))
    except Exception:  # noqa: BLE001 - HTML dell'OCR, mai bloccare la lettura
        return []
    occupate: set[tuple[int, int]] = set()
    out: list[list[str]] = []
    for r, (testi, span) in enumerate(zip(parser.rows, parser.span)):
        riga: list[str] = []
        for testo, (cs, rs) in zip(testi, span):
            while (r, len(riga)) in occupate:
                riga.append("")
            c = len(riga)
            for k in range(cs):
                riga.append(_SPAZI.sub(" ", testo).strip() if k == 0 else "")
                for rr in range(1, rs):
                    occupate.add((r + rr, c + k))
        while (r, len(riga)) in occupate:
            riga.append("")
        out.append(riga)
    return out


# --------------------------------------------------------------------------------------
# Intestazione
# --------------------------------------------------------------------------------------

def _parole_testata(cella: str) -> list[str]:
    return [p for p in (_parola_testata(t) for t in cella.split()) if p]


def _periodo(cella: str) -> tuple | None:
    """(fine, inizio, mesi) di una cella d'intestazione: una data (o un anno), o «dal ... al ...», con intorno solo
    parole di testata («Esercizio 2024», «Saldo al 31/12/2024», «2025 (€)»)."""
    parole = _parole_testata(cella)
    date_ = [(k, d) for k, p in enumerate(parole) if (d := _data(p)) is not None]
    if not date_ or not all(p in _LESSICO_TESTATA for k, p in enumerate(parole) if k not in {i for i, _ in date_}):
        return None
    if len(date_) == 1:
        fine, intera = date_[0][1]
        return fine, None, _mesi(None, fine, intera)
    if len(date_) == 2 and date_[0][0] > 0 and parole[date_[0][0] - 1] == "dal" and date_[0][1][1] and date_[1][1][1]:
        inizio, (fine, _) = date_[0][1][0], date_[1][1]
        return fine, inizio, _mesi(inizio, fine, True)
    return None


def _lato_di(cella: str) -> str | None:
    """La sezione del titolo di un lato da solo nella sua cella: «Attivita'», «PASSIVITA'» -> SP; «Costi»,
    «Ricavi» -> CE (le parole di `totali._PAROLE_SP`/`_PAROLE_CE`)."""
    parole = [p for p in re.split(r"[^a-z]+", _norm(cella)) if p and p not in _PAROLE_VUOTE]
    if not parole or len(parole) > 3:
        return None
    if all(p in _PAROLE_SP for p in parole):
        return "SP"
    if all(p in _PAROLE_CE for p in parole):
        return "CE"
    return None


def _tipo_cella(cella: str) -> str:
    """«vuota», «data», «lato» (il titolo di un lato), «colonna» (solo parole di testata, almeno una di una colonna
    di valori: «Importo», «Saldo», «Differenza», «Scost. %»), «descrizione» (solo parole di testata della
    descrizione: «Cod.», «Conto», «Descrizione»), «testo»."""
    if not cella:
        return "vuota"
    if _periodo(cella) is not None:
        return "data"
    if _lato_di(cella) is not None:
        return "lato"
    parole = _parole_testata(cella)
    if parole and all(p in _LESSICO_TESTATA for p in parole):
        return "colonna" if any(p in _PAROLE_VALORE for p in parole) else "descrizione"
    return "testo"


def _ruolo(cella: str) -> set[str]:
    """Le parole di ruolo di una cella d'intestazione («Differenza», «Scost. %», «Saldo»)."""
    return {_parola_testata(p) for p in cella.split()} & {_parola_testata(p) for p in _ANALISI | set(_RUOLI_TESTATA)}


def _solo_testata(testo: str) -> bool:
    """La descrizione di una testata fatta solo di parole di testata («Cod. Descrizione», «Conto»): non e' un
    titolo."""
    return _tipo_cella(testo) in ("colonna", "descrizione")


@dataclass
class _Segmento:
    lato: str
    etichetta: list[int]               # posizioni delle celle della descrizione
    colonne: dict[int, tuple]          # posizione -> chiave della colonna del documento
    sezione: str | None = None         # la sezione che il titolo del lato apre («Attivita'» -> SP)


@dataclass
class _Testata:
    segmenti: list[_Segmento]
    larghezza: int
    periodi: dict[tuple, tuple] = field(default_factory=dict)    # chiave -> (fine, inizio, mesi)
    parole: dict[tuple, set[str]] = field(default_factory=dict)  # chiave -> parole di ruolo
    firma: tuple = ()                  # la prima cella e il formato delle date: l'intestazione del prospetto


def _forma_data(cella: str) -> str:
    return re.sub(r"\d", "9", " ".join(p for p in _parole_testata(cella) if _data(p) is not None))


def _testata(celle: list[str], senza_date: bool = False) -> _Testata | None:
    """L'intestazione delle colonne, o None. E' tale una riga senza importi che dalla seconda cella in poi ha
    almeno una data o una parola di colonna, e per il resto solo parole di testata o celle vuote. Una cella di
    descrizione, di testo o il titolo di un lato dopo una colonna apre il secondo lato delle sezioni contrapposte
    («Attivita' | 2024 | Passivita' | 2024», «Conto | Descrizione | Importo | Conto | Descrizione | Importo»); una
    cella di testo dentro la descrizione (un'anagrafica: «Unicarton Srl | Via ... | Data | 11/09/2026») non e'
    un'intestazione. Una data nella prima cella vuol dire che MinerU ha omesso la cella vuota sopra le descrizioni.
    Senza `senza_date` ci vuole almeno una data: «Descrizione | Esercizio precedente | Esercizio corrente» e' una
    tabella della nota."""
    if any(_importo_cella(c) for c in celle):
        return None
    if not senza_date and not any(_tipo_cella(c) == "data" for c in celle):
        return None
    if celle and _tipo_cella(celle[0]) == "data":
        celle = [""] + celle
    tipi = [_tipo_cella(c) for c in celle]
    firma = ("vuota" if tipi[0] == "vuota" else "titolo" if tipi[0] in ("lato", "descrizione") or _sezione_titolo(
        celle[0]) else "testo", tuple(_forma_data(c) for c, t in zip(celle, tipi) if t == "data"))
    if senza_date and tipi.count("lato") == 2 and tipi[0] == "lato" and set(tipi) == {"lato", "vuota"}:
        # solo i titoli dei due lati («ATTIVITA' | | PASSIVITA' |»): sotto ciascuno, le colonne senza intestazione
        k = tipi.index("lato", 1)
        if k >= 2 and len(tipi) - k >= 2:
            testata = _Testata([], len(celle), firma=firma)
            for lato, (a, b) in (("L", (0, k)), ("R", (k, len(celle)))):
                testata.segmenti.append(_Segmento(lato, [a], {i: (lato, "vuota", i - a, 0) for i in range(a + 1, b)},
                                                  _lato_di(celle[a])))
            return testata
        return None
    inizi, colonna = [0], False
    for i in range(1, len(tipi)):
        if tipi[i] in ("data", "colonna"):
            colonna = True
        elif tipi[i] in ("descrizione", "testo", "lato"):
            if colonna:
                inizi.append(i)
                colonna = False
            elif tipi[i] == "testo":
                return None
    if not colonna:
        return None          # un lato senza colonne, o nessuna colonna
    testata = _Testata([], len(celle), firma=firma)
    lati = ["U"] if len(inizi) == 1 else ["L", "R"] if len(inizi) == 2 else ["?"] * len(inizi)
    for s, (a, lato) in enumerate(zip(inizi, lati)):
        b = inizi[s + 1] if s + 1 < len(inizi) else len(celle)
        prima = next(i for i in range(a + 1, b) if tipi[i] in ("data", "colonna"))
        seg = _Segmento(lato, list(range(a, prima)), {}, _lato_di(celle[a]))
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
        segmenti.append(_Segmento(seg.lato, list(range(inizio, prima)), {p + d: c for p, c in seg.colonne.items()},
                                  seg.sezione))
    return _Testata(segmenti, testata.larghezza + d, testata.periodi, testata.parole, testata.firma)


def _allinea(testata: _Testata, righe: list[list[str]], pagina: int, avvisi: list[str]) -> _Testata | None:
    """Una tabella senza intestazione larga diversamente da quella che eredita (MinerU aggiunge o toglie una cella
    vuota fra descrizione e importi): fra gli spostamenti possibili vale quello che mette piu' importi in una
    colonna, meno quelli che lascia fuori. Una cella aggiunta e' vuota sulle righe con importi: se porta testo
    («Quoziente di indebitamento | Esprime il grado ... | 0,86 | 0,49») la tabella non e' il seguito. La colonna resta
    la posizione della cella, nella tabella allineata. Piu' di una cella di differenza: None."""
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

    def aggiunte_vuote(t: _Testata, d: int) -> bool:
        if d <= 0:
            return True
        nuove = {min(seg.colonne) - k for seg in t.segmenti if seg.colonne for k in range(1, d + 1)}
        return not any(i in nuove and c for r in righe if any(_importo_cella(x) for x in r) for i, c in enumerate(r))

    candidati = [(punti(t), -abs(d), d, t) for d in range(min(0, differenza), max(0, differenza) + 1)
                 if (t := _spostata(testata, d)) is not None and aggiunte_vuote(t, d)]
    if not candidati:
        return None
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
    """La prima riga di una tabella che e' un'intestazione ma non di colonne di valori: la tabella e' della nota
    («Valore di inizio esercizio | Incrementi | ...», «Entro 12 mesi | Oltre 12 mesi»)."""
    piene = [c for c in celle[1:] if c]
    return len(piene) >= 2 and not any(_importo_cella(c) for c in celle)


def _testo_sopra_colonne(celle: list[str], testata: _Testata) -> bool:
    """La prima riga di una tabella senza intestazione porta testo, non un importo, sopra le colonne che erediterebbe:
    e' l'intestazione o la prosa di una tabella della nota («| Variazioni nell'esercizio», «| Importo»). Gli importi
    delle altre celle non contano."""
    colonne = {p for seg in testata.segmenti for p in seg.colonne}
    return any(i in colonne and _LETTERA.search(c) and _importo_cella(c) is None for i, c in enumerate(celle) if c)


# --------------------------------------------------------------------------------------
# Titoli: nota, sezione, anagrafica
# --------------------------------------------------------------------------------------

def _riga_di_testo(testo: str) -> RigaFisica:
    return RigaFisica(1, 0.0, [Parola(_X_TESTO, -4, _X_TESTO + 100, 4, testo)])


def _tipo_titolo(testo: str) -> str | None:
    """«nota», «nota-debole», «prospetto» o None: `profilo._titolo_parte` (R12) piu' i titoli delle tabelle della nota
    che solo le tabelle OCR stampano."""
    tipo = _titolo_parte(_riga_di_testo(testo))
    if tipo is None and _TITOLO_NOTA_TABELLA.match(_norm(testo).replace("'", "")):
        return "nota"
    return tipo


def _sezione_titolo(testo: str) -> str | None:
    """La sezione che un titolo apre («Stato patrimoniale», «CONTO ECONOMICO»), come `profilo._titolo_sezione`."""
    return _titolo_sezione(_riga_di_testo(testo), []) if testo else None


def _titoli_tabella(righe: list[list[str]], didascalia: str | None) -> list[str]:
    """I titoli di una tabella: la didascalia, la prima cella di ogni riga senza importi in testa alla tabella (fra
    le prime righe, fino alla prima con importi)."""
    out = [didascalia] if didascalia else []
    for r in righe[:_RIGHE_TITOLO + 1]:
        if any(_importo_cella(c) for c in r):
            break
        if r and r[0] and _LETTERA.search(r[0]):
            out.append(r[0])
    return out


def _prove_di_prospetto(righe: list[list[str]]) -> bool:
    """Le prove di un prospetto (R12): un totale dei prospetti, o almeno tre voci con la numerazione o il percorso di
    legge («A.1) Ricavi», «B.7) Servizi»)."""
    etichette = [_norm(c) for r in righe for c in r[:2] if c and _LETTERA.search(c)]
    voci = sum(1 for e in etichette if _voce_di_legge(e.upper()) or _VOCE_NUMERATA.match(e)
               or _PERCORSO_LEGGE.match(e.split()[0].upper()))
    return voci >= _MIN_VOCI_PROSPETTO or any(_TOTALE_PROSPETTO.match(e) for e in etichette)


def _percorsi_di_legge(righe: list[list[str]]) -> bool:
    """Qualche riga apre con il percorso di una voce di legge («A.1) Ricavi», «B.II.4.c)») o con la sua lettera
    («B) Costi della produzione»): la sezione dopo, non una tabella della nota."""
    return any(_PERCORSO_LEGGE.match(c.split()[0].upper()) or _voce_di_legge(c.upper())
               for r in righe for c in r[:2] if c and _LETTERA.search(c))


_VOCI_CE = re.compile(r"valore della produzione|costi della produzione|differenza tra valore e costi"
                      r"|proventi e oneri finanziari|risultato prima delle imposte|ricavi delle vendite")
_VOCI_SP = re.compile(r"immobilizzazioni|attivo circolante|patrimonio netto|trattamento di fine rapporto"
                      r"|ratei e risconti|disponibilita liquide")


def _sezione_dal_contenuto(righe: list[list[str]]) -> str | None:
    """La sezione che le voci della tabella nominano (le voci di legge del conto economico o dello stato
    patrimoniale), se una prevale."""
    testi = [_norm(c).replace("'", "") for r in righe for c in r[:2] if c]
    ce = sum(1 for t in testi if _VOCI_CE.search(t))
    sp = sum(1 for t in testi if _VOCI_SP.search(t))
    return "CE" if ce > sp else "SP" if sp > ce else None


def _anagrafica(righe: list[list[str]]) -> bool:
    testo = " | ".join(c for r in righe for c in r if c)
    return bool(_ANAGRAFICA_PAROLE.search(testo.upper()) or any(_ANAGRAFICA.search(c.upper()) for r in righe
                                                                  for c in r if c))


def _periodo_anagrafica(righe: list[list[str]]) -> tuple[date, date] | None:
    """Il periodo che un'anagrafica stampa («Movimenti dal 1/01/2026 al 15/06/2026»)."""
    for r in righe:
        for c in r:
            m = _PERIODO_ANAGRAFICA.search(c or "")
            if m:
                inizio = _data(_zeri(m.group(1)))
                fine = _data(_zeri(m.group(2)))
                if inizio and fine and inizio[1] and fine[1] and inizio[0] <= fine[0]:
                    return inizio[0], fine[0]
    return None


def _zeri(d: str) -> str:
    """«1/01/2026» -> «01/01/2026», la forma di `colonne._data`."""
    g, m, a = d.split("/")
    return f"{int(g):02d}/{int(m):02d}/{a}"


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
    blocco: int = 0
    sezione: str | None = None        # la sezione che la tabella apre (didascalia, titolo, titolo del lato)


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
    return max(set(larghezze), key=lambda n: (larghezze.count(n), n)) if larghezze else 0


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


@dataclass
class _Lettura:
    grezze: list[_Grezza] = field(default_factory=list)
    periodi: dict[tuple, tuple] = field(default_factory=dict)
    parole: dict[tuple, set[str]] = field(default_factory=dict)
    note: list[TabellaNota] = field(default_factory=list)
    altro: set[int] = field(default_factory=set)              # pagine con un'anagrafica
    periodo_anagrafica: tuple[date, date] | None = None
    titoli_sezione: list[tuple[int, int, str]] = field(default_factory=list)   # (pagina, indice grezza, sezione)


def _grezze(tabelle: list[str], pagine: list[int], titoli: list[str | None], avvisi_doc: list[str],
            avvisi: list[str]) -> _Lettura:
    out = _Lettura()
    testata: _Testata | None = None
    firma_prospetto: tuple | None = None
    senza_testata = False
    tutte = [[r for r in _celle_tabella(html) if any(r)] for html in tabelle]
    vere = _testate(tutte)
    nota_larghezza: int | None = None       # la larghezza dell'ultima tabella, se era della nota
    blocco, letta_prima = 0, False
    chiusa = False                          # l'ultima riga letta chiude una sezione («Totale passivo»)
    for k, (pagina, piene, didascalia) in enumerate(zip(pagine, tutte, titoli)):
        if not piene:
            continue
        titolo = " | ".join(c for c in piene[0] if c)
        larghezza = _larghezza(piene)
        # l'intestazione della tabella puo' stare sotto i titoli dei lati («Attivita' | | | Passivita' | | |»)
        propria = next((vere[(k, j)] for j in range(min(len(piene), _RIGHE_TITOLO + 1)) if (k, j) in vere), None)
        candidati = _titoli_tabella(piene, didascalia)
        tipi_titolo = [_tipo_titolo(t) for t in candidati]
        sezione = next((s for t in candidati if (s := _sezione_titolo(t))), None)
        if sezione is None and propria is not None:
            sezione = next((seg.sezione for seg in propria.segmenti if seg.sezione), None)
        perche = None                       # perche' la tabella non e' il prospetto
        if "nota" in tipi_titolo or ("nota-debole" in tipi_titolo and not _prove_di_prospetto(piene)):
            forte = "nota" if "nota" in tipi_titolo else "nota-debole"
            perche = f"titolo della nota («{candidati[tipi_titolo.index(forte)]}»)"
        elif propria is not None:
            if (firma_prospetto is not None and propria.firma[0] == "testo" and propria.firma[1] != firma_prospetto[1]
                    and sezione is None):
                perche = f"intestazione diversa da quella del prospetto («{titolo}»)"
            elif chiusa and sezione is None and not _prove_di_prospetto(piene) and not _percorsi_di_legge(piene):
                perche = f"tabella datata dopo il totale che chiude la sezione, senza titolo proprio («{titolo}»)"
        elif _nota(piene[0]):
            perche = f"intestazione non di colonne di valori («{titolo}»)"
        elif nota_larghezza is not None and (testata is None or abs(larghezza - nota_larghezza)
                                             < abs(larghezza - testata.larghezza) or (
                abs(larghezza - nota_larghezza) == abs(larghezza - testata.larghezza)
                and (chiusa or not _voci_di_legge(piene)))):
            # senza intestazione, larga come la tabella della nota prima e non meno: ne e' il seguito, salvo che a
            # parita' di larghezza porti le voci dello schema prima che il prospetto abbia chiuso la sezione (il
            # prospetto che riprende dopo una nota in mezzo, «Varie altre riserve», `_grezze_mineru`; il rendiconto
            # dopo l'utile dell'esercizio numera anche lui le sue voci, «B) Flussi finanziari ...»)
            perche = f"seguito di una tabella della nota larga come lei («{titolo}»)"
        elif testata is None and vere:
            perche = f"senza intestazione, prima di ogni intestazione di colonne («{titolo}»)"
        elif testata is not None:
            allineata = _allinea(testata, piene, pagina, avvisi)
            if allineata is not None and _testo_sopra_colonne(piene[0], allineata):
                perche = f"testo sopra le colonne del prospetto («{titolo}»)"
            elif allineata is None:
                perche = f"senza intestazione, larga diversamente dal prospetto («{titolo}»)"
            else:
                testata = allineata
        if perche is not None:
            if _anagrafica(piene):
                out.altro.add(pagina)
                out.periodo_anagrafica = out.periodo_anagrafica or _periodo_anagrafica(piene)
                avvisi_doc.append(f"pagina {pagina}: anagrafica («{titolo}»), non si legge")
            else:
                out.note.append(TabellaNota(pagina, 0.0, 0.0, didascalia or titolo, ()))
                avvisi_doc.append(f"pagina {pagina}: tabella della nota, non si legge: {perche}")
            nota_larghezza, letta_prima = larghezza, False
            continue
        nota_larghezza = None
        if sezione is None and propria is not None:
            # senza titolo, la sezione di una tabella con la sua intestazione la dice il contenuto; dopo il totale che
            # chiude una sezione, se il contenuto non decide resta da determinare («» apre una sezione sconosciuta,
            # mai quella chiusa)
            sezione = _sezione_dal_contenuto(piene) or ("" if chiusa else None)
        if not letta_prima or sezione is not None or (propria is not None and testata is not None
                                                      and propria.firma != testata.firma):
            # un'altra tabella, non il seguito della prima (dopo una nota, con un titolo di sezione, con
            # un'intestazione diversa): la ricerca di un'intestazione sopra non la attraversa
            blocco += 1
        letta_prima = True
        if sezione is not None:
            out.titoli_sezione.append((pagina, len(out.grezze), sezione))
        dentro = True
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
                firma_prospetto = firma_prospetto or nuova.firma
                out.periodi.update(nuova.periodi)
                for chiave, p in nuova.parole.items():
                    out.parole.setdefault(chiave, set()).update(p)
            elif propria is not None and len(propria.segmenti) <= 2 and dentro and celle is piene[0]:
                testata = propria      # i titoli dei lati sopra l'intestazione si leggono con le sue colonne
            if not dentro:
                continue
            if testata is None:
                if not senza_testata:
                    avvisi_doc.append("nessuna intestazione delle colonne: colonne per posizione, senza periodo")
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
                    g.blocco = blocco
                    # senza il codice in testa («2 | Stato patrimoniale attivo»): il titolo e' la descrizione
                    etichetta = " ".join(t for t in g.testi if _LETTERA.search(t))
                    if g.celle and _tipo_titolo(etichetta) == "prospetto" and (s_riga := _sezione_titolo(etichetta)):
                        # «Stato patrimoniale attivo 21.045.280,10»: il titolo del prospetto stampato col suo totale
                        out.titoli_sezione.append((pagina, len(out.grezze), s_riga))
                    out.grezze.append(g)
                    if g.celle:
                        chiusa = bool(_CHIUSURA_SEZIONE.match(_norm(" ".join(g.testi))))
    return out


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


# I titoli che `profilo._titolo_sezione` legge: «» e' la sezione sconosciuta (come «Conti non assegnati»)
_TITOLI_SINTETICI = {"SP": "STATO PATRIMONIALE", "CE": "CONTO ECONOMICO", "": "CONTI NON ASSEGNATI"}


# --------------------------------------------------------------------------------------
# Documento
# --------------------------------------------------------------------------------------

def leggi_celle(tabelle: list[str], pagine: list[int], titoli: list[str | None] | None = None) -> Documento:
    """Il Documento dalle tabelle HTML di MinerU (`tabelle[k]` sta a pagina `pagine[k]`, 1-based), consumabile come
    quello di `leggi_pdf`: righe del prospetto, colonne, sezioni, totali e padri. `titoli[k]`, se c'e', e' il testo
    stampato subito sopra la tabella (la didascalia di MinerU): dice la sezione («Stato patrimoniale») o che la
    tabella e' della nota («Rendiconto finanziario»), anche su una pagina con SP e CE. Le tabelle della nota non
    danno righe: si dichiarano in `profilo.tabelle_nota`; le anagrafiche sono «altro»."""
    avvisi: list[str] = []
    avvisi_doc: list[str] = []
    if len(tabelle) != len(pagine) or any(p < 1 for p in pagine):
        raise ValueError("leggi_celle: una pagina per tabella, contata da 1")
    if titoli is not None and len(titoli) != len(tabelle):
        raise ValueError("leggi_celle: un titolo (o None) per tabella")
    lettura = _grezze(tabelle, pagine, list(titoli) if titoli is not None else [None] * len(tabelle), avvisi_doc,
                      avvisi)
    grezze, periodi, parole, note = lettura.grezze, lettura.periodi, lettura.parole, lettura.note
    parti = {n: "nota" for n in {t.pagina for t in note}}
    parti.update({n: "altro" for n in lettura.altro if n not in parti})
    if not grezze:
        profilo = Profilo("ignoto", "nessuna tabella", [], None, frozenset(), {}, [], {}, frozenset(),
                          avvisi_doc + ["tipo non determinato: nessuna riga di prospetto nelle tabelle OCR"],
                          tabelle_nota=note, parti=parti)
        return Documento([], [], False, avvisi + ["nessuna riga di prospetto nelle tabelle OCR"], profilo)

    # le colonne del documento, nell'ordine in cui compaiono: prima un lato, poi l'altro
    chiavi: list[tuple] = []
    for g in grezze:
        for chiave in list(g.celle) + list(g.interi):
            if chiave not in chiavi:
                chiavi.append(chiave)
    chiavi.sort(key=lambda c: _ORDINE_LATI.get(c[0], 0))
    indici = {c: i for i, c in enumerate(chiavi)}
    colonne = [Colonna(i, _X_COLONNA + i * _PASSO_COLONNA, c[0], "ignoto", *periodi.get(c, (None, None, None)), False)
               for i, c in enumerate(chiavi)]

    # y: in ordine dentro la pagina, i due lati di una stessa riga di tabella alla stessa altezza; un titolo di
    # sezione della tabella (didascalia, titolo del lato) sta poco sopra la sua prima riga
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
            if indici[chiave] in intere:
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
    if lettura.periodo_anagrafica is not None and not any(c.fine for c in colonne):
        # il periodo stampato nell'anagrafica («Movimenti dal 1/01/2026 al 15/06/2026») e' quello delle colonne
        # senza date; i mesi solo se gli estremi sono di mese intero, come per le date in testata (`colonne._mesi`)
        inizio, fine = lettura.periodo_anagrafica
        for c in colonne:
            if c.ruolo in ("esercizio", "saldo"):
                c.fine, c.inizio, c.mesi = fine, inizio, _mesi(inizio, fine, True)
        avvisi_doc.append(f"periodo dall'anagrafica: dal {inizio:%d/%m/%Y} al {fine:%d/%m/%Y}")
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
                      "intestazioni sopra, dentro la stessa tabella o il suo seguito")
    # le sezioni: i titoli dentro le tabelle, piu' una riga-titolo sintetica (non una riga del documento) dove la
    # tabella apre una sezione con la didascalia o col titolo di un lato
    sintetiche: list[list[RigaFisica]] = [list(p) for p in per_pagina]
    for pagina, i, sezione in lettura.titoli_sezione:
        y = grezze[i].y - _INTERLINEA / 2
        sintetiche[pagina - 1].append(RigaFisica(pagina, y, [Parola(_X_TESTO, y - 4, _X_TESTO + 100, y + 4,
                                                                    _TITOLI_SINTETICI[sezione])]))
    for p in sintetiche:
        p.sort(key=lambda r: r.y)
    per_riga = _sezioni(sintetiche, colonne, avvisi_doc)
    sezione_di = {id(f): s for ff, ss in zip(sintetiche, per_riga) for f, s in zip(ff, ss)}
    # una tabella che continua sulla pagina dopo resta nella sua sezione, anche se `_sezioni` sulla pagina nuova non
    # la vede (la pagina prima ha chiuso con un totale che `_chiude_sezione` prende per la chiusura)
    del_blocco: dict[int, str] = {}
    for g, f in zip(grezze, fisiche):
        if sezione_di[id(f)]:
            del_blocco[g.blocco] = sezione_di[id(f)]
        elif g.blocco in del_blocco:
            sezione_di[id(f)] = del_blocco[g.blocco]
    per_riga = [[sezione_di[id(f)] for f in ff] for ff in sintetiche]
    per_riga_doc = [[sezione_di[id(f)] for f in ff] for ff in per_pagina]
    profilo = Profilo(
        tipo, f"{perche}; {perche_parole}; {indizio}", colonne, None, _negativi(fisiche, colonne, intere), decimali,
        forme_codice, _sezioni_pagina(per_pagina, per_riga_doc), frozenset(), avvisi_doc, contrapposto,
        {**parti, **{g.pagina: "prospetto" for g in grezze}}, [], note, frozenset(),
        {(f.pagina, f.y): sezione_di[id(f)] for f in fisiche}, {(f.pagina, f.y): "prospetto" for f in fisiche})

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
                              x=0.0 if testo else None, x_etichetta=0.0 if cod.codice else None, blocco=g.blocco))
    doc = Documento(righe_doc, colonne, contrapposto, avvisi, profilo)
    marca_totali(doc)
    assegna_padri(doc)
    return doc
