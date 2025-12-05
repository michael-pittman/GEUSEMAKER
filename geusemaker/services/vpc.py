"""VPC service for create/discover/validate with rollback and tagging."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from geusemaker.infra import AWSClientFactory
from geusemaker.models import SubnetResource, VPCResource
from geusemaker.services.base import BaseService
from geusemaker.services.cost import ResourceTagger


class VPCService(BaseService):
    """Manage VPC discovery, validation, and creation."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        tagger: ResourceTagger | None = None,
    ):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")
        self._tagger = tagger or ResourceTagger(client_factory, region=region)

    def list_vpcs(self) -> list[dict[str, Any]]:
        """Discover VPCs with key metadata."""
        paginator = self._ec2.get_paginator("describe_vpcs")
        items: list[dict[str, Any]] = []
        for page in paginator.paginate():
            for vpc in page.get("Vpcs", []):
                items.append(
                    {
                        "vpc_id": vpc.get("VpcId"),
                        "cidr_block": vpc.get("CidrBlock"),
                        "state": vpc.get("State"),
                        "is_default": vpc.get("IsDefault", False),
                        "tags": vpc.get("Tags", []),
                    },
                )
        return items

    def create_vpc_with_subnets(
        self,
        cidr_block: str,
        name: str,
        deployment: str | None = None,
        tier: str | None = None,
    ) -> VPCResource:
        """Create a VPC with two public and two private subnets and rollback on failure."""
        created: list[dict[str, str]] = []
        tags = self._build_tags(name=name, deployment=deployment, tier=tier)

        try:
            vpc_id = self._safe_call(
                lambda: self._ec2.create_vpc(
                    CidrBlock=cidr_block,
                    TagSpecifications=[
                        {"ResourceType": "vpc", "Tags": tags},
                    ],
                )["Vpc"]["VpcId"],
            )
            created.append({"type": "vpc", "id": vpc_id})
            self._enable_vpc_dns(vpc_id)
            self._apply_network_acl_defaults(vpc_id, tags)

            igw_id = self._ensure_internet_gateway(vpc_id, tags, created)

            azs = self._select_availability_zones(2)
            public_cidrs = ["10.0.1.0/24", "10.0.2.0/24"]
            private_cidrs = ["10.0.101.0/24", "10.0.102.0/24"]

            public_subnets = self._create_subnets(
                vpc_id,
                azs,
                cidrs=public_cidrs,
                name=name,
                tags=tags,
                is_public=True,
                created=created,
            )
            self._create_subnets(
                vpc_id,
                azs,
                cidrs=private_cidrs,
                name=name,
                tags=tags,
                is_public=False,
                created=created,
            )

            public_route_table_id = self._create_public_route_table(
                vpc_id,
                igw_id,
                [subnet.subnet_id for subnet in public_subnets],
                tags,
                created,
            )

            subnets = self._subnet_resources(vpc_id)
            main_route_table = self._main_route_table_id(vpc_id)
            route_table_ids = [
                public_route_table_id,
                *(rt for rt in {main_route_table} if rt),
            ]

            return VPCResource(
                vpc_id=vpc_id,
                cidr_block=cidr_block,
                name=name,
                public_subnets=[subnet for subnet in subnets if subnet.is_public],
                private_subnets=[subnet for subnet in subnets if not subnet.is_public],
                internet_gateway_id=igw_id,
                route_table_ids=route_table_ids,
                created_by_geusemaker=True,
            )
        except Exception as exc:  # noqa: BLE001
            self._rollback(created)
            raise RuntimeError(f"Failed to create VPC: {exc}") from exc

    def configure_existing_vpc(
        self,
        vpc_id: str,
        name: str | None = None,
        deployment: str | None = None,
        tier: str | None = None,
        public_subnet_ids: list[str] | None = None,
        private_subnet_ids: list[str] | None = None,
        attach_internet_gateway: bool = False,
    ) -> VPCResource:
        """Validate and attach internet-facing resources for an existing VPC."""
        tags = self._build_tags(name=name, deployment=deployment, tier=tier)
        created: list[dict[str, str]] = []

        try:
            vpc = self._safe_call(
                lambda: self._ec2.describe_vpcs(VpcIds=[vpc_id])["Vpcs"][0],
            )
            if vpc.get("State") != "available":
                raise ValueError(f"VPC {vpc_id} is not available")
            self._enable_vpc_dns(vpc_id)
            if tags:
                self._apply_tags([vpc_id], tags)

            self._apply_network_acl_defaults(vpc_id, tags)
            igw_id = self._attached_internet_gateway(vpc_id)
            if not igw_id:
                if not attach_internet_gateway:
                    raise ValueError(
                        f"VPC {vpc_id} has no internet gateway. Attach one or re-run with attach_internet_gateway=True.",
                    )
                igw_id = self._ensure_internet_gateway(vpc_id, tags, created)
            elif tags:
                self._apply_tags([igw_id], tags)

            subnets = self._subnet_resources(vpc_id)
            if not subnets:
                raise ValueError(f"VPC {vpc_id} has no subnets to configure")

            requested_public = public_subnet_ids or []
            requested_private = private_subnet_ids or []

            if requested_public:
                missing = [
                    subnet_id for subnet_id in requested_public if subnet_id not in {s.subnet_id for s in subnets}
                ]
                if missing:
                    raise ValueError(f"Public subnets not found in VPC {vpc_id}: {', '.join(missing)}")
                # Limit to requested public subnets for compute placement
                subnets = [s.model_copy() for s in subnets if s.subnet_id in requested_public or not s.is_public]
                for subnet in subnets:
                    if subnet.subnet_id in set(requested_public):
                        subnet.is_public = True
            if requested_private:
                missing = [
                    subnet_id for subnet_id in requested_private if subnet_id not in {s.subnet_id for s in subnets}
                ]
                if missing:
                    raise ValueError(f"Private subnets not found in VPC {vpc_id}: {', '.join(missing)}")

            public_subnet_ids = self._determine_public_subnets(subnets)
            if not public_subnet_ids:
                if not attach_internet_gateway:
                    raise ValueError(
                        f"No public subnets found in VPC {vpc_id}. "
                        "Provide public_subnet_ids with internet routing or enable attach_internet_gateway.",
                    )
                promoted = subnets[0]
                self._safe_call(
                    lambda: self._ec2.modify_subnet_attribute(
                        SubnetId=promoted.subnet_id,
                        MapPublicIpOnLaunch={"Value": True},
                    ),
                )
                public_subnet_ids = [promoted.subnet_id]

            route_table_ids: set[str] = set()
            if attach_internet_gateway:
                public_route_table_id = self._ensure_public_routes(
                    vpc_id,
                    igw_id,
                    public_subnet_ids,
                    tags,
                    created,
                )
                if public_route_table_id:
                    route_table_ids.add(public_route_table_id)
            else:
                route_table_ids.update(self._validate_public_routes(vpc_id, public_subnet_ids, tags))

            refreshed_subnets = self._subnet_resources(vpc_id)
            if public_subnet_ids:
                refreshed_subnets = [
                    sub
                    for sub in refreshed_subnets
                    if (sub.is_public and sub.subnet_id in public_subnet_ids)
                    or (not sub.is_public and (not private_subnet_ids or sub.subnet_id in private_subnet_ids))
                ]
            main_route_table = self._main_route_table_id(vpc_id)
            if main_route_table:
                route_table_ids.add(main_route_table)
            route_table_ids_list = list(route_table_ids)

            return VPCResource(
                vpc_id=vpc_id,
                cidr_block=vpc.get("CidrBlock", ""),
                name=name or self._tag_value(vpc.get("Tags", []), "Name") or vpc_id,
                public_subnets=[sub for sub in refreshed_subnets if sub.is_public],
                private_subnets=[sub for sub in refreshed_subnets if not sub.is_public],
                internet_gateway_id=igw_id,
                route_table_ids=route_table_ids_list,
                created_by_geusemaker=False,
            )
        except Exception as exc:  # noqa: BLE001
            self._rollback(created)
            raise RuntimeError(f"Failed to configure existing VPC {vpc_id}: {exc}") from exc

    def list_subnets(self, vpc_id: str) -> list[dict[str, Any]]:
        """Discover subnets for a given VPC."""
        subnets = self._subnet_resources(vpc_id)
        return [
            {
                "subnet_id": subnet.subnet_id,
                "vpc_id": subnet.vpc_id,
                "cidr_block": subnet.cidr_block,
                "availability_zone": subnet.availability_zone,
                "is_public": subnet.is_public,
                "route_table_id": subnet.route_table_id,
            }
            for subnet in subnets
        ]

    def _determine_public_subnets(self, subnets: Iterable[SubnetResource]) -> list[str]:
        """Return subnet IDs considered public (IGW route or public IP mapping)."""
        return [subnet.subnet_id for subnet in subnets if subnet.is_public]

    def _select_availability_zones(self, count: int) -> list[str]:
        zones = self._safe_call(lambda: self._ec2.describe_availability_zones())
        azs = [az["ZoneName"] for az in zones.get("AvailabilityZones", [])]
        return azs[:count] or ["us-east-1a"]

    def _create_subnets(
        self,
        vpc_id: str,
        azs: list[str],
        cidrs: list[str],
        name: str,
        tags: list[dict[str, str]],
        is_public: bool,
        created: list[dict[str, str]],
    ) -> list[SubnetResource]:
        subnets: list[SubnetResource] = []
        tier_label = "public" if is_public else "private"
        # Filter out Name tag from base tags - subnets get their own specific names
        base_tags = [t for t in tags if t.get("Key") != "Name"]
        for idx, az in enumerate(azs):
            cidr_block = cidrs[idx]
            subnet_name = f"{name}-{tier_label}-{idx + 1}"
            subnet_tags = base_tags + [
                {"Key": "Name", "Value": subnet_name},
                {"Key": "Tier", "Value": tier_label},
            ]
            # Capture loop variables for lambda
            _vpc, _cidr, _az, _tags = vpc_id, cidr_block, az, subnet_tags
            subnet_id = self._safe_call(
                lambda: self._ec2.create_subnet(
                    VpcId=_vpc,
                    CidrBlock=_cidr,
                    AvailabilityZone=_az,
                    TagSpecifications=[
                        {
                            "ResourceType": "subnet",
                            "Tags": _tags,
                        },
                    ],
                )["Subnet"]["SubnetId"],
            )
            created.append({"type": "subnet", "id": subnet_id})

            if is_public:
                self._safe_call(
                    lambda: self._ec2.modify_subnet_attribute(
                        SubnetId=subnet_id,
                        MapPublicIpOnLaunch={"Value": True},
                    ),
                )

            subnets.append(
                SubnetResource(
                    subnet_id=subnet_id,
                    vpc_id=vpc_id,
                    cidr_block=cidr_block,
                    availability_zone=az,
                    is_public=is_public,
                    route_table_id=None,
                ),
            )
        return subnets

    def _create_public_route_table(
        self,
        vpc_id: str,
        igw_id: str,
        subnet_ids: list[str],
        tags: list[dict[str, str]],
        created: list[dict[str, str]],
    ) -> str:
        rt_id = self._safe_call(
            lambda: self._ec2.create_route_table(
                VpcId=vpc_id,
                TagSpecifications=[
                    {"ResourceType": "route-table", "Tags": tags},
                ],
            )["RouteTable"]["RouteTableId"],
        )
        created.append({"type": "route_table", "id": rt_id})

        self._safe_call(
            lambda: self._ec2.create_route(
                RouteTableId=rt_id,
                DestinationCidrBlock="0.0.0.0/0",
                GatewayId=igw_id,
            ),
        )
        for subnet_id in subnet_ids:
            self._safe_call(
                lambda: self._ec2.associate_route_table(RouteTableId=rt_id, SubnetId=subnet_id),
            )
        return rt_id

    def _ensure_public_routes(
        self,
        vpc_id: str,
        igw_id: str,
        public_subnet_ids: list[str],
        tags: list[dict[str, str]],
        created: list[dict[str, str]],
    ) -> str:
        """Ensure at least one route table sends public subnets to the IGW."""
        route_table_map, main_route_table = self._route_table_lookup(vpc_id)
        existing_route_table_id = None

        for subnet_id in public_subnet_ids:
            route_table_id, has_igw = route_table_map.get(subnet_id, main_route_table) or (None, False)
            if has_igw and route_table_id:
                existing_route_table_id = route_table_id
                break

        if existing_route_table_id is None and main_route_table and main_route_table[1]:
            existing_route_table_id = main_route_table[0]

        if existing_route_table_id:
            if tags:
                self._apply_tags([existing_route_table_id], tags)
            self._associate_public_subnets(
                existing_route_table_id,
                public_subnet_ids,
                route_table_map,
            )
            return existing_route_table_id

        return self._create_public_route_table(vpc_id, igw_id, public_subnet_ids, tags, created)

    def _associate_public_subnets(
        self,
        route_table_id: str,
        subnet_ids: list[str],
        route_table_map: dict[str, tuple[str, bool]],
    ) -> None:
        associated_subnets = {subnet_id for subnet_id, (rt_id, _) in route_table_map.items() if rt_id == route_table_id}
        for subnet_id in subnet_ids:
            if subnet_id not in associated_subnets:
                self._safe_call(
                    lambda: self._ec2.associate_route_table(
                        RouteTableId=route_table_id,
                        SubnetId=subnet_id,
                    ),
                )

    def _attached_internet_gateway(self, vpc_id: str) -> str | None:
        gateways = self._safe_call(lambda: self._ec2.describe_internet_gateways())
        for igw in gateways.get("InternetGateways", []):
            for attachment in igw.get("Attachments", []):
                if attachment.get("VpcId") == vpc_id:
                    return igw["InternetGatewayId"]
        return None

    def _ensure_internet_gateway(
        self,
        vpc_id: str,
        tags: list[dict[str, str]],
        created: list[dict[str, str]],
    ) -> str:
        gateways = self._safe_call(lambda: self._ec2.describe_internet_gateways())
        for igw in gateways.get("InternetGateways", []):
            for attachment in igw.get("Attachments", []):
                if attachment.get("VpcId") == vpc_id:
                    igw_id = igw["InternetGatewayId"]
                    if tags:
                        self._apply_tags([igw_id], tags)
                    return igw_id

        igw_id = self._safe_call(
            lambda: self._ec2.create_internet_gateway(
                TagSpecifications=[{"ResourceType": "internet-gateway", "Tags": tags}],
            )["InternetGateway"]["InternetGatewayId"],
        )
        created.append({"type": "internet_gateway", "id": igw_id, "vpc_id": vpc_id})
        self._safe_call(
            lambda: self._ec2.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id),
        )
        return igw_id

    def _validate_public_routes(
        self,
        vpc_id: str,
        public_subnet_ids: list[str],
        tags: list[dict[str, str]],
    ) -> list[str]:
        route_table_map, main_route_table = self._route_table_lookup(vpc_id)
        missing_routes = []
        route_table_ids: set[str] = set()

        for subnet_id in public_subnet_ids:
            rt_id, has_igw = route_table_map.get(subnet_id, main_route_table) or (None, False)
            if not rt_id or not has_igw:
                missing_routes.append(subnet_id)
                continue
            route_table_ids.add(rt_id)

        if missing_routes:
            raise ValueError(
                f"Subnets lack a route to an internet gateway: {', '.join(missing_routes)}. "
                "Attach routes manually or enable attach_internet_gateway.",
            )

        if main_route_table:
            route_table_ids.add(main_route_table[0])
        if tags and route_table_ids:
            self._apply_tags(list(route_table_ids), tags)
        return list(route_table_ids)

    def _enable_vpc_dns(self, vpc_id: str) -> None:
        self._safe_call(
            lambda: self._ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={"Value": True}),
        )
        self._safe_call(
            lambda: self._ec2.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={"Value": True}),
        )

    def _apply_network_acl_defaults(self, vpc_id: str, tags: list[dict[str, str]]) -> None:
        """Tag the default network ACL to align with tagging strategy."""
        nacls = self._safe_call(
            lambda: self._ec2.describe_network_acls(
                Filters=[{"Name": "vpc-id", "Values": [vpc_id]}],
            ),
        )
        for nacl in nacls.get("NetworkAcls", []):
            if nacl.get("IsDefault") and tags:
                self._apply_tags([nacl["NetworkAclId"]], tags)
                return

    def _subnet_resources(self, vpc_id: str) -> list[SubnetResource]:
        route_table_map, main_route_table = self._route_table_lookup(vpc_id)
        paginator = self._ec2.get_paginator("describe_subnets")
        subnets: list[SubnetResource] = []
        for page in paginator.paginate(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]):
            for subnet in page.get("Subnets", []):
                subnet_id = subnet["SubnetId"]
                route_table_id, has_igw = route_table_map.get(subnet_id, main_route_table) or (None, False)
                is_public = bool(
                    subnet.get("MapPublicIpOnLaunch", False) or has_igw,
                )
                subnets.append(
                    SubnetResource(
                        subnet_id=subnet_id,
                        vpc_id=subnet["VpcId"],
                        cidr_block=subnet["CidrBlock"],
                        availability_zone=subnet["AvailabilityZone"],
                        is_public=is_public,
                        route_table_id=route_table_id,
                    ),
                )
        return subnets

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

    def _main_route_table_id(self, vpc_id: str) -> str | None:
        _, main = self._route_table_lookup(vpc_id)
        return main[0] if main else None

    def _apply_tags(self, resource_ids: list[str], tags: list[dict[str, str]]) -> None:
        if not tags:
            return
        self._safe_call(lambda: self._ec2.create_tags(Resources=resource_ids, Tags=tags))

    def _tag_value(self, tags: list[dict[str, str]], key: str) -> str | None:
        for tag in tags:
            if tag.get("Key") == key:
                return tag.get("Value")
        return None

    def _build_tags(
        self,
        name: str | None,
        deployment: str | None,
        tier: str | None,
    ) -> list[dict[str, str]]:
        tags: list[dict[str, str]] = []
        if deployment and tier:
            tags.extend(self._tagger.build_tags(deployment, tier))
        if name:
            tags.append({"Key": "Name", "Value": name})
        # Dedupe tags by key preserving order
        seen: set[str] = set()
        deduped: list[dict[str, str]] = []
        for tag in tags:
            key = tag.get("Key")
            if key and key not in seen:
                deduped.append(tag)
                seen.add(key)
        return deduped

    def _rollback(self, created: list[dict[str, str]]) -> None:
        """Best-effort rollback in reverse creation order."""
        for resource in reversed(created):
            r_type = resource.get("type")
            r_id = resource.get("id")
            try:
                if r_type == "route_table" and r_id:
                    self._delete_route_table(r_id)
                elif r_type == "subnet" and r_id:
                    self._safe_call(lambda: self._ec2.delete_subnet(SubnetId=r_id))
                elif r_type == "internet_gateway" and r_id:
                    vpc_id = resource.get("vpc_id")
                    if vpc_id:
                        try:
                            self._safe_call(
                                lambda: self._ec2.detach_internet_gateway(
                                    InternetGatewayId=r_id,
                                    VpcId=vpc_id,
                                ),
                            )
                        except RuntimeError:
                            pass
                    self._safe_call(lambda: self._ec2.delete_internet_gateway(InternetGatewayId=r_id))
                elif r_type == "vpc" and r_id:
                    self._safe_call(lambda: self._ec2.delete_vpc(VpcId=r_id))
            except Exception:
                # Rollback is best-effort; swallow errors to continue cleanup.
                continue

    def _delete_route_table(self, route_table_id: str) -> None:
        """Disassociate and delete a route table."""
        try:
            table = self._safe_call(
                lambda: self._ec2.describe_route_tables(RouteTableIds=[route_table_id]),
            )["RouteTables"][0]
        except RuntimeError:
            return

        for assoc in table.get("Associations", []):
            if assoc.get("Main"):
                continue
            assoc_id = assoc.get("RouteTableAssociationId")
            if assoc_id:
                try:
                    self._safe_call(lambda: self._ec2.disassociate_route_table(AssociationId=assoc_id))
                except (RuntimeError, ClientError):
                    continue
        try:
            self._safe_call(lambda: self._ec2.delete_route_table(RouteTableId=route_table_id))
        except RuntimeError:
            return


__all__ = ["VPCService"]
