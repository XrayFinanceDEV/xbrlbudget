"""Punteggio dell'importatore PDF contro la verità del campione (Fase 0).

Fa girare l'importatore di produzione (`import_pdf_balance_sheet`, la funzione dell'endpoint
`/import/pdf`) sui documenti di `tests/corpus/campione.json`, su un DB in memoria usa-e-getta,
e confronta campo per campo ciò che ha salvato con la verità consolidata
(`Test/_analisi-campione/verita/<id>.json`, fuori da git: sono cifre di clienti).

Come in produzione:
- una scansione passa da MinerU, con lo stesso criterio dell'endpoint (`_e_una_scansione`);
- per un infrannuale si passano i mesi del periodo, come li inserirebbe l'utente.

Che cosa misura, per documento e in sintesi:
- **esito**: importato o rifiutato, contro il giudizio atteso (i rifiuti giusti contano);
- **macro**: gli aggregati sp01..sp18 e ce01..ce20 uguali alla verità entro 1 €;
- **kpi**: i dettagli sui confini dei KPI (sp06a, sp16a-d, sp17a-c, ce08, ce09a/b);
- **dettagli**: gli altri dettagli presenti nella verità;
- **quadra**: attivo = passivo + PN nel salvato;
- **anno precedente**: lo stesso confronto sull'esercizio precedente, quando l'importatore lo salva.
I campi che la verità marca `dubbio` sono contati a parte e non pesano sul punteggio.

La lettura dei modelli non è deterministica: con `--ripetizioni N` ogni documento gira N volte e il
rapporto dice quanti campi cambiano fra un giro e l'altro.

Uso (le variabili dell'ambiente di produzione, gx10 e MinerU, nel processo: mai su riga di comando):
    backend/venv/bin/python tests/corpus/punteggio.py --etichetta main-046ab43 [--ripetizioni 3]
    backend/venv/bin/python tests/corpus/punteggio.py --solo 1325,395 --etichetta prova
    backend/venv/bin/python tests/corpus/punteggio.py --da-esiti <cartella>   # ricalcola senza importare

Scrive in `Test/_analisi-campione/punteggio/<etichetta>/`: `esiti.jsonl` (ciò che l'importatore ha
salvato, giro per giro), `punteggio.json` e `punteggio.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPIONE = ROOT / "tests" / "corpus" / "campione.json"
VERITA = Path(os.environ.get("IMPORT_VERITA_DIR", ROOT / "Test" / "_analisi-campione" / "verita"))
USCITA = ROOT / "Test" / "_analisi-campione" / "punteggio"
CORPUS = Path(os.environ.get("IMPORT_CORPUS_ROOT", ROOT / "Test"))

TOLLERANZA = 1.0          # euro: molti documenti stampano all'unità
CODICE = re.compile(r"^((?:sp|ce)\d{2}[a-z]?)(?:_|$)")
MACRO = {f"sp{n:02d}" for n in range(1, 19)} | {f"ce{n:02d}" for n in range(1, 21)}
KPI = {"sp06a", "sp16a", "sp16b", "sp16c", "sp16d", "sp17a", "sp17b", "sp17c", "ce08", "ce09a", "ce09b"}


# --- confronto (puro: lo prova tests/test_punteggio_corpus.py) ---------------------------------

def codice(nome: str) -> str | None:
    m = CODICE.match(nome)
    return m.group(1) if m else None


def categoria(cod: str) -> str:
    return "macro" if cod in MACRO else "kpi" if cod in KPI else "dettagli"


def confronta_periodo(vero: dict, letto: dict, tol: float = TOLLERANZA) -> dict:
    """`vero`: {codice: {valore, stato}} della verità; `letto`: {codice: float} salvato
    dall'importatore (un campo assente vale zero, come nel DB). Restituisce i conteggi per
    categoria e l'elenco degli errori."""
    out = {c: {"giusti": 0, "totali": 0} for c in ("macro", "kpi", "dettagli")}
    out["dubbi"] = {"giusti": 0, "totali": 0}
    errori = []
    for cod, campo in vero.items():
        try:
            v = float(campo["valore"])
        except (TypeError, ValueError, KeyError):
            continue
        l = float(letto.get(cod, 0.0) or 0.0)
        giusto = abs(v - l) <= tol
        cat = "dubbi" if campo.get("stato") == "dubbio" else categoria(cod)
        out[cat]["totali"] += 1
        out[cat]["giusti"] += giusto
        if not giusto and cat != "dubbi":
            errori.append({"campo": cod, "categoria": cat, "vero": v, "letto": l, "scarto": round(l - v, 2)})
    errori.sort(key=lambda e: -abs(e["scarto"]))
    out["errori"] = errori
    return out


def esito_atteso_rispettato(giudizio_atteso: str, importato: bool) -> bool:
    return importato != (giudizio_atteso == "da rifiutare")


def quota(n: int, d: int):
    return round(n / d, 4) if d else None


# --- verità ---------------------------------------------------------------------------------------

def carica_verita(id_: str) -> dict | None:
    p = VERITA / f"{id_}.json"
    if not p.exists():
        return None
    d = json.load(open(p, encoding="utf-8"))
    periodi = []
    for per in d.get("periodi", []):
        campi = {}
        for k, c in per.get("campi", {}).items():
            cod = codice(k)
            if cod and isinstance(c, dict):
                campi[cod] = c
        periodi.append({"fine": per.get("fine"), "periodo": per.get("periodo"), "campi": campi})
    periodi.sort(key=lambda p: p["fine"] or "", reverse=True)    # il più recente è il corrente
    return {"id": id_, "giudizio_atteso": d.get("giudizio_atteso"), "periodi": periodi}


def mesi_del_periodo(periodo: str | None) -> int | None:
    """'2026-01-01..2026-09-30' -> 9; un esercizio intero o non leggibile -> None."""
    d = re.findall(r"(\d{4})-(\d{2})-(\d{2})", periodo or "")
    if len(d) < 2:
        return None
    (a0, m0, _), (a1, m1, _) = d[0], d[-1]
    mesi = (int(a1) - int(a0)) * 12 + int(m1) - int(m0) + 1
    return mesi if 1 <= mesi <= 11 else None


# --- import ---------------------------------------------------------------------------------------

def anno_del_periodo(fine: str | None) -> int | None:
    """L'anno di chiusura, quello che l'utente scrive nell'import (`fiscal_year` è obbligatorio
    sull'endpoint: senza, l'importatore salva l'anno di oggi e non salva l'esercizio precedente)."""
    return int(fine[:4]) if fine and fine[:4].isdigit() else None


def importa(percorso: Path, period_months: int | None, fiscal_year: int | None = None) -> dict:
    """Un giro dell'importatore di produzione: ciò che ha salvato, per esercizio. Non solleva mai."""
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "backend"))
    from tests._import_probe import probe              # installa il DB in memoria
    import database.db as dbmod
    from database.models import Company, FinancialYear

    scansione = _e_una_scansione(percorso.read_bytes())
    metodo = "ocr" if scansione and os.environ.get("MINERU_OCR_ENABLED", "").lower() in ("1", "true") else "standard"
    t0 = time.monotonic()
    rec = probe(str(percorso), metodo, fiscal_year=fiscal_year, period_months=period_months)
    esito = {"metodo": metodo, "scansione": scansione, "secondi": round(time.monotonic() - t0, 1),
             "importato": bool(rec.get("ok")) and not rec.get("error"), "errore": rec.get("error"),
             "estrattore": rec.get("extraction_method"), "quadra": rec.get("quadra"),
             "sbilancio": rec.get("sbilancio"), "avvisi": rec.get("warnings", []), "esercizi": []}
    # Tutti gli esercizi salvati per l'azienda creata dal giro (anno corrente e, se c'è, precedente).
    # Ogni giro cancella le sue aziende, quindi l'unica presente è quella appena creata (il nome
    # può essere quello letto nel documento, non quello del file).
    s = dbmod.SessionLocal()
    try:
        az = s.query(Company).order_by(Company.id.desc()).first() if esito["importato"] else None
        for fy in (s.query(FinancialYear).filter(FinancialYear.company_id == az.id).all() if az else []):
            campi = {}
            for obj in (fy.balance_sheet, fy.income_statement):
                for col in (obj.__table__.columns if obj is not None else []):
                    cod = codice(col.name)
                    v = getattr(obj, col.name)
                    if cod and v is not None and not col.name.endswith(("_pct", "_override")):
                        campi[cod] = float(v)
            esito["esercizi"].append({"anno": fy.year, "mesi": fy.period_months, "campi": campi})
        for c in s.query(Company).all():                          # il prossimo giro riparte pulito
            s.delete(c)                                           # (oggetto per oggetto: cascata ORM)
        s.commit()
    finally:
        s.close()
    esito["esercizi"].sort(key=lambda e: (e["anno"], e["mesi"] or 12), reverse=True)
    return esito


def _importa_lavoro(lavoro: tuple) -> dict:
    """(id, giro, percorso, mesi, anno) -> esito con id e giro: l'unità di lavoro, anche in un processo a parte."""
    id_, giro, percorso, mesi, anno = lavoro
    e = importa(percorso, mesi, anno)
    e.update(id=id_, giro=giro)
    return e


def _e_una_scansione(content: bytes) -> bool:
    """Lo stesso criterio dell'endpoint `/import/pdf`."""
    sys.path.insert(0, str(ROOT / "backend"))
    from app.api.v1.imports import _e_una_scansione as criterio
    return criterio(content)


# --- punteggio ------------------------------------------------------------------------------------

def punteggio_documento(vero: dict, giri: list[dict]) -> dict:
    """Confronta ogni giro con la verità: periodo corrente col primo esercizio salvato,
    periodo precedente col secondo."""
    risultati = []
    for g in giri:
        r = {"importato": g["importato"], "errore": g.get("errore"),
             "esito_giusto": esito_atteso_rispettato(vero["giudizio_atteso"], g["importato"]),
             "quadra": g.get("quadra"), "secondi": g.get("secondi"), "periodi": []}
        if g["importato"] and vero["giudizio_atteso"] != "da rifiutare":
            for i, per in enumerate(vero["periodi"][:2]):
                es = _esercizio_del_periodo(g["esercizi"], per, i)
                c = confronta_periodo(per["campi"], es["campi"] if es else {})
                c["fine"] = per["fine"]
                c["salvato"] = es is not None
                # Un confronto di nove mesi salvato come esercizio intero diventa un anno base falso.
                c["periodo_giusto"] = es is None or es.get("mesi") == mesi_del_periodo(per.get("periodo"))
                r["periodi"].append(c)
        risultati.append(r)
    stab = _stabilita(giri)
    return {"id": vero["id"], "giudizio_atteso": vero["giudizio_atteso"], "giri": risultati, "stabilita": stab}


def _esercizio_del_periodo(esercizi: list[dict], per: dict, i: int) -> dict | None:
    """L'esercizio salvato (anno, mesi, campi) con l'anno del periodo; senza anno nel periodo, quello nella stessa posizione."""
    anno = anno_del_periodo(per.get("fine"))
    if anno is None:
        return esercizi[i] if i < len(esercizi) else None
    return next((e for e in esercizi if e["anno"] == anno), None)


def _stabilita(giri: list[dict]) -> dict | None:
    """Fra più giri dello stesso documento: quanti campi del corrente cambiano."""
    salvati = [g["esercizi"][0]["campi"] for g in giri if g["importato"] and g["esercizi"]]
    if len(giri) < 2:
        return None
    campi = set().union(*salvati) if salvati else set()
    instabili = sorted(c for c in campi if len({round(s.get(c, 0.0), 2) for s in salvati}) > 1)
    return {"giri": len(giri), "esiti_diversi": len({g["importato"] for g in giri}) > 1,
            "campi_instabili": instabili}


def sintesi(documenti: list[dict], campione: dict) -> dict:
    tot = defaultdict(lambda: [0, 0])
    per_tipo = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    esiti = [0, 0]
    doc_macro_esatti = [0, 0]
    instabili = 0
    periodo_sbagliato = []
    for d in documenti:
        tipo = campione[d["id"]].get("tipologia", "?")
        for g in d["giri"]:
            esiti[0] += g["esito_giusto"]
            esiti[1] += 1
            per_tipo[tipo]["esito"][0] += g["esito_giusto"]
            per_tipo[tipo]["esito"][1] += 1
            corr = g["periodi"][0] if g["periodi"] else None
            if corr:
                doc_macro_esatti[1] += 1
                doc_macro_esatti[0] += corr["macro"]["giusti"] == corr["macro"]["totali"]
                for cat in ("macro", "kpi", "dettagli"):
                    tot[cat][0] += corr[cat]["giusti"]
                    tot[cat][1] += corr[cat]["totali"]
                    per_tipo[tipo][cat][0] += corr[cat]["giusti"]
                    per_tipo[tipo][cat][1] += corr[cat]["totali"]
            for per in g["periodi"]:
                if per.get("periodo_giusto") is False and (d["id"], per["fine"]) not in periodo_sbagliato:
                    periodo_sbagliato.append((d["id"], per["fine"]))
            if len(g["periodi"]) > 1:
                prec = g["periodi"][1]
                tot["precedente_macro"][0] += prec["macro"]["giusti"] if prec["salvato"] else 0
                tot["precedente_macro"][1] += prec["macro"]["totali"]
        if d["stabilita"] and (d["stabilita"]["campi_instabili"] or d["stabilita"]["esiti_diversi"]):
            instabili += 1
    return {
        "esito_giusto": quota(*esiti),
        "documenti_macro_tutti_esatti": quota(*doc_macro_esatti),
        **{f"{k}_esatti": quota(*v) for k, v in tot.items()},
        "documenti_instabili": instabili,
        "periodo_sbagliato": [f"{i} {f}" for i, f in periodo_sbagliato],
        "per_tipologia": {t: {k: quota(*v) for k, v in c.items()} for t, c in sorted(per_tipo.items())},
    }


def scrivi_rapporto(cartella: Path, documenti: list[dict], sin: dict, meta: dict) -> None:
    json.dump({"meta": meta, "sintesi": sin, "documenti": documenti},
              open(cartella / "punteggio.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    pct = lambda x: "—" if x is None else f"{100 * x:.1f}%"
    r = [f"# Punteggio importatore — {meta['etichetta']}", "",
         f"{meta['documenti']} documenti, {meta['ripetizioni']} giri ciascuno, commit {meta['commit']}, {meta['data']}.", "",
         "| Misura | Valore |", "|---|---|",
         f"| Esito giusto (importa / rifiuta come atteso) | {pct(sin['esito_giusto'])} |",
         f"| Documenti con tutte le macro-voci esatte | {pct(sin['documenti_macro_tutti_esatti'])} |",
         f"| Macro-voci esatte (entro 1 €) | {pct(sin.get('macro_esatti'))} |",
         f"| Dettagli KPI esatti | {pct(sin.get('kpi_esatti'))} |",
         f"| Altri dettagli esatti | {pct(sin.get('dettagli_esatti'))} |",
         f"| Anno precedente, macro esatte | {pct(sin.get('precedente_macro_esatti'))} |",
         f"| Documenti instabili fra i giri | {sin['documenti_instabili']} |",
         f"| Esercizi salvati con la durata sbagliata | {', '.join(sin.get('periodo_sbagliato', [])) or 'nessuno'} |", "",
         "## Per tipologia", "", "| Tipologia | Esito | Macro | KPI | Dettagli |", "|---|---|---|---|---|"]
    for t, c in sin["per_tipologia"].items():
        r.append(f"| {t} | {pct(c.get('esito'))} | {pct(c.get('macro'))} | {pct(c.get('kpi'))} | {pct(c.get('dettagli'))} |")
    r += ["", "## Per documento (primo giro)", "", "| Id | Atteso | Esito | Macro | KPI | Errori principali |", "|---|---|---|---|---|---|"]
    for d in documenti:
        g = d["giri"][0]
        corr = g["periodi"][0] if g["periodi"] else None
        esito = ("importato" if g["importato"] else "rifiutato") + ("" if g["esito_giusto"] else " ✗")
        macro = f"{corr['macro']['giusti']}/{corr['macro']['totali']}" if corr else "—"
        kpi = f"{corr['kpi']['giusti']}/{corr['kpi']['totali']}" if corr else "—"
        err = "; ".join(f"{e['campo']} {e['scarto']:+,.0f}" for e in (corr["errori"][:3] if corr else []))
        if not g["importato"] and g.get("errore"):
            err = str(g["errore"])[:80]
        r.append(f"| {d['id']} | {d['giudizio_atteso']} | {esito} | {macro} | {kpi} | {err} |")
    (cartella / "punteggio.md").write_text("\n".join(r) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--etichetta", default=time.strftime("%Y%m%d-%H%M"))
    ap.add_argument("--ripetizioni", type=int, default=1)
    ap.add_argument("--solo", default=None, help="id separati da virgola")
    ap.add_argument("--riprendi", action="store_true", help="salta i giri già scritti in esiti.jsonl della stessa etichetta")
    ap.add_argument("--paralleli", type=int, default=1, help="import contemporanei, un processo ciascuno")
    ap.add_argument("--da-esiti", default=None, help="cartella di un giro precedente: ricalcola senza importare")
    args = ap.parse_args()

    campione = {c["id"]: c for c in json.load(open(CAMPIONE, encoding="utf-8"))["documenti"]}
    ids = [i.strip() for i in args.solo.split(",")] if args.solo else list(campione)
    cartella = Path(args.da_esiti) if args.da_esiti else USCITA / args.etichetta
    cartella.mkdir(parents=True, exist_ok=True)
    esiti_file = cartella / "esiti.jsonl"

    giri = defaultdict(list)
    if args.da_esiti:
        for riga in open(esiti_file, encoding="utf-8"):
            e = json.loads(riga)
            giri[e["id"]].append(e)
    else:
        fatti = set()
        if args.riprendi and esiti_file.exists():
            for riga in open(esiti_file, encoding="utf-8"):
                e = json.loads(riga)
                fatti.add((e["id"], e["giro"]))
                giri[e["id"]].append(e)
        lavori = []
        for id_ in ids:
            vero = carica_verita(id_)
            if vero is None:
                print(f"{id_}: verità assente, saltato", flush=True)
                continue
            mesi = mesi_del_periodo(vero["periodi"][0]["periodo"]) if vero["periodi"] else None
            anno = anno_del_periodo(vero["periodi"][0]["fine"]) if vero["periodi"] else None
            lavori += [(id_, n + 1, CORPUS / campione[id_]["path"], mesi, anno) for n in range(args.ripetizioni)
                       if (id_, n + 1) not in fatti]
        with open(esiti_file, "a", encoding="utf-8") as out:
            def registra(e: dict) -> None:
                out.write(json.dumps(e, ensure_ascii=False) + "\n")
                out.flush()
                giri[e["id"]].append(e)
                print(f"{e['id']} giro {e['giro']}: {'importato' if e['importato'] else 'rifiutato'} "
                      f"({e['metodo']}, {e['secondi']} s)", flush=True)
            if args.paralleli <= 1:
                for lavoro in lavori:
                    registra(_importa_lavoro(lavoro))
            else:
                # un processo per lavoratore: ognuno ha il suo DB in memoria (il probe lo installa nel processo)
                import multiprocessing as mp
                from concurrent.futures import ProcessPoolExecutor, as_completed
                with ProcessPoolExecutor(max_workers=args.paralleli, mp_context=mp.get_context("spawn")) as pool:
                    for fut in as_completed([pool.submit(_importa_lavoro, l) for l in lavori]):
                        registra(fut.result())
        for v in giri.values():
            v.sort(key=lambda e: e["giro"])

    documenti = [punteggio_documento(carica_verita(i), giri[i]) for i in ids if giri.get(i) and carica_verita(i)]
    commit = os.popen(f"git -C {ROOT} rev-parse --short HEAD").read().strip()
    meta = {"etichetta": args.etichetta if not args.da_esiti else cartella.name, "documenti": len(documenti),
            "ripetizioni": max((len(v) for v in giri.values()), default=0), "commit": commit,
            "data": time.strftime("%Y-%m-%d %H:%M")}
    sin = sintesi(documenti, campione)
    scrivi_rapporto(cartella, documenti, sin, meta)
    print(json.dumps(sin, indent=1, ensure_ascii=False))
    print(f"rapporto: {cartella / 'punteggio.md'}")


if __name__ == "__main__":
    main()
