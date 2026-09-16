"""Reproducible offline comparison of three chart backends on the M1 contract.

This is a development spike. It does not implement the production renderer.
Linux user/network namespaces, Poppler and PyMuPDF are required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import fitz

from tools.typst.spike.fixtures import build_all_spike_fixtures
from tools.typst.spike.packages import HERE, prepare_packages

SECTIONS = (
    "02 · Sintesi esecutiva", "03 · Origine e qualità dei dati",
    "04 · Rettifiche apportate", "06 · Ipotesi del budget",
    "07 · Conto economico previsionale", "08 · Stato patrimoniale previsionale",
    "09 · Flussi di cassa e sostenibilità finanziaria", "10 · Indicatori e rischi",
    "11 · Diagnostica e punti da verificare", "12 · Appendici e metodologia",
)


def italian(value: str | None) -> str:
    if value is None:
        return "n.d."
    sign = "−" if value.startswith("-") else ""
    integer, dot, fraction = value.lstrip("-").partition(".")
    groups = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    return sign + ".".join(groups) + ("," + fraction if dot else "")


def compact(text: str) -> str:
    return "".join(text.replace("−", "-").replace("’", "'").replace("\u00ad", "").split())


def validate_pdf(path: Path, model: dict, *, draft: bool) -> dict:
    if not path.read_bytes().startswith(b"%PDF-"):
        raise ValueError("missing PDF signature")
    doc = fitz.open(path)
    texts = [page.get_text() for page in doc]
    text = "\n".join(texts)
    extracted = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                               capture_output=True, text=True, check=True).stdout
    expected_sections = list(SECTIONS)
    closing = "05 · Dall'infrannuale alla chiusura"
    if model["practice"]["workflow_type"] == "infrannuale":
        expected_sections.append(closing)
    elif compact(closing) in compact(extracted):
        raise ValueError("unexpected interim section")
    expected = expected_sections + [model["model_hash"], model["source_hash"]]
    headings = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            headings.append("".join(span["text"] for line in block.get("lines", [])
                                   for span in line["spans"] if span["size"] >= 20))
    for heading in expected_sections:
        if not any(compact(heading) in compact(actual) for actual in headings):
            raise ValueError(f"missing section body heading: {heading}")
    expected.extend(italian(v) for c in model["chart_series"] for s in c["series"] for v in s["values"])
    expected.extend(italian(a["edit_delta"]) for a in model["adjustments"]["entries"])
    expected.extend(a["edited_label"] for a in model["adjustments"]["entries"])
    for needle in expected:
        if compact(needle) not in compact(extracted) and compact(needle) not in compact(text):
            raise ValueError(f"missing semantic content: {needle}")
    if draft and not all("BOZZA" in t for t in texts):
        raise ValueError("draft watermark missing on a page")
    if not draft and any("BOZZA" in t for t in texts):
        raise ValueError("unexpected draft watermark")
    if any(len(compact(t)) < 100 for t in texts):
        raise ValueError("unexpected empty page")
    images = sum(len(page.get_images()) for page in doc)
    vectors = sum(len(page.get_drawings()) for page in doc)
    if images or not vectors:
        raise ValueError("expected vector-only graphics")
    fonts = subprocess.run(["pdffonts", str(path)], capture_output=True, text=True, check=True).stdout
    rows = fonts.splitlines()[2:]
    if not rows or any("yes yes yes" not in row for row in rows):
        raise ValueError("fonts must be embedded, subset, with Unicode mappings")
    if any(abs(page.rect.width - 595.276) > 1 or abs(page.rect.height - 841.890) > 1 for page in doc):
        raise ValueError("unexpected page size")
    return {"pages": len(doc), "bytes": path.stat().st_size,
            "vector_paths": vectors, "raster_images": images,
            "embedded_fonts": len(rows), "text_characters": len(text),
            "semantic_checks": len(expected), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def compile_once(typst: Path, packages: Path, output: Path, candidate: str,
                 fixture: str, state: str, gray: bool, *, pdfa: bool = False) -> dict:
    name = f"{candidate}-{fixture}-{state}-{'gray' if gray else 'color'}"
    if pdfa:
        name += "-pdfa2u"
    pdf = output / f"{name}.pdf"
    metrics = output / f"{name}.time"
    env = {k: v for k, v in os.environ.items() if not k.startswith("TYPST_")}
    command = ["unshare", "--user", "--map-root-user", "--net", "/usr/bin/time",
               "-f", "%M", "-o", str(metrics), str(typst), "compile",
               "--root", str(output), "--ignore-system-fonts", "--jobs", "1",
               "--creation-timestamp", "1789462800", "--package-path", str(packages),
               "--package-cache-path", str(output / "empty-cache"),
               "--input", f"candidate={candidate}", "--input", f"model={fixture}.json",
               "--input", f"state={state}", "--input", f"gray={str(gray).lower()}"]
    if pdfa:
        command += ["--pdf-standard", "a-2u"]
    command += [str(output / "report.typ"), str(pdf)]
    start = time.perf_counter()
    proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
    elapsed = time.perf_counter() - start
    peak = int(metrics.read_text().splitlines()[-1]) if metrics.exists() else None
    return {"candidate": candidate, "fixture": fixture, "state": state, "gray": gray,
            "pdfa2u": pdfa, "exit_code": proc.returncode, "seconds": round(elapsed, 4),
            "peak_rss_kib": peak, "stderr": proc.stderr.strip(), "file": pdf.name}


def run(typst: Path, output: Path, cache: Path) -> dict:
    # Verify the installed compiler against its committed manifest before running it.
    subprocess.run(["bash", str(HERE.parent / "verify.sh")],
                   env=dict(os.environ, TYPST_TOOL_ROOT=str(typst.parent.parent)), check=True)
    subprocess.run(["unshare", "--user", "--map-root-user", "--net", "true"], check=True)
    packages = prepare_packages(cache)  # offline, hashes checked; never downloads
    output.mkdir(parents=True, exist_ok=True)
    for file in HERE.glob("*.typ"):
        shutil.copyfile(file, output / file.name)
    models = {name: model.model_dump(mode="json") for name, model in build_all_spike_fixtures().items()}
    for name, model in models.items():
        (output / f"{name}.json").write_text(json.dumps(model, ensure_ascii=False, indent=2))
    results = []
    for candidate in ("native", "cetz", "primaviz"):
        for name, model in models.items():
            for state in ("final", "draft"):
                for gray in (False, True):
                    row = compile_once(typst, packages, output, candidate, name, state, gray)
                    if row["exit_code"] == 0:
                        row.update(validate_pdf(output / row["file"], model, draft=state == "draft"))
                    results.append(row)
                    print(candidate, name, state, "gray" if gray else "color", row["exit_code"], row["seconds"], flush=True)
    # First/repeated are new compiler processes; warm means filesystem cache only.
    repeats = []
    for candidate in ("native", "cetz"):
        for name in models:
            repeats.append(compile_once(typst, packages, output, candidate, name, "final", False))
    pdfa = []
    for candidate in ("native", "cetz"):
        row = compile_once(typst, packages, output, candidate, "startup", "final", False, pdfa=True)
        if row["exit_code"] == 0:
            row.update(validate_pdf(output / row["file"], models["startup"], draft=False))
        pdfa.append(row)
    # Counterexample proving the isolated namespace prevents package downloads.
    missing = output / "missing-package.typ"
    missing.write_text('#import "@preview/primaviz:0.10.0": *\nHello')
    empty = output / "no-packages"
    empty.mkdir(exist_ok=True)
    probe = subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(typst),
        "compile", "--package-path", str(empty), "--package-cache-path", str(empty),
        str(missing), str(output / "missing-package.pdf")], capture_output=True, text=True, timeout=30)
    if probe.returncode == 0:
        raise ValueError("network isolation negative control unexpectedly compiled")
    result = {"compiler": "0.15.1", "base_commit": "db8c97b", "jobs": 1,
              "network_isolation": "Linux user+network namespace, no interfaces except disconnected loopback",
              "font_policy": "embedded Libertinus Serif from pinned compiler; system fonts ignored",
              "cold_warm_definition": "first process vs repeated process; OS page cache not flushed",
              "results": results, "repeated": repeats, "pdfa2u": pdfa,
              "network_negative_control": {"exit_code": probe.returncode, "stderr": probe.stderr.strip()},
              "formal_pdfa_validation": "not performed; veraPDF unavailable"}
    (output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--typst", type=Path, default=HERE.parent / "bin" / "typst")
    parser.add_argument("--output", type=Path, default=HERE / "output")
    parser.add_argument("--cache", type=Path, default=HERE / ".packages")
    args = parser.parse_args()
    run(args.typst.resolve(), args.output.resolve(), args.cache.resolve())
