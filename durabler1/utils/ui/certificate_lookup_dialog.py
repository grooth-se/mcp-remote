"""
Certificate Lookup Dialog.

Reusable dialog for browsing and selecting certificates from the register,
and importing test information into test programs.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Dict, Any, Callable
from datetime import datetime


class CertificateLookupDialog:
    """
    Dialog for browsing and selecting certificates.

    Parameters
    ----------
    parent : tk.Widget
        Parent widget
    on_select : Callable
        Callback function called with certificate data when selected
    """

    def __init__(self, parent: tk.Widget, on_select: Optional[Callable] = None):
        self.parent = parent
        self.on_select = on_select
        self.selected_certificate = None

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Select Certificate")
        self.dialog.geometry("800x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Center dialog
        self.dialog.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - 800) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - 500) // 2
        self.dialog.geometry(f"800x500+{x}+{y}")

        # Initialize database
        from utils.database.certificate_db import CertificateDatabase
        self.db = CertificateDatabase()

        self._create_ui()
        self._load_certificates()

    def _create_ui(self):
        """Create dialog UI."""
        main_frame = ttk.Frame(self.dialog, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Filter controls
        filter_frame = ttk.Frame(main_frame)
        filter_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(filter_frame, text="Year:").pack(side=tk.LEFT)
        self.year_filter = ttk.Combobox(filter_frame, width=8, state="readonly")
        self.year_filter.pack(side=tk.LEFT, padx=5)
        self.year_filter.bind('<<ComboboxSelected>>', lambda e: self._load_certificates())

        ttk.Label(filter_frame, text="Search:").pack(side=tk.LEFT, padx=(20, 0))
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind('<Return>', lambda e: self._search())
        ttk.Button(filter_frame, text="Search", command=self._search).pack(side=tk.LEFT)
        ttk.Button(filter_frame, text="Clear", command=self._clear_search).pack(side=tk.LEFT, padx=5)

        # Certificate list
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("cert_number", "date", "project", "customer", "standard", "product_sn")
        self.cert_tree = ttk.Treeview(
            list_frame, columns=columns, show="headings", height=15
        )

        self.cert_tree.heading("cert_number", text="Certificate No.")
        self.cert_tree.heading("date", text="Date")
        self.cert_tree.heading("project", text="Project")
        self.cert_tree.heading("customer", text="Customer")
        self.cert_tree.heading("standard", text="Standard")
        self.cert_tree.heading("product_sn", text="Product S/N")

        self.cert_tree.column("cert_number", width=130)
        self.cert_tree.column("date", width=80)
        self.cert_tree.column("project", width=100)
        self.cert_tree.column("customer", width=120)
        self.cert_tree.column("standard", width=100)
        self.cert_tree.column("product_sn", width=100)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.cert_tree.yview)
        self.cert_tree.configure(yscrollcommand=scrollbar.set)

        self.cert_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Double-click to select
        self.cert_tree.bind('<Double-1>', lambda e: self._select_certificate())

        # Preview frame
        preview_frame = ttk.LabelFrame(main_frame, text="Certificate Info Preview", padding=10)
        preview_frame.pack(fill=tk.X, pady=(10, 0))

        self.preview_text = tk.Text(preview_frame, height=5, width=80, state=tk.DISABLED)
        self.preview_text.pack(fill=tk.X)

        # Bind selection to show preview
        self.cert_tree.bind('<<TreeviewSelect>>', self._on_select)

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(button_frame, text="Select", command=self._select_certificate).pack(
            side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.dialog.destroy).pack(
            side=tk.RIGHT)

        # Status label
        self.status_label = ttk.Label(button_frame, text="")
        self.status_label.pack(side=tk.LEFT)

    def _load_certificates(self):
        """Load certificates from database."""
        # Update year filter
        years = self.db.get_years_list()
        current_year = datetime.now().year
        if current_year not in years:
            years.insert(0, current_year)
        year_options = ["All"] + [str(y) for y in years]
        self.year_filter['values'] = year_options
        if not self.year_filter.get():
            self.year_filter.set("All")

        # Get filter
        year_filter = self.year_filter.get()
        year = int(year_filter) if year_filter != "All" else None

        # Clear tree
        for item in self.cert_tree.get_children():
            self.cert_tree.delete(item)

        # Load certificates
        certificates = self.db.get_all_certificates(year=year, limit=500)

        for cert in certificates:
            self.cert_tree.insert("", tk.END, iid=cert.id, values=(
                cert.certificate_number_with_rev,
                cert.cert_date or "",
                cert.test_project,
                cert.customer,
                cert.test_standard,
                cert.product_sn
            ))

        self.status_label.config(text=f"{len(certificates)} certificates")

    def _search(self):
        """Search certificates."""
        search_term = self.search_var.get().strip()
        if not search_term:
            self._load_certificates()
            return

        # Clear tree
        for item in self.cert_tree.get_children():
            self.cert_tree.delete(item)

        # Search
        certificates = self.db.search_certificates(search_term, limit=200)

        for cert in certificates:
            self.cert_tree.insert("", tk.END, iid=cert.id, values=(
                cert.certificate_number_with_rev,
                cert.cert_date or "",
                cert.test_project,
                cert.customer,
                cert.test_standard,
                cert.product_sn
            ))

        self.status_label.config(text=f"Found {len(certificates)} matching '{search_term}'")

    def _clear_search(self):
        """Clear search and reload."""
        self.search_var.set("")
        self._load_certificates()

    def _on_select(self, event):
        """Handle selection - show preview."""
        selection = self.cert_tree.selection()
        if not selection:
            return

        record_id = int(selection[0])
        cert = self.db.get_certificate_by_id(record_id)

        if cert:
            self.selected_certificate = cert

            # Update preview
            self.preview_text.config(state=tk.NORMAL)
            self.preview_text.delete(1.0, tk.END)

            preview = (
                f"Certificate: {cert.certificate_number_with_rev}\n"
                f"Project: {cert.test_project} - {cert.project_name}\n"
                f"Customer: {cert.customer} | Order: {cert.customer_order}\n"
                f"Product S/N: {cert.product_sn} | Material: {cert.material}\n"
                f"Standard: {cert.test_standard} | Specimen: {cert.specimen_id}"
            )
            self.preview_text.insert(tk.END, preview)
            self.preview_text.config(state=tk.DISABLED)

    def _select_certificate(self):
        """Confirm selection and close dialog."""
        if not self.selected_certificate:
            return

        if self.on_select:
            # Prepare data dictionary for import
            data = {
                'certificate_number': self.selected_certificate.certificate_number,
                'test_project': self.selected_certificate.test_project,
                'project_name': self.selected_certificate.project_name,
                'customer': self.selected_certificate.customer,
                'customer_order': self.selected_certificate.customer_order,
                'product_sn': self.selected_certificate.product_sn,
                'specimen_id': self.selected_certificate.specimen_id,
                'location_orientation': self.selected_certificate.location_orientation,
                'material': self.selected_certificate.material,
                'temperature': self.selected_certificate.temperature,
                'test_standard': self.selected_certificate.test_standard,
                'test_date': self.selected_certificate.cert_date,
            }
            self.on_select(data)

        self.dialog.destroy()

    def show(self):
        """Show dialog and wait for result."""
        self.dialog.wait_window()
        return self.selected_certificate


def show_certificate_lookup(parent: tk.Widget, on_select: Callable) -> None:
    """
    Show certificate lookup dialog.

    Parameters
    ----------
    parent : tk.Widget
        Parent widget
    on_select : Callable
        Callback with certificate data dict when selected
    """
    dialog = CertificateLookupDialog(parent, on_select)
    dialog.show()
