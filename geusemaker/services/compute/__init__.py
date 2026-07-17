"""Compute-related services."""

from geusemaker.services.compute.selector import (
    InstancePreference,
    InstanceTypeAlternative,
    InstanceTypeSelection,
    InstanceTypeSelector,
)
from geusemaker.services.compute.spot import SpotSelectionService

__all__ = [
    "SpotSelectionService",
    "InstancePreference",
    "InstanceTypeAlternative",
    "InstanceTypeSelector",
    "InstanceTypeSelection",
]
