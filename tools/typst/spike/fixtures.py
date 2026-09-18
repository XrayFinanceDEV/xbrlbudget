"""Deterministic, synthetic-only report models for the Typst rendering spike.

These fixtures deliberately start from the versioned canonical contract examples,
but never write them.  They are rendering stress data, not accounting examples:
all amounts are explicit strings and labels say that they are synthetic.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Final, Literal

from backend.app.schemas.final_report import FinalReportModel, model_hash, source_hash


FixtureName = Literal["bilancio", "infrannuale", "startup"]

_REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[3]
_CANONICAL_DIR: Final = _REPOSITORY_ROOT / "tests" / "fixtures" / "final_report"
_FIXTURE_NAMES: Final[tuple[FixtureName, ...]] = ("bilancio", "infrannuale", "startup")
_FIXED_TIMESTAMP: Final = "2032-02-03T04:05:06Z"

# These are byte hashes, rather than model hashes.  They make an accidental edit
# to a canonical fixture visible to the spike harness without treating the
# canonical files as generated output.
# Le impronte delle fixture canoniche: servono a far notare una modifica
# ACCIDENTALE, non a vietarne una voluta. Erano ferme a prima del giro
# «sette passi» (507944e), che ha riscritto legittimamente le sezioni di
# ipotesi: da allora questo controllo era rosso, e non si vedeva perché
# senza il compilatore Typst installato l'intero file si salta.
CANONICAL_FIXTURE_SHA256: Final = {
    "bilancio": "d202fbbc5e07ca2f4654a024806e522223f8dc64c3d728f1fbef330bf57fb60c",
    "infrannuale": "629d7edc77846d7d56a1f753e9b2621887d7de6fc40ab142d92152a2f1358783",
    "startup": "3061389be8708c0a8bbb08bdd8f63ef50e5fb9a62ef4d42654cce1735c67843a",
}

# Metadata belongs to the harness, not to FinalReportModel.  In particular, the
# DSCR reference is a plotting instruction and must not become an API contract.
SPIKE_FIXTURE_MANIFEST: Final = {
    "bilancio": {
        "workflow": "bilancio",
        "year_count": 1,
        "purpose": "one-year annual report with dense tables and a negative operating result",
        "dscr_reference_line": "1.00",
    },
    "infrannuale": {
        "workflow": "infrannuale",
        "year_count": 3,
        "purpose": "three-year interim report with closing data and partial working-capital series",
        "dscr_reference_line": "1.00",
    },
    "startup": {
        "workflow": "startup",
        "year_count": 5,
        "purpose": "five-year synthetic startup report with zero, negative, and partial series",
        "dscr_reference_line": "1.00",
    },
}


# Explicit presentation test data; these are not formulas or a financial model.
_VALUES: Final = {
    "bilancio": {
        "revenue": ("125000.00",), "ebitda": ("-4250.50",), "net_result": ("-7800.00",),
        "operating": ("-2200.00",), "debt_service": ("-12500.00",), "free_cashflow": ("-14700.00",),
        "cash": ("0.00",), "financial_debt": ("84000.00",), "receivables": ("18500.00",),
        "dso": (None,), "dio": ("0.00",), "ebitda_margin": ("-3.40",), "net_margin": ("-6.24",),
        "dscr": ("0.86",), "interest_cover": ("0.72",),
    },
    "infrannuale": {
        "revenue": ("126150.00", "134400.00", "142050.00"),
        "ebitda": ("-1500.00", "8420.00", "12350.00"),
        "net_result": ("-4800.00", "2150.00", "5640.00"),
        "operating": ("-350.00", "9400.00", "13200.00"),
        "debt_service": ("-7200.00", "-7600.00", "-8100.00"),
        "free_cashflow": ("-7550.00", "1800.00", "5100.00"),
        "cash": ("1800.00", "3600.00", "8700.00"),
        "financial_debt": ("92500.00", "84900.00", "76800.00"),
        "receivables": ("25200.00", "26800.00", "28100.00"),
        "dso": (None, "72.00", "68.00"), "dio": ("0.00", "46.00", "44.00"),
        "ebitda_margin": ("-1.19", "6.26", "8.69"), "net_margin": ("-3.80", "1.60", "3.97"),
        "dscr": ("0.81", "1.16", "1.39"), "interest_cover": ("0.64", "1.31", "1.58"),
    },
    "startup": {
        "revenue": ("0.00", "48000.00", "125000.00", "214000.00", "335000.00"),
        "ebitda": ("-18500.00", "-6300.00", "8400.00", "26300.00", "49100.00"),
        "net_result": ("-22100.00", "-9800.00", "2100.00", "14100.00", "29800.00"),
        "operating": ("-20200.00", "-5900.00", "13200.00", "31400.00", "54800.00"),
        "debt_service": ("0.00", "-1800.00", "-9200.00", "-9600.00", "-10100.00"),
        "free_cashflow": ("-20200.00", "-7700.00", "4000.00", "21800.00", "44700.00"),
        "cash": ("35000.00", "27300.00", "31300.00", "53100.00", "97800.00"),
        "financial_debt": ("120000.00", "118200.00", "109000.00", "99400.00", "89300.00"),
        "receivables": ("0.00", "8600.00", "20200.00", "31800.00", "47500.00"),
        "dso": (None, None, "59.00", "54.00", "49.00"),
        "dio": (None, "0.00", "38.00", "35.00", "33.00"),
        "ebitda_margin": (None, "-13.13", "6.72", "12.29", "14.66"),
        "net_margin": (None, "-20.42", "1.68", "6.59", "8.90"),
        "dscr": (None, None, "1.04", "1.27", "1.51"),
        "interest_cover": (None, None, "1.18", "1.42", "1.73"),
    },
}

_ADJUSTMENT_AMOUNTS: Final = (
    "125.00", "-125.00", "840.50", "-840.50", "0.00", "1250.00", "-1250.00",
    "75.25", "-75.25", "3300.00", "-3300.00", "410.00", "-410.00", "980.75",
    "-980.75", "64.00", "-64.00", "215.40",
)

_NARRATIVE_TEXTS: Final = (
    "Sintesi esclusivamente sintetica per stressare impaginazione, sillabazione e rientri: "
    "nessun dato appartiene a clienti, fornitori o persone reali. La denominazione lunga "
    "serve a verificare la continuità visiva tra pagine e la leggibilità dei numeri negativi.",
    "Le rettifiche sono un campione artificiale ad alto volume, costruito con costanti esplicite "
    "per provare righe affollate, descrizioni italiane molto lunghe e date fisse senza deduzioni contabili.",
    "Le ipotesi comprendono finanziamenti, piani pregressi e differenze temporanee create soltanto "
    "per osservare tabelle multipagina, intestazioni ripetute e celle con valori nulli.",
    "L'andamento economico è fittizio: i ricavi, i margini e il risultato netto sono sequenze di test "
    "con zeri e segni negativi, non previsioni né risultati di un'impresa esistente.",
    "La sezione finanziaria usa liquidità, debito e copertura del servizio del debito come etichette "
    "di rendering; la linea di riferimento DSCR è metadata esterno al contratto del report.",
    "Rischi e azioni sono testo di prova. Il caso verifica elenchi densi, serie parziali, accenti italiani "
    "e il comportamento tipografico di paragrafi lunghi in uno scenario dichiaratamente sintetico.",
)


def _line(code: str, label: str, value: str) -> dict[str, str]:
    return {"code": code, "label": label, "value": value}


def _metric(key: str, label: str, values: tuple[str | None, ...]) -> dict[str, object]:
    return {"key": key, "label": label, "values": list(values)}


def _series(series_id: str, title: str, unit: str, years: list[int], metrics: list[dict[str, object]]) -> dict[str, object]:
    return {"id": series_id, "title": title, "unit": unit, "categories": years, "series": metrics}


def _forecast(years: list[int], values: dict[str, tuple[str | None, ...]]) -> dict[str, object]:
    rows = []
    for index, year in enumerate(years):
        calculations = []
        if values["dio"][index] is not None:
            calculations.append(_line("dio", "Giorni di giacenza sintetici", values["dio"][index]))
        if values["dso"][index] is not None:
            calculations.append(_line("dso", "Giorni medi di incasso sintetici", values["dso"][index]))
        if values["dscr"][index] is not None:
            calculations.extend((
                _line("dscr", "DSCR sintetico per test di linea di riferimento", values["dscr"][index]),
                _line("interest_cover", "Copertura interessi sintetica", values["interest_cover"][index]),
            ))
        rows.append({
            "year": year,
            "income_statement": [
                _line("revenue", "Ricavi sintetici da contratti pluriennali a denominazione molto estesa", values["revenue"][index]),
                _line("ebitda", "Margine operativo lordo sintetico", values["ebitda"][index]),
                _line("net_result", "Risultato netto sintetico dell'esercizio", values["net_result"][index]),
            ],
            "balance_sheet": [
                _line("cash", "Disponibilità liquide sintetiche", values["cash"][index]),
                _line("financial_debt", "Debito finanziario lordo sintetico a medio-lungo termine", values["financial_debt"][index]),
                _line("receivables", "Crediti commerciali sintetici con descrizione volutamente molto lunga", values["receivables"][index]),
            ],
            "cashflow": [
                _line("operating", "Flusso di cassa operativo sintetico", values["operating"][index]),
                _line("debt_service", "Servizio del debito sintetico", values["debt_service"][index]),
                _line("free_cashflow", "Flusso di cassa libero sintetico", values["free_cashflow"][index]),
            ],
            "calculations": calculations,
        })
    return {"years": rows}


def _chart_series(years: list[int], values: dict[str, tuple[str | None, ...]]) -> list[dict[str, object]]:
    return [
        _series("income_results", "Risultati economici sintetici con etichetta italiana intenzionalmente molto lunga", "eur", years, [
            _metric("revenue", "Ricavi sintetici", values["revenue"]),
            _metric("ebitda", "Margine operativo lordo sintetico", values["ebitda"]),
            _metric("net_result", "Risultato netto sintetico", values["net_result"]),
        ]),
        _series("margins", "Margini percentuali sintetici con serie parziali e valori negativi", "percent", years, [
            _metric("ebitda_margin", "Margine EBITDA sintetico", values["ebitda_margin"]),
            _metric("net_margin", "Margine netto sintetico", values["net_margin"]),
        ]),
        _series("cashflows", "Flussi finanziari sintetici per verifica di serie multiple", "eur", years, [
            _metric("operating", "Flusso operativo sintetico", values["operating"]),
            _metric("debt_service", "Servizio del debito sintetico", values["debt_service"]),
            _metric("free_cashflow", "Flusso libero sintetico", values["free_cashflow"]),
        ]),
        _series("liquidity_debt", "Liquidità e indebitamento sintetici in euro", "eur", years, [
            _metric("cash", "Liquidità sintetica", values["cash"]),
            _metric("financial_debt", "Debito finanziario sintetico", values["financial_debt"]),
            _metric("receivables", "Crediti commerciali sintetici", values["receivables"]),
        ]),
        _series("working_capital_days", "Giorni del capitale circolante sintetico e parzialmente disponibili", "days", years, [
            _metric("dso", "Giorni medi di incasso sintetici", values["dso"]),
            _metric("dio", "Giorni di giacenza sintetici", values["dio"]),
        ]),
        _series("coverage", "Copertura sintetica del debito con riferimento DSCR esterno", "ratio", years, [
            _metric("dscr", "DSCR sintetico", values["dscr"]),
            _metric("interest_cover", "Copertura interessi sintetica", values["interest_cover"]),
        ]),
    ]


def _adjustments() -> dict[str, object]:
    entries = []
    for index, amount in enumerate(_ADJUSTMENT_AMOUNTS, start=1):
        entries.append({
            "id": f"synthetic-adjustment-{index:02d}",
            "edited_field": f"ce{index:02d}_override",
            "edited_label": f"Rettifica sintetica numero {index:02d} con descrizione italiana volutamente molto lunga",
            "edit_delta": amount,
            "counterpart_field": f"sp{index:02d}_synthetic",
            "counterpart_label": f"Contropartita sintetica numero {index:02d} per stressare la colonna descrittiva",
            "counterpart_delta": amount,
            "explanation": "Voce artificiale per prova di tabella multipagina; non rappresenta un fatto aziendale.",
            "created_at": _FIXED_TIMESTAMP,
        })
    return {"confirmed": True, "entries": entries, "net_effect": "0.00"}


def _assumption_sections(year_count: int) -> list[dict[str, object]]:
    empty = [None] * year_count
    zeroes = ["0.00"] * year_count
    return [
        {"key": "scenario", "title": "Scenario sintetico", "assumptions": []},
        {"key": "fatturato", "title": "Fatturato sintetico", "assumptions": [{
            "field": "revenue_growth_pct", "label": "Crescita ricavi sintetica", "values": zeroes,
            "provenance": "user", "active": True,
        }]},
        {"key": "costi", "title": "Costi principali sintetici", "assumptions": [{
            "field": "personnel_growth_pct", "label": "Crescita personale sintetica", "values": empty,
            "provenance": "automatic", "active": True,
        # Il catalogo delle sezioni (contracts/final_report_assumption_sections.json)
        # ha SETTE chiavi, e queste prove erano rimaste su quelle vecchie:
        # «altre-voci-ce» e «pregresso-nuovo» non esistono più, e `sp_indexing`
        # appartiene a «patrimoniale-piano», non al circolante. La fixture non
        # si costruiva più, ma il fallimento si vedeva solo con il compilatore
        # Typst installato — senza, questi test si saltano.
        }, {
            "field": "ce_overrides", "label": "Override economici sintetici ad alta densità", "values": empty,
            "provenance": "override", "active": True,
            "ce_overrides": [
                {"field": field, "value": value}
                for field, value in (("ce01_override", "0.00"), ("ce03_override", "-120.50"), ("ce08_override", "340.00"), ("ce11_override", "-85.25"), ("ce17_override", "625.00"), ("ce20_override", "-42.00"))
            ],
        }]},
        {"key": "circolante", "title": "Capitale circolante sintetico", "assumptions": [{
            "field": "dso_days", "label": "Giorni incasso sintetici", "values": empty,
            "provenance": "user", "active": True,
        }]},
        {"key": "patrimoniale-pregresso", "title": "Pregresso e nuovo sintetico", "assumptions": [{
            "field": "financing_loans", "label": "Finanziamenti sintetici per prova di tabella multipagina", "values": empty,
            "provenance": "user", "active": True,
            "financing_loans": [
                {"name": f"Prestito sintetico {number:02d} con denominazione italiana molto lunga", "amount": amount,
                 "opening_residual": residual, "duration_years": duration, "interest_rate": rate,
                 "grace_years": grace, "balloon_pct": balloon}
                for number, amount, residual, duration, rate, grace, balloon in (
                    (1, "120000.00", "120000.00", 7, "3.25", 1, "0.00"), (2, "85000.50", "85000.50", 5, "4.10", 0, "10.00"),
                    (3, "0.00", "42000.00", 4, "2.90", 0, "0.00"), (4, "31000.00", "31000.00", 3, "5.00", 0, "25.00"),
                    (5, "76500.75", "76500.75", 8, "3.80", 2, "15.00"), (6, "18000.00", "18000.00", 2, "6.25", 0, "0.00"),
                )
            ],
        }, {
            "field": "pregresso", "label": "Piani pregressi sintetici con scadenze e valori negativi", "values": empty,
            "provenance": "user", "active": True,
            "pregresso": {
                "crediti_commerciali": {"opening": "24500.00", "amounts": ["8200.00", "8100.00", "8200.00"], "writeoff": ["0.00", "-250.00", "0.00"]},
                "debiti_fornitori": {"opening": "19400.00", "amounts": ["6400.00", "6500.00", "6500.00"]},
                "debiti_tributari": {"opening": "11800.00", "amounts": ["3900.00", "3950.00", "3950.00"], "saldo": "2900.00", "rateizzato": "4900.00", "acconto_pct": "40.00"},
                "debiti_previdenziali": {"opening": "7300.00", "amounts": ["2400.00", "2450.00", "2450.00"]},
                "altri_debiti": {"opening": "5100.00", "amounts": ["1700.00", "1700.00", "1700.00"]},
            },
        }]},
        {"key": "patrimoniale-piano", "title": "Patrimoniale piano sintetica", "assumptions": [{
            "field": "sp_indexing", "label": "Indicizzazioni sintetiche con etichette estese", "values": empty,
            "provenance": "automatic", "active": True,
            "sp_indexing": [
                {"field": "sp01_growth_pct", "driver": "ricavi"}, {"field": "sp04_growth_pct", "driver": "acquisti"},
                {"field": "sp06e_growth_pct", "driver": "personale"}, {"field": "sp16f_growth_pct", "driver": "ricavi"},
            ],
        }]},
        {"key": "imposte", "title": "Imposte sintetiche", "assumptions": [{
            "field": "tax_temporary_differences", "label": "Differenze temporanee sintetiche per tabella fiscale multipagina", "values": empty,
            "provenance": "user", "active": True,
            "temporary_differences": [
                {"name": f"Differenza temporanea sintetica {number:02d} con spiegazione estesa", "kind": kind,
                 "maturity": maturity, "opening_amount": opening, "additions": additions, "reversals": reversals, "tax_rate": rate}
                for number, kind, maturity, opening, additions, reversals, rate in (
                    (1, "deductible", "short", "1200.00", "0.00", "-400.00", "24.00"), (2, "taxable", "long", "-850.00", "250.00", "0.00", "24.00"),
                    (3, "deductible", "long", "3400.50", "620.00", "-300.00", "24.00"), (4, "taxable", "short", "-420.00", "0.00", "210.00", None),
                    (5, "deductible", "short", "0.00", "950.00", "0.00", "27.90"), (6, "taxable", "long", "-1750.00", "500.00", "-125.00", "24.00"),
                    (7, "deductible", "long", "2140.00", "0.00", "-710.00", "24.00"), (8, "taxable", "short", "-90.00", "45.00", "0.00", "24.00"),
                )
            ],
        }]},
    ]


def _narrative() -> list[dict[str, str]]:
    ids = ("executive_summary", "adjustments_and_closing", "budget_assumptions", "economic_outlook", "financial_outlook", "risks_and_actions")
    return [{
        "id": block_id, "text": text, "provenance": "user", "updated_at": _FIXED_TIMESTAMP,
        "source_hash": f"{index:064x}", "freshness": "fresh",
    } for index, (block_id, text) in enumerate(zip(ids, _NARRATIVE_TEXTS), start=1)]


def _canonical_payload(name: FixtureName) -> dict[str, object]:
    """Read a canonical fixture without modifying its bytes or in-memory object."""
    return json.loads((_CANONICAL_DIR / f"{name}.json").read_text(encoding="utf-8"))


def build_spike_fixture(name: FixtureName) -> FinalReportModel:
    """Return one strict, self-contained synthetic rendering fixture.

    Hashes are calculated on the completed payload and validation below uses no
    context flags.  Returned objects therefore cannot rely on hash-validation
    bypasses.
    """
    if name not in _FIXTURE_NAMES:
        raise ValueError(f"unknown spike fixture: {name}")
    payload = copy.deepcopy(_canonical_payload(name))
    years = list(payload["practice"]["periods"]["forecast_years"])
    values = _VALUES[name]
    payload["generated_at"] = _FIXED_TIMESTAMP
    payload["company"] = {
        "id": {"bilancio": 9101, "infrannuale": 9102, "startup": 9103}[name],
        "name": "Società dimostrativa sintetica per impaginazione finanziaria italiana a denominazione eccezionalmente lunga",
        "tax_id": "SYNTHETIC-NO-REAL-CUSTOMER-DATA",
    }
    payload["practice"]["budget_scenario"]["name"] = "Scenario sintetico per prova Typst — nessun dato operativo reale"
    if payload["practice"].get("source_scenario") is not None:
        payload["practice"]["source_scenario"]["name"] = "Sorgente sintetica per confronto di rendering a testo lungo"
    payload["source_revisions"] = [{"source": "calculation_engine", "identifier": "typst-spike-synthetic", "revision": "fixed-2032-02-03", "revision_at": _FIXED_TIMESTAMP, "available": True}]
    payload["adjustments"] = _adjustments()
    payload["assumption_sections"] = _assumption_sections(len(years))
    payload["forecast"] = _forecast(years, values)
    payload["chart_series"] = _chart_series(years, values)
    payload["narrative"] = _narrative()
    payload["diagnostics"] = [{
        "code": "synthetic_rendering_fixture", "severity": "info", "section": "typst-spike",
        "message": "Dati interamente sintetici: non usare per decisioni economiche o operative.",
    }]
    payload["source_data_quality"] = {"status": "complete", "diagnostics": []}
    payload["readiness"] = {"status": "ready", "reasons": []}
    # Hashing is defined over the parsed contract: Decimal("125000.00") is
    # canonicalized as "125000", unlike the raw wire string.  The short-lived
    # seed is used only to obtain that canonical representation; the returned
    # model below is always validated again with hash validation enabled.
    seed = FinalReportModel.model_validate(payload, context={"skip_hash_validation": True})
    payload["source_hash"] = source_hash(seed)
    payload["model_hash"] = model_hash(seed)
    return FinalReportModel.model_validate(payload)


def build_all_spike_fixtures() -> dict[FixtureName, FinalReportModel]:
    """Build the 1-, 3-, and 5-year synthetic fixture set in stable order."""
    return {name: build_spike_fixture(name) for name in _FIXTURE_NAMES}
