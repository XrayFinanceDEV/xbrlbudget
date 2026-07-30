"""Trial balances often do NOT consolidate the prior-year result into patrimonio netto.

The "bilancio 4 sezioni" family prints it as a CODE-LESS footer row in the SP
("Utile esercizio precedente  68.228,65"), outside the coded mastri block.
`_hier_collect` only keeps rows with a leading account code, so that amount used
to be dropped from the passivo side.  The SP gap then over-stated the period
result by exactly the prior-year amount and `_hier_reconstruct`'s CE cross-check
rejected an otherwise exact reconstruction (budget_342).
"""

from decimal import Decimal
from pathlib import Path
import sys

import pytest

TESTS_DIR = Path(__file__).parent
ROOT = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(ROOT))

from importers.situazione_contabile_parser import (  # noqa: E402
    _hier_prior_result,
    _is_prior_result_caption,
)

D = Decimal


def _row(y, *cells):
    """Build PyMuPDF-style word tuples for one printed row: (x, text) cells."""
    return [(x, y, x + 40.0, y + 8.0, text, 0, 0, 0) for x, text in cells]


@pytest.mark.parametrize(
    "caption",
    [
        "UTILE ESERCIZIO PRECEDENTE",
        "PERDITA ESERCIZIO PRECEDENTE",
        "UTILE ES. PRECEDENTE",
        "RISULTATO ESERCIZIO PRECEDENTE",
        "UTILI PORTATI A NUOVO",
        "UTILI (PERDITE) PORTATI A NUOVO",
        "PERDITE PORTATE A NUOVO",
    ],
)
def test_prior_result_captions_are_recognised(caption):
    assert _is_prior_result_caption(caption) is True


@pytest.mark.parametrize(
    "caption",
    [
        # the CURRENT period result — it is the balancing figure, never PN
        "UTILE DEL PERIODO",
        "PERDITA DEL PERIODO",
        "UTILE D'ESERCIZIO",
        "UTILE DELL'ESERCIZIO",
        "RISULTATO DEL PERIODO",
        # control rows
        "TOTALE A PAREGGIO",
        "TOTALE PASSIVITA'",
        # ordinary accounts
        "BANCHE C/C E POSTA C/C",
        "RATEI E RISCONTI PASSIVI",
    ],
)
def test_non_prior_result_captions_are_rejected(caption):
    assert _is_prior_result_caption(caption) is False


def test_codeless_prior_profit_in_passivo_column_increases_pn():
    words = _row(480.0, (400.0, "Utile"), (418.0, "esercizio"), (452.0, "precedente")) \
        + _row(482.1, (541.0, "68.228,65"))
    assert _hier_prior_result(words, 308.7, 1e9) == D("68228.65")


def test_codeless_prior_loss_in_passivo_column_decreases_pn():
    words = _row(480.0, (400.0, "Perdita"), (418.0, "esercizio"), (452.0, "precedente")) \
        + _row(482.1, (541.0, "12.500,00"))
    assert _hier_prior_result(words, 308.7, 1e9) == D("-12500.00")


def test_coded_prior_result_row_is_not_double_counted():
    """A prior result carrying an account code already sits inside a level-1 mastro
    (e.g. 23 CAPITALE E RISERVE); collecting it again would double-count it."""
    words = _row(480.0, (400.0, "23.05.01"), (430.0, "Utili"), (452.0, "portati"),
                 (470.0, "a"), (478.0, "nuovo"), (541.0, "68.228,65"))
    assert _hier_prior_result(words, 308.7, 1e9) == D("0")


def test_current_period_result_is_never_collected_as_pn():
    words = _row(503.0, (400.0, "Utile"), (421.0, "del"), (436.0, "periodo")) \
        + _row(505.4, (540.0, "100.046,26"))
    assert _hier_prior_result(words, 308.7, 1e9) == D("0")


def _budget_342_pdf():
    for folder in ("Test/july_budget", "tests/debug"):
        matches = sorted((ROOT / folder).glob("budget_342_*.pdf"))
        if matches:
            return matches[0]
    return None


def test_budget_342_four_sections_reconciles_with_prior_result_in_pn():
    """End-to-end: the prior result lands in PN, so the SP gap equals the CE result
    and the hierarchical reconstruction is accepted instead of falling back to the
    masked best-effort extraction."""
    pdf = _budget_342_pdf()
    if pdf is None:
        pytest.skip("local regression PDF budget_342 is not available")

    from _prod_route_c_runner import run_prod_route_c

    result = run_prod_route_c(str(pdf))

    assert result["masked"] is False
    assert result["quadra"] is True
    assert result["plug_residual"] == D("0")
    # declared TOTALE ATTIVITA' 1.999.306,21 gross, less 821.807,32 of fondi
    assert result["totale_attivo"] == D("1177498.89")
    # declared "Utile del periodo"
    assert result["sp13"] == D("100046.26")
    # declared "Utile esercizio precedente", parked in utili portati a nuovo
    assert result["bs"].get("sp12_riserve", D(0)) >= D("68228.65")
