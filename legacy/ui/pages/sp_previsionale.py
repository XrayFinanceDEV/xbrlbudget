"""
SP Previsionale - Balance Sheet Forecast View
Display forecasted balance sheets with historical comparison
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from database.models import Company, FinancialYear, BudgetScenario, ForecastYear
from decimal import Decimal


def show():
    """Display balance sheet forecast page"""
    st.title("📊 Stato Patrimoniale Previsionale")
    st.markdown("Confronto tra dati storici e previsionali dello stato patrimoniale")

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
        st.subheader("📊 Stato Patrimoniale - Dati Storici e Previsionali")

        rows = [
            {"Voce": "ATTIVO", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "B) Immobilizzazioni", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "  Immateriali", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp02_immob_immateriali for yd in years_data_bs}},
            {"Voce": "  Materiali", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp03_immob_materiali for yd in years_data_bs}},
            {"Voce": "  Finanziarie", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp04_immob_finanziarie for yd in years_data_bs}},
            {"Voce": "  TOTALE IMMOBILIZZAZIONI", **{f"{yd['year']} ({yd['type']})": yd['bs'].fixed_assets for yd in years_data_bs}},
            {"Voce": "", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "C) Attivo Corrente", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "  Rimanenze", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp05_rimanenze for yd in years_data_bs}},
            {"Voce": "  Crediti breve", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp06_crediti_breve for yd in years_data_bs}},
            {"Voce": "  Crediti lungo", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp07_crediti_lungo for yd in years_data_bs}},
            {"Voce": "  Liquidità", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp09_disponibilita_liquide for yd in years_data_bs}},
            {"Voce": "  TOTALE ATTIVO CORRENTE", **{f"{yd['year']} ({yd['type']})": yd['bs'].current_assets for yd in years_data_bs}},
            {"Voce": "", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "TOTALE ATTIVO", **{f"{yd['year']} ({yd['type']})": yd['bs'].total_assets for yd in years_data_bs}},
            {"Voce": "", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "PASSIVO E PATRIMONIO NETTO", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "A) Patrimonio Netto", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "  Capitale", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp11_capitale for yd in years_data_bs}},
            {"Voce": "  Riserve", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp12_riserve for yd in years_data_bs}},
            {"Voce": "  Utile/Perdita", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp13_utile_perdita for yd in years_data_bs}},
            {"Voce": "  TOTALE PATRIMONIO NETTO", **{f"{yd['year']} ({yd['type']})": yd['bs'].total_equity for yd in years_data_bs}},
            {"Voce": "", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "B-D) Debiti e Fondi", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
            {"Voce": "  Debiti breve termine", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp16_debiti_breve for yd in years_data_bs}},
            {"Voce": "  Debiti lungo termine", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp17_debiti_lungo for yd in years_data_bs}},
            {"Voce": "  TFR", **{f"{yd['year']} ({yd['type']})": yd['bs'].sp15_tfr for yd in years_data_bs}},
            {"Voce": "  TOTALE DEBITI", **{f"{yd['year']} ({yd['type']})": yd['bs'].total_debt + yd['bs'].sp15_tfr for yd in years_data_bs}},
            {"Voce": "", **{f"{yd['year']} ({yd['type']})": "" for yd in years_data_bs}},
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
            use_container_width=True,
            height=700
        )

        st.markdown("---")

        # Charts
        st.subheader("📈 Trend Patrimoniale")

        chart_data = []
        for yd in years_data_bs:
            chart_data.append({
                'Anno': f"{yd['year']} ({yd['type']})",
                'Totale Attivo': float(yd['bs'].total_assets),
                'Immobilizzazioni': float(yd['bs'].fixed_assets),
                'Attivo Corrente': float(yd['bs'].current_assets)
            })

        df_chart_bs = pd.DataFrame(chart_data)

        fig_assets = px.bar(
            df_chart_bs,
            x='Anno',
            y=['Immobilizzazioni', 'Attivo Corrente'],
            title="Composizione Attivo",
            labels={'value': 'Valore (€)', 'variable': 'Componente'},
            barmode='stack'
        )

        fig_assets.update_layout(
            xaxis_title="Anno",
            yaxis_title="Valore (€)",
            legend_title="Attivo",
            hovermode='x unified'
        )

        st.plotly_chart(fig_assets, use_container_width=True)

        # Equity vs Debt chart
        st.subheader("📊 Struttura Patrimoniale")

        equity_debt_data = []
        for yd in years_data_bs:
            equity_debt_data.append({
                'Anno': f"{yd['year']} ({yd['type']})",
                'Patrimonio Netto': float(yd['bs'].total_equity),
                'Debiti Totali': float(yd['bs'].total_debt)
            })

        df_equity_debt = pd.DataFrame(equity_debt_data)

        fig_equity = px.bar(
            df_equity_debt,
            x='Anno',
            y=['Patrimonio Netto', 'Debiti Totali'],
            title="Patrimonio Netto vs Debiti",
            labels={'value': 'Valore (€)', 'variable': 'Componente'},
            barmode='group'
        )

        fig_equity.update_layout(
            xaxis_title="Anno",
            yaxis_title="Valore (€)",
            legend_title="Componenti",
            hovermode='x unified'
        )

        st.plotly_chart(fig_equity, use_container_width=True)

        # Liquidity chart
        st.subheader("💰 Liquidità")

        liquidity_data = []
        for yd in years_data_bs:
            liquidity_data.append({
                'Anno': f"{yd['year']} ({yd['type']})",
                'Liquidità': float(yd['bs'].sp09_disponibilita_liquide),
                'Crediti': float(yd['bs'].sp06_crediti_breve + yd['bs'].sp07_crediti_lungo)
            })

        df_liquidity = pd.DataFrame(liquidity_data)

        fig_liq = px.line(
            df_liquidity,
            x='Anno',
            y=['Liquidità', 'Crediti'],
            title="Andamento Liquidità e Crediti",
            labels={'value': 'Valore (€)', 'variable': 'Componente'},
            markers=True
        )

        fig_liq.update_layout(
            xaxis_title="Anno",
            yaxis_title="Valore (€)",
            legend_title="Componenti",
            hovermode='x unified'
        )

        st.plotly_chart(fig_liq, use_container_width=True)

    else:
        st.warning("⚠️ Nessun dato disponibile per la visualizzazione")
