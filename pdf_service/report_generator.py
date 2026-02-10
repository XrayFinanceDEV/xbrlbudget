"""
Report Generator: orchestrator that loads data from the database,
runs calculators, generates charts, and passes everything to the PDF renderer.
"""
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session, joinedload
from io import BytesIO

from database import models
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from calculations.rating_fgpmi import FGPMICalculator
from pdf_service.em_score import calculate_em_score, get_em_score_description, EM_SCORE_TABLE
from pdf_service import charts
from pdf_service.styles import (
    CHART_BLUE, CHART_GREEN, CHART_RED, CHART_YELLOW,
    CHART_ORANGE, CHART_PURPLE, CHART_TEAL, CHART_GRAY,
    CHART_LIGHT_BLUE, CHART_LIGHT_GREEN,
)

# Try to import DetailedCashFlowCalculator
try:
    from backend.app.calculations.cashflow_detailed import DetailedCashFlowCalculator
except ImportError:
    try:
        from app.calculations.cashflow_detailed import DetailedCashFlowCalculator
    except ImportError:
        DetailedCashFlowCalculator = None


class YearData:
    """Container for one year's financial data and calculations."""

    def __init__(self, year: int, bs, inc, is_forecast: bool = False):
        self.year = year
        self.bs = bs
        self.inc = inc
        self.is_forecast = is_forecast
        self.ratios = None
        self.altman = None
        self.fgpmi = None
        self.cashflow = None


class ReportData:
    """All data needed for PDF report generation."""

    def __init__(self):
        self.company = None
        self.scenario = None
        self.sector = None
        self.years: List[YearData] = []
        self.chart_images: Dict[str, BytesIO] = {}
        self.em_score_rating = None
        self.em_score_z = None


def generate_report_data(db: Session, company_id: int,
                         scenario_id: int) -> ReportData:
    """
    Load all data and run calculations for a PDF report.

    Args:
        db: SQLAlchemy session
        company_id: Company ID
        scenario_id: Budget scenario ID

    Returns:
        ReportData with all computed values and chart images
    """
    data = ReportData()

    # 1. Load scenario with eager loading
    scenario = db.query(models.BudgetScenario)\
        .options(
            joinedload(models.BudgetScenario.company),
            joinedload(models.BudgetScenario.forecast_years)
                .joinedload(models.ForecastYear.balance_sheet),
            joinedload(models.BudgetScenario.forecast_years)
                .joinedload(models.ForecastYear.income_statement)
        )\
        .filter(
            models.BudgetScenario.id == scenario_id,
            models.BudgetScenario.company_id == company_id
        ).first()

    if not scenario:
        raise ValueError(f"Scenario {scenario_id} not found for company {company_id}")

    data.company = scenario.company
    data.scenario = scenario
    data.sector = scenario.company.sector

    # 2. Load historical years
    historical_years = db.query(models.FinancialYear)\
        .options(
            joinedload(models.FinancialYear.balance_sheet),
            joinedload(models.FinancialYear.income_statement)
        )\
        .filter(
            models.FinancialYear.company_id == company_id,
            models.FinancialYear.year >= scenario.base_year - 1,
            models.FinancialYear.year <= scenario.base_year
        )\
        .order_by(models.FinancialYear.year).all()

    for fy in historical_years:
        if fy.balance_sheet and fy.income_statement:
            data.years.append(YearData(
                fy.year, fy.balance_sheet, fy.income_statement, False))

    # 3. Load forecast years
    forecast_years_sorted = sorted(scenario.forecast_years, key=lambda x: x.year)
    for fy in forecast_years_sorted:
        if fy.balance_sheet and fy.income_statement:
            data.years.append(YearData(
                fy.year, fy.balance_sheet, fy.income_statement, True))

    if not data.years:
        raise ValueError("No financial data available for report")

    # 4. Run calculators for each year
    for yd in data.years:
        # Ratios
        calc = FinancialRatiosCalculator(yd.bs, yd.inc)
        yd.ratios = calc.calculate_all_ratios()

        # Altman
        altman_calc = AltmanCalculator(yd.bs, yd.inc, data.sector)
        yd.altman = altman_calc.calculate()

        # FGPMI
        fgpmi_calc = FGPMICalculator(yd.bs, yd.inc, data.sector)
        yd.fgpmi = fgpmi_calc.calculate()

    # 5. Calculate cashflow (needs year-over-year)
    if DetailedCashFlowCalculator:
        for i in range(1, len(data.years)):
            prev = data.years[i - 1]
            curr = data.years[i]
            try:
                curr.cashflow = DetailedCashFlowCalculator.calculate(
                    bs_current=curr.bs,
                    bs_previous=prev.bs,
                    inc_current=curr.inc,
                    year=curr.year
                )
            except Exception:
                curr.cashflow = None

    # 6. Calculate EM-Score (using most recent year)
    latest = data.years[-1]
    if data.sector == 1:
        # Manufacturing: recalculate Z-Score with services formula
        svc_calc = AltmanCalculator(latest.bs, latest.inc, 3)
        svc_result = svc_calc.calculate()
        em_z = svc_result.z_score
    else:
        em_z = latest.altman.z_score

    em_rating, em_z_used = calculate_em_score(em_z, data.sector)
    data.em_score_rating = em_rating
    data.em_score_z = em_z_used

    # 7. Generate chart images
    _generate_charts(data)

    return data


def _generate_charts(data: ReportData):
    """Generate all chart images for the report."""
    years = [yd.year for yd in data.years]
    latest = data.years[-1]

    # --- Dashboard gauges ---
    # Altman gauge
    z_score = float(latest.altman.z_score)
    if latest.altman.model_type == "manufacturing":
        thresholds = [(1.23, CHART_RED, "Rischio"), (2.9, CHART_YELLOW, "Ombra"),
                      (10, CHART_GREEN, "Sicuro")]
    else:
        thresholds = [(1.1, CHART_RED, "Rischio"), (2.6, CHART_YELLOW, "Ombra"),
                      (10, CHART_GREEN, "Sicuro")]
    data.chart_images['gauge_altman'] = charts.gauge_chart(
        z_score, 0, 10, "Altman Z-Score", thresholds,
        subtitle=latest.altman.classification.replace("_", " ").title())

    # FGPMI gauge
    fgpmi_pct = (latest.fgpmi.total_score / latest.fgpmi.max_score) * 100
    data.chart_images['gauge_fgpmi'] = charts.gauge_chart(
        fgpmi_pct, 0, 100, "Rating FGPMI",
        [(40, CHART_RED, "Rischio"), (65, CHART_YELLOW, "Medio"),
         (100, CHART_GREEN, "Buono")],
        subtitle=latest.fgpmi.rating_code)

    # EM-Score gauge
    em_z = float(data.em_score_z)
    data.chart_images['gauge_em'] = charts.gauge_chart(
        em_z, 0, 10, "EM-Score",
        [(3.2, CHART_RED, ""), (5.65, CHART_YELLOW, ""),
         (10, CHART_GREEN, "")],
        subtitle=data.em_score_rating)

    # --- Asset/Liability composition ---
    _generate_composition_charts(data, years)

    # --- Income margin charts ---
    _generate_income_charts(data, years)

    # --- Structural analysis ---
    _generate_structural_charts(data, years)

    # --- Ratio line charts ---
    _generate_ratio_charts(data, years)

    # --- Altman components ---
    latest_components = latest.altman.components
    comp_labels = ["A (CCN/TA)", "B (RIS/TA)", "C (EBIT/TA)", "D (CN/TD)"]
    comp_values = [float(latest_components.A), float(latest_components.B),
                   float(latest_components.C), float(latest_components.D)]
    if latest.altman.model_type == "manufacturing":
        comp_labels.append("E (FAT/TA)")
        comp_values.append(float(latest_components.E))
    comp_colors = [CHART_BLUE, CHART_GREEN, CHART_ORANGE, CHART_PURPLE, CHART_TEAL]
    data.chart_images['altman_components'] = charts.bar_chart(
        comp_labels, comp_values, "Componenti Z-Score",
        colors=comp_colors[:len(comp_values)], horizontal=True,
        size=(6, 3))

    # Altman trend
    if len(years) > 1:
        z_values = [float(yd.altman.z_score) for yd in data.years]
        data.chart_images['altman_trend'] = charts.line_chart(
            years,
            [{'label': 'Z-Score', 'values': z_values, 'color': CHART_BLUE}],
            "Andamento Z-Score", ylabel="Z-Score",
            y_zero_line=True, size=(6, 3))

    # --- FGPMI indicators ---
    ind_labels = [f"V{i}" for i in range(1, 8)]
    ind_points = [latest.fgpmi.indicators[f'V{i}'].points for i in range(1, 8)]
    ind_max = [latest.fgpmi.indicators[f'V{i}'].max_points for i in range(1, 8)]
    data.chart_images['fgpmi_indicators'] = charts.bar_chart(
        ind_labels, ind_points, "Indicatori FGPMI - Punteggi",
        colors=[CHART_BLUE if p >= m * 0.5 else CHART_RED
                for p, m in zip(ind_points, ind_max)],
        ylabel="Punti", size=(6, 3))

    # --- Break Even ---
    _generate_break_even_chart(data, years)

    # --- Cashflow ---
    _generate_cashflow_charts(data, years)


def _generate_composition_charts(data: ReportData, years: List[int]):
    """Generate asset and liability composition stacked bar charts."""
    # Asset composition as % of total assets
    asset_series = []
    fixed_pct = []
    inventory_pct = []
    receivables_pct = []
    cash_pct = []
    other_pct = []

    for yd in data.years:
        ta = float(yd.bs.total_assets) or 1
        fixed_pct.append(float(yd.bs.fixed_assets) / ta * 100)
        inventory_pct.append(float(yd.bs.sp05_rimanenze) / ta * 100)
        recv = float(yd.bs.sp06_crediti_breve) + float(yd.bs.sp07_crediti_lungo)
        receivables_pct.append(recv / ta * 100)
        cash_pct.append(float(yd.bs.sp09_disponibilita_liquide) / ta * 100)
        other_a = float(yd.bs.sp01_crediti_soci) + float(yd.bs.sp08_attivita_finanziarie) + float(yd.bs.sp10_ratei_risconti_attivi)
        other_pct.append(other_a / ta * 100)

    data.chart_images['composition_assets'] = charts.stacked_bar_chart(
        years,
        [
            {'label': 'Immobilizzazioni', 'values': fixed_pct, 'color': CHART_BLUE},
            {'label': 'Rimanenze', 'values': inventory_pct, 'color': CHART_TEAL},
            {'label': 'Crediti', 'values': receivables_pct, 'color': CHART_GREEN},
            {'label': 'Liquidita', 'values': cash_pct, 'color': CHART_LIGHT_GREEN},
            {'label': 'Altro', 'values': other_pct, 'color': CHART_GRAY},
        ],
        "Composizione dell'Attivo (%)")

    # Liability composition
    equity_pct = []
    lt_debt_pct = []
    st_debt_pct = []
    other_l_pct = []

    for yd in data.years:
        tp = float(yd.bs.total_liabilities) or 1
        equity_pct.append(float(yd.bs.total_equity) / tp * 100)
        lt_debt_pct.append(float(yd.bs.sp17_debiti_lungo) / tp * 100)
        st_debt_pct.append(float(yd.bs.sp16_debiti_breve) / tp * 100)
        other_l = (float(yd.bs.sp14_fondi_rischi) + float(yd.bs.sp15_tfr) +
                   float(yd.bs.sp18_ratei_risconti_passivi))
        other_l_pct.append(other_l / tp * 100)

    data.chart_images['composition_liabilities'] = charts.stacked_bar_chart(
        years,
        [
            {'label': 'Patrimonio Netto', 'values': equity_pct, 'color': CHART_BLUE},
            {'label': 'Debiti M/L termine', 'values': lt_debt_pct, 'color': CHART_ORANGE},
            {'label': 'Debiti a breve', 'values': st_debt_pct, 'color': CHART_RED},
            {'label': 'Fondi/TFR/Ratei', 'values': other_l_pct, 'color': CHART_GRAY},
        ],
        "Composizione del Passivo (%)")


def _generate_income_charts(data: ReportData, years: List[int]):
    """Generate income margin line charts."""
    revenue = [float(yd.inc.revenue) for yd in data.years]
    ebitda = [float(yd.inc.ebitda) for yd in data.years]
    ebit = [float(yd.inc.ebit) for yd in data.years]
    net_profit = [float(yd.inc.net_profit) for yd in data.years]

    data.chart_images['income_margins'] = charts.line_chart(
        years,
        [
            {'label': 'Ricavi', 'values': revenue, 'color': CHART_BLUE},
            {'label': 'EBITDA', 'values': ebitda, 'color': CHART_GREEN},
            {'label': 'EBIT', 'values': ebit, 'color': CHART_ORANGE},
            {'label': 'Utile Netto', 'values': net_profit, 'color': CHART_RED},
        ],
        "Andamento Margini di Reddito",
        ylabel="Euro", format_currency=True, y_zero_line=True)

    # Margin percentages
    ebitda_m = [float(yd.ratios['profitability'].ebitda_margin) * 100 for yd in data.years]
    ebit_m = [float(yd.ratios['profitability'].ebit_margin) * 100 for yd in data.years]
    net_m = [float(yd.ratios['profitability'].net_margin) * 100 for yd in data.years]

    data.chart_images['margin_pct'] = charts.line_chart(
        years,
        [
            {'label': 'EBITDA %', 'values': ebitda_m, 'color': CHART_GREEN},
            {'label': 'EBIT %', 'values': ebit_m, 'color': CHART_ORANGE},
            {'label': 'Utile Netto %', 'values': net_m, 'color': CHART_RED},
        ],
        "Margini di Reddito (%)",
        ylabel="%", format_pct=True, y_zero_line=True)

    # Waterfall for most recent year
    latest = data.years[-1]
    waterfall_labels = ['Ricavi', '+Variazioni', '-Mat.Prime', '-Servizi',
                        '-Personale', '-Ammort.', '-Altro', 'Utile Netto']
    prod_cost_other = (float(latest.inc.ce07_godimento_beni) +
                       float(latest.inc.ce10_var_rimanenze_mat_prime) +
                       float(latest.inc.ce11_accantonamenti) +
                       float(latest.inc.ce12_oneri_diversi) +
                       float(latest.inc.ce15_oneri_finanziari) +
                       float(latest.inc.ce20_imposte))
    other_income = (float(latest.inc.ce02_variazioni_rimanenze) +
                    float(latest.inc.ce03_lavori_interni) +
                    float(latest.inc.ce03a_incrementi_immobilizzazioni) +
                    float(latest.inc.ce04_altri_ricavi))

    waterfall_values = [
        float(latest.inc.revenue),
        other_income,
        -float(latest.inc.ce05_materie_prime),
        -float(latest.inc.ce06_servizi),
        -float(latest.inc.ce08_costi_personale),
        -float(latest.inc.ce09_ammortamenti),
        -prod_cost_other,
        float(latest.inc.net_profit),
    ]
    data.chart_images['income_waterfall'] = charts.waterfall_chart(
        waterfall_labels, waterfall_values,
        f"Da Ricavi a Utile Netto ({latest.year})")


def _generate_structural_charts(data: ReportData, years: List[int]):
    """Generate structural analysis charts (MS, CCN, MT)."""
    ms = [float(yd.ratios['working_capital'].ms) for yd in data.years]
    ccn = [float(yd.ratios['working_capital'].ccn) for yd in data.years]
    mt = [float(yd.ratios['working_capital'].mt) for yd in data.years]

    data.chart_images['structural'] = charts.line_chart(
        years,
        [
            {'label': 'Margine di Struttura', 'values': ms, 'color': CHART_BLUE},
            {'label': 'CCN', 'values': ccn, 'color': CHART_GREEN},
            {'label': 'Margine di Tesoreria', 'values': mt, 'color': CHART_ORANGE},
        ],
        "Analisi Strutturale",
        ylabel="Euro", format_currency=True, y_zero_line=True)


def _generate_ratio_charts(data: ReportData, years: List[int]):
    """Generate line charts for each ratio category."""
    if len(years) < 2:
        return

    # Liquidity
    cr = [float(yd.ratios['liquidity'].current_ratio) for yd in data.years]
    qr = [float(yd.ratios['liquidity'].quick_ratio) for yd in data.years]
    data.chart_images['ratio_liquidity'] = charts.line_chart(
        years,
        [
            {'label': 'Current Ratio', 'values': cr, 'color': CHART_BLUE},
            {'label': 'Quick Ratio', 'values': qr, 'color': CHART_GREEN},
        ],
        "Indici di Liquidita", ylabel="Ratio")

    # Solvency
    auto = [float(yd.ratios['solvency'].autonomy_index) * 100 for yd in data.years]
    dte = [float(yd.ratios['solvency'].debt_to_equity) for yd in data.years]
    data.chart_images['ratio_solvency'] = charts.line_chart(
        years,
        [
            {'label': 'Autonomia Fin. %', 'values': auto, 'color': CHART_BLUE},
        ],
        "Indice di Autonomia Finanziaria", ylabel="%", format_pct=True)

    # Profitability
    roe = [float(yd.ratios['profitability'].roe) * 100 for yd in data.years]
    roi = [float(yd.ratios['profitability'].roi) * 100 for yd in data.years]
    ros = [float(yd.ratios['profitability'].ros) * 100 for yd in data.years]
    rod = [float(yd.ratios['profitability'].rod) * 100 for yd in data.years]
    data.chart_images['ratio_profitability'] = charts.line_chart(
        years,
        [
            {'label': 'ROE', 'values': roe, 'color': CHART_BLUE},
            {'label': 'ROI', 'values': roi, 'color': CHART_GREEN},
            {'label': 'ROS', 'values': ros, 'color': CHART_ORANGE},
            {'label': 'ROD', 'values': rod, 'color': CHART_RED, 'linestyle': '--'},
        ],
        "Indici di Redditivita", ylabel="%", format_pct=True, y_zero_line=True)

    # Activity (days)
    inv_d = [float(yd.ratios['activity'].inventory_turnover_days) for yd in data.years]
    recv_d = [float(yd.ratios['activity'].receivables_turnover_days) for yd in data.years]
    pay_d = [float(yd.ratios['activity'].payables_turnover_days) for yd in data.years]
    data.chart_images['ratio_activity'] = charts.line_chart(
        years,
        [
            {'label': 'Giorni Magazzino', 'values': inv_d, 'color': CHART_BLUE},
            {'label': 'Giorni Crediti', 'values': recv_d, 'color': CHART_GREEN},
            {'label': 'Giorni Debiti', 'values': pay_d, 'color': CHART_RED},
        ],
        "Durata del Ciclo Operativo", ylabel="Giorni")

    # Coverage
    cov1 = [float(yd.ratios['coverage'].fixed_assets_coverage_with_equity_and_ltdebt) * 100
            for yd in data.years]
    cov2 = [float(yd.ratios['coverage'].fixed_assets_coverage_with_equity) * 100
            for yd in data.years]
    data.chart_images['ratio_coverage'] = charts.line_chart(
        years,
        [
            {'label': '(CN+PF)/AF', 'values': cov1, 'color': CHART_BLUE},
            {'label': 'CN/AF', 'values': cov2, 'color': CHART_GREEN},
        ],
        "Indici di Solidita (Copertura Immobilizzazioni)",
        ylabel="%", format_pct=True)


def _generate_break_even_chart(data: ReportData, years: List[int]):
    """Generate break-even analysis chart."""
    bep_rev = [float(yd.ratios['break_even'].break_even_revenue) for yd in data.years]
    actual_rev = [float(yd.inc.revenue) for yd in data.years]
    safety = [float(yd.ratios['break_even'].safety_margin) * 100 for yd in data.years]

    data.chart_images['break_even'] = charts.line_chart(
        years,
        [
            {'label': 'Ricavi Effettivi', 'values': actual_rev, 'color': CHART_BLUE},
            {'label': 'Break Even', 'values': bep_rev, 'color': CHART_RED,
             'linestyle': '--'},
        ],
        "Break Even Point", ylabel="Euro", format_currency=True)

    data.chart_images['safety_margin'] = charts.line_chart(
        years,
        [{'label': 'Margine di Sicurezza', 'values': safety, 'color': CHART_GREEN}],
        "Margine di Sicurezza", ylabel="%", format_pct=True, y_zero_line=True)


def _generate_cashflow_charts(data: ReportData, years: List[int]):
    """Generate cashflow summary charts."""
    cf_years = []
    op_cf = []
    inv_cf = []
    fin_cf = []

    for yd in data.years:
        if yd.cashflow:
            cf_years.append(yd.year)
            op_cf.append(float(yd.cashflow.operating_activities.total_operating_cashflow))
            inv_cf.append(float(yd.cashflow.investing_activities.total_investing_cashflow))
            fin_cf.append(float(yd.cashflow.financing_activities.total_financing_cashflow))

    if cf_years:
        data.chart_images['cashflow_summary'] = charts.line_chart(
            cf_years,
            [
                {'label': 'Operativo', 'values': op_cf, 'color': CHART_GREEN},
                {'label': 'Investimenti', 'values': inv_cf, 'color': CHART_RED},
                {'label': 'Finanziamento', 'values': fin_cf, 'color': CHART_BLUE},
            ],
            "Flussi di Cassa", ylabel="Euro", format_currency=True,
            y_zero_line=True)
