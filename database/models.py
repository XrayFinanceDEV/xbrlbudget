"""
SQLAlchemy ORM Models for Financial Analysis Application
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric, Text, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import relationship
from database.db import Base
from config import Sector
import enum


class Company(Base):
    """
    Company master data (DATI_IMPRESA)
    """
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint('user_id', 'tax_id', name='uq_company_user_tax_id'),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), nullable=True, index=True)  # Supabase user UUID
    name = Column(String(255), nullable=False, index=True)
    tax_id = Column(String(20), nullable=True, index=True)  # Partita IVA / Codice Fiscale
    sector = Column(Integer, nullable=False)  # 1-6 (Sector enum)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    financial_years = relationship("FinancialYear", back_populates="company", cascade="all, delete-orphan")
    budget_scenarios = relationship("BudgetScenario", back_populates="company", cascade="all, delete-orphan")

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
    period_months = Column(Integer, nullable=True, default=None)  # NULL/12 = full year, 1-11 = partial
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = relationship("Company", back_populates="financial_years")
    balance_sheet = relationship("BalanceSheet", back_populates="financial_year", uselist=False, cascade="all, delete-orphan")
    income_statement = relationship("IncomeStatement", back_populates="financial_year", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<FinancialYear(id={self.id}, company_id={self.company_id}, year={self.year}, period_months={self.period_months})>"


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

    # DETAILED BREAKDOWN - Crediti verso soci
    sp01a_parte_richiamata = Column(Numeric(15, 2), default=0, nullable=False)  # A.1) Parte già richiamata
    sp01b_parte_da_richiamare = Column(Numeric(15, 2), default=0, nullable=False)  # A.2) Parte da richiamare

    # B) Immobilizzazioni
    # B.I) Immobilizzazioni immateriali
    sp02_immob_immateriali = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Immobilizzazioni immateriali
    sp02a_costi_impianto = Column(Numeric(15, 2), default=0, nullable=False)  # 1) Costi di impianto e ampliamento
    sp02b_costi_sviluppo = Column(Numeric(15, 2), default=0, nullable=False)  # 2) Costi di sviluppo
    sp02c_brevetti = Column(Numeric(15, 2), default=0, nullable=False)  # 3) Diritti di brevetto industriale e utilizzo opere ingegno
    sp02d_concessioni = Column(Numeric(15, 2), default=0, nullable=False)  # 4) Concessioni, licenze, marchi e diritti simili
    sp02e_avviamento = Column(Numeric(15, 2), default=0, nullable=False)  # 5) Avviamento
    sp02f_immob_in_corso = Column(Numeric(15, 2), default=0, nullable=False)  # 6) Immobilizzazioni in corso e acconti
    sp02g_altre_immob_imm = Column(Numeric(15, 2), default=0, nullable=False)  # 7) Altre

    # B.II) Immobilizzazioni materiali
    sp03_immob_materiali = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Immobilizzazioni materiali
    sp03a_terreni_fabbricati = Column(Numeric(15, 2), default=0, nullable=False)  # 1) Terreni e fabbricati
    sp03b_impianti_macchinari = Column(Numeric(15, 2), default=0, nullable=False)  # 2) Impianti e macchinario
    sp03c_attrezzature = Column(Numeric(15, 2), default=0, nullable=False)  # 3) Attrezzature industriali e commerciali
    sp03d_altri_beni = Column(Numeric(15, 2), default=0, nullable=False)  # 4) Altri beni
    sp03e_immob_in_corso = Column(Numeric(15, 2), default=0, nullable=False)  # 5) Immobilizzazioni in corso e acconti

    # B.III) Immobilizzazioni finanziarie
    sp04_immob_finanziarie = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Immobilizzazioni finanziarie
    sp04a_partecipazioni = Column(Numeric(15, 2), default=0, nullable=False)  # 1) Partecipazioni
    sp04b_crediti_immob_breve = Column(Numeric(15, 2), default=0, nullable=False)  # 2) Crediti - Entro esercizio successivo
    sp04c_crediti_immob_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # 2) Crediti - Oltre esercizio successivo
    sp04d_altri_titoli = Column(Numeric(15, 2), default=0, nullable=False)  # 3) Altri titoli
    sp04e_strumenti_derivati_attivi = Column(Numeric(15, 2), default=0, nullable=False)  # 4) Strumenti finanziari derivati attivi

    # C) Attivo circolante
    # C.I) Rimanenze
    sp05_rimanenze = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Rimanenze
    sp05a_materie_prime = Column(Numeric(15, 2), default=0, nullable=False)  # 1) Materie prime, sussidiarie e di consumo
    sp05b_prodotti_in_corso = Column(Numeric(15, 2), default=0, nullable=False)  # 2) Prodotti in corso di lavorazione e semilavorati
    sp05c_lavori_in_corso = Column(Numeric(15, 2), default=0, nullable=False)  # 3) Lavori in corso su ordinazione
    sp05d_prodotti_finiti = Column(Numeric(15, 2), default=0, nullable=False)  # 4) Prodotti finiti e merci
    sp05e_acconti = Column(Numeric(15, 2), default=0, nullable=False)  # 5) Acconti

    # C.II) Crediti - split by maturity
    sp06_crediti_breve = Column(Numeric(15, 2), default=0, nullable=False)  # Entro 12 mesi
    sp07_crediti_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # Oltre 12 mesi

    # DETAILED BREAKDOWN - Crediti breve termine (by source)
    sp06a_crediti_clienti_breve = Column(Numeric(15, 2), default=0, nullable=False)  # 1) verso clienti
    sp06b_crediti_controllate_breve = Column(Numeric(15, 2), default=0, nullable=False)  # 2) verso imprese controllate
    sp06c_crediti_collegate_breve = Column(Numeric(15, 2), default=0, nullable=False)  # 3) verso imprese collegate
    sp06d_crediti_controllanti_breve = Column(Numeric(15, 2), default=0, nullable=False)  # 4) verso imprese controllanti
    sp06e_crediti_tributari_breve = Column(Numeric(15, 2), default=0, nullable=False)  # 5) crediti tributari
    sp06f_imposte_anticipate_breve = Column(Numeric(15, 2), default=0, nullable=False)  # 5-bis) imposte anticipate
    sp06g_crediti_altri_breve = Column(Numeric(15, 2), default=0, nullable=False)  # 5-ter) verso altri

    # DETAILED BREAKDOWN - Crediti lungo termine (by source)
    sp07a_crediti_clienti_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # 1) verso clienti
    sp07b_crediti_controllate_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # 2) verso imprese controllate
    sp07c_crediti_collegate_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # 3) verso imprese collegate
    sp07d_crediti_controllanti_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # 4) verso imprese controllanti
    sp07e_crediti_tributari_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # 5) crediti tributari
    sp07f_imposte_anticipate_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # 5-bis) imposte anticipate
    sp07g_crediti_altri_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # 5-ter) verso altri

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

    # DETAILED BREAKDOWN - Patrimonio Netto (Riserve)
    sp12a_riserva_sovrapprezzo = Column(Numeric(15, 2), default=0, nullable=False)  # II - Riserva da soprapprezzo azioni
    sp12b_riserve_rivalutazione = Column(Numeric(15, 2), default=0, nullable=False)  # III - Riserve di rivalutazione
    sp12c_riserva_legale = Column(Numeric(15, 2), default=0, nullable=False)  # IV - Riserva legale
    sp12d_riserve_statutarie = Column(Numeric(15, 2), default=0, nullable=False)  # V - Riserve statutarie
    sp12e_altre_riserve = Column(Numeric(15, 2), default=0, nullable=False)  # VI - Altre riserve
    sp12f_riserva_copertura_flussi = Column(Numeric(15, 2), default=0, nullable=False)  # VII - Riserva per operazioni di copertura dei flussi finanziari attesi
    sp12g_utili_perdite_portati = Column(Numeric(15, 2), default=0, nullable=False)  # VIII - Utili (perdite) portati a nuovo
    sp12h_riserva_neg_azioni_proprie = Column(Numeric(15, 2), default=0, nullable=False)  # X - Riserva negativa per azioni proprie in portafoglio

    # A.IX) Utile/Perdita dell'esercizio
    sp13_utile_perdita = Column(Numeric(15, 2), default=0, nullable=False)

    # B) Fondi per rischi e oneri
    sp14_fondi_rischi = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Fondi per rischi e oneri
    sp14a_fondi_trattamento_quiescenza = Column(Numeric(15, 2), default=0, nullable=False)  # 1) per trattamento di quiescenza
    sp14b_fondi_imposte = Column(Numeric(15, 2), default=0, nullable=False)  # 2) per imposte, anche differite
    sp14c_strumenti_derivati_passivi = Column(Numeric(15, 2), default=0, nullable=False)  # 3) strumenti finanziari derivati passivi
    sp14d_altri_fondi = Column(Numeric(15, 2), default=0, nullable=False)  # 4) altri

    # C) Trattamento di fine rapporto di lavoro subordinato (TFR)
    sp15_tfr = Column(Numeric(15, 2), default=0, nullable=False)

    # D) Debiti - split by maturity AND by nature (financial vs operating)
    # Aggregate fields (for backward compatibility)
    sp16_debiti_breve = Column(Numeric(15, 2), default=0, nullable=False)  # Entro 12 mesi
    sp17_debiti_lungo = Column(Numeric(15, 2), default=0, nullable=False)  # Oltre 12 mesi

    # DETAILED BREAKDOWN - Financial debts (for financing cashflow)
    sp16a_debiti_banche_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17a_debiti_banche_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16b_debiti_altri_finanz_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17b_debiti_altri_finanz_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16c_debiti_obbligazioni_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17c_debiti_obbligazioni_lungo = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Operating debts (for working capital cashflow)
    sp16d_debiti_fornitori_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17d_debiti_fornitori_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16e_debiti_tributari_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17e_debiti_tributari_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16f_debiti_previdenza_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17f_debiti_previdenza_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16g_altri_debiti_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17g_altri_debiti_lungo = Column(Numeric(15, 2), default=0, nullable=False)

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
    def financial_debt_short(self) -> Decimal:
        """Short-term Financial Debt (for financing cashflow)"""
        return (
            self.sp16a_debiti_banche_breve +
            self.sp16b_debiti_altri_finanz_breve +
            self.sp16c_debiti_obbligazioni_breve
        )

    @property
    def financial_debt_long(self) -> Decimal:
        """Long-term Financial Debt (for financing cashflow)"""
        return (
            self.sp17a_debiti_banche_lungo +
            self.sp17b_debiti_altri_finanz_lungo +
            self.sp17c_debiti_obbligazioni_lungo
        )

    @property
    def financial_debt_total(self) -> Decimal:
        """Total Financial Debt (for financing cashflow)"""
        return self.financial_debt_short + self.financial_debt_long

    @property
    def operating_debt_short(self) -> Decimal:
        """Short-term Operating Debt (for working capital cashflow)"""
        return (
            self.sp16d_debiti_fornitori_breve +
            self.sp16e_debiti_tributari_breve +
            self.sp16f_debiti_previdenza_breve +
            self.sp16g_altri_debiti_breve
        )

    @property
    def operating_debt_long(self) -> Decimal:
        """Long-term Operating Debt (rare, but exists)"""
        return (
            self.sp17d_debiti_fornitori_lungo +
            self.sp17e_debiti_tributari_lungo +
            self.sp17f_debiti_previdenza_lungo +
            self.sp17g_altri_debiti_lungo
        )

    @property
    def operating_debt_total(self) -> Decimal:
        """Total Operating Debt (for working capital cashflow)"""
        return self.operating_debt_short + self.operating_debt_long

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
    ce03a_incrementi_immobilizzazioni = Column(Numeric(15, 2), default=0, nullable=False)

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
    ce08a_tfr_accrual = Column(Numeric(15, 2), default=0, nullable=False)  # TFR accrual detail ("di cui...")

    # B.10) Ammortamenti e svalutazioni
    ce09_ammortamenti = Column(Numeric(15, 2), default=0, nullable=False)

    # B.10) Split depreciation by asset type (for detailed cashflow)
    ce09a_ammort_immateriali = Column(Numeric(15, 2), default=0, nullable=False)
    ce09b_ammort_materiali = Column(Numeric(15, 2), default=0, nullable=False)
    ce09c_svalutazioni = Column(Numeric(15, 2), default=0, nullable=False)  # Other write-downs of fixed assets (c)
    ce09d_svalutazione_crediti = Column(Numeric(15, 2), default=0, nullable=False)  # Write-downs of receivables (d)

    # B.11) Variazioni delle rimanenze di materie prime
    ce10_var_rimanenze_mat_prime = Column(Numeric(15, 2), default=0, nullable=False)

    # B.12) Accantonamenti per rischi
    ce11_accantonamenti = Column(Numeric(15, 2), default=0, nullable=False)

    # B.13) Altri accantonamenti
    ce11b_altri_accantonamenti = Column(Numeric(15, 2), default=0, nullable=False)

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

    # D.18) Rivalutazioni
    ce17a_rivalutazioni = Column(Numeric(15, 2), default=0, nullable=False)

    # D.19) Svalutazioni
    ce17b_svalutazioni = Column(Numeric(15, 2), default=0, nullable=False)

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
            self.ce03a_incrementi_immobilizzazioni +
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


class BudgetScenario(Base):
    """
    Budget Scenario - contains forecast assumptions for a company
    Allows creating multiple forecast scenarios (base case, optimistic, pessimistic, etc.)
    """
    __tablename__ = "budget_scenarios"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(255), nullable=False)  # e.g., "Budget 2025-2027", "Scenario Ottimistico"
    base_year = Column(Integer, nullable=False)  # Base year for % calculations (e.g., 2024)
    scenario_type = Column(String(20), nullable=False, default="budget")  # "budget" | "infrannuale"
    period_months = Column(Integer, nullable=True)  # 1-11 for partial year (infrannuale), NULL for budget
    description = Column(Text, nullable=True)
    is_active = Column(Integer, default=1)  # 1 = active scenario, 0 = archived
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = relationship("Company", back_populates="budget_scenarios")
    assumptions = relationship("BudgetAssumptions", back_populates="scenario", cascade="all, delete-orphan")
    forecast_years = relationship("ForecastYear", back_populates="scenario", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BudgetScenario(id={self.id}, name='{self.name}', base_year={self.base_year})>"


class BudgetAssumptions(Base):
    """
    Budget Assumptions - stores % variation assumptions for forecasting
    Each row represents assumptions for one forecast year
    """
    __tablename__ = "budget_assumptions"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("budget_scenarios.id"), nullable=False)
    forecast_year = Column(Integer, nullable=False)  # e.g., 2025, 2026, 2027

    # Revenue assumptions (% vs base year)
    revenue_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)  # % change in revenue
    other_revenue_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)  # % change in other revenue

    # Cost assumptions (% vs base year)
    variable_materials_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)
    fixed_materials_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)
    variable_services_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)
    fixed_services_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)
    rent_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)  # Godimento beni terzi
    personnel_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)
    other_costs_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)  # Oneri diversi

    # Investment and working capital
    investments = Column(Numeric(15, 2), default=0, nullable=False)  # New investments
    receivables_short_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)  # Crediti breve
    receivables_long_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)  # Crediti lungo
    payables_short_growth_pct = Column(Numeric(10, 6), default=0, nullable=False)  # Debiti breve

    # Financial parameters
    interest_rate_receivables = Column(Numeric(10, 6), default=0, nullable=False)  # % on receivables
    interest_rate_payables = Column(Numeric(10, 6), default=0, nullable=False)  # % on payables

    # Tax and other parameters
    tax_rate = Column(Numeric(10, 6), default=24, nullable=False)  # IRES/IRAP tax rate %
    fixed_materials_percentage = Column(Numeric(10, 6), default=40, nullable=False)  # % of materials that are fixed costs
    fixed_services_percentage = Column(Numeric(10, 6), default=40, nullable=False)  # % of services that are fixed costs
    depreciation_rate = Column(Numeric(10, 6), default=20, nullable=False)  # Average depreciation rate %

    # Financing parameters (optional)
    financing_amount = Column(Numeric(15, 2), default=0, nullable=False)  # New financing amount
    financing_duration_years = Column(Numeric(10, 2), default=0, nullable=False)  # Loan duration in years
    financing_interest_rate = Column(Numeric(10, 6), default=0, nullable=False)  # Loan interest rate %

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    scenario = relationship("BudgetScenario", back_populates="assumptions")

    def __repr__(self):
        return f"<BudgetAssumptions(id={self.id}, scenario_id={self.scenario_id}, year={self.forecast_year})>"


class ForecastYear(Base):
    """
    Forecast Year - links to forecasted financial statements
    Similar to FinancialYear but for forecast data
    """
    __tablename__ = "forecast_years"

    id = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("budget_scenarios.id"), nullable=False)
    year = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    scenario = relationship("BudgetScenario", back_populates="forecast_years")
    balance_sheet = relationship("ForecastBalanceSheet", back_populates="forecast_year", uselist=False, cascade="all, delete-orphan")
    income_statement = relationship("ForecastIncomeStatement", back_populates="forecast_year", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ForecastYear(id={self.id}, scenario_id={self.scenario_id}, year={self.year})>"


class ForecastBalanceSheet(Base):
    """
    Forecast Balance Sheet - projected balance sheet
    Same structure as BalanceSheet but for forecast data
    """
    __tablename__ = "forecast_balance_sheets"

    id = Column(Integer, primary_key=True, index=True)
    forecast_year_id = Column(Integer, ForeignKey("forecast_years.id"), nullable=False, unique=True)

    # Same fields as BalanceSheet
    sp01_crediti_soci = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Crediti verso soci
    sp01a_parte_richiamata = Column(Numeric(15, 2), default=0, nullable=False)
    sp01b_parte_da_richiamare = Column(Numeric(15, 2), default=0, nullable=False)

    sp02_immob_immateriali = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Immobilizzazioni immateriali
    sp02a_costi_impianto = Column(Numeric(15, 2), default=0, nullable=False)
    sp02b_costi_sviluppo = Column(Numeric(15, 2), default=0, nullable=False)
    sp02c_brevetti = Column(Numeric(15, 2), default=0, nullable=False)
    sp02d_concessioni = Column(Numeric(15, 2), default=0, nullable=False)
    sp02e_avviamento = Column(Numeric(15, 2), default=0, nullable=False)
    sp02f_immob_in_corso = Column(Numeric(15, 2), default=0, nullable=False)
    sp02g_altre_immob_imm = Column(Numeric(15, 2), default=0, nullable=False)

    sp03_immob_materiali = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Immobilizzazioni materiali
    sp03a_terreni_fabbricati = Column(Numeric(15, 2), default=0, nullable=False)
    sp03b_impianti_macchinari = Column(Numeric(15, 2), default=0, nullable=False)
    sp03c_attrezzature = Column(Numeric(15, 2), default=0, nullable=False)
    sp03d_altri_beni = Column(Numeric(15, 2), default=0, nullable=False)
    sp03e_immob_in_corso = Column(Numeric(15, 2), default=0, nullable=False)

    sp04_immob_finanziarie = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Immobilizzazioni finanziarie
    sp04a_partecipazioni = Column(Numeric(15, 2), default=0, nullable=False)
    sp04b_crediti_immob_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp04c_crediti_immob_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp04d_altri_titoli = Column(Numeric(15, 2), default=0, nullable=False)
    sp04e_strumenti_derivati_attivi = Column(Numeric(15, 2), default=0, nullable=False)

    sp05_rimanenze = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Rimanenze
    sp05a_materie_prime = Column(Numeric(15, 2), default=0, nullable=False)
    sp05b_prodotti_in_corso = Column(Numeric(15, 2), default=0, nullable=False)
    sp05c_lavori_in_corso = Column(Numeric(15, 2), default=0, nullable=False)
    sp05d_prodotti_finiti = Column(Numeric(15, 2), default=0, nullable=False)
    sp05e_acconti = Column(Numeric(15, 2), default=0, nullable=False)

    sp06_crediti_breve = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Crediti breve termine
    sp06a_crediti_clienti_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp06b_crediti_controllate_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp06c_crediti_collegate_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp06d_crediti_controllanti_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp06e_crediti_tributari_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp06f_imposte_anticipate_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp06g_crediti_altri_breve = Column(Numeric(15, 2), default=0, nullable=False)

    sp07_crediti_lungo = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Crediti lungo termine
    sp07a_crediti_clienti_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp07b_crediti_controllate_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp07c_crediti_collegate_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp07d_crediti_controllanti_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp07e_crediti_tributari_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp07f_imposte_anticipate_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp07g_crediti_altri_lungo = Column(Numeric(15, 2), default=0, nullable=False)

    sp08_attivita_finanziarie = Column(Numeric(15, 2), default=0, nullable=False)
    sp09_disponibilita_liquide = Column(Numeric(15, 2), default=0, nullable=False)
    sp10_ratei_risconti_attivi = Column(Numeric(15, 2), default=0, nullable=False)
    sp11_capitale = Column(Numeric(15, 2), default=0, nullable=False)
    sp12_riserve = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Patrimonio Netto (Riserve)
    sp12a_riserva_sovrapprezzo = Column(Numeric(15, 2), default=0, nullable=False)
    sp12b_riserve_rivalutazione = Column(Numeric(15, 2), default=0, nullable=False)
    sp12c_riserva_legale = Column(Numeric(15, 2), default=0, nullable=False)
    sp12d_riserve_statutarie = Column(Numeric(15, 2), default=0, nullable=False)
    sp12e_altre_riserve = Column(Numeric(15, 2), default=0, nullable=False)
    sp12f_riserva_copertura_flussi = Column(Numeric(15, 2), default=0, nullable=False)
    sp12g_utili_perdite_portati = Column(Numeric(15, 2), default=0, nullable=False)
    sp12h_riserva_neg_azioni_proprie = Column(Numeric(15, 2), default=0, nullable=False)

    sp13_utile_perdita = Column(Numeric(15, 2), default=0, nullable=False)
    sp14_fondi_rischi = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Fondi per rischi e oneri
    sp14a_fondi_trattamento_quiescenza = Column(Numeric(15, 2), default=0, nullable=False)
    sp14b_fondi_imposte = Column(Numeric(15, 2), default=0, nullable=False)
    sp14c_strumenti_derivati_passivi = Column(Numeric(15, 2), default=0, nullable=False)
    sp14d_altri_fondi = Column(Numeric(15, 2), default=0, nullable=False)

    sp15_tfr = Column(Numeric(15, 2), default=0, nullable=False)
    sp16_debiti_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17_debiti_lungo = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Financial debts (for financing cashflow)
    sp16a_debiti_banche_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17a_debiti_banche_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16b_debiti_altri_finanz_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17b_debiti_altri_finanz_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16c_debiti_obbligazioni_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17c_debiti_obbligazioni_lungo = Column(Numeric(15, 2), default=0, nullable=False)

    # DETAILED BREAKDOWN - Operating debts (for working capital cashflow)
    sp16d_debiti_fornitori_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17d_debiti_fornitori_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16e_debiti_tributari_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17e_debiti_tributari_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16f_debiti_previdenza_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17f_debiti_previdenza_lungo = Column(Numeric(15, 2), default=0, nullable=False)
    sp16g_altri_debiti_breve = Column(Numeric(15, 2), default=0, nullable=False)
    sp17g_altri_debiti_lungo = Column(Numeric(15, 2), default=0, nullable=False)

    sp18_ratei_risconti_passivi = Column(Numeric(15, 2), default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    forecast_year = relationship("ForecastYear", back_populates="balance_sheet")

    # Reuse same properties as BalanceSheet
    @property
    def total_assets(self) -> Decimal:
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
        return (
            self.sp11_capitale +
            self.sp12_riserve +
            self.sp13_utile_perdita
        )

    @property
    def total_liabilities(self) -> Decimal:
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
        return (
            self.sp02_immob_immateriali +
            self.sp03_immob_materiali +
            self.sp04_immob_finanziarie
        )

    @property
    def current_assets(self) -> Decimal:
        return (
            self.sp05_rimanenze +
            self.sp06_crediti_breve +
            self.sp07_crediti_lungo +
            self.sp08_attivita_finanziarie +
            self.sp09_disponibilita_liquide
        )

    @property
    def current_liabilities(self) -> Decimal:
        return self.sp16_debiti_breve

    @property
    def total_debt(self) -> Decimal:
        return self.sp16_debiti_breve + self.sp17_debiti_lungo

    @property
    def financial_debt_short(self) -> Decimal:
        """Short-term Financial Debt (for financing cashflow)"""
        return (
            self.sp16a_debiti_banche_breve +
            self.sp16b_debiti_altri_finanz_breve +
            self.sp16c_debiti_obbligazioni_breve
        )

    @property
    def financial_debt_long(self) -> Decimal:
        """Long-term Financial Debt (for financing cashflow)"""
        return (
            self.sp17a_debiti_banche_lungo +
            self.sp17b_debiti_altri_finanz_lungo +
            self.sp17c_debiti_obbligazioni_lungo
        )

    @property
    def financial_debt_total(self) -> Decimal:
        """Total Financial Debt (for financing cashflow)"""
        return self.financial_debt_short + self.financial_debt_long

    @property
    def operating_debt_short(self) -> Decimal:
        """Short-term Operating Debt (for working capital cashflow)"""
        return (
            self.sp16d_debiti_fornitori_breve +
            self.sp16e_debiti_tributari_breve +
            self.sp16f_debiti_previdenza_breve +
            self.sp16g_altri_debiti_breve
        )

    @property
    def operating_debt_long(self) -> Decimal:
        """Long-term Operating Debt (rare, but exists)"""
        return (
            self.sp17d_debiti_fornitori_lungo +
            self.sp17e_debiti_tributari_lungo +
            self.sp17f_debiti_previdenza_lungo +
            self.sp17g_altri_debiti_lungo
        )

    @property
    def operating_debt_total(self) -> Decimal:
        """Total Operating Debt (for working capital cashflow)"""
        return self.operating_debt_short + self.operating_debt_long

    @property
    def working_capital_net(self) -> Decimal:
        return self.current_assets - self.current_liabilities

    def __repr__(self):
        return f"<ForecastBalanceSheet(id={self.id}, year_id={self.forecast_year_id}, TA={self.total_assets})>"


class ForecastIncomeStatement(Base):
    """
    Forecast Income Statement - projected income statement
    Same structure as IncomeStatement but for forecast data
    """
    __tablename__ = "forecast_income_statements"

    id = Column(Integer, primary_key=True, index=True)
    forecast_year_id = Column(Integer, ForeignKey("forecast_years.id"), nullable=False, unique=True)

    # Same fields as IncomeStatement
    ce01_ricavi_vendite = Column(Numeric(15, 2), default=0, nullable=False)
    ce02_variazioni_rimanenze = Column(Numeric(15, 2), default=0, nullable=False)
    ce03_lavori_interni = Column(Numeric(15, 2), default=0, nullable=False)
    ce03a_incrementi_immobilizzazioni = Column(Numeric(15, 2), default=0, nullable=False)
    ce04_altri_ricavi = Column(Numeric(15, 2), default=0, nullable=False)
    ce05_materie_prime = Column(Numeric(15, 2), default=0, nullable=False)
    ce06_servizi = Column(Numeric(15, 2), default=0, nullable=False)
    ce07_godimento_beni = Column(Numeric(15, 2), default=0, nullable=False)
    ce08_costi_personale = Column(Numeric(15, 2), default=0, nullable=False)
    ce08a_tfr_accrual = Column(Numeric(15, 2), default=0, nullable=False, comment="TFR accrual (di cui)")
    ce09_ammortamenti = Column(Numeric(15, 2), default=0, nullable=False)
    ce09a_ammort_immateriali = Column(Numeric(15, 2), default=0, nullable=False)
    ce09b_ammort_materiali = Column(Numeric(15, 2), default=0, nullable=False)
    ce09c_svalutazioni = Column(Numeric(15, 2), default=0, nullable=False)
    ce10_var_rimanenze_mat_prime = Column(Numeric(15, 2), default=0, nullable=False)
    ce11_accantonamenti = Column(Numeric(15, 2), default=0, nullable=False)
    ce12_oneri_diversi = Column(Numeric(15, 2), default=0, nullable=False)
    ce13_proventi_partecipazioni = Column(Numeric(15, 2), default=0, nullable=False)
    ce14_altri_proventi_finanziari = Column(Numeric(15, 2), default=0, nullable=False)
    ce15_oneri_finanziari = Column(Numeric(15, 2), default=0, nullable=False)
    ce16_utili_perdite_cambi = Column(Numeric(15, 2), default=0, nullable=False)
    ce17_rettifiche_attivita_fin = Column(Numeric(15, 2), default=0, nullable=False)
    ce17a_rivalutazioni = Column(Numeric(15, 2), default=0, nullable=False)
    ce17b_svalutazioni = Column(Numeric(15, 2), default=0, nullable=False)
    ce18_proventi_straordinari = Column(Numeric(15, 2), default=0, nullable=False)
    ce19_oneri_straordinari = Column(Numeric(15, 2), default=0, nullable=False)
    ce20_imposte = Column(Numeric(15, 2), default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    forecast_year = relationship("ForecastYear", back_populates="income_statement")

    # Reuse same properties as IncomeStatement
    @property
    def production_value(self) -> Decimal:
        return (
            self.ce01_ricavi_vendite +
            self.ce02_variazioni_rimanenze +
            self.ce03_lavori_interni +
            self.ce03a_incrementi_immobilizzazioni +
            self.ce04_altri_ricavi
        )

    @property
    def production_cost(self) -> Decimal:
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
        return self.production_value - self.production_cost

    @property
    def financial_result(self) -> Decimal:
        return (
            self.ce13_proventi_partecipazioni +
            self.ce14_altri_proventi_finanziari -
            self.ce15_oneri_finanziari +
            self.ce16_utili_perdite_cambi
        )

    @property
    def extraordinary_result(self) -> Decimal:
        return self.ce18_proventi_straordinari - self.ce19_oneri_straordinari

    @property
    def profit_before_tax(self) -> Decimal:
        return (
            self.ebit +
            self.financial_result +
            self.ce17_rettifiche_attivita_fin +
            self.extraordinary_result
        )

    @property
    def net_profit(self) -> Decimal:
        return self.profit_before_tax - self.ce20_imposte

    @property
    def revenue(self) -> Decimal:
        return self.ce01_ricavi_vendite

    def __repr__(self):
        return f"<ForecastIncomeStatement(id={self.id}, year_id={self.forecast_year_id}, Revenue={self.revenue}, NP={self.net_profit})>"
