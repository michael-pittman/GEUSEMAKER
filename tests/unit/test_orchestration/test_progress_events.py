"""Recording-callback tests for the tier orchestrators' ProgressEvent timelines."""

from __future__ import annotations

from decimal import Decimal

import pytest

from geusemaker.cli.progress_events import ProgressEvent
from geusemaker.models import DeploymentConfig
from geusemaker.models.compute import InstanceSelection, SavingsComparison
from geusemaker.orchestration.errors import OrchestrationError
from geusemaker.orchestration.tier1 import Tier1Orchestrator
from geusemaker.orchestration.tier2 import Tier2Orchestrator
from geusemaker.orchestration.tier3 import Tier3Orchestrator
from tests.unit.test_orchestration.conftest import (
    StubALBService,
    StubClientFactory,
    StubCloudFrontService,
    StubEC2Service,
    StubEFSService,
    StubIAMService,
    StubSecurityGroupService,
    StubSSMService,
    StubStateManager,
    StubUserDataGenerator,
    StubVPCService,
)

TIER1_STAGE_SEQUENCE = [
    "spot",
    "vpc",
    "vpc",
    "sg",
    "sg",
    "efs",
    "efs",
    "iam",
    "userdata",
    "ec2",
    "ec2",
    "finalize",
]
TIER2_STAGE_SEQUENCE = [*TIER1_STAGE_SEQUENCE[:-1], "userdata", "alb", "alb", "health", "finalize"]
TIER3_STAGE_SEQUENCE = [*TIER2_STAGE_SEQUENCE[:-1], "cdn", "cdn", "finalize"]


def _on_demand_selection(instance_type: str = "t3.medium") -> InstanceSelection:
    hourly = Decimal("0.0416")
    return InstanceSelection(
        instance_type=instance_type,
        availability_zone="us-east-1a",
        is_spot=False,
        price_per_hour=hourly,
        selection_reason="On-demand requested",
        fallback_reason=None,
        savings_vs_on_demand=SavingsComparison(
            on_demand_hourly=hourly,
            selected_hourly=hourly,
            hourly_savings=Decimal("0"),
            monthly_savings=Decimal("0"),
            savings_percentage=0.0,
        ),
        pricing_source="live",
    )


def _stub_services(orch: Tier1Orchestrator) -> None:
    """Replace every AWS-backed service on the orchestrator with offline stubs."""
    orch.vpc_service = StubVPCService()  # type: ignore[assignment]
    orch.sg_service = StubSecurityGroupService()  # type: ignore[assignment]
    orch.efs_service = StubEFSService()  # type: ignore[assignment]
    orch.iam_service = StubIAMService()  # type: ignore[assignment]
    orch.ec2_service = StubEC2Service()  # type: ignore[assignment]
    orch.userdata_generator = StubUserDataGenerator()  # type: ignore[assignment]
    if isinstance(orch, Tier2Orchestrator):
        orch.alb_service = StubALBService()  # type: ignore[assignment]
        orch.ssm_service = StubSSMService()  # type: ignore[assignment]
    if isinstance(orch, Tier3Orchestrator):
        orch.cloudfront_service = StubCloudFrontService()  # type: ignore[assignment]


def _build_orchestrator(
    orchestrator_cls: type[Tier1Orchestrator],
    events: list[ProgressEvent] | None,
    instance_type: str = "t3.medium",
) -> Tier1Orchestrator:
    on_progress = events.append if events is not None else None
    orch = orchestrator_cls(
        client_factory=StubClientFactory(),  # type: ignore[arg-type]
        region="us-east-1",
        state_manager=StubStateManager(),  # type: ignore[arg-type]
        on_progress=on_progress,
    )
    _stub_services(orch)
    orch._preselected_selection = _on_demand_selection(instance_type)
    return orch


def test_tier1_emits_complete_stage_sequence() -> None:
    events: list[ProgressEvent] = []
    orch = _build_orchestrator(Tier1Orchestrator, events)
    config = DeploymentConfig(stack_name="stack", tier="dev", use_spot=False)

    orch.deploy(config, enable_rollback=False)

    assert [event.stage for event in events] == TIER1_STAGE_SEQUENCE
    assert all(event.level == "info" for event in events)
    # resource_id must be attached once the resource exists.
    by_resource = {event.resource_id for event in events}
    assert {"vpc-new", "sg-1", "fs-1", "i-1234567890abcdef0"} <= by_resource


def test_tier2_emits_alb_and_health_stages() -> None:
    events: list[ProgressEvent] = []
    orch = _build_orchestrator(Tier2Orchestrator, events)
    config = DeploymentConfig(
        stack_name="stack-t2",
        tier="automation",
        instance_type="t3.medium",
        enable_alb=True,
        enable_https=False,
        use_spot=False,
    )

    orch.deploy(config, enable_rollback=False)

    assert [event.stage for event in events] == TIER2_STAGE_SEQUENCE
    alb_resource_events = [event for event in events if event.stage == "alb" and event.resource_id]
    assert len(alb_resource_events) == 1
    assert "loadbalancer" in alb_resource_events[0].resource_id  # type: ignore[operator]


def test_tier2_without_alb_matches_tier1_sequence() -> None:
    """enable_alb=False must not emit alb/health stages."""
    events: list[ProgressEvent] = []
    orch = _build_orchestrator(Tier2Orchestrator, events)
    config = DeploymentConfig(
        stack_name="stack-t2-noalb",
        tier="dev",
        enable_alb=False,
        enable_https=False,
        use_spot=False,
    )

    orch.deploy(config, enable_rollback=False)

    assert [event.stage for event in events] == TIER1_STAGE_SEQUENCE


def test_tier3_emits_cdn_stage() -> None:
    events: list[ProgressEvent] = []
    orch = _build_orchestrator(Tier3Orchestrator, events, instance_type="g4dn.xlarge")
    config = DeploymentConfig(
        stack_name="stack-t3",
        tier="gpu",
        instance_type="g4dn.xlarge",
        enable_alb=True,
        enable_https=False,
        use_spot=False,
    )

    orch.deploy(config, enable_rollback=False)

    assert [event.stage for event in events] == TIER3_STAGE_SEQUENCE
    cdn_resource_events = [event for event in events if event.stage == "cdn" and event.resource_id]
    assert [event.resource_id for event in cdn_resource_events] == ["E1234567890ABC"]


def test_no_callback_is_zero_behavior_change() -> None:
    """on_progress=None must deploy exactly as before (no events, no errors)."""
    orch = _build_orchestrator(Tier1Orchestrator, None)
    config = DeploymentConfig(stack_name="stack-silent", tier="dev", use_spot=False)

    state = orch.deploy(config, enable_rollback=False)

    assert state.vpc_id == "vpc-new"
    assert orch.on_progress is None


class FailingEFSService(StubEFSService):
    """Raise during filesystem creation to exercise error events."""

    def create_filesystem(self, tags):  # type: ignore[no-untyped-def]  # noqa: ARG002
        raise RuntimeError("EFS create failed")


def test_error_event_emitted_on_stage_failure() -> None:
    events: list[ProgressEvent] = []
    orch = _build_orchestrator(Tier1Orchestrator, events)
    orch.efs_service = FailingEFSService()  # type: ignore[assignment]
    config = DeploymentConfig(stack_name="stack-fail", tier="dev", use_spot=False)

    with pytest.raises(OrchestrationError):
        orch.deploy(config, enable_rollback=False)

    assert [event.stage for event in events] == ["spot", "vpc", "vpc", "sg", "sg", "efs", "efs"]
    assert events[-1].stage == "efs"
    assert events[-1].level == "error"
    assert "EFS create failed" in events[-1].message
    assert all(event.level == "info" for event in events[:-1])
