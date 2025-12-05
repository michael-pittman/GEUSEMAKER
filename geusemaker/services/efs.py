"""EFS service for filesystem creation."""

from __future__ import annotations

import time
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class EFSService(BaseService):
    """Manage EFS lifecycle."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._efs = self._client("efs")

    def create_filesystem(self, tags: list[dict[str, str]]) -> dict[str, Any]:
        """Create an encrypted EFS filesystem with standard defaults."""

        def _call() -> dict[str, Any]:
            return self._efs.create_file_system(  # type: ignore[no-any-return]
                PerformanceMode="generalPurpose",
                Encrypted=True,
                ThroughputMode="bursting",
                Tags=tags,
            )

        return self._safe_call(_call)

    def wait_for_available(self, fs_id: str, max_attempts: int = 60, delay: int = 5) -> None:
        """Wait for EFS filesystem to reach 'available' state.

        Polls describe_file_systems until LifeCycleState transitions from 'creating' to 'available'.
        This is required before creating mount targets.

        Args:
            fs_id: The filesystem ID to monitor
            max_attempts: Maximum number of polling attempts (default: 60)
            delay: Seconds to wait between attempts (default: 5)

        Raises:
            RuntimeError: If filesystem doesn't become available within max_attempts * delay seconds
                         or if filesystem enters an error state
        """

        def _call() -> None:
            for attempt in range(max_attempts):
                resp = self._efs.describe_file_systems(FileSystemId=fs_id)
                if not resp.get("FileSystems"):
                    raise RuntimeError(f"EFS filesystem {fs_id} not found")

                state = resp["FileSystems"][0]["LifeCycleState"]

                if state == "available":
                    return

                if state in ("deleting", "deleted", "error"):
                    raise RuntimeError(f"EFS filesystem {fs_id} entered invalid state: {state}")

                if attempt < max_attempts - 1:
                    time.sleep(delay)

            raise RuntimeError(
                f"EFS filesystem {fs_id} did not become available within {max_attempts * delay} seconds (timeout)"
            )

        self._safe_call(_call)

    def create_mount_target(self, fs_id: str, subnet_id: str, security_groups: list[str]) -> str:
        """Create an EFS mount target."""

        def _call() -> str:
            resp = self._efs.create_mount_target(
                FileSystemId=fs_id,
                SubnetId=subnet_id,
                SecurityGroups=security_groups,
            )
            return resp["MountTargetId"]  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def wait_for_mount_target_available(self, mount_target_id: str, max_attempts: int = 60, delay: int = 5) -> None:
        """Wait for EFS mount target to reach 'available' state.

        Polls describe_mount_targets until LifeCycleState transitions from 'creating' to 'available'.
        This is required before EC2 instances can successfully mount the filesystem.

        Args:
            mount_target_id: The mount target ID to monitor
            max_attempts: Maximum number of polling attempts (default: 60)
            delay: Seconds to wait between attempts (default: 5)

        Raises:
            RuntimeError: If mount target doesn't become available within max_attempts * delay seconds
                         or if mount target enters an error state
        """

        def _call() -> None:
            for attempt in range(max_attempts):
                resp = self._efs.describe_mount_targets(MountTargetId=mount_target_id)
                if not resp.get("MountTargets"):
                    raise RuntimeError(f"EFS mount target {mount_target_id} not found")

                state = resp["MountTargets"][0]["LifeCycleState"]

                if state == "available":
                    return

                if state in ("deleting", "deleted", "error"):
                    raise RuntimeError(f"EFS mount target {mount_target_id} entered invalid state: {state}")

                if attempt < max_attempts - 1:
                    time.sleep(delay)

            raise RuntimeError(
                f"EFS mount target {mount_target_id} did not become available within {max_attempts * delay} seconds (timeout)"
            )

        self._safe_call(_call)

    def delete_mount_target(self, mount_target_id: str) -> None:
        """Delete an EFS mount target."""

        def _call() -> None:
            self._efs.delete_mount_target(MountTargetId=mount_target_id)

        self._safe_call(_call)

    def delete_filesystem(self, fs_id: str) -> None:
        """Delete an EFS filesystem."""

        def _call() -> None:
            self._efs.delete_file_system(FileSystemId=fs_id)

        self._safe_call(_call)

    def list_mount_targets(self, fs_id: str) -> list[str]:
        """List mount target IDs for a filesystem."""

        def _call() -> list[str]:
            resp = self._efs.describe_mount_targets(FileSystemId=fs_id)
            return [mt["MountTargetId"] for mt in resp.get("MountTargets", [])]  # type: ignore[return-value]

        return self._safe_call(_call)

    def wait_for_mount_target_deleted(self, mount_target_id: str, max_attempts: int = 60, delay: int = 5) -> None:
        """Wait until an EFS mount target is fully deleted."""

        def _call() -> None:
            for attempt in range(max_attempts):
                resp = self._efs.describe_mount_targets(MountTargetId=mount_target_id)
                targets = resp.get("MountTargets", [])
                if not targets:
                    return

                state = targets[0].get("LifeCycleState")
                if state == "deleted":
                    return
                if state not in ("deleting", "available", "creating"):
                    raise RuntimeError(f"EFS mount target {mount_target_id} entered invalid state: {state}")

                if attempt < max_attempts - 1:
                    time.sleep(delay)

            raise RuntimeError(
                f"EFS mount target {mount_target_id} did not delete within {max_attempts * delay} seconds (timeout)"
            )

        self._safe_call(_call)


__all__ = ["EFSService"]
