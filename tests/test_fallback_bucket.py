"""Materiality + criticality policy for unclassified mass.

A plug INVENTS mass to make a sheet balance and is forbidden. A fallback
LABELS mass that was actually read and is allowed - but never onto a tier-0
account, because those decide every KPI (a fondo ammortamento landing in
'altri debiti' inflates assets and debts together and breaks PFN, ROI,
indipendenza finanziaria and both rating models at once).
"""
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.situazione_contabile_parser import (  # noqa: E402
    TIER0_FIELDS,
    fallback_bucket,
    materiality_threshold,
)

D = Decimal


def test_threshold_has_an_absolute_floor_of_1000():
    assert materiality_threshold(D("100000")) == D("1000")


def test_threshold_scales_with_total_assets():
    assert materiality_threshold(D("10000000")) == D("10000")


def test_threshold_of_zero_total_is_the_floor():
    assert materiality_threshold(D("0")) == D("1000")


def test_small_cost_goes_silently_to_servizi():
    field, severity = fallback_bucket("QUALCOSA", "ce", D("500"), D("1000000"))
    assert field == "ce06"
    assert severity == "silent"


def test_material_cost_is_recorded():
    field, severity = fallback_bucket("QUALCOSA", "ce", D("50000"), D("1000000"))
    assert field == "ce06"
    assert severity == "recorded"


def test_balance_sheet_fallback_is_altri_debiti():
    field, _severity = fallback_bucket("QUALCOSA", "bs", D("500"), D("1000000"))
    assert field == "sp16g"


def test_fallback_field_is_usable_before_the_total_is_known():
    """A classification loop knows the amount long before the sheet total, so it
    needs the destination without a materiality verdict."""
    from importers.situazione_contabile_parser import fallback_field
    assert fallback_field("ce") == "ce06"
    assert fallback_field("bs") == "sp16g"


@pytest.mark.parametrize("target", ["sp02", "sp03", "sp12", "sp16a", "ce09"])
def test_tier0_targets_are_refused(target):
    with pytest.raises(ValueError):
        fallback_bucket("F.DO AMM. FABBRICATI", "bs", D("500"), D("1000000"),
                        target=target)


def test_tier0_set_covers_the_critical_accounts():
    for f in ("sp02", "sp03", "sp04", "sp11", "sp12", "sp13", "sp16a", "sp17a"):
        assert f in TIER0_FIELDS
