"""
Income Statement (Conto Economico) Page
View and edit income statement data
"""
import streamlit as st
import pandas as pd
from database.models import FinancialYear, IncomeStatement
from decimal import Decimal


def show():
    """Display income statement page"""
    st.title("💰 Conto Economico")
    st.markdown("Visualizzazione e modifica del Conto Economico (CE)")

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

    if not fy:
        st.error("❌ Anno fiscale non trovato!")
        return

    inc = fy.income_statement

    if not inc:
        st.info("📄 Nessun conto economico presente. Importa i dati o creane uno nuovo.")

        if st.button("➕ Crea Nuovo Conto Economico"):
            new_inc = IncomeStatement(financial_year_id=fy.id)
            db.add(new_inc)
            db.commit()
            st.success("✅ Conto Economico creato!")
            st.rerun()

        return

    # Summary cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Ricavi",
            f"€{inc.revenue:,.2f}",
            help="Ricavi delle vendite e prestazioni"
        )

    with col2:
        st.metric(
            "EBITDA",
            f"€{inc.ebitda:,.2f}",
            delta=f"{(inc.ebitda/inc.revenue*100):.1f}%" if inc.revenue != 0 else "0%",
            help="Margine operativo lordo"
        )

    with col3:
        st.metric(
            "EBIT",
            f"€{inc.ebit:,.2f}",
            delta=f"{(inc.ebit/inc.revenue*100):.1f}%" if inc.revenue != 0 else "0%",
            help="Risultato operativo"
        )

    with col4:
        st.metric(
            "Utile Netto",
            f"€{inc.net_profit:,.2f}",
            delta=f"{(inc.net_profit/inc.revenue*100):.1f}%" if inc.revenue != 0 else "0%",
            help="Risultato dell'esercizio"
        )

    st.markdown("---")

    # Tabs
    tab1, tab2 = st.tabs(["📋 Visualizzazione", "✏️ Modifica"])

    with tab1:
        # View mode
        st.subheader("Conto Economico Civilistico")

        # Prepare data
        income_data = [
            ("A) Valore della produzione", ""),
            ("  1. Ricavi delle vendite", inc.ce01_ricavi_vendite),
            ("  2. Variazioni rimanenze prodotti", inc.ce02_variazioni_rimanenze),
            ("  3. Incrementi immobilizzazioni", inc.ce03_lavori_interni),
            ("  4. Altri ricavi e proventi", inc.ce04_altri_ricavi),
            ("  TOTALE VALORE PRODUZIONE", inc.production_value),
            ("", ""),
            ("B) Costi della produzione", ""),
            ("  5. Materie prime e sussidiarie", inc.ce05_materie_prime),
            ("  6. Servizi", inc.ce06_servizi),
            ("  7. Godimento beni di terzi", inc.ce07_godimento_beni),
            ("  8. Costi per il personale", inc.ce08_costi_personale),
            ("  9. Ammortamenti e svalutazioni", inc.ce09_ammortamenti),
            ("  10. Variazioni rimanenze mat. prime", inc.ce10_var_rimanenze_mat_prime),
            ("  11. Accantonamenti per rischi", inc.ce11_accantonamenti),
            ("  12. Oneri diversi di gestione", inc.ce12_oneri_diversi),
            ("  TOTALE COSTI PRODUZIONE", inc.production_cost),
            ("", ""),
            ("DIFFERENZA (A-B) - EBIT", inc.ebit),
            ("", ""),
            ("C) Proventi e oneri finanziari", ""),
            ("  13. Proventi da partecipazioni", inc.ce13_proventi_partecipazioni),
            ("  14. Altri proventi finanziari", inc.ce14_altri_proventi_finanziari),
            ("  15. Interessi e oneri finanziari", inc.ce15_oneri_finanziari),
            ("  16. Utili/perdite su cambi", inc.ce16_utili_perdite_cambi),
            ("", ""),
            ("D) Rettifiche valore attività finanziarie", ""),
            ("  17. Rettifiche di valore", inc.ce17_rettifiche_attivita_fin),
            ("", ""),
            ("E) Proventi e oneri straordinari", ""),
            ("  18. Proventi straordinari", inc.ce18_proventi_straordinari),
            ("  19. Oneri straordinari", inc.ce19_oneri_straordinari),
            ("", ""),
            ("Risultato prima delle imposte", inc.profit_before_tax),
            ("  20. Imposte sul reddito", inc.ce20_imposte),
            ("", ""),
            ("UTILE (PERDITA) DELL'ESERCIZIO", inc.net_profit),
        ]

        df_income = pd.DataFrame(income_data, columns=["Voce", "Valore"])
        df_income['Valore'] = df_income['Valore'].apply(
            lambda x: f"€{x:,.2f}" if isinstance(x, Decimal) else x
        )

        st.dataframe(
            df_income,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Voce": st.column_config.TextColumn("Voce", width="large"),
                "Valore": st.column_config.TextColumn("Valore", width="medium")
            }
        )

        # Margin analysis
        st.markdown("---")
        st.subheader("📊 Analisi Margini")

        col1, col2, col3 = st.columns(3)

        with col1:
            ebitda_margin = (inc.ebitda / inc.revenue * 100) if inc.revenue != 0 else 0
            st.metric("EBITDA Margin", f"{ebitda_margin:.2f}%")

        with col2:
            ebit_margin = (inc.ebit / inc.revenue * 100) if inc.revenue != 0 else 0
            st.metric("EBIT Margin", f"{ebit_margin:.2f}%")

        with col3:
            net_margin = (inc.net_profit / inc.revenue * 100) if inc.revenue != 0 else 0
            st.metric("Net Margin", f"{net_margin:.2f}%")

    with tab2:
        # Edit mode
        st.info("✏️ Modalità modifica - Inserisci i valori manualmente")

        with st.form("edit_income_statement"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### A) VALORE PRODUZIONE")
                ce01 = st.number_input("Ricavi vendite", value=float(inc.ce01_ricavi_vendite), step=0.01, format="%.2f")
                ce02 = st.number_input("Variazioni rimanenze", value=float(inc.ce02_variazioni_rimanenze), step=0.01, format="%.2f")
                ce03 = st.number_input("Lavori interni", value=float(inc.ce03_lavori_interni), step=0.01, format="%.2f")
                ce04 = st.number_input("Altri ricavi", value=float(inc.ce04_altri_ricavi), step=0.01, format="%.2f")

                st.markdown("### B) COSTI PRODUZIONE")
                ce05 = st.number_input("Materie prime", value=float(inc.ce05_materie_prime), step=0.01, format="%.2f")
                ce06 = st.number_input("Servizi", value=float(inc.ce06_servizi), step=0.01, format="%.2f")
                ce07 = st.number_input("Godimento beni", value=float(inc.ce07_godimento_beni), step=0.01, format="%.2f")
                ce08 = st.number_input("Costi personale", value=float(inc.ce08_costi_personale), step=0.01, format="%.2f")
                ce09 = st.number_input("Ammortamenti", value=float(inc.ce09_ammortamenti), step=0.01, format="%.2f")
                ce10 = st.number_input("Var. rimanenze mat. prime", value=float(inc.ce10_var_rimanenze_mat_prime), step=0.01, format="%.2f")
                ce11 = st.number_input("Accantonamenti", value=float(inc.ce11_accantonamenti), step=0.01, format="%.2f")
                ce12 = st.number_input("Oneri diversi", value=float(inc.ce12_oneri_diversi), step=0.01, format="%.2f")

            with col2:
                st.markdown("### C) PROVENTI/ONERI FINANZIARI")
                ce13 = st.number_input("Proventi partecipazioni", value=float(inc.ce13_proventi_partecipazioni), step=0.01, format="%.2f")
                ce14 = st.number_input("Altri proventi finanziari", value=float(inc.ce14_altri_proventi_finanziari), step=0.01, format="%.2f")
                ce15 = st.number_input("Oneri finanziari", value=float(inc.ce15_oneri_finanziari), step=0.01, format="%.2f")
                ce16 = st.number_input("Utili/perdite cambi", value=float(inc.ce16_utili_perdite_cambi), step=0.01, format="%.2f")

                st.markdown("### D) RETTIFICHE ATTIVITÀ FIN.")
                ce17 = st.number_input("Rettifiche di valore", value=float(inc.ce17_rettifiche_attivita_fin), step=0.01, format="%.2f")

                st.markdown("### E) STRAORDINARI E IMPOSTE")
                ce18 = st.number_input("Proventi straordinari", value=float(inc.ce18_proventi_straordinari), step=0.01, format="%.2f")
                ce19 = st.number_input("Oneri straordinari", value=float(inc.ce19_oneri_straordinari), step=0.01, format="%.2f")
                ce20 = st.number_input("Imposte", value=float(inc.ce20_imposte), step=0.01, format="%.2f")

            submitted = st.form_submit_button("💾 Salva Modifiche", use_container_width=True)

            if submitted:
                try:
                    inc.ce01_ricavi_vendite = Decimal(str(ce01))
                    inc.ce02_variazioni_rimanenze = Decimal(str(ce02))
                    inc.ce03_lavori_interni = Decimal(str(ce03))
                    inc.ce04_altri_ricavi = Decimal(str(ce04))
                    inc.ce05_materie_prime = Decimal(str(ce05))
                    inc.ce06_servizi = Decimal(str(ce06))
                    inc.ce07_godimento_beni = Decimal(str(ce07))
                    inc.ce08_costi_personale = Decimal(str(ce08))
                    inc.ce09_ammortamenti = Decimal(str(ce09))
                    inc.ce10_var_rimanenze_mat_prime = Decimal(str(ce10))
                    inc.ce11_accantonamenti = Decimal(str(ce11))
                    inc.ce12_oneri_diversi = Decimal(str(ce12))
                    inc.ce13_proventi_partecipazioni = Decimal(str(ce13))
                    inc.ce14_altri_proventi_finanziari = Decimal(str(ce14))
                    inc.ce15_oneri_finanziari = Decimal(str(ce15))
                    inc.ce16_utili_perdite_cambi = Decimal(str(ce16))
                    inc.ce17_rettifiche_attivita_fin = Decimal(str(ce17))
                    inc.ce18_proventi_straordinari = Decimal(str(ce18))
                    inc.ce19_oneri_straordinari = Decimal(str(ce19))
                    inc.ce20_imposte = Decimal(str(ce20))

                    db.commit()
                    st.success("✅ Conto Economico aggiornato!")
                    st.rerun()

                except Exception as e:
                    db.rollback()
                    st.error(f"❌ Errore durante il salvataggio: {e}")
