#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
REQUIREMENTS="${SCRIPT_DIR}/requirements.txt"
PYTHON_CMD="${PYTHON_CMD:-python3}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_info() {
    echo -e "${GREEN}[INFO]${NC} $1" >&2
}

echo_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
}

echo_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Start the MCP server for artdaq Deep Investigation Agent."
    echo ""
    echo "Transports:"
    echo "  (default)          stdio transport (for Claude Desktop, VS Code)"
    echo "  --sse              SSE transport (for web clients)"
    echo "  --streamable-http  Streamable HTTP transport (for OpenWebUI)"
    echo ""
    echo "Options:"
    echo "  -p, --port PORT   Port for SSE/Streamable HTTP transport (default: 8001)"
    echo "  -h, --help        Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  ARTDAQ_DATA_DIR   Data directory path (default: ./data)"
    echo ""
    echo "Examples:"
    echo "  $0                        # Start stdio server (Claude Desktop)"
    echo "  $0 --sse                  # Start SSE server on port 8001"
    echo "  $0 --sse --port 9000      # Start SSE server on port 9000"
    echo "  $0 --streamable-http      # Start for OpenWebUI on port 8001"
    echo "  $0 --streamable-http -p 9000  # OpenWebUI on custom port"
    echo ""
    echo "Claude Desktop Configuration:"
    echo "  Add to claude_desktop_config.json:"
    echo "  {"
    echo "    \"mcpServers\": {"
    echo "      \"artdaq-binder\": {"
    echo "        \"command\": \"${SCRIPT_DIR}/run_mcp.sh\""
    echo "      }"
    echo "    }"
    echo "  }"
    echo ""
    echo "OpenWebUI Configuration:"
    echo "  1. Start: $0 --streamable-http --port 8001"
    echo "  2. In OpenWebUI: Admin Settings -> External Tools -> Add Server"
    echo "  3. Type: MCP (Streamable HTTP)"
    echo "  4. URL: http://localhost:8001/mcp (or http://host.docker.internal:8001/mcp)"
    echo ""
}

check_python() {
    if ! command -v ${PYTHON_CMD} &> /dev/null; then
        echo_error "Python 3 is not installed or not in PATH"
        exit 1
    fi

    PYTHON_MAJOR=$(${PYTHON_CMD} -c 'import sys; print(sys.version_info.major)')
    PYTHON_MINOR=$(${PYTHON_CMD} -c 'import sys; print(sys.version_info.minor)')

    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
        PYTHON_VERSION=$(${PYTHON_CMD} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        echo_error "Python 3.10+ is required. Found: ${PYTHON_VERSION}"
        exit 1
    fi
}

setup_venv() {
    if [ ! -d "${VENV_DIR}" ]; then
        echo_info "Virtual environment not found. Creating..."
        check_python

        ${PYTHON_CMD} -m venv "${VENV_DIR}"
        echo_info "Virtual environment created at ${VENV_DIR}"

        source "${VENV_DIR}/bin/activate"

        echo_info "Upgrading pip..."
        pip install --upgrade pip -q

        echo_info "Installing dependencies..."
        pip install -r "${REQUIREMENTS}" -q

        echo_info "Installing artdaq-agent package..."
        pip install -e "${SCRIPT_DIR}" -q

        echo_info "Setup complete."
    else
        source "${VENV_DIR}/bin/activate"
    fi
}

main() {
    for arg in "$@"; do
        case $arg in
            -h|--help)
                show_help
                exit 0
                ;;
        esac
    done

    setup_venv

    artdaq-agent mcp "$@"
}

main "$@"
