# Development Projects - Summary

**Date:** February 17, 2026  
**Prepared for:** Claude Code multi-session development

---

## Overview

**Six projects** for Subseatec plus **one personal project** (Family Office). All Subseatec apps connect through a central portal on the Ubuntu server.

### Infrastructure

**Server:** 172.27.55.104  
- HPE ProLiant ML110 Gen11, 64GB RAM
- Ubuntu Server with GUI
- Docker installed
- SSH user: administrator

---

## Project 0: Subseatec App Portal (NEW - Build First)

**Folder:** `subseatec-portal/`  
**Purpose:** Central login and app launcher for all Subseatec applications  
**Port:** 5000 (behind Nginx on 80/443)

### Features
- User authentication (12 users)
- Per-user app permissions
- Admin user management
- App health monitoring
- JWT token validation for apps
- Nginx reverse proxy with SSL

### Connected Apps (7 total)
| App | Port | Status |
|-----|------|--------|
| Accrued Income | 5001 | In development |
| HeatSim | 5002 | Planned |
| MPQP Generator | 5003 | Planned |
| MG5 Integrator | 5004 | Planned |
| Durabler2 | 5005 | Planned |
| SPInventory | 5006 | Planned |
| Heat Treatment Tracker | 5007 | External developer |

---

## Project 1: Accrued Income Calculator

**Folder:** `accruedincome/`  
**Status:** Session started  
**AI:** Cloud OK (internal financial data)

### Purpose
Calculate and report accrued income for monthly financial statements, replacing existing Tkinter application with web-based Flask interface.

### Key Features
- Import data from Monitor G5 ERP (currently via Excel export)
- Calculate project accrued income per K3/IFRS 15
- Compare to previous month, generate booking differences
- Store historical data in SQLite (replacing Excel)
- Generate reports: Revenue, Order Book, Profit & Change
- Project progress charts (time-lapse of income/cost)
- Preliminary P&L and Balance sheet from verification register
- AI analysis of reports with anomaly detection

### Technology
- Flask, Pandas, SQLite, Matplotlib
- Claude API for report analysis
- Docker deployment

### Reference
- `oldprogram/acrued5.py` - Existing code for reference
- Excel files in `oldprogram/`

---

## Project 2: Monitor G5 API Integration

**Folder:** `MG5integration/`  
**Status:** Ready to start (waiting for IT details)  
**AI:** None required

### Purpose
Automate data extraction from Monitor G5 ERP to replace manual Excel exports. Provides data to Accrued Income app and potentially other applications.

### Key Features
- Connect to Monitor G5 REST API on LAN
- Query projects, customer orders, vouchers, accounting data
- Transform data to application-ready format
- Export to JSON, Excel, or direct database insert
- REST API for other apps to request data

### Technology
- Flask, requests/httpx, Pandas
- SQLite (shared with Accrued Income app)
- Docker deployment

### Prerequisites from IT
- Monitor G5 server URL and port
- Company code
- API user credentials
- Network access confirmation

### Monitor API Reference
- Documentation: https://api.monitor.se
- Free read access included with license
- OData-style query parameters

---

## Project 3: Materials Simulation Platform

**Folder:** `heatsim/`  
**Status:** Context file ready  
**AI:** Cloud OK (literature data, simulations)

### Purpose
Simulate heat transfer in forgings and weldments, optimize thermal processes to achieve target microstructures, automate COMSOL model generation.

### Key Features
- Material database with temperature-dependent properties
- Two data sources per grade: Standard (literature) and Subseatec (proprietary)
- CCT/TTT diagram storage (manually digitized)
- Two-tier simulation: Fast Python → Accurate COMSOL
- Heat treatment optimization (quenching parameters)
- Welding simulation (GTAW, MIG/MAG, SAW, AM)
- Interpass temperature optimization for no-PWHT welds
- Weld log comparison for model validation
- 3D visualization with PyVista, time-lapse animations

### Pre-populated Steel Grades (20)
S355J2G3, AISI 4130, AISI 4340, AISI 4330V, AISI 8630, A182 F22, A182 F11, A182 F5, 304, 316, 316L, Duplex 2205, Duplex 2507, 410, H13, P20, 300M, Inconel 625, Inconel 718, AISI 1045

### Technology
- Flask, NumPy, SciPy, FiPy, Pandas
- COMSOL Multiphysics (Heat Transfer module) via mph library
- PyVista for visualization, MoviePy for animations
- PostgreSQL for material data, SQLite for config
- Docker deployment

### Hardware
- Requires COMSOL license (available)
- Standard server hardware sufficient

---

## Project 4: MPQP Generator

**Folder:** `mpqp-generator/`  
**Status:** Context file ready  
**AI:** **Local only** (confidential customer data)

### Purpose
Automatically generate first drafts of MPQP, MPS, and ITP documents by learning from 15 years of historical project data.

### Key Features
- Index historical projects (~100 projects, 1000+ documents)
- Extract and embed document content locally
- Multi-factor similarity matching:
  - Customer (40%), Product type (30%), Material (15%), Standards (15%)
- User reviews and approves reference projects
- Generate complete first draft in Word/Excel
- Chat-based refinement after generation
- Version tracking

### Document Types
- **Input:** Customer specs (PDF), standards, drawings, contracts
- **Output:** MPQP, MPS, ITP (Word or Excel based on template)

### Product Categories
- Risers: TTR, SCR, CWOR, SLS
- Components: Bodies, Valves, Flanges

### Key Standards
API 6A, API 17G, API 1104, ASME VIII & IX, DNV-RP-0034, DNV-OS-C101, DNV-RP-C203

### Technology
- Flask, python-docx, openpyxl, PyMuPDF
- **Ollama with Llama 3 70B** (local LLM)
- ChromaDB or Qdrant (local vector database)
- Local embedding model (nomic-embed-text)
- PostgreSQL for metadata
- Docker deployment

### Hardware Requirements
- **GPU:** NVIDIA RTX 4090 (24GB) or RTX A6000 (48GB)
- **RAM:** 128GB (64GB minimum)
- **Storage:** 2TB SSD
- **CPU:** 16+ cores

## Project 5: Family Office Administration

**Folder:** `familjekontor/` (suggested)  
**Status:** Context file ready  
**AI:** **Local only** (financial data confidentiality)

### Purpose
Streamline administration of family-owned companies (4 AB + 1 HB), reducing 5-6 hours/week manual work. Complete accounting, tax reporting, and corporate governance.

### Company Structure
- 4 Aktiebolag (AB) - target: group structure with holding company
- 1 Handelsbolag (HB) - standalone
- 3 employees across companies
- ~500 transactions/year, growing to ~2000
- Banks: SEB, Nordea + Nordnet (trading)

### Key Features (Phased)
**Phase 1-2:** Core accounting (K2/K3), AI invoice processing, SIE import from Adaro  
**Phase 3:** Bank payment files (SEB/Nordea pain.001 format)  
**Phase 4:** VAT reporting, deadline tracking with reminders  
**Phase 5:** Reports & Statements  
**Phase 6:** Governance & Documents  
**Phase 7:** Salary & Pension  
**Phase 8:** Nordnet & Investments (transactions, holdings, portfolio)  
**Phase 9:** Group consolidation  
**Phase 10:** AI advisory

### Technology
- Flask, PostgreSQL, SQLAlchemy
- **Ollama with Llama 3 70B** (local AI for invoice processing)
- Tesseract/EasyOCR (local OCR)
- ReportLab (PDF), openpyxl (Excel)
- Docker deployment

### Hardware
- Can share with MPQP Generator GPU setup
- Or run lighter models for lower transaction volume
- Minimum: 8 cores, 32GB RAM (CPU inference acceptable for ~500 tx/year)

---

## Updated Shared Infrastructure

### AI Hardware Strategy
| Application | AI Requirement | Hardware |
|-------------|---------------|----------|
| Accrued Income | Cloud Claude API | None |
| MG5 Integration | None | None |
| HeatSim | Cloud Claude API | None |
| MPQP Generator | Local Llama 3 70B | RTX 4090 + 128GB RAM |
| Family Office | Local Llama 3 70B | Can share MPQP hardware |

**Single GPU server can serve both MPQP Generator and Family Office** if they're on the same network.

---

## Updated Development Priority

| Priority | Project | Timeline | Notes |
|----------|---------|----------|-------|
| 1 | Accrued Income | Running | Immediate business value |
| 2 | MG5 Integration | Ready | Waiting for IT details |
| 3 | Family Office | Ready | Address admin pain points |
| 4 | HeatSim | Ready | High technical value |
| 5 | MPQP Generator | Ready | Most complex, needs GPU |

Note: Family Office moved up in priority due to weekly time savings potential (5-6 hrs/week = 250+ hrs/year).

---

### Database Strategy
| Database | Used By | Purpose |
|----------|---------|---------|
| SQLite | All apps | User config, light data, shared data files |
| PostgreSQL | HeatSim, MPQP | Heavy data, material properties, document metadata |

### Deployment
All applications containerized with Docker, deployed on Subseatec network server.

### Common Technology
- Python 3.12
- Flask for web interface
- SQLAlchemy for database ORM
- Pandas for data processing
- Docker + Docker Compose

---

## Cloud vs Local AI Decision

| Application | Recommendation | Reason |
|-------------|---------------|--------|
| Accrued Income | Cloud OK | Internal financial data |
| MG5 Integration | N/A | No AI |
| HeatSim | Cloud OK | Mostly literature data |
| MPQP Generator | **Local required** | Customer confidential data |

### Local AI Hardware Investment
- RTX 4090: ~$1,800
- Additional RAM: ~$300
- SSD: ~$150
- **Total: ~$2,250**

Break-even vs cloud costs: 6-18 months depending on usage.

---

## Development Priority

Suggested order based on dependencies and complexity:

1. **Accrued Income** - Already started, immediate business value
2. **MG5 Integration** - Enables automation for #1, waiting for IT info
3. **HeatSim** - Independent, high technical value
4. **MPQP Generator** - Most complex, requires hardware setup

---

## Files Created

| File | Location | Description |
|------|----------|-------------|
| Context MD | `accruedincome/` | Accrued Income app specification |
| Context MD | `MG5integration/` | Monitor API integration specification |
| Context MD | `heatsim/` | Materials simulation specification |
| Context MD | `mpqp-generator/` | MPQP generator specification |
| Context MD | `familjekontor/` | Family office admin specification |

---

## Next Steps

1. Continue Accrued Income session (already running)
2. Obtain Monitor G5 API details from IT
3. Create `familjekontor` folder and start session
4. Procure GPU hardware (RTX 4090) - serves both MPQP and Family Office
5. Start remaining sessions as bandwidth allows

---

*Generated: February 5, 2026*
