"""
Vickers Hardness Test GUI Application per ASTM E92.

This module provides the VickersTestApp class for Vickers hardness
testing with manual data entry, uncertainty calculation, plotting,
photo import, and Word report generation.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import Optional, Dict, Any, List
import numpy as np
from PIL import Image, ImageTk
from datetime import datetime

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# Project root for logo path
PROJECT_ROOT = Path(__file__).parent.parent.parent


class VickersTestApp:
    """
    Vickers Hardness Test Application per ASTM E92.

    Features:
    - Manual entry of hardness readings (1-20 readings)
    - Load level selection (HV1, HV5, HV10, HV30, HV50, HV100)
    - Certificate register integration
    - Hardness plot with reading numbers
    - Photo import for indent images
    - Word report generation with uncertainty

    Parameters
    ----------
    parent_launcher : object, optional
        Reference to parent launcher window
    """

    def __init__(self, parent_launcher: Optional[Any] = None):
        self.parent_launcher = parent_launcher

        self.root = tk.Toplevel() if parent_launcher else tk.Tk()
        self.root.title("Durabler - Vickers Hardness Test (ASTM E92)")
        self.root.geometry("1400x900")

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Data storage
        self.current_results = None
        self.reading_vars: List[Dict[str, tk.StringVar]] = []
        self.reading_entries: List[Dict[str, ttk.Entry]] = []
        self.photo_path: Optional[Path] = None
        self.photo_image = None

        # Create UI components
        self._create_menu()
        self._create_toolbar()
        self._create_statusbar()  # Create statusbar before main panels
        self._create_main_panels()

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
        file_menu.add_command(label="Import Photo...", command=self.import_photo)
        file_menu.add_separator()
        file_menu.add_command(label="Export Report...", command=self.export_report)
        file_menu.add_separator()
        if self.parent_launcher:
            file_menu.add_command(label="Return to Launcher", command=self._on_close)
        file_menu.add_command(label="Exit", command=self._exit_app)

        # Analysis menu
        analysis_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Analysis", menu=analysis_menu)
        analysis_menu.add_command(label="Calculate Results", command=self.run_analysis,
                                  accelerator="F5")
        analysis_menu.add_command(label="Clear All", command=self.clear_all)

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

        ttk.Button(toolbar, text="Import Photo", command=self.import_photo).pack(
            side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(toolbar, text="Calculate", command=self.run_analysis).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Clear", command=self.clear_all).pack(
            side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(toolbar, text="Export Report", command=self.export_report).pack(
            side=tk.LEFT, padx=2)

    def _create_main_panels(self):
        """Create left and right panels with 1:2 proportional layout."""
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        main_frame.columnconfigure(0, weight=1)  # Left panel - 1/3
        main_frame.columnconfigure(1, weight=2)  # Right panel - 2/3
        main_frame.rowconfigure(0, weight=1)

        # Left panel (inputs)
        self._create_left_panel(main_frame)

        # Right panel (results, plot, photo)
        self._create_right_panel(main_frame)

    def _create_left_panel(self, parent):
        """Create left panel with scrollable input area."""
        left_frame = ttk.Frame(parent)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left_frame.rowconfigure(0, weight=1)
        left_frame.columnconfigure(0, weight=1)

        # Create canvas with scrollbar
        canvas = tk.Canvas(left_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Bind canvas width to frame
        def configure_scroll_width(event):
            canvas.itemconfig(canvas.find_all()[0], width=event.width)
        canvas.bind('<Configure>', configure_scroll_width)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)

        # Build content in scrollable frame
        self._build_left_content(self.scrollable_frame)

    def _build_left_content(self, parent):
        """Build the left panel content."""
        # Load Level Selection
        load_frame = ttk.LabelFrame(parent, text="Load Level (ASTM E92)", padding=10)
        load_frame.pack(fill=tk.X, pady=5, padx=5)

        self.load_level_var = tk.StringVar(value="HV 10")
        load_levels = ["HV 1", "HV 5", "HV 10", "HV 30", "HV 50", "HV 100"]

        load_btn_frame = ttk.Frame(load_frame)
        load_btn_frame.pack(fill=tk.X)

        for i, level in enumerate(load_levels):
            ttk.Radiobutton(
                load_btn_frame, text=level,
                variable=self.load_level_var, value=level
            ).grid(row=i // 3, column=i % 3, sticky=tk.W, padx=5, pady=2)

        # Number of Readings Selection
        qty_frame = ttk.LabelFrame(parent, text="Number of Readings", padding=10)
        qty_frame.pack(fill=tk.X, pady=5, padx=5)

        ttk.Label(qty_frame, text="Select quantity:").pack(side=tk.LEFT, padx=5)
        self.qty_var = tk.StringVar(value="5")
        qty_combo = ttk.Combobox(qty_frame, textvariable=self.qty_var, width=5,
                                  values=[str(i) for i in range(1, 21)], state="readonly")
        qty_combo.pack(side=tk.LEFT, padx=5)
        qty_combo.bind('<<ComboboxSelected>>', self._on_qty_changed)

        ttk.Button(qty_frame, text="Update Fields", command=self._update_reading_fields).pack(
            side=tk.LEFT, padx=10)

        # Test Information Frame
        info_frame = ttk.LabelFrame(parent, text="Test Information", padding=10)
        info_frame.pack(fill=tk.X, pady=5, padx=5)

        row = 0
        # Certificate number - Combobox with selection list
        ttk.Label(info_frame, text="Certificate number:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.certificate_var = tk.StringVar()
        cert_frame = ttk.Frame(info_frame)
        cert_frame.grid(row=row, column=1, sticky=tk.EW, pady=2)
        self.cert_combobox = ttk.Combobox(cert_frame, textvariable=self.certificate_var, width=20)
        self.cert_combobox.pack(side=tk.LEFT)
        self.cert_combobox.bind('<<ComboboxSelected>>', self._on_certificate_selected)
        ttk.Button(cert_frame, text="↻", width=3,
                  command=self._refresh_certificate_list).pack(side=tk.LEFT, padx=2)
        self._refresh_certificate_list()
        row += 1

        # Test project
        ttk.Label(info_frame, text="Test project:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.test_project_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.test_project_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        # Customer
        ttk.Label(info_frame, text="Customer:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.customer_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.customer_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        # Specimen ID
        ttk.Label(info_frame, text="Specimen ID:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.specimen_id_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.specimen_id_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        # Material
        ttk.Label(info_frame, text="Material:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.material_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.material_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        # Test Date
        ttk.Label(info_frame, text="Test Date:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.test_date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(info_frame, textvariable=self.test_date_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)
        row += 1

        # Operator
        ttk.Label(info_frame, text="Operator:").grid(row=row, column=0, sticky=tk.W, pady=2)
        self.operator_var = tk.StringVar()
        ttk.Entry(info_frame, textvariable=self.operator_var, width=25).grid(
            row=row, column=1, sticky=tk.EW, pady=2)

        info_frame.columnconfigure(1, weight=1)

        # Hardness Readings Frame
        self.readings_frame = ttk.LabelFrame(parent, text="Hardness Readings", padding=10)
        self.readings_frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=5)

        # Create initial reading fields
        self._update_reading_fields()

    def _on_qty_changed(self, event=None):
        """Handle quantity selection change."""
        self._update_reading_fields()

    def _update_reading_fields(self):
        """Update the reading entry fields based on selected quantity."""
        # Clear existing fields
        for widget in self.readings_frame.winfo_children():
            widget.destroy()
        self.reading_vars.clear()
        self.reading_entries.clear()

        qty = int(self.qty_var.get())

        # Header row
        ttk.Label(self.readings_frame, text="#", width=3, font=('Helvetica', 9, 'bold')).grid(
            row=0, column=0, padx=2, pady=2)
        ttk.Label(self.readings_frame, text="Location", width=15, font=('Helvetica', 9, 'bold')).grid(
            row=0, column=1, padx=2, pady=2)
        ttk.Label(self.readings_frame, text="Hardness (HV)", width=12, font=('Helvetica', 9, 'bold')).grid(
            row=0, column=2, padx=2, pady=2)

        # Create entry fields for each reading
        for i in range(qty):
            row = i + 1
            vars_dict = {
                'location': tk.StringVar(value=f"Point {i+1}"),
                'hardness': tk.StringVar()
            }
            self.reading_vars.append(vars_dict)

            # Reading number
            ttk.Label(self.readings_frame, text=str(i + 1)).grid(row=row, column=0, padx=2, pady=2)

            # Location entry
            loc_entry = ttk.Entry(self.readings_frame, textvariable=vars_dict['location'], width=15)
            loc_entry.grid(row=row, column=1, padx=2, pady=2)

            # Hardness value entry
            hv_entry = ttk.Entry(self.readings_frame, textvariable=vars_dict['hardness'], width=12)
            hv_entry.grid(row=row, column=2, padx=2, pady=2)

            self.reading_entries.append({'location': loc_entry, 'hardness': hv_entry})

        self._update_status(f"Created {qty} reading fields")

    def _create_right_panel(self, parent):
        """Create right panel with results, plot, and photo."""
        right_frame = ttk.Frame(parent)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        right_frame.rowconfigure(2, weight=1)

        # Results frame (top)
        results_frame = ttk.LabelFrame(right_frame, text="Results (ASTM E92)", padding=5)
        results_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        columns = ("parameter", "value", "uncertainty", "unit")
        self.results_tree = ttk.Treeview(
            results_frame, columns=columns, show="headings", height=8
        )

        self.results_tree.heading("parameter", text="Parameter")
        self.results_tree.heading("value", text="Value")
        self.results_tree.heading("uncertainty", text="U (k=2)")
        self.results_tree.heading("unit", text="Unit")

        self.results_tree.column("parameter", width=150)
        self.results_tree.column("value", width=80, anchor=tk.E)
        self.results_tree.column("uncertainty", width=80, anchor=tk.E)
        self.results_tree.column("unit", width=60, anchor=tk.CENTER)

        self.results_tree.pack(fill=tk.BOTH, expand=True)

        # Plot frame (middle)
        plot_frame = ttk.LabelFrame(right_frame, text="Hardness Profile", padding=5)
        plot_frame.grid(row=1, column=0, sticky="nsew", pady=5)

        self.fig = Figure(figsize=(6, 3), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self._setup_empty_plot()

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.pack(fill=tk.X)
        self.toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        self.toolbar.update()

        # Photo frame (bottom)
        photo_frame = ttk.LabelFrame(right_frame, text="Indent Photo", padding=5)
        photo_frame.grid(row=2, column=0, sticky="nsew", pady=(5, 0))

        self.photo_label = ttk.Label(photo_frame, text="No photo imported\n\nClick 'Import Photo' to add indent image",
                                      anchor=tk.CENTER, justify=tk.CENTER)
        self.photo_label.pack(fill=tk.BOTH, expand=True)

    def _setup_empty_plot(self):
        """Set up empty plot with labels."""
        self.ax.set_facecolor('white')
        self.fig.patch.set_facecolor('white')
        self.ax.set_xlabel("Reading Number")
        self.ax.set_ylabel("Hardness (HV)")
        self.ax.set_title("Vickers Hardness Profile")
        self.ax.grid(True, linestyle='--', alpha=0.7)

    def _create_statusbar(self):
        """Create status bar at bottom."""
        self.statusbar = ttk.Label(
            self.root, text="Ready - Enter hardness readings and click Calculate",
            relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.grid(row=2, column=0, sticky="ew")

    def _update_status(self, message: str):
        """Update status bar message."""
        self.statusbar.config(text=message)
        self.root.update_idletasks()

    def _refresh_certificate_list(self):
        """Load certificate numbers from database."""
        try:
            from utils.database.certificate_db import CertificateDatabase
            db = CertificateDatabase()
            cert_numbers = db.get_certificate_numbers_list()
            if hasattr(self, 'cert_combobox'):
                self.cert_combobox['values'] = cert_numbers
        except Exception as e:
            print(f"Error loading certificates: {e}")

    def _on_certificate_selected(self, event):
        """Handle certificate selection - populate test info fields."""
        cert_number = self.certificate_var.get()
        if not cert_number:
            return

        try:
            from utils.database.certificate_db import CertificateDatabase
            db = CertificateDatabase()
            cert = db.get_certificate_by_string(cert_number)

            if cert:
                self.test_project_var.set(cert.test_project or "")
                self.customer_var.set(cert.customer or "")
                self.specimen_id_var.set(cert.specimen_id or "")
                self.material_var.set(cert.material or "")
                self._update_status(f"Loaded certificate: {cert_number}")
        except Exception as e:
            self._update_status(f"Error loading certificate: {e}")

    def import_photo(self):
        """Import indent photograph."""
        filepath = filedialog.askopenfilename(
            title="Select Indent Photo",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff"),
                ("All files", "*.*")
            ]
        )

        if filepath:
            try:
                self.photo_path = Path(filepath)
                img = Image.open(filepath)

                # Resize to fit the label while maintaining aspect ratio
                max_size = (400, 300)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                self.photo_image = ImageTk.PhotoImage(img)
                self.photo_label.config(image=self.photo_image, text="")

                self._update_status(f"Imported photo: {self.photo_path.name}")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to import photo:\n{e}")

    def run_analysis(self):
        """Run Vickers hardness analysis."""
        try:
            from utils.models.vickers_specimen import VickersTestData, VickersReading, VickersLoadLevel
            from utils.analysis.vickers_calculations import VickersAnalyzer

            # Collect readings
            readings = []
            for i, vars_dict in enumerate(self.reading_vars):
                hv_str = vars_dict['hardness'].get().strip()
                if hv_str:
                    try:
                        hv_value = float(hv_str)
                        location = vars_dict['location'].get().strip()
                        readings.append(VickersReading(
                            reading_number=i + 1,
                            location=location if location else f"Point {i+1}",
                            hardness_value=hv_value
                        ))
                    except ValueError:
                        messagebox.showwarning("Warning", f"Invalid hardness value at reading {i+1}")
                        return

            if not readings:
                messagebox.showwarning("Warning", "Please enter at least one hardness reading")
                return

            # Get load level
            load_str = self.load_level_var.get()
            force_kgf = float(load_str.replace("HV ", ""))
            load_level = VickersLoadLevel(load_str, force_kgf)

            # Create test data
            test_data = VickersTestData(
                readings=readings,
                load_level=load_level,
                specimen_id=self.specimen_id_var.get(),
                material=self.material_var.get(),
                test_date=self.test_date_var.get(),
                operator=self.operator_var.get(),
                photo_path=str(self.photo_path) if self.photo_path else None
            )

            # Run analysis
            analyzer = VickersAnalyzer()
            self.current_results = analyzer.run_analysis(test_data)
            self.current_test_data = test_data

            # Get uncertainty budget
            values = test_data.hardness_values
            self.uncertainty_budget = analyzer.get_uncertainty_budget(values, np.mean(values))

            # Display results
            self._display_results()

            # Update plot
            self._plot_hardness()

            self._update_status(f"Analysis complete: {len(readings)} readings, Mean = {self.current_results.mean_hardness}")

        except Exception as e:
            messagebox.showerror("Error", f"Analysis failed:\n{e}")
            import traceback
            traceback.print_exc()

    def _display_results(self):
        """Display results in treeview."""
        # Clear existing
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        if not self.current_results:
            return

        r = self.current_results

        results = [
            ("Mean Hardness", f"{r.mean_hardness.value:.1f}", f"± {r.mean_hardness.uncertainty:.1f}", r.load_level),
            ("Standard Deviation", f"{r.std_dev:.1f}", "", r.load_level),
            ("Range (Max - Min)", f"{r.range_value:.1f}", "", r.load_level),
            ("Minimum Value", f"{r.min_value:.1f}", "", r.load_level),
            ("Maximum Value", f"{r.max_value:.1f}", "", r.load_level),
            ("Number of Readings", f"{r.n_readings}", "", "-"),
        ]

        for name, value, unc, unit in results:
            self.results_tree.insert("", tk.END, values=(name, value, unc, unit))

    def _plot_hardness(self):
        """Plot hardness profile."""
        if not self.current_results:
            return

        self.ax.clear()

        # Set white background
        self.ax.set_facecolor('white')
        self.fig.patch.set_facecolor('white')

        readings = self.current_results.readings
        x = [r.reading_number for r in readings]
        y = [r.hardness_value for r in readings]

        # Plot individual readings - dark red color
        self.ax.plot(x, y, color='darkred', marker='o', markersize=8,
                    linewidth=1.5, label='Readings')

        # Mean line - black dotted
        mean = self.current_results.mean_hardness.value
        self.ax.axhline(y=mean, color='black', linestyle=':', linewidth=1.5,
                       label=f'Mean = {mean:.1f}')

        # Uncertainty band - light gray
        unc = self.current_results.mean_hardness.uncertainty
        self.ax.axhspan(mean - unc, mean + unc, alpha=0.2, color='gray',
                       label=f'U (k=2) = ± {unc:.1f}')

        # Labels and formatting
        self.ax.set_xlabel("Reading Number", fontsize=10)
        self.ax.set_ylabel(f"Hardness ({self.current_results.load_level})", fontsize=10)
        self.ax.set_title(f"Vickers Hardness Profile: {self.specimen_id_var.get()}", fontsize=11, fontweight='bold')
        self.ax.legend(loc='best', fontsize=8)
        self.ax.grid(True, linestyle='--', alpha=0.4)

        # Set x-axis to show integer reading numbers
        self.ax.set_xticks(x)
        self.ax.set_xlim(0.5, max(x) + 0.5)

        # Set y-axis limits with some padding
        y_min = min(y) - self.current_results.range_value * 0.2
        y_max = max(y) + self.current_results.range_value * 0.2
        if y_min == y_max:
            y_min -= 10
            y_max += 10
        self.ax.set_ylim(y_min, y_max)

        self.fig.tight_layout()
        self.canvas.draw()

    def clear_all(self):
        """Clear all data and reset."""
        # Clear reading values
        for vars_dict in self.reading_vars:
            vars_dict['hardness'].set("")

        # Clear results
        self.current_results = None
        self.current_test_data = None

        # Clear treeview
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)

        # Reset plot
        self.ax.clear()
        self._setup_empty_plot()
        self.canvas.draw()

        # Clear photo
        self.photo_path = None
        self.photo_image = None
        self.photo_label.config(image="", text="No photo imported\n\nClick 'Import Photo' to add indent image")

        self._update_status("All data cleared")

    def _generate_report_chart(self) -> Path:
        """Generate chart for report."""
        import tempfile
        from matplotlib.figure import Figure

        fig = Figure(figsize=(7, 4), dpi=150, facecolor='white')
        ax = fig.add_subplot(111)
        ax.set_facecolor('white')

        readings = self.current_results.readings
        x = [r.reading_number for r in readings]
        y = [r.hardness_value for r in readings]

        # Dark red line and points
        ax.plot(x, y, color='darkred', marker='o', markersize=8,
               linewidth=1.5, label='Readings')

        # Black dotted mean line
        mean = self.current_results.mean_hardness.value
        ax.axhline(y=mean, color='black', linestyle=':', linewidth=1.5,
                   label=f'Mean = {mean:.1f}')

        # Gray uncertainty band
        unc = self.current_results.mean_hardness.uncertainty
        ax.axhspan(mean - unc, mean + unc, alpha=0.2, color='gray',
                   label=f'U (k=2) = ± {unc:.1f}')

        ax.set_xlabel("Reading Number", fontsize=10)
        ax.set_ylabel(f"Hardness ({self.current_results.load_level})", fontsize=10)
        ax.set_title(f"Vickers Hardness Profile: {self.specimen_id_var.get()}", fontsize=11, fontweight='bold')
        ax.legend(loc='best', fontsize=9)
        ax.grid(True, linestyle='--', alpha=0.4)
        ax.set_xticks(x)
        ax.set_xlim(0.5, max(x) + 0.5)

        y_min = min(y) - self.current_results.range_value * 0.2
        y_max = max(y) + self.current_results.range_value * 0.2
        if y_min == y_max:
            y_min -= 10
            y_max += 10
        ax.set_ylim(y_min, y_max)

        fig.tight_layout()

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            chart_path = Path(tmp.name)
            fig.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor='white')

        return chart_path

    def export_report(self):
        """Export results to Word report."""
        if not self.current_results:
            messagebox.showwarning("Warning", "No results to export. Run analysis first.")
            return

        filepath = filedialog.asksaveasfilename(
            title="Export Report",
            defaultextension=".docx",
            filetypes=[("Word documents", "*.docx"), ("All files", "*.*")],
            initialfile=f"Vickers_Report_{self.specimen_id_var.get()}.docx"
        )

        if not filepath:
            return

        try:
            from utils.reporting.vickers_word_report import VickersReportGenerator

            self._update_status("Generating report...")

            template_path = PROJECT_ROOT / "templates" / "vickers_e92_report_template.docx"
            logo_path = PROJECT_ROOT / "templates" / "logo.png"

            if not logo_path.exists():
                logo_path = PROJECT_ROOT / "durablersvart.png"

            if not template_path.exists():
                messagebox.showerror("Error", f"Template not found:\n{template_path}\n\nPlease run create_vickers_template.py first.")
                return

            # Prepare test info
            test_info = {
                'certificate_number': self.certificate_var.get(),
                'test_project': self.test_project_var.get(),
                'customer': self.customer_var.get(),
                'specimen_id': self.specimen_id_var.get(),
                'material': self.material_var.get(),
                'test_date': self.test_date_var.get(),
                'operator': self.operator_var.get(),
                'load_level': self.load_level_var.get(),
            }

            # Generate chart
            chart_path = self._generate_report_chart()

            # Generate report
            generator = VickersReportGenerator(template_path)
            output_path = generator.generate_report(
                output_path=Path(filepath),
                test_info=test_info,
                results=self.current_results,
                uncertainty_budget=self.uncertainty_budget,
                chart_path=chart_path,
                photo_path=self.photo_path,
                logo_path=logo_path if logo_path.exists() else None
            )

            # Clean up temp chart
            if chart_path.exists():
                chart_path.unlink()

            self._update_status(f"Report exported: {filepath}")
            messagebox.showinfo("Success", f"Report exported to:\n{filepath}")

        except Exception as e:
            messagebox.showerror("Error", f"Report generation failed:\n{e}")
            import traceback
            traceback.print_exc()

    def show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About Durabler",
            "Durabler - Vickers Hardness Test\n\n"
            "Version: 0.1.0\n"
            "Standard: ASTM E92\n\n"
            "ISO 17025 compliant analysis system\n"
            "for mechanical testing laboratories.\n\n"
            "Features:\n"
            "- Manual hardness reading entry\n"
            "- Load levels: HV1 to HV100\n"
            "- Statistical analysis with uncertainty\n"
            "- Hardness profile plotting\n"
            "- Indent photo import\n"
            "- Word report generation\n\n"
            "Uncertainty per GUM methodology (k=2)"
        )

    def run(self):
        """Start the application main loop."""
        self.root.mainloop()


def main():
    """Application entry point."""
    app = VickersTestApp()
    app.run()


if __name__ == "__main__":
    main()
