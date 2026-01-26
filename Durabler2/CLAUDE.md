## CLAUDE.md - Mechanical Testing Analysis System (Durabler2 - Web Version)

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**Durabler2** is the web-based version of the Durabler mechanical testing analysis system for an ISO 17025 accredited materials testing laboratory. The system handles data acquisition from MTS testing equipment, performs standardized calculations with uncertainty propagation, generates accredited test reports, and maintains full audit traceability.

### Core Objectives
1. Import and process test data from MTS Landmark 500kN servo-dynamic test machine
2. Perform calculations according to international standards (ASTM, ISO)
3. Generate accredited test reports meeting ISO 17025 and Swedac STAFS-2020
4. Maintain complete data traceability and audit logging
5. Store all test data, analysis results, plots, and photos in database
6. **Provide multi-user access via web browser on local network (LAN)**

### Key Difference from Durabler1
- **Durabler1**: Desktop Tkinter GUI application (single user)
- **Durabler2**: Web application accessible via browser (multi-user on LAN)

---

## Architecture Overview

### Web Application Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                    Web Browser (Client)                          │
│              http://192.168.x.x:5000                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP
┌──────────────────────────▼──────────────────────────────────────┐
│                    Flask Web Server                              │
│                    (gunicorn/waitress)                          │
├─────────────────────────────────────────────────────────────────┤
│  Routes/Blueprints    │  Templates (Jinja2)  │  Static Files    │
│  - /tensile/*         │  - HTML pages        │  - CSS           │
│  - /sonic/*           │  - Form templates    │  - JavaScript    │
│  - /fcgr/*            │  - Plot components   │  - Images        │
│  - /ctod/*            │                      │                  │
│  - /kic/*             │                      │                  │
│  - /vickers/*         │                      │                  │
├─────────────────────────────────────────────────────────────────┤
│                    Business Logic Layer                          │
│  utils/analysis/      │  utils/data_acquisition/                │
│  (calculations)       │  (CSV/Excel parsers)                    │
├─────────────────────────────────────────────────────────────────┤
│                    Database Layer (SQLAlchemy)                   │
│                    PostgreSQL or SQLite                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Technical Stack

| Component | Technology | Notes |
|-----------|------------|-------|
| Language | Python 3.11+ | |
| Web Framework | Flask 3.x | Lightweight, flexible |
| Templates | Jinja2 | Server-side rendering |
| Frontend Enhancement | htmx (optional) | AJAX without JavaScript complexity |
| CSS Framework | Bootstrap 5 | Responsive design |
| Database | PostgreSQL (prod) / SQLite (dev) | Multi-user support |
| ORM | SQLAlchemy 2.x | Database abstraction |
| Authentication | Flask-Login | Session management |
| Forms | Flask-WTF | Form validation |
| Plotting | Plotly.js (interactive) or Matplotlib (static) | Web-compatible charts |
| File Upload | Flask file handling | CSV/Excel upload via browser |
| Reports | python-docx / ReportLab | PDF/Word generation |
| Data Processing | NumPy, SciPy, Pandas | Unchanged from desktop |
| WSGI Server | gunicorn (Linux) / waitress (Windows) | Production deployment |

---

## Project Structure

```
Durabler2/
├── CLAUDE.md                   # This file
├── README.md                   # User documentation
├── requirements.txt            # Python dependencies
├── run.py                      # Application entry point
├── config.py                   # Configuration settings
│
├── app/                        # Flask application package
│   ├── __init__.py             # App factory
│   ├── extensions.py           # Flask extensions (db, login)
│   │
│   ├── auth/                   # Authentication module
│   │   ├── __init__.py
│   │   ├── routes.py           # Login, logout routes
│   │   ├── forms.py            # Login forms
│   │   └── models.py           # User model
│   │
│   ├── main/                   # Main dashboard
│   │   ├── __init__.py
│   │   └── routes.py           # Dashboard route
│   │
│   ├── tensile/                # Tensile test module
│   │   ├── __init__.py
│   │   ├── routes.py           # /tensile/* routes
│   │   └── forms.py            # Specimen input forms
│   │
│   ├── sonic/                  # Sonic resonance module
│   ├── fcgr/                   # FCGR module
│   ├── ctod/                   # CTOD module
│   ├── kic/                    # KIC module
│   ├── vickers/                # Vickers module
│   ├── certificates/           # Certificate register
│   │
│   ├── models/                 # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── specimen.py
│   │   ├── test_record.py
│   │   ├── analysis_result.py
│   │   └── audit_log.py
│   │
│   ├── templates/              # Jinja2 HTML templates
│   │   ├── base.html           # Base layout
│   │   ├── auth/
│   │   ├── main/
│   │   ├── tensile/
│   │   └── components/         # Reusable components
│   │
│   └── static/                 # Static files
│       ├── css/
│       ├── js/
│       └── images/
│
├── utils/                      # Shared utilities (from Durabler1)
│   ├── analysis/               # Calculation engines (unchanged)
│   │   ├── tensile_calculations.py
│   │   ├── sonic_calculations.py
│   │   ├── fcgr_calculations.py
│   │   ├── ctod_calculations.py
│   │   ├── kic_calculations.py
│   │   ├── vickers_calculations.py
│   │   └── uncertainty.py
│   │
│   ├── data_acquisition/       # Data parsers (unchanged)
│   │   ├── mts_csv_parser.py
│   │   └── mts_xml_parser.py
│   │
│   ├── reporting/              # Report generators (unchanged)
│   │   ├── word_report.py
│   │   └── [test]_word_report.py
│   │
│   └── models/                 # Data models (unchanged)
│       ├── specimen.py
│       └── test_result.py
│
├── migrations/                 # Database migrations
├── uploads/                    # Uploaded test data files
├── reports/                    # Generated reports
├── templates/                  # Report templates (Word/PDF)
├── tests/                      # Test suite
└── instance/                   # Instance config (not in git)
    └── durabler.db             # SQLite database (dev)
```

---

## URL Routes

```
/                           → Dashboard (launcher equivalent)
/auth/login                 → Login page
/auth/logout                → Logout

/tensile/                   → Tensile test list
/tensile/new                → Start new test (upload CSV, enter specimen)
/tensile/<id>               → View test details
/tensile/<id>/analyze       → Run analysis
/tensile/<id>/report        → Generate/download report

/sonic/                     → Sonic resonance tests
/fcgr/                      → FCGR tests
/ctod/                      → CTOD tests
/kic/                       → KIC tests
/vickers/                   → Vickers tests

/certificates/              → Certificate register
/certificates/search        → Search certificates

/admin/                     → Admin panel
/admin/users                → User management
/admin/calibration          → Calibration records
/admin/audit-log            → View audit trail
```

---

## Test Methods and Standards

| Test Method | Primary Standard | Status |
|-------------|------------------|--------|
| Tensile Testing | ASTM E8/E8M, ISO 6892-1 | Migrate first |
| Sonic Resonance | Modified ASTM E1875 | Migrate second |
| FCGR | ASTM E647 | Migrate |
| CTOD | ASTM E1820, E1290 | Migrate |
| KIC | ASTM E399 | Migrate |
| Vickers Hardness | ISO 6507-1, ASTM E92 | Migrate |

---

## Migration Strategy

### Phase 1: Infrastructure (Start Here)
1. Create Flask app factory (`app/__init__.py`)
2. Set up configuration (`config.py`)
3. Create database models (`app/models/`)
4. Implement authentication (`app/auth/`)
5. Create base templates with Bootstrap

### Phase 2: First Test Module (Tensile)
1. Create tensile blueprint (`app/tensile/`)
2. Create file upload form
3. Create specimen input form
4. Integrate existing analysis code from `utils/analysis/`
5. Add Plotly charts for stress-strain curves
6. Generate reports using existing `utils/reporting/`

### Phase 3: Remaining Modules
- Migrate each test module following same pattern
- Reuse existing calculation and reporting code

### Phase 4: Polish
1. Certificate register
2. Admin panel
3. Audit log viewer
4. Multi-user testing

---

## Key Code Patterns

### Flask App Factory
```python
# app/__init__.py
from flask import Flask
from .extensions import db, login_manager

def create_app(config_class='config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Register blueprints
    from .main import main_bp
    from .auth import auth_bp
    from .tensile import tensile_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(tensile_bp, url_prefix='/tensile')

    return app
```

### File Upload Route
```python
# app/tensile/routes.py
from flask import Blueprint, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from utils.data_acquisition.mts_csv_parser import parse_mts_csv

tensile_bp = Blueprint('tensile', __name__)

@tensile_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        file = request.files['csv_file']
        if file and file.filename.endswith('.csv'):
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Parse using existing code
            data = parse_mts_csv(filepath)
            # Store in session or database
            return redirect(url_for('tensile.analyze'))

    return render_template('tensile/upload.html')
```

### Plot Generation for Web
```python
# Option 1: Plotly (interactive)
import plotly.graph_objects as go
import plotly.io as pio

def create_stress_strain_plot(stress, strain):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=strain, y=stress, mode='lines', name='Stress-Strain'))
    fig.update_layout(
        xaxis_title='Strain',
        yaxis_title='Stress (MPa)',
        template='plotly_white'
    )
    return pio.to_html(fig, full_html=False)

# In template: {{ plot_html | safe }}

# Option 2: Matplotlib as base64 image
import io, base64
import matplotlib.pyplot as plt

def create_plot_image(stress, strain):
    fig, ax = plt.subplots()
    ax.plot(strain, stress)
    ax.set_xlabel('Strain')
    ax.set_ylabel('Stress (MPa)')

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150)
    buf.seek(0)
    plt.close(fig)

    return base64.b64encode(buf.getvalue()).decode('utf-8')

# In template: <img src="data:image/png;base64,{{ plot_data }}">
```

---

## Database Models

```python
# app/models/user.py
from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    role = db.Column(db.String(20), default='operator')  # operator, reviewer, admin

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# app/models/test_record.py
class TestRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.String(50), unique=True)
    test_method = db.Column(db.String(20))  # TENSILE, FCGR, etc.
    test_date = db.Column(db.DateTime)
    operator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(20), default='DRAFT')
    # ... more fields
```

---

## Deployment

### Development
```bash
cd /Users/pjbhb/Durabler2
export FLASK_APP=run.py
export FLASK_DEBUG=1
flask run --host=0.0.0.0 --port=5000

# Access at http://localhost:5000
# Or from LAN: http://192.168.x.x:5000
```

### Production (LAN Server)
```bash
# Linux/Mac
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 run:app

# Windows
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 run:app
```

---

## Common Commands

```bash
# Run development server
flask run --host=0.0.0.0 --port=5000

# Initialize database
flask db init
flask db migrate -m "Initial"
flask db upgrade

# Run tests
pytest tests/

# Install dependencies
pip install -r requirements.txt
```

---

## ISO 17025 Compliance (Web-Specific)

1. **User Authentication**: All users must log in before accessing data
2. **Audit Trail**: Log user, IP address, timestamp for all actions
3. **Session Timeout**: Auto-logout after inactivity
4. **Role-Based Access**: operator, reviewer, admin roles
5. **Data Integrity**: Never delete, only mark as superseded

---

## Notes for Claude Code

### When Creating Routes
1. Always use `@login_required` decorator
2. Log all data changes to audit trail
3. Validate form inputs with Flask-WTF
4. Use `secure_filename()` for uploads

### When Converting from Tkinter
| Tkinter | Flask Web |
|---------|-----------|
| `tk.Entry` | `<input>` + WTForms |
| `tk.Button` | `<button>` or form submit |
| `ttk.Treeview` | HTML `<table>` |
| `filedialog` | `<input type="file">` |
| `FigureCanvasTkAgg` | Plotly.js or `<img>` |
| Instance variables | Session or database |

### Reuse from Durabler1
- `utils/analysis/*` - All calculation code (unchanged)
- `utils/data_acquisition/*` - All parsers (unchanged)
- `utils/reporting/*` - Report generators (unchanged)
- `utils/models/*` - Data models (unchanged)

### Swedish Context
- Date format: YYYY-MM-DD (ISO 8601)
- Decimal: Comma in reports, period in code
- Swedac accreditation requirements apply
