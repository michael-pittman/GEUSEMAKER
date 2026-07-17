#!/usr/bin/env bash
# GeuseMaker TUI launcher — double-click in Finder, or run from a terminal:
#   ./scripts/geusemaker-tui.command
#   ./scripts/geusemaker-tui.command --screen deploy
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$ROOT_DIR/venv"

cd "$ROOT_DIR"

# Prefer the venv interpreter by path (avoids stale shebang paths in console scripts).
if [[ -x "$VENV_DIR/bin/python" ]]; then
  PYTHON="$VENV_DIR/bin/python"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON="$(command -v python3.12)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "Python 3.12+ not found."
  echo "From the repo root, run:"
  echo "  python3.12 -m venv venv && source venv/bin/activate && pip install -e \".[dev,tui]\""
  read -r -p "Press Enter to close…"
  exit 1
fi

if ! "$PYTHON" -c "import geusemaker" >/dev/null 2>&1; then
  echo "GeuseMaker is not installed for: $PYTHON"
  echo "From the repo root, run:"
  echo "  python3.12 -m venv venv && source venv/bin/activate && pip install -e \".[dev,tui]\""
  read -r -p "Press Enter to close…"
  exit 1
fi

if ! "$PYTHON" -c "import textual" >/dev/null 2>&1; then
  echo "Installing optional TUI extra (textual)…"
  "$PYTHON" -m pip install -e ".[tui]"
fi

# Default: full-screen hub (deploy / monitor / inspect). Pass args to override, e.g. --screen deploy
exec "$PYTHON" -m geusemaker tui "$@"
