"""Confronta due esecuzioni di tests/_import_probe.py (per esempio Haiku contro Qwen).

uso: python scripts/confronta_probe.py A.jsonl B.jsonl
Per ogni file: il candidato vincente di route C, attivo, sbilancio, utile, e i campi che
cambiano. I campi sono il vero oggetto del confronto: la quadratura non vede uno
spostamento fra due campi dello stesso lato.
"""
from __future__ import annotations

import json
import sys


def _carica(percorso: str) -> list[dict]:
    with open(percorso, encoding="utf-8") as fh:
        return [json.loads(riga) for riga in fh if riga.strip()]


def confronta(a: list[dict], b: list[dict]) -> list[dict]:
    per_a = {r["file"]: r for r in a}
    per_b = {r["file"]: r for r in b}
    out = []
    for f in sorted(set(per_a) | set(per_b)):
        ra, rb = per_a.get(f), per_b.get(f)
        if ra is None or rb is None:
            out.append({"file": f, "solo_in": "A" if rb is None else "B"})
            continue
        ca, cb = ra.get("fields") or {}, rb.get("fields") or {}
        out.append({
            "file": f,
            "metodo": (ra.get("extraction_method"), rb.get("extraction_method")),
            "provider": (
                (ra.get("coge_provider"), ra.get("ivcee_provider"), ra.get("dettagli_provider")),
                (rb.get("coge_provider"), rb.get("ivcee_provider"), rb.get("dettagli_provider")),
            ),
            "attivo": (ra.get("totale_attivo"), rb.get("totale_attivo")),
            "stesso_attivo": ra.get("totale_attivo") == rb.get("totale_attivo"),
            "sbilancio": (ra.get("sbilancio"), rb.get("sbilancio")),
            "utile": (ra.get("utile_ce"), rb.get("utile_ce")),
            "campi_diversi": sorted(k for k in set(ca) | set(cb) if ca.get(k) != cb.get(k)),
            "secondi": (ra.get("secondi"), rb.get("secondi")),
        })
    return out


def main(argv: list[str]) -> None:
    for r in confronta(_carica(argv[1]), _carica(argv[2])):
        if "solo_in" in r:
            print(f"{r['file']}: presente solo in {r['solo_in']}")
            continue
        print(f"== {r['file']}")
        print(f"   metodo   {r['metodo'][0]}  |  {r['metodo'][1]}")
        print(f"   provider {r['provider'][0]}  |  {r['provider'][1]}")
        print(f"   attivo   {r['attivo'][0]}  |  {r['attivo'][1]}")
        print(f"   sbilancio {r['sbilancio'][0]}  |  {r['sbilancio'][1]}")
        print(f"   utile    {r['utile'][0]}  |  {r['utile'][1]}")
        print(f"   secondi  {r['secondi'][0]}  |  {r['secondi'][1]}")
        print(f"   campi diversi ({len(r['campi_diversi'])}): {', '.join(r['campi_diversi'][:15])}")


if __name__ == "__main__":
    main(sys.argv)
