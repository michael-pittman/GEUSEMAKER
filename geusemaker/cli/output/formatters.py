"""Helpers for machine-readable CLI output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import click
import yaml

from geusemaker.cli.output.verbosity import VerbosityLevel, get_verbosity


class OutputFormat(str, Enum):
    """Supported output formats."""

    TEXT = "text"
    JSON = "json"
    YAML = "yaml"


def output_option(default: OutputFormat = OutputFormat.TEXT) -> click.Option:
    """Return a Click option for output selection."""
    return click.option(
        "--output",
        type=click.Choice([f.value for f in OutputFormat], case_sensitive=False),
        default=default.value,
        show_default=True,
        help="Output format: text, json, yaml.",
    )


def build_response(
    *,
    status: str = "ok",
    message: str | None = None,
    data: Any = None,
    error_code: str | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    """Build a consistent response envelope for machine-readable output."""
    payload: dict[str, Any] = {
        "status": status,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if message:
        payload["message"] = message
    if error_code:
        payload["error_code"] = error_code
    if errors:
        payload["errors"] = errors
    if data is not None:
        payload["data"] = _normalize(data)
    return payload


def render_output(payload: Any, output_format: OutputFormat) -> str:
    """Serialize payload to the requested format."""
    normalized = _normalize(payload)
    if output_format == OutputFormat.JSON:
        return json.dumps(normalized, indent=2, default=str)
    if output_format == OutputFormat.YAML:
        return yaml.safe_dump(normalized, sort_keys=False)
    return str(payload)


def emit_result(payload: Any, output_format: OutputFormat, verbosity: str = "result") -> None:
    """Print payload using the requested format and honour verbosity."""
    from geusemaker.cli import console

    if output_format == OutputFormat.TEXT:
        console.print(payload, verbosity=verbosity)
        return
    console.print(render_output(payload, output_format), verbosity="result")


def _normalize(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def require_text_output() -> bool:
    """Return True when running in text mode; useful for progress indicators."""
    return get_verbosity() != VerbosityLevel.SILENT


__all__ = [
    "OutputFormat",
    "output_option",
    "build_response",
    "render_output",
    "emit_result",
    "require_text_output",
]
