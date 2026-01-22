"""
Balance Sheet (Stato Patrimoniale) Page
View and edit balance sheet data
"""
import streamlit as st
import pandas as pd
from database.models import FinancialYear, BalanceSheet
from decimal import Decimal


def show():
    """Display balance sheet page"""
    st.title("📊 Stato Patrimoniale")
    st.markdown("Visualizzazione e modifica dello Stato Patrimoniale (SP)")

    db = st.session_state.db

    # Check if company and year are selected
    if not st.session_state.selected_company_id:
        st.warning("⚠️ Seleziona un'azienda in alto")
        return

    if not st.session_state.selected_year:
        st.warning("⚠️ Seleziona un anno fiscale in alto")
        return

    # Get financial year
    fy = db.query(FinancialYear).filter(
        FinancialYear.company_id == st.session_state.selected_company_id,
        FinancialYear.year == st.session_state.selected_year
    ).first()

    if not fy:
        st.error("❌ Anno fiscale non trovato!")
        return

    bs = fy.balance_sheet

    if not bs:
        st.info("📄 Nessun bilancio presente per questo anno. Importa i dati o creane uno nuovo.")

        if st.button("➕ Crea Nuovo Stato Patrimoniale"):
            new_bs = BalanceSheet(financial_year_id=fy.id)
            db.add(new_bs)
            db.commit()
            st.success("✅ Stato Patrimoniale creato!")
            st.rerun()

        return

    # Summary cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Totale Attivo",
            f"€{bs.total_assets:,.2f}",
            help="Somma di tutte le attività"
        )

    with col2:
        st.metric(
            "Patrimonio Netto",
            f"€{bs.total_equity:,.2f}",
            help="Capitale proprio dell'azienda"
        )

    with col3:
        st.metric(
            "Totale Passivo",
            f"€{bs.total_liabilities:,.2f}",
            help="Debiti e obbligazioni"
        )

    with col4:
        balanced = bs.is_balanced()
        st.metric(
            "Bilanciato",
            "✓ Sì" if balanced else "✗ No",
            help="Attivo = Passivo + Patrimonio Netto"
        )

    if not balanced:
        diff = bs.total_assets - bs.total_liabilities
        st.warning(f"⚠️ Bilancio non quadrato! Differenza: €{diff:,.2f}")

    st.markdown("---")

    # Tabs for different views
    tab1, tab2 = st.tabs(["📋 Visualizzazione", "✏️ Modifica"])

    with tab1:
        # View mode - show as formatted tables
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("ATTIVO")

            # Prepare data
            assets_data = [
                ("A) Crediti verso soci", bs.sp01_crediti_soci),
                ("B) Immobilizzazioni", ""),
                ("  I. Immobilizzazioni immateriali", bs.sp02_immob_immateriali),
                ("  II. Immobilizzazioni materiali", bs.sp03_immob_materiali),
                ("  III. Immobilizzazioni finanziarie", bs.sp04_immob_finanziarie),
                ("C) Attivo circolante", ""),
                ("  I. Rimanenze", bs.sp05_rimanenze),
                ("  II. Crediti esigibili entro esercizio", bs.sp06_crediti_breve),
                ("  II. Crediti esigibili oltre esercizio", bs.sp07_crediti_lungo),
                ("  III. Attività finanziarie", bs.sp08_attivita_finanziarie),
                ("  IV. Disponibilità liquide", bs.sp09_disponibilita_liquide),
                ("D) Ratei e risconti attivi", bs.sp10_ratei_risconti_attivi),
                ("", ""),
                ("TOTALE ATTIVO", bs.total_assets),
            ]

            df_assets = pd.DataFrame(assets_data, columns=["Voce", "Valore"])
            df_assets['Valore'] = df_assets['Valore'].apply(
                lambda x: f"€{x:,.2f}" if isinstance(x, Decimal) else x
            )

            st.dataframe(
                df_assets,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Voce": st.column_config.TextColumn("Voce", width="large"),
                    "Valore": st.column_config.TextColumn("Valore", width="medium")
                }
            )

        with col2:
            st.subheader("PASSIVO")

            # Prepare data
            liabilities_data = [
                ("A) Patrimonio netto", ""),
                ("  I. Capitale", bs.sp11_capitale),
                ("  II. Riserve", bs.sp12_riserve),
                ("  III. Utile (perdita) dell'esercizio", bs.sp13_utile_perdita),
                ("  Totale Patrimonio Netto", bs.total_equity),
                ("B) Fondi per rischi e oneri", bs.sp14_fondi_rischi),
                ("C) Trattamento fine rapporto", bs.sp15_tfr),
                ("D) Debiti", ""),
                ("  - Esigibili entro esercizio", bs.sp16_debiti_breve),
                ("  - Esigibili oltre esercizio", bs.sp17_debiti_lungo),
                ("E) Ratei e risconti passivi", bs.sp18_ratei_risconti_passivi),
                ("", ""),
                ("TOTALE PASSIVO", bs.total_liabilities),
            ]

            df_liabilities = pd.DataFrame(liabilities_data, columns=["Voce", "Valore"])
            df_liabilities['Valore'] = df_liabilities['Valore'].apply(
                lambda x: f"€{x:,.2f}" if isinstance(x, Decimal) else x
            )

            st.dataframe(
                df_liabilities,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Voce": st.column_config.TextColumn("Voce", width="large"),
                    "Valore": st.column_config.TextColumn("Valore", width="medium")
                }
            )

        # Additional metrics
        st.markdown("---")
        st.subheader("📈 Metriche Rapide")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Attivo Immobilizzato",
                f"€{bs.fixed_assets:,.2f}",
                help="Immobilizzazioni totali"
            )

        with col2:
            st.metric(
                "Attivo Circolante",
                f"€{bs.current_assets:,.2f}",
                help="Attività correnti"
            )

        with col3:
            st.metric(
                "Debiti Totali",
                f"€{bs.total_debt:,.2f}",
                help="Debiti a breve + lungo termine"
            )

        with col4:
            autonomy = (bs.total_equity / bs.total_assets * 100) if bs.total_assets != 0 else 0
            st.metric(
                "Indice Autonomia",
                f"{autonomy:.1f}%",
                help="Patrimonio Netto / Totale Attivo"
            )

    with tab2:
        # Edit mode
        st.info("✏️ Modalità modifica - Inserisci i valori manualmente")

        with st.form("edit_balance_sheet"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### ATTIVO")

                sp01 = st.number_input("Crediti verso soci", value=float(bs.sp01_crediti_soci), step=0.01, format="%.2f")

                st.markdown("**Immobilizzazioni**")
                sp02 = st.number_input("  Immateriali", value=float(bs.sp02_immob_immateriali), step=0.01, format="%.2f")
                sp03 = st.number_input("  Materiali", value=float(bs.sp03_immob_materiali), step=0.01, format="%.2f")
                sp04 = st.number_input("  Finanziarie", value=float(bs.sp04_immob_finanziarie), step=0.01, format="%.2f")

                st.markdown("**Attivo Circolante**")
                sp05 = st.number_input("  Rimanenze", value=float(bs.sp05_rimanenze), step=0.01, format="%.2f")
                sp06 = st.number_input("  Crediti breve termine", value=float(bs.sp06_crediti_breve), step=0.01, format="%.2f")
                sp07 = st.number_input("  Crediti lungo termine", value=float(bs.sp07_crediti_lungo), step=0.01, format="%.2f")
                sp08 = st.number_input("  Attività finanziarie", value=float(bs.sp08_attivita_finanziarie), step=0.01, format="%.2f")
                sp09 = st.number_input("  Disponibilità liquide", value=float(bs.sp09_disponibilita_liquide), step=0.01, format="%.2f")

                sp10 = st.number_input("Ratei e risconti attivi", value=float(bs.sp10_ratei_risconti_attivi), step=0.01, format="%.2f")

            with col2:
                st.markdown("### PASSIVO")

                st.markdown("**Patrimonio Netto**")
                sp11 = st.number_input("  Capitale", value=float(bs.sp11_capitale), step=0.01, format="%.2f")
                sp12 = st.number_input("  Riserve", value=float(bs.sp12_riserve), step=0.01, format="%.2f")
                sp13 = st.number_input("  Utile (perdita)", value=float(bs.sp13_utile_perdita), step=0.01, format="%.2f")

                sp14 = st.number_input("Fondi rischi e oneri", value=float(bs.sp14_fondi_rischi), step=0.01, format="%.2f")
                sp15 = st.number_input("TFR", value=float(bs.sp15_tfr), step=0.01, format="%.2f")

                st.markdown("**Debiti**")
                sp16 = st.number_input("  Esigibili entro esercizio", value=float(bs.sp16_debiti_breve), step=0.01, format="%.2f")
                sp17 = st.number_input("  Esigibili oltre esercizio", value=float(bs.sp17_debiti_lungo), step=0.01, format="%.2f")

                sp18 = st.number_input("Ratei e risconti passivi", value=float(bs.sp18_ratei_risconti_passivi), step=0.01, format="%.2f")

            submitted = st.form_submit_button("💾 Salva Modifiche", use_container_width=True)

            if submitted:
                try:
                    bs.sp01_crediti_soci = Decimal(str(sp01))
                    bs.sp02_immob_immateriali = Decimal(str(sp02))
                    bs.sp03_immob_materiali = Decimal(str(sp03))
                    bs.sp04_immob_finanziarie = Decimal(str(sp04))
                    bs.sp05_rimanenze = Decimal(str(sp05))
                    bs.sp06_crediti_breve = Decimal(str(sp06))
                    bs.sp07_crediti_lungo = Decimal(str(sp07))
                    bs.sp08_attivita_finanziarie = Decimal(str(sp08))
                    bs.sp09_disponibilita_liquide = Decimal(str(sp09))
                    bs.sp10_ratei_risconti_attivi = Decimal(str(sp10))
                    bs.sp11_capitale = Decimal(str(sp11))
                    bs.sp12_riserve = Decimal(str(sp12))
                    bs.sp13_utile_perdita = Decimal(str(sp13))
                    bs.sp14_fondi_rischi = Decimal(str(sp14))
                    bs.sp15_tfr = Decimal(str(sp15))
                    bs.sp16_debiti_breve = Decimal(str(sp16))
                    bs.sp17_debiti_lungo = Decimal(str(sp17))
                    bs.sp18_ratei_risconti_passivi = Decimal(str(sp18))

                    db.commit()
                    st.success("✅ Stato Patrimoniale aggiornato!")
                    st.rerun()

                except Exception as e:
                    db.rollback()
                    st.error(f"❌ Errore durante il salvataggio: {e}")
