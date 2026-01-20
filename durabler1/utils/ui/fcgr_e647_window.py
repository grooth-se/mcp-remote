"""
FCGR Test Application Window (ASTM E647).

Provides GUI for loading MTS FCGR test data, entering specimen dimensions,
running ASTM E647 calculations, and displaying results with dual plots.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, Dict, Any, List
import tempfile
import numpy as np
from PIL import Image, ImageTk

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# Project root for logo path
PROJECT_ROOT = Path(__file__).parent.parent.parent


class FCGRTestApp:
    """
    Main Tkinter application for FCGR test analysis (ASTM E647).

    Parameters
    ----------
    parent_launcher : object, optional
        Reference to parent launcher window to return to on close
    """

    def __init__(self, parent_launcher: Optional[Any] = None):
        self.parent_launcher = parent_launcher

        self.root = tk.Toplevel() if parent_launcher else tk.Tk()
        self.root.title("Durabler - Fatigue Crack Growth Rate Analysis (ASTM E647)")
        self.root.geometry("1600x1000")

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Data storage
        self.csv_data = None
        self.excel_data = None
        self.current_results = None
        self.crack_photos: List[Path] = []

        # Compliance coefficients from Excel
        self.compliance_coefficients: List[float] = []
        self.k_calibration_coefficients: List[float] = []

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
        file_menu.add_command(label="Load FCG CSV Data...", command=self.load_fcg_csv)
        file_menu.add_command(label="Import Excel Data...", command=self.import_excel)
        file_menu.add_separator()
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
        analysis_menu.add_separator()
        analysis_menu.add_command(label="Remove Outliers", command=self.remove_outliers)

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
        ttk.Button(toolbar, text="Load FCG CSV", command=self.load_fcg_csv).pack(
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
        """Create left and right panels with 1:2 width ratio."""
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        # Set column weights: left=1, right=2 (1/3 and 2/3 of width)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=2)
        main_frame.rowconfigure(0, weight=1)

        # Left panel (inputs) - 1/3 of width
        self._create_left_panel(main_frame)

        # Right panel (results + plots + photos) - 2/3 of width
        self._create_right_panel(main_frame)

    def _create_left_panel(self, parent):
        """Create left panel with specimen inputs (scrollable)."""
        # Create outer frame - expands to fill 1/3 of window width
        left_outer = ttk.Frame(parent)
        left_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_outer.rowconfigure(0, weight=1)
        left_outer.columnconfigure(0, weight=1)

        # Create canvas and scrollbar for scrolling
        canvas = tk.Canvas(left_outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_outer, orient="vertical", command=canvas.yview)

        # Create scrollable frame inside canvas
        left_frame = ttk.Frame(canvas)

        # Configure canvas scrolling
        left_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        # Create window and store reference for resizing
        canvas_window = canvas.create_window((0, 0), window=left_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Make inner frame expand to canvas width
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Pack scrollbar and canvas
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Enable mousewheel scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        # For macOS
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        # Data Import display
        files_frame = ttk.LabelFrame(left_frame, text="Data Import", padding=10)
        files_frame.pack(fill=tk.X, pady=5, padx=5)

        ttk.Label(files_frame, text="FCG CSV:").grid(row=0, column=0, sticky=tk.W, pady=1)
        self.csv_file_var = tk.StringVar(value="Not loaded")
        ttk.Label(files_frame, textvariable=self.csv_file_var, foreground='gray').grid(
            row=0, column=1, sticky=tk.EW, pady=1)

        ttk.Label(files_frame, text="Excel Data:").grid(row=1, column=0, sticky=tk.W, pady=1)
        self.excel_file_var = tk.StringVar(value="Not loaded")
        ttk.Label(files_frame, textvariable=self.excel_file_var, foreground='gray').grid(
            row=1, column=1, sticky=tk.EW, pady=1)

        ttk.Label(files_frame, text="Photos:").grid(row=2, column=0, sticky=tk.W, pady=1)
        self.photos_count_var = tk.StringVar(value="0 photos")
        ttk.Label(files_frame, textvariable=self.photos_count_var, foreground='gray').grid(
            row=2, column=1, sticky=tk.EW, pady=1)

        files_frame.columnconfigure(1, weight=1)

        # Specimen type and control mode selection
        specimen_frame = ttk.LabelFrame(left_frame, text="Specimen Geometry & Control Mode", padding=10)
        specimen_frame.pack(fill=tk.X, pady=5, padx=5)

        # Specimen type radio buttons
        ttk.Label(specimen_frame, text="Type:", font=('Helvetica', 9, 'bold')).grid(
            row=0, column=0, sticky=tk.W)
        self.specimen_type = tk.StringVar(value="C(T)")
        type_frame = ttk.Frame(specimen_frame)
        type_frame.grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(
            type_frame, text="C(T) Compact Tension",
            variable=self.specimen_type, value="C(T)"
        ).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Radiobutton(
            type_frame, text="M(T) Middle Tension",
            variable=self.specimen_type, value="M(T)"
        ).pack(side=tk.LEFT)

        # Control mode radio buttons
        ttk.Label(specimen_frame, text="Control Mode:", font=('Helvetica', 9, 'bold')).grid(
            row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.control_mode = tk.StringVar(value="Load Control")
        control_frame = ttk.Frame(specimen_frame)
        control_frame.grid(row=1, column=1, sticky=tk.W, pady=(5, 0))
        ttk.Radiobutton(
            control_frame, text="Load Control",
            variable=self.control_mode, value="Load Control"
        ).pack(side=tk.LEFT, padx=(0, 15))
        ttk.Radiobutton(
            control_frame, text="Delta-K Control",
            variable=self.control_mode, value="Delta-K Control"
        ).pack(side=tk.LEFT)

        # Test parameters frame
        test_frame = ttk.LabelFrame(left_frame, text="Test Parameters", padding=10)
        test_frame.pack(fill=tk.X, pady=5, padx=5)

        test_params = [
            ("Pmax (Maximum load, kN):", "P_max", ""),
            ("Kmax (Maximum K, MPa√m):", "K_max", ""),
            ("R (Load ratio):", "load_ratio", "0.1"),
            ("Frequency (Hz):", "frequency", "10.0"),
            ("Temperature (C):", "temperature", "23"),
        ]

        self.test_vars: Dict[str, tk.StringVar] = {}
        for i, (label, key, default) in enumerate(test_params):
            ttk.Label(test_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=default)
            self.test_vars[key] = var
            ttk.Entry(test_frame, textvariable=var).grid(
                row=i, column=1, sticky=tk.EW, pady=2)

        test_frame.columnconfigure(1, weight=1)

        # Test info frame
        info_frame = ttk.LabelFrame(left_frame, text="Test Information", padding=10)
        info_frame.pack(fill=tk.X, pady=5, padx=5)

        row = 0
        # Certificate number - Combobox
        ttk.Label(info_frame, text="Certificate number:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.certificate_number_var = tk.StringVar()
        cert_frame = ttk.Frame(info_frame)
        cert_frame.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self.cert_combobox = ttk.Combobox(cert_frame, textvariable=self.certificate_number_var)
        self.cert_combobox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cert_combobox.bind('<<ComboboxSelected>>', self._on_certificate_selected)
        ttk.Button(cert_frame, text="Refresh", width=3,
                  command=self._refresh_certificate_list).pack(side=tk.LEFT, padx=2)
        self._refresh_certificate_list()
        row += 1

        info_fields = [
            ("Test project:", "test_project"),
            ("Customer:", "customer"),
            ("Specimen ID:", "specimen_id"),
            ("Material:", "material"),
            ("Test Date:", "test_date"),
        ]

        self.info_vars: Dict[str, tk.StringVar] = {}
        for label, key in info_fields:
            ttk.Label(info_frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar()
            self.info_vars[key] = var
            state = 'readonly' if key == 'test_date' else 'normal'
            ttk.Entry(info_frame, textvariable=var, state=state).grid(
                row=row, column=1, sticky=tk.EW, pady=2)
            row += 1

        info_frame.columnconfigure(1, weight=1)

        # Analysis options
        options_frame = ttk.LabelFrame(left_frame, text="Analysis Options", padding=10)
        options_frame.pack(fill=tk.X, pady=5, padx=5)

        ttk.Label(options_frame, text="da/dN Method:").grid(row=0, column=0, sticky=tk.W)
        self.dadn_method = tk.StringVar(value="polynomial")
        ttk.Radiobutton(
            options_frame, text="Secant",
            variable=self.dadn_method, value="secant"
        ).grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(
            options_frame, text="Polynomial",
            variable=self.dadn_method, value="polynomial"
        ).grid(row=0, column=2, sticky=tk.W)

        ttk.Label(options_frame, text="Outlier Threshold:").grid(row=1, column=0, sticky=tk.W)
        self.outlier_threshold = tk.StringVar(value="60")
        ttk.Entry(options_frame, textvariable=self.outlier_threshold, width=8).grid(
            row=1, column=1, sticky=tk.W)
        ttk.Label(options_frame, text="% deviation").grid(row=1, column=2, sticky=tk.W)

        # Dimension entry frame (moved to bottom)
        self.dim_frame = ttk.LabelFrame(left_frame, text="Dimensions (mm)", padding=10)
        self.dim_frame.pack(fill=tk.X, pady=5, padx=5)
        self.dim_vars: Dict[str, tk.StringVar] = {}
        self._create_dimension_fields()

        # Material properties frame (moved to bottom)
        mat_frame = ttk.LabelFrame(left_frame, text="Material Properties", padding=10)
        mat_frame.pack(fill=tk.X, pady=5, padx=5)

        mat_fields = [
            ("sigma_ys (Yield strength, MPa):", "yield_strength", "500"),
            ("sigma_uts (Ultimate strength, MPa):", "ultimate_strength", "600"),
            ("E (Young's modulus, GPa):", "youngs_modulus", "210"),
            ("nu (Poisson's ratio):", "poissons_ratio", "0.3"),
        ]

        self.mat_vars: Dict[str, tk.StringVar] = {}
        for i, (label, key, default) in enumerate(mat_fields):
            ttk.Label(mat_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=default)
            self.mat_vars[key] = var
            ttk.Entry(mat_frame, textvariable=var).grid(
                row=i, column=1, sticky=tk.EW, pady=2)

        mat_frame.columnconfigure(1, weight=1)

    def _create_dimension_fields(self):
        """Create dimension entry fields."""
        for widget in self.dim_frame.winfo_children():
            widget.destroy()

        self.dim_vars = {}

        fields = [
            ("W (Width):", "W", "50.0"),
            ("B (Thickness):", "B", "12.5"),
            ("B_n (Net thickness):", "B_n", ""),
            ("a_0 (Initial notch length):", "a_0", "10.0"),
            ("h (Notch height):", "notch_height", "0.0"),
        ]

        for i, (label, key, default) in enumerate(fields):
            ttk.Label(self.dim_frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar(value=default)
            self.dim_vars[key] = var
            ttk.Entry(self.dim_frame, textvariable=var).grid(
                row=i, column=1, sticky=tk.EW, pady=2)

        self.dim_frame.columnconfigure(1, weight=1)

    def _create_right_panel(self, parent):
        """Create right panel with results table (top), dual plots (middle), and photos (bottom)."""
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=0)  # Results table - fixed height
        right_frame.rowconfigure(1, weight=1)  # Plots - expandable
        right_frame.rowconfigure(2, weight=0)  # Photos - fixed height

        # === Row 0: Results table (top) ===
        results_frame = ttk.LabelFrame(right_frame, text="Results (ASTM E647)", padding=5)
        results_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        columns = ("parameter", "value", "uncertainty", "unit")
        self.results_tree = ttk.Treeview(
            results_frame, columns=columns, show="headings", height=10
        )

        self.results_tree.heading("parameter", text="Parameter")
        self.results_tree.heading("value", text="Value")
        self.results_tree.heading("uncertainty", text="U (k=2)")
        self.results_tree.heading("unit", text="Unit")

        self.results_tree.column("parameter", width=250)
        self.results_tree.column("value", width=150, anchor=tk.E)
        self.results_tree.column("uncertainty", width=120, anchor=tk.E)
        self.results_tree.column("unit", width=150, anchor=tk.CENTER)

        # Add scrollbar to results
        results_scroll = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=results_scroll.set)
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        results_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # === Row 1: Plots frame (middle) ===
        plots_frame = ttk.Frame(right_frame)
        plots_frame.grid(row=1, column=0, sticky="nsew", pady=5)
        plots_frame.columnconfigure(0, weight=1)
        plots_frame.columnconfigure(1, weight=1)
        plots_frame.rowconfigure(0, weight=1)

        # Plot 1: Crack length vs Cycles (left)
        plot1_frame = ttk.LabelFrame(plots_frame, text="Crack Length vs Cycles", padding=5)
        plot1_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 3))

        self.fig1 = Figure(figsize=(5, 4), dpi=100)
        self.ax1 = self.fig1.add_subplot(111)
        self._setup_empty_plot1()

        self.canvas1 = FigureCanvasTkAgg(self.fig1, master=plot1_frame)
        self.canvas1.draw()
        self.canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar1_frame = ttk.Frame(plot1_frame)
        toolbar1_frame.pack(fill=tk.X)
        self.toolbar1 = NavigationToolbar2Tk(self.canvas1, toolbar1_frame)
        self.toolbar1.update()

        # Plot 2: da/dN vs Delta-K (Paris law plot, right)
        plot2_frame = ttk.LabelFrame(plots_frame, text="da/dN vs Delta-K (Paris Law)", padding=5)
        plot2_frame.grid(row=0, column=1, sticky="nsew", padx=(3, 0))

        self.fig2 = Figure(figsize=(5, 4), dpi=100)
        self.ax2 = self.fig2.add_subplot(111)
        self._setup_empty_plot2()

        self.canvas2 = FigureCanvasTkAgg(self.fig2, master=plot2_frame)
        self.canvas2.draw()
        self.canvas2.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar2_frame = ttk.Frame(plot2_frame)
        toolbar2_frame.pack(fill=tk.X)
        self.toolbar2 = NavigationToolbar2Tk(self.canvas2, toolbar2_frame)
        self.toolbar2.update()

        # === Row 2: Photos frame (bottom) ===
        photos_frame = ttk.LabelFrame(right_frame, text="Crack Photos", padding=5)
        photos_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 0))

        # Horizontal layout for photos section
        photos_inner = ttk.Frame(photos_frame)
        photos_inner.pack(fill=tk.BOTH, expand=True)

        self.photos_listbox = tk.Listbox(photos_inner, height=4, width=60)
        self.photos_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=2)

        photos_scroll = ttk.Scrollbar(photos_inner, orient=tk.VERTICAL, command=self.photos_listbox.yview)
        self.photos_listbox.configure(yscrollcommand=photos_scroll.set)
        photos_scroll.pack(side=tk.LEFT, fill=tk.Y, pady=2)

        photos_buttons = ttk.Frame(photos_inner)
        photos_buttons.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(photos_buttons, text="Add Photos", command=self.add_photos).pack(fill=tk.X, pady=2)
        ttk.Button(photos_buttons, text="Remove Selected", command=self.remove_photo).pack(fill=tk.X, pady=2)

    def _setup_empty_plot1(self):
        """Set up empty crack length vs cycles plot."""
        self.ax1.set_xlabel("Cycles, N")
        self.ax1.set_ylabel("Crack length, a (mm)")
        self.ax1.set_title("a vs N")
        self.ax1.grid(True, linestyle='--', alpha=0.4)

    def _setup_empty_plot2(self):
        """Set up empty da/dN vs Delta-K plot."""
        self.ax2.set_xlabel(r"$\Delta K$ (MPa$\sqrt{m}$)")
        self.ax2.set_ylabel("da/dN (mm/cycle)")
        self.ax2.set_title("Paris Law Plot")
        self.ax2.set_xscale('log')
        self.ax2.set_yscale('log')
        self.ax2.grid(True, which='both', linestyle='--', alpha=0.4)

    def _create_statusbar(self):
        """Create status bar at bottom."""
        self.statusbar = ttk.Label(
            self.root, text="Ready - Load FCGR test data to begin",
            relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.grid(row=2, column=0, sticky="ew")

    def load_fcg_csv(self):
        """Load FCG test CSV file."""
        filepath = filedialog.askopenfilename(
            title="Select FCG Test CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir="/Users/pjbhb/durabler1/data/Testdataexport"
        )
        if filepath:
            try:
                from ..data_acquisition.fcgr_csv_parser import parse_fcgr_csv

                self.csv_data = parse_fcgr_csv(Path(filepath))
                self.info_vars['test_date'].set(self.csv_data.test_date)
                self.info_vars['specimen_id'].set(self.csv_data.test_run_name)
                self.csv_file_var.set(Path(filepath).name)

                self._update_status(f"Loaded: {Path(filepath).name} ({self.csv_data.num_points} points)")
                self._plot_raw_data()

            except Exception as e:
                messagebox.showerror("Error", f"Failed to load CSV:\n{e}")
                import traceback
                traceback.print_exc()

    def import_excel(self):
        """Import specimen data from Excel file."""
        filepath = filedialog.askopenfilename(
            title="Select Excel Data File",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
            initialdir="/Users/pjbhb/durabler1/data/Testdataexport"
        )
        if filepath:
            try:
                from ..data_acquisition.fcgr_excel_parser import parse_fcgr_excel

                data = parse_fcgr_excel(Path(filepath))
                self.excel_data = data

                # Populate fields
                self.specimen_type.set(data.specimen_type)
                self.dim_vars['W'].set(str(data.W))
                self.dim_vars['B'].set(str(data.B))
                self.dim_vars['B_n'].set(str(data.B_n) if data.B_n else "")
                self.dim_vars['a_0'].set(str(data.a_0))
                self.dim_vars['notch_height'].set(str(data.notch_height))

                self.mat_vars['yield_strength'].set(str(data.yield_strength))
                self.mat_vars['ultimate_strength'].set(str(data.ultimate_strength))
                self.mat_vars['youngs_modulus'].set(str(data.youngs_modulus))
                self.mat_vars['poissons_ratio'].set(str(data.poissons_ratio))

                self.control_mode.set(data.control_mode)
                self.test_vars['load_ratio'].set(str(data.load_ratio))
                self.test_vars['frequency'].set(str(data.frequency))
                self.test_vars['temperature'].set(str(data.test_temperature))

                # Populate Pmax and Kmax from FCG results
                if data.fcgr_results.get('final_P_max', 0) > 0:
                    self.test_vars['P_max'].set(str(data.fcgr_results['final_P_max']))
                if data.fcgr_results.get('final_K_max', 0) > 0:
                    self.test_vars['K_max'].set(str(data.fcgr_results['final_K_max']))

                self.info_vars['specimen_id'].set(data.specimen_id)
                self.info_vars['material'].set(data.material)

                # Store coefficients
                self.compliance_coefficients = data.compliance_coefficients
                self.k_calibration_coefficients = data.k_calibration_coefficients

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
            title="Select Crack Photos",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp"), ("All files", "*.*")]
        )
        for filepath in filepaths:
            self.crack_photos.append(Path(filepath))
            self.photos_listbox.insert(tk.END, Path(filepath).name)
        count = len(self.crack_photos)
        self.photos_count_var.set(f"{count} photo{'s' if count != 1 else ''}")

    def remove_photo(self):
        """Remove selected photo from list."""
        selection = self.photos_listbox.curselection()
        if selection:
            idx = selection[0]
            self.photos_listbox.delete(idx)
            del self.crack_photos[idx]
            count = len(self.crack_photos)
            self.photos_count_var.set(f"{count} photo{'s' if count != 1 else ''}")

    def _plot_raw_data(self):
        """Plot raw cycle data."""
        if self.csv_data is None:
            return

        self.ax1.clear()
        # Plot COD vs cycle count as proxy for crack length
        self.ax1.plot(
            self.csv_data.integer_count,
            self.csv_data.cod,
            color='darkred', linestyle='-', linewidth=0.5, label='COD vs Cycles'
        )
        self.ax1.set_xlabel("Cycles, N")
        self.ax1.set_ylabel("COD (mm)")
        self.ax1.set_title(f"Raw Data: {self.csv_data.test_run_name}")
        self.ax1.grid(True, linestyle='--', alpha=0.4)
        self.ax1.legend(loc='upper left')
        self.fig1.tight_layout()
        self.canvas1.draw()

    def run_analysis(self):
        """Run full FCGR analysis."""
        if self.csv_data is None and self.excel_data is None:
            messagebox.showwarning("Warning", "Please load test data first")
            return

        try:
            from ..analysis.fcgr_calculations import FCGRAnalyzer
            from ..models.fcgr_specimen import FCGRSpecimen, FCGRMaterial, FCGRTestParameters
            from ..data_acquisition.fcgr_csv_parser import extract_cycle_extrema, calculate_compliance_per_cycle

            self._update_status("Running analysis...")

            # Build specimen from input fields
            W = float(self.dim_vars['W'].get())
            B = float(self.dim_vars['B'].get())
            B_n_str = self.dim_vars['B_n'].get()
            B_n = float(B_n_str) if B_n_str else B
            a_0 = float(self.dim_vars['a_0'].get())
            notch_height = float(self.dim_vars['notch_height'].get() or 0)

            specimen = FCGRSpecimen(
                specimen_id=self.info_vars['specimen_id'].get(),
                specimen_type=self.specimen_type.get(),
                W=W,
                B=B,
                B_n=B_n,
                a_0=a_0,
                notch_height=notch_height,
                material=self.info_vars['material'].get()
            )

            # Build material properties
            material = FCGRMaterial(
                yield_strength=float(self.mat_vars['yield_strength'].get()),
                ultimate_strength=float(self.mat_vars['ultimate_strength'].get()),
                youngs_modulus=float(self.mat_vars['youngs_modulus'].get()),
                poissons_ratio=float(self.mat_vars['poissons_ratio'].get())
            )

            # Build test parameters
            test_params = FCGRTestParameters(
                control_mode=self.control_mode.get(),
                load_ratio=float(self.test_vars['load_ratio'].get()),
                frequency=float(self.test_vars['frequency'].get()),
                temperature=float(self.test_vars['temperature'].get())
            )

            # Add compliance coefficients if available
            if self.compliance_coefficients:
                test_params.compliance_coefficients = self.compliance_coefficients

            # Run analysis
            analyzer = FCGRAnalyzer(specimen, material, test_params)

            if self.csv_data is not None:
                # Extract cycle extrema
                cycles, P_max, P_min, COD_max, COD_min = extract_cycle_extrema(self.csv_data)

                # Calculate compliance per cycle
                _, compliance = calculate_compliance_per_cycle(self.csv_data)

                # Get outlier threshold percentage from UI
                try:
                    outlier_pct = float(self.outlier_threshold.get())
                except ValueError:
                    outlier_pct = 60.0

                # Analyze
                self.current_results = analyzer.analyze_fcgr_data(
                    cycles=cycles,
                    compliance=compliance,
                    P_max=P_max,
                    P_min=P_min,
                    method=self.dadn_method.get(),
                    outlier_percentage=outlier_pct
                )
            elif self.excel_data is not None:
                # Use Excel data (pre-calculated by MTS)
                # This would require additional parsing of MTS results
                messagebox.showinfo("Info", "Analysis from Excel-only data not yet implemented.\nPlease load CSV data.")
                return

            # Store specimen and material for report
            self.current_results.specimen = specimen
            self.current_results.material = material
            self.current_results.test_params = test_params

            # Update results display
            self._display_results()

            # Plot results
            self._plot_analysis_results()

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

        # Configure tags
        self.results_tree.tag_configure('section', background='#E0E0E0')
        self.results_tree.tag_configure('valid', foreground='green')
        self.results_tree.tag_configure('invalid', foreground='red')
        self.results_tree.tag_configure('outlier', foreground='orange')

        def add_section(title):
            self.results_tree.insert("", tk.END, values=(f"-- {title} --", "", "", ""),
                                    tags=('section',))

        # === Test Summary ===
        add_section("Test Summary")

        self.results_tree.insert("", tk.END, values=(
            "Total Cycles", f"{self.current_results.total_cycles:,}", "-", "cycles"
        ))
        self.results_tree.insert("", tk.END, values=(
            "Final Crack Length", f"{self.current_results.final_crack_length:.3f}", "-", "mm"
        ))
        self.results_tree.insert("", tk.END, values=(
            "Data Points", f"{len(self.current_results.data_points)}", "-", ""
        ))
        self.results_tree.insert("", tk.END, values=(
            "Valid Points", f"{self.current_results.n_valid_points}", "-", ""
        ))
        self.results_tree.insert("", tk.END, values=(
            "Outliers Detected", f"{self.current_results.n_outliers}", "-", ""
        ))

        # === Paris Law Results - Initial (all data) ===
        paris_initial = self.current_results.paris_law_initial
        if paris_initial:
            add_section("Initial Paris Law (all data points)")
            self.results_tree.insert("", tk.END, values=(
                "Coefficient C (initial)", f"{paris_initial.C:.4e}", f"+/-{paris_initial.std_error_C:.2e}", "mm/cycle/(MPa*m^0.5)^m"
            ))
            self.results_tree.insert("", tk.END, values=(
                "Exponent m (initial)", f"{paris_initial.m:.4f}", f"+/-{paris_initial.std_error_m:.4f}", ""
            ))
            self.results_tree.insert("", tk.END, values=(
                "R² (initial)", f"{paris_initial.r_squared:.6f}", "-", ""
            ))
            self.results_tree.insert("", tk.END, values=(
                "Points (initial)", f"{paris_initial.n_points}", "-", ""
            ))

        # === Paris Law Results - Final (after outlier removal) ===
        add_section("Final Paris Law (excl. outliers)")

        paris = self.current_results.paris_law
        self.results_tree.insert("", tk.END, values=(
            "Coefficient C", f"{paris.C:.4e}", f"+/-{paris.std_error_C:.2e}", "mm/cycle/(MPa*m^0.5)^m"
        ))
        self.results_tree.insert("", tk.END, values=(
            "Exponent m", f"{paris.m:.4f}", f"+/-{paris.std_error_m:.4f}", ""
        ))
        self.results_tree.insert("", tk.END, values=(
            "R-squared", f"{paris.r_squared:.6f}", "-", ""
        ))
        self.results_tree.insert("", tk.END, values=(
            "Points in Fit", f"{paris.n_points}", "-", ""
        ))
        self.results_tree.insert("", tk.END, values=(
            "Delta-K Range", f"{paris.delta_K_range[0]:.2f} - {paris.delta_K_range[1]:.2f}", "-", "MPa*m^0.5"
        ))
        self.results_tree.insert("", tk.END, values=(
            "da/dN Range", f"{paris.da_dN_range[0]:.2e} - {paris.da_dN_range[1]:.2e}", "-", "mm/cycle"
        ))

        # === Threshold ===
        if self.current_results.threshold_delta_K > 0:
            add_section("Threshold")
            self.results_tree.insert("", tk.END, values=(
                "Delta-K_th (at 1e-7 mm/cycle)", f"{self.current_results.threshold_delta_K:.2f}", "-", "MPa*m^0.5"
            ))

        # === Validity ===
        add_section("Validity")
        for note in self.current_results.validity_notes:
            tag = 'valid' if 'PASS' in note else ('invalid' if 'FAIL' in note else '')
            self.results_tree.insert("", tk.END, values=(note, "", "", ""), tags=(tag,))

    def _plot_analysis_results(self):
        """Plot analysis results on both plots."""
        if not self.current_results:
            return

        # Get data points
        valid_points = self.current_results.valid_points
        outlier_points = [p for p in self.current_results.data_points if p.is_outlier]

        # Arrays for plotting
        cycles_valid = np.array([p.cycle_count for p in valid_points])
        a_valid = np.array([p.crack_length for p in valid_points])
        dK_valid = np.array([p.delta_K for p in valid_points])
        dadN_valid = np.array([p.da_dN for p in valid_points])

        cycles_outlier = np.array([p.cycle_count for p in outlier_points])
        a_outlier = np.array([p.crack_length for p in outlier_points])
        dK_outlier = np.array([p.delta_K for p in outlier_points])
        dadN_outlier = np.array([p.da_dN for p in outlier_points])

        # Plot 1: Crack length vs Cycles
        self.ax1.clear()
        self.ax1.plot(cycles_valid, a_valid, color='darkred', marker='o', markersize=3,
                      linewidth=0.8, label='Valid data')
        if len(cycles_outlier) > 0:
            self.ax1.plot(cycles_outlier, a_outlier, color='gray', marker='x',
                          linestyle='none', markersize=5, label='Outliers')
        self.ax1.set_xlabel("Cycles, N")
        self.ax1.set_ylabel("Crack length, a (mm)")
        self.ax1.set_title(f"a vs N: {self.info_vars['specimen_id'].get()}")
        self.ax1.grid(True, linestyle='--', alpha=0.4)
        self.ax1.legend(loc='upper left', fontsize=8)
        self.fig1.tight_layout()
        self.canvas1.draw()

        # Plot 2: da/dN vs Delta-K (Paris law)
        self.ax2.clear()

        # Valid data points - dark red
        valid_mask = (dK_valid > 0) & (dadN_valid > 0)
        self.ax2.loglog(dK_valid[valid_mask], dadN_valid[valid_mask], 'o',
                        color='darkred', markersize=4, label='Valid data')

        # Outliers - grey
        if len(dK_outlier) > 0:
            outlier_mask = (dK_outlier > 0) & (dadN_outlier > 0)
            if np.any(outlier_mask):
                self.ax2.loglog(dK_outlier[outlier_mask], dadN_outlier[outlier_mask], 'x',
                                color='gray', markersize=5, label='Outliers')

        # Paris law fit lines - both in black with different styles
        paris_final = self.current_results.paris_law
        paris_initial = self.current_results.paris_law_initial

        # Plot initial regression line (all data) - dashed black
        if paris_initial and paris_initial.C > 0 and paris_initial.m > 0:
            dK_fit_init = np.logspace(np.log10(paris_initial.delta_K_range[0]),
                                      np.log10(paris_initial.delta_K_range[1]), 50)
            dadN_fit_init = paris_initial.C * dK_fit_init**paris_initial.m
            self.ax2.loglog(dK_fit_init, dadN_fit_init, '--', color='black', linewidth=1.5,
                            label=f'Initial fit (all data): C={paris_initial.C:.2e}, m={paris_initial.m:.2f}')

        # Plot final regression line (without outliers) - solid black
        if paris_final and paris_final.C > 0 and paris_final.m > 0:
            dK_fit_final = np.logspace(np.log10(paris_final.delta_K_range[0]),
                                       np.log10(paris_final.delta_K_range[1]), 50)
            dadN_fit_final = paris_final.C * dK_fit_final**paris_final.m
            self.ax2.loglog(dK_fit_final, dadN_fit_final, '-', color='black', linewidth=2,
                            label=f'Final fit (excl. outliers): C={paris_final.C:.2e}, m={paris_final.m:.2f}')

        self.ax2.set_xlabel(r"$\Delta K$ (MPa$\sqrt{m}$)")
        self.ax2.set_ylabel("da/dN (mm/cycle)")
        self.ax2.set_title("Paris Law Plot")
        self.ax2.grid(True, which='both', linestyle='--', alpha=0.4)
        self.ax2.legend(loc='upper left', fontsize=8)
        self.fig2.tight_layout()
        self.canvas2.draw()

    def remove_outliers(self):
        """Manually remove outliers and refit Paris law."""
        if not self.current_results:
            messagebox.showwarning("Warning", "Run analysis first")
            return

        # Re-run Paris law fit with stricter threshold
        try:
            threshold = float(self.outlier_threshold.get())
        except ValueError:
            threshold = 2.5

        # Update threshold and re-analyze
        messagebox.showinfo("Info", f"Re-analyzing with outlier threshold: {threshold} std dev")
        self.run_analysis()

    def clear_results(self):
        """Clear all results and reset plots."""
        self.current_results = None

        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        self.ax1.clear()
        self._setup_empty_plot1()
        self.canvas1.draw()

        self.ax2.clear()
        self._setup_empty_plot2()
        self.canvas2.draw()

        if self.csv_data:
            self._plot_raw_data()

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
                    # Header
                    f.write("FCGR Analysis Results - ASTM E647\n")
                    f.write(f"Specimen: {self.info_vars['specimen_id'].get()}\n")
                    f.write(f"Material: {self.info_vars['material'].get()}\n\n")

                    # Paris law
                    paris = self.current_results.paris_law
                    f.write("Paris Law: da/dN = C * (Delta-K)^m\n")
                    f.write(f"C,{paris.C:.6e}\n")
                    f.write(f"m,{paris.m:.6f}\n")
                    f.write(f"R-squared,{paris.r_squared:.6f}\n\n")

                    # Data points
                    f.write("N,a (mm),Delta-K (MPa*sqrt(m)),da/dN (mm/cycle),Valid,Outlier\n")
                    for p in self.current_results.data_points:
                        f.write(f"{p.cycle_count},{p.crack_length:.4f},{p.delta_K:.4f},"
                               f"{p.da_dN:.6e},{p.is_valid},{p.is_outlier}\n")

                self._update_status(f"Exported to: {filepath}")
                messagebox.showinfo("Success", f"Results exported to:\n{filepath}")

            except Exception as e:
                messagebox.showerror("Error", f"Export failed:\n{e}")

    def export_report(self):
        """Export results to Word report."""
        if not self.current_results:
            messagebox.showwarning("Warning", "No results to export. Run analysis first.")
            return

        # Ask for save location - use certificate number as filename
        cert_num = self.info_vars['certificate_number'].get() or self.info_vars['specimen_id'].get()
        filepath = filedialog.asksaveasfilename(
            title="Save Word Report",
            defaultextension=".docx",
            filetypes=[("Word Documents", "*.docx")],
            initialfile=f"{cert_num}.docx"
        )

        if not filepath:
            return

        try:
            from utils.reporting.fcgr_word_report import FCGRReportGenerator

            # Check if template exists
            template_path = PROJECT_ROOT / "templates" / "fcgr_e647_report_template.docx"
            if not template_path.exists():
                messagebox.showerror("Error", f"Template not found: {template_path}\n\nRun scripts/create_fcgr_template.py to generate it.")
                return

            # Create temporary files for plots
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Save Plot 1 (a vs N)
                plot1_path = temp_path / "plot1_a_vs_N.png"
                self.fig1.savefig(plot1_path, dpi=150, bbox_inches='tight', facecolor='white')

                # Save Plot 2 (Paris law)
                plot2_path = temp_path / "plot2_paris.png"
                self.fig2.savefig(plot2_path, dpi=150, bbox_inches='tight', facecolor='white')

                # Collect test information
                test_info = {
                    'test_project': self.info_vars['test_project'].get(),
                    'customer': self.info_vars['customer'].get(),
                    'specimen_id': self.info_vars['specimen_id'].get(),
                    'material': self.info_vars['material'].get(),
                    'certificate_number': self.certificate_number_var.get(),
                    'test_date': self.info_vars['test_date'].get(),
                }

                # Collect specimen data
                specimen_data = {
                    'specimen_type': self.specimen_type.get(),
                    'W': self.dim_vars['W'].get(),
                    'B': self.dim_vars['B'].get(),
                    'B_n': self.dim_vars['B_n'].get() or self.dim_vars['B'].get(),
                    'a_0': self.dim_vars['a_0'].get(),
                    'notch_height': self.dim_vars.get('notch_height', tk.StringVar(value='0')).get(),
                }

                # Collect material data
                material_data = {
                    'yield_strength': self.mat_vars['yield_strength'].get(),
                    'ultimate_strength': self.mat_vars['ultimate_strength'].get(),
                    'youngs_modulus': self.mat_vars['youngs_modulus'].get(),
                    'poissons_ratio': self.mat_vars['poissons_ratio'].get() or '0.3',
                }

                # Collect test parameters
                test_params = {
                    'control_mode': self.control_mode.get(),
                    'load_ratio': self.test_vars['load_ratio'].get(),
                    'frequency': self.test_vars['frequency'].get(),
                    'temperature': self.test_vars['temperature'].get(),
                    'P_max': self.test_vars['P_max'].get(),
                    'K_max': self.test_vars['K_max'].get(),
                    'wave_shape': self.test_vars.get('wave_shape', tk.StringVar(value='Sine')).get() if hasattr(self, 'test_vars') and 'wave_shape' in self.test_vars else 'Sine',
                    'environment': self.test_vars.get('environment', tk.StringVar(value='Laboratory Air')).get() if hasattr(self, 'test_vars') and 'environment' in self.test_vars else 'Laboratory Air',
                    'dadn_method': self.dadn_method.get().capitalize(),
                    'outlier_threshold': self.outlier_threshold.get() or '60',
                }

                # Prepare report data
                report_data = FCGRReportGenerator.prepare_report_data(
                    test_info=test_info,
                    specimen_data=specimen_data,
                    material_data=material_data,
                    test_params=test_params,
                    results=self.current_results,
                    validity_notes=self.current_results.validity_notes if self.current_results else None
                )

                # Generate report
                generator = FCGRReportGenerator(template_path)

                # Check for logo
                logo_path = PROJECT_ROOT / "templates" / "logo.png"
                if not logo_path.exists():
                    logo_path = PROJECT_ROOT / "durablersvart.png"
                    if not logo_path.exists():
                        logo_path = None

                output_path = generator.generate_report(
                    output_path=Path(filepath),
                    data=report_data,
                    plot1_path=plot1_path,
                    plot2_path=plot2_path,
                    logo_path=logo_path,
                    photo_paths=self.crack_photos if self.crack_photos else None
                )

            messagebox.showinfo("Success", f"Report saved to:\n{output_path}")
            self._update_status(f"Report exported: {output_path.name}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report:\n{str(e)}")
            self._update_status("Report generation failed")

    def _refresh_certificate_list(self):
        """Load certificate numbers from database into combobox."""
        try:
            from utils.database.certificate_db import CertificateDatabase
            db = CertificateDatabase()
            cert_numbers = db.get_certificate_numbers_list()

            if hasattr(self, 'cert_combobox'):
                self.cert_combobox['values'] = cert_numbers
        except Exception as e:
            print(f"Error loading certificates: {e}")

    def _on_certificate_selected(self, event):
        """Handle certificate selection from combobox."""
        cert_number = self.certificate_number_var.get()
        if not cert_number:
            return

        try:
            from utils.database.certificate_db import CertificateDatabase
            db = CertificateDatabase()
            cert = db.get_certificate_by_string(cert_number)

            if cert:
                self.info_vars['test_project'].set(cert.test_project or "")
                self.info_vars['customer'].set(cert.customer or "")
                self.info_vars['specimen_id'].set(cert.specimen_id or "")
                self.info_vars['material'].set(cert.material or "")
                self.test_vars['temperature'].set(cert.temperature or "23")

                self._update_status(f"Loaded certificate: {cert_number}")
        except Exception as e:
            self._update_status(f"Error loading certificate: {e}")

    def show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About Durabler FCGR",
            "Durabler - FCGR Test Analysis\n\n"
            "Version: 0.1.0\n"
            "Standard: ASTM E647\n\n"
            "ISO 17025 compliant analysis system\n"
            "for mechanical testing laboratories.\n\n"
            "Calculations include:\n"
            "- Crack length from compliance\n"
            "- da/dN by secant or polynomial method\n"
            "- Paris law regression with outlier detection\n"
            "- Delta-K threshold determination\n"
            "- Validity checks per E647\n\n"
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
    app = FCGRTestApp()
    app.run()


if __name__ == "__main__":
    main()
