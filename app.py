"""
Financial Analysis Application - Main Entry Point
Italian GAAP Financial Analysis and Rating System
"""
import streamlit as st
from database.db import init_db, SessionLocal
from database.models import Company, FinancialYear
from config import Sector

# Page configuration
st.set_page_config(
    page_title="Analisi Finanziaria",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Initialize database
@st.cache_resource
def get_database():
    """Initialize database connection"""
    init_db()
    return SessionLocal()

# Initialize session state
if 'db' not in st.session_state:
    st.session_state.db = get_database()

if 'selected_company_id' not in st.session_state:
    st.session_state.selected_company_id = None

if 'selected_year' not in st.session_state:
    st.session_state.selected_year = None

# Sidebar - Company Selection
st.sidebar.title("🏢 Selezione Azienda")

# Get all companies
db = st.session_state.db
companies = db.query(Company).all()

if companies:
    company_options = {f"{c.name} ({c.tax_id})": c.id for c in companies}
    company_options["+ Nuova Azienda"] = None

    selected_company_name = st.sidebar.selectbox(
        "Azienda",
        options=list(company_options.keys()),
        index=0 if st.session_state.selected_company_id is None else
              list(company_options.values()).index(st.session_state.selected_company_id)
    )

    st.session_state.selected_company_id = company_options[selected_company_name]
else:
    st.sidebar.info("Nessuna azienda trovata. Crea la prima azienda!")
    st.session_state.selected_company_id = None

# If company is selected, show year selection
if st.session_state.selected_company_id:
    company = db.query(Company).filter(Company.id == st.session_state.selected_company_id).first()

    st.sidebar.markdown("---")
    st.sidebar.subheader(f"📅 Anno Fiscale")

    # Get available years for this company
    financial_years = db.query(FinancialYear).filter(
        FinancialYear.company_id == company.id
    ).order_by(FinancialYear.year.desc()).all()

    if financial_years:
        year_options = {str(fy.year): fy.year for fy in financial_years}
        year_options["+ Nuovo Anno"] = None

        selected_year_str = st.sidebar.selectbox(
            "Anno",
            options=list(year_options.keys()),
            index=0 if st.session_state.selected_year is None else
                  list(year_options.values()).index(st.session_state.selected_year)
        )

        st.session_state.selected_year = year_options[selected_year_str]
    else:
        st.sidebar.info("Nessun anno fiscale trovato. Crea il primo anno!")
        st.session_state.selected_year = None

    # Show company info
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Informazioni Azienda:**")
    st.sidebar.text(f"Settore: {Sector(company.sector).name}")
    st.sidebar.text(f"P.IVA: {company.tax_id or 'N/A'}")

st.sidebar.markdown("---")

# Navigation
st.sidebar.title("📋 Navigazione")

page = st.sidebar.radio(
    "Sezioni",
    [
        "🏠 Home",
        "🏢 Dati Impresa",
        "📥 Importazione Dati",
        "📊 Stato Patrimoniale",
        "💰 Conto Economico",
        "📈 Indici Finanziari",
        "⚖️ Altman Z-Score",
        "⭐ Rating FGPMI",
        "📉 Dashboard"
    ]
)

# Main content area
if page == "🏠 Home":
    st.markdown('<div class="main-header">📊 Analisi Finanziaria - Sistema di Rating</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Analisi di bilancio secondo i principi contabili italiani (OIC)</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info("### 📊 Analisi Completa\n\nImporta bilanci da XBRL, calcola indici finanziari e ottieni rating creditizio automatico.")

    with col2:
        st.success("### ⚖️ Altman Z-Score\n\nValutazione del rischio di insolvenza con modelli settoriali specifici.")

    with col3:
        st.warning("### ⭐ Rating FGPMI\n\nRating creditizio per PMI secondo il modello Fondo di Garanzia.")

    st.markdown("---")

    # Statistics
    st.subheader("📈 Statistiche Sistema")

    col1, col2, col3, col4 = st.columns(4)

    total_companies = db.query(Company).count()
    total_years = db.query(FinancialYear).count()

    with col1:
        st.metric("Aziende", total_companies)

    with col2:
        st.metric("Anni Fiscali", total_years)

    with col3:
        if st.session_state.selected_company_id:
            company = db.query(Company).filter(Company.id == st.session_state.selected_company_id).first()
            st.metric("Azienda Selezionata", "Sì" if company else "No")
        else:
            st.metric("Azienda Selezionata", "No")

    with col4:
        if st.session_state.selected_year:
            st.metric("Anno Selezionato", st.session_state.selected_year)
        else:
            st.metric("Anno Selezionato", "N/A")

    st.markdown("---")

    # Quick actions
    st.subheader("🚀 Azioni Rapide")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("➕ Nuova Azienda", use_container_width=True):
            st.session_state.selected_company_id = None
            st.rerun()

    with col2:
        if st.button("📥 Importa XBRL", use_container_width=True):
            st.info("Vai alla sezione 'Importazione Dati' per importare file XBRL")

    with col3:
        if st.button("📊 Dashboard", use_container_width=True):
            st.info("Seleziona 'Dashboard' dalla navigazione")

    st.markdown("---")

    # Features
    st.subheader("✨ Funzionalità")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **Gestione Dati:**
        - ✅ Creazione e modifica aziende
        - ✅ Gestione multi-anno (fino a 5 anni)
        - ✅ Importazione da XBRL (formato italiano)
        - ✅ Importazione da CSV (TEBE)
        - ✅ Inserimento manuale bilanci
        """)

    with col2:
        st.markdown("""
        **Analisi Finanziaria:**
        - ✅ Indici di liquidità, solvibilità, redditività
        - ✅ Capitale circolante netto (CCN)
        - ✅ Altman Z-Score settoriale
        - ✅ Rating FGPMI (13 classi di rating)
        - ✅ Confronti anno su anno
        """)

elif page == "🏢 Dati Impresa":
    # Import the company data page
    from ui.pages import dati_impresa
    dati_impresa.show()

elif page == "📥 Importazione Dati":
    from ui.pages import importazione
    importazione.show()

elif page == "📊 Stato Patrimoniale":
    from ui.pages import balance_sheet
    balance_sheet.show()

elif page == "💰 Conto Economico":
    from ui.pages import income_statement
    income_statement.show()

elif page == "📈 Indici Finanziari":
    from ui.pages import ratios
    ratios.show()

elif page == "⚖️ Altman Z-Score":
    from ui.pages import altman
    altman.show()

elif page == "⭐ Rating FGPMI":
    from ui.pages import rating
    rating.show()

elif page == "📉 Dashboard":
    from ui.pages import dashboard
    dashboard.show()

# Footer
st.sidebar.markdown("---")
st.sidebar.caption("💻 Financial Analysis System v1.0")
st.sidebar.caption("🇮🇹 Italian GAAP Compliant")
