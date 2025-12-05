"""Resource selection helpers with provenance tracking."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, TypeVar

from geusemaker.models.discovery import (
    ALBInfo,
    CloudFrontInfo,
    EFSInfo,
    KeyPairInfo,
    SecurityGroupInfo,
    SubnetInfo,
    VPCInfo,
)
from geusemaker.models.selection import ResourceProvenance, ResourceSelection

_T = TypeVar("_T")
ResourceType = Literal[
    "vpc",
    "subnet",
    "security_group",
    "key_pair",
    "efs",
    "alb",
    "cloudfront",
]


Chooser = Callable[[list[str]], int]


class ResourceSelector:
    """Select resources with Rich-friendly option ordering."""

    def __init__(self, chooser: Chooser | None = None):
        self._chooser = chooser or (lambda options: 0 if options else -1)

    def select_vpc(
        self,
        vpcs: list[VPCInfo],
        provided_id: str | None = None,
        chooser: Chooser | None = None,
    ) -> ResourceSelection:
        return self._select(
            "vpc",
            vpcs,
            id_getter=lambda v: v.vpc_id,
            label_getter=lambda v: f"{v.vpc_id} ({v.cidr_block})",
            provided_id=provided_id,
            chooser=chooser,
        )

    def select_subnet(
        self,
        subnets: list[SubnetInfo],
        provided_id: str | None = None,
        chooser: Chooser | None = None,
    ) -> ResourceSelection:
        return self._select(
            "subnet",
            subnets,
            id_getter=lambda s: s.subnet_id,
            label_getter=lambda s: f"{s.subnet_id} ({s.availability_zone})",
            provided_id=provided_id,
            chooser=chooser,
        )

    def select_security_group(
        self,
        groups: list[SecurityGroupInfo],
        provided_id: str | None = None,
        chooser: Chooser | None = None,
    ) -> ResourceSelection:
        return self._select(
            "security_group",
            groups,
            id_getter=lambda g: g.security_group_id,
            label_getter=lambda g: f"{g.security_group_id} ({g.name})",
            provided_id=provided_id,
            chooser=chooser,
        )

    def select_key_pair(
        self,
        key_pairs: list[KeyPairInfo],
        provided_id: str | None = None,
        chooser: Chooser | None = None,
    ) -> ResourceSelection:
        return self._select(
            "key_pair",
            key_pairs,
            id_getter=lambda k: k.key_name,
            label_getter=lambda k: k.key_name,
            provided_id=provided_id,
            chooser=chooser,
        )

    def select_efs(
        self,
        filesystems: list[EFSInfo],
        provided_id: str | None = None,
        chooser: Chooser | None = None,
    ) -> ResourceSelection:
        return self._select(
            "efs",
            filesystems,
            id_getter=lambda e: e.file_system_id,
            label_getter=lambda e: f"{e.file_system_id} ({e.lifecycle_state})",
            provided_id=provided_id,
            chooser=chooser,
        )

    def select_alb(
        self,
        albs: list[ALBInfo],
        provided_id: str | None = None,
        chooser: Chooser | None = None,
    ) -> ResourceSelection:
        return self._select(
            "alb",
            albs,
            id_getter=lambda a: a.arn,
            label_getter=lambda a: f"{a.name} ({a.scheme})",
            provided_id=provided_id,
            chooser=chooser,
        )

    def select_cloudfront(
        self,
        distributions: list[CloudFrontInfo],
        provided_id: str | None = None,
        chooser: Chooser | None = None,
    ) -> ResourceSelection:
        return self._select(
            "cloudfront",
            distributions,
            id_getter=lambda c: c.distribution_id,
            label_getter=lambda c: c.domain_name,
            provided_id=provided_id,
            chooser=chooser,
        )

    def _select(
        self,
        resource_type: ResourceType,
        items: list[_T],
        id_getter: Callable[[_T], str],
        label_getter: Callable[[_T], str],
        provided_id: str | None,
        chooser: Chooser | None,
    ) -> ResourceSelection:
        # Non-interactive path when caller provides an explicit ID
        if provided_id:
            for item in items:
                if id_getter(item) == provided_id:
                    return self._selection(resource_type, id_getter(item), item, ResourceProvenance.REUSED)
            return ResourceSelection(
                resource_type=resource_type,
                resource_id=provided_id,
                provenance=ResourceProvenance.AUTO_DISCOVERED,
                original_state=None,
            )

        options = ["Create New"] + [label_getter(item) for item in items]
        choice_fn = chooser or self._chooser
        index = choice_fn(options)
        if index < 0 or index >= len(options):
            raise ValueError(f"Selection index {index} is out of range for {resource_type}")

        if index == 0:
            return ResourceSelection(
                resource_type=resource_type,
                resource_id=None,
                provenance=ResourceProvenance.CREATED,
                original_state=None,
            )
        item = items[index - 1]
        return self._selection(resource_type, id_getter(item), item, ResourceProvenance.REUSED)

    def _selection(
        self,
        resource_type: ResourceType,
        resource_id: str,
        item: _T,
        provenance: ResourceProvenance,
    ) -> ResourceSelection:
        state = self._to_dict(item)
        return ResourceSelection(
            resource_type=resource_type,
            resource_id=resource_id,
            provenance=provenance,
            original_state=state,
        )

    def _to_dict(self, item: _T) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return item.model_dump()  # type: ignore[return-value]
        if hasattr(item, "__dict__"):
            return dict(item.__dict__)
        return {}


__all__ = ["ResourceSelector"]
