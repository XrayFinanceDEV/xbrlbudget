# 📊 XBRL Budget - Financial Analysis Application

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.40+-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Sistema completo di analisi finanziaria per bilanci italiani secondo i principi contabili OIC (Organismo Italiano di Contabilità).

**🇮🇹 Italian GAAP Compliant Financial Analysis & Credit Rating System**

## Caratteristiche

### Gestione Dati
- ✅ Creazione e modifica aziende
- ✅ Gestione multi-anno (fino a 5 anni)
- ✅ Importazione da XBRL (formato italiano - tassonomie 2011-2018)
- ✅ Importazione da CSV (TEBE)
- ✅ Inserimento manuale bilanci (Stato Patrimoniale + Conto Economico)

### Analisi Finanziaria
- ✅ **Indici di Liquidità**: Current Ratio, Quick Ratio, Acid Test
- ✅ **Indici di Solvibilità**: Autonomia, Leverage, Debt/Equity
- ✅ **Indici di Redditività**: ROE, ROI, ROS, ROD, EBITDA Margin
- ✅ **Indici di Rotazione**: Asset Turnover, giorni magazzino/crediti/debiti
- ✅ **Capitale Circolante**: CCN, CCLN, MS, MT

### Modelli di Valutazione
- ✅ **Altman Z-Score**: Previsione rischio insolvenza con modelli settoriali
  - Modello manifatturiero (5 componenti)
  - Modello servizi (4 componenti)
- ✅ **Rating FGPMI**: Rating creditizio PMI (13 classi da AAA a B-)
  - 7 indicatori settoriali (V1-V7)
  - 5 modelli di settore
  - Bonus fatturato

## Installazione

### Requisiti
- Python 3.11+
- pip

### Setup

1. **Clona il repository**
   ```bash
   git clone git@github.com:XrayFinanceDEV/xbrlbudget.git
   cd xbrlbudget
   ```

2. **Crea virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Installa dipendenze**
   ```bash
   pip install -r requirements.txt
   ```

4. **Inizializza database**
   ```bash
   python -c "from database.db import init_db; init_db()"
   ```

## Utilizzo

### Avvio Applicazione Web

```bash
streamlit run app.py
```

L'applicazione sarà disponibile su `http://localhost:8501`

### Import Dati

#### Da XBRL
```python
from importers.xbrl_parser import import_xbrl_file

result = import_xbrl_file(
    file_path="bilancio.xbrl",
    create_company=True
)
```

#### Da CSV (TEBE)
```python
from importers.csv_importer import import_csv_file

result = import_csv_file(
    file_path="bilancio.csv",
    company_id=1,
    year1=2024,
    year2=2023
)
```

### Calcolo Indici

```python
from database.db import SessionLocal
from database.models import FinancialYear
from calculations.ratios import FinancialRatiosCalculator
from calculations.altman import AltmanCalculator
from calculations.rating_fgpmi import FGPMICalculator

db = SessionLocal()
fy = db.query(FinancialYear).filter(FinancialYear.year == 2024).first()

# Indici finanziari
calc = FinancialRatiosCalculator(fy.balance_sheet, fy.income_statement)
liquidity = calc.calculate_liquidity_ratios()
profitability = calc.calculate_profitability_ratios()

# Altman Z-Score
altman = AltmanCalculator(fy.balance_sheet, fy.income_statement, sector=1)
z_score = altman.calculate()

# Rating FGPMI
fgpmi = FGPMICalculator(fy.balance_sheet, fy.income_statement, sector=1)
rating = fgpmi.calculate()
```

## Struttura Progetto

```
budget/
├── app.py                          # Streamlit main app
├── config.py                       # Configuration & constants
├── requirements.txt
├── database/
│   ├── models.py                   # SQLAlchemy models
│   └── db.py                       # Database setup
├── calculations/
│   ├── base.py                     # Base calculator
│   ├── ratios.py                   # Financial ratios
│   ├── altman.py                   # Altman Z-Score
│   └── rating_fgpmi.py             # FGPMI Rating
├── importers/
│   ├── xbrl_parser.py              # XBRL importer
│   └── csv_importer.py             # CSV importer
├── ui/
│   └── pages/                      # Streamlit pages
│       ├── dati_impresa.py         # Company data
│       ├── importazione.py         # Data import
│       ├── balance_sheet.py        # Balance sheet
│       ├── income_statement.py     # Income statement
│       ├── ratios.py               # Financial ratios
│       ├── altman.py               # Altman analysis
│       ├── rating.py               # FGPMI rating
│       └── dashboard.py            # Dashboard
├── data/
│   ├── sectors.json                # Sector definitions
│   ├── rating_tables.json          # FGPMI tables
│   └── taxonomy_mapping.json       # XBRL mappings
└── tests/
    ├── test_db.py
    ├── test_calculations.py
    ├── test_fgpmi.py
    ├── test_csv_import.py
    └── test_xbrl_import.py
```

## Settori Supportati

1. **Industria** (Manufacturing)
2. **Commercio** (Commerce)
3. **Servizi** (Services)
4. **Autotrasporti** (Transport)
5. **Immobiliare** (Real Estate)
6. **Edilizia** (Construction)

## Testing

```bash
# Test database
python test_db.py

# Test calculations
python test_calculations.py

# Test FGPMI rating
python test_fgpmi.py

# Test CSV import
python test_csv_import.py

# Test XBRL import
python test_xbrl_import.py

# Test real XBRL data
python test_bkps_xbrl.py
```

## Tassonomie XBRL Supportate

- 2018-11-04 (latest)
- 2017-07-06
- 2016-11-14
- 2015-12-14
- 2014-11-17
- 2011-01-04

## Pagine Web

### 🏠 Home
Dashboard iniziale con statistiche e azioni rapide

### 🏢 Dati Impresa
Creazione e modifica anagrafica aziende

### 📥 Importazione Dati
Import da XBRL o CSV (TEBE)

### 📊 Stato Patrimoniale
Visualizzazione e modifica SP con verifica bilanciamento

### 💰 Conto Economico
Visualizzazione e modifica CE con calcolo automatico margini

### 📈 Indici Finanziari
Analisi completa con 5 categorie:
- Capitale Circolante (CCN, CCLN, MS, MT)
- Liquidità (Current, Quick, Acid Test)
- Solvibilità (Autonomia, Debt/Equity, Leverage)
- Redditività (ROE, ROI, ROS, ROD)
- Rotazione (Asset Turnover, giorni)

### ⚖️ Altman Z-Score
Valutazione rischio insolvenza con:
- Gauge chart interattivo
- Componenti dettagliate
- Trend storico
- Interpretazione

### ⭐ Rating FGPMI
Rating creditizio PMI con:
- Scala visiva 13 classi (AAA → B-)
- 7 indicatori dettagliati
- Trend storico
- Analisi rischio

### 📉 Dashboard
Panoramica completa con grafici interattivi:
- Andamento economico
- Andamento patrimoniale
- Indicatori chiave
- Valutazioni correnti

## Database

SQLite locale (`financial_analysis.db`)

**Modelli:**
- `Company`: Anagrafica aziende
- `FinancialYear`: Anni fiscali
- `BalanceSheet`: Stato Patrimoniale (22 voci)
- `IncomeStatement`: Conto Economico (20 voci)

## Export

- CSV per indici finanziari
- Report testuali per Altman e FGPMI
- Grafici interattivi (Plotly)

## Note

- Tutti i calcoli seguono i principi contabili italiani (OIC)
- Formule Altman Z-Score calibrate per settore
- Rating FGPMI secondo modello Fondo di Garanzia
- Supporto multi-anno con confronti temporali

## 📸 Screenshots

Coming soon: Dashboard, Altman Z-Score, FGPMI Rating views

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🏢 Developed By

**Xray Finance DEV**
- GitHub: [@XrayFinanceDEV](https://github.com/XrayFinanceDEV)
- Repository: [xbrlbudget](https://github.com/XrayFinanceDEV/xbrlbudget)

## 📧 Support

For issues and questions:
- Open an issue on [GitHub Issues](https://github.com/XrayFinanceDEV/xbrlbudget/issues)
- Contact: [GitHub Discussions](https://github.com/XrayFinanceDEV/xbrlbudget/discussions)

## 🙏 Acknowledgments

- Italian GAAP (OIC) standards
- XBRL International taxonomy
- Altman Z-Score research
- FGPMI (Fondo di Garanzia per le PMI) rating model

---

**Version:** 1.0.0
**Released:** January 2026
**Python:** 3.11+
**Framework:** Streamlit 1.40+
**Made with ❤️ in Italy 🇮🇹**
