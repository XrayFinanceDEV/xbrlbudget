# IV CEE PDF Balance Sheet Import - Technical Documentation

## Executive Summary

This document outlines the architecture and implementation strategy for adding PDF-based balance sheet import capabilities to the XBRL Budget application using **Docling**, an open-source document extraction framework from IBM.

**Goal**: Extract structured financial data from PDF balance sheets (IV CEE format) filed with Italian Chambers of Commerce and integrate them into the existing database schema.

---

## 1. Background: IV CEE Directive

### What is IV CEE?

**IV CEE (Fourth EEC Directive)** refers to the **Fourth European Economic Community Directive 78/660/EEC** (1978), which Italy transposed through Legislative Decree 127/1991. This directive established harmonized standards for drawing up financial statements across Europe.

### Italian Implementation

- **Legal Framework**: Italian Civil Code Articles 2424 (Balance Sheet) and 2425 (Income Statement)
- **Governing Body**: OIC (Organismo Italiano di Contabilità) - Italian Accounting Board
- **Balance Sheet Formats**: Two layouts defined in Directive Annexes III and IV
- **Modern Directive**: Consolidated into Directive 2013/34/EU
- **Company Types**: Ordinario (standard), Abbreviato (abbreviated), Micro (micro-entities)

### PDF Source

Italian companies file annual financial statements with the **Camera di Commercio** (Chamber of Commerce), which provides:
- Official balance sheet PDFs
- XBRL format files (already supported by this project)
- Shareholders' meeting minutes

This service will handle **PDF balance sheets** that follow the IV CEE standardized formats.

---

## 2. Docling Overview

### What is Docling?

**Docling** is an open-source document extraction framework created by IBM Research, now part of the LF AI & Data Foundation.

**Key Capabilities:**
- Advanced PDF understanding (layout, reading order, tables, formulas)
- 94%+ accuracy on financial tables (benchmarked against LlamaParse, Unstructured)
- OCR support for scanned documents
- Multi-format support (PDF, DOCX, PPTX, images, HTML)
- Structured output (JSON, Markdown, HTML, CSV)

**License**: MIT
**Repository**: https://github.com/docling-project/docling
**Documentation**: https://docling-project.github.io/docling/

### Why Docling for Financial Documents?

1. **Table Extraction**: TableFormer component converts tables → pandas DataFrames → CSV
2. **Financial Domain**: Designed for legal agreements, financial statements, invoice processing
3. **Hierarchical Structure**: Recognizes nested line items (perfect for Italian balance sheet sp16a-g debt categories)
4. **Enterprise Ready**: Used in production by financial institutions
5. **Integrations**: Built-in support for LangChain, LlamaIndex, Haystack

### Technical Requirements

- **Python**: 3.10+ (dropped 3.9 support in v2.70.0)
- **Dependencies**: `docling`, `fastapi`, `celery`, `redis`, `python-multipart`
- **Performance**: First request ~137s (model download from HuggingFace), subsequent requests <5s
- **GPU Support**: Highly recommended for production (significantly faster)
- **Models**: Automatically downloaded and cached locally (~2GB)

---

## 3. Architecture Options

### Pattern A: Simple Synchronous API (Development)

```
Client → FastAPI Endpoint → Docling Converter → JSON Response
```

**Pros:**
- Simple implementation
- Immediate feedback
- Good for testing/development

**Cons:**
- Blocks API during processing (30-120s for typical PDFs)
- First request very slow (model download)
- Not scalable
- Poor user experience

**Use Case**: Development, testing, low-volume scenarios

---

### Pattern B: Async Queue Worker ⭐ **RECOMMENDED**

```
┌─────────┐     ┌──────────┐     ┌───────┐     ┌────────────────┐
│ Client  │────▶│ FastAPI  │────▶│ Redis │────▶│ Celery Worker  │
│         │     │ (upload) │     │ Queue │     │   + Docling    │
└─────────┘     └──────────┘     └───────┘     └────────────────┘
                     │                                  │
                     │                                  ▼
                     │                          ┌──────────────┐
                     │◀─────────────────────────│  PostgreSQL  │
                     │      task_id             │  or SQLite   │
                     │                          └──────────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ Poll /status/   │
            │ Get /result/    │
            └─────────────────┘
```

**Components:**

1. **FastAPI Service** (Port 8001):
   - Accepts PDF upload via multipart/form-data
   - Validates file (size, format)
   - Creates task ID and queues job to Redis
   - Returns task_id immediately (non-blocking)
   - Provides status/result endpoints

2. **Redis** (Port 6379):
   - Message broker for Celery
   - Task metadata storage
   - Result caching (configurable TTL)

3. **Celery Workers** (1-N instances):
   - Pulls tasks from Redis queue
   - Executes Docling extraction
   - Stores results in database
   - Updates task status (pending → processing → completed/failed)

4. **Docling Processing**:
   - Runs in worker process (isolated from API)
   - GPU-accelerated if available
   - Models pre-loaded on worker startup

**Pros:**
- Non-blocking API (instant response)
- Horizontal scaling (add more workers)
- Retry logic and error handling
- Production-ready
- Monitoring via Flower

**Cons:**
- More complex setup
- Requires Redis infrastructure
- Eventual consistency model

**Use Case**: Production deployment, high volume

---

### Pattern C: Event-Driven Microservice (Enterprise)

```
┌─────────────┐     ┌──────────────────┐     ┌────────────┐
│ API Gateway │────▶│ PDF Import       │────▶│ RabbitMQ   │
│             │     │ Service (FastAPI)│     │            │
└─────────────┘     └──────────────────┘     └────────────┘
                                                     │
                    ┌────────────────────────────────┤
                    ▼                                ▼
            ┌────────────────┐            ┌──────────────────┐
            │ PDF Worker     │            │ Validator        │
            │ Service        │            │ Service          │
            │ (Docling)      │            │                  │
            └────────────────┘            └──────────────────┘
                    │                                │
                    ▼                                ▼
            ┌────────────────────────────────────────────┐
            │        Document Store (S3/MongoDB)         │
            └────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ Supervisor Service    │
                    │ (Orchestration)       │
                    └───────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │ Main XBRL Budget DB   │
                    └───────────────────────┘
```

**Use Case**: Large enterprise, multiple document types, complex workflows

---

## 4. Recommended Implementation (Pattern B)

### 4.1 Project Structure

```
budget/
├── pdf_service/                    # New microservice
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI application
│   │   ├── api/
│   │   │   └── v1/
│   │   │       ├── pdf_import.py   # Upload endpoints
│   │   │       └── status.py       # Status/result endpoints
│   │   ├── schemas/
│   │   │   ├── pdf_models.py       # Pydantic models
│   │   │   └── balance_sheet.py    # IV CEE structure
│   │   ├── services/
│   │   │   ├── docling_service.py  # Docling wrapper
│   │   │   └── mapper_service.py   # PDF → DB mapping
│   │   └── core/
│   │       ├── config.py           # Settings
│   │       └── celery_app.py       # Celery config
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── pdf_worker.py           # Main worker
│   │   └── tasks.py                # Celery tasks
│   ├── mappings/
│   │   └── iv_cee_mapping.json     # PDF field → sp01-sp18
│   ├── tests/
│   │   ├── test_docling.py
│   │   ├── test_mapper.py
│   │   └── sample_pdfs/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── backend/                        # Existing FastAPI backend
├── frontend/                       # Existing Next.js frontend
├── database/                       # Shared models
├── calculations/                   # Shared calculators
└── IV-CEE-PDF-IMPORT.md           # This document
```

### 4.2 Technology Stack

**Core Dependencies:**
```
docling>=2.70.0
fastapi>=0.115.0
celery>=5.4.0
redis>=5.2.0
python-multipart>=0.0.9
uvicorn>=0.32.0
pydantic>=2.0.0
sqlalchemy>=2.0.0
flower>=2.0.0  # Celery monitoring
```

**Optional (Production):**
```
prometheus-client  # Metrics
structlog         # Structured logging
sentry-sdk        # Error tracking
```

### 4.3 API Endpoints

#### POST /api/v1/pdf/upload
Upload PDF balance sheet for extraction.

**Request:**
```bash
curl -X POST http://localhost:8001/api/v1/pdf/upload \
  -F "file=@balance_sheet_2023.pdf" \
  -F "company_id=123" \
  -F "year=2023" \
  -F "company_name=ACME S.r.l."
```

**Response:**
```json
{
  "task_id": "a3c4d5e6-7890-1234-5678-90abcdef1234",
  "status": "pending",
  "message": "PDF uploaded successfully. Processing started.",
  "estimated_time_seconds": 30
}
```

#### GET /api/v1/pdf/status/{task_id}
Check processing status.

**Response (Processing):**
```json
{
  "task_id": "a3c4d5e6-7890-1234-5678-90abcdef1234",
  "status": "processing",
  "progress": 45,
  "current_step": "Extracting tables from PDF",
  "started_at": "2026-02-02T10:30:00Z"
}
```

**Response (Completed):**
```json
{
  "task_id": "a3c4d5e6-7890-1234-5678-90abcdef1234",
  "status": "completed",
  "progress": 100,
  "result_url": "/api/v1/pdf/result/a3c4d5e6-7890-1234-5678-90abcdef1234",
  "started_at": "2026-02-02T10:30:00Z",
  "completed_at": "2026-02-02T10:30:35Z",
  "duration_seconds": 35
}
```

#### GET /api/v1/pdf/result/{task_id}
Retrieve extracted data.

**Response:**
```json
{
  "task_id": "a3c4d5e6-7890-1234-5678-90abcdef1234",
  "company_id": 123,
  "year": 2023,
  "extraction_method": "docling_v2.70",
  "confidence_score": 0.96,
  "balance_sheet": {
    "sp01_crediti_soci": 0.00,
    "sp02_immob_immateriali": 125000.00,
    "sp03_immob_materiali": 850000.00,
    "sp04_immob_finanziarie": 50000.00,
    "sp05_rimanenze": 320000.00,
    "sp06_crediti": 560000.00,
    "sp07_attivita_finanziarie": 0.00,
    "sp08_disponibilita_liquide": 95000.00,
    "sp09_ratei_risconti_attivi": 15000.00,
    "sp10_capitale_sociale": 100000.00,
    "sp11_riserve": 250000.00,
    "sp12_utile_perdita": 85000.00,
    "sp13_fondi_rischi": 30000.00,
    "sp14_tfr": 120000.00,
    "sp15_debiti_lungo": 450000.00,
    "sp16_debiti_breve": 980000.00,
    "sp17_ratei_risconti_passivi": 25000.00,
    "sp18_totale_attivo": 2015000.00,
    "sp18_totale_passivo": 2015000.00,
    "balance_check": true
  },
  "extracted_tables": 2,
  "warnings": [],
  "raw_data": {
    "pdf_pages": 4,
    "extraction_timestamp": "2026-02-02T10:30:35Z"
  }
}
```

### 4.4 Celery Task Implementation

**workers/tasks.py:**
```python
from celery import Task
from docling.document_converter import DocumentConverter
from app.services.mapper_service import IVCEEMapper
from database.models import BalanceSheet, IncomeStatement

class PDFExtractionTask(Task):
    """Base task with Docling converter pre-loaded."""

    _converter = None

    @property
    def converter(self):
        if self._converter is None:
            # Initialize once per worker
            self._converter = DocumentConverter()
        return self._converter

@celery_app.task(base=PDFExtractionTask, bind=True)
def extract_balance_sheet(self, task_id: str, pdf_path: str, company_id: int, year: int):
    """Extract balance sheet data from PDF using Docling."""

    try:
        # Update status
        self.update_state(state='PROCESSING', meta={'progress': 10})

        # Convert PDF to structured format
        result = self.converter.convert(pdf_path)
        self.update_state(state='PROCESSING', meta={'progress': 50})

        # Extract tables
        tables = []
        for element in result.document.elements:
            if element.type == "table":
                tables.append(element.export_to_dataframe())

        # Map to IV CEE structure
        mapper = IVCEEMapper()
        balance_sheet_data = mapper.extract_balance_sheet(tables)
        self.update_state(state='PROCESSING', meta={'progress': 80})

        # Validate totals
        if not mapper.validate_balance(balance_sheet_data):
            raise ValueError("Balance sheet does not balance")

        # Save to database
        db = SessionLocal()
        try:
            balance_sheet = BalanceSheet(
                company_id=company_id,
                year=year,
                **balance_sheet_data
            )
            db.add(balance_sheet)
            db.commit()
        finally:
            db.close()

        return {
            'status': 'completed',
            'balance_sheet_id': balance_sheet.id,
            'data': balance_sheet_data
        }

    except Exception as e:
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise
```

### 4.5 Mapping Strategy: PDF → Database

**Challenge**: PDF tables may have different structures than our database schema.

**Solution**: Pattern-based extraction with fuzzy matching.

**mappings/iv_cee_mapping.json:**
```json
{
  "balance_sheet_attivo": {
    "patterns": [
      {
        "keywords": ["crediti verso soci", "crediti soci"],
        "field": "sp01_crediti_soci",
        "section": "A"
      },
      {
        "keywords": ["immobilizzazioni immateriali", "immob. immateriali"],
        "field": "sp02_immob_immateriali",
        "section": "B.I"
      },
      {
        "keywords": ["immobilizzazioni materiali", "immob. materiali"],
        "field": "sp03_immob_materiali",
        "section": "B.II"
      }
    ]
  },
  "balance_sheet_passivo": {
    "patterns": [
      {
        "keywords": ["capitale sociale", "capitale"],
        "field": "sp10_capitale_sociale",
        "section": "A.I"
      }
    ]
  },
  "hierarchical_debts": {
    "sp16_banks": ["debiti verso banche", "banche"],
    "sp16_financial": ["debiti verso altri finanziatori", "finanziatori"],
    "sp16_bonds": ["obbligazioni", "prestiti obbligazionari"],
    "sp16_suppliers": ["debiti verso fornitori", "fornitori"],
    "sp16_tax": ["debiti tributari", "erario"],
    "sp16_social_security": ["debiti verso istituti previdenza", "inps", "inail"],
    "sp16_other": ["altri debiti"]
  }
}
```

**Mapper Logic:**
1. Identify table structure (look for "ATTIVO"/"PASSIVO" headers)
2. Extract rows with monetary values
3. Match row labels to patterns using fuzzy matching (Levenshtein distance)
4. Handle multi-year columns (extract correct year)
5. Parse numbers (handle Italian format: 1.234.567,89)
6. Validate:
   - Total Assets = Total Liabilities + Equity
   - Sub-totals match hierarchical sums
   - Required fields present

### 4.6 Integration with Existing Backend

**Option 1: Direct Database Write**
- PDF service writes directly to `financial_analysis.db`
- Uses shared `database/models.py`
- Same schema as XBRL import

**Option 2: API Integration**
- PDF service calls backend API `/api/v1/import/balance_sheet`
- Backend handles validation and storage
- Better separation of concerns

**Recommended**: Option 1 (simpler, consistent with XBRL importer)

---

## 5. Deployment

### 5.1 Docker Compose Setup

**pdf_service/docker-compose.yml:**
```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  pdf_api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8001
    ports:
      - "8001:8001"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=sqlite:////app/data/financial_analysis.db
    volumes:
      - ../financial_analysis.db:/app/data/financial_analysis.db
      - ./uploads:/app/uploads
    depends_on:
      - redis

  celery_worker:
    build: .
    command: celery -A app.core.celery_app worker --loglevel=info
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL=sqlite:////app/data/financial_analysis.db
    volumes:
      - ../financial_analysis.db:/app/data/financial_analysis.db
      - ./uploads:/app/uploads
      - docling_models:/root/.cache/huggingface
    depends_on:
      - redis
    deploy:
      replicas: 2  # Scale workers as needed

  flower:
    build: .
    command: celery -A app.core.celery_app flower --port=5555
    ports:
      - "5555:5555"
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
      - celery_worker

volumes:
  redis_data:
  docling_models:
```

### 5.2 Running the Service

**Development:**
```bash
cd pdf_service

# Terminal 1: Redis
docker run -p 6379:6379 redis:7-alpine

# Terminal 2: API
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 3: Worker
celery -A app.core.celery_app worker --loglevel=info

# Terminal 4: Monitoring (optional)
celery -A app.core.celery_app flower --port=5555
```

**Production:**
```bash
cd pdf_service
docker-compose up -d

# Scale workers
docker-compose up -d --scale celery_worker=4

# View logs
docker-compose logs -f celery_worker
```

### 5.3 Monitoring

**Flower Dashboard** (http://localhost:5555):
- Active/completed/failed tasks
- Worker status and performance
- Task execution time histograms
- Retry statistics

**Prometheus Metrics** (Optional):
```python
from prometheus_client import Counter, Histogram

pdf_extractions_total = Counter('pdf_extractions_total', 'Total PDF extractions')
pdf_extraction_duration = Histogram('pdf_extraction_duration_seconds', 'PDF extraction duration')
pdf_extraction_errors = Counter('pdf_extraction_errors_total', 'Total extraction errors')
```

---

## 6. IV CEE PDF Parsing Specifics

### 6.1 Expected PDF Structure

Italian balance sheets typically follow this format:

```
STATO PATRIMONIALE - ATTIVO                    31/12/2023    31/12/2022
─────────────────────────────────────────────────────────────────────
A) Crediti verso soci                                    0             0
B) Immobilizzazioni
   I.   Immobilizzazioni immateriali            125.000       110.000
   II.  Immobilizzazioni materiali              850.000       800.000
   III. Immobilizzazioni finanziarie             50.000        45.000
C) Attivo circolante
   I.   Rimanenze                                320.000       280.000
   II.  Crediti                                  560.000       520.000
   III. Attività finanziarie                          0             0
   IV.  Disponibilità liquide                     95.000        80.000
D) Ratei e risconti attivi                        15.000        12.000
─────────────────────────────────────────────────────────────────────
TOTALE ATTIVO                                 2.015.000     1.847.000


STATO PATRIMONIALE - PASSIVO                   31/12/2023    31/12/2022
─────────────────────────────────────────────────────────────────────
A) Patrimonio netto
   I.   Capitale sociale                         100.000       100.000
   II.  Riserve                                  250.000       200.000
   III. Utile (perdita) dell'esercizio            85.000        70.000
B) Fondi per rischi e oneri                       30.000        25.000
C) Trattamento fine rapporto                     120.000       110.000
D) Debiti
   - esigibili oltre 12 mesi                     450.000       500.000
   - esigibili entro 12 mesi                     980.000       842.000
E) Ratei e risconti passivi                       25.000        20.000
─────────────────────────────────────────────────────────────────────
TOTALE PASSIVO                                2.015.000     1.847.000
```

### 6.2 Parsing Challenges

1. **Multi-Year Columns**: Extract correct year based on request
2. **Number Formatting**: Italian format (1.234.567,89) vs DB (1234567.89)
3. **Hierarchical Structure**: Map B.I, B.II to flat fields
4. **Missing Data**: Some PDFs omit zero-value lines
5. **Scanned PDFs**: Require OCR (Docling handles this)
6. **Different Schemas**: Ordinario vs Abbreviato vs Micro

### 6.3 Docling Extraction Approach

**Step 1: Detect Table Boundaries**
```python
tables = []
for element in result.document.elements:
    if element.type == "table":
        df = element.export_to_dataframe()
        # Check if it's the balance sheet table
        if any("ATTIVO" in str(col).upper() for col in df.columns):
            tables.append(('attivo', df))
        elif any("PASSIVO" in str(col).upper() for col in df.columns):
            tables.append(('passivo', df))
```

**Step 2: Extract Values**
```python
def extract_value(df, keywords, year_column):
    """Extract value matching keywords from DataFrame."""
    for idx, row in df.iterrows():
        row_text = ' '.join(str(cell).lower() for cell in row)
        if any(kw.lower() in row_text for kw in keywords):
            value_str = str(row[year_column])
            return parse_italian_number(value_str)
    return Decimal(0)

def parse_italian_number(value_str):
    """Convert Italian number format to Decimal."""
    # Remove thousand separators (.), replace decimal comma with dot
    clean = value_str.replace('.', '').replace(',', '.').strip()
    return Decimal(clean)
```

**Step 3: Map to Schema**
```python
balance_sheet_data = {}
attivo_df, passivo_df = tables

# Extract each field
for pattern in iv_cee_mapping['balance_sheet_attivo']['patterns']:
    field = pattern['field']
    keywords = pattern['keywords']
    balance_sheet_data[field] = extract_value(attivo_df, keywords, '31/12/2023')
```

**Step 4: Validate**
```python
total_attivo = balance_sheet_data['sp18_totale_attivo']
total_passivo = balance_sheet_data['sp18_totale_passivo']

if abs(total_attivo - total_passivo) > Decimal('0.01'):
    raise ValueError(f"Balance sheet does not balance: {total_attivo} != {total_passivo}")
```

---

## 7. Testing Strategy

### 7.1 Unit Tests

**tests/test_mapper.py:**
```python
def test_italian_number_parsing():
    assert parse_italian_number("1.234.567,89") == Decimal("1234567.89")
    assert parse_italian_number("0") == Decimal("0")
    assert parse_italian_number("123,45") == Decimal("123.45")

def test_pattern_matching():
    mapper = IVCEEMapper()
    assert mapper.match_field("Crediti verso soci") == "sp01_crediti_soci"
    assert mapper.match_field("Immobilizzazioni immateriali") == "sp02_immob_immateriali"
```

### 7.2 Integration Tests

**tests/test_docling.py:**
```python
def test_extract_sample_pdf():
    converter = DocumentConverter()
    result = converter.convert("tests/sample_pdfs/obicon_2023.pdf")

    tables = extract_tables(result)
    assert len(tables) >= 2  # At least Attivo and Passivo

    mapper = IVCEEMapper()
    data = mapper.extract_balance_sheet(tables)

    assert data['sp18_totale_attivo'] > 0
    assert abs(data['sp18_totale_attivo'] - data['sp18_totale_passivo']) < Decimal('0.01')
```

### 7.3 Test Data

Collect sample PDFs from:
1. Camera di Commercio downloads
2. Different company sizes (Ordinario, Abbreviato, Micro)
3. Different years (2020-2025)
4. Scanned vs digital PDFs

---

## 8. Frontend Integration

### 8.1 Upload Component

**frontend/app/import-pdf/page.tsx:**
```typescript
'use client'

import { useState } from 'react'
import { uploadPDF, checkStatus, getResult } from '@/lib/api'

export default function PDFImportPage() {
  const [file, setFile] = useState<File | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [status, setStatus] = useState<string>('idle')
  const [progress, setProgress] = useState<number>(0)

  const handleUpload = async () => {
    if (!file) return

    const formData = new FormData()
    formData.append('file', file)
    formData.append('company_name', 'ACME S.r.l.')
    formData.append('year', '2023')

    const response = await uploadPDF(formData)
    setTaskId(response.task_id)
    pollStatus(response.task_id)
  }

  const pollStatus = async (taskId: string) => {
    const interval = setInterval(async () => {
      const status = await checkStatus(taskId)
      setStatus(status.status)
      setProgress(status.progress)

      if (status.status === 'completed') {
        clearInterval(interval)
        const result = await getResult(taskId)
        // Show result, save to database
      }
    }, 2000)
  }

  return (
    <div>
      <h1>Import PDF Balance Sheet</h1>
      <input type="file" accept=".pdf" onChange={(e) => setFile(e.target.files[0])} />
      <button onClick={handleUpload}>Upload</button>

      {taskId && (
        <div>
          <p>Status: {status}</p>
          <progress value={progress} max={100}>{progress}%</progress>
        </div>
      )}
    </div>
  )
}
```

### 8.2 API Client Updates

**frontend/lib/api.ts:**
```typescript
const PDF_SERVICE_URL = 'http://localhost:8001/api/v1/pdf'

export async function uploadPDF(formData: FormData) {
  const response = await fetch(`${PDF_SERVICE_URL}/upload`, {
    method: 'POST',
    body: formData,
  })
  return response.json()
}

export async function checkStatus(taskId: string) {
  const response = await fetch(`${PDF_SERVICE_URL}/status/${taskId}`)
  return response.json()
}

export async function getResult(taskId: string) {
  const response = await fetch(`${PDF_SERVICE_URL}/result/${taskId}`)
  return response.json()
}
```

---

## 9. Performance Considerations

### 9.1 Benchmarks (Expected)

| Scenario | Time | Notes |
|----------|------|-------|
| First request (model download) | 90-150s | One-time per worker |
| 4-page PDF (digital) | 3-8s | Typical Italian balance sheet |
| 4-page PDF (scanned) | 10-20s | Requires OCR |
| 20-page PDF (full report) | 30-60s | Annual report with notes |

### 9.2 Optimization Strategies

1. **Pre-warm Workers**: Download models during container build
2. **GPU Acceleration**: 5-10x speedup for OCR-heavy documents
3. **Caching**: Store extracted data with PDF hash to avoid re-processing
4. **Batch Processing**: Process multiple PDFs in parallel
5. **Model Quantization**: Reduce model size for faster loading

### 9.3 Scaling Guidelines

| Load | Workers | Redis | Notes |
|------|---------|-------|-------|
| <10 PDFs/hour | 1 | 1 instance | Development |
| 10-100 PDFs/hour | 2-4 | 1 instance | Small production |
| 100-1000 PDFs/hour | 10-20 | Redis Cluster | Medium production |
| >1000 PDFs/hour | 50+ | Redis Cluster + Load Balancer | Enterprise |

---

## 10. Security Considerations

### 10.1 File Upload Validation

```python
ALLOWED_EXTENSIONS = {'.pdf'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

def validate_upload(file: UploadFile):
    # Check extension
    if not file.filename.endswith('.pdf'):
        raise ValueError("Only PDF files allowed")

    # Check size
    file.file.seek(0, 2)  # Seek to end
    size = file.file.tell()
    file.file.seek(0)  # Reset

    if size > MAX_FILE_SIZE:
        raise ValueError("File too large")

    # Check magic bytes
    header = file.file.read(4)
    file.file.seek(0)
    if header != b'%PDF':
        raise ValueError("Invalid PDF file")
```

### 10.2 Sandboxing

- Run Celery workers in separate containers
- Use read-only file system for uploaded PDFs
- Limit worker memory/CPU via Docker
- Automatically delete processed files after 24h

### 10.3 Authentication

If adding to production:
- Add JWT authentication to PDF service
- Validate company_id ownership
- Rate limiting (e.g., 10 uploads/hour per user)

---

## 11. Cost Analysis

### 11.1 Infrastructure Costs (AWS Example)

| Component | Instance Type | Monthly Cost |
|-----------|---------------|--------------|
| Redis | ElastiCache t3.micro | $13 |
| API Server | ECS Fargate 0.5vCPU/1GB | $15 |
| Celery Workers (2x) | ECS Fargate 1vCPU/2GB | $60 |
| S3 Storage (100GB PDFs) | Standard | $2.30 |
| **Total** | | **~$90/month** |

### 11.2 Alternative: Self-Hosted

- VPS with 4vCPU/8GB RAM: $40-80/month
- Can run all components on single server
- Docker Compose deployment

---

## 12. Roadmap

### Phase 1: MVP (2-3 weeks)
- [ ] Set up FastAPI service structure
- [ ] Integrate Docling for basic PDF extraction
- [ ] Implement simple mapping (top 10 balance sheet fields)
- [ ] Create upload endpoint (synchronous)
- [ ] Manual testing with 5 sample PDFs

### Phase 2: Production Ready (2-3 weeks)
- [ ] Implement Celery + Redis async architecture
- [ ] Complete IV CEE mapping (all sp01-sp18 fields)
- [ ] Add hierarchical debt extraction (sp16a-g)
- [ ] Implement validation and error handling
- [ ] Create status/result endpoints
- [ ] Write unit and integration tests

### Phase 3: Frontend Integration (1 week)
- [ ] Build PDF upload UI component
- [ ] Add progress indicator
- [ ] Display extraction results
- [ ] Handle errors and retries
- [ ] Add to main navigation

### Phase 4: Optimization (1-2 weeks)
- [ ] Add Flower monitoring
- [ ] Implement caching
- [ ] Performance tuning
- [ ] GPU acceleration setup
- [ ] Load testing

### Phase 5: Production Deployment (1 week)
- [ ] Docker Compose configuration
- [ ] CI/CD pipeline
- [ ] Monitoring and alerting
- [ ] Documentation
- [ ] User training

**Total Estimated Time**: 7-11 weeks

---

## 13. References

### Documentation
- [Docling Official Documentation](https://docling-project.github.io/docling/)
- [Docling GitHub Repository](https://github.com/docling-project/docling)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Celery Documentation](https://docs.celeryq.dev/)

### Research Articles
- [PDF Table Extraction Showdown: Docling vs. LlamaParse](https://boringbot.substack.com/p/pdf-table-extraction-showdown-docling)
- [A REST Implementation of Docling with FastAPI](https://alain-airom.medium.com/a-rest-implementation-of-docling-with-fastapi-2a260bbcaa0a)
- [Building Async Processing Pipelines with FastAPI and Celery](https://devcenter.upsun.com/posts/building-async-processing-pipelines-with-fastapi-and-celery-on-upsun/)

### Legal Framework
- [EUR-Lex - Directive 2013/34/EU (Accounting Directive)](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32013L0034)
- [Fourth Council Directive (78/660/EEC)](https://www.worker-participation.eu/Company-Law-and-CG/Company-Law/Overview-of-Directives/Fourth-Council-Directive-Annual-accounts-of-companies-with-limited-liability-78-660-EEC)
- [Italian Financial Statements Structure (PDF)](https://iris.uniupo.it/retrieve/9588868b-0c20-46f7-a526-a8e86c7d87d2/Structure%20and%20Contents%20of%20(Italian)%20Financial.pdf)

### Implementation Examples
- [docling-api GitHub Repository](https://github.com/drmingler/docling-api)
- [FastAPI Middleware Patterns 2026](https://johal.in/fastapi-middleware-patterns-custom-logging-metrics-and-error-handling-2026-2/)
- [Celery + Redis + FastAPI Production Guide](https://medium.com/@dewasheesh.rana/celery-redis-fastapi-the-ultimate-2025-production-guide-broker-vs-backend-explained-5b84ef508fa7)

---

## 14. Appendix: Sample Data

### A. Sample Balance Sheet Mapping

```json
{
  "company": "OBICON S.R.L.",
  "tax_id": "01234567890",
  "year": 2023,
  "extraction_date": "2026-02-02",
  "pdf_source": "Camera_Commercio_Milano_2023.pdf",
  "confidence": 0.96,
  "balance_sheet": {
    "sp01_crediti_soci": 0,
    "sp02_immob_immateriali": 125000,
    "sp03_immob_materiali": 850000,
    "sp04_immob_finanziarie": 50000,
    "sp05_rimanenze": 320000,
    "sp06_crediti": 560000,
    "sp07_attivita_finanziarie": 0,
    "sp08_disponibilita_liquide": 95000,
    "sp09_ratei_risconti_attivi": 15000,
    "sp10_capitale_sociale": 100000,
    "sp11_riserve": 250000,
    "sp12_utile_perdita": 85000,
    "sp13_fondi_rischi": 30000,
    "sp14_tfr": 120000,
    "sp15_debiti_lungo": 450000,
    "sp16_debiti_breve": 980000,
    "sp16a_debiti_banche_lungo": 300000,
    "sp16a_debiti_banche_breve": 400000,
    "sp16b_debiti_finanziari_lungo": 100000,
    "sp16b_debiti_finanziari_breve": 50000,
    "sp16c_debiti_obbligazioni_lungo": 0,
    "sp16c_debiti_obbligazioni_breve": 0,
    "sp16d_debiti_fornitori_lungo": 50000,
    "sp16d_debiti_fornitori_breve": 450000,
    "sp16e_debiti_tributari_lungo": 0,
    "sp16e_debiti_tributari_breve": 35000,
    "sp16f_debiti_previdenziali_lungo": 0,
    "sp16f_debiti_previdenziali_breve": 25000,
    "sp16g_altri_debiti_lungo": 0,
    "sp16g_altri_debiti_breve": 20000,
    "sp17_ratei_risconti_passivi": 25000,
    "sp18_totale_attivo": 2015000,
    "sp18_totale_passivo": 2015000
  }
}
```

---

**Document Version**: 1.0
**Last Updated**: 2026-02-02
**Author**: Claude Code Research
**Status**: Draft - Ready for Implementation Review
