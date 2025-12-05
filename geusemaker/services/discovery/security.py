"""Security group discovery and validation."""

from __future__ import annotations

from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.models.discovery import (
    SecurityGroupInfo,
    SecurityGroupRule,
    ValidationResult,
)
from geusemaker.services.base import BaseService
from geusemaker.services.discovery.cache import DiscoveryCache


def _tags_to_dict(tags: list[dict[str, Any]] | None) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in tags or [] if "Key" in tag and "Value" in tag}


class SecurityGroupDiscoveryService(BaseService):
    """Discover security groups and perform compatibility validation."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        cache: DiscoveryCache | None = None,
    ):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")
        self._cache = cache or DiscoveryCache()

    def list_security_groups(
        self,
        vpc_id: str,
        use_cache: bool = True,
    ) -> list[SecurityGroupInfo]:
        """List security groups within a VPC."""
        cache_key = f"sg:{self.region}:{vpc_id}"
        cached = self._cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached  # type: ignore[return-value]

        def _call() -> list[SecurityGroupInfo]:
            paginator = self._ec2.get_paginator("describe_security_groups")
            groups: list[SecurityGroupInfo] = []
            for page in paginator.paginate(
                Filters=[{"Name": "vpc-id", "Values": [vpc_id]}],
            ):
                for sg in page.get("SecurityGroups", []):
                    tags = _tags_to_dict(sg.get("Tags"))
                    groups.append(
                        SecurityGroupInfo(
                            security_group_id=sg["GroupId"],
                            name=sg.get("GroupName", ""),
                            description=sg.get("Description", ""),
                            vpc_id=sg.get("VpcId", vpc_id),
                            ingress_rules=self._parse_rules(
                                sg.get("IpPermissions", []),
                            ),
                            egress_rules=self._parse_rules(
                                sg.get("IpPermissionsEgress", []),
                            ),
                            tags=tags,
                        ),
                    )
            return groups

        groups = self._safe_call(_call)
        if use_cache:
            self._cache.set(cache_key, groups)
        return groups

    def validate_security_group(
        self,
        group: SecurityGroupInfo,
        required_ports: list[int],
    ) -> ValidationResult:
        """Validate that required ports are permitted."""
        result = ValidationResult.ok()
        for port in required_ports:
            if not self._port_allowed(group.ingress_rules, port):
                result.add_issue(
                    f"Security group {group.security_group_id} is missing ingress for port {port}",
                )
        return result

    def _parse_rules(
        self,
        permissions: list[dict[str, Any]] | None,
    ) -> list[SecurityGroupRule]:
        rules: list[SecurityGroupRule] = []
        for perm in permissions or []:
            cidrs: list[str] = [rng["CidrIp"] for rng in perm.get("IpRanges", []) if "CidrIp" in rng]
            cidrs.extend(rng["CidrIpv6"] for rng in perm.get("Ipv6Ranges", []) if "CidrIpv6" in rng)
            source_groups = [grp["GroupId"] for grp in perm.get("UserIdGroupPairs", []) if "GroupId" in grp]
            description = perm.get("Description")
            if description is None and perm.get("IpRanges"):
                described = [rng.get("Description") for rng in perm["IpRanges"] if rng.get("Description")]
                description = described[0] if described else None
            rules.append(
                SecurityGroupRule(
                    protocol=perm.get("IpProtocol", "-1"),
                    from_port=perm.get("FromPort"),
                    to_port=perm.get("ToPort"),
                    cidr_blocks=cidrs,
                    source_security_groups=source_groups,
                    description=description,
                ),
            )
        return rules

    def _port_allowed(self, rules: list[SecurityGroupRule], port: int) -> bool:
        for rule in rules:
            if rule.protocol in ("-1", "tcp"):
                from_port = rule.from_port if rule.from_port is not None else port
                to_port = rule.to_port if rule.to_port is not None else port
                if from_port <= port <= to_port:
                    return True
        return False


__all__ = ["SecurityGroupDiscoveryService"]
