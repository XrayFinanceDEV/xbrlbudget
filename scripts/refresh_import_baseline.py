"""Genera / aggiorna `tests/fixtures/import_baseline.json`.

La baseline e' indicizzata per **sha256 del documento** (gli stessi PDF ricorrono
con nomi diversi in piu' cartelle del corpus) e distingue due livelli:

  verified=False  cio' che il software produce oggi -> intercetta i CAMBI
  verified=True   il numero letto SULLA FONTE da un umano -> asserzione di correttezza

Regole di sicurezza:
  * le entry `verified=True` NON vengono mai sovrascritte da questo script
    (si aggiornano a mano, insieme a `verified_note`);
  * i fallimenti dovuti all'AMBIENTE (crediti esauriti, chiave assente, MinerU
    spento, rete) NON vengono scritti affatto: congelarli significherebbe
    dichiarare "atteso" un errore che non dipende dal software.

Uso:
    python scripts/refresh_import_baseline.py Test/successSecondo Test/june_sample/success
    python scripts/refresh_import_baseline.py --method ocr Test/errori
    python scripts/refresh_import_baseline.py --verify <sha256> "TOTALE A PAREGGIO pag.4"
"""
import argparse
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BASELINE = os.path.join(ROOT, "tests", "fixtures", "import_baseline.json")

# Un errore che corrisponde a uno di questi non descrive il software: descrive
# la macchina su cui gira. Non entra in baseline.
_ENVIRONMENTAL = re.compile(
    r"credit balance|rate.?limit|429|insufficient_quota"
    r"|ANTHROPIC_API_KEY|api[_ ]key"
    r"|MINERU_UNAVAILABLE|MinerU unreachable|ConnectError|ConnectionError"
    r"|Timeout|timed out|Temporary failure in name resolution",
    re.I,
)


def is_environmental(error: str) -> bool:
    """True se l'errore dipende dall'ambiente e non dal comportamento del software."""
    return bool(error) and bool(_ENVIRONMENTAL.search(error))


def _config_tag() -> str:
    """Con o senza chiave LLM il risultato di route C puo' DIFFERIRE: con la chiave
    gira prima la CoGe-LLM e la selezione per completezza puo' scegliere un altro
    candidato. Due configurazioni = due baseline diverse; l'entry dichiara la propria."""
    return "llm" if os.environ.get("ANTHROPIC_API_KEY") else "no-llm"


def _load() -> dict:
    if os.path.exists(BASELINE):
        with open(BASELINE, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save(base: dict) -> None:
    os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
    tmp = BASELINE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(base, fh, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, BASELINE)


def refresh(paths, method="standard") -> None:
    from tests._import_probe import probe, sha256_of

    base = _load()
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += [f for f in glob.glob(os.path.join(p, "**", "*"), recursive=True)
                      if f.lower().endswith(".pdf")]
        elif p.lower().endswith(".pdf"):
            files.append(p)

    added = updated = skipped_env = kept_verified = 0
    for path in sorted(files):
        h = sha256_of(path)
        entry = base.get(h)
        if entry and entry.get("verified"):
            kept_verified += 1
            print(f"  verified, non tocco : {os.path.basename(path)[:60]}")
            continue
        rec = probe(path, method)
        if is_environmental(rec.get("error") or ""):
            skipped_env += 1
            print(f"  AMBIENTE, scartato  : {os.path.basename(path)[:60]}")
            continue
        rec["method"] = method
        base[h] = {"file": os.path.basename(path), "verified": False,
                   "verified_note": "", "config": _config_tag(), "expected": rec}
        if entry:
            updated += 1
        else:
            added += 1
        state = "OK  " if rec["ok"] else "FAIL"
        print(f"  {state}                : {os.path.basename(path)[:60]}")

    _save(base)
    print(f"\nbaseline: {len(base)} entry totali "
          f"(+{added} nuove, {updated} aggiornate, {kept_verified} verified intatte, "
          f"{skipped_env} scartate per errore d'ambiente)")


def promote(sha: str, note: str) -> None:
    base = _load()
    if sha not in base:
        raise SystemExit(f"sha non in baseline: {sha}")
    if not note.strip():
        raise SystemExit("verified richiede una nota: dove hai letto il numero sulla fonte")
    base[sha]["verified"] = True
    base[sha]["verified_note"] = note
    _save(base)
    print(f"promosso a verified: {base[sha]['file']} — {note}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--method", default="standard", choices=["standard", "ocr"])
    ap.add_argument("--verify", nargs=2, metavar=("SHA256", "NOTA"),
                    help="promuove una entry a verified con la nota di provenienza")
    args = ap.parse_args()
    if args.verify:
        promote(*args.verify)
    elif args.paths:
        refresh(args.paths, args.method)
    else:
        ap.error("indicare almeno una cartella/PDF, oppure --verify")


if __name__ == "__main__":
    main()
