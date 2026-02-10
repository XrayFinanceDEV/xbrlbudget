# XBRL PCI Taxonomy → IV CEE Schema
## Complete Reconciliation Guide

**Version:** 2.0  
**Date:** February 2, 2026  
**Purpose:** Mapping XBRL PCI 2018-11-04 (itcc-ci) elements to Italian IV CEE balance sheet and income statement structure  
**Target Audience:** Financial data architects, XBRL implementation specialists, financial software developers

---

## 1. Introduction

### 1.1 Scope

This document defines the complete reconciliation between:
- **XBRL PCI Taxonomy 2018-11-04** (itcc-ci namespace) - structured financial reporting standard
- **IV CEE Schema** - Italian Civil Code balance sheet (Stato Patrimoniale) and income statement (Conto Economico) structure

**Coverage:**
- Balance Sheet (SP) with hierarchical detail (sp01-sp18 and sub-items)
- Income Statement (CE) with all cost and revenue line items
- Calculation rules and aggregation formulas
- Validation logic and balance verification

**Out of Scope:**
- Cash flow statements (optional under D.Lgs. 139/2015)
- Comprehensive notes to financial statements (Nota Integrativa)
- Segment reporting or management commentary

### 1.2 Regulatory Context

The PCI 2018-11-04 taxonomy was adopted in Italy on **March 1, 2019** following D.Lgs. 139/2015 (transposition of EU Directive 2013/34/EU). It supersedes all previous Italian XBRL taxonomies.

**Applicable Companies:**
- All Italian joint-stock companies (S.p.A.)
- Limited liability companies (S.r.l.)
- Other entities filing financial statements with Italian Register of Enterprises (Registro Imprese)

**Three Reporting Formats:**
1. **Ordinario** - Full detail (standard format)
2. **Abbreviato** - Simplified format for SMEs (Art. 2435-bis)
3. **Micro** - Ultra-simplified for micro-entities (Art. 2435-bis)

---

## 2. XBRL PCI Taxonomy Structure

### 2.1 Taxonomy Organization

The XBRL PCI 2018-11-04 taxonomy is organized into:

| Component | Description |
|-----------|-------------|
| **Main schema** | `itcc-ci-2018-11-04.xsd` - Core financial reporting concepts |
| **Label file** | `itcc-ci-2018-11-04-lab-it.xml` - Italian human-readable descriptions |
| **Definition linkbase** | `itcc-ci-2018-11-04-def.xml` - Hierarchical relationships |
| **Calculation linkbase** | `itcc-ci-2018-11-04-cal.xml` - Aggregation formulas |
| **Presentation linkbase** | `itcc-ci-2018-11-04-pre.xml` - Display order |

**Namespace:** `http://www.xbrl.it/2018-11-04/itcc-ci`  
**Prefix:** `itcc-ci:`

### 2.2 Concept Naming Convention

All XBRL PCI concepts follow the pattern:

```
itcc-ci:ConceptNameInCamelCase
```

Examples:
- `itcc-ci:ShareCapital` (Capitale Sociale)
- `itcc-ci:IntangibleAssets` (Immobilizzazioni Immateriali)
- `itcc-ci:TradePayablesCurrent` (Debiti verso fornitori a breve)

### 2.3 Key Characteristics of PCI Taxonomy

**Dimensional Structure:**
- Uses abstract vs. concrete concepts
- Supports multiple dimensions (e.g., current vs. non-current)
- Allows company type variations (Ordinario, Abbreviato, Micro)

**Calculation Rules:**
- Parent-child aggregation formulas built into taxonomy
- Example: `Assets = FixedAssets + CurrentAssets`
- Automatic validation of balance sheet equation

**Localization:**
- All labels in Italian
- Supports EUR currency (implicit)
- Company context metadata

---

## 3. Balance Sheet (Stato Patrimoniale) – Complete Mapping

### 3.1 IV CEE Balance Sheet Structure – Assets (Attivo)

The IV CEE organizes assets into five sections:

```
ATTIVO (Assets)
├─ A) Crediti verso soci per versamenti ancora dovuti
├─ B) Immobilizzazioni (Fixed Assets)
│  ├─ I – Immobilizzazioni immateriali (Intangible)
│  ├─ II – Immobilizzazioni materiali (Tangible)
│  └─ III – Immobilizzazioni finanziarie (Financial)
├─ C) Attivo circolante (Current Assets)
│  ├─ I – Rimanenze (Inventories)
│  ├─ II – Crediti (Receivables)
│  ├─ III – Attività finanziarie non immobilizzate (Current financial assets)
│  └─ IV – Disponibilità liquide (Cash & equivalents)
└─ D) Ratei e risconti (Accruals & deferrals)
```

### 3.2 Detailed XBRL → IV CEE Mapping – Assets

#### Section A: Crediti verso soci per versamenti ancora dovuti (Credits from members for outstanding payments)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A** | Credits from members for outstanding payments | `itcc-ci:CreditTowardsMemberForOutstandingPayment` | Subscribed but uncalled capital |
| A.1 | – Part called | Sub-component of above (if separately identified) | May be embedded in parent element |
| A.2 | – Part to be called | Uncalled portion | Not separately coded in standard taxonomy |
| **Total A** | Total credits (A) | Aggregate of A.1 + A.2 | Reconciles to single XBRL element |

**Calculation Formula:**
```
A (IV CEE) = itcc-ci:CreditTowardsMemberForOutstandingPayment
```

**Validation:**
- Must be ≥ 0 (cannot be negative)
- Typically applicable only to joint-stock companies with called but unpaid capital

---

#### Section B.I: Immobilizzazioni immateriali (Intangible fixed assets)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.I** | Intangible fixed assets | `itcc-ci:IntangibleAssets` | Net of accumulated amortization |
| | – Goodwill | `itcc-ci:Goodwill` | Sub-component |
| | – Patents, trademarks, software | `itcc-ci:Patents`, `itcc-ci:CopyrightAndIntellectualPropertyRights` | Sub-components |
| | – Capitalized development costs | `itcc-ci:CapitalizedExpenses` | Sub-component |
| | – Other intangible assets | `itcc-ci:OtherIntangibleAssets` | Sub-component |

**Calculation Formula:**
```
B.I (IV CEE) = itcc-ci:IntangibleAssets
            = Goodwill + Patents + Capitalized Expenses + Other Intangibles
            (net of accumulated amortization)
```

**Validation:**
- Net value (gross amount – accumulated amortization)
- Must be ≥ 0
- Breakdown in notes to financial statements

---

#### Section B.II: Immobilizzazioni materiali (Tangible fixed assets)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.II** | Tangible fixed assets (net) | `itcc-ci:TangibleAssets` | Includes all tangible property |
| | – Land & buildings | `itcc-ci:LandBuildings` | Usually not depreciated (land) |
| | – Plant & machinery | `itcc-ci:PlantAndMachinery` | Production equipment |
| | – Other tangible assets | `itcc-ci:OtherTangibleFixedAssets` | Vehicles, furniture, etc. |
| | Less: Accumulated depreciation | `itcc-ci:AccumulatedDepreciationTangibleAssets` | Deducted to get net value |

**Calculation Formula:**
```
B.II (IV CEE) = itcc-ci:TangibleAssets
             = (Land + Buildings + Machinery + Other Assets) – Accumulated Depreciation
             (net value)
```

**Validation:**
- Always presented net of depreciation
- Gross amounts and depreciation disclosed in notes
- Depreciation rates follow OIC 16 (Property, Plant & Equipment)

---

#### Section B.III: Immobilizzazioni finanziarie (Financial fixed assets)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.III** | Financial fixed assets | `itcc-ci:FinancialAssets` | Aggregate of all financial holdings |
| | **B.III.1 Equity investments** | | |
| | – In subsidiaries | `itcc-ci:InvestmentsInSubsidiaries` | >50% ownership |
| | – In associates | `itcc-ci:InvestmentsInAssociates` | 20-50% ownership |
| | – Other equity securities | `itcc-ci:OtherSecurities` | <20% holdings |
| | **B.III.2 Receivables** | | Split by maturity |
| | – – Receivables due within 12 months | `itcc-ci:LongTermLoansGiven` (current portion) | Esigibili entro es. succ. |
| | – – Receivables due beyond 12 months | `itcc-ci:LongTermLoansGiven` (non-current) | Esigibili oltre es. succ. |
| | – – From related parties | `itcc-ci:ReceivablesFromRelatedParties` | Related party loans/credits |
| | – – Other financial receivables | `itcc-ci:OtherNoncurrentReceivables` | Miscellaneous credits |
| | **Total Receivables** | Sum of above items | Must distinguish current/non-current |
| | **B.III.3 Other securities** | `itcc-ci:OtherSecurities` | Bonds, derivatives, other titles |
| | **B.III.4 Derivative instruments (assets)** | `itcc-ci:DerivativeAssets` | If applicable |
| **Total B.III** | Total financial fixed assets | `itcc-ci:FinancialAssets` | Aggregate |

**Calculation Formula:**
```
B.III (IV CEE) = Investments (subsidiaries + associates + other)
               + Receivables (current portion + non-current portion)
               + Other securities
               + Derivatives (if any)
```

**Maturity Split Rules:**
- Receivables due within 12 months from balance sheet date → "Esigibili entro es. succ."
- Receivables due beyond 12 months → "Esigibili oltre es. succ."
- Must total to complete receivables amount

---

#### Section C.I: Rimanenze (Inventories)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **C.I** | Inventories | `itcc-ci:Inventories` | Net of obsolescence allowance |
| | – Raw materials | `itcc-ci:RawMaterials` | Purchased inputs |
| | – Work in progress | `itcc-ci:WorkInProgress` | Partial production |
| | – Finished goods | `itcc-ci:FinishedGoods` | Ready for sale |
| | – Goods for resale | `itcc-ci:GoodsForResale` | Purchased goods held for resale |

**Calculation Formula:**
```
C.I (IV CEE) = itcc-ci:Inventories
            = Raw Materials + Work in Progress + Finished Goods + Goods for Resale
            (net of obsolescence provision)
```

**Valuation Method:**
- Cost method (FIFO, LIFO, weighted average, or standard cost) per OIC 13
- Disclosed in accounting policies
- Lower of cost or NRV (net realizable value)

---

#### Section C.II: Crediti (Receivables)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **C.II** | Current receivables | `itcc-ci:ReceivablesCurrentAssets` | All receivables < 12 months |
| | **Due within 12 months** | | Split by source |
| | – From customers | `itcc-ci:TradeReceivablesCurrent` | Trade accounts receivable |
| | – From related parties | `itcc-ci:ReceivablesFromRelatedParties` | Related party receivables |
| | – Tax credits | `itcc-ci:TaxAssets` | VAT credits, income tax recoveries |
| | – Social security bodies | `itcc-ci:ReceivablesFromGovernment` | Social security credits |
| | – Accrued income & other | `itcc-ci:OtherCurrentReceivables` | Miscellaneous receivables |
| | **Due beyond 12 months** | | Non-current classification |
| | – From customers | `itcc-ci:TradeReceivablesNonCurrent` | Long-term trade receivables |
| | – From related parties | `itcc-ci:ReceivablesFromRelatedPartiesNonCurrent` | Long-term related party credits |
| | – Other | `itcc-ci:OtherNoncurrentReceivables` | Long-term miscellaneous credits |
| **Total C.II** | Total receivables | Sum of current + non-current | Must separate by maturity |

**Calculation Formula:**
```
C.II (IV CEE) = Receivables due within 12 months
             + Receivables due beyond 12 months
             = itcc-ci:ReceivablesCurrentAssets
```

**Allowance for Doubtful Receivables:**
- Gross receivables less allowance
- Allowance logic per OIC 15

---

#### Section C.III: Attività finanziarie che non costituiscono immobilizzazioni (Current financial assets)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **C.III** | Current financial assets | `itcc-ci:CurrentSecurities` | <12 month maturity |
| | – Equity securities (current) | `itcc-ci:EquityInvestments` (current portion) | Marketable shares |
| | – Debt securities (current) | `itcc-ci:BondInvestments` | Short-term bonds |
| | – Mutual fund shares | Part of above | Investment funds |
| | – Other financial assets (current) | `itcc-ci:OtherCurrentFinancialAssets` | Repo securities, derivatives |

**Calculation Formula:**
```
C.III (IV CEE) = itcc-ci:CurrentSecurities
              = Equity Investments + Debt Securities + Other Financial Assets
```

**Valuation:**
- Fair value or amortized cost per OIC 14
- Marked-to-market for trading securities

---

#### Section C.IV: Disponibilità liquide (Cash and cash equivalents)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **C.IV** | Cash & cash equivalents | `itcc-ci:CashAndCashEquivalents` | Highly liquid assets |
| | – Bank deposits | `itcc-ci:BankDeposits` | Current accounts, savings accounts |
| | – Cash on hand | `itcc-ci:CashOnHand` | Physical currency |
| | – Money market funds | Part of above or C.III | Immediate availability |

**Calculation Formula:**
```
C.IV (IV CEE) = itcc-ci:CashAndCashEquivalents
             = Bank Deposits + Cash On Hand
```

**Definition:**
- Immediately available (no restrictions)
- No maturity or very short maturity (<3 months)

---

#### Section D: Ratei e risconti attivi (Accruals and deferrals – assets)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **D** | Accruals and deferrals (assets) | `itcc-ci:AccrualsAndDeferralsAssets` | Deferred revenue items |
| | – Interest accrued | `itcc-ci:InterestAccrued` | Interest earned but not received |
| | – Income deferred | `itcc-ci:DeferredIncome` | Prepaid income allocated over periods |
| | – Rent/lease accruals | Typically in accruals | Accrued income from leases |
| | – Other accruals | `itcc-ci:OtherAccrualsAndDeferrals` | Miscellaneous accruals |

**Calculation Formula:**
```
D (IV CEE) = itcc-ci:AccrualsAndDeferralsAssets
          = Interest Accrued + Income Deferred + Other Accruals
```

---

#### Total Assets

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **TOTAL ASSETS** | Sum of all asset sections | `itcc-ci:Assets` | sp18_A in shorthand |

**Calculation Formula:**
```
Total Assets (IV CEE) = A + B + C + D
                      = itcc-ci:Assets
```

**Where:**
- A = Credits from members
- B = Fixed assets (B.I + B.II + B.III)
- C = Current assets (C.I + C.II + C.III + C.IV)
- D = Accruals and deferrals

---

### 3.3 IV CEE Balance Sheet Structure – Liabilities & Equity (Passivo)

The IV CEE organizes liabilities and equity into five sections:

```
PASSIVO (Liabilities & Equity)
├─ A) Patrimonio netto (Equity)
│  ├─ I – Capitale (Share capital)
│  ├─ II – Riserva da soprapprezzo (Share premium)
│  ├─ III – Riserve di rivalutazione (Revaluation reserves)
│  ├─ IV – Riserva legale (Legal reserve)
│  ├─ V – Riserve statutarie (Statutory reserves)
│  ├─ VI – Altre riserve (Other reserves)
│  ├─ VII – Riserva per coperture (Hedge reserve)
│  ├─ VIII – Utili portati a nuovo (Retained earnings)
│  ├─ IX – Utile/perdita d'esercizio (Current year result)
│  └─ X – Riserva negativa per azioni proprie (Negative treasury reserve)
├─ B) Fondi per rischi e oneri (Provisions)
├─ C) Trattamento fine rapporto (Employee severance)
├─ D) Debiti (Liabilities)
│  ├─ Esigibili oltre l'esercizio successivo (Due > 12 months)
│  └─ Esigibili entro l'esercizio successivo (Due ≤ 12 months)
│     ├─ Verso banche (To banks)
│     ├─ Verso altri finanziatori (To other financiers)
│     ├─ Obbligazioni (Bonds)
│     ├─ Verso fornitori (Trade payables)
│     ├─ Tributari (Tax payables)
│     ├─ Verso istituti previdenza (Social security payables)
│     └─ Altri debiti (Other liabilities)
└─ E) Ratei e risconti (Accruals & deferrals)
```

### 3.4 Detailed XBRL → IV CEE Mapping – Liabilities & Equity

#### Section A: Patrimonio netto (Equity)

##### A.I: Capitale (Share capital)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.I** | Share capital | `itcc-ci:ShareCapital` | Subscribed and paid-in capital |

**Calculation Formula:**
```
A.I (IV CEE) = itcc-ci:ShareCapital
```

**Definition:**
- Nominal value of shares issued
- Must be fully paid (uncalled portion → Section A of assets)
- For S.r.l.: share contributions

---

##### A.II: Riserva da soprapprezzo (Share premium reserve)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.II** | Share premium reserve | `itcc-ci:SharePremiumReserve` | Amount paid above par value |

**Calculation Formula:**
```
A.II (IV CEE) = itcc-ci:SharePremiumReserve
```

**Definition:**
- Issue premium on share sales
- Legally restricted from dividend distribution in some jurisdictions
- Part of contributed capital

---

##### A.III: Riserve di rivalutazione (Revaluation reserves)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.III** | Revaluation reserves | `itcc-ci:RevaluationReserves` | From optional revaluation of fixed assets |

**Calculation Formula:**
```
A.III (IV CEE) = itcc-ci:RevaluationReserves
```

**Definition:**
- Unrealized gains from revaluation of fixed assets
- Must be separately identified
- Reversal upon asset disposal

---

##### A.IV: Riserva legale (Legal reserve)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.IV** | Legal reserve | `itcc-ci:LegalReserve` | Mandatory allocation from earnings |

**Calculation Formula:**
```
A.IV (IV CEE) = itcc-ci:LegalReserve
```

**Definition:**
- Minimum 1/20 of net profit until reaching 1/5 of capital
- Cannot be distributed as dividends (except at liquidation)
- Per Italian Civil Code Art. 2430

---

##### A.V: Riserve statutarie (Statutory reserves)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.V** | Statutory reserves | `itcc-ci:StatutoryReserve` | Per company bylaws (Articles of Association) |

**Calculation Formula:**
```
A.V (IV CEE) = itcc-ci:StatutoryReserve
```

**Definition:**
- Allocation required by company statute/bylaws
- Non-distributable per articles
- Company-specific

---

##### A.VI: Altre riserve (Other reserves)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.VI** | Other reserves | `itcc-ci:OtherReserves` | Extraordinary & discretionary allocations |
| | – Extraordinary reserves | | From extraordinary gains |
| | – Free reserves | | Retained earnings retained by choice |

**Calculation Formula:**
```
A.VI (IV CEE) = itcc-ci:OtherReserves
             = Extraordinary Reserves + Free Reserves
```

**Definition:**
- All other equity items not separately classified
- Generally distributable (unless restricted by law/bylaws)

---

##### A.VII: Riserva per coperture flussi (Hedge reserve)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.VII** | Hedge reserve | `itcc-ci:HedgeReserve` | From cash flow hedge accounting |

**Calculation Formula:**
```
A.VII (IV CEE) = itcc-ci:HedgeReserve
```

**Definition:**
- Unrealized gains/losses on cash flow hedges (OIC 11)
- Separate identification required
- Subsequently reclassified to P&L

---

##### A.VIII: Utili portati a nuovo (Retained earnings)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.VIII** | Retained earnings | `itcc-ci:RetainedEarnings` | Prior year net income retained |

**Calculation Formula:**
```
A.VIII (IV CEE) = itcc-ci:RetainedEarnings
```

**Definition:**
- Accumulated profits from prior years not distributed
- May be positive or negative (losses carried forward)

---

##### A.IX: Utile (perdita) dell'esercizio (Current year profit/loss)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.IX** | Profit or loss for the year | `itcc-ci:NetIncomeFromContinuingOperations` | Current period result |

**Calculation Formula:**
```
A.IX (IV CEE) = itcc-ci:NetIncomeFromContinuingOperations
```

**Definition:**
- Must equal bottom-line of Income Statement
- Can be positive (profit) or negative (loss)
- Subject to profit/loss allocation in subsequent period

---

##### A.X: Riserva negativa per azioni proprie (Negative treasury reserve)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.X** | Negative treasury reserve | `itcc-ci:NegativeTreasuryStockReserve` | Deduction from equity for own shares |

**Calculation Formula:**
```
A.X (IV CEE) = –itcc-ci:NegativeTreasuryStockReserve
```

**Definition:**
- When own shares held exceed original share capital allocation
- Negative equity component
- Per Italian Civil Code restrictions

---

##### Total Equity (A)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **Total A** | Total equity | Aggregate of A.I through A.X | Must be clearly subtotaled |

**Calculation Formula:**
```
Total A (IV CEE) = A.I + A.II + A.III + A.IV + A.V + A.VI + A.VII + A.VIII + A.IX + A.X
                = itcc-ci:Equity (or sum of components)
```

---

#### Section B: Fondi per rischi e oneri (Provisions for risks and charges)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B** | Provisions for risks and charges | `itcc-ci:ProvisionsForRisksAndCharges` | Aggregate of specific provisions |
| | – Litigation provisions | `itcc-ci:ProvisionForLitigations` | Uncertain legal outcomes |
| | – Warranty provisions | `itcc-ci:ProvisionForWarranties` | Product/service warranties |
| | – Restructuring provisions | `itcc-ci:ProvisionForRestructuring` | Planned operational changes |
| | – Environmental provisions | `itcc-ci:ProvisionForEnvironmental` | Remediation obligations |
| | – Decommissioning | `itcc-ci:ProvisionForDecommissioning` | Asset retirement obligations |
| | – Other provisions | `itcc-ci:ProvisionForOther` | Miscellaneous contingencies |

**Calculation Formula:**
```
B (IV CEE) = itcc-ci:ProvisionsForRisksAndCharges
          = Litigation + Warranty + Restructuring + Environmental + Other
```

**Definition (per OIC 19):**
- Obligations arising from past events
- Probable resource outflow
- Reliable estimate possible
- Distinct from accruals (contingent vs. actual liability)

---

#### Section C: Trattamento fine rapporto (Employee severance indemnity)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **C** | Employee severance indemnity (TFR) | `itcc-ci:ProvisionForEmployeeSeverance` | Accrued termination benefits |

**Calculation Formula:**
```
C (IV CEE) = itcc-ci:ProvisionForEmployeeSeverance
```

**Definition:**
- Severance pay for Italian employees
- Accumulates at 1/13.5 of gross salary per year
- Paid upon termination or transfer
- Per Italian labor law requirements

**Note:** TFR classified separately from general provisions under Italian Civil Code

---

#### Section D: Debiti (Liabilities) – With Maturity Split

Section D requires explicit separation between:
- **D.1: Debiti esigibili oltre l'esercizio successivo** (Due > 12 months from balance sheet date)
- **D.2: Debiti esigibili entro l'esercizio successivo** (Due ≤ 12 months from balance sheet date)

##### D.1: Long-term liabilities (> 12 months)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **D.1** | Long-term liabilities | `itcc-ci:NoncurrentLiabilities` | Maturity > 12 months |
| | – Bank borrowings | `itcc-ci:BorrowingsNonCurrent` | Long-term loans |
| | – Bonds payable | `itcc-ci:BondsPayable` | Issued debt securities |
| | – Other financing | `itcc-ci:OtherNoncurrentLiabilities` | Miscellaneous long-term debt |

**Calculation Formula:**
```
D.1 (IV CEE) = itcc-ci:NoncurrentLiabilities
```

---

##### D.2: Short-term liabilities (≤ 12 months) – Detailed Breakdown

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **D.2** | Short-term liabilities | `itcc-ci:CurrentLiabilities` | Maturity ≤ 12 months |
| | **D.2.a Verso banche (To banks)** | | Bank financing |
| | – Short-term loans | `itcc-ci:BorrowingsCurrent` | Current portion of loans |
| | | `itcc-ci:BorrowingsFromBanks` | From banking institutions |
| | **D.2.b Verso altri finanziatori (To other financiers)** | | Non-bank financing |
| | – Equipment financing | `itcc-ci:BorrowingsFromOtherFinanciers` | Leasing, factoring, etc. |
| | **D.2.c Obbligazioni (Bonds)** | | Issued debt securities |
| | – Current portion | `itcc-ci:BondsCurrentPortion` | Due within 12 months |
| | **D.2.d Verso fornitori (Trade payables)** | | Supplier invoices |
| | – Trade payables | `itcc-ci:TradePayables` | Amounts due to suppliers |
| | | `itcc-ci:TradePayablesCurrent` | Current/supplier credits |
| | **D.2.e Tributari (Tax liabilities)** | | Tax obligations |
| | – Income tax payable | `itcc-ci:IncomeTaxPayable` | Current period income taxes |
| | – VAT payable | `itcc-ci:VATPayable` | Value-added tax |
| | – Other tax payables | `itcc-ci:OtherTaxLiabilities` | Regional, local taxes, etc. |
| | Subtotal: Tax liabilities | `itcc-ci:TaxLiabilities` | Sum of all tax items |
| | **D.2.f Verso istituti previdenza (To social security)** | | Social security contributions |
| | – Employee withholdings | `itcc-ci:EmployeesPayroll` | IRPEF withheld from employees |
| | – Employer contributions | `itcc-ci:SocialSecurityLiabilities` | INPS, INAIL employer portions |
| | | `itcc-ci:SocialContributions` | Total social security dues |
| | **D.2.g Altri debiti (Other liabilities)** | | Miscellaneous payables |
| | – Dividends payable | `itcc-ci:DividendPayable` | Declared but unpaid dividends |
| | – Accrued expenses | `itcc-ci:AccruedExpenses` | Accrued supplier expenses |
| | – Other current payables | `itcc-ci:OtherCurrentLiabilities` | Miscellaneous current liabilities |

**Calculation Formula (D.2):**
```
D.2 (IV CEE) = D.2.a + D.2.b + D.2.c + D.2.d + D.2.e + D.2.f + D.2.g
            = itcc-ci:CurrentLiabilities
            = Bank + Other Financiers + Bonds + Suppliers + Taxes + Social Security + Other
```

**Key Maturity Rules:**
- If liability matures within 12 months → D.2 (current)
- If liability matures after 12 months → D.1 (non-current)
- Current portion of long-term debt → reclassified to D.2

---

#### Section E: Ratei e risconti (Accruals and deferrals – liabilities)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **E** | Accruals and deferrals (liabilities) | `itcc-ci:AccrualsAndDeferralsLiabilities` | Deferred expense items |
| | – Interest payable | `itcc-ci:InterestPayable` | Accrued but unpaid interest |
| | – Deferred income | `itcc-ci:DeferredIncome` | Advance receipts allocated over periods |
| | – Rent/lease accruals | Typically in accruals | Accrued rent/lease obligations |
| | – Other accruals | `itcc-ci:OtherAccrualsAndDeferrals` | Miscellaneous accruals |

**Calculation Formula:**
```
E (IV CEE) = itcc-ci:AccrualsAndDeferralsLiabilities
          = Interest Payable + Deferred Income + Other Accruals
```

---

#### Total Liabilities & Equity

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **TOTAL LIABILITIES & EQUITY** | Sum of all liability & equity sections | `itcc-ci:LiabilitiesAndEquity` | sp18_P in shorthand |

**Calculation Formula:**
```
Total Liabilities & Equity (IV CEE) = A + B + C + D.1 + D.2 + E
                                    = itcc-ci:LiabilitiesAndEquity
                                    = Total Assets (must balance)
```

---

### 3.5 Balance Sheet Validation Rules

**Fundamental Equation:**
```
itcc-ci:Assets = itcc-ci:LiabilitiesAndEquity
```

**Tolerance:** ±€1.00 (rounding differences)

**Sectional Checks:**

1. **Fixed Assets Subtotal:**
   ```
   B (total) = B.I + B.II + B.III
   ```

2. **Current Assets Subtotal:**
   ```
   C (total) = C.I + C.II + C.III + C.IV
   ```

3. **Total Assets:**
   ```
   Total Assets = A + B + C + D
   ```

4. **Total Equity:**
   ```
   A (total) = A.I + A.II + ... + A.X
   ```

5. **Current Liabilities Detail:**
   ```
   D.2 (total) = D.2.a + D.2.b + D.2.c + D.2.d + D.2.e + D.2.f + D.2.g
   ```

6. **Total Liabilities & Equity:**
   ```
   Total L&E = A + B + C + D.1 + D.2 + E
   ```

---

## 4. Income Statement (Conto Economico) – Complete Mapping

### 4.1 IV CEE Income Statement Structure

The IV CEE organizes the income statement into five sections:

```
INCOME STATEMENT
├─ A) Valore della produzione (Value of production)
│  ├─ 1) Ricavi delle vendite e prestazioni (Revenues)
│  ├─ 2) Variazioni rimanenze (Changes in inventories)
│  ├─ 3) Variazioni lavori in corso (Changes in WIP)
│  ├─ 4) Incrementi immobilizzazioni (Self-constructed fixed assets)
│  └─ 5) Altri ricavi e proventi (Other revenue)
│     Total value of production
├─ B) Costi della produzione (Cost of production)
│  ├─ 6) Materie prime (Raw materials)
│  ├─ 7) Servizi (Services)
│  ├─ 8) Godimento beni terzi (Use of third-party assets)
│  ├─ 9) Personale (Personnel costs)
│  ├─ 10) Ammortamenti (Depreciation & amortization)
│  ├─ 11) Variazioni rimanenze materie (Changes in material inventories)
│  ├─ 12) Accantonamenti rischi (Provisions for risks)
│  ├─ 13) Altri accantonamenti (Other provisions)
│  └─ 14) Oneri diversi (Miscellaneous operating charges)
│     Total cost of production
├─ C) Proventi e oneri finanziari (Financial income & expense)
│  ├─ 15) Proventi da partecipazioni (Dividend income)
│  ├─ 16) Altri proventi finanziari (Other financial income)
│  ├─ 17) Interessi e oneri finanziari (Interest & financial charges)
│  └─ 17-bis) Utili/perdite su cambi (Foreign exchange gains/losses)
│     Total financial items
├─ D) Rettifiche di valore attività finanziarie (Fair value adjustments)
│  ├─ 18) Rivalutazioni (Revaluations)
│  └─ 19) Svalutazioni (Impairments)
│     Total fair value adjustments
└─ E) Proventi e oneri straordinari (Extraordinary items)
   ├─ 20) Proventi straordinari (Extraordinary gains)
   └─ 21) Oneri straordinari (Extraordinary charges)
      Total extraordinary items

RESULT BEFORE TAX (A – B + C + D + E)
22) Imposte (Income tax)
NET INCOME (result before tax – taxes)
```

### 4.2 Detailed XBRL → IV CEE Mapping – Income Statement

#### Section A: Valore della produzione (Value of production)

##### A.1: Ricavi delle vendite e prestazioni (Revenues from sales and services)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.1** | Revenues from sales and services | `itcc-ci:RevenuesFromSalesOfGoods` + `itcc-ci:RevenuesFromServices` | Gross revenues (before returns/discounts) |

**Calculation Formula:**
```
A.1 (IV CEE) = itcc-ci:RevenuesFromSalesOfGoods
            + itcc-ci:RevenuesFromServices
```

**Definition:**
- Sale of goods manufactured/purchased
- Service revenues
- Gross amount (before deductions)
- Per OIC 12

---

##### A.2: Variazioni rimanenze prodotti in corso, semilavorati e finiti (Changes in inventory of work in progress and finished goods)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.2** | Changes in work-in-progress & finished goods | `itcc-ci:IncreaseDecreaseWorkInProgressFinishedGoods` | Ending - Beginning inventory |

**Calculation Formula:**
```
A.2 (IV CEE) = Ending Inventory (WIP + Finished Goods) 
            – Beginning Inventory (WIP + Finished Goods)
            = itcc-ci:IncreaseDecreaseWorkInProgressFinishedGoods
```

**Sign Convention:**
- Increase in inventory → Negative (reduces production value)
- Decrease in inventory → Positive (increases production value)

---

##### A.3: Variazioni lavori in corso su ordinazione (Changes in contract work in progress)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.3** | Changes in work-in-progress on customer orders | `itcc-ci:IncreaseDecreaseContractWorkInProgress` | For construction/projects |

**Calculation Formula:**
```
A.3 (IV CEE) = Ending Contract WIP – Beginning Contract WIP
            = itcc-ci:IncreaseDecreaseContractWorkInProgress
```

**Applicability:**
- Companies performing long-term contracts
- Construction, engineering projects
- Usually zero for manufacturers/services

---

##### A.4: Incrementi di immobilizzazioni per lavori interni (Capitalized internally developed assets)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.4** | Capitalized internally developed fixed assets | `itcc-ci:IncreaseFixedAssetsDueToInternalWork` | Self-construction of assets |

**Calculation Formula:**
```
A.4 (IV CEE) = Cost of internally developed fixed assets
            = itcc-ci:IncreaseFixedAssetsDueToInternalWork
```

**Definition:**
- Capitalized cost of self-constructed assets (software, machinery, etc.)
- Must meet capitalization criteria
- Per OIC 16

---

##### A.5: Altri ricavi e proventi (Other revenues and income)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A.5** | Other revenues and income | `itcc-ci:OtherRevenuesAndIncome` | Non-operating revenues |
| | – Rental income | Component of above | Lease revenue |
| | – Insurance recoveries | Component of above | Claims settlements |
| | – Gains on asset sales | Component of above | Non-ordinary disposals |
| | – Other miscellaneous income | Component of above | Sundry revenues |

**Calculation Formula:**
```
A.5 (IV CEE) = itcc-ci:OtherRevenuesAndIncome
```

---

##### Total A: Valore della produzione (Total value of production)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **Total A** | Total value of production | `itcc-ci:ValueOfProduction` | Sum A.1 to A.5 |

**Calculation Formula:**
```
Total A = A.1 + A.2 + A.3 + A.4 + A.5
        = itcc-ci:ValueOfProduction
```

---

#### Section B: Costi della produzione (Cost of production)

##### B.6: Materie prime, sussidiarie, di consumo e di merci (Materials and supplies)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.6** | Raw materials, supplies, goods purchased | `itcc-ci:CostOfRawMaterialsAndConsumables` | Inventory purchases/usage |

**Calculation Formula:**
```
B.6 (IV CEE) = itcc-ci:CostOfRawMaterialsAndConsumables
            = Cost of Raw Materials + Supplies + Purchased Goods
```

**Definition:**
- Cost of materials consumed in production
- Purchased finished goods for resale
- Includes direct and indirect materials
- Per OIC 12

---

##### B.7: Servizi (Services)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.7** | Services | `itcc-ci:CostOfServices` | Outside services |
| | – Transport | Component | Delivery, logistics |
| | – Utilities | Component | Electricity, gas, water |
| | – Maintenance | Component | Repairs, upkeep |
| | – Professional fees | Component | Legal, accounting, consulting |
| | – Travel & accommodation | Component | Employee business travel |
| | – Insurance | Component | General liability, property, etc. |

**Calculation Formula:**
```
B.7 (IV CEE) = itcc-ci:CostOfServices
```

---

##### B.8: Godimento di beni di terzi (Use of third-party assets)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.8** | Lease and rental costs | `itcc-ci:LeaseAndRentalCosts` | Operating leases |
| | – Equipment leasing | Component | Machinery, vehicles, IT |
| | – Real estate rental | Component | Buildings, land |

**Calculation Formula:**
```
B.8 (IV CEE) = itcc-ci:LeaseAndRentalCosts
```

**IFRS 16 Note:**
- Under OIC (Italian standards), operating leases are expensed
- IFRS 16 would capitalize right-of-use assets (not applicable here)

---

##### B.9: Personale (Personnel costs)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.9** | Personnel costs | `itcc-ci:CostOfPersonnel` | All employee-related costs |
| | – Salaries and wages | Component | Base compensation |
| | – Social security contributions | Component | INPS, INAIL, healthcare |
| | – Employee severance (TFR) | Separate item in notes | Accrual for termination |

**Calculation Formula:**
```
B.9 (IV CEE) = itcc-ci:CostOfPersonnel
            = Salaries + Social Security + Other Personnel Costs
```

**Mandatory Disclosure:**
```
Of which: Severance accrual (TFR) = [specific amount]
```

---

##### B.10: Ammortamenti e svalutazioni (Depreciation, amortization, and impairments)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.10** | Total depreciation & amortization | | Aggregate of B.10a-d |
| | **B.10.a** | Amortization of intangible assets | `itcc-ci:AmortizationOfIntangibleAssets` | Per OIC 16 |
| | **B.10.b** | Depreciation of tangible assets | `itcc-ci:DepreciationOfTangibleAssets` | Per OIC 16 |
| | **B.10.c** | Impairment of fixed assets | `itcc-ci:ImpairmentOfFixedAssets` | One-time write-downs |
| | **B.10.d** | Impairment of receivables | `itcc-ci:ImpairmentOfReceivables` | Allowance for doubtful accounts |

**Calculation Formula:**
```
B.10 (IV CEE) = B.10.a + B.10.b + B.10.c + B.10.d
             = Intangible Amortization
             + Tangible Depreciation
             + Fixed Asset Impairments
             + Receivable Impairments
```

---

##### B.11: Variazioni rimanenze materie prime, sussidiarie, di consumo e merci (Changes in raw material inventory)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.11** | Changes in raw material inventory | `itcc-ci:DecreaseIncreaseRawMaterialsInventory` | Ending - Beginning |

**Calculation Formula:**
```
B.11 (IV CEE) = Beginning Inventory (Materials) 
             – Ending Inventory (Materials)
             = itcc-ci:DecreaseIncreaseRawMaterialsInventory
```

**Sign Convention:**
- Decrease in inventory (used up) → Positive (adds to cost)
- Increase in inventory (buildup) → Negative (reduces cost)

---

##### B.12: Accantonamenti per rischi (Provisions for risks)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.12** | Provisions for risks | `itcc-ci:ProvisionForRisks` | Charges to income statement |

**Calculation Formula:**
```
B.12 (IV CEE) = itcc-ci:ProvisionForRisks
```

**Definition:**
- New provisions or increases to existing provisions for contingencies
- Expensed in current period
- Differs from balance sheet disclosure (accumulated amount)

---

##### B.13: Altri accantonamenti (Other provisions)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.13** | Other provisions | `itcc-ci:OtherProvisions` | Miscellaneous provisions |
| | – Warranty provisions | Component | Product warranties |
| | – Restructuring charges | Component | Reorganization costs |
| | – Environmental remediation | Component | Contamination cleanup |

**Calculation Formula:**
```
B.13 (IV CEE) = itcc-ci:OtherProvisions
```

---

##### B.14: Oneri diversi di gestione (Miscellaneous operating charges)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **B.14** | Miscellaneous operating charges | `itcc-ci:OtherOperatingExpenses` | Non-classified expenses |
| | – Donations | Component | Charitable gifts |
| | – Subscriptions & memberships | Component | Professional associations |
| | – Penalties & fines | Component | Tax/regulatory penalties |
| | – Losses on minor items | Component | Scrap, obsolete goods |

**Calculation Formula:**
```
B.14 (IV CEE) = itcc-ci:OtherOperatingExpenses
```

---

##### Total B: Costi della produzione (Total cost of production)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **Total B** | Total cost of production | `itcc-ci:CostOfProduction` | Sum B.6 to B.14 |

**Calculation Formula:**
```
Total B = B.6 + B.7 + B.8 + B.9 + B.10 + B.11 + B.12 + B.13 + B.14
        = itcc-ci:CostOfProduction
```

---

##### Difference A – B: Operating Profit

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **A – B** | Difference (Operating profit/loss) | `itcc-ci:OperatingProfitLoss` | EBIT equivalent |

**Calculation Formula:**
```
A – B = itcc-ci:ValueOfProduction – itcc-ci:CostOfProduction
      = itcc-ci:OperatingProfitLoss
```

---

#### Section C: Proventi e oneri finanziari (Financial income and expense)

##### C.15: Proventi da partecipazioni (Dividend and participation income)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **C.15** | Income from equity investments | `itcc-ci:IncomeFromEquityInvestments` | Dividends & distributions |

**Calculation Formula:**
```
C.15 (IV CEE) = itcc-ci:IncomeFromEquityInvestments
```

---

##### C.16: Altri proventi finanziari (Other financial income)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **C.16** | Other financial income | `itcc-ci:OtherFinancialIncome` | Interest, lease income, etc. |
| | – Interest income | Component | Bank interest, loans given |
| | – Lease income | Component | Finance lease revenues |
| | – Gains on derivatives | Component | Forward contracts, options |

**Calculation Formula:**
```
C.16 (IV CEE) = itcc-ci:OtherFinancialIncome
```

---

##### C.17: Interessi e altri oneri finanziari (Interest and other financial charges)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **C.17** | Interest and other financial charges | `itcc-ci:InterestAndOtherFinancialCharges` | Cost of financing |
| | – Interest on bank loans | Component | Bank financing cost |
| | – Interest on bonds | Component | Debt securities cost |
| | – Bond issuance costs | Component | Underwriting, legal fees |
| | – Financial lease charges | Component | Implicit interest |

**Calculation Formula:**
```
C.17 (IV CEE) = itcc-ci:InterestAndOtherFinancialCharges
```

---

##### C.17-bis: Utili e perdite su cambi (Foreign exchange gains and losses)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **C.17-bis** | Foreign exchange gains/losses | `itcc-ci:ExchangeGainsAndLosses` | FX revaluation |

**Calculation Formula:**
```
C.17-bis (IV CEE) = itcc-ci:ExchangeGainsAndLosses
```

**Definition:**
- Realized gains/losses on foreign currency transactions
- Unrealized gains/losses on monetary items in foreign currency
- Per OIC 10

---

##### Total C: Proventi e oneri finanziari (Total financial income/expense)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **Total C** | Total financial income/expense (net) | `itcc-ci:FinancialProfitLoss` | C.15 + C.16 – C.17 ± C.17-bis |

**Calculation Formula:**
```
Total C = C.15 + C.16 – C.17 ± C.17-bis
        = itcc-ci:FinancialProfitLoss
```

**Note:** C.17 is subtracted (it's an expense); C.17-bis is added if positive (gain) or subtracted if negative (loss)

---

#### Section D: Rettifiche di valore di attività finanziarie (Fair value adjustments)

##### D.18: Rivalutazioni (Revaluations of financial assets)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **D.18** | Revaluations of financial assets | `itcc-ci:RevaluationsOfFinancialAssets` | Mark-to-market gains |
| | – Revaluation of equity investments | Component | Increase in fair value |
| | – Revaluation of securities | Component | Bond/equity appreciation |

**Calculation Formula:**
```
D.18 (IV CEE) = itcc-ci:RevaluationsOfFinancialAssets
```

---

##### D.19: Svalutazioni (Impairments of financial assets)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **D.19** | Impairments of financial assets | `itcc-ci:ImpairmentOfFinancialAssets` | Write-downs |
| | – Impairment of equity investments | Component | Decline in fair value |
| | – Impairment of securities | Component | Credit losses |

**Calculation Formula:**
```
D.19 (IV CEE) = itcc-ci:ImpairmentOfFinancialAssets
```

---

##### Total D: Fair Value Adjustments (Net)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **Total D** | Fair value adjustments (net) | `itcc-ci:FairValueGainsAndLosses` | D.18 – D.19 |

**Calculation Formula:**
```
Total D = D.18 – D.19
        = itcc-ci:FairValueGainsAndLosses
```

---

#### Section E: Proventi e oneri straordinari (Extraordinary items)

##### E.20: Proventi straordinari (Extraordinary gains)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **E.20** | Extraordinary gains | `itcc-ci:ExtraordinaryGains` | Non-recurring positive items |
| | – Gains on asset sales | Component | Sale of land, buildings |
| | – Recovery of prior years' expenses | Component | Tax refunds, legal recoveries |
| | – Insurance proceeds | Component | Claims settlements |
| | – Litigation settlements (favorable) | Component | Lawsuit wins |

**Calculation Formula:**
```
E.20 (IV CEE) = itcc-ci:ExtraordinaryGains
```

---

##### E.21: Oneri straordinari (Extraordinary charges)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **E.21** | Extraordinary charges | `itcc-ci:ExtraordinaryExpenses` | Non-recurring negative items |
| | – Losses on asset sales | Component | Disposal below book value |
| | – Prior years' adjustments | Component | Tax settlements |
| | – Litigation losses | Component | Lawsuit losses |
| | – Catastrophic losses | Component | Fires, accidents |

**Calculation Formula:**
```
E.21 (IV CEE) = itcc-ci:ExtraordinaryExpenses
```

---

##### Total E: Extraordinary Items (Net)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **Total E** | Extraordinary items (net) | `itcc-ci:ExtraordinaryProfitLoss` | E.20 – E.21 |

**Calculation Formula:**
```
Total E = E.20 – E.21
        = itcc-ci:ExtraordinaryProfitLoss
```

**Note:** Under OIC 12, extraordinary items are still separately disclosed (unlike IFRS which eliminated the concept)

---

#### Profit Before Tax

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **Profit before tax** | Result before income tax | `itcc-ci:ProfitLossBeforeTax` | (A–B)+C±D±E |

**Calculation Formula:**
```
Profit Before Tax = (A – B) + Total C + Total D + Total E
                  = Operating Profit + Financial + Fair Value + Extraordinary
                  = itcc-ci:ProfitLossBeforeTax
```

---

#### Item 22: Imposte sul reddito (Income tax)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **Item 22** | Income tax expense | `itcc-ci:IncomeTaxExpense` | Current + deferred + anticipated |
| | – Current tax | Component | Tax on current year earnings |
| | – Deferred tax | Component | Future tax from timing differences |
| | – Anticipated tax | Component | Prior years' adjustments |

**Calculation Formula:**
```
Item 22 (IV CEE) = itcc-ci:IncomeTaxExpense
                = Current Tax + Deferred Tax – Anticipated Tax
```

---

#### Net Income (Profit/Loss for the Year)

| IV CEE Item | Description | XBRL PCI Element | Notes |
|---|---|---|---|
| **Net Income** | Profit or loss for the year | `itcc-ci:NetIncomeFromContinuingOperations` | Bottom-line result |

**Calculation Formula:**
```
Net Income = Profit Before Tax – Income Tax Expense
          = itcc-ci:ProfitLossBeforeTax – itcc-ci:IncomeTaxExpense
          = itcc-ci:NetIncomeFromContinuingOperations
```

**Reconciliation to Balance Sheet:**
```
Net Income (CE) = A.IX (SP – Current year profit/loss)
                (must match exactly)
```

---

## 5. Comprehensive Validation Rules

### 5.1 Balance Sheet Equation

**Primary Equation:**
```
itcc-ci:Assets = itcc-ci:LiabilitiesAndEquity

Tolerance: ±€1.00 (for rounding)
```

### 5.2 Detailed Sectional Validations

#### Assets Hierarchy
```
Total Assets = A + B + C + D
where:
  A = Credits from members
  B = B.I + B.II + B.III (fixed assets)
  C = C.I + C.II + C.III + C.IV (current assets)
  D = Accruals and deferrals
```

#### Liabilities & Equity Hierarchy
```
Total Liabilities & Equity = Equity + Liabilities
where:
  Equity = A.I + A.II + ... + A.X
  Liabilities = B + C + D.1 + D.2 + E
  
  D = D.1 + D.2
  D.2 = D.2.a + D.2.b + D.2.c + D.2.d + D.2.e + D.2.f + D.2.g
```

#### Income Statement Flow
```
Net Income = (A – B) + C + D + E – Taxes
where:
  A = Value of production
  B = Cost of production
  C = Financial income/expense
  D = Fair value adjustments
  E = Extraordinary items
  Taxes = Income tax expense
```

### 5.3 Cross-Sheet Validations

**Income Statement to Balance Sheet:**
```
Net Income (CE) ≡ A.IX (SP – Profit/loss for year)

Must reconcile before statement publication
```

**Material Changes Tracking:**
```
Retained Earnings (Year 2) = Retained Earnings (Year 1)
                           + Net Income (Year 1)
                           – Dividends Paid (Year 1)
```

---

## 6. Implementation Guidelines

### 6.1 Data Extraction from XBRL Instance

When extracting from an XBRL instance document:

1. **Identify context**: Balance date, company identifier, currency
2. **Extract by concept**: Use XML parsing to retrieve value for each itcc-ci: element
3. **Apply calculations**: Sum components per formulas above
4. **Populate IV CEE schema**: Map extracted values to sp01–sp18 (SP) or CE line items
5. **Validate**: Check balance sheet equation and sectional aggregates
6. **Report**: Generate IV CEE formatted output

### 6.2 Mapping Architecture

**Recommended structure:**

```python
class XBRLtoIVCEEMapper:
    """Map XBRL PCI 2018-11-04 to IV CEE prospetti."""
    
    # Define mapping dictionary
    XBRL_TO_IVCEE_MAPPING = {
        "itcc-ci:CreditTowardsMemberForOutstandingPayment": "sp01",
        "itcc-ci:IntangibleAssets": "sp02",
        "itcc-ci:TangibleAssets": "sp03",
        "itcc-ci:FinancialAssets": "sp04",
        "itcc-ci:Inventories": "sp05",
        "itcc-ci:ReceivablesCurrentAssets": "sp06",
        "itcc-ci:CurrentSecurities": "sp07",
        "itcc-ci:CashAndCashEquivalents": "sp08",
        "itcc-ci:AccrualsAndDeferralsAssets": "sp09",
        # ... continue for all elements
    }
    
    def extract_balance_sheet(self, xbrl_instance_data):
        """Extract and map XBRL to IV CEE SP."""
        ivcee_data = {}
        for xbrl_element, sp_code in self.XBRL_TO_IVCEE_MAPPING.items():
            value = xbrl_instance_data.get(xbrl_element)
            ivcee_data[sp_code] = value
        return ivcee_data
    
    def validate_balance(self, ivcee_data):
        """Verify balance sheet equation."""
        assets = ivcee_data.get("sp18_A", 0)
        liabilities_equity = ivcee_data.get("sp18_P", 0)
        difference = abs(assets - liabilities_equity)
        return difference <= 1.00
```

### 6.3 Database Schema Alignment

Ensure your financial_analysis database schema includes fields for:

- **Balance Sheet Fields**: sp01–sp18 (Decimal/Numeric type)
- **Income Statement Fields**: CE.A1–E.21 (Decimal/Numeric type)
- **Metadata**: fiscal_year, company_id, source, extraction_date
- **Validation**: balance_verified, confidence_score

---

## 7. Summary of Key XBRL Concepts

### 7.1 Most Frequently Used Elements

| Frequency | Element | IV CEE Code |
|-----------|---------|-------------|
| **Essential** | `itcc-ci:Assets` | sp18_A |
| **Essential** | `itcc-ci:LiabilitiesAndEquity` | sp18_P |
| **Essential** | `itcc-ci:ShareCapital` | sp10 |
| **Essential** | `itcc-ci:NetIncomeFromContinuingOperations` | sp12 |
| **High** | `itcc-ci:TangibleAssets` | sp03 |
| **High** | `itcc-ci:IntangibleAssets` | sp02 |
| **High** | `itcc-ci:CurrentLiabilities` | sp16 |
| **High** | `itcc-ci:TradePayables` | sp16d |
| **Medium** | `itcc-ci:ReceivablesCurrentAssets` | sp06 |
| **Medium** | `itcc-ci:ProvisionsForRisksAndCharges` | sp13 |

### 7.2 Dimensional Concepts

Several XBRL elements support dimensions to distinguish:

- **Current vs. Non-current**: e.g., `BorrowingsCurrent` vs. `BorrowingsNonCurrent`
- **By party**: e.g., `ReceivablesFromRelatedParties` vs. `OtherReceivables`
- **By purpose**: e.g., `LegalReserve` vs. `StatutoryReserve`

---

## 8. References

**Official Documentation:**
- XBRL Italia: https://it.xbrl.org/ (Tassonomia PCI 2018-11-04)
- AgID: https://www.agid.gov.it/it/dati/formati-aperti/xbrl
- Register of Enterprises: https://www.registroimprese.it/

**Italian Accounting Standards:**
- OIC (Organismo Italiano di Contabilità) – All standards at https://www.fondazioneoic.eu/
  - OIC 11 – Cash flow statement
  - OIC 12 – Revenue and income recognition
  - OIC 13 – Inventories
  - OIC 14 – Financial assets and liabilities
  - OIC 15 – Receivables and payables
  - OIC 16 – Property, plant & equipment; intangible assets
  - OIC 19 – Provisions, contingencies, commitments

**EU Legislation:**
- Directive 2013/34/EU – Accounting directives for member states
- D.Lgs. 139/2015 – Italian transposition decree

---

**Document Version:** 2.0  
**Last Updated:** February 2, 2026  
**Status:** Complete Reference  
**Target Users:** Financial software architects, XBRL implementation teams, financial data specialists
