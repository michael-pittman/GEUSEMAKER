"""Generate sample configuration files."""

from __future__ import annotations

import json
from pathlib import Path

import click
import yaml

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.config import CONFIG_SCHEMA
from geusemaker.models import DeploymentConfig


@click.command("init")
@click.option(
    "--directory",
    "-d",
    type=click.Path(file_okay=False, dir_okay=True, resolve_path=True),
    default=".",
    show_default=True,
    help="Target directory for sample configs.",
)
@click.option("--force", is_flag=True, default=False, help="Overwrite existing sample files.")
def init(directory: str, force: bool) -> None:
    """Generate sample JSON/YAML config files and schema."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    sample_config = DeploymentConfig(
        stack_name="my-stack",
        tier="dev",
        region="us-east-1",
    ).model_dump(mode="python")

    json_path = target / "geusemaker.config.sample.json"
    yaml_path = target / "geusemaker.config.sample.yaml"
    schema_path = target / "geusemaker.config.schema.json"

    for path in (json_path, yaml_path, schema_path):
        if path.exists() and not force:
            raise click.ClickException(f"{path} already exists. Use --force to overwrite.")

    json_path.write_text(json.dumps(sample_config, indent=2))
    yaml_path.write_text(yaml.safe_dump(sample_config, sort_keys=False))
    schema_path.write_text(json.dumps(CONFIG_SCHEMA, indent=2))

    console.print(
        f"{EMOJI['check']} Sample configs created at {target} (JSON, YAML, and JSON Schema).",
        verbosity="result",
    )


__all__ = ["init"]
