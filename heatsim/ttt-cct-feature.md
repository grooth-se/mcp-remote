# HeatSim Feature Addition: TTT/CCT Diagram Generation & Phase Prediction

## Feature Overview

**Purpose:** Generate and manage TTT (Time-Temperature-Transformation) and CCT (Continuous Cooling Transformation) diagrams per steel grade, with parameter calibration from test data, for use in simulation phase predictions.

## Scientific Foundation

### Core Models

**1. JMAK Model (Isothermal - TTT)**
```
X(t, T) = 1 - exp(-b(T) · t^n)
```
Where:
- X = transformed fraction (0-1)
- t = time at temperature
- T = temperature
- n = Avrami exponent (1-4, mechanism dependent)
- b(T) = temperature-dependent rate constant

**2. Rate Constant (Arrhenius form)**
```
b(T) = b₀ · exp(-Q / RT)
```
Or C-curve (nose) form for pearlite/bainite

**3. Martensite (Koistinen-Marburger)**
```
X_m = 1 - exp(-α_M · (Ms - T))
```
Diffusionless transformation below Ms

**4. Scheil Additivity (CCT from TTT)**
```
Σ (Δt_i / τ_start(T_i)) ≥ 1
```
Integrate along cooling curve using isothermal TTT data

### Phase Transformations Modeled

| Phase | Model | Key Parameters |
|-------|-------|----------------|
| Ferrite | JMAK | n_f, b_f(T), Ae3 |
| Pearlite | JMAK | n_p, b_p(T), Ae1 |
| Bainite | JMAK | n_b, b_b(T), Bs |
| Martensite | Koistinen-Marburger | Ms, Mf, α_M |

### Critical Temperatures (Empirical Formulas)

```python
# Andrews formulas (°C)
Ae1 = 727 - 10.7*Mn - 16.9*Ni + 29.1*Si + 16.9*Cr + 290*As + 6.38*W
Ae3 = 910 - 203*sqrt(C) - 15.2*Ni + 44.7*Si + 104*V + 31.5*Mo + 13.1*W

# Steven-Haynes Ms formula (°C)
Ms = 539 - 423*C - 30.4*Mn - 17.7*Ni - 12.1*Cr - 7.5*Mo

# Bainite start (approximate)
Bs = 830 - 270*C - 90*Mn - 37*Ni - 70*Cr - 83*Mo
```

## Database Schema Additions

```sql
-- TTT/CCT Parameters per steel grade
CREATE TABLE ttt_parameters (
    id SERIAL PRIMARY KEY,
    steel_grade_id INTEGER REFERENCES steel_grades(id),
    
    -- Critical temperatures (°C)
    ae1 DECIMAL(6,2),                    -- Eutectoid temperature
    ae3 DECIMAL(6,2),                    -- Ferrite start
    bs DECIMAL(6,2),                     -- Bainite start
    ms DECIMAL(6,2),                     -- Martensite start
    mf DECIMAL(6,2),                     -- Martensite finish
    
    -- Grain size
    astm_grain_size DECIMAL(4,2),        -- ASTM grain size number
    
    -- Source/calibration info
    data_source TEXT,                    -- 'calculated', 'experimental', 'literature'
    calibration_date DATE,
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- JMAK parameters per phase
CREATE TABLE jmak_parameters (
    id SERIAL PRIMARY KEY,
    ttt_parameters_id INTEGER REFERENCES ttt_parameters(id),
    phase TEXT NOT NULL,                 -- 'ferrite', 'pearlite', 'bainite'
    
    -- Avrami exponent (can be temperature dependent)
    n_value DECIMAL(6,4),                -- Constant n, or
    n_coefficients JSONB,                -- Polynomial coefficients n(T)
    
    -- Rate constant b(T) parameters
    b_model TEXT,                        -- 'arrhenius', 'gaussian', 'polynomial', 'tabular'
    b_parameters JSONB,                  -- Model-specific parameters
    
    -- Temperature range
    t_min DECIMAL(6,2),                  -- Lower temperature limit
    t_max DECIMAL(6,2),                  -- Upper temperature limit
    
    -- Nose parameters (for C-curve)
    nose_temperature DECIMAL(6,2),       -- Temperature of fastest transformation
    nose_time DECIMAL(10,4),             -- Time at nose (seconds)
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Martensite parameters
CREATE TABLE martensite_parameters (
    id SERIAL PRIMARY KEY,
    ttt_parameters_id INTEGER REFERENCES ttt_parameters(id),
    
    ms DECIMAL(6,2) NOT NULL,            -- Martensite start
    mf DECIMAL(6,2),                     -- Martensite finish
    alpha_m DECIMAL(8,6) DEFAULT 0.011,  -- KM coefficient
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Experimental calibration data
CREATE TABLE ttt_calibration_data (
    id SERIAL PRIMARY KEY,
    steel_grade_id INTEGER REFERENCES steel_grades(id),
    
    test_type TEXT,                      -- 'isothermal', 'continuous'
    temperature DECIMAL(6,2),            -- Hold temperature (isothermal) or cooling rate
    time_start DECIMAL(10,4),            -- Time to transformation start
    time_finish DECIMAL(10,4),           -- Time to transformation finish
    phase TEXT,                          -- Phase observed
    fraction DECIMAL(5,4),               -- Fraction transformed (0-1)
    hardness DECIMAL(6,2),               -- Measured hardness (HV)
    
    test_date DATE,
    test_method TEXT,                    -- 'dilatometry', 'metallography', 'XRD'
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Stored TTT/CCT curve data (for plotting)
CREATE TABLE ttt_curves (
    id SERIAL PRIMARY KEY,
    ttt_parameters_id INTEGER REFERENCES ttt_parameters(id),
    curve_type TEXT NOT NULL,            -- 'TTT' or 'CCT'
    phase TEXT NOT NULL,
    curve_position TEXT,                 -- 'start' (1%), 'finish' (99%), or specific %
    
    data_points JSONB NOT NULL,          -- [{t: time, T: temp}, ...]
    
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Application Structure Additions

```
heatsim/
├── app/
│   ├── services/
│   │   ├── phase_transformation/           # NEW MODULE
│   │   │   ├── __init__.py
│   │   │   ├── critical_temperatures.py    # Ae1, Ae3, Ms, Bs calculations
│   │   │   ├── jmak_model.py               # JMAK transformation kinetics
│   │   │   ├── martensite_model.py         # Koistinen-Marburger
│   │   │   ├── scheil_additivity.py        # CCT from TTT
│   │   │   ├── ttt_generator.py            # Generate TTT diagrams
│   │   │   ├── cct_generator.py            # Generate CCT diagrams
│   │   │   ├── parameter_calibration.py    # Fit parameters to test data
│   │   │   ├── phase_predictor.py          # Predict phases along cooling curve
│   │   │   └── property_calculator.py      # Hardness, strength from phases
│   │   └── ...
│   ├── routes/
│   │   ├── ttt_cct.py                      # NEW: TTT/CCT management routes
│   │   └── ...
│   └── templates/
│       ├── ttt_cct/                        # NEW
│       │   ├── index.html                  # TTT/CCT diagram list per steel
│       │   ├── view.html                   # View/plot diagram
│       │   ├── edit_parameters.html        # Edit JMAK parameters
│       │   ├── calibration.html            # Upload/manage test data
│       │   └── compare.html                # Compare TTT vs CCT
│       └── ...
```

## Core Implementation

### 1. Critical Temperature Calculator

```python
# services/phase_transformation/critical_temperatures.py

def calculate_critical_temperatures(composition: dict) -> dict:
    """
    Calculate critical transformation temperatures from composition.
    
    Args:
        composition: dict with keys C, Mn, Si, Cr, Ni, Mo, V, W, etc. (wt%)
    
    Returns:
        dict with Ae1, Ae3, Bs, Ms, Mf
    """
    C = composition.get('C', 0)
    Mn = composition.get('Mn', 0)
    Si = composition.get('Si', 0)
    Cr = composition.get('Cr', 0)
    Ni = composition.get('Ni', 0)
    Mo = composition.get('Mo', 0)
    V = composition.get('V', 0)
    W = composition.get('W', 0)
    
    # Andrews formulas
    Ae1 = 727 - 10.7*Mn - 16.9*Ni + 29.1*Si + 16.9*Cr + 6.38*W
    Ae3 = 910 - 203*np.sqrt(C) - 15.2*Ni + 44.7*Si + 104*V + 31.5*Mo + 13.1*W
    
    # Steven-Haynes Ms
    Ms = 539 - 423*C - 30.4*Mn - 17.7*Ni - 12.1*Cr - 7.5*Mo
    
    # Approximate Mf (typically Ms - 150 to 200°C)
    Mf = Ms - 150
    
    # Bainite start
    Bs = 830 - 270*C - 90*Mn - 37*Ni - 70*Cr - 83*Mo
    
    return {
        'Ae1': max(Ae1, 650),  # Physical limits
        'Ae3': max(Ae3, Ae1 + 20),
        'Bs': min(Bs, 650),
        'Ms': max(Ms, 0),
        'Mf': max(Mf, -50)
    }
```

### 2. JMAK Model

```python
# services/phase_transformation/jmak_model.py

import numpy as np
from scipy.optimize import curve_fit

class JMAKModel:
    """Johnson-Mehl-Avrami-Kolmogorov transformation kinetics."""
    
    def __init__(self, n: float, b_func: callable):
        """
        Args:
            n: Avrami exponent
            b_func: Function b(T) returning rate constant at temperature T
        """
        self.n = n
        self.b_func = b_func
    
    def fraction_transformed(self, t: float, T: float) -> float:
        """Calculate transformed fraction X at time t and temperature T."""
        b = self.b_func(T)
        return 1 - np.exp(-b * t**self.n)
    
    def time_to_fraction(self, X: float, T: float) -> float:
        """Calculate time to reach fraction X at temperature T."""
        if X <= 0:
            return 0
        if X >= 1:
            return np.inf
        b = self.b_func(T)
        return (-np.log(1 - X) / b) ** (1/self.n)
    
    def transformation_rate(self, X: float, T: float) -> float:
        """Calculate dX/dt at fraction X and temperature T."""
        if X <= 0 or X >= 1:
            return 0
        b = self.b_func(T)
        return self.n * b**(1/self.n) * (1-X) * (-np.log(1-X))**((self.n-1)/self.n)


def create_gaussian_b_function(b_max: float, T_nose: float, sigma: float):
    """Create Gaussian-shaped b(T) function for C-curve nose."""
    def b_func(T):
        return b_max * np.exp(-((T - T_nose)**2) / (2 * sigma**2))
    return b_func


def create_arrhenius_b_function(b0: float, Q: float, R: float = 8.314):
    """Create Arrhenius b(T) function."""
    def b_func(T):
        T_kelvin = T + 273.15
        return b0 * np.exp(-Q / (R * T_kelvin))
    return b_func


def fit_jmak_parameters(time_data: np.ndarray, fraction_data: np.ndarray, T: float):
    """
    Fit JMAK n and b parameters from isothermal test data.
    
    Uses linearization: ln(-ln(1-X)) = ln(b) + n*ln(t)
    """
    # Filter valid data (0 < X < 1)
    valid = (fraction_data > 0.01) & (fraction_data < 0.99)
    t = time_data[valid]
    X = fraction_data[valid]
    
    # Linearize
    y = np.log(-np.log(1 - X))
    x = np.log(t)
    
    # Linear regression
    coeffs = np.polyfit(x, y, 1)
    n = coeffs[0]
    ln_b = coeffs[1]
    b = np.exp(ln_b)
    
    return {'n': n, 'b': b, 'T': T}
```

### 3. Martensite Model

```python
# services/phase_transformation/martensite_model.py

import numpy as np

class KoistinenMarburgerModel:
    """Koistinen-Marburger model for martensite transformation."""
    
    def __init__(self, Ms: float, Mf: float = None, alpha: float = 0.011):
        """
        Args:
            Ms: Martensite start temperature (°C)
            Mf: Martensite finish temperature (°C), optional
            alpha: KM coefficient (default 0.011)
        """
        self.Ms = Ms
        self.alpha = alpha
        self.Mf = Mf if Mf else Ms - 150
    
    def fraction_martensite(self, T: float) -> float:
        """Calculate martensite fraction at temperature T."""
        if T >= self.Ms:
            return 0.0
        if T <= self.Mf:
            return 1.0
        return 1 - np.exp(-self.alpha * (self.Ms - T))
    
    def temperature_for_fraction(self, X: float) -> float:
        """Calculate temperature for given martensite fraction."""
        if X <= 0:
            return self.Ms
        if X >= 1:
            return self.Mf
        return self.Ms + np.log(1 - X) / self.alpha
```

### 4. Scheil Additivity (CCT from TTT)

```python
# services/phase_transformation/scheil_additivity.py

import numpy as np
from typing import List, Tuple, Dict
from .jmak_model import JMAKModel

def calculate_cct_transformation(
    cooling_curve: List[Tuple[float, float]],  # [(time, temperature), ...]
    jmak_models: Dict[str, JMAKModel],         # {'ferrite': model, 'pearlite': model, ...}
    martensite_model,
    critical_temps: dict
) -> Dict[str, List[float]]:
    """
    Calculate phase fractions along a cooling curve using Scheil additivity.
    
    Returns:
        Dict with phase fractions at each time step
    """
    n_steps = len(cooling_curve)
    
    # Initialize results
    results = {
        'time': [],
        'temperature': [],
        'austenite': [],
        'ferrite': [],
        'pearlite': [],
        'bainite': [],
        'martensite': []
    }
    
    # Track transformed fractions
    X_total = 0.0  # Total transformed from austenite
    X_ferrite = 0.0
    X_pearlite = 0.0
    X_bainite = 0.0
    X_martensite = 0.0
    
    # Scheil integrals
    S_ferrite = 0.0
    S_pearlite = 0.0
    S_bainite = 0.0
    
    for i in range(n_steps):
        t, T = cooling_curve[i]
        dt = cooling_curve[i][0] - cooling_curve[i-1][0] if i > 0 else 0
        
        # Remaining austenite
        X_austenite = 1 - X_total
        
        if X_austenite > 0.01:
            # Diffusional transformations (above Ms)
            if T > martensite_model.Ms:
                
                # Ferrite (between Ae3 and Ae1)
                if critical_temps['Ae1'] < T < critical_temps['Ae3']:
                    if 'ferrite' in jmak_models:
                        tau = jmak_models['ferrite'].time_to_fraction(0.01, T)
                        if tau > 0:
                            S_ferrite += dt / tau
                            if S_ferrite >= 1 and X_ferrite < X_austenite:
                                # Transformation started, use JMAK rate
                                dX = jmak_models['ferrite'].transformation_rate(
                                    X_ferrite / X_austenite, T
                                ) * dt * X_austenite
                                X_ferrite += min(dX, X_austenite - X_total)
                
                # Pearlite (below Ae1)
                if T < critical_temps['Ae1']:
                    if 'pearlite' in jmak_models:
                        tau = jmak_models['pearlite'].time_to_fraction(0.01, T)
                        if tau > 0:
                            S_pearlite += dt / tau
                            if S_pearlite >= 1:
                                dX = jmak_models['pearlite'].transformation_rate(
                                    X_pearlite / max(X_austenite, 0.01), T
                                ) * dt * X_austenite
                                X_pearlite += min(dX, X_austenite - X_total)
                
                # Bainite (below Bs, above Ms)
                if T < critical_temps['Bs']:
                    if 'bainite' in jmak_models:
                        tau = jmak_models['bainite'].time_to_fraction(0.01, T)
                        if tau > 0:
                            S_bainite += dt / tau
                            if S_bainite >= 1:
                                dX = jmak_models['bainite'].transformation_rate(
                                    X_bainite / max(X_austenite, 0.01), T
                                ) * dt * X_austenite
                                X_bainite += min(dX, X_austenite - X_total)
            
            else:
                # Below Ms - martensite transformation
                X_m_equilibrium = martensite_model.fraction_martensite(T) * X_austenite
                if X_m_equilibrium > X_martensite:
                    X_martensite = X_m_equilibrium
        
        # Update total
        X_total = X_ferrite + X_pearlite + X_bainite + X_martensite
        X_total = min(X_total, 1.0)
        
        # Store results
        results['time'].append(t)
        results['temperature'].append(T)
        results['austenite'].append(1 - X_total)
        results['ferrite'].append(X_ferrite)
        results['pearlite'].append(X_pearlite)
        results['bainite'].append(X_bainite)
        results['martensite'].append(X_martensite)
    
    return results
```

### 5. TTT/CCT Diagram Generator

```python
# services/phase_transformation/ttt_generator.py

import numpy as np
from typing import Dict, List
from .jmak_model import JMAKModel

def generate_ttt_diagram(
    jmak_models: Dict[str, JMAKModel],
    critical_temps: dict,
    temperature_range: tuple = (200, 800),
    temperature_step: float = 10,
    fractions: List[float] = [0.01, 0.5, 0.99]
) -> Dict[str, Dict[str, List[dict]]]:
    """
    Generate TTT diagram data for plotting.
    
    Returns:
        {
            'ferrite': {
                '1%': [{'T': temp, 't': time}, ...],
                '50%': [...],
                '99%': [...]
            },
            'pearlite': {...},
            ...
        }
    """
    temperatures = np.arange(temperature_range[0], temperature_range[1], temperature_step)
    
    result = {}
    
    for phase, model in jmak_models.items():
        result[phase] = {}
        
        for X in fractions:
            label = f"{int(X*100)}%"
            result[phase][label] = []
            
            for T in temperatures:
                # Check if transformation possible at this temperature
                if phase == 'ferrite' and (T > critical_temps['Ae3'] or T < critical_temps['Ae1']):
                    continue
                if phase == 'pearlite' and T > critical_temps['Ae1']:
                    continue
                if phase == 'bainite' and (T > critical_temps['Bs'] or T < critical_temps.get('Ms', 200)):
                    continue
                
                try:
                    t = model.time_to_fraction(X, T)
                    if 0 < t < 1e6:  # Reasonable time range
                        result[phase][label].append({'T': T, 't': t})
                except:
                    pass
    
    return result
```

### 6. Property Calculator

```python
# services/phase_transformation/property_calculator.py

def calculate_hardness(
    phase_fractions: dict,
    composition: dict,
    cooling_rate: float = None
) -> float:
    """
    Calculate hardness (HV) from phase fractions using Maynier equations.
    """
    C = composition.get('C', 0)
    Mn = composition.get('Mn', 0)
    Si = composition.get('Si', 0)
    Cr = composition.get('Cr', 0)
    Ni = composition.get('Ni', 0)
    Mo = composition.get('Mo', 0)
    
    X_m = phase_fractions.get('martensite', 0)
    X_b = phase_fractions.get('bainite', 0)
    X_f = phase_fractions.get('ferrite', 0)
    X_p = phase_fractions.get('pearlite', 0)
    
    # Individual phase hardness (Maynier)
    HV_m = 127 + 949*C + 27*Si + 11*Mn + 8*Ni + 16*Cr + 21*np.log10(cooling_rate or 10)
    HV_b = -109 + 1089*C + 37*Si + 63*Mn + 16*Cr + 44*Mo + 8*Ni
    HV_fp = 42 + 223*C + 53*Si + 30*Mn + 12.6*Ni + 7*Cr + 19*Mo
    
    # Rule of mixtures
    HV_total = X_m * HV_m + X_b * HV_b + (X_f + X_p) * HV_fp
    
    return HV_total
```

## Web Interface

### Routes

```python
# routes/ttt_cct.py

from flask import Blueprint, render_template, request, jsonify
from app.services.phase_transformation import (
    calculate_critical_temperatures,
    generate_ttt_diagram,
    generate_cct_diagram,
    fit_jmak_parameters
)

ttt_cct_bp = Blueprint('ttt_cct', __name__, url_prefix='/ttt-cct')

@ttt_cct_bp.route('/<int:steel_grade_id>')
def view_diagrams(steel_grade_id):
    """View TTT/CCT diagrams for a steel grade."""
    # Load steel grade and parameters
    # Generate or load cached diagrams
    # Render template
    pass

@ttt_cct_bp.route('/<int:steel_grade_id>/parameters', methods=['GET', 'POST'])
def edit_parameters(steel_grade_id):
    """Edit JMAK parameters for a steel grade."""
    pass

@ttt_cct_bp.route('/<int:steel_grade_id>/calibrate', methods=['GET', 'POST'])
def calibrate(steel_grade_id):
    """Upload test data and calibrate parameters."""
    pass

@ttt_cct_bp.route('/api/generate-ttt', methods=['POST'])
def api_generate_ttt():
    """API endpoint to generate TTT diagram."""
    pass

@ttt_cct_bp.route('/api/predict-phases', methods=['POST'])
def api_predict_phases():
    """API endpoint to predict phases for a cooling curve."""
    pass
```

## Development Phases

### Phase 1: Core Models (Local Development)
- [ ] Implement critical temperature calculations
- [ ] Implement JMAK model class
- [ ] Implement Koistinen-Marburger model
- [ ] Unit tests for all models

### Phase 2: TTT Generation
- [ ] TTT diagram generator
- [ ] Database schema for parameters
- [ ] Store/retrieve parameters per steel grade
- [ ] TTT visualization (Matplotlib or Plotly)

### Phase 3: CCT via Scheil
- [ ] Scheil additivity implementation
- [ ] CCT diagram generator
- [ ] Phase fraction prediction along cooling curve
- [ ] CCT visualization

### Phase 4: Parameter Calibration
- [ ] Import experimental data (dilatometry CSV)
- [ ] JMAK parameter fitting (scipy.optimize)
- [ ] Visual comparison: fitted vs measured
- [ ] Save calibrated parameters

### Phase 5: Integration with Simulation
- [ ] Connect phase predictor to heat simulation results
- [ ] Property calculation (hardness, strength)
- [ ] Microstructure visualization in 3D model
- [ ] Report generation with phase predictions

### Phase 6: Web Interface
- [ ] TTT/CCT parameter management pages
- [ ] Interactive diagram viewer
- [ ] Calibration data upload
- [ ] Integration with existing material pages

### Phase 7: Testing & Deployment
- [ ] Integration tests
- [ ] Validate against known steel data (42CrMo4, etc.)
- [ ] Deploy to server as update

## References

- Johnson-Mehl-Avrami-Kolmogorov: Classical nucleation/growth kinetics
- Scheil (1935): Additivity rule for non-isothermal transformations
- Kirkaldy/Li et al. (1998): Composition-dependent TTT model
- Koistinen-Marburger (1959): Martensite kinetics
- Maynier et al.: Hardness prediction from microstructure
- GitHub reference: https://github.com/arthursn/transformation-diagrams
