"""Parser for thermocouple logger CSV data.

Supports the format from temperature loggers with up to 8 channels.
Format: date;time;network ID;device type;device ID;sensor;data channel;data flags;data sequence number;value;
"""
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import csv
import io


def parse_tc_csv(file_content: str) -> Dict:
    """Parse thermocouple logger CSV data.

    Parameters
    ----------
    file_content : str
        CSV file content as string

    Returns
    -------
    dict
        Parsed data with keys:
        - start_time: datetime
        - end_time: datetime
        - duration_seconds: float
        - times: list of seconds from start
        - channels: dict of {channel_name: [temperatures]}
        - statistics: dict of {channel_name: {min, max, avg}}
    """
    # Parse CSV with semicolon delimiter
    reader = csv.DictReader(io.StringIO(file_content), delimiter=';')

    # Collect data by channel
    channel_data: Dict[str, List[Tuple[datetime, float]]] = {}

    for row in reader:
        try:
            # Parse date and time
            date_str = row.get('date', '').strip()
            time_str = row.get('time', '').strip()
            if not date_str or not time_str:
                continue

            timestamp = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")

            # Get sensor/channel name
            sensor = row.get('sensor', '').strip()
            if not sensor:
                continue

            # Parse value (European decimal format: comma as decimal separator)
            value_str = row.get('value', '').strip()
            if not value_str:
                continue
            value = float(value_str.replace(',', '.'))

            # Add to channel data
            if sensor not in channel_data:
                channel_data[sensor] = []
            channel_data[sensor].append((timestamp, value))

        except (ValueError, KeyError) as e:
            # Skip malformed rows
            continue

    if not channel_data:
        raise ValueError("No valid data found in CSV file")

    # Sort each channel by timestamp
    for sensor in channel_data:
        channel_data[sensor].sort(key=lambda x: x[0])

    # Find global time range
    all_times = []
    for sensor, data in channel_data.items():
        all_times.extend([d[0] for d in data])

    start_time = min(all_times)
    end_time = max(all_times)
    duration_seconds = (end_time - start_time).total_seconds()

    # Extract temperature arrays and times per channel
    channels: Dict[str, List[float]] = {}
    channel_times: Dict[str, List[float]] = {}
    statistics: Dict[str, Dict[str, float]] = {}

    for sensor, data in channel_data.items():
        # Each channel gets its own times array (seconds from global start)
        channel_times[sensor] = [(d[0] - start_time).total_seconds() for d in data]
        temps = [d[1] for d in data]
        channels[sensor] = temps

        # Calculate statistics
        statistics[sensor] = {
            'min': min(temps),
            'max': max(temps),
            'avg': sum(temps) / len(temps),
            'count': len(temps)
        }

    # For backwards compatibility, also provide unified times from first channel
    reference_channel = list(channel_data.keys())[0]
    times = channel_times[reference_channel]

    return {
        'start_time': start_time,
        'end_time': end_time,
        'duration_seconds': duration_seconds,
        'times': times,
        'channels': channels,
        'channel_times': channel_times,  # Per-channel times
        'statistics': statistics
    }


def validate_tc_csv(file_content: str) -> Tuple[bool, str]:
    """Validate TC CSV file format.

    Parameters
    ----------
    file_content : str
        CSV file content as string

    Returns
    -------
    tuple
        (is_valid, error_message)
    """
    try:
        # Check if it has the expected header
        lines = file_content.strip().split('\n')
        if not lines:
            return False, "File is empty"

        header = lines[0].lower()
        if 'date' not in header or 'time' not in header or 'sensor' not in header:
            return False, "Missing required columns (date, time, sensor)"

        if 'value' not in header:
            return False, "Missing 'value' column"

        # Try parsing
        data = parse_tc_csv(file_content)
        if not data['channels']:
            return False, "No valid channel data found"

        return True, f"Found {len(data['channels'])} channels with {len(data['times'])} data points"

    except Exception as e:
        return False, str(e)
