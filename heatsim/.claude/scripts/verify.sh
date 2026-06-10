#!/bin/bash
# Verification gate: runs when Claude tries to stop.
# Exit 2 = block stopping + send stderr back as feedback so Claude keeps working.
# Exit 0 = let Claude stop normally.

set -uo pipefail  # not -e: we want to control exit explicitly

INPUT=$(cat)

# CRITICAL: prevent infinite loops. If Stop has already fired and we
# blocked once, let the next attempt through to avoid wedging Claude.
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [ "$STOP_ACTIVE" = "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR" || exit 0

# Heatsim needs offscreen rendering envs set or PyVista/VTK will hang.
export MPLBACKEND=Agg
export PYVISTA_OFF_SCREEN=true

FAILED=0
FEEDBACK=""

# --- Lint gate (ruff) ----------------------------------------------------
if command -v ruff >/dev/null 2>&1; then
  if ! LINT_OUT=$(ruff check . 2>&1); then
    FEEDBACK+=$'\n=== Lint errors (ruff) ===\n'"$LINT_OUT"
    FAILED=1
  fi
else
  # Don't block on missing tooling on first install
  echo "Note: ruff not installed - skipping lint gate." >&2
fi

# --- Test gate (pytest) --------------------------------------------------
# Only the smoke tests by default so the Stop gate stays fast.
# Switch to `pytest -x --tb=short -q` for the full suite if desired.
if command -v pytest >/dev/null 2>&1; then
  if [ -f "tests/test_smoke.py" ]; then
    if ! TEST_OUT=$(pytest tests/test_smoke.py -x --tb=short -q 2>&1); then
      FEEDBACK+=$'\n\n=== Smoke test failures (pytest) ===\n'"$TEST_OUT"
      FAILED=1
    fi
  else
    echo "Note: tests/test_smoke.py missing - skipping test gate." >&2
  fi
else
  echo "Note: pytest not installed - skipping test gate." >&2
fi

# --- Smoke check: does the app at least import? -------------------------
# Lightweight gate that's useful even before formal tests exist.
if [ -f "run.py" ]; then
  if ! IMPORT_OUT=$(python -c "import app; app.create_app('testing')" 2>&1); then
    FEEDBACK+=$'\n\n=== Flask app failed to import ===\n'"$IMPORT_OUT"
    FAILED=1
  fi
fi

# --- Decide ---------------------------------------------------------------
if [ "$FAILED" -eq 1 ]; then
  echo "Verification gate failed. Fix the issues below before stopping:" >&2
  echo "$FEEDBACK" >&2
  exit 2
fi

exit 0
