"""
MTS TestSuite XML metadata parser.

Parses XML exports containing specimen geometry and test parameters.
"""

from pathlib import Path
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any


@dataclass
class SpecimenMetadata:
    """
    Specimen metadata from MTS XML export.

    Parameters
    ----------
    specimen_name : str
        Specimen identifier
    geometry_type : str
        Geometry type (Generic, Round, Rectangular)
    diameter : float, optional
        Specimen diameter in mm (for round specimens)
    width : float, optional
        Specimen width in mm (for rectangular specimens)
    thickness : float, optional
        Specimen thickness in mm (for rectangular specimens)
    gauge_length : float, optional
        Gauge length in mm
    parallel_length : float, optional
        Parallel length (Ln) in mm
    ramp_rate : float, optional
        Displacement rate in mm/s
    preload : float, optional
        Preload force in kN
    raw_data : dict
        All parsed data from XML
    """
    specimen_name: str
    geometry_type: str
    diameter: Optional[float] = None
    width: Optional[float] = None
    thickness: Optional[float] = None
    gauge_length: Optional[float] = None
    parallel_length: Optional[float] = None
    ramp_rate: Optional[float] = None
    preload: Optional[float] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


def parse_mts_xml(filepath: Path) -> SpecimenMetadata:
    """
    Parse MTS XML metadata file.

    The MTS XML format uses ArrayOfVariableData elements
    containing Name, Values, and Unit elements.

    Parameters
    ----------
    filepath : Path
        Path to XML file

    Returns
    -------
    SpecimenMetadata
        Parsed specimen metadata

    Raises
    ------
    FileNotFoundError
        If XML file does not exist
    ET.ParseError
        If XML format is invalid

    Examples
    --------
    >>> metadata = parse_mts_xml(Path('specimen.xml'))
    >>> print(f"Diameter: {metadata.diameter} mm")
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"XML file not found: {filepath}")

    tree = ET.parse(filepath)
    root = tree.getroot()

    data: Dict[str, Any] = {}

    # Parse all VariableData elements
    for var_data in root.findall('.//VariableData'):
        name_elem = var_data.find('Name')
        if name_elem is None:
            continue

        name = name_elem.text
        if name is None:
            continue

        values_elem = var_data.find('Values')
        if values_elem is None:
            continue

        value_elem = values_elem.find('Value')
        value_text = value_elem.text if value_elem is not None else None

        unit_elem = var_data.find('Unit')
        unit = unit_elem.text if unit_elem is not None else None

        # Try to convert to numeric
        if value_text:
            try:
                value = float(value_text)
            except ValueError:
                value = value_text
        else:
            value = None

        data[name] = {'value': value, 'unit': unit}

    # Extract specific fields
    def get_value(key: str) -> Optional[float]:
        if key in data and data[key]['value'] is not None:
            try:
                return float(data[key]['value'])
            except (ValueError, TypeError):
                return None
        return None

    def get_string(key: str) -> str:
        if key in data and data[key]['value'] is not None:
            return str(data[key]['value'])
        return ""

    return SpecimenMetadata(
        specimen_name=get_string('SpecimenName'),
        geometry_type=get_string('GeometryType') or 'Generic',
        diameter=get_value('Diameter'),
        width=get_value('Width'),
        thickness=get_value('Thickness'),
        gauge_length=get_value('GageLength'),
        parallel_length=get_value('Ln'),
        ramp_rate=get_value('RampRate'),
        preload=get_value('Preload'),
        raw_data={k: v['value'] for k, v in data.items()}
    )
