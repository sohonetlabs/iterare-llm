#!/bin/bash
set -e

# Entrypoint script for iterare Docker container
# This script:
# 1. Verifies credentials are mounted
# 2. Runs firewall initialization (REQUIRED for security)
# 3. Launches Claude Code (interactive or with prompt)
#
# Environment variables:
# - ITERARE_MODE: Set to "interactive" for interactive mode, otherwise runs with prompt

echo "Starting iterare container..."

# Determine mode
MODE="${ITERARE_MODE:-prompt}"
echo "=== DEBUG: ITERARE_MODE='${ITERARE_MODE}' ==="
echo "=== DEBUG: MODE='${MODE}' ==="

# Verify credentials are mounted
if [ ! -f "$HOME/.claude/.credentials.json" ]; then
    echo "Error: Claude credentials not found at $HOME/.claude/.credentials.json"
    echo "Make sure ~/.iterare/.credentials.json exists on the host"
    exit 1
fi

if [ ! -f "$HOME/.claude.json" ]; then
    echo "Error: Claude config not found at $HOME/.claude.json"
    echo "Make sure ~/.iterare/.claude.json exists on the host"
    exit 1
fi

echo "Credentials verified"

# Run firewall initialization - REQUIRED for network isolation
if [ ! -f /usr/local/bin/init-firewall.sh ]; then
    echo "Error: Firewall script not found at /usr/local/bin/init-firewall.sh"
    echo "Network isolation is required for security. Exiting."
    exit 1
fi

echo "Initializing firewall rules..."
if ! sudo /usr/local/bin/init-firewall.sh; then
    echo "Error: Firewall initialization failed"
    echo "Network isolation is required for security. Exiting."
    exit 1
fi

echo "Firewall rules initialized successfully"

# Change to workspace directory
cd /workspace

if [ "$MODE" = "interactive" ]; then
    # Interactive mode - launch Claude Code for interactive use
    echo "Launching Claude Code in interactive mode..."
    echo "Type 'exit' or press Ctrl+D to end the session."
    echo ""

    # Launch Claude Code interactively with dangerous permissions
    # --dangerously-skip-permissions: Bypass all permission checks (safe in sandboxed environment)
    exec claude --dangerously-skip-permissions
else
    # Prompt mode - verify prompt file and run non-interactively
    if [ ! -f /workspace/.claude-prompt.md ]; then
        echo "Error: Prompt file not found at /workspace/.claude-prompt.md"
        exit 1
    fi

    echo "Launching Claude Code with prompt..."

    # Launch Claude Code in non-interactive mode with dangerous permissions
    # --print: Non-interactive mode that prints response and exits
    # --output-format=stream-json: Real-time streaming output
    # --dangerously-skip-permissions: Bypass all permission checks (safe in sandboxed environment)
    # Use tee to write output to both stdout and the log file
    claude --print --verbose --output-format=stream-json --dangerously-skip-permissions "$(cat /workspace/.claude-prompt.md)" | tee /var/log/iterare.log | jq -r '
if .type == "assistant" then
  .message.content[] |
  if .type == "text" then
    "💬 Claude: " + .text
  elif .type == "tool_use" then
    "🔧 Tool: " + .name + "\n   " + (if .input.description then .input.description elif .input.command then .input.command else (.input | tostring | .[0:200]) end)
  else empty end
elif .type == "user" then
  .message.content[] |
  select(.type == "tool_result") |
  "📦 Result: " + (if (.content | length) > 200 then (.content | .[0:200]) + "..." else .content end)
elif .type == "result" then
  "\n✅ Complete in " + ((.duration_ms / 1000) | tostring) + "s (cost: $" + (.total_cost_usd | tostring) + ")\n   Turns: " + (.num_turns | tostring)
else empty end
'
fi
