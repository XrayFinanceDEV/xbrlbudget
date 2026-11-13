#!/usr/bin/env python3
"""Churn, sopravvivenza, LIFO e contatori di rilavorazione per la retrospettiva.

Reimplementa `misure.py` della retro del 18/10 senza percorsi né date nel codice.

- Traversata APERTA: `git log --all --since=<da − margine>` filtrato per data autore dentro [da, a).
  La forma secca `--since=<da>` pota la discesa e perde commit (Appendice A della retro del 26/09).
- Due colonne di righe: con e senza spazi (`-w`). Un flip dei fine-riga (CRLF ↔ LF) conta migliaia di
  righe che non esistono (retro del 18/10, §2.1-bis): la colonna che conta è quella `-w`.
- «Vive» = righe ancora presenti in `git blame`, il massimo fra main e i ref che contengono commit
  della finestra non raggiungibili da main (calcolati da sé, o passati con --refs).

Uso:
    python3 misure.py --da 2026-10-19 --a 2026-11-14 [--repo .] [--margine 3] [--out <cartella>]
                      [--refs ref1,ref2] [--senza-blame]
Scrive <out>/churn.json e stampa una sintesi. Con --senza-blame salta la sopravvivenza (secondi
invece di minuti).
"""
import argparse
import collections
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

BIN_EXT = {".ttf", ".otf", ".woff", ".woff2", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
           ".pdf", ".db", ".sqlite", ".xlsx", ".xls", ".docx", ".doc", ".zip", ".gz", ".pyc",
           ".ico", ".mp4", ".pickle", ".pkl", ".bin", ".exe", ".so", ".dll"}
HEADER = re.compile(r"^([0-9a-f]{7,40}) \d+ \d+( \d+)?$")
AREE = [("importers/lettore/", "importers/lettore/"), ("importers/", "importers/ (altro)"),
        ("calculations/", "calculations/"), ("tests/corpus/", "tests/corpus/"), ("tests/", "tests/"),
        ("frontend/", "frontend/"), ("backend/app/renderers/", "backend/app/renderers/"),
        ("backend/", "backend/app/ (altro)"), ("docs/", "docs/"), ("scripts/", "scripts/"),
        ("database/", "database/"), ("pdf_service/", "pdf_service/"), (".claude/", ".claude/")]
PAROLE_RITORNO = ("fix round", "fix wave", "correzion", "revert", "riliev", "ripristin", "regression",
                  "secondo giro", "giro 2", "torna a", "di nuovo")


def area(p):
    if p == "CLAUDE.md":
        return "CLAUDE.md"
    for pre, name in AREE:
        if p.startswith(pre):
            return name
    return "altro"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--da", required=True, help="inizio finestra, incluso (YYYY-MM-DD)")
    ap.add_argument("--a", required=True, help="fine finestra, esclusa (YYYY-MM-DD)")
    ap.add_argument("--margine", type=int, default=3, help="giorni di traversata prima di --da")
    ap.add_argument("--refs", default=None, help="ref extra per la sopravvivenza (default: calcolati)")
    ap.add_argument("--out", default=".")
    ap.add_argument("--senza-blame", action="store_true")
    a = ap.parse_args()

    repo = subprocess.run(["git", "-C", a.repo, "rev-parse", "--show-toplevel"], capture_output=True,
                          text=True, check=True).stdout.strip()

    def git(*args):
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace").stdout

    da, fine = a.da, a.a
    dal = (datetime.date.fromisoformat(da) - datetime.timedelta(days=a.margine)).isoformat()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    def is_text(p):
        return Path(p).suffix.lower() not in BIN_EXT

    def traversa(extra):
        raw = git("log", "--all", "--no-merges", f"--since={dal}", *extra, "--numstat",
                  "--format=%x01%ad%x01%H%x01%s", "--date=iso-strict")
        commits, cur = {}, None
        for line in raw.splitlines():
            if line.startswith("\x01"):
                d, h, s = line[1:].split("\x01", 2)
                cur = h if da <= d[:10] < fine else None
                if cur:
                    commits.setdefault(cur, {"date": d, "subj": s, "files": {}})
                continue
            if cur is None or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != 3 or parts[0] == "-" or not is_text(parts[2]):
                continue
            ad, de, f = parts
            fl = commits[cur]["files"]
            pa, pd = fl.get(f, (0, 0))
            fl[f] = (pa + int(ad), pd + int(de))
        return commits

    commits = traversa([])
    commits_w = traversa(["-w"])
    sha_set = set(commits)
    sha_by_prefix = {h[:10]: h for h in sha_set}
    n_merge = sum(1 for l in git("log", "--all", "--merges", f"--since={dal}", "--format=%ad",
                                 "--date=iso-strict").splitlines() if da <= l[:10] < fine)

    # churn per area e per file (con e senza spazi)
    areas = collections.defaultdict(lambda: [0, 0, 0, 0, set()])
    filestats = collections.defaultdict(lambda: [0, 0, set()])
    for h, c in commits.items():
        cw = commits_w.get(h, {"files": {}})["files"]
        for f, (ad, de) in c["files"].items():
            ar = areas[area(f)]
            ar[0] += ad; ar[1] += de; ar[4].add(h)
            aw, dw = cw.get(f, (0, 0))
            ar[2] += aw; ar[3] += dw
            fs = filestats[f]
            fs[0] += aw; fs[1] += dw; fs[2].add(h)

    # commit con numstat > 5× il diff -w (flip dei fine-riga)
    flip = []
    for h, c in commits.items():
        tot = sum(x + y for x, y in c["files"].values())
        totw = sum(x + y for x, y in commits_w.get(h, {"files": {}})["files"].values())
        if tot >= 200 and tot > 5 * max(totw, 1):
            flip.append((h[:7], tot, totw, c["subj"][:70]))

    # LIFO morte ≤7g / ≤30g (sulle righe -w)
    perfile = collections.defaultdict(list)
    for h, c in commits_w.items():
        ts = datetime.datetime.fromisoformat(c["date"]).timestamp()
        for f, (ad, de) in c["files"].items():
            perfile[f].append((ts, ad, de))
    dead7 = dead30 = 0
    for f, evs in perfile.items():
        evs.sort()
        stack = []
        for ts, ad, de in evs:
            if ad:
                stack.append([ts, ad])
            n = de
            while n > 0 and stack:
                top = stack[-1]
                take = min(n, top[1])
                life = ts - top[0]
                if life <= 7 * 86400:
                    dead7 += take
                if life <= 30 * 86400:
                    dead30 += take
                top[1] -= take; n -= take
                if top[1] == 0:
                    stack.pop()
    add_w = sum(ad for c in commits_w.values() for ad, _ in c["files"].values())
    del_w = sum(de for c in commits_w.values() for _, de in c["files"].values())
    add = sum(ad for c in commits.values() for ad, _ in c["files"].values())
    dele = sum(de for c in commits.values() for _, de in c["files"].values())

    # coppie sullo stesso file entro 3 giorni (≥20 righe)
    coppie = 0
    for f, evs in perfile.items():
        big = sorted(ts for ts, ad, de in evs if ad + de >= 20)
        coppie += sum(1 for i in range(len(big) - 1) if big[i + 1] - big[i] <= 3 * 86400)

    # soggetti
    subj = [c["subj"] for c in commits.values()]
    n_fix = sum(1 for s in subj if s.lower().startswith("fix"))
    n_kw = sum(1 for s in subj if any(k in s.lower() for k in PAROLE_RITORNO))
    reverts = sorted(s for s in subj if s.lower().startswith("revert"))
    decisioni = sum(1 for h in sha_set if "decisione del proprietario" in
                    git("log", "-1", "--format=%B", h).lower())
    id_doc = collections.Counter()
    for s in subj:
        for m in re.findall(r"\b(?:budget_)?(\d{3,4})\b", s):
            if not m.startswith("20"):
                id_doc[m] += 1

    # in volo: commit della finestra non raggiungibili da main
    in_volo = [h for h in sha_set if subprocess.run(
        ["git", "-C", repo, "merge-base", "--is-ancestor", h, "main"]).returncode != 0]
    righe_in_volo = sum(sum(x for x, _ in commits_w[h]["files"].values()) for h in in_volo if h in commits_w)

    # sopravvivenza
    if a.refs:
        refs = ["main"] + [r for r in a.refs.split(",") if r]
    else:
        refs = ["main"]
        for r in git("for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes").split():
            if r in ("main", "origin/main", "origin/HEAD", "origin"):
                continue
            if any(subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", h, r]).returncode == 0
                   for h in in_volo):
                refs.append(r)
    vive = None
    big_dead = []
    survivors_commit = collections.Counter()
    if not a.senza_blame:
        trees = {r: set(git("ls-tree", "-r", "--name-only", r).splitlines()) for r in refs}
        files = sorted({f for c in commits.values() for f in c["files"]})
        vive = 0
        for i, f in enumerate(files):
            best = 0
            for r in refs:
                if f not in trees[r]:
                    continue
                n = 0
                curc = None
                for line in git("blame", "-w", "--line-porcelain", r, "--", f).splitlines():
                    if line.startswith("\t"):
                        if curc in sha_set:
                            n += 1
                            if r == "main":
                                survivors_commit[curc] += 1
                        continue
                    m = HEADER.match(line)
                    if m:
                        pfx = m.group(1)
                        curc = sha_by_prefix.get(pfx[:10])
                best = max(best, n)
            vive += best
            if (i + 1) % 50 == 0:
                print(f"blame {i + 1}/{len(files)}", file=sys.stderr)
        big_dead = [(h[:7], sum(x for x, _ in commits_w[h]["files"].values()), commits[h]["subj"][:70])
                    for h in sha_set if h in commits_w
                    and sum(x for x, _ in commits_w[h]["files"].values()) >= 50
                    and survivors_commit.get(h, 0) == 0 and h not in in_volo]

    res = {
        "finestra": [da, fine], "traversata_dal": dal,
        "misura_ora": datetime.datetime.now().astimezone().isoformat(timespec="minutes"),
        "main": git("rev-parse", "--short", "main").strip(),
        "commit_non_merge": len(commits), "merge": n_merge,
        "righe": {"+": add, "-": dele, "+w": add_w, "-w": del_w},
        "aree": {k: {"+": v[0], "-": v[1], "+w": v[2], "-w": v[3], "commit": len(v[4])}
                 for k, v in sorted(areas.items())},
        "vive_max_sui_ref": vive, "vive_pct": round(100 * vive / add_w, 1) if vive is not None and add_w else None,
        "ref_sopravvivenza": refs,
        "morte_7g_pct": round(100 * dead7 / add_w, 1) if add_w else None,
        "morte_30g_pct": round(100 * dead30 / add_w, 1) if add_w else None,
        "coppie_3gg": coppie, "fix": n_fix, "parole_di_ritorno": n_kw, "revert": reverts,
        "commit_decisione_proprietario": decisioni,
        "flip_fine_riga": flip,
        "in_volo": {"commit": len(in_volo), "righe_w": righe_in_volo},
        "commit_50_morti_in_main": big_dead,
        "id_documento_nei_soggetti": id_doc.most_common(30),
        "top_file": sorted(((len(v[2]), v[0], v[1], f) for f, v in filestats.items()), reverse=True)[:25],
    }
    (out / "churn.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for k in ("finestra", "main", "commit_non_merge", "merge", "righe", "vive_pct", "morte_7g_pct",
              "morte_30g_pct", "coppie_3gg", "fix", "parole_di_ritorno", "revert",
              "commit_decisione_proprietario", "in_volo", "flip_fine_riga", "ref_sopravvivenza"):
        print(f"{k}: {res[k]}")
    print("aree (+w/-w, commit):")
    for k, v in res["aree"].items():
        print(f"  {k:26s} +{v['+w']:>7} -{v['-w']:>6}  c{v['commit']}")
    print("commit ≥50 righe tutti morti su main:", res["commit_50_morti_in_main"])
    print("id documento più citati nei soggetti:", res["id_documento_nei_soggetti"][:15])
    print("file più toccati (commit, +w, -w):")
    for n, ad, de, f in res["top_file"][:15]:
        print(f"  {n:>3}c +{ad:>6} -{de:>6} {f}")


if __name__ == "__main__":
    main()
