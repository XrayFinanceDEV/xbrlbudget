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

# Existing-debt repayment is a BANK plan and therefore uses the total bank
# exposure (entro + oltre 12 mesi). Bonds and other lenders have distinct legal
# maturities and must never be silently amortised as bank debt.
_BANK_FIELDS = ('sp16a_debiti_banche_breve', 'sp17a_debiti_banche_lungo')
_NON_BANK_SHORT_FIELDS = (
    'sp16b_debiti_altri_finanz_breve',
    'sp16c_debiti_obbligazioni_breve',
    'sp16d_debiti_fornitori_breve',
    'sp16e_debiti_tributari_breve',
    'sp16f_debiti_previdenza_breve',
    'sp16g_altri_debiti_breve',
)
_NON_BANK_LONG_FIELDS = (
    'sp17b_debiti_altri_finanz_lungo',
    'sp17c_debiti_obbligazioni_lungo',
    'sp17d_debiti_fornitori_lungo',
    'sp17e_debiti_tributari_lungo',
    'sp17f_debiti_previdenza_lungo',
    'sp17g_altri_debiti_lungo',
)


def base_bank_debt(getter: Callable[[str], Decimal]) -> Decimal:
    """Base-year bank debt across both maturity buckets.

    Positive aggregate/detail gaps from abbreviated statements are assigned to
    banks, matching the import/forecast convention used elsewhere in the app.
    """
    explicit_banks = sum((getter(f) for f in _BANK_FIELDS), ZERO)
    short_gap = getter('sp16_debiti_breve') - (
        getter('sp16a_debiti_banche_breve')
        + sum((getter(f) for f in _NON_BANK_SHORT_FIELDS), ZERO)
    )
    long_gap = getter('sp17_debiti_lungo') - (
        getter('sp17a_debiti_banche_lungo')
        + sum((getter(f) for f in _NON_BANK_LONG_FIELDS), ZERO)
    )
    return explicit_banks + max(ZERO, short_gap) + max(ZERO, long_gap)


def base_financial_long_term_debt(getter: Callable[[str], Decimal]) -> Decimal:
    """Backward-compatible alias for the bank-debt repayment base."""
    return base_bank_debt(getter)


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
    bank_debt = base_bank_debt(getter)
    return bank_debt / years if bank_debt > ZERO else ZERO


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


def tax_closing_position(opening_credit, opening_debt, current_tax, advances):
    """Return ``(closing_credit, closing_debt)`` after annual tax settlement.

    The two sides are mutually exclusive and non-negative; overpayments are
    reclassified to tax credits instead of producing a negative liability.
    """
    opening_net_debt = (opening_debt or ZERO) - (opening_credit or ZERO)
    closing_net_debt = opening_net_debt + (current_tax or ZERO) - (advances or ZERO)
    return max(ZERO, -closing_net_debt), max(ZERO, closing_net_debt)


def deferred_tax_position(lines, default_tax_rate):
    """Calculate deferred-tax assets/liabilities from temporary differences.

    Every line contains a tax base roll-forward (opening + additions - reversals),
    a kind (``deductible`` or ``taxable``), a maturity (``short``/``long``) and
    an optional percentage tax rate.  Returns closing DTA split by maturity, the
    closing deferred-tax liability and the P&L deferred-tax expense (negative for
    a benefit).  Empty input is a strict no-op.
    """
    short_asset = ZERO
    long_asset = ZERO
    liability = ZERO
    deferred_expense = ZERO
    default_rate = Decimal(str(default_tax_rate or ZERO)) / Decimal('100')

    for line in lines or ():
        opening_base = max(ZERO, Decimal(str(line.get('opening_amount') or ZERO)))
        additions = max(ZERO, Decimal(str(line.get('additions') or ZERO)))
        reversals = max(ZERO, Decimal(str(line.get('reversals') or ZERO)))
        closing_base = max(ZERO, opening_base + additions - reversals)
        raw_rate = line.get('tax_rate')
        rate = (
            Decimal(str(raw_rate)) / Decimal('100')
            if raw_rate is not None else default_rate
        )
        opening_tax = opening_base * rate
        closing_tax = closing_base * rate

        if line.get('kind', 'deductible') == 'taxable':
            liability += closing_tax
            deferred_expense += closing_tax - opening_tax
        else:
            if line.get('maturity', 'short') == 'long':
                long_asset += closing_tax
            else:
                short_asset += closing_tax
            deferred_expense -= closing_tax - opening_tax

    return {
        'short_asset': short_asset,
        'long_asset': long_asset,
        'liability': liability,
        'deferred_expense': deferred_expense,
    }


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

    In addition to the legacy keys, a loan may contain ``opening_residual``
    (already present in the base-year bank debt), ``grace_years`` and
    ``balloon_pct``. Grace years are interest-only; the balloon is paid with the
    final instalment. Returns ``(0, 0, 0)`` for an empty list (no-op)."""
    raised = ZERO
    repayment = ZERO
    interest = ZERO
    for loan in loans or ():
        raise_year = loan['year']
        amount = Decimal(str(loan.get('amount') or ZERO))
        opening_residual = Decimal(str(loan.get('opening_residual') or ZERO))
        principal = amount + opening_residual
        duration = int(Decimal(str(loan.get('duration') or ZERO)))
        rate = Decimal(str(loan.get('rate') or ZERO))
        grace_years = int(Decimal(str(loan.get('grace_years') or ZERO)))
        balloon_pct = Decimal(str(loan.get('balloon_pct') or ZERO)) / Decimal('100')
        if principal <= ZERO or duration <= 0 or grace_years >= duration:
            continue
        if target_year == raise_year:
            raised += amount
        elapsed = target_year - raise_year           # whole years since raised
        if 0 <= elapsed < duration:
            balloon = principal * max(ZERO, min(Decimal('1'), balloon_pct))
            amort_years = duration - grace_years
            annual_principal = (principal - balloon) / Decimal(amort_years)
            previous_amort_years = max(0, elapsed - grace_years)
            opening = max(
                ZERO,
                principal - annual_principal * Decimal(previous_amort_years),
            )
            current_repayment = ZERO
            if elapsed >= grace_years:
                current_repayment = annual_principal
                if elapsed == duration - 1:
                    current_repayment += balloon
            repayment += min(opening, current_repayment)
            interest += opening * rate
    return raised, repayment, interest
