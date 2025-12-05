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
    KeyPairInfo,
    SecurityGroupInfo,
    SubnetInfo,
    VPCInfo,
)
from geusemaker.services.cost import CostEstimator
from geusemaker.services.discovery import (
    DiscoveryCache,
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

    def _init_services(self) -> None:
        self._vpc_service = VPCDiscoveryService(self._client_factory, region=self._region, cache=self._cache)
        self._sg_service = SecurityGroupDiscoveryService(self._client_factory, region=self._region, cache=self._cache)
        self._kp_service = KeyPairDiscoveryService(self._client_factory, region=self._region, cache=self._cache)

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
        self.state: dict[str, Any] = initial_state.copy() if initial_state else {}
        self._discovery = DiscoveryFacade(self.client_factory, region=self.state.get("region", "us-east-1"))
        pricing = PricingService(self.client_factory, region=self.state.get("region", "us-east-1"))
        self._cost_estimator = CostEstimator(
            self.client_factory,
            pricing_service=pricing,
            region=self.state.get("region", "us-east-1"),
        )

        self._steps = [
            self._step_stack_name,
            self._step_region,
            self._step_tier,
            self._step_spot,
            self._step_instance_type,
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
                idx += 1
            except DialogBack:
                idx = max(0, idx - 1)
                continue
            except DialogAbort as exc:
                self.session.save(self._serializable_state())
                raise InteractiveAbort(str(exc)) from exc
        self.session.clear()
        return self._build_config()

    def _maybe_resume(self) -> None:
        saved = self.session.load()
        if not saved:
            return
        if self.prompts.ask_resume(str(self.session.path)):
            self.state.update(saved)
            messages.info("Resuming saved interactive session.")
        else:
            self.session.clear()

    def _step_stack_name(self) -> None:
        self.state["stack_name"] = self.prompts.stack_name(default=self.state.get("stack_name"))

    def _step_region(self) -> None:
        region = self.prompts.region(default=self.state.get("region"))
        if region != self._discovery.region:
            self._discovery.set_region(region)
            pricing = PricingService(self.client_factory, region=region)
            self._cost_estimator = CostEstimator(self.client_factory, pricing_service=pricing, region=region)
        self.state["region"] = region

    def _step_tier(self) -> None:
        self.state["tier"] = self.prompts.tier(default=self.state.get("tier"))

    def _step_spot(self) -> None:
        self.state["use_spot"] = self.prompts.use_spot(default=self.state.get("use_spot", True))

    def _step_instance_type(self) -> None:
        tier = self.state.get("tier", "dev")
        self.state["instance_type"] = self.prompts.instance_type(
            tier,
            default=self.state.get("instance_type"),
        )

    def _step_discovery(self) -> None:
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
        estimate = self._cost_estimator.estimate_deployment_cost(config)
        tables.cost_preview_table(estimate)
        self.state["cost_monthly_estimate"] = float(estimate.monthly_cost)
        if not self.prompts.confirm_costs():
            raise DialogBack()

    def _step_confirm(self) -> None:
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

    def _build_config(self) -> DeploymentConfig:
        return DeploymentConfig(
            stack_name=self.state.get("stack_name", "geusemaker"),
            tier=self.state.get("tier", "dev"),
            region=self.state.get("region", "us-east-1"),
            instance_type=self.state.get("instance_type", "t3.medium"),
            use_spot=self.state.get("use_spot", True),
            os_type=(self.state.get("os_type") or "ubuntu-22.04").lower(),
            architecture=(self.state.get("architecture") or "x86_64").lower(),
            ami_type=(self.state.get("ami_type") or "base").lower(),
            vpc_id=self.state.get("vpc_id"),
            subnet_id=self.state.get("subnet_id"),
            attach_internet_gateway=self.state.get("attach_internet_gateway", False),
            public_subnet_ids=self.state.get("public_subnet_ids"),
            private_subnet_ids=self.state.get("private_subnet_ids"),
            storage_subnet_id=self.state.get("storage_subnet_id"),
            security_group_id=self.state.get("security_group_id"),
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
