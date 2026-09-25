"""Verdetto del banco di triage AMBIENTA: stesse suite su 62bfed1 e su HEAD, esito per rilievo nel foglio.

Uso: python tools/triage_rilievi.py   (dal worktree del banco; scrive inbox/Verifica_piano_Ambienta_triage.xlsx)
"""
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

VECCHIO = "62bfed1"
PY = "/home/peter/DEV/budget/backend/venv/bin/python"
NODE_MODULES = "/home/peter/DEV/budget/frontend/node_modules"
BANCO = ["tests/rilievi_kit.py", "tests/test_rilievi_ambienta.py", "tests/fixtures/ambienta_2026.json",
         "frontend/lib/rilievi-ambienta.test.ts"]
_ID = re.compile(r"(?:^|test_|> )([A-E]\d{2})[_ ]")
_PESO = {"fail": 3, "pass": 2, "skip": 1}


def verdetto(vecchio, nuovo) -> str:
    if nuovo is None:
        return "Senza test"
    if vecchio == "skip" or vecchio is None:
        base = "Confermato" if nuovo == "fail" else "Non riprodotto"
        return f"{base} (n/a su {VECCHIO})"
    return {("fail", "fail"): "Confermato", ("fail", "pass"): "Risolto (2026-09-24)",
            ("pass", "pass"): "Non riprodotto", ("pass", "fail"): "Regressione"}.get((vecchio, nuovo), f"{vecchio}/{nuovo}")


def esiti_junit(path) -> dict:
    out = {}
    for tc in ET.parse(path).iter("testcase"):
        m = _ID.search(tc.get("name", ""))
        if not m:
            continue
        esito = ("fail" if tc.find("failure") is not None or tc.find("error") is not None
                 else "skip" if tc.find("skipped") is not None else "pass")
        rid = m.group(1)
        if _PESO[esito] > _PESO.get(out.get(rid), 0):
            out[rid] = esito
    return out


def _suite(root: Path, tag: str, out: Path) -> dict:
    py_xml, js_xml = out / f"{tag}-pytest.xml", out / f"{tag}-vitest.xml"
    subprocess.run([PY, "-m", "pytest", "tests/test_rilievi_ambienta.py", "-q", "-p", "no:warnings",
                    f"--junitxml={py_xml}"], cwd=root)
    nm = root / "frontend" / "node_modules"
    if not nm.exists():
        nm.symlink_to(NODE_MODULES)
    subprocess.run(["npx", "vitest", "run", "lib/rilievi-ambienta.test.ts", "--reporter=junit",
                    f"--outputFile={js_xml}"], cwd=root / "frontend")
    esiti = {}
    for x in (py_xml, js_xml):
        if x.exists():
            for rid, e in esiti_junit(x).items():
                if _PESO[e] > _PESO.get(esiti.get(rid), 0):
                    esiti[rid] = e
    return esiti


def main() -> int:
    qui = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    out = qui / ".superpowers" / "triage"
    out.mkdir(parents=True, exist_ok=True)
    vecchio = out / f"wt-{VECCHIO}"
    if not vecchio.exists():
        subprocess.run(["git", "worktree", "add", "--detach", str(vecchio), VECCHIO], cwd=qui, check=True)
    for f in BANCO:
        (vecchio / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(qui / f, vecchio / f)
    e_old, e_new = _suite(vecchio, "vecchio", out), _suite(qui, "nuovo", out)

    import openpyxl
    src = qui / "inbox" / "Verifica_piano_Ambienta_problemi.xlsx"
    wb = openpyxl.load_workbook(src)
    ws = wb["Elenco problemi"]
    for r in range(5, ws.max_row + 1):
        rid = ws.cell(r, 1).value
        if not rid or ws.cell(r, 10).value != "Softwarista":
            continue
        v = verdetto(e_old.get(rid), e_new.get(rid))
        ws.cell(r, 11).value = v
        ws.cell(r, 12).value = f"banco: {VECCHIO}={e_old.get(rid, '-')}, HEAD={e_new.get(rid, '-')}"
        print(f"{rid:4} {v}")
    dst = qui / "inbox" / "Verifica_piano_Ambienta_triage.xlsx"
    wb.save(dst)
    print(f"scritto {dst}")
    subprocess.run(["git", "worktree", "remove", "--force", str(vecchio)], cwd=qui)
    return 0


if __name__ == "__main__":
    sys.exit(main())
