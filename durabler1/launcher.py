#!/usr/bin/env python3
"""
Durabler - Mechanical Testing Analysis System
Main application launcher.

ISO 17025 compliant analysis for:
- Tensile testing (ASTM E8/E8M)
- More test methods coming soon

Usage:
    python launcher.py
"""

import sys
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


def main():
    """Launch the Durabler application."""
    print("=" * 60)
    print("Durabler - Mechanical Testing Analysis System")
    print("ISO 17025 Compliant - ASTM E8/E8M Tensile Testing")
    print("=" * 60)
    print()

    # Check dependencies
    if not check_dependencies():
        sys.exit(1)

    print("Starting GUI...")
    print()

    # Import and run main application
    from utils.ui.main_window import TensileTestApp

    app = TensileTestApp()
    app.run()


if __name__ == "__main__":
    main()
