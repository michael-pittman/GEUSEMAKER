from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from geusemaker.cli.main import cli
from geusemaker.models.validation import ValidationCheck, ValidationReport


class DummyReportGenerator:
    def __init__(self, *args: object, **kwargs: object) -> None:  # noqa: D401
        pass

    def __call__(self, *args: object, **kwargs: object) -> ValidationReport:  # noqa: D401
        return ValidationReport(
            deployment_name="demo",
            deployment_tier="dev",
            checks=[
                ValidationCheck(check_name="ok", passed=True, message="ok", severity="info"),
            ],
        )


def test_report_command_json(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    # Monkeypatch internal generator
    monkeypatch.setattr(
        "geusemaker.cli.commands.report._generate_report",
        DummyReportGenerator(),
    )
    result = runner.invoke(
        cli,
        ["report", "--stack-name", "demo", "--output", "json"],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert data["data"]["deployment_name"] == "demo"


def test_report_command_fails_on_failed_report(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_report(*args: object, **kwargs: object) -> ValidationReport:  # noqa: ANN001
        return ValidationReport(
            deployment_name="demo",
            deployment_tier="dev",
            checks=[
                ValidationCheck(
                    check_name="fail",
                    passed=False,
                    message="bad",
                    severity="error",
                ),
            ],
        )

    runner = CliRunner()
    monkeypatch.setattr(
        "geusemaker.cli.commands.report._generate_report",
        failing_report,
    )
    result = runner.invoke(
        cli,
        ["report", "--stack-name", "demo", "--output", "json"],
    )

    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["data"]["deployment_name"] == "demo"
