"""Builders for interactive (Plotly) simulation plot data.

Each builder returns a JSON-serializable dict:

    {"traces": [{"x": [...], "y": [...], "name": str, "mode": "lines", ...}],
     "layout": {"title": str, "xaxis_title": str, "yaxis_title": str,
                "shapes": [...], "annotations": [...]}}

or None when the simulation has no data for that plot. The traces mirror
the matplotlib plots in app/services/visualization.py so the interactive
charts show the same information as the stored PNGs (used in reports).
"""

import numpy as np

from app.services.visualization import (
    FOUR_POINT_COLORS,
    FOUR_POINT_LABELS,
    moving_average,
)

MAX_TRACE_POINTS = 2000

POSITION_KEYS = ["center", "one_third", "two_thirds", "surface"]

PHASE_REGION_COLORS = {
    "heating": "rgba(255, 228, 181, 0.3)",
    "transfer": "rgba(230, 230, 250, 0.3)",
    "quenching": "rgba(176, 224, 230, 0.3)",
    "tempering": "rgba(255, 218, 185, 0.3)",
    "cooling": "rgba(245, 245, 220, 0.3)",
}

TRANSFORMATION_COLORS = {"Ms": "purple", "Mf": "magenta", "Ac1": "orange", "Ac3": "red"}

# Measured channel colors (mirror visualization.TC_COLORS intent)
MEASURED_COLORS = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
]


def _decimate(xs, ys, max_points=MAX_TRACE_POINTS):
    """Stride-decimate paired arrays, always keeping the last point."""
    xs = list(xs)
    ys = list(ys)
    n = min(len(xs), len(ys))
    if n <= max_points:
        return xs[:n], ys[:n]
    step = max(1, n // max_points)
    dx = xs[:n:step]
    dy = ys[:n:step]
    if dx[-1] != xs[n - 1]:
        dx.append(xs[n - 1])
        dy.append(ys[n - 1])
    return dx, dy


def _line_trace(xs, ys, name, color=None, dash=None, width=2):
    xs, ys = _decimate(xs, ys)
    trace = {"x": xs, "y": ys, "name": name, "mode": "lines", "line": {"width": width}}
    if color:
        trace["line"]["color"] = color
    if dash:
        trace["line"]["dash"] = dash
    return trace


def _layout(title, xaxis_title, yaxis_title):
    return {"title": title, "xaxis_title": xaxis_title, "yaxis_title": yaxis_title}


def _latest_results(sim):
    """Result rows from the latest completed run only.

    Every run keeps its results under a snapshot for the history feature, so
    unscoped queries would mix old and new runs in one chart. Mirrors the
    scoping used by the simulation view route.
    """
    from app.models.simulation import SimulationResult

    snapshot = sim.snapshots.filter_by(status="completed").first()
    if snapshot:
        return SimulationResult.query.filter_by(snapshot_id=snapshot.id)
    return sim.results


def _full_cycle_result(sim):
    return _latest_results(sim).filter_by(result_type="full_cycle").first()


def _position_traces(times, data_dict, fallback_values=None):
    """Build one trace per stored radial position (or a single center trace)."""
    traces = []
    if data_dict.get("positions"):
        for key in POSITION_KEYS:
            values = data_dict.get(key)
            if values:
                traces.append(
                    _line_trace(times, values, FOUR_POINT_LABELS[key], FOUR_POINT_COLORS[key])
                )
    elif fallback_values:
        traces.append(
            _line_trace(
                times, fallback_values, FOUR_POINT_LABELS["center"], FOUR_POINT_COLORS["center"]
            )
        )
    return traces


def _furnace_trace(furnace_segments):
    """Rebuild the furnace/ambient profile polyline (mirrors visualization.py)."""
    times = []
    values = []
    for ft in furnace_segments:
        start_time = ft.get("start_time", 0)
        end_time = ft.get("end_time", 0)
        target = ft.get("temperature")
        if target is None or end_time <= start_time:
            continue
        cold_furnace = ft.get("cold_furnace", False)
        start_temp = ft.get("furnace_start_temperature", target)
        ramp_rate = ft.get("furnace_ramp_rate", 0)
        if cold_furnace and ramp_rate and start_temp != target:
            ramp_end = min(start_time + abs(target - start_temp) / ramp_rate * 60, end_time)
            times.extend([start_time, ramp_end])
            values.extend([start_temp, target])
            if ramp_end < end_time:
                times.append(end_time)
                values.append(target)
        else:
            times.extend([start_time, end_time])
            values.extend([target, target])
    if not times:
        return None
    trace = _line_trace(times, values, "Furnace/Ambient", "#FF6B00", dash="dashdot", width=2.5)
    return trace


def _phase_region_shapes(furnace_segments):
    shapes = []
    annotations = []
    for ft in furnace_segments:
        start = ft.get("start_time", 0)
        end = ft.get("end_time", 0)
        phase_name = ft.get("phase_name", "")
        if end <= start:
            continue
        shapes.append(
            {
                "type": "rect",
                "xref": "x",
                "yref": "paper",
                "x0": start,
                "x1": end,
                "y0": 0,
                "y1": 1,
                "fillcolor": PHASE_REGION_COLORS.get(phase_name, "rgba(245,245,245,0.3)"),
                "line": {"width": 0},
                "layer": "below",
            }
        )
        annotations.append(
            {
                "x": (start + end) / 2,
                "y": 1,
                "xref": "x",
                "yref": "paper",
                "text": phase_name.title(),
                "showarrow": False,
                "yanchor": "bottom",
                "font": {"size": 10},
            }
        )
    return shapes, annotations


def _transformation_shapes(sim):
    """Horizontal dotted lines for Ms/Mf/Ac1/Ac3."""
    shapes = []
    annotations = []
    diagram = sim.steel_grade.phase_diagrams.first() if sim.steel_grade else None
    temps = diagram.temps_dict if diagram else {}
    for name, temp in (temps or {}).items():
        if temp is None:
            continue
        shapes.append(
            {
                "type": "line",
                "xref": "paper",
                "yref": "y",
                "x0": 0,
                "x1": 1,
                "y0": temp,
                "y1": temp,
                "line": {
                    "color": TRANSFORMATION_COLORS.get(name, "gray"),
                    "width": 1,
                    "dash": "dot",
                },
            }
        )
        annotations.append(
            {
                "x": 1,
                "y": temp,
                "xref": "paper",
                "yref": "y",
                "text": f"{name} = {temp}°C",
                "showarrow": False,
                "xanchor": "right",
                "yanchor": "bottom",
                "font": {"size": 9},
            }
        )
    return shapes, annotations


def full_cycle(sim):
    """Full heat-treatment cycle: 4 positions + furnace profile + phase regions."""
    result = _full_cycle_result(sim)
    if not result:
        return None
    times = result.time_array
    if not times:
        return None

    data = result.data_dict
    traces = _position_traces(times, data, fallback_values=result.value_array)
    if not traces:
        return None

    layout = _layout(f"Heat Treatment Cycle - {sim.name}", "Time (s)", "Temperature (°C)")
    shapes = []
    annotations = []

    furnace_segments = data.get("furnace_segments") or []
    furnace = _furnace_trace(furnace_segments)
    if furnace:
        traces.append(furnace)
    region_shapes, region_annotations = _phase_region_shapes(furnace_segments)
    shapes.extend(region_shapes)
    annotations.extend(region_annotations)

    trans_shapes, trans_annotations = _transformation_shapes(sim)
    shapes.extend(trans_shapes)
    annotations.extend(trans_annotations)

    # t8/5 annotation on the center curve
    center = data.get("center") or result.value_array
    if center:
        center_arr = np.array(center, dtype=float)
        times_arr = np.array(times, dtype=float)
        if center_arr.max() > 800 and center_arr.min() < 500:
            idx_800 = np.where(center_arr <= 800)[0]
            idx_500 = np.where(center_arr <= 500)[0]
            if len(idx_800) > 0 and len(idx_500) > 0:
                t_800 = float(times_arr[idx_800[0]])
                t_500 = float(times_arr[idx_500[0]])
                annotations.append(
                    {
                        "x": (t_800 + t_500) / 2,
                        "y": 810,
                        "xref": "x",
                        "yref": "y",
                        "text": f"t8/5 = {t_500 - t_800:.1f}s",
                        "showarrow": False,
                        "font": {"size": 10, "color": "darkgreen"},
                    }
                )

    if shapes:
        layout["shapes"] = shapes
    if annotations:
        layout["annotations"] = annotations
    return {"traces": traces, "layout": layout}


def phase_curve(sim, phase):
    """Temperature vs time for one process phase (all stored positions)."""
    rows = [
        r
        for r in _latest_results(sim).filter_by(phase=phase).all()
        if r.result_type in ("cooling_curve", "heating_curve")
    ]
    if not rows:
        return None
    traces = []
    for row in rows:
        times = row.time_array
        if not times:
            continue
        traces.extend(_position_traces(times, row.data_dict, fallback_values=row.value_array))
    if not traces:
        return None
    layout = _layout(f"{phase.title()} - Temperature vs Time", "Time (s)", "Temperature (°C)")
    return {"traces": traces, "layout": layout}


def _phase_position_series(sim, phase):
    """(times, {position: temps}) for a phase, falling back to center-only."""
    rows = [
        r
        for r in _latest_results(sim).filter_by(phase=phase).all()
        if r.result_type in ("cooling_curve", "heating_curve")
    ]
    for row in rows:
        times = row.time_array
        if not times:
            continue
        data = row.data_dict
        if data.get("positions"):
            series = {k: data[k] for k in POSITION_KEYS if data.get(k)}
        elif row.value_array:
            series = {"center": row.value_array}
        else:
            continue
        return times, series
    return None, None


def dtdt_time(sim, phase):
    """dT/dt vs time for one process phase, derived from stored temperatures."""
    times, series = _phase_position_series(sim, phase)
    if not times or len(times) < 3:
        return None
    times_arr = np.array(times, dtype=float)
    dt = np.diff(times_arr)
    dt[dt == 0] = 1e-6
    mid = 0.5 * (times_arr[:-1] + times_arr[1:])
    traces = []
    for key, temps in series.items():
        dTdt = np.diff(np.array(temps, dtype=float)) / dt
        traces.append(
            _line_trace(
                mid.tolist(),
                dTdt.tolist(),
                FOUR_POINT_LABELS.get(key, key),
                FOUR_POINT_COLORS.get(key),
            )
        )
    layout = _layout(f"dT/dt vs Time ({phase.title()})", "Time (s)", "dT/dt (°C/s)")
    return {"traces": traces, "layout": layout}


def dtdt_temp(sim, phase):
    """dT/dt vs temperature for one process phase."""
    times, series = _phase_position_series(sim, phase)
    if not times or len(times) < 3:
        return None
    times_arr = np.array(times, dtype=float)
    dt = np.diff(times_arr)
    dt[dt == 0] = 1e-6
    traces = []
    for key, temps in series.items():
        temps_arr = np.array(temps, dtype=float)
        dTdt = np.diff(temps_arr) / dt
        temp_mid = 0.5 * (temps_arr[:-1] + temps_arr[1:])
        traces.append(
            _line_trace(
                temp_mid.tolist(),
                dTdt.tolist(),
                FOUR_POINT_LABELS.get(key, key),
                FOUR_POINT_COLORS.get(key),
            )
        )
    layout = _layout(f"dT/dt vs Temperature ({phase.title()})", "Temperature (°C)", "dT/dt (°C/s)")
    return {"traces": traces, "layout": layout}


def _mass_and_cp(sim):
    """(mass, cp_func) from geometry + material, mirroring simulation_runner."""
    from app.services import create_geometry
    from app.services.property_evaluator import evaluate_scalar

    geometry = create_geometry(sim.geometry_type, sim.geometry_dict)
    grade = sim.steel_grade

    rho_prop = grade.get_property("density") if grade else None
    density = evaluate_scalar(rho_prop, 7850.0, temperature=20.0)
    mass = geometry.volume * density

    cp_prop = grade.get_property("specific_heat") if grade else None

    def cp_func(temp):
        return evaluate_scalar(cp_prop, 500.0, temperature=temp)

    return mass, cp_func


def absorbed_power(sim, phase):
    """Absorbed power (m·Cp·dT/dt) vs time for heating/tempering phases."""
    times, series = _phase_position_series(sim, phase)
    if not times or len(times) < 3:
        return None
    temps = series.get("center")
    if not temps:
        return None
    try:
        mass, cp_func = _mass_and_cp(sim)
    except Exception:
        return None
    times_arr = np.array(times, dtype=float)
    temps_arr = np.array(temps, dtype=float)
    dt = np.diff(times_arr)
    dt[dt == 0] = 1e-6
    dTdt = np.diff(temps_arr) / dt
    temp_mid = 0.5 * (temps_arr[:-1] + temps_arr[1:])
    cp_values = np.array([cp_func(t) for t in temp_mid])
    power = mass * cp_values * dTdt
    mid = 0.5 * (times_arr[:-1] + times_arr[1:])
    total_energy_kj = float(np.trapz(np.clip(power, 0, None), mid)) / 1000.0

    traces = [_line_trace(mid.tolist(), power.tolist(), "Absorbed power (center)", "#1a5c5c")]
    layout = _layout(f"Absorbed Power ({phase.title()})", "Time (s)", "Power (W)")
    layout["annotations"] = [
        {
            "x": 0.02,
            "y": 0.95,
            "xref": "paper",
            "yref": "paper",
            "text": f"Absorbed energy ≈ {total_energy_kj:.1f} kJ",
            "showarrow": False,
            "xanchor": "left",
        }
    ]
    return {"traces": traces, "layout": layout}


def _measured_channels_for_step(sim, step):
    measured_list = [m for m in sim.measured_data.all() if m.process_step == step]
    channels = []
    for m in measured_list:
        for channel in m.available_channels:
            channels.append(
                {
                    "name": m.get_channel_label(channel),
                    "times": m.get_channel_times(channel),
                    "temps": m.channels[channel],
                }
            )
    return channels


def measured_tc(sim, step):
    """Measured thermocouple temperatures vs time for a process step."""
    channels = _measured_channels_for_step(sim, step)
    if not channels:
        return None
    traces = [
        _line_trace(
            c["times"], c["temps"], c["name"], MEASURED_COLORS[i % len(MEASURED_COLORS)], width=1.5
        )
        for i, c in enumerate(channels)
    ]
    layout = _layout(f"Measured T vs Time ({step.title()})", "Time (s)", "Temperature (°C)")
    return {"traces": traces, "layout": layout}


def _measured_dtdt_series(channels, smooth_window=20):
    """[(mid_times, dTdt, temp_mid, name)] mirroring the matplotlib smoothing."""
    series = []
    for c in channels:
        times = np.array(c["times"], dtype=float)
        temps = np.array(c["temps"], dtype=float)
        if times.size < 3:
            continue
        dt = np.diff(times)
        dt[dt == 0] = 1e-6
        dTdt = np.diff(temps) / dt
        if smooth_window > 1:
            dTdt = moving_average(dTdt, smooth_window)
        mid = 0.5 * (times[:-1] + times[1:])
        temp_mid = 0.5 * (temps[:-1] + temps[1:])
        series.append((mid, dTdt, temp_mid, c["name"]))
    return series


def measured_dtdt(sim, step):
    """Measured dT/dt vs time (smoothed) for a process step."""
    channels = _measured_channels_for_step(sim, step)
    series = _measured_dtdt_series(channels)
    if not series:
        return None
    traces = [
        _line_trace(
            mid.tolist(), dTdt.tolist(), name, MEASURED_COLORS[i % len(MEASURED_COLORS)], width=1.5
        )
        for i, (mid, dTdt, _temp_mid, name) in enumerate(series)
    ]
    layout = _layout(
        f"Measured dT/dt vs Time ({step.title()}, smoothed)", "Time (s)", "dT/dt (°C/s)"
    )
    return {"traces": traces, "layout": layout}


def measured_dtdt_temp(sim, step):
    """Measured dT/dt vs temperature (smoothed) for a process step."""
    channels = _measured_channels_for_step(sim, step)
    series = _measured_dtdt_series(channels)
    if not series:
        return None
    traces = [
        _line_trace(
            temp_mid.tolist(),
            dTdt.tolist(),
            name,
            MEASURED_COLORS[i % len(MEASURED_COLORS)],
            width=1.5,
        )
        for i, (_mid, dTdt, temp_mid, name) in enumerate(series)
    ]
    layout = _layout(
        f"Measured dT/dt vs Temperature ({step.title()}, smoothed)",
        "Temperature (°C)",
        "dT/dt (°C/s)",
    )
    return {"traces": traces, "layout": layout}


def measured_power(sim, step):
    """Measured absorbed power vs time (m·Cp·dT/dt from TC data)."""
    channels = _measured_channels_for_step(sim, step)
    series = _measured_dtdt_series(channels)
    if not series:
        return None
    try:
        mass, cp_func = _mass_and_cp(sim)
    except Exception:
        return None
    traces = []
    for i, (mid, dTdt, temp_mid, name) in enumerate(series):
        cp_values = np.array([cp_func(t) for t in temp_mid])
        power = mass * cp_values * dTdt
        traces.append(
            _line_trace(
                mid.tolist(),
                power.tolist(),
                name,
                MEASURED_COLORS[i % len(MEASURED_COLORS)],
                width=1.5,
            )
        )
    layout = _layout(f"Measured Absorbed Power ({step.title()})", "Time (s)", "Power (W)")
    return {"traces": traces, "layout": layout}


def comparison_channel(sim, channel, offset=0.0):
    """Simulation center temperature vs one measured channel (time-offset)."""
    cycle = _full_cycle_result(sim)
    if not cycle:
        return None
    md_match = None
    for md in sim.measured_data.all():
        if channel in md.available_channels:
            md_match = md
            break
    if not md_match:
        return None

    sim_times = cycle.time_array
    sim_temps = cycle.data_dict.get("center") or cycle.value_array
    meas_times = [t + offset for t in md_match.get_channel_times(channel)]
    meas_temps = md_match.get_channel_data(channel)

    traces = [
        _line_trace(
            sim_times, sim_temps, "Simulation (center)", FOUR_POINT_COLORS["center"], dash="dash"
        ),
        _line_trace(
            meas_times, meas_temps, f"{md_match.name} - {channel}", MEASURED_COLORS[0], width=1.5
        ),
    ]
    layout = _layout(
        f"Simulation vs {channel} (offset={offset:.0f}s)", "Time (s)", "Temperature (°C)"
    )
    return {"traces": traces, "layout": layout}
