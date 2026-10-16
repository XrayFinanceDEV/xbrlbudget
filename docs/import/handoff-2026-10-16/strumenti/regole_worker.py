"""Un PDF -> una riga JSON: SOLO lettori a regole, nessuna chiamata di modello.

Rete bloccata a livello socket: qualunque tentativo di chiamata (Anthropic, gx10, MinerU)
solleva RetBloccata e viene registrato come "avrebbe chiamato un modello".
"""
import json, os, socket, sys, time, traceback
from decimal import Decimal

ROOT = r"C:\DEV\xbrlbudget-main\xbrlbudget"
sys.path.insert(0, ROOT)
for k in ("ANTHROPIC_API_KEY", "GX10_API_KEY", "MINERU_API_KEY"):
    os.environ.pop(k, None)
os.environ["MINERU_OCR_ENABLED"] = "false"

TENTATIVI_RETE = []


class RetBloccata(RuntimeError):
    pass


def _blocca(*a, **k):
    TENTATIVI_RETE.append(repr(a[1:2]))
    raise RetBloccata("rete bloccata dall'analisi")


socket.socket.connect = _blocca
socket.socket.connect_ex = _blocca
socket.create_connection = _blocca

import logging
logging.disable(logging.CRITICAL)


def s(v):
    return None if v is None else str(v)


def main(path):
    out = {"file": path}
    t0 = time.time()
    import fitz
    doc = fitz.open(path)
    out["pagine"] = len(doc)
    sample = "".join(p.get_text() for p in doc[:14])
    doc.close()
    out["caratteri"] = len(sample.strip())
    out["scansione"] = len(sample.strip()) < 50
    from importers.pdf_extractor_llm import _text_layer_is_garbled
    try:
        out["testo_corrotto"] = bool(_text_layer_is_garbled(sample))
    except Exception:
        out["testo_corrotto"] = None
    if out["scansione"]:
        out["esito"] = "scansione"
        return out
    from importers.bilancio_classifier import classify_bilancio
    c = classify_bilancio(file_path=path, text=sample)
    out.update(route=c.route, macro=c.macro_area, sub=c.subcategory, motivo=c.reason)

    from importers.pdf_mapper import IVCEEMapper
    from importers.iv_cee_hierarchy import check_quadratura
    mapper = IVCEEMapper()
    lettori = {}

    # --- source_reconciliation (gira su ogni route prima della scelta) ---
    import importers.ledger_evidence as le
    import importers.llm_provider as lp
    chiamata = {"ledger": False}

    def finto_reader(frontier):
        chiamata["ledger"] = True
        raise RetBloccata("ledger avrebbe chiamato il modello")
    lp.lettore_dettagli_disponibile = lambda: True
    le.read_accounts = finto_reader
    try:
        from importers.source_reconciliation import extract_source_candidates
        sc = extract_source_candidates(path)
        compl = bool(sc and sc[0][0] is not None and sc[0][1] is not None)
        meta = sc[0][2] if sc and len(sc[0]) > 2 and isinstance(sc[0][2], dict) else {}
        lettori["fonti"] = {"completo": compl, "metodo": meta.get("method"),
                            "stato": meta.get("status"), "ledger_llm": chiamata["ledger"]}
    except Exception as e:
        lettori["fonti"] = {"errore": f"{type(e).__name__}: {str(e)[:120]}",
                            "ledger_llm": chiamata["ledger"]}

    if c.route == "ivcee" or "ivcee" in str(c.route).lower():
        # 1. reso XBRL
        try:
            from importers import xbrl_reso_parser
            cand = xbrl_reso_parser.estrai(path)
            if cand is None:
                lettori["xbrl_reso"] = {"riconosciuto": False}
            else:
                lettori["xbrl_reso"] = {"riconosciuto": True, "adottabile": bool(cand.get("adottabile")),
                                        "rifiuto": s(cand.get("rifiuto"))[:300] if cand.get("rifiuto") else None}
            from importers.pdf_importer import _xbrl_reso_extract
            lettori["xbrl_reso"]["adottato"] = _xbrl_reso_extract(path) is not None
        except Exception as e:
            lettori["xbrl_reso"] = {"errore": f"{type(e).__name__}: {str(e)[:160]}"}
        # 2. schema con percorso nell'etichetta
        try:
            from importers import schema_etichette_parser as et
            letto = et.estrai(path)
            if letto is None:
                lettori["etichette"] = {"riconosciuto": False}
            else:
                lettori["etichette"] = {"riconosciuto": True,
                                        "bs_ce": letto.get("bs") is not None and letto.get("ce") is not None,
                                        "rifiuto": s(letto.get("rifiuto"))[:300] if letto.get("rifiuto") else None}
            from importers.pdf_importer import _schema_etichette_extract
            lettori["etichette"]["adottato"] = _schema_etichette_extract(path) is not None
        except Exception as e:
            lettori["etichette"] = {"errore": f"{type(e).__name__}: {str(e)[:160]}"}
        # 3. IV-CEE standard
        try:
            from importers.standard_ivcee_parser import (extract_standard_ivcee_balances,
                                                         extract_standard_ivcee_income)
            bs, pbs = extract_standard_ivcee_balances(path)
            ce, pce = extract_standard_ivcee_income(path)
            r = {"bs": bs is not None, "ce": ce is not None}
            if bs is not None and ce is not None:
                q = check_quadratura(bs, ce, tol=Decimal("2"))
                r["valida"] = bool(mapper.validate_balance(bs))
                r["quadra"] = bool(q.quadra)
                r["avvisi"] = [str(w)[:160] for w in (q.warnings or [])][:4]
                r["adottato"] = r["valida"] and r["quadra"]
            else:
                r["adottato"] = False
            lettori["standard"] = r
        except Exception as e:
            lettori["standard"] = {"errore": f"{type(e).__name__}: {str(e)[:160]}", "adottato": False}
        adott = [n for n in ("xbrl_reso", "etichette", "standard") if lettori.get(n, {}).get("adottato")]
        if lettori["fonti"].get("completo"):
            out["esito"] = "corta:fonti"
        elif adott:
            out["esito"] = "corta:" + adott[0]
        else:
            out["esito"] = "lunga:ivcee_llm"
    elif "trial" in str(c.route).lower() or c.route == "C":
        try:
            from importers.situazione_contabile_parser import extract_situazione_contabile
            from importers.pdf_importer import _map_sc_keys
            sb, sce, pb, pce = extract_situazione_contabile(path, return_prior=True)
            b, e = _map_sc_keys(sb or {}), _map_sc_keys(sce or {})
            r = {"attivo": s(b.get("totale_attivo")), "passivo": s(b.get("totale_passivo"))}
            if b.get("totale_attivo", Decimal(0)) > 0:
                q = check_quadratura(b, e)
                r.update(vuoto=bool(q.is_empty), quadra=bool(q.quadra), plug=s(q.plug_residual),
                         massa_non_class=s(b.get("_unclassified_mass")))
            else:
                r["vuoto"] = True
            try:
                from importers.pdf_extractor_llm import _declared_control_totals
                dc = _declared_control_totals(path, text=None)
                r["dichiarati"] = {k: s(v) for k, v in (dc or {}).items() if not isinstance(v, (dict, list))}
            except Exception as ex:
                r["dichiarati_err"] = type(ex).__name__
            r["anno_prec"] = bool(pb and pce)
            lettori["sc_deterministico"] = r
        except Exception as ex:
            lettori["sc_deterministico"] = {"errore": f"{type(ex).__name__}: {str(ex)[:160]}"}
        out["esito"] = "corta:fonti" if lettori["fonti"].get("completo") else "lunga:route_C_CoGe"
    else:
        out["esito"] = "rifiutato:" + str(c.route)
    out["lettori"] = lettori
    out["secondi"] = round(time.time() - t0, 1)
    out["tentativi_rete"] = TENTATIVI_RETE[:3]
    return out


if __name__ == "__main__":
    p = sys.argv[1]
    try:
        r = main(p)
    except Exception as e:
        r = {"file": p, "esito": "crash", "errore": f"{type(e).__name__}: {str(e)[:200]}",
             "tb": traceback.format_exc()[-600:], "tentativi_rete": TENTATIVI_RETE[:3]}
    print("@@JSON@@" + json.dumps(r, ensure_ascii=False, default=str))
