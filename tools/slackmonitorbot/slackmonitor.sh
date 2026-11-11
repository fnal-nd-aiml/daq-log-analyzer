#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
PID_FILE="$SCRIPT_DIR/.slackmonitor.pid"

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
            echo -e "${RED}[ERROR]${NC} Slack monitor is already running (PID $old_pid)"
            echo -e "${RED}[ERROR]${NC} Stop it first: $0 stop"
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

if [ "${1:-}" = "stop" ]; then
    if [ -f "$PID_FILE" ]; then
        old_pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$old_pid" ] && _pid_running "$old_pid"; then
            echo -e "${GREEN}[INFO]${NC} Stopping Slack monitor (PID $old_pid)..."
            kill "$old_pid" 2>/dev/null
            for _ in $(seq 1 10); do
                _pid_running "$old_pid" || break
                sleep 0.5
            done
            if _pid_running "$old_pid"; then
                echo -e "${YELLOW}[WARN]${NC} Process did not exit, sending SIGKILL..."
                kill -9 "$old_pid" 2>/dev/null
            fi
            _cleanup_pid
            echo -e "${GREEN}[INFO]${NC} Slack monitor stopped"
        else
            echo -e "${GREEN}[INFO]${NC} Monitor not running (stale PID file removed)"
            _cleanup_pid
        fi
    else
        echo -e "${GREEN}[INFO]${NC} No PID file found – monitor is not running"
    fi
    exit 0
fi

if [ "${1:-}" = "start" ]; then
    _check_already_running
    trap _cleanup_pid EXIT INT TERM
fi

python -m tools.slackmonitorbot.slackmonitor "$@" &
MONITOR_PID=$!

if [ "${1:-}" = "start" ]; then
    echo "$MONITOR_PID" > "$PID_FILE"
fi

wait $MONITOR_PID
