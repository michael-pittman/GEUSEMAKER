"""Route 53 service for DNS record management."""

from __future__ import annotations

from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class Route53Service(BaseService):
    """Manage Route 53 DNS records (used for ACM validation)."""

    def __init__(self, client_factory: AWSClientFactory):
        # Route53 is global; region is unused.
        super().__init__(client_factory, region="us-east-1")
        self._route53 = self._client("route53")

    def upsert_record(
        self,
        hosted_zone_id: str,
        name: str,
        record_type: str,
        value: str,
        ttl: int = 60,
    ) -> str:
        """UPSERT a single DNS record; returns the change id."""

        def _call() -> str:
            resp = self._route53.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch={
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": name,
                                "Type": record_type,
                                "TTL": ttl,
                                "ResourceRecords": [{"Value": value}],
                            },
                        }
                    ]
                },
            )
            change_id = resp.get("ChangeInfo", {}).get("Id", "")
            return change_id.split("/")[-1] if change_id else change_id

        return self._safe_call(_call)

    def upsert_alias(
        self,
        hosted_zone_id: str,
        record_name: str,
        dns_name: str,
        target_hosted_zone_id: str,
        record_type: str = "A",
        evaluate_target_health: bool = False,
    ) -> str:
        """Create/replace an ALIAS record (A/AAAA) pointing to an AWS target (e.g., ALB)."""

        def _call() -> str:
            resp = self._route53.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch={
                    "Changes": [
                        {
                            "Action": "UPSERT",
                            "ResourceRecordSet": {
                                "Name": record_name,
                                "Type": record_type,
                                "AliasTarget": {
                                    "HostedZoneId": target_hosted_zone_id,
                                    "DNSName": dns_name,
                                    "EvaluateTargetHealth": evaluate_target_health,
                                },
                            },
                        }
                    ]
                },
            )
            change_id = resp.get("ChangeInfo", {}).get("Id", "")
            return change_id.split("/")[-1] if change_id else change_id

        return self._safe_call(_call)

    def wait_for_change(self, change_id: str) -> None:
        def _call() -> None:
            waiter = self._route53.get_waiter("resource_record_sets_changed")
            waiter.wait(Id=change_id)

        self._safe_call(_call)

    def list_record_sets(self, hosted_zone_id: str, record_name: str) -> list[dict[str, Any]]:
        """Return record sets in the zone whose name matches ``record_name`` exactly."""
        wanted = record_name.rstrip(".").lower()

        def _call() -> list[dict[str, Any]]:
            resp = self._route53.list_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                StartRecordName=record_name,
                MaxItems="20",
            )
            return [
                rrset
                for rrset in resp.get("ResourceRecordSets", [])
                if rrset.get("Name", "").rstrip(".").lower() == wanted
            ]

        return self._safe_call(_call)

    def delete_record_set(self, hosted_zone_id: str, record_set: dict[str, Any]) -> str:
        """Delete an exact record set (as returned by list_record_sets); returns the change id."""

        def _call() -> str:
            resp = self._route53.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch={"Changes": [{"Action": "DELETE", "ResourceRecordSet": record_set}]},
            )
            change_id = resp.get("ChangeInfo", {}).get("Id", "")
            return change_id.split("/")[-1] if change_id else change_id

        return self._safe_call(_call)


__all__ = ["Route53Service"]
