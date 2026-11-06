"""Colonne di importi del documento: bordi destri allineati, ruolo e periodo di ciascuna.

Le colonne vengono dai bordi destri degli importi (`schema_legge_generico._bordi`/`_colonne_pagina`); il
ruolo lo decidono i numeri (3 decimali = percentuale, a - b = differenza, la somma dei conti = mastro) e le
intestazioni lo confermano; il periodo viene dalle date stampate sopra la colonna (`_anni_intestazione`).
"""
from __future__ import annotations

import calendar
import re
import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from importers.lettore._ereditati import PAROLE_TESTATA, e_differenza
from importers.lettore.geometria import Parola, RigaFisica
from importers.lettore.importi import leggi_importo

# Due bordi destri nella stessa colonna distano al piu' cosi' (punti); una colonna ne porta almeno tanti.
_TOL_COLONNA = 14.0
_MIN_IMPORTI_COLONNA = 4
# A sinistra di qui c'e' la didascalia, non una colonna di importi.
_X0_MINIMO = 150.0
# Un'intestazione sta sopra una colonna se il suo bordo destro o il suo centro distano al piu' cosi'.
_TOL_INTESTAZIONE = 70.0
_TOL_SOMMA = Decimal("0.01")
_TESTATA_SU_DUE_RIGHE = 12.0

# Anno nudo, gg/mm/aaaa, gg/mm/aa, con "/", "." o "-".
_DATA = re.compile(r"^(?:(\d{2})[-/.](\d{2})[-/.])?(20\d{2})$|^(\d{2})[-/.](\d{2})[-/.](\d{2})$")
# Una lista sola per le colonne di analisi (C10).
_ANALISI = {"differenza", "diff.", "scostamento", "scost.", "variazione", "%"}
_ANALISI_DIFFERENZA = {"differenza", "diff.", "variazione"}
_RUOLI_TESTATA = {"dare": "dare", "avere": "avere", "saldo": "saldo"}
_PAROLE_RIGA_TESTATA = PAROLE_TESTATA | _ANALISI | set(_RUOLI_TESTATA) | {"dal", "fino", "infrannuale"}
# Lessico di testata per le intestazioni gia' divise in celle (le tabelle OCR, `celle.py`): quali parole di testata
# sono di una colonna di valori («Importo», «Esercizio precedente», «Scost. %») e quali della descrizione («Cod.»,
# «Partitario»); le altre parole di testata stanno in `_PAROLE_RIGA_TESTATA` e in `totali._TESTATA`.
_PAROLE_VALORE = {"importo", "importi", "saldo", "saldi", "dare", "avere", "esercizio", "esercizi", "corrente",
                  "precedente", "consuntivo", "comparato", "valori", "progr", "progressivo", "progressivi",
                  "differenza", "diff", "scost", "scostamento", "variazione", "var", "%", "periodo", "bilancio",
                  "anno", "totali", "parziali", "rettificato", "finale", "euro", "\u20ac", "eserc"}
_PAROLE_DESCRIZIONE = {"partitario", "sottoconto", "sottoconti", "mastri", "denominazione", "nr", "n"}


def _parola_testata(token: str) -> str:
    """Una parola d'intestazione nella forma del lessico: minuscola, senza parentesi, punti e due punti attorno
    («(€)» -> «€», «Scost.» -> «scost», «2025:» -> «2025»)."""
    return token.strip().casefold().strip("().:;[]")


@dataclass
class Colonna:
    indice: int                  # 0.. nell'ordine x
    x_destra: float              # bordo destro mediano
    lato: str                    # "U" (unico) | "L" | "R" (Task 4 lo raffina)
    ruolo: str                   # "esercizio" | "mastro" | "differenza" | "percentuale" | "dare" | "avere" | "saldo" | "ignoto"
    fine: date | None            # data di chiusura stampata sopra la colonna
    inizio: date | None
    mesi: int | None             # da inizio..fine, o da gennaio se l'inizio non e' stampato
    corrente: bool               # la colonna-esercizio piu' recente


def colonna_di(x_destra: float, colonne: list[Colonna]) -> Colonna | None:
    """La colonna il cui bordo destro dista al piu' 14 pt; None = fuori colonna."""
    vicine = [c for c in colonne if abs(c.x_destra - x_destra) <= _TOL_COLONNA]
    return min(vicine, key=lambda c: abs(c.x_destra - x_destra)) if vicine else None


def colonne_documento(righe: list[RigaFisica]) -> list[Colonna]:
    colonne = _colonne_dai_bordi(righe)
    if not colonne:
        return []
    valori = _valori(righe, colonne)
    periodi, parole = _intestazioni(righe, colonne)
    for c in colonne:
        c.fine, c.inizio, c.mesi = periodi.get(c.indice, (None, None, None))
    _ruoli(colonne, valori, parole, periodi)
    _mastri(colonne, valori)
    _corrente(colonne)
    return colonne


def _colonne_dai_bordi(righe: list[RigaFisica]) -> list[Colonna]:
    bordi = sorted(p.x1 for r in righe for p in r.parole
                   if _in_colonna(p) and _e_importo(p.testo))
    gruppi: list[list[float]] = []
    for x in bordi:
        if gruppi and x - gruppi[-1][-1] <= _TOL_COLONNA:
            gruppi[-1].append(x)
        else:
            gruppi.append([x])
    tenuti = [g for g in gruppi if len(g) >= _MIN_IMPORTI_COLONNA]
    return [Colonna(i, statistics.median(g), "U", "ignoto", None, None, None, False)
            for i, g in enumerate(tenuti)]


def _e_importo(testo: str) -> bool:
    imp = leggi_importo(testo)
    return imp is not None and imp.forma != "zero"


def _in_colonna(p: Parola) -> bool:
    """Un importo che comincia nella zona della didascalia non fa colonna e non vi conta."""
    return p.x0 > _X0_MINIMO


def _valori(righe: list[RigaFisica], colonne: list[Colonna]) -> list[list]:
    """Per ogni riga con importi, nell'ordine del documento: [pagina, y, valori per colonna, forme]."""
    out = []
    for r in sorted(righe, key=lambda r: (r.pagina, r.y)):
        valori: list[Decimal | None] = [None] * len(colonne)
        forme: list[str | None] = [None] * len(colonne)
        doppie: set[int] = set()
        for p in r.parole:
            imp = leggi_importo(p.testo) if _in_colonna(p) else None
            c = colonna_di(p.x1, colonne) if imp is not None else None
            if c is None:
                continue
            if valori[c.indice] is not None:
                doppie.add(c.indice)
            valori[c.indice], forme[c.indice] = imp.valore, imp.forma
        for i in doppie:        # due importi nella stessa colonna: la cella non si sa leggere
            valori[i] = forme[i] = None
        if any(v is not None for v in valori):
            out.append([r.pagina, r.y, valori, forme])
    return out


# --------------------------------------------------------------------------------------
# Intestazioni: date e parole sopra le colonne
# --------------------------------------------------------------------------------------

def _data(testo: str) -> tuple[date, bool] | None:
    """(data, stampata per intero); un anno nudo vale il 31/12 di quell'anno."""
    m = _DATA.match(testo.strip())
    if not m:
        return None
    try:
        if m.group(3):
            if m.group(1) is None:
                return date(int(m.group(3)), 12, 31), False
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1))), True
        return date(2000 + int(m.group(6)), int(m.group(5)), int(m.group(4))), True
    except ValueError:
        return None


def _sopra(parola: Parola, colonne: list[Colonna]) -> Colonna | None:
    centro = (parola.x0 + parola.x1) / 2
    c = min(colonne, key=lambda c: abs(parola.x1 - c.x_destra))
    if abs(parola.x1 - c.x_destra) <= _TOL_INTESTAZIONE or abs(centro - c.x_destra) <= _TOL_INTESTAZIONE:
        return c
    return None


def _norm(testo: str) -> str:
    return testo.strip().casefold().rstrip(":")


def _norm_testata(testo: str) -> str:
    """Come `_norm`, e una parola di testata col segno di percento vale «%» («%Scost.», «Diff.%»; non «(80%)»)."""
    n = _norm(testo)
    return "%" if "%" in n and n.replace("%", "") in _PAROLE_RIGA_TESTATA else n


def _e_riga_testata(r: RigaFisica) -> bool:
    """Solo parole di testata, date e anni: «ESERCIZIO ESERCIZIO DIFFERENZA SCOST.», «DARE AVERE SALDO»."""
    return all(_norm_testata(p.testo) in _PAROLE_RIGA_TESTATA or re.fullmatch(r"[\d\-./]+", p.testo.strip())
               for p in r.parole)


def _mesi(inizio: date | None, fine: date, intera: bool) -> int | None:
    """Mesi da inizio a fine (da gennaio se l'inizio manca); None se gli estremi non sono di mese intero
    o se la data e' un anno nudo."""
    if not intera or fine.day != calendar.monthrange(fine.year, fine.month)[1]:
        return None
    if inizio is None:
        return fine.month
    if inizio.day != 1 or inizio > fine:
        return None
    return (fine.year - inizio.year) * 12 + fine.month - inizio.month + 1


def _periodi_riga(r: RigaFisica, colonne: list[Colonna]) -> dict[int, tuple] | None:
    """Colonna -> (fine, inizio, mesi) dalle date della riga; None se la riga e' una frase (una data
    lontana dalle colonne, o due periodi sopra la stessa colonna)."""
    parole = r.parole
    trovati: dict[int, list[tuple]] = {}
    k = 0
    while k < len(parole):
        d = _data(parole[k].testo)
        if d is None:
            k += 1
            continue
        inizio = None
        prima = _norm(parole[k - 1].testo) if k else ""
        # «dal 01/01/2026 al 31/05/2026»: l'inizio e la fine sono un periodo solo, sopra la fine
        if (prima == "dal" and d[1] and k + 2 < len(parole) and _norm(parole[k + 1].testo) == "al"
                and (f := _data(parole[k + 2].testo)) is not None and f[1]):
            inizio, d, k = d[0], f, k + 2
        c = _sopra(parole[k], colonne)
        if c is None:
            return None
        trovati.setdefault(c.indice, []).append((d[0], inizio, _mesi(inizio, d[0], d[1])))
        k += 1
    if any(len(v) > 1 for v in trovati.values()):
        return None
    return {i: v[0] for i, v in trovati.items()}


def _testata_con_didascalia(r: RigaFisica, colonne: list[Colonna]) -> bool:
    """«Stato patrimoniale attivo 31/12/2025 31/12/2024», «Cod. Descrizione 31/12/2024»: una riga di testata con la
    didascalia a sinistra. Dalla prima data in poi solo date e parole di testata; prima, parole di testata o testo che
    finisce nella zona della didascalia, lontano dalle colonne («Data di stampa: 26/05/2026» sta sopra le colonne, e
    «Pagina 1» dopo la data la esclude)."""
    prima = next((k for k, p in enumerate(r.parole) if _data(p.testo)), None)
    if prima is None or not colonne:
        return False
    # date di periodo («dal …», «al …») accanto a una data nuda: quella nuda e' la data di stampa («Stato
    # Patrimoniale dal 01/01/2026 al 11/09/2026 12/10/2026»)
    etichettate = [k > 0 and _norm(r.parole[k - 1].testo) in ("al", "dal") for k, p in enumerate(r.parole)
                   if _data(p.testo)]
    if any(etichettate) and not all(etichettate):
        return False
    zona = min(c.x_destra for c in colonne) - _TOL_INTESTAZIONE
    return (all(_norm(p.testo) in _PAROLE_RIGA_TESTATA or _data(p.testo) for p in r.parole[prima:])
            and all(_norm(p.testo) in _PAROLE_RIGA_TESTATA or p.x1 <= zona for p in r.parole[:prima]))


def _intestazioni(righe: list[RigaFisica], colonne: list[Colonna], extra: set[str] = frozenset()):
    """(colonna -> periodo, colonna -> parole di ruolo) dalle righe di testata sopra le colonne.

    Un'intestazione vera ha importi sotto di se' (`standard_ivcee_parser._anchors_carry_amounts`): vale
    solo per una colonna che porta un importo piu' in basso sulla stessa pagina. Il periodo si legge solo
    da una riga di testata («Data stampa 15/03/2026» non lo e'), e fra piu' testate vince la piu' vicina
    sopra gli importi della colonna, sulla prima pagina che ne ha una."""
    importi: dict[tuple[int, int], list[float]] = {}
    for r in righe:
        for p in r.parole:
            if _in_colonna(p) and _e_importo(p.testo) and (c := colonna_di(p.x1, colonne)) is not None:
                importi.setdefault((r.pagina, c.indice), []).append(r.y)

    def distanza(r: RigaFisica, i: int) -> float | None:
        sotto = [y for y in importi.get((r.pagina, i), []) if y > r.y]
        return min(sotto) - r.y if sotto else None

    candidati: dict[int, tuple] = {}     # colonna -> ((pagina, distanza), periodo)
    parole: dict[int, set[str]] = {}
    datate: list[tuple[RigaFisica, dict[int, tuple]]] = []
    zona = min((c.x_destra for c in colonne), default=0.0) - _TOL_INTESTAZIONE
    for r in sorted(righe, key=lambda r: (r.pagina, r.y)):
        if any(_e_importo(p.testo) for p in r.parole):
            continue
        if not (_e_riga_testata(r) or _testata_con_didascalia(r, colonne)):
            # «ATTIVITA' CORRENTE PRECEDENTE»: per le sole parole chieste in piu', anche una testata senza date con
            # la didascalia nella sua zona
            if extra and not any(_data(p.testo) for p in r.parole) \
                    and all(_norm(p.testo) in _PAROLE_RIGA_TESTATA or p.x1 <= zona for p in r.parole):
                for p in r.parole:
                    if (n := _norm(p.testo)) in extra and (c := _sopra(p, colonne)) is not None \
                            and distanza(r, c.indice) is not None:
                        parole.setdefault(c.indice, set()).add(n)
            continue
        if periodi := _periodi_riga(r, colonne):
            datate.append((r, periodi))
        for p in r.parole:
            n = _norm_testata(p.testo)
            if (n in _ANALISI or n in _RUOLI_TESTATA or n in extra) and (c := _sopra(p, colonne)) is not None \
                    and distanza(r, c.indice) is not None:
                parole.setdefault(c.indice, set()).add(n)
    # La testata datata piu' vicina sopra gli importi della colonna decide, anche se non la copre: una riga datata piu'
    # in alto («Bilancio di verifica al 30/06/2025», sopra una testata «Periodo al 30/06/2026 … al 30/06/2025» che
    # copre altre colonne) non da' il periodo a una colonna che la testata vera lascia senza data. Le righe datate a
    # meno di 12 punti dalla piu' vicina sono la stessa testata su due righe.
    for c in colonne:
        for pagina in sorted({r.pagina for r, _ in datate}):
            qui = [(d, r, periodi) for r, periodi in datate
                   if r.pagina == pagina and (d := distanza(r, c.indice)) is not None]
            if not qui:
                continue
            vicina = min(d for d, _, _ in qui)
            blocco = sorted((d, r.y, periodi) for d, r, periodi in qui if d <= vicina + _TESTATA_SU_DUE_RIGHE
                            and c.indice in periodi)
            if blocco:
                candidati[c.indice] = ((pagina, blocco[0][0]), blocco[0][2][c.indice])
            break
    return {i: v[1] for i, v in candidati.items()}, parole


# --------------------------------------------------------------------------------------
# Periodo del documento: i titoli («Situazione dal 01/01/2026 al 30/09/2026», «Bilancio al 31/12/2025»)
# --------------------------------------------------------------------------------------

_D = r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})"
_MESI_NOME = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
              "ottobre", "novembre", "dicembre")
_DAL_AL = re.compile(r"\bdal:?\s+" + _D + r"\s+al:?\s+" + _D + r"(?!\S)", re.I)
_TRATTINO = re.compile(r"(?<!\S)" + _D + r"\s*[\u2013\u2014-]\s*" + _D + r"(?!\S)")
_AL = re.compile(r"\bal:?\s+" + _D + r"(?!\S)", re.I)
_A_PAROLE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MESI_NOME) + r")\s+(20\d{2})\b", re.I)
_ESERCIZIO = re.compile(r"\b(?:esercizio|es\. di competenza):?\s+(20\d{2})\b", re.I)
# un titolo che dice di confrontare il periodo con l'anno intero prima («COMPARATO CON SALDO ANNO PRECEDENTE»)
_ANNO_PRECEDENTE = re.compile(r"\b(?:anno|esercizio) precedente\b", re.I)
_PAROLE_PERIODO = {"corrente": "corrente", "precedente": "precedente", "comparato": "precedente"}


# 31/12/2099 e simili: la data segnaposto di un gestionale («Dal al 31/12/2099»), non un periodo
_ANNO_SEGNAPOSTO = 2090


def _data_intera(testo: str) -> date | None:
    d = _data(testo)
    return d[0] if d and d[1] and d[0].year < _ANNO_SEGNAPOSTO else None


def periodi_stampati(righe: list[RigaFisica]) -> tuple[list[tuple[date | None, date]], bool]:
    """I periodi che i titoli stampano, (inizio, fine), dai piu' espliciti: «dal A al B», «A–B» e «al B»; se non ce
    n'e', «31 dicembre 2025»; se no «Esercizio 2025» (un anno nudo: fine 31/12, nessun inizio). In piu': se un titolo
    confronta con l'anno precedente."""
    espliciti, a_parole, anni = [], [], []
    precedente = False
    for r in righe:
        testo = " ".join(p.testo for p in r.parole)
        precedente = precedente or bool(_ANNO_PRECEDENTE.search(testo))
        presi: list[tuple[int, int]] = []
        for rx in (_DAL_AL, _TRATTINO):
            for m in rx.finditer(testo):
                i, f = _data_intera(m.group(1)), _data_intera(m.group(2))
                if f is not None:
                    espliciti.append((i, f))
                    presi.append(m.span())
        for m in _AL.finditer(testo):
            if not any(a <= m.start() < b for a, b in presi) and (f := _data_intera(m.group(1))) is not None:
                espliciti.append((None, f))
        for m in _A_PAROLE.finditer(testo):
            try:
                a_parole.append((None, date(int(m.group(3)), _MESI_NOME.index(m.group(2).casefold()) + 1,
                                            int(m.group(1)))))
            except ValueError:
                pass
        anni += [(None, date(int(m.group(1)), 12, 31)) for m in _ESERCIZIO.finditer(testo)
                 if int(m.group(1)) < _ANNO_SEGNAPOSTO]
    return (espliciti or a_parole or anni), precedente


def _periodo_unico(stampati: list[tuple[date | None, date]], anno: int | None = None) -> tuple | None:
    """(fine, inizio, mesi) se i periodi stampati (dell'anno dato) hanno una fine sola; se no None: due fini diverse
    non si scelgono."""
    scelti = [(i, f) for i, f in stampati if anno is None or f.year == anno]
    fini = {f for _, f in scelti}
    if len(fini) != 1:
        return None
    fine = fini.pop()
    inizi = {i for i, f in scelti if i is not None}
    inizio = inizi.pop() if len(inizi) == 1 else None
    mesi = _mesi(inizio, fine, True)
    if mesi is not None and mesi > 12:      # «dal 01.01.20 al 31.03.26»: un progressivo, non un esercizio
        inizio, mesi = None, None
    return fine, inizio, mesi


def completa_periodi(colonne: list[Colonna], testate: list[RigaFisica], titoli: list[RigaFisica],
                     avvisi: list[str] | None = None) -> None:
    """Il periodo delle colonne-valori che le testate lasciano senza data o con l'anno nudo, dai titoli del documento.

    - Un anno nudo sopra la colonna («Esercizio: 2026») prende il periodo stampato che finisce in quell'anno, se e'
      uno solo («Col. 1 Esercizio: 2026 periodo dal 01/01/2026 al 31/05/2026»).
    - Una colonna-valori senza data, sola sul suo lato, prende il periodo del documento, se e' uno solo («Situazione
      dal 01/01/2026 al 30/09/2026»); fra piu' colonne, quella con «corrente» in testata; quella con «precedente» o
      «comparato» prende l'anno intero prima, come un anno nudo, solo se un titolo dice «anno precedente» o se la
      corrente e' un anno solare intero: quella data non e' stampata, e si dichiara in `avvisi`.
    - Una colonna di mastri sul lato di una colonna-valori sola ne prende il periodo (sono lo stesso periodo).
    Poi la corrente si ricalcola (per lato)."""
    stampati, precedente = periodi_stampati(titoli)
    if not stampati:
        return
    _completa(colonne, testate, stampati, precedente, avvisi if avvisi is not None else [])
    for c in colonne:
        c.corrente = False
    for lato in {c.lato for c in colonne}:
        _corrente([c for c in colonne if c.lato == lato])


def _completa(colonne: list[Colonna], testate: list[RigaFisica], stampati: list, precedente: bool,
              avvisi: list[str]) -> None:
    for c in colonne:
        if c.ruolo in ("esercizio", "saldo", "mastro") and c.fine is not None and c.mesi is None \
                and c.inizio is None and (c.fine.month, c.fine.day) == (12, 31):
            if (p := _periodo_unico(stampati, c.fine.year)) is not None:
                c.fine, c.inizio, c.mesi = p
    documento = _periodo_unico(stampati)
    if documento is None:
        return
    _, parole = _intestazioni(testate, colonne, extra=set(_PAROLE_PERIODO))
    for lato in {c.lato for c in colonne}:
        valori = [c for c in colonne if c.lato == lato and c.ruolo in ("esercizio", "saldo")]
        senza = [c for c in valori if c.fine is None]
        if not senza:
            continue
        if len(valori) == 1:
            valori[0].fine, valori[0].inizio, valori[0].mesi = documento
            for m in colonne:
                if m.lato == lato and m.ruolo == "mastro" and m.fine is None:
                    m.fine, m.inizio, m.mesi = documento
            continue
        for c in senza:
            nomi = {_PAROLE_PERIODO[n] for n in parole.get(c.indice, set()) if n in _PAROLE_PERIODO}
            if nomi == {"corrente"}:
                c.fine, c.inizio, c.mesi = documento
            elif nomi == {"precedente"} and (precedente or (documento[2] == 12 and documento[0].month == 12)):
                # l'anno intero prima, come un anno nudo: dal titolo («anno precedente»), o perche' la corrente e'
                # un anno solare intero; dopo un infrannuale «precedente» puo' essere lo stesso periodo, e non si sceglie
                c.fine, c.inizio, c.mesi = date(documento[0].year - 1, 12, 31), None, None
                perche = "dal titolo «anno precedente»" if precedente else "dopo un anno solare intero"
                avvisi.append(f"colonna {c.indice + 1} «precedente» senza data stampata: letta come l'esercizio al "
                              f"{c.fine:%d/%m/%Y} ({perche}), data non stampata nel documento")


# --------------------------------------------------------------------------------------
# Ruoli
# --------------------------------------------------------------------------------------

def _ruoli(colonne: list[Colonna], valori: list[list], parole: dict[int, set[str]],
           periodi: dict[int, tuple]) -> None:
    matrice = [riga[2] for riga in valori]
    esercizi: list[int] = []
    for c in colonne:
        nomi = parole.get(c.indice, set())
        testata = {_RUOLI_TESTATA[n] for n in nomi if n in _RUOLI_TESTATA}
        if len(testata) == 1:           # dare/avere/saldo: l'intestazione decide (saldo = dare - avere)
            c.ruolo = testata.pop()
            continue
        if testata:
            c.ruolo = "ignoto"
            continue
        forme = [riga[3][c.indice] for riga in valori if riga[3][c.indice] not in (None, "zero")]
        if forme and sum(1 for f in forme if f == "percentuale") >= max(1, len(forme) // 2):
            c.ruolo = "percentuale"
            continue
        if c.indice not in periodi and any(
                e_differenza(matrice, c.indice, a, b) for a in esercizi for b in esercizi if a < b):
            c.ruolo = "differenza"
            continue
        analisi = nomi & _ANALISI
        if analisi:     # i numeri non lo dicono, l'intestazione dice che non e' un esercizio
            c.ruolo = "percentuale" if "%" in analisi else (
                "differenza" if analisi & _ANALISI_DIFFERENZA else "ignoto")
            continue
        c.ruolo = "esercizio"
        esercizi.append(c.indice)


def _e_mastro(valori: list[list], m: int, f: int) -> bool:
    """Ogni importo della colonna m e' la somma degli importi della colonna f che lo seguono, fino al
    prossimo importo di m; le due colonne non sono mai piene sulla stessa riga."""
    gruppi: list[list] = []
    for riga in valori:
        vm, vf = riga[2][m], riga[2][f]
        if vm is not None and vf is not None:
            return False
        if vm is not None:
            gruppi.append([vm, Decimal("0"), 0])
        elif vf is not None and gruppi:
            gruppi[-1][1] += vf
            gruppi[-1][2] += 1
    return len(gruppi) >= 2 and all(n > 0 and abs(tot - somma) <= _TOL_SOMMA for tot, somma, n in gruppi)


def _mastri(colonne: list[Colonna], valori: list[list]) -> None:
    """Due colonne-esercizio vicine dello stesso periodo: quella che somma i conti dell'altra e' dei mastri,
    e il periodo stampato sopra una vale per entrambe."""
    esercizi = [c for c in colonne if c.ruolo == "esercizio"]
    for a, b in zip(esercizi, esercizi[1:]):
        if a.fine is not None and b.fine is not None and (a.fine, a.mesi) != (b.fine, b.mesi):
            continue
        for m, f in ((a, b), (b, a)):
            if m.ruolo == "esercizio" and f.ruolo == "esercizio" and _e_mastro(valori, m.indice, f.indice):
                m.ruolo = "mastro"
                fonte = m if m.fine is not None else f
                for c in (m, f):
                    c.fine, c.inizio, c.mesi = fonte.fine, fonte.inizio, fonte.mesi
                break


def _corrente(colonne: list[Colonna]) -> None:
    """La colonna di valori piu' recente, ovunque stia (C4). Valori = esercizio e saldo: in un bilancio di
    verifica dare e avere sono movimenti, il saldo e' il valore di chiusura del periodo. Una sola colonna di
    valori e' la corrente anche senza data; piu' colonne senza date, o la data piu' recente su due colonne,
    nessuna."""
    esercizi = [c for c in colonne if c.ruolo in ("esercizio", "saldo")]
    if len(esercizi) == 1:
        esercizi[0].corrente = True
        return
    datate = [c for c in esercizi if c.fine is not None]
    if not datate:
        return
    recente = max(c.fine for c in datate)
    scelte = [c for c in datate if c.fine == recente]
    if len(scelte) == 1:
        scelte[0].corrente = True
