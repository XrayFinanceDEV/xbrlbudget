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
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
<style>
    /* Hide sidebar completely */
    [data-testid="stSidebar"] {
        display: none;
    }

    /* Adjust main content to use full width */
    .main .block-container {
        padding-left: 2rem;
        padding-right: 2rem;
        max-width: 100%;
    }

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

    /* Selection bar styling */
    .selection-bar {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1.5rem;
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

# Get all companies
db = st.session_state.db
companies = db.query(Company).all()

# Company and Year Selection Bar (horizontal layout at top)
st.markdown('<div class="selection-bar">', unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns([3, 2, 2, 3])

with col1:
    if companies:
        company_options = {f"{c.name} ({c.tax_id})": c.id for c in companies}
        company_options["+ Nuova Azienda"] = None

        selected_company_name = st.selectbox(
            "🏢 Azienda",
            options=list(company_options.keys()),
            index=0 if st.session_state.selected_company_id is None else
                  list(company_options.values()).index(st.session_state.selected_company_id),
            key="company_select"
        )

        st.session_state.selected_company_id = company_options[selected_company_name]
    else:
        st.info("Nessuna azienda trovata")
        st.session_state.selected_company_id = None

with col2:
    # If company is selected, show year selection
    if st.session_state.selected_company_id:
        company = db.query(Company).filter(Company.id == st.session_state.selected_company_id).first()

        # Get available years for this company
        financial_years = db.query(FinancialYear).filter(
            FinancialYear.company_id == company.id
        ).order_by(FinancialYear.year.desc()).all()

        if financial_years:
            year_options = {str(fy.year): fy.year for fy in financial_years}
            year_options["+ Nuovo Anno"] = None

            selected_year_str = st.selectbox(
                "📅 Anno Fiscale",
                options=list(year_options.keys()),
                index=0 if st.session_state.selected_year is None else
                      list(year_options.values()).index(st.session_state.selected_year),
                key="year_select"
            )

            st.session_state.selected_year = year_options[selected_year_str]
        else:
            st.info("Nessun anno trovato")
            st.session_state.selected_year = None
    else:
        st.selectbox("📅 Anno Fiscale", options=["Seleziona azienda"], disabled=True, key="year_disabled")

with col3:
    if st.session_state.selected_company_id:
        company = db.query(Company).filter(Company.id == st.session_state.selected_company_id).first()
        st.metric("Settore", Sector(company.sector).name, label_visibility="visible")
    else:
        st.metric("Settore", "N/A", label_visibility="visible")

with col4:
    if st.session_state.selected_company_id:
        company = db.query(Company).filter(Company.id == st.session_state.selected_company_id).first()
        st.metric("P.IVA", company.tax_id or "N/A", label_visibility="visible")
    else:
        st.metric("P.IVA", "N/A", label_visibility="visible")

st.markdown('</div>', unsafe_allow_html=True)

# Main content area - Using Tabs for navigation
page = st.tabs([
    "🏠 Home",
    "📥 Importazione Dati",
    "📝 Input Ipotesi",
    "💰 CE Previsionale",
    "📊 SP Previsionale",
    "📋 Previsionale Riclassificato",
    "📈 Indici",
    "💵 Rendiconto Finanziario"
])

# Home Tab
with page[0]:
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
        - ✅ Previsioni budget 3 anni
        """)

    with col2:
        st.markdown("""
        **Analisi Finanziaria:**
        - ✅ Indici di liquidità, solvibilità, redditività
        - ✅ Capitale circolante netto (CCN)
        - ✅ Altman Z-Score settoriale
        - ✅ Rating FGPMI (13 classi di rating)
        - ✅ Rendiconto finanziario
        """)

# Importazione Dati Tab
with page[1]:
    from ui.pages import importazione
    importazione.show()

# Input Ipotesi Tab
with page[2]:
    from ui.pages import budget
    budget.show()

# CE Previsionale Tab
with page[3]:
    from ui.pages import ce_previsionale
    ce_previsionale.show()

# SP Previsionale Tab
with page[4]:
    from ui.pages import sp_previsionale
    sp_previsionale.show()

# Previsionale Riclassificato Tab
with page[5]:
    from ui.pages import previsionale_riclassificato
    previsionale_riclassificato.show()

# Indici Tab (combines ratios + Altman + FGPMI)
with page[6]:
    from ui.pages import indici
    indici.show()

# Rendiconto Finanziario Tab
with page[7]:
    from ui.pages import rendiconto_finanziario
    rendiconto_finanziario.show()
