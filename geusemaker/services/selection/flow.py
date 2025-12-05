"""Simple orchestration for resource selection and dependency validation."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from geusemaker.models.discovery import (
    ALBInfo,
    CloudFrontInfo,
    EFSInfo,
    KeyPairInfo,
    SecurityGroupInfo,
    SubnetInfo,
    ValidationResult,
    VPCInfo,
)
from geusemaker.models.selection import ResourceSelection, SelectionResult
from geusemaker.services.selection.selector import ResourceSelector
from geusemaker.services.selection.validator import DependencyValidator

_T = TypeVar("_T")


class ResourceSelectionFlow:
    """Coordinates sequential selection steps for deployments."""

    def __init__(
        self,
        selector: ResourceSelector | None = None,
        validator: DependencyValidator | None = None,
    ):
        self.selector = selector or ResourceSelector()
        self.validator = validator or DependencyValidator()

    def run(
        self,
        vpcs: list[VPCInfo],
        subnets: list[SubnetInfo],
        security_groups: list[SecurityGroupInfo],
        key_pairs: list[KeyPairInfo],
        efs_list: list[EFSInfo] | None = None,
        alb_list: list[ALBInfo] | None = None,
        cloudfront_list: list[CloudFrontInfo] | None = None,
        provided_ids: dict[str, str] | None = None,
    ) -> SelectionResult:
        provided_ids = provided_ids or {}

        vpc_sel = self.selector.select_vpc(vpcs, provided_ids.get("vpc"))
        chosen_vpc = vpc_sel.resource_id or (vpcs[0].vpc_id if vpcs else None)

        subnet_candidates = _filter_by_vpc(subnets, chosen_vpc)
        subnet_sel = self.selector.select_subnet(
            subnet_candidates,
            provided_ids.get("subnet"),
        )

        sg_candidates = _filter_by_vpc(security_groups, chosen_vpc)
        sg_sel = self.selector.select_security_group(
            sg_candidates,
            provided_ids.get("security_group"),
        )

        key_sel = self.selector.select_key_pair(key_pairs, provided_ids.get("key_pair"))

        efs_sel: ResourceSelection | None = None
        if efs_list is not None:
            efs_sel = self.selector.select_efs(efs_list, provided_ids.get("efs"))

        alb_sel: ResourceSelection | None = None
        if alb_list is not None:
            alb_sel = self.selector.select_alb(alb_list, provided_ids.get("alb"))

        cloudfront_sel: ResourceSelection | None = None
        if cloudfront_list is not None:
            cloudfront_sel = self.selector.select_cloudfront(
                cloudfront_list,
                provided_ids.get("cloudfront"),
            )

        validations: list[ValidationResult] = []
        if subnet_sel.resource_id and chosen_vpc:
            subnet_obj = _find(subnet_candidates, subnet_sel.resource_id, lambda s: s.subnet_id)
            if subnet_obj:
                validations.append(
                    self.validator.validate_subnet_in_vpc(subnet_obj, chosen_vpc),
                )
        if sg_sel.resource_id and chosen_vpc:
            sg_obj = _find(sg_candidates, sg_sel.resource_id, lambda g: g.security_group_id)
            if sg_obj:
                validations.append(
                    self.validator.validate_security_group_vpc(sg_obj, chosen_vpc),
                )
        if efs_sel and efs_sel.resource_id and subnet_sel.resource_id and efs_list:
            efs_obj = _find(efs_list, efs_sel.resource_id, lambda e: e.file_system_id)
            if efs_obj:
                validations.append(
                    self.validator.validate_efs_mount_targets(
                        efs_obj,
                        [subnet_sel.resource_id],
                    ),
                )
        if alb_sel and alb_sel.resource_id and alb_list and chosen_vpc:
            alb_obj = _find(alb_list, alb_sel.resource_id, lambda a: a.arn)
            if alb_obj:
                validations.append(self.validator.validate_alb_vpc(alb_obj, chosen_vpc))

        return SelectionResult(
            vpc=vpc_sel,
            subnets=[subnet_sel],
            security_group=sg_sel,
            key_pair=key_sel,
            efs=efs_sel,
            alb=alb_sel,
            cloudfront=cloudfront_sel,
            validations=validations,
        )


def _filter_by_vpc(items: list[_T], vpc_id: str | None) -> list[_T]:
    if vpc_id is None:
        return items
    matches: list[_T] = []
    for item in items:
        if getattr(item, "vpc_id", None) == vpc_id:
            matches.append(item)
    return matches or items


def _find(
    items: list[_T],
    needle: str,
    key_fn: Callable[[_T], str],
) -> _T | None:
    for item in items:
        if key_fn(item) == needle:
            return item
    return None


__all__ = ["ResourceSelectionFlow"]
