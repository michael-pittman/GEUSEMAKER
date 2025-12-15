"""Security group service."""

from __future__ import annotations

from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class SecurityGroupService(BaseService):
    """Manage security group creation and rule configuration."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")

    def create_security_group(
        self,
        name: str,
        description: str,
        vpc_id: str,
        ingress_rules: list[dict[str, Any]],
        egress_rules: list[dict[str, Any]] | None = None,
        tags: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Create a security group and apply rules."""

        def _call() -> dict[str, Any]:
            create_kwargs: dict[str, Any] = {
                "GroupName": name,
                "Description": description,
                "VpcId": vpc_id,
            }
            # Only include TagSpecifications if there are actual tags
            if tags:
                create_kwargs["TagSpecifications"] = [
                    {"ResourceType": "security-group", "Tags": tags},
                ]
            response = self._ec2.create_security_group(**create_kwargs)
            group_id = response["GroupId"]
            if ingress_rules:
                self._ec2.authorize_security_group_ingress(
                    GroupId=group_id,
                    IpPermissions=ingress_rules,
                )
            if egress_rules:
                self._ec2.authorize_security_group_egress(
                    GroupId=group_id,
                    IpPermissions=egress_rules,
                )
            return {"group_id": group_id}

        return self._safe_call(_call)

    def ensure_rules(
        self,
        group_id: str,
        ingress_rules: list[dict[str, Any]],
        egress_rules: list[dict[str, Any]] | None = None,
    ) -> None:
        """Authorize missing rules."""

        def _call() -> None:
            if ingress_rules:
                self._ec2.authorize_security_group_ingress(
                    GroupId=group_id,
                    IpPermissions=ingress_rules,
                )
            if egress_rules:
                self._ec2.authorize_security_group_egress(
                    GroupId=group_id,
                    IpPermissions=egress_rules,
                )

        self._safe_call(_call)

    def list_security_groups(self, vpc_id: str) -> list[dict[str, Any]]:
        """List security groups for a VPC."""

        def _call() -> list[dict[str, Any]]:
            paginator = self._ec2.get_paginator("describe_security_groups")
            groups: list[dict[str, Any]] = []
            for page in paginator.paginate(
                Filters=[{"Name": "vpc-id", "Values": [vpc_id]}],
            ):
                for sg in page.get("SecurityGroups", []):
                    groups.append(
                        {
                            "group_id": sg.get("GroupId"),
                            "group_name": sg.get("GroupName"),
                            "description": sg.get("Description"),
                            "tags": sg.get("Tags", []),
                            "ingress": sg.get("IpPermissions", []),
                            "egress": sg.get("IpPermissionsEgress", []),
                        },
                    )
            return groups

        return self._safe_call(_call)

    def delete_security_group(self, group_id: str) -> None:
        """Delete a security group."""

        def _call() -> None:
            self._ec2.delete_security_group(GroupId=group_id)

        self._safe_call(_call)

    def ensure_https_port(self, group_id: str) -> bool:
        """
        Ensure HTTPS port (443) is open in a security group.

        Returns:
            True if port was added, False if it already existed
        """

        def _call() -> bool:
            # Get current security group rules
            response = self._ec2.describe_security_groups(GroupIds=[group_id])
            rules = response["SecurityGroups"][0]["IpPermissions"]

            # Check if port 443 is already open
            for rule in rules:
                if (
                    rule.get("IpProtocol") == "tcp"
                    and rule.get("FromPort") == 443
                    and rule.get("ToPort") == 443
                ):
                    return False  # Port already open

            # Port 443 not found, add it
            self._ec2.authorize_security_group_ingress(
                GroupId=group_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": 443,
                        "ToPort": 443,
                        "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                    },
                ],
            )
            return True  # Port was added

        return self._safe_call(_call)


__all__ = ["SecurityGroupService"]
