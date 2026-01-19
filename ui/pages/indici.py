"""
Indici - Combined Financial Analysis Page
Includes Financial Ratios, Altman Z-Score, and FGPMI Rating
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from database.models import FinancialYear, Company
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from calculations.rating_fgpmi import FGPMICalculator
from config import Sector


def show():
    """Display combined financial indices page"""
    st.title("📈 Indici Finanziari e Valutazioni")

    db = st.session_state.db

    # Check if company and year are selected
    if not st.session_state.selected_company_id:
        st.warning("⚠️ Seleziona un'azienda in alto")
        return

    if not st.session_state.selected_year:
        st.warning("⚠️ Seleziona un anno fiscale in alto")
        return

    # Get company and financial year
    company = db.query(Company).filter(Company.id == st.session_state.selected_company_id).first()

    fy = db.query(FinancialYear).filter(
        FinancialYear.company_id == st.session_state.selected_company_id,
        FinancialYear.year == st.session_state.selected_year
    ).first()

    if not fy or not fy.balance_sheet or not fy.income_statement:
        st.error("❌ Dati finanziari non completi! Assicurati di aver importato SP e CE.")
        return

    bs = fy.balance_sheet
    inc = fy.income_statement

    # Create tabs for different analyses
    tab1, tab2, tab3 = st.tabs(["📊 Indici di Bilancio", "⚖️ Altman Z-Score", "⭐ Rating FGPMI"])

    # Tab 1: Financial Ratios
    with tab1:
        st.subheader("Indici Finanziari")
        st.markdown(f"Anno: **{fy.year}** | Azienda: **{company.name}**")

        # Calculate ratios
        calc = FinancialRatiosCalculator(bs, inc)

        wc = calc.calculate_working_capital_metrics()
        liq = calc.calculate_liquidity_ratios()
        solv = calc.calculate_solvency_ratios()
        prof = calc.calculate_profitability_ratios()
        act = calc.calculate_activity_ratios()

        # Summary cards
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("CCN", f"€{wc.ccn:,.0f}", help="Capitale Circolante Netto")

        with col2:
            st.metric("Current Ratio", f"{liq.current_ratio:.2f}", help="Liquidità corrente")

        with col3:
            st.metric("ROE", f"{prof.roe*100:.2f}%", help="Return on Equity")

        with col4:
            st.metric("Autonomia", f"{solv.autonomy_index*100:.2f}%", help="Indice di autonomia finanziaria")

        st.markdown("---")

        # Detailed sections
        subtab1, subtab2, subtab3, subtab4, subtab5 = st.tabs([
            "💰 Capitale Circolante",
            "💧 Liquidità",
            "🏛️ Solvibilità",
            "📈 Redditività",
            "🔄 Rotazione"
        ])

        with subtab1:
            st.subheader("Capitale Circolante")
            col1, col2 = st.columns(2)

            with col1:
                st.metric("CCN", f"€{wc.ccn:,.0f}", help="Capitale Circolante Netto")
                st.metric("CCLN", f"€{wc.ccln:,.0f}", help="Capitale Circolante Lordo Netto")

            with col2:
                st.metric("MS", f"€{wc.ms:,.0f}", help="Margine di Struttura")
                st.metric("MT", f"€{wc.mt:,.0f}", help="Margine di Tesoreria")

        with subtab2:
            st.subheader("Indici di Liquidità")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Current Ratio", f"{liq.current_ratio:.2f}", help="Attivo Corrente / Passivo Corrente")

            with col2:
                st.metric("Quick Ratio", f"{liq.quick_ratio:.2f}", help="(AC - Rimanenze) / PC")

            with col3:
                st.metric("Acid Test", f"{liq.acid_test:.2f}", help="Liquidità / PC")

        with subtab3:
            st.subheader("Indici di Solvibilità")
            col1, col2 = st.columns(2)

            with col1:
                st.metric("Autonomia Finanziaria", f"{solv.autonomy_index*100:.2f}%",
                         help="Capitale Netto / Totale Attivo")
                st.metric("Debt/Equity", f"{solv.debt_to_equity:.2f}",
                         help="Debiti Totali / Patrimonio Netto")

            with col2:
                st.metric("Leverage", f"{solv.leverage_ratio:.2f}",
                         help="Totale Attivo / Patrimonio Netto")
                st.metric("Debt/Produzione", f"{solv.debt_to_production:.2f}",
                         help="Debiti / Valore della Produzione")

        with subtab4:
            st.subheader("Indici di Redditività")
            col1, col2 = st.columns(2)

            with col1:
                st.metric("ROE", f"{prof.roe*100:.2f}%", help="Return on Equity")
                st.metric("ROI", f"{prof.roi*100:.2f}%", help="Return on Investment")
                st.metric("ROS", f"{prof.ros*100:.2f}%", help="Return on Sales")

            with col2:
                st.metric("ROD", f"{prof.rod*100:.2f}%", help="Costo del Denaro")
                st.metric("EBITDA Margin", f"{prof.ebitda_margin*100:.2f}%")
                st.metric("EBIT Margin", f"{prof.ebit_margin*100:.2f}%")

        with subtab5:
            st.subheader("Indici di Rotazione")
            col1, col2 = st.columns(2)

            with col1:
                st.metric("Asset Turnover", f"{act.asset_turnover:.2f}",
                         help="Ricavi / Totale Attivo")
                st.metric("Giorni Magazzino", f"{act.inventory_turnover_days:.0f} gg")

            with col2:
                st.metric("Giorni Credito", f"{act.receivables_turnover_days:.0f} gg")
                st.metric("Giorni Debito", f"{act.payables_turnover_days:.0f} gg")

    # Tab 2: Altman Z-Score
    with tab2:
        st.subheader("Altman Z-Score - Valutazione Rischio Insolvenza")
        st.markdown(f"Anno: **{fy.year}** | Azienda: **{company.name}**")

        # Calculate Altman Z-Score
        altman = AltmanCalculator(bs, inc, company.sector)
        result = altman.calculate()

        # Display Z-Score with gauge
        col1, col2 = st.columns([1, 2])

        with col1:
            # Classification box
            if result.classification == "safe":
                st.success(f"### {result.interpretation_it}")
                color = "green"
            elif result.classification == "gray_zone":
                st.warning(f"### {result.interpretation_it}")
                color = "orange"
            else:
                st.error(f"### {result.interpretation_it}")
                color = "red"

            st.metric("Z-Score", f"{result.z_score:.2f}")
            st.caption(f"Modello: {result.model_type.capitalize()}")
            st.caption(f"Settore: {Sector(company.sector).name}")

        with col2:
            # Gauge chart
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=float(result.z_score),
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "Altman Z-Score"},
                gauge={
                    'axis': {'range': [None, 5]},
                    'bar': {'color': color},
                    'steps': [
                        {'range': [0, 1.23], 'color': "lightcoral"},
                        {'range': [1.23, 2.9], 'color': "lightyellow"},
                        {'range': [2.9, 5], 'color': "lightgreen"}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': 2.9
                    }
                }
            ))

            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # Components
        st.subheader("📊 Componenti Z-Score")

        components_data = [
            {"Componente": "A - Working Capital / Total Assets", "Valore": f"{result.components.A:.4f}"},
            {"Componente": "B - Retained Earnings / Total Assets", "Valore": f"{result.components.B:.4f}"},
            {"Componente": "C - EBIT / Total Assets", "Valore": f"{result.components.C:.4f}"},
            {"Componente": "D - Equity / Total Debt", "Valore": f"{result.components.D:.4f}"},
        ]

        if result.model_type == "manufacturing":
            components_data.append(
                {"Componente": "E - Revenue / Total Assets", "Valore": f"{result.components.E:.4f}"}
            )

        df_comp = pd.DataFrame(components_data)
        st.dataframe(df_comp, hide_index=True, use_container_width=True)

    # Tab 3: FGPMI Rating
    with tab3:
        st.subheader("Rating FGPMI - Fondo di Garanzia PMI")
        st.markdown(f"Anno: **{fy.year}** | Azienda: **{company.name}**")

        # Calculate FGPMI Rating
        fgpmi = FGPMICalculator(bs, inc, company.sector)
        rating_result = fgpmi.calculate()

        # Display rating
        col1, col2, col3 = st.columns([1, 1, 2])

        with col1:
            # Rating display with color
            rating_colors = {
                "AAA": "🟢", "AA+": "🟢", "AA": "🟢", "AA-": "🟢",
                "A+": "🟡", "A": "🟡", "A-": "🟡",
                "BBB+": "🟠", "BBB": "🟠", "BBB-": "🟠",
                "BB+": "🔴", "BB": "🔴", "BB-": "🔴",
                "B+": "🔴", "B": "🔴", "B-": "🔴"
            }

            rating_icon = rating_colors.get(rating_result.rating_code, "⚪")
            st.markdown(f"## {rating_icon} {rating_result.rating_code}")
            st.caption(rating_result.rating_description)

        with col2:
            st.metric("Punteggio", f"{rating_result.total_score}/{rating_result.max_score}")
            st.metric("Percentuale", f"{(rating_result.total_score/rating_result.max_score*100):.1f}%")

        with col3:
            st.info(f"**Livello di Rischio:** {rating_result.risk_level}")
            st.caption(f"Modello Settore: {rating_result.sector_model}")
            if rating_result.revenue_bonus > 0:
                st.success(f"✓ Bonus Fatturato: +{rating_result.revenue_bonus} punti")

        st.markdown("---")

        # Indicators detail
        st.subheader("📊 Dettaglio Indicatori")

        indicators_data = []
        for code, ind in rating_result.indicators.items():
            indicators_data.append({
                "Indicatore": f"{code} - {ind.name}",
                "Valore": f"{ind.value:.4f}",
                "Punti": f"{ind.points}/{ind.max_points}",
                "Percentuale": f"{ind.percentage:.1f}%"
            })

        df_ind = pd.DataFrame(indicators_data)
        st.dataframe(df_ind, hide_index=True, use_container_width=True)
