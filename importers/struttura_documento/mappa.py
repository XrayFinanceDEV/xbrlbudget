"""Mappa del documento: Sonnet 5 dichiara la struttura di ogni pagina, dall'immagine.

Non legge importi: dice che prospetto è la pagina, se le sezioni sono affiancate,
il ruolo e l'intestazione stampata di ogni colonna numerica, dove stanno i fondi.
La dichiarazione è un'ipotesi: la verifica sui totali stampati la fa `verifica.py`.

Non tutte le pagine vanno alla vision (decisione del proprietario, 2026-09-22): una pagina
senza importi è nota o testo, e le pagine di uno stesso prospetto sono strutturalmente uguali.
Sonnet mappa una sola pagina per blocco (`blocchi`); le pagine successive dello stesso blocco
riusano la mappa con `continuazione = True` (`mappa_documento`).

Riusare la mappa è un'economia, non una scorciatoia: è lecita solo dove il titolo di prospetto
stampato dal documento stesso dimostra che la pagina appartiene allo stesso blocco. Una pagina
senza titolo proprio comincia sempre un blocco suo — e quindi la sua vision — anche quando
l'intestazione di colonna è identica a quella della pagina precedente (`blocchi`).
"""
from __future__ import annotations

import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from config import STRUTTURA_MODEL as MODELLO

NUM_SEP = re.compile(r"^\(?-?\d{1,3}(\.\d{3})+(,\d{1,2})?\)?-?$|^\(?-?\d+,\d{1,2}\)?-?$")

RUOLI = ["saldo_corrente", "saldo_precedente", "saldo_non_rettificato", "rettifiche",
         "saldo_finale", "dare", "avere", "variazione", "percentuale", "altro"]
TIPI = ["prospetto_sp", "prospetto_ce", "prospetto_sp_e_ce", "dettaglio_conti", "nota_o_testo", "altro"]

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "tipo_pagina": {"enum": TIPI},
        "disposizione": {"enum": ["colonna_unica", "sezioni_contrapposte"]},
        "schema": {"enum": ["iv_cee_di_legge", "piano_dei_conti_gerarchico",
                            "riclassificato_con_codici_ivcee", "elenco_piatto"]},
        "sezioni": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "posizione": {"enum": ["unica", "sinistra", "destra"]},
                "contenuto": {"enum": ["attivo", "passivo", "costi", "ricavi", "misto"]},
                "colonne": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {"ruolo": {"enum": RUOLI},
                                   "intestazione": {"type": "string",
                                                    "description": "testo stampato dell'intestazione, esatto"}},
                    "required": ["ruolo", "intestazione"]}},
            },
            "required": ["posizione", "contenuto", "colonne"]}},
        "continuazione": {"type": "boolean",
                          "description": "la pagina continua il prospetto della pagina precedente, con le stesse colonne"},
        "codici_conto": {"type": "boolean"},
        "totali_stampati": {"type": "boolean"},
        "anno_precedente": {"type": "boolean"},
        "negativi": {"enum": ["parentesi", "segno_meno", "nessuno", "non_visibile"]},
        "fondi_ammortamento": {"enum": ["assenti", "righe_negative_nell_attivo", "nel_passivo", "sezione_separata"]},
        "note": {"type": "string", "description": "al massimo una frase"},
    },
    "required": ["tipo_pagina", "disposizione", "schema", "sezioni", "continuazione", "codici_conto", "totali_stampati",
                 "anno_precedente", "negativi", "fondi_ammortamento", "note"],
}

PROMPT = (
    "Pagina di un bilancio italiano. Descrivi la STRUTTURA, non i numeri: che prospetto è; se le sezioni "
    "sono affiancate (attivo a sinistra e passivo a destra, o costi e ricavi) o in colonna unica; per ogni "
    "sezione le colonne numeriche da sinistra a destra, con il ruolo e l'intestazione stampata esatta "
    "(per un anno usa la data stampata); se ci sono codici di conto; se ci sono totali stampati; se c'è "
    "un anno precedente; come sono scritti i negativi; dove stanno i fondi ammortamento; se la pagina "
    "continua il prospetto della pagina precedente con le stesse colonne (continuazione). Una pagina di "
    "sola nota integrativa o testo è nota_o_testo; una tabella di dettaglio di una voce è dettaglio_conti."
)

TITOLI_SP = re.compile(r"stato patrimoniale|passivit[aà]|situazione patrimoniale", re.I)
TITOLI_CE = re.compile(r"conto economico|situazione economica|a\) valore della produzione"
                        r"|ricavi e profitti|costi,?\s*spese e perdite", re.I)

# "attivita'" da sola conta come titolo di Stato Patrimoniale solo su una riga corta (poche
# parole, come una vera intestazione) e non preceduta da un apostrofo: la preposizione
# articolata di un rendiconto finanziario ("dall'attivita' operativa", "dell'attivita' di
# investimento") ci cadeva sempre, perche' il vecchio TITOLI_SP la matchava ovunque nel testo di
# testa unito, senza nessun contesto di titolo (Task lotto-b, fix 7, diagnosi budget_671).
_ATTIVITA_TITOLO = re.compile(r"(?<!['’])attivit[aà]'?(?:\s|$)", re.I)
MASSIMO_PAROLE_TITOLO_ATTIVITA = 6

# "costi" e "ricavi" sulla STESSA riga stampata, come una vera testata a sezioni contrapposte
# ("COSTI, SPESE E PERDITE      RICAVI E PROFITTI"): tenuta separata da TITOLI_CE e verificata
# riga per riga (`_titolo_pagina`), non sul testo di testa unito. Dentro TITOLI_CE, con un `.*`
# senza limite su 1.500 caratteri uniti da _testo_di_testa, la stessa alternativa scambiava per
# un titolo due parole di righe diverse dentro il corpo di un prospetto fiscale — "Rettifiche
# costi" e "Rettifiche ricavi" di una rideterminazione IRAP, separate da righe di conto — e una
# colonna di percentuali finiva letta come ricavi (Task 28, misurato su un file reale del
# pilota: 1.600 euro di ricavi in piu' per sedici righe da 100,00).
COSTI_RICAVI_STESSA_RIGA = re.compile(r"costi\b.*\bricavi", re.I)
MIN_IMPORTI = 5

# Pie' di pagina che solo un PDF generato dalla tassonomia XBRL di legge stampa: nessun
# gestionale di conti scrive queste frasi, quindi bastano a riconoscere la famiglia senza
# vision (decisione del proprietario, 2026-09-22).
PIE_TASSONOMIA = re.compile(r"conforme alla tassonomia|generato automaticamente|itcc-ci-", re.I)
DATA = re.compile(r"^\d{2}[-/]\d{2}[-/]\d{4}$")

# Una tabella di nota, dopo "Nota integrativa", puo' ripetere "conto economico"/"attivo
# circolante"/"Totale ..." e abbastanza importi da sembrare un prospetto: il confine della nota
# integrativa la esclude (difetto B, Task 7b).
NOTA_INTEGRATIVA = re.compile(r"nota integrativa", re.I)

# Titoli di sezioni diverse dal prospetto: una pagina di continuazione non deve mai attraversare
# questo confine, anche se non ha un titolo di prospetto proprio e ha importi (Task lotto-b,
# fix 6, diagnosi budget_671/972/614/158). Controllati solo sulla prima riga di testa: il testo
# unito su 1500 caratteri e' troppo largo e "relazione"/"verbale" comparirebbero anche in prosa.
_SEZIONI_CONFINE = ("nota integrativa", "rendiconto finanziario", "relazione", "verbale")

# Al massimo tante pagine di fila senza titolo/tipo proprio si accettano come continuazione dello
# stesso prospetto: oltre questo limite un blocco che non richiude mai da solo (documento
# malformato, o due prospetti diversi senza titoli intermedi) rischierebbe di inghiottire tutto
# il resto del documento.
MAX_PAGINE_CONTINUAZIONE = 2


# Quante righe di testa si guardano per un titolo di sezione confine: non solo la riga 0, perche'
# un running header aziendale ("ACME SRL - Bilancio al 31-12-2025") puo' precederlo, spingendo il
# vero titolo sulla seconda riga o oltre (fix round 1, gap 1 del collaudo lotto-b).
MASSIMO_RIGHE_SEZIONE_CONFINE = 4
MASSIMO_PAROLE_SEZIONE_CONFINE = 8


def _apre_sezione_nuova(page) -> bool:
    """Una fra le prime righe di testa (non solo la riga 0: un running header aziendale puo'
    precedere il titolo vero) comincia con il titolo di una sezione diversa dal prospetto in
    corso: non puo' esserne la continuazione, anche se ha importi e nessun titolo di prospetto
    proprio. Solo le righe corte (<= 8 parole) contano: un running header o un titolo sono brevi
    per natura, una riga di prosa lunga non lo e' e non deve far scattare il confine per caso."""
    righe = _righe_di_testa(page, caratteri=200)
    for riga in righe[:MASSIMO_RIGHE_SEZIONE_CONFINE]:
        pulita = riga.strip().lower()
        if pulita and len(pulita.split()) <= MASSIMO_PAROLE_SEZIONE_CONFINE:
            if any(pulita.startswith(s) for s in _SEZIONI_CONFINE):
                return True
    return False


# Quanti caratteri di testa (dopo la ricompattazione) si guardano per riconoscere un titolo di
# prospetto. 1500, non solo le prime righe: un layout "quattro sezioni" puo' stampare 20+ righe
# brevi di intestazione aziendale prima delle parole di sezione ("costi"/"ricavi"), e una finestra
# di sole 15 righe le perdeva (rilievo del bench reale sul riesame di Task 7b). La ricompattazione
# e l'ordine CE-prima-di-SP bastano da soli a non farsi ingannare da una descrizione di conto CE
# che contiene "attivita'": il titolo vero del CE si trova comunque per primo, dentro la stessa
# finestra.
CARATTERI_TITOLO = 1500

# "S I T U A Z I O N E" -> "SITUAZIONE": solo sequenze di almeno tre lettere singole separate da
# uno spazio letterale, per non toccare il testo normale (una "A)" di voce di bilancio e' una
# lettera sola, mai tre).
_LETTERE_SPAZIATE = re.compile(r"\b(?:[A-Za-zÀ-ÖØ-öø-ÿ] ){2,}[A-Za-zÀ-ÖØ-öø-ÿ]\b")


def _ricompatta_lettere_spaziate(testo: str) -> str:
    return _LETTERE_SPAZIATE.sub(lambda m: m.group(0).replace(" ", ""), testo)


def _testo_di_testa(page, caratteri: int = CARATTERI_TITOLO) -> str:
    """Il testo della pagina, ricompattato riga per riga e unito con uno spazio (non un a-capo,
    cosi' un titolo su due righe come "SITUAZIONE" / "PATRIMONIALE" combacia con un pattern
    scritto come una frase sola), poi tagliato ai primi `caratteri`: la testata dove stampano i
    titoli di prospetto, non necessariamente le sole prime righe quando l'intestazione aziendale
    e' lunga."""
    testo = " ".join(_ricompatta_lettere_spaziate(linea) for linea in page.get_text().splitlines())
    return testo[:caratteri]


def _righe_di_testa(page, caratteri: int = CARATTERI_TITOLO) -> list[str]:
    """Le stesse righe di `_testo_di_testa` (ricompattate, tagliate alla stessa finestra di
    testa), ma NON unite: per `COSTI_RICAVI_STESSA_RIGA`, che deve leggere "costi" e "ricavi"
    sulla stessa riga stampata dal documento, non a distanza qualunque nel testo unito da uno
    spazio al posto dell'a-capo."""
    righe = []
    totale = 0
    for linea in page.get_text().splitlines():
        riga = _ricompatta_lettere_spaziate(linea)
        righe.append(riga)
        totale += len(riga) + 1
        if totale >= caratteri:
            break
    return righe


@dataclass
class Blocco:
    pagine: list
    titolo: str | None       # "stato patrimoniale" | "conto economico" | None
    intestazione: str        # riga delle intestazioni di colonna, normalizzata


def _importi_pagina(page) -> int:
    return sum(1 for w in page.get_text("words") if NUM_SEP.match(w[4]))


def _titolo_pagina(page) -> str | None:
    righe = _righe_di_testa(page)
    testo = _testo_di_testa(page)
    if TITOLI_CE.search(testo) or any(COSTI_RICAVI_STESSA_RIGA.search(riga) for riga in righe):
        return "conto economico"
    if TITOLI_SP.search(testo):
        return "stato patrimoniale"
    for riga in righe:
        if len(riga.split()) <= MASSIMO_PAROLE_TITOLO_ATTIVITA and _ATTIVITA_TITOLO.search(riga):
            return "stato patrimoniale"
    return None


def e_xbrl_di_legge(pdf: str) -> bool:
    """True se il PDF e' stato generato dalla tassonomia XBRL di legge: lo dice il suo
    stesso pie' di pagina, non serve aprirlo con la vision per saperlo."""
    import fitz
    with fitz.open(pdf) as doc:
        return any(PIE_TASSONOMIA.search(doc[i].get_text()) for i in range(min(3, doc.page_count)))


def _colonne(date: tuple) -> tuple[list[dict], bool]:
    """Le colonne di un prospetto xbrl dalle date stampate: una seconda colonna (saldo
    precedente) solo se la seconda data e' diversa dalla prima — un documento a un solo anno a
    volte ripete la stessa data due volte, e non e' un anno precedente vero. Condivisa dal ramo
    che apre un prospetto e da quello che ne riconosce la continuazione, con la stessa guardia."""
    colonne = [{"ruolo": "saldo_corrente", "intestazione": date[0]}]
    con_precedente = len(date) > 1 and date[1] != date[0]
    if con_precedente:
        colonne.append({"ruolo": "saldo_precedente", "intestazione": date[1]})
    return colonne, con_precedente


def mappa_xbrl(pdf: str) -> list[dict]:
    """Mappa deterministica per i PDF generati dalla tassonomia: prospetti dai titoli
    di legge (`_titolo_pagina`, gia' usato da `blocchi`), colonne dalle due date stampate
    in testa. Nessuna chiamata al modello: una pagina senza titolo di prospetto o senza
    date resta nota_o_testo, dichiarata cosi' e mai forzata in un prospetto che non e'.

    Dalla prima pagina la cui testa contiene "nota integrativa" in poi, nessuna pagina e' piu' un
    prospetto: le tabelle di nota possono ripetere "conto economico"/"Totale ..." e abbastanza
    importi da sembrarlo, ma non lo sono (difetto B, Task 7b). Prima di quel confine, una pagina
    senza titolo proprio ma con importi ne e' la continuazione (stesso tipo, `continuazione=True`):
    non serve che ripeta le stesse date del prospetto appena letto, una vera continuazione spesso
    non le ristampa affatto (Task lotto-b, fix 6a, diagnosi budget_671/247) — al massimo
    MAX_PAGINE_CONTINUAZIONE pagine di fila, e mai oltre una pagina che apre una sezione diversa
    (nota integrativa, rendiconto finanziario, relazione, verbale)."""
    import fitz
    mappe = []
    with fitz.open(pdf) as doc:
        pagine = list(doc)
        indice_nota = next((i for i, p in enumerate(pagine) if NOTA_INTEGRATIVA.search(_testo_di_testa(p))), None)
        blocco_aperto: tuple[str, tuple] | None = None  # (tipo_pagina, date) del prospetto in corso
        continuazioni = 0
        for i, page in enumerate(pagine):
            base = {"pagina": page.number + 1, "tipo_pagina": "nota_o_testo", "disposizione": "colonna_unica",
                    "schema": "iv_cee_di_legge", "sezioni": [], "continuazione": False, "codici_conto": False,
                    "totali_stampati": True, "anno_precedente": False, "negativi": "parentesi",
                    "fondi_ammortamento": "assenti", "note": "xbrl di legge, mappa deterministica"}
            oltre_nota = indice_nota is not None and i >= indice_nota
            titolo = None if oltre_nota else _titolo_pagina(page)
            date = tuple(w[4] for w in sorted(page.get_text("words"), key=lambda w: (w[1], w[0])) if DATA.match(w[4]))
            importi_ok = _importi_pagina(page) >= MIN_IMPORTI
            if titolo and importi_ok and date:
                colonne, anno_precedente = _colonne(date)
                tipo = "prospetto_sp" if titolo == "stato patrimoniale" else "prospetto_ce"
                base.update(tipo_pagina=tipo, sezioni=[{"posizione": "unica", "contenuto": "misto", "colonne": colonne}],
                            anno_precedente=anno_precedente)
                blocco_aperto = (tipo, date)
                continuazioni = 0
            elif (not oltre_nota and blocco_aperto is not None and not titolo and importi_ok
                  and continuazioni < MAX_PAGINE_CONTINUAZIONE and not _apre_sezione_nuova(page)):
                tipo, date_blocco = blocco_aperto
                colonne, anno_precedente = _colonne(date_blocco)
                base.update(tipo_pagina=tipo, continuazione=True,
                            sezioni=[{"posizione": "unica", "contenuto": "misto", "colonne": colonne}],
                            anno_precedente=anno_precedente)
                continuazioni += 1
            else:
                blocco_aperto = None
                continuazioni = 0
            mappe.append(base)
    return mappe


def _intestazione_pagina(page) -> str:
    """La prima riga di testo che contiene almeno due parole di intestazione tipiche, normalizzata;
    vuota se la pagina non ristampa le intestazioni (continuazione)."""
    chiavi = ("saldo", "importo", "descrizione", "conto", "dare", "avere", "rettifiche", "corrente", "precedente",
              "esercizio", "31-12", "31/12", "30-06", "30/06")
    righe = {}
    for w in page.get_text("words"):
        righe.setdefault(round(w[1] / 4), []).append(w[4].lower())
    for y in sorted(righe):
        parole = righe[y]
        if sum(1 for p in parole if any(k in p for k in chiavi)) >= 2:
            return " ".join(parole)
    return ""


def blocchi(pdf: str) -> list[Blocco]:
    """Pagine con importi, divise ai titoli di prospetto e alle intestazioni di colonna diverse.

    Una pagina si unisce al blocco precedente solo se il suo titolo PROPRIO non e' None, e' uguale
    al titolo del blocco, e la sua intestazione di colonna e' uguale (o vuota, il caso normale di
    una vera continuazione che non ristampa le intestazioni). Riusare la mappa e' un'economia
    lecita solo dove il titolo stampato dal documento stesso dimostra che la pagina appartiene
    allo stesso prospetto: senza un titolo, un'intestazione di colonna identica non basta a
    dimostrarlo da sola (un bilancio di verifica misto SP/CE, senza titoli, riusava la stessa
    mappa su piu' pagine ed e' uscito sbilanciato — rilievo del bench reale, riesame di Task 7b).
    Una pagina senza titolo proprio comincia quindi sempre un blocco suo, con una vision propria."""
    import fitz
    out: list[Blocco] = []
    with fitz.open(pdf) as doc:
        for page in doc:
            if _importi_pagina(page) < MIN_IMPORTI:
                continue
            titolo, intestazione = _titolo_pagina(page), _intestazione_pagina(page)
            precedente = out[-1] if out else None
            stesso = (precedente is not None and titolo is not None and titolo == precedente.titolo
                      and (intestazione == "" or intestazione == precedente.intestazione))
            if stesso:
                precedente.pagine.append(page.number + 1)
            else:
                out.append(Blocco([page.number + 1], titolo, intestazione))
    return out


def _client():
    import anthropic
    return anthropic.Anthropic(max_retries=1, timeout=120)


def mappa_pagina(client, png: bytes) -> dict:
    r = client.messages.create(
        model=MODELLO, max_tokens=900,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.b64encode(png).decode()}},
            {"type": "text", "text": PROMPT}]}],
        tools=[{"name": "struttura", "description": "struttura della pagina", "input_schema": SCHEMA}],
        tool_choice={"type": "tool", "name": "struttura"})
    blocchi = [b for b in r.content if b.type == "tool_use"]
    if not blocchi:
        raise RuntimeError("mappa senza tool_use")
    out = dict(blocchi[0].input)
    out["_token"] = {"in": r.usage.input_tokens, "out": r.usage.output_tokens}
    return out


def mappa_documento(pdf: str, mappa_pagina_fn=None, cache_dir: str | None = None, concorrenza: int = 6) -> list[dict]:
    """Una mappa per pagina, con UNA chiamata al modello per blocco: le pagine seguenti del
    blocco riusano la mappa con continuazione=True; le pagine senza importi sono nota_o_testo."""
    cache = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache = os.path.join(cache_dir, os.path.basename(pdf) + ".mappa.json")
        if os.path.exists(cache):
            with open(cache, encoding="utf-8") as fh:
                return json.load(fh)
    import fitz
    fn = mappa_pagina_fn or mappa_pagina
    gruppi = blocchi(pdf)
    client = None if mappa_pagina_fn else _client()
    with fitz.open(pdf) as doc:
        n_pagine = doc.page_count
        prime = [doc[b.pagine[0] - 1].get_pixmap(dpi=110).tobytes("png") for b in gruppi]
    with ThreadPoolExecutor(max_workers=concorrenza) as pool:
        mappe_blocco = list(pool.map(lambda png: fn(client, png), prime))
    mappe = [{"pagina": i + 1, "tipo_pagina": "nota_o_testo", "disposizione": "colonna_unica",
              "schema": "elenco_piatto", "sezioni": [], "continuazione": False, "codici_conto": False,
              "totali_stampati": False, "anno_precedente": False, "negativi": "non_visibile",
              "fondi_ammortamento": "assenti", "note": "filtrata: nessun importo"} for i in range(n_pagine)]
    for blocco, mappa in zip(gruppi, mappe_blocco):
        for k, pagina in enumerate(blocco.pagine):
            # k > 0 forza la continuazione sulle pagine che riusano la mappa del blocco: e' vero
            # per costruzione, non una dichiarazione del modello. Sulla prima pagina (k == 0) la
            # mappa e' quella che il modello ha dichiarato per QUELLA pagina, e puo' gia' dire
            # "continuazione": True da sola (un blocco di una pagina sola tipato "dettaglio_conti"
            # che continua il prospetto precedente): sovrascriverla a False la faceva sparire da
            # leggi_documento (rilievo del bench reale, terzo giro di Task 7b).
            mappe[pagina - 1] = {**mappa, "pagina": pagina, "continuazione": bool(mappa.get("continuazione")) or k > 0}
    mappe[0]["_chiamate"] = len(gruppi)
    if cache:
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(mappe, fh, ensure_ascii=False, indent=1)
    return mappe
