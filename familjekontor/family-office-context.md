# Family Office Administration System - Development Context

## Project Overview

**Application name:** Family Office Admin (working name: `familjekontor`)  
**Purpose:** Streamline administration of family-owned companies, reducing manual work and ensuring compliance with Swedish regulations  
**Users:** Family members (primary: 1-2 users, potential: 3-5)  
**AI:** Local only (financial data confidentiality)

## Business Context

### Current Situation
- 5 companies: 4 Aktiebolag (AB) + 1 Handelsbolag (HB)
- 3 employees across 5 companies
- ~500 transactions/year currently, growing to ~2000
- Using Adaro Bokföring (SIE export available)
- Banks: SEB, Nordea + Nordnet for trading
- Administrative time: 5-6 hours/week (unevenly distributed)

### Pain Points to Solve
1. Manual entry of invoices (biggest time-waster)
2. Tracking deadlines for tax and VAT reporting
3. Tracking payment deadlines
4. Year-end and annual tax reporting workload peaks
5. No consolidated view across companies

### Target Structure
- Convert one AB to holding company (moderbolag)
- 3 ABs as subsidiaries under holding
- 1 HB remains standalone
- Enable group consolidation for tax optimization

## Scope & Prioritization

### Phase 1: Core Accounting & Automation (Must Have)
- Multi-company accounting (K2/K3)
- AI-powered invoice processing
- Verification proposal and booking
- Payment instruction generation
- Bank payment file export (SEB, Nordea)
- Basic P&L and Balance reports
- SIE import (migration from Adaro)

### Phase 2: Tax & Compliance
- VAT reporting (momsdeklaration) - file generation
- Employer tax reporting (arbetsgivaravgifter)
- Deadline calendar with reminders
- Tax payment tracking

### Phase 3: Salary & Pension
- Salary administration (3 employees)
- Tax deduction calculations (PAYE)
- Pension reporting (Collectum file generation)
- Salary slips

### Phase 4: Corporate Governance
- Shareholder register (aktiebok)
- Certificate register (Bolagsverket)
- Approval/certification tracking
- Renewal reminders
- Document storage per company

### Phase 5: Financial Statements & Reporting
- Annual report generation (årsredovisning)
- K2/K3 compliant formatting
- Bolagsverket submission support
- Monthly/quarterly management reports

### Phase 6: Group Structure & Consolidation
- Holding company setup support
- Intercompany transaction handling
- Group consolidation reports
- Koncernredovisning preparation

### Phase 7: Asset & Investment Management
- Fixed asset register with depreciation
- Nordnet integration:
  - Import all transactions (buy, sell, dividend, fees)
  - Import currency account holdings
  - Portfolio holdings tracking and valuation
  - Capital gains calculations
- Investment tracking
- Real estate register

### Phase 8: AI Advisory & Analysis
- Business analysis reports
- Tax planning recommendations
- Cash flow forecasting
- Activity reminders and alerts

## Technology Stack

- **Backend:** Python with Flask
- **Database:** PostgreSQL (multi-company, 10+ years data)
- **Local AI:** Ollama with Llama 3 70B (invoice reading, analysis)
- **OCR:** Tesseract or EasyOCR (local)
- **Document Processing:** PyMuPDF, python-docx
- **Reporting:** ReportLab (PDF), openpyxl (Excel)
- **Deployment:** Docker on home server/NAS

## Hardware Requirements

**Minimum (Phase 1-5):**
- Modern CPU (8+ cores)
- 32GB RAM
- 500GB SSD
- No GPU required (can use CPU inference for low volume)

**Recommended (with AI features):**
- 16+ cores
- 64GB RAM
- 1TB SSD
- GPU: RTX 3080/4070 or better (faster invoice processing)

**Note:** Can share hardware with MPQP Generator if on same network, or run lighter models for lower transaction volume.

## Core Functionality

### 1. Multi-Company Management

**Company Types Supported:**
| Type | Tax Rules | Reporting | Notes |
|------|-----------|-----------|-------|
| Aktiebolag (AB) | Corporate tax 20.6% | Årsredovisning to Bolagsverket | K2 or K3 |
| Handelsbolag (HB) | Pass-through to partners | Inkomstdeklaration 4 | Simpler rules |

**Company Switching:**
- Dashboard shows all companies
- Quick switch between company contexts
- Cross-company views for consolidated reporting
- Each company has isolated data with clear separation

**Data Structure:**
```
Company A (AB - future holding)
├── Fiscal years (2015-2025)
├── Verifications
├── Accounts (BAS-kontoplan)
├── Documents
└── Reports

Company B (AB - subsidiary)
├── ...

Company E (HB - standalone)
├── ...
```

### 2. Invoice Processing with AI

**Workflow:**
```
1. Upload invoice (PDF/image)
         │
         ▼
2. OCR extracts text (local Tesseract/EasyOCR)
         │
         ▼
3. AI analyzes and extracts:
   - Supplier name & org.nr
   - Invoice number & date
   - Due date
   - Amount (excl. VAT, VAT, total)
   - Line items if readable
   - Payment details (bankgiro/plusgiro/IBAN)
         │
         ▼
4. AI proposes verification:
   - Debit account (cost account based on supplier/content)
   - Credit account (supplier liability 2440)
   - VAT account (2640/2641)
   - Cost center if applicable
         │
         ▼
5. User reviews & approves/adjusts
         │
         ▼
6. Verification created
   Payment instruction queued
```

**Learning:**
- System learns from corrections
- Builds supplier → account mapping
- Improves over time

### 3. Payment Management

**Payment Instructions:**
- Generated automatically from approved invoices
- Manual payment instructions supported
- Payment date based on due date or user preference

**Weekly Payment File Generation:**
| Bank | Format | File Type |
|------|--------|-----------|
| SEB | ISO 20022 pain.001 | XML |
| Nordea | ISO 20022 pain.001 | XML |
| Bankgirot | Bankgirot format | Text |

**Workflow:**
```
1. Review pending payments
2. Select payments for this week
3. Generate payment file per bank
4. Download file
5. Upload to bank portal (manual)
6. Mark as paid when confirmed
```

### 4. Accounting Core

**Chart of Accounts:**
- BAS-kontoplan (Swedish standard)
- Customizable per company
- K2 and K3 compatible account structures

**Verification Types:**
| Type | Source | Automation |
|------|--------|------------|
| Supplier invoice | Upload | AI-assisted |
| Customer invoice | Create in system | Template-based |
| Customer invoice (export) | Create in system | Template + VAT handling |
| Bank transaction | Import bank file | Matching |
| Nordnet transaction | Import from Nordnet | Automatic categorization |
| Salary | Salary run | Automatic |
| Manual | User entry | None |

**Multi-Currency Support:**
- SEK as base currency
- NOK for Norwegian customer invoices
- Foreign currencies for Nordnet holdings (USD, EUR, etc.)
- Exchange rate handling per Skatteverket rules

**Fiscal Year Management:**
- Support multiple open years (current + previous for adjustments)
- Year-end closing procedures
- Opening balance generation

### 5. VAT Reporting

**Swedish VAT Periods:**
| Turnover | Reporting Period |
|----------|-----------------|
| < 1 MSEK | Annual |
| 1-40 MSEK | Quarterly |
| > 40 MSEK | Monthly |

**Generated Output:**
- Momsdeklaration summary
- SKV 4700 format data
- Ready for entry into Skatteverket portal

**VAT Accounts Tracked:**
| Account | Description |
|---------|-------------|
| 2610 | Utgående moms 25% |
| 2620 | Utgående moms 12% |
| 2630 | Utgående moms 6% |
| 2640 | Ingående moms |
| 2650 | Moms redovisningskonto |

### 6. Salary Administration

**Features:**
- Employee register (3 employees currently)
- Salary specifications per employee
- Tax table calculations (PAYE/källskatt)
- Employer contributions (arbetsgivaravgifter 31.42%)
- Salary slip generation

**Reporting:**
| Report | Frequency | Destination |
|--------|-----------|-------------|
| Arbetsgivardeklaration | Monthly | Skatteverket |
| AGI (individuppgift) | Monthly | Skatteverket |
| Kontrolluppgift KU10 | Annual | Skatteverket |
| Pension report | Per agreement | Collectum |

**Collectum Integration:**
- Generate file in Collectum format
- Track pension contributions
- Support ITP1/ITP2 plans

### 7. Deadline Management

**Automatic Tracking:**
| Deadline Type | Frequency | Reminder |
|---------------|-----------|----------|
| VAT declaration | Monthly/Quarterly | 7 days before |
| Employer declaration | Monthly (12th) | 5 days before |
| Corporate tax payment | Quarterly | 7 days before |
| Annual report filing | 7 months after FY | 30 days before |
| Tax return (AB) | July 1 | 14 days before |
| Tax return (HB) | May 2 | 14 days before |

**Dashboard:**
- Upcoming deadlines (30 days)
- Overdue items (red alert)
- Completed items log

### 8. Document Management

**Per Company:**
- Bolagsverket certificates (registreringsbevis)
- Approval certificates
- Contracts
- Board meeting minutes (if desired)
- Historical annual reports

**Features:**
- Upload and categorize documents
- Expiry date tracking for certificates
- Automatic reminders for renewals
- Link documents to verifications

### 9. Reports

**Standard Reports:**
| Report | Frequency |
|--------|-----------|
| Resultaträkning (P&L) | Monthly/Annual |
| Balansräkning (Balance) | Monthly/Annual |
| Huvudbok (General ledger) | On demand |
| Leverantörsreskontra | On demand |
| Kundreskontra | On demand |
| Momsrapport | Per period |

**Annual Report (Årsredovisning):**
- K2 or K3 format
- Förvaltningsberättelse template
- Notes (noter) generation
- PDF output for Bolagsverket

**Group Reports (Phase 6):**
- Consolidated P&L
- Consolidated Balance
- Intercompany elimination

### 10. SIE Integration

### 13. SIE Integration

**Import:**
- SIE4 import from Adaro
- Map accounts if needed
- Import historical years

**Export:**
- SIE4 export for auditors
- SIE4 export for backup
- SIE4 export per fiscal year

## Database Schema

### Core Tables

```sql
-- Companies
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    org_number TEXT UNIQUE NOT NULL,      -- 10 digits
    company_type TEXT NOT NULL,            -- 'AB', 'HB'
    accounting_standard TEXT DEFAULT 'K2', -- 'K2', 'K3'
    fiscal_year_start INTEGER DEFAULT 1,   -- Month (1=Jan)
    vat_period TEXT DEFAULT 'quarterly',   -- 'monthly', 'quarterly', 'annual'
    parent_company_id INTEGER REFERENCES companies(id),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Fiscal years
CREATE TABLE fiscal_years (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    year INTEGER NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status TEXT DEFAULT 'open',           -- 'open', 'closed', 'archived'
    UNIQUE(company_id, year)
);

-- Chart of accounts (per company, based on BAS)
CREATE TABLE accounts (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    account_number TEXT NOT NULL,         -- e.g., '1930', '4000'
    name TEXT NOT NULL,
    account_type TEXT NOT NULL,           -- 'asset', 'liability', 'equity', 'revenue', 'expense'
    vat_code TEXT,                        -- For automatic VAT handling
    active BOOLEAN DEFAULT TRUE,
    UNIQUE(company_id, account_number)
);

-- Verifications (huvudbok poster)
CREATE TABLE verifications (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    fiscal_year_id INTEGER REFERENCES fiscal_years(id),
    verification_number INTEGER NOT NULL,
    verification_date DATE NOT NULL,
    description TEXT,
    verification_type TEXT,               -- 'supplier', 'customer', 'bank', 'salary', 'manual'
    source_document_id INTEGER,           -- Reference to uploaded document
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER,
    UNIQUE(company_id, fiscal_year_id, verification_number)
);

-- Verification rows (transactions)
CREATE TABLE verification_rows (
    id SERIAL PRIMARY KEY,
    verification_id INTEGER REFERENCES verifications(id),
    account_id INTEGER REFERENCES accounts(id),
    debit DECIMAL(15,2) DEFAULT 0,
    credit DECIMAL(15,2) DEFAULT 0,
    description TEXT,
    cost_center TEXT
);

-- Suppliers
CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    name TEXT NOT NULL,
    org_number TEXT,
    default_account TEXT,                 -- Default expense account
    payment_terms INTEGER DEFAULT 30,     -- Days
    bankgiro TEXT,
    plusgiro TEXT,
    iban TEXT,
    bic TEXT,
    learned_mappings JSONB,               -- AI-learned account mappings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Invoices (supplier)
CREATE TABLE supplier_invoices (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    supplier_id INTEGER REFERENCES suppliers(id),
    invoice_number TEXT,
    invoice_date DATE,
    due_date DATE,
    amount_excl_vat DECIMAL(15,2),
    vat_amount DECIMAL(15,2),
    total_amount DECIMAL(15,2),
    currency TEXT DEFAULT 'SEK',
    status TEXT DEFAULT 'pending',        -- 'pending', 'approved', 'paid', 'cancelled'
    verification_id INTEGER REFERENCES verifications(id),
    payment_instruction_id INTEGER,
    document_id INTEGER,                  -- Uploaded invoice document
    ai_extracted_data JSONB,              -- Raw AI extraction
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Payment instructions
CREATE TABLE payment_instructions (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    supplier_invoice_id INTEGER REFERENCES supplier_invoices(id),
    amount DECIMAL(15,2),
    currency TEXT DEFAULT 'SEK',
    payment_date DATE,
    recipient_name TEXT,
    payment_method TEXT,                  -- 'bankgiro', 'plusgiro', 'iban'
    payment_reference TEXT,               -- Bankgiro/plusgiro/IBAN
    ocr_reference TEXT,
    status TEXT DEFAULT 'pending',        -- 'pending', 'in_file', 'paid'
    payment_file_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Payment files (generated for bank upload)
CREATE TABLE payment_files (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    bank TEXT NOT NULL,                   -- 'SEB', 'Nordea'
    file_format TEXT,                     -- 'pain.001', 'bankgirot'
    file_path TEXT,
    total_amount DECIMAL(15,2),
    payment_count INTEGER,
    status TEXT DEFAULT 'generated',      -- 'generated', 'uploaded', 'confirmed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Employees
CREATE TABLE employees (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    personal_number TEXT NOT NULL,        -- Personnummer
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    employment_start DATE,
    employment_end DATE,
    salary_monthly DECIMAL(15,2),
    tax_table TEXT,                       -- Skattetabell
    tax_column INTEGER,                   -- Kolumn
    pension_plan TEXT,                    -- 'ITP1', 'ITP2', etc.
    active BOOLEAN DEFAULT TRUE
);

-- Salary runs
CREATE TABLE salary_runs (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    period_year INTEGER,
    period_month INTEGER,
    status TEXT DEFAULT 'draft',          -- 'draft', 'approved', 'paid'
    total_gross DECIMAL(15,2),
    total_tax DECIMAL(15,2),
    total_net DECIMAL(15,2),
    total_employer_contributions DECIMAL(15,2),
    verification_id INTEGER REFERENCES verifications(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Documents
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    document_type TEXT,                   -- 'invoice', 'certificate', 'contract', 'annual_report'
    file_name TEXT,
    file_path TEXT,
    mime_type TEXT,
    extracted_text TEXT,
    expiry_date DATE,                     -- For certificates
    reminder_date DATE,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Deadlines
CREATE TABLE deadlines (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    deadline_type TEXT,                   -- 'vat', 'employer_tax', 'annual_report', etc.
    description TEXT,
    due_date DATE,
    reminder_date DATE,
    status TEXT DEFAULT 'pending',        -- 'pending', 'completed', 'overdue'
    completed_at TIMESTAMP,
    notes TEXT
);

-- Customer invoices
CREATE TABLE customer_invoices (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    customer_id INTEGER REFERENCES customers(id),
    invoice_number TEXT NOT NULL,
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    currency TEXT DEFAULT 'SEK',
    exchange_rate DECIMAL(10,6) DEFAULT 1.0,
    amount_excl_vat DECIMAL(15,2),
    vat_amount DECIMAL(15,2),
    total_amount DECIMAL(15,2),
    vat_type TEXT,                        -- 'standard', 'reverse_charge', 'export'
    status TEXT DEFAULT 'draft',          -- 'draft', 'sent', 'paid', 'overdue', 'cancelled'
    verification_id INTEGER REFERENCES verifications(id),
    pdf_path TEXT,
    sent_at TIMESTAMP,
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Customers
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    name TEXT NOT NULL,
    org_number TEXT,
    country TEXT DEFAULT 'SE',            -- ISO country code
    vat_number TEXT,                      -- For EU VAT validation
    address TEXT,
    postal_code TEXT,
    city TEXT,
    email TEXT,
    payment_terms INTEGER DEFAULT 30,
    default_currency TEXT DEFAULT 'SEK',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Nordnet accounts
CREATE TABLE nordnet_accounts (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    account_number TEXT NOT NULL,
    account_type TEXT,                    -- 'ISK', 'AF', 'KF', 'Depå'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Nordnet transactions
CREATE TABLE nordnet_transactions (
    id SERIAL PRIMARY KEY,
    nordnet_account_id INTEGER REFERENCES nordnet_accounts(id),
    transaction_date DATE NOT NULL,
    settlement_date DATE,
    transaction_type TEXT,                -- 'BUY', 'SELL', 'DIVIDEND', 'INTEREST', 'FEE', 'DEPOSIT', 'WITHDRAWAL'
    security_name TEXT,
    isin TEXT,
    quantity DECIMAL(15,6),
    price DECIMAL(15,6),
    currency TEXT,
    amount DECIMAL(15,2),
    fee DECIMAL(15,2),
    exchange_rate DECIMAL(10,6),
    verification_id INTEGER REFERENCES verifications(id),
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_data JSONB                        -- Original import data
);

-- Nordnet holdings (snapshot)
CREATE TABLE nordnet_holdings (
    id SERIAL PRIMARY KEY,
    nordnet_account_id INTEGER REFERENCES nordnet_accounts(id),
    snapshot_date DATE NOT NULL,
    security_name TEXT,
    isin TEXT,
    quantity DECIMAL(15,6),
    avg_cost_price DECIMAL(15,6),
    current_price DECIMAL(15,6),
    currency TEXT,
    market_value DECIMAL(15,2),
    unrealized_gain_loss DECIMAL(15,2),
    UNIQUE(nordnet_account_id, snapshot_date, isin)
);

-- Currency accounts (Nordnet and others)
CREATE TABLE currency_accounts (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id),
    account_name TEXT,
    currency TEXT NOT NULL,
    balance DECIMAL(15,2),
    last_updated TIMESTAMP
);
CREATE TABLE audit_log (
    id SERIAL PRIMARY KEY,
    company_id INTEGER,
    user_id INTEGER,
    action TEXT,
    entity_type TEXT,
    entity_id INTEGER,
    old_values JSONB,
    new_values JSONB,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Application Structure

```
familjekontor/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── dashboard.py
│   │   ├── companies.py
│   │   ├── accounting.py
│   │   ├── invoices.py
│   │   ├── payments.py
│   │   ├── salary.py
│   │   ├── vat.py
│   │   ├── reports.py
│   │   ├── documents.py
│   │   └── admin.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── company.py
│   │   ├── accounting.py
│   │   ├── invoice.py
│   │   ├── payment.py
│   │   ├── employee.py
│   │   └── document.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── invoice_processor.py     # AI invoice reading
│   │   ├── payment_generator.py     # Bank file generation
│   │   ├── vat_calculator.py        # VAT reporting
│   │   ├── salary_processor.py      # Salary calculations
│   │   ├── report_generator.py      # Financial reports
│   │   ├── sie_handler.py           # SIE import/export
│   │   ├── deadline_tracker.py      # Deadline management
│   │   ├── consolidation.py         # Group consolidation
│   │   └── llm_client.py            # Ollama interface
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── ocr.py                   # OCR processing
│   │   ├── pdf_utils.py
│   │   ├── bas_kontoplan.py         # Standard chart of accounts
│   │   ├── tax_tables.py            # Swedish tax tables
│   │   └── validators.py
│   └── templates/
│       ├── base.html
│       ├── dashboard.html
│       ├── companies/
│       ├── accounting/
│       ├── invoices/
│       ├── payments/
│       ├── salary/
│       ├── reports/
│       └── admin/
├── static/
├── data/
│   ├── uploads/                     # Uploaded documents
│   ├── generated/                   # Generated reports/files
│   ├── backups/                     # Database backups
│   └── archive/                     # Archived years
├── models/
│   └── prompts/                     # LLM prompts for invoice processing
├── tests/
├── scripts/
│   ├── import_sie.py                # SIE import script
│   ├── backup_db.py                 # Backup script
│   └── archive_year.py              # Year archiving
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Bank Payment File Formats

### ISO 20022 pain.001 (SEB & Nordea)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03">
  <CstmrCdtTrfInitn>
    <GrpHdr>
      <MsgId>MSGID-2025-001</MsgId>
      <CreDtTm>2025-02-05T10:00:00</CreDtTm>
      <NbOfTxs>3</NbOfTxs>
      <CtrlSum>15000.00</CtrlSum>
      <InitgPty>
        <Nm>Company Name AB</Nm>
        <Id><OrgId><Othr><Id>5566778899</Id></Othr></OrgId></Id>
      </InitgPty>
    </GrpHdr>
    <PmtInf>
      <!-- Payment details -->
    </PmtInf>
  </CstmrCdtTrfInitn>
</Document>
```

### Bankgirot Format (Alternative)

```
01BGMAX               0120250205            
200001             5566778899FÖRETAGET AB                    
260000000001000000001500000SUPPLIER ONE                      123456    
280001OCR-REFERENCE                    
290001                    
260000000002000000002500000SUPPLIER TWO                      789012    
...
```

## Web Interface

### Dashboard
- Company selector (dropdown or tabs)
- Key metrics per company:
  - Bank balance (manual entry or import)
  - Unpaid supplier invoices
  - Outstanding customer invoices
  - VAT due this period
- Upcoming deadlines (next 30 days)
- Recent activity
- Quick actions: Upload invoice, Create verification

### Invoice Processing
- Drag & drop upload area
- Processing status indicator
- AI extraction review:
  - Supplier (auto-detected, editable)
  - Amounts (editable)
  - Proposed accounts (editable)
- Approve / Adjust / Reject buttons
- Bulk processing for multiple invoices

### Payment Management
- Pending payments list
- Select payments for batch
- Generate payment file button
- Download file
- Mark as uploaded/confirmed

## Development Phases

### Phase 1: Foundation & Core Accounting (Months 1-2)
- [ ] Project setup, database, Docker
- [ ] Multi-company structure
- [ ] BAS-kontoplan implementation
- [ ] Multi-currency support (SEK, NOK, EUR, USD)
- [ ] Basic verification entry (manual)
- [ ] SIE4 import from Adaro
- [ ] Simple P&L and Balance reports

### Phase 2: Invoice Automation (Months 2-3)
- [ ] Document upload system
- [ ] OCR integration (Tesseract)
- [ ] Local LLM setup (Ollama)
- [ ] Supplier invoice data extraction
- [ ] Verification proposal
- [ ] Supplier learning/mapping
- [ ] Customer invoice creation
- [ ] Norwegian customer support (NOK, reverse charge VAT)
- [ ] Invoice PDF generation and sending

### Phase 3: Payments (Month 3)
- [ ] Payment instruction management
- [ ] SEB pain.001 file generation
- [ ] Nordea pain.001 file generation
- [ ] Payment status tracking

### Phase 4: Tax & VAT (Month 4)
- [ ] VAT calculation engine
- [ ] Momsdeklaration report generation
- [ ] Deadline tracking system
- [ ] Reminder notifications

### Phase 5: Reports & Statements (Month 5)
- [ ] Enhanced financial reports
- [ ] Annual report (årsredovisning) generation
- [ ] K2/K3 formatting
- [ ] PDF export for Bolagsverket

### Phase 6: Governance & Documents (Month 6)
- [ ] Document management
- [ ] Certificate tracking
- [ ] Shareholder register
- [ ] Expiry reminders
- [ ] Fixed asset register
- [ ] Depreciation calculations

### Phase 7: Salary & Pension (Month 6-7)
- [ ] Employee register
- [ ] Tax table calculations
- [ ] Salary run processing
- [ ] Arbetsgivardeklaration generation
- [ ] Collectum file generation

### Phase 8: Nordnet & Investments (Month 7-8)
- [ ] Nordnet CSV import
- [ ] Transaction categorization and booking
- [ ] Currency account tracking
- [ ] Portfolio holdings snapshots
- [ ] Cost basis tracking (genomsnittsmetoden)
- [ ] Capital gains/losses calculation
- [ ] Dividend and withholding tax handling
- [ ] Investment performance reports

### Phase 9: Group & Consolidation (Month 8-9)
- [ ] Holding company setup
- [ ] Intercompany transactions
- [ ] Consolidated reports
- [ ] Group tax optimization views

### Phase 10: AI Advisory (Month 9+)
- [ ] Business analysis reports
- [ ] Tax planning suggestions
- [ ] Cash flow forecasting
- [ ] Anomaly detection

## Notes

### Compliance
- All verifications must have complete audit trail
- 7-year retention requirement (Bokföringslagen)
- System must support auditor access (read-only export)

### Backup Strategy
- Daily automated backup to separate location
- Monthly backup verification
- 10-year retention with yearly archives

### Data Migration
- Import historical SIE files from Adaro
- Verify opening balances
- Run parallel with Adaro for 1-2 months before switch

### Security
- Local deployment only
- User authentication
- Role-based access (admin, user, read-only)
- Encryption at rest for sensitive data

## References

- BAS-kontoplan: https://www.bas.se/
- SIE format: https://sie.se/
- Skatteverket: https://www.skatteverket.se/
- Bolagsverket: https://bolagsverket.se/
- ISO 20022: https://www.iso20022.org/
- Swedish tax tables: https://www.skatteverket.se/tabeller
