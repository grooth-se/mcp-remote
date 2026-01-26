"""
CTOD MTS TestSuite CSV file parsers.

Parses CSV exports from MTS TestSuite software for CTOD testing:
- Pre-crack fatigue data
- Main CTOD test data (Force vs COD)
- Crack size check/compliance data
"""

from pathlib import Path
from dataclasses import dataclass
import numpy as np
import pandas as pd
from typing import Optional


@dataclass
class CTODPrecrackData:
    """
    Container for parsed CTOD pre-crack fatigue data.

    Parameters
    ----------
    cycle_count : np.ndarray
        Fatigue cycle numbers
    cod : np.ndarray
        Crack Opening Displacement (mm)
    force : np.ndarray
        Applied force (kN)
    time : np.ndarray
        Running time (seconds)
    test_name : str
        Test template name
    test_run_name : str
        Test run/specimen name
    test_date : str
        Date and time of test
    total_cycles : int
        Total number of pre-crack cycles
    """
    cycle_count: np.ndarray
    cod: np.ndarray
    force: np.ndarray
    time: np.ndarray
    test_name: str
    test_run_name: str
    test_date: str
    total_cycles: int


@dataclass
class CTODTestData:
    """
    Container for parsed main CTOD test data.

    Parameters
    ----------
    cod : np.ndarray
        Crack Opening Displacement / CMOD (mm)
    displacement : np.ndarray
        Axial displacement / Load-line displacement (mm)
    force : np.ndarray
        Applied force (kN)
    time : np.ndarray
        Running time (seconds)
    test_name : str
        Test template name
    test_run_name : str
        Test run/specimen name
    test_date : str
        Date and time of test
    file_path : str
        Path to source file
    """
    cod: np.ndarray
    displacement: np.ndarray
    force: np.ndarray
    time: np.ndarray
    test_name: str
    test_run_name: str
    test_date: str
    file_path: str


@dataclass
class CTODCrackCheckData:
    """
    Container for crack size check/compliance data.

    Parameters
    ----------
    sequence : np.ndarray
        Check sequence numbers (1, 2, 3, etc.)
    cod : np.ndarray
        Crack Opening Displacement (mm)
    force : np.ndarray
        Applied force (kN)
    time : np.ndarray
        Running time (seconds)
    num_sequences : int
        Number of compliance check sequences
    """
    sequence: np.ndarray
    cod: np.ndarray
    force: np.ndarray
    time: np.ndarray
    num_sequences: int


def _parse_mts_metadata(filepath: Path) -> dict:
    """
    Parse MTS CSV metadata from header lines.

    Parameters
    ----------
    filepath : Path
        Path to CSV file

    Returns
    -------
    dict
        Dictionary with test_name, test_run_name, test_date, file_path_line
    """
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        lines = []
        for _ in range(8):
            line = f.readline().strip()
            if line.startswith('"') and line.endswith('"'):
                line = line[1:-1]
            lines.append(line)

    return {
        'file_path_line': lines[0].replace('File Path: ', '').strip(),
        'test_name': lines[1].replace('Test: ', '').strip(),
        'test_run_name': lines[2].replace('Test Run: ', '').strip(),
        'test_date': lines[3].replace('Date: ', '').strip()
    }


def _read_mts_csv_data(filepath: Path) -> pd.DataFrame:
    """
    Read MTS CSV data, skipping header and handling units row.

    Parameters
    ----------
    filepath : Path
        Path to CSV file

    Returns
    -------
    pd.DataFrame
        Cleaned numeric data
    """
    df = pd.read_csv(
        filepath,
        skiprows=6,
        encoding='utf-8-sig',
        quotechar='"',
        skipinitialspace=True
    )

    # Clean column names
    df.columns = [col.strip().strip('"') for col in df.columns]

    # Check if first row is units row
    first_row = df.iloc[0]
    try:
        if str(first_row.iloc[0]).strip() in ['sec', 'mm', 'kN', 's', 'cycles']:
            df = df.iloc[1:].reset_index(drop=True)
    except (ValueError, TypeError):
        pass

    # Convert to numeric
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Drop NaN rows
    df = df.dropna()

    return df


def parse_ctod_precrack_csv(filepath: Path) -> CTODPrecrackData:
    """
    Parse CTOD pre-crack fatigue CSV file.

    The pre-crack file contains cyclic fatigue data used to create
    a sharp fatigue crack from the machined notch.

    Expected columns: CycleCount, Axial COD, Axial Force, Running Time

    Parameters
    ----------
    filepath : Path
        Path to pre-crack CSV file

    Returns
    -------
    CTODPrecrackData
        Parsed pre-crack data

    Raises
    ------
    FileNotFoundError
        If file does not exist
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Pre-crack CSV file not found: {filepath}")

    metadata = _parse_mts_metadata(filepath)
    df = _read_mts_csv_data(filepath)

    # Find columns by name
    cycle_col = None
    cod_col = None
    force_col = None
    time_col = None

    for col in df.columns:
        col_lower = col.lower()
        if 'cycle' in col_lower and 'count' in col_lower:
            cycle_col = col
        elif 'cod' in col_lower:
            cod_col = col
        elif 'force' in col_lower:
            force_col = col
        elif 'time' in col_lower:
            time_col = col

    # Fallback to positional
    if cycle_col is None and len(df.columns) >= 1:
        cycle_col = df.columns[0]
    if cod_col is None and len(df.columns) >= 2:
        cod_col = df.columns[1]
    if force_col is None and len(df.columns) >= 3:
        force_col = df.columns[2]
    if time_col is None and len(df.columns) >= 4:
        time_col = df.columns[3]

    cycle_count = df[cycle_col].values if cycle_col else np.array([])
    cod = np.abs(df[cod_col].values) if cod_col else np.array([])
    force = np.abs(df[force_col].values) if force_col else np.array([])
    time = df[time_col].values if time_col else np.array([])

    total_cycles = int(np.max(cycle_count)) if len(cycle_count) > 0 else 0

    return CTODPrecrackData(
        cycle_count=cycle_count,
        cod=cod,
        force=force,
        time=time,
        test_name=metadata['test_name'],
        test_run_name=metadata['test_run_name'],
        test_date=metadata['test_date'],
        total_cycles=total_cycles
    )


def parse_ctod_test_csv(filepath: Path) -> CTODTestData:
    """
    Parse main CTOD test CSV file.

    The main test file contains monotonic loading data:
    Force vs COD (CMOD) and displacement.

    Expected columns: Axial COD, Axial Displacement, Axial Force, Running Time

    Parameters
    ----------
    filepath : Path
        Path to CTOD test CSV file

    Returns
    -------
    CTODTestData
        Parsed CTOD test data

    Raises
    ------
    FileNotFoundError
        If file does not exist
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"CTOD test CSV file not found: {filepath}")

    metadata = _parse_mts_metadata(filepath)
    df = _read_mts_csv_data(filepath)

    # Find columns by name
    cod_col = None
    disp_col = None
    force_col = None
    time_col = None

    for col in df.columns:
        col_lower = col.lower()
        if 'cod' in col_lower:
            cod_col = col
        elif 'displacement' in col_lower:
            disp_col = col
        elif 'force' in col_lower:
            force_col = col
        elif 'time' in col_lower:
            time_col = col

    # Fallback to positional (based on MTS format)
    if cod_col is None and len(df.columns) >= 1:
        cod_col = df.columns[0]
    if disp_col is None and len(df.columns) >= 2:
        disp_col = df.columns[1]
    if force_col is None and len(df.columns) >= 3:
        force_col = df.columns[2]
    if time_col is None and len(df.columns) >= 4:
        time_col = df.columns[3]

    cod = np.abs(df[cod_col].values) if cod_col else np.array([])
    displacement = np.abs(df[disp_col].values) if disp_col else np.array([])
    force = np.abs(df[force_col].values) if force_col else np.array([])
    time = df[time_col].values if time_col else np.array([])

    return CTODTestData(
        cod=cod,
        displacement=displacement,
        force=force,
        time=time,
        test_name=metadata['test_name'],
        test_run_name=metadata['test_run_name'],
        test_date=metadata['test_date'],
        file_path=str(filepath)
    )


def parse_ctod_crack_check_csv(filepath: Path) -> CTODCrackCheckData:
    """
    Parse CTOD crack size check CSV file.

    The crack check file contains compliance measurement sequences
    used to verify crack length during/after testing.

    Expected columns: CycleCount, Axial COD, Axial Force, Running Time

    Parameters
    ----------
    filepath : Path
        Path to crack check CSV file

    Returns
    -------
    CTODCrackCheckData
        Parsed crack check data

    Raises
    ------
    FileNotFoundError
        If file does not exist
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Crack check CSV file not found: {filepath}")

    df = _read_mts_csv_data(filepath)

    # Find columns by name
    seq_col = None
    cod_col = None
    force_col = None
    time_col = None

    for col in df.columns:
        col_lower = col.lower()
        if 'cycle' in col_lower:
            seq_col = col
        elif 'cod' in col_lower:
            cod_col = col
        elif 'force' in col_lower:
            force_col = col
        elif 'time' in col_lower:
            time_col = col

    # Fallback to positional
    if seq_col is None and len(df.columns) >= 1:
        seq_col = df.columns[0]
    if cod_col is None and len(df.columns) >= 2:
        cod_col = df.columns[1]
    if force_col is None and len(df.columns) >= 3:
        force_col = df.columns[2]
    if time_col is None and len(df.columns) >= 4:
        time_col = df.columns[3]

    sequence = df[seq_col].values if seq_col else np.array([])
    cod = np.abs(df[cod_col].values) if cod_col else np.array([])
    force = np.abs(df[force_col].values) if force_col else np.array([])
    time = df[time_col].values if time_col else np.array([])

    num_sequences = int(np.max(sequence)) if len(sequence) > 0 else 0

    return CTODCrackCheckData(
        sequence=sequence,
        cod=cod,
        force=force,
        time=time,
        num_sequences=num_sequences
    )
