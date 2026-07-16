"""Canonical, side-effect-free calculation of the IV CEE income result.

This module is deliberately independent from SQLAlchemy and from the importers so
that the same formula can be used for dictionaries, ORM objects and projections.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Union


ZERO = Decimal("0")
CESource = Union[Mapping[str, Any], object]


@dataclass(frozen=True)
class CEResult:
    """Immutable breakdown produced by :func:`calculate_ce_result`."""

    production_value: Decimal
    production_cost: Decimal
    ebitda: Decimal
    ebit: Decimal
    financial_result: Decimal
    value_adjustments: Decimal
    value_adjustments_source: str
    extraordinary_result: Decimal
    profit_before_tax: Decimal
    taxes: Decimal
    net_profit: Decimal


def _value(source: CESource, field: str) -> Decimal:
    if isinstance(source, Mapping):
        raw = source.get(field, ZERO)
    else:
        raw = getattr(source, field, ZERO)

    if raw is None:
        return ZERO
    if isinstance(raw, Decimal):
        return raw
    return Decimal(str(raw))


def calculate_ce_result(source: CESource) -> CEResult:
    """Calculate the canonical IV CEE income-statement result.

    ``source`` may be a mapping or an object exposing the ``ceXX_*`` attributes.
    Missing and ``None`` values are treated as zero.

    The D-section rule is intentionally explicit:

    * if either ``ce17a_rivalutazioni`` or ``ce17b_svalutazioni`` is non-zero,
      the result is ``ce17a - ce17b`` and the aggregate ``ce17`` is ignored;
    * otherwise ``ce17_rettifiche_attivita_fin`` is the legacy fallback.

    This prevents double-counting when both aggregate and detailed D-section
    values are present while preserving old records that only contain ``ce17``.
    """

    get = lambda field: _value(source, field)

    production_value = (
        get("ce01_ricavi_vendite")
        + get("ce02_variazioni_rimanenze")
        + get("ce03_lavori_interni")
        + get("ce03a_incrementi_immobilizzazioni")
        + get("ce04_altri_ricavi")
    )
    production_cost = (
        get("ce05_materie_prime")
        + get("ce06_servizi")
        + get("ce07_godimento_beni")
        + get("ce08_costi_personale")
        + get("ce09_ammortamenti")
        + get("ce10_var_rimanenze_mat_prime")
        + get("ce11_accantonamenti")
        + get("ce11b_altri_accantonamenti")
        + get("ce12_oneri_diversi")
    )
    ebit = production_value - production_cost
    ebitda = ebit + get("ce09_ammortamenti")

    financial_result = (
        get("ce13_proventi_partecipazioni")
        + get("ce14_altri_proventi_finanziari")
        - get("ce15_oneri_finanziari")
        + get("ce16_utili_perdite_cambi")
    )

    rivalutazioni = get("ce17a_rivalutazioni")
    svalutazioni = get("ce17b_svalutazioni")
    if rivalutazioni != ZERO or svalutazioni != ZERO:
        value_adjustments = rivalutazioni - svalutazioni
        value_adjustments_source = "detail"
    else:
        value_adjustments = get("ce17_rettifiche_attivita_fin")
        value_adjustments_source = "aggregate"

    extraordinary_result = (
        get("ce18_proventi_straordinari") - get("ce19_oneri_straordinari")
    )
    profit_before_tax = (
        ebit
        + financial_result
        + value_adjustments
        + extraordinary_result
    )
    taxes = get("ce20_imposte")

    return CEResult(
        production_value=production_value,
        production_cost=production_cost,
        ebitda=ebitda,
        ebit=ebit,
        financial_result=financial_result,
        value_adjustments=value_adjustments,
        value_adjustments_source=value_adjustments_source,
        extraordinary_result=extraordinary_result,
        profit_before_tax=profit_before_tax,
        taxes=taxes,
        net_profit=profit_before_tax - taxes,
    )
