"""Production Spot instance automation backed by EC2 Auto Scaling."""

from __future__ import annotations

import base64
import io
import json
import time
import zipfile
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from geusemaker.infra import AWSClientFactory
from geusemaker.services.base import BaseService


@dataclass(frozen=True)
class SpotAutomationResources:
    """AWS resources created for a production Spot worker."""

    launch_template_id: str
    auto_scaling_group_name: str
    instance_id: str
    log_group_name: str
    event_rule_names: tuple[str, ...]
    lease_table_name: str
    lifecycle_hook_names: tuple[str, ...]
    coordinator_function_name: str
    coordinator_role_name: str


class SpotAutomationService(BaseService):
    """Create and manage the low-footprint production Spot control plane."""

    def __init__(self, client_factory: AWSClientFactory, region: str = "us-east-1"):
        super().__init__(client_factory, region)
        self._ec2 = self._client("ec2")
        self._autoscaling = self._client("autoscaling")
        self._events = self._client("events")
        self._logs = self._client("logs")
        self._dynamodb = self._client("dynamodb")
        self._iam = self._client("iam")
        self._lambda = self._client("lambda")

    def create(
        self,
        *,
        stack_name: str,
        image_id: str,
        instance_type: str,
        subnet_ids: list[str],
        security_group_ids: list[str],
        instance_profile_name: str,
        user_data: bytes,
        block_device_mappings: list[dict[str, Any]],
        tags: dict[str, str],
        key_name: str | None = None,
        timeout_seconds: int = 600,
    ) -> SpotAutomationResources:
        """Create a desired-capacity-one Spot ASG and wait for its first instance."""
        template_name = f"{stack_name}-spot-lt"[:128]
        asg_name = f"{stack_name}-spot-asg"
        tag_list = [{"Key": key, "Value": value} for key, value in tags.items()]
        template_data: dict[str, Any] = {
            "ImageId": image_id,
            "InstanceType": instance_type,
            "SecurityGroupIds": security_group_ids,
            "IamInstanceProfile": {"Name": instance_profile_name},
            "UserData": base64.b64encode(user_data).decode("ascii"),
            "BlockDeviceMappings": block_device_mappings,
            "MetadataOptions": {
                "HttpEndpoint": "enabled",
                "HttpTokens": "required",
                "HttpPutResponseHopLimit": 1,
            },
            "TagSpecifications": [
                {"ResourceType": "instance", "Tags": tag_list},
                {"ResourceType": "network-interface", "Tags": tag_list},
            ],
        }
        if key_name:
            template_data["KeyName"] = key_name

        launch_template_id: str | None = None
        control: dict[str, Any] = {
            "log_group_name": f"/geusemaker/{stack_name}/spot-events",
            "rule_names": (
                f"{stack_name[:44]}-spot-interruption",
                f"{stack_name[:50]}-asg-lifecycle",
            ),
            "lease_table_name": f"{stack_name}-spot-lease"[:255],
            "hook_names": (f"{stack_name[:42]}-launch", f"{stack_name[:39]}-terminate"),
            "function_name": f"{stack_name}-spot-coordinator"[:64],
            "role_name": f"{stack_name}-spot-coordinator"[:64],
        }
        try:
            response = self._ec2.create_launch_template(
                LaunchTemplateName=template_name,
                VersionDescription="GeuseMaker production Spot automation",
                LaunchTemplateData=template_data,
                TagSpecifications=[{"ResourceType": "launch-template", "Tags": tag_list}],
            )
            launch_template_id = response["LaunchTemplate"]["LaunchTemplateId"]

            self._autoscaling.create_auto_scaling_group(
                AutoScalingGroupName=asg_name,
                MinSize=1,
                MaxSize=2,
                DesiredCapacity=1,
                DefaultInstanceWarmup=300,
                HealthCheckType="EC2",
                HealthCheckGracePeriod=600,
                VPCZoneIdentifier=",".join(subnet_ids),
                CapacityRebalance=True,
                MixedInstancesPolicy={
                    "LaunchTemplate": {
                        "LaunchTemplateSpecification": {
                            "LaunchTemplateId": launch_template_id,
                            "Version": "$Latest",
                        },
                        "Overrides": [{"InstanceType": instance_type}],
                    },
                    "InstancesDistribution": {
                        "OnDemandBaseCapacity": 0,
                        "OnDemandPercentageAboveBaseCapacity": 0,
                        "SpotAllocationStrategy": "price-capacity-optimized",
                    },
                },
                Tags=[
                    {"Key": key, "Value": value, "PropagateAtLaunch": True, "ResourceType": "auto-scaling-group"}
                    for key, value in tags.items()
                ],
            )
            control = self._create_failover_control_plane(stack_name, asg_name, tags)
            instance_id = self.wait_for_instance(asg_name, timeout_seconds=timeout_seconds)
        except Exception:
            self._rollback_partial(
                asg_name=asg_name if launch_template_id else None,
                launch_template_id=launch_template_id,
                rule_names=list(control.get("rule_names", ())),
                log_group_name=control.get("log_group_name"),
                lease_table_name=control.get("lease_table_name"),
                lifecycle_hook_names=list(control.get("hook_names", ())),
                coordinator_function_name=control.get("function_name"),
                coordinator_role_name=control.get("role_name"),
            )
            raise
        return SpotAutomationResources(
            launch_template_id=launch_template_id,
            auto_scaling_group_name=asg_name,
            instance_id=instance_id,
            log_group_name=control["log_group_name"],
            event_rule_names=control["rule_names"],
            lease_table_name=control["lease_table_name"],
            lifecycle_hook_names=control["hook_names"],
            coordinator_function_name=control["function_name"],
            coordinator_role_name=control["role_name"],
        )

    def wait_for_instance(self, asg_name: str, timeout_seconds: int = 600) -> str:
        """Wait for an ASG instance to enter InService."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            groups = self._autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name]).get(
                "AutoScalingGroups", []
            )
            if groups:
                for instance in groups[0].get("Instances", []):
                    if instance.get("LifecycleState") == "InService" and instance.get("HealthStatus") == "Healthy":
                        return str(instance["InstanceId"])
            time.sleep(5)
        raise RuntimeError(f"Auto Scaling group {asg_name} did not produce a healthy instance in time")

    def attach_target_group(self, asg_name: str, target_group_arn: str) -> None:
        """Route current and replacement instances through the existing ALB target group."""
        self._autoscaling.attach_load_balancer_target_groups(
            AutoScalingGroupName=asg_name,
            TargetGroupARNs=[target_group_arn],
        )
        self._autoscaling.update_auto_scaling_group(
            AutoScalingGroupName=asg_name,
            HealthCheckType="ELB",
            HealthCheckGracePeriod=600,
        )

    def verify(
        self,
        *,
        asg_name: str,
        instance_id: str,
        lease_table_name: str,
        lifecycle_hook_names: list[str],
        event_rule_names: list[str],
    ) -> None:
        """Fail unless the production Spot protection control plane is ready."""
        groups = self._autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name]).get(
            "AutoScalingGroups", []
        )
        if not groups:
            raise RuntimeError(f"Auto Scaling group {asg_name} was not found during protection verification")
        group = groups[0]
        if not group.get("CapacityRebalance") or group.get("DesiredCapacity") != 1:
            raise RuntimeError(f"Auto Scaling group {asg_name} does not have the required rebalance configuration")
        if not any(
            item.get("InstanceId") == instance_id
            and item.get("LifecycleState") == "InService"
            and item.get("HealthStatus") == "Healthy"
            for item in group.get("Instances", [])
        ):
            raise RuntimeError(f"Instance {instance_id} is not a healthy InService member of {asg_name}")

        stack_name = next(
            (tag.get("Value") for tag in group.get("Tags", []) if tag.get("Key") == "Stack"),
            None,
        )
        if not stack_name:
            raise RuntimeError(f"Auto Scaling group {asg_name} is missing its Stack tag")
        lease = self._dynamodb.get_item(
            TableName=lease_table_name,
            Key={"StackName": {"S": stack_name}},
            ConsistentRead=True,
        ).get("Item", {})
        if lease.get("Owner", {}).get("S") != instance_id:
            raise RuntimeError(f"Instance {instance_id} does not hold the active-node lease")

        hooks = self._autoscaling.describe_lifecycle_hooks(
            AutoScalingGroupName=asg_name,
            LifecycleHookNames=lifecycle_hook_names,
        ).get("LifecycleHooks", [])
        if {hook.get("LifecycleHookName") for hook in hooks} != set(lifecycle_hook_names):
            raise RuntimeError(f"Auto Scaling group {asg_name} is missing lifecycle hooks")
        for rule_name in event_rule_names:
            if not self._events.list_targets_by_rule(Rule=rule_name).get("Targets"):
                raise RuntimeError(f"EventBridge rule {rule_name} has no coordinator target")

    def delete(
        self,
        *,
        asg_name: str | None,
        launch_template_id: str | None,
        rule_names: list[str],
        log_group_name: str | None,
        lease_table_name: str | None = None,
        lifecycle_hook_names: list[str] | None = None,
        coordinator_function_name: str | None = None,
        coordinator_role_name: str | None = None,
    ) -> None:
        """Delete Spot automation resources in dependency order."""
        for rule_name in rule_names:
            targets = self._events.list_targets_by_rule(Rule=rule_name).get("Targets", [])
            if targets:
                self._events.remove_targets(Rule=rule_name, Ids=[target["Id"] for target in targets], Force=True)
            self._events.delete_rule(Name=rule_name, Force=True)
        if asg_name:
            for hook_name in lifecycle_hook_names or []:
                self._autoscaling.delete_lifecycle_hook(AutoScalingGroupName=asg_name, LifecycleHookName=hook_name)
        if coordinator_function_name:
            self._lambda.delete_function(FunctionName=coordinator_function_name)
        if asg_name:
            self._autoscaling.delete_auto_scaling_group(AutoScalingGroupName=asg_name, ForceDelete=True)
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                groups = self._autoscaling.describe_auto_scaling_groups(AutoScalingGroupNames=[asg_name]).get(
                    "AutoScalingGroups", []
                )
                if not groups:
                    break
                time.sleep(5)
            else:
                raise RuntimeError(f"Auto Scaling group {asg_name} did not finish deleting in time")
        if launch_template_id:
            self._ec2.delete_launch_template(LaunchTemplateId=launch_template_id)
        if log_group_name:
            self._logs.delete_log_group(logGroupName=log_group_name)
        if lease_table_name:
            self._dynamodb.delete_table(TableName=lease_table_name)
        if coordinator_role_name:
            self._iam.delete_role_policy(RoleName=coordinator_role_name, PolicyName="GeuseMakerSpotCoordinator")
            self._iam.delete_role(RoleName=coordinator_role_name)

    def _rollback_partial(self, **resources: Any) -> None:
        """Best-effort rollback without hiding the provisioning failure."""
        try:
            self.delete(**resources)
        except Exception:  # noqa: BLE001 - rollback must preserve the original error
            # A partially-created control plane commonly returns NotFound for the
            # first resource that was never reached. Continue with independent
            # cleanup passes for resources whose APIs are safe and idempotent.
            for function, kwargs in (
                (self._lambda.delete_function, {"FunctionName": resources.get("coordinator_function_name")}),
                (
                    self._autoscaling.delete_auto_scaling_group,
                    {"AutoScalingGroupName": resources.get("asg_name"), "ForceDelete": True},
                ),
                (self._ec2.delete_launch_template, {"LaunchTemplateId": resources.get("launch_template_id")}),
                (self._logs.delete_log_group, {"logGroupName": resources.get("log_group_name")}),
                (self._dynamodb.delete_table, {"TableName": resources.get("lease_table_name")}),
            ):
                if not all(kwargs.values()):
                    continue
                try:
                    function(**kwargs)
                except Exception as cleanup_error:  # noqa: BLE001 - best effort after failed create
                    _ = cleanup_error
            for rule_name in resources.get("rule_names", []):
                try:
                    self._events.remove_targets(Rule=rule_name, Ids=["spot-coordinator"], Force=True)
                    self._events.delete_rule(Name=rule_name, Force=True)
                except Exception as cleanup_error:  # noqa: BLE001 - best effort after failed create
                    _ = cleanup_error
            role_name = resources.get("coordinator_role_name")
            if role_name:
                try:
                    self._iam.delete_role_policy(RoleName=role_name, PolicyName="GeuseMakerSpotCoordinator")
                    self._iam.delete_role(RoleName=role_name)
                except Exception as cleanup_error:  # noqa: BLE001 - best effort after failed create
                    _ = cleanup_error

    def _create_failover_control_plane(self, stack_name: str, asg_name: str, tags: dict[str, str]) -> dict[str, Any]:
        log_group_name = f"/geusemaker/{stack_name}/spot-events"
        self._logs.create_log_group(logGroupName=log_group_name, tags=tags)
        self._logs.put_retention_policy(logGroupName=log_group_name, retentionInDays=30)
        log_group_arn = self._logs.describe_log_groups(logGroupNamePrefix=log_group_name)["logGroups"][0][
            "arn"
        ].removesuffix(":*")

        account_id = log_group_arn.split(":")[4]
        lease_table_name = f"{stack_name}-spot-lease"[:255]
        self._dynamodb.create_table(
            TableName=lease_table_name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "StackName", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "StackName", "KeyType": "HASH"}],
            Tags=[{"Key": key, "Value": value} for key, value in tags.items()],
        )
        self._dynamodb.get_waiter("table_exists").wait(TableName=lease_table_name)
        self._dynamodb.update_time_to_live(
            TableName=lease_table_name,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "ExpiresAt"},
        )

        role_name = f"{stack_name}-spot-coordinator"[:64]
        assume_role = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}
            ],
        }
        role = self._iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(assume_role),
            Tags=[{"Key": key, "Value": value} for key, value in tags.items()],
        )["Role"]
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {"Effect": "Allow", "Action": ["ec2:DescribeTags"], "Resource": "*"},
                {"Effect": "Allow", "Action": "ssm:SendCommand", "Resource": "*"},
                {
                    "Effect": "Allow",
                    "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                    "Resource": f"arn:aws:logs:{self.region}:{account_id}:log-group:{log_group_name}:*",
                },
            ],
        }
        self._iam.put_role_policy(
            RoleName=role_name, PolicyName="GeuseMakerSpotCoordinator", PolicyDocument=json.dumps(policy)
        )

        function_name = f"{stack_name}-spot-coordinator"[:64]
        function_request = {
            "FunctionName": function_name,
            "Runtime": "python3.12",
            "Role": role["Arn"],
            "Handler": "index.handler",
            "Code": {"ZipFile": self._coordinator_zip()},
            "Timeout": 30,
            "Environment": {
                "Variables": {
                    "STACK_NAME": stack_name,
                    "ASG_NAME": asg_name,
                    "LOG_GROUP": log_group_name,
                }
            },
            "Tags": tags,
        }
        for attempt in range(6):
            try:
                function_arn = self._lambda.create_function(**function_request)["FunctionArn"]
                break
            except ClientError as exc:
                message = exc.response.get("Error", {}).get("Message", "")
                if attempt == 5 or "cannot be assumed" not in message.lower():
                    raise
                time.sleep(2**attempt)
        else:  # pragma: no cover - the final failed attempt always raises
            raise RuntimeError(f"Could not create Spot coordinator {function_name}")

        patterns = {
            f"{stack_name[:44]}-spot-interruption": {
                "source": ["aws.ec2"],
                "detail-type": ["EC2 Spot Instance Interruption Warning", "EC2 Instance Rebalance Recommendation"],
            },
            f"{stack_name[:50]}-asg-lifecycle": {
                "source": ["aws.autoscaling"],
                "detail-type": [
                    "EC2 Instance-launch Lifecycle Action",
                    "EC2 Instance-terminate Lifecycle Action",
                    "EC2 Instance Launch Successful",
                    "EC2 Instance Launch Unsuccessful",
                    "EC2 Instance Terminate Successful",
                    "EC2 Instance Terminate Unsuccessful",
                ],
                "detail": {"AutoScalingGroupName": [asg_name]},
            },
        }
        for rule_name, pattern in patterns.items():
            self._events.put_rule(
                Name=rule_name,
                EventPattern=json.dumps(pattern),
                State="ENABLED",
                Tags=[{"Key": key, "Value": value} for key, value in tags.items()],
            )
            self._lambda.add_permission(
                FunctionName=function_name,
                StatementId=f"EventBridge-{rule_name}"[:100],
                Action="lambda:InvokeFunction",
                Principal="events.amazonaws.com",
                SourceArn=self._events.describe_rule(Name=rule_name)["Arn"],
            )
            self._events.put_targets(Rule=rule_name, Targets=[{"Id": "spot-coordinator", "Arn": function_arn}])

        hook_names = (f"{stack_name[:42]}-launch", f"{stack_name[:39]}-terminate")
        for hook_name, transition in zip(
            hook_names, ("autoscaling:EC2_INSTANCE_LAUNCHING", "autoscaling:EC2_INSTANCE_TERMINATING"), strict=True
        ):
            self._autoscaling.put_lifecycle_hook(
                LifecycleHookName=hook_name,
                AutoScalingGroupName=asg_name,
                LifecycleTransition=transition,
                HeartbeatTimeout=300 if transition.endswith("LAUNCHING") else 110,
                DefaultResult="ABANDON" if transition.endswith("LAUNCHING") else "CONTINUE",
            )
        return {
            "log_group_name": log_group_name,
            "rule_names": tuple(patterns),
            "lease_table_name": lease_table_name,
            "hook_names": hook_names,
            "function_name": function_name,
            "role_name": role_name,
        }

    @staticmethod
    def _coordinator_zip() -> bytes:
        """Build the small, dependency-free event coordinator Lambda package."""
        source = """import json, os, time, boto3
ec2=boto3.client("ec2"); ssm=boto3.client("ssm"); logs=boto3.client("logs")
def emit(record):
 try: logs.create_log_stream(logGroupName=os.environ["LOG_GROUP"],logStreamName="coordinator")
 except logs.exceptions.ResourceAlreadyExistsException: pass
 logs.put_log_events(logGroupName=os.environ["LOG_GROUP"],logStreamName="coordinator",logEvents=[{"timestamp":int(time.time()*1000),"message":json.dumps(record)}])
def handler(event, context):
 d=event.get("detail", {}); iid=d.get("instance-id") or d.get("EC2InstanceId")
 if not iid: return {"ignored":"missing-instance"}
 tags={x["Key"]:x["Value"] for x in ec2.describe_tags(Filters=[{"Name":"resource-id","Values":[iid]}]).get("Tags",[])}
 if tags.get("ManagedBy")!="GeuseMaker" or tags.get("Stack")!=os.environ["STACK_NAME"]: return {"ignored":"not-managed"}
 emit({"event":event.get("detail-type"),"instance_id":iid,"stack":tags["Stack"]})
 if event.get("detail-type") in ("EC2 Spot Instance Interruption Warning","EC2 Instance Rebalance Recommendation","EC2 Instance-terminate Lifecycle Action"):
  try: ssm.send_command(InstanceIds=[iid],DocumentName="AWS-RunShellScript",Parameters={"commands":["sudo systemctl start geusemaker-spot-drain.service"]})
  except Exception as exc: emit({"drain_error":str(exc),"instance_id":iid})
 return {"handled":iid}
"""
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("index.py", source)
        return output.getvalue()


__all__ = ["SpotAutomationResources", "SpotAutomationService"]
