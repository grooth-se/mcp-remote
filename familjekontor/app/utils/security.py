"""Security utilities for path traversal prevention."""

import os


def safe_path(base_dir, untrusted_path):
    """Resolve path and ensure it stays within base_dir.

    Raises ValueError if the resolved path escapes base_dir.
    """
    base = os.path.realpath(base_dir)
    full = os.path.realpath(os.path.join(base, untrusted_path))
    if not full.startswith(base + os.sep) and full != base:
        raise ValueError('Path traversal detected')
    return full
