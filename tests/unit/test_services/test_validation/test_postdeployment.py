from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from geusemaker.models import CostTracking, DeploymentConfig, DeploymentState
from geusemaker.services.validation.postdeployment import PostDeploymentValidator


class FakeEC2:
    def __init__(self, system_ok: bool = True, instance_ok: bool = True) -> None:
        self.system_ok = system_ok
        self.instance_ok = instance_ok

    def describe_instance_status(self, **_: object) -> dict:
        return {
            "InstanceStatuses": [
                {
                    "SystemStatus": {"Status": "ok" if self.system_ok else "impaired"},
                    "InstanceStatus": {"Status": "ok" if self.instance_ok else "impaired"},
                },
            ],
        }


class FakeHealth:
    def __init__(self, healthy: bool = True) -> None:
        self.healthy = healthy

    async def check_all(self, configs):  # noqa: ANN001
        return [
            SimpleNamespace(
                service_name="n8n",
                healthy=self.healthy,
                status_code=200 if self.healthy else 500,
                response_time_ms=10.0,
                error_message=None if self.healthy else "boom",
                endpoint=configs[0].endpoint if configs else "",
                retry_count=0,
            ),
        ]

    async def check_tcp(self, **kwargs: object):  # noqa: ANN001
        return SimpleNamespace(
            service_name="postgres",
            healthy=self.healthy,
            status_code=None,
            response_time_ms=5.0,
            error_message=None if self.healthy else "refused",
            endpoint="localhost:5432",
            retry_count=0,
        )


class FakeHealthClient(FakeHealth):
    async def check_http(self, **kwargs: object):  # noqa: ANN001
        return await super().check_all([])[0]  # type: ignore[index]


def _state(public_ip: str = "1.2.3.4") -> DeploymentState:
    cost = CostTracking(
        instance_type="t3.medium",
        is_spot=True,
        on_demand_price_per_hour=Decimal("0.04"),
        estimated_monthly_cost=Decimal("25"),
    )
    return DeploymentState(
        stack_name="demo",
        status="running",
        vpc_id="vpc-1",
        subnet_ids=["subnet-1"],
        security_group_id="sg-1",
        efs_id="efs-1",
        efs_mount_target_id="mt-1",
        instance_id="i-1",
        keypair_name="kp-1",
        public_ip=public_ip,
        private_ip="10.0.0.1",
        n8n_url="http://example.com",
        cost=cost,
        config=DeploymentConfig(stack_name="demo", tier="dev", region="us-east-1"),
    )


@pytest.mark.asyncio
async def test_postdeployment_validation_success(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state()

    async def fake_check_all(client, host: str):  # noqa: ANN001
        return [
            SimpleNamespace(
                service_name="n8n",
                healthy=True,
                status_code=200,
                response_time_ms=10.0,
                error_message=None,
                endpoint=f"http://{host}:5678/healthz",
                retry_count=0,
            ),
        ]

    monkeypatch.setattr("geusemaker.services.validation.postdeployment.check_all_services", fake_check_all)
    monkeypatch.setattr(
        "geusemaker.services.validation.postdeployment.check_postgres",
        lambda client, host, port=5432: asyncio.Future(),
    )
    fut = asyncio.Future()
    fut.set_result(
        SimpleNamespace(
            service_name="postgres",
            healthy=True,
            status_code=None,
            response_time_ms=5.0,
            error_message=None,
            endpoint="localhost:5432",
            retry_count=0,
        ),
    )
    monkeypatch.setattr(
        "geusemaker.services.validation.postdeployment.check_postgres",
        lambda client, host, port=5432: fut,
    )

    validator = PostDeploymentValidator(
        client_factory=None,  # type: ignore[arg-type]
        region="us-east-1",
        health_client=FakeHealthClient(),
        ec2_client=FakeEC2(),
    )
    report = await validator.validate(state)

    assert report.passed is True
    assert report.errors == 0
    assert any(check.check_name.startswith("service_") for check in report.checks)


@pytest.mark.asyncio
async def test_postdeployment_validation_ec2_failure() -> None:
    state = _state()
    validator = PostDeploymentValidator(
        client_factory=None,  # type: ignore[arg-type]
        region="us-east-1",
        health_client=FakeHealthClient(),
        ec2_client=FakeEC2(system_ok=False),
    )
    report = await validator.validate(state)

    assert report.passed is False
    assert report.errors > 0


@pytest.mark.asyncio
async def test_postdeployment_validation_efs_failure() -> None:
    state = _state()
    validator = PostDeploymentValidator(
        client_factory=None,  # type: ignore[arg-type]
        region="us-east-1",
        health_client=FakeHealthClient(),
        ec2_client=FakeEC2(),
        efs_mount_checker=lambda _: False,
    )
    report = await validator.validate(state)

    efs_check = next(check for check in report.checks if check.check_name == "efs_mount")
    assert efs_check.passed is False
    assert report.passed is False


@pytest.mark.asyncio
async def test_postdeployment_validation_service_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state()

    async def fake_check_all(client, host: str):  # noqa: ANN001
        return [
            SimpleNamespace(
                service_name="n8n",
                healthy=False,
                status_code=500,
                response_time_ms=10.0,
                error_message="boom",
                endpoint=f"http://{host}:5678/healthz",
                retry_count=0,
            ),
        ]

    monkeypatch.setattr("geusemaker.services.validation.postdeployment.check_all_services", fake_check_all)
    fut = asyncio.Future()
    fut.set_result(
        SimpleNamespace(
            service_name="postgres",
            healthy=True,
            status_code=None,
            response_time_ms=5.0,
            error_message=None,
            endpoint="localhost:5432",
            retry_count=0,
        ),
    )
    monkeypatch.setattr(
        "geusemaker.services.validation.postdeployment.check_postgres",
        lambda client, host, port=5432: fut,
    )

    validator = PostDeploymentValidator(
        client_factory=None,  # type: ignore[arg-type]
        region="us-east-1",
        health_client=FakeHealthClient(),
        ec2_client=FakeEC2(),
    )
    report = await validator.validate(state)

    assert report.passed is False
    assert any(check.check_name == "service_n8n" and not check.passed for check in report.checks)
