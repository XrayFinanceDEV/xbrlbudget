"""M1-05B — pure read-model mapping of budget assumptions into the report.

One function, ``build_assumption_sections``, turns the persisted
``BudgetAssumptions`` rows of a scenario into the seven authoritative wizard
sections of the final report contract.  Nothing here computes a forecast: the
module reads what the engines and the persistence milestones already stored and
*classifies* it for the report.

Rules, and where each one comes from:

* **Sections and fields** come from ``contracts/final_report_assumption_sections.json``
  through ``app.schemas.final_report.ASSUMPTION_SECTION_CATALOG`` — never a copy.
  That catalog is itself pinned to ``frontend/lib/budget-wizard-steps.ts`` by
  ``tests/test_final_report_contract.py``, so the backend has exactly one list.
* **Provenance** (spec §6.4) is read from the per-row
  ``explicitly_supplied_fields`` list (M1-01).  A value is NEVER classified by
  comparing it with a schema default — a user may have confirmed the default
  on purpose.  A row whose list is NULL predates provenance tracking and makes
  the whole series ``legacy_unknown``, with one non-blocking diagnostic.
* **DEAD_FIELDS** (``investments``, ``receivables_short_growth_pct``,
  ``payables_short_growth_pct``, ``interest_rate_receivables``,
  ``interest_rate_payables``) are columns no wizard step shows and no active
  driver path reads; they can never appear as an assumption here because only
  catalog fields are mapped.  The legacy ``investments`` total is the one dead
  column that is *not* inert: ``ForecastEngine._get_split_investments`` raises
  when it is valued without the tangible/intangible splits, so it is declared
  through a diagnostic instead of being presented as an active driver.
* **Nested structures** (financing loans, pregresso runoff plans, temporary
  tax differences, CE/SP overrides, SP indexing) stay tables — parsed with the
  same Pydantic input schemas the API uses, never flattened to text.
* **Ignored** values use the one engine-documented case reachable from
  persisted data alone: ``forecast_engine`` reads ``ce20_override`` *instead
  of* the ``tax_rate`` components (``calculations/forecast_engine.py``, the
  ``if assumption.ce20_override is not None`` branch), so when every plan year
  carries that override the ``tax_rate`` value is present but drives nothing.

Amounts are ``Decimal`` end to end; a JSON bag that stored a number as text or
float is converted, never silently trusted as a numeric type.
"""
from __future__ import annotations

import sys
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, NamedTuple, Optional, Sequence, get_args

_backend_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

from pydantic import ValidationError

from app.schemas.budget import (
    FinancingLoanInput,
    PregressoInput,
    TemporaryDifferenceInput,
)
from app.schemas.final_report import (
    ASSUMPTION_SECTION_CATALOG,
    CEOverrideField,
    AssumptionSection,
    AssumptionValue,
    CEOverride,
    Diagnostic,
    FinancingLoan,
    Pregresso as PregressoContract,
    RunoffPlan,
    SPIndexing,
    SPOverride,
    TaxRunoffPlan,
    TemporaryDifference,
)
from database.models import BudgetAssumptions

ZERO = Decimal("0")

#: The one authoritative section/field catalog (see module docstring).
CATALOG: Sequence[Mapping[str, Any]] = ASSUMPTION_SECTION_CATALOG

#: ``Literal`` of the contract — the authoritative list of CE override columns.
CE_OVERRIDE_COLUMNS: tuple[str, ...] = tuple(get_args(CEOverrideField))

_STRUCTURAL_COLUMNS = frozenset({
    "id", "scenario_id", "forecast_year", "explicitly_supplied_fields",
    "created_at", "updated_at",
})


def _catalog_field_names() -> set[str]:
    names: set[str] = set()
    for section in CATALOG:
        names.update(section["fields"])
        names.update(section.get("nested_fields", []))
    return names


def dead_assumption_fields() -> frozenset[str]:
    """Persisted assumption columns mapped nowhere: the dead-field set.

    Parity with ``DEAD_FIELDS`` in ``frontend/lib/budget-wizard-steps.ts`` is
    asserted by ``tests/test_m1_05b_assumption_sections.py``, not copied here.
    """
    columns = {column.name for column in BudgetAssumptions.__table__.columns}
    mapped = _catalog_field_names() | set(CE_OVERRIDE_COLUMNS) | _STRUCTURAL_COLUMNS
    return frozenset(columns - mapped)


#: Nested-table fields, keyed by the catalog name they are emitted under.
#: ``financing_loans`` and ``tax_temporary_differences`` are catalog *fields*
#: but carry JSON tables, so they render through the nested path too.
_PRESENCE_NESTED_FIELDS = frozenset({"financing_loans", "sp_indexing", "tax_temporary_differences"})
_OVERRIDE_NESTED_FIELDS = frozenset({"ce_overrides", "sp_overrides"})
_NESTED_FIELDS = _PRESENCE_NESTED_FIELDS | _OVERRIDE_NESTED_FIELDS | {"pregresso"}

#: Display labels for the report body.  The field *sets* stay in the catalog;
#: this is presentation text owned by the read model (the contract requires a
#: label per assumption and no backend label source exists yet).
FIELD_LABELS: Mapping[str, str] = {
    # fatturato
    "revenue_growth_pct": "Crescita ricavi %",
    "other_revenue_growth_pct": "Crescita altri ricavi %",
    # costi
    "fixed_materials_percentage": "Quota fissa materie %",
    "fixed_services_percentage": "Quota fissa servizi %",
    "variable_materials_growth_pct": "Crescita materie variabile %",
    "variable_services_growth_pct": "Crescita servizi variabile %",
    "fixed_materials_growth_pct": "Crescita materie fissa %",
    "fixed_services_growth_pct": "Crescita servizi fissa %",
    "personnel_growth_pct": "Crescita personale %",
    "rent_growth_pct": "Crescita godimento beni di terzi %",
    # altre voci CE
    "other_costs_growth_pct": "Crescita oneri diversi %",
    "ce_overrides": "Override CE",
    # circolante
    "dso_days": "DSO (giorni incasso)",
    "dio_days": "DIO (giorni magazzino)",
    "dpo_days": "DPO (giorni pagamento)",
    "receivables_long_growth_pct": "Crescita crediti verso soci (lungo) %",
    "sp01_growth_pct": "Crescita crediti verso soci %",
    "sp04_growth_pct": "Crescita immobilizzazioni finanziarie %",
    "sp06e_growth_pct": "Crescita crediti tributari %",
    "sp06f_growth_pct": "Crescita imposte anticipate %",
    "sp08_growth_pct": "Crescita attività finanziarie correnti %",
    "sp10_growth_pct": "Crescita ratei e risconti attivi %",
    "sp14_growth_pct": "Crescita fondi per rischi e oneri %",
    "sp16f_growth_pct": "Crescita debiti previdenziali (breve) %",
    "sp16g_growth_pct": "Crescita altri debiti (breve) %",
    "sp17d_growth_pct": "Crescita debiti fornitori (lungo) %",
    "sp17f_growth_pct": "Crescita debiti previdenziali (lungo) %",
    "sp17g_growth_pct": "Crescita altri debiti (lungo) %",
    "sp18_growth_pct": "Crescita ratei e risconti passivi %",
    "previdenza_scales_with_personnel": "Previdenza scala con personale",
    "tfr_accrual_suspended": "Accantonamento TFR sospeso",
    "sp_indexing": "Indicizzazione SP",
    "sp_overrides": "Override SP",
    # pregresso e nuovo
    "existing_debt_repayment_years": "Anni di rimborso debito bancario",
    "altri_finanz_repayment_years": "Anni di rimborso altri finanziatori",
    "financing_loans": "Finanziamenti",
    "financing_amount": "Nuovo finanziamento",
    "financing_duration_years": "Durata finanziamento (anni)",
    "financing_interest_rate": "Tasso finanziamento %",
    "tangible_investments": "Investimenti materiali",
    "intangible_investments": "Investimenti immateriali",
    "depreciation_rate": "Aliquota ammortamenti materiali %",
    "depreciation_rate_intangible": "Aliquota ammortamenti immateriali %",
    "asset_disposal_nbv": "Valore netto contabile del cespite ceduto",
    "asset_disposal_proceeds": "Corrispettivo di cessione",
    "cash_sweep_enabled": "Cash sweep",
    "cash_sweep_min_cash": "Cassa minima del cash sweep",
    "overdraft_allowed": "Scoperto di conto consentito",
    "overdraft_limit": "Tetto dello scoperto",
    "pregresso": "Pregresso",
    # imposte
    "tax_rate": "Aliquota fiscale %",
    "tax_advances_paid": "Acconti d'imposta versati",
    "tax_temporary_differences": "Differenze temporanee",
    "sp16e_growth_pct": "Crescita debiti tributari (breve) %",
    "sp17e_growth_pct": "Crescita debiti tributari (lungo) %",
}


class AssumptionReadModel(NamedTuple):
    sections: list[AssumptionSection]
    diagnostics: list[Diagnostic]


def _diagnostic(code: str, severity: str, section: str, message: str) -> Diagnostic:
    return Diagnostic(code=code, severity=severity, section=section, message=message)


def _decimal(value: Any) -> Optional[Decimal]:
    """Coerce a persisted scalar to Decimal without trusting float round-trips."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean assumptions are scalars, not decimals")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        result = Decimal(repr(value))
    elif isinstance(value, str):
        try:
            result = Decimal(value)
        except InvalidOperation:
            raise ValueError(f"value {value!r} is not a decimal")
    else:
        raise ValueError(f"unsupported assumption value {type(value).__name__}")
    if not result.is_finite():
        return None
    return result


def _scalar(row: Any, field: str) -> Any:
    value = getattr(row, field, None)
    if isinstance(value, bool) or value is None:
        return value
    return _decimal(value)


def _supplied(row: Any) -> Optional[frozenset[str]]:
    """The persisted per-row supplied list, or None when the row predates it."""
    raw = getattr(row, "explicitly_supplied_fields", None)
    if raw is None:
        return None
    if not isinstance(raw, list) or any(not isinstance(name, str) for name in raw):
        return None
    return frozenset(raw)


def _years(rows: Sequence[Any]) -> str:
    return ", ".join(str(row.forecast_year) for row in rows)


def build_assumption_sections(rows: Iterable[Any]) -> AssumptionReadModel:
    """Map persisted assumption rows onto the seven contract sections, once each.

    ``rows`` are ``BudgetAssumptions`` ORM objects (or anything exposing the
    same attributes) of a single scenario; they are ordered by forecast year.
    """
    ordered = sorted(rows, key=lambda row: row.forecast_year)
    if not ordered:
        raise ValueError("build_assumption_sections richiede almeno una riga di ipotesi")

    diagnostics: list[Diagnostic] = []
    supplied_sets = [_supplied(row) for row in ordered]
    legacy_rows = [row for row, supplied in zip(ordered, supplied_sets) if supplied is None]
    if legacy_rows:
        diagnostics.append(_diagnostic(
            "legacy_assumption_provenance", "warning", "assumptions",
            f"Origine storica non disponibile per gli anni {_years(legacy_rows)}: "
            "input utente e default non distinguibili",
        ))

    diagnostics.extend(_legacy_investments_diagnostics(ordered))
    diagnostics.extend(_pregresso_position_diagnostics(ordered))

    sections: list[AssumptionSection] = []
    for section in CATALOG:
        assumptions = [
            _nested_assumption(ordered, supplied_sets, field, diagnostics)
            if field in _NESTED_FIELDS
            else _scalar_assumption(ordered, supplied_sets, field)
            for field in section["fields"]
        ] + [
            _nested_assumption(ordered, supplied_sets, field, diagnostics)
            for field in section.get("nested_fields", [])
        ]
        sections.append(AssumptionSection(key=section["key"], title=section["title"], assumptions=assumptions))
    return AssumptionReadModel(sections=sections, diagnostics=diagnostics)


# ---------------------------------------------------------------------------
# Scalars
# ---------------------------------------------------------------------------

def _scalar_assumption(
    rows: Sequence[Any],
    supplied_sets: Sequence[Optional[frozenset[str]]],
    field: str,
) -> AssumptionValue:
    values = [_scalar(row, field) for row in rows]
    provenance = _scalar_provenance(field, rows, supplied_sets, values)
    return AssumptionValue(
        field=field,
        label=FIELD_LABELS.get(field, field),
        values=values,
        provenance=provenance,
        active=True,
    )


def _scalar_provenance(
    field: str,
    rows: Sequence[Any],
    supplied_sets: Sequence[Optional[frozenset[str]]],
    values: Sequence[Any],
) -> str:
    if any(supplied is None for supplied in supplied_sets):
        return "legacy_unknown"
    # A value the engine never reads on this path loses the input-vs-default
    # question entirely: `ce20_override` replaces the tax computation, so the
    # `tax_rate` value drives nothing whatever its provenance was.
    if field == "tax_rate" and all(getattr(row, "ce20_override", None) is not None for row in rows):
        return "ignored"
    if any(field in supplied for supplied in supplied_sets if supplied is not None):
        return "user"
    if all(value is None for value in values):
        # NULL on every year is the documented "let the engine decide" state
        # (days derived from the base year, carry-forward balances, no floor,
        # no cap) — that is a rule, not a default someone confirmed.
        return "automatic"
    return "default"


# ---------------------------------------------------------------------------
# Nested tables
# ---------------------------------------------------------------------------

def _nested_assumption(
    rows: Sequence[Any],
    supplied_sets: Sequence[Optional[frozenset[str]]],
    field: str,
    diagnostics: list[Diagnostic],
) -> AssumptionValue:
    builder = {
        "ce_overrides": _ce_overrides,
        "sp_overrides": _sp_overrides,
        "sp_indexing": _sp_indexing,
        "financing_loans": _financing_loans,
        "pregresso": _pregresso,
        "tax_temporary_differences": _temporary_differences,
    }[field]
    data, invalid = builder(rows, field)
    diagnostics.extend(invalid)

    if any(supplied is None for supplied in supplied_sets):
        provenance = "legacy_unknown"
    elif data is None:
        provenance = "default"
    elif field in _OVERRIDE_NESTED_FIELDS:
        provenance = "override"
    else:
        provenance = "user"
    kwargs: dict[str, Any] = {
        "field": field,
        "label": FIELD_LABELS.get(field, field),
        "values": [None] * len(rows),
        "provenance": provenance,
        "active": True,
    }
    if data is not None:
        kwargs[field if field != "tax_temporary_differences" else "temporary_differences"] = data
    return AssumptionValue(**kwargs)


def _invalid_diagnostic(field: str, row: Any, error: Exception) -> Diagnostic:
    first_line = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
    return _diagnostic(
        "nested_assumption_invalid", "warning", "assumptions",
        f"Struttura nidificata di {field} non valida nell'anno {row.forecast_year}: {first_line}",
    )


def _ce_overrides(rows: Sequence[Any], field: str) -> tuple[Optional[list[CEOverride]], list[Diagnostic]]:
    entries: list[CEOverride] = []
    for row in rows:
        for column in CE_OVERRIDE_COLUMNS:
            raw = getattr(row, column, None)
            if raw is None:
                continue
            try:
                entries.append(CEOverride(field=column, value=_decimal(raw)))
            except (ValueError, ValidationError) as error:
                return None, [_invalid_diagnostic(field, row, error)]
    return (entries or None), []


def _dict_bag(field: str, rows: Sequence[Any], convert: Any) -> tuple[Optional[list], list[Diagnostic]]:
    """Flatten a per-row JSON bag (``{code: value}``) into contract table rows.

    The contract has no per-year slot for nested entries, so entries arrive in
    year order, then by code: duplicates across years are kept apart by their
    own value (an SP override re-forced in a later year) and indexing rows
    simply repeat when a plan is unchanged.
    """
    entries: list = []
    diagnostics: list[Diagnostic] = []
    for row in rows:
        raw = getattr(row, field, None)
        if not isinstance(raw, dict):
            continue
        for key in sorted(raw):
            try:
                entries.append(convert(key, raw[key]))
            except (ValueError, ValidationError) as error:
                diagnostics.append(_invalid_diagnostic(field, row, error))
    return (entries or None), diagnostics


def _sp_overrides(rows: Sequence[Any], field: str) -> tuple[Optional[list[SPOverride]], list[Diagnostic]]:
    return _dict_bag(field, rows, lambda key, value: SPOverride(field=key, value=_decimal(value)))


def _sp_indexing(rows: Sequence[Any], field: str) -> tuple[Optional[list[SPIndexing]], list[Diagnostic]]:
    return _dict_bag(field, rows, lambda key, value: SPIndexing(field=key, driver=value))


def _financing_loans(rows: Sequence[Any], field: str) -> tuple[Optional[list[FinancingLoan]], list[Diagnostic]]:
    loans: list[FinancingLoan] = []
    diagnostics: list[Diagnostic] = []
    for row in rows:
        raw = getattr(row, field, None)
        if not isinstance(raw, list):
            continue
        for item in raw:
            try:
                parsed = FinancingLoanInput.model_validate(item)
            except (ValueError, ValidationError) as error:
                diagnostics.append(_invalid_diagnostic(field, row, error))
                continue
            loans.append(FinancingLoan(
                name=parsed.name,
                amount=parsed.amount,
                opening_residual=parsed.opening_residual,
                duration_years=parsed.duration_years,
                interest_rate=parsed.interest_rate,
                grace_years=parsed.grace_years,
                balloon_pct=parsed.balloon_pct,
                repayments=parsed.repayments,
            ))
    return (loans or None), diagnostics


def _temporary_differences(rows: Sequence[Any], field: str) -> tuple[Optional[list[TemporaryDifference]], list[Diagnostic]]:
    lines: list[TemporaryDifference] = []
    diagnostics: list[Diagnostic] = []
    for row in rows:
        raw = getattr(row, field, None)
        if not isinstance(raw, list):
            continue
        for item in raw:
            try:
                parsed = TemporaryDifferenceInput.model_validate(item)
            except (ValueError, ValidationError) as error:
                diagnostics.append(_invalid_diagnostic(field, row, error))
                continue
            lines.append(TemporaryDifference(
                name=parsed.name,
                kind=parsed.kind,
                maturity=parsed.maturity,
                opening_amount=parsed.opening_amount,
                additions=parsed.additions,
                reversals=parsed.reversals,
                tax_rate=parsed.tax_rate,
            ))
    return (lines or None), diagnostics


def _pregresso(rows: Sequence[Any], field: str) -> tuple[Optional[PregressoContract], list[Diagnostic]]:
    """The runoff plan is a snapshot of the base year, so only row 1 may carry it.

    ``ForecastEngine`` raises when a later row does; that is declared (see
    ``_pregresso_position_diagnostics``) and the plan itself is still rendered
    from wherever it was found, so a misplaced snapshot never disappears.
    """
    raw = None
    source_row = rows[0]
    for row in rows:
        candidate = getattr(row, field, None)
        if isinstance(candidate, dict) and candidate:
            raw, source_row = candidate, row
            break
    if not isinstance(raw, dict):
        return None, []
    try:
        parsed = PregressoInput.model_validate(raw)
    except (ValueError, ValidationError) as error:
        return None, [_invalid_diagnostic(field, source_row, error)]

    def plan(item: Any) -> Optional[RunoffPlan]:
        if item is None:
            return None
        return RunoffPlan(
            opening=item.opening,
            amounts=list(item.amounts),
            writeoff=None if item.writeoff is None else list(item.writeoff),
        )

    tributari = None
    if parsed.debiti_tributari is not None:
        tributari = TaxRunoffPlan(
            opening=parsed.debiti_tributari.opening,
            amounts=list(parsed.debiti_tributari.amounts),
            writeoff=None if parsed.debiti_tributari.writeoff is None else list(parsed.debiti_tributari.writeoff),
            saldo=parsed.debiti_tributari.saldo,
            rateizzato=parsed.debiti_tributari.rateizzato,
            acconto_pct=parsed.debiti_tributari.acconto_pct,
        )
    return PregressoContract(
        crediti_commerciali=plan(parsed.crediti_commerciali),
        debiti_fornitori=plan(parsed.debiti_fornitori),
        debiti_tributari=tributari,
        debiti_previdenziali=plan(parsed.debiti_previdenziali),
        altri_debiti=plan(parsed.altri_debiti),
    ), []


# ---------------------------------------------------------------------------
# Legacy / positional diagnostics
# ---------------------------------------------------------------------------

def _legacy_investments_diagnostics(rows: Sequence[Any]) -> list[Diagnostic]:
    """`investments` is inert only while the splits exist or it is zero.

    Valued alone it stops the engine (`_get_split_investments` raises on any
    non-zero total, whatever its sign), so it must surface as a diagnostic and
    never as an inert dead-field footnote.
    """
    blocked = [
        row for row in rows
        if (_decimal(getattr(row, "investments", None)) or ZERO) != ZERO
        and (_decimal(getattr(row, "intangible_investments", None)) or ZERO) <= ZERO
        and (_decimal(getattr(row, "tangible_investments", None)) or ZERO) <= ZERO
    ]
    if not blocked:
        return []
    return [_diagnostic(
        "legacy_investments_without_split", "warning", "assumptions",
        f"Investimenti legacy senza ripartizione negli anni {_years(blocked)}: "
        "la generazione del previsionale si ferma finché non sono indicati "
        "gli investimenti materiali e/o immateriali",
    )]


def _pregresso_position_diagnostics(rows: Sequence[Any]) -> list[Diagnostic]:
    late = [
        row for row in rows[1:]
        if isinstance(getattr(row, "pregresso", None), dict) and getattr(row, "pregresso")
    ]
    if not late:
        return []
    return [_diagnostic(
        "pregresso_beyond_first_year", "warning", "assumptions",
        f"Scadenziamento del pregresso anche sugli anni {_years(late)}: vale solo "
        "sulla riga del primo anno e la generazione del previsionale lo rifiuta",
    )]
