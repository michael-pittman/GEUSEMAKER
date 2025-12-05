# 14. Security

## 14.1 Input Validation

- **Validation Library:** Pydantic v2 with custom validators
- **Validation Location:** CLI argument parsing and model instantiation
- **Required Rules:**
  - All external inputs MUST be validated via Pydantic models
  - Validation at API boundary before processing
  - Whitelist approach for allowed values (tiers, regions, instance types)

```python
from pydantic import BaseModel, Field, field_validator
import re

class DeploymentConfig(BaseModel):
    """Validated deployment configuration."""

    stack_name: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
    )
    tier: Literal["dev", "automation", "gpu"]
    region: str = Field(default="us-east-1")
    instance_type: str = Field(default="t3.medium")

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        allowed_regions = [
            "us-east-1", "us-east-2", "us-west-1", "us-west-2",
            "eu-west-1", "eu-west-2", "eu-central-1",
            "ap-northeast-1", "ap-southeast-1", "ap-southeast-2",
        ]
        if v not in allowed_regions:
            raise ValueError(f"Region must be one of: {allowed_regions}")
        return v

    @field_validator("instance_type")
    @classmethod
    def validate_instance_type(cls, v: str) -> str:
        # Prevent extremely expensive instances without explicit flag
        prohibited_prefixes = ["p4", "p5", "inf2", "trn1"]
        if any(v.startswith(p) for p in prohibited_prefixes):
            raise ValueError(
                f"Instance type '{v}' requires --allow-expensive flag"
            )
        return v
```

## 14.2 Authentication & Authorization

- **Auth Method:** AWS IAM (Boto3 session from environment/config)
- **Session Management:** Boto3 handles credential refresh automatically
- **Required Patterns:**
  - NEVER hardcode AWS credentials
  - Use `boto3.Session()` which reads from standard locations
  - Support `AWS_PROFILE` environment variable

```python
from boto3 import Session

class AWSClientFactory:
    """Factory for creating authenticated AWS clients."""

    def __init__(self, profile_name: str | None = None):
        """Initialize with optional AWS profile.

        Credential resolution order:
        1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        2. AWS profile from ~/.aws/credentials
        3. IAM role (for EC2 instances)
        4. AWS SSO (if configured)
        """
        self._session = Session(profile_name=profile_name)
        self._clients: dict[str, Any] = {}

    def get_client(self, service: str, region: str = "us-east-1"):
        """Get or create cached Boto3 client."""
        key = f"{service}:{region}"
        if key not in self._clients:
            self._clients[key] = self._session.client(service, region_name=region)
        return self._clients[key]
```

## 14.3 Secrets Management

| Environment | Approach |
|-------------|----------|
| **Development** | AWS CLI configuration (`~/.aws/credentials`) |
| **Production** | IAM roles, environment variables |
| **CI/CD** | GitHub Secrets → environment variables |

**Code Requirements:**
- 🚫 NEVER hardcode secrets
- 🚫 NEVER store secrets in state files
- 🚫 NEVER log credentials or tokens
- ✅ Access credentials via boto3 session only

```python