"""Il percorso del lettore (Fase 3, Task 5-6): dal PDF a SP e CE quadrati, anno corrente e anno precedente.

Foglie e ancore della colonna corrente -> passo 1 (macro-voce) -> `componi`; i blocchi che non tornano contro un
totale stampato si rivotano (solo le macro-voci ancorate: un totale attivo/passivo/utile che non torna non dipende
dalla classe, il lato lo decide la colonna) -> passo 2 (dettagli KPI) -> composizione finale. Le foglie della
colonna precedente si accoppiano per id di riga a quelle della corrente e usano le STESSE classi; una foglia
presente solo nel precedente entra nello stesso giro di classificazione, senza chiamate in piu'.

Il risultato ha la forma che `deterministico._esito` si aspetta (nomi pieni di colonna, chiavi diagnostiche sempre
presenti, anche a zero). Mai un'eccezione verso il chiamante: un errore da' bs/ce vuoti e `diagnostica["errore"]`.
"""
from __future__ import annotations

import threading
import time
from collections import Counter
from decimal import Decimal

from importers import llm_provider
from importers.import_snello import percorsi
from importers.lettore.celle import leggi_celle
from importers.lettore.classifica import classifica_dettagli, classifica_macro, rivota
from importers.lettore.componi import Composizione, componi
from importers.lettore.foglie import ancore, colonne_utili, foglie_contabili, senza_colonna
from importers.lettore.righe import Documento, leggi_pdf

_ZERO = Decimal(0)
_MACRO_ANCORATE = set(percorsi.NOMI)


def _leggi(file_path: str, contesto) -> Documento:
    tabelle = list(getattr(contesto, "tables", ()) or ())
    if tabelle:
        # MinerU numera le pagine da 0 (page_idx), il lettore da 1
        return leggi_celle([t.html for t in tabelle], [int(t.page or 0) + 1 for t in tabelle],
                           titoli=[t.caption for t in tabelle])
    return leggi_pdf(file_path)


def _contatore(chiama_json):
    """Avvolge il modello contando le chiamate (da piu' thread)."""
    blocco = threading.Lock()
    conto = {"n": 0}

    def chiama(*a, **k):
        with blocco:
            conto["n"] += 1
        return chiama_json(*a, **k)
    return chiama, conto


def _dati(c: Composizione) -> tuple[dict, dict]:
    """bs/ce con le chiavi diagnostiche sempre dichiarate: a valle una chiave assente vale zero."""
    plug = sum((x["importo"] for x in c.chiusure), _ZERO)
    return ({**c.bs, "_plug_residual": plug, "_unclassified_mass": c.senza_classe}, dict(c.ce))


def _blocchi(c: Composizione) -> list[str]:
    """I blocchi della composizione. Senza CE (`sp13_da != "ce"`) l'utile stampato e' la cifra di `sp13`, non
    un totale da rifare dal CE: `componi` lo confronta con un utile di CE assente, e non e' un blocco."""
    return [b for b in c.blocchi if not (b == "utile" and c.sp13_da != "ce")]


def _somma_macro(c: Composizione, chiave: str) -> Decimal:
    pieno = percorsi.NOMI.get(chiave)
    return (c.bs if chiave.startswith("sp") else c.ce).get(pieno, _ZERO) if pieno else _ZERO


def _importa(file_path, contesto_mineru, chiama_json, diag: dict) -> dict:
    doc = _leggi(file_path, contesto_mineru)
    if not doc.righe:
        raise ValueError("nessun testo e nessuna tabella")
    corrente, precedente = colonne_utili(doc)
    if corrente is None:
        raise ValueError("nessuna colonna di esercizio")
    base = chiama_json or llm_provider.chiama_gx10_json
    chiama, conto = _contatore(base)

    foglie_c = foglie_contabili(doc, corrente)
    anc_c = ancore(doc, corrente)
    foglie_p = foglie_contabili(doc, precedente) if precedente is not None else []
    anc_p = ancore(doc, precedente) if precedente is not None else []
    ids_c = {f.id for f in foglie_c}
    tutte = foglie_c + [f for f in foglie_p if f.id not in ids_c]   # un solo giro per le due colonne
    diag.update(foglie=len(foglie_c), ancore=len(anc_c), voti=0)

    cache: dict = {}
    classi = classifica_macro(tutte, chiama_json=chiama, cache=cache, diagnostica=diag)
    comp = componi(foglie_c, classi, anc_c)
    voti = 0
    for a in anc_c:
        if a.chiave not in _blocchi(comp) or a.chiave not in _MACRO_ANCORATE:
            continue
        sotto = [f for f in foglie_c if f.id in set(a.foglie)]
        if not sotto:
            continue
        classi = rivota(sotto, classi, chiama_json=chiama, ancora=a, somma=_somma_macro(comp, a.chiave),
                        cache=cache)
        voti += len(sotto)
        comp = componi(foglie_c, classi, anc_c)
    classifica_dettagli(tutte, classi, chiama_json=chiama, cache=cache)
    comp = componi(foglie_c, classi, anc_c)
    bs, ce = _dati(comp)

    out = {"bs": bs, "ce": ce, "prior_bs": None, "prior_ce": None, "anno_precedente": None,
           "prior_stato": "assente"}
    stampati = {f"totale_{a.chiave}": a.importo for a in anc_c if a.chiave in ("attivo", "passivo")}
    if stampati:
        out["stampati"] = stampati
    prec = next((c for c in doc.colonne if c.indice == precedente), None)
    diag["mesi_precedente"] = prec.mesi if prec else None
    if prec is not None and prec.fine is not None:
        out["anno_precedente"] = prec.fine.year
    if foglie_p:
        comp_p = componi(foglie_p, classi, anc_p)
        if _blocchi(comp_p):
            out["prior_stato"] = "scartato"
            diag["prior_blocchi"] = _blocchi(comp_p)
        else:
            out["prior_bs"], out["prior_ce"] = _dati(comp_p)
            out["prior_stato"] = "letto"

    diag.update(
        blocchi=_blocchi(comp), voti=voti, chiamate=conto["n"],
        classi_per_fonte=dict(Counter(classi[f.id].fonte for f in foglie_c if f.id in classi)),
        scarti={k: str(v) for k, v in comp.scarti.items()}, sbilancio=str(comp.sbilancio),
        chiusure=[{**x, "importo": str(x["importo"])} for x in comp.chiusure], scelte=list(comp.scelte),
        sp13_da=comp.sp13_da, senza_colonna=list(senza_colonna(doc, corrente)))
    out["diagnostica"] = diag
    return out


def importa_col_lettore(file_path: str, contesto_mineru=None, *, chiama_json=None) -> dict:
    """SP e CE del PDF, corrente e precedente. Mai un'eccezione: un errore da' bs/ce vuoti e `diagnostica["errore"]`."""
    inizio = time.monotonic()
    diag: dict = {"foglie": 0, "ancore": 0, "blocchi": [], "voti": 0, "chiamate": 0, "classi_per_fonte": {},
                  "secondi": 0.0}
    try:
        out = _importa(file_path, contesto_mineru, chiama_json, diag)
    except Exception as e:  # noqa: BLE001 - il percorso non fa mai fallire un import
        diag["errore"] = f"{type(e).__name__}: {e}"[:300]
        out = {"bs": {}, "ce": {}, "diagnostica": diag}
    diag["secondi"] = round(time.monotonic() - inizio, 3)
    return out
