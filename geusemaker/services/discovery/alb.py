"""ALB discovery and validation."""

from __future__ import annotations

from geusemaker.infra import AWSClientFactory
from geusemaker.models.discovery import (
    ALBInfo,
    ListenerInfo,
    TargetGroupInfo,
    ValidationResult,
)
from geusemaker.services.base import BaseService
from geusemaker.services.discovery.cache import DiscoveryCache


class ALBDiscoveryService(BaseService):
    """Discover Application Load Balancers and assess readiness."""

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        cache: DiscoveryCache | None = None,
    ):
        super().__init__(client_factory, region)
        self._elbv2 = self._client("elbv2")
        self._cache = cache or DiscoveryCache()

    def list_load_balancers(
        self,
        vpc_id: str,
        use_cache: bool = True,
    ) -> list[ALBInfo]:
        """List ALBs within the given VPC."""
        cache_key = f"albs:{self.region}:{vpc_id}"
        cached = self._cache.get(cache_key) if use_cache else None
        if cached is not None:
            return cached  # type: ignore[return-value]

        def _call() -> list[ALBInfo]:
            paginator = self._elbv2.get_paginator("describe_load_balancers")
            albs: list[ALBInfo] = []
            for page in paginator.paginate():
                for lb in page.get("LoadBalancers", []):
                    if lb.get("VpcId") != vpc_id:
                        continue
                    alb_arn = lb["LoadBalancerArn"]
                    listeners = self._describe_listeners(alb_arn)
                    target_groups = self._describe_target_groups(alb_arn)
                    availability_zones = [
                        zone.get("ZoneName") or zone.get("SubnetId", "") for zone in lb.get("AvailabilityZones", [])
                    ]
                    albs.append(
                        ALBInfo(
                            arn=alb_arn,
                            name=lb.get("LoadBalancerName", alb_arn.split("/")[-1]),
                            dns_name=lb.get("DNSName", ""),
                            scheme=lb.get("Scheme", "internet-facing"),
                            state=lb.get("State", {}).get("Code", "provisioning"),
                            vpc_id=lb.get("VpcId", vpc_id),
                            availability_zones=availability_zones,
                            listeners=listeners,
                            target_groups=target_groups,
                            tags={},
                        ),
                    )
            return albs

        albs = self._safe_call(_call)
        if use_cache:
            self._cache.set(cache_key, albs)
        return albs

    def validate_alb_for_deployment(self, alb: ALBInfo) -> ValidationResult:
        """Check ALB readiness for GeuseMaker traffic."""
        result = ValidationResult.ok()
        if alb.state != "active":
            result.add_issue(f"ALB {alb.name} is in {alb.state} state")
        has_web_listener = any(listener.port in (80, 443) for listener in alb.listeners)
        if not has_web_listener:
            result.add_issue("ALB missing HTTP/HTTPS listener", level="warning")
        if alb.scheme != "internet-facing":
            result.add_issue(
                f"ALB {alb.name} is {alb.scheme}; internet-facing recommended",
                level="warning",
            )
        return result

    def _describe_listeners(self, alb_arn: str) -> list[ListenerInfo]:
        resp = self._elbv2.describe_listeners(LoadBalancerArn=alb_arn)
        listeners: list[ListenerInfo] = []
        for listener in resp.get("Listeners", []):
            default_actions = [
                f"{action.get('Type')}:{action.get('TargetGroupArn', '')}".rstrip(":")
                for action in listener.get("DefaultActions", [])
            ]
            listeners.append(
                ListenerInfo(
                    arn=listener["ListenerArn"],
                    protocol=listener.get("Protocol", ""),
                    port=int(listener.get("Port", 0)),
                    ssl_policy=listener.get("SslPolicy"),
                    default_actions=default_actions,
                ),
            )
        return listeners

    def _describe_target_groups(self, alb_arn: str) -> list[TargetGroupInfo]:
        resp = self._elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
        tgs: list[TargetGroupInfo] = []
        for tg in resp.get("TargetGroups", []):
            tgs.append(
                TargetGroupInfo(
                    arn=tg["TargetGroupArn"],
                    name=tg.get("TargetGroupName", ""),
                    protocol=tg.get("Protocol", ""),
                    port=int(tg.get("Port", 0)),
                    target_type=tg.get("TargetType", ""),
                    vpc_id=tg.get("VpcId", ""),
                    health_check_path=tg.get("HealthCheckPath"),
                ),
            )
        return tgs


__all__ = ["ALBDiscoveryService"]
