#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
PID_FILE="$SCRIPT_DIR/.slacktester.pid"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

_pid_running() { kill -0 "$1" 2>/dev/null; }

_check_already_running() {
    if [ -f "$PID_FILE" ]; then
        local old_pid
        old_pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$old_pid" ] && _pid_running "$old_pid"; then
            echo -e "${RED}[ERROR]${NC} Slack tester is already running (PID $old_pid)"
            echo -e "${RED}[ERROR]${NC} Wait for it to finish or kill PID $old_pid"
            exit 1
        fi
        echo -e "${YELLOW}[WARN]${NC} Removing stale PID file (PID $old_pid no longer running)"
        rm -f "$PID_FILE"
    fi
}

_cleanup_pid() { rm -f "$PID_FILE"; }

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"

    echo "Installing dependencies..."
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip -q
    pip install -r "$REQUIREMENTS" -q
    echo "Setup complete."
else
    source "$VENV_DIR/bin/activate"
fi

PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

case "${1:-}" in
    run|send)
        _check_already_running
        trap _cleanup_pid EXIT INT TERM
        python -m tools.slacktesterbot.slacktester "$@" &
        echo "$!" > "$PID_FILE"
        wait $!
        ;;
    *)
        python -m tools.slacktesterbot.slacktester "$@"
        ;;
esac
