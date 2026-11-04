"""Righe logiche del documento: etichetta, codice conto, una cella per colonna, sezione e lato.

Compone i passi 1-4 (importi, righe fisiche, colonne, lati) e vi applica le regole di lettura che
l'importatore attuale sparge in piu' copie (inventario §1.2, §1.6, §1.8): importo legato alla colonna dal
bordo destro (fuori colonna torna nell'etichetta), parentesi staccata ricucita, importo orfano riattaccato,
didascalia a capo, margini e piedi tolti, riporti e anagrafiche scartati, codice conto separato, sezione SP/CE
dai titoli e dalla continuazione di pagina. Non classifica e non somma: legge e dichiara.
"""
from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field

import fitz

from importers.detail_enrichment import _chiude_sezione, _sezione_della_chiusura
from importers.lettore.colonne import Colonna, _e_riga_testata, colonna_di, colonne_documento
from importers.lettore.geometria import Parola, RigaFisica, parole_pagina, righe_fisiche
from importers.lettore.importi import Importo, leggi_importo
from importers.lettore.lati import assegna_lati, confine_dei_lati
from importers.schema_legge_generico import _PIEDE, _forma_strutturale, _intestazione
from importers.standard_ivcee_parser import riga_conto
from importers.xbrl_reso_parser import _FASCIA_MARGINE, _chiave_ripetuta, _frase_aperta

_X0_MINIMO = 150.0          # come `colonne._in_colonna`
# Una riga senza importi piu' vicina di cosi' (frazione dell'interlinea) alla riga sopra ne e' il seguito
# (`schema_legge_generico._A_CAPO`).
_A_CAPO = 0.7
# Un importo senza didascalia a non piu' di tanti punti dalla didascalia senza importi e' il suo
# (`xbrl_reso_parser._DISTANZA_IMPORTO_ORFANO`); oppure i riquadri si sovrappongono per meta' altezza
# (`schema_legge_generico._riattacca_importi`).
_DISTANZA_ORFANO = 8.0
_ADIACENTE = 1.5
_SOVRAPPOSIZIONE_ORFANO = 0.5
_STACCO_PARENTESI = 6.0
_VALUTA = {"euro", "eur", "€"}
_SCADENZA = {"mesi", "mese", "anni", "anno", "m"}
_ORDINE_LATI = {"U": 0, "L": 1, "R": 2}
_SEZIONI = {"bs": "SP", "ce": "CE"}

# Anagrafiche e riporti (`situazione_contabile_parser._be_collect_side_facts`): non sono righe del prospetto.
_ANAGRAFICA = re.compile(r"^(?:VIA|VIALE|V\.LE|PIAZZA|P\.ZZA|CORSO|C\.F\.|P\.\s?IVA|REA)\b|CODICE FISCALE|PARTITA IVA")
# A parola intera: «SEGUENTE» («esercizio seguente») non e' un riporto.
_RIPORTO = re.compile(r"\bA\s+RIPORT\w*|\bRIPORTO\b|\bRIPORTARE\b|\bSEGUE\b|\bPROGRESSIV\w*")
_IMPORTI = re.compile(r"\bIMPORTI\b")
# Il capitale sociale nella ragione sociale o nell'anagrafica («CAP. SOC. E 22.000.000,00», «Capitale sociale:
# Euro 1.500.000,00 di cui versato: Euro 1.500.000,00»): un importo con la valuta davanti e' testo, anche
# quando cade per caso sotto una colonna (budget_1450, budget_1445).
_CAPITALE = re.compile(r"\bCAP(?:ITALE|\.)?\s*SOC(?:IALE|\.)?", re.I)
_CODICE_AGO = (re.compile(r"^\d{6}$"), re.compile(r"^\d{3}$"))
_TAG_IVCEE = re.compile(r"^[a-e](?:[ivx]+\d*[a-z]?|\d+[a-z]?)?$")
_SEPARATORE = re.compile(r"^[-–:.]+$")


@dataclass
class Riga:
    id: str                      # "p{pagina}r{n}{lato}", stabile fra due letture dello stesso file
    pagina: int
    y: float
    lato: str                    # "U" | "L" | "R"
    sezione: str                 # "SP" | "CE" | ""
    codice: str                  # "" se assente
    etichetta: str
    celle: dict[int, Importo]    # indice di Colonna -> importo; una colonna assente = cella vuota
    totale: bool = False         # Task 6
    figli: dict[int, tuple[str, ...]] = field(default_factory=dict)   # per colonna, id dei figli (Task 6)
    intestazione: bool = False   # riga-titolo senza importi (mastro o gruppo stampato come titolo)
    padre: str | None = None     # id della riga madre (Task 6)
    padre_verificato: bool = False   # True se i figli del padre sommano al suo totale stampato
    percorso: tuple[str, ...] = ()   # etichette degli antenati, dalla sezione al padre (Task 6)


@dataclass
class Documento:
    righe: list[Riga]
    colonne: list[Colonna]
    contrapposto: bool
    avvisi: list[str]


@dataclass
class _Pezzo:
    """Una riga fisica di un lato, prima delle unioni."""
    pagina: int
    lato: str
    y: float                     # centro della prima riga fisica
    y_ultima: float              # centro dell'ultima riga fisica unita
    y0: float
    y1: float
    sezione: str
    codice: str
    etichetta: str
    celle: dict[int, Importo]


# --------------------------------------------------------------------------------------
# Token
# --------------------------------------------------------------------------------------

def _normalizza(testo: str) -> str:
    """Il token come lo legge `leggi_importo`: meno Unicode e trattino lungo davanti alle cifre, spazi non
    separabili tolti, marcatore D/A attaccato («1.234,56D») staccato. Solo se il risultato e' un importo;
    altrimenti il testo resta com'e' stampato."""
    t = testo
    for spazio in (" ", " ", " "):
        t = t.replace(spazio, "")
    t = re.sub(r"^(\(?)[−–](?=\d)", r"\1-", t)
    t = re.sub(r"(?<=\d)[−–](\)?)$", r"-\1", t)
    m = re.fullmatch(r"(.*\d\)?)([DA])", t)
    if m:
        t = f"{m.group(1)} {m.group(2)}"
    return t if t != testo and leggi_importo(t) is not None else testo


def _ricuci(parole: list[Parola]) -> list[Parola]:
    """Normalizza i token e ricuce la parentesi aperta staccata dall'importo («(» + «1.234,56)»)."""
    out: list[Parola] = []
    for p in parole:
        p = Parola(p.x0, p.y0, p.x1, p.y1, _normalizza(p.testo))
        prima = out[-1] if out else None
        if (prima is not None and prima.testo == "(" and p.x0 - prima.x1 <= _STACCO_PARENTESI
                and p.testo[:1].isdigit()):
            out[-1] = Parola(prima.x0, min(prima.y0, p.y0), p.x1, max(prima.y1, p.y1), "(" + p.testo)
            continue
        out.append(p)
    return out


def _norm(testo: str) -> str:
    testo = "".join(c for c in unicodedata.normalize("NFKD", testo) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", testo).strip().casefold()


# --------------------------------------------------------------------------------------
# Celle
# --------------------------------------------------------------------------------------

def _in_colonna(p: Parola, colonne: list[Colonna]) -> tuple[Importo, Colonna] | None:
    if p.x0 <= _X0_MINIMO:
        return None
    imp = leggi_importo(p.testo)
    c = colonna_di(p.x1, colonne) if imp is not None else None
    return (imp, c) if c is not None else None


def _ha_celle(r: RigaFisica, colonne: list[Colonna]) -> bool:
    return any(_in_colonna(p, colonne) for p in r.parole)


def _valuta_davanti(parole: list[Parola], i: int) -> bool:
    """La parola `i` segue una valuta, o la «E» del capitale sociale («CAP. SOC. E 22.000.000,00»)."""
    prima = parole[i - 1].testo.lower().strip(".:") if i >= 1 else ""
    if prima in _VALUTA:
        return True
    return prima == "e" and i >= 2 and parole[i - 2].testo.lower().startswith("soc")


def _celle_del_lato(parole: list[Parola], colonne: list[Colonna], lato: str, pagina: int,
                    avvisi: list[str]) -> tuple[dict[int, Importo], list[Parola]]:
    """(celle per colonna, parole dell'etichetta). Un importo e' una cella solo nella sua colonna e sul suo
    lato; fuori colonna, seguito da una durata («12 mesi») o dentro una frase dopo una valuta («euro 516,46
    di valore unitario», o in una riga col capitale sociale) torna nell'etichetta. Due importi nella stessa colonna: la cella non si legge."""
    celle: dict[int, Importo] = {}
    sedi: dict[int, list[Parola]] = {}
    testo: list[Parola] = []
    capitale = bool(_CAPITALE.search(" ".join(p.testo for p in parole)))
    for i, p in enumerate(parole):
        dopo = parole[i + 1].testo.lower().strip(".,:;") if i + 1 < len(parole) else ""
        trovato = _in_colonna(p, colonne)
        if (trovato is None or trovato[1].lato != lato or dopo in _SCADENZA
                or (_valuta_davanti(parole, i) and (capitale or any(ch.isalpha() for ch in dopo)))):
            testo.append(p)
            continue
        imp, c = trovato
        sedi.setdefault(c.indice, []).append(p)
        celle[c.indice] = Importo(imp.valore, imp.forma, p.testo)
    for indice, ps in sedi.items():
        if len(ps) > 1:
            del celle[indice]
            testo.extend(ps)
            avvisi.append(f"pagina {pagina}: due importi nella colonna {indice} sulla stessa riga "
                          f"({' '.join(p.testo for p in ps)}): cella non letta")
    testo.sort(key=lambda p: p.x0)
    while testo and _norm(testo[-1].testo) in _VALUTA:
        testo.pop()
    return celle, testo


def _codice(parole: list[str], ha_importo: bool) -> tuple[str, list[str]]:
    """(codice conto, parole dell'etichetta) col predicato unico `standard_ivcee_parser.riga_conto`. Il
    sottoconto a tre cifre dopo un mastro a sei («102355 151») e il conto dopo la voce IV-CEE («CII1A
    208.00121») fanno parte del codice."""
    if not parole or not riga_conto(" ".join(parole), ha_importo):
        return "", parole
    n = 1
    if _TAG_IVCEE.match(parole[0].lower()) and not re.match(r"^[\d/.]+$", parole[0]):
        n = 2
    elif len(parole) > 2 and _CODICE_AGO[0].match(parole[0]) and _CODICE_AGO[1].match(parole[1]):
        n = 2
    resto = parole[n:]
    while resto and _SEPARATORE.match(resto[0]):
        resto = resto[1:]
    return " ".join(parole[:n]), resto


# --------------------------------------------------------------------------------------
# Margini, piedi, sezioni
# --------------------------------------------------------------------------------------

def _testo(r: RigaFisica) -> str:
    return " ".join(p.testo for p in r.parole)


def _nel_margine(r: RigaFisica, altezza: float) -> bool:
    y0, y1 = min(p.y0 for p in r.parole), max(p.y1 for p in r.parole)
    return y1 <= _FASCIA_MARGINE * altezza or y0 >= (1 - _FASCIA_MARGINE) * altezza


def _ripetute(pagine: list[list[RigaFisica]], altezze: list[float], colonne: list[Colonna]) -> set[str]:
    """Le righe di margine senza importi che si ripetono su piu' pagine (`xbrl_reso_parser._ripetute`): «Pag.
    2» e «Pag. 3» sono la stessa, a meno delle cifre."""
    pagine_per_chiave: dict[str, set[int]] = {}
    for n, righe in enumerate(pagine):
        for r in righe:
            if _nel_margine(r, altezze[n]) and not _ha_celle(r, colonne):
                pagine_per_chiave.setdefault(_chiave_ripetuta(_testo(r)), set()).add(n)
    return {k for k, p in pagine_per_chiave.items() if len(p) >= 2}


def _scartata(r: RigaFisica, altezza: float, colonne: list[Colonna], ripetute: set[str]) -> bool:
    """Righe che non sono del prospetto: margini ripetuti, piedi «Pagina N di M», «Pag. N», «Utente:», il
    numero di pagina nudo, le intestazioni di colonna («ESERCIZIO 2025 ESERCIZIO 2024»)."""
    if _ha_celle(r, colonne):
        return False
    testo = _testo(r)
    if _nel_margine(r, altezza) and _chiave_ripetuta(testo) in ripetute and not _intestazione(testo):
        return True
    return bool(_PIEDE.search(_norm(testo)) or re.fullmatch(r"\d{1,3}", testo.strip())
                or _e_riga_testata(r))


def _titolo_sezione(r: RigaFisica, colonne: list[Colonna]) -> str | None:
    """La sezione che una riga-titolo apre (`detail_enrichment.collect_source_rows`); solo una riga senza
    importi: «UTILE DA CONTO ECONOMICO 5.000,00» nel passivo non apre il CE."""
    if _ha_celle(r, colonne):
        return None
    compatto = re.sub(r"\s+", "", _testo(r).upper())
    if "STATOPATRIMONIALE" in compatto or "SITUAZIONEPATRIMONIALE" in compatto:
        return "SP"
    if "CONTOECONOMICO" in compatto or "SITUAZIONEECONOMICA" in compatto:
        return "CE"
    if "CONTINONASSEGNATI" in compatto or compatto.startswith("NOTAINTEGRATIVA"):
        return ""
    return None


def _tuple(righe: list[RigaFisica]) -> list[list[tuple]]:
    return [[(p.x0, p.y0, p.x1, p.y1, p.testo) for p in r.parole] for r in righe]


def _sezioni(pagine: list[list[RigaFisica]], colonne: list[Colonna]) -> list[list[str]]:
    """Per pagina e riga, la sezione: l'ultimo titolo sopra la riga; sopra il primo titolo, la sezione della
    pagina prima finche' quella non si e' chiusa col suo totale; una pagina senza titoli che chiude con un
    totale dell'altra sezione decide da se' (`collect_source_rows` 255-267, `_sezione_della_chiusura`)."""
    ultima, chiusa = "", False
    out = []
    for righe in pagine:
        titoli = [(r.y, s) for r in righe if (s := _titolo_sezione(r, colonne)) is not None]
        grezze = _tuple(righe)
        chiusura = _SEZIONI.get(_sezione_della_chiusura(grezze) or "")
        if ultima and not chiusa and (titoli or chiusura in (None, ultima)):
            pagina = ultima
        elif not titoli and chiusura is not None:
            pagina = chiusura
        else:
            pagina = ultima if not chiusa else ""
        sezioni = []
        for r in righe:
            s = pagina
            for y, sezione in titoli:
                if y <= r.y + 2:
                    s = sezione
            sezioni.append(s)
        out.append(sezioni)
        ultima = titoli[-1][1] if titoli else pagina
        chiusa = _chiude_sezione(grezze)
    return out


# --------------------------------------------------------------------------------------
# Unioni: importo orfano, didascalia a capo
# --------------------------------------------------------------------------------------

def _passo(pezzi: list[_Pezzo]) -> float:
    salti = [b.y - a.y for a, b in zip(pezzi, pezzi[1:]) if b.y - a.y > 0.5]
    return statistics.median(salti) if salti else 0.0


def _sovrapposizione(a: _Pezzo, b: _Pezzo) -> float:
    altezza = a.y1 - a.y0
    return max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0)) / altezza if altezza > 0 else 0.0


def _unisci(sopra: _Pezzo, sotto: _Pezzo, *, sillaba: bool = False) -> _Pezzo:
    etichetta = (sopra.etichetta[:-1] + sotto.etichetta if sillaba
                 else " ".join(t for t in (sopra.etichetta, sotto.etichetta) if t))
    return _Pezzo(sopra.pagina, sopra.lato, sopra.y, max(sopra.y_ultima, sotto.y_ultima),
                  min(sopra.y0, sotto.y0), max(sopra.y1, sotto.y1), sopra.sezione,
                  sopra.codice or sotto.codice, etichetta, {**sopra.celle, **sotto.celle})


def _solo_importi(p: _Pezzo) -> bool:
    return bool(p.celle) and not p.etichetta and not p.codice


def _didascalia_nuda(p: _Pezzo) -> bool:
    return not p.celle and bool(p.etichetta)


def _riattacca_orfani(pezzi: list[_Pezzo]) -> list[_Pezzo]:
    """Un importo stampato qualche punto sopra o sotto la propria didascalia senza importi le si riattacca
    (a parita', a quella sopra)."""
    out = list(pezzi)
    i = 0
    while i < len(out):
        p = out[i]
        if _solo_importi(p):
            vicine = [j for j in (i - 1, i + 1) if 0 <= j < len(out) and _didascalia_nuda(out[j])
                      and (abs(out[j].y_ultima - p.y) <= _DISTANZA_ORFANO
                           or _sovrapposizione(p, out[j]) >= _SOVRAPPOSIZIONE_ORFANO)]
            if vicine:
                j = min(vicine, key=lambda k: (abs(out[k].y - p.y), k))
                a, b = (out[j], p) if j < i else (p, out[j])
                out[min(i, j)] = _unisci(a, b)
                del out[max(i, j)]
                i = min(i, j)
                continue
        i += 1
    return out


def _strutturale(etichetta: str) -> bool:
    return bool(_forma_strutturale(etichetta) or _intestazione(etichetta))


def _a_capo(pezzi: list[_Pezzo]) -> list[_Pezzo]:
    """Le didascalie andate a capo (`_grezze_pdf` e `_unisci_a_capo`): una riga senza importi ne' codice
    piu' vicina di 0,7 interlinee alla riga sopra ne e' il seguito, qualunque sia la maiuscola; la riga senza
    importi che finisce a meta' frase o a meta' parola si completa con quella sotto; il seguito in minuscolo
    senza importi di una riga che li ha gia' le si aggiunge. Vale anche per le righe-conto."""
    passo = _passo(pezzi)
    out: list[_Pezzo] = []
    for p in pezzi:
        if out:
            sopra = out[-1]
            nuda = not p.celle and not p.codice and p.etichetta and not _strutturale(p.etichetta)
            salto = p.y - sopra.y_ultima
            vicina = passo and salto < _A_CAPO * passo
            # le altre due regole non guardano l'interlinea, ma non scavalcano un vuoto (una riga saltata)
            adiacente = not passo or salto <= _ADIACENTE * passo
            if nuda and vicina:
                out[-1] = _unisci(sopra, p)
                continue
            sillaba = bool(re.search(r"[^\W\d_]-$", sopra.etichetta))
            if (adiacente and not sopra.celle and sopra.etichetta and not p.codice and p.etichetta
                    and not _intestazione(sopra.etichetta) and not _strutturale(p.etichetta)
                    and (_frase_aperta(sopra.etichetta) or sillaba)):
                out[-1] = _unisci(sopra, p, sillaba=sillaba)
                continue
            if adiacente and sopra.celle and nuda and p.etichetta[:1].islower():
                out[-1] = _unisci(sopra, p)
                continue
        out.append(p)
    return out


# --------------------------------------------------------------------------------------
# Lettura
# --------------------------------------------------------------------------------------

def _pezzi_della_riga(r: RigaFisica, sezione: str, colonne: list[Colonna], confine: float | None,
                      avvisi: list[str]) -> list[_Pezzo]:
    """Una riga fisica -> un pezzo per lato (uno solo senza confine)."""
    if confine is None:
        gruppi = {"U": r.parole}
    else:
        gruppi = {"L": [p for p in r.parole if (p.x0 + p.x1) / 2 < confine],
                  "R": [p for p in r.parole if (p.x0 + p.x1) / 2 >= confine]}
    out = []
    for lato, parole in gruppi.items():
        if not parole:
            continue
        celle, testo = _celle_del_lato(parole, colonne, lato, r.pagina, avvisi)
        codice, etichetta = _codice([p.testo for p in testo], bool(celle))
        etichetta_testo = " ".join(etichetta).strip()
        controllo = (codice + " " + etichetta_testo).upper()
        if _ANAGRAFICA.search(etichetta_testo.upper()) or _RIPORTO.search(controllo) \
                or (not celle and _IMPORTI.search(controllo)):
            continue
        if not celle and not codice and not etichetta_testo:
            continue
        out.append(_Pezzo(r.pagina, lato, r.y, r.y, min(p.y0 for p in parole), max(p.y1 for p in parole),
                          sezione, codice, etichetta_testo, celle))
    return out


def leggi_pdf(file_path: str) -> Documento:
    """Le righe logiche di un PDF dal suo text layer; senza testo, un documento vuoto con l'avviso."""
    avvisi: list[str] = []
    pagine: list[list[RigaFisica]] = []
    altezze: list[float] = []
    with fitz.open(file_path) as documento:
        for n, pagina in enumerate(documento, start=1):
            righe = righe_fisiche(parole_pagina(pagina), n)
            for r in righe:
                r.parole = _ricuci(r.parole)
            pagine.append(righe)
            altezze.append(float(pagina.rect.height))
    if not any(pagine):
        return Documento([], [], False, ["nessun testo: serve l'OCR"])
    colonne = colonne_documento([r for righe in pagine for r in righe])
    if not colonne:
        avvisi.append("nessuna colonna di importi riconosciuta")
    ripetute = _ripetute(pagine, altezze, colonne)
    pagine = [[r for r in righe if not _scartata(r, altezze[n], colonne, ripetute)]
              for n, righe in enumerate(pagine)]
    tutte = [r for righe in pagine for r in righe]
    confine = confine_dei_lati(tutte, colonne)
    assegna_lati(colonne, confine)
    sezioni = _sezioni(pagine, colonne)

    righe_doc: list[Riga] = []
    for righe, sezioni_pag in zip(pagine, sezioni):
        per_lato: dict[str, list[_Pezzo]] = {}
        for r, sezione in zip(righe, sezioni_pag):
            for pezzo in _pezzi_della_riga(r, sezione, colonne, confine, avvisi):
                per_lato.setdefault(pezzo.lato, []).append(pezzo)
        for lato in sorted(per_lato, key=_ORDINE_LATI.get):
            pezzi = _a_capo(_riattacca_orfani(per_lato[lato]))
            for k, p in enumerate(pezzi, start=1):
                righe_doc.append(Riga(id=f"p{p.pagina}r{k}{lato}", pagina=p.pagina, y=p.y, lato=lato,
                                      sezione=p.sezione, codice=p.codice, etichetta=p.etichetta,
                                      celle=dict(sorted(p.celle.items())),
                                      intestazione=not p.celle and bool(p.etichetta)))
    return Documento(righe_doc, colonne, confine is not None, avvisi)
