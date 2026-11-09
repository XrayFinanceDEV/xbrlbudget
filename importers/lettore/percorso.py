"""Il percorso del lettore (Fase 3, Task 5-6): dal PDF a SP e CE quadrati, anno corrente e anno precedente.

Foglie e ancore della colonna corrente -> passo 1 (macro-voce) -> `componi`; i blocchi che non tornano contro un
totale stampato si rivotano (solo le macro-voci ancorate: un totale attivo/passivo/utile che non torna non dipende
dalla classe, il lato lo decide la colonna) -> passo 2 (il dettaglio di ogni macro che ne ha) -> composizione finale. Le foglie della
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
from importers.lettore.classifica import classifica_dettagli, classifica_macro, rivota, scadenza_dei_debiti
from importers.lettore.componi import (Composizione, componi, e_questo_risultato, e_risultato, importo_sp,
                                       lato_sp, risultato_con_segno)
from importers.lettore.foglie import ancore, colonne_utili, foglie_contabili, senza_colonna
from importers.lettore.righe import Documento, leggi_pdf

_ZERO = Decimal(0)
_VOTI = 3          # i turni di `rivota` per foglia (il suo default)
_MACRO_ANCORATE = set(percorsi.NOMI)
MAX_CHIAMATE = 40  # tetto di chiamate al modello per documento (Ruling F3-15): oltre, le foglie restano senza classe


def _leggi(file_path: str, contesto) -> Documento:
    tabelle = list(getattr(contesto, "tables", ()) or ())
    if tabelle:
        # MinerU numera le pagine da 0 (page_idx), il lettore da 1
        return leggi_celle([t.html for t in tabelle], [int(t.page or 0) + 1 for t in tabelle],
                           titoli=[t.caption for t in tabelle])
    return leggi_pdf(file_path)


def _contatore(chiama_json, diag: dict | None = None):
    """Avvolge il modello contando le chiamate (da piu' thread); oltre `MAX_CHIAMATE` non chiama piu' e
    solleva `LLMProviderError` (le foglie restano senza classe), dichiarando `diag["tetto_chiamate"]`."""
    blocco = threading.Lock()
    conto = {"n": 0}

    def chiama(*a, **k):
        with blocco:
            if conto["n"] >= MAX_CHIAMATE:
                if diag is not None:
                    diag["tetto_chiamate"] = MAX_CHIAMATE
                raise llm_provider.LLMProviderError(f"tetto di {MAX_CHIAMATE} chiamate al modello raggiunto")
            conto["n"] += 1
        return chiama_json(*a, **k)
    return chiama, conto


def _foglie_non_in_pari(foglie, ancore=()) -> str | None:
    """Il motivo per cui le foglie, classificate comunque, non potrebbero mai quadrare (il lato lo decide la
    colonna, non il modello): nessuna foglia di SP, o attivo diverso da passivo piu' un risultato candidato oltre la
    soglia di adozione. Lato, segno e righe del risultato come li tratta la composizione (`componi`): una riga del
    risultato nello SP che non vale il risultato candidato e' un conto del patrimonio netto e resta sul suo lato.
    Candidati del risultato: zero, l'utile delle foglie di CE (se ognuna ha il verso) e l'utile stampato col suo
    segno. None se non si sa: una foglia di sezione ignota con un importo, o una foglia di SP senza lato."""
    from importers.import_snello.verifica import soglia

    if any(f.sezione not in ("SP", "CE") and f.importo for f in foglie):
        return None     # sezione ignota: potrebbe essere CE come SP, non lo so (e «non lo so» non blocca)
    sp = [f for f in foglie if f.sezione == "SP" and f.importo]
    if not sp:
        return "senza_foglie_sp"
    if any(lato_sp(f) is None for f in sp):
        return None
    conti = [f for f in sp if not e_risultato(f)]
    righe_risultato = [f for f in sp if e_risultato(f)]
    attivo = sum((importo_sp(f) for f in conti if lato_sp(f) == "A"), _ZERO)
    passivo = sum((importo_sp(f) for f in conti if lato_sp(f) == "P"), _ZERO)
    utili = [_ZERO]
    utili += [a.importo for a in ancore if a.chiave == "utile"]
    ce = [f for f in foglie if f.sezione == "CE" and f.importo and not e_risultato(f)]
    if not ce:
        pass
    elif all(f.verso_ce in ("costo", "ricavo") for f in ce):
        utili.append(sum((f.importo if f.verso_ce == "ricavo" else -f.importo for f in ce), _ZERO))
    else:
        return None     # un verso ignoto rende libero l'utile composto (sp13 viene dal CE, non dallo stampato)
    s = soglia(attivo)
    senza_sp13 = not ce and len(utili) == 1     # ne' CE ne' utile stampato: `componi` non ha sp13 e toglie le righe
    for u in utili:
        altri = _ZERO if senza_sp13 else sum(
            (risultato_con_segno(f) for f in righe_risultato if not e_questo_risultato(f, u, s)), _ZERO)
        if abs(attivo - (passivo + altri + u)) <= s:
            return None
    return "foglie_non_in_pari"


def _dati(c: Composizione) -> tuple[dict, dict]:
    """bs/ce con le chiavi diagnostiche sempre dichiarate: a valle una chiave assente vale zero."""
    plug = sum((x["importo"] for x in c.chiusure), _ZERO)
    # `_netted_contra`: la massa rettificata che i totali stampati contano ancora (stessa chiave del percorso C)
    return ({**c.bs, "_plug_residual": plug, "_unclassified_mass": c.senza_classe, "_netted_contra": c.rettifiche},
            dict(c.ce))


def _stampati(c: Composizione, anc) -> dict:
    """Totale attivo e passivo stampati, al netto delle rettifiche passate dalla colonna opposta: il documento li
    stampa lordi, il cancello li confronta con attivo e passivo composti (come `net_contra_accounts` chiede al
    chiamante di ridurre l'ancora dichiarata)."""
    return {f"totale_{a.chiave}": a.importo - c.rettifiche for a in anc if a.chiave in ("attivo", "passivo")}


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
    chiama, conto = _contatore(base, diag)

    foglie_c = foglie_contabili(doc, corrente)
    anc_c = ancore(doc, corrente)
    foglie_p = foglie_contabili(doc, precedente) if precedente is not None else []
    anc_p = ancore(doc, precedente) if precedente is not None else []
    ids_c = {f.id for f in foglie_c}
    tutte = foglie_c + [f for f in foglie_p if f.id not in ids_c]   # un solo giro per le due colonne
    diag.update(foglie=len(foglie_c), ancore=len(anc_c), voti=0, foglie_rivotate=0)
    motivo = _foglie_non_in_pari(foglie_c, anc_c)
    if motivo:      # guardia di costo (F3-15): nessuna classe puo' sistemarlo, quindi nessuna chiamata al modello
        diag["motivo"] = motivo
        diag.setdefault("mesi_precedente", None)
        return {"bs": {}, "ce": {}, "prior_bs": None, "prior_ce": None, "anno_precedente": None,
                "prior_stato": "assente", "stampati": {}, "diagnostica": diag}

    cache: dict = {}
    classi = classifica_macro(tutte, chiama_json=chiama, cache=cache, diagnostica=diag)
    comp = componi(foglie_c, classi, anc_c)
    voti = rivotate = 0
    for a in anc_c:
        if a.chiave not in comp.blocchi or a.chiave not in _MACRO_ANCORATE:
            continue
        sotto = [f for f in foglie_c if f.id in set(a.foglie)]
        if not sotto:
            continue
        classi = rivota(sotto, classi, chiama_json=chiama, ancora=a, somma=_somma_macro(comp, a.chiave),
                        cache=cache)
        rivotate += len(sotto)
        voti += len(sotto) * _VOTI
        comp = componi(foglie_c, classi, anc_c)
    # la scadenza dei debiti la decide il testo stampato, prima del dettaglio (sp16a e sp17a sono sotto-voci diverse)
    classi, diag["scadenze"] = scadenza_dei_debiti(tutte, classi)
    prima = conto["n"]
    classifica_dettagli(tutte, classi, chiama_json=chiama, cache=cache)
    diag["chiamate_dettagli"] = conto["n"] - prima
    comp = componi(foglie_c, classi, anc_c)
    bs, ce = _dati(comp)

    out = {"bs": bs, "ce": ce, "prior_bs": None, "prior_ce": None, "anno_precedente": None,
           "prior_stato": "assente"}
    out["stampati"] = _stampati(comp, anc_c)
    prec = next((c for c in doc.colonne if c.indice == precedente), None)
    diag["mesi_precedente"] = prec.mesi if prec else None
    if prec is not None and prec.fine is not None:
        out["anno_precedente"] = prec.fine.year
    if foglie_p:
        comp_p = componi(foglie_p, classi, anc_p)
        if comp_p.blocchi:
            out["prior_stato"] = "scartato"
            diag["prior_rifiuto"] = {"controllo": "blocchi", "blocchi": list(comp_p.blocchi)}
        else:
            # lo stesso cancello dell'anno corrente e di `_con_precedente`: adottato e "ok" (niente tappo, massa
            # non classificata sotto soglia), altrimenti il precedente si scarta e si dice perche'
            from importers.import_snello.deterministico import esito as _esito_deterministico   # import tardivo: niente cicli col T7
            bs_p, ce_p = _dati(comp_p)
            ps = _stampati(comp_p, anc_p)
            e = _esito_deterministico("lettore", bs_p, ce_p, ps)
            if e["adottato"] and e["esito"] == "ok":
                out["prior_bs"], out["prior_ce"] = e["bs"], e["ce"]
                out["prior_stato"] = "letto"
            else:
                out["prior_stato"] = "scartato"
                diag["prior_rifiuto"] = {"controllo": e["esito"],
                                         **({"unclassified_mass": e["unclassified_mass"]}
                                            if "unclassified_mass" in e else {})}

    diag.update(
        blocchi=list(comp.blocchi), voti=voti, foglie_rivotate=rivotate, chiamate=conto["n"],
        classi_per_fonte=dict(Counter(classi[f.id].fonte for f in foglie_c if f.id in classi)),
        scarti={k: str(v) for k, v in comp.scarti.items()}, sbilancio=str(comp.sbilancio),
        chiusure=[{**x, "importo": str(x["importo"])} for x in comp.chiusure], scelte=list(comp.scelte),
        sp13_da=comp.sp13_da, senza_colonna=list(senza_colonna(doc, corrente)), rettifiche=str(comp.rettifiche),
        immobilizzazioni_negative_tagliate=list(comp.tagliate))
    out["diagnostica"] = diag
    return out


def importa_col_lettore(file_path: str, contesto_mineru=None, *, chiama_json=None) -> dict:
    """SP e CE del PDF, corrente e precedente. Mai un'eccezione: un errore da' bs/ce vuoti e `diagnostica["errore"]`."""
    inizio = time.monotonic()
    diag: dict = {"foglie": 0, "ancore": 0, "blocchi": [], "voti": 0, "foglie_rivotate": 0, "chiamate": 0, "classi_per_fonte": {},
                  "scadenze": [],
                  "secondi": 0.0}
    try:
        out = _importa(file_path, contesto_mineru, chiama_json, diag)
    except Exception as e:  # noqa: BLE001 - il percorso non fa mai fallire un import
        diag["errore"] = f"{type(e).__name__}: {e}"[:300]
        diag.setdefault("mesi_precedente", None)
        out = {"bs": {}, "ce": {}, "prior_bs": None, "prior_ce": None, "anno_precedente": None,
               "prior_stato": "assente", "stampati": {}, "diagnostica": diag}
    diag["secondi"] = round(time.monotonic() - inizio, 3)
    return out
