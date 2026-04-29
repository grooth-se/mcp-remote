# Claude Code hooks for TRB App

This directory configures Claude Code's behaviour for the TRB project. It is
shared via Git so both team members get the same gates.

## What gets installed

- **`PreToolUse` Bash guard** — blocks destructive shell commands (`rm -rf /`,
  force-push to main, writes to `.env` or the SQLite DBs, etc).
- **`PostToolUse` formatter** — runs `ruff format` and `ruff check --fix` on
  every Python file Claude edits.
- **`Stop` verification gate** — when Claude thinks it's done, runs lint,
  tests (if present), and a smoke import of the Flask app. Failures are sent
  back to Claude as feedback so it keeps working.
- **`SessionStart` context** — injects Git branch/commit info into every new
  session so Claude knows where things stand.

## One-time setup

The TRB App currently has no formatter, linter, or tests. The hooks degrade
gracefully (skip what's missing) but you'll get the most value once these are
in place. Run from the project root:

```bash
# 0. Install jq if you don't have it (used by hook scripts to parse JSON).
brew install jq

# 1. Install dev tools into the local environment.
pip install ruff pytest

# 2. Make hook scripts executable.
chmod +x .claude/scripts/*.sh

# 3. Create a minimal ruff config in pyproject.toml (or skip — defaults work).
cat > pyproject.toml <<'EOF'
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP"]
ignore = ["E501"]  # line length is handled by formatter

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
EOF

# 4. Add a smoke test so the gate has something real to check.
mkdir -p tests
cat > tests/test_smoke.py <<'EOF'
"""Smoke tests — proves the app boots and basic routes respond."""
import pytest
from app import create_app


@pytest.fixture
def client():
    app = create_app("testing")
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_app_creates():
    app = create_app("testing")
    assert app is not None


def test_index_responds(client):
    # Adjust the path if your landing route is different.
    resp = client.get("/")
    # 200, 302 (redirect to login), or 401 are all "app is alive".
    assert resp.status_code in (200, 302, 401)
EOF
```

## Verifying it works

In Claude Code, run `/hooks` — you should see the four hooks listed. Then ask
Claude to make a trivial edit to a Python file. You should see:

- The file gets formatted automatically (no mention from Claude needed).
- When Claude tries to stop, the verify script runs and either lets it stop
  or sends it back with feedback.

## What's gitignored

`.claude/settings.local.json` — your personal overrides. Don't commit it.
Personal stuff (extra hooks you want for yourself, debug prints, etc.) goes
there.

## Tuning

- **False positives in the Bash guard:** edit the `DANGEROUS_PATTERNS` array
  in `guard-bash.sh`.
- **Verify gate too strict:** comment out sections in `verify.sh` you don't
  want active yet (the smoke import gate is the one most worth keeping).
- **Verify gate not strict enough:** uncomment the mypy block (you'll need to
  `pip install mypy` and add `[tool.mypy]` config).

## Common pitfalls

- **Infinite Stop loop:** if Claude keeps getting stuck retrying, check that
  `verify.sh` honours `stop_hook_active`. The version here does.
- **Hooks not firing:** run `/hooks` inside Claude Code to see what it's
  actually loaded. If your edit to `settings.json` isn't showing up, restart
  the session.
- **Conda vs system Python:** the hooks call `ruff`, `pytest`, `python` from
  whatever PATH is active when Claude Code launches. Activate the right env
  before starting Claude Code, or hardcode the interpreter path in the
  scripts.
