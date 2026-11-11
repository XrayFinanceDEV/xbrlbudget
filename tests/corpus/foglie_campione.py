"""Foglie del percorso del lettore, in pari o no, sul campione e sul corpus (Fase 5, Task 1). Offline.

Il percorso del lettore decide `foglie_non_in_pari`/`senza_foglie_sp` PRIMA di qualunque chiamata al modello
(`percorso._foglie_non_in_pari`, la guardia di costo): le foglie e il loro pareggio si misurano quindi senza gx10.
Lo strumento ripete i passi di `percorso._importa` fino a quella guardia — `leggi_pdf` → `colonne_utili` →
`foglie_contabili` e `ancore` della colonna corrente — e si ferma: nessun modello, nessun DB, nessuna rete.

Stato per documento:
- `in_pari`: la guardia passa e ogni foglia ha sezione, lato (SP) e verso (CE): il pareggio e' verificato;
- `foglie_non_in_pari` / `senza_foglie_sp`: la guardia del percorso rinuncia (nessuna classe puo' sistemarlo);
- `sezione_ignota` / `lato_ignoto` / `verso_ignoto`: la guardia passa perche' «non lo sa» (il percorso chiamerebbe il
  modello, ma il pareggio non e' verificabile qui);
- `senza_colonna`, `vuoto`, `errore`; le scansioni (criterio dell'endpoint `/import/pdf`) stanno a parte, `scansione`:
  il lettore le legge solo dalle celle MinerU.

`--confronta <etichetta>` mette a fianco un giro precedente dello strumento: un documento e' cambiato se cambia lo stato
o l'impronta delle foglie (id, etichetta, importo, sezione, lato, verso, percorso di legge). `--adottati <etichetta>`
legge gli esiti di un giro di `punteggio.py` e marca i documenti adottati dal lettore in almeno un giro: una
correzione di lettura che ne cambia le foglie va spiegata (Review Focus 1 del piano).

Uso (cifre dei clienti: l'uscita sta fuori da git, in `$IMPORT_PUNTEGGIO_DIR/<etichetta>/foglie.{json,md}`):
    IMPORT_CORPUS_ROOT=... IMPORT_PUNTEGGIO_DIR=... backend/venv/bin/python tests/corpus/foglie_campione.py \
        --etichetta foglie-base [--corpus] [--solo 395,1456] [--confronta foglie-x] [--adottati fase4-ad2b581-R3]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "corpus"))

CAMPIONE = ROOT / "tests" / "corpus" / "campione.json"
MANIFESTO = ROOT / "tests" / "corpus" / "manifest.json"
CORPUS = Path(os.environ.get("IMPORT_CORPUS_ROOT", ROOT / "Test"))
USCITA = Path(os.environ.get("IMPORT_PUNTEGGIO_DIR", ROOT / "Test" / "_analisi-campione" / "punteggio"))
_ZERO = Decimal(0)

STATI_RINUNCIA = ("foglie_non_in_pari", "senza_foglie_sp")


def _impronta(f) -> list:
    return [f.id, f.etichetta, str(f.importo), f.sezione, f.lato_sp, f.verso_ce, f.percorso_legale]


def misura(percorso: str | Path) -> dict:
    """Stato, conteggi e foglie del percorso del lettore sulla colonna corrente, senza modello. Mai un'eccezione."""
    from importers.lettore.componi import e_risultato, importo_sp, lato_sp
    from importers.lettore.foglie import ancore, colonne_utili, foglie_contabili
    from importers.lettore.percorso import _foglie_non_in_pari
    from importers.lettore.righe import leggi_pdf

    try:
        doc = leggi_pdf(str(percorso))
        if not doc.righe:
            return {"stato": "vuoto"}
        corrente, precedente = colonne_utili(doc)
        if corrente is None:
            return {"stato": "senza_colonna", "righe": len(doc.righe)}
        foglie = foglie_contabili(doc, corrente)
        anc = ancore(doc, corrente)
        motivo = _foglie_non_in_pari(foglie, anc)
    except Exception as exc:  # noqa: BLE001 - uno strumento di misura non si ferma su un documento
        return {"stato": "errore", "errore": f"{type(exc).__name__}: {exc}"[:300]}

    con_importo = [f for f in foglie if f.importo]
    sp = [f for f in con_importo if f.sezione == "SP"]
    ce = [f for f in con_importo if f.sezione == "CE"]
    conti_sp = [f for f in sp if lato_sp(f) is not None and not e_risultato(f)]
    conteggi = {
        "foglie": len(foglie),
        "sp": len(sp), "ce": len(ce),
        "senza_sezione": sum(1 for f in con_importo if f.sezione not in ("SP", "CE")),
        "senza_lato": sum(1 for f in sp if lato_sp(f) is None),
        "senza_verso": sum(1 for f in ce if f.verso_ce not in ("costo", "ricavo") and not e_risultato(f)),
        "senza_percorso": sum(1 for f in con_importo if not f.percorso_legale),
        "ancore": len(anc),
    }
    attivo = sum((importo_sp(f) for f in conti_sp if lato_sp(f) == "A"), _ZERO)
    passivo = sum((importo_sp(f) for f in conti_sp if lato_sp(f) == "P"), _ZERO)
    if motivo:
        stato = motivo
    elif conteggi["senza_sezione"]:
        stato = "sezione_ignota"
    elif conteggi["senza_lato"]:
        stato = "lato_ignoto"
    elif conteggi["senza_verso"]:
        stato = "verso_ignoto"
    else:
        stato = "in_pari"
    impronte = [_impronta(f) for f in foglie]
    firma = hashlib.sha256(json.dumps(impronte, ensure_ascii=False).encode()).hexdigest()[:16]
    return {"stato": stato, "corrente": corrente, "precedente": precedente, **conteggi,
            "attivo": str(attivo), "passivo": str(passivo), "differenza": str(attivo - passivo),
            "ancore_chiavi": sorted({a.chiave for a in anc}), "firma": firma, "impronte": impronte}


def documenti(corpus: bool, solo: list[str] | None) -> list[dict]:
    campione = {d["id"]: d for d in json.loads(CAMPIONE.read_text())["documenti"]}
    if corpus:
        import punteggio
        docs = punteggio.documenti_del_corpus(json.loads(MANIFESTO.read_text()), campione)
    else:
        docs = [{"id": i, "path": d["path"], "tipologia": d.get("tipologia"), "in_campione": True}
                for i, d in campione.items()]
    for d in docs:
        d.setdefault("tipologia", (campione.get(d["id"]) or {}).get("tipologia"))
    return [d for d in docs if not solo or d["id"] in solo]


def _e_scansione(percorso: Path) -> bool:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.api.v1.imports import _e_una_scansione
    return _e_una_scansione(percorso.read_bytes())


def adottati(etichetta: str) -> set[str]:
    """Id adottati dal lettore in almeno un giro di un rapporto di `punteggio.py` (esiti.jsonl)."""
    import punteggio
    esiti = USCITA / etichetta / "esiti.jsonl"
    out = set()
    for riga in esiti.read_text().splitlines():
        if riga.strip():
            g = json.loads(riga)
            if punteggio.adottato_dal_lettore(g):
                out.add(str(g["id"]))
    return out


def confronta(prima: dict, dopo: dict) -> list[dict]:
    """Documenti presenti in entrambi i giri con stato o foglie diversi."""
    out = []
    for i in sorted(set(prima) & set(dopo), key=lambda x: (len(x), x)):
        a, b = prima[i], dopo[i]
        if a.get("stato") != b.get("stato") or a.get("firma") != b.get("firma"):
            ia = {tuple(x) for x in a.get("impronte") or []}
            ib = {tuple(x) for x in b.get("impronte") or []}
            out.append({"id": i, "prima": a.get("stato"), "dopo": b.get("stato"),
                        "foglie_tolte": len(ia - ib), "foglie_nuove": len(ib - ia)})
    return out


def _righe_rapporto(etichetta: str, misure: dict, docs: list[dict], diff: list[dict] | None, base: str | None,
                    adott: set[str]) -> list[str]:
    stati = Counter(m["stato"] for m in misure.values())
    righe = [f"# Foglie del lettore — {etichetta}", "", f"{len(misure)} documenti.", "", "| Stato | Documenti |",
             "|---|---|"]
    righe += [f"| {s} | {n} |" for s, n in stati.most_common()]
    per_id = {d["id"]: d for d in docs}
    righe += ["", "## Per documento", "", "| Id | Tipologia | Stato | Foglie | Senza sez. | Senza lato | Differenza A-P |"
              " Adottato |", "|---|---|---|---|---|---|---|---|"]
    for i, m in sorted(misure.items(), key=lambda x: (x[1]["stato"], len(x[0]), x[0])):
        righe.append(f"| {i} | {per_id.get(i, {}).get('tipologia') or ''} | {m['stato']} | {m.get('foglie', '')} | "
                     f"{m.get('senza_sezione', '')} | {m.get('senza_lato', '')} | {m.get('differenza', '')} | "
                     f"{'sì' if i in adott else ''} |")
    if diff is not None:
        righe += ["", f"## Cambiati rispetto a `{base}`", ""]
        if not diff:
            righe.append("Nessun documento cambiato.")
        else:
            righe += ["| Id | Prima | Dopo | Foglie tolte | Foglie nuove | Adottato |", "|---|---|---|---|---|---|"]
            righe += [f"| {d['id']} | {d['prima']} | {d['dopo']} | {d['foglie_tolte']} | {d['foglie_nuove']} | "
                      f"{'**sì**' if d['id'] in adott else ''} |" for d in diff]
    return righe


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--etichetta", required=True)
    ap.add_argument("--corpus", action="store_true")
    ap.add_argument("--solo", default=None, help="id separati da virgola")
    ap.add_argument("--confronta", default=None, metavar="ETICHETTA")
    ap.add_argument("--adottati", default=None, metavar="ETICHETTA_PUNTEGGIO")
    a = ap.parse_args(argv)
    solo = [x.strip() for x in a.solo.split(",")] if a.solo else None

    docs = documenti(a.corpus, solo)
    misure: dict[str, dict] = {}
    for d in docs:
        p = CORPUS / d["path"]
        if not p.exists():
            misure[d["id"]] = {"stato": "mancante"}
        elif _e_scansione(p):
            misure[d["id"]] = {"stato": "scansione"}
        else:
            misure[d["id"]] = misura(p)
    adott = adottati(a.adottati) if a.adottati else set()
    diff = None
    if a.confronta:
        prima = json.loads((USCITA / a.confronta / "foglie.json").read_text())["misure"]
        diff = confronta(prima, misure)

    cartella = USCITA / a.etichetta
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / "foglie.json").write_text(json.dumps(
        {"etichetta": a.etichetta, "corpus": a.corpus, "confronta": a.confronta, "adottati": sorted(adott),
         "cambiati": diff, "misure": misure}, ensure_ascii=False, indent=1))
    righe = _righe_rapporto(a.etichetta, misure, docs, diff, a.confronta, adott)
    (cartella / "foglie.md").write_text("\n".join(righe) + "\n")

    stati = Counter(m["stato"] for m in misure.values())
    print(f"{len(misure)} documenti: " + ", ".join(f"{s} {n}" for s, n in stati.most_common()))
    if diff is not None:
        print(f"cambiati rispetto a {a.confronta}: {len(diff)}"
              + "".join(f"\n  {d['id']}: {d['prima']} -> {d['dopo']} (-{d['foglie_tolte']} +{d['foglie_nuove']})"
                        + ("  ADOTTATO" if d["id"] in adott else "") for d in diff))
    print(f"rapporto: {cartella / 'foglie.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
