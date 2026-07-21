from decimal import Decimal
from pathlib import Path

import pytest
import fitz

from importers.pdf_extractor_llm import _declared_control_totals
from importers.iv_cee_hierarchy import check_quadratura
from importers.pdf_mapper import IVCEEMapper
from importers.standard_ivcee_parser import (
    extract_standard_ivcee_balances,
    extract_standard_ivcee_income,
    overlay_standard_ivcee_balance,
)


ROOT = Path(__file__).resolve().parents[1]
PDF_328 = (
    ROOT
    / "Test"
    / "successTerzo"
    / "success"
    / "budget_328_2025- ELLE ERRE BIL.pdf"
)


def _write_compact_infrannual_pdf(
    path: Path,
    *,
    period_months: int | None = 6,
    other_reserve_roman: str = "VII",
    negative_style: str = "minus",
    interest_style: str = "negative",
    positive_equity: bool = False,
    passivo_total_delta: Decimal = Decimal("0"),
) -> None:
    """Create configurable clean/bizarre monocolumn IV-CEE regression layouts."""
    def it_amount(value: Decimal) -> str:
        return (
            f"{value:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
        )

    def negative_amount(value: Decimal, style: str) -> str:
        absolute = it_amount(abs(value))
        if style == "parentheses":
            return f"({absolute})"
        if style == "trailing":
            return f"{absolute}-"
        return f"-{absolute}"

    if positive_equity:
        carried = Decimal("-85649.68")
        total_equity = Decimal("200000")
        tax_debt = Decimal("794335.07")
        total_debt = Decimal("2119247.51")
    else:
        carried = Decimal("-442263.65")
        total_equity = Decimal("-156613.97")
        tax_debt = Decimal("1150949.04")
        total_debt = Decimal("2475861.48")

    interest = Decimal("-9156.46")
    if interest_style == "positive":
        interest_printed = it_amount(abs(interest))
    elif interest_style == "parentheses":
        interest_printed = negative_amount(interest, "parentheses")
    else:
        interest_printed = negative_amount(interest, "minus")

    document = fitz.open()

    def add_page(title, rows):
        page = document.new_page()
        page.insert_text((50, 55), title, fontsize=12)
        y = 85
        for label, amount in rows:
            page.insert_text((50, y), label, fontsize=8)
            if amount is not None:
                page.insert_text((400, y), amount, fontsize=8)
            y += 14

    add_page(
        "STATO PATRIMONIALE - ATTIVO",
        [
            ("A) Crediti verso soci per versamenti ancora dovuti", "0,00"),
            ("B) Immobilizzazioni", None),
            ("I - Immobilizzazioni immateriali", None),
            ("2) Costi di sviluppo", "18.223,20"),
            ("3) Diritti di brevetto industriale", "0,00"),
            ("Totale immobilizzazioni immateriali", "18.223,20"),
            ("II - Immobilizzazioni materiali", None),
            ("1) Terreni e fabbricati", "1.126.709,57"),
            ("2) Impianti e macchinario", "88.469,22"),
            ("3) Attrezzature industriali e commerciali", "460.415,10"),
            ("4) Altri beni", "2.377,84"),
            ("Totale immobilizzazioni materiali", "1.677.971,73"),
            ("III - Immobilizzazioni finanziarie", "0,00"),
            ("Totale immobilizzazioni (B)", "1.696.194,93"),
            ("C) Attivo circolante", None),
            ("I - Rimanenze", None),
            ("1) Materie prime, sussidiarie e di consumo", "55.314,42"),
            ("2) Prodotti in corso di lavorazione e semilavorati", "53.347,80"),
            ("4) Prodotti finiti e merci", "35.800,00"),
            ("Totale rimanenze", "144.462,22"),
            ("II - Crediti (esigibili entro l'esercizio successivo)", None),
            ("1) Verso clienti", "401.191,32"),
            ("4-bis) Crediti tributari", "13.908,19"),
            ("5) Verso altri", "1.019,23"),
            ("Totale crediti", "416.118,74"),
            ("III - Attivita finanziarie non immobilizzate", "0,00"),
            ("IV - Disponibilita liquide", None),
            ("1) Depositi bancari e postali, cassa", "160.168,58"),
            ("Totale attivo circolante (C)", "720.749,54"),
            ("D) Ratei e risconti attivi", "643,78"),
            ("TOTALE ATTIVO (A+B+C+D)", "2.417.588,25"),
        ],
    )
    add_page(
        "STATO PATRIMONIALE - PASSIVO",
        [
            ("A) Patrimonio netto", None),
            ("I - Capitale sociale", "50.000,00"),
            ("IV - Riserva legale", "3.399,87"),
            (f"{other_reserve_roman} - Altre riserve", "160.039,46"),
            ("VIII - Utili (perdite) portati a nuovo", negative_amount(carried, negative_style)),
            ("IX - Utile (perdita) del periodo", "72.210,35"),
            ("Totale patrimonio netto (A)", (
                negative_amount(total_equity, negative_style)
                if total_equity < 0 else it_amount(total_equity)
            )),
            ("B) Fondi per rischi e oneri", "0,00"),
            ("C) Trattamento di fine rapporto di lavoro subordinato", "98.340,74"),
            ("D) Debiti (esigibili entro/oltre l'esercizio successivo)", None),
            ("4) Debiti verso banche", "321.113,81"),
            ("5) Debiti verso altri finanziatori", "268.040,29"),
            ("7) Debiti verso fornitori", "470.832,04"),
            ("12) Debiti tributari", it_amount(tax_debt)),
            ("13) Debiti verso istituti di previdenza", "215.847,82"),
            ("14) Altri debiti", "49.078,48"),
            ("Totale debiti (D)", it_amount(total_debt)),
            ("E) Ratei e risconti passivi", "0,00"),
            ("TOTALE PASSIVO (A+B+C+D+E)", it_amount(
                Decimal("2417588.25") + passivo_total_delta
            )),
        ],
    )
    add_page(
        (
            "CONTO ECONOMICO - Periodo 01/01/2026 - 31/12/2026"
            if period_months is None
            else f"CONTO ECONOMICO - Periodo 01/01/2026 - {period_months:02d}/2026"
        ),
        [
            ("A) Valore della produzione", None),
            ("1) Ricavi delle vendite e delle prestazioni", "403.702,34"),
            ("2) Variazione rimanenze prodotti in lavorazione", "-11.063,44"),
            ("5) Altri ricavi e proventi", "122,66"),
            ("Totale valore della produzione (A)", "392.761,56"),
            ("B) Costi della produzione", None),
            ("6) Per materie prime, sussidiarie, di consumo e merci", "138.210,93"),
            ("7) Per servizi", "69.037,11"),
            ("8) Per godimento di beni di terzi", "942,78"),
            ("9) Per il personale", None),
            ("a) salari e stipendi", "72.132,17"),
            ("b) oneri sociali", "21.917,80"),
            ("c) trattamento di fine rapporto", "5.152,69"),
            ("e) altri costi", "32,86"),
            ("10) Ammortamenti e svalutazioni", "0,00"),
            ("11) Variazione rimanenze materie prime", "-1.154,49"),
            ("14) Oneri diversi di gestione", "5.374,47"),
            ("Totale costi della produzione (B)", "311.646,32"),
            ("Differenza tra valore e costi della produzione (A - B)", "81.115,24"),
            ("C) Proventi e oneri finanziari", None),
            ("16) Altri proventi finanziari", "251,57"),
            ("17) Interessi e altri oneri finanziari", interest_printed),
            ("Totale proventi e oneri finanziari (C)", "-8.904,89"),
            ("D) Rettifiche di valore di attivita finanziarie", "0,00"),
            ("Risultato prima delle imposte", "72.210,35"),
            ("20) Imposte sul reddito dell'esercizio", "0,00"),
            ("21) UTILE (PERDITA) DEL PERIODO", "72.210,35"),
        ],
    )
    document.save(path)
    document.close()


def test_compact_infrannual_monocolumn_is_source_validated(tmp_path):
    pdf = tmp_path / "infrannual-monocolumn.pdf"
    _write_compact_infrannual_pdf(pdf)

    current, prior = extract_standard_ivcee_balances(str(pdf))
    current_ce, prior_ce = extract_standard_ivcee_income(str(pdf))

    assert current is not None
    assert current_ce is not None
    assert prior is None
    assert prior_ce is None
    assert current["totale_attivo"] == Decimal("2417588.25")
    assert current["totale_passivo"] == Decimal("2417588.25")
    assert current["sp12_riserve"] == Decimal("-278824.32")
    assert current["sp12e_altre_riserve"] == Decimal("160039.46")
    assert current["sp13_utile_perdita"] == Decimal("72210.35")
    assert IVCEEMapper().validate_balance(current)
    quadratura = check_quadratura(current, current_ce, tol=Decimal("2"))
    assert quadratura.quadra
    assert quadratura.semantic_valid
    assert quadratura.utile_ce == Decimal("72210.35")


def test_compact_infrannual_imports_without_prior_or_api_key(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base
    from database.models import FinancialYear
    from importers import pdf_importer

    pdf = tmp_path / "infrannual-monocolumn.pdf"
    _write_compact_infrannual_pdf(pdf)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    try:
        result = pdf_importer.import_pdf_balance_sheet(
            file_path=str(pdf),
            fiscal_year=2026,
            company_name="MONOCOLUMN SOURCE TEST",
            create_company=True,
            sector=1,
            period_months=6,
            user_id="source-test",
        )

        assert result["success"] is True
        assert result["extraction_method"] == "ivcee_source"
        assert result["prior_year_imported"] is False
        with sessions() as db:
            years = db.query(FinancialYear).all()
            assert len(years) == 1
            assert years[0].year == 2026
            assert years[0].period_months == 6
            assert years[0].validation_status == "verified"
            assert years[0].balance_sheet.total_assets == Decimal("2417588.25")
            assert years[0].income_statement.net_profit == Decimal("72210.35")
    finally:
        engine.dispose()


FULL_WORKFLOW_CASES = [
    pytest.param(
        None,
        True,
        "VI",
        "minus",
        "positive",
        id="annual-positive-equity-positive-interest",
    ),
    pytest.param(
        None,
        False,
        "VII",
        "minus",
        "negative",
        id="annual-negative-equity-abbreviated",
    ),
    pytest.param(
        6,
        False,
        "VII",
        "minus",
        "negative",
        id="six-month-no-prior",
    ),
    pytest.param(
        9,
        False,
        "VI",
        "parentheses",
        "parentheses",
        id="nine-month-parenthesized-negatives",
    ),
    pytest.param(
        3,
        False,
        "VII",
        "trailing",
        "parentheses",
        id="three-month-trailing-minus",
    ),
]


@pytest.mark.parametrize(
    "period_months,positive_equity,other_reserve_roman,negative_style,interest_style",
    FULL_WORKFLOW_CASES,
)
def test_pdf_to_adjustments_to_assumptions_full_workflow_matrix(
    tmp_path,
    monkeypatch,
    period_months,
    positive_equity,
    other_reserve_roman,
    negative_style,
    interest_style,
):
    """Exercise the same complete accounting journey used by the application.

    The matrix deliberately mixes normal and awkward but legal representations:
    annual/partial periods, no comparative year, negative equity, VI/VII reserve
    numbering, parentheses and trailing-minus amounts, and signed/unsigned costs.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.api.v1 import budget_scenarios, financial_years
    from backend.app.schemas.adjustments import AdjustmentsUpdate, RettificaEntry
    from backend.app.schemas.budget import BudgetScenarioCreate
    from backend.app.services.promote_service import (
        promote_projection_to_financial_year,
    )
    from database.db import Base
    from database.models import FinancialYear, ForecastYear
    from importers import pdf_importer

    case_name = (
        f"workflow-{period_months or 12}m-{negative_style}-"
        f"{'positive' if positive_equity else 'negative'}"
    )
    pdf = tmp_path / f"{case_name}.pdf"
    _write_compact_infrannual_pdf(
        pdf,
        period_months=period_months,
        positive_equity=positive_equity,
        other_reserve_roman=other_reserve_roman,
        negative_style=negative_style,
        interest_style=interest_style,
    )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    user_id = "workflow-matrix"

    try:
        imported = pdf_importer.import_pdf_balance_sheet(
            file_path=str(pdf),
            fiscal_year=2026,
            company_name=case_name,
            create_company=True,
            sector=1,
            period_months=period_months,
            user_id=user_id,
        )
        assert imported["success"] is True
        assert imported["extraction_method"] == "ivcee_source"
        assert imported["prior_year_imported"] is False
        company_id = imported["company_id"]

        with sessions() as db:
            editable = financial_years.get_adjustable_financial_year(
                company_id,
                2026,
                period_months=period_months,
                user_id=user_id,
                db=db,
            )
            original_cash = Decimal(
                str(editable.balance_sheet["sp09_disponibilita_liquide"])
            )
            original_bank_debt = Decimal(
                str(editable.balance_sheet["sp16a_debiti_banche_breve"])
            )
            original_total_debt = Decimal(
                str(editable.balance_sheet["sp16_debiti_breve"])
            )

            adjusted = financial_years.save_adjustments(
                company_id,
                2026,
                AdjustmentsUpdate(
                    balance_sheet={
                        "sp09_disponibilita_liquide": original_cash
                        + Decimal("1000"),
                        "sp16_debiti_breve": original_total_debt
                        + Decimal("1000"),
                        "sp16a_debiti_banche_breve": original_bank_debt
                        + Decimal("1000"),
                    },
                    income_statement={},
                    rettifiche_log=[
                        RettificaEntry(
                            id="matrix-cash-debt",
                            edited_field="sp09_disponibilita_liquide",
                            edited_label="Disponibilita liquide",
                            edit_delta=1000,
                            counterpart_field="sp16a_debiti_banche_breve",
                            counterpart_label="Debiti verso banche entro 12 mesi",
                            counterpart_delta=1000,
                            explanation="Rettifica bilanciata del test end-to-end",
                            created_at="2026-07-20T12:00:00Z",
                        )
                    ],
                ),
                period_months=period_months,
                user_id=user_id,
                db=db,
            )
            assert adjusted.validation_status == "verified"
            assert adjusted.forecastable is True
            assert len(adjusted.rettifiche_log) == 1
            assert Decimal(
                str(adjusted.original_balance_sheet["sp09_disponibilita_liquide"])
            ) == original_cash
            assert Decimal(
                str(adjusted.balance_sheet["sp09_disponibilita_liquide"])
            ) == original_cash + Decimal("1000")

            is_partial = period_months is not None
            scenario = budget_scenarios.create_budget_scenario(
                company_id,
                BudgetScenarioCreate(
                    company_id=company_id,
                    name=f"Scenario {case_name}",
                    base_year=2025 if is_partial else 2026,
                    scenario_type="infrannuale" if is_partial else "budget",
                    period_months=period_months,
                ),
                user_id=user_id,
                db=db,
            )

            forecast_years = [2026] if is_partial else [2027, 2028]
            assumptions = []
            for index, forecast_year in enumerate(forecast_years):
                assumptions.append(
                    {
                        "forecast_year": forecast_year,
                        "revenue_growth_pct": 5 + index,
                        "personnel_growth_pct": 2,
                        "fixed_materials_percentage": 40,
                        "fixed_services_percentage": 40,
                        "tax_rate": 24,
                        "tangible_investments": 10000 if index == 0 else 5000,
                        "ce01_override": 850000 + index * 50000,
                        "sp_overrides": {"sp11_capitale": 51000},
                        "financing_loans": (
                            [
                                {
                                    "name": "Mutuo matrice",
                                    # A 3-month loss-making annualization can
                                    # expose a sizeable explicit funding need.
                                    # Fund the valid-path matrix deliberately;
                                    # uncovered needs have separate diagnostic tests.
                                    "amount": 500000 if is_partial else 20000,
                                    "duration_years": 5,
                                    "interest_rate": 4,
                                    "grace_years": 1,
                                    "balloon_pct": 10,
                                }
                            ]
                            if index == 0
                            else None
                        ),
                        "tax_temporary_differences": [
                            {
                                "name": "Fondo temporaneo",
                                "kind": "deductible",
                                "maturity": "short",
                                "opening_amount": 1200,
                                "additions": 300,
                                "reversals": 100,
                                "tax_rate": 24,
                            }
                        ],
                    }
                )

            generated = budget_scenarios.bulk_upsert_assumptions(
                company_id,
                scenario.id,
                request={"assumptions": assumptions, "auto_generate": True},
                user_id=user_id,
                db=db,
            )
            assert generated["success"] is True
            assert generated["forecast_generated"] is True, generated["message"]
            assert generated["forecast_years"] == forecast_years

            forecasts = (
                db.query(ForecastYear)
                .filter(ForecastYear.scenario_id == scenario.id)
                .order_by(ForecastYear.year)
                .all()
            )
            assert [forecast.year for forecast in forecasts] == forecast_years
            for forecast in forecasts:
                assert (
                    forecast.balance_sheet.total_assets
                    == forecast.balance_sheet.total_liabilities
                )
                bs_values = {
                    column.name: Decimal(
                        str(getattr(forecast.balance_sheet, column.name, None) or 0)
                    )
                    for column in forecast.balance_sheet.__table__.columns
                    if column.name.startswith("sp")
                }
                ce_values = {
                    column.name: Decimal(
                        str(getattr(forecast.income_statement, column.name, None) or 0)
                    )
                    for column in forecast.income_statement.__table__.columns
                    if column.name.startswith("ce")
                }
                validation = check_quadratura(bs_values, ce_values)
                assert validation.semantic_valid, validation.warnings
                assert (
                    sum(
                        (
                            bs_values[field]
                            for field in (
                                "sp02a_costi_impianto",
                                "sp02b_costi_sviluppo",
                                "sp02c_brevetti",
                                "sp02d_concessioni",
                                "sp02e_avviamento",
                                "sp02f_immob_in_corso",
                                "sp02g_altre_immob_imm",
                            )
                        ),
                        Decimal("0"),
                    )
                    == bs_values["sp02_immob_immateriali"]
                )
                assert (
                    sum(
                        (
                            bs_values[field]
                            for field in (
                                "sp03a_terreni_fabbricati",
                                "sp03b_impianti_macchinari",
                                "sp03c_attrezzature",
                                "sp03d_altri_beni",
                                "sp03e_immob_in_corso",
                            )
                        ),
                        Decimal("0"),
                    )
                    == bs_values["sp03_immob_materiali"]
                )

            if is_partial:
                promoted = promote_projection_to_financial_year(db, scenario.id)
                assert promoted["verification"]["exact_match"] is True
                assert promoted["verification"]["semantic_valid"] is True
                promoted_year = db.query(FinancialYear).filter(
                    FinancialYear.id == promoted["financial_year_id"]
                ).one()
                assert promoted_year.year == 2026
                assert promoted_year.period_months is None
                assert promoted_year.forecastable is True
    finally:
        engine.dispose()


def test_contradictory_source_is_rejected_before_api_key_fallback(
    tmp_path, monkeypatch
):
    """A printed Attivo/Passivo mismatch is a source error, not an AI-key error."""
    from importers import pdf_importer

    pdf = tmp_path / "contradictory-source.pdf"
    _write_compact_infrannual_pdf(
        pdf,
        period_months=6,
        passivo_total_delta=Decimal("100"),
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(pdf_importer.PDFImportError) as raised:
        pdf_importer.import_pdf_balance_sheet(
            file_path=str(pdf),
            fiscal_year=2026,
            company_name="CONTRADICTORY SOURCE",
            create_company=True,
            sector=1,
            period_months=6,
            user_id="workflow-matrix",
        )

    message = str(raised.value)
    assert "non quadra prima dell'importazione" in message
    assert "scarto €100,00" in message
    assert "ANTHROPIC_API_KEY" not in message


def test_infrannual_llm_fallback_uses_single_year_when_prior_column_is_absent(
    tmp_path, monkeypatch
):
    """Non-standard monocolumn PDFs must never be forced into the dual-year prompt."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base
    from importers import pdf_extractor_llm, pdf_importer, standard_ivcee_parser

    pdf = tmp_path / "infrannual-monocolumn.pdf"
    _write_compact_infrannual_pdf(pdf)
    source_bs, _ = extract_standard_ivcee_balances(str(pdf))
    source_ce, _ = extract_standard_ivcee_income(str(pdf))
    llm_bs = {key: value for key, value in source_bs.items() if not key.startswith("_source")}
    llm_ce = {key: value for key, value in source_ce.items() if not key.startswith("_source")}
    calls = {"single": 0, "dual": 0}

    monkeypatch.setattr(
        standard_ivcee_parser, "extract_standard_ivcee_balances", lambda _path: (None, None)
    )
    monkeypatch.setattr(
        standard_ivcee_parser, "extract_standard_ivcee_income", lambda _path: (None, None)
    )
    monkeypatch.setattr(
        standard_ivcee_parser, "has_comparative_ivcee_columns", lambda _path: False
    )

    def single_year(_path, force_llm=False):
        calls["single"] += 1
        assert force_llm is True
        return dict(llm_bs), dict(llm_ce)

    def dual_year(_path):
        calls["dual"] += 1
        raise AssertionError("dual-year extractor must not be called")

    monkeypatch.setattr(pdf_extractor_llm, "extract_pdf_with_llm", single_year)
    monkeypatch.setattr(pdf_extractor_llm, "extract_pdf_both_years_with_llm", dual_year)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    try:
        result = pdf_importer.import_pdf_balance_sheet(
            file_path=str(pdf),
            fiscal_year=2026,
            company_name="MONOCOLUMN LLM FALLBACK TEST",
            create_company=True,
            sector=1,
            period_months=6,
            user_id="source-test",
        )
        assert result["success"] is True
        assert result["prior_year_imported"] is False
        assert calls == {"single": 1, "dual": 0}
    finally:
        engine.dispose()


def test_declared_controls_accept_whole_euro_thousands_totals():
    text = """
    Stato patrimoniale attivo
    Totale attivo
    6.474.612
    Stato patrimoniale passivo
    Totale passivo
    6.474.612
    Utile d'esercizio
    30.440
    Conto economico
    """

    controls = _declared_control_totals("unused.pdf", text=text)

    assert controls["attivo"] == Decimal("6474612")
    assert controls["passivo"] == Decimal("6474612")
    assert controls["utile"] == Decimal("30440")


def test_source_overlay_preserves_typed_llm_details():
    extracted = {
        "sp06_crediti_breve": Decimal("1"),
        "sp06a_crediti_clienti_breve": Decimal("2790956"),
    }
    source = {
        "sp06_crediti_breve": Decimal("2926403"),
        "totale_attivo": Decimal("6474612"),
    }

    result = overlay_standard_ivcee_balance(extracted, source)

    assert result["sp06_crediti_breve"] == Decimal("2926403")
    assert result["totale_attivo"] == Decimal("6474612")
    assert result["sp06a_crediti_clienti_breve"] == Decimal("2790956")


@pytest.mark.skipif(not PDF_328.exists(), reason="local PDF corpus not available")
def test_budget_328_source_balances_are_exact_and_self_validating():
    current, prior = extract_standard_ivcee_balances(str(PDF_328))
    current_ce, prior_ce = extract_standard_ivcee_income(str(PDF_328))

    assert current is not None
    assert current["totale_attivo"] == Decimal("6474612")
    assert current["totale_passivo"] == Decimal("6474612")
    assert current["sp13_utile_perdita"] == Decimal("30440")
    assert current["sp06_crediti_breve"] == Decimal("2926403")
    assert current["sp07_crediti_lungo"] == Decimal("73019")
    assert current["sp16_debiti_breve"] == Decimal("2683274")
    assert current["sp17_debiti_lungo"] == Decimal("303510")
    assert IVCEEMapper().validate_balance(current)
    assert current_ce is not None
    assert current_ce["ce10_var_rimanenze_mat_prime"] == Decimal("0")
    assert current_ce["ce11_accantonamenti"] == Decimal("12586")
    current_q = check_quadratura(current, current_ce, tol=Decimal("2"))
    assert current_q.quadra
    assert current_q.utile_ce == Decimal("30440")

    assert prior is not None
    assert prior["totale_attivo"] == Decimal("6783434")
    assert prior["totale_passivo"] == Decimal("6783434")
    assert IVCEEMapper().validate_balance(prior)
    assert prior_ce is not None
    assert prior_ce["ce10_var_rimanenze_mat_prime"] == Decimal("-300567")
    prior_q = check_quadratura(prior, prior_ce, tol=Decimal("2"))
    assert prior_q.quadra
    assert prior_q.utile_ce == Decimal("283549")


@pytest.mark.skipif(not PDF_328.exists(), reason="local PDF corpus not available")
def test_budget_328_imports_end_to_end_without_an_api_key(monkeypatch):
    """The production import must use verified source rows, not LLM luck."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from database.db import Base
    from database.models import FinancialYear
    from importers import pdf_importer

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(pdf_importer, "SessionLocal", sessions)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    try:
        result = pdf_importer.import_pdf_balance_sheet(
            file_path=str(PDF_328),
            fiscal_year=2025,
            company_name="ELLE ERRE SOURCE TEST",
            create_company=True,
            sector=1,
            user_id="source-test",
        )

        assert result["success"] is True
        assert result["extraction_method"] == "ivcee_source"
        assert result["prior_year_imported"] is True

        with sessions() as db:
            current = db.query(FinancialYear).filter_by(year=2025).one()
            prior = db.query(FinancialYear).filter_by(year=2024).one()
            assert current.balance_sheet.total_assets == Decimal("6474612")
            assert current.balance_sheet.total_liabilities == Decimal("6474612")
            assert current.balance_sheet.sp13_utile_perdita == Decimal("30440")
            assert current.income_statement.net_profit == Decimal("30440")
            assert prior.balance_sheet.total_assets == Decimal("6783434")
            assert prior.balance_sheet.total_liabilities == Decimal("6783434")
            assert prior.income_statement.net_profit == Decimal("283549")
    finally:
        engine.dispose()
