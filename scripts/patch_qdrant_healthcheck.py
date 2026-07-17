#!/usr/bin/env python3
"""Patch Qdrant healthcheck in docker-compose.yml to use bash TCP (no curl/wget)."""

import sys
from pathlib import Path

COMPOSE_PATHS = ["/root/docker-compose.yml", "/opt/geusemaker/runtime/docker-compose.yml"]

OLD_PATTERNS = [
    'test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:6333/healthz"]',
    'test: ["CMD-SHELL", "if command -v curl >/dev/null 2>&1; then curl -fsS http://localhost:6333/healthz >/dev/null; elif command -v wget >/dev/null 2>&1; then wget -q -O- http://localhost:6333/healthz >/dev/null; else exit 1; fi"]',
]
NEW_TEST = 'test: ["CMD-SHELL", "bash -c \': > /dev/tcp/127.0.0.1/6333\' || exit 1"]'


def main():
    for path in COMPOSE_PATHS:
        p = Path(path)
        if not p.exists():
            continue
        content = p.read_text()
        for old in OLD_PATTERNS:
            if old in content:
                content = content.replace(old, NEW_TEST)
                p.write_text(content)
                print(f"Patched {path}")
                return 0
        print(f"No matching healthcheck in {path}")
    print("Compose file not found or no match")
    return 1


if __name__ == "__main__":
    sys.exit(main())
