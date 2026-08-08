"""Il marker di conferma delle Rettifiche vive nel rettifiche_log senza consumare il cap."""
import backend.app.main  # noqa: F401  — inserisce la project root in sys.path

from backend.app.api.v1.financial_years import (
    RETTIFICHE_LOG_MAX,
    _countable_log_entries,
)
from backend.app.schemas.adjustments import RettificaEntry


def _rettifica(idx: int) -> RettificaEntry:
    return RettificaEntry(
        id=f"r{idx}",
        edited_field="sp09_disponibilita_liquide",
        edited_label="Disponibilità liquide",
        edit_delta=100.0,
        counterpart_field="sp16g_altri_debiti_breve",
        counterpart_label="Altri debiti",
        counterpart_delta=100.0,
        created_at="2026-08-08T10:00:00",
    )


def _confirm() -> RettificaEntry:
    return RettificaEntry(
        id="confirm-2025",
        entry_type="confirm",
        edited_field="",
        edited_label="Rettifiche confermate",
        edit_delta=0.0,
        counterpart_field="",
        counterpart_label="",
        counterpart_delta=0.0,
        created_at="2026-08-08T10:05:00",
    )


def test_entry_type_defaults_to_none():
    """Le voci esistenti non hanno entry_type: il campo è additivo e opzionale."""
    assert _rettifica(1).entry_type is None


def test_confirm_marker_round_trips():
    """Il marker sopravvive a model_dump/validate: è così che viene persistito."""
    dumped = _confirm().model_dump()
    assert dumped["entry_type"] == "confirm"
    assert RettificaEntry(**dumped).entry_type == "confirm"


def test_confirm_does_not_consume_the_cap():
    """Con 20 rettifiche + 1 conferma il log resta accettabile."""
    log = [_rettifica(i) for i in range(RETTIFICHE_LOG_MAX)] + [_confirm()]
    assert _countable_log_entries(log) == RETTIFICHE_LOG_MAX


def test_real_entries_are_counted():
    log = [_rettifica(i) for i in range(RETTIFICHE_LOG_MAX + 1)]
    assert _countable_log_entries(log) == RETTIFICHE_LOG_MAX + 1
