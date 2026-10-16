import sys, glob, json, os, socket, logging
sys.path.insert(0, r"C:\DEV\xbrlbudget-main\xbrlbudget")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for k in ("ANTHROPIC_API_KEY","GX10_API_KEY"): os.environ.pop(k, None)
def _b(*a, **k): raise RuntimeError("rete")
socket.socket.connect = _b
logging.disable(logging.CRITICAL)
import importlib, importers.schema_legge_generico as g
ids = sys.argv[1:] or "133 585 586 665 672 382 413 594 597 638 315 138 161 298 341 289 695 355 150 171 257 265 137 314 115 135 152 253 683 297 sangae6".split()
ok = 0
for i in ids:
    f = (glob.glob(f"Test/**/budget_{i}_*", recursive=True) or glob.glob(f"Test/**/{i}*", recursive=True))[0]
    try:
        r = g.estrai(f)
    except Exception as e:
        print(f"{i:>7} CRASH {type(e).__name__}: {e}"); continue
    if r is None: print(f"{i:>7} non riconosciuto"); continue
    if r["adottabile"]:
        ok += 1; print(f"{i:>7} OK anni={r['anni']} prior={r.get('prior_stato')} massa={r['bs'].get('_unclassified_mass')}")
    else:
        rf = dict(r["rifiuto"]); altri = rf.pop("altri", [])
        print(f"{i:>7} NO {json.dumps(rf, ensure_ascii=False, default=str)[:230]} (+{len(altri)})")
print("adottabili", ok, "su", len(ids))
