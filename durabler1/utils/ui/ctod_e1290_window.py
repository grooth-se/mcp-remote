"""
CTOD Test Application Window (ASTM E1290).

Provides GUI for loading MTS CTOD test data, entering specimen dimensions,
running ASTM E1290 calculations, and displaying results with plots.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
import numpy as np
from PIL import Image, ImageTk

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# Project root for logo path
PROJECT_ROOT = Path(__file__).parent.parent.parent


class CTODTestApp:
    """
    Main Tkinter application for CTOD test analysis (ASTM E1290).

    Parameters
    ----------
    parent_launcher : object, optional
        Reference to parent launcher window to return to on close
    """

    def __init__(self, parent_launcher: Optional[Any] = None):
        self.parent_launcher = parent_launcher

        self.root = tk.Toplevel() if parent_launcher else tk.Tk()
        self.root.title("Durabler - CTOD Test Analysis (ASTM E1290)")
        self.root.geometry("1500x950")

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Data storage
        self.precrack_data = None
        self.ctod_data = None
        self.crack_check_data = None
        self.current_results = None
        self.crack_photos: List[Path] = []

        # Excel import data
        self.precrack_measurements: List[float] = []
        self.final_crack_measurements: List[float] = []
        self.compliance_coefficients: List[float] = []
        self.excel_ctod_results: Dict[str, Any] = {}
        self.excel_data = None

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
        file_menu.add_command(label="Load Pre-crack CSV...", command=self.load_precrack_csv)
        file_menu.add_command(label="Load CTOD Test CSV...", command=self.load_ctod_csv)
        file_menu.add_command(label="Import Excel Data...", command=self.import_excel)
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

        # Data import buttons
        ttk.Button(toolbar, text="Load Pre-crack CSV", command=self.load_precrack_csv).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Load CTOD CSV", command=self.load_ctod_csv).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Import Excel", command=self.import_excel).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Add Photos", command=self.add_photos).pack(
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

        # Right panel (results + plot + photos)
        self._create_right_panel(main_frame)

    def _create_left_panel(self, parent):
        """Create left panel with specimen inputs."""
        left_frame = ttk.Frame(parent, width=450)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_frame.grid_propagate(False)

        # Data Import display - shows imported file names
        files_frame = ttk.LabelFrame(left_frame, text="Data Import", padding=10)
        files_frame.pack(fill=tk.X, pady=5)

        ttk.Label(files_frame, text="Pre-crack CSV:").grid(row=0, column=0, sticky=tk.W, pady=1)
        self.precrack_file_var = tk.StringVar(value="Not loaded")
        ttk.Label(files_frame, textvariable=self.precrack_file_var, foreground='gray',
                  width=35).grid(row=0, column=1, sticky=tk.W, pady=1)

        ttk.Label(files_frame, text="CTOD CSV:").grid(row=1, column=0, sticky=tk.W, pady=1)
        self.ctod_file_var = tk.StringVar(value="Not loaded")
        ttk.Label(files_frame, textvariable=self.ctod_file_var, foreground='gray',
                  width=35).grid(row=1, column=1, sticky=tk.W, pady=1)

        ttk.Label(files_frame, text="Excel Data:").grid(row=2, column=0, sticky=tk.W, pady=1)
        self.excel_file_var = tk.StringVar(value="Not loaded")
        ttk.Label(files_frame, textvariable=self.excel_file_var, foreground='gray',
                  width=35).grid(row=2, column=1, sticky=tk.W, pady=1)

        ttk.Label(files_frame, text="Photos:").grid(row=3, column=0, sticky=tk.W, pady=1)
        self.photos_count_var = tk.StringVar(value="0 photos")
        ttk.Label(files_frame, textvariable=self.photos_count_var, foreground='gray',
                  width=35).grid(row=3, column=1, sticky=tk.W, pady=1)

        files_frame.columnconfigure(1, weight=1)

        # Specimen type selection
        specimen_frame = ttk.LabelFrame(left_frame, text="Specimen Geometry", padding=10)
        specimen_frame.pack(fill=tk.X, pady=5)

        # Specimen type radio buttons
        ttk.Label(specimen_frame, text="Type:", font=('Helvetica', 9, 'bold')).grid(
            row=0, column=0, sticky=tk.W)
        self.specimen_type = tk.StringVar(value="SE(B)")
        ttk.Radiobutton(
            specimen_frame, text="SE(B) Three-Point Bend",
            variable=self.specimen_type, value="SE(B)"
        ).grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(
            specimen_frame, text="C(T) Compact Tension",
            variable=self.specimen_type, value="C(T)"
        ).grid(row=0, column=2, sticky=tk.W)

        # Dimension entry frame
        self.dim_frame = ttk.LabelFrame(left_frame, text="Dimensions (mm)", padding=10)
        self.dim_frame.pack(fill=tk.X, pady=5)
        self.dim_vars: Dict[str, tk.StringVar] = {}
        self._create_dimension_fields()

        # Material properties frame
        mat_frame = ttk.LabelFrame(left_frame, text="Material Properties", padding=10)
        mat_frame.pack(fill=tk.X, pady=5)

        mat_fields = [
            ("σ_ys (Yield strength, MPa):", "yield_strength", "500"),
            ("σ_uts (Ultimate strength, MPa):", "ultimate_strength", "600"),
            ("E (Young's modulus, GPa):", "youngs_modulus", "210"),
            ("ν (Poisson's ratio):", "poissons_ratio", "0.3"),
        ]

        self.mat_vars: Dict[str, tk.StringVar] = {}
        for i, (label, key, default) in enumerate(mat_fields):
            ttk.Label(mat_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=default)
            self.mat_vars[key] = var
            ttk.Entry(mat_frame, textvariable=var, width=12).grid(
                row=i, column=1, sticky=tk.W, pady=2)

        mat_frame.columnconfigure(1, weight=1)

        # Test info frame
        info_frame = ttk.LabelFrame(left_frame, text="Test Information", padding=10)
        info_frame.pack(fill=tk.X, pady=5)

        row = 0
        # Certificate number - Combobox with selection list (at top)
        ttk.Label(info_frame, text="Certificate number:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.certificate_number_var = tk.StringVar()
        cert_frame = ttk.Frame(info_frame)
        cert_frame.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self.cert_combobox = ttk.Combobox(cert_frame, textvariable=self.certificate_number_var, width=18)
        self.cert_combobox.pack(side=tk.LEFT)
        self.cert_combobox.bind('<<ComboboxSelected>>', self._on_certificate_selected)
        ttk.Button(cert_frame, text="↻", width=3,
                  command=self._refresh_certificate_list).pack(side=tk.LEFT, padx=2)
        # Load certificate list
        self._refresh_certificate_list()
        row += 1

        ttk.Label(info_frame, text="Test project:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.test_project_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.test_project_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        ttk.Label(info_frame, text="Customer:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.customer_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.customer_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        ttk.Label(info_frame, text="Customer order:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.customer_order_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.customer_order_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        ttk.Label(info_frame, text="Product/S/N:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.product_sn_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.product_sn_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        ttk.Label(info_frame, text="Specimen ID:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.specimen_id_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.specimen_id_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        ttk.Label(info_frame, text="Location/Orientation:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.location_orientation_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.location_orientation_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        ttk.Label(info_frame, text="Material:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.material_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.material_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        ttk.Label(info_frame, text="Temperature (°C):").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.temperature_var = tk.StringVar(value="23")
        ttk.Entry(info_frame, textvariable=self.temperature_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        ttk.Label(info_frame, text="Test Date:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.date_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.date_var, state='readonly', width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)

        info_frame.columnconfigure(1, weight=1)

    def _create_dimension_fields(self):
        """Create dimension entry fields."""
        for widget in self.dim_frame.winfo_children():
            widget.destroy()

        self.dim_vars = {}

        fields = [
            ("W (Width/Depth):", "W", "25.0"),
            ("B (Thickness):", "B", "12.5"),
            ("B_n (Net thickness):", "B_n", ""),
            ("a₀ (Initial crack length):", "a_0", "12.5"),
            ("S (Span, SE(B) only):", "S", "100.0"),
        ]

        for i, (label, key, default) in enumerate(fields):
            ttk.Label(self.dim_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=default)
            self.dim_vars[key] = var
            ttk.Entry(self.dim_frame, textvariable=var, width=12).grid(
                row=i, column=1, sticky=tk.W, pady=2)

        self.dim_frame.columnconfigure(1, weight=1)

    def _create_right_panel(self, parent):
        """Create right panel with results table, plot, and photo viewer."""
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        # Results table (top)
        results_frame = ttk.LabelFrame(right_frame, text="Results (ASTM E1290)", padding=5)
        results_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        columns = ("parameter", "value", "uncertainty", "unit")
        self.results_tree = ttk.Treeview(
            results_frame, columns=columns, show="headings", height=10
        )

        self.results_tree.heading("parameter", text="Parameter")
        self.results_tree.heading("value", text="Value")
        self.results_tree.heading("uncertainty", text="U (k=2)")
        self.results_tree.heading("unit", text="Unit")

        self.results_tree.column("parameter", width=180)
        self.results_tree.column("value", width=80, anchor=tk.E)
        self.results_tree.column("uncertainty", width=80, anchor=tk.E)
        self.results_tree.column("unit", width=60, anchor=tk.CENTER)

        self.results_tree.pack(fill=tk.BOTH, expand=True)

        # Bottom frame containing plot and photos side by side
        bottom_frame = ttk.Frame(right_frame)
        bottom_frame.grid(row=1, column=0, sticky="nsew")
        bottom_frame.columnconfigure(0, weight=3)  # Plot gets more space
        bottom_frame.columnconfigure(1, weight=1)  # Photos get less space
        bottom_frame.rowconfigure(0, weight=1)

        # Plot (left side of bottom)
        plot_frame = ttk.LabelFrame(bottom_frame, text="Force vs CMOD", padding=5)
        plot_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.fig = Figure(figsize=(5, 3.5), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self._setup_empty_plot()

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()

        # Photos (right side of bottom)
        photos_frame = ttk.LabelFrame(bottom_frame, text="Crack Surface Photos", padding=5)
        photos_frame.grid(row=0, column=1, sticky="nsew")

        self.photos_listbox = tk.Listbox(photos_frame, height=6)
        self.photos_listbox.pack(fill=tk.BOTH, expand=True, pady=2)
        ttk.Button(photos_frame, text="Remove Selected", command=self.remove_photo).pack(
            fill=tk.X, pady=2)

    def _setup_empty_plot(self):
        """Set up empty plot with labels."""
        self.ax.set_xlabel("CMOD (mm)")
        self.ax.set_ylabel("Force (kN)")
        self.ax.set_title("Force vs Crack Mouth Opening Displacement")
        self.ax.grid(True, linestyle='--', alpha=0.7)

    def _create_statusbar(self):
        """Create status bar at bottom."""
        self.statusbar = ttk.Label(
            self.root, text="Ready - Load CTOD test data to begin",
            relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.grid(row=2, column=0, sticky="ew")

    def load_ctod_csv(self):
        """Load main CTOD test CSV file."""
        filepath = filedialog.askopenfilename(
            title="Select CTOD Test CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir="/Users/pjbhb/durabler1/data/Testdataexport"
        )
        if filepath:
            try:
                from ..data_acquisition.ctod_csv_parser import parse_ctod_test_csv

                self.ctod_data = parse_ctod_test_csv(Path(filepath))
                self.date_var.set(self.ctod_data.test_date)
                self.specimen_id_var.set(self.ctod_data.test_run_name)
                self.ctod_file_var.set(Path(filepath).name)

                self._update_status(f"Loaded: {Path(filepath).name}")
                self._plot_raw_data()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load CSV:\n{e}")
                import traceback
                traceback.print_exc()

    def load_precrack_csv(self):
        """Load pre-crack fatigue CSV file."""
        filepath = filedialog.askopenfilename(
            title="Select Pre-crack CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir="/Users/pjbhb/durabler1/data/Testdataexport"
        )
        if filepath:
            try:
                from ..data_acquisition.ctod_csv_parser import parse_ctod_precrack_csv

                self.precrack_data = parse_ctod_precrack_csv(Path(filepath))
                self.precrack_file_var.set(Path(filepath).name)
                self._update_status(f"Loaded pre-crack: {self.precrack_data.total_cycles} cycles")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load pre-crack CSV:\n{e}")

    def load_crack_check_csv(self):
        """Load crack size check CSV file."""
        filepath = filedialog.askopenfilename(
            title="Select Crack Check CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir="/Users/pjbhb/durabler1/data/Testdataexport"
        )
        if filepath:
            try:
                from ..data_acquisition.ctod_csv_parser import parse_ctod_crack_check_csv

                self.crack_check_data = parse_ctod_crack_check_csv(Path(filepath))
                self.crack_check_label.config(
                    text=f"{Path(filepath).name} ({self.crack_check_data.num_sequences} checks)",
                    foreground='green'
                )
                self._update_status(f"Loaded crack check: {self.crack_check_data.num_sequences} sequences")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load crack check CSV:\n{e}")

    def import_excel(self):
        """Import specimen data from Excel file."""
        filepath = filedialog.askopenfilename(
            title="Select Excel Data File",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
            initialdir="/Users/pjbhb/durabler1/data/Testdataexport"
        )
        if filepath:
            try:
                from ..data_acquisition.ctod_excel_parser import parse_ctod_excel

                data = parse_ctod_excel(Path(filepath))

                # Populate fields
                self.specimen_type.set(data.specimen_type)
                self.dim_vars['W'].set(str(data.W))
                self.dim_vars['B'].set(str(data.B))
                self.dim_vars['B_n'].set(str(data.B_n))
                self.dim_vars['a_0'].set(str(data.a_0))
                self.dim_vars['S'].set(str(data.S))

                self.mat_vars['yield_strength'].set(str(data.yield_strength))
                self.mat_vars['ultimate_strength'].set(str(data.ultimate_strength))
                self.mat_vars['youngs_modulus'].set(str(data.youngs_modulus))
                self.mat_vars['poissons_ratio'].set(str(data.poissons_ratio))

                self.specimen_id_var.set(data.specimen_id)
                self.material_var.set(data.material)
                self.temperature_var.set(str(data.test_temperature))

                # Store precrack and final crack measurements
                self.precrack_measurements = data.precrack_measurements
                self.final_crack_measurements = data.final_crack_measurements
                self.compliance_coefficients = data.compliance_coefficients
                self.excel_ctod_results = data.ctod_results
                self.excel_data = data

                # Update file display
                self.excel_file_var.set(Path(filepath).name)

                self._update_status(f"Imported Excel data: {Path(filepath).name}")
                messagebox.showinfo("Success", f"Imported specimen data from:\n{filepath}")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to import Excel:\n{e}")
                import traceback
                traceback.print_exc()

    def add_photos(self):
        """Add crack surface photos."""
        filepaths = filedialog.askopenfilenames(
            title="Select Crack Surface Photos",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp"), ("All files", "*.*")]
        )
        for filepath in filepaths:
            self.crack_photos.append(Path(filepath))
            self.photos_listbox.insert(tk.END, Path(filepath).name)
        # Update photos count display
        count = len(self.crack_photos)
        self.photos_count_var.set(f"{count} photo{'s' if count != 1 else ''}")

    def remove_photo(self):
        """Remove selected photo from list."""
        selection = self.photos_listbox.curselection()
        if selection:
            idx = selection[0]
            self.photos_listbox.delete(idx)
            del self.crack_photos[idx]
            # Update photos count display
            count = len(self.crack_photos)
            self.photos_count_var.set(f"{count} photo{'s' if count != 1 else ''}")

    def _plot_raw_data(self):
        """Plot raw Force vs CMOD data."""
        if self.ctod_data is None:
            return

        self.ax.clear()
        self.ax.plot(
            self.ctod_data.cod,
            self.ctod_data.force,
            'b-', linewidth=0.8, label='Force vs CMOD'
        )
        self.ax.set_xlabel("CMOD (mm)")
        self.ax.set_ylabel("Force (kN)")
        self.ax.set_title(f"Raw Data: {self.ctod_data.test_run_name}")
        self.ax.grid(True, linestyle='--', alpha=0.7)
        self.ax.legend(loc='lower right')
        self.fig.tight_layout()
        self.canvas.draw()

    def run_analysis(self):
        """Run full CTOD analysis."""
        if self.ctod_data is None:
            messagebox.showwarning("Warning", "Please load CTOD test data first")
            return

        try:
            from ..analysis.ctod_calculations import CTODAnalyzer
            from ..models.ctod_specimen import CTODSpecimen, CTODMaterial

            self._update_status("Running analysis...")

            # Build specimen from input fields
            W = float(self.dim_vars['W'].get())
            B = float(self.dim_vars['B'].get())
            B_n_str = self.dim_vars['B_n'].get()
            B_n = float(B_n_str) if B_n_str else B
            a_0 = float(self.dim_vars['a_0'].get())
            S = float(self.dim_vars['S'].get())

            specimen = CTODSpecimen(
                specimen_id=self.specimen_id_var.get(),
                specimen_type=self.specimen_type.get(),
                W=W,
                B=B,
                B_n=B_n,
                a_0=a_0,
                S=S,
                material=self.material_var.get()
            )

            # Build material properties
            material = CTODMaterial(
                yield_strength=float(self.mat_vars['yield_strength'].get()),
                ultimate_strength=float(self.mat_vars['ultimate_strength'].get()),
                youngs_modulus=float(self.mat_vars['youngs_modulus'].get()),
                poissons_ratio=float(self.mat_vars['poissons_ratio'].get())
            )

            # Run analysis
            analyzer = CTODAnalyzer()
            self.current_results = analyzer.run_analysis(
                force=self.ctod_data.force,
                cmod=self.ctod_data.cod,
                specimen=specimen,
                material=material
            )

            # Store specimen and material for report
            self.current_results['specimen'] = specimen
            self.current_results['material'] = material

            # Update results display
            self._display_results()

            # Plot with annotations
            self._plot_ctod_curve()

            self._update_status("Analysis complete")

        except ValueError as e:
            messagebox.showerror("Analysis Error", f"Invalid input:\n{e}")
        except Exception as e:
            messagebox.showerror("Analysis Error", f"Analysis failed:\n{e}")
            import traceback
            traceback.print_exc()

    def _display_results(self):
        """Update results treeview."""
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        if not self.current_results:
            return

        # Section header helper
        def add_section(title):
            self.results_tree.insert("", tk.END, values=(f"── {title} ──", "", "", ""),
                                    tags=('section',))

        # Configure section tag
        self.results_tree.tag_configure('section', background='#E0E0E0')
        self.results_tree.tag_configure('valid', foreground='green')
        self.results_tree.tag_configure('invalid', foreground='red')

        # === Test Results Section ===
        add_section("Test Results")

        results_list = [
            ("P_max (Max Force)", self.current_results.get('P_max')),
            ("CMOD at P_max", self.current_results.get('CMOD_max')),
            ("K at P_max", self.current_results.get('K_max')),
            ("a₀/W ratio", self.current_results.get('a_W_ratio')),
        ]

        for name, result in results_list:
            if result is not None:
                self.results_tree.insert("", tk.END, values=(
                    name,
                    f"{result.value:.4f}" if result.value < 1 else f"{result.value:.2f}",
                    f"±{result.uncertainty:.4f}" if result.uncertainty < 0.1 else f"±{result.uncertainty:.2f}",
                    result.unit
                ))

        # === CTOD Results Section (E1290) ===
        add_section("CTOD Results (E1290)")

        for ctod_key in ['delta_c', 'delta_u', 'delta_m']:
            ctod_result = self.current_results.get(ctod_key)
            if ctod_result is not None:
                label = {
                    'delta_c': 'δc (CTOD at cleavage)',
                    'delta_u': 'δu (CTOD with growth)',
                    'delta_m': 'δm (CTOD at max force)'
                }[ctod_key]
                self.results_tree.insert("", tk.END, values=(
                    label,
                    f"{ctod_result.ctod_value.value:.4f}",
                    f"±{ctod_result.ctod_value.uncertainty:.4f}",
                    ctod_result.ctod_value.unit
                ))

        # === CTOD Results Section (BS 7448) ===
        add_section("CTOD Results (BS 7448)")

        delta_bs7448 = self.current_results.get('delta_m_bs7448')
        if delta_bs7448 is not None:
            self.results_tree.insert("", tk.END, values=(
                "δm (CTOD at max force)",
                f"{delta_bs7448.value:.4f}",
                f"±{delta_bs7448.uncertainty:.4f}",
                delta_bs7448.unit
            ))

        # === Compliance Section ===
        add_section("Compliance (E1290)")

        compliance = self.current_results.get('compliance', 0)
        if compliance > 0:
            self.results_tree.insert("", tk.END, values=(
                "Elastic Compliance",
                f"{compliance:.6f}",
                "-",
                "mm/kN"
            ))

            # Calculate and show Vp at max force
            if self.ctod_data is not None:
                max_idx = np.argmax(self.ctod_data.force)
                P_max = self.ctod_data.force[max_idx]
                V_max = self.ctod_data.cod[max_idx]
                Vp = V_max - compliance * P_max
                self.results_tree.insert("", tk.END, values=(
                    "Vp (Plastic CMOD)",
                    f"{Vp:.4f}",
                    "-",
                    "mm"
                ))

        # === Precrack Measurements Section ===
        if hasattr(self, 'precrack_measurements') and self.precrack_measurements:
            add_section("Precrack Measurements (9-point)")

            for i, val in enumerate(self.precrack_measurements, 1):
                self.results_tree.insert("", tk.END, values=(
                    f"a{i}",
                    f"{val:.3f}",
                    "-",
                    "mm"
                ))

            # Average
            if hasattr(self, 'excel_data') and self.excel_data:
                avg = self.excel_data.crack_length_average
                self.results_tree.insert("", tk.END, values=(
                    "Average (E1290)",
                    f"{avg:.3f}",
                    "-",
                    "mm"
                ))

        # === Final Crack Measurements Section ===
        if hasattr(self, 'final_crack_measurements') and self.final_crack_measurements:
            add_section("Final Crack Measurements")

            for i, val in enumerate(self.final_crack_measurements, 1):
                self.results_tree.insert("", tk.END, values=(
                    f"af{i}",
                    f"{val:.3f}",
                    "-",
                    "mm"
                ))

            if hasattr(self, 'excel_data') and self.excel_data:
                avg = self.excel_data.final_crack_length_average
                self.results_tree.insert("", tk.END, values=(
                    "Average (E1290)",
                    f"{avg:.3f}",
                    "-",
                    "mm"
                ))

        # === Validity Section ===
        add_section("Validity")
        is_valid = self.current_results.get('is_valid', False)
        self.results_tree.insert("", tk.END, values=(
            "Test Validity",
            "VALID" if is_valid else "INVALID",
            "",
            ""
        ), tags=('valid' if is_valid else 'invalid',))

    def _plot_ctod_curve(self):
        """Plot Force vs CMOD with CTOD annotations."""
        if self.ctod_data is None or self.current_results is None:
            return

        self.ax.clear()

        force = self.ctod_data.force
        cmod = self.ctod_data.cod

        # Main curve - dark red
        self.ax.plot(cmod, force, color='darkred', linewidth=1, label='Force vs CMOD')

        # Elastic compliance line through max force point
        # Per E1290: line has initial elastic slope, passes through (P_max, V_max)
        compliance = self.current_results.get('compliance', 0)
        if compliance > 0:
            # Get max force point
            max_idx = np.argmax(force)
            P_max = force[max_idx]
            V_max = cmod[max_idx]

            # Calculate Vp (plastic CMOD) = intercept with CMOD axis
            Vp = V_max - compliance * P_max

            # Draw line from (Vp, 0) through (V_max, P_max)
            # Line equation: P = (V - Vp) / compliance
            elastic_cmod = np.linspace(max(0, Vp), V_max * 1.05, 100)
            elastic_force = (elastic_cmod - Vp) / compliance
            elastic_force = np.clip(elastic_force, 0, None)

            # Elastic line - black, dashed
            self.ax.plot(elastic_cmod, elastic_force, color='black', linestyle='--',
                        linewidth=1.5, label=f'Elastic line (Vp={Vp:.3f} mm)')

            # Mark Vp on the CMOD axis - grey, dotted
            if Vp > 0:
                self.ax.axvline(x=Vp, color='grey', linestyle=':', linewidth=1, alpha=0.7)
                self.ax.plot(Vp, 0, 'o', color='black', markersize=6,
                            fillstyle='none', markeredgewidth=1.5, label=f'Vp = {Vp:.3f} mm')

        # Mark CTOD points - black rings
        labels = {'delta_c': 'δc', 'delta_u': 'δu', 'delta_m': 'δm'}

        for ctod_key in ['delta_c', 'delta_u', 'delta_m']:
            ctod_result = self.current_results.get(ctod_key)
            if ctod_result is not None:
                self.ax.plot(
                    ctod_result.cmod.value,
                    ctod_result.force.value,
                    'o',
                    color='black',
                    markersize=7,
                    fillstyle='none',
                    markeredgewidth=1.5,
                    label=f"{labels[ctod_key]} = {ctod_result.ctod_value.value:.3f} mm"
                )

        # Max force line - grey, dash-dot
        P_max = self.current_results.get('P_max')
        if P_max:
            self.ax.axhline(y=P_max.value, color='grey', linestyle='-.', linewidth=1,
                          label=f'P_max = {P_max.value:.1f} kN')

        self.ax.set_xlabel("CMOD (mm)")
        self.ax.set_ylabel("Force (kN)")
        self.ax.set_title(f"CTOD Analysis: {self.specimen_id_var.get()}")
        self.ax.legend(loc='lower right', fontsize=8)
        self.ax.grid(True, linestyle='--', alpha=0.4)
        self.ax.set_xlim(left=0)
        self.ax.set_ylim(bottom=0)

        self.fig.tight_layout()
        self.canvas.draw()

    def clear_results(self):
        """Clear all results and reset plot."""
        self.current_results = None

        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        if self.ctod_data:
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
                    for key, result in self.current_results.items():
                        if hasattr(result, 'value'):
                            f.write(f"{key},{result.value},{result.uncertainty},{result.unit}\n")

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
            title="Save CTOD Report",
            initialfile=f"CTOD_Report_{self.specimen_id_var.get() or 'Unknown'}.docx"
        )

        if not filepath:
            return

        try:
            from utils.reporting.ctod_word_report import CTODReportGenerator

            # Template path
            template_path = PROJECT_ROOT / "templates" / "ctod_e1290_report_template.docx"
            if not template_path.exists():
                messagebox.showerror("Error", f"Template not found: {template_path}")
                return

            # Prepare test info
            test_info = {
                'test_project': self.test_project_var.get(),
                'customer': self.customer_var.get(),
                'customer_order': self.customer_order_var.get(),
                'product_sn': self.product_sn_var.get(),
                'specimen_id': self.specimen_id_var.get(),
                'location_orientation': self.location_orientation_var.get(),
                'material': self.material_var.get(),
                'certificate_number': self.certificate_number_var.get(),
                'test_date': self.date_var.get(),
                'temperature': self.temperature_var.get(),
            }

            # Prepare specimen data
            specimen_data = {
                'specimen_type': self.specimen_type.get(),
                'W': self.dim_vars['W'].get(),
                'B': self.dim_vars['B'].get(),
                'B_n': self.dim_vars['B_n'].get() or self.dim_vars['B'].get(),
                'a_0': self.dim_vars['a_0'].get(),
                'S': self.dim_vars['S'].get(),
                'a_f': '-',
                'notch_type': 'Fatigue pre-crack',
            }

            # Prepare material data
            material_data = {
                'yield_strength': self.mat_vars['yield_strength'].get(),
                'ultimate_strength': self.mat_vars['ultimate_strength'].get(),
                'youngs_modulus': self.mat_vars['youngs_modulus'].get(),
                'poissons_ratio': self.mat_vars['poissons_ratio'].get(),
            }

            # Get crack measurements if available
            crack_measurements = None
            if hasattr(self, 'precrack_measurements') and self.precrack_measurements:
                crack_measurements = self.precrack_measurements

            # Prepare report data
            report_data = CTODReportGenerator.prepare_report_data(
                test_info=test_info,
                specimen_data=specimen_data,
                material_data=material_data,
                results=self.current_results,
                crack_measurements=crack_measurements
            )

            # Save chart if plot exists
            chart_path = None
            if hasattr(self, 'fig') and self.fig:
                chart_path = Path(filepath).parent / "temp_ctod_chart.png"
                self.fig.savefig(chart_path, dpi=150, bbox_inches='tight')

            # Logo path
            logo_path = PROJECT_ROOT / "templates" / "logo.png"
            if not logo_path.exists():
                logo_path = None

            # Generate report
            generator = CTODReportGenerator(template_path)
            output_path = generator.generate_report(
                output_path=Path(filepath),
                data=report_data,
                chart_path=chart_path,
                logo_path=logo_path,
                photo_paths=self.crack_photos
            )

            # Clean up temp chart
            if chart_path and chart_path.exists():
                chart_path.unlink()

            self._update_status(f"Report saved: {output_path}")
            messagebox.showinfo("Success", f"Report saved to:\n{output_path}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report:\n{str(e)}")

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
        cert_number = self.certificate_number_var.get()
        if not cert_number:
            return

        try:
            from utils.database.certificate_db import CertificateDatabase
            db = CertificateDatabase()
            cert = db.get_certificate_by_string(cert_number)

            if cert:
                # Populate fields from certificate
                self.test_project_var.set(cert.test_project or "")
                self.customer_var.set(cert.customer or "")
                self.customer_order_var.set(cert.customer_order or "")
                self.product_sn_var.set(cert.product_sn or "")
                self.specimen_id_var.set(cert.specimen_id or "")
                self.location_orientation_var.set(cert.location_orientation or "")
                self.material_var.set(cert.material or "")
                self.temperature_var.set(cert.temperature or "23")

                self._update_status(f"Loaded certificate: {cert_number}")
        except Exception as e:
            self._update_status(f"Error loading certificate: {e}")

    def show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About Durabler CTOD",
            "Durabler - CTOD Test Analysis\n\n"
            "Version: 0.1.0\n"
            "Standard: ASTM E1290\n\n"
            "ISO 17025 compliant analysis system\n"
            "for mechanical testing laboratories.\n\n"
            "Calculations include:\n"
            "- CTOD by plastic hinge model\n"
            "- Stress intensity factor K\n"
            "- δc, δu, δm determination\n"
            "- Validity checks per E1290\n\n"
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
    app = CTODTestApp()
    app.run()


if __name__ == "__main__":
    main()
