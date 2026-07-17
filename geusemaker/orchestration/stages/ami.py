"""AMI resolution and root-device detection for instance launch.

Pure helpers extracted from ``Tier1Orchestrator._launch_instance``. They take
the EC2 service object explicitly so they stay unit-testable without a live
orchestrator.
"""

from __future__ import annotations

import logging
from typing import Any

from geusemaker.models import DeploymentConfig
from geusemaker.services.ec2 import EC2Service

LOGGER = logging.getLogger(__name__)

# Minimum root volume size (GiB). The Deep Learning AMIs ship large driver and
# CUDA payloads, so the root volume must be generously sized.
MIN_ROOT_GB = 75


def resolve_ami(ec2_service: EC2Service, config: DeploymentConfig) -> str:
    """Return the AMI id to launch, honoring an explicit override.

    Uses ``config.ami_id`` verbatim when provided; otherwise auto-selects the
    latest Deep Learning Base AMI matching the config's OS/architecture/type.
    """
    if config.ami_id:
        ami_id = config.ami_id
        LOGGER.info(f"Using custom AMI: {ami_id}")
    else:
        ami_id = ec2_service.get_latest_dlami(
            os_type=config.os_type,
            architecture=config.architecture,
            ami_type=config.ami_type,
            instance_type=config.instance_type,
        )
        LOGGER.info(f"Auto-selected AMI: {ami_id}")
    return ami_id


def detect_root_device(ec2_service: EC2Service, ami_id: str) -> str:
    """Return the AMI's root device name, defaulting to ``/dev/xvda`` on error."""
    try:
        return ec2_service.get_root_device_name(ami_id)
    except Exception as exc:  # noqa: BLE001
        root_device_name = "/dev/xvda"
        LOGGER.warning(f"Could not determine AMI root device; defaulting to {root_device_name}. Details: {exc}")
        return root_device_name


def build_block_device_mappings(root_device_name: str) -> list[dict[str, Any]]:
    """Build the EBS block device mapping for the root volume."""
    return [
        {
            "DeviceName": root_device_name,
            "Ebs": {
                "VolumeSize": MIN_ROOT_GB,
                "VolumeType": "gp3",
                "DeleteOnTermination": True,
                "Encrypted": True,
            },
        },
    ]
