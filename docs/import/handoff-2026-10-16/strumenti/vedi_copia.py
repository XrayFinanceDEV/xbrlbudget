r"""Uso: python -I vedi_copia.py <copia_modulo.py> <id> [da a]  -> righe normalizzate dal lettore."""
import sys, glob, fitz, importlib.util
sys.path.insert(0, r"C:\DEV\xbrlbudget-main\xbrlbudget")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
spec = importlib.util.spec_from_file_location("copia_generico", sys.argv[1])
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
i = sys.argv[2]
f = (glob.glob(f"Test/**/budget_{i}_*", recursive=True) or glob.glob(f"Test/**/{i}*", recursive=True))[0]
with fitz.open(f) as d:
    righe, n, anni = g._leggi(d)
print(f, "colonne", n, "anni", anni)
a, b = (int(x) for x in (sys.argv[3:5] if len(sys.argv) > 4 else (0, 1000)))
for k, r in enumerate(righe[a:b], a):
    print(k, r.pagina, r.didascalia[:80], [str(v) for v in r.valori])
