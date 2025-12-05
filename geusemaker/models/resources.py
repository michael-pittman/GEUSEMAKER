"""Resource models for AWS infrastructure."""

from __future__ import annotations

from pydantic import BaseModel


class SubnetResource(BaseModel):
    subnet_id: str
    vpc_id: str
    cidr_block: str
    availability_zone: str
    is_public: bool
    route_table_id: str | None = None


class VPCResource(BaseModel):
    vpc_id: str
    cidr_block: str
    name: str
    public_subnets: list[SubnetResource]
    private_subnets: list[SubnetResource]
    internet_gateway_id: str
    route_table_ids: list[str]
    created_by_geusemaker: bool = True


__all__ = ["SubnetResource", "VPCResource"]
