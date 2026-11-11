#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"

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

python -m tools.mcptester.mcptester "$@"
