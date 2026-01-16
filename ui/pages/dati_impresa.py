"""
Company Data (Dati Impresa) Page
Create and edit company information
"""
import streamlit as st
from database.models import Company
from config import Sector


def show():
    """Display company data page"""
    st.title("🏢 Dati Impresa")
    st.markdown("Gestione dei dati anagrafici dell'azienda")

    db = st.session_state.db

    # Check if creating new or editing existing
    if st.session_state.selected_company_id is None:
        # Create new company
        st.subheader("➕ Nuova Azienda")

        with st.form("new_company_form"):
            col1, col2 = st.columns(2)

            with col1:
                name = st.text_input("Ragione Sociale *", placeholder="Es: Acme S.r.l.")
                tax_id = st.text_input("Partita IVA / Codice Fiscale", placeholder="12345678901")
                sector = st.selectbox(
                    "Settore *",
                    options=[s.value for s in Sector],
                    format_func=lambda x: Sector(x).name
                )

            with col2:
                address = st.text_area("Indirizzo", placeholder="Via, Città, CAP")
                notes = st.text_area("Note", placeholder="Informazioni aggiuntive...")

            submitted = st.form_submit_button("💾 Crea Azienda", use_container_width=True)

            if submitted:
                if not name:
                    st.error("❌ La ragione sociale è obbligatoria!")
                else:
                    try:
                        new_company = Company(
                            name=name,
                            tax_id=tax_id if tax_id else None,
                            sector=sector,
                            notes=notes if notes else None
                        )
                        db.add(new_company)
                        db.commit()
                        db.refresh(new_company)

                        st.success(f"✅ Azienda '{name}' creata con successo!")
                        st.session_state.selected_company_id = new_company.id
                        st.rerun()

                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Errore durante la creazione: {e}")

    else:
        # Edit existing company
        company = db.query(Company).filter(Company.id == st.session_state.selected_company_id).first()

        if not company:
            st.error("❌ Azienda non trovata!")
            st.session_state.selected_company_id = None
            st.rerun()
            return

        st.subheader(f"✏️ Modifica: {company.name}")

        # Display mode toggle
        edit_mode = st.toggle("Modalità Modifica", value=False)

        if edit_mode:
            # Edit form
            with st.form("edit_company_form"):
                col1, col2 = st.columns(2)

                with col1:
                    name = st.text_input("Ragione Sociale *", value=company.name)
                    tax_id = st.text_input(
                        "Partita IVA / Codice Fiscale",
                        value=company.tax_id if company.tax_id else ""
                    )
                    sector = st.selectbox(
                        "Settore *",
                        options=[s.value for s in Sector],
                        index=[s.value for s in Sector].index(company.sector),
                        format_func=lambda x: Sector(x).name
                    )

                with col2:
                    notes = st.text_area(
                        "Note",
                        value=company.notes if company.notes else "",
                        placeholder="Informazioni aggiuntive..."
                    )

                col1, col2 = st.columns(2)

                with col1:
                    submitted = st.form_submit_button("💾 Salva Modifiche", use_container_width=True)

                with col2:
                    delete = st.form_submit_button("🗑️ Elimina Azienda", use_container_width=True, type="secondary")

                if submitted:
                    if not name:
                        st.error("❌ La ragione sociale è obbligatoria!")
                    else:
                        try:
                            company.name = name
                            company.tax_id = tax_id if tax_id else None
                            company.sector = sector
                            company.notes = notes if notes else None

                            db.commit()
                            st.success(f"✅ Azienda '{name}' aggiornata con successo!")
                            st.rerun()

                        except Exception as e:
                            db.rollback()
                            st.error(f"❌ Errore durante l'aggiornamento: {e}")

                if delete:
                    # Confirm deletion
                    st.warning("⚠️ Confermare l'eliminazione?")
                    if st.button("Sì, elimina definitivamente"):
                        try:
                            db.delete(company)
                            db.commit()
                            st.success("✅ Azienda eliminata")
                            st.session_state.selected_company_id = None
                            st.rerun()
                        except Exception as e:
                            db.rollback()
                            st.error(f"❌ Errore durante l'eliminazione: {e}")

        else:
            # View mode
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### 📋 Informazioni Generali")
                st.text(f"Ragione Sociale: {company.name}")
                st.text(f"P.IVA / CF: {company.tax_id if company.tax_id else 'N/A'}")
                st.text(f"Settore: {Sector(company.sector).name}")
                st.text(f"ID: {company.id}")

            with col2:
                st.markdown("### 📝 Note")
                if company.notes:
                    st.text(company.notes)
                else:
                    st.text("Nessuna nota")

            # Financial years summary
            from database.models import FinancialYear

            st.markdown("---")
            st.markdown("### 📅 Anni Fiscali")

            years = db.query(FinancialYear).filter(
                FinancialYear.company_id == company.id
            ).order_by(FinancialYear.year.desc()).all()

            if years:
                cols = st.columns(min(len(years), 4))
                for idx, fy in enumerate(years[:4]):
                    with cols[idx % 4]:
                        st.metric(
                            label=f"Anno {fy.year}",
                            value=f"€{fy.balance_sheet.total_assets:,.0f}" if fy.balance_sheet else "N/A"
                        )

                if len(years) > 4:
                    st.info(f"+ {len(years) - 4} altri anni...")
            else:
                st.info("Nessun anno fiscale presente. Vai a 'Importazione Dati' o crea manualmente.")
