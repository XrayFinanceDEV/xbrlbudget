#!/usr/bin/env python3
"""Parte meccanica del riallineamento documentazione <-> codice.

Trova i simboli che il codice ha mosso in un intervallo di commit e quali documenti
li nominano. NON modifica documentazione: osserva e riferisce. Chi decide cosa
correggere e cosa segnalare e' lo skill `/riallinea`, che consuma questo JSON.

Solo libreria standard: deve girare con `python3 scripts/riallinea.py`, senza venv.

Spec: docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md
"""
import argparse
import json
import re
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List

ESTENSIONI_CODICE = {".py", ".ts", ".tsx", ".js", ".jsx"}

# Riconoscimento per riga. Deliberatamente grossolano: un falso positivo costa una
# verifica in piu', un falso negativo costa un disallineamento non visto (spec §Rischi 3).
_REGOLE = [
    ("funzione", re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)")),
    ("classe", re.compile(r"^\s*class\s+([A-Za-z_]\w*)")),
    ("funzione", re.compile(r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_]\w*)")),
    ("funzione", re.compile(r"^\s*export\s+const\s+([a-z][A-Za-z0-9_]*)\s*[:=]")),
    ("colonna", re.compile(r"^\s*([a-z_]\w*)\s*=\s*Column\(")),
    ("costante", re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})\s*[:=]")),
]


@dataclass(frozen=True)
class Simbolo:
    nome: str
    genere: str
    file: str
    stato: str          # "aggiunto" | "rimosso"


def _e_codice(percorso: str) -> bool:
    return Path(percorso).suffix in ESTENSIONI_CODICE


def simboli_da_diff(diff: str) -> List[Simbolo]:
    """Simboli mossi, letti da un diff unificato. Un rename appare come rimosso +
    aggiunto: riconoscerlo come tale e' compito dello skill, con `git log -M`."""
    trovati, visti = [], set()
    file_corrente = ""
    for riga in diff.splitlines():
        if riga.startswith("+++ b/"):
            file_corrente = riga[6:].strip()
            continue
        if riga.startswith("--- ") or riga.startswith("diff --git"):
            continue
        if not riga or riga[0] not in "+-":
            continue
        stato = "aggiunto" if riga[0] == "+" else "rimosso"
        if not _e_codice(file_corrente):
            continue
        corpo = riga[1:]
        for genere, regola in _REGOLE:
            m = regola.match(corpo)
            if not m:
                continue
            chiave = (m.group(1), file_corrente, stato)
            if chiave in visti:
                break
            visti.add(chiave)
            trovati.append(Simbolo(m.group(1), genere, file_corrente, stato))
            break
    return trovati


def simboli_mossi(rev_range: str, cwd: str = ".") -> List[Simbolo]:
    """Come simboli_da_diff, ma prende il diff da git."""
    diff = subprocess.run(
        ["git", "diff", "-U0", "-M", rev_range],
        cwd=cwd, capture_output=True, text=True, check=True,
    ).stdout
    return simboli_da_diff(diff)


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rev_range", help="intervallo di commit, es. HEAD~1..HEAD")
    parser.add_argument("--cwd", default=".", help="repository su cui operare")
    args = parser.parse_args()
    simboli = simboli_mossi(args.rev_range, cwd=args.cwd)
    print(json.dumps([asdict(s) for s in simboli], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
