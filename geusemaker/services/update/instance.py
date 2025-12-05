"""Instance update helpers."""

from __future__ import annotations

from geusemaker.infra import AWSClientFactory
from geusemaker.models import DeploymentState
from geusemaker.services.ec2 import EC2Service


class InstanceUpdater:
    """Update EC2 instance attributes such as instance type."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        region: str = "us-east-1",
        ec2_service: EC2Service | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.region = region
        self.ec2 = ec2_service or EC2Service(self.client_factory, region=region)

    def update_instance_type(self, state: DeploymentState, new_type: str) -> list[str]:
        """Stop, modify, and restart the instance with a new type."""
        if not new_type:
            raise ValueError("New instance type must be provided.")
        if not state.instance_id:
            raise ValueError("Deployment state is missing an instance_id.")

        if state.config.instance_type == new_type:
            return []

        self.ec2.stop_instance(state.instance_id)
        self.ec2.wait_for_stopped(state.instance_id)
        self.ec2.modify_instance_type(state.instance_id, new_type)
        self.ec2.start_instance(state.instance_id)
        self.ec2.wait_for_running(state.instance_id)

        state.config = state.config.model_copy(update={"instance_type": new_type})
        state.cost.instance_type = new_type
        return [f"instance_type:{new_type}"]


__all__ = ["InstanceUpdater"]
