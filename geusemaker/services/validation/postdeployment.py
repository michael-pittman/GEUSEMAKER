"""Post-deployment validation service."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
)

from geusemaker.infra import AWSClientFactory
from geusemaker.models import (
    DeploymentState,
    HealthCheckResult,
    ValidationCheck,
    ValidationReport,
)
from geusemaker.services.health import (
    HealthCheckClient,
    check_all_services,
    check_postgres,
)
from geusemaker.services.validation.remediation import remediation_for

LOGGER = logging.getLogger(__name__)


class PostDeploymentValidator:
    """Validate deployment health after provisioning."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        health_client: HealthCheckClient | None = None,
        ec2_client: object | None = None,
        efs_mount_checker: Callable[[DeploymentState], bool] | None = None,
    ):
        self._client_factory = client_factory
        self.region = region
        self._health = health_client or HealthCheckClient()
        self._ec2 = ec2_client or self._client_factory.get_client("ec2", region=region)
        self._efs_mount_checker = efs_mount_checker or (lambda _: True)

    async def validate(self, deployment: DeploymentState) -> ValidationReport:
        """Run post-deployment validation and return a report."""
        start = time.perf_counter()
        report = ValidationReport(
            deployment_name=deployment.stack_name,
            deployment_tier=deployment.config.tier,
        )

        instance_check = await self._check_instance_status(deployment.instance_id)
        report.add(instance_check)
        if not instance_check.passed:
            return self._finalize(report, start)

        efs_check = await self._check_efs_mount(deployment)
        report.add(efs_check)
        if not efs_check.passed:
            return self._finalize(report, start)

        service_checks = await self._check_services(deployment)
        for check in service_checks:
            report.add(check)

        return self._finalize(report, start)

    async def _check_instance_status(self, instance_id: str) -> ValidationCheck:
        """Validate EC2 instance/system status checks."""
        try:
            response = self._ec2.describe_instance_status(  # type: ignore[attr-defined]
                InstanceIds=[instance_id],
                IncludeAllInstances=True,
            )
        except (ClientError, BotoCoreError) as exc:
            return ValidationCheck(
                check_name="instance_status",
                passed=False,
                message=f"Unable to fetch instance status: {exc}",
                remediation=remediation_for("ec2_status"),
            )

        statuses = response.get("InstanceStatuses", [])
        if not statuses:
            return ValidationCheck(
                check_name="instance_status",
                passed=False,
                message="Instance status not available.",
                remediation=remediation_for("ec2_status"),
            )

        status = statuses[0]
        system_ok = status.get("SystemStatus", {}).get("Status") == "ok"
        instance_ok = status.get("InstanceStatus", {}).get("Status") == "ok"
        if system_ok and instance_ok:
            return ValidationCheck(
                check_name="instance_status",
                passed=True,
                message="Instance and system checks passed.",
                severity="info",
            )
        failed = []
        if not system_ok:
            failed.append("system")
        if not instance_ok:
            failed.append("instance")
        return ValidationCheck(
            check_name="instance_status",
            passed=False,
            message=f"Instance checks failed: {', '.join(failed)}",
            remediation=remediation_for("ec2_status"),
        )

    async def _check_efs_mount(self, deployment: DeploymentState) -> ValidationCheck:
        """Validate EFS mount using injected checker."""
        try:
            mounted = await asyncio.to_thread(self._efs_mount_checker, deployment)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("EFS mount check raised: %s", exc)
            return ValidationCheck(
                check_name="efs_mount",
                passed=False,
                message=f"EFS mount validation failed: {exc}",
                remediation=remediation_for("efs_mount"),
            )

        if mounted:
            return ValidationCheck(
                check_name="efs_mount",
                passed=True,
                message="EFS mount verified.",
                severity="info",
            )
        return ValidationCheck(
            check_name="efs_mount",
            passed=False,
            message="EFS not mounted or mismatched.",
            remediation=remediation_for("efs_mount"),
        )

    async def _check_services(self, deployment: DeploymentState) -> list[ValidationCheck]:
        """Run service health checks in parallel."""
        host = deployment.public_ip or deployment.private_ip
        if not host:
            return [
                ValidationCheck(
                    check_name="service_health",
                    passed=False,
                    message="No host/IP available for health checks.",
                    remediation="Ensure instance has reachable IP and retry.",
                ),
            ]

        results: list[HealthCheckResult] = await check_all_services(self._health, host=host)
        # Add Postgres check separately via TCP
        pg_result = await check_postgres(self._health, host=host, port=5432)
        results.append(pg_result)

        checks: list[ValidationCheck] = []
        for result in results:
            checks.append(
                ValidationCheck(
                    check_name=f"service_{result.service_name}",
                    passed=result.healthy,
                    message=_result_message(result),
                    details=result.error_message,
                    remediation=remediation_for(result.service_name) if not result.healthy else None,
                    severity="info" if result.healthy else "error",
                ),
            )
        return checks

    def _finalize(self, report: ValidationReport, start: float) -> ValidationReport:
        report.validation_duration_seconds = time.perf_counter() - start
        return report


def _result_message(result: HealthCheckResult) -> str:
    if result.healthy:
        return f"{result.service_name} healthy ({result.response_time_ms:.1f} ms)"
    if result.status_code:
        return f"{result.service_name} unhealthy (status {result.status_code})"
    return f"{result.service_name} unhealthy ({result.error_message})"


__all__ = ["PostDeploymentValidator"]
