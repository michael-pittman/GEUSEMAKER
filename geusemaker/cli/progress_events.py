"""Back-compat shim for the UI-neutral deployment progress contract.

The contract now lives in :mod:`geusemaker.progress`. This module re-exports it
so existing imports from ``geusemaker.cli.progress_events`` keep working.
"""

from geusemaker.progress import ProgressCallback, ProgressEvent, ProgressLevel, Stage

__all__ = ["ProgressCallback", "ProgressEvent", "ProgressLevel", "Stage"]
