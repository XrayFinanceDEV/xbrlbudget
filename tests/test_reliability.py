"""Per-account reliability verdicts.

UNRELIABLE requires POSITIVE evidence of contradiction, never the mere absence
of a control - otherwise every route A/B file (which runs no contra scan) and
every abbreviated statement would be blocked.
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.reliability import (  # noqa: E402
    AccountStatus,
    ReliabilityReport,
    assess,
)

D = Decimal


def _bs(**over):
    base = {
        "sp02_immob_immateriali": D("6000"),
        "sp03_immob_materiali": D("1500000"),
        "sp11_capitale": D("10000"),
        "sp12_riserve": D("800000"),
        "sp13_utile_perdita": D("100000"),
        "sp16_debiti_breve": D("220000"),
        "sp16a_debiti_banche_breve": D("7000"),
        "sp16d_debiti_fornitori_breve": D("213000"),
        "sp17_debiti_lungo": D("0"),
        "totale_attivo": D("2000000"),
        "totale_passivo": D("2000000"),
    }
    base.update(over)
    return base


# ---------------------------------------------------------- immobilizzazioni

def test_contra_detected_but_not_applied_is_unreliable():
    """The 613 shape: the scan found 2,25M of fondi and then discarded them."""
    bs = _bs(_contra_detected=D("2247715.70"), _contra_applied=D("0"),
             _contra_reason="contro rilevati ma non applicati")
    r = assess(bs, {})
    assert r.immobilizzazioni is AccountStatus.UNRELIABLE
    assert r.all_critical_ok is False


def test_contra_applied_is_verified():
    bs = _bs(_contra_detected=D("2247715.70"), _contra_applied=D("2247715.70"),
             _contra_reason="applicato")
    r = assess(bs, {})
    assert r.immobilizzazioni is AccountStatus.VERIFIED


def test_no_contra_mass_found_is_derived_not_unreliable():
    bs = _bs(_contra_detected=D("0"), _contra_applied=D("0"),
             _contra_reason="nessuna massa contro")
    r = assess(bs, {})
    assert r.immobilizzazioni is AccountStatus.DERIVED


def test_route_ab_without_any_contra_metadata_is_derived():
    """Route A/B never runs a contra scan; absence of metadata must not block."""
    r = assess(_bs(), {})
    assert r.immobilizzazioni is AccountStatus.DERIVED
    assert r.all_critical_ok is True


# ---------------------------------------------------------- patrimonio netto

def test_pn_matching_the_printed_control_is_verified():
    r = assess(_bs(), {}, declared={"patrimonio_netto": D("910000")})
    assert r.patrimonio_netto is AccountStatus.VERIFIED


def test_pn_contradicting_the_printed_control_is_unreliable():
    r = assess(_bs(), {}, declared={"patrimonio_netto": D("500000")})
    assert r.patrimonio_netto is AccountStatus.UNRELIABLE
    assert r.all_critical_ok is False


def test_pn_without_a_printed_control_is_derived():
    r = assess(_bs(), {}, declared={})
    assert r.patrimonio_netto is AccountStatus.DERIVED


# ------------------------------------------------------------ debiti banche

def test_explicit_bank_subfields_are_verified():
    r = assess(_bs(), {})
    assert r.debiti_banche is AccountStatus.VERIFIED


def test_material_aggregate_gap_is_unreliable():
    """base_bank_debt assigns any aggregate/detail gap to BANKS, so a material
    gap means the bank figure is invented rather than read."""
    bs = _bs(sp16_debiti_breve=D("500000"))   # 280k unexplained
    r = assess(bs, {})
    assert r.debiti_banche is AccountStatus.UNRELIABLE


def test_immaterial_aggregate_gap_is_tolerated():
    bs = _bs(sp16_debiti_breve=D("220500"))   # 500 gap, below M=2000
    r = assess(bs, {})
    assert r.debiti_banche is not AccountStatus.UNRELIABLE


def test_no_bank_debt_and_no_gap_is_derived():
    bs = _bs(sp16a_debiti_banche_breve=D("0"),
             sp16d_debiti_fornitori_breve=D("220000"))
    r = assess(bs, {})
    assert r.debiti_banche is AccountStatus.DERIVED


# ------------------------------------------------------------------ payload

def test_to_dict_is_json_safe_and_carries_reasons():
    import json
    r = assess(_bs(), {})
    payload = r.to_dict()
    json.dumps(payload)          # must not raise
    assert set(payload) >= {"immobilizzazioni", "patrimonio_netto",
                            "debiti_banche", "all_critical_ok"}
    assert payload["immobilizzazioni"]["status"] == "derived"
    assert isinstance(payload["immobilizzazioni"]["reason"], str)


def test_unclassified_mass_is_carried_through_and_json_safe():
    import json
    bs = _bs(_unclassified_mass=D("4321.55"))
    r = assess(bs, {})
    assert r.unclassified_mass == D("4321.55")
    payload = r.to_dict()
    json.dumps(payload)          # must not raise
    assert payload["unclassified_mass"] == "4321.55"
