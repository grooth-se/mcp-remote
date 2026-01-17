"""
FCGR Test Data Parser for MTS TestSuite CSV Exports.

This module provides functions to parse CSV files exported from MTS TestSuite
software for fatigue crack growth rate (FCGR) testing per ASTM E647.

The parser handles the standard MTS export format with metadata in the
first few lines and data starting after headers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple
import numpy as np
import pandas as pd


@dataclass
class FCGRCycleData:
    """
    Container for parsed FCGR cycle data from MTS CSV export.

    Attributes
    ----------
    cycle_count : np.ndarray
        Cycle count array
    cod : np.ndarray
        Crack opening displacement (mm)
    force : np.ndarray
        Axial force (kN)
    time : np.ndarray
        Running time (s)
    integer_count : np.ndarray
        Integer cycle count
    test_name : str
        Test name from file metadata
    test_run_name : str
        Test run name from file metadata
    test_date : str
        Test date from file metadata
    file_path : str
        Path to the source CSV file
    """
    cycle_count: np.ndarray
    cod: np.ndarray           # Crack Opening Displacement (mm)
    force: np.ndarray         # Force (kN)
    time: np.ndarray          # Time (s)
    integer_count: np.ndarray # Integer cycle count
    test_name: str
    test_run_name: str
    test_date: str
    file_path: str

    @property
    def num_points(self) -> int:
        """Number of data points."""
        return len(self.force)

    @property
    def max_force(self) -> float:
        """Maximum force in kN."""
        return float(np.max(self.force))

    @property
    def min_force(self) -> float:
        """Minimum force in kN."""
        return float(np.min(self.force))

    @property
    def delta_force(self) -> float:
        """Force range in kN."""
        return self.max_force - self.min_force

    @property
    def total_cycles(self) -> int:
        """Total number of cycles."""
        return int(np.max(self.integer_count)) if len(self.integer_count) > 0 else 0


def _parse_mts_metadata(filepath: Path) -> dict:
    """
    Extract metadata from MTS CSV file header.

    Parameters
    ----------
    filepath : Path
        Path to CSV file

    Returns
    -------
    dict
        Dictionary with 'test_name', 'test_run_name', 'test_date' keys
    """
    metadata = {
        'test_name': '',
        'test_run_name': '',
        'test_date': ''
    }

    try:
        encodings = ['utf-8-sig', 'utf-8', 'iso-8859-1', 'cp1252']

        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    lines = [f.readline().strip() for _ in range(8)]
                break
            except UnicodeDecodeError:
                continue

        for line in lines:
            line = line.strip('"').strip("'").strip()

            if line.startswith('Test:'):
                metadata['test_name'] = line.replace('Test:', '').strip()
            elif line.startswith('Test Run:'):
                metadata['test_run_name'] = line.replace('Test Run:', '').strip()
            elif line.startswith('Date:'):
                metadata['test_date'] = line.replace('Date:', '').strip()

    except Exception as e:
        print(f"Warning: Could not parse metadata: {e}")

    return metadata


def _find_column(df: pd.DataFrame, keywords: list) -> Optional[str]:
    """
    Find column name matching any of the keywords (case-insensitive).

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with columns to search
    keywords : list
        List of keywords to match

    Returns
    -------
    str or None
        Matching column name or None if not found
    """
    for col in df.columns:
        col_lower = col.lower().strip()
        for keyword in keywords:
            if keyword.lower() in col_lower:
                return col
    return None


def parse_fcgr_csv(filepath: Path) -> FCGRCycleData:
    """
    Parse MTS TestSuite CSV export file for FCGR test.

    Reads cycle-by-cycle force and COD data exported from MTS TestSuite
    software and returns arrays suitable for FCGR analysis.

    Parameters
    ----------
    filepath : Path
        Path to CSV file exported from MTS TestSuite

    Returns
    -------
    FCGRCycleData
        Container with cycle, force, COD, and time arrays

    Raises
    ------
    FileNotFoundError
        If CSV file does not exist
    ValueError
        If required columns are not found
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    # Parse metadata
    metadata = _parse_mts_metadata(filepath)

    # Try different encodings
    df = None
    encodings = ['utf-8-sig', 'utf-8', 'iso-8859-1', 'cp1252']

    for encoding in encodings:
        try:
            # MTS format: skip first 6 rows (metadata), row 7 is headers
            df = pd.read_csv(filepath, skiprows=6, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
        except Exception:
            try:
                df = pd.read_csv(filepath, skiprows=7, encoding=encoding)
                break
            except:
                continue

    if df is None or df.empty:
        raise ValueError(f"Could not parse CSV file: {filepath}")

    # Clean column names
    df.columns = [str(col).strip().strip('"').strip("'") for col in df.columns]

    # Find required columns
    cycle_col = _find_column(df, ['cyclecount', 'cycle count', 'cycle'])
    force_col = _find_column(df, ['force', 'axial force', 'load'])
    cod_col = _find_column(df, ['cod', 'axial cod', 'crack opening', 'displacement'])
    time_col = _find_column(df, ['time', 'running time', 'elapsed'])
    int_count_col = _find_column(df, ['integer count', 'axial integer'])

    # Validate columns found
    if force_col is None:
        raise ValueError(f"Could not find force column in {filepath}")
    if cod_col is None:
        raise ValueError(f"Could not find COD column in {filepath}")

    # Extract arrays
    force = pd.to_numeric(df[force_col], errors='coerce').values
    cod = pd.to_numeric(df[cod_col], errors='coerce').values

    if cycle_col is not None:
        cycle_count = pd.to_numeric(df[cycle_col], errors='coerce').values
    else:
        cycle_count = np.ones(len(force))

    if time_col is not None:
        time = pd.to_numeric(df[time_col], errors='coerce').values
    else:
        time = np.arange(len(force)) * 0.01

    if int_count_col is not None:
        integer_count = pd.to_numeric(df[int_count_col], errors='coerce').values
    else:
        integer_count = np.cumsum(np.diff(cycle_count, prepend=cycle_count[0]) > 0)

    # Remove NaN values
    valid_mask = ~(np.isnan(force) | np.isnan(cod))
    force = force[valid_mask]
    cod = cod[valid_mask]
    cycle_count = cycle_count[valid_mask]
    time = time[valid_mask]
    integer_count = integer_count[valid_mask]

    if len(force) == 0:
        raise ValueError(f"No valid data points in {filepath}")

    return FCGRCycleData(
        cycle_count=cycle_count,
        cod=cod,
        force=force,
        time=time,
        integer_count=integer_count,
        test_name=metadata['test_name'],
        test_run_name=metadata['test_run_name'],
        test_date=metadata['test_date'],
        file_path=str(filepath)
    )


def extract_cycle_extrema(data: FCGRCycleData) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Extract max/min force and COD for each cycle.

    Parameters
    ----------
    data : FCGRCycleData
        Parsed cycle data

    Returns
    -------
    Tuple containing:
        - cycle_numbers: Unique cycle numbers
        - P_max: Maximum force per cycle (kN)
        - P_min: Minimum force per cycle (kN)
        - COD_max: Maximum COD per cycle (mm)
        - COD_min: Minimum COD per cycle (mm)
    """
    # Get unique cycles
    unique_cycles = np.unique(data.integer_count)

    P_max = np.zeros(len(unique_cycles))
    P_min = np.zeros(len(unique_cycles))
    COD_max = np.zeros(len(unique_cycles))
    COD_min = np.zeros(len(unique_cycles))

    for i, cycle in enumerate(unique_cycles):
        mask = data.integer_count == cycle
        if np.any(mask):
            P_max[i] = np.max(data.force[mask])
            P_min[i] = np.min(data.force[mask])
            COD_max[i] = np.max(data.cod[mask])
            COD_min[i] = np.min(data.cod[mask])

    return unique_cycles, P_max, P_min, COD_max, COD_min


def calculate_compliance_per_cycle(data: FCGRCycleData,
                                   upper_pct: float = 80.0,
                                   lower_pct: float = 20.0) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculate compliance for each cycle from load-COD data.

    Uses linear regression on the upper portion of each cycle's
    loading curve (between lower_pct and upper_pct of max load).

    Parameters
    ----------
    data : FCGRCycleData
        Parsed cycle data
    upper_pct : float
        Upper percentage of max load for fit (default 80%)
    lower_pct : float
        Lower percentage of max load for fit (default 20%)

    Returns
    -------
    Tuple containing:
        - cycle_numbers: Unique cycle numbers
        - compliance: Compliance per cycle (mm/kN)
    """
    from scipy import stats

    unique_cycles = np.unique(data.integer_count)
    compliance = np.zeros(len(unique_cycles))

    for i, cycle in enumerate(unique_cycles):
        mask = data.integer_count == cycle
        if np.sum(mask) < 10:
            continue

        P = data.force[mask]
        COD = data.cod[mask]

        P_max = np.max(P)
        P_lower = P_max * lower_pct / 100
        P_upper = P_max * upper_pct / 100

        fit_mask = (P >= P_lower) & (P <= P_upper)
        if np.sum(fit_mask) < 5:
            continue

        P_fit = P[fit_mask]
        COD_fit = COD[fit_mask]

        # Linear regression: COD = C * P + offset
        slope, intercept, r_value, p_value, std_err = stats.linregress(P_fit, COD_fit)
        compliance[i] = slope if slope > 0 else 0.0

    return unique_cycles, compliance


def validate_fcgr_data(data: FCGRCycleData) -> tuple:
    """
    Validate FCGR test data for analysis.

    Parameters
    ----------
    data : FCGRCycleData
        Parsed test data

    Returns
    -------
    tuple
        (is_valid, list of validation messages)
    """
    messages = []
    is_valid = True

    # Check minimum number of points
    if data.num_points < 100:
        messages.append(f"WARNING: Only {data.num_points} data points (recommend > 100)")

    # Check for positive forces
    if data.min_force < 0:
        messages.append("WARNING: Negative force values detected")

    # Check load ratio is reasonable
    if data.max_force > 0:
        R = data.min_force / data.max_force
        if R < 0 or R > 1:
            messages.append(f"WARNING: Load ratio R = {R:.2f} outside 0-1 range")
        else:
            messages.append(f"Load ratio R = {R:.2f}")

    # Check cycle count
    if data.total_cycles < 100:
        messages.append(f"WARNING: Only {data.total_cycles} cycles")

    if len(messages) == 0:
        messages.append("Data validation passed")

    return is_valid, messages
