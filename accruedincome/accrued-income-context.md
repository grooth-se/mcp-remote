# Accrued Income Application - Development Context

## Project Overview

**Application name:** Accrued Income Calculator  
**Company:** Subseatec  
**Purpose:** Calculate and report accrued income for monthly financial statements  
**Current state:** Existing Python program with Tkinter GUI - to be rebuilt with Flask web interface

## Technology Stack

- **Backend:** Python with Flask
- **Frontend:** HTML/CSS/JavaScript (browser-based)
- **Database:** SQLite (for storing historical project accrued income tables)
- **Data processing:** Pandas
- **Visualization:** Matplotlib or Plotly (for project progress charts)
- **Deployment:** Docker container on network server
- **AI analysis:** Claude API integration (Opus 4.5 or similar)

## Accounting Standards

- Swedish K3
- IFRS 15 (Revenue from Contracts with Customers)

## Architecture

### Standalone Phase (Current Development)
- Single-user application
- No authentication required
- Runs locally or on network server
- Open access

### Future Integration
- Will connect to a central portal/start page
- User authentication handled by portal
- Role-based access control managed externally

## Data Flow

### 1. Data Import
**Source:** Monitor G5 ERP system (Subseatec)  
**Method:** Manual Excel export from Monitor reports (current)  
**Future consideration:** Investigate API access or automated export from Monitor G5 (server on LAN)

**Import files:** (Structure to be determined from existing code and example files)
- Project data
- Cost transactions
- Revenue transactions
- Verification register (complete account transactions)

### 2. Calculations

**Accrued income calculation per project:**
- Based on percentage of completion method (K3/IFRS 15 compliant)
- Calculation logic to be extracted from existing code

**Process:**
1. Import Excel files from Monitor G5
2. Process and validate data
3. Calculate project accrued income for current closing date
4. Generate project accrued income table (Pandas DataFrame)
5. Compare to previous month's table
6. Calculate differences (what needs to be booked)
7. Store results in SQLite database

### 3. Database Schema

**Historical storage (replacing current Excel file):**
- Project accrued income tables with closing dates
- One record per project per closing date
- Schema details to be designed based on existing Excel structure

### 4. Reports

**Required reports:**
1. **Project Revenue Report** - Revenue recognition per project
2. **Project Order Book Report** - Remaining contract values
3. **Project Profit and Change Report** - Profitability and month-over-month changes
4. **Booking Differences Table** - What to book for P&L and balance sheet
5. **Preliminary P&L Statement** - Based on verification register
6. **Preliminary Balance Sheet** - Based on verification register

**Report format:** Display in browser with option to export (format TBD)

### 5. Visualizations

**Project Progress Charts (per project):**
- Line chart over time (x-axis: historical closing dates)
- Lines to plot:
  - Total income (cumulative)
  - Total cost (cumulative)
  - Current period income
  - Current period cost
- Implementation exists in current code - to be migrated

### 6. AI Analysis

**Claude API integration for:**
- Analyze generated reports
- Prepare comments for monthly report
- Flag anomalies or potential errors:
  - Data inconsistencies
  - Unusual variances
  - Margin anomalies
  - Cost overruns
  - Missing or incomplete data

## File Structure

```
accruedincome/
├── app/
│   ├── __init__.py
│   ├── routes.py
│   ├── models.py
│   ├── calculations.py      # Accrued income logic
│   ├── import_handler.py    # Excel import processing
│   ├── reports.py           # Report generation
│   ├── charts.py            # Visualization generation
│   ├── ai_analysis.py       # Claude API integration
│   └── templates/
│       ├── base.html
│       ├── index.html
│       ├── import.html
│       ├── calculate.html
│       ├── reports.html
│       └── analysis.html
├── static/
│   ├── css/
│   └── js/
├── data/
│   └── example_files/       # Example Excel imports
├── legacy_code/             # Existing Tkinter code for reference
├── database/
│   └── accrued_income.db    # SQLite database
├── config.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## User Interface Flow

1. **Home/Dashboard** - Overview and navigation
2. **Import Data** - Upload Excel files from Monitor G5
3. **Select Closing Date** - Choose period for calculation
4. **Run Calculation** - Execute accrued income calculation
5. **View Results** - See calculated tables and differences
6. **Reports** - Generate and view/export reports
7. **Project Charts** - View project progress visualizations
8. **AI Analysis** - Get automated analysis and comments

## Development Phases

### Phase 1: Core Migration
- [ ] Set up Flask application structure
- [ ] Migrate Excel import logic from existing code
- [ ] Migrate calculation logic from existing code
- [ ] Implement SQLite database for historical data
- [ ] Basic web interface for import and calculation

### Phase 2: Reports and Visualization
- [ ] Implement all report generators
- [ ] Migrate chart generation from existing code
- [ ] Add P&L and Balance sheet from verification register
- [ ] Report viewing and export functionality

### Phase 3: AI Integration
- [ ] Integrate Claude API
- [ ] Implement report analysis
- [ ] Automated comment generation
- [ ] Anomaly detection

### Phase 4: Deployment
- [ ] Create Dockerfile
- [ ] Docker Compose configuration
- [ ] Network deployment documentation
- [ ] Prepare for portal integration

## Reference Materials

**Located in project folder:**
- `oldprogram/` - Existing Python/Tkinter application and Excel files
  - `acrued5.py` - Main launcher (entry point for legacy code)
  - Excel example files from Monitor G5
  
**Instructions for Claude Code:**
1. Review `oldprogram/acrued5.py` first to understand application structure
2. Trace imports to find calculation logic, data import routines, and chart generation
3. Examine Excel files in `oldprogram/` to understand data structure from Monitor G5

## Notes

- Single user operation - no concurrent access handling needed
- No authentication in standalone version
- Monitor G5 API access to be investigated as future enhancement
- Portal integration specifications to come later

## To Be Determined (from existing code review)

- Exact Excel file structure and column names
- Detailed calculation formulas
- Current data validation rules
- Existing chart specifications
- Any business logic edge cases
