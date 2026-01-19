"""
Configuration and Constants for Financial Analysis Application
"""
from enum import Enum
from typing import Dict, List

# Application Settings
APP_NAME = "Analisi Finanziaria"
APP_VERSION = "1.0.0"
DATABASE_URL = "sqlite:///./financial_analysis.db"  # For production: postgresql://user:pass@localhost/dbname

# Analysis Configuration
MIN_ANALYSIS_YEAR = 2014  # AnnoAnalisiInizialeAssoluto from VBA
MAX_YEARS_TO_ANALYZE = 5

# Sector Definitions (IndiceSettoreAttività)
class Sector(Enum):
    INDUSTRIA = 1  # Manufacturing, Hotels (property owners), Agriculture, Fishing
    COMMERCIO = 2  # Commerce/Retail
    SERVIZI = 3  # Services (non-transport) and Hotels (lessees)
    AUTOTRASPORTI = 4  # Transport
    IMMOBILIARE = 5  # Real Estate
    EDILIZIA = 6  # Construction

SECTOR_NAMES_IT = {
    Sector.INDUSTRIA: "Industria, Alberghi (Proprietari), Agricoltura, Pesca",
    Sector.COMMERCIO: "Commercio",
    Sector.SERVIZI: "Servizi (Diversi da Autotrasporti) e Alberghi (Locatari)",
    Sector.AUTOTRASPORTI: "Autotrasporti",
    Sector.IMMOBILIARE: "Immobiliare",
    Sector.EDILIZIA: "Edilizia"
}

# Balance Sheet Line Item Codes (SP = Stato Patrimoniale)
class BalanceSheetCode(Enum):
    # ASSETS
    SP01_CREDITI_SOCI = "sp01"  # Receivables from shareholders
    SP02_IMMOB_IMMATERIALI = "sp02"  # Intangible fixed assets
    SP03_IMMOB_MATERIALI = "sp03"  # Tangible fixed assets
    SP04_IMMOB_FINANZIARIE = "sp04"  # Financial fixed assets
    SP05_RIMANENZE = "sp05"  # Inventory
    SP06_CREDITI_BREVE = "sp06"  # Short-term receivables (within 12 months)
    SP07_CREDITI_LUNGO = "sp07"  # Long-term receivables (beyond 12 months)
    SP08_ATTIVITA_FINANZIARIE = "sp08"  # Current financial assets
    SP09_DISPONIBILITA_LIQUIDE = "sp09"  # Cash and cash equivalents
    SP10_RATEI_RISCONTI_ATTIVI = "sp10"  # Prepaid expenses

    # LIABILITIES & EQUITY
    SP11_CAPITALE = "sp11"  # Capital stock
    SP12_RISERVE = "sp12"  # Reserves
    SP13_UTILE_PERDITA = "sp13"  # Profit/Loss for the year
    SP14_FONDI_RISCHI = "sp14"  # Provisions for risks and charges
    SP15_TFR = "sp15"  # Employee severance obligations (TFR)
    SP16_DEBITI_BREVE = "sp16"  # Short-term debt (within 12 months)
    SP17_DEBITI_LUNGO = "sp17"  # Long-term debt (beyond 12 months)
    SP18_RATEI_RISCONTI_PASSIVI = "sp18"  # Accrued expenses and deferred income

# Income Statement Line Item Codes (CE = Conto Economico)
class IncomeStatementCode(Enum):
    # REVENUE
    CE01_RICAVI_VENDITE = "ce01"  # Revenue from sales and services
    CE02_VARIAZIONI_RIMANENZE = "ce02"  # Changes in inventory
    CE03_LAVORI_INTERNI = "ce03"  # Capitalized internal work
    CE04_ALTRI_RICAVI = "ce04"  # Other revenue and income

    # COSTS
    CE05_MATERIE_PRIME = "ce05"  # Raw materials
    CE06_SERVIZI = "ce06"  # Services
    CE07_GODIMENTO_BENI = "ce07"  # Lease/rental of third-party assets
    CE08_COSTI_PERSONALE = "ce08"  # Personnel costs
    CE09_AMMORTAMENTI = "ce09"  # Depreciation and amortization
    CE10_SVALUTAZIONI = "ce10"  # Impairments
    CE11_ACCANTONAMENTI = "ce11"  # Provisions
    CE12_ONERI_DIVERSI = "ce12"  # Other operating expenses

    # FINANCIAL
    CE13_PROVENTI_PARTECIPAZIONI = "ce13"  # Income from investments
    CE14_PROVENTI_FINANZIARI = "ce14"  # Other financial income
    CE15_ONERI_FINANZIARI = "ce15"  # Financial expenses/interest
    CE16_UTILI_PERDITE_CAMBI = "ce16"  # Exchange gains/losses

    # EXTRAORDINARY & TAXES
    CE17_RETTIFICHE_ATTIVITA_FIN = "ce17"  # Adjustments to financial assets
    CE18_PROVENTI_STRAORDINARI = "ce18"  # Extraordinary income
    CE19_ONERI_STRAORDINARI = "ce19"  # Extraordinary expenses
    CE20_IMPOSTE = "ce20"  # Income taxes

# Named Ranges (Excel equivalents)
NAMED_RANGES = {
    # Balance Sheet Aggregates
    "TA": "total_assets",  # Totale Attivo
    "CN": "total_equity",  # Capitale Netto
    "TP": "total_liabilities",  # Totale Passivo
    "AF": "fixed_assets",  # Attivo Fisso (Immobilizzazioni)
    "AC": "current_assets",  # Attivo Corrente
    "PC": "current_liabilities",  # Passivo Corrente
    "DBT": "total_debt",  # Debiti Totali
    "DML": "long_term_debt",  # Debiti Medio-Lungo termine
    "DBT_BREVE": "short_term_debt",  # Debiti Breve termine

    # Income Statement Aggregates
    "FATT": "revenue",  # Fatturato (Revenue)
    "VP": "production_value",  # Valore della Produzione
    "COPRO": "production_cost",  # Costi della Produzione
    "MOL": "ebitda",  # Margine Operativo Lordo (EBITDA)
    "RO": "ebit",  # Risultato Operativo (EBIT)
    "RISO": "operating_result",  # Risultato Operativo
    "CL": "labor_cost",  # Costi del Lavoro
    "POFIN": "financial_income",  # Proventi Finanziari
    "ONFIN": "financial_charges",  # Oneri Finanziari
    "UTILE": "net_profit"  # Utile Netto
}

# Working Capital Metrics Formulas
WORKING_CAPITAL_FORMULAS = {
    "CCLN": "current_assets - inventory",  # Capital Circolante Lordo Netto
    "CCN": "current_assets - current_liabilities",  # Capitale Circolante Netto
    "MS": "equity - fixed_assets",  # Margine di Struttura
    "MT": "(cash + short_term_receivables + long_term_receivables) - current_liabilities"  # Margine di Tesoreria
}

# XBRL Taxonomy Versions
SUPPORTED_TAXONOMIES = [
    "2018-11-04",
    "2017-07-06",
    "2016-11-14",
    "2015-12-14",
    "2014-11-17",
    "2011-01-04"
]

# Balance Sheet Types (Schema Bilancio)
class BalanceSheetType(Enum):
    ORDINARIO = "BILANCIO ESERCIZIO"  # Full balance sheet
    ABBREVIATO = "BILANCIO ABBREVIATO"  # Abbreviated balance sheet
    MICRO = "BILANCIO MICRO"  # Micro-enterprise balance sheet

# Taxonomy detection by row count
TAXONOMY_ROW_COUNTS = {
    BalanceSheetType.ORDINARIO: [363, 294, 305],
    BalanceSheetType.ABBREVIATO: [234, 233, 193, 205],
    BalanceSheetType.MICRO: [231, 230]
}

# Altman Z-Score Thresholds
ALTMAN_THRESHOLDS_MANUFACTURING = {
    "safe": 2.9,
    "gray_zone_low": 1.23,
    "distress": 1.23
}

ALTMAN_THRESHOLDS_SERVICES = {
    "safe": 2.6,
    "gray_zone_low": 1.1,
    "distress": 1.1
}

# Altman Z-Score Coefficients
ALTMAN_COEFFICIENTS_MANUFACTURING = {
    "A": 0.717,  # Working Capital / Total Assets
    "B": 0.847,  # Retained Earnings / Total Assets
    "C": 3.107,  # EBIT / Total Assets
    "D": 0.42,   # Market Value Equity / Total Debt
    "E": 0.998   # Revenue / Total Assets
}

ALTMAN_COEFFICIENTS_SERVICES = {
    "A": 6.56,  # Working Capital / Total Assets
    "B": 3.26,  # Retained Earnings / Total Assets
    "C": 6.72,  # EBIT / Total Assets
    "D": 1.05,  # Market Value Equity / Total Debt
    "constant": 3.25
}

# FGPMI Rating Classes
FGPMI_RATING_CLASSES = [
    "AAA", "AA+", "AA", "AA-", "A+", "A", "A-",  # Investment grade (1-7)
    "BBB+", "BBB", "BBB-",  # Medium grade (8-10)
    "BB+", "BB", "BB-", "B+", "B", "B-",  # Below investment grade (11-16)
    "CCC+", "CCC", "CCC-"  # High risk (17-19)
]

# Revenue thresholds for FGPMI
FGPMI_REVENUE_THRESHOLD = 500_000  # €500K

# Number formatting
DECIMAL_PLACES = {
    "currency": 2,
    "percentage": 2,
    "ratio": 4,
    "zscore": 2
}

# Chart configuration
CHART_COLORS = {
    "primary": "#1f77b4",
    "secondary": "#ff7f0e",
    "positive": "#2ca02c",
    "negative": "#d62728",
    "neutral": "#7f7f7f"
}

# PDF Report Settings
PDF_PAGE_SIZE = "A4"
PDF_MARGIN = {
    "left": 20,
    "right": 20,
    "top": 25,
    "bottom": 25
}

# CSV Import Settings
CSV_DELIMITER = ";"  # Semicolon for Italian CSV format
CSV_ENCODING = "utf-8"
CSV_HTML_ENTITIES_TO_REPLACE = {
    "&nbsp;": " ",
    "à": "a",
    "è": "e",
    "ì": "i",
    "ò": "o",
    "ù": "u",
    "'": "'"
}

# Validation Rules
VALIDATION_RULES = {
    "balance_sheet_tolerance": 0.01,  # €0.01 tolerance for Assets = Equity + Liabilities
    "percentage_min": 0.0,
    "percentage_max": 100.0,
    "days_min": 0,
    "days_max": 360
}
