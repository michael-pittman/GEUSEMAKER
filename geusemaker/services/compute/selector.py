"""Automatic instance type selection based on requirements and availability."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from geusemaker.cli import console
from geusemaker.cli.branding import EMOJI
from geusemaker.models.compute import InstanceSelection
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
    alternatives: tuple[InstanceTypeAlternative, ...] = ()


@dataclass(frozen=True)
class InstanceTypeAlternative:
    """A ranked, eligible alternative shown alongside the recommendation."""

    instance_type: str
    is_spot: bool
    price_per_hour: Decimal
    placement_score: float


InstancePreference = Literal["balanced", "lowest_cost", "highest_availability", "performance"]


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
        preference: InstancePreference = "balanced",
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

        candidates: list[tuple[int, InstanceSelection, float]] = []
        for rank, instance_type in enumerate(instance_types):
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

            placement_score = 0.0
            if selection.is_spot and selection.availability_zone:
                analysis = self._spot_service.analyze_spot_prices(instance_type, region)
                placement_score = analysis.placement_scores_by_az.get(selection.availability_zone, 0.0)
            candidates.append((rank, selection, placement_score))

        if not candidates:  # defensive: the spot service normally returns on-demand fallback
            raise RuntimeError(f"No eligible {compute_type.upper()} instance candidates")

        candidates.sort(key=lambda item: self._ranking_key(item, preference, use_spot))
        _, selection, placement_score = candidates[0]
        fallback = use_spot and not selection.is_spot
        reason = self._build_selection_reason(
            instance_type=selection.instance_type,
            compute_type=compute_type,
            is_spot=selection.is_spot,
            use_spot_preference=use_spot,
            placement_score=placement_score,
            tried_count=len(candidates),
            preference=preference,
        )
        alternatives = tuple(
            InstanceTypeAlternative(
                instance_type=item.instance_type,
                is_spot=item.is_spot,
                price_per_hour=item.price_per_hour,
                placement_score=score,
            )
            for _, item, score in candidates[1:4]
        )
        console.print(f"{EMOJI['check']} Selected {selection.instance_type} ({reason})", verbosity="info")

        return InstanceTypeSelection(
            instance_type=selection.instance_type,
            availability_zone=selection.availability_zone,
            is_spot=selection.is_spot,
            price_per_hour=selection.price_per_hour,
            reason=reason,
            placement_score=placement_score,
            fallback_occurred=fallback,
            alternatives=alternatives,
        )

    @staticmethod
    def _ranking_key(
        candidate: tuple[int, InstanceSelection, float], preference: InstancePreference, use_spot: bool
    ) -> tuple[object, ...]:
        rank, selection, placement = candidate
        mode_penalty = int(selection.is_spot != use_spot)
        if preference == "lowest_cost":
            return (selection.price_per_hour, mode_penalty, -placement)
        if preference == "highest_availability":
            return (mode_penalty, -placement, selection.price_per_hour)
        if preference == "performance":
            return (-rank, mode_penalty, selection.price_per_hour)
        # Balanced: honor purchase mode, then combine price and capacity signal.
        adjusted_cost = selection.price_per_hour / Decimal(str(1 + max(placement, 0) / 10))
        return (mode_penalty, adjusted_cost, rank)

    def _build_selection_reason(
        self,
        instance_type: str,
        compute_type: str,
        is_spot: bool,
        use_spot_preference: bool,
        placement_score: float,
        tried_count: int,
        preference: InstancePreference = "balanced",
    ) -> str:
        """Build a human-readable reason for the selection."""
        parts = []

        # Instance type position
        parts.append(f"{preference.replace('_', ' ')} policy across {tried_count} options")

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


__all__ = [
    "InstancePreference",
    "InstanceTypeAlternative",
    "InstanceTypeSelector",
    "InstanceTypeSelection",
]
