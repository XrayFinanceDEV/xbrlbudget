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
    ("rotta", re.compile(r"^\s*@router\.(?:get|post|put|patch|delete)\(\s*[\"']([^\"']+)")),
    ("funzione", re.compile(r"^\s*export\s+default\s+(?:async\s+)?function\s+([A-Za-z_]\w*)")),
    ("funzione", re.compile(r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_]\w*)")),
    ("funzione", re.compile(r"^\s*export\s+const\s+([a-z][A-Za-z0-9_]*)\s*[:=]")),
    ("costante", re.compile(r"^\s*export\s+const\s+([A-Z][A-Z0-9_]{2,})\s*[:=]")),
    ("tipo", re.compile(r"^\s*export\s+(?:type|interface)\s+([A-Za-z_]\w*)")),
    ("colonna", re.compile(r"^\s*([a-z_]\w*)\s*=\s*Column\(")),
    ("costante", re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})\s*[:=]")),
]

# File rinominato/cancellato: cattura sia il vecchio (a/) sia il nuovo (b/) percorso,
# perche' su una cancellazione "+++" vale "/dev/null" e il nome va preso da qui.
_RIGA_DIFF_GIT = re.compile(r"^diff --git a/(.+) b/(.+)$")


@dataclass(frozen=True)
class Simbolo:
    """Un simbolo che il codice ha spostato (aggiunto o rimosso) in un diff.

    genere ∈ {"funzione", "classe", "costante", "colonna", "rotta", "tipo"}
    stato  ∈ {"aggiunto", "rimosso"}
    """
    nome: str
    genere: str
    file: str
    stato: str          # "aggiunto" | "rimosso"


def _e_codice(percorso: str) -> bool:
    return Path(percorso).suffix in ESTENSIONI_CODICE


def simboli_da_diff(diff: str) -> List[Simbolo]:
    """Simboli mossi, letti da un diff unificato. Un rename appare come rimosso +
    aggiunto: riconoscerlo come tale e' compito dello skill, con `git log -M`.

    Attribuzione del file: normalmente e' il percorso "b/" (nuovo). Su una
    cancellazione intera "+++" vale "/dev/null" — in quel caso i simboli rimossi
    vanno attribuiti al percorso "a/" (vecchio), letto dalla riga "diff --git",
    altrimenti spariscono o restano agganciati al file precedente nello stesso diff.
    """
    trovati, visti = [], set()
    file_corrente = ""
    file_vecchio = ""
    for riga in diff.splitlines():
        m_git = _RIGA_DIFF_GIT.match(riga)
        if m_git:
            file_vecchio, file_corrente = m_git.group(1), m_git.group(2)
            continue
        if riga.startswith("+++ "):
            percorso = riga[4:].strip()
            if percorso == "/dev/null":
                file_corrente = file_vecchio
            elif percorso.startswith("b/"):
                file_corrente = percorso[2:]
            else:
                file_corrente = percorso
            continue
        if riga.startswith("--- "):
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


@dataclass(frozen=True)
class Citazione:
    simbolo: str
    file: str
    riga: int
    testo: str


def documenti_che_nominano(simboli, radici) -> List[Citazione]:
    """Le righe di documentazione che nominano uno dei simboli mossi.

    E' questa fase a rendere il costo proporzionale al CAMBIAMENTO invece che al
    corpus: solo i documenti che nominano un simbolo mosso entrano in verifica.
    Il confine di parola (\\b) evita che `resolve` peschi `_resolve_ce_field`.

    `radici` sono percorsi da scandire: una cartella e' scandita ricorsivamente
    per `*.md`, ma una radice che e' essa stessa un file `.md` (es. CLAUDE.md,
    che vive nella root e non e' una cartella) viene letta direttamente —
    altrimenti sparirebbe in silenzio da ogni riallineamento.
    """
    if not simboli:
        return []
    per_nome = {}
    for s in simboli:
        per_nome.setdefault(s.nome, re.compile(r"\b" + re.escape(s.nome) + r"\b"))
    out = []
    for radice in radici:
        base = Path(radice)
        if not base.exists():
            continue
        if base.is_file():
            candidati = [base] if base.suffix == ".md" else []
        else:
            candidati = sorted(base.rglob("*.md"))
        for md in candidati:
            try:
                righe = md.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for n, testo in enumerate(righe, start=1):
                for nome, regola in per_nome.items():
                    if regola.search(testo):
                        out.append(Citazione(nome, str(md), n, testo.strip()[:200]))
    return out


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rev_range", help="intervallo di commit, es. HEAD~1..HEAD")
    parser.add_argument("--cwd", default=".", help="repository su cui operare")
    args = parser.parse_args()
    simboli = simboli_mossi(args.rev_range, cwd=args.cwd)
    print(json.dumps([asdict(s) for s in simboli], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
