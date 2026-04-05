#!/usr/bin/env bash
# forge-pane.sh — Dispatch coding agents to visible tmux panes
#
# Usage:
#   forge-pane.sh <pane-name> <prompt>              # Dispatch with auto-detected agent
#   forge-pane.sh <pane-name> <prompt> --agent codex # Override agent
#   forge-pane.sh <pane-name> <prompt> --no-window   # Headless (no Terminal.app)
#   forge-pane.sh <pane-name> <prompt> --cwd /path   # Set working directory
#   forge-pane.sh list                               # List active forge panes
#   forge-pane.sh kill <pane-name>                   # Kill a specific pane
#   forge-pane.sh kill-all                           # Kill entire forge session
#
# Environment:
#   FORGE_AGENT    — Override default coding agent
#   FORGE_SESSION  — Override tmux session name (default: forge)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION="${FORGE_SESSION:-forge}"

# ─── Subcommands ────────────────────────────────────────────────

cmd_list() {
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "No active forge session."
        exit 0
    fi
    echo "Active forge panes ($SESSION):"
    tmux list-panes -t "$SESSION" -F "  #{pane_index}: #{pane_title} (#{pane_current_command})" 2>/dev/null
}

cmd_kill() {
    local name="$1"
    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "No active forge session."
        exit 1
    fi
    # Find pane by title
    local pane_id
    pane_id=$(tmux list-panes -t "$SESSION" -F "#{pane_id}:#{pane_title}" 2>/dev/null \
        | grep ":${name}$" | head -1 | cut -d: -f1)
    if [[ -z "$pane_id" ]]; then
        echo "No pane named '$name' found."
        exit 1
    fi
    tmux kill-pane -t "$pane_id"
    echo "Killed pane: $name"
    # If no panes left, session auto-closes
}

cmd_kill_all() {
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux kill-session -t "$SESSION"
        echo "Killed forge session and all panes."
    else
        echo "No active forge session."
    fi
}

# ─── Detect best coding agent ──────────────────────────────────

detect_agent() {
    if [[ -n "${FORGE_AGENT:-}" ]]; then
        echo "$FORGE_AGENT"
        return
    fi
    if [[ -x "$SCRIPT_DIR/forge-detect.sh" ]]; then
        "$SCRIPT_DIR/forge-detect.sh" --best 2>/dev/null && return
    fi
    # Inline fallback
    for agent in claude codex aider opencode; do
        if command -v "$agent" &>/dev/null; then
            echo "$agent"
            return
        fi
    done
    echo ""
}

# ─── Build the agent command ───────────────────────────────────

build_command() {
    local agent="$1"
    local prompt="$2"
    local cwd="$3"

    local cmd=""
    [[ -n "$cwd" ]] && cmd="cd $(printf '%q' "$cwd") && "

    case "$agent" in
        claude)
            # Note: do NOT use --print or -p flags — they use the alternate screen buffer
            # and render blank in tmux. Interactive mode (--dangerously-skip-permissions only)
            # is the only reliable approach. Prompt is sent via tmux send-keys after load.
            cmd+="claude --dangerously-skip-permissions"
            ;;
        codex)
            cmd+="codex --approval-policy full-auto $(printf '%q' "$prompt")"
            ;;
        aider)
            cmd+="aider --message $(printf '%q' "$prompt")"
            ;;
        opencode)
            cmd+="opencode $(printf '%q' "$prompt")"
            ;;
        *)
            cmd+="$agent $(printf '%q' "$prompt")"
            ;;
    esac

    echo "$cmd"
}

# ─── Dispatch ──────────────────────────────────────────────────

dispatch() {
    local pane_name="$1"
    local prompt="$2"
    local agent_override=""
    local no_window=false
    local cwd=""

    # Parse remaining args
    shift 2
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --agent)   agent_override="$2"; shift 2 ;;
            --no-window) no_window=true; shift ;;
            --cwd)     cwd="$2"; shift 2 ;;
            *)         shift ;;
        esac
    done

    # Determine agent
    local agent="${agent_override:-$(detect_agent)}"
    if [[ -z "$agent" ]]; then
        echo "ERROR: No coding agent found. Install claude, codex, aider, or opencode."
        exit 1
    fi

    # Verify the chosen agent exists
    if ! command -v "$agent" &>/dev/null; then
        echo "ERROR: Agent '$agent' not found in PATH."
        exit 1
    fi

    local agent_cmd
    agent_cmd=$(build_command "$agent" "$prompt" "$cwd")

    # Wrap with header + wait-on-exit
    local pane_cmd
    pane_cmd=$(cat <<PANE_EOF
printf '\033[1;36m── forge: ${pane_name} [$agent] ──\033[0m\n\n'; \
${agent_cmd}; \
EXIT_CODE=\$?; \
echo ""; \
if [ \$EXIT_CODE -eq 0 ]; then \
    printf '\033[1;32m✓ Done.\033[0m Press Enter to close.'; \
else \
    printf '\033[1;31m✗ Exited with code %d.\033[0m Press Enter to close.' \$EXIT_CODE; \
fi; \
read -r
PANE_EOF
)

    local is_new_session=false

    if ! tmux has-session -t "$SESSION" 2>/dev/null; then
        # First pane: create new session
        tmux new-session -d -s "$SESSION" -n forge bash -c "$pane_cmd"
        is_new_session=true
    else
        # Subsequent pane: split and re-tile
        tmux split-window -t "$SESSION" bash -c "$pane_cmd"
        tmux select-layout -t "$SESSION" tiled
    fi

    # Name the pane
    tmux select-pane -t "$SESSION" -T "$pane_name"

    # Open Terminal.app attached to the session (unless --no-window)
    if [[ "$no_window" == false && "$is_new_session" == true ]]; then
        osascript -e "
            tell application \"Terminal\"
                activate
                do script \"tmux attach-session -t ${SESSION}\"
            end tell
        " &>/dev/null &
    fi

    # For Claude: send the prompt via tmux send-keys after it loads.
    # Claude uses an interactive TUI — passing prompt via -p/--print breaks rendering.
    # We wait for Claude to load (trust dialog + prompt ready) then inject the task.
    if [[ "$agent" == "claude" && -n "$prompt" ]]; then
        (
            sleep 5  # Wait for Claude to load and show trust dialog
            # Confirm trust dialog if present (Enter = "Yes, I trust this folder")
            tmux send-keys -t "$SESSION" "" Enter 2>/dev/null
            sleep 2
            # Send the actual prompt
            tmux send-keys -t "$SESSION" "$prompt" Enter 2>/dev/null
        ) &
    fi

    echo "Dispatched '$pane_name' using $agent"
    echo "  Session: $SESSION"
    echo "  Prompt:  ${prompt:0:80}$([ ${#prompt} -gt 80 ] && echo '...')"
}

# ─── Main ──────────────────────────────────────────────────────

if [[ $# -lt 1 ]]; then
    echo "Usage: forge-pane.sh <pane-name> <prompt> [--agent <name>] [--no-window] [--cwd <path>]"
    echo "       forge-pane.sh list"
    echo "       forge-pane.sh kill <name>"
    echo "       forge-pane.sh kill-all"
    exit 1
fi

case "$1" in
    list)     cmd_list ;;
    kill-all) cmd_kill_all ;;
    kill)
        [[ $# -lt 2 ]] && { echo "Usage: forge-pane.sh kill <pane-name>"; exit 1; }
        cmd_kill "$2"
        ;;
    *)
        [[ $# -lt 2 ]] && { echo "Usage: forge-pane.sh <pane-name> <prompt> [options]"; exit 1; }
        dispatch "$@"
        ;;
esac
