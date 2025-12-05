#!/usr/bin/env bash
set -euo pipefail

# Build a runtime-bundle tarball from geusemaker/runtime_assets for embedding in UserData.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/.."
ASSET_ROOT="$REPO_ROOT/geusemaker/runtime_assets"
DIST_DIR="$ASSET_ROOT/dist"
OUTPUT="$DIST_DIR/runtime-bundle.tar.gz"

mkdir -p "$DIST_DIR"

if [ ! -d "$ASSET_ROOT" ]; then
    echo "Asset directory not found: $ASSET_ROOT" >&2
    exit 1
fi

echo "Building runtime bundle from $ASSET_ROOT -> $OUTPUT"

# Exclude dist output and common noise files
tar \
  --exclude="dist" \
  --exclude="__pycache__" \
  --exclude=".DS_Store" \
  -czf "$OUTPUT" \
  -C "$ASSET_ROOT" .

echo "Runtime bundle written to $OUTPUT"
