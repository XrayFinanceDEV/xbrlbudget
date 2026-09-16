"""Semantic PDF regression checks: use the pinned compiler, never a browser."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import fitz
import pytest

from tools.typst.spike.fixtures import build_spike_fixture
from tools.typst.spike.packages import HERE, prepare_packages
from tools.typst.spike.run import italian, validate_pdf

TYPST = HERE.parent / "bin" / "typst"


@pytest.fixture(scope="module")
def sample():
    if not TYPST.exists() or not shutil.which("pdftotext") or not shutil.which("pdffonts"):
        pytest.skip("install the pinned dev toolchain and Poppler to run PDF spike integration tests")
    with tempfile.TemporaryDirectory(prefix="typst-semantic-test-") as tmp:
        output = Path(tmp)
        for file in HERE.glob("*.typ"):
            shutil.copyfile(file, output / file.name)
        model = build_spike_fixture("startup").model_dump(mode="json")
        (output / "startup.json").write_text(json.dumps(model))
        env = {k: v for k, v in os.environ.items() if not k.startswith("TYPST_")}
        for state in ("final", "draft"):
            subprocess.run([str(TYPST), "compile", "--root", tmp, "--ignore-system-fonts",
                "--package-path", str(output / "empty"), "--package-cache-path", str(output / "empty"),
                "--input", f"state={state}", str(output / "report.typ"), str(output / f"{state}.pdf")],
                env=env, check=True, capture_output=True, timeout=30)
        yield output, model


def test_actual_pdf_has_vector_graphics_embedded_fonts_and_contract_values(sample):
    output, model = sample
    result = validate_pdf(output / "final.pdf", model, draft=False)
    assert result["raster_images"] == 0
    assert result["vector_paths"] > 100
    assert result["pages"] > 3
    assert result["semantic_checks"] > 90


def test_actual_draft_watermark_is_present_on_every_page(sample):
    output, model = sample
    validate_pdf(output / "draft.pdf", model, draft=True)
    with pytest.raises(ValueError, match="watermark missing"):
        validate_pdf(output / "final.pdf", model, draft=True)


def test_missing_chart_value_really_fails_the_semantic_check(sample):
    output, original = sample
    model = copy.deepcopy(original)
    model["chart_series"][0]["series"][0]["values"][0] = "987654321.09"
    with pytest.raises(ValueError, match="missing semantic content"):
        validate_pdf(output / "final.pdf", model, draft=False)


def test_missing_body_heading_fails_even_when_it_remains_in_toc(sample):
    output, model = sample
    doc = fitz.open(output / "final.pdf")
    removed = False
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            spans = [s for line in block.get("lines", []) for s in line["spans"]]
            if any("07 ·" in s["text"] and s["size"] >= 20 for s in spans):
                page.add_redact_annot(fitz.Rect(block["bbox"]), fill=(1, 1, 1))
                removed = True
        page.apply_redactions()
    assert removed
    path = output / "missing-body.pdf"
    doc.save(path)
    with pytest.raises(ValueError, match="missing section body heading"):
        validate_pdf(path, model, draft=False)


def test_incorrect_pdf_signature_fails_before_reading_content(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a PDF")
    with pytest.raises(ValueError, match="signature"):
        validate_pdf(path, {}, draft=False)


@pytest.mark.parametrize("raw,expected", [("-1250.50", "−1.250,50"), ("0.00", "0,00"), (None, "n.d.")])
def test_italian_text_format_retains_wire_precision(raw, expected):
    assert italian(raw) == expected


def test_altered_package_archive_is_rejected_before_extraction(tmp_path):
    archives = tmp_path / "archives"
    archives.mkdir()
    (archives / "cetz-plot-0.1.4.tar.gz").write_bytes(b"altered archive")
    with pytest.raises(ValueError, match="checksum mismatch"):
        prepare_packages(tmp_path)
    assert not (tmp_path / "packages").exists()
