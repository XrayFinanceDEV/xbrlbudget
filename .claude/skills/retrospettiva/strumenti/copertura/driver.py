#!/usr/bin/env python3
"""Copertura dei lettori deterministici sul corpus, a un commit dato, senza rete (retro del 18/10, §2.4).

Chiama `importers.import_snello.deterministico.tentativo()` su ogni PDF distinto (sha256) del corpus, in
un processo per file con le chiavi tolte e `socket.connect` bloccato: nessun documento esce dal PC.
Il commit da misurare si prepara come worktree detached FUORI dal repo principale:

    git worktree add --detach <scratch>/wt/<sha> <sha>

Uso:
    RETRO_ROOT=<worktree> RETRO_TEST=<corpus> [RETRO_PY=<python>] python3 driver.py <uscita.jsonl> [--escludi a,b]

RETRO_PY di default è backend/venv/bin/python del repo principale (il worktree non ha un venv).
Escluse per default le cartelle `july_budget` e `_analysis` (copie e materiale di analisi, come fa
tests/corpus/api_pdf_import_audit.py) e quelle che iniziano per `_analisi`.
Conteggio: righe con "adottato": true. Attenzione al denominatore: il corpus cresce fra le misure.
"""
import hashlib, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(os.environ["RETRO_ROOT"])
TEST = Path(os.environ["RETRO_TEST"])
HERE = Path(__file__).resolve().parent
PRINCIPALE = Path(subprocess.run(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"],
                                 capture_output=True, text=True).stdout.strip())
PY = os.environ.get("RETRO_PY", str(PRINCIPALE / "backend" / "venv" / "bin" / "python"))
OUT = Path(sys.argv[1])
escludi = {"july_budget", "_analysis"}
if "--escludi" in sys.argv:
    escludi = set(sys.argv[sys.argv.index("--escludi") + 1].split(","))

pdfs = sorted(p for p in TEST.rglob("*") if p.suffix.lower() == ".pdf"
              and not (set(p.relative_to(TEST).parts) & escludi)
              and not any(x.startswith("_analisi") for x in p.relative_to(TEST).parts))
uniq, dup = {}, {}
for p in pdfs:
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    (dup.setdefault(h, []).append(str(p.relative_to(TEST))) if h in uniq else uniq.__setitem__(h, p))
print(f"PDF totali {len(pdfs)}, unici {len(uniq)}", flush=True)


def run(item):
    h, p = item
    rel = str(p.relative_to(TEST))
    env = dict(os.environ, RETRO_ROOT=str(ROOT))
    try:
        cp = subprocess.run([PY, "-I", str(HERE / "worker.py"), str(p)], cwd=str(ROOT), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=240, env=env)
        line = next((l for l in cp.stdout.splitlines() if l.startswith("@@JSON@@")), None)
        r = json.loads(line[8:]) if line else {"esito": "crash", "errore": cp.stderr[-400:]}
    except subprocess.TimeoutExpired:
        r = {"esito": "timeout_240s"}
    r.update(sha=h[:12], duplicati=dup.get(h, []), file=rel)
    return r


OUT.parent.mkdir(parents=True, exist_ok=True)
with ThreadPoolExecutor(6) as ex, OUT.open("w", encoding="utf-8") as f:
    for i, r in enumerate(ex.map(run, uniq.items()), 1):
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        if i % 40 == 0:
            print(i, flush=True)
rs = [json.loads(l) for l in OUT.open(encoding="utf-8")]
print(f"adottati {sum(1 for r in rs if r.get('adottato'))}/{len(rs)}, "
      f"rete {sum(r.get('rete', 0) for r in rs)}, crash {sum(1 for r in rs if r.get('esito') == 'crash')}")
