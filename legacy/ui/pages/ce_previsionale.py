"""
CE Previsionale - Income Statement Forecast View
Display forecasted income statements with historical comparison
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from database.models import Company, FinancialYear, BudgetScenario, ForecastYear
from decimal import Decimal


def show():
    """Display income statement forecast page"""
    st.title("💰 Conto Economico Previsionale")
    st.markdown("Confronto tra dati storici e previsionali del conto economico")

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

        # Add recalculate button
        if st.button("🔄 Ricalcola Scenario"):
            from calculations.forecast_engine import generate_forecast_for_scenario
            result = generate_forecast_for_scenario(scenario_id, db)
            if result:
                st.success("✅ Scenario ricalcolato con successo!")
                st.rerun()
            else:
                st.error("❌ Errore nel calcolo dello scenario")
        return

    # Get actual historical data
    historical_years = db.query(FinancialYear).filter(
        FinancialYear.company_id == company.id,
        FinancialYear.year <= scenario.base_year
    ).order_by(FinancialYear.year.desc()).limit(3).all()
    historical_years.reverse()  # Chronological order

    st.markdown("---")

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
        st.subheader("📊 Conto Economico - Dati Storici e Previsionali")

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
            {"Voce": "Oneri finanziari", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce15_oneri_finanziari for yd in years_data}},
            {"Voce": "Imposte", **{f"{yd['year']} ({yd['type']})": yd['inc'].ce20_imposte for yd in years_data}},
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
            use_container_width=True,
            height=600
        )

        st.markdown("---")

        # Charts
        st.subheader("📈 Trend Ricavi e Margini")

        chart_data = []
        for yd in years_data:
            chart_data.append({
                'Anno': f"{yd['year']} ({yd['type']})",
                'Ricavi': float(yd['inc'].revenue),
                'EBITDA': float(yd['inc'].ebitda),
                'EBIT': float(yd['inc'].ebit),
                'Utile Netto': float(yd['inc'].net_profit)
            })

        df_chart = pd.DataFrame(chart_data)

        # Create line chart with Plotly for better control
        fig = px.line(
            df_chart,
            x='Anno',
            y=['Ricavi', 'EBITDA', 'EBIT', 'Utile Netto'],
            title="Andamento Ricavi e Margini",
            labels={'value': 'Valore (€)', 'variable': 'Metrica'},
            markers=True
        )

        fig.update_layout(
            xaxis_title="Anno",
            yaxis_title="Valore (€)",
            legend_title="Metriche",
            hovermode='x unified'
        )

        st.plotly_chart(fig, use_container_width=True)

        # Margins percentage chart
        st.subheader("📊 Margini Percentuali")

        margin_data = []
        for yd in years_data:
            revenue = float(yd['inc'].revenue)
            if revenue > 0:
                margin_data.append({
                    'Anno': f"{yd['year']} ({yd['type']})",
                    'EBITDA Margin %': (float(yd['inc'].ebitda) / revenue * 100),
                    'EBIT Margin %': (float(yd['inc'].ebit) / revenue * 100),
                    'Net Margin %': (float(yd['inc'].net_profit) / revenue * 100)
                })

        if margin_data:
            df_margin = pd.DataFrame(margin_data)

            fig_margin = px.bar(
                df_margin,
                x='Anno',
                y=['EBITDA Margin %', 'EBIT Margin %', 'Net Margin %'],
                title="Margini Percentuali sul Fatturato",
                labels={'value': 'Margine %', 'variable': 'Tipo Margine'},
                barmode='group'
            )

            fig_margin.update_layout(
                xaxis_title="Anno",
                yaxis_title="Margine %",
                legend_title="Margini",
                hovermode='x unified'
            )

            st.plotly_chart(fig_margin, use_container_width=True)

    else:
        st.warning("⚠️ Nessun dato disponibile per la visualizzazione")
