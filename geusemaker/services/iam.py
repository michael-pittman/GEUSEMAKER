"""IAM service for role and instance profile management."""

from __future__ import annotations

import json
import time
from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class IAMService(BaseService):
    """Manage IAM roles and instance profiles for EC2 instances."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._iam = self._client("iam")

    def create_efs_mount_role(self, role_name: str, tags: list[dict[str, str]]) -> str:
        """Create an IAM role with EFS mount permissions for EC2 instances.

        Args:
            role_name: Name for the IAM role
            tags: Resource tags to apply

        Returns:
            Role ARN
        """
        # Trust policy allowing EC2 to assume this role
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        # Inline policy granting EFS mount permissions
        efs_mount_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "elasticfilesystem:ClientMount",
                        "elasticfilesystem:ClientWrite",
                        "elasticfilesystem:ClientRootAccess",
                    ],
                    "Resource": "*",
                }
            ],
        }

        def _call() -> str:
            # Create the role
            create_resp = self._iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy),
                Description="GeuseMaker EFS mount role for EC2 instances",
                Tags=tags,
            )

            # Attach inline policy for EFS mount permissions
            self._iam.put_role_policy(
                RoleName=role_name,
                PolicyName="EFSMountPolicy",
                PolicyDocument=json.dumps(efs_mount_policy),
            )

            # Attach AWS managed policy for SSM access (required for log streaming)
            self._iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            )

            return create_resp["Role"]["Arn"]  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def create_instance_profile(self, profile_name: str, tags: list[dict[str, str]]) -> str:
        """Create an IAM instance profile.

        Args:
            profile_name: Name for the instance profile
            tags: Resource tags to apply

        Returns:
            Instance profile ARN
        """

        def _call() -> str:
            resp = self._iam.create_instance_profile(
                InstanceProfileName=profile_name,
                Tags=tags,
            )
            return resp["InstanceProfile"]["Arn"]  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def attach_role_to_profile(self, profile_name: str, role_name: str) -> None:
        """Attach an IAM role to an instance profile.

        Args:
            profile_name: Instance profile name
            role_name: IAM role name
        """

        def _call() -> None:
            self._iam.add_role_to_instance_profile(
                InstanceProfileName=profile_name,
                RoleName=role_name,
            )

        self._safe_call(_call)

    def wait_for_instance_profile(
        self,
        profile_name: str,
        role_name: str,
        max_attempts: int = 30,
        delay: int = 2,
    ) -> None:
        """Wait for instance profile to be available with role attached.

        Instance profiles may not be immediately usable after creation due to eventual consistency.
        This method verifies both profile existence and role attachment for reliable EC2 usage.

        Args:
            profile_name: Instance profile name to check
            role_name: Expected role name that should be attached
            max_attempts: Maximum number of polling attempts (default: 30)
            delay: Seconds to wait between attempts (default: 2)

        Raises:
            RuntimeError: If instance profile doesn't become available with role attached within timeout
        """

        def _call() -> None:
            for attempt in range(max_attempts):
                try:
                    resp = self._iam.get_instance_profile(InstanceProfileName=profile_name)
                    profile = resp.get("InstanceProfile", {})
                    roles = profile.get("Roles", [])

                    # Verify the expected role is attached
                    if any(r.get("RoleName") == role_name for r in roles):
                        return

                    # Profile exists but role not attached yet - wait and retry
                    if attempt < max_attempts - 1:
                        time.sleep(delay)
                        continue

                    raise RuntimeError(
                        f"Instance profile {profile_name} exists but role {role_name} not attached after {max_attempts * delay}s"
                    )
                except Exception as e:
                    if "NoSuchEntity" in str(e):
                        if attempt < max_attempts - 1:
                            time.sleep(delay)
                            continue
                    raise

            raise RuntimeError(
                f"Instance profile {profile_name} did not become available within {max_attempts * delay} seconds"
            )

        self._safe_call(_call)

    def delete_instance_profile(self, profile_name: str, role_name: str | None = None) -> None:
        """Delete an IAM instance profile, detaching any roles first.

        Args:
            profile_name: Instance profile name to delete
            role_name: Optional role name to detach (if known)
        """

        def _call() -> None:
            # Get the instance profile to find attached roles
            try:
                resp = self._iam.get_instance_profile(InstanceProfileName=profile_name)
                attached_roles = resp.get("InstanceProfile", {}).get("Roles", [])

                # Detach all roles
                for role in attached_roles:
                    self._iam.remove_role_from_instance_profile(
                        InstanceProfileName=profile_name,
                        RoleName=role["RoleName"],
                    )

                # If role_name was provided but not found in attached roles, try to detach it anyway
                if role_name and role_name not in [r["RoleName"] for r in attached_roles]:
                    try:
                        self._iam.remove_role_from_instance_profile(
                            InstanceProfileName=profile_name,
                            RoleName=role_name,
                        )
                    except Exception:  # noqa: S110
                        pass  # Role wasn't attached, continue - acceptable to ignore

            except Exception as e:
                if "NoSuchEntity" not in str(e):
                    raise

            # Delete the instance profile
            try:
                self._iam.delete_instance_profile(InstanceProfileName=profile_name)
            except Exception as e:
                if "NoSuchEntity" not in str(e):
                    raise

        self._safe_call(_call)

    def delete_role(self, role_name: str) -> None:
        """Delete an IAM role, removing inline policies first.

        Args:
            role_name: Role name to delete
        """

        def _call() -> None:
            try:
                # Detach managed policies (SSM policy)
                try:
                    self._iam.detach_role_policy(
                        RoleName=role_name,
                        PolicyArn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
                    )
                except Exception:  # noqa: S110
                    pass  # Policy might not be attached, continue

                # List and delete all inline policies
                resp = self._iam.list_role_policies(RoleName=role_name)
                for policy_name in resp.get("PolicyNames", []):
                    self._iam.delete_role_policy(
                        RoleName=role_name,
                        PolicyName=policy_name,
                    )

                # Delete the role
                self._iam.delete_role(RoleName=role_name)
            except Exception as e:
                if "NoSuchEntity" not in str(e):
                    raise

        self._safe_call(_call)

    def get_role(self, role_name: str) -> dict[str, Any]:
        """Get IAM role details.

        Args:
            role_name: Role name to retrieve

        Returns:
            Role details dictionary
        """

        def _call() -> dict[str, Any]:
            resp = self._iam.get_role(RoleName=role_name)
            return resp["Role"]  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def get_instance_profile(self, profile_name: str) -> dict[str, Any]:
        """Get instance profile details.

        Args:
            profile_name: Instance profile name to retrieve

        Returns:
            Instance profile details dictionary
        """

        def _call() -> dict[str, Any]:
            resp = self._iam.get_instance_profile(InstanceProfileName=profile_name)
            return resp["InstanceProfile"]  # type: ignore[no-any-return]

        return self._safe_call(_call)
