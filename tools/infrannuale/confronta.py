"""PNG affiancati riferimento | report infrannuale di AMBIENTA dal DB locale, per la verifica con la vision.

Uso: python tools/infrannuale/confronta.py [--db PATH] [--scenario 17]
Scrive in tests/.banco-infrannuale/confronto/ (gitignored). Legge una COPIA del DB.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

import fitz  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def _png(page, dpi=90) -> Image.Image:
    px = page.get_pixmap(dpi=dpi)
    return Image.frombytes("RGB", (px.width, px.height), px.samples)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "financial_analysis.db"))
    ap.add_argument("--scenario", type=int, default=17)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp()) / "db.sqlite"
    shutil.copyfile(args.db, tmp)
    db = sessionmaker(bind=create_engine(f"sqlite:///{tmp}"))()
    from database.models import BudgetScenario
    from app.renderers.infrannuale.data import from_intermedio
    from app.renderers.infrannuale.document import render_infrannuale
    from app.services.intermedio_report_service import assemble_intermedio
    pdf_bytes = render_infrannuale(from_intermedio(assemble_intermedio(db, db.get(BudgetScenario, args.scenario))))
    out = ROOT / "tests/.banco-infrannuale/confronto"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report-infrannuale.pdf").write_bytes(pdf_bytes)
    new = fitz.open(stream=pdf_bytes, filetype="pdf")
    ref_path = ROOT / "tests/.banco-infrannuale/riferimento.pdf"
    ref = fitz.open(ref_path) if ref_path.is_file() else None
    for i in range(new.page_count):
        b = _png(new[i])
        if ref is not None and i < ref.page_count:
            a = _png(ref[i])
            m = Image.new("RGB", (a.width + b.width + 16, max(a.height, b.height)), "#888")
            m.paste(a, (0, 0))
            m.paste(b, (a.width + 16, 0))
        else:
            m = b
        m.save(out / f"p{i + 1:02d}.png")
    print(f"{new.page_count} pagine in {out}")


if __name__ == "__main__":
    main()
