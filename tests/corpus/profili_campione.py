"""Misura del profilo del documento (Task 5-bis) sul campione annotato.

Per i documenti di `Test/_analisi-campione/campione.json` e `wk44/campione.json` calcola il profilo
(`importers.lettore.righe.profilo_pdf`, nessuna rete, nessun modello, nessun DB) e lo confronta con la
tipologia annotata a mano:

- **tipo**: `ivcee` -> `schema`, `ivcee-dettaglio` -> `schema-dettaglio`, `contrapposte` -> `contrapposte`,
  `conti` -> `verifica`; `scansione` e `limite` si contano a parte;
- **contrapposto**: un confine fra i lati su tutti e soli i documenti `contrapposte`;
- **periodi**: le colonne-esercizio (per lato, sulle contrapposte) contro i periodi di `verita/<id>.json`.

I PDF e le verita' sono cifre di clienti, fuori da git (`Test/` e' ignorata).

Uso:
    IMPORT_CORPUS_ROOT=$PWD/Test backend/venv/bin/python tests/corpus/profili_campione.py --etichetta profilo
    ... --solo 395,1456

Scrive `Test/_analisi-campione/profili/<etichetta>.json` (un profilo per documento) e stampa la sintesi.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from importers.lettore.righe import profilo_pdf  # noqa: E402

CORPUS = Path(os.environ.get("IMPORT_CORPUS_ROOT", ROOT / "Test"))
CAMPIONE = CORPUS / "_analisi-campione"
ELENCHI = (CAMPIONE / "campione.json", CAMPIONE / "wk44" / "campione.json")
USCITA = CAMPIONE / "profili"
TIPO_ATTESO = {"ivcee": "schema", "ivcee-dettaglio": "schema-dettaglio", "contrapposte": "contrapposte",
               "conti": "verifica"}
A_PARTE = ("scansione", "limite")
_VALORI = ("esercizio", "saldo")


def _documenti(solo: set[str] | None) -> list[dict]:
    docs = []
    for elenco in ELENCHI:
        docs += json.loads(elenco.read_text(encoding="utf-8"))
    return [d for d in docs if not solo or d["id"] in solo]


def _periodi_veri(doc_id: str) -> list[str] | None:
    f = CAMPIONE / "verita" / f"{doc_id}.json"
    if not f.exists():
        return None
    return [p.get("fine") for p in json.loads(f.read_text(encoding="utf-8")).get("periodi", [])]


def _registro(doc: dict) -> dict:
    prof = profilo_pdf(str(CORPUS / doc["path"]))
    ruoli: dict[str, int] = defaultdict(int)
    for c in prof.colonne:
        ruoli[c.ruolo] += 1
    per_lato: dict[str, int] = defaultdict(int)
    fini = set()
    for c in prof.colonne:
        if c.ruolo in _VALORI:
            per_lato[c.lato] += 1
            if c.fine is not None:
                fini.add(c.fine.strftime("%Y-%m"))
    return {
        "id": doc["id"], "path": doc["path"], "tipologia": doc["tipologia"],
        "tipo": prof.tipo, "tipo_perche": prof.tipo_perche,
        "confine": None if prof.confine is None else round(prof.confine, 1),
        "colonne": [{"indice": c.indice, "x": round(c.x_destra, 1), "lato": c.lato, "ruolo": c.ruolo,
                     "fine": c.fine.isoformat() if c.fine else None, "mesi": c.mesi, "corrente": c.corrente}
                    for c in prof.colonne],
        "colonne_per_ruolo": dict(ruoli),
        "esercizi_per_lato": max(per_lato.values(), default=0),
        "fini_stampate": sorted(fini),
        "negativi": sorted(prof.negativi),
        "decimali": {str(k): v for k, v in prof.decimali.items()},
        "codici": [{"forma": f.forma, "x0": round(f.x0, 1), "x_etichetta": round(f.x_etichetta, 1),
                    "con_importi": f.con_importi, "senza_importi": f.senza_importi} for f in prof.codici],
        "sezioni": {str(k): v for k, v in prof.sezioni.items()},
        "margini": len(prof.margini),
        "avvisi": prof.avvisi,
    }


def _giudizio(reg: dict) -> dict:
    famiglia = reg["tipologia"].split("/")[0]
    out = {"famiglia": famiglia}
    if famiglia in A_PARTE:
        return out
    out["tipo_giusto"] = reg["tipo"] == TIPO_ATTESO.get(famiglia)
    out["contrapposto_giusto"] = (reg["confine"] is not None) == (famiglia == "contrapposte")
    veri = _periodi_veri(reg["id"])
    if veri:
        n_ok = reg["esercizi_per_lato"] == len(veri)
        fini_ok = set(reg["fini_stampate"]) <= set(veri)
        out["periodi"] = "giusti" if n_ok and fini_ok else (
            f"{reg['esercizi_per_lato']} colonne per {len(veri)} periodi" if not n_ok
            else f"date stampate {reg['fini_stampate']} fuori da {veri}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--etichetta", required=True)
    ap.add_argument("--solo", default="", help="id separati da virgola")
    args = ap.parse_args()
    solo = {s.strip() for s in args.solo.split(",") if s.strip()} or None

    registri = []
    for doc in _documenti(solo):
        try:
            reg = _registro(doc)
        except Exception as e:          # la misura non si ferma su un documento
            reg = {"id": doc["id"], "path": doc["path"], "tipologia": doc["tipologia"], "errore": repr(e),
                   "tipo": None, "confine": None, "esercizi_per_lato": 0, "fini_stampate": []}
        reg["giudizio"] = _giudizio(reg)
        registri.append(reg)

    USCITA.mkdir(parents=True, exist_ok=True)
    (USCITA / f"{args.etichetta}.json").write_text(json.dumps(registri, ensure_ascii=False, indent=1),
                                                   encoding="utf-8")

    per_famiglia: dict[str, list[dict]] = defaultdict(list)
    for reg in registri:
        per_famiglia[reg["giudizio"]["famiglia"]].append(reg)
    print(f"{'tipologia':18} {'doc':>4} {'tipo ok':>8} {'contr. ok':>10} {'periodi ok':>11}   tipi trovati")
    for fam in sorted(per_famiglia):
        regs = per_famiglia[fam]
        trovati = defaultdict(int)
        for r in regs:
            trovati[r["tipo"]] += 1
        if fam in A_PARTE:
            print(f"{fam:18} {len(regs):>4} {'-':>8} {'-':>10} {'-':>11}   {dict(trovati)}")
            continue
        tipo_ok = sum(r["giudizio"]["tipo_giusto"] for r in regs)
        contr_ok = sum(r["giudizio"]["contrapposto_giusto"] for r in regs)
        con_periodi = [r for r in regs if "periodi" in r["giudizio"]]
        per_ok = sum(r["giudizio"]["periodi"] == "giusti" for r in con_periodi)
        print(f"{fam:18} {len(regs):>4} {tipo_ok:>8} {contr_ok:>10} {per_ok:>5}/{len(con_periodi):<5}   "
              f"{dict(trovati)}")
    valutati = [r for r in registri if r["giudizio"]["famiglia"] not in A_PARTE]
    altri = [r for r in valutati if r["giudizio"]["famiglia"] != "contrapposte"]
    contr = [r for r in valutati if r["giudizio"]["famiglia"] == "contrapposte"]
    print(f"\ncontrapposto giusto: {sum(r['giudizio']['contrapposto_giusto'] for r in valutati)}/{len(valutati)}"
          f" (contrapposte trovate {sum(r['confine'] is not None for r in contr)}/{len(contr)}, "
          f"confini su altri tipi {sum(r['confine'] is not None for r in altri)})")
    print(f"tipo giusto: contrapposte {sum(r['giudizio']['tipo_giusto'] for r in contr)}/{len(contr)}, "
          f"altri {sum(r['giudizio']['tipo_giusto'] for r in altri)}/{len(altri)}")
    print("\nsbagliati:")
    for r in valutati:
        g = r["giudizio"]
        if not g["tipo_giusto"] or not g["contrapposto_giusto"]:
            print(f"  {r['id']:>10} {r['tipologia'][:26]:26} -> {r['tipo']} confine={r['confine']} "
                  f"| {r.get('tipo_perche') or r.get('errore')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
