"""ACM certificate provisioning via Route 53 DNS validation.

Presentation-free workflow logic extracted from the CLI deployment runner. This
module owns the multi-step ACM request + Route 53 DNS validation loop so the CLI
only builds config and renders progress. It imports no ``geusemaker.cli`` code
and reports progress through the UI-neutral :class:`ProgressCallback` contract.
"""

from __future__ import annotations

from geusemaker.infra import AWSClientFactory
from geusemaker.models import DeploymentConfig
from geusemaker.progress import ProgressCallback, ProgressEvent
from geusemaker.services.acm import ACMService
from geusemaker.services.route53 import Route53Service


def certificate_required(config: DeploymentConfig) -> bool:
    """Return True when an ALB ACM certificate must be provisioned.

    Mirrors the exact gating condition used by the CLI runner today: HTTPS is
    requested for an ALB, no certificate ARN was supplied, and a Route 53 domain
    plus hosted zone are available for DNS validation.
    """
    return bool(
        config.enable_https
        and config.enable_alb
        and not config.alb_certificate_arn
        and config.alb_domain_name
        and config.alb_hosted_zone_id
    )


class CertificateProvisioner:
    """Provision an ALB ACM certificate validated via Route 53 DNS.

    Owns the request → DNS validation record → Route 53 UPSERT → issuance flow.
    Emits :class:`ProgressEvent`s (stage ``"alb"``) through an optional callback
    and returns the issued certificate ARN. No CLI/Rich dependencies.
    """

    # Preserve the timeouts used by the CLI runner today.
    DNS_RECORD_TIMEOUT_SECONDS = 300
    DNS_RECORD_POLL_SECONDS = 5.0
    ISSUANCE_TIMEOUT_SECONDS = 900
    RECORD_TTL_SECONDS = 60

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str,
        acm_service: ACMService | None = None,
        route53_service: Route53Service | None = None,
    ):
        self.client_factory = client_factory
        self.region = region
        self.acm = acm_service or ACMService(client_factory, region=region)
        self.route53 = route53_service or Route53Service(client_factory)

    def provision(
        self,
        config: DeploymentConfig,
        on_progress: ProgressCallback | None = None,
    ) -> str:
        """Request, DNS-validate, and wait for issuance of an ALB certificate.

        Returns the issued certificate ARN. Raises ``RuntimeError`` on timeout,
        matching the underlying ACM/Route 53 service behavior.
        """
        if not config.alb_domain_name or not config.alb_hosted_zone_id:
            raise ValueError(
                "CertificateProvisioner requires alb_domain_name and alb_hosted_zone_id; "
                "call certificate_required(config) before provisioning."
            )

        def emit(message: str, resource_id: str | None = None) -> None:
            if on_progress is not None:
                on_progress(ProgressEvent("alb", message, resource_id=resource_id))

        domain_name = config.alb_domain_name
        tags = [
            {"Key": "Name", "Value": f"{config.stack_name}-alb-cert"},
            {"Key": "Stack", "Value": config.stack_name},
            {"Key": "Tier", "Value": config.tier},
            {"Key": "ManagedBy", "Value": "GeuseMaker"},
        ]

        emit(f"Requesting ACM certificate for {domain_name} (DNS validation)")
        cert_arn = self.acm.request_dns_certificate(domain_name, tags=tags)

        emit("Waiting for ACM DNS validation record")
        rr_name, rr_type, rr_value = self.acm.wait_for_dns_validation_record(
            cert_arn,
            timeout_seconds=self.DNS_RECORD_TIMEOUT_SECONDS,
            poll_interval_seconds=self.DNS_RECORD_POLL_SECONDS,
        )
        change_id = self.route53.upsert_record(
            hosted_zone_id=config.alb_hosted_zone_id,
            name=rr_name,
            record_type=rr_type,
            value=rr_value,
            ttl=self.RECORD_TTL_SECONDS,
        )
        if change_id:
            self.route53.wait_for_change(change_id)

        emit("Waiting for ACM certificate to be issued")
        self.acm.wait_for_issued(cert_arn, timeout_seconds=self.ISSUANCE_TIMEOUT_SECONDS)

        emit(f"ACM certificate issued: {cert_arn}", resource_id=cert_arn)
        return cert_arn


__all__ = ["CertificateProvisioner", "certificate_required"]
