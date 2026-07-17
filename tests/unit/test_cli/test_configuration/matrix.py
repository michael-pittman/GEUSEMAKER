"""Shared field-matrix fixtures for configuration-seam tests.

Each entry is a complete draft payload covering a distinct deployment shape.
Both the builder unit tests and the YAML round-trip tests parametrize over
this matrix so the wizard and Textual adapters are exercised against the same
configuration fixtures (docs/tui-brutalist-rollout.md section 11).
"""

from __future__ import annotations

from typing import Any

FIELD_MATRIX: dict[str, dict[str, Any]] = {
    "quick_dev": {
        "stack_name": "quick-dev",
        "tier": "dev",
        "setup_mode": "quick",
        "workload": "cpu",
        "instance_type": "t3.medium",
        "region": "us-east-1",
    },
    "advanced_automation_https": {
        "stack_name": "adv-auto",
        "tier": "automation",
        "setup_mode": "advanced",
        "workload": "cpu",
        "region": "us-west-2",
        "instance_type": "t3.large",
        "use_spot": False,
        "enable_https": True,
        "alb_domain_name": "n8n.example.com",
        "alb_hosted_zone_id": "Z0123456789ABCDEF",
        "budget_limit": "25.50",
    },
    "gpu_tier": {
        "stack_name": "gpu-stack",
        "tier": "gpu",
        "workload": "gpu",
        "instance_type": "g4dn.xlarge",
        "enable_https": True,
        "alb_certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/alb-cert",
        "cloudfront_certificate_arn": "arn:aws:acm:us-east-1:123456789012:certificate/cf-cert",
        "rollback_timeout_minutes": 30,
    },
    "reused_vpc_networking": {
        "stack_name": "reuse-net",
        "tier": "dev",
        "vpc_id": "vpc-0123",
        "subnet_id": "subnet-public",
        "public_subnet_ids": ["subnet-public"],
        "private_subnet_ids": ["subnet-private"],
        "storage_subnet_id": "subnet-private",
        "security_group_id": "sg-0123",
        "efs_id": "fs-0123",
        "keypair_name": "kp-0123",
        "attach_internet_gateway": True,
    },
    "custom_ami": {
        "stack_name": "custom-ami",
        "tier": "dev",
        "ami_id": "ami-0123456789abcdef0",
        "os_type": "ubuntu-24.04",
        "architecture": "arm64",
        "ami_type": "pytorch",
    },
}

MATRIX_IDS: list[str] = sorted(FIELD_MATRIX)
