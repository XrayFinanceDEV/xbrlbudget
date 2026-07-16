"""Deterministic (LLM-free) tests for SP/CE page-range splitting.

These lock the page-routing that decides which text reaches the balance-sheet
vs income-statement extractor. A leak of the Conto Economico into the SP text
makes the LLM mis-map values and the import fails with the cryptic
"Balance sheet does not balance".
"""

from pathlib import Path

import pytest

from importers.pdf_extractor_llm import extract_relevant_pages, find_section_pages


ROOT = Path(__file__).resolve().parents[1]
# budget_585: IV-CEE with a 4-column (2025/2024/DIFFERENZA/SCOST.%) layout whose
# closing total is printed as "TOTALE STATO PATRIMONIALE - PASSIVO" (spaced dash)
# and whose CE page carries a stale "PASSIVO E PATRIMONIO NETTO" running header.
# Regression: the spaced-dash SP_END anchor used to be missed, so sp_end fell
# back forward and swallowed the CE page into the SP text.
BUDGET_585 = ROOT / "Test" / "july_budget" / "budget_585_INQCEE-001.pdf"


@pytest.mark.skipif(not BUDGET_585.exists(), reason="local corpus is not present")
def test_ce_does_not_leak_into_sp_text_when_passivo_total_has_spaced_dash():
    sp_pages, ce_pages = find_section_pages(str(BUDGET_585))

    # Page 2 is the Conto Economico body; it must NOT be part of the SP range.
    assert 2 not in sp_pages, f"CE page leaked into SP range: {sorted(sp_pages)}"

    sp_text, ce_text = extract_relevant_pages(str(BUDGET_585))
    sp_upper = sp_text.upper()

    # The SP text must carry the whole balance sheet ...
    assert "TOTALE STATO PATRIMONIALE - PASSIVO" in sp_upper
    assert "TOTALE DEBITI" in sp_upper
    # ... but none of the income-statement bodies that would confuse the mapper.
    assert "RICAVI DELLE VENDITE" not in sp_upper
    assert "COSTI DELLA PRODUZIONE" not in sp_upper

    # The CE extractor still receives the income statement.
    assert "VALORE DELLA PRODUZIONE" in ce_text.upper()
