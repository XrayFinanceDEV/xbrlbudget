"""
Financial Ratios (Indici Finanziari) Page
Display comprehensive financial ratio analysis
"""
import streamlit as st
import pandas as pd
from database.models import FinancialYear
from calculations.ratios import FinancialRatiosCalculator


def show():
    """Display financial ratios page"""
    st.title("📈 Indici Finanziari")
    st.markdown("Analisi completa degli indici di bilancio")

    db = st.session_state.db

    # Check if company and year are selected
    if not st.session_state.selected_company_id:
        st.warning("⚠️ Seleziona un'azienda dal menu laterale")
        return

    if not st.session_state.selected_year:
        st.warning("⚠️ Seleziona un anno fiscale dal menu laterale")
        return

    # Get financial year
    fy = db.query(FinancialYear).filter(
        FinancialYear.company_id == st.session_state.selected_company_id,
        FinancialYear.year == st.session_state.selected_year
    ).first()

    if not fy or not fy.balance_sheet or not fy.income_statement:
        st.error("❌ Dati finanziari non completi! Assicurati di aver importato SP e CE.")
        return

    bs = fy.balance_sheet
    inc = fy.income_statement

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
        st.metric(
            "CCN",
            f"€{wc.ccn:,.0f}",
            help="Capitale Circolante Netto"
        )

    with col2:
        st.metric(
            "Current Ratio",
            f"{liq.current_ratio:.2f}",
            help="Liquidità corrente"
        )

    with col3:
        st.metric(
            "ROE",
            f"{prof.roe*100:.2f}%",
            help="Return on Equity"
        )

    with col4:
        st.metric(
            "Autonomia",
            f"{solv.autonomy_index*100:.2f}%",
            help="Indice di autonomia finanziaria"
        )

    st.markdown("---")

    # Tabs for different ratio categories
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "💰 Capitale Circolante",
        "💧 Liquidità",
        "⚖️ Solvibilità",
        "💹 Redditività",
        "🔄 Rotazione"
    ])

    with tab1:
        # Working Capital
        st.subheader("Capitale Circolante e Margini")

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "CCN - Capitale Circolante Netto",
                f"€{wc.ccn:,.2f}",
                help="Attivo Circolante - Passivo Corrente"
            )
            st.metric(
                "CCLN - Capitale Circolante Lordo Netto",
                f"€{wc.ccln:,.2f}",
                help="Valore della Produzione - Costi Operativi"
            )

        with col2:
            st.metric(
                "MS - Margine di Struttura",
                f"€{wc.ms:,.2f}",
                help="Patrimonio Netto - Attivo Fisso"
            )
            st.metric(
                "MT - Margine di Tesoreria",
                f"€{wc.mt:,.2f}",
                help="Liquidità + Crediti - Debiti Brevi"
            )

        # Interpretation
        st.markdown("### 📊 Interpretazione")

        ccn_status = "✅ Positivo" if wc.ccn > 0 else "⚠️ Negativo"
        ms_status = "✅ Positivo" if wc.ms > 0 else "⚠️ Negativo"

        st.info(f"""
        **CCN {ccn_status}**: {"L'azienda ha capitale circolante sufficiente" if wc.ccn > 0 else "Possibili problemi di liquidità"}\n
        **MS {ms_status}**: {"Patrimonio copre le immobilizzazioni" if wc.ms > 0 else "Immobilizzazioni finanziate con debiti"}
        """)

    with tab2:
        # Liquidity
        st.subheader("Indici di Liquidità")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Current Ratio",
                f"{liq.current_ratio:.4f}",
                help="Attivo Corrente / Passivo Corrente"
            )
            threshold = "✅ Buono" if liq.current_ratio >= 1.5 else ("⚠️ Accettabile" if liq.current_ratio >= 1.0 else "❌ Critico")
            st.caption(f"Soglia ottimale: ≥ 1.5 ({threshold})")

        with col2:
            st.metric(
                "Quick Ratio",
                f"{liq.quick_ratio:.4f}",
                help="(Liquidità + Crediti) / Passivo Corrente"
            )
            threshold = "✅ Buono" if liq.quick_ratio >= 1.0 else ("⚠️ Accettabile" if liq.quick_ratio >= 0.8 else "❌ Critico")
            st.caption(f"Soglia ottimale: ≥ 1.0 ({threshold})")

        with col3:
            st.metric(
                "Acid Test",
                f"{liq.acid_test:.4f}",
                help="Liquidità / Passivo Corrente"
            )
            threshold = "✅ Buono" if liq.acid_test >= 0.5 else "⚠️ Basso"
            st.caption(f"Soglia ottimale: ≥ 0.5 ({threshold})")

    with tab3:
        # Solvency
        st.subheader("Indici di Solvibilità e Indebitamento")

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "Indice di Autonomia Finanziaria",
                f"{solv.autonomy_index:.4f} ({solv.autonomy_index*100:.2f}%)",
                help="Patrimonio Netto / Totale Attivo"
            )
            threshold = "✅ Ottimo" if solv.autonomy_index >= 0.40 else ("⚠️ Accettabile" if solv.autonomy_index >= 0.30 else "❌ Critico")
            st.caption(f"Soglia ottimale: ≥ 40% ({threshold})")

            st.metric(
                "Rapporto di Indebitamento",
                f"{solv.debt_ratio:.4f} ({solv.debt_ratio*100:.2f}%)",
                help="Debiti Totali / Totale Attivo"
            )

            st.metric(
                "Indice di Copertura Immobilizzazioni",
                f"{solv.fixed_asset_coverage:.4f}",
                help="Patrimonio Netto / Immobilizzazioni"
            )

        with col2:
            st.metric(
                "Debt to Equity",
                f"{solv.debt_to_equity:.4f}",
                help="Debiti Totali / Patrimonio Netto"
            )
            threshold = "✅ Basso" if solv.debt_to_equity <= 2.0 else ("⚠️ Moderato" if solv.debt_to_equity <= 3.0 else "❌ Alto")
            st.caption(f"Livello di leva: {threshold}")

            st.metric(
                "Leverage",
                f"{solv.leverage:.4f}",
                help="Totale Attivo / Patrimonio Netto"
            )

            st.metric(
                "Debiti / Produzione",
                f"{solv.debt_to_production:.4f}",
                help="Debiti Totali / Valore Produzione"
            )

    with tab4:
        # Profitability
        st.subheader("Indici di Redditività")

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "ROE - Return on Equity",
                f"{prof.roe:.4f} ({prof.roe*100:.2f}%)",
                help="Utile Netto / Patrimonio Netto"
            )
            threshold = "✅ Ottimo" if prof.roe >= 0.15 else ("⚠️ Accettabile" if prof.roe >= 0.08 else "❌ Basso")
            st.caption(f"Rendimento capitale proprio: {threshold}")

            st.metric(
                "ROI - Return on Investment",
                f"{prof.roi:.4f} ({prof.roi*100:.2f}%)",
                help="EBIT / Totale Attivo"
            )

            st.metric(
                "ROS - Return on Sales",
                f"{prof.ros:.4f} ({prof.ros*100:.2f}%)",
                help="EBIT / Ricavi"
            )

        with col2:
            st.metric(
                "ROD - Return on Debt",
                f"{prof.rod:.4f} ({prof.rod*100:.2f}%)",
                help="Oneri Finanziari / Debiti Totali"
            )

            st.metric(
                "EBITDA Margin",
                f"{prof.ebitda_margin:.4f} ({prof.ebitda_margin*100:.2f}%)",
                help="EBITDA / Ricavi"
            )

            st.metric(
                "Net Profit Margin",
                f"{prof.net_margin:.4f} ({prof.net_margin*100:.2f}%)",
                help="Utile Netto / Ricavi"
            )

    with tab5:
        # Activity/Turnover
        st.subheader("Indici di Rotazione e Efficienza")

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "Asset Turnover",
                f"{act.asset_turnover:.4f}",
                help="Ricavi / Totale Attivo"
            )
            efficiency = "✅ Alta" if act.asset_turnover >= 1.5 else ("⚠️ Media" if act.asset_turnover >= 1.0 else "❌ Bassa")
            st.caption(f"Efficienza utilizzo attivi: {efficiency}")

            st.metric(
                "Inventory Turnover",
                f"{act.inventory_turnover:.4f}",
                help="Costo Venduto / Rimanenze Medie"
            )

            st.metric(
                "Receivables Turnover",
                f"{act.receivables_turnover:.4f}",
                help="Ricavi / Crediti"
            )

        with col2:
            st.metric(
                "Giorni Magazzino",
                f"{act.inventory_turnover_days:.0f} giorni",
                help="365 / Inventory Turnover"
            )

            st.metric(
                "Giorni Crediti",
                f"{act.receivables_turnover_days:.0f} giorni",
                help="365 / Receivables Turnover"
            )

            st.metric(
                "Giorni Debiti",
                f"{act.payables_turnover_days:.0f} giorni",
                help="365 / Payables Turnover"
            )

        # Cash Conversion Cycle
        st.markdown("---")
        st.metric(
            "🔄 Ciclo di Conversione del Circolante",
            f"{act.cash_conversion_cycle:.0f} giorni",
            help="Magazzino + Crediti - Debiti (in giorni)"
        )

    # Export to Excel
    st.markdown("---")
    if st.button("📥 Esporta Indici in Excel", use_container_width=True):
        # Create export data
        ratios_data = {
            'Categoria': [
                'Capitale Circolante', 'Capitale Circolante', 'Capitale Circolante', 'Capitale Circolante',
                'Liquidità', 'Liquidità', 'Liquidità',
                'Solvibilità', 'Solvibilità', 'Solvibilità', 'Solvibilità', 'Solvibilità', 'Solvibilità',
                'Redditività', 'Redditività', 'Redditività', 'Redditività', 'Redditività', 'Redditività',
                'Rotazione', 'Rotazione', 'Rotazione', 'Rotazione', 'Rotazione', 'Rotazione', 'Rotazione'
            ],
            'Indice': [
                'CCN', 'CCLN', 'MS', 'MT',
                'Current Ratio', 'Quick Ratio', 'Acid Test',
                'Autonomia', 'Debt Ratio', 'Debt/Equity', 'Leverage', 'Copertura Immob.', 'Debiti/Produz.',
                'ROE', 'ROI', 'ROS', 'ROD', 'EBITDA Margin', 'Net Margin',
                'Asset Turnover', 'Inventory Turnover', 'Receivables Turnover',
                'Giorni Magazzino', 'Giorni Crediti', 'Giorni Debiti', 'Ciclo Conversione'
            ],
            'Valore': [
                float(wc.ccn), float(wc.ccln), float(wc.ms), float(wc.mt),
                float(liq.current_ratio), float(liq.quick_ratio), float(liq.acid_test),
                float(solv.autonomy_index), float(solv.debt_ratio), float(solv.debt_to_equity),
                float(solv.leverage), float(solv.fixed_asset_coverage), float(solv.debt_to_production),
                float(prof.roe), float(prof.roi), float(prof.ros), float(prof.rod),
                float(prof.ebitda_margin), float(prof.net_margin),
                float(act.asset_turnover), float(act.inventory_turnover), float(act.receivables_turnover),
                float(act.inventory_turnover_days), float(act.receivables_turnover_days),
                float(act.payables_turnover_days), float(act.cash_conversion_cycle)
            ]
        }

        df = pd.DataFrame(ratios_data)

        st.download_button(
            label="💾 Download Excel",
            data=df.to_csv(index=False).encode('utf-8'),
            file_name=f"indici_finanziari_{st.session_state.selected_year}.csv",
            mime="text/csv"
        )
