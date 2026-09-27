"""Le sole chiamate a Qwen del percorso snello. Risposte corte, mai un elenco di codici da cui scegliere."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from importers import llm_provider
from importers.import_snello.percorsi import LEGENDA

BLOCCO = 60

PROMPT_CONTI = (
    "Righe di un prospetto contabile italiano (bilancio di verifica, situazione contabile o bilancio). "
    "Il codice ha gia' tolto i totali: ogni riga con id e' un saldo che conta, anche se ha un nome generico "
    "(un mastro stampato senza conti sotto e' un conto). "
    "Per OGNI riga con id scrivi il percorso della voce di legge (artt. 2424 e 2425 c.c.): "
    "sezione SPA (attivo), SPP (passivo e netto) o CE, poi lettera, numero romano, numero arabo, lettera minuscola, "
    "separati da punto; aggiungi '.E' o '.O' per crediti/debiti entro/oltre l'esercizio se indicato. "
    "Fondi ammortamento e svalutazione: percorso del bene rettificato con '.F'. "
    "Utile o perdita di esercizi PRECEDENTI, o risultato d'esercizio registrato in un conto di patrimonio netto "
    "(con codice conto): SPP.A.VIII se portato a nuovo, altrimenti SPP.A.IX. "
    "'R' SOLO per la riga finale di quadratura senza codice conto (utile/perdita a pareggio, sbilancio). "
    "'X' SOLO per righe che non sono saldi contabili: prospetti fiscali (variazioni in aumento/diminuzione, "
    "reddito imponibile), conti d'ordine, statistiche, totali generali. "
    "Le righe '#' sono contesto e non si rispondono; '[...]' e' il mastro del conto; (sx)/(dx) la colonna di stampa. "
    "Formato: una riga per id, 'id percorso', nient'altro.\n\nLEGENDA DEI PERCORSI:\n" + LEGENDA)

PROMPT_VOCI = (
    "Prospetto di bilancio italiano secondo lo schema di legge (artt. 2424 e 2425 c.c.), eventualmente abbreviato. "
    "Per ciascuna colonna d'esercizio restituisci le voci STAMPATE come coppie [percorso, importo]: "
    "percorso con la sintassi della legenda, importo come stampato (negativo se tra parentesi o col meno). "
    "Solo le voci piu' di dettaglio stampate: non i totali ('Totale immobilizzazioni', 'Totale crediti', "
    "'Totale attivo'); una voce stampata solo al livello romano (schema abbreviato) si scrive a quel livello "
    "(es. 'SPA.B.I'); crediti o debiti stampati solo come 'esigibili entro/oltre' senza numero arabo: "
    "'SPA.C.II.E', 'SPP.D.O'. Fondi stampati a parte: percorso del bene con '.F'. "
    "Il risultato dell'esercizio va sia come 'SPP.A.IX' nello SP sia come 'CE.21' nel CE. "
    "In 'totali' riporta i totali stampati (totale attivo, totale passivo, utile), null se non stampati."
    "\n\nLEGENDA DEI PERCORSI:\n" + LEGENDA)

_COPPIE = {"type": "array", "items": {"type": "array", "prefixItems": [{"type": "string"}, {"type": "number"}],
                                      "minItems": 2, "maxItems": 2}}
SCHEMA_VOCI = {"type": "object", "properties": {
    "corrente": _COPPIE, "precedente": _COPPIE,
    "totali": {"type": "object", "properties": {k: {"type": ["number", "null"]}
                                                for k in ("totale_attivo", "totale_passivo", "utile")}}},
    "required": ["corrente", "precedente", "totali"]}

SCHEMA_RIGHE = {"type": "object", "properties": {"righe": {"type": "array", "items": {
    "type": "array", "prefixItems": [{"type": "string"}, {"type": ["number", "null"]}, {"type": ["number", "null"]}],
    "minItems": 3, "maxItems": 3}}}, "required": ["righe"]}
PROMPT_TRASCRIVI = ("Trascrivi TUTTE le righe di tabella visibili, in ordine (ignora le righe tagliate a meta' dal bordo). "
                    "Per ogni riga: [etichetta, importo colonna 1, importo colonna 2]. Importi senza separatori, "
                    "negativi se tra parentesi, null se vuoto o '-'.")


def _testo(system, user, max_tokens):
    return llm_provider.chiama_gx10_testo(system, [{"role": "user", "content": user}],
                                          max_tokens=max_tokens, timeout=120.0)


def _json(system, user, schema, max_tokens):
    return llm_provider.chiama_gx10_json(system, [{"role": "user", "content": user}], schema,
                                         max_tokens=max_tokens, timeout=120.0)


def _blocco_testo(righe, blocco):
    ids = {f.id for f in blocco}
    numero = {f.id: n for n, f in enumerate(righe)}
    lo, hi = numero[blocco[0].id], numero[blocco[-1].id]
    contesto = [r for r in righe[max(0, lo - 40):lo] if r.valore is None and r.testo][-5:]
    linee = ["# " + r.testo[:80] for r in contesto]
    for r in righe[lo:hi + 1]:
        if r.id in ids:
            mastro = f" [{r.mastro[:40]}]" if r.mastro else ""
            linee.append(f"{numero[r.id]}|{r.testo[:80]}{mastro} ({'dx' if r.lato == 'R' else 'sx'})")
        elif r.valore is None and r.testo:
            linee.append("# " + r.testo[:80])
    return "\n".join(linee)


def percorsi_dei_conti(righe, foglie, *, chiama=None) -> dict:
    chiama = chiama or _testo
    per_numero = {n: r for n, r in enumerate(righe)}
    posizione_di = {id(r): n for n, r in enumerate(righe)}
    esito = {"chiamate": 0, "saltate_prima": 0, "senza_percorso": 0}

    def uno(blocco):
        out = chiama(PROMPT_CONTI, _blocco_testo(righe, blocco), 40 + 14 * len(blocco))
        # Un id nella risposta che non appartiene a QUESTO blocco (l'id di un altro blocco
        # dello stesso giro, allucinato o letto per contesto) va scartato qui: senza questo
        # filtro il blocco 1 potrebbe assegnare una riga di proprieta' del blocco 2, o
        # sovrascrivere piu' avanti la risposta corretta del blocco che la possiede davvero.
        ammessi = {posizione_di[id(f)] for f in blocco}
        trovati = {}
        for linea in out.splitlines():
            parti = linea.split()
            if len(parti) == 2 and parti[0].isdigit():
                n = int(parti[0])
                # una risposta vuota o di sola sezione ("SPA","SPP","CE") non e' una
                # classificazione: non conta come assegnazione, cosi' il secondo giro la
                # ritenta invece di restare bloccata su un percorso spazzatura.
                if n in ammessi and parti[1] not in ("", "SPA", "SPP", "CE"):
                    trovati[n] = parti[1]
        return trovati

    def giro(da_fare):
        # Il confronto deve essere per identita' dell'oggetto, mai per uguaglianza di campi:
        # Riga e' un dataclass e due righe distinte con campi identici (compreso l'id)
        # comparerebbero uguali con `in`, assegnando un percorso a una riga che non fa parte
        # di questo giro (per esempio un id che il modello ha inventato fuori dal blocco).
        identita_da_fare = {id(r) for r in da_fare}
        blocchi = [da_fare[i:i + BLOCCO] for i in range(0, len(da_fare), BLOCCO)]
        with ThreadPoolExecutor(llm_provider.GX10_CONCORRENZA) as ex:
            for trovati in ex.map(uno, blocchi):
                esito["chiamate"] += 1
                for n, p in trovati.items():
                    if n in per_numero and id(per_numero[n]) in identita_da_fare:
                        per_numero[n].percorso = p

    giro(foglie)
    mancanti = [f for f in foglie if not f.percorso]
    esito["saltate_prima"] = len(mancanti)
    if mancanti:
        giro(mancanti)
    esito["senza_percorso"] = sum(1 for f in foglie if not f.percorso)
    return esito


def voci_di_legge(testo: str, intestazioni: list[str], *, chiama_json=None, nota: str = "") -> dict:
    chiama_json = chiama_json or _json
    colonne = ", ".join(f"'{i}'" for i in intestazioni) or "non indicate"
    user = (f"Colonne d'esercizio, da sinistra: {colonne}. 'corrente' = la prima colonna d'esercizio, "
            f"'precedente' = la seconda (vuoto se non c'e').\n{nota}\n\n{testo}")
    righe = max(1, testo.count("\n") + 1)
    o = chiama_json(PROMPT_VOCI, user, SCHEMA_VOCI, min(6000, 300 + 30 * righe))
    conv = lambda coppie: [(str(p), Decimal(str(v))) for p, v in coppie or [] if v is not None]
    totali = {k: (None if v is None else Decimal(str(v))) for k, v in (o.get("totali") or {}).items()}
    return {"corrente": conv(o.get("corrente")), "precedente": conv(o.get("precedente")), "totali": totali}


def trascrivi_pagine(pdf: str, pagine: list[int], *, chiama_json=None, strisce: int = 3, dpi: int = 120) -> str:
    import fitz
    chiama_json = chiama_json or (lambda system, contenuto, schema, max_tokens: llm_provider.chiama_gx10_json(
        system, [{"role": "user", "content": contenuto}], schema, max_tokens=max_tokens, timeout=120.0))
    lavori = []
    with fitz.open(pdf) as doc:
        for numero in pagine:
            pagina = doc[numero - 1]
            r = pagina.rect
            alto, basso = r.height * 0.05, r.height * 0.95
            passo = (basso - alto) / strisce
            for k in range(strisce):
                clip = fitz.Rect(0, max(alto, alto + k * passo - 12), r.width, min(basso, alto + (k + 1) * passo + 12))
                png = pagina.get_pixmap(dpi=dpi, clip=clip).tobytes("png")
                lavori.append((numero, k, base64.b64encode(png).decode()))

    def uno(lavoro):
        _, _, b64 = lavoro
        contenuto = [{"type": "text", "text": PROMPT_TRASCRIVI},
                     {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}}]
        return chiama_json("", contenuto, SCHEMA_RIGHE, 3000)["righe"]

    with ThreadPoolExecutor(llm_provider.GX10_CONCORRENZA) as ex:
        risultati = list(ex.map(uno, lavori))

    linee: list[str] = []
    pagina_corrente, ultima_riga = None, None
    for (numero, k, _), righe_striscia in zip(lavori, risultati):
        if numero != pagina_corrente:
            # nuova pagina: mai confrontare la riga di bordo oltre il confine di pagina
            pagina_corrente, ultima_riga = numero, None
        for i, riga in enumerate(righe_striscia):
            # la sovrapposizione fra strisce ripete la riga di bordo, ma solo alla giuntura
            # strip k>0 / k-1 (mai dentro la stessa striscia: due righe identiche vere restano)
            if i == 0 and k > 0 and ultima_riga is not None and riga == ultima_riga:
                continue
            linee.append(" | ".join("" if x is None else str(x) for x in riga))
        if righe_striscia:
            ultima_riga = righe_striscia[-1]
    return "\n".join(linee)
