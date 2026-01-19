"""
FGPMI Rating Page
Italian SME credit rating model
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from database.models import FinancialYear, Company
from calculations.rating_fgpmi import FGPMICalculator
from config import Sector


def show():
    """Display FGPMI rating page"""
    st.title("⭐ Rating FGPMI")
    st.markdown("Rating creditizio per PMI - Modello Fondo di Garanzia")

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
        st.error("❌ Dati finanziari non completi!")
        return

    bs = fy.balance_sheet
    inc = fy.income_statement

    # Calculate FGPMI Rating
    fgpmi = FGPMICalculator(bs, inc, company.sector)
    result = fgpmi.calculate()

    # Display rating header
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        # Rating badge
        rating_color = {
            1: "🟢", 2: "🟢", 3: "🟢",  # AAA, AA+, AA
            4: "🟡", 5: "🟡", 6: "🟡",  # A+, A, BBB+
            7: "🟠", 8: "🟠", 9: "🟠",  # BBB, BBB-, BB+
            10: "🔴", 11: "🔴", 12: "🔴", 13: "🔴"  # BB, BB-, B, B-
        }.get(result.rating_class, "⚪")

        st.markdown(f"## {rating_color} {result.rating_code}")
        st.markdown(f"**{result.rating_description}**")

    with col2:
        st.metric(
            "Punteggio Totale",
            f"{result.total_score}/{result.max_score}",
            delta=f"{(result.total_score/result.max_score*100):.1f}%"
        )
        st.metric("Livello Rischio", result.risk_level)

    with col3:
        st.metric("Modello Settoriale", result.sector_model.title())
        if result.revenue_bonus > 0:
            st.metric("Bonus Fatturato", f"+{result.revenue_bonus} punti")

    # Rating scale visualization
    st.markdown("---")
    st.subheader("📊 Scala di Rating")

    # Create rating scale chart
    ratings_scale = [
        ("AAA", 1, "green"),
        ("AA+/AA", 2.5, "green"),
        ("A+/A", 4.5, "yellowgreen"),
        ("BBB+/BBB/BBB-", 7, "yellow"),
        ("BB+/BB/BB-", 10, "orange"),
        ("B/B-", 12, "red")
    ]

    fig = go.Figure()

    # Add marker for current rating
    fig.add_trace(go.Scatter(
        x=[result.rating_class],
        y=[1],
        mode='markers+text',
        marker=dict(size=30, color='blue', symbol='diamond'),
        text=[result.rating_code],
        textposition='top center',
        name='Rating Attuale',
        showlegend=False
    ))

    # Add scale
    for rating_label, rating_pos, color in ratings_scale:
        fig.add_shape(
            type="rect",
            x0=rating_pos-0.5, x1=rating_pos+0.5,
            y0=0.5, y1=1.5,
            fillcolor=color,
            opacity=0.3,
            line=dict(width=1)
        )
        fig.add_annotation(
            x=rating_pos, y=0.3,
            text=rating_label,
            showarrow=False,
            font=dict(size=10)
        )

    fig.update_layout(
        height=200,
        xaxis=dict(range=[0, 14], showticklabels=False, showgrid=False),
        yaxis=dict(range=[0, 2], showticklabels=False, showgrid=False),
        margin=dict(l=20, r=20, t=20, b=40),
        plot_bgcolor='white'
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Indicators breakdown
    st.subheader("📈 Dettaglio Indicatori")

    # Sort indicators by score
    sorted_indicators = sorted(
        result.indicators.items(),
        key=lambda x: x[1].percentage,
        reverse=True
    )

    for code, ind in sorted_indicators:
        col1, col2 = st.columns([3, 1])

        with col1:
            # Progress bar
            percentage = ind.percentage
            color = "green" if percentage >= 80 else ("orange" if percentage >= 50 else "red")

            st.markdown(f"**{ind.code}** - {ind.name}")

            # Create progress bar
            progress_html = f"""
            <div style="background-color: #f0f2f6; border-radius: 10px; height: 25px; position: relative;">
                <div style="background-color: {color}; width: {percentage}%; height: 100%; border-radius: 10px;"></div>
                <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-weight: bold;">
                    {percentage:.1f}%
                </div>
            </div>
            """
            st.markdown(progress_html, unsafe_allow_html=True)

        with col2:
            st.metric(
                "Punteggio",
                f"{ind.points}/{ind.max_points}",
                help=f"Valore: {ind.value:.4f}"
            )

    # Detailed table
    st.markdown("---")
    st.subheader("📋 Tabella Riepilogativa")

    indicators_data = []
    for code, ind in result.indicators.items():
        indicators_data.append({
            'Codice': ind.code,
            'Indicatore': ind.name,
            'Valore': f"{ind.value:.4f}",
            'Punti': f"{ind.points}/{ind.max_points}",
            'Percentuale': f"{ind.percentage:.1f}%"
        })

    df = pd.DataFrame(indicators_data)
    st.dataframe(df, hide_index=True, use_container_width=True)

    # Historical trend
    st.markdown("---")
    st.subheader("📊 Trend Storico Rating")

    all_years = db.query(FinancialYear).filter(
        FinancialYear.company_id == st.session_state.selected_company_id
    ).order_by(FinancialYear.year).all()

    if len(all_years) >= 2:
        years = []
        ratings = []
        scores = []

        for year_data in all_years:
            if year_data.balance_sheet and year_data.income_statement:
                try:
                    year_bs = year_data.balance_sheet
                    year_inc = year_data.income_statement
                    year_fgpmi = FGPMICalculator(year_bs, year_inc, company.sector)
                    year_result = year_fgpmi.calculate()

                    years.append(year_data.year)
                    ratings.append(year_result.rating_class)
                    scores.append(year_result.total_score)
                except:
                    continue

        if len(years) >= 2:
            # Create dual-axis chart
            fig = go.Figure()

            # Rating class (left axis)
            fig.add_trace(go.Scatter(
                x=years,
                y=ratings,
                mode='lines+markers',
                name='Rating Class',
                yaxis='y',
                line=dict(width=3, color='blue'),
                marker=dict(size=10)
            ))

            # Score (right axis)
            fig.add_trace(go.Scatter(
                x=years,
                y=scores,
                mode='lines+markers',
                name='Score',
                yaxis='y2',
                line=dict(width=3, color='green', dash='dash'),
                marker=dict(size=8, symbol='diamond')
            ))

            fig.update_layout(
                title="Evoluzione Rating e Punteggio",
                xaxis_title="Anno",
                yaxis=dict(
                    title="Rating Class",
                    autorange="reversed"  # Lower number = better rating
                ),
                yaxis2=dict(
                    title="Punteggio Totale",
                    overlaying='y',
                    side='right'
                ),
                height=400,
                hovermode='x unified'
            )

            st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("Importa più anni per vedere il trend storico")

    # Risk analysis
    st.markdown("---")
    st.subheader("⚠️ Analisi del Rischio")

    risk_indicators = []

    for code, ind in result.indicators.items():
        if ind.percentage < 50:
            risk_indicators.append(f"- **{ind.code}** ({ind.name}): {ind.percentage:.1f}% - Richiede attenzione")

    if risk_indicators:
        st.warning("**Indicatori Critici:**\n" + "\n".join(risk_indicators))
    else:
        st.success("✅ Nessun indicatore critico rilevato")

    # Export
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📥 Esporta Report Rating", use_container_width=True):
            report = f"""
FGPMI RATING REPORT
{'='*60}

Azienda: {company.name}
Anno: {st.session_state.selected_year}
Settore: {Sector(company.sector).name}

RATING:
Classe: {result.rating_code}
Descrizione: {result.rating_description}
Rischio: {result.risk_level}
Punteggio: {result.total_score}/{result.max_score} ({result.total_score/result.max_score*100:.1f}%)

INDICATORI:
"""
            for code, ind in sorted_indicators:
                report += f"\n{ind.code} - {ind.name}:\n"
                report += f"  Valore: {ind.value:.4f}\n"
                report += f"  Punteggio: {ind.points}/{ind.max_points} ({ind.percentage:.1f}%)\n"

            st.download_button(
                "💾 Download Report",
                data=report,
                file_name=f"fgpmi_rating_{st.session_state.selected_year}.txt",
                mime="text/plain"
            )

    with col2:
        # Export Excel
        export_data = {
            'Indicatore': [ind.name for _, ind in result.indicators.items()],
            'Valore': [ind.value for _, ind in result.indicators.items()],
            'Punti': [ind.points for _, ind in result.indicators.items()],
            'Max Punti': [ind.max_points for _, ind in result.indicators.items()],
            'Percentuale': [ind.percentage for _, ind in result.indicators.items()]
        }

        df_export = pd.DataFrame(export_data)

        st.download_button(
            "📊 Esporta Excel",
            data=df_export.to_csv(index=False).encode('utf-8'),
            file_name=f"fgpmi_indicators_{st.session_state.selected_year}.csv",
            mime="text/csv",
            use_container_width=True
        )
