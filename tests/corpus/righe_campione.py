"""Misura del lettore di righe (Fase 1, Task 8) sul campione contro la verità.

Fa girare `importers.lettore.leggi_pdf` sui documenti di `tests/corpus/campione.json` (nessun import, nessun DB,
nessuna rete, nessun modello) e confronta le righe del prospetto (`parte == "prospetto"`) con le due letture a vista
(`Test/_analisi-campione/<id>.json` e `opus/<id>.json`) e con la verità (`verita/<id>.json`). Le scansioni si contano
a parte: vanno per `leggi_celle` solo con MinerU acceso, fuori da questa misura.

Che cosa misura, per documento:
- **totali ritrovati**: un totale stampato (unione delle due letture, valore diverso da zero, deduplicato per
  `(pagina, valore)`) è ritrovato se una riga del prospetto di quella pagina ha una cella con quel valore entro
  0,01 € (1 € se nessuna colonna del documento stampa i centesimi);
- **totali chiusi**: fra i ritrovati, quelli su una riga marcata `totale` con `figli` sulla colonna della cella;
  accanto, *chiusi v.*: la stessa quota senza i totali ritrovati solo su una colonna di analisi o di movimenti
  (differenza, percentuale, dare, avere), dove il lettore non somma per costruzione;
- **periodi giusti**: per ogni periodo della verità, su ogni lato con colonne di valori, una colonna esercizio o
  saldo con la stessa fine (anno e mese) e gli stessi mesi; una colonna ad anno nudo (`mesi` None) vale solo per un
  anno intero (R3); con un periodo solo nella verità basta la fine;
- **mastri giusti**: per i documenti con l'elenco `conti` nella prima lettura, ogni conto non totale ritrovato
  (stessa pagina e importo; a parità, lo stesso codice o la stessa descrizione) ha come padre la riga che la lettura
  annota. Due quote: *stretta* (codice o etichetta del padre diretto) e *tollerante* (anche il primo antenato che non
  è un «Totale …», o un padre «Totale X» con X uguale al padre annotato: la lettura nomina la voce, il lettore il
  totale stampato che la chiude). Accanto, la quota di conti col padre verificato dalla somma. Le annotazioni
  sbagliate note (`CORREZIONI_ANNOTAZIONE`) non pesano e si elencano.

Uso:
    IMPORT_CORPUS_ROOT=$PWD/Test backend/venv/bin/python tests/corpus/righe_campione.py --etichetta fase1
    ... --solo 395,1456

Scrive `Test/_analisi-campione/righe/<etichetta>/righe.json` e `righe.md` (fuori da git: cifre di clienti) e stampa
la sintesi.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from importers.lettore import leggi_pdf  # noqa: E402

CAMPIONE = ROOT / "tests" / "corpus" / "campione.json"
CORPUS = Path(os.environ.get("IMPORT_CORPUS_ROOT", ROOT / "Test"))
ANALISI = CORPUS / "_analisi-campione"
USCITA = ANALISI / "righe"
A_PARTE = ("scansione",)
_VALORI = ("esercizio", "saldo")
_VALORI_E_MASTRI = ("esercizio", "saldo", "mastro")
_CENT = Decimal("0.01")
_UNITA = Decimal("1")

# Annotazioni della prima lettura che contraddicono il documento: non pesano sulla misura e si elencano, perché il
# proprietario le corregga. Un conto è escluso se ha l'id, il codice e il padre annotato dati (None = qualunque) e,
# con «voce_non», una voce_di_legge che non comincia così (il padre annotato contraddice la voce del conto stesso).
CORREZIONI_ANNOTAZIONE = [
    {"id": "353", "codice": "3901051", "padre": None, "voce_non": None,
     "perche": "sta sotto «a) Debiti verso fornitori esigibili entro»: 537.649,65 + 35.993,98 + 951,00 = "
               "574.594,63 stampato"},
    *({"id": i, "codice": None, "padre": "3) Denaro e valori in cassa", "voce_non": "SPA.C.IV",
       "perche": "annotato sotto la cassa contro la sua voce_di_legge (risconti, patrimonio netto, utili "
                 "portati a nuovo, TFR: il padre della pagina prima trascinato avanti)"}
      for i in ("1524", "1525", "1526")),
]


# --- confronto ----------------------------------------------------------------------------------------------------

def norm(testo: str | None) -> str:
    """Un'etichetta o un codice nella forma di confronto: senza accenti, spazi, punteggiatura, minuscola."""
    testo = "".join(c for c in unicodedata.normalize("NFKD", testo or "") if not unicodedata.combining(c))
    return re.sub(r"[^0-9a-z]", "", testo.casefold())


def senza_totale(etichetta: str) -> str:
    """«Totale 7) per servizi» -> «7) per servizi»; «Totale esigibili entro» -> «esigibili entro»."""
    return re.sub(r"^\s*(tot(ale|ali)?\.?|t\.)\s*[:\-]?\s*", "", etichetta or "", flags=re.I)


def e_un_totale(etichetta: str) -> bool:
    return bool(re.match(r"^\s*(tot(ale|ali)?\.?|t\.)(\s|:|$)", etichetta or "", flags=re.I))


def stesso_nome(riga, annotati: set[str]) -> bool:
    """Il padre annotato (codice, o il suo nome) nomina la riga per codice, per etichetta, o per codice + etichetta
    stampati insieme."""
    cod, et = norm(riga.codice), norm(riga.etichetta)
    return bool(annotati & ({cod, et, cod + et} - {""}))


_NUMERAZIONE = re.compile(r"^\s*(?:[A-Z]\)|[IVX]+\s*[-.)]|\d+\)|[a-z]\))\s*", re.I)


def senza_numero(testo: str) -> str:
    """«4) Debiti verso banche» -> «Debiti verso banche»; «VIII - Utili…» -> «Utili…»: il totale stampato spesso
    ripete la voce senza la sua numerazione di legge."""
    return _NUMERAZIONE.sub("", testo or "", count=1)


def stesso_totale(riga, annotati: set[str]) -> bool:
    """Un padre «Totale X» con X uguale al padre annotato, numerazione di legge a parte, o che lo contiene
    («Totale crediti verso clienti» per «1) Verso clienti»): la lettura nomina la voce, il lettore il totale che
    la chiude."""
    if not e_un_totale(riga.etichetta):
        return False
    x = senza_totale(riga.etichetta)
    nomi = {norm(x), norm(senza_numero(x))}
    return bool(nomi & annotati) or any(len(a) >= 8 and a in n for a in annotati for n in nomi)


def mesi_del_periodo(periodo: str | None) -> int | None:
    """'2026-01-01..2026-09-30' -> 9; '2025-09-01..2026-08-31' -> 12; non leggibile -> None."""
    d = re.findall(r"(\d{4})-(\d{2})-(\d{2})", periodo or "")
    if len(d) < 2:
        return None
    (a0, m0, _), (a1, m1, _) = d[0], d[-1]
    return (int(a1) - int(a0)) * 12 + int(m1) - int(m0) + 1


def periodo_giusto(colonna, fine: str, mesi: int | None, basta_la_fine: bool) -> bool:
    if colonna.fine is None or colonna.fine.strftime("%Y-%m") != fine:
        return False
    if basta_la_fine:
        return True
    if colonna.mesi is None:              # anno nudo (R3): giusto solo per un anno intero
        return mesi == 12
    return colonna.mesi == mesi


def quota(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


# --- letture --------------------------------------------------------------------------------------------------------

def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def totali_stampati(doc_id: str) -> list[dict]:
    """L'unione dei totali stampati delle due letture, senza gli zeri, uno per `(pagina, valore)`."""
    visti: dict[tuple[int, Decimal], dict] = {}
    for f in (ANALISI / f"{doc_id}.json", ANALISI / "opus" / f"{doc_id}.json"):
        for t in (_json(f) or {}).get("totali_stampati") or []:
            try:
                v = abs(Decimal(str(t["valore"]))).quantize(_CENT)
                pag = int(t["pagina"])
            except (KeyError, TypeError, ValueError, ArithmeticError):
                continue
            if v != 0:
                visti.setdefault((pag, v), {"pagina": pag, "valore": v, "voce": t.get("voce") or ""})
    return list(visti.values())


def conti_annotati(doc_id: str) -> tuple[list[dict], dict[str, str]]:
    """I conti non totali con padre, importo e pagina, uno per conto (la prima colonna annotata); e, per codice, la
    descrizione delle righe annotate: il padre annotato è spesso solo il codice del mastro, il lettore lo nomina
    anche col suo nome («0101» = «CASSA», chiuso da «Totale CASSA:»)."""
    d = _json(ANALISI / f"{doc_id}.json") or {}
    tutti = d.get("conti") or []
    nomi: dict[str, str] = {}
    for c in tutti + (d.get("totali_stampati") or []):
        cod = norm(c.get("codice"))
        desc = c.get("descrizione") or c.get("voce")
        if cod and desc and cod not in nomi:
            nomi[cod] = desc
    visti, out = set(), []
    for c in tutti:
        if c.get("e_totale") or not c.get("padre") or not c.get("importo") or not c.get("pagina"):
            continue
        chiave = (c["pagina"], norm(c.get("codice")), norm(c.get("descrizione")))
        if chiave in visti:
            continue
        visti.add(chiave)
        out.append(c)
    return out, nomi


def periodi_veri(doc_id: str) -> list[dict]:
    d = _json(ANALISI / "verita" / f"{doc_id}.json") or {}
    return [{"fine": p.get("fine"), "mesi": mesi_del_periodo(p.get("periodo"))} for p in d.get("periodi", [])
            if re.fullmatch(r"\d{4}-\d{2}", p.get("fine") or "")]      # «?» = periodo non noto alla verità


def correzione(doc_id: str, conto: dict) -> str | None:
    for c in CORREZIONI_ANNOTAZIONE:
        if c["id"] != doc_id:
            continue
        if c["codice"] is not None and norm(conto.get("codice")) != norm(c["codice"]):
            continue
        if c["padre"] is not None and norm(conto.get("padre")) != norm(c["padre"]):
            continue
        if c["voce_non"] is not None and (conto.get("voce_di_legge") or "").startswith(c["voce_non"]):
            continue
        return c["perche"]
    return None


# --- misura di un documento -----------------------------------------------------------------------------------------

def _tolleranza(doc) -> Decimal:
    dec = [v for v in doc.profilo.decimali.values() if v is not None]
    return _UNITA if dec and not any(dec) else _CENT


def misura_totali(doc, totali: list[dict], tol: Decimal) -> dict:
    per_pagina = defaultdict(list)
    for r in doc.righe:
        if r.parte == "prospetto":
            per_pagina[r.pagina].append(r)
    ritrovati = chiusi = analisi = 0
    ruoli = {c.indice: c.ruolo for c in doc.colonne}
    mancanti, aperti = [], []
    for t in totali:
        trovate = [(r, col) for r in per_pagina[t["pagina"]] for col, imp in r.celle.items()
                   if abs(abs(imp.valore) - t["valore"]) <= tol]
        voce = {"pagina": t["pagina"], "valore": float(t["valore"]), "voce": t["voce"][:70]}
        if not trovate:
            mancanti.append(voce)
            continue
        ritrovati += 1
        if any(r.totale and r.figli.get(col) for r, col in trovate):
            chiusi += 1
        elif all(ruoli.get(col) not in _VALORI_E_MASTRI for _, col in trovate):
            analisi += 1        # ritrovato solo su una colonna di analisi o di movimenti: lì non si somma
        else:
            r, col = trovate[0]
            aperti.append({**voce, "riga": r.id, "etichetta": r.etichetta[:50], "colonna": col,
                           "ruolo": next((c.ruolo for c in doc.colonne if c.indice == col), None)})
    return {"stampati": len(totali), "ritrovati": ritrovati, "chiusi": chiusi, "solo_analisi": analisi,
            "mancanti": mancanti, "non_chiusi": aperti}


def misura_periodi(doc, veri: list[dict]) -> dict | None:
    if not veri:
        return None
    lati = defaultdict(list)
    for c in doc.colonne:
        if c.ruolo in _VALORI:
            lati[c.lato].append(c)
    basta = len(veri) == 1
    sbagliati = []
    for p in veri:
        if not lati or not all(any(periodo_giusto(c, p["fine"], p["mesi"], basta) for c in cols)
                               for cols in lati.values()):
            sbagliati.append(p)
    trovati = sorted({f"{c.lato}:{c.fine:%Y-%m}/{c.mesi}" if c.fine else f"{c.lato}:-/{c.mesi}"
                      for cols in lati.values() for c in cols})
    return {"veri": veri, "giusti": not sbagliati, "sbagliati": sbagliati, "colonne": trovati,
            "esercizi_per_lato": max((len(v) for v in lati.values()), default=0)}


def _antenati(riga, per_id: dict) -> list:
    out, visti = [], set()
    while riga.padre and riga.padre in per_id and riga.padre not in visti:
        visti.add(riga.padre)
        riga = per_id[riga.padre]
        out.append(riga)
    return out


def _riga_del_conto(conto: dict, righe: list, tol: Decimal):
    imp = abs(Decimal(str(conto["importo"])))
    cand = [r for r in righe if r.pagina == conto["pagina"] and not r.totale
            and any(abs(abs(v.valore) - imp) <= tol for v in r.celle.values())]
    if len(cand) > 1 and conto.get("codice"):
        cand = [r for r in cand if norm(r.codice) == norm(conto["codice"])] or cand
    if len(cand) > 1 and conto.get("descrizione"):
        cand = [r for r in cand if norm(conto["descrizione"])[:20] in norm(r.etichetta)] or cand
    if len(cand) > 1 and conto.get("codice"):
        cand = [r for r in cand if norm(r.codice) == norm(conto["codice"])]
    return cand[0] if len(cand) == 1 else None


def misura_mastri(doc_id: str, doc, tol: Decimal) -> dict | None:
    conti, nomi = conti_annotati(doc_id)
    if not conti:
        return None
    righe = [r for r in doc.righe if r.parte == "prospetto"]
    per_id = {r.id: r for r in doc.righe}
    st = {"annotati": len(conti), "ritrovati": 0, "stretti": 0, "tolleranti": 0, "verificati": 0,
          "verificati_giusti": 0, "verificati_sbagliati": 0, "senza_padre": 0, "esclusi": 0}
    sbagliati, esclusi = [], []
    for c in conti:
        perche = correzione(doc_id, c)
        r = _riga_del_conto(c, righe, tol)
        if perche:
            st["esclusi"] += 1
            esclusi.append({"codice": c.get("codice"), "descrizione": (c.get("descrizione") or "")[:50],
                            "importo": c["importo"], "padre_annotato": c["padre"], "perche": perche,
                            "padre_letto": per_id[r.padre].etichetta[:50] if r and r.padre in per_id else None})
            continue
        if r is None:
            continue
        st["ritrovati"] += 1
        padre = per_id.get(r.padre)
        if padre is None:
            st["senza_padre"] += 1
            sbagliati.append({"riga": r.id, "codice": c.get("codice"), "descrizione": (c.get("descrizione") or "")[:40],
                              "importo": c["importo"], "padre_annotato": c["padre"], "padre_letto": None,
                              "verificato": False})
            continue
        nomi_padre = [c["padre"]] + ([nomi[norm(c["padre"])]] if norm(c["padre"]) in nomi else [])
        annotati = {norm(n) for n in nomi_padre} - {""}
        senza = {norm(senza_numero(n)) for n in nomi_padre} - {""}
        stretto = stesso_nome(padre, annotati)
        tollerante = stretto
        if not tollerante:
            # granularità: si sale per i «Totale …» (esigibili entro, 7) per servizi…) fino al primo antenato che
            # non è un totale; vale uno qualunque di quei totali col nome giusto, o quell'antenato
            for a in [padre] + _antenati(padre, per_id):
                if stesso_totale(a, annotati | senza) or (not e_un_totale(a.etichetta) and stesso_nome(a, annotati)):
                    tollerante = True
                if not e_un_totale(a.etichetta):
                    break
        st["stretti"] += stretto
        st["tolleranti"] += tollerante
        if r.padre_verificato:
            st["verificati"] += 1
            st["verificati_giusti" if tollerante else "verificati_sbagliati"] += 1
        if not tollerante:
            sbagliati.append({"riga": r.id, "codice": c.get("codice"), "descrizione": (c.get("descrizione") or "")[:40],
                              "importo": c["importo"], "padre_annotato": c["padre"],
                              "padre_letto": f"{padre.codice} {padre.etichetta}".strip()[:60],
                              "verificato": r.padre_verificato})
    return {**st, "sbagliati": sbagliati, "esclusi_elenco": esclusi}


def misura_documento(d: dict) -> dict:
    out = {"id": d["id"], "tipologia": d["tipologia"], "path": d["path"]}
    if d["tipologia"].split("/")[0] in A_PARTE:
        out["a_parte"] = "scansione"
        return out
    fp = CORPUS / d["path"]
    if not fp.exists():
        out["errore"] = "file assente"
        return out
    try:
        doc = leggi_pdf(str(fp))
    except Exception as e:              # la misura non si ferma su un documento
        out["errore"] = repr(e)
        return out
    tol = _tolleranza(doc)
    out["tolleranza"] = float(tol)
    out["tipo"] = doc.profilo.tipo
    out["contrapposto"] = doc.contrapposto
    out["totali"] = misura_totali(doc, totali_stampati(d["id"]), tol)
    out["periodi"] = misura_periodi(doc, periodi_veri(d["id"]))
    out["mastri"] = misura_mastri(d["id"], doc, tol)
    return out


# --- sintesi --------------------------------------------------------------------------------------------------------

def _somma(regs: list[dict]) -> dict:
    s = defaultdict(int)
    for r in regs:
        t = r.get("totali")
        if t:
            s["doc"] += 1
            s["stampati"] += t["stampati"]
            s["ritrovati"] += t["ritrovati"]
            s["chiusi"] += t["chiusi"]
            s["solo_analisi"] += t["solo_analisi"]
        p = r.get("periodi")
        if p:
            s["con_periodi"] += 1
            s["periodi_giusti"] += p["giusti"]
        m = r.get("mastri")
        if m:
            s["con_conti"] += 1
            for k in ("ritrovati", "stretti", "tolleranti", "verificati", "verificati_sbagliati", "senza_padre",
                      "esclusi"):
                s["conti_" + k] += m[k]
    return dict(s)


def _pct(n, d) -> str:
    return "-" if not d else f"{100 * n / d:5.1f}%"


def sintesi(registri: list[dict]) -> tuple[dict, list[str]]:
    misurati = [r for r in registri if "totali" in r]
    per_tip = defaultdict(list)
    for r in misurati:
        per_tip[r["tipologia"]].append(r)
    tabella = {"totale": _somma(misurati), **{t: _somma(v) for t, v in sorted(per_tip.items())}}
    righe = [f"{'tipologia':30} {'doc':>4} {'ritrovati':>10} {'chiusi':>8} {'chiusi v.':>9} {'periodi':>9} "
             f"{'mastri str':>11} {'mastri tol':>11} {'verif.':>8}"]
    for nome, s in tabella.items():
        righe.append(
            f"{nome:30} {s.get('doc', 0):>4} {_pct(s.get('ritrovati', 0), s.get('stampati', 0)):>10} "
            f"{_pct(s.get('chiusi', 0), s.get('ritrovati', 0)):>8} "
            f"{_pct(s.get('chiusi', 0), s.get('ritrovati', 0) - s.get('solo_analisi', 0)):>9} "
            f"{s.get('periodi_giusti', 0):>4}/{s.get('con_periodi', 0):<4} "
            f"{_pct(s.get('conti_stretti', 0), s.get('conti_ritrovati', 0)):>11} "
            f"{_pct(s.get('conti_tolleranti', 0), s.get('conti_ritrovati', 0)):>11} "
            f"{_pct(s.get('conti_verificati', 0), s.get('conti_ritrovati', 0)):>8}")
    a_parte = [r["id"] for r in registri if r.get("a_parte")]
    errori = [(r["id"], r["errore"]) for r in registri if r.get("errore")]
    righe.append(f"a parte (scansioni): {len(a_parte)} {a_parte}; errori: {errori}")
    return tabella, righe


def rapporto_md(etichetta: str, registri: list[dict], righe_sintesi: list[str]) -> str:
    out = [f"# Lettore di righe sul campione — {etichetta}", "", "```", *righe_sintesi, "```", "",
           "## Per documento", ""]
    for r in registri:
        if "totali" not in r:
            out.append(f"### {r['id']} ({r['tipologia']}) — {r.get('a_parte') or r.get('errore')}")
            out.append("")
            continue
        t, p, m = r["totali"], r["periodi"], r["mastri"]
        testa = (f"### {r['id']} ({r['tipologia']}) — totali {t['ritrovati']}/{t['stampati']} ritrovati, "
                 f"{t['chiusi']}/{t['ritrovati']} chiusi")
        if p:
            testa += f"; periodi {'giusti' if p['giusti'] else 'SBAGLIATI'} {p['colonne']}"
        if m:
            testa += (f"; mastri {m['tolleranti']}/{m['ritrovati']} (stretti {m['stretti']}, "
                      f"verificati {m['verificati']})")
        out += [testa, ""]
        if p and not p["giusti"]:
            out.append(f"- periodi veri {[(x['fine'], x['mesi']) for x in p['veri']]}, colonne {p['colonne']}")
        for x in t["mancanti"]:
            out.append(f"- non ritrovato p{x['pagina']} {x['valore']:,.2f} «{x['voce']}»")
        for x in t["non_chiusi"]:
            out.append(f"- non chiuso p{x['pagina']} {x['valore']:,.2f} «{x['voce']}» su {x['riga']} "
                       f"«{x['etichetta']}» col {x['colonna']} ({x['ruolo']})")
        if m:
            for x in m["sbagliati"]:
                out.append(f"- mastro {x['riga']} {x['codice'] or ''} «{x['descrizione']}» {x['importo']}: annotato "
                           f"«{x['padre_annotato']}», letto «{x['padre_letto']}»{' (verificato)' if x['verificato'] else ''}")
            for x in m["esclusi_elenco"]:
                out.append(f"- annotazione da correggere: {x['codice'] or ''} «{x['descrizione']}» {x['importo']}, "
                           f"annotato «{x['padre_annotato']}», letto «{x['padre_letto']}»: {x['perche']}")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--etichetta", required=True)
    ap.add_argument("--solo", default="", help="id separati da virgola")
    args = ap.parse_args()
    solo = {s.strip() for s in args.solo.split(",") if s.strip()} or None

    docs = json.loads(CAMPIONE.read_text(encoding="utf-8"))["documenti"]
    registri = [misura_documento(d) for d in docs if not solo or d["id"] in solo]
    tabella, righe_sintesi = sintesi(registri)

    cartella = USCITA / args.etichetta
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / "righe.json").write_text(json.dumps({"sintesi": tabella, "documenti": registri}, ensure_ascii=False,
                                                    indent=1, default=str), encoding="utf-8")
    (cartella / "righe.md").write_text(rapporto_md(args.etichetta, registri, righe_sintesi), encoding="utf-8")
    print("\n".join(righe_sintesi))
    print(f"-> {cartella}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
