from __future__ import annotations

import time

import pytest

from geusemaker.services.acm import ACMService


class StubACM:
    def __init__(self, records_after: int = 3, status: str = "PENDING_VALIDATION") -> None:
        self._calls = 0
        self._records_after = records_after
        self._status = status

    def describe_certificate(self, CertificateArn):  # type: ignore[no-untyped-def]  # noqa: N803, ANN001
        self._calls += 1
        if self._calls >= self._records_after:
            return {
                "Certificate": {
                    "Status": self._status,
                    "DomainValidationOptions": [
                        {
                            "ResourceRecord": {
                                "Name": "_abc.example.com.",
                                "Type": "CNAME",
                                "Value": "_xyz.acm-validations.aws.",
                            }
                        }
                    ],
                }
            }
        return {"Certificate": {"Status": self._status, "DomainValidationOptions": []}}


def test_wait_for_dns_validation_record_polls_until_available(monkeypatch) -> None:
    sleeps: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(time, "sleep", _fake_sleep)

    from geusemaker.infra import AWSClientFactory

    svc = ACMService(client_factory=AWSClientFactory(), region="us-east-1")
    svc._acm = StubACM(records_after=3)  # type: ignore[assignment]

    name, rtype, value = svc.wait_for_dns_validation_record(
        "arn:aws:acm:us-east-1:123:certificate/abc",
        timeout_seconds=30,
        poll_interval_seconds=0.1,
    )

    assert name == "_abc.example.com."
    assert rtype == "CNAME"
    assert value == "_xyz.acm-validations.aws."
    assert len(sleeps) >= 1


def test_wait_for_dns_validation_record_times_out(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)

    from geusemaker.infra import AWSClientFactory

    svc = ACMService(client_factory=AWSClientFactory(), region="us-east-1")
    svc._acm = StubACM(records_after=10_000)  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="Timed out"):
        svc.wait_for_dns_validation_record(
            "arn:aws:acm:us-east-1:123:certificate/abc",
            timeout_seconds=0,
            poll_interval_seconds=0.1,
        )
