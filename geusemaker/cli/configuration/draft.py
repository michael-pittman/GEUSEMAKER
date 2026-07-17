"""UI-neutral draft model for building deployment configurations.

``DeploymentDraft`` mirrors every :class:`~geusemaker.models.DeploymentConfig`
field as an optional value so partially-completed wizard/TUI sessions can be
held, resumed, and validated without constructing a full config. The mirror is
derived reflectively from ``DeploymentConfig.model_fields`` so new config
fields are picked up automatically.

This module must stay UI-neutral: no Rich, questionary, Textual, or boto3.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, create_model, field_validator

from geusemaker.models import DeploymentConfig


class _DraftBase(BaseModel):
    """Static base carrying draft-only fields and shared model configuration."""

    model_config = ConfigDict(validate_assignment=True, extra="ignore")

    # Wizard/TUI session fields that never reach DeploymentConfig directly.
    setup_mode: Literal["quick", "advanced"] | None = None
    create_mount_target: bool | None = None

    # Preview metadata (excluded from ConfigBuilder.build() and to_yaml()).
    cost_monthly_estimate: float | None = None
    instance_selection_reason: str | None = None
    instance_selection_fallback: bool | None = None
    instance_alternatives: list[dict[str, Any]] | None = None

    @field_validator("stack_name", mode="before", check_fields=False)
    @classmethod
    def _normalize_stack_name(cls, value: Any) -> Any:
        """Normalize the literal string "None" (a known wizard resume footgun)."""
        if value == "None":
            return None
        return value


def _optional_config_fields() -> dict[str, Any]:
    """Mirror every DeploymentConfig field as ``Optional[...] = None``.

    Field constraints (patterns, ge/le bounds, min/max lengths) are
    intentionally dropped so a draft can hold in-progress values;
    ``ConfigBuilder.validate()`` surfaces constraint violations by
    materializing a real ``DeploymentConfig``.
    """
    fields: dict[str, Any] = {}
    for name, info in DeploymentConfig.model_fields.items():
        annotation: Any = info.annotation
        fields[name] = (Optional[annotation], None)  # noqa: UP045 - runtime typing expression
    return fields


_ConfigMirror: type[_DraftBase] = create_model(  # type: ignore[call-overload]
    "_ConfigMirror",
    __base__=_DraftBase,
    **_optional_config_fields(),
)


class DeploymentDraft(_ConfigMirror):  # type: ignore[misc, valid-type]
    """Every ``DeploymentConfig`` field as an optional value, plus draft-only fields.

    Tolerates loose resume payloads: unknown keys are ignored, the literal
    string ``"None"`` is normalized to ``None`` for ``stack_name``, and
    pre-stringified values (e.g. ``budget_limit="12.50"``) are coerced by
    Pydantic validation.
    """


# Field-name sets used by ConfigBuilder to partition draft state.
DRAFT_ONLY_FIELDS: frozenset[str] = frozenset(_DraftBase.model_fields)
PREVIEW_FIELDS: frozenset[str] = frozenset(
    {
        "cost_monthly_estimate",
        "instance_selection_reason",
        "instance_selection_fallback",
        "instance_alternatives",
    }
)
CONFIG_FIELDS: tuple[str, ...] = tuple(DeploymentConfig.model_fields)


__all__ = ["CONFIG_FIELDS", "DRAFT_ONLY_FIELDS", "PREVIEW_FIELDS", "DeploymentDraft"]
