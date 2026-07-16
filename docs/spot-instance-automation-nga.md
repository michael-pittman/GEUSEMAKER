# Spot Instance Automation — Stack `nga` (`i-0267cc79deab4cd7a`)

**Status:** Design document (not implemented)  
**Audience:** Operators converting On-Demand → Spot; GeuseMaker contributors integrating Path 2  
**Region:** `us-east-1`  
**Account (from live inventory):** `576245050892`  
**Captured:** 2026-07-15 (from live AWS describe APIs)

This document describes **two complete automation approaches** for surviving Spot interruptions while keeping all currently attached resources for the live `nga` stack. Path 2 is designed for **non-breaking integration** into the GeuseMaker codebase.

---

## Table of contents

1. [Current inventory (source of truth)](#1-current-inventory-source-of-truth)
2. [What must move vs what stays](#2-what-must-move-vs-what-stays)
3. [Shared invariants (both paths)](#3-shared-invariants-both-paths)
4. [Path 1 — ASG + Launch Template](#4-path-1--asg--launch-template)
5. [Path 2 — EventBridge + GeuseMaker `replace` (codebase-safe)](#5-path-2--eventbridge--geusemaker-replace-codebase-safe)
6. [Comparison matrix](#6-comparison-matrix)
7. [Cutover checklist (On-Demand → Spot)](#7-cutover-checklist-on-demand--spot)
8. [Risks, secrets, and non-goals](#8-risks-secrets-and-non-goals)

---

## 1. Current inventory (source of truth)

All IDs below were read from the live instance and related AWS APIs. Automation must treat these as the attachment set.

### 1.1 EC2 compute

| Field | Value |
|-------|--------|
| Instance ID | `i-0267cc79deab4cd7a` |
| Type | `g4dn.xlarge` (Tesla T4 16 GiB, 4 vCPU, 16 GiB RAM) |
| Lifecycle today | **On-Demand** (`InstanceLifecycle` unset / no Spot request) |
| AMI | `ami-0193ca8306cf64925` — Deep Learning Base AMI Single CUDA Ubuntu 22.04 (20251205) |
| AZ | `us-east-1b` |
| VPC | `vpc-009f2956e4089d8d1` |
| Subnet | `subnet-07b82f43883236dc4` |
| Private IP | `10.0.2.84` |
| Public IP | `3.81.134.93` (ephemeral — **do not** put in webhook configs) |
| Key pair | **None** (SSM-only access) |
| IAM instance profile | `nga-instance-profile` (`arn:aws:iam::576245050892:instance-profile/nga-instance-profile`) |
| Primary ENI | `eni-0daf826b7dfd2ede4` |
| Root volume | `vol-029a54da45d3c78fa` — 75 GiB gp3, encrypted, **DeleteOnTermination=true** |
| Monitoring | disabled |
| IMDS | HttpEndpoint enabled, HttpTokens optional |
| Tags | `Name=nga`, `Stack=nga`, `Tier=automation` |

### 1.2 Security group `nga-sg` (`sg-0fb262d8f38446ca3`)

| Direction | Proto | Ports | Source |
|-----------|-------|-------|--------|
| Ingress | TCP | 22 | `0.0.0.0/0` |
| Ingress | TCP | 80, 443 | `0.0.0.0/0` |
| Ingress | TCP | 5678 | `0.0.0.0/0` (n8n; ALB also fronts this) |
| Ingress | TCP | 3001 | self SG (editor; ALB TG) |
| Ingress | TCP | 8088 | self SG (webhook-alias; ALB TG) |
| Ingress | TCP | 2049 | `10.0.0.0/16` (EFS NFS) |
| Egress | all | all | (default allow) |

**Automation note:** Reuse this SG ID on every replacement launch. Do not recreate.

### 1.3 EFS (persistent data plane)

| Field | Value |
|-------|--------|
| File system | `fs-025495fdc7804f872` (`Name=nga`) |
| Mode | generalPurpose / bursting / encrypted / available |
| Mount target | `fsmt-0d147b06025c0ced4` |
| Mount IP | `10.0.2.107` |
| Mount subnet / AZ | `subnet-07b82f43883236dc4` / `us-east-1b` |
| Host mounts (observed) | `/mnt/efs/n8n`, `/mnt/efs/ollama`, `/mnt/efs/postgres`, `/mnt/efs/qdrant` |

**Automation note:** EFS and mount target are **stable**. New instances remount via UserData + IAM auth (`tls,iam`). Pin mount IP in `/etc/hosts` as GeuseMaker already does.

### 1.4 ALB / TLS / DNS (stable edge)

| Field | Value |
|-------|--------|
| ALB | `nga-alb` |
| ALB ARN | `arn:aws:elasticloadbalancing:us-east-1:576245050892:loadbalancer/app/nga-alb/17b9815f165d2d47` |
| ALB DNS | `nga-alb-1360825012.us-east-1.elb.amazonaws.com` |
| Scheme | internet-facing |
| ALB AZs | `us-east-1a` (`subnet-0014bc2705ebf34ba`), `us-east-1b` (`subnet-07b82f43883236dc4`) |
| ALB SG | `sg-0fb262d8f38446ca3` (same as instance) |
| Listeners | HTTP :80, HTTPS :443 |
| ACM cert | `arn:aws:acm:us-east-1:576245050892:certificate/4672b2e5-20ba-4ed6-8955-a5c11d6b8a33` |
| DNS | `ai.geuse.io` **A/AAAA alias → ALB** (Route53 zone `geuse.io.`) |
| Extra host | `editor.geuse.io` → editor TG (listener rule priority 98) |

### 1.5 Target groups (must re-register on every replace)

| Name | ARN suffix | Port | Health | Host / path routing |
|------|------------|------|--------|---------------------|
| `nga-tg` | `.../targetgroup/nga-tg/7a9840a5d15bec68` | **5678** | `/healthz`, HTTP 200–399 | Default forward for `ai.geuse.io` (n8n) |
| `nga-webhook-alias-tg` | `.../targetgroup/nga-webhook-alias-tg/90caef48681f4e5c` | **8088** | `/healthz` | `ai.geuse.io` + path `/v1/*` |
| `nga-editor-tg` | `.../targetgroup/nga-editor-tg/1e0c39cdde764073` | **3001** | `/healthz` | host `editor.geuse.io` |

All three currently register **only** `i-0267cc79deab4cd7a` and are healthy.

### 1.6 Workload on the instance (runtime)

Containers observed on this host (compose under `/root/docker-compose.yml` + `/root/runtime.env`):

- `n8n`, `ollama`, `qdrant`, `crawl4ai`, `postgres`, `webhook-alias` (nginx)
- Additional: `geuse-editor` (separate compose under `/opt/geuse/...`)

Primary LLM (as of 2026-07-14): `qwythos:q6k` on Ollama; models on EFS.

### 1.7 GeuseMaker product state vs live AWS gap

| Concern | GeuseMaker `DeploymentState` today | Live `nga` |
|---------|--------------------------------------|------------|
| Target groups | **Singular** `target_group_arn` | **Three** TGs |
| Local state file | Often empty / recoverable via tags | Resources exist in AWS |
| Spot | `config.use_spot` + launch-time market options | Currently On-Demand |
| Interruption handling | `RollbackRecord.trigger` includes `"spot_interruption"` literal only | **Not implemented** |

Path 2 must **discover** all TGs attached to `alb_arn` at replace time rather than requiring a breaking state schema change.

---

## 2. What must move vs what stays

```text
STABLE (never recreate on interrupt)
────────────────────────────────────
  Route53 ai.geuse.io / editor.geuse.io
  ALB nga-alb + listeners + ACM + rules
  Target group objects (ARNs stay; membership changes)
  EFS fs-025495fdc7804f872 + mount target
  VPC / subnets / SG nga-sg
  IAM role + instance profile nga-instance-profile

MOVES / RECREATES
────────────────────────────────────
  EC2 instance ID + ENI + public/private IPs
  Root EBS volume (DeleteOnTermination)
  ALB target registrations (old Id → new Id) × 3 TGs
  Local root-disk state (/root/runtime.env, /opt/..., Docker images cache)
```

**Webhook URLs stay stable** because callers use `https://ai.geuse.io/...`, not the public IP.

---

## 3. Shared invariants (both paths)

1. **Launch in `us-east-1b` when possible** so the EFS mount target (`10.0.2.107`) is same-AZ (lower latency; required for single mount target layout).
2. **Same IAM profile** so EFS IAM auth continues to work.
3. **Same SG** so ALB → instance ports 5678/3001/8088 and EFS 2049 still work.
4. **Preserve secrets** on replace: `POSTGRES_PASSWORD`, `N8N_ENCRYPTION_KEY`, and any tokens in `/root/runtime.env`. Regenerating them while EFS keeps old DB/n8n data **breaks** the stack.
5. **Do not depend on public IP** in n8n webhook URLs, DNS, or client configs.
6. **Expect downtime** from interruption notice → new instance healthy (often 5–20+ minutes depending on UserData / image pulls).
7. **Tag every replacement** with `Stack=nga` (and prefer `Name=nga`, `Tier=automation`) for discovery and GeuseMaker list/recovery.

---

## 4. Path 1 — ASG + Launch Template

### 4.1 When to choose Path 1

- You want AWS-native capacity replacement with minimal custom code.
- You are OK managing Launch Template + ASG outside (or beside) the GeuseMaker Python package.
- You want ALB target registration handled by ASG target-group attachments.

### 4.2 Architecture

```text
Spot interruption / unhealthy target
        │
        ▼
   ASG (desired=1, CapacityRebalance)
        │ launches from
        ▼
 Launch Template (Spot g4dn.xlarge, same SG/IAM/UserData/EFS)
        │
        ▼
 ASG registers instance into:
   nga-tg :5678
   nga-webhook-alias-tg :8088
   nga-editor-tg :3001
        │
        ▼
 ALB healthy → ai.geuse.io / editor.geuse.io resume
```

### 4.3 Step-by-step build

#### Step 1 — Capture a Launch Template baseline from the live instance

Record (already inventoried):

- Image: `ami-0193ca8306cf64925` (or pin a newer DLAMI later deliberately)
- Type: `g4dn.xlarge`
- Subnet default: `subnet-07b82f43883236dc4` (us-east-1b)
- SG: `sg-0fb262d8f38446ca3`
- IAM profile: `nga-instance-profile`
- Block device: 75 GiB gp3 encrypted, delete on termination
- Tags: `Stack=nga`, `Name=nga`, `Tier=automation`
- UserData: must mount EFS `fs-025495fdc7804f872` at mount IP `10.0.2.107`, install/start Docker stack, write preserved `runtime.env`

**CLI sketch:**

```bash
aws ec2 create-launch-template \
  --launch-template-name nga-spot-lt \
  --version-description "nga spot baseline from i-0267cc79deab4cd7a" \
  --launch-template-data '{
    "ImageId": "ami-0193ca8306cf64925",
    "InstanceType": "g4dn.xlarge",
    "IamInstanceProfile": {"Name": "nga-instance-profile"},
    "SecurityGroupIds": ["sg-0fb262d8f38446ca3"],
    "KeyName": null,
    "BlockDeviceMappings": [{
      "DeviceName": "/dev/sda1",
      "Ebs": {
        "VolumeSize": 75,
        "VolumeType": "gp3",
        "Iops": 3000,
        "Encrypted": true,
        "DeleteOnTermination": true
      }
    }],
    "MetadataOptions": {
      "HttpEndpoint": "enabled",
      "HttpTokens": "optional",
      "HttpPutResponseHopLimit": 1
    },
    "TagSpecifications": [{
      "ResourceType": "instance",
      "Tags": [
        {"Key": "Name", "Value": "nga"},
        {"Key": "Stack", "Value": "nga"},
        {"Key": "Tier", "Value": "automation"},
        {"Key": "ManagedBy", "Value": "asg-spot"}
      ]
    }],
    "InstanceMarketOptions": {
      "MarketType": "spot",
      "SpotOptions": {
        "SpotInstanceType": "one-time",
        "InstanceInterruptionBehavior": "terminate"
      }
    },
    "UserData": "<BASE64_USERDATA_WITH_EFS_AND_PRESERVED_SECRETS>"
  }'
```

> **Critical:** Build UserData from a secret-preserving source (SSM Parameter Store or a one-time pull of `/root/runtime.env`), not a fresh GeuseMaker password generator.

#### Step 2 — Create / verify the three target groups exist

Do **not** recreate; use existing ARNs:

- `arn:aws:elasticloadbalancing:us-east-1:576245050892:targetgroup/nga-tg/7a9840a5d15bec68` (port 5678)
- `arn:aws:elasticloadbalancing:us-east-1:576245050892:targetgroup/nga-webhook-alias-tg/90caef48681f4e5c` (port 8088)
- `arn:aws:elasticloadbalancing:us-east-1:576245050892:targetgroup/nga-editor-tg/1e0c39cdde764073` (port 3001)

#### Step 3 — Create ASG with desired capacity 1

```bash
aws autoscaling create-auto-scaling-group \
  --auto-scaling-group-name nga-spot-asg \
  --launch-template LaunchTemplateName=nga-spot-lt,Version='$Latest' \
  --min-size 0 \
  --max-size 1 \
  --desired-capacity 0 \
  --vpc-zone-identifier subnet-07b82f43883236dc4 \
  --health-check-type ELB \
  --health-check-grace-period 600 \
  --capacity-rebalance \
  --tags \
    Key=Stack,Value=nga,PropagateAtLaunch=true \
    Key=Name,Value=nga,PropagateAtLaunch=true
```

Attach all three target groups with correct ports:

```bash
aws autoscaling attach-load-balancer-target-groups \
  --auto-scaling-group-name nga-spot-asg \
  --target-group-arns \
    arn:aws:elasticloadbalancing:us-east-1:576245050892:targetgroup/nga-tg/7a9840a5d15bec68 \
    arn:aws:elasticloadbalancing:us-east-1:576245050892:targetgroup/nga-webhook-alias-tg/90caef48681f4e5c \
    arn:aws:elasticloadbalancing:us-east-1:576245050892:targetgroup/nga-editor-tg/1e0c39cdde764073
```

> If port overrides are required per TG, use ASG target group config with `Port` matching 5678 / 8088 / 3001 respectively (ASG API `TargetGroupARNs` alone assumes instance port = TG port; these TGs already define those ports).

#### Step 4 — Cut over from the current On-Demand instance

1. Confirm EFS data is healthy (`n8n`, Postgres, Ollama models).
2. Snapshot secrets from the live instance into SSM SecureString (or sealed LT UserData pipeline).
3. Drain / deregister `i-0267cc79deab4cd7a` from all three TGs **or** terminate after ASG is ready to take traffic.
4. Set ASG desired capacity to `1`.
5. Wait until all three TGs show the **new** instance healthy.
6. Terminate `i-0267cc79deab4cd7a` if still running.
7. Verify:
   - `https://ai.geuse.io/healthz` (or n8n health)
   - webhook path `https://ai.geuse.io/v1/...`
   - `https://editor.geuse.io/healthz`

#### Step 5 — Interruption behavior (steady state)

1. AWS emits Spot interruption (≈2 minute warning).
2. Capacity Rebalance may start a replacement early when available.
3. Old instance terminates; ASG launches replacement from LT.
4. ASG registers new instance into the three TGs.
5. ALB serves 502/503 until health checks pass; DNS unchanged.

#### Step 6 — Operations runbook (Path 1)

| Action | Command / note |
|--------|----------------|
| Scale down for cost | `desired-capacity 0` (EFS data retained) |
| Scale up | `desired-capacity 1` |
| Change instance type | New LT version → ASG instance refresh |
| Rotate AMI | New LT version with new AMI + refresh |
| Inspect targets | `describe-target-health` on each TG ARN |
| Rollback to OD | New LT version **without** `InstanceMarketOptions`, refresh |

#### Step 7 — Path 1 ownership boundary vs GeuseMaker

| Component | Owned by |
|-----------|----------|
| LT / ASG / EventBridge (optional alarms) | AWS account ops / IaC (Terraform/CFN/CDK) |
| EFS / ALB / SG / IAM (already exist) | Shared; do not destroy via ASG |
| App compose / models | EFS + UserData |
| GeuseMaker CLI | Optional for initial provision only; **not required** for interrupt recovery |

**Non-breaking note:** Path 1 does not require GeuseMaker code changes. If you later sync state, update `instance_id` via discovery (`geusemaker list --discover-from-aws`) rather than changing deploy semantics.

---

## 5. Path 2 — EventBridge + GeuseMaker `replace` (codebase-safe)

### 5.1 Design goals (non-breaking)

1. **Additive only** — new CLI command, new service module, new models; optional additive ALB helper.
2. **Do not change** `UpdateOrchestrator`, `UpdateRequest`, Tier1/2/3 public flows, or singular `target_group_arn` semantics for existing stacks.
3. **Multi-TG (nga)** handled by **runtime discovery** from `alb_arn`, not a forced state migration.
4. EventBridge / Lambda stay **outside** the installable Python package (docs + optional infra templates only).
5. Reuse existing services: `EC2Service.launch_instance(**kwargs)`, `terminate_instance`, `ALBService.register_targets` / `wait_for_healthy`, `UserDataGenerator`, `SpotSelectionService`, `StateManager`, `SSMService`.

### 5.2 Architecture

```text
EC2 Spot Interruption Warning  (or Instance State-change → terminated)
        │
        ▼
 EventBridge rule (account infra)
        │ invokes
        ▼
 Lambda / SSM Automation / operator CI
        │ runs
        ▼
 geusemaker replace nga --force --use-spot
        │
        ├─ load DeploymentState (or recover from AWS tags Stack=nga)
        ├─ discover ALL target groups for alb_arn (3 for nga)
        ├─ SSM: pull /root/runtime.env secrets from old instance (if still up)
        ├─ UserData with existing efs_id + mount IP + preserved secrets
        ├─ launch Spot clone (same SG/IAM/subnet family)
        ├─ wait running + SSM online
        ├─ for each TG: deregister old → register new → wait healthy
        ├─ save state (instance_id, IPs, cost.is_spot)
        └─ terminate old instance (if still present)
```

### 5.3 GeuseMaker integration map (accurate to current tree)

| Piece | Location | Action |
|-------|----------|--------|
| CLI entry | `geusemaker/cli/main.py` (`cli.add_command(...)`) | **Add** `replace` registration only |
| New command | `geusemaker/cli/commands/replace.py` | **Create** (mirror `update.py` patterns) |
| New orchestrator | `geusemaker/services/replace/` (e.g. `orchestrator.py`) | **Create** |
| New models | `geusemaker/models/replace.py` → `ReplaceRequest`, `ReplaceResult` | **Create** |
| Barrel exports | `services/__init__.py`, `models/__init__.py` | **Additive** exports |
| ALB deregister | Today only in `destruction/service.py` via raw elbv2 | Prefer **additive** `ALBService.deregister_targets(...)` mirroring `register_targets` |
| State | `DeploymentState.target_group_arn` remains singular | Discover extras at runtime; optionally later add `target_group_arns: list[str] = []` with default (migration-safe) |
| Update path | `services/update/*` | **Do not modify** behavior |

CLI patterns to copy (`cli/commands/update.py`):

- `@click.command("replace")` + `@click.argument("stack_name")`
- `--force`, `--state-dir`, `@output_option()`
- `console.print` + `EMOJI` (never `print()`)
- `asyncio.run(StateManager(...).load_deployment(...))`
- `build_response` / `emit_result` for JSON mode

### 5.4 Proposed public CLI (additive)

```bash
geusemaker replace nga \
  --force \
  --use-spot \
  --discover-target-groups \
  --preserve-secrets-via-ssm \
  --output text
```

Suggested options (all new; no changes to `deploy`/`update` flags required):

| Option | Purpose |
|--------|---------|
| `--use-spot` / `--on-demand` | Market type for the **new** instance (OD→Spot cutover uses `--use-spot`) |
| `--instance-type` | Optional override (default: current / `config.instance_type`) |
| `--ami-id` | Optional pin (default: current image or DLAMI lookup) |
| `--subnet-id` | Prefer current AZ subnet for EFS locality |
| `--discover-target-groups` | Enumerate TGs for `state.alb_arn` (required for nga’s 3 TGs) |
| `--preserve-secrets-via-ssm` | Fetch `runtime.env` from old instance before terminate |
| `--skip-terminate-old` | Leave old instance for manual cutover debugging |
| `--force` | Skip confirmation |

### 5.5 Step-by-step implementation (code, non-breaking)

#### Step A — Models (`geusemaker/models/replace.py`)

Add only new types, for example:

```python
class ReplaceRequest(BaseModel):
    deployment_name: str
    use_spot: bool = True
    instance_type: str | None = None
    ami_id: str | None = None
    subnet_id: str | None = None
    discover_target_groups: bool = True
    preserve_secrets_via_ssm: bool = True
    terminate_old: bool = True
    force: bool = False

class ReplaceResult(BaseModel):
    success: bool
    old_instance_id: str
    new_instance_id: str
    target_groups_updated: list[str]
    duration_seconds: float
    warnings: list[str] = []
```

Do **not** extend `UpdateRequest`.

#### Step B — Optional additive ALB API

In `geusemaker/services/alb.py`, add (do not alter existing signatures):

```python
def deregister_targets(
    self,
    target_group_arn: str,
    instance_ids: list[str],
    port: int | None = None,
) -> dict[str, Any]:
    ...
```

Mirror `register_targets` / destruction’s raw call shape.

#### Step C — `ReplaceOrchestrator` algorithm (nga-accurate)

1. **Load state** via `StateManager.load_deployment("nga")`.  
   - If missing: recover from AWS tags `Stack=nga` (existing discovery/list path), then require confirm unless `--force`.
2. **Validate** prerequisites:
   - `efs_id`, `efs_mount_target_ip` (or look up mount target)
   - `iam_instance_profile_name`
   - `security_group_id`, subnet
   - For Tier automation: `alb_arn` present
3. **Snapshot** `previous_states` / `last_healthy_state` (same pattern as update).
4. **Resolve TG ARNs**:
   - Always include `state.target_group_arn` if set.
   - If `--discover-target-groups` and `alb_arn`: describe listeners/rules/TGs for that ALB and collect unique TG ARNs + ports.  
     For nga this yields the three ARNs in §1.5.
5. **Preserve secrets** (if old instance still running / SSM online):
   - `SSMService.run_shell_script` to read `/root/runtime.env` (and editor env if needed).
   - Persist temporarily in memory for UserData generation; optionally write SecureString params tagged `Stack=nga`.
6. **Build UserData**:
   - `UserDataConfig(efs_id=state.efs_id, efs_mount_target_ip=..., stack_name="nga", region=..., tier=automation, ...)`
   - Inject **preserved** postgres/n8n secrets — do not call generators that mint new encryption keys.
7. **Launch** via `EC2Service.launch_instance(...)` with kwargs aligned to Tier1 spot launch:
   - `ImageId`, `InstanceType=g4dn.xlarge` (or override)
   - `SubnetId=subnet-07b82f43883236dc4` (prefer)
   - `SecurityGroupIds=[sg-0fb262d8f38446ca3]`
   - `IamInstanceProfile={"Name": "nga-instance-profile"}`
   - `BlockDeviceMappings` 75 GiB gp3 encrypted
   - `TagSpecifications` Stack/Name/Tier
   - If spot:  
     `InstanceMarketOptions={MarketType: spot, SpotOptions: {SpotInstanceType: one-time, InstanceInterruptionBehavior: terminate}}`
8. **Wait** `wait_for_running`; optionally wait SSM Online.
9. **Reattach ALB**:
   - For each TG ARN: `deregister_targets(old_id)` (ignore if already gone).
   - `register_targets(new_id, port=TG port if required)`.
   - `wait_for_healthy` per TG (nga health path `/healthz`).
10. **Update state fields only** (no schema break):
    - `instance_id`, `public_ip`, `private_ip`, `updated_at`
    - `cost.is_spot`, spot/on-demand hourly if available
    - `status="running"`
    - Keep `alb_arn`, `efs_*`, IAM names unchanged
11. **Terminate old** `i-0267cc79deab4cd7a` (unless `--skip-terminate-old`).
12. **Emit** `ReplaceResult`; append optional `RollbackRecord(trigger="spot_interruption")` only when replace was interruption-driven (field already exists — safe to use).

#### Step D — Wire CLI

1. Create `geusemaker/cli/commands/replace.py`.
2. In `geusemaker/cli/main.py` add:
   - `from geusemaker.cli.commands.replace import replace`
   - `cli.add_command(replace)`
3. Add unit tests under `tests/unit/...` with stubs (moto for EC2/ELBv2 where useful). **Do not** change existing update tests’ contracts.

#### Step E — EventBridge automation (outside the package)

Account-level rule (example):

**Event pattern — interruption warning:**

```json
{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Spot Instance Interruption Warning"],
  "detail": {
    "instance-id": ["i-0267cc79deab4cd7a"]
  }
}
```

After first replace, update the rule to tag-based matching (`Stack=nga`) instead of hardcoding instance ID.

**Target options (pick one):**

1. **Lambda** in VPC or with network access that runs a container/task executing `geusemaker replace nga --force --use-spot --discover-target-groups`.
2. **SSM Automation** document that assumes an operator host / CodeBuild with GeuseMaker installed and AWS creds.
3. **Manual** first: CloudWatch alarm / SNS email → human runs the CLI (lowest risk while validating secrets handling).

**IAM for the invoker (least privilege sketch):**

- `ec2:RunInstances`, `TerminateInstances`, `Describe*`, `CreateTags`
- `iam:PassRole` on `nga` instance role only
- `elasticloadbalancing:RegisterTargets`, `DeregisterTargets`, `DescribeTargetHealth`, `DescribeTargetGroups`, `DescribeListeners`, `DescribeRules`
- `ssm:SendCommand`, `GetCommandInvocation` on instances tagged `Stack=nga`
- `elasticfilesystem:ClientMount` already on instance role; invoker needs describe only
- **No** broad `iam:*` or unrelated destroy permissions

### 5.6 Step-by-step operator runbook (Path 2) for this instance

#### One-time OD → Spot cutover

1. Ensure local/recovered state for stack `nga` includes `efs_id=fs-025495fdc7804f872`, IAM profile name, SG, subnet, `alb_arn`.
2. Dry-run mental check: TGs discovered = 3.
3. Confirm SSM Online on `i-0267cc79deab4cd7a`.
4. Run:
   ```bash
   geusemaker replace nga --use-spot --discover-target-groups --preserve-secrets-via-ssm --force
   ```
5. Validate health on all three TGs and HTTPS endpoints.
6. Confirm old instance terminated; new instance tagged `Stack=nga`.
7. Point EventBridge at tag-based replace (not the old instance ID).

#### Ongoing interruption

1. Warning fires → automation invokes `geusemaker replace`.
2. If SSM already dead, secrets must come from Parameter Store backup (pre-requisite: Step C5 should also **write** secrets to SSM on successful replace).
3. ALB continues resolving `ai.geuse.io`; clients retry during 502 window.

### 5.7 Explicit non-changes (break-glass list)

Do **not**:

- Fold replace into `geusemaker update` / `UpdateOrchestrator`
- Require `target_groups: dict` in state for v2 schema bump (optional additive field later only)
- Recreate ALB, EFS, SG, or IAM profile on replace
- Regenerate `N8N_ENCRYPTION_KEY` / Postgres password on replace
- Put EventBridge rules inside the hatchling package
- Change destruction order or provenance rules
- Assume single TG registration is enough for nga (it is not)

### 5.8 Test plan (Path 2)

| Test | Expect |
|------|--------|
| Unit: TG discovery from fake ALB describe | Returns 3 ARNs + ports for nga-like fixtures |
| Unit: launch kwargs include Spot options when requested | Matches Tier1 shape |
| Unit: secrets injection into UserData | No new random encryption key when preserve=True |
| Unit: state update keeps `alb_arn`/`efs_id` | Unchanged |
| Integration (manual): replace on non-prod | All TGs healthy; n8n decrypts credentials; Postgres accepts password |
| Negative: replace without secrets preserve against EFS data | Fails validation or warns loudly |

---

## 6. Comparison matrix

| Dimension | Path 1 ASG+LT | Path 2 EventBridge + `geusemaker replace` |
|-----------|---------------|---------------------------------------------|
| Fits GeuseMaker model | Loose (ops beside CLI) | **Tight** (CLI/service extension) |
| Code changes in repo | None required | Additive modules + CLI register |
| Multi-TG (nga’s 3) | Native ASG attachments | Discovery at replace time |
| Secret preservation | Must bake into LT/SSM pipeline | SSM pull + optional SSM store in orchestrator |
| Interrupt latency | Often best (Capacity Rebalance) | Depends on EventBridge→invoke cold start |
| OD→Spot cutover | LT without→with Spot + refresh | `replace --use-spot` |
| Drift from GeuseMaker state | High unless sync discovery | Low if replace updates state |
| Blast radius | ASG misconfig can scale wrong | Scoped to explicit replace command |

**Recommendation for this account:**  
- Use **Path 2** if you want GeuseMaker to remain the control plane and to integrate cleanly.  
- Use **Path 1** if you want fastest AWS-native recovery and accept LT/ASG as the source of compute truth.

Hybrid is valid: Path 1 for compute, Path 2’s secret/UserData lessons applied to LT UserData, plus periodic `list --discover-from-aws` for state sync.

---

## 7. Cutover checklist (On-Demand → Spot)

Applicable to both paths for `i-0267cc79deab4cd7a`:

- [ ] Backup confirmation: EFS `fs-025495fdc7804f872` has n8n/Postgres/Ollama data
- [ ] Export `/root/runtime.env` (and editor env if required) to SSM SecureString
- [ ] Confirm callers use `https://ai.geuse.io` / `https://editor.geuse.io` (not `3.81.134.93`)
- [ ] Confirm ACM on ALB still valid
- [ ] Implement Path 1 LT/ASG **or** Path 2 `replace` + EventBridge
- [ ] Execute cutover in a maintenance window
- [ ] Verify TG health for ports **5678, 8088, 3001**
- [ ] Spot-check n8n login, one webhook, Ollama `qwythos:q6k`, editor host
- [ ] Remove/disable any hardcoded dependency on old instance ID in alarms/rules
- [ ] Document new instance ID in ops notes; keep tags `Stack=nga`

---

## 8. Risks, secrets, and non-goals

### Risks

| Risk | Mitigation |
|------|------------|
| New UserData regenerates n8n encryption key | Always preserve secrets from old host or SSM |
| Replace launches in wrong AZ without mount target | Prefer `us-east-1b` / subnet `subnet-07b82f43883236dc4`; or create multi-AZ mount targets first |
| Only re-register `state.target_group_arn` | Discover all TGs for `nga-alb` (3) |
| Spot capacity shortage in `us-east-1b` | Fallback AZ only if EFS mount targets exist there; else On-Demand fallback |
| Root disk only artifacts lost | Keep compose/secrets on EFS or SSM; treat AMI+UserData as rebuildable |
| ASG desired>1 accidentally | Max size 1 for this single-node stack |

### Non-goals (this document)

- Multi-node active-active n8n
- Changing instance family beyond what LT/`replace` overrides allow
- Migrating off ALB to CloudFront (Tier 3) as part of Spot work
- Implementing the code in this PR/doc pass (design only)

---

## Appendix A — Quick reference IDs

```text
Instance (current OD):  i-0267cc79deab4cd7a
AMI:                    ami-0193ca8306cf64925
VPC:                    vpc-009f2956e4089d8d1
Subnet (1b):            subnet-07b82f43883236dc4
SG:                     sg-0fb262d8f38446ca3
IAM profile:            nga-instance-profile
EFS:                    fs-025495fdc7804f872
EFS MT / IP:            fsmt-0d147b06025c0ced4 / 10.0.2.107
ALB:                    nga-alb / nga-alb-1360825012.us-east-1.elb.amazonaws.com
TG n8n:                 nga-tg :5678
TG webhooks:            nga-webhook-alias-tg :8088
TG editor:              nga-editor-tg :3001
DNS:                    ai.geuse.io → ALB; editor.geuse.io → editor TG
```

## Appendix B — Related GeuseMaker code (read-only anchors)

| Topic | Path |
|-------|------|
| CLI registration | `geusemaker/cli/main.py` |
| Update command pattern | `geusemaker/cli/commands/update.py` |
| Spot launch options | `geusemaker/orchestration/tier1.py` (`InstanceMarketOptions`) |
| Spot selection | `geusemaker/services/compute/spot.py` |
| EC2 launch | `geusemaker/services/ec2.py` (`launch_instance`) |
| ALB register/wait | `geusemaker/services/alb.py` |
| ALB deregister today | `geusemaker/services/destruction/service.py` |
| State model | `geusemaker/models/deployment.py` |
| UserData | `geusemaker/services/userdata/` |
| Spot interruption trigger literal | `RollbackRecord.trigger` includes `"spot_interruption"` |

---

*End of document.*
