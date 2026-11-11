#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/venv"
PYTHON_CMD="${PYTHON_CMD:-python3}"

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

check_python() {
    if ! command -v ${PYTHON_CMD} &> /dev/null; then
        echo_error "Python 3 is not installed or not in PATH"
        exit 1
    fi

    PYTHON_VERSION=$(${PYTHON_CMD} -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$(${PYTHON_CMD} -c 'import sys; print(sys.version_info.major)')
    PYTHON_MINOR=$(${PYTHON_CMD} -c 'import sys; print(sys.version_info.minor)')

    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
        echo_error "Python 3.10+ is required. Found: ${PYTHON_VERSION}"
        exit 1
    fi

    echo_info "Found Python ${PYTHON_VERSION}"
}

create_venv() {
    if [ -d "${VENV_DIR}" ]; then
        echo_info "Virtual environment already exists at ${VENV_DIR}"
    else
        echo_info "Creating virtual environment at ${VENV_DIR}"
        ${PYTHON_CMD} -m venv "${VENV_DIR}"
        echo_info "Virtual environment created"
    fi
}

activate_venv() {
    echo_info "Activating virtual environment"
    source "${VENV_DIR}/bin/activate"
}

upgrade_pip() {
    echo_info "Upgrading pip"
    pip install --upgrade pip
}

install_deps() {
    local DEV_MODE=$1

    if [ "$DEV_MODE" = "true" ]; then
        echo_info "Installing development dependencies"
        pip install -r "${SCRIPT_DIR}/requirements-dev.txt"
    else
        echo_info "Installing production dependencies"
        pip install -r "${SCRIPT_DIR}/requirements.txt"
    fi

    echo_info "Installing artdaq-agent in editable mode"
    pip install -e "${SCRIPT_DIR}"
}

init_data() {
    DATA_DIR="${SCRIPT_DIR}/data"
    if [ ! -d "${DATA_DIR}" ]; then
        echo_info "Creating data directory at ${DATA_DIR}"
        mkdir -p "${DATA_DIR}/chroma"
    else
        echo_info "Data directory already exists"
    fi
}

print_instructions() {
    echo ""
    echo_info "Setup complete!"
    echo ""
    echo "To activate the virtual environment, run:"
    echo "  source ${VENV_DIR}/bin/activate"
    echo ""
    echo "Then you can use the CLI:"
    echo "  artdaq-agent --help"
    echo "  artdaq-agent init"
    echo "  artdaq-agent investigate <logfile>"
    echo ""
    echo "Or start the API server:"
    echo "  uvicorn srcs.api:app --reload --port 8000"
    echo ""
}

main() {
    local DEV_MODE="false"

    while [[ $# -gt 0 ]]; do
        case $1 in
            --dev|-d)
                DEV_MODE="true"
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [--dev]"
                echo ""
                echo "Options:"
                echo "  --dev, -d    Install development dependencies"
                echo "  --help, -h   Show this help message"
                exit 0
                ;;
            *)
                echo_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    echo "=========================================="
    echo " artdaq Deep Investigation Agent Setup"
    echo "=========================================="
    echo ""

    check_python
    create_venv
    activate_venv
    upgrade_pip
    install_deps "$DEV_MODE"
    init_data
    print_instructions
}

main "$@"
