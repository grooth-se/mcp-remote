"""Parse MTS pre-crack CSV data and calculate compliance metrics.

This module parses CSV data from fatigue pre-cracking phase and validates
compliance with ASTM E399, E647, and E1820 requirements.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional
import math


def parse_precrack_csv(filepath: Path, specimen_geometry: dict) -> dict:
    """
    Parse pre-crack CSV and extract key metrics.

    Uses MTS TestSuite CSV format:
    - Lines 1-4: Metadata (file path, test name, test run, date)
    - Lines 5-6: Blank lines
    - Line 7: Column headers
    - Line 8: Units row
    - Lines 9+: Numerical data

    Args:
        filepath: Path to CSV file
        specimen_geometry: Dict with W, B, B_n, a_0, specimen_type, yield_strength, youngs_modulus

    Returns:
        dict with:
        - total_cycles: int
        - K_max: float (MPa√m) - maximum K during pre-cracking
        - K_min: float (MPa√m)
        - P_max: float (N)
        - P_min: float (N)
        - load_ratio: float (R = Pmin/Pmax)
        - frequency: float (Hz, estimated from time data)
    """
    # Read CSV using MTS format - skip first 6 rows of metadata
    df = pd.read_csv(
        filepath,
        skiprows=6,
        encoding='utf-8-sig',
        quotechar='"',
        skipinitialspace=True
    )

    # Clean column names (remove trailing spaces and quotes)
    df.columns = [col.strip().strip('"') for col in df.columns]

    # Check if first row is units row
    first_row = df.iloc[0]
    try:
        if str(first_row.iloc[0]).strip() in ['sec', 'mm', 'kN', 's', 'N']:
            df = df.iloc[1:].reset_index(drop=True)
    except (ValueError, TypeError):
        pass

    # Convert to numeric
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Drop any rows with NaN values
    df = df.dropna()

    # Find force column
    force_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'force' in col_lower or 'load' in col_lower:
            force_col = col
            break

    # Fallback to column position (force is typically column 3)
    if force_col is None and len(df.columns) >= 3:
        force_col = df.columns[2]

    if force_col is None:
        raise ValueError("Could not find Force column in CSV")

    # Find time column for frequency estimation
    time_col = None
    for col in df.columns:
        col_lower = col.lower()
        if 'time' in col_lower:
            time_col = col
            break

    # Fallback to first column
    if time_col is None and len(df.columns) >= 1:
        time_col = df.columns[0]

    # Get force data (convert to N if in kN)
    force = df[force_col].values.astype(float)
    force = np.abs(force)  # MTS may output negative values
    if np.nanmax(np.abs(force)) < 1000:  # Likely in kN
        force = force * 1000

    # Get extrema
    P_max = float(np.nanmax(force))
    P_min = float(np.nanmin(force))
    if P_min < 0:
        P_min = 0  # Assume tension-tension loading

    # Calculate load ratio
    load_ratio = P_min / P_max if P_max > 0 else 0

    # Estimate cycles from zero crossings or peaks
    # Simple approach: count sign changes in derivative
    force_diff = np.diff(force)
    sign_changes = int(np.sum(np.abs(np.diff(np.sign(force_diff))) > 0))
    total_cycles = max(sign_changes // 4, 1)  # Each cycle has ~4 sign changes

    # Estimate frequency from time data
    frequency = 10.0  # Default
    if time_col is not None:
        time = df[time_col].values.astype(float)
        if len(time) > 100:
            total_time = float(time[-1] - time[0])
            if total_time > 0:
                frequency = float(total_cycles) / total_time

    # Calculate K_max using specimen geometry
    K_max = calculate_K(
        P=P_max,
        W=specimen_geometry.get('W', 50),
        B=specimen_geometry.get('B', 12.5),
        a=specimen_geometry.get('a_0', 10),
        specimen_type=specimen_geometry.get('specimen_type', 'C(T)'),
        S=specimen_geometry.get('S')
    )

    K_min = calculate_K(
        P=P_min,
        W=specimen_geometry.get('W', 50),
        B=specimen_geometry.get('B', 12.5),
        a=specimen_geometry.get('a_0', 10),
        specimen_type=specimen_geometry.get('specimen_type', 'C(T)'),
        S=specimen_geometry.get('S')
    )

    return {
        'total_cycles': int(total_cycles),
        'K_max': float(K_max),
        'K_min': float(K_min),
        'P_max': float(P_max),
        'P_min': float(P_min),
        'load_ratio': float(load_ratio),
        'frequency': float(frequency)
    }


def calculate_K(P: float, W: float, B: float, a: float,
                specimen_type: str = 'C(T)', S: Optional[float] = None) -> float:
    """
    Calculate stress intensity factor K for given geometry.

    Args:
        P: Applied force (N)
        W: Specimen width (mm)
        B: Specimen thickness (mm)
        a: Crack length (mm)
        specimen_type: 'C(T)' or 'SE(B)'
        S: Span for SE(B) specimens (mm)

    Returns:
        K in MPa√m
    """
    a_W = a / W

    if specimen_type == 'C(T)':
        # ASTM E399 C(T) geometry function
        f_aW = ((2 + a_W) / (1 - a_W) ** 1.5) * (
            0.886 + 4.64 * a_W - 13.32 * a_W ** 2 +
            14.72 * a_W ** 3 - 5.6 * a_W ** 4
        )
        K = (P / (B * math.sqrt(W))) * f_aW

    elif specimen_type == 'SE(B)':
        # ASTM E399 SE(B) geometry function
        if S is None:
            S = 4 * W
        S_W = S / W
        f_aW = (3 * S_W * math.sqrt(a_W) / (2 * (1 + 2 * a_W) * (1 - a_W) ** 1.5)) * (
            1.99 - a_W * (1 - a_W) * (2.15 - 3.93 * a_W + 2.7 * a_W ** 2)
        )
        K = (P / (B * math.sqrt(W))) * f_aW

    else:
        # Default to C(T)
        f_aW = ((2 + a_W) / (1 - a_W) ** 1.5) * (
            0.886 + 4.64 * a_W - 13.32 * a_W ** 2 +
            14.72 * a_W ** 3 - 5.6 * a_W ** 4
        )
        K = (P / (B * math.sqrt(W))) * f_aW

    # Convert from N/mm^1.5 to MPa√m
    K_MPa_sqrt_m = K / 1000 * math.sqrt(1000)

    return K_MPa_sqrt_m


def validate_precrack_compliance(
    precrack_data: dict,
    expected_K: float,
    test_standard: str,
    specimen_geometry: dict
) -> dict:
    """
    Check pre-crack compliance with standard requirements.

    Args:
        precrack_data: Output from parse_precrack_csv
        expected_K: Expected test K (KQ for E399, Kmax for E647, etc.)
        test_standard: 'ASTM E399', 'ASTM E647', 'ASTM E1820', 'ASTM E1290'
        specimen_geometry: Dict with W, B, B_n, a_0, notch_height

    Returns:
        dict with:
        - is_valid: bool
        - checks: list of {name, passed, requirement, actual}
    """
    checks = []
    K_max = precrack_data['K_max']

    if 'E399' in test_standard:
        # ASTM E399: Kmax < 60% of expected KQ
        limit = 0.60 * expected_K
        checks.append({
            'name': 'Pre-crack Kmax limit',
            'requirement': f'Kmax < {limit:.1f} MPa√m (60% of expected KQ)',
            'actual': f'{K_max:.1f} MPa√m',
            'passed': K_max < limit
        })

    elif 'E647' in test_standard:
        # ASTM E647: Kmax ≤ initial test Kmax
        checks.append({
            'name': 'Pre-crack Kmax limit',
            'requirement': f'Kmax ≤ {expected_K:.1f} MPa√m (initial test Kmax)',
            'actual': f'{K_max:.1f} MPa√m',
            'passed': K_max <= expected_K
        })

        # E647: Pre-crack extension ≥ max(0.10B, h, 1 mm)
        B = specimen_geometry.get('B', 0)
        h = specimen_geometry.get('notch_height', 0)
        min_extension = max(0.10 * B, h, 1.0)
        checks.append({
            'name': 'Pre-crack extension minimum',
            'requirement': f'Extension ≥ {min_extension:.2f} mm (max of 0.10B, h, 1mm)',
            'actual': 'Verify on fracture surface',
            'passed': True  # Can't verify from CSV alone
        })

    elif 'E1820' in test_standard or 'E1290' in test_standard:
        # ASTM E1820/E1290: Kmax < 65% of expected Kmax
        limit = 0.65 * expected_K
        checks.append({
            'name': 'Pre-crack Kmax limit',
            'requirement': f'Kmax < {limit:.1f} MPa√m (65% of expected)',
            'actual': f'{K_max:.1f} MPa√m',
            'passed': K_max < limit
        })

        # E1820: Pre-crack extension requirements
        B = specimen_geometry.get('B', 0)
        h = specimen_geometry.get('notch_height', 0)
        min_extension = max(0.10 * B, h, 1.0)
        checks.append({
            'name': 'Pre-crack extension minimum',
            'requirement': f'Extension ≥ {min_extension:.2f} mm',
            'actual': 'Verify on fracture surface',
            'passed': True  # Can't verify from CSV alone
        })

    # Check load ratio (common to all standards)
    R = precrack_data['load_ratio']
    if R > 0.5:
        checks.append({
            'name': 'Load ratio during pre-crack',
            'requirement': 'R ≤ 0.5 (recommended)',
            'actual': f'R = {R:.2f}',
            'passed': False
        })
    else:
        checks.append({
            'name': 'Load ratio during pre-crack',
            'requirement': 'R ≤ 0.5 (recommended)',
            'actual': f'R = {R:.2f}',
            'passed': True
        })

    # Ensure all boolean values are Python native bools (not numpy.bool_)
    for check in checks:
        check['passed'] = bool(check['passed'])

    return {
        'is_valid': bool(all(c['passed'] for c in checks)),
        'checks': checks
    }
