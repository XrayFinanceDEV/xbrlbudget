"""Schema di legge con il PERCORSO nell'etichetta: la "Situazione contabile riclassificata
dettagliata" (BILAQ, detail_riclass, 2R Immobiliare, Santini 31/12/2025...).

Ogni riga e' "Cod. | Descrizione | esercizio | precedente | Differenza | Scost. %", e la
descrizione comincia col percorso di legge: "B.I.2) Costi di sviluppo", "C.II.5 bis.1) Esigibili
entro l'esercizio successivo", "D.11 bis) Debiti verso imprese sottoposte...", "20) Imposte".
Sotto ogni voce il gestionale stampa i propri dettagli: sotto-righe col percorso allungato
("B.I.2.b) (Fondi di ammortamento)", "B.6.2) Materie prime") e i conti ("3020200 COSTI DI
RICERCA"). Ogni livello stampa il proprio totale.

La voce non si indovina dalla descrizione: il percorso si traduce nel campo (``percorsi.
campo_da_percorso``, la tabella dei lettori deterministici). Si legge SOLO la voce di legge,
mai una sotto-riga del gestionale ne' un conto: il valore della voce e' gia' netto dei fondi e
comprende i propri dettagli. Unica eccezione, le righe "Esigibili entro/oltre" sotto crediti e
debiti, che sono la scadenza voluta dall'art. 2424 e decidono fra breve e lungo.

Il totale stampato decide: ogni totale (B, B.I, C.II, D, il totale dell'attivo...) deve essere
uguale alla somma delle voci lette sotto di lui. Un solo totale che non torna e l'anno non si
adotta (``rifiuto`` nomina quale): nessun importo corretto, nessun tappo. Le regole di adozione
restano poi quelle di tutti i lettori deterministici.

Le righe arrivano da due sorgenti con lo stesso significato: il layer di testo del PDF
(``estrai``, colonne lette dalla geometria) e le tabelle di MinerU di una scansione
(``estrai_da_mineru``, celle, con la colonna Differenza a ricomporre le cifre che l'OCR sposta
da una cella alla successiva).
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from typing import Iterable, Optional

from importers.import_snello.percorsi import campo_da_percorso, completa

_C = Decimal("0.01")
_TOLLERANZA = Decimal("0.05")
_MIN_VOCI = 10

# percorso all'inizio dell'etichetta, fino alla parentesi: "B.I.2", "C.II.5 bis.1", "20.a", "21"
_PERCORSO = re.compile(r"^\s*((?:[A-E]|\d{1,2})(?:[.\s][A-Za-z0-9-]+)*)\)\s*(.*)$")
_SUFFISSO = re.compile(r"\s+(bis|ter|quater)\b", re.I)
_SCADENZA = re.compile(r"esigibil\w*\s+(entro|oltre)")
_IMPORTO = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2}")
_IMPORTO_PIENO = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}-?$")
_PERCENTUALE = re.compile(r"-?\d{1,3}(?:\.\d{3})*,\d{2,3}")
_DATA = re.compile(r"^\d{1,2}[/.]\d{1,2}[/.]((?:19|20)\d{2})$")
_LETTERE = re.compile(r"[A-Za-zÀ-ÿ]")

# voci di A) Valore della produzione: la convenzione dell'albero di legge condiviso
# (data/iv_cee_tree.json), quella che leggono Rettifiche e Confronto: A.4 in ce03, mai in ce03a
_VALORE_PRODUZIONE = {"1": "ce01", "2": "ce02", "3": "ce02", "4": "ce03", "5": "ce04"}


def _norm(testo: str) -> str:
    t = unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


def _importo(testo: str) -> Decimal:
    neg = testo.endswith("-")
    v = Decimal(testo.rstrip("-").replace(".", "").replace(",", "."))
    return -v if neg else v


def _sezione(etichetta: str) -> Optional[str]:
    n = _norm(etichetta)
    if n.startswith("stato patrimoniale attivo"):
        return "SPA"
    if n.startswith("stato patrimoniale passivo"):
        return "SPP"
    if n.startswith("conto economico"):
        return "CE"
    return None


_ROMANO_OCR = re.compile(r"^[IVXlivx]+$")


def percorso(etichetta: str) -> Optional[tuple[str, ...]]:
    """"C.II.5 bis.1) Esigibili entro" -> ("C", "II", "5-bis", "1"); None senza percorso."""
    m = _PERCORSO.match(etichetta or "")
    if not m:
        return None
    testo = _SUFFISSO.sub(lambda s: "-" + s.group(1).lower(), m.group(1))
    parti = [p for p in re.split(r"[.\s]+", testo) if p]
    # il secondo livello di B), C) e A) e' un numero romano: l'OCR legge "C.Il.5" con la elle
    if len(parti) >= 2 and parti[0] in ("A", "B", "C") and _ROMANO_OCR.match(parti[1]):
        parti[1] = parti[1].upper().replace("L", "I")
    return tuple(parti) or None


def _scadenza(etichetta: str) -> Optional[str]:
    m = _SCADENZA.search(_norm(etichetta))
    return None if m is None else ("E" if m.group(1) == "entro" else "O")


# --------------------------------------------------------------------------- #
# Ruolo di una riga: voce di legge, totale, scadenza, dettaglio del gestionale
# --------------------------------------------------------------------------- #
def _famiglia_con_scadenza(sez: str, t: tuple[str, ...]) -> Optional[tuple[str, ...]]:
    """La voce di crediti/debiti sotto cui una riga "Esigibili entro/oltre" e' la scadenza."""
    if sez == "SPA" and len(t) >= 3 and t[:3] == ("B", "III", "2"):
        return t[:3]
    if sez == "SPA" and len(t) >= 3 and t[:2] == ("C", "II"):
        return t[:3]
    if sez == "SPP" and len(t) >= 2 and t[0] == "D":
        return t[:2]
    return None


def _profondita_voce(sez: str, t: tuple[str, ...]) -> Optional[int]:
    """Quanti livelli ha la voce di legge del ramo di ``t`` (None: ramo sconosciuto)."""
    r = t[0]
    if sez == "SPA":
        if r in ("A", "D"):
            return 1
        if r == "B":
            return 3
        if r == "C" and len(t) >= 2:
            return 3 if t[1] in ("I", "II") else 2
        return None
    if sez == "SPP":
        if r in ("C", "E"):
            return 1
        if r in ("A", "B", "D"):
            return 2
        return None
    if sez == "CE":
        if r == "20":
            return 1
        if r in ("A", "B", "C", "D"):
            if r == "B" and len(t) >= 3 and t[1] in ("9", "10") and len(t[2]) == 1 and t[2].isalpha():
                return 3
            return 2
    return None


def _campo(sez: str, t: tuple[str, ...], scad: Optional[str] = None) -> Optional[str]:
    if sez == "CE":
        if t[0] == "A" and len(t) == 2:
            return _VALORE_PRODUZIONE.get(t[1])
        return campo_da_percorso(".".join(("CE", *t)))
    p = ".".join((sez, *t, *((scad,) if scad else ())))
    return campo_da_percorso(p)


def _segno(sez: str, t: tuple[str, ...]) -> int:
    """Nel totale stampato C) la voce 17 si sottrae, in D) la 19: e' l'unica somma con segno."""
    if sez == "CE" and len(t) >= 2 and (t[0], t[1]) in (("C", "17"), ("D", "19")):
        return -1
    return 1


def _leggi_anno(voci: list[dict], anno: int) -> dict:
    """Le voci di un anno (0 esercizio, 1 precedente): importi per campo e totali stampati,
    oppure ``rifiuto`` col totale che non torna."""
    # Una voce con un'articolazione di legge sotto di se' - crediti e debiti con le righe
    # "Esigibili entro/oltre", B.9 / B.10 con le lettere a), b)... - si legge dai figli, MA
    # solo se in QUESTO anno i figli portano l'importo: un anno stampato sul solo totale
    # ("C.II.1) Verso clienti 218.669" senza entro/oltre, budget_372) conta la voce, a breve
    # per prudenza come ogni scadenza non dichiarata. Mai voce e figli insieme.
    figli_di: dict[int, list[dict]] = {}
    padre_di: dict[int, dict] = {}
    for v in voci:
        if v["ruolo"] != "voce":
            continue
        if v["sez"] == "CE" and len(v["t"]) == 2:
            figli = [f for f in voci if f["ruolo"] == "voce" and f["sez"] == "CE"
                     and len(f["t"]) == 3 and f["t"][:2] == v["t"]]
        else:
            figli = [f for f in voci if f["ruolo"] == "scadenza" and f["sez"] == v["sez"]
                     and f["famiglia"] == v["t"]]
        if figli:
            figli_di[id(v)] = figli
            for f in figli:
                padre_di[id(f)] = v

    def _dai_figli(padre: dict) -> bool:
        return (any(f["valori"][anno] not in (None, Decimal(0)) for f in figli_di[id(padre)])
                or padre["valori"][anno] in (None, Decimal(0)))

    contate: list[dict] = []
    for v in voci:
        if v["ruolo"] not in ("voce", "scadenza"):
            continue
        if id(v) in figli_di:
            if not _dai_figli(v):
                contate.append(v)
        elif id(v) in padre_di:
            if _dai_figli(padre_di[id(v)]):
                contate.append(v)
        else:
            contate.append(v)
    # un totale stampato senza nessuna voce valorizzata sotto di lui in quest'anno e' la voce
    # stessa (un fondo rischi unico, l'anno precedente stampato sui soli totali, budget_372):
    # mai perso. Dal piu' interno, perche' padre e figlio non contino entrambi.
    for v in sorted((v for v in voci if v["ruolo"] == "totale"), key=lambda v: -len(v["t"])):
        if v["valori"][anno] in (None, Decimal(0)) or not _campo(v["sez"], v["t"]):
            continue
        if not any(_sotto(c, v) and c["valori"][anno] not in (None, Decimal(0)) for c in contate):
            contate.append(v)
    contati = {id(c) for c in contate}

    importi: dict[str, Decimal] = {}
    massa_ignota = Decimal(0)
    for v in contate:
        valore = v["valori"][anno]
        if valore is None:
            return {"rifiuto": f"{v['sez']}.{'.'.join(v['t'])} senza importo"}
        campo = (_campo(v["sez"], v["famiglia"], v["scad"]) if v["ruolo"] == "scadenza"
                 else _campo(v["sez"], v["t"]))
        if campo is None:
            massa_ignota += abs(valore)
            continue
        importi[campo] = importi.get(campo, Decimal(0)) + valore

    # Un anno stampato in euro interi (budget_372, precedente da un abbreviato) arrotonda ogni
    # voce di mezzo euro al piu': il totale puo' scostarsi di tanto, non di piu'.
    interi = all(v["valori"][anno] is None or v["valori"][anno] == v["valori"][anno].to_integral_value()
                 for v in voci)

    def _tolleranza(n: int) -> Decimal:
        return Decimal("0.5") * (n + 1) if interi else _TOLLERANZA

    # il totale stampato decide: ogni riga sopra le voci lette deve esserne la somma. Si
    # nomina il totale piu' interno che non torna, quello da guardare sul documento.
    scarti = []
    for v in voci:
        if v["ruolo"] not in ("totale", "voce") or id(v) in contati:
            continue
        sotto = [c for c in contate if _sotto(c, v)]
        if not sotto or v["valori"][anno] is None:
            continue
        somma = sum((_segno(c["sez"], c["t"]) * c["valori"][anno] for c in sotto), Decimal(0))
        if abs(somma - v["valori"][anno]) > _tolleranza(len(sotto)):
            scarti.append((len(v["t"]), v, somma))
    if scarti:
        _, v, somma = max(scarti, key=lambda s: s[0])
        return {"rifiuto": f"{v['sez']}.{'.'.join(v['t'])} stampato {v['valori'][anno]}, "
                           f"voci lette {somma}"}
    stampati = {}
    for v in voci:
        if v["ruolo"] == "intestazione" and v["valori"][anno] is not None:
            chiave = {"SPA": "totale_attivo", "SPP": "totale_passivo"}.get(v["sez"])
            if chiave:
                stampati[chiave] = v["valori"][anno]
    for chiave, sez in (("totale_attivo", "SPA"), ("totale_passivo", "SPP")):
        if chiave not in stampati:
            return {"rifiuto": f"{chiave} non stampato"}
        della_sezione = [c for c in contate if c["sez"] == sez]
        somma = sum((c["valori"][anno] for c in della_sezione), Decimal(0))
        if abs(somma - stampati[chiave]) > _tolleranza(len(della_sezione)):
            return {"rifiuto": f"{chiave} stampato {stampati[chiave]}, voci lette {somma}"}
    utile = next((v["valori"][anno] for v in voci if v["ruolo"] == "risultato"), None)
    return {"importi": importi, "stampati": stampati, "utile": utile, "massa_ignota": massa_ignota}


def _sotto(c: dict, v: dict) -> bool:
    """La voce contata ``c`` sta sotto la riga ``v`` (stessa sezione, percorso piu' lungo)."""
    if c["sez"] != v["sez"]:
        return False
    return len(c["t"]) > len(v["t"]) and c["t"][:len(v["t"])] == v["t"]


def _voci(righe: Iterable[tuple[str, Optional[Decimal], Optional[Decimal]]]) -> Optional[list[dict]]:
    sez = None
    voci: list[dict] = []
    sezioni = set()
    visti: set[tuple] = set()
    for etichetta, corrente, precedente in righe:
        nuova = _sezione(etichetta)
        if nuova:
            sez = nuova
            sezioni.add(nuova)
            voci.append({"ruolo": "intestazione", "sez": sez, "t": (),
                         "valori": (corrente, precedente)})
            continue
        t = percorso(etichetta)
        if t is None or sez is None:
            continue
        # il gestionale ripete il percorso della voce sulla propria sotto-riga ("1950
        # A.IV) Riserva legale" e sotto "1970 A.IV) Riserva legale", budget_147): la prima e'
        # la voce, la ripetizione un dettaglio, mai contato due volte
        if (sez, t) in visti:
            continue
        visti.add((sez, t))
        # lo zero non si stampa (nicee: "D.6) Acconti | | 3.000,00"): accanto a un importo,
        # la cella vuota vale zero, e i totali stampati la confermano o la smentiscono
        if corrente is None and precedente is not None:
            corrente = Decimal(0)
        elif precedente is None and corrente is not None:
            precedente = Decimal(0)
        valori = (corrente, precedente)
        if sez == "CE" and t[0] == "21" and len(t) == 1:
            voci.append({"ruolo": "risultato", "sez": sez, "t": t, "valori": valori})
            continue
        if sez != "CE" and t[0].isdigit():
            continue
        famiglia = _famiglia_con_scadenza(sez, t)
        scad = _scadenza(etichetta)
        if famiglia is not None and scad and len(t) > len(famiglia):
            voci.append({"ruolo": "scadenza", "sez": sez, "t": t, "famiglia": famiglia,
                         "scad": scad, "valori": valori})
            continue
        prof = _profondita_voce(sez, t)
        if prof is None:
            continue
        ruolo = "voce" if len(t) == prof else ("totale" if len(t) < prof else "dettaglio")
        if ruolo == "dettaglio":
            continue
        voci.append({"ruolo": ruolo, "sez": sez, "t": t, "valori": valori})
    percorsi_lunghi = sum(1 for v in voci if len(v["t"]) >= 2)
    if sezioni != {"SPA", "SPP", "CE"} or percorsi_lunghi < _MIN_VOCI:
        return None
    return voci


def _bilancio(letto: dict) -> tuple[dict, dict]:
    importi = dict(letto["importi"])
    rivalutazioni, svalutazioni = importi.get("ce17a", Decimal(0)), importi.get("ce17b", Decimal(0))
    bs, ce = completa({k: str(v) for k, v in importi.items()})
    if "ce17a" in importi or "ce17b" in importi:
        ce["ce17_rettifiche_attivita_fin"] = (rivalutazioni - svalutazioni).quantize(_C)
    bs["totale_attivo"] = letto["stampati"]["totale_attivo"]
    bs["totale_passivo"] = letto["stampati"]["totale_passivo"]
    bs["_source_schema_etichette"] = Decimal("1")
    bs["_unclassified_mass"] = letto["massa_ignota"].quantize(_C)
    bs["_plug_residual"] = Decimal("0")
    return bs, ce


def estrai_da_righe(righe) -> Optional[dict]:
    """None se le righe non sono di questa famiglia; altrimenti, per l'esercizio e per il
    precedente, ``bs``/``ce`` (nomi pieni di colonna), i totali stampati e l'utile stampato,
    oppure ``bs = ce = None`` col ``rifiuto`` che dice quale totale non torna."""
    voci = _voci(righe)
    if voci is None:
        return None
    out: dict = {}
    for anno, nome in ((0, ""), (1, "prior_")):
        attivo = next((v["valori"][anno] for v in voci
                       if v["ruolo"] == "intestazione" and v["sez"] == "SPA"), None)
        if attivo in (None, Decimal(0)):
            # colonna assente o tutta a zero (budget_371, prima annualita'): attivo = passivo
            # = 0 non e' un bilancio quadrato, e' un anno che il documento non porta
            out[nome + "bs"] = out[nome + "ce"] = None
            continue
        letto = _leggi_anno(voci, anno)
        if "rifiuto" in letto:
            out[nome + "bs"] = out[nome + "ce"] = None
            out[nome + "rifiuto"] = letto["rifiuto"]
            continue
        out[nome + "bs"], out[nome + "ce"] = _bilancio(letto)
        out[nome + "stampati"] = letto["stampati"]
        out[nome + "utile"] = letto["utile"]
    if out.get("bs") is None and out.get("prior_bs") is None and "rifiuto" not in out:
        return None
    return out


# --------------------------------------------------------------------------- #
# Sorgente 1: layer di testo del PDF
# --------------------------------------------------------------------------- #
def _colonne(parole) -> Optional[tuple[float, Optional[float], Optional[float], float]]:
    """Dall'intestazione: bordo destro delle colonne esercizio, precedente (None a colonna
    unica, budget_381), Differenza, e il bordo destro della colonna "Cod." (0 se la stampa
    non la porta, budget_282: l'etichetta parte allora dal margine)."""
    date = sorted((w for w in parole if _DATA.match(w[4])), key=lambda w: w[0])
    if not date:
        return None
    y_date = (date[0][1] + date[0][3]) / 2
    date = [w for w in date if abs((w[1] + w[3]) / 2 - y_date) <= 3]
    if not any(w[4].lower().startswith("descrizione") for w in parole):
        return None
    diff = next((w[2] for w in parole if w[4].lower().startswith("differenza")), None)
    cod = next((w[2] for w in parole if w[4].lower() == "cod."), 0.0)
    return date[0][2], (date[1][2] if len(date) > 1 else None), diff, cod


def _righe_pdf(file_path: str) -> tuple[list, tuple]:
    import fitz

    righe: list = []
    anni: tuple = ()
    colonne = None
    with fitz.open(file_path) as doc:
        for page in doc:
            parole = page.get_text("words")
            trovate = _colonne(parole)
            if trovate:
                colonne = trovate
                if not anni:
                    date = sorted((w for w in parole if _DATA.match(w[4])), key=lambda w: w[0])
                    anni = tuple(int(_DATA.match(w[4]).group(1)) for w in date[:2])
            if colonne is None:
                continue
            x_cor, x_prec, x_diff, x_cod = colonne
            limite_etichetta = x_cor - 60
            per_y: dict[int, list] = {}
            for w in parole:
                per_y.setdefault(round((w[1] + w[3]) / 2), []).append(w)
            in_attesa = None                        # (y, etichetta) senza importi
            for y in sorted(per_y):
                ws = sorted(per_y[y], key=lambda w: w[0])
                importi = [w for w in ws if _IMPORTO_PIENO.match(w[4]) and w[0] > limite_etichetta]
                etichetta = " ".join(w[4] for w in ws if w not in importi and w[0] > x_cod
                                     and w[2] < limite_etichetta + 20)
                valori: list[Optional[Decimal]] = [None, None, None]
                for w in importi:
                    distanze = [(abs(w[2] - x), i) for i, x in enumerate((x_cor, x_prec, x_diff))
                                if x is not None]
                    # gli importi sono allineati a destra un po' oltre l'intestazione (BILAQ:
                    # "31/12/2025" finisce a 360, gli importi a 373); le colonne distano ~70
                    d, i = min(distanze)
                    if d <= 30:
                        valori[i] = _importo(w[4])
                if valori[0] is None and valori[1] is None:
                    if etichetta and (percorso(etichetta) or _sezione(etichetta)):
                        in_attesa = (y, etichetta)
                    continue
                if not (etichetta and (percorso(etichetta) or _sezione(etichetta))):
                    if in_attesa and y - in_attesa[0] <= 9:
                        etichetta = in_attesa[1]
                    else:
                        etichetta = ""
                in_attesa = None
                if etichetta:
                    righe.append((etichetta, valori[0], valori[1]))
    return righe, anni


def riconosci(file_path: str) -> bool:
    try:
        righe, _ = _righe_pdf(file_path)
    except Exception:
        return False
    return _voci(righe) is not None


def estrai(file_path: str) -> Optional[dict]:
    """Il PDF di testo di questa famiglia; None se non lo e'."""
    try:
        righe, anni = _righe_pdf(file_path)
    except Exception:
        return None
    letto = estrai_da_righe(righe)
    if letto is not None:
        letto["anni"] = anni
    return letto


# --------------------------------------------------------------------------- #
# Sorgente 2: tabelle di MinerU (scansione)
# --------------------------------------------------------------------------- #
def _cella_ocr(c: str) -> str:
    """Le grafie OCR di una cella numerica: "0.00" per "0,00", spazi nelle migliaia."""
    c = c.strip()
    if re.fullmatch(r"-?\d+\.\d{2}", c):
        return c.replace(".", ",")
    return c


def _ricomponi(celle: list[str]) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Esercizio e precedente dalle celle numeriche di una riga MinerU, confermati dalla
    Differenza stampata. L'OCR sposta talvolta l'ultima cifra di una cella all'inizio della
    successiva ("62.871,92 | 0,0 | 0  62.871,9 | 2  100,000"): unite senza separatore le
    celle tornano "62.871,92 0,00 62.871,92 100,00"."""
    prove = (" ".join(_cella_ocr(c) for c in celle), "".join(celle))
    letture = []
    for testo in prove:
        importi = [_importo(m.group(0)) for m in _IMPORTO.finditer(testo)]
        letture.append(importi)
        if len(importi) >= 3 and any(abs(importi[0] - importi[1] - d) <= _C for d in importi[2:]):
            return importi[0], importi[1]
    # precedente vuoto: esercizio - Differenza, confermato dallo scostamento percentuale
    if len(celle) >= 3 and not celle[1].strip():
        cor = _IMPORTO.fullmatch(_cella_ocr(celle[0]))
        diff = _IMPORTO.fullmatch(_cella_ocr(celle[2]))
        pct = _PERCENTUALE.fullmatch(celle[3].strip()) if len(celle) > 3 else None
        if cor and diff and pct:
            c, d = _importo(cor.group(0)), _importo(diff.group(0))
            p = c - d
            perc = Decimal(pct.group(0).replace(".", "").replace(",", "."))
            if p != 0 and abs(d / p * 100 - perc) <= Decimal("0.01"):
                return c, p
    importi = letture[0]
    if len(importi) >= 2:
        return importi[0], importi[1]
    return (importi[0], None) if importi else (None, None)


def estrai_da_mineru(context) -> Optional[dict]:
    """Le tabelle MinerU di una scansione di questa famiglia; None se non lo e'."""
    righe: list = []
    anni: tuple = ()
    for table in getattr(context, "tables", ()) or ():
        for row in table.rows:
            celle = [(c.text or "").replace("\xa0", " ").strip() for c in row.cells]
            if not anni:
                date = [int(_DATA.match(c).group(1)) for c in celle if _DATA.match(c)]
                if len(date) >= 2:
                    anni = (date[0], date[1])
                    continue
            # l'etichetta e' la prima cella con lettere (il codice, quando c'e', la precede)
            idx = next((i for i, c in enumerate(celle) if _LETTERE.search(c)), None)
            if idx is None:
                continue
            numeriche = celle[idx + 1:]
            corrente, precedente = _ricomponi(numeriche) if numeriche else (None, None)
            if corrente is None and precedente is None:
                continue
            righe.append((celle[idx], corrente, precedente))
    letto = estrai_da_righe(righe)
    if letto is not None:
        letto["anni"] = anni
    return letto
