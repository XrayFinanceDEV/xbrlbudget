"""I campi booleani e testuali del contratto del report: una sola verità, in due lingue.

Il backend (`backend/app/schemas/final_report.py`) e il validatore del frontend
(`frontend/types/final-report.ts`) tengono ciascuno il proprio elenco. Erano divergiti: il backend
aveva aggiunto i due «segue l'inflazione» e la regola dei fidi, il frontend no, e il Report di
AMBIENTA si fermava su «Unsupported or invalid FinalReportModel v2 payload» (2026-09-17). Nessun
test se n'era accorto, perché le fixture condivise del report non contengono alcuna ipotesi.
"""
import re
from pathlib import Path

from backend.app.schemas.final_report import _BOOLEAN_ASSUMPTION_FIELDS, _STRING_ASSUMPTION_FIELDS

ROOT = Path(__file__).resolve().parents[1]
TS = (ROOT / "frontend" / "types" / "final-report.ts").read_text(encoding="utf-8")


def _insieme_ts(nome: str) -> set[str]:
    corpo = re.search(rf"export const {nome}: ReadonlySet<string> = new Set\(\[(.*?)\]\)", TS)
    assert corpo, f"{nome} non trovato in final-report.ts: il test non deve passare per un parse a vuoto"
    valori = set(re.findall(r'"([a-z0-9_]+)"', corpo.group(1)))
    assert valori
    return valori


def test_i_campi_booleani_sono_gli_stessi_nei_due_contratti():
    assert _insieme_ts("BOOLEAN_ASSUMPTION_FIELDS") == set(_BOOLEAN_ASSUMPTION_FIELDS)


def test_i_campi_testuali_sono_gli_stessi_nei_due_contratti():
    assert _insieme_ts("STRING_ASSUMPTION_FIELDS") == set(_STRING_ASSUMPTION_FIELDS)
