"""Copertura del resolver semantico sull'intero corpus.

Domanda a cui risponde: *quante etichette reali, e quanta massa in euro, il sistema
NON sa ricondurre a una voce IV-CEE?* — indipendentemente dal singolo file.

Scorre i PDF di una o piu' cartelle, estrae le righe "etichetta ... importo", e per
ogni etichetta chiede a `iv_cee_hierarchy.resolve` se la riconosce. Produce:
  - % di righe e % di massa NON risolte;
  - classifica delle etichette non risolte per numero di DOCUMENTI in cui compaiono
    (le prime della lista sono i buchi generali del dizionario, non casi isolati).

CLI:  python tests/_label_coverage.py Test/successSecondo Test/june_sample/success ...
"""
import glob
import os
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import fitz  # noqa: E402

from importers.iv_cee_hierarchy import resolve  # noqa: E402

_AMOUNT_RE = re.compile(r"-?\(?\d{1,3}(?:[.\s]\d{3})*,\d{2}\)?|-?\d+,\d{2}")
_NOISE = re.compile(r"^(pag|pagina|data|ditta|cod|codice fiscale|partita iva|\d+)$", re.I)


def _to_dec(tok: str) -> Decimal:
    tok = tok.strip().replace("(", "-").replace(")", "").replace(" ", "")
    try:
        return abs(Decimal(tok.replace(".", "").replace(",", ".")))
    except InvalidOperation:
        return Decimal(0)


def _label_of(line: str) -> str:
    s = _AMOUNT_RE.sub(" ", line)
    s = re.sub(r"[.…]{3,}", " ", s)
    s = re.sub(r"^\s*[\d/.\-]{2,12}\s+", "", s)      # codice di conto in testa
    return re.sub(r"\s+", " ", s).strip(" .-|")


def _visual_lines(path: str, ytol: float = 2.5):
    """Ricostruisce le righe VISIVE (etichetta + importo sulla stessa riga stampata).

    `page.get_text()` su layout a colonne separa spesso l'etichetta dall'importo su
    righe logiche diverse: contarle cosi' sottostima enormemente le voci. Qui le
    parole vengono raggruppate per coordinata y, come fanno i parser di produzione.
    """
    out = []
    doc = fitz.open(path)
    try:
        for page in doc:
            words = page.get_text("words")  # (x0,y0,x1,y1,word,block,line,word_no)
            buckets = defaultdict(list)
            for w in words:
                buckets[round(w[1] / ytol)].append(w)
            for key in sorted(buckets):
                ws = sorted(buckets[key], key=lambda w: w[0])
                out.append(" ".join(w[4] for w in ws))
    finally:
        doc.close()
    return out


def scan(paths):
    rows = mass = Decimal(0), Decimal(0)
    n_rows = n_unres = 0
    mass_tot = Decimal(0)
    mass_unres = Decimal(0)
    per_doc = defaultdict(set)      # etichetta non risolta -> set di documenti
    freq = Counter()
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += [f for f in sorted(glob.glob(os.path.join(p, "*")))
                      if f.lower().endswith(".pdf")]
        elif p.lower().endswith(".pdf"):
            files.append(p)

    for f in files:
        try:
            lines = _visual_lines(f)
        except Exception:
            continue
        base = os.path.basename(f)
        for line in lines:
            amounts = _AMOUNT_RE.findall(line)
            if not amounts:
                continue
            lab = _label_of(line)
            if len(lab) < 4 or not re.search(r"[A-Za-z]{3}", lab) or _NOISE.match(lab):
                continue
            val = max((_to_dec(a) for a in amounts), default=Decimal(0))
            n_rows += 1
            mass_tot += val
            hit = (resolve(lab, side=None) or resolve(lab, side="attivo")
                   or resolve(lab, side="passivo"))
            if not hit:
                n_unres += 1
                mass_unres += val
                key = re.sub(r"\d", "#", lab.lower())[:60]
                per_doc[key].add(base)
                freq[key] += 1

    print(f"documenti analizzati : {len(files)}")
    print(f"righe con importo    : {n_rows:,}")
    print(f"righe NON risolte    : {n_unres:,} ({100 * n_unres / max(1, n_rows):.1f}%)")
    print(f"massa totale righe   : {mass_tot:,.0f}")
    print(f"massa NON risolta    : {mass_unres:,.0f} "
          f"({100 * float(mass_unres) / max(1.0, float(mass_tot)):.1f}%)")
    print("\n--- etichette NON risolte piu' DIFFUSE (n. documenti / n. occorrenze) ---")
    for key, docs in sorted(per_doc.items(), key=lambda kv: (-len(kv[1]), -freq[kv[0]]))[:60]:
        print(f"  doc={len(docs):<3} occ={freq[key]:<5} {key}")


if __name__ == "__main__":
    scan(sys.argv[1:])
