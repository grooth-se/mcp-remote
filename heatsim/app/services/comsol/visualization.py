"""Visualization generation for weld simulation results.

Creates plots, animations, and 3D visualizations from simulation data.
"""
import logging
from io import BytesIO
from pathlib import Path
from typing import Optional, List, Dict, Any, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.models.weld_project import WeldProject, WeldString, WeldResult

logger = logging.getLogger(__name__)


class WeldVisualization:
    """Generate visualizations from weld simulation results.

    Creates:
    - Thermal cycle plots (T vs t)
    - Temperature profile plots (T vs position)
    - CCT overlay plots (dT/dt vs T)
    - 3D temperature field snapshots
    - Time-lapse animations
    """

    def __init__(self):
        """Initialize visualization generator."""
        self._has_matplotlib = False
        self._has_pyvista = False
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        """Check for optional visualization dependencies."""
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            self._has_matplotlib = True
        except ImportError:
            logger.warning("matplotlib not available - plotting disabled")

        try:
            import pyvista
            self._has_pyvista = True
        except ImportError:
            logger.warning("pyvista not available - 3D visualization disabled")

    def create_thermal_cycle_plot(self, results: List['WeldResult'],
                                   title: str = "Thermal Cycles",
                                   figsize: tuple = (10, 6)) -> Optional[bytes]:
        """Create T vs t plot for thermal cycle results.

        Parameters
        ----------
        results : list of WeldResult
            Results with time_data and temperature_data
        title : str
            Plot title
        figsize : tuple
            Figure size in inches

        Returns
        -------
        bytes or None
            PNG image data, or None if plotting unavailable
        """
        if not self._has_matplotlib:
            return None

        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=figsize)

        for result in results:
            times = result.time_array
            temps = result.temperature_array

            if times and temps:
                label = result.location or f'String {result.string_id}'
                ax.plot(times, temps, label=label, linewidth=1.5)

        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Temperature (°C)', fontsize=12)
        ax.set_title(title, fontsize=14)
        ax.legend(loc='upper right', fontsize=10)
        ax.grid(True, alpha=0.3)

        # Add reference lines for critical temperatures
        ax.axhline(y=800, color='r', linestyle='--', alpha=0.5, label='800°C')
        ax.axhline(y=500, color='b', linestyle='--', alpha=0.5, label='500°C')

        # Save to bytes
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)

        return buf.read()

    def create_temperature_position_plot(self, line_data: Dict[float, Dict[str, np.ndarray]],
                                          title: str = "Temperature Profile",
                                          figsize: tuple = (10, 6)) -> Optional[bytes]:
        """Create T vs position plot at multiple times.

        Parameters
        ----------
        line_data : dict
            Dictionary mapping time to {position, temperature} arrays
        title : str
            Plot title
        figsize : tuple
            Figure size

        Returns
        -------
        bytes or None
            PNG image data
        """
        if not self._has_matplotlib:
            return None

        import matplotlib.pyplot as plt
        from matplotlib.cm import get_cmap

        fig, ax = plt.subplots(figsize=figsize)

        times = sorted(line_data.keys())
        cmap = get_cmap('plasma')
        colors = cmap(np.linspace(0, 1, len(times)))

        for i, t in enumerate(times):
            data = line_data[t]
            positions = data.get('position', [])
            temps = data.get('temperature', [])

            if len(positions) > 0 and len(temps) > 0:
                ax.plot(positions, temps, color=colors[i], label=f't = {t:.1f}s', linewidth=1.5)

        ax.set_xlabel('Position (mm)', fontsize=12)
        ax.set_ylabel('Temperature (°C)', fontsize=12)
        ax.set_title(title, fontsize=14)
        ax.legend(loc='upper right', fontsize=10)
        ax.grid(True, alpha=0.3)

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)

        return buf.read()

    def create_cct_overlay_plot(self, results: List['WeldResult'],
                                 cct_data: Optional[Dict] = None,
                                 title: str = "Cooling Rate vs Temperature",
                                 figsize: tuple = (10, 6)) -> Optional[bytes]:
        """Create dT/dt vs T plot with optional CCT diagram overlay.

        Parameters
        ----------
        results : list of WeldResult
            Cooling rate results with temperature (x) and rate (y) data
        cct_data : dict, optional
            CCT diagram data for overlay
        title : str
            Plot title
        figsize : tuple
            Figure size

        Returns
        -------
        bytes or None
            PNG image data
        """
        if not self._has_matplotlib:
            return None

        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=figsize)

        for result in results:
            # For cooling rate results, time_data holds T, temperature_data holds dT/dt
            temps = result.time_array  # Temperature on x-axis
            rates = result.temperature_array  # Cooling rate on y-axis

            if temps and rates:
                label = result.location or f'String {result.string_id}'
                ax.plot(temps, rates, label=label, linewidth=1.5)

        # Add CCT diagram overlay if available
        if cct_data:
            self._add_cct_overlay(ax, cct_data)

        ax.set_xlabel('Temperature (°C)', fontsize=12)
        ax.set_ylabel('Cooling Rate (°C/s)', fontsize=12)
        ax.set_title(title, fontsize=14)
        ax.legend(loc='upper right', fontsize=10)
        ax.grid(True, alpha=0.3)

        # Invert x-axis (high temp on left, like CCT diagrams)
        ax.invert_xaxis()

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)

        return buf.read()

    def _add_cct_overlay(self, ax: Any, cct_data: Dict) -> None:
        """Add CCT diagram boundaries to plot.

        Parameters
        ----------
        ax : Axes
            Matplotlib axes
        cct_data : dict
            CCT diagram data with phase boundaries
        """
        # Add typical phase boundary regions
        # This would use actual CCT data from the steel grade

        # Example: Add Ms temperature line
        ms_temp = cct_data.get('Ms', 350)
        ax.axvline(x=ms_temp, color='purple', linestyle=':', alpha=0.5, label=f'Ms = {ms_temp}°C')

        # Add Bs temperature line
        bs_temp = cct_data.get('Bs', 550)
        ax.axvline(x=bs_temp, color='green', linestyle=':', alpha=0.5, label=f'Bs = {bs_temp}°C')

    def create_phase_fraction_plot(self, results: List['WeldResult'],
                                    title: str = "Phase Fractions",
                                    figsize: tuple = (10, 6)) -> Optional[bytes]:
        """Create bar chart of phase fractions for each string.

        Parameters
        ----------
        results : list of WeldResult
            Results with phase_fractions data
        title : str
            Plot title
        figsize : tuple
            Figure size

        Returns
        -------
        bytes or None
            PNG image data
        """
        if not self._has_matplotlib:
            return None

        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=figsize)

        # Collect phase data
        string_labels = []
        phase_data = {'martensite': [], 'bainite': [], 'ferrite': [], 'pearlite': []}

        for result in results:
            phases = result.phases_dict
            if phases:
                string_labels.append(result.location or f'String {result.string_id}')
                for phase in phase_data.keys():
                    phase_data[phase].append(phases.get(phase, 0))

        if not string_labels:
            return None

        # Create stacked bar chart
        x = np.arange(len(string_labels))
        width = 0.6

        colors = {
            'martensite': '#e74c3c',
            'bainite': '#3498db',
            'ferrite': '#2ecc71',
            'pearlite': '#9b59b6',
        }

        bottom = np.zeros(len(string_labels))
        for phase, values in phase_data.items():
            values_array = np.array(values)
            ax.bar(x, values_array, width, bottom=bottom, label=phase.title(), color=colors[phase])
            bottom += values_array

        ax.set_xlabel('Location', fontsize=12)
        ax.set_ylabel('Phase Fraction', fontsize=12)
        ax.set_title(title, fontsize=14)
        ax.set_xticks(x)
        ax.set_xticklabels(string_labels, rotation=45, ha='right')
        ax.legend(loc='upper right', fontsize=10)
        ax.set_ylim(0, 1.1)

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)

        return buf.read()

    def create_3d_snapshot(self, vtk_data: bytes, view_angle: tuple = (30, 45),
                           colormap: str = 'coolwarm',
                           clim: tuple = None) -> Optional[bytes]:
        """Render 3D temperature field snapshot as PNG.

        Parameters
        ----------
        vtk_data : bytes
            VTK file content
        view_angle : tuple
            (elevation, azimuth) viewing angle
        colormap : str
            Colormap name
        clim : tuple, optional
            (vmin, vmax) color limits

        Returns
        -------
        bytes or None
            PNG image data
        """
        if not self._has_pyvista:
            return None

        # VTK Cocoa renderer crashes on macOS in non-main thread
        import sys, threading
        if sys.platform == 'darwin' and threading.current_thread() is not threading.main_thread():
            return None

        import pyvista as pv
        import tempfile

        try:
            # Write VTK data to temp file
            with tempfile.NamedTemporaryFile(suffix='.vtk', delete=False) as f:
                f.write(vtk_data)
                temp_path = f.name

            # Load and render
            mesh = pv.read(temp_path)

            plotter = pv.Plotter(off_screen=True)
            plotter.add_mesh(mesh, scalars='Temperature', cmap=colormap, clim=clim,
                           scalar_bar_args={'title': 'Temperature (°C)'})
            plotter.view_isometric()
            plotter.camera.elevation = view_angle[0]
            plotter.camera.azimuth = view_angle[1]

            # Render to image
            img = plotter.screenshot(return_img=True)
            plotter.close()

            # Convert to PNG bytes
            from PIL import Image
            pil_img = Image.fromarray(img)
            buf = BytesIO()
            pil_img.save(buf, format='PNG')
            buf.seek(0)

            return buf.read()

        except Exception as e:
            logger.error(f"3D rendering failed: {e}")
            return None
        finally:
            try:
                Path(temp_path).unlink()
            except Exception:
                pass

    def create_timelapse_animation(self, vtk_files: List[bytes],
                                    times: List[float],
                                    fps: int = 10,
                                    colormap: str = 'coolwarm',
                                    clim: tuple = None) -> Optional[bytes]:
        """Generate MP4 animation from VTK file sequence.

        Parameters
        ----------
        vtk_files : list of bytes
            VTK file contents in time order
        times : list of float
            Time values for each frame
        fps : int
            Frames per second
        colormap : str
            Colormap name
        clim : tuple, optional
            (vmin, vmax) color limits

        Returns
        -------
        bytes or None
            MP4 video data
        """
        if not self._has_pyvista:
            logger.warning("PyVista not available for animation generation")
            return self._create_fallback_animation(times, fps)

        # VTK Cocoa renderer crashes on macOS in non-main thread
        import sys, threading
        if sys.platform == 'darwin' and threading.current_thread() is not threading.main_thread():
            logger.info("Skipping animation on macOS worker thread")
            return self._create_fallback_animation(times, fps)

        import pyvista as pv
        import tempfile

        try:
            temp_dir = Path(tempfile.mkdtemp())
            frame_paths = []

            # Render each frame
            for i, (vtk_data, t) in enumerate(zip(vtk_files, times)):
                # Write VTK to temp file
                vtk_path = temp_dir / f"frame_{i:04d}.vtk"
                vtk_path.write_bytes(vtk_data)

                # Load mesh
                mesh = pv.read(str(vtk_path))

                # Render
                plotter = pv.Plotter(off_screen=True)
                plotter.add_mesh(mesh, scalars='Temperature', cmap=colormap, clim=clim)
                plotter.add_text(f't = {t:.1f}s', position='upper_left', font_size=12)
                plotter.view_isometric()

                # Save frame
                frame_path = temp_dir / f"frame_{i:04d}.png"
                plotter.screenshot(str(frame_path))
                plotter.close()
                frame_paths.append(frame_path)

            # Combine frames into video
            try:
                import imageio
                output_path = temp_dir / "animation.mp4"

                writer = imageio.get_writer(str(output_path), fps=fps, codec='libx264')
                for frame_path in frame_paths:
                    frame = imageio.imread(str(frame_path))
                    writer.append_data(frame)
                writer.close()

                return output_path.read_bytes()

            except ImportError:
                logger.warning("imageio not available for video encoding")
                return None

        except Exception as e:
            logger.error(f"Animation generation failed: {e}")
            return None
        finally:
            # Cleanup temp files
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    def _create_fallback_animation(self, times: List[float], fps: int) -> Optional[bytes]:
        """Create simple placeholder animation without PyVista.

        Parameters
        ----------
        times : list of float
            Time values
        fps : int
            Frames per second

        Returns
        -------
        bytes or None
            MP4 video data
        """
        if not self._has_matplotlib:
            return None

        import matplotlib.pyplot as plt
        import matplotlib.animation as animation
        import tempfile

        try:
            fig, ax = plt.subplots(figsize=(8, 6))

            def update(frame):
                ax.clear()
                t = times[frame] if frame < len(times) else times[-1]
                ax.text(0.5, 0.5, f'Time: {t:.1f}s\n(VTK visualization not available)',
                       ha='center', va='center', fontsize=16, transform=ax.transAxes)
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.axis('off')
                return []

            anim = animation.FuncAnimation(fig, update, frames=len(times), interval=1000/fps)

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
                temp_path = f.name

            anim.save(temp_path, writer='ffmpeg', fps=fps)
            plt.close(fig)

            result = Path(temp_path).read_bytes()
            Path(temp_path).unlink()
            return result

        except Exception as e:
            logger.error(f"Fallback animation failed: {e}")
            return None

    def create_summary_table_image(self, project: 'WeldProject',
                                    results: List['WeldResult']) -> Optional[bytes]:
        """Create summary statistics table as image.

        Parameters
        ----------
        project : WeldProject
            Weld project
        results : list of WeldResult
            All results for the project

        Returns
        -------
        bytes or None
            PNG image data
        """
        if not self._has_matplotlib:
            return None

        import matplotlib.pyplot as plt

        # Collect summary data
        rows = []
        for string in project.strings.order_by('string_number').all():
            string_results = [r for r in results if r.string_id == string.id]

            # Get thermal cycle result
            thermal = next((r for r in string_results if r.result_type == 'thermal_cycle'), None)

            if thermal:
                phases = thermal.phases_dict
                dominant_phase = max(phases.items(), key=lambda x: x[1])[0] if phases else 'N/A'

                rows.append([
                    string.string_number,
                    string.display_name,
                    f"{thermal.peak_temperature:.0f}" if thermal.peak_temperature else 'N/A',
                    f"{thermal.t_800_500:.1f}" if thermal.t_800_500 else 'N/A',
                    f"{thermal.cooling_rate_max:.0f}" if thermal.cooling_rate_max else 'N/A',
                    dominant_phase.title(),
                ])

        if not rows:
            return None

        # Create table
        fig, ax = plt.subplots(figsize=(12, max(3, len(rows) * 0.5)))
        ax.axis('off')

        columns = ['#', 'String', 'Peak T (°C)', 't8/5 (s)', 'Max dT/dt (°C/s)', 'Dominant Phase']
        table = ax.table(
            cellText=rows,
            colLabels=columns,
            cellLoc='center',
            loc='center',
            colColours=['#3498db'] * len(columns),
        )
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)

        # Style header
        for (i, j), cell in table.get_celld().items():
            if i == 0:
                cell.set_text_props(color='white', fontweight='bold')

        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)

        return buf.read()
