"""Core deployment-related Pydantic models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from geusemaker.models.cost import CostSnapshot

STATE_SCHEMA_VERSION = 2


class DeploymentConfig(BaseModel):
    """Immutable configuration for a GeuseMaker deployment."""

    model_config = ConfigDict(frozen=True)

    stack_name: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z][a-zA-Z0-9-]*$",
        description="Identifier for the deployment; used for tagging and state files.",
    )
    tier: Literal["dev", "automation", "gpu"]
    region: str = Field(
        default="us-east-1",
        pattern=r"^[a-z]{2}-[a-z]+-\d$",
        description="AWS region for all resources.",
    )

    # Instance configuration
    instance_type: str = Field(default="t3.medium")
    use_spot: bool = Field(default=True)
    budget_limit: Decimal | None = Field(
        default=None,
        description="Monthly budget limit in USD; optional.",
    )
    os_type: Literal["amazon-linux-2023", "ubuntu-22.04", "ubuntu-24.04", "amazon-linux-2"] = Field(
        default="ubuntu-22.04",
        description="Operating system for Deep Learning AMI selection.",
    )
    architecture: Literal["x86_64", "arm64"] = Field(
        default="x86_64",
        description="CPU architecture (x86_64 or ARM64/Graviton).",
    )
    ami_type: Literal["base", "pytorch", "tensorflow", "multi-framework"] = Field(
        default="base",
        description="Deep Learning AMI type. 'base' recommended for general use.",
    )
    ami_id: str | None = Field(
        default=None,
        description="Custom AMI ID to use instead of automatic AMI selection. Overrides os_type, architecture, and ami_type.",
    )

    # Networking (None = auto-discover or create)
    vpc_id: str | None = None
    subnet_id: str | None = None
    public_subnet_ids: list[str] | None = None
    private_subnet_ids: list[str] | None = None
    storage_subnet_id: str | None = None
    security_group_id: str | None = None
    efs_id: str | None = Field(
        default=None,
        description="Existing EFS filesystem ID to reuse. If None, a new EFS filesystem will be created.",
    )
    keypair_name: str | None = None
    attach_internet_gateway: bool = Field(
        default=False,
        description="When reusing a VPC, allow GeuseMaker to attach an internet gateway and create public routes.",
    )

    # Provisioning optimizations
    use_runtime_bundle: bool = Field(
        default=False,
        description="Embed the packaged runtime bundle into UserData to reduce on-instance downloads.",
    )
    runtime_bundle_path: str | None = Field(
        default=None,
        description="Optional path to a prebuilt runtime bundle tar.gz to embed instead of the packaged assets.",
    )

    # Optional features
    enable_alb: bool = Field(default=False)
    enable_cdn: bool = Field(default=False)

    # HTTPS/TLS configuration
    enable_https: bool = Field(
        default=True,
        description="Enable HTTPS for the deployment. Tier 1 uses self-signed certs, Tier 2/3 require ACM certificates.",
    )
    tier1_use_self_signed: bool = Field(
        default=True,
        description="Use self-signed certificates for Tier 1 dev deployments (via NGINX reverse proxy).",
    )
    alb_certificate_arn: str | None = Field(
        default=None,
        description="ACM certificate ARN for ALB HTTPS listener (required for Tier 2/3 HTTPS).",
    )
    cloudfront_certificate_arn: str | None = Field(
        default=None,
        description="ACM certificate ARN for CloudFront (Tier 3 only, must be in us-east-1 region).",
    )
    force_https_redirect: bool = Field(
        default=True,
        description="Redirect HTTP traffic to HTTPS (applies to ALB and CloudFront).",
    )

    # Rollback settings
    auto_rollback_on_failure: bool = Field(default=True)
    rollback_timeout_minutes: int = Field(default=15, ge=5, le=60)


class RollbackRecord(BaseModel):
    """Record of a rollback operation."""

    timestamp: datetime
    trigger: Literal["manual", "health_check_failed", "timeout", "spot_interruption"]
    resources_deleted: list[str]
    success: bool
    error_message: str | None = None
    previous_state_version: int | None = None
    rolled_back_changes: list[str] = Field(default_factory=list)


class CostTracking(BaseModel):
    """Cost tracking for the deployment."""

    instance_type: str
    is_spot: bool
    spot_price_per_hour: Decimal | None = None
    on_demand_price_per_hour: Decimal
    efs_gb_month_price: Decimal = Decimal("0.30")
    estimated_monthly_cost: Decimal

    budget_limit: Decimal | None = None
    cost_history: list[CostSnapshot] = Field(default_factory=list)

    instance_start_time: datetime | None = None
    total_runtime_hours: float = 0.0
    estimated_cost_to_date: Decimal = Decimal("0.0")


class DeploymentState(BaseModel):
    """Current state of a deployment with rollback and cost tracking."""

    model_config = ConfigDict(frozen=False)

    schema_version: int = Field(default=STATE_SCHEMA_VERSION)
    stack_name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal[
        "creating",
        "running",
        "updating",
        "rolling_back",
        "destroying",
        "failed",
        "terminated",
    ]

    vpc_id: str
    subnet_ids: list[str]
    security_group_id: str
    efs_id: str
    efs_mount_target_id: str
    efs_mount_target_ip: str | None = None
    instance_id: str
    keypair_name: str

    # IAM resources (required for EFS mount with IAM authentication)
    iam_role_name: str | None = None
    iam_role_arn: str | None = None
    iam_instance_profile_name: str | None = None
    iam_instance_profile_arn: str | None = None

    # Optional resources (Tier 2/3)
    alb_arn: str | None = None
    alb_dns: str | None = None
    target_group_arn: str | None = None
    cloudfront_id: str | None = None
    cloudfront_domain: str | None = None
    storage_subnet_id: str | None = None

    # Access info
    public_ip: str | None = None
    private_ip: str
    n8n_url: str

    # HTTPS/TLS state
    https_enabled: bool = Field(default=False)
    https_endpoint: str | None = Field(
        default=None,
        description="Primary HTTPS endpoint URL (CloudFront > ALB > EC2 public IP).",
    )
    certificate_arn: str | None = Field(
        default=None,
        description="ACM certificate ARN used for HTTPS (ALB or CloudFront).",
    )
    nginx_proxy_enabled: bool = Field(
        default=False,
        description="Whether NGINX reverse proxy is enabled (Tier 1 self-signed cert only).",
    )

    rollback_history: list[RollbackRecord] = Field(default_factory=list)
    last_healthy_state: dict[str, Any] | None = None
    previous_states: list[dict[str, Any]] = Field(default_factory=list)
    container_images: dict[str, str] = Field(default_factory=dict)
    resource_provenance: dict[str, str] = Field(default_factory=dict)
    migration_history: list[str] = Field(default_factory=list)
    terminated_at: datetime | None = None

    cost: CostTracking
    config: DeploymentConfig

    @field_validator("subnet_ids")
    @classmethod
    def _ensure_subnets(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one subnet_id is required")
        return value
