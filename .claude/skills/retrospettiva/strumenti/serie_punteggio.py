#!/usr/bin/env python3
"""Serie dei giri di punteggio dell'importatore, per la retrospettiva.

Legge ogni `<etichetta>/punteggio.json` nella cartella dei giri (quella di `tests/corpus/punteggio.py`,
`IMPORT_PUNTEGGIO_DIR`) e stampa due tabelle markdown in ordine di data:

1. i giri sul campione con verità, raggruppati per **insieme di documenti** (stessi id ⇒ stesso gruppo):
   solo dentro un gruppo i numeri sono confrontabili. Le verità possono cambiare anche a insieme fisso
   (es. le regole R3 dell'11/11): la colonna `verità` riporta la data di modifica più recente delle
   verità **non** registrata nel giro, quindi quel salto va dichiarato a mano dal ledger;
2. i giri sul corpus intero (`--corpus`), senza verità.

Con `--forme` aggiunge le colonne macro/KPI/dettagli delle tipologie indicate (default: le due dei
bilanci di verifica, `conti/colonne` e `contrapposte`).

Non legge cifre dei documenti, solo le sintesi: l'uscita si può citare in una retrospettiva in git.

Uso:
    python3 serie_punteggio.py <cartella-punteggio> [--da 2026-10-18] [--forme conti/colonne,contrapposte]
            [--json uscita.json]
"""
import argparse
import hashlib
import json
from pathlib import Path


def pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def leggi(cartella: Path):
    giri = []
    for f in sorted(cartella.glob("*/punteggio.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        meta = d.get("meta") or {}
        if not meta.get("data"):
            continue
        ids = sorted(str(x.get("id")) for x in d.get("documenti") or [])
        g = {
            "etichetta": meta.get("etichetta") or f.parent.name,
            "data": meta.get("data"),
            "commit": meta.get("commit"),
            "ripetizioni": meta.get("ripetizioni"),
            "modo": meta.get("modo") or "campione",
            "n_doc": len(ids),
            "insieme": hashlib.sha1(",".join(ids).encode()).hexdigest()[:8],
            "confronto": meta.get("confronto"),
        }
        s = d.get("sintesi") or {}
        if g["modo"] == "corpus":
            t = (s.get("totale") or {}).get("tutti") or {}
            fonti = t.get("fonti") or {}
            g.update(
                importati=t.get("importati"), quadrati=t.get("quadrati"), sbilanciati=t.get("sbilanciati"),
                rif_attesi=t.get("rifiutati_attesi"), rif_errore=t.get("rifiutati_errore"),
                rif_servizio=t.get("rifiutati_servizio"), instabili=t.get("instabili"),
                sec_mediana=t.get("secondi_mediana"),
                deterministici=sum(v for k, v in fonti.items() if k.startswith("deterministico:")
                                   and k != "deterministico:lettore"),
                lettore=fonti.get("deterministico:lettore", 0), qwen=fonti.get("qwen", 0),
            )
        else:
            per = d.get("percorso") or {}
            let = d.get("lettore") or {}
            sbil = per.get("sbilanciati_ora")
            if sbil is None:
                sbil = let.get("sbilanciati_documenti")
            g.update(
                esito=s.get("esito_giusto"), macro=s.get("macro_esatti"), kpi=s.get("kpi_esatti"),
                dettagli=s.get("dettagli_esatti"), precedente=s.get("precedente_macro_esatti"),
                instabili=s.get("documenti_instabili"),
                sbilanciati=len(sbil) if isinstance(sbil, list) else sbil,
                adottati=len(per.get("documenti_adottati") or []) if per.get("presente") else None,
                per_tipologia=s.get("per_tipologia") or {},
            )
        giri.append(g)
    return sorted(giri, key=lambda g: g["data"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cartella", type=Path)
    ap.add_argument("--da", default=None, help="solo giri da questa data (YYYY-MM-DD)")
    ap.add_argument("--forme", default="conti/colonne,contrapposte")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()
    giri = [g for g in leggi(a.cartella) if not a.da or g["data"] >= a.da]
    forme = [x for x in a.forme.split(",") if x]

    camp = [g for g in giri if g["modo"] != "corpus"]
    gruppi = {}
    for g in camp:
        gruppi.setdefault((g["n_doc"], g["insieme"]), []).append(g)
    print("## Giri sul campione con verità (confrontabili solo dentro un gruppo)\n")
    for (n, ins), gs in sorted(gruppi.items(), key=lambda kv: kv[1][0]["data"]):
        print(f"### {n} documenti · insieme {ins}\n")
        cols = ["data", "giro", "commit", "×", "esito", "macro", "KPI", "dettagli", "anno prec.",
                "instabili", "sbilanciati", "adottati"] + [f"{f} macro/KPI/det." for f in forme]
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for g in gs:
            pt = g["per_tipologia"]
            ff = []
            for f in forme:
                t = pt.get(f)
                ff.append("—" if not t else f"{pct(t.get('macro'))} / {pct(t.get('kpi'))} / {pct(t.get('dettagli'))}")
            row = [g["data"], g["etichetta"], g["commit"] or "", str(g["ripetizioni"] or ""),
                   pct(g["esito"]), pct(g["macro"]), pct(g["kpi"]), pct(g["dettagli"]), pct(g["precedente"]),
                   str(g["instabili"]), str(g["sbilanciati"] if g["sbilanciati"] is not None else "—"),
                   str(g["adottati"] if g["adottati"] is not None else "—")] + ff
            print("| " + " | ".join(row) + " |")
        print()

    corp = [g for g in giri if g["modo"] == "corpus"]
    if corp:
        print("## Giri sul corpus intero (senza verità)\n")
        cols = ["data", "giro", "commit", "×", "doc", "importati", "quadrati", "sbilanciati", "rif. attesi",
                "rif. errore", "rif. servizio", "instabili", "det.", "lettore", "qwen", "sec. mediana"]
        print("| " + " | ".join(cols) + " |")
        print("|" + "---|" * len(cols))
        for g in corp:
            print("| " + " | ".join(str(x) for x in [
                g["data"], g["etichetta"], g["commit"], g["ripetizioni"], g["n_doc"], g["importati"],
                g["quadrati"], g["sbilanciati"], g["rif_attesi"], g["rif_errore"], g["rif_servizio"],
                g["instabili"], g["deterministici"], g["lettore"], g["qwen"], g["sec_mediana"]]) + " |")
        print()
    if a.json:
        a.json.write_text(json.dumps(giri, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
