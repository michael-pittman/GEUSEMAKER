from __future__ import annotations

import json

from click.testing import CliRunner

from geusemaker.cli.main import cli
from geusemaker.models.validation import ValidationCheck, ValidationReport


class PassingValidator:
    def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: D401
        pass

    def validate(self, config):  # type: ignore[no-untyped-def]
        return ValidationReport(
            checks=[
                ValidationCheck(
                    check_name="credentials",
                    passed=True,
                    message="ok",
                    severity="info",
                ),
            ],
        )


class FailingValidator(PassingValidator):
    def validate(self, config):  # type: ignore[no-untyped-def]
        return ValidationReport(
            checks=[
                ValidationCheck(
                    check_name="credentials",
                    passed=False,
                    message="bad",
                    severity="error",
                ),
            ],
        )


class DummyOrchestrator:
    last_config = None
    last_selection = None

    def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: D401
        pass

    def deploy(self, config, enable_rollback: bool = True):  # type: ignore[no-untyped-def] # noqa: ARG002
        DummyOrchestrator.last_config = config
        # The runner pre-selects compute and stamps it onto the orchestrator.
        DummyOrchestrator.last_selection = getattr(self, "_preselected_selection", None)
        return type(
            "State",
            (),
            {
                "stack_name": config.stack_name,
                "status": "creating",
                "config": config,
                "instance_id": "",  # Empty instance_id to skip log display
            },
        )()


def test_deploy_shows_validation_report_and_succeeds(monkeypatch):
    monkeypatch.setattr("geusemaker.cli.interactive.runner.PreDeploymentValidator", PassingValidator)
    monkeypatch.setattr("geusemaker.cli.interactive.runner.Tier1Orchestrator", DummyOrchestrator)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--stack-name",
            "demo",
            "--tier",
            "dev",
            "--region",
            "us-east-1",
            "--storage-subnet-id",
            "subnet-1",
        ],
    )

    assert result.exit_code == 0
    assert "PASS" in result.output
    assert "Deployment created" in result.output


def test_deploy_shows_validation_report_and_fails(monkeypatch):
    monkeypatch.setattr("geusemaker.cli.interactive.runner.PreDeploymentValidator", FailingValidator)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deploy", "--stack-name", "demo", "--tier", "dev", "--region", "us-east-1"],
    )

    assert result.exit_code == 2
    assert "FAIL" in result.output


def test_deploy_json_output_is_single_clean_document(monkeypatch):
    """--output json must emit exactly one parseable document on stdout (diagnostics on stderr)."""
    monkeypatch.setattr("geusemaker.cli.interactive.runner.PreDeploymentValidator", PassingValidator)
    monkeypatch.setattr("geusemaker.cli.interactive.runner.Tier1Orchestrator", DummyOrchestrator)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--stack-name",
            "demo",
            "--tier",
            "dev",
            "--region",
            "us-east-1",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    # The ENTIRE stdout must be one JSON document — no banner, no progress noise.
    # (result.output is the combined stream; result.stdout is stdout alone.)
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["data"]["stack_name"] == "demo"


def test_deploy_json_output_rejects_interactive(monkeypatch):  # noqa: ARG001
    """Interactive mode cannot produce a structured document; fail fast with a parseable error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["deploy", "--output", "json"])

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["error_code"] == "usage"


def test_deploy_no_spot_flag_selects_on_demand(monkeypatch):
    """--no-spot must flow through the runner into config and the preselected compute choice."""
    DummyOrchestrator.last_config = None
    DummyOrchestrator.last_selection = None
    monkeypatch.setattr("geusemaker.cli.interactive.runner.PreDeploymentValidator", PassingValidator)
    monkeypatch.setattr("geusemaker.cli.interactive.runner.Tier1Orchestrator", DummyOrchestrator)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--stack-name",
            "demo",
            "--tier",
            "dev",
            "--region",
            "us-east-1",
            "--no-spot",
        ],
    )

    assert result.exit_code == 0
    assert DummyOrchestrator.last_config is not None
    assert DummyOrchestrator.last_config.use_spot is False
    assert DummyOrchestrator.last_selection is not None
    assert DummyOrchestrator.last_selection.is_spot is False
    assert DummyOrchestrator.last_selection.selection_reason == "User requested on-demand"


def test_deploy_accepts_ami_configuration(monkeypatch):
    DummyOrchestrator.last_config = None
    monkeypatch.setattr("geusemaker.cli.interactive.runner.PreDeploymentValidator", PassingValidator)
    monkeypatch.setattr("geusemaker.cli.interactive.runner.Tier1Orchestrator", DummyOrchestrator)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "deploy",
            "--stack-name",
            "demo",
            "--tier",
            "dev",
            "--region",
            "us-east-1",
            "--os-type",
            "ubuntu-24.04",
            "--architecture",
            "arm64",
            "--ami-type",
            "pytorch",
        ],
    )

    assert result.exit_code == 0
    assert DummyOrchestrator.last_config is not None
    assert DummyOrchestrator.last_config.os_type == "ubuntu-24.04"
    assert DummyOrchestrator.last_config.architecture == "arm64"
    assert DummyOrchestrator.last_config.ami_type == "pytorch"
