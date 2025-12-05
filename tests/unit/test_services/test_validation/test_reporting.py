from __future__ import annotations

import json

import yaml

from geusemaker.models.validation import ValidationCheck, ValidationReport
from geusemaker.services.validation.reporting import (
    build_summary,
    export_json,
    export_yaml,
)


def _report() -> ValidationReport:
    return ValidationReport(
        deployment_name="demo",
        deployment_tier="dev",
        checks=[
            ValidationCheck(check_name="ok", passed=True, message="ok", severity="info"),
            ValidationCheck(
                check_name="warn",
                passed=False,
                message="warn",
                severity="warning",
            ),
            ValidationCheck(
                check_name="fail",
                passed=False,
                message="fail",
                severity="error",
            ),
        ],
    )


def test_build_summary_counts() -> None:
    report = _report()
    summary = build_summary(report)

    assert summary.total_checks == 3
    assert summary.failed == 1
    assert summary.warnings == 1
    assert summary.overall_status == "unhealthy"


def test_export_json_and_yaml() -> None:
    report = _report()
    json_out = export_json(report)
    yaml_out = export_yaml(report)

    loaded_json = json.loads(json_out)
    loaded_yaml = yaml.safe_load(yaml_out)

    assert loaded_json["deployment_name"] == "demo"
    assert loaded_yaml["deployment_tier"] == "dev"
