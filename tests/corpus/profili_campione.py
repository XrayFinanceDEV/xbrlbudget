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
    ... --rete          # in piu': su TUTTI i PDF di Test/, i totali dei prospetti finiti in una banda nota/altro

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

from importers.lettore.profilo import (  # noqa: E402
    _chiave_ripetuta, _nel_margine, _norm, _prova, _testo, _titolo_parte, profilo_documento)
from importers.lettore.righe import _pagine_pdf, profilo_pdf  # noqa: E402

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
        "contrapposto": prof.contrapposto,
        "parti": {str(k): v for k, v in prof.parti.items()},
        "tabelle_nota": len(prof.tabelle_nota),
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
    out["contrapposto_giusto"] = bool(reg.get("contrapposto")) == (famiglia == "contrapposte")
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
    ap.add_argument("--rete", action="store_true", help="rete di sicurezza su tutto il corpus")
    args = ap.parse_args()
    solo = {s.strip() for s in args.solo.split(",") if s.strip()} or None

    registri = []
    for doc in _documenti(solo):
        try:
            reg = _registro(doc)
        except Exception as e:          # la misura non si ferma su un documento
            reg = {"id": doc["id"], "path": doc["path"], "tipologia": doc["tipologia"], "errore": repr(e),
                   "tipo": None, "confine": None, "contrapposto": False, "esercizi_per_lato": 0,
                   "fini_stampate": []}
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
    con_periodi = [r for r in valutati if "periodi" in r["giudizio"]]
    print(f"\ncontrapposto giusto: {sum(r['giudizio']['contrapposto_giusto'] for r in valutati)}/{len(valutati)}"
          f" (contrapposte trovate {sum(bool(r['contrapposto']) for r in contr)}/{len(contr)}, "
          f"contrapposto su altri tipi {sum(bool(r['contrapposto']) for r in altri)})")
    print(f"tipo giusto: contrapposte {sum(r['giudizio']['tipo_giusto'] for r in contr)}/{len(contr)}, "
          f"altri {sum(r['giudizio']['tipo_giusto'] for r in altri)}/{len(altri)}")
    print(f"periodi giusti (colonne-esercizio per lato = periodi della verita'): "
          f"{sum(r['giudizio']['periodi'] == 'giusti' for r in con_periodi)}/{len(con_periodi)}")
    print("\nsbagliati:")
    for r in valutati:
        g = r["giudizio"]
        if not g["tipo_giusto"] or not g["contrapposto_giusto"]:
            print(f"  {r['id']:>10} {r['tipologia'][:26]:26} -> {r['tipo']} confine={r['confine']} "
                  f"| {r.get('tipo_perche') or r.get('errore')}")
    print("\nconfine fisico senza sezioni contrapposte (non e' un errore):")
    for r in registri:
        if r["confine"] is not None and not r.get("contrapposto"):
            avviso = next((a for a in r.get("avvisi", []) if "affiancate" in a), "")
            print(f"  {r['id']:>10} {r['tipologia'][:26]:26} {avviso}")
    print("\nperiodi sbagliati:")
    for r in con_periodi:
        if r["giudizio"]["periodi"] != "giusti":
            print(f"  {r['id']:>10} {r['tipologia'][:26]:26} {r['giudizio']['periodi']}")
    if args.rete:
        _rete()
    return 0


def _parte_di(bande: list[tuple[int, float, str]], pagina: int, y: float) -> str:
    parte = bande[0][2] if bande else "?"
    for p, y0, nome in bande:
        if (p, y0) <= (pagina, y):
            parte = nome
    return parte


def _rete() -> None:
    """Rete di sicurezza (R12): su ogni PDF del corpus, le righe con un totale dei prospetti («Totale attivo»,
    «Differenza tra valore e costi», «Utile (perdita) dell'esercizio», …) che stanno in una banda nota o altro.

    Si dividono in due: quelle sotto un titolo forte della nota (il rendiconto finanziario comincia dall'utile, la
    tabella delle variazioni del patrimonio netto ha «Totale patrimonio netto», il riepilogo del bilancio della
    controllante ripete i prospetti), elencate per titolo; e tutte le altre, cioe' un prospetto perso: l'obiettivo
    e' zero."""
    files = sorted(f for f in CORPUS.rglob("*") if f.suffix.lower() == ".pdf" and "_analisi-campione" not in f.parts)
    perse, sotto_nota = [], defaultdict(list)
    for f in files:
        try:
            pagine, altezze, _ = _pagine_pdf(str(f))
            prof = profilo_documento([r for rr in pagine for r in rr],
                                     altezze={n: h for n, h in enumerate(altezze, start=1)})
        except Exception as e:          # la rete non si ferma su un documento
            perse.append((f.name, 0, f"errore {e!r}"))
            continue
        titolo = None
        for n, rr in enumerate(pagine):
            for r in rr:
                t = None if (_nel_margine(r, altezze[n]) and _chiave_ripetuta(_testo(r)) in prof.margini) \
                    else _titolo_parte(r)
                if t is not None:
                    titolo = (t, _testo(r))
                if _prova(r) != "totale" or _parte_di(prof.bande, r.pagina, r.y) == "prospetto":
                    continue
                if titolo is not None and titolo[0] == "nota":
                    sotto_nota[_norm(titolo[1])[:45]].append(f"{f.name[:30]} p{r.pagina}")
                else:
                    perse.append((f.name, r.pagina, _testo(r)[:80]))
    print(f"\nrete di sicurezza su {len(files)} PDF: {len(perse)} totali dei prospetti fuori dal prospetto senza un "
          f"titolo della nota sopra (obiettivo 0)")
    for nome, pagina, testo in perse:
        print(f"  {nome[:50]:50} p{pagina} {testo}")
    print(f"sotto un titolo della nota: {sum(map(len, sotto_nota.values()))} righe, per titolo:")
    for titolo, dove in sorted(sotto_nota.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(dove):3}  «{titolo}»  es. {dove[0]}")


if __name__ == "__main__":
    raise SystemExit(main())
