#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  cli [ARGS]              Run CLI (artdaq-agent) with arguments"
    echo "  api [--port PORT]       Start the REST API server (default port: 8000)"
    echo "  mcp [--sse] [--port]    Start MCP server (default: stdio transport)"
    echo "  investigate <logfile>   Shortcut: investigate a log file"
    echo "  feedback <id> [ARGS]    Shortcut: submit feedback for investigation"
    echo "  init                    Shortcut: initialize knowledge base"
    echo ""
    echo "Examples:"
    echo "  $0 api                              # Start API on port 8000"
    echo "  $0 api --port 8080                  # Start API on port 8080"
    echo "  $0 mcp                              # Start MCP server (stdio)"
    echo "  $0 mcp --sse --port 8001            # Start MCP server (SSE)"
    echo "  $0 cli --help                       # Show CLI help"
    echo "  $0 investigate logs/sample.log      # Investigate a log file"
    echo "  $0 investigate logs/app.log -e 150  # Investigate specific error line"
    echo "  $0 feedback inv-123 --correct       # Mark investigation as correct"
    echo "  $0 init                             # Initialize knowledge base"
    echo ""
}

if [ ! -d "${VENV_DIR}" ]; then
    echo_error "Virtual environment not found at ${VENV_DIR}"
    echo_error "Run ./setup.sh first"
    exit 1
fi

source "${VENV_DIR}/bin/activate"

if [ $# -eq 0 ]; then
    show_help
    exit 0
fi

COMMAND=$1
shift

case $COMMAND in
    api)
        PORT=8000
        RELOAD=""

        while [[ $# -gt 0 ]]; do
            case $1 in
                --port|-p)
                    PORT=$2
                    shift 2
                    ;;
                --reload|-r)
                    RELOAD="--reload"
                    shift
                    ;;
                *)
                    shift
                    ;;
            esac
        done

        echo_info "Starting API server on port ${PORT}"
        uvicorn srcs.api:app --host 0.0.0.0 --port ${PORT} ${RELOAD}
        ;;

    cli)
        artdaq-agent "$@"
        ;;

    investigate)
        artdaq-agent investigate "$@"
        ;;

    feedback)
        artdaq-agent feedback "$@"
        ;;

    init)
        artdaq-agent init "$@"
        ;;

    mcp)
        artdaq-agent mcp "$@"
        ;;

    --help|-h|help)
        show_help
        ;;

    *)
        echo_error "Unknown command: ${COMMAND}"
        echo ""
        show_help
        exit 1
        ;;
esac
