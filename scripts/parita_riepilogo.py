#!/usr/bin/env python3
"""Riepilogo delle divergenze del banco di parita' (`scripts/parita_motore.py --json`).

Perche' esiste (lotto 3A, Task 1). Ogni task del lotto dichiara PRIMA quali celle del banco
devono muoversi e in quali scenari. Questo script raggruppa le divergenze per profilo e campo e,
con `--attese`, elenca quelle che nessun pattern ammette. Un pattern e' `fnmatch` su
`<scenario>|<campo>`: lo scenario e' `<fixture>__<profilo>`, il campo e' quello del banco
(`balance_sheet.sp09_disponibilita_liquide`, `details.debito_bancario`, `@errore`, `@anno`).

Uso:
    backend/venv/bin/python scripts/parita_riepilogo.py /tmp/parita.json
    backend/venv/bin/python scripts/parita_riepilogo.py /tmp/parita.json \\
        --attese '*__finanziamento|balance_sheet.sp17a_*' '*|details.debito_bancario'

Uscita: 0 se nessuna divergenza e' fuori dalle attese (o se `--attese` manca), 1 altrimenti.
"""
import argparse
import fnmatch
import json
import sys
from collections import Counter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("json", help="il file scritto da parita_motore.py --json")
    parser.add_argument("--attese", nargs="*", default=None,
                        help="pattern fnmatch '<fixture>__<profilo>|<campo>' delle divergenze ammesse")
    argomenti = parser.parse_args()
    with open(argomenti.json, encoding="utf-8") as fh:
        dati = json.load(fh)
    divergenze = dati.get("divergenze") or []
    gruppi: Counter = Counter()
    fuori = []
    for d in divergenze:
        profilo = d["scenario"].partition("__")[2] or d["scenario"]
        gruppi[(profilo, d["campo"])] += 1
        chiave = f"{d['scenario']}|{d['campo']}"
        if argomenti.attese is not None and not any(fnmatch.fnmatchcase(chiave, p) for p in argomenti.attese):
            fuori.append(d)
    for (profilo, campo), n in sorted(gruppi.items()):
        print(f"{n:5d}  {profilo:28s} {campo}")
    print(f"totale divergenze: {len(divergenze)}; controllo negativo: {dati.get('controllo_negativo')}")
    if argomenti.attese is None:
        return 0
    print(f"fuori dalle attese: {len(fuori)}")
    for d in fuori[:60]:
        print(f"  [{d['scenario']} · {d['anno']}] {d['campo']}: {d['valore_a']} -> {d['valore_b']}")
    return 1 if fuori else 0


if __name__ == "__main__":
    sys.exit(main())
