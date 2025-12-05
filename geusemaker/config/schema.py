"""Configuration schema helpers."""

from __future__ import annotations

from typing import Any

from geusemaker.config.loader import ENV_VAR_MAP
from geusemaker.models import DeploymentConfig


def config_schema() -> dict[str, Any]:
    """Return JSON schema for DeploymentConfig."""
    schema = DeploymentConfig.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "GeuseMaker Deployment Configuration"
    return schema


CONFIG_SCHEMA = config_schema()


def environment_variables() -> list[dict[str, str]]:
    """Return a mapping of config fields to environment variables for docs."""
    return [{"field": field, "env": env} for field, env in ENV_VAR_MAP.items()]


__all__ = ["config_schema", "CONFIG_SCHEMA", "environment_variables"]
