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


from importers.pdf_importer import _resolve_validation_status


def test_status_unbalanced_ha_precedenza_su_review_required():
    assert _resolve_validation_status(warning_free=False, forecastable=False) == "unbalanced"


def test_status_unbalanced_anche_se_forecastable_fosse_vero():
    # Difensivo: un bilancio per cui e' stato mostrato un avviso di sbilancio
    # non e' mai "verified", anche se sarebbe altrimenti forecastable.
    assert _resolve_validation_status(warning_free=False, forecastable=True) == "unbalanced"


def test_status_verified_solo_se_nessun_avviso_ed_e_forecastable():
    assert _resolve_validation_status(warning_free=True, forecastable=True) == "verified"


def test_status_review_required_se_nessun_avviso_ma_non_forecastable():
    assert _resolve_validation_status(warning_free=True, forecastable=False) == "review_required"


def test_status_unbalanced_coincide_sempre_con_avviso_mostrato_allutente():
    """Invariante del fix: lo stato e' "unbalanced" se e solo se all'utente e'
    stato mostrato un avviso "BILANCIO SBILANCIATO" (``unbalanced_reason`` non
    None). Stato e avviso sono derivati dalla STESSA condizione, quindi non
    possono mai disaccordare — a differenza della vecchia implementazione, che
    derivava lo stato dalla tolleranza rigorosa di ``arithmetic_balanced``
    (0,01 €) mentre l'avviso veniva prodotto dai gate con tolleranze piu'
    larghe (``validate_balance``, ``check_quadratura(tol=2)``), lasciando uno
    sbilancio nella fascia (0,01 €; 2,00 €] senza alcun avviso a spiegare lo
    stato "unbalanced"."""
    for unbalanced_reason in (None, "BILANCIO SBILANCIATO: scarto 1,82"):
        for forecastable in (True, False):
            status = _resolve_validation_status(
                unbalanced_reason is None, forecastable
            )
            assert (status == "unbalanced") == (unbalanced_reason is not None)


from importers.pdf_importer import _should_import_prior


def test_prior_che_quadra_si_importa_sempre():
    assert _should_import_prior(True, False, has_existing=False) is True
    assert _should_import_prior(True, False, has_existing=True) is True


def test_prior_sbilanciato_si_importa_se_non_ce_n_e_gia_uno():
    # Meglio uno storico sbilanciato da correggere che nessuno storico:
    # senza anno di raffronto il wizard infrannuale non parte affatto.
    assert _should_import_prior(False, False, has_existing=False) is True


def test_prior_sbilanciato_non_sovrascrive_un_record_esistente():
    assert _should_import_prior(False, False, has_existing=True) is False


def test_prior_vuoto_non_si_importa_mai():
    assert _should_import_prior(False, True, has_existing=False) is False
    assert _should_import_prior(False, True, has_existing=True) is False
