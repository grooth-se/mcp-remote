# Monitor G5 Data Integration Service - Development Context

## Project Overview

**Application name:** Monitor G5 Data Integration Service  
**Company:** Subseatec  
**Purpose:** Extract data from Monitor G5 ERP via ODBC, store centrally, provide to other applications  
**Related projects:** Accrued Income Application, potentially others

## Architecture Decision

**Centralized Data Service** - One service fetches data from Monitor, other apps consume from shared storage.

Benefits:
- Single connection point to production ERP
- Consistent data across all consuming applications
- One place to maintain Monitor integration
- Reduced load on ERP system
- Daily refresh sufficient for financial reporting

## Connection Details

**Database:** SQL Anywhere (via ODBC)  
**Server IP:** 172.27.55.101  
**Port:** 2638  
**Username:** ReadOnlyUser  
**Password:** Subseatec1!  
**Company Code:** 001.1

**Connection String (Python pyodbc):**
```python
import pyodbc

conn_str = (
    "DRIVER={SQL Anywhere 17};"  # Or appropriate SQL Anywhere ODBC driver
    "HOST=172.27.55.101:2638;"
    "DATABASE=001.1;"
    "UID=ReadOnlyUser;"
    "PWD=Subseatec1!;"
)
connection = pyodbc.connect(conn_str)
```

**Note:** SQL Anywhere ODBC driver must be installed. May need to verify exact driver name on the system.

## Technology Stack

- **Backend:** Python with Flask (for REST API to consuming apps)
- **Database Connection:** pyodbc with SQL Anywhere driver
- **Data Processing:** Pandas
- **Storage:** SQLite or PostgreSQL (for extracted data)
- **Scheduling:** APScheduler or system cron for daily runs
- **Deployment:** Docker container on network server

## Phase 1: Schema Discovery

**Priority task:** Discover Monitor G5 database schema using ODBC connection and uploaded Excel exports.

### Excel Reference Files

Located in `MG5integration/` folder:
- Accrued income related exports
- Additional report exports

These files contain column headers that will help identify:
- Field names used by Monitor
- Data relationships
- Required data for Accrued Income app

### Schema Discovery Queries

**List all tables:**
```sql
SELECT table_name 
FROM sys.systable 
WHERE table_type = 'BASE'
ORDER BY table_name;
```

**List columns for a specific table:**
```sql
SELECT column_name, domain_name, width, scale, nulls
FROM sys.syscolumn c
JOIN sys.systable t ON c.table_id = t.table_id
WHERE t.table_name = 'TABLE_NAME'
ORDER BY column_id;
```

**Search for column by name (find which table contains a field):**
```sql
SELECT t.table_name, c.column_name
FROM sys.syscolumn c
JOIN sys.systable t ON c.table_id = t.table_id
WHERE c.column_name LIKE '%ProjectNumber%'
ORDER BY t.table_name;
```

**Search for tables by name pattern:**
```sql
SELECT table_name 
FROM sys.systable 
WHERE table_type = 'BASE' 
AND table_name LIKE '%Project%'
ORDER BY table_name;
```

### Discovery Workflow

1. Connect to Monitor database via ODBC
2. Read Excel exports to extract column header names
3. List all tables in the database
4. Search for tables containing columns from Excel exports
5. Document discovered schema
6. Map Monitor tables to required data for Accrued Income app
7. Build extraction queries

## Data Requirements

### For Accrued Income Application

Based on the Accrued Income context file, we need:

**Project Data:**
- Project number/code
- Project name/description
- Customer information
- Project status
- Contract value / order value
- Budget data
- Forecast data

**Financial Transactions:**
- Verification/voucher data
- Account postings
- Transaction dates
- Project-coded transactions
- Revenue and cost postings per project

**Customer Orders:**
- Order numbers
- Order values
- Invoiced amounts
- Order status

**Verification Register:**
- All account transactions
- For preliminary P&L and Balance sheet

### Additional Reports

(To be identified from uploaded Excel files)

## Application Structure

```
MG5integration/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── monitor_connection.py   # ODBC connection to Monitor
│   │   ├── local_storage.py        # SQLite/PostgreSQL for extracted data
│   │   └── schema_discovery.py     # Tools to explore Monitor schema
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── projects.py             # Project data extraction
│   │   ├── transactions.py         # Financial transactions
│   │   ├── orders.py               # Customer orders
│   │   ├── verifications.py        # Verification register
│   │   └── custom_reports.py       # Additional report data
│   ├── services/
│   │   ├── __init__.py
│   │   ├── scheduler.py            # Daily extraction scheduling
│   │   ├── data_transformer.py     # Transform Monitor data for apps
│   │   └── export_service.py       # Export to various formats
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py               # REST API for consuming apps
│   └── utils/
│       ├── __init__.py
│       ├── excel_analyzer.py       # Analyze Excel exports for schema hints
│       └── query_builder.py        # Build SQL queries
├── data/
│   ├── excel_exports/              # Uploaded Monitor Excel exports
│   ├── extracted/                  # Extracted data storage
│   └── schema/                     # Documented schema
├── docs/
│   └── monitor_schema.md           # Discovered schema documentation
├── tests/
├── scripts/
│   ├── discover_schema.py          # Schema discovery script
│   ├── test_connection.py          # Test ODBC connection
│   └── run_extraction.py           # Manual extraction trigger
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Configuration

```python
# config.py
import os

class Config:
    # Monitor G5 ODBC Connection
    MONITOR_HOST = os.environ.get('MONITOR_HOST', '172.27.55.101')
    MONITOR_PORT = os.environ.get('MONITOR_PORT', '2638')
    MONITOR_DATABASE = os.environ.get('MONITOR_DATABASE', '001.1')
    MONITOR_USER = os.environ.get('MONITOR_USER', 'ReadOnlyUser')
    MONITOR_PASSWORD = os.environ.get('MONITOR_PASSWORD', 'Subseatec1!')
    MONITOR_DRIVER = os.environ.get('MONITOR_DRIVER', 'SQL Anywhere 17')
    
    # Local Storage
    LOCAL_DB_PATH = os.environ.get('LOCAL_DB_PATH', './data/extracted/monitor_data.db')
    
    # Scheduling
    EXTRACTION_SCHEDULE = os.environ.get('EXTRACTION_SCHEDULE', '06:00')  # Daily at 6 AM
    
    # API
    API_HOST = os.environ.get('API_HOST', '0.0.0.0')
    API_PORT = int(os.environ.get('API_PORT', 5001))
    
    @property
    def monitor_connection_string(self):
        return (
            f"DRIVER={{{self.MONITOR_DRIVER}}};"
            f"HOST={self.MONITOR_HOST}:{self.MONITOR_PORT};"
            f"DATABASE={self.MONITOR_DATABASE};"
            f"UID={self.MONITOR_USER};"
            f"PWD={self.MONITOR_PASSWORD};"
        )
```

## REST API for Consuming Applications

The service exposes a REST API for other apps (like Accrued Income) to fetch data:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check and last extraction time |
| `/api/projects` | GET | Get all projects with optional filters |
| `/api/projects/{code}` | GET | Get single project details |
| `/api/transactions` | GET | Get transactions with date range filter |
| `/api/verifications` | GET | Get verification register |
| `/api/orders` | GET | Get customer orders |
| `/api/extract/trigger` | POST | Manually trigger extraction |
| `/api/extract/status` | GET | Check extraction status |
| `/api/schema` | GET | Get discovered schema documentation |

**Example usage from Accrued Income app:**
```python
import requests

# Get all active projects
response = requests.get('http://localhost:5001/api/projects?status=active')
projects = response.json()

# Get transactions for a date range
response = requests.get('http://localhost:5001/api/transactions', params={
    'from_date': '2025-01-01',
    'to_date': '2025-01-31'
})
transactions = response.json()
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Monitor G5 (SQL Anywhere)                    │
│                     172.27.55.101:2638                           │
└───────────────────────────┬─────────────────────────────────────┘
                            │ ODBC (ReadOnlyUser)
                            │ Daily scheduled extraction
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                 MG5 Integration Service                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │  Extractor  │  │  Local DB   │  │  REST API               │ │
│  │  (pyodbc)   │→ │  (SQLite)   │→ │  (Flask)                │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP REST API
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
      ┌──────────────┐ ┌──────────┐ ┌──────────────┐
      │Accrued Income│ │ Future   │ │ Future       │
      │     App      │ │ App 2    │ │ App 3        │
      └──────────────┘ └──────────┘ └──────────────┘
```

## Development Phases

### Phase 1: Connection & Schema Discovery
- [ ] Set up project structure
- [ ] Install SQL Anywhere ODBC driver
- [ ] Test ODBC connection to Monitor
- [ ] Analyze uploaded Excel exports for column names
- [ ] Discover and document Monitor database schema
- [ ] Identify tables for required data

### Phase 2: Data Extraction
- [ ] Build extraction queries based on discovered schema
- [ ] Create extractors for each data type:
  - Projects
  - Transactions/Verifications
  - Customer Orders
  - Additional report data
- [ ] Transform data to standardized format
- [ ] Store in local SQLite database

### Phase 3: REST API
- [ ] Flask REST API setup
- [ ] Endpoints for all data types
- [ ] Filtering and pagination
- [ ] Documentation (OpenAPI/Swagger)

### Phase 4: Scheduling & Automation
- [ ] Daily extraction scheduler
- [ ] Extraction logging and monitoring
- [ ] Error handling and notifications
- [ ] Manual trigger capability

### Phase 5: Deployment
- [ ] Dockerfile with SQL Anywhere driver
- [ ] Docker Compose configuration
- [ ] Network server deployment
- [ ] Integration testing with Accrued Income app

## SQL Anywhere ODBC Driver

**Installation on Ubuntu/Debian:**
```bash
# Download SQL Anywhere client from SAP
# Install the ODBC driver
sudo dpkg -i sqlany-client.deb
# Or use the tar.gz installer

# Configure ODBC
sudo odbcinst -i -d -f /opt/sqlanywhere/drivers/odbc.ini
```

**Docker considerations:**
- Include SQL Anywhere client in Docker image
- Or use a base image with SQL Anywhere drivers
- May need to obtain driver from SAP/Monitor

## Excel Export Analysis Tool

```python
# utils/excel_analyzer.py
import pandas as pd
from pathlib import Path

def analyze_excel_exports(folder_path: str) -> dict:
    """
    Analyze all Excel files in folder to extract column names.
    Returns dict mapping filename to list of columns.
    """
    results = {}
    folder = Path(folder_path)
    
    for excel_file in folder.glob('*.xlsx'):
        try:
            # Read just the header row
            df = pd.read_excel(excel_file, nrows=0)
            results[excel_file.name] = {
                'columns': list(df.columns),
                'column_count': len(df.columns)
            }
        except Exception as e:
            results[excel_file.name] = {'error': str(e)}
    
    return results

def find_common_columns(analysis: dict) -> list:
    """Find columns that appear in multiple exports."""
    from collections import Counter
    all_columns = []
    for file_data in analysis.values():
        if 'columns' in file_data:
            all_columns.extend(file_data['columns'])
    return Counter(all_columns).most_common()

def generate_search_queries(columns: list) -> list:
    """Generate SQL queries to find tables containing these columns."""
    queries = []
    for col in columns:
        query = f"""
SELECT t.table_name, c.column_name
FROM sys.syscolumn c
JOIN sys.systable t ON c.table_id = t.table_id
WHERE LOWER(c.column_name) LIKE LOWER('%{col}%')
ORDER BY t.table_name;
"""
        queries.append({'column': col, 'query': query})
    return queries
```

## Notes

### Security
- ReadOnlyUser credentials stored in environment variables
- No write access to Monitor database
- All connections are read-only queries

### Performance
- Extraction runs during off-hours (default 6 AM)
- Incremental extraction where possible (by date)
- Full extraction available on demand

### Error Handling
- Connection retry logic
- Extraction failure notifications
- Fallback to last successful extraction data

### Monitor Schema
- Schema will be documented in `docs/monitor_schema.md` as discovered
- May need to consult Monitor documentation or support for complex relationships

## Reference Files

**Excel exports to analyze (in MG5integration/data/excel_exports/):**
- (To be uploaded by user)
- Accrued income related exports
- Additional report exports

These files will be analyzed to:
1. Extract column names
2. Identify data relationships
3. Guide schema discovery
4. Build extraction queries

## First Steps for Claude Code Session

1. **Test connection:**
   ```python
   python scripts/test_connection.py
   ```

2. **Analyze Excel exports:**
   ```python
   python -c "from app.utils.excel_analyzer import analyze_excel_exports; print(analyze_excel_exports('data/excel_exports/'))"
   ```

3. **Discover schema:**
   ```python
   python scripts/discover_schema.py
   ```

4. **Document findings** in `docs/monitor_schema.md`
