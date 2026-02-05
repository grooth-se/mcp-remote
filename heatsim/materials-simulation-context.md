# Subseatec Materials Simulation Application - Development Context

## Project Overview

**Application name:** Subseatec Materials Simulation Platform  
**Company:** Subseatec  
**Users:** Senior materials engineers  
**Purpose:** Simulate heat transfer in forgings and weldments, optimize thermal processes to achieve target microstructures, automate COMSOL model generation, and visualize results

## Business Context

Subseatec delivers fatigue-exposed stress joints for the offshore oil & gas industry. Over the years, the company has accumulated extensive material process data and test data, developing detailed understanding of how heat transfer coefficients depend on time, temperature, and stress for specific steel grades.

**Key objectives:**
- Optimize heat treatment processes (quenching, tempering) to achieve target microstructures
- Optimize welding parameters to achieve proper phase transformations without PWHT (Post Weld Heat Treatment)
- Speed up COMSOL model generation for complex 3D geometries
- Visualize temperature evolution in 3D models
- Compare simulation results with actual weld log data

## Technology Stack

- **Backend:** Python with Flask
- **Databases:** 
  - SQLite for user management and configuration
  - PostgreSQL for material data, simulation results, and large datasets
- **Simulation:** 
  - Python (NumPy, SciPy, FiPy) for fast approximate calculations
  - COMSOL Multiphysics (Heat Transfer module) for accurate 3D simulations
- **COMSOL Integration:** mph library with JPype (Java API)
- **Visualization:** PyVista for 3D rendering, Matplotlib for plots, MoviePy for animations
- **Data Processing:** Pandas for import/export, SciPy for curve fitting
- **Deployment:** Docker container on network server

## Core Functionality

### 1. Material Database

**Steel Grade Organization:**
- Each steel grade has a unique designation (e.g., "A182 F22")
- Two data variants per grade:
  - **Standard** - Literature values (e.g., "A182 F22 Standard")
  - **Subseatec** - Proprietary measured values (e.g., "A182 F22 Subseatec")

**Initial Data:**
- 20 standard steel grades with literature values (pre-populated)
- 5 steel grades with Subseatec proprietary data (to be imported)

**Pre-populated Standard Steel Grades:**

| Category | Steel Grade | Standard/Spec |
|----------|-------------|---------------|
| **Structural** | S355J2G3 | EN 10025 |
| **Low Alloy** | AISI 4130 | AMS 6370 |
| **Low Alloy** | AISI 4340 | AMS 6414 |
| **Low Alloy** | AISI 4330V | AMS 6411 |
| **Low Alloy** | AISI 8630 | AMS 6280 |
| **Cr-Mo** | A182 F22 (2.25Cr-1Mo) | ASTM A182 |
| **Cr-Mo** | A182 F11 (1.25Cr-0.5Mo) | ASTM A182 |
| **Cr-Mo** | A182 F5 (5Cr-0.5Mo) | ASTM A182 |
| **Stainless Austenitic** | 304 (1.4301) | ASTM A240 |
| **Stainless Austenitic** | 316 (1.4401) | ASTM A240 |
| **Stainless Austenitic** | 316L (1.4404) | ASTM A240 |
| **Stainless Duplex** | 2205 (1.4462) | ASTM A240 |
| **Stainless Duplex** | 2507 (1.4410) | ASTM A240 |
| **Stainless Martensitic** | 410 (1.4006) | ASTM A240 |
| **Tool Steel** | H13 | ASTM A681 |
| **Tool Steel** | P20 | ASTM A681 |
| **High Strength** | 300M | AMS 6417 |
| **Nickel Alloy** | Inconel 625 | UNS N06625 |
| **Nickel Alloy** | Inconel 718 | UNS N07718 |
| **Carbon Steel** | AISI 1045 | ASTM A29 |

These grades cover the typical range for offshore, forging, and welding applications. Literature values for thermal properties will be sourced from standard references (ASM Handbook, NIST, manufacturer datasheets).

**Material Properties (all with dependency support):**

| Property | Typical Dependencies | Units |
|----------|---------------------|-------|
| Thermal conductivity | Temperature, phase | W/(m·K) |
| Specific heat capacity | Temperature, phase | J/(kg·K) |
| Density | Temperature | kg/m³ |
| Emissivity | Temperature, surface condition | - |
| Heat transfer coefficient | Temperature, medium, flow | W/(m²·K) |
| Yield strength | Temperature, strain rate | MPa |
| Latent heat | Phase transformation | J/kg |

**Dependency Storage Format:**
All properties can be stored as:
- Constant value
- Temperature-dependent curve (T, value pairs)
- Multi-variable table (T, time, stress → value)
- Polynomial coefficients
- Custom equation (parsed and evaluated)

### 2. Phase Transformation Data (CCT/TTT)

**Data Source:** Manual digitization of existing diagrams  
**Storage:** Key transformation points and curves as data arrays

**Required data per steel grade:**
- Austenite start/finish temperatures (Ac1, Ac3)
- Martensite start/finish temperatures (Ms, Mf)
- Bainite nose temperature and time
- Ferrite/pearlite transformation curves
- Critical cooling rates

**Digitization workflow:**
1. Upload CCT/TTT diagram image
2. Use built-in digitization tool (or import from WebPlotDigitizer)
3. Store curve points in database
4. Interpolate for simulation use

### 3. Heat Treatment Simulation

**Target processes:**
- Quenching (water, oil, polymer, air)
- Tempering
- Normalizing
- Stress relieving

**Geometry:**
- 3D STEP files of open die forgings
- Simplified geometry (cylinders/rings) for fast Python calculations

**Two-tier simulation approach:**

**Tier 1 - Fast Python Simulation:**
- Simplified/approximated geometry
- Finite difference or FiPy solver
- Used for parameter sweeps and optimization
- Seconds to minutes per run

**Tier 2 - Accurate COMSOL Simulation:**
- Full 3D STEP geometry
- COMSOL Heat Transfer module
- Used for final verification and detailed analysis
- Minutes to hours per run

**Optimization workflow:**
1. Define target (e.g., cooling rate at core, surface temperature limits)
2. Run parameter sweep in Python (quench medium, temperature, timing)
3. Identify optimal parameters
4. Verify best cases in COMSOL
5. Compare predicted microstructure with CCT/TTT data

### 4. Welding Simulation

**Welding methods:**
- GTAW (Gas Tungsten Arc Welding)
- MIG/MAG
- SAW (Submerged Arc Welding)
- AM (Additive Manufacturing methodology)

**Simulation modes:**

**Simple - Heat Input Only:**
- Moving heat source model (Goldak or similar)
- Temperature field evolution
- HAZ prediction
- Fast calculation for parameter studies

**Full Weld Simulation:**
- Material deposition modeling
- Residual stress calculation
- Distortion prediction
- Multi-pass weld buildup

**Key objectives:**
- Predict interpass temperatures for optimal phase transformations
- Achieve target weld metal properties without PWHT
- Validate against actual weld log data (surface temperature measurements)

**Weld parameter database:**
- Heat input per method (efficiency, power, speed)
- Typical parameters for each welding process
- Subseatec-specific validated parameters

**Validation workflow:**
1. Import weld log data (time, surface temperature)
2. Run simulation with same parameters
3. Compare predicted vs measured surface temperatures
4. Adjust model parameters to match
5. Use validated model for optimization

### 5. Visualization

**Time-lapse Temperature Animation:**
- Load STEP geometry into PyVista
- Map COMSOL temperature results onto geometry
- Render animation with color gradient (temperature scale)
- Export as video file (MP4/GIF)

**Static Visualizations:**
- Temperature distribution at specific times
- Cooling curves at selected points
- CCT/TTT diagrams with cooling curve overlay
- Comparison plots (simulation vs measured data)

**Interactive 3D Viewer:**
- Rotate, zoom, slice geometry
- Select points for temperature history
- Toggle between time steps

### 6. COMSOL Automation

**Workflow to automate:**
1. Import STEP geometry
2. Apply material properties (from database, with dependencies)
3. Define boundary conditions (convection, radiation)
4. Set initial temperature
5. Configure mesh (with refinement options)
6. Run transient simulation
7. Export results (temperature field at time steps)

**mph Library Integration:**
```python
# Example workflow structure
client = mph.start()
model = client.create('HeatTreatment')
model.java.component().create("comp1", True)
# Import geometry, set physics, mesh, solve, export
```

**Parameterized Models:**
- Save model templates for common geometries
- Parameter input via Python (temperatures, times, HTC values)
- Batch running for parameter studies

## Data Import Formats

### Material Property Data Template (Excel)

**Recommended structure:**

**Sheet: Metadata**
| Field | Value |
|-------|-------|
| Steel Grade | A182 F22 |
| Data Source | Subseatec |
| Version | 1.0 |
| Date | 2025-02-04 |
| Notes | Measured at Subseatec lab 2024 |

**Sheet: Thermal_Conductivity**
| Temperature_C | Conductivity_W_mK | Phase |
|---------------|-------------------|-------|
| 20 | 42.5 | Ferrite |
| 100 | 42.0 | Ferrite |
| 200 | 40.5 | Ferrite |
| ... | ... | ... |
| 900 | 28.0 | Austenite |

**Sheet: Specific_Heat**
| Temperature_C | Cp_J_kgK | Phase |
|---------------|----------|-------|
| 20 | 460 | Ferrite |
| ... | ... | ... |

**Sheet: HTC_Quench**
| Temperature_C | HTC_Water | HTC_Oil | HTC_Air |
|---------------|-----------|---------|---------|
| 900 | 2500 | 800 | 50 |
| 800 | 3500 | 1000 | 55 |
| ... | ... | ... | ... |

### CCT/TTT Digitized Data Template (Excel)

**Sheet: Transformation_Points**
| Parameter | Value_C |
|-----------|---------|
| Ac1 | 730 |
| Ac3 | 820 |
| Ms | 350 |
| Mf | 180 |

**Sheet: CCT_Curves**
| Cooling_Rate_C_s | Ferrite_Start_C | Ferrite_Finish_C | Pearlite_Start_C | Bainite_Start_C | ... |
|------------------|-----------------|------------------|------------------|-----------------|-----|
| 0.1 | 720 | 650 | 680 | - | ... |
| 1.0 | 700 | 600 | 650 | 550 | ... |
| 10 | - | - | - | 500 | ... |
| 100 | - | - | - | - | ... |

### Weld Log Data Template (CSV)

```csv
timestamp_s,surface_temp_C,torch_position_mm,current_A,voltage_V,travel_speed_mm_s
0.0,25,0,180,12,2.5
0.5,150,1.25,180,12,2.5
1.0,380,2.5,180,12,2.5
...
```

## Application Architecture

```
subseatec-simulation/
├── app/
│   ├── __init__.py
│   ├── config.py                 # Database, COMSOL, paths configuration
│   ├── routes.py                 # Flask routes
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py               # User model (SQLite)
│   │   ├── material.py           # Material/property models (PostgreSQL)
│   │   ├── simulation.py         # Simulation job/result models
│   │   └── weld.py               # Weld parameters/logs models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── material_database.py  # Material CRUD operations
│   │   ├── property_handler.py   # Handle dependencies, interpolation
│   │   ├── phase_transformation.py # CCT/TTT calculations
│   │   ├── heat_simulation.py    # Python-based heat transfer solver
│   │   ├── weld_simulation.py    # Welding heat source models
│   │   ├── comsol_interface.py   # COMSOL automation via mph
│   │   ├── optimizer.py          # Parameter optimization routines
│   │   └── visualization.py      # PyVista rendering, animations
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── curve_fitting.py      # Polynomial fitting, interpolation
│   │   ├── digitizer.py          # CCT/TTT diagram digitization helper
│   │   ├── step_handler.py       # STEP geometry processing
│   │   └── validators.py         # Data validation
│   └── templates/
│       ├── base.html
│       ├── materials/
│       ├── simulation/
│       ├── welding/
│       └── visualization/
├── static/
│   ├── css/
│   └── js/
├── data/
│   ├── templates/                # Excel import templates
│   ├── materials/                # Imported material data files
│   ├── geometries/               # STEP files
│   ├── weld_logs/                # Weld measurement data
│   └── results/                  # Simulation outputs
├── comsol/
│   ├── templates/                # COMSOL model templates (.mph)
│   └── exports/                  # Exported results
├── tests/
│   ├── test_materials.py
│   ├── test_simulation.py
│   └── test_comsol.py
├── migrations/                   # Database migrations
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Database Schema

### SQLite (User Management)

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'engineer',  -- 'admin', 'engineer'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    token TEXT UNIQUE,
    expires_at TIMESTAMP
);
```

### PostgreSQL (Material & Simulation Data)

```sql
-- Steel grades
CREATE TABLE steel_grades (
    id SERIAL PRIMARY KEY,
    designation TEXT NOT NULL,          -- e.g., "A182 F22"
    data_source TEXT NOT NULL,          -- "Standard" or "Subseatec"
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(designation, data_source)
);

-- Material properties with dependencies
CREATE TABLE material_properties (
    id SERIAL PRIMARY KEY,
    steel_grade_id INTEGER REFERENCES steel_grades(id),
    property_name TEXT NOT NULL,        -- e.g., "thermal_conductivity"
    property_type TEXT NOT NULL,        -- "constant", "curve", "table", "polynomial", "equation"
    units TEXT,
    dependencies TEXT[],                -- ["temperature"], ["temperature", "phase"], etc.
    data JSONB NOT NULL,                -- Flexible storage for any data type
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Phase transformation data
CREATE TABLE phase_diagrams (
    id SERIAL PRIMARY KEY,
    steel_grade_id INTEGER REFERENCES steel_grades(id),
    diagram_type TEXT NOT NULL,         -- "CCT" or "TTT"
    transformation_temps JSONB,         -- {Ac1, Ac3, Ms, Mf, etc.}
    curves JSONB,                       -- Digitized transformation curves
    source_image BYTEA,                 -- Original diagram image
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Welding parameters
CREATE TABLE weld_methods (
    id SERIAL PRIMARY KEY,
    method_name TEXT NOT NULL,          -- "GTAW", "MIG/MAG", "SAW", "AM"
    default_parameters JSONB,           -- Default values
    efficiency DECIMAL
);

CREATE TABLE weld_procedures (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    steel_grade_id INTEGER REFERENCES steel_grades(id),
    weld_method_id INTEGER REFERENCES weld_methods(id),
    parameters JSONB,                   -- Current, voltage, speed, etc.
    interpass_temp_min DECIMAL,
    interpass_temp_max DECIMAL,
    preheat_temp DECIMAL,
    notes TEXT,
    validated BOOLEAN DEFAULT FALSE
);

-- Weld log data for validation
CREATE TABLE weld_logs (
    id SERIAL PRIMARY KEY,
    weld_procedure_id INTEGER REFERENCES weld_procedures(id),
    log_data JSONB,                     -- Time series: [{t, temp, position, ...}, ...]
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Simulation jobs and results
CREATE TABLE simulations (
    id SERIAL PRIMARY KEY,
    simulation_type TEXT NOT NULL,      -- "heat_treatment", "welding_simple", "welding_full"
    steel_grade_id INTEGER REFERENCES steel_grades(id),
    geometry_file TEXT,                 -- Path to STEP file
    parameters JSONB,                   -- Input parameters
    solver TEXT,                        -- "python" or "comsol"
    status TEXT DEFAULT 'pending',      -- "pending", "running", "completed", "failed"
    results JSONB,                      -- Output data
    comsol_model_path TEXT,             -- Path to .mph file if COMSOL
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

-- Optimization runs
CREATE TABLE optimizations (
    id SERIAL PRIMARY KEY,
    simulation_type TEXT NOT NULL,
    steel_grade_id INTEGER REFERENCES steel_grades(id),
    objective TEXT,                     -- What to optimize
    constraints JSONB,                  -- Limits and constraints
    parameter_ranges JSONB,             -- Parameters to vary and their ranges
    results JSONB,                      -- Optimization results
    best_parameters JSONB,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Web Interface Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/login` | GET/POST | User authentication |
| `/logout` | POST | End session |
| **Materials** |||
| `/materials` | GET | List all steel grades |
| `/materials/new` | GET/POST | Add new steel grade |
| `/materials/<id>` | GET | View steel grade details |
| `/materials/<id>/edit` | GET/POST | Edit steel grade |
| `/materials/<id>/properties` | GET/POST | Manage properties |
| `/materials/<id>/phase-diagram` | GET/POST | Manage CCT/TTT data |
| `/materials/import` | GET/POST | Import from Excel |
| `/materials/templates` | GET | Download import templates |
| **Simulation** |||
| `/simulation/heat-treatment` | GET/POST | Heat treatment simulation setup |
| `/simulation/welding` | GET/POST | Welding simulation setup |
| `/simulation/<id>/status` | GET | Check simulation status |
| `/simulation/<id>/results` | GET | View results |
| `/simulation/<id>/visualize` | GET | 3D visualization |
| **Optimization** |||
| `/optimize/heat-treatment` | GET/POST | Heat treatment optimization |
| `/optimize/welding` | GET/POST | Welding parameter optimization |
| `/optimize/<id>/results` | GET | Optimization results |
| **Welding** |||
| `/welding/procedures` | GET | List weld procedures |
| `/welding/procedures/new` | GET/POST | Create weld procedure |
| `/welding/logs/import` | POST | Import weld log data |
| `/welding/validate/<id>` | GET/POST | Validate simulation vs log |
| **Visualization** |||
| `/visualize/<simulation_id>` | GET | Interactive 3D viewer |
| `/visualize/<simulation_id>/animation` | GET | Generate time-lapse |
| `/visualize/<simulation_id>/export` | POST | Export video/images |

## Development Phases

### Phase 1: Foundation
- [ ] Project structure and configuration
- [ ] Database setup (SQLite + PostgreSQL)
- [ ] User authentication (simple, single admin initially)
- [ ] Basic Flask app with templates

### Phase 2: Material Database
- [ ] Steel grade CRUD operations
- [ ] Property storage with dependencies
- [ ] Excel import functionality
- [ ] Property interpolation/evaluation engine
- [ ] CCT/TTT data storage and digitization helper

### Phase 3: Python Heat Simulation
- [ ] 1D/2D heat transfer solver (finite difference or FiPy)
- [ ] Simplified geometry handling
- [ ] Boundary condition implementation (convection, radiation)
- [ ] Phase transformation tracking using CCT/TTT data
- [ ] Basic visualization (Matplotlib)

### Phase 4: COMSOL Integration
- [ ] mph library setup and connection testing
- [ ] STEP geometry import
- [ ] Material property assignment from database
- [ ] Boundary condition setup
- [ ] Meshing and solving
- [ ] Result extraction

### Phase 5: Welding Simulation
- [ ] Moving heat source models (Goldak double ellipsoid)
- [ ] GTAW, MIG/MAG, SAW parameter sets
- [ ] Multi-pass weld logic
- [ ] Weld log import and comparison
- [ ] Interpass temperature optimization

### Phase 6: Optimization
- [ ] Parameter sweep framework
- [ ] Objective function definition
- [ ] Python-based optimization (SciPy optimize)
- [ ] Integration with COMSOL for verification
- [ ] Results comparison and reporting

### Phase 7: Visualization
- [ ] PyVista integration for STEP viewing
- [ ] Temperature mapping onto geometry
- [ ] Time-lapse animation generation
- [ ] Interactive viewer in browser (vtk.js or similar)
- [ ] Export to video formats

### Phase 8: Deployment
- [ ] Dockerfile
- [ ] docker-compose with PostgreSQL
- [ ] COMSOL license configuration in container
- [ ] Network server deployment
- [ ] Documentation

## Technical Notes

### COMSOL License in Docker
- COMSOL license server must be accessible from container
- Set environment variables for license server address
- mph library requires Java; use appropriate base image

### Property Dependency Evaluation
```python
# Example: Evaluate temperature-dependent property
def evaluate_property(property_data, conditions):
    """
    property_data: {
        "type": "curve",
        "dependencies": ["temperature"],
        "data": {"temperature": [20, 100, 200, ...], "value": [42.5, 42.0, 40.5, ...]}
    }
    conditions: {"temperature": 150}
    """
    if property_data["type"] == "constant":
        return property_data["data"]["value"]
    elif property_data["type"] == "curve":
        return np.interp(conditions["temperature"], 
                         property_data["data"]["temperature"],
                         property_data["data"]["value"])
    # ... handle other types
```

### Goldak Heat Source Model
For welding simulation, implement the Goldak double ellipsoid:
```
q(x,y,z,t) = (6√3 * f * Q) / (a*b*c*π√π) * exp(-3x²/a² - 3y²/b² - 3z²/c²)
```
Where Q = η * V * I (heat input), and a, b, c are ellipsoid dimensions.

### CCT Curve Interpolation
Store CCT curves as arrays of (cooling_rate, transformation_temperature) pairs for each phase. During simulation, track cooling rate at each point and determine phase fractions.

## External Dependencies

```
# requirements.txt
flask>=3.0
sqlalchemy>=2.0
psycopg2-binary
pandas
numpy
scipy
matplotlib
pyvista
moviepy
mph  # COMSOL interface
jpype1  # Required by mph
fipy  # Optional: for Python PDE solving
openpyxl  # Excel handling
python-dotenv
werkzeug  # Password hashing
pytest
```

## Configuration

```python
# config.py example
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    
    # SQLite for users
    SQLITE_DATABASE = 'sqlite:///users.db'
    
    # PostgreSQL for materials/simulations
    POSTGRES_HOST = os.environ.get('POSTGRES_HOST', 'localhost')
    POSTGRES_DB = os.environ.get('POSTGRES_DB', 'subseatec_sim')
    POSTGRES_USER = os.environ.get('POSTGRES_USER', 'subseatec')
    POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', '')
    
    # COMSOL
    COMSOL_PATH = os.environ.get('COMSOL_PATH', '/usr/local/comsol')
    COMSOL_LICENSE_SERVER = os.environ.get('COMSOL_LICENSE', 'license.subseatec.local')
    
    # Paths
    UPLOAD_FOLDER = 'data/uploads'
    GEOMETRY_FOLDER = 'data/geometries'
    RESULTS_FOLDER = 'data/results'
```

## Notes

- Start with a single admin user; expand user management later if needed
- Material data is proprietary; ensure proper backup and access control
- COMSOL simulations can be long-running; implement job queue (Celery) if needed
- Consider caching frequently used material properties in memory
- PyVista rendering may require a display; use virtual framebuffer (Xvfb) in Docker

## References

- COMSOL mph library: https://mph.readthedocs.io/
- PyVista documentation: https://docs.pyvista.org/
- Goldak heat source: Goldak et al., "A new finite element model for welding heat sources"
- FiPy documentation: https://www.ctcms.nist.gov/fipy/
