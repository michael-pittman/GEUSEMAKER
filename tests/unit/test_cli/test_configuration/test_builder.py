"""Unit tests for the UI-neutral DeploymentDraft / ConfigBuilder seam.

No AWS, network, or boto3 usage anywhere in this module.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from geusemaker.cli.configuration import (
    CONFIG_FIELDS,
    DRAFT_ONLY_FIELDS,
    PREVIEW_FIELDS,
    ConfigBuilder,
    DeploymentDraft,
)
from geusemaker.models import DeploymentConfig
from tests.unit.test_cli.test_configuration.matrix import FIELD_MATRIX, MATRIX_IDS


# ----------------------------------------------------------------------
# Draft field mirror
# ----------------------------------------------------------------------
def test_draft_mirrors_every_config_field_reflectively() -> None:
    missing = set(DeploymentConfig.model_fields) - set(DeploymentDraft.model_fields)
    assert missing == set()
    assert set(CONFIG_FIELDS) == set(DeploymentConfig.model_fields)
    # Draft-only fields must not shadow config fields.
    assert DRAFT_ONLY_FIELDS.isdisjoint(set(DeploymentConfig.model_fields))
    assert PREVIEW_FIELDS <= DRAFT_ONLY_FIELDS


def test_draft_all_fields_default_to_none() -> None:
    draft = DeploymentDraft()
    assert all(getattr(draft, name) is None for name in DeploymentDraft.model_fields)


def test_draft_tolerates_loose_resume_payloads() -> None:
    draft = DeploymentDraft(
        stack_name="None",  # wizard footgun: stringified None
        unknown_key="ignored",
        budget_limit="12.50",  # pre-stringified Decimal
    )
    assert draft.stack_name is None
    assert draft.budget_limit == Decimal("12.50")
    assert not hasattr(draft, "unknown_key")


def test_draft_constraints_are_relaxed_until_validate() -> None:
    # Config-level pattern/bound constraints must not fire on assignment.
    draft = DeploymentDraft(stack_name="9starts-with-digit", rollback_timeout_minutes=99)
    assert draft.stack_name == "9starts-with-digit"
    assert draft.rollback_timeout_minutes == 99


# ----------------------------------------------------------------------
# Field matrix: build()
# ----------------------------------------------------------------------
@pytest.mark.parametrize("entry", MATRIX_IDS)
def test_matrix_entry_builds_valid_config(entry: str) -> None:
    payload = FIELD_MATRIX[entry]
    builder = ConfigBuilder(DeploymentDraft(**payload))
    assert builder.validate() == {}
    config = builder.build()
    assert isinstance(config, DeploymentConfig)
    for field, value in payload.items():
        if field in DRAFT_ONLY_FIELDS:
            continue
        expected = Decimal(value) if field == "budget_limit" else value
        assert getattr(config, field) == expected, field


def test_build_applies_model_defaults_not_hardcoded_literals() -> None:
    config = ConfigBuilder(DeploymentDraft(stack_name="defaults", tier="dev")).build()
    for name, info in DeploymentConfig.model_fields.items():
        if name in {"stack_name", "tier"}:
            continue
        assert getattr(config, name) == info.get_default(call_default_factory=True), name


def test_build_does_not_apply_tier_normalization() -> None:
    # enable_alb/enable_cdn derivation belongs to DeploymentRunner post-build.
    config = ConfigBuilder(
        DeploymentDraft(
            stack_name="tier2",
            tier="automation",
            alb_domain_name="n8n.example.com",
            alb_hosted_zone_id="Z123",
        )
    ).build()
    assert config.enable_alb is False
    assert config.enable_cdn is False
    assert config.rollback_timeout_minutes == 15


def test_build_excludes_preview_metadata_and_draft_only_fields() -> None:
    builder = ConfigBuilder(
        DeploymentDraft(
            stack_name="preview",
            tier="dev",
            setup_mode="quick",
            create_mount_target=True,
            cost_monthly_estimate=12.34,
            instance_selection_reason="because",
            instance_selection_fallback=True,
            instance_alternatives=[{"instance_type": "t3.large"}],
        )
    )
    config = builder.build()
    dumped = config.model_dump()
    for field in DRAFT_ONLY_FIELDS:
        assert field not in dumped


# ----------------------------------------------------------------------
# apply_defaults / quick presets
# ----------------------------------------------------------------------
def test_apply_defaults_quick_mode_presets() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="quick", tier="dev", setup_mode="quick"))
    builder.apply_defaults()
    draft = builder.draft
    assert draft.os_type == "ubuntu-22.04"
    assert draft.architecture == "x86_64"
    assert draft.ami_type == "base"
    assert draft.ami_id is None
    assert draft.instance_preference == "balanced"
    assert draft.use_spot is True
    for field in ("vpc_id", "subnet_id", "security_group_id", "efs_id", "keypair_name", "storage_subnet_id"):
        assert getattr(draft, field) is None, field


def test_apply_defaults_never_overwrites_user_values() -> None:
    builder = ConfigBuilder(
        DeploymentDraft(
            stack_name="keep",
            tier="dev",
            setup_mode="quick",
            os_type="amazon-linux-2023",
            use_spot=False,
            instance_type="m5.large",
        )
    )
    builder.apply_defaults()
    assert builder.draft.os_type == "amazon-linux-2023"
    assert builder.draft.use_spot is False
    assert builder.draft.instance_type == "m5.large"


def test_apply_defaults_leaves_required_fields_unset() -> None:
    builder = ConfigBuilder().apply_defaults()
    assert builder.draft.stack_name is None
    assert builder.draft.tier is None
    assert builder.draft.instance_type == "t3.medium"
    assert builder.draft.region == "us-east-1"


# ----------------------------------------------------------------------
# set / update
# ----------------------------------------------------------------------
def test_set_and_update_chain_and_coerce() -> None:
    builder = ConfigBuilder()
    result = builder.set("stack_name", "chained").update(tier="dev", budget_limit="9.99")
    assert result is builder
    assert builder.draft.stack_name == "chained"
    assert builder.draft.budget_limit == Decimal("9.99")


def test_set_unknown_field_raises() -> None:
    with pytest.raises(ValueError, match="Unknown draft field"):
        ConfigBuilder().set("not_a_field", 1)
    with pytest.raises(ValueError, match="Unknown draft field"):
        ConfigBuilder().update(not_a_field=1)


# ----------------------------------------------------------------------
# visible_fields / is_visible
# ----------------------------------------------------------------------
def test_quick_mode_hides_advanced_fields() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="q", tier="dev", setup_mode="quick"))
    hidden = {
        "instance_preference",
        "use_spot",
        "os_type",
        "architecture",
        "ami_type",
        "ami_id",
        "vpc_id",
        "subnet_id",
        "public_subnet_ids",
        "private_subnet_ids",
        "storage_subnet_id",
        "security_group_id",
        "efs_id",
        "keypair_name",
        "attach_internet_gateway",
        "create_mount_target",
    }
    visible = set(builder.visible_fields())
    assert hidden.isdisjoint(visible)
    assert {"stack_name", "tier", "region", "instance_type", "enable_https"} <= visible


def test_advanced_mode_shows_networking_and_ami_fields() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="a", tier="dev", setup_mode="advanced"))
    visible = set(builder.visible_fields())
    assert {"vpc_id", "subnet_id", "security_group_id", "efs_id", "keypair_name"} <= visible
    assert {"os_type", "architecture", "ami_type", "ami_id", "use_spot", "instance_preference"} <= visible


def test_dev_tier_https_visibility() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="d", tier="dev", enable_https=True))
    assert builder.is_visible("tier1_use_self_signed")
    assert not builder.is_visible("alb_domain_name")
    assert not builder.is_visible("alb_hosted_zone_id")
    assert not builder.is_visible("alb_certificate_arn")
    assert not builder.is_visible("cloudfront_certificate_arn")


def test_automation_tier_https_visibility() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="t2", tier="automation", enable_https=True))
    assert builder.is_visible("alb_domain_name")
    assert builder.is_visible("alb_hosted_zone_id")
    assert builder.is_visible("alb_certificate_arn")
    assert not builder.is_visible("tier1_use_self_signed")
    assert not builder.is_visible("cloudfront_certificate_arn")


def test_gpu_tier_shows_cloudfront_certificate() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="t3", tier="gpu", enable_https=True))
    assert builder.is_visible("cloudfront_certificate_arn")
    assert builder.is_visible("alb_domain_name")


def test_https_disabled_hides_all_cert_fields() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="nossl", tier="automation", enable_https=False))
    for field in (
        "tier1_use_self_signed",
        "alb_domain_name",
        "alb_hosted_zone_id",
        "alb_certificate_arn",
        "cloudfront_certificate_arn",
        "force_https_redirect",
    ):
        assert not builder.is_visible(field), field
    assert builder.is_visible("enable_https")


def test_unset_enable_https_falls_back_to_config_default() -> None:
    # enable_https defaults to True, so HTTPS detail fields show for the tier.
    builder = ConfigBuilder(DeploymentDraft(stack_name="x", tier="automation"))
    assert builder.is_visible("alb_domain_name")


def test_preview_fields_never_visible_and_unknown_raises() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="p", tier="dev"))
    for field in PREVIEW_FIELDS:
        assert not builder.is_visible(field)
    with pytest.raises(ValueError, match="Unknown draft field"):
        builder.is_visible("nope")


# ----------------------------------------------------------------------
# validate()
# ----------------------------------------------------------------------
def test_validate_valid_draft_returns_empty_dict() -> None:
    for payload in FIELD_MATRIX.values():
        assert ConfigBuilder(DeploymentDraft(**payload)).validate() == {}


def test_validate_reports_bad_stack_name_pattern() -> None:
    errors = ConfigBuilder(DeploymentDraft(stack_name="9bad-start", tier="dev")).validate()
    assert "stack_name" in errors
    assert any("pattern" in message for message in errors["stack_name"])


def test_validate_reports_rollback_timeout_bounds() -> None:
    errors = ConfigBuilder(DeploymentDraft(stack_name="ok", tier="dev", rollback_timeout_minutes=99)).validate()
    assert "rollback_timeout_minutes" in errors
    errors_low = ConfigBuilder(DeploymentDraft(stack_name="ok", tier="dev", rollback_timeout_minutes=1)).validate()
    assert "rollback_timeout_minutes" in errors_low


def test_validate_tier2_https_requires_domain_or_certificate() -> None:
    errors = ConfigBuilder(DeploymentDraft(stack_name="t2", tier="automation", enable_https=True)).validate()
    assert "alb_domain_name" in errors
    assert "alb_hosted_zone_id" in errors

    # A certificate ARN satisfies the cross-field rule without DNS inputs.
    with_cert = ConfigBuilder(
        DeploymentDraft(
            stack_name="t2",
            tier="automation",
            enable_https=True,
            alb_certificate_arn="arn:aws:acm:us-east-1:123456789012:certificate/x",
        )
    ).validate()
    assert with_cert == {}

    # Disabling HTTPS also clears the requirement.
    no_https = ConfigBuilder(DeploymentDraft(stack_name="t2", tier="automation", enable_https=False)).validate()
    assert no_https == {}


def test_validate_missing_required_fields() -> None:
    errors = ConfigBuilder().validate()
    assert "stack_name" in errors
    assert "tier" in errors


def test_validate_does_not_mutate_draft() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="pure", tier="dev"))
    builder.validate()
    assert builder.draft.instance_type is None
    assert builder.draft.region is None


# ----------------------------------------------------------------------
# from_initial_state
# ----------------------------------------------------------------------
def test_from_initial_state_normalizes_none_string_stack_name() -> None:
    builder = ConfigBuilder.from_initial_state({"stack_name": "None", "tier": "dev"})
    assert builder.draft.stack_name is None


def test_from_initial_state_ignores_unknown_keys() -> None:
    builder = ConfigBuilder.from_initial_state(
        {"stack_name": "demo", "tier": "dev", "totally_unknown": object(), "another": [1, 2]}
    )
    assert builder.draft.stack_name == "demo"


def test_from_initial_state_maps_underscore_metadata_keys() -> None:
    builder = ConfigBuilder.from_initial_state(
        {
            "stack_name": "demo",
            "_instance_selection_reason": "balanced policy",
            "_instance_selection_fallback": True,
            "_instance_alternatives": [{"instance_type": "t3.large", "is_spot": True}],
            "cost_monthly_estimate": 7.30,
        }
    )
    assert builder.draft.instance_selection_reason == "balanced policy"
    assert builder.draft.instance_selection_fallback is True
    assert builder.draft.instance_alternatives == [{"instance_type": "t3.large", "is_spot": True}]
    assert builder.draft.cost_monthly_estimate == 7.30


def test_from_initial_state_maps_legacy_compute_type_to_workload() -> None:
    builder = ConfigBuilder.from_initial_state({"stack_name": "demo", "compute_type": "gpu"})
    assert builder.draft.workload == "gpu"

    # An explicit non-None workload wins over the legacy alias.
    explicit = ConfigBuilder.from_initial_state({"stack_name": "demo", "compute_type": "gpu", "workload": "cpu"})
    assert explicit.draft.workload == "cpu"

    # A None workload does not clobber the legacy alias.
    none_direct = ConfigBuilder.from_initial_state({"stack_name": "demo", "workload": None, "compute_type": "gpu"})
    assert none_direct.draft.workload == "gpu"


def test_from_initial_state_captures_wizard_session_fields() -> None:
    builder = ConfigBuilder.from_initial_state(
        {"stack_name": "demo", "setup_mode": "quick", "create_mount_target": True}
    )
    assert builder.draft.setup_mode == "quick"
    assert builder.draft.create_mount_target is True
