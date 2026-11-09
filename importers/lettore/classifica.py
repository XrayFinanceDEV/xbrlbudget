"""La classificazione in due passi delle foglie, con i voti sui blocchi che non tornano (Fase 3, Task 3).

Passo 1: foglia -> macro-voce. Una foglia con un percorso di legge ben formato prende la macro dalla tavola senza
modello; le altre vanno a Qwen a blocchi, con JSON guidato: ogni id ha il proprio enum, le macro ammesse da *quel*
lato e verso, le sole rettifiche che possono attraversare il lato (`tavola.rettifiche_ammesse`: un fondo dal passivo,
il netto in diminuzione dall'attivo) piu' «X» (non e' un conto). Qwen indica una classe per un id, mai un importo. Una risposta fuori
dall'enum e' scartata e la foglia resta senza classe (F3-6): la massa senza classe la dichiara chi compone.
Passo 2: dentro ogni macro con dettagli (`tavola.DETTAGLI`) la sotto-voce, o «altri» se non si sa; la macro non
cambia mai. Un dettaglio che il percorso di legge dice esattamente si tiene senza chiedere (decisione del
proprietario, 2026-11-09: «max details if possible, if not generic accounts»).
"""
from __future__ import annotations

import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from decimal import Decimal

from importers import llm_provider
from importers.llm_provider import ContestoEccessivo, LLMProviderError, RispostaTroncata
from importers.lettore import _ereditati, tavola
from importers.lettore.foglie import Ancora, Foglia, gettoni_di_legge
from importers.lettore.totali import _norm

BLOCCO = 60
TIMEOUT = 120.0
NON_UN_CONTO = "X"
ALTRI = "altri"

PROMPT_MACRO = (
    "Sei un ragioniere italiano. Per ogni riga di un bilancio indica la voce di legge (art. 2424 stato "
    "patrimoniale, art. 2425 conto economico) a cui appartiene il conto, scegliendo SOLO fra i codici ammessi per "
    "quella riga. Il lato (attivo/passivo, costo/ricavo) e' gia' deciso dalla colonna in cui l'importo e' "
    "stampato: non contraddirlo. Un conto il cui nome sembra dell'altro lato (un fornitore, un debito o un rateo "
    "passivo con saldo dare fra le attivita'; un cliente o un credito con saldo avere fra le passivita') e' un saldo "
    "a lato invertito: e' comunque un conto e va sulla voce ammessa piu' vicina (crediti o debiti verso altri, "
    "ratei e risconti). Uniche eccezioni, coi codici che finiscono in .F o .N: un fondo ammortamento o "
    "svalutazione stampato fra le passivita' rettifica il bene dell'attivo (codice .F del bene); perdite portate a "
    "nuovo o azioni proprie stampate fra le attivita' stanno in diminuzione del netto (codice .N). Fondi rischi, "
    "TFR e fondi imposte restano passivita'. "
    "Rispondi «X» solo se la riga non e' un conto (intestazione, nota, totale, riferimento): ogni riga che ti "
    "mando ha un importo che conta, e una riga col nome di una voce di legge («Immobilizzazioni immateriali», «Crediti "
    "entro l'esercizio») e' il conto di quella voce, non un'intestazione. "
    "Conta la natura del conto, non il mastro del gestionale: compensi e contributi degli amministratori sono "
    "servizi (B.7); il lavoro somministrato o interinale e' costo del personale (B.9); i depositi cauzionali versati "
    "sono immobilizzazioni finanziarie; i versamenti dei soci in conto capitale o a copertura perdite sono riserve, "
    "non capitale sociale; migliorie, lavori e spese incrementative su beni di terzi sono immobilizzazioni "
    "immateriali; il trattamento di fine rapporto (C) e' solo il fondo TFR, mentre i debiti verso dipendenti per "
    "retribuzioni o ferie e verso fondi pensione sono debiti. "
    "Non scrivere mai importi. Rispondi solo con un JSON {id: codice}.")
PROMPT_DETTAGLIO = (
    "Sei un ragioniere italiano. Ogni riga e' gia' stata assegnata a una voce di bilancio: indica la sotto-voce "
    "che la descrive, scegliendo SOLO fra quelle ammesse per quella riga, oppure «altri» se nessuna calza. "
    "Regole: conti correnti bancari o postali con saldo avere, carte di credito e anticipi bancari sono debiti "
    "verso banche; i finanziamenti dei soci e i finanziamenti "
    "agevolati di enti pubblici sono debiti verso altri finanziatori; fatture da ricevere sono debiti verso fornitori; "
    "acconti ricevuti dai clienti, debiti verso controllanti, collegate o altre societa' del gruppo, verso dipendenti "
    "e amministratori sono altri debiti; i crediti verso controllanti o collegate vanno nella loro sotto-voce. "
    "Un ammortamento che non dice la categoria va sulle immobilizzazioni materiali. Le riserve che citano una legge "
    "di rivalutazione o di riallineamento sono riserve di rivalutazione. Le rimanenze di merci sono prodotti finiti "
    "e merci, non materie prime. "
    "Non scrivere mai importi. Rispondi solo con un JSON {id: codice}.")
NOTA_VOTO = "Nota: questo blocco non torna contro il totale stampato nel documento; rileggi con attenzione ogni riga."


@dataclass
class Classe:
    macro: str | None          # "sp06"; None = senza classe
    dettaglio: str | None      # "sp06a"; None = non noto (la foglia va nel secchio «altri» della macro)
    fonte: str                 # "legale" | "modello" | "voto" | "nessuna" | "errore" (il modello ha fallito)
    voti: tuple[str, ...] = ()
    rettifica: str | None = None   # percorso di legge di una rettifica stampata nella colonna opposta (`tavola.RETTIFICHE`)


def _lato_colonna(f: Foglia) -> str:
    lato = f.lato
    if lato == "U" and f.sezione != "CE":
        lato = {"A": "L", "P": "R"}.get(f.lato_sp or "", "U")
    return lato


def _ammesse(f: Foglia) -> tuple[str, ...]:
    return tavola.macro_ammesse(_lato_colonna(f), f.sezione or "SP", f.verso_ce)


# Un contro-conto si riconosce dal nome (decisione del proprietario, 2026-11-09: «contro-conti riconosciuti»): un
# fondo ammortamento o svalutazione, una rettifica di valore; dall'attivo perdite portate a nuovo o azioni proprie.
# Senza, il modello usava il «.F» per un conto qualunque che non trovava posto sul lato (una banca in avere sotto le
# disponibilita' liquide nettata sui crediti verso clienti): una massa spostata fra lati senza che nessun cancello
# la veda.
# Un fondo e' un contro-conto solo se dice di che cosa: ammortamento, svalutazione, deprezzamento, rettifica, o un fondo
# sui crediti (il «fondo rischi su crediti» tassato e' la svalutazione crediti). «Fondi pensione», il fondo TFR, un
# fondo rischi e oneri sono debiti o fondi del passivo, mai una rettifica dell'attivo (revisione Task 11).
_TESTA_FONDO = r"(?:\bF(?:ONDO|ONDI|DO|DI)\b|\bF\s*[./]\s*(?:D[OI]\b|(?=AMM|SVAL)))"
_FONDO = re.compile(rf"AMMORT|SVALUT|DEPREZZ|RETTIFIC|{_TESTA_FONDO}.*(?:\bAMM|SVAL|CREDIT)", re.I)
_NETTO_IN_DIMINUZIONE = re.compile(r"PERDIT|AZION\w*\s+PROPRI|RISERV\w*\s+NEGATIV", re.I)


# Le voci a parole chiave di route C per lo SP sono tag interni: solo quelli che sono una macro-voce (o il lordo di
# una immobilizzazione) diventano un indizio. `equity_total` (capitale, riserve e utile insieme) e `debt_bank`
# (breve o lungo) non nominano una macro: restano senza indizio, come i fondi (`depr_*`) e le voci di conto economico.
_INDIZIO_SP = {"gross_sp02": "sp02", "gross_sp03": "sp03", "gross_sp04": "sp04", "sp05": "sp05", "sp06": "sp06",
               "sp09": "sp09", "sp10": "sp10", "sp14": "sp14", "sp15": "sp15", "sp16": "sp16", "sp18": "sp18"}


def indizio(f: Foglia) -> str | None:
    """La macro-voce che i classificatori a parole chiave di oggi darebbero all'etichetta: un indizio per il
    modello, mai un vincolo. CE: la catena di route C (`_ereditati.catena_ce`: regole di mastro, `_resolve_ce_field`, conto foglia, sinonimo)
    nella direzione della colonna (mai `iv_cee_hierarchy.resolve` con `side`: su un nodo CE non filtra nulla); SP: le regole a parole chiave di route C per il lato della
    colonna. `None` se non decidono, se la direzione o il lato sono ignoti, o se l'esito non e' fra le macro
    ammesse per il lato (un indizio contro la colonna non entra mai)."""
    nome = f.etichetta.upper()
    if (f.sezione or "SP") == "CE":
        direzione = {"costo": "costi", "ricavo": "ricavi"}.get(f.verso_ce or "")
        campo = _ereditati.catena_ce(nome, direzione) if direzione else None
    else:
        lato = _lato_colonna(f)
        if lato == "U":
            return None
        campo = _INDIZIO_SP.get(_ereditati._regola_sp(nome, "attivo" if lato == "L" else "passivo") or "")
    macro = tavola.macro_di(campo.split("_")[0]) if campo else None  # ce10_close, ce02_open: il tag e' la macro
    return macro if macro in _ammesse(f) else None


def _rettifiche(f: Foglia) -> tuple[str, ...]:
    """Le rettifiche del lato opposto che la foglia puo' essere (solo SP; un fondo dal passivo, il netto in
    diminuzione dall'attivo): l'unica eccezione a «la colonna decide il lato», e solo per un conto che il nome dice
    contro-conto."""
    if (f.sezione or "SP") != "SP":
        return ()
    ammesse = tavola.rettifiche_ammesse(_lato_colonna(f))
    if not ammesse:
        return ()
    nome = _FONDO if ammesse[0].endswith(".F") else _NETTO_IN_DIMINUZIONE
    return ammesse if nome.search(f.etichetta) else ()


def _classe(codice: str | None, fonte: str, voti: tuple[str, ...] = ()) -> Classe:
    """La classe di una risposta valida: una macro-voce, oppure una rettifica (campo dal percorso di legge, come
    nel percorso snello: macro del bene o del netto, dettaglio se il percorso lo dice)."""
    if codice is None:
        return Classe(None, None, fonte, voti)
    if codice in tavola.RETTIFICHE:
        p = tavola.RETTIFICHE[codice]
        campo = tavola.campo_da_percorso_legale(p)
        macro = tavola.macro_di(campo)
        return Classe(macro, campo if campo != macro else None, fonte, voti, rettifica=p)
    return Classe(codice, None, fonte, voti)


def _chiave(f: Foglia) -> tuple:
    return (_norm(f.etichetta), _norm(f.contesto[-1]) if f.contesto else "", f.lato, f.sezione, f.verso_ce,
            f.lato_sp)


def _da_percorso(f: Foglia) -> Classe | None:
    if not f.percorso_legale:
        return None
    campo = tavola.campo_da_percorso_legale(f.percorso_legale)
    if not campo:
        return None
    macro = tavola.macro_di(campo)
    if macro not in _ammesse(f):
        return None
    dettaglio = campo if campo != macro else None
    return Classe(macro, dettaglio, "legale")


def _schema(enum_per_id: dict[str, list[str]]) -> dict:
    return {"type": "object",
            "properties": {i: {"type": "string", "enum": e} for i, e in enum_per_id.items()},
            "required": list(enum_per_id), "additionalProperties": False}


def _contesto(f: Foglia) -> str:
    parti = []
    if f.contesto:     # i mastri sopra il conto, anche quelli di una catena non verificata: ne dicono la natura
        parti.append("sotto: " + " > ".join(f.contesto[-3:]))
    parti.append({"L": "colonna sinistra", "R": "colonna destra", "U": "colonna unica"}.get(f.lato, f.lato))
    if f.sezione:
        parti.append(f.sezione)
    if f.sezione != "CE":
        lato = {"L": "A", "R": "P"}.get(f.lato) or (f.lato_sp if f.lato == "U" else None)
        if lato:
            parti.append("attivo" if lato == "A" else "passivo")
    if f.verso_ce:
        parti.append(f.verso_ce)
    return "; ".join(parti)


def _fratelli(f: Foglia, blocco: list[Foglia]) -> str:
    stessi = [g.etichetta for g in blocco if g.id != f.id and g.contesto[-1:] == f.contesto[-1:]]
    return "; fratelli: " + ", ".join(stessi[:4]) if stessi else ""


def _richiesta(blocco: list[Foglia], enum_per_id: dict[str, list[str]], etichette: dict[str, str],
               nota: str = "", *, fratelli: bool = False, macro_assegnata: dict[str, str] | None = None,
               ) -> tuple[list[dict], dict]:
    usati = sorted({c for e in enum_per_id.values() for c in e if c in etichette})
    legenda = "\n".join(f"{c}: {etichette[c]}" for c in usati)
    righe = "\n".join(
        f"{f.id} | {f.etichetta} | {_contesto(f)}{_fratelli(f, blocco) if fratelli else ''}"
        + (f"; indizio dalle parole chiave: {i}" if not macro_assegnata and (i := indizio(f)) else "")
        + (f" | voce: {macro_assegnata[f.id]}" if macro_assegnata and f.id in macro_assegnata else "")
        + f" | ammessi: {', '.join(enum_per_id[f.id])}" for f in blocco)
    testo = ("Classifica queste righe.\n\nCodici:\n" + legenda + "\n\n" + (nota + "\n\n" if nota else "")
             + "Righe (id | voce | contesto):\n" + righe)
    return [{"role": "user", "content": testo}], _schema(enum_per_id)


_ERRORI_DA_DIMEZZARE = (RispostaTroncata, ContestoEccessivo)


def _chiama(chiama_json, system: str, blocco, enum_per_id, etichette, nota="", diag: dict | None = None,
            **opzioni) -> tuple[dict[str, str], set[str]]:
    """(risposte {id: codice}, id del blocco persi per un errore del modello). Mai un'eccezione.

    Su risposta troncata o contesto eccessivo il blocco si dimezza e si riprova, fino a una foglia; su
    qualunque altro errore del provider il blocco si abbandona."""
    messaggi, schema = _richiesta(blocco, enum_per_id, etichette, nota, **opzioni)
    try:
        out = chiama_json(system, messaggi, schema, max_tokens=40 + 14 * len(blocco), timeout=TIMEOUT)
    except _ERRORI_DA_DIMEZZARE:
        if len(blocco) > 1:
            if diag is not None:
                diag["dimezzamenti"] = diag.get("dimezzamenti", 0) + 1
            m = len(blocco) // 2
            ris, persi = {}, set()
            for meta in (blocco[:m], blocco[m:]):
                r, p = _chiama(chiama_json, system, meta, {f.id: enum_per_id[f.id] for f in meta}, etichette,
                               nota, diag, **opzioni)
                ris.update(r)
                persi |= p
            return ris, persi
        return {}, {f.id for f in blocco}
    except LLMProviderError:
        return {}, {f.id for f in blocco}
    if not isinstance(out, dict):
        return {}, {f.id for f in blocco}
    return {str(k): v for k, v in out.items() if isinstance(v, str)}, set()


def _blocchi(foglie: list[Foglia]) -> list[list[Foglia]]:
    return [foglie[i:i + BLOCCO] for i in range(0, len(foglie), BLOCCO)]


def _in_parallelo(chiamate: list) -> list:
    if not chiamate:
        return []
    with ThreadPoolExecutor(llm_provider.GX10_CONCORRENZA) as ex:
        return list(ex.map(lambda c: c(), chiamate))


def _enum_macro(f: Foglia) -> list[str]:
    return list(_ammesse(f)) + list(_rettifiche(f)) + [NON_UN_CONTO]


def _valida(f: Foglia, risposta) -> str | None:
    return risposta if risposta in _enum_macro(f) and risposta != NON_UN_CONTO else None


def _chiama_default():
    return llm_provider.chiama_gx10_json


def classifica_macro(foglie: list[Foglia], *, chiama_json=None, cache: dict | None = None,
                     diagnostica: dict | None = None) -> dict[str, Classe]:
    """Passo 1. `diagnostica`, se dato, e' riempito con `foglie_errore` (foglie la cui domanda il modello non ha
    saputo evadere: fonte «errore», diverso da una risposta «X» o fuori enum, che e' «nessuna»), `blocchi_falliti`
    (id persi) e `dimezzamenti`."""
    chiama_json = chiama_json or _chiama_default()
    cache = cache if cache is not None else {}
    diag = diagnostica if diagnostica is not None else {}
    diag.setdefault("foglie_errore", 0)
    diag.setdefault("dimezzamenti", 0)
    classi: dict[str, Classe] = {}
    da_chiedere: dict[tuple, list[Foglia]] = {}
    for f in foglie:
        legale = _da_percorso(f)
        if legale:
            classi[f.id] = legale
            continue
        k = ("macro",) + _chiave(f)
        if k in cache:
            m = cache[k]
            classi[f.id] = _classe(m, "modello") if m else Classe(None, None, "nessuna")
            continue
        da_chiedere.setdefault(k, []).append(f)
    rappresentanti = [gruppo[0] for gruppo in da_chiedere.values()]
    risposte = _in_parallelo([
        (lambda b=b: _chiama(chiama_json, PROMPT_MACRO, b, {f.id: _enum_macro(f) for f in b},
                             tavola.ETICHETTE_MACRO, diag=diag)) for b in _blocchi(rappresentanti)])
    per_id: dict[str, str] = {}
    persi: set[str] = set()
    for r, p in risposte:
        per_id.update(r)
        persi |= p
    for k, gruppo in da_chiedere.items():
        rep = gruppo[0]
        if rep.id in persi:
            for f in gruppo:
                classi[f.id] = Classe(None, None, "errore")
            diag["foglie_errore"] += len(gruppo)
            continue
        r = per_id.get(rep.id)
        macro = _valida(rep, r)     # «X», fuori enum, assente: senza classe
        if macro or rep.id in per_id:
            cache[k] = macro
        for f in gruppo:
            classi[f.id] = _classe(macro, "modello") if macro else Classe(None, None, "nessuna")
    diag["blocchi_falliti"] = len(persi)
    return classi


def _variante(n: int, blocco: list[Foglia], ancora: Ancora | None, somma: Decimal | None) -> tuple[list[Foglia], str, dict]:
    """Il voto n-esimo presenta il blocco in modo diverso, perche' a temperatura zero la stessa domanda darebbe
    la stessa risposta (F3-11). 0: ogni foglia coi soli antenati; 1: l'ancora con totale stampato e somma di oggi
    (mai importi di foglia); 2: ordine rovesciato e contesto dei fratelli."""
    n %= 3
    if n == 0:
        return blocco, NOTA_VOTO + " Ogni riga va letta da sola, col solo contesto dei suoi antenati.", {}
    if n == 1:
        if ancora is not None and somma is not None:
            nota = (f"{NOTA_VOTO} Questi conti dovrebbero sommare a {ancora.chiave} = {ancora.importo}; "
                    f"oggi sommano {somma}.")
        else:
            nota = NOTA_VOTO + " Verifica che le righe, insieme, rifacciano il totale della voce."
        return blocco, nota, {}
    return blocco[::-1], NOTA_VOTO + " Guarda anche le righe vicine dello stesso gruppo.", {"fratelli": True}


def rivota(foglie: list[Foglia], classi: dict[str, Classe], *, voti: int = 3, chiama_json=None,
           ancora: Ancora | None = None, somma: Decimal | None = None,
           cache: dict | None = None) -> dict[str, Classe]:
    """Rivota le sole foglie date (mai una classe «legale»); ritorna copie, non muta `classi`. Ogni voto presenta
    il blocco in modo diverso (`_variante`). `ancora`/`somma` danno al secondo voto il totale stampato e la somma
    di oggi; `cache`, se data, e' aggiornata con l'esito."""
    chiama_json = chiama_json or _chiama_default()
    nuove = {i: replace(c) for i, c in classi.items()}
    foglie = [f for f in foglie if not (classi.get(f.id) and classi[f.id].fonte == "legale")]
    if not foglie:
        return nuove
    chiamate, indice = [], []
    for b in _blocchi(foglie):
        for n in range(voti):
            ordine, nota, opz = _variante(n, b, ancora, somma)
            chiamate.append(lambda o=ordine, nota=nota, opz=opz: _chiama(
                chiama_json, PROMPT_MACRO, o, {f.id: _enum_macro(f) for f in o}, tavola.ETICHETTE_MACRO, nota, **opz))
            indice.append(b)
    risposte = _in_parallelo(chiamate)
    raccolti: dict[str, list[str]] = {f.id: [] for f in foglie}
    for b, (r, _persi) in zip(indice, risposte):
        for f in b:
            raccolti[f.id].append(r.get(f.id, "?"))
    for f in foglie:
        v = tuple(raccolti[f.id])
        precedente = classi.get(f.id) or Classe(None, None, "nessuna")
        validi = [x for x in v if x in _enum_macro(f)]
        macro_voto, n = (Counter(validi).most_common(1)[0] if validi else (None, 0))
        if macro_voto is not None and n * 2 > voti:
            macro = None if macro_voto == NON_UN_CONTO else macro_voto
            nuove[f.id] = _classe(macro, "voto", v)
            if cache is not None:
                cache[("macro",) + _chiave(f)] = macro
        else:
            nuove[f.id] = Classe(precedente.macro, precedente.dettaglio, "voto", v, precedente.rettifica)
    return nuove


def _voce(c: Classe) -> str:
    if c.rettifica:
        return f"{c.macro} ({tavola.ETICHETTE_MACRO.get(c.macro + '.F', 'rettifica')}: indica il bene rettificato)"
    return c.macro


# Le parole di una voce di legge che non dicono un dettaglio: la scadenza e i connettivi
_PAROLE_SENZA_DETTAGLIO = {"verso", "esigibili", "entro", "oltre", "esercizio", "successivo", "mesi", "totale", "di",
                           "e", "dei", "delle", "del", "della", "degli", "in", "su", "per", "da", "a", "con", "ed",
                           "al", "il", "lo", "la", "le", "gli", "l"}


def _nomina_solo_la_macro(f: Foglia, macro: str) -> bool:
    """Tolti enumeratori, scadenza e connettivi, ogni parola dell'etichetta e' una parola del nome della macro-voce
    (o ne comincia: «immobilizzazioni» per «immob»)."""
    nome = tavola.ETICHETTE_MACRO.get(macro, "").split()
    parole = [w for w in re.findall(r"[a-z]+", _norm(f.etichetta))
              if len(w) > 1 and w not in _PAROLE_SENZA_DETTAGLIO and not re.fullmatch(r"[ivx]+", w)]
    return all(any(w.startswith(n) or n.startswith(w) for n in nome if len(n) >= 4) for w in parole)


def classifica_dettagli(foglie: list[Foglia], classi: dict[str, Classe], *, chiama_json=None,
                        cache: dict | None = None) -> None:
    chiama_json = chiama_json or _chiama_default()
    cache = cache if cache is not None else {}
    da_chiedere: dict[tuple, list[Foglia]] = {}
    for f in foglie:
        c = classi.get(f.id)
        if not c or c.macro not in tavola.DETTAGLI or c.dettaglio:
            continue
        if c.fonte == "legale" and gettoni_di_legge(f.etichetta, f.codice) and _nomina_solo_la_macro(f, c.macro):
            # la foglia e' la voce di legge stampata e ne porta solo il nome («II - Crediti» di un abbreviato): il
            # dettaglio e' ignoto e la massa va in «altri», mai inventata. «II - Crediti verso clienti» nomina il
            # dettaglio, e il passo 2 lo puo' dare
            continue
        k = ("dettaglio", c.macro, c.rettifica) + _chiave(f)
        if k in cache:
            c.dettaglio = cache[k]
            continue
        da_chiedere.setdefault(k, []).append(f)
    rappresentanti = [g[0] for g in da_chiedere.values()]
    enum = lambda f: list(tavola.DETTAGLI[classi[f.id].macro]) + [ALTRI]
    etichette = {d: tavola.nome_pieno(d).split("_", 1)[1].replace("_", " ")
                 for ds in tavola.DETTAGLI.values() for d in ds}
    etichette[ALTRI] = "nessuna delle altre sotto-voci"
    risposte = _in_parallelo([
        (lambda b=b: _chiama(chiama_json, PROMPT_DETTAGLIO, b, {f.id: enum(f) for f in b}, etichette,
                             macro_assegnata={f.id: _voce(classi[f.id]) for f in b}))
        for b in _blocchi(rappresentanti)])
    per_id: dict[str, str] = {}
    for r, _p in risposte:
        per_id.update(r)
    for k, gruppo in da_chiedere.items():
        rep = gruppo[0]
        r = per_id.get(rep.id)
        det = r if r in tavola.DETTAGLI[classi[rep.id].macro] else None   # «altri» e fuori enum: nessun dettaglio
        if r is not None:
            cache[k] = det
        for f in gruppo:
            classi[f.id].dettaglio = det


# --- scadenza dei debiti ------------------------------------------------------------------------------------------
# Regola del proprietario (CLAUDE.md, «Debito senza scadenza dichiarata → a breve»): un debito va oltre 12 mesi solo con
# una prova stampata - «oltre 12 mesi / l'esercizio», «lungo termine», «medio/lungo», «m/l» - nel conto o nel suo mastro
# (eccezione del 2026-10-28: il mastro «medio/lungo termine» e' una scadenza dichiarata). Senza prova si va a breve:
# anticipare una scadenza peggiora gli indici di liquidita', non li abbellisce. Il modello sceglie fra sp16 e sp17
# dall'etichetta e da una corsa all'altra cambia idea (un «FINANZIAMENTI PASSIVI» va oltre in una corsa e no
# nell'altra): la scadenza la decide il testo, non lui.
_PERIODO = r"(?:I\s*)?(?:12\s*M|L\W?\s*(?:ANNO|ESERCIZIO)|ES\.?\s*SUCC|ESERCIZIO\s+SUCC)"
# «(OE)»/«(EE)»: le sigle «oltre/entro l'esercizio» dei gestionali, come le legge `detail_enrichment._ledger_maturity`
_OLTRE = re.compile(rf"\bOLTRE\s*{_PERIODO}|\bLUNGO\s+TERMINE|\bM(?:EDIO)?\s*/\s*L(?:UNGO)?\b|\bA\s+LUNGO\b"
                    r"|\(OE[)\s-]")
_ENTRO = re.compile(rf"\bENTRO\s*{_PERIODO}|\bBREVE\s+TERMINE|\bA\s+BREVE\b|\(EE[)\s-]")
# interessi maturati in un mastro «medio/lungo» sono dovuti entro l'anno (proprietario, P3 del 2026-11-04)
_INTERESSI = re.compile(r"\bINTERESS|\bRATEI\b")


def scadenza_stampata(testo: str) -> str | None:
    """«E» | «O» se il testo dichiara una scadenza (una sola), altrimenti None."""
    t = (testo or "").upper()
    entro, oltre = bool(_ENTRO.search(t)), bool(_OLTRE.search(t))
    return None if entro == oltre else ("E" if entro else "O")


def _scadenza_del_debito(f: Foglia) -> str | None:
    """La scadenza che il documento stampa per la foglia: prima il suo conto, poi i mastri dal piu' vicino."""
    propria = scadenza_stampata(f.etichetta)
    if propria:
        return propria
    for a in reversed(f.contesto):
        s = scadenza_stampata(a)
        if s:
            return "E" if s == "O" and _INTERESSI.search(f.etichetta.upper()) else s
    return None


_DEBITI = {"E": "sp16", "O": "sp17"}


def scadenza_dei_debiti(foglie: list[Foglia], classi: dict[str, Classe]) -> tuple[dict[str, Classe], list[str]]:
    """Debiti verso sp16/sp17 dalla scadenza stampata, senza prova a breve. Solo le classi del modello (il percorso
    di legge porta gia' la sua scadenza) e solo fra sp16 e sp17: la natura resta, il dettaglio passa alla stessa
    lettera dell'altra parte (sp17a -> sp16a). Ritorna copie e le scelte dichiarate."""
    nuove = dict(classi)
    scelte: list[str] = []
    for f in foglie:
        k = classi.get(f.id)
        if k is None or k.fonte == "legale" or k.rettifica or k.macro not in ("sp16", "sp17"):
            continue
        s = _scadenza_del_debito(f)
        voluta = _DEBITI.get(s or "E")
        if voluta == k.macro:
            continue
        dettaglio = voluta + k.dettaglio[4:] if k.dettaglio else None
        nuove[f.id] = replace(k, macro=voluta, dettaglio=dettaglio)
        perche = "scadenza stampata" if s else "nessuna scadenza stampata"
        scelte.append(f"debito {'oltre' if voluta == 'sp17' else 'a breve'} ({perche}): {f.id}")
    return nuove, scelte


def imposte_anticipate_oltre(foglie: list[Foglia], classi: dict[str, Classe]) -> tuple[dict[str, Classe], list[str]]:
    """Imposte anticipate senza scadenza stampata -> oltre 12 mesi (sp07f), regola D14 del proprietario
    (2026-10-28): per un credito la prudenza e' l'opposto dei debiti, e il percorso di legge «5-ter» non dice la
    scadenza. Resta entro solo con un «entro» stampato (nel percorso, nel conto o nel mastro). Copie, scelte dichiarate."""
    nuove = dict(classi)
    scelte: list[str] = []
    for f in foglie:
        k = classi.get(f.id)
        if k is None or k.rettifica or k.dettaglio != "sp06f":
            continue
        if (f.percorso_legale or "").endswith(".E") or _scadenza_del_debito(f) == "E":
            continue
        nuove[f.id] = replace(k, macro="sp07", dettaglio="sp07f")
        scelte.append(f"imposte anticipate oltre 12 mesi (nessuna scadenza stampata): {f.id}")
    return nuove, scelte
