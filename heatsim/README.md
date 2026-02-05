# Subseatec Materials Simulation Platform

A Flask-based platform for simulating heat transfer in forgings and weldments, optimizing thermal processes to achieve target microstructures.

## Features (Planned)

- **Material Database** - Steel grades with thermal properties and CCT/TTT data
- **Heat Treatment Simulation** - Python and COMSOL-based solvers
- **Welding Simulation** - GTAW, MIG/MAG, SAW, AM methods
- **Optimization** - Parameter sweeps and process tuning
- **Visualization** - 3D rendering and time-lapse animations

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL (for Phase 2+)

### Installation

```bash
# Clone repository
cd heatsim

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Initialize database
flask init_db

# Create admin user
flask create_admin

# Run development server
flask run
# or: python run.py
```

### Access

Open http://localhost:5000 and login with your admin credentials.

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Key settings:
- `SECRET_KEY` - Flask secret key (change in production)
- `FLASK_CONFIG` - development, production, or testing
- `POSTGRES_*` - PostgreSQL settings (Phase 2+)

## Docker

```bash
docker-compose up -d
```

## Project Structure

```
heatsim/
├── app/
│   ├── __init__.py      # Application factory
│   ├── extensions.py    # Flask extensions
│   ├── auth/            # Authentication blueprint
│   ├── main/            # Dashboard blueprint
│   ├── models/          # Database models
│   ├── templates/       # Jinja2 templates
│   └── static/          # CSS, JS
├── data/                # Uploads, geometries, results
├── config.py            # Configuration classes
├── run.py               # Entry point
└── requirements.txt     # Dependencies
```

## CLI Commands

```bash
flask init_db       # Initialize database
flask create_admin  # Create admin user interactively
flask seed_admin    # Create admin from environment variables
```

## Development Phases

1. **Foundation** - Project structure, auth, basic Flask app
2. **Material Database** - Steel grades, properties, CCT/TTT
3. **Python Heat Simulation** - Finite difference solver
4. **COMSOL Integration** - mph library automation
5. **Welding Simulation** - Heat source models
6. **Optimization** - Parameter sweeps
7. **Visualization** - PyVista 3D rendering
8. **Deployment** - Docker, documentation

## License

Proprietary - Subseatec
