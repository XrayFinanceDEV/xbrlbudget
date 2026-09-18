"""Contract tests for the deterministic, synthetic Typst-spike fixture factory."""
from __future__ import annotations

import hashlib
import unittest
from decimal import Decimal
from pathlib import Path

from backend.app.schemas.final_report import FinalReportModel
from tools.typst.spike.fixtures import (
    CANONICAL_FIXTURE_SHA256,
    SPIKE_FIXTURE_MANIFEST,
    build_all_spike_fixtures,
    build_spike_fixture,
)


ROOT = Path(__file__).resolve().parent.parent
CANONICAL_DIR = ROOT / "tests" / "fixtures" / "final_report"
EXPECTED_ORDER = ("income_results", "margins", "cashflows", "liquidity_debt", "working_capital_days", "coverage")


class SpikeFixtureFactoryTest(unittest.TestCase):
    def test_canonical_source_files_remain_byte_for_byte_unchanged(self):
        for name, expected in CANONICAL_FIXTURE_SHA256.items():
            self.assertEqual(hashlib.sha256((CANONICAL_DIR / f"{name}.json").read_bytes()).hexdigest(), expected)

    def test_factory_is_deterministic_and_uses_ordinary_strict_validation(self):
        for name, model in build_all_spike_fixtures().items():
            first = model.model_dump(mode="json")
            second = build_spike_fixture(name).model_dump(mode="json")
            self.assertEqual(first, second)
            strict = FinalReportModel.model_validate(first)
            self.assertEqual(strict.model_hash, strict.calculate_model_hash())
            self.assertEqual(strict.source_hash, strict.calculate_source_hash())

    def test_workflow_and_year_coverage_match_manifest(self):
        models = build_all_spike_fixtures()
        self.assertEqual(tuple(models), ("bilancio", "infrannuale", "startup"))
        for name, model in models.items():
            metadata = SPIKE_FIXTURE_MANIFEST[name]
            self.assertEqual(model.practice.workflow_type, metadata["workflow"])
            self.assertEqual(len(model.forecast.years), metadata["year_count"])
            self.assertEqual([year.year for year in model.forecast.years], model.practice.periods.forecast_years)
            self.assertEqual(metadata["dscr_reference_line"], "1.00")
            self.assertFalse(hasattr(model, "dscr_reference_line"))

    def test_six_charts_are_ordered_dense_and_year_aligned(self):
        for model in build_all_spike_fixtures().values():
            self.assertEqual(tuple(chart.id for chart in model.chart_series), EXPECTED_ORDER)
            for chart in model.chart_series:
                self.assertGreaterEqual(len(chart.series), 2)
                self.assertEqual(chart.categories, model.practice.periods.forecast_years)
                self.assertTrue(all(len(metric.values) == len(chart.categories) for metric in chart.series))

    def test_chart_counterparts_agree_with_financial_lines(self):
        counterpart_statements = {
            "revenue": "income_statement", "ebitda": "income_statement", "net_result": "income_statement",
            "operating": "cashflow", "debt_service": "cashflow", "free_cashflow": "cashflow",
            "cash": "balance_sheet", "financial_debt": "balance_sheet", "receivables": "balance_sheet",
            "dso": "calculations", "dio": "calculations", "dscr": "calculations", "interest_cover": "calculations",
        }
        for model in build_all_spike_fixtures().values():
            chart_values = {metric.key: metric.values for chart in model.chart_series for metric in chart.series}
            for metric, statement in counterpart_statements.items():
                for index, year in enumerate(model.forecast.years):
                    lines = {line.code: line.value for line in getattr(year, statement)}
                    if metric in lines:
                        self.assertEqual(chart_values[metric][index], lines[metric])

    def test_synthetic_text_tables_null_negative_zero_and_decimal_strings_are_preserved(self):
        models = build_all_spike_fixtures()
        self.assertTrue(all("sintetica" in model.company.name.lower() for model in models.values()))
        self.assertTrue(all(len(model.adjustments.entries) == 18 for model in models.values()))
        # Per CHIAVE, non per posizione: le sezioni sono sette e il loro ordine
        # è quello del catalogo, non un dettaglio che questo test debba fissare.
        def section(model, key):
            return next(s for s in model.assumption_sections if s.key == key)
        self.assertTrue(all(len(section(model, "patrimoniale-pregresso").assumptions[0].financing_loans) == 6
                            for model in models.values()))
        self.assertTrue(all(len(model.assumption_sections[6].assumptions[0].temporary_differences) == 8 for model in models.values()))
        wire = models["startup"].model_dump(mode="json")
        self.assertIn(None, wire["chart_series"][1]["series"][0]["values"])
        all_values = [value for chart in wire["chart_series"] for metric in chart["series"] for value in metric["values"] if value is not None]
        self.assertIn("0.00", all_values)
        self.assertTrue(any(value.startswith("-") for value in all_values))
        self.assertTrue(all(isinstance(value, str) for value in all_values))
        self.assertEqual(models["bilancio"].forecast.years[0].income_statement[0].value, Decimal("125000.00"))
        self.assertEqual(models["bilancio"].model_dump(mode="json")["forecast"]["years"][0]["income_statement"][0]["value"], "125000.00")


if __name__ == "__main__":
    unittest.main()
