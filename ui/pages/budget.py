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
    Show scenario creation/edit form

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

    col1, col2 = st.columns(2)

    with col1:
        scenario_name = st.text_input(
            "Nome Scenario *",
            value=scenario.name if scenario else "",
            placeholder="es. Budget 2025-2027"
        )

        base_year_options = [fy.year for fy in financial_years]
        base_year = st.selectbox(
            "Anno Base *",
            options=base_year_options,
            index=base_year_options.index(scenario.base_year) if scenario and scenario.base_year in base_year_options else 0,
            help="L'anno su cui basare le variazioni percentuali"
        )

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

    st.markdown("---")
    st.markdown("### 2️⃣ Parametri Generali Budget")
    st.info("💡 Parametri comuni per tutti gli anni di previsione")

    # Get first assumption for common parameters if editing
    first_assumption = None
    if scenario:
        assumptions_list = db.query(BudgetAssumptions).filter(
            BudgetAssumptions.scenario_id == scenario.id
        ).order_by(BudgetAssumptions.forecast_year).first()
        first_assumption = assumptions_list

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**📊 Aliquote Fiscali**")
        tax_rate = st.number_input(
            "% Aliquota IRES/IRAP",
            min_value=0.0,
            max_value=100.0,
            value=float(first_assumption.tax_rate) if first_assumption else 27.9,
            step=0.1,
            format="%.2f",
            help="Aliquota fiscale attesa (IRES 24% + IRAP 3.9% media = 27.9%)"
        )

        depreciation_rate = st.number_input(
            "% Ammortamento Medio",
            min_value=0.0,
            max_value=100.0,
            value=float(first_assumption.depreciation_rate) if first_assumption else 20.0,
            step=1.0,
            format="%.1f",
            help="Percentuale media di ammortamento sugli investimenti"
        )

    with col2:
        st.markdown("**🏭 Struttura Costi**")
        fixed_materials_pct = st.number_input(
            "% Quota Fissa Materie Prime",
            min_value=0.0,
            max_value=100.0,
            value=float(first_assumption.fixed_materials_percentage) if first_assumption else 40.0,
            step=5.0,
            format="%.1f",
            help="Percentuale dei costi materie prime che sono fissi"
        )

        fixed_services_pct = st.number_input(
            "% Quota Fissa Servizi",
            min_value=0.0,
            max_value=100.0,
            value=float(first_assumption.fixed_services_percentage) if first_assumption else 40.0,
            step=5.0,
            format="%.1f",
            help="Percentuale dei costi servizi che sono fissi"
        )

    with col3:
        st.markdown("**💳 Finanziamenti (opzionale)**")
        financing_amount = st.number_input(
            "Importo Finanziamento (€)",
            min_value=0.0,
            value=float(first_assumption.financing_amount) if first_assumption else 0.0,
            step=10000.0,
            format="%.0f",
            help="Nuovo finanziamento da ottenere"
        )

        financing_duration = st.number_input(
            "Durata Media (anni)",
            min_value=0.0,
            max_value=30.0,
            value=float(first_assumption.financing_duration_years) if first_assumption else 0.0,
            step=0.5,
            format="%.1f",
            help="Durata del finanziamento in anni"
        )

        financing_rate = st.number_input(
            "% Tasso Interesse Finanziamento",
            min_value=0.0,
            max_value=100.0,
            value=float(first_assumption.financing_interest_rate) if first_assumption else 0.0,
            step=0.1,
            format="%.2f",
            help="Tasso di interesse sul finanziamento"
        )

    st.markdown("---")
    st.markdown("### 3️⃣ Ipotesi Previsionali per Anno")
    st.info("💡 Inserisci le variazioni % rispetto all'anno base per ciascun anno di previsione")

    # Get existing assumptions if editing
    existing_assumptions = {}
    if scenario:
        for assumption in db.query(BudgetAssumptions).filter(
            BudgetAssumptions.scenario_id == scenario.id
        ).all():
            existing_assumptions[assumption.forecast_year] = assumption

    # Input assumptions for 3 years
    num_years = st.number_input(
        "Numero di anni da prevedere",
        min_value=1,
        max_value=5,
        value=len(existing_assumptions) if existing_assumptions else 3,
        help="Numero di anni futuri da prevedere (default: 3)"
    )

    assumptions_data = []

    for i in range(num_years):
        forecast_year = base_year + i + 1
        existing = existing_assumptions.get(forecast_year)

        with st.expander(f"📅 Anno {forecast_year}", expanded=(i == 0)):
            col1, col2, col3 = st.columns(3)

            with col1:
                st.markdown("**💰 Ricavi**")
                revenue_growth = st.number_input(
                    f"% Ricavi vs {base_year}",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.revenue_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"rev_{forecast_year}",
                    help=f"Anno base: €{base_inc.ce01_ricavi_vendite:,.0f}"
                )

                other_revenue_growth = st.number_input(
                    f"% Altri Ricavi vs {base_year}",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.other_revenue_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"other_rev_{forecast_year}",
                    help=f"Anno base: €{base_inc.ce04_altri_ricavi:,.0f}"
                )

            with col2:
                st.markdown("**💸 Costi**")
                var_materials = st.number_input(
                    "% Costi Var. Materiali",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.variable_materials_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"var_mat_{forecast_year}"
                )

                fix_materials = st.number_input(
                    "% Costi Fissi Materiali",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.fixed_materials_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"fix_mat_{forecast_year}"
                )

                var_services = st.number_input(
                    "% Costi Var. Servizi",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.variable_services_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"var_serv_{forecast_year}"
                )

                fix_services = st.number_input(
                    "% Costi Fissi Servizi",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.fixed_services_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"fix_serv_{forecast_year}"
                )

                rent_growth = st.number_input(
                    "% Godimento Beni Terzi",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.rent_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"rent_{forecast_year}"
                )

                personnel_growth = st.number_input(
                    "% Costi Personale",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.personnel_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"pers_{forecast_year}"
                )

                other_costs_growth = st.number_input(
                    "% Oneri Diversi",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.other_costs_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"other_cost_{forecast_year}"
                )

            with col3:
                st.markdown("**🏗️ Investimenti & WC**")
                investments = st.number_input(
                    "Investimenti (€)",
                    min_value=0.0,
                    value=float(existing.investments) if existing else 0.0,
                    step=1000.0,
                    format="%.0f",
                    key=f"inv_{forecast_year}"
                )

                rec_short = st.number_input(
                    "% Crediti Breve",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.receivables_short_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"rec_short_{forecast_year}"
                )

                rec_long = st.number_input(
                    "% Crediti Lungo",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.receivables_long_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"rec_long_{forecast_year}"
                )

                pay_short = st.number_input(
                    "% Debiti Breve",
                    min_value=-100.0,
                    max_value=1000.0,
                    value=float(existing.payables_short_growth_pct) if existing else 0.0,
                    step=0.1,
                    format="%.2f",
                    key=f"pay_short_{forecast_year}"
                )

            assumptions_data.append({
                'forecast_year': forecast_year,
                'revenue_growth_pct': Decimal(str(revenue_growth)),
                'other_revenue_growth_pct': Decimal(str(other_revenue_growth)),
                'variable_materials_growth_pct': Decimal(str(var_materials)),
                'fixed_materials_growth_pct': Decimal(str(fix_materials)),
                'variable_services_growth_pct': Decimal(str(var_services)),
                'fixed_services_growth_pct': Decimal(str(fix_services)),
                'rent_growth_pct': Decimal(str(rent_growth)),
                'personnel_growth_pct': Decimal(str(personnel_growth)),
                'other_costs_growth_pct': Decimal(str(other_costs_growth)),
                'investments': Decimal(str(investments)),
                'receivables_short_growth_pct': Decimal(str(rec_short)),
                'receivables_long_growth_pct': Decimal(str(rec_long)),
                'payables_short_growth_pct': Decimal(str(pay_short)),
                'interest_rate_receivables': Decimal('0'),
                'interest_rate_payables': Decimal('0'),
                # Common parameters (same for all years)
                'tax_rate': Decimal(str(tax_rate)),
                'fixed_materials_percentage': Decimal(str(fixed_materials_pct)),
                'fixed_services_percentage': Decimal(str(fixed_services_pct)),
                'depreciation_rate': Decimal(str(depreciation_rate)),
                'financing_amount': Decimal(str(financing_amount)),
                'financing_duration_years': Decimal(str(financing_duration)),
                'financing_interest_rate': Decimal(str(financing_rate))
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
        st.warning("⚠️ Seleziona un'azienda dal menu laterale")
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
