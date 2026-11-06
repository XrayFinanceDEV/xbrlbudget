"""La diagnosi del lettore per un import (Fase 2, Task 3): non solleva mai, ha un tetto di tempo, esce in JSON.

Si legge e si dichiara, non si corregge: nessun importo dell'import dipende da questo modulo.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as TempoScaduto
from datetime import date
from decimal import Decimal

from importers.lettore.blocchi import Blocco, blocchi_aperti, frase_blocco
from importers.lettore.celle import leggi_celle
from importers.lettore.righe import Documento, leggi_pdf

TETTO_SECONDI_DEFAULT = 20
_MAX_BLOCCHI = 20
_MAX_FRASI = 5
_INTESTAZIONE = ("BLOCCHI CHE NON CHIUDONO NEL PDF: i totali stampati qui sotto non sono la somma delle righe "
                 "che li precedono; verificarli in Rettifiche.")
_DA_VERIFICARE = " (righe individuate dal lettore: da verificare)"


def _tetto(parametro: float | None) -> float:
    if parametro is not None:
        return parametro
    try:
        valore = float(os.environ.get("LETTORE_TETTO_SECONDI", ""))
        return valore if valore > 0 else TETTO_SECONDI_DEFAULT
    except ValueError:
        return TETTO_SECONDI_DEFAULT


def _blocco_dict(b: Blocco) -> dict:
    return {"voce": b.voce, "codice": b.codice, "sezione": b.sezione, "lato": b.lato, "colonna": b.colonna,
            "fine": b.fine.isoformat() if b.fine else None, "mesi": b.mesi, "corrente": b.corrente,
            "stampato": str(b.stampato), "somma": str(b.somma), "scarto": str(b.scarto), "pagina": b.pagina,
            "righe": list(b.righe), "etichette": list(b.etichette), "cercato": b.cercato}


def _blocco_da_dict(d: dict) -> Blocco:
    return Blocco(voce=d["voce"], codice=d["codice"], sezione=d["sezione"], lato=d["lato"], colonna=d["colonna"],
                  fine=date.fromisoformat(d["fine"]) if d["fine"] else None, mesi=d["mesi"],
                  corrente=d["corrente"], stampato=Decimal(d["stampato"]), somma=Decimal(d["somma"]),
                  scarto=Decimal(d["scarto"]), pagina=d["pagina"], righe=tuple(d["righe"]),
                  etichette=tuple(d["etichette"]), cercato=d.get("cercato", False))


def _leggi(file_path: str, contesto, anno_corrente, anno_precedente) -> dict:
    tabelle = list(getattr(contesto, "tables", ()) or ())
    if tabelle:
        ingresso = "mineru"
        # MinerU numera le pagine da 0 (page_idx), il lettore da 1
        doc: Documento = leggi_celle([t.html for t in tabelle], [int(t.page or 0) + 1 for t in tabelle],
                                     titoli=[t.caption for t in tabelle])
    else:
        ingresso = "pdf"
        doc = leggi_pdf(file_path)
    if not doc.righe:
        return {"esito": "non_applicabile", "motivo": "nessun testo e nessuna tabella", "ingresso": ingresso}
    anni = {a for a in (anno_corrente, anno_precedente) if a}
    blocchi = []
    for b in blocchi_aperti(doc):
        if anni and not (b.fine and b.fine.year in anni):
            continue
        blocchi.append(_blocco_dict(b))
    return {
        "esito": "ok", "motivo": None, "ingresso": ingresso, "tipo": str(doc.profilo.tipo),
        "contrapposto": bool(doc.contrapposto),
        "colonne": [{"indice": c.indice, "ruolo": c.ruolo, "fine": c.fine.isoformat() if c.fine else None,
                     "mesi": c.mesi, "corrente": c.corrente} for c in doc.colonne],
        "blocchi_aperti": blocchi[:_MAX_BLOCCHI],
        "avvisi": [str(a) for a in doc.tutti_gli_avvisi()],
    }


def diagnosi_pdf(file_path: str, contesto_mineru=None, *, anno_corrente: int | None = None,
                 anno_precedente: int | None = None, tetto_secondi: float | None = None) -> dict:
    """La diagnosi di un import; mai un'eccezione. `esito`: ok | errore | tempo | non_applicabile."""
    inizio = time.monotonic()
    base = {"esito": "errore", "motivo": None, "ingresso": "pdf", "tipo": "", "contrapposto": False,
            "colonne": [], "blocchi_aperti": [], "avvisi": []}
    esecutore = None
    try:
        base["ingresso"] = "mineru" if getattr(contesto_mineru, "tables", None) else "pdf"
        esecutore = ThreadPoolExecutor(max_workers=1)
        futuro = esecutore.submit(_leggi, file_path, contesto_mineru, anno_corrente, anno_precedente)
        base.update(futuro.result(timeout=_tetto(tetto_secondi)))
    except TempoScaduto:
        base.update(esito="tempo", motivo="tempo massimo della lettura superato")
    except Exception as e:  # noqa: BLE001 - la diagnosi non fa mai fallire un import
        base.update(esito="errore", motivo=f"{type(e).__name__}: {e}"[:300] or "errore")
    finally:
        if esecutore is not None:
            esecutore.shutdown(wait=False)
    base["secondi"] = round(time.monotonic() - inizio, 3)
    return base


def frasi_per_utente(diagnosi: dict, sezioni: set[str], *, anno_precedente: int | None = None) -> list[str]:
    """Le frasi d'avviso: l'intestazione e al piu' 5 blocchi della colonna corrente (o dell'anno precedente, se
    richiesto) delle `sezioni`. Prima i blocchi dai figli noti, poi quelli individuati dal lettore, ciascun gruppo
    dal piu' grande scarto in valore assoluto."""
    try:
        if diagnosi.get("esito", "ok") != "ok":
            return []
        scelti = []
        for d in diagnosi.get("blocchi_aperti") or []:
            if d.get("sezione") not in sezioni:
                continue
            precedente = bool(anno_precedente and d.get("fine") and d["fine"][:4] == str(anno_precedente))
            if d.get("corrente") or precedente:
                scelti.append(_blocco_da_dict(d))
        if not scelti:
            return []
        scelti.sort(key=lambda b: (b.cercato, -abs(b.scarto)))
        return [_INTESTAZIONE] + [frase_blocco(b) + (_DA_VERIFICARE if b.cercato else "") for b in scelti[:_MAX_FRASI]]
    except Exception:  # noqa: BLE001 - una diagnosi malformata non produce frasi, mai un errore
        return []
