import json, sys, collections
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
base = {json.loads(l)["file"]: json.loads(l) for l in open(sys.argv[1], encoding="utf-8")}
dopo = {json.loads(l)["file"]: json.loads(l) for l in open(sys.argv[2], encoding="utf-8")}
print("adottati prima:", sum(1 for b in base.values() if b.get("adottato")),
      " dopo:", sum(1 for b in dopo.values() if b.get("adottato")), " su", len(dopo))
print("rete:", sum(b.get("rete", 0) for b in dopo.values()))
cambiati, nuovi, persi = [], [], []
for f, b in base.items():
    d = dopo.get(f, {})
    if b.get("adottato") and not d.get("adottato"):
        persi.append(f)
    elif b.get("adottato") and d.get("adottato"):
        for k in ("bs", "ce", "prior_bs", "prior_ce"):
            if b.get(k) != d.get(k):
                cambiati.append((f, k)); break
    elif not b.get("adottato") and d.get("adottato"):
        nuovi.append((f, d.get("parser"), d.get("esito")))
print("PERSI:", persi)
print("VALORI CAMBIATI:", cambiati)
print("NUOVI:", len(nuovi))
for n in nuovi: print("  ", n)
print(collections.Counter((d.get("parser"), d.get("esito")) for d in dopo.values() if d.get("adottato")))
