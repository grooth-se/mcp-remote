#!/usr/bin/env python3
"""
Durabler - Mechanical Testing Analysis System
Main application launcher.

ISO 17025 compliant analysis for:
- Tensile testing (ASTM E8/E8M)
- Sonic Resonance (ASTM E1875)
- FCGR (ASTM E647)
- CTOD (ASTM E1820)
- KIC (ASTM E399)
- Vickers Hardness (ISO 6507-1)

Usage:
    python launcher.py
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def check_dependencies():
    """Check that required packages are installed."""
    missing = []

    try:
        import numpy
    except ImportError:
        missing.append('numpy')

    try:
        import pandas
    except ImportError:
        missing.append('pandas')

    try:
        import scipy
    except ImportError:
        missing.append('scipy')

    try:
        import matplotlib
    except ImportError:
        missing.append('matplotlib')

    if missing:
        print("Missing required packages:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nInstall with: pip install " + " ".join(missing))
        return False

    return True


class DurablerLauncher:
    """
    Main launcher window for Durabler test methods.

    Provides buttons to launch each test method application.
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Durabler - Mechanical Testing Analysis System")
        self.root.geometry("500x600")
        self.root.resizable(False, False)

        # Center window on screen
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() - 500) // 2
        y = (self.root.winfo_screenheight() - 600) // 2
        self.root.geometry(f"500x600+{x}+{y}")

        self._create_ui()

    def _create_ui(self):
        """Create the launcher UI."""
        # Header
        header_frame = ttk.Frame(self.root, padding=20)
        header_frame.pack(fill=tk.X)

        ttk.Label(
            header_frame,
            text="Durabler",
            font=('Helvetica', 24, 'bold')
        ).pack()

        ttk.Label(
            header_frame,
            text="Mechanical Testing Analysis System",
            font=('Helvetica', 12)
        ).pack()

        ttk.Label(
            header_frame,
            text="ISO 17025 Compliant",
            font=('Helvetica', 10, 'italic')
        ).pack(pady=(5, 0))

        # Separator
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=20)

        # Test methods frame
        methods_frame = ttk.LabelFrame(
            self.root, text="Test Methods", padding=20
        )
        methods_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Test method buttons
        test_methods = [
            ("Tensile Testing", "ASTM E8/E8M, ISO 6892-1",
             self.launch_tensile, True),
            ("Sonic Resonance", "ASTM E1875 (Modified)",
             self.launch_sonic, False),
            ("Fatigue Crack Growth (FCGR)", "ASTM E647",
             self.launch_fcgr, False),
            ("CTOD Testing", "ASTM E1820, E1290, BS 7448",
             self.launch_ctod, False),
            ("Fracture Toughness (KIC)", "ASTM E399",
             self.launch_kic, False),
            ("Vickers Hardness", "ISO 6507-1, ASTM E92",
             self.launch_vickers, False),
        ]

        for i, (name, standard, command, available) in enumerate(test_methods):
            frame = ttk.Frame(methods_frame)
            frame.pack(fill=tk.X, pady=5)

            btn = ttk.Button(
                frame,
                text=name,
                command=command,
                width=30,
                state=tk.NORMAL if available else tk.DISABLED
            )
            btn.pack(side=tk.LEFT)

            status = "" if available else " (Coming soon)"
            ttk.Label(
                frame,
                text=f"{standard}{status}",
                font=('Helvetica', 9),
                foreground='gray'
            ).pack(side=tk.LEFT, padx=10)

        # Footer
        footer_frame = ttk.Frame(self.root, padding=10)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM)

        ttk.Label(
            footer_frame,
            text="Version 0.1.0",
            font=('Helvetica', 9),
            foreground='gray'
        ).pack(side=tk.LEFT)

        ttk.Button(
            footer_frame,
            text="Exit",
            command=self.root.quit
        ).pack(side=tk.RIGHT)

        ttk.Button(
            footer_frame,
            text="About",
            command=self.show_about
        ).pack(side=tk.RIGHT, padx=5)

    def launch_tensile(self):
        """Launch tensile testing application."""
        self.root.withdraw()  # Hide launcher

        from utils.ui.main_window import TensileTestApp
        app = TensileTestApp(parent_launcher=self)
        app.run()

    def launch_sonic(self):
        """Launch sonic resonance application."""
        messagebox.showinfo(
            "Coming Soon",
            "Sonic Resonance (ASTM E1875) module is under development."
        )

    def launch_fcgr(self):
        """Launch FCGR application."""
        messagebox.showinfo(
            "Coming Soon",
            "Fatigue Crack Growth Rate (ASTM E647) module is under development."
        )

    def launch_ctod(self):
        """Launch CTOD application."""
        messagebox.showinfo(
            "Coming Soon",
            "CTOD (ASTM E1820) module is under development."
        )

    def launch_kic(self):
        """Launch KIC application."""
        messagebox.showinfo(
            "Coming Soon",
            "Fracture Toughness KIC (ASTM E399) module is under development."
        )

    def launch_vickers(self):
        """Launch Vickers hardness application."""
        messagebox.showinfo(
            "Coming Soon",
            "Vickers Hardness (ISO 6507-1) module is under development."
        )

    def show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About Durabler",
            "Durabler - Mechanical Testing Analysis System\n\n"
            "Version: 0.1.0\n\n"
            "ISO 17025 compliant analysis system for\n"
            "mechanical testing laboratories.\n\n"
            "Supports:\n"
            "- Tensile testing (ASTM E8/E8M)\n"
            "- More test methods coming soon\n\n"
            "All results include measurement uncertainty\n"
            "following GUM methodology (k=2)."
        )

    def show(self):
        """Show the launcher window."""
        self.root.deiconify()

    def run(self):
        """Start the launcher main loop."""
        self.root.mainloop()


def main():
    """Launch the Durabler application."""
    print("=" * 60)
    print("Durabler - Mechanical Testing Analysis System")
    print("ISO 17025 Compliant")
    print("=" * 60)
    print()

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    print("Starting launcher...")
    print()

    launcher = DurablerLauncher()
    launcher.run()


if __name__ == "__main__":
    main()
