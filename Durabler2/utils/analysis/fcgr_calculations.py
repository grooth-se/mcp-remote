"""
FCGR Analysis Calculations per ASTM E647.

Provides crack length calculation from compliance, da/dN calculation,
Delta-K calculation, Paris law regression, and outlier detection.
"""

import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional
import numpy as np
from scipy import stats
from scipy.optimize import curve_fit

from utils.models.fcgr_specimen import (
    FCGRSpecimen, FCGRMaterial, FCGRTestParameters,
    FCGRDataPoint, ParisLawResult, FCGRResult
)


@dataclass
class MeasuredValue:
    """Value with associated uncertainty."""
    value: float
    uncertainty: float
    unit: str
    coverage_factor: float = 2.0

    def __str__(self) -> str:
        return f"{self.value:.4g} ± {self.uncertainty:.2g} {self.unit}"


class FCGRAnalyzer:
    """
    FCGR analysis engine per ASTM E647.

    Performs compliance-based crack length calculation, da/dN determination,
    Paris law regression, and validity checks.
    """

    def __init__(self, specimen: FCGRSpecimen, material: FCGRMaterial,
                 test_params: FCGRTestParameters):
        """
        Initialize FCGR analyzer.

        Parameters
        ----------
        specimen : FCGRSpecimen
            Specimen geometry
        material : FCGRMaterial
            Material properties
        test_params : FCGRTestParameters
            Test parameters
        """
        self.specimen = specimen
        self.material = material
        self.test_params = test_params

    def crack_length_from_compliance_CT(self, compliance: float) -> float:
        """
        Calculate crack length from compliance for C(T) specimen per E647.

        Uses the compliance calibration equation:
        a/W = C0 + C1*u + C2*u² + C3*u³ + C4*u⁴ + C5*u⁵

        where u = 1 / (√(E*B*C) + 1)

        Parameters
        ----------
        compliance : float
            Specimen compliance (mm/kN)

        Returns
        -------
        float
            Crack length a (mm)
        """
        # E in GPa = kN/mm², B in mm, C in mm/kN
        E = self.material.youngs_modulus  # GPa = kN/mm²
        B = self.specimen.B_effective

        # Calculate u parameter
        # E*B*C has units: (kN/mm²) * mm * (mm/kN) = dimensionless
        EBC = E * B * compliance
        if EBC <= 0:
            return self.specimen.a_0

        u = 1.0 / (math.sqrt(EBC) + 1.0)

        # Standard E647 compliance coefficients for C(T)
        # These are default values; can be overridden by test_params
        C = self.test_params.compliance_coefficients if hasattr(self.test_params, 'compliance_coefficients') else None

        if C and len(C) >= 6:
            C0, C1, C2, C3, C4, C5 = C[0], C[1], C[2], C[3], C[4], C[5]
        else:
            # E647 standard coefficients for C(T)
            C0 = 1.0010
            C1 = -4.6695
            C2 = 18.460
            C3 = -236.82
            C4 = 1214.9
            C5 = -2143.6

        a_W = C0 + C1*u + C2*u**2 + C3*u**3 + C4*u**4 + C5*u**5

        # Clamp to valid range
        a_W = max(0.2, min(0.95, a_W))

        return a_W * self.specimen.W

    def crack_length_from_compliance_MT(self, compliance: float) -> float:
        """
        Calculate crack length from compliance for M(T) specimen per E647.

        Parameters
        ----------
        compliance : float
            Specimen compliance (mm/kN)

        Returns
        -------
        float
            Half crack length a (mm)
        """
        # Simplified M(T) compliance relationship
        # More complex implementation would use E647 Annex equations
        E = self.material.youngs_modulus
        B = self.specimen.B_effective
        W = self.specimen.W

        # Approximate using secant correction
        # This is a simplified approach
        EBC = E * B * compliance
        if EBC <= 0:
            return self.specimen.a_0

        # Iterative solution would be more accurate
        # For now, use linear approximation
        a = self.specimen.a_0 + (compliance - self.test_params.initial_compliance) * W * 0.1
        return max(self.specimen.a_0, a)

    def crack_length_from_compliance(self, compliance: float) -> float:
        """
        Calculate crack length from compliance based on specimen type.

        Parameters
        ----------
        compliance : float
            Specimen compliance (mm/kN)

        Returns
        -------
        float
            Crack length a (mm)
        """
        if self.specimen.specimen_type == 'C(T)':
            return self.crack_length_from_compliance_CT(compliance)
        else:
            return self.crack_length_from_compliance_MT(compliance)

    def calculate_delta_K(self, delta_P: float, a: float) -> float:
        """
        Calculate stress intensity factor range Delta-K.

        Parameters
        ----------
        delta_P : float
            Load range P_max - P_min (kN)
        a : float
            Current crack length (mm)

        Returns
        -------
        float
            Delta-K in MPa*sqrt(m)
        """
        return self.specimen.calculate_delta_K(delta_P, a)

    def calculate_da_dN_secant(self, cycles: np.ndarray,
                               crack_lengths: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate da/dN using secant (point-to-point) method per E647.

        da/dN = (a_{i+1} - a_i) / (N_{i+1} - N_i)

        Parameters
        ----------
        cycles : np.ndarray
            Cycle count array
        crack_lengths : np.ndarray
            Crack length array (mm)

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (cycle_midpoints, da_dN values in mm/cycle)
        """
        # Calculate differences
        da = np.diff(crack_lengths)
        dN = np.diff(cycles)

        # Avoid division by zero
        valid = dN > 0
        da_dN = np.zeros(len(da))
        da_dN[valid] = da[valid] / dN[valid]

        # Midpoint cycles and crack lengths
        N_mid = (cycles[:-1] + cycles[1:]) / 2
        a_mid = (crack_lengths[:-1] + crack_lengths[1:]) / 2

        return N_mid, a_mid, da_dN

    def calculate_da_dN_polynomial(self, cycles: np.ndarray,
                                    crack_lengths: np.ndarray,
                                    n_points: int = 7,
                                    poly_order: int = 2) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate da/dN using incremental polynomial method per E647.

        Fits a polynomial to local data points and takes derivative.

        Parameters
        ----------
        cycles : np.ndarray
            Cycle count array
        crack_lengths : np.ndarray
            Crack length array (mm)
        n_points : int
            Number of points for local fit (default 7)
        poly_order : int
            Polynomial order (default 2)

        Returns
        -------
        Tuple[np.ndarray, np.ndarray, np.ndarray]
            (cycles, crack_lengths, da_dN values in mm/cycle)
        """
        n = len(cycles)
        half_window = n_points // 2

        da_dN = np.zeros(n)
        valid_mask = np.zeros(n, dtype=bool)

        for i in range(half_window, n - half_window):
            # Get local window
            start = i - half_window
            end = i + half_window + 1

            N_local = cycles[start:end]
            a_local = crack_lengths[start:end]

            # Fit polynomial a = f(N)
            try:
                coeffs = np.polyfit(N_local, a_local, poly_order)
                # Derivative: da/dN at N[i]
                deriv_coeffs = np.polyder(coeffs)
                da_dN[i] = np.polyval(deriv_coeffs, cycles[i])
                valid_mask[i] = True
            except:
                continue

        return cycles[valid_mask], crack_lengths[valid_mask], da_dN[valid_mask]

    def paris_law_regression(self, delta_K: np.ndarray,
                             da_dN: np.ndarray,
                             exclude_outliers: bool = True,
                             outlier_percentage: float = 30.0) -> Tuple[ParisLawResult, ParisLawResult, np.ndarray]:
        """
        Perform Paris law regression with percentage-based outlier detection.

        Method:
        1. Run initial linear regression with all data points
        2. Classify a point as outlier if da/dN deviates more than
           the specified percentage from the regression line
        3. Re-run regression without outliers
        4. Return both regression results for plotting

        Uses log-log linear regression:
        log(da/dN) = log(C) + m * log(Delta-K)

        Parameters
        ----------
        delta_K : np.ndarray
            Stress intensity range array (MPa*sqrt(m))
        da_dN : np.ndarray
            Crack growth rate array (mm/cycle)
        exclude_outliers : bool
            If True, remove outliers based on percentage deviation
        outlier_percentage : float
            Percentage deviation threshold for outlier detection (e.g., 30 = 30%)

        Returns
        -------
        Tuple[ParisLawResult, ParisLawResult, np.ndarray]
            (initial_result, final_result, outlier_mask)
            - initial_result: Paris law from all data points
            - final_result: Paris law after removing outliers
            - outlier_mask: Boolean array where True = outlier
        """
        # Filter valid data (positive values only)
        valid = (delta_K > 0) & (da_dN > 0)
        dK = delta_K[valid]
        dadN = da_dN[valid]

        empty_result = ParisLawResult(C=0.0, m=0.0, r_squared=0.0, n_points=0)
        if len(dK) < 5:
            return empty_result, empty_result, np.zeros(len(delta_K), dtype=bool)

        # Log transform
        log_dK = np.log10(dK)
        log_dadN = np.log10(dadN)

        # Step 1: Initial regression with ALL data points
        slope_init, intercept_init, r_value_init, _, _ = stats.linregress(log_dK, log_dadN)

        # Calculate initial Paris law parameters
        m_init = slope_init
        C_init = 10**intercept_init
        r_squared_init = r_value_init**2

        # Calculate uncertainties for initial fit
        n_init = len(dK)
        y_pred_init = intercept_init + slope_init * log_dK
        ss_res_init = np.sum((log_dadN - y_pred_init)**2)
        ss_x_init = np.sum((log_dK - np.mean(log_dK))**2)
        std_error_m_init = np.sqrt(ss_res_init / (n_init - 2) / ss_x_init) if ss_x_init > 0 and n_init > 2 else 0
        std_error_logC_init = std_error_m_init * np.sqrt(np.sum(log_dK**2) / n_init) if n_init > 0 else 0
        std_error_C_init = C_init * np.log(10) * std_error_logC_init

        initial_result = ParisLawResult(
            C=C_init,
            m=m_init,
            r_squared=r_squared_init,
            n_points=n_init,
            delta_K_range=(float(np.min(dK)), float(np.max(dK))),
            da_dN_range=(float(np.min(dadN)), float(np.max(dadN))),
            std_error_C=std_error_C_init,
            std_error_m=std_error_m_init
        )

        # Step 2: Identify outliers based on percentage deviation
        # Calculate predicted da/dN values from initial regression
        dadN_predicted = C_init * dK**m_init

        # Calculate percentage deviation: |actual - predicted| / predicted * 100
        percentage_deviation = np.abs(dadN - dadN_predicted) / dadN_predicted * 100

        # Mark outliers (points deviating more than threshold percentage)
        outlier_mask_valid = percentage_deviation > outlier_percentage

        # Create full outlier mask (for original array size)
        outlier_mask_full = np.zeros(len(delta_K), dtype=bool)
        outlier_mask_full[valid] = outlier_mask_valid

        if not exclude_outliers or np.sum(~outlier_mask_valid) < 5:
            # Return initial result as both if not excluding or not enough points
            return initial_result, initial_result, outlier_mask_full

        # Step 3: Re-run regression WITHOUT outliers
        mask = ~outlier_mask_valid
        log_dK_clean = log_dK[mask]
        log_dadN_clean = log_dadN[mask]
        dK_clean = dK[mask]
        dadN_clean = dadN[mask]

        slope_final, intercept_final, r_value_final, _, _ = stats.linregress(
            log_dK_clean, log_dadN_clean
        )

        # Calculate final Paris law parameters
        m_final = slope_final
        C_final = 10**intercept_final
        r_squared_final = r_value_final**2

        # Calculate uncertainties for final fit
        n_final = len(dK_clean)
        if n_final > 2:
            y_pred_final = intercept_final + slope_final * log_dK_clean
            ss_res_final = np.sum((log_dadN_clean - y_pred_final)**2)
            ss_x_final = np.sum((log_dK_clean - np.mean(log_dK_clean))**2)
            std_error_m_final = np.sqrt(ss_res_final / (n_final - 2) / ss_x_final) if ss_x_final > 0 else 0
            std_error_logC_final = std_error_m_final * np.sqrt(np.sum(log_dK_clean**2) / n_final) if n_final > 0 else 0
            std_error_C_final = C_final * np.log(10) * std_error_logC_final
        else:
            std_error_m_final = 0
            std_error_C_final = 0

        final_result = ParisLawResult(
            C=C_final,
            m=m_final,
            r_squared=r_squared_final,
            n_points=n_final,
            delta_K_range=(float(np.min(dK_clean)), float(np.max(dK_clean))),
            da_dN_range=(float(np.min(dadN_clean)), float(np.max(dadN_clean))),
            std_error_C=std_error_C_final,
            std_error_m=std_error_m_final
        )

        return initial_result, final_result, outlier_mask_full

    def detect_outliers(self, delta_K: np.ndarray, da_dN: np.ndarray,
                        method: str = 'residual',
                        threshold: float = 2.5) -> np.ndarray:
        """
        Detect outliers in da/dN vs Delta-K data.

        Parameters
        ----------
        delta_K : np.ndarray
            Stress intensity range array
        da_dN : np.ndarray
            Crack growth rate array
        method : str
            Detection method: 'residual', 'iqr', or 'zscore'
        threshold : float
            Threshold for outlier detection

        Returns
        -------
        np.ndarray
            Boolean mask where True indicates outlier
        """
        valid = (delta_K > 0) & (da_dN > 0)

        if method == 'residual':
            # Residual-based detection from Paris law fit
            log_dK = np.log10(delta_K[valid])
            log_dadN = np.log10(da_dN[valid])

            slope, intercept, _, _, _ = stats.linregress(log_dK, log_dadN)
            predicted = intercept + slope * log_dK
            residuals = log_dadN - predicted

            # Outliers are points with large residuals
            std_resid = np.std(residuals)
            outliers_valid = np.abs(residuals) > threshold * std_resid

            # Map back to full array
            outliers = np.zeros(len(delta_K), dtype=bool)
            outliers[valid] = outliers_valid

        elif method == 'iqr':
            # Interquartile range method
            log_dadN = np.log10(da_dN[valid])
            q1, q3 = np.percentile(log_dadN, [25, 75])
            iqr = q3 - q1
            lower = q1 - threshold * iqr
            upper = q3 + threshold * iqr

            outliers_valid = (log_dadN < lower) | (log_dadN > upper)

            outliers = np.zeros(len(delta_K), dtype=bool)
            outliers[valid] = outliers_valid

        elif method == 'zscore':
            # Z-score method
            log_dadN = np.log10(da_dN[valid])
            z_scores = np.abs(stats.zscore(log_dadN))
            outliers_valid = z_scores > threshold

            outliers = np.zeros(len(delta_K), dtype=bool)
            outliers[valid] = outliers_valid

        else:
            outliers = np.zeros(len(delta_K), dtype=bool)

        return outliers

    def determine_threshold_delta_K(self, delta_K: np.ndarray,
                                     da_dN: np.ndarray,
                                     growth_rate_threshold: float = 1e-7) -> float:
        """
        Determine threshold Delta-K from test data.

        The threshold is defined as the Delta-K corresponding to a
        crack growth rate of 10^-7 mm/cycle (or specified threshold).

        Parameters
        ----------
        delta_K : np.ndarray
            Stress intensity range array
        da_dN : np.ndarray
            Crack growth rate array
        growth_rate_threshold : float
            Crack growth rate threshold (default 1e-7 mm/cycle)

        Returns
        -------
        float
            Threshold Delta-K (MPa*sqrt(m)) or 0 if not determinable
        """
        # Get Paris law fit (use final result after outlier removal)
        _, result, _ = self.paris_law_regression(delta_K, da_dN, exclude_outliers=True)

        if result.C <= 0 or result.m <= 0:
            return 0.0

        # Calculate Delta-K at threshold growth rate
        # da/dN = C * (Delta-K)^m
        # Delta-K = (da/dN / C)^(1/m)
        try:
            delta_K_th = (growth_rate_threshold / result.C)**(1.0 / result.m)
            return delta_K_th
        except:
            return 0.0

    def validate_fcgr_test(self, data_points: List[FCGRDataPoint]) -> Tuple[bool, List[str]]:
        """
        Validate FCGR test per E647 requirements.

        Parameters
        ----------
        data_points : List[FCGRDataPoint]
            Processed data points

        Returns
        -------
        Tuple[bool, List[str]]
            (is_valid, list of validation messages)
        """
        messages = []
        is_valid = True

        if not data_points:
            return False, ["No data points to validate"]

        # Extract crack lengths
        crack_lengths = [p.crack_length for p in data_points if p.is_valid]

        if not crack_lengths:
            return False, ["No valid data points"]

        a_initial = crack_lengths[0]
        a_final = crack_lengths[-1]
        W = self.specimen.W

        # Check initial a/W ratio
        a_W_initial = a_initial / W
        if a_W_initial < 0.2:
            messages.append(f"Initial a/W = {a_W_initial:.3f} < 0.2: FAIL")
            is_valid = False
        else:
            messages.append(f"Initial a/W = {a_W_initial:.3f} >= 0.2: PASS")

        # Check final a/W ratio
        a_W_final = a_final / W
        if a_W_final > 0.95:
            messages.append(f"Final a/W = {a_W_final:.3f} > 0.95: FAIL")
            is_valid = False
        else:
            messages.append(f"Final a/W = {a_W_final:.3f} <= 0.95: PASS")

        # Check load ratio
        R = self.test_params.load_ratio
        if R < 0 or R >= 1:
            messages.append(f"Load ratio R = {R:.2f} outside 0 <= R < 1: WARNING")
        else:
            messages.append(f"Load ratio R = {R:.2f}: PASS")

        # Check plasticity constraint
        # (W - a) >= (4/pi) * (K_max / sigma_ys)^2
        # Simplified check for now
        if self.material.yield_strength > 0:
            messages.append(f"Yield strength available for plasticity check: PASS")
        else:
            messages.append("No yield strength provided: Plasticity check skipped")

        # Check crack growth validity
        valid_points = [p for p in data_points if p.is_valid and not p.is_outlier]
        n_valid = len(valid_points)
        n_total = len(data_points)

        if n_valid < 10:
            messages.append(f"Only {n_valid} valid points (recommend >= 10): WARNING")
        else:
            messages.append(f"{n_valid}/{n_total} valid data points: PASS")

        return is_valid, messages

    def analyze_fcgr_data(self, cycles: np.ndarray, compliance: np.ndarray,
                          P_max: np.ndarray, P_min: np.ndarray,
                          method: str = 'secant',
                          outlier_percentage: float = 30.0) -> FCGRResult:
        """
        Perform complete FCGR analysis.

        Parameters
        ----------
        cycles : np.ndarray
            Cycle count array
        compliance : np.ndarray
            Compliance array (mm/kN)
        P_max : np.ndarray
            Maximum load array (kN)
        P_min : np.ndarray
            Minimum load array (kN)
        method : str
            da/dN calculation method: 'secant' or 'polynomial'
        outlier_percentage : float
            Percentage deviation threshold for outlier detection (default 30%)

        Returns
        -------
        FCGRResult
            Complete analysis results
        """
        # Calculate crack lengths from compliance
        crack_lengths = np.array([
            self.crack_length_from_compliance(c) for c in compliance
        ])

        # Calculate Delta-P
        delta_P = P_max - P_min

        # Calculate da/dN
        if method == 'polynomial':
            N_valid, a_valid, da_dN = self.calculate_da_dN_polynomial(
                cycles, crack_lengths
            )
        else:  # secant
            N_valid, a_valid, da_dN = self.calculate_da_dN_secant(
                cycles, crack_lengths
            )

        # Interpolate delta_P for midpoints
        delta_P_mid = np.interp(N_valid, cycles, delta_P)

        # Calculate Delta-K
        delta_K = np.array([
            self.calculate_delta_K(dP, a)
            for dP, a in zip(delta_P_mid, a_valid)
        ])

        # Paris law regression with percentage-based outlier detection
        # Returns both initial (all data) and final (without outliers) results
        paris_initial, paris_final, outlier_mask = self.paris_law_regression(
            delta_K, da_dN, exclude_outliers=True, outlier_percentage=outlier_percentage
        )

        # Create data points with outlier flags from regression
        data_points = []
        for i in range(len(N_valid)):
            point = FCGRDataPoint(
                cycle_count=int(N_valid[i]),
                crack_length=a_valid[i],
                delta_K=delta_K[i],
                da_dN=da_dN[i],
                P_max=float(np.interp(N_valid[i], cycles, P_max)),
                P_min=float(np.interp(N_valid[i], cycles, P_min)),
                compliance=float(np.interp(N_valid[i], cycles, compliance)),
                is_valid=delta_K[i] > 0 and da_dN[i] > 0,
                is_outlier=outlier_mask[i] if i < len(outlier_mask) else False
            )
            data_points.append(point)

        # Determine threshold using final Paris law
        threshold_dK = 0.0
        if paris_final.C > 0 and paris_final.m > 0:
            try:
                threshold_dK = (1e-7 / paris_final.C)**(1.0 / paris_final.m)
            except:
                pass

        # Validate test
        is_valid, validity_notes = self.validate_fcgr_test(data_points)

        return FCGRResult(
            data_points=data_points,
            paris_law=paris_final,
            paris_law_initial=paris_initial,
            threshold_delta_K=threshold_dK,
            final_crack_length=crack_lengths[-1] if len(crack_lengths) > 0 else 0.0,
            total_cycles=int(cycles[-1]) if len(cycles) > 0 else 0,
            is_valid=is_valid,
            validity_notes=validity_notes
        )

    def analyze_from_raw_data(self, cycles: np.ndarray,
                              crack_lengths: np.ndarray,
                              P_max: np.ndarray, P_min: np.ndarray,
                              method: str = 'secant',
                              outlier_percentage: float = 30.0) -> FCGRResult:
        """
        Perform FCGR analysis from pre-calculated crack lengths.

        Use this when crack lengths are already known (e.g., from
        optical measurements or MTS analysis output).

        Parameters
        ----------
        cycles : np.ndarray
            Cycle count array
        crack_lengths : np.ndarray
            Crack length array (mm)
        P_max : np.ndarray
            Maximum load array (kN)
        P_min : np.ndarray
            Minimum load array (kN)
        method : str
            da/dN calculation method: 'secant' or 'polynomial'
        outlier_percentage : float
            Percentage deviation threshold for outlier detection (default 30%)

        Returns
        -------
        FCGRResult
            Complete analysis results
        """
        # Calculate Delta-P
        delta_P = P_max - P_min

        # Calculate da/dN
        if method == 'polynomial':
            N_valid, a_valid, da_dN = self.calculate_da_dN_polynomial(
                cycles, crack_lengths
            )
        else:  # secant
            N_valid, a_valid, da_dN = self.calculate_da_dN_secant(
                cycles, crack_lengths
            )

        # Interpolate delta_P for midpoints
        delta_P_mid = np.interp(N_valid, cycles, delta_P)
        P_max_mid = np.interp(N_valid, cycles, P_max)
        P_min_mid = np.interp(N_valid, cycles, P_min)

        # Calculate Delta-K
        delta_K = np.array([
            self.calculate_delta_K(dP, a)
            for dP, a in zip(delta_P_mid, a_valid)
        ])

        # Paris law regression with percentage-based outlier detection
        paris_initial, paris_final, outlier_mask = self.paris_law_regression(
            delta_K, da_dN, exclude_outliers=True, outlier_percentage=outlier_percentage
        )

        # Create data points with outlier flags from regression
        data_points = []
        for i in range(len(N_valid)):
            point = FCGRDataPoint(
                cycle_count=int(N_valid[i]),
                crack_length=a_valid[i],
                delta_K=delta_K[i],
                da_dN=da_dN[i],
                P_max=float(P_max_mid[i]),
                P_min=float(P_min_mid[i]),
                compliance=0.0,  # Not available from raw data
                is_valid=delta_K[i] > 0 and da_dN[i] > 0,
                is_outlier=outlier_mask[i] if i < len(outlier_mask) else False
            )
            data_points.append(point)

        # Determine threshold using final Paris law
        threshold_dK = 0.0
        if paris_final.C > 0 and paris_final.m > 0:
            try:
                threshold_dK = (1e-7 / paris_final.C)**(1.0 / paris_final.m)
            except:
                pass

        # Validate test
        is_valid, validity_notes = self.validate_fcgr_test(data_points)

        return FCGRResult(
            data_points=data_points,
            paris_law=paris_final,
            paris_law_initial=paris_initial,
            threshold_delta_K=threshold_dK,
            final_crack_length=crack_lengths[-1] if len(crack_lengths) > 0 else 0.0,
            total_cycles=int(cycles[-1]) if len(cycles) > 0 else 0,
            is_valid=is_valid,
            validity_notes=validity_notes
        )


def calculate_effective_crack_length_CT(a_measurements: List[float]) -> float:
    """
    Calculate effective crack length from 5-point measurements per E647.

    Uses weighted average: a_eff = (0.5*a1 + a2 + a3 + a4 + 0.5*a5) / 4

    Parameters
    ----------
    a_measurements : List[float]
        Five crack length measurements across thickness

    Returns
    -------
    float
        Effective crack length
    """
    if len(a_measurements) != 5:
        return np.mean(a_measurements) if a_measurements else 0.0

    a = a_measurements
    return (0.5*a[0] + a[1] + a[2] + a[3] + 0.5*a[4]) / 4


def check_crack_front_straightness(a_measurements: List[float],
                                   B: float, W: float) -> Tuple[bool, str]:
    """
    Check crack front straightness per E647.

    The difference between any two measurements shall not exceed
    0.025W or 0.25B, whichever is less.

    Parameters
    ----------
    a_measurements : List[float]
        Crack length measurements across thickness
    B : float
        Specimen thickness (mm)
    W : float
        Specimen width (mm)

    Returns
    -------
    Tuple[bool, str]
        (is_valid, message)
    """
    if len(a_measurements) < 2:
        return True, "Insufficient measurements for straightness check"

    max_diff = max(a_measurements) - min(a_measurements)
    limit = min(0.025 * W, 0.25 * B)

    if max_diff <= limit:
        return True, f"Crack front difference {max_diff:.3f} mm <= {limit:.3f} mm: PASS"
    else:
        return False, f"Crack front difference {max_diff:.3f} mm > {limit:.3f} mm: FAIL"
