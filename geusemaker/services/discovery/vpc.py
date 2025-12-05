"""VPC and subnet discovery with validation helpers."""

from __future__ import annotations

from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.models.discovery import (
    SubnetInfo,
    ValidationResult,
    VPCInfo,
)
from geusemaker.services.base import BaseService
from geusemaker.services.discovery.cache import DiscoveryCache


def _tags_to_dict(tags: list[dict[str, Any]] | None) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in tags or [] if "Key" in tag and "Value" in tag}


class VPCDiscoveryService(BaseService):
    """Discover VPCs, subnets, and run basic compatibility checks."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        cache: DiscoveryCache | None = None,
    ):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")
        self._cache = cache or DiscoveryCache()

    def list_vpcs(self, use_cache: bool = True) -> list[VPCInfo]:
        """List VPCs in the configured region."""
        cache_key = f"vpcs:{self.region}"
        cached = self._cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached  # type: ignore[return-value]

        def _call() -> list[VPCInfo]:
            igw_map = self._internet_gateway_map()
            paginator = self._ec2.get_paginator("describe_vpcs")
            vpcs: list[VPCInfo] = []
            for page in paginator.paginate():
                for vpc in page.get("Vpcs", []):
                    tags = _tags_to_dict(vpc.get("Tags"))
                    vpcs.append(
                        VPCInfo(
                            vpc_id=vpc["VpcId"],
                            cidr_block=vpc["CidrBlock"],
                            name=tags.get("Name"),
                            state=vpc.get("State", "available"),
                            is_default=vpc.get("IsDefault", False),
                            has_internet_gateway=vpc["VpcId"] in igw_map,
                            region=self.region,
                            tags=tags,
                        ),
                    )
            return vpcs

        vpcs = self._safe_call(_call)
        if use_cache:
            self._cache.set(cache_key, vpcs)
        return vpcs

    def list_subnets(self, vpc_id: str, use_cache: bool = True) -> list[SubnetInfo]:
        """List subnets for a given VPC."""
        cache_key = f"subnets:{self.region}:{vpc_id}"
        cached = self._cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached  # type: ignore[return-value]

        def _call() -> list[SubnetInfo]:
            route_table_map, main_route_table = self._route_table_lookup(vpc_id)
            paginator = self._ec2.get_paginator("describe_subnets")
            items: list[SubnetInfo] = []
            for page in paginator.paginate(
                Filters=[{"Name": "vpc-id", "Values": [vpc_id]}],
            ):
                for subnet in page.get("Subnets", []):
                    subnet_id = subnet["SubnetId"]
                    tags = _tags_to_dict(subnet.get("Tags"))
                    route_table_id, has_igw = route_table_map.get(
                        subnet_id,
                        main_route_table,
                    ) or (None, False)
                    is_public = bool(has_igw or subnet.get("MapPublicIpOnLaunch"))
                    items.append(
                        SubnetInfo(
                            subnet_id=subnet_id,
                            vpc_id=subnet["VpcId"],
                            cidr_block=subnet["CidrBlock"],
                            availability_zone=subnet["AvailabilityZone"],
                            available_ip_count=int(
                                subnet.get("AvailableIpAddressCount", 0),
                            ),
                            name=tags.get("Name"),
                            is_public=is_public,
                            map_public_ip_on_launch=subnet.get(
                                "MapPublicIpOnLaunch",
                                False,
                            ),
                            route_table_id=route_table_id,
                            has_internet_route=has_igw,
                            tags=tags,
                        ),
                    )
            return items

        subnets = self._safe_call(_call)
        if use_cache:
            self._cache.set(cache_key, subnets)
        return subnets

    def validate_vpc(self, vpc_id: str) -> ValidationResult:
        """Validate VPC readiness for deployment (IGW + available state)."""
        vpcs = [v for v in self.list_vpcs() if v.vpc_id == vpc_id]
        if not vpcs:
            return ValidationResult.failed(f"VPC {vpc_id} not found in {self.region}")
        vpc = vpcs[0]
        result = ValidationResult.ok()
        if vpc.state != "available":
            result.add_issue(f"VPC {vpc_id} is in {vpc.state} state")
        if not vpc.has_internet_gateway:
            result.add_issue("VPC has no internet gateway attached")
        return result

    def validate_subnets(self, subnets: list[SubnetInfo]) -> ValidationResult:
        """Validate subnet routing/associations."""
        if not subnets:
            return ValidationResult.failed("No subnets provided for validation")
        result = ValidationResult.ok()
        azs = {subnet.availability_zone for subnet in subnets}
        for subnet in subnets:
            if subnet.route_table_id is None:
                result.add_issue(
                    f"Subnet {subnet.subnet_id} has no route table association",
                )
            if not subnet.has_internet_route:
                result.add_issue(
                    f"Subnet {subnet.subnet_id} lacks a route to an internet gateway",
                    level="warning",
                )
        if len(azs) == 1:
            result.add_issue(
                "All subnets are in the same availability zone; consider spreading across AZs",
                level="warning",
            )
        return result

    def _internet_gateway_map(self) -> set[str]:
        gateways = self._ec2.describe_internet_gateways()
        attached_vpcs: set[str] = set()
        for igw in gateways.get("InternetGateways", []):
            for attachment in igw.get("Attachments", []):
                vpc_id = attachment.get("VpcId")
                if vpc_id:
                    attached_vpcs.add(vpc_id)
        return attached_vpcs

    def _route_table_lookup(
        self,
        vpc_id: str,
    ) -> tuple[dict[str, tuple[str, bool]], tuple[str, bool] | None]:
        """Return mapping of subnet -> (route_table_id, has_igw_route)."""
        paginator = self._ec2.get_paginator("describe_route_tables")
        subnet_map: dict[str, tuple[str, bool]] = {}
        main: tuple[str, bool] | None = None
        for page in paginator.paginate(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}],
        ):
            for rt in page.get("RouteTables", []):
                rt_id = rt["RouteTableId"]
                has_igw = any(
                    route.get("GatewayId", "").startswith("igw-") and route.get("State") != "blackhole"
                    for route in rt.get("Routes", [])
                )
                for assoc in rt.get("Associations", []):
                    if assoc.get("Main"):
                        main = (rt_id, has_igw)
                    subnet_id = assoc.get("SubnetId")
                    if subnet_id:
                        subnet_map[subnet_id] = (rt_id, has_igw)
        return subnet_map, main


__all__ = ["VPCDiscoveryService"]
