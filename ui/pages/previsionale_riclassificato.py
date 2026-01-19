"""
Previsionale Riclassificato - Reclassified Forecast View
Display key financial indicators with historical vs forecast comparison
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from database.models import Company, FinancialYear, BudgetScenario, ForecastYear
from decimal import Decimal


def show():
    """Display reclassified forecast page"""
    st.title("📋 Previsionale Riclassificato")
    st.markdown("Indici finanziari chiave - Storico vs Budget")

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
        st.info("📝 Nessuno scenario attivo trovato. Crea uno scenario nella sezione 'Input Ipotesi'")
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
        st.warning("⚠️ Nessun dato previsionale trovato. Calcola lo scenario nella sezione 'Input Ipotesi'.")
        return

    # Get actual historical data
    historical_years = db.query(FinancialYear).filter(
        FinancialYear.company_id == company.id,
        FinancialYear.year <= scenario.base_year
    ).order_by(FinancialYear.year.desc()).limit(3).all()
    historical_years.reverse()  # Chronological order

    st.markdown("---")

    # Collect data for analysis
    years_data = []

    # Historical data
    for hy in historical_years:
        if hy.balance_sheet and hy.income_statement:
            years_data.append({
                'year': hy.year,
                'type': 'Storico',
                'bs': hy.balance_sheet,
                'inc': hy.income_statement
            })

    # Forecast data
    for fy in forecast_years:
        if fy.balance_sheet and fy.income_statement:
            years_data.append({
                'year': fy.year,
                'type': 'Budget',
                'bs': fy.balance_sheet,
                'inc': fy.income_statement
            })

    if not years_data:
        st.warning("⚠️ Nessun dato disponibile per l'analisi")
        return

    # Calculate ratios for all years
    ratios_data = []

    for yd in years_data:
        bs = yd['bs']
        inc = yd['inc']

        # Calculate key ratios
        roe = (inc.net_profit / bs.total_equity * 100) if bs.total_equity > 0 else Decimal('0')
        roa = (inc.net_profit / bs.total_assets * 100) if bs.total_assets > 0 else Decimal('0')
        roi = (inc.ebit / bs.total_assets * 100) if bs.total_assets > 0 else Decimal('0')
        current_ratio = (bs.current_assets / bs.current_liabilities) if bs.current_liabilities > 0 else Decimal('0')
        debt_to_equity = (bs.total_debt / bs.total_equity) if bs.total_equity > 0 else Decimal('0')
        ebitda_margin = (inc.ebitda / inc.revenue * 100) if inc.revenue > 0 else Decimal('0')
        ebit_margin = (inc.ebit / inc.revenue * 100) if inc.revenue > 0 else Decimal('0')
        net_margin = (inc.net_profit / inc.revenue * 100) if inc.revenue > 0 else Decimal('0')
        asset_turnover = (inc.revenue / bs.total_assets) if bs.total_assets > 0 else Decimal('0')

        # Working capital
        ccn = bs.current_assets - bs.current_liabilities

        ratios_data.append({
            'Anno': yd['year'],
            'Tipo': yd['type'],
            'ROE (%)': float(roe),
            'ROA (%)': float(roa),
            'ROI (%)': float(roi),
            'Current Ratio': float(current_ratio),
            'Debt/Equity': float(debt_to_equity),
            'EBITDA Margin (%)': float(ebitda_margin),
            'EBIT Margin (%)': float(ebit_margin),
            'Net Margin (%)': float(net_margin),
            'Asset Turnover': float(asset_turnover),
            'CCN (€)': float(ccn),
            'Ricavi (€)': float(inc.revenue),
            'EBITDA (€)': float(inc.ebitda),
            'EBIT (€)': float(inc.ebit),
            'Utile Netto (€)': float(inc.net_profit),
            'Totale Attivo (€)': float(bs.total_assets),
            'Patrimonio Netto (€)': float(bs.total_equity),
            'Debiti (€)': float(bs.total_debt)
        })

    df_ratios = pd.DataFrame(ratios_data)
    df_ratios['Anno_Label'] = df_ratios['Anno'].astype(str) + '\n(' + df_ratios['Tipo'] + ')'

    # Summary metrics
    st.subheader("📊 Metriche Chiave")

    latest = ratios_data[-1]
    base_idx = next((i for i, r in enumerate(ratios_data) if r['Anno'] == scenario.base_year), 0)
    base = ratios_data[base_idx] if base_idx < len(ratios_data) else ratios_data[0]

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        delta_roe = latest['ROE (%)'] - base['ROE (%)']
        st.metric("ROE (Ultimo)", f"{latest['ROE (%)']:.2f}%", delta=f"{delta_roe:+.2f}%")

    with col2:
        delta_ebitda = latest['EBITDA Margin (%)'] - base['EBITDA Margin (%)']
        st.metric("EBITDA Margin", f"{latest['EBITDA Margin (%)']:.2f}%", delta=f"{delta_ebitda:+.2f}%")

    with col3:
        delta_current = latest['Current Ratio'] - base['Current Ratio']
        st.metric("Current Ratio", f"{latest['Current Ratio']:.2f}", delta=f"{delta_current:+.2f}")

    with col4:
        delta_debt = latest['Debt/Equity'] - base['Debt/Equity']
        st.metric("Debt/Equity", f"{latest['Debt/Equity']:.2f}", delta=f"{delta_debt:+.2f}")

    with col5:
        delta_ccn = latest['CCN (€)'] - base['CCN (€)']
        st.metric("CCN", f"€{latest['CCN (€)']:,.0f}", delta=f"€{delta_ccn:+,.0f}")

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Indici di Redditività",
        "🏛️ Solidità Patrimoniale",
        "💰 Margini Operativi",
        "📊 Tabella Completa"
    ])

    with tab1:
        st.subheader("Indici di Redditività")

        # ROE, ROA, ROI chart
        fig_prof = px.line(
            df_ratios,
            x='Anno_Label',
            y=['ROE (%)', 'ROA (%)', 'ROI (%)'],
            title="Trend Redditività",
            labels={'value': 'Percentuale %', 'variable': 'Indice', 'Anno_Label': 'Anno'},
            markers=True
        )

        fig_prof.update_layout(
            xaxis_title="Anno",
            yaxis_title="Percentuale %",
            legend_title="Indici",
            hovermode='x unified'
        )

        st.plotly_chart(fig_prof, use_container_width=True)

        # Profit evolution
        st.subheader("Evoluzione Risultati Economici")

        fig_results = px.bar(
            df_ratios,
            x='Anno_Label',
            y=['EBITDA (€)', 'EBIT (€)', 'Utile Netto (€)'],
            title="Margini e Utile",
            labels={'value': 'Valore (€)', 'variable': 'Voce', 'Anno_Label': 'Anno'},
            barmode='group'
        )

        fig_results.update_layout(
            xaxis_title="Anno",
            yaxis_title="Valore (€)",
            legend_title="Risultati",
            hovermode='x unified'
        )

        st.plotly_chart(fig_results, use_container_width=True)

    with tab2:
        st.subheader("Solidità Patrimoniale")

        # Current Ratio and Debt/Equity
        fig_solid = px.line(
            df_ratios,
            x='Anno_Label',
            y=['Current Ratio', 'Debt/Equity'],
            title="Indici di Solidità",
            labels={'value': 'Valore', 'variable': 'Indice', 'Anno_Label': 'Anno'},
            markers=True
        )

        fig_solid.update_layout(
            xaxis_title="Anno",
            yaxis_title="Valore",
            legend_title="Indici",
            hovermode='x unified'
        )

        st.plotly_chart(fig_solid, use_container_width=True)

        # Equity vs Debt evolution
        st.subheader("Evoluzione Patrimonio e Debiti")

        fig_equity_debt = px.bar(
            df_ratios,
            x='Anno_Label',
            y=['Patrimonio Netto (€)', 'Debiti (€)'],
            title="Patrimonio Netto vs Debiti",
            labels={'value': 'Valore (€)', 'variable': 'Componente', 'Anno_Label': 'Anno'},
            barmode='group'
        )

        fig_equity_debt.update_layout(
            xaxis_title="Anno",
            yaxis_title="Valore (€)",
            legend_title="Componenti",
            hovermode='x unified'
        )

        st.plotly_chart(fig_equity_debt, use_container_width=True)

    with tab3:
        st.subheader("Margini Operativi")

        # Margin percentages
        fig_margins = px.line(
            df_ratios,
            x='Anno_Label',
            y=['EBITDA Margin (%)', 'EBIT Margin (%)', 'Net Margin (%)'],
            title="Margini sul Fatturato",
            labels={'value': 'Margine %', 'variable': 'Tipo Margine', 'Anno_Label': 'Anno'},
            markers=True
        )

        fig_margins.update_layout(
            xaxis_title="Anno",
            yaxis_title="Margine %",
            legend_title="Margini",
            hovermode='x unified'
        )

        st.plotly_chart(fig_margins, use_container_width=True)

        # Revenue and asset turnover
        st.subheader("Fatturato e Rotazione Attivo")

        col1, col2 = st.columns(2)

        with col1:
            fig_revenue = px.bar(
                df_ratios,
                x='Anno_Label',
                y='Ricavi (€)',
                title="Evoluzione Ricavi",
                labels={'Ricavi (€)': 'Valore (€)', 'Anno_Label': 'Anno'},
                color='Tipo',
                color_discrete_map={'Storico': '#1f77b4', 'Budget': '#ff7f0e'}
            )

            st.plotly_chart(fig_revenue, use_container_width=True)

        with col2:
            fig_turnover = px.line(
                df_ratios,
                x='Anno_Label',
                y='Asset Turnover',
                title="Asset Turnover",
                labels={'Asset Turnover': 'Rotazione', 'Anno_Label': 'Anno'},
                markers=True
            )

            st.plotly_chart(fig_turnover, use_container_width=True)

    with tab4:
        st.subheader("Tabella Completa Indici")

        # Display full table
        display_cols = [
            'Anno', 'Tipo',
            'ROE (%)', 'ROA (%)', 'ROI (%)',
            'EBITDA Margin (%)', 'EBIT Margin (%)', 'Net Margin (%)',
            'Current Ratio', 'Debt/Equity', 'Asset Turnover',
            'CCN (€)'
        ]

        df_display = df_ratios[display_cols].copy()

        # Format the DataFrame
        st.dataframe(
            df_display.style.format({
                'ROE (%)': '{:.2f}',
                'ROA (%)': '{:.2f}',
                'ROI (%)': '{:.2f}',
                'EBITDA Margin (%)': '{:.2f}',
                'EBIT Margin (%)': '{:.2f}',
                'Net Margin (%)': '{:.2f}',
                'Current Ratio': '{:.2f}',
                'Debt/Equity': '{:.2f}',
                'Asset Turnover': '{:.2f}',
                'CCN (€)': '€{:,.0f}'
            }),
            hide_index=True,
            use_container_width=True
        )

        # Export option
        st.markdown("---")
        csv = df_ratios.to_csv(index=False)
        st.download_button(
            label="📥 Scarica Dati CSV",
            data=csv,
            file_name=f"previsionale_riclassificato_{company.name}_{scenario.name}.csv",
            mime="text/csv"
        )
