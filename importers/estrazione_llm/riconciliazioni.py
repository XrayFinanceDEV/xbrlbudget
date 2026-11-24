"""Riconciliazioni dopo l'estrazione: segni del CE, crediti, ammortamenti, patrimonio netto, personale.

Spostato da importers/pdf_extractor_llm.py senza cambiare il codice; quel modulo resta
la facciata da cui importare (vedi il suo docstring)."""

import logging
import pydantic
import re
from calculations.ce_result import calculate_ce_result
from decimal import Decimal
from typing import Dict
from importers.estrazione_llm.modelli import (
    _parse_it_number,
)

# il nome di prima: i filtri e i test sui log non cambiano
logger = logging.getLogger("importers.pdf_extractor_llm")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_to_decimal_dict(model: pydantic.BaseModel) -> Dict[str, Decimal]:
    """Convert a Pydantic model with float fields to Dict[str, Decimal]."""
    result = {}
    for field_name, value in model:
        result[field_name] = Decimal(str(value))
    return result

_CREDIT_BREVE_SOURCE_FIELDS = (
    'sp06a_crediti_clienti_breve',
    'sp06b_crediti_controllate_breve',
    'sp06c_crediti_collegate_breve',
    'sp06d_crediti_controllanti_breve',
    'sp06e_crediti_tributari_breve',
    'sp06f_imposte_anticipate_breve',
    'sp06g_crediti_altri_breve',
)

_CREDIT_LUNGO_SOURCE_FIELDS = (
    'sp07a_crediti_clienti_lungo',
    'sp07b_crediti_controllate_lungo',
    'sp07c_crediti_collegate_lungo',
    'sp07d_crediti_controllanti_lungo',
    'sp07e_crediti_tributari_lungo',
    'sp07f_imposte_anticipate_lungo',
    'sp07g_crediti_altri_lungo',
)

def _reconcile_credit_aggregates_from_source(
    balance_sheet_data: Dict[str, Decimal], label: str
) -> Dict[str, Decimal]:
    """Rebuild credit aggregates only from corroborated rows in the source.

    The LLM can extract every typed C.II row correctly but make a small arithmetic
    error in ``sp06_crediti_breve``.  The strict balance gate then rejects an exact
    statement (budget_594 differs by EUR 22).

    Unlike the historical balance-gap correction, this function never infers an
    amount from total assets and never creates a plug.  It changes the aggregates
    only when the extracted short/long details add up to the PDF's explicit
    ``totale_crediti`` control row.
    """
    result = dict(balance_sheet_data)
    declared_total = result.get('totale_crediti', Decimal('0'))
    if declared_total <= 0:
        return result

    short_total = sum(
        (result.get(key, Decimal('0')) for key in _CREDIT_BREVE_SOURCE_FIELDS),
        Decimal('0'),
    )
    long_total = sum(
        (result.get(key, Decimal('0')) for key in _CREDIT_LUNGO_SOURCE_FIELDS),
        Decimal('0'),
    )
    detail_total = short_total + long_total
    old_short = result.get('sp06_crediti_breve', Decimal('0'))
    old_long = result.get('sp07_crediti_lungo', Decimal('0'))

    # One euro absorbs harmless display rounding without accepting a partial
    # breakdown as proof of an aggregate. Preserve an aggregate that already
    # agrees with the printed total: legal detail rows can differ by one euro due
    # to independent display rounding (budget_394).
    if (
        detail_total <= 0
        or abs(old_short + old_long - declared_total) <= Decimal('1')
    ):
        return result

    if abs(detail_total - declared_total) <= Decimal('1'):
        new_short, new_long = short_total, long_total
    else:
        # Some legal layouts print a maturity subtotal that excludes a separate
        # typed row (typically "imposte anticipate") and then print the complete
        # C.II total.  Accept the omitted amount only when that exact residual is
        # independently present in one maturity-specific detail bucket.
        residual = declared_total - old_short - old_long
        short_match = short_total != 0 and abs(residual - short_total) <= Decimal('1')
        long_match = long_total != 0 and abs(residual - long_total) <= Decimal('1')
        if short_match == long_match:  # neither match, or ambiguous
            return result
        if short_match:
            new_short, new_long = old_short + residual, old_long
        else:
            new_short, new_long = old_short, old_long + residual

    if abs(old_short - new_short) > Decimal('0.01') or abs(old_long - new_long) > Decimal('0.01'):
        logger.warning(
            f"[{label}] Crediti source-backed: dettagli C.II={detail_total} "
            f"confermano totale_crediti={declared_total}; "
            f"sp06 {old_short}->{new_short}, sp07 {old_long}->{new_long}"
        )
        result['sp06_crediti_breve'] = new_short
        result['sp07_crediti_lungo'] = new_long
    return result

# Core cost fields that must always be positive (the model subtracts them).
# Some PDFs (e.g. Zucchetti, "bilancio riclassificato") show costs as negative.
_POSITIVE_COST_FIELDS = {
    'ce05_materie_prime', 'ce06_servizi', 'ce07_godimento_beni',
    'ce08_costi_personale', 'ce08a_tfr_accrual',
    'ce09_ammortamenti', 'ce09a_ammort_immateriali', 'ce09b_ammort_materiali',
    'ce09c_svalutazioni', 'ce09d_svalutazione_crediti',
    'ce11_accantonamenti', 'ce11b_altri_accantonamenti',
    'ce12_oneri_diversi',
    'ce15_oneri_finanziari',
    'ce19_oneri_straordinari',
}
# Ambiguous fields handled explicitly in _normalize_ce_signs Pass 2 when the PDF uses
# the "all costs as negative" convention:
#   ce10_var_rimanenze_mat_prime — a variation that can be a cost OR a credit; it must
#     be NEGATED (not abs'd) so an inventory-increase credit shown as +X becomes -X.
#   ce20_imposte — effectively always an expense; flipped to positive only when negative.


def _normalize_ce_signs(income_data: Dict[str, Decimal]) -> Dict[str, Decimal]:
    """Ensure cost fields are stored as positive values.

    The model formulas explicitly subtract costs (e.g. EBIT = VP - COPRO),
    so ce05-ce12, ce15, ce19, ce20 must be positive.  Some PDFs show costs
    in parentheses and the LLM correctly extracts them as negative — this
    function flips those to positive.

    When the PDF uses "all costs as negative" convention (detected by ≥3
    core cost fields being negative), also flip ce10 and ce20.
    """
    # Pass 1: flip core cost fields and count how many were negative
    flipped = []
    for field in _POSITIVE_COST_FIELDS:
        val = income_data.get(field, Decimal('0'))
        if val < 0:
            income_data[field] = abs(val)
            flipped.append(field)

    # Pass 2: if many core fields were negative, the PDF uses "costs as negative"
    # convention — handle the ambiguous fields.
    if len(flipped) >= 3:
        # ce10 (variazioni rimanenze materie prime) is NOT a pure cost: an inventory
        # INCREASE is a credit that REDUCES COPRO and is printed with the opposite
        # sign of the surrounding cost block (i.e. a plain positive number, while the
        # real costs are in parentheses). The correct transform is therefore to NEGATE
        # it — the very same flip applied to every cost line — so a +X credit becomes
        # -X in the positive-cost model and a real cost shown as -X becomes +X. Using
        # abs() (the old behaviour) left a +X credit untouched and inflated COPRO by 2X,
        # breaking the CE cross-foot (e.g. ALMA item 11 = +7.831 → CE off by 15.662).
        ce10 = income_data.get('ce10_var_rimanenze_mat_prime', Decimal('0'))
        if ce10 != 0:
            income_data['ce10_var_rimanenze_mat_prime'] = -ce10
            flipped.append('ce10_var_rimanenze_mat_prime')
        # ce20 (imposte) is effectively always an expense in these layouts; flip the
        # parenthesised (negative) presentation to positive, leave an already-positive
        # value alone.
        ce20 = income_data.get('ce20_imposte', Decimal('0'))
        if ce20 < 0:
            income_data['ce20_imposte'] = abs(ce20)
            flipped.append('ce20_imposte')

    if flipped:
        logger.info(f"CE sign normalization: flipped {len(flipped)} fields to positive: {flipped}")
    return income_data

_CE09_DETAIL_FIELDS = (
    'ce09a_ammort_immateriali',
    'ce09b_ammort_materiali',
    'ce09c_svalutazioni',
    'ce09d_svalutazione_crediti',
)

def _reconcile_ce09_from_source_details(
    income_data: Dict[str, Decimal],
    balance_sheet_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Select the exhaustive B.10 detail sum when SP independently confirms it.

    The model occasionally scales one B.10 sub-row while computing the aggregate
    (budget_413: 1,254 becomes 1,254,000) even though every extracted a/b/c/d row is
    correct.  The four legal detail fields are exhaustive, but a partially printed
    statement can omit one.  Therefore the roll-up is accepted only when replacing
    ``ce09`` makes the reconstructed CE result agree with the independently printed
    SP result; otherwise the source aggregate is left untouched for review.
    """
    result = dict(income_data)
    detail_total = sum(
        (result.get(field, Decimal('0')) for field in _CE09_DETAIL_FIELDS),
        Decimal('0'),
    )
    aggregate = result.get('ce09_ammortamenti', Decimal('0'))
    if detail_total <= 0 or abs(aggregate - detail_total) <= Decimal('0.01'):
        return result

    sp_result = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    current_result = calculate_ce_result(result).net_profit
    candidate = dict(result)
    candidate['ce09_ammortamenti'] = detail_total
    candidate_result = calculate_ce_result(candidate).net_profit
    tolerance = max(Decimal('2'), abs(sp_result) * Decimal('0.001'))
    if (
        abs(candidate_result - sp_result) <= tolerance
        and abs(candidate_result - sp_result) + Decimal('0.01')
        < abs(current_result - sp_result)
    ):
        logger.warning(
            f"[{label}] B.10 source-backed: ce09 {aggregate}->{detail_total}; "
            f"dettagli a/b/c/d e risultato SP {sp_result} confermano il roll-up"
        )
        candidate['_ce09_source_reconciled'] = aggregate - detail_total
        return candidate
    return result

def _reconcile_isolated_ce_cost_signs(
    income_data: Dict[str, Decimal],
    raw_income_data: Dict[str, Decimal],
    balance_sheet_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Preserve isolated negative cost rows when the SP result confirms them.

    Three or more negative cost rows signal a presentation convention and are
    normalized to positive magnitudes.  One or two negative rows can instead be a
    real reversal (budget_253 B.14 = -1,239).  Try only the explicitly negative
    source signs and retain a candidate solely when its CE result cross-foots to the
    independently extracted SP result.
    """
    negative_fields = [
        field for field in _POSITIVE_COST_FIELDS
        if raw_income_data.get(field, Decimal('0')) < 0
    ]
    if not negative_fields or len(negative_fields) >= 3:
        return dict(income_data)

    sp_result = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    tolerance = max(Decimal('2'), abs(sp_result) * Decimal('0.001'))
    baseline_gap = abs(calculate_ce_result(income_data).net_profit - sp_result)
    candidates = []
    subsets = [[field] for field in negative_fields]
    if len(negative_fields) == 2:
        subsets.append(negative_fields)
    for fields in subsets:
        trial = dict(income_data)
        for field in fields:
            trial[field] = raw_income_data[field]
        gap = abs(calculate_ce_result(trial).net_profit - sp_result)
        if gap <= tolerance and gap + Decimal('0.01') < baseline_gap:
            candidates.append((gap, tuple(sorted(fields)), trial))
    if not candidates:
        return dict(income_data)

    gap, fields, best = min(candidates, key=lambda item: (item[0], len(item[1]), item[1]))
    logger.warning(
        f"[{label}] segni CE source-backed: mantenuti negativi {list(fields)}; "
        f"risultato CE riconciliato a sp13={sp_result} (scarto {gap})"
    )
    return best

def _reconcile_global_ce_thousand_scale(
    income_data: Dict[str, Decimal],
    balance_sheet_data: Dict[str, Decimal],
    label: str,
) -> Dict[str, Decimal]:
    """Correct a whole CE column parsed at 1000x only with SP corroboration.

    A mangled value such as ``542.218.750`` can represent ``542.218,750`` after
    the decimal comma was converted to a dot.  It is indistinguishable from an
    integer in isolation.  When at least three CE fields share the scale error,
    dividing the complete CE by 1000 is accepted only if the resulting net profit
    matches the independently extracted SP result (budget_305).
    """
    result = dict(income_data)
    ce_fields = [
        field for field, value in result.items()
        if field.startswith('ce') and isinstance(value, Decimal) and value != 0
    ]
    if len(ce_fields) < 3:
        return result
    sp_result = balance_sheet_data.get('sp13_utile_perdita', Decimal('0'))
    baseline_result = calculate_ce_result(result).net_profit
    baseline_gap = abs(baseline_result - sp_result)
    if baseline_gap <= max(Decimal('2'), abs(sp_result) * Decimal('0.001')):
        return result

    candidate = dict(result)
    for field in ce_fields:
        candidate[field] = result[field] / Decimal('1000')
    candidate_result = calculate_ce_result(candidate).net_profit
    tolerance = max(Decimal('2'), abs(sp_result) * Decimal('0.001'))
    # Require a characteristic three-order-of-magnitude mismatch, not merely a
    # somewhat better result, before treating the punctuation as a scale error.
    magnitude_floor = max(Decimal('100000'), abs(sp_result) * Decimal('100'))
    if baseline_gap >= magnitude_floor and abs(candidate_result - sp_result) <= tolerance:
        logger.warning(
            f"[{label}] scala CE source-backed: colonna /1000; risultato "
            f"{baseline_result}->{candidate_result}, confermato da sp13={sp_result}"
        )
        candidate['_ce_scale_reconciled'] = Decimal('1000')
        return candidate
    return result

_DETAIL_TOKEN_RE = re.compile(r'\(?-?[\d.,]+\)?-?')

def _values_for_label(lines, idx: int, label_end: int):
    """Collect up to 2 numeric values for a matched label: first any numbers on the
    SAME line after the label, then numbers on following (blank-skipped) lines, stopping
    at the first non-blank non-numeric line. Handles both the 'label\\ncur\\nprior'
    column layout (PyMuPDF cell-per-line) and the 'label cur prior' single-line layout."""
    nums = []
    tail = lines[idx][label_end:]
    for t in _DETAIL_TOKEN_RE.findall(tail):
        v = _parse_it_number(t)
        if v is not None:
            nums.append(v)
    j = idx + 1
    skipped_total = False
    while len(nums) < 2 and j < len(lines):
        s = lines[j].strip()
        if not s:
            j += 1
            continue
        v = _parse_it_number(s)
        if v is None:
            # In detail / Zucchetti layouts the voce value can sit AFTER an interposed
            # "Totale <voce>" line (the pre-filter reorders the detail block so the
            # numbers land below the "Totale" structural line). Skip ONE such line
            # before giving up, so the voce total stays reachable (e.g. budget_331:
            # "VIII - Utili portati" \n "Totale VIII - Utili portati" \n "(1.520)").
            if not nums and not skipped_total and s[:6].lower() == 'totale':
                skipped_total = True
                j += 1
                continue
            break
        nums.append(v)
        j += 1
    return nums

def _scan_labeled(text: str, specs):
    """specs: list of (compiled regex anchored at line start, key). Returns
    {key: [vals...]} for the FIRST line matching each spec, in document order."""
    lines = text.split('\n')
    out = {}
    for i, line in enumerate(lines):
        for rx, key in specs:
            if key in out:
                continue
            m = rx.match(line)
            if m:
                vals = _values_for_label(lines, i, m.end())
                if vals:
                    out[key] = vals
                break
    return out

# Roman-numeral PN reserve lines (art. 2424 A.II..A.X). The numeral is followed by a
# separator (dash OR ')') OR just whitespace — `(?:\s*[-–)]\s*|\s+)` — so layouts that
# print "IV   Riserva legale" with NO separator (budget_315) are matched too. The required
# whitespace still disambiguates 'V'/'VI'/'VII'/'VIII' ('VII ...' cannot match the 'VI'
# spec because the char after 'VI' is 'I', not whitespace). An optional 'A.' letter prefix
# is allowed for gestionali that print the legal path-code ('A.VIII) Utili...' — budget_340/341).
_PN_DETAIL_SPECS = [
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*II(?:\s*[-–)]\s*|\s+)Riserva da soprapprezzo', re.I), 'sp12a_riserva_sovrapprezzo'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*III(?:\s*[-–)]\s*|\s+)Riserve di rivalutazione', re.I), 'sp12b_riserve_rivalutazione'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*IV(?:\s*[-–)]\s*|\s+)Riserva legale', re.I), 'sp12c_riserva_legale'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*V(?:\s*[-–)]\s*|\s+)Riserve statutarie', re.I), 'sp12d_riserve_statutarie'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*(?:VI|VII)(?:\s*[-–)]\s*|\s+)Altre riserve', re.I), 'sp12e_altre_riserve'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*VII(?:\s*[-–)]\s*|\s+)Ris\w*\.?\s+per\s+operaz', re.I), 'sp12f_riserva_copertura_flussi'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*VIII(?:\s*[-–)]\s*|\s+)Util.*portat', re.I), 'sp12g_utili_perdite_portati'),
    (re.compile(r'^\s*(?:[A-Z]\.)?\s*X(?:\s*[-–)]\s*|\s+)Riserva negativa per azioni proprie', re.I), 'sp12h_riserva_neg_azioni_proprie'),
]

# Declared PN control total. Besides the canonical "Totale patrimonio netto", accept
# the gestionale variants "A TOTALE PATRIMONIO NETTO" (budget_341) and the section
# header "A) Patrimonio netto" that itself carries the subtotal (budget_340).
_PN_TOTAL_SPECS = [
    (re.compile(r'^\s*Totale patrimonio netto', re.I), 'pn_total'),
    (re.compile(r'^\s*[A-Z]\s+Totale patrimonio netto', re.I), 'pn_total'),
    (re.compile(r'^\s*[A-Z][.\)]\s*Patrimonio netto\b', re.I), 'pn_total'),
]
# Personnel split (B.9 a/b/c/e). The SPECIFIC single-letter lines only: the combined
# "c), d), e) trattamento ..." header starts "c)," so it cannot match 'c)\s*trattamento'.
_PERS_DETAIL_SPECS = [
    (re.compile(r'^\s*a\)\s*salari', re.I), 'ce08b_salari_stipendi'),
    (re.compile(r'^\s*b\)\s*oneri sociali', re.I), 'ce08c_oneri_sociali'),
    # CE cost line "c) trattamento di fine rapporto" — NOT the SP fund line
    # "C) Trattamento di fine rapporto di lavoro subordinato" (sp15, = 11.561) that
    # bleeds into the CE text window: the lookahead rejects the "...di lavoro" variant.
    (re.compile(r'^\s*c\)\s*trattamento di fine rapporto(?!\s+di\s+lavoro)', re.I), 'ce08a_tfr_accrual'),
    (re.compile(r'^\s*e\)\s*altri costi', re.I), 'ce08d_altri_costi_personale'),
]

_PERS_TOTAL_SPECS = [(re.compile(r'^\s*Totale costi per il personale', re.I), 'pers_total')]

def _reconcile_pn_detail(bs: Dict[str, Decimal], sp_text: str, label: str,
                         column: int = 0) -> Dict[str, Decimal]:
    """Fill sp12a..h from the explicit PN reserve lines and set sp12_riserve to their
    algebraic sum. Applied ONLY when sp11 + Σsp12* + sp13 reconciles to the printed
    'Totale patrimonio netto' (anti-masking). Recovers the dropped NEGATIVE reserve
    (utili/(perdite) portati a nuovo) that otherwise inflates equity → masked into cash."""
    if not sp_text:
        return bs
    found = _scan_labeled(sp_text, _PN_DETAIL_SPECS)
    subs = {k: v[column] for k, v in found.items() if column < len(v)}
    if not subs:
        return bs
    new_sp12 = sum(subs.values())
    sp11 = bs.get('sp11_capitale', Decimal('0'))
    sp13 = bs.get('sp13_utile_perdita', Decimal('0'))
    pn_tot = _scan_labeled(sp_text, _PN_TOTAL_SPECS).get('pn_total')
    declared_pn = pn_tot[column] if pn_tot and column < len(pn_tot) else None
    if declared_pn is None:
        return bs  # no control total to anchor on -> stay conservative
    tol = max(Decimal('2'), abs(declared_pn) * Decimal('0.005'))
    if abs(sp11 + new_sp12 + sp13 - declared_pn) > tol:
        logger.info(f"[{label}] PN detail: Σsp12*={new_sp12} + sp11 + sp13 does not "
                    f"reconcile to declared PN {declared_pn}; skipping detail fill")
        return bs
    for k, v in subs.items():
        bs[k] = v
    bs['sp12_riserve'] = new_sp12
    logger.info(f"[{label}] PN detail reconciled: sp12_riserve -> {new_sp12} "
                f"(legale={subs.get('sp12c_riserva_legale')}, "
                f"altre={subs.get('sp12e_altre_riserve')}, "
                f"utili a nuovo={subs.get('sp12g_utili_perdite_portati')})")
    return bs

def _reconcile_personale_detail(ce: Dict[str, Decimal], ce_text: str, label: str,
                                column: int = 0) -> Dict[str, Decimal]:
    """Fill ce08a/b/c/d from the explicit B.9 a/b/c/e personnel lines, gated on the
    printed 'Totale costi per il personale'. Fixes the salari/oneri split the LLM merges
    into ce08b (e.g. salari 214.698 + oneri 60.346 reported as salari 275.044)."""
    if not ce_text:
        return ce
    found = _scan_labeled(ce_text, _PERS_DETAIL_SPECS)
    subs = {k: v[column] for k, v in found.items() if column < len(v)}
    if not subs:
        return ce
    s = sum(subs.values())
    tot = _scan_labeled(ce_text, _PERS_TOTAL_SPECS).get('pers_total')
    declared = (tot[column] if tot and column < len(tot)
                else ce.get('ce08_costi_personale', Decimal('0')))
    if declared is None or declared <= 0:
        return ce
    tol = max(Decimal('2'), abs(declared) * Decimal('0.02'))
    if abs(s - declared) > tol:
        logger.info(f"[{label}] personale detail: Σsub={s} != declared total {declared}; skipping")
        return ce
    for k, v in subs.items():
        ce[k] = v
    ce['ce08_costi_personale'] = declared  # authoritative total (also fixes an LLM merge)
    logger.info(f"[{label}] personale split reconciled: salari={subs.get('ce08b_salari_stipendi')}, "
                f"oneri={subs.get('ce08c_oneri_sociali')}, tfr={subs.get('ce08a_tfr_accrual')}, "
                f"altri={subs.get('ce08d_altri_costi_personale')}")
    return ce
