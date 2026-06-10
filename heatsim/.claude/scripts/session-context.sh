#!/bin/bash
# Inject useful project context at the start of each session.
# Stdout (as JSON with hookSpecificOutput.additionalContext) is added to
# Claude's context so it knows where things stand without you having to say.

set -euo pipefail

cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0

BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
LAST_COMMIT=$(git log -1 --oneline 2>/dev/null || echo "no commits")
STATUS=$(git status --short 2>/dev/null | head -20 || echo "")
RECENT=$(git log --oneline -5 2>/dev/null || echo "")

CONTEXT="Heatsim project context:
- Branch: $BRANCH
- Last commit: $LAST_COMMIT
- Recent commits:
$RECENT
- Working tree status:
${STATUS:-clean}

Stack: Flask 3 + SQLAlchemy (dual bind: users.db + materials.db) + COMSOL/PyVista, Python 3.11, run.py on :5004
Run locally: MPLBACKEND=Agg PYVISTA_OFF_SCREEN=true python run.py
Production: Docker + gunicorn behind nginx (subseavm01)
"

# Emit as JSON for Claude Code to ingest as additionalContext.
jq -n --arg ctx "$CONTEXT" '{
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $ctx
  }
}'
