"""ALB service."""

from __future__ import annotations

from typing import Any

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


class ALBService(BaseService):
    """Manage Application Load Balancers."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._elbv2 = self._client("elbv2")

    def create_alb(
        self,
        name: str,
        subnets: list[str],
        security_groups: list[str],
        scheme: str = "internet-facing",
        tags: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Create an Application Load Balancer.

        Args:
            name: ALB name
            subnets: List of subnet IDs (minimum 2 in different AZs)
            security_groups: List of security group IDs
            scheme: "internet-facing" or "internal"
            tags: Optional resource tags

        Returns:
            CreateLoadBalancer API response with LoadBalancers list

        Raises:
            RuntimeError: If ALB creation fails
        """

        def _call() -> dict[str, Any]:
            kwargs: dict[str, Any] = {
                "Name": name,
                "Subnets": subnets,
                "SecurityGroups": security_groups,
                "Scheme": scheme,
                "Type": "application",
                "IpAddressType": "ipv4",
            }
            if tags:
                kwargs["Tags"] = tags

            return self._elbv2.create_load_balancer(**kwargs)  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def create_target_group(
        self,
        name: str,
        vpc_id: str,
        port: int = 80,
        protocol: str = "HTTP",
        health_check_path: str = "/health",
        health_check_interval: int = 30,
        health_check_timeout: int = 5,
        healthy_threshold: int = 2,
        unhealthy_threshold: int = 2,
        tags: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Create a target group for ALB.

        Args:
            name: Target group name
            vpc_id: VPC ID where targets reside
            port: Port on which targets receive traffic
            protocol: Protocol to use (HTTP or HTTPS)
            health_check_path: Health check endpoint path
            health_check_interval: Seconds between health checks
            health_check_timeout: Health check timeout in seconds
            healthy_threshold: Consecutive successes to mark healthy
            unhealthy_threshold: Consecutive failures to mark unhealthy
            tags: Optional resource tags

        Returns:
            CreateTargetGroup API response with TargetGroups list

        Raises:
            RuntimeError: If target group creation fails
        """

        def _call() -> dict[str, Any]:
            kwargs: dict[str, Any] = {
                "Name": name,
                "Protocol": protocol,
                "Port": port,
                "VpcId": vpc_id,
                "HealthCheckProtocol": protocol,
                "HealthCheckPath": health_check_path,
                "HealthCheckIntervalSeconds": health_check_interval,
                "HealthCheckTimeoutSeconds": health_check_timeout,
                "HealthyThresholdCount": healthy_threshold,
                "UnhealthyThresholdCount": unhealthy_threshold,
                "TargetType": "instance",
            }
            if tags:
                kwargs["Tags"] = tags

            return self._elbv2.create_target_group(**kwargs)  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def create_listener(
        self,
        load_balancer_arn: str,
        target_group_arn: str,
        port: int = 80,
        protocol: str = "HTTP",
    ) -> dict[str, Any]:
        """
        Create a listener for ALB that forwards to a target group.

        Args:
            load_balancer_arn: ARN of the load balancer
            target_group_arn: ARN of the target group
            port: Port on which the load balancer listens
            protocol: Protocol for connections (HTTP or HTTPS)

        Returns:
            CreateListener API response with Listeners list

        Raises:
            RuntimeError: If listener creation fails
        """

        def _call() -> dict[str, Any]:
            return self._elbv2.create_listener(  # type: ignore[no-any-return]
                LoadBalancerArn=load_balancer_arn,
                Protocol=protocol,
                Port=port,
                DefaultActions=[
                    {
                        "Type": "forward",
                        "TargetGroupArn": target_group_arn,
                    },
                ],
            )

        return self._safe_call(_call)

    def register_targets(
        self,
        target_group_arn: str,
        instance_ids: list[str],
        port: int | None = None,
    ) -> dict[str, Any]:
        """
        Register EC2 instances as targets in a target group.

        Args:
            target_group_arn: ARN of the target group
            instance_ids: List of EC2 instance IDs to register
            port: Optional port override (uses target group port if not specified)

        Returns:
            RegisterTargets API response

        Raises:
            RuntimeError: If target registration fails
        """

        def _call() -> dict[str, Any]:
            targets = [{"Id": instance_id} for instance_id in instance_ids]
            if port is not None:
                for target in targets:
                    target["Port"] = port

            return self._elbv2.register_targets(  # type: ignore[no-any-return]
                TargetGroupArn=target_group_arn,
                Targets=targets,
            )

        return self._safe_call(_call)

    def describe_target_health(
        self,
        target_group_arn: str,
        instance_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Describe health status of registered targets.

        Args:
            target_group_arn: ARN of the target group
            instance_ids: Optional list of specific instance IDs to check

        Returns:
            DescribeTargetHealth API response with TargetHealthDescriptions list

        Raises:
            RuntimeError: If health check fails
        """

        def _call() -> dict[str, Any]:
            kwargs: dict[str, Any] = {"TargetGroupArn": target_group_arn}
            if instance_ids:
                kwargs["Targets"] = [{"Id": instance_id} for instance_id in instance_ids]

            return self._elbv2.describe_target_health(**kwargs)  # type: ignore[no-any-return]

        return self._safe_call(_call)

    def wait_for_healthy(
        self,
        target_group_arn: str,
        instance_ids: list[str],
        max_attempts: int = 60,
        delay: int = 5,
    ) -> None:
        """
        Wait for registered targets to become healthy using boto3 waiter.

        Args:
            target_group_arn: ARN of the target group
            instance_ids: List of instance IDs to monitor
            max_attempts: Maximum polling attempts (default: 60)
            delay: Seconds between polling attempts (default: 5)

        Raises:
            RuntimeError: If targets don't become healthy within max_attempts
        """

        def _call() -> None:
            from botocore.exceptions import WaiterError  # type: ignore[import-untyped]

            try:
                waiter = self._elbv2.get_waiter("target_in_service")
                # Wait for each target to become healthy
                for instance_id in instance_ids:
                    waiter.wait(
                        TargetGroupArn=target_group_arn,
                        Targets=[{"Id": instance_id}],
                        WaiterConfig={
                            "Delay": delay,
                            "MaxAttempts": max_attempts,
                        },
                    )
            except WaiterError as exc:
                # Provide detailed error message on timeout or failure
                resp = self.describe_target_health(target_group_arn, instance_ids)
                health_descriptions = resp.get("TargetHealthDescriptions", [])
                error_details = []

                for desc in health_descriptions:
                    state = desc.get("TargetHealth", {}).get("State", "unknown")
                    reason = desc.get("TargetHealth", {}).get("Reason", "Unknown")
                    description = desc.get("TargetHealth", {}).get("Description", "")
                    target_id = desc.get("Target", {}).get("Id", "unknown")
                    error_details.append(f"Target {target_id}: {state} ({reason} - {description})")

                raise RuntimeError(
                    f"Targets did not become healthy within {max_attempts * delay}s. "
                    f"Details: {'; '.join(error_details)}"
                ) from exc

        self._safe_call(_call)

    def create_https_listener(
        self,
        load_balancer_arn: str,
        target_group_arn: str,
        certificate_arn: str,
        port: int = 443,
    ) -> dict[str, Any]:
        """
        Create an HTTPS listener for ALB with ACM certificate.

        Args:
            load_balancer_arn: ARN of the load balancer
            target_group_arn: ARN of the target group
            certificate_arn: ARN of the ACM certificate
            port: Port on which the load balancer listens (default 443)

        Returns:
            CreateListener API response with Listeners list

        Raises:
            RuntimeError: If HTTPS listener creation fails
        """

        def _call() -> dict[str, Any]:
            return self._elbv2.create_listener(  # type: ignore[no-any-return]
                LoadBalancerArn=load_balancer_arn,
                Protocol="HTTPS",
                Port=port,
                Certificates=[{"CertificateArn": certificate_arn}],
                DefaultActions=[
                    {
                        "Type": "forward",
                        "TargetGroupArn": target_group_arn,
                    },
                ],
            )

        return self._safe_call(_call)

    def create_redirect_listener(
        self,
        load_balancer_arn: str,
        port: int = 80,
    ) -> dict[str, Any]:
        """
        Create an HTTP listener that redirects all traffic to HTTPS.

        Args:
            load_balancer_arn: ARN of the load balancer
            port: Port on which the load balancer listens (default 80)

        Returns:
            CreateListener API response with Listeners list

        Raises:
            RuntimeError: If redirect listener creation fails
        """

        def _call() -> dict[str, Any]:
            return self._elbv2.create_listener(  # type: ignore[no-any-return]
                LoadBalancerArn=load_balancer_arn,
                Protocol="HTTP",
                Port=port,
                DefaultActions=[
                    {
                        "Type": "redirect",
                        "RedirectConfig": {
                            "Protocol": "HTTPS",
                            "Port": "443",
                            "StatusCode": "HTTP_301",
                        },
                    }
                ],
            )

        return self._safe_call(_call)


__all__ = ["ALBService"]
