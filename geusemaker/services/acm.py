"""ACM service for certificate lifecycle."""

from __future__ import annotations

import time
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class ACMService(BaseService):
    """Manage ACM certificates (DNS validation)."""

    def __init__(self, client_factory: AWSClientFactory, region: str):
        super().__init__(client_factory, region)
        self._acm = self._client("acm")

    def request_dns_certificate(
        self,
        domain_name: str,
        tags: list[dict[str, str]] | None = None,
    ) -> str:
        """Request a public ACM certificate validated via DNS."""

        def _call() -> str:
            kwargs: dict[str, Any] = {
                "DomainName": domain_name,
                "ValidationMethod": "DNS",
            }
            if tags:
                kwargs["Tags"] = tags
            resp = self._acm.request_certificate(**kwargs)
            return resp["CertificateArn"]  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def describe_certificate(self, certificate_arn: str) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            return self._acm.describe_certificate(CertificateArn=certificate_arn)  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def get_dns_validation_record(self, certificate_arn: str) -> tuple[str, str, str]:
        """Return (record_name, record_type, record_value) for DNS validation.

        Note: ACM may return a certificate before it has populated DomainValidationOptions
        with the required CNAME record. Prefer using wait_for_dns_validation_record() in
        orchestration flows to avoid timing/race conditions.
        """

        def _call() -> tuple[str, str, str]:
            cert = self._acm.describe_certificate(CertificateArn=certificate_arn).get("Certificate", {})
            options = cert.get("DomainValidationOptions", []) or []
            for opt in options:
                rr = opt.get("ResourceRecord")
                if rr and rr.get("Name") and rr.get("Type") and rr.get("Value"):
                    return rr["Name"], rr["Type"], rr["Value"]  # type: ignore[return-value]
            raise RuntimeError("ACM certificate did not return DNS validation records yet; retry shortly.")

        return self._safe_call(_call)

    def wait_for_dns_validation_record(
        self,
        certificate_arn: str,
        timeout_seconds: int = 300,
        poll_interval_seconds: float = 5.0,
    ) -> tuple[str, str, str]:
        """Wait until ACM populates the DNS validation record, then return it.

        ACM can briefly return a certificate with empty DomainValidationOptions right
        after request. This method polls describe_certificate until ResourceRecord is present.
        """

        deadline = time.monotonic() + timeout_seconds
        last_status: str | None = None

        while time.monotonic() < deadline:
            desc = self.describe_certificate(certificate_arn)
            cert = desc.get("Certificate", {}) or {}
            last_status = cert.get("Status") or last_status

            options = cert.get("DomainValidationOptions", []) or []
            for opt in options:
                rr = opt.get("ResourceRecord")
                if rr and rr.get("Name") and rr.get("Type") and rr.get("Value"):
                    return rr["Name"], rr["Type"], rr["Value"]

            # Terminal-ish statuses where waiting longer is not useful.
            if last_status in {"FAILED", "EXPIRED", "REVOKED"}:
                raise RuntimeError(f"ACM certificate entered status {last_status} before DNS record was available.")

            time.sleep(poll_interval_seconds)

        raise RuntimeError(
            f"Timed out after {timeout_seconds}s waiting for ACM DNS validation record. "
            f"Last known status: {last_status or 'unknown'}."
        )

    def list_tags(self, certificate_arn: str) -> list[dict[str, str]]:
        """Return the tags attached to a certificate."""

        def _call() -> list[dict[str, str]]:
            resp = self._acm.list_tags_for_certificate(CertificateArn=certificate_arn)
            return resp.get("Tags", [])  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def delete_certificate(self, certificate_arn: str) -> None:
        """Delete a certificate. Fails while the certificate is still in use (e.g. by an ALB listener)."""

        def _call() -> None:
            self._acm.delete_certificate(CertificateArn=certificate_arn)

        self._safe_call(_call)

    def wait_for_issued(self, certificate_arn: str, timeout_seconds: int = 900) -> None:
        """Wait for certificate to become validated/issued."""
        # boto3 ACM waiter polls validation status; keep it bounded.
        delay = 15
        max_attempts = max(1, timeout_seconds // delay)

        def _call() -> None:
            waiter = self._acm.get_waiter("certificate_validated")
            waiter.wait(
                CertificateArn=certificate_arn,
                WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts},
            )

        self._safe_call(_call)


__all__ = ["ACMService"]
