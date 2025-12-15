"""Automatic instance type selection based on requirements and availability."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.models.deployment import DeploymentConfig
from geusemaker.services.compute.spot import SpotSelectionService

if TYPE_CHECKING:
    from geusemaker.infra import AWSClientFactory
    from geusemaker.services.pricing import PricingService


@dataclass
class InstanceTypeSelection:
    """Result of automatic instance type selection."""

    instance_type: str
    availability_zone: str | None
    is_spot: bool
    price_per_hour: Decimal
    reason: str
    placement_score: float
    fallback_occurred: bool


class InstanceTypeSelector:
    """Automatically select the best available instance type based on requirements."""

    # CPU instance types ordered by preference (cost-effective first)
    CPU_INSTANCE_TYPES = [
        "t3.medium",  # Balanced baseline, cheapest
        "t3.large",  # More memory
        "m5.large",  # CPU optimized
        "m5.xlarge",  # Higher capacity
    ]

    # GPU instance types ordered by preference (cost-effective first, meeting minimum requirements)
    GPU_INSTANCE_TYPES = [
        "g4dn.xlarge",  # Entry GPU (T4, 16GB VRAM, 4 vCPU) - Best cost/performance
        "g5.xlarge",  # Larger models (A10G, 24GB VRAM, 4 vCPU) - Better availability
        "g4dn.2xlarge",  # More CPU headroom (T4, 16GB VRAM, 8 vCPU)
        "g5.2xlarge",  # Larger models + CPU (A10G, 24GB VRAM, 8 vCPU)
        "p3.2xlarge",  # Training-optimized (V100, 16GB VRAM, 8 vCPU)
    ]

    # Minimum requirements for GPU instances (from your research)
    GPU_MIN_VRAM_GB = 16
    GPU_MIN_VCPU = 4

    def __init__(
        self,
        client_factory: AWSClientFactory,
        pricing_service: PricingService,
        region: str = "us-east-1",
    ):
        self._client_factory = client_factory
        self._pricing_service = pricing_service
        self._region = region
        self._spot_service = SpotSelectionService(
            client_factory=client_factory,
            pricing_service=pricing_service,
            region=region,
        )

    def select_best_instance(
        self,
        compute_type: Literal["cpu", "gpu"],
        use_spot: bool = True,
        region: str | None = None,
    ) -> InstanceTypeSelection:
        """Select the best available instance type based on requirements.

        Args:
            compute_type: "cpu" or "gpu"
            use_spot: Whether to prefer spot instances
            region: AWS region (defaults to service region)

        Returns:
            InstanceTypeSelection with the selected instance and reasoning

        """
        region = region or self._region
        instance_types = self.GPU_INSTANCE_TYPES if compute_type == "gpu" else self.CPU_INSTANCE_TYPES

        console.print(
            f"{EMOJI['info']} Searching for best available {compute_type.upper()} instance...",
            verbosity="info",
        )

        # Try each instance type in order of preference
        for instance_type in instance_types:
            console.print(
                f"{EMOJI['info']} Checking {instance_type}...",
                verbosity="debug",
            )

            # Create a temporary config to use spot selection service
            config = DeploymentConfig(
                stack_name="temp-selector",
                tier="dev",
                region=region,
                instance_type=instance_type,
                use_spot=use_spot,
            )

            selection = self._spot_service.select_instance_type(config)

            # If spot is requested and we got spot, or if on-demand is requested and we got it
            if (use_spot and selection.is_spot) or (not use_spot and not selection.is_spot):
                # Success! This instance type is available
                placement_score = 0.0
                if selection.is_spot and selection.availability_zone:
                    # Get placement score from analysis
                    analysis = self._spot_service.analyze_spot_prices(instance_type, region)
                    placement_score = analysis.placement_scores_by_az.get(selection.availability_zone, 0.0)

                reason = self._build_selection_reason(
                    instance_type=instance_type,
                    compute_type=compute_type,
                    is_spot=selection.is_spot,
                    use_spot_preference=use_spot,
                    placement_score=placement_score,
                    tried_count=instance_types.index(instance_type) + 1,
                )

                console.print(
                    f"{EMOJI['check']} Selected {instance_type} ({reason})",
                    verbosity="info",
                )

                return InstanceTypeSelection(
                    instance_type=instance_type,
                    availability_zone=selection.availability_zone,
                    is_spot=selection.is_spot,
                    price_per_hour=selection.price_per_hour,
                    reason=reason,
                    placement_score=placement_score,
                    fallback_occurred=False,
                )

            # This instance type isn't available in the preferred mode, try next
            console.print(
                f"{EMOJI['warning']} {instance_type} not available with preferred settings, trying alternatives...",
                verbosity="debug",
            )

        # If we reach here, none of the preferred instances are available
        # Fall back to the first instance type with on-demand
        fallback_instance = instance_types[0]
        console.print(
            f"{EMOJI['warning']} No spot instances available, falling back to on-demand {fallback_instance}",
            verbosity="info",
        )

        config = DeploymentConfig(
            stack_name="temp-selector",
            tier="dev",
            region=region,
            instance_type=fallback_instance,
            use_spot=False,  # Force on-demand for fallback
        )

        selection = self._spot_service.select_instance_type(config)
        reason = f"fallback to on-demand (spot unavailable for all {compute_type.upper()} instances)"

        return InstanceTypeSelection(
            instance_type=fallback_instance,
            availability_zone=selection.availability_zone,
            is_spot=False,
            price_per_hour=selection.price_per_hour,
            reason=reason,
            placement_score=0.0,
            fallback_occurred=True,
        )

    def _build_selection_reason(
        self,
        instance_type: str,
        compute_type: str,
        is_spot: bool,
        use_spot_preference: bool,
        placement_score: float,
        tried_count: int,
    ) -> str:
        """Build a human-readable reason for the selection."""
        parts = []

        # Instance type position
        if tried_count == 1:
            parts.append("best available")
        else:
            parts.append(f"tried {tried_count} options")

        # Compute type
        parts.append(compute_type.upper())

        # Spot or on-demand
        if is_spot:
            parts.append("spot")
            if placement_score > 0:
                parts.append(f"score: {placement_score:.1f}")
        else:
            if use_spot_preference:
                parts.append("on-demand (spot unavailable)")
            else:
                parts.append("on-demand")

        return ", ".join(parts)


__all__ = ["InstanceTypeSelector", "InstanceTypeSelection"]
