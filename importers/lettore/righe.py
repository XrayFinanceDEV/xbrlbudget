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
from dataclasses import dataclass, field

import fitz

from importers.lettore.colonne import Colonna
from importers.lettore.geometria import Parola, RigaFisica, parole_pagina, righe_fisiche
from importers.lettore.importi import Importo, leggi_importo
# Le regole di livello documento stanno nel profilo (Task 5-bis); il Task 5-ter le fara' leggere dal Profilo.
from importers.lettore.profilo import (
    _SEPARATORE, _VALUTA, Profilo, _capitale_in_anagrafica, _codici_senza_importi, _in_colonna, _norm,
    _rimando_di_nota, _scartata, _sezioni, _valuta_davanti, profilo_documento)
from importers.schema_legge_generico import _forma_strutturale, _intestazione
from importers.standard_ivcee_parser import riga_conto
from importers.xbrl_reso_parser import _frase_aperta

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
_SCADENZA = {"mesi", "mese", "anni", "anno", "m"}
_ORDINE_LATI = {"U": 0, "L": 1, "R": 2}

# Anagrafiche e riporti (`situazione_contabile_parser._be_collect_side_facts`): non sono righe del prospetto.
_ANAGRAFICA = re.compile(r"^(?:VIA|VIALE|V\.LE|PIAZZA|P\.ZZA|CORSO|C\.F\.|P\.\s?IVA|REA)\b|CODICE FISCALE|PARTITA IVA")
# A parola intera: «SEGUENTE» («esercizio seguente») non e' un riporto.
_RIPORTO = re.compile(r"\bA\s+RIPORT\w*|\bRIPORTO\b|\bRIPORTARE\b|\bSEGUE\b|\bPROGRESSIV\w*")
_IMPORTI = re.compile(r"\bIMPORTI\b")
# Il token davanti a un numero che lo fa un riferimento, non un importo («art. 2423», «REA n. 1234567»).
_RIFERIMENTO = {"art.", "art", "artt.", "n.", "n", "nr.", "nr", "n°", "num.", "numero", "rea", "p.iva", "piva",
                "p.i.", "iva", "c.f.", "cf", "cap", "cap.", "c.a.p.", "ateco", "codice", "cod.", "tel.", "fax",
                "prot.", "comma", "lett.", "mutuo", "contratto"}
_ANNO = re.compile(r"^(?:19|20)\d{2}$")
_CODICE_AGO = (re.compile(r"^\d{6}$"), re.compile(r"^\d{3}$"))
_TAG_IVCEE = re.compile(r"^[a-e](?:[ivx]+\d*[a-z]?|\d+[a-z]?)?$")


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
    parole: list[str] = field(default_factory=list)   # etichetta in token, codice compreso se non separato
    x0: float = 0.0                                   # bordo sinistro del primo token (codice o etichetta)
    conto: bool = False                               # conto senza importo: non un titolo
    tutti: list[str] = field(default_factory=list)      # i token della riga fisica, codice e separatori compresi
    x_token: list[float] = field(default_factory=list)  # e i loro x0


# --------------------------------------------------------------------------------------
# Token
# --------------------------------------------------------------------------------------

def _normalizza(testo: str) -> str:
    """Il token come lo legge `leggi_importo`: meno Unicode e trattino lungo davanti alle cifre, spazi non
    separabili tolti, marcatore D/A attaccato («1.234,56D») staccato. Solo se il risultato e' un importo;
    altrimenti il testo resta com'e' stampato."""
    t = testo
    for spazio in ("\u00a0", "\u202f", "\u2009"):
        t = t.replace(spazio, "")
    t = re.sub("^(\\(?)[\u2212\u2013](?=\\d)", r"\1-", t)
    t = re.sub("(?<=\\d)[\u2212\u2013](\\)?)$", r"-\1", t)
    m = re.fullmatch(r"(.*\d\)?)([DA])", t)
    if m:
        t = f"{m.group(1)} {m.group(2)}"
    return t if t != testo and leggi_importo(t) is not None else testo


def _ricuci(parole: list[Parola], stampati: dict[Parola, str]) -> list[Parola]:
    """Normalizza i token e ricuce la parentesi aperta staccata dall'importo («(» + «1.234,56)»). In
    `stampati` resta il testo come stampato di ogni parola cambiata, per `Importo.testo`."""
    out: list[Parola] = []
    for originale in parole:
        p = Parola(originale.x0, originale.y0, originale.x1, originale.y1, _normalizza(originale.testo))
        if p.testo != originale.testo:
            stampati[p] = originale.testo
        prima = out[-1] if out else None
        if (prima is not None and prima.testo == "(" and p.x0 - prima.x1 <= _STACCO_PARENTESI
                and p.testo[:1].isdigit()):
            unita = Parola(prima.x0, min(prima.y0, p.y0), p.x1, max(prima.y1, p.y1), "(" + p.testo)
            stampati[unita] = "(" + stampati.get(p, p.testo)
            out[-1] = unita
            continue
        out.append(p)
    return out


# --------------------------------------------------------------------------------------
# Celle
# --------------------------------------------------------------------------------------

def _riferimento_davanti(parole: list[Parola], i: int) -> bool:
    if i == 0:
        return False
    prima = re.split(r"['\u2019]", parole[i - 1].testo.lower().strip(":"))[-1]
    return prima in _RIFERIMENTO


def _celle_del_lato(parole: list[Parola], colonne: list[Colonna], lato: str, pagina: int,
                    avvisi: list[str], stampati: dict[Parola, str],
                    intere: frozenset[int] = frozenset()) -> tuple[dict[int, Importo], list[Parola]]:
    """(celle per colonna, parole dell'etichetta). Un importo e' una cella solo nella sua colonna e sul suo
    lato; fuori colonna, seguito da una durata («12 mesi») o dentro una frase dopo una valuta («euro 516,46
    di valore unitario», o in un'anagrafica col capitale sociale) torna nell'etichetta. Un anno nudo su una
    riga senza altri importi resta testo. Due importi nella stessa colonna: la cella non si legge. La valuta
    davanti a una cella, o in coda all'etichetta, si toglie."""
    trovati = [_in_colonna(p, colonne, intere) for p in parole]
    for i, p in enumerate(parole[:-1]):
        # l'importo seguito da un rimando di nota («46.078 (1)») sta nella colonna dove il rimando la chiude
        if trovati[i] is None and _rimando_di_nota(parole, i + 1):
            trovati[i] = _in_colonna(Parola(p.x0, p.y0, parole[i + 1].x1, p.y1, p.testo), colonne, intere)
    trovati = [None if t is None or t[1].lato != lato or _rimando_di_nota(parole, i)
               or (leggi_importo(p.testo) is None and _riferimento_davanti(parole, i)) else t
               for i, (p, t) in enumerate(zip(parole, trovati))]
    # un trattino seguito da una parola e' un separatore («PRESTAZ. - IMPRESE»), e un intero nudo davanti a quel
    # separatore o a una parola e' un codice («Codice attivita' 255100 - LAVORAZ.»): si legge da destra, perche'
    # il trattino decide per l'intero. Davanti a un importo il trattino resta una cella zero.
    separatori: set[int] = set()
    for i in range(len(parole) - 2, -1, -1):
        dopo = parole[i + 1].testo
        segue_testo = any(ch.isalpha() for ch in dopo) or (i + 1 in separatori and dopo == "-")
        if trovati[i] is not None and segue_testo and (
                parole[i].testo == "-" or leggi_importo(parole[i].testo) is None):
            trovati[i] = None
            separatori.add(i)
    anni = {i for i, (p, t) in enumerate(zip(parole, trovati)) if t is not None and _ANNO.match(p.testo)}
    if anni and all(t is None or i in anni for i, t in enumerate(trovati)):
        trovati = [None if i in anni else t for i, t in enumerate(trovati)]
    capitale = _capitale_in_anagrafica(parole, colonne)
    celle: dict[int, Importo] = {}
    sedi: dict[int, list[Parola]] = {}
    testo: list[int] = []
    for i, (p, trovato) in enumerate(zip(parole, trovati)):
        dopo = parole[i + 1].testo.lower().strip(".,:;") if i + 1 < len(parole) else ""
        if (trovato is None or dopo in _SCADENZA
                or (_valuta_davanti(parole, i)
                    and (capitale or (any(ch.isalpha() for ch in dopo) and dopo not in _VALUTA)))):
            testo.append(i)
            continue
        imp, c = trovato
        sedi.setdefault(c.indice, []).append(p)
        celle[c.indice] = Importo(imp.valore, imp.forma, stampati.get(p, p.testo))
    for indice, ps in sedi.items():
        # davanti a un importo vero, l'intero nudo nella stessa colonna cede (budget_1438, colonne della nota)
        nudi = [p for p in ps if leggi_importo(p.testo) is None]
        if len(ps) > 1 and len(nudi) < len(ps):
            testo.extend(parole.index(p) for p in nudi)
            ps = [p for p in ps if p not in nudi]
            celle[indice] = next(Importo(t[0].valore, t[0].forma, stampati.get(q, q.testo))
                                 for q, t in zip(parole, trovati) if q is ps[-1])
        if len(ps) > 1 and not any(leggi_importo(p.testo) is not None for p in ps):
            # solo interi nudi: le colonne di una tabella della nota, non quelle del documento; restano testo
            del celle[indice]
            testo.extend(parole.index(p) for p in ps)
            continue
        if len(ps) > 1:
            del celle[indice]
            testo.extend(parole.index(p) for p in ps)
            avvisi.append(f"pagina {pagina}: due importi nella colonna {indice} sulla stessa riga "
                          f"({' '.join(p.testo for p in ps)}): cella non letta")
    in_cella = set(range(len(parole))) - set(testo)
    etichetta = [parole[i] for i in sorted(testo, key=lambda i: parole[i].x0)
                 if not (_norm(parole[i].testo) in _VALUTA and i + 1 in in_cella)]
    while etichetta and _norm(etichetta[-1].testo) in _VALUTA:
        etichetta.pop()
    return celle, etichetta


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
                  sopra.codice or sotto.codice, etichetta, {**sopra.celle, **sotto.celle},
                  sopra.parole + sotto.parole, sopra.x0, sopra.conto or sotto.conto, sopra.tutti, sopra.x_token)


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
                      avvisi: list[str], stampati: dict[Parola, str],
                      intere: frozenset[int] = frozenset()) -> list[_Pezzo]:
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
        celle, testo = _celle_del_lato(parole, colonne, lato, r.pagina, avvisi, stampati, intere)
        codice, etichetta = _codice([p.testo for p in testo], bool(celle))
        etichetta_testo = " ".join(etichetta).strip()
        controllo = (codice + " " + etichetta_testo).upper()
        if _ANAGRAFICA.search(etichetta_testo.upper()) or _RIPORTO.search(controllo) \
                or (not celle and _IMPORTI.search(controllo)):
            continue
        if not celle and not codice and not etichetta_testo:
            continue
        out.append(_Pezzo(r.pagina, lato, r.y, r.y, min(p.y0 for p in parole), max(p.y1 for p in parole),
                          sezione, codice, etichetta_testo, celle, etichetta,
                          testo[0].x0 if testo else parole[0].x0, False, [p.testo for p in testo],
                          [p.x0 for p in testo]))
    return out


def _pagine_pdf(file_path: str) -> tuple[list[list[RigaFisica]], list[float], dict[Parola, str]]:
    """Le righe fisiche di ogni pagina coi token ricuciti, le altezze delle pagine e il testo stampato dei token
    cambiati."""
    pagine: list[list[RigaFisica]] = []
    altezze: list[float] = []
    stampati: dict[Parola, str] = {}
    with fitz.open(file_path) as documento:
        for n, pagina in enumerate(documento, start=1):
            righe = righe_fisiche(parole_pagina(pagina), n)
            for r in righe:
                r.parole = _ricuci(r.parole, stampati)
            pagine.append(righe)
            altezze.append(float(pagina.rect.height))
    return pagine, altezze, stampati


def profilo_pdf(file_path: str) -> Profilo:
    """Il profilo del documento di un PDF, sulle stesse righe fisiche che legge `leggi_pdf`."""
    pagine, altezze, _ = _pagine_pdf(file_path)
    return profilo_documento([r for righe in pagine for r in righe],
                             altezze={n: h for n, h in enumerate(altezze, start=1)})


def leggi_pdf(file_path: str) -> Documento:
    """Le righe logiche di un PDF dal suo text layer; senza testo, un documento vuoto con l'avviso."""
    avvisi: list[str] = []
    pagine, altezze, stampati = _pagine_pdf(file_path)
    if not any(pagine):
        return Documento([], [], False, ["nessun testo: serve l'OCR"])
    # colonne, margini, lati e interi in colonna dal profilo; il resto delle regole di documento il Task 5-ter
    profilo = profilo_documento([r for righe in pagine for r in righe],
                                altezze={n: h for n, h in enumerate(altezze, start=1)})
    colonne, confine = profilo.colonne, profilo.confine
    if not colonne:
        avvisi.append("nessuna colonna di importi riconosciuta")
    ripetute = set(profilo.margini)
    pagine = [[r for r in righe if not _scartata(r, altezze[n], colonne, ripetute)]
              for n, righe in enumerate(pagine)]
    sezioni = _sezioni(pagine, colonne, avvisi)
    intere = frozenset(i for i, d in profilo.decimali.items() if d is False)

    sequenze: list[list[_Pezzo]] = []
    for righe, sezioni_pag in zip(pagine, sezioni):
        per_lato: dict[str, list[_Pezzo]] = {}
        for r, sezione in zip(righe, sezioni_pag):
            for pezzo in _pezzi_della_riga(r, sezione, colonne, confine, avvisi, stampati, intere):
                per_lato.setdefault(pezzo.lato, []).append(pezzo)
        sequenze += [per_lato[lato] for lato in sorted(per_lato, key=_ORDINE_LATI.get)]
    _codici_senza_importi(sequenze)

    righe_doc: list[Riga] = []
    for seq in sequenze:
        pezzi = _a_capo(_riattacca_orfani(seq))
        for k, p in enumerate(pezzi, start=1):
            righe_doc.append(Riga(id=f"p{p.pagina}r{k}{p.lato}", pagina=p.pagina, y=p.y, lato=p.lato,
                                  sezione=p.sezione, codice=p.codice, etichetta=p.etichetta,
                                  celle=dict(sorted(p.celle.items())),
                                  intestazione=not p.celle and bool(p.etichetta) and not p.conto))
    return Documento(righe_doc, colonne, confine is not None, avvisi)
