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
# Enforce the layered architecture (CLI > Orchestration > Services > Infra).
# Invoked via `python -c` rather than the `lint-imports`/`import-linter`
# console scripts so a stale venv shebang can't break the gate; lint_imports()
# returns a non-zero exit code on any broken contract, tripping `set -e`.
python -c "import sys; from importlinter.cli import lint_imports; sys.exit(lint_imports())"
