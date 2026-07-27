"""Diagnostica SINONIMIA: quali etichette del documento il sistema NON riconosce.

Per un PDF stampa:
  1. la rotta scelta dal classificatore;
  2. i totali dichiarati che il preflight riesce a leggere (`_declared_control_totals`);
  3. quali righe/etichette il resolver semantico (`iv_cee_hierarchy.resolve`) NON risolve,
     con la massa in euro che quelle etichette portano con sé.

Serve a distinguere due cause diverse di "il bilancio non quadra":
  (a) l'LLM non capisce la voce  ->  le etichette risolvono, ma i numeri sono sbagliati;
  (b) un gate DETERMINISTICO non riconosce la GRAFIA  ->  etichette irrisolte / totale
      dichiarato non letto, e un'estrazione corretta viene comunque rifiutata.

CLI:  python tests/_label_diag.py "<file.pdf>"
"""
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import fitz  # noqa: E402

from importers.bilancio_classifier import classify_bilancio  # noqa: E402
from importers.iv_cee_hierarchy import resolve  # noqa: E402
from importers.pdf_extractor_llm import _declared_control_totals  # noqa: E402

# riga "etichetta ......... 1.234.567,89"
_AMOUNT_RE = re.compile(r"-?\(?\d{1,3}(?:[.\s]\d{3})*,\d{2}\)?|-?\d+,\d{2}")


def _label_of(line: str) -> str:
    s = _AMOUNT_RE.sub(" ", line)
    s = re.sub(r"[.…]{3,}", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .-|")
    return s


def diag(path: str, max_pages: int = 14) -> None:
    doc = fitz.open(path)
    text = "".join(p.get_text() for p in doc[:max_pages])
    full = "".join(p.get_text() for p in doc)
    doc.close()

    c = classify_bilancio(file_path=path, text=text)
    print(f"FILE   : {os.path.basename(path)}")
    print(f"ROTTA  : area={c.macro_area} route={c.route} sub={c.subcategory} conf={c.confidence}")
    print(f"REASON : {c.reason[:160]}")

    try:
        dt = _declared_control_totals(full)
    except Exception as exc:
        dt = f"ERRORE: {exc}"
    print(f"TOTALI DICHIARATI LETTI: {dt}")

    unresolved, resolved = Counter(), Counter()
    for line in full.splitlines():
        if not _AMOUNT_RE.search(line):
            continue
        lab = _label_of(line)
        if len(lab) < 4 or not re.search(r"[A-Za-z]{3}", lab):
            continue
        hit = resolve(lab, side=None) or resolve(lab, side="attivo") or resolve(lab, side="passivo")
        (resolved if hit else unresolved)[lab[:70]] += 1

    print(f"\nETICHETTE RISOLTE dal resolver : {len(resolved)} distinte")
    print(f"ETICHETTE NON RISOLTE          : {len(unresolved)} distinte")
    print("\n--- prime 40 NON risolte (grafie che il sistema non riconduce a una voce) ---")
    for lab, n in unresolved.most_common(40):
        print(f"  x{n:<3} {lab}")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        diag(p)
        print("\n" + "=" * 100 + "\n")
