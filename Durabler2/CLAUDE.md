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
| Authentication | Flask-Login | Session management, app credentials |
| Forms | Flask-WTF | Form validation |
| Plotting | Plotly.js (interactive) or Matplotlib (static) | Web-compatible charts |
| File Upload | Flask file handling | CSV/Excel upload via browser |
| Reports | python-docx | Word document generation |
| PDF Conversion | docx2pdf or LibreOffice | Word to PDF conversion |
| PDF Signing | endesive | X.509 cryptographic signatures |
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
│   ├── reporting/              # Report generators
│   │   ├── word_report.py      # Tensile report (from scratch)
│   │   ├── sonic_word_report.py
│   │   ├── fcgr_word_report.py
│   │   ├── ctod_word_report.py
│   │   ├── kic_word_report.py
│   │   └── vickers_word_report.py
│   │
│   ├── signing/                # PDF signing utilities
│   │   ├── __init__.py
│   │   └── pdf_signer.py       # X.509 PDF signing
│   │
│   └── models/                 # Data models (unchanged)
│       ├── specimen.py
│       └── test_result.py
│
├── migrations/                 # Database migrations
├── uploads/                    # Uploaded test data files
├── reports/                    # Generated reports
│   ├── drafts/                 # Word documents (editable)
│   ├── signed/                 # Signed PDFs (immutable)
│   │   └── YYYY/               # Organized by year
│   └── archive/                # Superseded versions
├── templates/                  # Report templates (Word/PDF)
├── tests/                      # Test suite
└── instance/                   # Instance config (not in git)
    ├── durabler.db             # SQLite database (dev)
    └── certificates/           # Signing certificates
        └── durabler_signing.p12  # Company X.509 certificate
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
/tensile/<id>/report        → Generate Word report

/sonic/                     → Sonic resonance tests
/fcgr/                      → FCGR tests
/ctod/                      → CTOD tests
/kic/                       → KIC tests
/vickers/                   → Vickers tests

/certificates/              → Certificate register (with status & action links)
/certificates/search        → Search certificates
/certificates/<cert_num>    → View certificate + approval history

/reports/                   → All reports with approval status
/reports/pending            → Reports awaiting approval (approvers)
/reports/<id>/submit        → Submit for approval
/reports/<id>/review        → Review report (approvers)
/reports/<id>/approve       → Approve and sign (approvers)
/reports/<id>/reject        → Reject with comments (approvers)
/reports/<id>/download      → Download signed PDF

/admin/                     → Admin panel
/admin/users                → User management (CRUD)
/admin/users/new            → Create new user
/admin/users/<id>/edit      → Edit user permissions
/admin/certificate          → Manage company signing certificate
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
4. **Role-Based Access**: operator, engineer, approver, admin roles
5. **Data Integrity**: Never delete, only mark as superseded
6. **Report Approval**: All reports must be approved before publishing
7. **Digital Signatures**: Signed PDFs with company X.509 certificate

---

## Report Approval Workflow

### Overview

Test reports follow an approval workflow before being published as signed PDFs. The certificate register shows approval status with links to continue the process.

### Workflow States

```
┌─────────┐    Submit    ┌─────────────────┐    Approve    ┌──────────┐    Sign    ┌────────────┐
│  DRAFT  │ ──────────►  │ PENDING_REVIEW  │ ────────────► │ APPROVED │ ────────► │ PUBLISHED  │
└─────────┘              └─────────────────┘               └──────────┘           └────────────┘
     ▲                          │                                                       │
     │         Reject           │                                                       ▼
     └──────────────────────────┘                                               ┌────────────┐
                                                                                │ Signed PDF │
                                                                                │ in Register│
                                                                                └────────────┘
```

**States:**
| Status | Description | Who can act |
|--------|-------------|-------------|
| DRAFT | Report created, can be edited | Test Engineer |
| PENDING_REVIEW | Submitted for approval (locked) | Approver |
| APPROVED | Approved, ready for signing | System (auto) |
| PUBLISHED | Signed PDF generated and stored | Read-only |
| REJECTED | Returned with comments | Test Engineer |

### User Roles and Permissions

| Role | User ID Format | Permissions |
|------|----------------|-------------|
| **Operator** | DUR-OPR-xxx | Create tests, view own data |
| **Test Engineer** | DUR-ENG-xxx | Create/edit reports, submit for approval |
| **Approver** | DUR-APR-xxx | Review, approve/reject, sign reports |
| **Admin** | DUR-ADM-xxx | User management, all permissions |

### Authentication

- **App-specific credentials**: Separate username/password for the application
- **User ID**: Unique identifier (e.g., DUR-ENG-001) for audit trail
- **Password**: Hashed with werkzeug security (bcrypt)
- **Session**: Flask-Login with configurable timeout

### Digital Signature

- **Single company certificate**: One X.509 certificate for all signatures
- **Certificate location**: `instance/certificates/durabler_signing.p12`
- **Signature type**: Hybrid (visual + cryptographic)
  - Visual: Approver name, date, "Approved" stamp in PDF
  - Cryptographic: PDF signed with company certificate (SHA-256)
- **Library**: `endesive` for PDF signing

### Certificate Register Integration

The certificate register list includes approval status with action links:

| Column | Description |
|--------|-------------|
| Certificate # | Certificate number (e.g., DUR-2025-1065) |
| Test Type | TENSILE, FCGR, CTOD, KIC, VICKERS, SONIC |
| Specimen ID | Specimen identifier |
| Test Date | Date of test |
| **Status** | DRAFT, PENDING, APPROVED, PUBLISHED |
| **Action** | Link to continue workflow (role-dependent) |

**Action links by status and role:**
- DRAFT + Engineer → "Edit" / "Submit for Approval"
- PENDING + Approver → "Review" / "Approve" / "Reject"
- APPROVED + System → Auto-generates signed PDF
- PUBLISHED + Any → "Download PDF" / "View"

### Database Models

```python
# Enhanced User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(20), unique=True)  # DUR-ENG-001
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    full_name = db.Column(db.String(120))  # For signature display
    role = db.Column(db.String(20), default='operator')
    can_approve = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Report approval tracking
class ReportApproval(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_record_id = db.Column(db.Integer, db.ForeignKey('test_records.id'))
    certificate_number = db.Column(db.String(50))
    status = db.Column(db.String(20), default='DRAFT')

    # Submission
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    submitted_at = db.Column(db.DateTime)

    # Approval
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    reviewed_at = db.Column(db.DateTime)
    review_comments = db.Column(db.Text)  # For rejections

    # Signed PDF
    word_report_path = db.Column(db.String(255))  # Draft Word document
    signed_pdf_path = db.Column(db.String(255))   # Final signed PDF
    pdf_hash = db.Column(db.String(64))           # SHA-256 for integrity
    signature_timestamp = db.Column(db.DateTime)

    # Relationships
    test_record = db.relationship('TestRecord', backref='approval')
    created_by = db.relationship('User', foreign_keys=[created_by_id])
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id])
```

### URL Routes (Approval)

```
# Approval workflow routes
/reports/                     → List all reports with status
/reports/pending              → List reports pending approval (approvers only)
/reports/<id>/submit          → Submit report for approval
/reports/<id>/review          → Review report (approvers only)
/reports/<id>/approve         → Approve report (approvers only)
/reports/<id>/reject          → Reject with comments (approvers only)
/reports/<id>/download        → Download signed PDF (published only)

# Certificate register (enhanced)
/certificates/                → List with status column and action links
/certificates/<cert_num>      → View certificate details + approval history

# Admin routes
/admin/users                  → User management (CRUD)
/admin/users/new              → Create new user
/admin/users/<id>/edit        → Edit user
/admin/certificate            → Manage company signing certificate
```

### PDF Signing Implementation

```python
# utils/signing/pdf_signer.py
from pathlib import Path
from datetime import datetime
import hashlib
from endesive import pdf

class PDFSigner:
    """Sign PDFs with company X.509 certificate."""

    def __init__(self, certificate_path: Path, password: str):
        self.certificate_path = certificate_path
        self.password = password

    def sign_pdf(self, input_path: Path, output_path: Path,
                 approver_name: str) -> dict:
        """
        Sign PDF with visual and cryptographic signature.

        Returns dict with signed_path, hash, timestamp.
        """
        # Load certificate
        with open(self.certificate_path, 'rb') as f:
            p12_data = f.read()

        # Read input PDF
        with open(input_path, 'rb') as f:
            pdf_data = f.read()

        # Create signature
        timestamp = datetime.utcnow()
        signed_data = pdf.cms.sign(
            datau=pdf_data,
            udct={
                'sigflags': 3,
                'name': f'Approved by: {approver_name}',
                'contact': 'Durabler AB',
                'location': 'Kristinehamn, Sweden',
                'reason': 'Test Report Approval',
                'signingdate': timestamp.strftime('%Y%m%d%H%M%S+00\'00\''),
            },
            key=p12_data,
            cert=p12_data,
            othercerts=[],
            algomd='sha256',
            password=self.password.encode()
        )

        # Write signed PDF
        with open(output_path, 'wb') as f:
            f.write(pdf_data)
            f.write(signed_data)

        # Calculate hash for integrity verification
        with open(output_path, 'rb') as f:
            pdf_hash = hashlib.sha256(f.read()).hexdigest()

        return {
            'signed_path': output_path,
            'hash': pdf_hash,
            'timestamp': timestamp
        }
```

### Signed PDF Storage

```
reports/
├── drafts/                    # Word documents (editable)
│   └── TENSILE_DUR-2025-1065_draft.docx
├── signed/                    # Signed PDFs (immutable)
│   └── 2025/
│       └── DUR-2025-1065_signed.pdf
└── archive/                   # Superseded versions
```

### Implementation Phases

**Phase 1: User Management**
1. Enhance User model with roles and user_id
2. Create user admin interface (CRUD)
3. Implement role-based access control decorators
4. Add login/logout with app credentials

**Phase 2: Approval Workflow**
1. Create ReportApproval model
2. Add status tracking to test records
3. Implement submit/approve/reject routes
4. Update certificate register with status column

**Phase 3: PDF Signing**
1. Set up company X.509 certificate
2. Implement PDFSigner utility
3. Convert Word reports to PDF (python-docx → pdf)
4. Add cryptographic signature on approval

**Phase 4: Certificate Register Integration**
1. Add action links based on status and user role
2. Implement signed PDF download
3. Add approval history view
4. Secure PDF storage with access control

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
