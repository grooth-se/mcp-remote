"""3D temperature visualization for heat treatment simulations.

Creates 3D visualizations and animations of temperature distribution
through the cross-section using PyVista.
"""
import io
import tempfile
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict
import numpy as np

logger = logging.getLogger(__name__)


def _check_pyvista():
    """Check if PyVista is available."""
    try:
        import pyvista
        return True
    except ImportError:
        return False


def create_cylinder_mesh(radius: float, length: float, n_radial: int = 50, n_axial: int = 20):
    """Create a cylindrical mesh for visualization.

    Parameters
    ----------
    radius : float
        Cylinder radius in meters
    length : float
        Cylinder length in meters
    n_radial : int
        Number of radial divisions
    n_axial : int
        Number of axial divisions

    Returns
    -------
    pyvista.StructuredGrid
        Cylindrical mesh
    """
    import pyvista as pv

    # Create cylindrical coordinates
    r = np.linspace(0, radius, n_radial)
    theta = np.linspace(0, 2 * np.pi, 60)
    z = np.linspace(0, length, n_axial)

    # Create mesh points
    R, THETA, Z = np.meshgrid(r, theta, z, indexing='ij')
    X = R * np.cos(THETA)
    Y = R * np.sin(THETA)

    # Reshape for structured grid
    points = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])

    # Create structured grid
    grid = pv.StructuredGrid()
    grid.points = points
    grid.dimensions = [n_radial, len(theta), n_axial]

    return grid


def create_hollow_cylinder_mesh(outer_radius: float, inner_radius: float, length: float,
                                  n_radial: int = 30, n_axial: int = 20):
    """Create a hollow cylindrical mesh for visualization.

    Parameters
    ----------
    outer_radius : float
        Outer radius in meters
    inner_radius : float
        Inner radius in meters
    length : float
        Length in meters
    n_radial : int
        Number of radial divisions
    n_axial : int
        Number of axial divisions

    Returns
    -------
    pyvista.StructuredGrid
        Hollow cylindrical mesh
    """
    import pyvista as pv

    # Create cylindrical coordinates (wall thickness only)
    r = np.linspace(inner_radius, outer_radius, n_radial)
    theta = np.linspace(0, 2 * np.pi, 60)
    z = np.linspace(0, length, n_axial)

    R, THETA, Z = np.meshgrid(r, theta, z, indexing='ij')
    X = R * np.cos(THETA)
    Y = R * np.sin(THETA)

    points = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])

    grid = pv.StructuredGrid()
    grid.points = points
    grid.dimensions = [n_radial, len(theta), n_axial]

    return grid


def create_plate_mesh(thickness: float, width: float, length: float, n_thickness: int = 30):
    """Create a plate mesh for visualization.

    Parameters
    ----------
    thickness : float
        Plate thickness in meters
    width : float
        Plate width in meters
    length : float
        Plate length in meters
    n_thickness : int
        Number of divisions through thickness

    Returns
    -------
    pyvista.StructuredGrid
        Plate mesh
    """
    import pyvista as pv

    # Create cartesian grid
    x = np.linspace(-width/2, width/2, 20)
    y = np.linspace(0, thickness, n_thickness)  # Through-thickness direction
    z = np.linspace(0, length, 20)

    X, Y, Z = np.meshgrid(x, y, z, indexing='ij')
    points = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])

    grid = pv.StructuredGrid()
    grid.points = points
    grid.dimensions = [len(x), n_thickness, len(z)]

    return grid


def interpolate_temperature_to_mesh(mesh, temperatures: np.ndarray, radial_positions: np.ndarray,
                                     geometry_type: str, geometry_params: dict):
    """Map temperature data to mesh points.

    Parameters
    ----------
    mesh : pyvista.StructuredGrid
        The mesh to add temperature data to
    temperatures : np.ndarray
        Temperature values at radial positions [n_positions]
    radial_positions : np.ndarray
        Normalized radial positions (0=center, 1=surface) [n_positions]
    geometry_type : str
        'cylinder', 'hollow_cylinder', or 'plate'
    geometry_params : dict
        Geometry parameters (radius, thickness, etc.)

    Returns
    -------
    pyvista.StructuredGrid
        Mesh with Temperature scalar field
    """
    from scipy.interpolate import interp1d

    # Create interpolation function
    interp = interp1d(radial_positions, temperatures, kind='linear',
                      fill_value='extrapolate')

    # Calculate normalized radial position for each mesh point
    points = mesh.points

    if geometry_type == 'cylinder':
        radius = geometry_params['radius']
        # Distance from center axis
        r = np.sqrt(points[:, 0]**2 + points[:, 1]**2)
        r_norm = r / radius

    elif geometry_type == 'hollow_cylinder':
        outer_radius = geometry_params['outer_radius']
        inner_radius = geometry_params['inner_radius']
        # Distance from center axis
        r = np.sqrt(points[:, 0]**2 + points[:, 1]**2)
        # Normalize: 0 at inner, 1 at outer
        r_norm = (r - inner_radius) / (outer_radius - inner_radius)

    elif geometry_type == 'plate':
        thickness = geometry_params['thickness']
        # Y coordinate is through-thickness
        # Normalize: 0 at center (y=thickness/2), 1 at surface
        r_norm = np.abs(points[:, 1] - thickness/2) / (thickness/2)

    else:
        # Default: use distance from origin
        r_norm = np.linalg.norm(points, axis=1)
        r_norm = r_norm / r_norm.max()

    # Clamp to valid range
    r_norm = np.clip(r_norm, 0, 1)

    # Interpolate temperature
    temps = interp(r_norm)
    mesh['Temperature'] = temps

    return mesh


def create_temperature_snapshot(
    geometry_type: str,
    geometry_params: dict,
    temperatures: np.ndarray,
    radial_positions: np.ndarray = None,
    colormap: str = 'coolwarm',
    clim: Tuple[float, float] = None,
    view_angle: Tuple[float, float] = (30, 45),
    show_colorbar: bool = True,
    title: str = None,
    resolution: Tuple[int, int] = (800, 600)
) -> Optional[bytes]:
    """Create a 3D temperature snapshot as PNG.

    Parameters
    ----------
    geometry_type : str
        'cylinder', 'hollow_cylinder', or 'plate'
    geometry_params : dict
        Geometry parameters
    temperatures : np.ndarray
        Temperature values at different radial positions
    radial_positions : np.ndarray
        Normalized radial positions (0=center, 1=surface)
    colormap : str
        Matplotlib colormap name
    clim : tuple
        (min, max) temperature limits for colorbar
    view_angle : tuple
        (elevation, azimuth) camera angles
    show_colorbar : bool
        Whether to show colorbar
    title : str
        Plot title
    resolution : tuple
        Image resolution (width, height)

    Returns
    -------
    bytes or None
        PNG image data
    """
    if not _check_pyvista():
        logger.warning("PyVista not available, using matplotlib fallback")
        return _create_fallback_snapshot(
            geometry_type, geometry_params, temperatures,
            radial_positions, colormap, clim, title
        )

    import pyvista as pv

    try:
        # Create mesh based on geometry type
        if geometry_type == 'cylinder':
            radius = geometry_params.get('radius', 0.05)
            length = geometry_params.get('length', 0.1)
            mesh = create_cylinder_mesh(radius, length)

        elif geometry_type == 'hollow_cylinder':
            outer_radius = geometry_params.get('outer_radius',
                           geometry_params.get('outer_diameter', 0.1) / 2)
            inner_radius = geometry_params.get('inner_radius',
                           geometry_params.get('inner_diameter', 0.05) / 2)
            length = geometry_params.get('length', 0.1)
            mesh = create_hollow_cylinder_mesh(outer_radius, inner_radius, length)

        elif geometry_type == 'plate':
            thickness = geometry_params.get('thickness', 0.02)
            width = geometry_params.get('width', 0.1)
            length = geometry_params.get('length', 0.1)
            mesh = create_plate_mesh(thickness, width, length)

        else:
            # Default to cylinder
            mesh = create_cylinder_mesh(0.05, 0.1)

        # Default radial positions if not provided
        if radial_positions is None:
            radial_positions = np.linspace(0, 1, len(temperatures))

        # Map temperatures to mesh
        mesh = interpolate_temperature_to_mesh(
            mesh, temperatures, radial_positions,
            geometry_type, geometry_params
        )

        # Set up plotter
        pv.global_theme.background = 'white'
        plotter = pv.Plotter(off_screen=True, window_size=resolution)

        # Add mesh with temperature coloring
        if clim is None:
            clim = (temperatures.min(), temperatures.max())

        scalar_bar_args = {
            'title': 'Temperature (°C)',
            'vertical': True,
            'position_x': 0.85,
            'position_y': 0.1,
            'width': 0.08,
            'height': 0.8,
        } if show_colorbar else None

        plotter.add_mesh(
            mesh,
            scalars='Temperature',
            cmap=colormap,
            clim=clim,
            show_scalar_bar=show_colorbar,
            scalar_bar_args=scalar_bar_args,
            smooth_shading=True
        )

        # Add title
        if title:
            plotter.add_text(title, position='upper_left', font_size=14)

        # Set camera
        plotter.view_isometric()
        plotter.camera.elevation = view_angle[0]
        plotter.camera.azimuth = view_angle[1]

        # Add axes
        plotter.add_axes()

        # Render to image
        img = plotter.screenshot(return_img=True)
        plotter.close()

        # Convert to PNG bytes
        from PIL import Image
        pil_img = Image.fromarray(img)
        buf = io.BytesIO()
        pil_img.save(buf, format='PNG')
        buf.seek(0)

        return buf.getvalue()

    except Exception as e:
        logger.error(f"3D snapshot creation failed: {e}")
        return None


def create_temperature_animation(
    geometry_type: str,
    geometry_params: dict,
    times: np.ndarray,
    temperature_history: np.ndarray,
    radial_positions: np.ndarray = None,
    colormap: str = 'coolwarm',
    clim: Tuple[float, float] = None,
    fps: int = 10,
    duration: float = None,
    max_frames: int = 100,
    resolution: Tuple[int, int] = (600, 450)
) -> Optional[bytes]:
    """Create animated GIF of temperature evolution.

    Parameters
    ----------
    geometry_type : str
        'cylinder', 'hollow_cylinder', or 'plate'
    geometry_params : dict
        Geometry parameters
    times : np.ndarray
        Time values [n_times]
    temperature_history : np.ndarray
        Temperature at each position and time [n_times, n_positions]
    radial_positions : np.ndarray
        Normalized radial positions (0=center, 1=surface)
    colormap : str
        Matplotlib colormap name
    clim : tuple
        (min, max) temperature limits
    fps : int
        Frames per second
    duration : float
        Target duration in seconds (will subsample frames if needed)
    max_frames : int
        Maximum number of frames
    resolution : tuple
        Frame resolution (width, height)

    Returns
    -------
    bytes or None
        GIF image data
    """
    if not _check_pyvista():
        logger.warning("PyVista not available for 3D animation")
        return _create_fallback_animation(times, temperature_history, fps)

    import pyvista as pv
    from PIL import Image

    try:
        # Subsample frames if needed
        n_times = len(times)
        if duration is not None:
            target_frames = int(duration * fps)
            max_frames = min(max_frames, target_frames)

        if n_times > max_frames:
            indices = np.linspace(0, n_times - 1, max_frames, dtype=int)
        else:
            indices = np.arange(n_times)

        # Determine color limits from all data
        if clim is None:
            clim = (temperature_history.min(), temperature_history.max())

        # Default radial positions
        if radial_positions is None:
            n_pos = temperature_history.shape[1]
            radial_positions = np.linspace(0, 1, n_pos)

        # Create base mesh
        if geometry_type == 'cylinder':
            radius = geometry_params.get('radius', 0.05)
            length = geometry_params.get('length', 0.1)
            mesh = create_cylinder_mesh(radius, length, n_radial=30, n_axial=10)
        elif geometry_type == 'hollow_cylinder':
            outer_radius = geometry_params.get('outer_radius',
                           geometry_params.get('outer_diameter', 0.1) / 2)
            inner_radius = geometry_params.get('inner_radius',
                           geometry_params.get('inner_diameter', 0.05) / 2)
            length = geometry_params.get('length', 0.1)
            mesh = create_hollow_cylinder_mesh(outer_radius, inner_radius, length,
                                                n_radial=20, n_axial=10)
        elif geometry_type == 'plate':
            thickness = geometry_params.get('thickness', 0.02)
            width = geometry_params.get('width', 0.1)
            length = geometry_params.get('length', 0.1)
            mesh = create_plate_mesh(thickness, width, length, n_thickness=20)
        else:
            mesh = create_cylinder_mesh(0.05, 0.1, n_radial=30, n_axial=10)

        # Generate frames
        frames = []
        pv.global_theme.background = 'white'

        for i, idx in enumerate(indices):
            t = times[idx]
            temps = temperature_history[idx]

            # Update mesh temperatures
            mesh_frame = mesh.copy()
            mesh_frame = interpolate_temperature_to_mesh(
                mesh_frame, temps, radial_positions,
                geometry_type, geometry_params
            )

            # Render frame
            plotter = pv.Plotter(off_screen=True, window_size=resolution)
            plotter.add_mesh(
                mesh_frame,
                scalars='Temperature',
                cmap=colormap,
                clim=clim,
                show_scalar_bar=True,
                scalar_bar_args={
                    'title': '°C',
                    'vertical': True,
                    'position_x': 0.85,
                    'width': 0.06,
                },
                smooth_shading=True
            )
            plotter.add_text(f't = {t:.1f}s', position='upper_left', font_size=12)
            plotter.view_isometric()
            plotter.camera.elevation = 25
            plotter.camera.azimuth = 45

            img = plotter.screenshot(return_img=True)
            plotter.close()

            frames.append(Image.fromarray(img))

        # Create GIF
        buf = io.BytesIO()
        frames[0].save(
            buf,
            format='GIF',
            save_all=True,
            append_images=frames[1:],
            duration=int(1000 / fps),
            loop=0
        )
        buf.seek(0)

        return buf.getvalue()

    except Exception as e:
        logger.error(f"3D animation creation failed: {e}")
        return _create_fallback_animation(times, temperature_history, fps)


def _create_fallback_animation(times: np.ndarray, temperature_history: np.ndarray,
                                fps: int = 10) -> Optional[bytes]:
    """Create 2D fallback animation when PyVista is unavailable.

    Creates a radial profile animation using matplotlib.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from PIL import Image

        n_times = len(times)
        n_pos = temperature_history.shape[1]
        r_norm = np.linspace(0, 1, n_pos)

        # Subsample if needed
        max_frames = 50
        if n_times > max_frames:
            indices = np.linspace(0, n_times - 1, max_frames, dtype=int)
        else:
            indices = np.arange(n_times)

        clim = (temperature_history.min(), temperature_history.max())
        frames = []

        for idx in indices:
            t = times[idx]
            temps = temperature_history[idx]

            fig, ax = plt.subplots(figsize=(8, 6))

            # Plot radial temperature profile
            ax.fill_between(r_norm, 0, temps, alpha=0.3, color='red')
            ax.plot(r_norm, temps, 'r-', linewidth=2)

            ax.set_xlabel('Normalized Position (0=Center, 1=Surface)', fontsize=12)
            ax.set_ylabel('Temperature (°C)', fontsize=12)
            ax.set_title(f'Temperature Profile at t = {t:.1f}s', fontsize=14)
            ax.set_xlim(0, 1)
            ax.set_ylim(clim[0] - 50, clim[1] + 50)
            ax.grid(True, alpha=0.3)

            # Add colorbar-like temperature indicator
            ax.axhline(y=temps.mean(), color='blue', linestyle='--', alpha=0.5,
                      label=f'Mean: {temps.mean():.0f}°C')
            ax.legend(loc='upper right')

            # Convert to image
            buf = io.BytesIO()
            fig.savefig(buf, format='PNG', dpi=100, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)

            frames.append(Image.open(buf))

        # Create GIF
        output = io.BytesIO()
        frames[0].save(
            output,
            format='GIF',
            save_all=True,
            append_images=frames[1:],
            duration=int(1000 / fps),
            loop=0
        )
        output.seek(0)

        return output.getvalue()

    except Exception as e:
        logger.error(f"Fallback animation failed: {e}")
        return None


def _create_fallback_snapshot(
    geometry_type: str,
    geometry_params: dict,
    temperatures: np.ndarray,
    radial_positions: np.ndarray = None,
    colormap: str = 'coolwarm',
    clim: Tuple[float, float] = None,
    title: str = None
) -> Optional[bytes]:
    """Create a 2D cross-section snapshot when PyVista is unavailable.

    Uses matplotlib to create a radial temperature profile or cross-section view.
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib.colors import Normalize
        from matplotlib.cm import ScalarMappable
        from matplotlib.patches import Circle, Wedge
        import matplotlib.patches as mpatches

        if radial_positions is None:
            radial_positions = np.linspace(0, 1, len(temperatures))

        if clim is None:
            clim = (temperatures.min() - 10, temperatures.max() + 10)

        cmap = plt.get_cmap(colormap)
        norm = Normalize(vmin=clim[0], vmax=clim[1])

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        # Left plot: Cross-section view
        if geometry_type in ['cylinder', 'hollow_cylinder']:
            if geometry_type == 'cylinder':
                radius = geometry_params.get('radius', 0.05) * 1000  # Convert to mm
                inner_radius = 0
            else:
                outer_radius = geometry_params.get('outer_radius',
                               geometry_params.get('outer_diameter', 0.1) / 2) * 1000
                inner_radius = geometry_params.get('inner_radius',
                               geometry_params.get('inner_diameter', 0.05) / 2) * 1000
                radius = outer_radius

            # Draw concentric rings with color
            n_rings = 20
            for i in range(n_rings):
                r_inner = inner_radius + (radius - inner_radius) * i / n_rings
                r_outer = inner_radius + (radius - inner_radius) * (i + 1) / n_rings
                r_norm = (r_inner + r_outer) / 2 / (radius - inner_radius) if (radius - inner_radius) > 0 else 0.5

                # Interpolate temperature
                temp = np.interp(r_norm, radial_positions, temperatures)
                color = cmap(norm(temp))

                ring = mpatches.Annulus((0, 0), r_outer, r_outer - r_inner,
                                        facecolor=color, edgecolor='none')
                ax1.add_patch(ring)

            ax1.set_xlim(-radius * 1.15, radius * 1.15)
            ax1.set_ylim(-radius * 1.15, radius * 1.15)
            ax1.set_aspect('equal')
            ax1.set_xlabel('Position (mm)', fontsize=11)
            ax1.set_ylabel('Position (mm)', fontsize=11)
            ax1.set_title('Cross-Section View', fontsize=12)

        else:  # plate
            thickness = geometry_params.get('thickness', 0.02) * 1000

            # Draw horizontal bands
            n_bands = 20
            for i in range(n_bands):
                y_low = i / n_bands * thickness
                y_high = (i + 1) / n_bands * thickness
                r_norm = abs((y_low + y_high) / 2 - thickness / 2) / (thickness / 2)
                temp = np.interp(r_norm, radial_positions, temperatures)
                color = cmap(norm(temp))
                ax1.axhspan(y_low, y_high, color=color, alpha=0.9)

            ax1.set_xlim(0, 100)
            ax1.set_ylim(0, thickness)
            ax1.set_xlabel('Width (mm)', fontsize=11)
            ax1.set_ylabel('Thickness (mm)', fontsize=11)
            ax1.set_title('Cross-Section View', fontsize=12)

        # Add colorbar to first plot
        sm = ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = plt.colorbar(sm, ax=ax1, shrink=0.8)
        cbar.set_label('Temperature (°C)', fontsize=10)

        # Right plot: Radial profile
        ax2.fill_between(radial_positions, temperatures, alpha=0.3, color='red')
        ax2.plot(radial_positions, temperatures, 'r-', linewidth=2, marker='o', markersize=8)

        ax2.set_xlabel('Normalized Position (0=Center, 1=Surface)', fontsize=11)
        ax2.set_ylabel('Temperature (°C)', fontsize=11)
        ax2.set_title('Radial Temperature Profile', fontsize=12)
        ax2.set_xlim(0, 1)
        ax2.set_ylim(clim[0], clim[1])
        ax2.grid(True, alpha=0.3)

        # Add temperature annotations
        for i, (r, t) in enumerate(zip(radial_positions, temperatures)):
            pos_label = ['Center', '1/3 R', '2/3 R', 'Surface'][i] if len(temperatures) == 4 else f'{r:.2f}'
            ax2.annotate(f'{t:.0f}°C', (r, t), textcoords='offset points',
                        xytext=(0, 10), ha='center', fontsize=9)

        if title:
            fig.suptitle(title, fontsize=14, fontweight='bold')

        plt.tight_layout()

        # Convert to PNG bytes
        buf = io.BytesIO()
        fig.savefig(buf, format='PNG', dpi=120, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)

        return buf.getvalue()

    except Exception as e:
        logger.error(f"Fallback snapshot failed: {e}")
        return None


def create_cross_section_animation(
    geometry_type: str,
    geometry_params: dict,
    times: np.ndarray,
    temperature_history: np.ndarray,
    radial_positions: np.ndarray = None,
    colormap: str = 'coolwarm',
    clim: Tuple[float, float] = None,
    fps: int = 10,
    max_frames: int = 60
) -> Optional[bytes]:
    """Create 2D cross-section animation (faster than full 3D).

    Parameters
    ----------
    geometry_type : str
        'cylinder', 'hollow_cylinder', or 'plate'
    geometry_params : dict
        Geometry parameters
    times : np.ndarray
        Time values
    temperature_history : np.ndarray
        Temperature at each position and time [n_times, n_positions]
    radial_positions : np.ndarray
        Normalized radial positions
    colormap : str
        Colormap name
    clim : tuple
        Color limits
    fps : int
        Frames per second
    max_frames : int
        Maximum frames

    Returns
    -------
    bytes or None
        GIF image data
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.cm import ScalarMappable
    from PIL import Image

    try:
        n_times = len(times)
        n_pos = temperature_history.shape[1]

        if radial_positions is None:
            radial_positions = np.linspace(0, 1, n_pos)

        # Subsample frames
        if n_times > max_frames:
            indices = np.linspace(0, n_times - 1, max_frames, dtype=int)
        else:
            indices = np.arange(n_times)

        if clim is None:
            clim = (temperature_history.min(), temperature_history.max())

        # Create colormap
        cmap = plt.get_cmap(colormap)
        norm = Normalize(vmin=clim[0], vmax=clim[1])

        frames = []

        for idx in indices:
            t = times[idx]
            temps = temperature_history[idx]

            fig, ax = plt.subplots(figsize=(8, 8))

            if geometry_type in ['cylinder', 'hollow_cylinder']:
                # Draw circular cross-section
                if geometry_type == 'cylinder':
                    radius = geometry_params.get('radius', 0.05) * 1000  # Convert to mm
                    inner_radius = 0
                else:
                    outer_radius = geometry_params.get('outer_radius',
                                   geometry_params.get('outer_diameter', 0.1) / 2) * 1000
                    inner_radius = geometry_params.get('inner_radius',
                                   geometry_params.get('inner_diameter', 0.05) / 2) * 1000
                    radius = outer_radius

                # Draw concentric rings
                theta = np.linspace(0, 2 * np.pi, 100)
                for i in range(n_pos):
                    r = radial_positions[i] * (radius - inner_radius) + inner_radius
                    color = cmap(norm(temps[i]))
                    circle = plt.Circle((0, 0), r, color=color, fill=False, linewidth=8)
                    ax.add_patch(circle)

                # Fill center
                if inner_radius == 0:
                    center = plt.Circle((0, 0), radial_positions[0] * radius * 0.5,
                                        color=cmap(norm(temps[0])), fill=True)
                    ax.add_patch(center)

                ax.set_xlim(-radius * 1.2, radius * 1.2)
                ax.set_ylim(-radius * 1.2, radius * 1.2)
                ax.set_aspect('equal')
                ax.set_xlabel('Position (mm)', fontsize=12)
                ax.set_ylabel('Position (mm)', fontsize=12)

            else:  # plate
                thickness = geometry_params.get('thickness', 0.02) * 1000

                # Draw horizontal bands
                for i in range(n_pos):
                    y = radial_positions[i] * thickness
                    color = cmap(norm(temps[i]))
                    ax.axhspan(y - thickness/(n_pos*2), y + thickness/(n_pos*2),
                              color=color, alpha=0.8)

                ax.set_xlim(0, 100)
                ax.set_ylim(0, thickness)
                ax.set_xlabel('Width (mm)', fontsize=12)
                ax.set_ylabel('Thickness (mm)', fontsize=12)

            ax.set_title(f'Cross-Section Temperature at t = {t:.1f}s', fontsize=14)

            # Add colorbar
            sm = ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax, label='Temperature (°C)')

            # Convert to image
            buf = io.BytesIO()
            fig.savefig(buf, format='PNG', dpi=100, bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            frames.append(Image.open(buf).copy())

        # Create GIF
        output = io.BytesIO()
        frames[0].save(
            output,
            format='GIF',
            save_all=True,
            append_images=frames[1:],
            duration=int(1000 / fps),
            loop=0
        )
        output.seek(0)

        return output.getvalue()

    except Exception as e:
        logger.error(f"Cross-section animation failed: {e}")
        return None
