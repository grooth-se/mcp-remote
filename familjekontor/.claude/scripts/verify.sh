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
if command -v pytest >/dev/null 2>&1; then
  if [ -d "tests" ] || [ -f "conftest.py" ]; then
    if ! TEST_OUT=$(pytest -x --tb=short -q 2>&1); then
      FEEDBACK+=$'\n\n=== Test failures (pytest) ===\n'"$TEST_OUT"
      FAILED=1
    fi
  else
    echo "Note: no tests/ directory yet - skipping test gate." >&2
  fi
else
  echo "Note: pytest not installed - skipping test gate." >&2
fi

# --- Decide ---------------------------------------------------------------
if [ "$FAILED" -eq 1 ]; then
  echo "Verification gate failed. Fix the issues below before stopping:" >&2
  echo "$FEEDBACK" >&2
  exit 2
fi

exit 0
