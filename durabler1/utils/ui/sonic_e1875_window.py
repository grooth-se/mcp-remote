"""
Sonic Resonance (Ultrasonic) Test Application Window.

Provides GUI for entering specimen dimensions, mass, and ultrasonic
velocity measurements to calculate E, G, and Poisson's ratio per
modified ASTM E1875.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, Dict, Any, List
import numpy as np
from PIL import Image, ImageTk

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# Project root for logo path
PROJECT_ROOT = Path(__file__).parent.parent.parent


class SonicTestApp:
    """
    Main Tkinter application for Sonic/Ultrasonic test analysis.

    Parameters
    ----------
    parent_launcher : object, optional
        Reference to parent launcher window to return to on close
    """

    def __init__(self, parent_launcher: Optional[Any] = None):
        self.parent_launcher = parent_launcher

        self.root = tk.Toplevel() if parent_launcher else tk.Tk()
        self.root.title("Durabler - Sonic Resonance Test (Modified ASTM E1875)")
        self.root.geometry("1200x850")

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Data storage
        self.current_results = None

        # Create UI components
        self._create_menu()
        self._create_toolbar()
        self._create_main_panels()
        self._create_statusbar()

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

    def _on_close(self):
        """Handle window close - return to launcher if available."""
        self.root.destroy()
        if self.parent_launcher:
            self.parent_launcher.show()

    def _create_menu(self):
        """Create application menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Export Results...", command=self.export_results)
        file_menu.add_command(label="Export Report...", command=self.export_report)
        file_menu.add_separator()
        if self.parent_launcher:
            file_menu.add_command(label="Return to Launcher", command=self._on_close)
        file_menu.add_command(label="Exit", command=self._exit_app)

        # Analysis menu
        analysis_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Analysis", menu=analysis_menu)
        analysis_menu.add_command(label="Run Analysis", command=self.run_analysis,
                                  accelerator="F5")
        analysis_menu.add_command(label="Clear Results", command=self.clear_results)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

        # Keyboard shortcuts
        self.root.bind('<F5>', lambda e: self.run_analysis())

    def _exit_app(self):
        """Exit the entire application."""
        if self.parent_launcher:
            self.parent_launcher.root.quit()
        self.root.quit()

    def _create_toolbar(self):
        """Create main toolbar with buttons."""
        toolbar = ttk.Frame(self.root)
        toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # Load and display logo
        logo_path = PROJECT_ROOT / "durablersvart.png"
        if logo_path.exists():
            logo_img = Image.open(logo_path)
            max_height = 40
            ratio = max_height / logo_img.height
            new_size = (int(logo_img.width * ratio), max_height)
            logo_img = logo_img.resize(new_size, Image.Resampling.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(logo_img)
            ttk.Label(toolbar, image=self.logo_photo).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        if self.parent_launcher:
            ttk.Button(toolbar, text="<< Back", command=self._on_close).pack(
                side=tk.LEFT, padx=2)
            ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Analysis buttons
        ttk.Button(toolbar, text="Analyze", command=self.run_analysis).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Clear", command=self.clear_results).pack(
            side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(toolbar, text="Export Report", command=self.export_report).pack(
            side=tk.LEFT, padx=2)

    def _create_main_panels(self):
        """Create left and right panels."""
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # Left panel (inputs)
        self._create_left_panel(main_frame)

        # Right panel (results + plot)
        self._create_right_panel(main_frame)

    def _create_left_panel(self, parent):
        """Create left panel with specimen inputs."""
        left_frame = ttk.Frame(parent, width=480)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.grid_propagate(False)

        # Scrollable frame
        canvas = tk.Canvas(left_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Test Information frame
        info_frame = ttk.LabelFrame(scrollable_frame, text="Test Information", padding=10)
        info_frame.pack(fill=tk.X, pady=5, padx=5)

        row = 0
        info_fields = [
            ("Certificate number:", "certificate_number"),
            ("Test project:", "test_project"),
            ("Customer:", "customer"),
            ("Customer order:", "customer_order"),
            ("Product/S/N:", "product_sn"),
            ("Specimen ID:", "specimen_id"),
            ("Location/Orientation:", "location_orientation"),
            ("Material:", "material"),
            ("Temperature (°C):", "temperature"),
            ("Test Date:", "test_date"),
        ]

        self.info_vars: Dict[str, tk.StringVar] = {}
        for label_text, key in info_fields:
            ttk.Label(info_frame, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar()
            if key == "temperature":
                var.set("23")
            self.info_vars[key] = var

            # Special handling for certificate number - add Combobox with selection list
            if key == "certificate_number":
                cert_frame = ttk.Frame(info_frame)
                cert_frame.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self.cert_combobox = ttk.Combobox(cert_frame, textvariable=var, width=22)
                self.cert_combobox.pack(side=tk.LEFT)
                self.cert_combobox.bind('<<ComboboxSelected>>', self._on_certificate_selected)
                ttk.Button(cert_frame, text="↻", width=3,
                          command=self._refresh_certificate_list).pack(side=tk.LEFT, padx=2)
                # Load certificate list
                self._refresh_certificate_list()
            else:
                ttk.Entry(info_frame, textvariable=var, width=25).grid(
                    row=row, column=1, sticky=tk.EW, pady=2)
            row += 1

        info_frame.columnconfigure(1, weight=1)

        # Specimen Geometry frame
        specimen_frame = ttk.LabelFrame(scrollable_frame, text="Specimen Geometry", padding=10)
        specimen_frame.pack(fill=tk.X, pady=5, padx=5)

        # Specimen type
        ttk.Label(specimen_frame, text="Type:", font=('Helvetica', 9, 'bold')).grid(
            row=0, column=0, sticky=tk.W)
        self.specimen_type = tk.StringVar(value="round")
        ttk.Radiobutton(
            specimen_frame, text="Round",
            variable=self.specimen_type, value="round",
            command=self._update_dimension_fields
        ).grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(
            specimen_frame, text="Square",
            variable=self.specimen_type, value="square",
            command=self._update_dimension_fields
        ).grid(row=0, column=2, sticky=tk.W)

        # Dimension fields container
        self.dim_container = ttk.Frame(specimen_frame)
        self.dim_container.grid(row=1, column=0, columnspan=3, sticky=tk.EW, pady=5)

        self.dim_vars: Dict[str, tk.StringVar] = {}
        self._update_dimension_fields()

        # Mass
        ttk.Label(specimen_frame, text="Mass (g):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.mass_var = tk.StringVar()
        ttk.Entry(specimen_frame, textvariable=self.mass_var, width=12).grid(
            row=2, column=1, sticky=tk.W, pady=2)

        specimen_frame.columnconfigure(1, weight=1)

        # Calculated density display
        ttk.Label(specimen_frame, text="Density (kg/m³):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.density_var = tk.StringVar(value="-")
        ttk.Label(specimen_frame, textvariable=self.density_var, foreground='blue').grid(
            row=3, column=1, sticky=tk.W, pady=2)

        # Ultrasonic Measurements frame
        velocity_frame = ttk.LabelFrame(scrollable_frame, text="Ultrasonic Velocity Measurements", padding=10)
        velocity_frame.pack(fill=tk.X, pady=5, padx=5)

        # Longitudinal (compression) wave velocities - vertical layout
        ttk.Label(velocity_frame, text="Longitudinal Wave Velocity (m/s):",
                  font=('Helvetica', 9, 'bold')).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 5))

        self.vl_vars: List[tk.StringVar] = []
        for i in range(3):
            ttk.Label(velocity_frame, text=f"Vl{i+1}:").grid(row=i+1, column=0, sticky=tk.W, padx=2, pady=2)
            var = tk.StringVar()
            self.vl_vars.append(var)
            ttk.Entry(velocity_frame, textvariable=var, width=12).grid(
                row=i+1, column=1, sticky=tk.W, padx=2, pady=2)

        ttk.Label(velocity_frame, text="Average Vl:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.vl_avg_var = tk.StringVar(value="-")
        ttk.Label(velocity_frame, textvariable=self.vl_avg_var, foreground='blue').grid(
            row=4, column=1, sticky=tk.W, pady=2)

        # Shear wave velocities - vertical layout
        ttk.Label(velocity_frame, text="Shear Wave Velocity (m/s):",
                  font=('Helvetica', 9, 'bold')).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(10, 5))

        self.vs_vars: List[tk.StringVar] = []
        for i in range(3):
            ttk.Label(velocity_frame, text=f"Vs{i+1}:").grid(row=i+6, column=0, sticky=tk.W, padx=2, pady=2)
            var = tk.StringVar()
            self.vs_vars.append(var)
            ttk.Entry(velocity_frame, textvariable=var, width=12).grid(
                row=i+6, column=1, sticky=tk.W, padx=2, pady=2)

        ttk.Label(velocity_frame, text="Average Vs:").grid(row=9, column=0, sticky=tk.W, pady=2)
        self.vs_avg_var = tk.StringVar(value="-")
        ttk.Label(velocity_frame, textvariable=self.vs_avg_var, foreground='blue').grid(
            row=9, column=1, sticky=tk.W, pady=2)

        # Bind updates for live calculation
        for var in self.vl_vars + self.vs_vars:
            var.trace_add('write', self._update_averages)

        self.mass_var.trace_add('write', self._update_density)
        for key in self.dim_vars:
            self.dim_vars[key].trace_add('write', self._update_density)

    def _update_dimension_fields(self):
        """Update dimension fields based on specimen type."""
        for widget in self.dim_container.winfo_children():
            widget.destroy()

        self.dim_vars = {}

        if self.specimen_type.get() == "round":
            ttk.Label(self.dim_container, text="Diameter (mm):").grid(row=0, column=0, sticky=tk.W, pady=2)
            self.dim_vars['diameter'] = tk.StringVar()
            ttk.Entry(self.dim_container, textvariable=self.dim_vars['diameter'], width=12).grid(
                row=0, column=1, sticky=tk.W, pady=2)
        else:  # square
            ttk.Label(self.dim_container, text="Side length (mm):").grid(row=0, column=0, sticky=tk.W, pady=2)
            self.dim_vars['side_length'] = tk.StringVar()
            ttk.Entry(self.dim_container, textvariable=self.dim_vars['side_length'], width=12).grid(
                row=0, column=1, sticky=tk.W, pady=2)

        ttk.Label(self.dim_container, text="Length (mm):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.dim_vars['length'] = tk.StringVar()
        ttk.Entry(self.dim_container, textvariable=self.dim_vars['length'], width=12).grid(
            row=1, column=1, sticky=tk.W, pady=2)

        # Bind updates
        for key in self.dim_vars:
            self.dim_vars[key].trace_add('write', self._update_density)

    def _update_density(self, *args):
        """Update calculated density display."""
        try:
            mass = float(self.mass_var.get()) if self.mass_var.get() else 0
            length = float(self.dim_vars['length'].get()) if self.dim_vars['length'].get() else 0

            if self.specimen_type.get() == "round":
                diameter = float(self.dim_vars['diameter'].get()) if self.dim_vars['diameter'].get() else 0
                area = 3.14159 * (diameter / 2) ** 2  # mm²
            else:
                side = float(self.dim_vars['side_length'].get()) if self.dim_vars['side_length'].get() else 0
                area = side ** 2  # mm²

            volume_mm3 = area * length
            volume_m3 = volume_mm3 * 1e-9
            mass_kg = mass / 1000

            if volume_m3 > 0:
                density = mass_kg / volume_m3
                self.density_var.set(f"{density:.1f}")
            else:
                self.density_var.set("-")
        except (ValueError, KeyError):
            self.density_var.set("-")

    def _update_averages(self, *args):
        """Update average velocity displays."""
        # Longitudinal average
        try:
            vl_values = [float(var.get()) for var in self.vl_vars if var.get()]
            if vl_values:
                self.vl_avg_var.set(f"{sum(vl_values)/len(vl_values):.1f}")
            else:
                self.vl_avg_var.set("-")
        except ValueError:
            self.vl_avg_var.set("-")

        # Shear average
        try:
            vs_values = [float(var.get()) for var in self.vs_vars if var.get()]
            if vs_values:
                self.vs_avg_var.set(f"{sum(vs_values)/len(vs_values):.1f}")
            else:
                self.vs_avg_var.set("-")
        except ValueError:
            self.vs_avg_var.set("-")

    def _create_right_panel(self, parent):
        """Create right panel with results table and plot."""
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=2)  # Results table gets more space
        right_frame.rowconfigure(1, weight=1)  # Plot gets less space

        # Results table (top)
        results_frame = ttk.LabelFrame(right_frame, text="Results (Modified ASTM E1875)", padding=5)
        results_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        columns = ("parameter", "value", "uncertainty", "unit")
        self.results_tree = ttk.Treeview(
            results_frame, columns=columns, show="headings", height=12
        )

        self.results_tree.heading("parameter", text="Parameter")
        self.results_tree.heading("value", text="Value")
        self.results_tree.heading("uncertainty", text="U (k=2)")
        self.results_tree.heading("unit", text="Unit")

        self.results_tree.column("parameter", width=200)
        self.results_tree.column("value", width=100, anchor=tk.E)
        self.results_tree.column("uncertainty", width=100, anchor=tk.E)
        self.results_tree.column("unit", width=80, anchor=tk.CENTER)

        self.results_tree.pack(fill=tk.BOTH, expand=True)

        # Plot (bottom) - smaller size
        plot_frame = ttk.LabelFrame(right_frame, text="Velocity Measurements", padding=5)
        plot_frame.grid(row=1, column=0, sticky="nsew")

        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self._setup_empty_plot()

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()

    def _setup_empty_plot(self):
        """Set up empty plot."""
        self.ax.set_xlabel("Measurement Number")
        self.ax.set_ylabel("Velocity (m/s)")
        self.ax.set_title("Ultrasonic Velocity Measurements")
        self.ax.grid(True, linestyle='--', alpha=0.7)

    def _create_statusbar(self):
        """Create status bar at bottom."""
        self.statusbar = ttk.Label(
            self.root, text="Ready - Enter specimen data and velocity measurements",
            relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.grid(row=2, column=0, sticky="ew")

    def run_analysis(self):
        """Run sonic/ultrasonic analysis."""
        try:
            from utils.models.sonic_specimen import SonicSpecimen, UltrasonicMeasurements
            from utils.analysis.sonic_calculations import SonicAnalyzer

            self._update_status("Running analysis...")

            # Validate inputs
            if not self._validate_inputs():
                return

            # Build specimen
            spec_type = self.specimen_type.get()
            if spec_type == "round":
                diameter = float(self.dim_vars['diameter'].get())
                side_length = 0
            else:
                diameter = 0
                side_length = float(self.dim_vars['side_length'].get())

            specimen = SonicSpecimen(
                specimen_id=self.info_vars['specimen_id'].get(),
                specimen_type=spec_type,
                diameter=diameter,
                side_length=side_length,
                length=float(self.dim_vars['length'].get()),
                mass=float(self.mass_var.get()),
                material=self.info_vars['material'].get()
            )

            # Build measurements
            vl_values = [float(var.get()) for var in self.vl_vars if var.get()]
            vs_values = [float(var.get()) for var in self.vs_vars if var.get()]

            measurements = UltrasonicMeasurements(
                longitudinal_velocities=vl_values,
                shear_velocities=vs_values
            )

            # Run analysis
            analyzer = SonicAnalyzer()
            self.current_results = analyzer.run_analysis(specimen, measurements)

            # Store specimen and measurements for report
            self.current_specimen = specimen
            self.current_measurements = measurements

            # Display results
            self._display_results()

            # Plot velocities
            self._plot_velocities(vl_values, vs_values)

            self._update_status("Analysis complete")

        except ValueError as e:
            messagebox.showerror("Input Error", f"Invalid input value:\n{e}")
        except Exception as e:
            messagebox.showerror("Analysis Error", f"Analysis failed:\n{e}")
            import traceback
            traceback.print_exc()

    def _validate_inputs(self) -> bool:
        """Validate input fields."""
        errors = []

        # Check dimensions
        if self.specimen_type.get() == "round":
            if not self.dim_vars.get('diameter') or not self.dim_vars['diameter'].get():
                errors.append("Diameter is required")
        else:
            if not self.dim_vars.get('side_length') or not self.dim_vars['side_length'].get():
                errors.append("Side length is required")

        if not self.dim_vars.get('length') or not self.dim_vars['length'].get():
            errors.append("Length is required")

        if not self.mass_var.get():
            errors.append("Mass is required")

        # Check velocities (need at least one of each)
        vl_count = sum(1 for var in self.vl_vars if var.get())
        vs_count = sum(1 for var in self.vs_vars if var.get())

        if vl_count == 0:
            errors.append("At least one longitudinal velocity measurement is required")
        if vs_count == 0:
            errors.append("At least one shear velocity measurement is required")

        if errors:
            messagebox.showwarning("Validation Error", "\n".join(errors))
            return False

        return True

    def _display_results(self):
        """Update results treeview."""
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        if not self.current_results:
            return

        # Configure tags
        self.results_tree.tag_configure('section', background='#E0E0E0')
        self.results_tree.tag_configure('valid', foreground='green')
        self.results_tree.tag_configure('invalid', foreground='red')

        def add_section(title):
            self.results_tree.insert("", tk.END, values=(f"── {title} ──", "", "", ""),
                                    tags=('section',))

        # Specimen Properties
        add_section("Specimen Properties")
        self.results_tree.insert("", tk.END, values=(
            "Density",
            f"{self.current_results.density.value:.1f}",
            f"±{self.current_results.density.uncertainty:.1f}",
            self.current_results.density.unit
        ))

        # Velocity Measurements
        add_section("Velocity Measurements")
        self.results_tree.insert("", tk.END, values=(
            "Longitudinal Velocity (Vl)",
            f"{self.current_results.longitudinal_velocity.value:.1f}",
            f"±{self.current_results.longitudinal_velocity.uncertainty:.1f}",
            self.current_results.longitudinal_velocity.unit
        ))
        self.results_tree.insert("", tk.END, values=(
            "Shear Velocity (Vs)",
            f"{self.current_results.shear_velocity.value:.1f}",
            f"±{self.current_results.shear_velocity.uncertainty:.1f}",
            self.current_results.shear_velocity.unit
        ))

        # Elastic Properties
        add_section("Elastic Properties")
        self.results_tree.insert("", tk.END, values=(
            "Poisson's Ratio (ν)",
            f"{self.current_results.poissons_ratio.value:.4f}",
            f"±{self.current_results.poissons_ratio.uncertainty:.4f}",
            self.current_results.poissons_ratio.unit
        ))
        self.results_tree.insert("", tk.END, values=(
            "Shear Modulus (G)",
            f"{self.current_results.shear_modulus.value:.2f}",
            f"±{self.current_results.shear_modulus.uncertainty:.2f}",
            self.current_results.shear_modulus.unit
        ))
        self.results_tree.insert("", tk.END, values=(
            "Young's Modulus (E)",
            f"{self.current_results.youngs_modulus.value:.2f}",
            f"±{self.current_results.youngs_modulus.uncertainty:.2f}",
            self.current_results.youngs_modulus.unit
        ))

        # Resonant Frequencies (ASTM E1875)
        add_section("Resonant Frequencies (ASTM E1875)")
        self.results_tree.insert("", tk.END, values=(
            "Flexural Frequency (ff)",
            f"{self.current_results.flexural_frequency.value:.1f}",
            f"±{self.current_results.flexural_frequency.uncertainty:.1f}",
            self.current_results.flexural_frequency.unit
        ))
        self.results_tree.insert("", tk.END, values=(
            "Torsional Frequency (ft)",
            f"{self.current_results.torsional_frequency.value:.1f}",
            f"±{self.current_results.torsional_frequency.uncertainty:.1f}",
            self.current_results.torsional_frequency.unit
        ))

        # Validity
        add_section("Validity")
        is_valid = self.current_results.is_valid
        self.results_tree.insert("", tk.END, values=(
            "Test Validity",
            "VALID" if is_valid else "CHECK",
            "",
            ""
        ), tags=('valid' if is_valid else 'invalid',))

        self.results_tree.insert("", tk.END, values=(
            "Notes",
            self.current_results.validity_notes[:40] + "..." if len(self.current_results.validity_notes) > 40 else self.current_results.validity_notes,
            "",
            ""
        ))

    def _plot_velocities(self, vl_values: List[float], vs_values: List[float]):
        """Plot velocity measurements."""
        self.ax.clear()

        measurements = [1, 2, 3]

        # Pad values if less than 3
        while len(vl_values) < 3:
            vl_values.append(None)
        while len(vs_values) < 3:
            vs_values.append(None)

        # Filter out None values for plotting
        vl_x = [i+1 for i, v in enumerate(vl_values) if v is not None]
        vl_y = [v for v in vl_values if v is not None]
        vs_x = [i+1 for i, v in enumerate(vs_values) if v is not None]
        vs_y = [v for v in vs_values if v is not None]

        # Plot longitudinal velocities (dark red)
        if vl_y:
            self.ax.plot(vl_x, vl_y, 'o-', color='darkred', markersize=10, linewidth=2,
                        label=f'Longitudinal (Avg: {sum(vl_y)/len(vl_y):.0f} m/s)')
            self.ax.axhline(y=sum(vl_y)/len(vl_y), color='darkred', linestyle='--', alpha=0.5)

        # Plot shear velocities (black)
        if vs_y:
            self.ax.plot(vs_x, vs_y, 's-', color='black', markersize=10, linewidth=2,
                        label=f'Shear (Avg: {sum(vs_y)/len(vs_y):.0f} m/s)')
            self.ax.axhline(y=sum(vs_y)/len(vs_y), color='black', linestyle='--', alpha=0.5)

        self.ax.set_xlabel("Measurement Number")
        self.ax.set_ylabel("Velocity (m/s)")
        self.ax.set_title("Ultrasonic Velocity Measurements")
        self.ax.set_xticks([1, 2, 3])
        self.ax.set_ylim(bottom=0)  # Always start y-axis at 0
        self.ax.legend(loc='best')
        self.ax.grid(True, linestyle='--', alpha=0.7)

        self.fig.tight_layout()
        self.canvas.draw()

    def clear_results(self):
        """Clear all results."""
        self.current_results = None

        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        self.ax.clear()
        self._setup_empty_plot()
        self.canvas.draw()

        self._update_status("Results cleared")

    def export_results(self):
        """Export results to CSV."""
        if not self.current_results:
            messagebox.showwarning("Warning", "No results to export")
            return

        filepath = filedialog.asksaveasfilename(
            title="Export Results",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if filepath:
            try:
                with open(filepath, 'w') as f:
                    f.write("Parameter,Value,Uncertainty,Unit\n")
                    f.write(f"Density,{self.current_results.density.value},{self.current_results.density.uncertainty},{self.current_results.density.unit}\n")
                    f.write(f"Longitudinal Velocity,{self.current_results.longitudinal_velocity.value},{self.current_results.longitudinal_velocity.uncertainty},{self.current_results.longitudinal_velocity.unit}\n")
                    f.write(f"Shear Velocity,{self.current_results.shear_velocity.value},{self.current_results.shear_velocity.uncertainty},{self.current_results.shear_velocity.unit}\n")
                    f.write(f"Poissons Ratio,{self.current_results.poissons_ratio.value},{self.current_results.poissons_ratio.uncertainty},{self.current_results.poissons_ratio.unit}\n")
                    f.write(f"Shear Modulus,{self.current_results.shear_modulus.value},{self.current_results.shear_modulus.uncertainty},{self.current_results.shear_modulus.unit}\n")
                    f.write(f"Youngs Modulus,{self.current_results.youngs_modulus.value},{self.current_results.youngs_modulus.uncertainty},{self.current_results.youngs_modulus.unit}\n")

                self._update_status(f"Exported to: {filepath}")
                messagebox.showinfo("Success", f"Results exported to:\n{filepath}")

            except Exception as e:
                messagebox.showerror("Error", f"Export failed:\n{e}")

    def export_report(self):
        """Export results to Word report."""
        if not self.current_results:
            messagebox.showwarning("Warning", "No results to export. Run analysis first.")
            return

        # Get output file path
        filepath = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx")],
            title="Save Sonic Test Report",
            initialfile=f"Sonic_Report_{self.info_vars['specimen_id'].get() or 'Unknown'}.docx"
        )

        if not filepath:
            return

        try:
            from utils.reporting.sonic_word_report import SonicReportGenerator

            # Template path
            template_path = PROJECT_ROOT / "templates" / "sonic_e1875_report_template.docx"
            if not template_path.exists():
                messagebox.showerror("Error", f"Template not found: {template_path}\nRun scripts/create_sonic_template.py first.")
                return

            # Prepare test info
            test_info = {key: var.get() for key, var in self.info_vars.items()}

            # Prepare specimen data
            specimen_data = {
                'specimen_type': self.specimen_type.get(),
                'diameter': self.dim_vars.get('diameter', tk.StringVar()).get(),
                'side_length': self.dim_vars.get('side_length', tk.StringVar()).get(),
                'length': self.dim_vars['length'].get(),
                'mass': self.mass_var.get(),
            }

            # Prepare velocity data
            velocity_data = {
                'vl1': self.vl_vars[0].get() if self.vl_vars[0].get() else '-',
                'vl2': self.vl_vars[1].get() if self.vl_vars[1].get() else '-',
                'vl3': self.vl_vars[2].get() if self.vl_vars[2].get() else '-',
                'vs1': self.vs_vars[0].get() if self.vs_vars[0].get() else '-',
                'vs2': self.vs_vars[1].get() if self.vs_vars[1].get() else '-',
                'vs3': self.vs_vars[2].get() if self.vs_vars[2].get() else '-',
            }

            # Prepare report data
            report_data = SonicReportGenerator.prepare_report_data(
                test_info=test_info,
                specimen_data=specimen_data,
                velocity_data=velocity_data,
                results=self.current_results
            )

            # Save chart
            chart_path = None
            if hasattr(self, 'fig') and self.fig:
                chart_path = Path(filepath).parent / "temp_sonic_chart.png"
                self.fig.savefig(chart_path, dpi=150, bbox_inches='tight')

            # Logo path
            logo_path = PROJECT_ROOT / "templates" / "logo.png"
            if not logo_path.exists():
                logo_path = None

            # Generate report
            generator = SonicReportGenerator(template_path)
            output_path = generator.generate_report(
                output_path=Path(filepath),
                data=report_data,
                chart_path=chart_path,
                logo_path=logo_path
            )

            # Clean up temp chart
            if chart_path and chart_path.exists():
                chart_path.unlink()

            self._update_status(f"Report saved: {output_path}")
            messagebox.showinfo("Success", f"Report saved to:\n{output_path}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report:\n{str(e)}")
            import traceback
            traceback.print_exc()

    def _refresh_certificate_list(self):
        """Load certificate numbers from database into combobox."""
        try:
            from utils.database.certificate_db import CertificateDatabase
            db = CertificateDatabase()
            cert_numbers = db.get_certificate_numbers_list()

            if hasattr(self, 'cert_combobox'):
                self.cert_combobox['values'] = cert_numbers
                if hasattr(self, 'statusbar'):
                    self._update_status(f"Loaded {len(cert_numbers)} certificates")
        except Exception as e:
            print(f"Error loading certificates: {e}")

    def _on_certificate_selected(self, event):
        """Handle certificate selection from combobox - populate test info fields."""
        cert_number = self.info_vars['certificate_number'].get()
        if not cert_number:
            return

        try:
            from utils.database.certificate_db import CertificateDatabase
            db = CertificateDatabase()
            cert = db.get_certificate_by_string(cert_number)

            if cert:
                # Populate fields from certificate
                self.info_vars['test_project'].set(cert.test_project or "")
                self.info_vars['customer'].set(cert.customer or "")
                self.info_vars['customer_order'].set(cert.customer_order or "")
                self.info_vars['product_sn'].set(cert.product_sn or "")
                self.info_vars['specimen_id'].set(cert.specimen_id or "")
                self.info_vars['location_orientation'].set(cert.location_orientation or "")
                self.info_vars['material'].set(cert.material or "")
                self.info_vars['temperature'].set(cert.temperature or "23")
                self.info_vars['test_date'].set(cert.cert_date or "")

                self._update_status(f"Loaded certificate: {cert_number}")
        except Exception as e:
            self._update_status(f"Error loading certificate: {e}")

    def show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About Sonic Resonance Test",
            "Durabler - Sonic Resonance Test\n\n"
            "Version: 0.1.0\n"
            "Standard: Modified ASTM E1875\n\n"
            "Ultrasonic method for determining:\n"
            "- Young's Modulus (E)\n"
            "- Shear Modulus (G)\n"
            "- Poisson's Ratio (ν)\n\n"
            "From longitudinal and shear wave velocities.\n\n"
            "All results include expanded uncertainty (k=2)"
        )

    def _update_status(self, message: str):
        """Update status bar."""
        self.statusbar.config(text=message)
        self.root.update_idletasks()

    def run(self):
        """Start the application main loop."""
        self.root.mainloop()


def main():
    """Application entry point."""
    app = SonicTestApp()
    app.run()


if __name__ == "__main__":
    main()
