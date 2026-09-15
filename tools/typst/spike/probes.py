"""Focused probes isolate null, all-null and negative-bar behavior for fairness."""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import fitz

from tools.typst.spike.fixtures import build_spike_fixture
from tools.typst.spike.packages import HERE, prepare_packages


def run_probes(output: Path, cache: Path, typst: Path) -> list[dict]:
    packages = prepare_packages(cache)
    complete = build_spike_fixture("startup").model_dump(mode="json")["chart_series"]
    negative = build_spike_fixture("bilancio").model_dump(mode="json")["chart_series"][0]
    allnull = copy.deepcopy(complete[1])
    allnull["id"] = "all_null"
    allnull["title"] = "Serie interamente non disponibili"
    for s in allnull["series"]:
        s["values"] = [None] * len(allnull["categories"])
    charts = complete + [dict(negative, id="negative_bars"), allnull]
    rows = []
    for candidate in ("native", "cetz", "primaviz"):
        for chart in charts:
            directory = output / "probes" / f"{candidate}-{chart['id']}"
            directory.mkdir(parents=True, exist_ok=True)
            for file in HERE.glob("*.typ"):
                shutil.copyfile(file, directory / file.name)
            # negative_bars is a probe identity; preserve the required bar rendering.
            payload = dict(chart, id="income_results") if chart["id"] == "negative_bars" else chart
            (directory / "chart.json").write_text(json.dumps(payload))
            pdf = directory / "chart.pdf"
            metrics = directory / "peak-rss.txt"
            command = ["unshare", "--user", "--map-root-user", "--net", "/usr/bin/time", "-f", "%M", "-o", str(metrics),
                       str(typst), "compile", "--root", str(directory), "--ignore-system-fonts", "--jobs", "1",
                       "--package-path", str(packages), "--package-cache-path", str(directory / "empty"),
                       "--input", f"candidate={candidate}", str(directory / "chart.typ"), str(pdf)]
            env = {k: v for k, v in os.environ.items() if not k.startswith("TYPST_")}
            start = time.perf_counter()
            proc = subprocess.run(command, env=env, capture_output=True, text=True, timeout=30)
            row = {"candidate": candidate, "chart": chart["id"], "exit_code": proc.returncode,
                   "seconds": round(time.perf_counter() - start, 4),
                   "peak_rss_kib": int(metrics.read_text().splitlines()[-1]), "stderr": proc.stderr.strip()}
            if not proc.returncode:
                doc = fitz.open(pdf)
                row.update(bytes=pdf.stat().st_size, raster_images=sum(len(p.get_images()) for p in doc),
                           vector_paths=sum(len(p.get_drawings()) for p in doc))
                if row["raster_images"] or not row["vector_paths"]:
                    raise ValueError("probe lost vector graphics")
                # Embedded SVG is generated directly by the actual PDF renderer.
                (directory / "chart.svg").write_text(doc[0].get_svg_image())
            rows.append(row)
            print(candidate, chart["id"], row["exit_code"], flush=True)
    (output / "probes.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    return rows


if __name__ == "__main__":
    run_probes(HERE / "output", HERE / ".packages", HERE.parent / "bin" / "typst")
