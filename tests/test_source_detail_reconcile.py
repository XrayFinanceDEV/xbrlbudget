"""Unit tests for reconcile_source_detail.

The helper makes a source whose typed sub-fields are empty (bilancio abbreviato
XBRL, TEBE CSV) self-consistent (aggregate == Σdetail) by booking the remainder
into each family's "altri" bucket, WITHOUT touching the aggregate or the balance,
so the forecast engine's aggregate/detail gate accepts it.
"""
from decimal import Decimal

from importers.iv_cee_hierarchy import (
    _DETAIL_GROUPS,
    check_quadratura,
    reconcile_source_detail,
)


def test_plugs_missing_detail_into_altri_bucket_without_changing_aggregate():
    bs = {
        "sp04_immob_finanziarie": Decimal("212663.00"),  # aggregate, no detail
        "sp14_fondi_rischi": Decimal("557089.00"),
    }
    report = reconcile_source_detail(bs)

    # aggregate untouched
    assert bs["sp04_immob_finanziarie"] == Decimal("212663.00")
    assert bs["sp14_fondi_rischi"] == Decimal("557089.00")
    # remainder booked into the family's "altri" bucket
    assert bs["sp04d_altri_titoli"] == Decimal("212663.00")
    assert bs["sp14d_altri_fondi"] == Decimal("557089.00")
    # detail now reconstructs the aggregate exactly
    assert (
        sum(bs.get(k, Decimal("0")) for k in _DETAIL_GROUPS["sp04_immob_finanziarie"])
        == bs["sp04_immob_finanziarie"]
    )
    assert report["sp04d_altri_titoli"] == Decimal("212663.00")


def test_partial_detail_only_the_unexplained_remainder_moves():
    bs = {
        "sp16_debiti_breve": Decimal("150000.00"),
        "sp16a_debiti_banche_breve": Decimal("40000.00"),  # partial detail present
        "sp16d_debiti_fornitori_breve": Decimal("60000.00"),
    }
    reconcile_source_detail(bs)

    # only the 50,000 remainder goes to "altri", existing detail untouched
    assert bs["sp16a_debiti_banche_breve"] == Decimal("40000.00")
    assert bs["sp16d_debiti_fornitori_breve"] == Decimal("60000.00")
    assert bs["sp16g_altri_debiti_breve"] == Decimal("50000.00")
    assert (
        sum(bs.get(k, Decimal("0")) for k in _DETAIL_GROUPS["sp16_debiti_breve"])
        == bs["sp16_debiti_breve"]
    )


def test_negative_over_extraction_residual_is_not_swallowed():
    """When Σdetail already EXCEEDS the aggregate (a mis-mapping / over-extraction
    parser bug), the remainder is NEGATIVE and must NOT be booked into "altri" —
    doing so would create a nonsensical negative line and hide the defect. It is
    left inconsistent so the forecast engine's aggregate/detail gate still fires.
    """
    bs = {
        "sp16_debiti_breve": Decimal("100000.00"),
        "sp16a_debiti_banche_breve": Decimal("80000.00"),
        "sp16d_debiti_fornitori_breve": Decimal("60000.00"),  # Σdetail 140k > 100k
    }
    report = reconcile_source_detail(bs)
    assert "sp16g_altri_debiti_breve" not in report
    assert bs.get("sp16g_altri_debiti_breve", Decimal("0")) == Decimal("0")
    # still inconsistent on purpose -> the gate catches it
    assert not check_quadratura(bs).hierarchy_consistent


def test_is_idempotent():
    bs = {"sp05_rimanenze": Decimal("60000.00")}
    first = reconcile_source_detail(bs)
    assert first == {"sp05e_acconti": Decimal("60000.00")}
    second = reconcile_source_detail(bs)
    assert second == {}  # already consistent, nothing plugged
    assert bs["sp05e_acconti"] == Decimal("60000.00")


def test_already_consistent_source_is_untouched():
    bs = {
        "sp06_crediti_breve": Decimal("100000.00"),
        "sp06a_crediti_clienti_breve": Decimal("70000.00"),
        "sp06g_crediti_altri_breve": Decimal("30000.00"),
    }
    report = reconcile_source_detail(bs)
    assert report == {}
    assert bs["sp06g_crediti_altri_breve"] == Decimal("30000.00")


def test_ce09_split_proportional_to_asset_base():
    bs = {
        "sp02_immob_immateriali": Decimal("20000.00"),
        "sp03_immob_materiali": Decimal("180000.00"),
    }
    ce = {"ce09_ammortamenti": Decimal("40000.00")}  # aggregate only
    report = reconcile_source_detail(bs, ce)

    # 20k intangible / 200k total -> 10% to intangible, 90% to tangible
    assert ce["ce09a_ammort_immateriali"] == Decimal("4000.00")
    assert ce["ce09b_ammort_materiali"] == Decimal("36000.00")
    # detail reconstructs the aggregate exactly (no cent lost in the split)
    assert (
        ce["ce09a_ammort_immateriali"]
        + ce["ce09b_ammort_materiali"]
        + ce.get("ce09c_svalutazioni", Decimal("0"))
        + ce.get("ce09d_svalutazione_crediti", Decimal("0"))
        == ce["ce09_ammortamenti"]
    )
    assert report["ce09b_ammort_materiali"] == Decimal("36000.00")


def test_ce09_all_to_tangible_when_no_asset_base():
    bs = {"sp02_immob_immateriali": Decimal("0"), "sp03_immob_materiali": Decimal("0")}
    ce = {"ce09_ammortamenti": Decimal("5000.00")}
    reconcile_source_detail(bs, ce)
    assert ce["ce09b_ammort_materiali"] == Decimal("5000.00")
    assert ce.get("ce09a_ammort_immateriali", Decimal("0")) == Decimal("0")


def test_reconciled_source_passes_the_hierarchy_check():
    # A full balanced abbreviato-style source with only aggregates.
    bs = {
        "sp02_immob_immateriali": Decimal("20000"),
        "sp03_immob_materiali": Decimal("180000"),
        "sp05_rimanenze": Decimal("60000"),
        "sp06_crediti_breve": Decimal("140000"),
        "sp09_disponibilita_liquide": Decimal("40000"),
        "sp11_capitale": Decimal("100000"),
        "sp12_riserve": Decimal("80000"),
        "sp13_utile_perdita": Decimal("20000"),
        "sp15_tfr": Decimal("30000"),
        "sp16_debiti_breve": Decimal("150000"),
        "sp17_debiti_lungo": Decimal("60000"),
    }
    ce = {
        "ce01_ricavi_vendite": Decimal("600000"),
        "ce05_materie_prime": Decimal("200000"),
        "ce06_servizi": Decimal("150000"),
        "ce08_costi_personale": Decimal("120000"),
        "ce09_ammortamenti": Decimal("40000"),
        "ce12_oneri_diversi": Decimal("46000"),
        "ce20_imposte": Decimal("24000"),
    }
    before = check_quadratura(bs, ce)
    assert not before.hierarchy_consistent  # aggregates without detail

    reconcile_source_detail(bs, ce)

    after = check_quadratura(bs, ce)
    assert after.hierarchy_consistent  # every family now reconciles
    # the balance is preserved (reconcile never touches an aggregate)
    assert after.sbilancio == before.sbilancio
