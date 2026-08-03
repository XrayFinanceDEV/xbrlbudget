"""Route C falls back to the shared IV-CEE tree before the catch-all.

_classify_ce_costi and iv_cee_hierarchy.resolve() are independent classifiers
that each miss what the other knows. _hier_reconstruct used only the former,
so a bare 'AMMORTAMENTI' mastro fell into the ce12 catch-all: totals and sp13
stayed correct (no gate fired) but EBITDA was wrong, because EBITDA = EBIT + ce09.
"""
import json
import os
import sys
from decimal import Decimal

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from importers.situazione_contabile_parser import (  # noqa: E402
    FALLBACK_FIELDS, _resolve_field)
from importers.pdf_importer import _map_sc_keys  # noqa: E402
from database.models import BalanceSheet, IncomeStatement  # noqa: E402

D = Decimal
TREE_PATH = os.path.join(ROOT, "data", "iv_cee_tree.json")


def test_resolve_field_returns_the_short_key():
    assert _resolve_field("AMMORTAMENTI", "costi") == "ce09"


def test_resolve_field_handles_a_known_financial_cost():
    assert _resolve_field("ONERI FINANZIARI", "costi") == "ce15"


def test_resolve_field_returns_none_when_unknown():
    assert _resolve_field("ACQUISTI DI BENI", "costi") is None


def test_resolve_field_rejects_a_node_from_the_wrong_statement():
    # a balance-sheet caption must not be returned when we asked for the CE
    assert _resolve_field("DISPONIBILITA' LIQUIDE", "costi", statement="ce") is None


# --------------------------------------------------------------- direction guard
#
# `statement='ce'` bounds the tree lookup to the income statement but does NOT
# constrain the SIGN: Node.side is None for every CE node, so the 'costi' /
# 'ricavi' argument enforces nothing. _hier_reconstruct adds every mastro
# POSITIVELY into the field it resolves, so a cost landing in a gain voce moves
# the result by TWICE the amount (gestione finanziaria = ce13+ce14-ce15+ce16).


@pytest.mark.parametrize("desc, wrong_field", [
    # exactly the two crossings the final review demonstrated
    ("DIFFERENZE CAMBIO PASSIVE", "ce16"),
    ("CONTRIBUTI IN CONTO ESERCIZIO", "ce04"),
    # other revenue/gain voci a cost-column mastro can reach through the tree
    ("RIVALUTAZIONI", "ce17"),
    ("PROVENTI STRAORDINARI", "ce18"),
    ("ALTRI PROVENTI FINANZIARI", "ce14"),
])
def test_a_cost_mastro_never_resolves_to_a_revenue_or_gain_voce(desc, wrong_field):
    from importers.situazione_contabile_parser import _resolve_ce_field
    # the raw tree lookup still crosses the direction - that is the bug ...
    assert _resolve_field(desc, "costi", statement="ce") == wrong_field
    # ... and the direction-constrained wrapper is what blocks it, so the
    # caller falls through to its KPI-neutral catch-all exactly as before.
    assert _resolve_ce_field(desc, "costi") is None


@pytest.mark.parametrize("desc, wrong_field", [
    ("INTERESSI PASSIVI SU MUTUI", "ce15"),
    ("AMMORTAMENTI", "ce09"),
    ("ONERI STRAORDINARI", "ce19"),
])
def test_a_revenue_mastro_never_resolves_to_a_cost_voce(desc, wrong_field):
    from importers.situazione_contabile_parser import _resolve_ce_field
    assert _resolve_field(desc, "ricavi", statement="ce") == wrong_field
    assert _resolve_ce_field(desc, "ricavi") is None


def test_the_direction_guard_still_lets_same_direction_lookups_through():
    from importers.situazione_contabile_parser import _resolve_ce_field
    # the Task 2 fix (ammortamenti out of the ce12 catch-all) must survive
    assert _resolve_ce_field("AMMORTAMENTI", "costi") == "ce09"
    assert _resolve_ce_field("ONERI FINANZIARI", "costi") == "ce15"
    assert _resolve_ce_field("ALTRI PROVENTI FINANZIARI", "ricavi") == "ce14"


def test_signed_voci_are_accepted_only_on_their_positive_side():
    """ce02, ce16 and ce17 are NET voci: a positive amount RAISES the result, so
    they may only receive a mastro printed in the revenue column. ce10 is the
    mirror case (a cost voce), so it may only receive a cost-column mastro."""
    from importers.situazione_contabile_parser import (
        _CE_COST_FIELDS, _CE_REVENUE_FIELDS)
    for signed in ("ce02", "ce16", "ce17"):
        assert signed in _CE_REVENUE_FIELDS
        assert signed not in _CE_COST_FIELDS
    assert "ce10" in _CE_COST_FIELDS
    assert "ce10" not in _CE_REVENUE_FIELDS


def test_hier_reconstruct_calls_the_direction_guarded_lookup():
    """Wiring guard. Every assertion above exercises _resolve_ce_field directly,
    so reverting _hier_reconstruct's two CE loops to the unguarded
    `_resolve_field(d, 'costi', statement='ce')` would leave them all green
    while re-opening the cost-booked-as-gain hole. Driving _hier_reconstruct for
    real needs a fully self-consistent synthetic PDF (it is gated on
    reconciling against the document's own printed totals), so pin the call
    sites instead - the guard is only worth anything if it is actually called.
    """
    import inspect
    from importers import situazione_contabile_parser as scp

    src = inspect.getsource(scp._hier_reconstruct)
    assert "_resolve_ce_field(d, 'costi')" in src
    assert "_resolve_ce_field(d, 'ricavi')" in src
    assert "_resolve_field(" not in src, (
        "_hier_reconstruct must go through the direction-guarded wrapper")


def test_the_two_allowlists_partition_every_ce_leaf_in_the_tree():
    """A voce added to data/iv_cee_tree.json without being classified in one of
    the two direction sets would be silently unreachable from the fallback."""
    from importers.situazione_contabile_parser import (
        _CE_COST_FIELDS, _CE_REVENUE_FIELDS)
    assert not (_CE_COST_FIELDS & _CE_REVENUE_FIELDS)
    known = _CE_COST_FIELDS | _CE_REVENUE_FIELDS
    leaves = {db_field.split("_", 1)[0]
              for statement, db_field in _tree_nodes_with_db_field()
              if statement == "ce"}
    assert leaves == known, (
        f"income-statement leaves not classified by direction: {leaves ^ known}")


def _tree_nodes_with_db_field():
    with open(TREE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    for statement, rows in (("bs", data["balance_sheet"]), ("ce", data["income_statement"])):
        for row in rows:
            db_field = row.get("db_field")
            if db_field:
                yield statement, db_field


def test_every_tree_short_key_is_routable_by_map_sc_keys():
    """Guard against a repeat of the sp04a incident.

    _resolve_field derives its short route-C key as db_field.split('_', 1)[0].
    That split is a mechanical string operation - it does NOT guarantee the
    result is routable. _map_sc_keys (importers/pdf_importer.py) only maps a
    short key that is in _SC_KEY_MAP, or passes a key through unchanged when
    it already contains an underscore; anything else is SILENTLY DROPPED
    (mass disappearing from the balance sheet with no gate firing). This test
    walks every node the tree can actually produce and fails loudly, naming
    the offending short key, instead of relying on a one-off assertion about
    a single field.
    """
    model_for_statement = {"bs": BalanceSheet, "ce": IncomeStatement}
    # The tree is not the only producer of short keys: FALLBACK_FIELDS names the
    # catch-all destinations the classification policy writes for mass that was
    # READ but not recognised. 'sp16g' shipped absent from _SC_KEY_MAP, which is
    # exactly the sp04a incident again — walk both sources.
    sources = list(_tree_nodes_with_db_field())
    sources += [(statement, short) for statement, short in FALLBACK_FIELDS.items()]
    for statement, db_field in sources:
        short_key = db_field.split("_", 1)[0]
        mapped = _map_sc_keys({short_key: D("1")})
        assert mapped, (
            f"short key '{short_key}' (from db_field '{db_field}') is not "
            f"routable by _map_sc_keys - the amount would be silently dropped"
        )
        full_key = next(iter(mapped))
        model = model_for_statement[statement]
        assert hasattr(model, full_key), (
            f"'{full_key}' resolved from short key '{short_key}' is not a "
            f"column on {model.__name__}"
        )


def _budget_342_pdf():
    for folder in ("Test/july_budget", "tests/debug"):
        matches = sorted(
            __import__("pathlib").Path(ROOT, folder).glob("budget_342_*.pdf"))
        if matches:
            return str(matches[0])
    return None


def test_budget_342_ammortamenti_are_not_swallowed_by_oneri_diversi():
    pdf = _budget_342_pdf()
    if pdf is None:
        pytest.skip("local regression PDF budget_342 is not available")
    sys.path.insert(0, os.path.join(ROOT, "tests"))
    from _prod_route_c_runner import run_prod_route_c

    result = run_prod_route_c(pdf)
    bs = result["bs"]
    ce = result["ce"]
    # declared in the PDF: Totale ammortamenti mastro 80 = 36.500,17
    assert abs(Decimal(ce.get("ce09_ammortamenti", 0)) - D("36500.17")) <= D("1")
    # ce12 must no longer swallow the ammortamenti. Pre-fix it was 140.918,68
    # (104.418,51 of mastri the tree genuinely does not map + 36.500,17 of
    # depreciation); post-fix it drops to 104.418,51. The residual is five
    # unmapped level-1 cost mastri (ACQUISTI DI BENI, GESTIONE VEICOLI
    # AZIENDALI, PRESTAZIONI DI LAVORO NON DIPENDENTI, SPESE AMMIN./COMM./DI
    # RAPPRESENTANZA, ONERI DIVERSI DI GESTIONE) — all inside costi della
    # produzione, so they move no subtotal and cross no KPI boundary
    # (EBITDA = EBIT + ce09 makes ce09 the only boundary here). Out of scope.
    assert Decimal(ce.get("ce12_oneri_diversi", 0)) < D("140000")
    # the result is unchanged by re-labelling costs
    assert abs(Decimal(result["sp13"]) - D("100046.26")) <= D("1")

    # --- Task 3 wiring check: the fallback must actually fire, not just exist ---
    # The `< 140000` bound above only documents the OLD bug (ammortamenti
    # leaking into ce12) and would stay green even if _hier_reconstruct's
    # Step-5 wiring were reverted to `or 'ce12'` / `or 'ce04'` and the
    # `unclassified` accumulation deleted. These two assertions are the ones
    # that actually break on a revert: `_unclassified_mass` would vanish
    # (KeyError -> falsy default, equality fails) and `ce12_oneri_diversi`
    # would jump back up by the unmapped-mastri mass (97.382,25) because the
    # four unmapped mastri (ACQUISTI DI BENI, GESTIONE VEICOLI AZIENDALI,
    # PRESTAZIONI DI LAVORO NON DIPENDENTI, SPESE AMMIN./COMM.) would land
    # there again, on top of the genuinely-recognised ONERI DIVERSI DI
    # GESTIONE (7.036,26) that belongs there.
    #
    # Measured (not asserted verbatim from the brief): the four unmapped
    # level-1 cost mastri sum to 58.604,70 + 8.773,07 + 23.172,80 + 6.831,68 =
    # 97.382,25, matching `_unclassified_mass` exactly.
    assert isinstance(bs.get("_unclassified_mass"), Decimal)
    assert abs(bs["_unclassified_mass"] - D("97382.25")) <= D("1")
    assert abs(Decimal(ce.get("ce12_oneri_diversi", 0)) - D("7036.26")) <= D("1")
