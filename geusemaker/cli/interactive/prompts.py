"""Interactive prompt set used by the deployment wizard."""

from __future__ import annotations

import re
from collections.abc import Iterable

from geusemaker.cli.branding import EMOJI
from geusemaker.cli.components import DialogAbort, DialogBack, Dialogs, messages

STACK_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]*$")
DEFAULT_REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-1"]
INSTANCE_CHOICES = [
    ("t3.medium", "Balanced CPU baseline (default)"),
    ("t3.large", "More memory for heavier workflows"),
    ("m5.large", "CPU optimized, better performance"),
    ("m5.xlarge", "CPU optimized, higher capacity"),
    ("g4dn.xlarge", "Entry GPU for inference (NVIDIA T4)"),
    ("g5.xlarge", "GPU for larger models (NVIDIA A10G)"),
]


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
            "dev – single instance (only tier currently implemented)",
            "automation – ALB + HA (planned, deploys as dev for now)",
            "gpu – ALB + CDN (planned, deploys as dev for now)",
        ]
        tier_keys = ["dev", "automation", "gpu"]
        default_idx = tier_keys.index(default) if default in tier_keys else 0
        choice = self.dialogs.select(
            "Select deployment tier",
            options=tiers,
            default_index=default_idx,
            help_text="Only 'dev' tier is implemented. Other tiers accepted for future compatibility but deploy as dev.",
        )
        return tier_keys[choice]

    def compute_type(self, default: str | None = None) -> str:
        """Select CPU or GPU compute for the deployment."""
        compute_choices = [
            ("cpu", "CPU instances — General workflows, cost-effective"),
            ("gpu", "GPU instances — AI model inference, GPU-accelerated tasks"),
        ]
        labels = [f"{ctype.upper()} — {desc}" for ctype, desc in compute_choices]
        default_idx = next((idx for idx, (name, _) in enumerate(compute_choices) if name == default), 0)
        choice = self.dialogs.select(
            "Choose compute type",
            options=labels,
            default_index=default_idx,
            help_text="CPU is suitable for most automation workflows. GPU is recommended for running AI models.",
        )
        return compute_choices[choice][0]

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

    def instance_type(self, default: str | None = None) -> str:
        labels = [f"{itype} — {desc}" for itype, desc in INSTANCE_CHOICES]
        default_idx = next((idx for idx, (name, _) in enumerate(INSTANCE_CHOICES) if name == default), 0)
        choice = self.dialogs.select(
            "Choose instance type",
            options=labels,
            default_index=default_idx,
            help_text="CPU instances work for most workflows. GPU instances recommended for AI model inference.",
        )
        return INSTANCE_CHOICES[choice][0]

    def os_type(self, default: str | None = None) -> str:
        os_choices = [
            ("ubuntu-22.04", "Ubuntu 22.04 LTS ⚡ fastest deployment"),
            ("amazon-linux-2023", "Amazon Linux 2023 ⚡ fastest deployment"),
            ("ubuntu-24.04", "Ubuntu 24.04 LTS (newest)"),
            ("amazon-linux-2", "Amazon Linux 2 (legacy)"),
        ]
        labels = [f"{os} — {desc}" for os, desc in os_choices]
        default_idx = next((idx for idx, (name, _) in enumerate(os_choices) if name == default), 0)
        choice = self.dialogs.select(
            "Choose operating system",
            options=labels,
            default_index=default_idx,
            help_text="⚡ = Optimized AMI with instant deployment. Others use automatic AMI search.",
        )
        return os_choices[choice][0]

    def architecture(self, default: str | None = None) -> str:
        arch_choices = [
            ("x86_64", "x86_64 (Intel/AMD) — widest compatibility"),
            ("arm64", "ARM64 (Graviton) — 20% cost savings"),
        ]
        labels = [f"{arch} — {desc}" for arch, desc in arch_choices]
        default_idx = next((idx for idx, (name, _) in enumerate(arch_choices) if name == default), 0)
        choice = self.dialogs.select(
            "Choose CPU architecture",
            options=labels,
            default_index=default_idx,
            help_text="x86_64 recommended unless you need Graviton cost optimization.",
        )
        return arch_choices[choice][0]

    def ami_type(self, default: str | None = None) -> str:
        ami_choices = [
            ("base", "Base ⚡ minimal AI stack, fastest deployment"),
            ("pytorch", "PyTorch — pre-configured PyTorch"),
            ("tensorflow", "TensorFlow — pre-configured TensorFlow"),
            ("multi-framework", "Multi-framework — PyTorch + TensorFlow"),
        ]
        labels = [f"{ami} — {desc}" for ami, desc in ami_choices]
        default_idx = next((idx for idx, (name, _) in enumerate(ami_choices) if name == default), 0)
        choice = self.dialogs.select(
            "Choose Deep Learning AMI type",
            options=labels,
            default_index=default_idx,
            help_text="⚡ = Optimized AMI. ML frameworks use automatic AMI search (slower).",
        )
        return ami_choices[choice][0]

    def custom_ami_id(self, default: str | None = None) -> str | None:
        use_custom = self.dialogs.confirm(
            "Use a custom AMI ID instead of auto-selection?",
            default=bool(default),
            help_text="Leave unchecked to use automatic AMI selection based on OS/architecture/type.",
        )
        if not use_custom:
            return None
        return (
            self.dialogs.prompt_text(
                "Enter custom AMI ID:",
                default=default or "",
                validator=lambda value: value.startswith("ami-") or value == "",
                help_text="Must start with 'ami-' (e.g., ami-0123456789abcdef0). Leave blank to auto-select.",
            )
            or None
        )

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

    def create_mount_target_confirm(self, efs_id: str, subnet_id: str) -> bool:
        """Ask user to confirm creating a mount target for existing EFS."""
        return self.dialogs.confirm(
            f"Create mount target for {efs_id} in subnet {subnet_id}?",
            default=True,
            help_text="The selected EFS filesystem doesn't have a mount target in the storage subnet. "
            "A mount target is required for EC2 instances to mount the filesystem.",
        )


__all__ = ["InteractivePrompts", "DialogAbort", "DialogBack"]
