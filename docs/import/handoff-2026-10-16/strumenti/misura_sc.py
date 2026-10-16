import sys, glob, os, socket, logging
sys.path.insert(0, r"C:\DEV\xbrlbudget-main\xbrlbudget")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for k in ("ANTHROPIC_API_KEY","GX10_API_KEY"): os.environ.pop(k, None)
def _b(*a, **k): raise RuntimeError("rete")
socket.socket.connect = _b
logging.disable(logging.CRITICAL)
from importers.situazione_contabile_parser import extract_situazione_contabile
from importers.import_snello.deterministico import _adatta
from importers.import_snello.verifica import misura
from importers.pdf_extractor_llm import _declared_control_totals
for i in sys.argv[1:]:
    f = glob.glob(f"Test/**/budget_{i}_*", recursive=True)[0]
    try:
        bs, ce, _, _ = extract_situazione_contabile(f, return_prior=True)
        b, c = _adatta(bs), _adatta(ce)
        m = misura(b, c, None, forma="bilancio")
        dc = _declared_control_totals(f)
        print(f"{i:>5} att={m['attivo']} sp={m['scarto_sp']} ce={m['scarto_ce']} plug={bs.get('_plug_residual')} massa={bs.get('_unclassified_mass')} dich={ {k:str(v) for k,v in dc.items() if v is not None and not isinstance(v,(dict,list))} }")
    except Exception as e:
        print(i, "ERR", type(e).__name__, e)
