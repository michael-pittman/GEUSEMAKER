from __future__ import annotations

import pytest
from click.testing import CliRunner

from geusemaker.cli.main import cli
from geusemaker.models.validation import ValidationCheck, ValidationReport


class DummyValidator:
    def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: D401
        pass

    def validate(self, config: object) -> ValidationReport:  # noqa: ARG002
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


class FailingValidator(DummyValidator):
    def validate(self, config: object) -> ValidationReport:  # noqa: ARG002
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


def test_validate_command_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "geusemaker.cli.commands.validate.PreDeploymentValidator",
        DummyValidator,
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", "--stack-name", "demo"])

    assert result.exit_code == 0
    assert "PASS" in result.output


def test_validate_command_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "geusemaker.cli.commands.validate.PreDeploymentValidator",
        FailingValidator,
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["validate", "--stack-name", "demo"])

    assert result.exit_code == 1
    assert "FAIL" in result.output
