"""Helpers for machine-readable CLI output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import click
import yaml

from geusemaker.cli.output.verbosity import (
    VerbosityLevel,
    get_verbosity,
    set_machine_output,
)


class OutputFormat(str, Enum):
    """Supported output formats."""

    TEXT = "text"
    JSON = "json"
    YAML = "yaml"


def _activate_machine_output(ctx: click.Context, param: click.Parameter, value: str) -> str:  # noqa: ARG001
    """Reserve stdout for the structured document as soon as --output is parsed."""
    if value and value.lower() != OutputFormat.TEXT.value:
        set_machine_output(True)
    return value


def output_option(default: OutputFormat = OutputFormat.TEXT) -> click.Option:
    """Return a Click option for output selection."""
    return click.option(
        "--output",
        type=click.Choice([f.value for f in OutputFormat], case_sensitive=False),
        default=default.value,
        show_default=True,
        callback=_activate_machine_output,
        help="Output format: text, json, yaml. json/yaml emit one document on stdout; diagnostics go to stderr.",
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
    """Print payload using the requested format and honour verbosity.

    json/yaml documents are written raw to stdout via click.echo — never through
    Rich, which could soft-wrap long lines and corrupt the document.
    """
    from geusemaker.cli import console

    if output_format == OutputFormat.TEXT:
        console.print(payload, verbosity=verbosity)
        return
    click.echo(render_output(payload, output_format))


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
