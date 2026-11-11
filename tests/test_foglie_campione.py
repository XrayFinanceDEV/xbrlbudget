"""Lo strumento offline delle foglie del lettore (Fase 5, Task 1): PDF sintetici, nessun modello."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "corpus"))

import foglie_campione as fc  # noqa: E402
from tests.lettore.pdf_sintetico import scrivi_pdf  # noqa: E402
from tests.lettore.test_foglie import _contrapposte_sp  # noqa: E402


def _pdf(tmp_path, voci, nome="doc.pdf"):
    p = tmp_path / nome
    scrivi_pdf(p, [voci])
    return p


def test_contrapposte_in_pari(tmp_path):
    m = fc.misura(_pdf(tmp_path, _contrapposte_sp()))
    assert m["stato"] == "in_pari"
    assert m["senza_sezione"] == 0 and m["senza_lato"] == 0
    assert m["attivo"] == "2100.00" and m["differenza"] == "100.00"   # l'utile sta fra le righe del risultato
    assert m["firma"] and m["impronte"]


def test_una_riga_in_piu_non_in_pari(tmp_path):
    voci = [(x, y, "9.999,00" if t == "500,00" and x == 280 and y == 140 + 14 * 4 else t)
            for x, y, t in _contrapposte_sp()]
    m = fc.misura(_pdf(tmp_path, voci))
    assert m["stato"] in fc.STATI_RINUNCIA


def test_pdf_senza_testo_e_vuoto(tmp_path):
    assert fc.misura(_pdf(tmp_path, []))["stato"] == "vuoto"


def test_confronta_segnala_solo_i_cambiati():
    a = {"1": {"stato": "in_pari", "firma": "x", "impronte": [["r1", "Banca", "1", "SP", "A", None, None]]},
         "2": {"stato": "foglie_non_in_pari", "firma": "y", "impronte": []}}
    b = {"1": {"stato": "in_pari", "firma": "x", "impronte": [["r1", "Banca", "1", "SP", "A", None, None]]},
         "2": {"stato": "in_pari", "firma": "z", "impronte": [["r9", "Cassa", "5", "SP", "A", None, None]]},
         "3": {"stato": "vuoto"}}
    diff = fc.confronta(a, b)
    assert [d["id"] for d in diff] == ["2"]
    assert diff[0]["prima"] == "foglie_non_in_pari" and diff[0]["dopo"] == "in_pari" and diff[0]["foglie_nuove"] == 1
