"""
Altman Z-Score Analysis Page
Bankruptcy prediction using sector-specific Altman models
"""
import streamlit as st
import plotly.graph_objects as go
from database.models import FinancialYear, Company
from calculations.altman import AltmanCalculator
from config import Sector


def show():
    """Display Altman Z-Score analysis page"""
    st.title("⚖️ Altman Z-Score")
    st.markdown("Valutazione del rischio di insolvenza")

    db = st.session_state.db

    # Check if company and year are selected
    if not st.session_state.selected_company_id:
        st.warning("⚠️ Seleziona un'azienda dal menu laterale")
        return

    if not st.session_state.selected_year:
        st.warning("⚠️ Seleziona un anno fiscale dal menu laterale")
        return

    # Get company and financial year
    company = db.query(Company).filter(Company.id == st.session_state.selected_company_id).first()

    fy = db.query(FinancialYear).filter(
        FinancialYear.company_id == st.session_state.selected_company_id,
        FinancialYear.year == st.session_state.selected_year
    ).first()

    if not fy or not fy.balance_sheet or not fy.income_statement:
        st.error("❌ Dati finanziari non completi!")
        return

    bs = fy.balance_sheet
    inc = fy.income_statement

    # Calculate Altman Z-Score
    altman = AltmanCalculator(bs, inc, company.sector)
    result = altman.calculate()

    # Display Z-Score with gauge
    col1, col2 = st.columns([1, 2])

    with col1:
        # Classification box
        if result.classification == "safe":
            st.success(f"### {result.classification_it}")
            color = "green"
        elif result.classification == "gray_zone":
            st.warning(f"### {result.classification_it}")
            color = "orange"
        else:
            st.error(f"### {result.classification_it}")
            color = "red"

        st.metric("Z-Score", f"{result.z_score:.2f}")
        st.metric("Modello", result.model_type_it)

    with col2:
        # Gauge chart
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=result.z_score,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "Altman Z-Score"},
            delta={'reference': 2.9 if result.model_type == "manufacturing" else 1.1},
            gauge={
                'axis': {'range': [None, 4.0 if result.model_type == "manufacturing" else 2.5]},
                'bar': {'color': color},
                'steps': [
                    {'range': [0, 1.23 if result.model_type == "manufacturing" else 0.65],
                     'color': "lightcoral"},
                    {'range': [1.23 if result.model_type == "manufacturing" else 0.65,
                              2.9 if result.model_type == "manufacturing" else 1.1],
                     'color': "lightyellow"},
                    {'range': [2.9 if result.model_type == "manufacturing" else 1.1,
                              4.0 if result.model_type == "manufacturing" else 2.5],
                     'color': "lightgreen"}
                ],
                'threshold': {
                    'line': {'color': "black", 'width': 4},
                    'thickness': 0.75,
                    'value': result.z_score
                }
            }
        ))

        fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Components
    st.subheader("📊 Componenti del Modello")

    components_data = []

    if result.model_type == "manufacturing":
        components_data = [
            ("A", "Working Capital / Total Assets", result.components.A, 0.717),
            ("B", "Retained Earnings / Total Assets", result.components.B, 0.847),
            ("C", "EBIT / Total Assets", result.components.C, 3.107),
            ("D", "Equity / Total Debt", result.components.D, 0.42),
            ("E", "Sales / Total Assets", result.components.E, 0.998)
        ]
    else:
        components_data = [
            ("A", "Working Capital / Total Assets", result.components.A, 6.56),
            ("B", "Retained Earnings / Total Assets", result.components.B, 3.26),
            ("C", "EBIT / Total Assets", result.components.C, 6.72),
            ("D", "Equity / Total Debt", result.components.D, 1.05),
        ]

    col_count = len(components_data)
    cols = st.columns(col_count)

    for idx, (label, description, value, weight) in enumerate(components_data):
        with cols[idx]:
            st.metric(
                f"Componente {label}",
                f"{value:.4f}",
                delta=f"× {weight}",
                help=description
            )

    # Formula display
    st.markdown("### 📐 Formula Utilizzata")

    if result.model_type == "manufacturing":
        st.latex(r"Z = 0.717A + 0.847B + 3.107C + 0.42D + 0.998E")
    else:
        st.latex(r"Z = 3.25 + 6.56A + 3.26B + 6.72C + 1.05D")

    st.markdown("---")

    # Interpretation
    st.subheader("💡 Interpretazione")

    st.info(result.interpretation_it)

    # Thresholds explanation
    with st.expander("📖 Soglie di Classificazione"):
        if result.model_type == "manufacturing":
            st.markdown("""
            **Modello Manifatturiero (5 componenti):**
            - **Z > 2.9**: Zona di Sicurezza - Basso rischio di insolvenza
            - **1.23 < Z < 2.9**: Zona Grigia - Rischio moderato, richiede monitoraggio
            - **Z < 1.23**: Zona di Rischio - Alto rischio di insolvenza entro 2 anni
            """)
        else:
            st.markdown("""
            **Modello Servizi/Non-Manifatturiero (4 componenti):**
            - **Z > 1.1**: Zona di Sicurezza - Basso rischio di insolvenza
            - **0.65 < Z < 1.1**: Zona Grigia - Rischio moderato
            - **Z < 0.65**: Zona di Rischio - Alto rischio di insolvenza
            """)

    # Historical trend if multiple years available
    st.markdown("---")
    st.subheader("📈 Trend Storico")

    all_years = db.query(FinancialYear).filter(
        FinancialYear.company_id == st.session_state.selected_company_id
    ).order_by(FinancialYear.year).all()

    if len(all_years) >= 2:
        years = []
        z_scores = []
        classifications = []

        for year_data in all_years:
            if year_data.balance_sheet and year_data.income_statement:
                try:
                    year_bs = year_data.balance_sheet
                    year_inc = year_data.income_statement
                    year_altman = AltmanCalculator(year_bs, year_inc, company.sector)
                    year_result = year_altman.calculate()

                    years.append(year_data.year)
                    z_scores.append(float(year_result.z_score))
                    classifications.append(year_result.classification)
                except:
                    continue

        if len(years) >= 2:
            # Create line chart
            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=years,
                y=z_scores,
                mode='lines+markers+text',
                name='Z-Score',
                text=[f"{z:.2f}" for z in z_scores],
                textposition='top center',
                line=dict(width=3),
                marker=dict(size=10)
            ))

            # Add threshold lines
            threshold_high = 2.9 if result.model_type == "manufacturing" else 1.1
            threshold_low = 1.23 if result.model_type == "manufacturing" else 0.65

            fig.add_hline(y=threshold_high, line_dash="dash", line_color="green",
                         annotation_text="Zona Sicurezza", annotation_position="right")
            fig.add_hline(y=threshold_low, line_dash="dash", line_color="red",
                         annotation_text="Zona Rischio", annotation_position="right")

            fig.update_layout(
                title="Evoluzione Altman Z-Score",
                xaxis_title="Anno",
                yaxis_title="Z-Score",
                height=400,
                hovermode='x'
            )

            st.plotly_chart(fig, use_container_width=True)

            # Year-over-year changes
            col1, col2, col3 = st.columns(3)

            with col1:
                if len(z_scores) >= 2:
                    last_change = z_scores[-1] - z_scores[-2]
                    st.metric(
                        "Variazione Ultimo Anno",
                        f"{z_scores[-1]:.2f}",
                        delta=f"{last_change:+.2f}"
                    )

            with col2:
                if len(z_scores) >= 1:
                    avg_z = sum(z_scores) / len(z_scores)
                    st.metric("Z-Score Medio", f"{avg_z:.2f}")

            with col3:
                improving = sum(1 for i in range(1, len(z_scores)) if z_scores[i] > z_scores[i-1])
                trend = "📈 Miglioramento" if improving > len(z_scores)//2 else "📉 Peggioramento"
                st.metric("Trend Generale", trend)

    else:
        st.info("Importa più anni per vedere il trend storico")

    # Export
    st.markdown("---")
    if st.button("📥 Esporta Report Altman", use_container_width=True):
        report = f"""
ALTMAN Z-SCORE REPORT
{'='*50}

Azienda: {company.name}
Anno: {st.session_state.selected_year}
Settore: {Sector(company.sector).name}

RISULTATO:
Z-Score: {result.z_score:.2f}
Classificazione: {result.classification_it}
Modello: {result.model_type_it}

COMPONENTI:
"""
        for label, desc, value, weight in components_data:
            report += f"\n{label} - {desc}: {value:.6f} (peso: {weight})"

        report += f"\n\nINTERPRETAZIONE:\n{result.interpretation_it}"

        st.download_button(
            "💾 Download Report",
            data=report,
            file_name=f"altman_report_{st.session_state.selected_year}.txt",
            mime="text/plain"
        )
