"""
Rendiconto Finanziario - Cash Flow Statement
Display cash flow analysis and related financial indicators
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from database.models import Company, FinancialYear, BudgetScenario, ForecastYear
from decimal import Decimal


def calculate_cash_flow(bs_current, bs_previous, inc_current):
    """
    Calculate cash flow statement using indirect method

    Args:
        bs_current: Current year balance sheet
        bs_previous: Previous year balance sheet
        inc_current: Current year income statement

    Returns:
        dict with cash flow components
    """
    # Operating activities
    operating_cf = inc_current.net_profit
    operating_cf += inc_current.ce09_ammortamenti  # Add back depreciation

    # Changes in working capital
    if bs_previous:
        delta_receivables = bs_current.sp06_crediti_breve - bs_previous.sp06_crediti_breve
        delta_inventory = bs_current.sp05_rimanenze - bs_previous.sp05_rimanenze
        delta_payables = bs_current.sp16_debiti_breve - bs_previous.sp16_debiti_breve

        operating_cf -= delta_receivables  # Increase in receivables reduces cash
        operating_cf -= delta_inventory    # Increase in inventory reduces cash
        operating_cf += delta_payables      # Increase in payables increases cash
    else:
        delta_receivables = Decimal('0')
        delta_inventory = Decimal('0')
        delta_payables = Decimal('0')

    # Investing activities (simplified)
    if bs_previous:
        capex = bs_current.fixed_assets - bs_previous.fixed_assets + inc_current.ce09_ammortamenti
    else:
        capex = inc_current.ce09_ammortamenti

    investing_cf = -capex  # Negative because it's an outflow

    # Financing activities
    if bs_previous:
        delta_debt = bs_current.total_debt - bs_previous.total_debt
        delta_equity = (bs_current.sp11_capitale + bs_current.sp12_riserve) - \
                      (bs_previous.sp11_capitale + bs_previous.sp12_riserve)
    else:
        delta_debt = Decimal('0')
        delta_equity = Decimal('0')

    financing_cf = delta_debt + delta_equity - inc_current.net_profit  # Exclude profit (already in operating)

    # Total cash flow
    total_cf = operating_cf + investing_cf + financing_cf

    # Verify with actual cash change
    if bs_previous:
        actual_cash_change = bs_current.sp09_disponibilita_liquide - bs_previous.sp09_disponibilita_liquide
    else:
        actual_cash_change = Decimal('0')

    return {
        'operating_cf': operating_cf,
        'investing_cf': investing_cf,
        'financing_cf': financing_cf,
        'total_cf': total_cf,
        'actual_cash_change': actual_cash_change,
        'delta_receivables': delta_receivables,
        'delta_inventory': delta_inventory,
        'delta_payables': delta_payables,
        'capex': capex,
        'delta_debt': delta_debt,
        'delta_equity': delta_equity
    }


def show():
    """Display cash flow statement page"""
    st.title("💵 Rendiconto Finanziario")
    st.markdown("Analisi dei flussi di cassa e indici di liquidità")

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
        st.info("📝 Analisi solo su dati storici (nessuno scenario budget attivo)")
        scenario = None
    else:
        # Scenario selection
        scenario_options = {f"{s.name} (Base: {s.base_year})": s.id for s in scenarios}
        scenario_options["Solo Dati Storici"] = None

        selected_scenario_name = st.selectbox(
            "Seleziona Vista",
            options=list(scenario_options.keys())
        )

        scenario_id = scenario_options[selected_scenario_name]
        scenario = db.query(BudgetScenario).filter(BudgetScenario.id == scenario_id).first() if scenario_id else None

    st.markdown("---")

    # Get data
    all_years_data = []

    # Historical data
    historical_years = db.query(FinancialYear).filter(
        FinancialYear.company_id == company.id
    ).order_by(FinancialYear.year).all()

    for hy in historical_years:
        if hy.balance_sheet and hy.income_statement:
            all_years_data.append({
                'year': hy.year,
                'type': 'Storico',
                'bs': hy.balance_sheet,
                'inc': hy.income_statement
            })

    # Forecast data (if scenario selected)
    if scenario:
        forecast_years = db.query(ForecastYear).filter(
            ForecastYear.scenario_id == scenario.id
        ).order_by(ForecastYear.year).all()

        for fy in forecast_years:
            if fy.balance_sheet and fy.income_statement:
                all_years_data.append({
                    'year': fy.year,
                    'type': 'Budget',
                    'bs': fy.balance_sheet,
                    'inc': fy.income_statement
                })

    if len(all_years_data) < 2:
        st.warning("⚠️ Sono necessari almeno 2 anni di dati per calcolare il rendiconto finanziario")
        return

    # Calculate cash flows
    cash_flows = []

    for i in range(1, len(all_years_data)):
        current = all_years_data[i]
        previous = all_years_data[i-1]

        cf = calculate_cash_flow(current['bs'], previous['bs'], current['inc'])

        cash_flows.append({
            'Anno': current['year'],
            'Tipo': current['type'],
            'Flusso Operativo': float(cf['operating_cf']),
            'Flusso Investimenti': float(cf['investing_cf']),
            'Flusso Finanziario': float(cf['financing_cf']),
            'Flusso Totale': float(cf['total_cf']),
            'Variazione Cassa Effettiva': float(cf['actual_cash_change']),
            'CAPEX': float(cf['capex']),
            'Δ Crediti': float(cf['delta_receivables']),
            'Δ Rimanenze': float(cf['delta_inventory']),
            'Δ Debiti': float(cf['delta_payables']),
            'Utile Netto': float(current['inc'].net_profit),
            'EBITDA': float(current['inc'].ebitda),
            'Cassa Finale': float(current['bs'].sp09_disponibilita_liquide)
        })

    df_cf = pd.DataFrame(cash_flows)
    df_cf['Anno_Label'] = df_cf['Anno'].astype(str) + '\n(' + df_cf['Tipo'] + ')'

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs([
        "💰 Rendiconto Finanziario",
        "📊 Indici di Liquidità",
        "📈 Analisi Flussi"
    ])

    with tab1:
        st.subheader("Rendiconto Finanziario (Metodo Indiretto)")

        # Summary metrics for latest year
        latest_cf = cash_flows[-1]

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Flusso Operativo", f"€{latest_cf['Flusso Operativo']:,.0f}")

        with col2:
            st.metric("Flusso Investimenti", f"€{latest_cf['Flusso Investimenti']:,.0f}")

        with col3:
            st.metric("Flusso Finanziario", f"€{latest_cf['Flusso Finanziario']:,.0f}")

        with col4:
            st.metric("Flusso Totale", f"€{latest_cf['Flusso Totale']:,.0f}")

        st.markdown("---")

        # Detailed table
        st.subheader("📋 Dettaglio Rendiconto")

        # Build detailed cash flow table
        for i, row in df_cf.iterrows():
            with st.expander(f"📅 Anno {row['Anno']} ({row['Tipo']})"):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("**A) Flusso da Attività Operative:**")
                    st.text(f"Utile Netto:           €{row['Utile Netto']:>15,.0f}")
                    st.text(f"+ Ammortamenti:        €{(row['EBITDA'] - row['Utile Netto']):>15,.0f}")
                    st.text(f"- Δ Crediti:          €{-row['Δ Crediti']:>15,.0f}")
                    st.text(f"- Δ Rimanenze:        €{-row['Δ Rimanenze']:>15,.0f}")
                    st.text(f"+ Δ Debiti:           €{row['Δ Debiti']:>15,.0f}")
                    st.markdown(f"**Flusso Operativo:    €{row['Flusso Operativo']:>15,.0f}**")

                with col2:
                    st.markdown("**B) Flusso da Attività di Investimento:**")
                    st.text(f"- CAPEX:              €{-row['CAPEX']:>15,.0f}")
                    st.markdown(f"**Flusso Investimenti: €{row['Flusso Investimenti']:>15,.0f}**")

                    st.markdown("**C) Flusso da Attività Finanziarie:**")
                    st.markdown(f"**Flusso Finanziario:  €{row['Flusso Finanziario']:>15,.0f}**")

                    st.markdown("---")
                    st.markdown(f"**FLUSSO TOTALE:       €{row['Flusso Totale']:>15,.0f}**")
                    st.markdown(f"Cassa Finale:          €{row['Cassa Finale']:>15,.0f}")

        st.markdown("---")

        # Chart: Cash flow components
        fig_cf = px.bar(
            df_cf,
            x='Anno_Label',
            y=['Flusso Operativo', 'Flusso Investimenti', 'Flusso Finanziario'],
            title="Componenti del Flusso di Cassa",
            labels={'value': 'Valore (€)', 'variable': 'Componente', 'Anno_Label': 'Anno'},
            barmode='group'
        )

        fig_cf.update_layout(
            xaxis_title="Anno",
            yaxis_title="Flusso (€)",
            legend_title="Componenti",
            hovermode='x unified'
        )

        st.plotly_chart(fig_cf, use_container_width=True)

    with tab2:
        st.subheader("Indici di Liquidità del Rendiconto Finanziario")

        # Calculate CF ratios
        cf_ratios = []

        for i, row in df_cf.iterrows():
            # Operating Cash Flow Margin
            ocf_margin = (row['Flusso Operativo'] / row['EBITDA'] * 100) if row['EBITDA'] != 0 else 0

            # Cash Flow to Debt (would need debt data)
            # Free Cash Flow
            free_cf = row['Flusso Operativo'] + row['Flusso Investimenti']

            # Cash Conversion
            cash_conversion = (row['Flusso Operativo'] / row['Utile Netto'] * 100) if row['Utile Netto'] != 0 else 0

            cf_ratios.append({
                'Anno': row['Anno'],
                'Tipo': row['Tipo'],
                'OCF Margin (%)': ocf_margin,
                'Free Cash Flow': free_cf,
                'Cash Conversion (%)': cash_conversion
            })

        df_cf_ratios = pd.DataFrame(cf_ratios)
        df_cf_ratios['Anno_Label'] = df_cf_ratios['Anno'].astype(str) + '\n(' + df_cf_ratios['Tipo'] + ')'

        # Display metrics
        col1, col2, col3 = st.columns(3)

        latest_ratio = cf_ratios[-1]

        with col1:
            st.metric("OCF Margin", f"{latest_ratio['OCF Margin (%)']:.1f}%",
                     help="Operating Cash Flow / EBITDA")

        with col2:
            st.metric("Free Cash Flow", f"€{latest_ratio['Free Cash Flow']:,.0f}",
                     help="Flusso Operativo + Flusso Investimenti")

        with col3:
            st.metric("Cash Conversion", f"{latest_ratio['Cash Conversion (%)']:.1f}%",
                     help="Operating Cash Flow / Utile Netto")

        st.markdown("---")

        # Charts
        fig_fcf = px.line(
            df_cf,
            x='Anno_Label',
            y='Flusso Operativo',
            title="Andamento Flusso di Cassa Operativo",
            labels={'Flusso Operativo': 'Valore (€)', 'Anno_Label': 'Anno'},
            markers=True
        )

        st.plotly_chart(fig_fcf, use_container_width=True)

        # Table
        st.dataframe(
            df_cf_ratios[['Anno', 'Tipo', 'OCF Margin (%)', 'Free Cash Flow', 'Cash Conversion (%)']].style.format({
                'OCF Margin (%)': '{:.2f}',
                'Free Cash Flow': '€{:,.0f}',
                'Cash Conversion (%)': '{:.2f}'
            }),
            hide_index=True,
            use_container_width=True
        )

    with tab3:
        st.subheader("Analisi Dettagliata Flussi")

        # Operating CF vs Net Profit
        fig_compare = px.bar(
            df_cf,
            x='Anno_Label',
            y=['Utile Netto', 'Flusso Operativo'],
            title="Utile Netto vs Flusso di Cassa Operativo",
            labels={'value': 'Valore (€)', 'variable': 'Metrica', 'Anno_Label': 'Anno'},
            barmode='group'
        )

        st.plotly_chart(fig_compare, use_container_width=True)

        # CAPEX trend
        st.subheader("📉 Investimenti (CAPEX)")

        fig_capex = px.bar(
            df_cf,
            x='Anno_Label',
            y='CAPEX',
            title="Trend Investimenti in Capitale Fisso",
            labels={'CAPEX': 'CAPEX (€)', 'Anno_Label': 'Anno'},
            color='Tipo',
            color_discrete_map={'Storico': '#1f77b4', 'Budget': '#ff7f0e'}
        )

        st.plotly_chart(fig_capex, use_container_width=True)

        # Working capital changes
        st.subheader("🔄 Variazioni Capitale Circolante")

        fig_wc = px.bar(
            df_cf,
            x='Anno_Label',
            y=['Δ Crediti', 'Δ Rimanenze', 'Δ Debiti'],
            title="Variazioni Capitale Circolante",
            labels={'value': 'Variazione (€)', 'variable': 'Componente', 'Anno_Label': 'Anno'},
            barmode='group'
        )

        st.plotly_chart(fig_wc, use_container_width=True)

        # Full data table
        st.subheader("📊 Tabella Completa")

        st.dataframe(
            df_cf.style.format({
                'Flusso Operativo': '€{:,.0f}',
                'Flusso Investimenti': '€{:,.0f}',
                'Flusso Finanziario': '€{:,.0f}',
                'Flusso Totale': '€{:,.0f}',
                'Variazione Cassa Effettiva': '€{:,.0f}',
                'CAPEX': '€{:,.0f}',
                'Δ Crediti': '€{:,.0f}',
                'Δ Rimanenze': '€{:,.0f}',
                'Δ Debiti': '€{:,.0f}',
                'Utile Netto': '€{:,.0f}',
                'EBITDA': '€{:,.0f}',
                'Cassa Finale': '€{:,.0f}'
            }),
            hide_index=True,
            use_container_width=True
        )

        # Export
        st.markdown("---")
        csv = df_cf.to_csv(index=False)
        st.download_button(
            label="📥 Scarica Dati CSV",
            data=csv,
            file_name=f"rendiconto_finanziario_{company.name}.csv",
            mime="text/csv"
        )
