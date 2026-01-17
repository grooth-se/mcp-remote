"""
KIC Fracture Toughness Test Application Window (ASTM E399).

Provides GUI for loading MTS test data, entering specimen dimensions,
running ASTM E399 KIC calculations, and displaying results with plots.

Supports SE(B) and C(T) specimen types.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, Dict, Any
import numpy as np
from PIL import Image, ImageTk

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# Project root for logo path
PROJECT_ROOT = Path(__file__).parent.parent.parent


class KICTestApp:
    """
    Main Tkinter application for KIC fracture toughness testing (ASTM E399).

    Parameters
    ----------
    parent_launcher : object, optional
        Reference to parent launcher window to return to on close
    """

    def __init__(self, parent_launcher: Optional[Any] = None):
        self.parent_launcher = parent_launcher

        self.root = tk.Toplevel() if parent_launcher else tk.Tk()
        self.root.title("Durabler - Fracture Toughness KIC (ASTM E399)")
        self.root.geometry("1400x900")

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Data storage
        self.current_data = None
        self.current_results = None
        self.precrack_measurements = []  # Store precrack measurements from Excel
        self.crack_photo_path = None     # Path to crack surface photo

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
        file_menu.add_command(label="Load Excel...", command=self.load_excel_file,
                              accelerator="Ctrl+E")
        file_menu.add_command(label="Load Crack Photo...", command=self.load_crack_photo,
                              accelerator="Ctrl+P")
        file_menu.add_separator()
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
        self.root.bind('<Control-o>', lambda e: self.load_csv_file())
        self.root.bind('<Control-e>', lambda e: self.load_excel_file())
        self.root.bind('<Control-p>', lambda e: self.load_crack_photo())
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

        ttk.Button(toolbar, text="Load CSV", command=self.load_csv_file).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Load Excel", command=self.load_excel_file).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Load Photo", command=self.load_crack_photo).pack(
            side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
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

        # Right panel (results table + plot)
        self._create_right_panel(main_frame)

    def _create_left_panel(self, parent):
        """Create left panel with specimen inputs."""
        left_frame = ttk.Frame(parent, width=420)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.grid_propagate(False)

        # Specimen type selection
        specimen_frame = ttk.LabelFrame(left_frame, text="Specimen Type", padding=10)
        specimen_frame.pack(fill=tk.X, pady=5)

        self.specimen_type = tk.StringVar(value="SE(B)")
        ttk.Radiobutton(
            specimen_frame, text="SE(B) - Single Edge Bend",
            variable=self.specimen_type, value="SE(B)",
            command=self._update_dimension_fields
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            specimen_frame, text="C(T) - Compact Tension",
            variable=self.specimen_type, value="C(T)",
            command=self._update_dimension_fields
        ).pack(anchor=tk.W)

        # Specimen dimensions frame
        self.dim_frame = ttk.LabelFrame(left_frame, text="Specimen Dimensions", padding=10)
        self.dim_frame.pack(fill=tk.X, pady=5)
        self.dim_vars = {}
        self._create_dimension_fields()

        # Material properties frame
        material_frame = ttk.LabelFrame(left_frame, text="Material Properties", padding=10)
        material_frame.pack(fill=tk.X, pady=5)

        self.material_vars = {}

        row = 0
        # Yield strength
        ttk.Label(material_frame, text="Yield strength sigma_ys (MPa):").grid(
            row=row, column=0, sticky=tk.W, pady=2)
        self.material_vars['yield_strength'] = tk.StringVar(value="500")
        ttk.Entry(material_frame, textvariable=self.material_vars['yield_strength'],
                  width=15).grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        # Young's modulus
        ttk.Label(material_frame, text="Young's modulus E (GPa):").grid(
            row=row, column=0, sticky=tk.W, pady=2)
        self.material_vars['youngs_modulus'] = tk.StringVar(value="210")
        ttk.Entry(material_frame, textvariable=self.material_vars['youngs_modulus'],
                  width=15).grid(row=row, column=1, sticky=tk.W, pady=2)

        row += 1
        # Poisson's ratio
        ttk.Label(material_frame, text="Poisson's ratio nu:").grid(
            row=row, column=0, sticky=tk.W, pady=2)
        self.material_vars['poissons_ratio'] = tk.StringVar(value="0.3")
        ttk.Entry(material_frame, textvariable=self.material_vars['poissons_ratio'],
                  width=15).grid(row=row, column=1, sticky=tk.W, pady=2)

        # Test information frame
        info_frame = ttk.LabelFrame(left_frame, text="Test Information", padding=10)
        info_frame.pack(fill=tk.X, pady=5)

        self.info_vars = {}
        info_fields = [
            ("certificate_number", "Certificate number:"),
            ("test_project", "Test project:"),
            ("customer", "Customer:"),
            ("specimen_id", "Specimen ID:"),
            ("material", "Material:"),
            ("test_date", "Test date:"),
            ("temperature", "Temperature (C):"),
        ]

        row = 0
        for key, label in info_fields:
            ttk.Label(info_frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar()
            self.info_vars[key] = var

            # Certificate number uses Combobox with database integration
            if key == "certificate_number":
                cert_frame = ttk.Frame(info_frame)
                cert_frame.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self.cert_combobox = ttk.Combobox(cert_frame, textvariable=var, width=22)
                self.cert_combobox.pack(side=tk.LEFT)
                self.cert_combobox.bind('<<ComboboxSelected>>', self._on_certificate_selected)
                ttk.Button(cert_frame, text="refresh", width=3,
                           command=self._refresh_certificate_list).pack(side=tk.LEFT, padx=2)
                self._refresh_certificate_list()
            else:
                ttk.Entry(info_frame, textvariable=var, width=38).grid(
                    row=row, column=1, sticky=tk.W, pady=2)
            row += 1

        # Set default temperature
        self.info_vars['temperature'].set("23")

        # Data file frame
        file_frame = ttk.LabelFrame(left_frame, text="Data File", padding=10)
        file_frame.pack(fill=tk.X, pady=5)

        self.file_var = tk.StringVar(value="No file loaded")
        ttk.Label(file_frame, textvariable=self.file_var, foreground='gray').pack(anchor=tk.W)

    def _create_dimension_fields(self):
        """Create dimension entry fields based on specimen type."""
        # Clear existing fields
        for widget in self.dim_frame.winfo_children():
            widget.destroy()

        self.dim_vars = {}
        spec_type = self.specimen_type.get()

        # Common fields for both specimen types
        fields = [
            ("W", "Width W (mm):", "25.0"),
            ("B", "Thickness B (mm):", "12.5"),
            ("a_0", "Crack length a_0 (mm):", "12.5"),
        ]

        # Add span for SE(B) only
        if spec_type == "SE(B)":
            fields.append(("S", "Span S (mm):", "100.0"))

        # Add B_n (net thickness for side-grooved)
        fields.append(("B_n", "Net thickness B_n (mm):", ""))

        row = 0
        for key, label, default in fields:
            ttk.Label(self.dim_frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=default)
            self.dim_vars[key] = var
            ttk.Entry(self.dim_frame, textvariable=var, width=15).grid(
                row=row, column=1, sticky=tk.W, pady=2)
            row += 1

        # Add a/W ratio display (calculated)
        ttk.Separator(self.dim_frame, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=5)
        row += 1

        ttk.Label(self.dim_frame, text="a/W ratio:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.aW_label = ttk.Label(self.dim_frame, text="-", foreground='blue')
        self.aW_label.grid(row=row, column=1, sticky=tk.W, pady=2)

        # Bind entries to update a/W display
        for key in ['W', 'a_0']:
            if key in self.dim_vars:
                self.dim_vars[key].trace_add('write', self._update_aW_display)

        self._update_aW_display()

    def _update_dimension_fields(self):
        """Update dimension fields when specimen type changes."""
        self._create_dimension_fields()

    def _update_aW_display(self, *args):
        """Update the a/W ratio display."""
        try:
            W = float(self.dim_vars['W'].get())
            a = float(self.dim_vars['a_0'].get())
            if W > 0:
                aW = a / W
                color = 'green' if 0.45 <= aW <= 0.55 else 'red'
                self.aW_label.config(text=f"{aW:.3f}", foreground=color)
            else:
                self.aW_label.config(text="-", foreground='blue')
        except ValueError:
            self.aW_label.config(text="-", foreground='blue')

    def _create_right_panel(self, parent):
        """Create right panel with results and plot."""
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        # Results frame (top)
        results_frame = ttk.LabelFrame(right_frame, text="Results", padding=10)
        results_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        # Results treeview
        columns = ("parameter", "value", "uncertainty", "unit")
        self.results_tree = ttk.Treeview(
            results_frame, columns=columns, show="headings", height=12
        )

        self.results_tree.heading("parameter", text="Parameter")
        self.results_tree.heading("value", text="Value")
        self.results_tree.heading("uncertainty", text="U (k=2)")
        self.results_tree.heading("unit", text="Unit")

        self.results_tree.column("parameter", width=180)
        self.results_tree.column("value", width=100, anchor=tk.E)
        self.results_tree.column("uncertainty", width=100, anchor=tk.E)
        self.results_tree.column("unit", width=80, anchor=tk.CENTER)

        self.results_tree.pack(fill=tk.BOTH, expand=True)

        # Tag configurations for styling
        self.results_tree.tag_configure('section', background='#E0E0E0', font=('Helvetica', 9, 'bold'))
        self.results_tree.tag_configure('valid', foreground='green')
        self.results_tree.tag_configure('invalid', foreground='red')
        self.results_tree.tag_configure('warning', foreground='orange')

        # Plot frame (bottom)
        plot_frame = ttk.LabelFrame(right_frame, text="Force vs Displacement", padding=5)
        plot_frame.grid(row=1, column=0, sticky="nsew")

        # Create matplotlib figure
        self.fig = Figure(figsize=(5, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)

        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Create toolbar
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()

    def _create_statusbar(self):
        """Create status bar at bottom."""
        self.statusbar = ttk.Label(
            self.root, text="Ready - Load a CSV file to begin",
            relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.grid(row=2, column=0, sticky="ew")

    def _update_status(self, message: str):
        """Update status bar."""
        self.statusbar.config(text=message)
        self.root.update_idletasks()

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
                if 'test_project' in self.info_vars and cert.test_project:
                    self.info_vars['test_project'].set(cert.test_project)
                if 'customer' in self.info_vars and cert.customer:
                    self.info_vars['customer'].set(cert.customer)
                if 'material' in self.info_vars and cert.material:
                    self.info_vars['material'].set(cert.material)

                self._update_status(f"Loaded certificate: {cert_number}")
        except Exception as e:
            self._update_status(f"Error loading certificate: {e}")

    def load_csv_file(self):
        """Load MTS CSV data file."""
        filepath = filedialog.askopenfilename(
            title="Select MTS CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=str(PROJECT_ROOT / "data" / "Testdataexport")
        )

        if not filepath:
            return

        try:
            from utils.data_acquisition.kic_csv_parser import parse_kic_csv

            self.current_data = parse_kic_csv(Path(filepath))
            self.file_var.set(Path(filepath).name)

            # Update test info from file
            if self.current_data.test_date:
                self.info_vars['test_date'].set(self.current_data.test_date)
            if self.current_data.test_run_name:
                self.info_vars['specimen_id'].set(self.current_data.test_run_name)

            self._update_status(f"Loaded: {Path(filepath).name} ({self.current_data.num_points} points)")
            self._plot_raw_data()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load CSV:\n{e}")
            import traceback
            traceback.print_exc()

    def load_excel_file(self):
        """Load MTS Excel Analysis Report file with specimen data."""
        filepath = filedialog.askopenfilename(
            title="Select MTS Excel Analysis Report",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialdir=str(PROJECT_ROOT / "data" / "Testdataexport")
        )

        if not filepath:
            return

        try:
            from utils.data_acquisition.kic_excel_parser import parse_kic_excel

            excel_data = parse_kic_excel(Path(filepath))

            # Set specimen type
            self.specimen_type.set(excel_data.specimen_type)
            self._update_dimension_fields()

            # Populate dimension fields
            self.dim_vars['W'].set(f"{excel_data.W:.2f}")
            self.dim_vars['B'].set(f"{excel_data.B:.2f}")
            self.dim_vars['a_0'].set(f"{excel_data.crack_length_average:.2f}")
            if 'S' in self.dim_vars:
                self.dim_vars['S'].set(f"{excel_data.S:.2f}")
            if excel_data.B_n and excel_data.B_n != excel_data.B:
                self.dim_vars['B_n'].set(f"{excel_data.B_n:.2f}")

            # Populate material properties
            self.material_vars['yield_strength'].set(f"{excel_data.yield_strength:.1f}")
            self.material_vars['youngs_modulus'].set(f"{excel_data.youngs_modulus:.1f}")
            self.material_vars['poissons_ratio'].set(f"{excel_data.poissons_ratio:.3f}")

            # Populate test info
            self.info_vars['specimen_id'].set(excel_data.specimen_id)
            self.info_vars['temperature'].set(f"{excel_data.test_temperature:.1f}")

            # Store MTS results for comparison
            self.mts_results = excel_data.kic_results

            # Store precrack measurements
            self.precrack_measurements = excel_data.precrack_measurements
            self.precrack_final_size = excel_data.precrack_final_size

            self._update_status(f"Loaded Excel: {Path(filepath).name}")

            # Display MTS results if available
            if excel_data.kic_results.get('KQ', 0) > 0:
                self._display_mts_results(excel_data)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load Excel:\n{e}")
            import traceback
            traceback.print_exc()

    def _display_mts_results(self, excel_data):
        """Display MTS analysis results in treeview."""
        # Clear existing
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        r = excel_data.kic_results

        # Precrack Measurements section
        if excel_data.precrack_measurements:
            self.results_tree.insert("", tk.END, values=("Precrack Measurements", "", "", ""),
                                      tags=('section',))
            for i, meas in enumerate(excel_data.precrack_measurements, 1):
                self.results_tree.insert("", tk.END, values=(
                    f"  Crack {i}",
                    f"{meas:.2f}",
                    "",
                    "mm"
                ))

            # Show calculated average
            avg_crack = excel_data.crack_length_average
            self.results_tree.insert("", tk.END, values=(
                "  Average (E399)",
                f"{avg_crack:.2f}",
                "",
                "mm"
            ))

            # Show compliance-based final size
            if excel_data.precrack_final_size > 0:
                self.results_tree.insert("", tk.END, values=(
                    "  Final (compliance)",
                    f"{excel_data.precrack_final_size:.2f}",
                    "",
                    "mm"
                ))

        # MTS Results section
        self.results_tree.insert("", tk.END, values=("MTS Analysis Results", "", "", ""),
                                  tags=('section',))

        self.results_tree.insert("", tk.END, values=(
            "P_max (MTS)",
            f"{r.get('P_max', 0):.2f}",
            "",
            "kN"
        ))

        self.results_tree.insert("", tk.END, values=(
            "P_Q (MTS)",
            f"{r.get('PQ', 0):.2f}",
            "",
            "kN"
        ))

        pmax_pq = r.get('pmax_pq_ratio', 0)
        ratio_tag = 'valid' if pmax_pq <= 1.10 else 'invalid'
        self.results_tree.insert("", tk.END, values=(
            "P_max/P_Q ratio",
            f"{pmax_pq:.3f}",
            "",
            "-"
        ), tags=(ratio_tag,))

        self.results_tree.insert("", tk.END, values=(
            "K_Q (MTS)",
            f"{r.get('KQ', 0):.2f}",
            "",
            "MPa*sqrt(m)"
        ))

        self.results_tree.insert("", tk.END, values=(
            "Type",
            r.get('type', ''),
            "",
            ""
        ))

        # Validity section
        self.results_tree.insert("", tk.END, values=("MTS Validity Checks", "", "", ""),
                                  tags=('section',))

        validity_items = [
            ('P_max/P_Q <= 1.1', r.get('pmax_pq_valid', '')),
            ('a/W in 0.45-0.55', r.get('aw_ratio_valid', '')),
            ('Plane strain', r.get('plane_strain_valid', '')),
            ('Loading rate', r.get('loading_rate_valid', '')),
        ]

        for label, value in validity_items:
            tag = 'valid' if value == 'Yes' else 'invalid' if value == 'No' else 'warning'
            self.results_tree.insert("", tk.END, values=(label, value, "", ""), tags=(tag,))

        self._update_status("MTS results loaded - Load CSV and click Analyze to compare")

    def load_crack_photo(self):
        """Load crack surface photo for inclusion in report."""
        filepath = filedialog.askopenfilename(
            title="Select Crack Surface Photo",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("All files", "*.*")
            ],
            initialdir=str(PROJECT_ROOT / "data" / "Testdataexport")
        )

        if not filepath:
            return

        try:
            # Verify it's a valid image
            test_img = Image.open(filepath)
            test_img.verify()

            self.crack_photo_path = Path(filepath)
            self._update_status(f"Loaded crack photo: {Path(filepath).name}")

            # Show confirmation
            messagebox.showinfo(
                "Photo Loaded",
                f"Crack surface photo loaded:\n{Path(filepath).name}\n\n"
                "The photo will be included in the test report."
            )

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image:\n{e}")
            self.crack_photo_path = None

    def _plot_raw_data(self):
        """Plot raw force-displacement data."""
        if self.current_data is None:
            return

        self.ax.clear()
        self.ax.plot(
            self.current_data.displacement,
            self.current_data.force,
            'b-', linewidth=0.8, label='Test data'
        )
        self.ax.set_xlabel("Displacement (mm)")
        self.ax.set_ylabel("Force (kN)")
        self.ax.set_title("Force vs Displacement")
        self.ax.grid(True, linestyle='--', alpha=0.4)
        self.ax.set_xlim(left=0)
        self.ax.set_ylim(bottom=0)
        self.ax.legend(loc='lower right')
        self.fig.tight_layout()
        self.canvas.draw()

    def run_analysis(self):
        """Run KIC analysis."""
        if self.current_data is None:
            messagebox.showwarning("Warning", "Please load test data first")
            return

        try:
            self._update_status("Running KIC analysis...")

            from utils.models.kic_specimen import KICSpecimen, KICMaterial
            from utils.analysis.kic_calculations import KICAnalyzer

            # Build specimen from inputs
            spec_type = self.specimen_type.get()
            W = float(self.dim_vars['W'].get())
            B = float(self.dim_vars['B'].get())
            a_0 = float(self.dim_vars['a_0'].get())

            S = 0.0
            if spec_type == 'SE(B)' and 'S' in self.dim_vars:
                S = float(self.dim_vars['S'].get())

            B_n = None
            if self.dim_vars.get('B_n') and self.dim_vars['B_n'].get():
                try:
                    B_n = float(self.dim_vars['B_n'].get())
                except ValueError:
                    pass

            specimen = KICSpecimen(
                specimen_id=self.info_vars['specimen_id'].get(),
                specimen_type=spec_type,
                W=W,
                B=B,
                a_0=a_0,
                S=S,
                B_n=B_n,
                material=self.info_vars.get('material', tk.StringVar()).get()
            )

            # Build material
            material = KICMaterial(
                yield_strength=float(self.material_vars['yield_strength'].get()),
                youngs_modulus=float(self.material_vars['youngs_modulus'].get()),
                poissons_ratio=float(self.material_vars['poissons_ratio'].get())
            )

            # Run analysis
            analyzer = KICAnalyzer()
            self.current_results = analyzer.run_analysis(
                force=self.current_data.force,
                displacement=self.current_data.displacement,
                specimen=specimen,
                material=material
            )

            # Update displays
            self._display_results(specimen)
            self._plot_analysis_results(analyzer)

            status = "VALID" if self.current_results.is_valid else "CONDITIONAL"
            self._update_status(f"Analysis complete - KIC is {status}")

        except ValueError as e:
            messagebox.showerror("Input Error", f"Invalid input value:\n{e}")
        except Exception as e:
            messagebox.showerror("Analysis Error", f"Analysis failed:\n{e}")
            import traceback
            traceback.print_exc()

    def _display_results(self, specimen):
        """Display analysis results in treeview."""
        # Clear existing
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        if not self.current_results:
            return

        r = self.current_results

        # Precrack Measurements section (if available)
        if self.precrack_measurements:
            self.results_tree.insert("", tk.END, values=("Precrack Measurements", "", "", ""),
                                      tags=('section',))
            for i, meas in enumerate(self.precrack_measurements, 1):
                self.results_tree.insert("", tk.END, values=(
                    f"  Crack {i}",
                    f"{meas:.2f}",
                    "",
                    "mm"
                ))

            # Calculate E399 average: (0.5*a1 + a2 + a3 + a4 + 0.5*a5) / 4
            if len(self.precrack_measurements) == 5:
                a = self.precrack_measurements
                avg_crack = (0.5 * a[0] + a[1] + a[2] + a[3] + 0.5 * a[4]) / 4
            else:
                avg_crack = sum(self.precrack_measurements) / len(self.precrack_measurements)

            self.results_tree.insert("", tk.END, values=(
                "  Average (E399)",
                f"{avg_crack:.2f}",
                "",
                "mm"
            ))

            # Show compliance-based final size if available
            if hasattr(self, 'precrack_final_size') and self.precrack_final_size > 0:
                self.results_tree.insert("", tk.END, values=(
                    "  Final (compliance)",
                    f"{self.precrack_final_size:.2f}",
                    "",
                    "mm"
                ))

        # Test results section
        self.results_tree.insert("", tk.END, values=("Test Results", "", "", ""),
                                  tags=('section',))

        self.results_tree.insert("", tk.END, values=(
            "P_max",
            f"{r.P_max.value:.2f}",
            f"+/-{r.P_max.uncertainty:.2f}",
            "kN"
        ))

        self.results_tree.insert("", tk.END, values=(
            "P_Q (5% secant)",
            f"{r.P_Q.value:.2f}",
            f"+/-{r.P_Q.uncertainty:.2f}",
            "kN"
        ))

        ratio_tag = 'valid' if r.P_ratio <= 1.10 else 'invalid'
        self.results_tree.insert("", tk.END, values=(
            "P_max/P_Q ratio",
            f"{r.P_ratio:.3f}",
            "",
            "-"
        ), tags=(ratio_tag,))

        # KIC results section
        self.results_tree.insert("", tk.END, values=("KIC Results", "", "", ""),
                                  tags=('section',))

        self.results_tree.insert("", tk.END, values=(
            "K_Q (conditional)",
            f"{r.K_Q.value:.2f}",
            f"+/-{r.K_Q.uncertainty:.2f}",
            "MPa*sqrt(m)"
        ))

        if r.K_IC:
            self.results_tree.insert("", tk.END, values=(
                "K_IC (valid)",
                f"{r.K_IC.value:.2f}",
                f"+/-{r.K_IC.uncertainty:.2f}",
                "MPa*sqrt(m)"
            ), tags=('valid',))
        else:
            self.results_tree.insert("", tk.END, values=(
                "K_IC",
                "CONDITIONAL",
                "",
                ""
            ), tags=('invalid',))

        # Geometry section
        self.results_tree.insert("", tk.END, values=("Geometry", "", "", ""),
                                  tags=('section',))

        aW = specimen.a_W_ratio
        aW_tag = 'valid' if 0.45 <= aW <= 0.55 else 'invalid'
        self.results_tree.insert("", tk.END, values=(
            "a/W ratio",
            f"{aW:.3f}",
            "",
            "-"
        ), tags=(aW_tag,))

        self.results_tree.insert("", tk.END, values=(
            "Compliance",
            f"{r.compliance:.4f}",
            "",
            "mm/kN"
        ))

        # Validity section
        self.results_tree.insert("", tk.END, values=("Validity Checks", "", "", ""),
                                  tags=('section',))

        for note in r.validity_notes:
            if 'PASS' in note:
                tag = 'valid'
            elif 'FAIL' in note:
                tag = 'invalid'
            else:
                tag = 'warning'
            self.results_tree.insert("", tk.END, values=(note, "", "", ""), tags=(tag,))

    def _plot_analysis_results(self, analyzer):
        """Plot analysis results with reference lines."""
        if self.current_data is None or self.current_results is None:
            return

        plot_data = analyzer.get_plot_data(
            force=self.current_data.force,
            displacement=self.current_data.displacement,
            result=self.current_results
        )

        self.ax.clear()

        # Main curve - dark red
        self.ax.plot(
            plot_data['displacement'],
            plot_data['force'],
            color='darkred', linestyle='-', linewidth=0.8, label='Test data'
        )

        # Elastic compliance line - grey dashed
        self.ax.plot(
            plot_data['elastic_line_x'],
            plot_data['elastic_line_y'],
            color='gray', linestyle='--', linewidth=1.2, alpha=0.8, label='Elastic compliance'
        )

        # 5% secant offset line - grey dash-dot
        self.ax.plot(
            plot_data['secant_line_x'],
            plot_data['secant_line_y'],
            color='gray', linestyle='-.', linewidth=1.2, alpha=0.8, label='5% secant offset'
        )

        # PQ point - gray
        pq_x, pq_y = plot_data['P_Q_point']
        self.ax.plot(pq_x, pq_y, 'o', markersize=10, markerfacecolor='none',
                     markeredgecolor='gray', markeredgewidth=2, label=f'P_Q = {pq_y:.2f} kN')

        # Pmax point - black
        pmax_x, pmax_y = plot_data['P_max_point']
        self.ax.plot(pmax_x, pmax_y, 'o', markersize=10, markerfacecolor='none',
                     markeredgecolor='black', markeredgewidth=2, label=f'P_max = {pmax_y:.2f} kN')

        self.ax.set_xlabel("Displacement (mm)")
        self.ax.set_ylabel("Force (kN)")

        status = "VALID" if self.current_results.is_valid else "CONDITIONAL"
        K_val = self.current_results.K_Q.value
        self.ax.set_title(f"KIC Analysis - K_Q = {K_val:.1f} MPa*sqrt(m) ({status})")

        self.ax.grid(True, linestyle='--', alpha=0.4)
        self.ax.set_xlim(left=0)
        self.ax.set_ylim(bottom=0)
        self.ax.legend(loc='lower right', fontsize=8)
        self.fig.tight_layout()
        self.canvas.draw()

    def clear_results(self):
        """Clear all results."""
        self.current_results = None

        # Clear treeview
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        # Clear plot
        self.ax.clear()
        self.ax.set_xlabel("Displacement (mm)")
        self.ax.set_ylabel("Force (kN)")
        self.ax.grid(True, linestyle='--', alpha=0.4)
        self.canvas.draw()

        self._update_status("Results cleared")

    def export_report(self):
        """Export results to Word report using CTOD E1290-style template."""
        if not self.current_results:
            messagebox.showwarning("Warning", "No results to export. Run analysis first.")
            return

        # Get output path
        filepath = filedialog.asksaveasfilename(
            title="Export Report",
            defaultextension=".docx",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
            initialfile=f"KIC_Report_{self.info_vars['specimen_id'].get()}.docx"
        )

        if not filepath:
            return

        try:
            from utils.reporting.kic_word_report import KICReportGenerator

            # Build test info dictionary
            test_info = {
                'certificate_number': self.info_vars['certificate_number'].get(),
                'test_project': self.info_vars['test_project'].get(),
                'customer': self.info_vars['customer'].get(),
                'customer_order': self.info_vars.get('customer_order', tk.StringVar()).get(),
                'product_sn': self.info_vars.get('product_sn', tk.StringVar()).get(),
                'specimen_id': self.info_vars['specimen_id'].get(),
                'location_orientation': self.info_vars.get('location_orientation', tk.StringVar()).get(),
                'material': self.info_vars['material'].get(),
                'test_date': self.info_vars['test_date'].get(),
                'temperature': self.info_vars['temperature'].get(),
            }

            # Build specimen data dictionary
            specimen_data = {
                'specimen_type': self.specimen_type.get(),
                'W': self.dim_vars['W'].get(),
                'B': self.dim_vars['B'].get(),
                'a_0': self.dim_vars['a_0'].get(),
                'notch_type': 'Fatigue pre-crack',
            }
            if 'S' in self.dim_vars:
                specimen_data['S'] = self.dim_vars['S'].get()
            if self.dim_vars.get('B_n') and self.dim_vars['B_n'].get():
                specimen_data['B_n'] = self.dim_vars['B_n'].get()

            # Build material data dictionary
            material_data = {
                'yield_strength': self.material_vars['yield_strength'].get(),
                'ultimate_strength': self.material_vars.get('ultimate_strength', tk.StringVar()).get(),
                'youngs_modulus': self.material_vars['youngs_modulus'].get(),
                'poissons_ratio': self.material_vars['poissons_ratio'].get(),
            }

            # Build results dictionary from KICResult object
            results_dict = {
                'P_max': self.current_results.P_max,
                'P_Q': self.current_results.P_Q,
                'K_Q': self.current_results.K_Q,
                'K_IC': self.current_results.K_IC,
                'P_ratio': self.current_results.P_ratio,
                'compliance': self.current_results.compliance,
                'r_squared': self.current_results.r_squared,
                'is_valid': self.current_results.is_valid,
                'validity_notes': self.current_results.validity_notes,
            }

            # Prepare report data using CTOD E1290-style method
            report_data = KICReportGenerator.prepare_report_data(
                test_info=test_info,
                specimen_data=specimen_data,
                material_data=material_data,
                results=results_dict,
                crack_measurements=self.precrack_measurements if self.precrack_measurements else None
            )

            # Save plot as temp image
            chart_path = Path(filepath).parent / "temp_kic_plot.png"
            self.fig.savefig(chart_path, dpi=150, bbox_inches='tight')

            # Generate report using template
            template_path = PROJECT_ROOT / "templates" / "kic_e399_report_template.docx"
            logo_path = PROJECT_ROOT / "durablersvart.png"

            generator = KICReportGenerator(template_path if template_path.exists() else None)

            # Prepare photo paths list
            photo_paths = [Path(self.crack_photo_path)] if self.crack_photo_path else None

            if template_path.exists():
                # Use template-based generation (CTOD E1290 style)
                output_path = generator.generate_from_template(
                    output_path=Path(filepath),
                    data=report_data,
                    chart_path=chart_path if chart_path.exists() else None,
                    logo_path=logo_path if logo_path.exists() else None,
                    photo_paths=photo_paths
                )
            else:
                # Fall back to scratch generation
                output_path = generator.generate_report(
                    output_path=Path(filepath),
                    test_info=test_info,
                    dimensions=specimen_data,
                    material_props=material_data,
                    results=self.current_results,
                    chart_path=chart_path if chart_path.exists() else None,
                    logo_path=logo_path if logo_path.exists() else None,
                    precrack_measurements=self.precrack_measurements if self.precrack_measurements else None,
                    crack_photo_path=self.crack_photo_path if self.crack_photo_path else None
                )

            # Clean up temp chart
            if chart_path.exists():
                chart_path.unlink()

            messagebox.showinfo("Success", f"Report exported to:\n{filepath}")
            self._update_status(f"Report exported: {Path(filepath).name}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to export report:\n{e}")
            import traceback
            traceback.print_exc()

    def show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About KIC Testing",
            "Durabler - KIC Fracture Toughness Testing\n\n"
            "Standard: ASTM E399\n\n"
            "Determines plane-strain fracture toughness (KIC)\n"
            "using the 5% secant offset method.\n\n"
            "Specimen types:\n"
            "- SE(B) - Single Edge Bend\n"
            "- C(T) - Compact Tension\n\n"
            "All results include measurement uncertainty\n"
            "following GUM methodology (k=2)."
        )

    def run(self):
        """Start the application main loop."""
        self.root.mainloop()


def main():
    """Run KIC test application standalone."""
    app = KICTestApp()
    app.run()


if __name__ == "__main__":
    main()
