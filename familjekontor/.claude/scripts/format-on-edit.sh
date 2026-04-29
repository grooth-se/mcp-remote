#!/bin/bash
# Auto-format Python files after Claude edits them.
# Silently no-ops on non-Python files or if ruff isn't installed.

set -euo pipefail

INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')

# Only act on Python files
if [[ "$FILE" != *.py ]]; then
  exit 0
fi

# Skip if file no longer exists (could happen with rapid edits)
if [[ ! -f "$FILE" ]]; then
  exit 0
fi

# Use ruff if available; fall back to a no-op rather than failing.
if ! command -v ruff >/dev/null 2>&1; then
  # Don't block Claude on missing tooling; just inform.
  echo "ruff not installed - skipping format. Run: pip install ruff" >&2
  exit 0
fi

# Format and auto-fix lints. We don't want this to block Claude's flow,
# so even if ruff finds issues it can't fix, exit 0 and let the Stop gate
# surface them.
ruff format "$FILE" 2>/dev/null || true
ruff check --fix "$FILE" 2>/dev/null || true

exit 0
