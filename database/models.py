"""
SQLAlchemy ORM Models for Financial Analysis Application
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from database.db import Base
from config import Sector
import enum


class Company(Base):
    """
    Company master data (DATI_IMPRESA)
    """
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    tax_id = Column(String(20), unique=True, nullable=True, index=True)  # Partita IVA / Codice Fiscale
    sector = Column(Integer, nullable=False)  # 1-6 (Sector enum)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    financial_years = relationship("FinancialYear", back_populates="company", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Company(id={self.id}, name='{self.name}', sector={self.sector})>"


class FinancialYear(Base):
    """
    Financial Year container linking Company to Balance Sheet and Income Statement
    """
    __tablename__ = "financial_years"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    year = Column(Integer, nullable=False, index=True)  # e.g., 2024
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = relationship("Company", back_populates="financial_years")
    balance_sheet = relationship("BalanceSheet", back_populates="financial_year", uselist=False, cascade="all, delete-orphan")
    income_statement = relationship("IncomeStatement", back_populates="financial_year", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<FinancialYear(id={self.id}, company_id={self.company_id}, year={self.year})>"


class BalanceSheet(Base):
    """
    Balance Sheet (Stato Patrimoniale - SP)

    All monetary values stored as Decimal for precision
    Line items follow Italian civil code structure (art. 2424 c.c.)
    """
    __tablename__ = "balance_sheets"

    id = Column(Integer, primary_key=True, index=True)
    financial_year_id = Column(Integer, ForeignKey("financial_years.id"), nullable=False, unique=True)

    # === ASSETS (ATTIVO) ===

    # A) Crediti verso soci per versamenti ancora dovuti
    sp01_crediti_soci = Column(Numeric(15, 2), default=0, nullable=False)

    # B) Immobilizzazioni
    # B.I) Immobilizzazioni immateriali
    sp02_immob_immateriali = Column(Numeric(15, 2), default=0, nullable=False)

    # B.II) Immobilizzazioni materiali
    sp03_immob_materiali = Column(Numeric(15, 2), default=0, nullable=False)

    # B.III) Immobilizzazioni finanziarie
    sp04_immob_finanziarie = Column(Numeric(15, 2), default=0, nullable=False)

    # C) Attivo circolante
    # C.I) Rimanenze
    sp05_rimanenze = Column(Numeric(15, 2), default=0, nullable=False)

    # C.II) Crediti - split by maturity
    sp06_crediti_breve = Column(Numeric(15, 2), default=0, nullable=False)  # Entro 12 mesi
    sp07_crediti_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # Oltre 12 mesi

    # C.III) Attività finanziarie che non costituiscono immobilizzazioni
    sp08_attivita_finanziarie = Column(Numeric(15, 2), default=0, nullable=False)

    # C.IV) Disponibilità liquide
    sp09_disponibilita_liquide = Column(Numeric(15, 2), default=0, nullable=False)

    # D) Ratei e risconti attivi
    sp10_ratei_risconti_attivi = Column(Numeric(15, 2), default=0, nullable=False)

    # === LIABILITIES & EQUITY (PASSIVO) ===

    # A) Patrimonio Netto
    # A.I) Capitale
    sp11_capitale = Column(Numeric(15, 2), default=0, nullable=False)

    # A.II-VII) Riserve (aggregated)
    sp12_riserve = Column(Numeric(15, 2), default=0, nullable=False)

    # A.VIII/IX) Utile/Perdita dell'esercizio
    sp13_utile_perdita = Column(Numeric(15, 2), default=0, nullable=False)

    # B) Fondi per rischi e oneri
    sp14_fondi_rischi = Column(Numeric(15, 2), default=0, nullable=False)

    # C) Trattamento di fine rapporto di lavoro subordinato (TFR)
    sp15_tfr = Column(Numeric(15, 2), default=0, nullable=False)

    # D) Debiti - split by maturity
    sp16_debiti_breve = Column(Numeric(15, 2), default=0, nullable=False)  # Entro 12 mesi
    sp17_debiti_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # Oltre 12 mesi

    # E) Ratei e risconti passivi
    sp18_ratei_risconti_passivi = Column(Numeric(15, 2), default=0, nullable=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    financial_year = relationship("FinancialYear", back_populates="balance_sheet")

    @property
    def total_assets(self) -> Decimal:
        """Total Assets (Totale Attivo - TA)"""
        return (
            self.sp01_crediti_soci +
            self.sp02_immob_immateriali +
            self.sp03_immob_materiali +
            self.sp04_immob_finanziarie +
            self.sp05_rimanenze +
            self.sp06_crediti_breve +
            self.sp07_crediti_lungo +
            self.sp08_attivita_finanziarie +
            self.sp09_disponibilita_liquide +
            self.sp10_ratei_risconti_attivi
        )

    @property
    def total_equity(self) -> Decimal:
        """Total Equity (Capitale Netto - CN / Patrimonio Netto)"""
        return (
            self.sp11_capitale +
            self.sp12_riserve +
            self.sp13_utile_perdita
        )

    @property
    def total_liabilities(self) -> Decimal:
        """Total Liabilities (Totale Passivo - TP)"""
        return (
            self.total_equity +
            self.sp14_fondi_rischi +
            self.sp15_tfr +
            self.sp16_debiti_breve +
            self.sp17_debiti_lungo +
            self.sp18_ratei_risconti_passivi
        )

    @property
    def fixed_assets(self) -> Decimal:
        """Fixed Assets (Attivo Fisso / Immobilizzazioni - AF)"""
        return (
            self.sp02_immob_immateriali +
            self.sp03_immob_materiali +
            self.sp04_immob_finanziarie
        )

    @property
    def current_assets(self) -> Decimal:
        """Current Assets (Attivo Corrente - AC)"""
        return (
            self.sp05_rimanenze +
            self.sp06_crediti_breve +
            self.sp07_crediti_lungo +
            self.sp08_attivita_finanziarie +
            self.sp09_disponibilita_liquide
        )

    @property
    def current_liabilities(self) -> Decimal:
        """Current Liabilities (Passivo Corrente - PC)"""
        return self.sp16_debiti_breve

    @property
    def total_debt(self) -> Decimal:
        """Total Debt (Debiti Totali - DBT)"""
        return self.sp16_debiti_breve + self.sp17_debiti_lungo

    @property
    def working_capital_net(self) -> Decimal:
        """Net Working Capital (Capitale Circolante Netto - CCN)"""
        return self.current_assets - self.current_liabilities

    def is_balanced(self, tolerance: Decimal = Decimal("0.01")) -> bool:
        """Check if balance sheet equation is satisfied: Assets = Equity + Liabilities"""
        return abs(self.total_assets - self.total_liabilities) <= tolerance

    def __repr__(self):
        return f"<BalanceSheet(id={self.id}, year_id={self.financial_year_id}, TA={self.total_assets})>"


class IncomeStatement(Base):
    """
    Income Statement (Conto Economico - CE)

    All monetary values stored as Decimal for precision
    Line items follow Italian civil code structure (art. 2425 c.c.)
    """
    __tablename__ = "income_statements"

    id = Column(Integer, primary_key=True, index=True)
    financial_year_id = Column(Integer, ForeignKey("financial_years.id"), nullable=False, unique=True)

    # === A) VALORE DELLA PRODUZIONE ===

    # A.1) Ricavi delle vendite e delle prestazioni
    ce01_ricavi_vendite = Column(Numeric(15, 2), default=0, nullable=False)

    # A.2) Variazioni delle rimanenze di prodotti in corso di lavorazione, semilavorati e finiti
    ce02_variazioni_rimanenze = Column(Numeric(15, 2), default=0, nullable=False)

    # A.3) Variazioni dei lavori in corso su ordinazione
    ce03_lavori_interni = Column(Numeric(15, 2), default=0, nullable=False)

    # A.4) Incrementi di immobilizzazioni per lavori interni
    # A.5) Altri ricavi e proventi
    ce04_altri_ricavi = Column(Numeric(15, 2), default=0, nullable=False)

    # === B) COSTI DELLA PRODUZIONE ===

    # B.6) Per materie prime, sussidiarie, di consumo e di merci
    ce05_materie_prime = Column(Numeric(15, 2), default=0, nullable=False)

    # B.7) Per servizi
    ce06_servizi = Column(Numeric(15, 2), default=0, nullable=False)

    # B.8) Per godimento di beni di terzi
    ce07_godimento_beni = Column(Numeric(15, 2), default=0, nullable=False)

    # B.9) Per il personale
    ce08_costi_personale = Column(Numeric(15, 2), default=0, nullable=False)

    # B.10) Ammortamenti e svalutazioni
    ce09_ammortamenti = Column(Numeric(15, 2), default=0, nullable=False)

    # B.11) Variazioni delle rimanenze di materie prime
    ce10_var_rimanenze_mat_prime = Column(Numeric(15, 2), default=0, nullable=False)

    # B.12) Accantonamenti per rischi
    ce11_accantonamenti = Column(Numeric(15, 2), default=0, nullable=False)

    # B.13) Altri accantonamenti
    # B.14) Oneri diversi di gestione
    ce12_oneri_diversi = Column(Numeric(15, 2), default=0, nullable=False)

    # === C) PROVENTI E ONERI FINANZIARI ===

    # C.15) Proventi da partecipazioni
    ce13_proventi_partecipazioni = Column(Numeric(15, 2), default=0, nullable=False)

    # C.16) Altri proventi finanziari
    ce14_altri_proventi_finanziari = Column(Numeric(15, 2), default=0, nullable=False)

    # C.17) Interessi e altri oneri finanziari
    ce15_oneri_finanziari = Column(Numeric(15, 2), default=0, nullable=False)

    # C.17-bis) Utili e perdite su cambi
    ce16_utili_perdite_cambi = Column(Numeric(15, 2), default=0, nullable=False)

    # === D) RETTIFICHE DI VALORE DI ATTIVITÀ FINANZIARIE ===
    ce17_rettifiche_attivita_fin = Column(Numeric(15, 2), default=0, nullable=False)

    # === E) PROVENTI E ONERI STRAORDINARI ===
    ce18_proventi_straordinari = Column(Numeric(15, 2), default=0, nullable=False)
    ce19_oneri_straordinari = Column(Numeric(15, 2), default=0, nullable=False)

    # === IMPOSTE ===
    ce20_imposte = Column(Numeric(15, 2), default=0, nullable=False)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    financial_year = relationship("FinancialYear", back_populates="income_statement")

    @property
    def production_value(self) -> Decimal:
        """Production Value (Valore della Produzione - VP)"""
        return (
            self.ce01_ricavi_vendite +
            self.ce02_variazioni_rimanenze +
            self.ce03_lavori_interni +
            self.ce04_altri_ricavi
        )

    @property
    def production_cost(self) -> Decimal:
        """Production Cost (Costi della Produzione - COPRO)"""
        return (
            self.ce05_materie_prime +
            self.ce06_servizi +
            self.ce07_godimento_beni +
            self.ce08_costi_personale +
            self.ce09_ammortamenti +
            self.ce10_var_rimanenze_mat_prime +
            self.ce11_accantonamenti +
            self.ce12_oneri_diversi
        )

    @property
    def ebitda(self) -> Decimal:
        """
        EBITDA (Margine Operativo Lordo - MOL)
        Earnings Before Interest, Taxes, Depreciation, and Amortization
        """
        return self.production_value - (
            self.ce05_materie_prime +
            self.ce06_servizi +
            self.ce07_godimento_beni +
            self.ce08_costi_personale +
            self.ce10_var_rimanenze_mat_prime +
            self.ce11_accantonamenti +
            self.ce12_oneri_diversi
        )

    @property
    def ebit(self) -> Decimal:
        """EBIT (Risultato Operativo - RO)"""
        return self.production_value - self.production_cost

    @property
    def financial_result(self) -> Decimal:
        """Net Financial Result"""
        return (
            self.ce13_proventi_partecipazioni +
            self.ce14_altri_proventi_finanziari -
            self.ce15_oneri_finanziari +
            self.ce16_utili_perdite_cambi
        )

    @property
    def extraordinary_result(self) -> Decimal:
        """Net Extraordinary Result"""
        return self.ce18_proventi_straordinari - self.ce19_oneri_straordinari

    @property
    def profit_before_tax(self) -> Decimal:
        """Profit Before Tax (Risultato prima delle imposte)"""
        return (
            self.ebit +
            self.financial_result +
            self.ce17_rettifiche_attivita_fin +
            self.extraordinary_result
        )

    @property
    def net_profit(self) -> Decimal:
        """Net Profit/Loss (Utile/Perdita Netto - UTILE)"""
        return self.profit_before_tax - self.ce20_imposte

    @property
    def revenue(self) -> Decimal:
        """Revenue from sales (Fatturato - FATT)"""
        return self.ce01_ricavi_vendite

    def __repr__(self):
        return f"<IncomeStatement(id={self.id}, year_id={self.financial_year_id}, Revenue={self.revenue}, NP={self.net_profit})>"
