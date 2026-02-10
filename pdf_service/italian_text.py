"""
Italian text constants for PDF report generation.
All labels, section titles, boilerplate text, and descriptions.
"""

# Report title and headers
REPORT_TITLE = "RELAZIONE DI ANALISI INDICI & RATING"
REPORT_SUBTITLE = "Analisi Finanziaria Completa"

# Cover page
COVER_PREPARED_BY = "Analisi elaborata dal sistema XBRL Budget"
COVER_DATE_PREFIX = "Data elaborazione:"
COVER_YEARS_PREFIX = "Anni di analisi:"

# Section titles
SECTION_COMPANY_DATA = "DATI IMPRESA"
SECTION_INTRODUCTION = "INTRODUZIONE"
SECTION_DASHBOARD = "DASHBOARD"
SECTION_ASSET_COMPOSITION = "COMPOSIZIONE DELL'ATTIVO E DEL PASSIVO"
SECTION_INCOME_MARGINS = "MARGINI DI REDDITO"
SECTION_STRUCTURAL_ANALYSIS = "ANALISI STRUTTURALE"
SECTION_RATIOS = "INDICI FINANZIARI"
SECTION_ALTMAN = "ALTMAN Z-SCORE"
SECTION_EM_SCORE = "EM-SCORE"
SECTION_FGPMI = "RATING FGPMI"
SECTION_CASHFLOW = "INDICI DI CASH FLOW"
SECTION_BALANCE_SHEET = "STATO PATRIMONIALE"
SECTION_INCOME_STATEMENT = "CONTO ECONOMICO"
SECTION_RECLASSIFIED_BS = "STATO PATRIMONIALE RICLASSIFICATO"
SECTION_RECLASSIFIED_IS = "CONTO ECONOMICO RICLASSIFICATO"
SECTION_CASHFLOW_STATEMENT = "RENDICONTO FINANZIARIO"
SECTION_NOTES = "NOTE METODOLOGICHE"
SECTION_BREAK_EVEN = "BREAK EVEN POINT"

# Company data labels
COMPANY_NAME = "Ragione Sociale"
COMPANY_TAX_ID = "Codice Fiscale / P.IVA"
COMPANY_SECTOR = "Settore di Attivita"
COMPANY_ANALYSIS_YEARS = "Anni di Analisi"

# Sector names
SECTOR_NAMES = {
    1: "Industria",
    2: "Commercio",
    3: "Servizi",
    4: "Autotrasporti",
    5: "Immobiliare",
    6: "Edilizia",
}

# Introduction text
INTRODUCTION_TEXT = """La presente relazione fornisce un'analisi completa della situazione \
economico-finanziaria dell'impresa, basata sui bilanci depositati e sulle \
proiezioni elaborate.

L'analisi si articola nelle seguenti sezioni:

1. Dashboard di sintesi con indicatori chiave di rischio creditizio
2. Composizione patrimoniale e analisi strutturale
3. Margini di reddito e variazioni interannuali
4. Indici finanziari dettagliati per categoria
5. Modelli di scoring: Altman Z-Score, EM-Score e FGPMI
6. Analisi di Cash Flow
7. Appendici con i prospetti contabili completi

Gli indicatori sono calcolati secondo i principi contabili italiani (OIC) \
e le metodologie di analisi finanziaria comunemente accettate nel sistema \
bancario italiano."""

# Dashboard labels
DASHBOARD_SUBTITLE = "Indicatori Chiave di Rischio"
DASHBOARD_ALTMAN_LABEL = "Altman Z-Score"
DASHBOARD_FGPMI_LABEL = "Rating FGPMI"
DASHBOARD_EM_SCORE_LABEL = "EM-Score"

# Altman classifications
ALTMAN_SAFE = "Zona di Sicurezza"
ALTMAN_GRAY = "Zona d'Ombra"
ALTMAN_DISTRESS = "Zona di Rischio"

# Balance Sheet line labels (Italian civil code structure)
BS_LABELS = {
    "sp01": "A) Crediti verso soci",
    "sp02": "B.I) Immobilizzazioni immateriali",
    "sp03": "B.II) Immobilizzazioni materiali",
    "sp04": "B.III) Immobilizzazioni finanziarie",
    "sp05": "C.I) Rimanenze",
    "sp06": "C.II) Crediti entro 12 mesi",
    "sp07": "C.II) Crediti oltre 12 mesi",
    "sp08": "C.III) Attivita finanziarie",
    "sp09": "C.IV) Disponibilita liquide",
    "sp10": "D) Ratei e risconti attivi",
    "sp11": "A.I) Capitale",
    "sp12": "A.II-VII) Riserve",
    "sp13": "A.IX) Utile (Perdita) d'esercizio",
    "sp14": "B) Fondi per rischi e oneri",
    "sp15": "C) Trattamento di fine rapporto",
    "sp16": "D) Debiti entro 12 mesi",
    "sp17": "D) Debiti oltre 12 mesi",
    "sp18": "E) Ratei e risconti passivi",
}

BS_AGGREGATE_LABELS = {
    "total_assets": "TOTALE ATTIVO",
    "fixed_assets": "Totale Immobilizzazioni",
    "current_assets": "Totale Attivo Corrente",
    "total_equity": "Totale Patrimonio Netto",
    "total_debt": "Totale Debiti",
    "total_liabilities": "TOTALE PASSIVO",
}

# Income Statement line labels
IS_LABELS = {
    "ce01": "A.1) Ricavi delle vendite",
    "ce02": "A.2) Variazioni rimanenze prod.",
    "ce03": "A.3) Variazioni lavori in corso",
    "ce03a": "A.4) Incrementi immobilizzazioni",
    "ce04": "A.5) Altri ricavi e proventi",
    "ce05": "B.6) Materie prime e consumo",
    "ce06": "B.7) Servizi",
    "ce07": "B.8) Godimento beni di terzi",
    "ce08": "B.9) Costo del personale",
    "ce09": "B.10) Ammortamenti e svalutazioni",
    "ce10": "B.11) Var. rimanenze mat. prime",
    "ce11": "B.12) Accantonamenti per rischi",
    "ce11b": "B.13) Altri accantonamenti",
    "ce12": "B.14) Oneri diversi di gestione",
    "ce13": "C.15) Proventi da partecipazioni",
    "ce14": "C.16) Altri proventi finanziari",
    "ce15": "C.17) Interessi e oneri finanz.",
    "ce16": "C.17bis) Utili/perdite su cambi",
    "ce17": "D) Rettifiche attivita finanz.",
    "ce18": "E) Proventi straordinari",
    "ce19": "E) Oneri straordinari",
    "ce20": "Imposte sul reddito",
}

IS_AGGREGATE_LABELS = {
    "production_value": "VALORE DELLA PRODUZIONE",
    "production_cost": "COSTI DELLA PRODUZIONE",
    "ebitda": "EBITDA (M.O.L.)",
    "ebit": "EBIT (Risultato Operativo)",
    "financial_result": "Risultato Finanziario",
    "profit_before_tax": "Risultato prima delle imposte",
    "net_profit": "UTILE (PERDITA) NETTO",
}

# Reclassified Balance Sheet labels
RECLASSIFIED_BS_LABELS = {
    "fixed_assets": "ATTIVO FISSO (Immobilizzazioni)",
    "sp02": "  Immobilizzazioni Immateriali",
    "sp03": "  Immobilizzazioni Materiali",
    "sp04": "  Immobilizzazioni Finanziarie",
    "current_assets": "ATTIVO CORRENTE",
    "sp05": "  Rimanenze",
    "sp06": "  Crediti a breve",
    "sp07": "  Crediti a lungo",
    "sp08": "  Attivita finanziarie correnti",
    "sp09": "  Disponibilita liquide",
    "sp10": "Ratei e risconti attivi",
    "sp01": "Crediti verso soci",
    "total_assets": "TOTALE ATTIVO",
    "total_equity": "PATRIMONIO NETTO",
    "sp11": "  Capitale sociale",
    "sp12": "  Riserve",
    "sp13": "  Utile (Perdita) d'esercizio",
    "sp14": "Fondi per rischi e oneri",
    "sp15": "TFR",
    "sp17": "Debiti a medio/lungo termine",
    "sp16": "Debiti a breve termine",
    "sp18": "Ratei e risconti passivi",
    "total_liabilities": "TOTALE PASSIVO",
}

# Ratio category names
RATIO_CATEGORIES = {
    "working_capital": "Analisi Strutturale (Margini)",
    "coverage": "Indici di Solidita",
    "liquidity": "Indici di Liquidita",
    "turnover": "Indici di Rotazione",
    "activity": "Indici di Durata",
    "profitability": "Indici di Redditivita",
    "extended_profitability": "Indici di Redditivita Estesi",
    "efficiency": "Indici di Efficienza",
    "solvency": "Indici di Solvibilita",
    "break_even": "Break Even Point",
}

# Individual ratio labels
RATIO_LABELS = {
    # Working Capital
    "ccln": ("Capitale Circolante Lordo Netto", "[LI+LD+RD]"),
    "ccn": ("Capitale Circolante Netto", "[LI+LD+RD]-PC"),
    "ms": ("Margine di Struttura", "CN-AF"),
    "mt": ("Margine di Tesoreria", "[LI+LD]-PC"),
    # Liquidity
    "current_ratio": ("Indice di Liquidita Corrente", "(LI+LD+RD)/PC"),
    "quick_ratio": ("Indice Secco di Liquidita", "(LI+LD)/PC"),
    "acid_test": ("Acid Test Ratio", "(LI+LD+AF_Fin)/PC"),
    # Solvency
    "autonomy_index": ("Indice di Autonomia Finanziaria", "CN/TA"),
    "leverage_ratio": ("Indice di Indebitamento", "AF/CN"),
    "debt_to_equity": ("Rapporto Debiti / Patrimonio Netto", "DBT/CN"),
    "debt_to_production": ("Rapporto Debiti / Valore Produzione", "DBT/VP"),
    # Coverage
    "fixed_assets_coverage_with_equity_and_ltdebt": (
        "Copertura Immob. con Fonti Durevoli", "(CN+PF)/AF"),
    "fixed_assets_coverage_with_equity": (
        "Copertura Immob. con Capitale Proprio", "CN/AF"),
    "independence_from_third_parties": (
        "Indipendenza dai Terzi", "CN/(PC+PF)"),
    # Turnover
    "inventory_turnover": ("Turnover del Magazzino", "CO/RD"),
    "receivables_turnover": ("Turnover dei Crediti", "RIC/LD"),
    "payables_turnover": ("Turnover dei Debiti", "(CO+AC+ODG)/PC"),
    "working_capital_turnover": ("Turnover del CCN", "RIC/CCN"),
    "total_assets_turnover": ("Turnover Attivita Totali", "RIC/TA"),
    # Activity
    "asset_turnover": ("Rotazione Attivo Totale", "RIC/TA"),
    "inventory_turnover_days": ("Durata Magazzino", "360/TdM"),
    "receivables_turnover_days": ("Durata Crediti", "360/TdC"),
    "payables_turnover_days": ("Durata Debiti", "360/TdD"),
    "working_capital_days": ("Durata CCN", "360/TdCCN"),
    "cash_conversion_cycle": ("Ciclo di Conversione del Denaro", "DMAG+DCRED-DDEB"),
    # Profitability
    "roe": ("ROE - Redditivita Cap. Proprio", "RN/CN"),
    "roi": ("ROI - Redditivita Cap. Investito", "MON/TA"),
    "ros": ("ROS - Redditivita delle Vendite", "RN/RIC"),
    "rod": ("ROD - Costo del Denaro", "OF/(PC+PF)"),
    "ebitda_margin": ("EBITDA Margin", "MOL/RIC"),
    "ebit_margin": ("EBIT Margin", "MON/RIC"),
    "net_margin": ("Net Margin", "RN/RIC"),
    # Extended Profitability
    "spread": ("Spread (ROI - ROD)", "(ROI-ROD)"),
    "financial_leverage_effect": ("Leva Finanziaria", "(PC+PF)/CN"),
    "ebitda_on_sales": ("MOL su Vendite", "MOL/RIC"),
    "financial_charges_on_revenue": ("Oneri Finanziari su Fatturato", "OF/RIC"),
    # Efficiency
    "revenue_per_employee_cost": ("Rendimento Dipendenti", "RIC/CL"),
    "revenue_per_materials_cost": ("Rendimento Materie", "RIC/CO"),
    # Break Even
    "fixed_costs": ("Costi Fissi", "CF"),
    "variable_costs": ("Costi Variabili", "CV"),
    "contribution_margin": ("Margine di Contribuzione", "RIC-CV"),
    "contribution_margin_percentage": ("% Margine Contribuzione", "MdC/RIC"),
    "break_even_revenue": ("Ricavi BEP", "CF/%MdC"),
    "safety_margin": ("Margine di Sicurezza", "1-(BEP/RIC)"),
    "operating_leverage": ("Leva Operativa", "MdC/MON"),
    "fixed_cost_multiplier": ("Moltiplicatore Costi Fissi", "1/%MdC"),
}

# Cash flow labels
CF_LABELS = {
    "total_operating_cashflow": "Flusso di Cassa Operativo",
    "total_investing_cashflow": "Flusso di Cassa da Investimenti",
    "total_financing_cashflow": "Flusso di Cassa da Finanziamenti",
    "total_cashflow": "Variazione Netta di Cassa",
    "cash_beginning": "Disponibilita Liquide Iniziali",
    "cash_ending": "Disponibilita Liquide Finali",
}

# Notes / disclaimer
NOTES_TEXT = """NOTE METODOLOGICHE

I dati presentati nella presente relazione sono elaborati sulla base dei \
bilanci depositati dall'impresa e delle proiezioni formulate dall'utente.

MODELLI DI SCORING UTILIZZATI:

1. Altman Z-Score: Modello predittivo del rischio di insolvenza. \
Per le imprese manifatturiere si utilizza il modello a 5 componenti; \
per le altre imprese il modello a 4 componenti (Z'-Score).

2. EM-Score: Mappatura dello Z-Score su scala di rating AAA-D, \
calibrata sul modello a 4 componenti. Per le imprese manifatturiere \
viene ricalcolato lo Z-Score con la formula dei servizi.

3. FGPMI: Rating basato sul modello del Fondo di Garanzia per le PMI. \
Utilizza 7 indicatori con soglie settoriali e prevede un bonus \
di +5 punti per fatturato superiore a 500.000 euro.

INDICI FINANZIARI:

Gli indici sono calcolati secondo le formule standard dell'analisi \
finanziaria italiana, utilizzando le voci di bilancio codificate \
secondo l'art. 2424 e 2425 del Codice Civile.

I costi sono ripartiti in fissi (40%) e variabili (60%) per il \
calcolo del Break Even Point, salvo diversa specificazione nelle \
ipotesi di budget.

LIMITAZIONI:

L'analisi si basa su dati contabili che possono non riflettere \
pienamente la situazione economica reale dell'impresa. I valori \
previsionali sono soggetti a incertezza e dipendono dalla \
realizzazione delle ipotesi formulate."""
