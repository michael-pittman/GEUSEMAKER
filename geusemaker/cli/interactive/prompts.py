"""Interactive prompt set used by the deployment wizard."""

from __future__ import annotations

import re
from collections.abc import Iterable

from geusemaker.cli.branding import EMOJI
from geusemaker.cli.components import DialogAbort, DialogBack, Dialogs, messages

STACK_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*$")
DEFAULT_REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"]
INSTANCE_CHOICES = {
    "dev": [
        ("t3.medium", "Balanced dev default"),
        ("t3.large", "More memory for heavier workflows"),
        ("m5.large", "CPU optimized baseline"),
    ],
    "automation": [
        ("m5.large", "ALB-ready general purpose"),
        ("m5.xlarge", "More headroom for automation tier"),
    ],
    "gpu": [
        ("g4dn.xlarge", "Entry GPU for inference"),
        ("g5.xlarge", "Ampere GPU for larger models"),
    ],
}


class InteractivePrompts:
    """Prompt helpers that wrap Dialogs with domain defaults."""

    def __init__(self, dialogs: Dialogs | None = None):
        self.dialogs = dialogs or Dialogs()

    def welcome(self) -> None:
        messages.info(
            f"{EMOJI['spark']} Interactive mode: type 'back' to revisit a step or 'quit' to exit.",
            title="Interactive",
        )

    def ask_resume(self, path: str) -> bool:
        return self.dialogs.confirm(
            f"Found a saved interactive session at {path}. Resume?",
            default=True,
            allow_back=False,
        )

    def stack_name(self, default: str | None = None) -> str:
        return self.dialogs.prompt_text(
            "Stack name:",
            default=default,
            validator=lambda value: bool(STACK_NAME_PATTERN.match(value)),
            help_text="Letters, numbers, and dashes only (used for tagging).",
        )

    def region(self, default: str | None = None) -> str:
        default_index = DEFAULT_REGIONS.index(default) if default in DEFAULT_REGIONS else 0
        choice = self.dialogs.select(
            "Choose AWS region",
            options=[f"{r} – close to US/EU users" if r.startswith("us") else r for r in DEFAULT_REGIONS],
            default_index=default_index,
            help_text="Pick the closest region to your users for lower latency.",
        )
        return DEFAULT_REGIONS[choice]

    def tier(self, default: str | None = None) -> str:
        tiers = [
            "dev – single instance, fastest path",
            "automation – ALB-ready, HA friendly",
            "gpu – GPU-backed with CDN (future)",
        ]
        tier_keys = ["dev", "automation", "gpu"]
        default_idx = tier_keys.index(default) if default in tier_keys else 0
        choice = self.dialogs.select(
            "Select deployment tier",
            options=tiers,
            default_index=default_idx,
            help_text="Dev = single node, Automation = ALB, GPU = CDN + GPU (roadmap).",
        )
        return tier_keys[choice]

    def use_spot(self, default: bool = True) -> bool:
        return self.dialogs.confirm(
            "Use spot instances when available?",
            default=default,
            help_text="Spot saves 50–70% with automatic on-demand fallback.",
        )

    def attach_internet_gateway(self, default: bool = True, reason: str | None = None) -> bool:
        return self.dialogs.confirm(
            "Attach an internet gateway and public routes to this VPC?",
            default=default,
            help_text=reason or "Required when the selected VPC lacks internet connectivity for the compute subnet.",
        )

    def instance_type(self, tier: str, default: str | None = None) -> str:
        choices = INSTANCE_CHOICES.get(tier, INSTANCE_CHOICES["dev"])
        labels = [f"{itype} — {desc}" for itype, desc in choices]
        default_idx = next((idx for idx, (name, _) in enumerate(choices) if name == default), 0)
        choice = self.dialogs.select(
            "Choose instance type",
            options=labels,
            default_index=default_idx,
            help_text="Pick based on workload needs; defaults favor cost efficiency.",
        )
        return choices[choice][0]

    def confirm_costs(self) -> bool:
        return self.dialogs.confirm(
            "Proceed with these estimated costs?",
            default=True,
            help_text="We will not create resources until you confirm.",
        )

    def confirm_deploy(self) -> bool:
        return self.dialogs.confirm(
            "Start deployment now?",
            default=True,
            help_text="We will run validation and then create resources.",
        )

    def confirm_export(self) -> bool:
        return self.dialogs.confirm(
            "Export this configuration for re-use?",
            default=True,
            help_text="Saves a YAML config under ~/.geusemaker/config.",
        )

    def choose_from_list(
        self,
        label: str,
        options: Iterable[str],
        default_index: int = 0,
        allow_create_new: bool = True,
    ) -> int:
        opt_list = list(options)
        if allow_create_new:
            opt_list.insert(0, "Create new")
        choice = self.dialogs.select(
            label,
            options=opt_list,
            default_index=default_index,
            help_text="Type the number to select, 'back' to revisit, 'quit' to exit.",
        )
        return choice


__all__ = ["InteractivePrompts", "DialogAbort", "DialogBack"]
