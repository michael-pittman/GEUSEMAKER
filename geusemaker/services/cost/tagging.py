"""Resource tagging utilities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.models.cost import ResourceTags
from geusemaker.services.base import BaseService


class ResourceTagger(BaseService):
    """Apply standardized GeuseMaker tags to AWS resources."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")
        self._efs = self._client("efs")
        self._elbv2 = self._client("elbv2")

    def build_tags(self, deployment: str, tier: str, created_by: str = "geusemaker") -> list[dict[str, str]]:
        """Return standard tag set for a deployment."""
        tags = ResourceTags(
            deployment=deployment,
            tier=tier,
            created_at=datetime.now(UTC).isoformat(),
            created_by=created_by,
        )
        return tags.to_aws()

    def tag_instances(self, instance_ids: list[str], tags: list[dict[str, str]]) -> Any:
        """Apply tags to EC2 instances."""

        def _call() -> Any:
            return self._ec2.create_tags(Resources=instance_ids, Tags=tags)

        return self._safe_call(_call)

    def tag_efs(self, file_system_id: str, tags: list[dict[str, str]]) -> Any:
        """Apply tags to an EFS filesystem."""

        def _call() -> Any:
            return self._efs.create_tags(FileSystemId=file_system_id, Tags=tags)

        return self._safe_call(_call)

    def tag_alb(self, resource_arn: str, tags: list[dict[str, str]]) -> Any:
        """Apply tags to an ALB."""

        def _call() -> Any:
            return self._elbv2.add_tags(ResourceArns=[resource_arn], Tags=tags)

        return self._safe_call(_call)


__all__ = ["ResourceTagger"]
