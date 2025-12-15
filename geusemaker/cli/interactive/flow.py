"""Interactive deployment flow orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from geusemaker.cli.components import (
    DialogAbort,
    DialogBack,
    Dialogs,
    messages,
    spinner,
    tables,
)
from geusemaker.cli.interactive.prompts import InteractivePrompts
from geusemaker.infra import AWSClientFactory, StateManager
from geusemaker.models import DeploymentConfig
from geusemaker.models.discovery import (
    EFSInfo,
    KeyPairInfo,
    SecurityGroupInfo,
    SubnetInfo,
    VPCInfo,
)
from geusemaker.services.cost import CostEstimator
from geusemaker.services.discovery import (
    DiscoveryCache,
    EFSDiscoveryService,
    KeyPairDiscoveryService,
    SecurityGroupDiscoveryService,
    VPCDiscoveryService,
)
from geusemaker.services.pricing import PricingService


class InteractiveAbort(RuntimeError):
    """Raised when the user aborts the interactive flow."""


class InteractiveSessionStore:
    """Persist in-progress interactive state for resume/recovery."""

    def __init__(self, base_path: Path | None = None):
        manager = StateManager(base_path=base_path) if base_path else StateManager()
        self.path = manager.cache_path / "interactive-session.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, state: dict[str, Any]) -> Path:
        serialized = json.dumps(state, indent=2)
        self.path.write_text(serialized)
        return self.path

    def load(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text())
        except json.JSONDecodeError:
            self.path.unlink(missing_ok=True)
            return None

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


class DiscoveryFacade:
    """Thin wrapper around discovery services to simplify interactive usage."""

    def __init__(self, client_factory: AWSClientFactory, region: str):
        self._client_factory = client_factory
        self._region = region
        self._cache = DiscoveryCache()
        self._init_services()

    @property
    def region(self) -> str:
        return self._region

    def set_region(self, region: str) -> None:
        if region == self._region:
            return
        self._region = region
        self._cache = DiscoveryCache()
        self._init_services()

    def list_vpcs(self) -> list[VPCInfo]:
        return self._safe(self._vpc_service.list_vpcs)

    def list_subnets(self, vpc_id: str) -> list[SubnetInfo]:
        return self._safe(lambda: self._vpc_service.list_subnets(vpc_id))

    def list_security_groups(self, vpc_id: str) -> list[SecurityGroupInfo]:
        return self._safe(lambda: self._sg_service.list_security_groups(vpc_id))

    def list_key_pairs(self) -> list[KeyPairInfo]:
        return self._safe(self._kp_service.list_key_pairs)

    def list_file_systems(self) -> list[EFSInfo]:
        return self._safe(self._efs_service.list_file_systems)

    def validate_efs_for_subnets(self, efs_id: str, subnet_ids: list[str]) -> bool:
        """Check if EFS has mount targets in all required subnets."""
        try:
            result = self._efs_service.validate_efs_for_subnets(efs_id, subnet_ids)
            return result.is_valid
        except Exception:  # noqa: BLE001
            return False

    def _init_services(self) -> None:
        self._vpc_service = VPCDiscoveryService(self._client_factory, region=self._region, cache=self._cache)
        self._sg_service = SecurityGroupDiscoveryService(self._client_factory, region=self._region, cache=self._cache)
        self._kp_service = KeyPairDiscoveryService(self._client_factory, region=self._region, cache=self._cache)
        self._efs_service = EFSDiscoveryService(self._client_factory, region=self._region, cache=self._cache)

    def _safe(self, fn):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            messages.warning(f"Discovery failed: {exc}")
            return []


class InteractiveFlow:
    """Guide the user through building a DeploymentConfig."""

    def __init__(
        self,
        client_factory: AWSClientFactory | None = None,
        prompts: InteractivePrompts | None = None,
        dialogs: Dialogs | None = None,
        session_store: InteractiveSessionStore | None = None,
        initial_state: dict[str, Any] | None = None,
    ):
        self.client_factory = client_factory or AWSClientFactory()
        self.dialogs = dialogs or Dialogs()
        self.prompts = prompts or InteractivePrompts(dialogs=self.dialogs)
        self.session = session_store or InteractiveSessionStore()
        self._initial_state = initial_state.copy() if initial_state else {}
        self.state: dict[str, Any] = self._initial_state.copy()
        self._discovery = DiscoveryFacade(self.client_factory, region=self.state.get("region", "us-east-1"))
        pricing = PricingService(self.client_factory, region=self.state.get("region", "us-east-1"))
        self._cost_estimator = CostEstimator(
            self.client_factory,
            pricing_service=pricing,
            region=self.state.get("region", "us-east-1"),
        )
        self._force_prompt: bool = False
        self._resumed_session: bool = False

        self._steps = [
            self._step_stack_name,
            self._step_region,
            self._step_tier,
            self._step_compute_type,
            self._step_spot,
            self._step_instance_type,
            self._step_ami,
            self._step_discovery,
            self._step_cost_preview,
            self._step_confirm,
        ]

    def run(self) -> DeploymentConfig:
        """Execute the step-by-step wizard and return a config."""
        self.prompts.welcome()
        self._maybe_resume()
        idx = 0
        while idx < len(self._steps):
            try:
                self._steps[idx]()
                self.session.save(self._serializable_state())
                self._force_prompt = False
                idx += 1
            except DialogBack:
                self._force_prompt = True
                idx = max(0, idx - 1)
                continue
            except DialogAbort as exc:
                # User chose to quit; clear the saved session to avoid stale resumes
                self.session.clear()
                raise InteractiveAbort(str(exc)) from exc
        self.session.clear()
        return self._build_config()

    def _maybe_resume(self) -> None:
        saved = self.session.load()
        if not saved:
            self._resumed_session = False
            return
        try:
            if self.prompts.ask_resume(str(self.session.path)):
                self.state.update(saved)
                messages.info("Resuming saved interactive session.")
                self._resumed_session = True
            else:
                # User chose not to resume - clear session and reset state completely
                self.session.clear()
                self.state = self._initial_state.copy()
                self._resumed_session = False
        except DialogAbort as exc:
            # User chose to quit - clear session and reset state
            self.session.clear()
            self.state = self._initial_state.copy()
            self._resumed_session = False
            raise InteractiveAbort(str(exc)) from exc

    def _step_stack_name(self) -> None:
        saved_name = self.state.get("stack_name")
        # Only skip prompt if we resumed AND have a valid non-empty stack name
        if self._resumed_session and not self._force_prompt and saved_name and saved_name != "None":
            messages.info(f"Using saved stack name: {saved_name}")
            return
        self.state["stack_name"] = self.prompts.stack_name(
            default=self.state.get("stack_name") if self.state.get("stack_name") != "None" else None
        )

    def _step_region(self) -> None:
        saved_region = self.state.get("region")
        if self._resumed_session and not self._force_prompt and saved_region:
            self._discovery.set_region(saved_region)
            pricing = PricingService(self.client_factory, region=saved_region)
            self._cost_estimator = CostEstimator(self.client_factory, pricing_service=pricing, region=saved_region)
            return
        region = self.prompts.region(default=self.state.get("region"))
        if region != self._discovery.region:
            self._discovery.set_region(region)
            pricing = PricingService(self.client_factory, region=region)
            self._cost_estimator = CostEstimator(self.client_factory, pricing_service=pricing, region=region)
        self.state["region"] = region

    def _step_tier(self) -> None:
        if self._resumed_session and not self._force_prompt and self.state.get("tier"):
            return
        self.state["tier"] = self.prompts.tier(default=self.state.get("tier"))

    def _step_compute_type(self) -> None:
        if self._resumed_session and not self._force_prompt and self.state.get("compute_type"):
            return
        self.state["compute_type"] = self.prompts.compute_type(default=self.state.get("compute_type"))

    def _step_spot(self) -> None:
        if self._resumed_session and not self._force_prompt and "use_spot" in self.state:
            return
        self.state["use_spot"] = self.prompts.use_spot(default=self.state.get("use_spot", True))

    def _step_instance_type(self) -> None:
        if self._resumed_session and not self._force_prompt and self.state.get("instance_type"):
            return

        # Auto-select instance type based on compute_type if available
        if self.state.get("compute_type"):
            from geusemaker.services.compute import InstanceTypeSelector

            selector = InstanceTypeSelector(
                client_factory=self.client_factory,
                pricing_service=PricingService(self.client_factory, region=self._discovery.region),
                region=self._discovery.region,
            )

            selection = selector.select_best_instance(
                compute_type=self.state["compute_type"],
                use_spot=self.state.get("use_spot", True),
                region=self._discovery.region,
            )

            self.state["instance_type"] = selection.instance_type
            self.state["_instance_selection_reason"] = selection.reason
            self.state["_instance_selection_fallback"] = selection.fallback_occurred
        else:
            # Fallback to manual selection if compute_type not set
            self.state["instance_type"] = self.prompts.instance_type(
                default=self.state.get("instance_type"),
            )

    def _step_ami(self) -> None:
        ami_keys = ["os_type", "architecture", "ami_type", "ami_id"]
        if self._resumed_session and not self._force_prompt and all(key in self.state for key in ami_keys):
            return
        self.state["os_type"] = self.prompts.os_type(default=self.state.get("os_type"))
        self.state["architecture"] = self.prompts.architecture(default=self.state.get("architecture"))
        self.state["ami_type"] = self.prompts.ami_type(default=self.state.get("ami_type"))
        self.state["ami_id"] = self.prompts.custom_ami_id(default=self.state.get("ami_id"))

    def _step_discovery(self) -> None:
        discovery_keys = [
            "vpc_id",
            "subnet_id",
            "storage_subnet_id",
            "public_subnet_ids",
            "private_subnet_ids",
            "security_group_id",
            "efs_id",
            "create_mount_target",
            "attach_internet_gateway",
            "keypair_name",
        ]
        if self._resumed_session and not self._force_prompt and all(key in self.state for key in discovery_keys):
            return
        with spinner("Discovering AWS resources"):
            vpcs = self._discovery.list_vpcs()
        tables.resource_table(vpcs=vpcs)
        recommendations: list[str] = []
        if any(v.is_default for v in vpcs):
            recommendations.append("Default VPC is convenient for quick starts.")
        if any(not v.has_internet_gateway for v in vpcs):
            recommendations.append("Pick a VPC with an Internet Gateway for public access.")
        if recommendations:
            tables.resource_recommendations_panel(recommendations)
        selected_vpc: VPCInfo | None = None
        if vpcs:
            options = [f"{v.vpc_id} ({v.cidr_block})" for v in vpcs]
            choice = self.prompts.choose_from_list("Choose a VPC", options, default_index=1 if len(options) > 1 else 0)
            if choice > 0:
                selected_vpc = vpcs[choice - 1]
        else:
            messages.info("No existing VPCs found; a new VPC will be created.")

        if selected_vpc:
            self.state["vpc_id"] = selected_vpc.vpc_id
            with spinner("Discovering subnets and security groups"):
                subnets = self._discovery.list_subnets(selected_vpc.vpc_id)
                security_groups = self._discovery.list_security_groups(selected_vpc.vpc_id)
            tables.resource_table(subnets=subnets, security_groups=security_groups)
            public_subnets = [s for s in subnets if s.is_public]
            private_subnets = [s for s in subnets if not s.is_public]
            chosen_compute = self._select_subnet(public_subnets or subnets, "Select subnet for compute")
            chosen_storage = (
                self._select_subnet(private_subnets, "Select subnet for storage") if private_subnets else chosen_compute
            )

            chosen_sg = self._select_security_group(security_groups)

            compute_subnet = next(
                (sub for sub in subnets if chosen_compute and sub.subnet_id == chosen_compute.subnet_id),
                None,
            )
            needs_gateway = not selected_vpc.has_internet_gateway
            needs_route = bool(compute_subnet and not compute_subnet.has_internet_route)
            if needs_gateway or needs_route:
                reason_parts = []
                if needs_gateway:
                    reason_parts.append("No internet gateway is attached to the selected VPC.")
                if needs_route:
                    reason_parts.append("The chosen compute subnet has no route to an internet gateway.")
                reason = " ".join(reason_parts) if reason_parts else None
                attach_default = self.state.get("attach_internet_gateway", True)
                self.state["attach_internet_gateway"] = self.prompts.attach_internet_gateway(
                    default=bool(attach_default),
                    reason=reason,
                )
            else:
                self.state["attach_internet_gateway"] = self.state.get("attach_internet_gateway", False)

            self.state["subnet_id"] = chosen_compute.subnet_id if chosen_compute else None
            self.state["public_subnet_ids"] = [chosen_compute.subnet_id] if chosen_compute else None
            self.state["storage_subnet_id"] = chosen_storage.subnet_id if chosen_storage else None
            self.state["private_subnet_ids"] = (
                [chosen_storage.subnet_id] if chosen_storage and chosen_storage not in public_subnets else None
            )
            self.state["security_group_id"] = chosen_sg.security_group_id if chosen_sg else None
        else:
            self.state["vpc_id"] = None
            self.state["subnet_id"] = None
            self.state["storage_subnet_id"] = None
            self.state["public_subnet_ids"] = None
            self.state["private_subnet_ids"] = None
            self.state["security_group_id"] = None
            self.state["attach_internet_gateway"] = False

        # EFS selection (always runs - EFS is regional, independent of VPC creation)
        with spinner("Discovering EFS filesystems"):
            efs_filesystems = self._discovery.list_file_systems()
        tables.resource_table(efs_filesystems=efs_filesystems)
        selected_efs = self._select_efs_filesystem(efs_filesystems)

        if selected_efs:
            self.state["efs_id"] = selected_efs.file_system_id
            # Validate mount target coverage only if we have an existing storage subnet
            storage_subnet_id = self.state.get("storage_subnet_id")
            if storage_subnet_id:
                # Reusing existing VPC/subnet - validate mount targets immediately
                has_mount_target = any(mt.subnet_id == storage_subnet_id for mt in selected_efs.mount_targets)
                if not has_mount_target:
                    # Ask user if they want to create a mount target
                    if self.prompts.create_mount_target_confirm(selected_efs.file_system_id, storage_subnet_id):
                        self.state["create_mount_target"] = True
                        messages.info(
                            f"Mount target will be created for {selected_efs.file_system_id} in {storage_subnet_id}"
                        )
                    else:
                        messages.warning(
                            f"EFS {selected_efs.file_system_id} cannot be used without a mount target in the storage subnet. "
                            "A new EFS will be created instead."
                        )
                        self.state["efs_id"] = None
                        self.state["create_mount_target"] = False
                else:
                    self.state["create_mount_target"] = False
            else:
                # Creating new VPC/subnet - mount target will be created during deployment
                self.state["create_mount_target"] = True
                messages.info(
                    f"Mount target for {selected_efs.file_system_id} will be created after VPC/subnet provisioning"
                )
        else:
            self.state["efs_id"] = None
            self.state["create_mount_target"] = False

        with spinner("Discovering key pairs"):
            key_pairs = self._discovery.list_key_pairs()
        tables.resource_table(key_pairs=key_pairs)
        if key_pairs:
            options = [kp.key_name for kp in key_pairs]
            choice = self.prompts.choose_from_list(
                "Choose SSH key pair",
                options,
                default_index=0,
                allow_create_new=True,
            )
            self.state["keypair_name"] = None if choice == 0 else options[choice - 1]
        else:
            messages.info("No key pairs found; EC2 will create one if needed.")
            self.state["keypair_name"] = None

    def _step_cost_preview(self) -> None:
        config = self._build_config()
        try:
            estimate = self._cost_estimator.estimate_deployment_cost(config)
        except Exception as exc:  # noqa: BLE001
            # Cost estimation failed - show error and let user go back to fix config
            messages.warning(
                f"Cost estimation failed: {exc}\n"
                "This usually happens due to temporary AWS API issues or invalid configuration. "
                "You can go back to adjust settings or proceed without cost preview."
            )
            # Ask user if they want to continue without cost estimate
            try:
                if self.dialogs.confirm(
                    "Continue deployment without cost estimate?",
                    default=False,
                    help_text="You can proceed without cost preview or go back to adjust configuration.",
                ):
                    self.state["cost_monthly_estimate"] = None
                    return
            except DialogAbort:
                # User chose to quit
                raise
            # User wants to go back and fix the issue
            raise DialogBack() from exc

        tables.cost_preview_table(estimate)
        self.state["cost_monthly_estimate"] = float(estimate.monthly_cost)
        if not self.prompts.confirm_costs():
            raise DialogBack()

    def _step_confirm(self) -> None:
        # Show comprehensive deployment summary before confirmation
        config = self._build_config()
        cost_estimate = self.state.get("cost_monthly_estimate")
        instance_selection_reason = self.state.get("_instance_selection_reason")
        tables.deployment_summary_table(
            config,
            cost_estimate=cost_estimate,
            instance_selection_reason=instance_selection_reason,
        )

        if not self.prompts.confirm_deploy():
            raise DialogAbort("User cancelled before deployment.")

    def _select_subnet(self, subnets: list[SubnetInfo], label: str) -> SubnetInfo | None:
        if not subnets:
            return None
        options = [f"{s.subnet_id} ({s.availability_zone})" for s in subnets]
        choice = self.prompts.choose_from_list(label, options, allow_create_new=False)
        return subnets[choice]

    def _select_security_group(self, groups: list[SecurityGroupInfo]) -> SecurityGroupInfo | None:
        if not groups:
            messages.warning("No security groups found; a new one will be created.")
            return None
        options = [f"{g.name} ({g.security_group_id})" for g in groups]
        choice = self.prompts.choose_from_list("Select security group", options, default_index=0)
        return None if choice == 0 else groups[choice - 1]

    def _select_efs_filesystem(self, filesystems: list[EFSInfo]) -> EFSInfo | None:
        if not filesystems:
            messages.info("No EFS filesystems found; a new one will be created.")
            return None
        # Filter to only show available filesystems
        available_fs = [fs for fs in filesystems if fs.lifecycle_state == "available"]
        if not available_fs:
            messages.info("No available EFS filesystems found; a new one will be created.")
            return None
        options = [f"{fs.file_system_id} ({fs.name or 'unnamed'})" for fs in available_fs]
        choice = self.prompts.choose_from_list("Select EFS filesystem", options, default_index=0)
        return None if choice == 0 else available_fs[choice - 1]

    def _build_config(self) -> DeploymentConfig:
        return DeploymentConfig(
            stack_name=self.state.get("stack_name", "geusemaker"),
            tier=self.state.get("tier", "dev"),
            region=self.state.get("region", "us-east-1"),
            instance_type=self.state.get("instance_type", "t3.medium"),
            use_spot=self.state.get("use_spot", True),
            os_type=self.state.get("os_type", "ubuntu-22.04").lower(),
            architecture=self.state.get("architecture", "x86_64").lower(),
            ami_type=self.state.get("ami_type", "base").lower(),
            ami_id=self.state.get("ami_id"),
            vpc_id=self.state.get("vpc_id"),
            subnet_id=self.state.get("subnet_id"),
            attach_internet_gateway=self.state.get("attach_internet_gateway", False),
            public_subnet_ids=self.state.get("public_subnet_ids"),
            private_subnet_ids=self.state.get("private_subnet_ids"),
            storage_subnet_id=self.state.get("storage_subnet_id"),
            security_group_id=self.state.get("security_group_id"),
            efs_id=self.state.get("efs_id"),
            keypair_name=self.state.get("keypair_name"),
        )

    def _serializable_state(self) -> dict[str, Any]:
        state = self.state.copy()
        # Drop anything not JSON serializable
        for key in list(state.keys()):
            if not isinstance(state[key], (str, int, float, bool, list, dict, type(None))):
                del state[key]
        return state


__all__ = ["InteractiveFlow", "InteractiveAbort", "InteractiveSessionStore", "DiscoveryFacade"]
