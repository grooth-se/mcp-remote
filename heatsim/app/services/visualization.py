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
    measured_data: Optional[List[dict]] = None,
    furnace_temps: Optional[List[dict]] = None
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
    furnace_temps : list, optional
        List of dicts with keys: start_time, end_time, temperature, phase_name
        for furnace/ambient temperature per phase

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

    # Plot furnace/ambient temperature (with ramping support)
    if furnace_temps:
        # Build furnace temperature profile (may include ramps)
        furnace_times = []
        furnace_values = []

        for ft in furnace_temps:
            start_time = ft.get('start_time', 0)
            end_time = ft.get('end_time', 0)
            target_temp = ft.get('temperature')

            # Check if this phase has ramping (cold furnace start)
            cold_furnace = ft.get('cold_furnace', False)
            start_temp = ft.get('furnace_start_temperature', target_temp)
            ramp_rate = ft.get('furnace_ramp_rate', 0)  # °C/min

            if target_temp is not None and end_time > start_time:
                if cold_furnace and ramp_rate > 0 and start_temp != target_temp:
                    # Calculate ramp time
                    ramp_time_sec = abs(target_temp - start_temp) / ramp_rate * 60
                    ramp_end_time = min(start_time + ramp_time_sec, end_time)

                    # Add ramp: start point
                    furnace_times.append(start_time)
                    furnace_values.append(start_temp)
                    # Add ramp: end of ramp
                    furnace_times.append(ramp_end_time)
                    furnace_values.append(target_temp)
                    # Add hold at target until end
                    if ramp_end_time < end_time:
                        furnace_times.append(end_time)
                        furnace_values.append(target_temp)
                else:
                    # Constant temperature (hot furnace or quench)
                    furnace_times.append(start_time)
                    furnace_values.append(target_temp)
                    furnace_times.append(end_time)
                    furnace_values.append(target_temp)

        if furnace_times:
            ax.plot(
                furnace_times,
                furnace_values,
                color='#FF6B00',  # Orange
                linewidth=2.5,
                linestyle='-.',
                label='Furnace/Ambient',
                alpha=0.85,
                zorder=5
            )

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


def create_measured_tc_plot(
    measured_data: List[dict],
    title: str = "Measured Temperature vs Time"
) -> bytes:
    """Generate Temperature vs Time plot for measured TC data only.

    Parameters
    ----------
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

    # Plot measured data
    for i, data in enumerate(measured_data):
        color = TC_COLORS[i % len(TC_COLORS)]
        times = np.array(data['times'])
        temps = np.array(data['temps'])
        name = data.get('name', f'TC{i+1}')

        ax.plot(times, temps, color=color, linewidth=1.5, label=name, alpha=0.9)

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


def filter_outliers_percentile(data: np.ndarray, lower_pct: float = 1, upper_pct: float = 99) -> tuple:
    """Filter outliers using percentile clipping.

    Returns mask of valid (non-outlier) indices and the percentile bounds.
    """
    lower_bound = np.percentile(data, lower_pct)
    upper_bound = np.percentile(data, upper_pct)
    mask = (data >= lower_bound) & (data <= upper_bound)
    return mask, lower_bound, upper_bound


def moving_average(data: np.ndarray, window_size: int = 10) -> np.ndarray:
    """Apply moving average smoothing to data.

    Parameters
    ----------
    data : np.ndarray
        Input data array
    window_size : int
        Number of points to average over

    Returns
    -------
    np.ndarray
        Smoothed data (same length as input, edges handled with smaller windows)
    """
    if window_size < 2:
        return data

    # Use convolution for efficient moving average
    kernel = np.ones(window_size) / window_size
    # 'same' mode keeps output same length as input
    smoothed = np.convolve(data, kernel, mode='same')

    # Fix edge effects by using smaller windows at edges
    half_window = window_size // 2
    for i in range(half_window):
        # Left edge
        smoothed[i] = np.mean(data[:i + half_window + 1])
        # Right edge
        smoothed[-(i + 1)] = np.mean(data[-(i + half_window + 1):])

    return smoothed


def create_measured_dtdt_plot(
    measured_data: List[dict],
    title: str = "Measured dT/dt vs Time",
    filter_outliers: bool = True,
    outlier_percentile: float = 2.0,
    smooth_window: int = 20
) -> bytes:
    """Generate dT/dt vs Time plot for measured TC data.

    Parameters
    ----------
    measured_data : list
        List of dicts with keys: name, times, temps
    title : str
        Plot title
    filter_outliers : bool
        If True, filter outliers for better y-axis scaling
    outlier_percentile : float
        Percentile for outlier filtering (removes below this and above 100-this)
    smooth_window : int
        Window size for moving average smoothing (0 to disable)

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    # Collect all dT/dt values to determine common y-axis limits
    all_dTdt = []

    # Plot dT/dt for each channel
    plot_data = []
    for i, data in enumerate(measured_data):
        times = np.array(data['times'])
        temps = np.array(data['temps'])
        name = data.get('name', f'TC{i+1}')

        # Calculate dT/dt
        dt = np.diff(times)
        dt[dt == 0] = 1e-6  # Avoid division by zero
        dTdt = np.diff(temps) / dt
        time_mid = 0.5 * (times[:-1] + times[1:])

        # Apply moving average smoothing
        if smooth_window > 1:
            dTdt = moving_average(dTdt, smooth_window)

        plot_data.append((time_mid, dTdt, name))
        all_dTdt.extend(dTdt)

    # Determine y-axis limits based on filtered data
    all_dTdt = np.array(all_dTdt)
    if filter_outliers and len(all_dTdt) > 0:
        _, y_min, y_max = filter_outliers_percentile(all_dTdt, outlier_percentile, 100 - outlier_percentile)
        # Add some padding
        y_range = y_max - y_min
        y_min -= 0.1 * y_range
        y_max += 0.1 * y_range
    else:
        y_min, y_max = None, None

    # Now plot
    for i, (time_mid, dTdt, name) in enumerate(plot_data):
        color = TC_COLORS[i % len(TC_COLORS)]
        ax.plot(time_mid, dTdt, color=color, linewidth=1.5, label=name, alpha=0.9)

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('dT/dt (°C/s)', fontsize=12)
    ax.set_title(title + f' (smoothed, window={smooth_window})', fontsize=14)
    ax.legend(loc='best', fontsize=9, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)

    # Apply filtered y-axis limits
    if y_min is not None and y_max is not None:
        ax.set_ylim(y_min, y_max)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_absorbed_power_plot(
    times: np.ndarray,
    temperatures: np.ndarray,
    mass: float,
    cp_values: np.ndarray,
    title: str = "Absorbed Power vs Time",
    phase_name: str = "heating"
) -> bytes:
    """Generate absorbed power vs time plot with total energy annotation.

    Power = m * Cp * dT/dt (W)

    Parameters
    ----------
    times : np.ndarray
        Time array in seconds
    temperatures : np.ndarray
        Temperature field [time, position]
    mass : float
        Part mass in kg
    cp_values : np.ndarray
        Specific heat values at each time point (J/kg·K)
    title : str
        Plot title
    phase_name : str
        Phase name (heating/tempering)

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Extract temperatures at 4 positions
    temps = extract_four_point_temperatures(temperatures)

    # Calculate time derivative and power
    dt = np.diff(times)
    dt[dt == 0] = 1e-6
    time_mid = 0.5 * (times[:-1] + times[1:])

    # Use average Cp for mid-points
    cp_mid = 0.5 * (cp_values[:-1] + cp_values[1:])

    # Calculate power for each position
    total_energies = {}
    for key in ['center', 'one_third', 'two_thirds', 'surface']:
        T = temps[key]
        dTdt = np.diff(T) / dt

        # Power in kW (mass * Cp * dT/dt)
        power_kw = (mass * cp_mid * dTdt) / 1000

        # Only show positive power for heating phases
        if phase_name in ('heating', 'tempering'):
            power_kw = np.maximum(power_kw, 0)

        ax.plot(time_mid, power_kw,
                color=FOUR_POINT_COLORS[key],
                linewidth=2,
                label=FOUR_POINT_LABELS[key])

        # Calculate total energy (integral of power over time)
        # Energy = sum(P * dt) in kJ
        energy_kj = np.sum(power_kw * dt)
        total_energies[key] = energy_kj

    # Calculate average energy across positions
    avg_energy = np.mean(list(total_energies.values()))

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Absorbed Power (kW)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='upper right', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    # Add total energy annotation
    textstr = f'Total Absorbed Energy:\n'
    textstr += f'  Average: {avg_energy:.1f} kJ ({avg_energy/3600:.3f} kWh)\n'
    textstr += f'  Center: {total_energies["center"]:.1f} kJ\n'
    textstr += f'  Surface: {total_energies["surface"]:.1f} kJ'

    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=props)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_measured_absorbed_power_plot(
    measured_data: List[dict],
    mass: float,
    cp_func,
    title: str = "Measured Absorbed Power vs Time",
    phase_name: str = "heating",
    smooth_window: int = 10
) -> bytes:
    """Generate absorbed power vs time plot for measured TC data.

    Parameters
    ----------
    measured_data : list
        List of dicts with keys: name, times, temps
    mass : float
        Part mass in kg
    cp_func : callable
        Function that returns Cp(T) in J/kg·K
    title : str
        Plot title
    phase_name : str
        Phase name (heating/tempering)
    smooth_window : int
        Window size for smoothing

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    total_energies = []

    for i, data in enumerate(measured_data):
        times = np.array(data['times'])
        temps = np.array(data['temps'])
        name = data.get('name', f'TC{i+1}')

        # Calculate dT/dt
        dt = np.diff(times)
        dt[dt == 0] = 1e-6
        dTdt = np.diff(temps) / dt
        time_mid = 0.5 * (times[:-1] + times[1:])
        temp_mid = 0.5 * (temps[:-1] + temps[1:])

        # Get Cp at mid-point temperatures
        cp_mid = np.array([cp_func(t) for t in temp_mid])

        # Power in kW
        power_kw = (mass * cp_mid * dTdt) / 1000

        # Apply smoothing
        if smooth_window > 1:
            power_kw = moving_average(power_kw, smooth_window)

        # Only show positive power for heating
        if phase_name in ('heating', 'tempering'):
            power_kw = np.maximum(power_kw, 0)

        color = TC_COLORS[i % len(TC_COLORS)]
        ax.plot(time_mid, power_kw, color=color, linewidth=1.5, label=name, alpha=0.9)

        # Calculate total energy
        energy_kj = np.sum(np.maximum(power_kw, 0) * dt)
        total_energies.append((name, energy_kj))

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Absorbed Power (kW)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    # Add total energy annotation
    if total_energies:
        textstr = 'Total Absorbed Energy:\n'
        for name, energy in total_energies:
            textstr += f'  {name}: {energy:.1f} kJ\n'
        avg_energy = np.mean([e for _, e in total_energies])
        textstr += f'  Average: {avg_energy:.1f} kJ ({avg_energy/3600:.3f} kWh)'

        props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
        ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=9,
                verticalalignment='top', bbox=props)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_measured_dtdt_vs_temp_plot(
    measured_data: List[dict],
    title: str = "Measured dT/dt vs Temperature",
    filter_outliers: bool = True,
    outlier_percentile: float = 2.0,
    smooth_window: int = 20
) -> bytes:
    """Generate dT/dt vs Temperature plot for measured TC data.

    Parameters
    ----------
    measured_data : list
        List of dicts with keys: name, times, temps
    title : str
        Plot title
    filter_outliers : bool
        If True, filter outliers for better y-axis scaling
    outlier_percentile : float
        Percentile for outlier filtering (removes below this and above 100-this)
    smooth_window : int
        Window size for moving average smoothing (0 to disable)

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    # Collect all dT/dt values to determine common y-axis limits
    all_dTdt = []

    # Plot dT/dt vs T for each channel
    plot_data = []
    for i, data in enumerate(measured_data):
        times = np.array(data['times'])
        temps = np.array(data['temps'])
        name = data.get('name', f'TC{i+1}')

        # Calculate dT/dt
        dt = np.diff(times)
        dt[dt == 0] = 1e-6  # Avoid division by zero
        dTdt = np.diff(temps) / dt
        temp_mid = 0.5 * (temps[:-1] + temps[1:])

        # Apply moving average smoothing
        if smooth_window > 1:
            dTdt = moving_average(dTdt, smooth_window)
            temp_mid = moving_average(temp_mid, smooth_window)

        plot_data.append((temp_mid, dTdt, name))
        all_dTdt.extend(dTdt)

    # Determine y-axis limits based on filtered data
    all_dTdt = np.array(all_dTdt)
    if filter_outliers and len(all_dTdt) > 0:
        _, y_min, y_max = filter_outliers_percentile(all_dTdt, outlier_percentile, 100 - outlier_percentile)
        # Add some padding
        y_range = y_max - y_min
        y_min -= 0.1 * y_range
        y_max += 0.1 * y_range
    else:
        y_min, y_max = None, None

    # Now plot
    for i, (temp_mid, dTdt, name) in enumerate(plot_data):
        color = TC_COLORS[i % len(TC_COLORS)]
        ax.plot(temp_mid, dTdt, color=color, linewidth=1.5, label=name, alpha=0.9)

    ax.set_xlabel('Temperature (°C)', fontsize=12)
    ax.set_ylabel('dT/dt (°C/s)', fontsize=12)
    ax.set_title(title + f' (smoothed, window={smooth_window})', fontsize=14)
    ax.legend(loc='best', fontsize=9, ncol=2)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)

    # Apply filtered y-axis limits
    if y_min is not None and y_max is not None:
        ax.set_ylim(y_min, y_max)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_hardness_profile_plot(
    hardness_result,
    title: str = "Predicted Hardness Profile"
) -> bytes:
    """Generate hardness profile bar chart at 4 radial positions.

    Parameters
    ----------
    hardness_result : HardnessResult
        Hardness prediction results from hardness_predictor
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    # Position labels and keys
    positions = ['center', 'one_third', 'two_thirds', 'surface']
    labels = ['Center', '1/3 R', '2/3 R', 'Surface']

    # Get hardness values
    hv_values = [hardness_result.hardness_hv.get(p, 0) for p in positions]
    hrc_values = [hardness_result.hardness_hrc.get(p) for p in positions]

    # Color gradient: blue (cool center) to red (hot surface)
    colors = ['#3498db', '#2ecc71', '#f39c12', '#e74c3c']

    # Create bar chart
    x = np.arange(len(labels))
    bars = ax.bar(x, hv_values, color=colors, edgecolor='black', linewidth=1.5)

    # Add value labels on bars
    for i, (bar, hv, hrc) in enumerate(zip(bars, hv_values, hrc_values)):
        height = bar.get_height()
        # HV value at top
        ax.annotate(f'{hv:.0f} HV',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=12, fontweight='bold')
        # HRC value inside bar
        if hrc is not None:
            ax.annotate(f'({hrc:.0f} HRC)',
                        xy=(bar.get_x() + bar.get_width() / 2, height / 2),
                        ha='center', va='center', fontsize=10, color='white',
                        fontweight='bold')

    # Styling
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylabel('Hardness (HV)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.set_ylim(0, max(hv_values) * 1.15 if hv_values else 600)
    ax.grid(True, axis='y', alpha=0.3)

    # Add annotation box with CE and DI
    ce = hardness_result.carbon_equivalent
    di = hardness_result.ideal_diameter
    textstr = f'CE(IIW) = {ce:.3f}\nDI = {di:.2f} in'

    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=props)

    # Add t8/5 values at bottom
    t8_5_text = 't8/5: '
    t8_5_parts = []
    for p, label in zip(positions, labels):
        t8_5 = hardness_result.t8_5_values.get(p)
        if t8_5:
            t8_5_parts.append(f'{label}={t8_5:.1f}s')
    t8_5_text += ', '.join(t8_5_parts)

    ax.text(0.5, -0.12, t8_5_text, transform=ax.transAxes, fontsize=9,
            ha='center', color='gray')

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


# Colors for simulation comparison
SIM_COLORS = [
    '#1f77b4',  # Blue
    '#ff7f0e',  # Orange
    '#2ca02c',  # Green
    '#d62728',  # Red
    '#9467bd',  # Purple
]


def create_comparison_overlay_plot(
    sim_data: List[dict],
    title: str = "Temperature Comparison"
) -> bytes:
    """Generate overlay plot comparing multiple simulations.

    Parameters
    ----------
    sim_data : list
        List of dicts with keys: name, times, temps
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(12, 7))

    for i, data in enumerate(sim_data):
        color = SIM_COLORS[i % len(SIM_COLORS)]
        times = np.array(data['times'])
        temps = np.array(data['temps'])
        name = data.get('name', f'Sim {i+1}')

        ax.plot(times, temps, color=color, linewidth=2, label=name, alpha=0.9)

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Temperature (°C)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


# CCT diagram colors
CCT_COLORS = {
    'ferrite': '#2ca02c',      # Green
    'pearlite': '#1f77b4',     # Blue
    'bainite': '#ff7f0e',      # Orange
    'martensite': '#d62728',   # Red
    'austenite': '#9467bd',    # Purple
}


def create_cct_overlay_plot(
    times: np.ndarray,
    temperatures: np.ndarray,
    transformation_temps: dict,
    curves: Optional[dict] = None,
    source_image: Optional[bytes] = None,
    title: str = "Cooling Curve on CCT Diagram",
    positions: Optional[List[str]] = None
) -> bytes:
    """Generate CCT diagram with cooling curve overlay.

    Parameters
    ----------
    times : np.ndarray
        Time array in seconds
    temperatures : np.ndarray
        Temperature field [time, position] or [time] for single curve
    transformation_temps : dict
        Dict with Ms, Mf, Bs, Bf, Ac1, Ac3 temperatures
    curves : dict, optional
        Digitized CCT curves with structure:
        {
            "ferrite": {"start": [[t,T], ...], "finish": [[t,T], ...]},
            "pearlite": {...},
            "bainite": {...}
        }
    source_image : bytes, optional
        Original CCT diagram image to use as background
    title : str
        Plot title
    positions : list, optional
        Position labels for multi-position data

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(12, 8))

    # If source image provided, use as background
    if source_image:
        try:
            from PIL import Image
            import io as io_module
            img = Image.open(io_module.BytesIO(source_image))
            # Note: User would need to calibrate the image axes
            # For now, we'll skip background image and just plot curves
        except Exception:
            pass  # Continue without background image

    # Plot digitized CCT curves if available
    if curves:
        for phase, phase_curves in curves.items():
            color = CCT_COLORS.get(phase, '#333333')

            if isinstance(phase_curves, dict):
                # Start curve
                if 'start' in phase_curves and phase_curves['start']:
                    start_data = np.array(phase_curves['start'])
                    if len(start_data) > 1:
                        ax.plot(start_data[:, 0], start_data[:, 1],
                                color=color, linewidth=2, linestyle='-',
                                label=f'{phase.title()} start')

                # Finish curve
                if 'finish' in phase_curves and phase_curves['finish']:
                    finish_data = np.array(phase_curves['finish'])
                    if len(finish_data) > 1:
                        ax.plot(finish_data[:, 0], finish_data[:, 1],
                                color=color, linewidth=2, linestyle='--',
                                label=f'{phase.title()} finish')

    # Plot transformation temperature lines
    temp_lines = [
        ('Ac3', transformation_temps.get('Ac3'), '#9467bd', 'Ac3'),
        ('Ac1', transformation_temps.get('Ac1'), '#8c564b', 'Ac1'),
        ('Bs', transformation_temps.get('Bs'), '#ff7f0e', 'Bs'),
        ('Ms', transformation_temps.get('Ms'), '#d62728', 'Ms'),
        ('Mf', transformation_temps.get('Mf'), '#e377c2', 'Mf'),
    ]

    x_min = 0.1  # Start at 0.1 seconds for log scale
    x_max = max(times) if len(times) > 0 else 10000

    for name, temp, color, label in temp_lines:
        if temp is not None:
            ax.axhline(y=temp, color=color, linestyle=':', linewidth=1.5,
                      alpha=0.7, label=f'{label} = {temp:.0f}°C')

    # Plot cooling curves (thick lines)
    if temperatures.ndim == 1:
        # Single curve
        valid_mask = times > 0
        ax.plot(times[valid_mask], temperatures[valid_mask],
                'k-', linewidth=3, label='Cooling curve (center)', zorder=10)
    else:
        # Multiple positions
        n_pos = temperatures.shape[1]
        pos_colors = ['#000000', '#555555', '#888888', '#bbbbbb']
        pos_labels = positions if positions else ['Center', '1/3 R', '2/3 R', 'Surface']

        for i in range(min(n_pos, 4)):
            valid_mask = times > 0
            idx = [0, n_pos//3, 2*n_pos//3, n_pos-1][i] if n_pos > 1 else 0
            ax.plot(times[valid_mask], temperatures[valid_mask, idx],
                    color=pos_colors[i], linewidth=2.5,
                    label=f'Cooling curve ({pos_labels[i]})', zorder=10)

    # Formatting
    ax.set_xscale('log')
    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Temperature (°C)', fontsize=12)
    ax.set_title(title, fontsize=14)

    # Set axis limits
    if len(times) > 0:
        ax.set_xlim(x_min, x_max * 1.5)

    y_min = 0
    y_max = max(
        transformation_temps.get('Ac3', 900) or 900,
        np.max(temperatures) if temperatures.size > 0 else 900
    )
    ax.set_ylim(y_min, y_max * 1.1)

    # Legend outside plot
    ax.legend(loc='upper right', fontsize=9, framealpha=0.9)
    ax.grid(True, alpha=0.3, which='both')

    # Add phase region labels if curves exist
    if curves:
        # Add text labels in approximate phase regions
        pass  # Could add later for better visualization

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_ttt_overlay_plot(
    times: np.ndarray,
    temperatures: np.ndarray,
    transformation_temps: dict,
    curves: Optional[dict] = None,
    title: str = "Isothermal Hold on TTT Diagram"
) -> bytes:
    """Generate TTT diagram with isothermal hold overlay.

    Similar to CCT but for isothermal transformations.

    Parameters
    ----------
    times : np.ndarray
        Time array in seconds (from start of isothermal hold)
    temperatures : np.ndarray
        Temperature array (should be relatively constant for TTT)
    transformation_temps : dict
        Dict with Ms, Mf, Bs, Bf, Ac1, Ac3 temperatures
    curves : dict, optional
        Digitized TTT curves
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    # TTT diagram is similar to CCT but typically shows isothermal holds
    # For now, use same implementation
    return create_cct_overlay_plot(
        times, temperatures, transformation_temps, curves,
        title=title
    )


def create_jominy_curve_plot(
    distances_mm: List[float],
    hardness_hv: List[float],
    hardness_hrc: List[Optional[float]],
    j_distance_50hrc: Optional[float] = None,
    title: str = "Jominy End-Quench Curve",
    show_hrc: bool = True
) -> bytes:
    """Generate Jominy end-quench hardenability curve.

    Parameters
    ----------
    distances_mm : list
        Distances from quenched end in mm
    hardness_hv : list
        Vickers hardness at each distance
    hardness_hrc : list
        Rockwell C hardness at each distance (None if HV < 200)
    j_distance_50hrc : float, optional
        Jominy distance where hardness = 50 HRC
    title : str
        Plot title
    show_hrc : bool
        Whether to show HRC scale on right axis

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Plot HV curve
    ax1.plot(distances_mm, hardness_hv, 'b-o', linewidth=2, markersize=6,
             label='Hardness (HV)')
    ax1.set_xlabel('Distance from Quenched End (mm)', fontsize=12)
    ax1.set_ylabel('Hardness (HV)', fontsize=12, color='blue')
    ax1.tick_params(axis='y', labelcolor='blue')

    # Set HV axis limits
    hv_min = min(hardness_hv) * 0.9
    hv_max = max(hardness_hv) * 1.1
    ax1.set_ylim(hv_min, hv_max)
    ax1.set_xlim(0, max(distances_mm) + 2)

    # Add HRC scale on right axis
    if show_hrc:
        ax2 = ax1.twinx()
        # Filter valid HRC values
        valid_hrc = [(d, h) for d, h in zip(distances_mm, hardness_hrc) if h is not None]
        if valid_hrc:
            d_hrc, hrc_vals = zip(*valid_hrc)
            ax2.plot(d_hrc, hrc_vals, 'r--s', linewidth=1.5, markersize=5,
                    alpha=0.7, label='Hardness (HRC)')
            ax2.set_ylabel('Hardness (HRC)', fontsize=12, color='red')
            ax2.tick_params(axis='y', labelcolor='red')

            # Set HRC axis limits based on HV conversion
            hrc_min = max(20, min(hrc_vals) - 5) if hrc_vals else 20
            hrc_max = min(70, max(hrc_vals) + 5) if hrc_vals else 70
            ax2.set_ylim(hrc_min, hrc_max)

    # Mark J50 distance if available
    if j_distance_50hrc is not None:
        ax1.axvline(x=j_distance_50hrc, color='green', linestyle=':', linewidth=2,
                   label=f'J50 = {j_distance_50hrc:.1f} mm')
        ax1.annotate(f'J50 = {j_distance_50hrc:.1f} mm',
                    xy=(j_distance_50hrc, hv_max * 0.95),
                    xytext=(j_distance_50hrc + 5, hv_max * 0.95),
                    fontsize=10, color='green',
                    arrowprops=dict(arrowstyle='->', color='green'))

    # Add reference lines for common hardness thresholds
    # 50 HRC is approximately 513 HV
    if hv_max > 500:
        ax1.axhline(y=513, color='gray', linestyle='--', alpha=0.5, linewidth=1)
        ax1.annotate('50 HRC', xy=(max(distances_mm) - 5, 520), fontsize=9, color='gray')

    ax1.set_title(title, fontsize=14)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='upper right', fontsize=9)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def create_jominy_phases_plot(
    distances_mm: List[float],
    phase_fractions: List[dict],
    title: str = "Phase Distribution - Jominy Test"
) -> bytes:
    """Generate stacked area plot of phase distribution along Jominy bar.

    Parameters
    ----------
    distances_mm : list
        Distances from quenched end in mm
    phase_fractions : list
        Phase fraction dicts at each distance
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    # Extract phase data
    martensite = [pf.get('martensite', 0) * 100 for pf in phase_fractions]
    bainite = [pf.get('bainite', 0) * 100 for pf in phase_fractions]
    ferrite = [pf.get('ferrite', 0) * 100 for pf in phase_fractions]
    pearlite = [pf.get('pearlite', 0) * 100 for pf in phase_fractions]

    # Create stacked area plot
    ax.stackplot(distances_mm,
                 martensite, bainite, ferrite, pearlite,
                 labels=['Martensite', 'Bainite', 'Ferrite', 'Pearlite'],
                 colors=['#d62728', '#ff7f0e', '#2ca02c', '#1f77b4'],
                 alpha=0.8)

    ax.set_xlabel('Distance from Quenched End (mm)', fontsize=12)
    ax.set_ylabel('Phase Fraction (%)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.set_xlim(0, max(distances_mm))
    ax.set_ylim(0, 100)
    ax.legend(loc='center right', fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


# ============================================================
# Sensitivity Analysis Plots
# ============================================================

OUTPUT_LABELS = {
    't8_5': 't₈/₅ (s)',
    'core_cooling_rate': 'Core Cooling Rate (K/s)',
    'surface_cooling_rate': 'Surface Cooling Rate (K/s)',
    'hardness_hv_center': 'Center Hardness (HV)',
    'hardness_hv_surface': 'Surface Hardness (HV)',
}


def create_tornado_plot(
    sensitivity_data: dict,
    output_key: str = 't8_5',
    title: str = "Sensitivity Analysis"
) -> bytes:
    """Generate tornado plot showing parameter impact on a given output.

    Parameters
    ----------
    sensitivity_data : dict
        Result from SensitivityAnalysisResult.to_dict()
    output_key : str
        Which output metric to display
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    parameters = sensitivity_data.get('parameters', [])
    output_label = OUTPUT_LABELS.get(output_key, output_key)

    labels = []
    low_impacts = []
    high_impacts = []

    for p in parameters:
        base_val = p['base_outputs'].get(output_key, 0)
        if base_val == 0:
            continue
        outputs = p['outputs'].get(output_key, [])
        if not outputs:
            continue

        pct_changes = [(v - base_val) / base_val * 100 for v in outputs]
        low_impacts.append(min(pct_changes))
        high_impacts.append(max(pct_changes))
        labels.append(p['label'])

    if not labels:
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.text(0.5, 0.5, f'No sensitivity data for {output_label}',
                ha='center', va='center', transform=ax.transAxes, fontsize=14)
        ax.set_axis_off()
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()

    # Sort by total impact range (largest at top)
    total_impact = [abs(h - l) for h, l in zip(high_impacts, low_impacts)]
    sorted_idx = np.argsort(total_impact)

    fig, ax = plt.subplots(figsize=(10, max(3, len(labels) * 0.8 + 1)))

    y_pos = np.arange(len(labels))
    for i, idx in enumerate(sorted_idx):
        ax.barh(i, high_impacts[idx], color='#e74c3c', alpha=0.75,
                height=0.5, align='center', label='Increase' if i == len(sorted_idx) - 1 else None)
        ax.barh(i, low_impacts[idx], color='#3498db', alpha=0.75,
                height=0.5, align='center', label='Decrease' if i == len(sorted_idx) - 1 else None)

        # Value annotations
        if high_impacts[idx] != 0:
            ax.text(high_impacts[idx] + 0.5, i, f'{high_impacts[idx]:+.1f}%',
                    va='center', ha='left', fontsize=9)
        if low_impacts[idx] != 0:
            ax.text(low_impacts[idx] - 0.5, i, f'{low_impacts[idx]:+.1f}%',
                    va='center', ha='right', fontsize=9)

    ax.set_yticks(y_pos)
    ax.set_yticklabels([labels[i] for i in sorted_idx], fontsize=11)
    ax.set_xlabel(f'% Change in {output_label}', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.axvline(x=0, color='black', linewidth=0.8)
    ax.grid(True, axis='x', alpha=0.3)
    ax.legend(loc='lower right', fontsize=9)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def create_spider_plot(
    sensitivity_data: dict,
    title: str = "Parameter Sensitivity Overview"
) -> bytes:
    """Generate radar/spider chart showing sensitivity of all outputs to all parameters.

    Each output metric is a separate line on the radar chart; each axis is a parameter.

    Parameters
    ----------
    sensitivity_data : dict
        Result from SensitivityAnalysisResult.to_dict()
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    parameters = sensitivity_data.get('parameters', [])
    if not parameters:
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.text(0.5, 0.5, 'No sensitivity data', ha='center', va='center',
                transform=ax.transAxes, fontsize=14)
        ax.set_axis_off()
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()

    param_labels = [p['label'] for p in parameters]
    n_params = len(param_labels)
    angles = np.linspace(0, 2 * np.pi, n_params, endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6']
    output_keys = ['t8_5', 'hardness_hv_center', 'hardness_hv_surface']

    for i, output_key in enumerate(output_keys):
        if output_key not in OUTPUT_LABELS:
            continue

        values = []
        for p in parameters:
            base_val = p['base_outputs'].get(output_key, 0)
            outputs = p['outputs'].get(output_key, [])
            if base_val == 0 or not outputs:
                values.append(0)
                continue
            pct_changes = [abs((v - base_val) / base_val * 100) for v in outputs]
            values.append(max(pct_changes))

        values += values[:1]
        ax.plot(angles, values, 'o-', color=colors[i % len(colors)],
                linewidth=2, label=OUTPUT_LABELS[output_key], markersize=5)
        ax.fill(angles, values, color=colors[i % len(colors)], alpha=0.1)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(param_labels, fontsize=10)
    ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=9)
    ax.set_ylabel('Max % Change', fontsize=10, labelpad=30)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


# ============================================================================
# Optimization Plots
# ============================================================================

def create_convergence_plot(opt_data: dict, title: str = 'Optimization Convergence') -> bytes:
    """Create convergence plot for optimization results.

    Parameters
    ----------
    opt_data : dict
        Optimization result dictionary (from OptimizationResult.to_dict()).
    title : str
        Plot title.

    Returns
    -------
    bytes
        PNG image data.
    """
    iterations = opt_data.get('iterations', [])
    if not iterations:
        return b''

    iters = [it['iteration'] for it in iterations]
    obj_values = [it['objective_value'] for it in iterations]
    feasible = [it['is_feasible'] for it in iterations]

    # Running best
    running_best = []
    best = float('inf')
    for obj, feas in zip(obj_values, feasible):
        if feas and obj < best:
            best = obj
        running_best.append(best if best < float('inf') else obj)

    fig, ax = plt.subplots(figsize=(10, 5))

    # Scatter: feasible vs infeasible
    feas_x = [x for x, f in zip(iters, feasible) if f]
    feas_y = [y for y, f in zip(obj_values, feasible) if f]
    infeas_x = [x for x, f in zip(iters, feasible) if not f]
    infeas_y = [y for y, f in zip(obj_values, feasible) if not f]

    if feas_x:
        ax.scatter(feas_x, feas_y, c='#2196F3', s=40, zorder=3,
                   label='Feasible', alpha=0.7)
    if infeas_x:
        ax.scatter(infeas_x, infeas_y, c='#f44336', s=40, zorder=3,
                   marker='x', label='Infeasible', alpha=0.7)

    # Running best line
    ax.plot(iters, running_best, 'g-', linewidth=2, label='Best so far', zorder=2)

    # Mark overall best
    if feas_x:
        best_idx = feas_y.index(min(feas_y))
        ax.scatter([feas_x[best_idx]], [feas_y[best_idx]], c='gold',
                   s=200, marker='*', zorder=4, edgecolors='black',
                   linewidths=1, label='Best')

    # Objective info
    obj_info = opt_data.get('objective', {})
    direction = obj_info.get('direction', '')
    output_key = obj_info.get('output_key', '')
    if direction == 'target':
        target = obj_info.get('target_value', 0)
        ax.set_ylabel(f'|{output_key} - {target}|', fontsize=11)
    elif direction == 'maximize':
        ax.set_ylabel(f'-{output_key} (maximizing)', fontsize=11)
    else:
        ax.set_ylabel(f'{output_key}', fontsize=11)

    ax.set_xlabel('Evaluation', fontsize=11)
    ax.set_title(title, fontsize=13, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=130, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


# ============================================================================
# HAZ & Preheat Visualization (Phase 14)
# ============================================================================

# Zone colors for HAZ diagrams
HAZ_ZONE_COLORS = {
    'fusion': '#FF4444',       # Red
    'cghaz': '#FF8800',        # Orange
    'fghaz': '#FFCC00',        # Yellow
    'ichaz': '#88CC00',        # Yellow-green
    'base_metal': '#4488FF',   # Blue
}


def create_haz_cross_section_plot(haz_data: dict) -> bytes:
    """Generate HAZ cross-section diagram with colored zone regions.

    Parameters
    ----------
    haz_data : dict
        HAZ result dictionary with zone widths and boundaries

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(12, 5))

    boundaries = haz_data.get('zone_boundaries', {})
    fz = boundaries.get('fusion', 0)
    cghaz = boundaries.get('cghaz', 0)
    fghaz = boundaries.get('fghaz', 0)
    ichaz = boundaries.get('ichaz', 0)

    total_width = max(ichaz * 1.3, 15)  # mm, with margin
    y_height = 8  # mm height for visualization

    # Draw zones as colored rectangles (symmetric about centerline)
    zones = [
        ('Fusion Zone', 0, fz, HAZ_ZONE_COLORS['fusion']),
        ('CGHAZ', fz, cghaz, HAZ_ZONE_COLORS['cghaz']),
        ('FGHAZ', cghaz, fghaz, HAZ_ZONE_COLORS['fghaz']),
        ('ICHAZ', fghaz, ichaz, HAZ_ZONE_COLORS['ichaz']),
        ('Base Metal', ichaz, total_width, HAZ_ZONE_COLORS['base_metal']),
    ]

    for name, x_start, x_end, color in zones:
        if x_end <= x_start:
            continue
        width = x_end - x_start

        # Right side
        rect_r = plt.Rectangle((x_start, 0), width, y_height,
                                facecolor=color, edgecolor='black',
                                linewidth=0.8, alpha=0.7)
        ax.add_patch(rect_r)

        # Left side (mirror)
        rect_l = plt.Rectangle((-x_end, 0), width, y_height,
                                facecolor=color, edgecolor='black',
                                linewidth=0.8, alpha=0.7)
        ax.add_patch(rect_l)

        # Label (right side only)
        mid_x = (x_start + x_end) / 2
        if width > 1.0:
            ax.text(mid_x, y_height / 2, name, ha='center', va='center',
                    fontsize=9, fontweight='bold', rotation=0)
            ax.text(mid_x, y_height * 0.15,
                    f'{width:.1f} mm', ha='center', va='bottom',
                    fontsize=8, color='#333333')

    # Weld center line
    ax.axvline(x=0, color='red', linewidth=2, linestyle='--', label='Weld Center')

    # Dimension annotations
    if ichaz > 0:
        y_dim = y_height + 0.8
        ax.annotate('', xy=(-ichaz, y_dim), xytext=(ichaz, y_dim),
                    arrowprops=dict(arrowstyle='<->', color='black', lw=1.5))
        ax.text(0, y_dim + 0.3,
                f'Total HAZ = {haz_data.get("total_haz_width", 0):.1f} mm',
                ha='center', va='bottom', fontsize=11, fontweight='bold')

    ax.set_xlim(-total_width, total_width)
    ax.set_ylim(-0.5, y_height + 2.5)
    ax.set_xlabel('Distance from Weld Center (mm)', fontsize=12)
    ax.set_title('HAZ Cross-Section', fontsize=14)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.2)

    # Remove y-axis ticks (it's a schematic)
    ax.set_yticks([])

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def create_peak_temperature_profile_plot(
    distances: List[float],
    peak_temps: List[float],
    zone_boundaries: Optional[dict] = None
) -> bytes:
    """Generate peak temperature vs distance from weld center.

    Parameters
    ----------
    distances : list
        Distances from weld center (mm)
    peak_temps : list
        Peak temperatures at each distance (°C)
    zone_boundaries : dict, optional
        Zone boundary distances {zone_name: distance_mm}

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(distances, peak_temps, 'b-', linewidth=2.5, label='Peak Temperature')

    # Add zone shading
    if zone_boundaries:
        fz = zone_boundaries.get('fusion', 0)
        cghaz = zone_boundaries.get('cghaz', 0)
        fghaz = zone_boundaries.get('fghaz', 0)
        ichaz = zone_boundaries.get('ichaz', 0)
        x_max = max(distances) if distances else 20

        zone_fills = [
            (0, fz, HAZ_ZONE_COLORS['fusion'], 'FZ'),
            (fz, cghaz, HAZ_ZONE_COLORS['cghaz'], 'CGHAZ'),
            (cghaz, fghaz, HAZ_ZONE_COLORS['fghaz'], 'FGHAZ'),
            (fghaz, ichaz, HAZ_ZONE_COLORS['ichaz'], 'ICHAZ'),
            (ichaz, x_max, HAZ_ZONE_COLORS['base_metal'], 'BM'),
        ]

        for x_start, x_end, color, label in zone_fills:
            if x_end > x_start:
                ax.axvspan(x_start, x_end, alpha=0.15, color=color, label=label)

    # Reference temperature lines
    ref_temps = [
        (1500, 'Solidus', 'red'),
        (1100, 'Grain Growth', '#FF8800'),
        (900, 'Ac3', '#888800'),
        (727, 'Ac1', 'green'),
    ]
    for temp, label, color in ref_temps:
        ax.axhline(y=temp, color=color, linestyle=':', linewidth=1, alpha=0.6)
        ax.text(max(distances) * 0.95, temp + 20, label,
                ha='right', fontsize=8, color=color)

    ax.set_xlabel('Distance from Weld Center (mm)', fontsize=12)
    ax.set_ylabel('Peak Temperature (°C)', fontsize=12)
    ax.set_title('Peak Temperature Profile', fontsize=14)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def create_hardness_traverse_plot(
    distances: List[float],
    hardness: List[float],
    zone_boundaries: Optional[dict] = None,
    limit_hv: float = 350.0
) -> bytes:
    """Generate hardness traverse plot (HV vs distance).

    Parameters
    ----------
    distances : list
        Distances from weld center (mm)
    hardness : list
        Hardness values (HV) at each distance
    zone_boundaries : dict, optional
        Zone boundary distances
    limit_hv : float
        Maximum acceptable hardness (HV)

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(distances, hardness, 'ko-', linewidth=2, markersize=4, label='Hardness')

    # Limit line
    ax.axhline(y=limit_hv, color='red', linestyle='--', linewidth=2,
               label=f'Limit = {limit_hv:.0f} HV')

    # Color points above limit
    distances_arr = np.array(distances)
    hardness_arr = np.array(hardness)
    above = hardness_arr > limit_hv
    if np.any(above):
        ax.scatter(distances_arr[above], hardness_arr[above],
                  color='red', s=60, zorder=5, label='Exceeds Limit')

    # Add zone shading
    if zone_boundaries:
        fz = zone_boundaries.get('fusion', 0)
        cghaz = zone_boundaries.get('cghaz', 0)
        fghaz = zone_boundaries.get('fghaz', 0)
        ichaz = zone_boundaries.get('ichaz', 0)

        zone_fills = [
            (0, fz, HAZ_ZONE_COLORS['fusion'], 'FZ'),
            (fz, cghaz, HAZ_ZONE_COLORS['cghaz'], 'CGHAZ'),
            (cghaz, fghaz, HAZ_ZONE_COLORS['fghaz'], 'FGHAZ'),
            (fghaz, ichaz, HAZ_ZONE_COLORS['ichaz'], 'ICHAZ'),
        ]
        for x_start, x_end, color, label in zone_fills:
            if x_end > x_start:
                ax.axvspan(x_start, x_end, alpha=0.1, color=color)

    # Pass/fail annotation
    max_hv = max(hardness) if hardness else 0
    if max_hv > limit_hv:
        ax.text(0.02, 0.98, f'FAIL: Max HV = {max_hv:.0f}',
                transform=ax.transAxes, fontsize=12, fontweight='bold',
                color='red', va='top',
                bbox=dict(boxstyle='round', facecolor='#FFE0E0', alpha=0.9))
    else:
        ax.text(0.02, 0.98, f'PASS: Max HV = {max_hv:.0f}',
                transform=ax.transAxes, fontsize=12, fontweight='bold',
                color='green', va='top',
                bbox=dict(boxstyle='round', facecolor='#E0FFE0', alpha=0.9))

    ax.set_xlabel('Distance from Weld Center (mm)', fontsize=12)
    ax.set_ylabel('Hardness (HV)', fontsize=12)
    ax.set_title('Hardness Traverse', fontsize=14)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=100)
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def create_haz_thermal_cycle_comparison_plot(
    thermal_cycles: dict,
    title: str = "HAZ Thermal Cycle Comparison"
) -> bytes:
    """Generate overlaid thermal cycles at different HAZ zone positions.

    Parameters
    ----------
    thermal_cycles : dict
        {zone_label: {'times': [...], 'temps': [...]}}
    title : str
        Plot title

    Returns
    -------
    bytes
        PNG image data
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    cycle_colors = {
        'centerline': '#FF0000',
        'cghaz': '#FF8800',
        'fghaz': '#CCAA00',
        'ichaz': '#44AA00',
        'base_metal': '#0044FF',
    }

    cycle_labels = {
        'centerline': 'Weld Center',
        'cghaz': 'CGHAZ',
        'fghaz': 'FGHAZ',
        'ichaz': 'ICHAZ',
        'base_metal': 'Base Metal',
    }

    for zone, data in thermal_cycles.items():
        times = np.array(data['times'])
        temps = np.array(data['temps'])
        color = cycle_colors.get(zone, 'gray')
        label = cycle_labels.get(zone, zone.replace('_', ' ').title())

        ax.plot(times, temps, color=color, linewidth=2, label=label)

    # Reference lines
    ax.axhline(y=800, color='gray', linestyle=':', alpha=0.5, linewidth=1)
    ax.text(0.01, 0.60, '800°C', transform=ax.transAxes, fontsize=8, color='gray')
    ax.axhline(y=500, color='gray', linestyle=':', alpha=0.5, linewidth=1)
    ax.text(0.01, 0.30, '500°C', transform=ax.transAxes, fontsize=8, color='gray')

    ax.set_xlabel('Time (s)', fontsize=12)
    ax.set_ylabel('Temperature (°C)', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.legend(loc='upper right', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def create_preheat_summary_plot(preheat_data: dict) -> bytes:
    """Generate preheat calculation summary visualization.

    Shows CE values as bars with threshold coloring and preheat/risk text.

    Parameters
    ----------
    preheat_data : dict
        PreheatResult.to_dict() output

    Returns
    -------
    bytes
        PNG image data
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5),
                                    gridspec_kw={'width_ratios': [3, 2]})

    # Left: CE bar chart
    ce_values = {
        'CE(IIW)': preheat_data.get('ce_iiw', 0),
        'Pcm': preheat_data.get('ce_pcm', 0),
        'CEN': preheat_data.get('ce_cen', 0),
    }

    thresholds = {
        'CE(IIW)': [0.35, 0.45],
        'Pcm': [0.20, 0.30],
        'CEN': [0.35, 0.45],
    }

    names = list(ce_values.keys())
    values = list(ce_values.values())

    colors = []
    for name, val in zip(names, values):
        t_low, t_high = thresholds[name]
        if val < t_low:
            colors.append('#2ecc71')  # Green
        elif val < t_high:
            colors.append('#f39c12')  # Orange
        else:
            colors.append('#e74c3c')  # Red

    bars = ax1.bar(names, values, color=colors, edgecolor='black', width=0.5)

    for bar, val in zip(bars, values):
        height = bar.get_height()
        ax1.annotate(f'{val:.3f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 5), textcoords="offset points",
                    ha='center', va='bottom', fontsize=12, fontweight='bold')

    ax1.set_ylabel('Carbon Equivalent', fontsize=12)
    ax1.set_title('Carbon Equivalent Values', fontsize=13)
    ax1.set_ylim(0, max(values) * 1.3 if values else 0.6)
    ax1.grid(True, axis='y', alpha=0.3)

    # Right: Preheat info text
    ax2.set_axis_off()

    preheat_temp = preheat_data.get('preheat_en1011_2', 0)
    risk = preheat_data.get('cracking_risk', 'unknown')
    thickness = preheat_data.get('plate_thickness_mm', 0)
    hi = preheat_data.get('heat_input_kj_mm', 0)
    hydrogen = preheat_data.get('hydrogen_level', 'B')

    risk_colors = {'low': '#2ecc71', 'medium': '#f39c12', 'high': '#e74c3c'}
    risk_color = risk_colors.get(risk, 'gray')

    text_lines = [
        f'Recommended Preheat:  {preheat_temp:.0f}°C',
        f'',
        f'Plate Thickness:  {thickness:.0f} mm',
        f'Heat Input:  {hi:.2f} kJ/mm',
        f'Hydrogen Level:  {hydrogen}',
        f'',
        f'Cracking Risk:  {risk.upper()}',
    ]

    y_pos = 0.9
    for line in text_lines:
        if 'Cracking Risk' in line:
            ax2.text(0.1, y_pos, line, transform=ax2.transAxes,
                    fontsize=13, fontweight='bold', color=risk_color, va='top')
        elif 'Recommended Preheat' in line:
            ax2.text(0.1, y_pos, line, transform=ax2.transAxes,
                    fontsize=14, fontweight='bold', va='top')
        else:
            ax2.text(0.1, y_pos, line, transform=ax2.transAxes,
                    fontsize=11, va='top')
        y_pos -= 0.12

    # Add border box
    ax2.add_patch(plt.Rectangle((0.05, 0.05), 0.9, 0.9,
                                 transform=ax2.transAxes,
                                 fill=False, edgecolor='gray',
                                 linewidth=1.5, linestyle='--'))

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def create_parameter_trajectory_plot(
    opt_data: dict,
    title: str = 'Parameter Trajectory'
) -> bytes:
    """Create parameter trajectory plot.

    Parameters
    ----------
    opt_data : dict
        Optimization result dictionary.
    title : str
        Plot title.

    Returns
    -------
    bytes
        PNG image data.
    """
    iterations = opt_data.get('iterations', [])
    param_defs = opt_data.get('parameters', [])
    if not iterations or not param_defs:
        return b''

    n_params = len(param_defs)
    fig, axes = plt.subplots(n_params, 1, figsize=(10, 3 * n_params), squeeze=False)

    for i, pdef in enumerate(param_defs):
        ax = axes[i, 0]
        key = pdef['key']

        x = [it['iteration'] for it in iterations]
        y = [it['parameters'].get(key, 0) for it in iterations]

        ax.plot(x, y, 'o-', color='#2196F3', markersize=4, linewidth=1.5, alpha=0.7)

        # Bounds
        ax.axhline(pdef['min_value'], color='red', linestyle='--',
                    alpha=0.5, label=f"Min: {pdef['min_value']}")
        ax.axhline(pdef['max_value'], color='red', linestyle='--',
                    alpha=0.5, label=f"Max: {pdef['max_value']}")

        # Mark best
        best_params = opt_data.get('best_parameters', {})
        if key in best_params:
            best_val = best_params[key]
            ax.axhline(best_val, color='green', linestyle='-',
                        alpha=0.8, linewidth=2, label=f'Best: {best_val:.1f}')

        ax.set_ylabel(f"{pdef['label']} ({pdef['unit']})", fontsize=10)
        ax.legend(fontsize=8, loc='upper right')
        ax.grid(True, alpha=0.3)

        if i == 0:
            ax.set_title(title, fontsize=13, fontweight='bold')
        if i == n_params - 1:
            ax.set_xlabel('Evaluation', fontsize=11)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=130, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()
