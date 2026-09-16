"""Build the self-contained HTML preview and embed actual native PDF samples."""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from tools.typst.spike.fixtures import build_all_spike_fixtures
from tools.typst.spike.packages import HERE


def build_preview(output: Path) -> Path:
    payload = {"models": {n: m.model_dump(mode="json") for n, m in build_all_spike_fixtures().items()}, "pdfs": {}}
    for name in payload["models"]:
        for state in ("draft", "final"):
            for mode in ("color", "gray"):
                key = f"native-{name}-{state}-{mode}"
                path = output / f"{key}.pdf"
                if not path.read_bytes().startswith(b"%PDF-"):
                    raise ValueError(f"invalid preview PDF: {path}")
                payload["pdfs"][key] = base64.b64encode(path.read_bytes()).decode("ascii")
    # HTML script data cannot terminate the surrounding script element.
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    html = (HERE / "preview.html").read_text().replace("__PAYLOAD__", encoded)
    path = output / "report-finale-anteprima.html"
    path.write_text(html, encoding="utf-8")
    print(path, path.stat().st_size, "bytes")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "output")
    build_preview(parser.parse_args().output.resolve())
