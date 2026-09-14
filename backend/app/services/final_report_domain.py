"""M1-05A — read-model domain rules for the final report: chain, rettifiche, chiusura.

Three pure(ish) transformations over data the persistence milestones already own:

* **catena** — resolve the practice's source scenario from the persisted link, or
  from a deterministic and *conservative* legacy fallback.  The fallback never
  writes: an inferred link is declared through a diagnostic, and an ambiguous
  one is refused rather than guessed (spec §4).
* **rettifiche** — the ``confirm`` marker is process bookkeeping, not an economic
  correction: it is filtered out of the entries and the net effect while the
  confirmation state itself is preserved (spec §6.2).
* **chiusura** — observed progressivo, comparable, automatic projection, explicit
  override and the value actually used stay five distinct fields (spec §6.3).

No forecasting or analysis formula is reproduced here; amounts are ``Decimal``
and the contract types come from ``app.schemas.final_report`` unchanged.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
import os
from typing import Any, Iterable, Mapping, Optional

_backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from sqlalchemy.orm import Session

from app.schemas.final_report import (
    AdjustmentEntry,
    Adjustments,
    ClosingValue,
    Diagnostic,
    ExtraAccountingAlerts as FinalReportExtraAccountingAlerts,
    InfrannualClosing,
)
from app.services.extra_accounting_alerts_service import normalize_extra_accounting_alerts
from database.models import BudgetScenario, FinancialYear


# ``entry_type == "confirm"`` is the only marker the Rettifiche gate persists to
# attest «Conferma e prosegui». It carries no economic movement by design.
CONFIRM_ENTRY_TYPE = "confirm"

# Counterpart pseudo-field used by the single-entry "Correggi Import" mode: it is
# a label, not a statement column, so it contributes no signed delta.
NON_POSTING_COUNTERPART = "_correzione_import"

ZERO = Decimal("0")


# ---------------------------------------------------------------------------
# 1. Catena della pratica
# ---------------------------------------------------------------------------
class ChainMatch(str, Enum):
    """How the source scenario of a practice was established."""

    EXPLICIT = "explicit"                # persisted link, usable as it stands
    UNIQUE_INFERRED = "unique_inferred"  # legacy fallback, exactly one origin
    NONE = "none"                        # head of its own practice (bilancio/startup)
    AMBIGUOUS = "ambiguous"              # several compatible origins -> not finalizable
    BROKEN = "broken"                    # persisted link points at nothing usable


@dataclass(frozen=True)
class ChainResolution:
    """Outcome of the lineage resolution, ready to be read by the assembler."""

    match: ChainMatch
    source_scenario: Optional[BudgetScenario] = None
    candidate_ids: tuple[int, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def source_scenario_id(self) -> Optional[int]:
        return self.source_scenario.id if self.source_scenario is not None else None

    @property
    def legacy_inferred(self) -> bool:
        return self.match is ChainMatch.UNIQUE_INFERRED

    @property
    def finalizable(self) -> bool:
        """An ambiguous or dangling lineage leaves the report consultable only."""
        return self.match not in (ChainMatch.AMBIGUOUS, ChainMatch.BROKEN)


def _diagnostic(code: str, severity: str, section: str, message: str) -> Diagnostic:
    return Diagnostic(code=code, severity=severity, section=section, message=message)


def _field(entry: Any, name: str, default: Any = None) -> Any:
    """Read a journal field from a dict or from an ORM/Pydantic object.

    The log reaches this module both ways: ``json.loads(fy.rettifiche_log)`` on
    the read path, ``RettificaEntry`` on a request body.
    """
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _decimal(value: Any) -> Decimal:
    """One boundary conversion to ``Decimal``; ``None`` is zero, as everywhere."""
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _is_infrannuale_origin(scenario: Optional[BudgetScenario]) -> bool:
    return bool(
        scenario is not None
        and scenario.scenario_type == "infrannuale"
        and scenario.period_months is not None
        and 1 <= scenario.period_months <= 11
    )


def _full_year(db: Session, company_id: int, year: int) -> Optional[FinancialYear]:
    """Annual exercise of ``year``, accepting both ``NULL`` and ``12`` spellings."""
    return db.query(FinancialYear).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == year,
        (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),  # noqa: E711
    ).first()


def _legacy_candidates(db: Session, scenario: BudgetScenario) -> tuple[BudgetScenario, ...]:
    """Deterministic origins for a scenario that never stored its link.

    Two signals are trusted, in this order:

    1. the annual exercise of ``scenario.base_year`` records
       ``promoted_from_scenario_id`` — promotion wrote that marker even when the
       budget row predates ``source_scenario_id``;
    2. otherwise, only a legacy row whose workflow is undeclared or explicitly
       ``infrannuale`` may search for an infrannuale scenario that closes into
       this base year.  A declared ``bilancio`` or ``startup`` is the head of its
       own practice and must never acquire a phantom parent.
    """
    promoted = _full_year(db, scenario.company_id, scenario.base_year)
    promoted_source_id = getattr(promoted, "promoted_from_scenario_id", None)
    if promoted_source_id is not None:
        origin = db.get(BudgetScenario, promoted_source_id)
        if origin is None or origin.company_id != scenario.company_id:
            return ()
        return (origin,)

    if scenario.workflow_type in ("bilancio", "startup"):
        return ()

    candidates = (
        db.query(BudgetScenario)
        .filter(
            BudgetScenario.company_id == scenario.company_id,
            BudgetScenario.scenario_type == "infrannuale",
            BudgetScenario.base_year == scenario.base_year - 1,
            BudgetScenario.period_months >= 1,
            BudgetScenario.period_months <= 11,
            BudgetScenario.is_active == 1,
        )
        .order_by(BudgetScenario.id)
        .all()
    )
    return tuple(candidates)


def resolve_source_scenario(db: Session, scenario: BudgetScenario) -> ChainResolution:
    """Resolve the practice's source scenario without touching the database.

    Reads run under ``no_autoflush``: resolving a lineage is never a reason to
    push someone else's pending unit of work to SQLite, and an inferred link is
    declared in ``diagnostics``, never written back.
    """
    with db.no_autoflush:
        return _resolve_source_scenario(db, scenario)


def _resolve_source_scenario(db: Session, scenario: BudgetScenario) -> ChainResolution:
    explicit_id = getattr(scenario, "source_scenario_id", None)
    if explicit_id is not None:
        origin = db.get(BudgetScenario, explicit_id)
        if origin is None or origin.company_id != scenario.company_id:
            return ChainResolution(
                ChainMatch.BROKEN,
                candidate_ids=(explicit_id,),
                diagnostics=(
                    _diagnostic(
                        "chain_source_missing",
                        "error",
                        "chain",
                        "Lo scenario di origine indicato non è disponibile per questa azienda: "
                        "il report resta consultabile ma non è finalizzabile.",
                    ),
                ),
            )
        return ChainResolution(ChainMatch.EXPLICIT, source_scenario=origin)

    if scenario.scenario_type == "infrannuale":
        # This scenario IS the intra-year source: a practice head has no parent,
        # and searching for one would invent a chain that never existed.
        return ChainResolution(ChainMatch.NONE)

    candidates = _legacy_candidates(db, scenario)
    if not candidates:
        if scenario.workflow_type == "infrannuale":
            return ChainResolution(
                ChainMatch.NONE,
                diagnostics=(
                    _diagnostic(
                        "chain_source_missing",
                        "warning",
                        "chain",
                        "Nessuna origine infrannuale riconoscibile per questa pratica: "
                        "la catena è ricostruibile solo dall'esercizio promosso.",
                    ),
                ),
            )
        return ChainResolution(ChainMatch.NONE)

    if len(candidates) == 1:
        only = candidates[0]
        if not _is_infrannuale_origin(only):
            # The marker names a scenario that is not an intra-year one: nothing
            # can be claimed about the lineage, and nothing is invented.
            return ChainResolution(ChainMatch.NONE)
        return ChainResolution(
            ChainMatch.UNIQUE_INFERRED,
            source_scenario=only,
            candidate_ids=tuple(item.id for item in candidates),
            diagnostics=(
                _diagnostic(
                    "legacy_chain_inferred",
                    "warning",
                    "chain",
                    "Collegamento di catena dedotto dal percorso legacy: non è stato "
                    "scritto alcun collegamento nello database.",
                ),
            ),
        )

    return ChainResolution(
        ChainMatch.AMBIGUOUS,
        candidate_ids=tuple(item.id for item in candidates),
        diagnostics=(
            _diagnostic(
                "legacy_chain_ambiguous",
                "error",
                "chain",
                "Più origini infrannuali sono compatibili con questa pratica "
                f"({', '.join(str(item.id) for item in candidates)}): il report non è "
                "finalizzabile finché il collegamento non viene risolto.",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# 2. Rettifiche: conferme fuori dai movimenti economici
# ---------------------------------------------------------------------------
def is_confirm_entry(entry: Any) -> bool:
    return _field(entry, "entry_type") == CONFIRM_ENTRY_TYPE


def economic_entries(entries: Iterable[Any]) -> list[Any]:
    """Only the entries that move money; ``confirm`` markers attest the process."""
    return [entry for entry in entries if not is_confirm_entry(entry)]


def is_confirmed(entries: Iterable[Any]) -> bool:
    """Confirmation state survives the filter: that is what the gate reads."""
    return any(is_confirm_entry(entry) for entry in entries)


#: Field names that are labels, not statement columns. ``_correzione_import`` is
#: the counterpart the single-entry "Correggi Import" mode writes; a delta parked
#: on it is mass that is not posted anywhere, so it is declared, never absorbed.
NON_POSTING_FIELDS = frozenset({NON_POSTING_COUNTERPART})


def _legs(entry: Any) -> Iterable[tuple[str, str]]:
    return (("edited_field", "edit_delta"), ("counterpart_field", "counterpart_delta"))


def signed_deltas(entries: Iterable[Any]) -> dict[str, Decimal]:
    """Per-field signed movement, in the statement's own sign convention.

    ``edit_delta`` is applied to ``edited_field`` and ``counterpart_delta`` to
    ``counterpart_field``: both are increments of the stored value, exactly as
    the Rettifiche journal writes them (a cost line grows positive, so does a
    liability), and a split row carries its counterpart only.
    """
    deltas: dict[str, Decimal] = {}
    for entry in economic_entries(entries):
        for name, delta_name in _legs(entry):
            code = _field(entry, name)
            if not code or code in NON_POSTING_FIELDS:
                continue
            deltas[code] = deltas.get(code, ZERO) + _decimal(_field(entry, delta_name))
    return deltas


def unposted_mass(entries: Iterable[Any]) -> Decimal:
    """What an economic entry moved onto a label instead of a statement field."""
    total = ZERO
    for entry in economic_entries(entries):
        for name, delta_name in _legs(entry):
            code = _field(entry, name)
            if code in NON_POSTING_FIELDS:
                total += _decimal(_field(entry, delta_name))
    return total


def net_effect(entries: Iterable[Any]) -> Decimal:
    """The algebraic sum of every delta the journal recorded, both legs included.

    This is the contract's ``adjustments.net_effect``: a *sum of recorded
    movements*, factual rather than an assertion of quadratura — an entry that
    moved equal and opposite amounts nets to ``0.00``, and the accounting truth
    of a row lives in :func:`signed_deltas` / :func:`reconcile_adjustments`,
    which the assembler reads alongside it.  ``confirm`` markers are absent by
    construction, whatever delta a stray one might carry.
    """
    entries = list(entries)
    return sum(
        (
            _decimal(_field(entry, "edit_delta")) + _decimal(_field(entry, "counterpart_delta"))
            for entry in economic_entries(entries)
        ),
        ZERO,
    )


def _as_contract_entry(entry: Any) -> AdjustmentEntry:
    return AdjustmentEntry(
        id=str(_field(entry, "id", "")),
        edited_field=str(_field(entry, "edited_field", "") or ""),
        edited_label=str(_field(entry, "edited_label", "") or ""),
        edit_delta=_decimal(_field(entry, "edit_delta")),
        counterpart_field=str(_field(entry, "counterpart_field", "") or ""),
        counterpart_label=str(_field(entry, "counterpart_label", "") or ""),
        counterpart_delta=_decimal(_field(entry, "counterpart_delta")),
        explanation=_field(entry, "explanation"),
        created_at=str(_field(entry, "created_at", "") or ""),
    )


def build_adjustments(entries: Iterable[Any]) -> Adjustments:
    """The ``Adjustments`` contract block: economic rows only, confirmation kept."""
    entries = list(entries)
    return Adjustments(
        confirmed=is_confirmed(entries),
        entries=[_as_contract_entry(entry) for entry in economic_entries(entries)],
        net_effect=net_effect(entries),
    )


@dataclass(frozen=True)
class AdjustmentReconciliation:
    """``before + signed adjustments = after``, verified field by field."""

    adjustments: Mapping[str, Decimal]
    differences: Mapping[str, Decimal]
    unposted: Decimal = ZERO
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def balanced(self) -> bool:
        return not self.differences


def reconcile_adjustments(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    entries: Iterable[Any],
    *,
    tolerance: Decimal = Decimal("0.01"),
) -> AdjustmentReconciliation:
    """Reconcile the journal against two snapshots of the statement.

    ``before``/``after`` are the two snapshots of one exercise with the balance
    sheet and the income statement merged (the shape
    ``GET .../adjustable`` already returns).  Only the fields the journal moved
    are checked: the aggregate of a moved detail is recomputed by the Rettifiche
    layer itself (``recalcAggregates``), and restating that rule here would be a
    second copy of it — the very drift this milestone exists to avoid.
    """
    adjustments = signed_deltas(entries)
    differences: dict[str, Decimal] = {}
    unposted = unposted_mass(entries)
    for code, delta in adjustments.items():
        actual = _decimal(after.get(code)) - _decimal(before.get(code))
        if abs(actual - delta) > tolerance:
            differences[code] = actual - delta
    diagnostics: tuple[Diagnostic, ...] = ()
    if differences:
        details = ", ".join(f"{code} {value}" for code, value in sorted(differences.items()))
        diagnostics = (
            _diagnostic(
                "adjustments_unreconciled",
                "error",
                "adjustments",
                f"La riconciliazione rettifiche non quadra: {details}",
            ),
        )
    if unposted:
        diagnostics = diagnostics + (
            _diagnostic(
                "adjustments_unposted_mass",
                "warning",
                "adjustments",
                f"{unposted} movimentati su un'intestazione non di bilancio: "
                "la rettifica non è stata registrata in partita doppia.",
            ),
        )
    return AdjustmentReconciliation(
        adjustments=adjustments,
        differences=differences,
        unposted=unposted,
        diagnostics=diagnostics,
    )


# ---------------------------------------------------------------------------
# 3. Chiusura infrannuale
# ---------------------------------------------------------------------------
def closing_value(
    code: str,
    label: str,
    *,
    observed: Any = None,
    comparable: Any = None,
    automatic: Any = None,
    override: Any = None,
) -> ClosingValue:
    """One closing row, with the five notions kept apart.

    ``closing_used`` is the only derived number, and only by precedence: an
    explicit override wins over the engine's automatic projection, which wins
    over the observed progressivo.  An override of ``0.00`` is a decision, so it
    beats an automatic value; an *absent* override (``None``) is not.

    With no measure at all nothing is invented: the row is refused, because a
    fabricated zero would be indistinguishable from a closing of zero.
    """
    values = {"observed": observed, "comparable": comparable, "automatic": automatic, "override": override}
    converted = {name: (None if value is None else _decimal(value)) for name, value in values.items()}
    known = [name for name in ("override", "automatic", "observed") if converted[name] is not None]
    if not known:
        raise ValueError(f"La voce di chiusura {code or '(senza codice)'} non ha nessun valore conosciuto")
    return ClosingValue(code=code, label=label, closing_used=converted[known[0]], **converted)


def build_closing_values(rows: Iterable[Mapping[str, Any]]) -> list[ClosingValue]:
    """Build closing rows from per-line measure mappings."""
    return [
        closing_value(
            str(row.get("code", "")),
            str(row.get("label", "")),
            observed=row.get("observed"),
            comparable=row.get("comparable"),
            automatic=row.get("automatic"),
            override=row.get("override"),
        )
        for row in rows
    ]


def final_report_alerts(raw: Any) -> FinalReportExtraAccountingAlerts:
    """Persisted alert JSON → the contract block, exactly seven booleans.

    ``normalize_extra_accounting_alerts`` owns the sparse/legacy/foreign-key
    normalisation; this only re-expresses its result in the report contract, so
    a ``None`` map, an empty one and seven explicit ``false`` all render the
    same seven keys and nothing else.
    """
    return FinalReportExtraAccountingAlerts(**normalize_extra_accounting_alerts(raw).model_dump())


def build_infrannual_closing(
    *,
    period_end: date | str,
    rows: Iterable[Mapping[str, Any]],
    alerts: Any = None,
) -> InfrannualClosing:
    """The whole ``infrannual_closing`` block of the contract."""
    values = build_closing_values(rows)
    if not values:
        raise ValueError("La chiusura infrannuale richiede almeno una voce")
    return InfrannualClosing(
        period_end=period_end if isinstance(period_end, date) else str(period_end),
        values=values,
        extra_accounting_alerts=final_report_alerts(alerts),
    )
