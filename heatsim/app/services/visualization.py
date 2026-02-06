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
