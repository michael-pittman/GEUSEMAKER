from __future__ import annotations

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

    def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: D401
        pass

    def deploy(self, config, enable_rollback: bool = True):  # type: ignore[no-untyped-def] # noqa: ARG002
        DummyOrchestrator.last_config = config
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
