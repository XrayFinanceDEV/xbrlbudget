"""Mastri gerarchici a codici puntati («bilancio 4 sezioni»).

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import re
from decimal import Decimal
from typing import List, Tuple
from importers.situazione_contabile.comune import (
    _parse_amount,
)
from importers.situazione_contabile.best_effort import (
    _BE_AMT_RE, _be_cluster_physical_rows,
)


# ---------------------------------------------------------------------------
# Hierarchical-mastri reconstruction (dotted "BILANCIO 4 SEZIONI" family)
# ---------------------------------------------------------------------------
# A whole sub-family of trial balances (Sistemi/DEPI "bilancio 4 sezioni",
# code 03.01.07 / 3 / 15 / 102) lists, for every IV-CEE voce, the LEVEL-1 mastro
# with its already-correct subtotal (e.g. "05 IMMOBILIZZAZIONI MATERIALI
# 1.293.041,01"), then its dotted children. The generic best-effort parser
# normalises the code to digits and the DEEPEST detail rows (printed with a
# truncated single-digit code, e.g. a finance instalment shown as "23") then
# COLLIDE with a mastro number and inflate it → large sp09/sp16 plug ("QUADRATURA
# MASCHERATA"). Anchoring instead on the level-1 mastri (taken in DOCUMENT ORDER,
# so a no-separator code is a mastro only when its own dotted children follow it)
# makes the attivo reconcile to the declared total exactly and the current-year
# result emerge as the attivo/passivo gap (which equals ricavi-costi). This runs
# ONLY as a rescue when the best-effort result is masked, and its output is kept
# ONLY when it reconciles (gross attivo vs declared total AND SP gap vs CE result),
# so it can never regress a file the best-effort already balances.
_DOTTED_HIER_RE = re.compile(r'\b\d{1,3}\.\d{2}\.\d{2,3}\b')

def is_dotted_hierarchical(text: str) -> bool:
    """True when the document is dominated by dotted hierarchical account codes
    (NN.NN.NN), the signature of the 'bilancio 4 sezioni' mastri layout."""
    return len(_DOTTED_HIER_RE.findall(text)) >= 12

def _hier_canon(raw: str) -> str:
    """Canonicalise a hierarchical code to dotted form: '3 / 15 / 102' -> '3.15.102',
    '05.03.05' unchanged. Depth = number of '.'-separated segments."""
    s = raw.replace('/', '.')
    s = re.sub(r'\.+', '.', s).strip('.')
    return s

def _hier_collect(words, lo: float, hi: float) -> List[Tuple[str, str, Decimal]]:
    """Collect (canon_code, desc_upper, amount) rows in x-band [lo, hi), preserving
    the hierarchical code structure and DOCUMENT (top-to-bottom) order."""
    # righe fisiche per sovrapposizione verticale, non per round(y/2): codice e importo in
    # font diversi finivano in due righe e il conto, rimasto senza importo, spariva
    # (budget_703: "336 ALTRI COSTI MANO D'OPERA 886,35", "340 ACQUA 393,46")
    out = []
    for riga in _be_cluster_physical_rows(words, lo, hi):
        toks = [w[4] for w in sorted(riga, key=lambda w: w[0])]
        i, code_toks = 0, []
        while i < len(toks) and re.match(r'^[\d./*]+$', toks[i]) and not _BE_AMT_RE.match(toks[i]):
            code_toks.append(toks[i])
            i += 1
        if not code_toks:
            continue
        cc = _hier_canon(''.join(code_toks))
        if not cc or not cc[0].isdigit():
            continue
        rest = toks[i:]
        amts = [_parse_amount(t) for t in rest if _BE_AMT_RE.match(t)]
        if not amts:
            continue
        desc = ' '.join(t for t in rest if not _BE_AMT_RE.match(t)).upper().strip()
        out.append((cc, desc, amts[-1]))
    return out

def _hier_split_ai_codici(words, split: float, width: float) -> float:
    """La separazione fra le due colonne, rimessa sull'inizio della colonna dei codici di
    destra (la x piu' frequente a cui cominciano i codici numerici nella meta' destra), ma
    solo quando fra la stima e quell'inizio ci sono soltanto importi della colonna sinistra
    (stima troppo a sinistra: un importo corto allineato a destra, "886,35" fra x 257 e 281,
    aveva il centro oltre 268 e finiva nella colonna accanto) o soltanto codici della colonna
    destra (stima troppo a destra: "37", "755" a x 294 finivano a sinistra). budget_703,
    pagine 2 e 1. Qualunque altra parola nel mezzo: la stima resta quella."""
    from collections import Counter
    if split is None:
        return split
    codice = re.compile(r'\d{1,3}(?:[./]\d+)*')
    xs = Counter(round(w[0]) for w in words if codice.fullmatch(w[4]) and w[0] > width * 0.35)
    if not xs:
        return split
    x_codici, volte = xs.most_common(1)[0]
    if volte < 3:
        return split
    nuovo = x_codici - 1
    lo, hi = sorted((split, nuovo))
    # solo il corpo dei conti: l'intestazione di pagina ("Pagina: 2 di 4") non conta
    y_corpo = min(w[1] for w in words if codice.fullmatch(w[4]) and abs(w[0] - x_codici) <= 2)
    nel_mezzo = [w for w in words if lo <= (w[0] + w[2]) / 2 < hi and w[1] >= y_corpo - 2]
    if nuovo > split and all(_BE_AMT_RE.match(w[4]) and w[2] < x_codici for w in nel_mezzo):
        return nuovo
    if nuovo < split and all(codice.fullmatch(w[4]) and abs(w[0] - x_codici) <= 2
                             for w in nel_mezzo):
        return nuovo
    return split

def _hier_lvl1(rows: List[Tuple[str, str, Decimal]]) -> List[Tuple[str, str, Decimal]]:
    """Level-1 mastri in document order: a no-'.' code is a mastro only when its OWN
    dotted children (code + '.') follow it before the next no-'.' code. This rejects
    the truncated deep-detail leaves whose code collides with a real mastro number."""
    n = len(rows)
    res = []
    for i, (c, d, a) in enumerate(rows):
        if '.' in c or 'TOTALE' in d or 'PAREGGIO' in d:
            continue
        is_mastro = False
        for j in range(i + 1, n):
            cj = rows[j][0]
            if cj.startswith(c + '.'):
                is_mastro = True
                break
            if '.' not in cj:
                break
        if not is_mastro:
            is_mastro = _hier_mastro_per_somma(rows, i)
        if is_mastro:
            res.append((c, d, a))
    # Un mastro senza conti sotto ("19 CLIENTI", "10 FORNITORI", budget_703) vale da se':
    # stesso livello di codice dei mastri riconosciuti per somma, e nessun codice piu' lungo
    # che lo segua. Il totale stampato, in _hier_reconstruct, decide se la lettura regge.
    # Solo senza codici a punti: li' la gerarchia la dicono i punti.
    lunghezze = {len(c) for c, _d, _a in res}
    if res and len(lunghezze) == 1 and not any('.' in c for c, _d, _a in rows):
        livello = lunghezze.pop()
        scelti = {(c, d, a) for c, d, a in res}
        res = []
        for i, (c, d, a) in enumerate(rows):
            con_figli = i + 1 < n and len(rows[i + 1][0]) > len(c)
            if (c, d, a) in scelti or (len(c) == livello and not con_figli
                                       and 'TOTALE' not in d and 'PAREGGIO' not in d):
                res.append((c, d, a))
    return res

def _hier_mastro_per_somma(rows: List[Tuple[str, str, Decimal]], i: int) -> bool:
    """Un codice senza punti i cui conti non ne portano il prefisso (budget_703, "BILANCIO
    CONTABILE": mastro "85 ONERI FINANZIARI", conti "070", "075", ... che si ripetono sotto
    mastri diversi). La lunghezza del codice e' solo l'ipotesi: e' un mastro quando le righe
    che lo seguono, con codici piu' lunghi e fino al codice successivo non piu' lungo del
    suo, ne ricostruiscono l'importo al centesimo. Una sezione ("1 ATTIVITA'") non lo e':
    sotto ha mastri e conti insieme, la somma e' doppia."""
    c, d, a = rows[i]
    figli = []
    for cj, dj, aj in rows[i + 1:]:
        if '.' in cj or 'TOTALE' in dj or 'PAREGGIO' in dj or len(cj) <= len(c):
            break
        figli.append(aj)
    return bool(figli) and abs(sum(figli, Decimal('0')) - a) <= Decimal('0.01')

def _is_prior_result_caption(desc_upper: str) -> bool:
    """True for a PRIOR-year result caption ("Utile esercizio precedente", "Utili
    portati a nuovo").

    Trial balances frequently do NOT consolidate the previous year's result into
    the capital/reserve accounts: it is printed as its own row — often CODE-LESS,
    in the SP footer next to the totals — and belongs to patrimonio netto (utili
    portati a nuovo). It must be told apart from the CURRENT period result, which
    is the balancing figure and is derived from the Attivo/Passivo gap.
    """
    d = desc_upper
    if 'TOTALE' in d or 'PAREGGIO' in d:
        return False
    # "Eccedenza esercizio precedente" (Unicarton 31/08/2026): la stessa riga col nome
    # che il gestionale da' al saldo, accanto a "Eccedenza (Utile)" del periodo.
    # 'RISULT' copre anche l'abbreviazione dei gestionali ("RISULT. D'ESERCIZIO PROVV. ANNO
    # PRECEDENTE", budget_1439).
    if not any(k in d for k in ('UTILE', 'UTILI', 'PERDITA', 'PERDITE', 'RISULT',
                                'ECCEDENZA')):
        return False
    return 'PRECEDENT' in d or 'PORTAT' in d

def _hier_prior_result(words, lo: float, hi: float) -> Decimal:
    """Signed prior-year result printed WITHOUT an account code in x-band [lo, hi).

    Only code-less rows are collected: a prior result that carries a code is
    already inside a level-1 mastro (e.g. "23 CAPITALE E RISERVE") and counting
    it again would double it.  The sign follows the caption (perdita -> negative),
    so the caller can add the value to patrimonio netto on either column.
    """
    total = Decimal('0')
    for row_words in _be_cluster_physical_rows(words, lo, hi):
        # Lo strato OCR di una scansione legge come caratteri le linee di sottolineatura
        # davanti all'importo ("___173.463,79", Unicarton 31/08/2026).
        toks = [w[4].strip().lstrip('_—|') for w in sorted(row_words, key=lambda w: w[0])]
        toks = [t for t in toks if t]
        # a leading account code means the row is already part of a mastro
        if toks and re.match(r'^[\d./*]+$', toks[0]) and not _BE_AMT_RE.match(toks[0]):
            continue
        caption = ' '.join(t for t in toks if not _BE_AMT_RE.fullmatch(t)).upper()
        if not _is_prior_result_caption(caption):
            continue
        amounts = [_parse_amount(t) for t in toks if _BE_AMT_RE.fullmatch(t)]
        if not amounts:
            continue
        amount = abs(amounts[-1])
        if 'PERDIT' in caption:
            amount = -amount
        total += amount
    return total

def _hier_prior_caption_senza_importo(words) -> bool:
    """Una riga senza codice con la didascalia del risultato precedente e nessun importo
    (budget_1410: l'OCR ha perso la cella di «Eccedenza esercizio precedente»)."""
    for row_words in _be_cluster_physical_rows(words, -1e9, 1e9):
        toks = [w[4].strip().lstrip('_—|') for w in sorted(row_words, key=lambda w: w[0])]
        toks = [t for t in toks if t]
        if not toks or any(_BE_AMT_RE.fullmatch(t) for t in toks):
            continue
        if re.match(r'^[\d./*]+$', toks[0]):
            continue
        if _is_prior_result_caption(' '.join(toks).upper()):
            return True
    return False
