"""Load deployment configuration from files, environment variables, and CLI overrides."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args, get_origin

import yaml
from pydantic import ValidationError

from geusemaker.models import DeploymentConfig

BOOL_TRUE = {"1", "true", "yes", "on", "y", "t"}
BOOL_FALSE = {"0", "false", "no", "off", "n", "f"}


ENV_VAR_MAP: dict[str, str] = {
    "stack_name": "GEUSEMAKER_STACK_NAME",
    "tier": "GEUSEMAKER_TIER",
    "region": "GEUSEMAKER_REGION",
    "instance_type": "GEUSEMAKER_INSTANCE_TYPE",
    "use_spot": "GEUSEMAKER_USE_SPOT",
    "os_type": "GEUSEMAKER_OS_TYPE",
    "architecture": "GEUSEMAKER_ARCHITECTURE",
    "ami_type": "GEUSEMAKER_AMI_TYPE",
    "budget_limit": "GEUSEMAKER_BUDGET",
    "vpc_id": "GEUSEMAKER_VPC_ID",
    "subnet_id": "GEUSEMAKER_SUBNET_ID",
    "public_subnet_ids": "GEUSEMAKER_PUBLIC_SUBNET_IDS",
    "private_subnet_ids": "GEUSEMAKER_PRIVATE_SUBNET_IDS",
    "storage_subnet_id": "GEUSEMAKER_STORAGE_SUBNET_ID",
    "security_group_id": "GEUSEMAKER_SECURITY_GROUP_ID",
    "keypair_name": "GEUSEMAKER_KEYPAIR_NAME",
    "attach_internet_gateway": "GEUSEMAKER_ATTACH_INTERNET_GATEWAY",
    "enable_alb": "GEUSEMAKER_ENABLE_ALB",
    "enable_cdn": "GEUSEMAKER_ENABLE_CDN",
    "auto_rollback_on_failure": "GEUSEMAKER_AUTO_ROLLBACK",
    "rollback_timeout_minutes": "GEUSEMAKER_ROLLBACK_TIMEOUT",
}


@dataclass
class ConfigurationError(Exception):
    """Raised when configuration cannot be parsed or validated."""

    message: str
    details: list[str] | None = None

    def __str__(self) -> str:  # noqa: D401
        if self.details:
            return f"{self.message}: {'; '.join(self.details)}"
        return self.message


class ConfigLoader:
    """Resolve deployment configuration from files, environment variables, and CLI."""

    def __init__(self, env: Mapping[str, str] | None = None):
        self.env = dict(env or os.environ)

    def load(
        self,
        config_path: str | Path | None,
        cli_overrides: Mapping[str, Any] | None = None,
    ) -> DeploymentConfig:
        """Return a validated DeploymentConfig with precedence: config < env < CLI."""
        raw_config: dict[str, Any] = {}
        if config_path:
            raw_config = self._load_config_file(Path(config_path))

        merged = self._apply_env(raw_config)
        merged = self._apply_overrides(merged, cli_overrides or {})
        try:
            return DeploymentConfig.model_validate(merged)
        except ValidationError as exc:
            raise ConfigurationError(
                "Invalid deployment configuration",
                details=_format_validation_errors(exc),
            ) from exc

    def env_overrides(self) -> dict[str, Any]:
        """Return parsed environment variable overrides without validation."""
        return self._apply_env({})

    def _apply_env(self, base: MutableMapping[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = dict(base)
        for field, env_var in ENV_VAR_MAP.items():
            if env_var not in self.env:
                continue
            raw = self.env[env_var]
            try:
                merged[field] = self._parse_env_value(field, raw)
            except ValueError as exc:
                raise ConfigurationError(
                    f"Invalid value for {env_var}",
                    details=[str(exc)],
                ) from exc
        return merged

    def _apply_overrides(
        self,
        base: MutableMapping[str, Any],
        overrides: Mapping[str, Any],
    ) -> dict[str, Any]:
        merged = dict(base)
        for key, value in overrides.items():
            if value is None:
                continue
            merged[key] = value
        return merged

    def _parse_env_value(self, field: str, raw: str) -> Any:
        model_field = DeploymentConfig.model_fields.get(field)
        if model_field is None:
            return raw

        annotation = model_field.annotation
        origin = get_origin(annotation)
        args = get_args(annotation)
        candidates = [annotation] + list(args)

        if field in {"tier", "os_type", "architecture", "ami_type"}:
            return raw.lower()
        if any(
            candidate in (list, list[str], tuple, set) or get_origin(candidate) in (list, tuple, set)
            for candidate in candidates
        ):
            return _parse_list(raw)
        if any(candidate is Decimal for candidate in candidates):
            return Decimal(str(raw))
        if any(candidate is bool for candidate in candidates):
            return _parse_bool(raw)
        if any(candidate is int for candidate in candidates):
            return int(raw)
        if any(candidate is float for candidate in candidates):
            return float(raw)
        if origin is str or annotation is str:
            return raw

        # Fall back to raw string and let Pydantic coerce/validate
        return raw

    def _load_config_file(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise ConfigurationError(f"Config file not found: {path}")
        content = path.read_text()
        loader = yaml.safe_load if path.suffix.lower() in {".yaml", ".yml"} else json.loads
        try:
            data = loader(content)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                f"Invalid JSON in {path}",
                details=[f"Line {exc.lineno}, column {exc.colno}: {exc.msg}"],
            ) from exc
        except yaml.YAMLError as exc:
            marker = getattr(exc, "problem_mark", None)
            location = f"Line {marker.line + 1}, column {marker.column + 1}" if marker else "Unknown location"
            raise ConfigurationError(
                f"Invalid YAML in {path}",
                details=[location],
            ) from exc

        if not isinstance(data, dict):
            raise ConfigurationError(f"Config file {path} must contain an object/dict.")
        return data


def _parse_bool(raw: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in BOOL_TRUE:
        return True
    if normalized in BOOL_FALSE:
        return False
    raise ValueError("Boolean env vars must be one of true/false/1/0/yes/no.")


def _parse_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _format_validation_errors(exc: ValidationError) -> list[str]:
    details: list[str] = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        msg = error.get("msg", "Invalid value")
        details.append(f"{loc}: {msg}")
    return details


__all__ = ["ConfigLoader", "ConfigurationError", "ENV_VAR_MAP"]
