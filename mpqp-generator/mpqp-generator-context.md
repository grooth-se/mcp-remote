# MPQP Generator - Development Context

## Project Overview

**Application name:** MPQP Generator  
**Company:** Subseatec  
**Users:** Engineers preparing manufacturing documentation  
**Purpose:** Automatically generate first drafts of MPQP, MPS, and ITP documents by learning from 15 years of historical project data

## Business Context

Subseatec prepares Manufacturing Procedure Specifications (MPS), Inspection and Test Plans (ITP), and combined Manufacturing Procedure Quality Plans (MPQP) for every order. These documents:

- Describe the complete manufacturing chain
- Reference process parameters and inspection points
- Link to controlling standards, procedures, and drawings
- Define reporting requirements and third-party witness points

The company has ~100 projects and 1000+ MPQP/MPS/ITP documents accumulated over 15 years, along with all reference documents (customer specs, standards, drawings).

**Current workflow:** Copy an old document, save with new name, manually modify based on new project requirements.

**Target workflow:** Upload new project documents → System finds similar projects → User approves references → System generates complete first draft → Chat-based refinement.

## Critical Requirement: Local Only

**All data is confidential.** The system must run entirely locally with no cloud services. This means:
- Local LLM (no OpenAI/Claude API)
- Local document processing
- Local vector database
- All data stays on Subseatec network

## Technology Stack

- **Backend:** Python with Flask
- **Local LLM:** Ollama with Llama 3 70B (or Mixtral 8x22B)
- **Document Processing:** 
  - PDF: PyMuPDF (fitz), pdfplumber
  - Word: python-docx
  - Excel: openpyxl
- **Vector Database:** ChromaDB or Qdrant (local deployment)
- **Embeddings:** Local embedding model (e.g., nomic-embed-text, bge-large)
- **Database:** PostgreSQL for metadata, SQLite for configuration
- **Deployment:** Docker on local server

## Hardware Requirements

**Recommended specification:**
- **GPU:** NVIDIA RTX 4090 (24GB VRAM) or RTX A6000 (48GB VRAM)
- **RAM:** 128GB (64GB minimum)
- **Storage:** 2TB SSD (for models, documents, vector database)
- **CPU:** 16+ cores for parallel document processing

**Model sizing:**
- Llama 3 70B Q4 quantized: ~40GB disk, runs on 24GB VRAM
- Embedding model: ~2GB
- Vector database: ~50GB for 1000+ documents with chunks

## Document Types

### Input Documents (Historical & New Projects)

| Document Type | Format | Typical Size | Content |
|---------------|--------|--------------|---------|
| Customer Specifications | PDF | 50-200 pages | Technical requirements, materials, testing |
| Standards | PDF | Varies | API, ASME, DNV requirements |
| Drawings | PDF | 1-50 pages | Component drawings, tolerances |
| Contracts | PDF/Word | 20-100 pages | Scope, deliverables, schedule |

**Typical new project package:** ~10 PDFs, ~300 pages total

### Output Documents (Generated)

| Document Type | Format | Description |
|---------------|--------|-------------|
| MPQP | Word/Excel | Combined manufacturing and quality plan |
| MPS | Word | Manufacturing procedure specification |
| ITP | Word/Excel | Inspection and test plan |

**Templates:** ~3 MPQP templates, ~2 MPS/ITP templates (user-selectable, client-dependent)

## Product Categories

| Category | Code | Description |
|----------|------|-------------|
| Top Tensioned Riser | TTR | Riser system for deepwater |
| Steel Catenary Riser | SCR | Free-hanging riser |
| Coiled Tubing Work Over Riser | CWOR | Intervention riser |
| Surface Landing String | SLS | Landing string system |
| Bodies | BODY | Valve bodies, housings |
| Valves | VALVE | Various valve types |
| Flanges | FLANGE | Connection flanges |

## Key Standards

| Standard | Description |
|----------|-------------|
| API 6A | Wellhead and Christmas tree equipment |
| API 17G | Subsea workover systems |
| API 1104 | Welding of pipelines |
| ASME VIII | Pressure vessel design |
| ASME IX | Welding qualifications |
| DNV-RP-0034 | Steel forgings for subsea applications |
| DNV-OS-C101 | Design of offshore structures |
| DNV-RP-C203 | Fatigue design |
| NORSOK M-650 | Steel forgings |

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MPQP Generator System                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │   Flask     │  │   Ollama    │  │   Vector Database       │ │
│  │   Web UI    │  │   (LLM)     │  │   (ChromaDB/Qdrant)     │ │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘ │
│         │                │                      │               │
│  ┌──────┴────────────────┴──────────────────────┴─────────────┐│
│  │                   Application Layer                         ││
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   ││
│  │  │  Document   │ │  Similarity │ │  Document           │   ││
│  │  │  Processor  │ │  Engine     │ │  Generator          │   ││
│  │  └─────────────┘ └─────────────┘ └─────────────────────┘   ││
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   ││
│  │  │  Template   │ │  Chat       │ │  Project            │   ││
│  │  │  Manager    │ │  Refiner    │ │  Indexer            │   ││
│  │  └─────────────┘ └─────────────┘ └─────────────────────┘   ││
│  └────────────────────────────────────────────────────────────┘│
│         │                                                       │
│  ┌──────┴─────────────────────────────────────────────────────┐│
│  │                   Data Layer                                ││
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   ││
│  │  │ PostgreSQL  │ │  Document   │ │  Generated          │   ││
│  │  │ (metadata)  │ │  Storage    │ │  Documents          │   ││
│  │  └─────────────┘ └─────────────┘ └─────────────────────┘   ││
│  └────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Initial Indexing (One-time + Updates)

```
Historical Project Folders
         │
         ▼
┌─────────────────────┐
│  Document Scanner   │  ← Scan all project folders
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Text Extraction    │  ← Extract text from PDF/Word/Excel
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Chunking &         │  ← Split into semantic chunks
│  Embedding          │  ← Generate embeddings locally
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Vector Database    │  ← Store embeddings + metadata
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Metadata Extract   │  ← LLM extracts: customer, product type,
│  (LLM)              │     materials, standards, etc.
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  PostgreSQL         │  ← Store structured metadata
└─────────────────────┘
```

### 2. New Project Document Generation

```
User uploads new project documents
         │
         ▼
┌─────────────────────┐
│  Document Processing│  ← Extract text, identify doc types
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Requirement        │  ← LLM extracts key requirements:
│  Extraction (LLM)   │     materials, standards, tests, etc.
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Similarity Search  │  ← Find similar historical projects
│                     │     Weight: customer > product > material > standard
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  User Review        │  ← Show similar projects, user approves
│                     │     or adjusts reference selection
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Document Generator │  ← LLM generates MPQP/MPS/ITP using:
│  (LLM)              │     - Selected template
│                     │     - Reference project documents
│                     │     - New project requirements
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Word/Excel Export  │  ← Generate formatted document
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Chat Refinement    │  ← User reviews, requests changes
│                     │     via chat interface
└─────────────────────┘
```

## Similarity Matching

### Weighting Factors

| Factor | Weight | Description |
|--------|--------|-------------|
| Customer | 40% | Same customer has highest preference |
| Product Type | 30% | Same riser type, valve, etc. |
| Material Grade | 15% | Same or similar steel grades |
| Standards | 15% | Overlapping standard requirements |

### Similarity Score Calculation

```python
def calculate_similarity(new_project, historical_project):
    score = 0.0
    
    # Customer match (exact)
    if new_project.customer == historical_project.customer:
        score += 0.40
    
    # Product type match
    if new_project.product_type == historical_project.product_type:
        score += 0.30
    elif same_category(new_project.product_type, historical_project.product_type):
        score += 0.15
    
    # Material overlap
    material_overlap = len(set(new_project.materials) & set(historical_project.materials))
    score += 0.15 * (material_overlap / max(len(new_project.materials), 1))
    
    # Standard overlap
    standard_overlap = len(set(new_project.standards) & set(historical_project.standards))
    score += 0.15 * (standard_overlap / max(len(new_project.standards), 1))
    
    return score
```

## Application Structure

```
mpqp-generator/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── main.py              # Dashboard, project list
│   │   ├── upload.py            # Document upload handling
│   │   ├── generate.py          # Document generation workflow
│   │   ├── chat.py              # Chat refinement API
│   │   └── admin.py             # Template management, indexing
│   ├── models/
│   │   ├── __init__.py
│   │   ├── project.py           # Project metadata model
│   │   ├── document.py          # Document model
│   │   ├── template.py          # MPQP/MPS/ITP templates
│   │   └── generation.py        # Generation job tracking
│   ├── services/
│   │   ├── __init__.py
│   │   ├── document_processor.py    # PDF/Word/Excel text extraction
│   │   ├── chunker.py               # Semantic chunking
│   │   ├── embedder.py              # Local embedding generation
│   │   ├── vector_store.py          # ChromaDB/Qdrant interface
│   │   ├── llm_client.py            # Ollama interface
│   │   ├── requirement_extractor.py # Extract requirements from specs
│   │   ├── similarity_engine.py     # Find similar projects
│   │   ├── document_generator.py    # Generate MPQP/MPS/ITP
│   │   ├── template_filler.py       # Fill Word/Excel templates
│   │   └── chat_refiner.py          # Handle refinement chat
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── pdf_utils.py
│   │   ├── word_utils.py
│   │   ├── excel_utils.py
│   │   └── text_utils.py
│   └── templates/
│       ├── base.html
│       ├── dashboard.html
│       ├── upload.html
│       ├── similarity_review.html
│       ├── generation_progress.html
│       ├── document_review.html
│       └── chat.html
├── static/
│   ├── css/
│   └── js/
├── data/
│   ├── historical_projects/     # Indexed historical data (read-only)
│   ├── new_projects/            # Uploaded new project docs
│   ├── generated/               # Generated documents
│   └── templates/               # MPQP/MPS/ITP templates
├── models/
│   └── prompts/                 # LLM prompt templates
├── tests/
├── scripts/
│   ├── index_historical.py      # One-time indexing script
│   └── update_index.py          # Incremental indexing
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Database Schema

### PostgreSQL (Project Metadata)

```sql
-- Customers
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    code TEXT,                      -- Short code if used
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Historical projects
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    project_number TEXT UNIQUE NOT NULL,
    project_name TEXT,
    customer_id INTEGER REFERENCES customers(id),
    product_type TEXT,              -- TTR, SCR, CWOR, SLS, BODY, VALVE, FLANGE
    product_category TEXT,          -- Riser, Component
    materials TEXT[],               -- Array of material grades used
    standards TEXT[],               -- Array of standards referenced
    folder_path TEXT NOT NULL,      -- Path to project folder
    indexed_at TIMESTAMP,
    metadata JSONB,                 -- Additional extracted metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Documents within projects
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    document_type TEXT,             -- MPQP, MPS, ITP, SPEC, DRAWING, CONTRACT
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_format TEXT,               -- PDF, DOCX, XLSX
    page_count INTEGER,
    extracted_text TEXT,            -- Full extracted text
    metadata JSONB,                 -- Document-specific metadata
    indexed_at TIMESTAMP,
    embedding_ids TEXT[],           -- References to vector DB chunks
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- MPQP/MPS/ITP templates
CREATE TABLE templates (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    document_type TEXT NOT NULL,    -- MPQP, MPS, ITP
    format TEXT NOT NULL,           -- DOCX, XLSX
    file_path TEXT NOT NULL,
    customer_id INTEGER REFERENCES customers(id),  -- NULL = generic
    structure JSONB,                -- Template structure definition
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Generation jobs
CREATE TABLE generation_jobs (
    id SERIAL PRIMARY KEY,
    status TEXT DEFAULT 'pending',  -- pending, processing, review, completed, failed
    template_id INTEGER REFERENCES templates(id),
    
    -- Input
    new_project_name TEXT,
    customer_id INTEGER REFERENCES customers(id),
    product_type TEXT,
    uploaded_documents JSONB,       -- List of uploaded file paths
    extracted_requirements JSONB,   -- LLM-extracted requirements
    
    -- Similarity
    similar_projects JSONB,         -- Ranked list of similar projects
    selected_references INTEGER[],  -- User-approved reference project IDs
    
    -- Output
    generated_document_path TEXT,
    generation_log TEXT,
    
    -- Chat refinement
    chat_history JSONB,
    current_version INTEGER DEFAULT 1,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Refinement versions
CREATE TABLE document_versions (
    id SERIAL PRIMARY KEY,
    generation_job_id INTEGER REFERENCES generation_jobs(id),
    version_number INTEGER,
    file_path TEXT,
    changes_description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## LLM Prompts

### Requirement Extraction Prompt

```
You are an expert in offshore oil & gas manufacturing documentation. 
Analyze the following specification documents and extract key requirements.

Documents:
{document_texts}

Extract and structure the following information:
1. Customer name and project reference
2. Product type and description
3. Material specifications (steel grades, heat treatment requirements)
4. Applicable standards (API, ASME, DNV, NORSOK, etc.)
5. Testing requirements (NDT, mechanical testing, pressure testing)
6. Quality requirements (certification level, third-party inspection)
7. Welding requirements if applicable
8. Special requirements or deviations from standards

Output as structured JSON.
```

### Document Generation Prompt

```
You are an expert in creating Manufacturing Procedure Quality Plans (MPQP) 
for offshore oil & gas components.

NEW PROJECT REQUIREMENTS:
{extracted_requirements}

REFERENCE PROJECT MPQP (similar product for same customer):
{reference_mpqp_text}

TEMPLATE STRUCTURE:
{template_structure}

Generate a complete MPQP for the new project following the template structure.
For each section:
1. Use the reference MPQP as a guide for format and level of detail
2. Update all references to match new project requirements
3. Include correct standard references from the new specification
4. Update material specifications as per new requirements
5. Adjust inspection and test points as needed

Maintain the professional technical writing style of the reference document.
Output the complete document content section by section.
```

### Chat Refinement Prompt

```
You are assisting with refinement of a generated MPQP document.

CURRENT DOCUMENT:
{current_document}

USER REQUEST:
{user_message}

CONTEXT (if referring to specific requirements):
{relevant_context}

Make the requested changes while maintaining document consistency.
Explain what changes you made.
Output the updated section(s).
```

## Web Interface Workflow

### 1. Dashboard
- List recent generation jobs
- Quick stats (projects indexed, documents generated)
- Start new generation

### 2. New Generation - Upload
- Select document type (MPQP, MPS, or ITP)
- Select template
- Enter customer name (autocomplete from existing)
- Enter product type (dropdown)
- Upload project documents (drag & drop, multiple files)
- Submit for processing

### 3. Processing Status
- Show extraction progress
- Display extracted requirements for review
- User can edit/correct extracted data

### 4. Similarity Review
- Show top 5-10 similar historical projects
- Display similarity scores and matching factors
- Show preview of reference MPQP sections
- User selects which projects to use as references
- Proceed to generation

### 5. Generation Progress
- Show generation progress
- Stream partial output if possible
- Estimated time remaining

### 6. Document Review
- Display generated document
- Side-by-side with reference if desired
- Highlight sections that may need review
- Download draft button

### 7. Chat Refinement
- Chat interface below document view
- User requests changes in natural language
- System updates document
- Version history sidebar
- Download final version

## Development Phases

### Phase 1: Foundation
- [ ] Project structure setup
- [ ] Database schema implementation
- [ ] Ollama integration and testing
- [ ] Basic Flask app with authentication

### Phase 2: Document Processing
- [ ] PDF text extraction (PyMuPDF)
- [ ] Word document parsing (python-docx)
- [ ] Excel parsing (openpyxl)
- [ ] Semantic chunking implementation
- [ ] Local embedding model setup

### Phase 3: Historical Indexing
- [ ] Project folder scanner
- [ ] Batch document processing
- [ ] Vector database population
- [ ] Metadata extraction with LLM
- [ ] PostgreSQL metadata storage

### Phase 4: Similarity Engine
- [ ] Multi-factor similarity calculation
- [ ] Vector similarity search
- [ ] Metadata-based filtering
- [ ] Ranking and scoring
- [ ] UI for similarity review

### Phase 5: Document Generation
- [ ] Template management system
- [ ] Requirement extraction pipeline
- [ ] Document generation prompts
- [ ] Word document generation
- [ ] Excel document generation

### Phase 6: Chat Refinement
- [ ] Chat interface implementation
- [ ] Context-aware refinement
- [ ] Version tracking
- [ ] Change highlighting

### Phase 7: Polish & Deployment
- [ ] UI/UX improvements
- [ ] Error handling and logging
- [ ] Docker containerization
- [ ] Documentation
- [ ] User training materials

## Configuration

```python
# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key')
    
    # PostgreSQL
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'mpqp_generator')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'mpqp')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')
    
    # Ollama (Local LLM)
    OLLAMA_HOST = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
    LLM_MODEL = os.environ.get('LLM_MODEL', 'llama3:70b-instruct-q4_K_M')
    EMBEDDING_MODEL = os.environ.get('EMBEDDING_MODEL', 'nomic-embed-text')
    
    # Vector Database
    VECTOR_DB_PATH = os.environ.get('VECTOR_DB_PATH', './data/vectordb')
    
    # Paths
    HISTORICAL_PROJECTS_PATH = os.environ.get('HISTORICAL_PATH', '/data/projects')
    UPLOAD_FOLDER = './data/new_projects'
    GENERATED_FOLDER = './data/generated'
    TEMPLATE_FOLDER = './data/templates'
    
    # Processing
    CHUNK_SIZE = 1000  # tokens
    CHUNK_OVERLAP = 200
    MAX_SIMILAR_PROJECTS = 10
    
    # LLM Settings
    LLM_TEMPERATURE = 0.3  # Lower for more consistent output
    LLM_MAX_TOKENS = 4096
```

## Docker Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - /path/to/historical/projects:/data/projects:ro
    environment:
      - POSTGRES_HOST=db
      - OLLAMA_HOST=http://ollama:11434
    depends_on:
      - db
      - ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  db:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=mpqp_generator
      - POSTGRES_USER=mpqp
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_models:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

volumes:
  postgres_data:
  ollama_models:
```

## Notes

### LLM Context Window
- Llama 3 70B has 8K context window
- For large documents, use chunking and summarization
- Consider Llama 3.1 70B (128K context) when available in Ollama

### Document Quality
- OCR quality affects extraction accuracy
- Consider pre-processing scanned PDFs with OCR enhancement
- Handle tables specially (may need table extraction)

### Performance Optimization
- Index historical projects incrementally
- Cache embeddings for frequently accessed documents
- Use async processing for large uploads
- Consider batch generation for similar documents

### Security
- All processing is local
- No external API calls
- Document storage on internal network only
- User authentication for access control

## References

- Ollama: https://ollama.ai/
- ChromaDB: https://www.trychroma.com/
- python-docx: https://python-docx.readthedocs.io/
- PyMuPDF: https://pymupdf.readthedocs.io/
- LangChain (optional): https://python.langchain.com/
