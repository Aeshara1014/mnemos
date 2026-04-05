#!/usr/bin/env bash
# forge-detect.sh — Detect installed coding agents
# Returns the best available agent and lists all found.
#
# Usage:
#   ./forge-detect.sh           # Print recommended agent + all found
#   ./forge-detect.sh --json    # JSON output
#   ./forge-detect.sh --best    # Print only the best agent name (for scripting)
#
# Exit codes:
#   0 — at least one coding agent found
#   1 — no coding agents found

set -euo pipefail

# Priority order: claude > codex > aider > opencode
AGENTS=("claude" "codex" "aider" "opencode")
declare -A FOUND=()
BEST=""

for agent in "${AGENTS[@]}"; do
    if command -v "$agent" &>/dev/null; then
        # Get version (best effort, suppress errors)
        case "$agent" in
            claude)  ver=$("$agent" --version 2>/dev/null | head -1) ;;
            codex)   ver=$("$agent" --version 2>/dev/null | head -1) ;;
            aider)   ver=$("$agent" --version 2>/dev/null | head -1) ;;
            opencode) ver=$("$agent" version 2>/dev/null | head -1) ;;
            *)       ver="unknown" ;;
        esac
        FOUND["$agent"]="${ver:-unknown}"
        [[ -z "$BEST" ]] && BEST="$agent"
    fi
done

if [[ ${#FOUND[@]} -eq 0 ]]; then
    echo "No coding agents found in PATH."
    echo "Install one of: claude, codex, aider, opencode"
    exit 1
fi

MODE="${1:-}"

case "$MODE" in
    --best)
        echo "$BEST"
        ;;
    --json)
        echo "{"
        echo "  \"recommended\": \"$BEST\","
        echo "  \"agents\": {"
        first=true
        for agent in "${AGENTS[@]}"; do
            if [[ -n "${FOUND[$agent]+x}" ]]; then
                $first || echo ","
                printf "    \"%s\": \"%s\"" "$agent" "${FOUND[$agent]}"
                first=false
            fi
        done
        echo ""
        echo "  }"
        echo "}"
        ;;
    *)
        echo "Installed coding agents:"
        for agent in "${AGENTS[@]}"; do
            if [[ -n "${FOUND[$agent]+x}" ]]; then
                marker=""
                [[ "$agent" == "$BEST" ]] && marker=" (recommended)"
                echo "  $agent: ${FOUND[$agent]}$marker"
            fi
        done
        ;;
esac

exit 0
