"""Nettatura dei contro-conti (fondi ammortamento, IVA) dopo l'estrazione.

Spostato da importers/situazione_contabile_parser.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import fitz
import logging
import re
from decimal import Decimal
from functools import partial
from typing import Dict, NamedTuple, Optional
from importers.situazione_contabile.fondi import (
    _fondo_is_immat, _is_fondo_aggregate, _is_fondo_amm, _is_fondo_immat_aggregate, _is_fondo_svalut_immob,
)
from importers.situazione_contabile.comune import (
    _parse_amount,
)
from importers.situazione_contabile.regole import (
    _classify_sp_attivo,
)
from importers.situazione_contabile.best_effort import (
    _be_collect_side, _be_split,
)
from importers.situazione_contabile.mastri_gerarchici import (
    _hier_canon,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.situazione_contabile_parser")


# ---------------------------------------------------------------------------
# Contra-netting overlay (spec docs/superpowers/specs/2026-07-06-contra-netting-
# overlay-design.md): deterministic post-extraction netting of fondi ammortamento
# (+ conservative IVA offset) on the CHOSEN route-C candidate, whatever extractor
# produced it. Pure, no LLM; no-op unless the scan self-validates against the
# document's own declared gross total.
# ---------------------------------------------------------------------------

class ContraScan(NamedTuple):
    gross_sp02: Decimal      # attivo-side immobilizzazioni immateriali (gross)
    gross_sp03: Decimal      # attivo-side immobilizzazioni materiali (gross)
    attivo_total: Decimal    # FULL attivo-side sum, fondi excluded (gate anchor)
    fondi_immat: Decimal     # fondi ammortamento immateriali (either side)
    fondi_mat: Decimal       # fondi ammortamento materiali (either side)
    iva_credito: Decimal     # IVA lines on the attivo side
    iva_debito: Decimal      # IVA lines on the passivo side
    fondi_att: Decimal       # fondi mass found on the ATTIVO side (already-net docs)
    anchor_sp02: Optional[Decimal]  # printed IMMOBILIZZAZIONI IMMATERIALI subtotal
    anchor_sp03: Optional[Decimal]  # printed IMMOBILIZZAZIONI MATERIALI subtotal
    has_aggregate: bool      # a generic grand-total 'FONDI AMMORTAMENTO IMMOBILIZ' was seen
    sval_immat: Decimal = Decimal('0')  # fondo svalutazione immobilizz. immateriali
    sval_mat: Decimal = Decimal('0')    # fondo svalutazione immobilizz. materiali

_IVA_LINE_RE = re.compile(r'\bIVA\b')

def _is_iva_line(desc_upper: str) -> bool:
    """IVA account line ('ERARIO C/IVA', 'IVA C/ACQUISTI', ...). Word-boundary so
    'RISERVA' (which contains the substring IVA) never matches."""
    return bool(_IVA_LINE_RE.search(desc_upper))

def _dedup_parent_child(rows):
    """Sum mastri OR leaves, never both. A parent row is dropped when its DIRECT
    child rows (codes strictly extending its code, with no intermediate ancestor
    among the descendants) are present and sum to its amount within
    max(2 EUR, 1%) — AGO layouts print the mastro subtotal above its detail
    accounts on both sides. Comparing against ALL descendants would double-count
    on 3-level layouts (mastro 41 → 41.01 → 41.01.07: intermediates + leaves sum
    to 2× the mastro, so the root was never dropped — budget_343/348).
    Code-less rows are always kept."""
    out = []
    for code, desc, amount in rows:
        if code:
            desc_codes = [(c, a) for c, _d, a in rows
                          if c != code and c.startswith(code)]
            kids = [a for c, a in desc_codes
                    if not any(o != c and c.startswith(o) for o, _a in desc_codes)]
            if kids:
                tol = max(Decimal('2'), abs(amount) * Decimal('0.01'))
                if abs(sum(kids) - amount) <= tol:
                    continue  # parent duplicated by its children
        out.append((code, desc, amount))
    return out

def _code_depth(code: str) -> int:
    """Hierarchy level of an account code.

    Dotted/slashed codes carry their depth explicitly ('03.01.07' -> 3). Flat
    numeric codes encode it in their LENGTH: AGO prints mastri as 8 digits
    ('13095000') and their sub-accounts as 9 ('101080000'). A 1-2 character
    flat code cannot be such an account — it is a bare level-1 mastro of a
    dotted-family chart ('03'), so it counts as depth 1.

    Depth is only a HINT — the caller must corroborate the chosen partition
    against a printed total before trusting it (see _select_dedup). Only the
    ORDER matters: a mastro must never score deeper than its own children.
    """
    c = (code or '').strip()
    if not c:
        return 0
    canon = _hier_canon(c)
    if '.' in canon:
        return len(canon.split('.'))
    return 1 if len(canon) <= 2 else len(canon)

def _depth_partition(rows, max_depth: int):
    """Keep the rows at or above `max_depth` in the hierarchy; code-less rows
    are always kept. A pure function of the THRESHOLD, so the same rule applies
    identically to any row set (see _dedup_rules)."""
    return [r for r in rows if not r[0] or _code_depth(r[0]) <= max_depth]

def _dedup_rules(rows):
    """Yield (label, rule) candidate partition RULES for a scan side.

    Each ``rule`` is a callable rows -> rows that CARRIES ITS OWN CRITERION, so
    the winner can be handed any other row set (the passivo side, the fondi
    subset) and still apply the very same partition. `rows` only generates the
    hypotheses (which depths exist here); it never parameterises the rules
    beyond the threshold they close over.

    No candidate is trusted on its own; _select_dedup scores them against the
    document's printed total. Includes the historical prefix-based dedup so a
    file that works today can still win.
    """
    yield 'all', list
    yield 'existing', _dedup_parent_child
    depths = sorted({_code_depth(c) for c, _d, _a in rows if c})
    for depth in depths:
        yield f'depth<={depth}', partial(_depth_partition, max_depth=depth)

def _dedup_candidates(rows):
    """Yield (label, rows) candidate partitions of a scan side — the rules of
    _dedup_rules already applied to `rows`."""
    for label, rule in _dedup_rules(rows):
        yield label, rule(rows)

def _select_dedup(attivo_rows, declared_total: Optional[Decimal]):
    """Pick the partition whose attivo sum reconciles to the declared total.

    Returns (label, dedup_fn, reconciled). ``dedup_fn`` is the WINNING RULE
    itself, not a label to be re-derived: it is applied unchanged to BOTH sides
    (and to the fondi subset), so the two are partitioned consistently even when
    a side happens to contain none of the winning depth's codes. When no
    declared total is available, or none of the candidates reconciles, the
    historical behaviour (`_dedup_parent_child`) is returned with
    reconciled=False — the caller then records the scan as unreliable instead of
    silently trusting it.
    """
    legacy = ('existing', _dedup_parent_child, False)
    if not declared_total or declared_total <= 0:
        return legacy
    tol = max(Decimal('50'), declared_total * Decimal('0.005'))
    best = None
    for label, rule in _dedup_rules(attivo_rows):
        kept = rule(attivo_rows)
        total = sum((a for _c, _d, a in kept), Decimal('0'))
        gap = abs(total - declared_total)
        if gap > tol:
            continue
        # tie-break: drop as few rows as possible
        key = (gap, -len(kept))
        if best is None or key < best[0]:
            best = (key, label, rule)
    if best is None:
        return legacy
    return best[1], best[2], True

def contra_declared_total(declared) -> Optional[Decimal]:
    """The printed total the contra scan must reconcile against.

    Contra-assets reconcile to the printed GROSS ATTIVO; ``pareggio`` can also
    include a current loss parked on the asset side, so using it first
    overstates the anchor (budget_330). Written once and shared, so every
    caller partitions the same document the same way.
    """
    if not declared:
        return None
    return (declared.get('attivo') or declared.get('pareggio')
            or declared.get('passivo'))

def contra_scan_mass(file_path: str, text: Optional[str] = None,
                     declared=None):
    """(fondi, iva_offset) that net_contra_accounts would remove from this doc.

    Exposed because pdf_importer has to reduce the declared anchor by exactly
    that mass BEFORE it picks between the CoGe-LLM and the deterministic
    candidate (the printed totals are GROSS on these files). Sharing this
    helper is what keeps the two sites on the SAME reconciliation-anchored
    partition: computing the mass with the historical prefix dedup over-reads
    it on AGO's disjoint code families (8-digit mastri vs 9-digit sub-accounts,
    neither a prefix of the other) and can hand the win to the wrong extractor.

    Returns (0, 0) when the document has no scannable rows.
    """
    Z = Decimal('0')
    rows = _contra_rows(file_path, text=text)
    if not rows:
        return Z, Z
    att_rows, pas_rows, _from_ocr = rows
    _label, dedup_fn, _reconciled = _select_dedup(
        att_rows, contra_declared_total(declared))
    scan = _contra_classify(att_rows, pas_rows, dedup=dedup_fn)
    fondi = (scan.fondi_immat + scan.fondi_mat
             + scan.sval_immat + scan.sval_mat)
    return fondi, min(scan.iva_credito, scan.iva_debito)

def _contra_classify(attivo_rows, passivo_rows, dedup=None) -> ContraScan:
    """Classify + sum deduplicated scan rows into the contra-netting aggregates.
    Rows are (code, desc_upper, amount); the SIDE each row came from is ground
    truth for attivo_total/IVA, while fondi ammortamento count from EITHER side.

    Besides the leaf sums, capture the document's own PRINTED level-1 subtotals
    ("IMMOBILIZZAZIONI IMMATERIALI/MATERIALI", max amount wins so a fondi-section
    header reusing the same caption never shadows the gross) — leaf-level sums
    under-count on layouts with truncated leaf descriptions, the printed anchors
    do not.

    ``dedup`` partitions the rows into the level actually summed; None keeps
    the historical prefix-based _dedup_parent_child (see _select_dedup)."""
    dedup = dedup or _dedup_parent_child
    Z = Decimal('0')
    g02 = g03 = att_total = f_im = f_mat = iva_c = iva_d = f_att = Z
    anch02 = anch03 = None

    # Printed subtotal anchors come from the RAW rows: dedup drops exactly the
    # mastro rows that carry them (their children reconcile). Skip the B-detail
    # captions that merely CONTAIN the subtotal phrase — 'ALTRE ...' and
    # '... IN CORSO' (immobilizzazioni in corso, B.II.5) — so that when the true
    # subtotal line is dropped by a noisy OCR pass we anchor to nothing (→ no-op)
    # rather than to a partial sub-line.
    for _c, d, a in attivo_rows:
        if _is_fondo_amm(d) or d.startswith('ALTRE') or 'IN CORSO' in d:
            continue
        if 'IMMOBILIZZAZIONI IMMATERIALI' in d:
            anch02 = a if anch02 is None else max(anch02, a)
        elif 'IMMOBILIZZAZIONI MATERIALI' in d:
            anch03 = a if anch03 is None else max(anch03, a)

    sval_rows = []                       # fondo svalutazione immobilizz. (either side)
    for _c, d, a in dedup(list(attivo_rows)):
        if _is_fondo_amm(d):
            continue                        # fondi handled from RAW rows below
        if _is_fondo_svalut_immob(d):
            sval_rows.append((abs(a), d))   # contra-asset: exclude from att_total
            continue
        att_total += a
        if _is_iva_line(d):
            iva_c += a
            continue
        f = _classify_sp_attivo(d)
        if f == 'gross_sp02':
            g02 += a
        elif f == 'gross_sp03':
            g03 += a
    for _c, d, a in dedup(list(passivo_rows)):
        if _is_fondo_amm(d):
            continue
        if _is_fondo_svalut_immob(d):
            sval_rows.append((abs(a), d))
            continue
        if _is_iva_line(d):
            iva_d += a

    def _reduce_fondi(raw_rows):
        """(total, immat) for one side's fondi rows [(code, desc, abs_amount)],
        taken PRE-dedup so the printed sub-aggregate captions survive.

        total  = the GRAND aggregate ('FONDI AMMORTAMENTO IMMOBILIZ', no category
                 qualifier) when the document prints one, else the deduplicated leaf
                 sum (parent/child collapsed so nothing double-counts).
        immat  = the IMMATERIALI sub-aggregate ('FONDI AMMORT. IMMOBILIZZAZ. IMM' /
                 'F/AMM IMMOBILIZZAZIONI IMMAT.') when printed, else the immat-
                 classified leaf sum. mat = total - immat.

        Reading the sub-aggregate from the RAW rows is the fix: the generic
        _dedup_parent_child keeps children and DROPS the parent, so post-dedup the
        immat sub-aggregate is gone and the surviving LEAVES are truncated
        ("F/AMM.LIC. D'USO SOF. A TEM. IND") and self-misclassify to materiali →
        the whole immateriali fondo leaks into materiali (budget_395). Anchoring on
        the printed sub-aggregate keeps the split correct without depending on leaf
        captions, while the deduped leaf sum keeps the TOTAL exact where there is a
        3-level tree with a grand total too (budget_343: 41 > 4101 > leaves)."""
        if not raw_rows:
            return Z, Z
        deduped = dedup(list(raw_rows))
        leaf_total = sum(a for _c, _d, a in deduped)
        grand_aggs = [a for _c, d, a in raw_rows if _is_fondo_aggregate(d)]
        total = max(grand_aggs) if grand_aggs else leaf_total
        immat_aggs = [a for _c, d, a in raw_rows if _is_fondo_immat_aggregate(d)]
        if immat_aggs:
            im = min(max(immat_aggs), total)
        else:
            im = sum(a for _c, d, a in deduped if _fondo_is_immat(d))
        return total, min(im, total)

    fondi_att_raw = [(c, d, abs(a)) for c, d, a in attivo_rows if _is_fondo_amm(d)]
    fondi_pas_raw = [(c, d, abs(a)) for c, d, a in passivo_rows if _is_fondo_amm(d)]
    t_att, im_att = _reduce_fondi(fondi_att_raw)
    t_pas, im_pas = _reduce_fondi(fondi_pas_raw)
    f_att = t_att
    f_im = im_att + im_pas
    f_mat = (t_att - im_att) + (t_pas - im_pas)
    has_agg = any(_is_fondo_aggregate(d) for _c, d, _a in fondi_att_raw + fondi_pas_raw)
    # Fondo svalutazione immobilizzazioni: a plain leaf sum split immat/mat — it
    # has its own 'FONDI SVALUTAZIONE ...' captions, kept in a SEPARATE stream so
    # the ammortamento aggregate helpers never shadow a svalutazione leaf.
    sval_im = sum(a for a, d in sval_rows if _fondo_is_immat(d))
    sval_mat = sum(a for a, d in sval_rows if not _fondo_is_immat(d))
    return ContraScan(g02, g03, att_total, f_im, f_mat, iva_c, iva_d,
                      f_att, anch02, anch03, has_agg, sval_im, sval_mat)

_CONTRA_TXT_ROW_RE = re.compile(
    r'^\s*(?P<code>[\d./*]+)?\s*(?P<desc>[A-ZÀ-Ù][^\d\n]*?)\s+'
    r'(?P<amt>-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$', re.MULTILINE)
# Multi-match segment: finds EVERY "code description amount" triple anywhere on a
# line, not just one anchored at EOL. Vision-OCR of a two-column bilancio di
# verifica merges attivo+passivo onto one physical line ("35 CONTI ERARIALI
# 50.794,41  41 FONDI AMMORTAMENTO IMMOBILIZZ 400.473,85"), which the single-row
# EOL-anchored regex above cannot split. Used only as a fallback when that regex
# yields nothing (real scanned PDFs), so text-layer scans are unaffected.
_CONTRA_TXT_SEG_RE = re.compile(
    r'(?P<code>\d[\d./]*)\s+(?P<desc>[A-ZÀ-Ù][^\d\n]*?)\s+'
    r'(?P<amt>-?\d{1,3}(?:\.\d{3})*,\d{2})')

def _contra_rows(file_path: str, text: Optional[str] = None):
    """Acquire (attivo_rows, passivo_rows, from_ocr) for the contra-netting scan.

    Generated PDFs: coordinate mode — the SP pages' two physical columns are
    split with the same helpers the best-effort parser uses (`_be_split` +
    `_be_collect_side`), so each row carries its true side (from_ocr=False,
    complete capture). Scanned PDFs (no word layer): line-parse the OCR `text`;
    the side is unknown and capture is partial, so rows are assigned by NATURE
    (fondi → passivo bucket, attivo-rule matches → attivo) and from_ocr=True —
    lower fidelity, which the caller's self-validation gate absorbs (a misread
    scan fails reconciliation → no-op, never corruption).
    Returns None when neither mode yields rows.
    """
    # --- coordinate mode -----------------------------------------------------
    try:
        import fitz
        doc = fitz.open(file_path)
        att, pas = [], []
        for page in doc:
            up = page.get_text().upper()
            flat = re.sub(r'\s+', '', up)
            # fiscal-reconciliation appendix pages are not the SP
            if 'RIDETERMINAZIONE' in flat or 'REDDITOIMPONIBILE' in flat:
                continue
            # 'Dettaglio ratei, risconti e competenze' breakdown appendices carry
            # the 'Conti Patrimoniali' header, so they pass the PATRIMONIAL test
            # below, yet they only RE-LIST fragments already totalled in the main
            # prospetto — scanning them double-counts (budget_210 reprints the
            # ricerca-sviluppo fondo on two such pages). Match the specific
            # appendix title and never a genuine prospetto ('SITUAZIONE/STATO
            # PATRIMONIALE'), so a real SP page like 'STATO PATRIMONIALE
            # (DETTAGLIO COMPLETO)' is kept.
            if ('SITUAZIONEPATRIMONIAL' not in flat
                    and 'STATOPATRIMONIAL' not in flat
                    and ('DETTAGLIORATEI' in flat or 'DETTAGLIORISCONT' in flat
                         or 'DETTAGLIOCOMPETENZE' in flat)):
                continue
            is_sp = ('PATRIMONIAL' in flat) or (
                'ATTIVIT' in up and 'PASSIVIT' in up and 'CONTOECONOMICO' not in flat)
            is_ce = ('CONTOECONOMICO' in flat) or ('COSTI' in up and 'RICAVI' in up)
            if not is_sp or is_ce:
                continue
            words = page.get_text('words')
            if not words:
                continue
            split = _be_split(words)
            if split is None:
                split = page.rect.width / 2
            att += _be_collect_side(words, -1e9, split)
            pas += _be_collect_side(words, split, 1e9)
        doc.close()
        if att or pas:
            return att, pas, False
    except Exception:
        pass

    # --- OCR-text fallback (scanned PDFs) ------------------------------------
    if not text:
        return None
    up = text.upper()
    # Vision OCR of a two-column sheet emits a markdown-ish table: cells separated
    # by '|' pipes ("41 | | FONDI AMMORTAMENTO IMMOBILIZZ | 400.473,85"). Collapse
    # pipes (and other table glyphs) to spaces so the code/desc/amount segment
    # regex sees a plain "code desc amount" stream on each line.
    up = re.sub(r'[|＋+]+', ' ', up)
    # keep only the SP region: cut at the CE section header
    m = re.search(r'CONTO\s+ECONOMICO', up)
    if m:
        up = up[:m.start()]
    def _assign(code, desc, amount, att, pas):
        desc = desc.strip()
        if len(desc) < 3 or 'TOTALE' in desc or 'PAREGGIO' in desc:
            return
        code = re.sub(r'\D', '', (code or '').strip().strip('./*'))
        entry = (code, desc, abs(amount))
        if _is_fondo_amm(desc):
            pas.append(entry)          # side irrelevant for fondi (contra either way)
        elif _is_iva_line(desc) and ('VENDIT' in desc or 'DEBITO' in desc):
            pas.append(entry)
        else:
            f = _classify_sp_attivo(desc)
            # text mode has no column ground truth: count ONLY explicit
            # attivo-rule matches (never the sp06 default, which would suck
            # passivo/CE lines into the attivo total and defeat the gate)
            if f != 'sp06' or _is_iva_line(desc):
                att.append(entry)

    # Multi-match segment extraction: finds every code/desc/amount triple on each
    # line, so it reads both columns of a two-column vision-OCR sheet AND ordinary
    # single-column rows. It is a strict superset of the EOL-anchored single-row
    # regex, so use it as the primary OCR parser (the single-row one returned early
    # on the first single-column match and never split the merged columns).
    att, pas = [], []
    for seg in _CONTRA_TXT_SEG_RE.finditer(up):
        try:
            amount = _parse_amount(seg.group('amt'))
        except Exception:
            continue
        _assign(seg.group('code'), seg.group('desc'), amount, att, pas)
    if att or pas:
        return att, pas, True

    # Fallback: EOL-anchored single-row (descriptions that start mid-line without a
    # leading code — the segment regex requires a leading digit).
    att, pas = [], []
    for row in _CONTRA_TXT_ROW_RE.finditer(up):
        try:
            amount = _parse_amount(row.group('amt'))
        except Exception:
            continue
        _assign(row.group('code'), row.group('desc'), amount, att, pas)
    if att or pas:
        return att, pas, True
    return None

def _reduce_debts(bs: Dict[str, Decimal], amount: Decimal) -> Decimal:
    """Remove `amount` from the debt buckets: sp16g (altri, where misclassified
    fondi land) first — mirrored on the sp16 aggregate to keep sub-field
    consistency — then the sp16 aggregate residual, then the sp17 side. Floors
    at 0 everywhere; returns the mass actually removed."""
    Z = Decimal('0')
    removed = Z
    for sub, agg in (('sp16g_altri_debiti_breve', 'sp16_debiti_breve'),
                     ('sp16e_debiti_tributari_breve', 'sp16_debiti_breve'),
                     ('sp17g_altri_debiti_lungo', 'sp17_debiti_lungo')):
        if removed >= amount:
            break
        take = min(amount - removed, bs.get(sub, Z))
        if take > Z:
            bs[sub] = bs.get(sub, Z) - take
            bs[agg] = max(Z, bs.get(agg, Z) - take)
            removed += take
    for agg in ('sp16_debiti_breve', 'sp17_debiti_lungo'):
        if removed >= amount:
            break
        take = min(amount - removed, bs.get(agg, Z))
        if take > Z:
            bs[agg] = bs.get(agg, Z) - take
            removed += take
    return removed

def net_contra_accounts(winner_bs: Dict[str, Decimal], file_path: str,
                        text: Optional[str] = None,
                        declared: Optional[dict] = None):
    """Deterministic contra-netting overlay for route-C trial balances.

    Re-reads the source document, sums fondi ammortamento (parent/child
    deduplicated) and the offsettable IVA position, then — deterministic
    authority — OVERWRITES sp02/sp03 with the scanned net values and removes
    from the debt buckets exactly the passivo excess over the new attivo
    (capped at the fondi mass), so an already-net extraction is passed through
    untouched (idempotent) and a gross one comes out net and balanced.

    Self-validation gates (either fails -> no-op, sheet returned unchanged):
      1. netted contra > 1% of the declared total (there is real contra mass);
      2. the scan's gross attivo reconciles to the declared TOTALE ATTIVO /
         pareggio within 0.5% (proves we read the right magnitudes).

    Returns (winner_bs, netted_contra). netted_contra > 0 also when the sheet
    needed no field change (already net): the caller must still reduce the
    DECLARED anchor by it, because the document's printed totals are GROSS.
    """
    Z = Decimal('0')

    def _mark(bs, detected, applied, reason):
        """Record the scan outcome on the sheet so downstream reliability
        reporting can distinguish 'no contra mass' from 'contra mass found but
        NOT applied'. Underscore keys are passed through by _map_sc_keys and
        ignored by _create_balance_sheet (which reads only ORM columns), the
        same mechanism _plug_residual / _netted_contra already rely on."""
        bs['_contra_detected'] = detected
        bs['_contra_applied'] = applied
        bs['_contra_reason'] = reason
        return bs

    dedup_label = 'existing'
    try:
        decl_total = contra_declared_total(declared)
        if not decl_total or decl_total <= 0:
            return _mark(winner_bs, Z, Z, 'nessun totale dichiarato'), Z
        rows = _contra_rows(file_path, text=text)
        if not rows:
            return _mark(winner_bs, Z, Z, 'scan non disponibile'), Z
        att_rows, pas_rows, from_ocr = rows
        # Which hierarchy level to sum is decided by RECONCILIATION against the
        # document's own printed total, never by code prefixes: AGO uses two
        # disjoint code families (8-digit mastri, 9-digit sub-accounts) that are
        # not prefixes of each other, so the historical dedup summed both.
        dedup_label, dedup_fn, dedup_reconciled = _select_dedup(att_rows, decl_total)
        scan = _contra_classify(att_rows, pas_rows, dedup=dedup_fn)
        logger.info("contra-netting: partizione '%s' (riconcilia=%s)",
                    dedup_label, dedup_reconciled)
        iva_offset = min(scan.iva_credito, scan.iva_debito)
        # Contra to immobilizzazioni = fondo ammortamento + fondo svalutazione
        # immobilizzazioni, per side (both reduce B.I/B.II net book value).
        immat_contra = scan.fondi_immat + scan.sval_immat
        mat_contra = scan.fondi_mat + scan.sval_mat
        fondi_total = immat_contra + mat_contra
        netted = fondi_total + iva_offset
        if netted <= decl_total * Decimal('0.01'):
            return _mark(winner_bs, netted, Z,
                         'massa contro sotto soglia'), Z     # gate 1
        anchored = False
        if abs(scan.attivo_total - decl_total) > decl_total * Decimal('0.005'):
            # Gate 2 failed: the FULL attivo sum is polluted (4-sezioni layouts
            # print partitari detail rows whose short codes collide with real
            # mastri after digit-normalisation). Fall back to ANCHORED mode:
            # trust the document's own printed IMMOBILIZZAZIONI subtotals as the
            # gross, provided (a) the fondi sit on the PASSIVO side (an already-
            # net doc lists them on the attivo → anchors would be NET → double
            # netting) and (b) each fondi mass fits under its anchor.
            def _fits(fondi, anchor):
                if fondi <= Z:
                    return True
                return (anchor is not None
                        and fondi <= anchor + max(Decimal('2'),
                                                  anchor * Decimal('0.005')))
            fondi_passivo_only = scan.fondi_att <= fondi_total * Decimal('0.01')
            # Anchored mode trusts a bottom-up fondi total. From a TEXT-LAYER scan
            # (from_ocr=False) capture is complete and reliable, so a single anchor
            # + leaf-summed fondi is enough (budget_405: specific fondi, no
            # grand-total line). From a SCANNED OCR pass capture is PARTIAL and
            # stochastic, so demand strong corroboration or NO-OP (→ user corrects
            # in Rettifiche) — never write a wrong net immobilizzazioni:
            #   • the printed grand-total aggregate line was captured; AND
            #   • BOTH printed immobilizzazioni subtotals (immat + mat) are present
            #     (a missing one means the OCR dropped a subtotal → unreliable); AND
            #   • the immateriali fondo was actually located (fondi_immat > 0) — else
            #     the whole aggregate would wrongly net onto materiali only.
            if from_ocr:
                reliable = (scan.has_aggregate
                            and scan.anchor_sp02 is not None
                            and scan.anchor_sp03 is not None
                            and scan.fondi_immat > Z)
            else:
                reliable = (scan.anchor_sp02 is not None
                            or scan.anchor_sp03 is not None)
            if (fondi_passivo_only and reliable
                    and _fits(immat_contra, scan.anchor_sp02)
                    and _fits(mat_contra, scan.anchor_sp03)):
                anchored = True
            else:
                logger.info(
                    "contra-netting: scan attivo %s non riconcilia col totale "
                    "dichiarato %s e niente anchor affidabili — no-op",
                    scan.attivo_total, decl_total)
                return _mark(
                    winner_bs, netted, Z,
                    'contro rilevati ma non applicati: scan non riconcilia'), Z
    except Exception as exc:
        logger.warning("contra-netting: scan fallito (%s) — no-op", exc)
        return _mark(winner_bs, Z, Z, f'scan fallito: {exc}'), Z

    # ---- apply (deterministic authority) ------------------------------------
    # IVA gross-evidence gate: the IVA collapse is a DELTA (not idempotent like
    # the sp02/sp03 overwrite), so it applies only when the winner's pre-apply
    # total still sits at the declared GROSS magnitude — proof nothing was
    # collapsed yet. An already-net / partially-net sheet skips the IVA delta.
    # Snapshot every field this phase can mutate: a raise mid-apply must never
    # leave winner_bs half-netted with no _contra_* marker on it (silent
    # masking) — roll back to this snapshot on failure so the sheet is
    # byte-identical to its pre-apply state.
    _pre_apply = dict(winner_bs)
    try:
        pre_total = winner_bs.get('totale_attivo', Z)
        apply_iva = (iva_offset > Z
                     and abs(pre_total - decl_total) <= decl_total * Decimal('0.005'))

        old_02 = winner_bs.get('sp02_immob_immateriali', Z)
        old_03 = winner_bs.get('sp03_immob_materiali', Z)
        if anchored:
            # Anchored mode: printed subtotal − (fondo amm + svalutazione). A side
            # without an anchor is left untouched (never zeroed by an absent leaf sum).
            new_02 = (max(Z, scan.anchor_sp02 - immat_contra)
                      if scan.anchor_sp02 is not None else old_02)
            new_03 = (max(Z, scan.anchor_sp03 - mat_contra)
                      if scan.anchor_sp03 is not None else old_03)
        else:
            # Reconciled scan: prefer the document's PRINTED immobilizzazioni subtotal
            # (anchor) over the keyword-summed gross. The keyword sum drops sub-lines
            # the attivo classifier does not recognise (budget_210: SITO WEB,
            # progettazioni, spese pluriennali → gross_sp02 205.600 vs printed
            # 223.901,20), which would under-net the net immobilizzazioni. Fall back to
            # the keyword gross only when the document prints no subtotal.
            base_02 = scan.anchor_sp02 if scan.anchor_sp02 is not None else scan.gross_sp02
            base_03 = scan.anchor_sp03 if scan.anchor_sp03 is not None else scan.gross_sp03
            new_02 = max(Z, base_02 - immat_contra)
            new_03 = max(Z, base_03 - mat_contra)
        winner_bs['sp02_immob_immateriali'] = new_02
        winner_bs['sp03_immob_materiali'] = new_03
        att_delta = (new_02 + new_03) - (old_02 + old_03)
        winner_bs['totale_attivo'] = winner_bs.get('totale_attivo', Z) + att_delta

        if apply_iva:
            # collapse the offsettable IVA: net erario position stays on the larger
            # side, the smaller side is dropped from crediti and debiti tributari.
            cred = winner_bs.get('sp06_crediti_breve', Z)
            take = min(iva_offset, cred)
            winner_bs['sp06_crediti_breve'] = cred - take
            winner_bs['totale_attivo'] -= take
            winner_bs['totale_passivo'] = (winner_bs.get('totale_passivo', Z)
                                           - _reduce_debts(winner_bs, take))

        # balance-invariant fondi removal from the debt buckets: exactly the passivo
        # excess over the (new, net) attivo, capped at the fondi mass — 0 when the
        # extractor had already netted, the full fondi mass when it was gross.
        excess = winner_bs.get('totale_passivo', Z) - winner_bs['totale_attivo']
        to_remove = min(max(Z, excess), fondi_total)
        if to_remove > Z:
            winner_bs['totale_passivo'] = (winner_bs.get('totale_passivo', Z)
                                           - _reduce_debts(winner_bs, to_remove))
        logger.info(
            "contra-netting: nettati %s (fondi immat %s + mat %s + IVA %s); "
            "sp02 %s→%s, sp03 %s→%s", netted, scan.fondi_immat, scan.fondi_mat,
            iva_offset, old_02, new_02, old_03, new_03)
    except Exception as exc:
        # Restore winner_bs to its exact pre-apply state: a partial mutation
        # here would leave sp02/sp03/totale_attivo/debt buckets half-netted
        # with NO _contra_* marker set, which downstream reliability reporting
        # would read as 'no scan ran on this route' (DERIVED) instead of the
        # failed-mid-application UNRELIABLE it actually is.
        winner_bs.clear()
        winner_bs.update(_pre_apply)
        logger.warning(
            "contra-netting: applicazione fallita (%s) — rollback allo stato "
            "pre-apply", exc, exc_info=True)
        return _mark(winner_bs, netted, Z,
                     f'applicazione fallita: {exc}'), Z

    _mark(winner_bs, netted, netted, f'applicato ({dedup_label})')
    return winner_bs, netted
