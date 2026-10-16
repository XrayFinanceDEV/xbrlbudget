r"""Uso: python -I prova_sc_copia.py <copia_situazione_contabile_parser.py> [id ...]
Misura la COPIA del parser delle situazioni contabili con le regole di adozione dello snello
(deterministico._esito: scarto SP, CE e totali stampati, massa non classificata).
Con --regressione: confronta, sui 31 file che oggi chiudono, i valori della copia con quelli del
parser del repo; ogni differenza e' una REGRESSIONE da eliminare.
Nessuna rete. Lanciare con cwd = C:\DEV\xbrlbudget-main\xbrlbudget."""
import sys, glob, os, socket, logging, importlib.util
sys.path.insert(0, r"C:\DEV\xbrlbudget-main\xbrlbudget")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for k in ("ANTHROPIC_API_KEY", "GX10_API_KEY"): os.environ.pop(k, None)
def _b(*a, **k): raise RuntimeError("rete vietata")
socket.socket.connect = _b; socket.create_connection = _b
logging.disable(logging.CRITICAL)
import importers.situazione_contabile_parser as repo
spec = importlib.util.spec_from_file_location("copia_sc", sys.argv[1])
copia = importlib.util.module_from_spec(spec); spec.loader.exec_module(copia)
from importers.import_snello.deterministico import _esito
OK31 = "158 169 188 213 238 249 281 338 587 589 590 612 615 647 680 691 699 700 343 348 435 342 373 374 375 131 210 337 132 215".split()
args = sys.argv[2:]
def trova(i):
    return (glob.glob(f"Test/**/budget_{i}_*", recursive=True) or glob.glob(f"Test/**/{i}*", recursive=True))[0]
if args and args[0] == "--regressione":
    ids = OK31 + ["BILANCIO-TEST"]; diffs = 0
    for i in ids:
        f = trova(i)
        a = repo.extract_situazione_contabile(f, return_prior=True)
        b = copia.extract_situazione_contabile(f, return_prior=True)
        if a != b:
            diffs += 1
            for n, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    ks = sorted(set(x or {}) | set(y or {}))
                    dd = [(k, str((x or {}).get(k)), str((y or {}).get(k))) for k in ks if (x or {}).get(k) != (y or {}).get(k)]
                    print(f"REGRESSIONE {i} parte={n} {dd[:6]}")
    print("file con differenze:", diffs, "su", len(ids))
    sys.exit(0)
for i in args:
    f = trova(i)
    try:
        bs, ce, pb, pc = copia.extract_situazione_contabile(f, return_prior=True)
        e = _esito("situazione_contabile_parser", bs, ce, None)
        m = e.get("misura") or (e.get("lettura") or {}).get("misura") or {}
        from importers.import_snello.verifica import misura
        from importers.import_snello.deterministico import _adatta
        mm = misura(_adatta(bs), _adatta(ce), None, forma="bilancio") if bs and ce else {}
        print(f"{i:>6} adottato={e['adottato']} esito={e['esito']} att={mm.get('attivo')} sp={mm.get('scarto_sp')} ce={mm.get('scarto_ce')} massa={e.get('unclassified_mass')}")
    except Exception as ex:
        print(f"{i:>6} ERR {type(ex).__name__}: {str(ex)[:150]}")
