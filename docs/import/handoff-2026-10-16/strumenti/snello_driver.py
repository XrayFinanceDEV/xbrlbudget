import hashlib, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(r"C:\DEV\xbrlbudget-main\xbrlbudget")
PY = str(ROOT / "backend/.venv/Scripts/python.exe")
HERE = Path(__file__).parent
WORKER = str(HERE / "snello_worker.py")
OUT = HERE / (sys.argv[1] if len(sys.argv)>1 else "snello_risultati.jsonl")

pdfs = sorted(p for p in (ROOT / "Test").rglob("*") if p.suffix.lower() == ".pdf")
uniq, dup = {}, {}
for p in pdfs:
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    if h in uniq:
        dup.setdefault(h, []).append(str(p.relative_to(ROOT)))
    else:
        uniq[h] = p
print(f"PDF totali {len(pdfs)}, unici {len(uniq)}", flush=True)


def run(item):
    h, p = item
    rel = str(p.relative_to(ROOT))
    try:
        cp = subprocess.run([PY, "-I", WORKER, rel], cwd=str(ROOT), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=240)
        line = next((l for l in cp.stdout.splitlines() if l.startswith("@@JSON@@")), None)
        r = json.loads(line[8:]) if line else {"file": rel, "esito": "crash",
                                               "errore": cp.stderr[-400:]}
    except subprocess.TimeoutExpired:
        r = {"file": rel, "esito": "timeout_240s"}
    r["sha"] = h[:12]
    r["duplicati"] = dup.get(h, [])
    return r


with ThreadPoolExecutor(6) as ex, OUT.open("w", encoding="utf-8") as f:
    for i, r in enumerate(ex.map(run, uniq.items()), 1):
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        if i % 20 == 0:
            print(i, flush=True)
print("fatto", flush=True)
