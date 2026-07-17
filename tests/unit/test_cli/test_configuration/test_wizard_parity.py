"""Parity tests: the wizard and ConfigBuilder must build identical configs.

Drives the real InteractiveFlow with scripted inputs (reusing the fakes from
tests/unit/test_cli/test_interactive/test_flow.py) and asserts that
ConfigBuilder.from_initial_state(flow.state).build() matches the wizard's
DeploymentConfig (docs/tui-brutalist-rollout.md section 11).

No AWS, network, or boto3 clients: the flow gets a stub client factory, fake
discovery/cost services, and a fake instance selector.

The wizard's `_build_config` now delegates to ConfigBuilder, so prefilled
fields it previously dropped (budget_limit, enable_alb, enable_cdn,
use_runtime_bundle, runtime_bundle_path, alb_certificate_arn,
cloudfront_certificate_arn, auto_rollback_on_failure,
rollback_timeout_minutes) propagate into the final config; the full-parity
test below locks that in.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from geusemaker.cli.components.dialogs import Dialogs, scripted_inputs
from geusemaker.cli.configuration import ConfigBuilder
from geusemaker.cli.interactive.flow import InteractiveFlow, InteractiveSessionStore
from geusemaker.models import DeploymentConfig
from geusemaker.models.discovery import HostedZoneInfo
from tests.unit.test_cli.test_interactive.test_flow import FakeDiscovery, FakeEstimator


class _FakeClientFactory:
    """Stub AWSClientFactory: never touches boto3/network."""

    def get_client(self, service: str, region: str = "us-east-1") -> object:
        return object()

    def clear_cache(self) -> None:  # pragma: no cover - interface parity only
        return None


class _FakeSelector:
    """Stub InstanceTypeSelector: deterministic recommendation, no AWS."""

    def __init__(self, **_kwargs: Any) -> None:
        return None

    def select_best_instance(
        self,
        compute_type: str,
        use_spot: bool = True,
        region: str | None = None,
        preference: str = "balanced",
    ) -> SimpleNamespace:
        instance_type = "g4dn.xlarge" if compute_type == "gpu" else "t3.medium"
        return SimpleNamespace(
            instance_type=instance_type,
            reason=f"{preference} policy, {compute_type.upper()}, scripted",
            fallback_occurred=False,
            alternatives=(),
        )


class _FakeDiscoveryWithZones(FakeDiscovery):
    """FakeDiscovery plus Route 53 zones for the Tier 2 HTTPS path."""

    def list_hosted_zones(self) -> list[HostedZoneInfo]:
        return [
            HostedZoneInfo(hosted_zone_id="Z0123456789ABCDEF", name="example.com.", private_zone=False),
        ]


def _run_wizard(
    dialog_sequence: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    discovery: FakeDiscovery | None = None,
    initial_state: dict[str, Any] | None = None,
) -> tuple[DeploymentConfig, dict[str, Any]]:
    monkeypatch.setattr("geusemaker.services.compute.InstanceTypeSelector", _FakeSelector)
    flow = InteractiveFlow(
        client_factory=_FakeClientFactory(),  # type: ignore[arg-type]
        dialogs=Dialogs(input_provider=scripted_inputs(dialog_sequence)),
        session_store=InteractiveSessionStore(base_path=tmp_path),
        initial_state=initial_state or {"region": "us-east-1"},
    )
    flow._discovery = discovery or FakeDiscovery()
    flow._cost_estimator = FakeEstimator()
    config = flow.run()
    return config, flow.state


QUICK_DEV_SEQUENCE = [
    "quick-parity",  # stack name
    "1",  # region us-east-1
    "1",  # quick setup
    "",  # tier default (dev)
    "",  # enable_https default yes
    "",  # tier1 self-signed default yes
    "",  # compute type default (cpu)
    "",  # accept instance recommendation
    "",  # accept costs
    "",  # confirm deploy
]

ADVANCED_AUTOMATION_SEQUENCE = [
    "adv-parity",  # stack name
    "1",  # region us-east-1
    "2",  # advanced setup
    "2",  # tier automation
    "",  # enable_https default yes
    "",  # compute type default (cpu)
    "",  # instance recommendation policy default (balanced)
    "",  # use spot default yes
    "",  # accept instance recommendation
    "",  # os_type default (ubuntu-22.04)
    "",  # architecture default (x86_64)
    "",  # ami_type default (base)
    "n",  # custom ami_id: no
    "",  # accept costs
    "1",  # hosted zone (first, no create-new entry)
    "",  # FQDN: accept default stack.zone name
    "2",  # choose existing vpc (option 2 after "Create new")
    "1",  # compute subnet
    "1",  # storage subnet
    "2",  # security group existing
    "2",  # EFS filesystem existing
    "2",  # key pair existing
    "",  # confirm deploy
]


def test_quick_dev_wizard_matches_config_builder(monkeypatch, tmp_path) -> None:
    wizard_config, state = _run_wizard(QUICK_DEV_SEQUENCE, monkeypatch, tmp_path)
    builder_config = ConfigBuilder.from_initial_state(state).build()

    # Spot-check the fields the wizard emits today...
    assert wizard_config.stack_name == "quick-parity"
    assert wizard_config.tier == "dev"
    assert wizard_config.workload == "cpu"
    assert wizard_config.instance_type == "t3.medium"
    assert wizard_config.vpc_id is None
    assert wizard_config.efs_id is None
    # ...and require the shared code path to reproduce them exactly. Neither
    # side sets the fields the wizard currently drops, so full model equality
    # holds for this fixture.
    assert builder_config == wizard_config


def test_advanced_automation_https_wizard_matches_config_builder(monkeypatch, tmp_path) -> None:
    wizard_config, state = _run_wizard(
        ADVANCED_AUTOMATION_SEQUENCE,
        monkeypatch,
        tmp_path,
        discovery=_FakeDiscoveryWithZones(),
    )
    builder_config = ConfigBuilder.from_initial_state(state).build()

    assert wizard_config.stack_name == "adv-parity"
    assert wizard_config.tier == "automation"
    assert wizard_config.enable_https is True
    assert wizard_config.alb_domain_name == "adv-parity.example.com"
    assert wizard_config.alb_hosted_zone_id == "Z0123456789ABCDEF"
    assert wizard_config.vpc_id == "vpc-1"
    assert wizard_config.subnet_id == "subnet-public"
    assert wizard_config.storage_subnet_id == "subnet-private"
    assert wizard_config.security_group_id == "sg-1"
    assert wizard_config.efs_id == "fs-1"
    assert wizard_config.keypair_name == "kp-1"
    assert builder_config == wizard_config


def test_parity_preview_metadata_stays_out_of_config(monkeypatch, tmp_path) -> None:
    _, state = _run_wizard(QUICK_DEV_SEQUENCE, monkeypatch, tmp_path)
    # The wizard records preview metadata in its session state...
    assert "_instance_selection_reason" in state
    assert "cost_monthly_estimate" in state
    builder = ConfigBuilder.from_initial_state(state)
    # ...which the builder captures on the draft but excludes from the config.
    assert builder.draft.instance_selection_reason == state["_instance_selection_reason"]
    config = builder.build()
    assert not hasattr(config, "instance_selection_reason")
    assert not hasattr(config, "cost_monthly_estimate")


def test_full_parity_including_fields_wizard_currently_drops(monkeypatch, tmp_path) -> None:
    """The wizard now routes through ConfigBuilder, so prefills like
    budget_limit/use_runtime_bundle/rollback settings survive into the config."""
    initial_state = {
        "region": "us-east-1",
        "budget_limit": "42.50",
        "use_runtime_bundle": True,
        "rollback_timeout_minutes": 30,
        "auto_rollback_on_failure": False,
    }
    wizard_config, state = _run_wizard(
        QUICK_DEV_SEQUENCE,
        monkeypatch,
        tmp_path,
        initial_state=initial_state,
    )
    # The wizard itself must retain the prefilled values (equality alone would
    # also hold if both sides dropped them).
    assert wizard_config.budget_limit == Decimal("42.50")
    assert wizard_config.use_runtime_bundle is True
    assert wizard_config.rollback_timeout_minutes == 30
    assert wizard_config.auto_rollback_on_failure is False

    builder_config = ConfigBuilder.from_initial_state(state).build()
    assert builder_config == wizard_config
