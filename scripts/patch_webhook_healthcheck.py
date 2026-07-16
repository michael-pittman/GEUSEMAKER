#!/usr/bin/env python3
"""Patch webhook-alias healthcheck from wget to curl."""
from pathlib import Path

COMPOSE = Path("/root/docker-compose.yml")
OLD = 'test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8088/healthz"]'
NEW = 'test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8088/healthz"]'

def main():
    if not COMPOSE.exists():
        print("Compose not found")
        return 1
    content = COMPOSE.read_text()
    if OLD not in content:
        print("Pattern not found")
        return 1
    content = content.replace(OLD, NEW)
    COMPOSE.write_text(content)
    print("Patched")
    return 0

if __name__ == "__main__":
    exit(main())
