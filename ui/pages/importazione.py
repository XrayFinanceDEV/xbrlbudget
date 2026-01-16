"""
Data Import Page (Importazione Dati)
Import financial data from XBRL or CSV files
"""
import streamlit as st
import tempfile
import os
from importers.xbrl_parser import import_xbrl_file
from importers.csv_importer import import_csv_file


def show():
    """Display import page"""
    st.title("📥 Importazione Dati")
    st.markdown("Importa bilanci da file XBRL o CSV")

    db = st.session_state.db

    # Import type selection
    import_type = st.radio(
        "Tipo di File",
        ["XBRL (formato italiano)", "CSV (da conversione TEBE)"],
        horizontal=True
    )

    st.markdown("---")

    if import_type == "XBRL (formato italiano)":
        # XBRL Import
        st.subheader("📄 Importazione XBRL")

        st.info("""
        **Formato supportato:** File XBRL secondo tassonomia italiana (OIC)
        - Versioni supportate: 2018-11-04, 2017-07-06, 2016-11-14, 2015-12-14, 2014-11-17, 2011-01-04
        - L'azienda verrà creata automaticamente se non esiste
        - Dati estratti: Stato Patrimoniale, Conto Economico, dati anagrafici
        """)

        uploaded_file = st.file_uploader(
            "Carica file XBRL",
            type=['xbrl', 'xml'],
            help="Seleziona un file XBRL (.xbrl o .xml)"
        )

        col1, col2 = st.columns(2)

        with col1:
            import_mode = st.radio(
                "Modalità Importazione",
                ["Aggiorna azienda esistente", "Crea nuova azienda"],
                help="Scegli se aggiornare l'azienda selezionata o crearne una nuova"
            )

        with col2:
            if import_mode == "Crea nuova azienda":
                st.info("💡 Verrà creata una nuova azienda con i dati dal file XBRL")
            else:
                if st.session_state.selected_company_id:
                    st.info("💡 I dati dell'azienda selezionata verranno aggiornati")
                else:
                    st.warning("⚠️ Nessuna azienda selezionata! Seleziona un'azienda o cambia modalità")

        # Set create_company based on mode
        create_company = (import_mode == "Crea nuova azienda") or (st.session_state.selected_company_id is None)

        if uploaded_file is not None:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xbrl') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name

            # Validate before allowing import
            can_import = True
            if import_mode == "Aggiorna azienda esistente" and not st.session_state.selected_company_id:
                can_import = False
                st.error("❌ Devi selezionare un'azienda per aggiornarla")

            if st.button("🚀 Importa XBRL", use_container_width=True, disabled=not can_import):
                try:
                    with st.spinner("Importazione in corso..."):
                        # If creating new company, pass None as company_id
                        company_id = None if import_mode == "Crea nuova azienda" else st.session_state.selected_company_id

                        result = import_xbrl_file(
                            file_path=tmp_file_path,
                            company_id=company_id,
                            create_company=create_company
                        )

                    # Clean up temp file
                    os.unlink(tmp_file_path)

                    # Show success
                    st.success("✅ Importazione completata con successo!")

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric("Azienda", result['company_name'])
                        st.metric("P.IVA", result['tax_id'])

                    with col2:
                        st.metric("Tassonomia", result['taxonomy_version'])
                        st.metric("Contesti", result['contexts_found'])

                    with col3:
                        st.metric("Anni Importati", result['years_imported'])
                        st.metric("Anni", ", ".join(map(str, result['years'])))

                    # Set selected company
                    st.session_state.selected_company_id = result['company_id']

                    st.balloons()

                except Exception as e:
                    st.error(f"❌ Errore durante l'importazione: {e}")
                    import traceback
                    with st.expander("Dettagli errore"):
                        st.code(traceback.format_exc())

                    # Clean up temp file
                    if os.path.exists(tmp_file_path):
                        os.unlink(tmp_file_path)

    else:
        # CSV Import
        st.subheader("📄 Importazione CSV")

        st.info("""
        **Formato supportato:** CSV esportato da conversione TEBE
        - Delimitatore: punto e virgola (;)
        - Codifica: UTF-8
        - Formato: Descrizione; Anno1; Anno2; Tag; Unità
        - Richiede un'azienda già creata
        """)

        # Company selection required for CSV
        if not st.session_state.selected_company_id:
            st.warning("⚠️ Seleziona o crea un'azienda prima di importare CSV")
            return

        uploaded_file = st.file_uploader(
            "Carica file CSV",
            type=['csv'],
            help="Seleziona un file CSV da conversione TEBE"
        )

        col1, col2 = st.columns(2)

        with col1:
            year1 = st.number_input(
                "Anno Corrente",
                min_value=2000,
                max_value=2100,
                value=2024,
                step=1
            )

        with col2:
            year2 = st.number_input(
                "Anno Precedente",
                min_value=2000,
                max_value=2100,
                value=2023,
                step=1
            )

        if uploaded_file is not None:
            # Save uploaded file temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name

            if st.button("🚀 Importa CSV", use_container_width=True):
                try:
                    with st.spinner("Importazione in corso..."):
                        result = import_csv_file(
                            file_path=tmp_file_path,
                            company_id=st.session_state.selected_company_id,
                            year1=year1,
                            year2=year2
                        )

                    # Clean up temp file
                    os.unlink(tmp_file_path)

                    # Show success
                    st.success("✅ Importazione completata con successo!")

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric("Tipo Bilancio", result['balance_sheet_type'])
                        st.metric("Anni", f"{year1}, {year2}")

                    with col2:
                        st.metric("Righe Processate", result['rows_processed'])
                        st.metric("Campi SP", result['balance_sheet_fields_imported'])

                    with col3:
                        st.metric("Campi CE", result['income_statement_fields_imported'])

                    st.balloons()

                except Exception as e:
                    st.error(f"❌ Errore durante l'importazione: {e}")
                    import traceback
                    with st.expander("Dettagli errore"):
                        st.code(traceback.format_exc())

                    # Clean up temp file
                    if os.path.exists(tmp_file_path):
                        os.unlink(tmp_file_path)

    st.markdown("---")

    # Quick guide
    with st.expander("📖 Guida all'Importazione"):
        st.markdown("""
        ### XBRL Import
        1. Seleziona un file XBRL (.xbrl o .xml) scaricato dal Registro Imprese
        2. Il sistema riconoscerà automaticamente la versione della tassonomia
        3. L'azienda verrà creata automaticamente con i dati dal file
        4. Verranno importati tutti gli anni presenti nel file

        ### CSV Import
        1. Esporta il bilancio da TEBE in formato CSV
        2. Crea prima l'azienda nella sezione "Dati Impresa"
        3. Seleziona l'azienda nel menù laterale
        4. Carica il file CSV e specifica gli anni
        5. Il sistema importerà automaticamente SP e CE

        ### Formato Dati
        - **Stato Patrimoniale**: Tutte le voci attivo e passivo
        - **Conto Economico**: Valore della produzione e costi
        - **Metadati**: Ragione sociale, P.IVA, settore
        """)
