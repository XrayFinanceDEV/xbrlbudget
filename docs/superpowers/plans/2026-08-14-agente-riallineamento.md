# Agente di riallineamento — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** uno skill `/riallinea` che il proprietario lancia **quando vuole**, che trova le affermazioni di documentazione smentite dal codice, corregge solo il dimostrabile e segnala il resto.

**Architecture:** due strati con un confine netto. Uno **script deterministico e testato** (`scripts/riallinea.py`, sola libreria standard) fa il lavoro meccanico — estrarre i simboli mossi da un intervallo di commit, trovare chi li nomina, tenere lo stato fra un'esecuzione e l'altra — ed espone il risultato come JSON. Uno **skill** (`.claude/skills/riallinea/SKILL.md`) fa il lavoro di giudizio: legge quel JSON, verifica ogni affermazione contro il codice, decide fra correzione e segnalazione, scrive il rapporto e committa. Il confine è deliberato: ciò che si può provare vive in codice con dei test; ciò che richiede interpretazione vive in istruzioni per un agente.

**Tech Stack:** Python 3 di sistema, **solo libreria standard** (`subprocess`, `re`, `json`, `pathlib`, `argparse`) — lo script deve girare senza attivare `backend/venv`. `pytest` per i test. Markdown per lo skill.

**Spec:** `docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md` — leggerla prima di iniziare.

## Global Constraints

- **Solo libreria standard** in `scripts/riallinea.py`. Nessun import da `backend/`, `importers/`, `database/`: lo script deve girare con `python3 scripts/riallinea.py` da solo.
- **Lo script non modifica MAI un file di documentazione.** Osserva e riferisce. Le uniche scritture che gli competono sono `STATO.json` e il proprio output JSON. Chi corregge è lo skill, e solo dentro la lista chiusa della spec §2.
- **La memoria non si scrive mai** (`~/.claude/projects/-home-peter-DEV-budget/memory/`): si legge e si verificano i riferimenti. Nessuna eccezione.
- **In dubbio si include** (estrazione simboli) e **in dubbio si segnala** (verdetto). Un falso positivo costa una verifica; un falso negativo costa un disallineamento non visto, e una correzione sbagliata costa un'affermazione falsa firmata da un commit che dice di aver sistemato le cose.
- Test dalla radice del progetto: `python3 -m pytest tests/test_riallinea.py -v`. Nessun test fa rete o chiama un LLM.
- I file nuovi sono **LF**.
- Messaggi di commit in italiano, stile del repo.

---

## Task 1: `simboli_mossi` — cosa il codice ha mosso

**Files:**
- Create: `scripts/riallinea.py`
- Test: `tests/test_riallinea.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Simbolo: nome: str; genere: str; file: str; stato: str`
    dove `genere ∈ {"funzione","classe","costante","colonna","rotta"}` e
    `stato ∈ {"aggiunto","rimosso"}` (un rename appare come rimosso+aggiunto: è lo skill a
    riconoscerlo, non lo script).
  - `simboli_mossi(rev_range: str, cwd: str = ".") -> list[Simbolo]`

- [ ] **Step 1: Scrivere i test che falliscono**

Crea `tests/test_riallinea.py`:

```python
"""Test dell'estrattore di simboli mossi (scripts/riallinea.py).

Spec: docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md §1 fase A
Run:  python3 -m pytest tests/test_riallinea.py -v
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.riallinea import Simbolo, simboli_da_diff  # noqa: E402


def _nomi(simboli, stato=None):
    return sorted(s.nome for s in simboli if stato is None or s.stato == stato)


def test_riconosce_una_funzione_aggiunta():
    diff = (
        "diff --git a/importers/foo.py b/importers/foo.py\n"
        "--- a/importers/foo.py\n"
        "+++ b/importers/foo.py\n"
        "@@ -0,0 +1 @@\n"
        "+def calcola_totale(bs):\n"
    )
    out = simboli_da_diff(diff)
    assert _nomi(out, "aggiunto") == ["calcola_totale"]
    assert out[0].genere == "funzione"
    assert out[0].file == "importers/foo.py"


def test_riconosce_una_funzione_rimossa():
    diff = (
        "diff --git a/importers/foo.py b/importers/foo.py\n"
        "--- a/importers/foo.py\n"
        "+++ b/importers/foo.py\n"
        "@@ -1 +0,0 @@\n"
        "-def vecchio_nome(bs):\n"
    )
    assert _nomi(simboli_da_diff(diff), "rimosso") == ["vecchio_nome"]


def test_un_rename_appare_come_rimosso_piu_aggiunto():
    # Lo script NON riconosce i rename: e' lo skill, con `git log -M`, a capire se
    # una coppia rimosso/aggiunto e' un rename o due cose diverse.
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n"
        "-def vecchio(x):\n"
        "+def nuovo(x):\n"
    )
    out = simboli_da_diff(diff)
    assert _nomi(out, "rimosso") == ["vecchio"]
    assert _nomi(out, "aggiunto") == ["nuovo"]


def test_riconosce_classi_costanti_e_colonne():
    diff = (
        "diff --git a/database/models.py b/database/models.py\n"
        "--- a/database/models.py\n+++ b/database/models.py\n@@ -0,0 +4 @@\n"
        "+class ForecastYear(Base):\n"
        "+    MAX_RIGHE = 20\n"
        "+    rettifiche_log = Column(JSON, nullable=True)\n"
        "+    _privata = 1\n"
    )
    out = simboli_da_diff(diff)
    per_genere = {s.nome: s.genere for s in out}
    assert per_genere["ForecastYear"] == "classe"
    assert per_genere["MAX_RIGHE"] == "costante"
    assert per_genere["rettifiche_log"] == "colonna"
    # una minuscola non-Column non e' una costante: sarebbe rumore
    assert "_privata" not in per_genere


def test_riconosce_il_typescript():
    diff = (
        "diff --git a/frontend/lib/api.ts b/frontend/lib/api.ts\n"
        "--- a/frontend/lib/api.ts\n+++ b/frontend/lib/api.ts\n@@ -0,0 +2 @@\n"
        "+export const patchCeOverrides = async (id: number) => {\n"
        "+export function labelOf(code: string) {\n"
    )
    assert _nomi(simboli_da_diff(diff), "aggiunto") == ["labelOf", "patchCeOverrides"]


def test_ignora_i_file_non_di_codice():
    diff = (
        "diff --git a/CLAUDE.md b/CLAUDE.md\n--- a/CLAUDE.md\n+++ b/CLAUDE.md\n@@ -0,0 +1 @@\n"
        "+def questa_e_prosa(x):\n"
    )
    assert simboli_da_diff(diff) == []


def test_non_duplica_lo_stesso_simbolo():
    diff = (
        "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -0,0 +2 @@\n"
        "+def stessa(x):\n"
        "+def stessa(y):\n"
    )
    assert len(simboli_da_diff(diff)) == 1
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python3 -m pytest tests/test_riallinea.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.riallinea'`

- [ ] **Step 3: Implementare**

Crea `scripts/riallinea.py` (e `scripts/__init__.py` se non esiste, vuoto):

```python
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
```

Nota sul `--- a/`: il file si legge dalla riga `+++ b/`, perché su un file cancellato `+++` vale `/dev/null` e il simbolo va comunque attribuito — verificalo e, se serve, prendi il nome da `diff --git` invece.

- [ ] **Step 4: Eseguire i test**

Run: `python3 -m pytest tests/test_riallinea.py -v`
Expected: 7 PASS. Se `test_riconosce_una_funzione_rimossa` fallisce, è il caso del `+++ /dev/null` descritto sopra: correggi l'attribuzione del file, non il test.

- [ ] **Step 5: Commit**

```bash
git diff --stat
git add scripts/riallinea.py scripts/__init__.py tests/test_riallinea.py
git commit -m "feat(riallinea): estrarre i simboli che il codice ha mosso"
```

---

## Task 2: `documenti_che_nominano` — chi ne parla

**Files:**
- Modify: `scripts/riallinea.py`
- Test: `tests/test_riallinea.py` (append)

**Interfaces:**
- Consumes: `Simbolo` (Task 1).
- Produces:
  - `@dataclass(frozen=True) Citazione: simbolo: str; file: str; riga: int; testo: str`
  - `documenti_che_nominano(simboli, radici: list[str]) -> list[Citazione]`
    — `radici` sono cartelle da scandire; ogni `.md` sotto di esse è candidato.

- [ ] **Step 1: Scrivere i test che falliscono**

Accoda a `tests/test_riallinea.py`:

```python
from scripts.riallinea import Citazione, documenti_che_nominano  # noqa: E402


def _scrivi(tmp_path, nome, testo):
    p = tmp_path / nome
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(testo, encoding="utf-8")
    return p


def test_trova_chi_nomina_un_simbolo(tmp_path):
    _scrivi(tmp_path, "docs/a.md", "Il netting usa `net_contra_accounts` due volte.\n")
    _scrivi(tmp_path, "docs/b.md", "Niente di rilevante qui.\n")
    sim = [Simbolo("net_contra_accounts", "funzione", "x.py", "rimosso")]
    cit = documenti_che_nominano(sim, [str(tmp_path)])
    assert [c.file for c in cit] == [str(tmp_path / "docs/a.md")]
    assert cit[0].riga == 1
    assert cit[0].simbolo == "net_contra_accounts"


def test_ignora_una_sottostringa_dentro_un_nome_piu_lungo(tmp_path):
    # `resolve` non deve pescare `_resolve_ce_field`: sarebbe rumore su ogni giro.
    _scrivi(tmp_path, "docs/a.md", "Usa `_resolve_ce_field` e non altro.\n")
    sim = [Simbolo("resolve", "funzione", "x.py", "rimosso")]
    assert documenti_che_nominano(sim, [str(tmp_path)]) == []


def test_legge_solo_i_markdown(tmp_path):
    _scrivi(tmp_path, "docs/a.py", "net_contra_accounts\n")
    sim = [Simbolo("net_contra_accounts", "funzione", "x.py", "rimosso")]
    assert documenti_che_nominano(sim, [str(tmp_path)]) == []


def test_piu_citazioni_dello_stesso_simbolo(tmp_path):
    _scrivi(tmp_path, "docs/a.md", "`foo_bar` qui\ne ancora `foo_bar` qui\n")
    sim = [Simbolo("foo_bar", "funzione", "x.py", "rimosso")]
    cit = documenti_che_nominano(sim, [str(tmp_path)])
    assert [c.riga for c in cit] == [1, 2]


def test_una_radice_inesistente_non_esplode(tmp_path):
    sim = [Simbolo("foo_bar", "funzione", "x.py", "rimosso")]
    assert documenti_che_nominano(sim, [str(tmp_path / "non-esiste")]) == []
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python3 -m pytest tests/test_riallinea.py -v`
Expected: FAIL — `ImportError: cannot import name 'documenti_che_nominano'`

- [ ] **Step 3: Implementare**

Accoda a `scripts/riallinea.py`:

```python
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
        for md in sorted(base.rglob("*.md")):
            try:
                righe = md.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for n, testo in enumerate(righe, start=1):
                for nome, regola in per_nome.items():
                    if regola.search(testo):
                        out.append(Citazione(nome, str(md), n, testo.strip()[:200]))
    return out
```

Attenzione: `\b` non separa su `_`, quindi `resolve` **non** deve pescare `_resolve_ce_field` — verifica che il test lo dimostri e, se `\b` non basta, usa un confine esplicito che escluda `[A-Za-z0-9_]` ai due lati.

- [ ] **Step 4: Eseguire i test**

Run: `python3 -m pytest tests/test_riallinea.py -v`
Expected: 12 PASS.

- [ ] **Step 5: Commit**

```bash
git diff --stat
git add scripts/riallinea.py tests/test_riallinea.py
git commit -m "feat(riallinea): trovare chi nomina un simbolo mosso"
```

---

## Task 3: stato, CLI e memoria

**Files:**
- Modify: `scripts/riallinea.py`
- Create: `docs/superpowers/allineamento/STATO.json`
- Test: `tests/test_riallinea.py` (append)

**Interfaces:**
- Produces:
  - `carica_stato(percorso) -> dict` / `salva_stato(percorso, sha, modo, data)`
  - `SOGLIA_GENERICO = 40` e `riduci_generici(citazioni) -> tuple[list[Citazione], list[dict]]`
  - CLI: `python3 scripts/riallinea.py --da <sha> [--a HEAD] [--completo]` → stampa su stdout un JSON `{"intervallo","simboli":[…],"citazioni":[…],"generici":[…],"radici":[…],"stato":{…}}`

**Nota aggiunta dopo la revisione del Task 2.** Misurato: nove nomi generici plausibili
(`resolve`, `add`, `main`, `probe`, `data`, `value`, `path`, `get`, `id`) producono **1147
citazioni** in un colpo solo. Un solo simbolo comune fra i ~40 di un diff reale seppellirebbe
le segnalazioni vere. La fase B fa bene a includerli — la regola è «in dubbio si include» — ma
il JSON che arriva allo skill va **ridotto**, non troncato in silenzio: un simbolo con più
citazioni della soglia esce dall'elenco `citazioni` ed entra in `generici` come
`{"nome": …, "citazioni": N, "file": [primi 5 file]}`. Lo skill lo riporterà come «troppo
comune per essere verificato per nome», che è un'informazione, mentre 1147 righe non lo sono.

- [ ] **Step 1: Scrivere i test che falliscono**

Accoda a `tests/test_riallinea.py`:

```python
import json as _json

from scripts.riallinea import carica_stato, salva_stato  # noqa: E402


def test_stato_assente_da_un_dizionario_vuoto(tmp_path):
    assert carica_stato(str(tmp_path / "STATO.json")) == {}


def test_salva_e_rilegge_lo_stato(tmp_path):
    p = str(tmp_path / "STATO.json")
    salva_stato(p, sha="abc1234", modo="diff", data="2026-08-21")
    letto = carica_stato(p)
    assert letto["ultimo_sha"] == "abc1234"
    assert letto["modo"] == "diff"
    assert letto["ultimo_completo"] is None


def test_lo_sweep_completo_aggiorna_ultimo_completo_e_lo_sha(tmp_path):
    # Uno sweep ha appena verificato tutto: il punto di ripartenza e' lo stesso del
    # modo diff, e in piu' resta traccia di QUANDO si e' fatto l'ultimo integrale.
    p = str(tmp_path / "STATO.json")
    salva_stato(p, sha="abc1234", modo="diff", data="2026-08-21")
    salva_stato(p, sha="def5678", modo="completo", data="2026-08-28")
    letto = carica_stato(p)
    assert letto["ultimo_sha"] == "def5678"
    assert letto["ultimo_completo"] == "2026-08-28"


def test_un_diff_successivo_non_cancella_ultimo_completo(tmp_path):
    p = str(tmp_path / "STATO.json")
    salva_stato(p, sha="def5678", modo="completo", data="2026-08-28")
    salva_stato(p, sha="aaa1111", modo="diff", data="2026-09-04")
    letto = carica_stato(p)
    assert letto["ultimo_completo"] == "2026-08-28"
    assert letto["ultimo_sha"] == "aaa1111"
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `python3 -m pytest tests/test_riallinea.py -v`
Expected: FAIL — `ImportError: cannot import name 'carica_stato'`

- [ ] **Step 3: Implementare stato e CLI**

Accoda a `scripts/riallinea.py`:

```python
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
    print(json.dumps({
        "intervallo": intervallo,
        "radici": radici,
        "stato": stato,
        "simboli": [asdict(s) for s in simboli],
        "citazioni": [asdict(c) for c in citazioni],
    }, ensure_ascii=False, indent=1))


# L'albero vuoto di git: diffare da qui equivale a "tutto il codice attuale".
_EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


if __name__ == "__main__":
    main()
```

`RADICI_DOC` contiene `"CLAUDE.md"`, che è un file e non una cartella: verifica che `documenti_che_nominano` lo gestisca (un `Path.rglob("*.md")` su un file non rende nulla). Se non lo gestisce, adattalo — e aggiungi il test.

- [ ] **Step 4: Creare lo stato iniziale**

```bash
mkdir -p docs/superpowers/allineamento
```
Crea `docs/superpowers/allineamento/STATO.json` con lo sha di `HEAD` al momento dell'implementazione, `"modo": "iniziale"`, `"ultimo_completo": null`, e la data.

- [ ] **Step 5: Eseguire i test e una prova reale**

```bash
python3 -m pytest tests/test_riallinea.py -v          # 16 PASS
python3 scripts/riallinea.py --da HEAD~5 | head -40   # deve stampare JSON valido
python3 scripts/riallinea.py --da HEAD~5 | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d['simboli']),'simboli,',len(d['citazioni']),'citazioni')"
```

- [ ] **Step 6: Commit**

```bash
git diff --stat
git add scripts/riallinea.py tests/test_riallinea.py docs/superpowers/allineamento/STATO.json
git commit -m "feat(riallinea): stato fra le esecuzioni e interfaccia a riga di comando"
```

---

## Task 4: lo skill `/riallinea`

**Files:**
- Create: `.claude/skills/riallinea/SKILL.md`

**Interfaces:**
- Consumes: il JSON di `scripts/riallinea.py`.

- [ ] **Step 1: Scrivere lo skill**

Crea `.claude/skills/riallinea/SKILL.md` con questo frontmatter e questa struttura:

```markdown
---
name: riallinea
description: Use when the user wants to check that documentation and memory still match the code — after a significant change, or as a periodic sweep. Finds claims the code contradicts, fixes only what is mechanically provable, reports the rest.
---

# Riallineamento documentazione ↔ codice

Trova le affermazioni di documentazione che il codice smentisce. **Corregge solo il
dimostrabile; segnala tutto il resto.** Non modifica mai un file di memoria.

Spec: `docs/superpowers/specs/2026-08-14-agente-riallineamento-design.md`

## Perché è severo

Una correzione sbagliata è peggio del disallineamento: finisce in `CLAUDE.md`, che è
caricato a ogni sessione, firmata da un commit che dice di aver sistemato le cose, e
nessuno la rilegge. Nel dubbio si segnala.

## Procedura

1. **Raccogli.** `python3 scripts/riallinea.py` (aggiungi `--completo` se l'utente
   chiede lo sweep integrale; `--da <sha>` alla prima esecuzione).
2. **Verifica una citazione per volta.** Per ciascuna, apri il codice e stabilisci:
   - `OK` — il codice conferma. Nessuna azione.
   - `MORTO` — il simbolo nominato non esiste più.
   - `SMENTITO` — esiste, ma il codice fa altro.
3. **Correggi solo dentro la lista chiusa** (sotto). Tutto il resto va in «Da decidere».
4. **Verifica anche la memoria**, ma non modificarla: solo riferimenti morti a rapporto.
5. **Scrivi il rapporto**, sempre, anche a esito nullo.
6. **Committa in due volte**: prima le correzioni, poi il rapporto.
7. **Aggiorna** `STATO.json`.

## La lista chiusa — ciò che puoi correggere da solo

1. Link relativo a un file inesistente → correggi **se** esiste un solo file con quel
   nome nel repo; altrimenti segnala.
2. Percorso di file nominato che non esiste → stessa regola.
3. Identificatore fra backtick sparito, **quando `git log -M --follow` mostra un rename
   inequivocabile** → sostituisci col nome nuovo. Rename ambiguo o simbolo rimosso →
   segnala.
4. Numero che contraddice una **costante nominata** nel codice, quando la frase cita
   sia la costante sia il valore → allinea il valore.

Non correggere mai: una descrizione di comportamento, un ordine di operazioni, una
motivazione, un numero non ancorato a una costante nominata, un esempio di codice.

## Il rapporto

`docs/superpowers/allineamento/AAAA-MM-GG.md`, con in testa il modo, l'intervallo, i
conteggi, e **da quanto non si lancia uno sweep completo** (`ultimo_completo` dello
stato). Sezioni: «Corretto automaticamente» (con la regola che l'ha autorizzata),
«Da decidere» (citazione, riga di codice, proposta NON applicata), «Memoria —
riferimenti morti», «Non verificabile».

## Limite da dichiarare in ogni rapporto

Un controllo guidato dal diff trova la **deriva**, non l'errore di nascita: una frase
sbagliata fin dall'inizio non è mai stata «mossa» e nessun diff la segnala. Solo
`--completo` la prende.
```

- [ ] **Step 2: Verificare che lo skill sia visibile**

Lo skill di progetto è caricato all'avvio della sessione. Verifica almeno che il file esista, che il frontmatter sia YAML valido e che `name` corrisponda alla cartella:

```bash
python3 -c "
import pathlib
t = pathlib.Path('.claude/skills/riallinea/SKILL.md').read_text(encoding='utf-8')
assert t.startswith('---'), 'manca il frontmatter'
fm = t.split('---')[1]
assert 'name: riallinea' in fm and 'description:' in fm
print('frontmatter ok')
"
```

- [ ] **Step 3: Commit**

```bash
git diff --stat
git add .claude/skills/riallinea/SKILL.md
git commit -m "feat(riallinea): lo skill che decide cosa correggere e cosa segnalare"
```

---

## Task 5: prima esecuzione vera

**Files:**
- Create: `docs/superpowers/allineamento/<data>.md` (il primo rapporto)
- Modify: `docs/superpowers/allineamento/STATO.json`, e i documenti che risultassero correggibili

- [ ] **Step 1: Eseguire su un intervallo reale e non banale**

Usa l'intervallo del lavoro sul riscatto vision, che ha mosso molti simboli:

```bash
python3 scripts/riallinea.py --da 520fbe8 --a HEAD > /tmp/riallinea.json
python3 -c "import json;d=json.load(open('/tmp/riallinea.json'));print(len(d['simboli']),'simboli,',len(d['citazioni']),'citazioni')"
```

Se i simboli sono zero o migliaia, il riconoscimento è tarato male: correggi le regole del Task 1 e rifai i test, non aggirare il problema.

- [ ] **Step 2: Seguire la procedura dello skill a mano, una volta**

È la prova che lo skill funziona: verifica ogni citazione, applica solo la lista chiusa, scrivi il rapporto. Su un intervallo così ampio è probabile che le citazioni siano molte: **verificale tutte** e, se sono più di quaranta, dillo nel rapporto invece di campionare in silenzio.

- [ ] **Step 3: Giudicare il risultato, onestamente**

Nel rapporto, in coda, una sezione «Taratura» che risponda a: quanti falsi positivi ha prodotto l'estrazione dei simboli? Le citazioni trovate erano pertinenti o rumore? Il filtro per nome ha perso qualcosa che sapevi essere disallineato? Se lo strumento non funziona, **dillo** — è la prima esecuzione, serve a questo.

- [ ] **Step 4: Commit**

```bash
git diff --stat
git add docs/superpowers/allineamento/
git commit -m "docs(allineamento): prima esecuzione e taratura"
```

---

## Note di esecuzione

- **Lo script non tocca la documentazione.** Se ti trovi a scrivere codice che modifica un `.md` dentro `scripts/riallinea.py`, hai attraversato il confine: quella è competenza dello skill.
- **La memoria non si scrive mai.** Nessuna eccezione, nemmeno per un riferimento palesemente morto.
- **La schedulazione settimanale non fa parte di questo piano.** Prima lo skill deve funzionare lanciato a mano; la cadenza si aggiunge dopo, ed è solo un innesco.
