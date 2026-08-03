"""Copertura del riconoscimento etichette, misurata PER SPAZIO SEMANTICO.

La misura precedente ("58,3% delle righe non risolte") era **sovrastimata e non
confrontabile**: metteva in un unico denominatore voci civilistiche, conti del
piano dei conti, marcatori di totale/sezione e prosa di nota integrativa, e
interrogava solo `iv_cee_hierarchy.resolve` — che per progetto copre SOLO le voci
legali. Accettare o rifiutare un fix su quel numero non ha senso.

Qui ogni riga con importo viene prima assegnata a uno di quattro insiemi, poi
interrogata nello spazio corretto:

  legal    riga con path civilistico (B.II.1.a) o voce di legge  -> spazio "voce"
  account  riga con codice di conto (DEPI/8-digit/dotted/...)    -> spazio "conto"
  marker   totali, sezioni, intestazioni di colonna              -> spazio "marker"
  other    prosa di nota integrativa, intestazioni documento     -> ESCLUSA dal denominatore

`other` e' il grosso della sovrastima: righe come "i ricavi caratteristici
crescono di circa il 18%" portano un importo ma non sono voci di bilancio.

CLI:  python tests/_label_coverage.py <cartelle o pdf...>
      python tests/_label_coverage.py --top 40 Test/june_sample/success
"""
import argparse
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

_AMOUNT_RE = re.compile(r"-?\(?\d{1,3}(?:[.\s]\d{3})*,\d{2}\)?|-?\d+,\d{2}")

# --- riconoscimento dell'INSIEME di appartenenza (non della voce) ---------------

# path civilistico: B.II.1.a) / C.II.5 quater) / A.VIII / D.1.2.b)
_LEGAL_PATH_RE = re.compile(
    r"^\s*[A-E]\s*[.)]?\s*(?:[IVX]{1,4}|\d{1,2})"
    r"(?:\s*[.)]\s*[0-9a-z]+|\s+(?:bis|ter|quater|quinquies))*\s*[.)]?",
    re.I)
# codice di conto: DEPI 03/35/005, 8-digit, dotted 03.01.07, BILAGRA 123.45678,
# TeamSystem 12/1234/1234, single-column 6-digit
_ACCOUNT_CODE_RE = re.compile(
    r"^\s*(?:\d{2}/\d{2,4}/\d{3,4}|\d{8}\b|\d{1,3}(?:\.\d{2,5}){1,3}\b|\d{6}\b)")
_MARKER_RE = re.compile(
    r"^\s*(?:\*+\s*)?(?:tot(?:ale|ali)?\b|t\s+o\s+t\s+a\s+l\s+e"
    r"|a\s*t\s*t\s*i\s*v\s*i\s*t|p\s*a\s*s\s*s\s*i\s*v\s*i\s*t"
    r"|stato\s+patrimoniale|conto\s+economico|differenza\b|scost"
    r"|utile\b|perdita\b|risultato\b|sbilancio\b|pareggio\b)",
    re.I)
# prosa: frasi lunghe, verbi, congiunzioni — non sono voci di bilancio
_PROSE_RE = re.compile(
    r"\b(?:che|come|sono|viene|vengono|essere|stato|nonche|pari a|circa|rispetto"
    r"|ammonta|ammontano|calcolat|utilizzabil|compensazione|esercizio precedente"
    r"|si\s+e\b|e'\s+stat)\b", re.I)


def classify_row_set(label: str, code: str) -> str:
    """A quale insieme appartiene questa riga? (non: quale voce e')."""
    # Il PATH CIVILISTICO ha la precedenza sul codice di conto: una riga come
    # "4010 C.II.1) Verso clienti" e' una VOCE DI LEGGE stampata con accanto il
    # codice del gestionale. Testare prima il codice la mandava nell'insieme
    # 'account', quindi la si interrogava nello spazio sbagliato — 1.668 righe del
    # corpus, che e' l'intera differenza fra le due misure.
    try:
        from importers.label_semantics import parse_label
        # il codice del gestionale in testa (4010, 03/35/005) non e' sempre
        # riconosciuto da _ACCOUNT_CODE_RE: toglierlo prima di cercare il path
        bare = re.sub(r"^\s*[\d/.\-]{1,12}\s+", "", label)
        if parse_label(bare).path_hint or parse_label(label).path_hint:
            return "legal"
    except Exception:
        pass
    if _MARKER_RE.match(label):
        return "marker"
    if code and _ACCOUNT_CODE_RE.match(code):
        return "account"
    if _LEGAL_PATH_RE.match(label):
        return "legal"
    words = label.split()
    if len(words) > 9 or _PROSE_RE.search(label):
        return "other"                      # prosa di nota integrativa
    if len(words) <= 6 and re.search(r"[A-Za-z]{4}", label):
        return "account"                    # voce senza codice: conto o voce breve
    return "other"


def _to_dec(tok: str) -> Decimal:
    tok = tok.strip().replace("(", "-").replace(")", "").replace(" ", "")
    try:
        return abs(Decimal(tok.replace(".", "").replace(",", ".")))
    except InvalidOperation:
        return Decimal(0)


def _split_code(line: str):
    """Separa un eventuale codice di conto in testa dalla descrizione."""
    m = _ACCOUNT_CODE_RE.match(line)
    if m:
        return m.group(0).strip(), line[m.end():].strip(" .-|")
    return "", line.strip(" .-|")


def _label_of(line: str):
    s = _AMOUNT_RE.sub(" ", line)
    s = re.sub(r"[.…]{3,}", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .-|")
    return _split_code(s)


def _visual_lines(path: str, ytol: float = 2.5):
    """Righe VISIVE: `get_text()` su layout a colonne separa spesso l'etichetta
    dall'importo su righe logiche diverse. Qui si raggruppa per coordinata y,
    come fanno i parser di produzione."""
    out = []
    doc = fitz.open(path)
    try:
        for page in doc:
            buckets = defaultdict(list)
            for w in page.get_text("words"):
                buckets[round(w[1] / ytol)].append(w)
            for key in sorted(buckets):
                ws = sorted(buckets[key], key=lambda w: w[0])
                out.append(" ".join(w[4] for w in ws))
    finally:
        doc.close()
    return out


# --- interrogazione del riconoscitore ------------------------------------------

def _resolver_for(space):
    """Usa il motore semantico (Piano 05) se c'e', altrimenti il vecchio resolve.

    Cosi' la stessa metrica misura il PRIMA e il DOPO senza cambiare strumento.
    """
    # nome dell'INSIEME misurato -> nome dello SPAZIO del motore semantico
    space_name = {"legal": "voce", "account": "conto", "marker": "marker"}[space]
    try:
        if os.environ.get("LABEL_COVERAGE_LEGACY"):
            raise ImportError("forzato il resolver legacy per il confronto")
        from importers.label_semantics import classify_label
        return lambda lab, side: classify_label(lab, space=space_name, side=side)
    except Exception:
        from importers.iv_cee_hierarchy import resolve
        if space == "marker":
            return lambda lab, side: None       # il vecchio resolver non ha marker
        return lambda lab, side: (resolve(lab, side=None) or resolve(lab, side="attivo")
                                  or resolve(lab, side="passivo"))


def scan(paths, top=40):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += [f for f in sorted(glob.glob(os.path.join(p, "**", "*"), recursive=True))
                      if f.lower().endswith(".pdf")]
        elif p.lower().endswith(".pdf"):
            files.append(p)

    resolvers = {s: _resolver_for(s) for s in ("legal", "account", "marker")}
    space_of = {"legal": "voce", "account": "conto", "marker": "marker"}
    rows = defaultdict(lambda: [0, 0])            # insieme -> [totali, irrisolte]
    mass = defaultdict(lambda: [Decimal(0), Decimal(0)])
    per_doc = defaultdict(lambda: defaultdict(set))
    freq = defaultdict(Counter)

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
            code, lab = _label_of(line)
            if len(lab) < 3 or not re.search(r"[A-Za-z]{3}", lab):
                continue
            group = classify_row_set(lab, code)
            if group == "other":
                continue                          # fuori dal denominatore, per progetto
            val = max((_to_dec(a) for a in amounts), default=Decimal(0))
            rows[group][0] += 1
            mass[group][0] += val
            hit = None
            for side in (None, "attivo", "passivo"):
                hit = resolvers[group](lab, side)
                if hit:
                    break
            if not hit:
                rows[group][1] += 1
                mass[group][1] += val
                key = re.sub(r"\d", "#", lab.lower())[:60]
                per_doc[group][key].add(base)
                freq[group][key] += 1

    print(f"documenti analizzati : {len(files)}")
    print(f"resolver interrogato : {'label_semantics' if _has_engine() else 'iv_cee_hierarchy.resolve (legacy)'}")
    print(f"\n{'SPAZIO':<10} {'righe':>7} {'irrisolte':>10} {'%':>6}   {'massa':>16} {'% massa':>8}")
    for group in ("legal", "account", "marker"):
        tot, unres = rows[group]
        if not tot:
            continue
        mt, mu = mass[group]
        print(f"{group:<10} {tot:>7,} {unres:>10,} {100*unres/tot:>5.1f}%   "
              f"{float(mt):>16,.0f} {100*float(mu)/float(mt or 1):>7.1f}%")

    for group in ("marker", "legal", "account"):
        if not per_doc[group]:
            continue
        print(f"\n--- {group}: etichette NON risolte piu' DIFFUSE (n. documenti) ---")
        for key, docs in sorted(per_doc[group].items(),
                                key=lambda kv: (-len(kv[1]), -freq[group][kv[0]]))[:top]:
            print(f"  doc={len(docs):<3} occ={freq[group][key]:<5} {key}")


def _has_engine() -> bool:
    try:
        import importers.label_semantics  # noqa: F401
        return True
    except Exception:
        return False


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    scan(a.paths, a.top)
