"""PNG affiancati riferimento | Business plan di AMBIENTA dal DB locale, per la verifica con la vision.

Uso: python tools/business_plan/confronta.py [--db PATH] [--company 575 --scenario 18]
Scrive in tests/.banco-business-plan/confronto/ (gitignored). Legge una COPIA del DB.
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
    ap.add_argument("--db", default="/home/peter/DEV/budget/financial_analysis.db")
    ap.add_argument("--company", type=int, default=575)
    ap.add_argument("--scenario", type=int, default=18)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp()) / "db.sqlite"
    shutil.copyfile(args.db, tmp)
    db = sessionmaker(bind=create_engine(f"sqlite:///{tmp}"))()
    from app.renderers.business_plan import from_report, render_business_plan
    from app.services.final_report_service import assemble_final_report
    data = from_report(assemble_final_report(db, args.company, args.scenario, schema_version=2), draft=False)
    pdf_bytes = render_business_plan(data)
    out = ROOT / "tests/.banco-business-plan/confronto"
    out.mkdir(parents=True, exist_ok=True)
    (out / "business-plan.pdf").write_bytes(pdf_bytes)
    new = fitz.open(stream=pdf_bytes, filetype="pdf")
    ref_path = ROOT / "tests/.banco-business-plan/riferimento.pdf"
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
