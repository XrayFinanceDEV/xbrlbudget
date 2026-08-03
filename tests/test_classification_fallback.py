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

from importers.situazione_contabile_parser import _resolve_field  # noqa: E402
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
    for statement, db_field in _tree_nodes_with_db_field():
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
