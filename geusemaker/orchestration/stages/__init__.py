"""Stateless stage helpers for the Tier1 deployment coordinator.

These modules hold the heavy, self-contained computational logic that used to
live inside ``Tier1Orchestrator``'s private methods. They take explicit
arguments (service objects, config, resource ids) rather than ``self`` so the
coordinator stays a thin sequencer while the bulk logic is unit-testable in
isolation.

No module here imports ``geusemaker.cli`` — presentation depends on
orchestration, never the reverse (enforced by the import-direction guard test).
"""

from __future__ import annotations

from geusemaker.orchestration.stages.alb import (
    build_n8n_url_patch_commands,
    build_tier2_state,
    create_alb,
    select_alb_subnets,
)
from geusemaker.orchestration.stages.ami import (
    build_block_device_mappings,
    detect_root_device,
    resolve_ami,
)
from geusemaker.orchestration.stages.cloudfront import (
    build_tier3_state,
    create_cloudfront,
    wait_for_cloudfront,
)
from geusemaker.orchestration.stages.compute_launch import launch_instance
from geusemaker.orchestration.stages.finalize import build_final_state, build_partial_state
from geusemaker.orchestration.stages.networking import (
    resolve_networking,
    resolve_security_group,
)
from geusemaker.orchestration.stages.storage import create_storage
from geusemaker.orchestration.stages.userdata_stage import build_userdata_config, compress_userdata

__all__ = [
    "build_block_device_mappings",
    "build_final_state",
    "build_n8n_url_patch_commands",
    "build_partial_state",
    "build_tier2_state",
    "build_tier3_state",
    "build_userdata_config",
    "compress_userdata",
    "create_alb",
    "create_cloudfront",
    "create_storage",
    "detect_root_device",
    "launch_instance",
    "resolve_ami",
    "resolve_networking",
    "resolve_security_group",
    "select_alb_subnets",
    "wait_for_cloudfront",
]
