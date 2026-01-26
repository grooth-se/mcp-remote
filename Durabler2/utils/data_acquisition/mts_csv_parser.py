"""
MTS TestSuite CSV file parser.

Parses CSV exports from MTS TestSuite software containing
time-series test data (force, displacement, extensometer).
"""

from pathlib import Path
from dataclasses import dataclass
import numpy as np
import pandas as pd
from typing import Optional


@dataclass
class MTSTestData:
    """
    Container for parsed MTS test data.

    Parameters
    ----------
    time : np.ndarray
        Time array in seconds
    displacement : np.ndarray
        Actuator displacement array in mm
    force : np.ndarray
        Force array in kN
    extension : np.ndarray
        Extensometer extension array in mm
    test_name : str
        Test template name from MTS
    test_run_name : str
        Test run/specimen name
    test_date : str
        Date and time of test
    file_path : str
        Path to source file
    """
    time: np.ndarray
    displacement: np.ndarray
    force: np.ndarray
    extension: np.ndarray
    test_name: str
    test_run_name: str
    test_date: str
    file_path: str


def parse_mts_csv(filepath: Path) -> MTSTestData:
    """
    Parse MTS TestSuite CSV export file.

    The MTS CSV format has:
    - Lines 1-4: Metadata (file path, test name, test run, date)
    - Lines 5-6: Blank lines
    - Line 7: Column headers with trailing spaces and quotes
    - Line 8: Units row
    - Lines 9+: Numerical data

    Parameters
    ----------
    filepath : Path
        Path to CSV file exported from MTS TestSuite

    Returns
    -------
    MTSTestData
        Parsed test data with arrays and metadata

    Raises
    ------
    FileNotFoundError
        If CSV file does not exist
    ValueError
        If CSV format is not recognized as MTS export

    Examples
    --------
    >>> data = parse_mts_csv(Path('test_001.csv'))
    >>> stress = data.force * 1000 / specimen_area  # MPa
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    # Read metadata from first few lines
    metadata = {}
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        lines = []
        for _ in range(8):
            line = f.readline().strip()
            # Remove surrounding quotes if present
            if line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
            lines.append(line)

    # Parse metadata lines
    # Line 0: File Path: ...
    # Line 1: Test: ...
    # Line 2: Test Run: ...
    # Line 3: Date: ...
    file_path_line = lines[0].replace('File Path: ', '').strip()
    test_name = lines[1].replace('Test: ', '').strip()
    test_run = lines[2].replace('Test Run: ', '').strip()
    test_date = lines[3].replace('Date: ', '').strip()

    # Read data using pandas, skip header metadata rows
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
    is_units_row = False
    try:
        # If first row contains unit strings like 'sec', 'mm', 'kN'
        if str(first_row.iloc[0]).strip() in ['sec', 'mm', 'kN', 's']:
            is_units_row = True
    except (ValueError, TypeError):
        pass

    if is_units_row:
        df = df.iloc[1:].reset_index(drop=True)

    # Convert to numeric, coercing errors
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Drop any rows with NaN values (invalid data)
    df = df.dropna()

    # Extract arrays - handle different possible column names
    time_col = None
    disp_col = None
    force_col = None
    ext_col = None

    for col in df.columns:
        col_lower = col.lower()
        if 'time' in col_lower or col_lower == 'running time':
            time_col = col
        elif 'displacement' in col_lower or col_lower == 'axial displacement':
            disp_col = col
        elif 'force' in col_lower or col_lower == 'axial force':
            force_col = col
        elif 'ext' in col_lower or col_lower == 'axial ext':
            ext_col = col

    # Fallback to column position if names not recognized
    if time_col is None and len(df.columns) >= 1:
        time_col = df.columns[0]
    if disp_col is None and len(df.columns) >= 2:
        disp_col = df.columns[1]
    if force_col is None and len(df.columns) >= 3:
        force_col = df.columns[2]
    if ext_col is None and len(df.columns) >= 4:
        ext_col = df.columns[3]

    time = df[time_col].values if time_col else np.array([])
    displacement = df[disp_col].values if disp_col else np.array([])
    force = df[force_col].values if force_col else np.array([])
    extension = df[ext_col].values if ext_col else np.array([])

    # Apply absolute value - MTS outputs negative values in machine coordinate system
    # Tensile test: displacement increases, force increases until fracture
    displacement = np.abs(displacement)
    force = np.abs(force)
    extension = np.abs(extension)

    return MTSTestData(
        time=time,
        displacement=displacement,
        force=force,
        extension=extension,
        test_name=test_name,
        test_run_name=test_run,
        test_date=test_date,
        file_path=str(filepath)
    )
