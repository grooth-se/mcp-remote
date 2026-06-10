# Claude Code hooks for Heatsim

This directory configures Claude Code's behaviour for the Heatsim project. It is
shared via Git so collaborators get the same gates.

## What gets installed

- **`PreToolUse` Bash guard** — blocks destructive shell commands (`rm -rf /`,
  force-push to main, writes to `.env` or `instance/users.db` / `instance/materials.db`, etc).
- **`PostToolUse` formatter** — runs `ruff format` and `ruff check --fix` on
  every Python file Claude edits.
- **`Stop` verification gate** — when Claude thinks it's done, runs lint,
  smoke tests, and a smoke import of the Flask app (with `PYVISTA_OFF_SCREEN=true`
  / `MPLBACKEND=Agg` set so VTK doesn't try to open a window). Failures are
  sent back to Claude as feedback so it keeps working.
- **`SessionStart` context** — injects Git branch/commit info and a short
  stack reminder into every new session.

## One-time setup

The hooks degrade gracefully (skip what's missing) but you'll get the most
value once the tooling is installed. Run from the project root:

```bash
# 0. Install jq if you don't have it (used by hook scripts to parse JSON).
brew install jq

# 1. Install dev tools into the active environment.
pip install ruff pytest

# 2. Make hook scripts executable (only needed once).
chmod +x .claude/scripts/*.sh
```

`pyproject.toml` already contains the ruff + pytest config (line length 100,
py311 target, comsol marker registered). `tests/test_smoke.py` is the smoke
suite the Stop gate runs by default.

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

- **False positives in the Bash guard:** edit the `DANGEROUS_PATTERNS` or
  `SENSITIVE_PATHS` arrays in `guard-bash.sh`.
- **Verify gate too strict:** comment out sections in `verify.sh` you don't
  want active yet (the smoke import gate is the one most worth keeping).
- **Verify gate too slow:** the Stop gate runs only `tests/test_smoke.py` by
  default. Switch to `pytest -x --tb=short -q` in `verify.sh` if you want the
  full 619-test suite to run on every Stop (slower; consider only doing it
  before committing).

## Common pitfalls

- **Infinite Stop loop:** if Claude keeps getting stuck retrying, check that
  `verify.sh` honours `stop_hook_active`. The version here does.
- **Hooks not firing:** run `/hooks` inside Claude Code to see what it's
  actually loaded. If your edit to `settings.json` isn't showing up, restart
  the session.
- **PyVista/VTK errors during smoke import:** `verify.sh` exports
  `MPLBACKEND=Agg` and `PYVISTA_OFF_SCREEN=true` before importing the app.
  If you run the smoke check by hand, set those envs yourself.
- **Conda vs system Python:** the hooks call `ruff`, `pytest`, `python` from
  whatever PATH is active when Claude Code launches. Activate the right env
  before starting Claude Code, or hardcode the interpreter path in the
  scripts.
