"""Tests for the ACM/Route53 certificate provisioner."""

from __future__ import annotations

import pytest

from geusemaker.models import DeploymentConfig
from geusemaker.orchestration.certificates import CertificateProvisioner, certificate_required
from geusemaker.progress import ProgressEvent


class StubACM:
    """Records the ACM call sequence and returns canned validation data."""

    def __init__(self, *, raise_on_issued: bool = False) -> None:
        self.calls: list[str] = []
        self.request_tags: list[dict[str, str]] | None = None
        self.issued_timeout: int | None = None
        self._raise_on_issued = raise_on_issued

    def request_dns_certificate(self, domain_name, tags=None):  # type: ignore[no-untyped-def]  # noqa: ANN001
        self.calls.append("request")
        self.domain_name = domain_name
        self.request_tags = tags
        return "arn:aws:acm:us-east-1:123:certificate/abc"

    def wait_for_dns_validation_record(self, cert_arn, timeout_seconds, poll_interval_seconds):  # type: ignore[no-untyped-def]  # noqa: ANN001
        self.calls.append("dns_record")
        self.dns_timeout = timeout_seconds
        return ("_x.example.com.", "CNAME", "_y.acm-validations.aws.")

    def wait_for_issued(self, cert_arn, timeout_seconds):  # type: ignore[no-untyped-def]  # noqa: ANN001
        self.calls.append("issued")
        self.issued_timeout = timeout_seconds
        if self._raise_on_issued:
            raise RuntimeError("Timed out waiting for certificate to be issued")


class StubRoute53:
    def __init__(self, *, change_id: str = "C123") -> None:
        self.calls: list[str] = []
        self._change_id = change_id
        self.upsert_kwargs: dict[str, object] | None = None

    def upsert_record(self, hosted_zone_id, name, record_type, value, ttl=60):  # type: ignore[no-untyped-def]  # noqa: ANN001
        self.calls.append("upsert")
        self.upsert_kwargs = {
            "hosted_zone_id": hosted_zone_id,
            "name": name,
            "record_type": record_type,
            "value": value,
            "ttl": ttl,
        }
        return self._change_id

    def wait_for_change(self, change_id):  # type: ignore[no-untyped-def]  # noqa: ANN001
        self.calls.append("wait_change")


def _config() -> DeploymentConfig:
    return DeploymentConfig(
        stack_name="stack",
        tier="automation",
        enable_alb=True,
        enable_https=True,
        alb_domain_name="n8n.example.com",
        alb_hosted_zone_id="Z123",
        use_spot=False,
    )


def _provisioner(acm: StubACM, r53: StubRoute53) -> CertificateProvisioner:
    from geusemaker.infra import AWSClientFactory

    return CertificateProvisioner(
        AWSClientFactory(),
        region="us-east-1",
        acm_service=acm,  # type: ignore[arg-type]
        route53_service=r53,  # type: ignore[arg-type]
    )


def test_certificate_required_gating() -> None:
    assert certificate_required(_config()) is True
    # No domain -> not required.
    assert certificate_required(_config().model_copy(update={"alb_domain_name": None})) is False
    # No hosted zone -> not required.
    assert certificate_required(_config().model_copy(update={"alb_hosted_zone_id": None})) is False
    # Cert already supplied -> not required.
    assert certificate_required(_config().model_copy(update={"alb_certificate_arn": "arn:x"})) is False
    # HTTPS disabled -> not required.
    assert certificate_required(_config().model_copy(update={"enable_https": False})) is False


def test_provision_happy_path_returns_arn_and_emits_events() -> None:
    acm = StubACM()
    r53 = StubRoute53()
    events: list[ProgressEvent] = []

    cert_arn = _provisioner(acm, r53).provision(_config(), on_progress=events.append)

    assert cert_arn == "arn:aws:acm:us-east-1:123:certificate/abc"
    # Exact AWS call sequence preserved.
    assert acm.calls == ["request", "dns_record", "issued"]
    assert r53.calls == ["upsert", "wait_change"]
    # Timeouts preserved.
    assert acm.dns_timeout == 300
    assert acm.issued_timeout == 900
    # Route 53 UPSERT uses the DNS validation record with TTL 60.
    assert r53.upsert_kwargs == {
        "hosted_zone_id": "Z123",
        "name": "_x.example.com.",
        "record_type": "CNAME",
        "value": "_y.acm-validations.aws.",
        "ttl": 60,
    }
    # Tags include Stack + managed-by markers.
    tag_keys = {t["Key"] for t in acm.request_tags or []}
    assert {"Name", "Stack", "Tier", "ManagedBy"} == tag_keys
    # Progress events are all on the alb stage; issuance carries the arn.
    assert [e.stage for e in events] == ["alb", "alb", "alb", "alb"]
    assert events[-1].resource_id == cert_arn


def test_provision_skips_wait_when_no_change_id() -> None:
    acm = StubACM()
    r53 = StubRoute53(change_id="")

    _provisioner(acm, r53).provision(_config())

    assert r53.calls == ["upsert"]  # wait_for_change skipped


def test_provision_propagates_issuance_timeout() -> None:
    acm = StubACM(raise_on_issued=True)
    r53 = StubRoute53()

    with pytest.raises(RuntimeError, match="Timed out"):
        _provisioner(acm, r53).provision(_config())


def test_provision_requires_domain_and_zone() -> None:
    acm = StubACM()
    r53 = StubRoute53()
    bad = _config().model_copy(update={"alb_hosted_zone_id": None})

    with pytest.raises(ValueError, match="alb_domain_name and alb_hosted_zone_id"):
        _provisioner(acm, r53).provision(bad)
