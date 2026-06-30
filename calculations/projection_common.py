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
