"""Pydantic models for AWS resource discovery."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ValidationIssue(BaseModel):
    """A single validation issue discovered during compatibility checks."""

    model_config = ConfigDict(frozen=False)

    level: Literal["info", "warning", "error"] = "error"
    message: str


class ValidationResult(BaseModel):
    """Aggregated validation result with helper constructors."""

    model_config = ConfigDict(frozen=False)

    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)

    @classmethod
    def ok(cls) -> ValidationResult:
        return cls(is_valid=True, issues=[])

    @classmethod
    def failed(cls, message: str) -> ValidationResult:
        return cls(is_valid=False, issues=[ValidationIssue(message=message)])

    def add_issue(
        self,
        message: str,
        level: Literal["info", "warning", "error"] = "error",
    ) -> None:
        self.issues.append(ValidationIssue(message=message, level=level))
        if level == "error":
            self.is_valid = False


class VPCInfo(BaseModel):
    """Metadata about an AWS VPC."""

    vpc_id: str
    cidr_block: str
    name: str | None = None
    state: Literal["available", "pending"]
    is_default: bool = False
    has_internet_gateway: bool = False
    region: str
    tags: dict[str, str] = Field(default_factory=dict)


class SubnetInfo(BaseModel):
    """Metadata about an AWS subnet."""

    subnet_id: str
    vpc_id: str
    cidr_block: str
    availability_zone: str
    available_ip_count: int
    name: str | None = None
    is_public: bool = False
    map_public_ip_on_launch: bool = False
    route_table_id: str | None = None
    has_internet_route: bool = False
    tags: dict[str, str] = Field(default_factory=dict)


class SecurityGroupRule(BaseModel):
    """Inbound or outbound security group rule."""

    protocol: str
    from_port: int | None
    to_port: int | None
    cidr_blocks: list[str] = Field(default_factory=list)
    source_security_groups: list[str] = Field(default_factory=list)
    description: str | None = None


class SecurityGroupInfo(BaseModel):
    """Security group metadata including parsed rules."""

    security_group_id: str
    name: str
    description: str
    vpc_id: str
    ingress_rules: list[SecurityGroupRule] = Field(default_factory=list)
    egress_rules: list[SecurityGroupRule] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class KeyPairInfo(BaseModel):
    """SSH key pair metadata."""

    key_name: str
    key_fingerprint: str
    key_type: Literal["rsa", "ed25519", "unknown"] = "unknown"
    created_at: datetime | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class MountTargetInfo(BaseModel):
    """EFS mount target metadata."""

    mount_target_id: str
    file_system_id: str
    subnet_id: str
    availability_zone: str
    ip_address: str
    lifecycle_state: str
    security_groups: list[str] = Field(default_factory=list)


class EFSInfo(BaseModel):
    """EFS filesystem metadata and mount targets."""

    file_system_id: str
    name: str | None = None
    lifecycle_state: Literal["available", "creating", "deleting", "deleted"]
    throughput_mode: Literal["bursting", "provisioned", "elastic"]
    encrypted: bool
    kms_key_id: str | None = None
    size_in_bytes: int = 0
    mount_targets: list[MountTargetInfo] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class ListenerInfo(BaseModel):
    """ALB listener metadata."""

    arn: str
    protocol: str
    port: int
    ssl_policy: str | None = None
    default_actions: list[str] = Field(default_factory=list)


class TargetGroupInfo(BaseModel):
    """Target group metadata."""

    arn: str
    name: str
    protocol: str
    port: int
    target_type: str
    vpc_id: str
    health_check_path: str | None = None


class ALBInfo(BaseModel):
    """Application Load Balancer metadata."""

    arn: str
    name: str
    dns_name: str
    scheme: Literal["internet-facing", "internal"]
    state: Literal["active", "provisioning", "active_impaired", "failed"]
    vpc_id: str
    availability_zones: list[str] = Field(default_factory=list)
    listeners: list[ListenerInfo] = Field(default_factory=list)
    target_groups: list[TargetGroupInfo] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class CloudFrontInfo(BaseModel):
    """CloudFront distribution metadata."""

    distribution_id: str
    domain_name: str
    status: Literal["Deployed", "InProgress"]
    origins: list[str] = Field(default_factory=list)
    default_cache_behavior: dict[str, str | int | bool] = Field(
        default_factory=dict,
    )
    enabled: bool
    ssl_certificate: str | None = None


__all__ = [
    "ALBInfo",
    "CloudFrontInfo",
    "EFSInfo",
    "KeyPairInfo",
    "ListenerInfo",
    "MountTargetInfo",
    "SecurityGroupInfo",
    "SecurityGroupRule",
    "SubnetInfo",
    "TargetGroupInfo",
    "ValidationIssue",
    "ValidationResult",
    "VPCInfo",
]
