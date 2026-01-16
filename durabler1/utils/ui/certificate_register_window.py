"""
Certificate Register Application Window.

Provides GUI for managing test certificate numbers and associated test information.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

from PIL import Image, ImageTk

# Project root for resources
PROJECT_ROOT = Path(__file__).parent.parent.parent


class CertificateRegisterApp:
    """
    Main Tkinter application for Certificate Register management.

    Parameters
    ----------
    parent_launcher : object, optional
        Reference to parent launcher window to return to on close
    """

    def __init__(self, parent_launcher: Optional[Any] = None):
        self.parent_launcher = parent_launcher

        self.root = tk.Toplevel() if parent_launcher else tk.Tk()
        self.root.title("Durabler - Certificate Register")
        self.root.geometry("1300x800")

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Initialize database
        from utils.database.certificate_db import CertificateDatabase, Certificate
        self.db = CertificateDatabase()
        self.Certificate = Certificate

        # Current selection
        self.current_certificate = None

        # Create UI
        self._create_menu()
        self._create_toolbar()
        self._create_main_panels()
        self._create_statusbar()

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # Load initial data
        self._refresh_certificate_list()

    def _on_close(self):
        """Handle window close."""
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
        file_menu.add_command(label="Import from Excel...", command=self._import_excel)
        file_menu.add_command(label="Export to Excel...", command=self._export_excel)
        file_menu.add_separator()
        if self.parent_launcher:
            file_menu.add_command(label="Return to Launcher", command=self._on_close)
        file_menu.add_command(label="Exit", command=self._exit_app)

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="New Certificate", command=self._new_certificate,
                             accelerator="Ctrl+N")
        edit_menu.add_command(label="Save", command=self._save_certificate,
                             accelerator="Ctrl+S")
        edit_menu.add_command(label="Delete", command=self._delete_certificate)
        edit_menu.add_separator()
        edit_menu.add_command(label="Create Revision", command=self._create_revision)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

        # Keyboard shortcuts
        self.root.bind('<Control-n>', lambda e: self._new_certificate())
        self.root.bind('<Control-s>', lambda e: self._save_certificate())

    def _exit_app(self):
        """Exit the application."""
        if self.parent_launcher:
            self.parent_launcher.root.quit()
        self.root.quit()

    def _create_toolbar(self):
        """Create main toolbar."""
        toolbar = ttk.Frame(self.root)
        toolbar.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # Logo
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

        # Action buttons
        ttk.Button(toolbar, text="New", command=self._new_certificate).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Save", command=self._save_certificate).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Delete", command=self._delete_certificate).pack(
            side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(toolbar, text="Import Excel", command=self._import_excel).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Refresh", command=self._refresh_certificate_list).pack(
            side=tk.LEFT, padx=2)

    def _create_main_panels(self):
        """Create main content panels."""
        main_frame = ttk.Frame(self.root)
        main_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)

        # Left panel - certificate list
        self._create_list_panel(main_frame)

        # Right panel - certificate details
        self._create_details_panel(main_frame)

    def _create_list_panel(self, parent):
        """Create left panel with certificate list."""
        list_frame = ttk.LabelFrame(parent, text="Certificates", padding=5)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Filter controls
        filter_frame = ttk.Frame(list_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(filter_frame, text="Year:").pack(side=tk.LEFT)
        self.year_filter = ttk.Combobox(filter_frame, width=8, state="readonly")
        self.year_filter.pack(side=tk.LEFT, padx=5)
        self.year_filter.bind('<<ComboboxSelected>>', lambda e: self._refresh_certificate_list())

        ttk.Label(filter_frame, text="Search:").pack(side=tk.LEFT, padx=(10, 0))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=15)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind('<Return>', lambda e: self._search_certificates())
        ttk.Button(filter_frame, text="Search", command=self._search_certificates).pack(
            side=tk.LEFT)

        # Treeview for certificates
        columns = ("cert_number", "date", "project", "customer", "standard")
        self.cert_tree = ttk.Treeview(
            list_frame, columns=columns, show="headings", height=25
        )

        self.cert_tree.heading("cert_number", text="Certificate No.")
        self.cert_tree.heading("date", text="Date")
        self.cert_tree.heading("project", text="Project")
        self.cert_tree.heading("customer", text="Customer")
        self.cert_tree.heading("standard", text="Standard")

        self.cert_tree.column("cert_number", width=120)
        self.cert_tree.column("date", width=80)
        self.cert_tree.column("project", width=100)
        self.cert_tree.column("customer", width=100)
        self.cert_tree.column("standard", width=80)

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.cert_tree.yview)
        self.cert_tree.configure(yscrollcommand=scrollbar.set)

        self.cert_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind selection
        self.cert_tree.bind('<<TreeviewSelect>>', self._on_certificate_select)

    def _create_details_panel(self, parent):
        """Create right panel with certificate details."""
        details_frame = ttk.LabelFrame(parent, text="Certificate Details", padding=10)
        details_frame.grid(row=0, column=1, sticky="nsew")

        # Certificate number section
        cert_num_frame = ttk.Frame(details_frame)
        cert_num_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(cert_num_frame, text="Certificate Number:",
                  font=('Helvetica', 10, 'bold')).pack(side=tk.LEFT)
        self.cert_number_label = ttk.Label(cert_num_frame, text="(New)",
                                           font=('Helvetica', 12, 'bold'), foreground='blue')
        self.cert_number_label.pack(side=tk.LEFT, padx=10)

        ttk.Separator(details_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # Scrollable form
        canvas = tk.Canvas(details_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(details_frame, orient="vertical", command=canvas.yview)
        form_frame = ttk.Frame(canvas)

        form_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=form_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Form fields
        self.form_vars = {}

        # Certificate info
        cert_info_frame = ttk.LabelFrame(form_frame, text="Certificate Info", padding=10)
        cert_info_frame.pack(fill=tk.X, pady=5, padx=5)

        cert_fields = [
            ("Year:", "year", 8),
            ("Cert ID:", "cert_id", 8),
            ("Revision:", "revision", 5),
            ("Date:", "cert_date", 12),
        ]

        row = 0
        for label, key, width in cert_fields:
            ttk.Label(cert_info_frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar()
            self.form_vars[key] = var
            entry = ttk.Entry(cert_info_frame, textvariable=var, width=width)
            entry.grid(row=row, column=1, sticky=tk.W, pady=2, padx=5)
            row += 1

        # Test information
        test_info_frame = ttk.LabelFrame(form_frame, text="Test Information", padding=10)
        test_info_frame.pack(fill=tk.X, pady=5, padx=5)

        test_fields = [
            ("Test Project:", "test_project", 20),
            ("Project Name:", "project_name", 30),
            ("Test Standard:", "test_standard", 20),
            ("Customer:", "customer", 30),
            ("Customer Order:", "customer_order", 20),
        ]

        row = 0
        for label, key, width in test_fields:
            ttk.Label(test_info_frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar()
            self.form_vars[key] = var
            entry = ttk.Entry(test_info_frame, textvariable=var, width=width)
            entry.grid(row=row, column=1, sticky=tk.W, pady=2, padx=5)
            row += 1

        # Specimen information
        specimen_frame = ttk.LabelFrame(form_frame, text="Specimen Information", padding=10)
        specimen_frame.pack(fill=tk.X, pady=5, padx=5)

        specimen_fields = [
            ("Product:", "product", 30),
            ("Product S/N:", "product_sn", 20),
            ("Material:", "material", 30),
            ("Specimen ID:", "specimen_id", 20),
            ("Location/Orient.:", "location_orientation", 20),
            ("Temperature:", "temperature", 10),
        ]

        row = 0
        for label, key, width in specimen_fields:
            ttk.Label(specimen_frame, text=label).grid(row=row, column=0, sticky=tk.W, pady=2)
            var = tk.StringVar()
            self.form_vars[key] = var
            entry = ttk.Entry(specimen_frame, textvariable=var, width=width)
            entry.grid(row=row, column=1, sticky=tk.W, pady=2, padx=5)
            row += 1

        # Comment
        comment_frame = ttk.LabelFrame(form_frame, text="Comment", padding=10)
        comment_frame.pack(fill=tk.X, pady=5, padx=5)

        self.form_vars['comment'] = tk.StringVar()
        comment_entry = ttk.Entry(comment_frame, textvariable=self.form_vars['comment'], width=50)
        comment_entry.pack(fill=tk.X)

        # Status checkboxes
        status_frame = ttk.LabelFrame(form_frame, text="Status", padding=10)
        status_frame.pack(fill=tk.X, pady=5, padx=5)

        self.reported_var = tk.BooleanVar()
        self.invoiced_var = tk.BooleanVar()

        ttk.Checkbutton(status_frame, text="Reported", variable=self.reported_var).pack(
            side=tk.LEFT, padx=10)
        ttk.Checkbutton(status_frame, text="Invoiced", variable=self.invoiced_var).pack(
            side=tk.LEFT, padx=10)

    def _create_statusbar(self):
        """Create status bar."""
        self.statusbar = ttk.Label(
            self.root, text="Ready", relief=tk.SUNKEN, anchor=tk.W
        )
        self.statusbar.grid(row=2, column=0, sticky="ew")

    def _update_status(self, message: str):
        """Update status bar message."""
        self.statusbar.config(text=message)
        self.root.update_idletasks()

    def _refresh_certificate_list(self):
        """Refresh the certificate list from database."""
        # Update year filter
        years = self.db.get_years_list()
        current_year = datetime.now().year
        if current_year not in years:
            years.insert(0, current_year)
        year_options = ["All"] + [str(y) for y in years]
        self.year_filter['values'] = year_options
        if not self.year_filter.get():
            self.year_filter.set("All")

        # Get selected year filter
        year_filter = self.year_filter.get()
        year = int(year_filter) if year_filter != "All" else None

        # Clear tree
        for item in self.cert_tree.get_children():
            self.cert_tree.delete(item)

        # Load certificates
        certificates = self.db.get_all_certificates(year=year)

        for cert in certificates:
            self.cert_tree.insert("", tk.END, iid=cert.id, values=(
                cert.certificate_number_with_rev,
                cert.cert_date or "",
                cert.test_project,
                cert.customer,
                cert.test_standard
            ))

        count = len(certificates)
        self._update_status(f"Loaded {count} certificates")

    def _search_certificates(self):
        """Search certificates by search term."""
        search_term = self.search_var.get().strip()
        if not search_term:
            self._refresh_certificate_list()
            return

        # Clear tree
        for item in self.cert_tree.get_children():
            self.cert_tree.delete(item)

        # Search
        certificates = self.db.search_certificates(search_term)

        for cert in certificates:
            self.cert_tree.insert("", tk.END, iid=cert.id, values=(
                cert.certificate_number_with_rev,
                cert.cert_date or "",
                cert.test_project,
                cert.customer,
                cert.test_standard
            ))

        count = len(certificates)
        self._update_status(f"Found {count} certificates matching '{search_term}'")

    def _on_certificate_select(self, event):
        """Handle certificate selection in treeview."""
        selection = self.cert_tree.selection()
        if not selection:
            return

        record_id = int(selection[0])
        cert = self.db.get_certificate_by_id(record_id)

        if cert:
            self.current_certificate = cert
            self._populate_form(cert)

    def _populate_form(self, cert):
        """Populate form with certificate data."""
        self.cert_number_label.config(text=cert.certificate_number_with_rev)

        self.form_vars['year'].set(str(cert.year))
        self.form_vars['cert_id'].set(str(cert.cert_id))
        self.form_vars['revision'].set(str(cert.revision))
        self.form_vars['cert_date'].set(cert.cert_date or "")
        self.form_vars['test_project'].set(cert.test_project)
        self.form_vars['project_name'].set(cert.project_name)
        self.form_vars['test_standard'].set(cert.test_standard)
        self.form_vars['customer'].set(cert.customer)
        self.form_vars['customer_order'].set(cert.customer_order)
        self.form_vars['product'].set(cert.product)
        self.form_vars['product_sn'].set(cert.product_sn)
        self.form_vars['material'].set(cert.material)
        self.form_vars['specimen_id'].set(cert.specimen_id)
        self.form_vars['location_orientation'].set(cert.location_orientation)
        self.form_vars['temperature'].set(cert.temperature)
        self.form_vars['comment'].set(cert.comment)
        self.reported_var.set(cert.reported)
        self.invoiced_var.set(cert.invoiced)

    def _clear_form(self):
        """Clear all form fields."""
        for var in self.form_vars.values():
            var.set("")
        self.reported_var.set(False)
        self.invoiced_var.set(False)
        self.cert_number_label.config(text="(New)")
        self.current_certificate = None

    def _new_certificate(self):
        """Create a new certificate."""
        self._clear_form()

        # Set defaults
        current_year = datetime.now().year
        next_id = self.db.get_next_cert_id(current_year)

        self.form_vars['year'].set(str(current_year))
        self.form_vars['cert_id'].set(str(next_id))
        self.form_vars['revision'].set("1")
        self.form_vars['cert_date'].set(datetime.now().strftime("%Y-%m-%d"))

        self.cert_number_label.config(text=f"DUR-{current_year}-{next_id} (New)")
        self._update_status(f"New certificate: DUR-{current_year}-{next_id}")

    def _save_certificate(self):
        """Save current certificate."""
        try:
            year = int(self.form_vars['year'].get())
            cert_id = int(self.form_vars['cert_id'].get())
            revision = int(self.form_vars['revision'].get())
        except ValueError:
            messagebox.showerror("Error", "Year, Cert ID, and Revision must be numbers")
            return

        cert = self.Certificate(
            id=self.current_certificate.id if self.current_certificate else None,
            year=year,
            cert_id=cert_id,
            revision=revision,
            cert_date=self.form_vars['cert_date'].get(),
            product=self.form_vars['product'].get(),
            product_sn=self.form_vars['product_sn'].get(),
            test_project=self.form_vars['test_project'].get(),
            project_name=self.form_vars['project_name'].get(),
            test_standard=self.form_vars['test_standard'].get(),
            material=self.form_vars['material'].get(),
            specimen_id=self.form_vars['specimen_id'].get(),
            location_orientation=self.form_vars['location_orientation'].get(),
            temperature=self.form_vars['temperature'].get(),
            customer=self.form_vars['customer'].get(),
            customer_order=self.form_vars['customer_order'].get(),
            comment=self.form_vars['comment'].get(),
            reported=self.reported_var.get(),
            invoiced=self.invoiced_var.get()
        )

        try:
            if self.current_certificate:
                self.db.update_certificate(cert)
                self._update_status(f"Updated certificate {cert.certificate_number}")
            else:
                new_id = self.db.create_certificate(cert)
                cert.id = new_id
                self.current_certificate = cert
                self._update_status(f"Created certificate {cert.certificate_number}")

            self._refresh_certificate_list()

            # Select the saved certificate
            if cert.id:
                self.cert_tree.selection_set(cert.id)
                self.cert_tree.see(cert.id)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save certificate:\n{str(e)}")

    def _delete_certificate(self):
        """Delete current certificate."""
        if not self.current_certificate:
            messagebox.showwarning("Warning", "No certificate selected")
            return

        cert_num = self.current_certificate.certificate_number_with_rev
        if not messagebox.askyesno("Confirm Delete",
                                    f"Are you sure you want to delete {cert_num}?"):
            return

        if self.db.delete_certificate(self.current_certificate.id):
            self._update_status(f"Deleted certificate {cert_num}")
            self._clear_form()
            self._refresh_certificate_list()
        else:
            messagebox.showerror("Error", "Failed to delete certificate")

    def _create_revision(self):
        """Create a new revision of the current certificate."""
        if not self.current_certificate:
            messagebox.showwarning("Warning", "No certificate selected")
            return

        # Get next revision number
        new_revision = self.current_certificate.revision + 1

        # Create new certificate with incremented revision
        self.current_certificate = None
        self.form_vars['revision'].set(str(new_revision))
        self.cert_number_label.config(
            text=f"DUR-{self.form_vars['year'].get()}-{self.form_vars['cert_id'].get()} Rev.{new_revision} (New)"
        )

        self._update_status(f"Creating revision {new_revision}")

    def _import_excel(self):
        """Import certificates from Excel file."""
        filepath = filedialog.askopenfilename(
            title="Select Excel File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
            initialdir=PROJECT_ROOT / "data"
        )

        if not filepath:
            return

        try:
            self._update_status("Importing certificates...")
            count = self.db.import_from_excel(Path(filepath))
            self._refresh_certificate_list()
            messagebox.showinfo("Import Complete", f"Imported {count} new certificates")
            self._update_status(f"Imported {count} certificates from Excel")
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to import:\n{str(e)}")

    def _export_excel(self):
        """Export certificates to Excel file."""
        messagebox.showinfo("Info", "Export to Excel not yet implemented")

    def _show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About Certificate Register",
            "Durabler - Certificate Register\n\n"
            "Version: 1.0.0\n\n"
            "Manages test certificate numbers and\n"
            "associated test information.\n\n"
            "Certificate format: DUR-YYYY-NNNN Rev.R"
        )

    def run(self):
        """Start the application main loop."""
        self.root.mainloop()


def main():
    """Application entry point."""
    app = CertificateRegisterApp()
    app.run()


if __name__ == "__main__":
    main()
