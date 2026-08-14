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


def _pathspec():
    """Chiedere a git il solo codice: uno sweep completo altrimenti trascina
    i PDF tracciati in docs/examples/ e li fa decodificare per niente."""
    return [f"*{e}" for e in sorted(ESTENSIONI_CODICE)]


def simboli_mossi(rev_range: str, cwd: str = ".") -> List[Simbolo]:
    """Come simboli_da_diff, ma prende il diff da git.

    Il diff e' letto in bytes e decodificato a mano con errors="replace": un
    repository che traccia binari (i PDF di docs/examples/) non deve far esplodere
    l'intero sweep con un UnicodeDecodeError. Il pathspec dopo "--" e' la cura vera:
    non chiede a git i binari, cosi' non c'e' nulla da decodificare per sbaglio.
    """
    diff = subprocess.run(
        ["git", "diff", "-U0", "-M", rev_range, "--", *_pathspec()],
        cwd=cwd, capture_output=True, check=True,
    ).stdout.decode("utf-8", errors="replace")
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


SOGLIA_GENERICO = 40


def riduci_generici(citazioni: List[Citazione]):
    """Separa i simboli troppo comuni per essere verificati per nome (>= SOGLIA_GENERICO
    citazioni) dal resto. Non e' un troncamento silenzioso: il simbolo esce da
    `citazioni` ed entra in `generici` con il proprio conteggio totale e i primi 5
    file in cui compare, cosi' lo skill puo' dire "troppo comune per essere verificato
    per nome" invece di sommergere le poche segnalazioni vere di un diff reale sotto
    centinaia di righe (misurato: 9 nomi generici -> 1147 citazioni in un colpo solo).
    """
    per_nome = {}
    for c in citazioni:
        per_nome.setdefault(c.simbolo, []).append(c)
    generici_nomi = {nome for nome, lst in per_nome.items() if len(lst) >= SOGLIA_GENERICO}
    if not generici_nomi:
        return citazioni, []
    ridotte = [c for c in citazioni if c.simbolo not in generici_nomi]
    generici = []
    for nome in sorted(generici_nomi):
        lst = per_nome[nome]
        file_visti = []
        for c in lst:
            if c.file not in file_visti:
                file_visti.append(c.file)
            if len(file_visti) >= 5:
                break
        generici.append({"nome": nome, "citazioni": len(lst), "file": file_visti})
    return ridotte, generici


RADICI_DOC = ["docs", "CLAUDE.md"]
RADICE_MEMORIA = str(
    Path.home() / ".claude" / "projects" / "-home-peter-DEV-budget" / "memory"
)
STATO_DEFAULT = "docs/superpowers/allineamento/STATO.json"


def carica_stato(percorso: str) -> dict:
    p = Path(percorso)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salva_stato(percorso: str, sha: str, modo: str, data: str) -> None:
    """Uno sweep completo aggiorna ultimo_sha come il modo diff (ha appena verificato
    tutto) e in piu' segna ultimo_completo, che i rapporti leggono per ricordare da
    quanto non si lancia una verifica integrale."""
    p = Path(percorso)
    p.parent.mkdir(parents=True, exist_ok=True)
    stato = carica_stato(percorso)
    stato["ultimo_sha"] = sha
    stato["modo"] = modo
    stato["data"] = data
    if modo == "completo":
        stato["ultimo_completo"] = data
    else:
        stato.setdefault("ultimo_completo", None)
    p.write_text(json.dumps(stato, ensure_ascii=False, indent=1) + "\n",
                 encoding="utf-8")


# L'albero vuoto di git: diffare da qui equivale a "tutto il codice attuale".
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--da", help="sha di partenza; default: ultimo_sha dello stato")
    ap.add_argument("--a", default="HEAD")
    ap.add_argument("--completo", action="store_true",
                    help="ignora l'intervallo: tutti i simboli del codice attuale")
    ap.add_argument("--stato", default=STATO_DEFAULT)
    ap.add_argument("--memoria", default=RADICE_MEMORIA)
    args = ap.parse_args()

    stato = carica_stato(args.stato)
    if args.completo:
        simboli = simboli_mossi(_EMPTY_TREE + ".." + args.a)
        intervallo = "completo"
    else:
        da = args.da or stato.get("ultimo_sha")
        if not da:
            ap.error("nessuno sha di partenza: passa --da la prima volta")
        intervallo = f"{da}..{args.a}"
        simboli = simboli_mossi(intervallo)

    radici = RADICI_DOC + [args.memoria]
    citazioni = documenti_che_nominano(simboli, radici)
    citazioni, generici = riduci_generici(citazioni)
    print(json.dumps({
        "intervallo": intervallo,
        "simboli": [asdict(s) for s in simboli],
        "citazioni": [asdict(c) for c in citazioni],
        "generici": generici,
        "radici": radici,
        "stato": stato,
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
