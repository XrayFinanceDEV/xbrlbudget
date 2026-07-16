"""Structural tests for the API-free, SHA-256 corpus manifest."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CORPUS_FIXTURES = Path(__file__).resolve().parent / "corpus"
BUILDER_PATH = CORPUS_FIXTURES / "build_manifest.py"
MANIFEST_PATH = CORPUS_FIXTURES / "manifest.json"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_corpus_manifest", BUILDER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


def test_manifest_builder_deduplicates_by_sha256_and_includes_csv(tmp_path):
    test_root = tmp_path / "Test"
    analysis = test_root / "_analysis"
    analysis.mkdir(parents=True)
    (test_root / "a.pdf").write_bytes(b"same-pdf")
    (test_root / "alias.pdf").write_bytes(b"same-pdf")
    (test_root / "data.csv").write_bytes(b"code,amount\n1,2\n")
    (analysis / "ignored.pdf").write_bytes(b"not-corpus")

    manifest = builder.build_manifest(test_root, analysis)

    assert manifest["summary"]["physical_files"] == 3
    assert manifest["summary"]["unique_contents"] == 2
    assert manifest["summary"]["formats"] == {"csv": 1, "pdf": 1}
    pdf = next(record for record in manifest["files"] if record["format"] == "pdf")
    assert pdf["paths"] == ["a.pdf", "alias.pdf"]
    assert len(pdf["sha256"]) == 64


def test_committed_manifest_is_reproducible_and_complete_for_local_corpus():
    if not (ROOT / "Test" / "sez-contrapposte").exists():
        pytest.skip("local corpus is not present")

    committed = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rebuilt = builder.build_manifest()

    assert committed == rebuilt
    assert rebuilt["hash_algorithm"] == "sha256"
    assert rebuilt["summary"]["unique_contents"] == 137
    assert rebuilt["summary"]["physical_files"] == 214
    assert rebuilt["summary"]["formats"] == {"csv": 1, "pdf": 121, "xbrl": 15}
    assert rebuilt["summary"]["truth_orphans"] == []
    assert len({record["sha256"] for record in rebuilt["files"]}) == 137


def test_337_verified_truth_is_pinned_to_content_not_filename():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    record = next(
        item
        for item in manifest["files"]
        if item["sha256"]
        == "70ea0d5277ec4a0ff4fcfa1e7822c0e371d5e6ebd304734985293ec16d177264"
    )

    assert record["status"] == "verified"
    assert record["route_expected"] == "trial_balance"
    assert len(record["paths"]) == 2
    assert record["truth"]["fixed_assets"] == {
        "intangible_gross": 3239.12,
        "intangible_funds": 0.0,
        "intangible_net": 3239.12,
        "tangible_gross": 67229.83,
        "tangible_funds": 62045.1,
        "tangible_net": 5184.73,
    }
    assert record["truth"]["expected_fields"] == {
        "sp02_immob_immateriali": 3239.12,
        "sp03_immob_materiali": 5184.73,
        "sp13_utile_perdita": 4287.23,
        "totale_attivo": 253076.09,
    }
