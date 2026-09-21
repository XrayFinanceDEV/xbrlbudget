"""Close additive PDF detail families without balancing either statement.

Run after extraction/enrichment and before validation/persistence. Allocations
are conventional residuals, NOT newly discovered source facts. Conflicts never
produce compensating negative details, changed aggregates or proportional splits.
"""
from decimal import Decimal

from importers.iv_cee_hierarchy import aggregates_with_details, detail_fields, residual_bucket

ZERO = Decimal('0')
# The schema has no unclassified-depreciation field. Use the existing PDF UI
# fallback, explicitly audited as conventional, not source-proved depreciation.
CE_BUCKETS = {
    'ce08_costi_personale': 'ce08d_altri_costi_personale',
    'ce09_ammortamenti': 'ce09c_svalutazioni',
}


def _decimal(value):
    return ZERO if value is None else Decimal(str(value))


def finalize_pdf_residuals(bs: dict, ce: dict | None = None) -> tuple[dict, dict | None, dict]:
    """Return copies and a JSON-safe audit, including families with no proposals.

    Missing parents cannot be inferred here. Exact positive gaps are allocated
    without a rounding tolerance, including a single cent. A negative parent
    with no detail can be carried intact in its conventional bucket (e.g. net
    negative reserves). Partial negative families are left for review: a signed
    reconciliation cannot be inferred from magnitude alone.
    """
    result_bs, result_ce = dict(bs), dict(ce) if ce is not None else None
    report = {'version': 'pdf-residuals-v1', 'status': 'completed', 'requires_review': False,
              'families': {}, 'warnings': []}
    for aggregate in aggregates_with_details():
        data = result_bs if aggregate.startswith('sp') else result_ce
        if data is None:
            continue
        fields = detail_fields(aggregate)
        values = {field: _decimal(data.get(field)) for field in fields}
        populated = any(value != ZERO for value in values.values())
        present = aggregate in data and data[aggregate] is not None
        if not present and not populated:
            continue
        total = _decimal(data.get(aggregate))
        summed = sum(values.values(), ZERO)
        difference = total - summed
        # Offsetting signed details are still details, even if their sum is 0.
        bucket = (CE_BUCKETS[aggregate] if aggregate.startswith('ce') else
                  residual_bucket(aggregate, Decimal('1') if populated else ZERO))
        audit = {'aggregate': str(total) if present else None,
                 'detail_sum_before': str(summed), 'gap_before': str(difference) if present else None,
                 'bucket': bucket, 'allocated': '0', 'basis': 'conventional_residual_not_source_detail'}
        conflict = None
        if not present:
            conflict = 'macrovoce assente con dettagli presenti'
        elif difference == ZERO:
            audit['status'] = 'already_balanced'
        elif total < ZERO and populated:
            conflict = 'macrovoce negativa con dettaglio parziale: riconciliazione dei segni da verificare'
        elif total >= ZERO and difference < ZERO:
            conflict = 'somma dei dettagli superiore alla macrovoce'
        else:
            # No change to ANY aggregate, other family, cash, CE/SP result,
            # explicit detail or maturity. Only the designated residual grows.
            data[bucket] = values[bucket] + difference
            audit.update(status='allocated', allocated=str(difference),
                         bucket_before=str(values[bucket]), bucket_after=str(data[bucket]))
            assert sum((_decimal(data.get(f)) for f in fields), ZERO) == total
        if conflict:
            audit.update(status='conflict', reason=conflict)
            report['requires_review'] = True
            report['status'] = 'conflicts'
            report['warnings'].append(
                f'RESIDUO NON ALLOCATO [{aggregate}]: {conflict}; '
                f'totale={audit["aggregate"]}, somma dettagli={summed}. Valori conservati.'
            )
        audit['detail_sum_after'] = str(sum((_decimal(data.get(f)) for f in fields), ZERO))
        report['families'][aggregate] = audit
    return result_bs, result_ce, report
