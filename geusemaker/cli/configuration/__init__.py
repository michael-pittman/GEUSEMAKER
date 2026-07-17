"""UI-neutral configuration seam shared by the wizard and the Textual deploy form.

The questionary wizard and the Textual deploy form both adapt their session
state into :class:`DeploymentDraft` and build the final ``DeploymentConfig``
through :class:`ConfigBuilder`, so the two front-ends cannot silently produce
different deployments.
"""

from geusemaker.cli.configuration.builder import ConfigBuilder
from geusemaker.cli.configuration.draft import (
    CONFIG_FIELDS,
    DRAFT_ONLY_FIELDS,
    PREVIEW_FIELDS,
    DeploymentDraft,
)

__all__ = [
    "CONFIG_FIELDS",
    "DRAFT_ONLY_FIELDS",
    "PREVIEW_FIELDS",
    "ConfigBuilder",
    "DeploymentDraft",
]
