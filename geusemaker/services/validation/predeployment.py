"""Pre-deployment validation service."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from botocore.exceptions import (  # type: ignore[import-untyped]
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
)

from geusemaker.infra import AWSClientFactory
from geusemaker.infra.state import StateManager
from geusemaker.models import DeploymentConfig
from geusemaker.models.validation import ValidationCheck, ValidationReport
from geusemaker.services.base import BaseService

LOGGER = logging.getLogger(__name__)


class PreDeploymentValidator(BaseService):
    """Run pre-deployment checks before provisioning resources."""

    REQUIRED_ACTIONS = [
        "ec2:RunInstances",
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:CreateSecurityGroup",
        "ec2:DescribeSecurityGroups",
        "elasticfilesystem:CreateFileSystem",
        "elasticfilesystem:DescribeFileSystems",
        "elasticloadbalancing:DescribeLoadBalancers",
        "servicequotas:GetServiceQuota",
        "sts:GetCallerIdentity",
    ]

    def __init__(
        self,
        client_factory: AWSClientFactory,
        region: str = "us-east-1",
        state_manager: StateManager | None = None,
        sts_client: object | None = None,
        iam_client: object | None = None,
        service_quotas_client: object | None = None,
        ec2_client: object | None = None,
        efs_client: object | None = None,
        elbv2_client: object | None = None,
    ):
        factory = client_factory or AWSClientFactory()
        super().__init__(factory, region)
        self._state_manager = state_manager or StateManager()
        self._overrides: dict[str, object | None] = {
            "sts": sts_client,
            "iam": iam_client,
            "service-quotas": service_quotas_client,
            "ec2": ec2_client,
            "efs": efs_client,
            "elbv2": elbv2_client,
        }
        self._available_regions: list[str] | None = None

    def validate(self, config: DeploymentConfig) -> ValidationReport:
        """Run all pre-deployment checks."""
        report = ValidationReport()

        credentials_check, identity_arn = self._validate_credentials()
        report.add(credentials_check)

        report.add(self._validate_permissions(identity_arn))
        report.add(self._validate_quotas())
        report.add(self._validate_region_services())
        report.add(self._validate_config(config))
        report.add(self._check_naming_conflicts(config.stack_name, config.vpc_id))
        for vpc_check in self._validate_existing_vpc(config):
            report.add(vpc_check)

        return report

    def _validate_credentials(self) -> tuple[ValidationCheck, str | None]:
        """Validate AWS credentials by calling STS."""
        check_name = "credentials"
        try:
            identity = self._safe_call(lambda: self._sts_client().get_caller_identity())
            account = identity.get("Account")
            arn = identity.get("Arn")
            message = f"Credentials valid for account {account}"
            details = f"{arn}" if arn else None
            return (
                ValidationCheck(
                    check_name=check_name,
                    passed=True,
                    message=message,
                    details=details,
                    severity="info",
                ),
                arn,
            )
        except (ClientError, BotoCoreError, RuntimeError) as exc:
            LOGGER.debug("Credential validation failed: %s", exc)
            return (
                ValidationCheck(
                    check_name=check_name,
                    passed=False,
                    message=f"Credential validation failed: {exc}",
                    remediation="Configure AWS credentials or refresh expired tokens.",
                    severity="error",
                ),
                None,
            )

    def _validate_permissions(self, identity_arn: str | None) -> ValidationCheck:
        """Validate IAM permissions using policy simulation when possible."""
        check_name = "permissions"
        if not identity_arn:
            return ValidationCheck(
                check_name=check_name,
                passed=False,
                message="Permission simulation skipped because identity is unknown.",
                remediation="Resolve credentials before validating permissions.",
                severity="warning",
            )
        try:
            response = self._safe_call(
                lambda: self._iam_client().simulate_principal_policy(
                    PolicySourceArn=identity_arn,
                    ActionNames=self.REQUIRED_ACTIONS,
                ),
            )
            evaluation_results = response.get("EvaluationResults", [])
            if not evaluation_results:
                return ValidationCheck(
                    check_name=check_name,
                    passed=False,
                    message="Permission validation unavailable (no evaluation results returned).",
                    remediation="Ensure iam:SimulatePrincipalPolicy is allowed or validate manually.",
                    severity="warning",
                )

            denied_actions: list[str] = []
            implicitly_denied: list[str] = []
            for result in evaluation_results:
                decision = str(result.get("EvalDecision", "")).lower()
                action = result.get("EvalActionName", "unknown")
                if decision == "allowed":
                    continue
                if decision == "implicitdeny":
                    implicitly_denied.append(action)
                    continue
                denied_actions.append(action)

            if denied_actions or implicitly_denied:
                missing = denied_actions + implicitly_denied
                decision_hint = ""
                if denied_actions and implicitly_denied:
                    decision_hint = f" (explicitly denied: {', '.join(denied_actions)}; implicit denies: {', '.join(implicitly_denied)})"
                elif denied_actions:
                    decision_hint = f" (explicitly denied: {', '.join(denied_actions)})"
                elif implicitly_denied:
                    decision_hint = f" (implicit denies: {', '.join(implicitly_denied)})"
                return ValidationCheck(
                    check_name=check_name,
                    passed=False,
                    message="Missing required permissions." + decision_hint,
                    details=", ".join(missing),
                    remediation="Grant the required IAM permissions for deployment actions.",
                    severity="error",
                )
            return ValidationCheck(
                check_name=check_name,
                passed=True,
                message="IAM permissions validated for required actions.",
                severity="info",
            )
        except (ClientError, BotoCoreError, RuntimeError) as exc:
            LOGGER.debug("Permission validation could not complete: %s", exc)
            return ValidationCheck(
                check_name=check_name,
                passed=False,
                message=f"Permission validation unavailable: {exc}",
                remediation="Ensure iam:SimulatePrincipalPolicy is allowed or validate manually.",
                severity="warning",
            )

    def _validate_quotas(self) -> ValidationCheck:
        """Check select service quotas to ensure capacity."""
        check_name = "quotas"
        quotas = [
            ("ec2", "L-1216C47A", "EC2 standard instances"),
            ("ec2", "L-0263D0A3", "Elastic IP addresses"),
            ("elasticfilesystem", "L-6C5AE51C", "EFS file systems"),
        ]
        failures: list[str] = []
        warnings: list[str] = []
        try:
            sq = self._service_quotas_client()
            for service_code, quota_code, label in quotas:
                try:
                    _sc, _qc = service_code, quota_code
                    quota = self._safe_call(
                        lambda: sq.get_service_quota(
                            ServiceCode=_sc,
                            QuotaCode=_qc,
                        ),
                    )
                    if quota.get("Quota", {}).get("Value", 0) < 1:
                        failures.append(f"{label} quota too low")
                except (ClientError, BotoCoreError, RuntimeError) as exc:
                    # NoSuchResourceException and similar API errors are warnings, not failures
                    # The quota might exist but the API doesn't recognize this quota code
                    exc_str = str(exc)
                    if "NoSuchResourceException" in exc_str or "does not exist" in exc_str:
                        warnings.append(f"{label} quota check skipped (API limitation)")
                    else:
                        warnings.append(f"{label} check unavailable: {exc}")
        except (ClientError, BotoCoreError, RuntimeError, EndpointConnectionError) as exc:
            LOGGER.debug("Quota validation unavailable: %s", exc)
            return ValidationCheck(
                check_name=check_name,
                passed=True,  # Pass with warning when service unavailable
                message="Quota validation skipped (Service Quotas API unavailable).",
                details=str(exc),
                remediation="Verify service quotas manually if needed.",
                severity="warning",
            )

        # Hard failures (quota too low) block deployment
        if failures:
            return ValidationCheck(
                check_name=check_name,
                passed=False,
                message="Quota checks failed.",
                details="; ".join(failures),
                remediation="Request quota increases before deployment.",
                severity="error",
            )

        # Warnings (API issues) don't block deployment
        if warnings:
            return ValidationCheck(
                check_name=check_name,
                passed=True,
                message="Quota checks passed with warnings.",
                details="; ".join(warnings),
                remediation="Verify quotas manually if deployment fails.",
                severity="warning",
            )

        return ValidationCheck(
            check_name=check_name,
            passed=True,
            message="Quotas sufficient for deployment.",
            severity="info",
        )

    def _validate_region_services(self) -> ValidationCheck:
        """Validate region and required service availability."""
        check_name = "region_services"
        issues: list[str] = []
        try:
            available_regions = self._get_available_regions()
            if self.region not in available_regions:
                return ValidationCheck(
                    check_name=check_name,
                    passed=False,
                    message=f"Region {self.region} is not available.",
                    remediation="Choose a supported AWS region.",
                    severity="error",
                )
        except (ClientError, BotoCoreError, RuntimeError) as exc:
            return ValidationCheck(
                check_name=check_name,
                passed=False,
                message=f"Unable to verify region availability: {exc}",
                remediation="Check AWS connectivity and credentials.",
                severity="error",
            )

        for label, fn in (
            ("EC2", lambda: self._ec2_client().describe_availability_zones()),
            ("EFS", lambda: self._efs_client().describe_file_systems(MaxItems=1)),
            ("ELBv2", lambda: self._elbv2_client().describe_load_balancers(PageSize=1)),
        ):
            try:
                self._safe_call(fn)
            except (ClientError, BotoCoreError, RuntimeError, EndpointConnectionError) as exc:
                issues.append(f"{label} unavailable: {exc}")

        if issues:
            return ValidationCheck(
                check_name=check_name,
                passed=False,
                message="Service availability issues detected.",
                details="; ".join(issues),
                remediation="Select a different region or enable the required services.",
                severity="error",
            )

        return ValidationCheck(
            check_name=check_name,
            passed=True,
            message=f"Region {self.region} supports required services.",
            severity="info",
        )

    def _validate_config(self, config: DeploymentConfig) -> ValidationCheck:
        """Validate deployment configuration values."""
        check_name = "config"
        errors: list[str] = []

        if not re.match(r"^[a-zA-Z][a-zA-Z0-9-]*$", config.stack_name):
            errors.append("Stack name must start with a letter and contain only letters, numbers, and dashes.")

        if config.tier not in {"dev", "automation", "gpu"}:
            errors.append("Tier must be one of dev, automation, gpu.")

        try:
            available_regions = self._get_available_regions()
            if config.region not in available_regions:
                errors.append(f"Region {config.region} is not valid or enabled.")
        except (ClientError, BotoCoreError, RuntimeError):
            errors.append("Could not verify region validity.")

        try:
            self._safe_call(
                lambda: self._ec2_client().describe_instance_types(
                    InstanceTypes=[config.instance_type],
                ),
            )
        except (ClientError, BotoCoreError, RuntimeError):
            errors.append(f"Instance type {config.instance_type} not available in {config.region}.")

        if errors:
            return ValidationCheck(
                check_name=check_name,
                passed=False,
                message="Configuration validation failed.",
                details="; ".join(errors),
                remediation="Update the deployment config to use supported values.",
                severity="error",
            )

        return ValidationCheck(
            check_name=check_name,
            passed=True,
            message="Configuration values are valid.",
            severity="info",
        )

    def _check_naming_conflicts(self, stack_name: str, vpc_id: str | None = None) -> ValidationCheck:
        """Check for naming conflicts with existing deployments/resources."""
        check_name = "naming_conflicts"
        conflicts: list[str] = []

        existing_state = self._state_manager.deployments_path / f"{stack_name}.json"
        if existing_state.exists():
            conflicts.append("Local deployment state already exists with this name.")

        try:
            vpcs = self._safe_call(
                lambda: self._ec2_client().describe_vpcs(
                    Filters=[{"Name": "tag:Name", "Values": [stack_name]}],
                ),
            )
            matching_vpcs = vpcs.get("Vpcs", [])
            if vpc_id:
                matching_vpcs = [vpc for vpc in matching_vpcs if vpc.get("VpcId") != vpc_id]
            if matching_vpcs:
                conflicts.append("VPC with matching Name tag already exists.")
        except (ClientError, BotoCoreError, RuntimeError):
            conflicts.append("Could not verify VPC naming conflicts.")

        if conflicts:
            return ValidationCheck(
                check_name=check_name,
                passed=False,
                message="Naming conflicts detected.",
                details="; ".join(conflicts),
                remediation="Use a unique stack name or clean up existing resources.",
                severity="error",
            )

        return ValidationCheck(
            check_name=check_name,
            passed=True,
            message="No naming conflicts detected.",
            severity="info",
        )

    def _validate_existing_vpc(self, config: DeploymentConfig) -> list[ValidationCheck]:
        """Validate an existing VPC for routing, tagging, and ACL defaults."""
        if not config.vpc_id:
            return []

        ec2 = self._ec2_client()
        checks: list[ValidationCheck] = []

        try:
            vpc = self._safe_call(
                lambda: ec2.describe_vpcs(VpcIds=[config.vpc_id])["Vpcs"][0],
            )
        except (ClientError, BotoCoreError, RuntimeError) as exc:
            return [
                ValidationCheck(
                    check_name="vpc_exists",
                    passed=False,
                    message=f"VPC {config.vpc_id} not found or inaccessible: {exc}",
                    remediation="Provide a reachable VPC id or omit vpc_id to let GeuseMaker create one.",
                ),
            ]

        state = vpc.get("State", "unknown")
        checks.append(
            ValidationCheck(
                check_name="vpc_state",
                passed=state == "available",
                message=f"VPC is in {state} state.",
                remediation="Wait for the VPC to become available.",
                severity="error" if state != "available" else "info",
            ),
        )

        tags = {tag["Key"]: tag["Value"] for tag in vpc.get("Tags", []) if "Key" in tag and "Value" in tag}
        missing_tag_keys: list[str] = []
        if "geusemaker:deployment" not in tags:
            missing_tag_keys.append("geusemaker:deployment")
        if "geusemaker:tier" not in tags and config.tier:
            missing_tag_keys.append("geusemaker:tier")
        checks.append(
            ValidationCheck(
                check_name="vpc_tags",
                passed=len(missing_tag_keys) == 0,
                message="VPC tags present."
                if not missing_tag_keys
                else f"VPC missing tags: {', '.join(missing_tag_keys)}",
                remediation="GeuseMaker will tag the VPC during configuration.",
                severity="warning" if missing_tag_keys else "info",
            ),
        )

        attach_requested = bool(getattr(config, "attach_internet_gateway", False))
        igws = self._safe_call(
            lambda: ec2.describe_internet_gateways(
                Filters=[{"Name": "attachment.vpc-id", "Values": [config.vpc_id]}],
            ),
        ).get("InternetGateways", [])
        has_igw = len(igws) > 0
        if has_igw:
            checks.append(
                ValidationCheck(
                    check_name="vpc_internet_gateway",
                    passed=True,
                    message="Internet gateway is attached.",
                    severity="info",
                ),
            )
        elif attach_requested:
            checks.append(
                ValidationCheck(
                    check_name="vpc_internet_gateway",
                    passed=False,
                    message="No internet gateway attached; will attach during deployment (--attach-internet-gateway).",
                    remediation="Ensure permissions allow creating and attaching an internet gateway.",
                    severity="warning",
                ),
            )
        else:
            checks.append(
                ValidationCheck(
                    check_name="vpc_internet_gateway",
                    passed=False,
                    message="No internet gateway attached to the VPC.",
                    remediation="Attach an internet gateway or rerun deploy with --attach-internet-gateway.",
                ),
            )

        subnets_resp = self._safe_call(
            lambda: ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [config.vpc_id]}]),
        )
        subnet_ids = [subnet["SubnetId"] for subnet in subnets_resp.get("Subnets", [])]
        checks.append(
            ValidationCheck(
                check_name="vpc_subnets",
                passed=len(subnet_ids) > 0,
                message=f"{len(subnet_ids)} subnets discovered." if subnet_ids else "No subnets found in the VPC.",
                remediation="Create at least one subnet or omit vpc_id for automatic creation.",
            ),
        )

        if config.public_subnet_ids:
            missing = [sid for sid in config.public_subnet_ids if sid not in subnet_ids]
            checks.append(
                ValidationCheck(
                    check_name="vpc_public_subnets",
                    passed=len(missing) == 0,
                    message="All requested public subnets are present."
                    if not missing
                    else f"Missing public subnets: {', '.join(missing)}",
                    remediation="Ensure the subnet ids belong to the selected VPC.",
                ),
            )
        if config.private_subnet_ids:
            missing = [sid for sid in config.private_subnet_ids if sid not in subnet_ids]
            checks.append(
                ValidationCheck(
                    check_name="vpc_private_subnets",
                    passed=len(missing) == 0,
                    message="All requested private subnets are present."
                    if not missing
                    else f"Missing private subnets: {', '.join(missing)}",
                    remediation="Ensure the subnet ids belong to the selected VPC.",
                ),
            )

        igw_routes = self._igw_routed_subnets(ec2, config.vpc_id)
        has_public_route = bool(igw_routes) or self._main_route_has_igw(ec2, config.vpc_id)
        if has_public_route:
            checks.append(
                ValidationCheck(
                    check_name="vpc_routes",
                    passed=True,
                    message="Subnets have routes to the internet gateway.",
                    details=f"Subnets with IGW routes: {', '.join(sorted(igw_routes))}" if igw_routes else None,
                    severity="info",
                ),
            )
        elif attach_requested:
            checks.append(
                ValidationCheck(
                    check_name="vpc_routes",
                    passed=False,
                    message="No subnet route to an internet gateway detected; routes will be configured during deployment.",
                    remediation="Confirm routing changes are acceptable or preconfigure routes manually.",
                    severity="warning",
                ),
            )
        else:
            checks.append(
                ValidationCheck(
                    check_name="vpc_routes",
                    passed=False,
                    message="No subnet route to an internet gateway detected.",
                    remediation="Associate a route table with 0.0.0.0/0 -> IGW for public subnets or enable --attach-internet-gateway.",
                ),
            )

        if config.storage_subnet_id:
            storage_ok = config.storage_subnet_id in subnet_ids
            checks.append(
                ValidationCheck(
                    check_name="vpc_storage_subnet",
                    passed=storage_ok,
                    message="Storage subnet is present in the VPC."
                    if storage_ok
                    else f"Storage subnet {config.storage_subnet_id} not found in VPC.",
                    remediation="Provide a storage subnet id from the target VPC.",
                ),
            )

        nacl_check = self._nacl_tag_check(ec2, config.vpc_id, config)
        if nacl_check is not None:
            checks.append(nacl_check)

        if config.security_group_id:
            checks.extend(
                self._validate_security_group(
                    ec2,
                    config.security_group_id,
                    config.vpc_id,
                    vpc.get("CidrBlock"),
                ),
            )

        return checks

    def _validate_security_group(
        self,
        ec2: object,
        security_group_id: str,
        vpc_id: str,
        vpc_cidr: str | None,
    ) -> list[ValidationCheck]:
        """Validate that a reused security group matches VPC and port needs."""
        checks: list[ValidationCheck] = []
        try:
            sg = self._safe_call(
                lambda: ec2.describe_security_groups(GroupIds=[security_group_id])["SecurityGroups"][0],
            )
        except (ClientError, BotoCoreError, RuntimeError) as exc:
            return [
                ValidationCheck(
                    check_name="security_group_exists",
                    passed=False,
                    message=f"Security group {security_group_id} not found or inaccessible: {exc}",
                    remediation="Provide a valid security group id in the selected VPC.",
                ),
            ]

        same_vpc = sg.get("VpcId") == vpc_id
        checks.append(
            ValidationCheck(
                check_name="security_group_vpc",
                passed=same_vpc,
                message="Security group belongs to selected VPC."
                if same_vpc
                else "Security group is not in the selected VPC.",
                remediation="Use a security group in the target VPC or omit to let GeuseMaker create one.",
                severity="error" if not same_vpc else "info",
            ),
        )

        required_ports = [
            (22, "SSH"),
            (80, "HTTP"),
            (5678, "n8n"),
            (2049, "EFS"),
        ]
        ingress = sg.get("IpPermissions", [])
        missing_ports = [
            f"{port} ({label})" for port, label in required_ports if not self._port_allowed(ingress, port, vpc_cidr)
        ]
        checks.append(
            ValidationCheck(
                check_name="security_group_ports",
                passed=len(missing_ports) == 0,
                message="Required ingress ports are open."
                if not missing_ports
                else f"Missing ingress for: {', '.join(missing_ports)}",
                remediation="Add ingress rules for SSH (22), HTTP (80), n8n (5678), and EFS (2049) or omit to auto-create.",
                severity="error" if missing_ports else "info",
            ),
        )
        return checks

    def _port_allowed(self, permissions: list[dict[str, object]], port: int, vpc_cidr: str | None) -> bool:
        """Return True if any rule allows the given port."""
        for perm in permissions or []:
            proto = perm.get("IpProtocol")
            if proto not in ("-1", "tcp"):
                continue
            from_port = perm.get("FromPort")
            to_port = perm.get("ToPort")
            if from_port is not None and port < int(from_port):
                continue
            if to_port is not None and port > int(to_port):
                continue
            cidrs = [rng.get("CidrIp") for rng in perm.get("IpRanges", []) if isinstance(rng, dict)]
            if "0.0.0.0/0" in cidrs:
                return True
            if vpc_cidr and vpc_cidr in cidrs:
                return True
            # Allow group-based rules as permissive (assume reachable within VPC)
            if perm.get("UserIdGroupPairs"):
                return True
        return False

    def _igw_routed_subnets(self, ec2: object, vpc_id: str) -> set[str]:
        """Return subnets associated to a route table that has an IGW route."""
        response = self._safe_call(
            lambda: ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]),
        )
        igw_subnets: set[str] = set()
        for rt in response.get("RouteTables", []):
            has_igw_route = any(
                route.get("GatewayId", "").startswith("igw-") and route.get("State") != "blackhole"
                for route in rt.get("Routes", [])
            )
            if not has_igw_route:
                continue
            for assoc in rt.get("Associations", []):
                subnet_id = assoc.get("SubnetId")
                if subnet_id:
                    igw_subnets.add(subnet_id)
        return igw_subnets

    def _main_route_has_igw(self, ec2: object, vpc_id: str) -> bool:
        """Return True if the main route table has an IGW route."""
        response = self._safe_call(
            lambda: ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]),
        )
        for rt in response.get("RouteTables", []):
            is_main = any(assoc.get("Main") for assoc in rt.get("Associations", []))
            if not is_main:
                continue
            return any(
                route.get("GatewayId", "").startswith("igw-") and route.get("State") != "blackhole"
                for route in rt.get("Routes", [])
            )
        return False

    def _nacl_tag_check(self, ec2: object, vpc_id: str, config: DeploymentConfig) -> ValidationCheck | None:
        """Validate default NACL tagging to align with deployment metadata."""
        nacls = self._safe_call(
            lambda: ec2.describe_network_acls(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]),
        ).get("NetworkAcls", [])
        default_nacl = next((nacl for nacl in nacls if nacl.get("IsDefault")), None)
        if default_nacl is None:
            return ValidationCheck(
                check_name="vpc_network_acl",
                passed=False,
                message="Default network ACL not found.",
                remediation="Ensure the VPC has a default network ACL before deployment.",
            )

        tags = {tag["Key"]: tag["Value"] for tag in default_nacl.get("Tags", []) if "Key" in tag and "Value" in tag}
        missing = []
        if "geusemaker:deployment" not in tags:
            missing.append("geusemaker:deployment")
        if "geusemaker:tier" not in tags and config.tier:
            missing.append("geusemaker:tier")

        return ValidationCheck(
            check_name="vpc_network_acl_tags",
            passed=len(missing) == 0,
            message="Default network ACL is tagged for GeuseMaker."
            if not missing
            else f"Default network ACL missing tags: {', '.join(missing)}",
            remediation="GeuseMaker will tag the default network ACL during configuration.",
            severity="warning" if missing else "info",
        )

    def _get_available_regions(self) -> list[str]:
        if self._available_regions is None:
            response = self._safe_call(
                lambda: self._ec2_client().describe_regions(AllRegions=False),
            )
            self._available_regions = [entry["RegionName"] for entry in response.get("Regions", [])]
        return self._available_regions

    def _client_with_override(self, service_name: str) -> object:
        override = self._overrides.get(service_name)
        return override if override is not None else self._client(service_name)

    def _sts_client(self) -> object:
        return self._client_with_override("sts")

    def _iam_client(self) -> object:
        return self._client_with_override("iam")

    def _service_quotas_client(self) -> object:
        return self._client_with_override("service-quotas")

    def _ec2_client(self) -> object:
        return self._client_with_override("ec2")

    def _efs_client(self) -> object:
        return self._client_with_override("efs")

    def _elbv2_client(self) -> object:
        return self._client_with_override("elbv2")

    def _safe_call(self, fn: Callable[[], object]) -> object:  # type: ignore[override]
        """Wrap boto calls and re-raise as RuntimeError for uniform handling."""
        try:
            return super()._safe_call(fn)
        except RuntimeError:
            raise


__all__ = ["PreDeploymentValidator"]
