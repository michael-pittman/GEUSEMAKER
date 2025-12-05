"""Rich table renderers for discovery results."""

from __future__ import annotations

from rich.table import Table

from geusemaker.models.discovery import (
    ALBInfo,
    CloudFrontInfo,
    EFSInfo,
    KeyPairInfo,
    SecurityGroupInfo,
    SubnetInfo,
    VPCInfo,
)


def vpc_table(vpcs: list[VPCInfo]) -> Table:
    table = Table(title="VPCs", expand=True)
    table.add_column("VPC ID", style="cyan")
    table.add_column("Name")
    table.add_column("CIDR")
    table.add_column("Default?")
    table.add_column("IGW?")
    for vpc in vpcs:
        table.add_row(
            vpc.vpc_id,
            vpc.name or "-",
            vpc.cidr_block,
            "Yes" if vpc.is_default else "No",
            "Yes" if vpc.has_internet_gateway else "No",
        )
    return table


def subnet_table(subnets: list[SubnetInfo]) -> Table:
    table = Table(title="Subnets", expand=True)
    table.add_column("Subnet ID", style="cyan")
    table.add_column("Name")
    table.add_column("AZ")
    table.add_column("CIDR")
    table.add_column("Public?")
    table.add_column("Route Table")
    for subnet in subnets:
        table.add_row(
            subnet.subnet_id,
            subnet.name or "-",
            subnet.availability_zone,
            subnet.cidr_block,
            "Yes" if subnet.is_public else "No",
            subnet.route_table_id or "-",
        )
    return table


def security_group_table(groups: list[SecurityGroupInfo]) -> Table:
    table = Table(title="Security Groups", expand=True)
    table.add_column("Group ID", style="cyan")
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Ingress")
    table.add_column("Egress")

    for sg in groups:
        ingress_summary = ", ".join(
            _rule_summary(rule.protocol, rule.from_port, rule.to_port) for rule in sg.ingress_rules
        )
        egress_summary = ", ".join(
            _rule_summary(rule.protocol, rule.from_port, rule.to_port) for rule in sg.egress_rules
        )
        table.add_row(
            sg.security_group_id,
            sg.name,
            sg.description,
            ingress_summary or "-",
            egress_summary or "-",
        )
    return table


def key_pair_table(keys: list[KeyPairInfo]) -> Table:
    table = Table(title="Key Pairs", expand=True)
    table.add_column("Name", style="cyan")
    table.add_column("Fingerprint")
    table.add_column("Type")
    table.add_column("Created")
    for key in keys:
        created = key.created_at.isoformat() if key.created_at else "-"
        table.add_row(key.key_name, key.key_fingerprint, key.key_type, created)
    return table


def efs_table(filesystems: list[EFSInfo]) -> Table:
    table = Table(title="EFS File Systems", expand=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("State")
    table.add_column("Throughput")
    table.add_column("Encrypted")
    table.add_column("Mount Targets")
    for fs in filesystems:
        table.add_row(
            fs.file_system_id,
            fs.name or "-",
            fs.lifecycle_state,
            fs.throughput_mode,
            "Yes" if fs.encrypted else "No",
            ", ".join(mt.subnet_id for mt in fs.mount_targets) or "-",
        )
    return table


def alb_table(albs: list[ALBInfo]) -> Table:
    table = Table(title="Application Load Balancers", expand=True)
    table.add_column("Name", style="cyan")
    table.add_column("ARN")
    table.add_column("State")
    table.add_column("Scheme")
    table.add_column("Listeners")
    for alb in albs:
        listeners = ", ".join(f"{lst.protocol}:{lst.port}" for lst in alb.listeners)
        table.add_row(
            alb.name,
            alb.arn,
            alb.state,
            alb.scheme,
            listeners or "-",
        )
    return table


def cloudfront_table(distributions: list[CloudFrontInfo]) -> Table:
    table = Table(title="CloudFront Distributions", expand=True)
    table.add_column("ID", style="cyan")
    table.add_column("Domain")
    table.add_column("Status")
    table.add_column("Origins")
    for dist in distributions:
        table.add_row(
            dist.distribution_id,
            dist.domain_name,
            dist.status,
            ", ".join(dist.origins) or "-",
        )
    return table


def _rule_summary(protocol: str, from_port: int | None, to_port: int | None) -> str:
    if from_port is None and to_port is None:
        return protocol
    if from_port == to_port:
        return f"{protocol}:{from_port}"
    return f"{protocol}:{from_port}-{to_port}"


__all__ = [
    "alb_table",
    "cloudfront_table",
    "efs_table",
    "key_pair_table",
    "security_group_table",
    "subnet_table",
    "vpc_table",
]
