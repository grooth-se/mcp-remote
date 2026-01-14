## CLAUDE.md - Mechanical Testing Analysis System (Durabler)

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**Durabler** is a comprehensive mechanical testing analysis system for an ISO 17025 accredited materials testing laboratory. The system handles data acquisition from MTS testing equipment, performs standardized calculations with uncertainty propagation, generates accredited test reports, and maintains full audit traceability in a PostgreSQL database.

### Core Objectives
1. Import and process test data from MTS Landmark 500kN servo-dynamic test machine
2. Perform calculations according to international standards (ASTM, ISO)
3. Generate accredited test reports meeting ISO 17025 and Swedac STAFS-2020
4. Maintain complete data traceability and audit logging
5. Store all test data, analysis results, plots, and photos in PostgreSQL

---

## Technical Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Database | PostgreSQL (with psycopg2 or asyncpg) |
| GUI | Tkinter |
| Reports | ReportLab for PDF generation, Jinja2 for templates |
| Plotting | Matplotlib |
| Data Processing | NumPy, SciPy, Pandas |
| Uncertainty | uncertainties package (or custom implementation) |

---

## Test Methods and Standards

| Test Method | Primary Standard | Secondary Standards | Status |
|-------------|------------------|---------------------|--------|
| Tensile Testing | ASTM E8/E8M | ISO 6892-1 | First issue complete |
| Sonic Resonance | Modified ASTM E1875 | - | First issue complete |
| FCGR (Fatigue Crack Growth Rate) | ASTM E647 | - | Draft in progress |
| CTOD Testing | ASTM E1820 | ASTM E1290, BS 7448 | Not started |
| KIC (Fracture Toughness) | ASTM E399 | ASTM E1820 | Not started |
| Vickers Hardness | ISO 6507-1 | ASTM E92, ASTM E384 | Not started |

### Key Calculations by Test Method

**Tensile (E8/E8M, ISO 6892-1):**
- Yield strength Rp0.2 (offset method)
- Ultimate tensile strength Rm
- Elongation at fracture A%
- Reduction of area Z%
- Young's modulus E
- Uniform elongation Ag
- True stress
- Ludviks coefficient
- Strain rate, stress rate and displacement rate to verify standard comliance

**CTOD (E1820, E1290):**
- Crack tip opening displacement δ
- J-integral conversion
- Plastic component calculation
- Validity checks per standard

**KIC (E399):**
- Plane-strain fracture toughness
- Validity criteria verification
- Load-displacement analysis

**FCGR (E647):**
- da/dN vs ΔK curves
- Paris law coefficients (C, m)
- Threshold ΔKth determination
- Crack length from compliance

**Sonic Resonance (Modified E1875):**
- Dynamic Young's modulus
- Shear modulus
- Poisson's ratio
- Resonant frequency analysis

**Vickers Hardness (ISO 6507-1, E92, E384):**
- HV calculation from diagonal measurements
- Load-dependent hardness
- Statistical analysis of indentations

---

## Project Structure

```
durabler/
├── CLAUDE.md                   # This file
├── README.md                   # User documentation
├── requirements.txt            # Python dependencies
├── launcher.py                 # Main application launcher
│
├── utils/                      # Shared utility modules
│   ├── __init__.py
│   ├── data_acquisition/       # MTS data import (CSV, Excel)
│   │   ├── __init__.py
│   │   ├── mts_csv_parser.py   # Parse MTS TestSuite CSV exports
│   │   ├── mts_excel_parser.py # Parse MTS system reports (Excel)
│   │   └── validators.py       # Data validation on import
│   │
│   ├── analysis/               # Calculation engines
│   │   ├── __init__.py
│   │   ├── curve_fitting.py    # Regression, interpolation
│   │   ├── statistics.py       # Statistical analysis
│   │   ├── uncertainty.py      # Uncertainty propagation (GUM)
│   │   └── signal_processing.py # Filtering, smoothing
│   │
│   ├── database/               # PostgreSQL interface
│   │   ├── __init__.py
│   │   ├── models.py           # SQLAlchemy or dataclass models
│   │   ├── connection.py       # Connection management
│   │   ├── queries.py          # CRUD operations
│   │   ├── migrations/         # Schema migrations
│   │   └── blob_storage.py     # Binary data (plots, photos)
│   │
│   ├── reporting/              # Report generation
│   │   ├── __init__.py
│   │   ├── pdf_generator.py    # ReportLab PDF creation
│   │   ├── template_engine.py  # Jinja2 template handling
│   │   └── report_numbering.py # Unique report ID generation
│   │
│   ├── validation/             # Data and result validation
│   │   ├── __init__.py
│   │   ├── limit_checks.py     # Acceptance criteria
│   │   ├── standard_validity.py # Standard-specific validity
│   │   └── schemas.py          # Input data schemas
│   │
│   ├── audit/                  # ISO 17025 compliance
│   │   ├── __init__.py
│   │   ├── logger.py           # Audit trail logging
│   │   ├── user_auth.py        # User identification
│   │   ├── change_tracking.py  # Data modification history
│   │   └── document_control.py # Version management
│   │
│   └── ui/                     # Tkinter GUI components
│       ├── __init__.py
│       ├── widgets.py          # Reusable custom widgets
│       ├── dialogs.py          # Common dialogs
│       ├── plotting.py         # Matplotlib integration
│       └── themes.py           # Visual styling
│
├── tests/                      # Test method implementations
│   ├── __init__.py
│   ├── test_analysis/          # Unit tests and reference data
│   │   ├── reference_tensile.csv
│   │   ├── reference_fcgr.csv
│   │   └── test_calculations.py
│   │
│   └── test_methods/           # Main test programs
│       ├── __init__.py
│       ├── tensile_e8.py       # Tensile testing (ASTM E8)
│       ├── sonic_e1875.py      # Sonic resonance
│       ├── fcgr_e647.py        # Fatigue crack growth (draft)
│       ├── ctod_e1820.py       # CTOD testing (to create)
│       ├── kic_e399.py         # KIC testing (to create)
│       └── vickers_iso6507.py  # Vickers hardness (to create)
│
├── templates/
│   └── report_templates/       # Jinja2/ReportLab templates
│       ├── tensile_report.jinja2
│       ├── sonic_report.jinja2
│       ├── fcgr_report.jinja2
│       ├── ctod_report.jinja2
│       ├── kic_report.jinja2
│       └── vickers_report.jinja2
│
├── reports/                    # Generated PDF reports
│   └── .gitkeep
│
├── data/
│   └── test_data/              # Raw test data files
│       └── .gitkeep
│
├── docs/
│   ├── standards/              # Standard interpretation notes
│   │   ├── E8_implementation.md
│   │   └── uncertainty_budget.md
│   └── validation/             # IQ/OQ/PQ documentation
│       └── validation_protocol.md
│
└── config/
    ├── database.ini            # Database connection settings
    ├── logging.ini             # Logging configuration
    └── app_settings.json       # Application preferences
```

---

## Database Schema

### Core Tables

```sql
-- Unique identifiers for all entities
-- Format: DURABLER-YYYY-NNNNNN (e.g., DURABLER-2026-000142)

specimens (
    id SERIAL PRIMARY KEY,
    specimen_id VARCHAR(50) UNIQUE NOT NULL,  -- Lab specimen identifier
    material VARCHAR(100),
    batch_number VARCHAR(50),
    geometry JSONB,                           -- Dimensions, shape
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(50),                   -- User ID
    metadata JSONB
)

test_records (
    id SERIAL PRIMARY KEY,
    test_id VARCHAR(50) UNIQUE NOT NULL,      -- Internal test ID
    specimen_id INTEGER REFERENCES specimens(id),
    test_method VARCHAR(20),                  -- 'TENSILE', 'FCGR', etc.
    test_standard VARCHAR(50),                -- 'ASTM E8/E8M-22'
    test_date TIMESTAMP,
    operator VARCHAR(50),
    machine_id VARCHAR(50),
    temperature NUMERIC,
    humidity NUMERIC,
    raw_data_path VARCHAR(255),
    status VARCHAR(20),                       -- 'DRAFT', 'REVIEWED', 'APPROVED'
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(50)
)

analysis_results (
    id SERIAL PRIMARY KEY,
    test_id INTEGER REFERENCES test_records(id),
    parameter_name VARCHAR(50),               -- 'Rp02', 'Rm', 'da_dN', etc.
    value NUMERIC,
    uncertainty NUMERIC,
    unit VARCHAR(20),
    calculation_method VARCHAR(100),
    is_valid BOOLEAN,
    validity_notes TEXT,
    calculated_at TIMESTAMP DEFAULT NOW(),
    calculated_by VARCHAR(50)
)

reports (
    id SERIAL PRIMARY KEY,
    report_number VARCHAR(50) UNIQUE NOT NULL, -- Accredited report number
    test_id INTEGER REFERENCES test_records(id),
    report_type VARCHAR(20),
    pdf_blob BYTEA,
    generated_at TIMESTAMP DEFAULT NOW(),
    generated_by VARCHAR(50),
    approved_at TIMESTAMP,
    approved_by VARCHAR(50),
    revision INTEGER DEFAULT 1
)

blobs (
    id SERIAL PRIMARY KEY,
    reference_type VARCHAR(20),               -- 'TEST', 'SPECIMEN', 'REPORT'
    reference_id INTEGER,
    blob_type VARCHAR(20),                    -- 'PLOT', 'PHOTO', 'RAW_DATA'
    description VARCHAR(255),
    data BYTEA,
    mime_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(50)
)

audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    user_id VARCHAR(50) NOT NULL,
    action VARCHAR(20),                       -- 'CREATE', 'UPDATE', 'DELETE', 'VIEW'
    table_name VARCHAR(50),
    record_id INTEGER,
    old_values JSONB,
    new_values JSONB,
    reason TEXT,                              -- Required for modifications
    ip_address VARCHAR(45)
)

calibration_records (
    id SERIAL PRIMARY KEY,
    equipment_id VARCHAR(50),
    calibration_date DATE,
    valid_until DATE,
    certificate_number VARCHAR(100),
    certificate_blob BYTEA,
    calibrated_by VARCHAR(100),
    parameters JSONB
)
```

---

## ISO 17025 and Swedac STAFS-2020 Compliance Requirements

### Mandatory Implementation

1. **Traceability (Clause 7.6)**
   - Every data modification must be logged with: timestamp, user, old value, new value, reason
   - Original data must never be deleted, only marked as superseded
   - All calculations must be traceable to raw data

2. **Audit Trail (Clause 7.11)**
   - `audit_log` table must capture ALL database operations
   - User authentication required before any data entry
   - Automatic timestamps, no manual override allowed

3. **Document Control (Clause 8.3)**
   - Report templates under version control
   - Each report revision creates new record, keeps history
   - Unique report numbering system

4. **Measurement Uncertainty (Clause 7.6)**
   - Every reported result must include uncertainty
   - Uncertainty budgets documented per test method
   - GUM (Guide to Uncertainty in Measurement) methodology

5. **Calibration Linkage (Clause 6.4)**
   - Test records must link to valid calibration certificates
   - System warns if calibration expired at test date
   - Calibration data stored and retrievable

6. **Non-conformance (Clause 7.10)**
   - Flag system for out-of-specification results
   - Non-conformance must be recorded and tracked
   - Root cause and corrective action fields

### Implementation Pattern

```python
# Every database write must follow this pattern:
def save_result(test_id: int, parameter: str, value: float, 
                uncertainty: float, user_id: str, reason: str = None) -> int:
    """
    Save analysis result with full audit trail.
    
    Parameters
    ----------
    test_id : int
        Reference to test_records.id
    parameter : str
        Parameter name (e.g., 'Rp02', 'Rm')
    value : float
        Calculated value
    uncertainty : float
        Measurement uncertainty (k=2)
    user_id : str
        Authenticated user identifier
    reason : str, optional
        Required if modifying existing value
        
    Returns
    -------
    int
        New record ID
        
    Raises
    ------
    AuditError
        If modification attempted without reason
    """
    with database.atomic_transaction() as txn:
        try:
            # Check for existing value
            existing = get_existing_result(test_id, parameter)
            if existing and not reason:
                raise AuditError("Modification requires documented reason")
            
            # Insert new record
            record_id = insert_result(test_id, parameter, value, 
                                      uncertainty, user_id)
            
            # Log to audit trail
            log_audit(
                user_id=user_id,
                action='UPDATE' if existing else 'CREATE',
                table_name='analysis_results',
                record_id=record_id,
                old_values=existing,
                new_values={'value': value, 'uncertainty': uncertainty},
                reason=reason
            )
            
            txn.commit()
            return record_id
            
        except Exception as e:
            txn.rollback()
            log_error(user_id, str(e))
            raise
```

---

## Coding Standards

### Type Hints
All functions must have complete type annotations:

```python
def calculate_yield_strength(
    stress: np.ndarray,
    strain: np.ndarray,
    offset: float = 0.002,
    elastic_modulus: float | None = None
) -> tuple[float, float]:
    """Calculate Rp0.2 with uncertainty."""
    ...
```

### Docstrings (NumPy Format)

```python
def parse_mts_csv(filepath: Path) -> dict[str, np.ndarray]:
    """
    Parse MTS TestSuite CSV export file.
    
    Reads force-displacement data exported from MTS TestSuite software
    and returns arrays suitable for analysis.
    
    Parameters
    ----------
    filepath : Path
        Path to CSV file exported from MTS TestSuite
        
    Returns
    -------
    dict[str, np.ndarray]
        Dictionary containing:
        - 'time': Time array in seconds
        - 'force': Force array in kN
        - 'displacement': Displacement array in mm
        - 'strain': Strain array (if extensometer used)
        
    Raises
    ------
    FileNotFoundError
        If CSV file does not exist
    ParseError
        If CSV format is not recognized as MTS export
        
    Examples
    --------
    >>> data = parse_mts_csv(Path('test_001.csv'))
    >>> stress = data['force'] / specimen_area
    
    Notes
    -----
    Expected CSV format from MTS TestSuite version 4.x.
    Column headers must include 'Time', 'Force', 'Displacement'.
    """
    ...
```

### Uncertainty Propagation
All calculations returning measured values must include uncertainty:

```python
from dataclasses import dataclass

@dataclass
class MeasuredValue:
    """Value with associated uncertainty."""
    value: float
    uncertainty: float  # Expanded uncertainty, k=2
    unit: str
    coverage_factor: float = 2.0
    
    def __str__(self) -> str:
        return f"{self.value:.4g} ± {self.uncertainty:.2g} {self.unit}"
```

### Error Handling

```python
# Custom exceptions for the project
class DurablerError(Exception):
    """Base exception for Durabler application."""
    pass

class ValidationError(DurablerError):
    """Data validation failed."""
    pass

class StandardComplianceError(DurablerError):
    """Test does not meet standard requirements."""
    pass

class AuditError(DurablerError):
    """Audit trail requirement not met."""
    pass

class CalibrationError(DurablerError):
    """Calibration invalid or expired."""
    pass
```

---

## MTS Data Import Specifications

### CSV Format (MTS TestSuite Export)
- Delimiter: Comma or semicolon (auto-detect)
- Encoding: UTF-8 or ISO-8859-1
- Header row: Contains channel names
- Expected columns: Time, Force, Displacement, Strain (optional), Cycle (for fatigue)

### Excel Format (System Reports)
- Contains metadata in header rows
- Test parameters in named ranges or specific cells
- Multiple sheets possible (summary, raw data, calibration)

### Import Validation Checklist
1. File exists and is readable
2. Format matches expected MTS export
3. Required columns present
4. Data types valid (numeric where expected)
5. No obvious artifacts (negative time, force jumps)
6. Units identified and converted to SI
7. Machine calibration valid for test date

---

## Report Generation Requirements

### Every Accredited Report Must Include
1. **Header**: Lab name, accreditation number, report number
2. **Specimen identification**: Unique ID, material, geometry
3. **Test conditions**: Date, temperature, humidity, machine, operator
4. **Method reference**: Standard designation and version
5. **Results**: All parameters with uncertainties
6. **Validity statement**: Per standard requirements
7. **Plots**: As required by standard
8. **Approval signatures**: Tested by, reviewed by, approved by
9. **Footer**: Page numbers, revision, document control

### Report Number Format
`DURABLER-[METHOD]-[YEAR]-[SEQUENCE]`
Example: `DURABLER-TEN-2026-00142`

---

## Common Commands

```bash
# Run the launcher
python launcher.py

# Run specific test module
python -m tests.test_methods.tensile_e8

# Run unit tests
pytest tests/test_analysis/

# Database migration
python -m utils.database.migrations.migrate

# Generate requirements
pip freeze > requirements.txt
```

---

## Development Priorities

### Immediate (Current Sprint)
1. Complete FCGR E647 module - draft to working state
2. Add uncertainty calculations to existing tensile module
3. Implement audit logging infrastructure

### Short Term
4. Develop CTOD E1820 module
5. Develop KIC E399 module
6. Create standardized report templates

### Medium Term
7. Develop Vickers hardness module
8. Add calibration management interface
9. Implement non-conformance workflow

---

## Notes for Claude Code

### When Creating New Test Methods
1. Follow naming convention: `[testname]_[standard].py`
2. Include complete uncertainty budget
3. Implement all validity checks from standard
4. Add reference test data for validation
5. Create corresponding report template
6. Update this CLAUDE.md with new method details

### When Modifying Calculations
1. Never change calculation without updating uncertainty
2. Document standard clause reference in comments
3. Add unit test with reference data
4. Log change in audit system

### When Working with Database
1. All operations must be atomic (transaction wrapper)
2. Never delete - only mark as superseded
3. Always include user_id and reason for changes
4. Test rollback behavior

### Swedish Context
- Swedac is the Swedish accreditation body
- STAFS-2020 contains Swedish-specific requirements
- Report language may need to be Swedish
- Date format: YYYY-MM-DD (ISO 8601)
- Decimal separator: Comma in Swedish reports, period in code