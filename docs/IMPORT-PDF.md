# PDF Import Pipeline

## Overview

The PDF importer extracts Italian IV CEE balance sheet (Stato Patrimoniale) and income statement (Conto Economico) data from PDF files and persists them to the database.

There are two extraction backends. The importer selects automatically based on whether `ANTHROPIC_API_KEY` is set in the environment.

| | LLM (fast path) | Docling (fallback) |
|---|---|---|
| **Speed** | ~11s | ~133s |
| **Cost** | ~$0.01/PDF | Free |
| **Requires** | `ANTHROPIC_API_KEY` | Docling models (~2GB first run) |
| **How it works** | PyMuPDF text + Claude Haiku 4.5 | pypdfium2 + AI table structure model |

## Pipeline Flow

```
PDF file
  │
  ├─ ANTHROPIC_API_KEY set? ──► LLM path
  │                               │
  │                               ├─ 1. PyMuPDF opens PDF, scans page text for keywords
  │                               ├─ 2. Extracts text from relevant pages only (~5KB)
  │                               ├─ 3. Claude Haiku extracts SP fields (tool-use, structured output)
  │                               ├─ 4. Claude Haiku extracts CE fields (tool-use, structured output)
  │                               └─ 5. Pydantic model → Dict[str, Decimal]
  │
  └─ No API key ──────────────► Docling path
                                  │
                                  ├─ 1. pypdfium2 backend converts all pages
                                  ├─ 2. AI table structure model finds tables
                                  ├─ 3. IVCEEMapper matches row labels → sp/ce fields
                                  └─ 4. Markdown fallback if no tables found
  │
  ▼
Shared validation (both paths)
  │
  ├─ IVCEEMapper.validate_balance()  →  totale_attivo == totale_passivo?
  ├─ IVCEEMapper.validate_hierarchy() →  subtotals match component sums?
  │
  ▼
Database persistence
  │
  ├─ Company (create or lookup)
  ├─ FinancialYear (replace if exists)
  ├─ BalanceSheet (sp01-sp18)
  └─ IncomeStatement (ce01-ce20 + sub-items)
```

## LLM Path Details

### Step 1: Page Detection (`extract_relevant_pages`)

PyMuPDF (`fitz`) opens the PDF and scans each page's text for keywords.

**Primary keywords** (highly specific, only on the actual financial statement pages):
- SP: `"totale attivo"`, `"totale passivo"`
- CE: `"totale valore della produzione"`, `"differenza tra valore e costi"`

**Secondary keywords** (used only if primary finds nothing):
- SP: `"stato patrimoniale"`, `"crediti verso soci"`
- CE: `"conto economico"`, `"ricavi delle vendite"`

Matched pages are expanded by +/- 1 page to catch tables that overflow across page breaks. If nothing matches, the first 6 pages are used as a fallback.

This reduces a 43-page PDF from ~40KB of text down to ~5KB for SP and ~10KB for CE.

### Step 2-3: Claude Haiku Extraction (`_extract_with_llm`)

Two separate API calls to `claude-haiku-4-5-20251001`, one for SP and one for CE.

**Structured output via tool-use:** A Pydantic model (`BalanceSheetExtraction` / `IncomeStatementExtraction`) is converted to a JSON schema and sent as a tool definition. `tool_choice` forces the model to call it, guaranteeing structured output.

```
client.messages.create(
    model="claude-haiku-4-5-20251001",
    system=<system_prompt>,           # Italian accounting expert + extraction rules
    messages=[{text + extracted PDF pages}],
    tools=[{schema from Pydantic model}],
    tool_choice={"type": "tool", "name": "balance_sheet"},
)
```

The model returns a `tool_use` content block whose `input` is validated against the Pydantic model.

**System prompts** include:
- Italian number format rules (dots = thousands, commas = decimals, parentheses = negative)
- Field-specific mapping rules (e.g., crediti esigibili entro/oltre, reserves aggregation)
- Instruction to preserve original signs (no flipping)
- Instruction to extract current year values only (leftmost column)

**Retry logic:** Transient 500 errors are retried up to 2 times with exponential backoff (1s, 2s).

### Step 4: Type Conversion

The Pydantic model (float fields) is converted to `Dict[str, Decimal]` via `_model_to_decimal_dict()`, matching the format expected by the database persistence layer.

## Fields Extracted

### Balance Sheet (20 fields)

| Field | IV CEE Reference |
|-------|-----------------|
| `sp01_crediti_soci` | A) Crediti verso soci |
| `sp02_immob_immateriali` | B.I) Immobilizzazioni immateriali |
| `sp03_immob_materiali` | B.II) Immobilizzazioni materiali |
| `sp04_immob_finanziarie` | B.III) Immobilizzazioni finanziarie |
| `sp05_rimanenze` | C.I) Rimanenze |
| `sp06_crediti_breve` | C.II) Crediti esigibili entro |
| `sp07_crediti_lungo` | C.II) Crediti esigibili oltre |
| `sp08_attivita_finanziarie` | C.III) Attivita finanziarie non immobilizzate |
| `sp09_disponibilita_liquide` | C.IV) Disponibilita liquide |
| `sp10_ratei_risconti_attivi` | D) Ratei e risconti attivi |
| `sp11_capitale` | A.I) Capitale sociale |
| `sp12_riserve` | A.II-VIII) Sum of all reserves |
| `sp13_utile_perdita` | A.IX) Utile/perdita dell'esercizio |
| `sp14_fondi_rischi` | B) Fondi per rischi e oneri |
| `sp15_tfr` | C) TFR |
| `sp16_debiti_breve` | D) Debiti esigibili entro |
| `sp17_debiti_lungo` | D) Debiti esigibili oltre |
| `sp18_ratei_risconti_passivi` | E) Ratei e risconti passivi |
| `totale_attivo` | Totale attivo (validation only) |
| `totale_passivo` | Totale passivo (validation only) |

### Income Statement (26 fields)

| Field | IV CEE Reference |
|-------|-----------------|
| `ce01_ricavi_vendite` | A.1) Ricavi vendite e prestazioni |
| `ce02_variazioni_rimanenze` | A.2) Variazioni rimanenze prodotti |
| `ce03_lavori_interni` | A.4) Incrementi immobilizzazioni |
| `ce04_altri_ricavi` | A.5) Altri ricavi e proventi |
| `ce05_materie_prime` | B.6) Materie prime |
| `ce06_servizi` | B.7) Servizi |
| `ce07_godimento_beni` | B.8) Godimento beni terzi |
| `ce08_costi_personale` | B.9) Totale costi personale |
| `ce08a_tfr_accrual` | B.9c) TFR accrual |
| `ce09_ammortamenti` | B.10) Totale ammortamenti |
| `ce09a_ammort_immateriali` | B.10a) Ammortamento immateriali |
| `ce09b_ammort_materiali` | B.10b) Ammortamento materiali |
| `ce09c_svalutazioni` | B.10c) Altre svalutazioni |
| `ce09d_svalutazione_crediti` | B.10d) Svalutazione crediti |
| `ce10_var_rimanenze_mat_prime` | B.11) Variazioni rimanenze materie prime |
| `ce11_accantonamenti` | B.12) Accantonamenti rischi |
| `ce11b_altri_accantonamenti` | B.13) Altri accantonamenti |
| `ce12_oneri_diversi` | B.14) Oneri diversi gestione |
| `ce13_proventi_partecipazioni` | C.15) Proventi partecipazioni |
| `ce14_altri_proventi_finanziari` | C.16) Altri proventi finanziari |
| `ce15_oneri_finanziari` | C.17) Interessi e altri oneri |
| `ce16_utili_perdite_cambi` | C.17-bis) Utili/perdite cambi |
| `ce17_rettifiche_attivita_fin` | D) Rettifiche attivita finanziarie |
| `ce18_proventi_straordinari` | E.20) Proventi straordinari |
| `ce19_oneri_straordinari` | E.21) Oneri straordinari |
| `ce20_imposte` | 22) Imposte sul reddito |

## Configuration

| Setting | Location | Value |
|---------|----------|-------|
| `ANTHROPIC_API_KEY` | Environment variable or `.env` | Your API key |
| `PDF_LLM_MODEL` | `config.py` | `claude-haiku-4-5-20251001` |
| `PDF_LLM_MAX_TOKENS` | `config.py` | `4096` |

## Files

| File | Role |
|------|------|
| `importers/pdf_importer.py` | Entry point, routing, DB persistence |
| `importers/pdf_extractor_llm.py` | PyMuPDF + Claude Haiku extraction |
| `importers/pdf_mapper.py` | Docling table/markdown extraction, validation |
| `config.py` | LLM model/token constants |
| `backend/app/core/config.py` | Settings (reads `ANTHROPIC_API_KEY` from env) |

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No `ANTHROPIC_API_KEY` | Silent fallback to Docling (info log) |
| PyMuPDF can't open file | `PDFImportError` raised |
| No relevant pages found | First 6 pages used as fallback + warning |
| Anthropic API 500 error | Retried up to 2 times (1s, 2s backoff) |
| Anthropic API other error | `PDFImportError` with message |
| Balance doesn't balance | `PDFImportError` (existing validation) |
| Missing field in LLM output | Defaults to `0` via Pydantic field defaults |

## API Endpoint

```
POST /api/v1/import/pdf
Content-Type: multipart/form-data

Form fields:
  file: <pdf_file>
  company_name: "DEPI SRLU"
  fiscal_year: 2025
  sector: 2              # optional, defaults to 3 (Servizi)
```

Response includes `extraction_method: "llm" | "docling"` and `extraction_time_seconds`.
