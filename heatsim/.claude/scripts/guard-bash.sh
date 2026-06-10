#!/bin/bash
# Block obviously destructive Bash commands.
# Reads JSON from stdin, exit 2 = block + send stderr to Claude as feedback.

set -euo pipefail

INPUT=$(cat)
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Patterns that should never run unattended.
# Tune this list to taste.
DANGEROUS_PATTERNS=(
  'rm -rf /'
  'rm -rf ~'
  'rm -rf \$HOME'
  'rm -rf \*'
  'sudo rm'
  'dd if=.*of=/dev/'
  'mkfs\.'
  ':\(\)\{ :\|:&'           # fork bomb
  '> /dev/sda'
  'chmod -R 777 /'
  'git push --force.*main'  # protect main branch
  'git push -f.*main'
  'docker system prune -a'  # nukes images on this machine
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$CMD" | grep -qE "$pattern"; then
    echo "BLOCKED: command matched dangerous pattern '$pattern'." >&2
    echo "If this is intentional, run it manually outside Claude Code." >&2
    exit 2
  fi
done

# Block writes to sensitive paths
SENSITIVE_PATHS=(
  '\.env($|[^.])'
  'instance/users\.db'
  'instance/materials\.db'
  '\.git/config'
)

for pattern in "${SENSITIVE_PATHS[@]}"; do
  if echo "$CMD" | grep -qE "(>|>>|rm|mv|cp).*$pattern"; then
    echo "BLOCKED: refusing to modify sensitive path matching '$pattern'." >&2
    echo "Make this change manually if intentional." >&2
    exit 2
  fi
done

exit 0
