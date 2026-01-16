"""
KIC Test Data Parser for MTS TestSuite CSV Exports.

This module provides functions to parse CSV files exported from MTS TestSuite
software for KIC (fracture toughness) testing per ASTM E399.

The parser handles the standard MTS export format with metadata in the
first few lines and data starting after headers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd


@dataclass
class KICTestData:
    """
    Container for parsed KIC test data from MTS CSV export.

    Attributes
    ----------
    displacement : np.ndarray
        Load-line displacement in mm
    force : np.ndarray
        Applied force in kN
    time : np.ndarray
        Running time in seconds
    test_name : str
        Test name from file metadata
    test_run_name : str
        Test run name from file metadata
    test_date : str
        Test date from file metadata
    file_path : str
        Path to the source CSV file
    """
    displacement: np.ndarray    # Load-line displacement (mm)
    force: np.ndarray           # Force (kN)
    time: np.ndarray            # Time (s)
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
    def max_force_index(self) -> int:
        """Index of maximum force."""
        return int(np.argmax(self.force))

    @property
    def displacement_at_max_force(self) -> float:
        """Displacement at maximum force in mm."""
        return float(self.displacement[self.max_force_index])


def _parse_mts_metadata(filepath: Path) -> dict:
    """
    Extract metadata from MTS CSV file header.

    MTS format typically has:
    - Line 1: File Path
    - Line 2: Test name
    - Line 3: Test Run name
    - Line 4: Date
    - Lines 5-6: blank or units
    - Line 7: Column headers
    - Line 8+: Data

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
        # Try UTF-8 first, then fall back to other encodings
        encodings = ['utf-8-sig', 'utf-8', 'iso-8859-1', 'cp1252']

        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    lines = [f.readline().strip() for _ in range(8)]
                break
            except UnicodeDecodeError:
                continue

        # Parse metadata from first few lines
        for line in lines:
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


def parse_kic_csv(filepath: Path) -> KICTestData:
    """
    Parse MTS TestSuite CSV export file for KIC test.

    Reads force-displacement data exported from MTS TestSuite software
    and returns arrays suitable for KIC analysis.

    Parameters
    ----------
    filepath : Path
        Path to CSV file exported from MTS TestSuite

    Returns
    -------
    KICTestData
        Container with time, force, and displacement arrays

    Raises
    ------
    FileNotFoundError
        If CSV file does not exist
    ValueError
        If required columns are not found

    Notes
    -----
    Expected columns:
    - Time (or 'Running Time', 'Elapsed Time')
    - Force (or 'Axial Force', 'Load')
    - Displacement (or 'Axial Displacement', 'Position')

    Examples
    --------
    >>> data = parse_kic_csv(Path('kic_test_001.csv'))
    >>> print(f"Max force: {data.max_force:.2f} kN")
    >>> print(f"Points: {data.num_points}")
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
            # Try with different skip rows
            try:
                df = pd.read_csv(filepath, skiprows=7, encoding=encoding)
                break
            except:
                continue

    if df is None or df.empty:
        raise ValueError(f"Could not parse CSV file: {filepath}")

    # Clean column names (remove quotes, whitespace)
    df.columns = [str(col).strip().strip('"').strip("'") for col in df.columns]

    # Find required columns
    time_col = _find_column(df, ['time', 'running time', 'elapsed'])
    force_col = _find_column(df, ['force', 'load', 'axial force'])
    disp_col = _find_column(df, ['displacement', 'position', 'axial displacement',
                                  'stroke', 'crosshead'])

    # Validate columns found
    if force_col is None:
        raise ValueError(f"Could not find force column in {filepath}")
    if disp_col is None:
        raise ValueError(f"Could not find displacement column in {filepath}")

    # Extract arrays
    force = pd.to_numeric(df[force_col], errors='coerce').values
    displacement = pd.to_numeric(df[disp_col], errors='coerce').values

    if time_col is not None:
        time = pd.to_numeric(df[time_col], errors='coerce').values
    else:
        # Generate time array from index
        time = np.arange(len(force)) * 0.01  # Assume 100 Hz sampling

    # Remove NaN values
    valid_mask = ~(np.isnan(force) | np.isnan(displacement))
    force = force[valid_mask]
    displacement = displacement[valid_mask]
    time = time[valid_mask]

    # Ensure arrays are not empty
    if len(force) == 0:
        raise ValueError(f"No valid data points in {filepath}")

    return KICTestData(
        displacement=displacement,
        force=force,
        time=time,
        test_name=metadata['test_name'],
        test_run_name=metadata['test_run_name'],
        test_date=metadata['test_date'],
        file_path=str(filepath)
    )


def validate_kic_data(data: KICTestData) -> tuple:
    """
    Validate KIC test data for analysis.

    Parameters
    ----------
    data : KICTestData
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
    if np.any(data.force < 0):
        messages.append("WARNING: Negative force values detected")

    # Check for monotonic displacement (mostly increasing)
    disp_diff = np.diff(data.displacement)
    if np.sum(disp_diff < 0) > len(disp_diff) * 0.1:
        messages.append("WARNING: Significant non-monotonic displacement")

    # Check max force is reasonable
    if data.max_force < 0.1:
        messages.append("WARNING: Maximum force very low (< 0.1 kN)")
        is_valid = False

    # Check displacement range
    disp_range = np.max(data.displacement) - np.min(data.displacement)
    if disp_range < 0.01:
        messages.append("WARNING: Very small displacement range")
        is_valid = False

    if len(messages) == 0:
        messages.append("Data validation passed")

    return is_valid, messages
