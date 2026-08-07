"""Il gate di import distingue cio' che si puo' rettificare da cio' che non si puo'.

Uno sbilancio e' correggibile in Rettifiche, quindi si importa con un avviso.
Un'estrazione vuota o un documento che non e' uno schema IV-CEE non lo sono,
quindi restano errori duri: non c'e' nulla su cui l'utente possa intervenire.
"""
import os
import sys
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

from importers.pdf_importer import (
    _UNBALANCED_WARNING_PREFIX,
    _classify_balance_failure,
)


def _sheet(**overrides):
    """Uno stato patrimoniale minimo che quadra, salvo gli override."""
    data = {
        "totale_attivo": Decimal("1000"),
        "totale_passivo": Decimal("1000"),
        "sp09_disponibilita_liquide": Decimal("1000"),
        "sp16_debiti_breve": Decimal("1000"),
    }
    data.update(overrides)
    return data


def test_estrazione_vuota_resta_errore_duro():
    verdict = _classify_balance_failure(
        _sheet(totale_attivo=Decimal("0"), totale_passivo=Decimal("0"),
               sp09_disponibilita_liquide=Decimal("0"),
               sp16_debiti_breve=Decimal("0")),
        is_scanned=False, ocr_source=False,
        is_trial_balance=False, sample_text="B) II 1) Terreni 100",
        file_path="x.pdf", ocr_text=None,
    )
    assert verdict.hard_error is not None
    assert "nessun dato" in verdict.hard_error.lower()


def test_ocr_resta_errore_duro():
    verdict = _classify_balance_failure(
        _sheet(totale_passivo=Decimal("960")),
        is_scanned=True, ocr_source=False,
        is_trial_balance=False, sample_text="B) II 1) Terreni 100",
        file_path="x.pdf", ocr_text=None,
    )
    assert verdict.hard_error is not None
    assert "OCR" in verdict.hard_error


def test_sbilancio_e_importabile_con_avviso():
    # _is_aggregated_summary richiede >= 3 righe con numero romano di voce legale
    # (una sola riga, come nei due test precedenti, e' sempre < 3 e farebbe
    # cadere il verdetto nel ramo "riepilogo aggregato" invece che nello sbilancio).
    verdict = _classify_balance_failure(
        _sheet(totale_passivo=Decimal("960")),
        is_scanned=False, ocr_source=False,
        is_trial_balance=False,
        sample_text=(
            "B) II 1) Terreni 100\n"
            "B) III 2) Impianti 50\n"
            "C) II Crediti 20"
        ),
        file_path="x.pdf", ocr_text=None,
    )
    assert verdict.hard_error is None
    assert verdict.warning.startswith(_UNBALANCED_WARNING_PREFIX)
    assert "Rettifiche" in verdict.warning
