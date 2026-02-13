"""Preview thermocouple CSV data without saving to database."""
import io
import base64

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from app.services.tc_data_parser import parse_tc_csv, validate_tc_csv


def generate_preview(file_content: str) -> dict:
    """Parse and preview TC CSV data.

    Parameters
    ----------
    file_content : str
        Raw CSV text

    Returns
    -------
    dict
        {valid, message, plot_base64, channels, statistics, duration_seconds}
    """
    is_valid, msg = validate_tc_csv(file_content)
    if not is_valid:
        return {'valid': False, 'message': msg}

    try:
        data = parse_tc_csv(file_content)
    except Exception as e:
        return {'valid': False, 'message': str(e)}

    channels = data['channels']
    statistics = data['statistics']
    times = data['times']
    channel_times = data.get('channel_times', {})

    if not channels:
        return {'valid': False, 'message': 'No channel data found.'}

    # Generate preview plot
    fig, ax = plt.subplots(figsize=(8, 4))
    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22', '#34495e']
    for i, (ch_name, temps) in enumerate(sorted(channels.items())):
        ch_t = channel_times.get(ch_name, times)
        color = colors[i % len(colors)]
        ax.plot(ch_t, temps, color=color, linewidth=1, label=ch_name, alpha=0.85)

    ax.set_xlabel('Time (s)', fontsize=10)
    ax.set_ylabel('Temperature (°C)', fontsize=10)
    ax.set_title('Preview: Temperature vs Time', fontsize=11)
    ax.legend(loc='best', fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    plot_b64 = base64.b64encode(buf.getvalue()).decode('ascii')

    return {
        'valid': True,
        'message': f'{len(channels)} channels, {len(times)} points',
        'plot_base64': plot_b64,
        'channels': list(sorted(channels.keys())),
        'statistics': statistics,
        'duration_seconds': data.get('duration_seconds', 0),
    }
