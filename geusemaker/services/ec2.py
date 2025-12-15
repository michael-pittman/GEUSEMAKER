"""EC2 service for instance and key pair operations."""

from __future__ import annotations

from typing import Any, Literal

from botocore.exceptions import ClientError

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class EC2Service(BaseService):
    """Manage EC2 instance lifecycle."""

    # Deep Learning Base AMI mappings with Single CUDA (unified for CPU and GPU instances)
    # Format: {region: {os_type: {architecture: ami_id}}}
    #
    # These AMIs are "Deep Learning Base AMI with Single CUDA" which work on both
    # CPU and GPU instances - GPU drivers (CUDA, cuDNN, etc.) are present but
    # dormant on CPU-only instances (t3, c5, m5, etc.) and activate automatically
    # on GPU instances (p3, p4, p5, g4, g5, g6, etc.).
    #
    # REGIONAL STRATEGY:
    # - Only us-east-1 is optimized with hardcoded AMI IDs for faster deployments
    # - Other regions use pattern-based search (fallback in get_latest_dlami)
    # - This avoids maintaining stale AMI IDs across all regions
    # - All regions are fully supported via the automatic pattern search
    #
    # BENEFITS OF HARDCODED IDS (us-east-1 only):
    # - Skip describe_images API call (faster)
    # - Guaranteed availability (validated)
    # - Newer images: Dec 2025 AMIs vs older Nov 2025 versions
    # - Smaller size: 30 GB vs 40 GB (saves disk space and launch time)
    DLAMI_BASE: dict[str, dict[str, dict[str, str]]] = {
        "us-east-1": {
            "amazon-linux-2023": {
                "x86_64": "ami-00a3a6192ba06e9ae",  # Deep Learning Base AMI with Single CUDA (30 GB)
                "arm64": "ami-0f7f69448b947f02e",  # Deep Learning Base AMI with Single CUDA (30 GB)
            },
            "ubuntu-22.04": {
                "x86_64": "ami-0193ca8306cf64925",  # Deep Learning Base AMI with Single CUDA (30 GB)
                "arm64": "ami-08f9f6bb4d8be1db8",  # Deep Learning Base AMI with Single CUDA (30 GB)
            },
        },
    }

    # GPU instance type specifications for LLM inference workloads
    # Format: {instance_type: {specs}}
    # Includes GPU model, memory, vCPU, and system memory for cost/performance planning
    GPU_INSTANCE_TYPES: dict[str, dict[str, str | int]] = {
        # G4dn instances (NVIDIA T4 Tensor Core GPUs) - Best for cost-effective inference
        "g4dn.xlarge": {"gpu": "T4", "gpu_count": 1, "gpu_memory_gb": 16, "vcpu": 4, "memory_gb": 16},
        "g4dn.2xlarge": {"gpu": "T4", "gpu_count": 1, "gpu_memory_gb": 16, "vcpu": 8, "memory_gb": 32},
        "g4dn.4xlarge": {"gpu": "T4", "gpu_count": 1, "gpu_memory_gb": 16, "vcpu": 16, "memory_gb": 64},
        "g4dn.8xlarge": {"gpu": "T4", "gpu_count": 1, "gpu_memory_gb": 16, "vcpu": 32, "memory_gb": 128},
        "g4dn.12xlarge": {"gpu": "T4", "gpu_count": 4, "gpu_memory_gb": 64, "vcpu": 48, "memory_gb": 192},
        "g4dn.16xlarge": {"gpu": "T4", "gpu_count": 1, "gpu_memory_gb": 16, "vcpu": 64, "memory_gb": 256},
        # G5 instances (NVIDIA A10G Tensor Core GPUs) - Best for large models (24GB VRAM)
        "g5.xlarge": {"gpu": "A10G", "gpu_count": 1, "gpu_memory_gb": 24, "vcpu": 4, "memory_gb": 16},
        "g5.2xlarge": {"gpu": "A10G", "gpu_count": 1, "gpu_memory_gb": 24, "vcpu": 8, "memory_gb": 32},
        "g5.4xlarge": {"gpu": "A10G", "gpu_count": 1, "gpu_memory_gb": 24, "vcpu": 16, "memory_gb": 64},
        "g5.8xlarge": {"gpu": "A10G", "gpu_count": 1, "gpu_memory_gb": 24, "vcpu": 32, "memory_gb": 128},
        "g5.12xlarge": {"gpu": "A10G", "gpu_count": 4, "gpu_memory_gb": 96, "vcpu": 48, "memory_gb": 192},
        "g5.16xlarge": {"gpu": "A10G", "gpu_count": 1, "gpu_memory_gb": 24, "vcpu": 64, "memory_gb": 256},
        "g5.24xlarge": {"gpu": "A10G", "gpu_count": 4, "gpu_memory_gb": 96, "vcpu": 96, "memory_gb": 384},
        "g5.48xlarge": {"gpu": "A10G", "gpu_count": 8, "gpu_memory_gb": 192, "vcpu": 192, "memory_gb": 768},
        # P3 instances (NVIDIA V100 Tensor Core GPUs) - Training-optimized
        "p3.2xlarge": {"gpu": "V100", "gpu_count": 1, "gpu_memory_gb": 16, "vcpu": 8, "memory_gb": 61},
        "p3.8xlarge": {"gpu": "V100", "gpu_count": 4, "gpu_memory_gb": 64, "vcpu": 32, "memory_gb": 244},
        "p3.16xlarge": {"gpu": "V100", "gpu_count": 8, "gpu_memory_gb": 128, "vcpu": 64, "memory_gb": 488},
        # P4 instances (NVIDIA A100 40GB GPUs) - High-performance training
        "p4d.24xlarge": {"gpu": "A100", "gpu_count": 8, "gpu_memory_gb": 320, "vcpu": 96, "memory_gb": 1152},
        # P5 instances (NVIDIA H100 80GB GPUs) - Latest generation
        "p5.48xlarge": {"gpu": "H100", "gpu_count": 8, "gpu_memory_gb": 640, "vcpu": 192, "memory_gb": 2048},
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
            # Try direct AMI ID lookup for base AMI type
            if ami_type == "base":
                region_amis = self.DLAMI_BASE.get(self.region)
                if region_amis:
                    os_amis = region_amis.get(os_type)
                    if os_amis:
                        ami_id = os_amis.get(architecture)
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

    def get_root_device_name(self, ami_id: str) -> str:
        """Return the root device name for an AMI (e.g., /dev/xvda)."""

        def _call() -> str:
            resp = self._ec2.describe_images(ImageIds=[ami_id]).get("Images", [])
            if not resp:
                raise RuntimeError(f"AMI {ami_id} not found")
            root = resp[0].get("RootDeviceName")
            if not root:
                raise RuntimeError(f"AMI {ami_id} missing RootDeviceName")
            return root  # type: ignore[no-any-return]

        return self._safe_call(_call)

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
            "p4d",
            "p4de",
            "p5",
            "p5e",
            "p6",  # Training-optimized (V100, A100, H100, B200)
            "g3",
            "g3s",
            "g4",
            "g4dn",
            "g4ad",
            "g5",
            "g5g",
            "g6",
            "g6e",  # Graphics/inference (M60, T4, A10G, L4)
        }

        return family in gpu_families

    @classmethod
    def get_gpu_instance_specs(cls, instance_type: str) -> dict[str, str | int] | None:
        """Get GPU specifications for a given instance type.

        Args:
            instance_type: EC2 instance type (e.g., "g5.xlarge")

        Returns:
            Dictionary with GPU specs (gpu, gpu_count, gpu_memory_gb, vcpu, memory_gb)
            or None if instance type is not in the GPU_INSTANCE_TYPES mapping

        Example:
            >>> EC2Service.get_gpu_instance_specs("g5.xlarge")
            {"gpu": "A10G", "gpu_count": 1, "gpu_memory_gb": 24, "vcpu": 4, "memory_gb": 16}

        """
        return cls.GPU_INSTANCE_TYPES.get(instance_type)

    @classmethod
    def validate_gpu_instance_type(cls, instance_type: str) -> tuple[bool, str | None]:
        """Validate if an instance type is supported for GPU workloads.

        Checks if the instance type:
        1. Has GPU hardware (detected by family name)
        2. Is in the GPU_INSTANCE_TYPES mapping with known specifications

        Args:
            instance_type: EC2 instance type to validate

        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if instance type is fully supported
            - (False, error_message) if instance type is not supported

        Example:
            >>> EC2Service.validate_gpu_instance_type("g5.xlarge")
            (True, None)
            >>> EC2Service.validate_gpu_instance_type("t3.medium")
            (False, "Instance type 't3.medium' does not have GPU support")

        """
        # Check if instance type has GPU hardware
        if not cls._is_gpu_instance_type(instance_type):
            return False, f"Instance type '{instance_type}' does not have GPU support"

        # Check if we have specifications for this GPU instance type
        if instance_type not in cls.GPU_INSTANCE_TYPES:
            return (
                False,
                f"GPU instance type '{instance_type}' is not in the supported list. "
                f"Supported types: {', '.join(sorted(cls.GPU_INSTANCE_TYPES.keys()))}",
            )

        return True, None

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
