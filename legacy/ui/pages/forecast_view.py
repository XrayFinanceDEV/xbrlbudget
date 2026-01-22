"""
Forecast View Page
Display forecasted financial statements
"""
import streamlit as st
import pandas as pd
from database.models import (
    Company, FinancialYear, BudgetScenario, ForecastYear
)
from decimal import Decimal


def show():
    """Display forecast view page"""
    st.title("🔮 Visualizza Previsionale")
    st.markdown("Visualizza bilanci previsionali e confrontali con i dati storici")

    db = st.session_state.db

    # Check if company is selected
    if not st.session_state.selected_company_id:
        st.warning("⚠️ Seleziona un'azienda in alto")
        return

    company = db.query(Company).filter(
        Company.id == st.session_state.selected_company_id
    ).first()

    # Get all active scenarios for this company
    scenarios = db.query(BudgetScenario).filter(
        BudgetScenario.company_id == company.id,
        BudgetScenario.is_active == 1
    ).order_by(BudgetScenario.created_at.desc()).all()

    if not scenarios:
        st.info("📝 Nessuno scenario attivo trovato. Crea uno scenario nella sezione 'Budget & Previsionale'")
        return

    # Scenario selection
    scenario_options = {f"{s.name} (Base: {s.base_year})": s.id for s in scenarios}
    selected_scenario_name = st.selectbox(
        "Seleziona Scenario",
        options=list(scenario_options.keys())
    )

    scenario_id = scenario_options[selected_scenario_name]
    scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first()

    # Get forecast years
    forecast_years = db.query(ForecastYear).filter(
        ForecastYear.scenario_id == scenario_id
    ).order_by(ForecastYear.year).all()

    if not forecast_years:
        st.warning("⚠️ Nessun dato previsionale trovato. Ricalcola lo scenario.")
        return

    # Get actual historical data
    historical_years = db.query(FinancialYear).filter(
        FinancialYear.company_id == company.id,
        FinancialYear.year <= scenario.base_year
    ).order_by(FinancialYear.year.desc()).limit(3).all()
    historical_years.reverse()  # Chronological order

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Conto Economico", "💼 Stato Patrimoniale", "📈 Indici"])

    with tab1:
        # Income Statement view
        st.subheader("Conto Economico - Dati Storici e Previsionali")

        # Collect data for table
        years_data = []
        headers = ["Voce"]

        # Historical data
        for hy in historical_years:
            if hy.income_statement:
                headers.append(f"{hy.year} (Storico)")
                years_data.append({
                    'year': hy.year,
                    'type': 'Storico',
                    'inc': hy.income_statement
                })

        # Forecast data
        for fy in forecast_years:
            if fy.income_statement:
                headers.append(f"{fy.year} (Budget)")
                years_data.append({
                    'year': fy.year,
                    'type': 'Budget',
                    'inc': fy.income_statement
                })

        # Build income statement table
        if years_data:
            rows = [
                {"Voce": "A) Valore della produzione", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data}},
                {"Voce": "  Ricavi vendite", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce01_ricavi_vendite for yd in years_data}},
                {"Voce": "  Altri ricavi", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce04_altri_ricavi for yd in years_data}},
                {"Voce": "  TOTALE VALORE PRODUZIONE", **{f"{yd['year']} ({yd['type']})": yd['inc'].production_value for yd in years_data}},
                {"Voce": "", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data}},
                {"Voce": "B) Costi della produzione", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data}},
                {"Voce": "  Materie prime", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce05_materie_prime for yd in years_data}},
                {"Voce": "  Servizi", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce06_servizi for yd in years_data}},
                {"Voce": "  Godimento beni terzi", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce07_godimento_beni for yd in years_data}},
                {"Voce": "  Costi personale", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce08_costi_personale for yd in years_data}},
                {"Voce": "  Ammortamenti", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce09_ammortamenti for yd in years_data}},
                {"Voce": "  Oneri diversi", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce12_oneri_diversi for yd in years_data}},
                {"Voce": "  TOTALE COSTI PRODUZIONE", **{f"{yd['year']} ({yd['type']})": yd['inc'].production_cost for yd in years_data}},
                {"Voce": "", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data}},
                {"Voce": "EBITDA", **{f"{yd['year']} ({yd['type']})": yd['inc'].ebitda for yd in years_data}},
                {"Voce": "EBIT", **{f"{yd['year']} ({yd['type']})": yd['inc'].ebit for yd in years_data}},
                {"Voce": "Risultato Netto", **{f"{yd['year']} ({yd['type']})": yd['inc'].net_profit for yd in years_data}},
            ]

            df_inc = pd.DataFrame(rows)

            # Format numeric columns
            for col in df_inc.columns:
                if col != "Voce":
                    df_inc[col] = df_inc[col].apply(
                        lambda x: f"€{x:,.0f}" if isinstance(x, Decimal) and x != "" else x
                    )

            st.dataframe(
                df_inc,
                hide_index=True,
                use_container_width=True
            )

            # Chart
            st.markdown("### 📊 Trend Ricavi e Margini")
            chart_data = []
            for yd in years_data:
                chart_data.append({
                    'Anno': f"{yd['year']}\n({yd['type']})",
                    'Ricavi': float(yd['inc'].revenue),
                    'EBITDA': float(yd['inc'].ebitda),
                    'EBIT': float(yd['inc'].ebit),
                    'Utile Netto': float(yd['inc'].net_profit)
                })

            df_chart = pd.DataFrame(chart_data)
            st.line_chart(df_chart, x='Anno', y=['Ricavi', 'EBITDA', 'EBIT', 'Utile Netto'])

    with tab2:
        # Balance Sheet view
        st.subheader("Stato Patrimoniale - Dati Storici e Previsionali")

        # Collect data for table
        years_data_bs = []

        # Historical data
        for hy in historical_years:
            if hy.balance_sheet:
                years_data_bs.append({
                    'year': hy.year,
                    'type': 'Storico',
                    'bs': hy.balance_sheet
                })

        # Forecast data
        for fy in forecast_years:
            if fy.balance_sheet:
                years_data_bs.append({
                    'year': fy.year,
                    'type': 'Budget',
                    'bs': fy.balance_sheet
                })

        # Build balance sheet table
        if years_data_bs:
            rows = [
                {"Voce": "ATTIVO", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
                {"Voce": "Immobilizzazioni", **{f"{yd['year']} ({yd['type']})": yd['bs'].fixed_assets for yd in years_data_bs}},
                {"Voce": "Attivo Corrente", **{f"{yd['year']} ({yd['type']})": yd['bs'].current_assets for yd in years_data_bs}},
                {"Voce": "  - Crediti", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp06_crediti_breve + yd['bs'].sp07_crediti_lungo for yd in years_data_bs}},
                {"Voce": "  - Liquidità", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp09_disponibilita_liquide for yd in years_data_bs}},
                {"Voce": "TOTALE ATTIVO", **{f"{yd['year']} ({yd['type']})": yd['bs'].total_assets for yd in years_data_bs}},
                {"Voce": "", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
                {"Voce": "PASSIVO", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
                {"Voce": "Patrimonio Netto", **{f"{yd['year']} ({yd['type']})": yd['bs'].total_equity for yd in years_data_bs}},
                {"Voce": "Debiti", **{f"{yd['year']} ({yd['type']})": yd['bs'].total_debt for yd in years_data_bs}},
                {"Voce": "  - Debiti Breve", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp16_debiti_breve for yd in years_data_bs}},
                {"Voce": "  - Debiti Lungo", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp17_debiti_lungo for yd in years_data_bs}},
                {"Voce": "TOTALE PASSIVO", **{f"{yd['year']} ({yd['type']})": yd['bs'].total_liabilities for yd in years_data_bs}},
            ]

            df_bs = pd.DataFrame(rows)

            # Format numeric columns
            for col in df_bs.columns:
                if col != "Voce":
                    df_bs[col] = df_bs[col].apply(
                        lambda x: f"€{x:,.0f}" if isinstance(x, Decimal) and x != "" else x
                    )

            st.dataframe(
                df_bs,
                hide_index=True,
                use_container_width=True
            )

            # Chart
            st.markdown("### 📊 Trend Patrimoniale")
            chart_data = []
            for yd in years_data_bs:
                chart_data.append({
                    'Anno': f"{yd['year']}\n({yd['type']})",
                    'Totale Attivo': float(yd['bs'].total_assets),
                    'Patrimonio Netto': float(yd['bs'].total_equity),
                    'Debiti Totali': float(yd['bs'].total_debt)
                })

            df_chart_bs = pd.DataFrame(chart_data)
            st.bar_chart(df_chart_bs, x='Anno', y=['Totale Attivo', 'Patrimonio Netto', 'Debiti Totali'])

    with tab3:
        # Financial Ratios view
        st.subheader("Indici Finanziari - Storico vs Budget")

        # Calculate ratios for all years
        ratios_data = []

        for yd in years_data_bs:
            bs = yd['bs']
            # Find corresponding income statement
            inc = next((y['inc'] for y in years_data if y['year'] == yd['year']), None)

            if inc and bs:
                # Calculate key ratios
                roe = (inc.net_profit / bs.total_equity * 100) if bs.total_equity > 0 else Decimal('0')
                roa = (inc.net_profit / bs.total_assets * 100) if bs.total_assets > 0 else Decimal('0')
                current_ratio = (bs.current_assets / bs.current_liabilities) if bs.current_liabilities > 0 else Decimal('0')
                debt_to_equity = (bs.total_debt / bs.total_equity) if bs.total_equity > 0 else Decimal('0')
                ebitda_margin = (inc.ebitda / inc.revenue * 100) if inc.revenue > 0 else Decimal('0')

                ratios_data.append({
                    'Anno': f"{yd['year']} ({yd['type']})",
                    'ROE (%)': float(roe),
                    'ROA (%)': float(roa),
                    'Current Ratio': float(current_ratio),
                    'Debt/Equity': float(debt_to_equity),
                    'EBITDA Margin (%)': float(ebitda_margin)
                })

        if ratios_data:
            df_ratios = pd.DataFrame(ratios_data)

            # Display as metrics
            col1, col2, col3, col4, col5 = st.columns(5)

            latest = ratios_data[-1]

            with col1:
                st.metric("ROE", f"{latest['ROE (%)']:.2f}%")
            with col2:
                st.metric("ROA", f"{latest['ROA (%)']:.2f}%")
            with col3:
                st.metric("Current Ratio", f"{latest['Current Ratio']:.2f}")
            with col4:
                st.metric("Debt/Equity", f"{latest['Debt/Equity']:.2f}")
            with col5:
                st.metric("EBITDA Margin", f"{latest['EBITDA Margin (%)']:.2f}%")

            st.markdown("---")

            # Full table
            st.dataframe(
                df_ratios.style.format({
                    'ROE (%)': '{:.2f}',
                    'ROA (%)': '{:.2f}',
                    'Current Ratio': '{:.2f}',
                    'Debt/Equity': '{:.2f}',
                    'EBITDA Margin (%)': '{:.2f}'
                }),
                hide_index=True,
                use_container_width=True
            )

            # Charts
            st.markdown("### 📈 Trend Indici")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**Redditività**")
                st.line_chart(df_ratios, x='Anno', y=['ROE (%)', 'ROA (%)'])

            with col2:
                st.markdown("**Struttura Patrimoniale**")
                st.line_chart(df_ratios, x='Anno', y=['Current Ratio', 'Debt/Equity'])
