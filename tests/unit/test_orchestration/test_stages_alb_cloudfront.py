"""Focused unit tests for the extracted Tier2/Tier3 stage helper functions.

These exercise the pure/computational logic moved out of ``Tier2Orchestrator``
and ``Tier3Orchestrator`` into ``geusemaker.orchestration.stages.alb`` and
``geusemaker.orchestration.stages.cloudfront`` during the Phase 4 decomposition.
They assert behavior parity with the coordinators' former inline implementations.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from geusemaker.models import DeploymentConfig
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.stages import (
    build_n8n_url_patch_commands,
    create_alb,
    select_alb_subnets,
)
from tests.unit.test_orchestration.conftest import StubALBService


class _FakeEC2WithSubnets:
    def __init__(self, subnets: list[dict] | None = None, *, error: bool = False) -> None:
        self._subnets = subnets
        self._error = error

    def describe_subnets(self, subnet_ids):  # type: ignore[no-untyped-def]  # noqa: ARG002
        if self._error:
            raise RuntimeError("boom")
        return self._subnets


def test_build_n8n_url_patch_commands_is_bash_with_env_keys() -> None:
    cmds = build_n8n_url_patch_commands("app.example.com", "https", 2)

    assert cmds[0] == "#!/bin/bash"
    joined = "\n".join(cmds)
    for key in (
        "N8N_HOST=app.example.com",
        "N8N_PROTOCOL=https",
        "WEBHOOK_URL=https://app.example.com/",
        "N8N_EDITOR_BASE_URL=https://app.example.com",
        "N8N_SECURE_COOKIE=true",
        "N8N_PROXY_HOPS=2",
    ):
        assert key in joined


def test_build_n8n_url_patch_commands_http_disables_secure_cookie() -> None:
    cmds = build_n8n_url_patch_commands("alb.example.com", "http", 1)
    joined = "\n".join(cmds)
    assert "N8N_SECURE_COOKIE=false" in joined
    assert "N8N_PROXY_HOPS=1" in joined


def test_select_alb_subnets_prefers_public_distinct_azs() -> None:
    ec2 = _FakeEC2WithSubnets(
        [
            {"SubnetId": "subnet-priv-a", "AvailabilityZone": "us-east-1a", "MapPublicIpOnLaunch": False},
            {"SubnetId": "subnet-pub-a", "AvailabilityZone": "us-east-1a", "MapPublicIpOnLaunch": True},
            {"SubnetId": "subnet-pub-b", "AvailabilityZone": "us-east-1b", "MapPublicIpOnLaunch": True},
        ]
    )
    state = SimpleNamespace(subnet_ids=["subnet-priv-a", "subnet-pub-a", "subnet-pub-b"])

    chosen = select_alb_subnets(ec2, state)  # type: ignore[arg-type]

    assert chosen == ["subnet-pub-a", "subnet-pub-b"]


def test_select_alb_subnets_prefers_compute_az() -> None:
    """The compute/spot AZ (via preferred_subnet_id) is included and comes first."""
    ec2 = _FakeEC2WithSubnets(
        [
            {"SubnetId": "subnet-pub-a", "AvailabilityZone": "us-east-1a", "MapPublicIpOnLaunch": True},
            {"SubnetId": "subnet-pub-b", "AvailabilityZone": "us-east-1b", "MapPublicIpOnLaunch": True},
            {"SubnetId": "subnet-priv-b", "AvailabilityZone": "us-east-1b", "MapPublicIpOnLaunch": False},
        ]
    )
    state = SimpleNamespace(subnet_ids=["subnet-pub-a", "subnet-pub-b", "subnet-priv-b"])

    # Storage/compute lives in us-east-1b -> ALB should include that AZ first.
    chosen = select_alb_subnets(ec2, state, preferred_subnet_id="subnet-priv-b")  # type: ignore[arg-type]

    assert chosen[0] == "subnet-pub-b"
    assert set(chosen) == {"subnet-pub-a", "subnet-pub-b"}


def test_select_alb_subnets_falls_back_on_error() -> None:
    ec2 = _FakeEC2WithSubnets(error=True)
    state = SimpleNamespace(subnet_ids=["subnet-1", "subnet-2", "subnet-3"])

    assert select_alb_subnets(ec2, state) == ["subnet-1", "subnet-2"]  # type: ignore[arg-type]


def test_select_alb_subnets_falls_back_without_describe() -> None:
    state = SimpleNamespace(subnet_ids=["subnet-1", "subnet-2"])
    assert select_alb_subnets(object(), state) == ["subnet-1", "subnet-2"]  # type: ignore[arg-type]


def test_create_alb_http_only_sets_target_group_port() -> None:
    alb = StubALBService()
    config = DeploymentConfig(stack_name="s", tier="automation", enable_alb=True, enable_https=False)
    state = SimpleNamespace(
        subnet_ids=["subnet-1", "subnet-2"],
        security_group_id="sg-123",
        vpc_id="vpc-123",
    )

    info = create_alb(alb, config, state, ["subnet-1", "subnet-2"], 80)  # type: ignore[arg-type]

    assert alb.alb_created and alb.target_group_created and alb.listener_created
    assert alb.last_target_group_port == 80
    assert info["https_enabled"] is False
    assert info["alb_dns"] == "test-alb-1234567890.us-east-1.elb.amazonaws.com"


def test_create_alb_requires_two_subnets() -> None:
    alb = StubALBService()
    config = DeploymentConfig(stack_name="s", tier="automation", enable_alb=True)
    state = SimpleNamespace(subnet_ids=["subnet-1"], security_group_id="sg-1", vpc_id="vpc-1")

    with pytest.raises(OrchestrationError, match="at least 2 subnets"):
        create_alb(alb, config, state, ["subnet-1"], 80)  # type: ignore[arg-type]
