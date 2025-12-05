"""EC2 service for instance and key pair operations."""

from __future__ import annotations

from typing import Any, Literal

from botocore.exceptions import ClientError

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class EC2Service(BaseService):
    """Manage EC2 instance lifecycle."""

    # Region-aware AMI mappings for Amazon Linux 2023 base images
    # Format: {region: {architecture: ami_id}}
    AL2023_BASE_AMIS: dict[str, dict[str, str]] = {
        "us-east-1": {
            "x86_64": "ami-0941ba2cd9ee2998a",
            "arm64": "ami-08742254cf19c5488",
        },
        "us-west-2": {
            "x86_64": "ami-019056869a13971ff",
            "arm64": "ami-0c5b116eea276f6f1",
        },
        "eu-west-1": {
            "x86_64": "ami-0a80bf774329b5816",
            "arm64": "ami-0e69d8ca2344ffc9d",
        },
        "ap-southeast-1": {
            "x86_64": "ami-05b1f2b5642f2ad75",
            "arm64": "ami-0895a44228ddd0f3d",
        },
    }

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")

    def get_latest_ami(self) -> str:
        """Return the most recent Deep Learning AMI using default parameters."""
        return self.get_latest_dlami()

    def validate_ami(self, ami_id: str) -> bool:
        """Validate that an AMI exists and is available in the current region.

        Note: The EC2 API follows an eventual consistency model. Recently deregistered
        AMIs may appear in results for a short interval.

        Args:
            ami_id: AMI ID to validate

        Returns:
            True if AMI exists and is available, False otherwise

        """

        def _call() -> bool:
            try:
                images = self._ec2.describe_images(
                    ImageIds=[ami_id],
                    Owners=["amazon"],  # Only accept official AWS AMIs for security
                    Filters=[{"Name": "state", "Values": ["available"]}],
                ).get("Images", [])
                return len(images) > 0
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code", "")
                if error_code in ("InvalidAMIID.NotFound", "InvalidAMIID.Malformed"):
                    return False
                # Re-raise for unexpected errors (permissions, API issues)
                raise

        return self._safe_call(_call)

    def get_latest_dlami(
        self,
        os_type: Literal["amazon-linux-2023", "ubuntu-22.04", "ubuntu-24.04", "amazon-linux-2"] = "ubuntu-22.04",
        architecture: Literal["x86_64", "arm64"] = "x86_64",
        ami_type: Literal["base", "pytorch", "tensorflow", "multi-framework"] = "base",
        instance_type: str | None = None,
    ) -> str:
        """Return the most recent AWS Deep Learning AMI based on OS, architecture, type, and instance.

        Tries direct AMI ID lookup first for amazon-linux-2023 base images,
        validates the AMI is available, then falls back to pattern-based search
        if no mapping exists or validation fails.

        Args:
            os_type: Operating system type
            architecture: CPU architecture
            ami_type: Deep Learning AMI variant
            instance_type: EC2 instance type (e.g., "t3.medium", "g5.xlarge").
                          If provided, automatically selects GPU vs CPU AMI patterns.

        Returns:
            AMI ID of the latest matching Deep Learning AMI

        """

        def _call() -> str:
            # Try direct AMI ID lookup first for Amazon Linux 2023 base images
            if os_type == "amazon-linux-2023" and ami_type == "base":
                region_amis = self.AL2023_BASE_AMIS.get(self.region)
                if region_amis:
                    ami_id = region_amis.get(architecture)
                    if ami_id and self.validate_ami(ami_id):
                        return ami_id

            # Fallback to pattern-based search
            # NOTE: All Deep Learning AMIs include GPU support (drivers, CUDA, etc.)
            # They work on both CPU and GPU instances - the GPU drivers are simply
            # not used when running on CPU-only instances like t3, c5, m5, etc.
            search_patterns = self._dlami_name_patterns(
                os_type=os_type,
                ami_type=ami_type,
                is_gpu_instance=self._is_gpu_instance_type(instance_type),
            )

            for name_pattern in search_patterns:
                images = self._ec2.describe_images(
                    Owners=["amazon"],
                    Filters=[
                        {"Name": "name", "Values": [name_pattern]},
                        {"Name": "state", "Values": ["available"]},
                        {"Name": "architecture", "Values": [architecture]},
                    ],
                ).get("Images", [])

                if images:
                    latest = sorted(images, key=lambda img: img.get("CreationDate", ""), reverse=True)[0]
                    return latest["ImageId"]

            raise RuntimeError(
                f"No Deep Learning AMI found for os={os_type}, arch={architecture}, "
                f"type={ami_type}, instance_type={instance_type}.",
            )

        return self._safe_call(_call)

    def list_key_pairs(self) -> list[dict[str, Any]]:
        """List SSH key pairs in the region."""

        def _call() -> list[dict[str, Any]]:
            resp = self._ec2.describe_key_pairs()
            return resp.get("KeyPairs", [])  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def launch_instance(self, **kwargs: Any) -> dict[str, Any]:
        """Launch an instance with provided kwargs (stub for future expansion)."""

        def _call() -> dict[str, Any]:
            resp = self._ec2.run_instances(MinCount=1, MaxCount=1, **kwargs)
            return resp  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def wait_for_running(self, instance_id: str) -> None:
        """Wait for an instance to reach running state."""

        def _call() -> None:
            waiter = self._ec2.get_waiter("instance_running")
            waiter.wait(InstanceIds=[instance_id])

        self._safe_call(_call)

    def describe_instance(self, instance_id: str) -> dict[str, Any]:
        """Fetch instance details."""

        def _call() -> dict[str, Any]:
            resp = self._ec2.describe_instances(InstanceIds=[instance_id])
            return resp["Reservations"][0]["Instances"][0]  # type: ignore[index]

        return self._safe_call(_call)

    def stop_instance(self, instance_id: str) -> None:
        """Stop an instance."""

        def _call() -> None:
            self._ec2.stop_instances(InstanceIds=[instance_id])

        self._safe_call(_call)

    def wait_for_stopped(self, instance_id: str) -> None:
        """Wait until an instance is stopped."""

        def _call() -> None:
            waiter = self._ec2.get_waiter("instance_stopped")
            waiter.wait(InstanceIds=[instance_id])

        self._safe_call(_call)

    def modify_instance_type(self, instance_id: str, instance_type: str) -> None:
        """Update the instance type."""

        def _call() -> None:
            self._ec2.modify_instance_attribute(
                InstanceId=instance_id,
                InstanceType={"Value": instance_type},
            )

        self._safe_call(_call)

    def start_instance(self, instance_id: str) -> None:
        """Start an instance."""

        def _call() -> None:
            self._ec2.start_instances(InstanceIds=[instance_id])

        self._safe_call(_call)

    def terminate_instance(self, instance_id: str) -> None:
        """Terminate an instance."""

        def _call() -> None:
            self._ec2.terminate_instances(InstanceIds=[instance_id])

        self._safe_call(_call)

    def wait_for_terminated(self, instance_id: str) -> None:
        """Wait until an instance is terminated."""

        def _call() -> None:
            waiter = self._ec2.get_waiter("instance_terminated")
            waiter.wait(InstanceIds=[instance_id])

        self._safe_call(_call)

    @staticmethod
    def _is_gpu_instance_type(instance_type: str | None) -> bool:
        """Detect if an EC2 instance type has GPU support.

        Args:
            instance_type: EC2 instance type (e.g., "t3.medium", "g5.xlarge")

        Returns:
            True if instance type is GPU-enabled, False otherwise

        Supported GPU families:
            - p3, p4, p5, p6 (training-optimized with NVIDIA Tesla/H100/B200)
            - g3, g4, g5, g6 (graphics/inference-optimized with NVIDIA M60/T4/A10G/L4)
            - g5g (ARM64 Graviton with GPU)

        """
        if not instance_type:
            return False

        # Extract instance family (e.g., "g5" from "g5.xlarge")
        family = instance_type.split(".")[0].lower()

        # GPU instance families per AWS documentation
        gpu_families = {
            "p3",
            "p4",
            "p5",
            "p5e",
            "p6",  # Training-optimized (V100, A100, H100, B200)
            "g3",
            "g4",
            "g5",
            "g6",  # Graphics/inference (M60, T4, A10G, L4)
            "g6e",
            "g5g",  # ARM64 Graviton with GPU
        }

        return family in gpu_families

    def _dlami_name_patterns(
        self,
        os_type: Literal["amazon-linux-2023", "ubuntu-22.04", "ubuntu-24.04", "amazon-linux-2"],
        ami_type: Literal["base", "pytorch", "tensorflow", "multi-framework"],
        is_gpu_instance: bool,
    ) -> list[str]:
        """Return ordered AMI name patterns, preferring CPU/GPU variants based on instance type."""
        patterns: dict[str, dict[str, dict[str, list[str]]]] = {
            "base": {
                "gpu": {
                    "amazon-linux-2023": [
                        "Deep Learning Base GPU AMI (Amazon Linux 2023)*",
                        "Deep Learning Base*GPU* (Amazon Linux 2023)*",
                        "Deep Learning Base* (Amazon Linux 2023)*",
                    ],
                    "ubuntu-22.04": [
                        "Deep Learning Base GPU AMI (Ubuntu 22.04)*",
                        "Deep Learning Base*GPU* (Ubuntu 22.04)*",
                        "Deep Learning Base* (Ubuntu 22.04)*",
                    ],
                    "ubuntu-24.04": [
                        "Deep Learning Base GPU AMI (Ubuntu 24.04)*",
                        "Deep Learning Base*GPU* (Ubuntu 24.04)*",
                        "Deep Learning Base* (Ubuntu 24.04)*",
                    ],
                    "amazon-linux-2": [
                        "Deep Learning Base GPU AMI (Amazon Linux 2)*",
                        "Deep Learning Base*GPU* (Amazon Linux 2)*",
                        "Deep Learning Base* (Amazon Linux 2)*",
                    ],
                },
                "cpu": {
                    "amazon-linux-2023": [
                        "Deep Learning Base AMI (Amazon Linux 2023)*",
                        "Deep Learning Base*AMI* (Amazon Linux 2023)*",
                        "Deep Learning Base* (Amazon Linux 2023)*",
                    ],
                    "ubuntu-22.04": [
                        "Deep Learning Base AMI (Ubuntu 22.04)*",
                        "Deep Learning Base*AMI* (Ubuntu 22.04)*",
                        "Deep Learning Base* (Ubuntu 22.04)*",
                    ],
                    "ubuntu-24.04": [
                        "Deep Learning Base AMI (Ubuntu 24.04)*",
                        "Deep Learning Base*AMI* (Ubuntu 24.04)*",
                        "Deep Learning Base* (Ubuntu 24.04)*",
                    ],
                    "amazon-linux-2": [
                        "Deep Learning Base AMI (Amazon Linux 2)*",
                        "Deep Learning Base*AMI* (Amazon Linux 2)*",
                        "Deep Learning Base* (Amazon Linux 2)*",
                    ],
                },
            },
            "pytorch": {
                "gpu": {
                    "amazon-linux-2023": [
                        "Deep Learning AMI GPU PyTorch* (Amazon Linux 2023)*",
                        "Deep Learning AMI*GPU*PyTorch* (Amazon Linux 2023)*",
                    ],
                    "ubuntu-22.04": [
                        "Deep Learning AMI GPU PyTorch* (Ubuntu 22.04)*",
                        "Deep Learning AMI*GPU*PyTorch* (Ubuntu 22.04)*",
                    ],
                    "ubuntu-24.04": [
                        "Deep Learning AMI GPU PyTorch* (Ubuntu 24.04)*",
                        "Deep Learning AMI*GPU*PyTorch* (Ubuntu 24.04)*",
                    ],
                    "amazon-linux-2": [
                        "Deep Learning AMI GPU PyTorch* (Amazon Linux 2)*",
                        "Deep Learning AMI*GPU*PyTorch* (Amazon Linux 2)*",
                    ],
                },
                "cpu": {
                    "amazon-linux-2023": ["Deep Learning AMI CPU PyTorch* (Amazon Linux 2023)*"],
                    "ubuntu-22.04": ["Deep Learning AMI CPU PyTorch* (Ubuntu 22.04)*"],
                    "ubuntu-24.04": ["Deep Learning AMI CPU PyTorch* (Ubuntu 24.04)*"],
                    "amazon-linux-2": ["Deep Learning AMI CPU PyTorch* (Amazon Linux 2)*"],
                },
            },
            "tensorflow": {
                "gpu": {
                    "amazon-linux-2023": ["Deep Learning AMI GPU TensorFlow* (Amazon Linux 2023)*"],
                    "ubuntu-22.04": ["Deep Learning AMI GPU TensorFlow* (Ubuntu 22.04)*"],
                    "ubuntu-24.04": ["Deep Learning AMI GPU TensorFlow* (Ubuntu 24.04)*"],
                    "amazon-linux-2": ["Deep Learning AMI GPU TensorFlow* (Amazon Linux 2)*"],
                },
                "cpu": {
                    "amazon-linux-2023": ["Deep Learning AMI CPU TensorFlow* (Amazon Linux 2023)*"],
                    "ubuntu-22.04": ["Deep Learning AMI CPU TensorFlow* (Ubuntu 22.04)*"],
                    "ubuntu-24.04": ["Deep Learning AMI CPU TensorFlow* (Ubuntu 24.04)*"],
                    "amazon-linux-2": ["Deep Learning AMI CPU TensorFlow* (Amazon Linux 2)*"],
                },
            },
            "multi-framework": {
                "gpu": {
                    "amazon-linux-2023": [
                        "Deep Learning AMI GPU (Amazon Linux 2023)*",
                        "Deep Learning AMI*GPU* (Amazon Linux 2023)*",
                    ],
                    "ubuntu-22.04": [
                        "Deep Learning AMI GPU (Ubuntu 22.04)*",
                        "Deep Learning AMI*GPU* (Ubuntu 22.04)*",
                    ],
                    "ubuntu-24.04": [
                        "Deep Learning AMI GPU (Ubuntu 24.04)*",
                        "Deep Learning AMI*GPU* (Ubuntu 24.04)*",
                    ],
                    "amazon-linux-2": [
                        "Deep Learning AMI GPU (Amazon Linux 2)*",
                        "Deep Learning AMI*GPU* (Amazon Linux 2)*",
                    ],
                },
                "cpu": {
                    "amazon-linux-2023": [
                        "Deep Learning AMI (Amazon Linux 2023)*",
                        "Deep Learning AMI CPU (Amazon Linux 2023)*",
                    ],
                    "ubuntu-22.04": [
                        "Deep Learning AMI (Ubuntu 22.04)*",
                        "Deep Learning AMI CPU (Ubuntu 22.04)*",
                        "Deep Learning AMI* (Ubuntu 22.04)*",
                    ],
                    "ubuntu-24.04": [
                        "Deep Learning AMI (Ubuntu 24.04)*",
                        "Deep Learning AMI CPU (Ubuntu 24.04)*",
                        "Deep Learning AMI* (Ubuntu 24.04)*",
                    ],
                    "amazon-linux-2": [
                        "Deep Learning AMI (Amazon Linux 2)*",
                        "Deep Learning AMI CPU (Amazon Linux 2)*",
                        "Deep Learning AMI* (Amazon Linux 2)*",
                    ],
                },
            },
        }

        try:
            variant_map = patterns[ami_type]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise RuntimeError(f"Unsupported Deep Learning AMI selection: os={os_type}, type={ami_type}") from exc

        ordered_variants = ("gpu", "cpu") if is_gpu_instance else ("cpu", "gpu")
        ordered_patterns: list[str] = []
        for variant in ordered_variants:
            candidates = variant_map.get(variant, {}).get(os_type, [])
            ordered_patterns.extend(candidates)

        deduped: list[str] = []
        seen: set[str] = set()
        for pattern in ordered_patterns:
            if pattern not in seen:
                deduped.append(pattern)
                seen.add(pattern)

        if not deduped:
            raise RuntimeError(f"Unsupported Deep Learning AMI selection: os={os_type}, type={ami_type}")

        return deduped


__all__ = ["EC2Service"]
