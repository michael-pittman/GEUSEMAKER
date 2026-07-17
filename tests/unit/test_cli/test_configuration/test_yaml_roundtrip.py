"""YAML import/export tests for ConfigBuilder.

The export must stay byte-compatible with the wizard's exporter
(`integration._export_config`) so `ConfigLoader.load()` accepts it unchanged.
No AWS, network, or boto3 usage anywhere in this module.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from geusemaker.cli.configuration import ConfigBuilder, DeploymentDraft
from geusemaker.config import ConfigLoader, ConfigurationError
from tests.unit.test_cli.test_configuration.matrix import FIELD_MATRIX, MATRIX_IDS


@pytest.mark.parametrize("entry", MATRIX_IDS)
def test_yaml_round_trip_produces_identical_config(entry: str) -> None:
    builder = ConfigBuilder(DeploymentDraft(**FIELD_MATRIX[entry]))
    text = builder.to_yaml()
    assert ConfigBuilder.from_yaml(text).build() == builder.build()


@pytest.mark.parametrize("entry", MATRIX_IDS)
def test_to_yaml_output_loads_via_config_loader(entry: str, tmp_path: Path) -> None:
    builder = ConfigBuilder(DeploymentDraft(**FIELD_MATRIX[entry]))
    target = tmp_path / f"{entry}.yaml"
    target.write_text(builder.to_yaml())
    loaded = ConfigLoader(env={}).load(target)
    assert loaded == builder.build()


@pytest.mark.parametrize("entry", MATRIX_IDS)
def test_to_yaml_matches_wizard_export_shape(entry: str) -> None:
    # integration._export_config writes model_dump(mode="json", exclude_none=True)
    # with sort_keys=False; to_yaml must stay byte-compatible with that shape.
    builder = ConfigBuilder(DeploymentDraft(**FIELD_MATRIX[entry]))
    config = builder.build()
    expected = yaml.safe_dump(config.model_dump(mode="json", exclude_none=True), sort_keys=False)
    assert builder.to_yaml() == expected


def test_to_yaml_excludes_none_values() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="minimal", tier="dev"))
    data = yaml.safe_load(builder.to_yaml())
    assert None not in data.values()
    for absent in ("vpc_id", "ami_id", "budget_limit", "alb_domain_name", "keypair_name"):
        assert absent not in data, absent
    assert data["stack_name"] == "minimal"
    assert data["instance_type"] == "t3.medium"


def test_from_yaml_accepts_path_objects(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("stack_name: from-file\ntier: dev\n")
    builder = ConfigBuilder.from_yaml(target)
    assert builder.build().stack_name == "from-file"


def test_from_yaml_accepts_existing_path_strings(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    target.write_text("stack_name: from-string-path\ntier: dev\n")
    builder = ConfigBuilder.from_yaml(str(target))
    assert builder.build().stack_name == "from-string-path"


def test_from_yaml_malformed_yaml_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        ConfigBuilder.from_yaml("stack_name: [unclosed\n")


def test_from_yaml_non_dict_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        ConfigBuilder.from_yaml("- a\n- list\n")
    with pytest.raises(ConfigurationError):
        ConfigBuilder.from_yaml("just a scalar")


def test_from_yaml_malformed_file_raises_configuration_error(tmp_path: Path) -> None:
    target = tmp_path / "broken.yaml"
    target.write_text("stack_name: [unclosed\n")
    with pytest.raises(ConfigurationError):
        ConfigBuilder.from_yaml(target)


def test_from_yaml_non_dict_file_raises_configuration_error(tmp_path: Path) -> None:
    target = tmp_path / "list.yaml"
    target.write_text("- a\n- list\n")
    with pytest.raises(ConfigurationError):
        ConfigBuilder.from_yaml(target)


def test_from_yaml_ignores_unknown_keys() -> None:
    builder = ConfigBuilder.from_yaml("stack_name: demo\ntier: dev\nnot_a_config_key: true\n")
    assert builder.build().stack_name == "demo"


def test_yaml_round_trip_preserves_decimal_budget() -> None:
    builder = ConfigBuilder(DeploymentDraft(stack_name="budget", tier="dev", budget_limit="42.42"))
    rebuilt = ConfigBuilder.from_yaml(builder.to_yaml()).build()
    assert rebuilt.budget_limit == builder.build().budget_limit
