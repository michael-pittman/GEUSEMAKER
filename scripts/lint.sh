#!/usr/bin/env bash
set -euo pipefail

# Use venv if available, otherwise assume tools are in PATH
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/../venv"

if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
fi

ruff check .
ruff format --check .
mypy geusemaker
