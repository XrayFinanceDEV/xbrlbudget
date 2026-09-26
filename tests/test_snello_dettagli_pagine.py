"""enrich_pdf_details: filtro pagine e interruttore LLM per l'innesto snello."""
from decimal import Decimal as D

import pytest

from importers import detail_enrichment as de

INV = "sp05_rimanenze"
GOODS = "sp05d_prodotti_finiti"
DEBT = "sp16_debiti_breve"
BANK = "sp16a_debiti_banche_breve"


def row(id, page, amount, text="documented detail"):
    return de.SourceRow(id, page, "L", text, (D(amount),))


def test_pagine_filters_keeps_only_matching_page_rows(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    rows = [row("p1", 1, "100"), row("p2", 2, "999")]
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: rows)
    monkeypatch.setattr(de, "read_details", lambda *a: de.DetailReading())
    current, prior, report = de.enrich_pdf_details(
        "unused", {INV: D("100")}, pagine={1},
    )
    assert report["source_rows_total"] == 1
    assert report["pagine"] == [1]


def test_pagine_none_keeps_default_behaviour(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    rows = [row("p1", 1, "100"), row("p2", 2, "999")]
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: rows)
    monkeypatch.setattr(de, "read_details", lambda *a: de.DetailReading())
    current, prior, report = de.enrich_pdf_details("unused", {INV: D("100")})
    assert report["source_rows_total"] == 2
    assert "pagine" not in report


def test_pagine_matching_nothing_keeps_all_rows_and_declares_ignored(monkeypatch):
    """OCR/text-only rows carry page=0; a page filter that matches none of them
    must not collapse a real source down to zero rows (the project rule that a
    page set never restricts to zero rows)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    rows = [row("ocr1", 0, "100"), row("ocr2", 0, "999")]
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: rows)
    monkeypatch.setattr(de, "read_details", lambda *a: de.DetailReading())
    current, prior, report = de.enrich_pdf_details(
        "unused", {INV: D("100")}, pagine={2},
    )
    assert report["source_rows_total"] == 2
    assert report["pagine_ignorate"] == [2]
    assert "pagine" not in report


def test_pagine_empty_set_restricts_nothing(monkeypatch):
    """Un insieme vuoto di pagine non e' un filtro: restringe zero pagine, non le righe a zero."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    rows = [row("p1", 1, "100"), row("p2", 2, "999")]
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: rows)
    monkeypatch.setattr(de, "read_details", lambda *a: de.DetailReading())
    current, prior, report = de.enrich_pdf_details(
        "unused", {INV: D("100")}, pagine=set(),
    )
    assert report["source_rows_total"] == 2
    assert "pagine" not in report


def test_usa_llm_false_never_calls_search_details(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    rows = [row("bank", 1, "25"), row("suppliers", 1, "60")]
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: rows)

    def boom(*args, **kwargs):
        pytest.fail("search_details/read_details called with usa_llm=False")

    monkeypatch.setattr(de, "read_details", boom)
    current, prior, report = de.enrich_pdf_details(
        "unused", {DEBT: D("100")}, usa_llm=False,
    )
    assert report["reason"] == "llm_disattivato"
    # Deterministic local details still run.
    assert report.get("local_search_completed") is True


def test_usa_llm_false_ignored_when_no_api_key_reason_stays_declared(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rows = [row("bank", 1, "25"), row("suppliers", 1, "60")]
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: rows)
    current, prior, report = de.enrich_pdf_details(
        "unused", {DEBT: D("100")}, usa_llm=False,
    )
    assert report["reason"] == "llm_disattivato"


def test_usa_llm_true_default_keeps_no_api_key_reason(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rows = [row("bank", 1, "25"), row("suppliers", 1, "60")]
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: rows)
    current, prior, report = de.enrich_pdf_details("unused", {DEBT: D("100")})
    assert report["reason"] == "no_api_key"


def test_pagine_and_usa_llm_false_together(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    rows = [row("p1", 1, "100"), row("p2", 2, "999")]
    monkeypatch.setattr(de, "collect_source_rows", lambda *a, **kw: rows)

    def boom(*args, **kwargs):
        pytest.fail("search_details/read_details called with usa_llm=False")

    monkeypatch.setattr(de, "read_details", boom)
    current, prior, report = de.enrich_pdf_details(
        "unused", {INV: D("100")}, pagine={1}, usa_llm=False,
    )
    assert report["source_rows_total"] == 1
    assert report["pagine"] == [1]
    assert report["reason"] == "llm_disattivato"
