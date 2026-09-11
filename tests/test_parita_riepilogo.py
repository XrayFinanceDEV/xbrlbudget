"""Il riepilogo del banco di parita' raggruppa e filtra le divergenze (lotto 3A, Task 1)."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "parita_riepilogo.py"

DIVERGENZE = [
    {"scenario": "base__finanziamento", "anno": 2028, "campo": "balance_sheet.sp17a_debiti_banche_lungo",
     "valore_a": "0,00", "valore_b": "10,00"},
    {"scenario": "banca__finanziamento", "anno": 2028, "campo": "balance_sheet.sp17a_debiti_banche_lungo",
     "valore_a": "1,00", "valore_b": "2,00"},
    {"scenario": "base__crescita", "anno": 2027, "campo": "income_statement.ce15_oneri_finanziari",
     "valore_a": "1,00", "valore_b": "2,00"},
]


def _json(tmp_path):
    percorso = tmp_path / "parita.json"
    percorso.write_text(json.dumps({"divergenze": DIVERGENZE, "controllo_negativo": True}), encoding="utf-8")
    return str(percorso)


def _esegui(*argomenti):
    return subprocess.run([sys.executable, str(SCRIPT), *argomenti], capture_output=True, text=True)


def test_senza_attese_raggruppa_ed_esce_zero(tmp_path):
    esito = _esegui(_json(tmp_path))
    assert esito.returncode == 0, esito.stderr
    assert "    2  finanziamento" in esito.stdout
    assert "totale divergenze: 3" in esito.stdout


def test_una_divergenza_fuori_dalle_attese_esce_uno_e_la_nomina(tmp_path):
    esito = _esegui(_json(tmp_path), "--attese", "*__finanziamento|balance_sheet.sp17a_*")
    assert esito.returncode == 1, esito.stdout
    assert "fuori dalle attese: 1" in esito.stdout
    assert "[base__crescita · 2027] income_statement.ce15_oneri_finanziari" in esito.stdout


def test_tutte_nelle_attese_esce_zero(tmp_path):
    esito = _esegui(_json(tmp_path), "--attese", "*__finanziamento|balance_sheet.*", "*|income_statement.ce15_*")
    assert esito.returncode == 0, esito.stdout
    assert "fuori dalle attese: 0" in esito.stdout
