"""La classificazione in due passi delle foglie, con i voti sui blocchi che non tornano (Fase 3, Task 3).

Passo 1: foglia -> macro-voce. Una foglia con un percorso di legge ben formato prende la macro dalla tavola senza
modello; le altre vanno a Qwen a blocchi, con JSON guidato: ogni id ha il proprio enum, le macro ammesse da *quel*
lato e verso piu' «X» (non e' un conto). Qwen indica una classe per un id, mai un importo. Una risposta fuori
dall'enum e' scartata e la foglia resta senza classe (F3-6): la massa senza classe la dichiara chi compone.
Passo 2: dentro le macro con un KPI sopra (`DETTAGLI_KPI`) la sotto-voce, o «altri»; la macro non cambia mai.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from importers import llm_provider
from importers.llm_provider import LLMProviderError
from importers.lettore import tavola
from importers.lettore.foglie import Foglia
from importers.lettore.totali import _norm

BLOCCO = 60
NON_UN_CONTO = "X"
ALTRI = "altri"

PROMPT_MACRO = (
    "Sei un ragioniere italiano. Per ogni riga di un bilancio indica la voce di legge (art. 2424 stato "
    "patrimoniale, art. 2425 conto economico) a cui appartiene il conto, scegliendo SOLO fra i codici ammessi per "
    "quella riga. Il lato (attivo/passivo, costo/ricavo) e' gia' deciso dalla colonna in cui l'importo e' "
    "stampato: non contraddirlo. Rispondi «X» se la riga non e' un conto (intestazione, nota, riferimento). "
    "Non scrivere mai importi. Rispondi solo con un JSON {id: codice}.")
PROMPT_DETTAGLIO = (
    "Sei un ragioniere italiano. Ogni riga e' gia' stata assegnata a una voce di bilancio: indica la sotto-voce "
    "che la descrive, scegliendo SOLO fra quelle ammesse per quella riga, oppure «altri» se nessuna calza. "
    "Non scrivere mai importi. Rispondi solo con un JSON {id: codice}.")
NOTA_VOTO = "Nota: questo blocco non torna contro il totale stampato nel documento; rileggi con attenzione ogni riga."


@dataclass
class Classe:
    macro: str | None          # "sp06"; None = senza classe
    dettaglio: str | None      # "sp06a" solo per le macro di DETTAGLI_KPI, altrimenti None
    fonte: str                 # "legale" | "modello" | "voto" | "nessuna"
    voti: tuple[str, ...] = ()


def _ammesse(f: Foglia) -> tuple[str, ...]:
    lato = f.lato
    if lato == "U" and f.sezione != "CE":
        lato = {"A": "L", "P": "R"}.get(f.lato_sp or "", "U")
    return tavola.macro_ammesse(lato, f.sezione or "SP", f.verso_ce)


def _chiave(f: Foglia) -> tuple:
    return (_norm(f.etichetta), f.lato, f.sezione, f.verso_ce, f.lato_sp)


def _da_percorso(f: Foglia) -> Classe | None:
    if not f.percorso_legale:
        return None
    campo = tavola.campo_da_percorso_legale(f.percorso_legale)
    if not campo:
        return None
    macro = tavola.macro_di(campo)
    if macro not in _ammesse(f):
        return None
    dettaglio = campo if campo != macro and campo in tavola.DETTAGLI_KPI.get(macro, ()) else None
    return Classe(macro, dettaglio, "legale")


def _schema(enum_per_id: dict[str, list[str]]) -> dict:
    return {"type": "object",
            "properties": {i: {"type": "string", "enum": e} for i, e in enum_per_id.items()},
            "required": list(enum_per_id), "additionalProperties": False}


def _contesto(f: Foglia) -> str:
    parti = []
    if f.antenati:
        parti.append("sotto: " + " > ".join(f.antenati[-3:]))
    parti.append({"L": "colonna sinistra", "R": "colonna destra", "U": "colonna unica"}.get(f.lato, f.lato))
    if f.sezione:
        parti.append(f.sezione)
    if f.verso_ce:
        parti.append(f.verso_ce)
    return "; ".join(parti)


def _richiesta(blocco: list[Foglia], enum_per_id: dict[str, list[str]], etichette: dict[str, str],
               intro: str, nota: str = "") -> tuple[list[dict], dict]:
    usati = sorted({c for e in enum_per_id.values() for c in e if c in etichette})
    legenda = "\n".join(f"{c}: {etichette[c]}" for c in usati)
    righe = "\n".join(f"{f.id} | {f.etichetta} | {_contesto(f)} | ammessi: {', '.join(enum_per_id[f.id])}"
                      for f in blocco)
    testo = f"{intro}\n\nCodici:\n{legenda}\n\n" + (nota + "\n\n" if nota else "") + f"Righe (id | voce | contesto):\n{righe}"
    return [{"role": "user", "content": testo}], _schema(enum_per_id)


def _chiama(chiama_json, system: str, blocco, enum_per_id, etichette, nota="") -> dict[str, str]:
    """Le risposte {id: codice} del blocco; vuoto se il modello fallisce o risponde male. Mai un'eccezione."""
    messaggi, schema = _richiesta(blocco, enum_per_id, etichette, "Classifica queste righe.", nota)
    try:
        out = chiama_json(system, messaggi, schema, max_tokens=40 + 14 * len(blocco), timeout=900.0)
    except LLMProviderError:
        return {}
    if not isinstance(out, dict):
        return {}
    return {str(k): v for k, v in out.items() if isinstance(v, str)}


def _blocchi(foglie: list[Foglia]) -> list[list[Foglia]]:
    return [foglie[i:i + BLOCCO] for i in range(0, len(foglie), BLOCCO)]


def _in_parallelo(chiamate: list) -> list:
    if not chiamate:
        return []
    with ThreadPoolExecutor(llm_provider.GX10_CONCORRENZA) as ex:
        return list(ex.map(lambda c: c(), chiamate))


def _enum_macro(f: Foglia) -> list[str]:
    return list(_ammesse(f)) + [NON_UN_CONTO]


def _chiama_default():
    return llm_provider.chiama_gx10_json


def classifica_macro(foglie: list[Foglia], *, chiama_json=None, cache: dict | None = None) -> dict[str, Classe]:
    chiama_json = chiama_json or _chiama_default()
    cache = cache if cache is not None else {}
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
            classi[f.id] = Classe(m, None, "modello") if m else Classe(None, None, "nessuna")
            continue
        da_chiedere.setdefault(k, []).append(f)
    rappresentanti = [gruppo[0] for gruppo in da_chiedere.values()]
    blocchi = _blocchi(rappresentanti)
    risposte = _in_parallelo([
        (lambda b=b: _chiama(chiama_json, PROMPT_MACRO, b, {f.id: _enum_macro(f) for f in b},
                             tavola.ETICHETTE_MACRO)) for b in blocchi])
    per_id: dict[str, str] = {}
    for r in risposte:
        per_id.update(r)
    for k, gruppo in da_chiedere.items():
        rep = gruppo[0]
        r = per_id.get(rep.id)
        macro = r if r in _ammesse(rep) else None     # «X», fuori enum, assente: senza classe
        if macro or rep.id in per_id:
            cache[k] = macro
        for f in gruppo:
            classi[f.id] = Classe(macro, None, "modello") if macro else Classe(None, None, "nessuna")
    return classi


def rivota(foglie: list[Foglia], classi: dict[str, Classe], *, voti: int = 3,
           chiama_json=None) -> dict[str, Classe]:
    chiama_json = chiama_json or _chiama_default()
    nuove = dict(classi)
    if not foglie:
        return nuove
    chiamate, indice = [], []
    for b in _blocchi(foglie):
        for _ in range(voti):
            chiamate.append(lambda b=b: _chiama(chiama_json, PROMPT_MACRO, b, {f.id: _enum_macro(f) for f in b},
                                                tavola.ETICHETTE_MACRO, NOTA_VOTO))
            indice.append(b)
    risposte = _in_parallelo(chiamate)
    raccolti: dict[str, list[str]] = {f.id: [] for f in foglie}
    for b, r in zip(indice, risposte):
        for f in b:
            raccolti[f.id].append(r.get(f.id, "?"))
    for f in foglie:
        v = tuple(raccolti[f.id])
        precedente = classi.get(f.id) or Classe(None, None, "nessuna")
        validi = [x for x in v if x in _enum_macro(f)]
        macro_voto, n = (Counter(validi).most_common(1)[0] if validi else (None, 0))
        if macro_voto is not None and n * 2 > voti:
            macro = None if macro_voto == NON_UN_CONTO else macro_voto
            nuove[f.id] = Classe(macro, None, "voto", v)
        else:
            nuove[f.id] = Classe(precedente.macro, precedente.dettaglio, "voto", v)
    return nuove


def classifica_dettagli(foglie: list[Foglia], classi: dict[str, Classe], *, chiama_json=None,
                        cache: dict | None = None) -> None:
    chiama_json = chiama_json or _chiama_default()
    cache = cache if cache is not None else {}
    da_chiedere: dict[tuple, list[Foglia]] = {}
    for f in foglie:
        c = classi.get(f.id)
        if not c or c.macro not in tavola.DETTAGLI_KPI or c.dettaglio:
            continue
        k = ("dettaglio", _norm(f.etichetta), c.macro)
        if k in cache:
            c.dettaglio = cache[k]
            continue
        da_chiedere.setdefault(k, []).append(f)
    rappresentanti = [g[0] for g in da_chiedere.values()]
    enum = lambda f: list(tavola.DETTAGLI_KPI[classi[f.id].macro]) + [ALTRI]
    etichette = {d: tavola.nome_pieno(d).split("_", 1)[1].replace("_", " ")
                 for ds in tavola.DETTAGLI_KPI.values() for d in ds}
    etichette[ALTRI] = "nessuna delle altre sotto-voci"
    risposte = _in_parallelo([
        (lambda b=b: _chiama(chiama_json, PROMPT_DETTAGLIO, b, {f.id: enum(f) for f in b}, etichette))
        for b in _blocchi(rappresentanti)])
    per_id: dict[str, str] = {}
    for r in risposte:
        per_id.update(r)
    for k, gruppo in da_chiedere.items():
        rep = gruppo[0]
        r = per_id.get(rep.id)
        det = r if r in tavola.DETTAGLI_KPI[classi[rep.id].macro] else None   # «altri» e fuori enum: nessun dettaglio
        if r is not None:
            cache[k] = det
        for f in gruppo:
            classi[f.id].dettaglio = det
