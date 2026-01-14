"""
Main Tkinter application for tensile test analysis.

Provides GUI for loading MTS test data, entering specimen dimensions,
running ASTM E8/E8M calculations, and displaying results with plots.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, Dict, Any
import numpy as np

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk


class TensileTestApp:
    """
    Main Tkinter application for tensile test analysis.

    Parameters
    ----------
    parent_launcher : object, optional
        Reference to parent launcher window to return to on close
    """

    def __init__(self, parent_launcher: Optional[Any] = None):
        self.parent_launcher = parent_launcher

        self.root = tk.Toplevel() if parent_launcher else tk.Tk()
        self.root.title("Durabler - Tensile Test Analysis (ASTM E8/E8M)")
        self.root.geometry("1400x900")

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Data storage
        self.current_data = None
        self.current_results = None
        self.stress = None
        self.strain = None
        self.strain_displacement = None  # Strain from crosshead displacement

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
        file_menu.add_command(label="Load CSV...", command=self.load_csv_file,
                              accelerator="Ctrl+O")
        file_menu.add_command(label="Load XML Metadata...", command=self.load_xml_metadata)
        file_menu.add_separator()
        file_menu.add_command(label="Export Results...", command=self.export_results)
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
        self.root.bind('<Control-o>', lambda e: self.load_csv_file())
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

        if self.parent_launcher:
            ttk.Button(toolbar, text="<< Back", command=self._on_close).pack(
                side=tk.LEFT, padx=2)
            ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        ttk.Button(toolbar, text="Load CSV", command=self.load_csv_file).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Load XML", command=self.load_xml_metadata).pack(
            side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(toolbar, text="Analyze", command=self.run_analysis).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Clear", command=self.clear_results).pack(
            side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(toolbar, text="Export PDF", command=self.export_pdf).pack(
            side=tk.LEFT, padx=2)

    def _create_main_panels(self):
        """Create left and right panels."""
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # Left panel
        self._create_left_panel(main_frame)

        # Right panel (plot)
        self._create_plot_panel(main_frame)

    def _create_left_panel(self, parent):
        """Create left panel with specimen input and results."""
        # Create scrollable frame for left panel
        left_frame = ttk.Frame(parent, width=400)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.grid_propagate(False)

        # Specimen type selection
        specimen_frame = ttk.LabelFrame(left_frame, text="Specimen Geometry", padding=10)
        specimen_frame.pack(fill=tk.X, pady=5)

        self.specimen_type = tk.StringVar(value="round")
        ttk.Radiobutton(
            specimen_frame, text="Round (Cylindrical)",
            variable=self.specimen_type, value="round",
            command=self._update_dimension_fields
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            specimen_frame, text="Rectangular (Flat)",
            variable=self.specimen_type, value="rectangular",
            command=self._update_dimension_fields
        ).pack(anchor=tk.W)

        # Dimension entry frame
        self.dim_frame = ttk.LabelFrame(left_frame, text="Dimensions", padding=10)
        self.dim_frame.pack(fill=tk.X, pady=5)
        self.dim_vars: Dict[str, tk.StringVar] = {}
        self._create_dimension_fields()

        # Strain source selection
        strain_frame = ttk.LabelFrame(left_frame, text="Strain Source", padding=10)
        strain_frame.pack(fill=tk.X, pady=5)

        self.strain_source = tk.StringVar(value="extensometer")
        ttk.Radiobutton(
            strain_frame, text="Extensometer (recommended)",
            variable=self.strain_source, value="extensometer"
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            strain_frame, text="Crosshead displacement",
            variable=self.strain_source, value="displacement"
        ).pack(anchor=tk.W)

        ttk.Label(
            strain_frame,
            text="Note: Crosshead strain uses parallel length (Lc)",
            font=('Helvetica', 8, 'italic'),
            foreground='gray'
        ).pack(anchor=tk.W, pady=(5, 0))

        # Test info frame
        info_frame = ttk.LabelFrame(left_frame, text="Test Information", padding=10)
        info_frame.pack(fill=tk.X, pady=5)

        ttk.Label(info_frame, text="Specimen ID:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.specimen_id_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.specimen_id_var, width=25).grid(
            row=0, column=1, sticky=tk.EW, pady=2)

        ttk.Label(info_frame, text="Material:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.material_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.material_var, width=25).grid(
            row=1, column=1, sticky=tk.EW, pady=2)

        ttk.Label(info_frame, text="Test Date:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.date_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.date_var, state='readonly', width=25).grid(
            row=2, column=1, sticky=tk.EW, pady=2)

        ttk.Label(info_frame, text="File:").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.file_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.file_var, state='readonly', width=25).grid(
            row=3, column=1, sticky=tk.EW, pady=2)

        info_frame.columnconfigure(1, weight=1)

        # Results frame
        results_frame = ttk.LabelFrame(left_frame, text="Results (ASTM E8/E8M)", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Create treeview for results
        columns = ("parameter", "value", "uncertainty", "unit")
        self.results_tree = ttk.Treeview(
            results_frame, columns=columns, show="headings", height=10
        )

        self.results_tree.heading("parameter", text="Parameter")
        self.results_tree.heading("value", text="Value")
        self.results_tree.heading("uncertainty", text="U (k=2)")
        self.results_tree.heading("unit", text="Unit")

        self.results_tree.column("parameter", width=130)
        self.results_tree.column("value", width=80, anchor=tk.E)
        self.results_tree.column("uncertainty", width=80, anchor=tk.E)
        self.results_tree.column("unit", width=50, anchor=tk.CENTER)

        self.results_tree.pack(fill=tk.BOTH, expand=True)

    def _create_dimension_fields(self):
        """Create dimension entry fields based on specimen type."""
        # Clear existing fields
        for widget in self.dim_frame.winfo_children():
            widget.destroy()

        self.dim_vars = {}

        if self.specimen_type.get() == "round":
            fields = [
                ("Diameter (mm):", "diameter", "9.97"),
                ("Diameter StdDev (mm):", "diameter_std", "0.01"),
                ("Gauge Length L0 (mm):", "gauge_length", "50.0"),
                ("Parallel Length Lc (mm):", "parallel_length", "60.0"),
                ("Final Diameter (mm):", "final_diameter", ""),
            ]
        else:
            fields = [
                ("Width (mm):", "width", "12.5"),
                ("Width StdDev (mm):", "width_std", "0.01"),
                ("Thickness (mm):", "thickness", "3.0"),
                ("Thickness StdDev (mm):", "thickness_std", "0.01"),
                ("Gauge Length L0 (mm):", "gauge_length", "50.0"),
                ("Parallel Length Lc (mm):", "parallel_length", "60.0"),
            ]

        for i, (label, key, default) in enumerate(fields):
            ttk.Label(self.dim_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=default)
            self.dim_vars[key] = var
            entry = ttk.Entry(self.dim_frame, textvariable=var, width=12)
            entry.grid(row=i, column=1, sticky=tk.W, pady=2)

        self.dim_frame.columnconfigure(1, weight=1)

    def _update_dimension_fields(self):
        """Update dimension fields when specimen type changes."""
        self._create_dimension_fields()

    def _create_plot_panel(self, parent):
        """Create matplotlib plot panel."""
        plot_frame = ttk.Frame(parent)
        plot_frame.grid(row=0, column=1, sticky="nsew")
        plot_frame.columnconfigure(0, weight=1)
        plot_frame.rowconfigure(0, weight=1)

        # Create matplotlib figure
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self._setup_empty_plot()

        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Create toolbar
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()

    def _setup_empty_plot(self):
        """Set up empty plot with labels."""
        self.ax.set_xlabel("Strain (mm/mm)")
        self.ax.set_ylabel("Stress (MPa)")
        self.ax.set_title("Engineering Stress-Strain Curve")
        self.ax.grid(True, linestyle='--', alpha=0.7)

    def _create_statusbar(self):
        """Create status bar at bottom."""
        self.statusbar = ttk.Label(
            self.root, text="Ready - Load a CSV file to begin",
            relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.grid(row=2, column=0, sticky="ew")

    def load_csv_file(self):
        """Load MTS CSV data file."""
        filepath = filedialog.askopenfilename(
            title="Select MTS CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir="/Users/pjbhb/durabler1/data/Testdataexport"
        )
        if filepath:
            try:
                from ..data_acquisition.mts_csv_parser import parse_mts_csv

                self.current_data = parse_mts_csv(Path(filepath))
                self.date_var.set(self.current_data.test_date)
                self.specimen_id_var.set(self.current_data.test_run_name)
                self.file_var.set(Path(filepath).name)

                self._update_status(f"Loaded: {Path(filepath).name}")
                self._plot_raw_data()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load CSV:\n{e}")
                import traceback
                traceback.print_exc()

    def load_xml_metadata(self):
        """Load MTS XML metadata file."""
        filepath = filedialog.askopenfilename(
            title="Select MTS XML File",
            filetypes=[("XML files", "*.xml"), ("All files", "*.*")],
            initialdir="/Users/pjbhb/durabler1/data/Testdataexport"
        )
        if filepath:
            try:
                from ..data_acquisition.mts_xml_parser import parse_mts_xml

                metadata = parse_mts_xml(Path(filepath))

                # Populate fields from XML
                if metadata.diameter and 'diameter' in self.dim_vars:
                    self.dim_vars['diameter'].set(str(metadata.diameter))
                if metadata.gauge_length and 'gauge_length' in self.dim_vars:
                    self.dim_vars['gauge_length'].set(str(metadata.gauge_length))
                if metadata.parallel_length and 'parallel_length' in self.dim_vars:
                    self.dim_vars['parallel_length'].set(str(metadata.parallel_length))
                if metadata.width and 'width' in self.dim_vars:
                    self.dim_vars['width'].set(str(metadata.width))
                if metadata.thickness and 'thickness' in self.dim_vars:
                    self.dim_vars['thickness'].set(str(metadata.thickness))

                self._update_status(f"Loaded metadata: {Path(filepath).name}")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load XML:\n{e}")

    def _plot_raw_data(self):
        """Plot raw force-extension data."""
        if self.current_data is None:
            return

        self.ax.clear()
        self.ax.plot(
            self.current_data.extension,
            self.current_data.force,
            'b-', linewidth=0.5, label='Extensometer'
        )
        self.ax.plot(
            self.current_data.displacement - self.current_data.displacement[0],
            self.current_data.force,
            'r-', linewidth=0.5, alpha=0.5, label='Crosshead'
        )
        self.ax.set_xlabel("Extension / Displacement (mm)")
        self.ax.set_ylabel("Force (kN)")
        self.ax.set_title(f"Raw Data: {self.current_data.test_run_name}")
        self.ax.grid(True, linestyle='--', alpha=0.7)
        self.ax.legend(loc='lower right')
        self.fig.tight_layout()
        self.canvas.draw()

    def run_analysis(self):
        """Run full tensile analysis."""
        if self.current_data is None:
            messagebox.showwarning("Warning", "Please load test data first")
            return

        try:
            from ..analysis.tensile_calculations import TensileAnalyzer
            from ..models.specimen import RoundSpecimen, RectangularSpecimen

            self._update_status("Running analysis...")

            analyzer = TensileAnalyzer()

            # Build specimen from input fields
            gauge_length = float(self.dim_vars['gauge_length'].get())
            parallel_length = float(self.dim_vars['parallel_length'].get())

            if self.specimen_type.get() == "round":
                diameter = float(self.dim_vars['diameter'].get())
                diameter_std = float(self.dim_vars['diameter_std'].get())
                specimen = RoundSpecimen(
                    specimen_id=self.specimen_id_var.get(),
                    diameter=diameter,
                    diameter_std=diameter_std,
                    gauge_length=gauge_length,
                    parallel_length=parallel_length,
                    material=self.material_var.get()
                )
                area = specimen.area
                area_unc = specimen.area_uncertainty
            else:
                width = float(self.dim_vars['width'].get())
                width_std = float(self.dim_vars['width_std'].get())
                thickness = float(self.dim_vars['thickness'].get())
                thickness_std = float(self.dim_vars['thickness_std'].get())
                specimen = RectangularSpecimen(
                    specimen_id=self.specimen_id_var.get(),
                    width=width,
                    width_std=width_std,
                    thickness=thickness,
                    thickness_std=thickness_std,
                    gauge_length=gauge_length,
                    parallel_length=parallel_length,
                    material=self.material_var.get()
                )
                area = specimen.area
                area_unc = specimen.area_uncertainty

            # Calculate stress (same for both strain sources)
            stress = (self.current_data.force * 1000) / area  # MPa

            # Calculate strain from extensometer
            strain_ext = self.current_data.extension / gauge_length

            # Calculate strain from crosshead displacement
            # Zero the displacement and use parallel length
            displacement_zeroed = self.current_data.displacement - self.current_data.displacement[0]
            strain_disp = displacement_zeroed / parallel_length

            # Store both strain arrays
            self.strain_extensometer = strain_ext
            self.strain_displacement = strain_disp

            # Select strain source based on user choice
            if self.strain_source.get() == "extensometer":
                self.strain = strain_ext
                strain_label = "Extensometer"
                reference_length = gauge_length
            else:
                self.strain = strain_disp
                strain_label = "Crosshead"
                reference_length = parallel_length

            self.stress = stress

            # Calculate results using selected strain
            E = analyzer.calculate_youngs_modulus(
                self.stress, self.strain, area_unc, reference_length
            )
            Rp02 = analyzer.calculate_yield_strength_rp02(
                self.stress, self.strain, E.value, area, area_unc
            )
            Rm = analyzer.calculate_ultimate_tensile_strength(
                self.current_data.force, area, area_unc
            )

            # Elongation calculations - use appropriate extension/displacement
            if self.strain_source.get() == "extensometer":
                extension_data = self.current_data.extension
                ref_length = gauge_length
            else:
                extension_data = displacement_zeroed
                ref_length = parallel_length

            A_percent = analyzer.calculate_elongation_at_fracture(
                extension_data, self.current_data.force, ref_length
            )
            Ag = analyzer.calculate_uniform_elongation(
                extension_data, self.current_data.force, ref_length
            )

            # Calculate Z% for round specimens if final diameter provided
            Z = None
            if self.specimen_type.get() == "round":
                final_d_str = self.dim_vars.get('final_diameter', tk.StringVar()).get()
                if final_d_str:
                    try:
                        final_d = float(final_d_str)
                        Z = analyzer.calculate_reduction_of_area(diameter, final_d)
                    except ValueError:
                        pass

            # Store results
            self.current_results = {
                'E': E,
                'Rp02': Rp02,
                'Rm': Rm,
                'A_percent': A_percent,
                'Ag': Ag,
                'Z': Z,
                'strain_source': strain_label
            }

            # Update results display
            self._display_results()

            # Plot stress-strain with annotations
            self._plot_stress_strain()

            self._update_status(f"Analysis complete (strain from {strain_label})")

        except ValueError as e:
            messagebox.showerror("Analysis Error", f"Invalid input:\n{e}")
        except Exception as e:
            messagebox.showerror("Analysis Error", f"Analysis failed:\n{e}")
            import traceback
            traceback.print_exc()

    def _display_results(self):
        """Update results treeview."""
        # Clear existing
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        if not self.current_results:
            return

        # Add strain source info
        strain_source = self.current_results.get('strain_source', 'Extensometer')
        self.results_tree.insert("", tk.END, values=(
            f"Strain Source:",
            strain_source,
            "",
            ""
        ), tags=('info',))

        results = [
            ("E (Young's Modulus)", self.current_results['E']),
            ("Rp0.2 (Yield)", self.current_results['Rp02']),
            ("Rm (Ultimate)", self.current_results['Rm']),
            ("A% (Elongation)", self.current_results['A_percent']),
            ("Ag (Uniform Elong.)", self.current_results['Ag']),
        ]

        if self.current_results.get('Z'):
            results.append(("Z% (Red. of Area)", self.current_results['Z']))

        for name, result in results:
            self.results_tree.insert("", tk.END, values=(
                name,
                f"{result.value:.2f}",
                f"+/-{result.uncertainty:.2f}",
                result.unit
            ))

    def _plot_stress_strain(self):
        """Plot stress-strain curve with key points annotated."""
        if self.stress is None or self.strain is None:
            return

        self.ax.clear()

        # Plot both strain sources if available
        if self.strain_extensometer is not None:
            self.ax.plot(self.strain_extensometer, self.stress, 'b-', linewidth=1,
                         alpha=0.3 if self.strain_source.get() != "extensometer" else 1.0,
                         label='Extensometer')
        if self.strain_displacement is not None:
            self.ax.plot(self.strain_displacement, self.stress, 'r-', linewidth=1,
                         alpha=0.3 if self.strain_source.get() != "displacement" else 1.0,
                         label='Crosshead')

        E = self.current_results['E']
        Rp02 = self.current_results['Rp02']
        Rm = self.current_results['Rm']

        # Offset line for Rp0.2
        offset = 0.002
        E_mpa = E.value * 1000
        max_strain_for_line = min(0.02, np.max(self.strain) * 0.3)
        offset_strain = np.linspace(offset, max_strain_for_line, 100)
        offset_stress = E_mpa * (offset_strain - offset)
        self.ax.plot(offset_strain, offset_stress, 'g--', linewidth=0.8,
                     label='0.2% Offset Line')

        # Mark Rp0.2
        rp02_strain = offset + Rp02.value / E_mpa
        self.ax.plot(rp02_strain, Rp02.value, 'go', markersize=8)
        self.ax.annotate(
            f'Rp0.2 = {Rp02.value:.0f} MPa',
            xy=(rp02_strain, Rp02.value),
            xytext=(rp02_strain + 0.01, Rp02.value - Rm.value * 0.1),
            fontsize=9,
            arrowprops=dict(arrowstyle='->', color='green', lw=1)
        )

        # Mark Rm
        rm_idx = np.argmax(self.stress)
        self.ax.plot(self.strain[rm_idx], Rm.value, 'ro', markersize=8)
        self.ax.annotate(
            f'Rm = {Rm.value:.0f} MPa',
            xy=(self.strain[rm_idx], Rm.value),
            xytext=(self.strain[rm_idx] + 0.01, Rm.value + Rm.value * 0.02),
            fontsize=9,
            arrowprops=dict(arrowstyle='->', color='red', lw=1)
        )

        strain_label = self.current_results.get('strain_source', 'Extensometer')
        self.ax.set_xlabel(f"Engineering Strain (mm/mm) - {strain_label}")
        self.ax.set_ylabel("Engineering Stress (MPa)")
        self.ax.set_title(f"Tensile Test: {self.specimen_id_var.get()}")
        self.ax.legend(loc='lower right')
        self.ax.grid(True, linestyle='--', alpha=0.7)

        # Set reasonable axis limits
        self.ax.set_xlim(left=0)
        self.ax.set_ylim(bottom=0)

        self.fig.tight_layout()
        self.canvas.draw()

    def clear_results(self):
        """Clear all results and reset plot."""
        self.current_results = None
        self.stress = None
        self.strain = None
        self.strain_extensometer = None
        self.strain_displacement = None

        # Clear treeview
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        # Reset plot
        if self.current_data:
            self._plot_raw_data()
        else:
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
                    f.write(f"Strain Source,{self.current_results.get('strain_source', '')},,\n")
                    for key, result in self.current_results.items():
                        if result and key != 'strain_source' and hasattr(result, 'value'):
                            f.write(f"{key},{result.value},{result.uncertainty},{result.unit}\n")

                self._update_status(f"Exported to: {filepath}")
                messagebox.showinfo("Success", f"Results exported to:\n{filepath}")

            except Exception as e:
                messagebox.showerror("Error", f"Export failed:\n{e}")

    def export_pdf(self):
        """Export results to PDF report."""
        messagebox.showinfo(
            "Info",
            "PDF report generation will be implemented in a future update.\n\n"
            "This will include:\n"
            "- Accredited report header\n"
            "- Specimen details\n"
            "- Results with uncertainties\n"
            "- Stress-strain curve\n"
            "- Approval signatures"
        )

    def show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About Durabler",
            "Durabler - Tensile Test Analysis\n\n"
            "Version: 0.1.0\n"
            "Standard: ASTM E8/E8M-22\n\n"
            "ISO 17025 compliant analysis system\n"
            "for mechanical testing laboratories.\n\n"
            "Calculations include:\n"
            "- Young's Modulus (E)\n"
            "- Yield Strength (Rp0.2)\n"
            "- Ultimate Tensile Strength (Rm)\n"
            "- Elongation at Fracture (A%)\n"
            "- Uniform Elongation (Ag)\n"
            "- Reduction of Area (Z%)\n\n"
            "Strain sources:\n"
            "- Extensometer (L0)\n"
            "- Crosshead displacement (Lc)\n\n"
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
    app = TensileTestApp()
    app.run()


if __name__ == "__main__":
    main()
