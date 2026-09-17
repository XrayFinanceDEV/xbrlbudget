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
from calculations.projection_common import eur_it
from database.models import BudgetScenario, FinancialYear


# ``entry_type == "confirm"`` is the only marker the Rettifiche gate persists to
# attest «Conferma e prosegui». It carries no economic movement by design.
CONFIRM_ENTRY_TYPE = "confirm"

# Pseudo-field used by the single-entry "Correggi Import" mode: it is a label,
# not a statement column, so it contributes no signed statement delta.
UNPOSTED_SENTINEL_FIELD = "_correzione_import"

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
        # ``NULL`` is the legacy spelling of the workflow inferred from the
        # scenario type.  A different, persisted workflow is never a source of
        # the infrannuale promotion chain.
        and scenario.workflow_type in (None, "infrannuale")
        and scenario.period_months is not None
        and 1 <= scenario.period_months <= 11
    )


def _is_annualized_origin_for(scenario: BudgetScenario, origin: Optional[BudgetScenario]) -> bool:
    """Whether ``origin`` could have produced ``scenario`` through promotion.

    This deliberately mirrors the facts persisted by ``promote_service`` and
    ``derive_scenario_provenance``: only a 1--11 month infrannuale becomes the
    following full-year exercise.  It does not infer extra requirements (for
    example that a legacy row must already have a workflow label).
    """
    return bool(
        scenario.scenario_type != "infrannuale"
        and _is_infrannuale_origin(origin)
        and origin.base_year + 1 == scenario.base_year
    )


def _explicit_origin_is_compatible(scenario: BudgetScenario, origin: Optional[BudgetScenario]) -> bool:
    """Explicit links are server-owned and must name the infrannuale chain."""
    return scenario.workflow_type == "infrannuale" and _is_annualized_origin_for(scenario, origin)


def _full_year(db: Session, company_id: int, year: int) -> Optional[FinancialYear]:
    """Annual exercise of ``year``, accepting both ``NULL`` and ``12`` spellings."""
    return db.query(FinancialYear).filter(
        FinancialYear.company_id == company_id,
        FinancialYear.year == year,
        (FinancialYear.period_months == None) | (FinancialYear.period_months == 12),  # noqa: E711
    ).first()


def _legacy_candidates(db: Session, scenario: BudgetScenario) -> tuple[BudgetScenario, ...]:
    """Deterministic origins for a scenario that never stored its link.

    Only a legacy row whose workflow is undeclared or explicitly
    ``infrannuale`` may search for an infrannuale scenario that closes into this
    base year.  A declared ``bilancio`` or ``startup`` is the head of its own
    practice and must never acquire a phantom parent.  The promotion marker is
    resolved separately: when it exists it is a persisted declaration, never a
    hint that may be replaced by this heuristic.
    """
    if scenario.workflow_type not in (None, "infrannuale"):
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
    return tuple(candidate for candidate in candidates if _is_annualized_origin_for(scenario, candidate))


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
    promoted = _full_year(db, scenario.company_id, scenario.base_year)
    marker_source_id = getattr(promoted, "promoted_from_scenario_id", None)
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
        if not _explicit_origin_is_compatible(scenario, origin) or (
            marker_source_id is not None and marker_source_id != origin.id
        ):
            return ChainResolution(
                ChainMatch.BROKEN,
                candidate_ids=(origin.id,),
                diagnostics=(
                    _diagnostic(
                        "chain_source_incompatible",
                        "error",
                        "chain",
                        "Lo scenario di origine indicato non è compatibile con la "
                        "catena infrannuale annualizzata o con il marcatore "
                        "dell'esercizio di base: il report resta consultabile ma non "
                        "è finalizzabile.",
                    ),
                ),
            )
        return ChainResolution(ChainMatch.EXPLICIT, source_scenario=origin)

    if scenario.scenario_type == "infrannuale":
        # This scenario IS the intra-year source: a practice head has no parent,
        # and searching for one would invent a chain that never existed.
        return ChainResolution(ChainMatch.NONE)

    # Promotion persists this marker even for annual scenarios predating
    # ``source_scenario_id``.  Therefore its mere presence is a declaration of
    # lineage: a missing, foreign or incompatible target is a broken chain, not
    # permission to find a more convenient legacy candidate.
    if marker_source_id is not None:
        origin = db.get(BudgetScenario, marker_source_id)
        if origin is None or origin.company_id != scenario.company_id:
            return ChainResolution(
                ChainMatch.BROKEN,
                candidate_ids=(marker_source_id,),
                diagnostics=(
                    _diagnostic(
                        "chain_source_missing",
                        "error",
                        "chain",
                        "Il marcatore di promozione indica uno scenario non disponibile "
                        "per questa azienda: il report resta consultabile ma non è "
                        "finalizzabile.",
                    ),
                ),
            )
        if not _is_annualized_origin_for(scenario, origin):
            return ChainResolution(
                ChainMatch.BROKEN,
                candidate_ids=(origin.id,),
                diagnostics=(
                    _diagnostic(
                        "chain_source_incompatible",
                        "error",
                        "chain",
                        "Il marcatore di promozione indica uno scenario non compatibile "
                        "con la catena infrannuale annualizzata: il report resta "
                        "consultabile ma non è finalizzabile.",
                    ),
                ),
            )
        return ChainResolution(
            ChainMatch.UNIQUE_INFERRED,
            source_scenario=origin,
            candidate_ids=(origin.id,),
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
#: the sentinel written by the single-entry "Correggi Import" mode; its economic
#: mass is deliberately declared rather than absorbed into statement deltas.
UNPOSTED_SENTINEL_FIELDS = frozenset({UNPOSTED_SENTINEL_FIELD})


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
            if not code or code in UNPOSTED_SENTINEL_FIELDS:
                continue
            deltas[code] = deltas.get(code, ZERO) + _decimal(_field(entry, delta_name))
    return deltas


def unposted_mass(entries: Iterable[Any]) -> Decimal:
    """Economic mass parked on an unposted sentinel instead of a statement field.

    The UI writer's actual ``Correggi Import`` shape is ``counterpart_delta=0``
    and carries the one-sided movement in ``edit_delta``.  Older rows can carry
    the mass on the sentinel counterpart itself, so retain that representation
    whenever it is non-zero.
    """
    total = ZERO
    for entry in economic_entries(entries):
        for name, delta_name in _legs(entry):
            code = _field(entry, name)
            if code in UNPOSTED_SENTINEL_FIELDS:
                delta = _decimal(_field(entry, delta_name))
                if name == "counterpart_field" and delta == ZERO:
                    delta = _decimal(_field(entry, "edit_delta"))
                total += delta
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


#: Fino a qui uno scarto fra giornale e bilancio è arrotondamento: si dichiara, non blocca. È la scala
#: che il proprietario ha scelto per la chiusura automatica delle Rettifiche (2026-09-16).
ROUNDING_DECLARED = Decimal("2.00")
_CENT = Decimal("0.01")


def _cents(value: Decimal) -> Decimal:
    return value.quantize(_CENT)


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
    ``GET .../adjustable`` already returns).  Every key visible in either
    snapshot or in the aggregated journal is checked, so a persisted drift that
    has no journal row cannot hide behind an otherwise balanced correction.

    What the journal is compared WITH is derived the way the Rettifiche tab
    derives the statement, because the journal never names what the tab
    recomputes (AMBIENTA, 2026-09-17: nine «differences», none of them an
    unexplained movement, and the dossier blocked):

    - an aggregate moves by the sum of its details' adjustments
      (``importers.iv_cee_hierarchy.detail_fields``); a leaf row that already
      explains its parent's difference is reported once, on the leaf;
    - ``sp13_utile_perdita`` moves with the P&L result
      (``calculations.ce_result``), because the tab recomputes it from the CE.

    Three movements are then *declared*, never absorbed, and do not block:

    - ``adjustments_details_realigned`` — details that moved while their
      aggregate did exactly what the journal says: the save realigned a detail
      breakdown that the import left inconsistent with its total;
    - ``adjustments_profit_realigned`` — ``sp13`` recomputed from the CE when
      the import had them apart (verifiable: after the save the gap is zero);
    - ``adjustments_rounding`` — anything else within ``ROUNDING_DECLARED``.

    Everything beyond that stays a blocking ``adjustments_unreconciled``.
    """
    from importers.iv_cee_hierarchy import aggregates_with_details, detail_fields
    from calculations.ce_result import calculate_ce_result

    entries = list(entries)
    adjustments = signed_deltas(entries)
    unposted = unposted_mass(entries)
    # The client writes the journal in floating point (100000.21999999997): a
    # statement is kept to the cent, so is the comparison.
    expected = {code: _cents(value) for code, value in adjustments.items()}
    all_codes = (set(before) | set(after) | set(adjustments)) - UNPOSTED_SENTINEL_FIELDS
    actual = {code: _cents(_decimal(after.get(code)) - _decimal(before.get(code))) for code in all_codes}

    for aggregate in aggregates_with_details():
        if aggregate in all_codes and aggregate not in expected:
            expected[aggregate] = sum((expected.get(d, ZERO) for d in detail_fields(aggregate)), ZERO)
    profit = "sp13_utile_perdita"
    profit_gap_before = profit_gap_after = ZERO
    if profit in all_codes and profit not in expected:
        result_before = _cents(calculate_ce_result(dict(before)).net_profit)
        result_after = _cents(calculate_ce_result(dict(after)).net_profit)
        expected[profit] = result_after - result_before
        profit_gap_before = result_before - _cents(_decimal(before.get(profit)))
        profit_gap_after = result_after - _cents(_decimal(after.get(profit)))

    raw = {code: actual[code] - expected.get(code, ZERO) for code in sorted(all_codes)}
    raw = {code: diff for code, diff in raw.items() if abs(diff) > tolerance}

    realigned: dict[str, Decimal] = {}
    for aggregate in aggregates_with_details():
        details = [d for d in detail_fields(aggregate) if d in raw]
        if not details:
            continue
        parent = raw.get(aggregate, ZERO)
        children = sum((raw[d] for d in details), ZERO)
        if abs(parent) <= tolerance:
            # The total did what the journal says; only its breakdown moved.
            for d in details:
                realigned[d] = raw.pop(d)
        elif abs(parent - children) <= tolerance:
            # The leaves carry the whole difference: say it once, where it is.
            raw.pop(aggregate)

    profit_realigned = ZERO
    if profit in raw and abs(profit_gap_after) <= tolerance and abs(raw[profit] - profit_gap_before) <= tolerance:
        profit_realigned = raw.pop(profit)

    rounding = {code: diff for code, diff in raw.items() if abs(diff) <= ROUNDING_DECLARED}
    differences = {code: diff for code, diff in raw.items() if code not in rounding}

    def _elenco(items: Mapping[str, Decimal]) -> str:
        return ", ".join(f"{code} {eur_it(value)}" for code, value in sorted(items.items()))

    diagnostics: tuple[Diagnostic, ...] = ()
    if differences:
        diagnostics += (
            _diagnostic(
                "adjustments_unreconciled",
                "error",
                "adjustments",
                f"La riconciliazione rettifiche non quadra: {_elenco(differences)}",
            ),
        )
    if realigned:
        diagnostics += (
            _diagnostic(
                "adjustments_details_realigned",
                "warning",
                "adjustments",
                f"Dettagli riallineati al proprio totale, che non cambia: {_elenco(realigned)}. "
                "L'import li aveva incoerenti con il totale e il salvataggio delle rettifiche li ha corretti.",
            ),
        )
    if profit_realigned:
        diagnostics += (
            _diagnostic(
                "adjustments_profit_realigned",
                "warning",
                "adjustments",
                f"Utile dello stato patrimoniale riallineato al conto economico: {eur_it(profit_realigned)}. "
                "L'import li aveva distanti di questo importo.",
            ),
        )
    if rounding:
        diagnostics += (
            _diagnostic(
                "adjustments_rounding",
                "warning",
                "adjustments",
                f"Scarti di arrotondamento fra giornale e bilancio: {_elenco(rounding)}.",
            ),
        )
    if unposted:
        diagnostics += (
            _diagnostic(
                "adjustments_unposted_mass",
                "warning",
                "adjustments",
                f"{eur_it(unposted)} movimentati su un'intestazione non di bilancio: "
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
