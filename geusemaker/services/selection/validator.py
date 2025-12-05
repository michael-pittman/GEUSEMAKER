"""Dependency validation between selected resources."""

from __future__ import annotations

from geusemaker.models.discovery import (
    ALBInfo,
    CloudFrontInfo,
    EFSInfo,
    SecurityGroupInfo,
    SubnetInfo,
    ValidationResult,
)


class DependencyValidator:
    """Validate compatibility between dependent resources."""

    def validate_subnet_in_vpc(
        self,
        subnet: SubnetInfo,
        vpc_id: str,
    ) -> ValidationResult:
        result = ValidationResult.ok()
        if subnet.vpc_id != vpc_id:
            result.add_issue(
                f"Subnet {subnet.subnet_id} is in VPC {subnet.vpc_id}, expected {vpc_id}",
            )
        return result

    def validate_security_group_vpc(
        self,
        group: SecurityGroupInfo,
        vpc_id: str,
    ) -> ValidationResult:
        result = ValidationResult.ok()
        if group.vpc_id != vpc_id:
            result.add_issue(
                f"Security group {group.security_group_id} is in VPC {group.vpc_id}, expected {vpc_id}",
            )
        return result

    def validate_efs_mount_targets(
        self,
        efs: EFSInfo,
        subnet_ids: list[str],
    ) -> ValidationResult:
        result = ValidationResult.ok()
        targets = {mt.subnet_id for mt in efs.mount_targets}
        missing = [subnet for subnet in subnet_ids if subnet not in targets]
        if missing:
            result.add_issue(
                f"EFS {efs.file_system_id} has no mount targets in subnets: {', '.join(missing)}",
            )
        return result

    def validate_alb_vpc(self, alb: ALBInfo, vpc_id: str) -> ValidationResult:
        result = ValidationResult.ok()
        if alb.vpc_id != vpc_id:
            result.add_issue(
                f"ALB {alb.name} is in VPC {alb.vpc_id}, expected {vpc_id}",
            )
        return result

    def validate_cloudfront_origin(
        self,
        distribution: CloudFrontInfo,
        origin_domain: str,
    ) -> ValidationResult:
        result = ValidationResult.ok()
        if origin_domain not in distribution.origins:
            result.add_issue(
                f"Origin {origin_domain} not present on CloudFront distribution {distribution.distribution_id}",
            )
        return result


__all__ = ["DependencyValidator"]
