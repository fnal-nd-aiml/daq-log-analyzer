#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
PID_FILE="${SCRIPT_DIR}/.slackbot.pid"
API_PID_FILE="${SCRIPT_DIR}/.slackbot-api.pid"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}


_pid_running() {
    kill -0 "$1" 2>/dev/null
}

_check_already_running() {
    if [ -f "$PID_FILE" ]; then
        local old_pid
        old_pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$old_pid" ] && _pid_running "$old_pid"; then
            echo_error "Slack bot is already running (PID $old_pid)"
            echo_error "Stop it first or remove $PID_FILE"
            exit 1
        fi
        echo_warn "Removing stale PID file (PID $old_pid no longer running)"
        rm -f "$PID_FILE"
    fi
}

_write_pid() {
    echo "$1" > "$PID_FILE"
}

_cleanup_pid() {
    rm -f "$PID_FILE"
}

show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Start the Slack bot for artdaq Deep Investigation Agent."
    echo ""
    echo "Options:"
    echo "  --socket          Use Socket Mode (default)"
    echo "  --http            Use HTTP mode"
    echo "  -p, --port PORT   Port for HTTP mode (default: 3000)"
    echo "  --stop            Stop a running Slack bot"
    echo "  --status          Show whether the bot is running"
    echo "  -h, --help        Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  LOGANALYZER_SLACK_BOT_BOT_TOKEN     Bot token (xoxb-...)"
    echo "  LOGANALYZER_SLACK_BOT_APP_TOKEN     App token for Socket Mode (xapp-...)"
    echo "  LOGANALYZER_SLACK_BOT_SIGNING_SECRET  Signing secret for HTTP mode"
    echo ""
    echo "Examples:"
    echo "  $0                    # Start in Socket Mode (recommended)"
    echo "  $0 --http             # Start in HTTP mode on port 3000"
    echo "  $0 --http -p 8080     # Start in HTTP mode on port 8080"
    echo "  $0 --stop             # Stop the running bot"
    echo "  $0 --status           # Check if bot is running"
    echo ""
}

if [ ! -d "${VENV_DIR}" ]; then
    echo_error "Virtual environment not found at ${VENV_DIR}"
    echo_error "Run ./setup.sh first"
    exit 1
fi

source "${VENV_DIR}/bin/activate"

if [ -f "${SCRIPT_DIR}/.env" ]; then
    set -a
    source "${SCRIPT_DIR}/.env"
    set +a
fi

if [ -f "${SCRIPT_DIR}/.env.slack" ]; then
    set -a
    source "${SCRIPT_DIR}/.env.slack"
    set +a
fi

MODE="--socket"
PORT=3000
ACTION="start"

while [[ $# -gt 0 ]]; do
    case $1 in
        --socket)
            MODE="--socket"
            shift
            ;;
        --http)
            MODE="--http"
            shift
            ;;
        -p|--port)
            PORT=$2
            shift 2
            ;;
        --stop)
            ACTION="stop"
            shift
            ;;
        --status)
            ACTION="status"
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo_error "Unknown option: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
done

if [ "$ACTION" = "stop" ]; then
    if [ ! -f "$PID_FILE" ]; then
        echo_info "No PID file found – bot is not running"
        exit 0
    fi
    old_pid=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$old_pid" ] && _pid_running "$old_pid"; then
        echo_info "Stopping Slack bot (PID $old_pid)..."
        kill "$old_pid" 2>/dev/null
        for i in $(seq 1 10); do
            _pid_running "$old_pid" || break
            sleep 0.5
        done
        if _pid_running "$old_pid"; then
            echo_warn "Process did not exit, sending SIGKILL..."
            kill -9 "$old_pid" 2>/dev/null
        fi
        _cleanup_pid
        echo_info "Slack bot stopped"
    else
        echo_info "Bot not running (stale PID file removed)"
        _cleanup_pid
    fi
    exit 0
fi

if [ "$ACTION" = "status" ]; then
    if [ -f "$PID_FILE" ]; then
        old_pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$old_pid" ] && _pid_running "$old_pid"; then
            echo_info "Slack bot is RUNNING (PID $old_pid)"
        else
            echo_info "Slack bot is NOT RUNNING (stale PID file for $old_pid)"
        fi
    else
        echo_info "Slack bot is NOT RUNNING (no PID file)"
    fi
    exit 0
fi

_check_already_running

API_PORT=${API_PORT:-8000}
_ensure_api_server() {
    local api_pid
    if [ -f "$API_PID_FILE" ]; then
        api_pid=$(cat "$API_PID_FILE" 2>/dev/null)
        if [ -n "$api_pid" ] && ! _pid_running "$api_pid"; then
            api_pid=""
            rm -f "$API_PID_FILE"
        fi
    fi
    if [ -z "$api_pid" ]; then
        api_pid=$(pgrep -f "uvicorn srcs.api.*--port ${API_PORT}" 2>/dev/null | head -1)
    fi
    if [ -n "$api_pid" ]; then
        echo_info "Restarting API server (PID $api_pid) to pick up code changes..."
        kill "$api_pid" 2>/dev/null
        sleep 2
        kill -0 "$api_pid" 2>/dev/null && kill -9 "$api_pid" 2>/dev/null
        sleep 1
    fi
    echo_info "Starting API server on port ${API_PORT}..."
    uvicorn srcs.api:app --host 0.0.0.0 --port "$API_PORT" &
    API_PID=$!
    echo "$API_PID" > "$API_PID_FILE"
    for i in $(seq 1 30); do
        if curl -s "http://localhost:${API_PORT}/health" >/dev/null 2>&1; then
            echo_info "API server ready (PID $API_PID)"
            return 0
        fi
        sleep 1
    done
    echo_error "API server failed to start within 30 seconds"
    kill "$API_PID" 2>/dev/null
    rm -f "$API_PID_FILE"
    exit 1
}

_ensure_api_server

_cleanup_all() {
    _cleanup_pid
    if [ -n "$API_PID" ] && _pid_running "$API_PID"; then
        echo_info "Stopping API server (PID $API_PID)..."
        kill "$API_PID" 2>/dev/null
    fi
    rm -f "$API_PID_FILE"
}
trap _cleanup_all EXIT INT TERM

if [ "$MODE" = "--socket" ]; then
    echo_info "Starting Slack bot in Socket Mode..."
    artdaq-agent slack --socket &
else
    echo_info "Starting Slack bot in HTTP mode on port ${PORT}..."
    artdaq-agent slack --http --port "${PORT}" &
fi

BOT_PID=$!
_write_pid $BOT_PID

wait $BOT_PID
