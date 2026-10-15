"""Schema di legge stampato con il PERCORSO come codice di riga ("Stampa dettaglio voci",
budget_1331 Crotto Ubiali): "1.B.2 IMMOBILIZZAZIONI MATERIALI", "2.D DEBITI", "3.B.9.a Salari
e stipendi", "3.20 Imposte...", con i conti del gestionale sotto ogni voce ("05.03.09 Impianti
specifici 1.300,00 D") e due coppie di colonne Parziali / Totali, esercizio e precedente.

Il codice e' gia' il percorso di legge (1 attivo, 2 passivo, 3 conto economico; lettera,
poi il numero romano scritto in cifre arabe), quindi la voce non si indovina dalla descrizione:
si traduce. Si legge solo la colonna "Totali" di ogni anno, mai i conti. Una voce conta solo se
nessuna voce sotto di lei (stampata con un importo) ha gia' un campo: padre e figli non si
sommano mai. Le regole di adozione restano quelle di tutti i lettori deterministici: attivo e
passivo stampati, utile del CE uguale all'utile dello SP.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

import fitz

from importers.import_snello.percorsi import campo_da_percorso, completa

_CODICE = re.compile(r"^[123](?:\.[A-Za-z0-9-]+)*$")
_IMPORTO = re.compile(r"^\d{1,3}(?:\.\d{3})*(?:,\d{2})?-?$")
_ROMANI = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X"}


def _valore(testo: str) -> Decimal:
    neg = testo.endswith("-")
    v = Decimal(testo.rstrip("-").replace(".", "").replace(",", "."))
    return -v if neg else v


def percorso(codice: str) -> Optional[str]:
    """"1.B.2" -> "SPA.B.II", "2.A.9" -> "SPP.A.IX", "2.D" -> "SPP.D", "3.B.9.a" ->
    "CE.B.9.a", "3.B.10.abc.b" -> "CE.B.10.b", "3.20" -> "CE.20"; None per i nodi di
    raggruppamento ("3.B.9.cde", "3.B.10.abc") e per i codici che non conosciamo."""
    t = codice.split(".")
    radice = {"1": "SPA", "2": "SPP", "3": "CE"}.get(t[0])
    if radice is None:
        return None
    resto = t[1:]
    if radice == "CE":
        # i raggruppamenti di lettere ("cde", "abc") non sono voci: il loro figlio si'
        resto = [x for x in resto if not (len(x) > 1 and x.isalpha() and x.islower())]
        if t[-1] != (resto[-1] if resto else None):
            return None
        return ".".join(["CE", *resto])
    if len(resto) >= 2 and resto[1].isdigit() and (
            (radice == "SPA" and resto[0] in ("B", "C")) or (radice == "SPP" and resto[0] == "A")):
        resto = [resto[0], _ROMANI.get(int(resto[1]), resto[1]), *resto[2:]]
    return ".".join([radice, *resto])


def _righe(file_path: str):
    """(codice, descrizione, importo corrente, importo precedente) di ogni riga con codice di
    legge; gli importi stanno sotto le due intestazioni "Totali"."""
    out = []
    with fitz.open(file_path) as doc:
        for page in doc:
            parole = page.get_text("words")
            totali = sorted(w[2] for w in parole if w[4] == "Totali")
            parziali = sorted(w[2] for w in parole if w[4] == "Parziali")
            if len(totali) != 2 or len(parziali) != 2:
                continue
            colonne = [(parziali[0], None), (totali[0], 0), (parziali[1], None), (totali[1], 1)]
            per_y: dict[int, list] = {}
            for w in parole:
                per_y.setdefault(round((w[1] + w[3]) / 2), []).append(w)
            for y in sorted(per_y):
                ws = sorted(per_y[y], key=lambda w: w[0])
                if not _CODICE.match(ws[0][4]) or ws[0][0] > 40 or len(ws) < 2:
                    continue
                valori: list[Optional[Decimal]] = [None, None]
                desc = []
                for w in ws[1:]:
                    if _IMPORTO.match(w[4]) and w[0] > 250:
                        # la colonna con il bordo destro piu' vicino
                        _x, anno = min(colonne, key=lambda c: abs(c[0] - w[2]))
                        if anno is not None:
                            valori[anno] = _valore(w[4])
                    else:
                        desc.append(w[4])
                out.append((ws[0][4], " ".join(desc), valori[0], valori[1]))
    return out


def riconosci(file_path: str) -> bool:
    try:
        righe = _righe(file_path)
    except Exception:
        return False
    radici = {c for c, *_ in righe if c in ("1", "2", "3")}
    return radici == {"1", "2", "3"} and len(righe) >= 15


def _colonna(righe, anno: int) -> Optional[dict]:
    # un codice ripetuto (intestazione ristampata a cavallo di pagina) vale una volta
    voci = {codice: (percorso(codice), valori[anno]) for codice, _desc, *valori in righe}
    importi: dict[str, Decimal] = {}
    for codice, (p, v) in voci.items():
        if v is None or p is None:
            continue
        campo = campo_da_percorso(p)
        if campo is None:
            continue
        figli = [c for c, (pp, vv) in voci.items()
                 if c.startswith(codice + ".") and vv is not None and pp and campo_da_percorso(pp)]
        if figli:
            continue
        importi[campo] = importi.get(campo, Decimal("0")) + v
    if not importi:
        return None
    stampati = {}
    for codice, chiave in (("1", "totale_attivo"), ("2", "totale_passivo")):
        if codice in voci and voci[codice][1] is not None:
            stampati[chiave] = voci[codice][1]
    utile = voci.get("3.21", (None, None))[1]
    return {"importi": importi, "stampati": stampati, "utile": utile}


def estrai(file_path: str) -> Optional[dict]:
    """None se il documento non e' di questa famiglia; altrimenti bs/ce dell'esercizio (codici
    pieni), i totali stampati e, se la colonna c'e', lo stesso per l'anno precedente."""
    if not riconosci(file_path):
        return None
    righe = _righe(file_path)
    out = {}
    for anno, nome in ((0, ""), (1, "prior_")):
        col = _colonna(righe, anno)
        if col is None:
            out[nome + "bs"] = out[nome + "ce"] = None
            continue
        bs, ce = completa({k: str(v) for k, v in col["importi"].items()})
        bs["_unclassified_mass"] = Decimal("0")
        bs["_plug_residual"] = Decimal("0")
        out[nome + "bs"], out[nome + "ce"] = bs, ce
        out[nome + "stampati"] = col["stampati"]
    return out
