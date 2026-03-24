# Measurement Uncertainty Budget — Technical Report

**Document:** DUR-UNC-001 Rev.1
**System:** Durabler2 Mechanical Testing Analysis System
**Laboratory:** Durabler AB, Kristinehamn, Sweden
**Date:** 2026-03-24
**Prepared for:** ISO 17025 Accreditation Audit (Swedac STAFS-2020)

---

## 1. Scope

This document describes the measurement uncertainty evaluation implemented in the Durabler2 software for all accredited test methods performed at the laboratory. The uncertainty budgets follow the methodology of:

- **JCGM 100:2008** (GUM) — Evaluation of measurement data — Guide to the expression of uncertainty in measurement
- **EA-4/02 M:2022** — Evaluation of the Uncertainty of Measurement in Calibration
- **ISO/IEC 17025:2017** — General requirements for the competence of testing and calibration laboratories, clause 7.6

All reported expanded uncertainties use a coverage factor k = 2, corresponding to an approximate confidence level of 95%.

---

## 2. Test Equipment and Calibration Data

| Equipment | Description | Calibrated Parameter | Expanded Uncertainty (k=2) |
|-----------|-------------|---------------------|---------------------------|
| MTS Landmark 500kN | Servo-hydraulic test frame | Force (load cell) | 0.31% of reading |
| MTS Landmark 500kN | Position gauge (crosshead) | Displacement | 0.16% of reading |
| Extensometer | Clip-on extensometer | Extension | 0.16% of reading |
| Micrometer | Dimension measurement | Length, diameter, thickness | 0.01 mm |
| Ultrasonic tester | Sonic resonance equipment | Wave velocity | 1.0% of reading |
| Analytical balance | Mass measurement | Specimen mass | 0.1% of reading |
| Vickers tester | q-ness ATM hardness tester | Machine repeatability | 2.0% of reading |

**Source files:**
- `utils/analysis/tensile_calculations.py` — TensileAnalysisConfig
- `utils/analysis/ctod_calculations.py` — CTODAnalyzer.__init__
- `utils/analysis/kic_calculations.py` — KICAnalyzer.__init__
- `utils/analysis/vickers_calculations.py` — VickersAnalyzer.__init__
- `utils/analysis/sonic_calculations.py` — SonicAnalyzer.__init__

---

## 3. Data Model

All measurement results are stored as `MeasuredValue` objects (`utils/models/test_result.py`) containing:

| Field | Description |
|-------|-------------|
| `value` | Best estimate of the measurand |
| `uncertainty` | Expanded uncertainty U (k=2) |
| `unit` | SI unit of measurement |
| `coverage_factor` | k = 2.0 (95% confidence) |
| `degrees_of_freedom` | Effective degrees of freedom (default 50) |

Derived properties:
- `standard_uncertainty` = U / k
- `relative_uncertainty` = |U / value|

---

## 4. Tensile Testing (ASTM E8/E8M)

### 4.1 Ultimate Tensile Strength R_m

**Mathematical model:**

$$R_m = \frac{F_{max}}{A_0} \times 10^3 \quad [\text{MPa}]$$

where F_max is the maximum force [kN] and A_0 is the original cross-sectional area [mm²].

**Uncertainty budget:**

| Source | Symbol | Type | Distribution | Relative Std Uncertainty | Sensitivity Coeff. |
|--------|--------|------|-------------|--------------------------|-------------------|
| Force measurement | u(F)/F | B | Normal | 0.155% (= 0.31%/2) | 1.0 |
| Cross-sectional area | u(A)/A | B | Normal | See §4.1.1 | 1.0 |

**Area uncertainty (round specimen):**

$$u(A_0) = \frac{\pi \cdot D_0 \cdot u(D_0)}{2}$$

where u(D_0) = dimension_uncertainty × D_0 (default dimension uncertainty: 0.5%).

**Area uncertainty (rectangular specimen):**

$$u(A_0) = \sqrt{(b_0 \cdot u(a_0))^2 + (a_0 \cdot u(b_0))^2}$$

where u(a_0) = u(b_0) = dimension_uncertainty × dimension value.

**Combined standard uncertainty:**

$$u_c(R_m) = \sqrt{u_{force}^2 + u_{area}^2}$$

where:
- u_force = R_m × 0.0031 / 2 (standard, from calibration)
- u_area = R_m × u(A_0) / A_0

**Expanded uncertainty:** U(R_m) = 2 × u_c(R_m)

---

### 4.2 Yield Strength R_p0.2 (Offset Method — Extensometer)

**Mathematical model:**

R_p0.2 is defined as the stress at the intersection of the stress-strain curve with a line parallel to the elastic region, offset by 0.2% strain.

**Uncertainty budget:**

| Source | Symbol | Type | Distribution | Value | Sensitivity |
|--------|--------|------|-------------|-------|-------------|
| Force measurement | u_force | B | Normal | R_p0.2 × 0.00155 | 1.0 |
| Cross-sectional area | u_area | B | Normal | R_p0.2 × u(A)/A | 1.0 |
| Interpolation | u_interp | A/B | Rectangular | |stress[i+1] - stress[i]| / 4 | 1.0 |

**Combined standard uncertainty:**

$$u_c(R_{p0.2}) = \sqrt{u_{force}^2 + u_{area}^2 + u_{interp}^2}$$

**Expanded uncertainty:** U(R_p0.2) = 2 × u_c(R_p0.2)

**Note:** When using displacement data instead of extensometer, an additional uncertainty component u_zero = R_p0.2 × 0.01 is included to account for the strain zero-point determination at 30% R_m.

---

### 4.3 Yield Strength R_p0.5

Identical to R_p0.2 with offset = 0.5% instead of 0.2%.

---

### 4.4 Upper Yield Strength R_eH

**Mathematical model:**

R_eH is the maximum stress before the first decrease in force (Lüders band onset).

**Uncertainty budget:**

| Source | Symbol | Type | Value |
|--------|--------|------|-------|
| Force measurement | u_force | B | R_eH × 0.00155 |
| Cross-sectional area | u_area | B | R_eH × u(A)/A |
| Peak detection | u_peak | B | R_eH × 0.005 |

**Combined:** u_c(R_eH) = sqrt(u_force² + u_area² + u_peak²)

**Expanded:** U(R_eH) = 2 × u_c

---

### 4.5 Lower Yield Strength R_eL

**Mathematical model:**

R_eL is the minimum stress in the Lüders band region (excluding the initial transient).

**Uncertainty budget:** Same structure as R_eH with u_detection = R_eL × 0.005 for minimum detection uncertainty.

---

### 4.6 Young's Modulus E (Extensometer)

**Mathematical model:**

$$E = \frac{d\sigma}{d\varepsilon}\bigg|_{elastic} \quad [\text{GPa}]$$

Determined by linear regression in the strain range 0.05%–0.25%.

**Uncertainty budget:**

| Source | Symbol | Type | Distribution | Evaluation Method |
|--------|--------|------|-------------|-------------------|
| Regression fit | u_regression | A | Normal | Standard error of slope / 1000 |
| Cross-sectional area | u_area | B | Normal | E × (u(A) / (sigma_mean × L_0/1000)) × 0.5 |
| Extensometer | u_extensometer | B | Normal | E × 0.0016 / L_0 |

**Combined:** u_c(E) = sqrt(u_regression² + u_area² + u_extensometer²)

**Expanded:** U(E) = 2 × u_c(E)

**Displacement method variant:** Uses strain range 15%–40% R_m to avoid machine slack. Displacement uncertainty u_displacement = 0.01 mm (absolute).

---

### 4.7 Elongation at Fracture A%

**Mathematical model:**

$$A = \frac{\Delta L}{L_0} \times 100 \quad [\%]$$

**Uncertainty propagation (ratio of two quantities):**

$$u(A) = A \times \sqrt{\left(\frac{u(\Delta L)}{\Delta L}\right)^2 + \left(\frac{u(L_0)}{L_0}\right)^2}$$

| Source | Symbol | Type | Default Value |
|--------|--------|------|--------------|
| Extension at fracture | u(ΔL) | B | extensometer_uncertainty (0.0016 mm) |
| Gauge length | u(L_0) | B | 0.1 mm |

**Expanded:** U(A) = 2 × u(A)

---

### 4.8 Reduction of Area Z%

**Mathematical model (round specimens):**

$$Z = \left(1 - \frac{d_f^2}{d_0^2}\right) \times 100 \quad [\%]$$

**Sensitivity coefficients (partial derivatives):**

$$\frac{\partial Z}{\partial d_f} = -\frac{200 \cdot d_f}{d_0^2}, \qquad \frac{\partial Z}{\partial d_0} = \frac{200 \cdot d_f^2}{d_0^3}$$

**Combined standard uncertainty:**

$$u_c(Z) = \sqrt{\left(\frac{\partial Z}{\partial d_f} \cdot u(d_f)\right)^2 + \left(\frac{\partial Z}{\partial d_0} \cdot u(d_0)\right)^2}$$

where u(d_0) = u(d_f) = 0.01 mm (micrometer).

**Expanded:** U(Z) = 2 × u_c(Z)

---

### 4.9 True Stress at Maximum Force

**Mathematical model:**

$$\sigma_{true} = \sigma_{eng} \times (1 + \varepsilon_{eng})$$

**Sensitivity coefficients:**

$$\frac{\partial \sigma_{true}}{\partial \sigma_{eng}} = (1 + \varepsilon_{eng}), \qquad \frac{\partial \sigma_{true}}{\partial \varepsilon_{eng}} = \sigma_{eng}$$

**Combined:**

$$u_c(\sigma_{true}) = \sqrt{(u(\sigma) \cdot (1 + \varepsilon))^2 + (u(\varepsilon) \cdot \sigma)^2}$$

---

### 4.10 Ludwik Strain Hardening Parameters (K, n)

**Mathematical model:**

$$\sigma_{true} = K \cdot \varepsilon_p^n$$

Fitted as log(sigma) = log(K) + n × log(epsilon_p) by linear regression.

**Uncertainty:** From regression standard error.
- u(n) = std_err of slope
- u(K) = K × std_err (approximate)

---

### 4.11 Test Rates

Stress rate, strain rate, and displacement rate uncertainties are estimated as 5% of the measured value (empirical, Type B).

---

## 5. CTOD Testing (ASTM E1290)

### 5.1 Stress Intensity Factor K

**Mathematical model (SE(B) specimen):**

$$K = \frac{P \cdot S}{B \cdot W^{3/2}} \cdot f(a/W) \quad [\text{MPa}\sqrt{\text{m}}]$$

**Uncertainty propagation (RSS of relative uncertainties):**

$$\frac{u(K)}{K} = \sqrt{u_{rel}(P)^2 + (2 \cdot u_{rel}(dim))^2}$$

The factor 2 on dimension uncertainty accounts for the W^(3/2) and B dependencies.

| Source | Symbol | Default Value |
|--------|--------|--------------|
| Force | u_rel(P) | 0.155% (std) |
| Dimensions (W, B, a_0) | u_rel(dim) | 0.25% (std) |

**Expanded:** U(K) = 2 × u(K)

---

### 5.2 CTOD (delta)

**Mathematical model (plastic hinge rotation):**

$$\delta = \frac{K^2(1-\nu^2)}{2 \sigma_Y E} + \frac{r_p(W-a_0) V_p}{r_p(W-a_0) + a_0}$$

**Uncertainty propagation:**

$$\frac{u(\delta)}{\delta} = \sqrt{u_{rel}(P)^2 + u_{rel}(V)^2 + (2 \cdot u_{rel}(dim))^2}$$

| Source | Symbol | Default Value | Sensitivity |
|--------|--------|--------------|-------------|
| Force | u_rel(P) | 0.155% (std) | 1.0 |
| CMOD displacement | u_rel(V) | 0.08% (std) | 1.0 |
| Dimensions | u_rel(dim) | 0.25% (std) | 2.0 |

**Expanded:** U(delta) = 2 × u(delta)

### 5.3 Force and CMOD Results

- U(P_max) = P_max × 0.0031 × 2 (direct from calibration, k=2)
- U(CMOD_max) = CMOD × 0.0016 × 2 (direct from calibration, k=2)

---

## 6. Fracture Toughness KIC (ASTM E399)

### 6.1 Conditional Fracture Toughness K_Q

**Mathematical model (SE(B)):**

$$K_Q = \frac{P_Q \cdot S}{B \cdot W^{3/2}} \cdot f(a/W)$$

**Sensitivity-coefficient approach for SE(B):**

$$\left(\frac{u(K)}{K}\right)^2 = u_{rel}(P)^2 + u_{rel}(S)^2 + u_{rel}(B)^2 + (1.5 \cdot u_{rel}(W))^2 + (2 \cdot u_{rel}(a))^2$$

**Sensitivity-coefficient approach for C(T):**

$$\left(\frac{u(K)}{K}\right)^2 = u_{rel}(P)^2 + u_{rel}(B)^2 + (0.5 \cdot u_{rel}(W))^2 + (2 \cdot u_{rel}(a))^2$$

| Source | Symbol | Default | Notes |
|--------|--------|---------|-------|
| Force P_Q | u_rel(P) | 0.155% (std) | From 5% secant offset |
| Thickness B | u_rel(B) | 0.25% (std) | |
| Width W | u_rel(W) | 0.25% (std) | Sensitivity 1.5× for SE(B), 0.5× for C(T) |
| Crack length a_0 | u_rel(a) | 0.25% (std) | Sensitivity 2× (through f(a/W)) |
| Span S | u_rel(S) | 0.25% (std) | SE(B) only |

**Expanded:** U(K_Q) = 2 × K_Q × u_rel(K)

### 6.2 Force Uncertainties

- U(P_max) = P_max × 0.0031 × 2
- U(P_Q) = P_Q × 0.0031 × 2

---

## 7. Fatigue Crack Growth Rate (ASTM E647)

### 7.1 Paris Law Parameters C and m

**Mathematical model:**

$$\frac{da}{dN} = C \cdot (\Delta K)^m$$

Paris law coefficients are determined by log-log linear regression of da/dN vs. ΔK data. Uncertainty is evaluated from the regression statistics:

| Parameter | Uncertainty Source | Type |
|-----------|-------------------|------|
| Paris exponent m | Standard error of slope | A |
| Paris coefficient C | Standard error of intercept (propagated) | A |
| R² | Goodness of fit (informational) | — |

The measurement input uncertainties (force 0.31%, displacement 0.16%, dimensions 0.5%) are stored in the uncertainty budget for reporting but do not directly modify the regression — they propagate through the ΔK calculation which is an input to the regression.

---

## 8. Sonic Resonance (ASTM E1875)

### 8.1 Density

**Mathematical model:**

$$\rho = \frac{m}{V} \quad [\text{kg/m}^3]$$

**Uncertainty propagation:**

$$\frac{u(\rho)}{\rho} = \sqrt{u_{rel}(m)^2 + (3 \cdot u_{rel}(dim))^2}$$

Factor 3 because V proportional to dim³ (three linear dimensions).

| Source | Symbol | Default |
|--------|--------|---------|
| Mass | u_rel(m) | 0.05% (std) |
| Dimensions | u_rel(dim) | 0.25% (std) |

---

### 8.2 Shear Modulus G

**Mathematical model:**

$$G = \rho \cdot V_s^2 \quad [\text{Pa}]$$

**Uncertainty propagation:**

$$\frac{u(G)}{G} = \sqrt{u_{rel}(\rho)^2 + 4 \cdot u_{rel}(V_s)^2}$$

Factor 4 because G proportional to V_s².

---

### 8.3 Young's Modulus E

**Mathematical model:**

$$E = 2G(1 + \nu) \quad [\text{Pa}]$$

**Uncertainty:** Same relative uncertainty as G (approximate, since nu contribution is secondary).

$$\frac{u(E)}{E} = \sqrt{u_{rel}(\rho)^2 + 4 \cdot u_{rel}(V)^2}$$

---

### 8.4 Poisson's Ratio nu

**Mathematical model:**

$$\nu = \frac{V_l^2 - 2V_s^2}{2(V_l^2 - V_s^2)}$$

**Uncertainty:** u(nu) = 2 × velocity_uncertainty (approximate sensitivity from velocity ratio).

---

### 8.5 Resonant Frequencies

Flexural and torsional resonant frequencies carry 2% relative uncertainty (empirical estimate based on measurement repeatability).

---

## 9. Vickers Hardness (ASTM E92 / ISO 6507)

### 9.1 Hardness HV

**Mathematical model:**

$$HV = 0.1891 \times \frac{F}{d^2}$$

where F is the applied force [N] and d is the mean diagonal length [mm].

**Uncertainty budget (GUM compliant, Type A + Type B):**

| Source | Symbol | Type | Distribution | Evaluation | Default |
|--------|--------|------|-------------|------------|---------|
| Repeatability | u_A | A | Normal | s / sqrt(n) from n readings | Calculated |
| Machine calibration | u_machine | B | Normal | Certificate value | 2.0% |
| Diagonal measurement | u_diagonal | B | Normal | Calibration + resolution | 1.0% |
| Force application | u_force | B | Normal | Load cell calibration | 0.31% |

**Note:** HV is proportional to 1/d², so the diagonal sensitivity coefficient is 2:

$$u_{diagonal} = HV \times 2 \times u_{rel}(d)$$

**Combined standard uncertainty:**

$$u_c(HV) = \sqrt{u_A^2 + u_{machine}^2 + u_{diagonal}^2 + u_{force}^2}$$

**Expanded uncertainty:** U(HV) = 2 × u_c(HV)

The Vickers module provides a detailed uncertainty budget breakdown via `get_uncertainty_budget()`, reporting each component individually for audit traceability.

---

## 10. Summary of Coverage Factors

All expanded uncertainties in this system use:

| Parameter | Value | Basis |
|-----------|-------|-------|
| Coverage factor k | 2.0 | Normal distribution assumption |
| Confidence level | ~95% | Per GUM Table G.2 for nu_eff > 30 |
| Degrees of freedom | 50 (default) | Conservative estimate |

The coverage factor k = 2 is applied uniformly to all measurands. For results where the effective degrees of freedom may be low (e.g., few test readings), the Welch-Satterthwaite equation could be applied to determine a more appropriate k value from the t-distribution, but this is not currently implemented.

---

## 11. Software Implementation

### 11.1 Architecture

```
utils/
├── models/
│   └── test_result.py          # MeasuredValue dataclass (value, U, k, unit)
└── analysis/
    ├── tensile_calculations.py  # TensileAnalyzer + TensileAnalysisConfig
    ├── ctod_calculations.py     # CTODAnalyzer (force, displacement, dimension unc.)
    ├── kic_calculations.py      # KICAnalyzer (force, displacement, dimension unc.)
    ├── sonic_calculations.py    # SonicAnalyzer (velocity, dimension, mass unc.)
    └── vickers_calculations.py  # VickersAnalyzer (machine, diagonal, force unc.)
```

### 11.2 User-Configurable Inputs

All uncertainty input values can be modified by the user via the specimen input form for each test method. The form defaults reflect the current calibration status of the laboratory equipment:

| Parameter | Default | Configurable Range |
|-----------|---------|-------------------|
| Force uncertainty | 0.31% | 0.01% – 10% |
| Displacement uncertainty | 0.16% | 0.01% – 10% |
| Dimension uncertainty | 0.50% | 0.01% – 5% |
| Velocity uncertainty (sonic) | 1.00% | 0.01% – 10% |
| Mass uncertainty (sonic) | 0.10% | 0.01% – 5% |
| Machine uncertainty (Vickers) | 2.00% | 0.01% – 10% |
| Diagonal uncertainty (Vickers) | 1.00% | 0.01% – 10% |

### 11.3 Propagation Method

All modules use the **law of propagation of uncertainty** (GUM clause 5.1.2):

$$u_c^2(y) = \sum_{i=1}^{N} \left(\frac{\partial f}{\partial x_i}\right)^2 u^2(x_i)$$

implemented as root-sum-of-squares (RSS) of individual uncertainty contributions. Correlation between input quantities is assumed to be zero (independent inputs).

### 11.4 Traceability

- Uncertainty input values are stored in the test record's `geometry['uncertainty_inputs']` JSON field
- The computed uncertainty budget is stored in `geometry['uncertainty_budget']`
- Each `AnalysisResult` database record stores the expanded uncertainty alongside the measured value
- All values are traceable through the audit log with user ID, timestamp, and IP address

---

## 12. References

1. **JCGM 100:2008** — Evaluation of measurement data — Guide to the expression of uncertainty in measurement (GUM)
2. **EA-4/02 M:2022** — Evaluation of the Uncertainty of Measurement in Calibration
3. **ISO/IEC 17025:2017** — General requirements for the competence of testing and calibration laboratories
4. **ASTM E8/E8M-22** — Standard Test Methods for Tension Testing of Metallic Materials
5. **ASTM E1290-08** — Standard Test Method for Crack-Tip Opening Displacement (CTOD) Fracture Toughness Measurement
6. **ASTM E399-22** — Standard Test Method for Linear-Elastic Plane-Strain Fracture Toughness of Metallic Materials
7. **ASTM E647-15** — Standard Test Method for Measurement of Fatigue Crack Growth Rates
8. **ASTM E1875-20** — Standard Test Method for Dynamic Young's Modulus, Shear Modulus, and Poisson's Ratio by Sonic Resonance
9. **ASTM E92-17** — Standard Test Methods for Vickers Hardness and Knoop Hardness of Metallic Materials
10. **ISO 6507-1:2018** — Metallic materials — Vickers hardness test — Part 1: Test method
11. **Swedac STAFS 2020:1** — Requirements for accredited testing laboratories

---

*This document is auto-generated from the Durabler2 source code and reflects the uncertainty models as implemented in the software. It should be reviewed and approved by the laboratory's quality manager before submission for accreditation audit.*
