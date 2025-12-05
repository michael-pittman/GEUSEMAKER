# 8. Database Schema (JSON State Files)

GeuseMaker uses **JSON file-based state persistence** instead of a traditional database. All deployment state is stored in `~/.geusemaker/` with JSON files serialized from Pydantic models.

## 8.1 State Storage Location

```
~/.geusemaker/
├── deployments/                    # Active deployment states
│   ├── my-stack.json              # Individual stack state
│   ├── prod-ai.json
│   └── dev-test.json
├── config/                         # User configuration
│   └── settings.json
├── cache/                          # Temporary cache data
│   ├── pricing.json               # Cached spot prices (TTL: 5min)
│   └── vpcs.json                  # Cached VPC discovery (TTL: 1hr)
└── logs/                           # Operation logs
    └── 2024-01-15.log
```

## 8.2 Deployment State Schema

**File:** `~/.geusemaker/deployments/{stack_name}.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "DeploymentState",
  "type": "object",
  "required": ["stack_name", "status", "created_at", "tier"],
  "properties": {
    "stack_name": {
      "type": "string",
      "pattern": "^[a-z0-9][a-z0-9-]{0,62}[a-z0-9]$",
      "description": "Unique stack identifier"
    },
    "status": {
      "type": "string",
      "enum": ["creating", "running", "updating", "rolling_back", "destroying", "failed", "destroyed"],
      "description": "Current deployment status"
    },
    "tier": {
      "type": "string",
      "enum": ["dev", "automation", "gpu"],
      "description": "Deployment tier (Tier 1/2/3)"
    },
    "region": {
      "type": "string",
      "default": "us-east-1",
      "description": "AWS region"
    },
    "created_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 creation timestamp"
    },
    "updated_at": {
      "type": "string",
      "format": "date-time",
      "description": "ISO 8601 last update timestamp"
    },
    "vpc_id": {
      "type": ["string", "null"],
      "pattern": "^vpc-[a-f0-9]+$",
      "description": "AWS VPC ID"
    },
    "subnet_ids": {
      "type": "array",
      "items": {
        "type": "string",
        "pattern": "^subnet-[a-f0-9]+$"
      },
      "description": "AWS Subnet IDs"
    },
    "efs_id": {
      "type": ["string", "null"],
      "pattern": "^fs-[a-f0-9]+$",
      "description": "AWS EFS filesystem ID (ALWAYS present when running)"
    },
    "security_group_id": {
      "type": ["string", "null"],
      "pattern": "^sg-[a-f0-9]+$",
      "description": "AWS Security Group ID"
    },
    "instance_id": {
      "type": ["string", "null"],
      "pattern": "^i-[a-f0-9]+$",
      "description": "AWS EC2 instance ID"
    },
    "public_ip": {
      "type": ["string", "null"],
      "format": "ipv4",
      "description": "Public IPv4 address"
    },
    "alb_arn": {
      "type": ["string", "null"],
      "description": "ALB ARN (Tier 2+)"
    },
    "alb_dns_name": {
      "type": ["string", "null"],
      "description": "ALB DNS hostname"
    },
    "cloudfront_id": {
      "type": ["string", "null"],
      "description": "CloudFront distribution ID (Tier 3)"
    },
    "cloudfront_domain": {
      "type": ["string", "null"],
      "description": "CloudFront domain name"
    },
    "services": {
      "type": "array",
      "items": { "$ref": "#/$defs/ServiceHealth" },
      "description": "Last known service health status"
    },
    "cost": {
      "$ref": "#/$defs/CostTracking",
      "description": "Cost tracking data"
    },
    "last_healthy_state": {
      "type": ["object", "null"],
      "description": "Snapshot for rollback (recursive DeploymentState)"
    },
    "rollback_history": {
      "type": "array",
      "items": { "$ref": "#/$defs/RollbackRecord" },
      "description": "History of rollback events"
    }
  },
  "$defs": {
    "ServiceHealth": {
      "type": "object",
      "required": ["service_name", "status"],
      "properties": {
        "service_name": {
          "type": "string",
          "enum": ["n8n", "ollama", "qdrant", "crawl4ai", "postgres"]
        },
        "port": { "type": "integer" },
        "status": {
          "type": "string",
          "enum": ["healthy", "unhealthy", "starting", "stopped"]
        },
        "last_check": {
          "type": "string",
          "format": "date-time"
        },
        "response_time_ms": {
          "type": ["integer", "null"]
        },
        "consecutive_failures": {
          "type": "integer",
          "default": 0
        },
        "error_message": {
          "type": ["string", "null"]
        }
      }
    },
    "CostTracking": {
      "type": "object",
      "properties": {
        "instance_type": { "type": "string" },
        "is_spot": { "type": "boolean" },
        "spot_price_per_hour": { "type": "number" },
        "on_demand_price_per_hour": { "type": "number" },
        "efs_gb_month_price": { "type": "number", "default": 0.30 },
        "estimated_monthly_cost": { "type": "number" },
        "instance_start_time": {
          "type": ["string", "null"],
          "format": "date-time"
        },
        "total_runtime_hours": { "type": "number", "default": 0 },
        "estimated_cost_to_date": { "type": "number", "default": 0 }
      }
    },
    "RollbackRecord": {
      "type": "object",
      "required": ["timestamp", "trigger"],
      "properties": {
        "timestamp": {
          "type": "string",
          "format": "date-time"
        },
        "trigger": {
          "type": "string",
          "enum": ["health_check_failed", "timeout", "spot_interruption", "manual", "update_failed"]
        },
        "resources_deleted": {
          "type": "array",
          "items": { "type": "string" }
        },
        "efs_preserved": {
          "type": "boolean",
          "default": true
        },
        "success": { "type": "boolean" },
        "error_message": {
          "type": ["string", "null"]
        }
      }
    }
  }
}
```

## 8.3 Example Deployment State

```json
{
  "stack_name": "prod-ai-stack",
  "status": "running",
  "tier": "automation",
  "region": "us-east-1",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T11:45:00Z",
  "vpc_id": "vpc-0abc123def456",
  "subnet_ids": ["subnet-0111aaa", "subnet-0222bbb"],
  "efs_id": "fs-0efs789xyz",
  "security_group_id": "sg-0sg456def",
  "instance_id": "i-0inst123abc",
  "public_ip": "54.123.45.67",
  "alb_arn": "arn:aws:elasticloadbalancing:us-east-1:123456789:loadbalancer/app/prod-ai-alb/abc123",
  "alb_dns_name": "prod-ai-alb-123456.us-east-1.elb.amazonaws.com",
  "cloudfront_id": null,
  "cloudfront_domain": null,
  "services": [
    {
      "service_name": "n8n",
      "port": 5678,
      "status": "healthy",
      "last_check": "2024-01-15T11:44:30Z",
      "response_time_ms": 45,
      "consecutive_failures": 0
    },
    {
      "service_name": "ollama",
      "port": 11434,
      "status": "healthy",
      "last_check": "2024-01-15T11:44:30Z",
      "response_time_ms": 23,
      "consecutive_failures": 0
    },
    {
      "service_name": "qdrant",
      "port": 6333,
      "status": "healthy",
      "last_check": "2024-01-15T11:44:30Z",
      "response_time_ms": 12,
      "consecutive_failures": 0
    },
    {
      "service_name": "crawl4ai",
      "port": 8000,
      "status": "healthy",
      "last_check": "2024-01-15T11:44:30Z",
      "response_time_ms": 34,
      "consecutive_failures": 0
    },
    {
      "service_name": "postgres",
      "port": 5432,
      "status": "healthy",
      "last_check": "2024-01-15T11:44:30Z",
      "response_time_ms": 8,
      "consecutive_failures": 0
    }
  ],
  "cost": {
    "instance_type": "t3.medium",
    "is_spot": true,
    "spot_price_per_hour": 0.0125,
    "on_demand_price_per_hour": 0.0416,
    "efs_gb_month_price": 0.30,
    "estimated_monthly_cost": 14.125,
    "instance_start_time": "2024-01-15T10:35:00Z",
    "total_runtime_hours": 1.17,
    "estimated_cost_to_date": 0.015
  },
  "last_healthy_state": null,
  "rollback_history": []
}
```

## 8.4 Settings Schema

**File:** `~/.geusemaker/config/settings.json`

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "UserSettings",
  "type": "object",
  "properties": {
    "default_region": {
      "type": "string",
      "default": "us-east-1"
    },
    "default_tier": {
      "type": "string",
      "enum": ["dev", "automation", "gpu"],
      "default": "dev"
    },
    "default_instance_type": {
      "type": "string",
      "default": "t3.medium"
    },
    "prefer_spot": {
      "type": "boolean",
      "default": true
    },
    "auto_rollback_on_failure": {
      "type": "boolean",
      "default": true
    },
    "health_check_interval_seconds": {
      "type": "integer",
      "default": 30,
      "minimum": 10,
      "maximum": 300
    },
    "consecutive_failures_threshold": {
      "type": "integer",
      "default": 3,
      "minimum": 1,
      "maximum": 10
    },
    "ui_preferences": {
      "type": "object",
      "properties": {
        "show_ascii_banners": {
          "type": "boolean",
          "default": true
        },
        "show_emojis": {
          "type": "boolean",
          "default": true
        },
        "compact_mode": {
          "type": "boolean",
          "default": false
        },
        "color_theme": {
          "type": "string",
          "enum": ["auto", "dark", "light"],
          "default": "auto"
        }
      }
    },
    "aws_profile": {
      "type": ["string", "null"],
      "default": null,
      "description": "AWS CLI profile to use (null = default)"
    }
  }
}
```

## 8.5 Cache Schema

**File:** `~/.geusemaker/cache/pricing.json`

```json
{
  "cached_at": "2024-01-15T11:40:00Z",
  "ttl_seconds": 300,
  "data": {
    "us-east-1": {
      "t3.micro": { "spot": 0.0031, "on_demand": 0.0104 },
      "t3.small": { "spot": 0.0062, "on_demand": 0.0208 },
      "t3.medium": { "spot": 0.0125, "on_demand": 0.0416 },
      "t3.large": { "spot": 0.025, "on_demand": 0.0832 },
      "g4dn.xlarge": { "spot": 0.1578, "on_demand": 0.526 }
    }
  }
}
```

## 8.6 State Operations

```python
from pathlib import Path
import json
from datetime import datetime
from filelock import FileLock
from geusemaker.models import DeploymentState, UserSettings

class StateManager:
    """JSON file-based state persistence with atomic operations."""

    def __init__(self):
        self.base_path = Path.home() / ".geusemaker"
        self.deployments_path = self.base_path / "deployments"
        self.config_path = self.base_path / "config"
        self.cache_path = self.base_path / "cache"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create state directories if they don't exist."""
        for path in [self.deployments_path, self.config_path, self.cache_path]:
            path.mkdir(parents=True, exist_ok=True)

    def _get_lock(self, file_path: Path) -> FileLock:
        """Get file lock for atomic operations."""
        return FileLock(f"{file_path}.lock", timeout=10)

    async def save_deployment(self, state: DeploymentState) -> None:
        """Save deployment state atomically."""
        file_path = self.deployments_path / f"{state.stack_name}.json"

        with self._get_lock(file_path):
            state.updated_at = datetime.utcnow()
            temp_path = file_path.with_suffix(".tmp")

            # Write to temp file first
            temp_path.write_text(
                state.model_dump_json(indent=2, exclude_none=True)
            )

            # Atomic rename
            temp_path.rename(file_path)

    async def load_deployment(self, stack_name: str) -> DeploymentState | None:
        """Load deployment state by stack name."""
        file_path = self.deployments_path / f"{stack_name}.json"

        if not file_path.exists():
            return None

        with self._get_lock(file_path):
            data = json.loads(file_path.read_text())
            return DeploymentState.model_validate(data)

    async def list_deployments(self) -> list[DeploymentState]:
        """List all deployment states."""
        deployments = []
        for file_path in self.deployments_path.glob("*.json"):
            state = await self.load_deployment(file_path.stem)
            if state:
                deployments.append(state)
        return sorted(deployments, key=lambda s: s.updated_at, reverse=True)

    async def delete_deployment(self, stack_name: str) -> bool:
        """Delete deployment state file."""
        file_path = self.deployments_path / f"{stack_name}.json"

        if not file_path.exists():
            return False

        with self._get_lock(file_path):
            file_path.unlink()
            # Clean up lock file
            lock_path = Path(f"{file_path}.lock")
            if lock_path.exists():
                lock_path.unlink()

        return True

    async def get_settings(self) -> UserSettings:
        """Load user settings with defaults."""
        file_path = self.config_path / "settings.json"

        if not file_path.exists():
            return UserSettings()

        data = json.loads(file_path.read_text())
        return UserSettings.model_validate(data)

    async def save_settings(self, settings: UserSettings) -> None:
        """Save user settings."""
        file_path = self.config_path / "settings.json"
        file_path.write_text(
            settings.model_dump_json(indent=2)
        )
```

## 8.7 State Validation

```python
from pydantic import ValidationError

async def validate_state_integrity(state: DeploymentState) -> list[str]:
    """Validate deployment state consistency."""
    errors = []

    # Rule 1: Running state must have instance_id
    if state.status == "running" and not state.instance_id:
        errors.append("❌ Running state requires instance_id")

    # Rule 2: Running state must have EFS (MANDATORY)
    if state.status == "running" and not state.efs_id:
        errors.append("❌ Running state requires efs_id (EFS is mandatory)")

    # Rule 3: Tier 2+ requires ALB
    if state.tier in ["automation", "gpu"] and state.status == "running":
        if not state.alb_arn:
            errors.append(f"❌ Tier '{state.tier}' requires ALB configuration")

    # Rule 4: Tier 3 requires CloudFront
    if state.tier == "gpu" and state.status == "running":
        if not state.cloudfront_id:
            errors.append("❌ Tier 'gpu' requires CloudFront configuration")

    # Rule 5: Cost tracking should have start time when running
    if state.status == "running" and state.cost:
        if not state.cost.instance_start_time:
            errors.append("⚠️ Running instance missing cost start time")

    return errors
```

---
