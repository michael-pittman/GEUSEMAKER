# 4. Data Models

Core Pydantic v2 models using discriminated unions for type safety and clear validation errors.

## 4.1 DeploymentConfig

**Purpose:** User-provided deployment configuration validated before any AWS operations

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from datetime import datetime

class DeploymentConfig(BaseModel):
    """Immutable configuration for a GeuseMaker deployment."""
    model_config = ConfigDict(frozen=True)

    stack_name: str = Field(..., min_length=1, max_length=128, pattern=r'^[a-zA-Z][a-zA-Z0-9-]*$')
    tier: Literal["dev", "automation", "gpu"]
    region: str = Field(default="us-east-1", pattern=r'^[a-z]{2}-[a-z]+-\d$')

    # Instance configuration
    instance_type: str = Field(default="t3.medium")
    use_spot: bool = Field(default=True)

    # Networking (None = auto-discover or create)
    vpc_id: str | None = None
    subnet_id: str | None = None
    keypair_name: str | None = None

    # Optional features
    enable_alb: bool = Field(default=False)
    enable_cdn: bool = Field(default=False)

    # Rollback settings
    auto_rollback_on_failure: bool = Field(default=True)
    rollback_timeout_minutes: int = Field(default=15, ge=5, le=60)
```

## 4.2 DeploymentState

**Purpose:** Tracks deployed resources, status, rollback history, and cost - persisted to `~/.geusemaker/<stack>.json`

```python
class RollbackRecord(BaseModel):
    """Record of a rollback operation."""
    timestamp: datetime
    trigger: Literal["manual", "health_check_failed", "timeout", "spot_interruption"]
    resources_deleted: list[str]  # Resource IDs that were cleaned up
    success: bool
    error_message: str | None = None

class CostTracking(BaseModel):
    """Cost tracking for the deployment."""
    instance_type: str
    is_spot: bool
    spot_price_per_hour: float | None = None  # From describe-spot-price-history
    on_demand_price_per_hour: float  # From pricing API
    efs_gb_month_price: float = 0.30  # Standard EFS pricing
    estimated_monthly_cost: float

    # Runtime tracking
    instance_start_time: datetime | None = None
    total_runtime_hours: float = 0.0
    estimated_cost_to_date: float = 0.0

class DeploymentState(BaseModel):
    """Current state of a deployment with rollback and cost tracking."""
    model_config = ConfigDict(frozen=False)

    stack_name: str
    created_at: datetime
    updated_at: datetime
    status: Literal["creating", "running", "updating", "rolling_back", "destroying", "failed", "terminated"]

    # AWS Resource IDs (always present when running)
    vpc_id: str
    subnet_ids: list[str]
    security_group_id: str
    efs_id: str
    efs_mount_target_id: str
    instance_id: str
    keypair_name: str

    # Optional resources (Tier 2/3)
    alb_arn: str | None = None
    alb_dns: str | None = None
    target_group_arn: str | None = None
    cloudfront_id: str | None = None
    cloudfront_domain: str | None = None

    # Access info
    public_ip: str | None = None
    private_ip: str
    n8n_url: str

    # Rollback tracking
    rollback_history: list[RollbackRecord] = []
    last_healthy_state: dict | None = None  # Snapshot for rollback

    # Cost tracking
    cost: CostTracking

    # Original config
    config: DeploymentConfig
```

## 4.3 ServiceHealth

**Purpose:** Health check status for each AI stack service

```python
class ServiceHealth(BaseModel):
    """Health status of a deployed service."""
    service_name: Literal["n8n", "ollama", "qdrant", "crawl4ai", "postgres"]
    port: int
    status: Literal["starting", "healthy", "unhealthy", "stopped"]
    last_check: datetime
    response_time_ms: int | None = None
    error_message: str | None = None
    consecutive_failures: int = 0
```

## 4.4 AWSResourceSpec (Discriminated Union)

**Purpose:** Type-safe AWS resource specifications using discriminated unions

```python
from typing import Annotated, Union
from pydantic import Discriminator, Tag

class BaseResourceSpec(BaseModel):
    """Base for all AWS resource specs."""
    tags: dict[str, str]

class EC2Spec(BaseResourceSpec):
    """EC2 instance specification."""
    resource_type: Literal["ec2"] = "ec2"
    ami_id: str
    instance_type: str
    subnet_id: str
    security_group_ids: list[str]
    keypair_name: str
    user_data_base64: str
    spot_options: dict | None = None

class EFSSpec(BaseResourceSpec):
    """EFS filesystem specification."""
    resource_type: Literal["efs"] = "efs"
    creation_token: str
    performance_mode: Literal["generalPurpose", "maxIO"] = "generalPurpose"
    throughput_mode: Literal["bursting", "elastic"] = "bursting"
    encrypted: bool = True

class SecurityGroupSpec(BaseResourceSpec):
    """Security group specification."""
    resource_type: Literal["security_group"] = "security_group"
    name: str
    description: str
    vpc_id: str
    ingress_rules: list[dict]

class ALBSpec(BaseResourceSpec):
    """Application Load Balancer specification."""
    resource_type: Literal["alb"] = "alb"
    name: str
    subnets: list[str]
    security_groups: list[str]
    scheme: Literal["internet-facing", "internal"] = "internet-facing"
