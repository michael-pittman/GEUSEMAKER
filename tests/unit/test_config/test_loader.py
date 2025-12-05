from __future__ import annotations

from pathlib import Path

import pytest

from geusemaker.config import ConfigLoader, ConfigurationError


def test_loads_yaml_and_cli_override(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "\n".join(
            [
                "stack_name: demo",
                "tier: dev",
                "region: us-east-1",
                "use_spot: false",
                "public_subnet_ids:",
                "  - subnet-1",
            ],
        ),
    )
    loader = ConfigLoader(env={})
    config = loader.load(config_file, cli_overrides={"region": "eu-west-1"})
    assert config.region == "eu-west-1"
    assert config.use_spot is False
    assert config.public_subnet_ids == ["subnet-1"]


def test_env_overrides_parsed(tmp_path: Path) -> None:
    loader = ConfigLoader(
        env={
            "GEUSEMAKER_STACK_NAME": "env-stack",
            "GEUSEMAKER_TIER": "automation",
            "GEUSEMAKER_REGION": "us-west-2",
            "GEUSEMAKER_USE_SPOT": "false",
            "GEUSEMAKER_PUBLIC_SUBNET_IDS": "subnet-a,subnet-b",
        },
    )
    config = loader.load(
        None,
        cli_overrides={"stack_name": "env-stack", "tier": "automation", "region": "us-west-2"},
    )
    assert config.stack_name == "env-stack"
    assert config.tier == "automation"
    assert config.region == "us-west-2"
    assert config.use_spot is False
    assert config.public_subnet_ids == ["subnet-a", "subnet-b"]


def test_invalid_env_bool_raises() -> None:
    loader = ConfigLoader(env={"GEUSEMAKER_USE_SPOT": "maybe"})
    with pytest.raises(ConfigurationError):
        loader.load(None, cli_overrides={"stack_name": "demo", "tier": "dev", "region": "us-east-1"})


def test_env_overrides_normalize_ami_fields() -> None:
    loader = ConfigLoader(
        env={
            "GEUSEMAKER_OS_TYPE": "UBUNTU-24.04",
            "GEUSEMAKER_ARCHITECTURE": "ARM64",
            "GEUSEMAKER_AMI_TYPE": "PYTORCH",
        },
    )
    config = loader.load(None, cli_overrides={"stack_name": "demo", "tier": "dev", "region": "us-east-1"})

    assert config.os_type == "ubuntu-24.04"
    assert config.architecture == "arm64"
    assert config.ami_type == "pytorch"
