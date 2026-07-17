"""Shared ConfigBuilder: one code path from draft state to DeploymentConfig/YAML.

Both the questionary wizard and the Textual deploy form adapt their session
state into a :class:`DeploymentDraft` and use this builder for defaults,
conditional field visibility, validation, YAML round-trips, and final
``DeploymentConfig`` construction.

Deliberate non-goals (owned elsewhere):

- Tier normalization (``enable_alb``/``enable_cdn``/rollback timeout scaling)
  stays in ``DeploymentRunner`` post-build; duplicating it here would
  double-apply it.
- Instance recommendation and AWS discovery stay in the wizard/TUI adapters;
  this module performs no AWS or network calls.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from geusemaker.cli.configuration.draft import (
    CONFIG_FIELDS,
    PREVIEW_FIELDS,
    DeploymentDraft,
)
from geusemaker.config import ConfigLoader, ConfigurationError
from geusemaker.models import DeploymentConfig

# Legacy wizard/deploy.py state keys mapped onto draft field names.
_LEGACY_STATE_KEYS: dict[str, str] = {
    "_instance_selection_reason": "instance_selection_reason",
    "_instance_selection_fallback": "instance_selection_fallback",
    "_instance_alternatives": "instance_alternatives",
    "compute_type": "workload",
}

# Quick-mode presets applied before generic defaults (None entries document
# fields the quick path leaves unset so auto-creation/auto-selection applies).
_QUICK_PRESETS: dict[str, Any] = {
    "os_type": "ubuntu-22.04",
    "architecture": "x86_64",
    "ami_type": "base",
    "ami_id": None,
    "instance_preference": "balanced",
    "use_spot": True,
    "vpc_id": None,
    "subnet_id": None,
    "public_subnet_ids": None,
    "private_subnet_ids": None,
    "storage_subnet_id": None,
    "security_group_id": None,
    "efs_id": None,
    "keypair_name": None,
}

_AMI_FIELDS: frozenset[str] = frozenset({"os_type", "architecture", "ami_type", "ami_id"})
_NETWORK_FIELDS: frozenset[str] = frozenset(
    {
        "vpc_id",
        "subnet_id",
        "public_subnet_ids",
        "private_subnet_ids",
        "storage_subnet_id",
        "security_group_id",
        "efs_id",
        "keypair_name",
        "attach_internet_gateway",
        "create_mount_target",
    }
)
_QUICK_HIDDEN_FIELDS: frozenset[str] = _AMI_FIELDS | _NETWORK_FIELDS | {"instance_preference", "use_spot"}
_HTTPS_DETAIL_FIELDS: frozenset[str] = frozenset(
    {
        "tier1_use_self_signed",
        "alb_domain_name",
        "alb_hosted_zone_id",
        "alb_certificate_arn",
        "cloudfront_certificate_arn",
        "force_https_redirect",
    }
)
_ALB_TIERS: frozenset[str] = frozenset({"automation", "gpu"})


class ConfigBuilder:
    """Build a validated ``DeploymentConfig`` from a ``DeploymentDraft``."""

    def __init__(self, draft: DeploymentDraft | None = None) -> None:
        self._draft = draft if draft is not None else DeploymentDraft()

    @property
    def draft(self) -> DeploymentDraft:
        """Return the underlying mutable draft."""
        return self._draft

    # ------------------------------------------------------------------
    # Construction adapters
    # ------------------------------------------------------------------
    @classmethod
    def from_initial_state(cls, state: Mapping[str, Any]) -> ConfigBuilder:
        """Adapt a wizard ``self.state`` / ``deploy.py`` initial-state mapping.

        Legacy underscore-prefixed metadata keys are mapped to draft fields and
        unknown keys are ignored. Direct (modern) keys win over legacy aliases
        unless the direct value is ``None``.
        """
        known = set(DeploymentDraft.model_fields)
        payload: dict[str, Any] = {}
        for key, value in state.items():
            target = _LEGACY_STATE_KEYS.get(key)
            if target is not None and target in known:
                payload[target] = value
        for key, value in state.items():
            if key not in known or key in _LEGACY_STATE_KEYS:
                continue
            if value is None and payload.get(key) is not None:
                continue
            payload[key] = value
        return cls(DeploymentDraft(**payload))

    @classmethod
    def from_yaml(cls, text_or_path: str | Path) -> ConfigBuilder:
        """Hydrate a builder from YAML/JSON text or a config file path.

        File parsing/validation follows ``ConfigLoader`` semantics: the
        document must be a mapping and malformed input raises
        :class:`ConfigurationError`.
        """
        data = _load_mapping(text_or_path)
        return cls(DeploymentDraft(**data))

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------
    def set(self, field: str, value: Any) -> ConfigBuilder:
        """Set a single draft field (validated; unknown fields raise)."""
        if field not in DeploymentDraft.model_fields:
            raise ValueError(f"Unknown draft field: {field!r}")
        setattr(self._draft, field, value)
        return self

    def update(self, **fields: Any) -> ConfigBuilder:
        """Set multiple draft fields (validated; unknown fields raise)."""
        for field, value in fields.items():
            self.set(field, value)
        return self

    def apply_defaults(self) -> ConfigBuilder:
        """Fill unset fields from ``DeploymentConfig`` field defaults.

        Quick mode applies its presets first; defaults never overwrite values
        the user already provided.
        """
        if self._draft.setup_mode == "quick":
            for field, preset in _QUICK_PRESETS.items():
                if preset is not None and getattr(self._draft, field) is None:
                    setattr(self._draft, field, preset)
        for name, info in DeploymentConfig.model_fields.items():
            if info.is_required() or getattr(self._draft, name) is not None:
                continue
            default = info.get_default(call_default_factory=True)
            if default is not None:
                setattr(self._draft, name, default)
        return self

    # ------------------------------------------------------------------
    # Conditional visibility (shared wizard/TUI form logic)
    # ------------------------------------------------------------------
    def is_visible(self, field: str) -> bool:
        """Return whether a draft field is visible for the current draft state."""
        if field not in DeploymentDraft.model_fields:
            raise ValueError(f"Unknown draft field: {field!r}")
        if field in PREVIEW_FIELDS:
            return False
        draft = self._draft
        if draft.setup_mode == "quick" and field in _QUICK_HIDDEN_FIELDS:
            return False
        if field in _HTTPS_DETAIL_FIELDS:
            if not self._effective_enable_https():
                return False
            tier = draft.tier or "dev"
            if field == "tier1_use_self_signed":
                return tier == "dev"
            if field in {"alb_domain_name", "alb_hosted_zone_id", "alb_certificate_arn"}:
                return tier in _ALB_TIERS
            if field == "cloudfront_certificate_arn":
                return tier == "gpu"
        return True

    def visible_fields(self) -> list[str]:
        """Return draft fields visible for the current state, in field order."""
        return [field for field in DeploymentDraft.model_fields if self.is_visible(field)]

    def _effective_enable_https(self) -> bool:
        """Return the draft's HTTPS setting, falling back to the config default."""
        if self._draft.enable_https is not None:
            return bool(self._draft.enable_https)
        return bool(DeploymentConfig.model_fields["enable_https"].get_default())

    # ------------------------------------------------------------------
    # Validation and construction
    # ------------------------------------------------------------------
    def validate(self) -> dict[str, list[str]]:
        """Return a per-field error map; an empty dict means the draft is valid.

        Runs ``DeploymentConfig`` validation on a defaults-applied copy (the
        draft itself is not mutated) plus the cross-field HTTPS rule for
        ALB tiers.
        """
        working = ConfigBuilder(self._draft.model_copy(deep=True)).apply_defaults()
        payload = working._materialize()
        errors: dict[str, list[str]] = {}
        try:
            DeploymentConfig.model_validate(payload)
        except ValidationError as exc:
            for error in exc.errors():
                loc = ".".join(str(part) for part in error.get("loc", ())) or "__root__"
                errors.setdefault(loc, []).append(str(error.get("msg", "Invalid value")))

        tier = payload.get("tier")
        if tier in _ALB_TIERS and payload.get("enable_https", True):
            has_dns_pair = bool(payload.get("alb_domain_name")) and bool(payload.get("alb_hosted_zone_id"))
            if not has_dns_pair and not payload.get("alb_certificate_arn"):
                message = (
                    "Tier 2/3 HTTPS requires alb_domain_name and alb_hosted_zone_id "
                    "(for ACM DNS validation) or an existing alb_certificate_arn."
                )
                for field in ("alb_domain_name", "alb_hosted_zone_id"):
                    if not payload.get(field):
                        errors.setdefault(field, []).append(message)
        return errors

    def build(self) -> DeploymentConfig:
        """Apply defaults and construct the ``DeploymentConfig``.

        Tier normalization is intentionally NOT applied here (it lives in
        ``DeploymentRunner``), and no AWS calls are made.
        """
        self.apply_defaults()
        return DeploymentConfig.model_validate(self._materialize())

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_yaml(self) -> str:
        """Serialize the built config to YAML accepted by ``ConfigLoader.load()``.

        Matches the wizard's export shape: JSON-mode dump with ``exclude_none``
        and insertion-ordered keys.
        """
        config = self.build()
        data = config.model_dump(mode="json", exclude_none=True)
        return yaml.safe_dump(data, sort_keys=False)

    def _materialize(self) -> dict[str, Any]:
        """Return the non-None config-field payload (preview metadata excluded)."""
        payload: dict[str, Any] = {}
        for name in CONFIG_FIELDS:
            value = getattr(self._draft, name)
            if value is not None:
                payload[name] = value
        return payload


def _load_mapping(text_or_path: str | Path) -> dict[str, Any]:
    """Load a config mapping from a path (via ConfigLoader) or YAML/JSON text."""
    if isinstance(text_or_path, Path):
        return ConfigLoader()._load_config_file(text_or_path)
    if "\n" not in text_or_path:
        try:
            is_file = Path(text_or_path).exists()
        except (OSError, ValueError):
            is_file = False
        if is_file:
            return ConfigLoader()._load_config_file(Path(text_or_path))
    try:
        data = yaml.safe_load(text_or_path)
    except yaml.YAMLError as exc:
        marker = getattr(exc, "problem_mark", None)
        location = f"Line {marker.line + 1}, column {marker.column + 1}" if marker else "Unknown location"
        raise ConfigurationError("Invalid YAML configuration text", details=[location]) from exc
    if not isinstance(data, dict):
        raise ConfigurationError("Configuration text must contain a YAML/JSON object/dict.")
    return data


__all__ = ["ConfigBuilder"]
