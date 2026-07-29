"""Unit tests for the MinerU → pipeline adapter, against the real 3.2.0 fixture."""
import json
import os
from decimal import Decimal

import pytest

from importers.mineru_adapter import (
    MinerUExtractionContext,
    build_extraction_context,
    extract_ivcee_candidate,
    normalize_italian_number,
)

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "mineru")


def _raw_result():
    with open(os.path.join(FIX, "file_parse_response.json"), encoding="utf-8") as fh:
        payload = json.load(fh)
    stem = next(iter(payload["results"]))
    block = payload["results"][stem]
    return {
        "md_content": block["md_content"],
        "content_list": block["content_list"],
        "middle_json": block["middle_json"],
        "version": payload.get("version"),
    }


# --------------------------------------------------------------------------- #
# Italian number normalization (§6.2)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "token,expected",
    [
        ("1.234,56", Decimal("1234.56")),
        ("-1.234,56", Decimal("-1234.56")),
        ("(1.234,56)", Decimal("-1234.56")),
        ("1.234,56-", Decimal("-1234.56")),
        ("442.263,65-", Decimal("-442263.65")),
        ("0,00", Decimal("0.00")),
        ("1.000.000", Decimal("1000000")),
    ],
)
def test_normalize_italian_number(token, expected):
    assert normalize_italian_number(token) == expected


@pytest.mark.parametrize("token", ["", "abc", "12,34,56", "1..234", "n/a", "-"])
def test_normalize_ambiguous_returns_none(token):
    assert normalize_italian_number(token) is None


# --------------------------------------------------------------------------- #
# Context building against the anonymized MinerU 3.2.0 contract fixture
# --------------------------------------------------------------------------- #
def test_build_context_real_fixture():
    ctx = build_extraction_context(_raw_result())
    assert isinstance(ctx, MinerUExtractionContext)
    assert ctx.mineru_version == "3.2.0"
    assert ctx.raw_format == "mineru_pipeline_v1"
    assert ctx.page_count == 2
    assert ctx.table_count == 2
    assert "Bilancio al 31/12/2024" in ctx.full_text
    # tables parsed into rows
    assert len(ctx.rows) > 0


def test_build_context_detects_years():
    ctx = build_extraction_context(_raw_result())
    # header row is "31/12/2024   31/12/2023"
    assert ctx.current_year == 2024
    assert ctx.comparative_year == 2023


def test_build_context_headings_present():
    ctx = build_extraction_context(_raw_result())
    assert any("bilancio" in h.lower() or "economico" in h.lower() for h in ctx.headings)


def test_build_context_empty_input():
    ctx = build_extraction_context({"md_content": "", "content_list": "", "middle_json": "", "version": None})
    assert ctx.full_text == ""
    assert ctx.table_count == 0
    assert ctx.rows == ()


def test_build_context_malformed_json_does_not_crash():
    ctx = build_extraction_context(
        {"md_content": "Testo", "content_list": "{bad json", "middle_json": "also bad", "version": "3.2.0"}
    )
    assert ctx.full_text == "Testo"
    assert ctx.table_count == 0


def test_table_rows_have_cells_with_coordinates():
    ctx = build_extraction_context(_raw_result())
    # every cell keeps row/column/page provenance
    a_row = next((r for r in ctx.rows if r.cells), None)
    assert a_row is not None
    for c in a_row.cells:
        assert c.row >= 0 and c.column >= 0 and c.page >= 0


def test_structured_rows_build_balanced_current_and_prior_candidates():
    ctx = build_extraction_context(_raw_result())
    candidate = extract_ivcee_candidate(ctx)

    assert candidate is not None
    assert candidate.current_bs["totale_attivo"] == Decimal("100")
    assert candidate.current_bs["totale_passivo"] == Decimal("100")
    assert candidate.current_bs["sp03_immob_materiali"] == Decimal("40")
    assert candidate.current_bs["sp09_disponibilita_liquide"] == Decimal("60")
    assert candidate.current_bs["sp12c_riserva_legale"] == Decimal("10")
    assert candidate.current_ce["ce01_ricavi_vendite"] == Decimal("30")
    assert candidate.current_ce["ce06_servizi"] == Decimal("10")
    assert candidate.prior_bs is not None
    assert candidate.prior_ce is not None
    assert candidate.prior_bs["totale_attivo"] == Decimal("90")


def test_structured_candidate_declines_without_both_printed_side_totals():
    ctx = build_extraction_context(
        {
            "md_content": "Stato Patrimoniale",
            "content_list": [
                {
                    "type": "table",
                    "page_idx": 0,
                    "table_caption": ["Stato Patrimoniale Attivo"],
                    "table_body": (
                        "<table><tr><td>Disponibilita liquide</td><td>100</td></tr>"
                        "<tr><td>Totale attivo</td><td>100</td></tr></table>"
                    ),
                }
            ],
            "middle_json": "",
            "version": "3.2.0",
        }
    )
    assert extract_ivcee_candidate(ctx) is None
