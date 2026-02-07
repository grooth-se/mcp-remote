"""Matplotlib visualization for simulation results.

Generates:
- Cooling curves (T vs t at different locations)
- Temperature profiles (T vs r at different times)
- Phase fraction diagrams
- Cooling rate plots
"""
import io
from typing import List, Optional
import numpy as np

import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for server
import matplotlib.pyplot as plt


def create_cooling_curve_plot(
    times: np.ndarray,
    center_temp: np.ndarray,
    surface_temp: np.ndarray,
    quarter_temp: Optional[np.ndarray] = None,
    title: str = "Cooling Curves",
    transformation_temps: Optional[dict] = None
) -> bytes:
    """Generate cooling curve plot.

    Parameters
    ----------
    times : np.ndarray
        Time array in seconds
    center_temp : np.ndarray
        Center temperature vs time
    surface_temp : np.ndarray
        Surface temperature vs time
    quarter_temp : np.ndarray, optional
        Quarter-thickness temperature vs time
    title : str
        Plot title
    transformation_temps : dict, optional
        Dict with Ms, Mf, Ac1, Ac3 temperatures

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot cooling curves
    ax.plot(times, center_temp, 'b-', linewidth=2, label='Center')
    ax.plot(times, surface_temp, 'r-', linewidth=2, label='Surface')
    if quarter_temp is not None:
        ax.plot(times, quarter_temp, 'g--', linewidth=1.5, label='Quarter')

    # Add transformation temperature lines
    if transformation_temps:
        colors = {'Ms': 'purple', 'Mf': 'magenta', 'Ac1': 'orange', 'Ac3': 'red'}
        for name, temp in transformation_temps.items():
            if temp is not None:
                ax.axhline(y=temp, color=colors.get(name, 'gray'),
                          linestyle=':', alpha=0.7, label=f'{name} = {temp}°C')

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Temperature (°C)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)

    # Convert to PNG bytes
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_temperature_profile_plot(
    positions: np.ndarray,
    temperatures: np.ndarray,
    times: np.ndarray,
    time_indices: List[int],
    title: str = "Temperature Profile",
    is_cylindrical: bool = True
) -> bytes:
    """Generate temperature profile plot at selected times.

    Parameters
    ----------
    positions : np.ndarray
        Spatial positions (radial or thickness)
    temperatures : np.ndarray
        Temperature field [time, position]
    times : np.ndarray
        Time array
    time_indices : list
        Indices of times to plot
    title : str
        Plot title
    is_cylindrical : bool
        If True, label x-axis as radius

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Convert positions to mm
    pos_mm = positions * 1000

    # Plot profiles at selected times
    colors = plt.cm.coolwarm(np.linspace(0, 1, len(time_indices)))

    for i, idx in enumerate(time_indices):
        if idx < len(times):
            t = times[idx]
            T = temperatures[idx, :]
            label = f't = {t:.1f} s'
            ax.plot(pos_mm, T, color=colors[i], linewidth=1.5, label=label)

    xlabel = 'Radius (mm)' if is_cylindrical else 'Distance from center (mm)'
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel('Temperature (°C)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_phase_fraction_plot(
    phases: dict,
    title: str = "Final Phase Fractions"
) -> bytes:
    """Generate phase fraction bar chart.

    Parameters
    ----------
    phases : dict
        Phase fractions {name: fraction}
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(8, 5))

    # Filter out very small fractions
    phases_nonzero = {k: v for k, v in phases.items() if v > 0.01}

    if not phases_nonzero:
        phases_nonzero = phases

    names = list(phases_nonzero.keys())
    fractions = list(phases_nonzero.values())

    # Format names
    display_names = [n.replace('_', ' ').title() for n in names]

    colors = {
        'martensite': '#d62728',
        'bainite': '#ff7f0e',
        'ferrite': '#2ca02c',
        'pearlite': '#1f77b4',
        'retained_austenite': '#9467bd',
        'retained austenite': '#9467bd',
    }
    bar_colors = [colors.get(n, 'gray') for n in names]

    bars = ax.bar(display_names, fractions, color=bar_colors, edgecolor='black')

    # Add percentage labels
    for bar, frac in zip(bars, fractions):
        height = bar.get_height()
        ax.annotate(f'{frac*100:.1f}%',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=11)

    ax.set_ylabel('Volume Fraction', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.set_ylim(0, 1.1)
    ax.grid(True, axis='y', alpha=0.3)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_cooling_rate_plot(
    times: np.ndarray,
    center_temp: np.ndarray,
    surface_temp: np.ndarray,
    title: str = "Cooling Rate"
) -> bytes:
    """Generate cooling rate vs temperature plot.

    Parameters
    ----------
    times : np.ndarray
        Time array
    center_temp : np.ndarray
        Center temperature
    surface_temp : np.ndarray
        Surface temperature
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Calculate cooling rates (dT/dt)
    dt = np.diff(times)
    dt[dt == 0] = 1e-6  # Avoid division by zero

    dT_center = -np.diff(center_temp) / dt
    dT_surface = -np.diff(surface_temp) / dt

    T_center_mid = 0.5 * (center_temp[:-1] + center_temp[1:])
    T_surface_mid = 0.5 * (surface_temp[:-1] + surface_temp[1:])

    ax.plot(T_center_mid, dT_center, 'b-', linewidth=2, label='Center')
    ax.plot(T_surface_mid, dT_surface, 'r-', linewidth=2, label='Surface')

    ax.set_xlabel('Temperature (°C)', fontsize=12)
    ax.set_ylabel('Cooling Rate (°C/s)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.invert_xaxis()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_heat_treatment_cycle_plot(
    times: np.ndarray,
    temperatures: np.ndarray,
    phase_results: Optional[List] = None,
    title: str = "Heat Treatment Cycle",
    transformation_temps: Optional[dict] = None,
    measured_data: Optional[List[dict]] = None
) -> bytes:
    """Generate comprehensive heat treatment cycle plot with phase markers.

    Parameters
    ----------
    times : np.ndarray
        Time array in seconds
    temperatures : np.ndarray
        Temperature field [time, position]
    phase_results : list, optional
        List of PhaseResult objects from multi-phase solver
    title : str
        Plot title
    transformation_temps : dict, optional
        Dict with Ms, Mf, Ac1, Ac3 temperatures
    measured_data : list, optional
        List of dicts with keys: name, times, temps for TC measurements

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    # Extract 4 radial positions
    four_temps = extract_four_point_temperatures(temperatures)

    # Plot simulation temperature curves at 4 radial positions
    for key in ['center', 'one_third', 'two_thirds', 'surface']:
        ax.plot(
            times,
            four_temps[key],
            color=FOUR_POINT_COLORS[key],
            linewidth=2,
            label=f'Sim: {FOUR_POINT_LABELS[key]}',
            linestyle='--' if measured_data else '-'
        )

    # Overlay measured TC data if available
    if measured_data:
        for i, data in enumerate(measured_data):
            color = TC_COLORS[i % len(TC_COLORS)]
            m_times = np.array(data['times'])
            m_temps = np.array(data['temps'])
            name = data.get('name', f'TC{i+1}')

            ax.plot(m_times, m_temps, color=color, linewidth=1.5,
                   label=f'Meas: {name}', alpha=0.9)

    # Add phase region shading if phase results available
    if phase_results:
        phase_colors = {
            'heating': '#FFE4B5',      # Moccasin
            'transfer': '#E6E6FA',     # Lavender
            'quenching': '#B0E0E6',    # Powder blue
            'tempering': '#FFDAB9',    # Peach puff
            'cooling': '#F5F5DC',      # Beige
        }

        for pr in phase_results:
            if pr.time.size < 2:
                continue

            color = phase_colors.get(pr.phase_name, '#F5F5F5')
            start = pr.start_time
            end = pr.end_time

            ax.axvspan(start, end, alpha=0.3, color=color, label=None)

            # Add phase label at top
            mid = (start + end) / 2
            y_pos = ax.get_ylim()[1] * 0.95
            ax.text(mid, y_pos, pr.phase_name.title(),
                   ha='center', va='top', fontsize=9, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7))

    # Add transformation temperature lines
    if transformation_temps:
        colors = {'Ms': 'purple', 'Mf': 'magenta', 'Ac1': 'orange', 'Ac3': 'red'}
        for name, temp in transformation_temps.items():
            if temp is not None:
                ax.axhline(y=temp, color=colors.get(name, 'gray'),
                          linestyle=':', alpha=0.7, linewidth=1.5,
                          label=f'{name} = {temp}°C')

    # Add t8/5 annotation if both 800 and 500 are in range
    center_temp = four_temps['center']
    if transformation_temps and center_temp.max() > 800 and center_temp.min() < 500:
        idx_800 = np.where(center_temp <= 800)[0]
        idx_500 = np.where(center_temp <= 500)[0]
        if len(idx_800) > 0 and len(idx_500) > 0:
            t_800 = times[idx_800[0]]
            t_500 = times[idx_500[0]]
            t8_5 = t_500 - t_800

            # Draw bracket for t8/5
            ax.annotate('', xy=(t_800, 800), xytext=(t_500, 800),
                       arrowprops=dict(arrowstyle='<->', color='darkgreen', lw=1.5))
            ax.text((t_800 + t_500)/2, 810, f't8/5 = {t8_5:.1f}s',
                   ha='center', va='bottom', fontsize=10, color='darkgreen',
                   fontweight='bold')

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Temperature (°C)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


# Colors for 4-point plots: center, 1/3R, 2/3R, surface
FOUR_POINT_COLORS = {
    'center': '#000000',      # Black
    'one_third': '#008080',   # Dark teal (blue-green)
    'two_thirds': '#404040',  # Dark grey
    'surface': '#8B0000',     # Dark red
}

FOUR_POINT_LABELS = {
    'center': 'Center',
    'one_third': '1/3 R',
    'two_thirds': '2/3 R',
    'surface': 'Surface',
}


def extract_four_point_temperatures(temperatures: np.ndarray) -> dict:
    """Extract temperatures at center, 1/3R, 2/3R, and surface.

    Parameters
    ----------
    temperatures : np.ndarray
        Temperature field [time, position]

    Returns
    -------
    dict
        Dictionary with keys: center, one_third, two_thirds, surface
    """
    n_positions = temperatures.shape[1]

    # Calculate indices for the 4 positions
    center_idx = 0
    one_third_idx = n_positions // 3
    two_thirds_idx = 2 * n_positions // 3
    surface_idx = n_positions - 1

    return {
        'center': temperatures[:, center_idx],
        'one_third': temperatures[:, one_third_idx],
        'two_thirds': temperatures[:, two_thirds_idx],
        'surface': temperatures[:, surface_idx],
    }


def create_dTdt_vs_time_plot(
    times: np.ndarray,
    temperatures: np.ndarray,
    title: str = "Temperature Rate vs Time",
    phase_name: str = "heating"
) -> bytes:
    """Generate dT/dt vs time plot for 4 radial positions.

    Parameters
    ----------
    times : np.ndarray
        Time array in seconds
    temperatures : np.ndarray
        Temperature field [time, position]
    title : str
        Plot title
    phase_name : str
        Phase name for labeling (heating/quenching)

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Extract temperatures at 4 positions
    temps = extract_four_point_temperatures(temperatures)

    # Calculate time derivative
    dt = np.diff(times)
    dt[dt == 0] = 1e-6  # Avoid division by zero
    time_mid = 0.5 * (times[:-1] + times[1:])

    for key in ['center', 'one_third', 'two_thirds', 'surface']:
        T = temps[key]
        dTdt = np.diff(T) / dt

        ax.plot(time_mid, dTdt,
                color=FOUR_POINT_COLORS[key],
                linewidth=2,
                label=FOUR_POINT_LABELS[key])

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('dT/dt (°C/s)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_dTdt_vs_temperature_plot(
    times: np.ndarray,
    temperatures: np.ndarray,
    title: str = "Temperature Rate vs Temperature",
    phase_name: str = "heating"
) -> bytes:
    """Generate dT/dt vs temperature plot for 4 radial positions.

    Parameters
    ----------
    times : np.ndarray
        Time array in seconds
    temperatures : np.ndarray
        Temperature field [time, position]
    title : str
        Plot title
    phase_name : str
        Phase name for labeling (heating/quenching)

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Extract temperatures at 4 positions
    temps = extract_four_point_temperatures(temperatures)

    # Calculate time derivative
    dt = np.diff(times)
    dt[dt == 0] = 1e-6  # Avoid division by zero

    for key in ['center', 'one_third', 'two_thirds', 'surface']:
        T = temps[key]
        dTdt = np.diff(T) / dt
        T_mid = 0.5 * (T[:-1] + T[1:])

        ax.plot(T_mid, dTdt,
                color=FOUR_POINT_COLORS[key],
                linewidth=2,
                label=FOUR_POINT_LABELS[key])

    ax.set_xlabel('Temperature (°C)', fontsize=12)
    ax.set_ylabel('dT/dt (°C/s)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)

    # For quenching, higher temp on left makes more sense
    if phase_name == 'quenching':
        ax.invert_xaxis()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


# TC measurement comparison colors
TC_COLORS = [
    '#e41a1c',  # Red
    '#377eb8',  # Blue
    '#4daf4a',  # Green
    '#984ea3',  # Purple
    '#ff7f00',  # Orange
    '#a65628',  # Brown
    '#f781bf',  # Pink
    '#999999',  # Grey
]


def create_comparison_plot(
    sim_times: np.ndarray,
    sim_temps: np.ndarray,
    measured_data: List[dict],
    title: str = "Simulation vs Measured"
) -> bytes:
    """Generate comparison plot of simulation vs measured TC data.

    Parameters
    ----------
    sim_times : np.ndarray
        Simulation time array in seconds
    sim_temps : np.ndarray
        Simulation temperature array (center)
    measured_data : list
        List of dicts with keys: name, times, temps
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    # Plot simulation (thick black dashed line)
    ax.plot(sim_times, sim_temps, 'k--', linewidth=2.5, label='Simulation (Center)', zorder=10)

    # Plot measured data
    for i, data in enumerate(measured_data):
        color = TC_COLORS[i % len(TC_COLORS)]
        times = np.array(data['times'])
        temps = np.array(data['temps'])
        name = data.get('name', f'TC{i+1}')

        ax.plot(times, temps, color=color, linewidth=1.5, label=name, alpha=0.8)

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Temperature (°C)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='best', fontsize=9, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_multi_comparison_plot(
    sim_times: np.ndarray,
    sim_temperatures: np.ndarray,
    measured_data: List[dict],
    title: str = "Simulation vs Measured"
) -> bytes:
    """Generate comparison plot with multiple simulation positions.

    Parameters
    ----------
    sim_times : np.ndarray
        Simulation time array in seconds
    sim_temperatures : np.ndarray
        Simulation temperature field [time, position]
    measured_data : list
        List of dicts with keys: name, times, temps
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    # Extract simulation positions
    sim_four = extract_four_point_temperatures(sim_temperatures)

    # Plot simulation curves (dashed lines)
    for key in ['center', 'one_third', 'two_thirds', 'surface']:
        ax.plot(
            sim_times,
            sim_four[key],
            color=FOUR_POINT_COLORS[key],
            linestyle='--',
            linewidth=2,
            label=f'Sim: {FOUR_POINT_LABELS[key]}',
            alpha=0.7
        )

    # Plot measured data (solid lines)
    for i, data in enumerate(measured_data):
        color = TC_COLORS[i % len(TC_COLORS)]
        times = np.array(data['times'])
        temps = np.array(data['temps'])
        name = data.get('name', f'TC{i+1}')

        ax.plot(times, temps, color=color, linewidth=1.5, label=f'Meas: {name}', alpha=0.9)

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Temperature (°C)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='best', fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()
