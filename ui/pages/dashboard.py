"""
Dashboard Page
Visual overview of financial performance and key metrics
"""
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from database.models import FinancialYear, Company
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from calculations.rating_fgpmi import FGPMICalculator
from config import Sector


def show():
    """Display dashboard page"""
    st.title("📉 Dashboard Finanziario")
    st.markdown("Panoramica completa delle performance aziendali")

    db = st.session_state.db

    # Check if company is selected
    if not st.session_state.selected_company_id:
        st.warning("⚠️ Seleziona un'azienda dal menu laterale")
        return

    company = db.query(Company).filter(Company.id == st.session_state.selected_company_id).first()

    # Get all financial years for this company
    all_years = db.query(FinancialYear).filter(
        FinancialYear.company_id == st.session_state.selected_company_id
    ).order_by(FinancialYear.year).all()

    if not all_years:
        st.info("📊 Nessun dato disponibile. Importa i bilanci per visualizzare il dashboard.")
        return

    # Filter years with complete data
    complete_years = [fy for fy in all_years if fy.balance_sheet and fy.income_statement]

    if not complete_years:
        st.error("❌ Nessun anno con dati completi (SP + CE)")
        return

    # Current year metrics (most recent)
    current_fy = complete_years[-1]
    current_bs = current_fy.balance_sheet
    current_inc = current_fy.income_statement

    # Summary KPIs
    st.subheader(f"📊 Riepilogo Anno {current_fy.year}")

    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "Ricavi",
            f"€{current_inc.revenue:,.0f}",
            help="Ricavi delle vendite"
        )

    with col2:
        st.metric(
            "EBITDA",
            f"€{current_inc.ebitda:,.0f}",
            delta=f"{(current_inc.ebitda/current_inc.revenue*100):.1f}%" if current_inc.revenue > 0 else None,
            help="Margine operativo lordo"
        )

    with col3:
        st.metric(
            "Utile Netto",
            f"€{current_inc.net_profit:,.0f}",
            delta=f"{(current_inc.net_profit/current_inc.revenue*100):.1f}%" if current_inc.revenue > 0 else None,
            help="Risultato dell'esercizio"
        )

    with col4:
        st.metric(
            "Tot. Attivo",
            f"€{current_bs.total_assets:,.0f}",
            help="Totale attività"
        )

    with col5:
        autonomy = (current_bs.total_equity / current_bs.total_assets * 100) if current_bs.total_assets > 0 else 0
        st.metric(
            "Autonomia",
            f"{autonomy:.1f}%",
            help="Patrimonio Netto / Totale Attivo"
        )

    st.markdown("---")

    # Multi-year comparison
    if len(complete_years) >= 2:
        st.subheader("📈 Andamento Pluriennale")

        # Prepare data
        years = [fy.year for fy in complete_years]
        revenues = [fy.income_statement.revenue for fy in complete_years]
        ebitdas = [fy.income_statement.ebitda for fy in complete_years]
        net_profits = [fy.income_statement.net_profit for fy in complete_years]
        total_assets = [fy.balance_sheet.total_assets for fy in complete_years]
        equities = [fy.balance_sheet.total_equity for fy in complete_years]

        # Create multi-chart layout
        tab1, tab2, tab3 = st.tabs(["💰 Economico", "📊 Patrimoniale", "📈 Indicatori"])

        with tab1:
            # Income statement trends
            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=("Ricavi", "EBITDA", "Utile Netto", "Margini %")
            )

            # Revenues
            fig.add_trace(
                go.Bar(x=years, y=[float(r) for r in revenues], name="Ricavi",
                      marker_color='lightblue'),
                row=1, col=1
            )

            # EBITDA
            fig.add_trace(
                go.Bar(x=years, y=[float(e) for e in ebitdas], name="EBITDA",
                      marker_color='lightgreen'),
                row=1, col=2
            )

            # Net Profit
            fig.add_trace(
                go.Bar(x=years, y=[float(p) for p in net_profits], name="Utile Netto",
                      marker_color='lightyellow'),
                row=2, col=1
            )

            # Margins
            ebitda_margins = [(float(e)/float(r)*100) if r > 0 else 0 for e, r in zip(ebitdas, revenues)]
            net_margins = [(float(p)/float(r)*100) if r > 0 else 0 for p, r in zip(net_profits, revenues)]

            fig.add_trace(
                go.Scatter(x=years, y=ebitda_margins, name="EBITDA %", mode='lines+markers'),
                row=2, col=2
            )
            fig.add_trace(
                go.Scatter(x=years, y=net_margins, name="Net Margin %", mode='lines+markers'),
                row=2, col=2
            )

            fig.update_layout(height=600, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            # Balance sheet trends
            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=("Totale Attivo", "Patrimonio Netto", "Composizione Attivo", "Autonomia Finanziaria")
            )

            # Total Assets
            fig.add_trace(
                go.Bar(x=years, y=[float(a) for a in total_assets], name="Tot. Attivo",
                      marker_color='lightcoral'),
                row=1, col=1
            )

            # Equity
            fig.add_trace(
                go.Bar(x=years, y=[float(e) for e in equities], name="Patrimonio Netto",
                      marker_color='lightseagreen'),
                row=1, col=2
            )

            # Asset composition (latest year)
            labels = ['Immobilizzazioni', 'Attivo Circolante', 'Ratei/Risconti']
            values = [
                float(current_bs.fixed_assets),
                float(current_bs.current_assets),
                float(current_bs.sp10_ratei_risconti_attivi)
            ]
            fig.add_trace(
                go.Pie(labels=labels, values=values, name="Attivo"),
                row=2, col=1
            )

            # Autonomy index trend
            autonomy_indices = [(float(e)/float(a)*100) if a > 0 else 0 for e, a in zip(equities, total_assets)]

            fig.add_trace(
                go.Scatter(x=years, y=autonomy_indices, name="Autonomia %",
                          mode='lines+markers', marker=dict(size=10)),
                row=2, col=2
            )

            fig.add_hline(y=40, line_dash="dash", line_color="green", row=2, col=2,
                         annotation_text="Ottimale (40%)")

            fig.update_layout(height=600, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

        with tab3:
            # Key financial indicators trends
            roes = []
            rois = []
            current_ratios = []
            debt_to_equities = []

            for fy in complete_years:
                bs = fy.balance_sheet
                inc = fy.income_statement
                calc = FinancialRatiosCalculator(bs, inc)

                prof = calc.calculate_profitability_ratios()
                liq = calc.calculate_liquidity_ratios()
                solv = calc.calculate_solvency_ratios()

                roes.append(float(prof.roe * 100))
                rois.append(float(prof.roi * 100))
                current_ratios.append(float(liq.current_ratio))
                debt_to_equities.append(float(solv.debt_to_equity))

            fig = make_subplots(
                rows=2, cols=2,
                subplot_titles=("ROE & ROI (%)", "Current Ratio", "Debt/Equity", "Z-Score Altman")
            )

            # ROE & ROI
            fig.add_trace(
                go.Scatter(x=years, y=roes, name="ROE %", mode='lines+markers'),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(x=years, y=rois, name="ROI %", mode='lines+markers'),
                row=1, col=1
            )

            # Current Ratio
            fig.add_trace(
                go.Scatter(x=years, y=current_ratios, name="Current Ratio",
                          mode='lines+markers', marker=dict(size=10)),
                row=1, col=2
            )
            fig.add_hline(y=1.5, line_dash="dash", line_color="green", row=1, col=2)

            # Debt/Equity
            fig.add_trace(
                go.Scatter(x=years, y=debt_to_equities, name="Debt/Equity",
                          mode='lines+markers', marker=dict(size=10)),
                row=2, col=1
            )
            fig.add_hline(y=2.0, line_dash="dash", line_color="orange", row=2, col=1)

            # Z-Score
            z_scores = []
            for fy in complete_years:
                try:
                    altman = AltmanCalculator(fy.balance_sheet, fy.income_statement, company.sector)
                    result = altman.calculate()
                    z_scores.append(float(result.z_score))
                except:
                    z_scores.append(0)

            fig.add_trace(
                go.Scatter(x=years, y=z_scores, name="Z-Score",
                          mode='lines+markers', marker=dict(size=10)),
                row=2, col=2
            )

            # Add Z-Score thresholds
            is_manufacturing = company.sector == Sector.INDUSTRIA.value
            threshold_safe = 2.9 if is_manufacturing else 1.1
            threshold_risk = 1.23 if is_manufacturing else 0.65

            fig.add_hline(y=threshold_safe, line_dash="dash", line_color="green", row=2, col=2)
            fig.add_hline(y=threshold_risk, line_dash="dash", line_color="red", row=2, col=2)

            fig.update_layout(height=600, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("📊 Importa almeno 2 anni per visualizzare i trend")

    # Latest ratings
    st.markdown("---")
    st.subheader("🎯 Valutazioni Attuali")

    col1, col2 = st.columns(2)

    with col1:
        # Altman Z-Score
        st.markdown("### ⚖️ Altman Z-Score")

        try:
            altman = AltmanCalculator(current_bs, current_inc, company.sector)
            altman_result = altman.calculate()

            if altman_result.classification == "safe":
                st.success(f"**{altman_result.z_score:.2f}** - {altman_result.classification_it}")
            elif altman_result.classification == "gray_zone":
                st.warning(f"**{altman_result.z_score:.2f}** - {altman_result.classification_it}")
            else:
                st.error(f"**{altman_result.z_score:.2f}** - {altman_result.classification_it}")

        except Exception as e:
            st.error(f"Errore calcolo Altman: {e}")

    with col2:
        # FGPMI Rating
        st.markdown("### ⭐ Rating FGPMI")

        try:
            fgpmi = FGPMICalculator(current_bs, current_inc, company.sector)
            fgpmi_result = fgpmi.calculate()

            rating_color_emoji = {
                1: "🟢", 2: "🟢", 3: "🟢",
                4: "🟡", 5: "🟡", 6: "🟡",
                7: "🟠", 8: "🟠", 9: "🟠",
                10: "🔴", 11: "🔴", 12: "🔴", 13: "🔴"
            }.get(fgpmi_result.rating_class, "⚪")

            if fgpmi_result.rating_class <= 3:
                st.success(f"**{rating_color_emoji} {fgpmi_result.rating_code}** - {fgpmi_result.rating_description}")
            elif fgpmi_result.rating_class <= 6:
                st.info(f"**{rating_color_emoji} {fgpmi_result.rating_code}** - {fgpmi_result.rating_description}")
            elif fgpmi_result.rating_class <= 9:
                st.warning(f"**{rating_color_emoji} {fgpmi_result.rating_code}** - {fgpmi_result.rating_description}")
            else:
                st.error(f"**{rating_color_emoji} {fgpmi_result.rating_code}** - {fgpmi_result.rating_description}")

            st.caption(f"Punteggio: {fgpmi_result.total_score}/{fgpmi_result.max_score} ({fgpmi_result.total_score/fgpmi_result.max_score*100:.1f}%)")

        except Exception as e:
            st.error(f"Errore calcolo FGPMI: {e}")
