import sys, glob, fitz
sys.path.insert(0, r"C:\DEV\xbrlbudget-main\xbrlbudget")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import importers.schema_legge_generico as g
i = sys.argv[1]
f = (glob.glob(f"Test/**/budget_{i}_*", recursive=True) or glob.glob(f"Test/**/{i}*", recursive=True))[0]
with fitz.open(f) as d:
    righe, n, anni = g._leggi(d)
print(f, "colonne", n, "anni", anni)
a, b = (int(x) for x in (sys.argv[2:4] if len(sys.argv) > 3 else (0, 400)))
for k, r in enumerate(righe[a:b], a):
    print(k, r.pagina, r.didascalia[:75], [str(v) for v in r.valori])
