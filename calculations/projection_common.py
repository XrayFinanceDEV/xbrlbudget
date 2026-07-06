"""
Shared projection rules — the "kernel" called by BOTH forecasting engines.

`forecast_engine` (budget: N years concatenated) and `intra_year_engine`
(infrannuale: one partial period annualised) are two ORCHESTRATORS. They
legitimately differ in HOW they reach the year to project — that difference
stays in each engine. But the per-line CALCULATION RULES must be identical in
both: they are facts about the world (a fixed debt instalment does not change
whether you look at the company over 3 months or 5 years).

Keeping a single implementation of each rule here means a fix lands once and is
correct by construction in both engines. This module was created to end the
duplication that let the debt-repayment amortisation (P2) be correct in the
budget engine while silently staying flat in the intra-year engine.

Each function takes a ``getter(field_name) -> Decimal`` accessor so each engine
can pass its own base-year reader (``_base`` / ``_get_field``) without this
module depending on the ORM object shape.
"""
from decimal import Decimal
from typing import Callable

ZERO = Decimal('0')

# Long-term FINANCIAL debt that the existing-debt repayment plan amortises:
# banks (sp17a) + bonds (sp17c). 'Altri finanziatori' (sp17b) amortise on their
# OWN plan (see altri_finanz_repayment_instalment); trade / tax / social-security
# / other long-term debts are non-financial and are NOT repaid by the plan.
_FIN_LONG_FIELDS = ('sp17a_debiti_banche_lungo', 'sp17c_debiti_obbligazioni_lungo')
_NON_FIN_LONG_FIELDS = (
    'sp17b_debiti_altri_finanz_lungo',
    'sp17d_debiti_fornitori_lungo',
    'sp17e_debiti_tributari_lungo',
    'sp17f_debiti_previdenza_lungo',
    'sp17g_altri_debiti_lungo',
)


def base_financial_long_term_debt(getter: Callable[[str], Decimal]) -> Decimal:
    """Base-year long-term FINANCIAL debt the repayment plan amortises:
    banche + obbligazioni, PLUS any positive 'abbreviato gap' (the sp17
    aggregate minus all known sub-fields — what an abbreviato import leaves when
    only the total is present, which both engines allocate to banks).

    Excludes 'altri finanziatori' (repaid on its own plan) and the non-financial
    long-term debts, so there is no double counting and no over-repayment.
    """
    banks_bonds = sum((getter(f) for f in _FIN_LONG_FIELDS), ZERO)
    non_financial = sum((getter(f) for f in _NON_FIN_LONG_FIELDS), ZERO)
    gap = getter('sp17_debiti_lungo') - (banks_bonds + non_financial)
    return banks_bonds + (gap if gap > ZERO else ZERO)


def financial_repayment_instalment(getter: Callable[[str], Decimal], repay_years) -> Decimal:
    """Fixed annual instalment on the base-year financial long-term debt, so e.g.
    a 100k loan on a 5-year plan drops by 20k/year and fully amortises to zero
    after ``repay_years``. Returns ZERO when the plan is unset / non-positive or
    there is no financial debt to repay (no-op — zero regression)."""
    if repay_years is None:
        return ZERO
    years = Decimal(str(repay_years))
    if years <= ZERO:
        return ZERO
    base_fin_long = base_financial_long_term_debt(getter)
    return base_fin_long / years if base_fin_long > ZERO else ZERO


def altri_finanz_repayment_instalment(getter: Callable[[str], Decimal], altri_years) -> Decimal:
    """Fixed annual instalment on the base-year 'altri finanziatori' debt (sp17b)
    — e.g. an intra-group loan — repaid on its own plan, independent of the bank
    debt. Returns ZERO when the plan is unset / non-positive."""
    if altri_years is None:
        return ZERO
    years = Decimal(str(altri_years))
    if years <= ZERO:
        return ZERO
    return getter('sp17b_debiti_altri_finanz_lungo') / years


# ── TFR (trattamento di fine rapporto) accrual ──
# The yearly TFR accrual is the statutory quota "retribuzione / 13,5". We use the
# projected "salari e stipendi" (ce08b) as the retribuzione base. When an import
# only carries the aggregate personnel cost (no B.9 sub-split), ce08b is 0 and we
# estimate the salary base as 70% of the total personnel cost (oneri sociali /
# TFR / altri make up the remaining ~30%). This drives BOTH the P&L accrual line
# (ce08a) and the TFR fund growth (sp15 = prev + ce08a) in both engines, so the
# fund no longer stays flat when the base year lacks the TFR sub-line.
TFR_DIVISOR = Decimal('13.5')
TFR_SALARY_FALLBACK_PCT = Decimal('0.70')


def tfr_accrual_quota(salari, personale_totale) -> Decimal:
    """Annual TFR accrual = salari e stipendi / 13,5. Falls back to 70% of the
    total personnel cost as the salary base when salari are not broken out.
    Returns ZERO when there is no usable base (no-op)."""
    salari = salari or ZERO
    personale_totale = personale_totale or ZERO
    base = salari if salari > ZERO else personale_totale * TFR_SALARY_FALLBACK_PCT
    return base / TFR_DIVISOR if base > ZERO else ZERO


# ── NEW financing raised DURING the plan ──
# Each forecast year's `financing_amount` assumption is a NEW loan raised that
# year (IMPORTO FINANZIAMENTO), linearly amortised (rata = amount / durata) over
# its `financing_duration_years` (DURATA MEDIA), with interest (% TASSO INTERESSE
# PASSIVO) accruing on the year-OPENING outstanding balance.
#
# This is DIFFERENT from `financial_repayment_instalment`, which amortises the
# BASE-year debt on a single plan: here the loans are born DURING the plan, in
# possibly several different years, so the schedule must be assembled across all
# forecast years — a single per-year `assumption` can't see it. The engine builds
# the loan list once (from every assumption) and asks this kernel, per target
# year, for the three figures it needs to keep the balance sheet and the P&L in
# sync: what was raised, what is repaid, and the interest on the residual.
def new_financing_schedule(loans, target_year):
    """For the NEW loans raised during the plan, return the
    ``(raised, repayment, interest)`` totals for ``target_year``:

    - ``raised``     — new financing raised IN ``target_year`` (added to sp17a).
    - ``repayment``  — straight-line instalment due in ``target_year`` across all
      loans still inside their amortisation window (subtracted from sp17a).
    - ``interest``   — interest for ``target_year`` = rate × the loan's OPENING
      outstanding; this is what the P&L (ce15) charges.

    Each loan is a dict ``{'year', 'amount', 'duration', 'rate'}`` (rate already a
    fraction, e.g. 0.05). A loan raised in year R with amount A and duration D
    pays rata ≈ A/D in years R … R+D-1 and is fully amortised after D years.
    Interest in year Y (R ≤ Y < R+D) is ``rate × A × (1 - (Y-R)/D)`` — on the
    balance at the START of Y, so the year it is raised charges interest on the
    full A. Repayment is clamped to the residual so a fractional D can't push the
    debt below zero. Returns ``(0, 0, 0)`` for an empty list (no-op)."""
    raised = ZERO
    repayment = ZERO
    interest = ZERO
    for loan in loans or ():
        raise_year = loan['year']
        amount = loan['amount'] or ZERO
        duration = loan['duration'] or ZERO
        rate = loan['rate'] or ZERO
        if amount <= ZERO or duration <= ZERO:
            continue
        if target_year == raise_year:
            raised += amount
        elapsed = target_year - raise_year           # whole years since raised
        if 0 <= elapsed < duration:                  # still amortising
            opening = amount * (Decimal('1') - Decimal(elapsed) / duration)
            opening = opening if opening > ZERO else ZERO
            repayment += min(amount / duration, opening)
            interest += opening * rate
    return raised, repayment, interest
