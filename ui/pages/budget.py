"""
Budget & Forecast Page
Create budget scenarios and input forecast assumptions
"""
import streamlit as st
from database.models import (
    Company, FinancialYear, BudgetScenario, BudgetAssumptions
)
from calculations.forecast_engine import generate_forecast_for_scenario
from decimal import Decimal


def _show_scenario_form(db, company, scenario=None, all_scenarios=None):
    """
    Show scenario creation/edit form with Excel-like table structure

    Args:
        db: Database session
        company: Company object
        scenario: BudgetScenario object (None for new scenario)
        all_scenarios: List of all scenarios (for context)
    """
    if scenario:
        st.subheader(f"✏️ Modifica Scenario: {scenario.name}")
    else:
        st.subheader("➕ Nuovo Scenario Budget")

    # Get available years for base year selection
    financial_years = db.query(FinancialYear).filter(
        FinancialYear.company_id == company.id
    ).order_by(FinancialYear.year.desc()).all()

    if not financial_years:
        st.error("❌ Nessun anno fiscale trovato. Importa prima i dati del bilancio.")
        return

    # Scenario details form
    st.markdown("### 1️⃣ Informazioni Scenario")

    # Automatically select the latest year as base year
    base_year = max(fy.year for fy in financial_years)

    col1, col2 = st.columns(2)

    with col1:
        scenario_name = st.text_input(
            "Nome Scenario *",
            value=scenario.name if scenario else "",
            placeholder="es. Budget 2025-2027"
        )

        st.info(f"📅 **Anno Base:** {base_year} (ultimo anno disponibile)")

    with col2:
        description = st.text_area(
            "Descrizione",
            value=scenario.description if scenario else "",
            placeholder="Descrizione dello scenario..."
        )

        is_active = st.checkbox(
            "Scenario Attivo",
            value=scenario.is_active if scenario else True
        )

    # Get base year data
    base_fy = db.query(FinancialYear).filter(
        FinancialYear.company_id == company.id,
        FinancialYear.year == base_year
    ).first()

    if not base_fy or not base_fy.income_statement or not base_fy.balance_sheet:
        st.error(f"❌ Dati completi non trovati per l'anno {base_year}")
        return

    base_inc = base_fy.income_statement
    base_bs = base_fy.balance_sheet

    st.markdown("---")

    # Get all available historical years
    historical_years = sorted([fy.year for fy in financial_years], reverse=True)

    # Fetch income statements for all historical years
    historical_data = {}
    for year in historical_years:
        fy = db.query(FinancialYear).filter(
            FinancialYear.company_id == company.id,
            FinancialYear.year == year
        ).first()
        if fy and fy.income_statement and fy.balance_sheet:
            historical_data[year] = {
                'income': fy.income_statement,
                'balance': fy.balance_sheet
            }

    # Number of forecast years
    existing_assumptions = {}
    if scenario:
        for assumption in db.query(BudgetAssumptions).filter(
            BudgetAssumptions.scenario_id == scenario.id
        ).all():
            existing_assumptions[assumption.forecast_year] = assumption

    num_years = st.number_input(
        "Numero di anni da prevedere",
        min_value=1,
        max_value=5,
        value=len(existing_assumptions) if existing_assumptions else 3,
        help="Numero di anni futuri da prevedere (default: 3)"
    )

    forecast_years = [base_year + i + 1 for i in range(num_years)]

    st.markdown("### 2️⃣ Ipotesi Previsionali")
    st.info("💡 Inserisci le ipotesi per ciascun anno. Le celle in blu rappresentano i valori modificabili.")

    # Get first assumption for common parameters
    first_assumption = existing_assumptions.get(forecast_years[0]) if existing_assumptions else None

    # Initialize data storage
    assumptions_data = []

    # Store fixed cost percentages for historical years
    historical_fixed_materials_pct = {}
    historical_fixed_services_pct = {}

    # Create table header
    st.markdown("---")
    st.markdown("#### VARIABILI ECONOMICHE")

    # Header row - show all historical years + forecast years
    total_years = len(historical_years) + num_years
    header_cols = st.columns([3] + [1] * total_years)
    with header_cols[0]:
        st.markdown("**ANNI ANALISI**")

    # Historical years (black text)
    for idx, year in enumerate(historical_years):
        with header_cols[idx + 1]:
            st.markdown(f"**{year}**")

    # Forecast years (blue text)
    for idx, year in enumerate(forecast_years):
        with header_cols[len(historical_years) + idx + 1]:
            st.markdown(f"**:blue[{year}]**")

    # Revenue growth
    st.markdown("---")
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % RICAVI RISPETTO ALL'ANNO BASE**")

    # Show historical revenue values
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            if year in historical_data:
                st.markdown(f"€ {historical_data[year]['income'].ce01_ricavi_vendite:,.0f}")
            else:
                st.markdown("—")

    # Input for forecast years
    revenue_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.revenue_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"rev_{year}",
                help="% da -100% a +1.000%"
            )
            revenue_growth_values.append(val)

    # Other revenue growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % ALTRI RICAVI RISPETTO ALL'ANNO BASE**")

    # Show historical other revenue values
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            if year in historical_data:
                st.markdown(f"€ {historical_data[year]['income'].ce04_altri_ricavi:,.0f}")
            else:
                st.markdown("—")

    # Input for forecast years
    other_revenue_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.other_revenue_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"other_rev_{year}",
                help="% da -100% a +1.000%"
            )
            other_revenue_growth_values.append(val)

    # Fixed percentage for materials - EDITABLE for ALL years (historical + forecast)
    st.markdown("---")
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**% QUOTA FISSA COSTI PER MATERIE PRIME, SUSSIDIARIE, DI CONSUMO E MERCI**")

    # Default base percentage
    base_materials_pct = float(first_assumption.fixed_materials_percentage) if first_assumption else 22.0

    # Input for HISTORICAL years (editable!)
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                max_value=100.0,
                value=base_materials_pct,
                step=1.0,
                format="%.2f",
                key=f"fix_mat_pct_hist_{year}",
                help="% di costi che non saranno influenzati dalle variazioni previsionali (calcolata come media degli anni storici)"
            )
            historical_fixed_materials_pct[year] = val

    # Input for FORECAST years
    fixed_materials_pct_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                max_value=100.0,
                value=float(existing.fixed_materials_percentage) if existing else base_materials_pct,
                step=1.0,
                format="%.2f",
                key=f"fix_mat_pct_{year}",
                help="% di costi che non saranno influenzati dalle variazioni previsionali (calcolata come media degli anni storici)"
            )
            fixed_materials_pct_values.append(val)

    # Variable materials growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % COSTI VARIABILI PER MAT. PRIME RISPETTO ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    var_materials_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.variable_materials_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"var_mat_{year}",
                help="% da -100% a +1.000%"
            )
            var_materials_growth_values.append(val)

    # Fixed materials growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % COSTI FISSI PER MAT. PRIME RISPETTO ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    fix_materials_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.fixed_materials_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"fix_mat_{year}",
                help="% da -100% a +1.000%"
            )
            fix_materials_growth_values.append(val)

    # Fixed percentage for services - EDITABLE for ALL years (historical + forecast)
    st.markdown("---")
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**% QUOTA FISSA COSTI PER SERVIZI**")

    base_services_pct = float(first_assumption.fixed_services_percentage) if first_assumption else 22.0

    # Input for HISTORICAL years (editable!)
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                max_value=100.0,
                value=base_services_pct,
                step=1.0,
                format="%.2f",
                key=f"fix_serv_pct_hist_{year}",
                help="% di costi che non saranno influenzati dalle variazioni previsionali (calcolata come media degli anni storici)"
            )
            historical_fixed_services_pct[year] = val

    # Input for FORECAST years
    fixed_services_pct_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                max_value=100.0,
                value=float(existing.fixed_services_percentage) if existing else base_services_pct,
                step=1.0,
                format="%.2f",
                key=f"fix_serv_pct_{year}",
                help="% di costi che non saranno influenzati dalle variazioni previsionali (calcolata come media degli anni storici)"
            )
            fixed_services_pct_values.append(val)

    # Variable services growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % COSTI VARIABILI PER SERVIZI RISPETTO ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    var_services_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.variable_services_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"var_serv_{year}",
                help="% da -100% a +1.000%"
            )
            var_services_growth_values.append(val)

    # Fixed services growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % COSTI FISSI PER SERVIZI RISPETTO ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    fix_services_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.fixed_services_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"fix_serv_{year}",
                help="% da -100% a +1.000%"
            )
            fix_services_growth_values.append(val)

    # Rent growth
    st.markdown("---")
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % COSTI GODIMENTO BENI DI TERZI RISPETTO ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    rent_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.rent_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"rent_{year}",
                help="% da -100% a +1.000%"
            )
            rent_growth_values.append(val)

    # Personnel growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % COSTI DEL PERSONALE RISPETTO ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    personnel_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.personnel_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"pers_{year}",
                help="% da -100% a +1.000%"
            )
            personnel_growth_values.append(val)

    # Other costs growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % ONERI DIVERSI DI GESTIONE ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    other_costs_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.other_costs_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"other_cost_{year}",
                help="% da -100% a +1.000%"
            )
            other_costs_growth_values.append(val)

    # Tax rate
    st.markdown("---")
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**% ALIQUOTA IRES/IRAP ATTESA**")

    base_tax_rate = float(first_assumption.tax_rate) if first_assumption else 27.9

    # Historical years - show base tax rate
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown(f"{base_tax_rate:.2f}%")

    # Forecast years - input
    tax_rate_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                max_value=100.0,
                value=float(existing.tax_rate) if existing else base_tax_rate,
                step=0.1,
                format="%.2f",
                key=f"tax_{year}"
            )
            tax_rate_values.append(val)

    # === BALANCE SHEET ASSUMPTIONS ===
    st.markdown("---")
    st.markdown("#### IMMOBILIZZAZIONI")

    # Immaterial investments
    st.markdown("**IMMOBILIZZAZIONI IMMATERIALI**")

    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**INVESTIMENTO**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    investments_immaterial_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                value=float(existing.investments) * 0.3 if existing and existing.investments > 0 else 0.0,
                step=1000.0,
                format="%.0f",
                key=f"inv_immat_{year}"
            )
            investments_immaterial_values.append(val)

    # Depreciation rate immaterial
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**% AMM.TO MEDIA**")

    base_depr_rate = float(first_assumption.depreciation_rate) if first_assumption else 20.0

    # Historical years - show base depreciation rate
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown(f"{base_depr_rate:.2f}%")

    # Forecast years - input
    depreciation_immaterial_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                max_value=100.0,
                value=float(existing.depreciation_rate) if existing else base_depr_rate,
                step=1.0,
                format="%.2f",
                key=f"depr_immat_{year}"
            )
            depreciation_immaterial_values.append(val)

    # Material investments
    st.markdown("---")
    st.markdown("**IMMOBILIZZAZIONI MATERIALI**")

    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**INVESTIMENTO**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    investments_material_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                value=float(existing.investments) * 0.7 if existing and existing.investments > 0 else 0.0,
                step=1000.0,
                format="%.0f",
                key=f"inv_mat_{year}"
            )
            investments_material_values.append(val)

    # Depreciation rate material
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**% AMM.TO MEDIA**")

    # Historical years - show base depreciation rate
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown(f"{base_depr_rate:.2f}%")

    # Forecast years - input
    depreciation_material_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                max_value=100.0,
                value=float(existing.depreciation_rate) if existing else base_depr_rate,
                step=1.0,
                format="%.2f",
                key=f"depr_mat_{year}"
            )
            depreciation_material_values.append(val)

    # === RECEIVABLES ===
    st.markdown("---")
    st.markdown("#### CREDITI DELL'ATTIVO CIRCOLANTE")

    # Short-term receivables growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % CREDITI ESIG. ENTRO ES. SUCC. RISPETTO ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    rec_short_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.receivables_short_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"rec_short_{year}",
                help="% da -100% a +1.000%"
            )
            rec_short_growth_values.append(val)

    # Long-term receivables growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % CREDITI ESIG. OLTRE ES. SUCC. RISPETTO ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    rec_long_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.receivables_long_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"rec_long_{year}",
                help="% da -100% a +1.000%"
            )
            rec_long_growth_values.append(val)

    # === PAYABLES ===
    st.markdown("---")
    st.markdown("#### DEBITI")
    st.markdown("**DEBITI ESIGIBILI ENTRO L'ESERCIZIO SUCCESSIVO**")

    # Short-term payables growth
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**VAR. % DEBITI ESIG. ENTRO ES. SUCC. RISPETTO ALL'ANNO BASE**")

    # Historical years - show placeholder
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown("—")

    # Forecast years - input
    pay_short_growth_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=-100.0,
                max_value=1000.0,
                value=float(existing.payables_short_growth_pct) if existing else 0.0,
                step=0.1,
                format="%.2f",
                key=f"pay_short_{year}",
                help="% da -100% a +1.000%"
            )
            pay_short_growth_values.append(val)

    # === FINANCING ===
    st.markdown("---")
    st.markdown("**DEBITI ESIGIBILI OLTRE L'ESERCIZIO SUCCESSIVO**")

    # Financing amount
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**IMPORTO FINANZIAMENTO**")

    base_financing = float(first_assumption.financing_amount) if first_assumption else 0.0

    # Historical years - show base financing
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown(f"€ {base_financing:,.0f}")

    # Forecast years - input
    financing_amount_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                value=float(existing.financing_amount) if existing else base_financing,
                step=10000.0,
                format="%.0f",
                key=f"fin_amt_{year}"
            )
            financing_amount_values.append(val)

    # Financing duration
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**DURATA MEDIA**")

    base_duration = float(first_assumption.financing_duration_years) if first_assumption else 5.0

    # Historical years - show base duration
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown(f"{base_duration:.1f} anni")

    # Forecast years - input
    financing_duration_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                max_value=30.0,
                value=float(existing.financing_duration_years) if existing else base_duration,
                step=0.5,
                format="%.1f",
                key=f"fin_dur_{year}"
            )
            financing_duration_values.append(val)

    # Financing interest rate
    cols = st.columns([3] + [1] * total_years)
    with cols[0]:
        st.markdown("**% TASSO INTERESSE PASSIVO MEDIO**")

    base_rate = float(first_assumption.financing_interest_rate) if first_assumption else 3.0

    # Historical years - show base rate
    for idx, year in enumerate(historical_years):
        with cols[idx + 1]:
            st.markdown(f"{base_rate:.2f}%")

    # Forecast years - input
    financing_rate_values = []
    for idx, year in enumerate(forecast_years):
        existing = existing_assumptions.get(year)
        with cols[len(historical_years) + idx + 1]:
            val = st.number_input(
                f"{year}",
                min_value=0.0,
                max_value=100.0,
                value=float(existing.financing_interest_rate) if existing else base_rate,
                step=0.1,
                format="%.2f",
                key=f"fin_rate_{year}"
            )
            financing_rate_values.append(val)

    # Build assumptions data
    for idx, year in enumerate(forecast_years):
        # Calculate total investment (immaterial + material)
        total_investment = investments_immaterial_values[idx] + investments_material_values[idx]

        # Use average depreciation rate from both types
        avg_depr_rate = (depreciation_immaterial_values[idx] + depreciation_material_values[idx]) / 2

        assumptions_data.append({
            'forecast_year': year,
            'revenue_growth_pct': Decimal(str(revenue_growth_values[idx])),
            'other_revenue_growth_pct': Decimal(str(other_revenue_growth_values[idx])),
            'variable_materials_growth_pct': Decimal(str(var_materials_growth_values[idx])),
            'fixed_materials_growth_pct': Decimal(str(fix_materials_growth_values[idx])),
            'variable_services_growth_pct': Decimal(str(var_services_growth_values[idx])),
            'fixed_services_growth_pct': Decimal(str(fix_services_growth_values[idx])),
            'rent_growth_pct': Decimal(str(rent_growth_values[idx])),
            'personnel_growth_pct': Decimal(str(personnel_growth_values[idx])),
            'other_costs_growth_pct': Decimal(str(other_costs_growth_values[idx])),
            'investments': Decimal(str(total_investment)),
            'receivables_short_growth_pct': Decimal(str(rec_short_growth_values[idx])),
            'receivables_long_growth_pct': Decimal(str(rec_long_growth_values[idx])),
            'payables_short_growth_pct': Decimal(str(pay_short_growth_values[idx])),
            'interest_rate_receivables': Decimal('0'),
            'interest_rate_payables': Decimal('0'),
            # Common/year-specific parameters
            'tax_rate': Decimal(str(tax_rate_values[idx])),
            'fixed_materials_percentage': Decimal(str(fixed_materials_pct_values[idx])),
            'fixed_services_percentage': Decimal(str(fixed_services_pct_values[idx])),
            'depreciation_rate': Decimal(str(avg_depr_rate)),
            'financing_amount': Decimal(str(financing_amount_values[idx])),
            'financing_duration_years': Decimal(str(financing_duration_values[idx])),
            'financing_interest_rate': Decimal(str(financing_rate_values[idx]))
        })

    # Save button
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        if st.button("💾 Salva e Calcola Previsionale", use_container_width=True, type="primary"):
            if not scenario_name:
                st.error("❌ Il nome dello scenario è obbligatorio!")
            else:
                try:
                    # Create or update scenario
                    if scenario:
                        # Update existing
                        scenario.name = scenario_name
                        scenario.base_year = base_year
                        scenario.description = description
                        scenario.is_active = 1 if is_active else 0

                        # Delete old assumptions
                        db.query(BudgetAssumptions).filter(
                            BudgetAssumptions.scenario_id == scenario.id
                        ).delete()
                    else:
                        # Create new
                        scenario = BudgetScenario(
                            company_id=company.id,
                            name=scenario_name,
                            base_year=base_year,
                            description=description,
                            is_active=1 if is_active else 0
                        )
                        db.add(scenario)

                    db.flush()

                    # Save assumptions
                    for assumption_data in assumptions_data:
                        assumption = BudgetAssumptions(
                            scenario_id=scenario.id,
                            **assumption_data
                        )
                        db.add(assumption)

                    db.commit()

                    # Generate forecast
                    with st.spinner("Calcolo del previsionale in corso..."):
                        result = generate_forecast_for_scenario(scenario.id, db)

                    st.success(f"✅ Scenario salvato e previsionale calcolato per {result['years_generated']} anni!")
                    st.balloons()

                    # Clear editing state
                    if 'editing_scenario_id' in st.session_state:
                        del st.session_state.editing_scenario_id

                    st.rerun()

                except Exception as e:
                    db.rollback()
                    st.error(f"❌ Errore: {e}")
                    import traceback
                    with st.expander("Dettagli errore"):
                        st.code(traceback.format_exc())

    with col1:
        if scenario:  # Only show cancel if editing
            if st.button("❌ Annulla", use_container_width=True):
                del st.session_state.editing_scenario_id
                st.rerun()


def show():
    """Display budget & forecast page"""
    st.title("📊 Budget & Previsionale")
    st.markdown("Crea scenari di budget e previsionali finanziari a 3 anni")

    db = st.session_state.db

    # Check if company is selected
    if not st.session_state.selected_company_id:
        st.warning("⚠️ Seleziona un'azienda in alto")
        return

    company = db.query(Company).filter(
        Company.id == st.session_state.selected_company_id
    ).first()

    # Get all scenarios for this company
    scenarios = db.query(BudgetScenario).filter(
        BudgetScenario.company_id == company.id
    ).order_by(BudgetScenario.created_at.desc()).all()

    # Check if editing a scenario
    editing_scenario_id = st.session_state.get('editing_scenario_id')

    # If editing, show edit form directly
    if editing_scenario_id:
        scenario = db.query(BudgetScenario).filter(
            BudgetScenario.id == editing_scenario_id
        ).first()

        if scenario:
            _show_scenario_form(db, company, scenario, scenarios)
        else:
            st.error("❌ Scenario non trovato!")
            del st.session_state.editing_scenario_id
            st.rerun()
        return

    # Otherwise show tabs
    tab1, tab2 = st.tabs(["📋 Scenari", "➕ Nuovo Scenario"])

    with tab1:
        if not scenarios:
            st.info("📝 Nessuno scenario presente. Crea il primo scenario nella tab 'Nuovo Scenario'")
        else:
            for scenario in scenarios:
                with st.expander(
                    f"{'✅ ' if scenario.is_active else '📦 '}{scenario.name} (Anno Base: {scenario.base_year})",
                    expanded=scenario.is_active
                ):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**Descrizione:** {scenario.description or 'N/A'}")
                        st.markdown(f"**Stato:** {'Attivo' if scenario.is_active else 'Archiviato'}")
                        st.markdown(f"**Creato:** {scenario.created_at.strftime('%d/%m/%Y')}")

                        # Show assumptions
                        assumptions = db.query(BudgetAssumptions).filter(
                            BudgetAssumptions.scenario_id == scenario.id
                        ).order_by(BudgetAssumptions.forecast_year).all()

                        if assumptions:
                            st.markdown("**Anni previsionali:**")
                            years_str = ", ".join([str(a.forecast_year) for a in assumptions])
                            st.text(years_str)

                    with col2:
                        if st.button("✏️ Modifica", key=f"edit_{scenario.id}", use_container_width=True):
                            st.session_state.editing_scenario_id = scenario.id
                            st.rerun()

                        if st.button("🔄 Ricalcola", key=f"calc_{scenario.id}", use_container_width=True):
                            try:
                                with st.spinner("Calcolo in corso..."):
                                    result = generate_forecast_for_scenario(scenario.id, db)
                                st.success(f"✅ Previsionale calcolato per {result['years_generated']} anni!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Errore: {e}")

                        if st.button("🗑️ Elimina", key=f"del_{scenario.id}", use_container_width=True):
                            db.delete(scenario)
                            db.commit()
                            st.success("✅ Scenario eliminato")
                            st.rerun()

    with tab2:
        # Show form for creating new scenario
        _show_scenario_form(db, company, scenario=None, all_scenarios=scenarios)
