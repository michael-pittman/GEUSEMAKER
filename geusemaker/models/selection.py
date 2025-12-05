"""Models for resource selection and provenance tracking."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from geusemaker.models.discovery import ValidationResult


class ResourceProvenance(StrEnum):
    """Represents how a resource was obtained."""

    CREATED = "created"
    REUSED = "reused"
    AUTO_DISCOVERED = "auto_discovered"


class ResourceSelection(BaseModel):
    """Selection outcome for a single resource."""

    model_config = ConfigDict(frozen=False)

    resource_type: Literal[
        "vpc",
        "subnet",
        "security_group",
        "key_pair",
        "efs",
        "alb",
        "cloudfront",
    ]
    resource_id: str | None = None
    provenance: ResourceProvenance
    original_state: dict[str, Any] | None = None


class SelectionResult(BaseModel):
    """Grouped selections for a deployment."""

    vpc: ResourceSelection | None = None
    subnets: list[ResourceSelection] = Field(default_factory=list)
    security_group: ResourceSelection | None = None
    key_pair: ResourceSelection | None = None
    efs: ResourceSelection | None = None
    alb: ResourceSelection | None = None
    cloudfront: ResourceSelection | None = None
    validations: list[ValidationResult] = Field(default_factory=list)


class DependencyValidation(BaseModel):
    """Compatibility validation between resources."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def ok(cls) -> DependencyValidation:
        return cls(is_valid=True, errors=[], warnings=[])

    @classmethod
    def failed(cls, message: str) -> DependencyValidation:
        return cls(is_valid=False, errors=[message], warnings=[])

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


__all__ = [
    "DependencyValidation",
    "ResourceProvenance",
    "ResourceSelection",
    "SelectionResult",
]
