import json, os, socket, sys, time
sys.path.insert(0, r"C:\DEV\xbrlbudget-main\xbrlbudget")
for k in ("ANTHROPIC_API_KEY","GX10_API_KEY","MINERU_API_KEY"): os.environ.pop(k, None)
T=[]
def _b(*a,**k):
    T.append(1); raise RuntimeError("rete bloccata")
socket.socket.connect=_b; socket.socket.connect_ex=_b; socket.create_connection=_b
import logging; logging.disable(logging.CRITICAL)
p=sys.argv[1]; t0=time.time()
try:
    from importers.import_snello.deterministico import tentativo
    r=tentativo(p)
    out={k:r.get(k) for k in ("adottato","parser","esito","rifiuto","unclassified_mass","xbrl_reso","causa")}
    m=r.get("misura") or (r.get("lettura") or {}).get("misura")
    if m: out["misura"]={k:str(v) for k,v in m.items() if k.startswith("scarto") or k=="attivo"}
    out["tappo"]=str(r.get("tappo")) if r.get("tappo") else None
    def _v(d): return None if not d else {k:str(v) for k,v in d.items() if not k.startswith("_") and v is not None}
    out["bs"]=_v(r.get("bs")); out["ce"]=_v(r.get("ce")); out["prior_bs"]=_v(r.get("prior_bs")); out["prior_ce"]=_v(r.get("prior_ce"))
except Exception as e:
    out={"esito":"crash","errore":f"{type(e).__name__}: {str(e)[:200]}"}
out.update(file=p, secondi=round(time.time()-t0,1), rete=len(T))
print("@@JSON@@"+json.dumps(out,ensure_ascii=False,default=str))
