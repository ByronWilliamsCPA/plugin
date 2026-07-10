#!/usr/bin/env bash
# rad-strict-hook.sh -- PreToolUse Bash hook for /rad-strict mode
# Only activates when RAD_STRICT_MODE=1 is set by the /rad-strict skill invocation.
# Registration: add a PreToolUse Bash entry in settings.json pointing to this script.
set -euo pipefail

[[ "${RAD_STRICT_MODE:-0}" != "1" ]] && exit 0

echo "[rad-strict-hook] active: RAD_STRICT_MODE=1" >&2

CONTEXT=$(cat)
COMMAND=$(jq -r '.tool_input.command // empty' <<< "$CONTEXT")
if echo "$COMMAND" | grep -q 'git commit' && grep -rn '#VERIFY' "${CLAUDE_PROJECT_DIR:-.}" --include='*.py' --include='*.ts' 2>/dev/null | grep -q .; then
  echo "ERROR: Unresolved #VERIFY annotations exist. Resolve before committing." >&2
  exit 2
fi
exit 0
