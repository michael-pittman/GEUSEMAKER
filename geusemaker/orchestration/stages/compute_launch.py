"""EC2 launch stage helper for Tier1 deployments.

Extracted verbatim from ``Tier1Orchestrator._launch_instance``: the production
Spot Auto Scaling group path, the on-demand/spot launch with the IAM-profile
propagation retry, and the spot-capacity fallback. Service objects are passed
explicitly so the retry loop and fallback logic stay identical but testable in
isolation.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from geusemaker.models import DeploymentConfig
from geusemaker.models.compute import InstanceSelection
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.services.ec2 import EC2Service
from geusemaker.services.spot_automation import SpotAutomationService

LOGGER = logging.getLogger(__name__)


def launch_instance(
    ec2_service: EC2Service,
    spot_automation_service: SpotAutomationService,
    config: DeploymentConfig,
    vpc_info: dict[str, Any],
    sg_id: str,
    userdata_payload: bytes,
    iam_info: dict[str, str],
    selection: InstanceSelection,
    ami_id: str,
    block_device_mappings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Launch the EC2 instance (or Spot ASG) and return its runtime metadata.

    For production Spot tiers (automation/gpu) this provisions a Capacity-
    Rebalancing Auto Scaling group via ``spot_automation_service``. Otherwise it
    launches a single instance, retrying through IAM-profile propagation delays
    and falling back to on-demand if spot capacity vanishes at launch time.
    """
    chosen_public_subnet_id = vpc_info["chosen_public_subnet_id"]
    chosen_public_subnet_az = vpc_info.get("chosen_public_subnet_az")

    if config.tier in {"automation", "gpu"} and selection.is_spot:
        LOGGER.info("Creating production Spot Auto Scaling group with Capacity Rebalancing...")
        tags = {
            "Name": config.stack_name,
            "Stack": config.stack_name,
            "Tier": config.tier,
            "ManagedBy": "GeuseMaker",
        }
        resources = spot_automation_service.create(
            stack_name=config.stack_name,
            image_id=ami_id,
            instance_type=config.instance_type,
            subnet_ids=vpc_info["public_subnet_ids"],
            security_group_ids=[sg_id],
            instance_profile_name=iam_info["profile_name"],
            user_data=userdata_payload,
            block_device_mappings=block_device_mappings,
            tags=tags,
            key_name=config.keypair_name,
        )
        ec2_service.wait_for_running(resources.instance_id)
        instance_desc = ec2_service.describe_instance(resources.instance_id)
        return {
            "instance_id": resources.instance_id,
            "public_ip": instance_desc.get("PublicIpAddress"),
            "private_ip": instance_desc.get("PrivateIpAddress", ""),
            "spot_fallback_to_on_demand": False,
            "launch_template_id": resources.launch_template_id,
            "auto_scaling_group_name": resources.auto_scaling_group_name,
            "spot_event_log_group": resources.log_group_name,
            "spot_event_rule_names": list(resources.event_rule_names),
            "spot_lease_table_name": resources.lease_table_name,
            "spot_lifecycle_hook_names": list(resources.lifecycle_hook_names),
            "spot_coordinator_function_name": resources.coordinator_function_name,
            "spot_coordinator_role_name": resources.coordinator_role_name,
        }

    # Launch instance with IAM instance profile for EFS mount
    # Use Name (simpler and more reliable for newly created profiles in same region)
    # Retry logic handles IAM->EC2 propagation delay
    max_launch_attempts = 5
    launch_delay = 3
    ec2_resp = None

    # Spot capacity can vanish between the selection dry-run and the real launch.
    # In that case retry the launch on-demand instead of failing the whole deploy.
    spot_capacity_errors = (
        "InsufficientInstanceCapacity",
        "SpotMaxPriceTooLow",
        "MaxSpotInstanceCountExceeded",
        "SpotFleetRequestConfigurationInvalid",
    )
    launch_as_spot = selection.is_spot

    for attempt in range(max_launch_attempts):
        try:
            launch_kwargs: dict[str, Any] = {
                "ImageId": ami_id,
                "InstanceType": config.instance_type,
                "SubnetId": chosen_public_subnet_id,
                "SecurityGroupIds": [sg_id],
                "UserData": userdata_payload,
                "BlockDeviceMappings": block_device_mappings,
                "IamInstanceProfile": {"Name": iam_info["profile_name"]},
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Name", "Value": config.stack_name},
                            {"Key": "Stack", "Value": config.stack_name},
                            {"Key": "Tier", "Value": config.tier},
                        ],
                    },
                    {
                        "ResourceType": "network-interface",
                        "Tags": [
                            {"Key": "Name", "Value": f"{config.stack_name}-eni"},
                            {"Key": "Stack", "Value": config.stack_name},
                            {"Key": "Tier", "Value": config.tier},
                        ],
                    },
                ],
            }
            if launch_as_spot:
                launch_kwargs["InstanceMarketOptions"] = {
                    "MarketType": "spot",
                    "SpotOptions": {
                        "SpotInstanceType": "one-time",
                        "InstanceInterruptionBehavior": "terminate",
                    },
                }
            if chosen_public_subnet_az:
                launch_kwargs["Placement"] = {"AvailabilityZone": chosen_public_subnet_az}

            ec2_resp = ec2_service.launch_instance(**launch_kwargs)
            break  # Success - exit retry loop
        except RuntimeError as e:
            error_msg = str(e)
            # Spot capacity vanished between selection and launch: retry on-demand
            if launch_as_spot and any(code in error_msg for code in spot_capacity_errors):
                LOGGER.warning(
                    f"Spot capacity no longer available at launch ({error_msg}). Retrying with on-demand pricing..."
                )
                launch_as_spot = False
                continue
            # Check for IAM profile propagation errors
            if "InvalidParameterValue" in error_msg or "does not exist" in error_msg:
                if attempt < max_launch_attempts - 1:
                    LOGGER.info(
                        f"IAM profile not yet visible to EC2, retrying in {launch_delay}s "
                        f"(attempt {attempt + 1}/{max_launch_attempts})..."
                    )
                    time.sleep(launch_delay)
                    continue
            # Not a propagation error or last attempt - re-raise
            raise

    if ec2_resp is None:
        raise OrchestrationError(
            f"Failed to launch EC2 instance after {max_launch_attempts} attempts. "
            f"IAM instance profile '{iam_info['profile_name']}' may not be propagated to EC2."
        )

    instance_id = ec2_resp["Instances"][0]["InstanceId"]
    ec2_service.wait_for_running(instance_id)

    instance_desc = ec2_service.describe_instance(instance_id)
    public_ip = instance_desc.get("PublicIpAddress")
    private_ip = instance_desc.get("PrivateIpAddress", "")

    return {
        "instance_id": instance_id,
        "public_ip": public_ip,
        "private_ip": private_ip,
        # True when a spot selection had to launch on-demand due to a
        # capacity error at launch time (cost/state must reflect this).
        "spot_fallback_to_on_demand": selection.is_spot and not launch_as_spot,
    }
